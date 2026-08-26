# Fortuna — Code Flow: Upstox Data Pipeline

How the data-layer pieces connect. Read top-to-bottom to understand the flow from
"nothing" to "populated catalogue + (future) price/fundamentals data."

Last updated: 2026-08-26. All three steps are now BUILT (catalogue, OHLCV, fundamentals).

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
(merge-dedup on (timeframe, ts)) exists for the future incremental refresh.

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

# Fundamentals Tier-1 screening (Step 3):
python -m modules.market_data.upstox.fetch_universe_fundamentals [--limit N] [--quiet]

# Fundamentals Tier-2 archive (Step 3, one-time, auto-cooldown):
python -m modules.market_data.upstox.backfill_universe_fundamentals_onetime [--limit N] [--quiet]
```
(`--limit N` = verify on first N before a full run; `--quiet` = less log noise.)
