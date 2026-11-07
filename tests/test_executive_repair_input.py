"""Canonical repair-input refusals; inert OHF completion, no provider effects."""
import copy
import dataclasses

import pytest

from control_plane.executive_orchestration_result import canonical_digest
from control_plane.executive_runtime import Runtime
from control_plane.executive_supervisor import SupervisorError
from test_executive_os_phase1fc import (
    _complete_ohf_role, _cycle_through_completed_work, _review_body,
)
from test_executive_supervisor import FakeAdapter, FakeInspector, _supervisor


def _claimed_repair(tmp_path):
    runtime, cycle, dispatches, root, planner, work, work_seal = (
        _cycle_through_completed_work(
            tmp_path, intent_id="CEO-REPAIR-INPUT", review_workers=["worker-b"],
        )
    )
    assert cycle.run_once(root.job_id).action == "REVIEW_CREATED"
    assert cycle.run_once(root.job_id).action == "DISPATCHED"
    review = dispatches[-1]
    subject = runtime.jobs.get_job(work.attempt.job_id)
    reject = _review_body(
        root_id=root.job_id, plan_attempt_id=planner.attempt.attempt_id,
        plan_digest=subject.plan_digest, target_job_id=subject.job_id,
        target_attempt_id=work.attempt.attempt_id,
        target_result_digest=work_seal["role_result_digest"],
        repair_round=0, verdict="reject",
    )
    reject["findings"][0]["message"] = "Retained repair finding: preserve omitted source facts."
    _complete_ohf_role(runtime, review, reject, identity_seed=9931)
    assert cycle.run_once(root.job_id).action == "REPAIR_CREATED"
    assert cycle.run_once(root.job_id).action == "DISPATCHED"
    repair = dispatches[-1]
    job = runtime.jobs.get_job(repair.attempt.job_id)
    supervisor = _supervisor(runtime, tmp_path, FakeAdapter(FakeInspector()))
    return runtime, supervisor, job, repair.attempt, review, work, reject


@pytest.mark.parametrize("fault", [
    "unavailable", "wrong_attempt", "foreign_root", "wrong_round",
    "wrong_verdict", "wrong_review_target", "role_digest", "envelope_digest",
    "creation_missing", "creation_digest", "cancelled", "projection_budget",
])
def test_repair_input_refuses_unbound_original_evidence(tmp_path, monkeypatch, fault):
    runtime, supervisor, job, attempt, review, work, reject = _claimed_repair(tmp_path)
    baseline = supervisor._repair_result_inputs(job, attempt)
    assert baseline["execution_authority"] is False
    assert baseline["rejecting_review"]["result_envelope"]["role_result"] == reject
    assert baseline["rejected"]["job_id"] == work.attempt.job_id
    original = Runtime.validated_role_completion

    def selected(owner, job_id, *, expected_attempt_id):
        result = original(owner, job_id, expected_attempt_id=expected_attempt_id)
        if owner is not runtime or job_id != review.attempt.job_id:
            return result
        if fault == "unavailable":
            raise RuntimeError("PRIVATE_REPAIR_CONTENT_MUST_NOT_ESCAPE")
        if fault == "wrong_attempt":
            return dataclasses.replace(result, attempt=dataclasses.replace(
                result.attempt, attempt_id="ATTEMPT-other"))
        if fault == "foreign_root":
            return dataclasses.replace(result, job=dataclasses.replace(
                result.job, root_job_id="JOB-other"))
        if fault == "wrong_round":
            return dataclasses.replace(result, job=dataclasses.replace(
                result.job, repair_round=9))
        if fault in {"wrong_verdict", "wrong_review_target"}:
            envelope = copy.deepcopy(result.result_envelope)
            field, value = (("verdict", "approve") if fault == "wrong_verdict"
                            else ("reviewed_job_id", "JOB-other"))
            envelope["role_result"][field] = value
            return dataclasses.replace(
                result, result_envelope=envelope,
                result_digest=canonical_digest(envelope),
                role_result_digest=canonical_digest(envelope["role_result"]),
            )
        if fault == "role_digest":
            return dataclasses.replace(result, role_result_digest="0" * 64)
        if fault == "envelope_digest":
            return dataclasses.replace(result, result_digest="0" * 64)
        if fault == "cancelled":
            runtime.jobs.cancel_job(job.job_id, expected_attempt_id=attempt.attempt_id,
                                    expected_fence_generation=attempt.fence_generation)
        return result

    monkeypatch.setattr(Runtime, "validated_role_completion", selected)
    if fault in {"creation_missing", "creation_digest"}:
        event_owner = runtime.events
        lookup = type(event_owner).get_event_by_command_id
        def creation(owner, command_id):
            found = lookup(owner, command_id)
            if owner is event_owner and command_id == job.orchestration_provenance["command_id"]:
                if fault == "creation_missing":
                    return None
                return dataclasses.replace(found, payload=dict(
                    found.payload, rejected_review_result_digest="0" * 64))
            return found
        monkeypatch.setattr(type(event_owner), "get_event_by_command_id", creation)
    if fault == "projection_budget":
        monkeypatch.setattr("control_plane.reviewed_role_input.MAX_PROJECTION_BYTES", 32)
    with pytest.raises(SupervisorError, match="^repair result input is unavailable$"):
        supervisor._repair_result_inputs(job, attempt)
    # These are projection-boundary fault cases, not physical launch tests.
    assert supervisor.adapter.spec is None
    if fault == "cancelled":
        assert runtime.jobs.get_job(job.job_id).status.value == "CANCEL_REQUESTED"
    retained = original(runtime, work.attempt.job_id,
                        expected_attempt_id=work.attempt.attempt_id)
    assert retained.result_envelope == baseline["rejected"]["result_envelope"]


