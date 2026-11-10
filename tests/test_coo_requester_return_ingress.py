"""Real MCP SDK/native consumer -> signed App -> existing Unix Control -> Runtime.

Requires the incumbent Unix-socket test capability. The isolated cloud executor
does not grant it; qualification there must not be reported as this proof.
All OAuth keys, source grants, workspaces and databases are disposable fixtures.
Only physical provider execution is inert. No installed runtime is activated.
"""
from __future__ import annotations

import asyncio
import copy
import dataclasses
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from common import coo_requester_return_contract as wire
from integrations.executive_mcp import server
from integrations.hermes_harness import native_executive_consumer as consumer
from integrations.hermes_harness import native_tool_registration as native
from integrations.hermes_harness.tests.test_native_executive_consumer import publication_document
from integrations.mastermind_executive_app.coo_binding import principal_frame
from tests import test_hermes_selected_child_ingress as ingress
from tests.test_coo_requester_return_contract import enable_disposable_requester_contract
from tests.test_hermes_selected_child_dispatch import _settle, _claim_events

rsa_key = ingress.rsa_key


def _receipts(runtime):
    with runtime.store.read() as connection:
        return list(connection.execute("SELECT * FROM events WHERE event_type=?", (wire.CONSUMPTION_EVENT,)))


def _publication(host):
    row, fact, authority = host.host.source.snapshot(ingress.WORK_REF)
    principal = dataclasses.asdict(fact)
    principal.pop("principal_binding_digest")
    principal["scopes"] = list(principal["scopes"])
    return consumer.publication_from_document(publication_document(
        schema=consumer.REQUESTER_RETURN_CONSUMER_SCHEMA,
        tools_schema_digest=consumer.REQUESTER_RETURN_TOOLS_SCHEMA_DIGEST,
        work_ref=ingress.WORK_REF, command=host.target.children[0].command_id,
        job_id=host.work.job_id, root_job_id=host.root.job_id,
        target_digest=host.target.material_digest(),
        principal=principal, principal_binding_digest=fact.principal_binding_digest,
        mission_authority_ref=authority.mission_authority_ref,
        authority_generation_digest=authority.authority_generation_digest,
        capability_profile_digest=authority.capability_profile_digest,
        mcp={"server": consumer.CONSUMER_MCP_SERVER, "url": "http://127.0.0.1/mcp/coo",
             "client_id": ingress.CLIENT, "scope": " ".join(fact.scopes),
             "server_name": "mastermind-executive-coo", "server_version": "1.0.0"}))


