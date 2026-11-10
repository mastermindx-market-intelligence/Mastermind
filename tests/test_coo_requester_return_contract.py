"""Versioned installed grant and explicit native consumer; legacy stays closed."""
from __future__ import annotations

import copy
import dataclasses
import json
import sys
import threading
import types
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from common import coo_requester_return_contract as wire
from control_plane.coo_principal_host import MISSION_AUTHORITY_VERSION
from control_plane.executive_agent_capabilities import (
    ExecutionCapabilityRegistry, HERMES_NATIVE_REQUESTER_RETURN_PROFILE_ID,
    PRINCIPAL_COO_REQUESTER_RETURN_MCP_CAPABILITY_ID,
)
from integrations.executive_mcp import coo
from integrations.executive_mcp.schemas import GatewayError
from integrations.hermes_harness import native_executive_consumer as consumer
from integrations.hermes_harness import native_tool_registration as native
from integrations.hermes_harness.tests.test_native_executive_consumer import (
    _McpLoop, _Owner, _Session, _Result, publication_document,
)
from integrations.hermes_runtime.errors import RuntimeRefusal
from tests.test_executive_coo_host import setup

ROOT = Path(__file__).resolve().parents[1]


def enable_disposable_requester_contract(host, configuration, path):
    """Explicit grant only in a disposable real registry, never installed config."""
    raw = json.loads(path.read_text())
    grant = copy.deepcopy(raw["mcp_servers"]["mastermind-executive-coo-v1"])
    grant["tool_schema_digest"] = coo.coo_requester_return_tool_schema_digest()
    raw["mcp_servers"][PRINCIPAL_COO_REQUESTER_RETURN_MCP_CAPABILITY_ID] = grant
    profile = copy.deepcopy(raw["profiles"]["principal.hermes-native.executive-coo.v1"])
    profile["mcp_servers"] = [PRINCIPAL_COO_REQUESTER_RETURN_MCP_CAPABILITY_ID]
    raw["profiles"][HERMES_NATIVE_REQUESTER_RETURN_PROFILE_ID] = profile
    path.write_text(json.dumps(raw))
    registry = ExecutionCapabilityRegistry.load(path, source_root=ROOT)
    configuration["missions"][0].update(
        authority_version=MISSION_AUTHORITY_VERSION,
        principal_actions=sorted(["bounded_intent", "governed_orchestration", wire.ACTION]),
        capability_profile_id=HERMES_NATIVE_REQUESTER_RETURN_PROFILE_ID,
        capability_profile_digest=registry.profiles[HERMES_NATIVE_REQUESTER_RETURN_PROFILE_ID].profile_digest)
    return registry


def _publication():
    return consumer.publication_from_document(consumer.validate_consumer_publication(
        publication_document(schema=consumer.REQUESTER_RETURN_CONSUMER_SCHEMA,
            tools_schema_digest=coo.coo_requester_return_tool_schema_digest())))


def _descriptor(publication=None):
    p = publication or _publication()
    return {"schema_version": wire.RETURN_SCHEMA, "family": wire.FAMILY,
        "command_id": p.command, "work_ref": p.work_ref, "root_job_id": p.root_job_id,
        "parent_job_id": p.root_job_id, "job_id": p.job_id, "attempt_id": "attempt-1",
        "requester_binding_digest": "a" * 64, "result_envelope_digest": "b" * 64,
        "terminal_evidence_digest": "c" * 64, "consumption": None,
        "parent_consumed": False, "acceptance": "not_accepted"}


def _observation(descriptor, publication, *, consumed=False):
    descriptor = copy.deepcopy(descriptor)
    if consumed:
        descriptor["consumption"] = {"schema_version": wire.CONSUMPTION_SCHEMA,
            "family": wire.FAMILY, **wire.identity(descriptor), "acknowledged_at_ms": 1234}
    return {"schema": native.SELECTED_CHILD_SCHEMA, "state": "COMPLETED", "reason": None,
        "command_id": publication.command, "job_id": publication.job_id,
        "root_job_id": publication.root_job_id, "attempt_id": descriptor["attempt_id"],
        "attempt_status": "COMPLETED", "job_status": "COMPLETED", "live_submit": True,
        "result_status": "RESULT", "result_envelope_digest": descriptor["result_envelope_digest"],
        "terminal_evidence_digest": descriptor["terminal_evidence_digest"],
        "target_digest": publication.target_digest, "requester_return": descriptor}


