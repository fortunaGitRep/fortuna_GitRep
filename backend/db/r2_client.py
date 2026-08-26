"""
db/r2_client.py

The single place that owns the Cloudflare R2 connection. Every module that reads
or writes bulk Parquet (OHLCV, later fundamentals snapshots) imports the ready
client from here -- it does NOT build its own. Same "infra module owns the
connection, feature modules import it" separation as db/supabase_client.py.

Why R2 (decided 2026-08-23): bulk OHLCV Parquet is read repeatedly for backtesting/
research. Supabase Storage free tier caps egress at 5 GB/month, which repeated reads
would blow through fast. R2 has ZERO egress fees (its whole selling point), 10 GB free
storage, S3-compatible API. So: Supabase Postgres = relational catalogue/fundamentals/
watchlists (queried); R2 = bulk time-series Parquet (read heavily); DuckDB (later) =
query engine over the Parquet.

Design notes / ADR:
  - R2 speaks the S3 API, so we use boto3 (the AWS SDK) pointed at R2's endpoint --
    no R2-specific SDK needed. This also means standard data tooling (pandas, pyarrow,
    duckdb, s3fs) works against it later.
  - Credentials from .env (fail loudly if missing): R2_ACCOUNT_ID, R2_ACCESS_KEY_ID,
    R2_SECRET_ACCESS_KEY, R2_BUCKET, R2_ENDPOINT.
  - region_name='auto' is required for R2 (it's not AWS-region-based).
  - Client is a module-level singleton (built once, reused) for connection reuse.
  - IMPORTANT signature/addressing: R2 needs path-style addressing (bucket in the
    path, not as a subdomain) and the s3v4 signature -- set via botocore Config so
    boto3 talks to R2 correctly rather than assuming AWS conventions.

Standards applied: single responsibility (owns the R2 connection only), fail-loud on
missing config, structured logging (never logs secrets), stdlib + boto3 + python-dotenv.
Deferred (belongs in the store layer, not here): Parquet (de)serialisation, key naming,
size/usage accounting, the OHLCV read/write logic.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Optional

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

load_dotenv()

# --- Config ----------------------------------------------------------------

_REQUIRED_ENV = (
    "R2_ACCOUNT_ID",
    "R2_ACCESS_KEY_ID",
    "R2_SECRET_ACCESS_KEY",
    "R2_BUCKET",
    "R2_ENDPOINT",
)


class R2ConfigError(RuntimeError):
    """Missing/invalid R2 configuration -- a setup bug to fix, surfaced immediately."""


@dataclass(frozen=True)
class R2Settings:
    account_id: str
    access_key_id: str
    secret_access_key: str
    bucket: str
    endpoint: str


def _load_settings() -> R2Settings:
    """Read R2 config from env, failing loudly (naming the missing var) rather than
    letting an empty credential produce a cryptic auth error later."""
    missing = [k for k in _REQUIRED_ENV if not os.environ.get(k, "").strip()]
    if missing:
        raise R2ConfigError(
            f"Missing required R2 env var(s): {', '.join(missing)}. "
            f"Add them to backend/.env (Cloudflare R2 -> Manage API Tokens for the "
            f"keys; Account ID + endpoint from the R2 overview page)."
        )
    return R2Settings(
        account_id=os.environ["R2_ACCOUNT_ID"].strip(),
        access_key_id=os.environ["R2_ACCESS_KEY_ID"].strip(),
        secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"].strip(),
        bucket=os.environ["R2_BUCKET"].strip(),
        endpoint=os.environ["R2_ENDPOINT"].strip(),
    )


# --- Client singleton ------------------------------------------------------

_client = None            # boto3 S3 client
_settings: Optional[R2Settings] = None


def get_r2_settings() -> R2Settings:
    """Return the loaded R2 settings (bucket name etc.), building once."""
    global _settings
    if _settings is None:
        _settings = _load_settings()
    return _settings


def get_r2():
    """
    Return a process-wide, ready boto3 S3 client configured for Cloudflare R2.
    Feature modules import this and call .put_object/.get_object etc. -- they never
    read credentials themselves. Built lazily and cached.
    """
    global _client
    if _client is not None:
        return _client

    s = get_r2_settings()
    _client = boto3.client(
        "s3",
        endpoint_url=s.endpoint,
        aws_access_key_id=s.access_key_id,
        aws_secret_access_key=s.secret_access_key,
        region_name="auto",                      # required for R2
        config=Config(
            signature_version="s3v4",
            s3={"addressing_style": "path"},     # R2 wants path-style addressing
        ),
    )
    logger.info("R2 client initialised (bucket=%s, endpoint=%s).", s.bucket, s.endpoint)
    return _client


# --- Smoke test ------------------------------------------------------------

@dataclass
class R2SmokeResult:
    ok: bool
    detail: Optional[str] = None


def smoke_test() -> R2SmokeResult:
    """
    Prove R2 auth + bucket access end-to-end: write a tiny object, read it back,
    confirm the bytes match, then delete it. Leaves the bucket clean. Returns
    R2SmokeResult(ok=...) rather than raising for expected failures.
    """
    try:
        client = get_r2()
        s = get_r2_settings()
    except R2ConfigError as exc:
        return R2SmokeResult(ok=False, detail=str(exc))

    key = "_smoke_test/hello.txt"
    payload = b"fortuna r2 smoke test"

    try:
        client.put_object(Bucket=s.bucket, Key=key, Body=payload)
        got = client.get_object(Bucket=s.bucket, Key=key)
        body = got["Body"].read()
        if body != payload:
            return R2SmokeResult(ok=False, detail="round-trip mismatch (read != wrote)")
        client.delete_object(Bucket=s.bucket, Key=key)
    except (BotoCoreError, ClientError) as exc:
        # Common causes: wrong keys (403 SignatureDoesNotMatch), wrong bucket name
        # (404 NoSuchBucket), wrong endpoint. The message says which.
        return R2SmokeResult(ok=False, detail=f"R2 op failed: {exc}")

    logger.info("R2 smoke test passed (write/read/delete round-trip OK on %s).", s.bucket)
    return R2SmokeResult(ok=True, detail=f"authenticated; bucket '{s.bucket}' read+write OK")


if __name__ == "__main__":
    #   python -m db.r2_client
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    result = smoke_test()
    if result.ok:
        print(f"PASS -- {result.detail}")
    else:
        print(f"FAIL -- {result.detail}")
        raise SystemExit(1)
