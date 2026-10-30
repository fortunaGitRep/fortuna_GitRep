"""Write pytest results for this folder to logs/options_sample_days_logs/test_sample_days.log."""
from pathlib import Path

_LOG = Path("logs") / "options_sample_days_logs" / "test_sample_days.log"
_lines: list[str] = []


def pytest_runtest_logreport(report):
    if report.when == "call" or (report.when == "setup" and report.outcome != "passed"):
        _lines.append(f"{report.outcome.upper():<7} {report.nodeid}")
        if report.outcome == "failed":
            _lines.append(str(report.longrepr))


def pytest_sessionfinish(session, exitstatus):
    _LOG.parent.mkdir(parents=True, exist_ok=True)
    passed = sum(l.startswith("PASSED") for l in _lines)
    _LOG.write_text("\n".join(_lines + [f"\n{passed} passed, exit status {int(exitstatus)}"]), encoding="utf-8")
