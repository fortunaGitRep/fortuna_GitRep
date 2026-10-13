# Fortuna — Indicators Runbook (how to run and check everything without help)

**What this doc is:** the hands‑on manual for Fortuna's indicator layer. With only this doc and the code you
should be able to: run every indicator, read its output, find its log, check it against TradingView, spot
the known differences, fix the common errors, and add the next indicator the same way. The **what and why**
of each indicator lives in its spec (`EMA.md`, `MACD.md`, `ADX.md` — §0 of each is the plain‑English
definition; `RSI.md` too). Stored with the specs in `Dev Documents\Development Docs\Fortuna Indicators\`.

_Version 1.3 — 2026‑10‑13. Covers: indicator reader, EMA, MACD, ADX / DMI, RSI, shared helpers (`indicator_common/`)._

---

## 1. The indicators in one table

| Indicator | Answers | Timeframes | Spec | Code folder (under `backend/modules/Module_F_Tech_Indicators_Funnel/`) |
|---|---|---|---|---|
| **EMA** 5/13/26/50/100/200 | **Direction** on each horizon; stack stage −5…+5; crosses | 1D | `EMA.md` | `trend_indicators/ema/` |
| **MACD** 12/26/9 | **Momentum**: trend (MACD vs 0) + speeding up / slowing down (vs signal, histogram colour) | 1M 1W 1D 60m 15m 5m | `MACD.md` | `trend_indicators/macd/` |
| **ADX / DMI** 14 14 | **Strength**: is there a trend at all (ADX), who is in control (+DI vs −DI) | 1M 1W 1D 60m 15m 5m | `ADX.md` | `trend_indicators/adx/` |
| **RSI** 14 close | **Momentum level** 0–100 in seven zones (80 / 70 / 55 / 45 / 30 / 20), 45–55 = RSI S&R zone; every zone change and 50 cross | 1M 1W 1D 60m 15m 5m | `RSI.md` | `oscillators/rsi/` |

Read them together: EMA = direction, MACD = momentum, ADX = strength, RSI = momentum level. All are pure calculations on
stored candles: **they never fetch data and never write anything except their own log files.**

**Shared helpers** live in `backend/modules/Module_F_Tech_Indicators_Funnel/indicator_common/`, beside
`trend_indicators/` (and the coming `oscillators/`). Every indicator uses them; no indicator imports from another
indicator's folder:

| File | Holds |
|---|---|
| `smoothing.py` | `ema_tradingview` (Pine `ta.ema`), `rma_tradingview` (Pine `ta.rma`, Wilder) |
| `crosses.py` | `cross_above`, `cross_below` (Pine `ta.crossover` / `ta.crossunder`), `runs` (held / since / from start), `bar_labels` |
| `timeframes.py` | `TIMEFRAMES`, `TF_NAME`, `DEFAULT_DOMAIN` (timeframe → R2 domain), `UNIT` / `NOW` / `PREV` words, `is_intraday` |
| `text_format.py` | `num`, `to_int`, `iso`, `when`, `units`, `price`, `signed` — JSON‑safe numbers and dates for snapshot texts |

Moved there 2026‑10‑12 unchanged; `ema.py`, `macd.py`, `macd_snapshot.py`, `adx.py` still export the old names
(`ema_tradingview`, `_runs`, `_DEFAULT_DOMAIN`, `_num` …), so older imports keep working. New code imports from
`indicator_common` directly.

---

## 2. Before you run anything

1. **Open a terminal in the `backend` folder** — every command in this doc is run from there:
   ```
   cd D:\Takara\Fortuna\_Repository\backend
   ```
   Activate your Python environment the usual way first (the same one used for the data pipeline).
2. **`.env` must be in `backend/`** with the R2 (Cloudflare) settings — the indicators read candles from R2
   bucket `fortuna-ohlcv`. Quick test: run the reader (§4.1). If it prints `bars read …` the setup is fine.
3. **Make sure the data is fresh.** Indicators use the **latest stored candle**. Upstox never returns the
   current day, so: run the refresh **after 4 pm** to get today's close, before 4 pm you get yesterday's.
   ```
   python -m modules.market_data.upstox.refresh_index_ohlcv                       # Nifty daily/weekly/monthly
   python -m modules.market_data.upstox.refresh_universe_options_intraday_ohlcv   # Nifty + F&O stocks 5m/15m/60m
   python -m modules.market_data.upstox.refresh_universe_ohlcv                    # stocks daily/weekly/monthly
   ```
   (Full details, long gaps, Supabase auto‑pause: `fortuna_data_pipeline_flow.md` §2.4.)
4. **How the commands work:** `python -m a.b.c` runs the file `a/b/c.py` as a module so its imports resolve
   from `backend/`. **Any command + `--help`** prints its flags, e.g.
   `python -m modules.Module_F_Tech_Indicators_Funnel.trend_indicators.adx.adx --help`.
5. **Shortcut prefix.** Every indicator command starts with the same long path. In this doc
   `…trend_indicators` means `modules.Module_F_Tech_Indicators_Funnel.trend_indicators` and `…oscillators`
   means `modules.Module_F_Tech_Indicators_Funnel.oscillators` — type them in full.

---

## 3. The daily routine (pre‑market or after close)

```
# 1. refresh data (§2 step 3)
# 2. where do we stand — all three indicators, all timeframes
python -m modules.Module_F_Tech_Indicators_Funnel.trend_indicators.ema.ema_snapshot
python -m modules.Module_F_Tech_Indicators_Funnel.trend_indicators.macd.macd_snapshot
python -m modules.Module_F_Tech_Indicators_Funnel.trend_indicators.adx.adx_snapshot
python -m modules.Module_F_Tech_Indicators_Funnel.oscillators.rsi.rsi_snapshot
# 3. read the logs (same text as the screen)
#    backend\logs\ema_test_logs\ema_snapshot.log
#    backend\logs\macd_test_logs\macd_snapshot.log
#    backend\logs\adx_test_logs\adx_snapshot.log
#    backend\logs\rsi_test_logs\rsi_snapshot.log
```
Each snapshot prints a header ("as of" which candle), the TradingView numbers, a label, any event on the
latest candle (alerts), recent/bigger‑picture lines and — for MACD/ADX — one summary line across all six
timeframes. How to read each line: `EMA.md` §9, `MACD.md` §9, `ADX.md` §6, `RSI.md` §6.

---

## 4. Command reference

All read‑only. Every run **overwrites** its log file; the **first line of each log is the command that
produced it**. Logs live in `backend\logs\<indicator>_test_logs\`.

### 4.1 Indicator reader — "is the data there and what is the last candle?"

```
python -m modules.market_data.upstox.indicator_ohlcv_reader [--key KEY] [--domain DOMAIN] [--timeframe TF]
```
| Flag | Default | Values |
|---|---|---|
| `--key` | `NSE_INDEX\|Nifty 50` | any instrument key, e.g. `NSE_EQ\|INE002A01018` |
| `--domain` | `indices` | `indices` (Nifty D/W/M) · `universe` (stocks D/W/M) · `universe_intraday` (Nifty + F&O stocks 5m/15m/60m) |
| `--timeframe` | `1d` | `1d 1w 1mo 5m 15m 60m` (2h/4h refused — not stored) |

Prints bars read, bars dropped by reader rule 1 (bad prices) and rule 2 (intraday bars at/after 15:30),
first/last bar and the last 3 candles' O/H/L/C. **Screen only (no log file yet — open item).**
Examples:
```
python -m modules.market_data.upstox.indicator_ohlcv_reader
python -m modules.market_data.upstox.indicator_ohlcv_reader --domain universe_intraday --timeframe 5m
python -m modules.market_data.upstox.indicator_ohlcv_reader --key "NSE_EQ|INE002A01018" --domain universe
```
Expected for Nifty (data to 9 Oct 2026): 1d 6,657 bars · 1w 1,398 · 1mo 322 · 60m 8,249 · 15m 29,455 ·
5m 88,449; 15m and 5m drop 94 bars on 89 days by rule 2.

### 4.2 EMA (daily only)

```
python -m …trend_indicators.ema.ema [--key KEY] [--domain DOMAIN] [--bars N] [--dates D ...] [--crosses N] [--state]
python -m …trend_indicators.ema.ema_snapshot [--key KEY] [--domain DOMAIN] [--name NAME] [--directions both|above] [--json]
```
| Command / flag | Prints | Log |
|---|---|---|
| `ema` (no flags) | last 3 days: close + all six EMAs | `ema_check.log` |
| `--bars N` | last N days | `ema_check.log` |
| `--dates 2026-10-07 2026-10-09` | those days only (YYYY‑MM‑DD, any number) | `ema_check.log` |
| `--crosses N` | the latest N crosses of the 12 checks + total count | `ema_check.log` |
| `--state` | stage, all six EMAs, all 12 checks: side, days held, since, margin, whole‑candle‑clear | `ema_check.log` |
| `ema_snapshot` | the daily package as text (header, stage, EMAs, crosses today, holding, bigger trend) | `ema_snapshot.log` |
| `--directions above` | stocks mode: bearish crosses not shown as texts/alerts | |
| `--json` | also the full package (what the frontend will use) | |

### 4.3 MACD (six timeframes)

```
python -m …trend_indicators.macd.macd [--key KEY] [--timeframe 1d|1w|1mo|60m|15m|5m|all] [--domain DOMAIN]
                                      [--bars N] [--dates D ...] [--ohlc] [--state | --crosses N | --turns N | --events N]
