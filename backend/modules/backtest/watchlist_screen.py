"""
watchlist_screen.py — in-memory Watchlist 2 (fundamental_threshold_stocks).

WL2 is a DERIVED, in-memory list: screen f_fundamentals_metrics on the quality/
valuation thresholds and return the surviving ISINs as a DataFrame. Nothing is
written to a table — recompute on demand (inputs are stored, output is cheap).

Ash's 15 target criteria vs what f_fundamentals_metrics currently holds
(per Build-Log 2026-08-25/26: ~10 available, 5 reserved-NULL gap columns):

    CRITERION                       COLUMN                       STATUS
    market_cap > 1000               market_cap_cr                MISSING (reserved NULL)
    debt_to_equity < 0.5            debt_to_equity               MISSING (reserved NULL)
    interest_coverage > 3           interest_coverage            MISSING (reserved NULL)
    pledged_pct < 10                pledge_pct                   MISSING (reserved NULL)
    roce > 12                       roce                         AVAILABLE
    roe > 12                        roe                          AVAILABLE
    sales_growth_5y > 10            revenue_growth_5y            MISSING (reserved NULL)
    profit_growth_5y > 10           net_profit_growth_5y         MISSING (reserved NULL)
    sales_growth(1y) > 0            revenue_growth_1y            AVAILABLE
    profit_growth(1y) > 0           net_profit_growth_1y         AVAILABLE
    pe > 0                          pe                           AVAILABLE
    pe < 60                         pe                           AVAILABLE
    pb < 8                          pb                           AVAILABLE
    sales_growth_3y > 12            revenue_growth_3y            AVAILABLE
    profit_growth_3y > 12           net_profit_growth_3y         AVAILABLE

Only AVAILABLE criteria are applied. MISSING ones are declared in the returned
metadata so a caller (and the backtest) knows the screen is partial, not silently
dropped. When the 5 gap columns get filled by their later jobs, move them from
MISSING_CRITERIA to CRITERIA and nothing else changes.

NOTE ON COLUMN NAMES: adjust the COLUMN strings below to match the exact column
names in f_fundamentals_metrics if they differ. Everything else is name-agnostic.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from db.supabase_client import get_supabase  # documented shared client


# ---------------------------------------------------------------------------
# Criteria definitions
# ---------------------------------------------------------------------------
# Each criterion maps to one server-side SQL filter (col > / < threshold).
# A stock must pass EVERY applied criterion (AND-chained) to survive.
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Criterion:
    label: str
    column: str
    op: str          # 'gt' or 'lt' — maps to a PostgREST .gt()/.lt() filter
    threshold: float


# Criteria whose columns are populated today -> applied.
CRITERIA: list[Criterion] = [
    Criterion("ROCE > 12",              "roce",                 "gt", 12.0),
    Criterion("ROE > 12",               "roe",                  "gt", 12.0),
    Criterion("Sales growth 1Y > 0",    "revenue_growth_1y",    "gt", 0.0),
    Criterion("Profit growth 1Y > 0",   "net_profit_growth_1y", "gt", 0.0),
    Criterion("PE > 0",                 "pe",                   "gt", 0.0),
    Criterion("PE < 60",                "pe",                   "lt", 60.0),
    Criterion("PB < 8",                 "pb",                   "lt", 8.0),
    Criterion("Sales growth 3Y > 12",   "revenue_cagr_3y",      "gt", 12.0),
    Criterion("Profit growth 3Y > 12",  "net_profit_cagr_3y",   "gt", 12.0),
]

# Criteria whose columns are reserved-NULL today -> declared, NOT applied.
MISSING_CRITERIA: list[str] = [
    "Market cap > 1000 (market_cap_cr)",
    "Debt/Equity < 0.5 (debt_to_equity)",
    "Interest coverage > 3 (interest_coverage)",
    "Pledged % < 10 (pledge_pct)",
    "Sales growth 5Y > 10 (revenue_growth_5y)",
    "Profit growth 5Y > 10 (net_profit_growth_5y)",
]


@dataclass
class ScreenResult:
    isins: list[str]
    frame: pd.DataFrame                       # surviving rows (isin only)
    applied: list[str] = field(default_factory=list)
    skipped_missing: list[str] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.isins)


# ---------------------------------------------------------------------------
# Screen
# ---------------------------------------------------------------------------

def screen_watchlist_2() -> ScreenResult:
    """Apply the available fundamental thresholds server-side; return ISINs.

    Builds the WHERE from the CRITERIA list so Supabase (PostgREST) does the
    filtering across all stocks and returns ONLY survivors — not the full table.
    NULLs are excluded automatically: `col > 12` is not true when col IS NULL,
    which matches the "can't confirm quality -> exclude" stance.

    Returns:
        ScreenResult with the surviving ISIN list and metadata on which criteria
        were applied vs skipped-missing (the reserved-NULL gap columns).
    """
    sb = get_supabase()
    query = sb.table("f_fundamentals_metrics").select("isin")

    applied_labels: list[str] = []
    for crit in CRITERIA:
        if crit.op == "gt":
            query = query.gt(crit.column, crit.threshold)
        elif crit.op == "lt":
            query = query.lt(crit.column, crit.threshold)
        else:
            raise ValueError(f"unknown op {crit.op!r}")
        applied_labels.append(crit.label)

    resp = query.execute()
    survivors = pd.DataFrame(resp.data or [])

    isins = (
        survivors["isin"].astype(str).tolist()
        if not survivors.empty and "isin" in survivors.columns
        else []
    )

    return ScreenResult(
        isins=isins,
        frame=survivors,
        applied=applied_labels,
        skipped_missing=list(dict.fromkeys(MISSING_CRITERIA)),  # dedup
    )


if __name__ == "__main__":
    res = screen_watchlist_2()
    print(f"WL2 -> {len(res)} survivors")
    print(f"Applied ({len(res.applied)}): " + "; ".join(res.applied))
    print(f"Skipped-missing ({len(res.skipped_missing)}): "
          + "; ".join(res.skipped_missing))
    print("First 20 ISINs:", res.isins[:20])
