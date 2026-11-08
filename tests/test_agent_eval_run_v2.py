"""Retain incomplete attempts without invented observations or denominator loss.

These are synthetic contract/store journeys, not native producer attestations.
V1 fixtures and immutable receipt semantics remain unchanged.
"""
from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import pytest

from scripts.agent_eval import contracts, scoring, store, validity, verification
from scripts.agent_eval.canonical import add_document_digest
from scripts.agent_eval.errors import ArtifactConflictError, ContractError, VerificationContextError
from tests.agent_eval_factories import (
    MemoryArtifactResolver, build_alternate_configuration, build_baseline_configuration,
    build_baseline_scenario, build_run_draft, build_two_arm_experiment,
)

ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = dict(
    validator_id="mastermind.eval_fixture_finalizer.v2", validator_version="2",
    validator_code_ref="git:mastermindx-market-intelligence/Mastermind@" + "a" * 40,
    validated_at="2026-08-25T00:00:10Z", created_at="2026-08-25T00:00:11Z",
)


def _v2(draft):
    draft = copy.deepcopy(draft)
    draft["schema"] = contracts.RUN_DRAFT_SCHEMA_V2
    draft["observation_availability"] = {
        "unavailable": [], "coverage": {
            key: {"status": "COMPLETE", "reason": None}
            for key in sorted(contracts.RUN_OBSERVATION_COVERAGE_KEYS)
        },
    }
    return draft


def _missing(draft, *paths, reason="NOT_OBSERVED"):
    items = {item["path"]: item for item in draft["observation_availability"]["unavailable"]}
    for path in paths:
        group, key = path.split(".")
        draft[group][key] = None
        items[path] = {"path": path, "reason": reason}
    draft["observation_availability"]["unavailable"] = [items[path] for path in sorted(items)]
    return draft


def _graph():
    scenario, configuration, other = (
        build_baseline_scenario(), build_baseline_configuration(), build_alternate_configuration())
    experiment = build_two_arm_experiment(scenario, configuration, other)
    draft = _v2(build_run_draft(scenario, configuration, experiment, arm_id="arm_a", replicate_index=1))
    return scenario, configuration, other, experiment, draft


def _finalize(graph, draft=None, **overrides):
    scenario, configuration, _, experiment, original = graph
    return validity.finalize_run_receipt(
        scenario, configuration, experiment, original if draft is None else draft,
        **{**VALIDATOR, **overrides})


def _source_pair_graph():
    scenario, config, other, _, _ = _graph()
    pairs = [{"artifact_ref": "git:fixture/sources@" + "c" * 40 + "#" + name,
              "digest": "sha256:" + "e" * 64} for name in ("one.md", "two.md")]
    fields = {key: copy.deepcopy(value) for key, value in scenario.items()
              if key not in {"schema", "scenario_digest"}}
    fields["source_policy"]["allowlist_artifacts"] = sorted(
        fields["source_policy"]["allowlist_artifacts"] + pairs, key=lambda row: row["artifact_ref"])
    fields["privacy"]["model_visible_artifact_refs"] = sorted(
        set(fields["privacy"]["model_visible_artifact_refs"]) | {row["artifact_ref"] for row in pairs})
    scenario = contracts.build_scenario(fields, schema=contracts.SCENARIO_SCHEMA_V2)
    experiment = build_two_arm_experiment(scenario, config, other)
    draft = _v2(build_run_draft(scenario, config, experiment, arm_id="arm_a", replicate_index=1))
    draft["schema"] = contracts.RUN_DRAFT_SCHEMA_V3
    draft["observations"]["observed_sources"] = copy.deepcopy(pairs)
    return scenario, config, other, experiment, draft


