"""
modules/market_data/upstox/repair_ohlcv_window.py

ONE-OFF repair: re-fetch a recent window of D/W/M candles and merge it into the existing
R2 Parquet, to fill days the refresh missed. Created for the hole the data audit found:
the 2026-08-24 daily bar is missing for every instrument (the weekly bar for that week
has it; the daily does not).

It reuses the proven store logic as-is -- ohlcv_store.update_instrument(): fetch-first,
merge on (timeframe, ts) keeping the freshest row, and skip the R2 write when nothing
changed. It does NOT touch the f_ohlcv_fetch_progress ledger (no mark_attempt/mark_done),
so normal refreshes are unaffected. No pipeline code is changed.

How the window is set: update_instrument() derives its window from `last_success_at`
(window = that date -> today). Here we pass an explicit date instead of the ledger's.
That is safe because (a) the cooldown check only compares it against "now" and (b) the
merge only adds/overwrites bars inside the window.

Scope:
  --scope watchlist (default)  Nifty 50 + F&O-eligible stocks (the watchlist)
  --scope all                  every active stock + every active index (~18 min at 4 workers)

Usage (from backend/):
    python -m modules.market_data.upstox.repair_ohlcv_window --dry-run
    python -m modules.market_data.upstox.repair_ohlcv_window --limit 3        # verify first
    python -m modules.market_data.upstox.repair_ohlcv_window                  # watchlist
    python -m modules.market_data.upstox.repair_ohlcv_window --since 2026-08-17 --scope all

Then re-run the audit: REFERENCE_DAILY_MISSING and the 208 GAP_DAILY rows should be gone.
"""

from __future__ import annotations

import logging
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Callable, Optional

logger = logging.getLogger(__name__)

MAX_WORKERS = 4                 # same Cloudflare-safe count as the backfill/refresh runners
THROTTLE_SECONDS = 0.25         # per-worker pace, same as the backfill runner
DEFAULT_SINCE = "2026-08-17"    # the Monday before the missing day: covers the whole week + prior week
NIFTY50_KEY = "NSE_INDEX|Nifty 50"


@dataclass
class Target:
    instrument_key: str
    domain: str                 # 'indices' | 'universe' (the D/W/M domains)


def _paged(sb, table: str, columns: str, eq: dict) -> list:
    rows, start, page = [], 0, 1000
    while True:
        q = sb.table(table).select(columns)
        for k, v in eq.items():
            q = q.eq(k, v)
        batch = q.range(start, start + page - 1).execute().data or []
        rows.extend(batch)
        if len(batch) < page:
            return rows
        start += page


def load_targets(scope: str) -> list[Target]:
    """Instruments to repair, from the active catalogues (same tables the pipelines use)."""
    from db.supabase_client import get_supabase
    sb = get_supabase()
    targets: list[Target] = []
    if scope == "all":
        for r in _paged(sb, "f_all_nse_index_instruments", "instrument_key", {"is_active": True}):
            targets.append(Target(r["instrument_key"], "indices"))
        for r in _paged(sb, "f_universe_instruments", "instrument_key", {"is_active": True}):
            targets.append(Target(r["instrument_key"], "universe"))
    else:
        targets.append(Target(NIFTY50_KEY, "indices"))
        for r in _paged(sb, "f_universe_instruments", "instrument_key",
                        {"is_active": True, "is_fno_eligible": True}):
            targets.append(Target(r["instrument_key"], "universe"))
    return targets


def run_repair(targets: list[Target], updater: Callable, since: str,
               workers: int = MAX_WORKERS) -> Counter:
    """Run `updater(instrument_key, domain, last_success_at=...)` for every target on a
    thread pool. `updater` is ohlcv_store.update_instrument in production (injected so the
    orchestration is testable). Returns counts: repaired / unchanged / failed."""
    since_ts = f"{since}T00:00:00"      # update_instrument slices [:10] for the date
    counts: Counter = Counter()
    failures: list[tuple[str, str]] = []

    def work(t: Target):
        try:
            res = updater(t.instrument_key, t.domain, last_success_at=since_ts)
            time.sleep(THROTTLE_SECONDS)
            return t, res, None
        except Exception as exc:  # noqa: BLE001 -- one bad instrument must not stop the run
            return t, None, f"{type(exc).__name__}: {exc}"

    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(work, t) for t in targets]
        for i, fut in enumerate(as_completed(futs), 1):
            t, res, err = fut.result()
            if err or res is None or not res.ok:
                counts["failed"] += 1
                msg = err or (res.error if res else "no result")
                failures.append((t.instrument_key, msg or "unknown"))
                logger.warning("FAILED %s: %s", t.instrument_key, msg)
            elif res.skipped:
                counts["skipped"] += 1                      # cooldown (shouldn't happen with an old --since)
            elif res.changed:
                counts["repaired"] += 1
            else:
                counts["unchanged"] += 1
            if i % 50 == 0:
                logger.info("  %d/%d done  %s", i, len(targets), dict(counts))
    counts["_failures"] = len(failures)
    for ik, msg in failures[:20]:
        logger.info("  failure: %-28s %s", ik, msg[:90])
    return counts


def cli_main() -> None:
    import argparse
    import os
    from dotenv import load_dotenv

    load_dotenv()
    os.makedirs("logs", exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[logging.StreamHandler(),
                  logging.FileHandler("logs/ohlcv_repair_window.log", mode="w")],   # overwritten each run
    )
    p = argparse.ArgumentParser(description="One-off D/W/M window repair (merge-only, ledger untouched).")
    p.add_argument("--since", default=DEFAULT_SINCE, help="window start, YYYY-MM-DD (default %(default)s)")
    p.add_argument("--scope", choices=("watchlist", "all"), default="watchlist")
    p.add_argument("--limit", type=int, default=None, help="repair only the first N targets (verify first)")
    p.add_argument("--dry-run", action="store_true", help="list targets and window, fetch nothing")
    args = p.parse_args()

    targets = load_targets(args.scope)
    if args.limit:
        targets = targets[: args.limit]
    logger.info("Repair window %s -> today | scope=%s | %d target(s)%s", args.since, args.scope,
                len(targets), " | DRY RUN" if args.dry_run else "")
    if args.dry_run:
        for t in targets[:10]:
            logger.info("  would repair %s (%s)", t.instrument_key, t.domain)
        if len(targets) > 10:
            logger.info("  ... and %d more", len(targets) - 10)
        return

    from modules.market_data.upstox.ohlcv_store import update_instrument
    counts = run_repair(targets, update_instrument, args.since)
    logger.info("=" * 60)
    logger.info("REPAIR SUMMARY  repaired=%d  unchanged=%d  skipped=%d  failed=%d",
                counts["repaired"], counts["unchanged"], counts["skipped"], counts["failed"])
    logger.info("repaired = bars added/changed and file rewritten; unchanged = window already matched")
    logger.info("=" * 60)


if __name__ == "__main__":
    cli_main()
