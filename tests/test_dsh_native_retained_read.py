"""Original native Runtime root/retained dispatch joins; only transport bytes are inert."""
from __future__ import annotations
import asyncio
import dataclasses
from pathlib import Path
from types import SimpleNamespace

import pytest

from common.session_bridge_private_contract import BridgeError
from control_plane.native_conversation_binding import NativeConversationHostComposition
from integrations.session_bridge.retained_native_read import RetainedNativeReadResolver
from integrations.deepseek_harness.native_read_port import RESPONSE_SCHEMA
from integrations.session_bridge.runtime_owner import RuntimeFabricTargetProjector, RuntimeCodexTargetProjector
from integrations.session_bridge.runtime_return import RuntimeSessionReturn
from tests.test_dsh_native_fresh_conversation import native_case, opened
from tests.test_fresh_conversation import cleanup


async def composition(tmp_path, monkeypatch):
    service, runtime, owner, principal, request, adapters = native_case(tmp_path, monkeypatch)
    created = await opened(owner, principal, request)
    dispatch, adapter = service._native_operator_dispatch, adapters[0]
    binding = service._fixture_native_binding
    host = NativeConversationHostComposition(binding.selection, binding.current, composition_sha256="a"*64)
    calls, writes = [], []
    hooks = {}
    async def invoke(operation, payload, *, timeout_seconds, before_write):
        assert timeout_seconds == 6.0 and callable(before_write)
        calls.append(operation)
        if operation in hooks: hooks[operation]()
        before_write(operation, payload)
        writes.append(operation)
        if operation == "ohf-native-read-binding":
            return {"native_read":dict(schema="mastermind.dsh.native_read_binding.v1",
                native_session_id=adapter.provider_session_id, native_package_sha256="3"*64,
                donor_sha="687f282e8625c6b8d11ff58211a90524be2e4317")}
        assert operation == "ohf-native-read"
        frame = payload["request"]
        return {"native_read":dict(schema=RESPONSE_SCHEMA, request_id=frame["request_id"],
            association_sha256=frame["association_sha256"],status="READ",
            data={"projections":None,"page":None})}
    adapter.client = SimpleNamespace(request=invoke)
    resolver = RetainedNativeReadResolver(service, runtime, host, require_current=binding.current)
    fabric = RuntimeFabricTargetProjector(runtime)
    returns = RuntimeSessionReturn(runtime, fabric=fabric, codex=RuntimeCodexTargetProjector(fabric),
        socket_path=tmp_path/"unused-dialogue.sock", deepseek=resolver)
    args = dict(selection={"work_ref":request["work_ref"],"root_job_id":created["locator"]["root_job_id"]},
                read={"kind":"snapshot"})
    return SimpleNamespace(service=service,runtime=runtime,owner=owner,principal=principal,request=request,
        adapter=adapter,dispatch=dispatch,returns=returns,args=args,host=host,calls=calls,writes=writes,hooks=hooks)


def test_original_native_creation_drives_read_without_another_owner_or_event(tmp_path, monkeypatch):
    async def run():
        h = await composition(tmp_path, monkeypatch)
        try:
            before = h.runtime.events.list_events()
            result = await h.returns.deepseek_history(h.principal,h.args)
            assert result["native"] == {"projections":None,"page":None} and result["observational_only"] is True
            assert result["can_send"] is False and result["parent_consumed"] is False
            assert result["native_session_id"] == h.adapter.provider_session_id
            assert h.calls == h.writes == ["ohf-native-read-binding","ohf-native-read"]
            assert h.runtime.events.list_events() == before
            assert h.service._native_operator_dispatch is h.dispatch and h.dispatch.retained.adapter is h.adapter
            assert h.adapter.start_calls == h.adapter.calls == 1
            assert len(h.runtime.jobs.list_jobs()) == 2 and len(h.runtime.attempts.list_attempts()) == 1
        finally: await cleanup(h.service)
    asyncio.run(run())


def test_foreign_principal_never_enters_original_worker_read(tmp_path, monkeypatch):
    async def run():
        h = await composition(tmp_path, monkeypatch)
        try:
            foreign = dataclasses.replace(h.principal,subject_digest="f"*64)
            with pytest.raises(BridgeError): await h.returns.deepseek_history(foreign,h.args)
            assert h.calls == h.writes == []
        finally: await cleanup(h.service)
    asyncio.run(run())


@pytest.mark.parametrize("drift",["supervisor-runtime","supervisor-type","phase","continuation",
    "fresh-turn","fresh-control","fresh-stop","host-source","adapter-client"])
