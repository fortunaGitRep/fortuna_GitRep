-- ============================================================================
-- Fortuna Index — daily history tables (run in Supabase SQL editor)
--
-- Three separate tables, one per index (Ash's choice). Each holds exactly
-- what that index is used for downstream in Module_F_Global_Gate_Funnel:
--   - VIX  : percentile calc reads CLOSE only        -> date + close
--   - NIFTY: CPR needs prior-day High/Low/Close      -> full OHLC
--   - GIFT : gap math needs close; OHLC future-proof -> full OHLC
--
-- Design notes:
--   - PRIMARY KEY on trade_date makes daily writes IDEMPOTENT: an upsert
--     (INSERT ... ON CONFLICT (trade_date) DO ...) can never create a
--     duplicate row for a day. Safe to re-run the daily job or the backfill.
--   - trade_date is DATE (not timestamp): these are end-of-day bars, one per
--     trading day, no intraday component.
--   - NUMERIC(12,4) for prices: exact decimal, no float rounding drift on
--     values like 24471.70. 12 total digits / 4 decimal places is ample for
--     NSE index levels (~5 digits) and VIX (~2 digits).
--   - created_at / updated_at for auditability (when did this row land/change).
--   - Row Level Security: these are single-user Fortuna tables. RLS enabled +
--     a service-role-only policy so the anon key can't read/write them; the
--     backend uses the service role key. Adjust if you later add authed reads.
-- ============================================================================

-- ---------------------------------------------------------------------------
-- 1. India VIX — close only (percentile needs nothing else)
-- ---------------------------------------------------------------------------
create table if not exists public.fortuna_vix_daily (
    trade_date  date        primary key,
    close       numeric(12,4) not null,
    created_at  timestamptz not null default now(),
    updated_at  timestamptz not null default now()
);

comment on table public.fortuna_vix_daily is
    'Daily India VIX close. Feeds VIX rolling-percentile in PRE-1. security_id=21, IDX_I.';

-- ---------------------------------------------------------------------------
-- 2. NIFTY 50 — full OHLC (CPR needs prior-day H/L/C)
-- ---------------------------------------------------------------------------
create table if not exists public.fortuna_nifty_daily (
    trade_date  date        primary key,
    open        numeric(12,4) not null,
    high        numeric(12,4) not null,
    low         numeric(12,4) not null,
    close       numeric(12,4) not null,
    created_at  timestamptz not null default now(),
    updated_at  timestamptz not null default now()
);

comment on table public.fortuna_nifty_daily is
    'Daily NIFTY 50 OHLC. Feeds CPR + basis-adjusted gap in Stage 4. security_id=13, IDX_I.';

-- ---------------------------------------------------------------------------
-- 3. GIFT Nifty — full OHLC (gap needs close; OHLC cheap + future-proof)
--    NOTE: GIFT Nifty via Dhan is UNVERIFIED. This table may stay empty if
--    Dhan doesn't actually serve GIFT data; the AI/web_search path remains
--    the fallback source. Table created now so the wiring is ready either way.
-- ---------------------------------------------------------------------------
create table if not exists public.fortuna_gift_daily (
    trade_date  date        primary key,
    open        numeric(12,4) not null,
    high        numeric(12,4) not null,
    low         numeric(12,4) not null,
    close       numeric(12,4) not null,
    created_at  timestamptz not null default now(),
    updated_at  timestamptz not null default now()
);

comment on table public.fortuna_gift_daily is
    'Daily GIFT Nifty OHLC. UNVERIFIED Dhan source; AI/web_search is fallback. security_id=5024, IDX_I.';

-- ---------------------------------------------------------------------------
-- updated_at auto-touch trigger (shared by all three tables)
-- ---------------------------------------------------------------------------
create or replace function public.touch_updated_at()
returns trigger as $$
begin
    new.updated_at = now();
    return new;
end;
$$ language plpgsql;

drop trigger if exists trg_touch_vix on public.fortuna_vix_daily;
create trigger trg_touch_vix before update on public.fortuna_vix_daily
    for each row execute function public.touch_updated_at();

drop trigger if exists trg_touch_nifty on public.fortuna_nifty_daily;
create trigger trg_touch_nifty before update on public.fortuna_nifty_daily
    for each row execute function public.touch_updated_at();

drop trigger if exists trg_touch_gift on public.fortuna_gift_daily;
create trigger trg_touch_gift before update on public.fortuna_gift_daily
    for each row execute function public.touch_updated_at();

-- ---------------------------------------------------------------------------
-- Row Level Security — lock to service role only (single-user backend)
-- ---------------------------------------------------------------------------
alter table public.fortuna_vix_daily   enable row level security;
alter table public.fortuna_nifty_daily enable row level security;
alter table public.fortuna_gift_daily  enable row level security;

-- No policies for anon/authenticated => those roles get zero access.
-- The backend connects with the service_role key, which bypasses RLS.
-- (If you later want authed dashboard reads, add explicit SELECT policies.)
