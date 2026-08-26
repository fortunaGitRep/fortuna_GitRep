"""
modules/market_data/upstox/fetch_index_instrument_list.py

Builds the index catalogue (Domains 2 + 3) from Upstox's NSE instrument file:
all NSE indices — broad-market, sector, thematic, strategy/factor, bond, etc.
Populates f_all_nse_index_instruments (Migration 004), which the index-OHLCV job
loops over.

>>> PHASE 1 (this version): DOWNLOAD + FILTER + SUMMARISE ONLY. <<<
No database writes. Prints every index so we can eyeball the full set before
storing — confirm the count, spot the exact Nifty 50 entry (which gets its own
file/handling, Domain 3), and sanity-check names. Phase 2 adds the diff + upsert.

Design notes / ADR:
  - SOURCE: same NSE.json.gz as the equity fetch; we just filter segment ==
    'NSE_INDEX' instead of 'NSE_EQ'. One file, two catalogues.
  - TABLE NAME f_all_nse_index_instruments — "all" signals the complete NSE index
    set (not a filtered subset), and stays accurate as NSE adds/retires indices over
    time (~139 as of 2026-08-23, but the name doesn't hardcode that). The live count
    is printed every run. REMINDER: the fetch captures whatever NSE currently
    publishes; if you later want to deliberately narrow/expand which indices are
    stored, that's a filter decision to revisit — the catalogue itself stays "all".
  - NIFTY 50 SPLIT (Domain 3 vs 2): all indices are catalogued here identically;
    the Nifty-50-gets-its-own-file decision lives in the OHLCV fetch code later
    (match on instrument_key = 'NSE_INDEX|Nifty 50'), NOT as a column/flag here —
    keeping this table pure catalogue data. This script prints which row is Nifty 50
    purely as a verification aid (confirmed exactly one match in the live file).
  - Indices have NO isin / fundamentals / F&O flag — hence a SEPARATE table from
    stocks (a combined table would be half-empty columns per row).

Standards applied: single responsibility, DRY (reuses the same download shape as
the equity fetch), defensive parsing, graceful errors, bounded retry w/ backoff,
structured logging, stdlib + requests only.
Deferred to Phase 2: DB diff/upsert into f_all_nse_index_instruments, is_active
soft-delete, f_fetch_status seeding.
"""

from __future__ import annotations

import gzip
import io
import json
import logging
import time
from collections import Counter
from dataclasses import dataclass, field
from typing import Optional

import requests

logger = logging.getLogger(__name__)

# --- Config ----------------------------------------------------------------

INSTRUMENTS_URL_TEMPLATE = (
    "https://assets.upstox.com/market-quote/instruments/exchange/{exchange}.json.gz"
)

SEGMENT_INDEX = "NSE_INDEX"

# The exact instrument_key / name we treat as Nifty 50 (Domain 3, own file). The
# instrument file has historically named it 'Nifty 50'. We match on name
# case-insensitively AND record the key we find, so downstream code can split by a
# verified instrument_key rather than a fragile string compare.
NIFTY_50_NAME_CANDIDATES = {"nifty 50", "nifty50"}

DOWNLOAD_TIMEOUT_SECONDS = 60
MAX_RETRIES = 3
BACKOFF_BASE_SECONDS = 2.0


@dataclass
class IndexRow:
    """One index instrument, normalised to what f_all_nse_index_instruments stores.
    No isin/fundamentals/fno — indices don't have them."""
    instrument_key: str
    trading_symbol: Optional[str]
    name: Optional[str]
    exchange: str
    segment: str
    instrument_type: Optional[str]


@dataclass
class IndexFetchResult:
    ok: bool
    rows: list[IndexRow] = field(default_factory=list)
    summary: dict = field(default_factory=dict)
    error: Optional[str] = None


# --- Download (same shape as the equity fetch) -----------------------------

def _download_instrument_file(exchange: str) -> list[dict]:
    url = INSTRUMENTS_URL_TEMPLATE.format(exchange=exchange)
    last_exc: Optional[Exception] = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            logger.info("Downloading instrument file (attempt %d/%d): %s",
                        attempt, MAX_RETRIES, url)
            resp = requests.get(url, timeout=DOWNLOAD_TIMEOUT_SECONDS)
            resp.raise_for_status()
            with gzip.GzipFile(fileobj=io.BytesIO(resp.content)) as gz:
                data = json.loads(gz.read().decode("utf-8"))
            if not isinstance(data, list):
                raise ValueError(f"expected a JSON list, got {type(data).__name__}")
            logger.info("Downloaded %d raw instrument records for %s", len(data), exchange)
            return data
        except (requests.RequestException, OSError, ValueError, json.JSONDecodeError) as exc:
            last_exc = exc
            wait = BACKOFF_BASE_SECONDS * (2 ** (attempt - 1))
            logger.warning("Instrument download failed (attempt %d/%d): %s. Retrying in %.1fs",
                           attempt, MAX_RETRIES, exc, wait)
            if attempt < MAX_RETRIES:
                time.sleep(wait)
    assert last_exc is not None
    raise last_exc


