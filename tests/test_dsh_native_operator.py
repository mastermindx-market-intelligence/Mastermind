"""OHF/native ownership and actual SDK final-write races, without providers."""
import asyncio
from dataclasses import replace
import hashlib
import os
from pathlib import Path
from types import SimpleNamespace
import sys

import pytest

from control_plane.operator_harness_contract import (
    AuthRealmFact, CapabilityManifest, EventCursor, NativeHelperPolicy,
    ObservedHarnessAttestation, OperationId, ProcessGenerationRef, ProcessLiveness,
    ProviderSessionHandoff, ProviderWriterState, RequestedExecutionProfile,
    SessionEpochRef, TurnRef, WorkspaceIdentity, compare_launch,
)
from control_plane.worker_execution_contract import BinaryAttestation
from integrations.acp_worker.turn import AcpProfile
from integrations.deepseek_harness import operator_adapter as module
from integrations.deepseek_harness.native_connection import NativeEffectUnknown, NativeWriteGuard
from integrations.deepseek_harness.native_protocol import NativeClaim, NativeProtocolError, NativeResult, NativeTerminal
from integrations.deepseek_harness.operator_adapter import NativeLaunchBinding, NativeOperatorAdapter, NativeOperatorError


class FixtureNative:
    def __init__(self, client):
        self.client = client
        self.provider_session_id = None
        self.open_calls = self.prompt_calls = self.stop_calls = 0
        self.done = asyncio.Event()
        self.stop_reason = "end_turn"
        process = SimpleNamespace(returncode=None)
        identity = SimpleNamespace(pid=987654, pgid=987654, session_id=987654,
            process_start_identity="fixture-start", boot_session_id="fixture-boot",
            effective_uid=os.geteuid())
        self.resource = SimpleNamespace(process=process, identity=identity,
            identity_matches=lambda: process.returncode is None,
            inspector=SimpleNamespace(boot_session_id=lambda: "fixture-boot"))

    async def open(self, *, provider_session_id, **kwargs):
        self.open_calls += 1
        self.client.before_send("session/resume" if provider_session_id else "session/new")
        self.client.before_write()
        self.provider_session_id = provider_session_id or "native-fixture-session"

    async def begin_prompt(self, operation_id, text):
        self.client.before_send("session/prompt")
        self.client.before_write()
        self.prompt_calls += 1
        self.done.clear()
        self.claim = NativeClaim(operation_id, self.prompt_calls, self.provider_session_id,
                                 "native-message-"+str(self.prompt_calls), self.prompt_calls, self.prompt_calls*5)
        self.client.on_update({"kind": "agent_message_chunk", "text_bytes": 7, "text_sha256": "a"*64})
        return self.claim

    async def result(self, claim, *, timeout_seconds):
        assert claim == self.claim
        await self.done.wait()
        return NativeResult(self.stop_reason, NativeTerminal(claim.operation_id, claim.request_id,
                            claim, claim.through_seq+5, claim.native_turn+1, 2))

    async def interrupt(self, claim):
        assert claim == self.claim
        self.client.before_send("_mastermind/native_cancel")
        self.client.before_write()
        self.stop_calls += 1
        self.stop_reason = "cancelled"
        self.done.set()
        return "requested"

    async def close(self, reason=None):
        self.resource.process.returncode = 0
        return SimpleNamespace(protocol_settled=True,
            physical=SimpleNamespace(settled=True, exit_code=0, signal_sent=reason is not None))


