"""
Archive every expired Nifty 50 contract Upstox still serves (rolling ~2 years) in R2.
Three parts, each one Parquet per expiry, each resumable:

  band     options, 1m:  every CE/PE from (window Nifty low - 9 strikes) to (high + 9 strikes)
           upstox/nifty_options_expired/1m/<expiry>.parquet
  futures  Nifty futures, 1m, monthly expiries (each month: tries its listed expiries from the
           last one back until Upstox lists a futures contract -- a holiday-shifted weekly can be
           the month's last expiry, e.g. 30 Apr 2025 while the monthly was 24 Apr)
           upstox/nifty_futures_expired/1m/<expiry>.parquet
  rest     options, 30m:  every other strike of the chain (OI / PCR / max pain)
           upstox/nifty_options_expired/rest_30m/<expiry>.parquet

Window per weekly option expiry: from 7 days before the expiry week starts (so the contract
is also stored as "next week" during the previous week) to expiry. The expiry week itself
starts the day after the previous listed expiry. Futures: from 7 days before the previous
monthly expiry to expiry (covers rollover), fetched in chunks of <= 28 days.

1m is the base: a check on 9 contracts (3 weeks, ATM and far OTM) showed 5m built from 1m
matches Upstox's own 5m exactly (OHLC, volume, OI). Build 5m/15m/60m from it.
Rules applied to every candle: drop bars starting at/after the F&O close on days with regular
bars (reader rule 2; close = 15:30, 15:40 from 3 Aug 2026 when NSE extended F&O trading) and
bars with a non-positive price (reader rule 1). Weeks stored before this rule have no
15:30-15:40 bars from Aug 2026 on -- known gap, after Ash's 15:10 auto square-off.

--force with --expiry still takes the previous month's futures expiry from R2, so a refetched
month keeps the same window as the others (fixed 2026-10-30; before, it started a week early).

Pacing: starts at --gap seconds between calls (default 0.13 s, under Upstox's 500/min);
on the first rate-limit error it switches to SAFE_GAP (0.95 s, under 2,000 per 30 min),
waits and retries. A week is written only when every contract in it was fetched; weeks
already in R2 are skipped, so stop and rerun at any time (--force refetches). A week where
Upstox returns no candles at all fails (nothing written); files smaller than MIN_STORED_BYTES
(empty weeks from an earlier version) count as not stored and are fetched again.

Refresh: the same command fetches new weeks. Upstox's expiry list grows after each expiry;
stored weeks are skipped, so a rerun after Tuesday's expiry adds only that week (and the
month's futures after the monthly expiry). Update Nifty intraday data first: a week whose
expiry is past the last Nifty 5m day fails (its strike band would be incomplete).
  python -m modules.market_data.upstox.fetch_expired_nifty_options --parts band,futures,rest

Run from backend/ (verify first with --limit):
  python -m modules.market_data.upstox.fetch_expired_nifty_options --limit 2
  python -m modules.market_data.upstox.fetch_expired_nifty_options            # band + futures
  python -m modules.market_data.upstox.fetch_expired_nifty_options --parts rest   # pass 2
  ... --expiry 2025-10-14   ... --force   ... --gap 0.95
Logs: logs/expired_options_fetch_logs/fetch_run.log (+ screen) and fetch_summary.log
"""

from __future__ import annotations

import argparse
import io
import logging
import math
import sys
import time
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urlencode

import pandas as pd

from db.r2_client import get_r2, get_r2_settings
from modules.market_data.upstox.indicator_ohlcv_reader import read_for_indicators
from modules.market_data.upstox.probe_expired_contracts import (
    ProbeError,
    _get,
    get_candles,
    get_contracts,
    get_expiries,
)

NIFTY_KEY = "NSE_INDEX|Nifty 50"
STRIKE_STEP = 50
STRIKES_EACH_SIDE = 9
FIRST_WEEK_BACK_DAYS = 7
PREVIOUS_WEEK_DAYS = 7                 # also store each contract during the week before
FUTURES_OVERLAP_DAYS = 7               # futures window starts this many days before previous expiry
MAX_CHUNK_DAYS = 28                    # Upstox: keep minute ranges within ~1 month per call
FAST_GAP = 0.13                        # ~460 calls/min, under 500/min
SAFE_GAP = 0.95                        # under 2,000 calls / 30 min
RATE_WAIT_SECONDS = 60
RATE_RETRIES = 40                      # up to ~40 min of waiting for the window to free up
RATE_MARKERS = ("429", "udapi10005", "too many", "rate limit")
MIN_STORED_BYTES = 15_000              # a 0-row Parquet is ~10 KB -> fetch again

