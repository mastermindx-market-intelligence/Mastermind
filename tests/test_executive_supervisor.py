"""Model-free integration tests for the durable Executive supervisor seam."""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import signal
import stat
from pathlib import Path

import pytest

from control_plane.codex_worker import (
    BinaryAttestation,
    CollectionReceipt,
    ProcessIdentityError,
    ProcessRef,
    ValidationReceipt,
    WorkerResult,
    WorkerRunStatus,
)
from control_plane.executive_runtime import (
    AttemptStatus,
    JobPayload,
    JobStatus,
    Runtime,
    StateConflict,
    WorkerStatus,
)
from control_plane.executive_supervisor import (
    ExecutiveSupervisor,
    IdentitySafeProcessController,
    ProcessPresence,
    ReconcileStatus,
    RESULT_SCHEMA_VERSION,
    worker_result_schema,
)


class FakeInspector:
    def __init__(self) -> None:
        self.live = True
        self.boot_id = "boot-fixture"
        self.start_identity = "start-fixture"
        self.pid = 42420

    def boot_session_id(self) -> str:
        return self.boot_id

    def identity(self, pid: int) -> tuple[str, int]:
        if not self.live or pid != self.pid:
            raise ProcessIdentityError("fixture process is absent")
        return self.start_identity, self.pid


class FakeProcessController:
    def __init__(self, inspector: FakeInspector) -> None:
        self.inspector = inspector
        self.terminated_attempt_ids: list[str] = []

    def presence(self, attempt) -> ProcessPresence:
        if attempt.pid is None or not attempt.process_start_identity or not attempt.boot_id:
            return ProcessPresence.UNKNOWN
        return ProcessPresence.LIVE if self.inspector.live else ProcessPresence.ABSENT

    def absence_verified(self, attempt) -> bool:
        return self.presence(attempt) is ProcessPresence.ABSENT

    def terminate(self, attempt) -> None:
        assert self.presence(attempt) is ProcessPresence.LIVE
        self.terminated_attempt_ids.append(attempt.attempt_id)
        self.inspector.live = False


class UnknownProcessController:
    def presence(self, attempt) -> ProcessPresence:
        return ProcessPresence.UNKNOWN

    def absence_verified(self, attempt) -> bool:
        return False

    def terminate(self, attempt) -> None:  # pragma: no cover - must never be called
        raise AssertionError("ambiguous process must not be signalled")


