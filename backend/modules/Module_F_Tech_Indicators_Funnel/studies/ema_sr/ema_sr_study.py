"""
EMA S&R study (Ash, 2026-10-19): does price bounce at EMAs on Nifty, which EMAs,
on which timeframes, after how many touches — measured, not assumed.

Lines tested
  - EMA 5 / 13 / 26 / 50 / 100 / 200 (Ash's set) + EMA 20 (the books' intraday
    EMA, Brooks / Raschke) on each timeframe's own candles (1M, 1W, 1D since
    2000; 60m, 15m, 5m since 2022).
  - Daily EMAs on 60m / 15m / 5m candles (option A: the daily EMA on the
    trading chart). Each intraday candle uses the PREVIOUS day's daily EMA —
    today's daily EMA is not known until today's close (no future data).
  EMAs use the TradingView-matched ema_tradingview (via compute_emas).

Episodes: line_reaction_study.find_episodes, both touch modes (wick / close),
X = average candle move over the last 20 candles.

Conditions — measured on the candle BEFORE the episode's first candle, i.e. only
what was known before the touch (study rule, 2026-10-19: measuring them on the
touch candle leaked the outcome — a falling EMA at support on the touch candle
means that candle already closed below the line):
  - with_trend : support in an up stack (stage > 0) or resistance in a down
                 stack (stage < 0) — Ash's EMA stack as the trend (option a,
                 2026-10-19). The line's own slope can NOT be used: an EMA always
                 rises after a candle that closes above it, so before a touch at
                 support it is rising by definition (found by the tests).
                 Market-structure trend (BOS / CHoCH) is option b, if needed.
  - stage      : Ash's EMA stack stage -5..+5 (stack_stage, same timeframe)
  - above_200  : close above that timeframe's EMA 200
  - era        : 2000-2012 / 2013-2019 / 2020-2026 (from the start time)
  - clear_bucket: candles price stayed clear before the touch (1-4 / 5-19 / 20+;
                  20 = Brooks' "20 gap bar")

Control (Chung & Bellotti 2021 method): the same test on prices rebuilt from the
real candles in random order (each candle's open/high/low/close relative to the
previous close, shuffled together), `shuffles` times (default 20, fixed seeds).
The control episodes get the same conditions from their own EMAs, so every
split (trend, stage, ...) is compared with the control in the same split.
Edge = real bounce % - control bounce %. Not run for daily EMAs on intraday
candles (one random order cannot keep the daily and intraday prices consistent).

Pure functions here; the runner (main) reads Nifty through the indicator reader,
writes progress lines to the screen and logs/studies_logs/ema_sr_study_progress.log
as it runs, then logs/studies_logs/ema_sr_episodes.csv (one row per real episode)
and logs/studies_logs/ema_sr_study.log (summary). Read-only.

Usage (from backend/):
    python -m modules.Module_F_Tech_Indicators_Funnel.studies.ema_sr.ema_sr_study
    python -m modules.Module_F_Tech_Indicators_Funnel.studies.ema_sr.ema_sr_study --timeframes 1d 1w --shuffles 5
"""

from __future__ import annotations

import argparse
import logging
import math
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

import numpy as np
import pandas as pd

from modules.Module_F_Tech_Indicators_Funnel.indicator_common.timeframes import (
    DEFAULT_DOMAIN,
    TIMEFRAMES,
    is_intraday,
)
from modules.Module_F_Tech_Indicators_Funnel.indicator_common.line_reaction_study import (
    DEFAULT_X_WINDOW,
    find_episodes,
    touch_table,
)
from modules.Module_F_Tech_Indicators_Funnel.trend_indicators.ema.ema import (
    DEFAULT_PERIODS,
    compute_emas,
    stack_stage,
)

logger = logging.getLogger(__name__)

