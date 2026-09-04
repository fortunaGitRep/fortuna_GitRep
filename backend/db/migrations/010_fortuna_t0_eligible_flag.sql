-- ============================================================================
-- Fortuna — add T+0 (same-day settlement) eligibility flag
-- (run in Supabase SQL editor)
--
-- WHAT T+0 IS: NSE's optional same-day settlement cycle (parallel to normal T+1).
-- Buy in the morning -> shares settle to demat the same afternoon; funds back same
-- evening. Benefit is same-day capital velocity. As of 2026, covers the top ~500 stocks
-- by market cap; NSE adds more periodically.
--
-- WHY A FLAG (not a table): T+0 eligibility is an ATTRIBUTE of a stock already in
-- f_universe_instruments — exactly like is_fno_eligible. A boolean answers the only
-- question we ask ("is this stock T+0 today?"). No separate table / join needed.
-- Refreshed by re-running the loader (load_t0_securities.py), which resolves NSE's
-- symbol list -> ISIN and sets this flag.
-- ============================================================================

alter table public.f_universe_instruments
    add column if not exists is_t0_eligible boolean not null default false;

comment on column public.f_universe_instruments.is_t0_eligible is
    'True if the stock is eligible for NSE T+0 (same-day settlement). Set by '
    'load_t0_securities.py from NSE''s published T+0 list. Same kind of eligibility '
    'attribute as is_fno_eligible.';

-- Index so `WHERE is_t0_eligible = true` screens are fast (matches the F&O flag pattern).
create index if not exists idx_universe_t0
    on public.f_universe_instruments (is_t0_eligible)
    where is_t0_eligible = true;
