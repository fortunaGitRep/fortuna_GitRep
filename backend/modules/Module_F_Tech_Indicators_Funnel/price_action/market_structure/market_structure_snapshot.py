"""
modules/Module_F_Tech_Indicators_Funnel/price_action/market_structure/market_structure_snapshot.py

Market structure step 6: the "where we stand" package for one instrument, per
timeframe (1M, 1W, 1D, 60m, 15m, 5m) plus the two provisional views (60m from 5m
candles, 1D from 60m candles) -- trend state, the prices that change it, BOS /
CHoCH on the latest candle, step-4 labels that happened on it, alerts and
plain-English texts -- plus one summary line. JSON-safe (no NaN, ISO dates).

structure_events.py / level_breaks.py do the work; this file turns their results
into what Ash reads. Texts are fixed templates (no AI), so the same data always
gives the same words. Same shape as macd_snapshot.py.

Meaning (printed once at the top of the manual check, Ash's wording):
  BOS  : Break of Structure  - indicates a trend continuation
  CHoCH: Change of Character - indicates a potential trend reversal

Entry points:
  - snapshot_from_bars(bars, name, timeframe, directions)          pure, one timeframe
  - provisional_snapshot(lower_bars, name, higher_tf, directions)   pure, 60m or 1d
  - summary_line(snapshots, provisional)                            pure, one line
  - build_market_structure_snapshot(key, name, timeframes, directions)
        reads via indicator_ohlcv_reader. NEVER raises: every view comes back ok
        or with a plain reason.

Decided with Ash (16 Oct 2026):
  - Alerts: every BOS and CHoCH on the latest candle, all timeframes, both
    directions ("above" = up events only, for stocks). Step-4 labels (failed,
    retested, held, re-broken) are text lines only, never alerts.
  - Dates: report_date everywhere ('Tue 13 Oct 2026', 'Week of Mon 12 Oct 2026').
  - Trend words: uptrend / downtrend / neutral (never bull / bear).
  - Each line uses only what was known that day; the next day informs same or
    different. The latest weekly / monthly candle is the running week / month.

Indicators never fetch data -- Fortuna's refresh step does.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional

import pandas as pd

from modules.Module_F_Tech_Indicators_Funnel.indicator_common.text_format import (
    iso,
    num,
    price,
    report_date,
    signed,
    units,
)
from modules.Module_F_Tech_Indicators_Funnel.indicator_common.timeframes import (
    DEFAULT_DOMAIN,
    NOW,
    TF_NAME,
    TIMEFRAMES,
)
from modules.Module_F_Tech_Indicators_Funnel.price_action.market_structure.level_breaks import (
    find_level_breaks,
)
from modules.Module_F_Tech_Indicators_Funnel.price_action.market_structure.structure_events import (
    current_structure,
    find_structure_events,
)
from modules.Module_F_Tech_Indicators_Funnel.price_action.swing_points.provisional_swings import (
    provisional_swings,
)
from modules.Module_F_Tech_Indicators_Funnel.price_action.swing_points.zigzag_settings import (
    get_equal_tolerance,
    get_zigzag_settings,
)
from modules.Module_F_Tech_Indicators_Funnel.price_action.swing_points.zigzag_swings import (
    find_zigzag_swings,
)

logger = logging.getLogger(__name__)

DIRECTIONS = ("both", "above")
PROVISIONAL = {"60m": "5m", "1d": "60m"}        # higher view -> the candles it is built on
LABEL_LOOKBACK = 20                               # events whose levels are checked for labels today
MEANING = ("BOS  : Break of Structure  - indicates a trend continuation",
           "CHoCH: Change of Character - indicates a potential trend reversal")


# --- small helpers -------------------------------------------------------------------

def _candles(bars: pd.DataFrame) -> pd.DataFrame:
    if bars is None or bars.empty:
        raise ValueError("no bars to build a snapshot from")
    df = bars.rename(columns={"ts": "time"}) if "ts" in bars.columns else bars
    return df[["time", "open", "high", "low", "close"]].reset_index(drop=True)


def _real_levels(candles: pd.DataFrame, tf: str) -> pd.DataFrame:
    dev, depth = get_zigzag_settings(tf)
    sw = find_zigzag_swings(candles, dev, depth)
    lv = sw.rename(columns={"detected_time": "active_from"})
    return lv[["kind", "price", "pivot_time", "active_from"]]


def _provisional_levels(lower: pd.DataFrame, lower_tf: str, higher_tf: str) -> pd.DataFrame:
    dev, depth = get_zigzag_settings(lower_tf)
    higher_dev, _ = get_zigzag_settings(higher_tf)
    prov = provisional_swings(find_zigzag_swings(lower, dev, depth), higher_dev)
    lv = prov.rename(columns={"known_at": "active_from"})
    return lv[["kind", "price", "pivot_time", "active_from"]]


def _event_name(ev: str, before: str, after: str) -> str:
    return f"BOS, {after} continues" if ev == "BOS" else f"CHoCH, {before} to {after}"


def _same(a: Any, b: Any) -> bool:
    return not pd.isna(a) and not pd.isna(b) and pd.Timestamp(a) == pd.Timestamp(b)


# --- pure core -------------------------------------------------------------------------

def _build(candles: pd.DataFrame, levels: pd.DataFrame, name: str, view: str, title: str,
           date_tf: str, tol: float, directions: str, partial: bool) -> dict:
    if directions not in DIRECTIONS:
        raise ValueError(f"directions must be one of {DIRECTIONS}, got {directions!r}")
    bullish_only = directions == "above"
    ev = find_structure_events(candles, levels, tol)
    st = current_structure(candles, levels)
    t = candles.iloc[-1]
    y = candles.iloc[-2] if len(candles) >= 2 else None
    close = num(t["close"])
    now = NOW.get(date_tf, "On this candle")

    def d(x):            # report date in this view's candle size
        return report_date(x, date_tf)

    # -- trend and what set it ----------------------------------------------------------
    trend_state = st["trend"]
    chochs = ev[ev["event"] == "CHoCH"]
    set_by = None
    held = None
    if len(chochs):
        c = chochs.iloc[-1]
        start = int(candles.index[candles["time"] == c["time"]][0])
        held = len(candles) - start                  # breaking candle counts as the first
        set_by = {"event": "CHoCH", "direction": c["direction"], "level": num(c["level_price"]),
                  "level_pivot": iso(c["level_pivot_time"], date_tf), "time": iso(c["time"], date_tf)}

    # -- prices that change it ------------------------------------------------------------
    def flip(level: Optional[float], up: bool) -> dict:
        side = "uptrend" if up else "downtrend"
        means = (f"BOS, {side} continues" if trend_state == side
                 else f"CHoCH, {trend_state} to {side}")
        if level is None or close is None:
            return {"level": level, "distance_pts": None, "distance_pct": None, "means": means}
        gap = level - close
        return {"level": level, "distance_pts": gap, "distance_pct": gap / close * 100, "means": means}

    flips = {"up": flip(st["up_target"], True), "down": flip(st["down_target"], False)}

    # -- events and labels on the latest candle -------------------------------------------------
    today_ev = ev[ev["time"] == t["time"]]
    events = [{"type": r["event"], "direction": r["direction"],
               "trend_before": r["trend_before"], "trend_after": r["trend_after"],
               "level": num(r["level_price"]), "level_pivot": iso(r["level_pivot_time"], date_tf),
               "gap": bool(r["gap"]), "bullish": r["direction"] == "up"}
              for _, r in today_ev.iterrows()]
    shown = [e for e in events if e["bullish"] or not bullish_only]
    alerts = [{"view": view, **e} for e in shown]

    labels = []
    recent = ev.tail(LABEL_LOOKBACK)
    if len(recent):
        lv = pd.DataFrame({"kind": recent["level_kind"], "price": recent["level_price"],
                           "known_at": recent["active_from"], "event_id": range(len(recent))})
        br = find_level_breaks(candles, lv, tol)
        for _, b in br.iterrows():
            src = recent.iloc[int(b["event_id"])]
            what = None
            if b["cycle"] > 1 and _same(b["confirmed_time"], t["time"]):
                what = "re-broken"
            elif isinstance(b["outcome"], str) and _same(b["outcome_time"], t["time"]):
                what = b["outcome"]                                   # 'failed' / 'held'
            elif _same(b["retest_time"], t["time"]):
                what = "retested"
            if what and (src["direction"] == "up" or not bullish_only):
                labels.append({"label": what, "level": num(src["level_price"]),
                               "direction": src["direction"], "event": src["event"],
                               "event_time": iso(src["time"], date_tf)})
        # one line per level and label
        seen, uniq = set(), []
        for lab in labels:
            k = (lab["label"], lab["level"])
            if k not in seen:
                seen.add(k)
                uniq.append(lab)
        labels = uniq

    # -- status of the last break ---------------------------------------------------------------
    last_break = None
    if len(ev):
        r = ev.iloc[-1]
        if pd.isna(r["cleared_time"]):
            status = "not cleared yet" if not isinstance(r["outcome"], str) else r["outcome"]
        elif isinstance(r["outcome"], str):
            status = r["outcome"]
        elif pd.isna(r["retest_time"]):
            status = "cleared, no retest yet"
        else:
            status = "retested"
        last_break = {"event": r["event"], "direction": r["direction"],
                      "name": _event_name(r["event"], r["trend_before"], r["trend_after"]),
                      "level": num(r["level_price"]), "time": iso(r["time"], date_tf),
                      "status": status, "rebreaks": int(r["rebreaks"])}

    def last_of(kind: str, direction: str) -> Optional[str]:
        hit = ev[(ev["event"] == kind) & (ev["direction"] == direction)]
        return iso(hit["time"].iloc[-1], date_tf) if len(hit) else None

    last_events = {f"{k.lower()}_{dr}": last_of(k, dr)
                   for k in ("BOS", "CHoCH") for dr in ("up", "down")}

    # -- texts ----------------------------------------------------------------------------------
    texts: list[str] = []
    head = f"{name} · {title} — as of {d(t['time'])}"
    if partial:
        head += " (week to date)" if date_tf == "1w" else " (month to date)"
    texts.append(head + f": close {price(close)}")

    if trend_state == "neutral" or set_by is None:
        texts.append("NEUTRAL: no structure break yet.")
    else:
        word = "above" if set_by["direction"] == "up" else "below"
        texts.append(f"{trend_state.upper()} since {d(chochs.iloc[-1]['time'])} "
                     f"(CHoCH, closed {word} {price(set_by['level'])}), {units(held, date_tf)}.")

    def flip_text(f: dict, up: bool) -> str:
        word = "above" if up else "below"
        if f["level"] is None:
            return (f"Close {word}: no level now, waiting for a new swing "
                    f"{'high' if up else 'low'} ({f['means']} on its break).")
        return (f"Close {word} {price(f['level'])} = {f['means']} "
                f"({signed(f['distance_pts'])} / {f['distance_pct']:+.2f}% away).")

    texts.append(flip_text(flips["up"], True))
    texts.append(flip_text(flips["down"], False))

    for e in shown:
        word = "above" if e["direction"] == "up" else "below"
        flag = "⚡ " if e["type"] == "CHoCH" else ""
        pivot = (f" (swing {'high' if e['direction'] == 'up' else 'low'} of "
                 f"{d(e['level_pivot'])})" if e["level_pivot"] else "")
        gap = ", on a gap" if e["gap"] else ""
        texts.append(f"{flag}{now}: {_event_name(e['type'], e['trend_before'], e['trend_after'])}"
                     f" — closed {word} {price(e['level'])}{gap}{pivot}.")

    for lab in labels:
        verb = {"re-broken": "was re-broken", "retested": "was retested"}.get(lab["label"], lab["label"])
        texts.append(f"{now}: the {price(lab['level'])} break "
                     f"({d(lab['event_time'])}) {verb}.")

    if last_break and not len(today_ev):
        extra = f", re-broken {last_break['rebreaks']}x" if last_break["rebreaks"] else ""
        texts.append(f"Last break: {last_break['name']}, {price(last_break['level'])} "
                     f"({d(last_break['time'])}): {last_break['status']}{extra}.")

    return {
        "instrument": name,
        "view": view,
        "title": title,
        "directions": directions,
        "as_of": iso(t["time"], date_tf),
        "partial": partial,
        "close": {"today": close, "previous": num(y["close"]) if y is not None else None},
        "trend": {"state": trend_state, "held": held, "set_by": set_by},
        "flip": flips,
        "events_today": events,
        "labels_today": labels,
        "last_break": last_break,
        "last_events": last_events,
        "alerts": alerts,
        "texts": texts,
    }


def snapshot_from_bars(bars: pd.DataFrame, name: str, timeframe: str,
                       directions: str = "both") -> dict:
    """One real timeframe from its candles (ascending 'ts' or 'time', OHLC).
    Raises ValueError on bad input (callers use build_market_structure_snapshot)."""
    if timeframe not in TIMEFRAMES:
        raise ValueError(f"timeframe must be one of {TIMEFRAMES}, got {timeframe!r}")
    candles = _candles(bars)
    return _build(candles, _real_levels(candles, timeframe), name, timeframe,
                  TF_NAME[timeframe], timeframe, get_equal_tolerance(timeframe), directions,
                  partial=timeframe in ("1w", "1mo"))


def provisional_snapshot(lower_bars: pd.DataFrame, name: str, higher_tf: str,
                         directions: str = "both") -> dict:
    """Ash's temporary-lock view: higher_tf '60m' (from 5m candles) or '1d' (from 60m)."""
    if higher_tf not in PROVISIONAL:
        raise ValueError(f"provisional view must be one of {tuple(PROVISIONAL)}, got {higher_tf!r}")
    lower_tf = PROVISIONAL[higher_tf]
    candles = _candles(lower_bars)
    title = f"provisional {TF_NAME[higher_tf]} (from {TF_NAME[lower_tf]})"
    return _build(candles, _provisional_levels(candles, lower_tf, higher_tf), name,
                  f"provisional_{higher_tf}", title, lower_tf, get_equal_tolerance(higher_tf),
                  directions, partial=False)


