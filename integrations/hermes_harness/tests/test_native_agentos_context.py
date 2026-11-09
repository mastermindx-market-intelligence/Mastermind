"""Actual adopted compiler and SDK shape; no installed native enrollment claim."""
from __future__ import annotations

import asyncio
import copy
from dataclasses import replace
import hashlib
import json
import threading

import httpx
import pytest
from mcp import types

from common import coo_agentos_context_contract as wire
from integrations.executive_mcp.schemas import RESULT_SCHEMA
from integrations.hermes_harness import native_executive_consumer as consumer
from integrations.hermes_harness.agentos_memory_provider import (
    AgentOsBinding, AgentOsHostPorts, AgentOsRefusal, create_provider)
from integrations.hermes_harness.native_agentos_context import (
    NativeAgentOsContextRead, decode_context_result)
from integrations.hermes_harness.tests.test_agentos_memory_provider import (
    ManualSpawn, StaticResolver, StaticGuard)
from integrations.hermes_harness.tests.test_native_executive_consumer import publication_document
from integrations.hermes_runtime.errors import RuntimeRefusal
from integrations.mastermind_executive_app.coo_binding import _digest
from tests import test_executive_coo_agentos_context as transport_tests

actual_result = transport_tests.actual_result
rsa_key = transport_tests.rsa_key


def context_document(frame=None, record=None):
    value = publication_document()
    for name in ("command", "job_id", "target_digest", "root_job_id"):
        value.pop(name)
    value.update(schema=consumer.CONTEXT_CONSUMER_SCHEMA, selected_child=None,
        context=dict(provider="agentos", source_mode="ADOPTED_SNAPSHOT",
                     max_context_bytes=131072, freshness_seconds=120),
        tools_schema_digest=consumer.CONTEXT_TOOLS_SCHEMA_DIGEST,
        permission_digest="d" * 64)
    if record is None:
        record = dict(value["principal"])
        record["resource"] = record.pop("resource_ref")
        record["permission_digest"] = value["permission_digest"]
    value["permission_digest"] = record["permission_digest"]
    value["principal"] = {key: item for key, item in record.items() if key != "permission_digest"}
    value["principal"]["resource_ref"] = value["principal"].pop("resource")
    value["principal_binding_digest"] = _digest(record)
    if frame:
        value.update(frame["principal_context"])
        value["capability_profile_digest"] = frame["capability_profile_digest"]
    return value


def sdk_result(value):
    payload = dict(schema=RESULT_SCHEMA, tool=wire.TOOL, ok=True, server_version="1.0.0",
        mode="readonly", generated_at="2026-11-07T00:00:00Z", grounding={}, data=value,
        degraded=[], bounded=[], error=None)
    return types.CallToolResult(content=[types.TextContent(type="text", text=wire.encode(payload).decode())],
                                isError=False)


@pytest.fixture
def decoded_fixture(actual_result):
    frame, value, seen = actual_result
    publication = consumer.publication_from_document(
        context_document(frame, seen["coo"]["binding"]["binding"]))
    return publication, sdk_result(value), seen


def test_v1_stays_closed_and_v2_needs_no_selected_child():
    old = publication_document()
    assert consumer.validate_consumer_publication(old) == old
    assert type(consumer.publication_from_document(old)) is consumer.ExecutiveConsumerPublication
    value = context_document()
    publication = consumer.publication_from_document(value)
    assert type(publication) is consumer.ExecutiveContextConsumerPublication
    assert consumer.selected_child_publication(publication) is None
    child = {name: old[name] for name in ("command", "job_id", "target_digest", "root_job_id")}
    selected = consumer.publication_from_document(dict(value, selected_child=child))
    projected = consumer.selected_child_publication(selected)
    assert projected.command == child["command"] and projected.root_job_id == child["root_job_id"]
    assert projected.principal_binding_digest == publication.principal_binding_digest
    with pytest.raises(RuntimeRefusal):
        consumer.publication_from_document(dict(old, context=value["context"]))


@pytest.mark.parametrize("change", [
    lambda p: p.pop("selected_child"),
    lambda p: p.update(selected_child={}),
    lambda p: p.update(selected_child={"job_id": "JOB1"}),
    lambda p: p.update(command="coo-cycle:ROOT1:dispatch:JOB1:attempt:1"),
    lambda p: p.update(tools_schema_digest="2" * 64),
    lambda p: p.pop("permission_digest"),
    lambda p: p["principal"].update(subject_digest="a" * 64),
    lambda p: p["context"].update(source_mode="LATEST"),
    lambda p: p["context"].update(owner_root="/private/alternate"),
    lambda p: p["context"].update(enabled=True),
    lambda p: p["context"].update(max_context_bytes=True),
    lambda p: p["context"].update(max_context_bytes=131073),
    lambda p: p["context"].update(freshness_seconds=float("inf")),
    lambda p: p["context"].update(freshness_seconds=True),
])
def test_v2_refuses_partial_or_contradictory_enrollment(change):
    value = context_document()
    change(value)
    with pytest.raises(RuntimeRefusal):
        consumer.validate_consumer_publication(value)


