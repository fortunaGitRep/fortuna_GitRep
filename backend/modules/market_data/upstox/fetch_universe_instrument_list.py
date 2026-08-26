"""
modules/market_data/upstox/fetch_universe_instrument_list.py

Domain-1 foundation fetch: builds the tradable-equity universe from Upstox's
per-exchange instrument master file. Populates f_universe_instruments, which
every downstream fundamentals/OHLCV job loops over.

>>> PHASE 1 (this version): DOWNLOAD + PARSE + FILTER + SUMMARISE ONLY. <<<
No database writes. This exists to verify the raw data is sane (right counts,
expected fields present, F&O flagging correct) BEFORE we let anything touch the
DB. Phase 2 will add the diff + upsert into f_universe_instruments on top of the
functions here. Verify-first mirrors how the Dhan layer was proven on real data
before wiring it into the funnel.

Design notes / ADR:
  - SOURCE: the per-exchange BOD file NSE.json.gz (not `complete`) — cheaper pull,
    contains everything the 3 domains need (NSE_EQ, NSE_INDEX, NSE_FO). Exchange is
    a parameter so MCX/BSE later is one call, not a new script.
        https://assets.upstox.com/market-quote/instruments/exchange/NSE.json.gz
  - IDENTITY: instrument_key ('NSE_EQ|INE002A01018') is the stable key. exchange_token
    is deliberately ignored for identity (Upstox warns it can be reused after expiry).
  - ETFs: NSE_EQ contains both company stock (instrument_type 'EQ') and ETFs. We KEEP
    both and distinguish by instrument_type, rather than dropping ETFs — capturing the
    data now is free and future ETF research shouldn't require a re-fetch. Downstream
    the fundamentals fetcher filters to instrument_type='EQ' (ETFs have no company
    fundamentals); OHLCV can include both.
  - F&O ELIGIBILITY: derived, not hand-listed. Scan NSE_FO records, collect their
    underlying instrument_keys, then an NSE_EQ stock is F&O-eligible iff its
    instrument_key is in that set. This is how Watchlist 2 (~208 names) falls out of
    the exchange's own data.
  - DEFENSIVE PARSING (from community reports): some fields (e.g. trading_symbol) have
    been reported missing/renamed in the downloadable file vs the API sample, and the
    public URL occasionally has SSL/availability hiccups. So: fetch via requests with
    retry/backoff + explicit cert handling, tolerate missing optional fields, and the
    Phase-1 summary REPORTS field presence so we catch schema surprises before Phase 2.

Standards applied: single responsibility, DRY, defensive programming, graceful
error handling, bounded retry w/ backoff, structured logging (no secrets),
stdlib + requests only (no pandas dependency for a simple JSON parse).
Deferred to Phase 2: DB diff/upsert, is_active soft-delete, f_fetch_status seeding.
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

# Segments we care about within the NSE file.
SEGMENT_EQUITY = "NSE_EQ"     # NOTE: this segment is NOT equities-only — it also holds
                              # a large pile of govt securities / bonds / debt (SG, GS,
                              # TB, GB, N*, Y*, Z* instrument_types). Segment alone is
                              # insufficient; we MUST also filter by instrument_type.
SEGMENT_FNO = "NSE_FO"        # used only to derive F&O-eligibility of equities
SEGMENT_INDEX = "NSE_INDEX"   # indices — counted here, but stored elsewhere (Domains 2+3)

# The instrument_type(s) that constitute our investable stock universe. NSE_EQ segment
# contains ~9,700 records but only ~2,600 are actual company equity shares ('EQ'); the
# rest are Sovereign Gilts (SG), Govt Securities (GS), T-Bills (TB), Govt Bonds (GB),
# and many debt series (N*/Y*/Z*) that are not stocks and have no company fundamentals.
# Confirmed via Phase-1 census 2026-08-23. ETFs are a future research item (chosen to
# defer 2026-08-23); if they turn out to be typed 'EQ' they're captured automatically,
# otherwise ETF handling gets its own design pass when researched.
EQUITY_INSTRUMENT_TYPES = {"EQ"}

DOWNLOAD_TIMEOUT_SECONDS = 60   # the gz file is a few MB
MAX_RETRIES = 3
BACKOFF_BASE_SECONDS = 2.0      # 2s, 4s, 8s


@dataclass
class UniverseRow:
    """One tradable-equity instrument, normalised to what f_universe_instruments
    stores. Field names match the DB columns 1:1 so Phase 2's upsert is trivial."""
    instrument_key: str
    trading_symbol: Optional[str]
    name: Optional[str]
    isin: Optional[str]
    exchange: str
    segment: str
    instrument_type: Optional[str]
    is_fno_eligible: bool = False


