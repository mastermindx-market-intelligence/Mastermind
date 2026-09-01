"""EVAL-C0: governed corpus / holdout governance.

Covers ``scripts/agent_eval/corpus.py`` (corpus-revision derivation,
scenario-vs-corpus consistency validation, the holdout-seal and
corpus-manifest closed schemas) plus the additive ``corpus-verify`` CLI
subcommand, and proves the real committed ``corpus/agent_eval/`` tree is
CONSISTENT under the real merged scenario contract.

TDD discriminating tests named by the C0 commission:

- tampered case -> revision mismatch
  (test_tampered_fixture_byte_produces_corpus_tree_digest_mismatch)
- missing cutoff -> refusal
  (test_scenario_missing_temporal_cutoff_produces_refusal)
- unsealed holdout body in-repo -> refusal
  (test_unsealed_holdout_body_in_repo_produces_refusal)
- secret-shape planted in a case -> refusal via the existing privacy detector
  (test_secret_shape_planted_in_scenario_produces_refusal_via_privacy_detector)
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.agent_eval import contracts, corpus
from scripts.agent_eval.canonical import canonical_json_bytes, digest_value
from scripts.agent_eval.errors import ContractError

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "agent_evaluation.py"
REAL_CORPUS_ROOT = ROOT / "corpus" / "agent_eval"

TEST_CORPUS_REVISION = "git:mastermindx-market-intelligence/Mastermind@" + "c" * 40
AUTHORSHIP = {"author_ref": "person:test-author", "independent_reviewer_ref": "person:test-reviewer"}
CUTOFF_AT = "2026-09-01T00:00:00Z"
AUTHORED_AT = "2026-09-01T00:30:00Z"

_PROFILE_DIGEST = digest_value({"profile": "test_reviewer", "version": 1})
_TOOL_DIGEST = digest_value({"tool": "test_read", "schema_version": 1})


# ---------------------------------------------------------------------------
# Minimal test-only corpus factories (independent of the real committed
# corpus and its real corpus_revision anchor -- these use a synthetic
# placeholder sha, same convention as tests/agent_eval_factories.py).
# ---------------------------------------------------------------------------


def _fixture_ref(family: str, case: str, name: str, *, corpus_revision: str = TEST_CORPUS_REVISION) -> str:
    return f"{corpus_revision}#corpus/agent_eval/scenarios/{family}/{case}/v1/fixtures/{name}"


def _write_json(path: Path, document: dict) -> None:
    """Write ``document`` as CANONICAL bytes (matches ``canonical.digest_value``'s
    own serialization exactly) -- fixture digests in this test file are
    computed with ``digest_value(...)`` over the same in-memory dict, so the
    on-disk bytes must match byte-for-byte or every fixture-digest check
    would spuriously fail regardless of correctness."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_json_bytes(document))


def _scenario_fields(
    *,
    family: str = "test_family",
    case: str = "test_case",
    objective: str = "A synthetic test-only comprehension case.",
    corpus_revision: str = TEST_CORPUS_REVISION,
) -> dict:
    input_ref = _fixture_ref(family, case, "input.json", corpus_revision=corpus_revision)
    return {
        "scenario_id": f"scenario:{family}:{case}",
        "scenario_version": 1,
        "scenario_family": f"mastermind.{family}.v1",
        "corpus_revision": corpus_revision,
        "risk_tier": "LOW",
        "objective": objective,
        "input_fixture": {"artifact_ref": input_ref, "digest": digest_value({"input": case})},
        "expected_contract": {
            "artifact_ref": _fixture_ref(family, case, "expected.json", corpus_revision=corpus_revision),
            "digest": digest_value({"expected": case}),
        },
        "temporal": {"cutoff_at": CUTOFF_AT, "authored_at": AUTHORED_AT},
        "source_policy": {"allowlist_artifacts": [], "denylist_refs": [], "solution_refs_hidden": []},
        "capability_policy": {
            "profile_id": "test_reviewer",
            "profile_digest": _PROFILE_DIGEST,
            "allowed_capability_ids": ["read_frozen_extract"],
            "forbidden_capability_ids": ["execute_shell"],
            "allowed_tool_schema_digests": [_TOOL_DIGEST],
        },
        "execution_policy": {
            "fresh_process_required": True,
            "fresh_workspace_required": True,
            "fresh_session_required": True,
            "resume_allowed": False,
            "network_policy": "DENY_ALL",
            "network_allowlist": [],
            "max_elapsed_ms": 60000,
            "max_tool_calls": 5,
            "allowed_degradations": [],
        },
        "effect_policy": {"mode": "NO_EFFECT_ONLY", "allowed_operation_refs": []},
        "scoring_policy": {
            "required_scorers": ["mastermind.technical_integrity.v1"],
            "optional_scorers": [],
            "required_dimensions": ["cleanup_integrity", "configuration_integrity", "effect_integrity", "source_integrity"],
        },
        "privacy": {"classification": "PUBLIC_SAFE", "model_visible_artifact_refs": [input_ref], "retention_class": "BOUNDED"},
        "authorship": AUTHORSHIP,
        "supersedes": None,
    }


