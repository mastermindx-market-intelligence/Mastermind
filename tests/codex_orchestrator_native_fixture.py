"""Test-only loopback response driver for actual native Codex machinery.

No real credentials, model service, Executive instance, or user configuration.
The in-repository OHF client owns the process and guarantees bounded cleanup.
SSE event shapes follow openai/codex core/tests/common/responses.rs.
"""
from __future__ import annotations

import json
import shlex
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from ops.codex_fabric.orchestrator_bundle import (
    configuration_overrides, inspect_bundle, install_bundle,
)
from scripts.ohf.laboratory import AppServerClient


def _named_tool(value: Any, name: str) -> dict | None:
    if isinstance(value, dict):
        if value.get("name") == name:
            return value
        for item in value.values():
            found = _named_tool(item, name)
            if found is not None:
                return found
    elif isinstance(value, list):
        for item in value:
            found = _named_tool(item, name)
            if found is not None:
                return found
    return None


def _tool_namespace(value: Any, name: str, namespace: str = "") -> str | None:
    if isinstance(value, dict):
        if value.get("type") == "namespace":
            namespace = ".".join(filter(None, (namespace, value.get("name", ""))))
        if value.get("name") == name and value.get("type") in {"function", "custom"}:
            return namespace
        for item in value.values():
            found = _tool_namespace(item, name, namespace)
            if found is not None:
                return found
    elif isinstance(value, list):
        for item in value:
            found = _tool_namespace(item, name, namespace)
            if found is not None:
                return found
    return None


def _request_text(request: dict) -> str:
    return "\n".join(part.get("text", "") for item in request.get("input", [])
                     for part in item.get("content", []) if isinstance(part, dict))


