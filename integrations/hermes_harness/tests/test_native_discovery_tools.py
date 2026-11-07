"""Real SDK/caller concurrency and original source Events with declared edges.

Controlled registry cases test failure semantics. The separately marked pinned
native cases execute actual PluginContext/ToolRegistry when the immutable donor
checkout is provided. Neither layer installs a service or calls a model/account.
"""
import asyncio
import concurrent.futures
import contextlib
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
from types import ModuleType, SimpleNamespace

import pytest
from mcp import types as sdk

from common import coo_discovery_contract as wire
from common import coo_agentos_context_contract as context
from common import workspace_discovery_correction_contract as correction
from integrations.hermes_harness import native_discovery_tools as adapter
from integrations.hermes_harness import native_executive_consumer as consumer
from integrations.hermes_harness.native_tool_registration import NativeToolRegistrationError
from integrations.hermes_harness.native_agentos_context import expected_context
from integrations.hermes_harness.native_mcp import render_consumer_mcp_server
from integrations.hermes_harness.tests.test_native_current_agentos_context import current_document
from integrations.hermes_harness.tests.test_native_executive_consumer import _McpLoop, _Owner, _Session
from integrations.hermes_harness.tests.test_native_tool_registration import _Upstream
from integrations.mastermind_executive_app.coo_binding import _digest
from integrations.mastermind_workspace_app.contract import principal_frame
from tests.test_project_discovery_correction import correction_owner, selection
from tests.test_workspace_project_git_publisher import env, isolated_git_env


def publication_for(o):
    workspace = principal_frame(o["who"])
    record = dict(workspace, policy_id="discovery-executive-fixture", resource=consumer._CURRENT_PRIMARY_RESOURCE,
        scopes=consumer._CURRENT_PRIMARY_SCOPE.split(), permission_digest="d" * 64)
    document = current_document(record=record, workspace=workspace)
    document.update(work_ref=o["request"]["work_ref"], schema=consumer.DISCOVERY_CONSUMER_SCHEMA,
                    tools_schema_digest=consumer.DISCOVERY_TOOLS_SCHEMA_DIGEST)
    return consumer.publication_from_document(document), document


class Registry:
    """Explicit registry edge for component failure/concurrency tests."""
    def __init__(self): self.entries = {}; self.inherited = {}
    def snapshot_registration(self, name, *, scope): return self.entries.get((scope, name))
    def get_entry(self, name, *, scope): return self.entries.get((scope, name), self.inherited.get(name))


def controlled_context(monkeypatch, home):
    registry = Registry()
    manager = SimpleNamespace(scope_key=str(home), _plugins={})
    manifest = SimpleNamespace(name=consumer.CONSUMER_PLUGIN_NAME, source=consumer.CONSUMER_PLUGIN_SOURCE)
    class Context:
        profile_name = "default"
        def __init__(self): self._manager = manager; self.manifest = manifest
        def register_tool(self, **values):
            entry = SimpleNamespace(**values)
            key = (manager.scope_key, values["name"])
            registry.entries[key] = entry
            def dispose():
                if registry.entries.get(key) is entry: registry.entries.pop(key)
            return SimpleNamespace(dispose=dispose)
    monkeypatch.setattr(adapter, "_registry", lambda: registry)
    monkeypatch.setattr(adapter, "_loading_mode_refusal", lambda ctx: None)
    module = ModuleType("registration_lifecycle")
    module.replacement_coordinator = SimpleNamespace(transaction=contextlib.nullcontext)
    monkeypatch.setitem(sys.modules, "registration_lifecycle", module)
    return registry, manager, Context()


@pytest.fixture
def native_binding(correction_owner, tmp_path, monkeypatch):
    o = correction_owner
    publication, document = publication_for(o)
    registry, manager, ctx = controlled_context(monkeypatch, tmp_path / "native-home")
    return build(o, publication, document, registry, manager, ctx)