PARTS = {
    "band":    {"interval": "1minute",  "prefix": "upstox/nifty_options_expired/1m"},
    "futures": {"interval": "1minute",  "prefix": "upstox/nifty_futures_expired/1m"},
    "rest":    {"interval": "30minute", "prefix": "upstox/nifty_options_expired/rest_30m"},
}
LOG_DIR = Path("logs") / "expired_options_fetch_logs"
IST = "Asia/Kolkata"
SESSION_CLOSE_MINUTE = 15 * 60 + 30     # F&O close up to 31 Jul 2026
FNO_CLOSE_1540_FROM = date(2026, 8, 3)  # NSE extended equity derivatives trading to 15:40


def fno_close_minute(d: date) -> int:
    """F&O close as minutes after midnight: 15:30, or 15:40 from 3 Aug 2026."""
    return 15 * 60 + 40 if d >= FNO_CLOSE_1540_FROM else SESSION_CLOSE_MINUTE


def after_close(ts: pd.Series) -> pd.Series:
    """True for F&O bars at/after that day's close: 15:30, or 15:40 from 3 Aug 2026."""
    minute = ts.dt.hour * 60 + ts.dt.minute
    close = ts.dt.date.map(fno_close_minute)
    return minute >= close.astype(int)

COLUMNS = ["expiry", "week_start", "window_start", "instrument_key", "trading_symbol", "strike",
           "option_type", "lot_size", "freeze_quantity", "ts", "trade_date", "open", "high", "low",
           "close", "volume", "oi"]

logger = logging.getLogger(__name__)
_gap = FAST_GAP
_last_call = 0.0


# ----------------------------------------------------------------------------- pacing
def _is_rate_limit(exc: Exception) -> bool:
    text = str(exc).lower()
    return any(m in text for m in RATE_MARKERS)


def _paced(fn, *args):
    """Call with the current gap; on a rate-limit error drop to SAFE_GAP, wait and retry."""
    global _gap, _last_call
    for attempt in range(1, RATE_RETRIES + 1):
        wait = _gap - (time.monotonic() - _last_call)
        if wait > 0:
            time.sleep(wait)
        try:
            return fn(*args)
        except ProbeError as exc:
            if not _is_rate_limit(exc):
                raise
            if attempt == 1:
                logger.warning("Upstox limit reached (2,000 calls per 30 min for the account, counted from the "
                               "window's first call -- earlier runs count too). Waiting for it to reset -- can take up to 30 min. LEAVE IT RUNNING; "
                               "stopping and restarting starts a new 30-min wait.")
            if _gap < SAFE_GAP:
                logger.warning("Switching to the safe pace (%.2fs per call)", SAFE_GAP)
                _gap = SAFE_GAP
            logger.warning("Still limited, checking again in %ds (%d/%d)", RATE_WAIT_SECONDS, attempt, RATE_RETRIES)
            time.sleep(RATE_WAIT_SECONDS)
        finally:
            _last_call = time.monotonic()
    raise ProbeError(f"still rate limited after {RATE_RETRIES} waits")


# ----------------------------------------------------------------------------- pure helpers
def week_windows(expiries: list[date]) -> list[tuple[date, date]]:
    """(week_start, expiry) per expiry: day after the previous expiry, first one 7 days back."""
    out, prev = [], None
    for e in sorted(expiries):
        start = (prev + timedelta(days=1)) if prev else e - timedelta(days=FIRST_WEEK_BACK_DAYS)
        out.append((start, e))
        prev = e
    return out


def month_candidates(expiries: list[date]) -> list[tuple[tuple[int, int], list[date]]]:
    """Per calendar month: its listed expiries, last first (the monthly is usually the last)."""
    by: dict = {}
    for e in sorted(expiries):
        by.setdefault((e.year, e.month), []).append(e)
    return [(ym, sorted(v, reverse=True)) for ym, v in sorted(by.items())]


def chunks(start: date, end: date, max_days: int = MAX_CHUNK_DAYS) -> list[tuple[date, date]]:
    out, s = [], start
    while s <= end:
        e = min(end, s + timedelta(days=max_days - 1))
        out.append((s, e))
        s = e + timedelta(days=1)
    return out


def strike_band(low: float, high: float) -> tuple[float, float]:
    lo = math.floor(low / STRIKE_STEP) * STRIKE_STEP - STRIKES_EACH_SIDE * STRIKE_STEP
    hi = math.ceil(high / STRIKE_STEP) * STRIKE_STEP + STRIKES_EACH_SIDE * STRIKE_STEP
    return float(lo), float(hi)


