# Fortuna Predictor

Oct 31, 2026 · @Ash

At 09:15 the predictor says what kind of day today will be, then takes the 09:30 option entry and the exit that suit that day type. It combines every Fortuna indicator, built now or later.

## Day categories

Every day falls into one of four kinds. Each kind gets its own way of entering and exiting.

| # | Day | Nifty move | How the option moves | How to trade it |
| --- | --- | --- | --- | --- |
| 1 | Trend day | 1.5–2%, about 300–400 points | Steady trend with no trapping swings (CE or PE). Example: 2 Jan 2025 CE | One entry, one exit |
| 2 | Swing-trend | 0.8–1.4%, or above 100 points | Swings a bit first, then a steady trend. Sometimes the trend runs only 09:15–10:15 or 10:15–11:15, with a smaller candle in the hour before or after. Example: 24 Feb 2026 PE | Stay away during the swings, then enter at the right time |
| 3 | Average day | 50–90 points | Around a 50% premium move | Catch the 50%; don't wait for 200–300% |
| 4 | Chop day | Under 50 points, or extreme swings both ways | Little real move, or swings that look like a swing-trend day but keep fooling. The swings show on the option charts even when the Nifty candles look small | Find a way to identify it early. Then stay away, or book the swings in several small trades |

The names follow the day types in Market Profile (James Dalton, *Mind Over Markets*). Trend day = Dalton's trend day. Swing-trend = his double-distribution trend day, and the bigger normal-variation days. Average day = his normal day. Chop day = his non-trend and neutral days.

Open: the bounds still need settling. 90–100 points sits between days 3 and 2, and 1.4–1.5% between days 2 and 1. At Nifty 24,000, 0.8% is about 190 points, so "0.8–1.4% or above 100 points" needs one rule.

**Agreed order (2 Nov 2026):** fetch and combine all stored data first, with these tags on every day. Study it. Split a category only where its days need different trading rules. Each category gets its own rules, and the predictor tells Ash which category today is and so which rules to use.

Tags on every day:

- **Dalton sub-type:** trend, double-distribution, normal variation, normal, non-trend, neutral-center, neutral-extreme
- **Open type:** open-drive, open-test-drive, open-rejection-reverse, open-auction; plus where the day opened against the previous day's range
- **Direction:** CE day or PE day (put moves may need their own rules)
- **Expiry:** expiry day or not, days to expiry
- **Where the move happened:** 09:15–10:15 (the first hour, Dalton's initial balance), 10:15–11:15, or later

Volume comes from Nifty futures, since the index has none. It gets a parity check before anything is locked in.

A likely split to check: Chop day mixes no-move days (probably don't trade) and trap days (perhaps trade the swings after they show).

## Contract choice

Ash's choice so far is the OTM contract priced close to ₹40 at 09:30. Still to decide: how to choose between OTM 2, OTM 4 and the others. That will be judged with VWAP drawn on the contract charts.

What the first two days showed, bought at 09:30 with ₹1 lakh (before charges):

| Day | Contract near ₹40 | 09:30 | Lots | Profit at the high | Premium at 15:10 |
| --- | --- | --- | --- | --- | --- |
| 2 Jan 2025 (CE, expiry day) | 23950 CE, OTM 4 | ₹40.04 | 33 | ₹5.98 lakh, at 14:55 | ₹241.40 |
| 24 Feb 2026 (PE, expiry day) | 25500 PE, OTM 1 | ₹41.00 | 37 | ₹3.05 lakh, at 13:33 | ₹90.05 |

On 24 Feb 2026 the far OTM puts made a big % move to the high, but then fell back to almost nothing by 15:10 (OTM 4: ₹9.90 → ₹0.20). On 2 Jan 2025 every call ended in the money, so all nine kept their gains.

## How the predictor gets built

Each step is discussed only when we reach it, and the next one starts only after the previous one is finished.

1. Group every day of the \~2 years of stored contracts into the four day categories.
2. Work out each group's data: Nifty, the contracts, and all indicators.
3. Turn what each group shows into rules.
4. Build the predictor: at 09:15 it says what today (or the next day) will look like.
5. Entry at 09:30 based on that prediction. Biggest-move days: one entry, one exit. Big-move days: stay out during the volatility and traps, then enter at the right time.
6. Combine every Fortuna indicator, built now or later, into the predictor.

## Where we are now

**Step A done (2 Nov 2026): the day table.** All 518 trading days from 27 Sep 2024 to 30 Oct 2026. Each day has its first hour (09:15–10:15) high, low and width, how far price went beyond it and which side broke first, the Nifty move in each hour block, the first 30 minutes against the previous close, previous-day narrow-range flags, and near-month futures volume. A one-page day viewer shows each day on its chart. The futures 5m candles were checked against Upstox on 3,465 of 3,465 candles, all exact, and against Dhan's chart.

**Next: step B.** Option-chart swing measures, to catch Chop days that look like Swing-trend days. Then C: category labels, once the bounds are settled. Then D: Dalton sub-type and open type, from the books first.