def test_source_pair_v3_uses_original_store_finalizer_and_immutable_paths(tmp_path):
    graph = _source_pair_graph()
    draft = graph[-1]
    with pytest.raises(ContractError) as old:
        contracts.validate_run_draft_shape({**draft, "schema": contracts.RUN_DRAFT_SCHEMA_V2})
    assert "DUPLICATE_ARTIFACT_DIGEST" in {d.code for d in old.value.defects}
    run = _finalize(graph)
    assert run["schema"] == contracts.RUN_SCHEMA_V3
    assert run["observations"]["observed_sources"] == draft["observations"]["observed_sources"]
    assert run["validity"]["status"] == "VALID"
    artifact_store = _store(tmp_path, graph)
    assert artifact_store.create(run).disposition is store.WriteDisposition.CREATED
    assert artifact_store.resolve_run(run["run_id"]) == run
    assert artifact_store.create(run).disposition is store.WriteDisposition.IDEMPOTENT
    assert artifact_store.resolve_scenario(graph[0]["scenario_id"], graph[0]["scenario_version"]) == graph[0]
    assert contracts.validate_document_shape(run) == "SHAPE_VALID"
    assert _score(run)["run_digest"] == run["run_digest"]


@pytest.mark.parametrize("change,reason", [
    ("alias", "UNAUTHORIZED_SOURCE"), ("digest", "SOURCE_DIGEST_MISMATCH"),
    ("hidden", "HIDDEN_SOLUTION_SOURCE"), ("denied", "UNAUTHORIZED_SOURCE"),
])
def test_v3_source_policy_checks_each_ref_even_when_bytes_repeat(change, reason):
    graph = _source_pair_graph()
    scenario, config, other, experiment, draft = graph
    pair = draft["observations"]["observed_sources"][1]
    if change == "alias":
        pair["artifact_ref"] += ".unlisted"
    elif change == "digest":
        pair["digest"] = "sha256:" + "f" * 64
    else:
        # Pure policy decision covers hidden/denied values even though an
        # internally contradictory scenario would independently fail shape.
        scenario = copy.deepcopy(scenario)
        key = "solution_refs_hidden" if change == "hidden" else "denylist_refs"
        scenario["source_policy"][key] = [pair["artifact_ref"]]
        assert reason in validity.source_policy_reason_codes(scenario, draft["observations"]["observed_sources"])
        return
    run = _finalize(graph)
    assert reason in run["validity"]["reason_codes"]
    assert len(run["observations"]["observed_sources"]) == 2


def test_v3_missing_observations_and_transient_draft_are_not_promoted():
    graph = _source_pair_graph()
    draft = graph[-1]
    _missing(draft, "execution.model_served")
    draft["observation_availability"]["coverage"]["observed_sources"] = {
        "status": "PARTIAL", "reason": "OBSERVATION_LIMIT"}
    run = _finalize(graph)
    assert {"REQUIRED_OBSERVATION_UNAVAILABLE", "OBSERVATION_COVERAGE_INCOMPLETE"} <= set(run["validity"]["reason_codes"])
    with pytest.raises(ContractError) as error:
        contracts.validate_document_shape(draft)
    assert "DRAFT_SCHEMA_REJECTED" in {d.code for d in error.value.defects}


def _resolver(graph, *runs):
    scenario, configuration, other, experiment, _ = graph
    return MemoryArtifactResolver.build(scenarios=(scenario,), configurations=(configuration, other),
                                        experiments=(experiment,), runs=runs)


def _store(tmp_path, graph):
    artifact_store = store.ArtifactStore(tmp_path / "eval")
    for document in graph[:4]:
        artifact_store.create(document)
    return artifact_store


def _score(run):
    return scoring.build_technical_integrity_scorer_pass(
        run, scorer_pass_id="scorer-pass:" + str(uuid4()),
        scorer_code_ref=VALIDATOR["validator_code_ref"], created_at="2026-08-25T00:00:12Z")


def _summary(graph, runs, passes, *, multi=False):
    kwargs = dict(evidence_ref_id="evidence-ref:" + str(uuid4()), intended_owner="person:sol",
                  review_at="2026-08-26T00:00:00Z", created_at="2026-08-25T00:00:13Z",
                  analysis_version="mastermind.agent_evaluation_r0_analysis.v1")
    if multi:
        return scoring.summarize_multi_scenario_experiment(graph[3], (graph[0],), runs, passes, **kwargs)
    return scoring.summarize_experiment(graph[3], graph[0], runs, passes, **kwargs)


