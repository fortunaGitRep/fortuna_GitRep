"""
modules/market_data/upstox/ohlcv_store.py

Store layer for bulk OHLCV Parquet in Cloudflare R2. Owns everything about HOW an
instrument's candles are serialised, keyed, written, and read back. Imports the
shared R2 client from db/r2_client -- it does NOT build its own connection (same
infra-vs-feature separation as index_store.py / instrument_store.py use for Supabase).

The fetch engine (_ohlcv_engine.py) gets candles; THIS module persists them. The
dependency points one way: this imports the engine's fetch functions + result type.

Storage model (decided 2026-08-23):
  - One Parquet object per instrument, ALL timeframes stacked inside (a `timeframe`
    column distinguishes 1d/1w/1mo/...). Object storage can't append in place, so an
    "update" = read existing object -> merge new candles in memory -> write whole
    object back. This is data-incremental (old + new preserved) even though the object
    is rewritten each time.
  - ATOMIC + FETCH-FIRST: R2 put_object atomically replaces the object. We only ever
    write AFTER we have good data in hand, so a failed fetch can never destroy the
    existing file (no delete-first). The old object survives any upstream failure.
  - Key layout in the bucket:
        upstox/universe/<ISIN>.parquet         (stocks, key = ISIN portion)
        upstox/indices/<slugified name>.parquet (indices, spaces -> underscores)
    Derived from instrument_key (part after '|') + domain prefix passed by the caller.

Two write paths, one atomic core:
  - backfill_instrument(): first-time / full-history fetch -> write. Creates the file.
  - update_instrument():   fetch a short recent window -> merge into existing -> write.
    The routine daily path. Self-heals small gaps (the recent window overlaps).
  (No "overwrite mode" and no re-backfill machinery -- not needed; rebuilding is just
  running backfill again, which the atomic write handles.)

Cost visibility: every write logs bytes written + the object key, so R2 usage is
observable from day one (the lightweight half of the cost-tracking plan; the queryable
f_usage_log table comes later as its own module).

Standards applied: single responsibility (OHLCV persistence only -- no fetching, no
DB), atomic + fetch-first writes (never destroy on failure), defensive (validate
domain, tolerate missing existing file on update), structured logging (no secrets),
in-memory Parquet (no temp files).
Deferred: f_fetch_status wiring (2.4), the per-domain bulk callers (2.5+), local
read-cache (measure-first, maybe-never), usage-log table.
"""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Optional

import pandas as pd
from botocore.exceptions import ClientError

from db.r2_client import get_r2, get_r2_settings
from modules.market_data.upstox._ohlcv_engine import (
    OhlcvFetchResult,
    TIER1_TIMEFRAMES,
    fetch_all_timeframes,
    fetch_full_history,
)

logger = logging.getLogger(__name__)

# --- Config ----------------------------------------------------------------

# Domain -> R2 key prefix. Domain is passed by the caller (universe vs indices).
_DOMAIN_PREFIX = {
    "universe": "upstox/universe",
    "indices": "upstox/indices",
    "universe_intraday": "upstox/universe_intraday",
}

# The 'universe_intraday' ledger domain also covers NSE indices (Nifty 50, ...). Their
# Parquet lives in its own folder; stocks keep upstox/universe_intraday/. Routed by the
# instrument_key's segment (not a new domain) so the refresh -- which only knows the
# domain -- lands in the same folder as the backfill.
_INDEX_INTRADAY_PREFIX = "upstox/nse_indexes_intraday"

# Canonical Parquet column order.
_COLUMNS = ["timeframe", "ts", "trade_date", "open", "high", "low", "close",
            "volume", "open_interest"]

# Minimum gap (minutes) since last_success_at before update_instrument() will even
# attempt a fetch, PER DOMAIN -- not one global number. NOT a "same calendar day"
# rule (that was tried and rejected -- it would block a legitimate later-in-day
# attempt just because an earlier run that same day already succeeded, e.g.
# pre-market then post-close). Domain-aware because D/W/M's finest granularity is
# a full day (cooldown can be generous) while universe_intraday's finest bar is
# 5 minutes (a 15-minute cooldown there would be needlessly conservative for
# someone actively trading intraday options and wanting fresher checks).
#
# Both values are genuine unknown-tuned-by-testing numbers, same posture as
# MAX_WORKERS: Upstox's actual candle-publish cadence after a bar closes isn't
# documented for either granularity. 15 (D/W/M) is confirmed to stop an
# accidental back-to-back re-run within minutes (2026-09-06: two universe runs
# 4 min apart triggered sustained Cloudflare rate limiting). 5 (intraday) matches
# the finest bar's own period as the logical minimum -- confirmed the OPPOSITE
# failure mode live (2026-09-06: two intraday runs 44 SECONDS apart, guaranteed
# empty since no 5-min bar could possibly exist yet) but has NOT itself been
# tested for whether Upstox has any publish lag beyond the bar's own close.
# Adjust either based on observed behavior, not assumed correct.
_COOLDOWN_MINUTES_BY_DOMAIN = {
    "universe_intraday": 5,
}
_DEFAULT_COOLDOWN_MINUTES = 15  # universe, indices, and any future D/W/M-only domain


