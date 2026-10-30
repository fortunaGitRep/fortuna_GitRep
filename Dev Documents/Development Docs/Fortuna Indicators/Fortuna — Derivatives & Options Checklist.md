# Fortuna — Derivatives & Options Checklist

Oct 27, 2026 · @Ash

## Purpose and scope

This checklist lists everything Fortuna's derivatives and options work involves, in 17 sections. Part A (1–9) is the data plumbing; Part B (10–17) is trading, analysis and risk.

It is built around Ash's live method: Nifty 50 options buying on the 5m chart, 09:30 to 11:30, with entries taken only when the CE/PE contract chart is also trending. Option R1/R2/R3 mirror Nifty's levels.

## Upstox Plus

Plus is free to activate and unlocks expired F&O contracts through the API. The cost is brokerage: the flat fee rises from ₹20 to ₹30 per order, which hits Ash's Upstox swing orders.

| Item | Finding | Source |
| --- | --- | --- |
| Price | Free to activate (may become chargeable later, with advance notice); flat brokerage ₹20 → ₹30 per order from next trading day | [Plus T&C](https://upstox.com/files/terms-and-condition/plus-pack.pdf), [Help Center](https://upstox.com/help-center/does-the-brokerage-plan-change-with-upstox-plus-264072/) |
| Switching | 24-hour cooling-off after each switch | [Plus T&C](https://upstox.com/files/terms-and-condition/plus-pack.pdf) |
| Expired contracts | Need an active Plus plan | [Community](https://community.upstox.com/t/historical-instruments-of-options/9028) |
| Current contracts, option chain, Greeks | No Plus or extra permission needed | [Community](https://community.upstox.com/t/how-to-enable-api-access-for-fetching-fno-futures-options-data-option-chain-historical-live-data/14000) |
| Activation in API | New access token carries Plus automatically | [Community](https://community.upstox.com/t/expired-instruments-api-toggle-missing-in-developer-console-plus-plan-active/11428) |
| Depth per contract | OHLC from first trade to expiry | [Community](https://community.upstox.com/t/historical-availability-retrieval-limit-per-query-for-expired-options-contract/9245) |
| Depth of expiry list | Checked 27 Oct 2026: Nifty expiries back to 3 Oct 2024, about 2 years, rolling | [Community](https://community.upstox.com/t/historical-availability-retrieval-limit-per-query-for-expired-options-contract/9245) |
| Earliest expiry seen | Nifty 3 Oct 2024 (checked 27 Oct 2026) | [Community](https://community.upstox.com/t/getting-historical-f-o-data-before-first-expiry-2024-10-04/9491) |
| Historical Greeks / IV | Not provided; Fortuna computes them (built 29 Oct 2026, matches Upstox live) | — |

The expiry list is a rolling window, so expired data is perishable. Fortuna keeps every expiry permanently in R2 and adds each new one after it expires (section 4).

## Part A — Data plumbing

### 1. Data access (Upstox Plus)

- [x] Switch to Plus
- [x] Read-only spike with `--limit`, to confirm:
  - [x] earliest Nifty expiry available today
  - [x] intervals available (5m / 15m / 60m)
  - [x] whether OI comes with the candles

### 2. Contract master

- [ ] Current contracts from Upstox's NSE\_FO instrument file
- [x] Expired contracts: expiries endpoint, then expired contract keys
- [ ] Own broker-agnostic contract ID (e.g. `NIFTY|2026-10-28|25000|CE`), Upstox and Dhan keys mapped to it
- [ ] Fields: underlying, expiry, weekly/monthly, strike, CE/PE, lot size
- [x] Expiry calendar, including the weekday change history (verify before coding)

### 3. Historical backfill of expired contracts

- [x] Scope: Nifty only, which strikes, which expiries, which timeframes
- [x] R2 Parquet folder layout for contracts
- [x] Reader-rules audit re-run on option data (zero prices, post-15:30 bars, special sessions)

### 4. Ongoing fetch jobs (perishable)

- [ ] Post-expiry archive job, so no expiry is ever lost. For now a manual rerun the morning after each Tuesday expiry: Nifty intraday refresh, then the archive fetch (band, futures, rest), then the IV/Greeks run. Each skips what is already stored.
- [ ] Intraday candles for live contracts (same next-day rule as the Nifty intraday refresh)
- [ ] Option chain snapshots: OI, OI change, IV, Greeks, LTP. History only builds from the day collection starts.

### 5. Nifty futures

- [ ] Futures OHLCV + OI as a continuous series across expiries
- [ ] Basis / premium over spot
- [ ] Futures volume as a stand-in for the missing Nifty index volume (research item, not a decision)

### 6. Investor footprint data

- [ ] NSE participant-wise OI and volume (FII / DII / Pro / Client), daily
  - [ ] FII index futures long/short
  - [ ] FII options positioning
- [ ] OI build-up labels: long build-up, short build-up, short covering, long unwinding
- [ ] OI concentration as S&R (heaviest call/put OI strikes), PCR, max pain

### 7. Derived values

- [x] IV from option price via Black-Scholes, then Greeks
  - [x] Settle risk-free rate and dividend inputs
  - [x] Check against Upstox's live Greeks
- [x] One spec doc per calculation, as with the indicators

Built 29 Oct 2026: Black's model on the forward price, with the forward taken from put-call parity each minute (no dividend guess needed). Rate 5.50% (RBI repo rate). Theta follows Upstox's convention: pure time decay, the same for a call and a put at the same strike. Checked against Upstox's live option chain: IV within 0.1 point, delta within 0.003.

### 8. Existing modules on CE/PE charts

- [ ] Horizontal S&R, Zig Zag, trendlines and VWAP run on the option contract's 5m chart
- [ ] "Option chart is trending, not sideways or low-momentum" check for the entry rule
- [ ] Option R1/R2/R3 mapped from Nifty's levels

### 9. Later

- [ ] Backtest of the options method
- [ ] Frontend view
- [ ] Alerts

## Part B — Trading, analysis and risk

### 10. Option price behaviour (premium vs Nifty)

- [ ] Delta: premium points per Nifty point, so Nifty's R1/R2/R3 become premium targets
- [ ] Theta: premium decay per hour, especially on expiry day and the day before
- [ ] Gamma on expiry day: small Nifty moves, big premium swings
- [ ] IV crush after events: premium falls even when Nifty moves the right way
- [ ] Time-of-day premium behaviour inside the 09:30–11:30 window

### 11. Strike and expiry selection

- [ ] Best move per rupee risked: ATM / ITM / OTM, by days to expiry
- [ ] Current week vs next week near expiry
- [ ] Liquidity filter: bid-ask spread, volume, OI

#### Decisions so far (27 Oct 2026)

- Nifty 50 only, weekly expiry, intraday option buying.
- Starting strike: 2 OTM. From trading experience, 2–4 OTM give the big moves. The study below confirms or changes it.
- Start with 1 lot, grow to ₹1 lakh, later ₹10 lakh. The chosen contract must stay within one order: freeze limit 3,510 units (54 lots of 65) from 5 Oct 2026.
- Position sizing and money management stay in section 14.

#### Contract study build plan

1. **Pick sample days.** Strong candle days from history: red and green, in uptrend, downtrend, sideways and ranging. Checked on charts before use.
2. **Fetch contracts.** For each sample day: current weekly expiry, ATM ±9 strikes, CE and PE (38 contracts), 5m candles plus OI.
3. **Compute.** Greeks and IV from premium, Nifty and time to expiry (no historical Greeks from Upstox). Indicators on each contract chart: VWAP, horizontal S&R, trendlines.
4. **Find the contract.** Premium move per strike in the 09:30–11:30 window (points, %, ₹ per lot) against Nifty's move; behaviour when the trend fails; volume and OI for up to 54 lots; split by day type and weekday, drawn on charts.
5. **Study price moves.** Which day types and weekdays to trade or skip.
6. **Entry and exit.** Trendline and S&R method applied to the chosen contract, backtested, then finalized as the everyday strategy.

#### Progress (30 Oct 2026)

1. **Sample days: done, review pending.** Picked from the full Nifty history to cover every test case (months, phases, weekdays, gaps, strong red and green days). Charts built: one page per day with Nifty, the CE, the PE and futures on one time axis. Ash's chart review is still open.
2. **Fetch: done, widened to everything.** Instead of only the sample days, every weekly expiry Upstox serves is archived permanently in R2:
   - options ATM ±9 strikes at 1 minute, over each contract's last 2 weeks: 108 expiries, about 28 million rows
   - the rest of each option chain at 30 minutes (for OI, PCR and max pain later)
   - monthly Nifty futures at 1 minute
   - audit: 105 of 109 option weeks and 24 of 25 futures months fully clean
   - known gaps Upstox can't fill: the 26 Dec 2024 week and Dec 2024 futures; 7 round-strike contracts with no candles (27 Mar 2025, 26 Jun 2025, 30 Sep 2025); 15:30–15:40 bars in Aug–Oct 2026 weeks (after the 15:10 auto square-off, not needed)
   - open: the 27 Oct 2026 week was fetched before Nifty data for 26–27 Oct existed; re-run the audit after the Nifty refresh and refetch that week if flagged
   - fixed 30 Oct: refetching one month's futures on its own started its file a week early; October 2026 futures to be refetched once with the fix
3. **Compute: IV and Greeks done and checked.** IV, delta, gamma, theta, vega, OI change (vs previous minute and previous day) and strikes-from-ATM for every stored contract, every minute: 108 expiries, about 28 million rows. Near-ATM IV available for 99.9–100% of minutes. Checked against outside sources on 30 Oct: prices match NSE's daily file on 20 days (open 99%, high and low 100%, last trade 91% with tiny misses); IV moves with India VIX (correlation 0.80); put IV above call IV on 84% of days, the normal Nifty shape. Indicators on the contract charts (VWAP, S&R, trendlines) are not started.
4. **Find the contract**, 5. **Study price moves**, 6. **Entry and exit**: next, starting with Ash's definition of a good premium move.

#### Reading traps found so far

Fortuna will flag each of these next to the value whenever it shows it, so it isn't read wrong.

- **IV looks low on Fridays, Mondays and holiday weeks.** Time to expiry counts calendar days, as Upstox does, but Nifty only moves on trading days. Weekends and holidays inside the time left spread the same premium over more days, so the IV number drops. Compare IV only between days with the same days-to-expiry, never across weekdays. Example: the week ending 30 Dec 2025 shows ATM IV as low as 6.1.
- **IV can look very high near expiry.** With only minutes left, even a small premium turns into a large IV number, so a high reading on an expiry afternoon is not by itself a sign of fear. Real panic days also show high IV, such as the April 2025 tariff fall. Highest daily ATM IV in the archive: 67.8, in the week ending 5 Dec 2024. Which of these it is gets checked in the study.
- **Dhan's Greeks and IV columns don't refresh** (seen 29 Oct 2026: identical at 14:17 and 14:23 while prices moved). Dhan's prices and OI are correct, so trading on Dhan is fine; read Greeks and IV on Upstox, or on Fortuna once its live view exists.
- **OI levels are Upstox's, not NSE's.** Upstox's end-of-day OI runs about 5% above NSE's official figure (median, up to 48%; cause not known yet). OI build-up within our data is consistent; official OI levels (PCR, max pain) should come from NSE's daily file.
- **Volume is in units, not lots.** Divide by the lot size (25, then 75, now 65) to compare with NSE or a broker's lot count.

### 12. Volatility regime

- [ ] India VIX level and direction
- [ ] IV rank / percentile: options cheap or expensive today
- [ ] Expected move from the ATM straddle price
- [ ] Event calendar that inflates IV: RBI, budget, results, expiry days

### 13. Writers' footprint

Working assumption, to verify in research: retail mostly buys while institutions and prop desks mostly write. If it holds, following the writers is following the money.

- [ ] Intraday OI shifts: where calls and puts are written or unwound during the day
- [ ] Call-wall and put-wall strikes moving up or down in the session
- [ ] Dealer gamma exposure (GEX): moves dampened or accelerated (research item)
- [ ] Futures rollover % and cost of carry at expiry, as institutional conviction

### 14. Risk and money management

- [ ] Position size in lots from capital and risk per trade
- [ ] Stop-loss: Nifty-level based (trendline break) vs premium based, and how one maps to the other
- [ ] Max loss per day; stop after N losing entries
- [ ] Charges per round trip (brokerage, STT, exchange fees, GST, stamp duty) → minimum premium move to break even
- [ ] Slippage allowance

### 15. Exchange and SEBI rules

- [ ] Lot sizes and their change history (needed for backtests)
- [ ] Freeze quantity, expiry-day margin rules, weekly expiry rules (verify current values)
- [ ] Stock options only:
  - [ ] F&O ban list (MWPL)
  - [ ] Physical settlement of in-the-money contracts at expiry
  - [ ] Results dates

### 16. Trade journal and review

- [ ] Each trade placed on Dhan recorded against the Fortuna reading at that moment
- [ ] P&L split: direction vs IV change vs time decay
- [ ] Feeds the predictor / backtest open item later

### 17. Backtest realism for options

- [ ] Real contract premiums from the archive, not Nifty points
- [ ] Spreads, charges and slippage included

## Next step

Ash defines what a good premium move is for him. Then the study records what Nifty, IV, the Greeks, OI and volume showed just before every good move and every failed start, across all stored expiries, to find the entry and skip conditions.

## Sources

- [Upstox Plus Plan — Terms & Conditions](https://upstox.com/files/terms-and-condition/plus-pack.pdf)
- [Upstox Help: Does the brokerage plan change with Upstox Plus?](https://upstox.com/help-center/does-the-brokerage-plan-change-with-upstox-plus-264072/)
- [Upstox Community: Historical instruments of Options](https://community.upstox.com/t/historical-instruments-of-options/9028)
- [Upstox Community: Enable API access for F&O data](https://community.upstox.com/t/how-to-enable-api-access-for-fetching-fno-futures-options-data-option-chain-historical-live-data/14000)
- [Upstox Community: Expired Instruments toggle (Plus active)](https://community.upstox.com/t/expired-instruments-api-toggle-missing-in-developer-console-plus-plan-active/11428)
- [Upstox Community: Historical availability for expired options](https://community.upstox.com/t/historical-availability-retrieval-limit-per-query-for-expired-options-contract/9245)
- [Upstox Community: F&O data before first expiry (2024-10-04)](https://community.upstox.com/t/getting-historical-f-o-data-before-first-expiry-2024-10-04/9491)
- [Upstox API: Option chain](https://upstox.com/developer/api-documentation/get-pc-option-chain)
- [RBI hikes repo rate to 5.50% (GKToday)](https://www.gktoday.in/rbi-hikes-repo-rate-by-25-basis-points-to-5-50/)
- [Upstox Community: today's candle only in the intraday API](https://community.upstox.com/t/historical-data-api-missing-current-day-candle-after-market-close/14005)