NIFTY_KEY = "NSE_INDEX|Nifty 50"
STUDY_PERIODS = (5, 13, 20, 26, 50, 100, 200)
TOUCH_MODES = ("wick", "close")
DEFAULT_SHUFFLES = 20
MIN_CASES = 30            # rows with fewer resolved episodes are flagged "few cases"
ERAS = ((2000, 2012, "2000-2012"), (2013, 2019, "2013-2019"), (2020, 2100, "2020-2026"))
SPLITS = ("side", "with_trend", "above_200", "stage", "clear_bucket", "era")


def _noop(_msg: str) -> None:
    return None


# --- pure helpers ---------------------------------------------------------------

def to_candles(df: pd.DataFrame) -> pd.DataFrame:
    """Reader output -> candles with `time` (and `trade_date` kept)."""
    return df.rename(columns={"ts": "time"}).reset_index(drop=True)


def add_lines(candles: pd.DataFrame) -> pd.DataFrame:
    """EMA columns for STUDY_PERIODS + stack stage (Ash's 6 EMAs) + close above EMA 200."""
    out = compute_emas(candles, STUDY_PERIODS)
    out["stage"] = stack_stage(out, DEFAULT_PERIODS)
    out["above_200"] = out["close"] > out["ema_200"]
    return out


def daily_lines_on_intraday(intraday: pd.DataFrame, daily: pd.DataFrame) -> pd.DataFrame:
    """Each intraday candle gets the PREVIOUS trading day's daily EMAs (d_ema_<n>)
    and daily stack stage (d_stage). Needs `trade_date` on both."""
    d = add_lines(daily)
    cols = [f"ema_{p}" for p in STUDY_PERIODS] + ["stage"]
    d = d[["trade_date"] + cols].copy()
    d["_day"] = pd.to_datetime(d["trade_date"]).dt.normalize()
    d = d.rename(columns={c: f"d_{c}" for c in cols}).drop(columns="trade_date").sort_values("_day")
    i = intraday.copy()
    i["_day"] = pd.to_datetime(i["trade_date"]).dt.normalize()
    i["_row"] = np.arange(len(i))
    merged = pd.merge_asof(i.sort_values("_day"), d, on="_day", allow_exact_matches=False)
    return merged.sort_values("_row").drop(columns=["_day", "_row"]).reset_index(drop=True)


def shuffled_candles(candles: pd.DataFrame, seed: int) -> pd.DataFrame:
    """Same candles, random order: each candle's open/high/low/close as a ratio of
    the previous close is kept together; the price path is rebuilt from the first close."""
    o = candles["open"].to_numpy(dtype=float)
    h = candles["high"].to_numpy(dtype=float)
    lo = candles["low"].to_numpy(dtype=float)
    c = candles["close"].to_numpy(dtype=float)
    prev = c[:-1]
    shape = np.column_stack([o[1:] / prev, h[1:] / prev, lo[1:] / prev, c[1:] / prev])
    shape = shape[np.random.default_rng(seed).permutation(len(shape))]
    closes = c[0] * np.cumprod(shape[:, 3])
    prev_new = np.concatenate([[c[0]], closes[:-1]])
    return pd.DataFrame({
        "time": candles["time"].to_numpy(),
        "open": np.concatenate([[o[0]], shape[:, 0] * prev_new]),
        "high": np.concatenate([[h[0]], shape[:, 1] * prev_new]),
        "low": np.concatenate([[lo[0]], shape[:, 2] * prev_new]),
        "close": np.concatenate([[c[0]], closes]),
    })


def _era(year: int) -> str:
    for a, b, name in ERAS:
        if a <= year <= b:
            return name
    return "other"


def _clear_bucket(n: float) -> str:
    if n < 5:
        return "1-4"
    if n < 20:
        return "5-19"
    return "20+"


