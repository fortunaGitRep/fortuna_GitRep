# TRENDLINES — Fortuna Indicator Spec

**Status:** v1 (2026-10-26), split out of `SUPPORT_RESISTANCE.md` (§6 there, v1.2 → v1.3) so trendlines have their own document (Ash, 2026-10-26: "separate … don't merge"). Two manual checks, no module yet: the old **chain check** (`trendline_check.py`, §3–§10: right on Ash's 19 Oct chart, but only 1 of 10 days) and the new **drawing Ash's way on every timeframe** (`trendline_draw.py` + `trendline_confluence.py`, §11). Exits on hold for options-contract data. Open questions in §9 and §11.
**Folder:** `backend/modules/Module_F_Tech_Indicators_Funnel/price_action/trendlines/`
**Timeframes:** old chain check 5m; new drawing 1M / 1W / 1D / 1h / 15m / 5m
**Scope:** Nifty 50 first
**Related:** horizontal S&R (lines, trading ladder, zones) — `SUPPORT_RESISTANCE.md` §4; S&R types and build order — `SUPPORT_RESISTANCE.md` §1–§3.
**Parity reference:** Ash's own drawings on tv.dhan.co.

---

**The chain check (2026-10-23):** `price_action/trendlines/trendline_check.py` draws Ash's trendlines candle by candle on 5m Nifty, marks her entries, and draws the lines on a chart. Checked against her own drawing of Mon 19 Oct 2026: **lines, entries and the line 4 ("vertical") are correct (Ash, 2026-10-23).** Exits are a **draft** and are on hold until options-contract data is in (§6). The every-day check was then right on only 1 of 10 days (§9) → drawing redone Ash's way (§11).

## 1. Research: books
- **Murphy** (*Technical Analysis of the Financial Markets*, ch. 4): two points draw a tentative trendline, a third touch confirms it. The longer a line holds and the more touches, the more significant it is. Steep lines break sooner. **Fan principle:** after a break, a second and third line are drawn; the break of the third line is the signal. **Role reversal:** a broken trendline tends to act from the other side. A break is a warning, not a trade by itself. **Penetration filters** against false breaks: a price filter (a close beyond the line by a minimum amount) and a time filter (two closes beyond).
- **Bulkowski** (thepatternsite.com, trendline pages — link to be re-added): buying at the 3rd touch "didn't work well" (37% win rate, +0.7% average); lines with 4+ touches, long and shallow lines did better; avoid the "top trap" (entering just under overhead resistance) and the "2B" setup. Breakouts with tall candles work better (`TallCandleSAR`).
- Trend acceleration usually shows in about 3 steps of steeper lines (fan / acceleration).

## 2. Research: studies
No study of intraday trendline bounces was found. Everything below is Ash's method, coded and checked on her chart; the history test comes later (§9).

## 3. Ash's method (her observations, 2026-10-19 → 23)
- Intraday Nifty 5m, options buying, trades in the 9:30–11:30 window. Falling side shown; the rising side is the exact mirror (lows, green bounces, call entries).
- Price scale **linear** (not % or log). Lines go through **wicks**. No angles, no Zig Zag (the Zig Zag misses her anchor candles and confirms late).
- **Line 1** starts at the top (highest high of the look-back). Entries are **red bounce candles** at a line. **Lines 2 and 3** get steeper. The **4th line ("vertical")** starts at the entry candle.
- Max 3 entries per window. Broken lines stay extended as S&R; when price has gone through all of them, the trend change is confirmed.
- On 19 Oct she drew: line 1 09:15 → 09:45, line 2 09:35 → 10:30, line 3 10:30 → 11:20, entries 09:50 / 10:30 / 11:20, vertical 11:20 → 11:30, its real break at **13:30** (12:55–13:25 was not the break).
- Similar highs next to each other (within the 5m equal tolerance): the line goes through the rightmost **red** one. 10:20's high, 23 pts short of the line, is **not** a touch. Line 1 is context; the trade is mostly on the later lines.
- **Which entries to trade (2026-10-23):** the first two verticals of the day can be fakes on the options chart (a deep fall below VWAP and back). When volume, liquidity, Greeks, IV and OI all support the trend, all 3 entries can work; when they don't, **only the line-3 entry and its vertical** are traded. On 19 Oct that is the **11:20 entry, exit 13:00 or 13:30**. This is decided on the option contract's chart, not the index.

## 4. Rules as built (`trendline_check.py`)
- **Point:** a candle whose next candle makes a lower high (falling) / higher low (rising); the last candle is a live point. **Turn** (allowed as a line's 1st point): a high ≥ the candle before and > the candle after.
- **Top:** highest high in the look-back window — 5m last 3 trading days, 15m / 60m last 25.
- **Touch tolerance:** median |close − previous close| of the last 20 candles (median, so opening spikes do not widen it).
- **Similar highs merge:** consecutive points within the equal tolerance (5m 0.05%, `zigzag_settings`) of the run's first point are one point, at the run's newest **red** candle (rising: green). Newest not red → the run waits, labelled "possible reversal / sideways / trap". Never across days.
- **Drawable line:** no close beyond it between its two points; between them a close must move away by more than the tolerance; the 2nd point at least 2 candles after the 1st; a similar-highs run at the 2nd point does not count as "between". **Break** = the first close beyond the line after its 2nd point.
- **Chain** (built candle by candle): line 1 = top → the first bounce candle with a drawable line (redrawn if broken before the next entry). **Entry** = a bounce candle touching the newest unbroken chain line, labelled "entry n of 3" / "over the 3 limit". Lines 2 / 3 = at an entry, the steepest drawable line ending there, starting at a turn after line 1's start, steeper than the line bounced off; its 2nd point must have "come back" (high above the lowest high between). **Vertical candidate** at every entry ("early, on line 1" when on line 1): entry → the next point ≥ 2 candles later that gives a drawable line. A new highest high starts a new chain.
- **Each entry shows** body % of range, range × the 20-candle average, and the nearest S1 (falling) / R1 (rising) on the **trading ladder** (all timeframes, only candles finished by the entry's close), with its timeframes.
- **After the break** (lines 1–3 and verticals): **retest** (wick back within the tolerance, close stays on the broken side), **failed break** (close back on the original side), **broke again**. Verticals are drawn through failed breaks up to the break that still stands (19 Oct: 12:55 break → 13:20 failed → **13:30** break). **Trend change confirmed** at the first candle where every chain line, line 1 included, stands broken (kept even if one later fails back — revisit after reviewing several days).
- **Chart** (`trendline_chart_<date>.html`, TradingView Lightweight Charts 4.1.3): candles, lines 1 / 2 / 3 (green / cyan / purple, extended to the last candle), verticals (pink; dashed when early), labels "line 1 T1" / "L1 T2" / "L1-Entry" / "vertical T1" / "V T2", break / retest / failed squares, "V BREAK" arrow, draft EXIT arrows, the Zig Zag (blue), the trading ladder's horizontal lines in the chart's price range (orange = on 5m, grey dashed = higher timeframes only; labelled with their timeframes), opens on the day; labels within 3 candles move to the other side of the bar.

## 5. Horizontal S&R used by trendlines
- The entry label and the chart use the full trading ladder (`horizontal_sr.trading_ladder`), not only 5m lines (2026-10-23). Higher-timeframe candles are used only when finished: intraday by start + length, 1D / 1W / 1M when their day / ISO week / month is before the cut-off. 1D / 1W / 1M read from `indices` (`--daily-domain`). Speed (2026-10-23): for the ladder, the Zig Zag reads only the last 30 trading days of 5m and 120 of 15m / 60m (lines use 3 / 25 / 25 days) — same ladder as full history on 14 checked cut-offs; ladders are cached per cut-off. A 10-day `--side both` run takes about 20 s (was 15+ min).
- Colour by timeframe (orange 5m, grey higher only) **kept for now** (Ash: "we will change later"); options noted: all lines orange + R1 / S1 thicker.

## 6. Exits — DRAFT, on hold (Ash, 2026-10-23)
- **Proven break** of an entry's vertical (all three): (1) a close beyond the line by more than the tolerance; (2) the candle is in the break direction (green when a falling line breaks); (3) not rejected at a horizontal line (no trading-ladder line between the close and the wick). Murphy's price and time filters alone each gave a wrong break on 19 Oct; candle type + horizontal S&R separated them (13:00's wick rejected at R4 22,950.00).
- Draft result on 19 Oct (index points, entry close → exit close): 09:45 → 10:15 +54.90 · 10:30 → 10:55 +12.65 (10:50 rejected at 23,056.40) · **11:20 → 13:30 +186.90** (13:00 rejected at 22,950.00) · 11:30 (over 3) → 12:30 +70.20. Same with all timeframes.
- **On hold:** entries and exits are finalised on the **option contract's chart** with volume, liquidity, Greeks, IV, OI and VWAP — needs expired-contract data first (§9).

## 7. Code map — `price_action/trendlines/`
| File | Main functions |
|---|---|
| `trendline_check.py` (manual check, read-only) | helpers `known_at`, `tolerance`, `window_start`, `points`, `turn_points`, `merge_similar`, `top_index`, `build_line`, `lines_for`, `_line_at`, `_came_back`, `candle_facts`; horizontal S&R `completed_by`, `ladder_at`, `nearest_level`; `build_chain`, `report_chain`; `after_break`, `standing_break`, `report_after_break`; draft exits `proven_break`, `report_exits`; chart `chart_data`, `_spread_markers`, `chart_html`; `report_side`, `candle_table`, `run`, `day_summary`, `main` |

Imports `horizontal_sr` (`timeframe_lines`, `trading_ladder`), `swing_points` (Zig Zag + `zigzag_settings`), the indicator reader. No tests yet (manual check; tests come with the module).

## 8. How to run (from `backend/`)
```
python -m modules.Module_F_Tech_Indicators_Funnel.price_action.trendlines.trendline_check [--date YYYY-MM-DD] [--at HH:MM ...] [--side down|up|both] [--candles FROM TO] [--show N]
python -m modules.Module_F_Tech_Indicators_Funnel.price_action.trendlines.trendline_check --date 2026-10-22 --last 10 --side both
python -m modules.Module_F_Tech_Indicators_Funnel.price_action.trendlines.trendline_check --dates 2026-10-15 2026-10-19 --side both
```
Defaults: `--date 2026-10-19 --at 09:50 10:35 11:25 11:40 15:30 --side down`. One run: candle table, then per `--at` time the chain, entries, after the break, exit candidates, live / unbroken / broken lines; chart for the last `--at`. Multi-day (`--last N` / `--dates`): per day a summary (lines, that day's entries with draft exits, trend change) as of 15:30, the chain detail, a chart per day. Log: `logs\trendline_test_logs\trendline_check.log` (overwritten, first line = the command); charts `trendline_chart_<date>.html` beside it (open in a browser; needs internet for the chart library).

## 9. Open items (trendlines)
1. **Every-day check — done after the 23 Oct docs:** `--last 10 --side both` was correct on **1 of 10 days** (19 Oct). Why: line 1 anchors on the 3-day highest high (8 and 21 Oct got no entries); lines 2 / 3 rarely form (12 Oct: 19 entries on line 1); the 3-entry limit counts across days. → Drawing replaced by Ash's 17-step method (§11); `trendline_check.py` kept as it is. Entries / exits come back on top of the new lines later.
2. **3-entry limit per day?** The chain spans the 3-day window, so entries on earlier days count toward the limit (16 / 19 Oct test: all later entries "over 3"). Reset per day / per 9:30–11:30 window — Ash to decide.
3. **Exits** (§6): options-contract data (expired contracts), Greeks, IV, OI, volume, VWAP → finalise entries and exits on the contract chart; how long to stay in the trend; ranging mid-trend vs end of trend; the 13:20 time exit.
4. **What makes a break real** — horizontal S&R + candle type, tested on history (backtest).
5. **Trend change** withdrawn if a line fails back later? Kept for now.
6. Horizontal lines from ranging prices (not swings), e.g. 22,860 on 19 Oct (same as `SUPPORT_RESISTANCE.md` §4.8).
7. Line colours on the chart: all orange + R1 / S1 thicker (later).
8. Candle-by-candle engine → backtest v1 (entries vs a random control, `studies/trendline_sr/`) → v2 with exits → module (`trendlines.py`, snapshot, tests) → frontend.
9. Re-add the Bulkowski trendline source link (§1).

## 10. Verification record (tv.dhan.co, Nifty 50 5m, Mon 19 Oct 2026)
| What | Result |
|---|---|
| Line 1 09:15 23,175.25 → 09:45 23,155.95 · line 2 09:35 23,168.45 → 10:30 23,124.50 · line 3 10:30 → 11:20 23,079.75 | = Ash's lines ✓ |
| Entries 09:45 / 10:30 / 11:20 (+ 11:30, 14:45 over the limit) | = Ash's 09:50 / 10:30 / 11:20 ✓ (09:45 candle closes at 09:50) |
| Vertical 11:20 23,079.75 → 11:30 23,062.75 | = Ash's 4th line ✓; break 12:55 → failed 13:20 → **13:30** standing = Ash's 13:30 ✓ |
| Line 3 after break | 14:55 break → 15:00 failed → 15:15 broke again → 15:20 retest = Ash's read ✓ |
| Nearest S1 at entries (trading ladder) | 23,116.10 [60m 15m] · 23,070.15 [1w 1d 5m] · 23,059.45 [15m 5m] · 23,020.95 [15m 5m] |
| Horizontal 23,076.55 (Ash: "closest to what I would draw") | R9 [1w 1d 5m] ✓ |

## 11. Drawing Ash's way on every timeframe (`trendline_draw.py`, 2026-10-25 → 26)
New file, separate from `trendline_check.py` (the old chain check is kept as it is; Ash: "great job at writing new one and keeping old one separate"). Read-only manual check. Step A of the simplified plan: **lines only**; entries and exits come back on top later.

**Ash's 17-step method (screenshots on tv.dhan, 23 Oct chart; 2026-10-25):** top-down 1M → 1W → 1D → 1h → 15m → 5m; horizontal S&R at the highest high and lowest low; trendlines from the extreme; a line whose points have a wick cutting between them is not valid; after a break, redraw from the same start; the next line starts where the previous one ends; on 5m the past 2 days decide the trend. **Her answers (2026-10-25):** a **wick break is a break** (no close needed, no tolerance: "prices need to stay above the trendline"); the 5m trade direction comes from the higher timeframe ("daily is going up but hourly is now on a downtrend → buy put"); keep it simple — focus on drawing trendlines her way; entry rules later.

**Rules as built:**
- **Lines = the outline of the wicks** from the look-back's extreme: upper outline of the highs from the highest high (falling lines), lower outline of the lows from the lowest low (rising lines), rebuilt candle by candle. A line that disappears was crossed by a wick = **break**; a new extreme breaks every line and moves the start. A line whose 2nd point is the last candle is "live" (not confirmed). Reproduces Ash's 1h line exactly; Ash: monthly correct, weekly good, 1h makes sense (2026-10-25/26).
- **Look-back:** 1M / 1W 20 years (her monthly chart starts 2006), 1D 1 year (250 trading days; Ash 2026-10-25, was 10 days), 1h / 15m 10 trading days, 5m 7 trading days on the `trendline_draw` charts (Ash 2026-10-26: "what you are doing for 3 days i want to see drawing and hsr … for 7 days"; `DRAW_LOOKBACK`, was 3) and 3 trading days in `trendline_confluence.py` (unchanged).
- **Candles at the cut-off (no future data):** intraday candles closed by then; 1D earlier days (today after 15:30); 1W / 1M finished periods + the running week / month built from the daily candles.
- **Trend per timeframe:** highest high more recent than the lowest low = DOWN, else UP (**confirmed by Ash 2026-10-26**: "my drawings are matching"). 5m trades follow 1h (`TRADE_TF = 60m`): DOWN → buy puts, UP → buy calls.
- **Drawing (2026-10-26):** the last confirmed line on each side solid, earlier lines dotted; broken lines dotted and **stop at the candle whose wick crossed them** (they were drawn on to the last candle and candles cut through them); lines whose 2nd point is the last candle **hidden until confirmed** (`--show-live` shows them); monthly lines width 3 (one thinner); falling red, rising green, thicker = higher timeframe.
- **Horizontal S&R per chart (Ash: "previous highs are my target exit price"):** 1M: Zig Zag (blue) + a line from each Zig Zag point to the right; 1W and 1h: Zig Zag + lines that stop where price first crosses them (only uncrossed ones reach the right edge with a label); 1D: Zig Zag + the ladder of 1D and higher; 15m: the ladder of 15m and higher; 5m: the full trading ladder. The log lists per timeframe the 3 nearest targets above and below ("targets (horizontal S&R, this + higher timeframes)").
- **Data check:** the log starts with the last stored candle per timeframe and flags intraday data that stops before the as-of day.

**Charts (`logs\trendline_test_logs\`):**
- `trendline_draw_<1M|1W|1D|1h|15m|5m>_<date>.html` — one per timeframe (5m: 7 days — lines from the 7-day extreme, horizontal S&R across the 7 days).
- `trendline_draw_all_<date>.html` — the 5m chart with every timeframe: opens on the last day; per higher timeframe only the nearest falling line above and rising line below the close (higher-timeframe lines far off the 5m prices left out), drawn from their own 1st point; names and values on the price axis; 3 nearest horizontal lines each side; the trend of every timeframe and the trade direction in the header. Ash: readable, "still lacks something".
- `trendline_draw_5m_zones_<date>.html` — the 5m trendlines with **zones**, last **7 days** (`SHOW_DAYS_5M` = the 5m look-back, 7; same lines as the 5m chart); each day's zones from candles finished before 09:15 that day (earlier days show whether they held); orange lines left out. **Temporary zone rule** (from `trendline_confluence.py`): trading-ladder lines within 0.1% of each other, from 2+ timeframes, strength = 1M 6 + 1W 5 + 1D 4 + 1h 3 + 15m 2 + 5m 1; trendlines are not in these zones. To be replaced by `hsr_zones.py` (`SUPPORT_RESISTANCE.md` §4.13) once zones are approved.

**All timeframes on one chart (`trendline_confluence.py`, new 2026-10-26):** at the last candle every timeframe's confirmed trendlines and horizontal S&R become prices; prices within 0.1% from 2+ timeframes = a zone (strength as above), shaded red above the price / green below; last 2 days of 5m; the 5m lines plus each higher timeframe's nearest line above / below; trend header. Log: the 5 nearest zones each side with what built them. Example 21 Oct: 23,056–23,077 strength 21, the only zone of all six timeframes. Ash: "looks good … but it's still the same chart, leave it, it's good not bad."

**Data findings (2026-10-26):** the intraday refresh for a day runs the **next day** (daily after 16:00); the 26 Oct refresh wrote 22–23 Oct (the first run of the day read the data 40 s before the refresh finished). On 21 and 23 Oct the 15:15 and 15:20 5m candles are flat and 15:25 jumps to the official close (23 Oct: 22,516.40 → 22,600.00 = the daily close) — it makes breaks at 15:25. No 5m candles for 20 Oct in the data.

**Code map (`price_action/trendlines/`):**
| File | Main functions |
|---|---|
| `trendline_draw.py` (new, read-only) | `candles_at`, `window`, `hsr_for`, `zigzag_of`, `_outline`, `draw_side`, `line_value`, `trend_of`, `report_tf`, `shown_lines`, `tf_chart`, `_pos_in`, `_line_series`, `chart_html` (lines, levels, rays, bands), `zone_bands`, `data_check`, `run`, `main`; settings `TFS`, `LOOKBACK`, `TRADE_TF`, `TF_WIDTH`, `ZIGZAG_CHART`, `SHOW_DAYS_5M`, `COMBINED_HSR_EACH_SIDE` |
| `trendline_confluence.py` (new, read-only) | `tf_lines`, `levels_now`, `zones`, `chart`, `run`, `main`; settings `ZONE_PCT = 0.10`, `MIN_TFS = 2`, `TRADE_DAYS = 2`, `WEIGHT` |
| `trendline_check.py` (old, unchanged) | §7; `trendline_draw.py` imports its helpers (`known_at`, `ladder_at`, `_swings`, `naive_ist`, `_epoch`, `LWC_URL`) |

**Run (from `backend/`):**
```
python -m modules.Module_F_Tech_Indicators_Funnel.price_action.trendlines.trendline_draw [--date YYYY-MM-DD] [--at HH:MM] [--show-live] [--key KEY] [--daily-domain indices|universe]
python -m modules.Module_F_Tech_Indicators_Funnel.price_action.trendlines.trendline_confluence [--date YYYY-MM-DD] [--at HH:MM]
```
Defaults `--date 2026-10-23 --at 15:30`. Logs `trendline_draw.log`, `trendline_confluence.log` (overwritten, first line = the command); charts beside them (open in a browser; internet needed for the chart library). The zones chart takes ~10 s more (zones per day). No tests yet (manual checks).

**Open questions (Ash to answer):**
1. **Weak zones:** hide zones below a strength (e.g. Z3 = one 15m + 5m line) on the zones chart?
2. **Closing jump at 15:25:** ignore it when deciding breaks, or keep it?
3. **Zones during the day:** fixed at 09:15 now; add new 5m / 15m swings confirmed during the day?
4. **Combined chart:** what is still missing?
5. **Small lines near the end** between close candles: noise? (minimum gap of 2 candles)
6. Do the earlier days' zones on the 5m zones chart match where price turned? (Ash: keep open)
7. Should trendlines stay out of the 5m zones (as now)?
8. Next steps after drawing: entries and exits on the new lines (step B / C), rerun the 10 days; 15m / 1h trading checks; tests and module.

---

## Sources
- Murphy, *Technical Analysis of the Financial Markets*, ch. 4 (trendlines, fan principle, role reversal, penetration filters)
- Bulkowski — trendline studies (thepatternsite.com; 3rd-touch results; link to be re-added, §9)
- [Bulkowski — Tall Candle S&R](https://thepatternsite.com/TallCandleSAR.html)

---

## Change log
- **v1 — 2026-10-26.** Split out of `SUPPORT_RESISTANCE.md` (its §6 → §1–§11 here, content unchanged): research, Ash's chain method, chain check rules, horizontal S&R used, draft exits, code map, how to run, open items (every-day check: 1 of 10 days), verification on 19 Oct, and §11 drawing Ash's way on every timeframe (`trendline_draw.py`, `trendline_confluence.py`). Same day, after the split: 5m look-back on the `trendline_draw` charts 3 → 7 trading days (§11; confluence stays 3). History before the split: `SUPPORT_RESISTANCE.md` v1.2 (2026-10-23, §6 created) and v1.3 (2026-10-26).
