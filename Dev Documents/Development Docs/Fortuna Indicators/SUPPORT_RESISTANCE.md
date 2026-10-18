# SUPPORT_RESISTANCE — Fortuna Indicator Spec

**Status:** v1 (2026-10-18). Type 1 (horizontal S&R) built and checked against Ash's drawings on tv.dhan.co. Types 2 onward not started.
**Folder:** `backend/modules/Module_F_Tech_Indicators_Funnel/price_action/<type>/` (one subfolder per S&R type, reusing `price_action/swing_points/`, per the Indicators Runbook §10). Horizontal S&R: `price_action/horizontal_sr/`
**Timeframes:** 1M / 1W / 1D / 60m / 15m / 5m
**Scope:** Nifty 50 first, then watchlist stocks
**Fortuna principle:** TradingView parity + investor mentality + India-market findings, else TradingView default.
For S&R there is no TradingView indicator to match. Ash draws his own lines, so **his drawn lines on tv.dhan are the parity reference.**

---

## 1. What comes under S&R (the 11 types from research, 2026-10-18)

| # | Type | What it is | Status in Fortuna |
|---|---|---|---|
| 1 | Horizontal levels (static) | Lines through past swing highs / lows | **Built 2026-10-18** (`price_action/horizontal_sr/`, §4) |
| 2 | Trendlines | Sloping lines through rising lows / falling highs | **Sequence 3** |
| 3 | Channels and fan principle | A parallel line to a trendline; the fan of steeper lines from one major low (Murphy) | Study later. Builds on trendlines |
| 4 | Moving averages (dynamic S&R) | Price finding support/resistance at an MA | **Sequence 2 (EMA S&R)**. EMAs already built |
| 5 | Round numbers (psychological) | e.g. Nifty 24,000 / 24,500 / 25,000 | Study later |
| 6 | Pivot points (incl. CPR) | Levels computed from the prior period's H/L/C | Study later. CPR exists in Foundation Funnel PRE-4 |
| 7 | Prior period levels | Previous day / week / month high, low | **Part of #1 Horizontal:** previous day O/H/L/C are tags (PDO/PDH/PDL/PDC) on lines that match, not separate lines (Ash, 2026-10-18). Previous week / month levels not built |
| 8 | Fibonacci retracements | 38.2% / 50% / 61.8% of a swing | Study later |
| 9 | Pattern-based S&R | Triangles, channels, flags create their own S&R | Study later. Belongs to the chart-patterns stage |
| 10 | Volume profile | High-volume prices act as S&R | Study later. Nifty has no index volume from Upstox, so it cannot produce a value for Nifty today |
| 11 | VWAP | Volume-weighted average price as S&R | Study later. Already planned under volume indicators |

**Rules that apply to every type (from the books):**
- **Role reversal:** broken support tends to become resistance, and broken resistance tends to become support (Murphy).
- **Zones, not exact lines:** treating S&R as one exact price is called a common mistake.
- **Confluence:** a level is stronger when several types meet at the same price.
- **Higher timeframes weigh more.**

## 2. Build sequence (Ash, 2026-10-18)

1. Horizontal S&R (previous day O/H/L/C as tags on matching lines)
2. EMA S&R
3. Trendline S&R
4. Channels and fan (suggested, since it builds on trendlines)
5. Round numbers (suggested)
6. Pivots / CPR (suggested)
7. Fibonacci (suggested)
8. VWAP (suggested, together with the volume indicators)
9. Pattern-based S&R (suggested, with chart patterns)
10. Volume profile (suggested last; Nifty has no volume data)

Ash's rule: only #1–#3 are things he manages manually. **#4 onward are studied, discussed and decided one at a time. We cross that bridge when we come to it.**

## 3. Working steps per S&R type

