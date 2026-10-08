"""
modules/market_data/upstox/audit_ohlcv_data.py

READ-ONLY data audit for every OHLCV Parquet in R2 plus the f_ohlcv_fetch_progress
ledger. Writes NOTHING to R2 or Supabase -- it only lists objects, reads Parquet and
reads ledger/catalogue rows. Output is a plain-language summary (terminal +
logs/data_audit_summary.txt) and a findings CSV (logs/data_audit_findings_<ts>.csv).

What it audits (the 4 pipelines):
  indices_daily    upstox/indices/               <- refresh_index_ohlcv        (1d/1w/1mo)
  universe_daily   upstox/universe/              <- refresh_universe_ohlcv     (1d/1w/1mo)
  stocks_intraday  upstox/universe_intraday/     <- refresh_universe_options_intraday_ohlcv (5m/15m/60m)
  index_intraday   upstox/nse_indexes_intraday/  <- fetch_nifty50_intraday_ohlcv + the same refresh (5m/15m/60m)

Reference calendar: Nifty 50 daily bars are THE trading calendar for daily checks, and
Nifty 50 5m/15m/60m bars per day are the reference for intraday completeness. This
avoids a hand-made holiday list and handles special sessions automatically.

Severity: ERROR = data is wrong/missing and indicators built on it would be unreliable;
WARN = needs a look, may be legitimate (suspended stock, circuit-limit jump);
INFO = counts for planning (e.g. how many instruments are too young for a 200 EMA).

ASSUMPTIONS to confirm from the first real run (the summary prints a probe for them):
  - weekly/monthly bars carry a trade_date inside their own ISO week / calendar month
  - the daily close is the official NSE close, so it may differ slightly from the last
    5m bar's close (tolerance below)

Outputs: logs/data_audit.log (progress + errors, overwritten each run),
logs/data_audit_summary.txt (overwritten), logs/data_audit_findings_<ts>.csv (new each run).

Usage (from backend/):
    python -m modules.market_data.upstox.audit_ohlcv_data
    python -m modules.market_data.upstox.audit_ohlcv_data --only index_intraday
    python -m modules.market_data.upstox.audit_ohlcv_data --scope all           # every instrument, not just the watchlist
    python -m modules.market_data.upstox.audit_ohlcv_data --limit 20      # quick smoke
"""

from __future__ import annotations

import logging
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# --- Config ----------------------------------------------------------------

MAX_WORKERS = 4                      # same R2/Cloudflare-safe count as the pipelines

NIFTY50_KEY = "NSE_INDEX|Nifty 50"

# set name -> (R2 prefix, expected timeframes, kind). Prefixes mirror ohlcv_store.
SETS = {
    "indices_daily":   ("upstox/indices",              ("1d", "1w", "1mo"), "daily"),
    "universe_daily":  ("upstox/universe",             ("1d", "1w", "1mo"), "daily"),
    "stocks_intraday": ("upstox/universe_intraday",    ("5m", "15m", "60m"), "intraday"),
    "index_intraday":  ("upstox/nse_indexes_intraday", ("5m", "15m", "60m"), "intraday"),
}
# set name -> ohlcv_store domain used to derive the object key
_KEY_DOMAIN = {"indices_daily": "indices", "universe_daily": "universe",
               "stocks_intraday": "universe_intraday", "index_intraday": "universe_intraday"}

EXPECTED_BARS = {"5m": 75, "15m": 25, "60m": 7}      # full NSE session, 09:15-15:30
INTERVAL_MIN = {"5m": 5, "15m": 15, "60m": 60}
SESSION_START_MIN = 9 * 60 + 15
SESSION_END_MIN = 15 * 60 + 30
# Last bar START allowed per timeframe: 5m 15:25, 15m 15:15, 60m 15:15 (the 7th hourly bar
# starts 15:15 and is a 15-minute stub before the 15:30 close).
LAST_START_MIN = {"5m": 15 * 60 + 25, "15m": 15 * 60 + 15, "60m": 15 * 60 + 15}

IST = timezone(timedelta(hours=5, minutes=30))
IST_TZ = "Asia/Kolkata"

STALE_WARN_DAYS = 1                  # >= this many trading days behind -> WARN
STALE_ERROR_DAYS = 5                 # >= this many -> ERROR
GAP_ERROR_DAYS = 5                   # >= this many missing daily bars -> ERROR (else WARN)
BAD_DAY_ERROR_FRAC = 0.03            # intraday: > 3% of days incomplete -> ERROR (else WARN)
JUMP_PCT = 0.25                      # daily close-to-close move flagged (NSE circuit limit is 20%)
RECENT_DAYS = 730                    # daily gaps within this many days of the last bar are "recent"
OLD_RUN_DAYS = 365                   # flat / zero-volume runs older than this are INFO only
SPECIAL_FRAC = 0.5                   # a day with < 50% of the full bar count is a special session
CLOSE_WARN_TOL = 0.02                # intraday-vs-daily close gap above 2% is a WARN (else INFO)
FLAT_OR_ZERO_RUN = 5                 # consecutive zero-volume / flat bars flagged
ROLLUP_HL_TOL = 0.001                # 0.1% on high/low for weekly/monthly vs daily
INTRA_HL_TOL = 0.002                 # 0.2% on high/low for intraday vs daily
INTRA_CLOSE_TOL = 0.005              # 0.5% on close (official close != last 5m close)
LEDGER_STALE_DAYS = 4                # ledger last_success_at older than this -> WARN
SMALL_FILE_FRAC = 0.10               # intraday file < 10% of peer median rows -> INFO
PRICE_EPS = 1e-9

_REQUIRED_COLS = ["timeframe", "ts", "trade_date", "open", "high", "low", "close",
                  "volume", "open_interest"]