def _write_scenario_case(corpus_root: Path, *, family: str, case: str, fields: dict | None = None) -> dict:
    document = contracts.build_scenario(fields if fields is not None else _scenario_fields(family=family, case=case))
    case_dir = corpus_root / "scenarios" / family / case / "v1"
    _write_json(case_dir / "fixtures" / "input.json", {"input": case})
    _write_json(case_dir / "fixtures" / "expected.json", {"expected": case})
    _write_json(case_dir / "scenario.json", document)
    return document


def _holdout_fields(*, family: str = "test_family", case: str = "held_out_case", corpus_revision: str = TEST_CORPUS_REVISION) -> dict:
    return {
        "scenario_id": f"scenario:{family}:{case}",
        "scenario_family": f"mastermind.{family}.v1",
        "risk_tier": "LOW",
        "corpus_revision": corpus_revision,
        "temporal_cutoff": CUTOFF_AT,
        "sealed_body_digest": digest_value({"sealed": case}),
        "sealing_method": "SHA256_OVER_CANONICAL_BUNDLE",
        "private_evidence_root_ref": f"private-eval-root:agent_eval/holdouts/{family}/{case}/v1/bundle.json",
        "authorship": AUTHORSHIP,
        "created_at": "2026-09-01T01:00:00Z",
    }


def _write_holdout_case(corpus_root: Path, *, family: str, case: str, fields: dict | None = None) -> dict:
    document = corpus.build_holdout_seal(fields if fields is not None else _holdout_fields(family=family, case=case))
    case_dir = corpus_root / "holdouts" / family / case
    _write_json(case_dir / "holdout_seal.json", document)
    return document


def _write_manifest(corpus_root: Path, *, corpus_revision: str = TEST_CORPUS_REVISION) -> dict:
    tree_digest, entries = corpus.compute_corpus_tree_digest(corpus_root)
    manifest = corpus.build_corpus_manifest(
        {
            "corpus_revision": corpus_revision,
            "entries": list(entries),
            "corpus_tree_digest": tree_digest,
            "generated_at": "2026-09-01T01:15:00Z",
        }
    )
    _write_json(corpus_root / "corpus_manifest.json", manifest)
    return manifest


def _build_minimal_valid_corpus(tmp_path: Path) -> Path:
    corpus_root = tmp_path / "corpus" / "agent_eval"
    _write_scenario_case(corpus_root, family="alpha_family", case="case_one")
    _write_scenario_case(corpus_root, family="beta_family", case="case_two")
    _write_holdout_case(corpus_root, family="alpha_family", case="held_out_one")
    _write_manifest(corpus_root)
    return corpus_root


# ---------------------------------------------------------------------------
# 1. Corpus-manifest closed contract
# ---------------------------------------------------------------------------


