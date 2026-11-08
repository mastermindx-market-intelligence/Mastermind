"""Actual Fresh seal -> original private native port -> cold donor JSONL content.

Installed artifact/process/provider seams remain explicitly inert.
Signed HTTP, compiled native routing and original Worker/binding joins are real.
Runtime root, Attempt, result seal, source references, private frame, donor
Gateway and the original held native writer are real.
"""
import asyncio
import base64
import copy
import dataclasses
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import time
import tempfile

import pytest

from common import project_conversation_read_contract as read_wire
from integrations.deepseek_harness.native_protocol import NativeClaim, NativeResult, NativeTerminal
from integrations.deepseek_harness.native_read_port import OwnedNativeReadPort
from integrations.session_bridge.deepseek_native import (
    DeepSeekNativeAssociation, DeepSeekNativeReadSource, DeepSeekNativeSession, principal_namespace,
)
from integrations.session_bridge.installed import build_runtime_session_bridge
from integrations.mastermind_executive_app.project_conversation_transport import validate_result, ProjectConversationReadClient
from integrations.mastermind_executive_app.gateway import CeoIngressClient
from integrations.business_mcp_auth.contracts import VerifiedPrincipal
from tests.test_dsh_native_fresh_http import native_mount, native_post, rsa_key
from tests.test_project_conversation_transport import exchange
from tests.test_mastermind_os_session_transport import make_app
from common.executive_workspace_contract import FRAME_SCHEMA, FRAME_SCHEMA_V2, PRINCIPAL_KEYS
from control_plane.principal_projection import neutral_principal_projection
from test_dsh_native_runtime_result import _NativeTurnAdapter

REPO = Path(__file__).resolve().parents[1]


