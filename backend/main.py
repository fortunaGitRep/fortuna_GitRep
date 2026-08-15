"""
Fortuna backend — FastAPI entrypoint.

This is the minimal starting point: a running server with a health check.
Real endpoints (Inbox, Buy, Exit, Positions, Watchlist) get added under app/
as they're built.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from dhan_client import dhan
from modules.market_data.index_store import connection_smoke_test

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


from dhan_client import dhan

from modules.market_data.nse_calendar import ensure_calendar

@app.get("/market-data/nse-calendar/sync")
async def nse_calendar_sync():
    return ensure_calendar().__dict__


@app.get("/market-data/index-store/smoke-test")
async def index_store_smoke_test():
    return connection_smoke_test()


@app.get("/")
def root():
    return {"status": "Fortuna API is running"}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/dhan/funds")
def get_dhan_funds():
    return dhan.get_fund_limits()
    
# main.py — add alongside the existing /dhan/funds route

from modules.Module_F_Foundation_Gate_Funnel.Module_F_Global_Gate_Funnel.orchestrator import run_stage1_to_4
from modules.Module_F_Foundation_Gate_Funnel.Module_F_Global_Gate_Funnel.schemas import ViXSnapshot, NiftyOHLC
from datetime import date

@app.get("/funnel/global-gate/run")
async def global_gate_smoke_test():
    # Mocked inputs for now — real Dhan-sourced VIX/OHLC once the Data API subscription is active
    vix = ViXSnapshot(level=13.4, percentile=42.0)
    prev_day = NiftyOHLC(trade_date=date(2026, 8, 12), open=24500, high=24610, low=24430, close=24471.70, prev_close=24400)

    result = run_stage1_to_4(
        vix=vix,
        nifty_prev_day=prev_day,
        nifty_today_open=24445.0,
        fii_dii_rolling_trend_strong=False,
        retail_vs_fii_divergence=False,
    )
    return result.model_dump(mode="json")    