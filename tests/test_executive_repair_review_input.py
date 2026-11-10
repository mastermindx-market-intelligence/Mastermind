"""Native repair-review consumer proof; physical adapters are inert fixtures."""
import asyncio
import copy
import dataclasses
import hashlib
import json
from pathlib import Path

import pytest

from control_plane.executive_coo_cycle import CooCycle
from control_plane.executive_orchestration_result import canonical_bytes
from control_plane.executive_runtime import AttemptLease, Runtime
from control_plane.worker_execution_contract import OrchestrationLaunchSpec, WorkerRecoveryBinding
from test_executive_os_phase1fc import _review_body
from test_executive_repair_input import _completed_paid_native_repair, _repair_supervisor
from test_executive_terminal_return import _PlannerSealedWorkerAdapter


def _repair_review_ready(tmp_path, monkeypatch):
    state, repair, retained = _completed_paid_native_repair(tmp_path, monkeypatch)
    runtime, root = state["runtime"], state["root"]
    quotas = {}
    for name in ("codex-plan-small", "codex-root-default", "codex-read"):
        quota = runtime.workers.get_quota_class("codex-plan", name)
        quotas[name] = {key: copy.deepcopy(getattr(quota, key)) for key in (
            "provider", "capabilities", "model", "effort", "cost_class", "metadata",
        )}
    runtime.workers.register_worker(
        "codex-review", provider="codex", account_label="codex-review-account",
        worker_type="codex-cli", capabilities=["read", "research"], quota_classes=quotas,
    )
    created = CooCycle(runtime).run_once(root.job_id)
    assert created.action == "REVIEW_CREATED"
    review = runtime.jobs.get_job(created.selected_job_id)
    assert review.reviews_job_id == repair.job_id
    return state, repair, retained, review


def _claim_review(runtime, root, review, supervisor):
    command = f"coo-cycle:{root.job_id}:dispatch:{review.job_id}:attempt:1"
    selected = runtime.attempts.dispatch_cycle_job(
        review.job_id, command_id=command, lease_owner=supervisor.instance_id,
        worker_id="codex-review", quota_class="codex-plan-small",
    )
    assert selected.claimed_now and selected.lease_token
    return selected, command


def _received_review_input(prompt):
    marker = "--- SEALED REPAIR REVIEW INPUT ---\n"
    body = prompt.split(marker, 1)[1].split("\n--- END SEALED REPAIR REVIEW INPUT ---", 1)[0]
    return json.loads(body.rsplit("\n", 1)[-1])


class RetainedRepairReviewAdapter(_PlannerSealedWorkerAdapter):
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
        role = packet["orchestration"]["role"]
        if role == "review":
            projection = _received_review_input(self.spec.prompt)
            subject = projection["reviewed_revision"]
            body = _review_body(
                root_id=subject["root_job_id"], plan_attempt_id=subject["plan_attempt_id"],
                plan_digest=subject["plan_digest"], plan_step_id=subject["plan_step_id"],
                target_job_id=subject["job_id"], target_attempt_id=subject["attempt_id"],
                target_result_digest=projection["reviewed_role_result_digest"],
                repair_round=subject["repair_round"], verdict="approve",
            )
            summary = "Reviewed retained repair contents: " + projection["reviewed_result_envelope"]["summary"]
        else:
            assert role == "aggregation"
            handoff = packet["orchestration"]["aggregation_handoff"]
            inputs = packet["orchestration"]["aggregation_result_inputs"]["revisions"]
            keys = {"ordinal", "plan_step_id", "current_job_id", "current_attempt_id",
                    "current_result_digest", "repair_round", "review_required",
                    "qualifying_review_job_id", "qualifying_review_attempt_id",
                    "qualifying_review_result_digest"}
            summary = "; ".join(row["current"]["result_envelope"]["summary"] for row in inputs)
            body = {
                "schema_version": handoff["aggregate_result_schema"],
                **{key: handoff[key] for key in (
                    "root_job_id", "handoff_digest", "policy_sha", "plan_attempt_id", "plan_digest",
                )},
                "revisions": [{key: value for key, value in row.items() if key in keys}
                              for row in handoff["revisions"]],
                "aggregate_summary": summary, "evidence_digests": [],
            }
            if body["schema_version"] == "mastermind.aggregation_result/v2":
                body["coordinator_job_id"] = packet["job_id"]
        envelope = dict(receipt.result.structured_output, role=role, role_result=body, summary=summary)
        raw = canonical_bytes(envelope)
        Path(ref.result_path).write_bytes(raw)
        return dataclasses.replace(
            receipt, result=dataclasses.replace(receipt.result, structured_output=envelope),
            result_sha256=hashlib.sha256(raw).hexdigest(),
        )