CHECK_HELP = {
    "LEDGER_DONE_NO_FILE": "ledger says done but the Parquet is missing from R2",
    "LEDGER_FAILED": "ledger shows a failed instrument",
    "LEDGER_PENDING": "ledger shows an instrument never completed",
    "LEDGER_STALE": "ledger last_success_at is old although the instrument is active (refresh missing it)",
    "LEDGER_STALE_INACTIVE": "same for an inactive/delisted instrument -- informational",
    "LEDGER_FAILED_INACTIVE": "failed ledger row for an inactive instrument -- informational",
    "ORPHAN_FILE": "Parquet in R2 with no matching ledger row",
    "CATALOGUE_NOT_IN_LEDGER": "active catalogue instrument has no ledger row (never backfilled)",
    "FNO_NOT_IN_INTRADAY_LEDGER": "F&O-eligible stock not tracked for intraday",
    "LEDGER_INACTIVE_INSTRUMENT": "ledger/R2 holds an instrument no longer active in the catalogue",
    "NIFTY50_INTRADAY_NOT_DONE": "Nifty 50 intraday is not marked done in the ledger",
    "REFERENCE_MISSING": "reference Nifty 50 file missing -- calendar checks impossible",
    "REFERENCE_DAILY_MISSING": "regular trading days missing from the Nifty 50 DAILY file (found via intraday) -- the daily data of every stock is probably missing them too",
    "REFERENCE_DAILY_MISSING_SPECIAL": "special-session days in Nifty 50 intraday but not daily -- informational",
    "REFERENCE_BEHIND": "Nifty 50 daily data is behind the latest weekday (holiday or missed refresh)",
    "REFERENCE_INTRADAY_BEHIND": "Nifty 50 intraday ends before Nifty 50 daily",
    "EMPTY_FILE": "file has no rows",
    "MISSING_COLUMNS": "file lacks required columns",
    "BAD_TIMESTAMPS": "timestamps could not be parsed",
    "MISSING_TIMEFRAME": "an expected timeframe is absent from the file",
    "UNEXPECTED_TIMEFRAME": "file holds a timeframe it should not",
    "TOO_FEW_ROWS": "a timeframe has fewer than 5 rows",
    "DUPLICATE_BARS": "duplicate (timeframe, ts) rows",
    "NOT_SORTED": "bars are not in ascending time order",
    "NAN_PRICES": "NaN in open/high/low/close",
    "NON_POSITIVE_PRICE": "zero or negative price",
    "OHLC_INVALID": "high/low inconsistent with open/close (high<low, high<open/close, low>open/close)",
    "FUTURE_BAR": "bar timestamped in the future",
    "TODAY_BAR": "today's (partial) bar present -- Upstox should never serve it",
    "TRADE_DATE_MISMATCH": "stored trade_date differs from the timestamp's IST date",
    "STALE": "last bar is behind the reference calendar",
    "STALE_SEVERE": "last bar is 5+ trading days behind (suspended/delisted or refresh failing)",
    "AHEAD_OF_CALENDAR": "last bar is later than Nifty 50's last bar",
    "GAP_DAILY": "recent weekday daily bars missing versus the Nifty 50 calendar (last 2 years)",
    "GAP_DAILY_OLD": "older weekday daily bars missing (history hole, matters for long backtests only)",
    "GAP_WEEKEND": "Saturday/Sunday special sessions that Nifty 50 has but this file lacks",
    "STALE_INACTIVE": "inactive/delisted instrument, data naturally ends -- informational",
    "POST_CLOSE_BARS": "Nifty 50 bars at/after 15:30 -- drop them when reading intraday for indicators",
    "SPECIAL_SESSION_DAYS": "Muhurat/Saturday/Sunday special sessions (short or off-grid) -- expected",
    "INTRADAY_DAILY_HL": "intraday high/low do not match the daily bar's high/low",
    "INTRADAY_DAILY_CLOSE": "last intraday close differs from the official daily close (expected, small)",
    "EXTRA_DAYS": "daily bars on dates Nifty 50 has none",
    "TF_OUT_OF_STEP": "timeframes end on different dates (partial-timeframe failure signature)",
    "OFF_SESSION_BAR": "intraday bars outside 09:15-15:30 or off the bar grid",
    "BARS_EXCEED_REFERENCE": "more intraday bars on a day than the index has",
    "MISSING_INTRADAY_DAYS": "whole days absent versus the Nifty 50 intraday reference",
    "SHORT_INTRADAY_DAYS": "days with fewer bars than the Nifty 50 reference",
    "PARTIAL_DAYS": "regular days with 50-99% of the full bar count (data gaps)",
    "ROLLUP_MISMATCH": "weekly/monthly high/low differ from the daily bars inside the period",
    "ROLLUP_MISSING_PERIOD": "a completed week/month has daily bars but no weekly/monthly bar",
    "INTRADAY_DAILY_MISMATCH": "no daily file to cross-check against",
    "PRICE_JUMP": "daily close-to-close move over 25% (split/bonus/demerger unadjusted, or a real move)",
    "ZERO_VOLUME_RUN": "5+ consecutive zero-volume daily bars in the last year (suspended?)",
    "FLAT_BAR_RUN": "5+ consecutive flat daily bars (open=high=low=close)",
    "FLAT_BAR_RUN_OLD": "same, but older than a year -- informational",
    "ZERO_VOLUME_RUN_OLD": "same, but older than a year -- informational",
    "DAILY_BARS_LT_200": "fewer than 200 daily bars: cannot warm up a 200 EMA",
    "DAILY_BARS_LT_100": "fewer than 100 daily bars: no 100/200 EMA",
    "DAILY_BARS_LT_50": "fewer than 50 daily bars: no 50/100/200 EMA",
    "DAILY_BARS_LT_26": "fewer than 26 daily bars: only the 5/13 EMA possible",
    "SMALL_FILE": "intraday file far smaller than its peers (recent listing or lost history)",
    "AUDIT_CRASH": "the audit itself failed on this file",
}


# --- Data model ------------------------------------------------------------

@dataclass
class Finding:
    severity: str            # ERROR | WARN | INFO
    check: str
    set_name: str
    instrument_key: str
    timeframe: str
    detail: str
    count: int = 1


@dataclass
class FileSpec:
    set_name: str
    instrument_key: Optional[str]    # None for an orphan file
    key: str                         # R2 object key
    expected_tfs: tuple
    kind: str
    is_reference: bool = False       # the Nifty 50 file of its set


@dataclass
class AuditContext:
    source: object
    now: datetime
    cal: pd.DatetimeIndex                         # Nifty 50 daily trade dates (sorted)
    cal_last: pd.Timestamp
    ref_intra: dict                               # tf -> Series(date -> bar count)
    ref_intra_last: Optional[pd.Timestamp]
    ref_special: set = field(default_factory=set)      # Nifty 50 special-session dates
    inactive: set = field(default_factory=set)         # instrument_keys not active in the catalogue


@dataclass
class AuditResult:
    scope_note: str = ""
    findings: list = field(default_factory=list)
    stats: list = field(default_factory=list)
    summary: str = ""


class _Collector:
    def __init__(self, spec: FileSpec):
        self.spec = spec
        self.items: list[Finding] = []

    def add(self, severity, check, detail, tf="", count=1):
        self.items.append(Finding(severity, check, self.spec.set_name,
                                  self.spec.instrument_key or self.spec.key, tf, detail, count))


# --- Helpers ---------------------------------------------------------------

def _normalize(df: pd.DataFrame) -> pd.DataFrame:
    """Add _ts (tz-aware IST timestamp) and _td (naive normalised trade date)."""
    out = df.copy()
    try:
        ts = pd.to_datetime(out["ts"])
        ts = ts.dt.tz_localize(IST_TZ) if ts.dt.tz is None else ts.dt.tz_convert(IST_TZ)
    except (TypeError, ValueError):
        ts = pd.to_datetime(out["ts"], utc=True).dt.tz_convert(IST_TZ)
    out["_ts"] = ts
    out["_td"] = pd.to_datetime(out["trade_date"]).dt.normalize()
    return out


def _fmt_dates(idx, n=5) -> str:
    vals = [pd.Timestamp(x).strftime("%Y-%m-%d") for x in list(idx)[:n]]
    more = f" (+{len(idx) - n} more)" if len(idx) > n else ""
    return ", ".join(vals) + more


def _longest_run(mask: np.ndarray):
    """(length, end_index) of the longest consecutive True run; (0, -1) if none."""
    if mask.size == 0 or not mask.any():
        return 0, -1
    m = mask.astype(np.int8)
    d = np.diff(np.concatenate(([0], m, [0])))
    starts, ends = np.where(d == 1)[0], np.where(d == -1)[0]
    lens = ends - starts
    i = int(lens.argmax())
    return int(lens[i]), int(ends[i] - 1)


def _bar_masks(g: pd.DataFrame, tf: str):
    """(valid, post_close, mins): valid = on the session grid; post_close = start >= 15:30."""
    mins = (g["_ts"].dt.hour * 60 + g["_ts"].dt.minute).to_numpy()
    interval = INTERVAL_MIN[tf]
    valid = (mins >= SESSION_START_MIN) & (mins <= LAST_START_MIN[tf]) & ((mins - SESSION_START_MIN) % interval == 0)
    post = mins >= SESSION_END_MIN
    return valid, post, mins


