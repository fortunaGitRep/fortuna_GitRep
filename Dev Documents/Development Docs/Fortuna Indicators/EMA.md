# Fortuna — Indicator Spec: EMA (Exponential Moving Average)

**What this doc is:** the single source of truth for how Fortuna calculates and reads EMAs —
the exact formulas, periods, rules, thresholds and outputs Fortuna uses. Other books and traders
define EMA signals in different ways; this doc records only what **Fortuna** does. One spec doc per
indicator (RSI, StochRSI, MACD, S&R … follow the same layout), stored in
`Dev Documents\Development Docs\Fortuna Indicators\`.

_Version 2 — 2026‑10‑11. Code: `backend/modules/Module_F_Tech_Indicators_Funnel/trend_indicators/ema/`._

---

## 1. Scope

| Item | Fortuna's choice |
|---|---|
| Instruments | **Nifty 50 now.** Watchlist / options stocks later — same code, no changes. |
| Timeframe | **Daily (1D) only.** Weekly/monthly technically possible (reader supports them) but not used. Intraday not supported yet. |
| EMA periods | **5, 13, 26, 50, 100, 200** — counted in bars of the timeframe (daily → trading days). No other lengths. |
| Price source | **Close.** |
| Parity rule | Every value must equal TradingView's (§3). |

---

## 2. Input data

- Daily candles from R2 (`upstox/indices/Nifty_50.parquet` for Nifty), read through
  `indicator_ohlcv_reader.read_for_indicators()`.
- **Reader rule 1:** bars with a zero or negative open/high/low/close are dropped (Nifty has none).
- **Indicators never fetch data.** Fortuna's data‑refresh step (one button) fetches the latest candles
  first — before 4 pm that is yesterday's close, after 4 pm today's — and the indicators then use the
  **latest stored bar**. Every output says which close it is "as of".
- Upstox never returns the current day from its historical API, so a stored daily bar is always a
  completed session's official close, never a half‑formed candle.
- Nifty history used: 2000‑01‑03 onward (6,657 daily bars as of 2026‑10‑09).

---

## 3. Why and how Fortuna matches TradingView

### 3.1 The decision (2026‑10‑11)
Ash trades by reading his TradingView charts. If Fortuna's EMA were even slightly different, its
crosses could land on a different day from the one Ash sees, and the two would disagree. So the rule
is: **Fortuna uses TradingView's own formulas and methods, and its values must equal TradingView's.**
This applies to every indicator, not only EMA.

### 3.2 What "the TradingView way" means for EMA
TradingView's EMA is Pine Script's `ta.ema(close, n)`. Its documented behaviour is:

```
alpha = 2 / (n + 1)
ema   = na(ema[1]) ? ta.sma(close, n)                    // first value: simple average of n closes
                   : alpha * close + (1 - alpha) * ema[1] // after that: the recursive formula
