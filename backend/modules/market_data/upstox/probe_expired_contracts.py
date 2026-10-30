"""
Read-only probe: how much expired Nifty 50 contract data Upstox serves on this account
(Upstox Plus). Test plan TC-DATA-01. Fetches a handful of calls, stores nothing.

What it checks:
  1. Expiries   -- every expired Nifty 50 expiry Upstox lists: earliest, latest, count,
                   and scheduled weekly expiries (Thursday to 28 Aug 2025, Tuesday from
                   2 Sept 2025) missing from the list.
  2. Contracts  -- for the earliest, a middle and the latest expiry: number of contracts,
                   CE/PE split, strike range and step, lot size.
  3. Candles    -- for the same three expiries, the strike nearest the middle of the
                   chain, CE and PE: 5m candles over the expiry week -- bar count, first
                   and last bar, whether OI is present. Plus one daily-candle call.

Run from backend/:
  python -m modules.market_data.upstox.probe_expired_contracts
Output: logs/expired_contracts_probe_logs/probe.log (also on screen) and
        expiries.json (the full expiry list).

Endpoints (Upstox Expired Instruments API, Plus plan):
  /expired-instruments/expiries?instrument_key=
  /expired-instruments/option/contract?instrument_key=&expiry_date=
  /expired-instruments/historical-candle/{key}/{interval}/{to_date}/{from_date}
UDAPI1149 in an error means the token does not carry the Plus plan: generate a fresh
token after switching to Plus.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import quote, urlencode

from modules.market_data.upstox.upstox_auth_client import request_get

NIFTY_KEY = "NSE_INDEX|Nifty 50"
LAST_THU_EXPIRY = date(2025, 8, 28)
FIRST_TUE_EXPIRY = date(2025, 9, 2)
WEEK_BACK_DAYS = 7                       # candle window: expiry - 7 days .. expiry
LOG_DIR = Path("logs") / "expired_contracts_probe_logs"
PATH_PREFIXES = ("/v2", "")              # tried in order; the first that works is kept

logger = logging.getLogger(__name__)
_prefix: str | None = None


class ProbeError(RuntimeError):
    pass


# ----------------------------------------------------------------------------- http
def _body(resp):
    """request_get may return a requests.Response or already-parsed JSON."""
    if hasattr(resp, "json"):
        status = getattr(resp, "status_code", 200)
        try:
            data = resp.json()
        except ValueError:
            raise ProbeError(f"HTTP {status}, body is not JSON: {getattr(resp, 'text', '')[:200]}")
        if status >= 400:
            raise ProbeError(f"HTTP {status}: {json.dumps(data)[:300]}")
        return data
    return resp


def _get(path_and_query: str):
    """GET through the existing Upstox client; finds once whether the base URL has /v2."""
    global _prefix
    prefixes = (_prefix,) if _prefix is not None else PATH_PREFIXES
    errors = []
    for p in prefixes:
        try:
            body = _body(request_get(p + path_and_query))
        except Exception as exc:  # noqa: BLE001 -- probe: record and try the next form
            errors.append(f"'{p}{path_and_query[:60]}...': {exc}")
            continue
        if isinstance(body, dict) and body.get("status") == "error":
            errors.append(f"'{p}...': {json.dumps(body.get('errors', body))[:300]}")
            continue
        if _prefix is None:
            _prefix = p
            logger.info("Path form that works: '%s<path>'", p or "")
        return body.get("data") if isinstance(body, dict) else body
    raise ProbeError(" | ".join(errors))


def get_expiries() -> list[date]:
    data = _get("/expired-instruments/expiries?" + urlencode({"instrument_key": NIFTY_KEY}))
    return sorted(date.fromisoformat(str(x)[:10]) for x in (data or []))


def get_contracts(expiry: date) -> list[dict]:
    q = urlencode({"instrument_key": NIFTY_KEY, "expiry_date": expiry.isoformat()})
    return list(_get("/expired-instruments/option/contract?" + q) or [])


def get_candles(key: str, interval: str, to_date: date, from_date: date) -> list[list]:
    path = (f"/expired-instruments/historical-candle/{quote(key, safe='')}/{interval}/"
            f"{to_date.isoformat()}/{from_date.isoformat()}")
    data = _get(path)
    return list((data or {}).get("candles", [])) if isinstance(data, dict) else list(data or [])


# ----------------------------------------------------------------------------- checks
def scheduled_expiries(first: date, last: date) -> list[date]:
    """Weekly expiry days before holiday shifts: Thursday to 28 Aug 2025, Tuesday after."""
    out, d = [], first + timedelta(days=(3 - first.weekday()) % 7)
    while d <= min(last, LAST_THU_EXPIRY):
        out.append(d)
        d += timedelta(days=7)
    d = max(FIRST_TUE_EXPIRY, first + timedelta(days=(1 - first.weekday()) % 7))
    while d <= last:
        out.append(d)
        d += timedelta(days=7)
    return out


def missing_weeks(expiries: list[date]) -> list[date]:
    """Scheduled expiry weeks with no listed expiry in the same week (holiday shifts allowed)."""
    listed_weeks = {(e - timedelta(days=e.weekday())) for e in expiries}
    return [s for s in scheduled_expiries(expiries[0], expiries[-1])
            if (s - timedelta(days=s.weekday())) not in listed_weeks]


def contract_summary(contracts: list[dict]) -> dict:
    strikes = sorted({float(c.get("strike_price", 0)) for c in contracts})
    steps = sorted({round(b - a, 2) for a, b in zip(strikes, strikes[1:])})
    types = [str(c.get("instrument_type", "")) for c in contracts]
    return {
        "contracts": len(contracts), "CE": types.count("CE"), "PE": types.count("PE"),
        "strike_min": strikes[0] if strikes else None, "strike_max": strikes[-1] if strikes else None,
        "strike_steps": steps[:5], "lot_size": sorted({c.get("lot_size") for c in contracts}),
    }


def middle_pair(contracts: list[dict]) -> tuple[dict | None, dict | None]:
    """CE and PE at the median listed strike (a stand-in for ATM; no spot needed)."""
    strikes = sorted({float(c.get("strike_price", 0)) for c in contracts})
    if not strikes:
        return None, None
    mid = strikes[len(strikes) // 2]
    pick = {c.get("instrument_type"): c for c in contracts if float(c.get("strike_price", 0)) == mid}
    return pick.get("CE"), pick.get("PE")


def candle_summary(candles: list[list]) -> dict:
    if not candles:
        return {"bars": 0}
    rows = sorted(candles, key=lambda r: r[0])
    oi_vals = [r[6] for r in rows if len(r) > 6 and r[6] is not None]
    return {"bars": len(rows), "first": rows[0][0], "last": rows[-1][0],
            "days": len({str(r[0])[:10] for r in rows}),
            "oi_present": bool(oi_vals) and any(v for v in oi_vals),
            "last_close": rows[-1][4]}


# ----------------------------------------------------------------------------- run
def run() -> list[str]:
    out = ["=" * 78, "EXPIRED CONTRACTS PROBE -- Nifty 50 (Upstox Plus)", "=" * 78]
    expiries = get_expiries()
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    (LOG_DIR / "expiries.json").write_text(json.dumps([e.isoformat() for e in expiries], indent=1))
    if not expiries:
        return out + ["No expired expiries returned."]

    gaps = missing_weeks(expiries)
    out += [
        f"expiries listed : {len(expiries)}",
        f"earliest        : {expiries[0]} ({expiries[0]:%a})",
        f"latest          : {expiries[-1]} ({expiries[-1]:%a})",
        f"span            : {(expiries[-1] - expiries[0]).days} days "
        f"(~{(expiries[-1] - expiries[0]).days / 30.4:.1f} months)",
        f"Thursday era    : {sum(e <= LAST_THU_EXPIRY for e in expiries)} expiries   "
        f"Tuesday era: {sum(e >= FIRST_TUE_EXPIRY for e in expiries)}",
        f"missing weeks   : {len(gaps)}" + (f"  {', '.join(map(str, gaps[:20]))}" if gaps else ""),
        "  full list in expiries.json",
        "",
    ]

    for label, exp in (("EARLIEST", expiries[0]), ("MIDDLE", expiries[len(expiries) // 2]),
                       ("LATEST", expiries[-1])):
        out.append(f"--- {label} expiry {exp} ({exp:%a}) " + "-" * 40)
        try:
            contracts = get_contracts(exp)
        except ProbeError as exc:
            out += [f"   contracts: FAILED -- {exc}", ""]
            continue
        s = contract_summary(contracts)
        out.append(f"   contracts {s['contracts']} (CE {s['CE']}, PE {s['PE']}), strikes "
                   f"{s['strike_min']} .. {s['strike_max']}, steps {s['strike_steps']}, lot {s['lot_size']}")
        if contracts:
            c0 = contracts[0]
            out.append(f"   sample fields: {sorted(c0.keys())}")
        for side, c in zip(("CE", "PE"), middle_pair(contracts)):
            if c is None:
                out.append(f"   {side}: none at the middle strike")
                continue
            key = c.get("instrument_key")
            try:
                cs = candle_summary(get_candles(key, "5minute", exp, exp - timedelta(days=WEEK_BACK_DAYS)))
                out.append(f"   {side} {c.get('trading_symbol', key)} 5m: {cs}")
            except ProbeError as exc:
                out.append(f"   {side} {key} 5m: FAILED -- {exc}")
        if label == "EARLIEST":
            ce, _ = middle_pair(contracts)
            if ce is not None:
                try:
                    cs = candle_summary(get_candles(ce["instrument_key"], "day", exp, exp - timedelta(days=120)))
                    out.append(f"   CE daily, 120 days back: {cs}  (first bar = when the contract started trading)")
                except ProbeError as exc:
                    out.append(f"   CE daily: FAILED -- {exc}")
        out.append("")
    return out


def main() -> int:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s",
                        handlers=[logging.StreamHandler(sys.stdout),
                                  logging.FileHandler(LOG_DIR / "probe_run.log", mode="w", encoding="utf-8")])
    try:
        lines = run()
    except ProbeError as exc:
        lines = ["EXPIRED CONTRACTS PROBE FAILED", str(exc),
                 "If you see UDAPI1149: generate a fresh Upstox token after switching to Plus, then rerun."]
    except Exception:
        logger.exception("Probe failed")
        return 1
    text = "\n".join(lines)
    (LOG_DIR / "probe.log").write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