def _paid_repair_ready(tmp_path):
    from control_plane.executive_coo_cycle import CooCycle
    from test_paid_runtime_owner_integration import paid_completed
    state = paid_completed(tmp_path)
    runtime, root, subject = state["runtime"], state["root"], state["completed"]
    completed = runtime.validated_role_completion(
        subject.job_id, expected_attempt_id=state["running"].attempt_id,
    )
    cycle = CooCycle(runtime)
    created = cycle.run_once(root.job_id)
    assert created.action == "REVIEW_CREATED"
    review = runtime.jobs.get_job(created.selected_job_id)
    reject = _review_body(
        root_id=root.job_id, plan_attempt_id=subject.plan_attempt_id,
        plan_digest=subject.plan_digest, plan_step_id=subject.plan_step_id,
        target_job_id=subject.job_id, target_attempt_id=completed.attempt.attempt_id,
        target_result_digest=completed.role_result_digest, repair_round=0, verdict="reject",
    )
    reject["findings"][0]["message"] = (
        "UNIQUE_REPAIR_FINDING: distinguish observed facts from omitted evidence."
    )
    import asyncio
    import hashlib
    from pathlib import Path
    from control_plane.executive_orchestration_result import canonical_bytes
    from test_executive_terminal_return import _PlannerSealedWorkerAdapter

    class RejectAdapter(_PlannerSealedWorkerAdapter):
        async def collect_result(self, ref):
            receipt = await super().collect_result(ref)
            envelope = dict(receipt.result.structured_output,
                            role="review", role_result=copy.deepcopy(reject))
            raw = canonical_bytes(envelope)
            Path(ref.result_path).write_bytes(raw)
            return dataclasses.replace(
                receipt, result=dataclasses.replace(receipt.result, structured_output=envelope),
                result_sha256=hashlib.sha256(raw).hexdigest(),
            )

    review_home = tmp_path / "rejecting-review"
    review_home.mkdir()
    supervisor, adapter = _repair_supervisor(runtime, root, review_home, RejectAdapter)
    active = asyncio.run(supervisor.start_cycle_job(
        review.job_id,
        command_id=f"coo-cycle:{root.job_id}:dispatch:{review.job_id}:attempt:1",
    ))
    assert state["envelope"]["summary"] in adapter.spec.prompt
    receipt = asyncio.run(supervisor.finish_job(active))
    assert receipt.job.status.value == "COMPLETED"
    created = cycle.run_once(root.job_id)
    assert created.action == "REPAIR_CREATED"
    repair = runtime.jobs.get_job(created.selected_job_id)
    return state, repair, review, reject


def _repair_supervisor(runtime, root, tmp_path, adapter_type):
    import os
    import pwd
    from pathlib import Path
    from control_plane.executive_supervisor import ExecutiveSupervisor
    from test_executive_terminal_return import _SEALED_WORKER_SECRET_CANARY
    from test_executive_supervisor import FakeProcessController

    uid, gid = os.geteuid(), os.getegid()
    home = tmp_path / "repair-codex-home"
    home.mkdir(mode=0o700)
    os.chown(home, -1, gid)
    adapter = adapter_type(FakeInspector(), root_job_id=root.job_id, provider_home=home)
    runs = tmp_path / "repair-runs"
    supervisor = ExecutiveSupervisor(
        runtime, adapter, runs_root=runs,
        isolation_roots=(Path(root.worktree).parent, runs),
        worker_user=pwd.getpwuid(uid).pw_name, worker_uid=uid, worker_gid=gid,
        inspector=adapter.inspector, process_controller=FakeProcessController(adapter.inspector),
        secret_canary_verdict=_SEALED_WORKER_SECRET_CANARY,
        require_complete_launch_attestation=True,
    )
    return supervisor, adapter


