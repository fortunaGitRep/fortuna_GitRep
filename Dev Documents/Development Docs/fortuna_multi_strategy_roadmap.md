# Fortuna — Multi-Strategy Data & Watchlist Roadmap

Status: partially built. See "Build Status" below for what's live vs pending.

---

## 0. Build Status (updated 2026-08-26)

**DONE — Step 1: Instrument Catalogue layer.**
- `upstox_auth_client.py` — Analytics Token auth, smoke test passed.
- Migrations 003/004 → `f_universe_instruments`, `f_all_nse_index_instruments` — live.
- Fetchers + `instrument_store.py` (config-driven, chunked upsert + soft-delete reconcile).
- **ETF split (Migration 008):** the 347 INF-prefix ETFs moved to their own
  `f_etf_instruments` table (different KIND of instrument, no fundamentals). Catalogue is
  now **2,296 companies** (2,295 INE + 1 IN9 DVR stock) + 139 indices + 347 ETFs.

**DONE — Step 2: OHLCV.**
- `_ohlcv_engine.py` (fetch core) + `ohlcv_store.py` (Parquet↔R2) + `ohlcv_fetch_progress.py`
  (ledger) + shared `_ohlcv_backfill_runner.py` + thin callers `fetch_{index,universe}_ohlcv.py`.
- Migration 005 → `f_ohlcv_fetch_progress`. Bulk OHLCV → **Cloudflare R2** (`fortuna-ohlcv`,
  zero egress), one Parquet/instrument, 1d/1w/1mo stacked.
- **Result:** 135 indices + 2,638 stocks, ~287 MB, content-verified.

**DONE — Step 3: Fundamentals (stocks).**
- `fundamentals_store.py` (parse + store; `store_fundamentals` Tier-1, `store_tier2_statements`
  Tier-2). Orchestrators `fetch_universe_fundamentals.py` (Tier-1) +
  `backfill_universe_fundamentals_onetime.py` (Tier-2, auto-cooldown).
- Migrations 006 (3 tables) / 007 (Tier-1 ledger) / 009 (Tier-2 ledger).
- **Result:** Tier-1 2,296 stocks (screening: `f_fundamentals_profile` + `f_fundamentals_metrics`);
  Tier-2 2,290 archived (`f_fundamentals_statements` JSONB).
- First watchlist screen RAN (~98-137 quality stocks on the ~10 available criteria).

**NEXT — Watchlist persistence:** build `f_watchlists` + `f_watchlist_members` (criteria +
materialized members, source flag). Three planned lists: fundamentals-swing,
fundamentals-longterm, options/F&O. Then price-behavior analysis of watchlist stocks.

**DEFERRED:** `update_universe_fundamentals_qtrly.py` (recurring append); NSE market-cap fill
(reserved gap columns); DuckDB analytical layer + `read_ohlcv.py`; scheduler/Render cloud runs.

---

## 1. Core data layer (BUILT)

- **Universe**: all NSE-listed equities from Upstox instrument master. CONFIRMED
  2026-08-23: filtering `segment=NSE_EQ` alone is NOT enough — that segment holds ~9,687
  records including govt securities/bonds/debt (SG/GS/TB/GB/N*/Y*/Z* types). Must ALSO
  filter `instrument_type=EQ` → ~2,643 rows. UPDATE 2026-08-26: the 347 INF-prefix ETFs were
  then split into `f_etf_instruments` (own table), leaving **2,296 companies**. ETFs kept
  for a future regime-rotation/exposure layer.
- **Fundamentals**: full universe, Upstox Fundamentals endpoints — BUILT (Tier-1 screening
  + Tier-2 archive). Recurring quarterly append (`update_universe_fundamentals_qtrly.py`)
  deferred until something consumes fresh data. Note: banks need the Total-Revenue fallback;
  5 criteria (market cap, pledge, debt/equity, interest cover, 5yr growth) are reserved
  NULL columns for later NSE/external fills.
