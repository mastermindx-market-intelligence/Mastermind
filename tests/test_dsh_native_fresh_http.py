"""Signed native-v2 BFF -> real Unix peer -> original owner/Runtime.

Installed policy, provider process and account are explicit inert seams from
native_case. The HTTP verifiers, private socket, kernel peer, original dispatch,
receipt currentness and Runtime writes are real. No production admission claim.
"""
import asyncio
from contextlib import asynccontextmanager
import dataclasses
import hashlib
import json
import os
from pathlib import Path
import tempfile
import threading

import pytest

from common import fresh_conversation_contract as wire
from control_plane.fresh_conversation import FreshConversationOwner
from integrations.mastermind_executive_app.fresh_conversation_transport import (
    FreshConversationTransportApp, InstalledFreshConversationClient,
)
from integrations.mastermind_executive_app.gateway import CeoIngressClient
from tests import test_mastermind_executive_app_asgi as auth
from tests.test_fresh_conversation import cleanup
from tests.test_fresh_conversation_http import mounted, post, rsa_key
from tests.test_dsh_native_fresh_conversation import native_case, active_dispatch


async def native_post(app, operation, arguments, token, workspace=None, *, change=None):
    path = next(path for path, candidate in wire.NATIVE_ROUTES.items() if candidate == operation)
    return await post(app, operation, arguments, token, workspace,
        change={"path": path, "raw_path": path.encode(), **(change or {})})


@asynccontextmanager
async def native_mount(tmp_path, rsa_key, monkeypatch):
    original, token, workspace, service, runtime, request, adapters, _, sink = await mounted(
        tmp_path, rsa_key, monkeypatch,
        case_factory=lambda principal: native_case(tmp_path, monkeypatch, principal))
    policy = auth._submit_policy()
    expected = (policy.policy_id, hashlib.sha256(policy.issuer.encode()).hexdigest(), policy.resource)

    def provider(selected):
        if selected is not runtime:
            raise ValueError("fixture namespace changed")
        return FreshConversationOwner(service, expected_policy=expected)

    service._ceo_ingress_app_binding = dataclasses.replace(
        service._ceo_ingress_app_binding, fresh_conversation_provider_factory=provider)
    with tempfile.TemporaryDirectory(prefix="native-fresh-ingress-", dir="/tmp") as directory:
        path = Path(directory) / "app.sock"
        server = await asyncio.start_unix_server(service._handle_ceo_ingress_connection,
            path=path, limit=service._ceo_ingress_stream_ceiling() + 1)
        client = CeoIngressClient()
        app = FreshConversationTransportApp(original._inner, executive=original._executive,
            workspace_config=original._workspace, workspace_verifier=original._workspace_verifier,
            client=InstalledFreshConversationClient(path, client))
        try:
            yield app, token, workspace, service, runtime, request, adapters, client, sink
        finally:
            pause = getattr(service, "_fixture_collect_pause", None)
            if pause is not None:
                pause.set()
            await cleanup(service)
            server.close()
            await server.wait_closed()


async def native_ready(app, token, workspace, request):
    code, preview = await native_post(app, "preview", request, token, workspace)
    assert code == 200 and preview["ok"], preview
    create = {**request, "preview_digest": preview["data"]["preview"]["digest"]}
    code, created = await native_post(app, "create", create, token, workspace)
    assert code == 200 and created["ok"] and created["data"]["state"] == "CREATED", created
    selected = {key: request[key] for key in ("work_ref", "operation_key")}
    code, initial = await native_post(app, "read", selected, token)
    assert code == 200 and initial["ok"] and initial["data"]["effect"] == "NONE", initial
    consume = {**selected, "initial_digest": initial["data"]["result"]["digest"]}
    code, consumed = await native_post(app, "consume", consume, token, workspace)
    assert code == 200 and consumed["ok"] and consumed["data"]["can_send"], consumed
    return selected, consume, created, initial, consumed