def _sev_by_frac(n: int, total: int) -> str:
    return "ERROR" if total and n / total > BAD_DAY_ERROR_FRAC else "WARN"


def _latest_weekday_before(now: datetime) -> pd.Timestamp:
    d = pd.Timestamp(now.date()) - pd.Timedelta(days=1)
    while d.weekday() >= 5:
        d -= pd.Timedelta(days=1)
    return d


# --- Per-file checks -------------------------------------------------------

def _check_structure(f: _Collector, df: pd.DataFrame, ctx: AuditContext):
    spec = f.spec
    present = set(df["timeframe"].unique())
    for tf in spec.expected_tfs:
        if tf not in present:
            f.add("ERROR", "MISSING_TIMEFRAME", "timeframe absent from file", tf)
    for tf in sorted(present - set(spec.expected_tfs)):
        f.add("WARN", "UNEXPECTED_TIMEFRAME", "unexpected timeframe in file", tf)

    for tf in spec.expected_tfs:
        g = df[df["timeframe"] == tf]
        if g.empty:
            continue
        if len(g) < 5:
            f.add("INFO" if tf in ("1w", "1mo") else "WARN", "TOO_FEW_ROWS", f"only {len(g)} rows", tf, len(g))
        dups = int(g.duplicated(["ts"]).sum())
        if dups:
            f.add("ERROR", "DUPLICATE_BARS", f"{dups} duplicate timestamps", tf, dups)
        if not g["_ts"].is_monotonic_increasing:
            f.add("ERROR", "NOT_SORTED", "bars not in ascending order", tf)

        ohlc = g[["open", "high", "low", "close"]].astype(float)
        nan_rows = int(ohlc.isna().any(axis=1).sum())
        if nan_rows:
            f.add("ERROR", "NAN_PRICES", f"{nan_rows} bars with NaN prices", tf, nan_rows)
        ohlc = ohlc.dropna()
        if ohlc.empty:
            continue
        nonpos = int((ohlc <= 0).any(axis=1).sum())
        if nonpos:
            f.add("ERROR", "NON_POSITIVE_PRICE", f"{nonpos} bars with price <= 0", tf, nonpos)
        o, h, l, c = ohlc["open"], ohlc["high"], ohlc["low"], ohlc["close"]
        bad = (h < l - PRICE_EPS) | (h < np.maximum(o, c) - PRICE_EPS) | (l > np.minimum(o, c) + PRICE_EPS)
        nbad = int(bad.sum())
        if nbad:
            first = g.loc[bad[bad].index[0], "_td"]
            f.add("WARN" if nbad <= 3 else "ERROR", "OHLC_INVALID",
                  f"{nbad} invalid bars, first on {first:%Y-%m-%d}", tf, nbad)

        n_future = int((g["_ts"] > pd.Timestamp(ctx.now, tz=IST_TZ)).sum())
        if n_future:
            f.add("ERROR", "FUTURE_BAR", f"{n_future} bars after now", tf, n_future)
        n_today = int((g["_td"] == pd.Timestamp(ctx.now.date())).sum())
        if n_today:
            f.add("WARN", "TODAY_BAR", f"{n_today} bars dated today (partial)", tf, n_today)
        mism = int((g["_ts"].dt.tz_localize(None).dt.normalize() != g["_td"]).sum())
        if mism:
            f.add("WARN", "TRADE_DATE_MISMATCH", f"{mism} bars where trade_date != ts date", tf, mism)


def _check_daily_set(f: _Collector, df: pd.DataFrame, ctx: AuditContext, stats: dict):
    spec = f.spec
    cal = ctx.cal
    inactive = (spec.instrument_key in ctx.inactive)
    g1 = df[df["timeframe"] == "1d"].sort_values("_ts")
    lags = {}
    if not g1.empty:
        dates = pd.DatetimeIndex(g1["_td"].unique())
        last = dates.max()
        lag = int((cal > last).sum())
        lags["1d"] = lag
        stats["primary_lag"] = lag
        stats["last_date"] = last
        if last > ctx.cal_last and not spec.is_reference:
            f.add("WARN", "AHEAD_OF_CALENDAR", f"last bar {last:%Y-%m-%d} > Nifty 50 {ctx.cal_last:%Y-%m-%d}", "1d")
        if lag >= STALE_WARN_DAYS:
            if inactive:
                f.add("INFO", "STALE_INACTIVE", f"last bar {last:%Y-%m-%d}, {lag} trading days behind", "1d", lag)
            elif lag >= STALE_ERROR_DAYS:
                f.add("ERROR", "STALE_SEVERE", f"last bar {last:%Y-%m-%d}, {lag} trading days behind", "1d", lag)
            else:
                f.add("WARN", "STALE", f"last bar {last:%Y-%m-%d}, {lag} trading days behind", "1d", lag)

        if not spec.is_reference:
            window = cal[(cal >= dates.min()) & (cal <= last)]
            missing = window.difference(dates)
            if len(missing):
                weekend = missing[missing.weekday >= 5]
                weekday = missing[missing.weekday < 5]
                if len(weekend):
                    f.add("INFO", "GAP_WEEKEND", f"{len(weekend)} special-session days missing: {_fmt_dates(weekend, 3)}", "1d", len(weekend))
                cutoff = ctx.cal_last - pd.Timedelta(days=RECENT_DAYS)
                recent, old = weekday[weekday >= cutoff], weekday[weekday < cutoff]
                if len(recent):
                    run, _ = _longest_run(~window.isin(dates) & (window.weekday < 5) & (window >= cutoff))
                    f.add("ERROR" if len(recent) >= GAP_ERROR_DAYS else "WARN", "GAP_DAILY",
                          f"{len(recent)} missing weekdays in last 2 years (longest run {run}): {_fmt_dates(recent)}",
                          "1d", len(recent))
                if len(old):
                    run, _ = _longest_run(~window.isin(dates) & (window.weekday < 5) & (window < cutoff))
                    f.add("WARN" if len(old) >= GAP_ERROR_DAYS else "INFO", "GAP_DAILY_OLD",
                          f"{len(old)} older missing weekdays (longest run {run}): {_fmt_dates(old, 3)}", "1d", len(old))
            extra = dates[(dates >= cal[0]) & ~dates.isin(cal)]
            if len(extra):
                f.add("WARN", "EXTRA_DAYS", f"{len(extra)} days not in Nifty calendar: {_fmt_dates(extra)}",
                      "1d", len(extra))

        # --- price jumps (possible unadjusted split/bonus/demerger) ---
        if "VIX" not in (spec.instrument_key or "").upper():
            close = g1.drop_duplicates("_td", keep="last").set_index("_td")["close"].astype(float)
            ret = close.pct_change().dropna()
            big = ret[ret.abs() > JUMP_PCT]
            if len(big):
                ex = ", ".join(f"{d:%Y-%m-%d} {v:+.1%}" for d, v in list(big.items())[-3:])
                f.add("WARN", "PRICE_JUMP", f"{len(big)} daily moves >{JUMP_PCT:.0%}; latest: {ex}", "1d", len(big))

        # --- zero-volume / flat runs (not for indices: volume is always 0) ---
        is_index = (spec.instrument_key or "").startswith("NSE_INDEX|")
        old_cut = ctx.cal_last - pd.Timedelta(days=OLD_RUN_DAYS)
        if not is_index:
            vol0 = (g1["volume"].fillna(0).to_numpy() == 0)
            run, end = _longest_run(vol0)
            if run >= FLAT_OR_ZERO_RUN:
                ed = g1["_td"].iloc[end]
                f.add("WARN" if ed >= old_cut else "INFO", "ZERO_VOLUME_RUN" if ed >= old_cut else "ZERO_VOLUME_RUN_OLD",
                      f"{run} consecutive zero-volume bars ending {ed:%Y-%m-%d}", "1d", run)
            flat = ((g1["open"] == g1["high"]) & (g1["high"] == g1["low"]) & (g1["low"] == g1["close"])).to_numpy()
            run, end = _longest_run(flat)
            if run >= FLAT_OR_ZERO_RUN:
                ed = g1["_td"].iloc[end]
                f.add("WARN" if ed >= old_cut else "INFO", "FLAT_BAR_RUN" if ed >= old_cut else "FLAT_BAR_RUN_OLD",
                      f"{run} consecutive flat bars ending {ed:%Y-%m-%d}", "1d", run)

        # --- indicator readiness (INFO) ---
        n = len(dates)
        stats["daily_bars"] = n
        for lim in (26, 50, 100, 200):
            if n < lim:
                f.add("INFO", f"DAILY_BARS_LT_{lim}", f"{n} daily bars", "1d", n)
                break

    # --- weekly / monthly freshness + rollups ---
    for tf, freq in (("1w", "W"), ("1mo", "M")):
        g = df[df["timeframe"] == tf]
        if g.empty or g1.empty:
            continue
        last = g["_td"].max()
        if last.to_period(freq) < ctx.cal_last.to_period(freq):
            behind = (ctx.cal_last.to_period(freq) - last.to_period(freq)).n
            lags[tf] = behind
            f.add("INFO" if inactive else "WARN", "STALE_INACTIVE" if inactive else "STALE",
                  f"last {tf} bar {last:%Y-%m-%d}, {behind} {'weeks' if freq == 'W' else 'months'} behind", tf, behind)
        else:
            lags[tf] = 0
        _rollup_check(f, g1, g, tf, freq, stats)

    if not inactive and lags.get("1d", 0) == 0 and any(v > 0 for k, v in lags.items() if k != "1d"):
        f.add("ERROR", "TF_OUT_OF_STEP",
              "1d is current but " + ", ".join(f"{k} behind" for k, v in lags.items() if k != "1d" and v > 0))


