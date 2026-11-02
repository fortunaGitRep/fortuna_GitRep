"""
Fortuna Predictor, step A: one row per trading day with the measures the day categories
(Trend day, Swing-trend, Average day, Chop day) will be decided from. Pure functions on
DataFrames, no I/O; the runner is predictor_days_run.py.

On top of the sample-day table (candle, gap, expiry, phase, day move -- sample_days.py):
  first hour      09:15-10:15 (Dalton's initial balance): high, low, width, width vs the
                  average of the previous 20 days
  extension       after 10:15: how far price went above the first-hour high / below its low,
                  in points and in first-hour widths; which side broke first and when
  hour blocks     Nifty move in each block 09:15-10:15, 10:15-11:15, 11:15-12:15,
                  12:15-13:15, 13:15-14:15, 14:15-close
  first 30 min    price at 09:45 minus the previous official close (Gao et al. 2018 measure
                  the first half-hour from the previous close)
  narrow range    previous day's range the narrowest of the last 4 / 7 days (Crabel NR4 / NR7)
  futures volume  near-month Nifty futures (the index has no volume): day and first hour,
                  in units and lots, and vs the average of the previous 20 days. Lots use the
                  contract's own lot size (NSE kept monthly futures at 25 until the 30 Jan 2025
                  expiry, 75 until 30 Dec 2025, 65 after) -- so compare units or the x-average
                  across time, never lots
Open location vs the previous day's range is already in gap_type (full_up = opened above the
previous high, full_down = below the previous low, otherwise inside).
"""

from __future__ import annotations

from datetime import date, time

import numpy as np
import pandas as pd

IB_END = time(10, 15)
FIRST30_END = time(9, 45)
BLOCKS = [("h1_0915", time(9, 15), time(10, 15)), ("h2_1015", time(10, 15), time(11, 15)),
          ("h3_1115", time(11, 15), time(12, 15)), ("h4_1215", time(12, 15), time(13, 15)),
          ("h5_1315", time(13, 15), time(14, 15)), ("h6_1415", time(14, 15), time(23, 59))]
AVG_DAYS = 20
NR_DAYS = (4, 7)

INTRADAY_COLUMNS = (["trade_date", "ib_high", "ib_low", "ib_width", "ext_up_pts", "ext_down_pts",
                     "first_break", "first_break_time", "first30_pts"] + [b[0] for b in BLOCKS])
FUT_COLUMNS = ["trade_date", "fut_expiry", "fut_lot_size", "fut_vol_day", "fut_vol_ib"]


def _with_time(bars: pd.DataFrame) -> pd.DataFrame:
    b = bars.copy()
    b["ts"] = pd.to_datetime(b["ts"])
    b["t"] = b["ts"].dt.time
    b["trade_date"] = pd.to_datetime(b["trade_date"]).dt.date
    return b.sort_values("ts")


# ----------------------------------------------------------------------------- Nifty 5m
def day_intraday(g: pd.DataFrame, prev_close: float | None) -> dict:
    """One day of Nifty 5m bars (with column t) -> first hour, extension, hour blocks, first 30 min."""
    out: dict = {k: np.nan for k in INTRADAY_COLUMNS if k != "trade_date"}
    out["first_break"] = out["first_break_time"] = ""
    ib = g[g["t"] < IB_END]
    if ib.empty:                                      # Muhurat / evening-only session
        return out
    hi, lo = float(ib["high"].max()), float(ib["low"].min())
    out.update(ib_high=hi, ib_low=lo, ib_width=hi - lo)
    after = g[g["t"] >= IB_END]
    if len(after):
        out["ext_up_pts"] = max(0.0, float(after["high"].max()) - hi)
        out["ext_down_pts"] = max(0.0, lo - float(after["low"].min()))
        brk = after[(after["high"] > hi) | (after["low"] < lo)]
        if len(brk):
            r = brk.iloc[0]
            up, down = r["high"] > hi, r["low"] < lo
            out["first_break"] = "both" if (up and down) else ("up" if up else "down")
            out["first_break_time"] = r["t"].strftime("%H:%M")
        else:
            out["first_break"] = "none"
    for name, start, end in BLOCKS:
        blk = g[(g["t"] >= start) & (g["t"] < end)]
        if len(blk):
            out[name] = float(blk["close"].iloc[-1]) - float(blk["open"].iloc[0])
    f30 = g[g["t"] < FIRST30_END]
    if len(f30) and prev_close is not None and not np.isnan(prev_close):
        out["first30_pts"] = float(f30["close"].iloc[-1]) - prev_close
    return out