def build(o, publication, document, registry, manager, ctx, *, register=True):
    loop = _McpLoop()
    session = _Session()
    owner = _Owner(session)
    state = {"current": True, "gate": None, "book": None}
    gates = []
    def gate(tool, booked, args):
        gates.append((tool, copy.deepcopy(args)))
        if state["book"] is not None: booked.append(state["book"])
        return state["gate"]
    slot = consumer.install_consumer_slot(manager, consumer.ConsumerSlot(owner="source-fixture",
        profile_id=ctx.profile_name, source=consumer.CONSUMER_PLUGIN_SOURCE,
        plugin_id=consumer.CONSUMER_PLUGIN_NAME, publication=publication))
    slot.package_check = slot.import_current = lambda: True
    caller = consumer._NativeMcpCaller(server=owner, session=session, loop=loop.loop,
        currentness=lambda: state["current"], wait_for_lock=False, timeout=1)
    binding = adapter.NativeDiscoveryBinding(slot, publication, caller, ctx.profile_name,
        "original-session", None, lambda: state["current"], gate)
    slot.discovery_binding = binding
    registered = adapter.register_discovery_tools(ctx, slot) if register else None
    slot.loader_record = manager._plugins[consumer.CONSUMER_PLUGIN_NAME] = SimpleNamespace(
        enabled=True, error=None, manifest=ctx.manifest)
    slot.load_outcome = "CONTEXT_REGISTERED"
    preview = o["service"].prepare(o["request"], o["who"])
    selection_value = correction.request_lookup(o["request"])
    args = {"operation": "prepare", "request": o["request"]}
    def wrapped(tool, value, data):
        body = wire.result(tool, value, state="OBSERVED", reason="OWNER_RESULT",
            principal_context=expected_context(publication), capability_profile_digest=publication.capability_profile_digest,
            workspace_principal=consumer.workspace_principal_frame(publication), data=data)
        return sdk.CallToolResult(content=[sdk.TextContent(type="text", text=context.encode(body).decode())], isError=False)
    session.results = [wrapped(wire.CORRECTION_TOOL, args, preview)]
    result = dict(o=o, publication=publication, document=document, registry=registry, manager=manager, ctx=ctx,
        loop=loop, session=session, owner=owner, state=state, gates=gates, slot=slot, binding=binding,
        registered=registered, args=args, lookup=selection_value, preview=preview, wrapped=wrapped)
    return result


@pytest.fixture(autouse=True)
def cleanup(request):
    yield
    # Each fixture-created loop/lease is disposed by its original owner.
    n = (request.node.funcargs.get("native_binding") or request.node.funcargs.get("pinned_native")
         or request.node.funcargs.get("pinned_registration"))
    if n:
        for _, handle in reversed(n["slot"].discovery_handles): handle.dispose()
        n["loop"].close()


def dispatch(n, args=None, *, tool=wire.CORRECTION_TOOL, session_id="original-session", task_id=None):
    entry = n["registry"].snapshot_registration(tool, scope=n["manager"].scope_key)
    return json.loads(entry.handler(n["args"] if args is None else args, session_id=session_id, task_id=task_id))


def test_v4_has_two_explicit_tools_without_child_and_retains_raw_mcp_exclusion(native_binding):
    n = native_binding
    assert n["slot"].startup is None and consumer.selected_child_publication(n["publication"]) is None
    assert tuple(row.name for row in n["registered"].tools) == wire.TOOLS
    assert render_consumer_mcp_server(n["publication"])["tools"]["include"] == []
    assert dispatch(n)["data"] == n["preview"]
    assert n["gates"] == [(wire.CORRECTION_TOOL, n["args"])]
    assert len(n["session"].calls) == 1
    assert adapter.readback(n["slot"])["registered"] is True
    old = copy.deepcopy(n["document"]); old["schema"] = consumer.CURRENT_CONTEXT_CONSUMER_SCHEMA
    with pytest.raises(Exception): consumer.publication_from_document(old)


@pytest.mark.parametrize("change", ["session", "task", "currentness", "loader", "entry", "schema", "slot"])
def test_native_handler_checks_lineage_and_actual_installed_entry(native_binding, change):
    n = native_binding; session_id = "original-session"; task_id = None
    if change == "session": session_id = "other-session"
    elif change == "task": task_id = "unassigned-child"
    elif change == "currentness": n["state"]["current"] = False
    elif change == "loader": n["slot"].loader_record.enabled = False
    elif change == "entry": n["registered"].tools[0].handle.dispose()
    elif change == "schema": n["registered"].tools[0].entry.schema["parameters"]["extra"] = True
    else: setattr(n["manager"], consumer.CONSUMER_SLOT_ATTRIBUTE, object())
    result = dispatch(n, session_id=session_id, task_id=task_id)
    assert result["state"] == "NOT_DISPATCHED" and not n["session"].calls and not n["gates"]