class FakeAdapter:
    def __init__(
        self,
        inspector: FakeInspector,
        *,
        output_status: str = "COMPLETED",
        validation_argv: list[str] | None = None,
        direct_validation_exit_code: int = 0,
        direct_validation_delay: float = 0.0,
        reported_validations: bool = False,
    ) -> None:
        self.inspector = inspector
        self.output_status = output_status
        self.validation_argv = validation_argv or ["/usr/bin/true"]
        self.direct_validation_exit_code = direct_validation_exit_code
        self.direct_validation_delay = direct_validation_delay
        self.reported_validations = reported_validations
        self.direct_validation_calls: list[tuple[str, ...]] = []
        self.spec = None
        self.ref = None

    async def start(self, spec):
        self.spec = spec
        logs = spec.run_dir / "logs"
        output = spec.run_dir / "output"
        logs.mkdir(mode=0o700)
        output.mkdir(mode=0o700)
        stdout = logs / "stdout.jsonl"
        stderr = logs / "stderr.log"
        result = output / "result.json"
        for path, payload in (
            (stdout, b'{"type":"turn.completed"}\n'),
            (stderr, b""),
            (result, b"{}\n"),
        ):
            path.write_bytes(payload)
            path.chmod(0o600)
        binary = BinaryAttestation(
            path="/fixture/codex",
            real_path="/fixture/codex",
            version="fixture-1",
            sha256="a" * 64,
            team_identifier="2DC432GLL2",
            size=1,
            device=1,
            inode=1,
            mode=0o755,
            uid=os.geteuid(),
            gid=os.getegid(),
            mtime_ns=1,
        )
        self.ref = ProcessRef(
            run_id=spec.run_id,
            pid=self.inspector.pid,
            pgid=self.inspector.pid,
            process_start_identity=self.inspector.start_identity,
            boot_session_id=self.inspector.boot_id,
            launch_nonce="nonce-fixture",
            provider_session_id=None,
            stdout_path=str(stdout),
            stderr_path=str(stderr),
            result_path=str(result),
            started_at="2026-08-11T00:00:00+00:00",
            binary=binary,
            base_sha="b" * 40,
        )
        return self.ref

    async def collect_result(self, ref):
        assert ref == self.ref and self.spec is not None
        artifact_path = self.spec.workspace_path / "research" / "proof.md"
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_text("durable proof\n", encoding="utf-8")
        structured = {
            "schema_version": RESULT_SCHEMA_VERSION,
            "job_id": self.spec.job_id,
            "run_id": self.spec.run_id,
            "worker_id": self.spec.worker_id,
            "status": self.output_status,
            "summary": "bounded proof complete",
            "completed_steps": ["wrote artifact", "left validation to supervisor"],
            "current_state": "done" if self.output_status == "COMPLETED" else "failed",
            "artifacts": [{"path": "research/proof.md"}],
            "next_actions": [],
            "errors": [] if self.output_status == "COMPLETED" else ["fixture failure"],
            "validations": (
                [{"argv": self.validation_argv, "exit_code": 0}]
                if self.reported_validations
                else []
            ),
        }
        result = WorkerResult(
            job_id=self.spec.job_id,
            run_id=self.spec.run_id,
            worker_id=self.spec.worker_id,
            status=WorkerRunStatus.SUCCEEDED,
            structured_output=structured,
            artifact_manifest=(),
            git_manifest={"base_sha": "b" * 40, "head_sha": "b" * 40},
            usage={"input_tokens": 10, "output_tokens": 5},
            provider_session_id="thread-fixture",
            exit_code=0,
            started_at=ref.started_at,
            finished_at="2026-08-11T00:00:01+00:00",
            error=None,
        )
        return CollectionReceipt(
            process_ref=ref,
            result=result,
            stdout_sha256=hashlib.sha256(Path(ref.stdout_path).read_bytes()).hexdigest(),
            stderr_sha256=hashlib.sha256(Path(ref.stderr_path).read_bytes()).hexdigest(),
            result_sha256=hashlib.sha256(Path(ref.result_path).read_bytes()).hexdigest(),
        )

    async def run_validation_argv(self, spec, argv, *, timeout_seconds=300.0):
        assert spec == self.spec
        exact = tuple(argv)
        self.direct_validation_calls.append(exact)
        if self.direct_validation_delay:
            await asyncio.sleep(self.direct_validation_delay)
        empty = hashlib.sha256(b"").hexdigest()
        return ValidationReceipt(
            argv=exact,
            exit_code=self.direct_validation_exit_code,
            stdout_sha256=empty,
            stdout_size=0,
            stderr_sha256=empty,
            stderr_size=0,
            timed_out=False,
            error=None,
        )

    async def cancel(self, ref, reason):  # pragma: no cover - exceptional cleanup seam
        self.inspector.live = False


def _runtime_and_job(
    tmp_path: Path,
    *,
    clock=None,
    lease_seconds: int = 30,
) -> tuple[Runtime, str, Path]:
    runtime = Runtime.at(tmp_path, clock=clock, lease_seconds=lease_seconds)
    runtime.workers.register_worker(
        "codex-01",
        provider="codex",
        account_label="manually-authenticated",
        worker_type="codex-cli",
        capabilities=["research", "code", "tests"],
        quota_classes={
            "codex-native": {
                "capabilities": ["research", "code", "tests"],
                "model": "gpt-5.6-sol",
                "effort": "xhigh",
                "cost_class": "standard",
            }
        },
    )
    workspace = tmp_path / "isolated-workspace"
    workspace.mkdir(mode=0o700)
    job = runtime.jobs.create_job(
        "Create the bounded proof artifact",
        worktree=str(workspace.resolve()),
        requested_authorities=["READ", "RESEARCH", "WRITE_BRANCH", "RUN_TESTS"],
        allowed_write_paths=["research/proof.md"],
        validation_commands=[["/usr/bin/true"]],
        constraints={
            "provider": "codex",
            "model": "gpt-5.6-sol",
            "effort": "xhigh",
            "cost_class": "standard",
            "base_sha": "b" * 40,
            "eligible_quota_classes": ["codex-native"],
            "required_capabilities": ["research", "code", "tests"],
        },
        attempt_limit=3,
    )
    return runtime, job.job_id, workspace


def _supervisor(runtime: Runtime, tmp_path: Path, adapter: FakeAdapter) -> ExecutiveSupervisor:
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir(mode=0o700, exist_ok=True)
    return ExecutiveSupervisor(
        runtime,
        adapter,  # type: ignore[arg-type]
        codex_home=codex_home,
        runs_root=tmp_path / "runs",
        heartbeat_interval_seconds=0.01,
        inspector=adapter.inspector,
        process_controller=FakeProcessController(adapter.inspector),
        instance_id="supervisor-fixture",
    )