def test_existing_catalogues_and_default_configuration_keep_exact_grants():
    assert coo.coo_tool_schema_digest() == "5cf2a0de4a47686c545d1ee3d9c388ab4dc94c880cb0670140de2eca2e54f550"
    assert coo.coo_context_tool_schema_digest() == "5fa24aa1d907d66d0ca0a56168617f955e09d063f532cf527fe0d7b923fb50af"
    assert coo.coo_current_context_tool_schema_digest() == "41644c90bbd8b5927c5cc7f97f65fef144ba9f9ca6e0277d702d7a8a26fa0da0"
    assert coo.coo_discovery_tool_schema_digest() == "94db08906bd04c78565f6172d7a657c13bbe608f3b14dba5649cbedb23deed42"
    assert coo.coo_requester_return_tool_schema_digest() == consumer.REQUESTER_RETURN_TOOLS_SCHEMA_DIGEST
    raw = json.loads((ROOT / "config/executive_claude_principal_capabilities.json").read_text())
    assert PRINCIPAL_COO_REQUESTER_RETURN_MCP_CAPABILITY_ID not in raw["mcp_servers"]
    assert HERMES_NATIVE_REQUESTER_RETURN_PROFILE_ID not in raw["profiles"]
    request = {"action": wire.ACK_ACTION, "command": _publication().command, "result": _descriptor()}
    with pytest.raises(GatewayError):
        coo.validate_coo_tool_arguments("mmx_delegate", request)
    assert coo.validate_coo_requester_tool_arguments("mmx_delegate", request) == request
    new = next(s for s in coo.catalogue_specs(wire.CATALOGUE) if s.name == "mmx_delegate")
    Draft202012Validator(new.input_schema).validate(request)
    assert not Draft202012Validator(coo.COO_TOOL_SPECS[-1].input_schema).is_valid(request)
    assert not Draft202012Validator(native.NATIVE_TOOL_SCHEMA["parameters"]).is_valid(request)
    Draft202012Validator(native.NATIVE_REQUESTER_RETURN_TOOL_SCHEMA["parameters"]).validate(request)


def test_actual_installed_source_requires_matching_profile_catalogue_and_mission_action(tmp_path):
    host, configuration, principal, path = setup(tmp_path)
    original = host.source.catalogue_for_principal(principal)
    assert original != wire.CATALOGUE
    enable_disposable_requester_contract(host, configuration, path)
    work = configuration["missions"][0]["work_ref"]
    assert host.source.catalogue_for_principal(principal, work_ref=work) == wire.CATALOGUE
    configuration["missions"][0]["principal_actions"].remove(wire.ACTION)
    with pytest.raises(ValueError):
        host.source.catalogue_for_principal(principal, work_ref=work)
    configuration["missions"][0]["principal_actions"].append(wire.ACTION)
    configuration["missions"][0]["principal_actions"].sort()
    raw = json.loads(path.read_text())
    raw["profiles"][HERMES_NATIVE_REQUESTER_RETURN_PROFILE_ID]["enabled"] = False
    path.write_text(json.dumps(raw))
    with pytest.raises(ValueError):
        host.source.catalogue_for_principal(principal, work_ref=work)


def test_publication_cannot_upgrade_by_boolean_or_old_contract_digest():
    good = _publication()
    assert good.requester_returns is True
    old = consumer.publication_from_document(consumer.validate_consumer_publication(publication_document()))
    assert old.requester_returns is False
    for changed in (
        {"schema": consumer.CONSUMER_SCHEMA, "tools_schema_digest": consumer.REQUESTER_RETURN_TOOLS_SCHEMA_DIGEST},
        {"schema": consumer.REQUESTER_RETURN_CONSUMER_SCHEMA, "tools_schema_digest": "2" * 64},
        {"requester_returns": True},
    ):
        with pytest.raises(RuntimeRefusal):
            consumer.validate_consumer_publication(publication_document(**changed))


