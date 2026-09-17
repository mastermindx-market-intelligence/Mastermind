from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
import select
import sys

import pytest

from integrations.workbench_action_mcp.tunnel import create_runtime_channel, parse_tunnel_config, TunnelConfigurationError
from tests.test_mcp_stdio_boundary import child, initialize, malformed_frames, SENTINEL
from tests.workbench_action_mcp.test_tunnel import _document

REPO = Path(__file__).resolve().parents[2]
LAUNCHER = REPO / "scripts" / "mastermind_workbench_action_stdio.py"


def config_file(tmp_path):
    document, project, audit, _ = _document(tmp_path)
    path = tmp_path / "tunnel.json"
    path.write_text(json.dumps(document))
    path.chmod(0o600)
    return path, document, project, audit


def test_production_child_rejects_private_wire_and_then_dispatches(tmp_path):
    path, document, project, _ = config_file(tmp_path)
    # DEBUG is deliberate: the scoped boundary also excludes full SDK messages.
    script = '''
import logging, runpy, sys
logging.basicConfig(level=logging.DEBUG)
sys.argv = [sys.argv[1], "--config", sys.argv[2]]
runpy.run_path(sys.argv[0], run_name="__main__")
'''
    with child([sys.executable, "-c", script, str(LAUNCHER), str(path)]) as process:
        initialize(process)
        for _name, frame in malformed_frames():
            process.send(frame)
            assert process.receive()["error"] == {
                "code": -32600, "message": "WORKBENCH_MCP_INVALID_REQUEST",
            }
        for bad in ({"action_ref": [SENTINEL]}, {"action_ref": SENTINEL},
                    {"secret": SENTINEL}):
            process.send({"jsonrpc": "2.0", "id": 50, "method": "tools/call", "params": {
                "name": "commit_text_patch", "arguments": bad,
            }})
            reply = process.receive()["result"]
            assert reply["isError"] is True
            assert SENTINEL not in json.dumps(reply)
        process.send({"jsonrpc": "2.0", "id": 51, "method": "tools/call", "params": {
            "name": "prepare_text_patch", "arguments": {
                "project_ref": document["lease"]["project_ref"], "relative_path": "sample.py",
                "mode": "CREATE", "new_text": "native-valid\n",
            },
        }})
        prepared = process.receive()["result"]["structuredContent"]
        assert prepared["status"] == "PREPARED"
        for request_id, name in ((52, "commit_text_patch"), (53, "reconcile_text_patch")):
            process.send({"jsonrpc": "2.0", "id": request_id, "method": "tools/call", "params": {
                "name": name, "arguments": {"action_ref": prepared["action_ref"]},
            }})
            effect = process.receive()["result"]["structuredContent"]
            assert effect["effect_state"] == "APPLIED"
            assert effect["cleanup_state"] == "CLEAN"
        assert (project / "sample.py").read_text() == "native-valid\n"
        process.assert_exit(0)
        assert SENTINEL.encode() not in process.wire + process.stderr()
        assert b"WORKBENCH_MCP_INVALID_REQUEST" in process.stderr()


def _modern_meta():
    return {
        "io.modelcontextprotocol/protocolVersion": "2026-07-28",
        "io.modelcontextprotocol/clientInfo": {"name": "chatgpt-web-test", "version": "1"},
        "io.modelcontextprotocol/clientCapabilities": {},
    }


def _modern_request(process, request_id, method, params):
    process.send({
        "jsonrpc": "2.0", "id": request_id, "method": method, "params": params,
    })
    reply = process.receive()
    assert reply["id"] == request_id
    return reply


