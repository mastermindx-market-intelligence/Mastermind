"""EVAL-S1: multi-scenario summarization (docs/superpowers/plans/2026-09-01-
agent-evaluation-s1-scorers.md).

Proves the ``scenario_refs[0]`` limitation this wave replaces:
``scripts/agent_eval/cli.py::_cmd_summarize`` used to resolve exactly ONE
scenario and apply its ``required_dimensions`` to EVERY matching run,
regardless of which scenario a run actually belonged to. E1 pairs 3
scenarios in one experiment, so 2 of 3 scenarios' runs would have been
scored against the wrong required-dimension set. These tests build TWO
scenarios with DIFFERENT ``required_dimensions``, bind runs to each, and
show the old single-scenario recompute gives the WRONG projection for the
non-primary scenario's run while the new multi-scenario summarize gives the
correct one.

The multi-scenario evidence reference (``mastermind.agent_evaluation_
evidence_ref_multi_scenario.v1``) is a distinct schema from R0's single-
scenario one and is NOT yet wired into ``ArtifactStore.create()`` (a
disclosed S1 limitation -- see the plan record and the PR body); it is
built, shape-validated, graph-verified, and persisted via the same
exclusive create-only file primitive the CLI already uses for
``finalize-run --output``.
"""
from __future__ import annotations

import copy
import json
import uuid

import pytest

from scripts.agent_eval import cli, contracts, scoring, store, validity
from scripts.agent_eval.errors import ContractError, VerificationContextError
from tests.agent_eval_factories import (
    MemoryArtifactResolver,
    build_baseline_configuration,
    build_baseline_scenario_fields,
    build_run_draft,
    fresh_experiment_id,
    fresh_run_id,
)

VALIDATOR_KW = dict(
    validator_id="mastermind.eval_r0_finalizer.v1",
    validator_version="1",
    validator_code_ref="git:mastermindx-market-intelligence/Mastermind@" + "a" * 40,
    validated_at="2026-09-01T00:00:10Z",
    created_at="2026-09-01T00:00:11Z",
)
SCORER_CODE_REF = "git:mastermindx-market-intelligence/Mastermind@" + "a" * 40


def _fresh_scorer_pass_id() -> str:
    return f"scorer-pass:{uuid.uuid4()}"


def _fresh_evidence_ref_id() -> str:
    return f"evidence-ref:{uuid.uuid4()}"


def _scenario_with(*, case: str, required_dimensions: list[str]) -> dict:
    fields = copy.deepcopy(build_baseline_scenario_fields())
    fields["scenario_id"] = f"scenario:evaluation_contract_integrity:{case}"
    fields["scoring_policy"] = dict(fields["scoring_policy"])
    fields["scoring_policy"]["required_dimensions"] = sorted(set(required_dimensions))
    return contracts.build_scenario(fields)


def _two_scenario_experiment(scenario_a: dict, scenario_b: dict, config_a: dict, config_b: dict) -> dict:
    def _ref(scenario: dict) -> dict:
        return {
            "scenario_id": scenario["scenario_id"],
            "scenario_version": scenario["scenario_version"],
            "scenario_digest": scenario["scenario_digest"],
            "corpus_revision": scenario["corpus_revision"],
        }

    fields = {
        "experiment_id": fresh_experiment_id(),
        "scenario_refs": sorted(
            [_ref(scenario_a), _ref(scenario_b)], key=lambda r: (r["scenario_id"], r["scenario_version"])
        ),
        "arms": sorted(
            [
                {"arm_id": "arm_a", "configuration_id": config_a["configuration_id"], "configuration_digest": config_a["configuration_digest"]},
                {"arm_id": "arm_b", "configuration_id": config_b["configuration_id"], "configuration_digest": config_b["configuration_digest"]},
            ],
            key=lambda item: item["arm_id"],
        ),
        "pairing": {"method": "PAIRED_BY_SCENARIO", "random_seed": None},
        "replicates_per_arm_target": 1,
        "stopping_rule": {"kind": "FIXED_REPLICATES_PER_ARM", "value": 1},
        "primary_dimensions": ["configuration_integrity"],
        "guardrail_dimensions": ["cleanup_integrity"],
        "analysis_version": "mastermind.agent_evaluation_r0_analysis.v1",
        "phase": "RETROSPECTIVE",
        "authorship": {"author_ref": "person:sol", "independent_reviewer_ref": "person:auditor"},
        "created_at": "2026-09-01T00:00:00Z",
    }
    return contracts.build_experiment(fields)


