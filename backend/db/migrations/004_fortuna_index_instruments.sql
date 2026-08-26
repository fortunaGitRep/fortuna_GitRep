-- ============================================================================
-- Fortuna Indices — index instrument catalogue (run in Supabase SQL editor)
--
-- The catalogue of all NSE indices (Domains 2 + 3). Every index-OHLCV fetch
-- loops over the rows here. Populated by
-- modules/market_data/upstox/fetch_index_instrument_list.py, which downloads
-- Upstox's NSE instrument JSON and filters to segment = 'NSE_INDEX'.
--
-- Separate from f_universe_instruments (stocks) on purpose: indices have no
-- ISIN, no fundamentals, no F&O-eligibility — a combined table would be
-- half-empty columns per row (the sparse-nullable anti-pattern).
--
-- Design notes:
--   - IDENTITY: instrument_key ('NSE_INDEX|Nifty 50') is the PRIMARY KEY —
--     stable, and the exact value the OHLCV fetch passes to Upstox. Verified
--     2026-08-23: 139 indices, all instrument_type='INDEX'.
--   - NIFTY 50 SPLIT is NOT a column here. Nifty 50 gets its own Parquet file
--     (it will carry intraday + options) and is excluded from the general "other
--     indices" group — but that decision lives in the OHLCV fetch code (a simple
--     match on instrument_key = 'NSE_INDEX|Nifty 50'), keeping this table as pure
--     catalogue data with no Fortuna-specific logic baked in. (Verified there is
--     exactly one such row in the live file.)
--   - NO isin / fundamentals / fno columns — not applicable to indices.
--   - is_active: soft-delete. NSE occasionally retires/merges indices; when one
--     stops appearing in the daily file we set this false rather than DELETE, so
--     any stored history stays intact for backtesting.
--   - WHAT'S IN HERE (heads-up, not filtered — per the capture-everything regime
--     research thesis): besides the real broad/sector indices (Nifty Bank, IT,
--     Auto, Pharma, Metal, PSU Bank, Midcap/Smallcap...), the 139 also include
--     leveraged/inverse synthetics (Nifty50 PR 2x Lev, TR 1x Inv), a USD variant
--     (Nifty50 USD), dividend-point (Nifty50 Div Point), and bond/gilt indices
--     (BHARATBOND-*, Nifty GS *). All stored as-is. instrument_type is uniformly
--     'INDEX' — the file gives no sub-type to separate "tradeable sector index"
--     from "synthetic/bond index"; any such categorisation is a FUTURE, self-
--     defined research decision, not imposed here.
--   - India VIX also appears here (NSE_INDEX|India VIX). Note the deliberate
--     overlap: the Foundation Funnel already sources VIX via Dhan
--     (fortuna_vix_daily); this is a second, independent copy for index/regime
--     research. Intentional, not a bug.
--   - TIMESTAMPS IN IST + RLS service-role-only: same posture as Migration 003.
--     Reuses the shared now_ist() and touch_updated_at_ist() from 003 (defined
--     there; re-created here defensively with create-or-replace so this migration
--     is self-contained if run standalone).
-- ============================================================================

-- ---------------------------------------------------------------------------
-- Shared helpers (idempotent re-create; originally from Migration 003).
-- Safe to run again — create or replace leaves 003's definitions intact.
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
-- f_all_nse_index_instruments — one row per NSE index
-- ---------------------------------------------------------------------------
create table if not exists public.f_all_nse_index_instruments (
    instrument_key   text        primary key,           -- 'NSE_INDEX|Nifty 50' (stable identity)
    trading_symbol   text,                              -- often null/absent for indices
    name             text        not null,              -- 'Nifty 50', 'Nifty Bank', ...
    exchange         text        not null,              -- 'NSE'
    segment          text        not null,              -- 'NSE_INDEX'
    instrument_type  text,                              -- 'INDEX' (uniform as of 2026-08-23)
    is_active        boolean     not null default true, -- false if the index is retired (soft delete)
    created_at       timestamp   not null default public.now_ist(),
    updated_at       timestamp   not null default public.now_ist()
);

comment on table public.f_all_nse_index_instruments is
    'Catalogue of all NSE indices (Domains 2+3). Index-OHLCV fetch loops over this. '
    'Separate from f_universe_instruments (no isin/fundamentals/fno). '
    '~139 indices as of 2026-08-23; captured in full (incl. sector, broad, thematic, '
    'strategy, leveraged/synthetic, bond/gilt) per the regime-research thesis. '
    'The Nifty-50-gets-its-own-file split is handled in the OHLCV fetch code (match on '
    'instrument_key = NSE_INDEX|Nifty 50), not a column here.';

-- Fast lookup of active indices.
create index if not exists idx_index_active
    on public.f_all_nse_index_instruments (is_active);

-- ---------------------------------------------------------------------------
-- updated_at auto-touch trigger (IST)
-- ---------------------------------------------------------------------------
drop trigger if exists trg_touch_index_instruments on public.f_all_nse_index_instruments;
create trigger trg_touch_index_instruments
    before update on public.f_all_nse_index_instruments
    for each row execute function public.touch_updated_at_ist();

-- ---------------------------------------------------------------------------
-- Row Level Security — service role only (single-user backend)
-- ---------------------------------------------------------------------------
alter table public.f_all_nse_index_instruments enable row level security;
-- No anon/authenticated policies => zero access for those roles.
-- Backend connects with service_role key, which bypasses RLS.