def test_reader_requires_original_ready_runtime_and_dispatch_at_every_boundary(tmp_path,monkeypatch,drift):
    async def run():
        h = await composition(tmp_path,monkeypatch)
        supervisor = h.service.operator_supervisor
        original_continuation = h.dispatch.continuation
        original_client = h.adapter.client
        try:
            if drift == "supervisor-runtime": supervisor.runtime = object()
            elif drift == "supervisor-type": h.service.operator_supervisor = SimpleNamespace(runtime=h.runtime)
            elif drift == "phase": h.dispatch.native_phase = "IDLING"
            elif drift == "continuation":
                h.dispatch.continuation = asyncio.get_running_loop().create_future()
                h.dispatch.continuation.set_result(None)
            elif drift == "fresh-turn": h.dispatch._fresh_turn_source = object()
            elif drift == "fresh-control": h.dispatch._fresh_control_source = object()
            elif drift == "fresh-stop": h.dispatch._fresh_interrupt_source = object()
            elif drift == "host-source": h.service._fixture_native_binding.live["current"] = False
            else: h.hooks["ohf-native-read-binding"] = lambda: setattr(h.adapter,"client",object())
            with pytest.raises(BridgeError): await h.returns.deepseek_history(h.principal,h.args)
            assert h.writes == []
        finally:
            supervisor.runtime = h.runtime; h.service.operator_supervisor = supervisor
            h.dispatch.native_phase = "READY"; h.dispatch.continuation = original_continuation
            for field in ("_fresh_turn_source","_fresh_control_source","_fresh_interrupt_source"):
                if hasattr(h.dispatch,field): setattr(h.dispatch,field,None)
            h.service._fixture_native_binding.live["current"] = True
            h.adapter.client = original_client
            await cleanup(h.service)
    asyncio.run(run())


def test_retirement_between_binding_and_content_is_refused_at_original_transport_write(tmp_path,monkeypatch):
    async def run():
        h = await composition(tmp_path,monkeypatch)
        try:
            h.hooks["ohf-native-read"] = lambda: setattr(h.dispatch,"native_phase","IDLING")
            with pytest.raises(BridgeError): await h.returns.deepseek_history(h.principal,h.args)
            assert h.calls == ["ohf-native-read-binding","ohf-native-read"]
            assert h.writes == ["ohf-native-read-binding"]
        finally:
            h.dispatch.native_phase = "READY"
            await cleanup(h.service)
    asyncio.run(run())


def historical_view(service, runtime, adapter, tmp_path):
    """The original Runtime and owner, with only Worker transport bytes inert."""
    from control_plane.operator_harness_wire import to_wire
    calls, writes, payloads, hooks = [], [], [], {}
    fault = {}
    binding = service._fixture_native_binding
    async def invoke(operation, payload, *, timeout_seconds, before_write):
        assert timeout_seconds == 6.0
        calls.append(operation)
        hook = hooks.get(operation)
        if hook is not None:
            result = hook()
            if asyncio.iscoroutine(result): await result
        before_write(operation, payload)
        writes.append(operation); payloads.append(payload)
        if operation == "ohf-native-read-binding":
            value = dict(schema="mastermind.dsh.native_history_binding.v1",
                binding=dict(schema="mastermind.dsh.native_read_binding.v1",
                    native_session_id=adapter.provider_session_id, native_package_sha256="3"*64,
                    donor_sha="687f282e8625c6b8d11ff58211a90524be2e4317"),
                materialization_receipt_sha256="4"*64)
            if fault.get("session"): value["binding"]["native_session_id"] = "foreign"
            if fault.get("digest"): value["materialization_receipt_sha256"] = "invalid"
            if fault.get("extra"): value["extra"] = True
            return {"native_read":value}
        frame = payload["request"]; selected = frame["read"]
        assert selected["kind"] == "result"
        return {"native_read":dict(schema=RESPONSE_SCHEMA, request_id=frame["request_id"],
            association_sha256=frame["association_sha256"], status="READ",
            data=dict(kind="result", state="NO_ANSWER", claim=selected["claim"], terminal=selected["terminal"],
                turn_start_seq=selected["claim"]["throughSeq"], turn_end_seq=selected["terminal"]["throughSeq"],
                user_message_seq=None, assistant_message_seqs=[], content=None))}
    client = SimpleNamespace(request=invoke)
    def factory(**identity):
        attempt = runtime.attempts.get_attempt(identity["attempt_id"])
        assert attempt.worker_id == identity["worker_id"] and attempt.job_id == identity["job_id"]
        epoch, generation = runtime.operator_harness.generation_refs(identity["process_generation_id"])
        assert epoch.session_epoch_id == identity["session_epoch_id"]
        return client
    host = NativeConversationHostComposition(binding.selection, binding.current,
        composition_sha256="a"*64, native_read_client_factory=factory)
    resolver = RetainedNativeReadResolver(service, runtime, host, require_current=binding.current)
    fabric = RuntimeFabricTargetProjector(runtime)
    returns = RuntimeSessionReturn(runtime, fabric=fabric, codex=RuntimeCodexTargetProjector(fabric),
        socket_path=tmp_path/"unused-history.sock", deepseek=resolver)
    return SimpleNamespace(returns=returns, calls=calls, writes=writes, payloads=payloads,
                           hooks=hooks, fault=fault, host=host, client=client)