def intraday_measures(nifty5: pd.DataFrame, prev_close: dict, progress=None) -> pd.DataFrame:
    """All days of Nifty 5m -> INTRADAY_COLUMNS. progress(i, n, day) is called as days are done."""
    b = _with_time(nifty5)
    groups = list(b.groupby("trade_date", sort=True))
    rows = []
    for i, (d, g) in enumerate(groups, 1):
        rows.append({"trade_date": d, **day_intraday(g, prev_close.get(d))})
        if progress:
            progress(i, len(groups), d)
    return pd.DataFrame(rows, columns=INTRADAY_COLUMNS)


# ----------------------------------------------------------------------------- futures
def near_month(day: date, expiries: list[date]) -> date | None:
    return next((e for e in sorted(expiries) if e >= day), None)


def futures_volume(fut: pd.DataFrame, expiries: list[date]) -> pd.DataFrame:
    """
    fut: 1m futures bars of every stored expiry (expiry, ts, trade_date, volume, lot_size).
    Per trading day, the near-month contract (first stored futures expiry on/after the day):
    whole-day and first-hour volume in units.
    """
    if fut.empty:
        return pd.DataFrame(columns=FUT_COLUMNS)
    b = _with_time(fut)
    b["expiry"] = pd.to_datetime(b["expiry"]).dt.date
    rows = []
    for d, g in b.groupby("trade_date", sort=True):
        e = near_month(d, expiries)
        c = g[g["expiry"] == e]
        if c.empty:
            continue
        lot = c["lot_size"].dropna()
        rows.append({"trade_date": d, "fut_expiry": e, "fut_lot_size": float(lot.iloc[0]) if len(lot) else np.nan,
                     "fut_vol_day": float(c["volume"].sum()),
                     "fut_vol_ib": float(c.loc[c["t"] < IB_END, "volume"].sum())})
    return pd.DataFrame(rows, columns=FUT_COLUMNS)


def to_5m(bars: pd.DataFrame) -> pd.DataFrame:
    """
    1m bars -> 5m bars per contract and day, labelled by start time: open first, high max,
    low min, close last, volume sum (and OI last when present). Used by the day viewer and the
    futures parity check, so both build 5m the same way.
    """
    if bars.empty:
        return bars
    b = bars.copy()
    b["ts"] = pd.to_datetime(b["ts"])
    b = b.sort_values("ts")
    keys = [k for k in ("expiry",) if k in b.columns]
    agg = {"open": ("open", "first"), "high": ("high", "max"), "low": ("low", "min"),
           "close": ("close", "last"), "volume": ("volume", "sum")}
    if "oi" in b.columns:
        agg["oi"] = ("oi", "last")
    out = b.groupby(keys + [b["ts"].dt.floor("5min").rename("bucket")], sort=True).agg(**agg).reset_index()
    out = out.rename(columns={"bucket": "ts"})
    out["trade_date"] = out["ts"].dt.date
    return out


# ----------------------------------------------------------------------------- history-based
def prior_average(s: pd.Series, days: int = AVG_DAYS) -> pd.Series:
    """
    Average of the previous `days` days that have a value (today excluded, so no look-ahead).
    Blank days (evening-only Muhurat sessions) are skipped, not counted, so one blank day doesn't
    blank the next 20. NaN until `days` earlier values exist, and on a blank day itself.
    """
    v = s.dropna()
    return v.shift(1).rolling(days, min_periods=days).mean().reindex(s.index).where(s.notna())


