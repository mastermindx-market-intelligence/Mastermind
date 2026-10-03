"""Coordination semantic handoff: actual owner machinery, explicitly fake models."""
from __future__ import annotations

import asyncio
import copy
import dataclasses
import importlib
import json
from pathlib import Path

import pytest

from tests.test_chairman_coordination_host import host, complete, ARTIFACT
from tests.test_chairman_coordination_acquisition import (
    reader, compiler_repo, composed_source, bind_sources, source_binding_inputs,
)
from tests.test_executive_os_phase1fc import _complete_ohf_role, _review_body
from control_plane.executive_coo_cycle import CooCycle
from control_plane.executive_runtime import JobStatus, AttemptStatus, StateConflict
from control_plane.executive_supervisor import ExecutiveSupervisor, SupervisorError


def module():
    spec = importlib.util.find_spec("control_plane.chairman_coordination_review")
    assert spec is not None, "verified coordination semantic handoff is missing"
    return importlib.import_module("control_plane.chairman_coordination_review")


def test_semantic_handoff_is_available_without_installing_or_starting_a_provider():
    assert callable(module().read_coordination_review_request)
    assert callable(module().read_coordination_review_return)


def prepare_review(host, *, dispatch=True):
    supervisor, work_done = complete(host)
    runtime = host["runtime"]
    runtime.workers.register_worker("worker-b", provider="codex", account_label="independent-review-fixture",
        worker_type="mock", capabilities=["read", "research"], quota_classes={"default": {
            "provider": "codex", "capabilities": ["read", "research"], "cost_class": "small",
            "model": "gpt-5.6-sol", "effort": "xhigh"}})
    review = runtime.jobs.create_cycle_review(host["root"].job_id, work_done.job.job_id,
        command_id=f"coo-cycle:{host['root'].job_id}:create-review:{work_done.job.job_id}:1")
    dispatched = None
    if dispatch:
        dispatched = runtime.attempts.dispatch_cycle_job(review.job_id,
            command_id=f"coo-cycle:{host['root'].job_id}:dispatch:{review.job_id}:attempt:1",
            worker_id="worker-b", quota_class="default")
    review = runtime.jobs.get_job(review.job_id)
    sources = host["config"]["coordination_sources"](work_done.job, work_done.attempt)
    return {**host, "work_done": work_done, "review": review, "review_dispatch": dispatched,
            "review_attempt": dispatched.attempt if dispatched else None, "sources": sources,
            "decision": supervisor._revalidate_authority(review, dispatched.attempt) if dispatched else None}


@pytest.fixture
def reviewing(host):
    return prepare_review(host)


def request(h, **overrides):
    args = dict(sources=h["sources"], runtime=h["reader"], root_job_id=h["root"].job_id,
        review_job_id=h["review"].job_id, reviewed_job_id=h["work_done"].job.job_id,
        expected_attempt_id=h["review_attempt"].attempt_id, authority_decision=h["decision"],
        artifact_reader=reader(h))
    args.update(overrides)
    return module().read_coordination_review_request(**args)


def finish_review(h, *, verdict="approve", cite=True):
    work, review = h["work_done"].job, h["review"]
    from control_plane.executive_orchestration_result import canonical_digest
    with h["reader"].observe_bounded_read() as observation:
        selected = observation.read_role_result_bounded(work.root_job_id, work.job_id,
            expected_attempt_id=work.current_attempt_id,
            expected_result_envelope_digest=work.result["result_envelope_digest"])
    completed = selected.completion
    body = _review_body(root_id=work.root_job_id, plan_attempt_id=work.plan_attempt_id,
        plan_digest=work.plan_digest, plan_step_id=work.plan_step_id,
        target_job_id=work.job_id, target_attempt_id=work.current_attempt_id,
        target_result_digest=canonical_digest(completed.result_envelope["role_result"]), repair_round=work.repair_round,
        verdict=verdict)
    if cite:
        import hashlib
        body["evidence_digests"] = [hashlib.sha256(h["adapter"].candidate_bytes).hexdigest()]
    _complete_ohf_role(h["runtime"], h["review_dispatch"], body, identity_seed=23501)
    return h["runtime"].jobs.get_job(review.job_id)