def summary_line(snapshots: dict, provisional: Optional[dict] = None) -> str:
    """'Structure: 1M uptrend · 1W downtrend · ... · prov. 60m uptrend · prov. 1D downtrend'"""
    parts = []
    for tf in TIMEFRAMES:
        if tf not in snapshots:
            continue
        snap = snapshots[tf]
        parts.append(f"{TF_NAME[tf]} {snap['trend']['state'] if snap else 'n/a'}")
    for higher in PROVISIONAL:
        if provisional and higher in provisional:
            snap = provisional[higher]
            parts.append(f"prov. {TF_NAME[higher]} {snap['trend']['state'] if snap else 'n/a'}")
    return "Structure: " + " · ".join(parts)


# --- never-raise entry point ------------------------------------------------------------

@dataclass
class MarketStructureSnapshotResult:
    ok: bool                                           # True only if every view built
    instrument_key: str
    snapshots: dict = field(default_factory=dict)      # timeframe -> snapshot or None
    provisional: dict = field(default_factory=dict)    # '60m' / '1d' -> snapshot or None
    errors: dict = field(default_factory=dict)         # view -> plain reason
    summary: Optional[str] = None


def build_market_structure_snapshot(
    instrument_key: str,
    name: str,
    timeframes: tuple[str, ...] = TIMEFRAMES,
    directions: str = "both",
    with_provisional: bool = True,
) -> MarketStructureSnapshotResult:
    """Read each timeframe and build its snapshot, then the provisional views.
    Never raises; one log line per view outcome."""
    from modules.market_data.upstox.indicator_ohlcv_reader import read_for_indicators

    result = MarketStructureSnapshotResult(ok=True, instrument_key=instrument_key)
    bars: dict = {}

    def read(tf: str):
        if tf not in bars:
            r = read_for_indicators(instrument_key, DEFAULT_DOMAIN[tf], tf)   # never raises
            bars[tf] = r.df if r.ok else None
            if not r.ok:
                result.errors[tf] = r.error
        return bars[tf]

    def run(view: str, store: dict, key: str, fn) -> None:
        try:
            snap = fn()
        except Exception as exc:  # boundary: a pre-market run must not crash
            error = f"could not build market structure snapshot ({type(exc).__name__}: {exc})"
            logger.exception("Market structure %s failed for %s: %s", view, instrument_key, error)
            store[key], result.errors[view] = None, error
            return
        if snap is None:
            store[key] = None
            return
        logger.info("Market structure ok for %s (%s): as of %s, %s, %d alert(s).",
                    instrument_key, view, snap["as_of"], snap["trend"]["state"], len(snap["alerts"]))
        store[key] = snap

    for tf in timeframes:
        if tf not in TIMEFRAMES:
            result.snapshots[tf], result.errors[tf] = None, f"timeframe must be one of {TIMEFRAMES}"
            continue
        df = read(tf)
        if df is None:
            logger.warning("Market structure %s not built for %s: %s", tf, instrument_key,
                           result.errors.get(tf))
            result.snapshots[tf] = None
            continue
        run(tf, result.snapshots, tf, lambda df=df, tf=tf: snapshot_from_bars(df, name, tf, directions))

    if with_provisional:
        for higher, lower in PROVISIONAL.items():
            view = f"provisional_{higher}"
            df = read(lower)
            if df is None:
                result.provisional[higher] = None
                result.errors.setdefault(view, f"no {lower} candles: {result.errors.get(lower)}")
                continue
            run(view, result.provisional, higher,
                lambda df=df, higher=higher: provisional_snapshot(df, name, higher, directions))

    result.ok = not result.errors
    result.summary = summary_line(result.snapshots, result.provisional)
    return result