@pytest.mark.parametrize("version", [2, 3, 4])
def test_existing_context_publications_project_child_without_implicit_acknowledgment(version):
    from integrations.mastermind_executive_app.coo_binding import _digest
    old = publication_document()
    document = {key: value for key, value in old.items()
                if key not in {"command", "job_id", "target_digest", "root_job_id"}}
    document.update(schema=consumer.CONTEXT_CONSUMER_SCHEMA,
        selected_child={key: old[key] for key in ("command", "job_id", "target_digest", "root_job_id")},
        context=dict(provider="agentos", source_mode="ADOPTED_SNAPSHOT",
                     max_context_bytes=131072, freshness_seconds=120),
        tools_schema_digest=consumer.CONTEXT_TOOLS_SCHEMA_DIGEST, permission_digest="d" * 64)
    if version > 2:
        document["principal"].update(resource_ref=consumer._CURRENT_PRIMARY_RESOURCE,
                                     scopes=consumer._CURRENT_PRIMARY_SCOPE.split())
        document["workspace_principal"] = dict(document["principal"], policy_id="workspace-policy",
            resource_ref=consumer._WORKSPACE_RESOURCE, scopes=[consumer._WORKSPACE_SCOPE])
        document["context"]["source_mode"] = "CANONICAL_PROJECT_DATA"
        document["mcp"].update(url=consumer._CURRENT_PRIMARY_URL, client_id="inert-client",
                               scope=consumer._CURRENT_PRIMARY_SCOPE)
        document["schema"] = consumer.CURRENT_CONTEXT_CONSUMER_SCHEMA if version == 3 else consumer.DISCOVERY_CONSUMER_SCHEMA
        document["tools_schema_digest"] = consumer.CURRENT_CONTEXT_TOOLS_SCHEMA_DIGEST if version == 3 else consumer.DISCOVERY_TOOLS_SCHEMA_DIGEST
    record = dict(document["principal"], permission_digest=document["permission_digest"])
    record["resource"] = record.pop("resource_ref")
    document["principal_binding_digest"] = _digest(record)
    publication = consumer.publication_from_document(document)
    child = consumer.selected_child_publication(publication)
    assert child.command == old["command"] and child.job_id == old["job_id"]
    assert child.tools_schema_digest == document["tools_schema_digest"]
    assert child.requester_returns is False


def test_native_mandate_requires_explicit_current_action_even_with_matching_profile_digest():
    p = _publication()
    mandate = {"principal": {**dataclasses.asdict(p.principal),
        "scopes": list(p.principal.scopes), "principal_binding_digest": p.principal_binding_digest},
        "mission": {key: getattr(p, key) for key in (
            "work_ref", "root_job_id", "mission_authority_ref", "authority_generation_digest")},
        "capability": {"capability_profile_digest": p.capability_profile_digest,
                       "principal_actions": ["governed_orchestration"]}}
    with pytest.raises(RuntimeRefusal):
        consumer.compare_mandate(mandate, p)
    mandate["capability"]["principal_actions"].append(wire.ACTION)
    consumer.compare_mandate(mandate, p)


def _native(session, publication, loop, *, current=lambda: True, enabled=True):
    owner = _Owner(session)
    transport = consumer.NativeExecutiveTransport(publication=publication,
        server=owner, session=session, loop=loop, currentness=current)
    handler = native.native_delegate_handler(native.NativeDelegateBinding(
        transport=transport, currentness_guard=current, profile_id="mmsecretary",
        session_id="original-session", task_id="original-task", command=publication.command,
        job_id=publication.job_id, requester_returns=enabled))
    return handler


def _invoke(handler, request, **changes):
    caller = dict(session_id="original-session", task_id="original-task")
    caller.update(changes)
    return json.loads(handler(request, **caller))


