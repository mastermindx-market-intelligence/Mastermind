"""Single-resource API ClientSession -> signed App -> Unix Control -> Runtime.

The actual T3 API source profile is enabled only in a disposable registry and
mission. No Hermes publication, ConsumerSlot, native T3 identity or Workspace
bearer is used. The incumbent fixture owns real admission, workspace/claim,
completion seal and ACK transactions; its physical provider and Mission input
are disposable fixtures. This requires the real Unix-socket test capability.
"""
from __future__ import annotations

import asyncio
import copy
import dataclasses
import json
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from common import coo_requester_return_contract as wire
from control_plane.executive_agent_capabilities import T3_API_REQUESTER_RETURN_PROFILE_ID
from integrations.executive_mcp import server
from integrations.mastermind_executive_app.coo_binding import principal_frame
from integrations.mastermind_executive_app.gateway import CeoIngressClient
from tests import test_hermes_selected_child_ingress as ingress
from tests.test_hermes_selected_child_dispatch import _settle, _claim_events
from tests.test_t3_api_requester_contract import enable_disposable_t3_requester_contract

rsa_key = ingress.rsa_key


def _receipts(runtime):
    with runtime.store.read() as connection:
        return list(connection.execute("SELECT * FROM events WHERE event_type=?", (wire.CONSUMPTION_EVENT,)))


@asynccontextmanager
async def _session(settings, token):
    app = server._build_coo_mcp_app(settings, audit_sink=ingress.app_fixture.Sink())
    async with app._app.router.lifespan_context(app._app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
            base_url="http://127.0.0.1", headers={"authorization": "Bearer " + token}) as http_client:
            assert "x-mastermind-workspace-authorization" not in http_client.headers
            async with streamable_http_client("http://127.0.0.1/mcp/coo", http_client=http_client) as (read, write, _):
                async with ClientSession(read, write) as session:
                    initialized = await session.initialize()
                    assert initialized.serverInfo.name == "mastermind-executive-coo"
                    yield session


async def _call(session, arguments):
    result = await session.call_tool("mmx_delegate", arguments)
    body = json.loads(next(item.text for item in result.content if item.type == "text"))
    assert result.isError is False, body
    assert body["schema"] == "mastermind.hermes_delegate.selected_child/v1", body
    return body


def _nested_admission(service, root, leaf_depth):
    coordinator = root
    for level in range(leaf_depth):
        planner = service.runtime.jobs.create_cycle_planner(coordinator.job_id,
            command_id=f"coo-cycle:{coordinator.job_id}:create-planner:0")
        planned = service.runtime.attempts.dispatch_cycle_job(planner.job_id,
            worker_id=service.config.worker_id,
            command_id=f"coo-cycle:{coordinator.job_id}:dispatch:{planner.job_id}:attempt:1")
        delegation = {"descendant_limit": 14 - 2 * level, "max_depth": 3} if level < leaf_depth - 1 else None
        ingress._complete(service.runtime, planned,
            ingress._plan_body(planned, coordinator, delegation=delegation))
        coordinator = service.runtime.jobs.admit_cycle_plan(coordinator.job_id,
            command_id=f"coo-cycle:{coordinator.job_id}:admit-plan:{planned.attempt.attempt_id}")[0]
    return coordinator