python -m …trend_indicators.macd.macd_snapshot [--key KEY] [--name NAME] [--timeframes TF ...] [--directions both|above] [--json]
```
| Command / flag | Prints | Log (`logs\macd_test_logs\`) |
|---|---|---|
| `macd` | 1D, last 3 candles: close, histogram, MACD, signal, colour, PPO % (TradingView legend order) | `macd_check_1d.log` |
| `--timeframe 60m` | same for that timeframe (domain picked automatically) | `macd_check_60m.log` |
| `--timeframe all` | all six timeframes in one run (+ summary table with `--state`) | `macd_check_all.log` / `macd_check_all_<mode>.log` |
| `--bars N` / `--dates …` | last N candles / those dates. Intraday: every candle of the date. Weekly: give the week's **Monday** (`2026-10-05`); monthly: the **1st** (`2026-09-01`). A date with no candle prints "no bar on this date" | per timeframe |
| `--ohlc` | adds open/high/low — use it to prove you hovered the same candle as Fortuna | per timeframe |
| `--state` | label, histogram state and how long, MACD vs 0 and vs signal: held / since, last crosses | `macd_check_<tf>_state.log` |
| `--crosses N` | latest N **crosses**: zero‑line and signal‑line (with zone) | `macd_check_<tf>_crosses.log` |
| `--turns N` | latest N **momentum turns** — every histogram colour change (useful on 5m/15m/60m) | `macd_check_<tf>_turns.log` |
| `--events N` | crosses + turns together (the pre‑12 Oct `--crosses` list) | `macd_check_<tf>_events.log` |
| `macd_snapshot` | package + texts for all six timeframes + summary line | `macd_snapshot.log` |
| `--timeframes 1d 60m` | only those timeframes | |

`--state`, `--crosses`, `--turns`, `--events` are one at a time. Why crosses and turns are separate: `MACD.md` §6.1.
In the snapshot a momentum turn on 1M/1W/1D is a plain text line (no ⚡, no alert); on 60m/15m/5m it has ⚡ and is an alert.

### 4.4 ADX / DMI (six timeframes)

```
python -m …trend_indicators.adx.adx [--key KEY] [--timeframe 1d|1w|1mo|60m|15m|5m|all] [--domain DOMAIN]
                                    [--bars N] [--dates D ...] [--ohlc] [--state] [--crosses N]