def test_run_once_persists_process_checkpoint_result_receipt_and_reopens(tmp_path: Path):
    runtime, job_id, _workspace = _runtime_and_job(tmp_path)
    inspector = FakeInspector()
    adapter = FakeAdapter(inspector)

    receipt = asyncio.run(_supervisor(runtime, tmp_path, adapter).run_once(job_id))

    assert receipt.job.status is JobStatus.COMPLETED
    assert receipt.attempt.status is AttemptStatus.COMPLETED
    assert receipt.attempt.pid == inspector.pid
    assert receipt.attempt.process_start_identity == inspector.start_identity
    assert receipt.attempt.checkpoint_sequence == 1
    assert adapter.spec.expected_base_sha == "b" * 40
    assert f'"base_sha": "{"b" * 40}"' in adapter.spec.prompt
    assert "set validations=[] exactly" in adapter.spec.prompt
    assert receipt.job.checkpoint is not None
    assert receipt.job.result is not None
    quota = runtime.workers.get_quota_class("codex-01", "codex-native")
    assert quota is not None and quota.status is WorkerStatus.AVAILABLE
    assert quota.active_attempt_id is None
    evidence = Path(receipt.collection_receipt_path)
    assert evidence.exists()
    assert stat.S_IMODE(evidence.stat().st_mode) == 0o600
    persisted = json.loads(evidence.read_text(encoding="utf-8"))
    assert persisted["result"]["status"] == "SUCCEEDED"
    assert "lease_token" not in evidence.read_text(encoding="utf-8")
    assert adapter.direct_validation_calls == [("/usr/bin/true",)]
    validation_evidence = Path(receipt.validation_receipt_path or "")
    assert validation_evidence.is_file()
    assert stat.S_IMODE(validation_evidence.stat().st_mode) == 0o600
    validation_payload = json.loads(validation_evidence.read_text(encoding="utf-8"))
    assert validation_payload["commands"][0]["argv"] == ["/usr/bin/true"]
    assert validation_payload["commands"][0]["exit_code"] == 0

    reopened = Runtime.at(tmp_path)
    reopened_job = reopened.jobs.get_job(job_id)
    reopened_attempt = reopened.attempts.get_attempt(receipt.attempt.attempt_id)
    assert reopened_job is not None and reopened_job.status is JobStatus.COMPLETED
    assert reopened_attempt is not None and reopened_attempt.status is AttemptStatus.COMPLETED
    assert reopened_attempt.result == reopened_job.result


def test_restart_missing_process_rotates_fence_marks_lost_preserves_checkpoint_and_requeues(
    tmp_path: Path,
):
    runtime, job_id, _workspace = _runtime_and_job(tmp_path)
    inspector = FakeInspector()
    first_adapter = FakeAdapter(inspector)
    first = _supervisor(runtime, tmp_path, first_adapter)
    active = asyncio.run(first.start_job(job_id))
    runtime.attempts.checkpoint_attempt(
        active.lease.attempt.attempt_id,
        fence_generation=active.lease.attempt.fence_generation,
        lease_token=active.lease.lease_token,
        payload=JobPayload(summary="checkpoint before abrupt death", current_state="halfway"),
    )
    original_fence = active.lease.attempt.fence_generation
    inspector.live = False

    reopened = Runtime.at(tmp_path, lease_seconds=30)
    restarted = _supervisor(reopened, tmp_path, FakeAdapter(inspector))
    outcomes = restarted.reconcile_restart(requeue_lost=True)

    assert len(outcomes) == 1
    assert outcomes[0].status is ReconcileStatus.REQUEUED
    assert outcomes[0].requeued is True
    attempt = reopened.attempts.get_attempt(active.lease.attempt.attempt_id)
    job = reopened.jobs.get_job(job_id)
    assert attempt is not None and attempt.status is AttemptStatus.LOST
    assert attempt.fence_generation == original_fence + 1
    assert job is not None and job.status is JobStatus.QUEUED
    assert job.checkpoint is not None
    assert job.checkpoint["summary"] == "checkpoint before abrupt death"
    with pytest.raises(StateConflict):
        reopened.attempts.heartbeat_attempt(
            attempt.attempt_id,
            fence_generation=original_fence,
            lease_token=active.lease.lease_token,
        )


