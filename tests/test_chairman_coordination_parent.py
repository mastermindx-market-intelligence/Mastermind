"""Parent input/return integration. All model/principal attestations are fixtures."""
from __future__ import annotations

import asyncio
import dataclasses
import hashlib
import importlib
import json
from pathlib import Path

import pytest

from tests.test_chairman_coordination_host import host
from tests.test_chairman_coordination_acquisition import reader, compiler_repo, composed_source
from tests.test_chairman_coordination_review import prepare_review, prepare_compiled_review, exercise_independent_review
from tests.test_executive_supervisor import Hf1bResultAdapter, FakeInspector, FakeProcessController
from control_plane.executive_coo_cycle import CooCycle
from control_plane.executive_runtime import JobStatus, AttemptStatus, StateConflict
from control_plane.executive_supervisor import ExecutiveSupervisor, SupervisorError
from control_plane.executive_orchestration_result import canonical_bytes


def module():
    spec = importlib.util.find_spec("control_plane.chairman_coordination_parent")
    assert spec is not None, "complete proposal delivery into the original parent is missing"
    return importlib.import_module("control_plane.chairman_coordination_parent")


def test_parent_composition_exists_without_a_new_runtime_or_acceptance_owner():
    assert issubclass(module().CoordinationParentSupervisor, ExecutiveSupervisor)


@pytest.fixture
def ready(host):
    h = prepare_review(host)
    returned, task, attempt, handoff = exercise_independent_review(h)
    return {**h, "review_return": returned, "handoff": handoff}


@pytest.fixture
def compiled_ready(host, composed_source):
    h, acquired, brief, observed, candidate = prepare_compiled_review(host, composed_source)
    returned, task, attempt, handoff = exercise_independent_review(h)
    return {**h, "review_return": returned, "handoff": handoff}


class ParentAdapter(Hf1bResultAdapter):
    """No real provider: output is derived explicitly from delivered parent input."""
    async def collect_result(self, ref):
        task = json.loads(self.spec.prompt.split("\n\nParent coordination evidence:\n", 1)[1])
        self.received_task = task
        original = await super().collect_result(ref)
        output = dict(original.result.structured_output)
        handoff = task["aggregation_handoff"]
        proposal = task["coordination_return"]["candidate"]
        work = task["coordination_return"]["structural_review"]["runtime_result_evidence"]
        keys = {"ordinal", "plan_step_id", "current_job_id", "current_attempt_id",
                "current_result_digest", "repair_round", "review_required",
                "qualifying_review_job_id", "qualifying_review_attempt_id",
                "qualifying_review_result_digest"}
        output["role"] = "aggregation"
        output["role_result"] = {
            "schema_version": "mastermind.aggregation_result/v1",
            "root_job_id": handoff["root_job_id"], "handoff_digest": handoff["handoff_digest"],
            "policy_sha": handoff["policy_sha"], "plan_attempt_id": handoff["plan_attempt_id"],
            "plan_digest": handoff["plan_digest"],
            "revisions": [{key: item[key] for key in keys} for item in handoff["revisions"]],
            "aggregate_summary": "Explicit model fixture consumed " + proposal["decision"] + ": "
                + proposal["rationale"] + " Next proposal: " + proposal["next_step"],
            "evidence_digests": [work["artifact_digest"]],
        }
        output["summary"] = "Parent input/return fixture, not a live intelligence claim."
        output["next_actions"] = [proposal["next_step"]]
        raw = canonical_bytes(output)
        Path(ref.result_path).write_bytes(raw)
        self.inspector.live = False
        return dataclasses.replace(original, result=dataclasses.replace(original.result, structured_output=output),
                                   result_sha256=hashlib.sha256(raw).hexdigest())


def parent_supervisor(h, **overrides):
    adapter = ParentAdapter(FakeInspector(), h["runtime"], h["root"])
    home = h["adapter"].provider_home.parent / "parent-provider-home"
    home.mkdir(mode=0o700)
    adapter.provider_home = home
    config = dict(h["config"])
    del config["coordination_job_id"]
    config.pop("exact_target_provider")  # This initial fixture uses original aggregation admission.
    config.update(coordination_root_job_id=h["root"].job_id,
        coordination_work_job_id=h["work_done"].job.job_id,
        coordination_sources=lambda job, attempt: h["sources"],
        coordination_artifact_reader=reader(h), inspector=adapter.inspector,
        process_controller=FakeProcessController(adapter.inspector),
        instance_id="coordination-parent-host-fixture")
    config.update(overrides)
    return module().CoordinationParentSupervisor(h["runtime"], adapter, **config), adapter


def dispatch_command(h):
    return f"coo-cycle:{h['root'].job_id}:dispatch:{h['root'].job_id}:attempt:1"


