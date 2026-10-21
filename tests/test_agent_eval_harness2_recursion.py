"""Native Harness2 mechanism tests; scripted improver, never model-efficacy proof.

The optional subprocess executes only this test's fixed arithmetic program.
Native EVAL declarations are explicit synthetic fixtures, not live attestations.
"""
from __future__ import annotations

import copy
import subprocess
import sys
from dataclasses import replace
from uuid import uuid4

import pytest

from scripts.agent_eval import contracts, store, validity
from scripts.agent_eval.canonical import digest_value
from scripts.agent_eval.harness2_native import harness_digest, sha256_bytes
from scripts.ohf.harness2_recursion import Harness2CycleError, Limits, Proposal, Trial, run_refinement
from tests.agent_eval_factories import (
    REPO_REF_BASE, build_baseline_scenario_fields, build_baseline_configuration,
    build_two_arm_experiment, build_alternate_configuration, build_run_draft,
)

BASE = {"AGENTS.md": b"Protected fixture: execute only the admitted task.\n",
        "scripts/total.py": b"numbers = (100, -20, 5)\nprint(sum(n for n in numbers if n > 0))\n"}
TASK = {"task_id": "signed-ledger", "domain": "accounting", "request": "Sum all signed amounts: 100, -20, 5."}


class FixturePort:
    def __init__(self, root, *, real_process=False):
        self.root = root
        self.real_process = real_process
        self.native = store.ArtifactStore(root / "eval")
        fields = build_baseline_scenario_fields()
        fields["objective"] = TASK["request"]
        self.scenario = contracts.build_scenario(fields)
        config = build_baseline_configuration()
        config.pop("schema")
        config.pop("configuration_digest")
        config["execution"].update(provider="fixture", model_requested="deterministic-fixture")
        config["procedure"]["instruction_bundle"] = {
            "artifact_ref": REPO_REF_BASE + "#fixture/base.json", "digest": harness_digest(BASE)}
        self.base_configuration = contracts.build_configuration(config)
        self.calls = []
        self.contexts = []
        self.trials = {}
        self.selected_views = []
        self.before_trial = None
        self.proposal_mutation = None
        self.reflection_mutation = None

    def execute(self, task, label, files):
        self.calls.append(("execute", label, copy.deepcopy(files)))
        cfg = copy.deepcopy(self.base_configuration)
        cfg.pop("schema")
        cfg.pop("configuration_digest")
        cfg["configuration_id"] = "configuration:" + str(uuid4())
        cfg["procedure"]["instruction_bundle"] = {
            "artifact_ref": REPO_REF_BASE + "#fixture/" + harness_digest(files)[7:] + ".json",
            "digest": harness_digest(files)}
        if self.before_trial:
            self.before_trial(label, cfg)
        cfg = contracts.build_configuration(cfg)
        other = build_alternate_configuration()
        experiment = build_two_arm_experiment(self.scenario, cfg, other)
        if self.real_process:
            script = self.root / ("arithmetic-" + str(len(self.calls)) + ".py")
            script.write_bytes(files["scripts/total.py"])
            response = subprocess.run([sys.executable, "-B", str(script)], capture_output=True, timeout=10, check=True)
            output = response.stdout
        else:
            output = b"105\n" if b"if n > 0" in files["scripts/total.py"] else b"85\n"
        draft = build_run_draft(self.scenario, cfg, experiment, arm_id="arm_a", replicate_index=1)
        draft["evidence"]["output"] = {"artifact_ref": REPO_REF_BASE + "#fixture/output/" + str(uuid4()),
                                         "digest": sha256_bytes(output)}
        self.adjust_draft(label, draft)
        run = validity.finalize_run_receipt(self.scenario, cfg, experiment, draft,
            validator_id="mastermind.fixture.validator.v1", validator_version="1",
            validator_code_ref=REPO_REF_BASE, validated_at="2026-08-26T00:00:00Z",
            created_at="2026-08-26T00:00:00Z")
        for doc in (self.scenario, cfg, other, experiment, run):
            self.native.create(doc)
        trial = Trial(self.scenario, cfg, experiment, run, output)
        self.trials[label] = trial
        return trial

    def adjust_draft(self, label, draft):
        pass

    def improve(self, task, label, kind, context):
        self.calls.append((kind, label))
        self.contexts.append((label, copy.deepcopy(context)))
        # The model-facing packet must not contain graders or native authority envelopes.
        assert "expected_contract" not in repr(context)
        assert "solution_refs_hidden" not in repr(context)
        files = copy.deepcopy(context["current_harness"])
        files["scripts/total.py"] = files["scripts/total.py"].replace(b" if n > 0", b"")
        if self.proposal_mutation:
            self.proposal_mutation(label, files, context)
        return Proposal(files, "Remove the positive-only filter; retain credits and debits.",
                        tuple(item["run_id"] for item in context["executions"][:2]))

    def select(self, task, candidates):
        self.calls.append(("select",))
        self.selected_views.append(copy.deepcopy(candidates))
        assert all(type(key) is str and len(key) == 1 and type(value) is bytes
                   for key, value in candidates.items())
        return sorted(candidates)[0]

    def reflect(self, task, chosen, context):
        self.calls.append(("reflect",))
        assert set(chosen) == {"run_id", "output", "harness_digest"}
        assert "expected_contract" not in repr(context)
        ids = [context["executions"][0]["run_id"], chosen["run_id"]]
        answer = {"claim": "The positive-only filter excluded a signed credit in this fixture.",
                  "falsifier": "Replay the signed inputs and compare output with the direct arithmetic sum.",
                  "so_what": "Keep negative as well as positive ledger amounts when adapting this helper.",
                  "evidence_run_ids": ids}
        return self.reflection_mutation(answer) if self.reflection_mutation else answer


