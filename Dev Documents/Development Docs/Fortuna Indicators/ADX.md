# Fortuna — Indicator Spec: ADX / DMI (Average Directional Index, Directional Movement Index)

**What this doc is:** the single source of truth for how Fortuna calculates and reads ADX / DMI — formulas,
settings, rules, thresholds, outputs, how parity with TradingView was proven, tests, and known
discrepancies. Records only what **Fortuna** does. Same layout as `EMA.md` / `MACD.md`, stored in
`Dev Documents\Development Docs\Fortuna Indicators\`.

_Version 1.1 — 2026‑10‑12 (§0 plain‑English definition; runbook `Fortuna-Indicators-Runbook.md`). v1 — **ADX complete (parts 1–3): the five DMI lines, strength band, slope, direction,
events, labels and texts on all six timeframes; daily equal to TradingView (tv.dhan) to 4 decimals; 7 cross
dates checked on the chart.** Code: `backend/modules/Module_F_Tech_Indicators_Funnel/trend_indicators/adx/`._

---

## 0. What ADX / DMI is, how it works, how to read it (plain English)

**What it is.** The Directional Movement Index (J. Welles Wilder, 1978) answers two questions:
**which side is pushing harder** (+DI vs −DI) and **is there a real trend at all, or just chop** (ADX).
ADX measures **trend strength, not direction** — it rises in a strong fall just as it does in a strong rise.
Scale 0–100, the same on every instrument and timeframe.

**How it works.**
1. Each candle, compare it with the previous one: **up‑move** = how far the high went above the previous
   high; **down‑move** = how far the low went below the previous low. Only the bigger one counts (+DM or −DM);
   the other is 0. An inside candle gives 0 to both.
2. **True range (TR)** = the candle's full range including any gap from the previous close.
3. Smooth all three over 14 candles with Wilder's average (slow, α = 1/14). **+DI** = smoothed +DM ÷ smoothed
   TR × 100 (share of the range that was upward push); **−DI** likewise for downward push.
4. **DX** = gap between +DI and −DI as a % of their sum — how one‑sided the push is today (spiky).
5. **ADX** = DX smoothed over 14 candles — the steady trend‑strength line. **ADXR** = average of today's
   ADX and the ADX 13 candles ago — an even slower version.
Formulas: §3.1.

**How to read it:**

| Look at | Reads as |
|---|---|
| **+DI above −DI** | bulls pushing harder (blue above orange); **−DI above +DI** = bears |
| **+DI / −DI cross** | control changing hands — but only meaningful if ADX says a trend exists |
| **ADX level** (Fortuna's bands, §4) | < 20 no trend (chop) · 20–25 trend forming · 25–40 trending · 40–50 strong · ≥ 50 very strong (often late in the move) |
| **ADX crossing 25** | above = trend confirmed (direction from the DIs); below = trend fading |
| **ADX rising / falling** | rising = the current trend (up *or* down) is strengthening; falling = weakening or turning into a range |

Example (Nifty daily, 9 Oct 2026): +DI 9.99, −DI 38.39 → bears in control since 12 Aug; ADX 43.84 and rising
for 11 days → **STRONG TREND DOWN**. The 12 Aug DI cross happened with ADX only 13.20 ("no trend, weak
signal"); the trend was confirmed when ADX crossed 25 on 9 Sep.

**Good at:** filtering — telling a trending market (where EMA and MACD signals work) from a sideways one
(where they whipsaw). Nifty daily May–Jul 2026 had 11 DI crosses, all with ADX below 22: chop. **Weak at:**
it is slow (two layers of 14‑candle smoothing), so ADX confirms a trend after it has started and keeps
rising late into a move; very high ADX often comes near the end. It says nothing about direction by itself.

**How it fits:** EMA = direction, MACD = momentum, ADX = strength. Read the three together — e.g. "EMA stage
−5, MACD strong downtrend, ADX 44 rising" = a strong, established downtrend.

---

## 1. Scope

| Item | Fortuna's choice |
|---|---|
| Instruments | **Nifty 50 now**; watchlist / options stocks later — same code. |
| Timeframes | **1M, 1W, 1D, 60m, 15m, 5m** (same code; periods = candles). 2h / 4h = open item. |
| Settings | **DMI 14 14** — DI Length 14, ADX Smoothing 14 (Ash's tv.dhan legend "DMI 14 14"). |
| Why ADX | EMA stage and MACD give **direction** and **momentum**; ADX adds **trend strength** — is this a trend worth trading or chop? (Ash, 2026‑10‑12.) ADX rises in strong down‑trends as much as up‑trends; direction comes from +DI vs −DI. |
| Parity rule | Every TradingView number must equal Fortuna's (§3). |
| Reference chart | tv.dhan.co (Nifty) — TradingView "Directional Movement Index" with **five lines**. |
| Display rule | **All five TradingView numbers are shown** (+DI, −DI, DX, ADX, ADXR); labels / texts are extra, never instead. |

---

## 2. Input data

Same reader and rules as MACD (`MACD.md` §2): `indicator_ohlcv_reader.read_for_indicators()` —
1D/1W/1M from `upstox/indices/Nifty_50.parquet`, 60m/15m/5m from `upstox/nse_indexes_intraday/Nifty_50.parquet`;
reader rules 1–2; latest weekly / monthly candle = "to date"; indicators never fetch data. **ADX uses high,
low and close** (MACD uses close only) — this matters for the 1h discrepancy (§10.3).

---

## 3. TradingView parity

### 3.1 The five lines, TradingView's method (Wilder)

```
up    = high − high[1]                 down = low[1] − low
+DM   = up   if up > down and up > 0 else 0        (blank on the first candle)
−DM   = down if down > up and down > 0 else 0      (a tie gives 0 to both)
TR    = max(high − low, |high − close[1]|, |low − close[1]|)   (blank on the first candle)
+DI   = 100 × rma(+DM, 14) ÷ rma(TR, 14)    −DI likewise      (x/0 → blank, then carried forward = Pine fixnan)
DX    = 100 × |+DI − −DI| ÷ (+DI + −DI)     (sum 0 → divide by 1)
ADX   = rma(DX, 14)
ADXR  = (ADX + ADX 13 candles ago) ÷ 2
```
`rma` = Wilder's average (Pine `ta.rma`): α = 1/14, **seeded with the simple average of the first 14 values**,
blank before. First values: +DI / −DI / DX candle 15, ADX candle 28, ADXR candle 41.

**TradingView legend order:** `DMI 14 14  +DI  −DI  DX  ADX  ADXR`. Ash's colours: +DI blue, −DI orange, DX
light orange (spiky), ADX pink, ADXR purple.

### 3.2 How parity was proven
1. **DX from the chart's own DIs** (before code): daily 9 Oct 2026: 100 × (38.3904 − 9.9922) ÷ (48.3826) =
   58.695 = chart; 1h 9 Oct 15:15: 7.077 = chart.
2. **Daily 9 Oct 2026, all five lines equal to 4 decimals:** 9.9922 / 38.3904 / 58.6951 / 43.8447 / 37.4798.
3. **ADXR lookback settled:** 13 candles back gives 37.4798 = chart; 14 back gives 37.8067. So ADXR uses n − 1.
4. **Daily cross candles** — Fortuna's ADX at the cross equals the chart: 12 Aug 2026 13.20 (chart 13.2046),
   29 Jul 2026 10.74 (10.7445).
5. **5m:** ADX at the 9 Oct 15:10 cross 30.47 = chart 30.4703.
6. **Cross dates** (§10.2): 7 events on 1M / 1W / 1D / 15m / 5m all on the chart's own candle.
7. **1h:** within 0.002–0.01 — known feed difference, see §10.3.

---

## 4. Strength band (convention)

ADX is bounded 0–100 and means the same on every instrument, so its levels are part of its definition
(unlike MACD). Shown as **labelled facts**; whether these levels work best on Nifty is to be tested.

| ADX | Band (`adx_band`) | Text |
|---|---|---|
| < 20 | `no_trend` | NO TREND (chop) |
| 20 – < 25 | `forming` | TREND FORMING |
| 25 – < 40 | `trending` | TRENDING |
| 40 – < 50 | `strong` | STRONG TREND |
| ≥ 50 | `very_strong` | VERY STRONG TREND (often late in the move) |

---

## 5. States, events, label (`adx_states`, `adx_label`)

**States per candle:** `adx_band`; `adx_slope` (+1 rising / −1 falling / 0 flat vs previous candle) and
`adx_slope_held`; `di_side` (+1 bulls = +DI above −DI, −1 bears, 0 equal), `di_held` (cross candle = 1),
`di_since`, `di_from_start`.

**Events** (TradingView cross rule): `di_cross_above` / `di_cross_below` (+DI vs −DI);
`adx_cross_above_25` (trend confirmed) / `adx_cross_below_25` (trend fading). **Not an event:** ADX turning
up/down on a single candle (too noisy — shows only as "rising/falling for N candles"). **ADX crossing 20 is
not an event** (it hovers around 20 in chop); 20 shows only through the band.

**Label** (`adx_label`): band + direction — `STRONG TREND DOWN`, `TRENDING UP`, `TREND FORMING UP`,
`VERY STRONG TREND DOWN`; `NO TREND` carries no direction; DI equal → `… (no direction)`; blank → `n/a (not
enough history)`. `adx_all(df)` = compute_adx → adx_states → adx_label.

**DI‑cross tag (Ash, 2026‑10‑12):** every +DI/−DI cross is tagged with the ADX at that moment and its band:
"no trend, weak signal" · "trend forming" · "trending, meaningful" · "strong trend, meaningful" · "very strong
trend (often late in the move)". Reason: Nifty daily May–Jul 2026 had 11 DI crosses, all with ADX below 22
(chop). A fact tag, not a filter.

**Directions:** Nifty both; stocks bullish only. Bullish events: +DI crosses above −DI; ADX crosses above 25
while bulls lead; ADX crosses below 25 while bears lead (a downtrend fading).

**Thresholds / candidate filters (not adopted):** ignore DI crosses with ADX < 20; require ADX rising;
"ADX turning down from above 40" as trend‑exhaustion warning; test 20/25 vs other levels on Nifty history.

---

## 6. Snapshot and texts (`adx_snapshot.build_adx_snapshot`)

One JSON‑safe package per timeframe + a summary line; never raises (a failed timeframe → `None` + reason).
Fixed templates. Real wording:

| Line | When |
|---|---|
| `Nifty 50 · 1D DMI — as of 9 Oct: close 22,520.45` (1W/1M "(week/month to date)", intraday "… candle") | always |
| `+DI 9.99 · -DI 38.39 · DX 58.70 · ADX 43.84 · ADXR 37.48 [yesterday: …]` — the five TradingView numbers | always |
| `STRONG TREND DOWN — ADX 43.84 rising for 11 days; bears (-DI above +DI) since 12 Aug.` (`(but no trend)` when NO TREND) | always |
| `Today: +DI crossed above -DI → bulls take over. ADX 10.74 — no trend, weak signal.` | DI cross on the latest candle |
| `⚡ Today: ADX crossed above 25 → trend confirmed (down, bears in control).` / `… below 25 → trend fading.` | ADX‑25 cross |
| `Bears holding for 4 candles (since 9 Oct 15:10); crossed with ADX 30.47 — trending, meaningful; now ADX 25.83.` | side 2–5 candles old |
| `Bigger picture: ADX above 25 since 9 Sep (21 days) · bears since 12 Aug (41 days).` | states held > 5 candles |
| `ADX: 1M trending down (rising) · 1W no trend (rising) · 1D strong trend down (rising) · …` | summary, once |

Package fields: `instrument, timeframe, directions, as_of, partial, previous, close, values{today, previous}
{plus_di, minus_di, dx, adx, adxr}, label, strength{adx, band, slope, slope_held, above_25, level_held,
level_since, level_from_start}, direction{side, held, since, from_start}, events_today, last_events, alerts,
texts`. Texts round to 2 decimals; the package keeps full precision.

---

## 7. Code map

All in `backend/modules/Module_F_Tech_Indicators_Funnel/trend_indicators/adx/`:

| File / function | Does |
|---|---|
| `adx.py` → `rma_tradingview(series, n)` | Wilder's average, seeded from the first n non‑blank values |
| `adx.py` → `compute_adx(df, di_len=14, adx_len=14, adxr_lookback=13)` | adds `plus_di, minus_di, dx, adx, adxr`; pure; ValueError on bad input |
| `adx.py` → `strength_band`, `adx_states`, `adx_label`, `adx_all` | §4–5 |
| `adx.py` → `__main__` | `--timeframe {…,all} --bars --dates --ohlc --state --crosses N` → screen + `logs/adx_test_logs/adx_check_<tf>.log` |
| `adx_snapshot.py` → `snapshot_from_bars`, `summary_line`, `build_adx_snapshot` | §6; manual check → `logs/adx_test_logs/adx_snapshot.log` |
| `test_adx.py` (43), `test_adx_snapshot.py` (18), `conftest.py` | tests → `logs/adx_test_logs/test_adx.log` |

Shared pieces (imported, not copied): `cross_above` / `cross_below` (ema.py), `_runs` (macd.py), formatting
helpers (macd_snapshot.py). Deferred: move these and the timeframe→domain map into one shared helper module
when the next indicator needs them.

**Run** (from `backend/`):
```
python -m pytest modules/Module_F_Tech_Indicators_Funnel/trend_indicators/adx -v
python -m modules.Module_F_Tech_Indicators_Funnel.trend_indicators.adx.adx --dates 2026-10-09
python -m modules.Module_F_Tech_Indicators_Funnel.trend_indicators.adx.adx --timeframe 60m --dates 2026-10-09 --ohlc
python -m modules.Module_F_Tech_Indicators_Funnel.trend_indicators.adx.adx --timeframe all --state
python -m modules.Module_F_Tech_Indicators_Funnel.trend_indicators.adx.adx --crosses 15
python -m modules.Module_F_Tech_Indicators_Funnel.trend_indicators.adx.adx_snapshot [--timeframes 1d 60m] [--directions above] [--json]
```

---

## 8. Not used / deferred / open items

- 2h / 4h ADX (with MACD's open item); live intraday (same as MACD).
- Candidate filters in §5 (not adopted); "ADX turning down from above 40" exhaustion warning.
- Combining ADX with EMA stage / MACD into one view (e.g. "MACD cross only counts when ADX ≥ 25") — later,
  after testing.
- 1h feed difference (§10.3) — recorded, not hunted.
- **Snapshot for stocks:** `build_adx_snapshot` reads 1d/1w/1mo from domain `indices` only; stocks need a domain option (`universe`). Same for MACD. Do with the watchlist work.

---

## 9. Testing and verification

**Unit tests — 61 passing on Windows, 2026‑10‑12** (log `logs\adx_test_logs\test_adx.log`):

| Group | Tests | Why they pass |
|---|---|---|
| Formula | `test_matches_plain_pine_reference` (all five lines on a 200‑candle walk vs a separate plain loop of Pine's DMI, 1e‑9), `test_rma_hand_worked` (rma3 of 1..5 = 2, 2.6667, 3.4444), `test_rma_with_leading_blank_seeds_from_first_value`, `test_dm_rule_ties_and_true_range` (hand‑worked DM/TR incl. a tie), `test_first_values` (15 / 28 / 41), `test_adxr_lookback`, `test_dx_formula_matches_tradingview` ×2 (Ash's chart values) | hand‑worked, independent loop, chart numbers |
| Edges | `test_flat_prices_no_errors`, `test_values_in_range` (0–100), `test_trend_phase_has_plus_di_above_minus_di`, `test_short_history_all_blank`, `test_input_not_modified`, `test_adds_exactly_the_adx_columns`, validation ×5 | contract |
| States / label | `test_strength_band_edges` ×10 (every boundary), `test_strength_band_blank`, `test_slope_and_held`, `test_di_side_cross_held_since`, `test_adx_cross_25` (25 itself is not "above"), `test_adx_label` ×7 (incl. Nifty daily 9 Oct → STRONG TREND DOWN, 1h → TREND FORMING UP), `test_adx_all_on_walk`, input/validation ×2 | §4–5, hand‑built series |
| Snapshot | header ×4, all five numbers today + previous, label line, "(but no trend)", DI‑cross tag text, ADX‑25 texts, stocks filter, holding line with ADX at the cross, bigger picture, short history, JSON, summary line, never‑raise ×3 | §6 |

---

## 10. Sample outputs and verification record

### 10.1 Values (Nifty 50, 9 Oct 2026)

| Candle | Fortuna +DI / −DI / DX / ADX / ADXR | tv.dhan | Result |
|---|---|---|---|
| 1D 9 Oct | 9.9922 / 38.3904 / 58.6951 / 43.8447 / 37.4798 | same | ✅ exact (4 decimals) |
| 1h 9 Oct 15:15 | 30.3495 / 26.3352 / 7.0819 / 20.0349 / 20.3764 | 30.3440 / 26.3330 / 7.0769 / 20.0430 / 20.3867 | ≈ (§10.3) |

### 10.2 Cross dates (checked on tv.dhan, 12 Oct 2026)

| Chart | Fortuna event | Chart on that candle (+DI / −DI · ADX) | Result |
|---|---|---|---|
| 1D | +DI crossed below −DI, 12 Aug 2026 (ADX 13.20, no trend) | 25.35 < 26.96 · 13.20 | ✅ |
| 1D | +DI crossed above −DI, 29 Jul 2026 (ADX 10.74, no trend) | 28.68 > 26.04 · 10.74 | ✅ |
| 1D | ADX crossed above 25, 9 Sep 2026 (trend confirmed, down) | ADX 25.46 | ✅ |
| 1W | +DI crossed below −DI, week of 17 Aug 2026 | 20.49 < 22.95 | ✅ |
| 1M | +DI crossed below −DI, Mar 2026 | 17.49 < 23.69 | ✅ |
| 15m | +DI crossed above −DI, 9 Oct 09:15 | 27.71 > 26.45 | ✅ |
| 5m | +DI crossed below −DI, 9 Oct 15:10 (ADX 30.47) | 22.06 < 23.10 · 30.4703 | ✅ (ADX exact) |

### 10.3 Known discrepancy — 1h

- **Seen:** 1h DMI on tv.dhan differs from Fortuna by 0.002–0.01 (9 Oct 15:15 above; 8 Oct 15:15, 6 Oct 15:15
  similar; re‑read identical, so not loaded history). On 1 Oct 11:15 DX / ADX / ADXR were **exact** while both
  DIs were 0.125 % lower on the chart — only the smoothed **true range** differed then. The gap **shrinks
  steadily** from 1 Oct to 9 Oct.
- **Checked:** the candles hovered (1 Oct 11:15, 6 Oct 15:15, 8 Oct 15:15, 9 Oct 15:15) have identical O/H/L/C;
  every day since July has all 7 one‑hour candles at the same times in both the daily and 1h files.
- **Cause (most likely):** a small high / low / close difference in one or more **September 2026** 1h candles
  between the Upstox and Dhan feeds, fading out of Wilder's slow average. MACD (close only) matched 1h
  exactly. Daily ADX is exact.
- **Impact:** same band, label and direction; a DI or 25 cross could only shift by one candle if the lines were
  within ~0.01. **Decision (Ash, 2026‑10‑12): record, don't hunt.**

### 10.4 Where Nifty stood, 9 Oct 2026 close (`adx_snapshot`)

```
Nifty 50 · 1M DMI — as of Oct 2026 (month to date): close 22,520.45
+DI 13.43 · -DI 25.42 · DX 30.87 · ADX 27.83 · ADXR 32.01 [last month: +DI 13.87 · -DI 24.09 · DX 26.92 · ADX 27.60 · ADXR 32.01]
TRENDING DOWN — ADX 27.83 rising for 1 month; bears (-DI above +DI) since Mar 2026.
Bigger picture: ADX above 25 since Dec 2023 (35 months) · bears since Mar 2026 (8 months).

