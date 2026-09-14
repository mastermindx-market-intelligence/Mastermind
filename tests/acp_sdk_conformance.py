"""Explicit SDK gate. Missing or wrong SDK exits nonzero, never a green skip.

Run: python tests/acp_sdk_conformance.py
Only the fixed inert peer in scripts/ohf may be spawned. No provider arguments,
URLs, account homes, auth commands, MCP servers, or real model turns are exposed.
"""
from __future__ import annotations

import asyncio
import hashlib
import importlib.metadata
import json
import logging
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.ohf.acp_probe_boundary import ProbeClient, ProbeLimits, StrictFrameReader, observe_prompt

SDK_VERSION = "0.12.1"
EXPECTED = {
    "end_turn": ("OBSERVED_END_TURN", "ORIGINAL_PROMPT_END_TURN"),
    "permission": ("OBSERVED_END_TURN", "ORIGINAL_PROMPT_END_TURN"),
    "cancel": ("OBSERVED_CANCELLED", "ORIGINAL_PROMPT_CANCELLED"),
    "cancel_no_terminal": ("INCONCLUSIVE", "CANCEL_TERMINAL_UNOBSERVED"),
    "wrong_session": ("INCONCLUSIVE", "SESSION_MISMATCH"),
    "oversized": ("INCONCLUSIVE", "FRAME_TOO_LARGE"),
    "malformed": ("INCONCLUSIVE", "INVALID_FRAME"),
    "duplicate_keys": ("INCONCLUSIVE", "INVALID_FRAME"),
    "partial_eof": ("INCONCLUSIVE", "PARTIAL_FRAME"),
    "disconnect": ("INCONCLUSIVE", "PROMPT_TRANSPORT_UNCERTAIN"),
    "wrong_protocol": ("NOT_DISPATCHED", "PROTOCOL_VERSION_REFUSED"),
    "auth_required": ("NOT_DISPATCHED", "AUTHENTICATION_NOT_ADMITTED"),
    "unsupported_tool": ("INCONCLUSIVE", "TOOL_NOT_GRANTED"),
}


async def one_case(scenario: str) -> dict:
    from acp import connect_to_agent
    from acp._transport import NdjsonTransport
    from acp.task import MessageSender, TaskSupervisor

    client = ProbeClient(ProbeLimits(frame_bytes=1024))
    sender_tasks = TaskSupervisor(source="mastermind-inert-acp-probe")
    conn = None
    result = None
    clean = True
    with tempfile.TemporaryDirectory(prefix="mmx-acp-probe-") as fixture_root:
        process = await asyncio.create_subprocess_exec(
            sys.executable, "-I", "-B", str(ROOT / "scripts/ohf/fake_acp_probe_peer.py"),
            "--scenario", scenario,
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE, limit=1024, cwd=fixture_root,
            env={"PATH": os.defpath, "PYTHONDONTWRITEBYTECODE": "1"},
        )
        stderr_task = asyncio.create_task(process.stderr.read(4097))
        try:
            transport = NdjsonTransport(
                StrictFrameReader(process.stdout, client),
                # Keep transport loss distinct from the 1s prompt + 1s cancel semantic budget.
                MessageSender(process.stdin, sender_tasks), receive_timeout=4.0)
            conn = connect_to_agent(client, transport)
            init = await asyncio.wait_for(conn.initialize(
                protocol_version=1, client_capabilities={
                    "fs": {"readTextFile": False, "writeTextFile": False}, "terminal": False}), timeout=2)
            if init.protocol_version != 1:
                result = {**client.snapshot(), "disposition": "NOT_DISPATCHED", "reason": "PROTOCOL_VERSION_REFUSED"}
            elif init.auth_methods:
                result = {**client.snapshot(), "disposition": "NOT_DISPATCHED", "reason": "AUTHENTICATION_NOT_ADMITTED"}
            else:
                session = await asyncio.wait_for(conn.new_session(cwd=fixture_root, mcp_servers=[]), timeout=2)
                client.bind_session(session.session_id)
                result = await observe_prompt(conn, client, "deterministic fixture input", timeout=1.0, cancel_timeout=1.0)
        finally:
            if conn is not None:
                try:
                    await asyncio.wait_for(conn.close(), timeout=1)
                except Exception:
                    clean = False
            try:
                await asyncio.wait_for(sender_tasks.shutdown(), timeout=1)
            except Exception:
                clean = False
            if process.stdin is not None:
                process.stdin.close()
            try:
                await asyncio.wait_for(process.wait(), timeout=1)
            except TimeoutError:
                # A deadline race is not a dirty exit when returncode is already
                # observed. Only a still-live fixture requires force and fails.
                if process.returncode is None:
                    clean = False
                    process.kill()
                await asyncio.wait_for(process.wait(), timeout=1)
            stderr = await asyncio.wait_for(stderr_task, timeout=1)
        if result is None:
            raise AssertionError("SDK_CASE_NO_RESULT")
        # A late frame rejected while closing cannot rescue an earlier snapshot.
        if client.violation:
            result.update(disposition="INCONCLUSIVE", reason=client.violation,
                          boundary_violation=client.violation)
        result.update(scenario=scenario, sdk_version=SDK_VERSION,
                      fixture_exit=process.returncode, fixture_cleanup=clean,
                      fixture_stderr_bytes=len(stderr), fixture_stderr_sha256=hashlib.sha256(stderr).hexdigest())
        assert process.returncode == 0 and clean and not stderr, (scenario, "FIXTURE_CLEANUP_FAILED", result)
        assert (result["disposition"], result["reason"]) == EXPECTED[scenario], result
        if scenario == "permission":
            assert result["permission_denials"] == 1, result
        assert result["production_proven"] is False and result["worker_adapter_implemented"] is False
        return result


async def main() -> int:
    if sys.flags.optimize:
        print(json.dumps({"status": "BLOCKED", "reason": "ASSERTIONS_DISABLED"}))
        return 2
    try:
        installed = importlib.metadata.version("agent-client-protocol")
    except importlib.metadata.PackageNotFoundError:
        print(json.dumps({"status": "BLOCKED", "reason": "SDK_NOT_INSTALLED", "required": SDK_VERSION}))
        return 2
    if installed != SDK_VERSION:
        print(json.dumps({"status": "BLOCKED", "reason": "SDK_VERSION_MISMATCH", "required": SDK_VERSION}))
        return 2
    # SDK exception handlers may log peer bodies. This fixture admits no secrets;
    # suppressing them is NOT a production logging/redaction qualification.
    logging.disable(logging.CRITICAL)
    results = []
    for scenario in EXPECTED:
        results.append(await one_case(scenario))
        print(json.dumps(results[-1], sort_keys=True), flush=True)
    print(json.dumps({"status": "PASS", "cases": len(results), "sdk_version": installed,
                      "proof_scope": "REAL_SDK_WITH_PROVIDER_FREE_SUBPROCESS_PEERS",
                      "production_proven": False}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