def _cooldown_minutes_for(domain: str) -> int:
    return _COOLDOWN_MINUTES_BY_DOMAIN.get(domain, _DEFAULT_COOLDOWN_MINUTES)

# Naive IST "now", matching ohlcv_fetch_progress._now_ist_iso()'s exact convention
# (last_success_at is stored as a naive IST string) -- comparing against a
# different timezone/offset would silently miscompute elapsed_minutes.
_IST = timezone(timedelta(hours=5, minutes=30))


def _now_ist() -> datetime:
    return datetime.now(_IST).replace(tzinfo=None)


@dataclass
class StoreResult:
    """Outcome of a store write. `ok` is the single flag. bytes_written + key give
    the cost/traceability info logged on every write. `changed` distinguishes an
    actual R2 write from a check that found nothing new (update_instrument only;
    always True for backfill_instrument, which always writes). `skipped` marks a
    cooldown skip — no fetch attempted at all (see COOLDOWN_MINUTES), distinct
    from `changed=False` which means a fetch WAS made and genuinely found nothing
    new."""
    ok: bool
    instrument_key: str
    key: Optional[str] = None
    rows: int = 0
    bytes_written: int = 0
    error: Optional[str] = None
    changed: bool = True
    skipped: bool = False


# --- Key derivation --------------------------------------------------------

def _object_key(instrument_key: str, domain: str) -> str:
    """
    Build the R2 object key from the instrument_key + domain.
      'NSE_EQ|INE002A01018'  + universe -> 'upstox/universe/INE002A01018.parquet'
      'NSE_INDEX|Nifty 50'   + indices  -> 'upstox/indices/Nifty_50.parquet'
      'NSE_INDEX|Nifty 50'   + universe_intraday
                                        -> 'upstox/nse_indexes_intraday/Nifty_50.parquet'
    The suffix after '|' is the ISIN (stocks) or index name (indices); spaces are
    slugified to underscores to keep keys path/URL-safe.
    """
    if domain not in _DOMAIN_PREFIX:
        raise ValueError(f"Unknown domain '{domain}'. Valid: {sorted(_DOMAIN_PREFIX)}")
    if "|" not in instrument_key:
        raise ValueError(f"instrument_key '{instrument_key}' has no '|' segment")
    suffix = instrument_key.split("|", 1)[1].strip().replace(" ", "_")
    prefix = _DOMAIN_PREFIX[domain]
    if domain == "universe_intraday" and instrument_key.startswith("NSE_INDEX|"):
        prefix = _INDEX_INTRADAY_PREFIX
    return f"{prefix}/{suffix}.parquet"


# --- DataFrame <-> candles -------------------------------------------------

def _results_to_df(results: dict[str, OhlcvFetchResult]) -> pd.DataFrame:
    """Flatten {label: OhlcvFetchResult} into one tidy DataFrame with a timeframe col."""
    frames = []
    for label, res in results.items():
        if not res.ok:
            logger.warning("Timeframe %s not ok, skipping: %s", label, res.error)
            continue
        frames.append(pd.DataFrame([{
            "timeframe": label,
            "ts": c.ts,
            "trade_date": c.trade_date,
            "open": c.open, "high": c.high, "low": c.low, "close": c.close,
            "volume": c.volume, "open_interest": c.open_interest,
        } for c in res.candles]))
    if not frames:
        return pd.DataFrame(columns=_COLUMNS)
    df = pd.concat(frames, ignore_index=True)
    return df[_COLUMNS].sort_values(["timeframe", "ts"]).reset_index(drop=True)


# --- Atomic write core -----------------------------------------------------

def _write_df(instrument_key: str, domain: str, df: pd.DataFrame) -> StoreResult:
    """
    Serialise df to Parquet IN MEMORY and atomically put_object to R2. This is the
    single write path all callers funnel through. Never called with empty df (callers
    guard), so a write here always means we have real data in hand.
    """
    key = _object_key(instrument_key, domain)
    buf = io.BytesIO()
    df.to_parquet(buf, engine="pyarrow", compression="snappy", index=False)
    payload = buf.getvalue()

    client = get_r2()
    bucket = get_r2_settings().bucket
    try:
        client.put_object(Bucket=bucket, Key=key, Body=payload,
                          ContentType="application/octet-stream")
    except ClientError as exc:
        logger.error("R2 write failed for %s (%s): %s", instrument_key, key, exc)
        return StoreResult(ok=False, instrument_key=instrument_key, key=key,
                           error=f"R2 write failed: {exc}")

    size = len(payload)
    # Cost-visibility log: bytes written + key, every write.
    logger.info("Wrote %s: %d rows, %s (%.1f KB) to R2.",
                instrument_key, len(df), key, size / 1024)
    return StoreResult(ok=True, instrument_key=instrument_key, key=key,
                       rows=len(df), bytes_written=size)


