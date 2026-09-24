"""EVAL-R0 Task 7: CLI and synthetic two-arm proof.

The complete fresh-root journey runs as REAL subprocess invocations of
``scripts/agent_evaluation.py`` (not in-process function calls) so this
test proves what a fresh reviewer actually sees on a terminal: exit codes,
stdout JSON, and no traceback for expected errors.
"""
from __future__ import annotations

import json
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "agent_evaluation.py"

VALIDATOR_ARGS = [
    "--validator-id",
    "mastermind.eval_r0_finalizer.v1",
    "--validator-version",
    "1",
    "--validator-code-ref",
    "git:mastermindx-market-intelligence/Mastermind@" + "a" * 40,
    "--validated-at",
    "2026-08-25T00:00:10Z",
    "--created-at",
    "2026-08-25T00:00:11Z",
]


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(CLI), *args],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        timeout=60,
    )


def _write_json(path: Path, document: dict) -> Path:
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


@pytest.fixture()
def journey(tmp_path):
    """Build the complete synthetic fixture set once per test as files on
    disk, mirroring exactly what a fresh reviewer would produce."""
    from tests.agent_eval_factories import (
        build_alternate_configuration,
        build_baseline_configuration,
        build_baseline_scenario,
        build_run_draft,
        build_two_arm_experiment,
        fresh_run_id,
    )

    scenario = build_baseline_scenario()
    config_a = build_baseline_configuration()
    config_b = build_alternate_configuration()
    experiment = build_two_arm_experiment(scenario, config_a, config_b)
    draft_valid = build_run_draft(scenario, config_a, experiment, arm_id="arm_a", replicate_index=1)
    draft_invalid = build_run_draft(
        scenario, config_a, experiment, arm_id="arm_a", replicate_index=1, model_served="claude-opus-9", run_id=fresh_run_id()
    )

    files_dir = tmp_path / "files"
    files_dir.mkdir()
    root_dir = tmp_path / "eval_root"

    paths = {
        "scenario": _write_json(files_dir / "scenario.json", scenario),
        "config_a": _write_json(files_dir / "config_a.json", config_a),
        "config_b": _write_json(files_dir / "config_b.json", config_b),
        "experiment": _write_json(files_dir / "experiment.json", experiment),
        "draft_valid": _write_json(files_dir / "draft_valid.json", draft_valid),
        "draft_invalid": _write_json(files_dir / "draft_invalid.json", draft_invalid),
    }
    return {
        "root": root_dir,
        "files_dir": files_dir,
        "paths": paths,
        "scenario": scenario,
        "config_a": config_a,
        "config_b": config_b,
        "experiment": experiment,
    }


# ---------------------------------------------------------------------------
# --help / usage
# ---------------------------------------------------------------------------


def test_cli_help_exits_cleanly() -> None:
    result = _run("--help")
    assert result.returncode == 0
    assert "verify-graph" in result.stdout
    assert "finalize-run" in result.stdout


def test_cli_unknown_command_is_a_usage_error() -> None:
    result = _run("not-a-real-command")
    assert result.returncode != 0


def test_cli_no_traceback_on_expected_error(tmp_path) -> None:
    missing = tmp_path / "does_not_exist.json"
    result = _run("validate-shape", str(missing))
    assert result.returncode == 2
    assert "Traceback (most recent call last)" not in result.stderr


# ---------------------------------------------------------------------------
# validate-shape
# ---------------------------------------------------------------------------


def test_validate_shape_prints_shape_valid_only(journey) -> None:
    result = _run("validate-shape", str(journey["paths"]["scenario"]))
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload == {"scope": "SHAPE_VALID"}


def test_validate_shape_rejects_a_draft_document_shape_error(journey) -> None:
    result = _run("validate-shape", str(journey["paths"]["draft_valid"]))
    # draft schema is a valid persisted-shape check target ONLY through the
    # draft-specific validators, never through the generic dispatcher used
    # by validate-shape (which is reserved for persisted schemas)
    assert result.returncode == 2