def returned(h, done, **overrides):
    args = dict(sources=h["sources"], runtime=h["reader"], root_job_id=h["root"].job_id,
        review_job_id=done.job_id, reviewed_job_id=h["work_done"].job.job_id,
        expected_attempt_id=done.current_attempt_id,
        expected_result_envelope_digest=done.result["result_envelope_digest"],
        artifact_reader=reader(h))
    args.update(overrides)
    return module().read_coordination_review_return(**args)


def test_review_input_preserves_complete_proposal_and_original_review_role(reviewing):
    h = reviewing
    out = request(h)
    assert out["task"]["candidate"] == h["c"]
    assert out["task"]["candidate"]["rationale"]
    assert out["task"]["candidate"]["next_step"]
    assert out["task"]["work_evidence"]["artifact_path"] == ARTIFACT
    assert out["task"]["work_evidence"]["summary_used"] is False
    assert out["task"]["structural_review"]["requires_semantic_review"] is True
    assert out["result_schema"]["properties"]["role"]["const"] == "review"
    assert out["effective_grant_digest"] == h["review_attempt"].effective_grant_digest
    assert "Do not execute" in out["prompt"]
    assert out["execution_authority_granted"] is False
    assert out["parent_consumption_proven"] is False
    assert h["namespace"].active is False


def test_request_reads_exact_sealed_artifact_once_and_does_not_mutate_runtime(reviewing):
    h = reviewing; calls = []; concrete = reader(h)
    before = (h["runtime"].jobs.get_job(h["review"].job_id).to_dict(),
              h["runtime"].jobs.get_job(h["root"].job_id).to_dict())
    def acquire(*args, **kwargs):
        assert h["namespace"].active is False
        calls.append((args, kwargs))
        return concrete(*args, **kwargs)
    request(h, artifact_reader=acquire)
    assert len(calls) == 1 and calls[0][0][0].job_id == h["work_done"].job.job_id
    assert before == (h["runtime"].jobs.get_job(h["review"].job_id).to_dict(),
                      h["runtime"].jobs.get_job(h["root"].job_id).to_dict())
    assert h["adapter"].start_count == 1


@pytest.mark.parametrize("field,value", [
    ("root_job_id", "JOB-999999"), ("review_job_id", "JOB-999999"),
    ("reviewed_job_id", "JOB-999999"), ("expected_attempt_id", "ATT-foreign"),
    ("root_job_id", " JOB-1"), ("review_job_id", None), ("reviewed_job_id", True),
])
def test_exact_review_selection_cannot_be_relabelled(reviewing, field, value):
    with pytest.raises(SupervisorError):
        request(reviewing, **{field: value})


def test_write_runtime_is_not_a_trusted_bounded_read_namespace(reviewing):
    with pytest.raises(SupervisorError):
        request(reviewing, runtime=reviewing["runtime"])


def test_another_jobs_authority_cannot_authorize_this_review(reviewing):
    h = reviewing
    altered = dataclasses.replace(h["decision"], requested=("READ", "WRITE_BRANCH"))
    with pytest.raises(SupervisorError):
        request(h, authority_decision=altered)


def test_source_revalidation_failure_does_not_leak_detail_or_read_artifacts(reviewing):
    h = reviewing; calls = []
    def failed():
        raise ValueError("private policy details must not leak")
    with pytest.raises(SupervisorError, match="coordination review request refused") as exc:
        request(h, sources=dataclasses.replace(h["sources"], revalidate=failed),
                artifact_reader=lambda *a, **k: calls.append(a))
    assert not calls and "private policy" not in str(exc.value)


def test_artifact_substitution_cannot_enter_the_parent_prompt(reviewing):
    with pytest.raises(SupervisorError):
        request(reviewing, artifact_reader=lambda *a, **k: b'{"next_step":"deploy now"}')


def test_work_summary_is_never_used_as_the_candidate(reviewing):
    h = reviewing
    artifact = Path(h["work_done"].job.worktree) / ARTIFACT
    artifact.unlink()
    with pytest.raises(SupervisorError):
        request(h)


def test_review_result_returns_full_proposal_without_claiming_parent_acceptance(reviewing):
    h = reviewing; request(h); done = finish_review(h)
    out = returned(h, done)
    assert out["candidate"] == h["c"]
    assert out["semantic_review"]["review"]["reviewed_job_id"] == h["work_done"].job.job_id
    assert out["semantic_review"]["acceptance"] == "NOT_PROJECTED"
    assert out["reviewer_cites_candidate"] is True
    assert out["review_supports_proposal"] is True
    for key in ("execution_authority_granted", "acceptance_granted", "parent_consumption_proven"):
        assert out[key] is False
    assert out["requires_parent_judgment"] and out["next_effect_requires_owner_revalidation"]


