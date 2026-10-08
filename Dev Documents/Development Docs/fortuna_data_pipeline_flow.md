# Fortuna — Data Pipeline Flow & Algorithms

**Scope:** how market data is fetched and stored — OHLCV (price history) and Fundamentals
(company financials, Tier‑1 screening + Tier‑2 archive). Covers the call trees (which
function calls which), the step‑by‑step algorithms, every real file/function/table name,
and the rate‑limit handling that shapes the whole thing.

_Last updated: 2026‑10‑08 (refresh after a long gap; Nifty 50 intraday pipeline §2.8; data verification — audit, window repair, probe, reader rules §2.9; indicator‑phase decisions §2.10). Earlier: 2026‑09‑06 (concurrency for refresh runtime; domain-aware fetch cooldown; jitter on retry backoff; file-logging gap fixed across all runners; confirmed same-calendar-day data gap in Upstox's historical-candle API)._

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

### 2.4 Daily refresh (BUILT — 2026‑09‑04, window logic REDESIGNED 2026‑09‑04, concurrency + cooldown added 2026‑09‑06)
`ohlcv_store.update_instrument(ik, domain, last_success_at, timeframes)` fetches
`from_date=last_success_at → to_date=today`, reads the existing Parquet, **merges +
dedups on (timeframe, ts)**.

**Window = `last_success_at → today`, not a fixed per-unit size.** The original
design used fixed lookback windows (days=10/weeks=21/months=95/minutes=3/hours=5) —
this only self-heals gaps SMALLER than the window; a genuine multi-week outage would
permanently miss everything beyond it, with no built-in remedy. Fixed 2026‑09‑04:
`last_success_at` (read from the ledger via `get_done()`'s `PendingItem`) only ever
advances on a genuine successful fetch — a miss leaves it untouched (see Failure
handling below) — so the window is exactly "everything since we last confirmed
complete," whatever that gap actually is. No buffer beyond `last_success_at` (an
earlier draft added one "in case Upstox revises old candles," ruled out as an
invented concern with no supporting evidence — see Rule #18). `window_days` removed
entirely; dead code.

**Cooldown (added 2026‑09‑06) — gates the FETCH itself, not just the write.** The
no‑op skip below only ever protected the R2 write; `update_instrument()` still made
the full API fetch on every call regardless of how recently the last one succeeded.
Confirmed as the direct cause of two real failures: universe D/W/M refreshed twice 4
minutes apart triggered sustained Cloudflare rate limiting; universe_intraday
refreshed twice 44 SECONDS apart hit guaranteed‑empty fetches (no 5‑minute bar could
possibly exist yet) plus real 429s. Fix: before fetching, compare elapsed time since
`last_success_at` against a **domain‑aware** cooldown
(`_COOLDOWN_MINUTES_BY_DOMAIN` in `ohlcv_store.py`) — if too recent, return
immediately with `StoreResult.skipped=True` and make ZERO API calls.
Deliberately NOT a same‑calendar‑day check (tried and rejected first — would
permanently block a legitimate later‑in‑day attempt, e.g. pre‑market then
post‑close, just because an earlier same‑day run already succeeded). Domain‑aware
because D/W/M's finest granularity is a full day (cooldown can be generous) while
intraday's finest bar is 5 minutes: `universe`/`indices` = 15 min
(`_DEFAULT_COOLDOWN_MINUTES`), `universe_intraday` = 5 min, matching its own bar
period as the logical minimum. Both values are unconfirmed‑optimal, same posture as
`MAX_WORKERS` below — tuned by observed behavior, not proven correct. New
`RunSummary.skipped` counter, reported distinctly from `unchanged` (fetched, no
change) and `failed` (fetched, miss).

**No-op skip:** the merged result is compared against the existing stored data
(`combined.equals(existing_sorted)`) *before* writing. If identical — the common case,
since refetching a closed/settled candle inside the window returns the same values —
the R2 write is skipped entirely (`StoreResult.changed=False`, `bytes_written=0`). Only
a genuinely still‑forming bar (today's daily / this week's / this month's) or a real
gap‑fill triggers an actual write. Verified live: a same‑day re‑run on 5 already‑current
indices produced `succeeded: 0, unchanged: 5, data written: 0.00 MB`.

**Cadence: all three Tier‑1 timeframes every run**, decided AGAINST the originally‑
planned calendar branching (no "1w only after Friday, 1mo only after month‑end"). The
lookback windows are small enough that the added API cost of checking W/M daily is
negligible against the 1000/30‑min limit, and it avoids calendar‑edge bugs. The
no‑op skip above is what makes daily‑checking W/M cheap in practice — most days it's a
fetch + compare + skip, not a fetch + write.

**Failure handling:** a refresh miss does **not** call `mark_failed()` — that would
flip the ledger row to `failed` and pull the instrument into the *backfill* runner's
queue (a full‑history re‑fetch), the wrong response to a transient daily miss. A miss
is logged + counted in the run summary; the row (and `last_success_at`) is left
untouched, so the NEXT successful run's window automatically covers everything missed
since, however large that gap is — the fix above generalises self-healing to gaps of
any size, not just ones smaller than a fixed window. Only success calls `mark_done()`
(stamps `last_success_at`) — on every successful check, whether data changed or not,
since it means "confirmed current," not "data changed."

**CONFIRMED (2026‑09‑06): Upstox's historical-candle API does not include the
current calendar day, for ANY unit.** Observed independently 4 times: universe D/W/M
same‑day queries at 16:27, 17:11, 17:53 IST (all well after the 15:30 close) all
returned empty; universe_intraday's 5m/15m/60m did the same 36 minutes after a prior
success (well past its cooldown, so not the cooldown's doing). Matches the very
first backfill in hindsight too — it fetched through the day *before* the day it
ran. Not a bug — every miss here is the harmless kind (no `mark_failed()`, see
above) and self‑heals the next calendar day when "today" becomes a real closed
trading day. A same‑day refresh will always show today's own date as a miss, by
design of the underlying API.

**Orchestration:** separate runner from backfill (`_ohlcv_refresh_runner.py`), not a
`--mode` flag on `_ohlcv_backfill_runner.py` — different ledger lifecycles (backfill:
one‑time‑complete; refresh: recurring, always reopens). Same shape otherwise
(per‑instrument isolation, `RunSummary`), but works `get_done(domain)` — instruments
already `status='done'` (or `intraday_status='done'` for the intraday domain — see
§2.7) — instead of `get_pending()`. Thin callers `refresh_universe_ohlcv.py` /
`refresh_index_ohlcv.py` / `refresh_universe_options_intraday_ohlcv.py` mirror the
backfill callers. Trigger is manual CLI for now; cron (Render/Supabase) wiring
deferred — swaps what invokes the script, not the script itself.

**Concurrency (added 2026‑09‑06) — `ThreadPoolExecutor`, MAX_WORKERS=4.** Real log
timestamps showed the API fetch is ~0.27s/instrument but the R2 read‑merge‑write
(full‑file read + rewrite, object storage can't append in place) is ~2s/instrument
— ~7.5× the fetch cost, and largely independent of how much data actually changed.
This is I/O‑bound work (network + R2 waits, not computation) — threads, not
processes or a full async rewrite. `RunSummary` is aggregated on the MAIN thread
only, from each worker's returned result — never mutated inside a worker thread
(avoids needing the dataclass itself thread‑safe). Confirmed safe to share across
threads before building: boto3 `client` (documented thread‑safe), `httpx.Client`
under supabase‑py (documented thread‑safe), `requests.Session` for Upstox (not
*officially* documented thread‑safe, but safe in this usage — headers set once at
construction, concurrent `.get()` only).

**Worker-count tuning — tested at each step, not guessed:** 10 → Cloudflare edge
rate limiting (`HTTP 429 "Error 1015"`, not just Upstox's own 25/sec/250/min/
1000‑30min limits), had to force‑kill the run. 6 → same wall, worse (680
occurrences before finishing). 5 → recoverable but not clean (53 occurrences, all
retried successfully). 4 → clean first time (0 429s, full 2,641 instruments,
**18m10s vs ~77m sequential — 4.2×**), but NOT clean on a second run minutes later
(55 occurrences) — most likely cumulative pressure from the day's back‑to‑back
testing rather than 4 itself being unsafe; a genuinely cold‑start test is still an
open item. **Settled: `MAX_WORKERS=4`.**

**Jitter on retry backoff** (`upstox_auth_client.request_get()`): concurrent
workers 429'd at the same instant were retrying in lockstep (`1s/2s/4s`, all
workers, all in sync), re‑triggering the same wall. Backoff is now
`base * 2^(attempt-1) * random.uniform(0.5, 1.5)`. Verified against a mock: 4
simultaneously‑429'd workers now retry at 4 visibly different times.

**Logging:** `cli_main()` writes to `logs/ohlcv_refresh_<domain>.log` (overwritten
fresh each run, one file per domain) in addition to console output. Same pattern on
the BACKFILL runner (`logs/ohlcv_backfill_<domain>.log`) and the news job
(`logs/news_fetch.log`) — all three log to the same `logs/` folder. **Gap found +
fixed 2026‑09‑06:** `print_summary()` in all three runners used plain `print()`,
which bypasses the logging system entirely — the FileHandler never captured it,
only the terminal did (stdout always shows `print()` regardless of logging config).
Fixed by converting every `print()` in all three `print_summary()` functions to
`logger.info()`.

**Status (2026‑09‑06):** all refresh scripts (universe D/W/M, indices D/W/M,
universe_intraday, daily news) run clean with concurrency + cooldown in place. Real
multi‑day‑gap self‑heal test deferred to the next calendar day's first run.

**After a long gap (2026‑10‑08, first run in 15+ days) — use the REFRESH scripts, not backfill.**
The window is `last_success_at → today`, so a 15‑ or 30‑day gap is simply a longer window pulled
in one go. Backfill only works on `pending`/`failed` ledger rows, so it would do nothing for
instruments already `done`. Run all four:
```
python -m modules.market_data.upstox.refresh_index_ohlcv
python -m modules.market_data.upstox.refresh_universe_ohlcv
python -m modules.market_data.upstox.refresh_universe_options_intraday_ohlcv
python -m modules.market_data.upstox.fetch_daily_news
```
Notes: intraday copes with a long gap (the engine already splits minute requests into chunks that
fit Upstox's per‑call limits); news cannot be recovered (Upstox returns only the last 7 days, so
anything older than that inside the gap is gone — just run it to start accumulating again);
refresh only touches instruments already `done`, so **new listings** need the instrument catalogue
sync first, then the backfill script once (skips everything done, fetches only the new ones);
expect a longer runtime than the usual "mostly unchanged" runs because nearly every file has real
data to write. **Supabase free tier auto‑pauses after inactivity:** the first attempt failed
with `getaddrinfo failed` (Errno 11001) on the very first Supabase query, before any Upstox call
(nothing fetched or written). Fix = restore the project in the Supabase dashboard, then rerun
(safe to retry).

### 2.5 Status (2026‑08‑26)
Indices: 135 done, 4 failed (BHARATBOND bond indices — Upstox rejects for candles;
since soft-deleted via `is_active=false`, so no longer attempted by any fetch job).
Stocks: 2,638 done, 2 failed (illiquid/new). ~287 MB in R2. Content‑verified
(India VIX, Reliance).

### 2.6 Options-intraday OHLCV (BUILT — 2026‑09‑04)
Same engine/store as D/W/M, extended not forked, for the F&O-eligible subset of the
universe (`is_fno_eligible=True` on `f_universe_instruments`, 208 stocks — NOT the
full 2,296).

```
   fetch_universe_options_intraday_ohlcv.py         refresh_universe_options_intraday_ohlcv.py
      |  DomainConfig(domain="universe_intraday",         |  cli_main("universe_intraday",
      |    catalogue_table="f_universe_instruments",       |    timeframes=INTRADAY_TIMEFRAMES)
      |    timeframes=INTRADAY_TIMEFRAMES,                 |
      |    extra_filter_column="is_fno_eligible",          |
      |    extra_filter_value=True,                        |
      |    backfill_from_date=today-365d)                  |
      v                                                     v
   _ohlcv_backfill_runner.py (extended)               _ohlcv_refresh_runner.py (extended)
      |  DomainConfig gained timeframes /                  |  run_refresh() gained timeframes
      |  extra_filter_* / backfill_from_date               |  param (default TIER1)
      |  (all optional, default = prior behavior)           |
      v                                                     v
   ohlcv_store.backfill_instrument/update_instrument   (same store functions, domain=
      |  domain="universe_intraday" -> new R2 prefix        "universe_intraday")
      v
   R2 bucket: upstox/universe_intraday/<ISIN>.parquet
      (5m/15m/60m stacked via `timeframe` col, same pattern as D/W/M)
```
`INTRADAY_TIMEFRAMES = (("minutes","5"), ("minutes","15"), ("minutes","60"))` in
`_ohlcv_engine.py`, alongside `TIER1_TIMEFRAMES`. Backfill bounded to 1 year back
(not the engine's full since‑2022 default) — indicators need a few hundred bars of
lookback, not years; storage cost is trivial either way (~0.9GB/200 stocks even at
full since‑2022) but a bounded window avoids unnecessary fetch time.

**Status (2026‑09‑04):** full backfill, 208/208 succeeded, 0 failed, **105.93 MB**
written (26,446 rows/instrument — matches the pre‑build estimate of 26,750 closely).
`--limit 5` refresh smoke‑tested post‑backfill; same‑day window correctly produced an
empty result (see §2.4's window redesign) — full multi‑day refresh behavior deferred
to the next calendar day.

### 2.7 Ledger multi-domain tracking (FIXED — 2026‑09‑04)
`f_ohlcv_fetch_progress`'s primary key is `instrument_key` ALONE (unchanged — a
composite‑PK migration was explicitly ruled out). The `universe_intraday` domain
tracks the SAME instrument_keys as `universe` (same 208 stocks, different dataset),
so seeding a second row under a different `domain` value silently no‑op'd on the
upsert (confirmed live: 208 loaded, 0 seeded, 0 pending).

**Fix:** added a second, independent column set — `intraday_status` /
`intraday_attempt_count` / `intraday_last_attempt_at` / `intraday_last_success_at` /
`intraday_last_error` — to the SAME row (Migration 012). `intraday_status` is NULL
for any row never seeded into that domain, which is what lets `get_pending`/
`get_done` scope correctly to the F&O subset without a `domain`‑column filter (these
rows' `domain` column still reads `'universe'`). Every function in
`ohlcv_fetch_progress.py` branches on `domain == 'universe_intraday'` to pick the
right column set. `mark_attempt`/`mark_done`/`mark_failed` now require an explicit
`domain` parameter (previously implicit via the single column set) — updated at all
5 call sites across both runners. Verified against a mock reproduction of the exact
bug before shipping.

### 2.8 Nifty 50 intraday OHLCV (BUILT — 2026‑10‑08)

Index intraday (5m/15m/60m) for **Nifty 50 only** (other indices only if later needed). Needed for
the "direction of the day" signal on Nifty 50 options.

**Upstox facts verified (read‑only spike `test_index_intraday.py`, no R2/Supabase/ledger):**
- Index intraday is on the standard Analytics Token — **free, no Upstox Plus** (Plus only gates
  expired‑instrument history and the enhanced WebSocket tier).
- Nifty 50 returns 75 / 25 / 7 bars per day for 5m / 15m / 60m (first bar 09:15; last bar starts
  15:25 / 15:15 / 15:15).
- **Volume is 0.0 on every candle** (non‑null, never positive) — so the Parquet schema works
  unchanged, but volume indicators (OBV, VWAP) cannot be computed for the index.
- Retention per Upstox's V3 docs: minute and hour candles from **January 2022**; days/weeks/months from
  January 2000. Confirmed for Nifty 50: all three timeframes start **2022‑01‑03**
  (1,800‑day test: 88,393 5m / 29,499 15m / 8,235 60m candles).
- The current day is never included (same as everything else).

**Design — reuse, don't fork (decision 2026‑10‑08).** A second intraday domain (`indices_intraday`)
was proposed first and rejected: the intraday ledger columns are shared and `get_pending` /
`get_done` / `get_counts` deliberately skip the `domain` filter for intraday, so a second domain
would have made the F&O refresh pick up Nifty 50 (209 instead of 208) and write it into the wrong
folder, forcing changes to working code. Chosen instead: Nifty 50 rides on the **existing
`universe_intraday` domain**.

```
   fetch_nifty50_intraday_ohlcv.py      (NEW thin caller, one variable: NIFTY50_INTRADAY_CONFIG)
      |  DomainConfig(domain="universe_intraday",
      |    catalogue_table="f_all_nse_index_instruments",
      |    extra_filter_column="instrument_key", extra_filter_value="NSE_INDEX|Nifty 50",
      |    timeframes=INTRADAY_TIMEFRAMES, backfill_from_date=None (= engine start, Jan 2022),
      |    log_name="Nifty_50_intraday")
      v
   _ohlcv_backfill_runner.cli_main   (existing; log_name field added)
      v
   ohlcv_store   (existing; _object_key routes by instrument_key segment)
      v
   R2: upstox/nse_indexes_intraday/Nifty_50.parquet    (stocks stay in upstox/universe_intraday/)
```
- **Ledger:** the Nifty 50 row already exists with `domain='indices'`; seeding sets
  `intraday_status='pending'` on it. No SQL migration, no change to `ohlcv_fetch_progress.py`.
- **Refresh:** `refresh_universe_options_intraday_ohlcv` needed **no change** — it reads every row with
  `intraday_status='done'`, so it now covers 209 instruments (208 F&O stocks + Nifty 50) and finds the
  file via the same `_object_key`. Same 5‑minute intraday cooldown.
- **Edits to existing files (two small):** `ohlcv_store.py` — `_INDEX_INTRADAY_PREFIX =
  "upstox/nse_indexes_intraday"` and 4 lines in `_object_key` (domain `universe_intraday` + key
  starting `NSE_INDEX|` → that folder); `_ohlcv_backfill_runner.py` — optional
  `DomainConfig.log_name` (default `None` = domain name, as before) used by `cli_main` for the log
  file name. Verified with 14 checks against stubbed copies of the real files before shipping; F&O
  stock and D/W/M paths unchanged.
- **Log:** `logs/ohlcv_backfill_Nifty_50_intraday.log` (future indices follow the same
  `<Index_Name>_intraday` pattern). The refresh log stays one shared file.

**Status (2026‑10‑08):** first run was a 1‑year backfill (2025‑10‑08 .. 2026‑10‑07, 26,339 rows,
~630 KB, ledger 209 done / 0 failed). Then extended to full history (`backfill_from_date=None`);
the ledger row was reset (`update public.f_ohlcv_fetch_progress set intraday_status='pending'
where instrument_key='NSE_INDEX|Nifty 50'`) and the backfill re‑run — **~126,000 rows, ~3 MB**.
Gotcha: the first re‑run did not replace the file (R2 still showed 645 kB = decimal kB of the
original 630.4 KiB) because the ledger row was not yet `pending` ("0 pending", nothing written);
after deleting the file and marking `pending` again the full file appeared. To check a backfill,
read the log's "Backfilling N pending" and "Wrote …" lines, not the R2 listing.

### 2.8b Refresh‑path review (2026‑10‑08, code review only, nothing changed)
Ran the real `update_instrument` on a real Reliance Parquet with only the Upstox fetch and R2
faked, for a 15‑day gap: new daily/weekly rows added, still‑forming week/month refreshed, no
duplicates, order kept, old rows untouched; a re‑run with nothing new skipped the write. The
refresh runner is correct on cooldown skips (`_refresh_one` returns before `mark_done`, so a
skip never advances `last_success_at`). **One real finding, deferred:** `_results_to_df` silently
drops any timeframe whose fetch failed (warning only) and `update_instrument` still returns ok,
so a weekly 429 after retries would leave a hole that the next window starts after.
Unconfirmed in real data (the audit showed no out‑of‑step files). Proposed fix (not applied):
return not‑ok without writing when a requested timeframe fails with a real error; ~5 lines in the
store. Interim check: search refresh logs for `not ok, skipping` lines mentioning HTTP 429 /
"request failed" ("no candles in response" is normal).

### 2.9 Data verification — audit, window repair, probe (BUILT — 2026‑10‑08)

Done before starting the indicator phase, so indicators can be computed on data we trust.

**Files** (all in `modules/market_data/upstox/`):
| File | What it does |
|---|---|
| `audit_ohlcv_data.py` | READ‑ONLY audit of the 4 OHLCV pipelines (indices daily, universe daily, F&O‑stock intraday, Nifty 50 intraday): ledger vs R2, structure, gaps vs the Nifty 50 calendar, staleness, price jumps, weekly/monthly rollups vs daily, intraday vs daily, special sessions. Report only. |
| `repair_ohlcv_window.py` | ONE‑OFF repair. Re‑fetches a recent D/W/M window and merges it into R2 via `update_instrument()`. Ledger untouched. Used to fill the 2026‑08‑24 daily hole. |
| `inspect_weekly_bar.py` | READ‑ONLY probe: compares a stored weekly bar (H/L/volume) with the daily bars of that week. Tells a genuine no‑trade day from a day the source is missing. |

**Run reference** (from `backend/`):
```
python -m modules.market_data.upstox.audit_ohlcv_data                 # Nifty 50 + watchlist (~1.5 min)
python -m modules.market_data.upstox.audit_ohlcv_data --scope all     # everything (~7 min)
python -m modules.market_data.upstox.repair_ohlcv_window --since 2026-08-17 --scope all [--dry-run] [--limit N]
python -m modules.market_data.upstox.inspect_weekly_bar --keys "NSE_EQ|INE..." --week-start 2026-08-24
```
Outputs: `logs/data_audit.log`, `logs/data_audit_summary.txt` (both overwritten per run) and
`logs/data_audit_findings_<ts>.csv` (timestamped). Repair log: `logs/ohlcv_repair_window.log`.

**Findings and outcome (2026‑10‑08)**
- Nifty 50 + the 208 F&O watchlist stocks: daily/intraday current (lag 0), no errors in the intraday set.
- One market‑wide hole: the 2026‑08‑24 daily bar was missing for every instrument (the weekly bar had it).
  Likely at the seam between the initial backfill and the first refresh. Repaired for 2,415 of 2,431 active
  instruments (7 unchanged, 9 no‑candle failures); the audit rerun confirms Nifty 50 and all watchlist stocks are clean.
- About 340 files (337 `INF…` ETFs/funds, 3 stocks) still lack 2026‑08‑24. Two causes: a genuine no‑trade day
  (weekly volume equals the sum of the dailies) or Upstox's daily endpoint not returning a day the weekly bar has
  (two ETFs checked). Not fixable by re‑fetch; not in the watchlist; left as is.
- 9 catalogue‑active stocks return no recent candles (INE657B01025, INE0NLT01010, INE524T01011, INE24OJ01011,
  INE252A01019, INE670X01014, INE0LZF01013, INE887D01016, INE105I01020): the catalogue `is_active` flag looks stale.
- Old‑history oddities (zero‑price bars, invalid OHLC around 2013‑04, rollup mismatches in early years) only matter
  for long backtests.

**Reader rules — apply whenever reading OHLCV for indicators**
1. Drop bars with non‑positive prices.
2. Drop Nifty 50 intraday bars starting at/after 15:30 (92 days, 2022‑03‑24 .. 2025‑05‑21).
3. Treat special sessions (Muhurat evenings, 2024 Saturday sessions, Sunday budget day) as short days, not gaps.
4. For signals use the official daily candle once published, not the last intraday close (they differ by up to ~4.5%).

**Known conventions**
- Weekly bars are dated the Monday of the week; monthly bars the 1st of the month.
- Upstox never returns the current day's candle; index volume is always 0.
- Upstox daily candles are NOT adjusted for demergers/splits/bonuses.

**Open items**
- Corporate‑action adjustment approach (Tata Motors 2025‑10‑14 and Siemens 2025‑04‑07 are demergers; check PB Fintech
  INE417T01026 2026‑09‑24 −36% on chart) — needed before EMAs on affected stocks.
- Deferred: partial‑timeframe failure in `ohlcv_store._results_to_df` (the audit shows no out‑of‑step files).
- Optional: make the audit skip a "missing day" when weekly volume equals the daily sum (removes the ETF noise).
- Catalogue `is_active` flag is stale for the 9 stocks above.

### 2.10 Indicator phase — decisions so far (2026‑10‑08, nothing built yet)
- **Upstox does not provide computed indicators** (RSI/MACD/EMA/Stochastic/VWAP/S&R are not in its
  market‑data categories) — we calculate them ourselves from OHLCV.
- **EMAs 200/100/50/26/13/5 on the DAILY timeframe only.** Purpose: tell Ash where price stands and when
  an uptrend/downtrend changes — **cross‑above and cross‑below for Nifty 50** (direction of the day for
  options buying), **cross‑above only for stocks** (swing trading), checked each day.
- Also wanted: support/resistance, RSI, Stochastic RSI, MACD. **Later:** volume/volatility/VWAP, then
  options data (OI, IV, contracts).
- **Timeframes in scope:** 1M, 1W, 1D, 60m, 15m, 5m. **4h/2h on hold** (NSE's 09:15–15:30 session gives
  7 hourly bars, which don't divide into four; decide later whether 2h/4h are needed at all).
- **Compute on the fly, leave raw OHLCV as is:** six EMAs took ~0.6 ms on a real 6,632‑bar daily series
  and ~1.2 ms on 18,500 bars, while an R2 read/write is ~2 s per instrument, so stored indicator files
  save almost nothing. Plan: one pure‑function indicator module on top of the OHLCV; revisit stored vs
  on‑the‑fly once the real scanner read pattern is measured.
- **Constraints:** the index's volume is all 0, so VWAP and any volume indicator work for stocks only;
  daily EMAs shown on a lower timeframe must use the previous completed daily bar (no look‑ahead).
- **Sequence agreed:** (1) read‑only data audit (done, §2.9) → (2) indicator spec from Ash (which EMA
  pairs for crosses, S&R method, RSI/StochRSI/MACD params) → (3) build module and check one stock
  against Ash's chart → (4) storage decision. Working in baby steps.

---

## 2A. News pipeline (BUILT — 2026‑09‑04)

Different shape from OHLCV: Upstox's News API (`GET /v2/news`) has no date-range
parameter and only returns articles from the **last 7 days** — perishable,
rolling-window data with no backfill possible. Also different storage: relational
Supabase (`f_news_articles`), not R2 Parquet — the read pattern is point-lookup-by-
stock (scanner flags N stocks → pull each one's articles, newest first), not a bulk
across-all-files scan, and article rows have no natural columnar/numeric shape the
way OHLCV does.

```
   fetch_daily_news.py
      |  _load_all_instrument_keys() -> ALL active instrument_keys across
      |    f_universe_instruments + f_etf_instruments + f_all_nse_index_instruments
      |    (2,782 total, NOT just F&O stocks)
      |  batched into groups of 30 (API's per-call limit) -> 93 batches
      v
   _news_engine.fetch_news_batch_resilient(batch)
      |  tries the batch as-is (fetch_news_batch, itself paginating per-batch
      |    if the combined 30-key result spans >1 page)
      |  on UDAPI1087 (invalid-key) specifically -> bisects the batch in half,
      |    recurses until the single bad key is isolated (~10 extra calls, only
      |    for a genuinely broken batch)
      |  on any OTHER error (network/429/5xx) -> short-circuits immediately,
      |    no wasted bisection (retrying smaller wouldn't fix a rate limit)
      v
   news_store.store_articles()
      |  upsert with ignore_duplicates=True, on_conflict=(instrument_key,
      |    article_link) -- re-running the same 7-day window daily is a no-op
      |    for anything already stored; only genuinely new pairs insert
      v
   Supabase table f_news_articles (id uuid PK, instrument_key, heading, summary,
     article_link, thumbnail_url, published_time, fetched_at)
     indexed on (instrument_key, published_time desc) for the scanner read pattern
```
No ledger, no backfill/refresh split (unlike OHLCV) — a full run is ~93 calls,
finishes in well under a minute, and the 7-day API window self-heals any missed
batch on tomorrow's run. Per-batch isolation (try/except) instead of per-instrument.

**Known-bad keys:** the 4 BHARATBOND bond indices (same ones failing OHLCV, see
§2.5) — isolated via the bisection logic above, then fixed at the source
(`is_active=false` in `f_all_nse_index_instruments`), not a hardcoded exclusion list
in this module.

**Status (2026‑09‑04):** full sweep, 92/93 batches clean, 1 batch partial (4 bad
keys isolated and excluded via `is_active=false` since), 0 non-isolatable failures,
398+ articles fetched across the run.

**Not yet built:** live option chain snapshots (15‑min cadence, current+next month
expiry, 208 F&O stocks — response shape confirmed from Upstox docs, `market_data` +
`option_greeks` per strike in ONE call) and expired option historical candles
(endpoint chain confirmed: `expiries → option/contract or future/contract →
historical‑candle`, old v2‑style interval naming; **Get Expiries only covers 6
months of historical expiries**, not a deep archive; requires Upstox Plus opt‑in,
₹20→₹30/trade, confirmed via `UDAPI1149`).

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
| `upstox_auth_client.py` | `request_get()` — authed Upstox calls + 429/5xx retry with jitter (added 2026-09-06, prevents concurrent workers retrying in lockstep) |
| `_ohlcv_engine.py` | OHLCV fetch core: `fetch_candles`, `fetch_full_history`, `fetch_all_timeframes` |
| `ohlcv_store.py` | Parquet↔R2: `backfill_instrument`, `update_instrument` (no‑op write skip via `StoreResult.changed`; domain-aware fetch cooldown via `StoreResult.skipped` + `_COOLDOWN_MINUTES_BY_DOMAIN`, added 2026-09-06), `read_candles`, `_write_df`; `_object_key` routes `universe_intraday` + `NSE_INDEX|…` keys to `upstox/nse_indexes_intraday/` (added 2026-10-08) |
| `ohlcv_fetch_progress.py` | OHLCV ledger: `seed_instruments`, `get_pending`, `get_done`, `mark_attempt/done/failed` (all require `domain` now — branch on `intraday_status` column set vs `status`), `get_counts(domain=)` |
| `_ohlcv_backfill_runner.py` | shared OHLCV backfill orchestration: `run_backfill(cfg)`, `cli_main(cfg)`, `DomainConfig` (carries `timeframes`/`extra_filter_*`/`backfill_from_date`, all optional). `ThreadPoolExecutor(MAX_WORKERS=4)` added 2026-09-06 — main-thread-only `RunSummary` aggregation; optional `DomainConfig.log_name` = log file stem (added 2026-10-08) |
| `_ohlcv_refresh_runner.py` | shared OHLCV daily‑refresh orchestration: `run_refresh(domain, timeframes=)`, `cli_main(domain, timeframes=)` — separate from backfill runner (different ledger lifecycle). Same `ThreadPoolExecutor(MAX_WORKERS=4)` + `RunSummary.skipped` (cooldown outcome) added 2026-09-06 |
| `fetch_index_ohlcv.py` | thin backfill caller — `INDEX_CONFIG` (domain=indices) |
| `fetch_universe_ohlcv.py` | thin backfill caller — `UNIVERSE_CONFIG` (domain=universe) |
| `fetch_nifty50_intraday_ohlcv.py` | thin backfill caller — Nifty 50 intraday, `NIFTY50_INTRADAY_CONFIG` on the existing `universe_intraday` domain, full history from Jan 2022, own log name (§2.8) |
| `test_index_intraday.py` | read‑only spike: fetches an index's 5m/15m/60m through the engine and prints coverage / bars per day / volume (no R2, no Supabase, no ledger); `--days N`, `--keys …` (§2.8) |
| `fetch_universe_options_intraday_ohlcv.py` | thin backfill caller — F&O-filtered, `INTRADAY_TIMEFRAMES`, 1yr bound (domain=universe_intraday) |
| `refresh_index_ohlcv.py` | thin daily‑refresh caller — domain=indices |
| `refresh_universe_ohlcv.py` | thin daily‑refresh caller — domain=universe |
| `refresh_universe_options_intraday_ohlcv.py` | thin daily‑refresh caller — domain=universe_intraday, `INTRADAY_TIMEFRAMES` |
| `_news_engine.py` | News fetch core: `fetch_news_batch`, `fetch_news_batch_resilient` (bisection on bad keys) |
| `news_store.py` | News persistence: `store_articles` (dedup-upsert) |
| `fetch_daily_news.py` | News orchestrator — all 2,782 instruments, 93 batches, no ledger |
| `audit_ohlcv_data.py` | read‑only OHLCV data audit (§2.9) |
| `repair_ohlcv_window.py` | one‑off D/W/M window repair, merge‑only, ledger untouched (§2.9) |
| `inspect_weekly_bar.py` | read‑only weekly‑bar vs daily‑bars probe (§2.9) |
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
| `upstox/indices/<slug>.parquet` | per‑index OHLCV (1d/1w/1mo) |
| `upstox/universe_intraday/<ISIN>.parquet` | per‑stock intraday (5m/15m/60m stacked), 208 F&O stocks |
| `upstox/nse_indexes_intraday/<slug>.parquet` | index intraday (5m/15m/60m); Nifty 50 only for now → `Nifty_50.parquet` (§2.8) |

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

# Nifty 50 intraday (§2.8) — backfill; the existing intraday refresh then covers it
python -m modules.market_data.upstox.fetch_nifty50_intraday_ohlcv
python -m modules.market_data.upstox.test_index_intraday [--days N] [--keys "NSE_INDEX|Nifty 50" ...]   # read-only spike

# Data verification (read-only audit) and one-off repair (§2.9)
python -m modules.market_data.upstox.audit_ohlcv_data [--scope all]
python -m modules.market_data.upstox.repair_ohlcv_window --since 2026-08-17 --scope all [--dry-run] [--limit N]
python -m modules.market_data.upstox.inspect_weekly_bar --keys "NSE_EQ|INE..." --week-start 2026-08-24
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