def test_actual_compiler_bytes_survive_actual_sdk_and_remote_provider(decoded_fixture):
    publication, result, seen = decoded_fixture
    raw, receipt = decode_context_result(result, publication)
    assert raw == seen["results"][0]["stdout"].encode()
    assert hashlib.sha256(raw).hexdigest() == receipt["bundle_sha256"]
    calls = []
    reader = NativeAgentOsContextRead(publication=publication,
        server=object(), session=object(), loop=object(), currentness=lambda: True)
    class OriginalCaller:
        def call(self, name, arguments):
            calls.append((name, arguments))
            return result
    reader.caller = OriginalCaller()  # Controlled connection; no native-install claim.
    binding = AgentOsBinding("physical-1", "mmsecretary", "mmsecretary", "/role/home",
        publication.work_ref, None, "native-claim-1", max_context_bytes=131072)
    spawn = ManualSpawn()
    provider = create_provider(ports=AgentOsHostPorts(StaticResolver({binding.session_id: binding}), StaticGuard()),
                               remote_reader=reader, spawn=spawn)
    provider.initialize(binding.session_id)
    assert provider.prefetch("different workstream WS:FORGED", session_id=binding.session_id) == ""
    provider.prepare_context()
    spawn.run_all()
    text = provider.prefetch("different workstream WS:FORGED", session_id=binding.session_id)
    assert text.endswith(raw.decode())
    assert calls == [(wire.TOOL, {"work_ref": publication.work_ref})]
    assert provider.readiness()["context_supplied"] is True


def test_sdk_shape_rejects_extras_fallbacks_and_semantic_conflicts(decoded_fixture):
    publication, good, _ = decoded_fixture
    variants = [good.model_dump(), {"content": good.content}, tuple(good.content),
        good.model_copy(update={"isError": True}),
        good.model_copy(update={"structuredContent": {}}),
        good.model_copy(update={"meta": {}}),
        types.CallToolResult(**good.model_dump(), unknown=None),
        good.model_copy(update={"content": good.content * 2}),
        good.model_copy(update={"content": [good.content[0].model_copy(update={"annotations": {}})]}),
        good.model_copy(update={"content": [types.TextContent(type="text", text=good.content[0].text, unknown=None)]}),
    ]
    body = json.loads(good.content[0].text)
    for field, replacement in (("ok", 1), ("mode", "active"), ("grounding", {"authority": True}),
                               ("generated_at", "2026-11-07"), ("server_version", "2.0.0"),
                               ("degraded", ["concealed_error"]), ("extra", None)):
        malformed = dict(body, **{field: replacement})
        variants.append(types.CallToolResult(content=[types.TextContent(type="text", text=json.dumps(malformed))]))
    for text in (good.content[0].text.replace('"ok":true', '"ok":true,"ok":true'),
                 good.content[0].text[:-1] + ',"unknown":1e999}',
                 good.content[0].text + "\ud800"):
        variants.append(types.CallToolResult(content=[types.TextContent(type="text", text=text)]))
    for malformed in variants:
        with pytest.raises(RuntimeRefusal):
            decode_context_result(malformed, publication)
    with pytest.raises(RuntimeRefusal):
        decode_context_result(good, replace(publication, authority_generation_digest="e" * 64))


def test_remote_port_never_borrows_local_source_or_changes_budget():
    class Port:
        def read(self, *_args, **_kwargs):
            raise AssertionError("invalid remote binding must not be read")
    with pytest.raises(AgentOsRefusal):
        create_provider(remote_reader=Port(), reader=lambda *_a, **_k: None)
    for budget in (True, 3999, 4000.0):
        with pytest.raises(AgentOsRefusal):
            create_provider(remote_reader=Port(), budget=budget)
    binding = AgentOsBinding("s", "mmsecretary", "mmsecretary", "/role/home", "WS:1-OWNER",
                            "/invented/fallback", "g")
    provider = create_provider(remote_reader=Port(),
        ports=AgentOsHostPorts(StaticResolver({"s": binding}), StaticGuard()))
    with pytest.raises(AgentOsRefusal):
        provider.initialize("s")
    binding = replace(binding, owner_root=None)
    provider = create_provider(remote_reader=Port(),
        ports=AgentOsHostPorts(StaticResolver({"s": binding}), StaticGuard()))
    provider.initialize("s")  # Canonical workspace selectors can start with a digit.