@pytest.mark.parametrize("verdict,cite", [("approve", False), ("reject", True)])
def test_missing_candidate_citation_or_rejection_is_not_a_clean_parent_return(reviewing, verdict, cite):
    done = finish_review(reviewing, verdict=verdict, cite=cite)
    out = returned(reviewing, done)
    assert out["review_supports_proposal"] is False
    assert out["parent_consumption_proven"] is False


def test_completed_review_is_not_an_active_review_request(reviewing):
    finish_review(reviewing)
    with pytest.raises(SupervisorError):
        request(reviewing)


def test_return_requires_the_exact_completed_review_not_the_work_result(reviewing):
    done = finish_review(reviewing)
    with pytest.raises(SupervisorError):
        returned(reviewing, done, expected_result_envelope_digest=reviewing["work_done"].job.result["result_envelope_digest"])


def test_existing_coo_parent_consumes_exact_independent_review_into_its_own_handoff(reviewing):
    h = reviewing; request(h); done = finish_review(h); returned(h, done)
    outcome = CooCycle(h["runtime"]).run_once(h["root"].job_id)
    assert outcome.action == "HANDOFF_CREATED"
    handoff = h["runtime"].jobs.get_cycle_handoff(h["root"].job_id)
    assert handoff["revisions"][0]["current_job_id"] == h["work_done"].job.job_id
    assert h["runtime"].jobs.get_job(h["root"].job_id).status is not JobStatus.COMPLETED


def test_new_supervisor_does_not_replace_dispatch_recovery_or_completion_owners():
    cls = module().CoordinationReviewSupervisor
    for name in ("start_cycle_job", "run_cycle_once", "finish_job", "_launch_spec"):
        assert getattr(cls, name) is getattr(ExecutiveSupervisor, name)


def review_supervisor(h, **overrides):
    config = dict(h["config"])
    del config["coordination_job_id"]
    config.update(coordination_review_job_id=h["review"].job_id,
                  coordination_work_job_id=h["work_done"].job.job_id,
                  coordination_sources=lambda job, attempt: h["sources"],
                  coordination_artifact_reader=reader(h))
    config.update(overrides)
    return module().CoordinationReviewSupervisor(h["runtime"], h["adapter"], **config)


def test_role_artifact_and_envelope_digest_domains_remain_distinct(reviewing):
    out = request(reviewing)
    evidence = out["task"]["work_evidence"]
    assert out["task"]["review_target"]["reviewed_result_digest"] == evidence["role_result_digest"]
    assert len({evidence["role_result_digest"], evidence["artifact_digest"],
                evidence["result_envelope_digest"]}) == 3


def test_selected_review_prompt_contains_the_actual_full_proposal(reviewing):
    h = reviewing; sup = review_supervisor(h)
    prompt = sup._prompt(h["review"], h["review_attempt"], h["review_attempt"].effective_grant)
    assert prompt.startswith("You are the one-shot Mastermind Executive worker")
    data = json.loads(prompt.split("\n\nEvidence data:\n", 1)[1])
    assert data["candidate"] == h["c"]
    assert data["review_target"]["reviewed_job_id"] == h["work_done"].job.job_id


@pytest.mark.parametrize("field,value", [("objective", "Unrelated replacement goal"),
                                         ("plan_step_id", "foreign-step")])
def test_stale_outer_job_cannot_pollute_the_original_supervisor_prompt(reviewing, field, value):
    h = reviewing; sup = review_supervisor(h)
    wrong = dataclasses.replace(h["review"], **{field: value})
    with pytest.raises(SupervisorError):
        sup._prompt(wrong, h["review_attempt"], h["review_attempt"].effective_grant)


def test_other_job_prompt_remains_byte_identical_without_acquiring_coordination_sources(reviewing):
    h = reviewing
    def forbidden(*args):
        raise AssertionError("unrelated Job acquired coordination sources")
    sup = review_supervisor(h, coordination_sources=forbidden)
    work, attempt = h["work_done"].job, h["work_done"].attempt
    assert sup._prompt(work, attempt, attempt.effective_grant) == ExecutiveSupervisor._prompt(
        sup, work, attempt, attempt.effective_grant)


