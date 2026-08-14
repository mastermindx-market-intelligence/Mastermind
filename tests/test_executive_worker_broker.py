"""Model-free tests for the distinct-UID Phase 1C worker broker."""
from __future__ import annotations

import asyncio
import contextlib
import dataclasses
import hashlib
import json
import os
import signal
import socket
import stat
import subprocess
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
    BROKER_RESPONSE_SCHEMA_VERSION,
    BROKER_UNAVAILABLE_ERROR_CODE,
    BrokerPolicy,
    BrokerProtocolError,
    BrokerStateError,
    DedicatedUIDError,
    DedicatedUIDSweeper,
    ExecutiveWorkerBroker,
    PeerAuthorizationError,
    PeerCredentials,
    RemoteBrokerError,
    RemoteCodexWorkerAdapter,
    RemoteWorkerProcessController,
    UIDSweepReceipt,
    UID_SWEEP_SCHEMA_VERSION,
    WorkerBrokerClient,
    _ps_pids_for_uid,
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
        allowed_supplementary_gids=frozenset(
            set(os.getgroups()) - {worker_gid}
        ),
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


def test_broker_requires_exact_root_owned_ambient_group_policy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    broker, _adapter, sweeper, _peer, _spec = _fixture(tmp_path)
    primary = broker.policy.worker_gid
    broker.policy = dataclasses.replace(
        broker.policy,
        allowed_supplementary_gids=frozenset({12, 61, 100, 396}),
    )
    monkeypatch.setattr(
        "control_plane.executive_worker_broker.os.getgroups",
        lambda: [primary, 12, 61, 100, 396],
    )
    assert broker.initialize().passed is True
    assert sweeper.calls == ["broker_startup"]

    other_root = tmp_path / "other"
    other_root.mkdir()
    other, _adapter, _sweeper, _peer, _spec = _fixture(other_root)
    other.policy = dataclasses.replace(
        other.policy,
        allowed_supplementary_gids=frozenset({12, 61, 100, 396}),
    )
    monkeypatch.setattr(
        "control_plane.executive_worker_broker.os.getgroups",
        lambda: [primary, 12, 61, 100, 396, 999],
    )
    with pytest.raises(DedicatedUIDError, match="supplementary groups differ"):
        other.initialize()


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


# ---------------------------------------------------------------------------
# Broker response framing: connection loss must never masquerade as an opaque
# protocol error.  The real-host Phase 1C acceptance failure was
# `[request_failed] Codex launch failed: BrokerProtocolError: broker response
# framing is invalid` at proof-job dispatch, reproduced two ways against the
# real broker on a tmp socket: the broker process SIGKILLed mid-handler, and
# the in-flight `handle_connection` task cancelled with the process alive.
# Both left the client's `readline()` returning b"" with no durable evidence
# of which happened.
# ---------------------------------------------------------------------------


class _HangingStartAdapter(FakeAdapter):
    """Stands in for the slow real `start` (binary SHA-256, fork/exec, sysctl).

    A launchd stop, kickstart, or reload landing inside that window is exactly
    where the cancelled-handler reproduction lives.
    """

    def __init__(self, marker: Path | None = None) -> None:
        super().__init__()
        self.start_entered = asyncio.Event()
        self.marker = marker

    async def start(self, spec):
        self.start_entered.set()
        if self.marker is not None:
            self.marker.write_text("entered\n", encoding="utf-8")
        await asyncio.Event().wait()
        raise AssertionError("the hanging start must never complete")  # pragma: no cover


class _FailingStartAdapter(FakeAdapter):
    """An ordinary (non-broker) exception raised inside the handler."""

    async def start(self, spec):
        raise ValueError("fixture adapter refused the launch")


def _socket_path() -> Path:
    # Unix socket paths are length-capped (104 bytes on Darwin); tmp_path is not
    # guaranteed to fit, so follow the house pattern used above.
    return Path("/tmp") / f"mm-broker-{os.getpid()}-{uuid.uuid4().hex[:8]}.sock"


def _start_payload(spec_value: dict) -> dict:
    return {"launch_spec": spec_value, "validation_commands": [["/usr/bin/true"]]}


