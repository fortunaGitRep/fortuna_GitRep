# EMA Break Watch — spec

_Version 1 — 2026‑10‑19. Code: `backend/modules/Module_F_Tech_Indicators_Funnel/trend_indicators/ema_break/`.
Evidence: the EMA S&R study (`SUPPORT_RESISTANCE.md` §5, code `studies/ema_sr/`)._

---

## 0. In plain English

On Nifty, EMAs are **not** support or resistance: when price touches an EMA it closes through it about 7 times
in 10, which is no better than a random line, and pullbacks to an EMA in a trend do not bounce more than chance
(`SUPPORT_RESISTANCE.md` §5). So Fortuna does not draw EMAs as S&R lines. Instead it watches EMA 50 / 100 / 200 as
levels that are **likely to break**:

1. **Near:** price comes within one average candle move of the EMA. Told once, when it first comes near.
2. **Break:** a candle closes through the EMA. Told with the size of the breaking candle — **tall** (≥ 2× the
   average candle), **normal** or **small**.
3. **Odds:** with every break, how often breaks like it (same timeframe, same EMA, same candle size) stayed broken
   after 10 candles and how often price was back within 3 candles — from the instrument's own history.

A tall-candle break of a slow EMA lasts about twice as often as a small-candle break. Whether to trade it is
decided later, with the other indicators (ADX, MACD, the EMA stack) — these are labels, not trade calls.

Built for live trading (Ash, 2026‑10‑19: "no noise that does not help"): live alerts only on 60m / 15m / 5m, only
EMA 50 / 100 / 200, ⚡ only for a tall-candle break, a near alert only when new; everything else is a text line.

---

## 1. Scope

