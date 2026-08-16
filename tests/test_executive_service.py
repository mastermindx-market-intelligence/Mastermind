"""Model-free tests for the private Executive OS control service."""
from __future__ import annotations

import asyncio
import errno
import hashlib
import json
import os
import shutil
import socket
import stat
import subprocess
import tempfile
import ast
from dataclasses import dataclass
from pathlib import Path

import pytest

from common.redaction import TRUNCATION_MARKER
from control_plane.executive_runtime import JobPayload, JobStatus, Runtime
from control_plane.executive_canary import (
    PrincipalIdentity,
    SecretCanaryConfig,
    run_secret_canary,
)
from control_plane.executive_service import (
    CONTROL_PROTOCOL_VERSION,
    ExecutiveControlService,
    ServiceConfig,
    ServiceError,
    send_control_request,
)
from control_plane.executive_workspace import (
    LAUNCH_CLEAN_STATUS_ARGS,
    LAUNCH_CLEAN_UNTRACKED_ARGS,
    WorkspaceError,
)
from control_plane import executive_service as es_mod
from scripts import executive_os_phase1c as service_cli


@dataclass
class _Active:
    lease: object


class _FakeSupervisor:
    def __init__(self, runtime: Runtime, *, finish_gate: asyncio.Event | None = None) -> None:
        self.runtime = runtime
        self.finish_gate = finish_gate
        self.requeue_values: list[bool] = []
        self.started_jobs: list[str] = []

    def reconcile_restart(self, *, requeue_lost: bool = False):
        self.requeue_values.append(requeue_lost)
        return []

    async def start_job(self, job_id: str):
        lease = self.runtime.broker.claim(job_id, lease_owner="service-fixture")
        assert lease is not None
        attempt = lease.attempt
        self.runtime.attempts.record_process(
            attempt.attempt_id,
            fence_generation=attempt.fence_generation,
            lease_token=lease.lease_token,
            provider_session_id="fixture-provider-session",
            launch_metadata={"fixture": "redacted"},
        )
        self.runtime.attempts.mark_running(
            attempt.attempt_id,
            fence_generation=attempt.fence_generation,
            lease_token=lease.lease_token,
        )
        self.started_jobs.append(job_id)
        return _Active(lease=lease)

    async def finish_job(self, active: _Active):
        if self.finish_gate is not None:
            await self.finish_gate.wait()
        lease = active.lease
        attempt = lease.attempt
        job = self.runtime.jobs.get_job(attempt.job_id)
        assert job is not None
        if job.status is JobStatus.CANCEL_REQUESTED:
            return self.runtime.attempts.acknowledge_cancel(
                attempt.attempt_id,
                fence_generation=attempt.fence_generation,
                lease_token=lease.lease_token,
            )
        payload = JobPayload(
            summary="fixed proof complete",
            completed_steps=["fixture"],
            current_state="complete",
        )
        self.runtime.attempts.checkpoint_attempt(
            attempt.attempt_id,
            fence_generation=attempt.fence_generation,
            lease_token=lease.lease_token,
            payload=payload,
        )
        return self.runtime.attempts.complete_attempt(
            attempt.attempt_id,
            fence_generation=attempt.fence_generation,
            lease_token=lease.lease_token,
            payload=payload,
        )


class _FakeBackup:
    def __init__(self) -> None:
        self.created: list[Path] = []
        self.verified: list[tuple[Path, Path | None]] = []

    def create_online_backup(self, store, destination_dir: Path):
        path = destination_dir / "fixture.sqlite3"
        path.write_bytes(b"fixture-backup")
        path.chmod(0o600)
        manifest = path.with_suffix(".manifest.json")
        manifest.write_text("{}\n", encoding="utf-8")
        manifest.chmod(0o600)
        self.created.append(path)
        return {"database_path": path, "source": store.path.name}

    def verify_backup(self, database_path: Path, manifest_path: Path | None = None):
        self.verified.append((database_path, manifest_path))
        return {"ok": database_path.is_file(), "database_path": database_path}


@pytest.fixture
def short_socket_root():
    # Darwin's sockaddr_un path ceiling is only 104 bytes; pytest's native
    # temporary path is intentionally much longer than a production /var/run path.
    value = Path(tempfile.mkdtemp(prefix="mmx-es-", dir="/tmp"))
    try:
        yield value
    finally:
        shutil.rmtree(value, ignore_errors=True)


def _source_repository(tmp_path: Path) -> tuple[Path, str]:
    source = tmp_path / "proof-source"
    if not (source / ".git").is_dir():
        source.mkdir(parents=True)
        subprocess.run(["git", "init", "-q", str(source)], check=True)
        subprocess.run(
            ["git", "-C", str(source), "config", "user.name", "Executive Fixture"],
            check=True,
        )
        subprocess.run(
            [
                "git",
                "-C",
                str(source),
                "config",
                "user.email",
                "executive-fixture@example.invalid",
            ],
            check=True,
        )
        (source / "README.md").write_text("# Exact proof base\n", encoding="utf-8")
        (source / ".codex").mkdir()
        (source / ".codex/config.toml").write_text(
            '[shell_environment_policy]\ninherit = "none"\n', encoding="utf-8"
        )
        subprocess.run(["git", "-C", str(source), "add", "."], check=True)
        subprocess.run(
            ["git", "-C", str(source), "commit", "-q", "-m", "proof base"],
            check=True,
        )
    base_sha = subprocess.run(
        ["git", "-C", str(source), "rev-parse", "HEAD"],
        check=True,
        stdout=subprocess.PIPE,
        text=True,
    ).stdout.strip()
    return source, base_sha


def _config(tmp_path: Path, *, socket_root: Path | None = None, **overrides) -> ServiceConfig:
    source, base_sha = _source_repository(tmp_path)
    values = {
        "runtime_root": tmp_path / "runtime",
        "socket_path": (socket_root or tmp_path / "run") / "executive.sock",
        "proof_source_repository": source,
        "proof_workspace_root": tmp_path / "workspaces",
        "proof_base_sha": base_sha,
        "proof_shared_gid": os.getegid(),
        "backup_root": tmp_path / "backups",
        "allowed_peer_uids": (os.geteuid(),),
        "shutdown_grace_seconds": 0.1,
    }
    values.update(overrides)
    return ServiceConfig(**values)


