"""
Options sample-day study -- step 1: label every Nifty 50 trading day and pick
sample days for the contract study (test plan: Fortuna_Options_SampleDay_TestCases.xlsx).

Study window: all Nifty 5m history (from 3 Jan 2022), trimmed later with `start` to the
expired-contract window. Every day gets its real weekly expiry: Thursday up to 28 Aug 2025,
Tuesday from 2 Sept 2025 (holidays move it to the previous trading day). The weekday /
days-to-expiry analysis (TC-SEL-06) uses Tuesday-era days only; months, phases, gaps and
timing use the whole window.

Per trading day:
  strong / colour        TC-SEL-01, 02  official daily candle (reader rule 4)
  gap                    TC-NB-04       09:15 open vs previous close
  expiry / dte / era     TC-DATA-02     trading days left to expiry (Tuesday era: Wed 4 ... Tue 0)
  phase                  TC-SEL-04      Wyckoff phase from LOCKED daily Zig Zag swings
  move timing            TC-NB-01       share of the day's move done by 11:30 (5m)
  window move            TC-NB-03       Nifty move 09:30 -> 11:30 (5m)
  event                  TC-NB-05       from an event CSV when one is given
Candidates: strongest strong days covering month x colour, phase x colour (whole window)
and dte x colour (Tuesday era only) (TC-SEL-03, 05, 06), plus every strong Tuesday-era
expiry day (TC-CB-06) and every strong day whose 09:30-11:30 move went against the day's
colour (TC-CB-04). Ash keeps or rejects them (TC-SEL-07).

Pure functions on DataFrames, no I/O. All thresholds are named constants below.
"""

from __future__ import annotations

from datetime import date, time, timedelta

import numpy as np
import pandas as pd

DEFAULT_START = date(2022, 1, 3)     # first Nifty 5m bar stored
LAST_THU_EXPIRY = date(2025, 8, 28)  # last Thursday weekly expiry
FIRST_TUE_EXPIRY = date(2025, 9, 2)  # first Tuesday weekly expiry (NSE, from 1 Sept 2025)

STRONG_BODY_RATIO = 0.60             # body >= 60% of range = strong day
GAP_NONE_PCT = 0.10                  # |open - prev close| below this % = no gap
WINDOW_START = time(9, 30)           # Ash's trading window
WINDOW_END = time(11, 30)
MORNING_SHARE = 0.75                 # >= 75% of the day's move done by 11:30 = morning
LATE_SHARE = 0.25                    # <= 25% done by 11:30 = late (not traded)
FLAT_MOVE_PCT = 0.10                 # |day move| below this % of open = flat (no timing label)

PHASES = ("markup", "markdown", "accumulation", "distribution")
DAY_COLUMNS = [
    "trade_date", "weekday", "month", "open", "high", "low", "close",
    "body_ratio", "strong", "colour", "prev_close", "gap_pct", "gap_type",
    "expiry_date", "dte", "era", "expiry_assumed", "phase", "phase_basis",
    "move_pct", "share_by_1130", "move_timing",
    "window_move_pts", "window_run_pts", "event",
]


# ----------------------------------------------------------------------------- daily
def daily_labels(daily: pd.DataFrame) -> pd.DataFrame:
    """
    daily: trade_date, open, high, low, close (official daily candles, any order).
    Adds body_ratio, strong, colour, prev_close, gap_pct, gap_type.
    gap_type: full_up (open above prev high), up, none, down, full_down (open below prev low).
    """
    d = daily.copy()
    d["trade_date"] = pd.to_datetime(d["trade_date"]).dt.date
    d = d.sort_values("trade_date").reset_index(drop=True)
    rng = d["high"] - d["low"]
    body = (d["close"] - d["open"]).abs()
    d["body_ratio"] = np.where(rng > 0, body / rng.where(rng > 0, 1.0), np.nan)
    d["strong"] = d["body_ratio"] >= STRONG_BODY_RATIO
    d["colour"] = np.select([d["close"] > d["open"], d["close"] < d["open"]],
                            ["green", "red"], default="doji")
    d["strong"] = d["strong"].fillna(False).astype(bool) & (d["colour"] != "doji")

    prev_close, prev_high, prev_low = d["close"].shift(1), d["high"].shift(1), d["low"].shift(1)
    d["prev_close"] = prev_close
    d["gap_pct"] = 100.0 * (d["open"] - prev_close) / prev_close
    gap_type = np.select(
        [d["open"] > prev_high, d["open"] < prev_low,
         d["gap_pct"] >= GAP_NONE_PCT, d["gap_pct"] <= -GAP_NONE_PCT],
        ["full_up", "full_down", "up", "down"], default="none")
    d["gap_type"] = np.where(prev_close.isna(), None, gap_type)
    d["weekday"] = pd.to_datetime(d["trade_date"]).dt.day_name().str[:3]
    d["month"] = pd.to_datetime(d["trade_date"]).dt.strftime("%Y-%m")
    return d


