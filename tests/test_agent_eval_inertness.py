"""EVAL-R0 Task 8: inertness, privacy, mutation, path fences.

Every load-bearing authority, privacy, identity, verification-scope,
immutability, and denominator invariant gets an executable negative test
somewhere across the EVAL-R0 test suite. This module concentrates:

1. AST-level import/attribute fences on every production module (no
   process/network/database/environment primitive, and -- per the binding
   2026-09-01 environment-free amendment, which has narrow precedence over
   the plan's older "permit the OHF helper" language -- no
   ``scripts.ohf.redaction`` / ``common.redaction`` either);
2. subprocess proof that importing each production module has zero
   observable side effect;
3. a consolidated mutation-matrix sweep naming every category the plan
   Task 8 requires, cross-referencing the dedicated test already proving it
   where one already exists in an earlier task's file, and adding a fresh
   test here for anything not already covered;
4. a changed-path fence: the diff against the exact protected base commit
   touches only plan §4.1's allowed paths plus the amendment's two
   additions -- never a control-plane/config/dependency/workflow file.
"""
from __future__ import annotations

import ast
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.agent_eval import contracts, scoring, store, validity
from scripts.agent_eval.canonical import add_document_digest
from scripts.agent_eval.errors import ContractError
from scripts.agent_eval.verification import GRAPH_VERIFIED_SCOPE, VerificationResult
from tests.agent_eval_factories import (
    build_alternate_configuration,
    build_baseline_configuration,
    build_baseline_scenario,
    build_run_draft,
    build_two_arm_experiment,
    fresh_run_id,
)

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_DIR = ROOT / "scripts" / "agent_eval"
PRODUCTION_FILES = tuple(sorted(PACKAGE_DIR.glob("*.py"))) + (ROOT / "scripts" / "agent_evaluation.py",)

VALIDATOR_KW = dict(
    validator_id="mastermind.eval_r0_finalizer.v1",
    validator_version="1",
    validator_code_ref="git:mastermindx-market-intelligence/Mastermind@" + "a" * 40,
    validated_at="2026-08-25T00:00:10Z",
    created_at="2026-08-25T00:00:11Z",
)

# ---------------------------------------------------------------------------
# 1. AST import/attribute fences
# ---------------------------------------------------------------------------

FORBIDDEN_IMPORT_MODULES = frozenset(
    {
        # amendment §2/§3.2/§4.5: never OHF/general redaction (ambient env read)
        "scripts.ohf.redaction",
        "common.redaction",
        "scripts.ohf",
        "common",
        # process/network/database
        "subprocess",
        "socket",
        "sqlite3",
        "psycopg2",
        "psycopg",
        "duckdb",
        "httpx",
        "requests",
        "urllib.request",
        "urllib3",
        "aiohttp",
        "websockets",
        "threading",
        "multiprocessing",
        "asyncio",
        # Executive/worker/router/Slack/company integrations
        "control_plane",
        "integrations.slack_agent_dialogue",
        "integrations",
        "app",
        "bot",
        "brain",
        "bridge",
        # third-party evaluation frameworks R0 does not adopt
        "inspect_ai",
        "langfuse",
        "promptfoo",
    }
)