# --- Read ------------------------------------------------------------------

def read_candles(
    instrument_key: str,
    domain: str,
    timeframe: Optional[str] = None,
) -> Optional[pd.DataFrame]:
    """
    Read an instrument's Parquet back from R2 into a DataFrame. Optionally filter to
    one timeframe ('1d'/'1w'/'1mo'). Returns None if the object doesn't exist yet
    (not an error -- the instrument simply hasn't been backfilled).

    NOTE: this is the store's own reader for merge/verify. The broad downstream read
    accessor for backtesting/research (read_ohlcv.py) comes later and may read via
    DuckDB directly; this method is deliberately simple.
    """
    key = _object_key(instrument_key, domain)
    client = get_r2()
    bucket = get_r2_settings().bucket
    try:
        obj = client.get_object(Bucket=bucket, Key=key)
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        if code in ("NoSuchKey", "404"):
            return None
        raise
    df = pd.read_parquet(io.BytesIO(obj["Body"].read()), engine="pyarrow")
    if timeframe is not None:
        df = df[df["timeframe"] == timeframe].reset_index(drop=True)
    return df


# --- Write paths -----------------------------------------------------------

def backfill_instrument(
    instrument_key: str,
    domain: str,
    timeframes: tuple[tuple[str, str], ...] = TIER1_TIMEFRAMES,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
) -> StoreResult:
    """
    First-time / full-history load: fetch all timeframes' full history, then write.
    FETCH-FIRST: if the fetch yields no data, we do NOT touch R2 (any existing file
    stays intact). Creates (or atomically replaces) the instrument's Parquet.
    """
    results = fetch_all_timeframes(instrument_key, timeframes=timeframes,
                                   from_date=from_date, to_date=to_date)
    df = _results_to_df(results)
    if df.empty:
        return StoreResult(ok=False, instrument_key=instrument_key,
                           error="fetch returned no candles; R2 left untouched")
    return _write_df(instrument_key, domain, df)