def episodes_with_conditions(lined: pd.DataFrame, line_col: str, touch_mode: str,
                             stage_col: Optional[str]) -> pd.DataFrame:
    """find_episodes on one line + the conditions on the candle BEFORE each
    episode's first candle (known before the touch). An episode on the very first
    candle has no candle before it: its conditions are blank (NaN)."""
    ep = find_episodes(lined, lined[line_col], touch_mode, x_window=DEFAULT_X_WINDOW)
    if ep.empty:
        return ep
    pos = pd.Index(pd.to_datetime(lined["time"])).get_indexer(ep["start_time"])
    before = pos - 1
    has_before = before >= 0
    prev = lined.iloc[np.where(has_before, before, 0)].reset_index(drop=True)

    def cond(col: str) -> pd.Series:
        s = prev[col].astype(object)
        s[~has_before] = np.nan
        return s

    if stage_col:
        stage = pd.to_numeric(cond(stage_col), errors="coerce")
        ep["stage"] = stage
        support = (ep["side"] == "support").to_numpy()
        wt = pd.Series(np.nan, index=ep.index, dtype=object)
        known = stage.notna().to_numpy()
        flat = known & (stage.to_numpy() == 0)
        wt[known & support] = (stage[known & support] > 0)
        wt[known & ~support] = (stage[known & ~support] < 0)
        wt[flat] = np.nan            # stage 0 = no trend: neither with nor against
        ep["with_trend"] = wt
    if "above_200" in prev:
        above = cond("above_200")
        # no EMA 200 yet on that candle -> blank, not False
        if "ema_200" in prev:
            above[prev["ema_200"].isna().to_numpy() & has_before] = np.nan
        ep["above_200"] = above
    ep["era"] = [_era(t.year) for t in pd.to_datetime(ep["start_time"])]
    ep["clear_bucket"] = [_clear_bucket(n) for n in ep["candles_clear_before"]]
    return ep


def rates(ep: pd.DataFrame) -> dict:
    """Resolved episodes, bounce % and break %."""
    done = ep[ep["outcome"].isin(["bounce", "break"])] if not ep.empty else ep
    n = len(done)
    b = int((done["outcome"] == "bounce").sum()) if n else 0
    return {"n": n, "bounce_pct": round(100.0 * b / n, 1) if n else math.nan,
            "break_pct": round(100.0 * (n - b) / n, 1) if n else math.nan}


def control_summary(control_eps: list[pd.DataFrame]) -> dict:
    """Overall control bounce %: mean over the random runs, with min and max."""
    pcts, ns = [], []
    for ep in control_eps:
        r = rates(ep)
        if r["n"]:
            pcts.append(r["bounce_pct"])
            ns.append(r["n"])
    if not pcts:
        return {"ctrl_bounce_pct": math.nan, "ctrl_min": math.nan, "ctrl_max": math.nan, "ctrl_n": 0}
    return {"ctrl_bounce_pct": round(float(np.mean(pcts)), 1), "ctrl_min": min(pcts),
            "ctrl_max": max(pcts), "ctrl_n": int(round(np.mean(ns)))}


def split_table(ep: pd.DataFrame, by: str, control_eps: Optional[list[pd.DataFrame]] = None) -> pd.DataFrame:
    """Resolved episodes and bounce % per value of a condition; with control
    episodes also the control's bounce % in the same group (all random runs pooled),
    its average episodes per run, and the edge."""
    if ep.empty or by not in ep:
        return pd.DataFrame(columns=[by, "n", "bounce_pct"])
    ctrl = None
    runs = 0
    if control_eps:
        non_empty = [c for c in control_eps if not c.empty and by in c]
        runs = len(control_eps)
        ctrl = pd.concat(non_empty, ignore_index=True) if non_empty else None
    rows = []
    for key, g in ep.groupby(by, dropna=True, sort=True):
        r = rates(g)
        row = {by: key, "n": r["n"], "bounce_pct": r["bounce_pct"]}
        if control_eps is not None:
            cg = ctrl[ctrl[by] == key] if ctrl is not None else pd.DataFrame(columns=["outcome"])
            cr = rates(cg)
            row["ctrl_n_per_run"] = round(cr["n"] / runs, 1) if runs else 0
            row["ctrl_bounce_pct"] = cr["bounce_pct"]
            row["edge_pts"] = (round(r["bounce_pct"] - cr["bounce_pct"], 1)
                               if not (math.isnan(r["bounce_pct"]) or math.isnan(cr["bounce_pct"])) else math.nan)
        rows.append(row)
    return pd.DataFrame(rows)


