"""
Unit tests for structure_events.py (BOS / CHoCH / trend state).

Run from backend/ (output also saved to logs/market_structure_test_logs/structure_events_unit_tests.log):
  python -m modules.Module_F_Tech_Indicators_Funnel.price_action.market_structure.test_structure_events
"""

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from structure_events import current_structure, find_structure_events  # noqa: E402

TOL = 1.0
T0 = pd.Timestamp("2026-10-14 09:15")


def t(i):
    return T0 + pd.Timedelta(minutes=5 * i)


def candles(closes):
    """Simple candles: open = previous close, high/low = +-0.5 around the body."""
    rows, prev = [], closes[0]
    for c in closes:
        o = prev
        rows.append((o, max(o, c) + 0.5, min(o, c) - 0.5, c))
        prev = c
    o, h, l, c = zip(*rows)
    return pd.DataFrame({"time": [t(i) for i in range(len(closes))],
                         "open": o, "high": h, "low": l, "close": c})


def levels(*rows):
    """rows: (kind, price, active_bar)."""
    return pd.DataFrame({"kind": [r[0] for r in rows], "price": [float(r[1]) for r in rows],
                         "active_from": [t(r[2]) for r in rows]})


def test_first_break_from_neutral_is_choch():
    c = candles([100, 101, 102, 106])
    ev = find_structure_events(c, levels(("high", 105, 0)), TOL)
    assert len(ev) == 1
    r = ev.iloc[0]
    assert r["event"] == "CHoCH" and r["direction"] == "up"
    assert r["trend_before"] == "neutral" and r["trend_after"] == "uptrend"
    assert r["time"] == t(3)


def test_with_trend_break_is_bos_and_against_is_choch():
    c = candles([100, 106, 104, 103, 109, 105, 101, 95])
    lv = levels(("high", 105, 0),      # broken bar 1 -> CHoCH to uptrend
                ("low", 102, 2),       # target below
                ("high", 108, 3),      # broken bar 4 -> BOS, uptrend continues
                ("low", 100, 5))       # replaces 102; broken bar 7 -> CHoCH to downtrend
    ev = find_structure_events(c, lv, TOL)
    assert list(ev["event"]) == ["CHoCH", "BOS", "CHoCH"]
    assert list(ev["trend_after"]) == ["uptrend", "uptrend", "downtrend"]
    assert list(ev["level_price"]) == [105.0, 108.0, 100.0]
    assert ev["time"].iloc[2] == t(7)


def test_wick_beyond_is_not_an_event():
    c = candles([100, 104, 103])
    c.loc[1, "high"] = 107                  # wick above 105, close 104
    ev = find_structure_events(c, levels(("high", 105, 0)), TOL)
    assert ev.empty


def test_level_not_live_before_active_time():
    c = candles([100, 106, 104, 104, 106])   # bar 1 close above is before the level is live
    ev = find_structure_events(c, levels(("high", 105, 2)), TOL)
    # live from bar 3 on: bar 4 close 106 breaks it
    assert len(ev) == 1 and ev["time"].iloc[0] == t(4)


def test_newer_level_replaces_older_target():
    c = candles([100, 101, 101.5, 101, 109])
    lv = levels(("high", 108, 0), ("high", 102, 2))   # older 108 replaced by newer 102
    ev = find_structure_events(c, lv, TOL)
    assert len(ev) == 1 and ev["level_price"].iloc[0] == 102.0


def test_ash_2024_example_break_fail_rebreak():
    # 3 May 2024 high (here 100), known from detection: break 23 May (bar 2),
    # close back below 99 on 4 Jun (bar 3), re-break 6 Jun (bar 5) = label only
    c = candles([98, 99, 101, 97, 98, 100.5, 103])
    ev = find_structure_events(c, levels(("high", 100, 0)), TOL)
    assert len(ev) == 1 and ev["time"].iloc[0] == t(2)
    assert ev["rebreaks"].iloc[0] == 1
    assert current_structure(c, levels(("high", 100, 0)))["trend"] == "uptrend"


def test_newest_known_swing_is_the_target_gap_case():
    # Fri 9 Oct 2026: two highs known (105 older, 103 newer); a gap close at 108
    # breaks the newer one -> exactly one event, no follow-up BOS
    c = candles([100, 101, 108, 109, 110])
    ev = find_structure_events(c, levels(("high", 105, 0), ("high", 103, 1)), TOL)
    assert len(ev) == 1 and ev["level_price"].iloc[0] == 103.0


def test_broken_level_used_up_rebreak_is_label_only():
    # break 100 down, fail back above 101, break down again
    c = candles([105, 98, 102, 97, 96])
    ev = find_structure_events(c, levels(("low", 100, 0)), TOL)
    assert len(ev) == 1                       # one event per level
    r = ev.iloc[0]
    assert r["event"] == "CHoCH" and r["trend_after"] == "downtrend"
    assert r["rebreaks"] == 1                 # the second break is a label


def test_failure_does_not_flip_trend():
    c = candles([100, 106, 99, 98])           # break up, then close back below 99
    ev = find_structure_events(c, levels(("high", 105, 0)), TOL)
    st = current_structure(c, levels(("high", 105, 0)))
    assert ev["outcome"].iloc[0] == "failed"
    assert st["trend"] == "uptrend"              # only a CHoCH flips the trend


def test_current_structure_targets():
    c = candles([100, 101, 102])
    st = current_structure(c, levels(("high", 105, 0), ("low", 95, 0)))
    assert st == {"trend": "neutral", "up_target": 105.0, "down_target": 95.0}
    c2 = candles([100, 106, 107])
    st2 = current_structure(c2, levels(("high", 105, 0), ("low", 95, 0)))
    assert st2["trend"] == "uptrend" and st2["up_target"] is None and st2["down_target"] == 95.0


def test_timezone_aware():
    c = candles([100, 101, 106])
    c["time"] = c["time"].dt.tz_localize("Asia/Kolkata")
    lv = levels(("high", 105, 0))
    lv["active_from"] = lv["active_from"].dt.tz_localize("Asia/Kolkata")
    ev = find_structure_events(c, lv, TOL)
    assert ev["time"].iloc[0] == t(2).tz_localize("Asia/Kolkata")


def test_no_events_and_bad_input():
    assert find_structure_events(candles([100, 101]), levels(("high", 200, 0)), TOL).empty
    with pytest.raises(ValueError):
        find_structure_events(candles([100]).drop(columns="close"), levels(("high", 1, 0)), TOL)
    with pytest.raises(ValueError):
        find_structure_events(candles([100]), levels(("high", 1, 0)).drop(columns="active_from"), TOL)


if __name__ == "__main__":
    from datetime import datetime

    class _Tee:
        def __init__(self, *streams):
            self.streams = streams

        def write(self, text):
            for s in self.streams:
                s.write(text)

        def flush(self):
            for s in self.streams:
                s.flush()

        def isatty(self):
            return False

    log_dir = Path(__file__).resolve().parents[4] / "logs" / "market_structure_test_logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "structure_events_unit_tests.log"
    with open(log_path, "w", encoding="utf-8") as log_file:
        real_stdout = sys.stdout
        sys.stdout = _Tee(real_stdout, log_file)
        try:
            print(f"Structure events unit tests, run at {datetime.now():%Y-%m-%d %H:%M:%S}")
            exit_code = pytest.main([__file__, "-v", "-p", "no:cacheprovider"])
            print(f"Log saved to: {log_path}")
        finally:
            sys.stdout = real_stdout
    sys.exit(exit_code)