- **OHLCV Tier 1 (broad)**: daily/weekly/monthly candles, full universe, **full available
  history** — Upstox serves days/weeks/months back to January 2000 (or the stock's
  listing date if later), not just a couple of years. Needed for real backtesting depth.
  Pulled once now while Upstox data is free; incremental daily appends after.
  - Weekly/monthly candles fetched directly from Upstox (not derived/resampled
    locally) — Upstox's aggregation is already calendar-aware (NSE holidays, week/month
    boundaries), which is non-trivial to correctly replicate ourselves; the API-cost
    savings from deriving locally would be marginal anyway, since weekly/monthly only
    need re-fetching once a week / once a month respectively, not daily.
  - Per-call date-range caps apply (~1yr/call for daily, ~10yr/call for weekly/monthly
    per V2 docs — exact V3 caps to be confirmed on first real call), so backfill loops
    ~32 calls/stock (~26 daily + ~3 weekly + ~3 monthly) → ~64,000 calls total across
    2,000 stocks for one full backfill. At the free rate limit (25/sec) this is a
    ~40-45 min throttled one-time job — build it resumable (track completed
    stock+timeframe combos) since a run this size will hit occasional transient
    failures.
  - Ongoing sync cadence: daily job re-fetches only the `1D` timeframe for all 2,000
    stocks (~2,000 calls/day); `1W` re-fetched once a week after Friday close; `1Mo`
    re-fetched once a month after month-end. All three timeframes share one progress-
    tracking mechanism (see resumable-fetch design) so a missed/failed run is visible
    and retried, not silently skipped.
- **OHLCV Tier 2 (narrow)**: 4H/1H/15m/5m — only for stocks that survive Tier 1 /
  scanner filtering on a given day. Never full-universe at intraday granularity.

## 2. Watchlist system

- Watchlists are **derived views**, not separate storage. A stock's fundamentals/OHLCV
  live once in the core tables; watchlists are just membership lists (or dynamically
  computed queries) pointing at that same data.
- A stock can belong to multiple watchlists simultaneously.

### Watchlist 1 — Fundamentally Good (~110 stocks)
- Membership driven by threshold rules (PE, ROE, Debt/Equity, EPS growth, etc.)
- **Thresholds must be editable from frontend** — not hardcoded. Changing a threshold
  should recompute membership, not require a code change/deploy.

### Watchlist 2 — F&O Eligible (~208 stocks)
- This is **not** a fundamental-threshold list — F&O eligibility is an NSE/SEBI-published
  criterion (based on market-wide position limits, liquidity, market cap) refreshed
  quarterly by the exchange, not something we derive ourselves.
- Should be fetched/flagged from the Upstox instrument master (segment = NSE_FO
  underlying) or NSE's own published list, stored as a flag on the instrument record.
- Overlaps with Watchlist 1 — same stock, same underlying data row, just two
  memberships.

### Future watchlists (ideas to build later)

- **Nifty-decoupled watchlist**: stocks whose price pattern does *not* track Nifty50
  (low correlation / low beta to index) — for deploying capital when the index itself
  is sideways or directionless (like the last ~2 years). Needs a correlation/beta study
  across the daily Tier 1 data, rolling window, re-evaluated periodically.
- **Trend-regime study**: classify markets/assets into trending vs ranging regimes over
  time, so strategy selection can be regime-aware rather than one-size-fits-all.
- **News-driven momentum capture**: detect when news hits a stock and it starts
  trending/bulling off the back of it — needs a news feed (Upstox News API) + some
  event-tagging + reaction-window price study to see if there's a repeatable edge.
- **Cross-asset rotation**: once commodity and forex data are added, build logic to
  rotate capital toward whichever asset class (equity/commodity/forex) is currently
  trending, rather than being equity-only.

## 3. Data beyond OHLCV (from Upstox, to fetch and store)

- Company Fundamentals (8 endpoints: profile, balance sheet, cash flow, income
  statement, shareholding, key ratios, corporate actions, competitors)
- Market Information (FII/DII activity, OI + change in OI, Max Pain, PCR)
- Option Chain (OI, Greeks, IV per strike)
- News feed
- Global Index / Global Indicators / India VIX (useful context signals, e.g. for
  GIFT Nifty-based gap analysis, already relevant to the PRE-2 basis adjustment issue
  flagged in the 12 Aug retrospective)

## 4. Backtesting

- Each watchlist gets its own strategy backtested independently — a stock being in
  Watchlist 1 doesn't mean it's tested the same way as when it's in Watchlist 2 or the
  Nifty-decoupled list. Strategy logic is per-watchlist, not global.

