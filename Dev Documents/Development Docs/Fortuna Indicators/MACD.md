# Fortuna — Indicator Spec: MACD (Moving Average Convergence Divergence)

**What this doc is:** the single source of truth for how Fortuna calculates and reads MACD — the exact
formulas, settings, rules, thresholds and outputs Fortuna uses. Other books and traders read MACD in
different ways; this doc records only what **Fortuna** does. Same layout as `EMA.md`, stored in
`Dev Documents\Development Docs\Fortuna Indicators\`.

_Version 3.1 — 2026‑10‑12 (§0 plain‑English definition; runbook `Fortuna-Indicators-Runbook.md`). v3 — **MACD complete (parts 1–4): values, trend / momentum states, labels, events and
texts on all six timeframes, verified against TradingView (tv.dhan) — values and cross dates exact.** Code:
`backend/modules/Module_F_Tech_Indicators_Funnel/trend_indicators/macd/`._

---

## 0. What MACD is, how it works, how to read it (plain English)

**What it is.** MACD (Moving Average Convergence Divergence, Gerald Appel, 1970s) measures **the gap
between a fast and a slow EMA** of the close. When the fast EMA pulls away above the slow one, upward
momentum is building; when the gap shrinks, the move is losing steam. It is a **momentum and trend**
indicator, drawn in its own panel under the price chart.

**How it works — three things TradingView draws:**

| Line | What it is | Plain meaning |
|---|---|---|
| **MACD line** (blue) | EMA12 − EMA26 of the close, in index points | above 0 = the 12 EMA is above the 26 EMA (short‑term trend up); below 0 = down. The further from 0, the stronger the push. |
| **Signal line** (orange) | EMA9 of the MACD line | a smoothed, slower copy of MACD — the "trigger" line |
| **Histogram** (bars) | MACD − signal | how far MACD is from its own average = is momentum **accelerating or slowing** |

**Histogram colours (TradingView's four):** dark green = above 0 and growing (bullish momentum
accelerating) · light green = above 0 but shrinking (bullish momentum fading) · light red = below 0 but
shrinking (bearish momentum fading) · dark red = below 0 and growing (bearish momentum accelerating) (§3.3).
A light colour after a dark one is the earliest warning that the move is tiring.

**How to read it — Fortuna's two views:**
1. **Trend (`trend_macd`) — MACD vs 0.** Above zero = uptrend, below = downtrend. A **zero‑line cross** is
   the same moment as the 12 EMA crossing the 26 EMA (slow, confirmed).
2. **Momentum (`momentum_macd`) — MACD vs signal and the histogram.** MACD crossing **above** the signal =
   momentum turning up; **below** = turning down. Where it happens matters: a bullish cross **below zero** is
   an early reversal sign inside a downtrend; **above zero** it is the uptrend resuming.
3. **Combined label:** both up = STRONG UPTREND; trend up but momentum down = UPTREND PAUSING (pullback);
   trend down but momentum up = DOWNTREND WEAKENING (bounce possible); both down = STRONG DOWNTREND (§7).

Example (Nifty daily, 9 Oct 2026): MACD −360.57 below 0 and below the signal −331.79 → STRONG DOWNTREND;
histogram −28.78 light red → bearish momentum fading for 1 day ("watch for a bullish MACD cross").

**Good at:** spotting momentum turning before price structure (EMA stack) does, and telling a pullback
from a reversal. **Weak at:** (1) **whipsaws** — on 5m/15m the signal line is crossed many times a day;
(2) **no overbought/oversold levels** — MACD is in points and unbounded, so "−360" has no fixed meaning and
can't be compared across instruments (that is what the extra **PPO** column is for: MACD as % of price);
(3) it **lags** (built from EMAs). **Divergence** (price makes a new low but MACD doesn't) is a well‑known
use; Fortuna does not detect it yet.

**How it fits:** EMA = direction, MACD = momentum, ADX = strength. A MACD cross with ADX below 20 is
happening in chop (see `ADX.md` §0).

---

## 1. Scope

| Item | Fortuna's choice |
|---|---|
| Instruments | **Nifty 50 now.** Watchlist / options stocks later — same code, no changes. |
| Timeframes | **1M, 1W, 1D, 60m, 15m, 5m** — all supported and verified (§10). 2h / 4h = open item (§12). Same code for every timeframe — periods are counted in **candles** of that timeframe. |
| Settings | **Fast 12 · Slow 26 · Source close · Signal 9 · Oscillator MA EMA · Signal MA EMA** — TradingView's defaults, confirmed from Ash's settings dialog 2026‑10‑11. No other settings. |
| Parity rule | Every value TradingView shows must equal Fortuna's (§3). |
| Reference charts | **tv.dhan.co** for Nifty (Ash trades Nifty options on Dhan); **tv.upstox.com / pro.upstox.com** for stocks (Ash buys swing equity on Upstox). All three are broker‑hosted TradingView charts — see §3.6. |
| **Display rule** | **Everything TradingView shows is shown by Fortuna** (MACD, signal, histogram values and the histogram colour). Anything Fortuna adds (PPO, labels, texts, held counts) is **extra on top — never a replacement** for a TradingView number. (Ash, 2026‑10‑11) |

---

## 2. Input data

- Candles from R2, read through `indicator_ohlcv_reader.read_for_indicators(key, domain, timeframe)`:
  - 1D / 1W / 1M: `upstox/indices/Nifty_50.parquet` (from 2000‑01‑03).
  - 60m / 15m / 5m: `upstox/nse_indexes_intraday/Nifty_50.parquet` (from 2022‑01‑03; 7 / 25 / 75 bars a
    day, first bar 09:15).
- **Reader rule 1:** bars with a zero or negative price are dropped (already built).
- **Reader rule 2 (built — MACD part 1):** drop intraday bars starting at/after 15:30 IST on any day
  that also has regular‑session bars (Nifty: 92 days, 2022‑03‑24 … 2025‑05‑21). A day whose bars are
  **all** after 15:30 (Muhurat evening) is kept whole, per rule 3. Applies to every intraday read
  (Nifty and stocks); daily/weekly/monthly untouched.
- **Reader rule 3:** special sessions (Muhurat, 2024 Saturdays, Sunday budget day) are short days, not
  gaps. **No code needed** — MACD counts candles, so a short day simply contributes fewer candles.
- **Reader rule 4:** daily signals use the official daily candle — already true (the 1D file is used, not
  the last intraday close).
- **Indicators never fetch data.** The refresh button fetches first (before 4 pm → yesterday's close,
  after 4 pm → today's); MACD uses the **latest stored completed candle** of each timeframe and every
  output says "as of" which candle.
- **Upstox never returns the current day**, so until the live phase (§12) the 60m/15m/5m picture is also
  as of yesterday's last candle — a pre‑market view, not intraday alerting.
- **The latest weekly and monthly candle can be unfinished.** Upstox stores the running week/month: on
  9 Oct 2026 the "Oct" monthly candle (dated 1 Oct) held only 1–9 Oct and its close was Friday's close. Its
  MACD keeps changing until the week/month ends. TradingView shows the same unfinished candle (plus the
  live price during market hours). **Rule for texts:** call it "week to date" / "month to date", never a
  completed candle. Daily and intraday candles are always completed (Upstox excludes today).
- Bar counts used (9 Oct 2026): 1M 322 · 1W 1,398 · 1D 6,657 · 60m 8,249 · 15m 29,455 · 5m 88,449.

---

## 3. TradingView parity

### 3.1 TradingView's MACD
Ash's settings dialog (2026‑10‑11): Fast Length 12, Slow Length 26, Source Close, Signal Length 9,
Oscillator MA Type EMA, Signal Line MA Type EMA. TradingView's built‑in script is equivalent to:

```
fast   = ta.ema(close, 12)
slow   = ta.ema(close, 26)
macd   = fast - slow
signal = ta.ema(macd, 9)
hist   = macd - signal
```

`ta.ema` is the same function proven for `EMA.md` (§3–4 there): α = 2/(n+1), **seeded with the simple
average of the first n values**, blank before that.

### 3.2 Where each line starts

| Line | First value | Why |
|---|---|---|
| EMA12 | bar 12 | 12‑close seed |
| EMA26, **MACD** | **bar 26** | needs both EMAs |
| **Signal, histogram** | **bar 34** | 9‑value seed taken from the first 9 MACD values (bars 26 … 34) |

Fortuna reuses the proven `ema_tradingview()` for all three EMAs. The signal EMA is run over the MACD
series **starting at its first non‑blank value**, so its seed is the average of MACD bars 26 … 34 — the
TradingView behaviour. (Code examples that start each EMA from the first close — pandas
`ewm(adjust=False)` from bar 1 — are **rejected**, same reason as EMA.)

### 3.3 Histogram colour (TradingView's exact rule)

| Condition (hist today vs hist yesterday) | TradingView colour | Fortuna state |
|---|---|---|
| hist ≥ 0 and hist > yesterday | dark green | `above_growing` |
| hist ≥ 0 and hist ≤ yesterday | light green | `above_fading` |
| hist < 0 and hist > yesterday | light red | `below_fading` |
| hist < 0 and hist ≤ yesterday | dark red | `below_growing` |

Notes: **zero counts as above** and **"equal to yesterday" counts as not rising** — both copied from
TradingView's script so Fortuna's colour always equals the chart's. First histogram bar (34) has no
yesterday → state blank.

### 3.4 Crosses
Same rule as EMA (`ta.crossover` / `ta.crossunder`): cross above on bar t = A > B on t **and** A ≤ B on
t−1; cross below is the mirror. Equal today is not a cross; a blank on either bar → no cross.

### 3.5 How parity was proven (2026‑10‑11 / 12)
1. **Hand check before any code:** Ash's TradingView values for 7–9 Oct 2026 (daily) were worked through
   the formula using Fortuna's already‑proven EMA26 — signal recursion, implied EMA12, histogram and colour
   all matched (§10.1).
2. **Fortuna run vs TradingView, every timeframe** (`macd --dates …` / `--bars …`, outputs in §10.2):
   **all six timeframes match to the paisa.** Full record in §10.3.
3. **Every mismatch seen on the way had a known cause — none was a Fortuna error:**
   - *Loaded history (TradingView side).* TradingView computes over the history it has loaded. A fresh
     page load zoomed into recent months gave daily 9 Oct −360.65 / −331.91 (vs −360.57 / −331.79) and
     60m 9 Oct 15:15 22.83 / −25.49 / −48.32 (vs 22.85 / −25.52 / −48.37). After re‑hovering with more
     history loaded, both showed exactly Fortuna's numbers. The same chart still showed EMA 100/200 off
     (23,750.12 / 24,085.44 vs 23,747.77 / 24,077.44) — the EMA.md §3.5 effect.
   - *Live price in the current month (1M).* Read during market hours on 12 Oct, TradingView's Oct candle
     included the live price (~22,394). A close 126 points lower moves MACD by 126 × (2/13 − 2/27) =
     −10.06 and the signal by 0.2 × −10.06 = −2.01: 170.84 → 160.78 and 595.02 → 593.01 — exactly
     TradingView's numbers. Sep 2026 (finished) matched exactly.
   - *Wrong candle under the crosshair (5m).* A first read differed by 0.2–0.5; re‑hovering 15:15, 15:20,
     15:25 gave exact matches.
   - *15m 9 Oct 15:15:* first read −0.09 / 35.26 / 35.35 on the same fresh page load as the 60m above;
     re‑read on 12 Oct: **−0.08 / 35.25 / 35.33 = Fortuna exactly** (loaded history).
4. **Candle data is identical:** with `--ohlc`, Upstox's stored candles equal the O/H/L/C on tv.dhan.co,
   tv.upstox.com and pro.upstox.com (e.g. 60m 9 Oct 09:15 = 22,314.95 / 22,502.75 / 22,294.75 /
   22,480.70; 5m 15:15/15:20 flat at 22,535.65 and 15:25 L/C 22,520.45 on both sides). All three charts
   showed −21.81 / −87.44 / −65.63 for 60m 09:15 = Fortuna.
5. **Cross dates (part 3) checked on the chart:** 9 events across all timeframes — the candle where the
   histogram flips colour group (signal cross) or the MACD line crosses 0 (zero cross) — all on the same
   candle Fortuna reports (§10.4).

**Re‑verifying later:** read **completed** candles only (not today's forming one, not the running
week/month); let the chart load plenty of history (on a fresh load, re‑hover after moving around the chart);
make sure the crosshair label shows the exact candle (date **and year**, and time on intraday); compare with
`macd --timeframe … --dates … [--ohlc]` (§13). The `--ohlc` columns settle any doubt about the candle itself.

**Reading TradingView's legend:** `MACD 12 26 close 9 EMA EMA  <histogram>  <MACD>  <signal>` — the
order is **histogram, MACD, signal**. On Ash's chart the MACD line is **pink/red** and the signal
line is **black** (custom colours; TradingView's default is blue/orange). The price legend (top‑left of the
price pane) shows the candle's O / H / L / C.

### 3.6 Which "TradingView" — the broker charts Ash uses
None of Ash's charts is tradingview.com itself. Each broker embeds TradingView's charting software and
feeds it with **its own market data**:

| Site | What it is |
|---|---|
| **tv.dhan.co** | Dhan's TradingView‑based charts, free with a Dhan account; trade from the chart (options, futures, stocks, commodities), option chain, basket / stop‑loss orders, live P&L. Dhan states it is not the same as tradingview.com. **Reference chart for Nifty.** |
| **tv.upstox.com** | Upstox's TradingView‑partnership platform (launched Jan 2023), free on desktop; 104 indicators, 80+ drawing tools, trade from chart, up to 8 charts, option chain. Upstox's community calls it "inspired by TradingView" — some indicators missing, **no Pine Script**. |
| **pro.upstox.com** | Upstox Pro Web (main trading app) with a TradingView chart inside (`library=tv` in the URL); same Upstox data. **Reference charts for stocks: tv.upstox / pro.upstox.** |

What this means for Fortuna:
- Parity = **TradingView's formulas**, checked against whichever broker chart Ash reads. On completed
  candles Fortuna, Dhan and Upstox all agree (§3.5).
- **Long EMAs differ slightly between platforms** because each loads a different amount of history (1h on
  12 Oct: EMA 100 = 22,840.71 on Dhan vs 22,839.37 on Upstox; EMA 5/13 identical). MACD uses short EMAs and
  is barely affected.
- **Today's forming candle differs between brokers** (12 Oct live 1h MACD: −36.75 / −38.52 on tv.dhan and
  tv.upstox vs −36.49 / −38.46 on pro.upstox) — each takes its own live tick at a slightly different time.
  Matters for the live phase (§12).
- **Index volume:** Dhan shows a volume for Nifty (e.g. 74.12M on a 1h candle); Upstox shows none
  (Upstox index volume is always 0). Observation only — not used.

---

## 4. The three lines and PPO

| Output | Formula | Shown on TradingView? |
|---|---|---|
| **MACD** | EMA12 − EMA26 (points) | yes |
| **Signal** | EMA9 of MACD (points) | yes |
| **Histogram** | MACD − Signal (points) | yes, with colour (§3.3) |
| PPO | (EMA12 − EMA26) ÷ EMA26 × 100 (%) | **extra** — TradingView's separate "Price Oscillator" |

**PPO** is MACD expressed as a % of price. Raw MACD is in points, so it can't be compared across
instruments (a −300 MACD on Nifty ≈ −1.3%; a −10 MACD on a ₹500 stock = −2%). PPO is computed as a
**column only — no texts** — for the later best‑to‑least stock ranking. It never replaces MACD.

**No fixed overbought / oversold levels.** MACD has no upper or lower bound and is in points, so a level
like "MACD above X = strong" doesn't exist. The only true reference lines are **zero** and **the signal
line**.

---

## 5. trend_macd — "which direction?"

The slow view: **MACD vs zero** (identical to EMA12 vs EMA26).

| Field | Definition |
|---|---|
| Side | above / below / equal (zero) |
| Held | candles MACD has stayed on this side, **cross candle = 1** |
| Since | date/time the side began; "(start of data)" if it began with the history |
| Value | MACD in points (and PPO %) |

**Events:** zero‑line cross above / below (rule §3.4).

**Columns added by `trend_macd(df)`:** `trend_side` (+1 / −1 / 0 / blank), `trend_held` (cross candle = 1),
`trend_since` (`ts` of the first candle of the run), `trend_from_start` (True if the side began with the
history, i.e. no cross has been seen), `zero_cross_above`, `zero_cross_below`.

---

## 6. momentum_macd — "is it speeding up or slowing down?"

The fast view: **MACD vs signal** plus the **histogram**.

| Field | Definition |
|---|---|
| Side vs signal | above / below / equal |
| Held | candles on this side, cross candle = 1 |
| Since | when the side began |
| Gap | MACD − signal = histogram, in points |
| Histogram state | one of the 4 states (§3.3) |
| State held | candles the histogram has been in that state, first candle = 1 |

**Events:**
1. **Signal cross** above / below, tagged with where it happened:
   - bullish cross **below zero** → "early reversal sign (downtrend still in force)"
   - bullish cross **above zero** → "uptrend resuming (continuation)"
   - bearish crosses: mirror ("early top sign (uptrend still in force)" / "downtrend resuming").
   - MACD exactly 0 on the cross candle → tagged "at zero".
2. **Momentum turn** — the histogram changes between growing and fading on the same side of zero
   (e.g. `below_growing` → `below_fading`). The sign change itself is the signal cross (event 1).

**Columns added by `momentum_macd(df)`:** `mom_side`, `mom_held`, `mom_since`, `mom_from_start`, `mom_gap`
(= histogram), `signal_cross_above`, `signal_cross_below`, `signal_cross_zone` (`below_zero` /
`above_zero` / `at_zero` on a cross candle — where MACD is on that candle — else blank),
`hist_state_held`, `momentum_turn`.

**Bullish / bearish events** (used by the `directions` filter): bullish = MACD crosses above signal or
zero, or a momentum turn **to** `below_fading` (bearish fading) or `above_growing` (bullish growing);
bearish is the mirror.

---

## 7. Combined label (one per timeframe)

| trend_macd (MACD vs 0) | momentum_macd (MACD vs signal) | Label |
|---|---|---|
| above | above | **STRONG UPTREND** |
| above | below | **UPTREND PAUSING** (pullback) |
| below | above | **DOWNTREND WEAKENING** (bounce possible) |
| below | below | **STRONG DOWNTREND** |
| equal on either | — | **NEUTRAL** |
| MACD/signal blank | — | **n/a (not enough history)** |

`macd_label(df)` returns this per candle; `macd_all(df)` runs `compute_macd → trend_macd → momentum_macd`
and adds the `macd_label` column.

The histogram state is added after the label, with a hint when momentum is fading, e.g.
"STRONG DOWNTREND — bearish momentum fading (1 day), watch for a bullish MACD cross."

**Across timeframes** (one summary line, longest first; "(fading)" when the histogram is fading) — real,
9 Oct 2026 close:
`MACD: 1M uptrend pausing · 1W strong downtrend · 1D strong downtrend (fading) · 60m downtrend weakening · 15m uptrend pausing · 5m uptrend pausing`

---

## 8. Directions and thresholds

- **Directions:** same as EMA — **Nifty both** (calls and puts), **stocks above only**. Both are always
  calculated; the `directions` setting decides which become texts/alerts. States are always shown.
- **Thresholds: none.** Fortuna shows facts (held, gap, histogram state, zero context). Candidate filters
  to test on Nifty history before any is adopted:

| Filter | Idea | Status |
|---|---|---|
| Hold | cross must hold N candles (needed most on 5m/15m, where the histogram flips often) | shown as *held*; no threshold |
| Zero context | trust bullish crosses above zero more than below zero | shown as the *tag*; no rule |
| EMA agreement | discount a bullish MACD cross while the EMA stage is −5 | not yet combined |
| Gap size | ignore crosses with a tiny gap | shown as *gap*; no threshold |

---

## 9. Snapshot and texts (what Ash reads)

`macd_snapshot.build_macd_snapshot(key, name, timeframes, directions)` returns one JSON‑safe package per
timeframe plus the summary line. It **never raises**: a timeframe that can't be read or built comes back as
`None` with a plain reason in `errors`, and the other timeframes still come back. Texts are fixed templates
(no AI) — same data → same words. Time words follow the timeframe: day(s) / week(s) / month(s) on
1D / 1W / 1M, candle(s) on intraday; "Today" / "This week" / "This month" / "On this candle";
"yesterday" / "last week" / "last month" / "previous candle".

| Line (real wording) | When shown |
|---|---|
| `Nifty 50 · 1D — as of 9 Oct: close 22,520.45` (1W/1M add "(week to date)" / "(month to date)"; intraday "… 9 Oct 15:15 candle: close …") | always |
| `MACD −360.57 · Signal −331.79 · Histogram −28.78 (light red) [yesterday: MACD … (dark red)]` — the TradingView numbers | always |
| `STRONG DOWNTREND — bearish momentum fading (1 day), watch for a bullish MACD cross.` (hint only when fading) | always (`MACD n/a (not enough history).` on short history) |
| `On this candle: MACD crossed below signal, above zero → early top sign (uptrend still in force). Gap -0.08.` | signal cross on the latest candle (filtered by `directions`) |
| `⚡ Today: MACD crossed above zero → 12 EMA now above 26 EMA (trend turned up).` | zero cross on the latest candle |
| `⚡ Momentum turn: bearish momentum fading (histogram -28.78 vs -43.97) after 1 day of growing bearish momentum.` | momentum turn on the latest candle |
| `MACD holding above signal for 5 candles (since 9 Oct 11:15), gap +22.85.` (also for zero) | side 2–**5** candles old (`RECENT_BARS = 5`), began with a cross |
| `Bigger picture: MACD below zero since 27 Aug (30 days) · MACD below signal since 13 Aug (40 days).` ("(start of data)" if no cross seen) | sides held more than 5 candles |
| Summary line across timeframes (§7) | once, after all timeframes |

**Package fields (per timeframe):** `instrument, timeframe, directions, as_of, partial, previous,
close{today, previous}, values{today, previous}{macd, signal, histogram, hist_state, colour, ppo}, label,
trend{side, held, since, from_start}, momentum{side, held, since, from_start, gap},
histogram{state, colour, held, meaning}, events_today, last_events{zero_cross_above, zero_cross_below,
signal_cross_above, signal_cross_below, momentum_turn}, alerts, texts`.

**Alerts:** every signal cross, zero cross and momentum turn on the latest candle in the allowed
directions, per timeframe, e.g. `{'timeframe': '15m', 'type': 'signal_cross', 'direction': 'below',
'zone': 'above_zero', 'bullish': False}`.

---

## 10. Sample outputs and verification record

### 10.1 TradingView values, Nifty 50 daily (Ash's chart, read 2026‑10‑11)

| Date | Close | MACD | Signal | Histogram | Colour on chart | Fortuna state |
|---|---|---|---|---|---|---|
| 7 Oct 2026 | 22,603.05 | −344.03 | −313.60 | −30.42 | — | — |
| 8 Oct 2026 | 22,231.80 | −368.57 | −324.60 | −43.97 | dark red | `below_growing` (−43.97 ≤ −30.42) |
| 9 Oct 2026 | 22,520.45 | −360.57 | −331.79 | −28.78 | light red | `below_fading` (−28.78 > −43.97) |

**Hand check (before any code), using Fortuna's proven EMA26 values from `EMA.md` §10.1:**
- Signal recursion, α = 0.2: 8 Oct = 0.2 × (−368.57) + 0.8 × (−313.60) = **−324.59** ✓;
  9 Oct = 0.2 × (−360.57) + 0.8 × (−324.60) = **−331.79** ✓.
- EMA12 implied by TradingView: 8 Oct = −368.57 + 23,130.96 = 22,762.39 → 9 Oct = 22,762.39 +
  (2/13) × (22,520.45 − 22,762.39) = 22,725.17 → MACD = 22,725.17 − 23,085.74 = **−360.57** ✓.
- Histogram = MACD − signal on all three days ✓ (±0.01 rounding). Colour rule §3.3 matches both bars ✓.

So TradingView's MACD is exactly EMA12 − EMA26 on the same EMAs Fortuna already matches, with a 9‑EMA signal.

**What the chart says on 9 Oct:** MACD below zero (trend down) and below signal (momentum down) →
**STRONG DOWNTREND**, histogram light red → **bearish momentum fading (1 day)**. Last time the histogram
was above zero: ~30 Jul – 12 Aug 2026 (exact dates from Fortuna once part 3 is built).

### 10.2 Fortuna output (`macd`, data as of 9 Oct 2026 close)

Columns are in TradingView's legend order (histogram, MACD, signal).

```
1d   --dates 2026-10-07 2026-10-08 2026-10-09
bar               close   histogram       MACD     signal   colour          PPO %
2026-10-07     22603.05      -30.42    -344.03    -313.60   light red      -1.483
2026-10-08     22231.80      -43.97    -368.57    -324.60   dark red       -1.593
2026-10-09     22520.45      -28.78    -360.57    -331.79   light red      -1.562