def _get(rec: dict, *keys: str) -> Optional[str]:
    for k in keys:
        v = rec.get(k)
        if v not in (None, ""):
            return v
    return None


def _filter_indices(records: list[dict], exchange: str) -> list[IndexRow]:
    rows: list[IndexRow] = []
    for rec in records:
        if rec.get("segment") != SEGMENT_INDEX:
            continue
        instrument_key = _get(rec, "instrument_key")
        if not instrument_key:
            logger.warning("Skipping NSE_INDEX record with no instrument_key: %s",
                           str(rec)[:120])
            continue
        rows.append(IndexRow(
            instrument_key=instrument_key,
            trading_symbol=_get(rec, "trading_symbol", "tradingsymbol", "symbol"),
            name=_get(rec, "name"),
            exchange=exchange,
            segment=SEGMENT_INDEX,
            instrument_type=_get(rec, "instrument_type"),
        ))
    return rows


def _is_nifty_50(row: IndexRow) -> bool:
    """Verification helper (for the Phase-1 summary print only). The Nifty-50
    special-casing for storage lives in the OHLCV fetch code later, not here."""
    return (row.name or "").strip().lower() in NIFTY_50_NAME_CANDIDATES


def fetch_indices(exchange: str = "NSE") -> IndexFetchResult:
    try:
        records = _download_instrument_file(exchange)
    except Exception as exc:  # noqa: BLE001
        logger.error("Index instrument fetch failed for %s: %s", exchange, exc)
        return IndexFetchResult(ok=False, error=f"download failed: {exc}")

    rows = _filter_indices(records, exchange)
    if not rows:
        return IndexFetchResult(ok=False, error="no NSE_INDEX rows parsed — check segment naming")

    nifty_50_rows = [r for r in rows if _is_nifty_50(r)]
    type_counts = Counter(r.instrument_type or "<none>" for r in rows)

    summary = {
        "exchange": exchange,
        "index_count": len(rows),
        "instrument_type_counts": dict(type_counts),
        "nifty_50_matches": len(nifty_50_rows),
        "nifty_50_keys": [r.instrument_key for r in nifty_50_rows],
    }
    logger.info("Indices parsed: %d total, %d Nifty-50 match(es).",
                len(rows), len(nifty_50_rows))
    return IndexFetchResult(ok=True, rows=rows, summary=summary)


# --- Phase 1 manual run: print all indices so we can read them --------------

def _print_summary(result: IndexFetchResult) -> None:
    print("\n" + "=" * 60)
    print("INDEX INSTRUMENT FETCH — PHASE 1 (no DB write)")
    print("=" * 60)
    if not result.ok:
        print(f"FAIL -- {result.error}")
        return

    s = result.summary
    print(f"Exchange              : {s['exchange']}")
    print(f"Total indices found   : {s['index_count']}   "
          f"(stored in f_all_nse_index_instruments — full NSE index set)")
    print(f"  by instrument_type  : {s['instrument_type_counts']}")
    print(f"Nifty 50 match(es)    : {s['nifty_50_matches']}  keys={s['nifty_50_keys']}")

    print("\nALL INDICES (sorted by name):")
    for r in sorted(result.rows, key=lambda x: (x.name or "").lower()):
        marker = "  <-- NIFTY 50 (own file downstream)" if _is_nifty_50(r) else ""
        print(f"    {str(r.name):<40} {r.instrument_key}{marker}")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    # Two run modes:
    #   verify (default): download + parse + print summary, NO DB write.
    #     python -m modules.market_data.upstox.fetch_index_instrument_list
    #   sync: download + parse + WRITE to f_all_nse_index_instruments (Phase 2).
    #     python -m modules.market_data.upstox.fetch_index_instrument_list --sync
    import sys
    from dotenv import load_dotenv

    # Load .env FIRST, before the store -> db.supabase_client chain reads
    # os.environ. Idempotent; harmless if something else also loads it.
    load_dotenv()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    result = fetch_indices("NSE")
    _print_summary(result)

    if "--sync" in sys.argv:
        if not result.ok:
            print("Not syncing — fetch failed.")
            raise SystemExit(1)
        from modules.market_data.upstox.instrument_store import sync_catalog
        print("\nSyncing to f_all_nse_index_instruments ...")
        store_result = sync_catalog("INDEX", result.rows)
        if store_result.ok:
            print(f"SYNC OK -- upserted {store_result.upserted}, "
                  f"marked_inactive {store_result.marked_inactive}.")
        else:
            print(f"SYNC FAILED -- {store_result.error}")
            raise SystemExit(1)