async def fixture(tmp_path, monkeypatch, *, served_model="fixture"):
    workspace, home, captures = [tmp_path.resolve()/name for name in ("workspace", "home", "captures")]
    for path in (workspace, home, captures):
        path.mkdir(mode=0o700)
    binary_path = Path(sys.executable).resolve()
    info = binary_path.stat()
    binary = BinaryAttestation(str(binary_path), str(binary_path), "fixture",
        hashlib.sha256(binary_path.read_bytes()).hexdigest(), None, info.st_size,
        info.st_dev, info.st_ino, info.st_mode & 0o7777, info.st_uid, info.st_gid, info.st_mtime_ns)
    info = workspace.stat()
    identity = WorkspaceIdentity(str(workspace), "b"*40, info.st_dev, info.st_ino, info.st_uid, info.st_gid)
    requested = RequestedExecutionProfile("fixture-worker", "acp", "fixture", module.DSH_NATIVE_HARNESS_KIND,
        binary.sha256, binary.version, identity, "fixture-only", "fixture-only", "fixture-only",
        CapabilityManifest(), NativeHelperPolicy.DISABLED, "c"*64)
    observed = ObservedHarnessAttestation(served_model, binary.version, binary.sha256, (), (), (), (),
        "fixture-only", "fixture-only", "fixture-only", None, AuthRealmFact("fixture-worker", "acp"), identity)
    guards, revoked = [], set()
    def require(operation, epoch, generation, method, session):
        guards.append((operation.command_id, method, session))
        if operation.command_id in revoked:
            raise NativeOperatorError("fixture current authority revoked")
    binding = NativeLaunchBinding(binary, (str(binary_path),), {"DSH_HOME": str(home)}, home, captures,
        AcpProfile("deepseek-harness-acp", "0.0.1"), lambda: None, lambda _native: observed, require)
    monkeypatch.setattr(module, "NativeAcpProcess", FixtureNative)
    monkeypatch.setattr(module, "_process_group_exists", lambda _pgid: False)
    adapter = NativeOperatorAdapter(workspace, lambda _turn: "original native message", requested, binding)
    epoch = SessionEpochRef("epoch-fixture", "attempt-fixture", "fixture-worker", 1)
    generation = ProcessGenerationRef("generation-fixture", epoch.session_epoch_id, 1, epoch.worker_id)
    turn = TurnRef("turn-fixture", epoch.session_epoch_id, generation.process_generation_id, epoch.attempt_id)
    return SimpleNamespace(adapter=adapter, requested=requested, observed=observed, epoch=epoch,
                           generation=generation, turn=turn, guards=guards, revoked=revoked)


async def start(f):
    return await asyncio.to_thread(f.adapter.start_session, operation_id=OperationId("ohf-op:fixture-start"),
        requested=f.requested, epoch=f.epoch, generation=f.generation)


async def begin(f, *, turn=None):
    return await asyncio.to_thread(f.adapter.begin_turn, operation_id=OperationId("ohf-op:fixture-prompt"),
        turn=turn or f.turn, generation=f.generation, launch=compare_launch(f.requested, f.observed))


def cursor(f, turn=None, sequence=0):
    return EventCursor(f.epoch.attempt_id, f.epoch.session_epoch_id, f.generation.process_generation_id,
                       sequence, (turn or f.turn).turn_id)


def test_original_ohf_turn_stop_candidate_and_exact_release(tmp_path, monkeypatch):
    async def exercise():
        f = await fixture(tmp_path, monkeypatch)
        started = await start(f)
        assert started.provider_session_id == "native-fixture-session"
        ack = await begin(f)
        assert ack.acknowledged and ack.provider_native_turn_id == "1"
        collections = [asyncio.create_task(asyncio.to_thread(f.adapter.read_events, cursor(f))) for _ in range(2)]
        await asyncio.to_thread(f.adapter.interrupt_turn, f.turn, operation_id=OperationId("ohf-op:fixture-stop"))
        first, second = await asyncio.gather(*collections)
        assert first == second
        assert sum(row.kind == "native_terminal" for row in f.adapter.events) == 1
        candidate = await asyncio.to_thread(f.adapter.collect_candidate_result, f.turn)
        observation = await asyncio.to_thread(f.adapter.observe_native_conversation_result, f.turn)
        assert candidate.artifact_digest == observation.provider_turn_artifact_digest
        assert candidate.complete_job_permitted is False and observation.stop_reason == "cancelled"
        assert observation.native_terminal.observed_last_turn == 2
        still = await asyncio.to_thread(f.adapter.reconcile, f.generation)
        assert still.provider_writer_state is ProviderWriterState.HELD
        with pytest.raises(NativeOperatorError, match="not an orchestration"):
            f.adapter.observe_raw_role_result(f.turn)
        closed = await asyncio.to_thread(f.adapter.graceful_stop, f.generation,
                                         operation_id=OperationId("ohf-op:fixture-close"))
        assert closed.process_liveness is ProcessLiveness.PROVEN_DEAD
        assert closed.provider_writer_state is ProviderWriterState.RELEASED
    asyncio.run(exercise())


