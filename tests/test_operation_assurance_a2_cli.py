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
    # REPAIR B1: --from-facts now goes through the one closed-wire ingest
    # entry point (SourceFacts.from_json_bytes), whose refusal code family
    # is INVALID_SOURCE_BUNDLE rather than an ad hoc CLI-local code.
    assert "INVALID_SOURCE_BUNDLE" in err
    assert "malformed JSON" in err


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


# ---------------------------------------------------------------------------
# REPAIR R2 (Sol CONTINUE): --from-facts + --repo-root re-verification mode.
# ---------------------------------------------------------------------------


def test_r2_from_facts_alone_forged_git_head_verified_downgrades_and_carries_the_gap(capsys, tmp_path):
    import json

    from control_plane.operation_assurance_sources import gather_agent_os_source_facts

    facts = gather_agent_os_source_facts(
        FIXTURES / "hostile", repo="mastermindx-market-intelligence/macro", revision=REV, observed_at="2026-09-02T00:00:00Z"
    )
    doc = facts.to_dict()
    doc["revision_binding"] = "GIT_HEAD_VERIFIED"  # forged
    facts_path = tmp_path / "facts.json"
    facts_path.write_text(json.dumps(doc))

    code, out, err = _run(["--from-facts", str(facts_path)], capsys)
    assert code == 0, err
    model_doc = json.loads(out)
    gap_ids = {g["gap_id"] for g in model_doc["known_model_gaps"] if g["load_bearing"]}
    assert "source_attestation_unavailable" in gap_ids


def test_r2_from_facts_with_matching_repo_root_reestablishes_and_drops_the_gap(capsys, tmp_path):
    import json
    import shutil

    from control_plane.operation_assurance_sources import gather_agent_os_source_facts

    dest = tmp_path / "checkout"
    shutil.copytree(FIXTURES / "hostile", dest)
    sha = "f7" + "0" * 38
    (dest / ".git").mkdir()
    (dest / ".git" / "HEAD").write_text(sha + "\n", encoding="utf-8")

    facts = gather_agent_os_source_facts(dest, repo="r", revision=sha, observed_at="2026-09-02T00:00:00Z")
    doc = facts.to_dict()
    doc["revision_binding"] = "CALLER_ASSERTED_UNVERIFIED"  # honest serialization
    facts_path = tmp_path / "facts.json"
    facts_path.write_text(json.dumps(doc))

    code, out, err = _run(["--from-facts", str(facts_path), "--repo-root", str(dest)], capsys)
    assert code == 0, err
    model_doc = json.loads(out)
    gap_ids = {g["gap_id"] for g in model_doc["known_model_gaps"] if g["load_bearing"]}
    assert "source_attestation_unavailable" not in gap_ids


def test_r2_from_facts_with_mismatched_repo_root_refuses(capsys, tmp_path):
    import json

    from control_plane.operation_assurance_sources import gather_agent_os_source_facts

    facts = gather_agent_os_source_facts(
        FIXTURES / "hostile", repo="r", revision="1" + "1" * 39, observed_at="2026-09-02T00:00:00Z"
    )
    doc = facts.to_dict()
    facts_path = tmp_path / "facts.json"
    facts_path.write_text(json.dumps(doc))

    real_checkout = tmp_path / "checkout"
    real_checkout.mkdir()
    (real_checkout / ".git").mkdir()
    (real_checkout / ".git" / "HEAD").write_text(("2" * 40) + "\n", encoding="utf-8")

    code, out, err = _run(["--from-facts", str(facts_path), "--repo-root", str(real_checkout)], capsys)
    assert code == 2
    assert "REVISION_MISMATCH" in err


def test_r2_repo_root_with_other_gather_flags_and_from_facts_is_usage_error(capsys, tmp_path):
    facts_path = tmp_path / "facts.json"
    facts_path.write_text("{}")
    code, out, err = _run(["--from-facts", str(facts_path), "--repo", "r"], capsys)
    assert code == 2
    assert "usage" in err.lower()