@pytest.mark.parametrize("mode", ["prepare", "submit", "reconcile"])
def test_malformed_mutating_result_keeps_all_eight_original_fields(native_binding, mode):
    n = native_binding
    args = n["args"] if mode == "prepare" else {"operation": mode, "lookup": n["lookup"]}
    if mode == "submit": args["preview_witness"] = n["preview"]["preview_witness"]
    n["session"].results = [sdk.CallToolResult(content=[sdk.TextContent(type="text", text='{"malformed":true}')], isError=False)]
    result = dispatch(n, args)
    assert result["state"] == "EFFECT_UNKNOWN" and result["selection"] == n["lookup"]
    assert n["slot"].discovery_uncertain == {"operation": mode, "lookup": n["lookup"]}
    if mode != "reconcile":
        assert dispatch(n, args)["state"] == "NOT_DISPATCHED"
    assert len(n["session"].calls) == 1


def test_original_busy_lock_proves_no_send_and_refunds_same_charge_once(native_binding):
    n = native_binding
    class Charge:
        calls = 0
        def refund(self): self.calls += 1
    charge = Charge(); n["state"]["book"] = charge
    asyncio.run_coroutine_threadsafe(n["owner"]._rpc_lock.acquire(), n["loop"].loop).result(timeout=1)
    try:
        result = dispatch(n)
        assert result["state"] == "NOT_DISPATCHED" and not n["session"].calls
        assert n["slot"].discovery_uncertain is None and charge.calls == 1
    finally:
        n["loop"].loop.call_soon_threadsafe(n["owner"]._rpc_lock.release)


def test_timeout_keeps_original_future_and_no_queued_duplicate(native_binding):
    n = native_binding
    release = threading.Event(); entered = threading.Event()
    original = n["session"].call_tool
    async def delayed(*a, **kw):
        entered.set()
        await asyncio.to_thread(release.wait)
        return await original(*a, **kw)
    n["session"].call_tool = delayed
    n["binding"].caller._timeout = 0.02
    try:
        result = dispatch(n)
        assert entered.is_set() and result["state"] == "EFFECT_UNKNOWN"
        call = n["slot"].discovery_call; future = call["original_future"]
        assert type(future) is concurrent.futures.Future and not future.cancelled()
        assert dispatch(n)["reason"] == "ORIGINAL_OPERATION_UNRESOLVED"
        assert n["slot"].discovery_call is call
        release.set(); future.result(timeout=5)
        n["session"].call_tool = original
        status = n["o"]["service"].read_status(n["lookup"], n["o"]["who"])
        args = {"operation": "read", "lookup": n["lookup"]}
        n["session"].results = [n["wrapped"](wire.CORRECTION_TOOL, args, status)]
        n["binding"].caller._timeout = 1
        assert dispatch(n, args)["state"] == "OBSERVED"
        assert n["slot"].discovery_uncertain is None and len(n["session"].calls) == 2
    finally:
        release.set()


def test_late_original_pre_send_proof_resolves_timeout_without_replaying(native_binding):
    n = native_binding
    entered, release = threading.Event(), threading.Event()
    class Charge:
        calls = 0
        def refund(self): self.calls += 1
    charge = Charge(); n["state"]["book"] = charge
    asyncio.run_coroutine_threadsafe(n["owner"]._rpc_lock.acquire(), n["loop"].loop).result(timeout=1)
    def hold_loop(): entered.set(); release.wait()
    n["loop"].loop.call_soon_threadsafe(hold_loop)
    assert entered.wait(1)
    n["binding"].caller._timeout = 0.02
    try:
        assert dispatch(n)["state"] == "EFFECT_UNKNOWN"
        original = n["slot"].discovery_call["original_future"]
        release.set()
        with pytest.raises(consumer._ConsumerNotDispatched): original.result(timeout=5)
        view = adapter.readback(n["slot"])
        assert view["uncertain_original"] is None and n["slot"].discovery_call is None
        assert not n["session"].calls and charge.calls == 1
        adapter.readback(n["slot"]); assert charge.calls == 1
    finally:
        release.set(); n["loop"].loop.call_soon_threadsafe(n["owner"]._rpc_lock.release)


def test_failed_refund_preserves_original_charge_and_blocks_replacement(native_binding):
    n = native_binding
    class Charge:
        calls = 0
        def refund(self): self.calls += 1; raise OSError("inert cost-owner failure")
    charge = Charge(); n["state"]["book"] = charge; n["state"]["gate"] = "refused"
    assert dispatch(n)["state"] == "NOT_DISPATCHED"
    original = n["slot"].discovery_call
    assert original["booked"] == [charge] and original["refund_unknown"] is True
    assert dispatch(n)["reason"] == "ORIGINAL_OPERATION_UNRESOLVED"
    assert n["slot"].discovery_call is original and charge.calls == 1
    assert adapter.readback(n["slot"])["reservation_unresolved"] is True