# ----------------------------------------------------------------------------- expiry
def nominal_expiries(start: date, end: date) -> list[date]:
    """Scheduled weekly expiries before holiday shifts: Thursdays to 28 Aug 2025, then Tuesdays."""
    out = []
    d = start + timedelta(days=(3 - start.weekday()) % 7)            # first Thursday >= start
    while d <= min(LAST_THU_EXPIRY, end):
        out.append(d)
        d += timedelta(days=7)
    d = max(FIRST_TUE_EXPIRY, start + timedelta(days=(1 - start.weekday()) % 7))
    while d <= end:
        out.append(d)
        d += timedelta(days=7)
    return out


def expiry_calendar(trading_days, start: date = DEFAULT_START) -> pd.DataFrame:
    """
    Real weekly expiry for every trading day >= start. A holiday on the scheduled day moves
    expiry to the previous trading day. dte = trading days left after this day up to expiry
    (expiry day = 0). era = 'thu' / 'tue'. Weeks whose expiry is beyond the data are
    'assumed' (scheduled day, no holiday known; dte counted in weekdays).
    """
    days = sorted({pd.Timestamp(x).date() for x in trading_days if pd.Timestamp(x).date() >= start})
    cols = ["trade_date", "expiry_date", "dte", "era", "expiry_assumed", "holiday_shifted"]
    if not days:
        return pd.DataFrame(columns=cols)
    last_day, rows, i = days[-1], [], 0
    for nom in nominal_expiries(start, last_day + timedelta(days=7)):
        if i >= len(days):
            break
        week = [d for d in days[i:] if d <= nom]
        era = "thu" if nom <= LAST_THU_EXPIRY else "tue"
        if nom > last_day:
            for d in week:
                dte = int(np.busday_count(d + timedelta(days=1), nom + timedelta(days=1)))
                rows.append((d, nom, dte, era, True, False))
        elif week:
            expiry = week[-1]
            for k, d in enumerate(week):
                rows.append((d, expiry, len(week) - 1 - k, era, False, expiry != nom))
        i += len(week)
    return pd.DataFrame(rows, columns=cols)


# ----------------------------------------------------------------------------- phase
def phase_by_day(trade_dates, swings: pd.DataFrame, equal_tol_pct: float) -> pd.DataFrame:
    """
    swings: output of find_zigzag_swings() on DAILY candles
            (kind 'high'/'low', price, pivot_time, locked_time, is_locked).
    For each day only swings LOCKED by that day's close are used (no lookahead).
    Pass ALL daily dates so the 'last trend' memory is built from full history.
      last two highs higher and last two lows higher -> markup
      last two highs lower  and last two lows lower  -> markdown
      anything else (mixed or equal within tolerance) -> range:
         accumulation if the last trend was markdown, distribution if markup.
    phase_basis records the swing comparison used, e.g. 'HH+HL'.
    """
    sw = swings[swings["is_locked"]].copy()
    sw["locked_date"] = pd.to_datetime(sw["locked_time"]).dt.date
    sw = sw.sort_values("locked_time")
    rows, last_trend = [], None
    for d in sorted(pd.Timestamp(x).date() for x in trade_dates):
        known = sw[sw["locked_date"] <= d]
        highs = known[known["kind"] == "high"]["price"].tolist()
        lows = known[known["kind"] == "low"]["price"].tolist()
        if len(highs) < 2 or len(lows) < 2:
            rows.append((d, None, "not enough swings"))
            continue
        h = _compare(highs[-2], highs[-1], equal_tol_pct)   # 'higher' / 'lower' / 'equal'
        l = _compare(lows[-2], lows[-1], equal_tol_pct)
        basis = f"{_tag(h, 'H')}+{_tag(l, 'L')}"
        if h == "higher" and l == "higher":
            phase = last_trend = "markup"
        elif h == "lower" and l == "lower":
            phase = last_trend = "markdown"
        elif last_trend == "markdown":
            phase = "accumulation"
        elif last_trend == "markup":
            phase = "distribution"
        else:
            phase = None
            basis += " (no earlier trend)"
        rows.append((d, phase, basis))
    return pd.DataFrame(rows, columns=["trade_date", "phase", "phase_basis"])