def test_native_repair_review_receives_retained_result_and_keeps_original_input(tmp_path, monkeypatch):
    state, repair, retained, review = _repair_review_ready(tmp_path, monkeypatch)
    runtime, root = state["runtime"], state["root"]
    work = tmp_path / "repair-review"
    work.mkdir()
    supervisor, adapter = _repair_supervisor(runtime, root, work, RetainedRepairReviewAdapter)
    claimed, command = _claim_review(runtime, root, review, supervisor)
    active = asyncio.run(supervisor._start_claimed_job(
        review.job_id, AttemptLease(attempt=claimed.attempt, lease_token=claimed.lease_token),
    ))
    summary = retained.result_envelope["summary"]
    assert summary not in review.objective
    assert summary in adapter.spec.prompt
    projection = _received_review_input(adapter.spec.prompt)
    assert projection["reviewed_revision"]["orchestration_role"] == "repair"
    assert projection["reviewed_revision"]["job_id"] == repair.job_id
    assert projection["reviewed_revision"]["attempt_id"] == retained.attempt.attempt_id
    assert projection["reviewed_result_envelope"] == retained.result_envelope
    assert projection["reviewed_result_envelope_digest"] == retained.result_digest
    assert projection["reviewed_role_result_digest"] == retained.role_result_digest
    packet, _ = json.JSONDecoder().raw_decode(adapter.spec.prompt[adapter.spec.prompt.index("{"):])
    assert packet["authorities"] == ["READ"] and packet["allowed_write_paths"] == []
    sealed_path = Path(adapter.spec.result_schema_path).parent / "worker-prompt.txt"
    sealed = sealed_path.read_bytes()
    assert sealed == adapter.spec.prompt.encode()

    def no_fresh_input(*_args, **_kwargs):
        raise AssertionError("review replay must retain the original sealed input")
    with monkeypatch.context() as guard:
        guard.setattr(supervisor, "_reviewed_role_prompt_suffix", no_fresh_input)
        replay = runtime.attempts.dispatch_cycle_job(
            review.job_id, command_id=command, lease_owner=supervisor.instance_id,
            worker_id="codex-review", quota_class="codex-plan-small",
        )
    assert replay.claimed_now is False and replay.attempt.attempt_id == claimed.attempt.attempt_id
    assert adapter.start_count == 1 and sealed_path.read_bytes() == sealed

    completed = asyncio.run(supervisor.finish_job(active))
    assert completed.job.status.value == "COMPLETED"
    result = runtime.validated_role_completion(
        review.job_id, expected_attempt_id=claimed.attempt.attempt_id,
    )
    assert summary in result.result_envelope["summary"]
    reopened = Runtime.at(runtime.store.root, create=False, existing_writable=True)
    original = reopened.attempts.get_attempt(claimed.attempt.attempt_id)
    binding = WorkerRecoveryBinding.from_dict(original.launch_metadata["worker_recovery_binding"])
    assert binding.recover_launch_spec(OrchestrationLaunchSpec).prompt.encode() == sealed
    assert reopened.validated_role_completion(
        review.job_id, expected_attempt_id=claimed.attempt.attempt_id,
    ).result_envelope == result.result_envelope

    # Distinct Worker/account/home do not turn this same-UID fixture into an
    # independent native review. The canonical owner must request replacement.
    from control_plane.executive_runtime import _review_attempt_is_independent
    with runtime.store.read() as connection:
        assert not _review_attempt_is_independent(
            connection, review_attempt_id=claimed.attempt.attempt_id,
            reviewed_attempt_id=retained.attempt.attempt_id,
        )
    replacement = CooCycle(runtime).run_once(root.job_id)
    assert replacement.action == "REVIEW_CREATED"
    assert replacement.selected_job_id != review.job_id
    from control_plane.executive_runtime import StateConflict
    with pytest.raises(StateConflict, match="immutable handoff"):
        runtime.jobs.get_cycle_handoff(root.job_id)

    # The replacement uses the existing OHF fixture owner with a deliberately
    # distinct principal observation. This is source composition, not physical
    # account enrollment or an installed independent-review receipt.
    replacement_job = runtime.jobs.get_job(replacement.selected_job_id)
    replacement_claim, _ = _claim_review(runtime, root, replacement_job, supervisor)
    replacement_job = runtime.jobs.get_job(replacement_job.job_id)
    replacement_prompt = supervisor._prompt(
        replacement_job, replacement_claim.attempt,
        supervisor._effective_grant(replacement_job, replacement_claim.attempt),
    )
    supplied = _received_review_input(replacement_prompt)
    assert supplied["reviewed_result_envelope"] == retained.result_envelope
    revision = supplied["reviewed_revision"]
    approve = _review_body(
        root_id=revision["root_job_id"], plan_attempt_id=revision["plan_attempt_id"],
        plan_digest=revision["plan_digest"], plan_step_id=revision["plan_step_id"],
        target_job_id=revision["job_id"], target_attempt_id=revision["attempt_id"],
        target_result_digest=supplied["reviewed_role_result_digest"],
        repair_round=revision["repair_round"], verdict="approve",
    )
    from test_executive_os_phase1fc import _complete_ohf_role
    _complete_ohf_role(runtime, replacement_claim, approve, identity_seed=9957)
    with runtime.store.read() as connection:
        assert _review_attempt_is_independent(
            connection, review_attempt_id=replacement_claim.attempt.attempt_id,
            reviewed_attempt_id=retained.attempt.attempt_id,
        )
    assert CooCycle(runtime).run_once(root.job_id).action == "HANDOFF_CREATED"
    handoff = runtime.jobs.get_cycle_handoff(root.job_id)
    assert handoff["revisions"][0]["current_job_id"] == repair.job_id
    assert handoff["revisions"][0]["repair_round"] == 1
    assert handoff["revisions"][0]["qualifying_review_job_id"] == replacement_job.job_id

    parent = asyncio.run(supervisor.start_cycle_job(
        root.job_id, command_id=f"coo-cycle:{root.job_id}:dispatch:{root.job_id}:attempt:1",
    ))
    packet, _ = json.JSONDecoder().raw_decode(adapter.spec.prompt[adapter.spec.prompt.index("{"):])
    received = packet["orchestration"]["aggregation_result_inputs"]["revisions"][0]
    assert received["current"]["result_envelope"] == retained.result_envelope
    assert received["current"]["job_id"] == repair.job_id
    assert received["qualifying_review"]["job_id"] == replacement_job.job_id
    completed_parent = asyncio.run(supervisor.finish_job(parent))
    assert completed_parent.job.job_id == root.job_id
    assert completed_parent.job.status.value == "COMPLETED"
    parent_result = runtime.validated_role_completion(
        root.job_id, expected_attempt_id=parent.lease.attempt.attempt_id,
    )
    assert parent_result.result_envelope["role_result"]["aggregate_summary"] == summary
    attempts = runtime.attempts.list_attempts()
    reopened = Runtime.at(runtime.store.root, create=False, existing_writable=True)
    assert reopened.validated_role_completion(
        root.job_id, expected_attempt_id=parent.lease.attempt.attempt_id,
    ).result_envelope == parent_result.result_envelope
    assert CooCycle(reopened).run_once(root.job_id).action == "NO_ACTION"
    assert reopened.attempts.list_attempts() == attempts
    assert adapter.start_count == 2 and sealed_path.read_bytes() == sealed