def _service(
    tmp_path: Path,
    *,
    socket_root: Path | None = None,
    finish_gate: asyncio.Event | None = None,
    backup: _FakeBackup | None = None,
    config: ServiceConfig | None = None,
):
    holder = {}

    def factory(runtime: Runtime):
        supervisor = _FakeSupervisor(runtime, finish_gate=finish_gate)
        holder["supervisor"] = supervisor
        return supervisor

    service = ExecutiveControlService(
        config or _config(tmp_path, socket_root=socket_root),
        supervisor_factory=factory,
        backup_backend=backup,
    )
    return service, holder


async def _request(service: ExecutiveControlService, command: str, args=None):
    return await send_control_request(service.socket_path, command, args or {})


async def _raw_request(path: Path, raw: bytes) -> dict:
    reader, writer = await asyncio.open_unix_connection(str(path))
    try:
        writer.write(raw)
        await writer.drain()
        response = await reader.readline()
        return json.loads(response)
    finally:
        writer.close()
        await writer.wait_closed()


def test_private_unix_service_round_trip_and_fixed_proof_lifecycle(
    tmp_path: Path, short_socket_root: Path, monkeypatch: pytest.MonkeyPatch
):
    async def exercise():
        service, holder = _service(tmp_path, socket_root=short_socket_root)

        async def tcp_must_not_start(*args, **kwargs):  # pragma: no cover - assertion hook
            raise AssertionError("Executive service must never create a TCP listener")

        monkeypatch.setattr(asyncio, "start_server", tcp_must_not_start)
        await service.start()
        try:
            assert service._server is not None
            assert service._server.sockets
            assert all(item.family == socket.AF_UNIX for item in service._server.sockets)
            assert stat.S_IMODE(service.socket_path.stat().st_mode) == 0o600
            assert stat.S_IMODE(service.socket_path.parent.stat().st_mode) == 0o700
            assert service.running_marker_path.is_file()
            assert service.service_lock_path.is_file()
            assert stat.S_IMODE(service.running_marker_path.stat().st_mode) == 0o600
            assert stat.S_IMODE(service.service_lock_path.stat().st_mode) == 0o600

            status = await _request(service, "status")
            assert status["ok"] is True
            assert status["result"]["protocol"] == CONTROL_PROTOCOL_VERSION
            assert status["result"]["startup_reconciliation"] == []
            assert holder["supervisor"].requeue_values == [False]

            health = await _request(service, "health")
            assert health["result"]["ok"] is True
            assert health["result"]["journal_mode"].lower() == "wal"
            assert health["result"]["foreign_key_violations"] == 0

            registered = await _request(service, "register-worker")
            assert registered["result"]["worker_id"] == "codex-01"
            # Registration is idempotent only for the exact configured identity.
            assert (await _request(service, "register-worker"))["ok"] is True

            created = await _request(service, "create-proof-job")
            assert created["ok"] is True
            job_id = created["result"]["job_id"]
            first_workspace = Path(created["result"]["worktree"])
            assert first_workspace.parent == service.config.proof_workspace_root
            assert first_workspace.name.startswith("proof-")
            assert created["result"]["branch"].endswith(first_workspace.name[6:])
            assert subprocess.run(
                ["git", "-C", str(first_workspace), "rev-parse", "HEAD"],
                check=True,
                stdout=subprocess.PIPE,
                text=True,
            ).stdout.strip() == service.config.proof_base_sha
            assert subprocess.run(
                ["git", "-C", str(first_workspace), "remote"],
                check=True,
                stdout=subprocess.PIPE,
                text=True,
            ).stdout == ""
            assert stat.S_IMODE((first_workspace / ".git").stat().st_mode) & 0o020 == 0
            assert (
                stat.S_IMODE((first_workspace / ".codex/config.toml").stat().st_mode)
                & 0o020
                == 0
            )
            proof_parent = (
                first_workspace / "research/executive_os_phase1c_worker_proof"
            )
            assert stat.S_IMODE(proof_parent.stat().st_mode) == 0o770
            assert created["result"]["requested_authorities"] == [
                "READ",
                "RESEARCH",
                "RUN_TESTS",
                "WRITE_BRANCH",
            ]
            assert created["result"]["allowed_write_paths"] == [
                "research/executive_os_phase1c_worker_proof/receipt.md"
            ]
            assert len(created["result"]["validation_commands"]) == 1

            dispatched = await _request(service, "dispatch", {"job_id": job_id})
            assert dispatched["ok"] is True
            attempt_id = dispatched["result"]["attempt"]["attempt_id"]
            for _ in range(100):
                inspected = await _request(service, "job", {"job_id": job_id})
                if inspected["result"]["status"] == "COMPLETED":
                    break
                await asyncio.sleep(0.01)
            assert inspected["result"]["status"] == "COMPLETED"
            attempt = await _request(service, "attempt", {"attempt_id": attempt_id})
            assert attempt["result"]["status"] == "COMPLETED"
            assert "lease_token" not in json.dumps(attempt, sort_keys=True)

            # A successful worker leaves its proof artifact behind.  A second
            # proof must receive a fresh workspace rather than inherit it.
            first_artifact = (
                first_workspace
                / "research/executive_os_phase1c_worker_proof/receipt.md"
            )
            first_artifact.parent.mkdir(parents=True, exist_ok=True)
            first_artifact.write_text("completed first proof\n", encoding="utf-8")
            second = await _request(service, "create-proof-job")
            assert second["ok"] is True
            second_workspace = Path(second["result"]["worktree"])
            assert second_workspace != first_workspace
            assert not (second_workspace / first_artifact.relative_to(first_workspace)).exists()
            assert subprocess.run(
                ["git", "-C", str(second_workspace), "status", "--porcelain=v1"],
                check=True,
                stdout=subprocess.PIPE,
                text=True,
            ).stdout == ""
            assert (await _request(service, "workers"))["result"][0]["worker_id"] == "codex-01"
            assert (await _request(service, "jobs"))["result"][0]["job_id"] == job_id
        finally:
            await service.close()
        assert not service.socket_path.exists()
        assert not service.running_marker_path.exists()

    asyncio.run(exercise())