@pytest.mark.parametrize("fault", ["cancel_after_seal", "prompt_changed_after_seal"])
def test_repair_input_revalidates_sealed_prompt_before_provider_start(tmp_path, monkeypatch, fault):
    import asyncio
    from test_executive_terminal_return import _PlannerSealedWorkerAdapter
    import control_plane.executive_supervisor as owner

    state, repair, _review, _reject = _paid_repair_ready(tmp_path)
    runtime, root = state["runtime"], state["root"]

    class NoStartAdapter(_PlannerSealedWorkerAdapter):
        start_count = 0
        async def start(self, spec):
            self.start_count += 1
            raise AssertionError("repair provider must not start")

    supervisor, adapter = _repair_supervisor(runtime, root, tmp_path, NoStartAdapter)
    sealed = []
    write = owner._write_private_recovery_prompt
    def seal_then_correct(path, prompt):
        write(path, prompt)
        sealed.append((path, path.read_bytes()))
        if fault == "cancel_after_seal":
            current = runtime.jobs.get_job(repair.job_id)
            attempt = runtime.attempts.get_attempt(current.current_attempt_id)
            runtime.jobs.cancel_job(repair.job_id, expected_attempt_id=attempt.attempt_id,
                                    expected_fence_generation=attempt.fence_generation)
    monkeypatch.setattr(owner, "_write_private_recovery_prompt", seal_then_correct)
    render = supervisor._prompt
    def changed_prompt(*args, **kwargs):
        prompt = render(*args, **kwargs)
        return prompt + "\nPRIVATE_PROMPT_DRIFT" if sealed and fault == "prompt_changed_after_seal" else prompt
    monkeypatch.setattr(supervisor, "_prompt", changed_prompt)
    # Fixture seams only for failed-preparation cleanup; no fake completion.
    monkeypatch.setattr(supervisor, "_seal_terminal_assignment", lambda **_kwargs: None)
    monkeypatch.setattr(supervisor, "_fail_claim", lambda *_args: None)
    message = ("repair result input is unavailable" if fault == "cancel_after_seal"
               else "repair input changed after sealing")
    with pytest.raises(SupervisorError, match="^" + message + "$"):
        asyncio.run(supervisor.start_cycle_job(
            repair.job_id,
            command_id=f"coo-cycle:{root.job_id}:dispatch:{repair.job_id}:attempt:1",
        ))
    assert adapter.start_count == 0 and len(sealed) == 1
    if fault == "cancel_after_seal":
        assert runtime.jobs.get_job(repair.job_id).status.value == "CANCEL_REQUESTED"
    path, original = sealed[0]
    assert path.read_bytes() == original and b"PRIVATE_PROMPT_DRIFT" not in original
    assert state["envelope"]["summary"].encode() in original