def test_complete_v2_uses_existing_validity_without_reinterpreting_v1():
    graph = _graph()
    v2 = _finalize(graph)
    legacy = copy.deepcopy(graph[-1])
    legacy["schema"] = contracts.RUN_DRAFT_SCHEMA
    legacy.pop("observation_availability")
    v1 = _finalize(graph, legacy)
    assert v1["schema"] == contracts.RUN_SCHEMA
    assert v2["schema"] == contracts.RUN_SCHEMA_V2
    assert v2["validity"] == v1["validity"]
    assert v2["validity"]["status"] == "VALID"
    assert v2["run_digest"] != v1["run_digest"]
    assert contracts.validate_document_shape(v2) == "SHAPE_VALID"


@pytest.mark.parametrize("path", sorted(contracts.RUN_OBSERVATION_PATHS))
def test_each_unavailable_observation_is_representable_but_never_valid(path):
    graph = _graph()
    draft = _missing(graph[-1], path)
    run = _finalize(graph)
    assert run["validity"]["status"] == "INVALID_CONFIGURATION"
    assert "REQUIRED_OBSERVATION_UNAVAILABLE" in run["validity"]["reason_codes"]
    assert contracts.validate_run_shape(run) == "SHAPE_VALID"
    assert verification.verify_run_graph(run, _resolver(graph)).scope == "EVALUATION_GRAPH_VERIFIED"
    legacy = copy.deepcopy(draft)
    legacy["schema"] = contracts.RUN_DRAFT_SCHEMA
    legacy.pop("observation_availability")
    with pytest.raises(ContractError):
        contracts.validate_run_draft_shape(legacy)


@pytest.mark.parametrize("mutation", ["no_reason", "nonnull", "duplicate", "unsorted", "unknown_path", "unknown_reason"])
def test_unavailability_is_a_closed_exact_bijection(mutation):
    draft = _missing(_graph()[-1], "execution.provider", "execution.model_served")
    items = draft["observation_availability"]["unavailable"]
    if mutation == "no_reason":
        items.pop()
    elif mutation == "nonnull":
        draft["execution"]["provider"] = "fixture"
    elif mutation == "duplicate":
        items.append(dict(items[-1]))
    elif mutation == "unsorted":
        items.reverse()
    elif mutation == "unknown_path":
        items[0]["path"] = "procedure.instruction_bundle"
    else:
        items[0]["reason"] = "ASSUME_CONFIGURED"
    with pytest.raises(ContractError):
        contracts.validate_run_draft_shape(draft)


@pytest.mark.parametrize("key", sorted(contracts.RUN_OBSERVATION_COVERAGE_KEYS))
def test_partial_collection_coverage_always_prevents_validity(key):
    graph = _graph()
    graph[-1]["observation_availability"]["coverage"][key] = {
        "status": "PARTIAL", "reason": "OBSERVATION_LIMIT"}
    run = _finalize(graph)
    assert run["validity"]["status"] == "INVALID_CONFIGURATION"
    assert "OBSERVATION_COVERAGE_INCOMPLETE" in run["validity"]["reason_codes"]


@pytest.mark.parametrize("mutation", ["missing_key", "complete_reason", "partial_no_reason", "unknown_key", "unobserved_retained"])
def test_coverage_claims_are_closed_and_do_not_erase_retained_observations(mutation):
    draft = _graph()[-1]
    coverage = draft["observation_availability"]["coverage"]
    if mutation == "missing_key":
        coverage.pop("provider_requests")
    elif mutation == "complete_reason":
        coverage["provider_requests"]["reason"] = "NOT_OBSERVED"
    elif mutation == "partial_no_reason":
        coverage["provider_requests"]["status"] = "PARTIAL"
    elif mutation == "unknown_key":
        coverage["all_security"] = {"status": "COMPLETE", "reason": None}
    else:
        coverage["observed_sources"] = {"status": "UNOBSERVED", "reason": "NOT_RETAINED"}
    with pytest.raises(ContractError):
        contracts.validate_run_draft_shape(draft)


@pytest.mark.parametrize("path", [
    "execution.runner_id", "execution.runner_code_ref", "execution.execution_surface",
    "execution.execution_surface_version", "execution.completion_status", "execution.termination_reason",
    "procedure.instruction_bundle", "context.context_packet", "context.source_policy_digest",
    "capabilities.profile_id", "capabilities.profile_digest", "configuration.configuration_id",
])
def test_selected_identity_and_terminal_provenance_cannot_be_downgraded_to_unknown(path):
    draft = _graph()[-1]
    group, key = path.split(".")
    draft[group][key] = None
    with pytest.raises(ContractError):
        contracts.validate_run_draft_shape(draft)