# --- runner ---------------------------------------------------------------------

def _read(reader, key: str, tf: str, daily_domain: str):
    domain = DEFAULT_DOMAIN[tf] if is_intraday(tf) else daily_domain
    return reader(key, domain, tf)


def _fmt_table(df: pd.DataFrame) -> list[str]:
    return ["    " + line for line in df.to_string(index=False).splitlines()] if not df.empty else ["    (none)"]


def run_study(reader, key: str, timeframes, shuffles: int, daily_domain: str = "indices",
              progress: Callable[[str], None] = _noop):
    """Returns (real episodes DataFrame, report lines). Never raises for one bad timeframe."""
    all_eps, report, summary = [], [], []
    t0 = time.perf_counter()
    daily_res = _read(reader, key, "1d", daily_domain)
    daily = to_candles(daily_res.df) if daily_res.ok else None

    for tf in timeframes:
        t_tf = time.perf_counter()
        res = _read(reader, key, tf, daily_domain)
        if not res.ok:
            report.append(f"{tf}: NOT OK -- {res.error}")
            progress(f"{tf}: NOT OK -- {res.error}")
            continue
        candles = to_candles(res.df)
        lined = add_lines(candles)
        progress(f"{tf}: read {len(candles):,} candles ({time.perf_counter() - t_tf:.1f} s)")

        t_c = time.perf_counter()
        control_lined = [add_lines(shuffled_candles(candles, seed=s)) for s in range(shuffles)]
        if shuffles:
            progress(f"{tf}: built {shuffles} random orders for the control ({time.perf_counter() - t_c:.1f} s)")

        jobs = [(f"ema_{p}", "stage", p, True) for p in STUDY_PERIODS]
        if is_intraday(tf) and daily is not None:
            lined = daily_lines_on_intraday(lined, daily)
            jobs += [(f"d_ema_{p}", "d_stage", p, False) for p in STUDY_PERIODS]

        report += ["", "=" * 110,
                   f"{tf}: {len(candles):,} candles, {pd.Timestamp(candles['time'].iloc[0]):%d %b %Y} "
                   f"to {pd.Timestamp(candles['time'].iloc[-1]):%d %b %Y}", "=" * 110]
        for line_col, stage_col, period, with_control in jobs:
            for mode in TOUCH_MODES:
                t_job = time.perf_counter()
                name = (f"daily EMA {period} on {tf}" if line_col.startswith("d_") else f"EMA {period}")
                try:
                    ep = episodes_with_conditions(lined, line_col, mode, stage_col)
                    ctrl_eps = ([episodes_with_conditions(cl, line_col, mode, stage_col)
                                 for cl in control_lined] if with_control and shuffles else None)
                except ValueError as exc:
                    report.append(f"  {name} {mode}: NOT OK -- {exc}")
                    progress(f"{tf}: {name} {mode}: NOT OK -- {exc}")
                    continue
                r = rates(ep)
                ctrl = control_summary(ctrl_eps) if ctrl_eps is not None else {}
                row = {"timeframe": tf, "line": name, "touch": mode, **r, **ctrl}
                if ctrl and not math.isnan(ctrl.get("ctrl_bounce_pct", math.nan)) and not math.isnan(r["bounce_pct"]):
                    row["edge_pts"] = round(r["bounce_pct"] - ctrl["ctrl_bounce_pct"], 1)
                row["few_cases"] = r["n"] < MIN_CASES
                summary.append(row)
                progress(f"{tf}: {name:<22} {mode:<5} - {r['n']:,} episodes"
                         + (f", control {shuffles}/{shuffles} done" if ctrl_eps is not None else "")
                         + f" ({time.perf_counter() - t_job:.1f} s)")
                if not ep.empty:
                    ep.insert(0, "touch_mode", mode)
                    ep.insert(0, "line", name)
                    ep.insert(0, "timeframe", tf)
                    all_eps.append(ep)
                if mode == "wick":   # detail tables for the wick mode
                    report += ["", f"  {name} (wick touch): episodes {r['n']:,}  bounce {r['bounce_pct']}%  "
                                   f"break {r['break_pct']}%"
                               + (f"  | control {ctrl['ctrl_bounce_pct']}% "
                                  f"({ctrl['ctrl_min']}-{ctrl['ctrl_max']})  edge {row.get('edge_pts')} pts"
                                  if ctrl else "  | no control (daily line on intraday candles)")]
                    report += ["   after k touches:"] + _fmt_table(touch_table(ep))
                    for by in SPLITS:
                        report += [f"   by {by}:"] + _fmt_table(split_table(ep, by, ctrl_eps))
        progress(f"{tf}: done ({time.perf_counter() - t_tf:.1f} s)")

    progress(f"all done - total {time.perf_counter() - t0:.0f} s")
    head = ["SUMMARY (one row per timeframe x line x touch mode; few_cases = fewer than "
            f"{MIN_CASES} resolved episodes)", ""] + _fmt_table(pd.DataFrame(summary))
    episodes = pd.concat(all_eps, ignore_index=True) if all_eps else pd.DataFrame()
    return episodes, head + report


