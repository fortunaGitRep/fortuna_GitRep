# Options IV and Greeks (Nifty 50 weekly options)

What Fortuna computes, exactly how, how it was checked, and what to watch for when reading it.

Built 29 Oct 2026. Code: `backend/modules/Module_F_Tech_Indicators_Funnel/options_indicators/greeks/`

| File | Job |
|---|---|
| `black76.py` | The maths: price, implied volatility, Greeks, forward from put-call parity |
| `archive_greeks.py` | Runs the maths over every stored expired contract, every minute; writes to R2 |
| `live_greeks_check.py` | Compares Fortuna's values with Upstox's live option chain |
| `verify_options_archive.py` | Checks the stored history against NSE's bhavcopy and India VIX |
| `test_black76.py`, `test_archive_greeks.py` | 10 tests (maths against known answers, synthetic archive) |

Reader: `backend/modules/market_data/upstox/expired_archive_reader.py`, part `greeks`.

## 1. Model

- **Black's model (Black-76) on the forward price** of the option's own expiry. This is the textbook model for index options (Hull, *Options, Futures and Other Derivatives*). European exercise, which matches Nifty index options.
- **Forward price, per minute, from put-call parity:** take the strike where the CE and PE prices are closest, and the 3 strikes nearest it that have both prices; forward = median of K + (C − P) × e^(rT). This uses the market's own prices, so no dividend guess is needed, and it avoids the mismatch between the weekly expiry and the monthly futures. If a minute has no CE/PE pair, the previous minute's forward is carried, for up to 5 minutes.
- **Time to expiry:** calendar minutes from the bar's close (bar start + 1 minute) to that expiry day's F&O close (15:30; 15:40 from 3 Aug 2026), divided by 365 × 24 × 60.
- **Rate:** 5.50%, the RBI repo rate after the Oct 2026 hike, one constant. In Black's model the rate only discounts the price, so its effect on a weekly option is under 0.1%.
- **Price used:** the 1-minute bar's close (last traded price), the only price the archive has.

## 2. Outputs (per contract, per minute)

| Column | Meaning | Units |
|---|---|---|
| `forward` | Nifty forward for that expiry at that minute | points |
| `t_minutes` | minutes left to expiry | minutes |
| `otm_steps` | strikes out of the money vs the forward: +2 = 2 OTM, 0 = ATM, −2 = 2 ITM (CE: (K − F)/50, PE: (F − K)/50) | strikes |
| `iv` | implied volatility | % (13.0 = 13%), Upstox style |
| `delta` | premium change per 1 Nifty point | CE 0..1, PE −1..0 |
| `gamma` | delta change per 1 Nifty point | per point |
| `theta` | premium change per calendar day with the forward held still (Upstox's convention: pure time decay, same for CE and PE at one strike) | ₹ per day |
| `vega` | premium change per 1 IV point | ₹ per vol point |
| `oi_chg_1m` | OI change vs the contract's previous bar | contracts |
| `oi_chg_day` | OI vs the contract's last OI of the previous trading day | contracts |

Also kept: expiry, instrument_key, strike, option_type, ts, trade_date, close, volume, oi.

Blank (NaN) where the model can't price: the expiry's final minute (no time left), a price below intrinsic value, or no forward that minute.

## 3. Storage and runs

- R2: `upstox/nifty_options_greeks/1m/<expiry>.parquet`, one file per expiry, about 10–18 MB each.
- Full run 29 Oct 2026: 108 expiries (every stored band week), 28.3 million rows, about 7 s per expiry, 0 failures.
- Refresh: the same command computes new expiries and skips stored ones (`--force` recomputes, `--expiry` one week, `--candidates` only the sample days' expiries).
- Logs: `logs/options_greeks_logs/greeks_run.log` and `greeks_summary.log`.
- Order after each Tuesday expiry: Nifty intraday refresh → expired-contract fetch → this run.

## 4. How it was checked

| Check | Result |
|---|---|
| Unit tests: put-call parity, IV round trip on calls and puts, Greeks against finite differences, theta equal for CE and PE at the forward | pass |
| Synthetic archive priced at a known 13% IV with a moving forward: IV recovered, forward recovered, final minute blank, OI changes correct, missing minute carries the forward | pass |
| Live check against Upstox's option chain, 29 Oct 2026, three runs (3, 3 and 1 snapshots, 14:05–14:18), ATM ±9 strikes, CE and PE, 38 contracts each | median gaps: IV 0.08–0.11 point, delta 0.002–0.003; gamma and vega equal (Upstox rounds gamma to 4 decimals); theta within 0.2 per strike after switching to Upstox's convention |
| Archive quality, all 108 expiries | near-ATM minutes with an IV: 99.9–100%; CE vs PE IV at the same strike: 0.01–0.04 point apart |

| Outside check, 30 Oct 2026: 20 days over 2 years, ATM ±2 strikes, 199 contracts vs NSE's F&O bhavcopy | open 99%, high 100%, low 100%, last trade 91% (median miss 0.20) before 3 Aug 2026; OI see §5 |
| ATM IV vs India VIX, days 2 trading days before expiry (103 days) | correlation 0.80 (levels), 0.68 (day-to-day changes); IV ≈ 0.94 × VIX |
| IV across strikes | put IV above call IV (3 strikes OTM) on 84% of 518 days; smooth curves on calm, crash (7 Apr 2025) and recent days |

The CE vs PE agreement partly follows from the method (both use the same parity forward), so it shows the values are consistent rather than proving accuracy. Accuracy comes from the live check.

Same check on Dhan (29 Oct 2026): Dhan's Greek and IV columns stayed identical between 14:17 and 14:23 while prices moved. They don't refresh. Its prices and OI match Upstox.

## 5. Reading traps

Fortuna must flag these next to the value whenever it shows it.

1. **IV looks low on Fridays, Mondays and in holiday weeks.** Time to expiry counts calendar days, but Nifty only moves on trading days. Weekends and holidays in the time left spread the same premium over more days, so IV drops. Compare IV only between days with the same days-to-expiry. Example: the week ending 30 Dec 2025, ATM IV as low as 6.1.
2. **IV can look very high near expiry.** With minutes left, a small premium becomes a large IV number. Real panic days also show high IV. Highest daily ATM IV in the archive: 67.8 (week ending 5 Dec 2024). The study confirms which days are which.
3. **Dhan's Greeks don't refresh.** Read Greeks and IV on Upstox or Fortuna.
4. **OI level is Upstox's, not NSE's.** The last 1-minute OI from Upstox is above NSE's end-of-day OI on almost every contract (median +4.9%, up to +48%; cause not known). OI changes within Upstox data are consistent; an OI level compared with NSE-published figures (PCR, max pain) needs NSE's bhavcopy.
5. **Volume units.** Upstox volume is in units (quantity); NSE reports contracts (lots). Divide by the lot size (25 / 75 / 65 over the archive).

## 6. Known limits

- One fixed rate for the whole history (the repo rate changed several times since Oct 2024). Effect on weekly options under 0.1%.
- IV comes from last traded prices; a thin contract's last trade can be stale, which mostly affects far OTM strikes.
- Weeks with archive gaps have no Greeks for the missing contracts (26 Dec 2024 week; 7 round-strike contracts).

## Sources

- [Upstox API: Option chain](https://upstox.com/developer/api-documentation/get-pc-option-chain)
- [RBI hikes repo rate to 5.50% (GKToday)](https://www.gktoday.in/rbi-hikes-repo-rate-by-25-basis-points-to-5-50/)
- J. C. Hull, *Options, Futures and Other Derivatives* (Black's model, Greeks)
