"""
modules/market_data/upstox/news_store.py

Store layer for news articles in Supabase (f_news_articles). Owns the write side
only -- the fetch engine (_news_engine.py) gets articles, this persists them.

Storage model:
  - Relational table, not R2 Parquet (see migration 006 docstring for why: the
    read pattern is point-lookup-by-stock, not bulk across-all-files scan).
  - DEDUP VIA UPSERT, not app-level compare-then-skip: unlike OHLCV's
    update_instrument() (which reads existing data back to compare), news relies
    on the DB's own UNIQUE (instrument_key, article_link) constraint with
    ignore_duplicates=True on upsert. Simpler here because there's a natural
    per-row unique key; OHLCV rows don't have one (a candle's identity is the
    (timeframe, ts) pair, but the whole file is rewritten atomically, not
    row-upserted) -- different mechanism because it's genuinely a different
    write pattern, not an inconsistency to reconcile.

Standards applied: single responsibility (persistence only -- no fetching),
idempotent writes (upsert-ignore-conflict, safe to re-run the same batch),
structured logging (no secrets), chunked writes (bounded payload size).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from db.supabase_client import get_supabase
from modules.market_data.upstox._news_engine import NewsArticle

logger = logging.getLogger(__name__)

_TABLE = "f_news_articles"

# Chunk upserts to keep individual requests small -- a single batch's articles
# (30 instruments x up to ~100 articles/page) could theoretically be large.
_UPSERT_CHUNK = 200


@dataclass
class NewsStoreResult:
    """Outcome of storing one set of articles. `ok` is the single flag.
    `rows_sent` is what we attempted to upsert -- NOT a count of genuinely new
    rows, since ignore_duplicates means the DB silently no-ops on conflicts and
    doesn't reliably report how many were actually inserted vs skipped."""
    ok: bool
    rows_sent: int = 0
    error: Optional[str] = None


def store_articles(articles: list[NewsArticle]) -> NewsStoreResult:
    """
    Upsert articles into f_news_articles. Dedup on (instrument_key, article_link)
    via ignore_duplicates=True -- re-running the same fetch (expected daily, since
    the API's 7-day window re-returns mostly-already-stored articles) is a no-op
    for anything already present; only genuinely new (instrument_key, article_link)
    pairs get inserted.

    Empty input is a no-op success, not an error (a batch can legitimately have
    zero fresh articles).
    """
    if not articles:
        return NewsStoreResult(ok=True, rows_sent=0)

    supabase = get_supabase()
    payloads = [{
        "instrument_key": a.instrument_key,
        "heading": a.heading,
        "summary": a.summary,
        "article_link": a.article_link,
        "thumbnail_url": a.thumbnail_url,
        "published_time": a.published_time.isoformat(),
    } for a in articles]

    try:
        for i in range(0, len(payloads), _UPSERT_CHUNK):
            chunk = payloads[i:i + _UPSERT_CHUNK]
            supabase.table(_TABLE).upsert(
                chunk,
                on_conflict="instrument_key,article_link",
                ignore_duplicates=True,
            ).execute()
    except Exception as exc:  # noqa: BLE001 -- surface as a store failure, not a crash
        logger.error("News upsert failed (%d articles): %s", len(payloads), exc)
        return NewsStoreResult(ok=False, rows_sent=0, error=str(exc))

    logger.info("Upserted %d article(s) (existing duplicates silently skipped).",
                len(payloads))
    return NewsStoreResult(ok=True, rows_sent=len(payloads))
