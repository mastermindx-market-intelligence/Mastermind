"""V4 enrolment uses the original current-DATA context owners and native SDK.

The inherited fixture executes actual temporary Git/Event/compiler paths with
declared host-seal/credential edges. No Control socket or service is opened.
"""
import asyncio
import dataclasses
import json

import pytest
from mcp import types

from common import coo_agentos_context_contract as wire
from common import coo_discovery_contract as discovery
from control_plane.executive_agent_capabilities import ExecutionCapabilityRegistry, HERMES_NATIVE_DISCOVERY_PROFILE_ID as PROFILE
from integrations.hermes_harness import native_executive_consumer as consumer
from integrations.hermes_harness.native_agentos_context import decode_context_result
from integrations.hermes_harness.tests.test_native_current_agentos_context import signed, current_document
from integrations.mastermind_executive_app.coo import create_coo_app
from integrations.mastermind_executive_app.coo_binding import principal_frame
from integrations.mastermind_executive_app.coo_installed import CooFactsClient
from integrations.mastermind_workspace_app.contract import principal_frame as workspace_frame
from tests import test_executive_current_agentos_context as app_tests
from tests.test_installed_current_agentos_context import joined, owner, env, isolated_git_env, identity

rsa_key = app_tests.rsa_key


@pytest.fixture
def v4(signed):
    s = signed
    raw = json.loads(s["path"].read_text()); raw["profiles"][PROFILE]["enabled"] = True
    s["path"].write_text(json.dumps(raw))
    registry = ExecutionCapabilityRegistry.load(s["path"], source_root=app_tests.ROOT)
    s["coo"]["missions"][0].update(capability_profile_id=PROFILE,
        capability_profile_digest=registry.profiles[PROFILE].profile_digest,
        principal_actions=sorted((wire.CURRENT_ACTION, discovery.READ_ACTION, discovery.CORRECTION_ACTION)))
    def context(who, workspace, context, digest):
        return s["provider"].read_discovery_agentos_context(dict(schema=wire.DISCOVERY_FRAME_SCHEMA,
            principal=principal_frame(who), workspace_principal=workspace_frame(workspace),
            principal_context=dataclasses.asdict(context), capability_profile_digest=digest))
    settings = dataclasses.replace(s["settings"], agentos_discovery_context_provider=context)
    s["settings"] = settings
    s["app"] = create_coo_app(settings, audit_sink=s["sink"], workspace_app=s["workspace_app"])
    return s


def test_v4_current_data_context_has_explicit_receipt_and_native_decoder(v4):
    response = asyncio.run(app_tests.request(v4))
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["catalogue"] == discovery.CATALOGUE and data["schema"] == wire.DISCOVERY_RESULT_SCHEMA
    doc = current_document(data, v4["coo"]["binding"]["binding"], data["workspace_principal"])
    doc.update(schema=consumer.DISCOVERY_CONSUMER_SCHEMA, tools_schema_digest=consumer.DISCOVERY_TOOLS_SCHEMA_DIGEST)
    publication = consumer.publication_from_document(doc)
    sdk = types.CallToolResult(content=[types.TextContent(type="text", text=response.text)], isError=False)
    raw, receipt = decode_context_result(sdk, publication)
    assert raw == v4["calls"][0][1]["stdout"].encode()
    assert receipt["data_commit"] == v4["j"]["current"] != receipt["compiler_code_commit"]
    with pytest.raises(ValueError): wire.validate_current_result(data,
        expected_context=data["principal_context"], capability_profile_digest=data["capability_profile_digest"],
        expected_workspace_principal=data["workspace_principal"])
    assert not v4["j"]["runtime"].jobs.list_jobs()


def test_existing_private_client_uses_only_explicit_v4_frame(v4, monkeypatch):
    s = v4
    client = CooFactsClient(s["j"]["tmp_path"] / "not-opened.sock")
    calls = []
    async def request(frame):
        calls.append(frame)
        assert frame["schema"] == wire.DISCOVERY_FRAME_SCHEMA
        return {"ok": True, "result": s["provider"].read_discovery_agentos_context(frame)}
    monkeypatch.setattr(client._client, "request", request)
    client._context_request = request
    # Retain a bound method shape at the declared in-memory carrier seam.
    class Carrier:
        socket_path = client._context_socket_path
        async def request(self, frame): return await request(frame)
    held = Carrier()
    client._client = client._context_client = held; client._context_request = held.request
    async def acquire():
        authority, selected = await s["app"]._authority(s["principal"], s["work"],
            s["coo"]["missions"][0]["principal_binding_digest"])
        return await client.agentos_discovery_context(s["principal"], s["j"]["workspace"], selected,
            authority.capability_profile_digest)
    result = asyncio.run(acquire())
    assert len(calls) == 1 and result["catalogue"] == discovery.CATALOGUE
