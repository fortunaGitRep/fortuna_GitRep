"""
Zig Zag settings per timeframe for Fortuna swing detection.

Values chosen by Ash on his tv.dhan.co chart (14 Oct 2026). Change values here
only; the swing code reads this table and never hardcodes a setting.

deviation_pct : minimum reversal, in percent of the last swing price, before
                Zig Zag changes direction (TradingView "Deviation (%)").
depth         : TradingView "Depth" input. The TradingView library halves it
                internally (bars checked each side = max(2, depth // 2)).
equal_tol_pct : two swings of the same kind count as EQUAL (double/triple top
                or bottom) when within this percent of each other. Agreed
                starting values (15 Oct 2026): 5m loosened to 0.05% (~11 Nifty
                pts), daily kept at 0.5% (~113 pts), 15m/60m on the same scale
                between them. Checking example pairs on the chart is a deferred
                open item.
status        : "chosen"  = confirmed by Ash on his chart
                "derived" = fitted between Ash's two choices (5m, 1D)
                            with one power-law scale; no study gives per-TF
                            values (directional-change research: no
                            threshold is privileged)
"""

ZIGZAG_SETTINGS = {
    "1mo": {"deviation_pct": 5.0,  "depth": 10, "equal_tol_pct": 0.50, "status": "chosen"},
    "1w":  {"deviation_pct": 5.0,  "depth": 10, "equal_tol_pct": 0.50, "status": "chosen"},
    "1d":  {"deviation_pct": 5.0,  "depth": 10, "equal_tol_pct": 0.50, "status": "chosen"},
    "60m": {"deviation_pct": 1.25, "depth": 10, "equal_tol_pct": 0.20, "status": "derived"},
    "15m": {"deviation_pct": 0.5,  "depth": 10, "equal_tol_pct": 0.10, "status": "derived"},
    "5m":  {"deviation_pct": 0.2,  "depth": 10, "equal_tol_pct": 0.05, "status": "chosen"},
}


def _row(timeframe: str) -> dict:
    if timeframe not in ZIGZAG_SETTINGS:
        raise ValueError(
            f"No Zig Zag settings for timeframe '{timeframe}'. "
            f"Known: {sorted(ZIGZAG_SETTINGS)}"
        )
    return ZIGZAG_SETTINGS[timeframe]


def get_zigzag_settings(timeframe: str) -> tuple[float, int]:
    """Return (deviation_pct, depth) for a timeframe key such as "1d" or "5m"."""
    row = _row(timeframe)
    return row["deviation_pct"], row["depth"]


def get_equal_tolerance(timeframe: str) -> float:
    """Equal-swing tolerance in percent for a timeframe, e.g. 0.05 for 5m."""
    return _row(timeframe)["equal_tol_pct"]
