"""Actual native FreshConversation owner/Runtime; physical and installed policy seams are inert.

This fixture uses the actual enabled-profile compiler and installed binding owner.
Physical process/provider and installed artifact observations remain inert.
Nominal original input, authenticated resource projections, source/project
checks, creator, dispatch, OHF transactions and final-write guards stay real.
It does not qualify production admission or an installed/provider journey.
"""
import asyncio
import dataclasses
import hashlib
import json
import os
from types import SimpleNamespace

import pytest

from common import fresh_conversation_contract as wire
from control_plane.executive_agent_capabilities import ExecutionCapabilityRegistry
from control_plane.executive_operator_supervisor import ExecutiveOperatorSupervisor
from control_plane.operator_harness_contract import WorkspaceIdentity
from control_plane.operator_harness_wire import to_wire
from control_plane.remote_operator_harness_adapter import RemoteOperatorHarnessAdapter
from tests.test_fresh_conversation import case, cleanup
from tests.test_executive_operator_supervisor import _ActiveAdapter
from test_dsh_native_runtime_result import _NativeTurnAdapter
from test_dsh_native_runtime_binding import CANDIDATE, PROFILE


def native_case(tmp_path, monkeypatch, principal=None):
    from tests.test_dsh_native_installed_binding import native_binding_case
    service, runtime, owner, principal, request, adapters = native_binding_case(tmp_path, monkeypatch, principal)

    class InertNative(_NativeTurnAdapter, _ActiveAdapter, RemoteOperatorHarnessAdapter):
        def __init__(self, loader, f):
            _ActiveAdapter.__init__(self, runtime, loader, cancel_during_collect=False)
            _NativeTurnAdapter.__init__(self, f)
            self._fresh_effect_guard = self._foreground_attempt_id = None
            self.start_calls = self.interrupt_calls = 0
            self._process_by_generation = {}
            self._closed_generations = set()
        def start_session(self, **kwargs):
            if self._fresh_effect_guard is not None:
                self._fresh_effect_guard()
            self.f.generation, self.f.epoch = kwargs["generation"], kwargs["epoch"]
            self.f.session_id = self.provider_session_id
            self.start_calls += 1
            self._process_by_generation[kwargs["generation"].process_generation_id] = self.process
            return _ActiveAdapter.start_session(self, **kwargs)
        def resume_session(self, *, operation_id, epoch, generation, provider_session, requested):
            from control_plane.operator_harness_contract import ProcessIdentityObservation, SessionStartObservation
            assert epoch == self.f.epoch and generation.generation_number == 2
            assert generation.session_epoch_id == epoch.session_epoch_id
            assert generation.worker_id == epoch.worker_id == requested.worker_id
            assert requested == self.profile == self.f.requested
            assert provider_session.provider_session_id == self.provider_session_id == self.f.session_id
            assert provider_session.worker_id == epoch.worker_id
            payload = dict(operation_id=to_wire(operation_id), requested=to_wire(requested),
                epoch=to_wire(epoch), generation=to_wire(generation), provider_session=to_wire(provider_session))
            options = self._fresh_write_options("ohf-resume", payload)
            assert callable(options.get("before_write"))
            hook = getattr(service, "_fixture_before_native_resume_write", None)
            if hook is not None:
                hook(payload)
            options["before_write"]("ohf-resume", payload)
            self.resume_calls += 1
            self.f.generation, self.f.epoch = generation, epoch
            self.process = ProcessIdentityObservation(3102, 3102, "start-3102", "boot-test")
            self._process_by_generation[generation.process_generation_id] = self.process
            return SessionStartObservation(provider_session.provider_session_id, self.process)
        def observed_attestation(self, generation):
            return dataclasses.replace(_ActiveAdapter.observed_attestation(self, generation),
                effective_plugins_or_apps=("mastermind-company",))
        def begin_turn(self, **kwargs):
            prompt = self.turn_input_loader(kwargs["turn"])
            self.prompts.append(prompt)
            payload = {key: to_wire(kwargs[key]) for key in ("operation_id", "turn", "generation", "launch")}
            payload["prompt"] = prompt
            hook = getattr(service, "_fixture_before_native_turn_write", None)
            if hook:
                hook(payload)
            options = self._fresh_write_options("ohf-begin-turn", payload)
            if options:
                options["before_write"]("ohf-begin-turn", payload)
            return _NativeTurnAdapter.begin_turn(self, **kwargs)
        def read_events(self, cursor, *, timeout_seconds):
            pause = getattr(service, "_fixture_collect_pause", None)
            if pause is not None and not pause.wait(timeout=min(timeout_seconds, 10)):
                raise TimeoutError("inert collector was not released")
            return _NativeTurnAdapter.read_events(self, cursor, timeout_seconds=timeout_seconds)
        def interrupt_turn(self, turn, *, operation_id):
            payload = dict(operation_id=to_wire(operation_id), turn=to_wire(turn))
            options = self._fresh_write_options("ohf-interrupt", payload)
            options["before_write"]("ohf-interrupt", payload)
            self.interrupt_calls += 1
            self.result = dataclasses.replace(self.result, stop_reason="cancelled")
            pause = getattr(service, "_fixture_collect_pause", None)
            if pause is not None:
                pause.set()
        def graceful_stop(self, generation, **kwargs):
            observed = _ActiveAdapter.graceful_stop(self, generation, **kwargs)
            self._closed_generations.add(generation.process_generation_id)
            return dataclasses.replace(observed, observed_process=self._process_by_generation[generation.process_generation_id],
                observed_config_digest=self.observed_attestation(generation).effective_config_digest)
        def cancel(self, generation, **kwargs):
            observed = _ActiveAdapter.cancel(self, generation, **kwargs)
            self._closed_generations.add(generation.process_generation_id)
            return dataclasses.replace(observed, observed_process=self._process_by_generation[generation.process_generation_id],
                observed_config_digest=self.observed_attestation(generation).effective_config_digest)
        def reconcile(self, generation):
            from control_plane.operator_harness_contract import ProcessLiveness, ProviderWriterState
            observed = _ActiveAdapter.reconcile(self, generation)
            closed = generation.process_generation_id in self._closed_generations
            return dataclasses.replace(observed, observed_process=self._process_by_generation[generation.process_generation_id],
                process_liveness=ProcessLiveness.PROVEN_DEAD if closed else ProcessLiveness.ALIVE,
                provider_writer_state=ProviderWriterState.RELEASED if closed else ProviderWriterState.HELD,
                observed_config_digest=self.observed_attestation(generation).effective_config_digest)
        def observe_raw_role_result(self, _turn):
            pytest.fail("native conversation entered the planner result codec")

    def factory(attempt, requested, loader, *, recovery):
        assert not recovery and requested.provider == "acp"
        f = SimpleNamespace(runtime=runtime, requested=requested)
        adapter = InertNative(loader, f)
        adapters.append(adapter)
        return adapter
    service.operator_supervisor = ExecutiveOperatorSupervisor(runtime, claimed_adapter_factory=factory,
        prompt_source=SimpleNamespace(_prompt=lambda *a, **k: pytest.fail("native input became planner prompt")))
    owner._fixture_native_errors = []
    original_start = service.operator_supervisor.start_retained_native_job
    async def traced_start(*args, **kwargs):
        try:
            return await original_start(*args, **kwargs)
        except BaseException:
            import traceback
            owner._fixture_native_errors.append(traceback.format_exc(limit=20))
            raise
    monkeypatch.setattr(service.operator_supervisor, "start_retained_native_job", traced_start)
    original_create = owner.create
    async def traced_create(*args, **kwargs):
        try:
            return await original_create(*args, **kwargs)
        except Exception as exc:
            import traceback
            owner._fixture_native_errors.append(traceback.format_exc(limit=10))
            cause = exc.__context__
            for _ in range(5):
                if cause is None:
                    break
                owner._fixture_native_errors.append("Original suppressed cause:\n" +
                    "".join(traceback.format_exception(cause, limit=15, chain=False)))
                cause = cause.__cause__ or cause.__context__
            raise
    monkeypatch.setattr(owner, "create", traced_create)
    def trace_read(method):
        async def traced(*args, **kwargs):
            try:
                return await method(*args, **kwargs)
            except BaseException:
                import traceback
                owner._fixture_native_errors.append(traceback.format_exc(limit=12))
                raise
        return traced
    for name in ("read", "status", "preview"):
        monkeypatch.setattr(owner, name, trace_read(getattr(owner, name)))
    from control_plane import fresh_conversation_turn as turns
    monkeypatch.setattr(turns, "execute_attended_turn", trace_read(turns.execute_attended_turn))
    original_validate = wire.validate_native_response
    def traced_validate(*args, **kwargs):
        try:
            return original_validate(*args, **kwargs)
        except Exception:
            import traceback
            owner._fixture_native_errors.append(traceback.format_exc(limit=12))
            raise
    monkeypatch.setattr(wire, "validate_native_response", traced_validate)
    return service, runtime, owner, principal, request, adapters