def active_parent(h):
    dispatched = h["runtime"].attempts.dispatch_cycle_job(h["root"].job_id,
        command_id=dispatch_command(h), worker_id="worker-b", quota_class="default")
    return h["runtime"].jobs.get_job(h["root"].job_id), dispatched.attempt


@pytest.mark.parametrize("prepared", ["ready", "compiled_ready"])
def test_full_proposal_is_delivered_consumed_and_sealed_in_original_parent_result(prepared, request, record_testsuite_property):
    h = request.getfixturevalue(prepared); sup, adapter = parent_supervisor(h)
    done = asyncio.run(sup.run_cycle_once(h["root"].job_id, command_id=dispatch_command(h)))
    assert done.job.status is JobStatus.COMPLETED and done.attempt.status is AttemptStatus.COMPLETED
    assert adapter.start_count == 1
    assert adapter.received_task["coordination_return"]["candidate"] == h["c"]
    assert adapter.received_task["aggregation_handoff"] == h["handoff"]
    completed = h["runtime"].validated_role_completion(h["root"].job_id,
        expected_attempt_id=done.attempt.attempt_id)
    body = completed.result_envelope["role_result"]
    assert h["c"]["next_step"] in body["aggregate_summary"]
    assert h["c"]["rationale"] in body["aggregate_summary"]
    assert body["handoff_digest"] == h["handoff"]["handoff_digest"]
    assert completed.result_envelope["next_actions"] == [h["c"]["next_step"]]
    assert body["evidence_digests"] == [hashlib.sha256(h["adapter"].candidate_bytes).hexdigest()]
    before_jobs = [job.to_dict() for job in h["runtime"].jobs.list_jobs()]
    replay = asyncio.run(sup.run_cycle_once(h["root"].job_id, command_id=dispatch_command(h)))
    assert replay.outcome == "TERMINAL" and adapter.start_count == 1
    assert CooCycle(h["runtime"]).run_once(h["root"].job_id).action == "NO_ACTION"
    assert before_jobs == [job.to_dict() for job in h["runtime"].jobs.list_jobs()]
    record_testsuite_property("COORDINATION_PARENT_INPUT_RETURN_" + prepared.upper(), json.dumps({
        "context_acquisition": "EXPLICIT_FAKE_CLI_THROUGH_CONCRETE_READER" if prepared == "compiled_ready" else "EXPLICIT_STATIC_FIXTURE",
        "qualification": "TEMPORARY_RUNTIME_EXPLICIT_FAKE_MODELS_AND_REVIEW_PRINCIPAL",
        "parent_job_id": done.job.job_id, "parent_attempt_id": done.attempt.attempt_id,
        "parent_result_envelope_digest": done.job.result["result_envelope_digest"],
        "parent_handoff_digest": body["handoff_digest"], "parent_revisions": body["revisions"],
        "candidate_artifact_digest": body["evidence_digests"][0],
        "full_proposal_present_in_parent_input": True, "proposal_used_in_parent_result": True,
        "next_instruction_executed": False, "real_model_usefulness_proven": False,
        "web_pro_input_turn_return_proven": False, "project_acceptance_proven": False,
    }, sort_keys=True))


def test_parent_composition_preserves_original_role_and_current_evidence(ready):
    h = ready; sup, adapter = parent_supervisor(h); job, attempt = active_parent(h)
    prompt = sup._prompt(job, attempt, attempt.effective_grant)
    assert prompt.startswith(ExecutiveSupervisor._prompt(sup, job, attempt, attempt.effective_grant))
    task = json.loads(prompt.split("\n\nParent coordination evidence:\n", 1)[1])
    assert task["coordination_return"]["candidate"] == h["c"]
    assert task["coordination_brief"]["project_ref"] == h["x"]["project_ref"]
    assert task["coordination_return"]["acceptance_granted"] is False
    assert adapter.start_count == 0 and h["namespace"].active is False


@pytest.mark.parametrize("field,value", [("objective", "Different assignment"), ("current_attempt_id", "ATT-other")])
def test_parent_source_cannot_be_added_to_a_stale_outer_assignment(ready, field, value):
    h = ready; sup, _ = parent_supervisor(h); job, attempt = active_parent(h)
    with pytest.raises(SupervisorError):
        sup._prompt(dataclasses.replace(job, **{field: value}), attempt, attempt.effective_grant)


def test_missing_or_changed_artifact_refuses_before_parent_model_launch(ready):
    h = ready
    from tests.test_chairman_coordination_host import ARTIFACT
    (Path(h["work_done"].job.worktree) / ARTIFACT).write_bytes(b'{"next_step":"invented"}')
    sup, adapter = parent_supervisor(h)
    with pytest.raises(SupervisorError):
        asyncio.run(sup.run_cycle_once(h["root"].job_id, command_id=dispatch_command(h)))
    assert adapter.start_count == 0


