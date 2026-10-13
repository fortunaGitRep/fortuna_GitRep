# Fortuna — Indicator Spec: RSI (Relative Strength Index)

**What this doc is:** the single source of truth for how Fortuna calculates and reads RSI — formula, settings,
zones, states, events, texts, how parity with TradingView was proven, the research behind Ash's choices, tests
and known discrepancies. Records only what **Fortuna** does. Same layout as `EMA.md` / `MACD.md` / `ADX.md`,
stored in `Dev Documents\Development Docs\Fortuna Indicators\`.

_Version 1 — 2026‑10‑13. **RSI complete (parts 1–3): RSI value + hidden Smoothed MA, seven zones, states,
events, alerts and report‑style texts on all six timeframes; equal to TradingView (tv.dhan) on 1M / 1W / 1D /
60m / 15m / 5m; four zone‑change dates confirmed on the chart.** Code:
`backend/modules/Module_F_Tech_Indicators_Funnel/oscillators/rsi/`._

---

## 0. What RSI is, how it works, how to read it (plain English)

**What it is.** RSI (J. Welles Wilder, 1978) measures **how strongly price has been pushed up versus down
over the last 14 candles**, on a fixed 0–100 scale that means the same on every instrument and timeframe.
High = buyers have been winning the recent closes; low = sellers have.

**How it works.**
1. Each candle, take the change in close from the previous candle. A rise counts as a **gain**, a fall as a
   **loss** (the other side is 0).
2. Average the gains and the losses over 14 candles with Wilder's slow average (the same one ADX uses).
3. RS = average gain ÷ average loss; **RSI = 100 − 100 ÷ (1 + RS)**. All gains → 100, all losses → 0,
   equal gains and losses → 50.

**How Fortuna reads it — seven zones (Ash, 2026‑10‑13, §4):**

| RSI | Zone | Reads as |
|---|---|---|
| > 80 | **OVERBOUGHT** | extreme buying — watch for exhaustion |
| 70–80 | **STRONG BULL** | strong upward momentum (normal in a bull trend, not a sell signal by itself) |
| 55–70 | **BULLISH** | buyers in control |
| 45–55 | **RSI S&R ZONE** | RSI's own support / resistance — **first profit booking zone**; the trend decides here |
| 30–45 | **BEARISH** | sellers in control |
| 20–30 | **STRONG BEAR** | strong downward momentum (normal in a bear trend, not a buy signal by itself) |
| < 20 | **OVERSOLD** | extreme selling — watch for exhaustion |

Every move from one zone to another is an alert, worded with **direction and strength**: e.g. `RSI 33.66
STRONG BEAR (20–30) rising up into BEARISH (30–45)` (§6).

Example (Nifty daily, 9 Oct 2026): RSI 36.50 — rose out of STRONG BEAR (27.55 on 8 Oct) into BEARISH; below 50
since 26 Aug. Weekly 32.74 and monthly 44.37 also BEARISH; 60m in the S&R zone, 15m BULLISH, 5m just broke
below 45.

**Good at:** showing momentum and its extremes on one fixed scale; comparing timeframes at a glance.
**Weak at:** in a strong trend RSI can stay in STRONG BULL / STRONG BEAR for a long time — those zones are not
reversal signals by themselves (that is why Fortuna uses 80/20 for "extreme", §3.4). It lags a little (14‑candle
average) and whipsaws around the zone edges on 5m / 15m.

**How it fits:** EMA = direction, MACD = momentum (trend vs signal), ADX = trend strength, RSI = momentum
**level** on a 0–100 scale with Ash's S&R zone. **Note:** MACD is technically an oscillator too, but it lives in
`trend_indicators/` because Fortuna reads it for trend + momentum (`MACD.md`); RSI and Stochastic RSI are the
`oscillators/` family.

---

## 1. Scope

| Item | Fortuna's choice |
|---|---|
| Instruments | **Nifty 50 now**; watchlist / options stocks later — same code. |
| Timeframes | **1M, 1W, 1D, 60m, 15m, 5m** (periods = candles). 2h / 4h = open item. |
| Settings | **Length 14 · Source close · Smoothing Line SMA · Smoothing Length 14** (Ash's tv.dhan settings dialog, 2026‑10‑13). Chart levels 70 / 50 / 30; the Smoothed MA line is **switched off** on Ash's chart. |
| Parity rule | Every TradingView number must equal Fortuna's (§3). |
| Reference chart | tv.dhan.co (Nifty); tv.upstox / pro.upstox (stocks). |
| Display rule | The RSI value TradingView shows is always shown; zones, labels, texts are extra. The Smoothed MA is **calculated but hidden** (§5). |
| Directions | **Both directions always, index and stocks alike — no filter** (Ash, 2026‑10‑13: "I need to constantly know what's happening" — options stocks later, and his swing holdings). |
| Fortuna principle | **Fortuna = TradingView parity + investor mentality + what works in India, else TradingView's default** (Ash, 2026‑10‑13). The investor / India research pass for all indicators is Phase 3, after every indicator is built (§8). |

---

## 2. Input data

Same reader and rules as MACD / ADX (`MACD.md` §2): `indicator_ohlcv_reader.read_for_indicators()` — 1D/1W/1M
from `upstox/indices/Nifty_50.parquet`, 60m/15m/5m from `upstox/nse_indexes_intraday/Nifty_50.parquet`; reader
rules 1–2; latest weekly / monthly candle = "to date"; indicators never fetch data. **RSI uses close only.**

---

## 3. TradingView parity and research

### 3.1 TradingView's RSI (Pine `ta.rsi`)
```
change = close − close[1]                      (blank on the first candle)
up     = rma(max(change, 0), 14)
down   = rma(max(−change, 0), 14)
rsi    = 100 if down = 0;  else 0 if up = 0;  else 100 − 100 / (1 + up / down)
rsi_ma = sma(rsi, 14)                          ("Smoothed MA" line — hidden in Fortuna)
```
`rma` = Wilder's average = `indicator_common.smoothing.rma_tradingview` (α = 1/14, seeded with the simple average
of the first 14 values) — the same function proven exact on ADX (`ADX.md` §3.2). **First values: RSI candle 15,
RSI MA candle 28.** Pine checks `down = 0` first, so a flat stretch gives **100**, not 50 (tested).

### 3.2 How parity was proven (2026‑10‑13)
1. Daily 9 Oct 2026: Fortuna **36.50** = Ash's tv.dhan legend.
2. One completed candle on every other timeframe, RSI **and** the Smoothed MA (Ash switched it on for the check):

| Chart · candle | Fortuna RSI / MA | tv.dhan RSI / MA | Result |
|---|---|---|---|
| 1M Sep 2026 | 44.82 / 56.29 | 44.82 / 56.29 | ✅ exact |
| 1M Aug 2026 | 51.94 / 57.55 | 51.94 / 57.55 | ✅ exact |
| 1W week of 28 Sep 2026 | 31.06 / 46.27 | 31.06 / 46.27 | ✅ exact |
| 1D 7 Oct 2026 | 33.13 / 31.45 | 33.13 / 31.45 | ✅ exact |
| 1D 9 Oct 2026 | 36.50 | 36.50 | ✅ exact |
| 60m 9 Oct 2026 15:15 | 51.18 / 41.86 | 51.18 / 41.85 | ✅ RSI exact; MA 0.01 (§10.3) |
| 15m 9 Oct 2026 15:15 | 56.85 / 62.14 | 56.85 / 62.14 | ✅ exact |
| 5m 9 Oct 2026 15:15 | 50.83 / 57.99 | 50.83 / 57.99 | ✅ exact |

3. Zone‑change dates confirmed on the chart (§10.2).

### 3.3 The Smoothed MA (research, 2026‑10‑13)
A 14‑SMA of RSI used like MACD's signal line: RSI crossing above / below it = momentum turning; also as a trend
filter (RSI above its MA = improving even while low). Some traders treat it as dynamic support / resistance — no
source tests that. Evidence is thin: the only India test (Share.Market, 25 years, Nifty‑index stocks) tried RSI
vs its 100/200 EMA — many small long‑only gains, shorts lost; a popular TradingView RSI‑SMA strategy is Bitcoin‑only
with no costs. **Decision (Ash):** calculate it, keep it hidden (no texts, no alerts, not in the snapshot package),
keep its crosses in `rsi_states` for the Phase 4 Nifty test. Sources: [TradingView RSI](https://www.tradingview.com/support/solutions/43000502338-relative-strength-index-rsi/),
[Share.Market study](https://www.phonepeinvest.com/buzz/insights/the-rsi-myth-is-this-popular-indicator-worth-using-part-2-research-report),
[TradingView RSI‑SMA script](https://www.tradingview.com/script/ZINSYeR8-RSI-SMA-Crossover-Strategy).

### 3.4 80 / 20 instead of 70 / 30 (research, 2026‑10‑13)
Wilder used 70/30 as turning points. 80/20 readings are rarer and mark stronger momentum (fewer, later setups).
Cardwell's range rules (popularised by Constance Brown): in an uptrend RSI tends to live 40–80 (pullbacks find
support at 40–50), in a downtrend 20–60 (rallies stall at 50–60) — so **RSI 70 in a bull trend is not
overbought**; 80 / 20 mark the real extremes, and even they are "not automatically" sell / buy signals. No study
compares 70/30 vs 80/20 on Indian markets (Phase 4 can). **Decision (Ash):** 80 / 20 = OVERBOUGHT / OVERSOLD,
70 / 30 kept as the STRONG BULL / STRONG BEAR boundaries (they are the lines on his chart). Sources:
[Wikipedia RSI](https://en.wikipedia.org/wiki/Relative_strength_index), [NexusFi Cardwell framework](https://nexusfi.com/a/concepts/cardwell-rsi-framework),
[LuxAlgo range rules](https://www.luxalgo.com/library/concept/rsi-range-rules.md), [Macroption RSI period](https://macroption.com/rsi-period).

### 3.5 RSI ~55 support / resistance (Ash's observation, research 2026‑10‑13)
Ash: RSI near 55 acts as support in up phases and resistance in down phases on all timeframes — **not exactly 55,
but close to 55 when price is also at a price S&R level.** It sits where Brown's bull buy zone (40–50) and bear
sell zone (55–65) meet ([Constance Brown RSI script](https://vn.tradingview.com/script/s3mrd1tU-Constance-Brown-RSI),
[CMT Association](https://cmtassociation.org/chartadvisor/mastering-the-relative-strength-index-rsi-how-to-read-it-correctly/)).
All published support is chart examples, no backtests; nothing supports "always". **Decision:** the 45–55 RSI S&R
zone is built now; the ~55‑at‑price‑S&R study waits for the price S&R indicator (Phase 5) and the Nifty testing
tool (Phase 4) — Phase 6.

### 3.6 Settings research
No RSI length is shown best in general — 14 is Wilder's and the most used; shorter = faster / more extremes,
longer = smoother ([Macroption](https://macroption.com/rsi-period)). Share.Market's India test favoured 21 for
30→70 and 7 for 50‑cross rules (no costs, current index members, numbers in images). **Ash: "these values are good
to go"** — 14 / close / SMA 14 kept; length testing belongs to Phase 4.

---

## 4. Zones (Ash, 2026‑10‑13)

| RSI | Key (`rsi_zone`) | Label |
|---|---|---|
| ≥ 80 | `overbought` | OVERBOUGHT (>80) |
| 70 – < 80 | `strong_bull` | STRONG BULL (70–80) |
| > 55 – < 70 | `bullish` | BULLISH (55–70) |
| **45 – 55 (both inside)** | `sr_zone` | **RSI S&R ZONE (45–55)** — first profit booking |
| 30 – < 45 | `bearish` | BEARISH (30–45) |
| 20 – < 30 | `strong_bear` | STRONG BEAR (20–30) |
| < 20 | `oversold` | OVERSOLD (<20) |

80 and 70 belong to the upper zone, 30 and 20 to the zone above them; every boundary is a unit test.
How it was settled: Ash keeps 20/80 for oversold/overbought (§3.4); added 45–55 as the RSI S&R / first profit
booking zone; renamed "weak" (20–30) because it is a good reading when he buys puts; then STRONG DOWN / STRONG UP
became STRONG BEAR / STRONG BULL with the strength carried by the event wording (§6).

---

## 5. States, events, label (`rsi_states`, `rsi_label`)

**States per candle:** `rsi_zone`, `rsi_zone_held` (first candle = 1), `rsi_zone_since`, `rsi_zone_from_start`;
`rsi_side50` (+1 / −1 / 0), held / since / from_start; `rsi_slope` (+1 rising / −1 falling / 0 flat vs previous)
and `rsi_slope_held`; `rsi_ma_side` (hidden).

**Events:**
- `zone_change` — RSI moved into a different zone (can skip zones in one candle); `zone_from`, `zone_change_up`.
  The first value after blanks is not a change.
- `rsi_cross_above_50` / `rsi_cross_below_50` — TradingView cross rule (50 itself is not "above"; 50 → 49.9 is a
  cross below).
- `rsi_ma_cross_above` / `rsi_ma_cross_below` — **recorded only** (hidden).

**Label:** the zone label (§4); blank RSI → `n/a (not enough history)` (fewer than 15 candles).
`rsi_all(df)` = compute_rsi → rsi_states → rsi_label.

---

## 6. Snapshot, texts and alerts (`rsi_snapshot.build_rsi_snapshot`)

One JSON‑safe package per timeframe + a summary line; never raises (a failed timeframe → `None` + reason).
Fixed templates.

**Zone‑change wording (Ash, 2026‑10‑13) — `rsi.zone_change_text()`, used by the manual check and the alerts:**
`RSI {value} {FROM} ({range}) {verb} into {TO} ({range})` — ranges written in the direction of the move
(falling 45–30, rising 30–45):

| Move | Lands in | Verb |
|---|---|---|
| Up | BULLISH, STRONG BULL, OVERBOUGHT | **rising strong up** |
| Up | RSI S&R ZONE, BEARISH, STRONG BEAR | **rising up** |
| Down | BEARISH, STRONG BEAR, OVERSOLD | **falling strong down** |
| Down | RSI S&R ZONE, BULLISH, STRONG BULL | **falling down** |

e.g. `RSI 26.44 BEARISH (45–30) falling strong down into STRONG BEAR (30–20)` · `RSI 54.81 BULLISH (70–55)
falling down into RSI S&R ZONE (55–45)` · `RSI 70.16 BULLISH (55–70) rising strong up into STRONG BULL (70–80)`.

**Dates read like a report, always with the year (Ash):** `Fri 9 Oct 2026` (1D, the last close — after the 4 pm
refresh that is today), `Fri 9 Oct 2026 15:25` (intraday), `Week of Mon 5 Oct 2026` (1W), `Oct 2026` (1M); the
running week / month adds `(week to date)` / `(month to date)`. (`indicator_common.text_format.report_date`.)

| Line (real, 9 Oct 2026) | When |
|---|---|
| `Nifty 50 · 1D RSI — Fri 9 Oct 2026: close 22,520.45` | always |
| `RSI 36.50 [yesterday: RSI 27.55]` — the TradingView number | always |
| `BEARISH (30–45) — RSI 36.50 rising for 1 day; below 50 since Wed 26 Aug 2026 (31 days).` | always (`RSI n/a (not enough history).` on short history) |
| `Fri 9 Oct 2026: RSI 36.50 STRONG BEAR (20–30) rising up into BEARISH (30–45)` | zone change on the latest candle — **alert** |
| `Fri 9 Oct 2026 15:25: RSI 44.95 crossed BELOW 50` | 50 cross on the latest candle — **alert** |
| `In BEARISH (30–45) for 5 weeks (since Week of Mon 7 Sep 2026), came from RSI S&R ZONE (45–55).` | zone 2–5 candles old, began with a change |
| `Bigger picture: in BULLISH (55–70) since Fri 9 Oct 2026 12:00 (14 candles).` | zone held > 5 candles |
| `RSI: 1M bearish 44.37 (falling) · 1W bearish 32.74 (rising) · 1D bearish 36.50 (rising) · 60m S&R zone 51.18 (falling) · 15m bullish 56.85 (falling) · 5m bearish 44.95 (falling)` | summary, once |

**Alerts:** every zone change and every 50 cross on the latest candle, all six timeframes, both directions, no
filter; each alert carries its sentence in `text`. RSI‑MA crosses: never texted / alerted.

**Package fields:** `instrument, timeframe, as_of, partial, previous, close{today, previous}, values{today,
previous}{rsi}, label, zone{key, label, held, since, from_start}, side50{side, held, since, from_start},
slope{direction, held}, events_today, last_events{zone_change, rsi_cross_above_50, rsi_cross_below_50}, alerts,
texts`. The hidden MA is **not** in the package.

---

## 7. Code map

All in `backend/modules/Module_F_Tech_Indicators_Funnel/oscillators/rsi/` (`oscillators/__init__.py` explains the
family; MACD stays in `trend_indicators/`). Imports only from `indicator_common/`.

| File / function | Does |
|---|---|
| `rsi.py` → `compute_rsi(df, length=14, ma_length=14)` | adds `rsi`, `rsi_ma`; pure; ValueError on bad input |
| `rsi.py` → `rsi_zone`, `rsi_states`, `rsi_label`, `rsi_all` | §4–5 |
| `rsi.py` → `zone_change_text(value, zone_from, zone_to)` | the alert sentence (§6) |
| `rsi.py` → `__main__` | `--timeframe {…,all} --domain --key --bars --dates --ohlc`, `--state` / `--crosses N` (one at a time) → screen + `logs/rsi_test_logs/rsi_check_<tf>.log` / `rsi_check_<tf>_<state|crosses>.log` |
| `rsi_snapshot.py` → `snapshot_from_bars`, `summary_line`, `build_rsi_snapshot` | §6; manual check → `logs/rsi_test_logs/rsi_snapshot.log` |
| `test_rsi.py` (63), `test_rsi_snapshot.py` (23), `conftest.py` | tests → `logs/rsi_test_logs/test_rsi.log` |
| `indicator_common/text_format.py` → `report_date` | report‑style dates (added for RSI, 5 tests) |

**Run** (from `backend/`):
```
python -m pytest modules/Module_F_Tech_Indicators_Funnel/oscillators/rsi -v
python -m modules.Module_F_Tech_Indicators_Funnel.oscillators.rsi.rsi --dates 2026-10-09
python -m modules.Module_F_Tech_Indicators_Funnel.oscillators.rsi.rsi --timeframe 60m --dates 2026-10-09 --ohlc
python -m modules.Module_F_Tech_Indicators_Funnel.oscillators.rsi.rsi --timeframe all --state
python -m modules.Module_F_Tech_Indicators_Funnel.oscillators.rsi.rsi --crosses 15 [--timeframe 5m]
python -m modules.Module_F_Tech_Indicators_Funnel.oscillators.rsi.rsi_snapshot [--timeframes 1d 60m] [--json]
```

---

## 8. Not used / deferred / open items

- **RSI ~55 at price S&R study** (§3.5) — Phase 6, needs price S&R (Phase 5) and the Nifty testing tool (Phase 4).
- **Smoothed MA as a signal** (§3.3) — hidden; test RSI‑MA crosses in Phase 4.
- **80/20 vs 70/30 and other lengths on Nifty** (§3.4, §3.6) — Phase 4.
- **Investor / India research pass** — Phase 3, for all indicators together after every indicator is built.
- **Divergence** — not offered in Ash's RSI settings (nothing to prove parity against).
- **2h / 4h** — with MACD / ADX open item. **Live intraday** — with MACD.
- **Snapshot for stocks:** `build_rsi_snapshot` reads 1d/1w/1mo from `indices` — add a domain option with the
  watchlist work (same as MACD / ADX). Manual checks take `--domain universe`.
- **Frontend:** final text layout and date style to be tuned when Ash sees labels and alerts on screen (e.g. the
  weekly date mid‑sentence reads `since Week of Mon 28 Sep 2026`).

---

## 9. Testing and verification

**Unit tests — 86 passing on Windows, 2026‑10‑13** (log `logs\rsi_test_logs\test_rsi.log`):

| Group | Tests | Why they pass |
|---|---|---|
| Formula | `test_matches_plain_pine_reference` (RSI and MA on a 300‑candle walk vs a separate plain loop of Pine's `ta.rsi` / `ta.sma`, 1e‑9), `test_hand_worked_3_rsi` (10, 11, 12, 11, 13 → 66.6667, 83.3333), `test_first_values_at_candles_15_and_28`, `test_only_gains_is_100_only_losses_is_0`, `test_flat_prices_give_100_like_pine`, `test_values_in_range_and_scale_free`, `test_rsi_ma_is_sma_of_rsi` | hand‑worked, independent loop, Pine's rules |
| Edges / contract | short history, non‑default index, input not modified, exact columns, validation ×4, unsorted | contract |
| Zones | `test_zone_edges` ×16 (every boundary incl. 0, 100), `test_zone_blank` | §4 |
| States / events | zone change from / held / since / direction, skip zones, first value after blanks, 50 cross rule, slope held, hidden MA cross | hand‑built series |
| Label | `test_rsi_label` ×8 (incl. Nifty daily 9 Oct 36.50 → BEARISH (30–45)), `test_rsi_all_on_walk` (visits all 7 zones; every change consistent) | §4–5 |
| Wording | `test_zone_change_text` ×12 — the exact sentences of the table Ash approved, `test_zone_change_text_rejects_non_changes` | §6 |
| Snapshot | header report dates ×4, numbers line, label line, zone change text + alert up / down, 50 cross text + alert above / below, event line date (daily, intraday with time), alerts = events (no filter), holding line names where it came from, bigger picture, hidden MA absent, short history, single bar, JSON safe, summary line, never‑raise ×2 | §6 |

Whole indicator suite on Windows 2026‑10‑13: **333 passed** (EMA 63, MACD 66, ADX 61, indicator_common 57, RSI 86).

---

## 10. Sample outputs and verification record

### 10.1 Values — see §3.2 (all six timeframes vs tv.dhan).

### 10.2 Zone‑change dates (checked on tv.dhan, 13 Oct 2026)

| Chart | Fortuna event | Chart (candle before → candle) | Result |
|---|---|---|---|
| 1D | 9 Sep 2026: BEARISH falling strong down into STRONG BEAR | → 26.44 | ✅ (8 Sep side not hovered; all other values exact) |
| 1D | 18 Sep 2026: STRONG BEAR rising up into BEARISH | 17 Sep 29.95 → 33.66 | ✅ |
| 1D | 12 Aug 2026: BULLISH falling down into RSI S&R ZONE | 11 Aug 56.10 → 54.81 | ✅ |
| 5m | 9 Oct 2026 09:25: BULLISH rising strong up into STRONG BULL | 09:20 61.29 → 70.16 | ✅ |

Plus from the value checks: 1D 8 Oct 27.55 → 9 Oct 36.50 (STRONG BEAR → BEARISH, today's alert); 5m 15:15 / 15:20
50.83 → 15:25 44.95 (S&R → BEARISH and cross below 50).

### 10.3 Known discrepancies

| Seen | Cause | Status |
|---|---|---|
| 60m 9 Oct 15:15 RSI MA 41.86 vs tv.dhan 41.85 (RSI itself exact) | rounding at the 2nd decimal (the MA averages 14 RSI values) | recorded, not hunted; MA is hidden |
| Loaded history / live forming candle | as `MACD.md` §3.5 / runbook §6.2 | read completed candles with history loaded |

### 10.4 Where Nifty stood, 9 Oct 2026 close (`rsi --timeframe all --state` / `rsi_snapshot`)

| TF | RSI | Zone | Held / note |
|---|---|---|---|
| 1M (month to date) | 44.37 | BEARISH | 2 months, falling 3 months |
| 1W (week to date) | 32.74 | BEARISH | 5 weeks, below 50 since week of 24 Aug |
| 1D | 36.50 | BEARISH | rose out of STRONG BEAR today; below 50 since 26 Aug (31 days) |
| 60m | 51.18 | RSI S&R ZONE | 7 candles |
| 15m | 56.85 | BULLISH | 14 candles |
| 5m | 44.95 | BEARISH | broke below 45 and 50 on the last candle |

Latest daily events (`rsi --crosses 15`): Aug: S&R / BEARISH flips around 45 and 50 crosses; 9 Sep into STRONG BEAR;
18 Sep back to BEARISH; 28 Sep STRONG BEAR; 6 Oct BEARISH; 8 Oct STRONG BEAR; 9 Oct BEARISH. 2,375 events in daily
history; 32,362 on 5m.

---

## 11. Change log

| Date | Change |
|---|---|
| 2026‑10‑13 | v1 — RSI parts 1–3 built: `compute_rsi` (TradingView `ta.rsi` via shared `rma_tradingview`, hidden SMA‑14 Smoothed MA), seven zones (80 / 70 / 55 / 45 / 30 / 20, 45–55 RSI S&R zone), states, zone changes and 50 crosses (both directions, no filter), Ash's direction‑and‑strength wording (`zone_change_text`), report‑style dates, snapshot + summary line, manual check (`--state`, `--crosses`, `--timeframe all`, `--ohlc`), logging to `logs/rsi_test_logs/`. Parity exact on all six timeframes (60m MA 0.01 rounding); 4 zone‑change dates on the chart. Research recorded: Smoothed MA, 80/20 vs 70/30, ~55 S&R, settings. New `oscillators/` family folder. Tests 86. |
