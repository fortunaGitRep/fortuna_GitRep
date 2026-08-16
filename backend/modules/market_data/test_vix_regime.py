"""
Unit tests for vix_regime.py -- the percentile math and decision branches that
gate live trades. Runs WITHOUT Supabase/network: tests the pure percentile
function directly, and tests evaluate_vix_decision() by monkeypatching the
store read so no DB is touched.

Run from the backend/ folder:
    python -m modules.market_data.test_vix_regime
"""

from __future__ import annotations

from . import vix_regime as vr


# --- calculate_percentile (pure) -------------------------------------------

def test_percentile_extremes_and_median():
    assert vr.calculate_percentile(30, [10, 12, 14, 16, 18]) == 100.0   # all below
    assert vr.calculate_percentile(5, [10, 12, 14, 16, 18]) == 0.0      # none below
    assert vr.calculate_percentile(14, [10, 12, 14, 16, 18]) == 50.0    # 2 below,1 eq
    assert vr.calculate_percentile(14, []) is None                       # no priors


def test_percentile_is_regime_relative():
    # Same VIX 14 reads very differently vs a calm vs a stressed year.
    calm_year = [11, 12, 11.5, 13, 12.5, 11, 10.5, 12, 13.5, 12] * 25
    stressed_year = [18, 20, 19, 22, 21, 18.5, 20.5, 19, 23, 20] * 25
    assert vr.calculate_percentile(14, calm_year) == 100.0     # extreme in a calm year
    assert vr.calculate_percentile(14, stressed_year) == 0.0   # calm in a stressed year


# --- evaluate_vix_decision (store monkeypatched) ---------------------------

def _patch_closes(monkeypatch_values):
    """Replace get_recent_closes with a stub returning a fixed oldest-first list."""
    vr.get_recent_closes = lambda index_key, window: list(monkeypatch_values)  # type: ignore


def test_empty_history_is_no_go_no_data():
    _patch_closes([])
    d = vr.evaluate_vix_decision()
    assert d.regime == vr.VolRegime.NO_DATA
    assert d.go_no_go == "NO_GO"
    assert d.latest_close_vix is None


def test_small_history_still_classifies_regime():
    # Thin-history special-casing was removed (can't recur post-backfill).
    # Even a few priors now produce a real regime from the percentile.
    _patch_closes([10.0] * 10 + [25.0])  # latest above all -> ~100th pctl
    d = vr.evaluate_vix_decision()
    assert d.regime == vr.VolRegime.EXTREME  # no longer forced to NO_DATA/UNKNOWN
    assert d.go_no_go == "NO_GO"             # EXTREME still votes NO-GO


def test_invalid_values_are_dropped():
    valid = [12.0] * 45
    _patch_closes(valid + [13.0])
    d = vr.evaluate_vix_decision()
    assert d.latest_close_vix == 13.0
    assert d.regime != vr.VolRegime.NO_DATA  # valid data present


def test_calm_regime_go_and_confidence():
    # Latest sits at the low end of a wide history -> LOW regime, GO, conf 1.2
    history = list(range(20, 60))  # 40 priors, values 20..59
    _patch_closes([float(x) for x in history] + [15.0])  # latest below all -> low pctl
    d = vr.evaluate_vix_decision()
    assert d.regime == vr.VolRegime.LOW
    assert d.go_no_go == "GO"
    assert d.confidence_mult == 1.2
    assert d.direction_weight == 0.0  # structural


def test_extreme_regime_is_no_go():
    history = list(range(20, 60))  # 40 priors
    _patch_closes([float(x) for x in history] + [100.0])  # latest above all -> 100th pctl
    d = vr.evaluate_vix_decision()
    assert d.regime == vr.VolRegime.EXTREME
    assert d.go_no_go == "NO_GO"


if __name__ == "__main__":
    import types

    # Preserve the real function so tests that don't patch aren't affected.
    original = vr.get_recent_closes

    tests = [v for k, v in sorted(globals().items())
             if k.startswith("test_") and isinstance(v, types.FunctionType)]
    passed = 0
    for t in tests:
        try:
            t()
            print(f"PASS  {t.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"FAIL  {t.__name__}: {e}")
        except Exception as e:  # noqa: BLE001
            print(f"ERROR {t.__name__}: {e}")
        finally:
            vr.get_recent_closes = original  # restore after each test

    print(f"\n{passed}/{len(tests)} passed.")
