"""
modules/market_data/index_store.py

Read/write layer for the three Fortuna index history tables:
  fortuna_vix_daily   (date + close)
  fortuna_nifty_daily (date + OHLC)
  fortuna_gift_daily  (date + OHLC)

This module owns everything about *how these specific tables are shaped and
accessed*. It imports the shared connection from db/supabase_client — it does
NOT build its own client (separation of concerns: infra vs feature access).

The three tables have different columns (VIX is close-only), so instead of
triplicating read/write code we drive everything off a small TABLE_CONFIG
registry. One set of functions, parameterised by index key.

Standards applied: single responsibility (table access only, no fetch/sync
logic), DRY (one code path for 3 tables via config), idempotent writes
(upsert on trade_date PK — safe to re-run), defensive programming (validate
index key, never trust the row shape), graceful error handling (store ops
return typed results / raise clearly), structured logging without secrets.
Deferred: pagination (bounded by design — we only ever read a fixed rolling
window, never an unbounded scan), caching (measure first).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from typing import Optional

from db.supabase_client import get_supabase

logger = logging.getLogger(__name__)


# --- Table registry --------------------------------------------------------
# One entry per index. `price_columns` is what distinguishes VIX (close only)
# from Nifty/GIFT (full OHLC). Everything downstream reads from this.

@dataclass(frozen=True)
class TableConfig:
    table_name: str
    price_columns: tuple[str, ...]  # columns beyond trade_date


TABLE_CONFIG: dict[str, TableConfig] = {
    "INDIA_VIX":  TableConfig("fortuna_vix_daily",   ("close",)),
    "NIFTY_50":   TableConfig("fortuna_nifty_daily", ("open", "high", "low", "close")),
    "GIFT_NIFTY": TableConfig("fortuna_gift_daily",  ("open", "high", "low", "close")),
}


def _config(index_key: str) -> TableConfig:
    cfg = TABLE_CONFIG.get(index_key)
    if cfg is None:
        raise KeyError(
            f"Unknown index '{index_key}'. Known: {sorted(TABLE_CONFIG)}"
        )
    return cfg


# --- Row shape -------------------------------------------------------------

@dataclass
class DailyBar:
    """
    One row to write. For VIX, only trade_date + close are meaningful; the
    OHLC fields stay None and are ignored when building the VIX payload.
    """
    trade_date: date
    close: float
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None

    def payload_for(self, cfg: TableConfig) -> dict:
        """Build the exact dict to upsert, using only this table's columns."""
        row: dict[str, object] = {"trade_date": self.trade_date.isoformat()}
        for col in cfg.price_columns:
            value = getattr(self, col)
            if value is None:
                raise ValueError(
                    f"Bar for {cfg.table_name} on {self.trade_date} is missing "
                    f"required column '{col}'."
                )
            row[col] = float(value)
        return row


# --- Writes ----------------------------------------------------------------

def upsert_bars(index_key: str, bars: list[DailyBar]) -> int:
    """
    Idempotent bulk upsert on trade_date. Re-running with the same dates
    updates in place rather than duplicating (trade_date is the PK). Returns
    the number of rows sent. Raises on a hard DB failure — caller decides
    whether that's fatal.
    """
    cfg = _config(index_key)
    if not bars:
        logger.info("upsert_bars(%s): nothing to write.", index_key)
        return 0

    rows = [bar.payload_for(cfg) for bar in bars]
    supabase = get_supabase()
    supabase.table(cfg.table_name).upsert(rows, on_conflict="trade_date").execute()
    logger.info("upsert_bars(%s): upserted %d rows into %s.",
                index_key, len(rows), cfg.table_name)
    return len(rows)


# --- Reads -----------------------------------------------------------------

def get_max_trade_date(index_key: str) -> Optional[date]:
    """
    Cheapest possible 'how current are we?' check — one row, most recent
    trade_date. Returns None if the table is empty (i.e. never backfilled).
    """
    cfg = _config(index_key)
    supabase = get_supabase()
    resp = (
        supabase.table(cfg.table_name)
        .select("trade_date")
        .order("trade_date", desc=True)
        .limit(1)
        .execute()
    )
    if not resp.data:
        return None
    return date.fromisoformat(resp.data[0]["trade_date"])


def get_row_count(index_key: str) -> int:
    """Total rows in the table — used to sanity-check contiguity after sync."""
    cfg = _config(index_key)
    supabase = get_supabase()
    resp = (
        supabase.table(cfg.table_name)
        .select("trade_date", count="exact")
        .execute()
    )
    return resp.count or 0


def get_recent_closes(index_key: str, window: int) -> list[float]:
    """
    Last `window` closes, oldest-first. This is the bounded read the VIX
    percentile calc uses — never an unbounded scan. `window` caps the rows.
    """
    if window <= 0:
        raise ValueError("window must be positive")
    cfg = _config(index_key)
    supabase = get_supabase()
    resp = (
        supabase.table(cfg.table_name)
        .select("trade_date, close")
        .order("trade_date", desc=True)
        .limit(window)
        .execute()
    )
    # came back newest-first; return oldest-first for intuitive downstream use
    closes = [float(r["close"]) for r in reversed(resp.data or [])]
    return closes


# --- Connection smoke test -------------------------------------------------

def connection_smoke_test() -> dict:
    """
    Cheap end-to-end check that the client actually reaches Supabase and the
    three tables exist. Returns a small status dict; raises nothing expected
    unless the connection itself is broken.
    """
    result: dict[str, object] = {}
    for index_key, cfg in TABLE_CONFIG.items():
        try:
            count = get_row_count(index_key)
            max_date = get_max_trade_date(index_key)
            result[cfg.table_name] = {
                "reachable": True,
                "row_count": count,
                "max_trade_date": max_date.isoformat() if max_date else None,
            }
        except Exception as exc:  # noqa: BLE001 — smoke test reports, doesn't crash
            logger.error("Smoke test failed for %s: %s", cfg.table_name, exc)
            result[cfg.table_name] = {"reachable": False, "error": str(exc)}
    return result
