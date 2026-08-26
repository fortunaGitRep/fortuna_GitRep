-- ============================================================================
-- Fortuna Fundamentals — three tables (run in Supabase SQL editor)
--
-- Stores the Upstox Company Fundamentals API data for the ~2,643 NSE equities.
-- Populated by the fundamentals fetch/store modules (3.3/3.4), one pass per stock
-- (8 endpoints: profile, key-ratios, balance-sheet, cash-flow, income-statement,
-- share-holdings, corporate-actions, competitors).
--
-- WHY THREE TABLES (tiered by use, decided 2026-08-24):
--   * f_fundamentals_profile   — descriptive (sector, description, sector mcap). Tier 1.
--   * f_fundamentals_metrics   — the SCREENING WORKHORSE: all numeric, one row/stock,
--                                every column a watchlist can filter on in plain SQL.
--                                Tier 1. Kept separate from profile so this table stays
--                                purely numeric + compact = fast threshold scans.
--   * f_fundamentals_statements — full multi-year statements as JSONB. Tier 2, queried
--                                occasionally for deep-dives, not bulk screening.
--   Separating tiers keeps the frequent operation (screening on _metrics) reading small
--   rows, not dragging multi-KB JSON blobs along.
--
-- FETCHED-RAW vs COMPUTED-DERIVED (important — see _metrics comments):
--   Some _metrics columns come straight from the API; growth columns are COMPUTED
--   because "sales" screening means CORE revenue (excl other income), while the API's
--   ready-made change% is on Total Revenue (incl other income):
--     * revenue_growth_1y  = core-Revenue YoY, computed from full_statement "Revenue"
--     * revenue_cagr_3y    = 3-yr CAGR of core Revenue (4 yearly periods; 3Y is deepest)
--     * net_profit_cagr_3y = 3-yr CAGR of net profit
--   3Y is the deepest CAGR possible (only 4 years of history; 5Y is NOT available).
--
-- KNOWN GAPS (Path A, logged 2026-08-24 — NOT reliably derivable from Upstox, deferred):
--   * MARKET CAP — needs true shares outstanding, which the API doesn't give. Deriving
--     shares via net_profit/EPS is ~20% off (different profit base), too wrong to trust
--     even for a coarse '>1000cr' filter. Add later from a real share-count source
--     (e.g. NSE bhavcopy). NOT stored as a misleading approximation.
--   * interest coverage (interest expense not broken out in the income statement)
--   * promoter PLEDGE % (holdings endpoint gives holding %, not pledge)
--   * true debt-to-equity (borrowings not broken out; only current/non-current liab)
--   * 5-YEAR growth (only 4 yrs of history)
--   A Screener.in-grade screen needs a supplementary source; later enhancement, not now.
--   The watchlist is built on the ~10 criteria Upstox CAN serve.
--
-- Conventions: lowercase f_ names, IST audit timestamps via shared now_ist(),
-- touch trigger, RLS service-role-only. Same posture as migrations 003-005.
-- ============================================================================

-- ---------------------------------------------------------------------------
-- Shared helpers (idempotent re-create; from migration 003).
-- ---------------------------------------------------------------------------
create or replace function public.now_ist()
returns timestamp
language sql
stable
as $$
    select (now() at time zone 'Asia/Kolkata');
$$;

create or replace function public.touch_updated_at_ist()
returns trigger
language plpgsql
as $$
begin
    new.updated_at = public.now_ist();
    return new;
end;
$$;

-- ===========================================================================
-- TABLE 1 — f_fundamentals_profile  (Tier 1, descriptive)
-- ===========================================================================
create table if not exists public.f_fundamentals_profile (
    isin                text        primary key,        -- company identity (matches f_universe_instruments.isin)
    sector              text,                            -- profile.sector, e.g. 'Refineries'
    company_profile     text,                            -- profile.company_profile (long business description)
    sector_mcap_inr_cr  numeric,                         -- profile.sector_market_cap_inr.value (SECTOR, not company)
    sector_mcap_usd_bn  numeric,                         -- profile.sector_market_cap_usd.value
    fetched_at          timestamp   not null default public.now_ist(),
    updated_at          timestamp   not null default public.now_ist()
);

