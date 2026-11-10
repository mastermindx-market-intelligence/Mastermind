"""Real nested Runtime targets through the installed read consumer.

Physical provider execution and the external Dialogue read response are inert
fixtures. Runtime admission, lineage, current harness/Wake facts, signed JWT
verification, installed composition and bounded original-reply reads are real.
No socket, external message, live profile or parent-consumption claim is made.
"""
from __future__ import annotations

import asyncio
import copy
import hashlib
import time
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from control_plane import executive_runtime as er
from control_plane.ceo_intent import submit_intent
from control_plane.dialogue_source_resolution import (
    DialogueSourceObservation, PhysicalDialogueSourceIdentity,
    attention_source_ref, correlated_source_ref,
)
from control_plane.executive_current_target import CurrentTargetUnavailable, read_current_target
from control_plane.executive_coo_policy import CooCyclePolicy, CooCyclePolicyError
from control_plane.executive_orchestration_principal import OperatorPrincipalObservation
from control_plane.operator_harness_contract import OperationId, ProcessIdentityObservation
from control_plane.wake_events import mint_obligation, mint_obligation_id
from control_plane.wake_ledger import requested_record
from control_plane.wake_persist import WakeLedgerRepository
from integrations.business_mcp_auth.principal_projection import principal_projection
from integrations.session_bridge import installed, native_read, runtime_return
from integrations.session_bridge.dialogue_reply import AgentDialogueContinueWriter
from integrations.session_bridge.runtime_owner import RuntimeFabricTargetProjector, RuntimeCodexTargetProjector
from integrations.session_bridge.schemas import BridgeError
from integrations.slack_agent_dialogue.contract_v2 import build_message_v2
from tests.test_business_mcp_auth_jwt_verifier import _authenticator, _jwks, _policy, _rsa_jwk, _token
from tests.test_executive_os_phase1fc import _register, _v2_intent, _orchestration_profile, _orchestration_attestation
from tests.test_hermes_nested_selected_child import _admit, _nested
from tests.test_hermes_selected_child_target import _runtime_snapshot
from tests.test_workspace_agent_runtime_binding import source


def _verified_principal(*, client_id="nested-fixture-client", scope=None):
    policy = _policy()
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    authenticator, _, _ = _authenticator(policy, _jwks(_rsa_jwk(key)))
    now = int(time.time())
    claims = {"iat": now - 10, "nbf": now - 10, "exp": now + 600, "client_id": client_id}
    if scope is not None:
        claims["scope"] = scope
    return asyncio.run(authenticator.verify_token(_token(key, policy, **claims), now=now))


def _live_nested(tmp_path, *, coordinator_depth=1, material=False, active=True, leaf_count=1):
    runtime = er.Runtime.at(tmp_path / "runtime")
    _register(runtime)
    dialogue = source()
    root = runtime.jobs.get_job(submit_intent(runtime,
        dict(_v2_intent(business_impact="material" if material else "routine"),
             workstream=dialogue.work_ref), dialogue_source=dialogue.to_dict())["job_id"])
    driver = SimpleNamespace(runtime=runtime, config=SimpleNamespace(worker_id="worker-1"))
    if leaf_count == 1:
        state = _nested(driver, root, tmp_path, coordinator_depth=coordinator_depth)
    else:
        coordinator = root
        for depth in range(coordinator_depth):
            coordinator = _admit(driver, coordinator,
                delegation={"descendant_limit": 14 - 2 * depth, "max_depth": 3})[0]
        leaves = _admit(driver, coordinator, step_count=leaf_count)
        state = SimpleNamespace(runtime=runtime, root=root, coordinator=coordinator, leaf=leaves[0])
    state.dialogue = dialogue
    return _activate(state) if active else state


