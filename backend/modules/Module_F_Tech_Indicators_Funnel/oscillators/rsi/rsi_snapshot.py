"""
modules/Module_F_Tech_Indicators_Funnel/oscillators/rsi/rsi_snapshot.py

RSI part 3: the "where we stand" package for one instrument, per timeframe
(1M, 1W, 1D, 60m, 15m, 5m) -- the TradingView RSI value, the zone label, how long in
the zone, side of 50, rising / falling, events on the latest candle, alerts and
plain-English texts -- plus one summary line across timeframes. JSON-safe.

rsi.py does the maths and the zone-change wording (zone_change_text); this file turns
it into what Ash reads. Fixed templates (no AI): same data -> same words.
Rules: Fortuna Indicators / RSI.md.

Entry points:
  - snapshot_from_bars(bars, name, timeframe)          pure, one timeframe
  - summary_line(snapshots)                            pure, one line
  - build_rsi_snapshot(key, name, timeframes)          never raises

Decisions (Ash, 2026-10-13):
  - Alerts: EVERY zone change and EVERY RSI cross of 50 on the latest candle, on all six
    timeframes, both directions, index and stocks alike -- no directions filter.
  - RSI crossing its Smoothed MA is not shown and not alerted (the MA line is off on
    Ash's chart); it stays in rsi_states for the later testing phase, and is not put in
    the package either (one candle's value is no use to a history test).
  - Dates read like a report, always with the year: 'Fri 9 Oct 2026' (1D),
    'Fri 9 Oct 2026 15:25' (intraday), 'Week of Mon 5 Oct 2026' (1W), 'Oct 2026' (1M);
    the running week / month is marked '(week to date)' / '(month to date)'.

Display rule: the one number TradingView shows (RSI) is shown; labels and texts are
extra, never instead.

Standards applied: single responsibility (assembly + wording), pure core, never-raise
boundary with one log line per timeframe, JSON-safe output, unit tests
(test_rsi_snapshot.py).
Deferred: the ~55 support / resistance study (needs price S&R first); final text
layout to be revisited when the frontend is built.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

import pandas as pd

from modules.Module_F_Tech_Indicators_Funnel.indicator_common.text_format import (
    iso,
    num,
    report_date,
    to_int,
    units,
)
from modules.Module_F_Tech_Indicators_Funnel.indicator_common.timeframes import (
    DEFAULT_DOMAIN,
    PREV,
    TF_NAME,
    TIMEFRAMES,
    UNIT,
)
from modules.Module_F_Tech_Indicators_Funnel.oscillators.rsi.rsi import (
    LABEL_NA,
    ZONE_LABEL,
    rsi_all,
    zone_change_text,
)

logger = logging.getLogger(__name__)

RECENT_BARS = 5          # zone change 2..5 candles old -> "holding" line; older -> bigger picture
_SLOPE = {1: "rising", -1: "falling", 0: "flat"}
_SIDE50 = {1: "above 50", -1: "below 50", 0: "at 50"}
_ZONE_SHORT = {          # summary line words
    "overbought": "overbought", "strong_bull": "strong bull", "bullish": "bullish",
    "sr_zone": "S&R zone", "bearish": "bearish", "strong_bear": "strong bear",
    "oversold": "oversold",
}


def _when(ts, tf: str, latest: bool = False) -> str:
    """Report date; the running week / month (latest candle only) gets 'to date'."""
    text = report_date(ts, tf)
    if latest and tf in ("1w", "1mo"):
        text += f" ({UNIT[tf]} to date)"
    return text


def snapshot_from_bars(bars: pd.DataFrame, name: str, timeframe: str,
                       recent_bars: int = RECENT_BARS) -> dict:
    """Build one timeframe's snapshot from its candles (ascending 'ts', with close).
    Raises ValueError on empty bars or a bad timeframe (build_rsi_snapshot never raises)."""
    if timeframe not in TIMEFRAMES:
        raise ValueError(f"timeframe must be one of {TIMEFRAMES}, got {timeframe!r}")
    if bars is None or bars.empty:
        raise ValueError("no bars to build a snapshot from")

    tf = timeframe
    a = rsi_all(bars)
    t = a.iloc[-1]
    y = a.iloc[-2] if len(a) >= 2 else None
    partial = tf in ("1w", "1mo")
    now = _when(t["ts"], tf, latest=True)

    rsi_t = num(t["rsi"])
    rsi_y = num(y["rsi"]) if y is not None else None
    zone = t["rsi_zone"] if isinstance(t["rsi_zone"], str) else None
    side50 = to_int(t["rsi_side50"])
    slope = to_int(t["rsi_slope"])

    zone_info = {"key": zone, "label": t["rsi_label"], "held": to_int(t["rsi_zone_held"]),
                 "since": iso(t["rsi_zone_since"], tf) if zone else None,
                 "from_start": bool(t["rsi_zone_from_start"])}
    side_info = {"side": {1: "above", -1: "below", 0: "at"}.get(side50) if side50 is not None else None,
                 "held": to_int(t["rsi_side50_held"]),
                 "since": iso(t["rsi_side50_since"], tf) if side50 is not None else None,
                 "from_start": bool(t["rsi_side50_from_start"])}
    slope_info = {"direction": _SLOPE.get(slope) if slope is not None else None,
                  "held": to_int(t["rsi_slope_held"])}

    # -- events on the latest candle: every one is an alert (both directions) -----------
    events: list[dict] = []
    if bool(t["zone_change"]):
        events.append({"type": "zone_change", "from": t["zone_from"], "to": zone,
                       "direction": "up" if t["zone_change_up"] else "down", "rsi": rsi_t,
                       "text": zone_change_text(t["rsi"], t["zone_from"], zone)})
    for col, d in (("rsi_cross_above_50", "above"), ("rsi_cross_below_50", "below")):
        if bool(t[col]):
            events.append({"type": "cross_50", "direction": d, "rsi": rsi_t,
                           "text": f"RSI {rsi_t:.2f} crossed {d.upper()} 50"})
    alerts = [{"timeframe": tf, **e} for e in events]

    def last(col: str) -> Optional[str]:
        hits = a.index[a[col].astype(bool)]
        return iso(a.loc[hits[-1], "ts"], tf) if len(hits) else None

    last_events = {c: last(c) for c in ("zone_change", "rsi_cross_above_50", "rsi_cross_below_50")}

    # -- texts -------------------------------------------------------------------------
    texts: list[str] = [f"{name} · {TF_NAME[tf]} RSI — {now}: close {num(t['close']):,.2f}"]

    line = f"RSI {rsi_t:.2f}" if rsi_t is not None else "RSI n/a"
    if y is not None:
        line += f" [{PREV.get(tf, 'previous candle')}: RSI " + \
                (f"{rsi_y:.2f}]" if rsi_y is not None else "n/a]")
    texts.append(line)

    if zone is None:
        texts.append(f"RSI {LABEL_NA}.")
    else:
        parts = [t["rsi_label"]]
        detail = []
        if slope_info["direction"] and slope_info["held"]:
            detail.append(f"RSI {rsi_t:.2f} {slope_info['direction']} for "
                          f"{units(slope_info['held'], tf)}")
        if side50 is not None:
            start = " (start of data)" if side_info["from_start"] else ""
            detail.append(f"{_SIDE50[side50]} since {_when(t['rsi_side50_since'], tf)}{start} "
                          f"({units(side_info['held'], tf)})")
        if detail:
            parts.append("; ".join(detail))
        texts.append(" — ".join(parts) + ".")

    for e in events:
        texts.append(f"{now}: {e['text']}")

    held = zone_info["held"]
    if zone is not None and held is not None and 2 <= held <= recent_bars and not zone_info["from_start"]:
        came_from = a["zone_from"].iloc[len(a) - held]
        texts.append(f"In {t['rsi_label']} for {units(held, tf)} "
                     f"(since {_when(t['rsi_zone_since'], tf)}), came from {ZONE_LABEL[came_from]}.")
    elif zone is not None and held is not None and held > recent_bars:
        start = " (start of data)" if zone_info["from_start"] else ""
        texts.append(f"Bigger picture: in {t['rsi_label']} since "
                     f"{_when(t['rsi_zone_since'], tf)}{start} ({units(held, tf)}).")

    return {
        "instrument": name,
        "timeframe": tf,
        "as_of": iso(t["ts"], tf),
        "partial": partial,
        "previous": iso(y["ts"], tf) if y is not None else None,
        "close": {"today": num(t["close"]), "previous": num(y["close"]) if y is not None else None},
        "values": {"today": {"rsi": rsi_t}, "previous": {"rsi": rsi_y} if y is not None else None},
        "label": t["rsi_label"],
        "zone": zone_info,
        "side50": side_info,
        "slope": slope_info,
        "events_today": events,
        "last_events": last_events,
        "alerts": alerts,
        "texts": texts,
    }


def summary_line(snapshots: dict) -> str:
    """'RSI: 1M bearish 44.37 (falling) · 1W bearish 32.74 (rising) · ... · 5m bearish 44.95 (falling)'"""
    parts = []
    for tf in TIMEFRAMES:
        if tf not in snapshots:
            continue
        snap = snapshots[tf]
        if snap is None or snap["zone"]["key"] is None:
            parts.append(f"{TF_NAME[tf]} n/a")
            continue
        slope = snap["slope"]["direction"]
        parts.append(f"{TF_NAME[tf]} {_ZONE_SHORT[snap['zone']['key']]} "
                     f"{snap['values']['today']['rsi']:.2f}" + (f" ({slope})" if slope else ""))
    return "RSI: " + " · ".join(parts)


@dataclass
class RsiSnapshotResult:
    ok: bool                       # True only if every requested timeframe built
    instrument_key: str
    snapshots: dict = field(default_factory=dict)    # timeframe -> snapshot dict or None
    errors: dict = field(default_factory=dict)       # timeframe -> plain reason
    summary: Optional[str] = None


def build_rsi_snapshot(instrument_key: str, name: str,
                       timeframes: tuple[str, ...] = TIMEFRAMES) -> RsiSnapshotResult:
    """Read each timeframe and build its snapshot. Never raises; a failed timeframe is
    None with a reason in `errors`; the others still come back."""
    from modules.market_data.upstox.indicator_ohlcv_reader import read_for_indicators

    result = RsiSnapshotResult(ok=True, instrument_key=instrument_key)
    for tf in timeframes:
        try:
            if tf not in TIMEFRAMES:
                raise ValueError(f"timeframe must be one of {TIMEFRAMES}, got {tf!r}")
            read = read_for_indicators(instrument_key, DEFAULT_DOMAIN[tf], tf)   # never raises
            if not read.ok:
                logger.warning("RSI snapshot %s not built for %s: %s", tf, instrument_key, read.error)
                result.snapshots[tf], result.errors[tf] = None, read.error
                continue
            snap = snapshot_from_bars(read.df, name, tf)
        except Exception as exc:  # boundary: a pre-market run must not crash
            error = f"could not build RSI snapshot ({type(exc).__name__}: {exc})"
            logger.exception("RSI snapshot %s failed for %s: %s", tf, instrument_key, error)
            result.snapshots[tf], result.errors[tf] = None, error
            continue
        logger.info("RSI snapshot ok for %s (%s): as of %s, %s, %d alert(s).",
                    instrument_key, tf, snap["as_of"], snap["label"], len(snap["alerts"]))
        result.snapshots[tf] = snap
    result.ok = not result.errors
    result.summary = summary_line(result.snapshots)
    return result


if __name__ == "__main__":
    #   python -m modules.Module_F_Tech_Indicators_Funnel.oscillators.rsi.rsi_snapshot
    #   ... rsi_snapshot --timeframes 1d 60m --json
    # Output goes to the screen AND to logs/rsi_test_logs/rsi_snapshot.log (overwritten;
    # first line = the command).
    import argparse
    import json
    from pathlib import Path

    from dotenv import load_dotenv

    parser = argparse.ArgumentParser(description="Build the RSI snapshot (read-only).")
    parser.add_argument("--key", default="NSE_INDEX|Nifty 50")
    parser.add_argument("--name", default="Nifty 50")
    parser.add_argument("--timeframes", nargs="+", default=list(TIMEFRAMES), choices=list(TIMEFRAMES))
    parser.add_argument("--json", action="store_true", help="also print the full package")
    args = parser.parse_args()

    load_dotenv()
    log_path = Path("logs") / "rsi_test_logs" / "rsi_snapshot.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[logging.FileHandler(log_path, mode="w", encoding="utf-8"),
                  logging.StreamHandler()],
    )
    out = logging.getLogger("rsi_snapshot_check")
    out.info("command: rsi_snapshot --timeframes %s --key %s%s", " ".join(args.timeframes),
             args.key, " --json" if args.json else "")

    res = build_rsi_snapshot(args.key, args.name, tuple(args.timeframes))
    out.info("=" * 96)
    for tf in args.timeframes:
        snap = res.snapshots.get(tf)
        if snap is None:
            out.warning("%s NOT OK -- %s", TF_NAME[tf], res.errors.get(tf))
        else:
            for line in snap["texts"]:
                out.info(line)
            out.info("alerts: %s", [a["text"] for a in snap["alerts"]] or "none")
        out.info("-" * 96)
    out.info(res.summary)
    out.info("=" * 96)
    if args.json:
        out.info(json.dumps({"summary": res.summary, "snapshots": res.snapshots,
                             "errors": res.errors}, indent=2, ensure_ascii=False))
    out.info("log written to %s", log_path)
