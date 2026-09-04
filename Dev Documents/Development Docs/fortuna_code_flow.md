# Fortuna — Code Flow: Upstox Data Pipeline

How the data-layer pieces connect. Read top-to-bottom to understand the flow from
"nothing" to "populated catalogue + (future) price/fundamentals data."

Last updated: 2026-09-04. All three steps are now BUILT (catalogue, OHLCV, fundamentals) —
plus daily OHLCV refresh, options-intraday OHLCV, and daily news — all also BUILT.

> **For the DEEP pipeline reference** (full call-trees, per-stock walk-throughs, rate-limit
> playbook, verification quirks + SQL) see `fortuna_data_pipeline_flow.md`. This doc is the
> higher-level "how the pieces connect" overview.

---

## The big picture: three steps (all built)

**Step 1 — Instrument Catalogue (DONE).** Build the *directory* of what exists. You
can't fetch "Reliance's price history" until you know Reliance's `instrument_key` /
ISIN — that comes from the catalogue. The phone book, not the conversations.

**Step 2 — OHLCV (DONE).** Loop the catalogue → fetch price history → one Parquet per
instrument in **Cloudflare R2** (bucket `fortuna-ohlcv`, zero egress).

**Step 3 — Fundamentals (DONE).** Loop the stock catalogue → fetch company fundamentals
→ Supabase tables (Tier-1 screening + Tier-2 JSONB archive).

Every step follows the same shape: **catalogue → progress ledger → orchestrator → store
→ engine/API → destination**, and every bulk run is **resumable** via its ledger.

---

## Step 1 flow (built + proven end-to-end)

```
                        .env  (UPSTOX_ANALYTICS_TOKEN, F_SUPABASE_URL, F_SUPABASE_KEY)
                          |
                          v
   upstox_auth_client.py  ......  owns Upstox auth. get_analytics_client() returns a
        |                         pre-authed requests.Session (Bearer token). Also a
        |                         stubbed get_trading_client() (Rule #16, not built).
        |                         [Note: instrument-list download is a PUBLIC file, so
        |                          it doesn't even need the token — auth is for the
        |                          future OHLCV/fundamentals API calls.]
        |
        v
   fetch_universe_instrument_list.py        fetch_index_instrument_list.py
   fetch_index_instrument_list.py           (same shape, NSE_INDEX filter)
        |                                         |
        |  downloads NSE.json.gz (public),        |  downloads same file,
        |  filters segment=NSE_EQ AND             |  filters segment=NSE_INDEX
        |  instrument_type=EQ, cross-refs         |  (all 139 indices)
        |  NSE_FO underlyings for F&O flag        |
        |  => 2,296 stock rows (post ETF split)                    |  => 139 index rows
        |                                         |
        |  DEFAULT run = verify only (prints      |  same two modes
        |  summary, NO db). --sync = write.       |
        |                                         |
        +---------------------+-------------------+
                              |  (on --sync)
                              v
                   instrument_store.py  ......  owns DB writes for BOTH catalogue
                        |                       tables via CATALOG_CONFIG registry
                        |                       (one code path, config-driven — same
                        |                       pattern as Dhan's index_store.py).
                        |                       sync_catalog() = upsert + reconcile.
                        v
                   db/supabase_client.py  .....  shared service-role client
                        |                        (get_supabase()). NOT built per-file.
                        v
        +-----------------------------+-----------------------------+
        |                             |                             |
   f_universe_instruments      f_all_nse_index_instruments    (both in Supabase
   2,296 stock rows            139 index rows                  Postgres, RLS
   (+ f_etf_instruments,                                       service-role-only)
    347 ETFs, split out)
```

### What each file is responsible for (single responsibility)