def test_context_caller_retains_timed_out_original_without_queuing_new_exchanges():
    from integrations.hermes_harness.tests.test_native_executive_consumer import _McpLoop, _Owner
    entered = threading.Event()
    release = asyncio.Event()
    calls = []
    class Session:
        async def call_tool(self, name, arguments):
            calls.append((name, arguments))
            entered.set()
            await release.wait()
            return "original result"
    loop = _McpLoop()
    session = Session()
    server = _Owner(session)
    first = consumer._NativeMcpCaller(server=server, session=session, loop=loop.loop,
                                     timeout=0.02, wait_for_lock=False)
    try:
        with pytest.raises(consumer._ConsumerUncertain, match="timed out"):
            first.call(wire.TOOL, {"work_ref": "WS:ORIGINAL"})
        assert entered.is_set() and len(server._inflight_tasks) == 1
        for _ in range(3):
            later = consumer._NativeMcpCaller(server=server, session=session, loop=loop.loop,
                                             timeout=1, wait_for_lock=False)
            with pytest.raises(consumer._ConsumerUncertain):
                later.call(wire.TOOL, {"work_ref": "WS:ORIGINAL"})
            assert len(server._inflight_tasks) == 1
        assert len(calls) == 1
    finally:
        loop.loop.call_soon_threadsafe(release.set)
        async def settled():
            tasks = list(server._inflight_tasks)
            if tasks:
                await asyncio.gather(*tasks)
        asyncio.run_coroutine_threadsafe(settled(), loop.loop).result(timeout=2)
        loop.close()
    assert server._inflight_tasks == set()


def test_context_caller_refuses_unlocked_original_lock_with_pending_waiter():
    from collections import deque
    from integrations.hermes_harness.tests.test_native_executive_consumer import _McpLoop, _Owner, _Session
    loop = _McpLoop()
    session = _Session()
    server = _Owner(session)
    async def waking_waiter():
        future = loop.loop.create_future()
        future.set_result(True)
        server._rpc_lock._waiters = deque([future])
    asyncio.run_coroutine_threadsafe(waking_waiter(), loop.loop).result(timeout=2)
    try:
        assert not server._rpc_lock.locked()
        caller = consumer._NativeMcpCaller(server=server, session=session, loop=loop.loop,
                                          timeout=1, wait_for_lock=False)
        with pytest.raises(consumer._ConsumerUncertain):
            caller.call(wire.TOOL, {"work_ref": "WS:ORIGINAL"})
        assert session.calls == [] and not server._inflight_tasks
    finally:
        server._rpc_lock._waiters.clear()
        loop.close()


def test_waiter_keeps_one_original_pending_read_and_cannot_resurrect_old_epoch(decoded_fixture):
    publication, result, _ = decoded_fixture
    raw, receipt = decode_context_result(result, publication)
    entered, release = threading.Event(), threading.Event()
    calls = []
    class Port:
        def read(self, binding, *, budget):
            calls.append(binding.generation)
            entered.set()
            assert release.wait(2)
            return raw, receipt
    binding = AgentOsBinding("s", "mmsecretary", "mmsecretary", "/role/home",
                            publication.work_ref, None, "g", 131072)
    resolver = StaticResolver({"s": binding})
    provider = create_provider(remote_reader=Port(),
        ports=AgentOsHostPorts(resolver, StaticGuard()),
        spawn=lambda target, *, name, args: threading.Thread(target=target, args=args, name=name))
    provider.initialize("s")
    provider.prepare_context()
    assert entered.wait(1)
    assert provider.wait_context(0)["state"] == "PENDING"
    assert calls == ["g"] and provider._pending == 1
    provider.on_session_switch("s")
    release.set()
    assert provider.wait_context(1)["state"] == "UNAVAILABLE"
    assert provider.prefetch("status", session_id="s") == "" and calls == ["g"]


def test_signed_mcp_producer_decodes_without_receipt_reconstruction(tmp_path, monkeypatch, rsa_key):
    token, current, settings, backend, seen = transport_tests.signed_components(tmp_path, monkeypatch, rsa_key)
    app = transport_tests.server.build_web_ceo_v2_with_coo_mcp_app(settings.executive,
        coo_settings=settings, audit_sink=transport_tests.app_tests.Sink())
    async def call():
        async with app._app.router.lifespan_context(app._app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1") as client:
                return await transport_tests.mcp_tests.rpc(client, token, "/mcp/coo", "tools/call",
                    {"name": wire.TOOL, "arguments": {"work_ref": transport_tests.WORK}})
    reply = asyncio.run(call())
    assert reply.status_code == 200
    result = types.CallToolResult.model_validate(reply.json()["result"])
    record = current["binding"]["binding"]
    frame = transport_tests.frame_for(backend, {key: value for key, value in record.items() if key != "permission_digest"})
    publication = consumer.publication_from_document(context_document(frame, record))
    raw, receipt = decode_context_result(result, publication)
    assert raw == seen["results"][0]["stdout"].encode()
    assert receipt == json.loads(result.content[0].text)["data"]["receipt"]