## 5. Future asset classes

- Commodities (data source TBD)
- Forex (data source TBD)
- Same tiered-fetch + watchlist + backtest pattern should extend to these once equity
  pipeline is proven.

## 6. Open design questions (to resolve before/while building)

1. ~~F&O eligible list~~ — **decided:** Upstox instrument master segment flag.
2. Threshold-based watchlist membership — compute live on every request, or cache into
   a membership table and recompute on a trigger (fundamentals refresh / threshold
   edit)? Cache is faster for frontend, live-compute is always fresh — leaning cache
   with recompute-on-change.
3. Correlation/beta study for the Nifty-decoupled watchlist — what lookback window
   and re-evaluation frequency makes sense (this needs its own design pass later).

## 7. Finalized architecture (fundamentals + OHLCV only, for now)

**Scope decision:** only fetching Fundamentals (all 8 endpoints — this IS the complete
data, not a subset) and Tier 1 OHLCV right now. Everything else Upstox offers
(Option Chain, Market Information, News, Global Index/Indicators, portfolio read-only)
is explicitly deferred — see §8.

**Broker bifurcation:** `modules/market_data/{dhan,upstox}/` — keeps Dhan (index data)
and Upstox (universe data) fully separable, so a future broker swap only touches one
folder. Same split mirrored in Supabase Storage (`fortuna-ohlcv/{dhan,upstox}/`).
Watchlists live as a sibling, not nested under either broker — broker-agnostic since
future watchlists (commodity/forex) will pull from more than one source.

**Three data domains (clarified 2026-08-21) — shared engine, separate callers:**
1. **Universe stocks** (~2,000, `NSE_EQ`): fundamentals (8 endpoints) + OHLCV (D/W/Mo now,
   intraday Tier-2-filtered later, options future). Filtered downstream into Fortuna Cash
   watchlists.
2. **Sector / other indices** (~15-20, `NSE_INDEX`): OHLCV only (no fundamentals exist for
   indices). Stored separately. Use case: gauge how each sector is performing.
3. **Nifty 50** (single, `NSE_INDEX`): OHLCV in ALL timeframes including intraday, plus
   options data near-term, for the options-trading chart.