FORBIDDEN_ATTRIBUTE_ACCESS = frozenset(
    {
        # amendment §4.5: environment-free fences
        "os.environ",
        "os.getenv",
        "environment_secrets",
        # process spawning via the (permitted, filesystem-only) os import
        "os.system",
        "os.popen",
        "os.fork",
        "os.execv",
        "os.execve",
        "os.execvp",
        "os.execvpe",
        "os.spawnv",
        "os.spawnl",
        "os.spawnve",
    }
)


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _imported_module_names(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            # normalize relative imports (level > 0) to their bare module name;
            # this package never uses relative imports, but stay defensive
            names.add(node.module)
    return names


def _dotted_attribute_accesses(tree: ast.AST) -> set[str]:
    hits: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            parts = []
            cursor: ast.AST = node
            while isinstance(cursor, ast.Attribute):
                parts.append(cursor.attr)
                cursor = cursor.value
            if isinstance(cursor, ast.Name):
                parts.append(cursor.id)
                hits.add(".".join(reversed(parts)))
        elif isinstance(node, ast.Name):
            hits.add(node.id)
    return hits


@pytest.mark.parametrize("path", PRODUCTION_FILES, ids=lambda p: p.name)
def test_production_module_imports_no_forbidden_module(path: Path) -> None:
    imported = _imported_module_names(_parse(path))
    hits = {
        name
        for name in imported
        if any(name == forbidden or name.startswith(forbidden + ".") for forbidden in FORBIDDEN_IMPORT_MODULES)
    }
    assert not hits, f"{path.relative_to(ROOT)} imports forbidden module(s): {hits}"


@pytest.mark.parametrize("path", PRODUCTION_FILES, ids=lambda p: p.name)
def test_production_module_never_accesses_forbidden_attribute(path: Path) -> None:
    accesses = _dotted_attribute_accesses(_parse(path))
    hits = accesses & FORBIDDEN_ATTRIBUTE_ACCESS
    assert not hits, f"{path.relative_to(ROOT)} accesses forbidden primitive(s): {hits}"


def test_only_the_amendment_named_exception_exists_for_privacy_module() -> None:
    # privacy.py is the ONE module permitted to define secret-shape pattern
    # constants; confirm it still imports no forbidden module either.
    privacy_path = PACKAGE_DIR / "privacy.py"
    assert privacy_path.exists()
    imported = _imported_module_names(_parse(privacy_path))
    assert "scripts.ohf.redaction" not in imported
    assert "common.redaction" not in imported


# ---------------------------------------------------------------------------
# 2. Subprocess proof: importing each production module has no side effect
# ---------------------------------------------------------------------------


def _module_name_for(path: Path) -> str:
    if path.name == "agent_evaluation.py":
        return "scripts.agent_evaluation"
    if path.name == "__init__.py":
        return "scripts.agent_eval"
    return f"scripts.agent_eval.{path.stem}"


@pytest.mark.parametrize("path", PRODUCTION_FILES, ids=lambda p: p.name)
def test_importing_production_module_has_no_observable_side_effect(path: Path, tmp_path) -> None:
    # NOTE: this repo's tests/conftest.py has autouse fixtures that create
    # isolation directories (_papers, _runlog, _macro_risk, ...) the FIRST
    # time any test accesses `tmp_path` -- those pre-exist before our test
    # body runs and are unrelated to this module's own behavior. Diff
    # before/after the subprocess call rather than assuming an empty dir.
    before = set(tmp_path.iterdir())
    module_name = _module_name_for(path)
    script = f"import sys\nsys.path.insert(0, {str(ROOT)!r})\nimport {module_name}\n"
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        cwd=str(tmp_path),
        timeout=30,
        env={"PATH": os.environ.get("PATH", "")},
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
    assert result.stderr == ""
    after = set(tmp_path.iterdir())
    assert after == before  # no file/socket/thread/background artifact created by the import


def test_environment_mutation_never_changes_whole_synthetic_journey_outcome(monkeypatch) -> None:
    """Prove no path through contracts/validity/scoring/store consults
    os.environ, by making any read raise loudly, then running the complete
    synthetic journey end to end."""

    class _RaisingMapping(dict):
        def __getitem__(self, key):  # pragma: no cover - defensive
            raise AssertionError(f"production R0 code must never read os.environ[{key!r}]")

        def get(self, key, default=None):  # pragma: no cover - defensive
            raise AssertionError(f"production R0 code must never read os.environ.get({key!r})")

    monkeypatch.setattr(os, "environ", _RaisingMapping())

    scenario = build_baseline_scenario()
    config_a = build_baseline_configuration()
    config_b = build_alternate_configuration()
    experiment = build_two_arm_experiment(scenario, config_a, config_b)
    draft = build_run_draft(scenario, config_a, experiment, arm_id="arm_a", replicate_index=1)
    run = validity.finalize_run_receipt(scenario, config_a, experiment, draft, **VALIDATOR_KW)
    scorer_pass = scoring.build_technical_integrity_scorer_pass(
        run, scorer_pass_id="scorer-pass:11111111-1111-4111-8111-111111111111", scorer_code_ref=VALIDATOR_KW["validator_code_ref"], created_at="2026-08-25T00:00:12Z"
    )
    evidence = scoring.summarize_experiment(
        experiment,
        scenario,
        (run,),
        (scorer_pass,),
        evidence_ref_id="evidence-ref:22222222-2222-4222-8222-222222222222",
        intended_owner="person:sol",
        review_at="2026-08-26T00:00:00Z",
        created_at="2026-08-25T00:00:13Z",
        analysis_version="mastermind.agent_evaluation_r0_analysis.v1",
    )
    assert evidence["evidence_grade"] == "INSUFFICIENT_EVIDENCE"


# ---------------------------------------------------------------------------
# 3. Mutation matrix (plan Task 8) -- consolidated sweep
# ---------------------------------------------------------------------------


def _graph():
    scenario = build_baseline_scenario()
    config_a = build_baseline_configuration()
    config_b = build_alternate_configuration()
    experiment = build_two_arm_experiment(scenario, config_a, config_b)
    return scenario, config_a, config_b, experiment


def test_matrix_unknown_field_rejected_on_every_schema() -> None:
    # see also: test_agent_eval_contracts.py, test_agent_eval_scoring.py
    scenario, config_a, _config_b, experiment = _graph()
    run = validity.finalize_run_receipt(
        scenario, config_a, experiment, build_run_draft(scenario, config_a, experiment, arm_id="arm_a", replicate_index=1), **VALIDATOR_KW
    )
    tampered = dict(run)
    tampered["winner"] = "arm_a"
    with pytest.raises(ContractError) as excinfo:
        contracts.validate_run_shape(tampered)
    assert any(d.code == "UNKNOWN_FIELD" for d in excinfo.value.defects)


def test_matrix_wrong_schema_and_digest_rejected() -> None:
    # see also: test_agent_eval_canonical.py
    with pytest.raises(ContractError):
        contracts.validate_scenario_shape({"schema": "not-a-real-schema"})


def test_matrix_float_tuple_non_nfc_non_string_key_rejected() -> None:
    # see also: test_agent_eval_canonical.py
    from scripts.agent_eval.canonical import require_canonical_json_tree

    for bad in (1.5, (1, 2), {1: "x"}):
        with pytest.raises(ContractError):
            require_canonical_json_tree(bad)


def test_matrix_missing_or_wrong_corpus_revision_rejected() -> None:
    # see also: test_agent_eval_validity.py::test_source_policy_digest_mismatch family
    scenario, config_a, _config_b, experiment = _graph()
    draft = build_run_draft(scenario, config_a, experiment, arm_id="arm_a", replicate_index=1)
    draft["scenario"]["corpus_revision"] = "git:mastermindx-market-intelligence/Mastermind@" + "9" * 40
    run = validity.finalize_run_receipt(scenario, config_a, experiment, draft, **VALIDATOR_KW)
    assert "CORPUS_REVISION_MISMATCH" in run["validity"]["reason_codes"]


def test_matrix_bare_commit_ref_rejected() -> None:
    # see also: test_agent_eval_canonical.py::test_parse_source_qualified_ref_rejects_bad_shapes
    from scripts.agent_eval.canonical import parse_source_qualified_ref

    with pytest.raises(ContractError):
        parse_source_qualified_ref("a" * 40)


def test_matrix_detached_artifact_ref_or_digest_rejected() -> None:
    scenario = build_baseline_scenario()
    tampered = dict(scenario)
    tampered["input_fixture"] = {"artifact_ref": scenario["input_fixture"]["artifact_ref"]}  # missing digest
    with pytest.raises(ContractError):
        contracts.validate_scenario_shape(tampered)


def test_matrix_future_or_mismatched_cutoff_rejected() -> None:
    # see also: test_agent_eval_contracts.py::test_cutoff_must_be_at_or_before_authored
    scenario, config_a, _config_b, experiment = _graph()
    draft = build_run_draft(scenario, config_a, experiment, arm_id="arm_a", replicate_index=1)
    draft["scenario"]["temporal_cutoff"] = "2099-01-01T00:00:00Z"
    run = validity.finalize_run_receipt(scenario, config_a, experiment, draft, **VALIDATOR_KW)
    assert "TEMPORAL_CUTOFF_MISMATCH" in run["validity"]["reason_codes"]


def test_matrix_unauthorized_hidden_source_digest_mismatch_rejected() -> None:
    # see also: test_agent_eval_validity.py leakage tests
    scenario, config_a, _config_b, experiment = _graph()
    draft = build_run_draft(scenario, config_a, experiment, arm_id="arm_a", replicate_index=1)
    draft["observations"]["observed_sources"][0]["digest"] = "sha256:" + "9" * 64
    run = validity.finalize_run_receipt(scenario, config_a, experiment, draft, **VALIDATOR_KW)
    assert run["validity"]["status"] == "INVALID_LEAKAGE"


def test_matrix_configuration_id_digest_field_mismatch_rejected() -> None:
    scenario, config_a, _config_b, experiment = _graph()
    draft = build_run_draft(scenario, config_a, experiment, arm_id="arm_a", replicate_index=1)
    draft["configuration"]["configuration_digest"] = "sha256:" + "9" * 64
    run = validity.finalize_run_receipt(scenario, config_a, experiment, draft, **VALIDATOR_KW)
    assert "CONFIGURATION_FIELD_MISMATCH" in run["validity"]["reason_codes"]


def test_matrix_requested_served_model_mismatch_rejected() -> None:
    # see also: test_agent_eval_validity.py::test_served_model_mismatch_run_is_invalid_configuration
    scenario, config_a, _config_b, experiment = _graph()
    draft = build_run_draft(scenario, config_a, experiment, arm_id="arm_a", replicate_index=1, model_served="claude-opus-9")
    run = validity.finalize_run_receipt(scenario, config_a, experiment, draft, **VALIDATOR_KW)
    assert "MODEL_SERVED_MISMATCH" in run["validity"]["reason_codes"]


def test_matrix_extra_or_missing_raw_capability_tool_rejected() -> None:
    # see also: test_agent_eval_validity.py::test_capability_drift_when_observed_exceeds_declared
    scenario, config_a, _config_b, experiment = _graph()
    draft = build_run_draft(scenario, config_a, experiment, arm_id="arm_a", replicate_index=1)
    draft["observations"]["observed_tool_schema_digests"] = ["sha256:" + "7" * 64]
    run = validity.finalize_run_receipt(scenario, config_a, experiment, draft, **VALIDATOR_KW)
    assert "TOOL_SCHEMA_DRIFT" in run["validity"]["reason_codes"]


def test_matrix_forbidden_capability_rejected() -> None:
    scenario, config_a, _config_b, experiment = _graph()
    draft = build_run_draft(scenario, config_a, experiment, arm_id="arm_a", replicate_index=1)
    draft["observations"]["observed_capability_ids"] = ["execute_shell"]
    run = validity.finalize_run_receipt(scenario, config_a, experiment, draft, **VALIDATOR_KW)
    assert "FORBIDDEN_CAPABILITY" in run["validity"]["reason_codes"]


def test_matrix_unexpected_network_destination_rejected() -> None:
    scenario, config_a, _config_b, experiment = _graph()
    draft = build_run_draft(scenario, config_a, experiment, arm_id="arm_a", replicate_index=1)
    draft["observations"]["observed_network_destinations"] = [contracts.sanitize_observed_destination("10.0.0.5")]
    run = validity.finalize_run_receipt(scenario, config_a, experiment, draft, **VALIDATOR_KW)
    assert "UNEXPECTED_NETWORK_DESTINATION" in run["validity"]["reason_codes"]


def test_matrix_freshness_false_is_rejected() -> None:
    scenario, config_a, _config_b, experiment = _graph()
    draft = build_run_draft(scenario, config_a, experiment, arm_id="arm_a", replicate_index=1)
    draft["execution"]["fresh_session_observed"] = False
    run = validity.finalize_run_receipt(scenario, config_a, experiment, draft, **VALIDATOR_KW)
    assert "FRESH_SESSION_UNPROVEN" in run["validity"]["reason_codes"]


def test_matrix_forbidden_resume_rejected() -> None:
    scenario, config_a, _config_b, experiment = _graph()
    draft = build_run_draft(scenario, config_a, experiment, arm_id="arm_a", replicate_index=1)
    draft["execution"]["resume_used"] = True
    run = validity.finalize_run_receipt(scenario, config_a, experiment, draft, **VALIDATOR_KW)
    assert "RESUME_FORBIDDEN" in run["validity"]["reason_codes"]


def test_matrix_unauthorized_unknown_effect_rejected() -> None:
    scenario, config_a, _config_b, experiment = _graph()
    draft = build_run_draft(scenario, config_a, experiment, arm_id="arm_a", replicate_index=1)
    draft["effect"] = {"state": "EFFECT_UNKNOWN", "operation_ref": None, "reconciliation_ref": None}
    run = validity.finalize_run_receipt(scenario, config_a, experiment, draft, **VALIDATOR_KW)
    assert run["validity"]["status"] == "INVALID_EFFECT_UNKNOWN"


def test_matrix_effect_ref_mismatch_rejected() -> None:
    scenario, config_a, _config_b, experiment = _graph()
    draft = build_run_draft(scenario, config_a, experiment, arm_id="arm_a", replicate_index=1)
    draft["effect"]["operation_ref"] = "op:demo"
    with pytest.raises(ContractError):
        contracts.validate_run_draft_shape(draft)


def test_matrix_unproven_cleanup_rejected() -> None:
    scenario, config_a, _config_b, experiment = _graph()
    draft = build_run_draft(scenario, config_a, experiment, arm_id="arm_a", replicate_index=1)
    draft["cleanup"] = {"status": "UNPROVEN", "proof": None}
    run = validity.finalize_run_receipt(scenario, config_a, experiment, draft, **VALIDATOR_KW)
    assert run["validity"]["status"] == "INVALID_CLEANUP"


def test_matrix_degradation_cases() -> None:
    scenario, config_a, _config_b, experiment = _graph()
    draft = build_run_draft(scenario, config_a, experiment, arm_id="arm_a", replicate_index=1)
    draft["observations"]["dependency_degradations"] = list(scenario["execution_policy"]["allowed_degradations"])
    run = validity.finalize_run_receipt(scenario, config_a, experiment, draft, **VALIDATOR_KW)
    assert run["validity"]["status"] == "DEGRADED_DEPENDENCY"


def test_matrix_experiment_scenario_arm_config_mismatch_rejected() -> None:
    scenario, config_a, _config_b, experiment = _graph()
    draft = build_run_draft(scenario, config_a, experiment, arm_id="arm_b", replicate_index=1)
    run = validity.finalize_run_receipt(scenario, config_a, experiment, draft, **VALIDATOR_KW)
    assert "EXPERIMENT_ARM_MISMATCH" in run["validity"]["reason_codes"]


def test_matrix_missing_pair_rejected() -> None:
    scenario, config_a, _config_b, experiment = _graph()
    draft = build_run_draft(scenario, config_a, experiment, arm_id="arm_a", replicate_index=1)
    draft["comparison"]["pair_key"] = None
    run = validity.finalize_run_receipt(scenario, config_a, experiment, draft, **VALIDATOR_KW)
    assert "PAIR_IDENTITY_MISSING" in run["validity"]["reason_codes"]


def test_matrix_bad_replicate_rejected() -> None:
    scenario, config_a, _config_b, experiment = _graph()
    draft = build_run_draft(scenario, config_a, experiment, arm_id="arm_a", replicate_index=1)
    draft["comparison"]["replicate_index"] = 99
    draft["comparison"]["pair_key"] = f"pair:{scenario['scenario_id']}:v{scenario['scenario_version']}:r99"
    run = validity.finalize_run_receipt(scenario, config_a, experiment, draft, **VALIDATOR_KW)
    assert "REPLICATE_OUT_OF_RANGE" in run["validity"]["reason_codes"]


def test_matrix_negative_or_bool_resource_rejected() -> None:
    scenario, config_a, _config_b, experiment = _graph()
    draft = build_run_draft(scenario, config_a, experiment, arm_id="arm_a", replicate_index=1)
    draft["resources"]["input_tokens"] = -5
    with pytest.raises(ContractError):
        contracts.validate_run_draft_shape(draft)
    draft2 = build_run_draft(scenario, config_a, experiment, arm_id="arm_a", replicate_index=1)
    draft2["resources"]["input_tokens"] = True  # bool must not silently coerce to int
    with pytest.raises(ContractError):
        contracts.validate_run_draft_shape(draft2)


def test_matrix_time_duration_mismatch_rejected() -> None:
    scenario, config_a, _config_b, experiment = _graph()
    draft = build_run_draft(scenario, config_a, experiment, arm_id="arm_a", replicate_index=1)
    draft["timing"]["monotonic_duration_ms"] = 999999
    with pytest.raises(ContractError):
        contracts.validate_run_draft_shape(draft)


def test_matrix_changed_id_bytes_rejected() -> None:
    scenario = build_baseline_scenario()
    tampered = dict(scenario)
    tampered["scenario_id"] = "scenario:evaluation_contract_integrity:different_case"
    with pytest.raises(ContractError) as excinfo:
        contracts.validate_scenario_shape(tampered)
    assert any(d.code == "DIGEST_MISMATCH" for d in excinfo.value.defects)


@pytest.mark.parametrize("segment", ["../escape", "CON", "a\x00b", "trailing.", ""])
def test_matrix_symlink_path_traversal_device_name_rejected(segment: str) -> None:
    with pytest.raises(ContractError):
        store._validate_path_segment(segment)


@pytest.mark.parametrize("forbidden_field", ["aggregate", "winner", "route", "policy", "approval"])
def test_matrix_aggregate_winner_route_policy_approval_rejected_on_run(forbidden_field: str) -> None:
    scenario, config_a, _config_b, experiment = _graph()
    run = validity.finalize_run_receipt(
        scenario, config_a, experiment, build_run_draft(scenario, config_a, experiment, arm_id="arm_a", replicate_index=1), **VALIDATOR_KW
    )
    tampered = dict(run)
    tampered[forbidden_field] = "anything"
    with pytest.raises(ContractError) as excinfo:
        contracts.validate_run_shape(tampered)
    assert any(d.code == "UNKNOWN_FIELD" for d in excinfo.value.defects)


def test_matrix_scorer_ref_injected_into_run_rejected() -> None:
    scenario, config_a, _config_b, experiment = _graph()
    run = validity.finalize_run_receipt(
        scenario, config_a, experiment, build_run_draft(scenario, config_a, experiment, arm_id="arm_a", replicate_index=1), **VALIDATOR_KW
    )
    tampered = dict(run)
    tampered["scorer_pass_id"] = "scorer-pass:11111111-1111-4111-8111-111111111111"
    with pytest.raises(ContractError) as excinfo:
        contracts.validate_run_shape(tampered)
    assert any(d.code == "UNKNOWN_FIELD" for d in excinfo.value.defects)


def test_matrix_runner_result_in_draft_rejected() -> None:
    scenario, config_a, _config_b, experiment = _graph()
    draft = build_run_draft(scenario, config_a, experiment, arm_id="arm_a", replicate_index=1)
    draft["pass_fail"] = "PASS"
    with pytest.raises(ContractError) as excinfo:
        contracts.validate_run_draft_shape(draft)
    assert any(d.code == "UNKNOWN_FIELD" for d in excinfo.value.defects)


def test_matrix_forged_validity_rejected() -> None:
    scenario, config_a, _config_b, experiment = _graph()
    run = validity.finalize_run_receipt(
        scenario, config_a, experiment, build_run_draft(scenario, config_a, experiment, arm_id="arm_a", replicate_index=1), **VALIDATOR_KW
    )
    forged = dict(run)
    forged["validity"] = dict(run["validity"])
    forged["validity"]["status"] = "VALID"  # pretend a previously-clean run stays clean after tampering below
    forged["observations"] = dict(run["observations"])
    forged = add_document_digest({k: v for k, v in forged.items() if k != "run_digest"}, "run_digest")
    from scripts.agent_eval.verification import verify_run_graph
    from tests.agent_eval_factories import MemoryArtifactResolver

    resolver = MemoryArtifactResolver.build(scenarios=(scenario,), configurations=(config_a,), experiments=(experiment,))
    result = verify_run_graph(forged, resolver)  # unchanged content -> still recomputes VALID, so this must PASS
    assert result.scope == GRAPH_VERIFIED_SCOPE
    # now actually forge a MISMATCH: mutate content but keep old validity
    truly_forged = dict(run)
    truly_forged["observations"] = dict(run["observations"])
    truly_forged["observations"]["observed_sources"] = list(run["observations"]["observed_sources"])
    truly_forged["observations"]["observed_sources"][0] = dict(truly_forged["observations"]["observed_sources"][0])
    truly_forged["observations"]["observed_sources"][0]["digest"] = "sha256:" + "9" * 64
    truly_forged = add_document_digest({k: v for k, v in truly_forged.items() if k != "run_digest"}, "run_digest")
    from scripts.agent_eval.errors import VerificationContextError

    with pytest.raises(VerificationContextError) as excinfo:
        verify_run_graph(truly_forged, resolver)
    assert any(d.code == "VALIDITY_NOT_RECOMPUTABLE" for d in excinfo.value.defects)


def test_matrix_shape_relabeled_graph_verified_rejected() -> None:
    with pytest.raises(ValueError):
        VerificationResult(scope="SHAPE_VALID", artifact_id="x", artifact_digest="sha256:" + "0" * 64, external_content_unverified_refs=())


def test_matrix_graph_relabeled_content_verified_rejected() -> None:
    with pytest.raises(ValueError):
        VerificationResult(
            scope="EVIDENCE_CONTENT_VERIFIED", artifact_id="x", artifact_digest="sha256:" + "0" * 64, external_content_unverified_refs=()
        )


def test_matrix_missing_resolver_dependency_rejected() -> None:
    from scripts.agent_eval.verification import verify_experiment_graph
    from tests.agent_eval_factories import MemoryArtifactResolver
    from scripts.agent_eval.errors import VerificationContextError

    scenario, config_a, _config_b, experiment = _graph()
    empty_resolver = MemoryArtifactResolver.build()
    with pytest.raises(VerificationContextError):
        verify_experiment_graph(experiment, empty_resolver)


def test_matrix_stale_evidence_counts_rejected() -> None:
    # see also test_agent_eval_scoring.py::test_verify_evidence_ref_graph_fails_on_stale_counts
    scenario, config_a, _config_b, experiment = _graph()
    run = validity.finalize_run_receipt(
        scenario, config_a, experiment, build_run_draft(scenario, config_a, experiment, arm_id="arm_a", replicate_index=1), **VALIDATOR_KW
    )
    scorer_pass = scoring.build_technical_integrity_scorer_pass(
        run, scorer_pass_id="scorer-pass:33333333-3333-4333-8333-333333333333", scorer_code_ref=VALIDATOR_KW["validator_code_ref"], created_at="2026-08-25T00:00:12Z"
    )
    evidence = scoring.summarize_experiment(
        experiment,
        scenario,
        (run,),
        (scorer_pass,),
        evidence_ref_id="evidence-ref:44444444-4444-4444-8444-444444444444",
        intended_owner="person:sol",
        review_at="2026-08-26T00:00:00Z",
        created_at="2026-08-25T00:00:13Z",
        analysis_version="mastermind.agent_evaluation_r0_analysis.v1",
    )
    tampered = dict(evidence)
    tampered["counts"] = dict(evidence["counts"])
    tampered["counts"]["valid_count"] = 999
    with pytest.raises(ContractError) as excinfo:
        scoring.validate_evidence_ref_shape(tampered)
    assert any(d.code == "COUNT_MISMATCH" for d in excinfo.value.defects)


def test_matrix_mutable_run_index_never_required_for_resolution(tmp_path) -> None:
    scenario, config_a, config_b, experiment = _graph()
    artifact_store = store.ArtifactStore(tmp_path / "root")
    artifact_store.create(scenario)
    artifact_store.create(config_a)
    artifact_store.create(config_b)
    artifact_store.create(experiment)
    run = validity.finalize_run_receipt(
        scenario, config_a, experiment, build_run_draft(scenario, config_a, experiment, arm_id="arm_a", replicate_index=1), **VALIDATOR_KW
    )
    artifact_store.create(run)
    # a BRAND NEW ArtifactStore instance (no shared state, no cache, no
    # index) over the same root resolves the run identically -- resolution
    # is a pure function of the schema-derived path, never a mutable index.
    reopened = store.ArtifactStore(artifact_store.root)
    assert reopened.resolve_run(run["run_id"]) == run


# ---------------------------------------------------------------------------
# 4. Changed-path fence
# ---------------------------------------------------------------------------

ALLOWED_PATHS = frozenset(
    {
        "scripts/agent_eval/__init__.py",
        "scripts/agent_eval/errors.py",
        "scripts/agent_eval/canonical.py",
        "scripts/agent_eval/contracts.py",
        "scripts/agent_eval/resolver.py",
        "scripts/agent_eval/verification.py",
        "scripts/agent_eval/validity.py",
        "scripts/agent_eval/store.py",
        "scripts/agent_eval/scoring.py",
        "scripts/agent_eval/cli.py",
        "scripts/agent_eval/privacy.py",  # amendment §4.2 addition
        "scripts/agent_evaluation.py",
        "tests/agent_eval_factories.py",
        "tests/test_agent_eval_canonical.py",
        "tests/test_agent_eval_contracts.py",
        "tests/test_agent_eval_verification.py",
        "tests/test_agent_eval_validity.py",
        "tests/test_agent_eval_store.py",
        "tests/test_agent_eval_scoring.py",
        "tests/test_agent_eval_cli.py",
        "tests/test_agent_eval_inertness.py",
        "tests/test_agent_eval_privacy.py",  # amendment §4.2 addition
        "tests/fixtures/agent_eval/README.md",
        # --- EVAL-C0 fence ratchet (principal-authorized 2026-09-01,
        # operation mastermind-agent-evaluation-c0-corpus-20260901-fable-001)
        "docs/superpowers/plans/2026-09-01-agent-evaluation-c0-corpus.md",
        "scripts/agent_eval/corpus.py",
        "tests/test_agent_eval_corpus.py",
        # --- EVAL-S1 fence ratchet (principal-authorized 2026-09-01,
        # operation mastermind-agent-evaluation-s1-scorers-20260901-fable-001):
        # deterministic task-class scorers + multi-scenario summarization.
        # scoring.py/cli.py above already carry this wave's smallest-surface
        # edits; these are S1's own new, additive files.
        "docs/superpowers/plans/2026-09-01-agent-evaluation-s1-scorers.md",
        "scripts/agent_eval/tc1_source_comprehension.py",
        "scripts/agent_eval/tc2_implementation_fence.py",
        "scripts/agent_eval/tc3_protocol_compliance.py",
        "tests/test_agent_eval_s1_scorers.py",
        "tests/test_agent_eval_s1_multi_scenario_summarize.py",
        # --- EVAL-OHF2 fence ratchet (principal-authorized 2026-09-01,
        # operation mastermind-agent-evaluation-ohf2-integration-20260901-
        # fable-001): the OHF-to-R0 bridge. Additive; imports nothing from
        # scripts.ohf.* (verified by this same file's AST fence, which
        # parametrizes over scripts/agent_eval/*.py automatically -- no
        # separate fence edit needed for ohf_bridge.py itself).
        "docs/superpowers/plans/2026-09-01-agent-evaluation-ohf2-integration.md",
        "scripts/agent_eval/ohf_bridge.py",
        "tests/test_agent_eval_ohf_bridge.py",
        # review repair MAJOR-2 (same operation key): one committed,
        # harness-written real-bytes fixture (plan record §9/§11).
        "tests/fixtures/agent_eval_ohf_bridge/README.md",
        "tests/fixtures/agent_eval_ohf_bridge/MANIFEST.json",
        "tests/fixtures/agent_eval_ohf_bridge/runs/control-1.0.0/S2/1cdaa1b19b584d50ba012dc3910637eb.md",
        # --- EVAL-E1 fence ratchet (principal-authorized 2026-09-01,
        # operation mastermind-agent-evaluation-e1-prereg-20260901-fable-001):
        # RECORDS ONLY paired-pilot preregistration -- a new additive shape
        # validator, its committed sealed record, and this wave's own plan
        # record. Executes nothing (tests/test_agent_eval_prereg.py's own
        # inertness section, plus the shared AST/subprocess fence above,
        # which parametrizes over prereg.py automatically -- no separate
        # fence edit needed for prereg.py itself).
        "docs/superpowers/plans/2026-09-01-agent-evaluation-e1-preregistration.md",
        "scripts/agent_eval/prereg.py",
        "tests/test_agent_eval_prereg.py",
        "experiments/agent_eval/e1/preregistration.json",
        # A2 exact-path repair, recovery-principal authorized 2026-09-17:
        # harness-convergence-a2-boundary-repair-20260917-sol-001 / PR #692.
        # The host bridge is OUTSIDE the inert core. This adds no core import
        # exception and removes no core discovery. Its tests retain this
        # program's fence and cover the bridge's closed pure-owner closure.
        "scripts/agent_eval_host_factor_lock.py",
        "tests/test_agent_eval_host_factor_lock.py",
        "docs/superpowers/plans/2026-09-17-agent-eval-host-factor-boundary-repair.md",
        # H1/H2 provider-free evidence-contract ratchet. Exact paths only;
        # no control-plane/config/workflow/provider-execution authority.
        "docs/superpowers/plans/2026-09-19-agent-eval-h1-h2-provider-free-vertical.md",
        "evidence/CHAIRMAN_C2_RULING_AND_SELF_REVIEW.md",
        "scripts/agent_eval/harness_convergence.py",
        "tests/test_agent_eval_harness_convergence.py",
        # Harness2 evidence-only extension: direct Chairman integration
        # commission 2026-10-21. Exact files only; no new execution scope.
        "docs/superpowers/plans/2026-10-21-harness2-agentos-native-adaptation.md",
        "scripts/agent_eval/harness2_bridge.py",
        "tests/test_agent_eval_harness2_bridge.py",
        # Same Chairman-authorized Harness2/1663 continuation: pure byte-bound
        # importer plus tests. Runtime/provider/config restrictions stay intact.
        "scripts/agent_eval/harness2_native.py",
        "tests/test_agent_eval_harness2_native.py",
        "scripts/agent_eval/harness2_context.py",
        "tests/test_agent_eval_harness2_context.py",
        # Same PR1663 native-method laboratory extension. The callback-based
        # runner stays OUTSIDE the inert core; no provider/runtime import is
        # admitted inside scripts/agent_eval and no control-plane file changes.
        "scripts/ohf/harness2_recursion.py",
        "tests/test_agent_eval_harness2_recursion.py",
        # Pro-turn conformance extension, Chairman-authorized 2026-09-17,
        # operation pro-turn-conformance-corpus-20260917-sol-001.
        "docs/superpowers/plans/2026-09-17-pro-turn-conformance-corpus.md",
        "tests/test_agent_eval_pro_turn_corpus.py",
        # Chairman Hermes teammate commission, 2026-11-06/07; PR #2234.
        # Frozen native input binding and incomplete-attempt accounting.
        # Exact EVAL-owned paths trigger the fence; shared owner connections
        # below are contextual allowances, not additional program ownership.
        "integrations/hermes_runtime/native_eval_inputs.py",
        "integrations/hermes_runtime/tests/test_native_eval_inputs.py",
        "integrations/hermes_runtime/native_eval_publication.py",
        "integrations/hermes_runtime/tests/test_native_eval_publication.py",
        "integrations/hermes_runtime/native_eval_operator.py",
        "integrations/hermes_runtime/tests/test_native_eval_operator.py",
        "docs/hermes/NATIVE_EVAL_INPUT_SELECTION.md",
        "integrations/hermes_qualification/native_eval_inputs/README.md",
        "integrations/hermes_qualification/native_eval_inputs/UPSTREAM_LICENSE",
        "integrations/hermes_qualification/native_eval_inputs/__init__.py",
        "integrations/hermes_qualification/native_eval_inputs/guard.patch",
        "integrations/hermes_qualification/native_eval_inputs/manifest.json",
        "integrations/hermes_qualification/native_eval_inputs/qualify.py",
        "integrations/hermes_runtime/tests/fixtures/native_eval_inputs/agent__reasoning_effort.py.source",
        "integrations/hermes_runtime/tests/fixtures/native_eval_inputs/hermes_cli__runtime_provider.py.source",
        "integrations/hermes_runtime/tests/fixtures/native_eval_inputs/hermes_cli__runtime_provider_custom.py.source",
        "integrations/hermes_runtime/tests/fixtures/native_eval_inputs/hermes_state_mutation_retirement.py.source",
        "integrations/hermes_runtime/tests/fixtures/native_eval_inputs/hermes_state_runtime.py.source",
        "integrations/hermes_runtime/tests/fixtures/native_eval_inputs/hermes_state_common.py.source",
        "integrations/hermes_runtime/tests/fixtures/native_eval_inputs/hermes_state_schema.py.source",
        "integrations/hermes_runtime/tests/fixtures/native_eval_inputs/legacy_marker_v1.json",
        "integrations/hermes_runtime/tests/fixtures/native_eval_inputs/plugins__model-providers__custom____init__.py.source",
        "integrations/hermes_runtime/tests/fixtures/native_eval_inputs/provenance.json",
        "integrations/hermes_runtime/tests/fixtures/native_eval_inputs/providers__base.py.source",
        "docs/HERMES_NATIVE_EVAL_RUN_V2.md",
        "tests/test_agent_eval_run_v2.py",
        "scripts/agent_eval/hermes_memory_grounding.py",
    }
)

# EVAL-C0 fence ratchet (principal-authorized 2026-09-01, operation
# mastermind-agent-evaluation-c0-corpus-20260901-fable-001): this is the
# deliberate per-wave surface ratchet -- each wave's OWNED paths are added
# to this fence only by explicit principal authorization, never by the
# wave's own worker unilaterally widening its own gate. C0's corpus tree
# (``corpus/agent_eval/``) grows case-by-case across this and future
# C0-lineage waves without renaming any script or test, so it established
# the bounded corpus-prefix mechanism rather than an ever-growing file list.
# The Chairman-authorized Pro-turn extension (2026-09-17, operation
# pro-turn-conformance-corpus-20260917-sol-001) adds the second corpus prefix
# while reusing the same filename/type guard below. Any further widening
# still needs explicit principal authorization and its own operation citation.
ALLOWED_PATH_PREFIXES = frozenset({"corpus/agent_eval/", "corpus/agent_eval_pro_turns/"})

# Same native commission, original owners only. This finite connection set
# is deliberately excluded from PROGRAM_SURFACE_PATHS: an unrelated Hermes
# change must not become an EVAL wave just because it touches a shared owner.
# No imports, forbidden prefixes, dependency paths, or workflow exceptions.
NATIVE_EVAL_INTEGRATION_PATHS = frozenset({
    "integrations/hermes_runtime/native_request_observation.py",
    "integrations/hermes_runtime/native_transport_observation.py",
    "integrations/hermes_runtime/native_session_control.py",
    "integrations/hermes_runtime/tests/test_native_session_control.py",
    "tests/test_hermes_isolated_entry.py",
    "integrations/hermes_runtime/native_agentos_memory.py",
    "integrations/hermes_runtime/native_gateway_entry.py",
    "integrations/hermes_runtime/install.py",
    "integrations/hermes_runtime/supervisor.py",
    "integrations/hermes_runtime/cli.py",
    "integrations/hermes_harness/native_byok.py",
    "ops/executive_os/release_manifest.py",
    "ops/executive_os/native_gateway_sources.py",
    "scripts/enroll_linux_secondary_worker.py",
    # Assigned-principal §55 amendment, existing sol/hermes-native-eval-inputs-20261107-c3:
    # git:mastermindx-market-intelligence/Mastermind@d78673689ecd381fb9241c87626518f7460484e0
    # research/HERMES_TEAMMATE_EVOLUTION_MASTERPLAN_2026-11-06.md
    "tests/test_linux_secondary_worker_enrollment.py",
    "tests/executive_fabric_release_identity_review.py",
    "ops/hermes_egress/squid.conf",
    "ops/hermes_egress/README.md",
    "ops/hermes_egress/tests/test_proxy_policy.py",
})

# NB-8 repair: a prefix in ALLOWED_PATH_PREFIXES is NOT a blanket allowance
# for any file type dropped under that tree -- admission is further
# constrained to the corpus law's own known filenames
# (scripts/agent_eval/corpus.py / the C0 plan record's §2 corpus-home
# layout): a scenario document, a holdout seal, the corpus manifest, a
# fixture JSON file, or a corpus README. An unexpected extension, a stray
# script, or a non-JSON fixture living under the prefix is still refused.
_CORPUS_TREE_ALLOWED_BASENAMES = frozenset({"scenario.json", "holdout_seal.json", "corpus_manifest.json", "README.md"})


def _corpus_prefix_path_is_allowed(path: str, prefix: str) -> bool:
    suffix = path[len(prefix):]
    parts = suffix.split("/")
    basename = parts[-1]
    if basename in _CORPUS_TREE_ALLOWED_BASENAMES:
        return True
    return len(parts) >= 2 and parts[-2] == "fixtures" and basename.endswith(".json")


def _changed_path_is_allowed(path: str) -> bool:
    if path in ALLOWED_PATHS or path in NATIVE_EVAL_INTEGRATION_PATHS:
        return True
    for prefix in ALLOWED_PATH_PREFIXES:
        if path.startswith(prefix) and _corpus_prefix_path_is_allowed(path, prefix):
            return True
    return False


# ---------------------------------------------------------------------------
# 4.0 Fence scoping (principal-authorized 2026-09-01, operation
# mastermind-agent-evaluation-fence-scoping-20260901-fable-001)
#
# The changed-path fence above was born as this program's OWN-wave
# assertion, but it runs repo-wide: any CI job that selects this test file
# (ci_pytest selection) diffs the WHOLE PR against origin/master and fences
# it against OUR ALLOWED_PATHS -- including a PR that never touches
# agent_eval at all. Measured: Mastermind PR #162 (run 33540139880) failed
# ``test_changed_paths_are_within_the_allowed_r0_surface`` on its own four
# legitimate, wholly-unrelated paths (two 2026-08-26 OHF records,
# scripts/ohf/fresh_sol_eval.py, tests/test_fresh_sol_eval.py) -- a fence
# meant to police THIS program's own waves became an accidental repo-wide
# gate on every PR that happens to run this test file.
#
# Repair: the fence is now SELF-SCOPING. It applies (enforces the strict
# whole delta within owned paths, exact shared connections, and constrained
# corpus paths; ratchet discipline unchanged) only
# when the PR's OWN delta touches at least one path under this program's
# surface. A delta touching NONE of it is simply not this program's
# business -- not-applicable, never failed. Shared native connections alone
# never trigger applicability; only the EVAL-owned set defines that boundary.
# ---------------------------------------------------------------------------

#: The frozen, minimal prefix set naming "this is unambiguously an
#: agent_eval program file" without hand-enumerating every individual
#: file. A future in-program file under one of these prefixes is
#: correctly classified as program-surface even before it is
#: ratchet-added to ALLOWED_PATHS -- it is still refused by the strict
#: allowlist check below (ratchet discipline is unchanged), it is simply
#: no longer misclassified as "foreign."
#:
#: Applicability repair, 2026-11-05 (root/parent
#: mastermind-queue-clearance-20261104-c1, commission
#: pr798-corpus-applicability-repair-20261105-c1, original PR #798): the
#: Pro-turn corpus prefix admitted by ALLOWED_PATH_PREFIXES above is ALSO
#: program surface. Without this entry a delta whose only paths were under
#: ``corpus/agent_eval_pro_turns/`` was classified "not applicable", so BOTH
#: real fence entry points skipped before the allowlist check and the
#: forbidden-surface check were ever applied to that corpus -- a standalone
#: new-prefix delta escaped both fences. Membership here does not widen the
#: allowlist: the filename/type guard, the strict allowlist check and the
#: forbidden-surface rule are all unchanged.
PROGRAM_SURFACE_PREFIXES = frozenset({"scripts/agent_eval/", "corpus/agent_eval/", "corpus/agent_eval_pro_turns/", "tests/test_agent_eval_"})

#: DERIVED from ALLOWED_PATHS (never hand-duplicated) for the small number
#: of program files that don't fall under any prefix above: the top-level
#: CLI entrypoint (``scripts/agent_evaluation.py``), the test factories
#: module (``tests/agent_eval_factories.py``), the fixture README, and the
#: program's own plan records. A future ratchet addition to ALLOWED_PATHS
#: that doesn't match a PROGRAM_SURFACE_PREFIXES prefix is automatically
#: program-surface too -- no second edit, no drift risk between the two
#: sets.
PROGRAM_SURFACE_PATHS = frozenset(
    path for path in ALLOWED_PATHS if not any(path.startswith(prefix) for prefix in PROGRAM_SURFACE_PREFIXES)
)


def _is_program_surface_path(path: str) -> bool:
    if path in PROGRAM_SURFACE_PATHS:
        return True
    return any(path.startswith(prefix) for prefix in PROGRAM_SURFACE_PREFIXES)


def _fence_not_applicable_reason(changed: set[str]) -> str | None:
    """``None`` when the fence applies (the delta touches at least one
    program-surface path); otherwise a clear, printable not-applicable
    reason string naming the exact delta -- shared by both real fence
    tests below and their synthetic-repo regressions."""
    if any(_is_program_surface_path(path) for path in changed):
        return None
    return (
        "PASS (not applicable): this PR's delta touches none of the agent_eval program "
        f"surface, so this program's changed-path fence does not apply to it -- delta: {sorted(changed)}"
    )


def _run_git(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], capture_output=True, text=True, cwd=str(cwd), timeout=30)