def _rollup_check(f: _Collector, daily: pd.DataFrame, other: pd.DataFrame, tf: str, freq: str, stats: dict):
    d = daily.drop_duplicates("_td", keep="last").sort_values("_td").copy()
    d["p"] = d["_td"].dt.to_period(freq)
    d = d[d["p"] < d["p"].iloc[-1]]                       # completed periods only
    o = other.drop_duplicates("_td", keep="last").sort_values("_td").copy()
    if d.empty or o.empty:
        return
    o["p"] = o["_td"].dt.to_period(freq)
    o = o.drop_duplicates("p", keep="last").set_index("p")
    d = d[d["p"] >= o.index.min()]
    if d.empty:
        return
    agg = d.groupby("p").agg(h=("high", "max"), l=("low", "min"))
    missing = agg.index.difference(o.index)
    if len(missing):
        f.add("WARN", "ROLLUP_MISSING_PERIOD",
              f"{len(missing)} completed periods without a {tf} bar: {', '.join(str(p) for p in list(missing)[:3])}",
              tf, len(missing))
    common = agg.index.intersection(o.index)
    if len(common):
        hh = (o.loc[common, "high"].astype(float) - agg.loc[common, "h"]) / agg.loc[common, "h"]
        ll = (o.loc[common, "low"].astype(float) - agg.loc[common, "l"]) / agg.loc[common, "l"]
        badmask = (hh.abs() > ROLLUP_HL_TOL) | (ll.abs() > ROLLUP_HL_TOL)
        bad = common[badmask.to_numpy()]
        stats["roll_total"] = stats.get("roll_total", 0) + len(common)
        stats["roll_bad"] = stats.get("roll_bad", 0) + len(bad)
        if len(bad):
            # describe the worst period: which side differs, by how much, and the two values
            worst_p = max(bad, key=lambda p: max(abs(hh[p]), abs(ll[p])))
            if abs(hh[worst_p]) >= abs(ll[worst_p]):
                side, a, b, pct = "high", o.loc[worst_p, "high"], agg.loc[worst_p, "h"], hh[worst_p]
            else:
                side, a, b, pct = "low", o.loc[worst_p, "low"], agg.loc[worst_p, "l"], ll[worst_p]
            f.add("WARN", "ROLLUP_MISMATCH",
                  f"{len(bad)}/{len(common)} periods differ ({', '.join(str(p) for p in list(bad)[:3])}); "
                  f"worst {worst_p}: {tf} {side} {float(a):.2f} vs daily-derived {float(b):.2f} ({pct:+.2%})",
                  tf, len(bad))


def _check_intraday_set(f: _Collector, df: pd.DataFrame, ctx: AuditContext, stats: dict):
    spec = f.spec
    inactive = (spec.instrument_key in ctx.inactive)
    last_dates = {}
    full_days = {}
    for tf in spec.expected_tfs:
        g = df[df["timeframe"] == tf].sort_values("_ts")
        if g.empty:
            continue
        valid, post, _mins = _bar_masks(g, tf)
        off = ~valid
        full = EXPECTED_BARS[tf]

        # --- off-session / post-close bars ---
        if off.any():
            if spec.is_reference:
                pd_dates = pd.DatetimeIndex(g.loc[post, "_td"].unique())
                if len(pd_dates):
                    f.add("WARN", "POST_CLOSE_BARS",
                          f"{int(post.sum())} bars at/after 15:30 on {len(pd_dates)} days "
                          f"({pd_dates.min():%Y-%m-%d} .. {pd_dates.max():%Y-%m-%d}); drop when reading", tf, int(post.sum()))
            else:
                offd = pd.DatetimeIndex(g.loc[off, "_td"].unique())
                offd = offd[~offd.isin(list(ctx.ref_special))]
                if len(offd):
                    f.add("WARN", "OFF_SESSION_BAR", f"bars off the 09:15-15:30 grid on {_fmt_dates(offd)}", tf, len(offd))

        gv = g[valid]                                   # only on-grid bars from here on
        if gv.empty:
            continue
        cnt = gv.groupby("_td").size()
        last = cnt.index.max()
        last_dates[tf] = last

        if spec.is_reference:
            odd = cnt[cnt != full]
            special = odd[odd < SPECIAL_FRAC * full]
            partial = odd[odd >= SPECIAL_FRAC * full]
            if len(special):
                ex = ", ".join(f"{d:%Y-%m-%d}={v}" for d, v in list(special.items())[:6])
                f.add("INFO", "SPECIAL_SESSION_DAYS", f"{len(special)} special-session days: {ex}", tf, len(special))
            if len(partial):
                ex = ", ".join(f"{d:%Y-%m-%d}={v}" for d, v in list(partial.items())[:4])
                f.add("WARN", "PARTIAL_DAYS", f"{len(partial)} regular days not at {full} bars: {ex}", tf, len(partial))
            full_days[tf] = cnt.index[cnt == full]
            if tf == "5m":
                stats["primary_lag"] = int((ctx.cal > last).sum())
                stats["last_date"] = last
            continue

        ref = ctx.ref_intra.get(tf)
        if ref is None or ref.empty:
            continue
        refw = ref[(ref.index >= cnt.index.min()) & (ref.index <= cnt.index.max())]
        c = cnt.reindex(refw.index).fillna(0)
        over = c[c > refw]
        if len(over):
            f.add("ERROR", "BARS_EXCEED_REFERENCE",
                  f"{len(over)} days with more bars than Nifty 50: {_fmt_dates(over.index)}", tf, len(over))
        miss_days = c[c == 0].index
        if len(miss_days):
            f.add(_sev_by_frac(len(miss_days), len(refw)), "MISSING_INTRADAY_DAYS",
                  f"{len(miss_days)}/{len(refw)} days absent: {_fmt_dates(miss_days)}", tf, len(miss_days))
        short = c[(c > 0) & (c < refw)]
        if len(short):
            ex = ", ".join(f"{d:%Y-%m-%d}={int(v)}/{int(refw[d])}" for d, v in list(short.items())[:3])
            f.add(_sev_by_frac(len(short), len(refw)), "SHORT_INTRADAY_DAYS",
                  f"{len(short)}/{len(refw)} days short: {ex}", tf, len(short))
        full_days[tf] = c.index[(c == refw) & (c > 0)]

        if ctx.ref_intra_last is not None:
            lag = int((ref.index > last).sum())
            if tf == "5m":
                stats["primary_lag"] = lag
                stats["last_date"] = last
            if lag >= STALE_WARN_DAYS:
                if inactive:
                    f.add("INFO", "STALE_INACTIVE", f"last bar {last:%Y-%m-%d}, {lag} trading days behind", tf, lag)
                elif lag >= STALE_ERROR_DAYS:
                    f.add("ERROR", "STALE_SEVERE", f"last bar {last:%Y-%m-%d}, {lag} trading days behind", tf, lag)
                else:
                    f.add("WARN", "STALE", f"last bar {last:%Y-%m-%d}, {lag} trading days behind", tf, lag)

    if not inactive and len(set(last_dates.values())) > 1:
        f.add("ERROR", "TF_OUT_OF_STEP",
              "timeframes end on different dates: " + ", ".join(f"{k}={v:%Y-%m-%d}" for k, v in last_dates.items()))

    for tf in spec.expected_tfs:
        stats.setdefault("rows", {})[tf] = int((df["timeframe"] == tf).sum())

    # --- intraday vs daily rollup ---
    if spec.instrument_key:
        _intraday_vs_daily(f, df, ctx, full_days)


