# Fortuna — Data Pipeline Flow & Algorithms

**Scope:** how market data is fetched and stored — OHLCV (price history) and Fundamentals
(company financials, Tier‑1 screening + Tier‑2 archive). Covers the call trees (which
function calls which), the step‑by‑step algorithms, every real file/function/table name,
and the rate‑limit handling that shapes the whole thing.

_Last updated: 2026‑08‑26._

---

## 0. The one pattern everything follows

Both pipelines are built from the **same five‑layer shape**. Learn it once, and every
flow below is a variation on it:

```
   CATALOGUE            what instruments exist            (Supabase table)
       │
       ▼
   PROGRESS LEDGER      what's done / pending / failed     (Supabase table)  ← resumability
       │
       ▼
   ORCHESTRATOR         loops pending, paces, handles      (a fetch_/backfill_ .py)
       │                rate limits, marks status
       ▼
   STORE                fetch one instrument, parse,       (a _store .py)
       │                write it
       ▼
   ENGINE / API         the actual Upstox call             (_ohlcv_engine / request_get)
       │
       ▼
   DESTINATION          where the data lands               (R2 Parquet, or Supabase tables)
```

**Why the ledger exists:** every bulk run can be interrupted (rate limit, network drop,
laptop sleep). The progress ledger records per‑instrument status, so a **re‑run skips
what's `done` and resumes** — no run ever has to start over. This is the backbone of
every backfill.

---

## 1. Storage map — where each kind of data lives

| Data | Store | Real location | Why there |
|---|---|---|---|
| Instrument catalogues | Supabase Postgres | `f_universe_instruments`, `f_all_nse_index_instruments`, `f_etf_instruments` | small, relational, queried |
| OHLCV price history | Cloudflare R2 | bucket `fortuna-ohlcv`, keys `upstox/universe/<ISIN>.parquet`, `upstox/indices/<slug>.parquet` | big, read‑heavy, zero‑egress |
| Fundamentals — screening | Supabase Postgres | `f_fundamentals_profile`, `f_fundamentals_metrics` | filtered across all stocks (watchlists) |
| Fundamentals — archive | Supabase Postgres | `f_fundamentals_statements` (JSONB) | deep per‑stock, occasional |
| Progress ledgers | Supabase Postgres | `f_ohlcv_fetch_progress`, `f_fundamentals_fetch_progress`, `f_fundamentals_tier2_progress` | resumability state |

**Shared infra clients:** `db/supabase_client.py → get_supabase()` and
`db/r2_client.py → get_r2()`, `get_r2_settings()`. Auth for Upstox:
`upstox_auth_client.py → request_get(path, params)` (adds retry/backoff on 429/5xx).

---

## 1.5 Walk‑throughs — follow one stock end‑to‑end

The call‑trees below show the *wiring* (which function calls which). These two narratives
show the *electricity* — what actually happens to one stock, in order, as it moves through
all five layers. Read these first if the trees feel abstract; the concrete journey makes
the structure click.

### Walk‑through A — one stock through the OHLCV pipeline

You run `python -m modules.market_data.upstox.fetch_universe_ohlcv`.

The thin caller `fetch_universe_ohlcv.py` wakes up holding a `UNIVERSE_CONFIG`
(a `DomainConfig`) that says two things: domain is `universe`, catalogue is
`f_universe_instruments`. It hands that config to the shared runner and does nothing else.
(This is why indices and stocks share all the machinery — the only difference is the config.)

`_ohlcv_backfill_runner.py` takes over:
- `_load_catalogue()` reads every active row from `f_universe_instruments` (~2,296 keys).
- `seed_instruments()` writes a `pending` row for each into `f_ohlcv_fetch_progress`
  (skipping any already there).
- `get_pending()` asks the ledger who still needs fetching → the work list.

Now follow **Reliance** (`NSE_EQ|INE002A01018`):
1. `mark_attempt(...)` — the ledger's `attempt_count` ticks up, `last_attempt_at` stamped.
   This happens *before* the fetch, so if the laptop dies mid‑fetch, the ledger already
   knows an attempt was underway.
