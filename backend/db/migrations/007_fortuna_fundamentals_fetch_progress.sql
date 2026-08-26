-- ============================================================================
-- Fortuna Fundamentals — fetch progress ledger (run in Supabase SQL editor)
--
-- Resumability for the bulk fundamentals fetch. One row per stock (EQ instrument),
-- recording whether its fundamentals (8 endpoints -> 3 tables) have been fetched.
-- The bulk job reads this to SKIP done stocks and RESUME after interruption, and to
-- surface failures (ETFs and dataless names fail here — that failed-list doubles as
-- the ETF/no-fundamentals signal, since the catalogue has no is_etf flag).
--
-- Scope: FUNDAMENTALS only (own table, per the per-data-type pattern — mirrors
-- f_ohlcv_fetch_progress). Keyed by isin (fundamentals are ISIN-addressed).
--
-- Same conventions as migrations 003-006: lowercase f_, IST audit timestamps via
-- now_ist(), touch trigger, RLS service-role-only.
-- ============================================================================

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

create table if not exists public.f_fundamentals_fetch_progress (
    isin             text        primary key,           -- matches f_universe_instruments.isin
    instrument_key   text        not null,              -- needed for the competitors endpoint
    status           text        not null default 'pending',  -- pending | done | failed
    attempt_count    int         not null default 0,
    last_attempt_at  timestamp,
    last_success_at  timestamp,
    last_error       text,                               -- ETFs land here ('no key-ratios...')
    created_at       timestamp   not null default public.now_ist(),
    updated_at       timestamp   not null default public.now_ist()
);

comment on table public.f_fundamentals_fetch_progress is
    'Resumable fundamentals fetch ledger — one row per EQ stock (keyed by ISIN). Bulk job '
    'skips status=done, resumes after interruption, isolates failures. ETFs/dataless names '
    'fail here (no fundamentals) — that failed-list is also the ETF signal (catalogue has '
    'no is_etf flag). Fundamentals-scoped; mirrors f_ohlcv_fetch_progress.';

create index if not exists idx_fund_progress_status
    on public.f_fundamentals_fetch_progress (status);

drop trigger if exists trg_touch_fund_progress on public.f_fundamentals_fetch_progress;
create trigger trg_touch_fund_progress
    before update on public.f_fundamentals_fetch_progress
    for each row execute function public.touch_updated_at_ist();

alter table public.f_fundamentals_fetch_progress enable row level security;