1d   --dates 2020-10-09
2020-10-09     11914.20       72.57     110.38      37.80   dark green     +0.965

1w   --bars 3   (2026-10-05 = week of 5 Oct, complete on 9 Oct)
2026-09-21     23140.50      -68.16    -215.23    -147.06   dark red       -0.896
2026-09-28     22421.95     -129.65    -309.13    -179.48   dark red       -1.294
2026-10-05     22520.45     -153.48    -371.32    -217.85   dark red       -1.561

1mo  --bars 3   (2026-10-01 = October month to date, 1–9 Oct)
2026-08-01     24080.40     -318.53     479.57     798.09   light red      +2.016
2026-09-01     22620.45     -388.13     312.93     701.06   dark red       +1.320
2026-10-01     22520.45     -424.18     170.84     595.02   dark red       +0.724

60m  --bars 3
2026-10-09 13:15:00+05:30    22544.40       18.14     -41.46     -59.59   dark green     -0.184
2026-10-09 14:15:00+05:30    22535.65       22.04     -32.05     -54.08   dark green     -0.142
2026-10-09 15:15:00+05:30    22520.45       22.85     -25.52     -48.37   dark green     -0.113

15m  --bars 3
2026-10-09 14:45:00+05:30    22563.20        6.07      40.63      34.56   light green    +0.181
2026-10-09 15:00:00+05:30    22535.65        3.19      38.54      35.36   light green    +0.171
2026-10-09 15:15:00+05:30    22520.45       -0.08      35.25      35.33   dark red       +0.157