async def closed_composition(tmp_path, monkeypatch):
    h = await composition(tmp_path, monkeypatch)
    reference = h.dispatch.retained.native_result
    await h.service.operator_supervisor.idle_retained_native_job(h.dispatch.retained)
    h.service.operator_supervisor.native_idle_projection(h.dispatch.retained, expected_result=reference)
    h.dispatch.native_phase = "IDLE"
    view = historical_view(h.service, h.runtime, h.adapter, tmp_path)
    for name in vars(view): setattr(h, name, getattr(view, name))
    h.args["read"] = dict(kind="result", native_ref=reference.to_wire(),
        offset_bytes=0, expected_sha256=None)
    h.reference = reference
    return h


def test_closed_original_result_joins_historical_receipt_without_new_events_or_session(tmp_path, monkeypatch):
    async def run():
        h = await closed_composition(tmp_path, monkeypatch)
        try:
            before = h.runtime.events.list_events()
            result = await h.returns.deepseek_history(h.principal, h.args)
            assert result["native"]["state"] == "NO_ANSWER"
            assert result["native_session_id"] == h.adapter.provider_session_id
            assert h.calls == h.writes == ["ohf-native-read-binding", "ohf-native-read"]
            binding, content = h.payloads
            assert "materialization_receipt_sha256" not in binding["history"]
            assert content["history"] == {**binding["history"], "materialization_receipt_sha256":"4"*64}
            assert content["epoch"] == binding["epoch"] and content["generation"] == binding["generation"]
            assert h.runtime.events.list_events() == before
            assert h.adapter.start_calls == h.adapter.calls == 1 and h.adapter.resume_calls == 0
            assert len(h.runtime.attempts.list_attempts()) == 1
        finally: await cleanup(h.service)
    asyncio.run(run())


@pytest.mark.parametrize("slot", ["active_turn", "pending_turn", "_fresh_turn_source",
                                  "_fresh_control_source", "_fresh_interrupt_source"])
def test_idle_history_refuses_reserved_original_operation_before_transport(tmp_path, monkeypatch, slot):
    async def run():
        h = await closed_composition(tmp_path, monkeypatch)
        previous = getattr(h.dispatch, slot, None)
        try:
            setattr(h.dispatch, slot, object())
            with pytest.raises(BridgeError): await h.returns.deepseek_history(h.principal, h.args)
            assert h.calls == h.writes == []
        finally:
            setattr(h.dispatch, slot, previous)
            await cleanup(h.service)
    asyncio.run(run())


@pytest.mark.parametrize("fault", ["session", "digest", "extra"])
def test_closed_history_pins_actual_binding_before_any_content_request(tmp_path, monkeypatch, fault):
    async def run():
        h = await closed_composition(tmp_path, monkeypatch)
        try:
            h.fault[fault] = True
            with pytest.raises(BridgeError): await h.returns.deepseek_history(h.principal, h.args)
            assert h.calls == h.writes == ["ohf-native-read-binding"]
        finally: await cleanup(h.service)
    asyncio.run(run())


def test_idle_resume_reservation_during_binding_prevents_content_write(tmp_path, monkeypatch):
    async def run():
        h = await closed_composition(tmp_path, monkeypatch)
        entered, release = asyncio.Event(), asyncio.Event()
        async def hold():
            entered.set()
            await release.wait()
        h.hooks["ohf-native-read-binding"] = hold
        pending = asyncio.create_task(h.returns.deepseek_history(h.principal, h.args))
        try:
            await asyncio.wait_for(entered.wait(), 2)
            h.dispatch._fresh_control_source = object()
            release.set()
            with pytest.raises(BridgeError): await pending
            assert h.calls == ["ohf-native-read-binding"] and h.writes == []
        finally:
            release.set(); h.dispatch._fresh_control_source = None
            await asyncio.gather(pending, return_exceptions=True)
            await cleanup(h.service)
    asyncio.run(run())