def test_build_corpus_manifest_round_trips_shape_valid() -> None:
    manifest = corpus.build_corpus_manifest(
        {
            "corpus_revision": TEST_CORPUS_REVISION,
            "entries": [{"relative_path": "a.json", "digest": digest_value({"a": 1})}],
            "corpus_tree_digest": digest_value([{"relative_path": "a.json", "digest": digest_value({"a": 1})}]),
            "generated_at": CUTOFF_AT,
        }
    )
    assert corpus.validate_corpus_manifest_shape(manifest) == "SHAPE_VALID"
    assert manifest["schema"] == corpus.CORPUS_MANIFEST_SCHEMA


def test_corpus_manifest_shape_rejects_unknown_field() -> None:
    manifest = corpus.build_corpus_manifest(
        {
            "corpus_revision": TEST_CORPUS_REVISION,
            "entries": [],
            "corpus_tree_digest": digest_value([]),
            "generated_at": CUTOFF_AT,
        }
    )
    tampered = dict(manifest)
    tampered["extra_field"] = "not allowed"
    with pytest.raises(ContractError) as excinfo:
        corpus.validate_corpus_manifest_shape(tampered)
    assert any(d.code in {"UNKNOWN_FIELD", "DIGEST_MISMATCH"} for d in excinfo.value.defects)


def test_corpus_manifest_entries_must_be_sorted_and_unique() -> None:
    entries = [
        {"relative_path": "b.json", "digest": digest_value({"b": 1})},
        {"relative_path": "a.json", "digest": digest_value({"a": 1})},
    ]
    with pytest.raises(ContractError) as excinfo:
        corpus.build_corpus_manifest(
            {
                "corpus_revision": TEST_CORPUS_REVISION,
                "entries": entries,
                "corpus_tree_digest": digest_value(entries),
                "generated_at": CUTOFF_AT,
            }
        )
    assert any(d.code == "LIST_NOT_SORTED" for d in excinfo.value.defects)


def test_build_corpus_manifest_rejects_caller_supplied_schema_or_digest() -> None:
    with pytest.raises(ContractError):
        corpus.build_corpus_manifest({"schema": "x", "corpus_revision": TEST_CORPUS_REVISION, "entries": [], "corpus_tree_digest": digest_value([]), "generated_at": CUTOFF_AT})
    with pytest.raises(ContractError):
        corpus.build_corpus_manifest({"manifest_digest": "sha256:" + "0" * 64, "corpus_revision": TEST_CORPUS_REVISION, "entries": [], "corpus_tree_digest": digest_value([]), "generated_at": CUTOFF_AT})


# ---------------------------------------------------------------------------
# 2. Holdout-seal closed contract
# ---------------------------------------------------------------------------


def test_build_holdout_seal_round_trips_shape_valid() -> None:
    seal = corpus.build_holdout_seal(_holdout_fields())
    assert corpus.validate_holdout_seal_shape(seal) == "SHAPE_VALID"
    assert seal["schema"] == corpus.CORPUS_HOLDOUT_SEAL_SCHEMA


def test_holdout_seal_rejects_non_independent_reviewer() -> None:
    fields = _holdout_fields()
    fields["authorship"] = {"author_ref": "person:same", "independent_reviewer_ref": "person:same"}
    with pytest.raises(ContractError) as excinfo:
        corpus.build_holdout_seal(fields)
    assert any(d.code == "REVIEWER_NOT_INDEPENDENT" for d in excinfo.value.defects)


def test_holdout_seal_rejects_scenario_family_id_mismatch() -> None:
    fields = _holdout_fields(family="alpha_family", case="case_x")
    fields["scenario_family"] = "mastermind.a_totally_different_family.v1"
    with pytest.raises(ContractError) as excinfo:
        corpus.build_holdout_seal(fields)
    assert any(d.code == "SCENARIO_FAMILY_ID_MISMATCH" for d in excinfo.value.defects)


def test_holdout_seal_rejects_missing_field() -> None:
    fields = _holdout_fields()
    del fields["temporal_cutoff"]
    with pytest.raises(ContractError) as excinfo:
        corpus.build_holdout_seal(fields)
    assert any(d.code == "FIELD_MISSING" for d in excinfo.value.defects)


