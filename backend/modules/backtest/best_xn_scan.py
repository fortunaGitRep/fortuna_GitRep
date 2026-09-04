"""
best_xn_scan.py — find the best X% within N days per stock, ranked so that
"shorter N for smaller X" wins.

WHY MONTHLY-COMPOUNDED RANKING (this encodes Ash's rule, doesn't assume it)
--------------------------------------------------------------------------
A raw "biggest X%" ranking would always prefer long holds. But the goal is
money-per-month: a small, fast swing you can repeat many times in a month can
beat a big, slow one you can only do once or twice. So each (X%, N-days)
opportunity is converted to an equivalent MONTHLY return:

    trades_per_month = ~21 trading days / N
    monthly_return   = (1 + X/100) ** trades_per_month - 1

Example: +3% in 4 days  -> (1.03)^(21/4)  - 1 = ~+16.9% / month
         +6% in 20 days -> (1.06)^(21/20) - 1 = ~+6.3%  / month
The fast small swing ranks HIGHER — exactly the intended behaviour.

WHAT IT MEASURES (this pass = outcome definition ONLY)
------------------------------------------------------
For each entry day t, look forward up to N_MAX daily bars and find the FIRST day
the HIGH reaches the best achievable gain over that window, measured from t's
close. This is the forward-looking "how good a swing was available if you'd
bought here" — the label. Entry/exit/stop TRIGGERS come later; this step just
defines what a "good swing buy outcome" is and finds where they occurred.

Two views produced:
  1. Per-(stock, entry-day) opportunity rows (the raw labelled events).
  2. Per-stock summary: best monthly-equivalent swing, and the (X, N) sweet spot.

Data: daily bars from R2 Parquet (one file per ISIN, timeframe col == '1d'),
read through the shared modules.market_data.read_ohlcv accessor — this module
never touches R2 directly (single-source-of-truth read layer).

Adjust the knobs at the top (TRADING_DAYS_PER_MONTH, N_MAX, X_FLOOR_PCT) as you tune.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


from modules.market_data.upstox.read_ohlcv import read_ohlcv


TRADING_DAYS_PER_MONTH = 21          # NSE ~21 trading days/month
N_MAX = 15                           # max look-forward horizon (~3 trading weeks)
X_FLOOR_PCT = 1.0                    # ignore opportunities smaller than this


# ---------------------------------------------------------------------------
# Core label computation
# ---------------------------------------------------------------------------

def monthly_equiv(x_pct: float, n_days: int) -> float:
    """Convert an (X%, N-day) swing to its monthly-compounded-return equivalent."""
    if n_days <= 0:
        return 0.0
    trades_per_month = TRADING_DAYS_PER_MONTH / n_days
    return ((1.0 + x_pct / 100.0) ** trades_per_month - 1.0) * 100.0


def best_swings_for_stock(
    isin: str,
    bars: pd.DataFrame,
    n_max: int = N_MAX,
    x_floor: float = X_FLOOR_PCT,
) -> pd.DataFrame:
    """For every entry day, find the best forward swing within n_max days.

    'Best' = the day within the window whose HIGH gives the largest gain over the
    entry close, where 'largest' is judged by MONTHLY-EQUIVALENT return (so a
    smaller-but-faster peak can beat a bigger-but-slower one).

    Returns one row per entry day that clears x_floor, with columns:
        isin, entry_date, entry_close, best_x_pct, n_days, exit_high,
        exit_date, monthly_equiv_pct
    """
    closes = bars["close"].to_numpy(dtype=float)
    highs = bars["high"].to_numpy(dtype=float)
    dates = bars["date"].to_numpy()
    n = len(bars)

    out_rows: list[dict] = []

    for t in range(n - 1):
        entry_close = closes[t]
        if entry_close <= 0:
            continue

        # scan the forward window [t+1 .. t+n_max]
        best_me = -1.0
        best = None
        upper = min(t + n_max, n - 1)
        for k in range(t + 1, upper + 1):
            n_days = k - t
            x_pct = (highs[k] - entry_close) / entry_close * 100.0
            if x_pct < x_floor:
                continue
            me = monthly_equiv(x_pct, n_days)
            if me > best_me:
                best_me = me
                best = (x_pct, n_days, highs[k], dates[k])

        if best is None:
            continue

        x_pct, n_days, exit_high, exit_date = best
        out_rows.append(
            {
                "isin": isin,
                "entry_date": dates[t],
                "entry_close": entry_close,
                "best_x_pct": round(x_pct, 3),
                "n_days": int(n_days),
                "exit_high": exit_high,
                "exit_date": exit_date,
                "monthly_equiv_pct": round(best_me, 3),
            }
        )

    return pd.DataFrame(out_rows)


def summarise_stock(opps: pd.DataFrame) -> dict:
    """Collapse a stock's opportunity rows into a single sweet-spot summary."""
    if opps.empty:
        return {}
    top = opps.loc[opps["monthly_equiv_pct"].idxmax()]
    return {
        "isin": top["isin"],
        "sweet_x_pct": top["best_x_pct"],
        "sweet_n_days": int(top["n_days"]),
        "best_monthly_equiv_pct": top["monthly_equiv_pct"],
        "median_monthly_equiv_pct": round(float(opps["monthly_equiv_pct"].median()), 3),
        "n_opportunities": len(opps),
        "median_n_days": int(opps["n_days"].median()),
        "median_x_pct": round(float(opps["best_x_pct"].median()), 3),
    }


