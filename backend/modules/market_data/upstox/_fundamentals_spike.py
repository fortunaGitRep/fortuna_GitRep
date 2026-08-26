"""
modules/market_data/upstox/_fundamentals_spike.py

>>> INCREMENT 3.1: VERIFY-FIRST SPIKE — fetch all 8 fundamentals endpoints for ONE
    stock, print raw JSON. No storage, no tables. Throwaway. <<<

Purpose: SEE the real response shape of each fundamentals endpoint before designing
Postgres tables. Upstox's Company Fundamentals API is new (~May 2026) and its responses
are nested/irregular (objects with value/unit/formatted, arrays of periods, etc.), so we
must observe reality rather than guess the schema. Delete this file after 3.2 designs
the tables.

Endpoints (all keyed by ISIN, base /v2/fundamentals/{ISIN}/...):
  profile, balance-sheet, cash-flow, income-statement, key-ratios,
  share-holdings, corporate-actions, competitors
Some take query params (type=consolidated|standalone, fs=true) — we try consolidated.

Run:  python -m modules.market_data.upstox._fundamentals_spike
"""

from __future__ import annotations

import json
import logging

from modules.market_data.upstox.upstox_auth_client import request_get

logger = logging.getLogger(__name__)

# Reliance — a big, complete company; good for seeing fully-populated responses.
TEST_ISIN = "INE002A01018"

# (label, path-suffix, params) for each of the 8 endpoints.
# type=consolidated is the usual "group" view; a few companies only have standalone,
# which the spike will reveal via an error/empty so we handle it in the real fetcher.
ENDPOINTS = [
    ("PROFILE",           "profile",           None),
    ("KEY_RATIOS",        "key-ratios",        None),
    ("BALANCE_SHEET",     "balance-sheet",     {"type": "consolidated", "fs": "true"}),
    ("CASH_FLOW",         "cash-flow",         {"type": "consolidated", "fs": "true"}),
    ("INCOME_STATEMENT",  "income-statement",  {"type": "consolidated", "fs": "true"}),
    ("SHARE_HOLDINGS",    "share-holdings",    None),
    ("CORPORATE_ACTIONS", "corporate-actions", None),
    ("COMPETITORS",       "competitors",       None),
]


def _fetch_and_print(label: str, suffix: str, params: dict | None) -> None:
    path = f"/v2/fundamentals/{TEST_ISIN}/{suffix}"
    print("\n" + "=" * 70)
    print(f"  {label}   ->  {path}   params={params}")
    print("=" * 70)
    try:
        resp = request_get(path, params=params)
    except Exception as exc:  # noqa: BLE001
        print(f"  REQUEST FAILED: {exc}")
        return

    print(f"  HTTP {resp.status_code}")
    try:
        body = resp.json()
    except ValueError:
        print(f"  (non-JSON body) {resp.text[:500]}")
        return

    # Pretty-print, but truncate very long arrays so the console stays readable
    # while still showing structure.
    pretty = json.dumps(body, indent=2, ensure_ascii=False)
    if len(pretty) > 6000:
        pretty = pretty[:6000] + "\n  ... (truncated for readability) ..."
    print(pretty)


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    logging.basicConfig(level=logging.WARNING,   # quiet; we want the JSON, not logs
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    print("\n" + "#" * 70)
    print(f"# FUNDAMENTALS SPIKE — all 8 endpoints for ISIN {TEST_ISIN} (Reliance)")
    print("#" * 70)

    for label, suffix, params in ENDPOINTS:
        _fetch_and_print(label, suffix, params)

    print("\n" + "#" * 70)
    print("# END. Review each shape above to design the Postgres tables (3.2).")
    print("#" * 70 + "\n")