Nifty 50 · 1W DMI — as of week of 5 Oct (week to date): close 22,520.45
+DI 12.68 · -DI 33.13 · DX 44.65 · ADX 18.53 · ADXR 16.83 [last week: …]
NO TREND — ADX 18.53 rising for 6 weeks; bears (-DI above +DI) since week of 17 Aug (but no trend).
Bigger picture: ADX below 25 since week of 8 Jul 2024 (118 weeks) · bears since week of 17 Aug (8 weeks).

Nifty 50 · 1D DMI — as of 9 Oct: close 22,520.45
+DI 9.99 · -DI 38.39 · DX 58.70 · ADX 43.84 · ADXR 37.48 [yesterday: +DI 11.12 · -DI 42.73 · DX 58.70 · ADX 42.70 · ADXR 37.24]
STRONG TREND DOWN — ADX 43.84 rising for 11 days; bears (-DI above +DI) since 12 Aug.
Bigger picture: ADX above 25 since 9 Sep (21 days) · bears since 12 Aug (41 days).

Nifty 50 · 60m DMI — as of 9 Oct 15:15 candle: close 22,520.45
TREND FORMING UP — ADX 20.03 falling for 7 candles; bulls (+DI above -DI) since 9 Oct 13:15.
Bulls holding for 3 candles (since 9 Oct 13:15); crossed with ADX 22.10 — trend forming; now ADX 20.03.

