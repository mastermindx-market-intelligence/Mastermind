"""Canonical Event/current compiler -> signed App -> native memory/prompt.

The original source/native fixtures retain their declared service, credential,
enrollment and model edges. HTTP and the compiler execute; no real account,
installed service, Unix socket, provider dispatch or efficacy is claimed.
"""
import asyncio
from copy import deepcopy
from dataclasses import replace
import hashlib
import json

import pytest
from mcp import types

from common import coo_agentos_context_contract as wire
from integrations.hermes_harness import native_executive_consumer as consumer
from integrations.hermes_harness.native_agentos_context import decode_context_result
from integrations.hermes_harness.native_mcp import render_consumer_mcp_server
from integrations.hermes_harness.tests.test_native_agentos_context import context_document
from integrations.hermes_runtime import native_agentos_memory as memory
from integrations.hermes_runtime.errors import RuntimeRefusal
from integrations.hermes_runtime.tests import test_native_agentos_memory as native_memory
from integrations.hermes_runtime.tests.test_native_request_observation import native
from integrations.mastermind_executive_app.coo_binding import _digest
from tests import test_executive_current_agentos_context as app
from tests.test_installed_current_agentos_context import joined, owner, env, isolated_git_env, identity

rsa_key = app.rsa_key


def current_document(frame=None, record=None, workspace=None):
    value = context_document(frame, record)
    if record is None:
        value["principal"].update(resource_ref=consumer._CURRENT_PRIMARY_RESOURCE,
            scopes=consumer._CURRENT_PRIMARY_SCOPE.split())
        actual = dict(value["principal"], permission_digest=value["permission_digest"])
        actual["resource"] = actual.pop("resource_ref")
        value["principal_binding_digest"] = _digest(actual)
    if workspace is None:
        workspace = dict(value["principal"], policy_id="workspace-policy",
            resource_ref=consumer._WORKSPACE_RESOURCE, scopes=[consumer._WORKSPACE_SCOPE])
    else:
        workspace = dict(workspace)
        workspace["resource_ref"] = workspace.pop("resource")
    value.update(schema=consumer.CURRENT_CONTEXT_CONSUMER_SCHEMA,
        workspace_principal=workspace, tools_schema_digest=consumer.CURRENT_CONTEXT_TOOLS_SCHEMA_DIGEST)
    value["context"]["source_mode"] = "CANONICAL_PROJECT_DATA"
    value["mcp"].update(url=consumer._CURRENT_PRIMARY_URL, client_id="inert-client",
                         scope=consumer._CURRENT_PRIMARY_SCOPE)
    return value


@pytest.fixture
def signed(joined, monkeypatch, rsa_key):
    # Select the actual public v3 resource in this disposable receiver fixture.
    # Workspace and the canonical publication remain the original same owner.
    factory = joined["factory"]
    def public(policy):
        return replace(policy, resource=consumer._CURRENT_PRIMARY_RESOURCE,
            resource_metadata_url=consumer._CURRENT_PRIMARY_RESOURCE + "/.well-known/oauth-protected-resource")
    factory.policies = replace(factory.policies, read=public(factory.policies.read),
                              submit=public(factory.policies.submit))
    return app.signed.__wrapped__(joined, monkeypatch, rsa_key)


@pytest.fixture
def current_result(signed):
    response = asyncio.run(app.request(signed))
    assert response.status_code == 200, response.text
    body = response.json()
    document = current_document(body["data"], signed["coo"]["binding"]["binding"], body["data"]["workspace_principal"])
    publication = consumer.publication_from_document(document)
    sdk = types.CallToolResult(content=[types.TextContent(type="text", text=response.text)], isError=False)
    return publication, sdk, signed, document


def test_v3_uses_existing_publication_type_and_derives_one_closed_companion():
    document = current_document()
    publication = consumer.publication_from_document(document)
    assert type(publication) is consumer.ExecutiveContextConsumerPublication
    assert consumer.validate_consumer_publication(document) == document
    assert consumer.selected_child_publication(publication) is None
    config = render_consumer_mcp_server(publication)
    frame = consumer.workspace_principal_frame(publication)
    assert config["oauth"]["workspace"]["principal_scope"] == hashlib.sha256(consumer._canonical(frame)).hexdigest()
    assert publication.mcp.matches_config(config)
    assert config["tools"] == {"include": [], "resources": False, "prompts": False}
    assert "headers" not in config and "client_secret" not in config["oauth"]
    old = consumer.publication_from_document(context_document())
    assert "workspace" not in render_consumer_mcp_server(old)["oauth"]
    assert not old.mcp.matches_config(config)