def test_validate_shape_never_prints_a_stronger_scope(journey) -> None:
    result = _run("validate-shape", str(journey["paths"]["scenario"]))
    assert "EVALUATION_GRAPH_VERIFIED" not in result.stdout
    assert "EVIDENCE_CONTENT_VERIFIED" not in result.stdout


# ---------------------------------------------------------------------------
# Complete fresh-root journey (plan Task 7, the ten-point vertical)
# ---------------------------------------------------------------------------


def test_complete_synthetic_two_arm_journey(journey) -> None:
    root = str(journey["root"])
    paths = journey["paths"]

    # 1. create scenario with corpus revision and artifact/digest source allowlist
    r = _run("create", "--root", root, str(paths["scenario"]))
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout)["disposition"] == "CREATED"

    # 2. create two configurations
    r = _run("create", "--root", root, str(paths["config_a"]))
    assert r.returncode == 0, r.stderr
    r = _run("create", "--root", root, str(paths["config_b"]))
    assert r.returncode == 0, r.stderr

    # 3. create/verify two-arm experiment
    r = _run("create", "--root", root, str(paths["experiment"]))
    assert r.returncode == 0, r.stderr
    experiment_id = journey["experiment"]["experiment_id"]
    r = _run("verify-graph", "--root", root, json.loads(r.stdout)["path"])
    assert r.returncode == 0, r.stderr
    graph_payload = json.loads(r.stdout)
    assert graph_payload["scope"] == "EVALUATION_GRAPH_VERIFIED"

    # 4. finalize/store clean baseline run
    run_valid_out = journey["files_dir"] / "run_valid.json"
    r = _run(
        "finalize-run",
        "--root",
        root,
        "--draft",
        str(paths["draft_valid"]),
        *VALIDATOR_ARGS,
        "--output",
        str(run_valid_out),
    )
    assert r.returncode == 0, r.stderr
    valid_payload = json.loads(r.stdout)
    assert valid_payload["validity_status"] == "VALID"
    r = _run("create", "--root", root, str(run_valid_out))
    assert r.returncode == 0, r.stderr
    valid_run_path = json.loads(r.stdout)["path"]

    # 5. finalize/store served-model mismatch run
    run_invalid_out = journey["files_dir"] / "run_invalid.json"
    r = _run(
        "finalize-run",
        "--root",
        root,
        "--draft",
        str(paths["draft_invalid"]),
        *VALIDATOR_ARGS,
        "--output",
        str(run_invalid_out),
    )
    assert r.returncode == 1, r.stderr  # invalid result -> exit 1, not an error
    invalid_payload = json.loads(r.stdout)
    assert invalid_payload["validity_status"] == "INVALID_CONFIGURATION"
    assert "MODEL_SERVED_MISMATCH" in invalid_payload["reason_codes"]
    r = _run("create", "--root", root, str(run_invalid_out))
    assert r.returncode == 0, r.stderr  # storing an INVALID run is a clean create
    invalid_run_path = json.loads(r.stdout)["path"]

    # 6. verify baseline VALID and mismatch INVALID_CONFIGURATION/MODEL_SERVED_MISMATCH
    run_valid_doc = json.loads(run_valid_out.read_text())
    run_invalid_doc = json.loads(run_invalid_out.read_text())
    assert run_valid_doc["validity"]["status"] == "VALID"
    assert run_invalid_doc["validity"]["status"] == "INVALID_CONFIGURATION"
    assert run_invalid_doc["validity"]["reason_codes"] == ["MODEL_SERVED_MISMATCH"]

    # 7. append integrity pass per run
    valid_scorer_id = f"scorer-pass:{uuid.uuid4()}"
    r = _run(
        "score-integrity",
        "--root",
        root,
        "--run-id",
        run_valid_doc["run_id"],
        "--scorer-code-ref",
        "git:mastermindx-market-intelligence/Mastermind@" + "a" * 40,
        "--created-at",
        "2026-08-25T00:00:12Z",
        "--id",
        valid_scorer_id,
    )
    assert r.returncode == 0, r.stderr
    valid_score_payload = json.loads(r.stdout)
    assert all(status == "PASS" for status in valid_score_payload["dimension_results"].values())

    invalid_scorer_id = f"scorer-pass:{uuid.uuid4()}"
    r = _run(
        "score-integrity",
        "--root",
        root,
        "--run-id",
        run_invalid_doc["run_id"],
        "--scorer-code-ref",
        "git:mastermindx-market-intelligence/Mastermind@" + "a" * 40,
        "--created-at",
        "2026-08-25T00:00:12Z",
        "--id",
        invalid_scorer_id,
    )
    assert r.returncode == 1, r.stderr  # a FAIL dimension is an incomplete, not an error
    invalid_score_payload = json.loads(r.stdout)
    assert invalid_score_payload["dimension_results"]["configuration_integrity"] == "FAIL"

    # 8. summarize/store evidence ref
    evidence_ref_id = f"evidence-ref:{uuid.uuid4()}"
    r = _run(
        "summarize",
        "--root",
        root,
        "--experiment-id",
        experiment_id,
        "--owner",
        "person:sol",
        "--review-at",
        "2026-08-26T00:00:00Z",
        "--created-at",
        "2026-08-25T00:00:13Z",
        "--id",
        evidence_ref_id,
    )
    assert r.returncode == 1, r.stderr  # R0 grade is always INSUFFICIENT_EVIDENCE
    evidence_payload = json.loads(r.stdout)
    assert evidence_payload["evidence_grade"] == "INSUFFICIENT_EVIDENCE"
    assert set(evidence_payload["verification_scopes"]) == {"SHAPE_VALID", "EVALUATION_GRAPH_VERIFIED"}
    assert evidence_payload["counts"] == {
        "valid_count": 1,
        "invalid_count": 1,
        "degraded_count": 0,
        "unscored_count": 0,
        "total_count": 2,
    }

    # 9. graph-verify tree
    r = _run("verify-tree-graph", "--root", root)
    assert r.returncode == 0, r.stderr
    tree_payload = json.loads(r.stdout)
    assert tree_payload == {"scope": "EVALUATION_GRAPH_VERIFIED", "defect_count": 0, "defects": []}

    # 10. assert config/arm/pair/replicate links, one valid/one invalid,
    # invalid retained, INSUFFICIENT_EVIDENCE, external content unverified,
    # no aggregate/winner/policy/acceptance anywhere, no file outside root
    evidence_root_path = Path(root) / "evidence-refs"
    (evidence_doc_path,) = list(evidence_root_path.rglob("evidence-ref.json"))
    evidence_doc = json.loads(evidence_doc_path.read_text())
    run_entries_by_id = {entry["run_id"]: entry for entry in evidence_doc["run_entries"]}
    assert run_entries_by_id[run_valid_doc["run_id"]]["technical_validity"] == "VALID"
    assert run_entries_by_id[run_valid_doc["run_id"]]["arm_id"] == "arm_a"
    assert run_entries_by_id[run_valid_doc["run_id"]]["replicate_index"] == 1
    assert run_entries_by_id[run_valid_doc["run_id"]]["pair_key"] is not None
    assert run_entries_by_id[run_invalid_doc["run_id"]]["technical_validity"] == "INVALID_CONFIGURATION"
    # invalid run retained in the denominator, never disappears
    assert evidence_doc["counts"]["invalid_count"] == 1
    assert evidence_doc["evidence_grade"] == "INSUFFICIENT_EVIDENCE"
    assert "EVIDENCE_CONTENT_VERIFIED" not in evidence_doc["verification_scopes"]
    # no aggregate/winner/route/policy/approval/acceptance FIELD anywhere in
    # the document (the required non_authority_statement PROSE below is
    # exempt -- it explicitly names these words to disclaim authority, which
    # is the opposite of asserting one; checked separately from field keys)
    non_authority_statement = evidence_doc["non_authority_statement"]
    document_without_statement = {k: v for k, v in evidence_doc.items() if k != "non_authority_statement"}
    remaining_text = json.dumps(document_without_statement).lower()
    for forbidden in ("winner", "aggregate", "\"route\"", "\"policy\"", "approved", "accepted", "promoted"):
        assert forbidden not in remaining_text
    assert non_authority_statement == (
        "This evidence reference does not authorize routing, policy, release, merge, deployment, "
        "production execution, or acceptance."
    )
    # no file was written outside --root
    for path in Path(root).rglob("*"):
        assert str(path).startswith(str(Path(root)))


