"""Model-free tests for the distinct-UID Phase 1C worker broker."""
from __future__ import annotations

import asyncio
import dataclasses
import hashlib
import json
import os
import signal
import stat
import uuid
from pathlib import Path

import pytest

from control_plane.codex_worker import (
    BinaryAttestation,
    CancelReceipt,
    CollectionReceipt,
    ProcessRef,
    ValidationReceipt,
    WorkerResult,
    WorkerRunStatus,
)
from control_plane.executive_worker_broker import (
    BROKER_REQUEST_SCHEMA_VERSION,
    BrokerPolicy,
    BrokerProtocolError,
    BrokerStateError,
    DedicatedUIDError,
    DedicatedUIDSweeper,
    ExecutiveWorkerBroker,
    PeerAuthorizationError,
    PeerCredentials,
    RemoteCodexWorkerAdapter,
    RemoteWorkerProcessController,
    UIDSweepReceipt,
    UID_SWEEP_SCHEMA_VERSION,
    WorkerBrokerClient,
)


class FakeSweeper:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def sweep(self, reason: str) -> UIDSweepReceipt:
        self.calls.append(reason)
        return UIDSweepReceipt(
            schema_version=UID_SWEEP_SCHEMA_VERSION,
            observed_at="2026-08-11T00:00:00+00:00",
            reason=reason,
            worker_uid=os.geteuid(),
            broker_pid=os.getpid(),
            residual_pids_before=(),
            residual_pids_after=(),
            signal_name="SIGKILL",
            signal_sent=False,
            quiescent_observations=2,
        )


class FakeAdapter:
    def __init__(self) -> None:
        self.spec = None
        self.ref = None
        self.collect_started = asyncio.Event()
        self.finished = asyncio.Event()
        self.cancel_calls = 0
        self.validation_calls: list[tuple[str, ...]] = []

    async def start(self, spec):
        self.spec = spec
        binary = BinaryAttestation(
            path="/fixture/codex",
            real_path="/fixture/codex",
            version="fixture-1",
            sha256="a" * 64,
            team_identifier="2DC432GLL2",
            size=1,
            device=1,
            inode=1,
            mode=0o555,
            uid=0,
            gid=0,
            mtime_ns=1,
        )
        self.ref = ProcessRef(
            run_id=spec.run_id,
            pid=42420,
            pgid=42420,
            process_start_identity="1700000000.000001",
            boot_session_id="boot-fixture",
            launch_nonce="nonce-fixture",
            provider_session_id=None,
            stdout_path=str(spec.run_dir / "logs" / "stdout.jsonl"),
            stderr_path=str(spec.run_dir / "logs" / "stderr.log"),
            result_path=str(spec.run_dir / "output" / "result.json"),
            started_at="2026-08-11T00:00:00+00:00",
            binary=binary,
            base_sha=spec.expected_base_sha,
            session_id=42420,
            effective_uid=spec.expected_worker_uid,
            effective_gid=spec.expected_worker_gid,
            real_uid=spec.expected_worker_uid,
            real_gid=spec.expected_worker_gid,
        )
        return self.ref

    def launch_attestation(self, ref):
        assert ref == self.ref
        return {
            "schema_version": "mastermind.executive_launch_attestation/v1",
            "launch_nonce": ref.launch_nonce,
            "process_identity": {
                "pid": ref.pid,
                "pgid": ref.pgid,
                "session_id": ref.session_id,
                "effective_uid": ref.effective_uid,
                "effective_gid": ref.effective_gid,
            },
        }

    async def status(self, ref):
        assert ref == self.ref
        return WorkerRunStatus.CANCELLING if self.cancel_calls else WorkerRunStatus.RUNNING

    def _collection(self):
        assert self.ref is not None and self.spec is not None
        empty = hashlib.sha256(b"").hexdigest()
        collected_ref = dataclasses.replace(
            self.ref,
            provider_session_id="provider-session-fixture",
        )
        result = WorkerResult(
            job_id=self.spec.job_id,
            run_id=self.spec.run_id,
            worker_id=self.spec.worker_id,
            status=WorkerRunStatus.CANCELLED if self.cancel_calls else WorkerRunStatus.SUCCEEDED,
            structured_output=None,
            artifact_manifest=(),
            git_manifest={"base_sha": self.spec.expected_base_sha},
            usage={},
            provider_session_id=collected_ref.provider_session_id,
            exit_code=-15 if self.cancel_calls else 0,
            started_at=self.ref.started_at,
            finished_at="2026-08-11T00:00:01+00:00",
            error=None,
        )
        return CollectionReceipt(
            process_ref=collected_ref,
            result=result,
            stdout_sha256=empty,
            stderr_sha256=empty,
            result_sha256=None,
        )

    async def collect_result(self, ref):
        assert ref == self.ref
        self.collect_started.set()
        await self.finished.wait()
        return self._collection()

    async def cancel(self, ref, reason):
        assert ref == self.ref and reason
        self.cancel_calls += 1
        self.finished.set()
        return CancelReceipt(
            run_id=ref.run_id,
            reason=reason,
            signal_sent=True,
            escalated_to_sigkill=False,
            already_exited=False,
            finished_at="2026-08-11T00:00:01+00:00",
        )

    async def run_validation_argv(self, spec, argv, *, timeout_seconds=300.0):
        assert spec == self.spec and timeout_seconds > 0
        command = tuple(argv)
        self.validation_calls.append(command)
        empty = hashlib.sha256(b"").hexdigest()
        return ValidationReceipt(
            argv=command,
            exit_code=0,
            stdout_sha256=empty,
            stdout_size=0,
            stderr_sha256=empty,
            stderr_size=0,
            timed_out=False,
            error=None,
        )


