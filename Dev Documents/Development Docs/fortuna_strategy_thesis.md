# Fortuna — Strategy Thesis: Cross-Market Regime Rotation

The "why" behind fetching broadly across every market and submarket. This is the
strategic vision that justifies the data architecture; specific strategies get built
and backtested later, per market.

Last updated: 2026-08-26.

---

## Core thesis

Fortuna's job is **cross-market regime detection and capital rotation**: continuously
scan every market and submarket, identify where price is *actually trending / where
money is being made right now*, and rotate capital there — rather than being locked to
one market (e.g. Nifty index options) and sitting idle when that one market is
directionless.

The last ~2 years of a sideways Nifty are the motivating example: if the index gives
no opportunity, the questions Fortuna should answer are:
1. Is the Nifty 50 index itself trending / giving good return? If yes, trade it.
2. If not — are individual stocks making money?
3. If not the broad market — are there stocks that DON'T follow the index (low
   correlation) that are trending independently?
4. Is equity dead but options making money (or vice versa)?
5. Is a particular SECTOR trending (Nifty Auto? Pharma? PSU Bank?)?
6. Is a particular THEME trending (defence, EV, digital, manufacturing)?
7. Is the trend in COMMODITIES right now (gold/silver/oil) rather than equities?
8. Are government bonds/securities the safe place to be (1 of ~10 capital splits)?

Fortuna should look across ALL of these, find where the trend/opportunity is, and
deploy there.

## Learn from history, apply forward

The system isn't about having deep history for its own sake — it's about capturing
ENOUGH history across ENOUGH markets that Fortuna can *recognize a regime when it
recurs* and act on it going forward, for as long as it's run (years/decades — an
investment-horizon tool, not a fixed-length dataset).

Motivating example: during a war/geopolitical shock, FIIs pull capital out of equities
and flee to safety — and gold/silver/oil become the right call. Fortuna should learn
that flight-to-safety pattern from history so that when something *like* it recurs
(in whatever new form), the system recognizes "this looks like risk-off → rotate toward
gold/commodities/bonds" and surfaces it.

## Why this justifies fetching EVERYTHING (the data consequence)

You cannot learn "when equities bleed, did gold/PSU/pharma/FMCG hold up?" unless you
actually captured gold, PSU Bank, pharma, and FMCG history to study. Breadth of data
is what makes cross-regime learning possible. Restricting to a hand-picked subset of
sectors would blind the system to exactly the rotations it's supposed to catch.

Hence the architecture decisions:
- **The full stock universe** (2,296 companies after ETFs were split into their own
  table; not a fixed Nifty 500) — so pattern-mining and the
  "non-index-correlated stocks" watchlist have the full field to discover from.
- **All 139 indices** (not just the famous sectors) — broad, sector, thematic,
  strategy/factor, even bond/gilt indices — so sector/theme rotation and risk-regime
  signals have full coverage.
- **Fundamentals across the whole universe** — so fundamental screening isn't
  pre-biased by a manual watchlist.
- **Capture now while Upstox is free** — treat the historical backfill as a one-time
  capital pull into storage; ongoing cost is just cheap daily appends. If Upstox ever
  turns paid, the exposure is limited to small increments, not a full re-backfill.

## Honest boundary (know the ceiling)

Upstox provides **Indian-market data only**, daily back to ~2000 (intraday to 2022).
So Fortuna can become a comprehensive **Indian** cross-market regime engine (equity,
F&O, all indices, later MCX commodities + bonds) with ~25 years of daily depth — enough
to contain multiple full crisis regimes (2008, 2013 taper, 2020 COVID) to learn from.

It is NOT, via this Upstox pipeline, a source of:
- True global-market tradeable history (US/London/etc. as instruments) — only a few
  global INDEX reference points (GIFT/Dow/S&P/FTSE) as context.
- Multi-century history — data doesn't exist digitally; Upstox starts ~2000.

"Global / very-long-horizon" is a separate, larger data-sourcing problem (different
vendors, paid, patchy) — a long-term aspiration, not something this pipeline delivers.
Naming the ceiling so the architecture isn't built on a false expectation.

## Sequence

Regime detection is the end goal; it's built up market by market:
1. Get the data in (instrument catalogues → OHLCV → fundamentals) — IN PROGRESS.
2. Per-market strategies + backtests (index, stocks, non-correlated stocks, options,
   later commodities/bonds) — each with its own logic, backtested independently.
3. Regime classifier that ties them together — "which market is trending now, rotate
   there" — the capstone, built once the per-market pieces exist and are validated.