5m   --bars 3
2026-10-09 15:15:00+05:30    22535.65       -4.75       9.77      14.52   dark red       +0.043
2026-10-09 15:20:00+05:30    22535.65       -4.93       8.35      13.29   dark red       +0.037
2026-10-09 15:25:00+05:30    22520.45       -5.88       5.94      11.82   dark red       +0.026
```

**Reading it across timeframes (9 Oct close), using the §7 labels:**

| Timeframe | Label | Histogram |
|---|---|---|
| 1M (month to date) | UPTREND PAUSING (MACD > 0, below signal) | bearish momentum growing |
| 1W | STRONG DOWNTREND | bearish momentum growing |
| 1D | STRONG DOWNTREND | bearish momentum fading |
| 60m | DOWNTREND WEAKENING (MACD < 0, above signal) | bullish momentum growing |
| 15m | UPTREND PAUSING — MACD crossed below signal on the last candle | — |
| 5m | UPTREND PAUSING | bearish momentum growing |

Plain words: the bigger trend is down; Friday's intraday bounce lifted the 60m, and it was already fading
into the close on 15m/5m.

### 10.3 Verification record (Fortuna vs TradingView, histogram / MACD / signal)

| Timeframe, candle | Fortuna | TradingView (chart) | Result |
|---|---|---|---|
| 1D 7 Oct 2026 | −30.42 / −344.03 / −313.60 | same (tv.dhan) | ✅ exact |
| 1D 8 Oct 2026 | −43.97 / −368.57 / −324.60 | same (tv.dhan) | ✅ exact |
| 1D 9 Oct 2026 | −28.78 / −360.57 / −331.79 | same (tv.dhan, 11 Oct and 12 Oct re‑read) | ✅ exact |
| 1D 9 Oct 2020 | 72.57 / 110.38 / 37.80 | same (tv.dhan) | ✅ exact |
| 1W week of 5 Oct | −153.48 / −371.32 / −217.85 | −153.48 / −371.32 / −217.84 | ✅ exact (rounding) |
| 1M Sep 2026 | −388.13 / 312.93 / 701.06 | same (tv.dhan) | ✅ exact |
| 1M Oct 2026 (to date) | −424.18 / 170.84 / 595.02 | −432.23 / 160.78 / 593.01 (live price) | ✅ explained (§3.5) |
| 60m 9 Oct 09:15 | −21.81 / −87.44 / −65.63 | same on tv.dhan, tv.upstox, pro.upstox | ✅ exact |
| 60m 9 Oct 15:15 | 22.85 / −25.52 / −48.37 | same (tv.dhan re‑read) | ✅ exact |
| 15m 9 Oct 15:15 | −0.08 / 35.25 / 35.33 | same (tv.dhan, 12 Oct re‑read; first read −0.09 / 35.26 / 35.35 = loaded history) | ✅ exact |
| 5m 9 Oct 15:15 | −4.75 / 9.77 / 14.52 | same (tv.dhan) | ✅ exact |
| 5m 9 Oct 15:20 | −4.93 / 8.35 / 13.29 | same (tv.dhan) | ✅ exact |
| 5m 9 Oct 15:25 | −5.88 / 5.94 / 11.82 | same (tv.dhan) | ✅ exact |

Colours matched on every candle checked.

### 10.4 Cross dates (parts 3) — Fortuna vs chart (tv.dhan, 12 Oct 2026)

| Chart | Fortuna event | TradingView on that candle (hist / MACD / signal) | Result |
|---|---|---|---|
| 1M | signal cross below, Jan 2025 (above zero) | −86.84 / 1,725.41 / 1,812.25 — first red bar | ✅ |
| 1M | zero cross above, Aug 2020 | −112.85 / 23.98 / 136.82 — MACD just above 0 | ✅ |
| 1W | signal cross below, week of 14 Sep 2026 (below zero) | −35.38 / −165.40 / −130.02 — first red bar | ✅ (TradingView labels it **Tue 15 Sep**: it names a weekly candle by the week's first trading day, Upstox by its Monday; Mon 14 Sep was not a trading day) |
| 1W | zero cross below, week of 2 Mar 2026 | −165.06 / −9.51 / 155.55 — MACD just below 0 | ✅ |
| 1D | signal cross below, 13 Aug 2026 (above zero) | −5.44 / 127.53 / 132.98 — first red bar | ✅ |
| 1D | zero cross below, 27 Aug 2026 | −39.76 / −8.06 / 31.70 — MACD just below 0 | ✅ |
| 60m | signal cross above, 9 Oct 11:15 (below zero) | 2.23 / −64.49 / −66.72 — first green bar; = Fortuna to the paisa | ✅ |
| 15m | signal cross below, 9 Oct 15:15 (above zero) | −0.08 / 35.25 / 35.33 — first red bar; = Fortuna | ✅ |
| 5m | signal cross below, 9 Oct 14:45 (above zero) | −0.22 / 18.13 / 18.35 — first red bar | ✅ |

### 10.5 Where Nifty stood, 9 Oct 2026 close (`macd --timeframe all --state`)

```
  1mo  2026-10-01 (month to date) UPTREND PAUSING          below growing (dark red), 2 month(s)
  1w   2026-10-05 (week to date)  STRONG DOWNTREND         below growing (dark red), 4 week(s)
  1d   2026-10-09                 STRONG DOWNTREND         below fading (light red), 1 day(s)
  60m  2026-10-09 15:15           DOWNTREND WEAKENING      above growing (dark green), 5 candle(s)
  15m  2026-10-09 15:15           UPTREND PAUSING          below growing (dark red), 1 candle(s)
  5m   2026-10-09 15:25           UPTREND PAUSING          below growing (dark red), 9 candle(s)
