"""Real authenticated MCP launch/recovery; disposable SQLite/Unix/Git, no execution."""
import asyncio
from contextlib import asynccontextmanager
import dataclasses
import hashlib
import json
import os
from pathlib import Path
import re
import sys

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).parent))
try:
    import test_mastermind_executive_app_asgi as fixture
finally:
    sys.path.pop(0)

from control_plane import ceo_intent, ceo_request, executive_ceo_ingress as ingress
from control_plane.executive_service import (
    CEO_WEB_CEO_V2_READ_SCHEMA, CeoIngressAppBinding, ExecutiveControlService,
)
from integrations.executive_mcp import server as transport
from integrations.executive_mcp.web_ceo import WebCeoV2InstalledExecutiveReaders
from integrations.mastermind_executive_app import gateway

rsa_key = fixture.rsa_key
short_socket_root = fixture.short_socket_root
PAYLOAD = {
    "operation_key": "mcp-launch-journey-001",
    "objective": "Read the disposable fixture and return evidence.",
    "department": "executive-infrastructure",
    "priority": 5,
    "execution_profile": "research_only",
    "workstream": "WS:ORIGINAL-LAUNCH",
}


class _Sink:
    def emit(self, event):
        pass


class _UnusedOwners:
    """Unrelated v3 capabilities must remain unreachable in this journey."""

    def __getattr__(self, name):
        return _unused_owner


def _unused_owner(*args, **kwargs):
    raise AssertionError("launch/status must not invoke MDM or session owners")


@asynccontextmanager
async def _connection(profile, settings):
    options = {"audit_sink": _Sink()}
    if profile == "web_ceo_v3":
        options.update(mdm_reader=_UnusedOwners(), session_target_projector=_unused_owner,
                       session_reply_handler=_unused_owner, session_summon_handler=_unused_owner)
    builder = getattr(transport, "build_" + profile + "_mcp_app")
    app = builder(settings, **options)
    async with app._app.router.lifespan_context(app._app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                     base_url="http://127.0.0.1") as client:
            yield client


async def _post(client, token, name, arguments):
    return await asyncio.wait_for(client.post(
        "/mcp",
        headers={"authorization": "Bearer " + token,
                 "accept": "application/json, text/event-stream",
                 "mcp-protocol-version": "2025-06-18"},
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/call",
              "params": {"name": name, "arguments": arguments}},
    ), 8)


async def _call(client, token, name, arguments):
    response = await _post(client, token, name, arguments)
    assert response.status_code == 200, response.text
    rpc = response.json()
    assert "error" not in rpc, rpc
    result = rpc["result"]
    return result, json.loads(result["content"][0]["text"])


def _assert_receipt_profile(receipt, strict_v2):
    assert receipt["schema"] == (ceo_intent.RECEIPT_SCHEMA_V2 if strict_v2 else ceo_intent.RECEIPT_SCHEMA)
    if strict_v2:
        assert receipt["work_ref"] == PAYLOAD["workstream"]
    else:
        assert "work_ref" not in receipt


