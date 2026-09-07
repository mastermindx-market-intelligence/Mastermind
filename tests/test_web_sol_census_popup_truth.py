"""Fail-closed pytest entrypoint for the actual-checkout popup regression suite."""
from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
NODE_TEST = ROOT / "tests" / "web_sol_census_popup_truth.test.cjs"
EXPECTED_NODE_CASES = 20
NODE_TIMEOUT_SECONDS = 20
MAX_TAP_BYTES = 128 * 1024


def _assert_node_result(result: subprocess.CompletedProcess[str]) -> None:
    """Require a complete flat suite, not merely a zero child exit status."""
    assert result.returncode == 0, "popup Node suite returned nonzero"
    assert isinstance(result.stdout, str) and isinstance(result.stderr, str)
    assert not result.stderr, "popup Node suite emitted unexpected stderr"
    output = result.stdout
    assert len(output.encode("utf-8")) <= MAX_TAP_BYTES, "popup TAP output exceeds limit"
    assert output.startswith("TAP version 13\n"), "popup TAP header is missing"
    assert len(re.findall(r"^TAP version 13$", output, re.MULTILINE)) == 1
    plans = re.findall(r"^1\.\.([0-9]+)$", output, re.MULTILINE)
    assert plans == [str(EXPECTED_NODE_CASES)], "popup test plan is missing, duplicate, or incomplete"
    expected = {"tests": EXPECTED_NODE_CASES, "suites": 0, "pass": EXPECTED_NODE_CASES,
                "fail": 0, "cancelled": 0, "skipped": 0, "todo": 0}
    for field, count in expected.items():
        values = re.findall(rf"^# {field} ([0-9]+)$", output, re.MULTILINE)
        assert values == [str(count)], f"popup TAP {field} summary is not exact"
    cases = re.findall(r"^(ok|not ok) ([1-9][0-9]*) - (.+)$", output, re.MULTILINE)
    assert len(cases) == EXPECTED_NODE_CASES, "popup case results are incomplete"
    assert [int(number) for _, number, _ in cases] == list(range(1, EXPECTED_NODE_CASES + 1))
    assert all(state == "ok" for state, _, _ in cases), "popup has a failing case"
    assert all(re.search(r"\s+#\s*(?:SKIP|TODO)\b", label, re.IGNORECASE) is None
               for _, _, label in cases), "popup contains a skipped or todo case"
    assert re.search(r"^Bail out!", output, re.MULTILINE) is None, "popup suite bailed out"


def _run_popup_suite() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.fail("Node.js is required for popup truth coverage; skipping is forbidden", pytrace=False)
    assert NODE_TEST.is_file(), "actual-checkout popup Node test is missing"
    environment = dict(os.environ)
    # Do not inherit module injection or test-filter flags from the parent environment.
    environment.pop("NODE_OPTIONS", None)
    environment.pop("NODE_PATH", None)
    try:
        result = subprocess.run(
            [node, "--test", "--test-reporter=tap", str(NODE_TEST)],
            cwd=ROOT, env=environment, capture_output=True, encoding="utf-8",
            timeout=NODE_TIMEOUT_SECONDS, check=False,
        )
    except (OSError, subprocess.TimeoutExpired, UnicodeError):
        pytest.fail("popup Node suite did not complete within its execution contract", pytrace=False)
    _assert_node_result(result)


def _good_tap() -> str:
    cases = "\n".join(f"ok {number} - case {number}" for number in range(1, 21))
    return (
        f"TAP version 13\n{cases}\n1..20\n# tests 20\n# suites 0\n"
        "# pass 20\n# fail 0\n# cancelled 0\n# skipped 0\n# todo 0\n"
    )