def _hand_scored_pass(run: dict, *, dimension: str, status: str) -> dict:
    return scoring.build_scorer_pass_document(
        run,
        scorer_pass_id=_fresh_scorer_pass_id(),
        scorer_id="mastermind.tc1_source_comprehension.v1",
        scorer_version="1",
        scorer_code_ref=SCORER_CODE_REF,
        method="DETERMINISTIC",
        dimension_results=[{"dimension": dimension, "status": status, "reason_codes": [], "evidence_refs": []}],
        created_at="2026-09-01T00:00:12Z",
    )


@pytest.fixture()
def two_scenario_graph():
    """scenario_a requires 'configuration_integrity' only; scenario_b
    requires 'completeness' only (a dimension NO scorer in this fixture
    ever produces). run_a1 is scored PASS on configuration_integrity;
    run_a2 is scored FAIL on configuration_integrity (both under
    scenario_a); run_b is scored only on configuration_integrity too (never
    on 'completeness') -- so under its OWN scenario_b it must be UNSCORED,
    even though it superficially "has data" for scenario_a's dimension."""
    scenario_a = _scenario_with(case="case_a", required_dimensions=["configuration_integrity"])
    scenario_b = _scenario_with(case="case_b", required_dimensions=["completeness"])
    config_a = build_baseline_configuration()
    config_b = build_baseline_configuration()
    experiment = _two_scenario_experiment(scenario_a, scenario_b, config_a, config_b)

    draft_a1 = build_run_draft(scenario_a, config_a, experiment, arm_id="arm_a", replicate_index=1)
    run_a1 = validity.finalize_run_receipt(scenario_a, config_a, experiment, draft_a1, **VALIDATOR_KW)
    draft_a2 = build_run_draft(scenario_a, config_a, experiment, arm_id="arm_a", replicate_index=1, run_id=fresh_run_id())
    run_a2 = validity.finalize_run_receipt(scenario_a, config_a, experiment, draft_a2, **VALIDATOR_KW)
    draft_b = build_run_draft(scenario_b, config_b, experiment, arm_id="arm_b", replicate_index=1)
    run_b = validity.finalize_run_receipt(scenario_b, config_b, experiment, draft_b, **VALIDATOR_KW)

    pass_a1 = _hand_scored_pass(run_a1, dimension="configuration_integrity", status="PASS")
    pass_a2 = _hand_scored_pass(run_a2, dimension="configuration_integrity", status="FAIL")
    pass_b = _hand_scored_pass(run_b, dimension="configuration_integrity", status="PASS")  # never "completeness"

    return dict(
        scenario_a=scenario_a,
        scenario_b=scenario_b,
        config_a=config_a,
        config_b=config_b,
        experiment=experiment,
        run_a1=run_a1,
        run_a2=run_a2,
        run_b=run_b,
        pass_a1=pass_a1,
        pass_a2=pass_a2,
        pass_b=pass_b,
    )


def test_old_single_scenario_recompute_misapplies_scenario_a_to_run_b(two_scenario_graph) -> None:
    """Pins the BUG this wave fixes: R0's own (untouched) single-scenario
    ``summarize_experiment``, given scenario_a as "the" scenario for an
    experiment that actually has two, silently applies scenario_a's
    required_dimensions to run_b too -- and since run_b's scorer pass
    happens to also carry 'configuration_integrity', it is WRONGLY reported
    VALID_PASS instead of the correct UNSCORED (scenario_b requires
    'completeness', which run_b was never scored on)."""
    g = two_scenario_graph
    evidence = scoring.summarize_experiment(
        g["experiment"],
        g["scenario_a"],  # the scenario_refs[0]-style shortcut
        (g["run_a1"], g["run_a2"], g["run_b"]),
        (g["pass_a1"], g["pass_a2"], g["pass_b"]),
        evidence_ref_id=_fresh_evidence_ref_id(),
        intended_owner="person:sol",
        review_at="2026-09-08T00:00:00Z",
        created_at="2026-09-01T00:00:13Z",
        analysis_version="mastermind.agent_evaluation_r0_analysis.v1",
    )
    by_run = {e["run_id"]: e for e in evidence["run_entries"]}
    assert by_run[g["run_b"]["run_id"]]["scored_projection"] == "VALID_PASS"  # WRONG -- the bug