def test_holdout_seal_path_mirrors_store_safe_path_law() -> None:
    path = corpus.holdout_seal_path("scenario:alpha_family:case_x")
    assert path == Path("holdouts") / "alpha_family" / "case_x" / "holdout_seal.json"


# ---------------------------------------------------------------------------
# 3. Corpus-tree digest derivation (tamper detection)
# ---------------------------------------------------------------------------


def test_file_digest_is_plain_sha256_over_raw_bytes() -> None:
    import hashlib

    data = b"hello world"
    assert corpus.file_digest(data) == "sha256:" + hashlib.sha256(data).hexdigest()


def test_compute_corpus_tree_digest_excludes_the_manifest_itself(tmp_path: Path) -> None:
    corpus_root = tmp_path / "corpus" / "agent_eval"
    _write_scenario_case(corpus_root, family="alpha_family", case="case_one")
    digest_before, entries_before = corpus.compute_corpus_tree_digest(corpus_root)
    _write_manifest(corpus_root)  # writes corpus_manifest.json into the SAME tree
    digest_after, entries_after = corpus.compute_corpus_tree_digest(corpus_root)
    assert digest_before == digest_after
    assert entries_before == entries_after
    assert not any(entry["relative_path"] == "corpus_manifest.json" for entry in entries_after)


def test_compute_corpus_tree_digest_changes_on_any_byte_change(tmp_path: Path) -> None:
    corpus_root = tmp_path / "corpus" / "agent_eval"
    _write_scenario_case(corpus_root, family="alpha_family", case="case_one")
    digest_before, _ = corpus.compute_corpus_tree_digest(corpus_root)
    input_path = corpus_root / "scenarios" / "alpha_family" / "case_one" / "v1" / "fixtures" / "input.json"
    input_path.write_bytes(input_path.read_bytes() + b" ")  # single extra byte
    digest_after, _ = corpus.compute_corpus_tree_digest(corpus_root)
    assert digest_before != digest_after


def test_enumerate_corpus_files_skips_symlinks(tmp_path: Path) -> None:
    corpus_root = tmp_path / "corpus" / "agent_eval"
    _write_scenario_case(corpus_root, family="alpha_family", case="case_one")
    real_file = corpus_root / "scenarios" / "alpha_family" / "case_one" / "v1" / "scenario.json"
    link = corpus_root / "scenarios" / "alpha_family" / "case_one" / "v1" / "scenario_link.json"
    link.symlink_to(real_file)
    files = corpus.enumerate_corpus_files(corpus_root)
    assert Path("scenarios/alpha_family/case_one/v1/scenario_link.json") not in files
    assert Path("scenarios/alpha_family/case_one/v1/scenario.json") in files


# ---------------------------------------------------------------------------
# 4. verify_corpus_tree_consistency -- happy path
# ---------------------------------------------------------------------------


def test_verify_corpus_tree_consistency_passes_on_freshly_built_corpus(tmp_path: Path) -> None:
    corpus_root = _build_minimal_valid_corpus(tmp_path)
    report = corpus.verify_corpus_tree_consistency(corpus_root, tmp_path)
    assert report.result == "CONSISTENT"
    assert report.defects == ()
    assert report.scenario_count == 2
    assert report.holdout_count == 1
    assert report.corpus_revision == TEST_CORPUS_REVISION


def test_verify_corpus_tree_consistency_reports_manifest_missing(tmp_path: Path) -> None:
    corpus_root = tmp_path / "corpus" / "agent_eval"
    _write_scenario_case(corpus_root, family="alpha_family", case="case_one")
    report = corpus.verify_corpus_tree_consistency(corpus_root, tmp_path)
    assert report.result == "INCONSISTENT"
    assert any(d.code == "MANIFEST_MISSING" for d in report.defects)


# ---------------------------------------------------------------------------
# 5. TDD discriminating tests named by the C0 commission
# ---------------------------------------------------------------------------


