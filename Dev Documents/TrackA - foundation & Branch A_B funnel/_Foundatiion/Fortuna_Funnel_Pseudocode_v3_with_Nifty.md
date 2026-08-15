# Fortuna Direction Funnel – Module Pseudo-code (v3, Nifty 50)

This document defines pseudo-code for each module in the Fortuna Foundation - Direction & Decision Funnel, aligned with the v3 corrections, and shows how to apply the funnel to the **Nifty 50 index**.

Each module returns a `ModuleOutput` object with three key weights:

- `direction_weight` – how much the module can sway the directional bias (up/down).
- `context_weight` – how important it is for day-type, volatility, theta, etc.
- `confidence_mult` – multiplier on conviction from other modules (0.0–>1.0+).

The funnel aggregates these to produce a `Verdict` for the day.

---

## Shared Data Structures

```pseudo
struct ModuleOutput:
    signal            // description or enum for what this module sees today
    direction_weight  // 0.0–1.0, how much it affects direction
    context_weight    // 0.0–1.0, how much it affects context/day-type
    confidence_mult   // 0.0–>1.0, multiplies conviction

struct Verdict:
    tradeable           // GO / NO_GO
    day_type            // trend / range / chop / drift / news-day
    direction           // up / down / sideways
    conviction          // 0.0–1.0
    volatility_character// calm / normal / high / chaotic
    size                // full / reduced / avoid
    trap_risk           // low / moderate / high
    stop                // SL logic (VWAP/ST/ATR-based)
```

---

## 1. Macro Modules (MAC-1..3)

### MAC-1 – Global Macro News

```pseudo
function MAC_1(global_events) -> ModuleOutput:
    if global_events.has_major_shock:
        signal = "event_shock"
        direction_weight = 0.4   // OPEN bias only
        context_weight = 0.6
        confidence_mult = 0.8    // cap conviction; two-sided risk
    else:
        signal = "neutral"
        direction_weight = 0.0
        context_weight = 0.3
        confidence_mult = 1.0
    return ModuleOutput(signal, direction_weight, context_weight, confidence_mult)
```

### MAC-2 – US/Asia Correlation + GIFT Cue

```pseudo
function MAC_2(us_close, asia_status, gift_gap, vix_level, time_of_day) -> ModuleOutput:
    aligned_cues = (us_close.direction == asia_status.direction == gift_gap.direction)
    normal_vix   = (vix_level in NORMAL_RANGE)

    if time_of_day < 10:00 and aligned_cues and normal_vix and abs(gift_gap.pct) >= 0.002:
        signal = "aligned_open_bias"
        direction_weight = 0.5   // open/first 30–60 min
        context_weight = 0.6
        confidence_mult = 1.1
    else:
        signal = "decayed_or_contradictory"
        direction_weight = 0.0   // after ~10:00 or noisy
        context_weight = 0.3
        confidence_mult = 1.0
    return ModuleOutput(signal, direction_weight, context_weight, confidence_mult)
```

### MAC-3 – Macro Levels (DXY, US10Y, Crude, Gold)

```pseudo
function MAC_3(dxy, us10y, crude, gold) -> ModuleOutput:
    if dxy_above_threshold(dxy) or us10y_above_threshold(us10y):
        signal = "risk_off_swing_bias"
        direction_weight = 0.4   // weekly/monthly only
        context_weight = 0.5
        confidence_mult = 0.9
    else:
        signal = "neutral_swing_background"
        direction_weight = 0.1   // small bias for swing only
        context_weight = 0.4
        confidence_mult = 1.0
    // intraday engine must ignore this direction_weight
    return ModuleOutput(signal, direction_weight, context_weight, confidence_mult)
```

---

## 2. National News (NAT-1)

```pseudo
function NAT_1(event_calendar, surprise_flag) -> ModuleOutput:
    if event_calendar.has_today_event:
        if surprise_flag:
            signal = "event_surprise"
            direction_weight = 0.3   // genuine surprise only
            context_weight = 0.8
            confidence_mult = 0.7    // caution
        else:
            signal = "scheduled_event"
            direction_weight = 0.0
            context_weight = 0.9
            confidence_mult = 0.6    // IV-crush risk
    else:
        signal = "no_event"
        direction_weight = 0.0
        context_weight = 0.2
        confidence_mult = 1.0
    return ModuleOutput(signal, direction_weight, context_weight, confidence_mult)
```

