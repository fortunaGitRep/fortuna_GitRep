# SUPPORT_RESISTANCE — Fortuna Indicator Spec

**Status:** v1.3 (2026-10-26). Type 1 (horizontal S&R lines) built and checked against Ash's drawings on tv.dhan.co; rule A by side of price (2026-10-23). **Horizontal S&R zones** built as a separate layer (`hsr_zones.py`, books + studies) and checked on 7 days of 5m; **stopped with open items** (§4.13). Type 2 (EMA S&R) studied on Nifty history: EMAs are **not** S&R on Nifty → built instead as the EMA break watch (`EMA_BREAK.md`). Type 3 (trendlines): own document **`TRENDLINES.md`** (split out 2026-10-26). Open questions on zones in §4.13.
**Folder:** `backend/modules/Module_F_Tech_Indicators_Funnel/price_action/<type>/` (one subfolder per S&R type, reusing `price_action/swing_points/`, per the Indicators Runbook §10). Horizontal S&R: `price_action/horizontal_sr/`
**Timeframes:** 1M / 1W / 1D / 60m / 15m / 5m
**Scope:** Nifty 50 first, then watchlist stocks
**Fortuna principle:** TradingView parity + investor mentality + India-market findings, else TradingView default.
For S&R there is no TradingView indicator to match. Ash draws her own lines, so **her drawn lines on tv.dhan are the parity reference.**

---

## 1. What comes under S&R (the 11 types from research, 2026-10-18)

| # | Type | What it is | Status in Fortuna |
|---|---|---|---|
| 1 | Horizontal levels (static) | Lines through past swing highs / lows | **Built 2026-10-18** (`price_action/horizontal_sr/`, §4); zones built 2026-10-26 as a separate layer, stopped with open items (§4.13) |
| 2 | Trendlines | Sloping lines through rising lows / falling highs | **Manual checks:** chain check 2026-10-23 (`trendline_check.py`; 1 of 10 days right); Ash's 17-step drawing on every timeframe 2026-10-26 (`trendline_draw.py` + `trendline_confluence.py`). All in **`TRENDLINES.md`**. Entries / exits on the new lines, then the module |
| 3 | Channels and fan principle | A parallel line to a trendline; the fan of steeper lines from one major low (Murphy) | Study later. Builds on trendlines |
| 4 | Moving averages (dynamic S&R) | Price finding support/resistance at an MA | **Studied 2026-10-19 (§5): not S&R on Nifty.** Built as the EMA break watch (`EMA_BREAK.md`), not as S&R lines |
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
2. EMA S&R — studied 2026-10-19: not S&R on Nifty; became the EMA break watch (§5)
3. Trendline S&R
4. Channels and fan (suggested, since it builds on trendlines)
5. Round numbers (suggested)
6. Pivots / CPR (suggested)
7. Fibonacci (suggested)
8. VWAP (suggested, together with the volume indicators)
9. Pattern-based S&R (suggested, with chart patterns)
10. Volume profile (suggested last; Nifty has no volume data)

Ash's rule: only #1–#3 are things she manages manually. **#4 onward are studied, discussed and decided one at a time. We cross that bridge when we come to it.**

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
- **Goal:** draw correct horizontal lines on any timeframe, on any chart: Nifty, stocks, and options contract charts (call/put). She needs support and resistance levels on both the Nifty chart and the options chart.
- **Timeframes:** she draws horizontal S&R on every timeframe she uses (1M / 1W / 1D / 60m / 15m / 5m).
- **Zone, not a line.** The tolerance comes from books/studies (see 4.5). *Superseded by 4.6: lines only for now; Ash reads the zone by eye.*
- **Which levels are kept:**
  - 1D / 1W / 1M levels are kept.
  - 60m levels are kept from recent times only.
  - Lower timeframe levels (15m / 5m) are drawn fresh every day.
- **Previous period:** previous day / week / month high and low (as in the research). *Built as previous-day O/H/L/C tags only (4.6).*
- **Touches:** to her, multiple touches mean price is trying to break. Fortuna should only record the base facts: the level, how close price is, how many times price has touched it, and whether it broke. Meaning comes later when indicators are combined. No strength rule is coded. *Today the snapshot gives the level and distance; touch count and break are not built yet (open item, via the level-break engine).*
- Her 1M method: horizontal levels from the lowest price upward.
- Intraday: S1 / R1 / R2 / R3 on the 5m chart are entries and bookings.