def invoke(port, *, mode="agg", k=1, experience=(), limits=None):
    return run_refinement(task=TASK, common_base=BASE, expected_scenario=port.scenario,
        baseline_configuration=port.base_configuration, prior_experience=experience,
        allowed_edit_paths=frozenset({"scripts/total.py"}), k=k, mode=mode,
        limits=limits or Limits(4 * k, 3 * k + 1 + (k > 1), 7), port=port)


@pytest.mark.parametrize("mode,k", [("agg", 1), ("agg", 2), ("seq", 1), ("seq", 2), ("seq", 3)])
def test_both_search_modes_use_existing_native_receipts(tmp_path, mode, k):
    port = FixturePort(tmp_path)
    before = copy.deepcopy(BASE)
    result = invoke(port, mode=mode, k=k)
    assert result["selected_output"] == b"85\n"
    assert result["rollout_count"] == 4 * k
    assert result["improver_call_count"] == 3 * k + 1 + (k > 1)
    assert result["promotion"] == "NONE" and result["automatic_memory_write"] is False
    assert len(result["experience_candidate"]["evidence_run_ids"]) >= 2
    assert BASE == before
    for run_id in result["retained_native_runs"]:
        assert port.native.resolve_run(run_id)["validity"]["status"] == "VALID"
    assert bool(port.selected_views) == (k > 1)


def test_real_local_program_contrast(tmp_path):
    port = FixturePort(tmp_path, real_process=True)
    result = invoke(port)
    assert port.trials["base1"].output == b"105\n"
    assert result["selected_output"] == b"85\n"
    assert len(list(tmp_path.glob("arithmetic-*.py"))) == 4


def test_parallel_compositions_do_not_inherit_previous_composition(tmp_path):
    port = FixturePort(tmp_path)
    invoke(port, k=2)
    compose = [ctx for label, ctx in port.contexts if label.startswith("agg")]
    assert len(compose) == 2
    for ctx in compose:
        assert ctx["current_harness"] == BASE
        assert all(not row["label"].startswith("agg") for row in ctx["executions"])


def test_sequential_round_two_inherits_executed_round_one(tmp_path):
    port = FixturePort(tmp_path)
    invoke(port, k=2, mode="seq")
    second = next(ctx for label, ctx in port.contexts if label == "inv2")
    assert b"if n > 0" not in second["current_harness"]["scripts/total.py"]
    assert "c1" in {row["label"] for row in second["executions"]}


def test_unadmitted_budget_makes_no_calls(tmp_path):
    port = FixturePort(tmp_path)
    with pytest.raises(Harness2CycleError, match="CEILING_INSUFFICIENT"):
        invoke(port, k=2, limits=Limits(7, 8, 0))
    assert port.calls == []


def test_unapproved_harness_path_never_executes(tmp_path):
    port = FixturePort(tmp_path)
    port.proposal_mutation = lambda label, files, context: files.update({"AGENTS.md": b"change policy"})
    with pytest.raises(Harness2CycleError, match="OUTSIDE_ADMITTED_SURFACE") as error:
        invoke(port)
    assert [call[1] for call in port.calls if call[0] == "execute"] == ["base1"]
    assert len(error.value.retained_run_ids) == 1


def test_changed_model_even_on_first_base_is_refused(tmp_path):
    port = FixturePort(tmp_path)
    port.before_trial = lambda label, cfg: cfg["execution"].update(model_requested="unexpected-model")
    with pytest.raises(Harness2CycleError, match="MATCHED_CONFIGURATION_CHANGED"):
        invoke(port)
    assert len(port.calls) == 1


