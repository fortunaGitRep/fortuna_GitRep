# Market Structure — spec (swing points, level breaks, BOS / CHoCH, trend state)

_Version 1 — 2026‑10‑16. Code: `backend/modules/Module_F_Tech_Indicators_Funnel/price_action/`
(`swing_points/` + `market_structure/`). Build history and every decision in order: the
"Fortuna — Market Structure Build Plan" doc (exported next to this file)._

---

## 0. In plain English

Market structure says, from price alone, whether Nifty is **trending up, trending down or not yet
decided** on each timeframe, and the exact price that would change that.

1. **Swings** are the corners of the chart: Fortuna draws them with TradingView's Zig Zag, the same
   lines Ash sees on tv.dhan.co.
2. A **level** is a swing high or low. Price can poke through it with a wick (an *attempt*) or close
   beyond it (a *break*). After a break Fortuna watches what happens: did price move away, come back
   to test the level, hold or fail?
3. A close beyond the latest swing high or low is a structure event:
   - **BOS: Break of Structure — indicates a trend continuation.**
   - **CHoCH: Change of Character — indicates a potential trend reversal.**
4. The **trend** is uptrend, downtrend or neutral. Only a CHoCH changes it.
5. Every day the report says what that day shows; the next day says the same or something new.
   Every situation is kept as a **label** — whether to trade is decided later, with all indicators.

---

## 1. Scope

| | |
|---|---|
| Instrument | Nifty 50. Stocks need the snapshot domain option (open item, §13) |
| Timeframes | 1M, 1W, 1D, 60m, 15m, 5m + two provisional views: 60m built on 5m candles, 1D built on 60m candles |
| Uses | high / low for swings and wicks, close for breaks, open for the gap tag. Volume not used (Upstox index volume is 0) |
| Not here | S/R lines and zones, trendlines, chart patterns (double tops etc. beyond the bare labels), order blocks — later modules reuse these swings |

Data comes through `indicator_ohlcv_reader.read_for_indicators` (reader rules applied there). Nothing
here fetches or writes data except its own log files.

---

## 2. Swings — TradingView Zig Zag (step 1)

`swing_points/zigzag_swings.py` is a port of TradingView's ZigZag library v9 (2026‑02‑25, MPL 2.0),
confirmed‑pivot logic only:

1. Bars checked each side = `max(2, floor(depth / 2))`; depth 10 → 5 bars.
2. Pivot high: high strictly above the 5 bars before, above‑or‑equal to the 5 bars after (the first of
   equal highs wins). Lows mirror it. A pivot is known 5 bars later (`detected_time`).
3. Highs are checked before lows on each bar; one bar can give both.
4. Same kind as the last swing → replaces it only if more extreme. Opposite kind → added only if at
   least the deviation away. When the opposite swing is added, the previous one is **locked**
   (`locked_time`) and never changes again. The last swing is not locked and can still move.