def test_resume_uses_exact_handoff_before_native_write(tmp_path, monkeypatch):
    async def exercise():
        f = await fixture(tmp_path, monkeypatch)
        started = await asyncio.to_thread(f.adapter.resume_session,
            operation_id=OperationId("ohf-op:fixture-resume"), requested=f.requested,
            epoch=f.epoch, generation=f.generation,
            provider_session=ProviderSessionHandoff("original-session", f.epoch.worker_id))
        assert started.provider_session_id == "original-session"
        assert f.guards and all(row[2] == "original-session" for row in f.guards)
        with pytest.raises(NativeOperatorError):
            await start(f)
        assert f.adapter.native.open_calls == 1
    asyncio.run(exercise())


@pytest.mark.parametrize("case", ("foreign-turn", "model-mismatch", "revoked"))
def test_unqualified_native_send_has_no_prompt_effect(tmp_path, monkeypatch, case):
    async def exercise():
        f = await fixture(tmp_path, monkeypatch, served_model="different" if case == "model-mismatch" else "fixture")
        await start(f)
        if case == "revoked":
            f.revoked.add("ohf-op:fixture-prompt")
        turn = replace(f.turn, attempt_id="other-attempt") if case == "foreign-turn" else f.turn
        with pytest.raises(NativeOperatorError):
            await begin(f, turn=turn)
        assert f.adapter.native.prompt_calls == 0
    asyncio.run(exercise())


@pytest.mark.parametrize("case", ("group-present", "forced", "close-unobserved", "boot-changed"))
def test_exit_alone_never_releases_native_writer(tmp_path, monkeypatch, case):
    async def exercise():
        f = await fixture(tmp_path, monkeypatch)
        await start(f)
        if case == "group-present":
            monkeypatch.setattr(module, "_process_group_exists", lambda _pgid: True)
        if case == "boot-changed":
            f.adapter.native.resource.inspector.boot_session_id = lambda: "different-boot"
        if case == "close-unobserved":
            f.adapter.native.resource.process.returncode = 0
            observed = await asyncio.to_thread(f.adapter.reconcile, f.generation)
        elif case == "forced":
            observed = await asyncio.to_thread(f.adapter.cancel, f.generation,
                operation_id=OperationId("ohf-op:fixture-cancel"), reason="fixture forced closure")
        else:
            observed = await asyncio.to_thread(f.adapter.graceful_stop, f.generation,
                operation_id=OperationId("ohf-op:fixture-close"))
        assert observed.provider_writer_state is ProviderWriterState.UNKNOWN
    asyncio.run(exercise())


def test_original_pending_call_survives_wait_timeout(tmp_path, monkeypatch):
    async def exercise():
        f = await fixture(tmp_path, monkeypatch)
        release, entered = asyncio.Event(), asyncio.Event()
        effects = []
        async def operation():
            entered.set()
            await release.wait()
            effects.append("original")
            return "settled"
        with pytest.raises(NativeEffectUnknown):
            await asyncio.to_thread(f.adapter._call, operation(), timeout=0.01)
        await entered.wait()
        assert len(f.adapter.pending_calls) == 1
        original = next(iter(f.adapter.pending_calls))
        assert not original.cancelled()
        release.set()
        assert await asyncio.wrap_future(original) == "settled"
        assert effects == ["original"]
    asyncio.run(exercise())


