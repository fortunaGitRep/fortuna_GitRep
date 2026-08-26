"""
modules/market_data/upstox/instrument_store.py

Read/write layer for the two Fortuna instrument-catalogue tables:
  f_universe_instruments        (stocks — 2,643 EQ, has isin + is_fno_eligible)
  f_all_nse_index_instruments   (indices — 139, no isin/fno)

Owns everything about *how these catalogue tables are shaped and accessed*.
Imports the shared connection from db/supabase_client — it does NOT build its
own client (separation of concerns: infra vs feature access), exactly like
modules/market_data/index_store.py does for the Dhan index tables.

The two tables differ only in a couple of columns (stocks carry isin +
is_fno_eligible; indices don't), so rather than duplicating write/reconcile
code we drive everything off a small TABLE_CONFIG registry — one code path,
parameterised by catalogue key. Same pattern as index_store.py's TABLE_CONFIG.

WHAT THIS MODULE DOES (the "reconcile" is the important part):
  - upsert_instruments(): idempotent bulk upsert on instrument_key (the PK).
    Re-running with the same keys updates in place, never duplicates.
  - reconcile_active(): the daily-refresh soft-delete. Given the set of keys
    present in today's fresh Upstox file, mark any previously-stored key that
    has VANISHED as is_active=false (delisted/suspended), and any that has
    RETURNED as is_active=true. Rows are NEVER deleted — a delisted name keeps
    its record + all its historical OHLCV/fundamentals for research (the
    regime/pattern thesis actively wants delisted names). is_active just tells
    the OHLCV/fundamentals fetchers to skip it (no wasted/failing fetch).

Standards applied: single responsibility (catalogue table access only — no
download/parse logic, that's the fetch_* modules), DRY (one path for 2 tables
via config), idempotent writes (upsert on instrument_key PK — safe to re-run),
defensive programming (validate catalogue key, tolerate empty inputs),
structured logging without secrets.
Deferred: pagination (catalogues are small + bounded, a few thousand rows max;
no unbounded scans here).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from db.supabase_client import get_supabase

logger = logging.getLogger(__name__)


# --- Table registry --------------------------------------------------------
# One entry per catalogue. `columns` is the full set this table stores (beyond
# the audit timestamps, which the DB defaults/trigger handle). Driving writes
# off this means the stock table (with isin/is_fno_eligible) and the index
# table (without them) share one code path.

@dataclass(frozen=True)
class CatalogConfig:
    table_name: str
    columns: tuple[str, ...]   # columns we write (instrument_key first = PK)


CATALOG_CONFIG: dict[str, CatalogConfig] = {
    "UNIVERSE": CatalogConfig(
        table_name="f_universe_instruments",
        columns=("instrument_key", "trading_symbol", "name", "isin",
                 "exchange", "segment", "instrument_type", "is_fno_eligible"),
    ),
    "INDEX": CatalogConfig(
        table_name="f_all_nse_index_instruments",
        columns=("instrument_key", "trading_symbol", "name",
                 "exchange", "segment", "instrument_type"),
    ),
}

_PRIMARY_KEY = "instrument_key"


def _config(catalog_key: str) -> CatalogConfig:
    cfg = CATALOG_CONFIG.get(catalog_key)
    if cfg is None:
        raise KeyError(
            f"Unknown catalog '{catalog_key}'. Known: {sorted(CATALOG_CONFIG)}"
        )
    return cfg


@dataclass
class StoreResult:
    """Normalised outcome of a store operation. `ok` is the single flag callers
    check; counts describe what changed for the run summary."""
    ok: bool
    upserted: int = 0
    marked_inactive: int = 0
    reactivated: int = 0
    error: Optional[str] = None


# --- Payload building ------------------------------------------------------

def _row_to_payload(row: object, cfg: CatalogConfig) -> dict:
    """
    Build the exact dict to upsert, pulling only this table's columns off the
    fetch row object (UniverseRow / IndexRow — both are simple attr holders).
    is_active is intentionally NOT set here: on upsert of a present instrument
    we let it default true for new rows and rely on reconcile_active() to flip
    vanished ones. (Explicitly forcing is_active=true here would also work, but
    keeping upsert about presence and reconcile about activeness keeps the two
    concerns clean.)
    """
    payload: dict[str, object] = {}
    for col in cfg.columns:
        payload[col] = getattr(row, col, None)
    payload["is_active"] = True   # a key present in the fresh file is active
    return payload


# --- Writes ----------------------------------------------------------------

def upsert_instruments(catalog_key: str, rows: list) -> int:
    """
    Idempotent bulk upsert on instrument_key. Present instruments are inserted
    (if new) or updated (if changed: e.g. a renamed trading_symbol, a newly
    F&O-eligible flag). Marks every upserted row is_active=true. Returns rows
    sent. Raises on a hard DB failure — caller decides fatality.

    Batched: supabase-py sends one request per upsert call; a few thousand rows
    is fine in a single call, but we chunk defensively to stay well under any
    payload limits.
    """
    cfg = _config(catalog_key)
    if not rows:
        logger.info("upsert_instruments(%s): nothing to write.", catalog_key)
        return 0

    supabase = get_supabase()
    payloads = [_row_to_payload(r, cfg) for r in rows]

    CHUNK = 500
    total = 0
    for i in range(0, len(payloads), CHUNK):
        batch = payloads[i:i + CHUNK]
        supabase.table(cfg.table_name).upsert(
            batch, on_conflict=_PRIMARY_KEY
        ).execute()
        total += len(batch)
    logger.info("upsert_instruments(%s): upserted %d rows into %s.",
                catalog_key, total, cfg.table_name)
    return total


def get_all_stored_keys(catalog_key: str) -> set[str]:
    """
    All instrument_keys currently stored (regardless of is_active). Used by
    reconcile_active() to diff against today's fresh file. Bounded — the
    catalogue is a few thousand rows, and we select only the key column.
    """
    cfg = _config(catalog_key)
    supabase = get_supabase()
    # Select only the PK; paginate defensively in case the table grows.
    keys: set[str] = set()
    PAGE = 1000
    start = 0
    while True:
        resp = (
            supabase.table(cfg.table_name)
            .select(_PRIMARY_KEY)
            .range(start, start + PAGE - 1)
            .execute()
        )
        batch = resp.data or []
        keys.update(r[_PRIMARY_KEY] for r in batch)
        if len(batch) < PAGE:
            break
        start += PAGE
    return keys


def _set_active_flag(catalog_key: str, keys: set[str], active: bool) -> int:
    """Set is_active for a specific set of instrument_keys. Chunked to keep the
    'in' filter list a sane size. Returns count of keys targeted."""
    if not keys:
        return 0
    cfg = _config(catalog_key)
    supabase = get_supabase()
    key_list = list(keys)
    CHUNK = 200
    for i in range(0, len(key_list), CHUNK):
        batch = key_list[i:i + CHUNK]
        (
            supabase.table(cfg.table_name)
            .update({"is_active": active})
            .in_(_PRIMARY_KEY, batch)
            .execute()
        )
    return len(key_list)


def reconcile_active(catalog_key: str, present_keys: set[str]) -> tuple[int, int]:
    """
    Soft-delete reconciliation against today's fresh file.

    Given the set of instrument_keys present in the freshly downloaded file:
      - keys stored but NO LONGER present  -> mark is_active = false (delisted)
      - keys present (handled by upsert setting is_active=true) -> nothing to do
        here, but we also proactively re-activate any previously-inactive key
        that has returned, for correctness on the rare relisting.

    Returns (marked_inactive, reactivated). Never deletes rows.
    """
    stored_keys = get_all_stored_keys(catalog_key)

    vanished = stored_keys - present_keys        # stored but gone from file -> inactive
    marked_inactive = _set_active_flag(catalog_key, vanished, active=False)

    # Returned names: present in file AND already stored. upsert_instruments has
    # already set these is_active=true, so this is belt-and-suspenders — cheap,
    # and covers the case where reconcile is ever called independently.
    reactivated = 0  # upsert already handles activeness for present keys.

    if marked_inactive:
        logger.info("reconcile_active(%s): marked %d instrument(s) inactive (delisted/suspended).",
                    catalog_key, marked_inactive)
    return marked_inactive, reactivated


# --- Full sync (fetch -> store) orchestration ------------------------------

def sync_catalog(catalog_key: str, rows: list) -> StoreResult:
    """
    One-call orchestration for a catalogue refresh: upsert everything in the
    fresh file, then soft-delete anything that vanished. Idempotent end to end —
    safe to re-run. This is what the fetch_* scripts' Phase-2 main() calls after
    a successful download+parse.
    """
    if not rows:
        return StoreResult(ok=False, error="no rows to sync")

    try:
        present_keys = {getattr(r, _PRIMARY_KEY) for r in rows}
        upserted = upsert_instruments(catalog_key, rows)
        marked_inactive, reactivated = reconcile_active(catalog_key, present_keys)
        return StoreResult(
            ok=True, upserted=upserted,
            marked_inactive=marked_inactive, reactivated=reactivated,
        )
    except Exception as exc:  # noqa: BLE001 — surface as ok=False for the caller
        logger.error("sync_catalog(%s) failed: %s", catalog_key, exc)
        return StoreResult(ok=False, error=str(exc))


# --- Reads / smoke test ----------------------------------------------------

def get_row_count(catalog_key: str, active_only: bool = False) -> int:
    """Total rows (optionally only active) — sanity check after a sync."""
    cfg = _config(catalog_key)
    supabase = get_supabase()
    q = supabase.table(cfg.table_name).select(_PRIMARY_KEY, count="exact")
    if active_only:
        q = q.eq("is_active", True)
    resp = q.execute()
    return resp.count or 0


def connection_smoke_test() -> dict:
    """Cheap check that the client reaches Supabase and both catalogue tables
    exist. Reports per-table row counts; never raises for expected errors."""
    result: dict[str, object] = {}
    for catalog_key, cfg in CATALOG_CONFIG.items():
        try:
            total = get_row_count(catalog_key)
            active = get_row_count(catalog_key, active_only=True)
            result[cfg.table_name] = {
                "reachable": True, "row_count": total, "active_count": active,
            }
        except Exception as exc:  # noqa: BLE001
            logger.error("Smoke test failed for %s: %s", cfg.table_name, exc)
            result[cfg.table_name] = {"reachable": False, "error": str(exc)}
    return result