1. Research (Rule #19): books → studies → Ash's observations → then finalize
2. Parity anchor: Ash's drawn lines on tv.dhan, checked on exact candles (weekday + year)
3. Plan before code (Rule #17): approach in 1–3 lines, Ash approves first
4. Baby steps (Rule #14): one part at a time, each verified on the chart
5. Location: own subfolder under `price_action/`. Reads stored candles only, never fetches. Applies the reader rules
6. Labels, not decisions: keep every true situation as a label, including low-weight ones. Trade decisions happen after all indicators are combined
7. Docs and commit once at the end. Every command logs to `logs/<name>_test_logs/`

---

## 4. Type 1 — Horizontal S&R

### 4.1 Research: books
- **Where levels come from:** prior peaks and valleys. Bulkowski adds round numbers, horizontal consolidation regions (prices that share tops/bottoms), and moving averages. ([Bulkowski SAR](https://thepatternsite.com/SAR.html))
- **Gaps:** Bulkowski tested gaps and found they don't work well as S&R. ([Bulkowski SAR](https://thepatternsite.com/SAR.html))
- **Tall candles:** Bulkowski found unusually tall candles show S&R only 39% of the time and calls it unclear. ([Bulkowski tall candle](https://thepatternsite.com/TallCandleSAR.html))
- **Zones:** a level should be treated as an approximate area, not a precise point. ([Narcouzi, S&C V.18:7](https://store.traders.com/v13034thestr.html))
- **Role reversal after a decisive break.** (Murphy, *Technical Analysis of the Financial Markets*, ch. 4)

### 4.2 Research: studies
- **Osler (NY Fed, FX intraday):** prices bounced off published levels 60.8% of the time vs 56.2% off random levels. The edge is real but small.
- **Chung & Bellotti 2021 (arXiv 2101.07410, intraday):** levels with more previous bounces are more likely to bounce again, and a level's bounce probability decays over time. ([arXiv](https://arxiv.org/pdf/2101.07410))
- **Zapranis & Tsinaslanidis 2012 (US stocks, 20 years daily):** a rule-based horizontal S&R detector built from swing points. Support levels predicted trend interruptions better than resistance, but did not beat buy-and-hold. ([Canterbury repository](https://repository.canterbury.ac.uk/item/871vw/identifying-and-evaluating-horizontal-support-and-resistance-levels-an-empirical-study-on-us-stock-markets))
- **Touch count is disputed:** the classical view says more touches make a level stronger. The liquidity view says each test uses up orders until the level breaks. Recency and the quality of each reaction matter as much as the count. ([LuxAlgo support level](https://www.luxalgo.com/library/concept/support-level.md))

### 4.3 Already in Fortuna that horizontal S&R can build on
- Zig Zag swings per timeframe (5%/10 for 1M/1W/1D; 1.25% 60m; 0.5% 15m; 0.2% 5m)
- Equal-swing tolerance per timeframe (5m 0.05%, 15m 0.10%, 60m 0.20%, 1D/1W/1M 0.50%)
- Level-break labels: attempt (wick) / break (close) / retest / held / failed / gap

### 4.4 Ash's observations (step 3 of Rule #19, 2026-10-18)
- **Goal:** draw correct horizontal lines on any timeframe, on any chart: Nifty, stocks, and options contract charts (call/put). He needs support and resistance levels on both the Nifty chart and the options chart.
- **Timeframes:** he draws horizontal S&R on every timeframe he uses (1M / 1W / 1D / 60m / 15m / 5m).
- **Zone, not a line.** The tolerance comes from books/studies (see 4.5). *Superseded by 4.6: lines only for now; Ash reads the zone by eye.*
- **Which levels are kept:**
  - 1D / 1W / 1M levels are kept.
  - 60m levels are kept from recent times only.
  - Lower timeframe levels (15m / 5m) are drawn fresh every day.
- **Previous period:** previous day / week / month high and low (as in the research). *Built as previous-day O/H/L/C tags only (4.6).*
- **Touches:** to him, multiple touches mean price is trying to break. Fortuna should only record the base facts: the level, how close price is, how many times price has touched it, and whether it broke. Meaning comes later when indicators are combined. No strength rule is coded. *Today the snapshot gives the level and distance; touch count and break are not built yet (open item, via the level-break engine).*
- His 1M method: horizontal levels from the lowest price upward.
- Intraday: S1 / R1 / R2 / R3 on the 5m chart are entries and bookings.

### 4.5 Zone tolerance research (2026-10-18)
- **Books / practice:** no fixed number. Width should grow with timeframe and volatility, and is often sanity-checked against ATR. Edges run from the extreme wick of the touches to the cluster of bodies. ([LuxAlgo S/R zone](https://www.luxalgo.com/library/concept/s-r-zone.md))
- **Studies (Garzarelli et al. 2014; Chung & Bellotti 2021):** half-width γ = the average absolute bar-to-bar price change of the series. On a random walk this gives a bounce probability of exactly 0.5, so it is a fair benchmark. A wider zone inflates bounce counts; a narrower one deflates them. ([arXiv 2101.07410](https://arxiv.org/pdf/2101.07410))
- **Common indicator practice:** zone = swing price ± ATR/2, using the ATR of the swing candle. ([LuxAlgo S/R Zone indicator](https://www.luxalgo.com/library/indicator/7AndUMz0-support-and-resistance-zone/))
- **Both methods are measured from the chart's own candles**, so they work the same on Nifty, stocks and option premiums. A fixed % (like our equal-swing tolerance) does not adapt across charts.
- Decision: no zones for now (4.6). Kept for when zones are coded.

### 4.6 Decisions (Ash, 2026-10-18)
- **Plan changed: no zones.** A horizontal line sits at every Zig Zag swing: the candle HIGH for a swing high, the candle LOW for a swing low. The zone research in 4.5 is kept for reference only.
- **Simplified further:** every Zig Zag point on every timeframe (1M/1W/1D/60m/15m/5m) is a horizontal line, including the latest unlocked point as the chart shows it.
- **Labels:** each line carries its timeframe, swing type (high/low), date-time and price. If a line's price equals the previous day's open/high/low/close, it also gets that label (PDO/PDH/PDL/PDC). Previous day OHLC is not added as separate lines.
- **Output:** S1 = nearest line below price, R1 = nearest line above price, on any chart.
- **Numbering (Option a):** each timeframe is numbered separately, outward from the current price: R1, R2, R3… above and S1, S2, S3… below, nearest first. A line exactly at price is labelled AT and not numbered.
- **Order of work:** (1) the module correctly identifies all horizontal lines on all timeframes; (2) Ash cross-checks them against his own drawings on tv.dhan; (3) the frontend shows Option (a) so he can read his S&R quickly while trading.

### 4.7 Decisions after the first chart cross-check (Ash, 2026-10-18 evening)
- **Cross-check result (data to Fri 16 Oct 2026):** every line Ash drew on 1M / 1W / 1D / 4h / 1h / 15m / 5m is a Fortuna Zig Zag line, to the paisa, except 22,840.30 (1h): a small sideways patch around Mon 28 – Tue 29 Sep 2026, not a swing turn (open item). After the rules below, two of his lines are listed under another line instead of standing alone:
  - 23,118.60 (low Tue 15 Sep 2026 15:25, 5m): outside the 5m recency window; 60m / 15m keep 23,116.10 (low Wed 16 Sep 2026), 2.50 pts away.
  - 24,774.30 (high Mon 3 Aug 2026) on 1D / 1W: merged into 24,857.75 by rule A (conflict below).
- **Recency ("lets try this"):** 1M / 1W / 1D keep all history. 60m and 15m keep lines whose pivot is in the last 25 trading days (5 weeks); 5m the last 3 trading days. Without it, the near 60m / 15m / 5m lines were old 2024–2025 swings (5m R1 was a Jan 2025 low).
- **Merge close lines, rule A:** lines within the timeframe's equal tolerance (5m 0.05%, 15m 0.10%, 60m 0.20%, 1D/1W/1M 0.50%) become one line.
  - All highs in the group → keep the highest. Ash: in a range he picks the highest high (26,373.20 over 26,277.35 / 26,325.80).
  - All lows → keep the lowest (22,179.90 over 22,182.55).
  - Highs and lows mixed (support turned resistance) → keep the earliest (23,056.40 over 23,059.45).
  - Ties keep the earliest. Absorbed lines are listed with the kept line, never lost.
- **Two fixes from the second run:**
  - Lines on opposite sides of price never merge. On 60m, 23,149.85 (above price) had merged into 23,116.10 (below).
  - A line equal to PDO / PDH / PDL / PDC never merges with another price, so the tag stays on the right line. Identical PD prices from several timeframes still combine.
- **Trading ladder (5m chart):** the lines of all timeframes merged again within 0.05% and numbered from the 5m close. Each line lists the timeframes it is on. R1 is the first profit booking, R2 the second target, R3 the final target; re-entry on the contract chart is at VWAP. Result on 16 Oct 2026: R1 23,149.85 (PDH), R2 23,162.70, matching Ash's 5m chart.
- **Conflict kept as option (a) for now:** rule A merges 24,774.30 (high Mon 3 Aug 2026, drawn by Ash) into 24,857.75 (high Thu 5 Dec 2024) on 1D / 1W. (a) Keep the true highest, 24,857.75 (**chosen**). (b) On 1D / 1W, let the highest / lowest rule look back a fixed period only (e.g. 12 months), so the recent 24,774.30 is kept. Ash draws within his visible range, which is closer to (b). **Switch the code to (b) if it proves right.**

### 4.8 Open items (horizontal S&R)
- Consolidation levels that are not swings (22,840.30 on 1h, Mon 28 – Tue 29 Sep 2026; Bulkowski's horizontal consolidation regions).
- Option (b) above.
- Zones in use: Ash reads prices near a line as "in the zone" by eye; the zone research in 4.5 is kept for when this is coded.
- Touch count and break per line (4.4), through the level-break engine.
- Previous week / month high and low (4.4) — only previous-day tags are built.
- Snapshot on the frontend (package ready, §4.9).

---

### 4.9 Code map — `price_action/horizontal_sr/`

| File | Main functions |
|---|---|
| `horizontal_sr.py` (pure) | `swing_lines`, `recent_since`, `keep_recent`, `pd_tags`, `merge_close_lines` (rule A + the two fixes), `number_lines`, `timeframe_lines` (one timeframe, not numbered), `horizontal_sr` (one timeframe, numbered), `trading_ladder`; settings `RECENT_TRADING_DAYS = {60m: 25, 15m: 25, 5m: 3}` |
| `horizontal_sr_check.py` | manual check: every timeframe's ladder with distance, swing, pivot candle, locked, PD tag, merged lines; then the TRADING LADDER with timeframes |
| `horizontal_sr_snapshot.py` | `snapshot_from_lines`, `summary_line`, `build_horizontal_sr_snapshot` (never raises) — JSON-safe package for the frontend |
| `test_horizontal_sr.py`, `test_horizontal_sr_snapshot.py` | 33 + 9 tests |

Inputs: `find_zigzag_swings` with `zigzag_settings` (deviation, depth, equal tolerance per timeframe); candles via `indicator_ohlcv_reader.read_for_indicators`; dates via `indicator_common.text_format.report_date`. Reads only; writes only its own logs. Works on any OHLCV series (Nifty, stocks, option contracts).

**Pipeline per timeframe:** Zig Zag swings → one line per swing (high = candle high, low = candle low) → recency → PD tags (latest daily candle O/H/L/C, exact at 2 decimals) → merge (rule A; never across price; PD lines never merge with another price) → number from the timeframe's latest close (R1 nearest above, S1 nearest below, AT at price). **Trading ladder:** all timeframes' merged lines → merged again within 0.05% → numbered from the 5m close; each line lists its timeframes.

**Snapshot package:** `ok, instrument, name, prev_day, views {trading, 1mo, 1w, 1d, 60m, 15m, 5m}, errors, summary, texts`. Each view: `title, as_of, close, resistances (R1 first), at_price, supports (S1 first), counts, texts` (+ `settings` per timeframe). Each line: `label, price, distance_pts, distance_pct, kind, timeframe, timeframes, pivot_time, pivot_text, is_locked, pd_tags, merged`. Texts show R3 · R2 · R1 and S1 · S2 · S3; the package holds every line. No alerts (touch / break of a line belongs to the level-break engine).

### 4.10 How to run (from `backend/`)
```
python -m modules.Module_F_Tech_Indicators_Funnel.price_action.horizontal_sr.horizontal_sr_check [--timeframe TF] [--show N] [--key KEY --daily-domain universe]
python -m modules.Module_F_Tech_Indicators_Funnel.price_action.horizontal_sr.horizontal_sr_snapshot [--json] [--key KEY --name NAME --daily-domain universe]
python -m modules.Module_F_Tech_Indicators_Funnel.price_action.horizontal_sr.test_horizontal_sr
python -m modules.Module_F_Tech_Indicators_Funnel.price_action.horizontal_sr.test_horizontal_sr_snapshot
```
Logs: `logs\horizontal_sr_test_logs\` — `horizontal_sr_check.log`, `horizontal_sr_snapshot.log`, `horizontal_sr_unit_tests.log`, `horizontal_sr_snapshot_unit_tests.log` (overwritten each run; first line = the command). Run the data refresh first (after 4 pm for today's close).

### 4.11 Tests — 42, all pass (Windows, 2026-10-18)

| File | Tests | Proves |
|---|---|---|
| `test_horizontal_sr.py` | 33 | one line per swing; line price = the swing candle's high / low on real Zig Zag output; numbering outward from close, top of chart first, AT at 2 decimals; equal prices stay separate; PD tags exact, missing field raises; recency counts trading days; rule A on Ash's examples (26,373.20, 22,179.90, 23,056.40); tolerance bounds the group width; never merging across price (real 60m case 23,149.85 / 23,116.10); PD lines never merged with another price, same-price PD lines combine across timeframes; trading ladder lists timeframes; naive and timezone-aware times mix; input not modified; bad close / missing columns raise; empty input |
| `test_horizontal_sr_snapshot.py` | 9 | nearest first on each side; text format R3 · R2 · R1 / S1 · S2 · S3; line fields; "no line" text; summary line; all seven views built and JSON-safe; never raises when the reader raises; a failed timeframe is reported and the rest still built |

### 4.12 Verification record (tv.dhan.co, Nifty 50, data to Fri 16 Oct 2026)

| What | Result |
|---|---|
| Ash's drawn lines on 1M / 1W / 1D / 4h / 1h / 15m / 5m (26,373.20 · 25,669.35 · 24,774.30 · 24,571.75 · 23,592.85 · 23,489.00 · 23,162.70 · 23,149.85 · 23,070.15 · 23,056.40 · 23,020.95 · 22,913.80 · 22,776.10 · 22,179.90 · 21,743.65 · 18,887.60 · 12,430.50 · 9,119.20 · 7,511.10 · 6,357.10 · 2,252.75) | every one is a Fortuna Zig Zag line, exact to the paisa (first check, before recency / merging) |
| 22,840.30 (1h) | not a swing — consolidation level, open item |
| 23,118.60 (low Tue 15 Sep 2026 15:25, 5m) | outside the 5m window (3 trading days); 60m / 15m line 23,116.10, 2.50 pts away |
| 24,774.30 (high Mon 3 Aug 2026) on 1D / 1W | merged into 24,857.75 by rule A — option (a) kept, (b) noted (§4.7) |
| Trading ladder vs Ash's 5m chart | R1 23,149.85 (PDH), R2 23,162.70 ✓; below price 23,116.10, 23,056.40, 23,020.95, 22,913.80 (PDL) present ✓; extra near lines are 5m swings of Thu 15 – Fri 16 Oct Ash did not draw (23,141.55, 23,087.35, 22,983.35, 22,950.00, 22,926.05, 22,894.15) |
| 60m after the fixes | R1 23,149.85 PDH, S1 23,116.10 (no tag) ✓ |
| Monthly Zig Zag 5 / 10 vs 10 / 10 | all of Ash's monthly lines appear with both; 10 / 10 only drops the small 2012–2013 swings; 5 / 10 kept |

**Snapshot, 16 Oct 2026:** `S&R: R1 23,149.85 PDH · S1 23,141.55 (trading ladder)`.

---

## 5. Type 2 — EMA S&R (not started)
## 6. Type 3 — Trendline S&R (not started)

---

## Sources
- [Bulkowski — Finding Support and Resistance](https://thepatternsite.com/SAR.html)
- [Bulkowski — Tall Candle S&R](https://thepatternsite.com/TallCandleSAR.html)
- [Chung & Bellotti 2021, arXiv 2101.07410](https://arxiv.org/pdf/2101.07410)
- [Zapranis & Tsinaslanidis 2012, Applied Financial Economics](https://repository.canterbury.ac.uk/item/871vw/identifying-and-evaluating-horizontal-support-and-resistance-levels-an-empirical-study-on-us-stock-markets)
- [Osler NY Fed study (quoted)](https://www.energyexch.com/thread/post/1776200)
- [LuxAlgo — Support Level](https://www.luxalgo.com/library/concept/support-level.md)
- [LuxAlgo — Round Numbers](https://www.luxalgo.com/library/concept/round-numbers.md)
- [Narcouzi — The Strength of Support and Resistance](https://store.traders.com/v13034thestr.html)
- [LuxAlgo — S/R Zone](https://www.luxalgo.com/library/concept/s-r-zone.md)
- [LuxAlgo — Support and Resistance Zone indicator](https://www.luxalgo.com/library/indicator/7AndUMz0-support-and-resistance-zone/)
- Garzarelli et al. 2014, *Memory effects in stock price dynamics: evidences of technical trading*, Scientific Reports 4, 4487 (zone width method, via Chung & Bellotti)
- Murphy, *Technical Analysis of the Financial Markets*, ch. 4 (support / resistance, role reversal, trendlines, fan principle)

---

## Change log
- **v1 — 2026-10-18.** Horizontal S&R built (`price_action/horizontal_sr/`): every Zig Zag swing a line, recency, rule A merge, never across price, PD lines kept, per-timeframe ladders + trading ladder, check, snapshot, 42 tests; checked against Ash's drawings (§4.7, §4.12). Folder corrected to `price_action/`.
- **v0.1 — 2026-10-18.** Scope (11 types), build sequence, research for horizontal S&R, Ash's observations, zone research.