```

So TradingView **seeds the EMA with the simple average of the first n closes** and shows nothing before
that. Fortuna does exactly the same (§4).

### 3.3 The alternative we rejected
Many code examples (and pandas' `ewm(adjust=False)`) start the EMA from the **first close** instead of
the first n‑day average. pandas' default (`adjust=True`) uses yet another weighting. Both give
different early values. On Nifty's 26‑year history the difference fades to nothing, but on a stock with
a short history (a recent listing) it would be visible — so Fortuna uses the TradingView seed everywhere.

### 3.4 Crosses the TradingView way
TradingView's `ta.crossover(a, b)` is true when **a > b on this bar and a ≤ b on the previous bar**;
`ta.crossunder` is the mirror (a < b now, a ≥ b before). The "≤" matters: if a line touches the other
and crosses the next day, that next day is the cross. Fortuna uses exactly this rule (§5).

### 3.5 How parity was proven
1. Fortuna printed all six EMAs for 7, 8 and 9 Oct 2026; Ash read the same candles on TradingView.
   5/13/26/50/100 matched to the paisa; **EMA 200 was 0.35 higher**.
2. The gap shrank each day at exactly the 200 EMA's own fade rate, which points to a difference in
   **older** data, not the formula.
3. Bisection: compared 13 dates from 2020 to 2026. From 2022 onward **every value matched exactly**,
   including 9 Oct when re‑read.
4. Cause: **TradingView computes indicators only over the history it has loaded.** The first screenshots
   were zoomed into recent days, so TradingView's 200 EMA started from a shorter history and had not yet
   settled. After scrolling back to 2020, TradingView recalculated and its 9 Oct EMA 200 became
   24,077.44 — Fortuna's value.
5. 2020 values differ slightly (EMA 100 −0.17) — old‑data differences that fade to zero by 2022; no
   effect on any current value.

**Verification summary:** all six EMAs equal TradingView to the paisa on Nifty daily on 11 dates
(2022‑10‑03 … 2026‑10‑09); the latest 15 crosses (25 Aug … 9 Oct 2026) confirmed on Ash's chart (§10.2);
the `--state` and snapshot outputs (§10.3, §10.4) checked against the chart.

**Re‑verifying later:** on TradingView, **scroll back a few years first**, then hover the candle and
compare with `ema --dates YYYY-MM-DD …` (§11).

---

## 4. EMA formula

For period **n**:

- α = 2 / (n + 1)
- Bars 1 … n−1 → **blank** (fewer than n closes exist, so no EMA yet — TradingView draws no line there either)
- Bar n → **simple average of the first n closes** (the seed)
- Every later bar → **EMA = α × close + (1 − α) × previous EMA**

| Period | α | Weight on today's close | First value appears at |
|---|---|---|---|
| 5 | 0.3333 | 33.3% | bar 5 |
| 13 | 0.1429 | 14.3% | bar 13 |
| 26 | 0.0741 | 7.4% | bar 26 |
| 50 | 0.0392 | 3.9% | bar 50 |
| 100 | 0.0198 | 2.0% | bar 100 |
| 200 | 0.00995 | 1.0% | bar 200 |

**Worked example (3‑EMA, closes 100, 110, 120, 100):**

| Bar | Close | 3‑EMA | How |
|---|---|---|---|
| 1 | 100 | blank | fewer than 3 closes |
| 2 | 110 | blank | fewer than 3 closes |
| 3 | 120 | **110** | (100 + 110 + 120) / 3 |
| 4 | 100 | **105** | 0.5 × 100 + 0.5 × 110 |

**Short history:** an instrument with fewer than n bars has no n‑EMA (e.g. a new listing with 150 days
has no 200 EMA). Fortuna shows "n/a" instead of a number.

---

## 5. Crosses

### 5.1 Rule (= TradingView `ta.crossover` / `ta.crossunder`)
- **Cross above on day t:** A > B on day t **and** A ≤ B on day t−1.
- **Cross below on day t:** A < B on day t **and** A ≥ B on day t−1.
- A equal to B today is **not** a cross. A blank value on either day → **no cross**.

### 5.2 The 12 checks Fortuna watches

| # | A | B | Meaning |
|---|---|---|---|
| 1–6 | Close | 5, 13, 26, 50, 100, 200 EMA | price vs each line |
| 7 | 5 EMA | 13 EMA | stack pair |
| 8 | 13 EMA | 26 EMA | stack pair |
| 9 | 26 EMA | 50 EMA | stack pair |
| 10 | 50 EMA | 100 EMA | stack pair |
| 11 | 100 EMA | 200 EMA | stack pair |
| 12 | 50 EMA | 200 EMA | **golden cross** (above) / **death cross** (below) |

### 5.3 Which directions are used
- **Nifty 50:** cross‑above **and** cross‑below (direction of the day for options buying, calls and puts).
- **Stocks:** cross‑above only (swing buying).
- Both directions are always calculated; the snapshot's `directions` setting (`both` / `above`)
  decides which become texts and alerts. The states of all 12 checks are always shown.

---

## 6. Stack and stage (−5 … +5)

**Stack order:** 5 > 13 > 26 > 50 > 100 > 200 (bullish) or the reverse (bearish).

**Stage:** start at the fast end and count how many consecutive pairs are aligned.

| Stage | Condition | Label shown |
|---|---|---|
| **+5** | 5 > 13 > 26 > 50 > 100 > 200 | STRONG UPTREND (+5 of 5) — strongest uptrend |
| +4 | 5 > 13 > 26 > 50 > 100, 100 not above 200 | UPTREND (stage +4 of 5) |
| +3 | 5 > 13 > 26 > 50, 50 not above 100 | UPTREND (stage +3 of 5) |
| +2 | 5 > 13 > 26, 26 not above 50 | UPTREND (stage +2 of 5) |
| **+1** | 5 > 13 only | EARLY UPTREND (+1 of 5, weakest) — still wanted for intraday options buying |
| 0 | 5 = 13 | NEUTRAL (0) |
| −1 … −5 | mirror image | EARLY DOWNTREND (−1, weakest) … STRONG DOWNTREND (−5, strongest) |

- The count stops at the first pair that is not aligned. Example: 5 < 13 but 13 > 26 → **−1**
  (a short dip inside a bigger uptrend — the "Bigger trend" line shows the rest).
- 5 or 13 blank → "STAGE n/a". A blank EMA further up stops the count (no 200 EMA → at most ±4).

---

## 7. Check states (all 12 checks, every day)

| Field | Definition |
|---|---|
| **Side** | above / below / equal |
| **Days held** | trading days A has stayed on the current side, **cross day = 1**. A cross that holds shows 1, 2, 3 …; one that fails flips back and resets to 1. |
| **Since** | date the current side began (the last cross). Marked "(start of data)" if the side began with the history rather than with a cross. |
| **Margin** | A − B in points, and (A − B) / B in % |
| **Whole candle clear** | close checks only. Above: the candle's **low** is above the line. Below: the candle's **high** is below the line. Not applicable to EMA‑vs‑EMA pairs (no candle). |

---

## 8. Thresholds (strong / weak)

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

## 9. Snapshot and texts (what Ash reads)

`ema_snapshot.build_ema_snapshot(key, domain, name, directions)` returns one package per instrument per
day: close today/yesterday, all 6 EMAs today/yesterday, stage today/yesterday + label, the 12 check
states, today's crosses, alerts, and the texts below. It **never raises** — a missing file or R2 error
comes back as "not ok" with a reason. Texts are fixed templates (no AI): same data → same words.

| Line | When shown |
|---|---|
| Header: name, as‑of date, close, previous close, change | always |
| Stage label + stack chain (`5 < 13 < 26 …`) | always |
| "Stage moved from X to Y today." | only when the stage changed |
| "EMAs today (yesterday): …" — all 6 values | always |
| "Today: A crossed above/below B — values today (yesterday). Margin … Whole candle clear …" | each cross today (filtered by `directions`) |
| "⚡ GOLDEN CROSS / DEATH CROSS today …" | 50/200 cross today |
| "A holding above/below B for N days (since …), now/gap …%" | crosses 2–**5** trading days old (`RECENT_DAYS = 5`) |
| "Bigger trend: …" | stack pairs and 50/200 held more than 5 days |

**Alerts:** every cross today in the allowed directions (Nifty: both; stocks: above), with golden/death flagged.

---

## 10. Sample outputs (Nifty 50, data as of 9 Oct 2026)

**10.1 EMA values** (`ema`) — matched TradingView exactly:
```
date              close      ema_5     ema_13     ema_26     ema_50    ema_100    ema_200
2026-10-07     22603.05   22664.60   22887.57   23202.90   23518.70   23803.70   24111.80
2026-10-08     22231.80   22520.33   22793.89   23130.96   23468.23   23772.57   24093.09
2026-10-09     22520.45   22520.37   22754.83   23085.74   23431.07   23747.77   24077.44
```

**10.2 Latest crosses** (`ema --crosses 15`) — confirmed on Ash's chart:
```
  2026-08-25  close crossed above 26 EMA
  2026-08-26  close crossed below 5 EMA
  2026-08-26  close crossed below 13 EMA
  2026-08-26  close crossed below 26 EMA
  2026-08-27  close crossed below 50 EMA
  2026-08-27  close crossed below 100 EMA
  2026-08-27  13 EMA crossed below 26 EMA
  2026-09-07  26 EMA crossed below 50 EMA
  2026-09-18  close crossed above 5 EMA
  2026-09-22  close crossed below 5 EMA
  2026-09-23  close crossed above 5 EMA
  2026-09-24  close crossed below 5 EMA
  2026-10-06  close crossed above 5 EMA
  2026-10-07  close crossed below 5 EMA
  2026-10-09  close crossed above 5 EMA