@pytest.mark.parametrize("fault", [
    "unavailable", "wrong_attempt", "role_digest", "envelope_digest",
    "creation_digest", "cancelled", "projection_budget", "render_budget",
])
def test_repair_review_refuses_unqualified_retained_input(tmp_path, monkeypatch, fault):
    from control_plane.executive_supervisor import SupervisorError

    state, repair, retained, review = _repair_review_ready(tmp_path, monkeypatch)
    runtime, root = state["runtime"], state["root"]
    work = tmp_path / "repair-review"
    work.mkdir()
    supervisor, adapter = _repair_supervisor(runtime, root, work, RetainedRepairReviewAdapter)
    claimed, _ = _claim_review(runtime, root, review, supervisor)
    current = runtime.jobs.get_job(review.job_id)
    baseline = supervisor._reviewed_role_prompt_suffix(current, claimed.attempt)
    projection = _received_review_input(baseline)
    assert projection["reviewed_result_envelope"] == retained.result_envelope
    original = Runtime.validated_role_completion

    def selected(owner, job_id, *, expected_attempt_id):
        found = original(owner, job_id, expected_attempt_id=expected_attempt_id)
        if owner is not runtime or job_id != repair.job_id:
            return found
        if fault == "unavailable":
            raise RuntimeError("PRIVATE_REPAIR_RESULT_MUST_NOT_ESCAPE")
        if fault == "wrong_attempt":
            return dataclasses.replace(found, attempt=dataclasses.replace(
                found.attempt, attempt_id="ATTEMPT-other"))
        if fault == "role_digest":
            return dataclasses.replace(found, role_result_digest="0" * 64)
        if fault == "envelope_digest":
            return dataclasses.replace(found, result_digest="0" * 64)
        if fault == "cancelled":
            runtime.jobs.cancel_job(
                current.job_id, expected_attempt_id=claimed.attempt.attempt_id,
                expected_fence_generation=claimed.attempt.fence_generation,
            )
        return found

    monkeypatch.setattr(Runtime, "validated_role_completion", selected)
    if fault == "creation_digest":
        lookup = type(runtime.store).get_event_by_command_id
        def wrong_creation(owner, command_id, **kwargs):
            found = lookup(owner, command_id, **kwargs)
            if owner is runtime.store and command_id == current.orchestration_provenance["command_id"]:
                return dataclasses.replace(found, payload=dict(
                    found.payload, reviewed_result_digest="0" * 64))
            return found
        monkeypatch.setattr(type(runtime.store), "get_event_by_command_id", wrong_creation)
    if fault in {"projection_budget", "render_budget"}:
        limit = 32 if fault == "projection_budget" else len(canonical_bytes(projection))
        monkeypatch.setattr("control_plane.reviewed_role_input.MAX_PROJECTION_BYTES", limit)
    with pytest.raises(SupervisorError, match="^reviewed repair input is not qualified$") as refused:
        supervisor._reviewed_role_prompt_suffix(current, claimed.attempt)
    assert "PRIVATE_" not in str(refused.value)
    assert adapter.start_count == 0 and adapter.spec is None
    if fault == "cancelled":
        assert runtime.jobs.get_job(current.job_id).status.value == "CANCEL_REQUESTED"
    assert original(runtime, repair.job_id, expected_attempt_id=retained.attempt.attempt_id
                    ).result_envelope == retained.result_envelope