Nifty 50 · 15m DMI — as of 9 Oct 15:15 candle: close 22,520.45
TRENDING UP — ADX 35.18 falling for 2 candles; bulls (+DI above -DI) since 9 Oct 09:15.
Bigger picture: ADX above 25 since 8 Oct 09:45 (48 candles) · bulls since 9 Oct 09:15 (25 candles).

Nifty 50 · 5m DMI — as of 9 Oct 15:25 candle: close 22,520.45
TRENDING DOWN — ADX 25.83 falling for 6 candles; bears (-DI above +DI) since 9 Oct 15:10.
Bears holding for 4 candles (since 9 Oct 15:10); crossed with ADX 30.47 — trending, meaningful; now ADX 25.83.

ADX: 1M trending down (rising) · 1W no trend (rising) · 1D strong trend down (rising) · 60m trend forming up (falling) · 15m trending up (falling) · 5m trending down (falling)
```

**Reading it with EMA and MACD (9 Oct close):** daily is a strong downtrend on all three (EMA stage −5, MACD
strong downtrend, ADX 43.8 rising); −DI took over on 12 Aug, one day before MACD crossed below its signal on
13 Aug. Weekly: bears clearly ahead but ADX 18.5 — not yet a weekly trend. Intraday: Friday's bounce shows on
15m/60m and was fading by the close.

**Latest daily events (`adx --crosses 15`):** 20 Apr ADX below 25 · 23 Apr +DI below −DI (ADX 20.71, forming) ·
May–Jul eleven DI crosses all tagged "no trend, weak signal" (ADX 9.6–21.7) · 12 Aug +DI below −DI (ADX 13.20,
no trend) · 9 Sep ADX above 25 (trend confirmed, down). 804 events in history.

---

## 11. Change log

| Date | Change |
|---|---|
| 2026‑10‑12 | v1 — ADX parts 1–3 built: `compute_adx` (five TradingView DMI lines; ADXR 13 back confirmed), states / events / label, DI‑cross ADX tag, snapshot texts + summary line, manual check (`--state`, `--crosses`, `--timeframe all`, `--ohlc`), logging to `logs/adx_test_logs/`. Daily exact to 4 decimals; 7 cross dates on the chart; 1h feed difference recorded (§10.3). Tests 61. |
| 2026‑10‑12 | v1.1 — §0 "What ADX / DMI is, how it works, how to read it" (step‑by‑step method, reading table, strengths/weaknesses). Runbook: `Fortuna-Indicators-Runbook.md`. Noted: `adx_snapshot` reads D/W/M from `indices` only — stocks need a domain option (open item). |