def test_workspace_creation_cannot_cross_manifest_to_worker_start_window(
    tmp_path: Path, short_socket_root: Path
):
    async def exercise() -> None:
        finish_gate = asyncio.Event()
        start_release = asyncio.Event()
        start_entered = asyncio.Event()
        service, holder = _service(
            tmp_path,
            socket_root=short_socket_root,
            finish_gate=finish_gate,
        )
        await service.start()
        try:
            await _request(service, "register-worker")
            proof = await _request(service, "create-proof-job")
            job_id = proof["result"]["job_id"]
            supervisor = holder["supervisor"]
            original_start = supervisor.start_job

            async def paused_start(value: str):
                # This point represents the interval after the control-side
                # manifest snapshot has begun but before broker start/spawn has
                # returned.  The service lifecycle lock must remain held.
                start_entered.set()
                await start_release.wait()
                return await original_start(value)

            supervisor.start_job = paused_start
            dispatch_task = asyncio.create_task(
                _request(service, "dispatch", {"job_id": job_id})
            )
            await asyncio.wait_for(start_entered.wait(), timeout=1)
            assert service._workspace_lock.locked() is True

            before = sorted(
                path.name for path in service.config.proof_workspace_root.iterdir()
            )
            create_task = asyncio.create_task(
                _request(service, "create-proof-job")
            )
            await asyncio.sleep(0)
            await asyncio.sleep(0)
            assert create_task.done() is False

            start_release.set()
            dispatched = await asyncio.wait_for(dispatch_task, timeout=1)
            assert dispatched["ok"] is True
            refused = await asyncio.wait_for(create_task, timeout=1)
            assert refused["ok"] is False
            assert "while a worker dispatch is active" in refused["error"]["message"]
            assert sorted(
                path.name for path in service.config.proof_workspace_root.iterdir()
            ) == before
        finally:
            start_release.set()
            finish_gate.set()
            await service.close()

    asyncio.run(exercise())


def test_protocol_rejects_malformed_oversized_unknown_and_argument_injection(
    tmp_path: Path, short_socket_root: Path
):
    async def exercise():
        config = _config(tmp_path, socket_root=short_socket_root, max_request_bytes=1024)
        service, _holder = _service(tmp_path, config=config)
        await service.start()
        try:
            malformed = await _raw_request(service.socket_path, b"{not-json}\n")
            assert malformed["error"]["code"] == "invalid_json"

            wrong_shape = await _raw_request(
                service.socket_path,
                json.dumps({"command": "status"}).encode() + b"\n",
            )
            assert wrong_shape["error"]["code"] == "request_failed"

            unknown = await _request(service, "execute-shell", {"argv": ["/bin/sh"]})
            assert unknown["ok"] is False
            assert "unknown control command" in unknown["error"]["message"]

            injected = await _request(
                service,
                "create-proof-job",
                {"objective": "run arbitrary command", "validation_command": ["/bin/sh"]},
            )
            assert injected["ok"] is False
            assert "exactly these arguments: none" in injected["error"]["message"]

            oversized = await _raw_request(service.socket_path, b"x" * 2048 + b"\n")
            assert oversized["error"]["code"] == "request_too_large"
        finally:
            await service.close()

    asyncio.run(exercise())


def test_service_dispatch_and_requeue_refuse_nonproof_jobs(
    tmp_path: Path, short_socket_root: Path
):
    async def exercise():
        service, _holder = _service(tmp_path, socket_root=short_socket_root)
        await service.start()
        try:
            runtime = service.runtime
            assert runtime is not None
            await _request(service, "register-worker")
            foreign = runtime.jobs.create_job(
                "Unreviewed operator-created job",
                constraints={
                    "provider": "codex",
                    "eligible_quota_classes": ["codex-native"],
                },
                requested_authorities=["READ"],
            )
            denied = await _request(service, "dispatch", {"job_id": foreign.job_id})
            assert denied["ok"] is False
            assert "fixed harmless proof job" in denied["error"]["message"]

            proof = await _request(service, "create-proof-job")
            proof_id = proof["result"]["job_id"]
            proof_workspace = Path(proof["result"]["worktree"])
            interrupted_artifact = (
                proof_workspace
                / "research/executive_os_phase1c_worker_proof/receipt.md"
            )
            interrupted_artifact.parent.mkdir(parents=True, exist_ok=True)
            interrupted_artifact.write_text(
                "interrupted evidence must survive\n", encoding="utf-8"
            )
            interrupted_inode = proof_workspace.stat().st_ino
            lease = runtime.broker.claim(proof_id, lease_owner="lost-fixture")
            assert lease is not None
            runtime.attempts.record_process(
                lease.attempt.attempt_id,
                fence_generation=lease.attempt.fence_generation,
                lease_token=lease.lease_token,
                provider_session_id="missing-provider-session",
            )
            runtime.attempts.mark_running(
                lease.attempt.attempt_id,
                fence_generation=lease.attempt.fence_generation,
                lease_token=lease.lease_token,
            )
            runtime.attempts.mark_lost(
                lease.attempt.attempt_id,
                fence_generation=lease.attempt.fence_generation,
                lease_token=lease.lease_token,
                reason="verified fixture absence",
                verified_process_absent=True,
            )
            proof_workspace.chmod(0o700)
            requeued = await _request(service, "requeue", {"job_id": proof_id})
            assert requeued["result"]["status"] == "QUEUED"
            assert requeued["result"]["checkpoint"] is None
            rotation = requeued["result"]["workspace_rotation"]
            archive = Path(rotation["archive_path"])
            receipt_path = Path(rotation["receipt_path"])
            assert archive.parent.parent.parent == service.config.proof_workspace_root
            assert archive.name == lease.attempt.attempt_id
            assert (
                archive / interrupted_artifact.relative_to(proof_workspace)
            ).read_text(encoding="utf-8") == "interrupted evidence must survive\n"
            assert proof_workspace.is_dir()
            assert proof_workspace.stat().st_ino != interrupted_inode
            assert stat.S_IMODE(proof_workspace.stat().st_mode) & 0o070 == 0o050
            assert stat.S_IMODE(archive.stat().st_mode) == 0o700
            index = proof_workspace / ".git" / "index"
            index_mode = stat.S_IMODE(index.stat().st_mode)
            assert index.stat().st_gid == os.getegid()
            assert index_mode & stat.S_IRGRP
            assert not index_mode & stat.S_IWGRP
            assert not index_mode & stat.S_IRWXO
            assert not (proof_workspace / ".git" / "index.lock").exists()
            assert subprocess.run(
                ["git", "-C", str(proof_workspace), "status", "--porcelain=v1"],
                check=True,
                stdout=subprocess.PIPE,
                text=True,
            ).stdout == ""
            assert subprocess.run(
                ["git", "-C", str(proof_workspace), "rev-parse", "HEAD"],
                check=True,
                stdout=subprocess.PIPE,
                text=True,
            ).stdout.strip() == service.config.proof_base_sha
            assert stat.S_IMODE(receipt_path.stat().st_mode) == 0o600
            receipt_bytes = receipt_path.read_bytes()
            assert hashlib.sha256(receipt_bytes).hexdigest() == rotation["receipt_sha256"]
            receipt = json.loads(receipt_bytes)
            assert receipt["old_workspace"]["inode"] == interrupted_inode
            assert receipt["old_workspace"]["status_dirty"] is True
            assert receipt["new_workspace"]["head"] == service.config.proof_base_sha
            assert receipt["new_workspace"]["status_dirty"] is False
            assert receipt["new_workspace"]["all_untracked_dirty"] is False
            assert receipt["new_workspace"]["launch_clean"] is True
            assert receipt["new_workspace"]["remote_count"] == 0
            assert receipt["new_workspace"]["branch"] == proof["result"]["branch"]
            events = runtime.events.list_events(job_id=proof_id)
            rotation_event = next(
                item for item in events if item.event_type == "PROOF_WORKSPACE_ROTATED"
            )
            assert rotation_event.attempt_id == lease.attempt.attempt_id
            assert rotation_event.payload["receipt_sha256"] == rotation["receipt_sha256"]
            assert events[-1].event_type == "JOB_REQUEUED"

            denied_requeue = await _request(service, "requeue", {"job_id": foreign.job_id})
            assert denied_requeue["ok"] is False
        finally:
            await service.close()

    asyncio.run(exercise())


