"""Closed, provider-free ACP byte-stream fixture. Never launch a real provider.

It accepts only one of the enumerated scenarios and the four fixed protocol
methods below. It has no filesystem tools, network client, shell, credentials,
model SDK, subprocess, dynamic imports, extension loading, or durable sessions.
"""
from __future__ import annotations

import argparse
import json
import sys

SCENARIOS = ("end_turn", "permission", "cancel", "cancel_no_terminal", "wrong_session",
             "oversized", "malformed", "duplicate_keys", "partial_eof", "disconnect",
             "wrong_protocol", "auth_required", "unsupported_tool")
SESSION = "fixture-1"


def send(message):
    sys.stdout.write(json.dumps(message, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def response(request_id, result):
    send({"jsonrpc": "2.0", "id": request_id, "result": result})


def update(session=SESSION):
    send({"jsonrpc": "2.0", "method": "session/update", "params": {
        "sessionId": session, "update": {"sessionUpdate": "agent_message_chunk",
                                         "content": {"type": "text", "text": "fixture result"}}}})


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", required=True, choices=SCENARIOS)
    scenario = parser.parse_args().scenario
    prompt_id = None
    initialized = created = False
    for _ in range(16):
        line = sys.stdin.buffer.readline(65537)
        if not line:
            return 0
        if len(line) > 65536 or not line.endswith(b"\n"):
            return 2
        message = json.loads(line)
        method, params = message.get("method"), message.get("params", {})
        if method == "initialize":
            assert not initialized
            assert params["protocolVersion"] == 1
            # SDK 0.12.1 excludes all-default ClientCapabilities from the wire.
            # Omission therefore means no client capability, not an unknown grant.
            capabilities = params.get("clientCapabilities", {})
            assert set(capabilities) <= {"fs", "terminal"}
            assert capabilities.get("terminal", False) is False
            fs = capabilities.get("fs", {})
            assert fs.get("readTextFile", False) is False
            assert fs.get("writeTextFile", False) is False
            initialized = True
            response(message["id"], {
                "protocolVersion": 2 if scenario == "wrong_protocol" else 1,
                "agentCapabilities": {"loadSession": False},
                "authMethods": ([{"id": "do-not-enroll", "name": "Fixture only"}]
                                if scenario == "auth_required" else []),
                "agentInfo": {"name": "mastermind-inert-acp-fixture", "version": "1"},
            })
        elif method == "session/new":
            assert initialized and not created
            assert params["mcpServers"] == []
            created = True
            response(message["id"], {"sessionId": SESSION})
        elif method == "session/prompt":
            assert created and prompt_id is None and params["sessionId"] == SESSION
            prompt_id = message["id"]
            if scenario == "oversized":
                sys.stdout.write("x" * 2048 + "\n"); sys.stdout.flush()
            elif scenario == "malformed":
                sys.stdout.write("not-json\n"); sys.stdout.flush()
            elif scenario == "duplicate_keys":
                sys.stdout.write('{"jsonrpc":"2.0","id":1,"result":{},"result":{}}\n')
                sys.stdout.flush()
            elif scenario == "partial_eof":
                sys.stdout.write('{"jsonrpc":"2.0","id":'); sys.stdout.flush()
                return 0
            elif scenario == "disconnect":
                return 0
            else:
                update("wrong-session" if scenario == "wrong_session" else SESSION)
            if scenario == "permission":
                send({"jsonrpc": "2.0", "id": 700, "method": "session/request_permission", "params": {
                    "sessionId": SESSION,
                    "toolCall": {"toolCallId": "fixture-tool", "title": "Fixture must be denied"},
                    "options": [{"optionId": "allow", "kind": "allow_always", "name": "Allow"}]}})
            elif scenario == "unsupported_tool":
                send({"jsonrpc": "2.0", "id": 701, "method": "fs/read_text_file", "params": {
                    "sessionId": SESSION, "path": "/fixture-must-not-be-read"}})
            elif scenario not in ("cancel", "cancel_no_terminal"):
                response(prompt_id, {"stopReason": "end_turn"})
        elif method == "session/cancel":
            assert params["sessionId"] == SESSION and prompt_id is not None
            if scenario == "cancel":
                response(prompt_id, {"stopReason": "cancelled"})
        elif message.get("id") == 700 and "result" in message:
            assert message["result"] == {"outcome": {"outcome": "cancelled"}}
            response(prompt_id, {"stopReason": "end_turn"})
        elif message.get("id") == 701 and "error" in message:
            response(prompt_id, {"stopReason": "end_turn"})
        else:
            # Authentication/resume/other methods are never a fixture escape hatch.
            return 3
    return 4


if __name__ == "__main__":
    raise SystemExit(main())
