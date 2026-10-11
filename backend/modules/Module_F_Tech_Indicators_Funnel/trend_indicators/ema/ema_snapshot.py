"""
modules/Module_F_Tech_Indicators_Funnel/trend_indicators/ema/ema_snapshot.py

EMA part 4: the daily "where we stand" package for one instrument -- values, stage,
the 12 check states, today's crosses, alerts and plain-English texts -- ready for the
API / frontend (JSON-safe: no NaN, dates as ISO strings).

ema.py does the maths; this file turns its results into what Ash reads. Texts are
fixed templates (no AI), so the same data always gives the same words.
Rules are documented in Fortuna Indicators / EMA (spec doc).

Two entry points:
  - snapshot_from_bars(bars, name, directions)   pure, no I/O
  - build_ema_snapshot(key, domain, name, directions)
        reads via indicator_ohlcv_reader, then snapshot_from_bars. NEVER raises:
        returns SnapshotResult(ok, snapshot | error) so a pre-market run can't crash.

`directions`: "both" (Nifty: calls and puts) or "above" (stocks: cross-above only).
It filters which crosses become texts / alerts; the states of all 12 checks are
always included.

Data date: the snapshot is "as of" the latest stored bar. Fetching fresh candles
(before 4 pm: yesterday's; after 4 pm: today's) is done by Fortuna's data-refresh step
before indicators are called -- no indicator fetches data itself.

Standards applied: single responsibility (assembly + wording only), pure core,
never-raise boundary with one log line per outcome, JSON-safe output, unit tests
(test_ema_snapshot.py).
Deferred: strong/weak verdicts (thresholds not adopted -- see spec §7); volume.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Any, Optional

import pandas as pd

from modules.Module_F_Tech_Indicators_Funnel.trend_indicators.ema.ema import (
    DEFAULT_PERIODS,
    GOLDEN_DEATH_PAIR,
    STACK_PAIRS,
    check_states,
    compute_emas,
    default_cross_checks,
    detect_crosses,
    stack_stage,
)

logger = logging.getLogger(__name__)

RECENT_DAYS = 5          # a cross is "recent" (holding line) for this many trading days
DIRECTIONS = ("both", "above")
_GOLDEN = (f"ema_{GOLDEN_DEATH_PAIR[0]}", f"ema_{GOLDEN_DEATH_PAIR[1]}")
_STACK_COLS = [(f"ema_{a}", f"ema_{b}") for a, b in STACK_PAIRS]


# --- small helpers ------------------------------------------------------------

def _num(x: Any) -> Optional[float]:
    """JSON-safe float: NaN/None -> None."""
    if x is None:
        return None
    try:
        f = float(x)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) else f


def _iso(x: Any) -> Optional[str]:
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return None
    return pd.Timestamp(x).date().isoformat()


def _day(x: Any, ref_year: int) -> str:
    """'9 Oct' in the as-of year, '12 Sep 2023' otherwise."""
    ts = pd.Timestamp(x)
    return f"{ts.day} {ts:%b}" if ts.year == ref_year else f"{ts.day} {ts:%b} {ts.year}"


def _price(x: Optional[float]) -> str:
    return "n/a" if x is None else f"{x:,.2f}"


def _name(col: str) -> str:
    return "close" if col == "close" else col.replace("ema_", "") + " EMA"


def _the(col: str) -> str:
    return "close" if col == "close" else "the " + _name(col)


def stage_label(stage: Optional[float], top: int) -> str:
    if stage is None:
        return "STAGE n/a (not enough history)"
    s = int(stage)
    if s == 0:
        return "NEUTRAL (0)"
    trend = "UPTREND" if s > 0 else "DOWNTREND"
    if abs(s) == top:
        return f"STRONG {trend} ({s:+d} of {top})"
    if abs(s) == 1:
        return f"EARLY {trend} ({s:+d} of {top}, weakest)"
    return f"{trend} (stage {s:+d} of {top})"


def _stack_chain(row: pd.Series, periods: tuple[int, ...]) -> str:
    parts = [str(periods[0])]
    for a, b in zip(periods, periods[1:]):
        va, vb = _num(row[f"ema_{a}"]), _num(row[f"ema_{b}"])
        sym = "?" if va is None or vb is None else (">" if va > vb else "<" if va < vb else "=")
        parts += [sym, str(b)]
    return " ".join(parts)


# --- pure core ----------------------------------------------------------------

def snapshot_from_bars(
    bars: pd.DataFrame,
    name: str,
    directions: str = "both",
    recent_days: int = RECENT_DAYS,
) -> dict:
    """
    Build the snapshot from daily bars (ascending, with trade_date, open/high/low/close).
    Raises ValueError on empty bars or a bad `directions` (callers use build_ema_snapshot,
    which never raises).
    """
    if directions not in DIRECTIONS:
        raise ValueError(f"directions must be one of {DIRECTIONS}, got {directions!r}")
    if bars is None or bars.empty:
        raise ValueError("no bars to build a snapshot from")

    periods = DEFAULT_PERIODS
    top = len(periods) - 1
    checks = default_cross_checks(periods)

    emas = compute_emas(bars, periods)
    data = check_states(detect_crosses(emas, checks), checks)
    stages = stack_stage(emas, periods)

    t = data.iloc[-1]
    y = data.iloc[-2] if len(data) >= 2 else None
    year = pd.Timestamp(t["trade_date"]).year
    allowed = ("above", "below") if directions == "both" else ("above",)

    close_t = _num(t["close"])
    close_y = _num(y["close"]) if y is not None else None
    stage_t = _num(stages.iloc[-1])
    stage_y = _num(stages.iloc[-2]) if len(stages) >= 2 else None

    # -- structured parts ------------------------------------------------------
    ema_values = [{"period": p,
                   "today": _num(t[f"ema_{p}"]),
                   "yesterday": _num(y[f"ema_{p}"]) if y is not None else None}
                  for p in periods]

    check_rows, crosses_today = [], []
    for a, b in checks:
        tag = f"{a}_{b}"
        side = _num(t[f"side_{tag}"])
        crossed = ("above" if bool(t[f"cross_above_{tag}"])
                   else "below" if bool(t[f"cross_below_{tag}"]) else None)
        row = {
            "a": a, "b": b,
            "side": None if side is None else {1: "above", -1: "below", 0: "equal"}[int(side)],
            "held_days": None if _num(t[f"held_{tag}"]) is None else int(t[f"held_{tag}"]),
            "since": _iso(t[f"since_{tag}"]) if side is not None else None,
            "margin_pts": _num(t[f"margin_pts_{tag}"]),
            "margin_pct": _num(t[f"margin_pct_{tag}"]),
            "candle_clear": (bool(t[f"candle_clear_{tag}"])
                             if f"candle_clear_{tag}" in data.columns and side is not None else None),
            "crossed_today": crossed,
            "golden_death": (a, b) == _GOLDEN,
        }
        check_rows.append(row)
        if crossed:
            crosses_today.append(row)

    alerts = [{"a": r["a"], "b": r["b"], "direction": r["crossed_today"],
               "golden_cross": r["golden_death"] and r["crossed_today"] == "above",
               "death_cross": r["golden_death"] and r["crossed_today"] == "below"}
              for r in crosses_today if r["crossed_today"] in allowed]

    # -- texts -----------------------------------------------------------------
    texts: list[str] = []
    head = f"{name} — as of {_day(t['trade_date'], year)} close: {_price(close_t)}"
    if close_y is not None and close_t is not None:
        chg = close_t - close_y
        head += (f" ({_day(y['trade_date'], year)}: {_price(close_y)}, "
                 f"{chg:+,.2f} / {chg / close_y * 100:+.2f}%)")
    texts.append(head)

    texts.append(f"{stage_label(stage_t, top)}: {_stack_chain(t, periods)}")
    if stage_t is not None and stage_y is not None and int(stage_t) != int(stage_y):
        texts.append(f"Stage moved from {int(stage_y):+d} to {int(stage_t):+d} today.")

    texts.append("EMAs today (yesterday): " + " · ".join(
        f"{v['period']}: {_price(v['today'])} ({_price(v['yesterday'])})" for v in ema_values))

    for r in crosses_today:
        if r["crossed_today"] not in allowed:
            continue
        a, b, d = r["a"], r["b"], r["crossed_today"]
        if r["golden_death"]:
            lead = ("⚡ GOLDEN CROSS today: " if d == "above" else "⚡ DEATH CROSS today: ")
            body = f"{_name(a)} crossed {d} {_the(b)}"
        else:
            lead = "Today: "
            body = f"{_the(a)} crossed {d} {_the(b)}"
        line = (f"{lead}{body} — {_price(_num(t[a]))} vs {_price(_num(t[b]))}")
        if y is not None:
            line += f" (yesterday {_price(_num(y[a]))} vs {_price(_num(y[b]))})"
        line += f". Margin {r['margin_pts']:+,.2f} ({r['margin_pct']:+.3f}%)."
        if r["candle_clear"] is not None:
            line += f" Whole candle clear: {'yes' if r['candle_clear'] else 'no'}."
        texts.append(line)

    for r in check_rows:
        held = r["held_days"]
        if held is None or not (2 <= held <= recent_days) or r["side"] not in allowed:
            continue
        start = len(data) - held           # row where the current side began
        if start == 0 or pd.isna(data[f"side_{r['a']}_{r['b']}"].iloc[start - 1]):
            continue                      # side began with the history / first EMA value, not a cross
        gap = "now" if r["a"] == "close" else "gap"
        texts.append(f"{_the(r['a']).capitalize()} holding {r['side']} {_the(r['b'])} "
                     f"for {held} days (since {_day(r['since'], year)}), "
                     f"{gap} {r['margin_pct']:+.2f}%.")

    trend_parts = []
    for r in check_rows:
        if (r["a"], r["b"]) not in _STACK_COLS + [_GOLDEN] or r["held_days"] is None:
            continue
        if r["held_days"] <= recent_days or r["side"] == "equal":
            continue
        since = _day(r["since"], year)
        start = len(data) - r["held_days"]
        if start == 0 or pd.isna(data[f"side_{r['a']}_{r['b']}"].iloc[start - 1]):
            since += " (start of data)"
        if r["golden_death"]:
            kind = "golden cross" if r["side"] == "above" else "death cross"
            trend_parts.append(f"{kind} (50 {r['side']} 200) since {since}")
        else:
            trend_parts.append(f"{_name(r['a']).replace(' EMA', '')} {r['side']} "
                               f"{_name(r['b']).replace(' EMA', '')} since {since}")
    if trend_parts:
        texts.append("Bigger trend: " + " · ".join(trend_parts))

    return {
        "instrument": name,
        "directions": directions,
        "as_of": _iso(t["trade_date"]),
        "previous": _iso(y["trade_date"]) if y is not None else None,
        "close": {"today": close_t, "yesterday": close_y,
                  "change_pts": (close_t - close_y) if close_y is not None else None,
                  "change_pct": ((close_t - close_y) / close_y * 100) if close_y else None},
        "emas": ema_values,
        "stage": {"today": None if stage_t is None else int(stage_t),
                  "yesterday": None if stage_y is None else int(stage_y),
                  "label": stage_label(stage_t, top)},
        "checks": check_rows,
        "crosses_today": [{"a": r["a"], "b": r["b"], "direction": r["crossed_today"]}
                          for r in crosses_today],
        "alerts": alerts,
        "texts": texts,
    }


# --- never-raise entry point ----------------------------------------------------

@dataclass
class SnapshotResult:
    ok: bool
    instrument_key: str
    snapshot: Optional[dict] = None
    error: Optional[str] = None


def build_ema_snapshot(
    instrument_key: str,
    domain: str,
    name: str,
    directions: str = "both",
) -> SnapshotResult:
    """Read daily bars and build the snapshot. Never raises; one log line per outcome."""
    from modules.market_data.upstox.indicator_ohlcv_reader import read_for_indicators

    read = read_for_indicators(instrument_key, domain, "1d")   # never raises
    if not read.ok:
        logger.warning("EMA snapshot not built for %s: %s", instrument_key, read.error)
        return SnapshotResult(ok=False, instrument_key=instrument_key, error=read.error)
    try:
        snap = snapshot_from_bars(read.df, name, directions)
    except Exception as exc:  # boundary: a pre-market run must not crash
        error = f"could not build EMA snapshot ({type(exc).__name__}: {exc})"
        logger.exception("EMA snapshot failed for %s: %s", instrument_key, error)
        return SnapshotResult(ok=False, instrument_key=instrument_key, error=error)
    logger.info("EMA snapshot ok for %s: as of %s, stage %s, %d alert(s).",
                instrument_key, snap["as_of"], snap["stage"]["today"], len(snap["alerts"]))
    return SnapshotResult(ok=True, instrument_key=instrument_key, snapshot=snap)


# --- manual check -------------------------------------------------------------------

if __name__ == "__main__":
    #   python -m modules.Module_F_Tech_Indicators_Funnel.trend_indicators.ema.ema_snapshot [--json]
    import argparse
    import json

    from dotenv import load_dotenv

    load_dotenv()
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    parser = argparse.ArgumentParser(description="Build the EMA snapshot (read-only).")
    parser.add_argument("--key", default="NSE_INDEX|Nifty 50")
    parser.add_argument("--domain", default="indices")
    parser.add_argument("--name", default="Nifty 50")
    parser.add_argument("--directions", default="both", choices=DIRECTIONS)
    parser.add_argument("--json", action="store_true", help="also print the full package")
    args = parser.parse_args()

    res = build_ema_snapshot(args.key, args.domain, args.name, args.directions)
    print("\n" + "=" * 78)
    if not res.ok:
        print(f"NOT OK -- {res.error}")
    else:
        for line in res.snapshot["texts"]:
            print(line)
        print(f"\nalerts: {res.snapshot['alerts'] or 'none'}")
        if args.json:
            print("\n" + json.dumps(res.snapshot, indent=2, ensure_ascii=False))
    print("=" * 78 + "\n")