def test_production_child_serves_modern_discovery_and_effects(tmp_path):
    path, document, project, _ = config_file(tmp_path)
    meta = _modern_meta()
    with child([sys.executable, str(LAUNCHER), "--config", str(path)]) as process:
        discovered = _modern_request(
            process, "openai-mcp-discover", "server/discover", {"_meta": meta}
        )["result"]
        assert discovered["resultType"] == "complete"
        assert discovered["supportedVersions"] == ["2026-07-28"]
        assert discovered["capabilities"] == {"tools": {"listChanged": False}}
        assert discovered["_meta"]["io.modelcontextprotocol/serverInfo"] == {
            "name": "Mastermind Workbench Action Tunnel", "version": "0.1.0",
        }

        listed = _modern_request(
            process, "openai-tools-list", "tools/list", {"_meta": meta}
        )["result"]
        assert listed["resultType"] == "complete"
        assert [tool["name"] for tool in listed["tools"]] == [
            "workspace_manifest", "read_project_file", "preview_text_replace",
            "prepare_text_patch", "commit_text_patch", "reconcile_text_patch",
            "prepare_project_command", "run_project_command",
            "read_action_result", "reconcile_action",
        ]

        manifest = _modern_request(
            process, "manifest", "tools/call",
            {"_meta": meta, "name": "workspace_manifest", "arguments": {}},
        )["result"]
        assert manifest["resultType"] == "complete"
        assert manifest["structuredContent"]["ok"] is True

        prepared = _modern_request(
            process, "prepare", "tools/call",
            {
                "_meta": meta, "name": "prepare_text_patch",
                "arguments": {
                    "project_ref": document["lease"]["project_ref"],
                    "relative_path": "sample.py", "mode": "CREATE",
                    "new_text": "modern-valid\n",
                },
            },
        )["result"]["structuredContent"]
        assert prepared["status"] == "PREPARED"
        for request_id, name in (("commit", "commit_text_patch"),
                                 ("reconcile", "reconcile_text_patch")):
            effect = _modern_request(
                process, request_id, "tools/call",
                {
                    "_meta": meta, "name": name,
                    "arguments": {"action_ref": prepared["action_ref"]},
                },
            )["result"]
            assert effect["resultType"] == "complete"
            assert effect["structuredContent"]["effect_state"] == "APPLIED"
            assert effect["structuredContent"]["cleanup_state"] == "CLEAN"
        assert (project / "sample.py").read_text() == "modern-valid\n"
        process.assert_exit(0)


def test_modern_unknown_method_is_correlated_and_session_recovers(tmp_path):
    path, _, _, _ = config_file(tmp_path)
    meta = _modern_meta()
    with child([sys.executable, str(LAUNCHER), "--config", str(path)]) as process:
        _modern_request(
            process, "openai-mcp-discover", "server/discover", {"_meta": meta}
        )
        refused = _modern_request(
            process, "unsupported-modern", "resources/list", {"_meta": meta}
        )
        assert refused["error"] == {"code": -32601, "message": "method not found"}
        listed = _modern_request(
            process, "after-refusal", "tools/list", {"_meta": meta}
        )["result"]
        assert len(listed["tools"]) == 10
        process.assert_exit(0)


def _read_signal(fd, expected):
    ready, _, _ = select.select([fd], [], [], 5)
    assert ready, "native physical lifecycle signal timed out"
    assert os.read(fd, 1) == expected


def test_actual_child_construction_failure_closes_runtime_without_fallback(tmp_path):
    path, _, _, _ = config_file(tmp_path)
    observed, signal = os.pipe()
    script = '''
import os, sys
import integrations.workbench_action_mcp.tunnel as tunnel
from integrations.workbench_action_mcp.runtime import WorkbenchActionRuntime
real_close = WorkbenchActionRuntime.aclose
async def close(self, *, timeout):
    await real_close(self, timeout=timeout)
    os.write(int(sys.argv[2]), b"C")
WorkbenchActionRuntime.aclose = close
def refuse(_runtime):
    raise ValueError("WORKBENCH_REJECTED_SECRET_7b927c")
tunnel.create_tunnel_action_server = refuse
raise SystemExit(tunnel.run_configured_stdio(sys.argv[1]))
'''
    try:
        with child([sys.executable, "-c", script, str(path), str(signal)], pass_fds=(signal,)) as process:
            _read_signal(observed, b"C")
            process.assert_exit(5)
            assert SENTINEL.encode() not in process.wire + process.stderr()
            assert not process.fallback_used
    finally:
        os.close(observed)
        os.close(signal)