@pytest.mark.parametrize("completion", ["FAILED", "TIMED_OUT", "CANCELLED"])
def test_terminal_attempt_with_no_execution_observations_remains_recordable(completion):
    graph = _graph()
    draft = _missing(graph[-1], *contracts.RUN_OBSERVATION_PATHS, reason="RESULT_EXPIRED")
    draft["execution"].update(completion_status=completion, termination_reason="ORIGINAL_TERMINAL_RECORD")
    draft["observations"] = {key: [] for key in draft["observations"]}
    draft["observation_availability"]["coverage"] = {
        key: {"status": "UNOBSERVED", "reason": "RESULT_EXPIRED"}
        for key in contracts.RUN_OBSERVATION_COVERAGE_KEYS}
    draft["effect"] = {"state": "EFFECT_UNKNOWN", "operation_ref": None, "reconciliation_ref": None}
    draft["cleanup"] = {"status": "UNPROVEN", "proof": None}
    draft["resources"] = {key: None for key in draft["resources"]}
    run = _finalize(graph)
    assert run["validity"]["status"] == "INVALID_EFFECT_UNKNOWN"
    assert {"REQUIRED_OBSERVATION_UNAVAILABLE", "OBSERVATION_COVERAGE_INCOMPLETE", "CLEANUP_UNPROVEN"} <= set(run["validity"]["reason_codes"])
    assert run["execution"]["model_served"] is None
    assert run["capabilities"]["environment_digest"] is None
    assert verification.collect_run_evidence_refs(run) == set()


def test_known_mismatch_and_leakage_survive_partial_observations():
    graph = _graph()
    draft = _missing(graph[-1], "execution.provider")
    draft["execution"]["model_served"] = "other-model"
    draft["observations"]["observed_sources"].append({
        "artifact_ref": graph[0]["source_policy"]["solution_refs_hidden"][0], "digest": "sha256:" + "2" * 64})
    draft["observation_availability"]["coverage"]["observed_sources"] = {
        "status": "PARTIAL", "reason": "OBSERVATION_LIMIT"}
    run = _finalize(graph)
    assert run["validity"]["status"] == "INVALID_LEAKAGE"
    assert {"MODEL_SERVED_MISMATCH", "HIDDEN_SOLUTION_SOURCE", "REQUIRED_OBSERVATION_UNAVAILABLE"} <= set(run["validity"]["reason_codes"])


def test_unknown_model_is_not_a_fabricated_observed_mismatch_or_allowed_degradation():
    graph = _graph()
    _missing(graph[-1], "execution.model_served")
    graph[-1]["observations"]["dependency_degradations"] = list(graph[0]["execution_policy"]["allowed_degradations"])
    run = _finalize(graph)
    assert run["validity"]["status"] == "INVALID_CONFIGURATION"
    assert "MODEL_SERVED_MISMATCH" not in run["validity"]["reason_codes"]


@pytest.mark.parametrize("mutation", ["late_start", "validation_after_creation"])
def test_missing_completion_time_cannot_break_known_chronology(mutation):
    graph = _graph()
    _missing(graph[-1], "timing.completed_at")
    kwargs = {}
    if mutation == "late_start":
        graph[-1]["timing"]["started_at"] = "2026-08-25T00:00:20Z"
    else:
        kwargs["created_at"] = "2026-08-25T00:00:09Z"
    with pytest.raises(ContractError) as caught:
        _finalize(graph, **kwargs)
    assert "VALIDITY_TIME_ORDER_VIOLATED" in {d.code for d in caught.value.defects}


def test_forged_validity_is_recomputed_with_unavailability():
    graph = _graph()
    _missing(graph[-1], "evidence.output", "evidence.tool_events")
    run = _finalize(graph)
    run["validity"].update(status="VALID", reason_codes=[])
    forged = add_document_digest({key: value for key, value in run.items() if key != "run_digest"}, "run_digest")
    with pytest.raises(VerificationContextError) as caught:
        verification.verify_run_graph(forged, _resolver(graph))
    assert "VALIDITY_NOT_RECOMPUTABLE" in {d.code for d in caught.value.defects}


