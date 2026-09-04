"""
modules/market_data/upstox/ohlcv_fetch_progress.py

Read/write layer for the f_ohlcv_fetch_progress ledger — the resumability tracker
for OHLCV backfills and daily updates. Imports the shared Supabase connection from
db/supabase_client; does NOT build its own (infra-vs-feature separation, same as
instrument_store.py / index_store.py).

WHAT IT'S FOR:
  A bulk OHLCV job (2.5+) loops over thousands of instruments. Runs get interrupted
  (network, rate-limit pause, laptop closed). This ledger records per-instrument
  status so a re-run SKIPS what's done and RESUMES where it stopped, and so failed
  instruments are visible for retry rather than silently blocking the run.

TYPICAL USE (by the bulk caller):
    seed_from_catalogue(...)               # ensure a row exists per instrument
    for ik, domain in get_pending(domain): # only not-yet-done instruments
        mark_attempt(ik, domain)           # attempt_count++, stamp last_attempt_at
        result = backfill_instrument(ik, domain)   # (ohlcv_store)
        if result.ok: mark_done(ik, domain)
        else:         mark_failed(ik, domain, result.error)

TWO TRACKING SHAPES ON ONE TABLE (added 2026-09-04):
  f_ohlcv_fetch_progress's primary key is instrument_key ALONE. The
  'universe_intraday' domain (5m/15m/60m OHLCV, F&O-eligible stocks only) tracks
  the SAME instrument_keys as the existing 'universe' domain (same stocks, a
  different dataset) — so a stock's row can't simply be re-seeded under a second
  domain value; that upsert silently no-ops on the existing instrument_key
  (confirmed live: 208 F&O keys loaded, 0 seeded, 0 pending).

  Rather than change the primary key to a composite (instrument_key, domain) —
  deliberately ruled out — this module gives 'universe_intraday' its OWN column
  set (intraday_status / intraday_attempt_count / intraday_last_attempt_at /
  intraday_last_success_at / intraday_last_error) on the SAME row, tracked
  independently of the original status/attempt_count/.../last_error columns that
  'universe' and 'indices' still use exactly as before. Every function below
  branches on `domain == 'universe_intraday'` to pick the right column set; the
  original 'universe'/'indices' code path is byte-for-byte the same behavior as
  before this change.

  intraday_status is NULL for any row never seeded into that domain (e.g. an
  index, or a non-F&O stock) — that's what lets get_pending/get_done scope
  correctly to just the F&O subset without a `domain` column filter (which
  would look at the wrong value: these rows' `domain` column still reads
  'universe', since that's the domain that originally created the row).

Scope: OHLCV only (fundamentals/news get their own trackers later). One row per
instrument, keyed by instrument_key.

Standards applied: single responsibility (ledger access only — no fetching/storing),
idempotent seeding (upsert / update-if-null, safe to re-run), defensive (validate
status + domain values), structured logging (no secrets). Bounded reads
(status-filtered, paginated).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from db.supabase_client import get_supabase

logger = logging.getLogger(__name__)

_TABLE = "f_ohlcv_fetch_progress"

# Allowed status values (guard against typos writing garbage into the ledger).
_STATUS_PENDING = "pending"
_STATUS_DONE = "done"
_STATUS_FAILED = "failed"
_VALID_STATUS = {_STATUS_PENDING, _STATUS_DONE, _STATUS_FAILED}

_VALID_DOMAINS = {"universe", "indices", "universe_intraday"}

# The one domain that uses the separate intraday_* column set instead of the
# original status/attempt_count/.../last_error columns. Everything else in this
# module branches on this single constant — one place to extend if a future
# domain ever needs the same treatment (or, better, revisit the composite-PK
# option at that point instead of adding a third column set).
_INTRADAY_DOMAIN = "universe_intraday"


@dataclass
class PendingItem:
    """One instrument still needing an OHLCV fetch. Same shape regardless of
    which column set it was actually read from."""
    instrument_key: str
    domain: str
    status: str
    attempt_count: int
    last_success_at: Optional[str]   # ISO str or None; None => never backfilled (full fetch)


# --- Seeding ---------------------------------------------------------------

def seed_instruments(rows: list[tuple[str, str]]) -> int:
    """
    Ensure a progress row exists for each (instrument_key, domain) and that the
    RIGHT column set is initialised to 'pending' for it. Idempotent either way:
    never resets an already-seeded row's progress. Returns count touched.

    'universe' / 'indices': unchanged from before this file's intraday-columns
    change — insert-only upsert (ignore_duplicates=True) on instrument_key; a
    row that already exists (already seeded, regardless of its status) is left
    completely untouched.

    'universe_intraday': the row almost always ALREADY EXISTS (created by the
    'universe' domain's own seeding, since intraday only ever covers stocks
    already in the universe catalogue). An insert-only upsert would no-op and
    never initialise intraday_status. So instead: an UPDATE that sets
    intraday_status='pending' WHERE instrument_key IN (these keys) AND
    intraday_status IS NULL — only touches rows not yet seeded for intraday,
    never resets a row already in progress. Falls back to a normal insert for
    the rare case an instrument_key has no row at all yet.
    """
    if not rows:
        return 0
    domains = {domain for _, domain in rows}
    for domain in domains:
        if domain not in _VALID_DOMAINS:
            raise ValueError(f"Invalid domain '{domain}'. Valid: {sorted(_VALID_DOMAINS)}")
    if len(domains) > 1:
        raise ValueError(f"seed_instruments expects one domain per call, got {sorted(domains)}")
    domain = next(iter(domains))
    keys = [ik for ik, _ in rows]

    supabase = get_supabase()
    CHUNK = 500

    if domain != _INTRADAY_DOMAIN:
        payloads = [{"instrument_key": ik, "domain": dom, "status": _STATUS_PENDING}
                    for ik, dom in rows]
        total = 0
        for i in range(0, len(payloads), CHUNK):
            batch = payloads[i:i + CHUNK]
            supabase.table(_TABLE).upsert(
                batch, on_conflict="instrument_key", ignore_duplicates=True
            ).execute()
            total += len(batch)
        logger.info("seed_instruments(%s): ensured %d progress row(s) exist (existing untouched).",
                    domain, total)
        return total

    # Intraday path: update-if-null on existing rows.
    total = 0
    for i in range(0, len(keys), CHUNK):
        chunk = keys[i:i + CHUNK]
        resp = (supabase.table(_TABLE)
                .update({"intraday_status": _STATUS_PENDING})
                .in_("instrument_key", chunk)
                .is_("intraday_status", "null")
                .execute())
        total += len(resp.data or [])
    logger.info("seed_instruments(%s): initialised %d row(s) to intraday_status='pending' "
                "(already-seeded rows untouched).", domain, total)

    # Rare fallback: any of these instrument_keys with NO row at all yet (should
    # not happen in practice — F&O stocks are always seeded by 'universe' first
    # — but handled defensively rather than silently dropped).
    existing = (supabase.table(_TABLE).select("instrument_key")
                .in_("instrument_key", keys).execute())
    existing_keys = {r["instrument_key"] for r in (existing.data or [])}
    missing = [ik for ik in keys if ik not in existing_keys]
    if missing:
        payloads = [{"instrument_key": ik, "domain": domain, "status": _STATUS_PENDING,
                    "intraday_status": _STATUS_PENDING} for ik in missing]
        for i in range(0, len(payloads), CHUNK):
            supabase.table(_TABLE).upsert(
                payloads[i:i + CHUNK], on_conflict="instrument_key", ignore_duplicates=True
            ).execute()
        logger.warning("seed_instruments(%s): %d instrument_key(s) had no row at all "
                       "(unexpected) — inserted fresh.", domain, len(missing))
        total += len(missing)
    return total


# --- Read (work list) ------------------------------------------------------

def get_pending(domain: Optional[str] = None, include_failed: bool = True) -> list[PendingItem]:
    """
    Instruments still needing a fetch. Optionally scope to one domain.
    include_failed=True (default) re-includes previously-failed rows so a re-run
    retries them; set False to fetch only never-attempted 'pending' ones.
    Paginated — safe as the table grows.

    'universe' / 'indices': filters on the original status column + domain column,
    exactly as before.

    'universe_intraday': filters on intraday_status instead — critically, WITHOUT
    a domain-column filter, since these rows' domain column reads 'universe' (the
    domain that originally created them), not 'universe_intraday'. Scoping to the
    F&O subset comes entirely from intraday_status being non-NULL only for rows
    seed_instruments actually initialised.
    """
    supabase = get_supabase()
    statuses = [_STATUS_PENDING, _STATUS_FAILED] if include_failed else [_STATUS_PENDING]
    is_intraday = domain == _INTRADAY_DOMAIN
    status_col = "intraday_status" if is_intraday else "status"
    attempt_col = "intraday_attempt_count" if is_intraday else "attempt_count"
    success_col = "intraday_last_success_at" if is_intraday else "last_success_at"

    items: list[PendingItem] = []
    PAGE = 1000
    start = 0
    while True:
        q = (supabase.table(_TABLE)
             .select(f"instrument_key, domain, {status_col}, {attempt_col}, {success_col}")
             .in_(status_col, statuses))
        if domain is not None and not is_intraday:
            q = q.eq("domain", domain)
        resp = q.range(start, start + PAGE - 1).execute()
        batch = resp.data or []
        for r in batch:
            items.append(PendingItem(
                instrument_key=r["instrument_key"],
                domain=domain if is_intraday else r["domain"],
                status=r[status_col],
                attempt_count=r[attempt_col],
                last_success_at=r.get(success_col),
            ))
        if len(batch) < PAGE:
            break
        start += PAGE
    logger.info("get_pending(domain=%s, include_failed=%s): %d instrument(s) to fetch.",
                domain, include_failed, len(items))
    return items


def get_done(domain: Optional[str] = None) -> list[PendingItem]:
    """
    Instruments already backfilled — the refresh runner's work list. Same
    PendingItem shape and same domain-branching as get_pending, paginated.
    """
    supabase = get_supabase()
    is_intraday = domain == _INTRADAY_DOMAIN
    status_col = "intraday_status" if is_intraday else "status"
    attempt_col = "intraday_attempt_count" if is_intraday else "attempt_count"
    success_col = "intraday_last_success_at" if is_intraday else "last_success_at"

    items: list[PendingItem] = []
    PAGE = 1000
    start = 0
    while True:
        q = (supabase.table(_TABLE)
             .select(f"instrument_key, domain, {status_col}, {attempt_col}, {success_col}")
             .eq(status_col, _STATUS_DONE))
        if domain is not None and not is_intraday:
            q = q.eq("domain", domain)
        resp = q.range(start, start + PAGE - 1).execute()
        batch = resp.data or []
        for r in batch:
            items.append(PendingItem(
                instrument_key=r["instrument_key"],
                domain=domain if is_intraday else r["domain"],
                status=r[status_col],
                attempt_count=r[attempt_col],
                last_success_at=r.get(success_col),
            ))
        if len(batch) < PAGE:
            break
        start += PAGE
    logger.info("get_done(domain=%s): %d instrument(s) ready for refresh.", domain, len(items))
    return items


# --- Write (status transitions) --------------------------------------------
# All three now take `domain` explicitly — needed to pick the right column set.
# Call sites: _ohlcv_backfill_runner.py and _ohlcv_refresh_runner.py already
# have `cfg.domain`/`domain` in scope at every call site, so this is a small,
# mechanical addition there.

def mark_attempt(instrument_key: str, domain: str) -> None:
    """Increment the domain-appropriate attempt_count + stamp last_attempt_at,
    just before a fetch try. Read-modify-write (single-user backend, no
    concurrency)."""
    supabase = get_supabase()
    is_intraday = domain == _INTRADAY_DOMAIN
    attempt_col = "intraday_attempt_count" if is_intraday else "attempt_count"
    attempt_at_col = "intraday_last_attempt_at" if is_intraday else "last_attempt_at"

    resp = (supabase.table(_TABLE)
            .select(attempt_col)
            .eq("instrument_key", instrument_key)
            .limit(1).execute())
    current = (resp.data[0][attempt_col] if resp.data and resp.data[0].get(attempt_col) else 0)
    supabase.table(_TABLE).update({
        attempt_col: current + 1,
        attempt_at_col: _now_ist_iso(),
    }).eq("instrument_key", instrument_key).execute()


def mark_done(instrument_key: str, domain: str) -> None:
    """Mark a successful fetch+store in the domain-appropriate column set:
    status=done, stamp last_success_at, clear last_error."""
    supabase = get_supabase()
    is_intraday = domain == _INTRADAY_DOMAIN
    status_col = "intraday_status" if is_intraday else "status"
    success_col = "intraday_last_success_at" if is_intraday else "last_success_at"
    error_col = "intraday_last_error" if is_intraday else "last_error"

    supabase.table(_TABLE).update({
        status_col: _STATUS_DONE,
        success_col: _now_ist_iso(),
        error_col: None,
    }).eq("instrument_key", instrument_key).execute()
    logger.info("mark_done(%s): %s", domain, instrument_key)


def mark_failed(instrument_key: str, domain: str, error: str) -> None:
    """Mark a failed fetch in the domain-appropriate column set: status=failed,
    record the (truncated) error."""
    supabase = get_supabase()
    is_intraday = domain == _INTRADAY_DOMAIN
    status_col = "intraday_status" if is_intraday else "status"
    error_col = "intraday_last_error" if is_intraday else "last_error"

    supabase.table(_TABLE).update({
        status_col: _STATUS_FAILED,
        error_col: (error or "")[:1000],
    }).eq("instrument_key", instrument_key).execute()
    logger.warning("mark_failed(%s): %s -- %s", domain, instrument_key, (error or "")[:200])


# --- Small helpers ---------------------------------------------------------

def _now_ist_iso() -> str:
    """IST timestamp as ISO string, matching the DB's now_ist() convention for
    application-side writes. (The DB default/trigger handles created_at/updated_at;
    last_success_at / intraday_last_success_at are set by us here.)"""
    from datetime import datetime, timezone, timedelta
    ist = timezone(timedelta(hours=5, minutes=30))
    return datetime.now(ist).replace(tzinfo=None).isoformat(timespec="seconds")


def get_counts(domain: Optional[str] = None) -> dict:
    """
    Summary counts by status — for run summaries / sanity checks.
    domain=None (default): original behavior, counts the status column across
    ALL rows (universe + indices combined, as before this file's change).
    domain='universe_intraday': counts the intraday_status column instead —
    NULL rows (not seeded for intraday) are correctly excluded from every
    bucket, since they're not pending/done/failed for this domain at all.
    """
    supabase = get_supabase()
    is_intraday = domain == _INTRADAY_DOMAIN
    status_col = "intraday_status" if is_intraday else "status"

    out = {"pending": 0, "done": 0, "failed": 0, "total": 0}
    for status in (_STATUS_PENDING, _STATUS_DONE, _STATUS_FAILED):
        resp = (supabase.table(_TABLE)
                .select("instrument_key", count="exact")
                .eq(status_col, status).execute())
        out[status] = resp.count or 0
    out["total"] = out["pending"] + out["done"] + out["failed"]
    return out


if __name__ == "__main__":
    #   python -m modules.market_data.upstox.ohlcv_fetch_progress
    # Read-only smoke: print current counts (table must exist; may be empty).
    from dotenv import load_dotenv
    load_dotenv()
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    print("f_ohlcv_fetch_progress counts (universe+indices):", get_counts())
    print("f_ohlcv_fetch_progress counts (universe_intraday):", get_counts(domain="universe_intraday"))