@pytest.mark.parametrize("change", [
    lambda d: d.update(schema=consumer.CONTEXT_CONSUMER_SCHEMA),
    lambda d: d.pop("workspace_principal"),
    lambda d: d.update(workspace_principal=None),
    lambda d: d["context"].update(source_mode="ADOPTED_SNAPSHOT"),
    lambda d: d.update(tools_schema_digest=consumer.CONTEXT_TOOLS_SCHEMA_DIGEST),
    lambda d: d["workspace_principal"].update(resource_ref=consumer._CURRENT_PRIMARY_RESOURCE),
    lambda d: d["workspace_principal"].update(scopes=["mastermind.workspace.write"]),
    lambda d: d["workspace_principal"].update(client_ref="f" * 64),
    lambda d: d["workspace_principal"].update(subject_digest="f" * 64),
    lambda d: d["workspace_principal"].update(issuer_digest="f" * 64),
    lambda d: d["workspace_principal"].update(policy_id=d["principal"]["policy_id"]),
    lambda d: d["mcp"].update(_workspace_principal_scope="f" * 64),
])
def test_publication_versions_cannot_mix_or_choose_another_workspace(change):
    document = current_document()
    change(document)
    with pytest.raises(RuntimeRefusal):
        consumer.publication_from_document(document)


@pytest.mark.parametrize("change", [
    lambda d: d["oauth"].pop("workspace"),
    lambda d: d["oauth"]["workspace"].update(principal_scope="f" * 64),
    lambda d: d["oauth"]["workspace"].update(scope="mastermind.workspace.write"),
    lambda d: d["oauth"].update(client_secret="inert-forbidden"),
    lambda d: d.update(transport="sse"),
    lambda d: d.update(strict_redirect_headers=False),
    lambda d: d.update(headers={"Authorization": "inert-forbidden"}),
    lambda d: d.update(server_json="alternate.json"),
    lambda d: d.update(ssl_verify=False),
])
def test_continuing_connection_guard_keeps_complete_pair(change):
    publication = consumer.publication_from_document(current_document())
    config = render_consumer_mcp_server(publication)
    change(config)
    assert not publication.mcp.matches_config(config)


def test_current_compiler_bytes_and_workspace_echo_survive_native_sdk_decoder(current_result):
    publication, sdk, signed, _ = current_result
    raw, receipt = decode_context_result(sdk, publication)
    assert raw == signed["calls"][0][1]["stdout"].encode()
    assert receipt["source_mode"] == "CANONICAL_PROJECT_DATA"
    assert receipt["compiler_code_commit"] != receipt["data_commit"]
    assert receipt["data_observation"]["source_operation"]["event_id"] == signed["j"]["status"]["receipt"]["event_id"]
    for change in (lambda d: d.update(tool=wire.TOOL),
                   lambda d: d["data"]["workspace_principal"].update(client_ref="f" * 64),
                   lambda d: d["data"]["receipt"].update(source_mode="ADOPTED_SNAPSHOT")):
        value = json.loads(sdk.content[0].text)
        change(value)
        bad = types.CallToolResult(content=[types.TextContent(type="text", text=json.dumps(value))])
        with pytest.raises(RuntimeRefusal):
            decode_context_result(bad, publication)


@pytest.fixture
def lifecycle(native, current_result, monkeypatch):
    publication, sdk, signed, document = current_result
    monkeypatch.setattr(native_memory, "context_document", lambda *_a, **_k: deepcopy(document))
    selection = dict(kind=memory.WORKSPACE_OAUTH_DERIVATION_KIND, base_sha=memory.DERIVATION_BASE,
        patch_sha256=memory.WORKSPACE_OAUTH_DERIVATION_PATCH, source_root="/opt/hermes/pristine")
    monkeypatch.setattr(native_memory, "privacy_selection", lambda: deepcopy(selection))
    monkeypatch.setattr(native_memory, "privacy_receipt", lambda vendor: dict(
        kind=selection["kind"], base_sha=selection["base_sha"], patch_sha256=selection["patch_sha256"],
        postimages=dict(memory.WORKSPACE_OAUTH_DERIVATION_POSTIMAGES),
        license_sha256=memory.PRIVACY_LICENSE_SHA256, vendor_root=str(vendor)))
    generator = native_memory.lifecycle.__wrapped__(native, (publication, sdk, signed), monkeypatch)
    value = next(generator)
    async def current_rpc(name, arguments=None, **kwargs):
        assert name == wire.CURRENT_TOOL and arguments == {"work_ref": publication.work_ref}
        value.session.calls.append((name, dict(arguments)))
        response = await app.request(signed)
        assert response.status_code == 200, response.text
        return types.CallToolResult(content=[types.TextContent(type="text", text=response.text)], isError=False)
    monkeypatch.setattr(value.session, "call_tool", current_rpc)
    value.signed = signed
    try:
        yield value
    finally:
        with pytest.raises(StopIteration):
            next(generator)