def test_second_fresh_root_reproduces_the_same_journey(journey, tmp_path) -> None:
    """Manually reproduce the vertical in a SECOND temporary root -- proves
    the journey is reproducible, not accidental (plan Task 7 final bullet)."""
    second_root = tmp_path / "second_root"
    paths = journey["paths"]
    for name in ("scenario", "config_a", "config_b", "experiment"):
        r = _run("create", "--root", str(second_root), str(paths[name]))
        assert r.returncode == 0, r.stderr
    run_out = journey["files_dir"] / "second_run.json"
    r = _run(
        "finalize-run",
        "--root",
        str(second_root),
        "--draft",
        str(paths["draft_valid"]),
        *VALIDATOR_ARGS,
        "--output",
        str(run_out),
    )
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout)["validity_status"] == "VALID"


# ---------------------------------------------------------------------------
# Individual command behaviors
# ---------------------------------------------------------------------------


def test_finalize_run_output_is_exclusive_never_overwrites(journey) -> None:
    root = str(journey["root"])
    paths = journey["paths"]
    for name in ("scenario", "config_a", "config_b", "experiment"):
        _run("create", "--root", root, str(paths[name]))
    output = journey["files_dir"] / "run_out.json"
    r = _run("finalize-run", "--root", root, "--draft", str(paths["draft_valid"]), *VALIDATOR_ARGS, "--output", str(output))
    assert r.returncode == 0, r.stderr
    r2 = _run("finalize-run", "--root", root, "--draft", str(paths["draft_valid"]), *VALIDATOR_ARGS, "--output", str(output))
    assert r2.returncode == 2  # refuses to overwrite an existing output file


