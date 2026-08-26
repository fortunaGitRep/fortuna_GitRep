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
    seed_from_catalogue(...)            # ensure a row exists per instrument
    for ik, domain in get_pending():    # only not-yet-done instruments
        mark_attempt(ik)                # attempt_count++, stamp last_attempt_at
        result = backfill_instrument(ik, domain)   # (ohlcv_store)
        if result.ok: mark_done(ik)
        else:         mark_failed(ik, result.error)

Scope: OHLCV only (fundamentals/news get their own trackers later). One row per
instrument, keyed by instrument_key.

Standards applied: single responsibility (ledger access only — no fetching/storing),
idempotent seeding (upsert, safe to re-run), defensive (validate status values),
structured logging (no secrets). Bounded reads (status-filtered, paginated).
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

_VALID_DOMAINS = {"universe", "indices"}


@dataclass
class PendingItem:
    """One instrument still needing an OHLCV fetch."""
    instrument_key: str
    domain: str
    status: str
    attempt_count: int
    last_success_at: Optional[str]   # ISO str or None; None => never backfilled (full fetch)


# --- Seeding ---------------------------------------------------------------

def seed_instruments(rows: list[tuple[str, str]]) -> int:
    """
    Ensure a progress row exists for each (instrument_key, domain). Idempotent:
    uses upsert on instrument_key, and DOES NOT reset status/counters for rows that
    already exist (only inserts missing ones as 'pending'). Returns count seeded.

    Implementation note: we can't blindly upsert full rows (that would reset a 'done'
    row back to 'pending'). So we insert with ignore-on-conflict semantics by only
    sending the identity + defaults, relying on the PK conflict to no-op existing rows.
    """
    if not rows:
        return 0
    for _, domain in rows:
        if domain not in _VALID_DOMAINS:
            raise ValueError(f"Invalid domain '{domain}'. Valid: {sorted(_VALID_DOMAINS)}")

    supabase = get_supabase()
    payloads = [{"instrument_key": ik, "domain": dom, "status": _STATUS_PENDING}
                for ik, dom in rows]

    # ignore_duplicates=True => existing rows are left untouched (no status reset);
    # only brand-new instrument_keys get inserted as pending.
    CHUNK = 500
    total = 0
    for i in range(0, len(payloads), CHUNK):
        batch = payloads[i:i + CHUNK]
        supabase.table(_TABLE).upsert(
            batch, on_conflict="instrument_key", ignore_duplicates=True
        ).execute()
        total += len(batch)
    logger.info("seed_instruments: ensured %d progress row(s) exist (existing untouched).",
                total)
    return total


# --- Read (work list) ------------------------------------------------------

def get_pending(domain: Optional[str] = None, include_failed: bool = True) -> list[PendingItem]:
    """
    Instruments still needing a fetch: status != 'done'. Optionally scope to one
    domain. include_failed=True (default) re-includes previously-failed rows so a
    re-run retries them; set False to fetch only never-attempted 'pending' ones.
    Paginated — safe as the table grows.
    """
    supabase = get_supabase()
    statuses = [_STATUS_PENDING, _STATUS_FAILED] if include_failed else [_STATUS_PENDING]

    items: list[PendingItem] = []
    PAGE = 1000
    start = 0
    while True:
        q = (supabase.table(_TABLE)
             .select("instrument_key, domain, status, attempt_count, last_success_at")
             .in_("status", statuses))
        if domain is not None:
            q = q.eq("domain", domain)
        resp = q.range(start, start + PAGE - 1).execute()
        batch = resp.data or []
        for r in batch:
            items.append(PendingItem(
                instrument_key=r["instrument_key"],
                domain=r["domain"],
                status=r["status"],
                attempt_count=r["attempt_count"],
                last_success_at=r.get("last_success_at"),
            ))
        if len(batch) < PAGE:
            break
        start += PAGE
    logger.info("get_pending(domain=%s, include_failed=%s): %d instrument(s) to fetch.",
                domain, include_failed, len(items))
    return items


# --- Write (status transitions) --------------------------------------------

def mark_attempt(instrument_key: str) -> None:
    """Increment attempt_count + stamp last_attempt_at, just before a fetch try.
    Read-modify-write of attempt_count (single-user backend, no concurrency)."""
    supabase = get_supabase()
    resp = (supabase.table(_TABLE)
            .select("attempt_count")
            .eq("instrument_key", instrument_key)
            .limit(1).execute())
    current = (resp.data[0]["attempt_count"] if resp.data else 0)
    supabase.table(_TABLE).update({
        "attempt_count": current + 1,
        "last_attempt_at": _now_ist_iso(),
    }).eq("instrument_key", instrument_key).execute()


def mark_done(instrument_key: str) -> None:
    """Mark a successful fetch+store: status=done, stamp last_success_at, clear error."""
    supabase = get_supabase()
    supabase.table(_TABLE).update({
        "status": _STATUS_DONE,
        "last_success_at": _now_ist_iso(),
        "last_error": None,
    }).eq("instrument_key", instrument_key).execute()
    logger.info("mark_done: %s", instrument_key)


def mark_failed(instrument_key: str, error: str) -> None:
    """Mark a failed fetch: status=failed, record the (truncated) error."""
    supabase = get_supabase()
    supabase.table(_TABLE).update({
        "status": _STATUS_FAILED,
        "last_error": (error or "")[:1000],
    }).eq("instrument_key", instrument_key).execute()
    logger.warning("mark_failed: %s -- %s", instrument_key, (error or "")[:200])


# --- Small helpers ---------------------------------------------------------

def _now_ist_iso() -> str:
    """IST timestamp as ISO string, matching the DB's now_ist() convention for
    application-side writes. (The DB default/trigger handles created_at/updated_at;
    last_success_at is set by us here.)"""
    from datetime import datetime, timezone, timedelta
    ist = timezone(timedelta(hours=5, minutes=30))
    return datetime.now(ist).replace(tzinfo=None).isoformat(timespec="seconds")


def get_counts() -> dict:
    """Summary counts by status — for run summaries / sanity checks."""
    supabase = get_supabase()
    out = {"pending": 0, "done": 0, "failed": 0, "total": 0}
    for status in (_STATUS_PENDING, _STATUS_DONE, _STATUS_FAILED):
        resp = (supabase.table(_TABLE)
                .select("instrument_key", count="exact")
                .eq("status", status).execute())
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
    print("f_ohlcv_fetch_progress counts:", get_counts())
