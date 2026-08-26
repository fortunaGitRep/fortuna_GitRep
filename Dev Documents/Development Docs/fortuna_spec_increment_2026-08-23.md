# Fortuna Spec — Increment (2026-08-23)

Incremental additions/corrections to the formal Spec (currently v0.4). Merge into the
main spec at next version bump. Captures scope + architecture decisions made since v0.4
that the spec doesn't yet reflect.

---

## A. What Fortuna IS (expanded scope)

The v0.4 spec defines Fortuna as "a personal trading research and analysis platform for
Indian equity and index options markets." That's still true but now UNDERSTATES the
scope. The fuller definition:

**Fortuna is a personal, systematic, cross-market research & analysis platform for
Indian markets — designed to detect where opportunity/trend exists across ALL markets
and submarkets (index, individual equities, index/stock options, sectors, themes,
commodities, government securities) and rotate capital toward it, learning regime
patterns from history to apply going forward over a multi-year/decade horizon.**

It remains: personal (single-user, Ash), manual-execution (Ash places all trades; see
Rule / Trade Execution below), research-first, and built "basement of a skyscraper"
for decades-scale scalability.

See `fortuna_strategy_thesis.md` for the full cross-market regime-rotation rationale.

## B. Corrections to v0.4 the spec must absorb

1. **Data broker (MAJOR CHANGE).** v0.4 says data comes from Dhan Data API (₹499/mo,
   Phase 2) with yfinance/NSE-scraping in Phase 1. SUPERSEDED: **all market data now
   comes FREE from Upstox** via the Analytics Token (1-yr, read-only, no static IP,
   covers historical/quotes/option-chain/fundamentals/news). Dhan is **execution-only**
   (+ the existing index-data feed for the live Foundation Funnel, pending its own
   migration to Upstox). This removes the ₹499/mo data cost entirely.

2. **Universe (CHANGE).** v0.4 says "Nifty 500" for Fortuna-Cash. SUPERSEDED: the full
   NSE equity universe + all 139 NSE indices are fetched — not a fixed 500 — to serve the
   cross-market regime thesis. Post ETF-split: **2,296 companies** in `f_universe_instruments`
   + **347 ETFs** in `f_etf_instruments` + 139 indices. (The raw `segment=NSE_EQ &
   instrument_type=EQ` pull is ~2,643; INF-prefix ETFs were moved to their own table as a
   different KIND of instrument with no fundamentals.)

3. **Broker roles (CLARIFY, Rule #16).** Broker choice must never be hardcoded. Upstox
   = data now (and possibly execution later if pricing/decision changes — deferred,
   read-only Analytics Token cannot trade). Dhan = execution now. Architecture keeps
   the seam so execution broker can change without rework.

## C. New architecture layer not in v0.4: the Data Foundation

v0.4's Module I-1 (Data Engine) assumed Dhan. The actual data foundation being built is
Upstox-based and broader. Three data domains:
- **Domain 1 — Universe stocks** (2,296 companies): fundamentals + OHLCV — **both now
  BUILT** (OHLCV in R2; fundamentals Tier-1 screening + Tier-2 archive in Supabase).
  Filtered downstream into Fortuna-Cash watchlists.
- **Domain 2 — All NSE indices** (~139, minus Nifty 50): OHLCV only (indices have no
  fundamentals). For sector/theme/regime analysis.
- **Domain 3 — Nifty 50** (separate): OHLCV all timeframes incl. intraday + (near
  future) options data, for index-options trading.

Storage split: reference/output data → Supabase Postgres; bulk historical OHLCV →
Parquet in **Cloudflare R2** (bucket `fortuna-ohlcv`, zero egress — superseded the
original Supabase Storage plan). Broker-namespaced folders (`dhan/`, `upstox/`) for
swappability.

See `fortuna_code_flow.md` for the file/DB flow, `fortuna_multi_strategy_roadmap.md`
for the full data/watchlist plan.

## D. Watchlists (new concept, not in v0.4)

Watchlists are DERIVED views over the shared universe data (not separate storage). A
stock lives once; watchlists are membership pointing at it. Planned:
- Watchlist 1: fundamentally-good — first screen RAN (~98-137 stocks pass the ~10
  Upstox-available criteria; banks included after the revenue-parsing fix). Persistence
  design settled (criteria + materialized members: `f_watchlists` + `f_watchlist_members`,
  source flag for screen-vs-manual) but NOT yet built — open item. Three planned lists:
  fundamentals-swing, fundamentals-longterm, options/F&O.
- Watchlist 2: F&O-eligible (~208, from `is_fno_eligible` flag).
- 5 screening criteria deferred (Path A, reserved NULL columns): market cap (NSE
  quote-equity), pledge %, debt/equity, interest coverage, 5yr growth (external sources).
- Future: Nifty-decoupled (low index correlation), news-momentum, cross-asset rotation.

## E. Unchanged from v0.4 (still authoritative)

- Three-tool architecture (Fortuna-Index → Cash → Options).
- Five-stage Direction/Foundation Funnel (MAC/NAT/FLO/PRE/ENG) → dual view → two books.
  (Branch A / OPT-1..5 complete per build log; Branch B skeleton locked.)
- Risk-management framework + SL-hunt logic.
- Manual-execution-only rule.
- Stack: FastAPI · Supabase · Claude API · TradingView · VectorBT.
