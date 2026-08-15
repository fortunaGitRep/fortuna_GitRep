-- ============================================================================
-- Fortuna — NSE calendar table (run in Supabase SQL editor)
--
-- One row per date that is NOT a normal trading day, plus clearing holidays.
-- Any date NOT in this table = normal tradeable weekday.
--
--   day_type = 'trading_holiday'   -> market closed, DO NOT trade
--   day_type = 'weekend'           -> Sat/Sun, DO NOT trade
--   day_type = 'clearing_holiday'  -> market OPEN, CAN trade (no settlement)
--
-- Lookup rule (in code):
--   in table as trading_holiday/weekend -> not tradeable
--   in table as clearing_holiday        -> tradeable
--   not in table                        -> tradeable (normal weekday)
--
-- trade_date is PK -> one row per date, no overlap/duplication possible,
-- and the annual upsert is idempotent.
-- ============================================================================

create table if not exists public.fortuna_nse_calendar (
    trade_date   date        primary key,
    day_type     text        not null
                 check (day_type in ('trading_holiday', 'clearing_holiday', 'weekend')),
    description  text,                        -- e.g. "Republic Day"; null for weekends
    year         smallint    not null,
    created_at   timestamptz not null default now(),
    updated_at   timestamptz not null default now()
);

comment on table public.fortuna_nse_calendar is
    'Non-trading dates (trading holidays + weekends) and clearing holidays. Absent date = normal trading day. Sourced from NSE holiday-master API (CM segment) + generated weekends.';

-- reuse the shared updated_at trigger from 001 if present; define-safe here too
create or replace function public.touch_updated_at()
returns trigger as $$
begin
    new.updated_at = now();
    return new;
end;
$$ language plpgsql;

drop trigger if exists trg_touch_nse_calendar on public.fortuna_nse_calendar;
create trigger trg_touch_nse_calendar before update on public.fortuna_nse_calendar
    for each row execute function public.touch_updated_at();

-- Index for "give me this year's calendar" lookups
create index if not exists idx_nse_calendar_year on public.fortuna_nse_calendar (year);

-- Service-role only, same as the index tables
alter table public.fortuna_nse_calendar enable row level security;