@pytest.mark.parametrize("boundary,leaf_depth", [
    ("normal", 1), ("normal", 2), ("normal", 3), ("changed_digest", 1),
    ("revoked_grant", 1), ("lost_response", 1),
])
def test_native_sdk_explicit_api_requester_ack_uses_original_control_transaction(tmp_path, rsa_key, monkeypatch, boundary, leaf_depth):
    original_intent = ingress._coo_intent
    # The source work reference is present at actual root admission. Never
    # repair a retained event or infer it from the later model request.
    monkeypatch.setattr(ingress, "_coo_intent", lambda config, name:
        {**original_intent(config, name), "workstream": ingress.WORK_REF})
    if leaf_depth > 1:
        def admitted_nested_leaf(service, root):
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
                children = service.runtime.jobs.admit_cycle_plan(coordinator.job_id,
                    command_id=f"coo-cycle:{coordinator.job_id}:admit-plan:{planned.attempt.attempt_id}")
                coordinator = children[0]
            return coordinator
        monkeypatch.setattr(ingress, "_admit_work_child", admitted_nested_leaf)

    async def exercise():
        with tempfile.TemporaryDirectory(prefix="mmx-coo-ack-", dir="/tmp") as directory:
            async with ingress._control(tmp_path, Path(directory), name=f"requester-{boundary}-{leaf_depth}") as host:
                enable_disposable_requester_contract(host.host, host.authority_config,
                    tmp_path / "selected-child-authority" / "capabilities.json")
                settings, token = await ingress._installed_app(host, rsa_key, socket_path=host.socket)
                settings = dataclasses.replace(settings, catalogue_provider=lambda principal, work_ref=None:
                    host.host.source.catalogue_for_principal(principal_frame(principal), work_ref=work_ref))
                app = server.build_web_ceo_v2_with_coo_mcp_app(settings.executive,
                    coo_settings=settings, audit_sink=ingress.app_fixture.Sink())
                publication = _publication(host)
                async with app._app.router.lifespan_context(app._app):
                    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                        base_url="http://127.0.0.1", headers={"authorization": "Bearer " + token}) as http_client:
                        async with streamable_http_client("http://127.0.0.1/mcp/coo", http_client=http_client) as (read, write, _):
                            async with ClientSession(read, write) as session:
                                initialized = await session.initialize()
                                assert initialized.serverInfo.name == "mastermind-executive-coo"
                                listed = await session.list_tools()
                                assert consumer.tools_schema_digest(listed.tools) == consumer.REQUESTER_RETURN_TOOLS_SCHEMA_DIGEST
                                owner = SimpleNamespace(session=session, _rpc_lock=asyncio.Lock(), _inflight_tasks=set())
                                caller = consumer._NativeMcpCaller(server=owner, session=session,
                                    loop=asyncio.get_running_loop(), timeout=30.0, currentness=lambda: True)
                                binding = await asyncio.to_thread(consumer.qualify_executive_consumer,
                                    publication=publication, caller=caller, profile_id="mmsecretary",
                                    session_id="original-native-session", instance_id="original-instance",
                                    authority_epoch=1, task_id="original-task", currentness=lambda: True)
                                assert binding.requester_returns is True
                                handler = native.native_delegate_handler(binding)
                                async def call(arguments, **caller_changes):
                                    actual_caller = {"session_id": "original-native-session", "task_id": "original-task"}
                                    actual_caller.update(caller_changes)
                                    return json.loads(await asyncio.to_thread(handler, arguments, **actual_caller))
                                command = publication.command
                                assert not _receipts(host.service.runtime)
                                submitted = await call({"action": "selected_child_submit", "command": command})
                                assert submitted["state"] in {"ACTIVE", "COMPLETED"}, submitted
                                claim = host.service.runtime.store.get_event_by_command_id(command)
                                assert claim.payload["selected_child_requester"]["context"]["principal_binding_digest"] == publication.principal_binding_digest
                                host.finish_gate.set()
                                await _settle(host.service)
                                observed = await call({"action": "selected_child_status", "command": command})
                                assert observed["state"] == "COMPLETED", observed
                                descriptor = observed["requester_return"]
                                assert descriptor["root_job_id"] == host.root.job_id
                                assert descriptor["parent_job_id"] == host.work.parent_job_id
                                assert host.work.depth == leaf_depth
                                assert descriptor["command_id"] == f"coo-cycle:{host.work.parent_job_id}:dispatch:{host.work.job_id}:attempt:1"
                                assert descriptor["consumption"] is None and not _receipts(host.service.runtime)
                                request = {"action": wire.ACK_ACTION, "command": command, "result": descriptor}
                                # Native caller validation remains before the RPC.
                                foreign = await call(request, session_id="foreign-native-session")
                                assert foreign["state"] == "REFUSED" and not _receipts(host.service.runtime)
                                if boundary == "changed_digest":
                                    wrong = copy.deepcopy(request)
                                    wrong["result"]["result_envelope_digest"] = "f" * 64
                                    refused = await call(wrong)
                                    assert refused["state"] == "REFUSED", refused
                                    assert not _receipts(host.service.runtime)
                                elif boundary == "revoked_grant":
                                    host.authority_config["missions"][0]["enabled"] = False
                                    refused = await call(request)
                                    assert refused["state"] in {"REFUSED", "EFFECT_UNKNOWN"}, refused
                                    assert not _receipts(host.service.runtime)
                                    return
                                elif boundary == "lost_response":
                                    original_ack = host.service.acknowledge_selected_child_result
                                    async def lose_original_reply(*args, **kwargs):
                                        await original_ack(*args, **kwargs)
                                        raise OSError("original acknowledgment response lost after commit")
                                    monkeypatch.setattr(host.service, "acknowledge_selected_child_result", lose_original_reply)
                                result = await call(request)
                                if boundary == "lost_response":
                                    assert result["state"] == "EFFECT_UNKNOWN", result
                                    assert "requester_return" not in result
                                else:
                                    assert result["state"] == "COMPLETED", result
                                    assert result["requester_return"]["consumption"] is not None
                                reconciled = await call({"action": "selected_child_status", "command": command})
                                assert reconciled["state"] == "COMPLETED", reconciled
                                assert wire.identity(reconciled["requester_return"]) == wire.identity(descriptor)
                                assert reconciled["requester_return"]["consumption"] is not None
                                assert reconciled["requester_return"]["parent_consumed"] is False
                                assert reconciled["requester_return"]["acceptance"] == "not_accepted"
                                assert len(_receipts(host.service.runtime)) == 1
                                assert len(_claim_events(host.service.runtime, host.work.job_id)) == 1
                                assert host.service.runtime.jobs.get_job(host.work.job_id).attempt_count == 1
    asyncio.run(exercise())
