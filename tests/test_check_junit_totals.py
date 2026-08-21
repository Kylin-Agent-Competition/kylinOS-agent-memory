import importlib.util
from pathlib import Path


_HELPER = Path(__file__).resolve().parents[1] / "scripts" / "check_junit_totals.py"
_SPEC = importlib.util.spec_from_file_location("check_junit_totals", _HELPER)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)


def test_summarize_counts_nested_pytest_testsuites(tmp_path):
    junit = tmp_path / "pytest.xml"
    junit.write_text(
        """<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite name="pytest" tests="4" failures="1" errors="1" skipped="1">
    <testcase classname="a" name="passed" />
    <testcase classname="a" name="failed"><failure /></testcase>
    <testcase classname="a" name="error"><error /></testcase>
    <testcase classname="a" name="skipped"><skipped /></testcase>
  </testsuite>
</testsuites>
""",
        encoding="utf-8",
    )

    assert _MODULE.summarize([junit]) == {
        "tests": 4,
        "failures": 1,
        "errors": 1,
        "skipped": 1,
    }


def test_summarize_combines_files_without_counting_suite_aggregates(tmp_path):
    first = tmp_path / "first.xml"
    second = tmp_path / "second.xml"
    first.write_text(
        "<testsuites><testsuite tests='1'><testcase name='one'/></testsuite></testsuites>",
        encoding="utf-8",
    )
    second.write_text(
        "<testsuite tests='2'><testcase name='two'/><testcase name='three'/></testsuite>",
        encoding="utf-8",
    )

    assert _MODULE.summarize([first, second]) == {
        "tests": 3,
        "failures": 0,
        "errors": 0,
        "skipped": 0,
    }