---

## 3. Flows (FLO-1, FLO-2)

### FLO-1 – FII/DII Cash Flow

```pseudo
function FLO_1(fii_net, dii_net, rolling_fii_dii_trend) -> ModuleOutput:
    total_net = fii_net + dii_net

    if trend_strong(rolling_fii_dii_trend) and total_net > 0:
        signal = "supportive_flows"
        direction_weight = 0.2    // next-day swing bias only
        context_weight = 0.5
        confidence_mult = 1.1
    elif trend_strong(rolling_fii_dii_trend) and total_net < 0:
        signal = "pressure_flows"
        direction_weight = 0.2
        context_weight = 0.5
        confidence_mult = 0.9
    else:
        signal = "noisy_or_offset_flows"
        direction_weight = 0.0    // same-day intraday
        context_weight = 0.3
        confidence_mult = 1.0
    return ModuleOutput(signal, direction_weight, context_weight, confidence_mult)
```

### FLO-2 – FII Index Derivatives Positioning

```pseudo
function FLO_2(fii_futures_ls_ratio, retail_vs_fii_divergence, flo1_signal) -> ModuleOutput:
    if retail_vs_fii_divergence and flo1_signal in ["supportive_flows","pressure_flows"]:
        signal = "trap_signal"
        direction_weight = 0.2   // confirmation only
        context_weight = 0.5
        confidence_mult = 1.2    // strengthen concordant cascades
    else:
        signal = "neutral_intent"
        direction_weight = 0.0
        context_weight = 0.3
        confidence_mult = 1.0
    return ModuleOutput(signal, direction_weight, context_weight, confidence_mult)
```

---

## 4. Pre-market Gates (PRE-1..5)

### PRE-1 – India VIX Regime

```pseudo
function PRE_1(vix_level, vix_percentile) -> ModuleOutput:
    if vix_percentile < LOW_PCTL:
        signal = "calm"
        direction_weight = 0.0
        context_weight = 0.8
        confidence_mult = 1.2   // trend / premium-buy friendly
    elif vix_percentile in NORMAL_BAND:
        signal = "normal"
        direction_weight = 0.0
        context_weight = 0.8
        confidence_mult = 1.0
    elif vix_percentile in HIGH_BAND:
        signal = "elevated"
        direction_weight = 0.0
        context_weight = 0.9
        confidence_mult = 0.8   // size down
    else:
        signal = "turbulent"
        direction_weight = 0.0
        context_weight = 1.0
        confidence_mult = 0.5   // avoid options buying
    return ModuleOutput(signal, direction_weight, context_weight, confidence_mult)
```

### PRE-2 – GIFT Nifty

```pseudo
function PRE_2(gift_gap_pct, time_of_day, is_domestic_event) -> ModuleOutput:
    if is_domestic_event:
        signal = "event_morning_context_only"
        direction_weight = 0.0
        context_weight = 0.5
        confidence_mult = 1.0
    else:
        if abs(gift_gap_pct) < 0.002:  // <0.2%
            signal = "small_gap_noise"
            direction_weight = 0.0
            context_weight = 0.3
            confidence_mult = 1.0
        elif abs(gift_gap_pct) < 0.005:
            signal = "moderate_gap_bias"
            direction_weight = 0.5 if time_of_day < 10:00 else 0.0
            context_weight = 0.6
            confidence_mult = 1.1
        else:
            signal = "large_gap_bias"
            direction_weight = 0.7 if time_of_day < 10:00 else 0.0
            context_weight = 0.7
            confidence_mult = 1.2
    return ModuleOutput(signal, direction_weight, context_weight, confidence_mult)
```

### PRE-3 – Gap Up / Gap Down Behaviour

