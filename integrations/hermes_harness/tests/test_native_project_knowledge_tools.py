"""V5 uses the same native registration, caller, future and recovery slot.

The controlled registry is explicit. Actual SDK values and the original owner
produce the previews/status; source HTTP/current-DATA journeys are qualified
separately. No native service, socket or real credential is activated.
"""
import asyncio
import copy
import json
import threading
from types import SimpleNamespace

import pytest
from mcp import types as sdk

from common import coo_project_knowledge_contract as wire
from common import coo_discovery_contract as discovery
from common import coo_agentos_context_contract as context
from integrations.hermes_harness import native_discovery_tools as adapter
from integrations.hermes_harness import native_executive_consumer as consumer
from integrations.hermes_harness.native_mcp import render_consumer_mcp_server
from integrations.hermes_harness.tests import test_native_discovery_tools as native
from tests.test_coo_project_knowledge_tools import file_request, preference_request
from tests.test_project_discovery_correction import correction_owner
from tests.test_workspace_project_git_publisher import env, isolated_git_env


@pytest.fixture
def native_knowledge(correction_owner, tmp_path, monkeypatch):
    o = dict(correction_owner)
    o["request"] = file_request(correction_owner)
    publication, document = native.publication_for(o, knowledge=True)
    registry, manager, ctx = native.controlled_context(monkeypatch, tmp_path / "native-home")
    n = native.build(o, publication, document, registry, manager, ctx, contract=wire)
    n["discovery_request"] = correction_owner["request"]
    yield n
    for _, handle in reversed(n["slot"].discovery_handles):
        handle.dispose()
    n["loop"].close()


def dispatch(n, args=None, *, tool=wire.AUTHOR_TOOL):
    return native.dispatch(n, args, tool=tool)


def sdk_result(body):
    return sdk.CallToolResult(content=[sdk.TextContent(type="text", text=context.encode(body).decode())], isError=False)


def status(n):
    return n["o"]["service"].read_status(n["lookup"], n["o"]["who"])


def test_native_v5_adds_only_two_tools_and_retains_one_original_slot(native_knowledge):
    n = native_knowledge
    assert tuple(row.name for row in n["registered"].tools) == wire.TOOLS
    assert adapter.readback(n["slot"])["catalogue"] == wire.CATALOGUE
    assert consumer.selected_child_publication(n["publication"]) is None and n["slot"].startup is None
    assert render_consumer_mcp_server(n["publication"])["tools"]["include"] == []
    result = dispatch(n)
    assert result["state"] == "OBSERVED" and result["data"] == n["preview"]
    assert result["selection"] == n["lookup"] and len(result["selection"]) == 7
    assert n["gates"] == [(wire.AUTHOR_TOOL, n["args"])]


def test_v5_existing_discovery_tool_uses_new_envelope_and_unchanged_data_validator(native_knowledge):
    n = native_knowledge
    value = {"operation": "prepare", "request": n["discovery_request"]}
    preview = n["o"]["service"].prepare(value["request"], n["o"]["who"])
    n["session"].results = [n["wrapped"](discovery.CORRECTION_TOOL, value, preview)]
    result = dispatch(n, value, tool=discovery.CORRECTION_TOOL)
    assert result["schema"] == wire.RESULT_SCHEMA and result["catalogue"] == wire.CATALOGUE
    assert result["data"] == preview and len(result["selection"]) == 8
    with pytest.raises(ValueError):
        discovery.validate_result(result, tool=discovery.CORRECTION_TOOL, value=value,
            expected_context=result["principal_context"],
            capability_profile_digest=result["capability_profile_digest"],
            workspace_principal=result["workspace_principal"])


