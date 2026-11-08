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