```pseudo
function PRE_3(actual_gap_pct, atr_normalized_gap, trend_alignment, vix_signal, news_flag) -> ModuleOutput:
    if abs(actual_gap_pct) < TINY_GAP_THRESHOLD:
        gap_type = "common_tiny"
        stance   = "sit_out_open"
        direction_weight = 0.1   // almost neutral
        context_weight = 0.4
        confidence_mult = 1.0
    elif aligned_runaway(atr_normalized_gap, trend_alignment, vix_signal, news_flag):
        gap_type = "runaway"
        stance   = "trade_with_gap"
        direction_weight = 0.4
        context_weight = 0.6
        confidence_mult = 1.1
    elif genuine_breakaway(news_flag):
        gap_type = "breakaway"
        stance   = "trade_with_gap_all_day"
        direction_weight = 0.5
        context_weight = 0.7
        confidence_mult = 1.2
    elif exhaustion_gap(atr_normalized_gap, vix_signal, trend_alignment):
        gap_type = "exhaustion"
        stance   = "fade_after_rollover"
        direction_weight = 0.3   // only after rollover
        context_weight = 0.7
        confidence_mult = 1.0
    else:
        gap_type = "uncertain"
        stance   = "wait"
        direction_weight = 0.0
        context_weight = 0.5
        confidence_mult = 0.9
    return ModuleOutput(gap_type + ":" + stance, direction_weight, context_weight, confidence_mult)
```

### PRE-4 – CPR (Central Pivot Range)

```pseudo
function PRE_4(cpr_width_points, price_vs_cpr, ema_bias, rsi_bias, vwap_bias) -> ModuleOutput:
    // width = day-type
    if cpr_width_points < NARROW_THRESHOLD:
        width_signal = "narrow_trend_possible"
        width_context_weight = 0.7
    elif cpr_width_points > WIDE_THRESHOLD:
        width_signal = "wide_range_day"
        width_context_weight = 0.7
    else:
        width_signal = "normal"
        width_context_weight = 0.5

    // location = small directional weight when aligned with other biases
    aligned = (ema_bias == rsi_bias == vwap_bias)
    if price_vs_cpr == "above_TC" and aligned == "bull":
        loc_direction_weight = 0.2
        loc_signal = "bull_bias_zone"
    elif price_vs_cpr == "below_BC" and aligned == "bear":
        loc_direction_weight = 0.2
        loc_signal = "bear_bias_zone"
    else:
        loc_direction_weight = 0.0
        loc_signal = "indecision_zone"

    signal = width_signal + " | " + loc_signal
    direction_weight = loc_direction_weight
    context_weight = width_context_weight
    confidence_mult = 1.0
    return ModuleOutput(signal, direction_weight, context_weight, confidence_mult)
```

### PRE-5 – Weekday Theta Map

```pseudo
function PRE_5(weekday, is_expiry_pm) -> ModuleOutput:
    if weekday == "Mon":
        signal = "pressure_cooker_mon"
        direction_weight = 0.0
        context_weight = 0.8
        confidence_mult = 0.9   // buyer headwind
    elif weekday == "Tue":
        if is_expiry_pm:
            signal = "Tue_expiry_PM_pin"
            direction_weight = 0.0
            context_weight = 0.9
            confidence_mult = 0.8   // avoid new positions
        else:
            signal = "Tue_expiry_AM_tradeable"
            direction_weight = 0.0
            context_weight = 0.8
            confidence_mult = 1.1
    elif weekday == "Wed":
        signal = "Wed_post_expiry_drift"
        direction_weight = 0.0
        context_weight = 0.7
        confidence_mult = 0.9   // reduced size
    elif weekday == "Thu":
        signal = "Thu_Sensex_expiry_spill"
        direction_weight = 0.0
        context_weight = 0.7
        confidence_mult = 1.0
    elif weekday == "Fri":
        signal = "Fri_pre_weekend_theta"
        direction_weight = 0.0
        context_weight = 0.7
        confidence_mult = 1.0
    return ModuleOutput(signal, direction_weight, context_weight, confidence_mult)
```

---

## 5. Direction Engine (ENG-1..11)

### ENG-1 – Regime Filter (ADX + CHOP)