def _completed(stdout: str, *, returncode: int = 0, stderr: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(["node"], returncode, stdout, stderr)



def test_node_receipt_accepts_complete_twenty_case_success() -> None:
    _assert_node_result(_completed(_good_tap()))


@pytest.mark.parametrize("invalid", [
    _completed(_good_tap(), returncode=1),
    _completed(_good_tap(), returncode=-9),
    _completed(""),
    _completed("TAP version 13\n1..0\n# tests 0\n# suites 0\n# pass 0\n# fail 0\n# cancelled 0\n# skipped 0\n# todo 0\n"),
    _completed(_good_tap().replace("# tests 20\n", "")),
    _completed(_good_tap() + "# tests 20\n"),
    _completed(_good_tap().replace("# pass 20", "# pass 19")),
    _completed(_good_tap().replace("# fail 0", "# fail 1")),
    _completed(_good_tap().replace("# cancelled 0", "# cancelled 1")),
    _completed(_good_tap().replace("# skipped 0", "# skipped 1")),
    _completed(_good_tap().replace("# todo 0", "# todo 1")),
    _completed(_good_tap().replace("# suites 0", "# suites 1")),
    _completed(_good_tap().replace("1..20", "1..19")),
    _completed(_good_tap() + "1..20\n"),
    _completed(_good_tap().replace("ok 20 - case 20\n", "")),
    _completed(_good_tap().replace("ok 20 - case 20", "ok 19 - duplicate")),
    _completed(_good_tap().replace("ok 1 - case 1\n", "not ok 1 - case 1\n")),
    _completed(_good_tap().replace("ok 1 - case 1\n", "ok 1 - case 1 # SKIP\n")),
    _completed(_good_tap().replace("ok 1 - case 1\n", "ok 1 - case 1 # TODO\n")),
    _completed(_good_tap().replace("TAP version 13\n", "")),
    _completed(_good_tap() + "# " + ("x" * MAX_TAP_BYTES)),
    _completed(_good_tap(), stderr="unexpected diagnostic"),
], ids=["nonzero", "signal", "empty", "zero-cases", "missing-summary", "duplicate-summary",
        "partial-pass", "failure", "cancelled", "skipped", "todo", "unexpected-suite",
        "wrong-plan", "duplicate-plan", "missing-case", "duplicate-case-number", "not-ok",
        "skip-directive", "todo-directive", "missing-header", "oversized", "stderr"])
def test_node_receipt_refuses_incomplete_or_false_green_result(invalid: subprocess.CompletedProcess[str]) -> None:
    with pytest.raises(AssertionError):
        _assert_node_result(invalid)



def test_popup_truth_actual_checkout_node_suite() -> None:
    _run_popup_suite()


def test_popup_wrapper_requires_node_instead_of_skipping(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda _name: None)
    with pytest.raises(pytest.fail.Exception, match="Node.js is required"):
        _run_popup_suite()


@pytest.mark.parametrize("error", [
    subprocess.TimeoutExpired(["node"], NODE_TIMEOUT_SECONDS),
    OSError("synthetic startup failure"),
    UnicodeError("synthetic output failure"),
], ids=["timeout", "startup", "encoding"])
def test_popup_wrapper_fails_closed_on_execution_error(monkeypatch: pytest.MonkeyPatch, error: Exception) -> None:
    monkeypatch.setattr(shutil, "which", lambda _name: "/synthetic/node")
    def fail(*_args: object, **_kwargs: object) -> None:
        raise error
    monkeypatch.setattr(subprocess, "run", fail)
    with pytest.raises(pytest.fail.Exception, match="popup Node suite did not complete"):
        _run_popup_suite()


def test_popup_wrapper_uses_fixed_checkout_and_finite_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    recorded: dict[str, object] = {}
    monkeypatch.setattr(shutil, "which", lambda _name: "/synthetic/node")
    monkeypatch.setenv("NODE_OPTIONS", "synthetic-untrusted-option")
    monkeypatch.setenv("NODE_PATH", "/synthetic/other-source")
    def capture(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        recorded.update(command=command, **kwargs)
        return _completed(_good_tap())
    monkeypatch.setattr(subprocess, "run", capture)
    _run_popup_suite()
    assert recorded["command"] == ["/synthetic/node", "--test", "--test-reporter=tap", str(NODE_TEST)]
    assert recorded["cwd"] == ROOT
    assert recorded["timeout"] == NODE_TIMEOUT_SECONDS
    assert recorded["capture_output"] is True
    assert recorded["encoding"] == "utf-8"
    assert recorded["check"] is False
    assert "shell" not in recorded
    environment = recorded["env"]
    assert isinstance(environment, dict)
    assert "NODE_OPTIONS" not in environment and "NODE_PATH" not in environment
