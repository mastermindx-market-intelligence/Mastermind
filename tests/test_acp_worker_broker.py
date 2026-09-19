"""Actual ACP SDK and broker, with explicitly simulated native ownership.

No provider, OS-isolation, route or production Runtime proof is claimed here.
"""
import asyncio
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import sys
import unittest

try:
    import acp
except ImportError:
    acp = None

from control_plane.codex_worker import ProcessInspector
from control_plane.executive_worker_broker import BrokerEffectUnknownError, BrokerStateError
from control_plane.worker_execution_contract import BinaryAttestation, CancelReceipt, WorkerLaunchSpec, WorkerRunStatus
from integrations.acp_worker.adapter import AcpProcessCompletion, AcpRunResources, AcpWorkerAdapter
from integrations.acp_worker.turn import AcpProfile
from integrations.acp_worker.native import AcpNativeProcessOwner, AcpNativeProfile


@unittest.skipIf(acp is None, "optional ACP SDK absent; no ACP qualification")
class AcpBrokerTests(unittest.IsolatedAsyncioTestCase):
    async def exercise(self, behavior="ok"):
        from acp.schema import (AgentMessageChunk, InitializeResponse, Implementation,
            NewSessionResponse, PromptResponse, SessionConfigOptionSelect,
            SessionConfigSelectOption, TextContentBlock)
        location = Path(__file__).with_name("test_executive_worker_broker.py")
        module_spec = importlib.util.spec_from_file_location("_mmx_broker_fixture", location)
        fixture = importlib.util.module_from_spec(module_spec)
        module_spec.loader.exec_module(fixture)
        tmp = tempfile.TemporaryDirectory(prefix="mmx-acp-broker-", dir="/private/tmp" if os.uname().sysname == "Darwin" else None)
        root = Path(tmp.name).resolve()
        os.chmod(root, 0o700)
        os.chown(root, -1, os.getegid())
        broker, native, sweeper, peer, payload = fixture._fixture(root)
        workspace = Path(payload["workspace_path"])
        env = {"PATH": os.defpath, "HOME": str(root), "GIT_CONFIG_GLOBAL": os.devnull,
               "GIT_CONFIG_NOSYSTEM": "1", "GIT_TERMINAL_PROMPT": "0"}
        def git(*args):
            return subprocess.run(["git", *args], cwd=workspace, env=env,
                capture_output=True, text=True, timeout=10, check=True).stdout.strip()
        git("init", "--template=", "-q")
        git("-c", "user.name=ACP Fixture", "-c", "user.email=fixture@example.invalid",
            "-c", "commit.gpgsign=false", "commit", "--allow-empty", "-qm", "fixture base")
        payload.update(expected_base_sha=git("rev-parse", "HEAD"), authorities=["READ", "RESEARCH"],
                       model="model-a", timeout_seconds=1.0, cancel_grace_seconds=1.0)
        manifest = payload["isolation_manifest"]
        for entry in manifest["entries"]:
            if entry["identity"]["path"] == str(workspace):
                entry["identity"]["mtime_ns"] = workspace.lstat().st_mtime_ns
        payload["isolation_manifest_sha256"] = hashlib.sha256(json.dumps(manifest,
            sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()).hexdigest()
        started, stopped = asyncio.Event(), asyncio.Event()
        calls = {"open": 0, "prompt": 0, "cancel": 0, "finish": 0}
        handlers, sockets = set(), []
        schema = {"type": "object", "properties": {"answer": {"type": "integer"}}, "required": ["answer"]}

        Path(payload["result_schema_path"]).write_text(json.dumps(schema))

        class Peer:
            def __init__(self, writer):
                self.writer = writer
            def on_connect(self, client):
                self.client = client
            async def initialize(self, **kwargs):
                return InitializeResponse(protocol_version=acp.PROTOCOL_VERSION,
                    agent_info=Implementation(name="fixture", version="1"))
            async def new_session(self, **kwargs):
                return NewSessionResponse(session_id="session-1", config_options=[
                    SessionConfigOptionSelect(id="model", name="Model", category="model", type="select",
                        current_value="model-a", options=[SessionConfigSelectOption(value="model-a", name="A")])])
            async def prompt(self, session_id, prompt, **kwargs):
                calls["prompt"] += 1
                started.set()
                if behavior == "cancel":
                    await stopped.wait()
                    return PromptResponse(stop_reason="cancelled")
                if behavior == "malformed-frame":
                    self.writer.write(b'{"jsonrpc":"2.0","id":1,"id":2,"result":{}}\n')
                    await self.writer.drain()
                    await stopped.wait()
                    return PromptResponse(stop_reason="cancelled")
                if behavior == "workspace-write":
                    (workspace / "unexpected.txt").write_text("not permitted")
                value = {"answer": 42}
                if behavior == "wrong-job":
                    value["job_id"] = "another-job"
                await self.client.session_update(session_id=session_id,
                    update=AgentMessageChunk(session_update="agent_message_chunk",
                        content=TextContentBlock(type="text", text=json.dumps(value))))
                return PromptResponse(stop_reason="end_turn")
            async def cancel(self, **kwargs):
                calls["cancel"] += 1
                stopped.set()

        async def handle(reader, writer):
            task = asyncio.current_task()
            handlers.add(task)
            try:
                await acp.run_agent(Peer(writer), writer, reader)
            except (ConnectionResetError, BrokenPipeError):
                if behavior != "malformed-frame":
                    raise
            finally:
                writer.close()
                try:
                    await writer.wait_closed()
                except (ConnectionResetError, BrokenPipeError):
                    if behavior != "malformed-frame":
                        raise
                finally:
                    handlers.discard(task)

        server = await asyncio.start_server(handle, "127.0.0.1", 0, limit=65536)
        async def open_run(spec):
            calls["open"] += 1
            ref = await native.start(spec)
            reader, writer = await asyncio.open_connection("127.0.0.1", server.sockets[0].getsockname()[1], limit=65536)
            sockets.append(writer)
            async def finish(reason):
                calls["finish"] += 1
                stopped.set()
                writer.close()
                try:
                    await writer.wait_closed()
                except (ConnectionResetError, BrokenPipeError):
                    if behavior != "malformed-frame":
                        raise
                if handlers:
                    await asyncio.wait_for(asyncio.gather(*tuple(handlers)), 0.5)
                cancellation = None if reason is None else CancelReceipt(
                    ref.run_id, reason, False, False, False, "2026-08-11T00:00:01+00:00")
                return AcpProcessCompletion(ref, 0, "2026-08-11T00:00:01+00:00",
                    "a" * 64, "b" * 64, behavior != "cleanup-unknown", cancellation)
            return AcpRunResources(ref, writer, reader, native.launch_attestation(ref), schema, finish)
        adapter = AcpWorkerAdapter(AcpProfile("fixture", "1"), inspector=ProcessInspector(), open_run=open_run)
        broker.adapter = adapter  # Existing structural test seam, not a registered route.
        try:
            response = await broker.execute(fixture._request("start", {"launch_spec": payload,
                "validation_commands": []}), peer=peer)
            self.assertTrue(response["ok"])
            self.assertEqual(calls["open"], 1)
            with self.assertRaises(BrokerStateError):
                await broker.execute(fixture._request("start", {"launch_spec": payload,
                    "validation_commands": []}, suffix="duplicate"), peer=peer)
            self.assertEqual(calls["open"], 1)
            await asyncio.wait_for(started.wait(), 1)
            if behavior == "cancel":
                result = await broker.execute(fixture._request("cancel", {"run_id": "run-1", "reason": "requested"}), peer=peer)
                self.assertTrue(result["ok"])
                self.assertEqual(calls["cancel"], 1)
                self.assertTrue(adapter._runs["run-1"].candidate.cancellation_observed)
            elif behavior in {"cleanup-unknown", "malformed-frame"}:
                with self.assertRaises(BrokerEffectUnknownError):
                    await broker.execute(fixture._request("collect", {"run_id": "run-1"}), peer=peer)
                self.assertTrue(adapter._quarantined)
                if behavior == "malformed-frame":
                    self.assertEqual(adapter._runs["run-1"].candidate.error, "ACP_FRAME_BOUNDARY_REFUSED")
                    self.assertTrue(adapter._runs["run-1"].completion.settled)
                self.assertEqual(broker._active_run_id, "run-1")
                result = None
            else:
                result = await broker.execute(fixture._request("collect", {"run_id": "run-1"}), peer=peer)
                self.assertTrue(result["ok"])
                receipt = adapter._runs["run-1"].receipt
                if behavior == "ok":
                    self.assertIs(receipt.result.status, WorkerRunStatus.SUCCEEDED)
                    self.assertEqual(dict(receipt.result.structured_output), {"answer": 42})
                    self.assertEqual(receipt.result.provider_session_id, "session-1")
                    self.assertEqual(receipt.result.git_manifest["head_sha"], payload["expected_base_sha"])
                else:
                    self.assertIs(receipt.result.status, WorkerRunStatus.INVALID_RESULT)
                    self.assertIsNone(receipt.result.structured_output)
            self.assertEqual(calls["prompt"], 1)
            self.assertEqual(calls["finish"], 1)
            self.assertFalse(adapter.unsettled_tasks)
            return result
        finally:
            stopped.set()
            for writer in sockets:
                writer.close()
            server.close()
            await server.wait_closed()
            if handlers:
                await asyncio.wait_for(asyncio.gather(*tuple(handlers), return_exceptions=True), 1)
            tmp.cleanup()

    async def test_existing_broker_consumes_sdk_output_once(self):
        await self.exercise()
    async def test_cancel_requires_original_prompt_and_owner_cleanup(self):
        await self.exercise("cancel")
    async def test_wrong_job_cannot_become_a_worker_result(self):
        await self.exercise("wrong-job")
    async def test_workspace_change_cannot_become_success(self):
        await self.exercise("workspace-write")
    async def test_unknown_cleanup_keeps_lane_and_broker_unreleased(self):
        await self.exercise("cleanup-unknown")
    async def test_malformed_frame_never_becomes_known_success(self):
        await self.exercise("malformed-frame")


    async def test_native_process_owner_executes_real_stdio_generation(self):
        tmp = tempfile.TemporaryDirectory(prefix="mmx-acp-native-", dir="/private/tmp" if os.uname().sysname == "Darwin" else None)
        root = Path(tmp.name).resolve()
        workspace, run_dir = root / "workspace", root / "run"
        workspace.mkdir(mode=0o700)
        run_dir.mkdir(mode=0o700)
        (run_dir / "input").mkdir(mode=0o700)
        env = {"PATH": os.defpath, "HOME": str(root), "GIT_CONFIG_GLOBAL": os.devnull,
               "GIT_CONFIG_NOSYSTEM": "1", "GIT_TERMINAL_PROMPT": "0"}
        def git(*args):
            return subprocess.run(["git", *args], cwd=workspace, env=env,
                capture_output=True, text=True, timeout=10, check=True).stdout.strip()
        git("init", "--template=", "-q")
        git("-c", "user.name=ACP Native", "-c", "user.email=native@example.invalid",
            "-c", "commit.gpgsign=false", "commit", "--allow-empty", "-qm", "fixture base")
        schema_path = run_dir / "input" / "result.schema.json"
        schema_path.write_text(json.dumps({"type": "object", "properties": {"answer": {"type": "integer"}},
            "required": ["answer"]}), encoding="utf-8")
        binary = Path(sys.executable).resolve(strict=True)
        info = binary.stat()
        digest = hashlib.sha256(binary.read_bytes()).hexdigest()
        attestation = BinaryAttestation(
            str(binary), str(binary), f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            digest, None, info.st_size, info.st_dev, info.st_ino, info.st_mode & 0o7777,
            info.st_uid, info.st_gid, info.st_mtime_ns)
        peer = Path(__file__).parent / "fixtures" / "acp_native_peer.py"
        native_profile = AcpNativeProfile("fixture-native", attestation,
            (str(binary), "-B", str(peer)))
        owner = AcpNativeProcessOwner(native_profile,
            environment_loader=lambda: {"PATH": os.defpath, "HOME": str(root), "PYTHONDONTWRITEBYTECODE": "1", "PYTHONNOUSERSITE": "1", "PYTHONPATH": str(Path(acp.__file__).resolve().parents[1])})
        spec = WorkerLaunchSpec(
            "run-native", "job-native", "worker-native", workspace, run_dir,
            "Return the required answer.", schema_path, authorities=("READ",), model="model-a",
            timeout_seconds=3.0, cancel_grace_seconds=1.0, expected_base_sha=git("rev-parse", "HEAD"),
            expected_worker_uid=os.geteuid(), expected_worker_gid=os.getegid())
        adapter = AcpWorkerAdapter(AcpProfile("fixture-native", "1"), inspector=owner.inspector, open_run=owner.open_run)
        try:
            ref = await adapter.start(spec)
            receipt = await asyncio.wait_for(adapter.collect_result(ref), 5)
            self.assertIs(receipt.result.status, WorkerRunStatus.SUCCEEDED)
            self.assertEqual(dict(receipt.result.structured_output), {"answer": 42})
            self.assertEqual(receipt.result.provider_session_id, "native-session")
            self.assertNotEqual(receipt.stdout_sha256, hashlib.sha256(b"").hexdigest())
            self.assertEqual(receipt.stderr_sha256, hashlib.sha256(b"").hexdigest())
            self.assertIsNone(owner._active)
            self.assertFalse(adapter.unsettled_tasks)
        finally:
            tmp.cleanup()


if __name__ == "__main__":
    unittest.main()