def test_actual_current_reader_reaches_original_native_provider_and_each_prompt(lifecycle):
    l = lifecycle
    before = len(l.signed["calls"])
    first = native_memory.exercise(l)
    second = native_memory.exercise(l, admission="admission-2", generation=4, cached=first["agent"])
    assert len(l.signed["calls"]) == before + 2  # Two new actual compiler acquisitions.
    assert l.session.calls == [(wire.CURRENT_TOOL, {"work_ref": l.slot.publication.work_ref})] * 2
    assert l.stores == [] and l.slot.startup is None and l.slot.registration is None
    for result, acquisition in zip((first, second), l.signed["calls"][before:], strict=True):
        live = result["live_readback"]
        assert live["schema"] == memory.CURRENT_READBACK_SCHEMA
        assert live["context"]["source_mode"] == "CANONICAL_PROJECT_DATA"
        assert live["context"]["readiness"]["state"] == "READY"
        assert live["context"]["last_delivery"]["prompt"]["boundary"] == "build_api_messages"
        assert "<memory-context>" in result["built"][0][-1]["content"]
        assert result["context"] in result["built"][0][-1]["content"]
        assert acquisition[1]["stdout"] in result["context"]
        envelope = json.loads(next(line for line in result["context"].splitlines()
            if line.startswith('{"agentos_read_observation":')))
        observed = envelope["agentos_read_observation"]
        assert observed["source_mode"] == "CANONICAL_PROJECT_DATA"
        assert observed["compiler_code_commit"] != observed["data_commit"]
        assert observed["bundle_sha256"] == live["context"]["last_delivery"]["bundle_sha256"]
        settled = result["settled_readback"]
        assert memory.validate_consumer_readback(settled, publication=l.slot.publication,
            expected_binding=settled["binding"]) == settled
        wrong = deepcopy(settled)
        wrong["schema"] = memory.READBACK_SCHEMA
        with pytest.raises(RuntimeRefusal):
            memory.validate_consumer_readback(wrong, publication=l.slot.publication,
                                             expected_binding=settled["binding"])


def test_current_factory_demands_complete_current_derivation(lifecycle):
    l = lifecycle
    l.native.launch.derivation["postimages"].pop("tools/mcp_oauth_manager.py")
    with pytest.raises(RuntimeRefusal):
        native_memory.exercise(l)


@pytest.mark.parametrize("current", [False, True])
@pytest.mark.parametrize("deferred", [False, True])
def test_release_bootstrap_keeps_exact_consumer_and_derivation_pair(current, deferred):
    from integrations.hermes_harness.tests.test_native_executive_consumer import _installation
    from ops.executive_os import release_manifest as release
    from tests.test_hermes_vendor_derivation import derivation
    document = current_document() if current else context_document()
    installation = _installation(consumer=document)
    native = next(row["native_gateway"] for row in installation["roles"] if row["role"] == "mmsecretary")
    kind = "workspace_oauth_privacy" if current else "diagnostic_privacy"
    native["vendor_derivation"] = derivation(kind)
    qualified = release.validate_hermes_runtime_installation(installation, _defer_consumer=deferred)
    actual = next(row["native_gateway"] for row in qualified["roles"] if row["role"] == "mmsecretary")
    assert actual["executive_consumer"] == document and actual["vendor_derivation"] == derivation(kind)
    for wrong in (None, "computer_env_guard", "diagnostic_privacy" if current else "workspace_oauth_privacy"):
        if wrong is None:
            native.pop("vendor_derivation", None)
        else:
            native["vendor_derivation"] = derivation(wrong)
        with pytest.raises(release.ReleaseManifestError):
            release.validate_hermes_runtime_installation(installation, _defer_consumer=deferred)