def drop_after_close(df: pd.DataFrame) -> pd.DataFrame:
    """Reader rule 2 at market level: on a trading day where ANY contract has a bar before the
    close (15:30; 15:40 from 3 Aug 2026), drop every bar after it. Days with only evening bars
    (Muhurat) are kept."""
    if df.empty:
        return df
    ts = pd.to_datetime(df["ts"])
    after = after_close(ts)
    day = ts.dt.date
    regular_days = set(day[~after])
    return df[~(after & day.isin(regular_days))].reset_index(drop=True)


def candles_frame(candles: list[list], contract: dict, expiry: date, week_start: date,
                  window_start: date | None = None) -> pd.DataFrame:
    """Upstox candle rows [ts, o, h, l, c, volume, oi] -> COLUMNS, reader rules 1 and 2 applied."""
    if not candles:
        return pd.DataFrame(columns=COLUMNS)
    df = pd.DataFrame([list(r)[:7] + [None] * (7 - len(r)) for r in candles],
                      columns=["ts", "open", "high", "low", "close", "volume", "oi"])
    df["ts"] = pd.to_datetime(df["ts"], utc=True).dt.tz_convert(IST)
    df = df.sort_values("ts").drop_duplicates("ts")
    df = df[(df[["open", "high", "low", "close"]] > 0).all(axis=1)]          # rule 1
    after = after_close(df["ts"])
    day = df["ts"].dt.date
    df = df[~(after & (~after).groupby(day).transform("any"))]                 # rule 2
    df["trade_date"] = df["ts"].dt.date
    df["expiry"], df["week_start"] = expiry, week_start
    df["window_start"] = window_start or week_start
    df["instrument_key"] = contract.get("instrument_key")
    df["trading_symbol"] = contract.get("trading_symbol")
    df["strike"] = float(contract.get("strike_price") or 0)
    df["option_type"] = contract.get("instrument_type")
    df["lot_size"] = contract.get("lot_size")
    df["freeze_quantity"] = contract.get("freeze_quantity")
    return df[COLUMNS].reset_index(drop=True)


# ----------------------------------------------------------------------------- Upstox
def get_future_contracts(expiry: date) -> list[dict]:
    q = urlencode({"instrument_key": NIFTY_KEY, "expiry_date": expiry.isoformat()})
    return list(_get("/expired-instruments/future/contract?" + q) or [])


def fetch_contract(contract: dict, interval: str, start: date, end: date) -> list[list]:
    rows = []
    for s, e in chunks(start, end):
        rows += _paced(get_candles, contract["instrument_key"], interval, e, s)
    return rows


# ----------------------------------------------------------------------------- R2
class Store:
    def __init__(self):
        self._r2 = get_r2()
        self._bucket = get_r2_settings().bucket

    @staticmethod
    def key(part: str, expiry: date) -> str:
        return f"{PARTS[part]['prefix']}/{expiry.isoformat()}.parquet"

    def stored(self, part: str) -> set[str]:
        keys, token = set(), None
        while True:
            kw = {"Bucket": self._bucket, "Prefix": PARTS[part]["prefix"] + "/"}
            if token:
                kw["ContinuationToken"] = token
            resp = self._r2.list_objects_v2(**kw)
            keys |= {o["Key"] for o in resp.get("Contents", []) if o.get("Size", 0) >= MIN_STORED_BYTES}
            if not resp.get("IsTruncated"):
                return keys
            token = resp.get("NextContinuationToken")

    def write(self, part: str, expiry: date, df: pd.DataFrame) -> int:
        buf = io.BytesIO()
        df.to_parquet(buf, engine="pyarrow", index=False)
        body = buf.getvalue()
        self._r2.put_object(Bucket=self._bucket, Key=self.key(part, expiry), Body=body)
        return len(body)


# ----------------------------------------------------------------------------- one expiry
@dataclass
class Result:
    part: str
    expiry: date
    status: str                          # written / skipped / pending / failed
    contracts: int = 0
    rows: int = 0
    bytes: int = 0
    strikes: tuple = ()
    errors: list = field(default_factory=list)


def _collect(part, expiry, chosen, interval, start, week_start, res) -> pd.DataFrame | None:
    frames = []
    for c in chosen:
        try:
            frames.append(candles_frame(fetch_contract(c, interval, start, expiry), c, expiry, week_start, start))
        except ProbeError as exc:
            res.errors.append(f"{c.get('trading_symbol')}: {exc}")
    if res.errors or not frames:
        res.errors = res.errors or ["no contracts selected"]
        return None
    df = drop_after_close(pd.concat(frames, ignore_index=True))
    if df.empty:
        res.errors = ["Upstox returned no candles for any contract"]
        return None
    res.status, res.rows = "written", len(df)
    return df


