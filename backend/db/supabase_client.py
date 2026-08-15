"""
db/supabase_client.py

The ONE Supabase connection for the Fortuna backend, shared by every module
that touches the database (market_data today; positions / watchlist / signal
history later). Nothing else should construct its own client.

Uses the SERVICE ROLE key — full DB access, bypasses RLS. This is correct
for a backend-only, single-user trading engine, but it means:
  - This key must NEVER reach the frontend or a commit. Backend .env only.
  - Every table these credentials touch is wide open to this process, so
    authorization is enforced by *what the backend chooses to do*, not by
    the DB. Keep table access behind deliberate store functions
    (e.g. market_data/index_store.py), not ad-hoc queries scattered around.

Design:
  - Lazy singleton. The client is built on first use and reused, not created
    per-call (avoids reconnecting on every query) and not at import time
    (so a missing env var fails at the call site with a clear message,
    rather than crashing the whole server on boot — same lesson as the Dhan
    import-time-token gotcha).
  - Fails loud and clear if env vars are missing — no silent None.

Standards applied: secrets from env (never hardcoded), single
responsibility (connection only, no table logic), separation of concerns
(infra vs feature data-access), defensive env validation, dependency
minimization (only the official supabase client). Deferred: connection
pooling / async client — the supabase-py client is fine synchronous for a
once-a-day pre-market job; revisit if call volume grows (measure first).
"""

from __future__ import annotations

import logging
import os
from typing import Optional

from supabase import create_client, Client

logger = logging.getLogger(__name__)

_ENV_URL = "F_SUPABASE_URL"
_ENV_SERVICE_KEY = "F_SUPABASE_SERVICE_KEY"

# Module-level cache for the lazy singleton.
_client: Optional[Client] = None


def _read_required_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(
            f"Missing required environment variable '{name}'. "
            f"Add it to the backend .env (service-role Supabase credentials)."
        )
    return value


def get_supabase() -> Client:
    """
    Return the shared Supabase service-role client, building it once on
    first call. Raises RuntimeError with a clear message if the required
    env vars are absent — caught at the call site, not at import.
    """
    global _client
    if _client is None:
        url = _read_required_env(_ENV_URL)
        service_key = _read_required_env(_ENV_SERVICE_KEY)
        _client = create_client(url, service_key)
        logger.info("Supabase service-role client initialised.")
    return _client