def _activate(state):
    runtime = state.runtime
    dispatch = runtime.attempts.dispatch_cycle_job(state.leaf.job_id, worker_id="worker-1",
        command_id=f"coo-cycle:{state.coordinator.job_id}:dispatch:{state.leaf.job_id}:attempt:1")
    harness = runtime.operator_harness
    profile = _orchestration_profile(dispatch)
    sealed = harness.seal_operator_harness_attempt(dispatch.attempt.attempt_id,
        fence_generation=dispatch.attempt.fence_generation, lease_token=dispatch.lease_token,
        requested=profile)
    operation = OperationId("ohf-op:nested-target-start")
    epoch, generation = harness.reserve_start(sealed.attempt_id,
        fence_generation=sealed.fence_generation, lease_token=dispatch.lease_token, operation_id=operation)
    process = ProcessIdentityObservation(3101, 3101, "nested-fixture-process", "nested-fixture-boot")
    harness.bind_start_result(epoch=epoch, generation=generation, operation_id=operation,
        fence_generation=sealed.fence_generation, lease_token=dispatch.lease_token,
        provider_session_id="nested-fixture-session", process=process)
    principal = OperatorPrincipalObservation(attempt_id=sealed.attempt_id, worker_id="worker-1",
        process_generation_id=generation.process_generation_id, provider_session_id="nested-fixture-session",
        process_identity={"pid": process.pid, "pgid": process.pgid,
            "process_start_identity": process.process_start_identity, "boot_id": process.boot_id},
        os_principal_name="nested-fixture-worker", os_principal_uid=3101,
        provider_home_identity={"path": "/tmp/nested-fixture-home", "device": 3101,
            "inode": 3102, "uid": 3101, "gid": 3101, "mode": 0o700},
        observed_at_ms=runtime.store.now_ms())
    harness.seal_attestation(generation=generation, fence_generation=sealed.fence_generation,
        lease_token=dispatch.lease_token, requested=profile,
        attestation=_orchestration_attestation(profile), principal_observation=principal)
    state.dispatch, state.epoch, state.generation = dispatch, epoch, generation
    state.operation_key = f"exec-{state.leaf.job_id.lower()}"
    state.current = read_current_target(runtime, state.operation_key)
    return state


def _physical(state, *, root_id=None):
    current = state.current
    candidate = {"mode": "ACTIVE_CURRENT_WORKER", "root_job_id": root_id or state.root.job_id,
        "job_id": current.job_id, "attempt_id": current.attempt_id, "worker_id": current.worker_id,
        "evidence_digest": hashlib.sha256(current.attempt_id.encode()).hexdigest()}
    observation = DialogueSourceObservation("T0BRD2AQXQV", "C0BRUL9F2V7",
        "1787961600.000001", "asd-nested-prior-001", "c" * 64)
    attention = attention_source_ref(parent_fingerprint="a" * 64,
        message_key="asd-nested-prior-001", target_seat="coo")
    logical = correlated_source_ref(attention_source_ref=attention, parent_fingerprint="a" * 64,
        operation_key=state.operation_key, candidate=candidate)
    physical = PhysicalDialogueSourceIdentity.create(logical_source_ref=logical,
        obligation_id=mint_obligation_id(source_kind="agent_dialogue_attention", source_ref=logical,
            wake_kind="dialogue_turn_pending"), observation=observation, parent_fingerprint="a" * 64,
        operation_key=state.operation_key, target_seat="coo", candidate=candidate)
    obligation = mint_obligation(wake_kind="dialogue_turn_pending", source_kind="agent_dialogue_attention",
        source_ref=logical, declared_target_seat="coo", job_id=current.job_id, attempt_id=current.attempt_id,
        root_job_id=root_id or state.root.job_id, source_workstream=state.dialogue.work_ref,
        emitted_at="2026-09-14T00:00:00Z")
    WakeLedgerRepository(state.runtime).append_record(requested_record(obligation, physical_source=physical),
                                                     obligation=obligation)