def _compare(prev: float, last: float, tol_pct: float) -> str:
    diff_pct = 100.0 * (last - prev) / abs(prev)
    if abs(diff_pct) <= tol_pct:
        return "equal"
    return "higher" if diff_pct > 0 else "lower"


def _tag(cmp: str, side: str) -> str:
    return {"higher": "H", "lower": "L", "equal": "EQ"}[cmp] + side


# ----------------------------------------------------------------------------- 5m timing
def intraday_profile(five_min: pd.DataFrame) -> pd.DataFrame:
    """
    five_min: ts (IST), trade_date, open, high, low, close -- reader rules applied.
    Per day:
      move_pct        (last close - first open) / first open, %
      share_by_1130   part of the day's move done by the close of the last bar before 11:30
      move_timing     morning / all_day / late / flat (thresholds above)
      window_move_pts close before 11:30 minus open of the 09:30 bar
      window_run_pts  best run inside 09:30-11:30 in the day's direction, from the 09:30 open
    """
    f = five_min.copy()
    ts = pd.to_datetime(f["ts"])
    f["t"] = ts.dt.time
    f["trade_date"] = pd.to_datetime(f["trade_date"]).dt.date
    f = f.sort_values("ts")
    rows = []
    for d, g in f.groupby("trade_date", sort=True):
        day_open, day_close = float(g["open"].iloc[0]), float(g["close"].iloc[-1])
        move = day_close - day_open
        before = g[g["t"] < WINDOW_END]
        win = g[(g["t"] >= WINDOW_START) & (g["t"] < WINDOW_END)]
        share = (float(before["close"].iloc[-1]) - day_open) / move if (len(before) and move) else np.nan
        move_pct = 100.0 * move / day_open
        if abs(move_pct) < FLAT_MOVE_PCT or np.isnan(share):
            timing = "flat"
        elif share >= MORNING_SHARE:
            timing = "morning"
        elif share <= LATE_SHARE:
            timing = "late"
        else:
            timing = "all_day"
        if len(win):
            w_open = float(win["open"].iloc[0])
            w_move = float(win["close"].iloc[-1]) - w_open
            w_run = (float(win["high"].max()) - w_open) if move >= 0 else (w_open - float(win["low"].min()))
        else:
            w_move = w_run = np.nan
        rows.append((d, move_pct, share, timing, w_move, w_run))
    return pd.DataFrame(rows, columns=["trade_date", "move_pct", "share_by_1130", "move_timing",
                                       "window_move_pts", "window_run_pts"])


# ----------------------------------------------------------------------------- assemble
def build_day_table(daily: pd.DataFrame, five_min: pd.DataFrame, swings: pd.DataFrame,
                    equal_tol_pct: float, events: pd.DataFrame | None = None,
                    start: date = DEFAULT_START) -> pd.DataFrame:
    """One row per trading day from `start`, DAY_COLUMNS. Daily data should be the full
    history: previous close for the gap, and the phase's trend memory."""
    d = daily_labels(daily)
    phases = phase_by_day(d["trade_date"], swings, equal_tol_pct)
    exp = expiry_calendar(d["trade_date"], start)
    d = d[d["trade_date"] >= start]
    d = d.merge(exp, on="trade_date", how="left")
    d = d.merge(phases, on="trade_date", how="left")
    d = d.merge(intraday_profile(five_min), on="trade_date", how="left")
    if events is not None and len(events):
        ev = events.copy()
        ev["trade_date"] = pd.to_datetime(ev["date"]).dt.date
        ev = ev.groupby("trade_date")["event"].apply(lambda s: "; ".join(map(str, s))).reset_index()
        d = d.merge(ev, on="trade_date", how="left")
    else:
        d["event"] = None
    d["move_timing"] = d["move_timing"].fillna("no 5m data")
    return d[DAY_COLUMNS + ["holiday_shifted"]].reset_index(drop=True)