The OHLCV fetch mechanic is identical across all three (same Upstox historical endpoint,
pagination, Parquet write, resumability) — only the instrument_keys, timeframes, and
storage subfolder differ. So OHLCV = ONE shared `_ohlcv_engine.py` + thin per-domain
callers (readable, independently runnable entry points on top; single bug-fixed core
underneath — avoids the triplicated-logic drift Rule #15 warns against). Fundamentals is
domain-1-only (indices have none), so it stays a single-purpose script. Tracker + reader
are domain-agnostic (renamed off `universe_` since indices use them too).

**`f_universe_instruments`** (Migration 003) — the foundation table domain-1 loops over:
`instrument_key` (unique, stable — preferred over `exchange_token` which can be reassigned
after expiry), `trading_symbol`, `name`, `isin`, `exchange`, `segment`, `instrument_type`,
`is_fno_eligible` (from cross-referencing NSE_FO underlying keys), `is_active` (set false
on delisting, see below — never deleted).

**Instrument file source — per-exchange, not `complete` (decided 2026-08-23).** Upstox
offers `complete.json.gz` (all exchanges) and per-exchange files (`NSE.json.gz`,
`BSE.json.gz`, `MCX.json.gz`). We use the per-exchange file for whichever exchange we
actually trade — cheaper fetch (no downloading BSE/MCX data daily just to extract NSE).
`NSE.json.gz` contains everything all 3 current domains need: NSE_EQ (stocks), NSE_INDEX
(indices), NSE_FO (for F&O-eligibility cross-ref). Fetcher takes exchange as a parameter,
so adding MCX later (commodities) is one call, not a new script. Upstox recommends JSON
over CSV (CSV being deprecated) and `instrument_key` over `exchange_token` for identity.
The code downloads this file automatically on each run — never a manual step.

**`f_index_instruments`** (separate from `f_universe_instruments`) — indices are a genuinely
different shape: no ISIN, no fundamentals linkage, no F&O flag, no delisting logic; instead
a sector-mapping purpose. A combined table would be half-empty nullable columns per row
(the sparse-nullable anti-pattern rejected for fundamentals). Kept separate.

**Parquet filenames = the portion of `instrument_key` after the `|`, space-slugified.**
For stocks that's the ISIN (`NSE_EQ|INE002A01018` → `INE002A01018.parquet`) — permanent,
globally unique, never reused (unlike `exchange_token`, which Upstox warns can be
reassigned after expiry) and survives symbol renames. For indices it's the index name
(`NSE_INDEX|Nifty 50` → `Nifty_50.parquet`) — spaces slugified to underscores to avoid
path/URL bugs. The raw instrument_key stays in the instruments table for lookup; the
filename is a sanitized derivative. Code never browses files by eye, so human-readable
symbol↔ISIN mapping lives in the table, not in filenames.

```
backend/modules/market_data/
├── dhan/                              (existing, untouched)
├── upstox/
│   ├── upstox_auth_client.py             (Analytics Token handling — see auth note below)
│   ├── _ohlcv_engine.py                  (SHARED OHLCV fetch core — given instrument_keys +
│   │                                       timeframes + storage subfolder, fetches + writes
│   │                                       Parquet. The ONE place OHLCV fetch logic lives;
│   │                                       all three domains' callers use it.)
│   ├── track_fetch_status.py             (resumable fetch tracker — domain-agnostic, any
│   │                                       dataset/domain; writes f_fetch_status)
│   │  — DOMAIN 1: universe stocks (~2000, NSE_EQ) —
│   ├── fetch_universe_instrument_list.py (NSE_EQ list + F&O flag → f_universe_instruments)
│   ├── fetch_universe_fundamentals.py    (8 normalized f_fundamentals_* tables — stocks only)
│   ├── fetch_universe_ohlcv.py           (thin caller → _ohlcv_engine: 2000 stocks, D/W/Mo,
│   │                                       universe/ path)
│   │  — DOMAINS 2+3: indices (sector indices + Nifty 50) —
│   ├── fetch_index_instrument_list.py    (NSE_INDEX list → f_index_instruments)
│   ├── fetch_index_ohlcv.py              (thin caller → _ohlcv_engine: sector indices D/W/Mo;
│   │                                       Nifty 50 D/W/Mo + INTRADAY 5m/15m/1h; indices/ path)
│   │  — SHARED reader —
│   └── read_ohlcv.py                     (read-only: get_candles(instrument_key, timeframe,
│                                           start, end) — domain-agnostic, works for any stored
│                                           Parquet, stock or index, same format.)
└── watchlists/
    ├── watchlist_db_operations.py     (CRUD: watchlists, rules, membership)
    └── watchlist_rule_evaluator.py    (applies threshold rules → recomputes membership)
```

**Upstox auth — Analytics Token, not daily OAuth login.** Upstox's standard access
token needs a fresh interactive login every day (expires 3:30 AM regardless of when
issued — same daily-refresh problem Dhan has). Upstox also offers a separate
**Analytics Token**: 1-year validity, read-only, generated once from the Developer
Apps console (no OAuth redirect flow), free. Covers Market Data + Historical Data +
Realtime/Streaming fully; Portfolio/Account read-only APIs too if a static IP is
registered. Since this build is data-only (no order placement via Upstox), the
Analytics Token avoids the daily-refresh problem entirely — no TOTP/Playwright
automation needed, unlike Dhan (which has no long-lived data-only token equivalent,
hence the TOTP headless workaround built for it). One token per account; regenerating
revokes the old one, so store securely and don't regenerate carelessly.

**Trading via Upstox — deliberately deferred, not designed yet (Rule #16).** The
Analytics Token is read-only by API contract — it can never be used for order
placement, no matter how it's configured. If Ash decides later to place trades via
Upstox (pricing plans may change; decision only made after Fortuna is complete), that
needs Upstox's standard daily-OAuth flow, automated separately (e.g. via a
TOTP-based headless login, similar in spirit to the Dhan TOTP setup, using a
package like `upstox-totp` or a custom implementation) — a fully separate auth
mechanism from the Analytics Token, not an upgrade path from it. **Not signing up
for this OAuth app / building this flow now** — but per Rule #16, `upstox_auth_client.py`
keeps a clear seam for it:
- `get_analytics_client()` — built now, data-only, used by all fetch scripts.
- `get_trading_client()` — **stubbed/TBD**, not implemented. Docstring notes it needs
  a separate Upstox OAuth app registration (different from the Analytics Token setup)
  and daily-refresh automation, to be built only if/when Ash decides to trade via
  Upstox.
- `.env` gets placeholder entries now (commented out / empty), so the file's shape
  already anticipates this without needing a later restructure:
  ```
  # --- Upstox: data-only (Analytics Token) — ACTIVE ---
  UPSTOX_API_KEY=
  UPSTOX_API_SECRET=
  UPSTOX_ANALYTICS_TOKEN=

  # --- Upstox: trading (standard OAuth) — TBD, not set up yet (Rule #16) ---
  # UPSTOX_TRADING_CLIENT_ID=
  # UPSTOX_TRADING_CLIENT_SECRET=
  # UPSTOX_TRADING_REDIRECT_URI=
  # UPSTOX_TRADING_TOTP_SECRET=
  ```

**OHLCV storage — Parquet, one file per stock, all timeframes inside:**
```
fortuna-ohlcv/upstox/universe/RELIANCE.parquet   (columns: date, timeframe, open,
                                                    high, low, close, volume, oi)
```
One file (not split per timeframe) because: fetch cost is identical either way (3 API
calls per stock regardless of storage layout — 1D/1W/1Mo are separate Upstox calls no
matter what); weekly+monthly rows are <20% of daily row count so combined-file read
overhead is negligible with Parquet's columnar predicate pushdown; and cross-timeframe
analysis (an indicator checking daily against weekly trend) needs one read, not a join
across files. Weekly/monthly fetched directly from Upstox (not derived/resampled
locally) — Upstox's aggregation is already calendar-aware (NSE holidays, week/month
boundaries), non-trivial to correctly replicate ourselves, and the API-cost savings
from deriving locally would be marginal (weekly/monthly only need re-fetching once a
week / once a month respectively, not daily).