@pytest.mark.parametrize("boundary,leaf_depth", [
    ("normal", 1), ("normal", 2), ("normal", 3),
    ("changed_digest", 1), ("stale_source_digest", 1), ("revoked_action", 1),
    ("foreign_principal", 1), ("lost_response", 1), ("concurrent_ack", 1),
])
def test_t3_api_requester_reaches_original_claim_status_and_explicit_ack(
    tmp_path, rsa_key, monkeypatch, boundary, leaf_depth,
):
    original_intent = ingress._coo_intent
    monkeypatch.setattr(ingress, "_coo_intent", lambda config, name:
        {**original_intent(config, name), "workstream": ingress.WORK_REF})
    if leaf_depth > 1:
        monkeypatch.setattr(ingress, "_admit_work_child",
            lambda service, root: _nested_admission(service, root, leaf_depth))
    frames = []
    original_send = CeoIngressClient.send_frame

    async def observed_send(self, path, frame):
        frames.append(copy.deepcopy(frame))
        return await original_send(self, path, frame)

    monkeypatch.setattr(CeoIngressClient, "send_frame", observed_send)

    async def exercise():
        with tempfile.TemporaryDirectory(prefix="mmx-t3-api-", dir="/tmp") as directory:
            async with ingress._control(tmp_path, Path(directory), name=f"t3-api-{boundary}-{leaf_depth}") as host:
                profile = enable_disposable_t3_requester_contract(host.host, host.authority_config,
                    tmp_path / "selected-child-authority" / "capabilities.json")
                assert profile.profile_id == T3_API_REQUESTER_RETURN_PROFILE_ID
                settings, token = await ingress._installed_app(host, rsa_key, socket_path=host.socket)
                settings = dataclasses.replace(settings, catalogue_provider=lambda principal, work_ref=None:
                    host.host.source.catalogue_for_principal(principal_frame(principal), work_ref=work_ref))
                command = host.target.children[0].command_id
                async with _session(settings, token) as session:
                    listed = await session.list_tools()
                    assert "executive_project_help" not in {tool.name for tool in listed.tools}
                    assert not _receipts(host.service.runtime)
                    submitted = await _call(session, {"action": "selected_child_submit", "command": command})
                    assert submitted["state"] in {"ACTIVE", "COMPLETED"}, submitted
                    claim = host.service.runtime.store.get_event_by_command_id(command)
                    retained = wire.validate_claim(claim.payload["selected_child_requester"])
                    assert retained["family"] == "coo_api_principal"
                    assert retained["capability_profile_digest"] == profile.profile_digest
                    assert retained["context"]["principal_binding_digest"] == host.authority_config["missions"][0]["principal_binding_digest"]
                    assert retained["selection"]["root_job_id"] == host.root.job_id
                    assert retained["selection"]["parent_job_id"] == host.work.parent_job_id
                    assert host.work.depth == leaf_depth
                    host.finish_gate.set()
                    await _settle(host.service)
                    observed = await _call(session, {"action": "selected_child_status", "command": command})
                    assert observed["state"] == "COMPLETED", observed
                    descriptor = wire.validate_descriptor(observed["requester_return"], observation=observed)
                    assert descriptor["consumption"] is None and not _receipts(host.service.runtime)
                    assert descriptor["root_job_id"] == host.root.job_id
                    assert descriptor["parent_job_id"] == host.work.parent_job_id
                    assert descriptor["command_id"] == f"coo-cycle:{host.work.parent_job_id}:dispatch:{host.work.job_id}:attempt:1"
                    request = {"action": wire.ACK_ACTION, "command": command, "result": descriptor}

                    if boundary == "foreign_principal":
                        foreign = ingress.fixture._token(rsa_key, scope=" ".join(settings.policy.required_scopes),
                            iss=settings.policy.issuer, aud=settings.policy.resource,
                            sub="c29-selected-child-subject", client_id="foreign-client")
                        count = len(frames)
                        with pytest.raises(Exception):
                            async with _session(settings, foreign) as other:
                                await _call(other, request)
                        assert len(frames) == count and not _receipts(host.service.runtime)
                    elif boundary in {"stale_source_digest", "revoked_action"}:
                        row = host.authority_config["missions"][0]
                        if boundary == "stale_source_digest":
                            row["capability_profile_digest"] = "f" * 64
                        else:
                            row["principal_actions"].remove(wire.ACTION)
                        count = len(frames)
                        refused = await _call(session, request)
                        assert refused["state"] == "REFUSED", refused
                        assert len(frames) == count and not _receipts(host.service.runtime)
                        return
                    elif boundary == "changed_digest":
                        wrong = copy.deepcopy(request)
                        wrong["result"]["result_envelope_digest"] = "f" * 64
                        refused = await _call(session, wrong)
                        assert refused["state"] == "REFUSED", refused
                        assert not _receipts(host.service.runtime)
                    elif boundary == "lost_response":
                        acknowledge = host.service.acknowledge_selected_child_result

                        async def lose_original_response(*args, **kwargs):
                            await acknowledge(*args, **kwargs)
                            raise OSError("original result acknowledgment response lost after commit")

                        monkeypatch.setattr(host.service, "acknowledge_selected_child_result", lose_original_response)

                    replies = (await asyncio.gather(_call(session, request), _call(session, request))
                               if boundary == "concurrent_ack" else [await _call(session, request)])
                    for reply in replies:
                        if boundary == "lost_response":
                            assert reply["state"] == "EFFECT_UNKNOWN", reply
                            assert "requester_return" not in reply
                        else:
                            assert reply["state"] == "COMPLETED", reply
                            assert reply["requester_return"]["consumption"] is not None
                    # Reconcile original command by status. A lost reply is
                    # never followed by an ACK resend or a new child claim.
                    reconciled = await _call(session, {"action": "selected_child_status", "command": command})
                    assert reconciled["state"] == "COMPLETED", reconciled
                    final = wire.validate_descriptor(reconciled["requester_return"], observation=reconciled)
                    assert wire.identity(final) == wire.identity(descriptor)
                    assert final["consumption"] is not None
                    assert final["parent_consumed"] is False and final["acceptance"] == "not_accepted"
                    assert len(_receipts(host.service.runtime)) == 1
                    assert len(_claim_events(host.service.runtime, host.work.job_id)) == 1
                    assert host.service.runtime.jobs.get_job(host.work.job_id).attempt_count == 1

    asyncio.run(exercise())