# ----------------------------------------------------------------------------- candidates
COVERAGE_KEYS = (("month", "TC-SEL-03"), ("phase", "TC-SEL-05"), ("dte", "TC-SEL-06"))


def _pool(days: pd.DataFrame, key: str) -> pd.DataFrame:
    """Rows a coverage key is judged on: dte only in the Tuesday-expiry era."""
    return days[days["era"] == "tue"] if key == "dte" else days


def pick_candidates(days: pd.DataFrame) -> pd.DataFrame:
    """
    Strongest strong day for every (month, colour), (phase, colour) and (dte, colour)
    cell (dte cells from Tuesday-era days only). A day already picked is reused when it
    also fills another cell.
    Returns candidate rows with 'covers' (cells this day fills) and 'keep' blank for Ash.
    """
    strong = days[days["strong"]].sort_values("body_ratio", ascending=False)
    picked: dict = {}
    for key, _tc in COVERAGE_KEYS:
        for (val, colour), g in _pool(strong, key).dropna(subset=[key]).groupby([key, "colour"]):
            already = [i for i in g.index if i in picked]
            idx = already[0] if already else g.index[0]
            picked.setdefault(idx, []).append(f"{key}={val}/{colour}")
    for idx, why in _extra_picks(strong):
        picked.setdefault(idx, []).append(why)
    if not picked:
        return days.iloc[0:0].assign(covers=[], keep=[])
    out = days.loc[list(picked)].copy()
    out["covers"] = [", ".join(picked[i]) for i in out.index]
    out["keep"] = ""
    return out.sort_values("trade_date").reset_index(drop=True)


def _extra_picks(strong: pd.DataFrame) -> list[tuple]:
    """Whole groups some tests need, not one day per cell."""
    out = []
    if {"era", "dte"} <= set(strong.columns):
        for i in strong.index[(strong["era"] == "tue") & (strong["dte"] == 0)]:
            out.append((i, "TC-CB-06 expiry day"))
    if "window_move_pts" in strong.columns:
        w = strong["window_move_pts"]
        against = ((strong["colour"] == "green") & (w < 0)) | ((strong["colour"] == "red") & (w > 0))
        for i in strong.index[against]:
            out.append((i, "TC-CB-04 window against colour"))
    return out


def coverage_report(days: pd.DataFrame, cands: pd.DataFrame) -> list[str]:
    """Text lines: counts per cell and every cell with no strong day (reported, not forced)."""
    lines = []
    strong = days[days["strong"]]
    expected = {
        "month": sorted(days["month"].dropna().unique()),
        "phase": list(PHASES),
        "dte": sorted(int(x) for x in _pool(days, "dte")["dte"].dropna().unique()),
    }
    for key, tc in COVERAGE_KEYS:
        era = "  [Tuesday-expiry era only]" if key == "dte" else ""
        lines.append(f"{tc}  coverage by {key} x colour (strong days available / picked){era}")
        pool_s, pool_c = _pool(strong, key), (_pool(cands, key) if len(cands) else cands)
        for val in expected[key]:
            cells = []
            for colour in ("green", "red"):
                n = int(((pool_s[key] == val) & (pool_s["colour"] == colour)).sum())
                p = int(((pool_c[key] == val) & (pool_c["colour"] == colour)).sum()) if len(cands) else 0
                cells.append(f"{colour} {n}/{p}" + ("  <-- NONE" if n == 0 else ""))
            lines.append(f"   {str(val):<14} " + "   ".join(cells))
        lines.append("")
    if len(cands):
        for tag in ("TC-CB-06 expiry day", "TC-CB-04 window against colour"):
            g = cands[cands["covers"].str.contains(tag, regex=False)]
            lines.append(f"{tag}: {len(g)} days (green {int((g['colour'] == 'green').sum())}, "
                         f"red {int((g['colour'] == 'red').sum())})")
        lines.append("")
    return lines