def scan_watchlist(
    isins: list[str],
    n_max: int = N_MAX,
    x_floor: float = X_FLOOR_PCT,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Run the best-X%/N-days scan across a watchlist of ISINs.

    Returns:
        (all_opportunities, per_stock_summary)
        per_stock_summary is sorted by best_monthly_equiv_pct descending — the
        fastest-compounding swings float to the top.
    """
    all_opps: list[pd.DataFrame] = []
    summaries: list[dict] = []

    memo: dict = {}  # per-run in-memory reuse; dies when this call returns

    for isin in isins:
        try:
            bars = read_ohlcv(isin, timeframe="1d", domain="universe", memo=memo)
        except Exception as exc:  # missing/illiquid parquet -> skip, don't abort
            print(f"[skip] {isin}: {exc}")
            continue
        if len(bars) < n_max + 2:
            continue
        opps = best_swings_for_stock(isin, bars, n_max=n_max, x_floor=x_floor)
        if opps.empty:
            continue
        all_opps.append(opps)
        summaries.append(summarise_stock(opps))

    opportunities = (
        pd.concat(all_opps, ignore_index=True) if all_opps else pd.DataFrame()
    )
    summary = (
        pd.DataFrame(summaries)
        .sort_values("best_monthly_equiv_pct", ascending=False)
        .reset_index(drop=True)
        if summaries
        else pd.DataFrame()
    )
    return opportunities, summary


# ---------------------------------------------------------------------------
# Watchlist registry + orchestration
# ---------------------------------------------------------------------------
# One entry per watchlist: name -> screen function returning a ScreenResult.
# Add WL3/WL4 here (one line each) once their screen functions exist; nothing
# else changes. Reports are INDEPENDENT per watchlist — a stock in both WL2 and
# WL3 is scanned and reported in each, by design (the point is to compare how
# each watchlist's stocks behave).

from modules.backtest.watchlist_screen import screen_watchlist_2

WATCHLISTS = {
    "WL2": screen_watchlist_2,
    # "WL3": screen_watchlist_3,   # add when the screen exists
    # "WL4": screen_watchlist_4,
}


def run_all_watchlists(
    n_max: int = N_MAX,
    x_floor: float = X_FLOOR_PCT,
) -> dict[str, tuple[pd.DataFrame, pd.DataFrame]]:
    """Screen + scan every registered watchlist independently.

    Returns:
        dict keyed by watchlist name -> (opportunities, summary). Each watchlist
        is screened to its ISINs, then scanned; a shared stock appears in every
        watchlist it belongs to (independent reports).
    """
    results: dict[str, tuple[pd.DataFrame, pd.DataFrame]] = {}
    for name, screen_fn in WATCHLISTS.items():
        screened = screen_fn()
        print(f"{name} -> {len(screened)} stocks; scanning best X% within "
              f"{n_max} days...")
        opps, summary = scan_watchlist(
            screened.isins, n_max=n_max, x_floor=x_floor
        )
        results[name] = (opps, summary)
    return results


def _print_report(name: str, opps: pd.DataFrame, summary: pd.DataFrame) -> None:
    """Print one labelled report block for a single watchlist."""
    print(f"\n{'=' * 60}\n=== {name} ===\n{'=' * 60}")
    print(f"Total opportunities: {len(opps)}")
    if summary.empty:
        print("(no summary — no stocks scanned)")
        return
    print("\nTop 15 stocks by fastest-compounding swing:")
    cols = ["isin", "sweet_x_pct", "sweet_n_days",
            "best_monthly_equiv_pct", "median_monthly_equiv_pct",
            "median_x_pct", "median_n_days", "n_opportunities"]
    print(summary[cols].head(15).to_string(index=False))


if __name__ == "__main__":
    all_results = run_all_watchlists()
    for name, (opps, summary) in all_results.items():
        _print_report(name, opps, summary)
