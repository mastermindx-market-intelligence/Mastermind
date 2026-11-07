"""Actual enrolled-source guard is repeated at the existing durable COMMIT seam."""
import asyncio
import json
from pathlib import Path

import pytest

from tests.test_principal_dialogue_authority_guard import prepared
from tests.test_company_dialogue_principal_runtime_fence import Resolver, binding, runtime_child
from integrations.mastermind_company_principal_host import build_principal_company_dialogue_host
from integrations.mastermind_company_principal_runtime_fence import PRINCIPAL_RUNTIME_EVENT_TYPE


@pytest.mark.parametrize("movement", [None, "revoked", "root_moved", "owner_exception"])
def test_receiving_control_rechecks_after_ready_and_before_commit(tmp_path, monkeypatch, movement):
    authority, config, document, args = prepared(tmp_path, monkeypatch)
    runtime, root, child, attempt = runtime_child(tmp_path)
    document = json.loads(json.dumps(document).replace('"JOB-100"', json.dumps(root.job_id)))
    monkeypatch.setattr(authority.workspace, "read_mission_for_work_ref", lambda work: document)
    context = args["context"]
    actor = dict(binding(root, child, attempt).actor_ref)
    actor.update(principal_binding_digest=context.principal_binding_digest,
                 mission_authority_ref=context.mission_authority_ref,
                 authority_generation_digest=context.authority_generation_digest,
                 capability_profile_digest=args["capability_profile_digest"])
    bound = binding(root, child, attempt, actor_ref=actor, work_ref=context.work_ref)
    sent = []
    async def service(path, request, **kwargs):
        assert request["operation"] == "send_message"
        if movement == "revoked":
            config["missions"][0]["enabled"] = False
        elif movement == "root_moved":
            document["mission"]["root_job_id"] = "JOB-999"
        elif movement == "owner_exception":
            def unavailable(work):
                raise PermissionError("PRIVATE_CANARY /private/authority")
            monkeypatch.setattr(authority.workspace, "read_mission_for_work_ref", unavailable)
        await kwargs["before_write"]()
        sent.append(request["args"]["message"])
        message = sent[-1]
        return {"ok": True, "result": {"action": "CREATED",
            "message_key": message["message_key"], "fingerprint": message["fingerprint"]}}
    host = build_principal_company_dialogue_host(runtime=runtime,
        binding_resolver=Resolver(bound), socket_path=Path("/fixture/relay.sock"),
        service_call=service, principal_authority_guard=authority.guard_dialogue)
    result = asyncio.run(host.gateway.call("continue", {
        "instruction": "Continue this bounded child.", "stop_condition": "Return the evidence."}))
    events = [e for e in runtime.events.list_events() if e.event_type == PRINCIPAL_RUNTIME_EVENT_TYPE]
    assert (result["ok"], len(sent), len(events)) == ((True, 1, 1) if movement is None else (False, 0, 0))
    assert "PRIVATE_CANARY" not in json.dumps(result)


def test_host_rejects_async_authority_guard(tmp_path):
    runtime, root, child, attempt = runtime_child(tmp_path)
    async def unsupported(**facts):
        pass
    with pytest.raises(TypeError, match="synchronous"):
        build_principal_company_dialogue_host(runtime=runtime,
            binding_resolver=Resolver(binding(root, child, attempt)),
            socket_path=Path("/fixture/relay.sock"), principal_authority_guard=unsupported)