**Fundamentals — Postgres, normalized per-endpoint (not one wide table, not Parquet):**

> ✅ **AUTH CONFIRMED (2026-08-21, from Upstox's current docs — screenshot verified):**
> The Analytics Token **DOES** support Fundamentals, with **no static IP needed**. Upstox's
> current supported-APIs table groups by static-IP requirement:
> - **No static IP needed** (any server/laptop/serverless): Charges, Margins, Market Quote,
>   Historical Data, Option Chain, Market Information, **Fundamentals**, News, IPO, Websocket.
> - **Static IP required:** User, Payments, Orders, GTT Orders, Portfolio, Mutual Fund,
>   Trade Profit And Loss (i.e. trading + account-state ops — none of which Fortuna does via
>   Upstox; that's Dhan's job).
>
> Net: the SINGLE Analytics Token covers EVERYTHING in Fortuna's Upstox data layer —
> all instrument lists, all OHLCV (3 domains), fundamentals, and the future option-chain/
> Greeks/Market-Info/News items — with no static IP, no OAuth redirect, no daily refresh,
> free. (An older cached version of the docs omitted Fundamentals from the list and there
> were stale community 403 reports; the current docs supersede both.)

Table not files, because watchlist filtering needs SQL's `WHERE pe < 20 AND roe > 15`
across the whole universe on arbitrary/changing threshold combos — the access pattern
is cross-sectional filtering, which SQL does natively; Parquet would force loading and
parsing all 2,000 stocks' data on every threshold change.

Normalized per endpoint (not one wide table) because the 8 endpoints have genuinely
different shapes/cadences — squashing them together forces sparse nullable columns or
loses history:

| Table | Shape | Refresh |
|---|---|---|
| `f_fundamentals_profile` | 1 row/stock | rarely |
| `f_fundamentals_key_ratios` | 1 row/stock/quarter | quarterly — main table Watchlist 1's thresholds filter against |
| `f_fundamentals_balance_sheet` | 1 row/stock/fiscal year | yearly |
| `f_fundamentals_income_statement` | 1 row/stock/fiscal year | yearly |
| `f_fundamentals_cash_flow` | 1 row/stock/fiscal year | yearly |
| `f_fundamentals_shareholding` | 1 row/stock/quarter | quarterly |
| `f_fundamentals_corporate_actions` | 1 row/event/stock | event-driven |
| `f_fundamentals_competitors` | 1 row/peer/stock | occasional |

**Resumable fetch tracking — one shared table + module, used by every fetch job
(all three domains):**
```sql
create table f_fetch_status (
  id bigserial primary key,
  dataset text not null,          -- 'ohlcv_1d' | 'ohlcv_1w' | 'ohlcv_1mo' | 'ohlcv_5m' |
                                   -- 'fundamentals_key_ratios' | 'index_ohlcv_1d' | ...
  instrument_key text not null,   -- matches f_universe_instruments / f_index_instruments
  status text not null default 'pending',   -- pending | done | failed
  attempt_count int not null default 0,
  last_attempt_at timestamptz,
  last_success_at timestamptz,
  last_error text,
  unique (dataset, instrument_key)
);
```
`track_fetch_status.py` exposes `get_pending(dataset)` /
`mark_done(instrument_key, dataset)` / `mark_failed(instrument_key, dataset, error)`.
All fetch scripts (universe fundamentals, universe OHLCV, index OHLCV) call into it,
domain-agnostic. An interrupted backfill re-run naturally skips already-`done` rows and
resumes. Keyed by `instrument_key` (not `symbol`) to match the instruments tables —
symbol can change on renames, instrument_key is stable. `last_error` (not `error`) is
explicitly the MOST RECENT error only, not a history. Fundamentals refresh is
staleness-based (daily check: any stock whose `last_success_at` is >90 days old gets
refetched), not a fixed global quarterly run, since companies don't all report on the
same calendar quarter.

**Universe list changes — checked daily, not assumed static.** Upstox refreshes its
instrument master file ~6 AM daily (rare intraday updates too). `fetch_universe_instrument_list.py`
runs daily, before the fundamentals/OHLCV jobs, and diffs the fresh download against
`f_universe_instruments` by `instrument_key`:
- New `instrument_key` → inserted. It automatically has no `f_fetch_status` rows for
  any dataset, so the next fundamentals/OHLCV run picks it up via the normal
  `get_pending()` path — no separate "new stock" code path needed. The one thing that
  DOES need explicit branching: a stock with no prior successful fetch
  (`last_success_at` is null) gets a FULL historical backfill, not an incremental
  append — same script, branches on that one check.
- Previously-stored `instrument_key` now missing from the file → marked
  `is_active = false` (delisted/suspended), not deleted. Historical OHLCV/fundamentals
  data stays intact for backtesting continuity; excluded from future daily fetch loops
  and from watchlist eligibility going forward.

**Table/file names finalized (approved 2026-08-21):** Supabase tables use the `F_`
prefix (not `fortuna_`, not unprefixed) to match project convention. File names are
verb-explicit (`fetch_*` for write jobs, `read_*` for the read-only accessor).

**RUN PATTERN (confirmed working 2026-08-23):** All backend Python is run from the
`backend/` folder using the `-m` module flag with the full dotted package path, e.g.
`python -m modules.market_data.upstox.upstox_auth_client`. This resolves imports
relative to `backend/` and lets `python-dotenv`'s `load_dotenv()` find `backend/.env`
(it searches from the current working dir upward). Every Upstox module is written to be
run this way. Folders in the import path (`modules/`, `market_data/`, `upstox/`) each
need an empty `__init__.py` to be proper importable packages.

**NAMING CONVENTIONS (build rules, set 2026-08-23):**
- **DB tables/functions: lowercase with `f_` prefix** (`f_universe_instruments`, not
  `F_universe_instruments`). Postgres folds unquoted identifiers to lowercase, so a
  capital-letter name would force `"F_..."` quoting in EVERY query forever — avoided by
  going lowercase from the start. Prefix `f_` still marks them as Fortuna tables.
- **Python files: verb-explicit snake_case** (`fetch_universe_ohlcv.py`,
  `read_ohlcv.py`) — `fetch_*` = write/pull jobs, `read_*` = read-only accessors,
  `track_*` = status/bookkeeping.
- **Parquet files: instrument_key suffix, space-slugified** (ISIN for stocks, index
  name for indices) — see OHLCV storage section.
- **Migrations: `NNN_fortuna_<subject>.sql`** zero-padded sequential (`003_fortuna_universe_instruments.sql`).
- **Audit timestamps: IST wall-clock** via a shared `now_ist()` SQL helper, not bare
  `now()` — so rows read in Indian market time on any server (incl. UTC-hosted Render).

**Rule #16 (Broker-Agnostic Design, added 2026-08-21):** Never let current broker
cost/pricing decisions (e.g. not placing trades via Upstox today due to cost) limit or
hardcode Fortuna's architecture. Design auth/execution layers so capabilities (e.g.
order placement via a currently data-only broker) can be added later without rework —
broker choice may change after Fortuna is complete, once Ash can properly evaluate it.
Paste into the main Rule Book alongside #7-15.

