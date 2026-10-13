"""
modules/Module_F_Tech_Indicators_Funnel/oscillators/stoch_rsi/stoch_rsi_snapshot.py

Stochastic RSI part 3: the "where we stand" package for one instrument, per timeframe
(1M, 1W, 1D, 60m, 15m, 5m) -- the TradingView %K and %D, the zone of %K, how long in the
zone, %K vs %D, rising / falling, pinned at 100 / 0, events on the latest candle, alerts
and plain-English texts -- plus one summary line across timeframes. JSON-safe.

stoch_rsi.py does the maths and the event wording (zone_change_text, kd_cross_text); this
file turns it into what Ash reads. Fixed templates (no AI): same data -> same words.
Same layout as rsi_snapshot.py. Rules: Fortuna Indicators / STOCH_RSI.md.

Entry points:
  - snapshot_from_bars(bars, name, timeframe)          pure, one timeframe
  - summary_line(snapshots)                            pure, one line
  - build_stoch_rsi_snapshot(key, name, timeframes)    never raises

Decisions (Ash, 2026-10-13):
  - Alerts: EVERY zone change of %K and EVERY %K/%D cross on the latest candle, on all six
    timeframes, both directions, index and stocks alike -- no directions filter.
  - %K equal to %D (e.g. both 100.00): shown as "%K equal to %D", no cross; the cross is
    reported on the candle where they separate (stoch_rsi.CROSS_TOL).
  - Dates read like a report, always with the year: 'Fri 9 Oct 2026' (1D),
    'Fri 9 Oct 2026 15:25' (intraday), 'Week of Mon 5 Oct 2026' (1W), 'Oct 2026' (1M);
    the running week / month is marked '(week to date)' / '(month to date)'.
  - Values print with fmt2, so TradingView's '-0.00' shows as '0.00'.

Display rule: the two numbers TradingView shows (%K, %D) are shown; labels and texts are
extra, never instead. The RSI it is built on and the unsmoothed value are not in the
package (they are checks only, see the stoch_rsi manual check).

Standards applied: single responsibility (assembly + wording), pure core, never-raise
boundary with one log line per timeframe, JSON-safe output, unit tests
(test_stoch_rsi_snapshot.py).
Deferred: final text layout to be revisited when the frontend is built.
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
from modules.Module_F_Tech_Indicators_Funnel.oscillators.stoch_rsi.stoch_rsi import (
    LABEL_NA,
    ZONE_LABEL,
    fmt2,
    kd_cross_text,
    srsi_all,
    zone_change_text,
)

logger = logging.getLogger(__name__)

RECENT_BARS = 5          # zone change 2..5 candles old -> "holding" line; older -> bigger picture
_SLOPE = {1: "rising", -1: "falling", 0: "flat"}
_KD_SIDE = {1: "above", -1: "below", 0: "equal"}
_KD_WORDS = {1: "%K above %D", -1: "%K below %D", 0: "%K equal to %D"}
_ZONE_SHORT = {"overbought": "overbought", "middle": "middle", "oversold": "oversold"}


def _when(ts, tf: str, latest: bool = False) -> str:
    """Report date; the running week / month (latest candle only) gets 'to date'."""
    text = report_date(ts, tf)
    if latest and tf in ("1w", "1mo"):
        text += f" ({UNIT[tf]} to date)"
    return text


def snapshot_from_bars(bars: pd.DataFrame, name: str, timeframe: str,
                       recent_bars: int = RECENT_BARS) -> dict:
    """Build one timeframe's snapshot from its candles (ascending 'ts', with close).
    Raises ValueError on empty bars or a bad timeframe (build_stoch_rsi_snapshot never raises)."""
    if timeframe not in TIMEFRAMES:
        raise ValueError(f"timeframe must be one of {TIMEFRAMES}, got {timeframe!r}")
    if bars is None or bars.empty:
        raise ValueError("no bars to build a snapshot from")

    tf = timeframe
    a = srsi_all(bars)
    t = a.iloc[-1]
    y = a.iloc[-2] if len(a) >= 2 else None
    partial = tf in ("1w", "1mo")
    now = _when(t["ts"], tf, latest=True)

    k_t, d_t = num(t["srsi_k"]), num(t["srsi_d"])
    k_y = num(y["srsi_k"]) if y is not None else None
    d_y = num(y["srsi_d"]) if y is not None else None
    zone = t["srsi_zone"] if isinstance(t["srsi_zone"], str) else None
    kd_side = to_int(t["srsi_kd_side"])
    slope = to_int(t["srsi_slope"])
    pinned = to_int(t["srsi_pinned"])

    zone_info = {"key": zone, "label": t["srsi_label"], "held": to_int(t["srsi_zone_held"]),
                 "since": iso(t["srsi_zone_since"], tf) if zone else None,
                 "from_start": bool(t["srsi_zone_from_start"])}
    kd_info = {"side": _KD_SIDE.get(kd_side) if kd_side is not None else None,
               "held": to_int(t["srsi_kd_held"]),
               "since": iso(t["srsi_kd_since"], tf) if kd_side is not None else None,
               "from_start": bool(t["srsi_kd_from_start"])}
    slope_info = {"direction": _SLOPE.get(slope) if slope is not None else None,
                  "held": to_int(t["srsi_slope_held"])}
    pinned_info = {"at": {1: 100, -1: 0}.get(pinned) if pinned else None,
                   "held": to_int(t["srsi_pinned_held"]) if pinned else None}

    # -- events on the latest candle: every one is an alert (both directions) -----------
    events: list[dict] = []
    if bool(t["srsi_zone_change"]):
        events.append({"type": "zone_change", "from": t["srsi_zone_from"], "to": zone,
                       "direction": "up" if t["srsi_zone_change_up"] else "down",
                       "k": k_t, "d": d_t,
                       "text": zone_change_text(t["srsi_k"], t["srsi_zone_from"], zone)})
    for col, above in (("srsi_kd_cross_above", True), ("srsi_kd_cross_below", False)):
        if bool(t[col]):
            events.append({"type": "kd_cross", "direction": "above" if above else "below",
                           "zone": t["srsi_kd_cross_zone"], "k": k_t, "d": d_t,
                           "text": kd_cross_text(t["srsi_k"], t["srsi_d"], above,
                                                 t["srsi_kd_cross_zone"])})
    alerts = [{"timeframe": tf, **e} for e in events]

    def last(col: str) -> Optional[str]:
        hits = a.index[a[col].astype(bool)]
        return iso(a.loc[hits[-1], "ts"], tf) if len(hits) else None

    last_events = {"zone_change": last("srsi_zone_change"),
                   "kd_cross_above": last("srsi_kd_cross_above"),
                   "kd_cross_below": last("srsi_kd_cross_below")}

    # -- texts -------------------------------------------------------------------------
    texts: list[str] = [f"{name} · {TF_NAME[tf]} Stoch RSI — {now}: close {num(t['close']):,.2f}"]

    line = f"%K {fmt2(k_t)} · %D {fmt2(d_t)}"
    if y is not None:
        line += f" [{PREV.get(tf, 'previous candle')}: %K {fmt2(k_y)} · %D {fmt2(d_y)}]"
    texts.append(line)

    if zone is None:
        texts.append(f"%K {LABEL_NA}.")
    else:
        parts = [t["srsi_label"]]
        detail = []
        if slope_info["direction"] and slope_info["held"]:
            detail.append(f"%K {slope_info['direction']} for {units(slope_info['held'], tf)}")
        if kd_side is not None:
            start = " (start of data)" if kd_info["from_start"] else ""
            detail.append(f"{_KD_WORDS[kd_side]} since {_when(t['srsi_kd_since'], tf)}{start} "
                          f"({units(kd_info['held'], tf)})")
        if pinned_info["at"] is not None and pinned_info["held"]:
            detail.append(f"%K pinned at {pinned_info['at']} for {units(pinned_info['held'], tf)}")
        if detail:
            parts.append("; ".join(detail))
        texts.append(" — ".join(parts) + ".")

    for e in events:
        texts.append(f"{now}: {e['text']}")

    held = zone_info["held"]
    if zone is not None and held is not None and 2 <= held <= recent_bars and not zone_info["from_start"]:
        came_from = a["srsi_zone_from"].iloc[len(a) - held]
        texts.append(f"In {t['srsi_label']} for {units(held, tf)} "
                     f"(since {_when(t['srsi_zone_since'], tf)}), came from {ZONE_LABEL[came_from]}.")
    elif zone is not None and held is not None and held > recent_bars:
        start = " (start of data)" if zone_info["from_start"] else ""
        texts.append(f"Bigger picture: in {t['srsi_label']} since "
                     f"{_when(t['srsi_zone_since'], tf)}{start} ({units(held, tf)}).")

    return {
        "instrument": name,
        "timeframe": tf,
        "as_of": iso(t["ts"], tf),
        "partial": partial,
        "previous": iso(y["ts"], tf) if y is not None else None,
        "close": {"today": num(t["close"]), "previous": num(y["close"]) if y is not None else None},
        "values": {"today": {"k": k_t, "d": d_t},
                   "previous": {"k": k_y, "d": d_y} if y is not None else None},
        "label": t["srsi_label"],
        "zone": zone_info,
        "kd": kd_info,
        "slope": slope_info,
        "pinned": pinned_info,
        "events_today": events,
        "last_events": last_events,
        "alerts": alerts,
        "texts": texts,
    }


def summary_line(snapshots: dict) -> str:
    """'Stoch RSI: 1M oversold 14.88 · 1W oversold 2.43 · 1D middle 56.04 · ... · 5m oversold 0.00'
    (the number is %K)."""
    parts = []
    for tf in TIMEFRAMES:
        if tf not in snapshots:
            continue
        snap = snapshots[tf]
        if snap is None or snap["zone"]["key"] is None:
            parts.append(f"{TF_NAME[tf]} n/a")
            continue
        parts.append(f"{TF_NAME[tf]} {_ZONE_SHORT[snap['zone']['key']]} "
                     f"{fmt2(snap['values']['today']['k'])}")
    return "Stoch RSI: " + " · ".join(parts)


@dataclass
class StochRsiSnapshotResult:
    ok: bool                       # True only if every requested timeframe built
    instrument_key: str
    snapshots: dict = field(default_factory=dict)    # timeframe -> snapshot dict or None
    errors: dict = field(default_factory=dict)       # timeframe -> plain reason
    summary: Optional[str] = None


def build_stoch_rsi_snapshot(instrument_key: str, name: str,
                             timeframes: tuple[str, ...] = TIMEFRAMES) -> StochRsiSnapshotResult:
    """Read each timeframe and build its snapshot. Never raises; a failed timeframe is
    None with a reason in `errors`; the others still come back."""
    from modules.market_data.upstox.indicator_ohlcv_reader import read_for_indicators

    result = StochRsiSnapshotResult(ok=True, instrument_key=instrument_key)
    for tf in timeframes:
        try:
            if tf not in TIMEFRAMES:
                raise ValueError(f"timeframe must be one of {TIMEFRAMES}, got {tf!r}")
            read = read_for_indicators(instrument_key, DEFAULT_DOMAIN[tf], tf)   # never raises
            if not read.ok:
                logger.warning("Stoch RSI snapshot %s not built for %s: %s", tf, instrument_key,
                               read.error)
                result.snapshots[tf], result.errors[tf] = None, read.error
                continue
            snap = snapshot_from_bars(read.df, name, tf)
        except Exception as exc:  # boundary: a pre-market run must not crash
            error = f"could not build Stoch RSI snapshot ({type(exc).__name__}: {exc})"
            logger.exception("Stoch RSI snapshot %s failed for %s: %s", tf, instrument_key, error)
            result.snapshots[tf], result.errors[tf] = None, error
            continue
        logger.info("Stoch RSI snapshot ok for %s (%s): as of %s, %s, %d alert(s).",
                    instrument_key, tf, snap["as_of"], snap["label"], len(snap["alerts"]))
        result.snapshots[tf] = snap
    result.ok = not result.errors
    result.summary = summary_line(result.snapshots)
    return result


if __name__ == "__main__":
    #   python -m modules.Module_F_Tech_Indicators_Funnel.oscillators.stoch_rsi.stoch_rsi_snapshot
    #   ... stoch_rsi_snapshot --timeframes 1d 60m --json
    # Output goes to the screen AND to logs/stoch_rsi_test_logs/stoch_rsi_snapshot.log
    # (overwritten; first line = the command).
    import argparse
    import json
    from pathlib import Path

    from dotenv import load_dotenv

    parser = argparse.ArgumentParser(description="Build the Stoch RSI snapshot (read-only).")
    parser.add_argument("--key", default="NSE_INDEX|Nifty 50")
    parser.add_argument("--name", default="Nifty 50")
    parser.add_argument("--timeframes", nargs="+", default=list(TIMEFRAMES), choices=list(TIMEFRAMES))
    parser.add_argument("--json", action="store_true", help="also print the full package")
    args = parser.parse_args()

    load_dotenv()
    log_path = Path("logs") / "stoch_rsi_test_logs" / "stoch_rsi_snapshot.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[logging.FileHandler(log_path, mode="w", encoding="utf-8"),
                  logging.StreamHandler()],
    )
    out = logging.getLogger("stoch_rsi_snapshot_check")
    out.info("command: stoch_rsi_snapshot --timeframes %s --key %s%s", " ".join(args.timeframes),
             args.key, " --json" if args.json else "")

    res = build_stoch_rsi_snapshot(args.key, args.name, tuple(args.timeframes))
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