```pseudo
function ENG_1(adx, chop) -> ModuleOutput:
    if chop < 38.2 and adx > 25:
        signal = "trend_regime"
        direction_weight = 0.0
        context_weight = 0.7
        confidence_mult = 1.2
    elif chop > 61.8 or adx < 20:
        signal = "chop_regime"
        direction_weight = 0.0
        context_weight = 0.7
        confidence_mult = 0.6   // gate others
    else:
        signal = "uncertain_regime"
        direction_weight = 0.0
        context_weight = 0.5
        confidence_mult = 0.9
    return ModuleOutput(signal, direction_weight, context_weight, confidence_mult)
```

### ENG-2 – EMAs Across Timeframes

```pseudo
function ENG_2(ema_stack_tf, slope_tf) -> ModuleOutput:
    if multi_tf_bull_stack(ema_stack_tf, slope_tf):
        signal = "bull_trend"
        direction_weight = 0.7
        context_weight = 0.6
        confidence_mult = 1.1
    elif multi_tf_bear_stack(ema_stack_tf, slope_tf):
        signal = "bear_trend"
        direction_weight = 0.7
        context_weight = 0.6
        confidence_mult = 1.1
    else:
        signal = "sideways_tangled"
        direction_weight = 0.0
        context_weight = 0.5
        confidence_mult = 0.8
    return ModuleOutput(signal, direction_weight, context_weight, confidence_mult)
```

### ENG-3 – RSI (Cardwell Ranges)

```pseudo
function ENG_3(rsi_tf) -> ModuleOutput:
    if rsi_in_bull_range(rsi_tf):
        signal = "bull_range"
        direction_weight = 0.5
        context_weight = 0.6
        confidence_mult = 1.1
    elif rsi_in_bear_range(rsi_tf):
        signal = "bear_range"
        direction_weight = 0.5
        context_weight = 0.6
        confidence_mult = 1.1
    elif rsi_in_sideways(rsi_tf):
        signal = "sideways"
        direction_weight = 0.0
        context_weight = 0.5
        confidence_mult = 0.8
    return ModuleOutput(signal, direction_weight, context_weight, confidence_mult)
```

### ENG-4 – MACD Crossover (HTF Filter)

```pseudo
function ENG_4(macd_htf, macd_ltf) -> ModuleOutput:
    if macd_htf_trending(macd_htf):
        signal = "htf_trend_filter"
        direction_weight = 0.2   // confirm only
        context_weight = 0.5
        confidence_mult = 1.0
    else:
        signal = "htf_unclear"
        direction_weight = 0.0
        context_weight = 0.4
        confidence_mult = 0.9
    // macd_ltf is never given standalone direction_weight
    return ModuleOutput(signal, direction_weight, context_weight, confidence_mult)
```

### ENG-5 – Supertrend

```pseudo
function ENG_5(supertrend_tf, vwap_bias, ema_bias, regime_signal) -> ModuleOutput:
    aligned = (supertrend_tf.color == vwap_bias == ema_bias)
    if aligned and regime_signal == "trend_regime":
        signal = "trend_filter_confirmed"
        direction_weight = 0.5
        context_weight = 0.5
        confidence_mult = 1.1
    else:
        signal = "filter_only"
        direction_weight = 0.0
        context_weight = 0.5
        confidence_mult = 0.9
    return ModuleOutput(signal, direction_weight, context_weight, confidence_mult)
```

### ENG-6 – Stochastic RSI

```pseudo
function ENG_6(stochrsi_state, cascade_bias) -> ModuleOutput:
    if stochrsi_cross_from_extreme_in_cascade_direction(stochrsi_state, cascade_bias):
        signal = "entry_timing_trigger"
        direction_weight = 0.0
        context_weight = 0.4
        confidence_mult = 1.0   // timing only
    else:
        signal = "noise_or_exit"
        direction_weight = 0.0
        context_weight = 0.4
        confidence_mult = 1.0
    return ModuleOutput(signal, direction_weight, context_weight, confidence_mult)
```

### ENG-7 – VWAP + SL Decisions

