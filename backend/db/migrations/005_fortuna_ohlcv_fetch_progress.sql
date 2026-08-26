-- ============================================================================
-- Fortuna OHLCV — fetch progress ledger (run in Supabase SQL editor)
--
-- Resumability for OHLCV backfills + daily updates. One row per instrument,
-- recording whether its OHLCV Parquet (all Tier-1 timeframes, stored in R2) has
-- been successfully fetched-and-stored. The bulk backfill/update jobs read this
-- to SKIP already-done instruments and RESUME after an interruption, and to
-- surface which instruments failed (without silently blocking the run).
--
-- Scope: OHLCV ONLY (Ash's choice 2026-08-23). Fundamentals and news get their
-- OWN progress tables later (f_fundamentals_fetch_progress, etc.) so each name is
-- honest and each table shows only its own data type. Hence NO 'dataset' column
-- here — this table IS the OHLCV dataset; instrument_key alone is the key.
--
-- Design notes:
--   - instrument_key is the PRIMARY KEY (matches f_universe_instruments /
--     f_all_nse_index_instruments; stable identity). One row per instrument.
--   - status: 'pending' | 'done' | 'failed'. The bulk job:
--       * queries status != 'done' to get the work list (resume/skip),
--       * marks 'done' + stamps last_success_at on a successful store,
--       * marks 'failed' + records last_error on a failure (attempt_count++).
--     Idempotent: re-running a completed backfill finds everything 'done' and
--     does nothing — same safety property proven on the instrument-catalogue sync.
--   - domain: 'universe' | 'indices' — which catalogue + R2 prefix this instrument
--     belongs to (so the job knows where to fetch/store without a second lookup).
--   - last_success_at drives the daily incremental path: a null value means never
--     backfilled -> do a FULL history fetch; a non-null value means the file exists
--     -> a windowed incremental update suffices.
--   - attempt_count + last_error: a permanently-broken instrument (e.g. a bad
--     symbol) is visible and can be capped/retried rather than looping forever or
--     blocking the whole run.
--   - IST audit timestamps via shared now_ist(); RLS service-role-only. Same
--     posture as migrations 003/004. now_ist()/touch trigger re-created defensively
--     (create-or-replace) so this migration is self-contained.
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

-- ---------------------------------------------------------------------------
-- f_ohlcv_fetch_progress — one row per instrument
-- ---------------------------------------------------------------------------
create table if not exists public.f_ohlcv_fetch_progress (
    instrument_key   text        primary key,            -- matches the catalogue tables
    domain           text        not null,               -- 'universe' | 'indices'
    status           text        not null default 'pending',  -- pending | done | failed
    attempt_count    int         not null default 0,
    last_attempt_at  timestamp,
    last_success_at  timestamp,                           -- null = never backfilled (full fetch)
    last_error       text,                                -- most recent error only
    created_at       timestamp   not null default public.now_ist(),
    updated_at       timestamp   not null default public.now_ist()
);

comment on table public.f_ohlcv_fetch_progress is
    'Resumable OHLCV fetch ledger — one row per instrument. Bulk backfill/update jobs '
    'skip status=done and resume after interruption; failed rows are visible for retry. '
    'last_success_at null => never backfilled (full fetch); non-null => incremental. '
    'OHLCV-only; fundamentals/news get their own progress tables.';

-- Work-list query is "status != done" (+ optionally by domain) -> index it.
create index if not exists idx_ohlcv_progress_status
    on public.f_ohlcv_fetch_progress (status);

create index if not exists idx_ohlcv_progress_domain_status
    on public.f_ohlcv_fetch_progress (domain, status);

-- ---------------------------------------------------------------------------
-- updated_at auto-touch trigger (IST)
-- ---------------------------------------------------------------------------
drop trigger if exists trg_touch_ohlcv_progress on public.f_ohlcv_fetch_progress;
create trigger trg_touch_ohlcv_progress
    before update on public.f_ohlcv_fetch_progress
    for each row execute function public.touch_updated_at_ist();

-- ---------------------------------------------------------------------------
-- Row Level Security — service role only (single-user backend)
-- ---------------------------------------------------------------------------
alter table public.f_ohlcv_fetch_progress enable row level security;
-- No anon/authenticated policies => zero access for those roles.
-- Backend connects with service_role key, which bypasses RLS.