2. `backfill_instrument(ik, 'universe')` → `fetch_all_timeframes()` needs 1d/1w/1mo.
   Daily can't come in one call (API span cap), so `fetch_full_history()` paginates
   backwards in ~decade chunks, each calling `fetch_candles()` → `request_get()` (the real
   HTTP hit). Weekly/monthly are single calls.
3. All candles flatten into one DataFrame (a `timeframe` column tags each row `1d`/`1w`/`1mo`).
4. `_write_df()` serialises to Parquet and `put_object`s it to R2 at
   `upstox/universe/INE002A01018.parquet`. This write happens **only because data came
   back** — a failed fetch writes nothing and leaves any existing file untouched.
5. `mark_done(...)` — status flips to `done`, `last_success_at` stamped. Sleep 0.25s.
   Next stock.

Ctrl+C and re‑run tomorrow → Reliance is `done`, so `get_pending()` skips it. That's
resumability in one sentence.

### Walk‑through B — one stock through the Tier‑2 archive, hitting the rate wall

You run `python -m modules.market_data.upstox.backfill_universe_fundamentals_onetime --quiet`.

The orchestrator loads ~2,296 stocks, seeds `f_fundamentals_tier2_progress`, gets the
pending list. It reaches stock 495: **INE142M01025**.

1. `store_tier2_statements('INE142M01025', 'NSE_EQ|INE142M01025')` →
   `_fetch_tier2_endpoints()` fires 4 calls: balance‑sheet, cash‑flow, corporate‑actions,
   competitors.
2. But the window is spent (~494 stocks × 4 ≈ 1,976 calls, past 1000/30min). Balance‑sheet
   returns **429**. The innermost layer — `request_get()`'s retry — tries again at 1s, 2s,
   still 429, gives up on that endpoint. Same for the other three.
3. **Completeness rule:** because ≥1 endpoint was rate‑limited, `store_tier2_statements`
   does **not** write a partial row. It returns `rate_limited=True`. (Without this fix, a
   half‑empty row would be saved and marked done — permanently incomplete.)
