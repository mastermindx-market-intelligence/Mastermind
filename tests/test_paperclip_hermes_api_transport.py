"""Original finite Hermes MCP owners over HTTP to the genuine API lifecycle.

This opt-in proof has two processes and their own declared MCP SDK versions.
The native side uses the unmodified, pinned Hermes CLI discovery, OAuth,
profile, middleware and tool-dispatch owners. This side runs the existing
signed App and Unix Control fixture. Only the provider execution is inert.
No model call, live Paperclip run, native issue origin or installed grant is
inferred from the disposable API enrollment.
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import hashlib
from importlib.metadata import version
import json
import os
from pathlib import Path
import socket

import pytest

from common import coo_requester_return_contract as return_wire
from integrations.executive_mcp import server
from tests.test_joint_api_ingress import (
    joint_signed, current_joint_project, full_joined, owner, env,
    isolated_git_env, identity, unsealed, rsa_key, unix_control, receipts,
)


class ObservedOriginalHttp:
    """Passive request evidence; forwards original bytes and stores no bearer."""

    def __init__(self, app):
        self.app, self.calls = app, []

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = dict(scope.get("headers", ()))
        original = []
        # Record the original exchange even when authentication rejects it
        # before reading JSON-RPC. This is passive evidence, never a retry.
        record = {
            "http_method": scope["method"], "path": scope["path"],
            "method": None, "tool": None, "action": None, "response_status": None,
            "authorization_sha256": hashlib.sha256(headers.get(b"authorization", b"")).hexdigest(),
            "workspace_companion": b"x-mastermind-workspace-authorization" in headers,
        }
        self.calls.append(record)

        async def observed_receive():
            message = await receive()
            if message["type"] == "http.request":
                original.append(message.get("body", b""))
                if not message.get("more_body", False):
                    try:
                        request = json.loads(b"".join(original))
                    except (ValueError, UnicodeError):
                        request = {}
                    params = request.get("params", {})
                    arguments = params.get("arguments", {})
                    record.update({
                        "method": request.get("method"), "tool": params.get("name"),
                        "action": arguments.get("action"),
                    })
            return message

        async def observed_send(message):
            if message["type"] == "http.response.start":
                record["response_status"] = message["status"]
            await send(message)

        await self.app(scope, observed_receive, observed_send)


@asynccontextmanager
async def original_http(s):
    import uvicorn

    observed = ObservedOriginalHttp(server._build_coo_mcp_app(
        s.settings, audit_sink=s.sink, workspace_app=s.workspace_app))
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.listen(128)
    config = uvicorn.Config(observed, log_level="error", access_log=False,
                            lifespan="on", timeout_graceful_shutdown=5)
    http = uvicorn.Server(config)
    task = asyncio.create_task(http.serve(sockets=[sock]))
    try:
        deadline = asyncio.get_running_loop().time() + 5
        while not http.started:
            if task.done():
                await task
                raise AssertionError("original HTTP App did not start")
            assert asyncio.get_running_loop().time() < deadline
            await asyncio.sleep(0.01)
        yield "http://127.0.0.1:%d/mcp/coo" % port, observed.calls
    finally:
        http.should_exit = True
        try:
            await asyncio.wait_for(task, timeout=10)
        finally:
            sock.close()


@pytest.fixture
def native_runtime():
    required = ("MMX_NATIVE_HERMES_PYTHON", "MMX_NATIVE_HERMES_SOURCE", "MMX_NATIVE_HERMES_PYTHONPATH")
    if not all(os.environ.get(key) for key in required):
        pytest.skip("explicit pinned native Hermes SDK process is required")
    assert version("mcp") == "1.28.1", "App must retain its own declared MCP SDK"
    values = {key: os.environ[key] for key in required}
    assert Path(values[required[0]]).is_file()
    assert Path(values[required[1]]).is_dir()
    return values


@pytest.mark.parametrize("current_joint_project", ["paperclip"], indirect=True)
@pytest.mark.parametrize("boundary", ["normal", "lost_response"])
def test_finite_native_hermes_requester_uses_original_http_and_unix_owners(
        joint_signed, native_runtime, tmp_path, monkeypatch, boundary):
    s, f = joint_signed, joint_signed.f
    command = s.target.children[0].command_id
    home = tmp_path / "paperclip-api-profile"
    home.mkdir(mode=0o700)
    report_path = tmp_path / "native-return.json"
    request_path = tmp_path / "native-input.json"
    stdout_path = tmp_path / "native-output.log"
    helper = Path(__file__).with_name("paperclip_hermes_native_client.py")

    async def run():
        async with unix_control(s, tmp_path) as host:
            # This existing disposable supervisor completes only the actual
            # admitted claim. Provider execution remains the incumbent inert fixture.
            host.finish_gate.set()
            if boundary == "lost_response":
                original = host.service.acknowledge_selected_child_result

                async def lose(*args, **options):
                    await original(*args, **options)
                    raise OSError("original acknowledgment response lost after commit")

                monkeypatch.setattr(host.service, "acknowledge_selected_child_result", lose)
            async with original_http(s) as (url, calls):
                request = {"url": url, "home": str(home),
                    "source": native_runtime["MMX_NATIVE_HERMES_SOURCE"],
                    "token": s.token, "issuer": s.settings.policy.issuer,
                    "scopes": list(s.principal.scopes), "work_ref": f.work,
                    "command": command, "root_job_id": f.root,
                    "job_id": f.work_child.job_id, "ack_action": return_wire.ACK_ACTION,
                    "boundary": boundary, "report": str(report_path)}
                fd = os.open(request_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                with os.fdopen(fd, "w") as stream:
                    json.dump(request, stream)
                child_env = {key: os.environ[key] for key in ("PATH", "LANG", "LC_ALL", "TMPDIR")
                             if key in os.environ}
                child_env.update(PYTHONPATH=native_runtime["MMX_NATIVE_HERMES_PYTHONPATH"],
                                 PYTHONDONTWRITEBYTECODE="1", HERMES_HOME=str(home))
                process = await asyncio.create_subprocess_exec(
                    native_runtime["MMX_NATIVE_HERMES_PYTHON"], "-B", str(helper), str(request_path),
                    cwd=tmp_path, env=child_env,
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
                try:
                    output, _ = await asyncio.wait_for(process.communicate(), timeout=90)
                except BaseException:
                    if process.returncode is None:
                        process.terminate()
                        await process.wait()
                    raise
                finally:
                    # Only this disposable input carries the fixture bearer.
                    request_path.unlink(missing_ok=True)
                    (tmp_path / "native-http-receipt.json").write_text(json.dumps({
                        "calls": calls, "native_returncode": process.returncode,
                        "native_origin_attested": False}, sort_keys=True, indent=2) + "\n")
                if s.token.encode() in output or s.second.encode() in output:
                    raise AssertionError("native output exposed a disposable fixture credential")
                stdout_path.write_bytes(output)
                assert process.returncode == 0, output.decode(errors="replace")[-10000:]
                report = json.loads(report_path.read_bytes())
                assert report["original_native_owner_closed"] is True
                assert report["missing_workspace_refused"] is True
                assert report["sibling_profile_refused"] is True
                assert report["native_origin_attested"] is False
                assert report["dispatch"] == "model_tools.handle_function_call(tool_call; default guards and middleware)"
                assert report["native_schema_source_patch"]["installed"] is False
                assert {"tool_search", "tool_describe", "tool_call"} <= set(report["model_visible_tools"])
                assert len(report["described_tools"]) == 2
                actual = [call for call in calls if call["method"] == "tools/call"]
                assert len([call for call in actual if call["action"] == "selected_child_submit"]) == 1
                assert len([call for call in actual if call["action"] == return_wire.ACK_ACTION]) == 1
                expected_token = hashlib.sha256(("Bearer " + s.token).encode()).hexdigest()
                assert all(call["authorization_sha256"] == expected_token for call in actual)
                assert not any(call["workspace_companion"] for call in actual)
                assert len(actual) == len(report["explicit_calls"]) - 1, "ungranted sibling reached HTTP"
                event = f.j["runtime"].store.get_event_by_command_id(command)
                claim = return_wire.validate_claim(event.payload["selected_child_requester"])
                assert claim["family"] == "coo_api_principal"
                assert claim["selection"]["root_job_id"] == f.root
                assert claim["capability_profile_digest"] == f.profile.profile_digest
                assert f.j["runtime"].jobs.get_job(f.work_child.job_id).attempt_count == 1
                assert len(receipts(f.j["runtime"])) == 1
                assert report["final"]["requester_return"]["consumption"] is not None
                (tmp_path / "native-wire-evidence.json").write_text(json.dumps({
                    "app_mcp_sdk": version("mcp"), "native_mcp_sdk": report["native_sdk"],
                    "calls": calls, "claim": claim,
                    "native_origin_attested": False}, sort_keys=True, indent=2) + "\n")

    asyncio.run(run())