total crosses in history: 4,923
```

**10.3 State of all 12 checks** (`ema --state`):
```
as of 2026-10-09   close 22520.45
stage           : -5  (-5..+5)
EMAs            : 5: 22520.37  13: 22754.83  26: 23085.74  50: 23431.07  100: 23747.77  200: 24077.44

     close vs 5 EMA   : above    held   1 day(s) since 2026-10-09  margin +0.08 (+0.000%)  whole candle clear: no
     close vs 13 EMA  : below    held  31 day(s) since 2026-08-26  margin -234.38 (-1.030%)  whole candle clear: yes
     close vs 26 EMA  : below    held  31 day(s) since 2026-08-26  margin -565.29 (-2.449%)  whole candle clear: yes
     close vs 50 EMA  : below    held  30 day(s) since 2026-08-27  margin -910.62 (-3.886%)  whole candle clear: yes
     close vs 100 EMA : below    held  30 day(s) since 2026-08-27  margin -1227.32 (-5.168%)  whole candle clear: yes
     close vs 200 EMA : below    held  39 day(s) since 2026-08-14  margin -1556.99 (-6.467%)  whole candle clear: yes
     5 EMA vs 13 EMA  : below    held  38 day(s) since 2026-08-17  margin -234.46 (-1.030%)
    13 EMA vs 26 EMA  : below    held  30 day(s) since 2026-08-27  margin -330.91 (-1.433%)
    26 EMA vs 50 EMA  : below    held  23 day(s) since 2026-09-07  margin -345.33 (-1.474%)
    50 EMA vs 100 EMA : below    held 147 day(s) since 2026-03-06  margin -316.71 (-1.334%)
   100 EMA vs 200 EMA : below    held 133 day(s) since 2026-03-27  margin -329.67 (-1.369%)
    50 EMA vs 200 EMA : below    held 141 day(s) since 2026-03-16  margin -646.38 (-2.685%)
