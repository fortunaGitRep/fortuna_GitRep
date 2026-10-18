"""
Horizontal support and resistance lines from Zig Zag swings (Ash, 2026-10-18).

Rules (SUPPORT_RESISTANCE.md section 4.6):
  1. Every Zig Zag swing on a timeframe is one horizontal line at the swing's
     price: the candle HIGH for a swing high, the candle LOW for a swing low
     (find_zigzag_swings already returns exactly that price).
  2. Recency (Ash, 2026-10-18 "lets try this"): 1M / 1W / 1D keep all history;
     60m and 15m keep lines whose pivot is in the last 25 trading days (5 weeks);
     5m keeps the last 3 trading days. RECENT_TRADING_DAYS holds the values.
  3. Merge close lines (rule A, Ash 2026-10-18): lines within the timeframe's
     equal tolerance (zigzag_settings equal_tol_pct) are one line. Keep:
       all highs in the group  -> the highest
       all lows in the group   -> the lowest
       highs and lows mixed    -> the earliest (support turned resistance)
     Ties keep the earliest. Absorbed lines are listed in `merged_from`.
     Lines on opposite sides of price never merge; a line equal to PDO/PDH/
     PDL/PDC is never merged with another price (fixes, Ash 2026-10-18).
     Option (b), noted for later (SUPPORT_RESISTANCE.md): on 1D/1W let the
     highest/lowest rule look back a fixed period only. Not used (Ash chose a).
  4. Each timeframe is numbered on its own, outward from its latest close:
     R1, R2, ... above (nearest first), S1, S2, ... below (nearest first).
     A line exactly at the close is AT and is not numbered.
  5. Trading ladder (the 5m chart): the lines of ALL timeframes (after steps
     2-3) merged again with the 5m tolerance and numbered from the latest close;
     each line lists every timeframe it appears on.
  6. A line whose price equals the latest daily candle's open / high / low /
     close gets PDO / PDH / PDL / PDC. Prices compared at 2 decimals.

Pure functions: no file, R2 or database access. Works for any chart (Nifty,
stocks, option contracts): nothing here assumes an instrument.
"""

from __future__ import annotations

import math
from typing import Optional

import pandas as pd

SWING_INPUT_COLUMNS = ("kind", "price", "pivot_time", "is_locked")
PD_FIELDS = (("open", "PDO"), ("high", "PDH"), ("low", "PDL"), ("close", "PDC"))
TF_ORDER = ("1mo", "1w", "1d", "60m", "15m", "5m")
RECENT_TRADING_DAYS = {"60m": 25, "15m": 25, "5m": 3}   # None / missing = all history
_IST = "Asia/Kolkata"


def _naive_ist(s: pd.Series) -> pd.Series:
    """Datetimes as tz-naive IST, so daily and intraday times compare safely."""
    s = pd.to_datetime(s)
    if getattr(s.dt, "tz", None) is not None:
        s = s.dt.tz_convert(_IST).dt.tz_localize(None)
    return s


