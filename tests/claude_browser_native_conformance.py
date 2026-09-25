#!/usr/bin/env python3
"""Opt-in native Claude/browser protocol fixture; no real account or inference.

This is a test consumer, never a provider adapter, admission route or installer.
A fixed loopback protocol responder drives an installed CLI and a fresh browser.
The MCP grant is explicitly a synthetic fixture, not a production B1 grant.
"""
from __future__ import annotations

import argparse
import base64
import dataclasses
import hashlib
import json
import os
from pathlib import Path
import secrets
import signal
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = Path(__file__).resolve().parents[1]
ROOT_MARKER = "MMX_BROWSER_NATIVE_ROOT"
LEAF_MARKER = "MMX_BROWSER_NATIVE_LEAF"
MAX_REQUEST_BYTES = 16 * 1024 * 1024
MAX_REQUESTS = 32
CHILD_CASES = frozenset({"scoped-child", "child-denied", "child-generated-deny", "child-explicit-deny"})
DENIAL_CASES = frozenset({"denied", "child-denied", "child-generated-deny", "child-explicit-deny"})
BROWSER_TOOLS = ("browser_navigate", "browser_fill_form", "browser_click",
                 "browser_wait_for", "browser_snapshot", "browser_take_screenshot", "browser_close")


def text_parts(value):
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(text_parts(x) for x in value)
    if isinstance(value, dict) and value.get("type") in {"text", "tool_result"}:
        return text_parts(value.get("text", value.get("content", "")))
    return ""


def tool_result(messages, tool_id):
    found = [block for msg in messages if msg.get("role") == "user"
             for block in (msg.get("content") if isinstance(msg.get("content"), list) else [])
             if isinstance(block, dict) and block.get("type") == "tool_result"
             and block.get("tool_use_id") == tool_id]
    if len(found) > 1:
        raise ValueError("duplicate tool result identity")
    return found[0] if found else None