def test_restart_live_process_is_terminated_verified_absent_then_lost_and_requeued(
    tmp_path: Path,
):
    runtime, job_id, _workspace = _runtime_and_job(tmp_path)
    inspector = FakeInspector()
    active = asyncio.run(_supervisor(runtime, tmp_path, FakeAdapter(inspector)).start_job(job_id))

    reopened = Runtime.at(tmp_path, lease_seconds=30)
    restarted = _supervisor(reopened, tmp_path, FakeAdapter(inspector))
    outcomes = restarted.reconcile_restart()

    assert [item.status for item in outcomes] == [ReconcileStatus.REQUEUED]
    assert outcomes[0].process_was_live is True
    assert restarted.process_controller.terminated_attempt_ids == [
        active.lease.attempt.attempt_id
    ]
    attempt = reopened.attempts.get_attempt(active.lease.attempt.attempt_id)
    job = reopened.jobs.get_job(job_id)
    assert attempt is not None and attempt.status is AttemptStatus.LOST
    assert job is not None and job.status is JobStatus.QUEUED


def test_restart_cancel_requested_live_process_is_terminated_before_cancel_ack(
    tmp_path: Path,
):
    runtime, job_id, _workspace = _runtime_and_job(tmp_path)
    inspector = FakeInspector()
    active = asyncio.run(_supervisor(runtime, tmp_path, FakeAdapter(inspector)).start_job(job_id))
    runtime.jobs.cancel_job(job_id)

    reopened = Runtime.at(tmp_path, lease_seconds=30)
    restarted = _supervisor(reopened, tmp_path, FakeAdapter(inspector))
    outcomes = restarted.reconcile_restart()

    assert [item.status for item in outcomes] == [ReconcileStatus.MISSING_CANCELLED]
    assert outcomes[0].process_was_live is True
    assert restarted.process_controller.terminated_attempt_ids == [
        active.lease.attempt.attempt_id
    ]
    attempt = reopened.attempts.get_attempt(active.lease.attempt.attempt_id)
    job = reopened.jobs.get_job(job_id)
    assert attempt is not None and attempt.status is AttemptStatus.CANCELLED
    assert job is not None and job.status is JobStatus.CANCELLED


def test_restart_expired_live_process_is_terminated_before_expiry_requeue(tmp_path: Path):
    now = [1_800_000_000_000]
    clock = lambda: now[0]
    runtime, job_id, _workspace = _runtime_and_job(
        tmp_path,
        clock=clock,
        lease_seconds=1,
    )
    inspector = FakeInspector()
    active = asyncio.run(_supervisor(runtime, tmp_path, FakeAdapter(inspector)).start_job(job_id))
    now[0] += 2_000

    reopened = Runtime.at(tmp_path, clock=clock, lease_seconds=1)
    restarted = _supervisor(reopened, tmp_path, FakeAdapter(inspector))
    outcomes = restarted.reconcile_restart()

    assert [item.status for item in outcomes] == [ReconcileStatus.REQUEUED]
    assert outcomes[0].process_was_live is True
    assert restarted.process_controller.terminated_attempt_ids == [
        active.lease.attempt.attempt_id
    ]
    attempt = reopened.attempts.get_attempt(active.lease.attempt.attempt_id)
    assert attempt is not None and attempt.status is AttemptStatus.LOST


def test_restart_expired_ambiguous_process_remains_active_and_is_not_requeued(tmp_path: Path):
    now = [1_800_000_000_000]
    clock = lambda: now[0]
    runtime, job_id, _workspace = _runtime_and_job(
        tmp_path,
        clock=clock,
        lease_seconds=1,
    )
    inspector = FakeInspector()
    active = asyncio.run(_supervisor(runtime, tmp_path, FakeAdapter(inspector)).start_job(job_id))
    now[0] += 2_000

    reopened = Runtime.at(tmp_path, clock=clock, lease_seconds=1)
    restarted = _supervisor(reopened, tmp_path, FakeAdapter(inspector))
    restarted.process_controller = UnknownProcessController()
    outcomes = restarted.reconcile_restart()

    assert [item.status for item in outcomes] == [ReconcileStatus.IDENTITY_AMBIGUOUS]
    attempt = reopened.attempts.get_attempt(active.lease.attempt.attempt_id)
    job = reopened.jobs.get_job(job_id)
    assert attempt is not None and attempt.status is AttemptStatus.RUNNING
    assert job is not None and job.status is JobStatus.RUNNING