def test_workspace_error_reason_reaches_client_as_request_failed(
    tmp_path: Path, short_socket_root: Path, monkeypatch: pytest.MonkeyPatch
):
    """Real-host repro: ``create-proof-job`` fails inside
    ``prepare_credentialless_clone`` with a ``WorkspaceError``.  That error is
    a bare ``RuntimeError`` (see control_plane/executive_workspace.py), so
    before this fix it fell through to the generic ``internal_error`` handler
    and the operator got only ``WorkspaceError: Executive request failed`` --
    the real reason existed in no channel.  It must now reach the client
    under the EXISTING ``request_failed`` code, carrying the actual reason.
    """

    async def exercise():
        service, _holder = _service(tmp_path, socket_root=short_socket_root)
        await service.start()
        try:
            await _request(service, "register-worker")

            reason = (
                "source repository is not a directory: "
                "/var/db/nonexistent-mastermind-source"
            )

            def fail_workspace(*args, **kwargs):
                raise WorkspaceError(reason)

            monkeypatch.setattr(
                "control_plane.executive_service.prepare_credentialless_clone",
                fail_workspace,
            )

            failed = await _request(service, "create-proof-job")
            assert failed["ok"] is False
            assert failed["error"]["code"] == "request_failed"
            assert failed["error"]["message"] == reason
        finally:
            await service.close()

    asyncio.run(exercise())


def test_workspace_error_redacts_secret_shaped_material(
    tmp_path: Path, short_socket_root: Path, monkeypatch: pytest.MonkeyPatch
):
    """Secret-shaped text embedded in a WorkspaceError is redacted before it
    crosses the socket.  common/redaction.py has NO git-object-id exemption
    -- unlike ops/executive_os/acceptance.py's refusal sanitizer, which
    exempts exactly-40 lowercase hex to keep release SHAs comparable/readable
    on that proof path.  This service is not that path, so a 40-hex git
    object id is expected to redact here too; this test pins that divergence
    rather than fighting it.
    """

    async def exercise():
        service, _holder = _service(tmp_path, socket_root=short_socket_root)
        await service.start()
        try:
            await _request(service, "register-worker")

            token_64_hex = "a" * 64
            git_object_id_40_hex = "b" * 40
            raw = (
                f"workspace clone failed: token={token_64_hex} "
                f"object={git_object_id_40_hex} done"
            )

            def fail_workspace(*args, **kwargs):
                raise WorkspaceError(raw)

            monkeypatch.setattr(
                "control_plane.executive_service.prepare_credentialless_clone",
                fail_workspace,
            )

            failed = await _request(service, "create-proof-job")
            assert failed["ok"] is False
            assert failed["error"]["code"] == "request_failed"
            message = failed["error"]["message"]
            assert token_64_hex not in message
            assert git_object_id_40_hex not in message
            assert message == (
                "workspace clone failed: token=<redacted> object=<redacted> done"
            )
        finally:
            await service.close()

    asyncio.run(exercise())


def test_workspace_error_text_is_bounded_at_service_boundary(
    tmp_path: Path, short_socket_root: Path, monkeypatch: pytest.MonkeyPatch
):
    """An oversized WorkspaceError message is bounded at the service
    boundary rather than forwarded verbatim.  The explicit ceiling is the
    sanitizer's ``limit=1000`` plus the length of its truncation marker.
    """

    async def exercise():
        service, _holder = _service(tmp_path, socket_root=short_socket_root)
        await service.start()
        try:
            await _request(service, "register-worker")

            oversized = "workspace clone failed while copying repository object " * 40
            assert len(oversized) > 1000

            def fail_workspace(*args, **kwargs):
                raise WorkspaceError(oversized)

            monkeypatch.setattr(
                "control_plane.executive_service.prepare_credentialless_clone",
                fail_workspace,
            )

            failed = await _request(service, "create-proof-job")
            assert failed["ok"] is False
            assert failed["error"]["code"] == "request_failed"
            message = failed["error"]["message"]
            ceiling = 1000 + len(TRUNCATION_MARKER)
            assert len(message) == ceiling
            assert len(message) <= ceiling
            assert message.endswith(TRUNCATION_MARKER)
        finally:
            await service.close()

    asyncio.run(exercise())


def test_workspace_error_empty_after_sanitization_falls_back_to_fixed_message(
    tmp_path: Path, short_socket_root: Path, monkeypatch: pytest.MonkeyPatch
):
    """A WorkspaceError whose text sanitizes to nothing (an empty message)
    falls back to the fixed string -- the client must never see an empty
    ``request_failed`` reason.
    """

    async def exercise():
        service, _holder = _service(tmp_path, socket_root=short_socket_root)
        await service.start()
        try:
            await _request(service, "register-worker")

            def fail_workspace(*args, **kwargs):
                raise WorkspaceError("")

            monkeypatch.setattr(
                "control_plane.executive_service.prepare_credentialless_clone",
                fail_workspace,
            )

            failed = await _request(service, "create-proof-job")
            assert failed["ok"] is False
            assert failed["error"]["code"] == "request_failed"
            assert failed["error"]["message"] == "workspace preparation failed"
        finally:
            await service.close()

    asyncio.run(exercise())