def _queue_single_pr_parent(repo_dir: Path, head: str, parent_shas: list[str]) -> str | None:
    """Use only an authenticated, single-appended-PR merge-group commit boundary.

    GitHub's queue can include earlier queued PRs in the *parent*. For the
    squash/linear candidate whose commit names the current PR, the parent-to-
    head diff is the candidate's complete appended change, not all earlier
    pending PRs. An unqualified or multi-PR-shaped candidate FAILS CLOSED.
    """
    if os.environ.get("GITHUB_EVENT_NAME") != "merge_group" or repo_dir.resolve() != ROOT.resolve():
        # Synthetic local Git tests and other caller-supplied repos must not
        # inherit the runner's real merge-group event. Test-of-test fixtures
        # explicitly bind their own isolated ROOT to qualify this path.
        return None
    if len(parent_shas) != 1:
        raise AssertionError("merge-group single-PR fence needs exactly one parent")
    source = os.environ.get("GITHUB_EVENT_PATH")
    if not source:
        raise AssertionError("merge-group event payload is unavailable")
    try:
        event = json.loads(Path(source).read_text(encoding="utf-8"))
        if not isinstance(event, dict):
            raise ValueError("merge-group event must be an object")
        group = event["merge_group"]
    except (OSError, UnicodeError, ValueError, KeyError, TypeError) as exc:
        raise AssertionError("merge-group event payload unreadable/invalid") from exc
    if event.get("action") != "checks_requested" or not isinstance(group, dict):
        raise AssertionError("unexpected merge-group action or payload")
    actual = _run_git(["rev-parse", head], repo_dir)
    if actual.returncode or not re.fullmatch(r"[0-9a-f]{40}", actual.stdout.strip()):
        raise AssertionError("cannot resolve merge-group source HEAD")
    resolved_head = actual.stdout.strip()
    ref = group.get("head_ref")
    match = re.fullmatch(
        r"refs/heads/gh-readonly-queue/master/pr-([1-9][0-9]*)-([0-9a-f]{40})",
        ref if isinstance(ref, str) else "",
    )
    if not match:
        raise AssertionError("merge-group ref is not a single PR queue ref")
    number, predecessor = match.groups()
    if (group.get("head_sha") != resolved_head
            or os.environ.get("GITHUB_SHA") != resolved_head
            or os.environ.get("GITHUB_REF") != ref
            or group.get("base_ref") != "refs/heads/master"
            or group.get("base_sha") != parent_shas[0]
            or predecessor != parent_shas[0]):
        raise AssertionError("merge-group event/head/ref/predecessor identity drift")
    subject = _run_git(["show", "-s", "--format=%s", head], repo_dir)
    if subject.returncode:
        raise AssertionError("cannot read merge-group candidate subject")
    if re.findall(r"\(#([1-9][0-9]*)\)", subject.stdout) != [number]:
        raise AssertionError("merge-group candidate is not one attributable PR commit")
    return parent_shas[0]