@pytest.mark.parametrize("fault", ["cancel_after_seal", "suffix_drift", "suffix_removed"])
def test_repair_review_revalidates_exact_suffix_before_start(tmp_path, monkeypatch, fault):
    import control_plane.executive_supervisor as owner

    state, repair, retained, review = _repair_review_ready(tmp_path, monkeypatch)
    runtime, root = state["runtime"], state["root"]
    work = tmp_path / "repair-review"
    work.mkdir()
    supervisor, adapter = _repair_supervisor(runtime, root, work, RetainedRepairReviewAdapter)
    claimed, _ = _claim_review(runtime, root, review, supervisor)
    sealed = []
    write = owner._write_private_recovery_prompt
    def seal_then_correct(path, prompt):
        write(path, prompt)
        sealed.append((path, path.read_bytes()))
        if fault == "cancel_after_seal":
            runtime.jobs.cancel_job(
                review.job_id, expected_attempt_id=claimed.attempt.attempt_id,
                expected_fence_generation=claimed.attempt.fence_generation,
            )
    monkeypatch.setattr(owner, "_write_private_recovery_prompt", seal_then_correct)
    render = supervisor._reviewed_role_prompt_suffix
    def changed_suffix(*args, **kwargs):
        result = render(*args, **kwargs)
        if sealed and fault == "suffix_removed":
            return ""
        return result + "\nPRIVATE_SUFFIX_DRIFT" if sealed and fault == "suffix_drift" else result
    monkeypatch.setattr(supervisor, "_reviewed_role_prompt_suffix", changed_suffix)
    # Isolate failed-preparation cleanup; these seams never complete a result.
    monkeypatch.setattr(supervisor, "_seal_terminal_assignment", lambda **_kwargs: None)
    monkeypatch.setattr(supervisor, "_fail_claim", lambda *_args: None)
    expected = ("reviewed subject input is not qualified" if fault == "cancel_after_seal"
                else "review subject changed after input sealing")
    with pytest.raises(owner.SupervisorError, match="^" + expected + "$"):
        asyncio.run(supervisor._start_claimed_job(
            review.job_id, AttemptLease(attempt=claimed.attempt, lease_token=claimed.lease_token),
        ))
    assert adapter.start_count == 0 and adapter.spec is None and len(sealed) == 1
    path, original = sealed[0]
    assert path.read_bytes() == original and b"PRIVATE_SUFFIX_DRIFT" not in original
    assert retained.result_envelope["summary"].encode() in original
    if fault == "cancel_after_seal":
        assert runtime.jobs.get_job(review.job_id).status.value == "CANCEL_REQUESTED"


def test_supervisor_keeps_native_work_review_suffix_unchanged(tmp_path):
    from test_reviewed_role_input import _seeded_review
    from test_executive_supervisor import FakeAdapter, FakeInspector, _supervisor

    runtime, _root, subject, review, attempt, _, _ = _seeded_review(tmp_path)
    supervisor = _supervisor(runtime, tmp_path, FakeAdapter(FakeInspector()))
    assert subject.orchestration_role == "work"
    assert supervisor._reviewed_role_prompt_suffix(review, attempt) == ""