@pytest.mark.parametrize("operation", ["prepare", "submit"])
def test_unavailable_reply_retains_original_identity_and_intent_only_recovers_prepare(native_knowledge, operation):
    n = native_knowledge
    n["session"].results = [sdk_result({})]
    args = n["args"] if operation == "prepare" else {
        "operation": "submit", "lookup": n["lookup"], "preview_witness": n["preview"]["preview_witness"]}
    result = dispatch(n, args)
    assert result["state"] == "EFFECT_UNKNOWN" and result["selection"] == n["lookup"]
    assert adapter.readback(n["slot"])["uncertain_original"] == {"operation": operation, "lookup": n["lookup"]}
    value = {"operation": "read", "lookup": n["lookup"]}
    original = status(n)
    assert original["receipt"]["kind"] == "INTENT"
    n["session"].results = [n["wrapped"](wire.AUTHOR_TOOL, value, original)]
    seen = dispatch(n, value)
    assert seen["state"] == "OBSERVED"
    assert (adapter.readback(n["slot"])["uncertain_original"] is None) == (operation == "prepare")


def test_unrelated_current_read_or_preference_cannot_clear_original_note_uncertainty(native_knowledge):
    n = native_knowledge
    n["session"].results = [sdk_result({})]
    assert dispatch(n)["state"] == "EFFECT_UNKNOWN"
    first = copy.deepcopy(n["slot"].discovery_uncertain)
    other = {"operation": "prepare", "request": preference_request(n["o"]["request"])}
    refused = dispatch(n, other)
    assert refused["state"] == "NOT_DISPATCHED" and refused["reason"] == "ORIGINAL_OPERATION_UNRESOLVED"
    value = {"mode": "catalogue", "work_ref": n["publication"].work_ref}
    n["session"].results = [sdk_result(wire.result(wire.READ_TOOL, value,
        state="UNAVAILABLE", reason="SOURCE_UNAVAILABLE"))]
    assert dispatch(n, value, tool=wire.READ_TOOL)["state"] == "UNAVAILABLE"
    assert n["slot"].discovery_uncertain == first
    assert n["o"]["pr"].create_calls == 0


def test_changed_seventh_field_cannot_reconcile_original_uncertainty(native_knowledge):
    n = native_knowledge
    n["session"].results = [sdk_result({})]
    assert dispatch(n)["state"] == "EFFECT_UNKNOWN"
    original = copy.deepcopy(n["lookup"])
    changed = dict(original, base_revision="f" * 64)
    result = dispatch(n, {"operation": "reconcile", "lookup": changed})
    assert result["state"] == "NOT_DISPATCHED" and result["reason"] == "ORIGINAL_OPERATION_UNRESOLVED"
    assert n["slot"].discovery_uncertain["lookup"] == original


def test_timeout_retains_original_future_and_blocks_concurrent_note_or_recovery(native_knowledge):
    n = native_knowledge
    entered, release = threading.Event(), threading.Event()
    actual = n["session"].call_tool
    async def delayed(*args, **kwargs):
        entered.set()
        await asyncio.to_thread(release.wait)
        return await actual(*args, **kwargs)
    n["session"].call_tool = delayed
    n["binding"].caller._timeout = 0.02
    try:
        lost = dispatch(n)
        assert entered.wait(1) and lost["state"] == "EFFECT_UNKNOWN"
        original = n["slot"].discovery_call
        future = original["original_future"]
        refusal = dispatch(n, {"operation": "reconcile", "lookup": n["lookup"]})
        assert refusal["reason"] == "ORIGINAL_OPERATION_UNRESOLVED"
        assert n["slot"].discovery_call is original
        release.set()
        future.result(timeout=3)
        assert adapter.readback(n["slot"])["uncertain_original"]["lookup"] == n["lookup"]
        value = {"operation": "read", "lookup": n["lookup"]}
        n["session"].results = [n["wrapped"](wire.AUTHOR_TOOL, value, status(n))]
        n["binding"].caller._timeout = 1
        assert dispatch(n, value)["state"] == "OBSERVED"
        assert adapter.readback(n["slot"])["uncertain_original"] is None
    finally:
        release.set()