def update_instrument(
    instrument_key: str,
    domain: str,
    last_success_at: Optional[str] = None,
    timeframes: tuple[tuple[str, str], ...] = TIER1_TIMEFRAMES,
) -> StoreResult:
    """
    Routine incremental update: fetch from the ledger's last_success_at through
    today for the GIVEN timeframes, merge into the existing Parquet (dedup on
    timeframe+ts, keep newest), write the merged superset back.

    COOLDOWN (added 2026-09-06, made domain-aware same day): if last_success_at is
    less than this domain's cooldown (see _COOLDOWN_MINUTES_BY_DOMAIN) old, returns
    immediately with skipped=True and makes NO API call at all. This is
    deliberately NOT a same-calendar-day check — that was tried and rejected,
    since it would permanently block a legitimate later-in-day attempt (e.g. a
    pre-market run followed by a post-close run, both on the same day, both
    wanting genuinely fresh data) just because an earlier run that day already
    succeeded. A short elapsed-time cooldown instead only blocks a re-run that
    happens shortly after the last one — confirmed live on two different failure
    shapes: universe D/W/M (15min cooldown) stops a same-day re-run minutes apart
    from triggering sustained Cloudflare rate limiting; universe_intraday (5min
    cooldown, matching its finest 5-minute bar) stops a re-run SECONDS apart from
    guaranteed-empty fetches (no new 5-min bar could possibly exist yet).

    WINDOW (once past cooldown) = last_success_at -> today, no fixed per-unit
    sizing and no buffer. last_success_at only ever advances on a genuine
    successful fetch (a miss leaves it untouched — see the refresh runner's
    failure handling), so this window is exactly "everything since we last
    confirmed complete," whatever that gap actually is — a missed day or a missed
    month both self-heal correctly, unlike a fixed window which only self-heals
    gaps smaller than itself. last_success_at is supplied by the caller (read
    from the ledger via get_done()); if not provided (shouldn't happen in
    practice — mark_done always sets it together with status='done'), the
    cooldown check is skipped entirely and the window falls back to today-only
    as the safe minimum rather than guessing.

    CADENCE IS STILL THE CALLER'S JOB for WHICH timeframes to refresh on a given
    run (unchanged) — this function still doesn't hardcode "all three every
    run"; that's a separate decision from how far back to look.

    If no existing file, behaves like a windowed create. FETCH-FIRST: a failed
    fetch leaves the existing file untouched (never delete-first).
    """
    if last_success_at is not None:
        cooldown = _cooldown_minutes_for(domain)
        last_dt = datetime.fromisoformat(last_success_at)
        elapsed_minutes = (_now_ist() - last_dt).total_seconds() / 60
        if elapsed_minutes < cooldown:
            logger.info("Cooldown skip for %s (%s): last checked %.1f min ago (< %d min).",
                       instrument_key, domain, elapsed_minutes, cooldown)
            return StoreResult(ok=True, instrument_key=instrument_key,
                               changed=False, skipped=True)

    to_d = date.today()
    from_d = date.fromisoformat(last_success_at[:10]) if last_success_at else to_d
    label_map = {("days", "1"): "1d", ("weeks", "1"): "1w", ("months", "1"): "1mo",
                ("minutes", "5"): "5m", ("minutes", "15"): "15m", ("minutes", "60"): "60m"}

    fresh: dict[str, OhlcvFetchResult] = {}
    for unit, interval in timeframes:
        label = label_map.get((unit, interval), f"{unit}{interval}")
        fresh[label] = fetch_full_history(instrument_key, unit, interval,
                                          from_date=from_d, to_date=to_d)
    fresh_df = _results_to_df(fresh)
    if fresh_df.empty:
        return StoreResult(ok=False, instrument_key=instrument_key,
                           error="recent fetch returned no candles; R2 left untouched")

    existing = read_candles(instrument_key, domain)
    if existing is not None and not existing.empty:
        combined = pd.concat([existing, fresh_df], ignore_index=True)
        # dedup: same timeframe + timestamp -> keep last (freshest). Timeframes NOT in
        # this fetch are untouched (their rows exist only in `existing` and pass through).
        combined = (combined
                    .drop_duplicates(subset=["timeframe", "ts"], keep="last")
                    .sort_values(["timeframe", "ts"])
                    .reset_index(drop=True))

        # No-op check: closed/settled candles refetched inside the recent window come
        # back byte-identical, and rewriting unchanged data to R2 wastes a PUT for
        # nothing gained. Only the still-forming bar (today's/this week's/this
        # month's) or a genuine gap-fill actually changes `combined` vs `existing`.
        existing_sorted = existing.sort_values(["timeframe", "ts"]).reset_index(drop=True)
        if combined.equals(existing_sorted):
            logger.info("No change for %s; R2 write skipped (%d rows unchanged).",
                       instrument_key, len(combined))
            return StoreResult(ok=True, instrument_key=instrument_key,
                               key=_object_key(instrument_key, domain),
                               rows=len(combined), bytes_written=0, changed=False)
    else:
        combined = fresh_df

    return _write_df(instrument_key, domain, combined)


# --- Increment 2.3 manual spike: one instrument end-to-end to R2 -----------

if __name__ == "__main__":
    #   python -m modules.market_data.upstox.ohlcv_store
    # Nifty 50 full history -> Parquet -> R2 -> read back -> verify round-trip.
    from dotenv import load_dotenv

    load_dotenv()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    test_key = "NSE_INDEX|Nifty 50"
    domain = "indices"

    print("\n" + "=" * 64)
    print("OHLCV STORE — INCREMENT 2.3 (one instrument end-to-end to R2)")
    print("=" * 64)
    print(f"Instrument : {test_key}  (domain={domain})")

    # 1. Backfill (fetch full history -> write to R2)
    print("\n[1] Backfilling full history to R2 ...")
    res = backfill_instrument(test_key, domain)
    if not res.ok:
        print(f"FAIL -- {res.error}")
        raise SystemExit(1)
    print(f"    OK  key={res.key}")
    print(f"        {res.rows:,} rows, {res.bytes_written/1024:.1f} KB written")

    # 2. Read back + verify
    print("\n[2] Reading back from R2 to verify ...")
    df = read_candles(test_key, domain)
    if df is None or df.empty:
        print("FAIL -- read back empty")
        raise SystemExit(1)
    print(f"    OK  read {len(df):,} rows")
    print(f"        timeframes: {df['timeframe'].value_counts().to_dict()}")
    for tf in df["timeframe"].unique():
        sub = df[df.timeframe == tf]
        print(f"        {tf:<4} {len(sub):>5,} rows  "
              f"{sub['trade_date'].min()} .. {sub['trade_date'].max()}  "
              f"last close={sub.iloc[-1]['close']:.2f}")

    match = "OK" if len(df) == res.rows else f"MISMATCH (wrote {res.rows}, read {len(df)})"
    print(f"\n    round-trip row count: {match}")
    print("=" * 64 + "\n")