def test_session_cannot_claim_no_send_after_original_call_entry(native_binding):
    n = native_binding
    entered = []
    async def uncertain(*args, **kwargs):
        entered.append((args, kwargs))
        raise consumer._ConsumerNotDispatched("untrusted session classification")
    n["session"].call_tool = uncertain
    result = dispatch(n)
    assert len(entered) == 1 and result["state"] == "EFFECT_UNKNOWN"
    assert n["slot"].discovery_uncertain == {"operation": "prepare", "lookup": n["lookup"]}


def test_readback_cannot_settle_future_before_original_observer_finalizes(native_binding, monkeypatch):
    n = native_binding
    future = concurrent.futures.Future()
    future.set_exception(consumer._ConsumerNotDispatched("completed original pre-send refusal"))
    def original_call(*args, **kwargs):
        raise consumer._ConsumerUncertain("observer timed out", original_future=future)
    monkeypatch.setattr(consumer._NativeMcpCaller, "call", original_call)
    original_result = wire.result
    observations = []
    def result(*args, **kwargs):
        if kwargs.get("state") == "EFFECT_UNKNOWN":
            original = n["slot"].discovery_call
            observations.append(adapter.readback(n["slot"]))
            assert n["slot"].discovery_call is original
            assert dispatch(n)["reason"] == "ORIGINAL_OPERATION_UNRESOLVED"
        return original_result(*args, **kwargs)
    monkeypatch.setattr(wire, "result", result)
    assert dispatch(n)["state"] == "EFFECT_UNKNOWN" and len(observations) == 1
    assert n["slot"].discovery_uncertain is not None
    assert adapter.readback(n["slot"])["uncertain_original"] is None
    assert n["slot"].discovery_call is None and not n["session"].calls


def test_owner_not_dispatched_can_resolve_original_without_receipt(native_binding):
    n = native_binding
    o = n["o"]
    permission = o["contexts"].bind(o["who"], action=correction.ACTION, work_ref=o["request"]["work_ref"])
    permit = o["events"].claim_phase(selection(n["preview"]), permission.principal_scope,
        permission_binding_digest=permission.permission_binding_digest,
        preview_witness=n["preview"]["preview_witness"], guard=permission.check)
    # Actual retained Event; this fixture's publisher no-effect qualification
    # remains an explicit stand-in, never installed publication evidence.
    o["events"].retain_no_effect(permit, selection(n["preview"]), permission.principal_scope,
        qualify_no_effect=lambda: True, guard=permission.check)
    status = o["service"].read_status(n["lookup"], o["who"])
    assert status["disposition"] == "refused" and status["reason"] == "NOT_DISPATCHED" and status["receipt"] is None
    args = {"operation": "read", "lookup": n["lookup"]}
    result = wire.validate_result(json.loads(n["wrapped"](wire.CORRECTION_TOOL, args, status).content[0].text),
        tool=wire.CORRECTION_TOOL, value=args, expected_context=expected_context(n["publication"]),
        capability_profile_digest=n["publication"].capability_profile_digest,
        workspace_principal=consumer.workspace_principal_frame(n["publication"]))
    pending = {"operation": "submit", "lookup": n["lookup"]}
    assert adapter._recovered(pending, wire.CORRECTION_TOOL, args, result)
    result["data"]["disposition"] = "unknown"; result["data"]["reason"] = "ORIGINAL_OPERATION_NOT_OBSERVED"
    assert not adapter._recovered(pending, wire.CORRECTION_TOOL, args, result)


def pinned_components(correction_owner, tmp_path, monkeypatch, *, register):
    raw = os.environ.get("MASTERMIND_HERMES_VENDOR_ROOT")
    if not raw: pytest.skip("exact pinned native checkout required for real registry API cases")
    root = Path(raw).resolve()
    head = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    assert head == "1c0cd667746d3395fe9e1b6c74f8f85952486f18"
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "isolated-native-home"))
    upstream = _Upstream(root)
    manager = upstream.PluginManager(scope_key=str(tmp_path / "isolated-native-home"))
    manifest = upstream.PluginManifest(name=consumer.CONSUMER_PLUGIN_NAME, version="1", source="user",
        path=str(tmp_path), provides_tools=list(wire.TOOLS), key=consumer.CONSUMER_PLUGIN_NAME)
    ctx = upstream.PluginContext(manifest, manager)
    publication, document = publication_for(correction_owner)
    return build(correction_owner, publication, document, upstream.registry, manager, ctx, register=register)


@pytest.fixture
def pinned_native(correction_owner, tmp_path, monkeypatch):
    return pinned_components(correction_owner, tmp_path, monkeypatch, register=True)