def swing_lines(swings: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    """One line per swing: timeframe, kind, price, pivot_time, is_locked."""
    missing = [c for c in SWING_INPUT_COLUMNS if c not in swings.columns]
    if missing:
        raise ValueError(f"swings is missing column(s): {missing}")
    lines = swings.loc[:, list(SWING_INPUT_COLUMNS)].copy()
    lines.insert(0, "timeframe", timeframe)
    lines["price"] = lines["price"].astype(float)
    lines["is_locked"] = lines["is_locked"].astype(bool)
    lines["pivot_time"] = _naive_ist(lines["pivot_time"])
    return lines.reset_index(drop=True)


def recent_since(candle_times: pd.Series, trading_days: Optional[int]) -> Optional[pd.Timestamp]:
    """Start of the Nth-last trading day in the candles (None = keep all history)."""
    if trading_days is None:
        return None
    if trading_days < 1:
        raise ValueError(f"trading_days must be >= 1, got {trading_days!r}")
    days = sorted(_naive_ist(pd.Series(candle_times)).dt.normalize().unique())
    if not days:
        return None
    return pd.Timestamp(days[-min(trading_days, len(days))])


def keep_recent(lines: pd.DataFrame, since: Optional[pd.Timestamp]) -> pd.DataFrame:
    """Lines whose pivot is on or after `since` (all lines when since is None)."""
    if since is None:
        return lines.copy()
    return lines[lines["pivot_time"] >= since].reset_index(drop=True)


def pd_tags(lines: pd.DataFrame, prev_day: Optional[dict]) -> pd.DataFrame:
    """Add column `pd_tags`: e.g. 'PDH', 'PDL PDC' or ''."""
    out = lines.copy()
    if prev_day is None or out.empty:
        out["pd_tags"] = ""
        return out
    for field, _ in PD_FIELDS:
        value = prev_day.get(field)
        if value is None or (isinstance(value, float) and math.isnan(value)):
            raise ValueError(f"prev_day is missing '{field}'")

    def tags_for(p: float) -> str:
        return " ".join(tag for field, tag in PD_FIELDS if p == round(float(prev_day[field]), 2))

    out["pd_tags"] = out["price"].round(2).map(tags_for)
    return out


def _keep_index(group: pd.DataFrame) -> int:
    """Rule A: all highs -> highest, all lows -> lowest, mixed -> earliest."""
    kinds = set(group["kind"])
    if kinds == {"high"}:
        best = group["price"].max()
        pool = group[group["price"] == best]
    elif kinds == {"low"}:
        best = group["price"].min()
        pool = group[group["price"] == best]
    else:
        pool = group
    return pool.sort_values("pivot_time", kind="stable").index[0]


def merge_close_lines(lines: pd.DataFrame, tol_pct: float,
                      close: Optional[float] = None) -> pd.DataFrame:
    """Merge lines within `tol_pct` percent of the group's lowest price (rule A).

    Fixes (Ash, 2026-10-18):
      - with `close`, a line above price and a line below price never merge
        (lines exactly at price are not merged with either side);
      - a line equal to PDO / PDH / PDL / PDC is never merged with another price,
        so the tag stays on the right price (identical-price PD lines from
        several timeframes still combine into one).

    Adds `merged_count` (lines in the group) and `merged_from` (the absorbed
    lines as text). The kept line's `timeframes` lists every timeframe in the group.
    """
    if tol_pct is None or tol_pct < 0:
        raise ValueError(f"tol_pct must be >= 0, got {tol_pct!r}")
    out = lines.copy()
    if "pd_tags" not in out.columns:
        out["pd_tags"] = ""
    if "timeframes" not in out.columns:
        out["timeframes"] = out["timeframe"]
    if out.empty:
        out["merged_count"] = pd.Series(dtype=int)
        out["merged_from"] = pd.Series(dtype=str)
        return out

    is_pd = out["pd_tags"].fillna("") != ""
    parts = [(out[is_pd], 0.0)]
    rest = out[~is_pd]
    if close is None:
        parts.append((rest, tol_pct))
    else:
        c, p = round(float(close), 2), rest["price"].round(2)
        parts += [(rest[p < c], tol_pct), (rest[p == c], 0.0), (rest[p > c], tol_pct)]
    merged = [_merge_frame(df, tol) for df, tol in parts if not df.empty]
    return (pd.concat(merged, ignore_index=True)
            .sort_values(["price", "pivot_time"], kind="stable").reset_index(drop=True))


def _merge_frame(out: pd.DataFrame, tol_pct: float) -> pd.DataFrame:
    """Rule A merge of one partition (see merge_close_lines)."""
    out = out.sort_values(["price", "pivot_time"], kind="stable").reset_index(drop=True)
    group_id, start, gid = [], None, -1
    for p in out["price"]:
        if start is None or p > start * (1 + tol_pct / 100.0):
            gid, start = gid + 1, p
        group_id.append(gid)
    out["_g"] = group_id

    kept = []
    for _, g in out.groupby("_g", sort=True):
        k = _keep_index(g)
        row = out.loc[k].copy()
        others = g.drop(index=k)
        tfs = set(" ".join(g["timeframes"]).split())
        row["timeframes"] = " ".join(t for t in TF_ORDER if t in tfs)
        tags = set(" ".join(g["pd_tags"]).split())
        row["pd_tags"] = " ".join(tag for _, tag in PD_FIELDS if tag in tags)
        # A second merge (trading ladder) carries the first merge's absorbed lines forward.
        prior_count = g["merged_count"].fillna(1).astype(int) if "merged_count" in g else pd.Series(1, index=g.index)
        prior_from = g["merged_from"].fillna("") if "merged_from" in g else pd.Series("", index=g.index)
        row["merged_count"] = int(prior_count.sum())
        parts = [f"{r['price']:,.2f} {r['timeframe']} {r['kind']} {r['pivot_time']:%d %b %Y %H:%M}"
                 for _, r in others.iterrows()
                 if round(r["price"], 2) != round(row["price"], 2)]   # same price: shown in timeframes
        parts += [p for s in prior_from if s for p in s.split("; ")]
        row["merged_from"] = "; ".join(dict.fromkeys(parts))      # unique, order kept
        kept.append(row)
    return pd.DataFrame(kept).drop(columns="_g").reset_index(drop=True)


def number_lines(lines: pd.DataFrame, close: float) -> pd.DataFrame:
    """Add `side` (R / S / AT), `rank` (1 = nearest, None for AT) and `label`.

    Returns a new DataFrame sorted top of the chart first (highest price first).
    Equal prices stay separate lines; the newer one is numbered first.
    """
    if close is None or not math.isfinite(float(close)) or float(close) <= 0:
        raise ValueError(f"close must be a positive number, got {close!r}")
    c = round(float(close), 2)
    out = lines.copy()
    p = out["price"].round(2)
    out["side"] = "AT"
    out.loc[p > c, "side"] = "R"
    out.loc[p < c, "side"] = "S"
    out["rank"] = None

    above = out[out["side"] == "R"].sort_values(["price", "pivot_time"], ascending=[True, False])
    below = out[out["side"] == "S"].sort_values(["price", "pivot_time"], ascending=[False, False])
    out.loc[above.index, "rank"] = range(1, len(above) + 1)
    out.loc[below.index, "rank"] = range(1, len(below) + 1)

    out["label"] = out.apply(
        lambda r: "AT" if r["side"] == "AT" else f"{r['side']}{int(r['rank'])}", axis=1
    ) if not out.empty else pd.Series(dtype=str)

    order = pd.concat([above.iloc[::-1], out[out["side"] == "AT"], below])
    return out.loc[order.index].reset_index(drop=True)


def timeframe_lines(swings: pd.DataFrame, timeframe: str, candle_times: pd.Series,
                    tol_pct: float, prev_day: Optional[dict] = None,
                    close: Optional[float] = None) -> pd.DataFrame:
    """Steps 1-3 and 6 for one timeframe (not numbered): swing lines, recency,
    PD tags, merge (never across `close` when given)."""
    lines = swing_lines(swings, timeframe)
    lines = keep_recent(lines, recent_since(candle_times, RECENT_TRADING_DAYS.get(timeframe)))
    return merge_close_lines(pd_tags(lines, prev_day), tol_pct, close)


def horizontal_sr(swings: pd.DataFrame, timeframe: str, close: float,
                  prev_day: Optional[dict] = None, tol_pct: float = 0.0,
                  candle_times: Optional[pd.Series] = None) -> pd.DataFrame:
    """One timeframe's numbered ladder. Without candle_times no recency filter;
    tol_pct 0 merges only identical prices."""
    lines = swing_lines(swings, timeframe)
    if candle_times is not None:
        lines = keep_recent(lines, recent_since(candle_times, RECENT_TRADING_DAYS.get(timeframe)))
    return number_lines(merge_close_lines(pd_tags(lines, prev_day), tol_pct, close), close)


def trading_ladder(per_timeframe: list[pd.DataFrame], close: float, tol_pct: float) -> pd.DataFrame:
    """Step 5: all timeframes' lines merged with `tol_pct` and numbered from `close`."""
    frames = [f for f in per_timeframe if f is not None and not f.empty]
    if not frames:
        return number_lines(pd.DataFrame(columns=["timeframe", "kind", "price", "pivot_time",
                                                  "is_locked", "pd_tags", "timeframes"]), close)
    combined = pd.concat(frames, ignore_index=True)
    return number_lines(merge_close_lines(combined, tol_pct, close), close)