def test_multi_scenario_summarize_resolves_required_dimensions_per_scenario(two_scenario_graph) -> None:
    g = two_scenario_graph
    evidence = scoring.summarize_multi_scenario_experiment(
        g["experiment"],
        (g["scenario_a"], g["scenario_b"]),
        (g["run_a1"], g["run_a2"], g["run_b"]),
        (g["pass_a1"], g["pass_a2"], g["pass_b"]),
        evidence_ref_id=_fresh_evidence_ref_id(),
        intended_owner="person:sol",
        review_at="2026-09-08T00:00:00Z",
        created_at="2026-09-01T00:00:13Z",
        analysis_version="mastermind.agent_evaluation_r0_analysis.v1",
    )
    assert scoring.validate_multi_scenario_evidence_ref_shape(evidence) == "SHAPE_VALID"

    by_run = {e["run_id"]: e for e in evidence["run_entries"]}
    assert by_run[g["run_a1"]["run_id"]]["scored_projection"] == "VALID_PASS"
    assert by_run[g["run_a2"]["run_id"]]["scored_projection"] == "VALID_FAIL"
    # the fix: run_b is correctly UNSCORED under its OWN scenario (scenario_b
    # requires 'completeness', never produced for run_b) -- never the WRONG
    # VALID_PASS the old single-scenario recompute produced above.
    assert by_run[g["run_b"]["run_id"]]["scored_projection"] == "UNSCORED"

    groups = {(g_["scenario_id"], g_["scenario_version"]): g_ for g_ in evidence["scenario_groups"]}
    group_a = groups[(g["scenario_a"]["scenario_id"], g["scenario_a"]["scenario_version"])]
    group_b = groups[(g["scenario_b"]["scenario_id"], g["scenario_b"]["scenario_version"])]
    assert group_a["sample_size"] == 2
    assert group_a["counts"]["valid_count"] == 2
    assert group_b["sample_size"] == 1
    assert group_b["counts"]["unscored_count"] == 1
    # top-level counts aggregate across every scenario group
    assert evidence["counts"]["total_count"] == 3
    assert evidence["evidence_grade"] == "INSUFFICIENT_EVIDENCE"
    assert "EVIDENCE_CONTENT_VERIFIED" not in evidence["verification_scopes"]


def test_multi_scenario_summarize_graph_verifies(two_scenario_graph) -> None:
    g = two_scenario_graph
    evidence = scoring.summarize_multi_scenario_experiment(
        g["experiment"],
        (g["scenario_a"], g["scenario_b"]),
        (g["run_a1"], g["run_a2"], g["run_b"]),
        (g["pass_a1"], g["pass_a2"], g["pass_b"]),
        evidence_ref_id=_fresh_evidence_ref_id(),
        intended_owner="person:sol",
        review_at="2026-09-08T00:00:00Z",
        created_at="2026-09-01T00:00:13Z",
        analysis_version="mastermind.agent_evaluation_r0_analysis.v1",
    )
    resolver = MemoryArtifactResolver.build(
        scenarios=(g["scenario_a"], g["scenario_b"]),
        experiments=(g["experiment"],),
        runs=(g["run_a1"], g["run_a2"], g["run_b"]),
        scorer_passes=(g["pass_a1"], g["pass_a2"], g["pass_b"]),
    )
    result = scoring.verify_multi_scenario_evidence_ref_graph(evidence, resolver)
    assert result.scope == "EVALUATION_GRAPH_VERIFIED"