def _fixture(tmp_path: Path):
    worker_uid = os.geteuid()
    worker_gid = os.getegid()
    control_uid = worker_uid + 1000 if worker_uid != 0 else 501
    workspace_root = tmp_path / "workspaces"
    run_root = tmp_path / "runs"
    provider_home = tmp_path / "provider-home"
    for path in (workspace_root, run_root, provider_home):
        path.mkdir(mode=0o700)
    workspace = workspace_root / "job-1"
    run_dir = run_root / "run-1"
    schema = run_dir / "input" / "result.schema.json"
    workspace.mkdir(mode=0o700)
    schema.parent.mkdir(parents=True, mode=0o700)
    schema.write_text("{}\n", encoding="utf-8")
    policy = BrokerPolicy(
        control_uid=control_uid,
        worker_uid=worker_uid,
        worker_gid=worker_gid,
        worker_user="fixture-worker",
        worker_id="codex-01",
        workspace_root=workspace_root,
        run_root=run_root,
        provider_home=provider_home,
    )
    adapter = FakeAdapter()
    sweeper = FakeSweeper()
    broker = ExecutiveWorkerBroker(adapter, policy, sweeper)
    peer = PeerCredentials(uid=control_uid, gid=worker_gid, pid=100)
    spec = {
        "run_id": "run-1",
        "job_id": "job-1",
        "worker_id": "codex-01",
        "workspace_path": str(workspace),
        "run_dir": str(run_dir),
        "prompt": "bounded harmless proof",
        "result_schema_path": str(schema),
        "codex_home": str(provider_home),
        "authorities": ["READ", "RUN_TESTS"],
        "authority": None,
        "worker_user": "fixture-worker",
        "expected_base_sha": "b" * 40,
        "allowed_artifact_paths": [],
        "isolation_roots": [str(workspace_root), str(run_root)],
        "isolation_denied_paths": [],
        "forbidden_paths": [str(tmp_path / "forbidden")],
        "expected_worker_uid": worker_uid,
        "expected_worker_gid": worker_gid,
        "shared_run_gid": worker_gid,
        "secret_canary_verdict": {},
        "require_secret_canary": True,
    }
    def identity(path: Path) -> dict:
        info = path.lstat()
        return {
            "path": str(path),
            "device": info.st_dev,
            "inode": info.st_ino,
            "mode": stat.S_IMODE(info.st_mode),
            "uid": info.st_uid,
            "gid": info.st_gid,
            "mtime_ns": info.st_mtime_ns,
        }

    manifest = {
        "schema_version": "mastermind.executive_isolation_manifest/v1",
        "roots": sorted(
            (identity(workspace_root), identity(run_root)),
            key=lambda value: value["path"],
        ),
        "entries": sorted(
            (
                {
                    "root_path": str(workspace_root),
                    "disposition": "CURRENT_WORKSPACE",
                    "identity": identity(workspace),
                },
                {
                    "root_path": str(run_root),
                    "disposition": "CURRENT_RUN",
                    "identity": identity(run_dir),
                },
            ),
            key=lambda value: value["identity"]["path"],
        ),
        "workspace_path": str(workspace),
        "run_dir": str(run_dir),
    }
    spec["isolation_manifest"] = manifest
    spec["isolation_manifest_sha256"] = hashlib.sha256(
        json.dumps(
            manifest,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()
    return broker, adapter, sweeper, peer, spec


def _request(operation: str, payload: dict, *, suffix: str = "1") -> dict:
    return {
        "schema_version": BROKER_REQUEST_SCHEMA_VERSION,
        "request_id": f"req-{suffix}",
        "operation": operation,
        "payload": payload,
    }


def test_broker_rejects_wrong_peer_and_unknown_operation(tmp_path: Path) -> None:
    async def scenario() -> None:
        broker, _adapter, _sweeper, peer, _spec = _fixture(tmp_path)
        with pytest.raises(PeerAuthorizationError):
            await broker.execute(
                _request("status", {}),
                peer=dataclasses.replace(peer, uid=peer.uid + 1),
            )
        with pytest.raises(BrokerProtocolError):
            await broker.execute(
                {
                    **_request("status", {}),
                    "operation": "shell",
                },
                peer=peer,
            )

    asyncio.run(scenario())


def test_broker_enforces_roots_principal_and_declared_argv(tmp_path: Path) -> None:
    async def scenario() -> None:
        broker, _adapter, _sweeper, peer, spec = _fixture(tmp_path)
        escaped = dict(spec, workspace_path=str(tmp_path))
        with pytest.raises(BrokerProtocolError, match="escapes"):
            await broker.execute(
                _request("start", {"launch_spec": escaped, "validation_commands": []}),
                peer=peer,
            )
        wrong_uid = dict(spec, expected_worker_uid=os.geteuid() + 42)
        with pytest.raises(BrokerProtocolError, match="principal"):
            await broker.execute(
                _request("start", {"launch_spec": wrong_uid, "validation_commands": []}),
                peer=peer,
            )
        with pytest.raises(BrokerProtocolError, match="shell"):
            await broker.execute(
                _request(
                    "start",
                    {"launch_spec": spec, "validation_commands": [["/bin/sh", "-c", "true"]]},
                ),
                peer=peer,
            )

    asyncio.run(scenario())


def test_cancel_can_interrupt_concurrent_collection_and_sweep_runs_once(tmp_path: Path) -> None:
    async def scenario() -> None:
        broker, adapter, sweeper, peer, spec = _fixture(tmp_path)
        await broker.execute(
            _request(
                "start",
                {"launch_spec": spec, "validation_commands": [["/usr/bin/true"]]},
            ),
            peer=peer,
        )
        collect = asyncio.create_task(
            broker.execute(_request("collect", {"run_id": "run-1"}, suffix="collect"), peer=peer)
        )
        await asyncio.wait_for(adapter.collect_started.wait(), timeout=1)
        cancel = await asyncio.wait_for(
            broker.execute(
                _request(
                    "cancel",
                    {"run_id": "run-1", "reason": "acceptance fault injection"},
                    suffix="cancel",
                ),
                peer=peer,
            ),
            timeout=1,
        )
        collected = await asyncio.wait_for(collect, timeout=1)
        assert cancel["ok"] is True
        assert collected["ok"] is True
        assert adapter.cancel_calls == 1
        assert sweeper.calls == ["run_terminal"]
        status = await broker.execute(
            _request("status", {"run_id": "run-1"}, suffix="status"), peer=peer
        )
        assert status["result"]["run"]["status"] == WorkerRunStatus.CANCELLED.value

    asyncio.run(scenario())


def test_validation_must_be_frozen_and_runs_only_after_collection(tmp_path: Path) -> None:
    async def scenario() -> None:
        broker, adapter, _sweeper, peer, spec = _fixture(tmp_path)
        adapter.finished.set()
        await broker.execute(
            _request(
                "start",
                {"launch_spec": spec, "validation_commands": [["/usr/bin/true"]]},
            ),
            peer=peer,
        )
        with pytest.raises(BrokerStateError, match="after worker collection"):
            await broker.execute(
                _request(
                    "validate",
                    {"run_id": "run-1", "argv": ["/usr/bin/true"], "timeout_seconds": 10},
                ),
                peer=peer,
            )
        await broker.execute(_request("collect", {"run_id": "run-1"}), peer=peer)
        with pytest.raises(BrokerProtocolError, match="not frozen"):
            await broker.execute(
                _request(
                    "validate",
                    {"run_id": "run-1", "argv": ["/usr/bin/false"], "timeout_seconds": 10},
                ),
                peer=peer,
            )
        response = await broker.execute(
            _request(
                "validate",
                {"run_id": "run-1", "argv": ["/usr/bin/true"], "timeout_seconds": 10},
            ),
            peer=peer,
        )
        assert response["result"]["validation"]["exit_code"] == 0
        assert adapter.validation_calls == [("/usr/bin/true",)]

    asyncio.run(scenario())


def test_dedicated_uid_sweep_uses_minus_one_and_requires_quiescence() -> None:
    snapshots = iter(((451, 999), (451,), (451,)))
    signals: list[tuple[int, int]] = []
    sweeper = DedicatedUIDSweeper(
        451,
        current_uid=lambda: 451,
        current_pid=lambda: 451,
        process_lister=lambda _uid: next(snapshots),
        kill_fn=lambda pid, value: signals.append((pid, value)),
        sleep_fn=lambda _seconds: None,
    )
    receipt = sweeper.sweep("test")
    assert receipt.passed is True
    assert receipt.residual_pids_before == (999,)
    assert signals == [(-1, signal.SIGKILL)]


def test_dedicated_uid_sweep_rejects_wrong_effective_uid() -> None:
    sweeper = DedicatedUIDSweeper(
        451,
        current_uid=lambda: 501,
        current_pid=lambda: 1,
        process_lister=lambda _uid: (),
    )
    with pytest.raises(DedicatedUIDError, match="does not match"):
        sweeper.sweep("test")


def test_remote_adapter_round_trips_extended_process_identity(tmp_path: Path) -> None:
    async def scenario() -> None:
        broker, _adapter, sweeper, peer, spec_value = _fixture(tmp_path)
        broker.startup_sweep = sweeper.sweep("broker_startup")
        broker.last_sweep = broker.startup_sweep
        socket_path = Path("/tmp") / f"mm-broker-{os.getpid()}-{uuid.uuid4().hex[:8]}.sock"
        server = await asyncio.start_unix_server(
            broker.handle_connection,
            path=str(socket_path),
            limit=1024 * 1024,
        )
        broker.peer_resolver = lambda _socket: peer
        client = WorkerBrokerClient(socket_path)
        remote = RemoteCodexWorkerAdapter(
            client,
            validation_commands_for_spec=lambda _spec: [["/usr/bin/true"]],
        )
        from control_plane.executive_worker_broker import _launch_spec

        launch_spec = _launch_spec(spec_value, broker.policy)
        try:
            ref = await remote.start(launch_spec)
            assert ref.session_id == ref.pid
            assert ref.effective_uid == os.geteuid()
            assert remote.launch_attestation(ref)["launch_nonce"] == "nonce-fixture"
        finally:
            server.close()
            await server.wait_closed()
            socket_path.unlink(missing_ok=True)

    asyncio.run(scenario())


def test_remote_adapter_uses_job_and_validation_timeouts(tmp_path: Path) -> None:
    async def scenario() -> None:
        broker, adapter, _sweeper, _peer, spec_value = _fixture(tmp_path)
        from control_plane.executive_worker_broker import _jsonable, _launch_spec

        spec = dataclasses.replace(
            _launch_spec(spec_value, broker.policy),
            timeout_seconds=1800.0,
            cancel_grace_seconds=15.0,
        )
        ref = await adapter.start(spec)
        adapter.finished.set()

        class RecordingClient:
            def __init__(self) -> None:
                self.calls: list[tuple[str, float | None]] = []

            async def request(self, operation, payload, *, timeout_seconds=None):
                self.calls.append((operation, timeout_seconds))
                sweep = _jsonable(FakeSweeper().sweep("remote-test"))
                if operation == "collect":
                    return {
                        "collection": _jsonable(adapter._collection()),
                        "uid_sweep": sweep,
                    }
                if operation == "validate":
                    receipt = await adapter.run_validation_argv(
                        spec,
                        payload["argv"],
                        timeout_seconds=payload["timeout_seconds"],
                    )
                    return {"validation": _jsonable(receipt), "uid_sweep": sweep}
                raise AssertionError(operation)

        client = RecordingClient()
        remote = RemoteCodexWorkerAdapter(client)  # type: ignore[arg-type]
        remote._refs[spec.run_id] = ref
        remote._specs[spec.run_id] = spec
        collected = await remote.collect_result(ref)
        assert collected.process_ref.provider_session_id == "provider-session-fixture"
        assert collected.result.provider_session_id == "provider-session-fixture"
        await remote.run_validation_argv(spec, ["/usr/bin/true"], timeout_seconds=300)
        assert client.calls == [("collect", 1860.0), ("validate", 360.0)]
        assert remote.uid_sweep_receipt(ref)["passed"] is True

    asyncio.run(scenario())


def test_remote_adapter_cleans_unbound_start_and_returns_fresh_absence_sweep() -> None:
    terminal = FakeSweeper().sweep("run_terminal").to_dict()
    fresh = FakeSweeper().sweep("status_absence").to_dict()

    class Client:
        async def request(self, operation, payload, *, timeout_seconds=None):
            if operation == "cancel":
                assert payload["run_id"] == "ATT-unbound"
                return {"uid_sweep": terminal, "cancellation": {}}
            assert operation == "status"
            assert payload == {"fresh_uid_sweep": True}
            return {
                "active_run_id": None,
                "starting": False,
                "validation_busy": False,
                "status_sweep_busy": False,
                "quarantined_reason": None,
                "status_sweep": fresh,
            }

    async def scenario() -> None:
        remote = RemoteCodexWorkerAdapter(Client())  # type: ignore[arg-type]
        sweep = await remote.cleanup_unbound_run("ATT-unbound")
        assert sweep["reason"] == "status_absence"
        assert sweep["preceding_terminal_sweep"]["reason"] == "run_terminal"

    asyncio.run(scenario())


def test_fresh_status_uid_sweep_proves_idle_absence(tmp_path: Path) -> None:
    async def scenario() -> None:
        broker, _adapter, sweeper, peer, _spec = _fixture(tmp_path)
        response = await broker.execute(
            _request(
                "status",
                {"fresh_uid_sweep": True},
                suffix="fresh-status",
            ),
            peer=peer,
        )

        result = response["result"]
        assert result["active_run_id"] is None
        assert result["status_sweep_busy"] is False
        assert result["status_sweep"]["passed"] is True
        assert result["status_sweep"]["reason"] == "status_absence"
        assert sweeper.calls == ["status_absence"]

    asyncio.run(scenario())


def test_remote_controller_absent_unknown_run_captures_fresh_status_sweep() -> None:
    sweep = FakeSweeper().sweep("status_absence").to_dict()

    class Client:
        def __init__(self) -> None:
            self.calls: list[tuple[str, dict]] = []

        def request_sync(self, operation, payload):
            self.calls.append((operation, payload))
            if payload.get("run_id"):
                from control_plane.executive_worker_broker import RemoteBrokerError

                raise RemoteBrokerError("BrokerStateError", "unknown run")
            assert payload == {"fresh_uid_sweep": True}
            return {
                "active_run_id": None,
                "starting": False,
                "validation_busy": False,
                "status_sweep_busy": False,
                "quarantined_reason": None,
                "status_sweep": sweep,
            }

    attempt = type("Attempt", (), {"attempt_id": "run-absent"})()
    client = Client()
    controller = RemoteWorkerProcessController(client)  # type: ignore[arg-type]

    from control_plane.executive_supervisor import ProcessPresence

    assert controller.presence(attempt) is ProcessPresence.ABSENT
    assert controller.uid_sweep_receipt(attempt)["reason"] == "status_absence"
    assert client.calls == [
        ("status", {"run_id": "run-absent"}),
        ("status", {"fresh_uid_sweep": True}),
    ]


def test_remote_controller_retains_terminal_and_fresh_absence_sweeps(
    tmp_path: Path,
) -> None:
    broker, adapter, _sweeper, _peer, spec_value = _fixture(tmp_path)
    from control_plane.executive_worker_broker import _jsonable, _launch_spec

    spec = _launch_spec(spec_value, broker.policy)
    ref = asyncio.run(adapter.start(spec))
    terminal = FakeSweeper().sweep("run_terminal").to_dict()
    terminal["residual_pids_before"] = [777]
    terminal["found_residuals"] = True
    fresh = FakeSweeper().sweep("status_absence").to_dict()

    class Client:
        cancelled = False

        def request_sync(self, operation, payload):
            if operation == "cancel":
                self.cancelled = True
                return {"uid_sweep": terminal, "cancellation": {}}
            if payload == {"fresh_uid_sweep": True}:
                return {
                    "active_run_id": None,
                    "starting": False,
                    "validation_busy": False,
                    "status_sweep_busy": False,
                    "quarantined_reason": None,
                    "status_sweep": fresh,
                }
            return {
                "run": {
                    "status": "CANCELLED" if self.cancelled else "RUNNING",
                    "process_ref": _jsonable(ref),
                }
            }

    identity = adapter.launch_attestation(ref)["process_identity"]
    attempt = type(
        "Attempt",
        (),
        {
            "attempt_id": ref.run_id,
            "pid": ref.pid,
            "pgid": ref.pgid,
            "process_start_identity": ref.process_start_identity,
            "boot_id": ref.boot_session_id,
            "launch_metadata": {
                "launch_attestation": {
                    "launch_nonce": ref.launch_nonce,
                    "process_identity": {
                        **identity,
                        "start_identity": ref.process_start_identity,
                        "boot_id": ref.boot_session_id,
                        "real_uid": ref.real_uid,
                        "real_gid": ref.real_gid,
                    },
                }
            },
        },
    )()
    controller = RemoteWorkerProcessController(Client())  # type: ignore[arg-type]
    controller.terminate(attempt)
    assert controller.absence_verified(attempt) is True
    assert controller.absence_verified(attempt) is True
    combined = controller.uid_sweep_receipt(attempt)
    assert combined["reason"] == "status_absence"
    assert combined["preceding_terminal_sweep"]["reason"] == "run_terminal"
    assert combined["preceding_terminal_sweep"]["residual_pids_before"] == [777]
