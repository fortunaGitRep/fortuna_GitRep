"""
Read side of the expired Nifty contracts archive in R2 (written by fetch_expired_nifty_options).
No Upstox calls. Files read once per process are kept in memory (per-run cache).

  stored_expiries(part)        -> sorted expiry dates stored for 'band' / 'rest' / 'futures' / 'greeks'
  read_part(part, expiry)      -> DataFrame (empty if not stored)
  to_bars(df, minutes)         -> per-contract OHLC + volume + OI at 1/5/15/... minutes
                                  (open first, high max, low min, close last, volume sum,
                                   OI last = at bar close; bars labelled by start time)
"""

from __future__ import annotations

import io
from datetime import date
from functools import lru_cache

import pandas as pd

from db.r2_client import get_r2, get_r2_settings
from modules.market_data.upstox.fetch_expired_nifty_options import MIN_STORED_BYTES, PARTS

GREEKS_PREFIX = "upstox/nifty_options_greeks/1m"     # computed IV/Greeks per band contract per minute
PREFIXES = {**{k: v["prefix"] for k, v in PARTS.items()}, "greeks": GREEKS_PREFIX}


@lru_cache(maxsize=1)
def _client():
    return get_r2(), get_r2_settings().bucket


@lru_cache(maxsize=None)
def stored_expiries(part: str) -> tuple[date, ...]:
    r2, bucket = _client()
    out, token = [], None
    while True:
        kw = {"Bucket": bucket, "Prefix": PREFIXES[part] + "/"}
        if token:
            kw["ContinuationToken"] = token
        resp = r2.list_objects_v2(**kw)
        for o in resp.get("Contents", []):
            if o["Key"].endswith(".parquet") and o.get("Size", 0) >= MIN_STORED_BYTES:
                out.append(date.fromisoformat(o["Key"].rsplit("/", 1)[1][:10]))
        if not resp.get("IsTruncated"):
            return tuple(sorted(out))
        token = resp.get("NextContinuationToken")


@lru_cache(maxsize=64)
def read_part(part: str, expiry: date) -> pd.DataFrame:
    if expiry not in stored_expiries(part):
        return pd.DataFrame()
    r2, bucket = _client()
    body = r2.get_object(Bucket=bucket, Key=f"{PREFIXES[part]}/{expiry.isoformat()}.parquet")["Body"].read()
    df = pd.read_parquet(io.BytesIO(body), engine="pyarrow")
    df["ts"] = pd.to_datetime(df["ts"])
    df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.date
    return df


def to_bars(df: pd.DataFrame, minutes: int) -> pd.DataFrame:
    if df.empty or minutes == 1:
        return df
    g = df.assign(bucket=df["ts"].dt.floor(f"{minutes}min")) \
          .sort_values("ts").groupby(["instrument_key", "bucket"], sort=True)
    out = g.agg(open=("open", "first"), high=("high", "max"), low=("low", "min"), close=("close", "last"),
                volume=("volume", "sum"), oi=("oi", "last"), strike=("strike", "first"),
                option_type=("option_type", "first"), trade_date=("trade_date", "first"))
    return out.reset_index().rename(columns={"bucket": "ts"})