async def frame(owner, principal, request, operation, *, reader=None):
    raw = dataclasses.asdict(principal)
    raw["scopes"] = list(raw["scopes"])
    value = dict(schema=wire.NATIVE_SCHEMA, operation=operation, principal=raw,
        workspace_principal=None, arguments=request)
    if operation in wire.NATIVE_DUAL_RESOURCE:
        workspace = dataclasses.asdict(owner._fixture_workspace_principal)
        workspace["scopes"] = list(workspace["scopes"])
        value["workspace_principal"] = workspace
    if reader is None and operation in wire.NATIVE_MODIFYING:
        reader = asyncio.StreamReader()
    return await owner.handle_frame(value, host_current=lambda: None, reader=reader)


async def opened(owner, principal, request):
    preview = await frame(owner, principal, request, "preview")
    assert preview["ok"], preview
    created = await frame(owner, principal, {**request, "preview_digest": preview["data"]["preview"]["digest"]}, "create")
    assert created["ok"], (created, owner._fixture_native_errors, owner._service._dispatch_errors)
    return created["data"]


def test_native_original_create_consume_send_and_receipt_read_do_not_replay(tmp_path, monkeypatch):
    async def run():
        service, runtime, owner, principal, request, adapters = native_case(tmp_path, monkeypatch)
        try:
            created = await opened(owner, principal, request)
            assert created["state"] == "CREATED"
            selected = {k: request[k] for k in ("work_ref", "operation_key")}
            read = await frame(owner, principal, selected, "read")
            assert read["ok"], (read, owner._fixture_native_errors)
            initial = read["data"]
            dispatch = service._native_operator_dispatch
            consumed = await frame(owner, principal, {**selected, "initial_digest": initial["result"]["digest"]}, "consume")
            assert consumed["ok"] and consumed["data"]["can_send"], consumed
            send = {**selected, "initial_digest": initial["result"]["digest"],
                    "turn_key": "native-second", "message": "  原样继续\nNo wrapper or rewrite.  "}
            preview = await frame(owner, principal, send, "turn_preview")
            assert preview["ok"], preview
            send["preview_digest"] = preview["data"]["preview_digest"]
            answer = await frame(owner, principal, send, "turn")
            assert answer["ok"] and answer["data"]["state"] == "RECORDED", (
                answer, owner._fixture_native_errors, service._dispatch_errors, adapters[0].calls)
            before = runtime.events.list_events()
            recovered = await frame(owner, principal, {**selected, "turn_key": send["turn_key"]}, "turn_read")
            duplicate = await frame(owner, principal, send, "turn")
            assert recovered["data"]["result"] == duplicate["data"]["result"] == answer["data"]["result"]
            assert recovered["data"]["effect"] == "NONE"
            assert runtime.events.list_events() == before
            assert service._native_operator_dispatch is dispatch
            assert len(adapters) == adapters[0].start_calls == 1
            assert adapters[0].calls == 2 and adapters[0].prompts == [request["message"], send["message"]]
            assert len(runtime.jobs.list_jobs()) == 2 and len(runtime.attempts.list_attempts()) == 1
            assert not any(e.event_type == "ORCHESTRATION_ROLE_RESULT_SEALED" for e in before)
        finally:
            await cleanup(service)
    asyncio.run(run())