```

**10.4 Snapshot texts** (`ema_snapshot`) — live run, 2026‑10‑11, data as of 9 Oct (1 alert: close crossed above the 5 EMA):
```
Nifty 50 — as of 9 Oct close: 22,520.45 (8 Oct: 22,231.80, +288.65 / +1.30%)
STRONG DOWNTREND (-5 of 5): 5 < 13 < 26 < 50 < 100 < 200
EMAs today (yesterday): 5: 22,520.37 (22,520.33) · 13: 22,754.83 (22,793.89) · 26: 23,085.74 (23,130.96) · 50: 23,431.07 (23,468.23) · 100: 23,747.77 (23,772.57) · 200: 24,077.44 (24,093.09)
Today: close crossed above the 5 EMA — 22,520.45 vs 22,520.37 (yesterday 22,231.80 vs 22,520.33). Margin +0.08 (+0.000%). Whole candle clear: no.
Bigger trend: 5 below 13 since 17 Aug · 13 below 26 since 27 Aug · 26 below 50 since 7 Sep · 50 below 100 since 6 Mar · 100 below 200 since 27 Mar · death cross (50 below 200) since 16 Mar
```
Reading it: Nifty is in the strongest downtrend; today's close only just crept above the 5 EMA
(0.08 points, candle not clear) — a weak signal against a fully bearish stack.

---

## 11. Not used / deferred

- Other EMA lengths (9, 20, 21 …), SMA and other moving‑average types.
- Weekly/monthly EMAs, intraday EMAs (needs reader rule 2), 4h/2h timeframes.
- Volume confirmation (see §8).
- **Stocks:** Upstox daily candles are not adjusted for demergers/splits (e.g. Tata Motors 2025‑10‑14,
  Siemens 2025‑04‑07). An adjustment approach is needed before EMAs on affected stocks are trusted.

---

## 12. Code map

All EMA files live in `backend/modules/Module_F_Tech_Indicators_Funnel/trend_indicators/ema/`
(convention: one folder per indicator).

| File / function | Does |
|---|---|
| `ema.py` → `compute_emas(df)` | adds `ema_5 … ema_200` |
| `ema.py` → `detect_crosses(df)` | adds `cross_above_<A>_<B>` / `cross_below_<A>_<B>` for the 12 checks (e.g. `cross_above_ema_50_ema_200` = golden cross) |
| `ema.py` → `stack_stage(df)` | stage −5 … +5 per day |
| `ema.py` → `check_states(df)` | adds `side_`, `held_`, `since_`, `margin_pts_`, `margin_pct_`, `candle_clear_` per check |
| `ema_snapshot.py` → `build_ema_snapshot(...)` | the daily package + texts + alerts; never raises |
| `test_ema.py` (43 tests), `test_ema_snapshot.py` (20 tests) | unit tests, no R2 |

`ema.py` functions are pure (no I/O, nothing instrument‑specific). Full chain on 6,657 bars ≈ 70 ms.
Reader: `market_data/upstox/indicator_ohlcv_reader.py` (13 tests).

**Run** (from `backend/`):
```
python -m modules.Module_F_Tech_Indicators_Funnel.trend_indicators.ema.ema                    # latest 3 days' EMAs
python -m modules.Module_F_Tech_Indicators_Funnel.trend_indicators.ema.ema --dates 2025-10-01 2026-10-09
python -m modules.Module_F_Tech_Indicators_Funnel.trend_indicators.ema.ema --crosses 15
python -m modules.Module_F_Tech_Indicators_Funnel.trend_indicators.ema.ema --state
python -m modules.Module_F_Tech_Indicators_Funnel.trend_indicators.ema.ema_snapshot [--json] [--directions above]
python -m pytest modules/Module_F_Tech_Indicators_Funnel/trend_indicators/ema -v
```

---

## 13. Change log

| Date | Change |
|---|---|
| 2026‑10‑11 | v1 — periods, formula, 12 checks, cross rule, stage, check states, thresholds (none yet), volume deferred. |
| 2026‑10‑11 | v2 — TradingView parity explained in detail (§3), snapshot and texts (§9), sample outputs (§10), files moved to `trend_indicators/ema/`, data fetch left to the refresh step. |
