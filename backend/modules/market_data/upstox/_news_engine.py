"""
modules/market_data/upstox/_news_engine.py

Shared News fetch core. Given a batch of up to 30 instrument_keys, calls Upstox's
News API (GET /v2/news, category=instrument_keys), parses the response, and returns
normalised articles keyed by instrument_key. Knows NOTHING about storage or which
catalogue (universe/ETF/index) the keys came from — the orchestrator layers that on.

API CONTRACT (Upstox News API, confirmed against the live docs):
  - category=instrument_keys, instrument_keys=<comma-separated>, MAX 30 KEYS PER CALL.
  - Only returns articles published in the last 7 DAYS. No date-range parameter,
    no article id, no way to ask for "since X" -- perishable, rolling-window data.
  - Response: {"data": {instrument_key: [{heading, summary, thumbnail, article_link,
    published_time (Unix ms)}, ...]}, "metadata": {"page": {page_number, page_size,
    total_records, total_pages}}}.
  - Pagination (page_number/page_size, 1-100 each) is on the RESPONSE, not
    documented as per-instrument-key -- ambiguous whether it paginates each key's
    article list or the combined 30-key result set. Treated defensively here:
    fetch_news_batch() loops pages for a batch until total_pages is exhausted,
    rather than assuming page 1 always has everything. Costs nothing extra on a
    quiet day (1 page) -- only adds calls when a batch actually has more.

Standards applied: single responsibility (fetch+parse only), defensive parsing
(skip malformed articles, don't abort the batch), graceful errors (ok flag, no
raise for expected failures), structured logging (no secrets).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlencode

from modules.market_data.upstox.upstox_auth_client import request_get

logger = logging.getLogger(__name__)

_NEWS_PATH = "/v2/news"
MAX_KEYS_PER_CALL = 30
_PAGE_SIZE = 100  # API max; keeps page count low for the common (quiet) case


@dataclass
class NewsArticle:
    """One news article, already resolved to the instrument it's tagged under."""
    instrument_key: str
    heading: str
    summary: Optional[str]
    article_link: str
    thumbnail_url: Optional[str]
    published_time: datetime  # tz-aware UTC, converted from the API's Unix-ms


@dataclass
class NewsFetchResult:
    """Normalised result for one batch (<=30 instrument_keys) call. `ok` is the
    single flag callers check. articles are flattened across all keys in the batch
    (each article already carries its own instrument_key)."""
    ok: bool
    instrument_keys: list[str]
    articles: list[NewsArticle] = field(default_factory=list)
    pages_fetched: int = 0
    error: Optional[str] = None

    @property
    def count(self) -> int:
        return len(self.articles)


def _parse_articles(raw: dict) -> list[NewsArticle]:
    """Defensively flatten {instrument_key: [article, ...]} into NewsArticle rows.
    A single malformed article is skipped + logged, never kills the whole parse."""
    data = raw.get("data") or {}
    articles: list[NewsArticle] = []
    for instrument_key, items in data.items():
        if not isinstance(items, list):
            continue
        for i, item in enumerate(items):
            try:
                published_ms = item["published_time"]
                articles.append(NewsArticle(
                    instrument_key=instrument_key,
                    heading=item["heading"],
                    summary=item.get("summary"),
                    article_link=item["article_link"],
                    thumbnail_url=item.get("thumbnail"),
                    published_time=datetime.fromtimestamp(published_ms / 1000, tz=timezone.utc),
                ))
            except (KeyError, TypeError, ValueError) as exc:
                logger.warning("Skipping malformed article #%d for %s: %s",
                               i, instrument_key, exc)
                continue
    return articles