def test_actual_child_eof_drains_inflight_audit_without_port_dispatch(tmp_path):
    path, document, project, _ = config_file(tmp_path)
    observed, signal = os.pipe()
    release, release_writer = os.pipe()
    dispatch_read, dispatch_write = os.pipe()
    script = '''
import os, sys
import integrations.workbench_action_mcp.tunnel as tunnel
from integrations.workbench_action_mcp.runtime import WorkbenchActionRuntime
from integrations.business_mcp_auth.audit import DurableAuthAuditSink
real_emit = DurableAuthAuditSink.emit
real_close = WorkbenchActionRuntime.aclose
real_port = tunnel.create_text_patch_port
signal, release, dispatch = map(int, sys.argv[2:])
def emit(self, event):
    if event.accepted:
        os.write(signal, b"E")
        if os.read(release, 1) != b"R":
            raise RuntimeError("TEST_RELEASE_REQUIRED")
    return real_emit(self, event)
async def close(self, *, timeout):
    os.write(signal, b"C")
    return await real_close(self, timeout=timeout)
def port(**kwargs):
    prepare, commit, reconcile = real_port(**kwargs)
    async def tracked_prepare(*args):
        os.write(dispatch, b"D")
        return await prepare(*args)
    return tracked_prepare, commit, reconcile
DurableAuthAuditSink.emit = emit
WorkbenchActionRuntime.aclose = close
tunnel.create_text_patch_port = port
raise SystemExit(tunnel.run_configured_stdio(sys.argv[1]))
'''
    released = False
    try:
        with child([sys.executable, "-c", script, str(path), str(signal), str(release), str(dispatch_write)],
                   pass_fds=(signal, release, dispatch_write)) as process:
            try:
                initialize(process)
                process.send({"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {
                    "name": "prepare_text_patch", "arguments": {
                        "project_ref": document["lease"]["project_ref"], "relative_path": "sample.py",
                        "mode": "CREATE", "new_text": "must-not-dispatch\n",
                    },
                }})
                _read_signal(observed, b"E")
                process.eof()
                _read_signal(observed, b"C")
                assert process.process.poll() is None
                os.write(release_writer, b"R")
                released = True
                process.assert_exit(0)
                assert not select.select([dispatch_read], [], [], 0)[0]
                assert not (project / "sample.py").exists()
            finally:
                if not released:
                    os.write(release_writer, b"R")
                    released = True
                # Drain before fallback cleanup, even if an assertion failed.
                process.eof()
                process.process.wait(timeout=10)
    finally:
        for fd in (observed, signal, release, release_writer, dispatch_read, dispatch_write):
            os.close(fd)


@pytest.mark.parametrize("field,value", [
    ("artifact_directory", None), ("artifact_directory", "relative"),
    ("host_id", None), ("host_id", "A" * 64), ("host_id", "a" * 63), ("host_id", 123),
])
def test_config_requires_explicit_artifact_directory_and_host(tmp_path, field, value):
    _, document, _, _ = config_file(tmp_path)
    if value is None:
        del document[field]
    else:
        document[field] = value
    with pytest.raises(TunnelConfigurationError):
        parse_tunnel_config(document)


def test_artifact_directory_has_no_creation_or_insecure_fallback(tmp_path):
    _, document, _, _ = config_file(tmp_path)
    directory = Path(document["artifact_directory"])
    directory.rmdir()
    with pytest.raises(TunnelConfigurationError):
        asyncio.run(create_runtime_channel(parse_tunnel_config(document)))
    assert not directory.exists()
    directory.mkdir(mode=0o777)
    directory.chmod(0o777)
    with pytest.raises(TunnelConfigurationError):
        asyncio.run(create_runtime_channel(parse_tunnel_config(document)))
