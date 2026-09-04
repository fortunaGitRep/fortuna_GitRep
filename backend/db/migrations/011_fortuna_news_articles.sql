-- ============================================================================
-- Fortuna News — articles table (run in Supabase SQL editor)
--
-- Stores news articles from Upstox's News API (GET /v2/news), fetched daily for
-- EVERY active instrument across all three catalogues (universe stocks, ETFs,
-- indices — ~2,782 instrument_keys). Upstox's API only returns articles
-- published in the last 7 days (no deeper history available at any point), so
-- this is PERISHABLE data: a missed daily run permanently loses that day's
-- articles once they roll off the API's 7-day window. Running daily without
-- gaps is what builds an archive over time; there is nothing to backfill.
--
-- NOTE: renumber this migration to match whatever the actual next number is in
-- the repo (Ash's fundamentals migrations aren't visible here) — 006 is a
-- placeholder following 005_fortuna_ohlcv_fetch_progress.sql.
--
-- Design notes:
--   - Relational table, NOT R2 Parquet. Read pattern is point-lookup-by-stock
--     (scanner flags N stocks -> pull each one's articles by instrument_key,
--     newest first) — exactly what a B-tree index serves, not a bulk
--     across-all-files scan (which is what OHLCV/Parquet is optimised for).
--   - No dedicated "article id" from Upstox's API, so `article_link` is the
--     only stable unique-ish field. UNIQUE (instrument_key, article_link) is
--     both the dedup key on insert AND deliberately allows the same article to
--     exist under multiple instrument_keys (a market-wide story tagged to
--     several stocks) without collision.
--   - published_time stored as timestamptz, converted from the API's Unix-ms
--     at fetch time. fetched_at is a separate audit column (when WE pulled it,
--     not when the article went live) — never used for display/sort.
--   - instrument_key is NOT a hard FK to any one catalogue table, since a
--     single key can come from universe, ETF, or index catalogues (three
--     different tables) — validated at the application layer against
--     is_active instrument_keys instead.
--   - IST audit timestamps via shared now_ist(); RLS service-role-only. Same
--     posture as prior migrations (idempotent create-or-replace helpers).
-- ============================================================================

create or replace function public.now_ist()
returns timestamp
language sql
stable
as $$
    select (now() at time zone 'Asia/Kolkata');
$$;

-- ---------------------------------------------------------------------------
-- f_news_articles — one row per (instrument, article)
-- ---------------------------------------------------------------------------
create table if not exists public.f_news_articles (
    id               uuid        primary key default gen_random_uuid(),
    instrument_key   text        not null,               -- from universe / etf / index catalogue
    heading          text        not null,
    summary          text,
    article_link     text        not null,
    thumbnail_url    text,
    published_time   timestamptz not null,                -- converted from API's Unix-ms at fetch time
    fetched_at       timestamp   not null default public.now_ist(),  -- audit only, never for display/sort

    constraint uq_news_instrument_article unique (instrument_key, article_link)
);

comment on table public.f_news_articles is
    'News articles from Upstox News API, fetched daily across all active instruments '
    '(universe + ETF + index catalogues). Upstox only serves the last 7 days -- '
    'perishable data, archive only exists if fetched daily without gaps. '
    'Dedup on (instrument_key, article_link) via upsert-ignore-conflict.';

-- Primary read pattern: "give me this stock's articles, newest first."
create index if not exists idx_news_instrument_published
    on public.f_news_articles (instrument_key, published_time desc);

-- Secondary: global recency queries (e.g. "what's the newest N articles overall").
create index if not exists idx_news_published_time
    on public.f_news_articles (published_time desc);

-- ---------------------------------------------------------------------------
-- Row Level Security — service role only (single-user backend)
-- ---------------------------------------------------------------------------
alter table public.f_news_articles enable row level security;
-- No anon/authenticated policies => zero access for those roles.
-- Backend connects with service_role key, which bypasses RLS.