def fetch_news_batch(instrument_keys: list[str]) -> NewsFetchResult:
    """
    Fetch news for up to 30 instrument_keys in one logical call (paginated
    internally if the batch's combined result spans multiple pages). Never raises
    for expected failure modes (network, API error, empty) -- returns ok=False
    with a message instead.

    Programmer error (>30 keys, empty list) DOES raise -- that's a bug to fix,
    not a runtime condition to degrade gracefully from.
    """
    if not instrument_keys:
        raise ValueError("instrument_keys must be non-empty")
    if len(instrument_keys) > MAX_KEYS_PER_CALL:
        raise ValueError(f"{len(instrument_keys)} keys exceeds the API's "
                          f"{MAX_KEYS_PER_CALL}-key-per-call limit")

    keys_param = ",".join(instrument_keys)
    all_articles: list[NewsArticle] = []
    page = 1
    total_pages = 1  # updated from the first response

    while page <= total_pages:
        query = urlencode({
            "category": "instrument_keys",
            "instrument_keys": keys_param,
            "page_number": page,
            "page_size": _PAGE_SIZE,
        })
        path = f"{_NEWS_PATH}?{query}"
        try:
            resp = request_get(path)
        except Exception as exc:  # noqa: BLE001 -- request_get already retried transient errors
            logger.error("News fetch failed for batch (%d keys), page %d: %s",
                         len(instrument_keys), page, exc)
            return NewsFetchResult(ok=False, instrument_keys=instrument_keys,
                                   articles=all_articles, pages_fetched=page - 1,
                                   error=f"request failed: {exc}")

        if resp.status_code != 200:
            return NewsFetchResult(ok=False, instrument_keys=instrument_keys,
                                   articles=all_articles, pages_fetched=page - 1,
                                   error=f"HTTP {resp.status_code}: {resp.text[:200]}")

        try:
            body = resp.json()
        except ValueError:
            return NewsFetchResult(ok=False, instrument_keys=instrument_keys,
                                   articles=all_articles, pages_fetched=page - 1,
                                   error="200 but body was not JSON")

        if body.get("status") != "success":
            return NewsFetchResult(ok=False, instrument_keys=instrument_keys,
                                   articles=all_articles, pages_fetched=page - 1,
                                   error=f"status != success: {str(body)[:200]}")

        all_articles.extend(_parse_articles(body))
        total_pages = (body.get("metadata", {}).get("page", {}).get("total_pages") or 1)
        page += 1

    logger.info("Fetched %d article(s) for %d instrument_key(s) across %d page(s).",
                len(all_articles), len(instrument_keys), page - 1)
    return NewsFetchResult(ok=True, instrument_keys=instrument_keys,
                           articles=all_articles, pages_fetched=page - 1)


# --- Resilient fetch: bisect out a bad key instead of losing the whole batch --

def _is_invalid_key_error(error: Optional[str]) -> bool:
    """True for the 'this specific key is malformed/unrecognised' error class
    (observed as UDAPI1087 in practice), where bisecting to isolate the culprit
    actually helps. False for network/429/5xx-shaped errors, where every key in
    the batch is equally fine and bisecting would just repeat the same failure
    at higher cost for no benefit."""
    if not error:
        return False
    return "UDAPI1087" in error or ("HTTP 400" in error and "invalid" in error.lower())


@dataclass
class ResilientFetchResult:
    """Outcome of a bisection-aware batch fetch. `articles` is everything
    successfully retrieved (from this batch or any of its sub-splits).
    `bad_keys` are individually-isolated invalid instrument_keys -- confirmed via
    bisection down to a single key that still fails. `other_errors` are
    non-isolatable failures (network/429/5xx) at whatever granularity they were
    hit -- these are NOT confirmed bad keys, just calls that failed for reasons
    bisecting wouldn't fix."""
    articles: list[NewsArticle] = field(default_factory=list)
    bad_keys: list[str] = field(default_factory=list)
    other_errors: list[tuple[str, str]] = field(default_factory=list)  # (label, error)
    calls_made: int = 0


def fetch_news_batch_resilient(instrument_keys: list[str]) -> ResilientFetchResult:
    """
    Fetch a batch (<=30 keys), and on an invalid-key-class failure, bisect to
    isolate exactly which key(s) are bad instead of losing the whole batch's
    news. Recurses until a single key is confirmed bad (further failure at n=1
    can't be split any smaller -- that key IS the problem). Non-isolatable
    errors (network/429/5xx) short-circuit immediately at whatever granularity
    they're hit, rather than recursing needlessly.

    Cost: 1 call for a clean batch (the common case). Only pays the extra
    ~2*log2(n) calls when a batch is genuinely broken, and only for that one
    batch.
    """
    result = fetch_news_batch(instrument_keys)
    if result.ok:
        return ResilientFetchResult(articles=result.articles, calls_made=result.pages_fetched)

    if not _is_invalid_key_error(result.error):
        label = (instrument_keys[0] if len(instrument_keys) == 1
                 else f"{instrument_keys[0]}..{instrument_keys[-1]}")
        return ResilientFetchResult(other_errors=[(label, result.error or "unknown")],
                                    calls_made=result.pages_fetched)

    if len(instrument_keys) == 1:
        logger.warning("Isolated bad instrument_key via bisection: %s", instrument_keys[0])
        return ResilientFetchResult(bad_keys=list(instrument_keys), calls_made=result.pages_fetched)

    mid = len(instrument_keys) // 2
    left = fetch_news_batch_resilient(instrument_keys[:mid])
    right = fetch_news_batch_resilient(instrument_keys[mid:])
    return ResilientFetchResult(
        articles=left.articles + right.articles,
        bad_keys=left.bad_keys + right.bad_keys,
        other_errors=left.other_errors + right.other_errors,
        calls_made=left.calls_made + right.calls_made,
    )