def test_a_run_from_a_scenario_absent_in_the_manifest_fails(two_scenario_graph) -> None:
    g = two_scenario_graph
    # a THIRD scenario, never declared in the experiment's own scenario_refs.
    # R0's OWN finalizer (design §7.6) will independently flag this
    # scenario/configuration as not belonging to the experiment (technical_
    # validity INVALID_CONFIGURATION) -- that is expected and irrelevant
    # here: this test targets the SEPARATE, NEW summarize-time structural
    # guard, which must reject the run before ever consulting its
    # technical_validity (an undeclared scenario is never silently
    # included, valid or not).
    rogue_scenario = _scenario_with(case="rogue", required_dimensions=["configuration_integrity"])
    rogue_config = build_baseline_configuration()
    rogue_draft = build_run_draft(rogue_scenario, rogue_config, g["experiment"], arm_id="arm_a", replicate_index=1, run_id=fresh_run_id())
    rogue_run = validity.finalize_run_receipt(rogue_scenario, rogue_config, g["experiment"], rogue_draft, **VALIDATOR_KW)

    with pytest.raises(ContractError) as excinfo:
        scoring.summarize_multi_scenario_experiment(
            g["experiment"],
            (g["scenario_a"], g["scenario_b"]),  # rogue_scenario deliberately NOT supplied
            (g["run_a1"], rogue_run),
            (g["pass_a1"],),
            evidence_ref_id=_fresh_evidence_ref_id(),
            intended_owner="person:sol",
            review_at="2026-09-08T00:00:00Z",
            created_at="2026-09-01T00:00:13Z",
            analysis_version="mastermind.agent_evaluation_r0_analysis.v1",
        )
    assert any(d.code == "SCENARIO_NOT_IN_EXPERIMENT" for d in excinfo.value.defects)


def _create_full_graph(artifact_store: "store.ArtifactStore", g: dict) -> None:
    for doc in (g["scenario_a"], g["scenario_b"], g["config_a"], g["config_b"], g["experiment"]):
        artifact_store.create(doc)
    for doc in (g["run_a1"], g["run_a2"], g["run_b"]):
        artifact_store.create(doc)
    for doc in (g["pass_a1"], g["pass_a2"], g["pass_b"]):
        artifact_store.create(doc)


# ---------------------------------------------------------------------------
# Store integration (EVAL-S1 store-integration wave, same operation key):
# the multi-scenario evidence reference is now published through the SAME
# governed create-only ArtifactStore.create() path, with the SAME
# enumeration-equality anti-laundering guarantee BLOCKER-1 gave R0's
# single-scenario schema (tests/test_agent_eval_store.py::
# test_create_refuses_an_evidence_ref_over_a_cherry_picked_run_subset /
# test_hand_planted_subset_evidence_ref_is_flagged_by_verify_tree_graph).
# ---------------------------------------------------------------------------


def test_honest_multi_scenario_evidence_ref_publishes_and_tree_verifies_clean(two_scenario_graph, tmp_path) -> None:
    g = two_scenario_graph
    artifact_store = store.ArtifactStore(tmp_path / "root")
    _create_full_graph(artifact_store, g)

    evidence = scoring.summarize_multi_scenario_experiment(
        g["experiment"],
        (g["scenario_a"], g["scenario_b"]),
        artifact_store.enumerate_runs(),
        artifact_store.enumerate_scorer_passes(),
        evidence_ref_id=_fresh_evidence_ref_id(),
        intended_owner="person:sol",
        review_at="2026-09-08T00:00:00Z",
        created_at="2026-09-01T00:00:13Z",
        analysis_version="mastermind.agent_evaluation_r0_analysis.v1",
    )
    result = artifact_store.create(evidence)
    assert result.disposition.value == "CREATED"
    assert artifact_store.resolve_evidence_ref(evidence["evidence_ref_id"]) == evidence
    assert artifact_store.verify_tree_graph() == ()