def test_v2_store_reuses_create_only_path_and_rejects_both_draft_versions(tmp_path):
    graph = _graph()
    artifact_store = _store(tmp_path, graph)
    _missing(graph[-1], "evidence.output", "evidence.tool_events")
    run = _finalize(graph)
    created = artifact_store.create(run)
    assert created.disposition == store.WriteDisposition.CREATED
    assert created.path == str(store.run_path(run["run_id"]))
    assert artifact_store.create(run).disposition == store.WriteDisposition.IDEMPOTENT
    reopened = store.ArtifactStore(artifact_store.root)
    assert reopened.resolve_run(run["run_id"]) == run
    assert reopened.enumerate_runs() == (run,)
    assert reopened.verify_tree_graph() == ()
    changed = copy.deepcopy(graph[-1])
    changed["execution"]["termination_reason"] = "DIFFERENT_RETAINED_OUTCOME"
    with pytest.raises(ArtifactConflictError):
        artifact_store.create(_finalize(graph, changed))
    for draft in (graph[-1], build_run_draft(graph[0], graph[1], graph[3], arm_id="arm_a", replicate_index=1)):
        with pytest.raises(ContractError):
            artifact_store.create(draft)


@pytest.mark.parametrize("multi", [False, True])
def test_mixed_versions_keep_incomplete_attempts_in_population_and_refuse_omission(tmp_path, multi):
    graph = _graph()
    artifact_store = _store(tmp_path, graph)
    legacy = build_run_draft(graph[0], graph[1], graph[3], arm_id="arm_a", replicate_index=1)
    v1 = _finalize(graph, legacy)
    _missing(graph[-1], "evidence.output", "execution.model_served")
    graph[-1]["execution"].update(completion_status="FAILED", termination_reason="PROVIDER_FAILURE")
    v2 = _finalize(graph)
    passes = (_score(v1), _score(v2))
    for doc in (v1, v2, *passes):
        artifact_store.create(doc)
    assert {r["schema"] for r in artifact_store.enumerate_runs()} == {
        contracts.RUN_SCHEMA, contracts.RUN_SCHEMA_V2}
    evidence = _summary(graph, (v1, v2), passes, multi=multi)
    assert {r["run_id"] for r in evidence["run_entries"]} == {v1["run_id"], v2["run_id"]}
    entry = next(r for r in evidence["run_entries"] if r["run_id"] == v2["run_id"])
    assert entry["scored_projection"] == "INVALID_CONFIGURATION"
    artifact_store.create(evidence)
    omission = _summary(graph, (v1,), (passes[0],), multi=multi)
    with pytest.raises(VerificationContextError) as caught:
        artifact_store.create(omission)
    assert "EVIDENCE_POPULATION_INCOMPLETE" in {d.code for d in caught.value.defects}


def test_scorer_never_invents_missing_evidence_or_positive_integrity():
    graph = _graph()
    _missing(graph[-1], "evidence.output", "evidence.tool_events")
    run = _finalize(graph)
    scored = _score(run)
    assert scored["input_evidence"] == []
    assert {r["status"] for r in scored["dimension_results"]} == {"FAIL", "UNKNOWN"}
    assert all(r["evidence_refs"] == [] for r in scored["dimension_results"])
    assert scoring.verify_scorer_pass_graph(scored, _resolver(graph, run)).scope == "EVALUATION_GRAPH_VERIFIED"