4. Orchestrator, **attempt 1:** logs "rate‑limited (attempt 1/2); pausing 10s then retry."
   Sleeps 10s, retries the **same** stock (doesn't move on).
5. **Attempt 2:** still 429 (10s wasn't enough). Now: "rate‑limited twice. Auto‑sleeping
   30 min… [auto‑sleep #1]." Sleeps a full 30 minutes — long enough for the rolling window
   to fully reset. Stays on stock 495; `i` does not advance.
6. 30 minutes later it resumes the same stock on a fresh window. The 4 calls succeed, the
   JSONB writes to `f_fundamentals_statements`, `mark_done`, and it advances to 496.

That's why today's run finished 2,290/2,290 with zero failures despite hitting the wall
4 times — each wall triggered a self‑managed 30‑min nap, then continued exactly where it
left off, untouched for ~3 hours.

---

## 2. OHLCV pipeline

### 2.1 What it produces
One Parquet file per instrument in R2, containing **all three Tier‑1 timeframes stacked**
(a `timeframe` column: `1d` / `1w` / `1mo`), full history back to 2000 (or the
instrument's inception).

### 2.2 Call tree (inverted — top calls down)

```
  fetch_index_ohlcv.py        fetch_universe_ohlcv.py         ← thin domain callers
      │  INDEX_CONFIG               │  UNIVERSE_CONFIG            (each = a DomainConfig)
      │  domain="indices"          │  domain="universe"
      │  table=f_all_nse_          │  table=f_universe_
      │        index_instruments   │        instruments
      └───────────┬────────────────┘
                  ▼
        _ohlcv_backfill_runner.py           ← shared orchestration (DRY)
          cli_main(cfg)
            └── run_backfill(cfg, limit)
                  ├── _load_catalogue(cfg)                 → reads the catalogue table
                  ├── ohlcv_fetch_progress.seed_instruments(rows)
                  ├── ohlcv_fetch_progress.get_pending(domain)
                  └── for each pending instrument:
                        ├── ohlcv_fetch_progress.mark_attempt(ik)
                        ├── ohlcv_store.backfill_instrument(ik, domain)     ← STORE
                        │        ├── _ohlcv_engine.fetch_all_timeframes(ik) ← ENGINE
                        │        │        └── fetch_full_history() → fetch_candles()
                        │        │                 └── upstox_auth_client.request_get()
                        │        ├── _results_to_df(results)
                        │        └── _write_df() → get_r2().put_object(Parquet)  ← R2
                        ├── mark_done(ik)   or   mark_failed(ik, err)
                        └── sleep(THROTTLE_SECONDS = 0.25)
```

### 2.3 Algorithm — OHLCV backfill (per domain)

1. **Load catalogue** — `_load_catalogue(cfg)` reads all `is_active=true` rows from
   `cfg.catalogue_table`, returns `(instrument_key, domain)` tuples.
2. **Seed ledger** — `seed_instruments()` upserts a `pending` row per instrument into
   `f_ohlcv_fetch_progress` (idempotent: `ignore_duplicates`, never resets `done`).
3. **Get work list** — `get_pending(domain)` returns rows with status `pending` or
   `failed` (failed are retried).
4. **Loop each instrument:**
   a. `mark_attempt` — bump `attempt_count`, stamp `last_attempt_at`.
   b. `backfill_instrument(ik, domain)`:
      - `fetch_all_timeframes` pulls 1d/1w/1mo. Daily paginates in ~decade chunks
        (V3 API limit); weekly/monthly are single calls.
      - Rows flattened to a DataFrame (`timeframe`, `ts`, `trade_date`, OHLC, volume, OI).
      - **Fetch‑first, atomic write:** `put_object` only runs if data came back; it
        atomically replaces the object. A failed fetch never destroys an existing file.
   c. `mark_done` on success (stamps `last_success_at`), else `mark_failed` with the error.
   d. `sleep(0.25s)` — proactive pace.
5. **Summary** — attempted / succeeded / failed / bytes written + ledger counts.

### 2.4 Update (daily/weekly/monthly) — future scheduler
`ohlcv_store.update_instrument(ik, domain, timeframes)` fetches a short recent window
(days=10/weeks=21/months=95), reads the existing Parquet, **merges + dedups on
(timeframe, ts)**, atomically writes back. The **scheduler decides which timeframes**
to refresh (1d daily, 1w after Friday, 1mo after month‑end) — the store doesn't hardcode
cadence. _Not built yet; resumability + merge logic are in place._

### 2.5 Status (2026‑08‑26)
Indices: 135 done, 4 failed (BHARATBOND bond indices — Upstox rejects for candles).
Stocks: 2,638 done, 2 failed (illiquid/new). ~287 MB in R2. Content‑verified
(India VIX, Reliance).

---

## 3. Fundamentals pipeline

Upstox **Company Fundamentals API**: 8 endpoints, base `/v2/fundamentals/{ISIN}/...`,
keyed by ISIN **except `competitors`** (needs `instrument_key` = `NSE_EQ|<ISIN>`).
Split into **Tier‑1 (screening, 4 endpoints)** and **Tier‑2 (archive, 4 endpoints)**.

| Tier | Endpoints | → writes | Purpose |
|---|---|---|---|
| Tier‑1 | profile, key‑ratios, income‑statement, share‑holdings | `f_fundamentals_profile`, `f_fundamentals_metrics` | watchlist screening |
| Tier‑2 | balance‑sheet, cash‑flow, corporate‑actions, competitors | `f_fundamentals_statements` (JSONB) | deep‑dive archive |

### 3.1 Tier‑1 — screening backfill (DONE)

**Orchestrator:** `fetch_universe_fundamentals.py` (`run(screening_only=True)`).
**Store:** `fundamentals_store.store_fundamentals(isin, ik, screening_only=True)`.

```
  fetch_universe_fundamentals.py
    run(limit, screening_only=True)
      ├── _load_eq_stocks()                → f_universe_instruments (is_active, EQ)
      ├── _seed(rows)                      → f_fundamentals_fetch_progress
      ├── _get_pending()                   → status in (pending, failed)
      └── for each stock:
            ├── _mark_attempt(isin)
            ├── fundamentals_store.store_fundamentals(isin, ik, screening_only=True)
            │       ├── _fetch_all_endpoints(screening_only=True)   → 4 endpoints
            │       │        └── request_get() per endpoint
            │       ├── build_rows() → parse:
            │       │     _parse_key_ratios / _parse_income / _parse_holdings / _parse_profile
            │       └── upsert profile_row → f_fundamentals_profile
            │           upsert metrics_row → f_fundamentals_metrics   (NOT statements)
            ├── _mark_done / _mark_failed / (rate‑limited → stays pending)
            └── sleep(BASE_THROTTLE_SECONDS = 1.0)
```

**Parsing rules that matter (in `fundamentals_store.py`):**
- `_parse_key_ratios`: maps names → columns (P/E→pe, ROE→roe, …). Strips `%`
  **conditionally** (only ROA/ROE/ROCE carry it).
- `_parse_income`: revenue source = core **"Revenue"** line‑item; **falls back to
  "Total Revenue"** when "Revenue" absent (banks/NBFCs report only Total Revenue).
- Growth **computed** (`_yoy`, `_cagr`) from the chosen revenue series — not the API's
  ready‑made change% (which is on Total Revenue). Periods are **sorted newest‑first**
  by parsed label (`_period_key`) — never trusts array order.
- `_cagr` returns `None` unless **both endpoints > 0** (a negative base yields a complex
  number — which also isn't JSON‑serialisable; guarded).
- Reserved gap columns left NULL (see §3.4).

### 3.2 Tier‑2 — archival backfill (ONE‑TIME)

**Why one‑time + archival:** Upstox serves only a rolling ~4 years. A company boring
today may matter later, and its early years will have rolled off by then. So we capture
every stock's deep statements **now, once**, to preserve them. A future
`update_universe_fundamentals_qtrly.py` will **append** new periods without overwriting.

**Orchestrator:** `backfill_universe_fundamentals_onetime.py`.
**Store:** `fundamentals_store.store_tier2_statements(isin, ik)`.

```
  backfill_universe_fundamentals_onetime.py
    run(limit)
      ├── _load_stocks()                   → f_universe_instruments (is_active, EQ)
      ├── _seed(rows)                      → f_fundamentals_tier2_progress   ← OWN ledger
      ├── _get_pending()
      └── while i < len(pending):          ← per‑stock 2‑attempt loop (see §4)
            for attempt in (1, 2):
              ├── _mark_attempt(isin)
              ├── fundamentals_store.store_tier2_statements(isin, ik)
              │       ├── _fetch_tier2_endpoints()   → balance‑sheet, cash‑flow,
              │       │                                 corporate‑actions, competitors
              │       ├── if ANY endpoint 429'd → return rate_limited (NO partial write)
              │       └── else upsert → f_fundamentals_statements (4 JSONB cols)
              ├── ok        → _mark_done, advance
              ├── no‑data   → _mark_failed, advance
              └── rate‑limited:
                    attempt 1 → sleep 10s, retry same stock
                    attempt 2 → sleep 30 min, then retry SAME stock (no advance)
```

**Archival‑completeness rule:** if *any* of the 4 endpoints is rate‑limited,
`store_tier2_statements` does **not** write a partial row — the whole stock stays
retryable. (Storing 2‑of‑4 and marking `done` would permanently archive incomplete data.)

_Does NOT touch profile/metrics — screening data is untouched. `store_fundamentals`
(the Tier‑1 path) is left intact for future disaster‑recovery re‑backfills._

### 3.3 Verify‑before‑build (how each fundamentals piece was proven)
- `_fundamentals_spike.py` — dumped all 8 endpoints for Reliance to see real shapes.
- `_bank_income_spike.py` — showed banks lack a "Revenue" line‑item → the Total‑Revenue
  fallback.
- `store_fundamentals(write=False)` — parsed Reliance and printed the metrics row to
  confirm every number before any DB write.

### 3.4 Reserved gap columns (in `f_fundamentals_metrics`, filled later)
| Column | Filled by | Note |
|---|---|---|
| `market_cap_cr`, `shares_outstanding`, `face_value` | NSE quote‑equity job | issuedSize × price (accurate; Upstox has no reliable share count) |
| `pledge_pct` | NSE disclosure feed | not in quote‑equity |
| `debt_to_equity`, `interest_coverage`, `revenue_growth_5y`, `net_profit_growth_5y` | external (Screener/Yahoo) | borrowings/interest not broken out; only 4yr history |

### 3.5 Status (2026‑08‑26)
Tier‑1: 2,296 stocks done (banks recovered via the Total‑Revenue fallback; ~411 legit
NULL‑revenue remain — genuinely dataless/new). Tier‑2: 2,290 stocks archived, 0 failed.

### 3.6 Verifying the data — quirks to know & how to cross‑check

Real data‑shape facts learned while verifying. Know these before trusting a screen or
chasing a "bug" that isn't one.

**Quirk 1 — latest period is per‑stock, NOT uniform.** `f_fundamentals_metrics.latest_period`
can be `Mar 2026` for early reporters (Reliance, SBI) but `Mar 2025` for others (e.g. KRBL)
— because companies file on different schedules and Upstox has newer data for some. This
is correct, not a bug. Implication: a screen compares a Mar‑2026 growth number against a
Mar‑2025 one. Usually fine (annual fundamentals move slowly), but `latest_period` is stored
precisely so you can *see* each stock's vintage and, if freshness matters, filter on it
(e.g. `WHERE latest_period = 'Mar 2026'`).

**Quirk 2 — the statements table has two permanently‑NULL columns.**
`f_fundamentals_statements.income_statement` and `.holdings` are always NULL. By design:
the Tier‑2 run writes only its 4 columns (balance_sheet, cash_flow, corporate_actions,
competitors); income & holdings live parsed‑into‑columns in `f_fundamentals_metrics`
instead. Nothing is missing — it's just in the other table. (Minor schema smell; harmless.)

**Quirk 3 — Tier‑2 statements lag Tier‑1 metrics by ~1 year.** Balance‑sheet/cash‑flow
latest may be `Mar 2025` while the income metrics show `Mar 2026`, because audited full
statements finalise later than headline results. Normal reporting lag; still real years,
so fine for the archival purpose.

**Quirk 4 — negative CAGR is valid.** A profit CAGR like KRBL's `‑2.58%` is correct — profit
declined but stayed positive across the window, so the compound rate is a real negative.
(`_cagr` only returns NULL when a value goes ≤0, which would make the math complex/undefined.)

**Cross‑check method (efficient):**
- **Breadth — Chartink.** Run the *same criteria* as a Chartink screen and as your SQL,
  then compare the resulting stock *lists*. Matching lists validates hundreds of stocks'
  numbers at once. Expect ~80‑90% overlap, not 100% — sources define ROCE / "3yr growth" /
  consolidated‑vs‑standalone slightly differently. *Systematic* divergence (wildly different
  lists, or all your growth numbers consistently off) = real bug; a few edge misses =
  definitional.
- **Depth — Screener.in.** Field‑by‑field check on 3‑4 stocks (one manufacturer, one bank,
  one NBFC) for exact revenue / promoter % / EPS.
- **Always pull all 3 tables for one ISIN together** (query below) to eyeball cross‑table
  consistency in one glance: same ISIN, profile matches metrics matches statements, periods
  align sensibly.

**Verification join — all 3 fundamentals tables for one stock:**
```sql
-- Pass any ISIN. Returns profile + metrics + which Tier-2 statements are present.
SELECT
    u.name,
    p.sector,
    -- valuation / returns
    m.pe, m.pb, m.roe, m.roce, m.quick_ratio,
    -- core figures
    m.revenue_cr, m.net_profit_cr, m.eps_basic,
    -- growth (computed)
    m.revenue_growth_1y, m.revenue_cagr_3y,
    m.net_profit_growth_1y, m.net_profit_cagr_3y,
    -- ownership
    m.promoter_pct, m.fii_pct, m.dii_pct, m.mutual_fund_pct,
    -- vintages (Quirk 1 & 3)
    m.latest_period            AS metrics_period,
    m.holdings_period,
    -- Tier-2 presence (true = that JSONB archived)
    (s.balance_sheet     IS NOT NULL) AS has_balance_sheet,
    (s.cash_flow         IS NOT NULL) AS has_cash_flow,
    (s.corporate_actions IS NOT NULL) AS has_corporate_actions,
    (s.competitors       IS NOT NULL) AS has_competitors
FROM f_universe_instruments u
LEFT JOIN f_fundamentals_profile    p ON p.isin = u.isin
LEFT JOIN f_fundamentals_metrics    m ON m.isin = u.isin
LEFT JOIN f_fundamentals_statements s ON s.isin = u.isin
WHERE u.isin = 'INE001B01026';   -- ← change ISIN
```

**Bulk Tier‑2 completeness check (is the whole archive intact?):**
```sql
SELECT
    COUNT(*)                                                    AS total,
    COUNT(*) FILTER (WHERE balance_sheet     IS NOT NULL)       AS has_bs,
    COUNT(*) FILTER (WHERE cash_flow         IS NOT NULL)       AS has_cf,
    COUNT(*) FILTER (WHERE corporate_actions IS NOT NULL)       AS has_ca,
    COUNT(*) FILTER (WHERE competitors       IS NOT NULL)       AS has_comp
FROM f_fundamentals_statements;
```

---

## 4. Rate‑limit handling — the playbook

Upstox limits (flat, **not** raised by the Plus plan): **25/sec, 250/min, 1000 / 30 min.**
The binding one for a sustained bulk job is **1000 per 30‑minute rolling window.**
Fundamentals = 4 calls/stock, so ~250 stocks exhausts a window.

**Layers of defence (innermost → outermost):**

1. **`request_get` retry/backoff** (`upstox_auth_client.py`) — on a single 429/5xx,
   waits 1s → 2s → 4s, up to 3 tries. Handles transient blips.
2. **Proactive throttle** — a base `sleep` between instruments (OHLCV 0.25s;
   fundamentals 1.0s) so we don't burst.
3. **Rate‑limited ≠ failed** — a stock that 429s after retries is left **`pending`**
   (never marked `failed`), so it's retried, and the `failed` list stays meaningful
   (genuine no‑data / ETFs only).
4. **Auto‑cooldown (Tier‑2 archival):** per‑stock, **2 attempts 10 s apart**; if the
   **2nd** is still rate‑limited, **sleep 30 min** (a full window reset) then resume the
   **same** stock — never moves on while blocked, never skips. Fully unattended.

**Manual playbook if a run stalls (older screening backfill without auto‑cooldown):**
cancel → wait ~30 min for the window to drain → re‑run the same command (resumes from
the ledger). Repeat.

**Perishability note:** don't fetch faster than the limit allows — but *do* run the
Tier‑2 archive, because the 4‑year window is perishable (old years roll off and can't
be re‑fetched later).

---

## 5. Full file & table reference

### Python (all under `backend/modules/market_data/upstox/`, infra under `backend/db/`)
| File | Role |
|---|---|
| `db/supabase_client.py` | `get_supabase()` — shared Postgres client |
| `db/r2_client.py` | `get_r2()`, `get_r2_settings()` — shared R2/S3 client |
| `upstox_auth_client.py` | `request_get()` — authed Upstox calls + 429/5xx retry |
| `_ohlcv_engine.py` | OHLCV fetch core: `fetch_candles`, `fetch_full_history`, `fetch_all_timeframes` |
| `ohlcv_store.py` | Parquet↔R2: `backfill_instrument`, `update_instrument`, `read_candles`, `_write_df` |
| `ohlcv_fetch_progress.py` | OHLCV ledger: `seed_instruments`, `get_pending`, `mark_attempt/done/failed`, `get_counts` |
| `_ohlcv_backfill_runner.py` | shared OHLCV orchestration: `run_backfill(cfg)`, `cli_main(cfg)`, `DomainConfig` |
| `fetch_index_ohlcv.py` | thin caller — `INDEX_CONFIG` (domain=indices) |
| `fetch_universe_ohlcv.py` | thin caller — `UNIVERSE_CONFIG` (domain=universe) |
| `fundamentals_store.py` | fetch+parse+store: `store_fundamentals` (Tier‑1), `store_tier2_statements` (Tier‑2), parsers |
| `fetch_universe_fundamentals.py` | Tier‑1 screening backfill orchestrator |
| `backfill_universe_fundamentals_onetime.py` | Tier‑2 one‑time archival orchestrator (auto‑cooldown) |
| `fetch_universe_instrument_list.py` / `fetch_index_instrument_list.py` | build the catalogues |
| `instrument_store.py` | catalogue upsert store |

### Supabase tables
| Table | Contents |
|---|---|
| `f_universe_instruments` | ~2,296 EQ stocks (ETFs split out) |
| `f_all_nse_index_instruments` | 139 indices |
| `f_etf_instruments` | 347 ETFs (INF‑prefix, split out) |
| `f_ohlcv_fetch_progress` | OHLCV resumability ledger |
| `f_fundamentals_profile` | Tier‑1 descriptive (sector, description, sector mcap) |
| `f_fundamentals_metrics` | Tier‑1 screening (ratios, growth, ownership + reserved gap cols) |
| `f_fundamentals_statements` | Tier‑2 archive (balance‑sheet/cash‑flow/corp‑actions/competitors JSONB) |
| `f_fundamentals_fetch_progress` | Tier‑1 screening ledger |
| `f_fundamentals_tier2_progress` | Tier‑2 archival ledger |

### R2 (bucket `fortuna-ohlcv`)
| Key pattern | Contents |
|---|---|
| `upstox/universe/<ISIN>.parquet` | per‑stock OHLCV (1d/1w/1mo stacked) |
| `upstox/indices/<slug>.parquet` | per‑index OHLCV |

### Migrations
`003` universe · `004` indices · `005` ohlcv progress · `006` fundamentals (3 tables) ·
`007` fundamentals progress · `008` split ETFs · `009` fundamentals tier‑2 progress.

---

## 6. Run commands (quick reference)

```bash
# OHLCV backfill
python -m modules.market_data.upstox.fetch_index_ohlcv    [--limit N] [--quiet]
python -m modules.market_data.upstox.fetch_universe_ohlcv [--limit N] [--quiet]

# Fundamentals Tier‑1 (screening)
python -m modules.market_data.upstox.fetch_universe_fundamentals [--limit N] [--quiet]

# Fundamentals Tier‑2 (one‑time archive, auto‑cooldown)
python -m modules.market_data.upstox.backfill_universe_fundamentals_onetime [--limit N] [--quiet]
```

`--limit N` = verify on the first N (always do this before a full run).
`--quiet` = suppress per‑call logs, show per‑instrument progress + summary.

### 6.1 How to actually run them

- **Run from:** the `backend/` folder (so `modules...` resolves). Example:
  ```bash
  cd D:\Takara\Fortuna\_Repository\backend
  python -m modules.market_data.upstox.fetch_universe_fundamentals --limit 3
  ```
- **`python -m <dotted.path>`** runs a file as a module. The dots are folder separators:
  `modules.market_data.upstox.fetch_universe_fundamentals` = the file
  `modules/market_data/upstox/fetch_universe_fundamentals.py`. We use `-m` (not
  `python path/to/file.py`) so that the file's own `import` lines (e.g.
  `from db.supabase_client import ...`) resolve against `backend/` as the root.
- **Order for any bulk run:** first `--limit 3` (proves it works on 3), eyeball the
  result / DB, then run **without** `--limit` for the full set.
- **`--quiet` is optional** and cosmetic — it only reduces log volume; the run, data,
  and summary are identical with or without it. Use it on long runs so the output is
  readable; drop it if you want to watch every call.
- **Interrupting is safe:** `Ctrl+C` any time. Because of the progress ledger, re‑running
  the **same command** resumes from where it stopped (done rows skipped).

### 6.2 How `--limit` and `--quiet` work in the code (this is new — here's the pattern)

Command‑line flags are read with Python's built‑in **`argparse`** library. Every
orchestrator has the same little block at the bottom, inside `if __name__ == "__main__":`
(the part that runs when you execute the file directly). Walking through it:

```python
import argparse

# 1) Create the parser (the thing that reads the command line).
parser = argparse.ArgumentParser(description="Bulk fundamentals fetch.")

# 2) Declare each flag we accept.
parser.add_argument(
    "--limit",              # the flag name typed on the command line
    type=int,               # convert the value to an int (so "3" → 3)
    default=None,           # if the flag is omitted, limit = None (= no cap)
    help="Process only the first N pending stocks (verify-first).",
)
parser.add_argument(
    "--quiet",
    action="store_true",    # a switch: present → True, absent → False (no value needed)
    help="Less log noise: per-stock progress + problems only.",
)

# 3) Read what the user actually typed.
args = argparse.parse_args()   # in the real files: args = parser.parse_args()
# Now: args.limit is an int or None; args.quiet is True or False.
```

**What each flag then does:**

- **`--limit N`** — after building the pending list, the code simply slices it:
  ```python
  pending = _get_pending()
  if limit is not None:
      pending = pending[:limit]     # keep only the first N
  ```
  So `--limit 3` processes 3 instruments; omitting it (`limit=None`) processes all.

- **`--quiet`** — turns *down* the logging level for the chatty loggers, so their
  `INFO` lines (every HTTP call) stop printing, leaving only warnings/errors + our own
  per‑instrument progress:
  ```python
  if args.quiet:
      for name in ("httpx", "...fundamentals_store", "...upstox_auth_client"):
          logging.getLogger(name).setLevel(logging.WARNING)  # hide INFO, keep WARNING+
  ```
  It changes **only** what prints — not the work done.

**Two `argparse` behaviours worth knowing:**
- Flags are **optional** and **order‑independent**: `--limit 3 --quiet` and
  `--quiet --limit 3` are the same.
- `action="store_true"` flags take **no value** — you write `--quiet`, not `--quiet true`.
  Value flags like `--limit` take one: `--limit 3`.
- `python -m ...module... --help` prints the auto‑generated usage (from the `help=` texts).


---

## 7. Golden rules (why the pipeline is shaped this way)

- **Verify‑first:** spike / `--limit` before every bulk run.
- **Resumable always:** ledger per data type; re‑run resumes, never restarts.
- **Fetch‑first, atomic writes:** never destroy existing data on a failed fetch.
- **Rate‑limited ≠ failed:** keep it retryable; `failed` means genuine no‑data.
- **No partial archive:** Tier‑2 won't store an incomplete row as `done`.
- **Right store for the access pattern:** bulk read‑heavy → R2; filter‑across‑all → Postgres.
- **Don't touch proven code:** new needs → new functions/files (e.g. `store_tier2_statements`
  beside the untouched `store_fundamentals`).
