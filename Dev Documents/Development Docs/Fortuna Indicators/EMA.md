# Fortuna — Indicator Spec: EMA (Exponential Moving Average)

**What this doc is:** the single source of truth for how Fortuna calculates and reads EMAs —
the exact formulas, periods, rules and thresholds Fortuna uses. Other books and traders
define EMA signals in different ways; this doc records only what **Fortuna** does. One spec
doc per indicator (RSI, StochRSI, MACD, S&R … follow the same layout).

_Version 1 — 2026‑10‑11. Code: `backend/modules/Module_F_Tech_Indicators_Funnel/trend_indicators/ema.py`._

---

## 1. Scope

| Item | Fortuna's choice |
|---|---|
| Instruments | **Nifty 50 now.** Watchlist / options stocks later — same code, no changes. |
| Timeframe | **Daily (1D) only.** Weekly/monthly technically possible (reader supports them) but not used. Intraday not supported yet. |
| EMA periods | **5, 13, 26, 50, 100, 200** — counted in bars of the timeframe (daily → days). No other lengths. |
| Price source | **Close.** |
| Parity rule | Every value must equal TradingView's. Formulas below are TradingView's own. |

---

## 2. Input data

- Daily candles from R2 (`upstox/indices/Nifty_50.parquet` for Nifty), read through
  `indicator_ohlcv_reader.read_for_indicators()`.
- **Reader rule 1:** bars with a zero or negative open/high/low/close are dropped.
- **Latest bar = the last completed trading day's official close.** Upstox never returns the
  current day, so a refresh during market hours cannot store a half‑formed candle. A run on
  Sunday shows Friday's close.
- Nifty history used: 2000‑01‑03 onward (6,657 daily bars as of 2026‑10‑09).

---

## 3. EMA formula (= TradingView `ta.ema`)

For period **n**:

- α = 2 / (n + 1)
- Bars 1 … n−1 → **blank** (fewer than n closes exist, so no EMA yet — TradingView draws no line there either)
- Bar n → **simple average of the first n closes** (the seed)
- Every later bar → **EMA = α × close + (1 − α) × previous EMA**

| Period | α | Weight on today's close |
|---|---|---|
| 5 | 0.3333 | 33.3% |
| 13 | 0.1429 | 14.3% |
| 26 | 0.0741 | 7.4% |
| 50 | 0.0392 | 3.9% |
| 100 | 0.0198 | 2.0% |
| 200 | 0.00995 | 1.0% |

**Worked example (3‑EMA, closes 100, 110, 120, 100):** blank, blank, 110 (= average of the first 3), then
0.5 × 100 + 0.5 × 110 = **105**.

**Short history:** an instrument with fewer than n bars has no n‑EMA (e.g. a new listing with 150 days
has no 200 EMA) and Fortuna says so instead of showing a number.

---

## 4. Crosses

### 4.1 Rule (= TradingView `ta.crossover` / `ta.crossunder`)
- **Cross above on day t:** A > B on day t **and** A ≤ B on day t−1.
- **Cross below on day t:** A < B on day t **and** A ≥ B on day t−1.
- A equal to B today is **not** a cross. A blank value on either day → **no cross**.

### 4.2 The 12 checks Fortuna watches

| # | A | B | Meaning |
|---|---|---|---|
| 1–6 | Close | 5, 13, 26, 50, 100, 200 EMA | price vs each line |
| 7 | 5 EMA | 13 EMA | stack pair |
| 8 | 13 EMA | 26 EMA | stack pair |
| 9 | 26 EMA | 50 EMA | stack pair |
| 10 | 50 EMA | 100 EMA | stack pair |
| 11 | 100 EMA | 200 EMA | stack pair |
| 12 | 50 EMA | 200 EMA | **golden cross** (above) / **death cross** (below) |

### 4.3 Which directions are used
- **Nifty 50:** cross‑above **and** cross‑below (direction of the day for options buying, calls and puts).
- **Stocks:** cross‑above only (swing buying).
- Both directions are always calculated; the choice above is made by the caller, not the indicator.

---

## 5. Stack and stage (−5 … +5)

**Stack order:** 5 > 13 > 26 > 50 > 100 > 200 (bullish) or the reverse (bearish).

**Stage:** start at the fast end and count how many consecutive pairs are aligned.

| Stage | Condition | Fortuna's reading |
|---|---|---|
| **+5** | 5 > 13 > 26 > 50 > 100 > 200 | strongest uptrend |
| +4 | 5 > 13 > 26 > 50 > 100, 100 not above 200 | |
| +3 | 5 > 13 > 26 > 50, 50 not above 100 | |
| +2 | 5 > 13 > 26, 26 not above 50 | |
| **+1** | 5 > 13 only | weakest uptrend — still wanted for intraday options buying |
| 0 | 5 = 13 | neutral |
| −1 … −5 | mirror image | weakest … strongest downtrend |