def test_create_refuses_a_multi_scenario_evidence_ref_over_a_cherry_picked_scenario_subset(two_scenario_graph, tmp_path) -> None:
    # mirrors test_create_refuses_an_evidence_ref_over_a_cherry_picked_run_subset
    # exactly, one scenario up: summarize_multi_scenario_experiment ITSELF is
    # internally consistent with whatever subset it is handed (it only
    # requires supplied scenarios to match the EXPERIMENT's declared set,
    # not that every declared run is present) -- the refusal must come from
    # the store recomputing against its OWN complete enumeration.
    g = two_scenario_graph
    artifact_store = store.ArtifactStore(tmp_path / "root")
    _create_full_graph(artifact_store, g)

    laundered_evidence = scoring.summarize_multi_scenario_experiment(
        g["experiment"],
        (g["scenario_a"], g["scenario_b"]),
        (g["run_a1"],),  # run_a2 and run_b silently dropped from the population
        (g["pass_a1"],),
        evidence_ref_id=_fresh_evidence_ref_id(),
        intended_owner="person:sol",
        review_at="2026-09-08T00:00:00Z",
        created_at="2026-09-01T00:00:13Z",
        analysis_version="mastermind.agent_evaluation_r0_analysis.v1",
    )
    assert laundered_evidence["sample_size"] == 1  # the laundering is internally "clean"

    with pytest.raises(VerificationContextError) as excinfo:
        artifact_store.create(laundered_evidence)
    assert any(d.code == "EVIDENCE_POPULATION_INCOMPLETE" for d in excinfo.value.defects)
    assert artifact_store.resolve_evidence_ref(laundered_evidence["evidence_ref_id"]) is None


def test_hand_planted_subset_multi_scenario_evidence_ref_is_flagged_by_verify_tree_graph(two_scenario_graph, tmp_path) -> None:
    from scripts.agent_eval.canonical import canonical_json_bytes

    g = two_scenario_graph
    artifact_store = store.ArtifactStore(tmp_path / "root")
    _create_full_graph(artifact_store, g)

    laundered_evidence = scoring.summarize_multi_scenario_experiment(
        g["experiment"],
        (g["scenario_a"], g["scenario_b"]),
        (g["run_a1"],),
        (g["pass_a1"],),
        evidence_ref_id=_fresh_evidence_ref_id(),
        intended_owner="person:sol",
        review_at="2026-09-08T00:00:00Z",
        created_at="2026-09-01T00:00:13Z",
        analysis_version="mastermind.agent_evaluation_r0_analysis.v1",
    )

    # hand-plant it directly at its own canonical path, bypassing create()
    final_path = artifact_store.root / store.evidence_ref_path(laundered_evidence["evidence_ref_id"])
    final_path.parent.mkdir(parents=True, exist_ok=True)
    final_path.write_bytes(canonical_json_bytes(laundered_evidence))

    defects = artifact_store.verify_tree_graph()
    assert any(d.code == "EVIDENCE_POPULATION_INCOMPLETE" for d in defects)


# ---------------------------------------------------------------------------
# CLI: multi-scenario summarize journey (now store-published end-to-end)
# ---------------------------------------------------------------------------


def test_cli_summarize_multi_scenario_publishes_through_the_store_and_tree_verifies_clean(two_scenario_graph, tmp_path, capsys) -> None:
    g = two_scenario_graph
    root = tmp_path / "root"
    artifact_store = store.ArtifactStore(root)
    _create_full_graph(artifact_store, g)

    exit_code = cli.main(
        [
            "summarize",
            "--root",
            str(root),
            "--experiment-id",
            g["experiment"]["experiment_id"],
            "--owner",
            "person:sol",
            "--review-at",
            "2026-09-08T00:00:00Z",
            "--created-at",
            "2026-09-01T00:00:13Z",
            "--id",
            _fresh_evidence_ref_id(),
        ]
    )
    assert exit_code == 1  # R0/S1's evidence grade is always INSUFFICIENT_EVIDENCE

    out = capsys.readouterr().out
    printed = json.loads(out)
    assert printed["disposition"] == "CREATED"
    assert printed["evidence_grade"] == "INSUFFICIENT_EVIDENCE"
    assert len(printed["scenario_groups"]) == 2

    stored = artifact_store.resolve_evidence_ref(printed["evidence_ref_id"])
    assert stored is not None
    assert stored["schema"] == "mastermind.agent_evaluation_evidence_ref_multi_scenario.v1"

    tree_verify_exit = cli.main(["verify-tree-graph", "--root", str(root)])
    assert tree_verify_exit == 0
    tree_verify_out = json.loads(capsys.readouterr().out)
    assert tree_verify_out["defect_count"] == 0
