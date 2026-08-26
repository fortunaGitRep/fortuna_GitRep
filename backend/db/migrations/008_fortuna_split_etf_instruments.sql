-- ============================================================================
-- Fortuna — split ETFs out of f_universe_instruments into f_etf_instruments
-- (run in Supabase SQL editor, in STAGES — verify between them)
--
-- WHY: ETFs (ISIN prefix 'INF') are a different KIND of instrument from companies.
-- They have no company fundamentals, aren't screening targets, and are used only by a
-- future regime-rotation/exposure layer — separately from stocks. A separate table
-- (like f_all_nse_index_instruments for indices) means every stock query reads pure
-- companies with no per-row is_etf filter, and ETFs are studied on their own when
-- wanted. Same "different kind -> own table" precedent as indices.
--
-- ISIN prefix logic (verified against the catalogue 2026-08-25):
--   INE (2295) = companies       -> stay in f_universe_instruments
--   IN9 (1)    = JAIN DVR shares  -> STAYS (real company w/ fundamentals; DVR class)
--   INF (347)  = ETFs / MF units  -> MOVE to f_etf_instruments
-- So the split key is: INF-prefix moves out; everything else stays.
--
-- SAFETY: staged. Create table + copy first, VERIFY counts (347 moved, source still
-- intact), and only THEN delete the moved rows from the source (Stage 3, run manually
-- after confirming). Never delete before the copy is verified.
-- ============================================================================

-- ---------------------------------------------------------------------------
-- Shared helpers (idempotent).
-- ---------------------------------------------------------------------------
create or replace function public.now_ist()
returns timestamp language sql stable as $$
    select (now() at time zone 'Asia/Kolkata');
$$;

create or replace function public.touch_updated_at_ist()
returns trigger language plpgsql as $$
begin
    new.updated_at = public.now_ist();
    return new;
end;
$$;

-- ===========================================================================
-- STAGE 1 — create f_etf_instruments (same shape as f_universe_instruments)
-- ===========================================================================
create table if not exists public.f_etf_instruments (
    instrument_key    text        primary key,
    trading_symbol    text,
    name              text,
    isin              text,
    exchange          text,
    segment           text,
    instrument_type   text,
    is_fno_eligible   boolean     not null default false,
    is_active         boolean     not null default true,
    created_at        timestamp   not null default public.now_ist(),
    updated_at        timestamp   not null default public.now_ist()
);

comment on table public.f_etf_instruments is
    'NSE ETF / mutual-fund-unit instruments (ISIN prefix INF), split out of '
    'f_universe_instruments. Not screening targets (no company fundamentals); used by '
    'the regime-rotation/exposure layer separately. Same shape as the universe table.';

create index if not exists idx_etf_active on public.f_etf_instruments (is_active);

drop trigger if exists trg_touch_etf on public.f_etf_instruments;
create trigger trg_touch_etf
    before update on public.f_etf_instruments
    for each row execute function public.touch_updated_at_ist();

alter table public.f_etf_instruments enable row level security;

-- ===========================================================================
-- STAGE 2 — COPY the INF-prefix rows into the ETF table (idempotent upsert).
-- Does NOT delete from source yet. Safe to re-run.
-- ===========================================================================
insert into public.f_etf_instruments
    (instrument_key, trading_symbol, name, isin, exchange, segment,
     instrument_type, is_fno_eligible, is_active, created_at, updated_at)
select
    instrument_key, trading_symbol, name, isin, exchange, segment,
    instrument_type, is_fno_eligible, is_active, created_at, updated_at
from public.f_universe_instruments
where isin like 'INF%'
on conflict (instrument_key) do nothing;

-- ---------------------------------------------------------------------------
-- STAGE 2 VERIFY — run these SELECTs and confirm before Stage 3:
--   Expect: etf_count = 347, and universe still has all 2643 (nothing deleted yet).
-- ---------------------------------------------------------------------------
-- select count(*) as etf_count from public.f_etf_instruments;                       -- expect 347
-- select count(*) as universe_total from public.f_universe_instruments;             -- expect 2643 (unchanged)
-- select count(*) as inf_in_universe from public.f_universe_instruments where isin like 'INF%';  -- expect 347 (still there)

-- ===========================================================================
-- STAGE 3 — DELETE the moved ETFs from the source. RUN ONLY AFTER Stage 2 verify.
-- Uncomment and run separately once counts are confirmed.
-- ===========================================================================
-- delete from public.f_universe_instruments where isin like 'INF%';
--
-- STAGE 3 VERIFY:
-- select count(*) as universe_after from public.f_universe_instruments;             -- expect 2296 (2295 INE + 1 IN9)
-- select count(*) as inf_remaining from public.f_universe_instruments where isin like 'INF%';  -- expect 0