def _intraday_vs_daily(f: _Collector, df: pd.DataFrame, ctx: AuditContext, full_days: dict):
    spec = f.spec
    daily_set = "indices_daily" if spec.instrument_key.startswith("NSE_INDEX|") else "universe_daily"
    dkey = ctx.source.object_key(spec.instrument_key, _KEY_DOMAIN[daily_set])
    ddf = ctx.source.read(dkey)
    if ddf is None or ddf.empty:
        f.add("WARN", "INTRADAY_DAILY_MISMATCH", "no daily file to cross-check against")
        return
    ddf = _normalize(ddf)
    dd = ddf[ddf["timeframe"] == "1d"].drop_duplicates("_td", keep="last").set_index("_td")
    special = set(ctx.ref_special)
    for tf in spec.expected_tfs:
        g = df[df["timeframe"] == tf].sort_values("_ts")
        if g.empty or tf not in full_days:
            continue
        valid, _post, _m = _bar_masks(g, tf)
        g = g[valid]
        day = g.groupby("_td").agg(h=("high", "max"), l=("low", "min"), c=("close", "last"))
        keep = day.index.isin(full_days[tf]) & ~day.index.isin(list(special)) & (day.index.weekday < 5)
        day = day[keep]
        common = day.index.intersection(dd.index)
        if len(common) == 0:
            continue
        dh, dl, dc = (dd.loc[common, k].astype(float) for k in ("high", "low", "close"))
        eh = (day.loc[common, "h"] - dh) / dh
        el = (day.loc[common, "l"] - dl) / dl
        ec = (day.loc[common, "c"] - dc) / dc

        bad_hl = ((eh.abs() > INTRA_HL_TOL) | (el.abs() > INTRA_HL_TOL)).to_numpy()
        if bad_hl.any():
            bd = common[bad_hl]
            w = max(bd, key=lambda d: max(abs(eh[d]), abs(el[d])))
            side, a, b, pct = (("high", day.loc[w, "h"], dh[w], eh[w]) if abs(eh[w]) >= abs(el[w])
                               else ("low", day.loc[w, "l"], dl[w], el[w]))
            f.add(_sev_by_frac(len(bd), len(common)), "INTRADAY_DAILY_HL",
                  f"{len(bd)}/{len(common)} full days: intraday high/low != daily; worst {w:%Y-%m-%d} {side} "
                  f"intraday {float(a):.2f} vs daily {float(b):.2f} ({pct:+.2%})", tf, len(bd))

        bad_c = (ec.abs() > INTRA_CLOSE_TOL).to_numpy()
        if bad_c.any():
            bd = common[bad_c]
            w = max(bd, key=lambda d: abs(ec[d]))
            sev = "WARN" if abs(ec[w]) > CLOSE_WARN_TOL else "INFO"
            f.add(sev, "INTRADAY_DAILY_CLOSE",
                  f"{len(bd)}/{len(common)} full days: last intraday close vs daily close > {INTRA_CLOSE_TOL:.1%}; "
                  f"worst {w:%Y-%m-%d} intraday {float(day.loc[w, 'c']):.2f} vs daily {float(dc[w]):.2f} ({ec[w]:+.2%})",
                  tf, len(bd))


def audit_file(spec: FileSpec, ctx: AuditContext, df: Optional[pd.DataFrame]):
    """Run all per-file checks. Returns (findings, stats)."""
    f = _Collector(spec)
    stats = {"set": spec.set_name, "key": spec.instrument_key or spec.key}
    if df is None:
        return f.items, stats
    if df.empty:
        f.add("ERROR", "EMPTY_FILE", "no rows")
        return f.items, stats
    missing_cols = [c for c in _REQUIRED_COLS if c not in df.columns]
    if missing_cols:
        f.add("ERROR", "MISSING_COLUMNS", f"missing: {', '.join(missing_cols)}")
        return f.items, stats
    try:
        ndf = _normalize(df)
    except Exception as exc:  # noqa: BLE001
        f.add("ERROR", "BAD_TIMESTAMPS", str(exc)[:120])
        return f.items, stats

    _check_structure(f, ndf, ctx)
    if spec.kind == "daily":
        _check_daily_set(f, ndf, ctx, stats)
    else:
        _check_intraday_set(f, ndf, ctx, stats)
    return f.items, stats


# --- Ledger / catalogue checks --------------------------------------------