## 8. Deferred data (open items — not fetched yet, revisit later)

- **Option Chain** (OI, Greeks, IV per strike) — needed once options strategies move
  beyond the existing Foundation Funnel's data sources.
- **Market Information** (FII/DII activity, OI change, Max Pain, PCR) — potential
  context-weight input for Foundation Funnel PRE-stage gates; currently FII/DII comes
  from Claude+web_search in the funnel, this could be a cleaner direct source later.
- **News API** — needed for the news-driven momentum capture watchlist idea (§2).
  Need to check response structure/coverage before designing the event-tagging
  pipeline.
- **Global Index / Global Indicators / India VIX (Upstox)** — Fortuna already sources
  VIX/Nifty/GIFT via Dhan in `modules/market_data/dhan/`; only relevant if Dhan's
  version proves insufficient, not a near-term need.
- **Portfolio/Account read-only APIs** — not needed while Dhan handles all execution
  and position tracking.

## 9. Deferred refactors (structure tidy-ups — not blocking, do as own tasks)

- **Dhan → `dhan/` migration.** Current real state (as of 2026-08-23): the Dhan files
  (`indices.py`, `index_store.py`, `nse_calendar.py`, `sync.py`, `vix_regime.py`,
  `test_vix_regime.py`) sit LOOSE directly in `modules/market_data/`, not yet in a
  `dhan/` subfolder. The `upstox/` subfolder exists. The broker-split design wants Dhan
  files moved into `dhan/` to mirror `upstox/`. Deferred (Option B, 2026-08-23) because:
  moving them breaks every existing import referencing those modules, which the live/
  tested Foundation Funnel depends on — a real risk best handled as a dedicated,
  carefully-tested migration task (move files → fix all imports → re-run
  `test_vix_regime.py` and funnel tests → confirm green), NOT interleaved with new
  Upstox feature work (avoids mixing two unrelated changes, per Rule #7). Upstox code is
  self-contained and imports nothing from Dhan, so building it now while Dhan sits loose
  costs nothing functional; the messy structure is temporary.
  - NOTE: `market_data/` and `upstox/` now DO have `__init__.py` files (added
    2026-08-23). Confirmed run pattern: `python -m modules.market_data.upstox.<file>`
    from `backend/`.

## 10. Scheduler (OPEN — important, needed before production)

Every fetch is currently a manual `python -m ... --sync` run. Production needs an
unattended scheduler that runs, in order, on the right cadence:
- Daily: instrument-list refresh (both catalogues, diff + soft-delete) → then daily
  OHLCV append (1D, full universe + indices) → then fundamentals staleness check.
- Weekly (after Fri close): 1W OHLCV re-fetch.
- Monthly (after month-end): 1Mo OHLCV re-fetch.
CANNOT be finalized until the individual fetch jobs (OHLCV, fundamentals) exist to
orchestrate. Options to evaluate when we get there: APScheduler in-process, Render
Cron Jobs, or a task queue. Must be resumable (leans on f_fetch_status) and log
failures visibly. Tracked as a first-class build item, not a nice-to-have.

## 11. Resolved: "bulk data in Postgres vs outputs-only" (was open in Learning doc §6)

RESOLVED 2026-08-23 by architecture, not left to default:
- **Reference/output data → Supabase Postgres** (small, relational): instrument
  catalogues (f_universe_instruments, f_all_nse_index_instruments), fundamentals tables,
  watchlist membership, fetch-status. Confirmed working at 2,643 + 139 rows.
- **Bulk historical market data → Parquet in Supabase Storage** (NOT Postgres): OHLCV
  for all stocks + indices. Per-instrument files. This is the deliberate decision the
  Learning doc §6 flagged as needing to be made before the signal engine — now made.
