"""tests.test_operation_assurance_a2_cli — OLS-A2 bounded compile CLI.

Exit contract (design Section 2 + control_plane.operation_assurance CLI
pattern): 0 valid output, 2 malformed input/refusal, 3 internal refusal.
scripts/operation_assurance_compile.py performs no write other than
stdout/stderr.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.operation_assurance_compile import main  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures" / "operation_assurance_a2"
REV = "a3f6ef40d41e6d308c8d8cdc35f76802cd0525e4"


def _run(args, capsys):
    code = main(args)
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def test_gather_and_compile_mode_exits_zero_with_a_model_bundle(capsys):
    code, out, err = _run(
        [
            "--repo-root",
            str(FIXTURES / "hostile"),
            "--repo",
            "mastermindx-market-intelligence/macro",
            "--revision",
            REV,
            "--observed-at",
            "2026-09-02T00:00:00Z",
        ],
        capsys,
    )
    assert code == 0, err
    doc = json.loads(out)
    assert doc["schema"] == "mastermind.operation_assurance_model.v1"
    assert doc["abstraction_contract"]["kind"] == "SOUND_OVERAPPROXIMATION"


def test_missing_arguments_exit_two(capsys):
    code, out, err = _run(["--repo-root", str(FIXTURES / "hostile")], capsys)
    assert code == 2
    assert "usage" in err.lower() or "missing" in err.lower()


def test_both_modes_at_once_exit_two(capsys, tmp_path):
    facts_path = tmp_path / "facts.json"
    facts_path.write_text("{}")
    code, out, err = _run(
        [
            "--repo-root",
            str(FIXTURES / "hostile"),
            "--repo",
            "r",
            "--revision",
            REV,
            "--observed-at",
            "2026-09-02T00:00:00Z",
            "--from-facts",
            str(facts_path),
        ],
        capsys,
    )
    assert code == 2


def test_abbreviated_revision_exits_two_not_three(capsys):
    code, out, err = _run(
        [
            "--repo-root",
            str(FIXTURES / "hostile"),
            "--repo",
            "r",
            "--revision",
            REV[:10],
            "--observed-at",
            "2026-09-02T00:00:00Z",
        ],
        capsys,
    )
    assert code == 2
    assert "INVALID_SOURCE_BUNDLE" in err


def test_missing_target_exits_two_with_source_missing(capsys):
    code, out, err = _run(
        [
            "--repo-root",
            str(FIXTURES / "missing"),
            "--repo",
            "r",
            "--revision",
            REV,
            "--observed-at",
            "2026-09-02T00:00:00Z",
        ],
        capsys,
    )
    assert code == 2
    assert "SOURCE_MISSING" in err


def test_conflicted_target_exits_two_with_source_conflicted(capsys):
    code, out, err = _run(
        [
            "--repo-root",
            str(FIXTURES / "conflict"),
            "--repo",
            "r",
            "--revision",
            REV,
            "--observed-at",
            "2026-09-02T00:00:00Z",
        ],
        capsys,
    )
    assert code == 2
    assert "SOURCE_CONFLICTED" in err


def test_from_facts_file_mode_round_trips(capsys, tmp_path):
    import sys as _sys

    sys_path_root = str(ROOT)
    if sys_path_root not in _sys.path:
        _sys.path.insert(0, sys_path_root)
    from control_plane.operation_assurance_sources import gather_agent_os_source_facts

    facts = gather_agent_os_source_facts(
        FIXTURES / "hostile",
        repo="mastermindx-market-intelligence/macro",
        revision=REV,
        observed_at="2026-09-02T00:00:00Z",
    )
    facts_path = tmp_path / "facts.json"
    facts_path.write_text(json.dumps(facts.to_dict()))
    code, out, err = _run(["--from-facts", str(facts_path)], capsys)
    assert code == 0, err
    doc = json.loads(out)
    assert doc["schema"] == "mastermind.operation_assurance_model.v1"


def test_from_facts_malformed_json_exits_two(capsys, tmp_path):
    facts_path = tmp_path / "facts.json"
    facts_path.write_text("{not valid json")
    code, out, err = _run(["--from-facts", str(facts_path)], capsys)
    assert code == 2
    assert "MALFORMED_JSON" in err


def test_from_facts_missing_file_exits_two(capsys, tmp_path):
    code, out, err = _run(["--from-facts", str(tmp_path / "nope.json")], capsys)
    assert code == 2
    assert "INPUT_READ_ERROR" in err


def test_pretty_flag_indents_output(capsys):
    code, out, err = _run(
        [
            "--repo-root",
            str(FIXTURES / "hostile"),
            "--repo",
            "r",
            "--revision",
            REV,
            "--observed-at",
            "2026-09-02T00:00:00Z",
            "--pretty",
        ],
        capsys,
    )
    assert code == 0
    assert "\n  " in out


@pytest.mark.parametrize("target_key", ["OPERATION-ASSURANCE"])
def test_gather_mode_output_is_deterministic_across_two_runs(capsys, target_key):
    args = [
        "--repo-root",
        str(FIXTURES / "hostile"),
        "--repo",
        "mastermindx-market-intelligence/macro",
        "--revision",
        REV,
        "--observed-at",
        "2026-09-02T00:00:00Z",
        "--target-key",
        target_key,
    ]
    code1, out1, _ = _run(args, capsys)
    code2, out2, _ = _run(args, capsys)
    assert code1 == code2 == 0
    assert out1 == out2