def test_generic_runtime_error_still_opaque_and_unwidened(
    tmp_path: Path, short_socket_root: Path, monkeypatch: pytest.MonkeyPatch
):
    """A plain RuntimeError -- NOT a WorkspaceError, RuntimeProofError, or
    ValueError -- must still land on the generic ``internal_error`` handler
    with its reason withheld, exactly as before this change.  Pins that the
    new WorkspaceError branch did not widen generic exception disclosure.
    """

    async def exercise():
        service, _holder = _service(tmp_path, socket_root=short_socket_root)
        await service.start()
        try:
            await _request(service, "register-worker")

            def fail_generic(*args, **kwargs):
                raise RuntimeError("sensitive internal reason")

            monkeypatch.setattr(
                "control_plane.executive_service.prepare_credentialless_clone",
                fail_generic,
            )

            failed = await _request(service, "create-proof-job")
            assert failed["ok"] is False
            assert failed["error"]["code"] == "internal_error"
            assert failed["error"]["message"] == "RuntimeError: Executive request failed"
            assert "sensitive internal reason" not in failed["error"]["message"]
        finally:
            await service.close()

    asyncio.run(exercise())


def test_cancel_clean_shutdown_and_manual_reconcile_never_auto_requeue(
    tmp_path: Path, short_socket_root: Path
):
    async def exercise():
        gate = asyncio.Event()
        service, holder = _service(
            tmp_path, socket_root=short_socket_root, finish_gate=gate
        )
        await service.start()
        await _request(service, "register-worker")
        created = await _request(service, "create-proof-job")
        job_id = created["result"]["job_id"]
        dispatched = await _request(service, "dispatch", {"job_id": job_id})
        assert dispatched["ok"] is True

        sibling = await _request(service, "create-proof-job")
        assert sibling["ok"] is False
        assert "sibling proof workspace" in sibling["error"]["message"]

        reconcile_while_live = await _request(service, "reconcile")
        assert reconcile_while_live["ok"] is False
        assert "active dispatch" in reconcile_while_live["error"]["message"]

        cancelled = await _request(service, "cancel", {"job_id": job_id})
        assert cancelled["result"]["status"] == "CANCEL_REQUESTED"
        gate.set()
        for _ in range(100):
            job = service.runtime.jobs.get_job(job_id)  # type: ignore[union-attr]
            if job is not None and job.status is JobStatus.CANCELLED:
                break
            await asyncio.sleep(0.01)
        assert job is not None and job.status is JobStatus.CANCELLED

        reconciled = await _request(service, "reconcile")
        assert reconciled["ok"] is True
        assert holder["supervisor"].requeue_values == [False, False]
        await service.close()
        assert not service.socket_path.exists()

    asyncio.run(exercise())


def test_backup_commands_are_confined_to_configured_root(
    tmp_path: Path, short_socket_root: Path
):
    async def exercise():
        backend = _FakeBackup()
        service, _holder = _service(
            tmp_path, socket_root=short_socket_root, backup=backend
        )
        await service.start()
        try:
            created = await _request(service, "backup")
            assert created["ok"] is True
            assert Path(created["result"]["database_path"]).parent == service.config.backup_root
            assert stat.S_IMODE(backend.created[0].stat().st_mode) == 0o600

            verified = await _request(service, "verify-backup", {"name": "fixture.sqlite3"})
            assert verified["result"]["ok"] is True
            assert backend.verified[0][0] == service.config.backup_root / "fixture.sqlite3"
            assert backend.verified[0][1] == service.config.backup_root / "fixture.manifest.json"

            (service.config.backup_root / "fixture.manifest.json").unlink()
            unrestorable = await _request(
                service, "verify-backup", {"name": "fixture.sqlite3"}
            )
            assert unrestorable["ok"] is False
            assert "no canonical manifest" in unrestorable["error"]["message"]

            escaped = await _request(
                service, "verify-backup", {"name": "../executive.sqlite3"}
            )
            assert escaped["ok"] is False
            assert "simple .sqlite3 file name" in escaped["error"]["message"]
        finally:
            await service.close()

    asyncio.run(exercise())


def test_peer_uid_is_checked_when_kernel_credentials_are_available(
    tmp_path: Path, short_socket_root: Path, monkeypatch: pytest.MonkeyPatch
):
    async def exercise():
        service, _holder = _service(tmp_path, socket_root=short_socket_root)
        await service.start()
        try:
            monkeypatch.setattr(
                "control_plane.executive_service._peer_uid",
                lambda _connection: os.geteuid() + 1,
            )
            denied = await _request(service, "status")
            assert denied["ok"] is False
            assert denied["error"]["code"] == "peer_denied"
        finally:
            await service.close()

    asyncio.run(exercise())


def test_missing_kernel_peer_credentials_fail_closed(
    tmp_path: Path, short_socket_root: Path, monkeypatch: pytest.MonkeyPatch
):
    async def exercise():
        service, _holder = _service(tmp_path, socket_root=short_socket_root)
        await service.start()
        try:
            monkeypatch.setattr(
                "control_plane.executive_service._peer_uid", lambda _connection: None
            )
            denied = await _request(service, "status")
            assert denied["ok"] is False
            assert denied["error"]["code"] == "peer_credentials_unavailable"
        finally:
            await service.close()

    asyncio.run(exercise())


def test_launchd_activated_unix_socket_is_reused_and_not_unlinked(
    tmp_path: Path, short_socket_root: Path
):
    async def exercise():
        socket_path = short_socket_root / "activated.sock"
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        listener.bind(str(socket_path))
        listener.listen(16)
        socket_path.chmod(0o660)
        config = _config(tmp_path, socket_root=short_socket_root)
        config = ServiceConfig(
            **{
                **config.__dict__,
                "socket_path": socket_path,
            }
        )
        holder = {}

        def factory(runtime):
            holder["supervisor"] = _FakeSupervisor(runtime)
            return holder["supervisor"]

        wrong_path = short_socket_root / "wrong-activated.sock"
        wrong_listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        wrong_listener.bind(str(wrong_path))
        wrong_listener.listen(1)
        with pytest.raises(ValueError, match="does not match"):
            ExecutiveControlService(
                config,
                supervisor_factory=factory,
                activated_socket=wrong_listener,
            )
        wrong_listener.close()

        service = ExecutiveControlService(
            config,
            supervisor_factory=factory,
            activated_socket=listener,
        )
        await service.start()
        assert (await _request(service, "status"))["ok"] is True
        await service.close()
        # launchd, not the daemon, owns removal of an activated socket node.
        assert socket_path.exists() and stat.S_ISSOCK(socket_path.stat().st_mode)

    asyncio.run(exercise())