comment on table public.f_fundamentals_profile is
    'Descriptive fundamentals (Tier 1): sector, business description, SECTOR market cap. '
    'One row per stock, keyed by ISIN. Note sector_mcap is sector-level, not company-level '
    '(company mcap is computed in f_fundamentals_metrics.market_cap_cr).';

-- ===========================================================================
-- TABLE 2 — f_fundamentals_metrics  (Tier 1, screening workhorse; all numeric)
-- One row per stock. Every column is watchlist-filterable in plain SQL.
-- ===========================================================================
create table if not exists public.f_fundamentals_metrics (
    isin                    text     primary key,

    -- ---- Valuation (fetched from key-ratios) ----
    pe                      numeric,     -- key-ratios "P/E" company_value
    pb                      numeric,     -- key-ratios "P/B"
    ev_ebitda               numeric,     -- key-ratios "EV/EBITDA"
    sector_pe               numeric,     -- key-ratios "P/E" sector_value (peer comparison)

    -- ---- Returns (fetched from key-ratios; % stripped -> numeric) ----
    roa                     numeric,     -- "ROA"  (e.g. 4.04 means 4.04%)
    roe                     numeric,     -- "ROE"
    roce                    numeric,     -- "ROCE"

    -- ---- Liquidity (fetched) ----
    quick_ratio             numeric,     -- key-ratios "Quick Ratio"

    -- ---- Growth (computed from CORE Revenue line-item, not API's Total-Revenue change) ----
    -- "Sales" in fundamental screening = core operating Revenue, EXCLUDING Other Income
    -- (interest/dividends = non-operating). The API's ready-made change% is on Total
    -- Revenue (incl other income), so we COMPUTE growth ourselves from the full_statement
    -- "Revenue" line-item year-over-year to get true sales growth.
    revenue_growth_1y       numeric,     -- COMPUTED: core Revenue YoY % (latest vs prior year)
    net_profit_growth_1y    numeric,     -- income "net_profit".change (no core/total ambiguity)
    revenue_cagr_3y         numeric,     -- COMPUTED: 3-yr CAGR of core Revenue (4 periods available)
    net_profit_cagr_3y      numeric,     -- COMPUTED: 3-yr CAGR of net profit

    -- ---- Ownership (fetched from share-holdings, latest quarter) ----
    promoter_pct            numeric,     -- holdings "promoters" latest
    fii_pct                 numeric,     -- holdings "fii" latest
    dii_pct                 numeric,     -- holdings "other_dii" latest
    mutual_fund_pct         numeric,     -- holdings "mutual_funds" latest

    -- ---- Raw reference values (fetched; core figures, for derivation & display) ----
    revenue_cr              numeric,     -- CORE "Revenue" line-item (excl Other Income), latest period
    net_profit_cr           numeric,     -- income latest net_profit
    eps_basic               numeric,     -- income latest "EPS - Basic"

    -- ---- Which periods the above came from (financials yearly, holdings quarterly) ----
    latest_period           text,        -- e.g. 'Mar 2026'
    holdings_period         text,        -- e.g. 'Jun 2026'

    -- =======================================================================
    -- RESERVED GAP COLUMNS — NOT filled by the Upstox job. Left NULL until a
    -- separate fill job populates them. Schema reserves them now so watchlist SQL
    -- can reference them and no migration is needed later. Each notes its filler.
    -- (Gap analysis 2026-08-24 vs Ash's 15-criteria screener.)
    -- =======================================================================
    -- Fillable from NSE quote-equity (issuedSize, faceValue) — a separate NSE job:
    market_cap_cr           numeric,     -- NSE-FILL: issuedSize * lastPrice (accurate, unlike net_profit/EPS)
    shares_outstanding      numeric,     -- NSE-FILL: securityInfo.issuedSize
    face_value              numeric,     -- NSE-FILL: securityInfo.faceValue
    -- Fillable from NSE corporate-disclosure feed (different endpoint) — later job:
    pledge_pct              numeric,     -- NSE-DISCLOSURE-FILL: promoter pledged % (SAST/disclosure feed)
    -- Path-A gaps needing a richer financials source (Screener.in / Yahoo) — later:
    debt_to_equity          numeric,     -- EXTERNAL-FILL: needs borrowings (not in Upstox or NSE-quote)
    interest_coverage       numeric,     -- EXTERNAL-FILL: needs interest expense (not broken out)
    revenue_growth_5y       numeric,     -- EXTERNAL-FILL: needs 5yr history (Upstox has 4yr)
    net_profit_growth_5y    numeric,     -- EXTERNAL-FILL: needs 5yr history

    fetched_at              timestamp not null default public.now_ist(),
    updated_at              timestamp not null default public.now_ist()
);

comment on table public.f_fundamentals_metrics is
    'Screening workhorse (Tier 1): one numeric row per stock, every column watchlist-'
    'filterable in plain SQL. Ratios/ownership fetched from key-ratios/income/holdings; '
    'growth (1Y + 3Y CAGR) COMPUTED from CORE Revenue line-item (excl other income) and '
    'net profit. Gaps NOT available in Upstox (deferred, Path A): market cap (no reliable '
    'share count — net_profit/EPS is ~20% off), interest coverage, pledge %, true debt/'
    'equity, 5yr growth.';

-- Screening indexes: the columns most watchlists filter on. Plain btree so
-- threshold scans (pe < 60 AND roe > 12 AND ...) are fast.
create index if not exists idx_metrics_pe          on public.f_fundamentals_metrics (pe);
create index if not exists idx_metrics_roe         on public.f_fundamentals_metrics (roe);
create index if not exists idx_metrics_roce        on public.f_fundamentals_metrics (roce);
create index if not exists idx_metrics_promoter    on public.f_fundamentals_metrics (promoter_pct);

-- ===========================================================================
-- TABLE 3 — f_fundamentals_statements  (Tier 2, JSONB archive)
-- Full multi-year statements as-is. Queried occasionally for deep-dives.
-- ===========================================================================
create table if not exists public.f_fundamentals_statements (
    isin                text        primary key,
    balance_sheet       jsonb,      -- full balance-sheet response (history + full_statement)
    cash_flow           jsonb,      -- full cash-flow response
    income_statement    jsonb,      -- full income-statement response
    holdings            jsonb,      -- full share-holdings response (all categories, all quarters)
    corporate_actions   jsonb,      -- full corporate-actions response (dividends, splits, ...)
    competitors         jsonb,      -- competitors response (NOTE: fetched by instrument_key, not ISIN)
    fetched_at          timestamp   not null default public.now_ist(),
    updated_at          timestamp   not null default public.now_ist()
);

comment on table public.f_fundamentals_statements is
    'Full fundamentals statements as JSONB (Tier 2): balance sheet, cash flow, income '
    'statement, holdings history, corporate actions, competitors — stored as-is for '
    'occasional deep-dive/research. Screening uses f_fundamentals_metrics instead. '
    'competitors is fetched by instrument_key (the API rejects ISIN for that one endpoint).';

-- ---------------------------------------------------------------------------
-- updated_at auto-touch triggers (IST) for all three
-- ---------------------------------------------------------------------------
drop trigger if exists trg_touch_fund_profile on public.f_fundamentals_profile;
create trigger trg_touch_fund_profile
    before update on public.f_fundamentals_profile
    for each row execute function public.touch_updated_at_ist();

drop trigger if exists trg_touch_fund_metrics on public.f_fundamentals_metrics;
create trigger trg_touch_fund_metrics
    before update on public.f_fundamentals_metrics
    for each row execute function public.touch_updated_at_ist();

drop trigger if exists trg_touch_fund_statements on public.f_fundamentals_statements;
create trigger trg_touch_fund_statements
    before update on public.f_fundamentals_statements
    for each row execute function public.touch_updated_at_ist();

-- ---------------------------------------------------------------------------
-- Row Level Security — service role only (single-user backend), all three
-- ---------------------------------------------------------------------------
alter table public.f_fundamentals_profile    enable row level security;
alter table public.f_fundamentals_metrics    enable row level security;
alter table public.f_fundamentals_statements enable row level security;
-- No anon/authenticated policies => zero access for those roles.
-- Backend connects with service_role key, which bypasses RLS.