5. Projection pivots (TradingView's dashed live line) are not ported.

**Settings** (`swing_points/zigzag_settings.py`, one table, change values there only):

| TF | Deviation | Depth | Equal tolerance | Status |
|---|---|---|---|---|
| 1M / 1W / 1D | 5% | 10 | 0.50% (≈113 pts) | chosen by Ash on the chart |
| 60m | 1.25% | 10 | 0.20% | derived (power‑law scale between Ash's 5m and 1D) |
| 15m | 0.5% | 10 | 0.10% | derived |
| 5m | 0.2% | 10 | 0.05% (≈11 pts) | chosen by Ash on the chart |

No study gives per‑timeframe values (directional‑change research: no threshold is privileged).

**Leg data** (step 2, `swing_legs.py`): leg points, %, bars, retracement % of the previous leg.
**Labels** (step 3, `market_structure/swing_labels.py`): H / L for the first two, then HH, LH, EQH /
HL, LL, EQL against the swing two rows back, using the equal tolerance; equal swings get a zone id,
touch count, zone range and neckline. Bare minimum on purpose — full pattern logic belongs to chart
patterns.

---

## 3. Provisional view — Ash's "temporary lock"

A daily swing needs 5 daily candles to confirm, a 60m swing 5 hours. The same turn shows up much
earlier as a locked swing on a lower timeframe, so `provisional_swings.py` re‑runs the Zig Zag rule
over the lower timeframe's **locked** swings with the **higher** timeframe's deviation:

- 5m locked swings + 1.25% → provisional 60m
- 60m locked swings + 5% → provisional 1D

`known_at` = the lower‑TF lock time of the swing; `confirmed_at` = when the next opposite provisional
swing was added. The real Zig Zag stays the reference for chart parity.

Example (13 Oct 2026): real daily cannot see the 8 Oct low yet (needs 5 more daily candles); the
provisional daily already shows 22,179.90 as the next level.

---

## 4. Level breaks (step 4) — `market_structure/level_breaks.py`

Levels = swing highs and lows (S&R lines and trendlines later reuse the same logic). Band = the
timeframe's equal tolerance. Shown for a high level; lows mirror it.

| Label | Rule |
|---|---|
| attempt | first candle whose **high** goes above the level (wick) |
| confirmed (break) | first candle that **closes** above the level |
| gap | the breaking candle **opened** above the level |
| cleared | from the breaking candle on, first candle fully outside the band (low above level + band) — the "white space" |
| retest | after cleared, first candle whose low comes back into the band |
| held | after a retest, a close back above the level |
| failed | a close below level − band (busted break, a signal on the other side) |
| re-break | after a failure the level is watched again; each new break is a new cycle (#2, #3 …) |

- **White space before a retest (Bulkowski):** without it almost every retest was simply the next
  candle overlapping the band. Not cleared yet = price hugging the level, not the strong case.
- **Held is not final:** a later failure reads `HELD … -> FAILED …`.
- **Levels are watched forever;** repeated tests are kept as labels (touch count = strength, later).
- **Every label is first‑class.** Low‑weight today (attempts, retests, failures) may be high‑weight
  later — markets change. Never drop them.

**Research behind it:**

| Finding | Source | Use |
|---|---|---|
| Wick beyond a swing = breakout, close = stronger | Al Brooks | attempt vs break |
| Close + 1–3% or 2‑close filter on daily | Murphy; Edwards & Magee | close for breaks; filter not used |
| 58–65% of breakouts throw back; throwback needs white space | Bulkowski | retest after cleared |
| No throwback = better in 97% (up) / 91% (down) of pattern types | Bulkowski | no retest = stronger |
| Staying above on the throwback: +40% vs +29% | Bulkowski | held vs failed |
| Gaps through the level help (68% / 85%) | Bulkowski | gap tag |
| Busted patterns outperform (97% / 94%) | Bulkowski | failed = opposite signal |
| Reversals at levels, acceleration after crossing (stops cluster) | Osler, NY Fed | breaks continue |
| More prior bounces → more likely to bounce, fading with time | arXiv 2101.07410 | touch count later |

No study compares wick vs close; the backtest can overturn the close rule.

---

## 5. BOS / CHoCH and trend state (step 5) — `market_structure/structure_events.py`

Sources: Dow Theory (trend = HH + HL, presumed to continue until a **close** beyond the prior swing;
Murphy), Sperandeo 1‑2‑3 (close beyond point 2), TradingView market‑structure scripts (Xcelerate,
LuxAlgo: close beyond the latest swing, start neutral, first break = CHoCH, a broken level is used up).

**Rules (Ash, 16 Oct 2026 — "label as we see it today; tomorrow informs same or different"):**

1. **Targets:** the latest swing high (above) and swing low (below) **known that day** — from the
   swing's detected time, no waiting for it to lock. A newer swing of the same kind replaces the target.
2. **Event:** the first close beyond a target. Up break in an uptrend = **BOS, uptrend continues**; in a
   downtrend or neutral = **CHoCH, trend flips to uptrend**. Down mirrors it.
3. **Start:** each timeframe is neutral on its first candle of history only; the whole history is scanned.
4. **Final:** the event and any trend flip are final at the close of the breaking candle.
5. **One event per level:** failure, retest, held‑then‑failed and re‑breaks are labels on the event
   (from §4). They never undo an event or flip the trend; only a CHoCH flips it.
6. Trend words are **uptrend / downtrend / neutral**, never bull / bear.

**Worked example (Ash, daily):** 3 May 2024 high 22,794.70 → **BOS Thu 23 May 2024**; failed Tue 4 Jun
(election‑day crash, close back below); re‑broken Thu 6 Jun (close 22,821.40); trend stays uptrend.

**Gap case (5m):** Fri 9 Oct 2026 09:15 opened above two known highs → one CHoCH on the newest
(22,256.00), no extra BOS.

**Tried and dropped (16 Oct 2026):** waiting for the swing to lock before it can be broken; skipping
swings already beyond when they lock; a "LATE" label; a close‑beyond‑level‑plus‑band filter (Ash counts
the 6 Jun 2024 close, +27 pts, as a break).

---

## 6. Snapshot texts and alerts (step 6) — `market_structure/market_structure_snapshot.py`

Same shape as `macd_snapshot.py`: `snapshot_from_bars` (one timeframe), `provisional_snapshot`
(`"60m"` / `"1d"`), `summary_line`, `build_market_structure_snapshot` (never raises). Fixed templates,
no AI. Dates via `indicator_common.text_format.report_date` (`Tue 13 Oct 2026`, `Week of Mon 12 Oct
2026`, `Oct 2026`, intraday with the time); running week / month marked "(week / month to date)".

**Texts per view** (real run, data to Tue 13 Oct 2026):
```
Nifty 50 · 1D — as of Tue 13 Oct 2026: close 22,721.95
DOWNTREND since Thu 24 Sep 2026 (CHoCH, closed below 23,116.10), 13 days.
Close above 24,774.30 = CHoCH, downtrend to uptrend (+2,052.35 / +9.03% away).
Close below: no level now, waiting for a new swing low (BOS, downtrend continues on its break).
Last break: CHoCH, uptrend to downtrend, 23,116.10 (Thu 24 Sep 2026): cleared, no retest yet.
```
On the day of an event: `⚡ Today: CHoCH, … — closed above X, on a gap (swing high of …).` (⚡ for CHoCH
only) or `Today: BOS, uptrend continues — …`. Step‑4 labels on the latest candle: `Today: the X break
(date) failed / held / was retested / was re-broken.` Intraday views say "On this candle".

**Summary line:** `Structure: 1M uptrend · 1W downtrend · 1D downtrend · 60m uptrend · 15m uptrend ·
5m uptrend · prov. 60m uptrend · prov. 1D downtrend` (13 Oct 2026).

**Alerts (Ash, 16 Oct 2026):** every BOS and CHoCH on the latest candle, all timeframes and both
provisional views, both directions. Labels (failed / retested / held / re‑broken) are text only.
`directions="above"` (stocks) shows only up events as texts and alerts; states always included.

**Package per view** (JSON‑safe): `instrument, view, title, directions, as_of, partial, close,
trend {state, held, set_by}, flip {up, down: level, distance_pts, distance_pct, means}, events_today,
labels_today, last_break, last_events {bos_up, bos_down, choch_up, choch_down}, alerts, texts`.

---

## 7. Code map

| File | Main functions |
|---|---|
| `swing_points/zigzag_swings.py` | `find_zigzag_swings`, `bars_each_side` |
| `swing_points/zigzag_settings.py` | `ZIGZAG_SETTINGS`, `get_zigzag_settings`, `get_equal_tolerance` |
| `swing_points/provisional_swings.py` | `provisional_swings`, `current_direction` |
| `swing_points/swing_legs.py` | `add_leg_data` |
| `swing_points/zigzag_check.py` | manual check: swings, temporary‑lock view, LEVEL BREAKS, STRUCTURE (all 6 TFs + provisional) |
| `market_structure/swing_labels.py` | `add_swing_labels` |
| `market_structure/level_breaks.py` | `find_level_breaks` |
| `market_structure/structure_events.py` | `find_structure_events`, `current_structure` |
| `market_structure/market_structure_snapshot.py` | `snapshot_from_bars`, `provisional_snapshot`, `summary_line`, `build_market_structure_snapshot` |

Imports only from `indicator_common/` (`text_format`, `timeframes`) and its own folders.

---

## 8. Tests — 78, all pass

| File | Tests | Proves |
|---|---|---|
| `test_zigzag_swings.py` | 18 | pivot rule, first of equal highs, replace / add by deviation, lock times, input checks |
| `test_provisional_swings.py` | 6 | locked swings only, higher deviation, direction and reverses_at |
| `test_swing_legs.py` | 4 | leg points / % / bars / retracement |
| `test_swing_labels.py` | 9 | HH/HL/LH/LL, EQH/EQL in tolerance, zones, neckline |
| `test_level_breaks.py` | 17 | attempt vs close, gap, white space, retest, held, failed, held‑then‑failed, re‑break cycles, timezones |
| `test_structure_events.py` | 12 | neutral start, BOS vs CHoCH, wick ≠ event, newest known swing, gap case, Ash's 2024 example, failure ≠ flip |
| `test_market_structure_snapshot.py` | 12 | texts, ⚡ only on CHoCH, labels text‑only, directions filter, flip distances, JSON‑safe, never raises |

Each test file runs on its own and writes its log (`python -m …test_<name>`), or all together with
`python -m pytest modules/Module_F_Tech_Indicators_Funnel/price_action -v`.

---

## 9. Verification record (tv.dhan.co, Nifty 50)

| What | Candle(s) | Result |
|---|---|---|
| Swings 1D (5 / 10) and 5m (0.2 / 10) | last 30 daily, last 40 5m swings | match the chart (14 Oct 2026) |
| Attempt, no break | 22,182.55 low · Thu 8 Oct 2026 | wick below, close above ✓ |
| Gap break → failed → re‑break | 24,571.75 · Wed 4 Mar 2026 (open 24,388.80, close 24,480.50) · Thu 5 Mar (close 24,765.90) · Fri 6 Mar (close 24,450.45) | ✓ |
| Break, retest, held | 25,669.35 · Fri 17 Oct 2025 (close 25,709.85) · Fri 24 Oct (low 25,718.20, close 25,795.15) | ✓ |
| Failed without clearing | 24,601.70 · Tue 11 Aug 2026 close 24,471.70 | ✓ (7 pts past the band) |
| White space, retest, held, failed (5m) | 22,534.40 · Fri 9 Oct 2026 14:20 (low 22,558.90), 14:30 (low 22,539.25, close 22,544.95), 15:25 (close 22,520.45) | ✓ |
| Re‑break on a gap (5m) | Mon 12 Oct 2026 09:15 (open 22,593.20) | ✓ |
| BOS 1D | Thu 23 May 2024 on 22,794.70; re‑broken Thu 6 Jun 2024 (close 22,821.40) | ✓ (Ash) |
| CHoCH 1D | Wed 4 Mar 2026 (24,571.75), Thu 24 Sep 2026 (close 23,063.10) | ✓ |
| CHoCH 5m | Mon 12 Oct 2026 10:50, close 22,442.15 below 22,446.10 | ✓ |
| Snapshot | all 8 views, data to 13 Oct 2026 | trends match the STRUCTURE check (16 Oct 2026) |

---

## 10. Known behaviour — not errors

| Seen | Why |
|---|---|
| The last swing moves | Zig Zag's last leg is not locked until the opposite swing is added (days on 1D) — use the provisional view for an early read |
| Rebuilt event history has fewer events than the live alerts did | a close beyond the last (unlocked) swing is a BOS that day; if Zig Zag later moves that swing, a rebuild from the finished Zig Zag no longer sees it (lookahead test: 10 of 50 cut dates). Live record = the stored daily snapshots (open item) |
| Weekly candles named by Monday | Upstox; TradingView names the week by its first trading day |
| Latest week / month moves | running candle ("to date") |
| Tiny breaks count (1.2 pts on 5m, 7 pts on 1D) | close beyond = break, by Ash's rule; a break‑margin label is an open item |
| 5m snapshot takes ~20 s | labels are computed for every event in history (≈2,500 on 5m); fine for Nifty |

---

## 11. How to run

See the Indicators Runbook §4.7. Short version (from `backend/`):
```
python -m modules.Module_F_Tech_Indicators_Funnel.price_action.market_structure.market_structure_snapshot [--timeframes …] [--directions both|above] [--no-provisional] [--json]
python -m modules.Module_F_Tech_Indicators_Funnel.price_action.swing_points.zigzag_check [--timeframe TF] [--show N] [--events N]
```

---

## 12. Defaults that are Ash's choices (change only with Ash)

Deviation 5% (1D/1W/1M) and 0.2% (5m), depth 10; equal tolerance per timeframe; wick = touch point /
attempt, close = break; white space before a retest; held not final; re‑breaks as cycles; targets =
latest swing known that day; one event per level; uptrend / downtrend wording; alerts on every BOS /
CHoCH, labels text only; report dates.

---

## 13. Open items

- Store the daily snapshots (the live record) — with the predictor item; then backtest on them.
- Snapshot domain option for stocks (same as MACD / ADX / RSI).
- Label only recent events in the snapshot (speed) before running the watchlist.
- Break‑margin label ("beyond by X pts"); thin white space (13 pts counts like a big move); a failure
  on the day's last candle (Fri 9 Oct 2026 15:25, 3 pts) — backtest decides.
- Levels keep acting after the outcome (role reversal, e.g. 22,534.40 on Tue 13 Oct 2026) — S&R module.
- Chart‑pattern stage: body spans the level / gap through for tops, strong‑candle measure (range vs
  average range), retest window; check the example equal pairs (D1–D6, M1–M4).
- Backtest each label; Bank Nifty confirmation (data not stored); frontend markers.

---

## 14. Sources

- TradingView ZigZag library v9: https://www.tradingview.com/script/bzIRuGXC-ZigZag/
- Bulkowski, Throwbacks: https://www.thepatternsite.com/throwbacks.html
- Bulkowski, Making Cents of Throwbacks and Pullbacks (S&C 2002): https://www.traders.com/Documentation/FEEDbk_docs/2002/06/Abstracts_new/Bulkowski/Bulkowski.html
- LuxAlgo, Change of Character: https://www.luxalgo.com/library/concept/change-of-character/
- LuxAlgo, Dow Theory: https://www.luxalgo.com/library/concept/dow-theory.md
- LuxAlgo, 1‑2‑3 Reversal: https://www.luxalgo.com/library/concept/1-2-3-reversal.md
- TradingView, Market Structure CHoCH / MSS / BOS (Xcelerate): https://in.tradingview.com/script/mB81RFwK-Market-Structure-CHoCH-MSS-BOS-Xcelerate-Trade/
- arXiv 2101.07410 (support/resistance bounces): https://arxiv.org/abs/2101.07410
- Books: Murphy, *Technical Analysis of the Financial Markets*; Edwards & Magee, *Technical Analysis of
  Stock Trends*; Brooks, *Trading Price Action* series; Osler, Federal Reserve Bank of New York (stop‑loss
  clustering at round numbers / levels).

---

## 15. Change log

- **v1 — 2026‑10‑16.** First version: steps 1–6 built and checked on tv.dhan.co (Zig Zag swings,
  provisional view, legs, labels, level breaks, BOS / CHoCH, snapshot texts and alerts).