def test_production_config_composes_remote_broker_and_launchd_socket(
    tmp_path: Path, short_socket_root: Path, monkeypatch: pytest.MonkeyPatch
):
    async def exercise():
        socket_path = short_socket_root / "production.sock"
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        listener.bind(str(socket_path))
        listener.listen(16)
        socket_path.chmod(0o660)
        canary = tmp_path / "canary.json"
        canary.write_text(
            json.dumps(
                {
                    "schema_version": "mastermind.executive_secret_canary/v1",
                    "passed": True,
                    "checks": {
                        "control_service_environment": "DENIED",
                        "administrative_checkout": "DENIED",
                        "executive_database": "DENIED",
                        "other_worker_home": "DENIED",
                        "forbidden_production_path": "DENIED",
                    },
                    "receipt_sha256": "a" * 64,
                    "control_environment_probe_sha256": "c" * 64,
                    "observed_at": "2026-08-11T00:00:00+00:00",
                    "worker_auth_exception": "DEDICATED_CODEX_HOME_ONLY",
                }
            ),
            encoding="utf-8",
        )
        canary.chmod(0o400)
        proof_source, proof_base_sha = _source_repository(tmp_path)
        raw = {
            "schema_version": service_cli.CONTROL_CONFIG_SCHEMA_VERSION,
            "runtime_root": str(tmp_path / "runtime"),
            "control_socket_path": str(socket_path),
            "launchd_socket_name": "Operator",
            "worker_broker_socket_path": str(short_socket_root / "worker.sock"),
            "worker_provider_home": str(tmp_path / "provider-home"),
            "worker_runs_root": str(tmp_path / "runs"),
            "receipts_root": str(tmp_path / "receipts"),
            "proof_source_repository": str(proof_source),
            "proof_workspace_root": str(tmp_path / "workspaces"),
            "proof_base_sha": proof_base_sha,
            "backup_root": str(tmp_path / "backups"),
            "control_uid": os.geteuid(),
            "worker_uid": os.geteuid() + 1,
            "worker_gid": os.getegid() + 1,
            "worker_user": "_mastermind_worker",
            "shared_run_gid": os.getegid() + 1,
            "allowed_peer_uids": [os.geteuid()],
            "secret_canary_receipt_path": str(canary),
            "control_environment_attestation_path": str(
                tmp_path / "control-environment-attestation.json"
            ),
        }
        config_path = tmp_path / "control.json"
        config_path.write_text(json.dumps(raw), encoding="utf-8")
        config_path.chmod(0o400)
        loaded = service_cli.load_control_config(config_path)
        monkeypatch.setattr(service_cli, "activate_launchd_socket", lambda _name: listener)
        service = service_cli._service_from_config(loaded)
        await service.start()
        try:
            from control_plane.executive_worker_broker import (
                RemoteCodexWorkerAdapter,
                RemoteWorkerProcessController,
            )

            assert isinstance(service.supervisor.adapter, RemoteCodexWorkerAdapter)
            assert isinstance(
                service.supervisor.process_controller, RemoteWorkerProcessController
            )
            assert service.supervisor.require_complete_launch_attestation is False
            assert service.supervisor.isolation_roots == (
                Path(raw["proof_workspace_root"]).resolve(),
                Path(raw["worker_runs_root"]).resolve(),
            )
            status = await _request(service, "status")
            assert status["ok"] is True
            assert status["result"]["service_state"] == "AWAITING_CANARY"
        finally:
            await service.close()

    asyncio.run(exercise())


def test_canary_envelope_binds_live_control_probe_and_inner_receipt(tmp_path: Path):
    host_root = tmp_path / "host"
    runtime_root = host_root / "control" / "db"
    proof_source = host_root / "control" / "admin-checkout" / ("a" * 40)
    codex_home = host_root / "workers" / "codex-01" / "provider-home"
    raw = {
        "runtime_root": runtime_root,
        "proof_source_repository": proof_source,
        "worker_provider_home": codex_home,
        "control_uid": os.geteuid(),
        "worker_uid": os.geteuid() + 1000,
        "worker_gid": os.getegid() + 1000,
    }
    control_identity = {
        "pid": 4242,
        "pgid": 4242,
        "session_id": 4242,
        "start_identity": "fixture-start",
        "boot_id": "fixture-boot",
        "effective_uid": os.geteuid(),
        "effective_gid": os.getegid(),
        "real_uid": os.getuid(),
        "real_gid": os.getgid(),
    }
    control_attestation = {
        "process_identity": control_identity,
        "config_sha256": "1" * 64,
        "release_manifest_sha256": "2" * 64,
        "sentinel_value_sha256": "3" * 64,
    }
    worker_principal = {
        "real_uid": raw["worker_uid"],
        "effective_uid": raw["worker_uid"],
        "real_gid": raw["worker_gid"],
        "effective_gid": raw["worker_gid"],
    }
    probe = {
        "schema_version": service_cli.CONTROL_ENVIRONMENT_PROBE_SCHEMA_VERSION,
        "passed": True,
        "control_process_identity": control_identity,
        "worker_principal": worker_principal,
        "config_sha256": control_attestation["config_sha256"],
        "release_manifest_sha256": control_attestation[
            "release_manifest_sha256"
        ],
        "sentinel_value_sha256": control_attestation["sentinel_value_sha256"],
        "process_identity_sha256": service_cli._canonical_sha256(control_identity),
        "checks": {
            "launchctl": "ABSENT",
            "ps": "DENIED",
            "kern_procargs2": "DENIED",
        },
    }
    probe_sha256 = service_cli._canonical_sha256(probe)
    canary_config = SecretCanaryConfig(
        expected_worker_uid=raw["worker_uid"],
        expected_worker_gid=raw["worker_gid"],
        control_uid=raw["control_uid"],
        control_gid=os.getegid(),
        control_environment_sentinel="EXECUTIVE_CONTROL_CANARY_VALUE",
        control_environment_probe_sha256=probe_sha256,
        administrative_checkout_sentinel=(
            proof_source / ".git" / "executive-secret-canary"
        ),
        executive_database=(
            runtime_root / "data" / "control_plane" / "executive.sqlite3"
        ),
        other_worker_home_sentinel=(
            host_root / "canary-fixtures" / "other-worker-home" / "sentinel"
        ),
        forbidden_production_sentinel=(
            host_root / "canary-fixtures" / "production-like" / "sentinel"
        ),
        codex_home=codex_home,
    )

    def opener(path: Path, _flags: int) -> int:
        if path == codex_home / "auth.json":
            return 19
        raise PermissionError(errno.EACCES, "denied")

    inner = run_secret_canary(
        canary_config,
        opener=opener,
        closer=lambda _descriptor: None,
        environment={},
        principal=PrincipalIdentity(**worker_principal),
    )
    envelope = {
        "schema_version": service_cli.SECRET_CANARY_ENVELOPE_SCHEMA_VERSION,
        "secret_canary": inner,
        "control_environment_probe": probe,
        "control_environment_probe_sha256": probe_sha256,
    }
    path = tmp_path / "secret-canary.json"
    path.write_text(json.dumps(envelope), encoding="utf-8")
    path.chmod(0o400)

    assert service_cli._load_canary_envelope(
        path,
        raw=raw,
        control_attestation=control_attestation,
    ) == inner

    stale = dict(control_attestation)
    stale["process_identity"] = {**control_identity, "pid": 9999}
    with pytest.raises(service_cli.ServiceError, match="identity is stale"):
        service_cli._load_canary_envelope(
            path,
            raw=raw,
            control_attestation=stale,
        )


