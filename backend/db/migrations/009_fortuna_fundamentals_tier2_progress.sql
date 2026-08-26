-- ============================================================================
-- Fortuna — Tier-2 fundamentals archival backfill progress ledger
-- (run in Supabase SQL editor)
--
-- Resumability for the ONE-TIME Tier-2 archival backfill (balance-sheet, cash-flow,
-- corporate-actions, competitors -> f_fundamentals_statements). Separate from the
-- screening ledger (f_fundamentals_fetch_progress) so Tier-2 completion is tracked
-- independently. One row per stock, keyed by ISIN.
--
-- Same conventions as prior progress tables (003-007): lowercase f_, IST timestamps,
-- touch trigger, RLS service-role-only.
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

create table if not exists public.f_fundamentals_tier2_progress (
    isin             text        primary key,
    instrument_key   text        not null,              -- for the competitors endpoint
    status           text        not null default 'pending',  -- pending | done | failed
    attempt_count    int         not null default 0,
    last_attempt_at  timestamp,
    last_success_at  timestamp,
    last_error       text,
    created_at       timestamp   not null default public.now_ist(),
    updated_at       timestamp   not null default public.now_ist()
);

comment on table public.f_fundamentals_tier2_progress is
    'Resumable ledger for the one-time Tier-2 fundamentals archival backfill '
    '(balance-sheet, cash-flow, corporate-actions, competitors -> f_fundamentals_statements). '
    'Separate from the screening ledger. ETFs/dataless fail here; rate-limited stay pending.';

create index if not exists idx_tier2_progress_status
    on public.f_fundamentals_tier2_progress (status);

drop trigger if exists trg_touch_tier2_progress on public.f_fundamentals_tier2_progress;
create trigger trg_touch_tier2_progress
    before update on public.f_fundamentals_tier2_progress
    for each row execute function public.touch_updated_at_ist();

alter table public.f_fundamentals_tier2_progress enable row level security;
