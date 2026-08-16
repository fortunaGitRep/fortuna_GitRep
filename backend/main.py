"""
Fortuna backend — FastAPI entrypoint.

This is the minimal starting point: a running server with a health check.
Real endpoints (Inbox, Buy, Exit, Positions, Watchlist) get added under
modules/ as they're built.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from dhan_client import dhan
from modules.market_data.index_store import connection_smoke_test
from modules.market_data.nse_calendar import ensure_calendar
from modules.market_data.sync import backfill_and_verify_all, sync_daily_all
from modules.market_data.vix_regime import evaluate_vix_decision
from modules.Module_F_Foundation_Gate_Funnel.Module_F_Global_Gate_Funnel.orchestrator import (
    run_stage1_to_4,
)

app = FastAPI(title="Fortuna API")

# Allows the React frontend (running on localhost:5173) to call this backend
# during local development. Update allow_origins once deployed to Render.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Health / root ---------------------------------------------------------

@app.get("/")
def root():
    return {"status": "Fortuna API is running"}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/dhan/funds")
def get_dhan_funds():
    return dhan.get_fund_limits()


# --- Market data -----------------------------------------------------------

@app.get("/market-data/index-store/smoke-test")
async def index_store_smoke_test():
    return connection_smoke_test()


@app.get("/market-data/nse-calendar/sync")
async def nse_calendar_sync():
    return ensure_calendar().__dict__


@app.get("/market-data/backfill")
async def market_data_backfill():
    results = backfill_and_verify_all()
    return {k: v.__dict__ for k, v in results.items()}


@app.get("/market-data/sync-daily")
async def market_data_sync_daily():
    results = sync_daily_all()
    return {k: v.__dict__ for k, v in results.items()}


@app.get("/market-data/vix-regime")
async def vix_regime_check():
    return evaluate_vix_decision().__dict__


# --- Foundation funnel -----------------------------------------------------

@app.get("/funnel/global-gate/run")
async def global_gate_run(nifty_today_open: float | None = None):
    # Pre-market: call with no open. After 9:15, pass ?nifty_today_open=<price>
    # to fill in PRE-3 (gap behaviour) and PRE-4 location.
    result = run_stage1_to_4(nifty_today_open=nifty_today_open)
    return result.model_dump(mode="json")