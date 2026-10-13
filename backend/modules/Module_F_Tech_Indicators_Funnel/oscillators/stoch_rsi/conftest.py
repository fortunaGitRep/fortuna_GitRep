"""
modules/Module_F_Tech_Indicators_Funnel/oscillators/stoch_rsi/conftest.py

Writes the Stochastic RSI test results to
logs/stoch_rsi_test_logs/test_stoch_rsi.log (overwritten each run) as
well as the normal pytest screen output -- so a test run never has to be
copy-pasted from the terminal. Loaded by pytest automatically for tests in this
folder; no change to how the tests are run:

    python -m pytest modules/Module_F_Tech_Indicators_Funnel/oscillators/stoch_rsi -v

Each test: PASSED / FAILED / SKIPPED, plus the full failure text for failures.
"""

from __future__ import annotations

import datetime as _dt
from pathlib import Path

_LOG = Path("logs") / "stoch_rsi_test_logs" / "test_stoch_rsi.log"
_results: list = []


def pytest_runtest_logreport(report):
    # One line per test: the call phase, or setup/teardown if that is what failed.
    # Only this folder's tests (pytest calls every conftest hook for every test
    # when several folders run together).
    if "oscillators/stoch_rsi/" not in str(report.fspath).replace("\\", "/"):
        return
    if report.when == "call" or (report.when != "call" and not report.passed):
        _results.append(report)


def pytest_sessionfinish(session, exitstatus):
    _LOG.parent.mkdir(parents=True, exist_ok=True)
    counts: dict[str, int] = {}
    lines = [f"Stoch RSI tests — {_dt.datetime.now():%Y-%m-%d %H:%M:%S}", "=" * 78]
    for r in _results:
        outcome = r.outcome.upper()
        counts[outcome] = counts.get(outcome, 0) + 1
        lines.append(f"{outcome:<8} {r.nodeid}")
        if r.failed:
            lines += ["-" * 78, r.longreprtext, "-" * 78]
    lines += ["=" * 78,
              "summary: " + (", ".join(f"{n} {k.lower()}" for k, n in sorted(counts.items()))
                             or "no tests ran"),
              f"exit status: {int(exitstatus)}"]
    _LOG.write_text("\n".join(lines) + "\n", encoding="utf-8")