def test_sdk_queued_prompt_rechecks_authority_at_actual_write():
    async def exercise():
        from acp.task import MessageSender, TaskSupervisor
        first_written, release = asyncio.Event(), asyncio.Event()
        allowed, writes = [True], []
        def require():
            if not allowed[0]:
                raise NativeProtocolError("revoked at physical write")
        class Writer:
            def write(self, data):
                writes.append(data)
                first_written.set()
            async def drain(self):
                await release.wait()
        supervisor = TaskSupervisor(source="native-guard-fixture")
        sender = MessageSender(NativeWriteGuard(Writer(), require), supervisor)
        first = asyncio.create_task(sender.send({"method": "initialize"}))
        await first_written.wait()
        prompt = asyncio.create_task(sender.send({"method": "session/prompt", "params": {"prompt": "private"}}))
        await asyncio.sleep(0)
        assert sender._queue.qsize() == 1
        allowed[0] = False
        release.set()
        await first
        with pytest.raises(NativeProtocolError, match="revoked"):
            await prompt
        assert len(writes) == 1 and b"session/prompt" not in writes[0]
        await supervisor.shutdown()
    asyncio.run(exercise())


def test_async_write_guard_never_grants_a_physical_write():
    writes = []
    async def incorrect_guard():
        pass
    guard = NativeWriteGuard(SimpleNamespace(write=writes.append), incorrect_guard)
    with pytest.raises(NativeProtocolError, match="SYNCHRONOUS"):
        guard.write(b"unadmitted")
    assert writes == []


def test_generation_cursor_never_returns_another_turns_events(tmp_path, monkeypatch):
    async def exercise():
        f = await fixture(tmp_path, monkeypatch)
        await start(f)
        await begin(f)
        f.adapter.native.done.set()
        first, first_cursor = await asyncio.to_thread(f.adapter.read_events, cursor(f))
        second_turn = replace(f.turn, turn_id="turn-second")
        await begin(f, turn=second_turn)
        f.adapter.native.done.set()
        second, second_cursor = await asyncio.to_thread(f.adapter.read_events, cursor(f, second_turn))
        assert first and second and all(row.turn_id == f.turn.turn_id for row in first)
        assert all(row.turn_id == second_turn.turn_id for row in second)
        assert second_cursor.local_sequence > first_cursor.local_sequence
        replay, _ = await asyncio.to_thread(f.adapter.read_events, cursor(f))
        assert replay == first
        with pytest.raises(NativeOperatorError, match="closed turn"):
            await asyncio.to_thread(f.adapter.read_events, cursor(f, sequence=second_cursor.local_sequence))
    asyncio.run(exercise())


@pytest.mark.parametrize("hook", ("verify_source", "require_current_effect"))
def test_async_authority_hook_cannot_start_a_native_effect(tmp_path, monkeypatch, hook):
    async def exercise():
        f = await fixture(tmp_path, monkeypatch)
        effects = []
        async def incorrect(*_args):
            effects.append("must never execute")
        f.adapter.binding = replace(f.adapter.binding, **{hook: incorrect})
        with pytest.raises(NativeOperatorError, match="synchronous"):
            await start(f)
        assert f.adapter.native.open_calls == 0 and effects == []
    asyncio.run(exercise())


def test_close_never_replaces_revoked_prompt_guard_with_cleanup_permission(tmp_path, monkeypatch):
    async def exercise():
        f = await fixture(tmp_path, monkeypatch)
        await start(f)
        await begin(f)
        f.revoked.add("ohf-op:fixture-prompt")
        f.adapter.close_operation = OperationId("ohf-op:fixture-close")
        with pytest.raises(NativeOperatorError, match="revoked"):
            f.adapter._before_write()
        assert f.adapter.current.operation == OperationId("ohf-op:fixture-prompt")
    asyncio.run(exercise())


def test_original_native_start_accepts_async_observation_without_another_owner(tmp_path, monkeypatch):
    async def exercise():
        f = await fixture(tmp_path, monkeypatch)
        calls = []
        class Observation:
            def __await__(self):
                async def resolve():
                    await asyncio.sleep(0)
                    return f.observed
                return resolve().__await__()
        def observe(native):
            calls.append(native)
            return Observation()
        f.adapter.binding = replace(f.adapter.binding, observe_attestation=observe)
        started = await start(f)
        assert started.provider_session_id == f.adapter.native.provider_session_id
        assert calls == [f.adapter.native] and f.adapter.native.open_calls == 1
        assert f.adapter.attestation == f.observed
        await begin(f)
        assert calls == [f.adapter.native, f.adapter.native] and f.adapter.native.prompt_calls == 1
    asyncio.run(exercise())