def compute_pr_diff_paths(repo_dir: Path, *, head: str = "HEAD", upstream: str = "origin/master") -> set[str]:
    """The effective PR delta, merge-ref-safe -- never a pinned base SHA.

    A pinned base SHA goes stale the moment the real base branch moves past
    it: hosted CI checks out a synthetic MERGE commit (the PR branch merged
    with the CURRENT base), so diffing against a base captured at pickup
    time counts every commit the base gained afterward as "PR changes" --
    this is exactly what broke CI run 33509507599 (a same-day master
    release landed docs/records the pinned-base diff then blamed on this
    PR).

    Fixed rule: if HEAD is a merge commit (has 2+ parents), the effective
    delta is what the merge introduced relative to its FIRST parent
    (``HEAD^1..HEAD``) -- under a hosted merge-ref checkout, parent 1 is the
    base branch tip at merge time and parent 2 is this PR's own tip, so this
    diff is exactly the PR's own changes regardless of how far the base has
    moved. An authenticated GitHub merge_group may instead use a *linear*
    single-PR squash commit on top of an earlier queued candidate, even when
    that predecessor has not reached origin/master. The exact native event,
    head/ref/first-parent relationship and sole PR-number commit marker must
    agree before the fence uses the candidate's own parent. Other linear
    heads (ordinary local/PR development) retain the original conservative
    ``merge-base(upstream, head)..head`` behavior. An unknown queue identity
    raises instead of silently passing or blaming other pending PRs.
    """
    parents_result = _run_git(["rev-list", "--parents", "-n", "1", head], repo_dir)
    if parents_result.returncode != 0:
        raise AssertionError(f"git rev-list failed: {parents_result.stderr}")
    tokens = parents_result.stdout.split()
    parent_shas = tokens[1:]  # tokens[0] is `head` itself
    if len(parent_shas) >= 2:
        base_ref = f"{head}^1"
    else:
        # A queue's linear squash commit can have a *preceding queued PR*
        # as its sole parent. merge-base(origin/master, HEAD) would falsely
        # attribute all that predecessor's changes to the appended EVAL PR.
        # Only the native, exact-identity, single-PR event permits HEAD^1.
        queue_parent = _queue_single_pr_parent(repo_dir, head, parent_shas)
        if queue_parent is not None:
            base_ref = queue_parent
        else:
            merge_base_result = _run_git(["merge-base", upstream, head], repo_dir)
            if merge_base_result.returncode != 0:
                raise AssertionError(f"git merge-base failed: {merge_base_result.stderr}")
            base_ref = merge_base_result.stdout.strip()
    diff_result = _run_git(["diff", "--name-only", base_ref, head], repo_dir)
    if diff_result.returncode != 0:
        raise AssertionError(f"git diff failed: {diff_result.stderr}")
    return {line.strip() for line in diff_result.stdout.splitlines() if line.strip()}