def test_tampered_fixture_byte_produces_corpus_tree_digest_mismatch(tmp_path: Path) -> None:
    """tampered case -> revision mismatch."""
    corpus_root = _build_minimal_valid_corpus(tmp_path)
    input_path = corpus_root / "scenarios" / "alpha_family" / "case_one" / "v1" / "fixtures" / "input.json"
    input_path.write_bytes(input_path.read_bytes() + b" ")  # tamper: one extra byte, post-manifest
    report = corpus.verify_corpus_tree_consistency(corpus_root, tmp_path)
    assert report.result == "INCONSISTENT"
    codes = {d.code for d in report.defects}
    assert "CORPUS_TREE_DIGEST_MISMATCH" in codes
    assert "FIXTURE_DIGEST_MISMATCH" in codes


def test_scenario_missing_temporal_cutoff_produces_refusal(tmp_path: Path) -> None:
    """missing cutoff -> refusal."""
    corpus_root = tmp_path / "corpus" / "agent_eval"
    document = contracts.build_scenario(_scenario_fields(family="alpha_family", case="case_one"))
    # hand-craft a malformed persisted document that bypasses the contract's
    # own build-time enforcement: delete temporal.cutoff_at entirely, then
    # write it directly to disk exactly as a corrupted/hand-edited artifact
    # would appear -- corpus-verify must catch this at READ time, not rely
    # on a build-time guarantee that this file was never edited by hand.
    malformed = json.loads(json.dumps(document))
    del malformed["temporal"]["cutoff_at"]
    case_dir = corpus_root / "scenarios" / "alpha_family" / "case_one" / "v1"
    _write_json(case_dir / "fixtures" / "input.json", {"input": "case_one"})
    _write_json(case_dir / "fixtures" / "expected.json", {"expected": "case_one"})
    _write_json(case_dir / "scenario.json", malformed)
    _write_manifest(corpus_root)  # manifest matches the malformed bytes; isolates THIS defect
    report = corpus.verify_corpus_tree_consistency(corpus_root, tmp_path)
    assert report.result == "INCONSISTENT"
    assert any(d.code == "FIELD_MISSING" for d in report.defects)


def test_unsealed_holdout_body_in_repo_produces_refusal(tmp_path: Path) -> None:
    """unsealed holdout body in-repo -> refusal."""
    corpus_root = tmp_path / "corpus" / "agent_eval"
    _write_holdout_case(corpus_root, family="alpha_family", case="case_one")
    # leak the sealed body's scenario.json into the SAME holdout directory --
    # this must never be allowed to coexist with a holdout_seal.json.
    scenario_document = contracts.build_scenario(_scenario_fields(family="alpha_family", case="case_one"))
    holdout_dir = corpus_root / "holdouts" / "alpha_family" / "case_one"
    _write_json(holdout_dir / "scenario.json", scenario_document)
    _write_manifest(corpus_root)
    report = corpus.verify_corpus_tree_consistency(corpus_root, tmp_path)
    assert report.result == "INCONSISTENT"
    assert any(d.code == "UNSEALED_HOLDOUT_BODY_IN_REPO" for d in report.defects)


def test_secret_shape_planted_in_scenario_produces_refusal_via_privacy_detector(tmp_path: Path) -> None:
    """secret-shape planted in a case -> refusal via the existing privacy detector."""
    corpus_root = tmp_path / "corpus" / "agent_eval"
    fields = _scenario_fields(family="alpha_family", case="case_one")
    # plant a recognized secret SHAPE inside an ordinary free-text field
    # (objective) -- this keeps the document structurally SHAPE_VALID (no
    # unknown field, so the closed-object check alone would pass it) and
    # isolates the privacy detector as the ONLY thing that can catch it.
    fields["objective"] = "Leaked credential for testing: sk-ant-abcdefghijklmnopqrstuvwxyz012345"
    document = contracts.build_scenario(fields)
    assert contracts.validate_scenario_shape(document) == "SHAPE_VALID"  # structurally fine on its own
    case_dir = corpus_root / "scenarios" / "alpha_family" / "case_one" / "v1"
    _write_json(case_dir / "fixtures" / "input.json", {"input": "case_one"})
    _write_json(case_dir / "fixtures" / "expected.json", {"expected": "case_one"})
    _write_json(case_dir / "scenario.json", document)
    _write_manifest(corpus_root)
    report = corpus.verify_corpus_tree_consistency(corpus_root, tmp_path)
    assert report.result == "INCONSISTENT"
    assert any(d.code == "KNOWN_SECRET_PREFIX" for d in report.defects)