@pytest.mark.parametrize("profile", ["web_ceo_v2", "web_ceo_v3"])
@pytest.mark.parametrize("lose_submit_reply", [False, True], ids=["accepted", "lost-reply"])
def test_real_launch_survives_reopen_without_another_submit(
    profile, lose_submit_reply, rsa_key, tmp_path, short_socket_root, strict_v2=False,
):
    mastermind_root, macro_root = tmp_path / "mastermind", tmp_path / "macro"
    mastermind_sha = fixture._git_repo(mastermind_root)
    (macro_root / "scripts").mkdir(parents=True)
    (macro_root / "scripts" / "agentos.py").write_text("")
    (macro_root / "agentos").mkdir()
    fixture._git_repo(macro_root)

    async def exercise():
        base = fixture._real_service(tmp_path, socket_root=short_socket_root,
                                     mastermind_root=mastermind_root, macro_root=macro_root)
        readers = WebCeoV2InstalledExecutiveReaders(
            repo_root=mastermind_root, macro_root=macro_root,
            runtime_root=base.config.runtime_root,
        )
        grounding = fixture._RealGitGroundingProvider(
            mastermind_root=mastermind_root, macro_root=macro_root,
        )
        source = {
            "schema_version": "mastermind.executive_dialogue_source/v1",
            "work_ref": PAYLOAD["workstream"],
            "commission_ref": {
                "repository": "mastermindx-market-intelligence/Mastermind",
                "commit": mastermind_sha,
                "path": "README.md",
                "content_sha256": hashlib.sha256((mastermind_root / "README.md").read_bytes()).hexdigest(),
            },
            "watch_mode": "turn_watch_v1",
        }
        source_state, source_calls = [source], []

        def source_provider(intent_id, work_ref):
            source_calls.append((intent_id, work_ref))
            return source_state[0]

        service = ExecutiveControlService(
            base.config, supervisor_factory=lambda runtime: fixture._NoExecutionSupervisor(),
            ceo_ingress_socket_path=short_socket_root / "real.sock",
            ceo_ingress_peer_uid=os.geteuid() + 1000,
            ceo_ingress_grounding_provider=grounding, ceo_ingress_armed=False,
            # Supplying a trusted host source selects strict v2; dispatch stays dormant.
            ceo_ingress_dialogue_source_provider=source_provider if strict_v2 else None,
            ceo_ingress_app_binding=CeoIngressAppBinding(
                peer_uid=os.geteuid(), armed=True, grounding_provider=grounding,
                read_provider=readers, read_schema=CEO_WEB_CEO_V2_READ_SCHEMA,
            ),
        )
        assert service.config.terminal_return_armed is False
        frames, backend_acceptances, handlers, errors = [], [], set(), []

        async def proxy(reader, writer):
            task, backend_writer = asyncio.current_task(), None
            handlers.add(task)
            try:
                raw = await asyncio.wait_for(reader.readline(), 2)
                frame = json.loads(raw)
                frames.append(frame)
                backend_reader, backend_writer = await asyncio.open_unix_connection(
                    str(service.ceo_ingress_socket_path), limit=gateway._STREAM_LIMIT,
                )
                backend_writer.write(raw)
                await backend_writer.drain()
                backend_writer.write_eof()
                reply = await asyncio.wait_for(backend_reader.readline(), 3)
                if frame["schema"] == ingress.SUBMIT_SCHEMA_V2:
                    backend_acceptances.append(json.loads(reply))
                    if lose_submit_reply:
                        return  # Real acceptance persisted; its reply never reaches the App.
                writer.write(reply)
                await writer.drain()
            except Exception as exc:
                errors.append(type(exc).__name__)
            finally:
                for stream in (backend_writer, writer):
                    if stream is not None:
                        stream.close()
                        try:
                            await asyncio.wait_for(stream.wait_closed(), .5)
                        except Exception:
                            stream.transport.abort()
                handlers.discard(task)

        server = None
        await service.start()
        try:
            server = await asyncio.start_unix_server(proxy, path=str(short_socket_root / "proxy.sock"))
            settings = dataclasses.replace(
                fixture._real_app_settings(
                    rsa_key, mastermind_root=mastermind_root, macro_root=macro_root,
                    ceo_ingress_socket_path=short_socket_root / "proxy.sock",
                ),
                read_from_ceo_ingress=True,
                mastermind_root=tmp_path / "no-app-checkout", macro_root_flag=None,
                connect_timeout=.5, read_timeout=3,
            )
            token = fixture._submit_token(rsa_key)
            async with _connection(profile, settings) as client:
                # An allowed read token and a genuinely foreign signed subject cannot write.
                envelope, refused = await _call(
                    client, fixture._read_token(rsa_key), "submit_ceo_intent", PAYLOAD,
                )
                assert envelope["isError"] is True
                assert refused["error"]["code"] == "scope_refused"
                foreign = await _post(client, fixture._read_token(rsa_key, sub="foreign-reader"),
                                      "submit_ceo_intent", PAYLOAD)
                assert foreign.status_code == 401, foreign.text
                assert frames == [] and service.runtime.jobs.list_jobs() == []
                envelope, submitted = await _call(client, token, "submit_ceo_intent", PAYLOAD)
                request_ref = ceo_request.app_request_ref(PAYLOAD["operation_key"])
                intent_id = ceo_request.automated_intent_id(request_ref)
                assert submitted["request_ref"] == request_ref
                if lose_submit_reply:
                    assert envelope["isError"] is True
                    assert submitted["status"] == "effect_unknown" and "receipt" not in submitted
                    match = re.search(r"intent_id=(auto-[0-9a-f]{32})", submitted["error"]["message"])
                    assert match and match.group(1) == intent_id
                    assert "does not authorize resubmission" in submitted["error"]["message"]
                else:
                    assert envelope["isError"] is False and submitted["status"] == "accepted"
                    assert submitted["receipt"]["intent_id"] == intent_id
                    _assert_receipt_profile(submitted["receipt"], strict_v2)

            assert len(backend_acceptances) == 1 and backend_acceptances[0]["ok"] is True
            _assert_receipt_profile(backend_acceptances[0]["result"], strict_v2)
            jobs = service.runtime.jobs.list_jobs()
            assert len(jobs) == 1
            durable = ceo_intent.resolve_intent(service.runtime, intent_id)
            assert durable["job_id"] == jobs[0].job_id
            assert durable["status"] == "QUEUED" and durable["dispatched"] is False
            _assert_receipt_profile(durable, strict_v2)
            event = service.runtime.store.find_event_by_command_id(ceo_intent.command_id_for(intent_id))
            provenance = event["payload"]["provenance"]
            assert provenance["intent_id"] == intent_id
            assert provenance["workstream"] == PAYLOAD["workstream"]
            assert provenance["grounding"] == grounding.observe()
            assert provenance["schema"] == (ceo_intent.INTENT_SCHEMA_V2 if strict_v2 else ceo_intent.INTENT_SCHEMA)
            if strict_v2:
                assert provenance["dialogue_source"] == source
                assert source_calls == [(intent_id, PAYLOAD["workstream"])] * 2
                assert jobs[0].orchestration_role == "aggregation"
            else:
                assert "dialogue_source" not in provenance and source_calls == []
            source_state[0] = None  # Reopened status must use durable source even during host outage.

            # Only this original pointer survives UI recreation; current workstream is stale input.
            reopened_ui = {"intent_id": intent_id, "workstream": "WS:CHANGED-UI"}
            assert reopened_ui["workstream"] != provenance["workstream"]
            async with _connection(profile, settings) as client:
                envelope, recovered = await _call(
                    client, fixture._read_token(rsa_key), "ceo_intent_status",
                    {"intent_id": reopened_ui["intent_id"]},
                )
                assert envelope["isError"] is False and recovered["ok"] is True
                assert recovered["data"] == durable
                _assert_receipt_profile(recovered["data"], strict_v2)
                assert recovered["grounding"]["source"] == "control_plane.ceo_intent.resolve_intent"
                _, job = await _call(client, fixture._read_token(rsa_key), "executive_job",
                                     {"job_id": durable["job_id"]})
                assert job["ok"] is True and job["data"]["job"]["job_id"] == durable["job_id"]
                assert job["data"]["attempt_count"] == 0

            assert sum(frame["schema"] == ingress.SUBMIT_SCHEMA_V2 for frame in frames) == 1
            assert service.runtime.jobs.list_jobs() == jobs
            assert service.runtime.attempts.list_attempts() == []
            assert service.runtime.workers.list_workers() == []
            assert service.runtime.store.find_event_by_command_id(
                ceo_intent.command_id_for(intent_id))["payload"]["provenance"] == provenance
            assert source_calls == ([(intent_id, PAYLOAD["workstream"])] * 2 if strict_v2 else [])
            assert not errors, errors
        finally:
            if server is not None:
                server.close()
                await server.wait_closed()
            if handlers:
                await asyncio.wait_for(asyncio.gather(*handlers), 2)
            await service.close()
            await readers.aclose()

    asyncio.run(exercise())


@pytest.mark.parametrize("profile", ["web_ceo_v2", "web_ceo_v3"])
@pytest.mark.parametrize("lose_submit_reply", [False, True], ids=["accepted", "lost-reply"])
def test_strict_v2_host_launch_preserves_original_work_ref(
    profile, lose_submit_reply, rsa_key, tmp_path, short_socket_root,
):
    test_real_launch_survives_reopen_without_another_submit(
        profile, lose_submit_reply, rsa_key, tmp_path, short_socket_root, strict_v2=True,
    )