def test_native_owner_reads_then_acknowledges_exact_reviewed_result_only_on_explicit_call():
    p = _publication()
    descriptor = _descriptor(p)
    session = _Session([_Result(structured=_observation(descriptor, p)),
                        _Result(structured=_observation(descriptor, p, consumed=True))])
    loop = _McpLoop()
    try:
        handler = _native(session, p, loop.loop)
        status = _invoke(handler, {"action": "selected_child_status", "command": p.command})
        assert status["requester_return"]["consumption"] is None
        assert len(session.calls) == 1 and session.calls[0][1]["action"] == "selected_child_status"
        request = {"action": wire.ACK_ACTION, "command": p.command, "result": status["requester_return"]}
        result = _invoke(handler, request)
        assert result["requester_return"]["consumption"] is not None
        assert result["requester_return"]["parent_consumed"] is False
        assert session.calls[1] == ("mmx_delegate", request)
    finally:
        loop.close()


@pytest.mark.parametrize("failure", ["not_enrolled", "foreign_session", "foreign_task", "revoked"])
def test_native_ack_refuses_before_captured_rpc_for_unqualified_caller(failure):
    p = _publication()
    session = _Session()
    loop = _McpLoop()
    try:
        handler = _native(session, p, loop.loop, enabled=failure != "not_enrolled",
                          current=lambda: failure != "revoked")
        changes = ({"session_id": "foreign"} if failure == "foreign_session" else
                   {"task_id": "foreign"} if failure == "foreign_task" else {})
        result = _invoke(handler, {"action": wire.ACK_ACTION, "command": p.command,
                                  "result": _descriptor(p)}, **changes)
        assert result["state"] == "REFUSED" and session.calls == []
    finally:
        loop.close()


@pytest.mark.parametrize("failure", ["missing_receipt", "changed_digest", "lost_response"])
def test_native_ack_preserves_original_uncertainty_after_possible_send(failure):
    p = _publication()
    descriptor = _descriptor(p)
    result = _observation(descriptor, p, consumed=failure != "missing_receipt")
    if failure == "changed_digest":
        result["requester_return"]["consumption"]["terminal_evidence_digest"] = "f" * 64
    session = _Session([_Result(structured=result)], error=OSError("response lost") if failure == "lost_response" else None)
    loop = _McpLoop()
    try:
        handler = _native(session, p, loop.loop)
        observed = _invoke(handler, {"action": wire.ACK_ACTION, "command": p.command, "result": descriptor})
        assert observed["state"] == "EFFECT_UNKNOWN" and observed["command_id"] == p.command
        assert len(session.calls) == 1 and "requester_return" not in observed
    finally:
        loop.close()