@dataclass
class UniverseFetchResult:
    """Normalised result. `ok` is the single flag callers check. Rows are the
    filtered equity universe; `summary` carries counts for the verify step."""
    ok: bool
    rows: list[UniverseRow] = field(default_factory=list)
    summary: dict = field(default_factory=dict)
    error: Optional[str] = None


# --- Download --------------------------------------------------------------

def _download_instrument_file(exchange: str) -> list[dict]:
    """
    Download and decompress the exchange BOD JSON.gz into a list of dicts.
    Bounded retry with backoff on transient network/SSL failures. Raises the
    last exception if every attempt fails (caller converts to ok=False).
    """
    url = INSTRUMENTS_URL_TEMPLATE.format(exchange=exchange)
    last_exc: Optional[Exception] = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            logger.info("Downloading instrument file (attempt %d/%d): %s",
                        attempt, MAX_RETRIES, url)
            resp = requests.get(url, timeout=DOWNLOAD_TIMEOUT_SECONDS)
            resp.raise_for_status()
            # File is gzipped JSON. Decompress in-memory.
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


# --- Field access (defensive: file schema has surprised people) -------------

def _get(rec: dict, *keys: str) -> Optional[str]:
    """Return the first present, non-empty value among candidate keys, else None.
    Tolerates the file using a different key name than the API sample."""
    for k in keys:
        v = rec.get(k)
        if v not in (None, ""):
            return v
    return None


# --- Parse / filter / cross-reference --------------------------------------

def _build_fno_underlying_keys(records: list[dict]) -> set[str]:
    """
    Collect the set of underlying instrument_keys referenced by NSE_FO contracts.
    An equity is F&O-eligible iff its instrument_key is in this set.
    Different file versions have used 'underlying_key' or 'underlying_symbol' — we
    prefer the key form (unambiguous); fall back is handled by the caller matching
    on whatever we collected.
    """
    keys: set[str] = set()
    for rec in records:
        if rec.get("segment") != SEGMENT_FNO:
            continue
        uk = _get(rec, "underlying_key", "underlying_instrument_key")
        if uk:
            keys.add(uk)
    return keys


def _filter_equities(records: list[dict], fno_keys: set[str], exchange: str) -> list[UniverseRow]:
    """Filter to actual equity shares (NSE_EQ segment AND an equity instrument_type)
    and map to UniverseRow, flagging F&O eligibility. The instrument_type filter is
    essential — the NSE_EQ segment also carries govt securities/bonds/debt that are
    not stocks (see EQUITY_INSTRUMENT_TYPES)."""
    rows: list[UniverseRow] = []
    for rec in records:
        if rec.get("segment") != SEGMENT_EQUITY:
            continue
        if rec.get("instrument_type") not in EQUITY_INSTRUMENT_TYPES:
            continue
        instrument_key = _get(rec, "instrument_key")
        if not instrument_key:
            # An equity with no instrument_key is unusable as an identity — skip + log.
            logger.warning("Skipping equity record with no instrument_key: %s",
                           str(rec)[:120])
            continue
        rows.append(UniverseRow(
            instrument_key=instrument_key,
            trading_symbol=_get(rec, "trading_symbol", "tradingsymbol", "symbol"),
            name=_get(rec, "name"),
            isin=_get(rec, "isin"),
            exchange=exchange,
            segment=SEGMENT_EQUITY,
            instrument_type=_get(rec, "instrument_type"),
            is_fno_eligible=instrument_key in fno_keys,
        ))
    return rows