def fetch_options_week(part: str, week_start: date, expiry: date, nifty5: pd.DataFrame):
    start = week_start - timedelta(days=PREVIOUS_WEEK_DAYS)
    wk = nifty5[(nifty5["trade_date"] >= start) & (nifty5["trade_date"] <= expiry)]
    if wk.empty:
        return None, Result(part, expiry, "failed", errors=["no Nifty 5m bars for this window"])
    nifty_last = nifty5["trade_date"].max()
    if nifty_last < expiry:
        # the strike band comes from the window's Nifty low/high: with days missing it can miss strikes
        return None, Result(part, expiry, "failed",
                            errors=[f"Nifty 5m data ends {nifty_last}, before this expiry -- "
                                    "update Nifty intraday data first, then rerun"])
    lo, hi = strike_band(float(wk["low"].min()), float(wk["high"].max()))
    try:
        contracts = _paced(get_contracts, expiry)
    except ProbeError as exc:
        return None, Result(part, expiry, "failed", strikes=(lo, hi), errors=[f"contracts: {exc}"])
    opts = [c for c in contracts if c.get("instrument_type") in ("CE", "PE")]
    inside = lambda c: lo <= float(c.get("strike_price") or 0) <= hi          # noqa: E731
    chosen = [c for c in opts if inside(c)] if part == "band" else [c for c in opts if not inside(c)]
    res = Result(part, expiry, "failed", contracts=len(chosen), strikes=(lo, hi))
    if not chosen:
        res.errors = ["no contracts selected"]
        return None, res
    return _collect(part, expiry, chosen, PARTS[part]["interval"], start, week_start, res), res


def fetch_futures_month(expiry: date, prev_monthly: date | None, contracts: list[dict]):
    start = (prev_monthly or expiry - timedelta(days=35)) - timedelta(days=FUTURES_OVERLAP_DAYS)
    res = Result("futures", expiry, "failed", contracts=len(contracts))
    return _collect("futures", expiry, contracts, PARTS["futures"]["interval"], start, start, res), res


def run_futures(store: "Store", expiries: list[date], limit: int | None, only: date | None,
                force: bool) -> list[Result]:
    on_r2 = store.stored("futures")        # also with --force: the previous month's expiry sets the window start
    months = month_candidates(expiries)
    results, prev, fetched = [], None, 0
    logger.info("[futures] %d months", len(months))
    today = date.today()
    for (y, m), cands in months:
        in_r2 = next((e for e in cands if Store.key("futures", e) in on_r2), None)
        stored = None if force else in_r2
        if only is not None and only not in cands:
            prev = in_r2 or prev
            continue
        if stored:
            results.append(Result("futures", stored, "skipped"))
            prev = stored
            continue
        if limit and fetched >= limit:
            continue
        fetched += 1
        t0, expiry, contracts, errs = time.monotonic(), None, [], []
        for e in cands:
            try:
                contracts = _paced(get_future_contracts, e)
            except ProbeError as exc:
                errs.append(f"{e}: {exc}")
                continue
            if contracts:
                expiry = e
                break
        if expiry is None:
            if (y, m) >= (today.year, today.month):
                res = Result("futures", cands[0], "pending",
                             errors=["this month's futures has not expired yet"])
            else:
                res = Result("futures", cands[0], "failed",
                             errors=errs or [f"no futures contract on any listed expiry {[str(c) for c in cands]}"])
            results.append(res)
            logger.info("[futures] %d-%02d %s: %s", y, m, res.status.upper(), res.errors[0])
            continue
        df, res = fetch_futures_month(expiry, prev, contracts)
        if df is not None:
            res.bytes = store.write("futures", expiry, df)
            prev = expiry
        else:
            prev = in_r2 or prev
        results.append(res)
        logger.info("[futures] %s %s: %d rows, %.2f MB, %.0fs%s", expiry, res.status.upper(), res.rows,
                    res.bytes / 1e6, time.monotonic() - t0, f" -- {res.errors[0]}" if res.errors else "")
    return results