def test_native_stop_can_interrupt_original_initial_turn_without_a_first_result(tmp_path, monkeypatch):
    import threading
    async def run():
        service, runtime, owner, principal, request, adapters = native_case(tmp_path, monkeypatch)
        pause = service._fixture_collect_pause = threading.Event()
        task = None
        try:
            preview = await frame(owner, principal, request, "preview")
            assert preview["ok"], preview
            task = asyncio.create_task(frame(owner, principal,
                {**request, "preview_digest": preview["data"]["preview"]["digest"]}, "create"))
            async def active():
                while True:
                    dispatch = service._native_operator_dispatch
                    if dispatch is not None and dispatch.active_turn is not None:
                        return dispatch
                    if task.done():
                        raise AssertionError((await task, owner._fixture_native_errors, service._dispatch_errors))
                    await asyncio.sleep(0.01)
            dispatch = await asyncio.wait_for(active(), 15)
            selected = {k: request[k] for k in ("work_ref", "operation_key")}
            status = await frame(owner, principal, selected, "status")
            assert status["ok"] and status["data"]["state"] == "ACTIVE", status
            assert status["data"]["result"] is None
            stop = {**selected, "stop_key": "stop-initial", "turn_id": status["data"]["active_turn"]["turn_id"],
                    "binding_digest": status["data"]["session"]["binding_digest"]}
            stopped = await frame(owner, principal, stop, "stop")
            assert stopped["ok"] and stopped["data"]["state"] == "APPLIED", stopped
            created = await asyncio.wait_for(task, 15)
            assert created["ok"], created
            state = await frame(owner, principal, selected, "status")
            assert state["ok"] and state["data"]["state"] == "IDLE", state
            assert state["data"]["can_resume"] and not state["data"]["can_send"]
            before = runtime.events.list_events()
            retry = await frame(owner, principal, stop, "stop")
            read = await frame(owner, principal, {**selected, "stop_key": stop["stop_key"]}, "stop_status")
            assert retry["data"]["receipt"] == read["data"]["receipt"] == stopped["data"]["receipt"]
            assert runtime.events.list_events() == before
            assert adapters[0].interrupt_calls == adapters[0].calls == adapters[0].start_calls == 1
            assert service._native_operator_dispatch is dispatch
        finally:
            pause.set()
            if task is not None and not task.done():
                await asyncio.gather(task, return_exceptions=True)
            await cleanup(service)
    asyncio.run(run())