def _return_fixture(state, verified):
    fabric = RuntimeFabricTargetProjector(state.runtime)
    target, = fabric.list_targets()
    binding = target.reply_binding()
    owner = runtime_return.RuntimeSessionReturn(state.runtime, fabric=fabric,
        codex=RuntimeCodexTargetProjector(fabric), socket_path=Path("/tmp/nested-fixture-dialogue.sock"))
    args = {"target_ref": target.target_ref, "operation_key": binding.continuation_operation_key,
            "instruction": "Read the bounded result.", "stop_condition": "Return the existing finding."}
    read_ref = owner.bind_request(principal_projection(verified), args)
    common = {"schema": "mastermind.agent_dialogue.v2", "message_type": "PROGRESS",
        "work_ref": binding.work_ref, "commission_ref": dict(binding.commission_ref),
        "session_ref": binding.session_ref, "actor_ref": dict(binding.current_writer),
        "applies_to": dict(binding.applies_to), "summary": "Bounded nested finding.",
        "evidence_refs": [], "requires_response": False, "created_at": "2026-09-03T01:00:00Z"}
    prior = build_message_v2({**common, "message_key": binding.reply_to_message_key,
        "reply_to_message_key": None, "body": {"stage": "source", "completed": "Ready.", "next": "Read."}})
    request = AgentDialogueContinueWriter._message(request_message=prior,
        context=AgentDialogueContinueWriter._context(binding), instruction=args["instruction"],
        stop_condition=args["stop_condition"], operation_key=args["operation_key"])
    reply_key = "asd-native-reply-" + hashlib.sha256(
        ("mastermind.session_bridge.native_reply.v1\n" + args["operation_key"]).encode()).hexdigest()[:40]
    reply = build_message_v2({**common, "message_key": reply_key, "reply_to_message_key": request["message_key"],
        "body": {"stage": "message_reply", "completed": "The original nested finding.", "next": "Parent decision."}})
    return SimpleNamespace(owner=owner, target=target, args=args, read_ref=read_ref,
        messages=[prior, request, reply], binding=binding)


def _installed(state, fixture, monkeypatch):
    calls = []
    async def carrier(_path, frame):
        calls.append(copy.deepcopy(frame))
        assert frame["operation"] == "read_thread"
        assert frame["args"]["context"]["operation_key"] == state.operation_key
        return {"ok": True, "result": {"thread_ts": fixture.binding.thread_ts,
            "historical_messages": [], "mutated_count": 0,
            "messages": [{"message": copy.deepcopy(message), "primary_ts": f"1787961600.00000{i + 1}",
                          "duplicate_timestamps": []} for i, message in enumerate(fixture.messages)]}}
    return_type, reader_type = runtime_return.RuntimeSessionReturn, native_read.NativeReplyReader
    return_init, reader_init = return_type.__init__, reader_type.__init__
    def returning(self, *args, **kwargs):
        return_init(self, *args, service_call=carrier, **kwargs)
    def reading(self, *args, **kwargs):
        reader_init(self, *args, service_call=carrier, **kwargs)
    # Preserve actual class identity even for modules imported by the factory.
    # Only the external carrier read response is an injected fixture.
    monkeypatch.setattr(return_type, "__init__", returning)
    monkeypatch.setattr(reader_type, "__init__", reading)
    return installed.build_runtime_session_bridge(state.runtime,
        dialogue_socket_path=Path("/tmp/nested-fixture-dialogue.sock")), calls


def _call(owner, verified, tool, arguments):
    return asyncio.run(owner.handle_frame({"schema": installed.PRIVATE_SCHEMA, "tool": tool,
        "principal": installed.principal_frame(verified), "arguments": arguments}))


@pytest.mark.parametrize("coordinator_depth", [1, 2])
def test_actual_nested_installed_target_resolve_and_original_reply_read(tmp_path, monkeypatch, coordinator_depth):
    state = _live_nested(tmp_path, coordinator_depth=coordinator_depth)
    _physical(state)
    verified = _verified_principal()
    fixture = _return_fixture(state, verified)
    owner, calls = _installed(state, fixture, monkeypatch)
    before = _runtime_snapshot(state.runtime)
    listed = _call(owner, verified, "session_targets", {"kind": "fabric_attempt"})
    assert listed["ok"] is True, listed
    target, = listed["data"]
    assert target["target_ref"] == fixture.target.target_ref
    assert target["root_job_id"] == state.root.job_id
    assert target["work_ref"] == state.dialogue.work_ref
    assert target["addressable"] is True
    assert not set(target) & {"execution_available", "placement_eligible", "admission_authorized"}
    for kind in ("t3", "codex"):
        assert _call(owner, verified, "session_targets", {"kind": kind})["data"] == []
    resolved = RuntimeFabricTargetProjector(state.runtime).resolve(target["target_ref"])
    assert resolved.epoch.job_id == state.leaf.job_id
    assert resolved.epoch.attempt_id == state.dispatch.attempt.attempt_id
    observed = _call(owner, verified, "session_reply_read", {"read_ref": fixture.read_ref})
    assert observed["ok"] is True, observed
    assert observed["data"]["text"] == "The original nested finding."
    assert observed["data"]["parent_consumed"] is False
    assert _runtime_snapshot(state.runtime) == before
    assert calls and all(call["operation"] == "read_thread" for call in calls)