def test_native_signed_large_input_original_send_and_lost_reply_recovery(tmp_path, rsa_key, monkeypatch):
    async def run():
        async with native_mount(tmp_path, rsa_key, monkeypatch) as (
                app, token, workspace, service, runtime, request, adapters, client, sink):
            request = {**request, "message": "🧭" * (wire.NATIVE_MESSAGE_BYTES // 4)}
            selected, consume, created, initial, consumed = await native_ready(app, token, workspace, request)
            dispatch = service._native_operator_dispatch
            send = {**consume, "turn_key": "native-http-original", "message": "  原文第二轮\nKeep my whitespace.  "}
            code, preview = await native_post(app, "turn_preview", send, token, workspace)
            assert code == 200 and preview["ok"] and preview["data"]["state"] == "TURN_READY", preview
            send["preview_digest"] = preview["data"]["preview_digest"]
            original_send = client._send_frame
            lost = []

            async def lose_original_reply(socket_path, frame, **options):
                value = await original_send(socket_path, frame, **options)
                if frame["operation"] == "turn":
                    assert not lost
                    assert value.ok and value.result["data"]["state"] == "RECORDED", value
                    lost.append(value.result)
                    raise OSError("inert delivery failure after the actual private reply")
                return value

            monkeypatch.setattr(client, "_send_frame", lose_original_reply)
            code, unknown = await native_post(app, "turn", send, token, workspace)
            assert code == 202 and unknown["error"]["code"] == "effect_unknown", unknown
            before = runtime.events.list_events()
            turn_ref = {**selected, "turn_key": send["turn_key"]}
            recovered = {}
            for operation in ("turn_status", "turn_read"):
                code, value = await native_post(app, operation, turn_ref, token)
                assert code == 200 and value["ok"] and value["data"]["state"] == "RECORDED", value
                assert value["data"]["effect"] == "NONE"
                assert value["data"]["result"] == lost[0]["data"]["result"]
                recovered[operation] = value
            code, consumption = await native_post(app, "consume_status", consume, token)
            assert code == 200 and consumption["data"]["state"] == "CONSUMED", consumption
            code, reopened = await native_post(app, "status", selected, token)
            assert code == 200 and reopened["ok"] and reopened["data"]["can_send"], reopened
            assert runtime.events.list_events() == before
            assert service._native_operator_dispatch is dispatch
            assert len(adapters) == adapters[0].start_calls == 1
            assert adapters[0].calls == 2 and adapters[0].prompts == [request["message"], send["message"]]
            assert len(runtime.jobs.list_jobs()) == 2 and len(runtime.attempts.list_attempts()) == 1
            assert sink.events
            destination = os.environ.get("MMX_NATIVE_TRANSPORT_EXPORT")
            if destination:
                payload = {"schema": "mastermind.native_fresh_transport_fixture.v1",
                    "seams": ["inert installed policy/admission", "inert provider/process",
                        "actual signed RS256 Executive and Workspace verifiers",
                        "actual private Unix socket/kernel peer/owner/Runtime",
                        "inert delivery failure after actual Send reply"],
                    "request": request, "create": created, "initial": initial, "consume": consumed,
                    "send": send, "turn_preview": preview, "turn": lost[0], "unknown": unknown,
                    **recovered, "consume_status": consumption, "status": reopened,
                    "counts": {"jobs": 2, "attempts": 1, "adapters": 1, "provider_turns": 2}}
                with Path(destination).open("x", encoding="utf-8") as output:
                    json.dump(payload, output, ensure_ascii=False, indent=2)
                    output.write("\n")
    asyncio.run(run())


def test_native_signed_stop_resume_keep_original_session_and_receipts(tmp_path, rsa_key, monkeypatch):
    async def run():
        async with native_mount(tmp_path, rsa_key, monkeypatch) as (
                app, token, workspace, service, runtime, request, adapters, client, sink):
            selected, consume, _, _, _ = await native_ready(app, token, workspace, request)
            original = service._native_operator_dispatch
            session = original.retained.session
            send = {**consume, "turn_key": "native-http-stoppable", "message": "Stop this original turn."}
            code, preview = await native_post(app, "turn_preview", send, token, workspace)
            assert code == 200 and preview["ok"], preview
            send["preview_digest"] = preview["data"]["preview_digest"]
            pause = service._fixture_collect_pause = threading.Event()
            task = asyncio.create_task(native_post(app, "turn", send, token, workspace))
            try:
                await asyncio.wait_for(active_dispatch(service, task), 15)
                code, active = await native_post(app, "status", selected, token)
                assert code == 200 and active["data"]["can_stop"], active
                stop = {**selected, "stop_key": "native-http-g1-stop",
                    "turn_id": active["data"]["active_turn"]["turn_id"],
                    "binding_digest": active["data"]["session"]["binding_digest"]}
                code, stopped = await native_post(app, "stop", stop, token, workspace)
                assert code == 200 and stopped["ok"] and stopped["data"]["state"] == "APPLIED", stopped
                code, sent = await asyncio.wait_for(task, 15)
                assert code == 200 and sent["ok"] and sent["data"]["state"] == "RECORDED", sent
                code, idle = await native_post(app, "status", selected, token)
                assert code == 200 and idle["data"]["state"] == "IDLE" and idle["data"]["can_resume"], idle
                before = runtime.events.list_events()
                code, stop_read = await native_post(app, "stop_status",
                    {**selected, "stop_key": stop["stop_key"]}, token)
                assert code == 200 and stop_read["data"]["receipt"] == stopped["data"]["receipt"], stop_read
                assert stop_read["data"]["effect"] == "NONE" and runtime.events.list_events() == before
                resume = {**selected, "resume_key": "native-http-original-g2",
                    "expected_result_digest": idle["data"]["head_result"]["digest"]}
                code, ready = await native_post(app, "resume_preview", resume, token, workspace)
                assert code == 200 and ready["ok"] and ready["data"]["state"] == "RESUME_READY", ready
                resume["preview_digest"] = ready["data"]["preview_digest"]
                code, resumed = await native_post(app, "resume", resume, token, workspace)
                assert code == 200 and resumed["ok"] and resumed["data"]["state"] == "APPLIED", resumed
                before = runtime.events.list_events()
                code, resume_read = await native_post(app, "resume_status",
                    {**selected, "resume_key": resume["resume_key"]}, token)
                assert code == 200 and resume_read["data"]["receipt"] == resumed["data"]["receipt"], resume_read
                assert resume_read["data"]["effect"] == "NONE" and runtime.events.list_events() == before
                assert service._native_operator_dispatch is original
                second = original.retained.session
                assert second.epoch == session.epoch and second.generation.generation_number == 2
                assert second.observation.provider_session_id == session.observation.provider_session_id
                assert adapters[0].resume_calls == adapters[0].start_calls == adapters[0].interrupt_calls == len(adapters) == 1
                assert len(runtime.attempts.list_attempts()) == 1
            finally:
                pause.set()
                if not task.done():
                    await asyncio.gather(task, return_exceptions=True)
    asyncio.run(run())


@pytest.mark.parametrize("fault", ["missing_workspace", "wrong_resource", "invalid_message", "extra_session",
    "path_alias", "query", "legacy_route_large_message"])
def test_native_route_and_authority_faults_do_not_admit(tmp_path, rsa_key, monkeypatch, fault):
    async def run():
        async with native_mount(tmp_path, rsa_key, monkeypatch) as (
                app, token, workspace, service, runtime, request, adapters, client, sink):
            change = None
            if fault == "missing_workspace":
                workspace = None
            elif fault == "wrong_resource":
                workspace = token
            elif fault == "invalid_message":
                request = {**request, "message": "x" * (wire.NATIVE_MESSAGE_BYTES + 1)}
            elif fault == "extra_session":
                request = {**request, "session_id": "caller-cannot-choose"}
            elif fault == "path_alias":
                change = {"raw_path": b"/os/executive/conversation/v2/%70review"}
            elif fault == "query":
                change = {"query_string": b"version=v1"}
            elif fault == "legacy_route_large_message":
                request = {**request, "message": "x" * 70000}
                path = "/os/executive/conversation/preview"
                change = {"path": path, "raw_path": path.encode()}
            before = runtime.events.list_events()
            code, result = await native_post(app, "preview", request, token, workspace, change=change)
            assert code in {400, 401, 403, 404}, result
            assert not runtime.jobs.list_jobs() and not adapters and runtime.events.list_events() == before
    asyncio.run(run())


def test_native_signed_recovery_rejoins_original_call_with_fresh_auth_only(tmp_path, rsa_key, monkeypatch):
    from tests.test_dsh_native_fresh_recovery import delay_original
    async def run():
        async with native_mount(tmp_path, rsa_key, monkeypatch) as (
                app, token, workspace, service, runtime, request, adapters, client, sink):
            state = delay_original(service, monkeypatch, ordinal=1)
            request = {**request, "operation_key": "mmos-native-create-"+"a"*40}
            selected = {key: request[key] for key in ("work_ref", "operation_key")}
            code, preview = await native_post(app, "preview", request, token, workspace)
            assert code == 200 and preview["ok"]
            code, unknown = await native_post(app, "create",
                {**request, "preview_digest": preview["data"]["preview"]["digest"]}, token, workspace)
            assert code == 202 and not unknown["ok"], unknown
            original = service._native_operator_dispatch
            assert original is not None and original.pending_turn is not None and service._service_state == "READY"
            before = state["observations"]
            code, refused = await native_post(app, "recover", selected, token)
            assert code == 400 and refused["error"]["code"] == "invalid_input", refused
            assert state["observations"] == before
            code, passive = await native_post(app, "read", selected, token)
            assert code == 200 and passive["data"]["state"] == "RECONCILIATION_REQUIRED"
            assert state["observations"] == before
            state["ready"] = True
            code, recovered = await native_post(app, "recover", selected, token, workspace)
            assert code == 200 and recovered["ok"] and recovered["data"]["state"] == "CREATED", recovered
            assert service._native_operator_dispatch is original and original.pending_turn is None
            assert len(adapters) == adapters[0].start_calls == adapters[0].calls == 1
            initial = recovered["data"]["result"]
            consume = {**selected, "initial_digest": initial["digest"]}
            code, kept = await native_post(app, "consume", consume, token, workspace)
            assert code == 200 and kept["data"]["can_send"]
            state.update(ready=False, ordinal=2)
            send = {**consume, "turn_key": "mmos-native-turn-"+"b"*40, "message": "The original second input."}
            code, preview = await native_post(app, "turn_preview", send, token, workspace)
            assert code == 200 and preview["ok"]
            send["preview_digest"] = preview["data"]["preview_digest"]
            code, pending = await native_post(app, "turn", send, token, workspace)
            assert code == 200 and pending["data"]["state"] == "RECONCILIATION_REQUIRED", pending
            target = {**selected, "turn_key": send["turn_key"]}
            before = state["observations"]
            code, refused = await native_post(app, "turn_recover", target, token)
            assert code == 400 and refused["error"]["code"] == "invalid_input", refused
            assert state["observations"] == before
            code, still = await native_post(app, "turn_read", target, token)
            assert code == 200 and still["data"]["result"] is None and state["observations"] == before
            state["ready"] = True
            code, answer = await native_post(app, "turn_recover", target, token, workspace)
            assert code == 200 and answer["ok"] and answer["data"]["state"] == "RECORDED", answer
            assert service._native_operator_dispatch is original and original.pending_turn is None
            assert original.retained.native_result.seal_digest == answer["data"]["result"]["digest"]
            assert adapters[0].calls == 2 and adapters[0].prompts == [request["message"], send["message"]]
            assert adapters[0].stop_calls == adapters[0].cancel_calls == 0
            assert len(runtime.attempts.list_attempts()) == 1 and len(runtime.jobs.list_jobs()) == 2
            destination = os.environ.get("MMX_NATIVE_RECOVERY_EXPORT")
            if destination:
                payload = {"schema": "mastermind.native_fresh_recovery_fixture.v1",
                    "seams": ["inert installed policy, provider and process",
                        "actual signed RS256 Executive and Workspace authentication",
                        "actual private Unix socket, kernel peer, original Control/Supervisor/Runtime",
                        "original begin timeout followed by explicit claim/answer recovery; no second send"],
                    "samples": [
                        {"test": "signed-original-initial-recovery", "operation": "recover", "arguments": selected, "response": recovered},
                        {"test": "signed-original-followup-recovery", "operation": "turn_recover", "arguments": target, "response": answer}],
                    "counts": {"jobs": 2, "attempts": 1, "adapters": 1, "starts": 1, "provider_turns": 2}}
                with Path(destination).open("x", encoding="utf-8") as output:
                    json.dump(payload, output, ensure_ascii=False, indent=2)
                    output.write("\n")
    asyncio.run(run())
