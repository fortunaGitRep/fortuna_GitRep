# Fortuna — Indicator Spec: Stochastic RSI

**What this doc is:** the single source of truth for how Fortuna calculates and reads Stochastic RSI — formula,
settings, zones, states, events, texts, how parity with TradingView was proven, the decisions Ash made, tests and
known discrepancies. Records only what **Fortuna** does. Same layout as `RSI.md`, stored in
`Dev Documents\Development Docs\Fortuna Indicators\`.

_Version 1 — 2026‑10‑13. **Stochastic RSI complete (parts 1–3): %K and %D, three zones on %K, states, zone changes
and %K/%D crosses, snapshot texts and alerts on all six timeframes; equal to TradingView (tv.dhan) on 1M / 1W / 1D /
60m / 15m / 5m (22 values).** Code: `backend/modules/Module_F_Tech_Indicators_Funnel/oscillators/stoch_rsi/`._

---

## 0. What Stochastic RSI is, how it works, how to read it (plain English)

**What it is.** Stochastic RSI (Tushar Chande and Stanley Kroll, *The New Technical Trader*, 1994) is **an indicator
of an indicator**: it takes the RSI and asks *where is today's RSI inside its own range of the last 14 candles?*
0 = RSI is at its 14‑candle low, 100 = at its 14‑candle high. Chande and Kroll built it because RSI can stay between
80 and 20 for long stretches without reaching an extreme; Stochastic RSI reaches its extremes much more often.

**How it works.**
1. Take the RSI (14, close) — the same RSI Fortuna already matches (`RSI.md`).
2. Over the last 14 RSI values find the highest and lowest. **raw = 100 × (RSI − lowest) ÷ (highest − lowest).**
3. **%K** = 3‑candle average of raw (the pink line on Ash's chart). **%D** = 3‑candle average of %K (the black line).

**How Fortuna reads it (Ash, 2026‑10‑13):**

| %K | Zone | Reads as |
|---|---|---|
| ≥ 80 | **OVERBOUGHT** | RSI near the top of its recent range |
| 20 – 80 | **MIDDLE** | in between |
| < 20 | **OVERSOLD** | RSI near the bottom of its recent range |

Events: every move of %K from one zone to another (= %K crossing 80 or 20) and every %K/%D cross, tagged with the zone
it happened in. A cross down inside OVERBOUGHT is the classic sell setup, a cross up inside OVERSOLD the classic buy
setup. When %K and %D are equal (e.g. both 100.00) Fortuna says so and reports no cross (§5).

Example (Nifty, 9 Oct 2026 close): 1D %K 56.04 / %D 56.31 — MIDDLE, %K crossed below %D today. 1W %K 2.43 / %D 0.81 —
OVERSOLD for 4 weeks, %K crossed above %D this week. 60m 96.77 / 97.82 — OVERBOUGHT, crossed below. 5m both 0.00 —
pinned at 0.

**Good at:** spotting short‑term momentum turns early; showing when RSI is stretched to the edge of its recent range.
**Weak at:** it is very fast and noisy (two steps away from price) — Nifty daily has 1,541 %K/%D crosses in 26 years,
one every ~4 days; it sits pinned at 0 or 100 for many candles in strong moves, and those readings are not reversal
signals by themselves. Published guidance (StockCharts) is to read it with the trend: in an uptrend look at oversold
readings, in a downtrend at overbought ones.

**How it fits:** EMA = direction, MACD = momentum, ADX = strength, RSI = momentum level, Stochastic RSI = where RSI
sits in its recent range (the fastest of the five).

---

## 1. Scope

| Item | Fortuna's choice |
|---|---|
| Instruments | **Nifty 50 now**; watchlist / options stocks later — same code. |
| Timeframes | **1M, 1W, 1D, 60m, 15m, 5m** (periods = candles). 2h / 4h = open item. |
| Settings | **LengthRSI 14 · LengthStoch 14 · SmoothK 3 · SmoothD 3 · source close** (Ash's tv.dhan dialog, 2026‑10‑13). Style: %K pink, %D black, Upper 80, Lower 20, background between them, no middle line. |
| Parity rule | Every TradingView number must equal Fortuna's (§3). |
| Reference chart | tv.dhan.co (Nifty); tv.upstox / pro.upstox (stocks). Legend `Stoch RSI 14 14 3 3  <%K>  <%D>`. |
| Display rule | %K and %D are always shown; zones, labels, texts are extra. The RSI it is built on and the unsmoothed value are calculated for checking only, not shown in texts. |
| Directions | **Both directions always, index and stocks alike — no filter** (same as RSI). |
| Reuse | The RSI comes from `oscillators/rsi/rsi.py` (`compute_rsi`, imported, not copied); other helpers from `indicator_common/` only. |

---

## 2. Input data

Same reader and rules as MACD / ADX / RSI (`MACD.md` §2): `indicator_ohlcv_reader.read_for_indicators()` — 1D/1W/1M
from `upstox/indices/Nifty_50.parquet`, 60m/15m/5m from `upstox/nse_indexes_intraday/Nifty_50.parquet`; reader rules
1–2; the latest weekly / monthly candle is "to date"; indicators never fetch data. **Close only.**

---

## 3. TradingView parity and research

### 3.1 TradingView's Stoch RSI (built‑in script)
```
rsi1 = ta.rsi(close, 14)
k    = ta.sma(ta.stoch(rsi1, rsi1, rsi1, 14), 3)
d    = ta.sma(k, 3)
ta.stoch(x, x, x, n) = 100 × (x − lowest(x, n)) ÷ (highest(x, n) − lowest(x, n))
```
The RSI is `compute_rsi` (proven exact, `RSI.md` §3.2). The window and both SMAs look back only 14 + 3 + 3 candles —
no extra "loaded history" effect beyond RSI's own Wilder average. **First values: RSI candle 15, raw candle 28, %K
candle 30, %D candle 32.**

### 3.2 Flat RSI window (range 0)
If the 14 RSI values in a window are all equal the formula divides by zero. Pine's documented rule is that an `na`
operand gives `na`, and division by zero gives `na` (third‑party Pine interpreter); TradingView does not document
the `ta.stoch` zero‑range case itself. **Fortuna: raw is blank (Pine `na`); %K is blank for the 3 candles whose
window contains it, %D for 5; values come back by themselves.**
**On real data it never happens** (`--flat`, 2026‑10‑13): no exactly‑flat and no near‑flat window on any timeframe.
Smallest RSI range in any window:

| TF | windows | flat | smallest range |
|---|---|---|---|
| 1M | 295 | 0 | 4.91 (Aug 2010) |
| 1W | 1,371 | 0 | 5.65 (week of 25 Feb 2019) |
| 1D | 6,630 | 0 | 5.98 (18 Sep 2007) |
| 60m | 8,222 | 0 | 3.90 (16 Apr 2025 15:15) |
| 15m | 29,428 | 0 | 3.13 (4 Dec 2023 13:15) |
| 5m | 88,422 | 0 | 1.59 (7 Mar 2022 10:20) |

### 3.3 How parity was proven (2026‑10‑13)
Ash read 15 values on tv.dhan; 7 more %K values follow from %D = average of the last three %K (±0.03 from rounding).
Fortuna's RSI column equalled `RSI.md`'s proven values on the same candles.

| Candle | tv.dhan %K / %D | Fortuna | |
|---|---|---|---|
| 1D Fri 7 Aug 2026 | 77.00 (implied) | 77.00 / 80.91 | ✅ |
| 1D Mon 10 Aug 2026 | 74.56 (implied) | 74.57 / 77.06 | ✅ |
| 1D Tue 11 Aug 2026 | 66.09 / 72.55 | 66.09 / 72.55 | ✅ |
| 1D Wed 12 Aug 2026 | 59.03 / 66.56 | 59.03 / 66.56 | ✅ |
| 1D Wed 9 Sep 2026 | 0.00 / 1.82 | 0.00 / 1.82 | ✅ |
| 1D Tue 15 Sep 2026 | 4.21 (implied) | 4.23 / 3.89 | ✅ |
| 1D Wed 16 Sep 2026 | 7.86 (implied) | 7.85 / 5.44 | ✅ |
| 1D Thu 17 Sep 2026 | 17.24 / 9.77 | 17.24 / 9.77 | ✅ |
| 1D Fri 18 Sep 2026 | 34.99 / 20.03 | 34.99 / 20.03 | ✅ |
| 1D Wed 7 Oct 2026 | 57.23 / 37.45 | 57.23 / 37.45 | ✅ |
| 1D Thu 8 Oct 2026 | 55.66 (implied) | 55.67 / 50.23 | ✅ |
| 1D Fri 9 Oct 2026 | 56.04 / 56.31 | 56.04 / 56.31 | ✅ |
| 1W week of Mon 28 Sep 2026 | −0.00 / 4.59 | 0.00 / 4.59 | ✅ (§3.5) |
| 1M Aug 2026 | 36.13 / 33.07 | 36.13 / 33.07 | ✅ |
| 1M Sep 2026 | 27.49 / 32.15 | 27.49 / 32.15 | ✅ |
| 60m Fri 9 Oct 2026 15:15 | 96.77 / 97.82 | 96.77 / 97.82 | ✅ |
| 15m Fri 9 Oct 2026 15:15 | 48.09 / 76.46 | 48.09 / 76.46 | ✅ |
| 5m Thu 8 Oct 2026 15:25 | 86.61 (implied) | 86.61 / 75.93 | ✅ |
| 5m Fri 9 Oct 2026 09:15 | 93.30 (implied) | 93.30 / 86.78 | ✅ |
| 5m Fri 9 Oct 2026 09:20 | 95.37 / 91.76 | 95.37 / 91.76 | ✅ |
| 5m Fri 9 Oct 2026 09:25 | 95.37 / 94.68 | 95.37 / 94.68 | ✅ |
| 5m Fri 9 Oct 2026 15:15 | 0.00 / 4.57 | 0.00 / 4.57 | ✅ |

Plus the equal‑lines check (§5): 1D Wed 5 Jul 2023 100.00 / 99.27 and Fri 7 Jul 2023 85.87 / 95.29 on tv.dhan = Fortuna.

### 3.4 What the bands and crosses mean (research, 2026‑10‑13)
- Origin and purpose: Chande & Kroll (1994) — RSI can stay between 80 and 20 for long periods; StochRSI raises
  sensitivity to produce more overbought / oversold readings ([StockCharts ChartSchool](https://chartschool.stockcharts.com/table-of-contents/technical-indicators-and-overlays/technical-indicators/stochrsi)).
- Bands 0.80 / 0.20 (80 / 20 on TradingView); signals: rising from below 20 to above 20 (buy, in an uptrend), falling
  from above 80 to below 80 (sell); moving back past the trigger line = failed signal; in a strong trend it can stay
  above 80 (or below 20) for a long time ([MultiCharts](https://www.multicharts.com/support/base/oscillators-gt-stoch-rsi/)).
- Read with the trend: in an uptrend oversold readings are preferred, overbought ones ignored (StockCharts).
- Two steps away from price, can briefly disconnect from it; main uses are crossovers and overbought / oversold
  ([TradingView help](https://in.tradingview.com/support/solutions/43000502333)).
- The %K / %D smoothing (3 / 3) is TradingView's addition; the 1994 original had none.
- Not built: divergence (not offered in Ash's settings, nothing to prove parity against). Investor / India research —
  Phase 3; testing 80/20, crosses by zone, lengths on Nifty — Phase 4.

### 3.5 TradingView's −0.00
When %K and %D sit at 0, TradingView sometimes shows **−0.00** (1W week of 28 Sep 2026). Mathematically raw can never
be below 0, so this is a float leftover of TradingView's running SMA sum. **Fortuna keeps the calculated values
untouched and prints 0.00** (`fmt2`); for parity −0.00 = 0.00.

### 3.6 Start of history (known unknown)
Fortuna is blank until 14 RSI values exist (strict window → first %K at candle 30). Whether TradingView's
`lowest`/`highest` skip the blank RSI candles at the very start is not documented; it can only change the first
~30 candles of an instrument (new listings), never Nifty's current values. Recorded, not hunted.

---

## 4. Zones (Ash, 2026‑10‑13)

| %K | Key (`srsi_zone`) | Label |
|---|---|---|
| ≥ 80 | `overbought` | OVERBOUGHT (>80) |
| 20 – < 80 | `middle` | MIDDLE (20–80) |
| < 20 | `oversold` | OVERSOLD (<20) |

80 and 20 belong to the zone above them (as RSI). The zone is decided by **%K** (it moves first; %D is its average).
No middle (50) line — matches Ash's chart. Every boundary is a unit test.

---

## 5. States, events, label (`srsi_states`, `srsi_label`)

**States per candle:** `srsi_zone`, `srsi_zone_held` (first candle = 1), `srsi_zone_since`, `srsi_zone_from_start`;
`srsi_kd_side` (+1 %K above %D, −1 below, 0 equal), held / since / from_start; `srsi_slope` (+1 rising / −1 falling
/ 0 flat) and `srsi_slope_held`; `srsi_pinned` (+1 at 100, −1 at 0, 0 neither) and `srsi_pinned_held`.

**Events:**
- `srsi_zone_change` — %K moved into a different zone (= crossed 80 or 20; can jump OVERBOUGHT ↔ OVERSOLD in one
  candle); `srsi_zone_from`, `srsi_zone_change_up`. The first value after blanks is not a change.
- `srsi_kd_cross_above` / `srsi_kd_cross_below` — %K crossing %D, TradingView cross rule; `srsi_kd_cross_zone` = %K's
  zone on that candle.

**%K equal to %D (Ash, 2026‑10‑13): "if it's 100.00 100.00 then just say that with no cross above or cross down."**
When %K and %D are equal Fortuna shows "%K equal to %D" and reports no cross; the cross is reported on the candle
where they separate. "Equal" = closer than `CROSS_TOL = 1e‑9`, i.e. only float leftovers.
*Why it was needed:* %K and %D often sit together at 100 or 0, where they differ only by ~1e‑14. TradingView's raw
rule then marks a "cross" on a candle where both read 100.00 (and sometimes a cross below and straight back above
while nothing moved). TradingView's own leftovers won't match Fortuna's digit for digit, so the raw rule could not
give parity there anyway. Seen on the chart: 1D Wed 5 Jul 2023 100.00 / 99.27, Thu 6 Jul 100.00 / 100.00 (equal, no
cross), Fri 7 Jul 85.87 / 95.29 (cross below reported here — where the lines visibly separate).
Effect on Nifty (`--crosscheck`, raw rule vs equal‑means‑no‑cross):

| TF | crosses, raw | crosses, Fortuna | candles only raw | candles only Fortuna |
|---|---|---|---|---|
| 1M | 68 | 68 | 0 | 0 |
| 1W | 313 | 312 | 1 | 0 |
| 1D | 1,548 | 1,541 | 11 | 4 |
| 60m | 1,930 | 1,919 | 14 | 3 |
| 15m | 7,106 | 7,094 | 19 | 7 |
| 5m | 21,526 | 21,492 | 160 | 126 |

All differences are at the 0 / 100 extremes; every %K and %D value is unchanged.
Slope and pinned use the same tiny tolerance (`FLAT_TOL = 1e‑9`), so leftovers never show as rising / falling or
break a pinned run.

**Label:** the zone label (§4); blank %K → `n/a (not enough history)` (fewer than 30 candles).
`srsi_all(df)` = compute_stoch_rsi → srsi_states → srsi_label.

---

## 6. Snapshot, texts and alerts (`stoch_rsi_snapshot.build_stoch_rsi_snapshot`)

One JSON‑safe package per timeframe + a summary line; never raises (a failed timeframe → `None` + reason). Fixed
templates, same layout and report‑style dates as RSI (`Fri 9 Oct 2026`, `Fri 9 Oct 2026 15:25`, `Week of Mon 5 Oct
2026`, `Oct 2026`; running week / month marked "(week / month to date)").

**Wording (Ash, 2026‑10‑13):**
- zone change — `%K 83.12 MIDDLE (20–80) rising into OVERBOUGHT (>80)` · `%K 18.40 MIDDLE (80–20) falling into
  OVERSOLD (<20)` (ranges in the direction of the move);
- %K / %D cross — `%K crossed below %D in OVERBOUGHT (%K 91.20, %D 93.05)`.

| Line (real, 9 Oct 2026) | When |
|---|---|
| `Nifty 50 · 1D Stoch RSI — Fri 9 Oct 2026: close 22,520.45` | always |
| `%K 56.04 · %D 56.31 [yesterday: %K 55.67 · %D 50.23]` — the TradingView numbers | always |
| `MIDDLE (20–80) — %K rising for 1 day; %K below %D since Fri 9 Oct 2026 (1 day).` (adds `%K pinned at 0 for 4 candles` when pinned; `%K equal to %D` when equal) | always (`%K n/a (not enough history).` on short history) |
| `Fri 9 Oct 2026: %K crossed below %D in MIDDLE (%K 56.04, %D 56.31)` | %K/%D cross on the latest candle — **alert** |
| `Fri 9 Oct 2026 15:15: %K 48.09 OVERBOUGHT (>80) falling into MIDDLE (80–20)` | zone change on the latest candle — **alert** |
| `In MIDDLE (20–80) for 4 days (since Tue 6 Oct 2026), came from OVERSOLD (<20).` | zone 2–5 candles old, began with a change |
| `Bigger picture: in … since … (N candles).` | zone held > 5 candles |
| `Stoch RSI: 1M oversold 14.88 · 1W oversold 2.43 · 1D middle 56.04 · 60m overbought 96.77 · 15m middle 48.09 · 5m oversold 0.00` | summary (%K), once |

**Alerts:** every zone change and every %K/%D cross on the latest candle, all six timeframes, both directions, no
filter; each alert carries its sentence in `text`. No alert when %K equals %D.

**Package fields:** `instrument, timeframe, as_of, partial, previous, close{today, previous}, values{today, previous}
{k, d}, label, zone{key, label, held, since, from_start}, kd{side, held, since, from_start}, slope{direction, held},
pinned{at, held}, events_today, last_events{zone_change, kd_cross_above, kd_cross_below}, alerts, texts`.

---

## 7. Code map

All in `backend/modules/Module_F_Tech_Indicators_Funnel/oscillators/stoch_rsi/`. Imports `compute_rsi` from
`oscillators/rsi/rsi.py` and helpers from `indicator_common/` only.

| File / function | Does |
|---|---|
| `stoch_rsi.py` → `compute_stoch_rsi(df, rsi_length=14, stoch_length=14, smooth_k=3, smooth_d=3)` | adds `srsi_rsi`, `srsi_raw`, `srsi_k`, `srsi_d`; pure; ValueError on bad input |
| `stoch_rsi.py` → `stoch_from_rsi(rsi, …)` | the Stochastic part on an RSI series → (raw, %K, %D) |
| `stoch_rsi.py` → `srsi_zone`, `srsi_states`, `srsi_label`, `srsi_all`, `kd_crosses` | §4–5 (`CROSS_TOL`, `FLAT_TOL`) |
| `stoch_rsi.py` → `zone_change_text`, `kd_cross_text`, `fmt2` | the alert sentences; 2‑decimal printing (−0.00 → 0.00) |
| `stoch_rsi.py` → `flat_windows`, `compare_cross_rules` | diagnostics for `--flat` and `--crosscheck` |
| `stoch_rsi.py` → `__main__` | `--timeframe {…,all} --domain --key --bars --dates --ohlc`, one of `--state` / `--crosses N` / `--flat` / `--crosscheck` → screen + `logs/stoch_rsi_test_logs/stoch_rsi_check_<tf>[_<mode>].log` |
| `stoch_rsi_snapshot.py` → `snapshot_from_bars`, `summary_line`, `build_stoch_rsi_snapshot` | §6; manual check → `logs/stoch_rsi_test_logs/stoch_rsi_snapshot.log` |
| `test_stoch_rsi.py` (73), `test_stoch_rsi_snapshot.py` (24), `conftest.py` | tests → `logs/stoch_rsi_test_logs/test_stoch_rsi.log` |

**Run** (from `backend/`):
```
python -m pytest modules/Module_F_Tech_Indicators_Funnel/oscillators/stoch_rsi -v
python -m modules.Module_F_Tech_Indicators_Funnel.oscillators.stoch_rsi.stoch_rsi --dates 2026-10-09
python -m modules.Module_F_Tech_Indicators_Funnel.oscillators.stoch_rsi.stoch_rsi --timeframe 60m --dates 2026-10-09 --ohlc
python -m modules.Module_F_Tech_Indicators_Funnel.oscillators.stoch_rsi.stoch_rsi --timeframe all --state
python -m modules.Module_F_Tech_Indicators_Funnel.oscillators.stoch_rsi.stoch_rsi --crosses 15 [--timeframe 5m]
python -m modules.Module_F_Tech_Indicators_Funnel.oscillators.stoch_rsi.stoch_rsi --timeframe all --flat
python -m modules.Module_F_Tech_Indicators_Funnel.oscillators.stoch_rsi.stoch_rsi --timeframe all --crosscheck
python -m modules.Module_F_Tech_Indicators_Funnel.oscillators.stoch_rsi.stoch_rsi_snapshot [--timeframes 1d 60m] [--json]
```

---

## 8. Not used / deferred / open items

- **Testing the readings on Nifty** (80/20, crosses inside OVERBOUGHT / OVERSOLD vs MIDDLE, crosses with the trend,
  lengths) — Phase 4 Nifty testing tool. **Investor / India research pass** — Phase 3.
- **Divergence** — not offered in Ash's settings (nothing to prove parity against).
- **2h / 4h** and **live intraday** — with the MACD / ADX / RSI open items.
- **Snapshot for stocks:** `build_stoch_rsi_snapshot` reads 1d/1w/1mo from `indices` — add a domain option with the
  watchlist work (same as MACD / ADX / RSI). Manual checks take `--domain universe`.
- **Frontend:** text layout to be tuned when Ash sees labels and alerts on screen (as RSI).
- Start of history (§3.6) — known unknown, recorded.

---

## 9. Testing and verification

**Unit tests — 97 passing on Windows, 2026‑10‑13** (log `logs\stoch_rsi_test_logs\test_stoch_rsi.log`):

| Group | Tests | Why they pass |
|---|---|---|
| Formula | `test_matches_plain_pine_reference` (RSI, raw, %K, %D on a 300‑candle walk vs a separate plain loop of Pine's `ta.rsi` / `ta.stoch` / `ta.sma`, 1e‑9), `test_custom_lengths_match_reference`, `test_hand_worked_window` (RSI 10, 20, 30, 25 → 100, 50), `test_hand_worked_flat_window_is_blank_then_recovers`, `test_first_values_at_candles_15_28_30_32`, `test_rsi_column_is_compute_rsi` (reuse), `test_d_is_sma3_of_k`, `test_values_in_range`, `test_scale_free` | hand‑worked, independent loop, Pine's rules |
| Edges / contract | flat prices all blank (Pine RSI 100 → range 0), short history, non‑default index, input not modified, exact columns, validation ×6, missing price column, unsorted, non‑Series | contract |
| Printing / diagnostics | `test_fmt2` ×7 (−1e‑15 and −0.0 → 0.00), `test_flat_windows_*` ×3 | §3.2, §3.5 |
| Zones | `test_zone_edges` ×8 (every boundary), `test_zone_blank` | §4 |
| States / events | zone change from / held / since / direction, skip MIDDLE, %K/%D cross rule and zone tag, crosses in OVERBOUGHT / OVERSOLD, side held / since, raw rule vs tolerance, **equal lines no cross until they separate** (the 5–7 Jul 2023 case), slope ignores leftovers, pinned at 100 / 0, blanks | hand‑built series |
| Label / wording | `test_srsi_label` ×6 (incl. 1D 9 Oct 56.04 → MIDDLE, 60m 96.77 → OVERBOUGHT), `test_zone_change_text` ×5 + rejects, `test_kd_cross_text` | §4–6 |
| Consistency / validation | `test_srsi_all_on_walk_is_consistent`, input not modified, missing columns, unsorted, bad `cross_tol` ×4 | contract |
| Snapshot (24) | header ×4 (report dates, week / month to date), numbers line = `compute_stoch_rsi`, state line, zone‑change text + alert, %K/%D cross text + alert both directions, alerts = events (no filter), intraday time in event lines, no event → no alert, holding line names where it came from, bigger picture, pinned text / none, short history, single bar, JSON safe, summary line order + n/a, bad inputs raise, `build` never raises ×3 (all ok; one missing / one exception, others still built; bad timeframe) | §6; events tested by cutting history right after an event |

Whole indicator suite: **430** (EMA 63, MACD 66, ADX 61, indicator_common 57, RSI 86, Stoch RSI 97).

---

## 10. Sample outputs and verification record

### 10.1 Values — §3.3 (22 values, all six timeframes, vs tv.dhan).

### 10.2 Where Nifty stood, 9 Oct 2026 close (`stoch_rsi --timeframe all --state` / `stoch_rsi_snapshot`)

| TF | %K / %D | Zone | Note |
|---|---|---|---|
| 1M (month to date) | 14.88 / 26.17 | OVERSOLD | fell into OVERSOLD this month; %K below %D since Sep 2026 |
| 1W (week to date) | 2.43 / 0.81 | OVERSOLD | 4 weeks; %K crossed above %D this week |
| 1D | 56.04 / 56.31 | MIDDLE | 4 days (from OVERSOLD on 6 Oct); %K crossed below %D today |
| 60m 15:15 | 96.77 / 97.82 | OVERBOUGHT | 5 candles; %K crossed below %D on the last candle |
| 15m 15:15 | 48.09 / 76.46 | MIDDLE | fell out of OVERBOUGHT on the last candle |
| 5m 15:25 | 0.00 / 0.00 | OVERSOLD | %K equal to %D, pinned at 0 for 4 candles, no alert |

Latest daily events (`--crosses 15`): 20 Aug cross above in OVERSOLD · 24 Aug into MIDDLE · 27 Aug cross below ·
31 Aug into OVERSOLD · 7, 9, 10 Sep crosses inside OVERSOLD · 18 Sep into MIDDLE · 23 Sep into OVERBOUGHT · 24 Sep back
to MIDDLE · 25 Sep cross below · 1 Oct into OVERSOLD · 6 Oct into MIDDLE + cross above · 9 Oct cross below.
2,813 events in daily history; 38,659 on 5m.

### 10.3 Known discrepancies

| Seen | Cause | Status |
|---|---|---|
| TradingView −0.00, Fortuna 0.00 | float leftover in TradingView's SMA (§3.5) | by design |
| A %K/%D cross on TradingView's maths one candle earlier than Fortuna, where both lines read the same | equal lines = no cross (§5) | by design (Ash) |
| First ~30 candles of a new listing | start‑of‑history behaviour not documented (§3.6) | recorded |

---

## 11. Change log

| Date | Change |
|---|---|
| 2026‑10‑13 | v1 — Stochastic RSI parts 1–3 built: `compute_stoch_rsi` (TradingView built‑in on the reused `compute_rsi`), flat window = blank (never occurs on Nifty), −0.00 printed as 0.00, three zones on %K (80 / 20), zone changes and %K/%D crosses tagged with zone (both directions, no filter), equal %K/%D = no cross (Ash), slope / pinned, snapshot + summary line, manual check (`--state`, `--crosses`, `--flat`, `--crosscheck`, `--timeframe all`, `--ohlc`), logging to `logs/stoch_rsi_test_logs/`. Parity exact on all six timeframes (22 values). Tests 97. |