def image_receipts(result):
    content = result.get("content", [])
    if not isinstance(content, list):
        return []
    receipts = []
    for block in content:
        if not isinstance(block, dict) or block.get("type") != "image":
            continue
        source = block.get("source", {})
        if source.get("type") != "base64" or source.get("media_type") not in {"image/png", "image/jpeg", "image/webp"}:
            raise ValueError("unsupported screenshot source")
        data = source.get("data", "")
        if not isinstance(data, str) or len(data) > 14 * 1024 * 1024:
            raise ValueError("screenshot too large")
        raw = base64.b64decode(data, validate=True)
        receipts.append({"media_type": source["media_type"], "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()})
    return receipts


def answer(blocks, model, *, stream):
    stop = "tool_use" if any(b["type"] == "tool_use" for b in blocks) else "end_turn"
    message = {"id": "msg_browser_fixture", "type": "message", "role": "assistant", "model": model,
               "content": blocks, "stop_reason": stop, "stop_sequence": None,
               "usage": {"input_tokens": 1, "output_tokens": 1}}
    if not stream:
        return "application/json", json.dumps(message).encode()
    events = [{"type": "message_start", "message": {**message, "content": [], "stop_reason": None}}]
    for i, block in enumerate(blocks):
        if block["type"] == "text":
            start, delta = {"type": "text", "text": ""}, {"type": "text_delta", "text": block["text"]}
        else:
            start, delta = {**block, "input": {}}, {"type": "input_json_delta", "partial_json": json.dumps(block["input"])}
        events += [{"type": "content_block_start", "index": i, "content_block": start},
                   {"type": "content_block_delta", "index": i, "delta": delta},
                   {"type": "content_block_stop", "index": i}]
    events += [{"type": "message_delta", "delta": {"stop_reason": stop, "stop_sequence": None}, "usage": {"output_tokens": 1}}, {"type": "message_stop"}]
    return "text/event-stream", "".join("event: " + e["type"] + "\ndata: " + json.dumps(e) + "\n\n" for e in events).encode()


def native_result_matches(native, expected):
    return isinstance(native, dict) and native.get("is_error") is False and native.get("result") == expected


def fixture_environment(root, port):
    return {"PATH": "/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin", "HOME": str(root / "home"),
            "TMPDIR": str(root / "tmp"), "CLAUDE_CONFIG_DIR": str(root / "home/.claude"),
            "ANTHROPIC_API_KEY": "fixture-not-a-real-key", "ANTHROPIC_BASE_URL": "http://127.0.0.1:" + str(port),
            "PWTEST_SOCKETS_DIR": str(root / "sockets"), "DISABLE_NONESSENTIAL_TRAFFIC": "1",
            "DISABLE_TELEMETRY": "1", "DISABLE_ERROR_REPORTING": "1", "CLAUDE_CODE_DISABLE_AUTO_MEMORY": "1",
            "CLAUDE_CODE_DISABLE_BACKGROUND_TASKS": "1", "ENABLE_TOOL_SEARCH": "false", "LANG": "en_US.UTF-8"}


def sdk_fixture_options(configuration, binary, workspace):
    if configuration.get("strict_mcp_config") is not True:
        raise ValueError("SDK fixture requires strict MCP configuration")
    return {**configuration, "cli_path": str(binary), "cwd": str(workspace),
            "setting_sources": [], "tools": [], "permission_mode": "dontAsk",
            "model": "sonnet", "effort": "medium", "max_turns": 12,
            "extra_args": {"bare": None, "no-chrome": None, "no-session-persistence": None}}


_SDK_FIXTURE_PROGRAM = r'''import asyncio,json,sys
from claude_agent_sdk import ClaudeAgentOptions,ResultMessage,query
async def main():
    options=ClaudeAgentOptions(**json.loads(sys.argv[1]))
    result=None
    async for message in query(prompt=sys.argv[2],options=options):
        if isinstance(message,ResultMessage):
            if result is not None: raise ValueError("duplicate SDK terminal result")
            result={"is_error":message.is_error,"result":message.result,
                    "subagent_stats":getattr(message,"subagent_stats",None)}
    if result is None: raise ValueError("missing SDK terminal result")
    print(json.dumps(result))
asyncio.run(main())
'''


class Oracle:
    def __init__(self, case, origin, nonce, value):
        self.case, self.origin, self.nonce, self.value = case, origin, nonce, value
        self.records, self.images, self.errors = [], [], []
        self.stage = 0
        self.parent_started = self.parent_consumed = self.completed = self.denied = False
        self.submission = None
        self.snapshot_consumed = False
        self.lock = threading.Lock()

    @property
    def marker(self):
        return "MMX_BROWSER_DONE " + self.nonce

    def respond(self, request):
        with self.lock:
            return self._respond(request)

    def _respond(self, request):
        if len(self.records) >= MAX_REQUESTS:
            raise ValueError("fixture request budget exceeded")
        messages = request.get("messages", [])
        user_text = "\n".join(text_parts(b) for m in messages if m.get("role") == "user"
                              for b in (m.get("content") if isinstance(m.get("content"), list) else [{"type": "text", "text": m.get("content", "")}])
                              if isinstance(b, dict) and b.get("type") == "text")
        leaf = LEAF_MARKER in user_text
        main = ROOT_MARKER in user_text
        auxiliary = not (leaf or main) or not request.get("tools")
        tools = [t.get("name") for t in request.get("tools", [])]
        self.records.append({"role": "auxiliary" if auxiliary else "leaf" if leaf else "parent", "tools": tools})
        if auxiliary:
            return [{"type": "text", "text": "BROWSER_FIXTURE_AUXILIARY"}]
        if self.case in CHILD_CASES and not leaf:
            if not self.parent_started:
                self.parent_started = True
                return [{"type": "tool_use", "id": "toolu_browser_child", "name": "Agent",
                         "input": {"description": "Synthetic browser fixture", "subagent_type": "browser-tester",
                                   "prompt": LEAF_MARKER + " Execute only the fixed synthetic browser fixture."}}]
            result = tool_result(messages, "toolu_browser_child")
            self.parent_consumed = bool(result and not result.get("is_error") and self.nonce in text_parts(result) and (self.completed or (self.case in DENIAL_CASES and self.denied)))
            return [{"type": "text", "text": "PARENT_CONSUMED:" + self.nonce if self.parent_consumed else "PARENT_CONSUMPTION_FAILED"}]
        if self.stage:
            result = tool_result(messages, "toolu_browser_" + str(self.stage - 1))
            if result is None:
                raise ValueError("missing exact browser tool result")
            if result.get("is_error"):
                self.errors.append(text_parts(result)[:900])
                if self.case in DENIAL_CASES and self.stage == 2:
                    self.denied = True
                    return [{"type": "text", "text": "EXPECTED_BROWSER_PERMISSION_DENIAL:" + self.nonce}]
                return [{"type": "text", "text": "BROWSER_FIXTURE_TOOL_FAILED"}]
            if self.stage == 5:
                self.snapshot_consumed = self.marker in text_parts(result)
            if self.stage == 6:
                self.images += image_receipts(result)
        actions = [
            ("browser_navigate", {"url": self.origin + "/"}),
            ("browser_fill_form", {"fields": [{"target": "#message", "name": "Synthetic message", "type": "textbox", "value": self.value}]}),
            ("browser_click", {"target": "#submit", "element": "Submit synthetic message"}),
            ("browser_wait_for", {"text": self.marker}),
            ("browser_snapshot", {}),
            ("browser_take_screenshot", {"scale": "css", "type": "png", "fullPage": False}),
            ("browser_close", {}),
        ]
        if self.stage == len(actions):
            self.completed = bool(self.submission and self.submission["text_integrity"] and self.snapshot_consumed and self.images)
            return [{"type": "text", "text": "BROWSER_RESULT:" + self.nonce if self.completed else "BROWSER_EVIDENCE_INCOMPLETE"}]
        name, args = actions[self.stage]
        full = "mcp__fixtureBrowser__" + name
        if full not in tools and not (self.case in DENIAL_CASES and self.stage == 1):
            raise ValueError("required browser tool not visible: " + full)
        block = {"type": "tool_use", "id": "toolu_browser_" + str(self.stage), "name": full, "input": args}
        self.stage += 1
        return [block]


def handler_for(oracle):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def reply(self, kind, payload):
            self.send_response(200)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self):
            if self.path != "/":
                self.send_error(404)
                return
            html = """<!doctype html><html><title>Mastermind native browser test</title>
<h1>Native browser fixture</h1><label>Message<textarea id="message"></textarea></label>
<button id="submit">Submit test</button><p id="result">Waiting</p>
<script>
const keys=[];let inputs=0;
document.querySelector('#message').addEventListener('keydown',e=>keys.push(e.key));
document.querySelector('#message').addEventListener('input',()=>inputs++);
document.querySelector('#submit').onclick=async()=>{const r=await fetch('/submit',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({value:document.querySelector('#message').value,keys,inputs})});const data=await r.json();document.title=data.marker;document.querySelector('#result').textContent=data.marker;};
</script></html>"""
            self.reply("text/html; charset=utf-8", html.encode())

        def do_POST(self):
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= MAX_REQUEST_BYTES:
                    raise ValueError("request size")
                request = json.loads(self.rfile.read(size))
                path = self.path.split("?")[0]
                if path == "/submit":
                    value, keys = request.get("value"), request.get("keys")
                    if not isinstance(value, str) or not isinstance(keys, list) or len(keys) > 4096:
                        raise ValueError("submission shape")
                    oracle.submission = {"text_integrity": value == oracle.value, "char_count": len(value),
                                         "text_sha256": hashlib.sha256(value.encode()).hexdigest(),
                                         "body_keydown_count": len(keys), "tab_count": keys.count("Tab"), "input_event_count": request.get("inputs")}
                    self.reply("application/json", json.dumps({"marker": oracle.marker}).encode())
                elif path == "/v1/messages/count_tokens":
                    self.reply("application/json", b'{"input_tokens":100}')
                elif path == "/v1/messages":
                    blocks = oracle.respond(request)
                    self.reply(*answer(blocks, request.get("model", "fixture"), stream=request.get("stream", False)))
                else:
                    self.send_error(404)
            except Exception as exc:
                oracle.errors.append(type(exc).__name__ + ": " + str(exc)[:900])
                self.send_error(400, "Fixture request refused")
    return Handler


def run_case(binary, runtime, case, evidence, catalog_path=None):
    sys.path.insert(0, str(ROOT))
    from control_plane.claude_mcp_client_projection import project_claude_mcp_client
    from control_plane.executive_agent_capabilities import ExecutionCapabilityRegistry, observed_mcp_tool_schema_digest
    from control_plane.operator_harness_contract import NativeHelperPolicy
    root = Path(tempfile.mkdtemp(prefix="mmxnb-", dir="/private/tmp"))
    root.chmod(0o700)
    for name in ["home", "tmp", "sockets", "workspace", "workspace/output"]:
        (root / name).mkdir(mode=0o700, parents=True)
    nonce = secrets.token_hex(12)
    value = "Synthetic browser message — Unicode ✓\n" * 24 + nonce
    oracle = Oracle(case, "", nonce, value)
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler_for(oracle))
    oracle.origin = "http://127.0.0.1:" + str(server.server_port)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    original = ExecutionCapabilityRegistry.load(ROOT / "scripts/ohf/fixtures/executive_agent_capabilities_v4_mastermind_operator.json", source_root=ROOT).resolve("operator.browser.local-review.v1")
    grant = next(g for g in original.mcp_server_grants if g.transport == "stdio")
    mcp_args = (str(runtime / "node_modules/@playwright/mcp/cli.js"), "--headless", "--sandbox", "--isolated",
                "--executable-path", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                "--allowed-origins", oracle.origin, "--output-dir", str(root / "workspace/output"))
    catalog_bytes = (catalog_path or runtime.parent / "runtime-tool-catalog.json").read_bytes()
    catalog = json.loads(catalog_bytes)
    selected_tools = tuple(t for t in BROWSER_TOOLS if case not in DENIAL_CASES or case == "denied" or t != "browser_fill_form")
    selected_schemas = {row["name"]: row for row in catalog["tools"] if row["name"] in selected_tools}
    selected_digest = observed_mcp_tool_schema_digest({"tools": selected_schemas})
    observed_catalogs = {"fixtureBrowser": catalog}
    # Synthetic transport fixture only. This does not rewrite/admit the B1 profile.
    grant = dataclasses.replace(grant, config_name="fixtureBrowser", command="/opt/homebrew/bin/node", args=mcp_args,
                                enabled_tools=selected_tools, tool_schema_digest=selected_digest,
                                grant_digest=hashlib.sha256(repr((mcp_args, selected_tools, selected_digest)).encode()).hexdigest())
    profile = dataclasses.replace(original, mcp_server_grants=(grant,), resource_grants=(),
                                  native_helper_policy=NativeHelperPolicy.PARENT_READ_ONLY_CEILING, profile_digest="f" * 64)
    args = [str(binary), *([] if case in CHILD_CASES else ["--bare"]), "--setting-sources", "", "--no-session-persistence", "--no-chrome", "--model", "sonnet", "--effort", "medium"]
    if case in CHILD_CASES:
        projection = project_claude_native_helpers(
            profile,
            helpers=(ClaudeNativeHelperDefinition(
                agent_id="browser-tester",
                description="Fixed synthetic browser fixture",
                prompt=LEAF_MARKER,
                max_turns=10,
            ),),
            permission_mode="dontAsk",
            observed_tool_catalogs=observed_catalogs,
        )
        agent = projection.agents()["browser-tester"]
        helper_args = list(projection.cli_arguments())
        if case in {"child-generated-deny", "child-explicit-deny"}:
            helper_args.insert(helper_args.index("--agents"), "mcp__fixtureBrowser__browser_fill_form")
            assert "mcp__fixtureBrowser__browser_fill_form" in agent["disallowedTools"]
        args += ["--tools", "Agent", *helper_args,
                 "--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}']
    else:
        projection = project_claude_mcp_client(profile, surface="cli", observed_tool_catalogs=observed_catalogs)
        args += ["--tools", "", *projection.cli_arguments()]
        if case == "denied":
            args += ["--disallowedTools", *projection.denied_tools, "mcp__fixtureBrowser__browser_fill_form"]
    args += ["--permission-mode", "dontAsk", "--max-turns", "12", "--output-format", "json", "-p", ROOT_MARKER + " Run only the fixed local browser conformance task."]
    env = fixture_environment(root, server.server_port)
    if case == "sdk":
        sdk_path = runtime.parent / "sdk-libs"
        from importlib.metadata import distributions
        versions = {d.metadata["Name"]: d.version for d in distributions(path=[str(sdk_path)])}
        if versions.get("claude-agent-sdk") != "0.2.153":
            server.shutdown(); server.server_close(); thread.join(timeout=3)
            raise ValueError("SDK fixture requires the exact 0.2.153 test installation")
        projection = project_claude_mcp_client(profile, surface="agent-sdk", observed_tool_catalogs=observed_catalogs)
        options = sdk_fixture_options(projection.configuration(), binary, root / "workspace")
        env["PYTHONPATH"] = str(sdk_path)
        args = [sys.executable, "-c", _SDK_FIXTURE_PROGRAM, json.dumps(options),
                ROOT_MARKER + " Run only the fixed local browser conformance task."]
    timed_out = False
    with (root / "stdout.json").open("wb") as out, (root / "stderr.log").open("wb") as err:
        proc = subprocess.Popen(args, cwd=root / "workspace", env=env, stdin=subprocess.DEVNULL, stdout=out, stderr=err, start_new_session=True)
        try:
            proc.wait(timeout=100)
        except subprocess.TimeoutExpired:
            timed_out = True
            os.killpg(proc.pid, signal.SIGTERM)
            try:
                proc.wait(timeout=8)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
                proc.wait(timeout=8)
        finally:
            server.shutdown(); server.server_close(); thread.join(timeout=3)
    raw = (root / "stdout.json").read_bytes()
    native = json.loads(raw) if len(raw) < MAX_REQUEST_BYTES and raw.lstrip().startswith(b"{") else {}
    try:
        os.killpg(proc.pid, 0)
        group_absent = False
    except ProcessLookupError:
        group_absent = True
    if case in DENIAL_CASES:
        passed = oracle.denied and oracle.submission is None
    else:
        passed = bool(oracle.completed and oracle.submission and oracle.submission["body_keydown_count"] == 0 and oracle.submission["tab_count"] == 0)
    if case in CHILD_CASES:
        passed = passed and oracle.parent_consumed
    expected = ("PARENT_CONSUMED:" + nonce if case in CHILD_CASES else
                "EXPECTED_BROWSER_PERMISSION_DENIAL:" + nonce if case == "denied" else "BROWSER_RESULT:" + nonce)
    passed = passed and native_result_matches(native, expected) and proc.returncode == 0 and not timed_out and group_absent
    receipt = {"schema": "mastermind.claude_browser_native_fixture.v1", "case": case, "status": "PASS" if passed else "FAIL",
               "production_proof": False, "real_account_authentication": False, "real_model_inference": False,
               "real_model_visual_judgment": False, "admitted_b1_resource": False, "provider_endpoint": "loopback protocol fixture",
               "egress_firewall_proof": False, "browser_sandbox_requested": True, "fixture_root": str(root),
               "sdk_version": "0.2.153" if case == "sdk" else None,
               "native_mode": "private-no-bare" if case in CHILD_CASES else "bare",
               "cli_version": subprocess.run([str(binary), "--version"], capture_output=True, text=True, timeout=15).stdout.strip(),
               "exit_code": proc.returncode, "timed_out": timed_out, "owned_process_group_absent": group_absent,
               "browser_tool_results_consumed": oracle.stage, "snapshot_consumed": oracle.snapshot_consumed,
               "image_receipts": oracle.images, "submission": oracle.submission, "parent_consumed": oracle.parent_consumed,
               "native_subagent_stats": native.get("subagent_stats"), "records": oracle.records, "errors": oracle.errors,
               "result": native.get("result"), "native_is_error": native.get("is_error"),
               "source_projection_sha256": hashlib.sha256((ROOT / "control_plane/claude_mcp_client_projection.py").read_bytes()).hexdigest(),
               "tool_catalog_sha256": hashlib.sha256(catalog_bytes).hexdigest(),
               "projected_denied_tools": list(projection.denied_tools),
               "native_helper_environment": (projection.environment() if case in CHILD_CASES else None),
               "source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    if evidence.exists():
        raise ValueError("evidence path already exists")
    evidence.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps({k: v for k, v in receipt.items() if k not in {"records", "image_receipts"}}, indent=2))
    return 0 if passed else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true", required=True)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--case", choices=("direct", "scoped-child", "denied", "child-denied", "child-generated-deny", "child-explicit-deny", "sdk"), required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--catalog", type=Path, default=ROOT / "research/evidence/claude_browser_mcp_tools_0_0_79.json")
    args = parser.parse_args()
    if args.evidence.exists() or not args.binary.is_absolute() or not args.runtime.is_absolute():
        parser.error("new evidence path and absolute installed paths required")
    package = json.loads((args.runtime / "node_modules/@playwright/mcp/package.json").read_text())
    if package.get("version") != "0.0.79":
        parser.error("only the reviewed 0.0.79 dependency is supported")
    return run_case(args.binary, args.runtime, args.case, args.evidence, args.catalog)


if __name__ == "__main__":
    raise SystemExit(main())