def ledger_checks(rows, stocks, indices, listings, key_for, now, in_scope=None, inactive=None,
                  scope_all=True) -> list:
    """Compare ledger rows + catalogue against what R2 actually holds.
    in_scope(ik) -> bool limits row-level findings (default: everything).
    inactive = instrument_keys not active in the catalogue (their stale/failed rows are INFO)."""
    out: list[Finding] = []
    in_scope = in_scope or (lambda ik: True)
    inactive = inactive or set()
    expected_keys = defaultdict(set)         # set_name -> {R2 keys the ledger accounts for}
    ledger_ik = {"universe": set(), "indices": set()}
    intraday_ik = set()

    def stale(ts):
        try:
            return (now - pd.to_datetime(ts).to_pydatetime()).days > LEDGER_STALE_DAYS
        except Exception:  # noqa: BLE001
            return False

    def side(ik, set_name, status, ts, err):
        key = key_for(ik, set_name)
        expected_keys[set_name].add(key)
        if not in_scope(ik):
            return
        have = key in listings[set_name]
        gone = ik in inactive
        if status == "done" and not have:
            out.append(Finding("ERROR", "LEDGER_DONE_NO_FILE", set_name, ik, "", f"expected {key}"))
        elif status == "failed":
            out.append(Finding("INFO" if gone else "WARN", "LEDGER_FAILED_INACTIVE" if gone else "LEDGER_FAILED",
                               set_name, ik, "", (err or "")[:100]))
        elif status == "pending":
            out.append(Finding("WARN", "LEDGER_PENDING", set_name, ik, "", "never completed"))
        if status == "done" and stale(ts):
            out.append(Finding("INFO" if gone else "WARN", "LEDGER_STALE_INACTIVE" if gone else "LEDGER_STALE",
                               set_name, ik, "", f"last_success_at {ts}"))

    for r in rows:
        ik, dom = r["instrument_key"], r.get("domain")
        if dom in ("universe", "indices") and r.get("status") is not None:
            ledger_ik[dom].add(ik)
            side(ik, "universe_daily" if dom == "universe" else "indices_daily",
                 r["status"], r.get("last_success_at"), r.get("last_error"))
        if r.get("intraday_status") is not None:
            intraday_ik.add(ik)
            side(ik, "index_intraday" if ik.startswith("NSE_INDEX|") else "stocks_intraday",
                 r["intraday_status"], r.get("intraday_last_success_at"), r.get("intraday_last_error"))

    stock_ik = {s["instrument_key"] for s in stocks}
    if scope_all:
        for set_name, keys in listings.items():
            for k in sorted(set(keys) - expected_keys[set_name]):
                out.append(Finding("WARN", "ORPHAN_FILE", set_name, k, "", "no ledger row accounts for this file"))
        for ik in sorted(set(indices) - ledger_ik["indices"]):
            out.append(Finding("WARN", "CATALOGUE_NOT_IN_LEDGER", "indices_daily", ik, "", "active index without ledger row"))
        for ik in sorted(ledger_ik["universe"] - stock_ik):
            out.append(Finding("INFO", "LEDGER_INACTIVE_INSTRUMENT", "universe_daily", ik, "", "in ledger but not an active catalogue stock"))
        for ik in sorted(ledger_ik["indices"] - set(indices)):
            out.append(Finding("INFO", "LEDGER_INACTIVE_INSTRUMENT", "indices_daily", ik, "", "in ledger but not an active catalogue index"))
    for ik in sorted(stock_ik - ledger_ik["universe"]):
        if in_scope(ik):
            out.append(Finding("WARN", "CATALOGUE_NOT_IN_LEDGER", "universe_daily", ik, "", "active stock without ledger row"))
    for s in stocks:
        if s.get("is_fno_eligible") and s["instrument_key"] not in intraday_ik:
            out.append(Finding("WARN", "FNO_NOT_IN_INTRADAY_LEDGER", "stocks_intraday", s["instrument_key"], "", "F&O stock not tracked for intraday"))

    n50 = next((r for r in rows if r["instrument_key"] == NIFTY50_KEY), None)
    if not n50 or n50.get("intraday_status") != "done":
        out.append(Finding("ERROR", "NIFTY50_INTRADAY_NOT_DONE", "index_intraday", NIFTY50_KEY, "",
                           f"intraday_status={n50.get('intraday_status') if n50 else 'no ledger row'}"))
    return out


# --- Orchestration ---------------------------------------------------------

def _build_specs(rows, listings, key_for, only, limit, in_scope=None, include_orphans=True) -> list:
    specs: dict[tuple, FileSpec] = {}
    in_scope = in_scope or (lambda ik: True)

    def add(set_name, ik, key):
        if only and set_name != only:
            return
        if ik is not None and not in_scope(ik):
            return
        if ik is None and not include_orphans:
            return                       # orphan files are only audited in --scope all
        prefix, tfs, kind = SETS[set_name]
        specs[(set_name, key)] = FileSpec(set_name, ik, key, tfs, kind, is_reference=(ik == NIFTY50_KEY))

    for r in rows:
        ik, dom = r["instrument_key"], r.get("domain")
        if dom in ("universe", "indices") and r.get("status") is not None:
            s = "universe_daily" if dom == "universe" else "indices_daily"
            add(s, ik, key_for(ik, s))
        if r.get("intraday_status") is not None:
            s = "index_intraday" if ik.startswith("NSE_INDEX|") else "stocks_intraday"
            add(s, ik, key_for(ik, s))
    known = {k for (_, k) in specs}
    for s, keys in listings.items():
        for k in keys:
            if k not in known:
                add(s, None, k)

    out = sorted(specs.values(), key=lambda x: (x.set_name, x.key))
    if limit:
        counts = defaultdict(int)
        trimmed = []
        for sp in out:
            counts[sp.set_name] += 1
            if counts[sp.set_name] <= limit or sp.is_reference:
                trimmed.append(sp)
        out = trimmed
    return out