```
Details per timeframe (daily): MACD below zero since 27 Aug (30 days), below signal since 13 Aug (40 days);
last signal cross above 31 Jul (above zero); last zero cross above 18 Jun. Monthly: above zero since Aug
2020 (75 months), below signal since Jan 2025 (22 months). Weekly: below zero since 2 Mar (32 weeks),
below signal since 14 Sep (4 weeks).

### 10.6 Snapshot texts (`macd_snapshot`, live run 12 Oct 2026, data as of 9 Oct close)

```
Nifty 50 · 1M — as of Oct 2026 (month to date): close 22,520.45
MACD 170.84 · Signal 595.02 · Histogram -424.18 (dark red) [last month: MACD 312.93 · Signal 701.06 · Histogram -388.13 (dark red)]
UPTREND PAUSING — bearish momentum growing (2 months).
Bigger picture: MACD above zero since Aug 2020 (75 months) · MACD below signal since Jan 2025 (22 months).

Nifty 50 · 1W — as of week of 5 Oct (week to date): close 22,520.45
MACD -371.32 · Signal -217.85 · Histogram -153.48 (dark red) [last week: MACD -309.13 · Signal -179.48 · Histogram -129.65 (dark red)]
STRONG DOWNTREND — bearish momentum growing (4 weeks).
MACD holding below signal for 4 weeks (since week of 14 Sep), gap -153.48.
Bigger picture: MACD below zero since week of 2 Mar (32 weeks).