def test_changed_paths_are_within_the_allowed_r0_surface() -> None:
    changed = compute_pr_diff_paths(ROOT)
    not_applicable_reason = _fence_not_applicable_reason(changed)
    if not_applicable_reason is not None:
        pytest.skip(not_applicable_reason)
    unexpected = {path for path in changed if not _changed_path_is_allowed(path)}
    assert not unexpected, f"changed path(s) outside the allowed R0 surface: {sorted(unexpected)}"


def test_no_control_plane_config_dependency_or_workflow_file_touched() -> None:
    changed = compute_pr_diff_paths(ROOT)
    not_applicable_reason = _fence_not_applicable_reason(changed)
    if not_applicable_reason is not None:
        pytest.skip(not_applicable_reason)
    forbidden_prefixes = ("control_plane/", ".github/workflows/", "config/", "pyproject.toml", "requirements")
    for path in changed:
        assert not path.startswith(forbidden_prefixes), f"unexpected control-plane/config/workflow change: {path}"


@pytest.mark.parametrize(
    "fence_test",
    [
        test_changed_paths_are_within_the_allowed_r0_surface,
        test_no_control_plane_config_dependency_or_workflow_file_touched,
    ],
    ids=["allowed_surface_fence", "forbidden_surface_fence"],
)
def test_empty_delta_is_not_applicable_for_real_fences(monkeypatch, fence_test) -> None:
    """An empty protected-master delta is not this program's business.

    Exercise the real fence entry points, not only the classifier helper, so
    a premature non-empty assertion cannot regress ahead of self-scoping.
    """
    monkeypatch.setattr(sys.modules[__name__], "compute_pr_diff_paths", lambda _repo: set())
    with pytest.raises(pytest.skip.Exception, match="not applicable"):
        fence_test()