def run_audit(source, only: Optional[str] = None, limit: Optional[int] = None,
              workers: int = MAX_WORKERS, scope: str = "watchlist") -> AuditResult:
    res = AuditResult()
    now = source.now_ist()

    logger.info("Loading ledger, catalogues and R2 listings ...")
    rows = source.ledger_rows()
    stocks = source.catalogue_stocks()
    indices = source.catalogue_indices()
    listings = {s_: source.list_objects(SETS[s_][0]) for s_ in SETS}      # set -> {key: size}

    active = {x["instrument_key"] for x in stocks} | set(indices)
    inactive = {r["instrument_key"] for r in rows} - active
    # Scope: "watchlist" = Nifty 50 + F&O-eligible stocks (the watchlist); "all" = everything.
    fno = {x["instrument_key"] for x in stocks if x.get("is_fno_eligible")} | \
          {r["instrument_key"] for r in rows if r.get("intraday_status") is not None}
    if scope == "all":
        in_scope = lambda ik: True                                     # noqa: E731
    else:
        in_scope = lambda ik: ik == NIFTY50_KEY or ik in fno           # noqa: E731
    n_total = len({r["instrument_key"] for r in rows})
    n_scoped = len({r["instrument_key"] for r in rows if in_scope(r["instrument_key"])})
    res.scope_note = (f"Scope: {'ALL instruments' if scope == 'all' else 'Nifty 50 + F&O watchlist'} -- "
                      f"{n_scoped} of {n_total} ledger instruments audited"
                      + ("" if scope == "all" else " (use --scope all for the rest)"))

    res.findings.extend(ledger_checks(rows, stocks, indices, listings,
                                      lambda ik, s_: source.object_key(ik, _KEY_DOMAIN[s_]), now,
                                      in_scope=in_scope, inactive=inactive, scope_all=(scope == "all")))

    # --- reference files ---
    nd_key = source.object_key(NIFTY50_KEY, "indices")
    ni_key = source.object_key(NIFTY50_KEY, "universe_intraday")
    nd = source.read(nd_key)
    if nd is None or nd.empty:
        res.findings.append(Finding("ERROR", "REFERENCE_MISSING", "indices_daily", NIFTY50_KEY, "1d",
                                    f"{nd_key} missing -- file checks skipped"))
        res.summary = render_summary(res, now, None, {}, [])
        return res
    nd = _normalize(nd)
    cal = pd.DatetimeIndex(sorted(nd.loc[nd["timeframe"] == "1d", "_td"].unique()))
    cal_last = cal.max()
    expected_last = _latest_weekday_before(now)
    if cal_last < expected_last:
        res.findings.append(Finding("WARN", "REFERENCE_BEHIND", "indices_daily", NIFTY50_KEY, "1d",
                                    f"Nifty 50 daily ends {cal_last:%Y-%m-%d}; latest weekday is {expected_last:%Y-%m-%d} (holiday or missed refresh)"))
    probe = []
    for tf in ("1w", "1mo"):
        g = nd[nd["timeframe"] == tf].tail(3)
        probe.append(f"{tf}: " + ", ".join(f"ts={a:%Y-%m-%d %H:%M} trade_date={b:%Y-%m-%d}"
                                           for a, b in zip(g["_ts"], g["_td"])))

    ni = source.read(ni_key)
    ref_intra, ref_intra_last, ref_special = {}, None, set()
    if ni is not None and not ni.empty:
        ni = _normalize(ni)
        for tf in EXPECTED_BARS:
            g = ni[ni["timeframe"] == tf]
            if g.empty:
                continue
            valid, post, _m = _bar_masks(g, tf)
            cnt = g[valid].groupby("_td").size()
            ref_intra[tf] = cnt                              # on-grid bars only (post-close stubs excluded)
            full = EXPECTED_BARS[tf]
            ref_special |= set(cnt.index[cnt < SPECIAL_FRAC * full])
            ref_special |= set(g.loc[~valid & ~post, "_td"].unique())      # off-grid in-session bars (Muhurat)
            ref_special |= {d for d in cnt.index if d.weekday() >= 5}
        ref_intra_last = ref_intra["5m"].index.max() if "5m" in ref_intra and len(ref_intra["5m"]) else None
        if ref_intra_last is not None and ref_intra_last < cal_last:
            res.findings.append(Finding("ERROR", "REFERENCE_INTRADAY_BEHIND", "index_intraday", NIFTY50_KEY, "5m",
                                        f"intraday ends {ref_intra_last:%Y-%m-%d}, daily ends {cal_last:%Y-%m-%d}"))
    # --- calendar blind-spot check -------------------------------------------------
    # The Nifty 50 DAILY file is our trading calendar, so a day missing from it is invisible
    # to every other check. Cross-check it against Nifty 50 INTRADAY (an independent
    # series, 2022 onwards): a regular session present in intraday but absent from daily is
    # a hole in the daily data of the whole market. Add such days to the calendar so every
    # stock's gap check sees them too.
    if "5m" in ref_intra and len(ref_intra["5m"]):
        intra_days = pd.DatetimeIndex(ref_intra["5m"].index)
        holes = intra_days.difference(cal)
        regular = pd.DatetimeIndex([d for d in holes if d not in ref_special])
        special = pd.DatetimeIndex([d for d in holes if d in ref_special])
        if len(regular):
            res.findings.append(Finding(
                "ERROR", "REFERENCE_DAILY_MISSING", "indices_daily", NIFTY50_KEY, "1d",
                f"{len(regular)} regular sessions are in Nifty 50 intraday but missing from Nifty 50 daily "
                f"(so from the calendar): {_fmt_dates(regular, 8)}", len(regular)))
            cal = cal.union(regular)
            cal_last = cal.max()
        if len(special):
            res.findings.append(Finding(
                "INFO", "REFERENCE_DAILY_MISSING_SPECIAL", "indices_daily", NIFTY50_KEY, "1d",
                f"{len(special)} special-session days in Nifty 50 intraday but not in daily: {_fmt_dates(special, 8)}",
                len(special)))

    ctx = AuditContext(source, now, cal, cal_last, ref_intra, ref_intra_last,
                       ref_special=ref_special, inactive=inactive)

    # --- per-file audit ---
    specs = _build_specs(rows, listings, lambda ik, s_: source.object_key(ik, _KEY_DOMAIN[s_]), only, limit, in_scope, include_orphans=(scope == "all"))
    to_read = [sp for sp in specs if sp.key in listings[sp.set_name]]
    logger.info("Auditing %d file(s) with %d workers ...", len(to_read), workers)

    def work(sp: FileSpec):
        try:
            df = source.read(sp.key)
            return audit_file(sp, ctx, df)
        except Exception as exc:  # noqa: BLE001 -- one bad file must not stop the audit
            logger.error("Audit crashed on %s: %s", sp.key, exc)
            return ([Finding("ERROR", "AUDIT_CRASH", sp.set_name, sp.instrument_key or sp.key, "", f"{type(exc).__name__}: {exc}"[:150])],
                    {"set": sp.set_name, "key": sp.instrument_key or sp.key})

    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(work, sp) for sp in to_read]
        for i, fut in enumerate(as_completed(futs), 1):
            fnd, st = fut.result()
            res.findings.extend(fnd)
            res.stats.append(st)
            if i % 250 == 0:
                logger.info("  audited %d/%d", i, len(to_read))

    _small_files(res)
    res.summary = render_summary(res, now, (cal_last, expected_last, ref_intra_last), {"probe": probe},
                                 [(s, len([x for x in to_read if x.set_name == s]),
                                   len(listings[s])) for s in SETS])
    return res


def _small_files(res: AuditResult):
    by_tf = defaultdict(list)
    for st in res.stats:
        if st.get("set") == "stocks_intraday":
            for tf, n in st.get("rows", {}).items():
                by_tf[tf].append((st["key"], n))
    for tf, items in by_tf.items():
        if len(items) < 10:
            continue
        med = float(np.median([n for _, n in items]))
        for key, n in items:
            if med and n < SMALL_FILE_FRAC * med:
                res.findings.append(Finding("INFO", "SMALL_FILE", "stocks_intraday", key, tf,
                                            f"{n} rows vs peer median {int(med)}", n))


# --- Reporting -------------------------------------------------------------

