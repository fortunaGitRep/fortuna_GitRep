"""
modules/market_data/upstox/fundamentals_store.py

Store layer for company fundamentals: fetches the 8 Upstox fundamentals endpoints for
a stock, PARSES the messy responses into the 3 tables (profile / metrics / statements),
and upserts to Supabase. Imports the shared Supabase client + the auth client's
request_get; does not build its own connections.

The parsing/computing is the meat here (the spike showed the responses are nested and
irregular). Key transforms:
  * key-ratios: array of {name, company_value, sector_value} -> named numeric columns.
    Strip '%' CONDITIONALLY (only ROA/ROE/ROCE carry it; P/E, P/B, Quick, EV/EBITDA don't).
  * income statement: pull CORE "Revenue" line-item (NOT "Total Revenue" — that includes
    other income; "sales" screening means core operating revenue). Also net profit, EPS.
  * growth: COMPUTE 1Y + 3Y from core Revenue / net profit year-over-year (the API's
    ready-made change% is on Total Revenue, wrong basis). 3Y is deepest (4 yrs history).
  * holdings: latest quarter's promoter/fii/dii/mutual_fund %.
  * profile: sector, description, SECTOR market cap.
  * statements: full responses dumped to JSONB as-is (Tier-2 archive).
  * competitors: fetched by INSTRUMENT_KEY (NSE_EQ|ISIN), not bare ISIN — the API rejects
    ISIN for that one endpoint (spike showed UDAPI100011).

RESERVED GAP COLUMNS (market_cap_cr, shares_outstanding, face_value, pledge_pct,
debt_to_equity, interest_coverage, revenue_growth_5y, net_profit_growth_5y) are left
untouched (NULL) — filled by separate NSE/external jobs later.

Standards: single responsibility (fundamentals persistence), fetch-first, defensive
parsing (tolerate missing fields/endpoints — a stock may lack some data), structured
logging, dataclass result with ok flag. VERIFY-FIRST: __main__ parses Reliance and
PRINTS the computed metrics row (no DB write) so numbers can be checked before bulk.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from db.supabase_client import get_supabase
from modules.market_data.upstox.upstox_auth_client import request_get

logger = logging.getLogger(__name__)

_PROFILE_TABLE = "f_fundamentals_profile"
_METRICS_TABLE = "f_fundamentals_metrics"
_STATEMENTS_TABLE = "f_fundamentals_statements"


@dataclass
class FundamentalsResult:
    ok: bool
    isin: str
    error: Optional[str] = None
    rate_limited: bool = False           # True if failure was due to 429 (retryable, NOT no-data)
    metrics: dict = field(default_factory=dict)   # the parsed metrics row (for inspection)


# --- Small parse helpers ---------------------------------------------------

def _num(s: Any) -> Optional[float]:
    """Parse a possibly-%/+/comma-laden string or number to float, or None."""
    if s is None:
        return None
    if isinstance(s, (int, float)):
        return float(s)
    txt = str(s).strip().replace("%", "").replace("+", "").replace(",", "")
    if txt in ("", "-", "NA", "N/A", "null", "None"):
        return None
    try:
        return float(txt)
    except ValueError:
        return None


def _cagr(latest: Optional[float], earliest: Optional[float], years: int) -> Optional[float]:
    """Compound annual growth rate as a percentage, or None if not meaningful.
    CAGR requires BOTH endpoints positive: growth from/to a negative value has no
    meaningful compound rate, and mathematically (negative)**(1/years) yields a COMPLEX
    number (which also isn't JSON-serialisable). So we return None unless both > 0.
    (A loss-making year -> None here; the raw values are still stored for reference.)"""
    if (latest is None or earliest is None
            or latest <= 0 or earliest <= 0 or years <= 0):
        return None
    try:
        result = ((latest / earliest) ** (1.0 / years) - 1.0) * 100.0
        # Defensive: if anything still produced a complex, discard it.
        if isinstance(result, complex):
            return None
        return result
    except (ValueError, ZeroDivisionError):
        return None


def _yoy(latest: Optional[float], prior: Optional[float]) -> Optional[float]:
    """Year-over-year growth % (latest vs prior), or None. Uses abs(prior) as base so a
    swing works directionally; None if prior is 0."""
    if latest is None or prior is None or prior == 0:
        return None
    return (latest - prior) / abs(prior) * 100.0


def _line_item_series(full_statement: list, particular: str) -> list[tuple[str, float]]:
    """From a statement's full_statement list, return [(period, value), ...] for the
    named line-item, newest-first as the API returns it. Empty if not found."""
    for row in full_statement or []:
        if str(row.get("particular", "")).strip().lower() == particular.strip().lower():
            out = []
            for h in row.get("history", []):
                v = _num(h.get("value"))
                p = h.get("period")
                if v is not None and p:
                    out.append((p, v))
            return out
    return []


def _category_series(blocks: list, category: str) -> list[tuple[str, float]]:
    """From an income_statement/cash_flow 'category' list, return [(period, value), ...]
    for the named category (revenue/net_profit/etc.), newest-first."""
    for blk in blocks or []:
        if str(blk.get("category", "")).strip().lower() == category.strip().lower():
            out = []
            for h in blk.get("history", []):
                v = _num(h.get("value"))
                p = h.get("period")
                if v is not None and p:
                    out.append((p, v))
            return out
    return []


# --- Fetch the 8 endpoints -------------------------------------------------

def _fetch_all_endpoints(isin: str, instrument_key: str,
                         screening_only: bool = False) -> tuple[dict[str, Any], bool]:
    """Fetch the fundamentals endpoints. Returns (data_dict, rate_limited).

    screening_only=True fetches ONLY the 4 endpoints that feed the profile+metrics
    (screening) tables: profile, key-ratios, income-statement, share-holdings. The
    Tier-2 archive endpoints (balance-sheet, cash-flow, corporate-actions, competitors)
    are skipped — fetched later, only for watchlist stocks. This halves calls/stock
    (8 -> 4), roughly halving the bulk run.

    rate_limited is True if ANY endpoint returned HTTP 429 after the auth client's
    retries — meaning the failure is a rate-limit (retryable), NOT missing data. The
    caller uses this to keep the stock retryable rather than marking it a permanent
    no-data failure (which would pollute the ETF signal).
    """
    saw_429 = {"hit": False}

    def _get(path: str, params: dict | None = None) -> Optional[Any]:
        try:
            resp = request_get(path, params=params)
            if resp.status_code == 429:
                saw_429["hit"] = True
                logger.warning("%s -> HTTP 429 (rate limit) for %s", path, isin)
                return None
            if resp.status_code != 200:
                logger.warning("%s -> HTTP %s for %s", path, resp.status_code, isin)
                return None
            body = resp.json()
            if body.get("status") != "success":
                return None
            return body.get("data")
        except Exception as exc:  # noqa: BLE001
            logger.warning("%s failed for %s: %s", path, isin, exc)
            return None

    base = f"/v2/fundamentals/{isin}"
    fs = {"type": "consolidated", "fs": "true"}

    # The 4 screening endpoints (always fetched).
    data: dict[str, Any] = {
        "profile":          _get(f"{base}/profile"),
        "key_ratios":       _get(f"{base}/key-ratios"),
        "income_statement": _get(f"{base}/income-statement", fs),
        "holdings":         _get(f"{base}/share-holdings"),
    }
    # Tier-2 archive endpoints (skipped in screening_only mode).
    if not screening_only:
        data["balance_sheet"]     = _get(f"{base}/balance-sheet", fs)
        data["cash_flow"]         = _get(f"{base}/cash-flow", fs)
        data["corporate_actions"] = _get(f"{base}/corporate-actions")
        # competitors wants INSTRUMENT_KEY, not ISIN (spike: UDAPI100011 on ISIN)
        data["competitors"]       = _get(f"/v2/fundamentals/{instrument_key}/competitors")

    return data, saw_429["hit"]


# --- Parse into the metrics row --------------------------------------------

def _parse_key_ratios(data: Optional[list]) -> dict:
    """key-ratios array -> {pe, pb, roa, roe, roce, quick_ratio, ev_ebitda, sector_pe}."""
    name_map = {
        "P/E": "pe", "P/B": "pb", "ROA": "roa", "ROE": "roe", "ROCE": "roce",
        "Quick Ratio": "quick_ratio", "EV/EBITDA": "ev_ebitda",
    }
    out: dict = {k: None for k in
                 ("pe", "pb", "roa", "roe", "roce", "quick_ratio", "ev_ebitda", "sector_pe")}
    for item in data or []:
        col = name_map.get(str(item.get("name", "")).strip())
        if col:
            out[col] = _num(item.get("company_value"))
            if col == "pe":
                out["sector_pe"] = _num(item.get("sector_value"))
    return out


def _period_key(period: str) -> tuple[int, int]:
    """Parse a period label like 'Mar 2026' / 'Jun 2026' into a sortable (year, month)
    so ordering never depends on the API's array order. Unknown -> (0,0) (sorts first,
    effectively oldest, so it won't be mistaken for latest)."""
    months = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
              "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12}
    try:
        parts = str(period).strip().split()
        mon = months.get(parts[0][:3].lower(), 0)
        yr = int(parts[1])
        return (yr, mon)
    except (IndexError, ValueError):
        return (0, 0)


def _sort_newest_first(series: list[tuple[str, float]]) -> list[tuple[str, float]]:
    """Sort [(period, value)] strictly newest-first by parsed period, so downstream
    growth/CAGR never rely on the API returning a particular order."""
    return sorted(series, key=lambda pv: _period_key(pv[0]), reverse=True)


def _parse_income(data: Optional[dict]) -> dict:
    """income statement -> revenue/net_profit/eps latest + computed growth.

    REVENUE SOURCE (handles two statement structures):
      * Manufacturers/services: full_statement has a core 'Revenue' line-item (excl
        other income) AND a 'Total Revenue'. We prefer core 'Revenue' (true sales).
      * Banks/financials: NO plain 'Revenue' line-item — only 'Total Revenue'. For these
        we fall back to the 'Total Revenue' line-item (their reported top line). Without
        this fallback, all banks/NBFCs got NULL revenue (~260 major financials missing).
    Fallback order: core 'Revenue' line-item -> 'Total Revenue' line-item.
    Growth is computed from whichever series we used, so it's self-consistent.
    """
    out: dict = {k: None for k in
                 ("revenue_cr", "net_profit_cr", "eps_basic", "latest_period",
                  "revenue_growth_1y", "net_profit_growth_1y",
                  "revenue_cagr_3y", "net_profit_cagr_3y")}
    if not data:
        return out
    full = data.get("full_statement", [])
    cats = data.get("income_statement", [])

    # Prefer core 'Revenue' (manufacturers); fall back to 'Total Revenue' (banks).
    rev = _sort_newest_first(_line_item_series(full, "Revenue"))
    if not rev:
        rev = _sort_newest_first(_line_item_series(full, "Total Revenue"))
    npf = _sort_newest_first(_category_series(cats, "net_profit"))
    eps = _sort_newest_first(_line_item_series(full, "EPS - Basic"))

    if rev:
        out["revenue_cr"] = rev[0][1]
        out["latest_period"] = rev[0][0]
        if len(rev) >= 2:
            out["revenue_growth_1y"] = _yoy(rev[0][1], rev[1][1])
        if len(rev) >= 4:  # 4 periods spanning 3 years -> 3Y CAGR (latest vs oldest)
            out["revenue_cagr_3y"] = _cagr(rev[0][1], rev[-1][1], 3)
    if npf:
        out["net_profit_cr"] = npf[0][1]
        out["latest_period"] = out["latest_period"] or npf[0][0]
        if len(npf) >= 2:
            out["net_profit_growth_1y"] = _yoy(npf[0][1], npf[1][1])
        if len(npf) >= 4:
            out["net_profit_cagr_3y"] = _cagr(npf[0][1], npf[-1][1], 3)
    if eps:
        out["eps_basic"] = eps[0][1]
    return out


def _parse_holdings(data: Optional[list]) -> dict:
    """share-holdings -> latest-quarter promoter/fii/dii/mutual_fund % + the period.
    Sorts each category's history explicitly newest-first (parsed period), not by array
    order, so 'latest' is truly the most recent quarter."""
    out = {k: None for k in
           ("promoter_pct", "fii_pct", "dii_pct", "mutual_fund_pct", "holdings_period")}
    cat_map = {"promoters": "promoter_pct", "fii": "fii_pct",
               "other_dii": "dii_pct", "mutual_funds": "mutual_fund_pct"}
    for blk in data or []:
        col = cat_map.get(str(blk.get("category", "")).strip())
        if not col:
            continue
        series = [(h.get("period"), _num(h.get("value")))
                  for h in blk.get("history", []) if h.get("period")]
        series = _sort_newest_first([(p, v) for p, v in series if v is not None])
        if series:
            out[col] = series[0][1]
            if out["holdings_period"] is None:
                out["holdings_period"] = series[0][0]
    return out


def _parse_profile(data: Optional[dict]) -> dict:
    out = {"sector": None, "company_profile": None,
           "sector_mcap_inr_cr": None, "sector_mcap_usd_bn": None}
    if not data:
        return out
    out["sector"] = data.get("sector")
    out["company_profile"] = data.get("company_profile")
    inr = data.get("sector_market_cap_inr") or {}
    usd = data.get("sector_market_cap_usd") or {}
    out["sector_mcap_inr_cr"] = _num(inr.get("value"))
    out["sector_mcap_usd_bn"] = _num(usd.get("value"))
    return out


def build_rows(isin: str, endpoints: dict) -> tuple[dict, dict, dict]:
    """Assemble the three table rows (profile, metrics, statements) from fetched data."""
    profile = _parse_profile(endpoints.get("profile"))
    ratios = _parse_key_ratios(endpoints.get("key_ratios"))
    income = _parse_income(endpoints.get("income_statement"))
    holdings = _parse_holdings(endpoints.get("holdings"))

    profile_row = {"isin": isin, **profile}
    metrics_row = {"isin": isin, **ratios, **income, **holdings}
    statements_row = {
        "isin": isin,
        "balance_sheet": endpoints.get("balance_sheet"),
        "cash_flow": endpoints.get("cash_flow"),
        "income_statement": endpoints.get("income_statement"),
        "holdings": endpoints.get("holdings"),
        "corporate_actions": endpoints.get("corporate_actions"),
        "competitors": endpoints.get("competitors"),
    }
    return profile_row, metrics_row, statements_row


# --- Store (upsert) --------------------------------------------------------

def _fetch_tier2_endpoints(isin: str, instrument_key: str) -> tuple[dict[str, Any], bool]:
    """Fetch ONLY the 4 Tier-2 archive endpoints (balance-sheet, cash-flow,
    corporate-actions, competitors). Returns (data, rate_limited). Kept separate from
    _fetch_all_endpoints so the proven screening path is untouched (Rule #7)."""
    saw_429 = {"hit": False}

    def _get(path: str, params: dict | None = None) -> Optional[Any]:
        try:
            resp = request_get(path, params=params)
            if resp.status_code == 429:
                saw_429["hit"] = True
                logger.warning("%s -> HTTP 429 (rate limit) for %s", path, isin)
                return None
            if resp.status_code != 200:
                logger.warning("%s -> HTTP %s for %s", path, resp.status_code, isin)
                return None
            body = resp.json()
            if body.get("status") != "success":
                return None
            return body.get("data")
        except Exception as exc:  # noqa: BLE001
            logger.warning("%s failed for %s: %s", path, isin, exc)
            return None

    base = f"/v2/fundamentals/{isin}"
    fs = {"type": "consolidated", "fs": "true"}
    data = {
        "balance_sheet":     _get(f"{base}/balance-sheet", fs),
        "cash_flow":         _get(f"{base}/cash-flow", fs),
        "corporate_actions": _get(f"{base}/corporate-actions"),
        # competitors wants INSTRUMENT_KEY, not ISIN (spike: UDAPI100011 on ISIN)
        "competitors":       _get(f"/v2/fundamentals/{instrument_key}/competitors"),
    }
    return data, saw_429["hit"]


def store_tier2_statements(isin: str, instrument_key: str) -> FundamentalsResult:
    """Fetch the 4 Tier-2 archive endpoints and upsert ONLY the f_fundamentals_statements
    row (balance_sheet/cash_flow/corporate_actions/competitors JSONB). Does NOT touch the
    already-populated profile/metrics tables (screening data stays as-is).

    Used by the one-time Tier-2 archival backfill. Distinguishes rate-limit (retryable)
    from genuine no-data via result.rate_limited. A stock with none of the 4 (ETF/dataless)
    returns ok=False (no-data); if it was purely 429, rate_limited=True."""
    endpoints, rate_limited = _fetch_tier2_endpoints(isin, instrument_key)

    # ARCHIVAL COMPLETENESS: if ANY endpoint was rate-limited, do NOT store a partial
    # row and mark done — that would permanently archive incomplete data (some columns
    # NULL only because of a 429, not because the data is absent). Instead treat the
    # whole stock as retryable so a later pass captures all 4 cleanly. Completeness
    # matters here because this is a one-time archive of perishable history.
    if rate_limited:
        return FundamentalsResult(ok=False, isin=isin, rate_limited=True,
                                  error="rate-limited (429) on >=1 tier-2 endpoint; retryable")

    got_any = any(endpoints.get(k) for k in
                  ("balance_sheet", "cash_flow", "corporate_actions", "competitors"))
    if not got_any:
        # No 429 anywhere, yet nothing came back -> genuinely no tier-2 data (ETF/dataless).
        return FundamentalsResult(ok=False, isin=isin,
                                  error="no tier-2 data (likely ETF/dataless)")

    # Clean fetch (no 429s): store whatever of the 4 exists. Any NULLs here are genuine
    # absences (e.g. a company with no competitors listed), not rate-limit gaps.
    statements_row = {
        "isin": isin,
        "balance_sheet": endpoints.get("balance_sheet"),
        "cash_flow": endpoints.get("cash_flow"),
        "corporate_actions": endpoints.get("corporate_actions"),
        "competitors": endpoints.get("competitors"),
    }
    try:
        get_supabase().table(_STATEMENTS_TABLE).upsert(
            statements_row, on_conflict="isin").execute()
    except Exception as exc:  # noqa: BLE001
        return FundamentalsResult(ok=False, isin=isin, error=f"DB upsert failed: {exc}")

    return FundamentalsResult(ok=True, isin=isin)


def store_fundamentals(isin: str, instrument_key: str, write: bool = True,
                       screening_only: bool = False) -> FundamentalsResult:
    """Fetch + parse + (optionally) upsert one stock's fundamentals.
    write=False        -> parse only (verify mode), return metrics row, no DB.
    screening_only=True -> fetch only the 4 screening endpoints (profile/ratios/income/
                           holdings), write profile + metrics only (NOT statements).

    Distinguishes a RATE-LIMIT failure (429, retryable) from a genuine NO-DATA failure
    (ETF/dataless): sets result.rate_limited so the caller keeps the stock retryable
    instead of marking it a permanent no-data failure."""
    endpoints, rate_limited = _fetch_all_endpoints(isin, instrument_key, screening_only)

    # Core screening data absent?
    core_missing = not endpoints.get("key_ratios") and not endpoints.get("income_statement")
    if core_missing:
        # If we saw a 429, this is a RATE-LIMIT miss (retry later), not real no-data.
        if rate_limited:
            return FundamentalsResult(ok=False, isin=isin, rate_limited=True,
                                      error="rate-limited (429); retryable")
        return FundamentalsResult(ok=False, isin=isin,
                                  error="no key-ratios or income statement (likely ETF/no-data)")

    profile_row, metrics_row, statements_row = build_rows(isin, endpoints)

    if not write:
        return FundamentalsResult(ok=True, isin=isin, metrics=metrics_row)

    supabase = get_supabase()
    try:
        supabase.table(_PROFILE_TABLE).upsert(profile_row, on_conflict="isin").execute()
        supabase.table(_METRICS_TABLE).upsert(metrics_row, on_conflict="isin").execute()
        # Only write the Tier-2 statements archive when we actually fetched it.
        if not screening_only:
            supabase.table(_STATEMENTS_TABLE).upsert(statements_row, on_conflict="isin").execute()
    except Exception as exc:  # noqa: BLE001
        return FundamentalsResult(ok=False, isin=isin, error=f"DB upsert failed: {exc}")

    return FundamentalsResult(ok=True, isin=isin, metrics=metrics_row)


# --- Verify-first spike ----------------------------------------------------

if __name__ == "__main__":
    #   python -m modules.market_data.upstox.fundamentals_store
    # Parse Reliance and PRINT the metrics row (NO DB write). Check numbers vs known good.
    from dotenv import load_dotenv
    load_dotenv()
    logging.basicConfig(level=logging.WARNING,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    isin = "INE002A01018"
    instrument_key = "NSE_EQ|INE002A01018"

    print("\n" + "=" * 64)
    print("FUNDAMENTALS STORE — 3.3 VERIFY (parse Reliance, NO write)")
    print("=" * 64)

    result = store_fundamentals(isin, instrument_key, write=False)
    if not result.ok:
        print(f"FAIL -- {result.error}")
        raise SystemExit(1)

    m = result.metrics
    print(f"\nISIN: {m['isin']}   period: {m.get('latest_period')} / holdings {m.get('holdings_period')}")
    print("\n  -- Valuation --")
    print(f"  P/E {m.get('pe')}   P/B {m.get('pb')}   EV/EBITDA {m.get('ev_ebitda')}   sector P/E {m.get('sector_pe')}")
    print("  -- Returns (%) --")
    print(f"  ROA {m.get('roa')}   ROE {m.get('roe')}   ROCE {m.get('roce')}   Quick {m.get('quick_ratio')}")
    print("  -- Core sales / profit --")
    print(f"  Revenue(core) {m.get('revenue_cr')}   NetProfit {m.get('net_profit_cr')}   EPS {m.get('eps_basic')}")
    print("  -- Growth (computed, %) --")
    print(f"  Rev 1Y {m.get('revenue_growth_1y')}   Rev 3Y CAGR {m.get('revenue_cagr_3y')}")
    print(f"  NP  1Y {m.get('net_profit_growth_1y')}   NP  3Y CAGR {m.get('net_profit_cagr_3y')}")
    print("  -- Ownership (%) --")
    print(f"  Promoter {m.get('promoter_pct')}   FII {m.get('fii_pct')}   DII {m.get('dii_pct')}   MF {m.get('mutual_fund_pct')}")

    print("\n  EXPECTED (from spike, for cross-check):")
    print("  P/E 20.17, P/B 1.97, ROA 4.04, ROE 8.94, ROCE 10.39, Quick 0.79, EV/EBITDA 9.99")
    print("  Revenue(core) 1057219, NetProfit 95610, EPS 59.69")
    print("  Promoter 50.48, FII 17.2, DII 11.08, MF 10.11")
    print("  Rev 1Y ~ (1057219 vs 964693) ~ +9.6% ;  NP 1Y +18.35% (per API)")
    print("=" * 64 + "\n")