def test_new_prompt_bound_refuses_instead_of_truncating_current_evidence(reviewing, monkeypatch):
    monkeypatch.setattr(module(), "_MAX_PACKET_BYTES", 1024)
    with pytest.raises(SupervisorError):
        request(reviewing)


def test_source_or_assignment_change_during_artifact_read_never_produces_a_prompt(reviewing):
    h = reviewing; concrete = reader(h); completions = []
    def changed(*args, **kwargs):
        blob = concrete(*args, **kwargs)
        completions.append(finish_review(h))
        return blob
    with pytest.raises(SupervisorError):
        request(h, artifact_reader=changed)
    assert len(completions) == 1 and completions[0].status is JobStatus.COMPLETED


def test_completed_review_does_not_override_a_now_held_proposal(reviewing):
    h = reviewing; done = finish_review(h)
    changed_context = copy.deepcopy(h["sources"].context)
    changed_context["coverage"] = "PARTIAL"
    changed_context["omissions"] = ["Current active-build join is unavailable."]
    out = returned(h, done, sources=dataclasses.replace(h["sources"], context=changed_context))
    assert out["review_supports_proposal"] is False
    assert out["structural_review"]["eligible_for_owner_revalidation"] is False
    assert out["semantic_review"]["review"]["verdict"] == "approve"
    assert not out["acceptance_granted"]


def native_review_supervisor(h, **overrides):
    """Actual Supervisor lifecycle with a fake adapter reading its delivered prompt."""
    import hashlib
    from tests.test_executive_supervisor import Hf1bResultAdapter, FakeInspector, FakeProcessController
    from control_plane.executive_orchestration_result import canonical_bytes

    class ReviewAdapter(Hf1bResultAdapter):
        async def collect_result(self, ref):
            task = json.loads(self.spec.prompt.split("\n\nEvidence data:\n", 1)[1])
            self.received_task = task
            original = await super().collect_result(ref)
            output = dict(original.result.structured_output)
            output["role"] = "review"
            output["role_result"] = {
                "schema_version": "mastermind.review_result/v1", **task["review_target"],
                "verdict": "approve", "findings": [],
                "evidence_digests": [task["work_evidence"]["artifact_digest"]],
            }
            output["summary"] = "Explicit fixture review of the delivered full proposal; no real model judgment."
            raw = canonical_bytes(output)
            Path(ref.result_path).write_bytes(raw)
            self.inspector.live = False
            return dataclasses.replace(original, result=dataclasses.replace(original.result, structured_output=output),
                                       result_sha256=hashlib.sha256(raw).hexdigest())

    adapter = ReviewAdapter(FakeInspector(), h["runtime"], h["review"])
    home = h["adapter"].provider_home.parent / "review-provider-home"
    home.mkdir(mode=0o700)
    adapter.provider_home = home
    config = dict(h["config"])
    del config["coordination_job_id"]
    config.update(coordination_review_job_id=h["review"].job_id,
        coordination_work_job_id=h["work_done"].job.job_id,
        coordination_sources=lambda job, attempt: h["sources"],
        coordination_artifact_reader=reader(h), inspector=adapter.inspector,
        process_controller=FakeProcessController(adapter.inspector),
        instance_id="coordination-review-host-fixture")
    config.pop("exact_target_provider")
    config.update(overrides)
    return module().CoordinationReviewSupervisor(h["runtime"], adapter, **config), adapter


def exercise_native_review(h):
    # Fixture admission config only. The product never selects or drains workers.
    h["runtime"].workers.set_worker_status(h["work_done"].attempt.worker_id, "DRAINING")
    sup, adapter = native_review_supervisor(h)
    command_id = f"coo-cycle:{h['root'].job_id}:dispatch:{h['review'].job_id}:attempt:1"
    result = asyncio.run(sup.run_cycle_once(h["review"].job_id, command_id=command_id))
    assert result.job.status is JobStatus.COMPLETED
    assert result.attempt.status is AttemptStatus.COMPLETED
    assert result.attempt.worker_id != h["work_done"].attempt.worker_id, {"work_worker": h["work_done"].attempt.worker_id, "review_worker": result.attempt.worker_id}
    assert adapter.start_count == 1
    assert adapter.received_task["candidate"] == h["c"]
    out = returned(h, result.job)
    assert out["review_supports_proposal"] is True
    replay = asyncio.run(sup.run_cycle_once(h["review"].job_id, command_id=command_id))
    assert replay.outcome == "TERMINAL" and adapter.start_count == 1
    # This adapter uses the real test runner UID, so it must NOT qualify as
    # physically independent from the author merely by changing worker labels.
    assert out["review_independence"] == "NOT_PROJECTED"
    assert CooCycle(h["runtime"]).run_once(h["root"].job_id).action == "REVIEW_CREATED"
    with pytest.raises(StateConflict, match="one immutable handoff"):
        h["runtime"].jobs.get_cycle_handoff(h["root"].job_id)
    return out, adapter.received_task, result