def render_summary(res: AuditResult, now, ref, extra, set_counts) -> str:
    sev_n = defaultdict(int)
    for x in res.findings:
        sev_n[x.severity] += 1
    L = []
    L.append("=" * 78)
    L.append(f"FORTUNA OHLCV DATA AUDIT  --  {now:%Y-%m-%d %H:%M} IST   (read-only)")
    L.append("=" * 78)
    if ref:
        cal_last, expected_last, ri = ref
        L.append(f"Reference: Nifty 50 daily last bar {cal_last:%Y-%m-%d} | latest weekday {expected_last:%Y-%m-%d} | "
                 f"Nifty 50 intraday last day {ri:%Y-%m-%d}" if ri is not None else
                 f"Reference: Nifty 50 daily last bar {cal_last:%Y-%m-%d} | latest weekday {expected_last:%Y-%m-%d} | no intraday reference")
        for p in extra.get("probe", []):
            L.append(f"  convention probe  {p}")
    if res.scope_note:
        L.append(res.scope_note)
    L.append(f"Files audited: {len(res.stats)}   |   ERROR {sev_n['ERROR']}   WARN {sev_n['WARN']}   INFO {sev_n['INFO']}")
    L.append("")

    groups = defaultdict(list)
    for x in res.findings:
        groups[(x.severity, x.check)].append(x)

    def block(sev, title):
        keys = sorted((k for k in groups if k[0] == sev), key=lambda k: -len({x.instrument_key for x in groups[k]}))
        if not keys:
            L.append(f"{title}: none")
            L.append("")
            return
        L.append(title)
        for k in keys:
            items = groups[k]
            n = len({x.instrument_key for x in items})
            L.append(f"  [{sev}] {k[1]}  --  {n} file(s)")
            L.append(f"      {CHECK_HELP.get(k[1], '')}")
            by_set = defaultdict(int)
            for x in items:
                by_set[x.set_name] += 1
            L.append("      by set: " + ", ".join(f"{s}={c}" for s, c in sorted(by_set.items())))
            for x in sorted(items, key=lambda y: y.instrument_key)[:4]:
                L.append(f"        - {x.instrument_key} {x.timeframe}: {x.detail}")
        L.append("")

    block("ERROR", "NEEDS ATTENTION FIRST (errors)")
    block("WARN", "WORTH A LOOK (warnings)")

    inf = sorted((k for k in groups if k[0] == "INFO"))
    L.append("PLANNING INFO")
    daily_bars = [st["daily_bars"] for st in res.stats if st.get("set") == "universe_daily" and "daily_bars" in st]
    if daily_bars:
        a = np.array(daily_bars)
        L.append(f"  stocks with daily history: {len(a)}   <200 bars: {(a < 200).sum()}   <100: {(a < 100).sum()}   "
                 f"<50: {(a < 50).sum()}   <26: {(a < 26).sum()}")
    for k in inf:
        if k[1].startswith("DAILY_BARS_LT"):
            continue
        L.append(f"  {k[1]}: {len(groups[k])} -- {CHECK_HELP.get(k[1], '')}")
    L.append("")

    L.append("PER SET")
    L.append(f"  {'set':<17}{'ledger-expected':>16}{'in R2':>8}{'audited':>9}{'ERROR files':>13}{'WARN files':>12}{'clean':>7}  freshness (lag 0 / 1-4 / 5+)")
    for set_name, n_exp, n_r2 in set_counts:
        sts = [s for s in res.stats if s.get("set") == set_name]
        keys = {s["key"] for s in sts}
        err = {x.instrument_key for x in res.findings if x.set_name == set_name and x.severity == "ERROR"} & keys
        warn = {x.instrument_key for x in res.findings if x.set_name == set_name and x.severity == "WARN"} & keys
        clean = len(keys - err - warn)
        lags = [s["primary_lag"] for s in sts if "primary_lag" in s]
        fresh = f"{sum(1 for v in lags if v == 0)} / {sum(1 for v in lags if 1 <= v < STALE_ERROR_DAYS)} / {sum(1 for v in lags if v >= STALE_ERROR_DAYS)}"
        L.append(f"  {set_name:<17}{n_exp:>16}{n_r2:>8}{len(sts):>9}{len(err):>13}{len(warn - err):>12}{clean:>7}  {fresh}")

    # assumption sanity: if most weekly/monthly PERIODS mismatch, it's a convention issue, not data
    tot = sum(st.get("roll_total", 0) for st in res.stats)
    bad = sum(st.get("roll_bad", 0) for st in res.stats)
    if tot and bad / tot > 0.2:
        L.append("")
        L.append(f"NOTE: {bad}/{tot} weekly/monthly periods fail the rollup check -- that is too many to be data faults;")
        L.append("      the weekly/monthly date convention probably differs from my assumption (see the probe).")
    L.append("=" * 78)
    return "\n".join(L)


def findings_to_csv(res: AuditResult, path: str) -> None:
    rows = [{"severity": x.severity, "check": x.check, "set": x.set_name, "instrument_key": x.instrument_key,
             "timeframe": x.timeframe, "count": x.count, "detail": x.detail}
            for x in sorted(res.findings, key=lambda y: ({"ERROR": 0, "WARN": 1, "INFO": 2}[y.severity], y.check, y.instrument_key))]
    pd.DataFrame(rows, columns=["severity", "check", "set", "instrument_key", "timeframe", "count", "detail"]).to_csv(path, index=False)


# --- Live source (R2 + Supabase) ------------------------------------------

class LiveSource:
    """All I/O lives here so the analysis above stays pure and testable. Read-only."""

    def __init__(self):
        from db.r2_client import get_r2, get_r2_settings
        from db.supabase_client import get_supabase
        from modules.market_data.upstox import ohlcv_store
        self._r2 = get_r2()
        self._bucket = get_r2_settings().bucket
        self._sb = get_supabase()
        self._store = ohlcv_store

    def now_ist(self) -> datetime:
        return datetime.now(IST).replace(tzinfo=None)

    def object_key(self, instrument_key: str, domain: str) -> str:
        return self._store._object_key(instrument_key, domain)

    def list_objects(self, prefix: str) -> dict:
        out, token = {}, None
        while True:
            kw = {"Bucket": self._bucket, "Prefix": prefix + "/"}
            if token:
                kw["ContinuationToken"] = token
            resp = self._r2.list_objects_v2(**kw)
            for o in resp.get("Contents", []):
                if o["Key"].endswith(".parquet"):
                    out[o["Key"]] = o["Size"]
            if not resp.get("IsTruncated"):
                return out
            token = resp.get("NextContinuationToken")

    def read(self, key: str) -> Optional[pd.DataFrame]:
        import io
        from botocore.exceptions import ClientError
        try:
            obj = self._r2.get_object(Bucket=self._bucket, Key=key)
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code", "") in ("NoSuchKey", "404"):
                return None
            raise
        return pd.read_parquet(io.BytesIO(obj["Body"].read()), engine="pyarrow")

    def _paged(self, table: str, columns: str, eq: Optional[dict] = None) -> list:
        rows, start, PAGE = [], 0, 1000
        while True:
            q = self._sb.table(table).select(columns)
            for k, v in (eq or {}).items():
                q = q.eq(k, v)
            batch = q.range(start, start + PAGE - 1).execute().data or []
            rows.extend(batch)
            if len(batch) < PAGE:
                return rows
            start += PAGE

    def ledger_rows(self) -> list:
        return self._paged("f_ohlcv_fetch_progress",
                           "instrument_key, domain, status, last_success_at, last_error, "
                           "intraday_status, intraday_last_success_at, intraday_last_error")

    def catalogue_stocks(self) -> list:
        return self._paged("f_universe_instruments", "instrument_key, is_fno_eligible", {"is_active": True})

    def catalogue_indices(self) -> list:
        return [r["instrument_key"] for r in
                self._paged("f_all_nse_index_instruments", "instrument_key", {"is_active": True})]


def cli_main() -> None:
    import argparse
    import os
    from dotenv import load_dotenv

    load_dotenv()
    os.makedirs("logs", exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(),                                    # terminal, as before
            logging.FileHandler("logs/data_audit.log", mode="w"),       # overwritten each run
        ],
    )
    p = argparse.ArgumentParser(description="Read-only OHLCV data audit.")
    p.add_argument("--only", choices=sorted(SETS), default=None, help="audit one set only")
    p.add_argument("--scope", choices=("watchlist", "all"), default="watchlist",
                   help="watchlist = Nifty 50 + F&O stocks (default); all = every instrument")
    p.add_argument("--limit", type=int, default=None, help="audit only the first N files per set (smoke test)")
    args = p.parse_args()

    res = run_audit(LiveSource(), only=args.only, limit=args.limit, scope=args.scope)
    print(res.summary)
    logger.info("Audit complete: %d file(s), %d finding(s).", len(res.stats), len(res.findings))
    stamp = datetime.now(IST).strftime("%Y%m%d_%H%M")
    with open("logs/data_audit_summary.txt", "w", encoding="utf-8") as fh:
        fh.write(res.summary + "\n")
    csv_path = f"logs/data_audit_findings_{stamp}.csv"
    findings_to_csv(res, csv_path)
    print(f"\nSummary -> logs/data_audit_summary.txt\nAll findings -> {csv_path}")


if __name__ == "__main__":
    cli_main()