def test_failed_async_start_observation_keeps_original_process_uncertain(tmp_path, monkeypatch):
    async def exercise():
        f = await fixture(tmp_path, monkeypatch)
        async def unavailable(_native):
            await asyncio.sleep(0)
            raise ValueError("fixture observation unavailable")
        f.adapter.binding = replace(f.adapter.binding, observe_attestation=unavailable)
        with pytest.raises(NativeOperatorError) as failure:
            await start(f)
        assert failure.value.effect_unknown is True
        assert failure.value.failure_class is module.AdapterFailureClass.CAPABILITY_ATTESTATION_FAILURE
        original = f.adapter.native
        assert original.open_calls == 1 and original.provider_session_id == "native-fixture-session"
        assert f.adapter.attestation is None
        with pytest.raises(NativeOperatorError):
            await start(f)
        assert f.adapter.native is original and original.open_calls == 1
    asyncio.run(exercise())


def test_async_observation_inventory_drift_never_dispatches_or_reseals(tmp_path, monkeypatch):
    async def exercise():
        f = await fixture(tmp_path, monkeypatch); await start(f)
        sealed = f.adapter.attestation
        async def changed(_native):
            await asyncio.sleep(0)
            return replace(f.observed, effective_plugins_or_apps=("unexpected-plugin",))
        f.adapter.binding = replace(f.adapter.binding, observe_attestation=changed)
        with pytest.raises(NativeOperatorError, match="configuration changed"):
            await begin(f)
        assert f.adapter.attestation is sealed and f.adapter.native.prompt_calls == 0
        assert f.adapter.current is None and f.adapter.turns == {}
    asyncio.run(exercise())


def test_overlapping_async_begin_observations_admit_at_most_one_original_prompt(tmp_path, monkeypatch):
    async def exercise():
        f = await fixture(tmp_path, monkeypatch); await start(f)
        entered, release = asyncio.Event(), asyncio.Event(); observations = []
        async def observe(native):
            observations.append(native)
            if len(observations) == 2: entered.set()
            await release.wait()
            return f.observed
        f.adapter.binding = replace(f.adapter.binding, observe_attestation=observe)
        first = asyncio.create_task(begin(f))
        other = replace(f.turn, turn_id="other-turn")
        second = asyncio.create_task(begin(f, turn=other))
        await entered.wait(); release.set()
        results = await asyncio.gather(first, second, return_exceptions=True)
        assert sum(isinstance(value, NativeOperatorError) for value in results) == 1
        assert sum(isinstance(value, module.TurnStartObservation) for value in results) == 1
        assert f.adapter.native.prompt_calls == 1 and len(f.adapter.turns) == 1
    asyncio.run(exercise())


@pytest.mark.parametrize("change", ["close", "binding", "generation", "sealed-attestation"])
def test_begin_observation_cannot_outlive_original_admission(tmp_path, monkeypatch, change):
    async def exercise():
        f = await fixture(tmp_path, monkeypatch); await start(f)
        entered, release = asyncio.Event(), asyncio.Event()
        async def observe(_native):
            entered.set(); await release.wait()
            return f.observed
        f.adapter.binding = replace(f.adapter.binding, observe_attestation=observe)
        task = asyncio.create_task(begin(f)); await entered.wait()
        if change == "close":
            await asyncio.to_thread(f.adapter.graceful_stop, f.generation,
                                    operation_id=OperationId("ohf-op:close-during-observation"))
        elif change == "binding":
            f.adapter.binding = replace(f.adapter.binding, verify_source=lambda: None)
        elif change == "generation":
            f.adapter.generation = replace(f.generation, process_generation_id="other-generation")
        else:
            f.adapter.attestation = replace(f.observed)
        release.set()
        with pytest.raises(NativeOperatorError):
            await task
        assert f.adapter.native.prompt_calls == 0 and f.adapter.current is None
    asyncio.run(exercise())