- The count stops at the first pair that is not aligned. Example: 5 < 13 but 13 > 26 → **−1**
  (a short‑term dip inside a bigger uptrend — the per‑pair states in §6 show the bigger picture).
- 5 or 13 blank → no stage. A blank EMA further up stops the count (no 200 EMA → at most ±4).

---

## 6. Check states (shown for all 12 checks, every day)

| Field | Definition |
|---|---|
| **Side** | above / below / equal |
| **Days held** | trading days A has stayed on the current side, **cross day = 1**. A cross that holds shows 1, 2, 3 …; one that fails flips back and resets to 1. |
| **Since** | date the current side began (date of the last cross) |
| **Margin** | A − B in points, and (A − B) / B in % |
| **Whole candle clear** | close checks only. Above: the candle's **low** is above the line. Below: the candle's **high** is below the line. Not applicable to EMA‑vs‑EMA pairs (no candle). |

**Example — Nifty, 9 Oct 2026 close 22,520.45:** stage **−5**; close vs 5 EMA: above, held 1 day,
margin **+0.08 pts (+0.000%)**, whole candle clear **no** (a weak cross); 13 vs 26: below since
27 Aug; 26 vs 50: below since 7 Sep; 50 vs 200: below since 16 Mar 2026 (death cross).

---

## 7. Thresholds (strong / weak)

**Current rule: none. Fortuna shows the facts — days held, margin %, whole‑candle clear — and does not
yet label a cross "strong" or "weak".**

Candidate filters from published technical analysis, kept for testing on Nifty's own 26‑year history
before any is adopted:

| Filter | Published example | Status in Fortuna |
|---|---|---|
| Time (hold) | close stays beyond the line 3 days | shown as *days held*; no threshold |
| Extent (margin) | 2% beyond a 50‑day EMA; 3% around the 200‑day (tested on the S&P 500, not Nifty) | shown as *margin %*; no threshold |
| Whole candle | low above the line (uptrend) / high below it (downtrend) | shown as *whole candle clear*; no threshold |
| Volume | cross on clearly higher volume | **not used** — Upstox sends zero volume for indices; revisit for stocks |

---

## 8. Not used / deferred

- Other EMA lengths (9, 20, 21 …), SMA and other moving‑average types.
- Weekly/monthly EMAs, intraday EMAs (needs reader rule 2), 4h/2h timeframes.
- Volume confirmation (see §7).
- **Stocks:** Upstox daily candles are not adjusted for demergers/splits (e.g. Tata Motors 2025‑10‑14,
  Siemens 2025‑04‑07). An adjustment approach is needed before EMAs on affected stocks are trusted.

---

## 9. Code map

| Function (in `ema.py`) | Does |
|---|---|
| `compute_emas(df)` | adds `ema_5 … ema_200` |
| `detect_crosses(df)` | adds `cross_above_<A>_<B>` / `cross_below_<A>_<B>` for the 12 checks (e.g. `cross_above_ema_50_ema_200` = golden cross) |
| `stack_stage(df)` | stage −5 … +5 per day |
| `check_states(df)` | adds `side_`, `held_`, `since_`, `margin_pts_`, `margin_pct_`, `candle_clear_` per check |

All are pure functions (no I/O, nothing instrument‑specific). Full chain on 6,657 bars ≈ 70 ms.
Tests: `trend_indicators/test_ema.py` (43). Reader: `market_data/upstox/indicator_ohlcv_reader.py` (13 tests).

**Manual checks** (from `backend/`):
```
python -m modules.Module_F_Tech_Indicators_Funnel.trend_indicators.ema                 # latest 3 days' EMAs
python -m modules.Module_F_Tech_Indicators_Funnel.trend_indicators.ema --dates 2025-10-01 2026-10-09
python -m modules.Module_F_Tech_Indicators_Funnel.trend_indicators.ema --crosses 15
python -m modules.Module_F_Tech_Indicators_Funnel.trend_indicators.ema --state
```

---

## 10. Verification

- **EMA values:** all six equal TradingView to the paisa on Nifty daily for 11 dates, 2022‑10‑03 … 2026‑10‑09.
- **Crosses:** latest 15 Nifty crosses (25 Aug … 9 Oct 2026) confirmed on Ash's TradingView chart.
- **TradingView tip:** TradingView computes over the history it has loaded. Scroll back a few years before
  reading a 200 EMA, or its value may be slightly off (seen: +0.35 before scrolling back, exact after).

---

## 11. Change log

| Date | Change |
|---|---|
| 2026‑10‑11 | v1 — periods, formula, 12 checks, cross rule, stage, check states, thresholds (none yet), volume deferred. |

**Next for EMA:** snapshot + plain‑English texts (with all 6 EMA values, today and yesterday) → daily
Nifty run + alerts → frontend chart and text panel. Update this doc when any rule changes.