@pytest.mark.parametrize("multi", [False, True])
def test_v3_incomplete_attempt_remains_in_mixed_version_population(tmp_path, multi):
    graph = _graph()
    artifact_store = _store(tmp_path, graph)
    drafts = [build_run_draft(graph[0], graph[1], graph[3], arm_id="arm_a", replicate_index=1),
              copy.deepcopy(graph[-1]), copy.deepcopy(graph[-1])]
    drafts[-1]["run_id"] = "run:" + str(uuid4())
    drafts[-1]["schema"] = contracts.RUN_DRAFT_SCHEMA_V3
    _missing(drafts[-1], "evidence.output", "execution.model_served")
    drafts[-1]["execution"].update(completion_status="FAILED", termination_reason="PROVIDER_FAILURE")
    runs = tuple(_finalize(graph, draft) for draft in drafts)
    passes = tuple(_score(run) for run in runs)
    for document in (*runs, *passes):
        artifact_store.create(document)
    assert {row["schema"] for row in artifact_store.enumerate_runs()} == contracts.RUN_SCHEMAS
    evidence = _summary(graph, runs, passes, multi=multi)
    assert {row["run_id"] for row in evidence["run_entries"]} == {run["run_id"] for run in runs}
    artifact_store.create(evidence)
    with pytest.raises(VerificationContextError) as error:
        artifact_store.create(_summary(graph, runs[:-1], passes[:-1], multi=multi))
    assert "EVIDENCE_POPULATION_INCOMPLETE" in {d.code for d in error.value.defects}


@pytest.mark.parametrize("missing", [None, "evidence.output", "execution.model_served"])
def test_harness2_accepts_complete_v2_and_refuses_incomplete_trial(tmp_path, missing):
    from scripts.ohf.harness2_recursion import Harness2CycleError, _validate_trial
    from tests.test_agent_eval_harness2_recursion import BASE, TASK, FixturePort

    class V2Port(FixturePort):
        def adjust_draft(self, label, draft):
            updated = _v2(draft)
            if missing is not None:
                _missing(updated, missing)
            draft.clear()
            draft.update(updated)

    port = V2Port(tmp_path)
    trial = port.execute(TASK, "retained-v2", BASE)
    if missing is None:
        _validate_trial(trial, BASE)
    else:
        with pytest.raises(Harness2CycleError, match="NATIVE_TRIAL_(OBSERVATION_UNAVAILABLE|INVALID)"):
            _validate_trial(trial, BASE)
        assert port.native.resolve_run(trial.run["run_id"]) == trial.run


def test_grounding_scorer_refuses_missing_output_with_typed_error():
    from scripts.agent_eval import hermes_memory_grounding
    from tests.test_agent_eval_hermes_memory_grounding import graph as grounding_graph
    args = grounding_graph()
    old = args["run"]
    draft = _v2({key: value for key, value in old.items() if key not in {"validity", "run_digest", "created_at"}})
    _missing(draft, "evidence.output")
    args["run"] = validity.finalize_run_receipt(args["scenario"], args["configuration"], args["experiment"], draft,
        **{**VALIDATOR, "validated_at": old["validity"]["validated_at"], "created_at": old["created_at"]})
    with pytest.raises(ContractError) as caught:
        hermes_memory_grounding.build_scorer_pass(**args)
    assert "RUN_OUTPUT_UNAVAILABLE" in {d.code for d in caught.value.defects}


def test_real_cli_finalizes_and_publishes_incomplete_v2_without_retrying_execution(tmp_path):
    graph = _graph()
    artifact_store = _store(tmp_path, graph)
    _missing(graph[-1], "execution.model_served", "evidence.output")
    draft_path, output_path = tmp_path / "draft.json", tmp_path / "receipt.json"
    draft_path.write_text(json.dumps(graph[-1]), encoding="utf-8")
    argv = [sys.executable, str(ROOT / "scripts/agent_evaluation.py"), "finalize-run", "--root", str(artifact_store.root),
            "--draft", str(draft_path), "--output", str(output_path)]
    for key, value in VALIDATOR.items():
        argv.extend(["--" + key.replace("_", "-"), value])
    finalized = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True, timeout=30)
    assert finalized.returncode == 1, finalized.stderr
    assert json.loads(finalized.stdout)["validity_status"] == "INVALID_CONFIGURATION"
    run = json.loads(output_path.read_text(encoding="utf-8"))
    assert run["schema"] == contracts.RUN_SCHEMA_V2
    assert run["execution"]["model_served"] is None
    created = subprocess.run([sys.executable, str(ROOT / "scripts/agent_evaluation.py"), "create", "--root",
                              str(artifact_store.root), str(output_path)], cwd=ROOT,
                             capture_output=True, text=True, timeout=30)
    assert created.returncode == 0, created.stderr
    assert json.loads(created.stdout)["disposition"] == "CREATED"
    assert artifact_store.resolve_run(run["run_id"]) == run