| | |
|---|---|
| Instrument | Any (Nifty 50 first). Stocks: `--key … --daily-domain universe`; 60m / 15m / 5m exist only for F&O stocks |
| Live timeframes | 60m, 15m, 5m (Ash's trading screens) |
| Context timeframes | 1M, 1W, 1D — one line each in the pre-market read; no alerts (a daily EMA can only break at the close) |
| EMAs | 50, 100, 200 (TradingView method, `compute_emas`) |
| Not watched | EMA 5 / 13 / 26: their breaks mostly reverse — on 5m only 6% / 18% / 25% are still broken after 10 candles (study) |

Data comes through `indicator_ohlcv_reader.read_for_indicators` (reader rules applied there). Nothing here fetches or
writes data except its own log files.

---

## 2. Rules

All touch / break / X definitions are the tested ones from `indicator_common/line_reaction_study.py` (the same
code the study used — single source of truth).

| Term | Rule |
|---|---|
| X (average candle move) | mean \|close − previous close\| over the last 20 candles (the S&R studies' measure; Garzarelli et al. 2014, Chung & Bellotti 2021), rolling so it follows the price scale |
| Near | \|close − EMA\| ≤ X on the latest candle |
| Near, new | near now and not near on the previous candle — the only near that is an alert |
| Touch episode | armed by a candle fully clear of the EMA; starts when a wick reaches it; each touching candle = one touch |
| Break | the first candle in the episode that **closes** beyond the EMA (Ash's rule: wick = attempt, close = break) |
| Bounce | the first close at least X away on the original side |
| Breaking-candle size | candle range ÷ average range of the last 20 candles: **tall ≥ 2×** (Bulkowski's "tall candle" = 2× the average height), **normal 1–2×**, **small < 1×** |
| Odds | past breaks of this timeframe × EMA × size: % still broken after 10 candles (never closed back on the original side within 10 candles), % back within 3 candles (closed back on the original side within 3) |
| Breaks counted in odds | only breaks with more than 10 candles after them (outcome known) |

**Why candle size and nothing else** (study, 5m / 15m / 60m, EMA 50 / 100 / 200, 10,685 breaks, 2022–2026):

| Breaking candle | Breaks | Still broken after 10 candles | Back within 3 candles |
|---|---|---|---|
| Tall (≥ 2×) | 2,380 | **50.3%** | **30.7%** |
| Normal (1–2×) | 5,446 | 32.4% | 46.0% |
| Small (< 1×) | 2,859 | 24.9% | 56.8% |
| All | 10,685 | 34.4% | 45.5% |

- Same on each timeframe (tall / small, still broken after 10): 5m 49% / 24%, 15m 53% / 26%, 60m 53% / 25%.
- Same out of sample: chosen on 2022–24 (tall 51% / 31%), unchanged on 2025–26 (tall 50% / 30%).
- Body % (cut-offs 30–90%) and close position in the range (50–90%) each moved the result only 1–5 points, so
  they are not used. Size 2× is a book definition, not fitted — nothing here needs tuning later.
- 10 candles / 3 candles are facts reported from history, not settings.

---

## 3. Texts and alerts

Illustrative lines (odds figures are the real Nifty history for that case on 16 Oct 2026; the prices and sizes are examples):

```
⚡ 15m: closed below EMA 200 (22,950.10) on a TALL candle (2.3x avg). History, tall-candle breaks (132): still broken after 10 candles 58%, back within 3 candles 30%.
5m: closed below EMA 50 (23,100.71) on a small candle (0.8x avg). History, small-candle breaks (989): still broken after 10 candles 23%, back within 3 candles 57%.
60m: price 32.10 above EMA 200 (23,033.48) — near (avg candle move 49.67). History 60m EMA 200: 71% of touches ended in a break (248).
```

| Case | Text | Alert |
|---|---|---|
| Tall-candle break | yes, starts with ⚡ | yes |
| Normal / small break | yes | no |
| Near, first candle | yes | yes |
| Near, later candles | yes | no |
| Far from all three EMAs | timeframe prints "quiet" | no |

**Snapshot layout:** title, summary line (`EMA break watch: 60m quiet · 15m ⚡ broke below EMA 200 (tall) · 5m near
EMA 50`), the three live views (header with as-of and close, then their lines or "quiet"), then "Context
(pre-market)" with one line per 1M / 1W / 1D (`1D (Fri 16 Oct 2026): close 23,146.15 — below EMA 50 23,313.95
(-0.72%), below EMA 100 23,655.45 (-2.15%), below EMA 200 24,013.87 (-3.61%)`).

**Package** (JSON-safe): `ok, instrument, name, live {60m, 15m, 5m}, context {1mo, 1w, 1d}, errors, summary,
alerts, texts`. Live view: `timeframe, as_of, as_of_text, close, lines, texts, alerts`; each line: `timeframe,
period, ema, close, distance_pts, distance_pct, avg_move, side, near, near_new, break {direction, range_vs_avg,
tier, touches, odds} | null, history {tall, normal, small, all: {n, held_pct, failed_pct}, touches,
touch_break_pct}`. Context view: `timeframe, as_of, close, levels [{period, ema, side, distance_pct}], texts`.

---

## 4. Code map

| File | Main functions |
|---|---|
| `trend_indicators/ema_break/ema_break.py` (pure) | `size_tier`, `history_odds`, `analyze_line`, `line_texts`; `WATCH_PERIODS`, `LIVE_TIMEFRAMES`, `TALL_X` 2.0, `SMALL_X` 1.0, `HELD_AFTER` 10, `FAILED_WITHIN` 3 |
| `trend_indicators/ema_break/ema_break_snapshot.py` | `live_view`, `context_view`, `summary_line`, `build_ema_break_snapshot` (never raises) + manual run |
| `indicator_common/line_reaction_study.py` (shared) | `average_move`, `find_episodes`, `touch_table` |
| `trend_indicators/ema/ema.py` | `compute_emas` (TradingView EMA) |

---

## 5. How to run (from `backend/`)

```
python -m modules.Module_F_Tech_Indicators_Funnel.trend_indicators.ema_break.ema_break_snapshot [--json] [--key KEY --name NAME --daily-domain universe]
python -m modules.Module_F_Tech_Indicators_Funnel.trend_indicators.ema_break.test_ema_break
python -m modules.Module_F_Tech_Indicators_Funnel.trend_indicators.ema_break.test_ema_break_snapshot
```
Logs: `logs\ema_break_test_logs\` — `ema_break_snapshot.log`, `ema_break_unit_tests.log`,
`ema_break_snapshot_unit_tests.log` (overwritten each run; first line = the command). The snapshot test prints
six "EMA break watch failed … R2 down" tracebacks on purpose (the never-raises test).

---

## 6. Tests — 19, all pass (Windows, 2026‑10‑19)

| File | Tests | Proves |
|---|---|---|
| `test_ema_break.py` | 10 | size tiers at 2× / 1×; tall break below support → ⚡ alert; small break → text only; break above resistance; near alert only on the first near candle; far → nothing; no EMA yet → None; odds per tier, breaks without 10 candles after are excluded; the break's odds = its tier's history; input not modified |
| `test_ema_break_snapshot.py` | 9 | three EMAs per live view; steady trend far above the EMAs → quiet; context sides and %; EMA not ready → "n/a"; summary wording; all six views built and JSON-safe (no default=); alerts collected; never raises when the reader raises; a failed timeframe is reported and the rest built |

The shared `line_reaction_study.py` has its own 17 tests (`indicator_common/test_line_reaction_study.py`).

---

## 7. Verification record (tv.dhan.co, Nifty 50, data to Fri 16 Oct 2026)

| Candle | EMA 50 (Fortuna / TradingView) | EMA 100 | EMA 200 |
|---|---|---|---|
| 5m Fri 16 Oct 2026 15:25 | 23,100.71 / 23,100.76 | 23,056.53 / 23,056.55 | 22,950.51 / 22,950.52 |
| 15m Fri 16 Oct 2026 15:15 | 23,004.90 / 23,004.96 | 22,871.14 / 22,871.21 | 22,765.11 / 22,764.41 |
| 60m Fri 16 Oct 2026 15:15 | 22,779.66 / 22,779.77 | 22,797.16 / 22,797.21 | 23,033.48 / 23,032.99 |
| 1D Fri 16 Oct 2026 | 23,313.95 / 23,313.95 | 23,655.45 / 23,655.45 | 24,013.87 / 24,013.87 |

- First reads were off on the long EMAs (1D EMA 200 by 17 pts, 60m by 19, 15m by 5) because the TradingView page
  had little history loaded; after scrolling back the daily matched to the paisa and the 15m EMA 200 moved from
  22,769.05 to 22,764.41, onto Fortuna's 22,765.11. Remaining intraday gaps of 0.01–0.7 pts = the known Upstox vs
  Dhan intraday feed difference (Indicators Runbook §6.2).
- Snapshot on 16 Oct 2026: 60m / 15m / 5m quiet (nearest EMA several average moves away, e.g. 5m 45.44 pts above
  EMA 50 with an average move of 10.09) — correct on the chart. No alerts.
- Pending: Mon 19 Oct 2026 — the 5m chart broke below EMA 200 (~22,979) around 12:00; after the evening refresh the
  snapshot should label it with its candle size (to add here).

---

## 8. Known behaviour — not errors

| Seen | Why |
|---|---|
| Long EMAs differ from a fresh TradingView page | TradingView calculates only over the history it has loaded — scroll back, re-read |
| A break shows "no past … breaks yet" | fewer than one past break of that size with 10 candles after it (new listings, short history) |
| No near alert although price is near | the near alert fires only on the first near candle; later candles are a text line |
| A break with no ⚡ | only tall-candle breaks are alerts, by design |

---

## 9. Open items

- Combine with strength indicators (ADX, MACD, EMA stack) when all indicators are combined — whether they sharpen
  the tall-break odds is to be tested then.
- Snapshots stored daily (live record) — with the predictor item.
- Frontend display of the alerts and odds.

---

## 10. Change log

- **v1 — 2026‑10‑19.** First version: EMA break watch built on the EMA S&R study; near / break / size / odds,
  live views 60m / 15m / 5m, context 1M / 1W / 1D, snapshot; parity with tv.dhan on all four timeframes.