def test_awaiting_canary_quarantine_allows_only_readiness_and_activation(
    tmp_path: Path, short_socket_root: Path
):
    async def exercise():
        config = _config(tmp_path, socket_root=short_socket_root)
        holder = {}
        verdict = {
            "schema_version": "mastermind.executive_secret_canary/v1",
            "passed": True,
            "checks": {
                "control_service_environment": "DENIED",
                "administrative_checkout": "DENIED",
                "executive_database": "DENIED",
                "other_worker_home": "DENIED",
                "forbidden_production_path": "DENIED",
            },
            "receipt_sha256": "b" * 64,
            "control_environment_probe_sha256": "c" * 64,
            "observed_at": "2026-08-11T00:00:00Z",
            "worker_auth_exception": "DEDICATED_CODEX_HOME_ONLY",
        }
        loader_calls = []

        def load_canary():
            loader_calls.append(True)
            return verdict

        def factory(runtime):
            holder["supervisor"] = _FakeSupervisor(runtime)
            holder["supervisor"].secret_canary_verdict = {}
            holder["supervisor"].require_complete_launch_attestation = False
            return holder["supervisor"]

        service = ExecutiveControlService(
            config,
            supervisor_factory=factory,
            service_state="AWAITING_CANARY",
            canary_loader=load_canary,
        )
        await service.start()
        try:
            status = await _request(service, "status")
            assert status["result"]["service_state"] == "AWAITING_CANARY"
            assert (await _request(service, "health"))["result"]["ok"] is True
            denied = await _request(service, "register-worker")
            assert denied["ok"] is False
            assert "AWAITING_CANARY" in denied["error"]["message"]
            assert holder["supervisor"].requeue_values == []
            rejected = await _request(
                service, "activate-canary", {"receipt_path": "/unreviewed"}
            )
            assert rejected["ok"] is False
            assert loader_calls == []
            activated = await _request(service, "activate-canary")
            assert activated["result"] == {"service_state": "READY"}
            ready = await _request(service, "status")
            assert ready["result"]["service_state"] == "READY"
            assert loader_calls == [True]
            assert holder["supervisor"].secret_canary_verdict == verdict
            assert holder["supervisor"].require_complete_launch_attestation is True
            assert holder["supervisor"].requeue_values == [False]
            repeated = await _request(service, "activate-canary")
            assert repeated["ok"] is False
            assert loader_calls == [True]
        finally:
            await service.close()

    asyncio.run(exercise())


def test_canary_activation_fails_closed_without_loader(
    tmp_path: Path, short_socket_root: Path
):
    async def exercise():
        service, _holder = _service(
            tmp_path,
            socket_root=short_socket_root,
        )
        service._service_state = "AWAITING_CANARY"
        await service.start()
        try:
            response = await _request(service, "activate-canary")
            assert response["ok"] is False
            assert "no canary loader" in response["error"]["message"]
            status = await _request(service, "status")
            assert status["result"]["service_state"] == "AWAITING_CANARY"
        finally:
            await service.close()

    asyncio.run(exercise())


def test_service_config_rejects_relative_paths_and_unbounded_inputs(tmp_path: Path):
    absolute = _config(tmp_path)
    assert absolute.socket_path.is_absolute()
    with pytest.raises(ValueError, match="socket_path must be absolute"):
        ServiceConfig(
            runtime_root=tmp_path,
            socket_path=Path("relative.sock"),
            proof_source_repository=absolute.proof_source_repository,
            proof_workspace_root=tmp_path / "workspaces",
            proof_base_sha=absolute.proof_base_sha,
        )
    with pytest.raises(ValueError, match="proof_base_sha"):
        _config(tmp_path / "bad-sha", proof_base_sha="main")
    with pytest.raises(ValueError, match="codex/"):
        _config(tmp_path / "bad-branch", proof_branch="main")


def test_cli_exposes_configured_serve_and_offline_restore_only():
    serve = service_cli._parser().parse_args(
        ["serve", "--config", "/etc/mastermind-executive/control.json"]
    )
    assert serve.command == "serve" and serve.config.is_absolute()
    restore = service_cli._parser().parse_args(
        [
            "restore-backup",
            "--config",
            "/etc/mastermind-executive/control.json",
            "executive-proof.sqlite3",
        ]
    )
    assert restore.command == "restore-backup"
    # The live JSON protocol deliberately has no restore verb.
    assert "restore" not in {
        "status",
        "health",
        "workers",
        "jobs",
        "job",
        "attempt",
        "register-worker",
        "create-proof-job",
        "dispatch",
        "cancel",
        "reconcile",
        "requeue",
        "backup",
        "verify-backup",
    }


def test_service_surface_has_no_financial_app_or_scheduler_integration():
    root = Path(__file__).resolve().parents[1]
    executive_sources = [
        root / "control_plane" / "executive_service.py",
        root / "control_plane" / "executive_worker_broker.py",
        root / "scripts" / "executive_os_phase1c.py",
        root / "scripts" / "executive_os_phase1c_worker.py",
    ]
    forbidden_roots = {
        "app",
        "apscheduler",
        "bot",
        "brain",
        "bridge",
        "loop",
        "portfolio",
    }
    for source in executive_sources:
        tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".", 1)[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".", 1)[0])
        assert imported.isdisjoint(forbidden_roots), (source, imported & forbidden_roots)

    service_names = {
        path.relative_to(root).as_posix()
        for path in executive_sources
    }
    for package in ("app", "bot", "brain", "bridge", "loop", "portfolio"):
        package_root = root / package
        for source in package_root.rglob("*.py"):
            content = source.read_text(encoding="utf-8", errors="replace")
            assert "control_plane.executive_service" not in content, (
                source.relative_to(root).as_posix(),
                service_names,
            )