async def ready_send(owner, principal, request, *, turn_key="native-second"):
    await opened(owner, principal, request)
    selected = {key: request[key] for key in ("work_ref", "operation_key")}
    first = await frame(owner, principal, selected, "read")
    assert first["ok"], first
    initial_digest = first["data"]["result"]["digest"]
    consumed = await frame(owner, principal, {**selected, "initial_digest": initial_digest}, "consume")
    assert consumed["ok"] and consumed["data"]["can_send"], consumed
    send = {**selected, "initial_digest": initial_digest, "turn_key": turn_key,
            "message": "  精确原文\nKeep my whitespace.  "}
    preview = await frame(owner, principal, send, "turn_preview")
    assert preview["ok"], preview
    return selected, {**send, "preview_digest": preview["data"]["preview_digest"]}


async def active_dispatch(service, task):
    while True:
        dispatch = service._native_operator_dispatch
        if dispatch is not None and dispatch.active_turn is not None:
            return dispatch
        if task.done():
            raise AssertionError(await task)
        await asyncio.sleep(0.01)


@pytest.mark.parametrize("failure", ["closed_reader", "lost_reply"])
def test_native_sealed_original_answer_survives_delivery_loss_without_resend(tmp_path, monkeypatch, failure):
    import threading
    from control_plane import fresh_conversation_turn as turns
    async def run():
        service, runtime, owner, principal, request, adapters = native_case(tmp_path, monkeypatch)
        pause, task = threading.Event(), None
        try:
            selected, send = await ready_send(owner, principal, request)
            if failure == "lost_reply":
                original_append = turns._append
                def append(runtime, connection, **kwargs):
                    if kwargs["kind"] == turns._REPLY:
                        raise OSError("inert lost application reply after original native seal")
                    return original_append(runtime, connection, **kwargs)
                monkeypatch.setattr(turns, "_append", append)
            service._fixture_collect_pause = pause
            reader = asyncio.StreamReader()
            task = asyncio.create_task(frame(owner, principal, send, "turn", reader=reader))
            dispatch = await asyncio.wait_for(active_dispatch(service, task), 15)
            original_attempt = dispatch.active_turn.session.attempt_id
            original_session = dispatch.active_turn.session.observation.provider_session_id
            if failure == "closed_reader":
                reader.feed_eof()
            pause.set()
            await asyncio.wait_for(task, 15)
            if failure == "lost_reply":
                await asyncio.gather(*list(service._dispatch_tasks.values()), return_exceptions=True)
                assert service._service_state == "QUARANTINED"
            before = runtime.events.list_events()
            recovered = await frame(owner, principal, {**selected, "turn_key": send["turn_key"]}, "turn_read")
            duplicate = await frame(owner, principal, send, "turn")
            assert recovered["ok"] and recovered["data"]["state"] == "RECORDED", (
                recovered, owner._fixture_native_errors, service._dispatch_errors)
            if failure == "lost_reply":
                assert not duplicate["ok"]  # Quarantine denies new writes; passive original READ still works.
            else:
                assert duplicate["data"]["result"] == recovered["data"]["result"]
            assert recovered["data"]["effect"] == "NONE"
            assert runtime.events.list_events() == before
            results = runtime.operator_harness.native_conversation_results(attempt_id=original_attempt)
            assert len(results) == adapters[0].calls == 2
            latest = runtime.operator_harness.native_conversation_result(attempt_id=original_attempt, reference=results[-1])
            assert latest["observation"]["provider_session_id"] == original_session
            assert adapters[0].prompts == [request["message"], send["message"]]
            assert len(adapters) == adapters[0].start_calls == 1
        finally:
            pause.set()
            if task is not None and not task.done():
                await asyncio.gather(task, return_exceptions=True)
            await cleanup(service)
    asyncio.run(run())