def narrow_range_prev(daily: pd.DataFrame, n: int) -> pd.Series:
    """True when the PREVIOUS day's range was the narrowest of its last n days (Crabel NR-n)."""
    rng = daily["high"] - daily["low"]
    nr = rng.eq(rng.rolling(n, min_periods=n).min())
    return nr.shift(1).fillna(False).astype(bool)


# ----------------------------------------------------------------------------- assemble
def build_predictor_days(day_table: pd.DataFrame, daily: pd.DataFrame, intraday: pd.DataFrame,
                         futvol: pd.DataFrame, start: date) -> pd.DataFrame:
    """
    day_table: sample_days.build_day_table() output (already trimmed to start).
    daily: official daily candles, full history (for NR flags).
    intraday / futvol: intraday_measures() / futures_volume() over the full available history,
    so the 20-day averages are filled from the first study day where history allows.
    """
    d = daily.copy()
    d["trade_date"] = pd.to_datetime(d["trade_date"]).dt.date
    d = d.sort_values("trade_date").reset_index(drop=True)
    nr = pd.DataFrame({"trade_date": d["trade_date"],
                       **{f"prev_nr{n}": narrow_range_prev(d, n) for n in NR_DAYS}})

    i = intraday.sort_values("trade_date").reset_index(drop=True).copy()
    i["ib_width_avg20"] = prior_average(i["ib_width"])
    i["ib_width_x"] = i["ib_width"] / i["ib_width_avg20"]
    i["ext_up_x"] = i["ext_up_pts"] / i["ib_width"]
    i["ext_down_x"] = i["ext_down_pts"] / i["ib_width"]

    f = futvol.sort_values("trade_date").reset_index(drop=True).copy()
    if len(f):
        f["fut_vol_day_lots"] = f["fut_vol_day"] / f["fut_lot_size"]
        f["fut_vol_ib_lots"] = f["fut_vol_ib"] / f["fut_lot_size"]
        f["fut_vol_day_x"] = f["fut_vol_day"] / prior_average(f["fut_vol_day"])
        f["fut_vol_ib_x"] = f["fut_vol_ib"] / prior_average(f["fut_vol_ib"])

    out = day_table.copy()
    out["trade_date"] = pd.to_datetime(out["trade_date"]).dt.date
    out = out[out["trade_date"] >= start]
    out = out.merge(i, on="trade_date", how="left").merge(nr, on="trade_date", how="left")
    out = out.merge(f, on="trade_date", how="left") if len(f) else out
    out["first30_pct"] = 100.0 * out["first30_pts"] / out["prev_close"]
    return out.reset_index(drop=True)


COLUMN_ORDER = [
    "trade_date", "weekday", "colour", "strong", "body_ratio", "open", "high", "low", "close", "prev_close",
    "move_pct", "day_move_pts", "day_range_pts", "gap_pct", "gap_type", "expiry_date", "dte", "era",
    "holiday_shifted", "phase", "phase_basis",
    "ib_high", "ib_low", "ib_width", "ib_width_avg20", "ib_width_x",
    "ext_up_pts", "ext_down_pts", "ext_up_x", "ext_down_x", "first_break", "first_break_time",
    "h1_0915", "h2_1015", "h3_1115", "h4_1215", "h5_1315", "h6_1415",
    "first30_pts", "first30_pct", "share_by_1130", "move_timing", "window_move_pts", "window_run_pts",
    "prev_nr4", "prev_nr7",
    "fut_expiry", "fut_lot_size", "fut_vol_day", "fut_vol_day_lots", "fut_vol_day_x",
    "fut_vol_ib", "fut_vol_ib_lots", "fut_vol_ib_x", "event",
]


def ordered(df: pd.DataFrame) -> pd.DataFrame:
    return df[[c for c in COLUMN_ORDER if c in df.columns] + [c for c in df.columns if c not in COLUMN_ORDER]]