@pytest.fixture
def pinned_registration(correction_owner, tmp_path, monkeypatch):
    return pinned_components(correction_owner, tmp_path, monkeypatch, register=False)


def test_pinned_second_collision_refuses_before_first_registration(pinned_registration, monkeypatch):
    n = pinned_registration
    schema = adapter.schemas()[wire.CORRECTION_TOOL]
    handle = n["ctx"].register_tool(name=wire.CORRECTION_TOOL, toolset=adapter.TOOLSET,
        schema=schema, handler=lambda args: "original", check_fn=lambda: True,
        is_async=False, description=schema["description"], emoji="mmx")
    entry = n["registry"].snapshot_registration(wire.CORRECTION_TOOL, scope=n["slot"].scope)
    def forbidden(**kwargs): pytest.fail("both names must be preflighted before any registration")
    monkeypatch.setattr(n["ctx"], "register_tool", forbidden)
    try:
        with pytest.raises(NativeToolRegistrationError, match="NATIVE_TOOL_COLLISION"):
            adapter.register_discovery_tools(n["ctx"], n["slot"])
        assert not n["slot"].discovery_attempted and not n["slot"].discovery_handles
        assert n["registry"].snapshot_registration(wire.SOURCE_TOOL, scope=n["slot"].scope) is None
        assert n["registry"].snapshot_registration(wire.CORRECTION_TOOL, scope=n["slot"].scope) is entry
    finally:
        handle.dispose()


@pytest.mark.parametrize("failure", ["second_readback", "second_write_then_raise"])
def test_pinned_partial_registration_disposes_only_returned_leases(pinned_registration, monkeypatch, failure):
    n = pinned_registration
    original_register = n["ctx"].register_tool
    original_snapshot = n["registry"].snapshot_registration
    handles = []
    def register(**kwargs):
        handle = original_register(**kwargs); handles.append(handle)
        if len(handles) == 2 and failure == "second_write_then_raise":
            raise OSError("original native owner cannot return its second lease")
        return handle
    def snapshot(name, **kwargs):
        if len(handles) == 2 and name == wire.CORRECTION_TOOL and failure == "second_readback":
            return None
        return original_snapshot(name, **kwargs)
    monkeypatch.setattr(n["ctx"], "register_tool", register)
    monkeypatch.setattr(n["registry"], "snapshot_registration", snapshot)
    try:
        with pytest.raises(NativeToolRegistrationError) as caught:
            adapter.register_discovery_tools(n["ctx"], n["slot"])
        assert len(handles) == 2 and n["slot"].discovery_registration is None
        assert original_snapshot(wire.SOURCE_TOOL, scope=n["slot"].scope) is None
        if failure == "second_readback":
            assert caught.value.code == "NATIVE_TOOL_READBACK_MISMATCH"
            assert original_snapshot(wire.CORRECTION_TOOL, scope=n["slot"].scope) is None
        else:
            assert caught.value.code == "NATIVE_TOOL_REGISTRATION_EFFECT_UNKNOWN"
            assert caught.value.original_tool_name == wire.CORRECTION_TOOL
            assert caught.value.original_context is n["ctx"] and caught.value.original_binding is n["binding"]
            assert caught.value.original_handle is None
            assert original_snapshot(wire.CORRECTION_TOOL, scope=n["slot"].scope) is not None
            assert len(n["slot"].discovery_handles) == 1
        with pytest.raises(NativeToolRegistrationError, match="ORIGINAL_REGISTRATION_RETAINED"):
            adapter.register_discovery_tools(n["ctx"], n["slot"])
        assert len(handles) == 2
    finally:
        # The fixture owns the actual unknown lease. The adapter never receives
        # or disposes it; this cleanup is not credited as runtime reconciliation.
        for handle in reversed(handles): handle.dispose()


def test_pinned_native_registry_dispatch_and_owner_lease_unload(pinned_native):
    n = pinned_native
    result = n["registry"].dispatch(wire.CORRECTION_TOOL, n["args"],
        scope=n["manager"].scope_key, session_id="original-session")
    assert json.loads(result)["state"] == "OBSERVED"
    first, second = n["registered"].tools
    first.handle.dispose()
    assert n["registry"].snapshot_registration(first.name, scope=n["manager"].scope_key) is None
    assert n["registry"].snapshot_registration(second.name, scope=n["manager"].scope_key) is second.entry
    assert json.loads(second.handler(n["args"], session_id="original-session"))["state"] == "NOT_DISPATCHED"
    assert len(n["session"].calls) == 1
