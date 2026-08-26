-- ============================================================================
-- Fortuna Universe — instrument master table (run in Supabase SQL editor)
--
-- The foundation table for Domain 1 (universe stocks). Every downstream
-- fundamentals/OHLCV fetch loops over the rows here. Populated by
-- modules/market_data/upstox/fetch_universe_instrument_list.py, which downloads
-- Upstox's per-exchange instrument JSON (NSE.json.gz), filters to tradable
-- equities, and cross-references the F&O segment to flag F&O-eligible names.
--
-- Design notes:
--   - IDENTITY: instrument_key is the PRIMARY KEY. Upstox explicitly recommends
--     it over exchange_token, which the exchange may REUSE for a different
--     instrument after expiry. instrument_key (e.g. 'NSE_EQ|INE002A01018') is
--     stable for the life of the instrument, so it's the safe join key for
--     F_fundamentals_*, F_fetch_status, and the OHLCV Parquet filenames (which
--     use the ISIN portion after the '|').
--   - trading_symbol is NOT the key: it can change on corporate actions/renames.
--     Stored for human readability and display only, never joined on.
--   - is_fno_eligible: true when this equity's instrument_key appears as the
--     underlying of any NSE_FO derivative in the same instrument file. This is
--     how Watchlist 2 (~208 F&O names) is derived — from the exchange's own
--     segment data, not a hand-maintained list.
--   - is_active: soft-delete flag. When a previously-seen instrument_key stops
--     appearing in Upstox's daily file (delisted/suspended), we set this false
--     rather than DELETE — historical OHLCV/fundamentals for that symbol stay
--     valid for backtesting. Excluded from future fetch loops + watchlists.
--   - EXCHANGE-AGNOSTIC BY DESIGN: exchange + segment columns are stored so the
--     same table serves NSE today and MCX/BSE later (commodities/other markets)
--     without a schema change. Domain 1 filters to exchange='NSE',
--     segment='NSE_EQ' at query time; the table itself imposes no such limit.
--   - Indices are NOT stored here — they go in F_index_instruments (Domains 2+3,
--     Migration 004), a genuinely different shape (no ISIN, no fundamentals,
--     no F&O flag). This table is equities only.
--   - TIMESTAMPS IN IST: created_at/updated_at are stored as IST wall-clock time
--     (timestamp, via now() AT TIME ZONE 'Asia/Kolkata') so an auditor reading a
--     row sees the Indian market time the row landed/changed, not UTC. This
--     mirrors the "pin IST explicitly, never trust the server's local tz"
--     correctness rule already applied in indices.py (a UTC-hosted backend like
--     Render would otherwise display audit times 5h30m behind IST). Market data
--     itself carries its own trade_date/timestamp from the feed; these two
--     columns are purely row-audit metadata.
--   - Row Level Security: single-user Fortuna table. RLS enabled, no anon/authed
--     policies => only the service_role key (which bypasses RLS, used by the
--     backend) can read/write. Same posture as Migration 001.
-- ============================================================================

-- ---------------------------------------------------------------------------
-- Shared IST-wall-clock helper for audit timestamps.
-- Returns the current instant expressed as Asia/Kolkata local time.
-- Marked STABLE (same value within a statement) — it depends only on clock +
-- fixed zone, no table reads.
-- ---------------------------------------------------------------------------
create or replace function public.now_ist()
returns timestamp
language sql
stable
as $$
    select (now() at time zone 'Asia/Kolkata');
$$;

comment on function public.now_ist() is
    'Current time as Asia/Kolkata (IST) wall-clock. Used for audit columns so '
    'timestamps read in Indian market time regardless of server timezone.';

-- ---------------------------------------------------------------------------
-- f_universe_instruments — one row per tradable equity instrument
-- ---------------------------------------------------------------------------
create table if not exists public.f_universe_instruments (
    instrument_key   text        primary key,          -- 'NSE_EQ|INE002A01018' (stable identity)
    trading_symbol   text        not null,             -- 'RELIANCE' (display only, can change)
    name             text,                             -- 'RELIANCE INDUSTRIES LTD'
    isin             text,                             -- 'INE002A01018' (null for non-ISIN instruments)
    exchange         text        not null,             -- 'NSE' (future: 'BSE','MCX')
    segment          text        not null,             -- 'NSE_EQ'
    instrument_type  text,                             -- 'EQ'
    is_fno_eligible  boolean     not null default false,-- true if underlying of any NSE_FO contract
    is_active        boolean     not null default true, -- false when delisted/suspended (soft delete)
    created_at       timestamp   not null default public.now_ist(),
    updated_at       timestamp   not null default public.now_ist()
);

comment on table public.f_universe_instruments is
    'Universe of tradable equities (Domain 1). Foundation table all fundamentals/OHLCV '
    'fetches loop over. Populated from Upstox per-exchange instrument JSON. '
    'Keyed by stable instrument_key; is_fno_eligible derived from NSE_FO segment; '
    'is_active soft-deletes delisted names (history preserved).';

-- Common query filters: active NSE equities, and F&O-eligible subset.
create index if not exists idx_universe_active_segment
    on public.f_universe_instruments (exchange, segment, is_active);

create index if not exists idx_universe_fno
    on public.f_universe_instruments (is_fno_eligible)
    where is_fno_eligible = true;

-- isin lookups (Parquet filename <-> instrument resolution)
create index if not exists idx_universe_isin
    on public.f_universe_instruments (isin);

-- ---------------------------------------------------------------------------
-- updated_at auto-touch trigger (IST). Reuses the shared touch pattern from
-- Migration 001 but writes IST wall-clock to match this table's audit columns.
-- ---------------------------------------------------------------------------
create or replace function public.touch_updated_at_ist()
returns trigger
language plpgsql
as $$
begin
    new.updated_at = public.now_ist();
    return new;
end;
$$;

drop trigger if exists trg_touch_universe_instruments on public.f_universe_instruments;
create trigger trg_touch_universe_instruments
    before update on public.f_universe_instruments
    for each row execute function public.touch_updated_at_ist();

-- ---------------------------------------------------------------------------
-- Row Level Security — lock to service role only (single-user backend)
-- ---------------------------------------------------------------------------
alter table public.f_universe_instruments enable row level security;
-- No anon/authenticated policies => those roles get zero access.
-- Backend connects with service_role key, which bypasses RLS.