def exercise_independent_review(h):
    """Existing OHF independent-principal fixture; no physical/model proof claim."""
    packet = request(h)
    task = packet["task"]
    body = {"schema_version": "mastermind.review_result/v1", **task["review_target"],
            "verdict": "approve", "findings": [],
            "evidence_digests": [task["work_evidence"]["artifact_digest"]]}
    _complete_ohf_role(h["runtime"], h["review_dispatch"], body, identity_seed=23501)
    done = h["runtime"].jobs.get_job(h["review"].job_id)
    attempt = h["runtime"].attempts.get_attempt(done.current_attempt_id)
    out = returned(h, done)
    assert out["review_supports_proposal"]
    assert CooCycle(h["runtime"]).run_once(h["root"].job_id).action == "HANDOFF_CREATED"
    handoff = h["runtime"].jobs.get_cycle_handoff(h["root"].job_id)
    revision = handoff["revisions"][0]
    assert revision["current_job_id"] == h["work_done"].job.job_id
    assert revision["current_attempt_id"] == h["work_done"].attempt.attempt_id
    assert revision["current_result_digest"] == out["structural_review"]["runtime_result_evidence"]["role_result_digest"]
    assert revision["qualifying_review_job_id"] == done.job_id
    assert revision["qualifying_review_attempt_id"] == attempt.attempt_id
    assert revision["qualifying_review_result_digest"] == out["semantic_review"]["role_result_digest"]
    assert revision["qualifying_review_effective_grant_digest"] == attempt.effective_grant_digest
    assert revision["qualifying_review_principal_snapshot_digest"] == attempt.execution_principal_snapshot_digest
    assert h["runtime"].jobs.get_job(h["root"].job_id).status is not JobStatus.COMPLETED
    assert out["parent_consumption_proven"] is False
    return out, task, attempt, handoff


def test_native_review_completion_does_not_bypass_physical_principal_independence(host):
    h = prepare_review(host, dispatch=False)
    exercise_native_review(h)


def prepare_compiled_review(host, composed_source):
    from control_plane.chairman_cognition_sources import COMPILED_CONTEXT_SOURCE_REF
    from control_plane.chairman_coordination import render_coordination_brief
    source, observed = composed_source
    target = "RUNTIME_BINDING:fixture-current-target"
    source["additional_source_receipts"].append(dict(source_ref=target, owner="RUNTIME_BINDING",
        revision="generation-fixture", state="CURRENT", load_bearing=True, observed_at=source["as_of"]))
    source["options"][0]["source_refs"] = [source["chairman_directive"]["source_ref"],
        "GITHUB:Mastermind:protected-master", "STRATEGIC_STATE:config/strategic_state.yml",
        "AGENT_OS:canonical-revision", "AGENT_OS:ceo_brief", "GITHUB:A1", target]
    fields = source_binding_inputs(source, observed)
    fields.update(target_ref="TARGET-A", target_source_ref=target)
    acquired = bind_sources(source, observed, fields)
    assert acquired.context["project_ref"] == host["x"]["project_ref"]
    brief = render_coordination_brief(acquired.document, context=acquired.context,
        context_bundle=acquired.context_bundle, bundle_source_ref=acquired.bundle_source_ref)
    candidate = json.loads(brief["messages"][1]["content"])["candidate_template"]
    candidate.update(option_id=source["options"][0]["option_id"], decision="CONTINUE",
        consumed_return_refs=[], evidence_refs=["GITHUB:A1"],
        rationale="The accepted design and current return establish the next bounded proof obligation.",
        next_step="Retain the principal and existing operation. Qualify the exact returned artifact through its parent; do not repeat the accepted design or activate a held route.")
    host["adapter"].proposal = candidate
    host["c"] = candidate
    host["config"]["coordination_sources"] = lambda job, attempt: acquired
    h = prepare_review(host)
    return h, acquired, brief, observed, candidate


