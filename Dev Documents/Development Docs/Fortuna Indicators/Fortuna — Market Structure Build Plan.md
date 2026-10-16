# Fortuna — Market Structure Build Plan

Oct 16, 2026 · @Ash

## Purpose and scope

Market structure tells Fortuna, from price alone, whether Nifty or a stock is trending up, trending down or undecided, and when that just changed. It is built in six baby steps, each tested against TradingView before the next starts.

- **In scope:** swing points, HH/HL/LH/LL labels, BOS and CHoCH events, trend state, and plain-language text for the frontend.
- **Instruments:** Nifty 50 first, then the watchlist / options stocks.
- **Timeframes:** 1M, 1W, 1D, 60m, 15m, 5m (same set as the other indicators).
- **Data:** reads stored OHLCV only, applying the four indicator reader rules; never fetches.
- **Not here:** S/R levels and zones (they live in `support_resistance_levels/` and reuse the swing points built here), chart patterns, order blocks.

## Research findings that shape the design

Every serious market-structure tool, on TradingView and in Python, is the same three-layer stack: find pivots, compare each pivot to the previous one of its kind, then fire an event when price closes through the last pivot.

| Finding | What it means for Fortuna |
| --- | --- |
| TradingView's `ta.pivothigh(left, right)` / `ta.pivotlow` are the base of almost every structure script; a pivot is only known `right` bars after it prints ([LuxAlgo](https://www.luxalgo.com/library/indicator/LY5jsCca-pivot-points-alerts/)) | Use the same left/right pivot rule for parity. Store `pivot_time` and `confirmed_time`; signals key off `confirmed_time` only. |
| Tie rule: a pivot may equal earlier bars but must strictly beat later ones; found by matching TradingView trade-for-trade ([replay-lab](https://github.com/gregkitz/replay-lab)) | Code the tie-break exactly this way, or equal-high days will differ from the chart. |
| Raw pivots do not alternate: two pivot highs can confirm with no low between them ([Swing High/Low Adaptive](https://ar.tradingview.com/script/yRh7OKsh-Swing-High-Low-Adaptive/)) | Keep raw pivots for parity, and add a separate cleaned high-low-high sequence for labelling. |
| Tools run two layers: internal (short pivot length, LuxAlgo default 5) and swing (long, default 50) ([LuxAlgo](https://www.luxalgo.com/library/indicator/ud6AQSm2-market-structure/)) | Make pivot length a parameter; run a minor and a major layer per timeframe. |
| Break confirmation is either the candle close or the wick; close is the common default to filter fakeouts ([BOS & CHoCH](https://www.tradingview.com/script/Tmwxv2Wg/), [smartmoneyconcepts](https://github.com/joshyattridge/smart-money-concepts)) | Default to close, keep wick as a switch. |
| Each pivot level fires once (BOS/CHoCH on a close through it, or a sweep on wick-through-and-close-back), then disarms ([MTF Clean Pivot Points](https://in.tradingview.com/script/RTtUtMu6-MTF-Clean-Pivot-Points/)) | One event per pivot, no repeat alerts. Sweeps come free from the same check. |
| BOS = break with the trend, CHoCH = break against it; both are the same break read against the current trend ([Advanced & Improved](https://il.tradingview.com/script/0t7puDyH-Market-Structure-BOS-CHOCH-Advanced-Improved/)) | One break detector plus a trend state decides the label. |
| Dow Theory, the investor-side source, judges trend on closes, treats minor trends as noise, and expects secondary moves to retrace about one third to two thirds ([Incredible Charts](https://www.incrediblecharts.com/technical/dow_theory_trends.php), [LuxAlgo Dow](https://www.luxalgo.com/library/concept/dow-theory/)) | Investor view = the major layer on 1D/1W/1M with close-based breaks. Retracement depth per leg is worth storing for the research pass. |
| Dow also requires averages to confirm each other, e.g. Nifty 50 with Bank Nifty ([Strike](https://www.strike.money/technical-analysis/dow-theory)) | Needs Bank Nifty data, which Fortuna does not store yet. Deferred. |

ZigZag (default 5% deviation, depth 10) is the main alternative swing method ([LuxAlgo ZigZag](https://www.luxalgo.com/library/indicator/zigzag/)). It alternates by design but its last leg keeps moving until confirmed, so it started as a second option; on 14 Oct 2026 it became the base, because it is what Ash uses on tv.dhan.co.

## Where the code lives

Built: two subfolders under the existing `price_action/` folder, so the swing detector is written once and reused by both market structure and S/R.

```
backend/modules/Module_F_Tech_Indicators_Funnel/
  price_action/
    swing_points/        # steps 1-2: Zig Zag swings, settings, provisional view, legs, check script
    market_structure/    # steps 3-6: labels, breaks, trend state, text
  support_resistance_levels/   # later: imports swing_points, never duplicates it
```

Each step is a new file with a new name, follows the existing folder convention (one subfolder per indicator, `__init__.py` in each), writes run output to `logs/`, and gets recorded in the build log. The spec doc goes to the Fortuna Indicators folder as "Market Structure" once the build is tested.

## Build steps

Six steps, each its own file, each tested on Nifty 50 1D and 5m against tv.dhan.co before moving on.

**Change, 14 Oct 2026:** steps 1 and 2 now use the Zig Zag method instead of left/right pivots, because Zig Zag is what Ash has on tv.dhan.co. Step 1 ports TradingView's published ZigZag library (start: deviation 5%, depth 10) so Fortuna's corners match the chart. Zig Zag already alternates high and low, so step 2 only measures each leg (size, bars, retracement).

Zig Zag settings per timeframe live in one config table (swing\_points/zigzag\_settings.py, editable without code changes); the values are in the progress log below.

1. **Zig Zag swings** (`swing_points/zigzag_swings.py`): port of TradingView ZigZag v9 with the per-timeframe settings; each swing has pivot, detected and locked time. Provisional view (`provisional_swings.py`): lower-TF locked swings re-run with the higher-TF deviation.
2. **Leg data** (`swing_points/swing_legs.py`): points, %, bars and retracement % per leg.
3. **Labels** (`market_structure/swing_labels.py`): HH/HL/LH/LL/EQH/EQL against the swing two back, equal tolerance per timeframe, zone, touches and neckline.
4. **Level breaks** (`market_structure/level_breaks.py`): attempt, confirmed (close), gap, cleared, retest, held, failed and re-break cycles. Decisions in the progress log.
5. **BOS / CHoCH and trend** (`market_structure/structure_events.py`): a close beyond the latest swing known that day; trend now plus the two prices that would change it. Decisions in the progress log.
6. **Text and alerts** (market\_structure/market\_structure\_snapshot.py): per-view package, plain-language texts and alerts, plus one summary line, in the same shape as macd\_snapshot.py. Decisions in the progress log.

## Test and TradingView parity plan

Each step passes when its output matches what Ash sees on TradingView for the same candles, logged to `logs/` with the cases checked.

| Step | Checked against | Result |
| --- | --- | --- |
| 1 Zig Zag swings | tv.dhan.co Zig Zag 5 / 10 on 1D, 0.2 / 10 on 5m | Matched, 14 Oct 2026 |
| 2 Leg data | Step 1 output | Done |
| 3 Labels | Ash's reading of named swings | Done |
| 4 Breaks | Named 1D and 5m candles: 22182.55 attempt, 24571.75 gap fail and re-break, 22534.40 white-space retest and held-then-failed | Matched, 16 Oct 2026 |
| 5 Trend state | Named events: 1D 23 May 2024, 4 Mar, 3 Aug, 24 Sep 2026; 5m 9 and 12–13 Oct 2026 | Matched, 16 Oct 2026 |
| 6 Text | Ash reads the sentences next to the chart | Real run 16 Oct 2026: trends match the STRUCTURE check |

A lookahead test runs once on step 1: compute on data cut at a date, then on full data, and confirm no pivot confirmed before the cut changes.

## Open decisions for Ash

All answered, 14–16 Oct 2026.

- [x] Parity target: Zig Zag on tv.dhan.co (5% / 10 on 1D, 0.2% / 10 on 5m).
- [x] Swing settings: the per-timeframe Zig Zag table instead of pivot lengths.
- [x] Folder: `price_action/swing_points/` approved.
- [x] Two highs in a row: not needed, Zig Zag alternates.
- [x] Equal highs and lows: a tolerance per timeframe (5m 0.05% up to 1D/1W/1M 0.50%).
- [x] Break confirmation: close = break, wick = attempt.
- [x] Timeframe order: all six together in the check report.

## Deferred

These build on the six steps and wait for the investor / India-market research pass.

**Ash's trendline method** (from his charts, 14 Oct 2026): horizontal S&R drawn from the lowest price upward on 1M; trendlines through the most swing touches; steeper trendlines as the trend accelerates, often a fan from one major low (the 2020 low). When the steepest line breaks, price tends to travel to the next line in the fan. All of it is built from step 1's swing points, so it becomes its own module after market structure.

- **Index confirmation:** Nifty 50 structure confirmed by Bank Nifty; needs Bank Nifty OHLCV stored first.
- **Strong vs weak swings and impulse vs corrective legs:** graded from the leg data stored in step 2.
- **Multi-timeframe alignment:** one line saying whether 1W, 1D and 15m structure agree.
- **Range and phase detection** (point 3 of price action): built on top of this trend state.
- **Frontend markers:** HH/HL/BOS/CHoCH labels on the Lightweight Charts view.

## Progress log (as of 16 Oct 2026)

Steps 1–6 are built, tested on Ash's machine and checked on his chart; market structure is complete (16 Oct 2026). Spec: MARKET\_STRUCTURE.md; runbook v1.5 §4.7; build log entry 14→16 Oct. Pick up from the first open line of the status table.

| Item | Status | Files / decision |
| --- | --- | --- |
| Step 1: Zig Zag swings | Done, matches tv.dhan.co on 1D and 5m | `swing_points/zigzag_swings.py` (port of TradingView ZigZag v9, depth halved internally, first of equal highs wins, projections not ported), `test_zigzag_swings.py` 18 tests |
| Zig Zag settings | Done | `swing_points/zigzag_settings.py`: deviation 1M/1W/1D 5%, 60m 1.25%, 15m 0.5%, 5m 0.2%, depth 10; 60m/15m derived between Ash's 5m and 1D choices (no study gives per-TF values) |
| Temporary-lock view | Done, checked on Nifty | `swing_points/provisional_swings.py`: 5m locked swings + 60m deviation = provisional hourly; 60m locked swings + 5% = provisional daily; direction = last line (last swing high = UP) with the price that flips it. Hourly direction is the direction traded on 5m |
| Step 2: leg data | Done | `swing_points/swing_legs.py`: leg points, %, bars, retracement % |
| Step 3: labels | Done | `market_structure/swing_labels.py`: HH/HL/LH/LL/EQH/EQL plus zone, touches, neckline (bare minimum; full logic belongs to chart patterns) |
| Equal tolerance | Closed 16 Oct | Per timeframe: 5m 0.05% (≈11 pts), 15m 0.10%, 60m 0.20%, 1D/1W/1M 0.50% (≈113 pts). In the repo (zigzag\_settings.py, equal\_tol\_pct) |
| Check script | Done | `swing_points/zigzag_check.py` writes `logs/zigzag_test_logs/zigzag_check.log` |
| Step 4: break / retest | Done 16 Oct, checked on tv.dhan.co (1D + 5m) | market\_structure/level\_breaks.py + test\_level\_breaks.py (17 tests). Attempt, confirmed, gap, cleared, retest, held, failed, re-break cycles. Decisions below |
| Step 5: BOS / CHoCH + trend | Done 16 Oct, checked on tv.dhan.co (1D + 5m) | market\_structure/structure\_events.py + test\_structure\_events.py (12 tests). Check log STRUCTURE section: all 6 TFs + provisional 60m and 1D; --events N (0 = full history). Decisions below |
| Step 6: plain-language text + alerts | Done 16 Oct, real run checked (all 8 views) | market\_structure/market\_structure\_snapshot.py + test\_market\_structure\_snapshot.py (12 tests). Same shape as macd\_snapshot. Decisions below |

**Decisions:** wick (high/low) is the touch point for levels and trendlines. A break is decided by the close; a wick beyond is an attempt (step 4). Ash's live view is 4 screens: 1D, 60m, 15m, 5m (trades on 5m).

**Open items:**

- Chart patterns section: a top counts as revisited when a later candle's body spans the level, or when price gaps through it.
- Check the example equal pairs (D1–D6, M1–M4) on the chart, then tune the tolerances.
- Backtest each indicator and the combined view on history.
- Predictor: store the daily analysis with probabilities and score it next day, week and month; the score history becomes its own indicator.

**Reminder:** export this plan as Markdown next to the specs (Dev Documents\\Development Docs\\Fortuna Indicators\\) and commit it with the market-structure code.

### Step 4 decisions: level breaks (16 Oct 2026)

Research done in rule #19 order (books, then studies); Ash's observations recorded.

- **Levels for now:** swing highs and lows only. S&R lines and trendlines come later and reuse the same break logic.
- **Events per level:** break attempt (wick beyond), break confirmed (close beyond), gap tag (candle opens beyond), cleared (first candle fully outside the tolerance band), retest (back within the band, only after cleared), held (close back on the break side after a retest), failed (close back through, past the band).
- **White space before a retest (Bulkowski).** A retest only counts after price has cleared the band. Before this rule almost every retest was the very next candle overlapping the band (Fri 9 Oct 2026 14:00 on 22534.40 was not a pullback). Not cleared yet = price hugging the level, not the strong no-retest case.
- **Held is not final.** The level is still watched after a hold; a later close back through the band reads HELD … -> FAILED … (22534.40 held Fri 9 Oct 2026 14:30, failed 15:25).
- **Re-breaks.** After a failure the level is watched again from the next candle; each re-break is a new cycle (re-break #2, #3 …). Example: 24571.75 gap break Wed 4 Mar 2026, failed Thu 5 Mar, re-broken Fri 6 Mar 2026. Levels are watched forever; repeated tests are kept as labels.
- **Structure (BOS/CHoCH) uses break confirmed, i.e. a close.** Books (Bulkowski, Murphy) and the common structure tools measure breaks on closes. No study compared wick vs close, so the backtest can overturn this.
- **Provisional breaks:** higher-TF levels are checked against lower-TF candles. A 60m close beyond a daily level is a provisional daily break; a 5m close beyond an hourly level is a provisional hourly break. Confirmed when the higher TF's own candle closes beyond.
- **Every situation is kept as a label.** Whether to trade is decided later, after combining all indicators and chart patterns.
- **Low-weight labels stay first-class.** Markets change, so wick attempts, retests and failed breaks can become high-weight indicators later. Never drop them.

**Research findings behind the weights:**

| Finding | Source | Use in Fortuna |
| --- | --- | --- |
| A wick beyond a swing counts as a breakout; a close is stronger | Al Brooks | Break attempt vs break confirmed |
| Close beyond plus a filter (1–3% or 2 closes) on daily | Murphy, Edwards & Magee | Close for structure; filter not used (sized for mid-1900s daily stocks) |
| 58–65% of breakouts come back to the level | Bulkowski | Retest is common |
| Breakouts without a throwback did better in 97% (up) / 91% (down) of pattern types | Bulkowski, Study of Studies | No retest = stronger move |
| Staying above the level on the throwback: +40% vs +29% | Bulkowski | Held vs slipped below |
| Gap through the level helps (68% up / 85% down) | Bulkowski | Gap tag = strong |
| Busted patterns outperform (97% / 94%) | Bulkowski | Failed break = signal on the opposite side |
| Trends reverse at levels and speed up after crossing (stop orders cluster beyond levels) | Osler, NY Fed | Breaks continue; wicks just beyond levels can be stop hunts |
| Levels with more prior bounces bounce again more often; the effect fades with time | arXiv 2101.07410 | Touch count = level strength (later) |

**Deferred to chart patterns / volatility:** a strong-candle measure (Ash: strong candles crossing a level, then a gap, mean continuation; Nifty has no volume, so use the candle's range vs its average range); the body-spans-level and gap-through cases for tops; the retest time window (backtest decides).

### Step 5 decisions (16 Oct 2026)

A close beyond the latest swing known that day is a BOS or CHoCH; each day reports what it sees, and the next day informs same or different (Ash).

- **Meaning, printed on every report:** BOS = Break of Structure, indicates a trend continuation. CHoCH = Change of Character, indicates a potential trend reversal. Trends read uptrend / downtrend / neutral (never bull / bear).
- **Targets:** the latest swing high and swing low known that day, from the swing's detected time. No waiting for the swing to lock. A newer swing of the same kind replaces the target (TradingView pivot-based scripts work the same way).
- **Event:** first close beyond a target. Up break in an uptrend = BOS, uptrend continues; in a downtrend or neutral = CHoCH, trend flips to uptrend. Down mirrors it.
- **Start:** each timeframe is neutral on its first candle of history only; the whole history is scanned.
- **Final:** the event and any trend flip are final at the close of the breaking candle, using only what was known that day.
- **One event per level:** failure, retest, held-then-failed and re-breaks are labels on the event (from step 4). They never undo an event or flip the trend; only a CHoCH flips it.
- **Worked example (Ash):** 3 May 2024 high 22794.70 → BOS Thu 23 May 2024; failed Tue 4 Jun (election-day crash); re-broken Thu 6 Jun (close 22821.40); trend stays uptrend.
- **Gap case:** Fri 9 Oct 2026 09:15 gap closes above two known highs → one CHoCH on the newest (22256.00), no extra BOS.
- **Tried and dropped the same day:** waiting for the swing to lock (Zig Zag's 5 candles), skipping already-broken swings, and a LATE label. Ash: label what today shows, no late events.
- **Also dropped:** requiring the close beyond the level plus the band (Murphy-style filter). Ash counts the 6 Jun 2024 close (+27 pts) as a break.
- **Provisional (Ash's method):** same logic on higher-TF levels with lower-TF candles: provisional 60m from 5m, provisional 1D from 60m.
- **Report:** the check log STRUCTURE section runs 1mo, 1w, 1d, 60m, 15m, 5m + both provisional views; --events N sets events shown (default 10, 0 = full history); monthly dates print as month + year.

**Trend now (Tue 13 Oct 2026 close):** monthly uptrend; weekly and daily downtrend (CHoCH up above 24774.30); 60m, 15m, 5m and provisional 60m uptrend; provisional 1D downtrend.

**Open notes for later (backtest or chart-pattern stage):** thin white space (a 13-pt clearance counts the same as a big move); levels keep acting after the outcome (role reversal, Tue 13 Oct 2026 on 22534.40); a failure by about 3 pts on the day's last candle (Fri 9 Oct 2026 15:25); a break-margin label ("beyond by X pts") to tell strong from weak breaks; the last weekly and monthly candles are still forming.

**Lookahead test (16 Oct 2026):** events built on data cut at a date vs on full history differed on 10 of 50 cut dates. Cause: a close beyond the last, not-yet-locked swing is a BOS that day; if Zig Zag later moves that swing, a rebuild from the finished Zig Zag no longer sees it. Today's report is always right. Ash: no code change; the live record = the stored daily snapshots (open item).

### Step 6 decisions (16 Oct 2026)

The snapshot follows macd\_snapshot.py exactly, using the shared indicator\_common helpers.

- **Views:** 1M, 1W, 1D, 60m, 15m, 5m + provisional 60m (from 5m) and provisional 1D (from 60m).
- **Texts per view:** header with close; trend + since + how long; the close above / below that changes it, with distance in pts and %; events on the latest candle (⚡ for CHoCH only, "on a gap" when it applies); step-4 labels on the latest candle; otherwise the last break's status. BOS / CHoCH meaning printed once at the top of the run.
- **Alerts:** every BOS and CHoCH on the latest candle, all views, both directions. Failed / retested / held / re-broken = text only (like MACD's higher-TF momentum turns).
- **Dates:** report\_date everywhere (Tue 13 Oct 2026, Week of Mon 12 Oct 2026, Oct 2026).
- **Directions:** both for Nifty; above (stocks) shows only up events as texts and alerts; states always included.
- **Wording fix after the real run:** "was re-broken" / "was retested" in texts; package values stay plain labels.
- **Speed:** the 5m view takes about 20 s (labels for every event in history); label only recent events before the watchlist (open item).

## Sources

- [LuxAlgo: Pivot Points Alerts](https://www.luxalgo.com/library/indicator/LY5jsCca-pivot-points-alerts/)
- [replay-lab (pivot tie-break)](https://github.com/gregkitz/replay-lab)
- [Swing High Low Adaptive](https://ar.tradingview.com/script/yRh7OKsh-Swing-High-Low-Adaptive/)
- [LuxAlgo: Market Structure](https://www.luxalgo.com/library/indicator/ud6AQSm2-market-structure/)
- [BOS & CHoCH (TradingView)](https://www.tradingview.com/script/Tmwxv2Wg/)
- [smartmoneyconcepts (Python)](https://github.com/joshyattridge/smart-money-concepts)
- [MTF Clean Pivot Points](https://in.tradingview.com/script/RTtUtMu6-MTF-Clean-Pivot-Points/)
- [Market Structure (BOS / CHOCH), Advanced & Improved](https://il.tradingview.com/script/0t7puDyH-Market-Structure-BOS-CHOCH-Advanced-Improved/)
- [Incredible Charts: Dow Theory trends](https://www.incrediblecharts.com/technical/dow_theory_trends.php)
- [LuxAlgo: Dow Theory](https://www.luxalgo.com/library/concept/dow-theory/)
- [Strike: Dow Theory](https://www.strike.money/technical-analysis/dow-theory)
- [LuxAlgo: ZigZag](https://www.luxalgo.com/library/indicator/zigzag/)