def test_identity_safe_termination_escalates_when_leader_exits_but_descendants_survive(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    runtime, job_id, _workspace = _runtime_and_job(tmp_path)
    inspector = FakeInspector()
    active = asyncio.run(_supervisor(runtime, tmp_path, FakeAdapter(inspector)).start_job(job_id))
    persisted = runtime.attempts.get_attempt(active.lease.attempt.attempt_id)
    assert persisted is not None
    group_live = [True]
    signals: list[signal.Signals] = []

    def fake_kill(pid: int, value: int) -> None:
        assert value == 0 and pid == inspector.pid
        if not inspector.live:
            raise ProcessLookupError(pid)

    def fake_killpg(pgid: int, value: int | signal.Signals) -> None:
        assert pgid == inspector.pid
        if value == 0:
            if not group_live[0]:
                raise ProcessLookupError(pgid)
            return
        signals.append(signal.Signals(value))
        if value == signal.SIGTERM:
            inspector.live = False
        elif value == signal.SIGKILL:
            group_live[0] = False

    monkeypatch.setattr("control_plane.executive_supervisor.os.kill", fake_kill)
    monkeypatch.setattr("control_plane.executive_supervisor.os.killpg", fake_killpg)
    controller = IdentitySafeProcessController(
        inspector, term_grace_seconds=0, kill_grace_seconds=0.1, poll_seconds=0.001
    )

    controller.terminate(persisted)

    assert signals == [signal.SIGTERM, signal.SIGKILL]
    assert group_live[0] is False


def test_result_schema_is_identity_bound_and_closed():
    schema = worker_result_schema(job_id="JOB-007", run_id="ATT-abc", worker_id="codex-01")
    assert schema["additionalProperties"] is False
    assert schema["properties"]["job_id"]["const"] == "JOB-007"
    assert schema["properties"]["run_id"]["const"] == "ATT-abc"
    assert schema["properties"]["worker_id"]["const"] == "codex-01"
    assert schema["properties"]["validations"]["maxItems"] == 0
    assert schema["properties"]["validations"]["items"]["type"] == "object"


def test_result_with_ungranted_validation_argv_is_failed_closed(tmp_path: Path):
    runtime, job_id, _workspace = _runtime_and_job(tmp_path)
    adapter = FakeAdapter(
        FakeInspector(),
        validation_argv=["/usr/bin/false"],
        reported_validations=True,
    )

    receipt = asyncio.run(_supervisor(runtime, tmp_path, adapter).run_once(job_id))

    assert receipt.job.status is JobStatus.FAILED
    assert receipt.attempt.status is AttemptStatus.FAILED
    assert "leave validations=[]" in receipt.job.result["errors"][0]


def test_completion_uses_supervisor_direct_argv_not_model_attested_exit_code(tmp_path: Path):
    runtime, job_id, _workspace = _runtime_and_job(tmp_path)
    adapter = FakeAdapter(FakeInspector(), direct_validation_exit_code=7)

    receipt = asyncio.run(_supervisor(runtime, tmp_path, adapter).run_once(job_id))

    assert adapter.direct_validation_calls == [("/usr/bin/true",)]
    assert receipt.job.status is JobStatus.FAILED
    assert receipt.attempt.status is AttemptStatus.FAILED
    assert "exit code 7" in receipt.job.result["errors"][0]
    validation_evidence = Path(receipt.validation_receipt_path or "")
    assert validation_evidence.is_file()
    assert json.loads(validation_evidence.read_text(encoding="utf-8"))["commands"][0][
        "exit_code"
    ] == 7


def test_empty_model_validation_telemetry_still_runs_exact_supervisor_argv(tmp_path: Path):
    runtime, job_id, _workspace = _runtime_and_job(tmp_path)
    adapter = FakeAdapter(FakeInspector(), reported_validations=False)

    receipt = asyncio.run(_supervisor(runtime, tmp_path, adapter).run_once(job_id))

    assert receipt.job.status is JobStatus.COMPLETED
    assert adapter.direct_validation_calls == [("/usr/bin/true",)]


def test_cancel_request_during_direct_validation_prevents_completion(tmp_path: Path):
    runtime, job_id, _workspace = _runtime_and_job(tmp_path)
    adapter = FakeAdapter(FakeInspector(), direct_validation_delay=30)
    supervisor = _supervisor(runtime, tmp_path, adapter)

    async def exercise():
        task = asyncio.create_task(supervisor.run_once(job_id))
        for _ in range(100):
            if adapter.direct_validation_calls:
                break
            await asyncio.sleep(0.01)
        assert adapter.direct_validation_calls == [("/usr/bin/true",)]
        runtime.jobs.cancel_job(job_id)
        return await task

    receipt = asyncio.run(exercise())

    assert receipt.job.status is JobStatus.CANCELLED
    assert receipt.attempt.status is AttemptStatus.CANCELLED
    assert receipt.validation_receipt_path is None