# --- manual check ---------------------------------------------------------------------

if __name__ == "__main__":
    #   python -m modules.Module_F_Tech_Indicators_Funnel.price_action.market_structure.market_structure_snapshot
    #   ... market_structure_snapshot --timeframes 1d 5m --directions above --json
    # Output goes to the screen AND to logs/market_structure_test_logs/market_structure_snapshot.log
    # (overwritten each run).
    import argparse
    import json
    from pathlib import Path

    from dotenv import load_dotenv

    parser = argparse.ArgumentParser(description="Build the market structure snapshot (read-only).")
    parser.add_argument("--key", default="NSE_INDEX|Nifty 50")
    parser.add_argument("--name", default="Nifty 50")
    parser.add_argument("--timeframes", nargs="+", default=list(TIMEFRAMES), choices=list(TIMEFRAMES))
    parser.add_argument("--directions", default="both", choices=DIRECTIONS)
    parser.add_argument("--no-provisional", action="store_true", help="skip the provisional views")
    parser.add_argument("--json", action="store_true", help="also print the full package")
    args = parser.parse_args()

    load_dotenv()
    log_path = (Path(__file__).resolve().parents[4] / "logs" / "market_structure_test_logs"
                / "market_structure_snapshot.log")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[logging.FileHandler(log_path, mode="w", encoding="utf-8"),
                  logging.StreamHandler()],
    )
    out = logging.getLogger("market_structure_snapshot_check")
    out.info("command: market_structure_snapshot --timeframes %s --directions %s --key %s%s%s",
             " ".join(args.timeframes), args.directions, args.key,
             " --no-provisional" if args.no_provisional else "", " --json" if args.json else "")

    res = build_market_structure_snapshot(args.key, args.name, tuple(args.timeframes),
                                          args.directions, not args.no_provisional)
    out.info("=" * 96)
    for line in MEANING:
        out.info(line)
    out.info("=" * 96)
    views = [(tf, res.snapshots.get(tf), tf) for tf in args.timeframes]
    views += [(f"provisional_{h}", res.provisional.get(h), f"provisional_{h}") for h in res.provisional]
    for view, snap, err_key in views:
        if snap is None:
            out.warning("%s NOT OK -- %s", view, res.errors.get(err_key))
        else:
            for line in snap["texts"]:
                out.info(line)
            out.info("alerts: %s", snap["alerts"] or "none")
        out.info("-" * 96)
    out.info(res.summary)
    out.info("=" * 96)
    if args.json:
        out.info(json.dumps({"summary": res.summary, "snapshots": res.snapshots,
                             "provisional": res.provisional, "errors": res.errors},
                            indent=2, ensure_ascii=False))
    out.info("log written to %s", log_path)