```pseudo
function ENG_7(price_vs_vwap, ema_bias, rsi_bias, time_of_day) -> ModuleOutput:
    aligned = (ema_bias == rsi_bias)
    early = (time_of_day < 9:45)

    if price_vs_vwap == "above" and aligned == "bull":
        signal = "intraday_bull_bias"
        direction_weight = 0.5
        context_weight = 0.6
        confidence_mult = 1.1 if not early else 1.0
    elif price_vs_vwap == "below" and aligned == "bear":
        signal = "intraday_bear_bias"
        direction_weight = 0.5
        context_weight = 0.6
        confidence_mult = 1.1 if not early else 1.0
    else:
        signal = "oscillating_flat"
        direction_weight = 0.0
        context_weight = 0.5
        confidence_mult = 0.9
    return ModuleOutput(signal, direction_weight, context_weight, confidence_mult)
```

### ENG-8 – Volume & Liquidity

```pseudo
function ENG_8(breakout_volume_rvol, liquidity_ok) -> ModuleOutput:
    if not liquidity_ok:
        signal = "illiquid"
        direction_weight = 0.0
        context_weight = 0.7
        confidence_mult = 0.0   // hard NO-GO
    elif breakout_volume_rvol > THRESHOLD:
        signal = "volume_confirms_move"
        direction_weight = 0.0
        context_weight = 0.6
        confidence_mult = 1.2
    else:
        signal = "normal_or_weak_volume"
        direction_weight = 0.0
        context_weight = 0.5
        confidence_mult = 0.9
    return ModuleOutput(signal, direction_weight, context_weight, confidence_mult)
```

### ENG-9 – ATR (Average True Range)

```pseudo
function ENG_9(atr_level, atr_percentile) -> ModuleOutput:
    if atr_percentile_low(atr_percentile):
        signal = "compression"
        direction_weight = 0.0
        context_weight = 0.7
        confidence_mult = 1.0   // future squeeze, not now
    elif atr_percentile_high(atr_percentile):
        signal = "high_vol"
        direction_weight = 0.0
        context_weight = 0.8
        confidence_mult = 0.9   // wider SL
    else:
        signal = "normal_vol"
        direction_weight = 0.0
        context_weight = 0.7
        confidence_mult = 1.0
    return ModuleOutput(signal, direction_weight, context_weight, confidence_mult)
```

### ENG-10 – Bollinger Bands + Squeeze

```pseudo
function ENG_10(squeeze_state, hist_direction) -> ModuleOutput:
    if squeeze_state == "ON":
        signal = "squeeze_loading"
        direction_weight = 0.0
        context_weight = 0.6
        confidence_mult = 1.0
    elif squeeze_state == "FIRED":
        signal = "squeeze_fired_" + hist_direction
        direction_weight = 0.2   // via histogram + other biases
        context_weight = 0.6
        confidence_mult = 1.1
    else:
        signal = "normal_bands"
        direction_weight = 0.0
        context_weight = 0.5
        confidence_mult = 1.0
    return ModuleOutput(signal, direction_weight, context_weight, confidence_mult)
```

### ENG-11 – Support & Resistance + OI Walls

```pseudo
function ENG_11(confluence_score, oi_walls_state) -> ModuleOutput:
    if confluence_score >= 3:
        signal = "A_plus_zone"
        direction_weight = 0.0    // location only
        context_weight = 0.8
        confidence_mult = 1.2
    else:
        signal = "lonely_or_weak_level"
        direction_weight = 0.0
        context_weight = 0.5
        confidence_mult = 1.0
    return ModuleOutput(signal, direction_weight, context_weight, confidence_mult)
```

---

## 6. Direction Sequence Aggregation

