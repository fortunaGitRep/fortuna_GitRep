"""
modules/Module_F_Tech_Indicators_Funnel/trend_indicators/adx/adx_snapshot.py

ADX part 3: the "where we stand" package for one instrument, per timeframe
(1M, 1W, 1D, 60m, 15m, 5m) -- the five TradingView DMI numbers, the label, strength
band, ADX slope, +DI/-DI direction, events on the latest candle, alerts and
plain-English texts -- plus one summary line across timeframes. JSON-safe.

adx.py does the maths; this file turns it into what Ash reads. Fixed templates (no
AI): same data -> same words. Rules: Fortuna Indicators / ADX.md.

Entry points:
  - snapshot_from_bars(bars, name, timeframe, directions)   pure, one timeframe
  - summary_line(snapshots)                                  pure, one line
  - build_adx_snapshot(key, name, timeframes, directions)    never raises

Display rule (Ash): all five TradingView DMI numbers (+DI, -DI, DX, ADX, ADXR) are
shown; labels / texts are extra, never instead.

DI-cross tag (Ash, 2026-10-12): every +DI/-DI cross is tagged with the ADX at that
moment and its band ("ADX 10.7 -- no trend, weak signal" ... "ADX 31.2 -- trending,
meaningful"), because DI crosses while ADX is low are mostly chop (Nifty daily
May-Jul 2026: 11 crosses, all with ADX below 22). A fact tag, not a filter.

`directions`: "both" (Nifty) or "above" (stocks: bullish only). Bullish events:
+DI crosses above -DI; ADX crosses above 25 while bulls lead; ADX crosses below 25
while bears lead (a downtrend fading). Bearish events are the mirror.

Data date: "as of" the latest stored candle; weekly / monthly = "to date".

Standards applied: single responsibility (assembly + wording), pure core,
never-raise boundary with one log line per timeframe, JSON-safe output, unit tests
(test_adx_snapshot.py). Shared helpers (2026-10-12): the run helper, timeframe
words (_NOW, _PREV, _UNIT -- previously repeated here) and formatting helpers come
from ../../indicator_common/; this file no longer imports from macd/.
Deferred: strong/weak verdicts beyond the conventional bands (to test on Nifty);
"ADX turning down from above 40" (trend exhaustion) -- candidate, not built.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd

from modules.Module_F_Tech_Indicators_Funnel.indicator_common.crosses import runs as _runs
from modules.Module_F_Tech_Indicators_Funnel.indicator_common.text_format import (
    iso as _iso,
    num as _num,
    price as _p,
    to_int as _int,
    units as _units,
    when as _when,
)
from modules.Module_F_Tech_Indicators_Funnel.indicator_common.timeframes import (
    NOW as _NOW,
    PREV as _PREV,
    TF_NAME,
    TIMEFRAMES,
    UNIT as _UNIT,
    is_intraday as _intraday,
)
from modules.Module_F_Tech_Indicators_Funnel.trend_indicators.adx.adx import (
    _DEFAULT_DOMAIN,
    LABEL_NA,
    LEVEL,
    adx_all,
)

logger = logging.getLogger(__name__)

DIRECTIONS = ("both", "above")
RECENT_BARS = 5
BAND_WORDS = {
    "no_trend": "no trend, weak signal",
    "forming": "trend forming",
    "trending": "trending, meaningful",
    "strong": "strong trend, meaningful",
    "very_strong": "very strong trend (often late in the move)",
}
_BAND_SHORT = {"no_trend": "no trend", "forming": "trend forming", "trending": "trending",
               "strong": "strong trend", "very_strong": "very strong trend"}
_WHO = {1: "bulls (+DI above -DI)", -1: "bears (-DI above +DI)", 0: "+DI = -DI"}


def _tag(adx: Optional[float], band: Optional[str]) -> str:
    if adx is None or not isinstance(band, str):
        return "ADX n/a"
    return f"ADX {adx:.2f} — {BAND_WORDS[band]}"


def snapshot_from_bars(
    bars: pd.DataFrame,
    name: str,
    timeframe: str,
    directions: str = "both",
    recent_bars: int = RECENT_BARS,
) -> dict:
    """Build one timeframe's snapshot from its candles (ascending 'ts', high/low/close).
    Raises ValueError on empty bars or bad timeframe / directions."""
    if timeframe not in TIMEFRAMES:
        raise ValueError(f"timeframe must be one of {TIMEFRAMES}, got {timeframe!r}")
    if directions not in DIRECTIONS:
        raise ValueError(f"directions must be one of {DIRECTIONS}, got {directions!r}")
    if bars is None or bars.empty:
        raise ValueError("no bars to build a snapshot from")

    tf = timeframe
    a = adx_all(bars)
    # ADX above / below 25 as a run (for "ADX above 25 since ...")
    level_side = np.sign(a["adx"] - LEVEL).replace(0, 1)       # exactly 25 counts as above
    lvl_held, lvl_since, lvl_from_start = _runs(level_side, a["ts"])

    t = a.iloc[-1]
    y = a.iloc[-2] if len(a) >= 2 else None
    year = pd.Timestamp(t["ts"]).year
    partial = tf in ("1w", "1mo")
    bullish_only = directions == "above"
    now = _NOW.get(tf, "On this candle")

    def vals(r) -> dict:
        return {"plus_di": _num(r["plus_di"]), "minus_di": _num(r["minus_di"]),
                "dx": _num(r["dx"]), "adx": _num(r["adx"]), "adxr": _num(r["adxr"])}

    today, prev = vals(t), (vals(y) if y is not None else None)
    band = t["adx_band"] if isinstance(t["adx_band"], str) else None
    slope = _int(t["adx_slope"])
    di_side = _int(t["di_side"])

    direction = {"side": {1: "bulls", -1: "bears", 0: "equal"}.get(di_side) if di_side is not None else None,
                 "held": _int(t["di_held"]),
                 "since": _iso(t["di_since"], tf) if di_side is not None else None,
                 "from_start": bool(t["di_from_start"])}
    strength = {"adx": today["adx"], "band": band,
                "slope": {1: "rising", -1: "falling", 0: "flat"}.get(slope) if slope is not None else None,
                "slope_held": _int(t["adx_slope_held"]),
                "above_25": None if today["adx"] is None else today["adx"] >= LEVEL,
                "level_held": _int(lvl_held.iloc[-1]),
                "level_since": _iso(lvl_since.iloc[-1], tf) if today["adx"] is not None else None,
                "level_from_start": bool(lvl_from_start.iloc[-1])}

    # -- events on the latest candle -------------------------------------------------
    events: list[dict] = []
    if bool(t["di_cross_above"]) or bool(t["di_cross_below"]):
        d = "above" if bool(t["di_cross_above"]) else "below"
        events.append({"type": "di_cross", "direction": d, "adx": today["adx"], "band": band,
                       "bullish": d == "above"})
    if bool(t["adx_cross_above_25"]):
        events.append({"type": "adx_cross_25", "direction": "above", "di_side": di_side,
                       "bullish": di_side == 1})
    if bool(t["adx_cross_below_25"]):
        events.append({"type": "adx_cross_25", "direction": "below", "di_side": di_side,
                       "bullish": di_side == -1})
    shown = [e for e in events if e["bullish"] or not bullish_only]
    alerts = [{"timeframe": tf, **e} for e in shown]

    def last(col: str) -> Optional[str]:
        hits = a.index[a[col].astype(bool)]
        return _iso(a.loc[hits[-1], "ts"], tf) if len(hits) else None

    last_events = {c: last(c) for c in ("di_cross_above", "di_cross_below",
                                         "adx_cross_above_25", "adx_cross_below_25")}

    # -- texts -----------------------------------------------------------------------
    texts: list[str] = []
    head = f"{name} · {TF_NAME[tf]} DMI — as of {_when(t['ts'], tf, year)}"
    head += f" ({_UNIT[tf]} to date)" if partial else (" candle" if _intraday(tf) else "")
    head += f": close {_p(_num(t['close']))}"
    texts.append(head)

    def vline(v: dict) -> str:
        return (f"+DI {_p(v['plus_di'])} · -DI {_p(v['minus_di'])} · DX {_p(v['dx'])} · "
                f"ADX {_p(v['adx'])} · ADXR {_p(v['adxr'])}")

    line = vline(today)
    if prev is not None:
        line += f" [{_PREV.get(tf, 'previous candle')}: {vline(prev)}]"
    texts.append(line)

    label = t["adx_label"]
    if label == LABEL_NA:
        texts.append(f"ADX {label}.")
    else:
        parts = [label]
        if strength["slope"] and strength["slope_held"]:
            parts.append(f"ADX {today['adx']:.2f} {strength['slope']} for "
                         f"{_units(strength['slope_held'], tf)}")
        if di_side is not None:
            who = _WHO[di_side]
            if direction["held"] and di_side != 0:
                start = " (start of data)" if direction["from_start"] else ""
                who += f" since {_when(t['di_since'], tf, year)}{start}"
            parts.append(who if band != "no_trend" else who + " (but no trend)")
        texts.append(" — ".join(parts[:2]) + ("; " + parts[2] if len(parts) > 2 else "") + ".")

    for e in shown:
        if e["type"] == "di_cross":
            side = "bulls take over" if e["direction"] == "above" else "bears take over"
            texts.append(f"{now}: +DI crossed {e['direction']} -DI → {side}. "
                         f"{_tag(e['adx'], e['band'])}.")
        elif e["direction"] == "above":
            way = {1: "up, bulls in control", -1: "down, bears in control"}.get(e["di_side"], "no direction")
            texts.append(f"⚡ {now}: ADX crossed above 25 → trend confirmed ({way}).")
        else:
            texts.append(f"⚡ {now}: ADX crossed below 25 → trend fading.")

    held = direction["held"]
    if (held is not None and 2 <= held <= recent_bars and not direction["from_start"]
            and di_side in (1, -1) and not (bullish_only and di_side != 1)):
        cross_row = a.iloc[len(a) - held]
        texts.append(f"{direction['side'].capitalize()} holding for {_units(held, tf)} "
                     f"(since {_when(t['di_since'], tf, year)}); crossed with "
                     f"{_tag(_num(cross_row['adx']), cross_row['adx_band'])}; "
                     f"now ADX {_p(today['adx'])}.")

    bigger = []
    lvl = strength["level_held"]
    if today["adx"] is not None and lvl is not None and lvl > recent_bars:
        where = "above" if strength["above_25"] else "below"
        start = " (start of data)" if strength["level_from_start"] else ""
        bigger.append(f"ADX {where} 25 since {_when(lvl_since.iloc[-1], tf, year)}{start} "
                      f"({_units(lvl, tf)})")
    if held is not None and held > recent_bars and di_side in (1, -1):
        start = " (start of data)" if direction["from_start"] else ""
        bigger.append(f"{direction['side']} since {_when(t['di_since'], tf, year)}{start} "
                      f"({_units(held, tf)})")
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
        "strength": strength,
        "direction": direction,
        "events_today": events,
        "last_events": last_events,
        "alerts": alerts,
        "texts": texts,
    }


def summary_line(snapshots: dict) -> str:
    """'ADX: 1M trending down (rising) · 1W no trend (rising) · 1D strong trend down (rising) ...'"""
    parts = []
    for tf in TIMEFRAMES:
        if tf not in snapshots:
            continue
        snap = snapshots[tf]
        if snap is None or snap["label"] == LABEL_NA:
            parts.append(f"{TF_NAME[tf]} n/a")
            continue
        slope = snap["strength"]["slope"]
        parts.append(f"{TF_NAME[tf]} {snap['label'].lower()}" + (f" ({slope})" if slope else ""))
    return "ADX: " + " · ".join(parts)


@dataclass
class AdxSnapshotResult:
    ok: bool
    instrument_key: str
    snapshots: dict = field(default_factory=dict)
    errors: dict = field(default_factory=dict)
    summary: Optional[str] = None


def build_adx_snapshot(
    instrument_key: str,
    name: str,
    timeframes: tuple[str, ...] = TIMEFRAMES,
    directions: str = "both",
) -> AdxSnapshotResult:
    """Read each timeframe and build its snapshot. Never raises; a failed timeframe is
    None with a reason in `errors`; the others still come back."""
    from modules.market_data.upstox.indicator_ohlcv_reader import read_for_indicators

    result = AdxSnapshotResult(ok=True, instrument_key=instrument_key)
    for tf in timeframes:
        try:
            if tf not in TIMEFRAMES:
                raise ValueError(f"timeframe must be one of {TIMEFRAMES}, got {tf!r}")
            read = read_for_indicators(instrument_key, _DEFAULT_DOMAIN[tf], tf)
            if not read.ok:
                logger.warning("ADX snapshot %s not built for %s: %s", tf, instrument_key, read.error)
                result.snapshots[tf], result.errors[tf] = None, read.error
                continue
            snap = snapshot_from_bars(read.df, name, tf, directions)
        except Exception as exc:  # boundary: a pre-market run must not crash
            error = f"could not build ADX snapshot ({type(exc).__name__}: {exc})"
            logger.exception("ADX snapshot %s failed for %s: %s", tf, instrument_key, error)
            result.snapshots[tf], result.errors[tf] = None, error
            continue
        logger.info("ADX snapshot ok for %s (%s): as of %s, %s, %d alert(s).",
                    instrument_key, tf, snap["as_of"], snap["label"], len(snap["alerts"]))
        result.snapshots[tf] = snap
    result.ok = not result.errors
    result.summary = summary_line(result.snapshots)
    return result


if __name__ == "__main__":
    #   python -m modules.Module_F_Tech_Indicators_Funnel.trend_indicators.adx.adx_snapshot
    #   ... adx_snapshot --timeframes 1d 60m --directions above --json
    # Output goes to the screen AND to logs/adx_test_logs/adx_snapshot.log (overwritten).
    import argparse
    import json
    from pathlib import Path

    from dotenv import load_dotenv

    parser = argparse.ArgumentParser(description="Build the ADX snapshot (read-only).")
    parser.add_argument("--key", default="NSE_INDEX|Nifty 50")
    parser.add_argument("--name", default="Nifty 50")
    parser.add_argument("--timeframes", nargs="+", default=list(TIMEFRAMES), choices=list(TIMEFRAMES))
    parser.add_argument("--directions", default="both", choices=DIRECTIONS)
    parser.add_argument("--json", action="store_true", help="also print the full package")
    args = parser.parse_args()

    load_dotenv()
    log_path = Path("logs") / "adx_test_logs" / "adx_snapshot.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[logging.FileHandler(log_path, mode="w", encoding="utf-8"),
                  logging.StreamHandler()],
    )
    out = logging.getLogger("adx_snapshot_check")
    out.info("command: adx_snapshot --timeframes %s --directions %s --key %s%s",
             " ".join(args.timeframes), args.directions, args.key, " --json" if args.json else "")

    res = build_adx_snapshot(args.key, args.name, tuple(args.timeframes), args.directions)
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