# ----------------------------------------------------------------------------- run
def run(parts: list[str], limit: int | None, only: date | None, force: bool) -> list[Result]:
    n5 = read_for_indicators(NIFTY_KEY, "universe_intraday", "5m")
    if not n5.ok:
        raise RuntimeError(f"Nifty 5m read failed: {n5.error}")
    nifty5 = n5.df.copy()
    nifty5["trade_date"] = pd.to_datetime(nifty5["trade_date"]).dt.date

    store = Store()
    expiries = _paced(get_expiries)
    logger.info("Expiries listed %d (%s .. %s); parts %s; start gap %.2fs",
                len(expiries), expiries[0] if expiries else "-", expiries[-1] if expiries else "-",
                ",".join(parts), _gap)
    results = []
    for part in parts:
        if part == "futures":
            results += run_futures(store, expiries, limit, only, force)
            continue
        have = set() if force else store.stored(part)
        jobs = [j for j in week_windows(expiries) if only is None or j[1] == only]
        exp_of = lambda j: j[1]                                                # noqa: E731
        todo = [j for j in jobs if Store.key(part, exp_of(j)) not in have]
        results += [Result(part, exp_of(j), "skipped") for j in jobs if Store.key(part, exp_of(j)) in have]
        already = len(jobs) - len(todo)
        todo = todo[:limit] if limit else todo
        logger.info("[%s] %d expiries, %d already in R2, fetching %d", part, len(jobs), already, len(todo))
        for k, job in enumerate(todo, 1):
            t0 = time.monotonic()
            df, res = fetch_options_week(part, job[0], job[1], nifty5)
            if df is not None:
                res.bytes = store.write(part, res.expiry, df)
            results.append(res)
            logger.info("[%s %d/%d] %s %s: %d contracts, %d rows, %.2f MB%s, %.0fs%s", part, k, len(todo),
                        res.expiry, res.status.upper(), res.contracts, res.rows, res.bytes / 1e6,
                        f", strikes {res.strikes}" if res.strikes else "", time.monotonic() - t0,
                        f" -- {len(res.errors)} error(s): {res.errors[0]}" if res.errors else "")
    return results


def summary(results: list[Result]) -> list[str]:
    lines = ["=" * 78, "EXPIRED NIFTY CONTRACTS FETCH -- summary", "=" * 78]
    for part in PARTS:
        rs = [r for r in results if r.part == part]
        if not rs:
            continue
        by = {s: [r for r in rs if r.status == s] for s in ("written", "skipped", "pending", "failed")}
        lines += [f"{part} ({PARTS[part]['interval']}, {PARTS[part]['prefix']}/)",
                  f"   written : {len(by['written'])} expiries, {sum(r.contracts for r in by['written'])} contracts, "
                  f"{sum(r.rows for r in by['written']):,} rows, {sum(r.bytes for r in by['written']) / 1e6:.2f} MB",
                  f"   skipped : {len(by['skipped'])} already in R2",
                  f"   pending : {len(by['pending'])} not expired yet" + (f" ({by['pending'][0].expiry:%b %Y})" if by['pending'] else ""),
                  f"   failed  : {len(by['failed'])} (rerun to retry; nothing written for them)"]
        for r in by["failed"]:
            lines.append(f"      {r.expiry}: {len(r.errors)} error(s); first: {r.errors[0] if r.errors else '?'}")
    lines.append(f"pace at end: {_gap:.2f}s per call")
    return lines


def main(argv=None) -> int:
    global _gap
    ap = argparse.ArgumentParser(description="Archive expired Nifty option and futures contracts to R2")
    ap.add_argument("--parts", default="band,futures", help="comma list of band, futures, rest (default band,futures)")
    ap.add_argument("--limit", type=int, help="fetch at most N expiries per part (verify first)")
    ap.add_argument("--expiry", type=lambda v: date.fromisoformat(v), help="one expiry only")
    ap.add_argument("--force", action="store_true", help="refetch expiries already in R2")
    ap.add_argument("--gap", type=float, default=FAST_GAP, help=f"seconds between calls at start (default {FAST_GAP})")
    args = ap.parse_args(argv)
    parts = [p.strip() for p in args.parts.split(",") if p.strip()]
    bad = [p for p in parts if p not in PARTS]
    if bad:
        ap.error(f"unknown part(s) {bad}; use {list(PARTS)}")
    _gap = args.gap
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s",
                        handlers=[logging.StreamHandler(sys.stdout),
                                  logging.FileHandler(LOG_DIR / "fetch_run.log", mode="a", encoding="utf-8")])
    results: list[Result] = []
    try:
        results = run(parts, args.limit, args.expiry, args.force)
    except KeyboardInterrupt:
        logger.warning("Stopped by user; expiries already written are kept, rerun to continue.")
        return 130
    except Exception:
        logger.exception("Fetch failed")
        return 1
    text = "\n".join(summary(results))
    (LOG_DIR / "fetch_summary.log").write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