```pseudo
function compute_verdict(all_module_outputs) -> Verdict:
    // 1. Regime & GO/NO-GO
    regime      = ENG_1.signal
    vix_gate    = PRE_1.signal
    weekday_ctx = PRE_5.signal

    if vix_gate == "turbulent" or weekday_ctx == "Tue_expiry_PM_pin":
        tradeable = "NO_GO"
    else:
        tradeable = "GO"

    // 2. Direction weights (macro + engine)
    dir_score_up   = sum(direction_weight_i where module bias == "bull")
    dir_score_down = sum(direction_weight_i where module bias == "bear")

    if dir_score_up > dir_score_down * 1.1:
        direction = "up"
    elif dir_score_down > dir_score_up * 1.1:
        direction = "down"
    else:
        direction = "sideways"

    // 3. Context for day_type & volatility
    day_type             = infer_day_type(PRE_3, PRE_4, ENG_1, PRE_5)
    volatility_character = infer_vol_character(PRE_1, ENG_9)

    // 4. Conviction & size
    base_conviction       = 0.5
    confidence_mult_total = product(module.confidence_mult for module in all_module_outputs)
    conviction            = base_conviction * confidence_mult_total

    if conviction > 0.7 and tradeable == "GO":
        size = "full"
    elif conviction > 0.4 and tradeable == "GO":
        size = "reduced"
    else:
        size = "avoid"

    trap_risk = infer_trap_risk(PRE_1, ENG_1, NAT_1, MAC_1)
    stop      = "VWAP/Supertrend/structure ± ATR"

    return Verdict(tradeable, day_type, direction, conviction,
                   volatility_character, size, trap_risk, stop)
```

---

## 7. Applying the Funnel to Nifty 50

The pseudo-code above is intended to be applied to the **Nifty 50 index**. To ensure the funnel is Nifty-specific, wire the modules to Nifty 50 data streams as follows.

### 7.1 Nifty 50 Data Inputs

- **Price series**
  - Nifty 50 spot OHLC (daily and intraday) for EMAs, RSI, ATR, Supertrend, CPR.
  - Nifty 50 futures for intraday VWAP, volume proxy, and EMAs/VWAP if preferred.
- **Volatility**
  - India VIX (INDEXNSE: INDIA_VIX) for PRE-1 (volatility gate).
- **Pre-market**
  - Gift Nifty (Nifty 50 futures on NSE IFSC) for PRE-2 implied opening gap.
- **Flows**
  - Daily FII/DII cash flows and index F&O positioning from NSE and trusted aggregators, mapped to Nifty.
- **Macro & News**
  - Fed decisions, global indices, DXY, US10Y, crude and gold, plus RBI/Budget/election calendar.
- **Expiry & Weekday Map**
  - Nifty 50 weekly expiry on Tuesday; Nifty monthlies on the last Tuesday.

### 7.2 Nifty-Specific Module Parameters

- **EMAs (ENG-2)**: use Nifty-appropriate EMAs (e.g., 9/20/50/200) on spot or futures.
- **RSI (ENG-3)**: tune Cardwell ranges to Nifty (bull 40–80, bear ~20–60, ceiling around ~55–60).
- **Supertrend (ENG-5)**: use Nifty-documented settings (e.g., 10/2 or 7/3) from your backtests.
- **ATR (ENG-9)**: compute per-instrument ATR for Nifty (different from BankNifty or midcaps).
- **CPR (PRE-4)**: calibrate narrow/wide thresholds (e.g., <~35 points vs >~60 points) to Nifty’s recent volatility regime.
- **S/R + OI (ENG-11)**: derive price levels and options OI walls from the Nifty 50 options chain (call/put walls, max pain, change in OI).

### 7.3 Running `compute_verdict` for Nifty 50

When you call `compute_verdict` for a given trading day on Nifty 50:

1. **Macro & news:** build `global_events` and macro inputs based on how global factors affect Nifty (MAC-1..3), plus domestic NAT-1 events.
2. **Flows:** pass Nifty-relevant FII/DII cash and index F&O data into FLO-1 and FLO-2.
3. **Pre-market:** feed Gift Nifty implied gap and India VIX into PRE-1 and PRE-2; use Nifty’s actual open vs prior close for PRE-3; compute Nifty CPR for PRE-4; apply Nifty’s Tuesday expiry calendar for PRE-5.
4. **Engine:** compute all ENG modules using Nifty price/futures data: ADX/CHOP, EMAs, RSI, MACD, Supertrend, StochRSI, VWAP, volume/liquidity, ATR, squeeze, S/R and options OI.
5. **Aggregate:** pass all `ModuleOutput` objects into `compute_verdict` to obtain the Nifty 50 verdict (tradeable, day_type, direction, conviction, volatility_character, size, trap_risk, stop).

This wiring ensures the funnel’s logic and weights operate specifically on Nifty 50, while keeping VIX, expiry, Gift Nifty, ATR, volume, and S/R in their correct context roles rather than as pure directional predictors.