def test_effect_unknown_is_retained_and_stops_without_retry(tmp_path):
    class UnknownPort(FixturePort):
        def adjust_draft(self, label, draft):
            if label == "inv1":
                draft["effect"] = {"state": "EFFECT_UNKNOWN", "operation_ref": "op:uncertain", "reconciliation_ref": None}
    port = UnknownPort(tmp_path)
    with pytest.raises(Harness2CycleError, match="RECONCILIATION") as error:
        invoke(port)
    assert [call[1] for call in port.calls if call[0] == "execute"] == ["base1", "inv1"]
    assert port.trials["inv1"].run["run_id"] in error.value.retained_run_ids
    assert port.native.resolve_run(port.trials["inv1"].run["run_id"])["validity"]["status"] == "INVALID_EFFECT_UNKNOWN"


def test_ambiguous_owner_call_is_not_replayed(tmp_path):
    class TimeoutPort(FixturePort):
        def execute(self, task, label, files):
            if label == "inv1":
                self.calls.append(("execute", label))
                raise TimeoutError("simulated interrupted owner call; reconcile incumbent")
            return super().execute(task, label, files)
    port = TimeoutPort(tmp_path)
    with pytest.raises(Harness2CycleError, match="OWNER_CALL") as error:
        invoke(port)
    assert len(error.value.retained_run_ids) == 1
    assert [c[1] for c in port.calls if c[0] == "execute"] == ["base1", "inv1"]


def test_second_task_uses_library_but_restarts_at_common_base(tmp_path):
    port = FixturePort(tmp_path)
    first = invoke(port)
    proposal = first["experience_candidate"]
    # Simulated already-admitted Agent OS read, not an automatic actual store write.
    entry = {"discovery_ref": "DSC:SIGNED-LEDGER", "source_ref": REPO_REF_BASE + "#agentos/discoveries/DSC-SIGNED-LEDGER.md",
             "domain": "accounting", "harness_artifact": first["selected_harness_artifact"],
             **{key: proposal[key] for key in ("claim", "falsifier", "so_what")}}
    before = copy.deepcopy(entry)
    port.contexts.clear()
    second = invoke(port, experience=(entry,))
    assert port.trials["base1"].output == b"105\n"
    assert second["selected_output"] == b"85\n"
    assert all(ctx["prior_experience"][0] == entry for _label, ctx in port.contexts)
    assert entry == before and BASE["AGENTS.md"].startswith(b"Protected")


def test_model_cannot_mutate_frozen_library(tmp_path):
    port = FixturePort(tmp_path)
    entry = {"discovery_ref": "DSC:FIXTURE", "source_ref": REPO_REF_BASE, "domain": "accounting",
             "claim": "prior", "falsifier": "test", "so_what": "use credits",
             "harness_artifact": port.base_configuration["procedure"]["instruction_bundle"]}
    def mutate(label, files, context):
        assert context["prior_experience"][0]["claim"] == "prior"
        context["prior_experience"][0]["claim"] = "tamper"
    port.proposal_mutation = mutate
    invoke(port, experience=(entry,))
    assert entry["claim"] == "prior"


def test_selector_cannot_choose_an_unexecuted_harness(tmp_path):
    class BadSelector(FixturePort):
        def select(self, task, candidates):
            return "unexecuted-candidate"
    port = BadSelector(tmp_path)
    with pytest.raises(Harness2CycleError, match="SELECTION_NOT_IN_FINALS") as error:
        invoke(port, k=2)
    assert len(error.value.retained_run_ids) == 8
    assert not any(call[0] == "reflect" for call in port.calls)


def test_unbound_reflection_is_not_memory(tmp_path):
    port = FixturePort(tmp_path)
    port.reflection_mutation = lambda value: dict(value, evidence_run_ids=["invented-1", "invented-2"])
    with pytest.raises(Harness2CycleError, match="REFLECTION_EVIDENCE_UNBOUND"):
        invoke(port)


def test_reflection_may_produce_no_entry(tmp_path):
    port = FixturePort(tmp_path)
    port.reflection_mutation = lambda value: None
    result = invoke(port)
    assert result["experience_candidate"] is None
    assert result["selected_output"] == b"85\n"
    assert result["automatic_memory_write"] is False


def test_output_tamper_refused_before_improver(tmp_path):
    class ChangedOutput(FixturePort):
        def execute(self, task, label, files):
            return replace(super().execute(task, label, files), output=b"fabricated output")
    port = ChangedOutput(tmp_path)
    with pytest.raises(Harness2CycleError, match="TRIAL_OUTPUT_CHANGED") as error:
        invoke(port)
    assert len(error.value.retained_run_ids) == 1
    assert len(port.calls) == 1