@pytest.mark.skipif(not os.environ.get("DSH_SOURCE"), reason="exact clean donor required")
def test_original_native_fresh_result_reassembles_actual_donor_content_without_replay(tmp_path, monkeypatch, rsa_key):
    donor = Path(os.environ["DSH_SOURCE"]).resolve(strict=True)
    node = os.environ.get("DSH_NODE") or shutil.which("node")
    assert node
    state = {}
    answer = "Original answer — 原样保留 🧭\n" * 2400
    original_begin = _NativeTurnAdapter.begin_turn

    async def run():
        async with native_mount(tmp_path, rsa_key, monkeypatch) as (
                app, token, workspace_token, service, runtime, request, adapters, client, sink):
            request = {**request, "operation_key": "mmos-native-create-" + "a" * 40}
            verified = await app._executive._verified_binding(token)
            assert type(verified) is VerifiedPrincipal
            principal = neutral_principal_projection(**dataclasses.asdict(verified))
            owner = service._ceo_ingress_app_binding.fresh_conversation_provider_factory(runtime)
            workspace_principal = await app._workspace_principal(workspace_token)
            assert type(workspace_principal) is VerifiedPrincipal
            workspace_frame = {key: list(workspace_principal.scopes) if key == "scopes" else getattr(workspace_principal, key)
                for key in PRINCIPAL_KEYS}
            backend = owner._app.workspace_read_provider_factory(runtime)
            programs_request = dict(schema=FRAME_SCHEMA, operation="programs", selection=None, principal=workspace_frame)
            from control_plane import chairman_control_room as compositor
            from scripts import chairman_control_room as catalogue_cache
            from tests.test_workspace_read_service import STAMP
            catalogue_owners, catalogue_clock = service._fixture_fresh_owner._fixture_catalogue
            def publish_catalogue():
                _public_jobs, projected_jobs, error = compositor._read_runtime_jobs_from_runtime(runtime)
                assert error is None
                doc = compositor.compose_control_room(inbox=None, boot_packet=None, active_builds=None,
                    bindings=None, binding_problems=(), generated_at=STAMP,
                    agent_os_state=dict(schema="agent_os_state.v1", generated_at=STAMP,
                        workstreams=[dict(key=request["work_ref"].removeprefix("WS:"), title="One",
                            status="active", owner="astra-meta-ceo")]),
                    runtime_jobs=projected_jobs)
                with catalogue_owners[0].state_lock:
                    catalogue_owners[0].state_published_seq += 1
                    catalogue_owners[0].state_cache["doc"] = doc
                    catalogue_cache._publish_source_validity(catalogue_owners[0], doc,
                        tuple(catalogue_clock), tuple(catalogue_clock))
            publish_catalogue()
            programs_before = await backend.handle_frame(programs_request)
            assert programs_before["ok"]
            def begin(adapter, **kwargs):
                observed = original_begin(adapter, **kwargs)
                assert adapter.calls == 1
                attempt = runtime.attempts.get_attempt(kwargs["turn"].attempt_id)
                child = runtime.jobs.get_job(attempt.job_id)
                association = DeepSeekNativeAssociation(work_ref=request["work_ref"], root_job_id=child.root_job_id,
                    native_session_id=adapter.f.session_id, owner_principal_scope=principal_namespace(principal),
                    composition_sha256="3"*64, native_package_sha256="4"*64)
                left, right = socket.socketpair()
                port = OwnedNativeReadPort(left, association_sha256=association.digest)
                state.update(port=port, association=association, live=True)
                def current():
                    if not state["live"]:
                        raise ValueError("fixture source revoked")
                source = DeepSeekNativeReadSource(association, port, require_current=current)
                native = DeepSeekNativeSession(source, read_guard=current)
                bridge = build_runtime_session_bridge(runtime,
                    dialogue_socket_path=tmp_path/"unused-dialogue.sock", deepseek_session=native)
                object.__setattr__(owner._app, "session_bridge_provider_factory", lambda value: bridge if value is runtime else None)
                ready, report = tmp_path/"ready.json", tmp_path/"report.json"
                spec, log = tmp_path/"spec.json", tmp_path/"native.log"
                spec.write_text(json.dumps(dict(fd=right.fileno(), association=association.document(),
                    ready=str(ready), report=str(report), answer=answer, question=request["message"],
                    laterAnswer="A different later answer must never substitute", runtimeContext=True)))
                env = dict(os.environ, DSH_SOURCE=str(donor), MMX_DSH_NATIVE_READ_FIXTURE=str(spec))
                with log.open("wb") as output:
                    process = subprocess.Popen([node, str(donor/"node_modules/vitest/vitest.mjs"),
                        "run", "--pool", "threads", "--config", "vitest.host.config.mts",
                        "native.executive.fixture.test.ts"],
                        cwd=REPO/"integrations/deepseek_harness/company_plugin", env=env,
                        pass_fds=(right.fileno(),), stdout=output, stderr=subprocess.STDOUT)
                right.close()
                state.update(process=process, log=log, report=report)
                deadline = time.monotonic()+40
                while not ready.exists() and process.poll() is None and time.monotonic()<deadline:
                    time.sleep(0.03)
                assert ready.exists(), log.read_text(errors="replace")[-6000:]
                actual = json.loads(ready.read_text())
                assert actual["session_id"] == adapter.f.session_id
                claim = NativeClaim(kwargs["operation_id"].command_id, 1, actual["session_id"],
                    actual["message_id"], 1, 0)
                adapter.result = NativeResult("end_turn", NativeTerminal(claim.operation_id, 1, claim,
                    actual["through_seq"], 2, 2))
                return observed
            monkeypatch.setattr(_NativeTurnAdapter, "begin_turn", begin)
            try:
                code, preview = await native_post(app, "preview", request, token, workspace_token)
                assert code == 200 and preview["ok"]
                create_request = {**request, "preview_digest": preview["data"]["preview"]["digest"]}
                code, created_reply = await native_post(app, "create", create_request, token, workspace_token)
                assert code == 200 and created_reply["ok"]
                created = created_reply["data"]
                assert created["state"] == "CREATED"
                lookup = {key: request[key] for key in ("work_ref", "operation_key")}
                code, initial = await native_post(app, "read", lookup, token)
                assert code == 200 and initial["ok"]
                code, status = await native_post(app, "status", lookup, token)
                assert code == 200 and status["ok"] and status["data"]["state"] == "CREATED"
                code, recovered_reply = await native_post(app, "recover", lookup, token, workspace_token)
                assert code == 200 and recovered_reply["ok"] and recovered_reply["operation"] == "recover"
                assert recovered_reply["data"]["state"] == "CREATED"
                assert recovered_reply["data"]["session"] == created["session"]
                assert recovered_reply["data"]["locator"] == created["locator"]
                assert recovered_reply["data"]["result"] == status["data"]["result"]
                assert len(adapters) == adapters[0].start_calls == adapters[0].calls == 1
                code, executive_context = await exchange(app._executive, token, operation="context",
                    path="/os/executive/context", body=b"{}")
                assert code == 200 and executive_context["principal_scope"] == principal_namespace(principal)
                session_app, unused_peer, clock, audit = make_app(rsa_key)
                clock[0] = app._executive._clock()
                code, history_context = await exchange(session_app, token, operation="history_context",
                    path="/os/executive/session/history-context",
                    body=json.dumps({"selection": {"work_ref": request["work_ref"]}}).encode())
                assert code == 200 and history_context["ok"] and unused_peer.calls == []
                reader = ProjectConversationReadClient(app._client.socket_path, client=CeoIngressClient())
                catalogue = await reader.read(verified, "fresh_references", {"work_ref": request["work_ref"]})
                reference = catalogue["entries"][0]["reference"]
                window = await reader.read(verified, "fresh_read", reference)
                assert window["initial_result"] == initial["data"]["result"]
                consume_request = {**lookup, "initial_digest": initial["data"]["result"]["digest"]}
                code, consume_status_before = await native_post(app, "consume_status", consume_request, token)
                assert code == 200 and consume_status_before["ok"]
                code, consumed = await native_post(app, "consume", consume_request, token, workspace_token)
                assert code == 200 and consumed["ok"] and consumed["data"]["can_send"]
                code, consume_status = await native_post(app, "consume_status", consume_request, token)
                assert code == 200 and consume_status["ok"] and consume_status["data"]["state"] == "CONSUMED"
                code, read_after_consumed = await native_post(app, "read", lookup, token)
                assert code == 200 and read_after_consumed["ok"]
                catalogue_after_consumed = await reader.read(verified, "fresh_references", {"work_ref": request["work_ref"]})
                window_after_consumed = await reader.read(verified, "fresh_read", reference)
                publish_catalogue()
                programs = await backend.handle_frame(programs_request)
                mission = await backend.handle_frame(dict(schema=FRAME_SCHEMA_V2, operation="mission_v3",
                    selection={"work_ref":request["work_ref"], "root_job_id":created["locator"]["root_job_id"]},
                    principal=workspace_frame))
                assert programs["ok"] and mission["ok"]
                ref = window["initial_result"]["reference"]
                before = [event.to_dict() for event in runtime.events.list_events()]
                raw, offset, digest, parts = bytearray(), 0, None, []
                while True:
                    selected = {**reference, "content":dict(native_ref=ref, offset_bytes=offset, expected_sha256=digest)}
                    assert read_wire.arguments(selected, "fresh_read") == selected
                    result = await reader.read(verified, "fresh_read", selected)
                    assert validate_result(result, "fresh_read", selected) == result
                    assert len(json.dumps(result, ensure_ascii=False).encode()) < read_wire.MAX_RESPONSE_BYTES
                    parts.append(dict(request=selected, response=result))
                    native = result["native"]
                    assert native["state"] == "CONTENT" and native["claim"]["sessionId"] == state["association"].native_session_id
                    part = native["content"]
                    fragment = base64.b64decode(part["data"], validate=True)
                    assert len(fragment) <= 4096
                    raw.extend(fragment)
                    digest = digest or part["sha256"]
                    assert digest == part["sha256"]
                    if part["next_offset_bytes"] is None:
                        assert len(raw) == part["total_bytes"]
                        break
                    offset = part["next_offset_bytes"]
                    assert offset == len(raw)
                assert len(parts)>20 and hashlib.sha256(raw).hexdigest()==digest
                body = json.loads(raw)
                records = body["records"]
                actual_answer = "".join(block["text"] for row in records if row["event"]["type"]=="assistant/message"
                    for block in row["event"]["data"]["message"]["content"] if block["type"]=="text")
                assert actual_answer == answer
                assert "A different later answer" not in raw.decode()
                assert any(row["event"].get("data",{}).get("source",{}).get("kind")=="runtime-context" for row in records)
                assert all(row["event"]["seq"] <= native["turn_end_seq"] for row in records)
                assert adapters[0].calls == adapters[0].start_calls == len(adapters) == 1
                assert [event.to_dict() for event in runtime.events.list_events()] == before
                original = parts[0]["request"]
                foreign = copy.deepcopy(original)
                foreign["content"]["native_ref"]["seal_digest"] = "f"*64
                with pytest.raises(ValueError):
                    await owner.read_reference(principal, foreign, guard=lambda:True)
                state["live"] = False
                with pytest.raises(ValueError):
                    await owner.read_reference(principal, original, guard=lambda:True)
                state["live"] = True
                recovered = await owner.read_reference(principal, original, guard=lambda:True)
                assert recovered == parts[0]["response"]  # Passive original recovery, no new turn.
                assert adapters[0].calls == 1
                state["port"].retire()
                assert state["process"].wait(timeout=40)==0, state["log"].read_text(errors="replace")[-6000:]
                report = json.loads(state["report"].read_text())
                assert report["original_writer_held"] and report["native_files_before"]==report["native_files_after"]
                assert report["provider_calls"]==report["agent_create_calls"]==report["agent_resume_calls"]==0
                assert report["native_session_promoted"] is False
                exported = dict(schema="mastermind.native_fresh_app_fixture.v1",
                    seams=["temporary compiled native policy/router and fixture Worker registration",
                        "actual installed binding owner, signed dual-resource HTTP and private Unix peer",
                        "actual original Runtime, result seal, history and donor reader",
                        "test-generated native history; inert process/provider; no installed account proof",
                        "actual context-only history auth leaf; no Session lifecycle or target enumeration"],
                    request=request, create_request=create_request, preview=preview, create=created_reply,
                    read=initial, status=status, recover=recovered_reply, executive_context=executive_context, history_context=history_context,
                    programs_before=programs_before, programs=programs, mission=mission,
                    clock=dict(verified_at_seconds=clock[0], exported_at_seconds=app._executive._clock(),
                        verified_expiry=verified.expires_at),
                    catalogue=catalogue, window=window, answer=answer, fragments=parts, report=report,
                    consume_request=consume_request, consume_status_before=consume_status_before, consume=consumed,
                    consume_status=consume_status, read_after_consumed=read_after_consumed,
                    catalogue_after_consumed=catalogue_after_consumed, window_after_consumed=window_after_consumed)
                if os.environ.get("MMX_NATIVE_CONTENT_EXPORT"):
                    Path(os.environ["MMX_NATIVE_CONTENT_EXPORT"]).write_text(json.dumps(exported, ensure_ascii=False)+"\n")
                print("NATIVE_FRESH_CONTENT_PROOF "+json.dumps(dict(
                    fragments=len(parts), content_bytes=len(raw), content_sha256=digest,
                    original_turns=adapters[0].calls, provider_calls=0, runtime_unchanged=True,
                    native_unchanged=True, installed=False)))
            finally:
                if "server" in state:
                    state["server"].close(); await state["server"].wait_closed()
                if "private_dir" in state: state["private_dir"].cleanup()
                if "port" in state: state["port"].retire()
                if "process" in state and state["process"].poll() is None:
                    state["process"].terminate(); state["process"].wait(timeout=10)
    asyncio.run(run())