@pytest.mark.parametrize("drift", ["wrong_schema", "v4_digest", "knowledge_without_discovery"])
def test_v5_publication_cannot_borrow_a_historical_contract(native_knowledge, drift):
    n = native_knowledge
    if drift == "knowledge_without_discovery":
        import dataclasses
        with pytest.raises(Exception):
            dataclasses.replace(n["publication"], discovery=False)
        return
    document = copy.deepcopy(n["document"])
    if drift == "wrong_schema":
        document["schema"] = consumer.DISCOVERY_CONSUMER_SCHEMA
    else:
        document["tools_schema_digest"] = consumer.DISCOVERY_TOOLS_SCHEMA_DIGEST
    with pytest.raises(Exception):
        consumer.publication_from_document(document)


@pytest.fixture
def pinned_v5(correction_owner, tmp_path, monkeypatch):
    """Actual pinned PluginContext/ToolRegistry; account/model edges stay inert."""
    raw = native.os.environ.get("MASTERMIND_HERMES_VENDOR_ROOT")
    if not raw:
        pytest.skip("exact pinned native checkout required for real v5 registry proof")
    root = native.Path(raw).resolve()
    head = native.subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"],
        capture_output=True, text=True, check=True).stdout.strip()
    assert head == "1c0cd667746d3395fe9e1b6c74f8f85952486f18"
    home = tmp_path / "isolated-native-v5-home"
    monkeypatch.setenv("HERMES_HOME", str(home))
    upstream = native._Upstream(root)
    manager = upstream.PluginManager(scope_key=str(home))
    manifest = upstream.PluginManifest(name=consumer.CONSUMER_PLUGIN_NAME, version="1", source="user",
        path=str(tmp_path), provides_tools=list(wire.TOOLS), key=consumer.CONSUMER_PLUGIN_NAME)
    ctx = upstream.PluginContext(manifest, manager)
    o = dict(correction_owner)
    o["request"] = file_request(correction_owner)
    publication, document = native.publication_for(o, knowledge=True)
    n = native.build(o, publication, document, upstream.registry, manager, ctx, register=False, contract=wire)
    try:
        yield n
    finally:
        for _, handle in reversed(n["slot"].discovery_handles):
            handle.dispose()
        n["loop"].close()


def test_pinned_v5_registry_dispatch_and_original_leases(pinned_v5):
    n = pinned_v5
    registered = adapter.register_discovery_tools(n["ctx"], n["slot"])
    assert tuple(row.name for row in registered.tools) == wire.TOOLS
    result = n["registry"].dispatch(wire.AUTHOR_TOOL, n["args"],
        scope=n["manager"].scope_key, session_id="original-session")
    result = json.loads(result)
    assert result["state"] == "OBSERVED" and result["data"] == n["preview"]
    assert result["selection"] == n["lookup"]
    assert adapter.readback(n["slot"])["catalogue"] == wire.CATALOGUE
    for row in reversed(registered.tools):
        row.handle.dispose()
    assert all(n["registry"].snapshot_registration(tool, scope=n["manager"].scope_key) is None
        for tool in wire.TOOLS)


def test_pinned_v5_fourth_tool_collision_cannot_partly_replace_owner(pinned_v5):
    n = pinned_v5
    schema = adapter.schemas(n["publication"])[wire.AUTHOR_TOOL]
    handle = n["ctx"].register_tool(name=wire.AUTHOR_TOOL, toolset=adapter.TOOLSET,
        schema=schema, handler=lambda args: "original", check_fn=lambda: True,
        is_async=False, description=schema["description"], emoji="mmx")
    original = n["registry"].snapshot_registration(wire.AUTHOR_TOOL, scope=n["manager"].scope_key)
    try:
        with pytest.raises(native.NativeToolRegistrationError):
            adapter.register_discovery_tools(n["ctx"], n["slot"])
        assert n["registry"].snapshot_registration(wire.AUTHOR_TOOL, scope=n["manager"].scope_key) is original
        assert all(n["registry"].snapshot_registration(tool, scope=n["manager"].scope_key) is None
            for tool in wire.TOOLS[:-1])
        assert n["slot"].discovery_handles == []
    finally:
        handle.dispose()