### 4.5 Zone tolerance research (2026-10-18)
- **Books / practice:** no fixed number. Width should grow with timeframe and volatility, and is often sanity-checked against ATR. Edges run from the extreme wick of the touches to the cluster of bodies. ([LuxAlgo S/R zone](https://www.luxalgo.com/library/concept/s-r-zone.md))
- **Studies (Garzarelli et al. 2014; Chung & Bellotti 2021):** half-width γ = the average absolute bar-to-bar price change of the series. On a random walk this gives a bounce probability of exactly 0.5, so it is a fair benchmark. A wider zone inflates bounce counts; a narrower one deflates them. ([arXiv 2101.07410](https://arxiv.org/pdf/2101.07410))
- **Common indicator practice:** zone = swing price ± ATR/2, using the ATR of the swing candle. ([LuxAlgo S/R Zone indicator](https://www.luxalgo.com/library/indicator/7AndUMz0-support-and-resistance-zone/))
- **Both methods are measured from the chart's own candles**, so they work the same on Nifty, stocks and option premiums. A fixed % (like our equal-swing tolerance) does not adapt across charts.
- Decision: no zones for now (4.6). Kept for when zones are coded.

### 4.6 Decisions (Ash, 2026-10-18)
- **Plan changed: no zones.** A horizontal line sits at every Zig Zag swing: the candle HIGH for a swing high, the candle LOW for a swing low. The zone research in 4.5 is kept for reference only. *Later (2026-10-26): zones built as a separate layer on top of the lines (§4.13); the lines are unchanged.*
- **Simplified further:** every Zig Zag point on every timeframe (1M/1W/1D/60m/15m/5m) is a horizontal line, including the latest unlocked point as the chart shows it.
- **Labels:** each line carries its timeframe, swing type (high/low), date-time and price. If a line's price equals the previous day's open/high/low/close, it also gets that label (PDO/PDH/PDL/PDC). Previous day OHLC is not added as separate lines.
- **Output:** S1 = nearest line below price, R1 = nearest line above price, on any chart.
- **Numbering (Option a):** each timeframe is numbered separately, outward from the current price: R1, R2, R3… above and S1, S2, S3… below, nearest first. A line exactly at price is labelled AT and not numbered.
- **Order of work:** (1) the module correctly identifies all horizontal lines on all timeframes; (2) Ash cross-checks them against her own drawings on tv.dhan; (3) the frontend shows Option (a) so she can read her S&R quickly while trading.

### 4.7 Decisions after the first chart cross-check (Ash, 2026-10-18 evening)
- **Cross-check result (data to Fri 16 Oct 2026):** every line Ash drew on 1M / 1W / 1D / 4h / 1h / 15m / 5m is a Fortuna Zig Zag line, to the paisa, except 22,840.30 (1h): a small sideways patch around Mon 28 – Tue 29 Sep 2026, not a swing turn (open item). After the rules below, two of her lines are listed under another line instead of standing alone:
  - 23,118.60 (low Tue 15 Sep 2026 15:25, 5m): outside the 5m recency window; 60m / 15m keep 23,116.10 (low Wed 16 Sep 2026), 2.50 pts away.
  - 24,774.30 (high Mon 3 Aug 2026) on 1D / 1W: merged into 24,857.75 by rule A (conflict below).
- **Recency ("lets try this"):** 1M / 1W / 1D keep all history. 60m and 15m keep lines whose pivot is in the last 25 trading days (5 weeks); 5m the last 3 trading days. Without it, the near 60m / 15m / 5m lines were old 2024–2025 swings (5m R1 was a Jan 2025 low).
- **Merge close lines, rule A:** lines within the timeframe's equal tolerance (5m 0.05%, 15m 0.10%, 60m 0.20%, 1D/1W/1M 0.50%) become one line.
  - All highs in the group → keep the highest. Ash: in a range she picks the highest high (26,373.20 over 26,277.35 / 26,325.80).
  - All lows → keep the lowest (22,179.90 over 22,182.55).
  - Highs and lows mixed (support turned resistance) → **changed 2026-10-23 (Ash): by side of price** — a group below price (support) keeps its **lowest swing low**, a group above price (resistance) keeps its **highest swing high**; only a group with no close given (or at price) keeps the earliest. Ash's example: 23,059.45 (low) over 23,056.40 (high) as support on 19 Oct. *(Was: mixed → earliest, 23,056.40 over 23,059.45.)*
  - Ties keep the earliest. Absorbed lines are listed with the kept line, never lost.
- **Two fixes from the second run:**
  - Lines on opposite sides of price never merge. On 60m, 23,149.85 (above price) had merged into 23,116.10 (below).
  - A line equal to PDO / PDH / PDL / PDC never merges with another price, so the tag stays on the right line. Identical PD prices from several timeframes still combine.
- **Trading ladder (5m chart):** the lines of all timeframes merged again within 0.05% and numbered from the 5m close. Each line lists the timeframes it is on. R1 is the first profit booking, R2 the second target, R3 the final target; re-entry on the contract chart is at VWAP. Result on 16 Oct 2026: R1 23,149.85 (PDH), R2 23,162.70, matching Ash's 5m chart.
- **Conflict kept as option (a) for now:** rule A merges 24,774.30 (high Mon 3 Aug 2026, drawn by Ash) into 24,857.75 (high Thu 5 Dec 2024) on 1D / 1W. (a) Keep the true highest, 24,857.75 (**chosen**). (b) On 1D / 1W, let the highest / lowest rule look back a fixed period only (e.g. 12 months), so the recent 24,774.30 is kept. Ash draws within her visible range, which is closer to (b). **Switch the code to (b) if it proves right.**

### 4.8 Open items (horizontal S&R)
- Consolidation levels that are not swings (22,840.30 on 1h, Mon 28 – Tue 29 Sep 2026; Bulkowski's horizontal consolidation regions).
- Option (b) above.
- Zones: built 2026-10-26 as a separate layer (`hsr_zones.py`, §4.13), stopped with open items there.
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
| `test_horizontal_sr.py`, `test_horizontal_sr_snapshot.py` | 38 + 9 tests |
| `hsr_zones.py` (pure, new 2026-10-26) | zones (§4.13): `depth_limits`, `swing_zones`, `same_turns`, `merge_zones`, `zone_breaks`, `number_zones`, `hsr_zones`; settings `GAMMA_WINDOW = 20`, `ATR_WINDOW = 14`, `BAR_SPAN` |
| `hsr_zones_check.py` (new 2026-10-26) | manual check: zones on the 5m chart, last 7 days, each day's zones known at 09:15; log + chart. Reuses `candles_at` / `data_check` from `trendlines/trendline_draw.py` and `_swings` / `WARMUP_CANDLES` from `trendline_check.py` (manual-check helpers; `hsr_zones.py` itself imports only `horizontal_sr.py`) |
| `test_hsr_zones.py` (new 2026-10-26) | 18 tests |

Inputs: `find_zigzag_swings` with `zigzag_settings` (deviation, depth, equal tolerance per timeframe); candles via `indicator_ohlcv_reader.read_for_indicators`; dates via `indicator_common.text_format.report_date`. Reads only; writes only its own logs. Works on any OHLCV series (Nifty, stocks, option contracts).

**Pipeline per timeframe:** Zig Zag swings → one line per swing (high = candle high, low = candle low) → recency → PD tags (latest daily candle O/H/L/C, exact at 2 decimals) → merge (rule A; never across price; PD lines never merge with another price) → number from the timeframe's latest close (R1 nearest above, S1 nearest below, AT at price). **Trading ladder:** all timeframes' merged lines → merged again within 0.05% → numbered from the 5m close; each line lists its timeframes.

**Snapshot package:** `ok, instrument, name, prev_day, views {trading, 1mo, 1w, 1d, 60m, 15m, 5m}, errors, summary, texts`. Each view: `title, as_of, close, resistances (R1 first), at_price, supports (S1 first), counts, texts` (+ `settings` per timeframe). Each line: `label, price, distance_pts, distance_pct, kind, timeframe, timeframes, pivot_time, pivot_text, is_locked, pd_tags, merged`. Texts show R3 · R2 · R1 and S1 · S2 · S3; the package holds every line. No alerts (touch / break of a line belongs to the level-break engine).

### 4.10 How to run (from `backend/`)
```
python -m modules.Module_F_Tech_Indicators_Funnel.price_action.horizontal_sr.horizontal_sr_check [--timeframe TF] [--show N] [--key KEY --daily-domain universe]
python -m modules.Module_F_Tech_Indicators_Funnel.price_action.horizontal_sr.horizontal_sr_snapshot [--json] [--key KEY --name NAME --daily-domain universe]
python -m modules.Module_F_Tech_Indicators_Funnel.price_action.horizontal_sr.test_horizontal_sr
python -m modules.Module_F_Tech_Indicators_Funnel.price_action.horizontal_sr.test_horizontal_sr_snapshot
python -m modules.Module_F_Tech_Indicators_Funnel.price_action.horizontal_sr.hsr_zones_check [--date YYYY-MM-DD] [--at HH:MM] [--key KEY --daily-domain universe]
python -m modules.Module_F_Tech_Indicators_Funnel.price_action.horizontal_sr.test_hsr_zones
```
Logs: `logs\horizontal_sr_test_logs\` — `horizontal_sr_check.log`, `horizontal_sr_snapshot.log`, `horizontal_sr_unit_tests.log`, `horizontal_sr_snapshot_unit_tests.log`, `hsr_zones_check.log` + `hsr_zones_<date>.html`, `hsr_zones_unit_tests.log` (overwritten each run; first line = the command). Run the data refresh first (after 4 pm for today's close).

### 4.11 Tests — 65, all pass (Windows, 2026-10-26)

| File | Tests | Proves |
|---|---|---|
| `test_horizontal_sr.py` | 38 | one line per swing; line price = the swing candle's high / low on real Zig Zag output; numbering outward from close, top of chart first, AT at 2 decimals; equal prices stay separate; PD tags exact, missing field raises; recency counts trading days; rule A on Ash's examples (26,373.20, 22,179.90; mixed by side of price: below → lowest low 23,059.45, above → highest high 22,900.65, the matching kind not the extreme price, no close → earliest, trading ladder applies the side rule); tolerance bounds the group width; never merging across price (real 60m case 23,149.85 / 23,116.10); PD lines never merged with another price, same-price PD lines combine across timeframes; trading ladder lists timeframes; naive and timezone-aware times mix; input not modified; bad close / missing columns raise; empty input |
| `test_horizontal_sr_snapshot.py` | 9 | nearest first on each side; text format R3 · R2 · R1 / S1 · S2 · S3; line fields; "no line" text; summary line; all seven views built and JSON-safe; never raises when the reader raises; a failed timeframe is reported and the rest still built |
| `test_hsr_zones.py` | 18 | depth limits use only past candles; swing high zone = wick to body top, swing low = wick to body bottom; at least gamma deep, never more than half the ATR; missing swing candle / unknown timeframe raise; the same turn on two timeframes is one swing with the smaller zone; the same price on different days is two swings; overlapping zones merge and count touches (highs / lows); touching edges merge, a gap does not; a wick past the far edge breaks (down from above, up from below); highs above a support zone are not a break; the side from the close decides the direction; numbering R / AT / S from the close; bad close raises; end to end with input not modified; empty input |

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

**After the rule A change (2026-10-23):** the mixed group 23,056.40 (high) / 23,059.45 (low) below price now keeps **23,059.45** (Ash: the lowest of the Zig Zag lows); above price, 22,894.15 / 22,900.65 keeps **22,900.65**. Tests 38 + 9 pass on Windows (2026-10-23).

### 4.13 Horizontal S&R zones (`hsr_zones.py`, built 2026-10-26, stopped with open items)
**Why:** Ash (2026-10-26): "HSR zones are what the books and studies say, I follow the same." Research recap (§4.1, §4.5, refreshed 2026-10-26):
- **Books / practice:** a zone is an area where price **reversed several times** at about the same price (two reversals usually the minimum, separate episodes count more; one reversal = a possible zone). Edges: the outer edge through the **extreme wick** of the touches, the inner edge at the **candle bodies**. Width grows with timeframe and volatility (often checked against ATR; common indicator practice: swing ± ATR/2). Stronger: higher timeframe, repeated well-spaced touches (disputed: tests also use the level up), fresh, confluence (round numbers, MAs). A close beyond confirms a break in the books; role reversal after a real break. ([LuxAlgo S/R zone](https://www.luxalgo.com/library/concept/s-r-zone.md), [Capital.com S&R zones](https://capital.com/en-gb/learn/technical-analysis/support-and-resistance-zones), [LuxAlgo ATR S&R](https://www.luxalgo.com/library/indicator/NxezQute-atr-support-and-resistance/))
- **Studies (Garzarelli et al. 2014; Chung & Bellotti 2021):** zone half-width = the average absolute bar-to-bar price change of the series. ([arXiv 2101.07410](https://arxiv.org/pdf/2101.07410))

**Decisions (Ash, 2026-10-26):** a new file, nothing in `horizontal_sr.py` changes ("don't touch what we did before"); the books + studies combination below; **a wick can say break**; no strength score (only base facts, §4.4).

**Rules as built:**
1. Every Zig Zag swing on 1M / 1W / 1D / 60m / 15m / 5m is one zone: swing high = candle high down to the body top (max of open / close); swing low = candle low up to the body bottom (min of open / close).
2. Depth at least **gamma** = mean |close − previous close| of the last 20 candles (studies) and at most **half the ATR** (mean true range of the last 14 candles; indicator practice), both from that timeframe's own candles up to the swing candle (no future data; works on Nifty, stocks and option premiums).
3. Recency as for lines (`RECENT_TRADING_DAYS`: 1M / 1W / 1D all history, 60m / 15m 25 trading days, 5m 3).
4. The same turning point on several timeframes (same kind, same price at 2 decimals, pivots within one candle of the bigger timeframe) counts **once**; it keeps the zone of its smallest timeframe and lists all its timeframes.
5. Overlapping zones merge (touching edges count as overlapping). **Touches** = separate swings inside.
6. Facts per zone: low / high, touches, highs and lows inside (a mix = role reversal seen), timeframes, highest timeframe, first / last touch, the swings. Side from the reference close: **R** (zone above), **S** (below), **AT** (contains it); numbered R1 / S1 nearest first.
7. **Break** (wick): from the zone's side at the reference close — an S zone breaks down on a later low below it, an R zone up on a later high above it, an AT zone either way; the zone is kept with the time and direction of the first break.

**Check (`hsr_zones_check.py`):** the 5m chart of the last 7 days; each day's zones use only candles finished before **09:15** that day (previous close = reference), drawn across the day in colour (red R, green S, orange AT) until a wick breaks them (black square, then grey). Log: per day the 3 nearest zones each side with touches, timeframes, last touch, break. Fix found while building it (2026-10-26): break direction first came from the first candle after the last touch, which gave "R zone broke down"; now from the zone's side at the reference close (+1 test).

**What the check showed (Ash's data, 14 – 23 Oct 2026):**
- Zones that held: 23,070.15–23,207.45 (1W 1D 1h 15m) capped 16 / 19 Oct; 22,179.90–22,438.06 (1M 1W 1D 1h 15m) caught the 23 Oct fall (low 22,372.00, inside it); on 23 Oct the zones broke in order as price fell (AT 09:30, S1 09:55, S2 10:05).
- **Problems (Ash, 2026-10-26: "are you drawing everything as zone?"):** (a) **every single swing is drawn as a zone**, even one swing on one timeframe (e.g. 23 Oct R2 22,889.00–22,900.65, 1 touch, 5m) — the books need 2+ reversals; (b) **chained wide zones**: a swing joins a zone when it overlaps any part of it, so busy areas grow (15 Oct R1 22,627.50–22,809.35, 182 pts, 15 touches; 23 Oct AT 22,677.33–22,811.35, 134 pts). Proposed fix (not approved): a zone needs 2+ separate swings; a swing joins only the zone's core (where its swings overlap); single swings stay lines. **Ash stopped the zone work here (2026-10-26).**

**Open items (zones):**
1. Single swings as zones → need 2+ swings? Single swings as thin lines or hidden?
2. Chaining → join only the zone's core?
3. Gap opens: a wick through a zone at the 09:15 open counts as a break today (16 / 21 Oct broke several zones at the open) — keep?
4. Wide higher-timeframe zones (22,179.90–22,438.06 258 pts; 23,263.15–23,413.11 150 pts) — keep as the books say?
5. Zones are fixed at 09:15; add new swings confirmed during the day?
6. Not used anywhere yet: the 5m zones chart in `trendline_draw.py` and `trendline_confluence.py` still use their own temporary zone grouping (`TRENDLINES.md` §11); switch them over only when zones are approved.
7. Touch count after the zone formed (tests) and freshness; volume.

---

## 5. Type 2 — EMA S&R (studied 2026-10-19: not S&R on Nifty → EMA break watch)

### 5.1 Research: books
- **Books teach moving averages as S&R.** Granville's moving-average rules (1960) include buying a dip toward a rising average; Murphy covers MAs as support in uptrends; StockCharts teaches the 50- and 200-day (SMA) as S&R in an uptrend with the 50 above the 200 and both rising ([StockCharts](https://chartschool.stockcharts.com/table-of-contents/trading-strategies-and-models/trading-strategies/moving-average-trading-strategies/finding-support-and-resistance-in-moving-averages)).
- **Intraday:** Al Brooks trades around the 20-bar EMA on every chart; his followers describe the "20 gap bar" (first touch after ~20 bars on one side) and report he plots the 1h 20 EMA on the 5m chart — second-hand forum reports, not his words ([Brooks forum](https://www.brookstradingcourse.com/support-forum/general-trading-discussion/20-gap-bar-buy-and-ema-gap-bar-buy/)). Raschke's "Holy Grail": pullback to the 20-period average when ADX > 30 and rising (daily examples, SMA) ([Trading Setups Review](https://tradingsetupsreview.com/the-holy-grail-trading-setup)). A practitioner on the Brooks forum: where the 20 EMA holds there is almost always other S&R there (confluence).
- **Why it is a topic at all:** everyone watches the same lines (50 / 200 DMA in every broker app and news story, e.g. "Nifty faces resistance near 200 DMA"), institutions use the 200-day as a benchmark, and an MA is the recent average price.

### 5.2 Research: studies
- **Kavajecz & Odders-White (2004, Review of Financial Studies):** S&R levels sit where limit-order-book depth peaks, and moving-average signals reveal where that depth sits — the only study tying MAs to real orders ([RePEc](https://ideas.repec.org/a/oup/rfinst/v17y2004i4p1043-1071.html)).
- **Grimes (200-day):** S&P / DJIA returns above vs below the 200-day differ weakly, not significantly, and not at all in the last decade ([Grimes](https://www.adamhgrimes.com/200-day-moving-average-work/)).
- **No published study measures how often price bounces at an EMA**, which EMA, or which timeframe (unlike horizontal levels). An NQ 5m EMA backtest found online is a cross test, not a bounce test ([Astreka](https://www.astreka.com/market-insights/best-ema-for-futures-trading-5-minute-nq-ema-backtest)).

### 5.3 Ash's observations
- Uses EMAs on the daily only; her 60m / 15m / 5m charts carry no EMAs (screenshots 2026-10-18).
- Logged on Mon 7 Sep 2026 that Nifty was rejected at the 200D EMA.
- Decision (Ash): since the books say it but no study measures it, **test it on Nifty's own history before building anything.**

### 5.4 The study — `studies/ema_sr/` (read-only, Nifty 50, data to Fri 16 Oct 2026)

| | |
|---|---|
| Lines | EMA 5 / 13 / 20 / 26 / 50 / 100 / 200 (Ash's six + the books' 20) on each timeframe's own candles; daily EMAs on 60m / 15m / 5m candles (each intraday candle uses the previous day's daily EMA) |
| Data | 1M 322 · 1W 1,399 · 1D 6,662 candles (3 Jan 2000 – 16 Oct 2026); 60m 8,284 · 15m 29,580 · 5m 88,824 candles (3 Jan 2022 – 16 Oct 2026) |
| Touch episode (Ash: "how many touches does it take") | armed by a candle fully clear of the line; starts at the first wick touch (or, close mode, a close within X); counts every touching candle; ends at the first **close beyond** the line (break) or a close at least X away on the original side (bounce) |
| X | average \|close − previous close\| over the last 20 candles (study method, Garzarelli 2014 / Chung & Bellotti 2021; rolling so it follows the price scale and never uses future candles) |
| Control (Chung & Bellotti method) | the same test on prices rebuilt from the real candles in random order, 20 times; edge = real bounce % − control bounce %; every split is compared with the control in the same split |
| Conditions | measured on the candle **before** the touch: trend = Ash's EMA stack (support with stage > 0, resistance with stage < 0), stage −5…+5, above / below the 200, era, candles clear before the touch |
| Recorded per episode | touches, candles, outcome, deciding candle's body %, range vs average, close position, and for a break the candles until price first closed back on the original side |

**Results (wick touch):**

| Timeframe | Edge vs control, all EMAs | Notes |
|---|---|---|
| 1D | EMA 13–200: **−3.1 to −6.3 pts**; EMA 5 +3.8 | touches end in a break 70–75% of the time; EMA 13 / 20 / 26 / 50 bounce **below the lowest** of the 20 random runs |
| 1W | −7.6 to +6.1 (EMA 5–100, 42–263 episodes each) | no consistent edge; EMA 200 only 14 episodes |
| 1M | — | 0–54 episodes per EMA: too few to read |
| 60m | −5.2 to +1.5 | nothing |
| 15m | −1.8 to +0.3 | nothing |
| 5m | −1.4 to +0.9 | nothing |
| 5m close mode | **+2.4 to +3.9** for EMA 13 / 20 / 26 / 50 / 100 / 200 (2,454–11,191 episodes each; every one above the control's highest run) | a 5m candle closing near an EMA without crossing bounces slightly more than chance; 15m EMA 200 close +3.7 |

**With trend (pullback in the direction of the EMA stack):** 1D EMA 13–200 **−3.5 to −7.4 pts** (worse than chance); 60m −3.3 to +2.2; 15m −1.7 to +3.2; 5m −1.6 to +0.3. Strongest stack only (+5 / −5): 15m EMA 20 +2.7, EMA 26 +3.3, 5m EMA 26 +2.4; larger figures (5m / 15m EMA 200 at +5: +10 to +12) rest on 19–56 cases.

**Touches (Ash's question), daily EMA 50:** 1st touch — bounce 18%, break 58%, more touches 24%; 2nd — 20% / 56%; 3rd — 23% / 59%; daily episodes rarely go past 3 touches.

**Era, daily EMA 200:** bounce 34.9% in 2000–2012, 19.0% in 2013–2019, 19.5% in 2020–2026 — fading, like Grimes' finding.

**What happens after a break** (5m / 15m / 60m, EMA 50 / 100 / 200, 10,685 breaks): about half close back on the original side within 3 candles (45.5%); 34.4% are still broken after 10 candles. The size of the breaking candle separates them (tall ≥ 2× average: 50.3% still broken / 30.7% back within 3; small < 1×: 24.9% / 56.8%; same on each timeframe and on 2025–26 data not used to choose the cut-off). Body % and close position add only 1–5 pts. Details: `EMA_BREAK.md` §2.

**Study method lessons (apply to every future study):**
- **Conditions may only use what was known before the touch.** The first run measured the EMA slope on the touch candle; by the EMA formula a candle closing below yesterday's EMA turns the EMA down **and** is already a break, so "against trend" showed exactly 0% bounce. Caught from the log, fixed, tested.
- **The line's own slope cannot measure trend.** An EMA always rises after a candle that closes above it, so before a support touch it is rising by definition — every episode came out "with trend". Trend must come from something else (here the EMA stack; market-structure trend is the alternative).
- A random control is essential: on the randomly reordered candles EMAs "bounce" 27–41% of the time too (control column, 1D and intraday).

### 5.5 Decision (Ash, 2026-10-19)
- **EMAs are not drawn as S&R lines** and do not go on the horizontal S&R ladders.
- They become the **EMA break watch** (`EMA_BREAK.md`, `trend_indicators/ema_break/`): near alert, break label with the breaking candle's size, odds from history; live on 60m / 15m / 5m for EMA 50 / 100 / 200 only, ⚡ only on a tall-candle break, context lines for 1M / 1W / 1D.
- Market-structure trend (option b) was not run: every split gave the same answer (overall, side, stack, strongest stack, wick and close, six timeframes, 26 years).
- The faint intraday signals (5m close near an EMA; stack +5 pullbacks to the 20 / 26 EMA) are kept as findings for the combining stage, not traded alone.

### 5.6 Code map, how to run, tests
| File | Holds |
|---|---|
| `indicator_common/line_reaction_study.py` | `average_move`, `find_episodes`, `touch_table` — the touch-episode engine, shared by the study and the EMA break watch (moved from `studies/` 2026-10-19) |
| `studies/ema_sr/ema_sr_study.py` | `add_lines`, `daily_lines_on_intraday`, `shuffled_candles`, `episodes_with_conditions`, `rates`, `control_summary`, `split_table`, `run_study` + runner |

```
python -m modules.Module_F_Tech_Indicators_Funnel.studies.ema_sr.ema_sr_study [--timeframes TF ...] [--shuffles N]
python -m modules.Module_F_Tech_Indicators_Funnel.studies.ema_sr.test_ema_sr_study
python -m modules.Module_F_Tech_Indicators_Funnel.indicator_common.test_line_reaction_study
```
Outputs in `logs\studies_logs\`: `ema_sr_study_progress.log` (written as it runs, one line per step), `ema_sr_study.log` (summary + per-EMA detail: touch table, splits with control and edge), `ema_sr_episodes.csv` (one row per real episode, ~176,000 rows), `ema_sr_study_unit_tests.log`. The engine's test log: `logs\indicator_common_test_logs\line_reaction_study_unit_tests.log`. Full run 199 s on Ash's machine (2026-10-19).

Tests: `test_line_reaction_study.py` 17 (single / multi-touch bounce, break and reclaim, never reclaimed, side flips, resistance mirror, gap through the line = one-touch break, needs a clear candle, open at the end, NaN line skipped, close mode, candle strength, rolling X with no future data, touch table, input not modified, validation); `test_ema_sr_study.py` 13 (random order keeps the same candles and is repeatable, lines and stage, daily line uses the previous day only, conditions from the candle before the touch, against-trend not a built-in zero, timezone-aware times, control summary and per-split control, progress messages, end-to-end with a fake reader, failed timeframe reported).

---

## 6. Type 3 — Trendline S&R → `TRENDLINES.md`

Moved to its own document on 2026-10-26 (Ash: keep them separate). There: research, the old chain check (`trendline_check.py`), the new drawing Ash's way on every timeframe (`trendline_draw.py`), all timeframes on one chart (`trendline_confluence.py`), open questions. Trendlines use the horizontal S&R of §4 (trading ladder, targets).

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
- [StockCharts — Finding Support and Resistance in Moving Averages](https://chartschool.stockcharts.com/table-of-contents/trading-strategies-and-models/trading-strategies/moving-average-trading-strategies/finding-support-and-resistance-in-moving-averages)
- [Kavajecz & Odders-White 2004, Technical Analysis and Liquidity Provision, Review of Financial Studies 17(4)](https://ideas.repec.org/a/oup/rfinst/v17y2004i4p1043-1071.html)
- [Grimes — Does the 200 day moving average "work"?](https://www.adamhgrimes.com/200-day-moving-average-work/)
- [Brooks Trading Course forum — 20 gap bar buy](https://www.brookstradingcourse.com/support-forum/general-trading-discussion/20-gap-bar-buy-and-ema-gap-bar-buy/)
- [Trading Setups Review — Raschke's Holy Grail](https://tradingsetupsreview.com/the-holy-grail-trading-setup)
- [Astreka — 5-minute NQ EMA backtest](https://www.astreka.com/market-insights/best-ema-for-futures-trading-5-minute-nq-ema-backtest)
- Granville, *A Strategy of Daily Stock Market Timing for Maximum Profit* (1960) — moving-average rules

---

## Change log
- **v1.3 — 2026-10-26.** Status, §1. Horizontal S&R: §4.6 / §4.8 notes, §4.9 code map, §4.10 run, §4.11 tests 65 (+18 `test_hsr_zones.py`), new §4.13 horizontal S&R zones (`hsr_zones.py`, `hsr_zones_check.py`: research recap, Ash's decisions, rules, check result on 14–23 Oct, problems found, stopped with open items). **§6 trendlines moved to its own `TRENDLINES.md`** (with the every-day check result and the new drawing Ash's way); §6 here is now a pointer.
- **v1.2 — 2026-10-23.** Type 3 trendlines (§6): research, Ash's method, rules as built, horizontal S&R in trendlines, draft exits (on hold for options data), code map, how to run (incl. multi-day), open items, verification on 19 Oct. Rule A for mixed groups changed to by side of price (§4.7, §4.11 47 tests, §4.12). §1 table, status.
- **v1.1 — 2026-10-19.** Type 2 EMA S&R (§5): research, Ash's observations, the Nifty study (`studies/ema_sr/`, shared engine in `indicator_common/line_reaction_study.py`), results, method lessons; decision: EMAs are not S&R on Nifty → EMA break watch (`EMA_BREAK.md`). §1 and §2 updated.
- **v1 — 2026-10-18.** Horizontal S&R built (`price_action/horizontal_sr/`): every Zig Zag swing a line, recency, rule A merge, never across price, PD lines kept, per-timeframe ladders + trading ladder, check, snapshot, 42 tests; checked against Ash's drawings (§4.7, §4.12). Folder corrected to `price_action/`.
- **v0.1 — 2026-10-18.** Scope (11 types), build sequence, research for horizontal S&R, Ash's observations, zone research.