def fetch_universe(exchange: str = "NSE") -> UniverseFetchResult:
    """
    PHASE 1 entry point. Download + parse + filter + cross-reference, returning the
    equity universe and a summary. Does NOT write to the DB. Never raises for
    expected failure modes (network) — returns ok=False instead.
    """
    try:
        records = _download_instrument_file(exchange)
    except Exception as exc:  # noqa: BLE001
        logger.error("Instrument fetch failed for %s: %s", exchange, exc)
        return UniverseFetchResult(ok=False, error=f"download failed: {exc}")

    # Segment census across the whole file (sanity: does the file look right?).
    segment_counts = Counter(r.get("segment", "<none>") for r in records)

    fno_keys = _build_fno_underlying_keys(records)
    rows = _filter_equities(records, fno_keys, exchange)

    if not rows:
        return UniverseFetchResult(
            ok=False,
            summary={"segment_counts": dict(segment_counts)},
            error="no NSE_EQ rows parsed — check segment naming / file schema",
        )

    # Verify-step metrics.
    type_counts = Counter(r.instrument_type or "<none>" for r in rows)
    fno_count = sum(1 for r in rows if r.is_fno_eligible)
    missing_symbol = sum(1 for r in rows if not r.trading_symbol)
    missing_isin = sum(1 for r in rows if not r.isin)

    summary = {
        "exchange": exchange,
        "raw_record_count": len(records),
        "segment_counts": dict(segment_counts),
        "equity_row_count": len(rows),
        "instrument_type_counts": dict(type_counts),
        "fno_eligible_count": fno_count,
        "fno_underlying_keys_found": len(fno_keys),
        "rows_missing_trading_symbol": missing_symbol,
        "rows_missing_isin": missing_isin,
    }
    logger.info("Universe parsed: %d equities, %d F&O-eligible.", len(rows), fno_count)
    return UniverseFetchResult(ok=True, rows=rows, summary=summary)


# --- Phase 1 manual run: print the summary so we can eyeball the data -------

def _print_summary(result: UniverseFetchResult) -> None:
    print("\n" + "=" * 60)
    print("UNIVERSE INSTRUMENT FETCH — PHASE 1 (no DB write)")
    print("=" * 60)
    if not result.ok:
        print(f"FAIL -- {result.error}")
        if result.summary:
            print(f"segment_counts seen: {result.summary.get('segment_counts')}")
        return

    s = result.summary
    print(f"Exchange                 : {s['exchange']}")
    print(f"Raw records in file      : {s['raw_record_count']:,}")
    print(f"Equity rows (NSE_EQ)     : {s['equity_row_count']:,}")
    print(f"  by instrument_type     : {s['instrument_type_counts']}")
    print(f"F&O-eligible equities    : {s['fno_eligible_count']:,}")
    print(f"F&O underlying keys found: {s['fno_underlying_keys_found']:,}  "
          f"(>= eligible is normal: some underlyings are indices, not equities)")
    print(f"Rows missing symbol      : {s['rows_missing_trading_symbol']:,}")
    print(f"Rows missing ISIN        : {s['rows_missing_isin']:,}")
    print("\nAll segments in file     :")
    for seg, cnt in sorted(s["segment_counts"].items(), key=lambda kv: -kv[1]):
        print(f"    {seg:<16} {cnt:>8,}")

    print("\nSample equity rows (first 5):")
    for r in result.rows[:5]:
        print(f"    {r.instrument_key:<24} {str(r.trading_symbol):<12} "
              f"type={r.instrument_type:<6} fno={r.is_fno_eligible} isin={r.isin}")

    print("\nSample F&O-eligible rows (first 5):")
    fno_rows = [r for r in result.rows if r.is_fno_eligible][:5]
    for r in fno_rows:
        print(f"    {r.instrument_key:<24} {str(r.trading_symbol):<12} isin={r.isin}")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    # Two run modes:
    #   verify (default): download + parse + print summary, NO DB write.
    #     python -m modules.market_data.upstox.fetch_universe_instrument_list
    #   sync: download + parse + WRITE to f_universe_instruments (Phase 2).
    #     python -m modules.market_data.upstox.fetch_universe_instrument_list --sync
    import sys
    from dotenv import load_dotenv

    # Load .env FIRST, before any import chain touches os.environ. The store ->
    # db.supabase_client chain reads env vars at call time; nothing else in this
    # path loads .env (unlike upstox_auth_client, which self-loads). Idempotent.
    load_dotenv()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    result = fetch_universe("NSE")
    _print_summary(result)

    if "--sync" in sys.argv:
        if not result.ok:
            print("Not syncing — fetch failed.")
            raise SystemExit(1)
        # Imported here so the verify mode has zero DB dependency.
        from modules.market_data.upstox.instrument_store import sync_catalog
        print("\nSyncing to f_universe_instruments ...")
        store_result = sync_catalog("UNIVERSE", result.rows)
        if store_result.ok:
            print(f"SYNC OK -- upserted {store_result.upserted}, "
                  f"marked_inactive {store_result.marked_inactive}.")
        else:
            print(f"SYNC FAILED -- {store_result.error}")
            raise SystemExit(1)