def _completed_paid_native_repair(tmp_path, monkeypatch):
    import asyncio
    import hashlib
    import json
    from pathlib import Path
    from control_plane.executive_orchestration_result import canonical_bytes
    from control_plane.worker_execution_contract import OrchestrationLaunchSpec, WorkerRecoveryBinding
    from test_executive_terminal_return import _PlannerSealedWorkerAdapter

    state, repair, review, reject = _paid_repair_ready(tmp_path)
    runtime, root = state["runtime"], state["root"]

    class RepairAdapter(_PlannerSealedWorkerAdapter):
        adapter_id = "codex-cli"
        start_count = 0
        async def start(self, spec):
            self.start_count += 1
            return await super().start(spec)
        def reattach(self, spec, binding):
            assert binding.recover_launch_spec(type(spec)) == spec
            self.spec, self.ref = spec, binding.process_ref
            return self.ref
        async def collect_result(self, ref):
            receipt = await super().collect_result(ref)
            packet, _ = json.JSONDecoder().raw_decode(self.spec.prompt[self.spec.prompt.index("{"):])
            selected = packet["orchestration"]["repair_result_inputs"]
            rejected, rejecting_review = selected["rejected"], selected["rejecting_review"]
            lineage = packet["orchestration"]
            body = {
                "schema_version": "mastermind.repair_result/v1",
                **{key: lineage[key] for key in (
                    "root_job_id", "plan_attempt_id", "plan_digest", "plan_step_id",
                    "repair_round", "supersedes_job_id",
                )},
                "rejected_review_job_id": rejecting_review["job_id"],
                "rejected_review_result_digest": rejecting_review["role_result_digest"],
                "artifacts": [], "evidence_digests": [],
            }
            findings = rejecting_review["result_envelope"]["role_result"]["findings"]
            summary = (
                "Repaired supplied analysis: " + rejected["result_envelope"]["summary"]
                + " Addressed retained findings: " + "; ".join(item["message"] for item in findings)
            )
            envelope = dict(receipt.result.structured_output,
                            role="repair", role_result=body, summary=summary)
            raw = canonical_bytes(envelope)
            Path(ref.result_path).write_bytes(raw)
            return dataclasses.replace(
                receipt, result=dataclasses.replace(receipt.result, structured_output=envelope),
                result_sha256=hashlib.sha256(raw).hexdigest(),
            )

    supervisor, adapter = _repair_supervisor(runtime, root, tmp_path, RepairAdapter)
    message = reject["findings"][0]["message"]
    original_summary = state["envelope"]["summary"]
    commission = (Path(root.worktree) / "research" / "commission.md").read_text()
    assert all(marker not in repair.objective and marker not in commission
               for marker in (message, original_summary))
    command = f"coo-cycle:{root.job_id}:dispatch:{repair.job_id}:attempt:1"
    active = asyncio.run(supervisor.start_cycle_job(repair.job_id, command_id=command))
    prompt = adapter.spec.prompt
    assert original_summary in prompt and message in prompt
    packet, _ = json.JSONDecoder().raw_decode(prompt[prompt.index("{"):])
    selected = packet["orchestration"]["repair_result_inputs"]
    assert selected["execution_authority"] is False
    assert selected["rejected"]["result_envelope"] == state["envelope"]
    assert selected["rejecting_review"]["job_id"] == review.job_id
    assert selected["rejecting_review"]["result_envelope"]["role_result"] == reject
    assert packet["authorities"] == ["READ"] and packet["allowed_write_paths"] == []
    sealed_path = Path(adapter.spec.result_schema_path).parent / "worker-prompt.txt"
    sealed = sealed_path.read_bytes()
    assert sealed == prompt.encode()

    def no_fresh_input(*_args, **_kwargs):
        raise AssertionError("original dispatch must reconcile without rebuilding input")
    with monkeypatch.context() as replay_guard:
        replay_guard.setattr(supervisor, "_repair_result_inputs", no_fresh_input)
        replay = asyncio.run(supervisor.start_cycle_job(repair.job_id, command_id=command))
    assert replay.claimed_now is False
    assert replay.attempt.attempt_id == active.lease.attempt.attempt_id
    assert adapter.start_count == 1 and sealed_path.read_bytes() == sealed

    receipt = asyncio.run(supervisor.finish_job(active))
    assert receipt.job.job_id == repair.job_id and receipt.job.status.value == "COMPLETED"
    retained = runtime.validated_role_completion(
        repair.job_id, expected_attempt_id=active.lease.attempt.attempt_id,
    )
    assert retained.result_envelope["role_result"]["supersedes_job_id"] == state["completed"].job_id
    assert original_summary in retained.result_envelope["summary"]
    assert message in retained.result_envelope["summary"]
    attempts = runtime.attempts.list_attempts()
    reopened = Runtime.at(runtime.store.root, create=False, existing_writable=True)
    restored = reopened.validated_role_completion(
        repair.job_id, expected_attempt_id=active.lease.attempt.attempt_id,
    )
    assert restored.result_envelope == retained.result_envelope
    original = reopened.attempts.get_attempt(active.lease.attempt.attempt_id)
    binding = WorkerRecoveryBinding.from_dict(original.launch_metadata["worker_recovery_binding"])
    recovered = binding.recover_launch_spec(OrchestrationLaunchSpec)
    assert recovered.prompt.encode() == sealed and recovered.run_id == original.attempt_id
    assert reopened.attempts.list_attempts() == attempts and adapter.start_count == 1
    return state, repair, retained


def test_repair_consumes_exact_retained_findings_and_keeps_original_launch(tmp_path, monkeypatch):
    _completed_paid_native_repair(tmp_path, monkeypatch)