# ---------------------------------------------------------------------------
# 4a. Test-of-the-test: compute_pr_diff_paths is merge-ref-safe
# ---------------------------------------------------------------------------
#
# Built entirely inside a synthetic temp git repo (never the real repo
# state) so both branches of the fence's own logic are exercised
# deterministically: the merge-ref case (a hosted-CI-style synthetic merge
# commit) must exclude base-side changes that landed after the PR forked,
# and the ordinary linear-branch case must still catch a real branch-side
# change via merge-base -- proving the repair didn't just make the fence
# permissive.


def _git_init(repo: Path) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    _run_git(["init", "-q", "-b", "master"], repo)
    _run_git(["config", "user.email", "test@example.invalid"], repo)
    _run_git(["config", "user.name", "EVAL-R0 Fence Test"], repo)


def _git_commit_file(repo: Path, relative_path: str, content: str, message: str) -> str:
    target = repo / relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    _run_git(["add", relative_path], repo)
    result = _run_git(["commit", "-q", "-m", message], repo)
    assert result.returncode == 0, result.stderr
    return _run_git(["rev-parse", "HEAD"], repo).stdout.strip()


def test_compute_pr_diff_paths_linear_branch_still_flags_a_branch_side_file(tmp_path: Path) -> None:
    # the ordinary (non-merge-ref) case: a ordinary feature branch head must
    # still be diffed correctly via merge-base against the upstream ref,
    # finding exactly what the branch itself added.
    repo = tmp_path / "linear_repo"
    _git_init(repo)
    _git_commit_file(repo, "README.md", "base\n", "base commit")
    _run_git(["update-ref", "refs/remotes/origin/master", "master"], repo)
    _run_git(["checkout", "-q", "-b", "feature"], repo)
    _git_commit_file(repo, "docs/OUT_OF_SURFACE.md", "not allowed\n", "branch-side out-of-surface file")

    changed = compute_pr_diff_paths(repo, head="HEAD", upstream="origin/master")

    assert changed == {"docs/OUT_OF_SURFACE.md"}  # IS flagged: this is a genuine branch-side change


def test_compute_pr_diff_paths_merge_ref_excludes_base_side_changes_after_fork(tmp_path: Path) -> None:
    # the hosted-CI merge-ref case: base (master) gains an unrelated file
    # AFTER the PR branch forked, then a synthetic merge commit (parent 1 =
    # advanced master, parent 2 = PR branch tip) is built exactly the way a
    # hosted CI merge-ref checkout does it. The fence must NOT blame this PR
    # for the base-side file.
    repo = tmp_path / "merge_repo"
    _git_init(repo)
    _git_commit_file(repo, "README.md", "base\n", "base commit")

    _run_git(["checkout", "-q", "-b", "feature"], repo)
    _git_commit_file(repo, "scripts/agent_eval/pr_only_file.py", "x = 1\n", "the PR's own change")

    _run_git(["checkout", "-q", "master"], repo)
    _git_commit_file(repo, "docs/LATER_RELEASE.md", "landed after PR forked\n", "unrelated same-day master release")
    _run_git(["update-ref", "refs/remotes/origin/master", "master"], repo)

    merge_result = _run_git(["merge", "--no-ff", "-q", "-m", "synthetic hosted-CI merge ref", "feature"], repo)
    assert merge_result.returncode == 0, merge_result.stderr
    merge_head = _run_git(["rev-parse", "HEAD"], repo).stdout.strip()
    parent_count = len(_run_git(["rev-list", "--parents", "-n", "1", merge_head], repo).stdout.split()) - 1
    assert parent_count == 2  # sanity: this really is a 2-parent merge commit

    changed = compute_pr_diff_paths(repo, head=merge_head, upstream="origin/master")

    assert changed == {"scripts/agent_eval/pr_only_file.py"}  # only the PR's own change
    assert "docs/LATER_RELEASE.md" not in changed  # NOT flagged: base-side movement after fork


# ---------------------------------------------------------------------------
# 4b. Tests-of-the-fence: self-scoping (operation
# mastermind-agent-evaluation-fence-scoping-20260901-fable-001)
#
# Four synthetic-repo cases proving the repair fixes PR #162's exact
# failure mode (a) without weakening ratchet discipline for any PR that
# genuinely touches this program's surface (b, c, d).
# ---------------------------------------------------------------------------


def test_fence_scoping_foreign_only_delta_is_not_applicable(tmp_path: Path) -> None:
    """(a) A delta touching ONLY foreign paths -- e.g. PR #162's own shape
    (an OHF script + a doc record), neither of which is anywhere near
    agent_eval -- is not-applicable, never failed. This is the exact bug
    measured on Mastermind PR #162 (run 33540139880)."""
    repo = tmp_path / "foreign_only_repo"
    _git_init(repo)
    _git_commit_file(repo, "README.md", "base\n", "base commit")
    _run_git(["update-ref", "refs/remotes/origin/master", "master"], repo)
    _run_git(["checkout", "-q", "-b", "feature"], repo)
    _git_commit_file(repo, "scripts/ohf/x.py", "x = 1\n", "foreign change")
    _git_commit_file(repo, "docs/record.md", "a record\n", "another foreign change")

    changed = compute_pr_diff_paths(repo, head="HEAD", upstream="origin/master")
    assert changed == {"scripts/ohf/x.py", "docs/record.md"}
    assert _fence_not_applicable_reason(changed) is not None  # PASS/not-applicable


def test_fence_scoping_mixed_delta_still_enforces_the_full_allowlist(tmp_path: Path) -> None:
    """(b) A delta that touches ONE program-surface file plus one
    un-allowlisted foreign file must still FAIL -- touching our program's
    surface at all re-arms the strict whole-delta rule; you cannot smuggle
    an unrelated foreign file in alongside a legitimate program change."""
    repo = tmp_path / "mixed_repo"
    _git_init(repo)
    _git_commit_file(repo, "README.md", "base\n", "base commit")
    _run_git(["update-ref", "refs/remotes/origin/master", "master"], repo)
    _run_git(["checkout", "-q", "-b", "feature"], repo)
    _git_commit_file(repo, "scripts/agent_eval/cli.py", "x = 1\n", "program file, already allowlisted")
    _git_commit_file(repo, "docs/unrelated_foreign.md", "not allowed\n", "un-allowlisted foreign file")

    changed = compute_pr_diff_paths(repo, head="HEAD", upstream="origin/master")
    assert changed == {"scripts/agent_eval/cli.py", "docs/unrelated_foreign.md"}
    assert _fence_not_applicable_reason(changed) is None  # applies -- delta touches program surface
    unexpected = {path for path in changed if not _changed_path_is_allowed(path)}
    assert unexpected == {"docs/unrelated_foreign.md"}  # FAIL


def test_fence_scoping_program_only_delta_within_allowlist_passes(tmp_path: Path) -> None:
    """(c) A delta entirely within the program surface AND fully
    allowlisted passes cleanly -- an ordinary in-program wave, unchanged
    behavior from before this repair."""
    repo = tmp_path / "program_only_repo"
    _git_init(repo)
    _git_commit_file(repo, "README.md", "base\n", "base commit")
    _run_git(["update-ref", "refs/remotes/origin/master", "master"], repo)
    _run_git(["checkout", "-q", "-b", "feature"], repo)
    _git_commit_file(repo, "scripts/agent_eval/cli.py", "x = 1\n", "program file, already allowlisted")

    changed = compute_pr_diff_paths(repo, head="HEAD", upstream="origin/master")
    assert changed == {"scripts/agent_eval/cli.py"}
    assert _fence_not_applicable_reason(changed) is None  # applies
    unexpected = {path for path in changed if not _changed_path_is_allowed(path)}
    assert not unexpected  # PASS


@pytest.mark.parametrize(
    "adjacent_path",
    [
        "scripts/agent_eval/unratcheted_new_module.py",
        "corpus/agent_eval/unratcheted_new_file.json",
        "tests/test_agent_eval_unratcheted_new_module.py",
    ],
    ids=["scripts_agent_eval_prefix", "corpus_agent_eval_prefix", "tests_test_agent_eval_prefix"],
)
def test_fence_scoping_unratcheted_program_adjacent_file_still_fails(tmp_path: Path, adjacent_path: str) -> None:
    """(d) A NEW file that matches a PROGRAM_SURFACE_PREFIXES prefix but
    has not yet been ratchet-added to ALLOWED_PATHS must still FAIL --
    landing under any of this program's own directories is never itself
    authorization; ratchet discipline for in-program waves is completely
    unchanged by this repair.

    Parametrized over ALL THREE PROGRAM_SURFACE_PREFIXES entries, each
    tested ALONE (never alongside an already-allowlisted companion file
    from a DIFFERENT prefix) -- reviewer finding on the first revision of
    this test: pairing every case with ``scripts/agent_eval/cli.py`` made
    ``_fence_not_applicable_reason`` return "applies" via that companion
    file regardless of whether the ``tests/`` or ``corpus/`` prefix itself
    still matched anything, so silently dropping either of those two
    entries from ``PROGRAM_SURFACE_PREFIXES`` would have shipped green.
    Testing each adjacent path completely alone means "applies" can only
    be true because THAT prefix specifically still matches -- a dropped
    prefix flips its own case to skip-as-not-applicable and this
    parametrized test catches it."""
    repo = tmp_path / f"adjacent_repo_{adjacent_path.replace('/', '_')}"
    _git_init(repo)
    _git_commit_file(repo, "README.md", "base\n", "base commit")
    _run_git(["update-ref", "refs/remotes/origin/master", "master"], repo)
    _run_git(["checkout", "-q", "-b", "feature"], repo)
    _git_commit_file(repo, adjacent_path, "x = 1\n", "NEW program-adjacent file, not yet ratchet-authorized")

    changed = compute_pr_diff_paths(repo, head="HEAD", upstream="origin/master")
    assert changed == {adjacent_path}
    # applies purely because THIS path matches its own PROGRAM_SURFACE_
    # PREFIXES entry -- if that specific prefix were ever dropped, this
    # assertion is exactly what would flip to "not applicable" instead.
    assert _fence_not_applicable_reason(changed) is None
    unexpected = {path for path in changed if not _changed_path_is_allowed(path)}
    assert unexpected == {adjacent_path}  # FAIL: not yet ratchet-authorized