def test_nested_target_rechecks_worker_after_actual_physical_source_read(tmp_path):
    from integrations.workspace_agent_runtime_binding import _read_physical_source
    state = _live_nested(tmp_path)
    _physical(state)
    def move(*args):
        physical = _read_physical_source(state.runtime, *args)
        state.runtime.workers.set_worker_status("worker-1", er.WorkerStatus.DRAINING)
        return physical
    assert RuntimeFabricTargetProjector(state.runtime, physical_source_reader=move).list_targets() == []


def test_nested_target_refuses_unavailable_current_hierarchy_policy(tmp_path, monkeypatch):
    state = _live_nested(tmp_path)
    _physical(state)
    original = CooCyclePolicy.load
    def load(cls, path=None, *, version=1):
        if version == 2:
            raise CooCyclePolicyError("fixture hierarchy policy unavailable")
        return original(path, version=version)
    monkeypatch.setattr(CooCyclePolicy, "load", classmethod(load))
    before = _runtime_snapshot(state.runtime)
    assert RuntimeFabricTargetProjector(state.runtime).list_targets() == []
    with pytest.raises(CurrentTargetUnavailable):
        read_current_target(state.runtime, state.operation_key)
    assert _runtime_snapshot(state.runtime) == before


def test_deepest_full_root_target_and_original_reply_fit_unchanged_budgets(tmp_path):
    state = _live_nested(tmp_path, coordinator_depth=2, leaf_count=11)
    assert len(state.runtime.jobs.list_jobs()) == 17
    _physical(state)
    fixture = _return_fixture(state, _verified_principal())
    before = _runtime_snapshot(state.runtime)
    with state.runtime.observe_bounded_read() as observation:
        job, identity = observation.read_current_target_identity_bounded(operation_key=state.operation_key)
    _ = observation.receipt
    assert job.job_id == state.leaf.job_id and identity.root_job_id == state.root.job_id
    with state.runtime.observe_bounded_read() as observation:
        facts = observation.read_session_live_writer_bounded(read_ref=fixture.read_ref)
    _ = observation.receipt
    assert facts[3].job_id == job.job_id
    assert _runtime_snapshot(state.runtime) == before


def test_nested_target_refuses_mixed_job_snapshot_and_foreign_root(tmp_path):
    state = _live_nested(tmp_path)
    _physical(state)
    current = state.runtime.jobs.get_job(state.leaf.job_id)
    before = _runtime_snapshot(state.runtime)
    for changed in (replace(current, current_attempt_id="ATT-" + "f" * 32),
                    replace(current, root_job_id=state.coordinator.job_id)):
        projector = RuntimeFabricTargetProjector(state.runtime, job_reader=lambda: [changed])
        assert projector.list_targets() == []
    assert _runtime_snapshot(state.runtime) == before


def test_nested_current_target_rechecks_exact_held_worker_after_discovery(tmp_path):
    state = _live_nested(tmp_path)
    _physical(state)
    projector = RuntimeFabricTargetProjector(state.runtime)
    target, = projector.list_targets()
    state.runtime.workers.set_worker_status("worker-1", er.WorkerStatus.DRAINING)
    before = _runtime_snapshot(state.runtime)
    assert projector.list_targets() == []
    with pytest.raises(BridgeError) as refused:
        projector.resolve(target.target_ref)
    assert refused.value.code == "native_target_stale"
    assert _runtime_snapshot(state.runtime) == before


def test_nested_target_refuses_foreign_physical_root(tmp_path):
    state = _live_nested(tmp_path)
    _physical(state, root_id=state.coordinator.job_id)
    before = _runtime_snapshot(state.runtime)
    assert RuntimeFabricTargetProjector(state.runtime).list_targets() == []
    assert _runtime_snapshot(state.runtime) == before