def _mark_proof_lost(runtime: Runtime, proof_id: str, proof_workspace: Path):
    lease = runtime.broker.claim(proof_id, lease_owner="lost-fixture")
    assert lease is not None
    runtime.attempts.record_process(
        lease.attempt.attempt_id,
        fence_generation=lease.attempt.fence_generation,
        lease_token=lease.lease_token,
        provider_session_id="missing-provider-session",
    )
    runtime.attempts.mark_running(
        lease.attempt.attempt_id,
        fence_generation=lease.attempt.fence_generation,
        lease_token=lease.lease_token,
    )
    runtime.attempts.mark_lost(
        lease.attempt.attempt_id,
        fence_generation=lease.attempt.fence_generation,
        lease_token=lease.lease_token,
        reason="verified fixture absence",
        verified_process_absent=True,
    )
    proof_workspace.chmod(0o700)
    return lease


def test_service_git_observer_uses_optional_locks_and_refuses_mutation(
    tmp_path: Path, short_socket_root: Path, monkeypatch: pytest.MonkeyPatch
):
    async def exercise():
        service, _holder = _service(tmp_path, socket_root=short_socket_root)
        await service.start()
        try:
            await _request(service, "register-worker")
            created = await _request(service, "create-proof-job")
            workspace = Path(created["result"]["worktree"])
            recorded_env: list[dict[str, str]] = []
            recorded_argv: list[tuple[str, ...]] = []
            real_run = es_mod.subprocess.run

            def observed_run(*args, **kwargs):
                argv = args[0] if args else kwargs.get("args")
                env = kwargs.get("env") or {}
                recorded_argv.append(tuple(argv))
                recorded_env.append(dict(env))
                return real_run(*args, **kwargs)

            monkeypatch.setattr(es_mod.subprocess, "run", observed_run)
            service._observe_git(workspace, ["rev-parse", "--verify", "HEAD^{commit}"])
            service._observe_git(workspace, list(LAUNCH_CLEAN_STATUS_ARGS))
            service._observe_git(workspace, list(LAUNCH_CLEAN_UNTRACKED_ARGS))
            assert recorded_argv == [
                ("git", "-C", str(workspace), "rev-parse", "--verify", "HEAD^{commit}"),
                ("git", "-C", str(workspace), *LAUNCH_CLEAN_STATUS_ARGS),
                ("git", "-C", str(workspace), *LAUNCH_CLEAN_UNTRACKED_ARGS),
            ]
            assert recorded_env
            assert all(item.get("GIT_OPTIONAL_LOCKS") == "0" for item in recorded_env)

            spawned: list[object] = []

            def refuse_spawn(*args, **kwargs):
                spawned.append(args[0] if args else kwargs.get("args"))
                raise AssertionError("mutating Git must not spawn")

            monkeypatch.setattr(es_mod.subprocess, "run", refuse_spawn)
            for forbidden in (
                ["checkout", "HEAD"],
                ["switch", "main"],
                ["update-index", "--refresh"],
                ["add", "."],
                ["config", "safe.directory", "*"],
                ["remote", "add", "origin", "https://example.invalid/repo.git"],
                ["reset", "--hard"],
            ):
                with pytest.raises(ServiceError, match="refuses mutating"):
                    service._observe_git(workspace, forbidden)
            assert spawned == []
        finally:
            await service.close()

    asyncio.run(exercise())


def test_requeue_refuses_simulated_0600_index_after_service_observation(
    tmp_path: Path, short_socket_root: Path, monkeypatch: pytest.MonkeyPatch
):
    async def exercise():
        service, holder = _service(tmp_path, socket_root=short_socket_root)
        await service.start()
        try:
            runtime = service.runtime
            assert runtime is not None
            await _request(service, "register-worker")
            proof = await _request(service, "create-proof-job")
            proof_id = proof["result"]["job_id"]
            proof_workspace = Path(proof["result"]["worktree"])
            _mark_proof_lost(runtime, proof_id, proof_workspace)
            real_observe = service._observe_git

            def corrupt_after_status(workspace: Path, arguments: list[str]) -> bytes:
                result = real_observe(workspace, arguments)
                if tuple(arguments) == LAUNCH_CLEAN_STATUS_ARGS:
                    (workspace / ".git" / "index").chmod(0o600)
                return result

            monkeypatch.setattr(service, "_observe_git", corrupt_after_status)
            failed = await _request(service, "requeue", {"job_id": proof_id})
            assert failed["ok"] is False
            assert failed["error"]["code"] == "request_failed"
            assert ".git/index" in failed["error"]["message"]
            job = runtime.jobs.get_job(proof_id)
            assert job is not None
            assert job.status is JobStatus.LOST
            assert holder["supervisor"].started_jobs == []
            rotation_root = service.config.proof_workspace_root / ".lost-attempts" / proof_id
            assert not any(rotation_root.glob("*.rotation.json"))
            assert runtime.attempts.list_attempts(job_id=proof_id)
            current = runtime.jobs.get_job(proof_id)
            assert current is not None and current.current_attempt_id is not None
        finally:
            await service.close()

    asyncio.run(exercise())


def test_dispatch_refuses_queued_workspace_with_0600_index(
    tmp_path: Path, short_socket_root: Path
):
    async def exercise():
        service, holder = _service(tmp_path, socket_root=short_socket_root)
        await service.start()
        try:
            runtime = service.runtime
            assert runtime is not None
            await _request(service, "register-worker")
            proof = await _request(service, "create-proof-job")
            proof_id = proof["result"]["job_id"]
            workspace = Path(proof["result"]["worktree"])
            (workspace / ".git" / "index").chmod(0o600)
            denied = await _request(service, "dispatch", {"job_id": proof_id})
            assert denied["ok"] is False
            assert denied["error"]["code"] == "request_failed"
            assert ".git/index" in denied["error"]["message"]
            job = runtime.jobs.get_job(proof_id)
            assert job is not None
            assert job.status is JobStatus.QUEUED
            assert job.current_attempt_id is None
            assert holder["supervisor"].started_jobs == []
            assert stat.S_IMODE((workspace / ".git" / "index").stat().st_mode) == 0o600
        finally:
            await service.close()

    asyncio.run(exercise())