python -m …trend_indicators.adx.adx_snapshot [--key KEY] [--name NAME] [--timeframes TF ...] [--directions both|above] [--json]
```
Same flags and meaning as MACD. Prints the five TradingView lines in legend order **+DI, −DI, DX, ADX,
ADXR**; `--state` adds band, ADX slope and how long, who is in control and since when; `--crosses N` lists DI
crosses (each tagged with the ADX at the cross and its band) and ADX crossing 25. Logs in
`logs\adx_test_logs\`: `adx_check_<timeframe>.log`, `adx_check_all.log`, `adx_snapshot.log`.

### 4.5 RSI (six timeframes)

```
python -m …oscillators.rsi.rsi [--key KEY] [--timeframe 1d|1w|1mo|60m|15m|5m|all] [--domain DOMAIN]
                               [--bars N] [--dates D ...] [--ohlc] [--state | --crosses N]
python -m …oscillators.rsi.rsi_snapshot [--key KEY] [--name NAME] [--timeframes TF ...] [--json]
```
| Command / flag | Prints | Log (`logs\rsi_test_logs\`) |
|---|---|---|
| `rsi` / `--bars N` / `--dates …` | close, RSI (the TradingView value), RSI MA (hidden Smoothed MA, for checking only) | `rsi_check_<tf>.log` |
| `--state` | zone label, zone held / since, side of 50, rising / falling, last zone change, last 50 crosses (`--timeframe all` adds a summary table) | `rsi_check_<tf>_state.log` |
| `--crosses N` | latest N zone changes (Ash's wording, e.g. `RSI 33.66 STRONG BEAR (20–30) rising up into BEARISH (30–45)`) and 50 crosses | `rsi_check_<tf>_crosses.log` |
| `rsi_snapshot` | report‑dated texts + alerts for all six timeframes + summary line | `rsi_snapshot.log` |

`--state` and `--crosses` are one at a time. No directions option: both directions always, index and stocks.
Same `--dates` rules as MACD (weekly = Monday, monthly = the 1st, intraday = every candle of the date).

### 4.6 Unit tests (no R2 needed, safe any time)

```
python -m pytest modules/market_data/upstox/test_indicator_ohlcv_reader.py -v        # 19 tests (screen only)
python -m pytest modules/Module_F_Tech_Indicators_Funnel/trend_indicators/ema -v      # 63 → logs\ema_test_logs\test_ema.log
python -m pytest modules/Module_F_Tech_Indicators_Funnel/trend_indicators/macd -v     # 66 → logs\macd_test_logs\test_macd.log
python -m pytest modules/Module_F_Tech_Indicators_Funnel/trend_indicators/adx -v      # 61 → logs\adx_test_logs\test_adx.log
python -m pytest modules/Module_F_Tech_Indicators_Funnel/trend_indicators -v          # all three; each log still gets only its own tests
python -m pytest modules/Module_F_Tech_Indicators_Funnel/indicator_common -v          # 57 → logs\indicator_common_test_logs\test_indicator_common.log
python -m pytest modules/Module_F_Tech_Indicators_Funnel/oscillators/rsi -v           # 86 → logs\rsi_test_logs\test_rsi.log
python -m pytest modules/Module_F_Tech_Indicators_Funnel -v                           # everything: 333 (63 + 66 + 61 + 57 + 86)
```
**Expected: every test PASSED, last line `summary: N passed`, `exit status: 0`.** Run the tests after any
code change, before committing. What each test proves: `EMA.md` §13.1, `MACD.md` §14.1, `ADX.md` §9, `RSI.md` §9;
`indicator_common`: 33 checks that each old name is the shared object (nothing can drift) + hand‑worked EMA / RMA,
a plain‑loop RMA reference, the cross rule, runs, timeframe map, text formatting, `report_date`.

**After touching anything in `indicator_common/`:** run the full test command above **and** the §6.1 health
check (`ema`, `macd`, `adx`, `rsi --dates 2026-10-09`) — every indicator depends on it.

---

## 5. Running on a stock

- **Instrument key:** `NSE_EQ|<ISIN>`, e.g. Reliance `NSE_EQ|INE002A01018` (keys are in Supabase
  `f_universe_instruments`).
- **EMA:** `ema --key "NSE_EQ|INE002A01018" --domain universe` (and the same for `ema_snapshot`, plus
  `--name "Reliance" --directions above`).
- **MACD / ADX manual checks:** add `--domain universe` for 1d/1w/1mo, one timeframe per run (`--domain` applies
  to every timeframe, so don't combine it with `--timeframe all`). 5m/15m/60m exist only for **F&O stocks**
  (domain `universe_intraday`, the automatic default — leave `--domain` out).
- **MACD / ADX snapshots: Nifty only for now.** They always read daily/weekly/monthly from `indices`, so a stock
  key fails those timeframes with "no OHLCV file" (intraday works for F&O stocks). Fixing this (a domain
  option) is an open item, to be done with the watchlist work.
- **Caution:** Upstox stock candles are **not adjusted** for splits/demergers (e.g. Tata Motors 2025‑10‑14,
  Siemens 2025‑04‑07). Indicators on such stocks will be wrong around those dates until an adjustment is built.
- Reference chart for stocks: **tv.upstox.com / pro.upstox.com**.

---

## 6. Checking Fortuna against TradingView (the parity procedure)

Use this whenever code changes, a new instrument is added, or a number looks wrong.

1. **Open the reference chart:** tv.dhan.co for Nifty (tv.upstox / pro.upstox for stocks). Add the indicator
   with the exact settings: EMA lengths 5/13/26/50/100/200 · MACD 12 26 close 9 EMA/EMA · DMI 14 14 (the DMI
   shows five lines: +DI, −DI, DX, ADX, ADXR) · RSI 14 close, Smoothing Line SMA 14 (turn the Smoothed MA on
   in Style only when checking `RSI MA`; legend `RSI 14 SMA 14  <RSI>  <MA>`).
2. **Load plenty of history first** — zoom out / scroll back a few years, then return. TradingView calculates
   only over the history it has loaded; with a short history long EMAs and smoothed lines are slightly off
   (`EMA.md` §3.5). If a number is off by a little, re‑read the same candle after loading more history.
3. **Pick completed candles** — never the live/forming one (the live price changes it, and it differs between
   brokers). For weekly/monthly the latest candle is "to date" and moves until the period ends.
4. **Run Fortuna for the same candle**, with `--ohlc` for intraday:
   `macd --timeframe 60m --dates 2026-10-09 --ohlc`. **First compare O/H/L/C** with the chart's — if they
   differ you are on a different candle.
5. **Compare the values in the legend** with Fortuna's (2 decimals; ADX shows 4). For an RSI zone change, hover
   the candle **and the one before** (the change needs the previous candle on the other side of the boundary).
6. **Labels on weekly candles:** Fortuna/Upstox name a week by its **Monday**; TradingView by the week's **first
   trading day** (week of 14 Sep 2026 = "Tue 15 Sep" on the chart because Monday was a holiday). Same candle.

### 6.1 Reference values (Nifty 50, data to 9 Oct 2026, all confirmed on tv.dhan)

| Indicator · candle | Fortuna = TradingView |
|---|---|
| EMA 1D 9 Oct 2026 | 5: 22,520.37 · 13: 22,754.83 · 26: 23,085.74 · 50: 23,431.07 · 100: 23,747.77 · 200: 24,077.44 |
| MACD 1D 9 Oct 2026 (hist / MACD / signal) | −28.78 / −360.57 / −331.79, light red |
| MACD 1D 9 Oct 2020 | 72.57 / 110.38 / 37.80, dark green |
| MACD 1W week of 5 Oct 2026 | −153.48 / −371.32 / −217.85 |
| MACD 1M Sep 2026 | −388.13 / 312.93 / 701.06 |
| MACD 60m 9 Oct 15:15 | 22.85 / −25.52 / −48.37 |
| MACD 15m 9 Oct 15:15 | −0.08 / 35.25 / 35.33 |
| MACD 5m 9 Oct 15:25 | −5.88 / 5.94 / 11.82 |
| ADX 1D 9 Oct 2026 (+DI / −DI / DX / ADX / ADXR) | 9.9922 / 38.3904 / 58.6951 / 43.8447 / 37.4798 |
| RSI 1D 9 Oct 2026 (RSI / MA) | 36.50 / 31.48 — BEARISH (30–45) |
| RSI 1M Sep 2026 · 1W week of 28 Sep 2026 | 44.82 / 56.29 · 31.06 / 46.27 |
| RSI 60m · 15m 9 Oct 15:15 · 5m 9 Oct 15:15 | 51.18 / 41.86 · 56.85 / 62.14 · 50.83 / 57.99 |

These never change for completed candles (unless history is re‑fetched), so they are the fastest health
check after any change: run `ema --dates 2026-10-09`, `macd --dates 2026-10-09`, `adx --dates 2026-10-09`,
`rsi --dates 2026-10-09`. Refreshing data adds newer candles but does not change these (an indicator on a candle
uses only that candle and earlier ones); after a refresh re‑run them once to confirm.
More values and cross dates: `EMA.md` §10, `MACD.md` §10.3–10.4, `ADX.md` §10.1–10.2, `RSI.md` §3.2 / §10.2.

### 6.2 Known differences — these are NOT Fortuna errors

| Seen | Why | What to do |
|---|---|---|
| Long EMAs / smoothed lines slightly off on a fresh page | TradingView's loaded history is short | load more history, re‑read (§6 step 2) |
| Latest month/week, or today's candle, differs | live price in the forming candle | compare completed candles only |
| tv.dhan vs tv.upstox differ slightly on long EMAs | each broker loads different history and its own feed | expected; use tv.dhan for Nifty |
| Nifty volume: Dhan shows it, Upstox stored data has 0 | Upstox sends no index volume | volume not used for indices |
| ADX 1h off by 0.002–0.01 vs tv.dhan | small Sept 2026 1h feed difference Upstox vs Dhan, fading out | recorded, not hunted (`ADX.md` §10.3) |
| RSI MA 60m 0.01 off (41.86 vs 41.85), RSI exact | rounding at the 2nd decimal | recorded; MA is hidden (`RSI.md` §10.3) |
| Old (2020) EMA 100/200 a few paise off | old‑data differences that vanish by 2022 | none |

---

## 7. Diagnostic commands (when something looks wrong)

**Is the last candle what I expect?** → reader (§4.1) — prints `last bar … (data as of this candle)`.

**Are intraday candles missing or extra?** (the "bar‑count probe" used for the 1h ADX check) — counts
candles per day since a date and lists any day that doesn't have the normal count (60m = 7, 15m = 25, 5m = 75):
```
python -c "from dotenv import load_dotenv; load_dotenv(); from modules.market_data.upstox.indicator_ohlcv_reader import read_for_indicators as r; d=r('NSE_INDEX|Nifty 50','universe_intraday','60m').df; d=d[d.ts.dt.strftime('%Y-%m-%d')>='2026-07-01']; c=d.groupby(d.ts.dt.date).size(); print(c.value_counts().to_string()); print(c[c!=7].to_string())"
```
Expected: one line `7  <number of days>` and nothing listed below it (short special sessions like Muhurat
will show up — those are fine, reader rule 3).

**After‑close bars (reader rule 2)** — the reader's INFO line `Reader rule 2: dropped 94 bar(s) … on 89 day(s)`
on 15m/5m shows it is working; Muhurat evening‑only days are kept on purpose.

**Full data audit (read‑only):** `python -m modules.market_data.upstox.audit_ohlcv_data` — ledger vs R2,
gaps, staleness, rollups (`fortuna_data_pipeline_flow.md` §2.9).

---

## 8. Troubleshooting

| Message / symptom | Cause | Fix |
|---|---|---|
| `unrecognized arguments: --ohlc` (or any flag) | your copy of the file is older than this doc | pull / copy the latest file |
| `ModuleNotFoundError: No module named 'modules'` | not run from `backend/` | `cd …\_Repository\backend` |
| `NOT OK -- no OHLCV file in R2` | wrong key or domain, or the instrument was never fetched | check key; daily = `indices`/`universe`, intraday = `universe_intraday` (the error adds a hint) |
| R2 / config error on the first line | `.env` missing or wrong | check `backend\.env` |
| `getaddrinfo failed` during refresh | Supabase free tier paused | restore the project in the Supabase dashboard, rerun |
| "as of" date is older than expected | refresh not run, or run before 4 pm | §2 step 3 |
| Label `n/a (not enough history)` | fewer candles than the indicator needs (EMA 200 → 200; MACD signal → 34; ADX → 28, ADXR → 41; RSI → 15, RSI MA → 28) | normal for new listings |
| A test FAILED | code changed something | open the test log; the failure text says which value differed |
| Numbers differ from the chart | almost always §6.2 | follow §6 steps 2–4 before suspecting code |

---

## 9. Log files map (all under `backend\logs\`)

| Folder | Files |
|---|---|
| `ema_test_logs\` | `ema_check.log` (any `ema` run) · `ema_snapshot.log` · `test_ema.log` |
| `macd_test_logs\` | `macd_check_<tf>.log` (bars/dates) · `macd_check_<tf>_<state/crosses/turns/events>.log` · `macd_snapshot.log` · `test_macd.log` (`<tf>` = 1d/1w/1mo/60m/15m/5m/all) |
| `adx_test_logs\` | `adx_check_<1d/1w/1mo/60m/15m/5m/all>.log` · `adx_snapshot.log` · `test_adx.log` |
| `rsi_test_logs\` | `rsi_check_<tf>.log` · `rsi_check_<tf>_<state/crosses>.log` · `rsi_snapshot.log` · `test_rsi.log` |
| `indicator_common_test_logs\` | `test_indicator_common.log` |

All overwritten on each run. The data‑pipeline logs (refresh, backfill) are in `backend\logs\` directly.

---

## 10. Adding the next indicator (the pattern every indicator follows)

1. **Research → discuss → plan → approve → code**, one step at a time. Confirm the exact TradingView settings
   from the chart's settings dialog first.
2. **Spec doc** `<NAME>.md` here, same layout: §0 plain English, scope, input, TradingView parity (formula in
   Pine terms), bands/labels, states/events, texts, code map, open items, tests, verification record, change log.
3. **Folder** `trend_indicators/<name>/` or `oscillators/<name>/` (RSI, Stochastic RSI and later CCI, Williams %R
   go in `oscillators/`) with `__init__.py`, `<name>.py`,
   `<name>_snapshot.py`, `test_<name>.py`, `test_<name>_snapshot.py`, `conftest.py`.
4. **`<name>.py`:** pure functions (no I/O) — `compute_<name>(df)` returns a copy with new columns and raises
   `ValueError` on bad input; states/labels as separate functions; a `__main__` manual check with the standard
   flags (`--timeframe … all --domain --bars --dates --ohlc --state --crosses`) logging to screen **and**
   `logs/<name>_test_logs/<name>_check_<tf>.log` (first line = the command).
5. **Reuse, don't copy — import from `indicator_common/` only** (§1): `smoothing` (`ema_tradingview`,
   `rma_tradingview`), `crosses` (`cross_above`, `cross_below`, `runs`, `bar_labels`), `timeframes`
   (`TIMEFRAMES`, `TF_NAME`, `DEFAULT_DOMAIN`, words), `text_format`. Never import from another indicator's folder.
   A helper a second indicator needs goes into `indicator_common/` (moved unchanged, with a test), not copied.
6. **`<name>_snapshot.py`:** `snapshot_from_bars` (pure) + `build_<name>_snapshot` that **never raises**
   (result with ok / errors / summary) + `__main__` logging to `<name>_snapshot.log`.
7. **Tests:** an independent plain‑loop reference of TradingView's formula, hand‑worked small cases, the chart's
   own numbers, edges (short history, flat prices, input not modified, validation). `conftest.py` copies
   EMA's, changing only the folder filter and the log name (the file must be called `conftest.py`).
8. **Parity:** compare several completed candles on every timeframe against tv.dhan (§6), plus cross dates.
   Record every mismatch and its explanation in the spec.
9. **Docs at checkpoints:** spec, `Fortuna-Build-Log.md`, `fortuna_data_pipeline_flow.md` §2.x / §5 / §6, this
   runbook (§1, §4, §6.1, §9).

---

## 11. Where else to look

| Need | Doc |
|---|---|
| What an indicator means and how to read it | spec §0 (`EMA.md`, `MACD.md`, `ADX.md`, `RSI.md`) |
| Exact formulas, labels, texts, thresholds | the spec |
| How parity was proven, every mismatch explained | spec §3.5 / §10 / §13–14 |
| Reader rules (bad prices, after‑close bars, special sessions) | `MACD.md` §2, `fortuna_data_pipeline_flow.md` §2.12 |
| Data pipeline: refresh, backfill, R2 layout | `fortuna_data_pipeline_flow.md` |
| What was built when, and open items | `Fortuna-Build-Log.md` |

---

## 12. Change log
- **v1.3 — 2026‑10‑13.** RSI (`oscillators/rsi/`): §1 table, §2 prefix `…oscillators`, §3 daily routine, new §4.5
  RSI commands (tests now §4.6: RSI 86, indicator_common 57, total 333), §6 RSI settings + zone‑change hover rule,
  §6.1 RSI reference values + refresh note, §6.2 RSI MA rounding, §8 RSI history, §9 RSI logs.
- **v1.2 — 2026‑10‑12.** Shared helpers `indicator_common/` (§1 table, §4.5 tests 52 / total 242 and "after touching
  indicator_common" rule, §9 log folder, §10 steps 3 and 5: `oscillators/` folder, import only from
  `indicator_common`).
- **v1.1 — 2026‑10‑12.** MACD `--crosses` / `--turns` / `--events` and per‑mode log files.
- **v1 — 2026‑10‑12.** First version: setup, daily routine, every command and flag, stock usage, parity
  procedure with reference values, known differences, diagnostics (incl. the bar‑count probe), troubleshooting,
  log map, new‑indicator pattern.
