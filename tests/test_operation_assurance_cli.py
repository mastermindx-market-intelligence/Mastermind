"""tests.test_operation_assurance_cli — OLS-A1 report-only CLI contract.

Real subprocess invocations over both a file path and stdin, per the exit
contract in the core plan Section 6/Task 7:

    0   valid report, including UNSAFE_COUNTEREXAMPLE / BOUNDED_NO_COUNTEREXAMPLE
        / INCONCLUSIVE_MODEL_GAP;
    2   malformed JSON or a refused closed model;
    3   internal checker/report refusal.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from tests.operation_assurance_fixture_lib import clone, dumps, effect, guard, minimal_model, transition

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "operation_assurance.py"


def _run_cli(args: list[str], stdin_text: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(CLI), *args],
        input=stdin_text,
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        timeout=30,
    )


def test_cli_valid_model_from_file_exits_zero(tmp_path) -> None:
    model_path = tmp_path / "model.json"
    model_path.write_text(dumps(minimal_model()))
    proc = _run_cli([str(model_path)])
    assert proc.returncode == 0, proc.stderr
    report = json.loads(proc.stdout)
    assert report["model_analysis_verdict"] == "PROVEN_WITHIN_FINITE_MODEL"
    assert report["schema"] == "mastermind.operation_assurance_report.v1"


def test_cli_valid_model_from_stdin_exits_zero() -> None:
    proc = _run_cli(["-"], stdin_text=dumps(minimal_model()))
    assert proc.returncode == 0, proc.stderr
    report = json.loads(proc.stdout)
    assert report["model_analysis_verdict"] == "PROVEN_WITHIN_FINITE_MODEL"


def test_cli_unsafe_model_still_exits_zero() -> None:
    d = clone(minimal_model())
    d["transitions"].append(
        transition("reopen", [guard("phase", "EQ", "DONE")], [effect("phase", "START")])
    )
    proc = _run_cli(["-"], stdin_text=dumps(d))
    assert proc.returncode == 0, proc.stderr
    report = json.loads(proc.stdout)
    assert report["model_analysis_verdict"] == "UNSAFE_COUNTEREXAMPLE"


def test_cli_invalid_json_exits_two() -> None:
    proc = _run_cli(["-"], stdin_text="{not valid json")
    assert proc.returncode == 2
    assert proc.stdout == ""
    assert proc.stderr.strip() != ""
    assert "Traceback" not in proc.stderr
    assert str(ROOT) not in proc.stderr


def test_cli_refused_model_exits_two() -> None:
    d = clone(minimal_model())
    del d["abstraction_contract"]
    proc = _run_cli(["-"], stdin_text=dumps(d))
    assert proc.returncode == 2
    assert proc.stdout == ""
    assert "Traceback" not in proc.stderr


def test_cli_missing_file_exits_two_without_leaking_path() -> None:
    proc = _run_cli(["/nonexistent/path/does-not-exist.json"])
    assert proc.returncode == 2
    assert "/nonexistent/path/does-not-exist.json" not in proc.stderr


def test_cli_wrong_arg_count_exits_two() -> None:
    proc = _run_cli([])
    assert proc.returncode == 2
    proc2 = _run_cli(["a.json", "b.json"])
    assert proc2.returncode == 2


def test_cli_pretty_flag_produces_indented_json() -> None:
    proc = _run_cli(["-", "--pretty"], stdin_text=dumps(minimal_model()))
    assert proc.returncode == 0
    assert proc.stdout.startswith("{\n")
    assert json.loads(proc.stdout)["schema"] == "mastermind.operation_assurance_report.v1"


def test_cli_output_is_byte_stable_across_runs() -> None:
    text = dumps(minimal_model())
    proc1 = _run_cli(["-"], stdin_text=text)
    proc2 = _run_cli(["-"], stdin_text=text)
    r1 = json.loads(proc1.stdout)
    r2 = json.loads(proc2.stdout)
    r1.pop("generated_at")
    r2.pop("generated_at")
    r1.pop("report_id")
    r2.pop("report_id")
    r1.pop("report_hash")
    r2.pop("report_hash")
    assert r1 == r2


def test_cli_no_trusted_source_flag_exists() -> None:
    proc = _run_cli(["--trusted-source", "-"], stdin_text=dumps(minimal_model()))
    # unknown flag is treated as a positional -> wrong arg count -> exit 2,
    # never accepted as a trust escalation switch.
    assert proc.returncode == 2


def test_cli_never_writes_any_file(tmp_path) -> None:
    model_path = tmp_path / "model.json"
    model_path.write_text(dumps(minimal_model()))
    before = sorted(p.name for p in tmp_path.iterdir())
    _run_cli([str(model_path)])
    after = sorted(p.name for p in tmp_path.iterdir())
    assert before == after
