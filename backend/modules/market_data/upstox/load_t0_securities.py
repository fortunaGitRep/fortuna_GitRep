"""
modules/market_data/upstox/load_t0_securities.py

Set the is_t0_eligible flag on f_universe_instruments from NSE's published T+0
(same-day settlement) list.

NSE publishes T+0 eligibility by SYMBOL; our table is ISIN-keyed. So this loader
resolves each symbol -> ISIN via f_universe_instruments.trading_symbol, REPORTS any
symbols that don't match (format mismatches / not in universe), then sets
is_t0_eligible = true on the matched ISINs.

REFRESH SEMANTICS: T+0 membership changes over time (NSE adds/removes). So a run first
RESETS every is_t0_eligible to false, then sets true for the current file's matches —
i.e. the flag always reflects exactly the current list (stocks NSE dropped go back to
false). Idempotent.

VERIFY-FIRST: --dry-run resolves + reports coverage and the unmatched list WITHOUT
writing. Run it first; if coverage looks right, run without --dry-run.

Input CSV columns: symbol, company_name, effective_date (effective_date is ignored here
-- we only set the boolean; NSE's list is the source of truth for membership).

Run:
  verify:  python -m modules.market_data.upstox.load_t0_securities --csv t0_securities_524.csv --dry-run
  set:     python -m modules.market_data.upstox.load_t0_securities --csv t0_securities_524.csv
"""

from __future__ import annotations

import argparse
import csv
import logging

from db.supabase_client import get_supabase

logger = logging.getLogger(__name__)

_UNIVERSE = "f_universe_instruments"


def _load_symbol_to_isin() -> dict[str, str]:
    """Map trading_symbol -> isin from the active universe. Paginated."""
    supabase = get_supabase()
    mapping: dict[str, str] = {}
    PAGE = 1000
    start = 0
    while True:
        resp = (supabase.table(_UNIVERSE)
                .select("isin, trading_symbol")
                .eq("is_active", True)
                .range(start, start + PAGE - 1)
                .execute())
        batch = resp.data or []
        for r in batch:
            sym = (r.get("trading_symbol") or "").strip()
            if sym and r.get("isin"):
                mapping[sym] = r["isin"]
        if len(batch) < PAGE:
            break
        start += PAGE
    logger.info("Loaded %d symbol->isin mappings from %s.", len(mapping), _UNIVERSE)
    return mapping


def _read_csv(path: str) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def run(csv_path: str, dry_run: bool = False) -> None:
    rows = _read_csv(csv_path)
    logger.info("Read %d T+0 rows from %s.", len(rows), csv_path)

    sym_to_isin = _load_symbol_to_isin()

    matched_isins: list[str] = []
    unmatched: list[str] = []
    for r in rows:
        sym = (r.get("symbol") or "").strip()
        isin = sym_to_isin.get(sym)
        if isin:
            matched_isins.append(isin)
        else:
            unmatched.append(sym)

    # --- Report (the verification) ---
    print("\n" + "=" * 60)
    print("T+0 SECURITIES -- SYMBOL -> ISIN MATCH REPORT")
    print("=" * 60)
    print(f"  total in file : {len(rows)}")
    print(f"  matched       : {len(matched_isins)}")
    print(f"  unmatched     : {len(unmatched)}")
    if unmatched:
        print("\n  unmatched symbols (format mismatch or not in active universe):")
        for s in unmatched:
            print(f"    {s}")
        print("\n  (May be symbol-format differences vs Upstox's master, or genuinely")
        print("   not in the active EQ universe. Eyeball before deciding to fix/ignore.)")
    print("=" * 60)

    if dry_run:
        print("\nDRY RUN -- flag NOT changed. Re-run without --dry-run to set is_t0_eligible.\n")
        return

    if not matched_isins:
        print("\nNo matched ISINs -- flag not changed.\n")
        return

    supabase = get_supabase()

    # 1) Reset all to false (so a refresh removes stocks NSE dropped).
    supabase.table(_UNIVERSE).update({"is_t0_eligible": False}).eq(
        "is_t0_eligible", True).execute()

    # 2) Set true for the current matches (chunk the IN-list to keep URLs sane).
    CHUNK = 200
    for i in range(0, len(matched_isins), CHUNK):
        chunk = matched_isins[i:i + CHUNK]
        supabase.table(_UNIVERSE).update({"is_t0_eligible": True}).in_(
            "isin", chunk).execute()

    logger.info("Set is_t0_eligible=true on %d stocks.", len(matched_isins))
    print(f"\nMarked {len(matched_isins)} stocks T+0-eligible in {_UNIVERSE}.\n")


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    parser = argparse.ArgumentParser(description="Set is_t0_eligible flag from NSE's T+0 list.")
    parser.add_argument("--csv", required=True, help="Path to the T+0 CSV (symbol, company_name, effective_date).")
    parser.add_argument("--dry-run", action="store_true", help="Report match coverage without writing.")
    args = parser.parse_args()

    run(args.csv, dry_run=args.dry_run)
