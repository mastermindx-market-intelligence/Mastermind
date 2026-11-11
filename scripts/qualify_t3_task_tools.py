#!/usr/bin/env python3
"""Prove installed Claude task-tool assembly using a loopback-only response fixture.

No real provider inference, source edits, live settings or session resumption.
The exact CLI binary is supplied by the caller. macOS sandbox-exec confines the
CLI to loopback networking; the fixture records only model and tool names.
"""
from __future__ import annotations

import argparse
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading

TASK_TOOLS = {"TaskCreate", "TaskGet", "TaskUpdate", "TaskList"}
MODEL = "claude-fable-5.2:free"
SANDBOX = "(version 1)(allow default)(deny network*)(allow network-outbound (remote ip \"localhost:*\"))"


def observed_catalog(records: list[dict]) -> list[str] | None:
    """Return the catalog only when the CLI emitted one unambiguous init record."""
    initial = [row for row in records if row.get("type") == "system" and row.get("subtype") == "init"]
    if len(initial) != 1:
        return None
    tools = initial[0].get("tools")
    if not isinstance(tools, list) or not all(isinstance(name, str) and name for name in tools):
        return None
    return tools


def run_variant(cli: Path, variant: str) -> dict:
    requests = []
    with tempfile.TemporaryDirectory(prefix="mmx-task-tools-") as temporary:
        directory = Path(temporary)
        config = directory / "config"
        work = directory / "work"
        config.mkdir()
        work.mkdir()
        native_settings = {"env": {"CLAUDE_CODE_ENABLE_TODO_TOOLS": "1"}} if variant.startswith("settings") else {}
        (config / "settings.json").write_text(json.dumps(native_settings))

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass

            def do_POST(self):
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 16 * 1024 * 1024:
                    self.send_error(413)
                    return
                obj = json.loads(self.rfile.read(length))
                if self.path.split("?")[0].endswith("/messages/count_tokens"):
                    payload = b'{"input_tokens":1}'
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(payload)))
                    self.end_headers()
                    self.wfile.write(payload)
                    return
                if self.path.split("?")[0] != "/v1/messages":
                    self.send_error(404)
                    return
                names = sorted(item.get("name", "") for item in obj.get("tools", []))
                auth_ok = self.headers.get("x-api-key") == "fixture-key-not-a-credential"
                requests.append({"model": obj.get("model"), "tool_names": names,
                                 "advertised_task_tools": sorted(name for name in TASK_TOOLS
                                     if name in json.dumps(obj)),
                                 "fixture_auth": auth_ok})
                message = {"id": "msg_fixture_" + variant, "type": "message",
                           "role": "assistant", "model": MODEL, "content": [],
                           "stop_reason": None, "stop_sequence": None,
                           "usage": {"input_tokens": 1, "output_tokens": 1}}
                if obj.get("stream"):
                    events = [
                        ("message_start", {"type": "message_start", "message": message}),
                        ("content_block_start", {"type": "content_block_start", "index": 0,
                                                "content_block": {"type": "text", "text": ""}}),
                        ("content_block_delta", {"type": "content_block_delta", "index": 0,
                                                "delta": {"type": "text_delta", "text": "fixture only"}}),
                        ("content_block_stop", {"type": "content_block_stop", "index": 0}),
                        ("message_delta", {"type": "message_delta", "delta": {
                            "stop_reason": "end_turn", "stop_sequence": None},
                            "usage": {"output_tokens": 2}}),
                        ("message_stop", {"type": "message_stop"}),
                    ]
                    payload = "".join(f"event: {name}\ndata: {json.dumps(data)}\n\n"
                                      for name, data in events).encode()
                    kind = "text/event-stream"
                else:
                    message.update(content=[{"type": "text", "text": "fixture only"}],
                                   stop_reason="end_turn")
                    payload = json.dumps(message).encode()
                    kind = "application/json"
                self.send_response(200)
                self.send_header("Content-Type", kind)
                self.send_header("Content-Length", str(len(payload)))
                self.send_header("Connection", "close")
                self.end_headers()
                self.wfile.write(payload)

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        env = {key: os.environ[key] for key in ("HOME", "USER", "LOGNAME", "TMPDIR", "LANG")
               if key in os.environ}
        env.update(PATH="/usr/bin:/bin:/usr/sbin:/sbin",
                   CLAUDE_CONFIG_DIR=str(config),
                   ANTHROPIC_BASE_URL=f"http://127.0.0.1:{server.server_port}",
                   ANTHROPIC_API_KEY="fixture-key-not-a-credential",
                   CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC="1",
                   DISABLE_AUTOUPDATER="1", DISABLE_ERROR_REPORTING="1",
                   DISABLE_TELEMETRY="1", NO_PROXY="127.0.0.1,localhost")
        if variant.startswith("environment"):
            env["CLAUDE_CODE_ENABLE_TODO_TOOLS"] = "1"
        eager = variant.endswith("_eager")
        if eager:
            env["ENABLE_TOOL_SEARCH"] = "false"
        command = ["/usr/bin/sandbox-exec", "-p", SANDBOX, str(cli), "--print",
                   "--verbose", "--output-format", "stream-json",
                   "--model", MODEL, "--max-turns", "1", "--no-session-persistence",
                   "--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}',
                   "--setting-sources", "user", "--disable-slash-commands",
                   "--no-chrome", "Return the fixture response without calling any tools."]
        try:
            result = subprocess.run(command, cwd=work, env=env, capture_output=True,
                                    text=True, timeout=45, stdin=subprocess.DEVNULL)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
        records = []
        for line in result.stdout.splitlines():
            try:
                row = json.loads(line)
                if isinstance(row, dict):
                    records.append(row)
            except json.JSONDecodeError:
                pass
        catalog = observed_catalog(records)
        present = sorted(TASK_TOOLS.intersection(catalog or []))
        results = [row for row in records if row.get("type") == "result"]
        completed = (len(results) == 1 and results[0].get("subtype") == "success"
                     and results[0].get("is_error") is False)
        wire_present = sorted(TASK_TOOLS.intersection(
            requests[-1]["tool_names"] if requests else []))
        expected = sorted(TASK_TOOLS) if not variant.startswith("baseline") else []
        passed = (result.returncode == 0 and len(requests) == 1
                  and requests[0]["model"] == MODEL and requests[0]["fixture_auth"]
                  and catalog is not None and completed and present == expected
                  and (not eager or wire_present == expected))
        return {"variant": variant, "passed": passed, "exit_code": result.returncode,
                "messages_requests": len(requests), "model": MODEL,
                "tool_search": "disabled_for_wire_proof" if eager else "default",
                "init_task_tools": present, "wire_task_tools": wire_present,
                "advertised_task_tools": requests[-1]["advertised_task_tools"] if requests else [],
                "wire_tool_names": requests[-1]["tool_names"] if requests else [],
                "init_tool_count": len(catalog) if catalog is not None else None, "wire_tool_count": len(
                    requests[-1]["tool_names"] if requests else []),
                "stderr_sha256": hashlib.sha256(result.stderr.encode()).hexdigest(),
                "stderr_tail": result.stderr[-1600:] if not passed else "",
                "output_types": [row.get("type") for row in records],
                "result_errors": [row.get("errors") for row in records
                                  if row.get("type") == "result" and row.get("is_error")]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--claude", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not Path("/usr/bin/sandbox-exec").is_file() or not args.claude.is_file():
        raise SystemExit("Actual installed Claude and macOS sandbox-exec are required")
    version = subprocess.run([str(args.claude), "--version"], text=True,
                             capture_output=True, timeout=10, check=True).stdout.strip()
    results = []
    for variant in ("baseline", "environment", "settings", "baseline_eager", "settings_eager"):
        row = run_variant(args.claude, variant)
        results.append(row)
        print(json.dumps(row, sort_keys=True), flush=True)
        if not row["passed"]:
            break
    report = {"schema": "mastermind.t3_task_tools_fixture.v1", "cli": str(args.claude),
              "cli_version": version, "model_inference": False,
              "process_network": "sandbox-exec loopback only",
              "live_settings_changed": False, "variants": results,
              "passed": len(results) == 5 and all(row["passed"] for row in results)}
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