def test_non_public_safe_classification_in_public_corpus_is_refused(tmp_path: Path) -> None:
    corpus_root = tmp_path / "corpus" / "agent_eval"
    fields = _scenario_fields(family="alpha_family", case="case_one")
    fields["privacy"]["classification"] = "PRIVATE_RESTRICTED"
    fields["privacy"]["model_visible_artifact_refs"] = []
    document = contracts.build_scenario(fields)
    case_dir = corpus_root / "scenarios" / "alpha_family" / "case_one" / "v1"
    _write_json(case_dir / "fixtures" / "input.json", {"input": "case_one"})
    _write_json(case_dir / "fixtures" / "expected.json", {"expected": "case_one"})
    _write_json(case_dir / "scenario.json", document)
    _write_manifest(corpus_root)
    report = corpus.verify_corpus_tree_consistency(corpus_root, tmp_path)
    assert report.result == "INCONSISTENT"
    assert any(d.code == "NON_PUBLIC_SAFE_IN_PUBLIC_CORPUS" for d in report.defects)


def test_scenario_corpus_revision_not_anchored_to_manifest_is_refused(tmp_path: Path) -> None:
    corpus_root = tmp_path / "corpus" / "agent_eval"
    other_revision = "git:mastermindx-market-intelligence/Mastermind@" + "d" * 40
    _write_scenario_case(
        corpus_root,
        family="alpha_family",
        case="case_one",
        fields=_scenario_fields(family="alpha_family", case="case_one", corpus_revision=other_revision),
    )
    _write_manifest(corpus_root)  # manifest anchor stays TEST_CORPUS_REVISION -- scenario declares a DIFFERENT one
    report = corpus.verify_corpus_tree_consistency(corpus_root, tmp_path)
    assert report.result == "INCONSISTENT"
    assert any(d.code == "CORPUS_REVISION_NOT_ANCHORED" for d in report.defects)


def test_scenario_mislocated_relative_to_its_own_id_is_refused(tmp_path: Path) -> None:
    corpus_root = tmp_path / "corpus" / "agent_eval"
    document = contracts.build_scenario(_scenario_fields(family="alpha_family", case="case_one"))
    # write it under the WRONG case directory
    case_dir = corpus_root / "scenarios" / "alpha_family" / "wrong_case_dir" / "v1"
    _write_json(case_dir / "fixtures" / "input.json", {"input": "case_one"})
    _write_json(case_dir / "fixtures" / "expected.json", {"expected": "case_one"})
    _write_json(case_dir / "scenario.json", document)
    _write_manifest(corpus_root)
    report = corpus.verify_corpus_tree_consistency(corpus_root, tmp_path)
    assert report.result == "INCONSISTENT"
    assert any(d.code == "SCENARIO_MISLOCATED" for d in report.defects)


def test_holdout_mislocated_relative_to_its_own_id_is_refused(tmp_path: Path) -> None:
    corpus_root = tmp_path / "corpus" / "agent_eval"
    document = corpus.build_holdout_seal(_holdout_fields(family="alpha_family", case="case_one"))
    wrong_dir = corpus_root / "holdouts" / "alpha_family" / "wrong_case_dir"
    _write_json(wrong_dir / "holdout_seal.json", document)
    _write_manifest(corpus_root)
    report = corpus.verify_corpus_tree_consistency(corpus_root, tmp_path)
    assert report.result == "INCONSISTENT"
    assert any(d.code == "HOLDOUT_SEAL_MISLOCATED" for d in report.defects)