Nifty 50 · 1D — as of 9 Oct: close 22,520.45
MACD -360.57 · Signal -331.79 · Histogram -28.78 (light red) [yesterday: MACD -368.57 · Signal -324.60 · Histogram -43.97 (dark red)]
STRONG DOWNTREND — bearish momentum fading (1 day), watch for a bullish MACD cross.
⚡ Momentum turn: bearish momentum fading (histogram -28.78 vs -43.97) after 1 day of growing bearish momentum.
Bigger picture: MACD below zero since 27 Aug (30 days) · MACD below signal since 13 Aug (40 days).

Nifty 50 · 60m — as of 9 Oct 15:15 candle: close 22,520.45
MACD -25.52 · Signal -48.37 · Histogram 22.85 (dark green) [previous candle: MACD -32.05 · Signal -54.08 · Histogram 22.04 (dark green)]
DOWNTREND WEAKENING — bullish momentum growing (5 candles).
MACD holding above signal for 5 candles (since 9 Oct 11:15), gap +22.85.
Bigger picture: MACD below zero since 7 Oct 13:15 (17 candles).

Nifty 50 · 15m — as of 9 Oct 15:15 candle: close 22,520.45
MACD 35.25 · Signal 35.33 · Histogram -0.08 (dark red) [previous candle: MACD 38.54 · Signal 35.36 · Histogram 3.19 (light green)]
UPTREND PAUSING — bearish momentum growing (1 candle).
On this candle: MACD crossed below signal, above zero → early top sign (uptrend still in force). Gap -0.08.
Bigger picture: MACD above zero since 9 Oct 10:30 (20 candles).