| File | Responsibility | Does NOT do |
|---|---|---|
| `upstox_auth_client.py` | Own Upstox auth; hand out authed session | Fetch/parse/store data |
| `fetch_universe_instrument_list.py` | Download+parse+filter STOCK list | Write to DB (delegates to store) |
| `fetch_index_instrument_list.py` | Download+parse+filter INDEX list | Write to DB (delegates to store) |
| `instrument_store.py` | Upsert + soft-delete reconcile, both catalogue tables | Download/parse (that's the fetchers) |
| `db/supabase_client.py` | Own the Supabase connection (shared infra) | Know about any specific table |

This mirrors the existing Dhan side exactly:
`indices.py` (fetch) + `index_store.py` (store) + `db/supabase_client.py` (infra).

---

## What's in the database (DB layer)

### `f_universe_instruments` (Migration 003) — stocks
One row per tradable equity (2,296 after ETFs split to `f_etf_instruments`). PK = `instrument_key` (stable; preferred over
exchange_token which can be reused). Columns: instrument_key, trading_symbol, name,
isin, exchange, segment, instrument_type, is_fno_eligible, is_active, created_at,
updated_at (IST). Indexes on (exchange,segment,is_active), F&O subset, isin.

### `f_all_nse_index_instruments` (Migration 004) — indices
One row per NSE index. Same shape MINUS isin/is_fno_eligible (indices have neither).
PK = instrument_key. is_active for soft-delete.

### Key DB behaviors
- **Upsert on PK** → idempotent. Re-running a sync never duplicates (proven: 2nd run
  returned HTTP 200 update, still 2,296 rows).
- **Soft-delete** → `reconcile_active()` sets is_active=false for instruments that
  vanished from today's Upstox file; NEVER deletes. Delisted names keep their row +
  (future) historical data for research. Fetchers skip is_active=false rows.
- **IST audit timestamps** → created_at/updated_at via shared now_ist() SQL helper,
  so rows read in Indian market time on any server (incl. UTC-hosted Render).
- **RLS service-role-only** → anon/authenticated roles get zero access; backend uses
  the service_role key (F_SUPABASE_KEY) which bypasses RLS.

---

## Step 2 flow — OHLCV (BUILT)

```
   read catalogue (f_universe_instruments / f_all_nse_index_instruments) → instrument_keys
        |
        v
   fetch_universe_ohlcv.py / fetch_index_ohlcv.py   ← thin callers, each a DomainConfig
        |
        v
   _ohlcv_backfill_runner.py   ← shared: run_backfill(cfg) / cli_main(cfg)
        |    seed → f_ohlcv_fetch_progress (ledger) → get_pending → loop
        v
   ohlcv_store.backfill_instrument(ik, domain)
        |    └── _ohlcv_engine.fetch_all_timeframes(ik)  (1d paginated in decade chunks,
        |            1w/1mo single calls) → request_get()
        |    └── _write_df() → get_r2().put_object(Parquet)   [fetch-first, atomic]
        v
   R2 bucket fortuna-ohlcv:
     upstox/universe/<ISIN>.parquet   (per stock, 1d/1w/1mo stacked via a `timeframe` col)
     upstox/indices/<slug>.parquet    (per index)
```
Resumability: `f_ohlcv_fetch_progress` marks each instrument pending/done/failed; a
re-run skips `done`. Result: 135 indices + 2,638 stocks, ~287 MB. `update_instrument()`
(merge-dedup on (timeframe, ts)) powers the **daily refresh — now BUILT** (see below).

## Step 2b flow — daily OHLCV refresh (BUILT, 2026-09-04)

```
   refresh_index_ohlcv.py      refresh_universe_ohlcv.py       ← thin domain callers
      |  domain="indices"          |  domain="universe"
      └───────────┬─────────────────┘
                  v
        _ohlcv_refresh_runner.py       ← shared, separate from backfill runner
              |    get_done(domain) → instruments already status='done'
              v
   ohlcv_store.update_instrument(ik, domain)
        |    └── _ohlcv_engine.fetch_full_history()  windowed only (10d/21w-lookback/95mo-lookback,
        |            NOT full history despite the function name)
        |    └── merge-dedup vs existing Parquet → compare to existing:
        |            identical  → R2 write SKIPPED (changed=False, bytes_written=0)
        |            different  → _write_df() → put_object (atomic)
        v
   mark_done(ik) on every successful check (changed or not) — NOT mark_failed() on a
   miss (would wrongly route into the backfill queue); a miss self-heals via next
   run's overlapping lookback window.
```
Cadence: all 3 timeframes (1d/1w/1mo) every run, no calendar branching — the no-op
skip above makes daily W/M checking cheap. Verified live: full sweep both domains
(universe 2,641 instruments ~1h17m, indices 135 ~4min); a same-day re-run correctly
reported `succeeded: 0, unchanged: 5, data written: 0.00 MB` on already-current data.
Logs to `logs/ohlcv_refresh_<domain>.log` (overwritten per run) + console. Trigger is
manual CLI; cron wiring deferred. **Window logic redesigned 2026-09-04**: was fixed
per-unit days (10/21/95), now dynamic `last_success_at → today` (any gap size
self-heals, not just gaps smaller than a fixed window) — no buffer, per Rule #18
(don't invent unconfirmed concerns). Full detail: `fortuna_data_pipeline_flow.md` §2.4.

## Step 2c flow — options-intraday OHLCV (BUILT, 2026-09-04)

Same engine as Step 2, extended not forked, scoped to F&O-eligible stocks only
(`is_fno_eligible=True`, 208 of 2,296) with 5m/15m/60m timeframes and a 1-year
bounded backfill (not full since-2022). New R2 folder
`upstox/universe_intraday/<ISIN>.parquet`. Required a ledger fix (see below) since
these 208 stocks already had a `domain='universe'` row and a second-domain seed
silently no-op'd on the single-column-PK upsert. Full backfill: 208/208 succeeded,
105.93 MB. Full detail: `fortuna_data_pipeline_flow.md` §2.6-2.7.

## Step 4 flow — News (BUILT, 2026-09-04)

All 2,782 instruments (universe + ETF + indices, not just options stocks), batched
30/call, no ledger (finishes in under a minute). Perishable — Upstox's News API only
returns the last 7 days, no date-range param, no backfill possible. Stored
relationally (`f_news_articles` in Supabase), not R2 Parquet — point-lookup-by-stock
read pattern, not bulk scan. Dedup via unique `(instrument_key, article_link)` +
ignore-duplicates upsert. `fetch_news_batch_resilient()` bisects on the
invalid-key error class specifically to isolate one bad key without losing the other
29 in its batch — found the 4 BHARATBOND indices already known-bad for OHLCV, fixed
at the source (`is_active=false`) rather than a second exclusion list. Full detail:
`fortuna_data_pipeline_flow.md` §2A.

**Not yet built:** live option chain snapshots (15-min cadence, 208 F&O stocks) and
expired option historical candles (Plus-gated, 6-month expiry depth limit found).

## Step 3 flow — Fundamentals, stocks only (BUILT)

```
   read f_universe_instruments (EQ; ETFs split into f_etf_instruments, indices have none)
        |
        v
   Tier-1 (screening):  fetch_universe_fundamentals.py
        |    seed → f_fundamentals_fetch_progress → loop
        |    └── fundamentals_store.store_fundamentals(screening_only=True)
        |          4 endpoints (profile, key-ratios, income, share-holdings)
        |          → upsert f_fundamentals_profile + f_fundamentals_metrics
        |
   Tier-2 (archive):    backfill_universe_fundamentals_onetime.py   [auto-cooldown]
        |    seed → f_fundamentals_tier2_progress → loop (per-stock 2-attempt→30min sleep)
        |    └── fundamentals_store.store_tier2_statements()
        |          4 endpoints (balance-sheet, cash-flow, corporate-actions, competitors)
        |          → upsert f_fundamentals_statements (JSONB)
        v
   3 Supabase tables (NOT 8 — decided against one-table-per-endpoint):
     f_fundamentals_profile     — descriptive (sector, profile, sector mcap)
     f_fundamentals_metrics     — screening workhorse (ratios/growth/ownership + reserved
                                  NULL gap cols: market_cap, pledge, debt/equity, 5yr…)
     f_fundamentals_statements  — Tier-2 JSONB archive (4 deep endpoints)
```
Parsing lives in `fundamentals_store.py`: conditional `%`-strip, core-Revenue with a
Total-Revenue fallback for banks, computed growth/CAGR sorted newest-first, CAGR NULL
through losses. Result: Tier-1 2,296 stocks, Tier-2 2,290 archived.

## Run reference

All from `backend/`, using the `-m` module flag:
```
# verify only (no DB):
python -m modules.market_data.upstox.fetch_universe_instrument_list
python -m modules.market_data.upstox.fetch_index_instrument_list

# fetch + write to DB:
python -m modules.market_data.upstox.fetch_universe_instrument_list --sync
python -m modules.market_data.upstox.fetch_index_instrument_list --sync

# auth smoke test:
python -m modules.market_data.upstox.upstox_auth_client

# OHLCV backfill (Step 2):
python -m modules.market_data.upstox.fetch_index_ohlcv    [--limit N] [--quiet]
python -m modules.market_data.upstox.fetch_universe_ohlcv [--limit N] [--quiet]

# OHLCV daily refresh (Step 2b):
python -m modules.market_data.upstox.refresh_index_ohlcv    [--limit N] [--quiet]
python -m modules.market_data.upstox.refresh_universe_ohlcv [--limit N] [--quiet]

# Options-intraday OHLCV, F&O stocks only (Step 2c):
python -m modules.market_data.upstox.fetch_universe_options_intraday_ohlcv   [--limit N]
python -m modules.market_data.upstox.refresh_universe_options_intraday_ohlcv [--limit N]

# Daily news, all instruments (Step 4):
python -m modules.market_data.upstox.fetch_daily_news [--limit N] [--quiet]

# Fundamentals Tier-1 screening (Step 3):
python -m modules.market_data.upstox.fetch_universe_fundamentals [--limit N] [--quiet]

# Fundamentals Tier-2 archive (Step 3, one-time, auto-cooldown):
python -m modules.market_data.upstox.backfill_universe_fundamentals_onetime [--limit N] [--quiet]
```
(`--limit N` = verify on first N before a full run; `--quiet` = less log noise.)