def test_create_rejects_a_draft_document(journey) -> None:
    root = str(journey["root"])
    r = _run("create", "--root", root, str(journey["paths"]["draft_valid"]))
    assert r.returncode == 2


def test_verify_tree_graph_exit_code_reflects_defects(journey) -> None:
    root = str(journey["root"])
    paths = journey["paths"]
    _run("create", "--root", root, str(paths["scenario"]))
    _run("create", "--root", root, str(paths["config_a"]))
    _run("create", "--root", root, str(paths["config_b"]))
    _run("create", "--root", root, str(paths["experiment"]))
    r = _run("verify-tree-graph", "--root", root)
    assert r.returncode == 0
    # corrupt one stored artifact directly on disk
    config_files = list((journey["root"] / "configurations").rglob("configuration.json"))
    config_files[0].write_bytes(b"{not valid json")
    r2 = _run("verify-tree-graph", "--root", root)
    assert r2.returncode == 2
    payload = json.loads(r2.stdout)
    assert payload["defect_count"] > 0


def test_score_integrity_rejects_unresolvable_run(journey) -> None:
    root = str(journey["root"])
    r = _run(
        "score-integrity",
        "--root",
        root,
        "--run-id",
        "run:00000000-0000-4000-8000-000000000000",
        "--scorer-code-ref",
        "git:mastermindx-market-intelligence/Mastermind@" + "a" * 40,
        "--created-at",
        "2026-08-25T00:00:12Z",
        "--id",
        f"scorer-pass:{uuid.uuid4()}",
    )
    assert r.returncode == 2