def test_wrong_work_selection_is_not_guessed_from_the_first_handoff_revision(ready):
    h = ready; sup, _ = parent_supervisor(h, coordination_work_job_id="JOB-999999")
    job, attempt = active_parent(h)
    with pytest.raises(SupervisorError):
        sup._prompt(job, attempt, attempt.effective_grant)


def test_parent_reads_require_the_existing_bound_namespace(ready):
    h = ready; sup, _ = parent_supervisor(h, coordination_runtime=h["runtime"])
    job, attempt = active_parent(h)
    with pytest.raises(SupervisorError):
        sup._prompt(job, attempt, attempt.effective_grant)


def test_parent_prompt_refuses_source_revalidation_failure(ready):
    h = ready
    def failed(): raise ValueError("private source detail")
    sources = dataclasses.replace(h["sources"], revalidate=failed)
    sup, _ = parent_supervisor(h, coordination_sources=lambda job, attempt: sources)
    job, attempt = active_parent(h)
    with pytest.raises(SupervisorError, match="coordination parent task composition refused") as exc:
        sup._prompt(job, attempt, attempt.effective_grant)
    assert "private source detail" not in str(exc.value)


def test_unrelated_prompt_is_unchanged_and_does_not_read_coordination_sources(ready):
    h = ready
    def failed(*args): raise AssertionError("unrelated Job opened coordination sources")
    sup, _ = parent_supervisor(h, coordination_sources=failed)
    job, attempt = h["work_done"].job, h["work_done"].attempt
    assert sup._prompt(job, attempt, attempt.effective_grant) == ExecutiveSupervisor._prompt(sup, job, attempt, attempt.effective_grant)


def test_parent_does_not_override_launch_retry_or_acceptance_owners():
    cls = module().CoordinationParentSupervisor
    for name in ("start_cycle_job", "run_cycle_once", "finish_job", "_launch_spec"):
        assert getattr(cls, name) is getattr(ExecutiveSupervisor, name)


def test_parent_prompt_limit_refuses_without_truncating_evidence(ready, monkeypatch):
    h = ready; sup, _ = parent_supervisor(h); job, attempt = active_parent(h)
    monkeypatch.setattr(module(), "_MAX_PROMPT_BYTES", 1024)
    with pytest.raises(SupervisorError):
        sup._prompt(job, attempt, attempt.effective_grant)


def test_other_project_context_cannot_be_used_by_the_selected_parent(ready):
    h = ready
    sources = dataclasses.replace(h["sources"], context={**h["sources"].context, "project_ref": "WS:OTHER-PROJECT"})
    sup, _ = parent_supervisor(h, coordination_sources=lambda job, attempt: sources)
    job, attempt = active_parent(h)
    with pytest.raises(SupervisorError):
        sup._prompt(job, attempt, attempt.effective_grant)


def test_current_partial_context_remains_visible_for_parent_hold_judgment(ready):
    h = ready
    sources = dataclasses.replace(h["sources"], context={**h["sources"].context,
        "coverage": "PARTIAL", "omissions": ["Current active-build evidence is missing."]})
    sup, _ = parent_supervisor(h, coordination_sources=lambda job, attempt: sources)
    job, attempt = active_parent(h)
    prompt = sup._prompt(job, attempt, attempt.effective_grant)
    task = json.loads(prompt.split("\n\nParent coordination evidence:\n", 1)[1])
    assert task["coordination_return"]["review_supports_proposal"] is False
    assert task["coordination_return"]["structural_review"]["eligible_for_owner_revalidation"] is False
    assert "Current active-build evidence is missing." in prompt
    assert not task["coordination_return"]["acceptance_granted"]


def test_no_parent_model_can_start_before_the_original_independent_review_handoff(host):
    h = prepare_review(host)
    sup, adapter = parent_supervisor(h)
    with pytest.raises(StateConflict):
        asyncio.run(sup.run_cycle_once(h["root"].job_id, command_id=dispatch_command(h)))
    assert adapter.start_count == 0
    assert h["runtime"].jobs.get_job(h["root"].job_id).current_attempt_id is None


def test_parent_never_drops_an_explicit_unusable_target_to_retry_untargeted(ready):
    h = ready; target = h["config"]["exact_target_provider"](h["work_done"].job.job_id)
    sup, adapter = parent_supervisor(h, exact_target_provider=lambda job_id: target)
    with pytest.raises(StateConflict):
        asyncio.run(sup.run_cycle_once(h["root"].job_id, command_id=dispatch_command(h)))
    assert adapter.start_count == 0
    assert h["runtime"].jobs.get_job(h["root"].job_id).current_attempt_id is None
