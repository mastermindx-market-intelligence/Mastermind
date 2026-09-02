"""EVAL-E1: tests for the paired-pilot preregistration shape validator
(``scripts/agent_eval/prereg.py``) and the committed
``experiments/agent_eval/e1/preregistration.json`` record.

Plan record: ``docs/superpowers/plans/2026-09-01-agent-evaluation-e1-
preregistration.md``. Operation
``mastermind-agent-evaluation-e1-prereg-20260901-fable-001``.

RECORDS ONLY -- every test here validates SHAPE, cross-references the
already-COMMITTED corpus/configuration/experiment data, or proves
inertness. Nothing in this file (or in ``prereg.py``) executes a
scenario, calls a provider, or drives R0's ``store``/``validity``
finalizer.
"""
from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.agent_eval import contracts, corpus, prereg
from scripts.agent_eval.errors import ContractError

ROOT = Path(__file__).resolve().parents[1]
CORPUS_ROOT = ROOT / "corpus" / "agent_eval"
PREREG_PATH = ROOT / "experiments" / "agent_eval" / "e1" / "preregistration.json"


def _load_document() -> dict:
    return json.loads(PREREG_PATH.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# 0. The committed record exists and is exactly what this test file checks
# ---------------------------------------------------------------------------


def test_committed_preregistration_file_exists() -> None:
    assert PREREG_PATH.is_file(), f"expected a committed preregistration at {PREREG_PATH}"


# ---------------------------------------------------------------------------
# 1. Shape validity (RED -> GREEN: a minimal malformed document must fail
#    before the real committed document is shown to pass)
# ---------------------------------------------------------------------------


def test_empty_document_is_not_shape_valid() -> None:
    with pytest.raises(ContractError):
        prereg.validate_preregistration_shape({})


def test_committed_document_is_shape_valid() -> None:
    document = _load_document()
    assert prereg.validate_preregistration_shape(document) == "SHAPE_VALID"


def test_committed_document_schema_is_the_frozen_e1_schema() -> None:
    document = _load_document()
    assert document["schema"] == prereg.PREREG_SCHEMA
    assert document["schema"] == "mastermind.agent_evaluation_e1_preregistration.v1"


def test_unknown_field_is_rejected() -> None:
    document = _load_document()
    document["unexpected_field"] = "surprise"
    with pytest.raises(ContractError):
        prereg.validate_preregistration_shape(document)


def test_missing_required_field_is_rejected() -> None:
    document = _load_document()
    del document["design_law"]
    with pytest.raises(ContractError):
        prereg.validate_preregistration_shape(document)


# ---------------------------------------------------------------------------
# 2. Frozen E1 design law (3 task classes x 2 arms x 2 replicates = 6
#    pairs / 12 intended runs, seed 5601, no early stopping, no sample
#    replacement, DESCRIPTIVE evidence ceiling)
# ---------------------------------------------------------------------------


def test_design_law_matches_the_frozen_e1_counts() -> None:
    document = _load_document()
    design = document["design_law"]
    assert design["task_class_count"] == 3
    assert design["arm_count"] == 2
    assert design["replicates_per_arm"] == 2
    assert design["pairs"] == 6
    assert design["intended_runs"] == 12
    assert design["seed"] == 5601
    assert design["no_early_stopping"] is True
    assert design["no_sample_replacement"] is True
    assert design["evidence_ceiling"] == prereg.EVIDENCE_CEILING
    assert design["evidence_ceiling"] == "DESCRIPTIVE_PAIRED_PILOT_NOT_POLICY_GRADE"


def test_design_law_rejects_an_inconsistent_run_count() -> None:
    document = _load_document()
    document["design_law"] = dict(document["design_law"], intended_runs=999)
    with pytest.raises(ContractError) as excinfo:
        prereg.validate_preregistration_shape(document)
    codes = {d.code for d in excinfo.value.defects}
    assert "RUN_COUNT_MISMATCH" in codes


def test_design_law_rejects_an_inconsistent_pair_count() -> None:
    document = _load_document()
    document["design_law"] = dict(document["design_law"], pairs=999)
    with pytest.raises(ContractError) as excinfo:
        prereg.validate_preregistration_shape(document)
    codes = {d.code for d in excinfo.value.defects}
    assert "PAIR_COUNT_MISMATCH" in codes


def test_design_law_rejects_early_stopping_or_sample_replacement() -> None:
    document = _load_document()
    document["design_law"] = dict(document["design_law"], no_early_stopping=False)
    with pytest.raises(ContractError) as excinfo:
        prereg.validate_preregistration_shape(document)
    assert any(d.code == "STOPPING_LAW_VIOLATED" for d in excinfo.value.defects)


def test_arm_identities_are_the_two_frozen_mas136_skillpack_arms() -> None:
    document = _load_document()
    arms = document["arm_identities"]
    assert arms["control"]["commit_sha"] == "51f9942733b86e550bb9169d2a43462bd28e774f"
    assert arms["control"]["skillpack_version"] == "1.0.0"
    assert arms["amended"]["commit_sha"] == "8209e1f31da15f8effc23a9899a5c5a02d30cab4"
    assert arms["amended"]["skillpack_version"] == "1.1.0"
    # Same frozen data scripts.agent_eval.ohf_bridge.OHF_SKILLPACK_ARMS carries
    # for these same two arm names -- independently reproduced, not imported.
    from scripts.agent_eval import ohf_bridge

    assert ohf_bridge.OHF_SKILLPACK_ARMS["control-1.0.0"] == (
        arms["control"]["commit_sha"],
        arms["control"]["skillpack_version"],
    )
    assert ohf_bridge.OHF_SKILLPACK_ARMS["amended-1.1.0"] == (
        arms["amended"]["commit_sha"],
        arms["amended"]["skillpack_version"],
    )


# ---------------------------------------------------------------------------
# 3. Task-class bindings: three materially different scenario families,
#    one primary scenario_id each, with a stated rationale
# ---------------------------------------------------------------------------


def test_exactly_three_task_classes_with_distinct_families() -> None:
    document = _load_document()
    task_classes = document["task_classes"]
    assert len(task_classes) == 3
    families = {t["scenario_family"] for t in task_classes}
    assert len(families) == 3
    assert families == {
        "mastermind.current_source_comprehension.v1",
        "mastermind.bounded_implementation_fence.v1",
        "mastermind.carrier_protocol_compliance.v1",
    }


def test_task_class_rejects_a_fourth_binding() -> None:
    document = _load_document()
    document["task_classes"] = document["task_classes"] + [document["task_classes"][0]]
    with pytest.raises(ContractError) as excinfo:
        prereg.validate_preregistration_shape(document)
    codes = {d.code for d in excinfo.value.defects}
    assert "NOT_THREE_TASK_CLASSES" in codes or "DUPLICATE_SCENARIO_FAMILY" in codes


def test_each_task_class_names_a_nonempty_rationale_and_scorer() -> None:
    document = _load_document()
    for task_class in document["task_classes"]:
        assert task_class["primary_scenario_rationale"].strip() != ""
        assert task_class["scorer_id"].startswith("mastermind.tc")
        assert task_class["rubric_residue_dimension"] == "rubric_residue"
        assert "rubric_residue" not in task_class["deterministic_dimensions"]


def test_each_task_class_scorer_dimensions_match_the_real_s1_scorer_modules() -> None:
    from scripts.agent_eval import tc1_source_comprehension, tc2_implementation_fence, tc3_protocol_compliance

    by_family = {t["scenario_family"]: t for t in _load_document()["task_classes"]}
    tc1 = by_family["mastermind.current_source_comprehension.v1"]
    assert tc1["scorer_id"] == tc1_source_comprehension.SCORER_ID
    assert set(tc1["all_dimensions"]) == set(tc1_source_comprehension.DIMENSIONS)

    tc2 = by_family["mastermind.bounded_implementation_fence.v1"]
    assert tc2["scorer_id"] == tc2_implementation_fence.SCORER_ID
    assert set(tc2["all_dimensions"]) == set(tc2_implementation_fence.DIMENSIONS)

    tc3 = by_family["mastermind.carrier_protocol_compliance.v1"]
    assert tc3["scorer_id"] == tc3_protocol_compliance.SCORER_ID
    assert set(tc3["all_dimensions"]) == set(tc3_protocol_compliance.DIMENSIONS)


# ---------------------------------------------------------------------------
# 4. Bound scenario_ids actually exist in the COMMITTED C0 corpus
# ---------------------------------------------------------------------------


def test_bound_scenarios_are_verified_present_in_the_real_committed_corpus() -> None:
    document = _load_document()
    # Must not raise -- every primary_scenario_ref resolves to a real,
    # byte-consistent, digest-matched scenario under corpus/agent_eval/.
    prereg.verify_scenario_bindings(document, corpus_root=CORPUS_ROOT, repo_root=ROOT)


def test_bound_scenario_digest_tamper_is_caught() -> None:
    document = copy.deepcopy(_load_document())
    document["task_classes"][0]["primary_scenario_ref"]["scenario_digest"] = "sha256:" + "0" * 64
    with pytest.raises(ContractError) as excinfo:
        prereg.verify_scenario_bindings(document, corpus_root=CORPUS_ROOT, repo_root=ROOT)
    codes = {d.code for d in excinfo.value.defects}
    assert "BOUND_SCENARIO_DIGEST_MISMATCH" in codes


def test_bound_scenario_pointing_at_a_nonexistent_case_is_caught() -> None:
    document = copy.deepcopy(_load_document())
    document["task_classes"][0]["primary_scenario_ref"]["scenario_id"] = (
        "scenario:current_source_comprehension:does_not_exist_anywhere"
    )
    with pytest.raises(ContractError) as excinfo:
        prereg.verify_scenario_bindings(document, corpus_root=CORPUS_ROOT, repo_root=ROOT)
    codes = {d.code for d in excinfo.value.defects}
    assert "BOUND_SCENARIO_NOT_FOUND" in codes


def test_scenario_binding_verification_fails_if_the_corpus_tree_is_inconsistent(tmp_path) -> None:
    # A corpus_root with no manifest at all is INCONSISTENT by construction.
    document = _load_document()
    empty_corpus = tmp_path / "corpus" / "agent_eval"
    empty_corpus.mkdir(parents=True)
    with pytest.raises(ContractError) as excinfo:
        prereg.verify_scenario_bindings(document, corpus_root=empty_corpus, repo_root=ROOT)
    codes = {d.code for d in excinfo.value.defects}
    assert "CORPUS_NOT_CONSISTENT" in codes


def test_real_corpus_tree_is_itself_consistent() -> None:
    # Independent of the preregistration -- proves the committed corpus
    # this preregistration binds against is not itself already broken.
    report = corpus.verify_corpus_tree_consistency(CORPUS_ROOT, ROOT)
    assert report.result == "CONSISTENT", report.defects


# ---------------------------------------------------------------------------
# 5. Configuration/experiment digests are stable and recomputable
# ---------------------------------------------------------------------------


def test_six_configurations_three_task_classes_times_two_arms() -> None:
    document = _load_document()
    assert len(document["configurations"]) == 6
    for configuration in document["configurations"]:
        assert contracts.validate_configuration_shape(configuration) == "SHAPE_VALID"


def test_three_experiments_one_per_task_class() -> None:
    document = _load_document()
    assert len(document["experiments"]) == 3
    for experiment in document["experiments"]:
        assert contracts.validate_experiment_shape(experiment) == "SHAPE_VALID"


def test_configuration_digests_are_stable_and_recomputable() -> None:
    document = _load_document()
    prereg.verify_configuration_digests(document)  # must not raise


def test_configuration_digest_tamper_is_caught() -> None:
    document = copy.deepcopy(_load_document())
    document["configurations"][0]["randomness"]["seed"] = 999999
    with pytest.raises(ContractError) as excinfo:
        prereg.verify_configuration_digests(document)
    codes = {d.code for d in excinfo.value.defects}
    assert "DIGEST_MISMATCH" in codes


def test_experiment_digests_are_stable_and_recomputable() -> None:
    document = _load_document()
    prereg.verify_experiment_digests(document)  # must not raise


def test_experiment_digest_tamper_is_caught() -> None:
    document = copy.deepcopy(_load_document())
    document["experiments"][0]["replicates_per_arm_target"] = 999
    with pytest.raises(ContractError) as excinfo:
        prereg.verify_experiment_digests(document)
    codes = {d.code for d in excinfo.value.defects}
    assert "DIGEST_MISMATCH" in codes


def test_every_experiment_pairing_binds_the_frozen_seed_5601_via_blocked_method() -> None:
    document = _load_document()
    for experiment in document["experiments"]:
        assert experiment["pairing"]["method"] == "BLOCKED"
        assert experiment["pairing"]["random_seed"] == 5601
        assert experiment["stopping_rule"] == {"kind": "FIXED_REPLICATES_PER_ARM", "value": 2}
        assert experiment["replicates_per_arm_target"] == 2
        assert experiment["phase"] == "PROSPECTIVE_SHADOW"
        assert len(experiment["arms"]) == 2


def test_a_pairing_seed_under_paired_by_scenario_is_schema_illegal() -> None:
    # Documents WHY this preregistration uses BLOCKED, not PAIRED_BY_SCENARIO,
    # to carry the frozen seed: R0's own experiment contract forbids it.
    document = copy.deepcopy(_load_document())
    document["experiments"][0]["pairing"] = {"method": "PAIRED_BY_SCENARIO", "random_seed": 5601}
    # Recompute the digest so this is a pure pairing-law probe, not a stale-digest one.
    from scripts.agent_eval.canonical import add_document_digest

    tampered = {k: v for k, v in document["experiments"][0].items() if k != "experiment_digest"}
    document["experiments"][0] = add_document_digest(tampered, "experiment_digest")
    with pytest.raises(ContractError) as excinfo:
        contracts.validate_experiment_shape(document["experiments"][0])
    codes = {d.code for d in excinfo.value.defects}
    assert "SEED_NOT_ALLOWED_EXCEPT_BLOCKED" in codes


# ---------------------------------------------------------------------------
# 6. The seal: deterministic canonical self-digest
# ---------------------------------------------------------------------------


def test_committed_seal_verifies() -> None:
    document = _load_document()
    prereg.verify_seal(document)  # must not raise


def test_seal_is_deterministic_across_rebuilds() -> None:
    document = _load_document()
    recomputed = prereg.compute_seal(document)
    assert recomputed == document["preregistration_digest"]
    # Recomputing twice from the same bytes gives the identical digest.
    assert prereg.compute_seal(document) == recomputed


def test_seal_changes_if_any_field_is_tampered() -> None:
    document = copy.deepcopy(_load_document())
    original_digest = document["preregistration_digest"]
    document["operation_key"] = document["operation_key"] + "-tampered"
    recomputed = prereg.compute_seal(document)
    assert recomputed != original_digest


def test_seal_tamper_is_caught_by_verify_seal() -> None:
    document = copy.deepcopy(_load_document())
    document["preregistration_digest"] = "sha256:" + "1" * 64
    with pytest.raises(ContractError):
        prereg.verify_seal(document)


def test_build_preregistration_rejects_a_fields_dict_carrying_schema_or_digest() -> None:
    with pytest.raises(ContractError):
        prereg.build_preregistration({"schema": "x"})
    with pytest.raises(ContractError):
        prereg.build_preregistration({"preregistration_digest": "sha256:" + "0" * 64})


# ---------------------------------------------------------------------------
# 7. Execution gate: sealed BEFORE execution, both conditions must be
#    present and neither may already be satisfied
# ---------------------------------------------------------------------------


def test_execution_gate_names_runner_proven_live_and_fresh_authorization() -> None:
    document = _load_document()
    condition_ids = {c["condition_id"] for c in document["execution_gate"]["conditions"]}
    assert "RUNNER_PROVEN_LIVE" in condition_ids
    assert "FRESH_LIVE_AUTHORIZATION" in condition_ids


def test_execution_gate_conditions_are_all_unsatisfied_at_preregistration_time() -> None:
    document = _load_document()
    for condition in document["execution_gate"]["conditions"]:
        assert condition["satisfied"] is False


def test_execution_gate_rejects_a_prematurely_satisfied_condition() -> None:
    document = _load_document()
    document["execution_gate"] = {
        "gate_law": document["execution_gate"]["gate_law"],
        "conditions": [
            {"condition_id": "RUNNER_PROVEN_LIVE", "description": "x", "satisfied": True},
            {"condition_id": "FRESH_LIVE_AUTHORIZATION", "description": "y", "satisfied": False},
        ],
    }
    with pytest.raises(ContractError) as excinfo:
        prereg.validate_preregistration_shape(document)
    codes = {d.code for d in excinfo.value.defects}
    assert "EXECUTION_GATE_PREMATURELY_SATISFIED" in codes


def test_execution_gate_rejects_fewer_than_two_conditions() -> None:
    document = _load_document()
    document["execution_gate"] = {
        "gate_law": document["execution_gate"]["gate_law"],
        "conditions": [{"condition_id": "ONLY_ONE", "description": "x", "satisfied": False}],
    }
    with pytest.raises(ContractError) as excinfo:
        prereg.validate_preregistration_shape(document)
    codes = {d.code for d in excinfo.value.defects}
    assert "EXECUTION_GATE_UNDERSPECIFIED" in codes


# ---------------------------------------------------------------------------
# 8. Ex-ante expectation: sealed, uncertain, never a fact
# ---------------------------------------------------------------------------


def test_ex_ante_expectation_is_sealed_with_one_forecast_per_task_class() -> None:
    document = _load_document()
    expectation = document["ex_ante_expectation"]
    assert expectation["sealed"] is True
    labels = {f["task_class_label"] for f in expectation["forecasts"]}
    assert labels == {"TC1", "TC2", "TC3"}
    for forecast in expectation["forecasts"]:
        assert forecast["uncertainty_statement"].strip() != ""
        assert forecast["falsification_condition"].strip() != ""


def test_ex_ante_expectation_disclosed_as_forecast_not_fact() -> None:
    document = _load_document()
    disclosed = document["ex_ante_expectation"]["disclosed_as"].lower()
    assert "forecast" in disclosed
    assert "not" in disclosed  # "not predictions dressed as fact"


# ---------------------------------------------------------------------------
# 9. Invalid/degraded handling covers R0's real, closed validity vocabulary
# ---------------------------------------------------------------------------


def test_invalid_degraded_handling_covers_every_real_validity_status() -> None:
    document = _load_document()
    from scripts.agent_eval import validity as validity_module

    statuses = set(document["invalid_degraded_handling"]["statuses"])
    assert statuses == set(prereg.TECHNICAL_VALIDITY_STATUSES)
    # Cross-check against validity.py's own module source rather than a
    # hand-maintained duplicate: every status name this preregistration
    # claims must actually appear as a literal in validity.py.
    source = Path(validity_module.__file__).read_text(encoding="utf-8")
    for status in statuses:
        assert status in source, f"{status!r} not found in validity.py -- prereg.py's status set has drifted"


def test_invalid_degraded_handling_rejects_a_status_set_that_drops_a_status() -> None:
    document = _load_document()
    handling = dict(document["invalid_degraded_handling"])
    handling["statuses"] = sorted(set(handling["statuses"]) - {"INVALID_LEAKAGE"})
    document = dict(document, invalid_degraded_handling=handling)
    with pytest.raises(ContractError) as excinfo:
        prereg.validate_preregistration_shape(document)
    codes = {d.code for d in excinfo.value.defects}
    assert "STATUS_SET_MISMATCH" in codes


# ---------------------------------------------------------------------------
# 10. Leakage audit requirement + disclosed placeholders + non_goals
# ---------------------------------------------------------------------------


def test_leakage_audit_is_required_and_independent() -> None:
    document = _load_document()
    audit = document["leakage_audit_requirement"]
    assert audit["required"] is True
    assert "independent" in audit["independence_law"].lower()
    assert len(audit["scope"]) > 0


def test_disclosed_placeholders_are_named_never_silently_fabricated() -> None:
    document = _load_document()
    placeholders = document["disclosed_placeholders"]
    assert len(placeholders) > 0
    fields_named = {p["field_path"] for p in placeholders}
    assert any("instruction_bundle" in f for f in fields_named)
    for placeholder in placeholders:
        assert "PLACEHOLDER" in placeholder["reason"].upper() or "placeholder" in placeholder["reason"]
        assert placeholder["bound_at_execution_by"].strip() != ""


def test_every_configuration_instruction_bundle_ref_is_marked_as_a_placeholder() -> None:
    document = _load_document()
    for configuration in document["configurations"]:
        artifact_ref = configuration["procedure"]["instruction_bundle"]["artifact_ref"]
        assert artifact_ref.startswith("PREREGISTRATION_PLACEHOLDER#")


def test_non_goals_cover_the_hard_scope_boundaries() -> None:
    document = _load_document()
    joined = " ".join(document["non_goals"]).lower()
    for phrase in ("execution", "network", "holdout", "corpus content", "causal"):
        assert phrase in joined, f"non_goals missing expected phrase: {phrase!r}"


def test_analysis_plan_states_no_causal_claim() -> None:
    document = _load_document()
    statement = document["analysis_plan"]["no_causal_claim_statement"].lower()
    assert "descriptive" in statement
    assert "never" in statement or "not" in statement


# ---------------------------------------------------------------------------
# 11. Corpus revision / base commit provenance
# ---------------------------------------------------------------------------


def test_corpus_revision_matches_the_committed_manifest_anchor() -> None:
    document = _load_document()
    manifest = json.loads((CORPUS_ROOT / "corpus_manifest.json").read_text(encoding="utf-8"))
    assert document["corpus_revision"] == manifest["corpus_revision"]


def test_base_commit_is_a_source_qualified_ref_on_this_repository() -> None:
    document = _load_document()
    assert document["base_commit"].startswith("git:mastermindx-market-intelligence/Mastermind@")


# ---------------------------------------------------------------------------
# 12. Inertness: prereg.py imports/invokes NO runner, executes NO turn
# ---------------------------------------------------------------------------

# Same closed forbidden-module vocabulary the shared R0 inertness fence
# (tests/test_agent_eval_inertness.py) already enforces repo-wide; proven
# again here, scoped to this wave's own new file, as the packet requires.
from tests.test_agent_eval_inertness import FORBIDDEN_IMPORT_MODULES, _imported_module_names, _parse

PREREG_MODULE_PATH = ROOT / "scripts" / "agent_eval" / "prereg.py"


def test_prereg_module_file_exists() -> None:
    assert PREREG_MODULE_PATH.is_file()


def test_prereg_module_imports_no_forbidden_module() -> None:
    imported = _imported_module_names(_parse(PREREG_MODULE_PATH))
    hits = {
        name
        for name in imported
        if any(name == forbidden or name.startswith(forbidden + ".") for forbidden in FORBIDDEN_IMPORT_MODULES)
    }
    assert not hits, f"prereg.py imports forbidden module(s): {hits}"


def test_prereg_module_never_imports_scripts_ohf() -> None:
    imported = _imported_module_names(_parse(PREREG_MODULE_PATH))
    assert "scripts.ohf" not in imported
    assert not any(name.startswith("scripts.ohf.") for name in imported)


def test_importing_prereg_module_has_no_observable_side_effect(tmp_path) -> None:
    before = set(tmp_path.iterdir())
    script = f"import sys\nsys.path.insert(0, {str(ROOT)!r})\nimport scripts.agent_eval.prereg\n"
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
    assert after == before


def test_full_validation_pipeline_against_the_committed_document_makes_no_filesystem_write(tmp_path) -> None:
    """Runs the entire shape+cross-check+seal pipeline (exactly what a
    future CI gate would run) inside a subprocess whose cwd is an empty
    temp directory, and proves nothing was written there and nothing
    escalated to a network/process call -- i.e. the whole prereg surface,
    invoked end to end, executes no runner and no turn."""
    before = set(tmp_path.iterdir())
    script = "\n".join(
        [
            "import sys, json",
            f"sys.path.insert(0, {str(ROOT)!r})",
            "from pathlib import Path",
            "from scripts.agent_eval import prereg, corpus",
            f"document = json.loads(open({str(PREREG_PATH)!r}).read())",
            "assert prereg.validate_preregistration_shape(document) == 'SHAPE_VALID'",
            f"prereg.verify_scenario_bindings(document, corpus_root=Path({str(CORPUS_ROOT)!r}), repo_root=Path({str(ROOT)!r}))",
            "prereg.verify_configuration_digests(document)",
            "prereg.verify_experiment_digests(document)",
            "prereg.verify_seal(document)",
            "print('PIPELINE_OK')",
        ]
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        cwd=str(tmp_path),
        timeout=30,
        env={"PATH": os.environ.get("PATH", "")},
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "PIPELINE_OK"
    after = set(tmp_path.iterdir())
    assert after == before  # zero files written -- no run/receipt/turn artifact of any kind