def main() -> None:
    from dotenv import load_dotenv

    from modules.market_data.upstox.indicator_ohlcv_reader import read_for_indicators

    load_dotenv()
    logging.basicConfig(level=logging.WARNING,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description="EMA S&R study on stored candles (read-only).")
    parser.add_argument("--key", default=NIFTY_KEY)
    parser.add_argument("--daily-domain", default="indices", choices=["indices", "universe"])
    parser.add_argument("--timeframes", nargs="+", default=list(TIMEFRAMES), choices=list(TIMEFRAMES))
    parser.add_argument("--shuffles", type=int, default=DEFAULT_SHUFFLES,
                        help="random orders for the control (0 = no control)")
    args = parser.parse_args()

    backend_dir = Path(__file__).resolve().parents[4]
    log_dir = backend_dir / "logs" / "studies_logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    command = "python -m " + (__spec__.name if __spec__ else Path(__file__).stem) + " " + " ".join(sys.argv[1:])

    progress_path = log_dir / "ema_sr_study_progress.log"
    with open(progress_path, "w", encoding="utf-8") as progress_file:
        def progress(msg: str) -> None:
            line = f"{datetime.now():%H:%M:%S}  {msg}"
            print(line, flush=True)
            progress_file.write(line + "\n")
            progress_file.flush()

        progress(command.strip())
        started = datetime.now()
        episodes, lines = run_study(read_for_indicators, args.key, args.timeframes, args.shuffles,
                                    args.daily_domain, progress)

    text = "\n".join([command.strip(),
                      f"EMA S&R study, run at {started:%Y-%m-%d %H:%M:%S}, took "
                      f"{(datetime.now() - started).total_seconds():.0f} s",
                      f"instrument {args.key}; X = average candle move over {DEFAULT_X_WINDOW} candles; "
                      f"control = {args.shuffles} random orders of the same candles; "
                      "conditions measured on the candle before the touch; "
                      "trend = EMA stack stage (support with stage > 0, resistance with stage < 0)", ""] + lines)
    (log_dir / "ema_sr_study.log").write_text(text + "\n", encoding="utf-8")
    if not episodes.empty:
        episodes.to_csv(log_dir / "ema_sr_episodes.csv", index=False)
    print(f"Log saved to: {log_dir / 'ema_sr_study.log'}")
    print(f"Progress log: {progress_path}")
    print(f"Episodes saved to: {log_dir / 'ema_sr_episodes.csv'} ({len(episodes):,} rows)")


if __name__ == "__main__":
    sys.exit(main())