# ---------------------------------------------------------------------------
# 4c. Native GitHub merge-group appended-PR range: incident #1939
# ---------------------------------------------------------------------------
#
# Earlier queued PRs are part of a native queue candidate's FIRST PARENT.
# A one-parent squash commit appended on that parent is not an ordinary local
# branch. Scope only that proven appended PR; do not make arbitrary HEAD^
# selection available to ordinary PRs or caller-supplied repositories.

def _synthetic_r0_queue(
    tmp_path: Path, monkeypatch, *,
    candidate_subject: str = "fix(eval-r0): safe store open (#1939)",
    forbidden: bool = False,
) -> tuple[Path, Path, str, str]:
    repo = tmp_path / "native_queue"
    _git_init(repo)
    base = _git_commit_file(repo, "README.md", "initial\n", "accepted base")
    _run_git(["update-ref", "refs/remotes/origin/master", base], repo)
    predecessor = _git_commit_file(
        repo, ".github/workflows/hermes-harness.yml",
        "name: prior queue workflow\n", "feat(hermes): preceding queue candidate (#1850)",
    )
    # The queue ref's SHA suffix is its previous candidate, not original
    # protected master. At the historical failure this predecessor had not
    # yet reached origin/master.
    ref = f"refs/heads/gh-readonly-queue/master/pr-1939-{predecessor}"
    assert _run_git(["checkout", "-q", "-b", ref.removeprefix("refs/heads/")], repo).returncode == 0
    changed = repo / "scripts/agent_eval/store.py"
    changed.parent.mkdir(parents=True, exist_ok=True)
    changed.write_text("create_root = False\n", encoding="utf-8")
    assert _run_git(["add", "scripts/agent_eval/store.py"], repo).returncode == 0
    if forbidden:
        outside = repo / "control_plane/bypass.py"
        outside.parent.mkdir(parents=True, exist_ok=True)
        outside.write_text("EVAL fence must reject this\n", encoding="utf-8")
        assert _run_git(["add", "control_plane/bypass.py"], repo).returncode == 0
    commit = _run_git(["commit", "-q", "-m", candidate_subject], repo)
    assert commit.returncode == 0, commit.stderr
    head = _run_git(["rev-parse", "HEAD"], repo).stdout.strip()
    event = {
        "action": "checks_requested",
        "merge_group": {
            "head_ref": ref,
            "head_sha": head,
            "base_ref": "refs/heads/master",
            "base_sha": predecessor,
        },
    }
    event_path = tmp_path / "native-queue-event.json"
    event_path.write_text(json.dumps(event), encoding="utf-8")
    monkeypatch.setattr(sys.modules[__name__], "ROOT", repo)
    monkeypatch.setenv("GITHUB_EVENT_NAME", "merge_group")
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event_path))
    monkeypatch.setenv("GITHUB_SHA", head)
    monkeypatch.setenv("GITHUB_REF", ref)
    return repo, event_path, head, predecessor


def test_native_queue_1939_excludes_predecessor_hermes_and_keeps_store_fence(
    tmp_path: Path, monkeypatch,
) -> None:
    repo, _, head, predecessor = _synthetic_r0_queue(tmp_path, monkeypatch)
    assert len(_run_git(["rev-list", "--parents", "-n", "1", head], repo).stdout.split()) == 2
    # The *old* branch-style merge-base comparison reproduces 41931657412.
    first_base = _run_git(["merge-base", "origin/master", head], repo).stdout.strip()
    old_paths = _run_git(["diff", "--name-only", first_base, head], repo).stdout.splitlines()
    assert ".github/workflows/hermes-harness.yml" in old_paths
    assert predecessor != first_base

    changed = compute_pr_diff_paths(repo)
    assert changed == {"scripts/agent_eval/store.py"}
    assert _fence_not_applicable_reason(changed) is None
    assert not {name for name in changed if not _changed_path_is_allowed(name)}
    assert not {name for name in changed if name.startswith(("control_plane/", ".github/workflows/", "config/"))}


def test_native_queue_r0_mixed_forbidden_candidate_still_fails(
    tmp_path: Path, monkeypatch,
) -> None:
    repo, _, _, _ = _synthetic_r0_queue(tmp_path, monkeypatch, forbidden=True)
    changed = compute_pr_diff_paths(repo)
    assert changed == {"scripts/agent_eval/store.py", "control_plane/bypass.py"}
    assert _fence_not_applicable_reason(changed) is None
    with pytest.raises(AssertionError, match="outside the allowed R0 surface"):
        test_changed_paths_are_within_the_allowed_r0_surface()
    with pytest.raises(AssertionError, match="unexpected control-plane/config"):
        test_no_control_plane_config_dependency_or_workflow_file_touched()


@pytest.mark.parametrize(
    "fault",
    [
        "missing_event", "bad_action", "wrong_head_sha", "wrong_base_sha",
        "wrong_ref", "wrong_env_sha", "wrong_env_ref",
        "wrong_subject", "multiple_pr_markers",
    ],
)
def test_native_queue_missing_or_ambiguous_identity_fails_closed(
    tmp_path: Path, monkeypatch, fault: str,
) -> None:
    subject = (
        "unattributed queue candidate"
        if fault == "wrong_subject" else
        "merge (#1939) (#2001)"
        if fault == "multiple_pr_markers" else
        "fix(eval-r0): safe store open (#1939)"
    )
    repo, event_path, _, _ = _synthetic_r0_queue(
        tmp_path, monkeypatch, candidate_subject=subject,
    )
    event = json.loads(event_path.read_text())
    if fault == "missing_event":
        monkeypatch.delenv("GITHUB_EVENT_PATH")
    elif fault == "bad_action":
        event["action"] = "destroyed"
    elif fault == "wrong_head_sha":
        event["merge_group"]["head_sha"] = "0" * 40
    elif fault == "wrong_base_sha":
        event["merge_group"]["base_sha"] = "0" * 40
    elif fault == "wrong_ref":
        event["merge_group"]["head_ref"] = "refs/heads/feature"
    elif fault == "wrong_env_sha":
        monkeypatch.setenv("GITHUB_SHA", "0" * 40)
    elif fault == "wrong_env_ref":
        monkeypatch.setenv("GITHUB_REF", "refs/heads/feature")
    event_path.write_text(json.dumps(event), encoding="utf-8")
    with pytest.raises(AssertionError, match="merge-group"):
        compute_pr_diff_paths(repo)


def test_native_queue_identity_not_inherited_by_unrelated_synthetic_repo(
    tmp_path: Path, monkeypatch,
) -> None:
    repo, _, _, _ = _synthetic_r0_queue(tmp_path, monkeypatch)
    # Another test's local Git fixture must NOT inherit a real Actions queue
    # event just because all tests run under GITHUB_EVENT_NAME=merge_group.
    unrelated = tmp_path / "other_git_repo"
    _git_init(unrelated)
    base = _git_commit_file(unrelated, "README.md", "base\n", "base")
    _run_git(["update-ref", "refs/remotes/origin/master", base], unrelated)
    _git_commit_file(unrelated, "docs/unrelated.md", "unrelated\n", "ordinary branch")
    assert compute_pr_diff_paths(unrelated) == {"docs/unrelated.md"}


def test_ordinary_branch_conservatively_includes_inherited_queue_delta(
    tmp_path: Path, monkeypatch,
) -> None:
    repo, _, _, _ = _synthetic_r0_queue(tmp_path, monkeypatch)
    monkeypatch.delenv("GITHUB_EVENT_NAME")
    changed = compute_pr_diff_paths(repo)
    assert changed == {
        ".github/workflows/hermes-harness.yml",
        "scripts/agent_eval/store.py",
    }
    assert {"scripts/agent_eval/store.py"} <= changed


# ---------------------------------------------------------------------------
# 4d. Pro-turn corpus prefix: narrow ratchet + applicability regressions
# ---------------------------------------------------------------------------
#
# Commission pr798-corpus-applicability-repair-20261105-c1 (root/parent
# mastermind-queue-clearance-20261104-c1), original PR #798.
#
# The original #798 ratchet admitted the ``corpus/agent_eval_pro_turns/``
# prefix through ALLOWED_PATH_PREFIXES (with the corpus law's own
# filename/type guard) but never made that prefix PROGRAM SURFACE. A delta
# whose only paths were under the new prefix was therefore classified
# "not applicable" and BOTH real fence entry points skipped before they
# evaluated it -- so neither the allowlist rule nor the forbidden-surface
# rule was ever applied to that corpus. The original helper-only negative
# control below (a direct ``_changed_path_is_allowed`` call) cannot see
# that defect: it never reaches the real fences.
#
# The regressions below therefore drive the REAL fence entry points against
# REAL temporary Git repositories whose delta contains ONLY the new prefix,
# so no already-recognized companion path can mask applicability, and they
# call the REAL ``compute_pr_diff_paths``. Nothing about changed paths, the
# classifier, the skip decision or an assertion is stubbed. An unexpected
# skip is converted into an assertion failure: a fence that skipped would
# otherwise be indistinguishable from a genuine pass.
#
# The pre-existing standalone-prefix regression in case (d) above covers the
# three original PROGRAM_SURFACE_PREFIXES entries; this section adds the
# Pro-turn prefix under the same "each prefix tested alone" discipline.


