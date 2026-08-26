"""
modules/market_data/upstox/_bank_income_spike.py  (throwaway)

See a BANK's income-statement structure so we parse bank 'revenue' correctly.
Banks report 'Interest Earned' / 'Total Income', not 'Revenue'. Prints the
full_statement line-item names + the category blocks for SBI, so we know exactly
which line to use as the bank revenue equivalent.

Run:  python -m modules.market_data.upstox._bank_income_spike
Delete after the parser fix.
"""

from __future__ import annotations

import json
import logging

from modules.market_data.upstox.upstox_auth_client import request_get

logging.basicConfig(level=logging.WARNING)

SBI_ISIN = "INE062A01020"

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()

    path = f"/v2/fundamentals/{SBI_ISIN}/income-statement"
    resp = request_get(path, params={"type": "consolidated", "fs": "true"})
    print("HTTP", resp.status_code)
    data = resp.json().get("data", {})

    print("\n=== CATEGORY blocks (income_statement) ===")
    for blk in data.get("income_statement", []):
        cat = blk.get("category")
        hist = blk.get("history", [])
        latest = hist[0] if hist else {}
        print(f"  category={cat!r:20}  latest={latest.get('period')}={latest.get('value')}  change={latest.get('change')}")

    print("\n=== FULL_STATEMENT line-items (particulars) ===")
    for row in data.get("full_statement", []):
        part = row.get("particular")
        hist = row.get("history", [])
        latest = hist[0] if hist else {}
        # print newest 2 values to see the series
        vals = [(h.get("period"), h.get("value")) for h in hist[:4]]
        print(f"  {part!r:32}  {vals}")

    print("\n=== units / meta ===")
    print("units_in:", data.get("units_in"), " time_period:", data.get("time_period"))