@pytest.mark.parametrize("failure", ["closed_reader", "changed_input"])
def test_native_final_write_loss_preserves_uncertainty_and_never_replays(tmp_path, monkeypatch, failure):
    async def run():
        service, runtime, owner, principal, request, adapters = native_case(tmp_path, monkeypatch)
        try:
            selected, send = await ready_send(owner, principal, request)
            reader = asyncio.StreamReader()
            def before_write(payload):
                if failure == "closed_reader":
                    reader.feed_eof()
                else:
                    payload["prompt"] += " changed at the last write boundary"
            service._fixture_before_native_turn_write = before_write
            outcome = await frame(owner, principal, send, "turn", reader=reader)
            if failure == "closed_reader":
                assert not outcome["ok"] and outcome["error"]["code"] == "effect_unknown", outcome
            else:
                assert outcome["ok"] and outcome["data"]["state"] == "RECONCILIATION_REQUIRED", outcome
            assert adapters[0].calls == 1
            await asyncio.gather(*list(service._dispatch_tasks.values()), return_exceptions=True)
            assert service._service_state == "QUARANTINED"
            before = runtime.events.list_events()
            duplicate = await frame(owner, principal, send, "turn")
            original = await frame(owner, principal, {**selected, "turn_key": send["turn_key"]}, "turn_read")
            assert not duplicate["ok"]  # No write authority survives the failed original dispatch.
            assert original["data"]["state"] == "RECONCILIATION_REQUIRED"
            assert original["data"]["result"] is None and original["data"]["effect"] == "NONE"
            assert runtime.events.list_events() == before and adapters[0].calls == 1
            alternate = {key: value for key, value in send.items() if key != "preview_digest"}
            alternate["turn_key"] = "replacement-must-not-send"
            refused = await frame(owner, principal, alternate, "turn_preview")
            assert not refused["ok"] and adapters[0].calls == 1
            assert len(adapters) == adapters[0].start_calls == 1
        finally:
            await cleanup(service)
    asyncio.run(run())