@pytest.mark.parametrize("requester_returns", [False, True])
def test_native_serving_and_supervisor_readback_require_the_same_qualified_schema(tmp_path, monkeypatch, requester_returns):
    """Read-owner proof with a scoped fixture registry, not an installed plugin."""
    from integrations.hermes_runtime import native_session_control as control
    from integrations.hermes_runtime.supervisor import ServiceRuntime
    document = publication_document(**({"schema": consumer.REQUESTER_RETURN_CONSUMER_SCHEMA,
        "tools_schema_digest": consumer.REQUESTER_RETURN_TOOLS_SCHEMA_DIGEST} if requester_returns else {}))
    publication = consumer.publication_from_document(document)
    home = tmp_path / "native-role"
    manager = types.SimpleNamespace(scope_key=str(home), _plugins={})
    server = _Owner(_Session())
    guard = consumer.NativeConsumerCurrentness(publication=publication,
        session_id="session-1", instance_id="instance-1", authority_epoch=1,
        server=server, session=server.session, guard=lambda: True)
    transport = consumer.NativeExecutiveTransport(publication=publication,
        server=server, session=server.session, loop=None, currentness=guard)
    binding = native.NativeDelegateBinding(transport=transport, currentness_guard=guard,
        profile_id="mmsecretary", session_id="session-1", command=publication.command,
        job_id=publication.job_id, requester_returns=requester_returns)
    owner_sha = "a" * 40
    slot = consumer.install_consumer_slot(manager, consumer.ConsumerSlot(
        owner=owner_sha, profile_id="mmsecretary", source=consumer.CONSUMER_PLUGIN_SOURCE,
        plugin_id=consumer.CONSUMER_PLUGIN_NAME, publication=publication,
        startup=native.NativeDelegateStartup(binding=binding)))
    handler = native.native_delegate_handler(binding)
    check = lambda: True
    expected_schema = native.NATIVE_REQUESTER_RETURN_TOOL_SCHEMA if requester_returns else native.NATIVE_TOOL_SCHEMA
    entry = types.SimpleNamespace(handler=handler, check_fn=check, toolset="mmx_delegate", schema=expected_schema)
    registration = native.NativeDelegateRegistration(name="mmx_delegate", toolset="mmx_delegate",
        scope=str(home), profile_id="mmsecretary", session_id="session-1", command=publication.command,
        job_id=publication.job_id, handler=handler, check_fn=check, handle=object(), entry=entry)
    slot.publish_registration(registration)
    slot.registration_context = types.SimpleNamespace(_manager=manager)
    slot.load_outcome = "REGISTERED"
    loaded = types.SimpleNamespace(enabled=True, error=None)
    slot.loader_record = loaded
    manager._plugins[consumer.CONSUMER_PLUGIN_NAME] = loaded
    live = {"entry": entry}
    plugins = types.ModuleType("hermes_cli.plugins")
    plugins.get_plugin_manager = lambda: manager
    registry = types.ModuleType("tools.registry")
    registry.registry = types.SimpleNamespace(snapshot_registration=lambda name, scope:
        live["entry"] if name == "mmx_delegate" and scope == str(home) else None)
    monkeypatch.setitem(sys.modules, "hermes_cli.plugins", plugins)
    monkeypatch.setitem(sys.modules, "tools.registry", registry)
    monkeypatch.setattr(control, "current_runtime_owner", lambda: owner_sha)
    runner = types.SimpleNamespace(_draining=False, session_runtime_descriptor={
        "state": "ready", "instance_id": "instance-1", "authority_epoch": 1})
    proof = control._consumer_extension(runner, home)
    assert proof["schema_sha256"] == consumer.schema_digest(expected_schema)
    assert proof["mcp_tools_schema_sha256"] == publication.tools_schema_digest

    # The existing supervisor validates this proof against the same held
    # publication and original enrolled child, not a caller's feature flag.
    supervisor = ServiceRuntime.__new__(ServiceRuntime)
    supervisor._lock = threading.Lock()
    supervisor._child = types.SimpleNamespace(pid=42, poll=lambda: None)
    supervisor._native_home = home
    supervisor._native_launch = types.SimpleNamespace(owner=types.SimpleNamespace(root=tmp_path / owner_sha))
    observation = {"proof": proof}
    target = {"instance_id": "instance-1", "authority_epoch": 1, "session_id": "session-1"}
    supervisor._observe_consumer_extension = lambda child_pid: (observation["proof"], target)
    supervisor._consumer_publication = lambda: document
    supervisor._consume_consumer_extension(42)
    assert supervisor._extension_proved is True
    other_schema = native.NATIVE_TOOL_SCHEMA if requester_returns else native.NATIVE_REQUESTER_RETURN_TOOL_SCHEMA
    observation["proof"] = {**proof, "schema_sha256": consumer.schema_digest(other_schema)}
    supervisor._consume_consumer_extension(42)
    assert supervisor._extension_proved is False

    live["entry"] = types.SimpleNamespace(handler=lambda: None, check_fn=check,
        toolset="mmx_delegate", schema=expected_schema)
    with pytest.raises(RuntimeRefusal):
        control._consumer_extension(runner, home)
    live["entry"] = entry
    slot.startup = native.NativeDelegateStartup(binding=dataclasses.replace(
        binding, requester_returns=not requester_returns))
    with pytest.raises(RuntimeRefusal):
        control._consumer_extension(runner, home)
