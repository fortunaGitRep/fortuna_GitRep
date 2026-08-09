"""
Fortuna backend — FastAPI entrypoint.

This is the minimal starting point: a running server with a health check.
Real endpoints (Inbox, Buy, Exit, Positions, Watchlist) get added under app/
as they're built.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from dhan_client import dhan

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


@app.get("/")
def root():
    return {"status": "Fortuna API is running"}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/dhan/funds")
def get_dhan_funds():
    return dhan.get_fund_limits()