def _armed_broker(tmp_path: Path, adapter):
    broker, _adapter, sweeper, peer, spec_value = _fixture(tmp_path)
    broker.adapter = adapter
    broker.startup_sweep = sweeper.sweep("broker_startup")
    broker.last_sweep = broker.startup_sweep
    broker.peer_resolver = lambda _socket: peer
    return broker, spec_value


async def _raw_exchange(socket_path: Path, request: dict) -> bytes:
    """Send one request and read every byte the broker wrote before EOF."""

    reader, writer = await asyncio.open_unix_connection(str(socket_path))
    try:
        writer.write(
            (json.dumps(request, sort_keys=True, separators=(",", ":")) + "\n").encode(
                "utf-8"
            )
        )
        await writer.drain()
        return await reader.read(1024 * 1024)
    finally:
        writer.close()
        await writer.wait_closed()


def test_dispatch_over_the_socket_returns_one_framed_success_envelope(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        broker, _spec_value = _armed_broker(tmp_path, FakeAdapter())
        socket_path = _socket_path()
        server = await asyncio.start_unix_server(
            broker.handle_connection, path=str(socket_path), limit=1024 * 1024
        )
        try:
            raw = await _raw_exchange(socket_path, _request("status", {}))
            assert raw.endswith(b"\n")
            assert raw.count(b"\n") == 1
            envelope = json.loads(raw.decode("utf-8"))
            assert envelope["schema_version"] == BROKER_RESPONSE_SCHEMA_VERSION
            assert envelope["request_id"] == "req-1"
            assert envelope["operation"] == "status"
            assert envelope["ok"] is True
            assert envelope["result"]["worker_uid"] == os.geteuid()

            client = WorkerBrokerClient(socket_path, timeout_seconds=10.0)
            result = await client.request("status", {})
            assert result["active_run_id"] is None
        finally:
            server.close()
            await server.wait_closed()
            socket_path.unlink(missing_ok=True)

    asyncio.run(scenario())


def test_ordinary_handler_failure_still_returns_one_framed_typed_envelope(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        broker, spec_value = _armed_broker(tmp_path, _FailingStartAdapter())
        socket_path = _socket_path()
        server = await asyncio.start_unix_server(
            broker.handle_connection, path=str(socket_path), limit=1024 * 1024
        )
        try:
            raw = await _raw_exchange(
                socket_path, _request("start", _start_payload(spec_value))
            )
            assert raw.endswith(b"\n")
            assert raw.count(b"\n") == 1
            envelope = json.loads(raw.decode("utf-8"))
            assert envelope["schema_version"] == BROKER_RESPONSE_SCHEMA_VERSION
            assert envelope["operation"] == "start"
            assert envelope["ok"] is False
            assert envelope["error"]["code"] == "InternalBrokerError"
            assert envelope["error"]["message"] == "broker operation failed: ValueError"
            # An ordinary failure must NOT borrow the shutting-down class.
            assert envelope["error"]["code"] != BROKER_UNAVAILABLE_ERROR_CODE
            # No traceback or adapter value reaches the socket.
            assert "refused the launch" not in raw.decode("utf-8")
        finally:
            server.close()
            await server.wait_closed()
            socket_path.unlink(missing_ok=True)

    asyncio.run(scenario())


def test_cancelled_handler_frames_unavailable_envelope_and_still_propagates(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        adapter = _HangingStartAdapter()
        broker, spec_value = _armed_broker(tmp_path, adapter)
        handler_tasks: list[asyncio.Task] = []

        async def handler(reader, writer) -> None:
            task = asyncio.current_task()
            assert task is not None
            handler_tasks.append(task)
            await broker.handle_connection(reader, writer)

        socket_path = _socket_path()
        server = await asyncio.start_unix_server(
            handler, path=str(socket_path), limit=1024 * 1024
        )
        try:
            client = WorkerBrokerClient(socket_path, timeout_seconds=20.0)
            pending = asyncio.create_task(
                client.request("start", _start_payload(spec_value))
            )
            await asyncio.wait_for(adapter.start_entered.wait(), timeout=10.0)
            assert handler_tasks, "the broker never created a connection handler task"
            handler_tasks[0].cancel()

            # 1. The control side gets a typed, newline-framed envelope, not EOF.
            with pytest.raises(RemoteBrokerError) as caught:
                await asyncio.wait_for(pending, timeout=10.0)
            assert caught.value.code == BROKER_UNAVAILABLE_ERROR_CODE
            message = str(caught.value)
            assert "broker is unavailable" in message
            assert "interrupted before the operation completed" in message
            assert "CancelledError" in message

            # 2. CancelledError is NOT swallowed: the handler task ends cancelled,
            #    so structured concurrency and launchd shutdown stay correct.
            await asyncio.wait({handler_tasks[0]}, timeout=10.0)
            assert handler_tasks[0].done() is True
            assert handler_tasks[0].cancelled() is True
        finally:
            server.close()
            await server.wait_closed()
            socket_path.unlink(missing_ok=True)

    asyncio.run(scenario())


@pytest.mark.skipif(not hasattr(os, "fork"), reason="requires POSIX fork")
def test_broker_process_death_is_named_as_connection_loss(tmp_path: Path) -> None:
    marker = tmp_path / "handler-entered"
    broker, spec_value = _armed_broker(tmp_path, _HangingStartAdapter(marker=marker))
    # `serve()` re-proves the dedicated UID, so let the real startup path run.
    broker.startup_sweep = None
    socket_path = _socket_path()
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listener.bind(str(socket_path))
    listener.listen(8)

    pid = os.fork()
    if pid == 0:  # pragma: no cover - child process
        try:
            asyncio.run(broker.serve(listener))
        except BaseException:
            pass
        finally:
            os._exit(0)
    listener.close()

    reaped = False
    try:

        async def scenario() -> None:
            client = WorkerBrokerClient(socket_path, timeout_seconds=20.0)
            pending = asyncio.create_task(
                client.request("start", _start_payload(spec_value))
            )
            for _ in range(1000):
                if marker.exists():
                    break
                await asyncio.sleep(0.02)
            else:  # pragma: no cover - defensive
                pending.cancel()
                raise AssertionError("the forked broker never entered its handler")
            os.kill(pid, signal.SIGKILL)
            with pytest.raises(BrokerProtocolError) as caught:
                await asyncio.wait_for(pending, timeout=15.0)
            message = str(caught.value)
            assert "closed the connection without sending a response" in message
            assert "0 bytes read" in message
            assert "the broker process died" in message
            # The old opaque string carried no evidence at all.
            assert "framing is invalid" not in message

        asyncio.run(scenario())
        _, status = os.waitpid(pid, 0)
        reaped = True
        assert os.WIFSIGNALED(status) is True
        assert os.WTERMSIG(status) == signal.SIGKILL
    finally:
        if not reaped:  # pragma: no cover - defensive
            with contextlib.suppress(ProcessLookupError):
                os.kill(pid, signal.SIGKILL)
            with contextlib.suppress(ChildProcessError):
                os.waitpid(pid, 0)
        socket_path.unlink(missing_ok=True)


def test_unterminated_broker_response_names_its_byte_count(tmp_path: Path) -> None:
    partial = b'{"schema_version":"mastermind.executive_worker_bro'

    async def scenario() -> None:
        socket_path = _socket_path()

        async def truncating(reader, writer) -> None:
            await reader.readline()
            writer.write(partial)
            await writer.drain()
            writer.close()
            await writer.wait_closed()

        server = await asyncio.start_unix_server(
            truncating, path=str(socket_path), limit=1024 * 1024
        )
        try:
            client = WorkerBrokerClient(socket_path, timeout_seconds=10.0)
            with pytest.raises(BrokerProtocolError) as caught:
                await client.request("status", {})
            message = str(caught.value)
            assert "broker response is unterminated" in message
            assert f"{len(partial)} bytes read" in message
            assert "no newline terminator" in message
            # Distinct from the clean-EOF diagnosis and from the old opaque one.
            assert "closed the connection without sending a response" not in message
            assert "framing is invalid" not in message
            # Bounded, sanitized excerpt only -- never the whole payload.
            assert "schema_version" in message
            assert partial.decode("ascii") not in message
        finally:
            server.close()
            await server.wait_closed()
            socket_path.unlink(missing_ok=True)

    asyncio.run(scenario())


# (svuid, ruid, euid, pid) rows for a fake `/bin/ps`.  Every row keeps
# svuid == ruid, which is what the real host shows: adding the saved-uid term
# changed no expectation in these tables, it only closes a window nothing on
# this host currently occupies.
_PS_ROWS_WITH_SETUID_RESIDUAL = (
    (0, 0, 0, 1),
    (451, 451, 451, 451),  # the broker itself
    (451, 451, 0, 999),  # setuid helper started by the worker UID: ruid=451, uid=0
    (0, 0, 451, 888),  # root-real process observed with the worker euid
    (777, 777, 777, 777),  # an unrelated principal
)
_PS_ROWS_QUIESCENT = (
    (0, 0, 0, 1),
    (451, 451, 451, 451),
    (777, 777, 777, 777),
)
# Reachable ONLY via the saved uid: neither ruid nor euid names the worker.
_PS_ROWS_SAVED_UID_ONLY = (
    (0, 0, 0, 1),
    (451, 451, 451, 451),
    (451, 0, 0, 555),
)

_REAL_SUBPROCESS_RUN = subprocess.run


def _fake_ps(rows_holder: list):
    """A `/bin/ps` that honours whichever uid columns the caller requests.

    `subprocess.run` is an attribute of the shared `subprocess` module, so
    patching it is process-wide for the duration of the test.  Anything that is
    not our `/bin/ps` probe therefore DELEGATES to the real implementation
    instead of asserting, so an unrelated caller cannot be broken by the patch.

    Mirrors the real Darwin behaviour verified on the host: an unsupported
    keyword exits non-zero while still printing the remaining columns.
    """

    index = {"svuid": 0, "ruid": 1, "uid": 2, "euid": 2, "pid": 3}

    def run(argv, **kwargs):
        if not (
            isinstance(argv, (list, tuple))
            and len(argv) >= 3
            and argv[0] == "/bin/ps"
            and "-axo" in argv
        ):
            return _REAL_SUBPROCESS_RUN(argv, **kwargs)
        columns = [item.rstrip("=") for item in argv[argv.index("-axo") + 1].split(",")]
        known = [item for item in columns if item in index]
        unknown = [item for item in columns if item not in index]
        text = "".join(
            " ".join(str(row[index[column]]) for column in known) + "\n"
            for row in rows_holder[0]
        )
        return subprocess.CompletedProcess(
            argv,
            1 if unknown else 0,
            text,
            f"ps: {unknown[0]}: keyword not found\n" if unknown else "",
        )

    return run


def test_uid_enumeration_counts_the_real_uid_the_broadcast_can_kill(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    holder = [_PS_ROWS_WITH_SETUID_RESIDUAL]
    monkeypatch.setattr(
        "control_plane.executive_worker_broker.subprocess.run", _fake_ps(holder)
    )
    pids = _ps_pids_for_uid(451)
    # ruid=451/uid=0: reachable by Darwin's kill(-1) broadcast and invisible to
    # the old effective-uid-only projection, so `passed` could certify
    # quiescence with this process still alive.
    assert 999 in pids
    # ruid=0/svuid=0/uid=451 is NOT broadcast-reachable -- measured on the host,
    # kill(pid, 0) against exactly this shape returns EPERM, because the kernel
    # checks the receiver's real or SAVED uid, not its effective one.  It is
    # counted because the union is deliberately wide: over-reporting fails the
    # sweep closed, it can never certify a false absence.
    assert 888 in pids
    assert 777 not in pids

    signals: list[tuple[int, int]] = []

    def kill_fn(target: int, value: int) -> None:
        # Deliberately stronger than the real kernel: this clears 888 too, which
        # a real kill(-1) from uid 451 could not.  The sweep's timing/retry
        # behaviour, not the kernel's permission model, is what is under test.
        signals.append((target, value))
        holder[0] = _PS_ROWS_QUIESCENT

    sweeper = DedicatedUIDSweeper(
        451,
        current_uid=lambda: 451,
        current_pid=lambda: 451,
        process_lister=_ps_pids_for_uid,
        kill_fn=kill_fn,
        sleep_fn=lambda _seconds: None,
    )
    receipt = sweeper.sweep("test")
    assert receipt.residual_pids_before == (888, 999)
    assert receipt.residual_pids_after == ()
    assert receipt.passed is True
    assert signals == [(-1, signal.SIGKILL)]


def test_uid_enumeration_counts_a_saved_uid_only_process(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """svuid==W with neither ruid nor euid matching is still signal-reachable."""

    holder = [_PS_ROWS_SAVED_UID_ONLY]
    monkeypatch.setattr(
        "control_plane.executive_worker_broker.subprocess.run", _fake_ps(holder)
    )
    assert 555 in _ps_pids_for_uid(451)


def test_uid_enumeration_still_proves_quiescence_for_an_absent_uid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    holder = [_PS_ROWS_QUIESCENT]
    monkeypatch.setattr(
        "control_plane.executive_worker_broker.subprocess.run", _fake_ps(holder)
    )
    assert _ps_pids_for_uid(451) == (451,)
    signals: list[tuple[int, int]] = []
    sweeper = DedicatedUIDSweeper(
        451,
        current_uid=lambda: 451,
        current_pid=lambda: 451,
        process_lister=_ps_pids_for_uid,
        kill_fn=lambda target, value: signals.append((target, value)),
        sleep_fn=lambda _seconds: None,
    )
    receipt = sweeper.sweep("test")
    assert receipt.residual_pids_before == ()
    assert receipt.passed is True
    assert receipt.signal_sent is False
    assert signals == []


def test_uid_enumeration_fails_closed_without_a_saved_uid_column(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A ps missing a uid keyword must break the proof, never degrade to euid."""

    holder = [_PS_ROWS_WITH_SETUID_RESIDUAL]
    fake = _fake_ps(holder)

    def run(argv, **kwargs):
        # Drop `svuid` the way a ps without that keyword would: non-zero exit
        # AND short rows.  Either signal alone must fail the proof closed.
        if isinstance(argv, (list, tuple)) and argv[0] == "/bin/ps":
            argv = [item.replace("svuid=,", "nosuchcol=,") for item in argv]
        return fake(argv, **kwargs)

    monkeypatch.setattr("control_plane.executive_worker_broker.subprocess.run", run)
    with pytest.raises(DedicatedUIDError, match="cannot inspect"):
        _ps_pids_for_uid(451)


def test_uid_enumeration_refuses_a_wrong_arity_projection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Short rows must raise, not be skipped -- skipping them fakes absence."""

    def run(argv, **_kwargs):
        # Exit 0 (so the returncode check cannot help) with one short row
        # among well-formed ones.
        return subprocess.CompletedProcess(
            argv, 0, "0 0 0 1\n451 451 451 451\n451 451 999\n", ""
        )

    monkeypatch.setattr("control_plane.executive_worker_broker.subprocess.run", run)
    with pytest.raises(DedicatedUIDError, match="malformed"):
        _ps_pids_for_uid(451)


def test_uid_enumeration_refuses_a_non_numeric_projection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A non-numeric column must raise, not be skipped."""

    def run(argv, **_kwargs):
        return subprocess.CompletedProcess(
            argv, 0, "0 0 0 1\n451 451 451 451\n451 451 451 notapid\n", ""
        )

    monkeypatch.setattr("control_plane.executive_worker_broker.subprocess.run", run)
    with pytest.raises(DedicatedUIDError, match="malformed"):
        _ps_pids_for_uid(451)


def test_uid_enumeration_refuses_an_empty_projection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """rc 0 with no rows must NEVER read as proven quiescence.

    Without this guard the sweep returns `residual_pids_after=()` and
    `passed=True` from a reader that observed nothing at all -- the exact
    shape of a false absence proof that `executive_supervisor` would then
    accept as terminal.
    """

    monkeypatch.setattr(
        "control_plane.executive_worker_broker.subprocess.run",
        lambda argv, **_kwargs: subprocess.CompletedProcess(argv, 0, "", ""),
    )
    with pytest.raises(DedicatedUIDError, match="empty"):
        _ps_pids_for_uid(451)

    sweeper = DedicatedUIDSweeper(
        451,
        current_uid=lambda: 451,
        current_pid=lambda: 451,
        process_lister=_ps_pids_for_uid,
        kill_fn=lambda _target, _value: None,
        sleep_fn=lambda _seconds: None,
    )
    # The sweeper must propagate, not hand back a passing receipt.
    with pytest.raises(DedicatedUIDError, match="empty"):
        sweeper.sweep("test")


def test_best_effort_envelope_never_masks_the_interrupt(tmp_path: Path) -> None:
    """A dead peer must not turn a cancellation into a ConnectionResetError."""

    async def scenario() -> None:
        adapter = _HangingStartAdapter()
        broker, spec_value = _armed_broker(tmp_path, adapter)
        handler_tasks: list[asyncio.Task] = []
        captured: dict[str, asyncio.StreamWriter] = {}

        async def handler(reader, writer) -> None:
            task = asyncio.current_task()
            assert task is not None
            handler_tasks.append(task)
            captured["writer"] = writer
            await broker.handle_connection(reader, writer)

        socket_path = _socket_path()
        server = await asyncio.start_unix_server(
            handler, path=str(socket_path), limit=1024 * 1024
        )
        try:
            reader, writer = await asyncio.open_unix_connection(str(socket_path))
            request = _request("start", _start_payload(spec_value))
            writer.write(
                (json.dumps(request, sort_keys=True, separators=(",", ":")) + "\n").encode(
                    "utf-8"
                )
            )
            await writer.drain()
            await asyncio.wait_for(adapter.start_entered.wait(), timeout=10.0)

            # Take the peer away, so the best-effort envelope write has nowhere
            # to go and raises on drain.
            captured["writer"].transport.abort()
            for _ in range(10):
                await asyncio.sleep(0)
            handler_tasks[0].cancel()
            await asyncio.wait({handler_tasks[0]}, timeout=10.0)
            assert handler_tasks[0].done() is True
            # The interrupt stays authoritative: not replaced by the write's
            # own ConnectionResetError.
            assert handler_tasks[0].cancelled() is True
            writer.close()
            with contextlib.suppress(Exception):
                await writer.wait_closed()
        finally:
            server.close()
            await server.wait_closed()
            socket_path.unlink(missing_ok=True)

    asyncio.run(scenario())


def test_pre_parse_cancellation_reports_connection_loss_not_identity_mismatch(
    tmp_path: Path,
) -> None:
    """An interrupt before the request is parsed must not emit an envelope.

    The same `asyncio.run` shutdown cancels handlers still parked in
    `readline()`.  An envelope built from the `"invalid"` sentinel fails the
    client's request-id check and surfaces as `broker response identity does
    not match the request` -- a protocol/identity bug that never happened,
    and a strictly worse diagnosis than the accurate clean-EOF message.
    """

    async def scenario() -> None:
        broker, _spec_value = _armed_broker(tmp_path, FakeAdapter())
        handler_tasks: list[asyncio.Task] = []
        parked = asyncio.Event()

        async def handler(reader, writer) -> None:
            task = asyncio.current_task()
            assert task is not None
            handler_tasks.append(task)
            # A reader that yields neither a line nor EOF, so the handler parks
            # in `readline()` -- the real pre-parse window.  Nothing is awaited
            # between `parked.set()` and that suspension, so the wait below is
            # a deterministic signal that the handler is in it.  The writer is
            # the genuine socket to the real client.
            stalled = asyncio.StreamReader()
            parked.set()
            await broker.handle_connection(stalled, writer)

        socket_path = _socket_path()
        server = await asyncio.start_unix_server(
            handler, path=str(socket_path), limit=1024 * 1024
        )
        try:
            client = WorkerBrokerClient(socket_path, timeout_seconds=20.0)
            pending = asyncio.create_task(client.request("status", {}))
            await asyncio.wait_for(parked.wait(), timeout=10.0)
            handler_tasks[0].cancel()

            with pytest.raises(BrokerProtocolError) as caught:
                await asyncio.wait_for(pending, timeout=10.0)
            message = str(caught.value)
            assert "closed the connection without sending a response" in message
            assert "0 bytes read" in message
            assert "identity does not match" not in message

            await asyncio.wait({handler_tasks[0]}, timeout=10.0)
            assert handler_tasks[0].cancelled() is True
        finally:
            server.close()
            await server.wait_closed()
            socket_path.unlink(missing_ok=True)

    asyncio.run(scenario())


class _DrainFailsOnceWriter:
    """Real writer whose first `drain()` fails after its `write()` succeeded."""

    def __init__(self, inner: asyncio.StreamWriter) -> None:
        self._inner = inner
        self.frames: list[bytes] = []
        self.drain_calls = 0

    def get_extra_info(self, name, default=None):
        return self._inner.get_extra_info(name, default)

    def write(self, data) -> None:
        self.frames.append(bytes(data))
        self._inner.write(data)

    async def drain(self) -> None:
        self.drain_calls += 1
        if self.drain_calls == 1:
            raise ConnectionResetError("Connection lost")
        await self._inner.drain()

    def close(self) -> None:
        self._inner.close()

    async def wait_closed(self) -> None:
        await self._inner.wait_closed()


def test_a_failed_drain_never_puts_a_second_envelope_on_the_wire(
    tmp_path: Path,
) -> None:
    """Once bytes are handed to the transport, no second envelope may follow.

    `close()` still flushes the buffer, so appending a second frame would put
    two documents on a stream the client reads with one `readline()`.
    """

    async def scenario() -> None:
        broker, _spec_value = _armed_broker(tmp_path, FakeAdapter())
        wrappers: list[_DrainFailsOnceWriter] = []
        finished = asyncio.Event()

        async def handler(reader, writer) -> None:
            wrapped = _DrainFailsOnceWriter(writer)
            wrappers.append(wrapped)
            try:
                with contextlib.suppress(ConnectionResetError):
                    await broker.handle_connection(reader, wrapped)  # type: ignore[arg-type]
            finally:
                finished.set()

        socket_path = _socket_path()
        server = await asyncio.start_unix_server(
            handler, path=str(socket_path), limit=1024 * 1024
        )
        try:
            raw = await _raw_exchange(socket_path, _request("status", {}))
            await asyncio.wait_for(finished.wait(), timeout=10.0)
            assert wrappers[0].drain_calls >= 1
            # Exactly one envelope was framed...
            assert len(wrappers[0].frames) == 1
            # ...and exactly one reached the wire.
            assert raw.count(b"\n") == 1
            assert raw.endswith(b"\n")
            assert json.loads(raw.decode("utf-8"))["ok"] is True
        finally:
            server.close()
            await server.wait_closed()
            socket_path.unlink(missing_ok=True)

    asyncio.run(scenario())


def test_unterminated_response_redacts_secret_shaped_runs(tmp_path: Path) -> None:
    """A wire excerpt is externally-produced text: redact before bounding.

    Ordering is what this pins.  Slicing the excerpt to its 48-byte bound
    FIRST would cut the 64-hex token down to the ~28 characters that fit,
    below every shape threshold in `sanitize_external_text`, and print that
    fragment verbatim.  Redacting the whole window first and bounding last
    keeps the token off the wire entirely.
    """

    token = b"0123456789abcdef" * 4  # 64 hex: a credential shape
    digest = b"a" * 40  # 40 hex: also redacted here, unlike acceptance.py
    partial = b'{"result":{"token":"' + token + b'","sha256":"' + digest + b'"'

    async def scenario() -> None:
        socket_path = _socket_path()

        async def truncating(reader, writer) -> None:
            await reader.readline()
            writer.write(partial)
            await writer.drain()
            writer.close()
            await writer.wait_closed()

        server = await asyncio.start_unix_server(
            truncating, path=str(socket_path), limit=1024 * 1024
        )
        try:
            client = WorkerBrokerClient(socket_path, timeout_seconds=10.0)
            with pytest.raises(BrokerProtocolError) as caught:
                await client.request("status", {})
            message = str(caught.value)

            # The secrets are gone -- whole, and in every partial form the
            # 48-byte bound could have left behind.
            assert token.decode("ascii") not in message
            assert digest.decode("ascii") not in message
            for width in (28, 32, 40, 48):
                assert token.decode("ascii")[:width] not in message
            assert "<redacted>" in message

            # ...while the diagnosis itself survives intact.
            assert "broker response is unterminated" in message
            assert f"{len(partial)} bytes read" in message
            assert "no newline terminator" in message
        finally:
            server.close()
            await server.wait_closed()
            socket_path.unlink(missing_ok=True)

    asyncio.run(scenario())