def test_one_native_run_cannot_count_as_two_baselines(tmp_path):
    class ReusedRun(FixturePort):
        def execute(self, task, label, files):
            if label == "base2":
                self.calls.append(("execute", label))
                return self.trials["base1"]
            return super().execute(task, label, files)
    port = ReusedRun(tmp_path)
    with pytest.raises(Harness2CycleError, match="NATIVE_RUN_REUSED"):
        invoke(port, k=2)
    assert len(port.calls) == 2


def test_library_from_another_domain_is_not_used(tmp_path):
    port = FixturePort(tmp_path)
    entry = {"discovery_ref": "DSC:FIXTURE", "source_ref": REPO_REF_BASE, "domain": "other",
             "claim": "prior", "falsifier": "test", "so_what": "use credits",
             "harness_artifact": port.base_configuration["procedure"]["instruction_bundle"]}
    with pytest.raises(Harness2CycleError, match="EXPERIENCE_DOMAIN_MISMATCH"):
        invoke(port, experience=(entry,))
    assert not port.calls


def test_invalid_cleanup_is_not_relabelled_success(tmp_path):
    class DirtyPort(FixturePort):
        def adjust_draft(self, label, draft):
            draft["cleanup"] = {"status": "UNPROVEN", "proof": None}
    port = DirtyPort(tmp_path)
    with pytest.raises(Harness2CycleError, match="NATIVE_TRIAL_INVALID") as error:
        invoke(port)
    assert len(error.value.retained_run_ids) == 1
    assert port.native.resolve_run(error.value.retained_run_ids[0])["validity"]["status"] == "INVALID_CLEANUP"


def test_model_proposal_without_bound_evidence_is_refused(tmp_path):
    class UngroundedPort(FixturePort):
        def improve(self, task, label, kind, context):
            value = super().improve(task, label, kind, context)
            return replace(value, evidence_run_ids=("invented",))
    port = UngroundedPort(tmp_path)
    with pytest.raises(Harness2CycleError, match="PROPOSAL_EVIDENCE_UNBOUND"):
        invoke(port)
    assert len(port.trials) == 1


def _invoke_context(port, context_inputs, prior=()):
    return run_refinement(task=TASK, common_base=BASE, expected_scenario=port.scenario,
        baseline_configuration=port.base_configuration, prior_experience=prior,
        allowed_edit_paths=frozenset({"scripts/total.py"}), k=1, mode="agg",
        limits=Limits(4, 4, 7), port=port, agentos_context_inputs=context_inputs)


def test_native_agentos_context_guides_refinement_without_dropping_higher_law(tmp_path):
    from tests.test_agent_eval_harness2_context import inputs, bundle_fixture
    port = FixturePort(tmp_path)
    context_inputs = inputs()
    cfg = copy.deepcopy(port.base_configuration)
    cfg.pop("schema")
    cfg.pop("configuration_digest")
    cfg["context"]["context_packet"] = {"artifact_ref": "artifact:native-agentos-context",
                                        "digest": context_inputs["expected_bundle_digest"]}
    port.base_configuration = contracts.build_configuration(cfg)
    result = _invoke_context(port, context_inputs)
    assert result["selected_output"] == b"85\n"
    assert result["context_bundle_digest"] == context_inputs["expected_bundle_digest"]
    for label, context in port.contexts:
        assert context["organizational_context"] == bundle_fixture()
        assert context["prior_experience"][0]["confidence"] == "verified"
        assert context["prior_experience"][0]["source_run_ids"]
        assert context["organizational_context"]["degraded"]
        assert context["organizational_context"]["sections"][0]["items"][0]["key"] == "DNR:NO-DUPLICATE"


def test_context_packet_must_match_the_native_configuration_before_calls(tmp_path):
    from tests.test_agent_eval_harness2_context import inputs
    port = FixturePort(tmp_path)
    with pytest.raises(Harness2CycleError, match="NATIVE_CONTEXT_PACKET_MISMATCH"):
        _invoke_context(port, inputs())
    assert not port.calls


def test_agentos_context_cannot_be_combined_with_an_unbound_extra_library(tmp_path):
    from tests.test_agent_eval_harness2_context import inputs
    port = FixturePort(tmp_path)
    with pytest.raises(Harness2CycleError, match="CONTEXT_LIBRARY_MUST_NOT_BE_MIXED"):
        _invoke_context(port, inputs(), prior=({"claim": "unbound"},))
    assert not port.calls


def test_context_task_domain_mismatch_is_pre_effect(tmp_path):
    from tests.test_agent_eval_harness2_context import inputs
    port = FixturePort(tmp_path)
    args = inputs()
    args["task_domain"] = "other"
    with pytest.raises(Harness2CycleError, match="CONTEXT_TASK_DOMAIN_MISMATCH"):
        _invoke_context(port, args)
    assert not port.calls