def test_fixture_file_missing_from_disk_is_refused(tmp_path: Path) -> None:
    corpus_root = tmp_path / "corpus" / "agent_eval"
    document = contracts.build_scenario(_scenario_fields(family="alpha_family", case="case_one"))
    case_dir = corpus_root / "scenarios" / "alpha_family" / "case_one" / "v1"
    # write the scenario document but NOT its fixture files
    _write_json(case_dir / "scenario.json", document)
    _write_manifest(corpus_root)
    report = corpus.verify_corpus_tree_consistency(corpus_root, tmp_path)
    assert report.result == "INCONSISTENT"
    assert any(d.code == "FIXTURE_FILE_UNRESOLVED" for d in report.defects)


# ---------------------------------------------------------------------------
# 6. The real committed corpus tree
# ---------------------------------------------------------------------------


def test_real_committed_corpus_is_consistent() -> None:
    report = corpus.verify_corpus_tree_consistency(REAL_CORPUS_ROOT, ROOT)
    assert report.defects == (), f"unexpected defects in the real corpus: {report.defects}"
    assert report.result == "CONSISTENT"
    assert report.scenario_count >= 9
    assert report.holdout_count >= 3


def test_real_committed_corpus_scenarios_validate_against_the_merged_contract() -> None:
    scenario_files = sorted(REAL_CORPUS_ROOT.rglob("scenario.json"))
    assert len(scenario_files) >= 9
    for path in scenario_files:
        document = json.loads(path.read_bytes())
        assert contracts.validate_scenario_shape(document) == "SHAPE_VALID"
        assert document["privacy"]["classification"] == "PUBLIC_SAFE"


def test_real_committed_corpus_has_at_least_three_task_families() -> None:
    scenario_files = sorted(REAL_CORPUS_ROOT.rglob("scenario.json"))
    families = {json.loads(path.read_bytes())["scenario_family"] for path in scenario_files}
    assert len(families) >= 3
    holdout_files = sorted(REAL_CORPUS_ROOT.rglob("holdout_seal.json"))
    assert len(holdout_files) >= 3
    holdout_families = {json.loads(path.read_bytes())["scenario_family"] for path in holdout_files}
    assert families == holdout_families  # every public family has at least one sealed holdout


def test_real_committed_corpus_holdout_bodies_are_not_in_the_repository() -> None:
    for holdout_file in sorted(REAL_CORPUS_ROOT.rglob("holdout_seal.json")):
        case_dir = holdout_file.parent
        assert not (case_dir / "scenario.json").exists()
        assert not (case_dir / "fixtures").exists()


# ---------------------------------------------------------------------------
# 7. corpus-verify CLI (real subprocess, mirrors test_agent_eval_cli.py)
# ---------------------------------------------------------------------------


def _run_cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(CLI), *args], capture_output=True, text=True, cwd=str(ROOT), timeout=60)


def test_cli_corpus_verify_passes_on_the_real_corpus() -> None:
    result = _run_cli("corpus-verify", "--corpus-root", str(REAL_CORPUS_ROOT), "--repo-root", str(ROOT))
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["result"] == "CONSISTENT"
    assert payload["defect_count"] == 0
    assert payload["scenario_count"] >= 9
    assert payload["holdout_count"] >= 3


def test_cli_corpus_verify_exits_nonzero_on_tampered_tree(tmp_path: Path) -> None:
    corpus_root = _build_minimal_valid_corpus(tmp_path)
    input_path = corpus_root / "scenarios" / "alpha_family" / "case_one" / "v1" / "fixtures" / "input.json"
    input_path.write_bytes(input_path.read_bytes() + b" ")
    result = _run_cli("corpus-verify", "--corpus-root", str(corpus_root), "--repo-root", str(tmp_path))
    assert result.returncode == 2
    payload = json.loads(result.stdout)
    assert payload["result"] == "INCONSISTENT"
    assert payload["defect_count"] > 0


def test_cli_corpus_verify_rejects_missing_corpus_root() -> None:
    result = _run_cli("corpus-verify", "--corpus-root", "/nonexistent/path/definitely-not-here", "--repo-root", str(ROOT))
    assert result.returncode == 2
    assert "no such corpus directory" in result.stderr