def test_native_stop_resume_send_and_terminal_stop_keep_one_session_and_two_generations(tmp_path, monkeypatch):
    import threading
    async def run():
        service, runtime, owner, principal, request, adapters = native_case(tmp_path, monkeypatch)
        pause, task = threading.Event(), None
        try:
            selected, send = await ready_send(owner, principal, request)
            original_dispatch = service._native_operator_dispatch
            original_session = original_dispatch.retained.session
            initial = original_dispatch.retained.native_result
            initial_value = runtime.operator_harness.native_conversation_result(
                attempt_id=original_session.attempt_id, reference=initial)
            service._fixture_collect_pause = pause
            task = asyncio.create_task(frame(owner, principal, send, "turn"))
            dispatch = await asyncio.wait_for(active_dispatch(service, task), 15)
            active = await frame(owner, principal, selected, "status")
            assert active["ok"] and active["data"]["can_stop"], active
            stop = {**selected, "stop_key": "g1-stop",
                    "turn_id": active["data"]["active_turn"]["turn_id"],
                    "binding_digest": active["data"]["session"]["binding_digest"]}
            stopped = await frame(owner, principal, stop, "stop")
            assert stopped["ok"] and stopped["data"]["state"] == "APPLIED", (
                stopped, owner._fixture_native_errors, service._dispatch_errors)
            sent = await asyncio.wait_for(task, 15)
            assert sent["ok"] and sent["data"]["state"] == "RECORDED", sent
            idle = await frame(owner, principal, selected, "status")
            assert idle["ok"] and idle["data"]["state"] == "IDLE" and idle["data"]["can_resume"], idle
            resume = {**selected, "resume_key": "same-session-g2",
                      "expected_result_digest": idle["data"]["head_result"]["digest"]}
            preview = await frame(owner, principal, resume, "resume_preview")
            assert preview["ok"] and preview["data"]["state"] == "RESUME_READY", preview
            resume["preview_digest"] = preview["data"]["preview_digest"]
            resumed = await frame(owner, principal, resume, "resume")
            assert resumed["ok"] and resumed["data"]["state"] == "APPLIED", (
                resumed, owner._fixture_native_errors, service._dispatch_errors)
            assert service._native_operator_dispatch is dispatch is original_dispatch
            second = dispatch.retained.session
            assert second.epoch == original_session.epoch
            assert second.observation.provider_session_id == original_session.observation.provider_session_id
            assert second.generation.generation_number == 2
            assert second.generation.process_generation_id != original_session.generation.process_generation_id
            ready = await frame(owner, principal, selected, "status")
            assert ready["ok"] and ready["data"]["can_send"] and not ready["data"]["can_resume"], ready
            before = runtime.events.list_events()
            duplicate = await frame(owner, principal, resume, "resume")
            recovered = await frame(owner, principal, {**selected, "resume_key": resume["resume_key"]}, "resume_status")
            assert duplicate["data"]["receipt"] == recovered["data"]["receipt"] == resumed["data"]["receipt"]
            assert runtime.events.list_events() == before
            assert adapters[0].resume_calls == adapters[0].start_calls == len(adapters) == 1
            assert runtime.operator_harness.native_conversation_result(
                attempt_id=original_session.attempt_id, reference=initial) == initial_value
            g2send = {**selected, "initial_digest": initial.seal_digest,
                      "turn_key": "g2-original-turn", "message": "G2 uses the original Session."}
            preview = await frame(owner, principal, g2send, "turn_preview")
            assert preview["ok"], preview
            g2send["preview_digest"] = preview["data"]["preview_digest"]
            pause.clear()
            task = asyncio.create_task(frame(owner, principal, g2send, "turn"))
            await asyncio.wait_for(active_dispatch(service, task), 15)
            active = await frame(owner, principal, selected, "status")
            assert active["ok"] and active["data"]["can_stop"], active
            g2stop = {**selected, "stop_key": "g2-terminal-stop",
                      "turn_id": active["data"]["active_turn"]["turn_id"],
                      "binding_digest": active["data"]["session"]["binding_digest"]}
            stopped = await frame(owner, principal, g2stop, "stop")
            assert stopped["ok"] and stopped["data"]["state"] == "APPLIED", stopped
            sent = await asyncio.wait_for(task, 15)
            assert sent["ok"] and sent["data"]["state"] == "RECORDED", (
                sent, owner._fixture_native_errors, service._dispatch_errors)
            await asyncio.gather(*list(service._dispatch_tasks.values()), return_exceptions=True)
            settled = await frame(owner, principal, selected, "status")
            assert settled["ok"] and settled["data"]["state"] == "SETTLED", (
                settled, owner._fixture_native_errors, service._dispatch_errors)
            assert not any(settled["data"][key] for key in ("can_send", "can_stop", "can_resume"))
            refs = runtime.operator_harness.native_conversation_results(attempt_id=original_session.attempt_id)
            assert len(refs) == adapters[0].calls == 3
            last = runtime.operator_harness.native_conversation_result(attempt_id=original_session.attempt_id, reference=refs[-1])
            assert last["turn"]["process_generation_id"] == second.generation.process_generation_id
            assert last["predecessor_result"] == refs[-2].to_wire()
            assert adapters[0].interrupt_calls == 2 and adapters[0].resume_calls == 1
            assert adapters[0].prompts == [request["message"], send["message"], g2send["message"]]
            assert len(runtime.attempts.list_attempts()) == 1
            with runtime.store.read() as connection:
                assert connection.execute("SELECT COUNT(*) FROM process_generations").fetchone()[0] == 2
            from tests.test_dsh_native_retained_read import historical_view
            history = historical_view(service, runtime, adapters[0], tmp_path)
            history_before = runtime.events.list_events()
            for original_reference in (initial, refs[-1]):
                recovered_body = await history.returns.deepseek_history(principal, dict(selection=dict(work_ref=request["work_ref"],
                    root_job_id=original_dispatch.retained.job.root_job_id),
                    read=dict(kind="result", native_ref=original_reference.to_wire(),
                              offset_bytes=0, expected_sha256=None)))
                assert recovered_body["native"]["state"] == "NO_ANSWER"
                assert recovered_body["native_session_id"] == original_session.observation.provider_session_id
            assert runtime.events.list_events() == history_before
            assert history.writes == ["ohf-native-read-binding", "ohf-native-read"] * 2
            assert history.payloads[0]["generation"]["process_generation_id"] == original_session.generation.process_generation_id
            assert history.payloads[2]["generation"]["process_generation_id"] == second.generation.process_generation_id
            refused = await frame(owner, principal, {**selected, "resume_key": "no-g3",
                "expected_result_digest": refs[-1].seal_digest}, "resume_preview")
            assert not refused["ok"] and adapters[0].resume_calls == 1
        finally:
            pause.set()
            if task is not None and not task.done():
                await asyncio.gather(task, return_exceptions=True)
            await cleanup(service)
    asyncio.run(run())