def test_pro_turn_conformance_surface_ratchet_is_narrow():
    assert _changed_path_is_allowed("docs/superpowers/plans/2026-09-17-pro-turn-conformance-corpus.md")
    assert _changed_path_is_allowed("tests/test_agent_eval_pro_turn_corpus.py")
    assert _changed_path_is_allowed("corpus/agent_eval_pro_turns/README.md")
    assert _changed_path_is_allowed("corpus/agent_eval_pro_turns/scenarios/carrier_protocol_compliance/healthy_chunk/v1/scenario.json")
    assert _changed_path_is_allowed("corpus/agent_eval_pro_turns/scenarios/carrier_protocol_compliance/healthy_chunk/v1/fixtures/input.json")
    assert not _changed_path_is_allowed("corpus/agent_eval_pro_turns/scenarios/carrier_protocol_compliance/healthy_chunk/v1/payload.py")


_PRO_TURN_PREFIX = "corpus/agent_eval_pro_turns/"


def _standalone_prefix_delta_repo(
    tmp_path: Path, name: str, files: list[tuple[str, str]],
) -> Path:
    """A real Git repository whose ONLY delta is ``files``.

    The base commit holds a single unrelated file and ``origin/master``
    points at it, so the effective PR delta is exactly the new files. No
    already-recognized companion path is present: applicability can never
    be masked by a second, separately allowlisted file.
    """
    repo = tmp_path / name
    _git_init(repo)
    _git_commit_file(repo, "README.md", "base\n", "base commit")
    _run_git(["update-ref", "refs/remotes/origin/master", "master"], repo)
    _run_git(["checkout", "-q", "-b", "feature"], repo)
    for relative_path, content in files:
        _git_commit_file(repo, relative_path, content, "NEW file under the Pro-turn corpus prefix")
    return repo


def _real_fence_outcome(fence_test) -> str:
    """Run a REAL fence entry point; return "PASS" or its failure message.

    A skip is converted into an assertion failure: the real fences skip
    when the delta is classified "not applicable", and such a skip must
    never be reported as a pass (nor accepted as a RED).
    """
    try:
        fence_test()
    except pytest.skip.Exception as exc:
        raise AssertionError(
            "real fence entry point SKIPPED instead of enforcing the changed-path rule: "
            f"{exc}"
        ) from exc
    except AssertionError as exc:
        return f"FAIL: {exc}"
    return "PASS"


def _bind_root_to_private_fixture(monkeypatch, repo: Path) -> None:
    """Bind the fence's ROOT to a private fixture repository.

    This is the same binding the existing #2071 native-queue tests use; it
    does not stub the diff, the classifier, the skip decision or any
    assertion.
    """
    monkeypatch.setattr(sys.modules[__name__], "ROOT", repo)
    monkeypatch.delenv("GITHUB_EVENT_NAME", raising=False)


@pytest.mark.parametrize("owned", [
    "integrations/hermes_runtime/native_eval_inputs.py",
    "integrations/hermes_qualification/native_eval_inputs/manifest.json",
    "tests/test_agent_eval_run_v2.py",
])
def test_native_eval_owned_delta_reaches_real_fences_with_shared_connections(tmp_path, monkeypatch, owned):
    files = [(owned, "fixture\n"), ("integrations/hermes_runtime/supervisor.py", "fixture\n"),
             ("tests/test_linux_secondary_worker_enrollment.py", "fixture\n"),
             ("ops/hermes_egress/squid.conf", "fixture\n")]
    repo = _standalone_prefix_delta_repo(tmp_path, "native_eval_owned", files)
    _bind_root_to_private_fixture(monkeypatch, repo)
    assert _fence_not_applicable_reason(compute_pr_diff_paths(repo)) is None
    assert _real_fence_outcome(test_changed_paths_are_within_the_allowed_r0_surface) == "PASS"
    assert _real_fence_outcome(test_no_control_plane_config_dependency_or_workflow_file_touched) == "PASS"


def test_shared_native_changes_do_not_claim_eval_program_ownership(tmp_path, monkeypatch):
    files = [("integrations/hermes_runtime/supervisor.py", "fixture\n"),
             ("tests/test_linux_secondary_worker_enrollment.py", "fixture\n"),
             ("ops/hermes_egress/squid.conf", "fixture\n"),
             ("integrations/hermes_runtime/unrelated_hermes_owner.py", "fixture\n")]
    repo = _standalone_prefix_delta_repo(tmp_path, "shared_native_only", files)
    _bind_root_to_private_fixture(monkeypatch, repo)
    changed = compute_pr_diff_paths(repo)
    assert _fence_not_applicable_reason(changed) is not None
    assert not (NATIVE_EVAL_INTEGRATION_PATHS & PROGRAM_SURFACE_PATHS)
    for fence in (test_changed_paths_are_within_the_allowed_r0_surface,
                  test_no_control_plane_config_dependency_or_workflow_file_touched):
        with pytest.raises(pytest.skip.Exception):
            fence()


@pytest.mark.parametrize("foreign", [
    "integrations/hermes_runtime/unlisted_native_owner.py",
    "tests/test_linux_secondary_worker_unlisted.py",
    "integrations/hermes_qualification/native_eval_inputs/extra.py",
    "integrations/hermes_runtime/tests/fixtures/native_eval_inputs/unlisted.source",
    "control_plane/bypass.py", "config/agent_eval.yaml", ".github/workflows/agent-eval.yml", "requirements/new.in",
])
def test_native_eval_delta_cannot_admit_nearby_or_forbidden_foreign_paths(tmp_path, monkeypatch, foreign):
    files = [("integrations/hermes_runtime/native_eval_inputs.py", "fixture\n"),
             ("integrations/hermes_runtime/supervisor.py", "fixture\n"), (foreign, "fixture\n")]
    repo = _standalone_prefix_delta_repo(tmp_path, "native_eval_foreign", files)
    _bind_root_to_private_fixture(monkeypatch, repo)
    assert _fence_not_applicable_reason(compute_pr_diff_paths(repo)) is None
    assert "outside the allowed R0 surface" in _real_fence_outcome(test_changed_paths_are_within_the_allowed_r0_surface)
    forbidden = foreign.startswith(("control_plane/", "config/", ".github/workflows/", "requirements"))
    result = _real_fence_outcome(test_no_control_plane_config_dependency_or_workflow_file_touched)
    assert ("unexpected control-plane/config/workflow change" in result) if forbidden else result == "PASS"


def test_pro_turn_prefix_only_delta_reaches_both_real_fences(
    tmp_path: Path, monkeypatch,
) -> None:
    """A delta of ONLY valid new-prefix corpus files must REACH both real
    fence entry points and pass them.

    Before the applicability repair this delta was classified "not
    applicable" and both fences skipped -- the corpus was never policed.
    """
    files = [
        (f"{_PRO_TURN_PREFIX}README.md", "pro-turn corpus\n"),
        (f"{_PRO_TURN_PREFIX}scenarios/carrier_protocol_compliance/healthy_chunk/v1/scenario.json", "{}\n"),
        (f"{_PRO_TURN_PREFIX}scenarios/carrier_protocol_compliance/healthy_chunk/v1/fixtures/input.json", "{}\n"),
    ]
    repo = _standalone_prefix_delta_repo(tmp_path, "pro_turn_prefix_only", files)
    _bind_root_to_private_fixture(monkeypatch, repo)

    changed = compute_pr_diff_paths(repo)
    assert changed == {relative_path for relative_path, _ in files}
    # The applicability boundary: a delta made only of program-surface
    # paths must be fenced, not skipped as foreign.
    assert _fence_not_applicable_reason(changed) is None
    assert _real_fence_outcome(test_changed_paths_are_within_the_allowed_r0_surface) == "PASS"
    assert _real_fence_outcome(test_no_control_plane_config_dependency_or_workflow_file_touched) == "PASS"


def test_pro_turn_prefix_only_disallowed_payload_fails_the_real_allowlist_fence(
    tmp_path: Path, monkeypatch,
) -> None:
    """A new-prefix delta whose only file is a disallowed type must REACH
    the real allowlist fence and be refused by it.

    The corpus law's own filename/type guard still refuses ``payload.py``:
    membership in PROGRAM_SURFACE_PREFIXES classifies the delta as
    in-program, it does not widen the allowlist.
    """
    payload = f"{_PRO_TURN_PREFIX}scenarios/carrier_protocol_compliance/healthy_chunk/v1/payload.py"
    repo = _standalone_prefix_delta_repo(tmp_path, "pro_turn_payload_only", [(payload, "x = 1\n")])
    _bind_root_to_private_fixture(monkeypatch, repo)

    changed = compute_pr_diff_paths(repo)
    assert changed == {payload}
    assert _fence_not_applicable_reason(changed) is None
    outcome = _real_fence_outcome(test_changed_paths_are_within_the_allowed_r0_surface)
    assert outcome.startswith("FAIL"), outcome
    assert "outside the allowed R0 surface" in outcome


@pytest.mark.parametrize(
    "forbidden_path",
    [
        "control_plane/bypass.py",
        "config/agent_eval.yaml",
        ".github/workflows/agent-eval.yml",
        "requirements.txt",
    ],
    ids=["control_plane", "config", "workflow", "dependency"],
)
def test_pro_turn_prefix_plus_forbidden_path_fails_the_real_forbidden_fence(
    tmp_path: Path, monkeypatch, forbidden_path: str,
) -> None:
    """A new-prefix corpus delta carrying one forbidden control-plane /
    config / workflow / dependency path must REACH the real forbidden
    fence and be refused by it -- and by the allowlist fence too.

    The corpus path alone (without the classifier repair) was classified
    "not applicable", so this mixed delta escaped BOTH fences.
    """
    files = [
        (f"{_PRO_TURN_PREFIX}README.md", "pro-turn corpus\n"),
        (forbidden_path, "forbidden surface\n"),
    ]
    repo = _standalone_prefix_delta_repo(
        tmp_path, "pro_turn_forbidden_" + forbidden_path.replace("/", "_"), files,
    )
    _bind_root_to_private_fixture(monkeypatch, repo)

    changed = compute_pr_diff_paths(repo)
    assert changed == {relative_path for relative_path, _ in files}
    assert _fence_not_applicable_reason(changed) is None
    allowlist_outcome = _real_fence_outcome(test_changed_paths_are_within_the_allowed_r0_surface)
    assert allowlist_outcome.startswith("FAIL"), allowlist_outcome
    assert "outside the allowed R0 surface" in allowlist_outcome
    forbidden_outcome = _real_fence_outcome(test_no_control_plane_config_dependency_or_workflow_file_touched)
    assert forbidden_outcome.startswith("FAIL"), forbidden_outcome
    assert "unexpected control-plane/config/workflow change" in forbidden_outcome