def test_concrete_compiler_and_sealed_artifact_reach_review_and_canonical_parent(host, composed_source, record_testsuite_property):
    from control_plane.chairman_cognition_sources import COMPILED_CONTEXT_SOURCE_REF
    h, acquired, brief, observed, candidate = prepare_compiled_review(host, composed_source)
    out, task, review_attempt, handoff = exercise_independent_review(h)
    assert task["coordination_brief"] == brief
    assert out["candidate"]["next_step"] == candidate["next_step"]
    assert acquired.context["source_revisions"][COMPILED_CONTEXT_SOURCE_REF] == observed.source_attestation["payload_digest"]
    assert h["work_done"].collection_receipt_path and h["work_done"].assignment_seal_receipt_path
    record_testsuite_property("COORDINATION_PARENT_FLOW", json.dumps({
        "qualification": "TEMPORARY_RUNTIME_EXPLICIT_FAKE_COMPILER_AND_MODELS",
        "project_ref": acquired.context["project_ref"],
        "compiled_context_digest": observed.source_attestation["payload_digest"],
        "work_evidence": task["work_evidence"],
        "review_selection": out["semantic_review"]["selection"],
        "review_role_result_digest": out["semantic_review"]["role_result_digest"],
        "parent_handoff_digest": handoff["handoff_digest"],
        "parent_revision": handoff["revisions"][0],
        "work_worker_id": h["work_done"].attempt.worker_id,
        "review_worker_id": review_attempt.worker_id,
        "parent_project_acceptance_proven": False, "web_pro_round_trip_proven": False,
    }, sort_keys=True))


def test_rejected_review_does_not_create_an_approved_parent_handoff(reviewing):
    h = reviewing
    done = finish_review(h, verdict="reject")
    out = returned(h, done)
    assert not out["review_supports_proposal"]
    outcome = CooCycle(h["runtime"]).run_once(h["root"].job_id)
    assert outcome.action != "HANDOFF_CREATED"
    with pytest.raises(StateConflict, match="one immutable handoff"):
        h["runtime"].jobs.get_cycle_handoff(h["root"].job_id)


def test_return_does_not_promote_a_verdict_into_independence_or_parent_eligibility(reviewing):
    done = finish_review(reviewing)
    out = returned(reviewing, done)
    assert out.get("review_independence") == "NOT_PROJECTED"
    assert "eligible_for_parent_judgment" not in out
    assert out["review_supports_proposal"] is True
    assert out["requires_parent_judgment"] and not out["parent_consumption_proven"]


def test_explicit_unusable_work_target_is_not_dropped_for_an_untargeted_review_retry(host):
    h = prepare_review(host, dispatch=False)
    target = h["config"]["exact_target_provider"](h["work_done"].job.job_id)
    sup, adapter = native_review_supervisor(h, exact_target_provider=lambda job_id: target)
    command_id = f"coo-cycle:{h['root'].job_id}:dispatch:{h['review'].job_id}:attempt:1"
    with pytest.raises(StateConflict, match="exact worker target"):
        asyncio.run(sup.run_cycle_once(h["review"].job_id, command_id=command_id))
    current = h["runtime"].jobs.get_job(h["review"].job_id)
    assert current.status is JobStatus.QUEUED and current.current_attempt_id is None
    assert adapter.start_count == 0


def test_original_parent_refuses_same_author_review_even_after_a_completed_model_result(host):
    h = prepare_review(host, dispatch=False)
    # Deliberately bad fixture placement, not a production policy or scheduler edit.
    h["runtime"].workers.set_worker_status("worker-b", "DRAINING")
    sup, adapter = native_review_supervisor(h)
    command_id = f"coo-cycle:{h['root'].job_id}:dispatch:{h['review'].job_id}:attempt:1"
    done = asyncio.run(sup.run_cycle_once(h["review"].job_id, command_id=command_id))
    assert done.job.status is JobStatus.COMPLETED
    assert done.attempt.worker_id == h["work_done"].attempt.worker_id
    out = returned(h, done.job)
    assert out["review_independence"] == "NOT_PROJECTED"
    assert not out["parent_consumption_proven"] and not out["acceptance_granted"]
    assert CooCycle(h["runtime"]).run_once(h["root"].job_id).action == "REVIEW_CREATED"
    with pytest.raises(StateConflict, match="one immutable handoff"):
        h["runtime"].jobs.get_cycle_handoff(h["root"].job_id)
