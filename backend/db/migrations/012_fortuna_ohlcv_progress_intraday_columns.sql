-- ============================================================================
-- Fortuna OHLCV progress ledger — add intraday tracking columns (no PK change)
-- Run in Supabase SQL editor. Renumber to match the actual next migration
-- number in the repo (last confirmed: 011_fortuna_news_articles.sql).
--
-- WHY: f_ohlcv_fetch_progress's primary key is instrument_key ALONE (from when
-- the ledger only ever tracked one domain per stock). The options-intraday
-- domain (universe_intraday) tracks the SAME instrument_keys as the existing
-- 'universe' domain (same 208 F&O-eligible stocks), just for a different
-- dataset (5m/15m/60m candles vs D/W/M). Seeding a second row under
-- domain='universe_intraday' for an instrument_key that already has a
-- domain='universe' row silently no-ops under upsert-ignore-duplicates —
-- confirmed live 2026-09-04 (208 loaded, 0 seeded, 0 pending).
--
-- FIX (deliberately NOT a composite-PK change, per Ash's call 2026-09-04):
-- add a second, independent set of tracking columns for the intraday domain.
-- A stock's single row now carries BOTH the original universe/indices
-- tracking (status/last_success_at/...) AND the intraday tracking
-- (intraday_status/intraday_last_success_at/...) side by side.
--
-- intraday_status is NULLABLE and defaults to NULL, not 'pending' — NULL means
-- "not tracked for intraday at all" (e.g. a non-F&O stock, or an index). Only
-- rows deliberately seeded for the intraday domain get an actual 'pending'
-- value. This is what lets get_pending/get_done scope correctly to the
-- F&O-eligible subset without a domain-column filter (which would look at
-- the wrong value — these rows' `domain` column stays 'universe').
-- ============================================================================

alter table public.f_ohlcv_fetch_progress
    add column if not exists intraday_status         text,  -- NULL | pending | done | failed
    add column if not exists intraday_attempt_count   int  not null default 0,
    add column if not exists intraday_last_attempt_at timestamp,
    add column if not exists intraday_last_success_at timestamp,
    add column if not exists intraday_last_error      text;

comment on column public.f_ohlcv_fetch_progress.intraday_status is
    'Independent completion tracking for the universe_intraday domain (5m/15m/60m '
    'OHLCV), alongside the same row''s existing status column for universe/indices. '
    'NULL = not seeded for intraday (most rows); pending/done/failed once seeded.';

-- Work-list query for intraday is "intraday_status in (pending, failed)" -> index it.
create index if not exists idx_ohlcv_progress_intraday_status
    on public.f_ohlcv_fetch_progress (intraday_status);