def test_nested_original_reply_uses_one_shared_loader_and_refuses_budget_exhaustion(tmp_path, monkeypatch):
    state = _live_nested(tmp_path, coordinator_depth=2)
    _physical(state)
    fixture = _return_fixture(state, _verified_principal())
    loader_type = er._BoundedRoleResultLoader
    created = []
    class CountingLoader(loader_type):
        def __init__(self, connection):
            created.append(connection)
            super().__init__(connection)
    monkeypatch.setattr(er, "_BoundedRoleResultLoader", CountingLoader)
    before = _runtime_snapshot(state.runtime)
    with state.runtime.observe_bounded_read() as observation:
        facts = observation.read_session_live_writer_bounded(read_ref=fixture.read_ref)
    _ = observation.receipt
    assert len(created) == 1
    assert facts[3].root_job_id == state.root.job_id
    assert facts[3].job_id == state.leaf.job_id
    monkeypatch.setattr(er, "BOUNDED_ROLE_RESULT_MAX_ROWS", 8)
    with pytest.raises(er.RuntimeProofError):
        with state.runtime.observe_bounded_read() as exhausted:
            exhausted.read_session_live_writer_bounded(read_ref=fixture.read_ref)
    with pytest.raises(er.RuntimeProofError):
        _ = exhausted.receipt
    assert _runtime_snapshot(state.runtime) == before


def test_nested_reply_refuses_foreign_authenticated_caller_and_revoked_worker(tmp_path, monkeypatch):
    state = _live_nested(tmp_path)
    _physical(state)
    verified = _verified_principal()
    fixture = _return_fixture(state, verified)
    owner, calls = _installed(state, fixture, monkeypatch)
    before = _runtime_snapshot(state.runtime)
    denied = _call(owner, _verified_principal(client_id="foreign-fixture-client"),
                   "session_reply_read", {"read_ref": fixture.read_ref})
    assert denied["error"]["code"] == "reply_unavailable"
    assert calls == []
    assert _runtime_snapshot(state.runtime) == before
    state.runtime.workers.set_worker_status("worker-1", er.WorkerStatus.DRAINING)
    before = _runtime_snapshot(state.runtime)
    denied = _call(owner, verified, "session_reply_read", {"read_ref": fixture.read_ref})
    assert denied["error"]["code"] == "reply_unavailable"
    assert calls == []
    assert _runtime_snapshot(state.runtime) == before


def test_nested_current_target_exposes_actual_repair_and_refuses_superseded_work(tmp_path):
    from tests.test_executive_coo_hierarchy_cycle import finish_result
    from tests.test_executive_coo_hierarchy_service import _complete
    from tests.test_executive_os_phase1fc import _review_body
    state = _live_nested(tmp_path, material=True, active=False)
    runtime, parent, leaf = state.runtime, state.coordinator, state.leaf
    work = runtime.attempts.dispatch_cycle_job(leaf.job_id, worker_id="worker-1",
        command_id=f"coo-cycle:{parent.job_id}:dispatch:{leaf.job_id}:attempt:1")
    finish_result(runtime, work)
    complete = runtime.validated_role_completion(leaf.job_id, expected_attempt_id=work.attempt.attempt_id)
    _register(runtime, "worker-2")
    review = runtime.jobs.create_cycle_review(parent.job_id, leaf.job_id,
        command_id=f"coo-cycle:{parent.job_id}:create-review:{leaf.job_id}:1")
    reviewed = runtime.attempts.dispatch_cycle_job(review.job_id, worker_id="worker-2",
        command_id=f"coo-cycle:{parent.job_id}:dispatch:{review.job_id}:attempt:1")
    seal, _ = _complete(runtime, reviewed, _review_body(root_id=state.root.job_id,
        plan_attempt_id=leaf.plan_attempt_id, plan_digest=leaf.plan_digest, plan_step_id=leaf.plan_step_id,
        target_job_id=leaf.job_id, target_attempt_id=work.attempt.attempt_id,
        target_result_digest=complete.role_result_digest, repair_round=0, verdict="reject"))
    state.leaf = runtime.jobs.create_cycle_repair(parent.job_id, leaf.job_id, review.job_id,
        command_id=f"coo-cycle:{parent.job_id}:create-repair:{leaf.job_id}:{review.job_id}:{seal['role_result_digest']}:1")
    _activate(state)
    _physical(state)
    before = _runtime_snapshot(runtime)
    target, = RuntimeFabricTargetProjector(runtime).list_targets()
    assert target.epoch.job_id == state.leaf.job_id
    assert target.epoch.root_job_id == state.root.job_id
    with pytest.raises(CurrentTargetUnavailable):
        read_current_target(runtime, f"exec-{leaf.job_id.lower()}")
    assert _runtime_snapshot(runtime) == before