Nifty 50 · 5m — as of 9 Oct 15:25 candle: close 22,520.45
MACD 5.94 · Signal 11.82 · Histogram -5.88 (dark red) [previous candle: MACD 8.35 · Signal 13.29 · Histogram -4.93 (dark red)]
UPTREND PAUSING — bearish momentum growing (9 candles).
Bigger picture: MACD above zero since 9 Oct 09:25 (73 candles) · MACD below signal since 9 Oct 14:45 (9 candles).

MACD: 1M uptrend pausing · 1W strong downtrend · 1D strong downtrend (fading) · 60m downtrend weakening · 15m uptrend pausing · 5m uptrend pausing
```
Alerts in that run: 1D momentum turn (bearish fading, counted bullish); 15m signal cross below (above zero).

---

## 11. Build plan (baby steps, each approved before the next)

| Part | What | Status |
|---|---|---|
| 1 | Reader rule 2 + allow 60m/15m/5m in `indicator_ohlcv_reader.py` | ✅ built 2026‑10‑11; 19 reader tests pass; live run: 5m and 15m each dropped 94 after‑close bars on 89 days, 60m none; the 3 Muhurat evenings (2022‑10‑24, 2023‑11‑12, 2024‑11‑01) kept — 89 + 3 = the 92 days the audit found |
| 2 | `macd.py` → `compute_macd(df)` + parity on all six timeframes; manual check with file logging and `--ohlc` | ✅ built 2026‑10‑11/12; 21 tests at that step (39 after part 3); parity §10.3 |
| 3 | `trend_macd(df)`, `momentum_macd(df)`, `macd_label(df)`, `macd_all(df)`; manual check `--state`, `--crosses N`, `--timeframe all` | ✅ built 2026‑10‑12; 18 tests; cross dates checked on the chart (§10.4) |
| 4 | `macd_snapshot.py`: package + texts per timeframe + summary line; never raises | ✅ built 2026‑10‑12; 21 tests; live run §10.6. **60 MACD tests pass on Windows.** |

---

## 12. Not used / deferred / open items

- **Divergence** (regular and hidden) — deferred to v2: needs swing‑point detection, which is subjective,
  and TradingView's built‑in MACD doesn't mark it (nothing to prove parity against).
- **2h / 4h MACD** — open item: resample from 60m, bars anchored to 09:15 each session the way
  TradingView draws them; parity check needed.
- **Live / intraday alerts** — open item: Upstox live feed (and its today's‑candles API, to confirm);
  alerts on **candle close**, with an optional "forming candle" preview (TradingView recalculates on the
  forming candle, so its signals can appear and vanish). Brokers' forming‑candle values differ slightly
  (§3.6), so live parity must be judged on closed candles.
- **Event list is flooded by momentum turns** (daily history: 2,389 events, mostly dark‑red/light‑red
  flips). Proposed, not yet built: `--crosses N` = zero + signal crosses only, `--turns N` = momentum
  turns; one log per mode (`macd_check_<tf>_state.log`, `…_crosses.log`) so runs don't overwrite each
  other. Also to test later: a minimum hold before a momentum turn is texted.
- **Frontend:** the snapshot package (§9) is ready for the indicators frontend (chart + texts), which is
  an important open item in the build log.
- **File logging for the reader's manual check** (`indicator_ohlcv_reader`) — still screen only. `ema` and
  `ema_snapshot` got file logging 2026‑10‑12 (`EMA.md` v2.2).
- **EMA on other timeframes** — open item: give EMA the same multi‑timeframe treatment (reader + "bars"
  wording); EMA code left untouched for now.
- SMA oscillator / signal types and other settings (5/35/5 etc.) — not used.
- **Stocks:** corporate‑action adjustment (see `EMA.md` §11) needed before MACD on affected stocks.
- **Snapshot for stocks:** `build_macd_snapshot` reads 1d/1w/1mo from domain `indices` only — add a domain option (`universe`) with the watchlist work. Manual checks already take `--domain universe`.
- Volume: not an input to MACD.

---

## 13. Code map

All MACD files in `backend/modules/Module_F_Tech_Indicators_Funnel/trend_indicators/macd/`:

| File / function | Status | Does |
|---|---|---|
| `__init__.py` | built | empty package marker |
| `macd.py` → `compute_macd(df, fast=12, slow=26, signal=9, price_col="close")` | built | returns a copy with `macd`, `macd_signal`, `macd_hist`, `macd_hist_state`, `ppo`; pure, raises `ValueError` on bad input (missing column, bad lengths, fast ≥ slow, unsorted `ts`) |
| `macd.py` → `hist_states(hist)` | built | the 4 colour states (§3.3); `HIST_COLOUR` maps them to TradingView's colour names |
| `macd.py` → `_ema_from_first_valid()` | built | runs `ema_tradingview` from the first non‑blank MACD value (signal seed, §3.2) |
| `macd.py` → `__main__` manual check | built | `--timeframe {1d,1w,1mo,5m,15m,60m}`, `--domain` (default by timeframe), `--key`, `--bars N`, `--dates …`, `--ohlc`; writes screen + `logs/macd_test_logs/macd_check_<timeframe>.log` (overwritten each run; first line = the command) |
| `test_macd.py` | built | 39 tests (21 from part 2 + 18 for states/labels/events, §14.1): plain‑loop Pine reference, start bars 26/34/35, signal seed, histogram, colour states incl. zero/equal, Ash's 9 Oct numbers, PPO (scale‑free), short history, non‑default index, input not modified, validation |
| `conftest.py` | built | pytest hook: writes PASSED/FAILED per test + failure text + summary to `logs/macd_test_logs/test_macd.log` (overwritten each run; only this folder's tests); no change to the pytest command |
| `macd.py` → `trend_macd(df)` | built | zero‑line side / held / since / from_start + zero crosses (§5) |
| `macd.py` → `momentum_macd(df)` | built | signal side / held / since / gap, signal crosses with zone, histogram state held, momentum turns (§6) |
| `macd.py` → `macd_label(df)`, `macd_all(df)` | built | §7 label; all of the above in one call |
| `macd.py` → `__main__` `--state`, `--crosses N`, `--timeframe all` | built | state of the latest candle; latest N events; all six timeframes + summary table in one run (`macd_check_all.log`) |
| `macd_snapshot.py` → `snapshot_from_bars(bars, name, timeframe, directions)` | built | pure: one timeframe's package + texts (§9) |
| `macd_snapshot.py` → `summary_line(snapshots)` | built | one line across timeframes |
| `macd_snapshot.py` → `build_macd_snapshot(key, name, timeframes, directions)` | built | reads each timeframe, never raises → `MacdSnapshotResult(ok, snapshots, errors, summary)`; manual check writes `logs/macd_test_logs/macd_snapshot.log` |
| `test_macd_snapshot.py` | built | 21 tests (§14.1) |

Reuses `ema.ema_tradingview()` from `../ema/ema.py` (no copy). Reader:
`market_data/upstox/indicator_ohlcv_reader.py` (D/W/M + 5m/15m/60m, rules 1–2).

**Run** (from `backend/`; every MACD output also lands in `logs\macd_test_logs\`):
```
python -m pytest modules/Module_F_Tech_Indicators_Funnel/trend_indicators/macd -v
python -m modules.Module_F_Tech_Indicators_Funnel.trend_indicators.macd.macd                       # 1d, latest 3 candles
python -m modules.Module_F_Tech_Indicators_Funnel.trend_indicators.macd.macd --dates 2026-10-07 2026-10-08 2026-10-09
python -m modules.Module_F_Tech_Indicators_Funnel.trend_indicators.macd.macd --timeframe 1w --bars 3
python -m modules.Module_F_Tech_Indicators_Funnel.trend_indicators.macd.macd --timeframe 1mo --bars 3
python -m modules.Module_F_Tech_Indicators_Funnel.trend_indicators.macd.macd --timeframe 60m --dates 2026-10-08 2026-10-09 --ohlc
python -m modules.Module_F_Tech_Indicators_Funnel.trend_indicators.macd.macd --timeframe 15m --bars 3
python -m modules.Module_F_Tech_Indicators_Funnel.trend_indicators.macd.macd --timeframe 5m --bars 3
python -m modules.Module_F_Tech_Indicators_Funnel.trend_indicators.macd.macd --state [--timeframe 15m]
python -m modules.Module_F_Tech_Indicators_Funnel.trend_indicators.macd.macd --crosses 15 [--timeframe 1d]
python -m modules.Module_F_Tech_Indicators_Funnel.trend_indicators.macd.macd --timeframe all --state     # where we stand on all six
python -m modules.Module_F_Tech_Indicators_Funnel.trend_indicators.macd.macd_snapshot [--timeframes 1d 60m] [--directions above] [--json]
python -m modules.market_data.upstox.indicator_ohlcv_reader --domain universe_intraday --timeframe 5m
```

---

## 14. Testing and verification (how MACD was proven)

Two layers, as for EMA: **unit tests** on hand‑made data (no R2) and **live verification** against Ash's
broker TradingView charts. A unit test passes because the code reproduces a value worked out
independently (by hand, from Ash's chart numbers, or by a separate plain loop written only for the test);
a live check passes because Fortuna's number equals the chart's number for the same completed candle.

### 14.1 Unit tests

**`test_macd.py` — 39 tests and `test_macd_snapshot.py` — 21 tests: 60 passing on Windows, 2026‑10‑12**
(log `logs\macd_test_logs\test_macd.log`). Part 2 tests (21):

| Test | What is checked | Why it passes (expected value comes from) |
|---|---|---|
| `test_matches_plain_pine_reference` | MACD and signal on a 120‑bar wave | a separate plain loop of Pine's `ta.ema` / `ta.macd` inside the test, equal to 1e‑9 |
| `test_first_values_at_bars_26_34_35` | MACD starts bar 26; signal/hist bar 34; colour bar 35 | §3.2 |
| `test_signal_seed_is_average_of_first_nine_macd` | signal at bar 34 = mean of MACD bars 26–34 | §3.2 (Pine SMA seed) |
| `test_macd_is_ema12_minus_ema26` | MACD = `ema_tradingview(12) − ema_tradingview(26)` | the proven EMA function |
| `test_histogram_is_macd_minus_signal` | hist = MACD − signal | definition |
| `test_signal_recursion_reproduces_tradingview` | Ash's 7–9 Oct numbers: signal = 0.2·MACD + 0.8·prev; hist = MACD − signal; colours dark red → light red | Ash's TradingView legend values (§10.1) |
| `test_hist_states_all_four_and_edges` | all 4 states, zero counts as above, equal‑to‑yesterday counts as not rising, blanks | TradingView's colour rule (§3.3) |
| `test_ppo_is_macd_as_percent_of_ema26`, `test_ppo_is_scale_free` | PPO formula; PPO same when prices are scaled, MACD not | §4 |
| `test_fewer_than_26_bars_all_blank_no_error`, `test_30_bars_macd_but_no_signal`, `test_constant_prices_give_zero_and_light_green`, `test_non_default_index` | short histories, flat prices, any index | §3.2, §3.3 |
| `test_input_not_modified`, `test_adds_exactly_the_macd_columns` | input safe; exactly the 5 new columns | contract |
| `test_bad_inputs_raise` ×5 (missing column, 0, 2.5, True, fast ≥ slow), `test_unsorted_bars_raise` | bad input raises `ValueError` | input contract |

Part 3 tests (18, in `test_macd.py`):

| Test | What is checked | Why it passes (expected value comes from) |
|---|---|---|
| `test_trend_side_held_since_and_zero_crosses` | MACD −2, −1, 1, 2, 0, −1 → sides, held 1/2/1/2/1/1, since, from_start, zero cross above on the 1st positive, below from 0 to −1 | hand‑worked; TradingView cross rule (≥ / ≤ on the previous bar) |
| `test_trend_matches_plain_loop` | held count on a 120‑bar wave | separate plain loop |
| `test_signal_cross_and_zone` | MACD/signal pairs → cross above on the candle after an equal one, below later; zones below/above zero; gap | hand‑worked |
| `test_signal_cross_at_zero_tag` | cross with MACD exactly 0 → `at_zero` | §6 rule |
| `test_momentum_turn_and_state_held` | histogram −5, −6, −4, −3, 1, 2, 1.5 → states, turns only on same‑side changes, side change = signal cross not turn, colour held counts | hand‑worked; §6 |
| `test_blank_breaks_run_and_from_start` | a blank candle ends a run; from_start only for the first run | §5 definition |
| `test_macd_label` ×8 | all label combinations incl. NEUTRAL and n/a | §7 table |
| `test_macd_all_consistent_on_wave`, `test_part3_input_not_modified`, `test_part3_missing_columns_raise`, `test_part3_unsorted_raises` | consistency (label vs sides, zone only on crosses), input safe, bad input raises | contract |

Part 4 tests (21, `test_macd_snapshot.py`):

| Test | What is checked |
|---|---|
| `test_header_per_timeframe` ×4, `test_month_and_intraday_dates` | header wording per timeframe ("as of", week/month to date, "candle"), ISO datetime for intraday |
| `test_numbers_line_shows_tradingview_values_today_and_previous` | the numbers line equals `compute_macd` for the latest and previous candle, with colour |
| `test_label_line_and_watch_hint` | label + "bullish momentum fading … watch for a bearish MACD cross" |
| `test_signal_cross_text_with_zone_meaning`, `test_zero_cross_text`, `test_momentum_turn_text` | each event text appears on the event candle with the right meaning |
| `test_directions_above_hides_bearish_events` | stocks setting: bearish cross kept in the record, not texted or alerted; label unchanged |
| `test_holding_line_after_signal_cross`, `test_bigger_picture_and_start_of_data` | holding line at 2–5 candles; bigger picture with "(start of data)" |
| `test_short_history_is_na_not_error`, `test_single_bar`, `test_json_safe` | n/a instead of errors; JSON without NaN |
| `test_summary_line_order_and_fading` | longest timeframe first, "(fading)", missing timeframe → "n/a" |
| `test_bad_inputs_raise_in_pure_core`, `test_build_all_timeframes_ok`, `test_build_one_timeframe_missing_others_still_built`, `test_build_bad_input_does_not_raise` | pure core raises on bad input; `build_macd_snapshot` never raises, reads each timeframe from its own domain, keeps the others when one fails |

**`test_indicator_ohlcv_reader.py` — 19 tests, all passing** (Windows, 2026‑10‑11):

| Tests | What is checked |
|---|---|
| `test_normal_read_drops_zero_bar_and_sorts`, `test_repeat_runs_give_same_result`, `test_input_frame_not_modified` | rule 1, sort by `ts`, output columns, repeatable |
| `test_file_missing`, `test_no_bars_for_timeframe`, `test_missing_column`, `test_every_bar_invalid`, `test_unsupported_timeframe_refused_without_reading` | expected misses → ok=False + reason, never raises |
| `test_r2_or_network_failure`, `test_missing_r2_config` | unexpected failures → ok=False, never raises |
| `test_log_success_is_one_info_line`, `test_log_expected_miss_is_one_warning`, `test_log_failure_is_one_error_with_traceback` | exactly one log line per outcome at the right level |
| `test_rule2_drops_after_close_bars_and_keeps_muhurat` | 15:30/15:35 bars dropped on a regular day; an 18:00 evening‑only day kept; counts and `last_ts` |
| `test_rule2_handles_fixed_offset_and_naive_timestamps`, `test_rule2_not_applied_to_daily`, `test_intraday_wrong_domain_gives_hint`, `test_rule2_bad_timestamps_not_ok_never_raises`, `test_log_rule2_success` | timestamp formats, daily untouched, helpful error, never raises, rule‑2 log line |

### 14.2 Live verification
- **Reader rule 2 on real data:** 5m/15m each dropped 94 bars on 89 days; the 3 evening‑only days kept
  were checked by a one‑off query to be exactly the Muhurat sessions (2022‑10‑24, 2023‑11‑12, 2024‑11‑01);
  89 + 3 = the 92 days the audit had found.
- **MACD values:** §3.5 (method) and §10.3 (every candle checked, Fortuna vs chart, with result).
- **Cross dates and labels:** §10.4 (9 events on all six timeframes, all on the same candle as the chart).
- **Snapshot texts:** live run read against the charts (§10.6).
- **Candles themselves:** `--ohlc` output equals the O/H/L/C on tv.dhan, tv.upstox and pro.upstox.

### 14.3 Known discrepancies

| Seen | Cause | Status |
|---|---|---|
| Daily 9 Oct 2026 −28.74 / −360.65 / −331.91 on a fresh page load | TradingView's loaded history (same chart had EMA 100/200 off) | re‑read: exact match |
| 60m 9 Oct 15:15 22.83 / −25.49 / −48.32 on a fresh load | loaded history | re‑read: exact match |
| 15m 9 Oct 15:15 −0.09 / 35.26 / 35.35 vs −0.08 / 35.25 / 35.33 | loaded history (same fresh load) | re‑read: exact match |
| Weekly candle label: TradingView "Tue 15 Sep" vs Fortuna "week of 14 Sep" | TradingView names the week by its first trading day, Upstox by its Monday (Mon 14 Sep not a trading day) | same candle, same values |
| 1M Oct 2026 −432.23 / 160.78 / 593.01 | live price inside the running month | explained by hand to the exact numbers (§3.5) |
| 5m 15:15 −4.92 / 10.12 / 15.04 (first read) | crosshair on a different candle | re‑read: exact match |
| Live (forming) 1h candle differs between Dhan and pro.upstox | each broker's live tick at a different moment | expected; compare closed candles only (§3.6) |

---

## 15. Change log

| Date | Change |
|---|---|
| 2026‑10‑11 | v1 — spec approved: TradingView defaults confirmed, parity method, histogram colour rule, trend_macd / momentum_macd split, combined label, PPO as extra column, display rule (all TradingView data shown, extras never replace), multi‑timeframe scope, divergence deferred, 2h/4h + live as open items. |
| 2026‑10‑12 | v2 — parts 1–2 built: reader rule 2 (Muhurat kept), `compute_macd`, manual check with file logging (`logs/macd_test_logs/`) and `--ohlc`, pytest log via `conftest.py`. Parity proven on 1M/1W/1D/60m/5m (15m within 0.02), with every mismatch explained (§3.5); broker charts documented (§3.6); weekly/monthly "to date" rule (§2); real outputs (§10.2) and verification record (§10.3). |
| 2026‑10‑12 | v2.1 — §14 testing and verification record: every unit test (MACD 21, reader 19) with what it checks and where the expected value comes from; live verification; known discrepancies. `conftest.py` now logs only this folder's tests. |
| 2026‑10‑12 | v3 — parts 3–4 built: `trend_macd`, `momentum_macd`, `macd_label`, `macd_all`, `--state` / `--crosses` / `--timeframe all`, `macd_snapshot.py` (texts per timeframe + summary line, never raises). 15m discrepancy closed (exact on re‑read) → all six timeframes exact; 9 cross dates checked on the chart (§10.4); real state, texts and summary recorded (§10.5, §10.6); tests 60 (§14.1). Open: split crosses vs momentum turns in the event list; frontend. |
| 2026‑10‑12 | v3.1 — §0 "What MACD is, how it works, how to read it" (three lines, histogram colours, trend vs momentum, strengths/weaknesses); code‑map test count corrected (`test_macd.py` 39). Runbook: `Fortuna-Indicators-Runbook.md`. Noted: `macd_snapshot` reads D/W/M from `indices` only — stocks need a domain option (open item). |