def run_native_fixture(binary: Path, root: Path, *, role: str | None = None,
                       attempt_grandchild: bool = False, attempt_write: bool = False) -> dict:
    root = root.resolve()
    home = root / "home"; home.mkdir()
    codex_home = home / "codex"; codex_home.mkdir()
    project = root / "project"; project.mkdir()
    requests: list[dict] = []
    faults: list[str] = []
    parent_id = ""
    attempted_child_ids: set[str] = set()
    write_attempted = threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_POST(self):
            if self.path != "/v1/responses" or len(requests) >= 6:
                faults.append("UNEXPECTED_OR_EXCESS_REQUEST")
                self.send_error(400)
                return
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= 2_000_000 or self.headers.get("Authorization"):
                faults.append("UNSAFE_FIXTURE_REQUEST")
                self.send_error(400)
                return
            data = json.loads(self.rfile.read(size))
            requests.append(data)
            response_id = "resp_fixture_" + str(len(requests))
            item = {"type": "message", "role": "assistant", "id": "msg_fixture",
                    "content": [{"type": "output_text", "text": "FIXTURE_COMPLETE"}]}
            request_thread = data.get("client_metadata", {}).get("thread_id")
            if role is not None and request_thread != parent_id:
                item["content"][0]["text"] = "FIXTURE_CHILD_RESULT"
            if role is not None and len(requests) == 1:
                namespace = _tool_namespace(data, "spawn_agent")
                item = {"type": "function_call", "call_id": "spawn_fixture", "name": "spawn_agent",
                        "arguments": json.dumps({"agent_type": role, "task_name": "coordinator",
                            "fork_turns": "none", "message": "Native test only; return fixture completion."})}
                if namespace:
                    item["namespace"] = namespace
            elif attempt_grandchild and request_thread != parent_id and not attempted_child_ids:
                attempted_child_ids.add(request_thread)
                namespace = _tool_namespace(data, "spawn_agent")
                item = {"type": "function_call", "call_id": "grandchild_fixture", "name": "spawn_agent",
                        "arguments": json.dumps({"agent_type": role, "task_name": "grandchild",
                            "fork_turns": "none", "message": "Native negative fixture only."})}
                if namespace:
                    item["namespace"] = namespace
            elif attempt_write and request_thread != parent_id and not write_attempted.is_set():
                write_attempted.set()
                marker = project / "write-probe.txt"
                command = "printf native-sandbox-negative > " + shlex.quote(str(marker))
                item = {"type": "custom_tool_call", "call_id": "write_fixture", "name": "exec",
                        "input": "text(await tools.exec_command(" + json.dumps({"cmd": command,
                            "login": False, "workdir": str(project), "max_output_tokens": 200}) + "));"}
                namespace = _tool_namespace(data, "exec")
                if namespace:
                    item["namespace"] = namespace
            elif role is not None and request_thread == parent_id and "FIXTURE_CHILD_RESULT" not in _request_text(data):
                namespace = _tool_namespace(data, "wait_agent")
                item = {"type": "function_call", "call_id": "wait_fixture_" + str(len(requests)),
                        "name": "wait_agent", "arguments": json.dumps({"timeout_ms": 10000})}
                if namespace:
                    item["namespace"] = namespace
            events = [
                {"type": "response.created", "response": {"id": response_id}},
                {"type": "response.output_item.done", "item": item},
                {"type": "response.completed", "response": {"id": response_id,
                 "usage": {"input_tokens": 0, "input_tokens_details": None,
                           "output_tokens": 0, "output_tokens_details": None,
                           "total_tokens": 0}}},
            ]
            body = "".join("event: " + x["type"] + "\ndata: " + json.dumps(x) + "\n\n"
                           for x in events).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    client = None
    result: dict = {}
    try:
        config = (
            'cli_auth_credentials_store="file"\nmcp_oauth_credentials_store="file"\n'
            'model_provider="scripted_test"\n[model_providers.scripted_test]\n'
            'name="Local deterministic test only"\n'
            f'base_url="http://127.0.0.1:{server.server_port}/v1"\n'
            'wire_api="responses"\nrequires_openai_auth=false\n'
            'request_max_retries=0\nstream_max_retries=0\n'
            '[features]\nenable_request_compression=false\n'
        )
        (codex_home / "config.toml").write_text(config)
        digest = inspect_bundle(codex_home)["bundle_digest"]
        install_bundle(codex_home, expected_bundle_digest=digest)
        argv = [str(binary)]
        for setting in configuration_overrides(codex_home, expected_bundle_digest=digest):
            argv.extend(["-c", setting])
        argv.append("app-server")
        client = AppServerClient(argv, cwd=project, start_new_session=True,
            env={"PATH": "/opt/homebrew/bin:/usr/bin:/bin", "HOME": str(home),
                 "CODEX_HOME": str(codex_home)})
        client.start()
        client.request("initialize", {"clientInfo": {"name": "mmx_fixture", "version": "1"},
                       "capabilities": {"experimentalApi": True}}, timeout=10)
        client.notify("initialized", {})
        parent = client.request("thread/start", {"cwd": str(project), "ephemeral": False}, timeout=15)
        parent_id = parent["thread"]["id"]
        client.request("turn/start", {"threadId": parent_id, "input": [
            {"type": "text", "text": "Native machinery fixture only."}]}, timeout=10)
        completed = {}
        deadline = time.monotonic() + 20
        while parent_id not in completed or len(completed) < (2 if role is not None else 1):
            event = client.wait_notification("turn/completed", timeout=max(0.1, deadline - time.monotonic()))
            completed[event["params"]["threadId"]] = event
        event = completed[parent_id]
        result = {"parent_id": parent_id, "parent_status": event["params"]["turn"]["status"],
                  "parent_sandbox": parent["sandbox"], "request_count": len(requests),
                  "spawn_schema": _named_tool(requests[0], "spawn_agent") if requests else None,
                  "wait_schema": _named_tool(requests[0], "wait_agent") if requests else None,
                  "faults": faults, "real_credentials_used": False,
                  "served_model_attested": False, "completed_thread_count": len(completed),
                  "parent_received_child_completion": any(
                      r.get("client_metadata", {}).get("thread_id") == parent_id
                      and "FIXTURE_CHILD_RESULT" in _request_text(r) for r in requests)}
        if role is not None:
            tree = client.request("thread/list", {"parentThreadId": parent_id,
                                  "cwd": str(project), "limit": 3}, timeout=10)
            grandchildren = []
            for row in tree.get("data", []):
                nested = client.request("thread/list", {"parentThreadId": row["id"],
                    "cwd": str(project), "limit": 3}, timeout=10)
                grandchildren.extend(nested.get("data", []))
            result["grandchildren"] = [{k: r.get(k) for k in ("id", "parentThreadId", "agentRole", "model")} for r in grandchildren]
            result["project_marker_exists"] = (project / "write-probe.txt").exists()
            result["write_call_outputs"] = [i.get("output") for r in requests for i in r.get("input", [])
                if i.get("type") == "custom_tool_call_output" and i.get("call_id") == "write_fixture"]
            result["grandchild_call_outputs"] = [i.get("output") for r in requests for i in r.get("input", [])
                if i.get("type") == "function_call_output" and i.get("call_id") == "grandchild_fixture"]
            child_requests = [r for r in requests if r.get("client_metadata", {}).get("thread_id") != parent_id]
            child_request = child_requests[0] if child_requests else {}
            child_text = "\n".join(piece.get("text", "") for item in child_request.get("input", [])
                        for piece in item.get("content", []) if isinstance(piece, dict))
            result.update({"children": [{k: row.get(k) for k in ("id", "parentThreadId", "agentRole", "model", "reasoningEffort", "status")}
                                        for row in tree.get("data", [])],
                "child_request_model": child_request.get("model"),
                "child_shell_schema": _named_tool(child_request, "exec_command") or _named_tool(child_request, "exec"),
                "child_spawn_tool_present": _named_tool(child_request, "spawn_agent") is not None,
                "child_read_only_instructions": 'sandbox_mode` is `read-only`' in child_text,
                "child_own_role_instructions": "Do not spawn native child agents" in child_text,
                "spawn_namespace": _tool_namespace(requests[0], "spawn_agent"),
                "tool_outputs": [i.get("output") for r in requests for i in r.get("input", [])
                                 if i.get("type") == "function_call_output"]})
    finally:
        try:
            if client is not None:
                client.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
    result["process_settled"] = not client.alive() and not client.private_group_alive() and not thread.is_alive()
    if faults or (codex_home / "auth.json").exists():
        raise AssertionError("fixture crossed its credential/request contract")
    return result
