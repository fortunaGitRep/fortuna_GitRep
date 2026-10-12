"""
modules/Module_F_Tech_Indicators_Funnel/trend_indicators/macd/macd_snapshot.py

MACD part 4: the "where we stand" package for one instrument, per timeframe
(1M, 1W, 1D, 60m, 15m, 5m) -- the TradingView numbers, the combined label, trend /
momentum / histogram states, events on the latest candle, alerts and plain-English
texts -- plus one summary line across timeframes. JSON-safe (no NaN, ISO dates),
ready for the API / frontend.

macd.py does the maths; this file turns its results into what Ash reads. Texts are
fixed templates (no AI), so the same data always gives the same words.
Rules: Fortuna Indicators / MACD.md (sections 5-9).

Entry points:
  - snapshot_from_bars(bars, name, timeframe, directions)   pure, no I/O, one timeframe
  - summary_line(snapshots)                                  pure, one line across timeframes
  - build_macd_snapshot(key, name, timeframes, directions)
        reads each timeframe via indicator_ohlcv_reader, then snapshot_from_bars.
        NEVER raises: every timeframe comes back ok or with a plain reason.

Display rule (Ash): every number TradingView shows (MACD, signal, histogram and its
colour) is shown; labels, held counts and texts are extra on top, never instead.

`directions`: "both" (Nifty: calls and puts) or "above" (stocks: bullish only). It
filters which events become texts / alerts; states and labels are always included.
Bullish events: MACD crosses above signal or zero; momentum turns to "bearish
fading" or "bullish growing". Bearish events are the mirror.

Data date: "as of" the latest stored candle of each timeframe. The latest weekly /
monthly candle is the running week / month ("week to date" / "month to date").
Indicators never fetch data -- Fortuna's refresh step does.

Standards applied: single responsibility (assembly + wording only), pure core,
never-raise boundary with one log line per timeframe outcome, JSON-safe output,
unit tests (test_macd_snapshot.py).
Deferred: strong/weak verdicts (no thresholds adopted -- MACD.md section 8); divergence.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Any, Optional

import pandas as pd

from modules.Module_F_Tech_Indicators_Funnel.trend_indicators.macd.macd import (
    _DEFAULT_DOMAIN,
    HIST_COLOUR,
    LABEL_NA,
    macd_all,
)

logger = logging.getLogger(__name__)

TIMEFRAMES = ("1mo", "1w", "1d", "60m", "15m", "5m")      # longest first
TF_NAME = {"1mo": "1M", "1w": "1W", "1d": "1D", "60m": "60m", "15m": "15m", "5m": "5m"}
DIRECTIONS = ("both", "above")
RECENT_BARS = 5        # a cross is "recent" (holding line) for this many candles

_UNIT = {"1mo": "month", "1w": "week", "1d": "day"}       # intraday -> "candle"
_NOW = {"1mo": "This month", "1w": "This week", "1d": "Today"}
_PREV = {"1mo": "last month", "1w": "last week", "1d": "yesterday"}
_MOMENTUM = {
    "above_growing": "bullish momentum growing",
    "above_fading": "bullish momentum fading",
    "below_fading": "bearish momentum fading",
    "below_growing": "bearish momentum growing",
}
_WATCH = {"above_fading": "watch for a bearish MACD cross",
          "below_fading": "watch for a bullish MACD cross"}
_ZONE_MEANING = {
    ("above", "below_zero"): "early reversal sign (downtrend still in force)",
    ("above", "above_zero"): "uptrend resuming (continuation)",
    ("below", "above_zero"): "early top sign (uptrend still in force)",
    ("below", "below_zero"): "downtrend resuming (continuation)",
    ("above", "at_zero"): "at the zero line",
    ("below", "at_zero"): "at the zero line",
}
_BULLISH_TURN = {"below_fading", "above_growing"}           # turn *to* these = bullish
_BEFORE = {"above_growing": "growing bullish", "above_fading": "fading bullish",
           "below_growing": "growing bearish", "below_fading": "fading bearish"}


# --- small helpers ---------------------------------------------------------------

def _num(x: Any) -> Optional[float]:
    """JSON-safe float: NaN/None -> None."""
    if x is None:
        return None
    try:
        f = float(x)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) else f


def _int(x: Any) -> Optional[int]:
    f = _num(x)
    return None if f is None else int(f)


def _intraday(tf: str) -> bool:
    return tf in ("5m", "15m", "60m")


def _iso(x: Any, tf: str) -> Optional[str]:
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return None
    ts = pd.Timestamp(x)
    return ts.isoformat() if _intraday(tf) else ts.date().isoformat()


def _when(x: Any, tf: str, ref_year: int) -> str:
    """Human date for a candle: '9 Oct', '9 Oct 15:15', 'week of 5 Oct', 'Oct 2026'."""
    ts = pd.Timestamp(x)
    day = f"{ts.day} {ts:%b}" + ("" if ts.year == ref_year else f" {ts.year}")
    if tf == "1mo":
        return f"{ts:%b %Y}"
    if tf == "1w":
        return f"week of {day}"
    if _intraday(tf):
        return f"{day} {ts:%H:%M}"
    return day


def _units(n: int, tf: str) -> str:
    unit = _UNIT.get(tf, "candle")
    return f"{n} {unit}" + ("" if n == 1 else "s")


def _p(x: Optional[float]) -> str:
    return "n/a" if x is None else f"{x:,.2f}"


def _sp(x: Optional[float]) -> str:
    return "n/a" if x is None else f"{x:+,.2f}"


def _colour(state: Any) -> Optional[str]:
    return HIST_COLOUR.get(state) if isinstance(state, str) else None


def _side_word(x: Any) -> Optional[str]:
    v = _int(x)
    return None if v is None else {1: "above", -1: "below", 0: "on"}[v]


# --- pure core: one timeframe ---------------------------------------------------------

def snapshot_from_bars(
    bars: pd.DataFrame,
    name: str,
    timeframe: str,
    directions: str = "both",
    recent_bars: int = RECENT_BARS,
) -> dict:
    """
    Build the snapshot for one timeframe from its candles (ascending 'ts', with
    trade_date and close). Raises ValueError on empty bars or a bad timeframe /
    directions (callers use build_macd_snapshot, which never raises).
    """
    if timeframe not in TIMEFRAMES:
        raise ValueError(f"timeframe must be one of {TIMEFRAMES}, got {timeframe!r}")
    if directions not in DIRECTIONS:
        raise ValueError(f"directions must be one of {DIRECTIONS}, got {directions!r}")
    if bars is None or bars.empty:
        raise ValueError("no bars to build a snapshot from")

    tf = timeframe
    m = macd_all(bars)
    t = m.iloc[-1]
    y = m.iloc[-2] if len(m) >= 2 else None
    year = pd.Timestamp(t["ts"]).year
    partial = tf in ("1w", "1mo")
    bullish_only = directions == "above"
    now = _NOW.get(tf, "On this candle")
    prev_word = _PREV.get(tf, "previous candle")

    def vals(r) -> dict:
        state = r["macd_hist_state"] if isinstance(r["macd_hist_state"], str) else None
        return {"macd": _num(r["macd"]), "signal": _num(r["macd_signal"]),
                "histogram": _num(r["macd_hist"]), "hist_state": state,
                "colour": _colour(state), "ppo": _num(r["ppo"])}

    today, prev = vals(t), (vals(y) if y is not None else None)
    label = t["macd_label"]
    hist_state = today["hist_state"]
    hist_held = _int(t["hist_state_held"])

    trend = {"side": _side_word(t["trend_side"]), "held": _int(t["trend_held"]),
             "since": _iso(t["trend_since"], tf) if _num(t["trend_side"]) is not None else None,
             "from_start": bool(t["trend_from_start"])}
    momentum = {"side": _side_word(t["mom_side"]), "held": _int(t["mom_held"]),
                "since": _iso(t["mom_since"], tf) if _num(t["mom_side"]) is not None else None,
                "from_start": bool(t["mom_from_start"]), "gap": _num(t["mom_gap"])}

    # -- events on the latest candle -------------------------------------------------
    events: list[dict] = []
    if bool(t["signal_cross_above"]) or bool(t["signal_cross_below"]):
        d = "above" if bool(t["signal_cross_above"]) else "below"
        events.append({"type": "signal_cross", "direction": d, "zone": t["signal_cross_zone"],
                       "bullish": d == "above"})
    if bool(t["zero_cross_above"]) or bool(t["zero_cross_below"]):
        d = "above" if bool(t["zero_cross_above"]) else "below"
        events.append({"type": "zero_cross", "direction": d, "bullish": d == "above"})
    if bool(t["momentum_turn"]) and y is not None:
        events.append({"type": "momentum_turn", "from": prev["hist_state"], "to": hist_state,
                       "bullish": hist_state in _BULLISH_TURN})
    shown = [e for e in events if e["bullish"] or not bullish_only]
    alerts = [{"timeframe": tf, **e} for e in shown]

    # -- last events in history (for the record / frontend) -----------------------------
    def last(col: str) -> Optional[str]:
        hits = m.index[m[col].astype(bool)]
        return _iso(m.loc[hits[-1], "ts"], tf) if len(hits) else None

    last_events = {c: last(c) for c in ("zero_cross_above", "zero_cross_below",
                                         "signal_cross_above", "signal_cross_below",
                                         "momentum_turn")}

    # -- texts -----------------------------------------------------------------------
    texts: list[str] = []
    asof = _when(t["ts"], tf, year)
    head = f"{name} · {TF_NAME[tf]} — as of {asof}"
    head += f" ({_UNIT[tf]} to date)" if partial else (" candle" if _intraday(tf) else "")
    head += f": close {_p(_num(t['close']))}"
    texts.append(head)

    def vline(v: dict) -> str:
        c = f" ({v['colour']})" if v["colour"] else ""
        return (f"MACD {_p(v['macd'])} · Signal {_p(v['signal'])} · "
                f"Histogram {_p(v['histogram'])}{c}")

    line = vline(today)
    if prev is not None:
        line += f" [{prev_word}: {vline(prev)}]"
    texts.append(line)

    if label == LABEL_NA:
        texts.append(f"MACD {label}.")
    else:
        lab = label
        if hist_state and hist_held:
            lab += f" — {_MOMENTUM[hist_state]} ({_units(hist_held, tf)})"
            if hist_state in _WATCH:
                lab += f", {_WATCH[hist_state]}"
        texts.append(lab + ".")

    for e in shown:
        if e["type"] == "signal_cross":
            texts.append(f"{now}: MACD crossed {e['direction']} signal, "
                         f"{e['zone'].replace('_', ' ')} → {_ZONE_MEANING[(e['direction'], e['zone'])]}. "
                         f"Gap {_sp(momentum['gap'])}.")
        elif e["type"] == "zero_cross":
            way = "up" if e["direction"] == "above" else "down"
            texts.append(f"⚡ {now}: MACD crossed {e['direction']} zero → 12 EMA now "
                         f"{e['direction']} 26 EMA (trend turned {way}).")
        else:
            prev_held = _int(y["hist_state_held"]) or 0
            texts.append(f"⚡ Momentum turn: {_MOMENTUM[e['to']]} "
                         f"(histogram {_p(today['histogram'])} vs {_p(prev['histogram'])}) "
                         f"after {_units(prev_held, tf)} of {_BEFORE[e['from']]} momentum.")

    def holding(kind: str, side_key: str, held: Optional[int], since: Optional[str],
                from_start: bool, against: str, extra: str = "") -> None:
        side = (trend if kind == "trend" else momentum)[side_key]
        if held is None or not (2 <= held <= recent_bars) or from_start or side == "on":
            return
        if bullish_only and side != "above":
            return
        texts.append(f"MACD holding {side} {against} for {_units(held, tf)} "
                     f"(since {_when(since, tf, year)}){extra}.")

    holding("momentum", "side", momentum["held"], momentum["since"], momentum["from_start"],
            "signal", f", gap {_sp(momentum['gap'])}")
    holding("trend", "side", trend["held"], trend["since"], trend["from_start"], "zero")

    bigger = []
    for part, against in ((trend, "zero"), (momentum, "signal")):
        if part["held"] is None or part["held"] <= recent_bars or part["side"] == "on":
            continue
        start = " (start of data)" if part["from_start"] else ""
        bigger.append(f"MACD {part['side']} {against} since {_when(part['since'], tf, year)}"
                      f"{start} ({_units(part['held'], tf)})")
    if bigger:
        texts.append("Bigger picture: " + " · ".join(bigger) + ".")

    return {
        "instrument": name,
        "timeframe": tf,
        "directions": directions,
        "as_of": _iso(t["ts"], tf),
        "partial": partial,
        "previous": _iso(y["ts"], tf) if y is not None else None,
        "close": {"today": _num(t["close"]),
                  "previous": _num(y["close"]) if y is not None else None},
        "values": {"today": today, "previous": prev},
        "label": label,
        "trend": trend,
        "momentum": momentum,
        "histogram": {"state": hist_state, "colour": today["colour"], "held": hist_held,
                      "meaning": _MOMENTUM.get(hist_state) if hist_state else None},
        "events_today": events,
        "last_events": last_events,
        "alerts": alerts,
        "texts": texts,
    }


def summary_line(snapshots: dict) -> str:
    """'MACD: 1M uptrend pausing · 1W strong downtrend · 1D strong downtrend (fading) ...'"""
    parts = []
    for tf in TIMEFRAMES:
        if tf not in snapshots:
            continue
        snap = snapshots[tf]
        if snap is None:
            parts.append(f"{TF_NAME[tf]} n/a")
            continue
        word = snap["label"].lower() if snap["label"] != LABEL_NA else "n/a"
        state = snap["histogram"]["state"] or ""
        if state.endswith("fading"):
            word += " (fading)"
        parts.append(f"{TF_NAME[tf]} {word}")
    return "MACD: " + " · ".join(parts)


# --- never-raise entry point ----------------------------------------------------------

@dataclass
class MacdSnapshotResult:
    ok: bool                       # True only if every requested timeframe built
    instrument_key: str
    snapshots: dict = field(default_factory=dict)    # timeframe -> snapshot dict or None
    errors: dict = field(default_factory=dict)       # timeframe -> plain reason
    summary: Optional[str] = None


def build_macd_snapshot(
    instrument_key: str,
    name: str,
    timeframes: tuple[str, ...] = TIMEFRAMES,
    directions: str = "both",
) -> MacdSnapshotResult:
    """
    Read each timeframe and build its snapshot. Never raises; one log line per
    timeframe outcome. A timeframe that can't be read or built is None in
    `snapshots` with its reason in `errors`; the others still come back.
    """
    from modules.market_data.upstox.indicator_ohlcv_reader import read_for_indicators

    result = MacdSnapshotResult(ok=True, instrument_key=instrument_key)
    for tf in timeframes:
        try:
            if tf not in TIMEFRAMES:
                raise ValueError(f"timeframe must be one of {TIMEFRAMES}, got {tf!r}")
            read = read_for_indicators(instrument_key, _DEFAULT_DOMAIN[tf], tf)  # never raises
            if not read.ok:
                logger.warning("MACD snapshot %s not built for %s: %s", tf, instrument_key,
                               read.error)
                result.snapshots[tf], result.errors[tf] = None, read.error
                continue
            snap = snapshot_from_bars(read.df, name, tf, directions)
        except Exception as exc:  # boundary: a pre-market run must not crash
            error = f"could not build MACD snapshot ({type(exc).__name__}: {exc})"
            logger.exception("MACD snapshot %s failed for %s: %s", tf, instrument_key, error)
            result.snapshots[tf], result.errors[tf] = None, error
            continue
        logger.info("MACD snapshot ok for %s (%s): as of %s, %s, %d alert(s).",
                    instrument_key, tf, snap["as_of"], snap["label"], len(snap["alerts"]))
        result.snapshots[tf] = snap
    result.ok = not result.errors
    result.summary = summary_line(result.snapshots)
    return result


# --- manual check -----------------------------------------------------------------

if __name__ == "__main__":
    #   python -m modules.Module_F_Tech_Indicators_Funnel.trend_indicators.macd.macd_snapshot
    #   ... macd_snapshot --timeframes 1d 60m --directions above --json
    # Output goes to the screen AND to logs/macd_test_logs/macd_snapshot.log
    # (overwritten each run).
    import argparse
    import json
    from pathlib import Path

    from dotenv import load_dotenv

    parser = argparse.ArgumentParser(description="Build the MACD snapshot (read-only).")
    parser.add_argument("--key", default="NSE_INDEX|Nifty 50")
    parser.add_argument("--name", default="Nifty 50")
    parser.add_argument("--timeframes", nargs="+", default=list(TIMEFRAMES),
                        choices=list(TIMEFRAMES))
    parser.add_argument("--directions", default="both", choices=DIRECTIONS)
    parser.add_argument("--json", action="store_true", help="also print the full package")
    args = parser.parse_args()

    load_dotenv()
    log_path = Path("logs") / "macd_test_logs" / "macd_snapshot.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[logging.FileHandler(log_path, mode="w", encoding="utf-8"),
                  logging.StreamHandler()],
    )
    out = logging.getLogger("macd_snapshot_check")
    out.info("command: macd_snapshot --timeframes %s --directions %s --key %s%s",
             " ".join(args.timeframes), args.directions, args.key,
             " --json" if args.json else "")

    res = build_macd_snapshot(args.key, args.name, tuple(args.timeframes), args.directions)
    out.info("=" * 96)
    for tf in args.timeframes:
        snap = res.snapshots.get(tf)
        if snap is None:
            out.warning("%s NOT OK -- %s", TF_NAME[tf], res.errors.get(tf))
        else:
            for line in snap["texts"]:
                out.info(line)
            out.info("alerts: %s", snap["alerts"] or "none")
        out.info("-" * 96)
    out.info(res.summary)
    out.info("=" * 96)
    if args.json:
        out.info(json.dumps({"summary": res.summary, "snapshots": res.snapshots,
                             "errors": res.errors}, indent=2, ensure_ascii=False))
    out.info("log written to %s", log_path)
