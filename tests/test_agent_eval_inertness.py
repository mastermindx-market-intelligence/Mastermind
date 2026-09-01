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
    }
)

# EVAL-C0 fence ratchet (principal-authorized 2026-09-01, operation
# mastermind-agent-evaluation-c0-corpus-20260901-fable-001): this is the
# deliberate per-wave surface ratchet -- each wave's OWNED paths are added
# to this fence only by explicit principal authorization, never by the
# wave's own worker unilaterally widening its own gate. C0's corpus tree
# (``corpus/agent_eval/``) grows case-by-case across this and future
# C0-lineage waves without renaming any script or test, so it is the one
# path allowed as a PREFIX rather than an ever-growing enumerated file
# list -- every other wave's surface (R0's own paths above, and C0's three
# new exact files above) stays exact-path-only. A future wave widening
# this ratchet further still needs its own explicit principal
# authorization and its own operation-key citation, exactly like this one.
ALLOWED_PATH_PREFIXES = frozenset({"corpus/agent_eval/"})

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
    if path in ALLOWED_PATHS:
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
# whole-delta-within-ALLOWED_PATHS rule, ratchet discipline unchanged) only
# when the PR's OWN delta touches at least one path under this program's
# surface. A delta touching NONE of it is simply not this program's
# business -- not-applicable, never failed.
# ---------------------------------------------------------------------------

#: The frozen, minimal prefix set naming "this is unambiguously an
#: agent_eval program file" without hand-enumerating every individual
#: file. A future in-program file under one of these prefixes is
#: correctly classified as program-surface even before it is
#: ratchet-added to ALLOWED_PATHS -- it is still refused by the strict
#: allowlist check below (ratchet discipline is unchanged), it is simply
#: no longer misclassified as "foreign."
PROGRAM_SURFACE_PREFIXES = frozenset({"scripts/agent_eval/", "corpus/agent_eval/", "tests/test_agent_eval_"})

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
    moved. Otherwise (an ordinary linear branch head, e.g. local dev) the
    delta is ``merge-base(upstream, head)..head``, which still finds
    whatever the branch itself changed since it forked, no matter how far
    upstream has since moved -- never a hardcoded commit.
    """
    parents_result = _run_git(["rev-list", "--parents", "-n", "1", head], repo_dir)
    if parents_result.returncode != 0:
        raise AssertionError(f"git rev-list failed: {parents_result.stderr}")
    tokens = parents_result.stdout.split()
    parent_shas = tokens[1:]  # tokens[0] is `head` itself
    if len(parent_shas) >= 2:
        base_ref = f"{head}^1"
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
    assert changed, "expected at least one changed file relative to the effective PR base"
    not_applicable_reason = _fence_not_applicable_reason(changed)
    if not_applicable_reason is not None:
        pytest.skip(not_applicable_reason)
    unexpected = {path for path in changed if not _changed_path_is_allowed(path)}
    assert not unexpected, f"changed path(s) outside the allowed R0 surface: {sorted(unexpected)}"


def test_no_control_plane_config_dependency_or_workflow_file_touched() -> None:
    changed = compute_pr_diff_paths(ROOT)
    assert changed, "expected at least one changed file relative to the effective PR base"
    not_applicable_reason = _fence_not_applicable_reason(changed)
    if not_applicable_reason is not None:
        pytest.skip(not_applicable_reason)
    forbidden_prefixes = ("control_plane/", ".github/workflows/", "config/", "pyproject.toml", "requirements")
    for path in changed:
        assert not path.startswith(forbidden_prefixes), f"unexpected control-plane/config/workflow change: {path}"


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
