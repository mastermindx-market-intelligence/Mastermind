"""Model-free integration tests for the durable Executive supervisor seam."""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import signal
import sqlite3
import stat
from pathlib import Path

import pytest

from control_plane.ceo_intent import INTENT_SCHEMA_V2, submit_intent
from control_plane.codex_worker import (
    BinaryAttestation,
    CollectionReceipt,
    ProcessIdentityError,
    ProcessRef,
    ValidationReceipt,
    WorkerResult,
    WorkerRunStatus,
)
from control_plane.worker_execution_contract import LAUNCH_ATTESTATION_SCHEMA_VERSION
from control_plane.executive_agent_capabilities import ExecutionCapabilityRegistry
from control_plane.executive_runtime import (
    AttemptLease,
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
    SupervisorError,
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

    def uid_sweep_receipt(self, attempt):
        before = (
            [attempt.pid]
            if attempt.attempt_id in self.terminated_attempt_ids
            else []
        )
        return {
            "schema_version": "mastermind.executive_uid_sweep/v2",
            "observed_at": "2026-08-11T00:00:01+00:00",
            "reason": (
                "run_terminal"
                if attempt.attempt_id in self.terminated_attempt_ids
                else "status_absence"
            ),
            "worker_uid": os.geteuid() if os.geteuid() > 1 else 451,
            "broker_pid": 42419,
            "residual_pids_before": before,
            "residual_pids_after": [],
            "signal_name": "SIGKILL",
            "signal_sent": bool(before),
            "quiescent_observations": 2,
            "ambient_pids": [],
            "ambient_identities": [],
            "ambient_attribution": "absent",
            "passed": True,
            "found_residuals": bool(before),
        }


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
        ambiguous_start: bool = False,
    ) -> None:
        self.inspector = inspector
        self.output_status = output_status
        self.validation_argv = validation_argv or ["/usr/bin/true"]
        self.direct_validation_exit_code = direct_validation_exit_code
        self.direct_validation_delay = direct_validation_delay
        self.reported_validations = reported_validations
        self.ambiguous_start = ambiguous_start
        self.direct_validation_calls: list[tuple[str, ...]] = []
        self.spec = None
        self.ref = None
        self.provider_home: Path | None = None

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
        if self.ambiguous_start:
            raise ConnectionError("fixture lost broker start response")
        return self.ref

    async def cleanup_unbound_run(self, run_id: str):
        assert self.ref is not None and self.ref.run_id == run_id
        self.inspector.live = False
        return {
            "schema_version": "mastermind.executive_uid_sweep/v2",
            "observed_at": "2026-08-11T00:00:01+00:00",
            "reason": "status_absence",
            "worker_uid": os.geteuid() if os.geteuid() > 1 else 451,
            "broker_pid": 42419,
            "residual_pids_before": [],
            "residual_pids_after": [],
            "signal_name": "SIGKILL",
            "signal_sent": False,
            "quiescent_observations": 2,
            "ambient_pids": [],
            "ambient_identities": [],
            "ambient_attribution": "absent",
            "passed": True,
            "found_residuals": False,
        }

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

    def launch_attestation(self, ref):
        assert self.spec is not None and ref == self.ref and self.provider_home is not None
        return {
            "schema_version": LAUNCH_ATTESTATION_SCHEMA_VERSION,
            "created_at": ref.started_at,
            "executable_path": ref.binary.real_path,
            "binary": {
                "path": ref.binary.path,
                "real_path": ref.binary.real_path,
                "version": ref.binary.version,
                "sha256": ref.binary.sha256,
                "team_identifier": ref.binary.team_identifier,
                "size": ref.binary.size,
                "device": ref.binary.device,
                "inode": ref.binary.inode,
                "mode": ref.binary.mode,
                "uid": ref.binary.uid,
                "gid": ref.binary.gid,
                "mtime_ns": ref.binary.mtime_ns,
            },
            "rendered_argv": [ref.binary.real_path, "exec", "--json", "-"],
            "environment_keys": ["CODEX_HOME", "HOME", "PATH"],
            "permission_profile_sha256": "c" * 64,
            "prompt_sha256": hashlib.sha256(self.spec.prompt.encode()).hexdigest(),
            "expected_base_sha": self.spec.expected_base_sha,
            "observed_base_sha": ref.base_sha,
            "workspace_identity": {"path": str(self.spec.workspace_path)},
            "worker_identity": {
                "requested_user": self.spec.worker_user,
                "effective_uid": os.geteuid(),
                "effective_gid": os.getegid(),
            },
            "provider_home_identity": {"path": str(self.provider_home)},
            "secret_canary_verdict": {
                "schema_version": "mastermind.executive_secret_canary/v1",
                "passed": True,
            },
            "launch_nonce": ref.launch_nonce,
            "process_identity": {
                "pid": ref.pid,
                "pgid": ref.pgid,
                "session_id": ref.pid,
                "start_identity": ref.process_start_identity,
                "boot_id": ref.boot_session_id,
                "effective_uid": os.geteuid(),
                "effective_gid": os.getegid(),
                "real_uid": os.geteuid(),
                "real_gid": os.getegid(),
            },
        }

    def uid_sweep_receipt(self, ref):
        assert ref == self.ref
        return {
            "schema_version": "mastermind.executive_uid_sweep/v2",
            "observed_at": "2026-08-11T00:00:01+00:00",
            "reason": "run_terminal",
            "worker_uid": os.geteuid() if os.geteuid() > 1 else 451,
            "broker_pid": 42419,
            "residual_pids_before": [],
            "residual_pids_after": [],
            "signal_name": "SIGKILL",
            "signal_sent": False,
            "quiescent_observations": 2,
            "ambient_pids": [],
            "ambient_identities": [],
            "ambient_attribution": "absent",
            "passed": True,
            "found_residuals": False,
        }

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
    workspace = tmp_path / "workspaces" / "isolated-workspace"
    workspace.mkdir(mode=0o700, parents=True)
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


def _supervisor(runtime: Runtime, tmp_path: Path, adapter: FakeAdapter, **kwargs) -> ExecutiveSupervisor:
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir(mode=0o700, exist_ok=True)
    adapter.provider_home = codex_home
    return ExecutiveSupervisor(
        runtime,
        adapter,  # type: ignore[arg-type]
        runs_root=tmp_path / "runs",
        isolation_roots=(tmp_path / "workspaces", tmp_path / "runs"),
        heartbeat_interval_seconds=0.01,
        inspector=adapter.inspector,
        process_controller=FakeProcessController(adapter.inspector),
        secret_canary_verdict={
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
            "control_environment_probe_sha256": "b" * 64,
            "observed_at": "2026-08-11T00:00:00Z",
            "worker_auth_exception": "DEDICATED_CODEX_HOME_ONLY",
        },
        require_complete_launch_attestation=True,
        instance_id="supervisor-fixture",
        **kwargs,
    )


def _runtime_and_routed_job(
    tmp_path: Path,
    *,
    profile_id: str = "sealed.worker.write.no-extensions.v1",
) -> tuple[Runtime, str, Path]:
    registry = ExecutionCapabilityRegistry.load()
    profile = registry.resolve(profile_id)
    capability_identity = {
        "execution_profile_id": profile.profile_id,
        "execution_profile_digest": profile.profile_digest,
        "capability_policy_version": registry.policy_version,
        "capability_policy_digest": registry.policy_digest,
    }
    runtime = Runtime.at(tmp_path)
    runtime.workers.register_worker(
        "codex-routed-01",
        provider="codex",
        account_label="dedicated-worker-account",
        worker_type="codex-cli",
        capabilities=["code", "tests"],
        quota_classes={
            "codex-native": {
                "capabilities": ["code", "tests"],
                "model": "gpt-5.6-sol",
                "effort": "xhigh",
                "cost_class": "standard",
                "metadata": capability_identity,
            }
        },
    )
    workspace = tmp_path / "workspaces" / "routed-workspace"
    workspace.mkdir(mode=0o700, parents=True)
    job = runtime.jobs.create_job(
        "Execute only under the exact reviewed capability profile",
        worktree=str(workspace.resolve()),
        requested_authorities=["READ", "WRITE_BRANCH", "RUN_TESTS"],
        allowed_write_paths=["control_plane/proof.py"],
        validation_commands=[["/usr/bin/true"]],
        constraints={
            "provider": "codex",
            "model": "gpt-5.6-sol",
            "effort": "xhigh",
            "cost_class": "standard",
            "base_sha": "c" * 40,
            "eligible_quota_classes": ["codex-native"],
            "required_capabilities": ["code", "tests"],
            "routing_policy_version": "2026-08-24.stage2",
            **capability_identity,
        },
        attempt_limit=1,
    )
    return runtime, job.job_id, workspace


def test_routed_job_launches_only_with_exact_installed_capability_profile(
    tmp_path: Path,
) -> None:
    runtime, job_id, _ = _runtime_and_routed_job(tmp_path)
    inspector = FakeInspector()
    adapter = FakeAdapter(inspector)
    supervisor = _supervisor(runtime, tmp_path, adapter)

    active = asyncio.run(supervisor.start_job(job_id))

    assert adapter.spec is not None
    assert active.lease.attempt.status is AttemptStatus.CLAIMED
    persisted = runtime.attempts.get_attempt(active.lease.attempt.attempt_id)
    assert persisted is not None and persisted.status is AttemptStatus.CHECKPOINTED
    assert persisted.launch_metadata["routing"]["execution_profile_id"] == (
        "sealed.worker.write.no-extensions.v1"
    )


def test_routed_job_refuses_capacity_profile_drift_before_provider_start(
    tmp_path: Path,
) -> None:
    runtime, job_id, _ = _runtime_and_routed_job(tmp_path)
    lease = runtime.attempts.claim_job(job_id, lease_owner="supervisor-fixture")
    assert lease is not None
    with sqlite3.connect(runtime.store.path) as connection:
        row = connection.execute(
            """
            SELECT metadata_json FROM worker_quota_classes
            WHERE worker_id=? AND quota_class=?
            """,
            (lease.attempt.worker_id, lease.attempt.quota_class),
        ).fetchone()
        assert row is not None
        metadata = json.loads(row[0])
        metadata["execution_profile_digest"] = "0" * 64
        connection.execute(
            """
            UPDATE worker_quota_classes SET metadata_json=?
            WHERE worker_id=? AND quota_class=?
            """,
            (
                json.dumps(metadata, sort_keys=True, separators=(",", ":")),
                lease.attempt.worker_id,
                lease.attempt.quota_class,
            ),
        )

    inspector = FakeInspector()
    adapter = FakeAdapter(inspector)
    supervisor = _supervisor(runtime, tmp_path, adapter)
    with pytest.raises(
        SupervisorError, match="capacity execution-profile identity drifted"
    ):
        asyncio.run(supervisor._start_claimed_job(job_id, lease))

    assert adapter.spec is None
    attempt = runtime.attempts.get_attempt(lease.attempt.attempt_id)
    job = runtime.jobs.get_job(job_id)
    assert attempt is not None and attempt.status is AttemptStatus.FAILED
    assert job is not None and job.status is JobStatus.FAILED


def test_read_only_profile_refuses_write_grant_before_provider_start(
    tmp_path: Path,
) -> None:
    runtime, job_id, _ = _runtime_and_routed_job(
        tmp_path,
        profile_id="sealed.worker.readonly.no-extensions.v1",
    )
    inspector = FakeInspector()
    adapter = FakeAdapter(inspector)

    with pytest.raises(SupervisorError, match="read-only execution profile"):
        asyncio.run(_supervisor(runtime, tmp_path, adapter).start_job(job_id))

    assert adapter.spec is None
    job = runtime.jobs.get_job(job_id)
    assert job is not None and job.status is JobStatus.FAILED


def test_start_cycle_job_claims_only_exact_command_bound_job_before_launch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime = Runtime.at(tmp_path)
    runtime.workers.register_worker(
        "worker-cycle",
        provider="codex",
        account_label="worker-cycle@company",
        worker_type="fixture",
        capabilities=["read"],
        quota_classes={
            "default": {
                "provider": "codex",
                "capabilities": ["read"],
                "cost_class": "small",
            }
        },
    )
    admitted = submit_intent(
        runtime,
        {
            "schema": INTENT_SCHEMA_V2,
            "intent_id": "CEO-SUPERVISOR-EXACT-DISPATCH",
            "actor": "ceo-sol",
            "objective": "Prove the accepted exact-job supervisor boundary.",
            "department": "executive-infrastructure",
            "priority": 9,
            "grounding": {"mastermind_sha": "a" * 40, "macro_sha": "b" * 40},
            "execution_contract": {
                "requested_authorities": ["READ"],
                "attempt_limit": 2,
            },
            "intent_kind": "executive_coo_cycle",
            "business_impact": "material",
        },
    )
    root = runtime.jobs.get_job(admitted["job_id"])
    assert root is not None
    planner = runtime.jobs.create_cycle_planner(
        root.job_id,
        command_id=f"coo-cycle:{root.job_id}:create-planner:0",
    )
    unrelated = runtime.jobs.create_job("Unrelated queued sentinel")
    supervisor = _supervisor(runtime, tmp_path, FakeAdapter(FakeInspector()))
    captured: list[AttemptLease] = []

    async def stop_before_provider(_job_id: str, lease: AttemptLease):
        captured.append(lease)
        return lease

    monkeypatch.setattr(supervisor, "_start_claimed_job", stop_before_provider)
    command = f"coo-cycle:{root.job_id}:dispatch:{planner.job_id}:attempt:1"

    result = asyncio.run(supervisor.start_cycle_job(planner.job_id, command_id=command))

    assert isinstance(result, AttemptLease)
    assert result.attempt.job_id == planner.job_id
    assert captured == [result]
    assert runtime.attempts.list_attempts(unrelated.job_id) == []
    assert runtime.jobs.get_job(unrelated.job_id).status is JobStatus.QUEUED


def test_run_once_persists_process_checkpoint_result_receipt_and_reopens(tmp_path: Path):
    runtime, job_id, _workspace = _runtime_and_job(tmp_path)
    inspector = FakeInspector()
    adapter = FakeAdapter(inspector)

    receipt = asyncio.run(_supervisor(runtime, tmp_path, adapter).run_once(job_id))

    assert receipt.job.status is JobStatus.COMPLETED
    assert receipt.attempt.status is AttemptStatus.COMPLETED
    assert receipt.attempt.pid == inspector.pid
    assert receipt.attempt.process_start_identity == inspector.start_identity
    assert receipt.attempt.checkpoint_sequence == 2
    assert (
        receipt.attempt.launch_metadata["launch_attestation"]["schema_version"]
        == LAUNCH_ATTESTATION_SCHEMA_VERSION
    )
    launch_evidence = Path(receipt.attempt.launch_metadata["launch_attestation_path"])
    assert launch_evidence.is_file()
    assert stat.S_IMODE(launch_evidence.stat().st_mode) == 0o600
    assert adapter.spec.prompt not in launch_evidence.read_text(encoding="utf-8")
    event_types = [
        event.event_type
        for event in runtime.events.list_events(attempt_id=receipt.attempt.attempt_id)
    ]
    assert event_types.index("ATTEMPT_PROCESS_RECORDED") < event_types.index(
        "ATTEMPT_RUNNING"
    )
    assert event_types.index("ATTEMPT_RUNNING") < event_types.index(
        "JOB_CHECKPOINTED"
    )
    assert adapter.spec.expected_base_sha == "b" * 40
    assert adapter.spec.isolation_roots == (
        (tmp_path / "workspaces").resolve(),
        (tmp_path / "runs").resolve(),
    )
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
    assert persisted["schema_version"] == "mastermind.executive_collection_evidence/v1"
    assert persisted["collection"]["result"]["status"] == "SUCCEEDED"
    assert persisted["uid_sweep"]["passed"] is True
    assert "lease_token" not in evidence.read_text(encoding="utf-8")
    assert adapter.direct_validation_calls == [("/usr/bin/true",)]
    validation_evidence = Path(receipt.validation_receipt_path or "")
    assert validation_evidence.is_file()
    assert stat.S_IMODE(validation_evidence.stat().st_mode) == 0o600
    validation_payload = json.loads(validation_evidence.read_text(encoding="utf-8"))
    assert validation_payload["commands"][0]["argv"] == ["/usr/bin/true"]
    assert validation_payload["commands"][0]["exit_code"] == 0
    assert validation_payload["uid_sweep"]["passed"] is True
    seal_evidence = Path(receipt.assignment_seal_receipt_path or "")
    assert seal_evidence.is_file()
    assert stat.S_IMODE(seal_evidence.stat().st_mode) == 0o600
    seal_payload = json.loads(seal_evidence.read_text(encoding="utf-8"))
    assert seal_payload["schema_version"] == "mastermind.executive_assignment_seal/v1"
    assert seal_payload["uid_sweep"]["passed"] is True
    assert seal_payload["paths"]["workspace"]["after"]["mode"] == 0o700
    assert seal_payload["paths"]["run"]["after"]["mode"] == 0o700

    reopened = Runtime.at(tmp_path)
    reopened_job = reopened.jobs.get_job(job_id)
    reopened_attempt = reopened.attempts.get_attempt(receipt.attempt.attempt_id)
    assert reopened_job is not None and reopened_job.status is JobStatus.COMPLETED
    assert reopened_attempt is not None and reopened_attempt.status is AttemptStatus.COMPLETED
    assert reopened_attempt.result == reopened_job.result


def test_complete_launch_attestation_reads_schema_version_from_common_contract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Supervisor gate must compare against the common contract constant,
    not against ``control_plane.codex_worker.LAUNCH_ATTESTATION_SCHEMA_VERSION``.

    Mutating the Codex module's constant must not flip the verdict on a
    non-Codex adapter that legitimately emits the COMMON attestation
    schema.  The carried effective grant activates the gate branch that
    requires a complete launch attestation even when the supervisor is
    not configured with ``require_complete_launch_attestation=True``.
    """

    import control_plane.codex_worker as codex_worker_module
    import control_plane.worker_execution_contract as worker_contract_module

    monkeypatch.setattr(
        codex_worker_module,
        "LAUNCH_ATTESTATION_SCHEMA_VERSION",
        "codex.adulterated_attestation/v9",
    )

    def fake_effective_grant(job, attempt):
        return {
            "schema_version": "mastermind.executive_effective_grant/v1",
            "authorities": ["READ", "RESEARCH", "WRITE_BRANCH", "RUN_TESTS"],
            "write_paths": ["research/proof.md"],
            "validation_argv": ["/usr/bin/true"],
            "policy_sha": "p" * 64,
            "job_id": job.job_id,
            "role": "primary",
        }

    monkeypatch.setattr(
        ExecutiveSupervisor,
        "_effective_grant",
        staticmethod(fake_effective_grant),
    )

    runtime, job_id, _workspace = _runtime_and_job(tmp_path)
    inspector = FakeInspector()
    adapter = FakeAdapter(inspector)
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir(mode=0o700, exist_ok=True)
    adapter.provider_home = codex_home
    supervisor = ExecutiveSupervisor(
        runtime,
        adapter,  # type: ignore[arg-type]
        runs_root=tmp_path / "runs",
        isolation_roots=(tmp_path / "workspaces", tmp_path / "runs"),
        heartbeat_interval_seconds=0.01,
        inspector=adapter.inspector,
        process_controller=FakeProcessController(adapter.inspector),
        secret_canary_verdict={
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
            "control_environment_probe_sha256": "b" * 64,
            "observed_at": "2026-08-11T00:00:00Z",
            "worker_auth_exception": "DEDICATED_CODEX_HOME_ONLY",
        },
        require_complete_launch_attestation=False,
        instance_id="supervisor-fixture-common-contract",
    )

    receipt = asyncio.run(supervisor.run_once(job_id))

    assert receipt.attempt.status is AttemptStatus.COMPLETED
    persisted_attestation = receipt.attempt.launch_metadata["launch_attestation"]
    assert (
        persisted_attestation["schema_version"]
        == worker_contract_module.LAUNCH_ATTESTATION_SCHEMA_VERSION
    )
    assert (
        persisted_attestation["schema_version"]
        == "mastermind.executive_launch_attestation/v1"
    )
    assert (
        persisted_attestation["schema_version"]
        != codex_worker_module.LAUNCH_ATTESTATION_SCHEMA_VERSION
    )
    assert persisted_attestation.get("effective_grant_digest") == (
        receipt.attempt.effective_grant_digest
    )


def test_terminal_state_is_not_persisted_when_assignment_seal_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    runtime, job_id, _workspace = _runtime_and_job(tmp_path)
    supervisor = _supervisor(runtime, tmp_path, FakeAdapter(FakeInspector()))

    def fail_seal(*_args, **_kwargs):
        from control_plane.executive_workspace import AssignmentSealError

        raise AssignmentSealError("fixture seal failure")

    monkeypatch.setattr(
        "control_plane.executive_supervisor.seal_control_owned_paths", fail_seal
    )

    with pytest.raises(Exception, match="seal failure"):
        asyncio.run(supervisor.run_once(job_id))

    job = runtime.jobs.get_job(job_id)
    assert job is not None and job.status is JobStatus.CHECKPOINTED
    attempt = runtime.attempts.get_attempt(job.current_attempt_id or "")
    assert attempt is not None and attempt.status is AttemptStatus.CHECKPOINTED


def test_ambiguous_start_is_cleaned_swept_sealed_before_failed_state(tmp_path: Path):
    runtime, job_id, workspace = _runtime_and_job(tmp_path)
    adapter = FakeAdapter(FakeInspector(), ambiguous_start=True)
    supervisor = _supervisor(runtime, tmp_path, adapter)

    with pytest.raises(Exception, match="launch failed"):
        asyncio.run(supervisor.start_job(job_id))

    job = runtime.jobs.get_job(job_id)
    assert job is not None and job.status is JobStatus.FAILED
    attempt = runtime.attempts.get_attempt(job.current_attempt_id or "")
    assert attempt is not None and attempt.status is AttemptStatus.FAILED
    seal_path = (
        runtime.store.path.parent
        / "assignment-seal-receipts"
        / attempt.attempt_id
        / "assignment-seal-receipt.json"
    )
    seal = json.loads(seal_path.read_text(encoding="utf-8"))
    assert seal["uid_sweep"]["reason"] == "status_absence"
    assert stat.S_IMODE(workspace.stat().st_mode) == 0o700
    assert stat.S_IMODE((tmp_path / "runs" / attempt.attempt_id).stat().st_mode) == 0o700


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
    assert outcomes[0].status is ReconcileStatus.MISSING_LOST
    assert outcomes[0].requeued is False
    absence_evidence = Path(outcomes[0].uid_sweep_receipt_path or "")
    assert absence_evidence.is_file()
    absence_payload = json.loads(absence_evidence.read_text(encoding="utf-8"))
    assert absence_payload["uid_sweep"]["reason"] == "status_absence"
    attempt = reopened.attempts.get_attempt(active.lease.attempt.attempt_id)
    job = reopened.jobs.get_job(job_id)
    assert attempt is not None and attempt.status is AttemptStatus.LOST
    assert attempt.fence_generation == original_fence + 1
    assert job is not None and job.status is JobStatus.LOST
    seal_evidence = Path(outcomes[0].assignment_seal_receipt_path or "")
    assert seal_evidence.is_file()
    assert json.loads(seal_evidence.read_text(encoding="utf-8"))["uid_sweep"][
        "reason"
    ] == "status_absence"
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

    assert [item.status for item in outcomes] == [ReconcileStatus.MISSING_LOST]
    assert outcomes[0].process_was_live is True
    reconciliation_evidence = Path(outcomes[0].uid_sweep_receipt_path or "")
    assert reconciliation_evidence.is_file()
    assert stat.S_IMODE(reconciliation_evidence.stat().st_mode) == 0o600
    reconciliation_payload = json.loads(
        reconciliation_evidence.read_text(encoding="utf-8")
    )
    assert reconciliation_payload["uid_sweep"]["passed"] is True
    assert "lease_token" not in reconciliation_evidence.read_text(encoding="utf-8")
    assert restarted.process_controller.terminated_attempt_ids == [
        active.lease.attempt.attempt_id
    ]
    attempt = reopened.attempts.get_attempt(active.lease.attempt.attempt_id)
    job = reopened.jobs.get_job(job_id)
    assert attempt is not None and attempt.status is AttemptStatus.LOST
    assert job is not None and job.status is JobStatus.LOST


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

    assert [item.status for item in outcomes] == [ReconcileStatus.EXPIRED_LOST]
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
    assert attempt is not None and attempt.status is AttemptStatus.CHECKPOINTED
    assert job is not None and job.status is JobStatus.CHECKPOINTED


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


def test_invalid_provider_result_with_ambient_pid_fails_job_not_containment(
    tmp_path: Path,
) -> None:
    """A platform ambient process plus INVALID_RESULT is a Job failure, not quarantine."""

    import dataclasses

    from control_plane.executive_ambient_process import (
        AMBIENT_CODESIGN_IDENTIFIER,
        AMBIENT_LAUNCHD_LABEL,
        AMBIENT_PLIST_PATH,
        AMBIENT_PROGRAM_PATH,
        AmbientProcessIdentity,
    )

    class InvalidAmbientAdapter(FakeAdapter):
        async def collect_result(self, ref):
            receipt = await super().collect_result(ref)
            result = dataclasses.replace(
                receipt.result,
                status=WorkerRunStatus.INVALID_RESULT,
                error="INVALID_RESULT",
                structured_output=None,
                exit_code=1,
            )
            return dataclasses.replace(receipt, result=result)

        def uid_sweep_receipt(self, ref):
            value = dict(super().uid_sweep_receipt(ref))
            identity = AmbientProcessIdentity(
                pid=88688,
                uid=os.geteuid() if os.geteuid() > 1 else 451,
                launchd_domain="user/451",
                launchd_label=AMBIENT_LAUNCHD_LABEL,
                launchd_reported_pid=88688,
                plist_path=AMBIENT_PLIST_PATH,
                program_path=AMBIENT_PROGRAM_PATH,
                executable_path=AMBIENT_PROGRAM_PATH,
                executable_device=1,
                executable_inode=1,
                codesign_identifier=AMBIENT_CODESIGN_IDENTIFIER,
                codesign_verified=True,
            )
            value["ambient_pids"] = [88688]
            value["ambient_identities"] = [identity.to_dict()]
            value["ambient_attribution"] = "attested"
            return value

    runtime, job_id, _workspace = _runtime_and_job(tmp_path)
    receipt = asyncio.run(
        _supervisor(runtime, tmp_path, InvalidAmbientAdapter(FakeInspector())).run_once(
            job_id
        )
    )
    assert receipt.job.status is JobStatus.FAILED
    assert receipt.attempt.status is AttemptStatus.FAILED
    assert receipt.attempt.exit_code == 1
    evidence = Path(receipt.collection_receipt_path)
    persisted = json.loads(evidence.read_text(encoding="utf-8"))
    assert persisted["collection"]["result"]["status"] == "INVALID_RESULT"
    assert persisted["uid_sweep"]["ambient_pids"] == [88688]
    assert persisted["uid_sweep"]["found_residuals"] is False
    seal = json.loads(Path(receipt.assignment_seal_receipt_path or "").read_text())
    assert seal["passed"] is True
    assert seal["uid_sweep"]["ambient_pids"] == [88688]


class Hf1bResultAdapter(FakeAdapter):
    """No provider process; writes only the existing fixture run-output files."""
    def __init__(self, inspector, runtime, work):
        super().__init__(inspector)
        self.runtime, self.work, self.start_count = runtime, work, 0
        self.entered, self.continue_start = None, None

    async def start(self, spec):
        self.start_count += 1
        if self.entered is not None:
            self.entered.set()
            await self.continue_start.wait()
        from dataclasses import replace
        ref = await super().start(spec)
        self.ref = replace(ref, provider_session_id="thread-fixture", session_id=ref.pid,
                           effective_uid=os.geteuid(), effective_gid=os.getegid(),
                           real_uid=os.geteuid(), real_gid=os.getegid())
        return self.ref

    def launch_attestation(self, ref):
        receipt = super().launch_attestation(ref)
        uid, gid = os.geteuid(), os.getegid()
        receipt["worker_identity"] = {
            "requested_user": self.spec.worker_user, "observed_user": self.spec.worker_user,
            "expected_uid": uid, "expected_gid": gid, "effective_uid": uid,
            "effective_gid": gid, "real_uid": uid, "real_gid": gid,
        }
        info = self.provider_home.stat()
        receipt["provider_home_identity"] = {
            "path": str(self.provider_home.resolve()), "device": info.st_dev,
            "inode": info.st_ino, "uid": info.st_uid, "gid": info.st_gid,
            "mode": stat.S_IMODE(info.st_mode), "mtime_ns": info.st_mtime_ns,
        }
        return receipt

    async def collect_result(self, ref):
        job = self.runtime.jobs.get_job(self.work.job_id)
        output = {
            "schema_version": "mastermind.executive_orchestration_result/v1",
            "job_id": job.job_id, "run_id": self.spec.run_id,
            "worker_id": self.spec.worker_id, "role": "work", "status": "COMPLETED",
            "role_result": {"schema_version": "mastermind.work_result/v1",
                "root_job_id": job.root_job_id, "plan_attempt_id": job.plan_attempt_id,
                "plan_digest": job.plan_digest, "plan_step_id": job.plan_step_id,
                "repair_round": job.repair_round, "artifacts": [], "evidence_digests": []},
            "summary": "One bounded fixture read completed.", "current_state": "done",
            "next_actions": [], "errors": [], "validations": [],
        }
        result_bytes = json.dumps(output, sort_keys=True, separators=(",", ":")).encode()
        Path(ref.result_path).write_bytes(result_bytes)
        result = WorkerResult(job_id=job.job_id, run_id=self.spec.run_id,
            worker_id=self.spec.worker_id, status=WorkerRunStatus.SUCCEEDED,
            structured_output=output, artifact_manifest=(), git_manifest={}, usage={},
            provider_session_id="thread-fixture", exit_code=0, started_at=ref.started_at,
            finished_at="2026-08-11T00:00:01+00:00", error=None)
        return CollectionReceipt(process_ref=ref, result=result,
            stdout_sha256=hashlib.sha256(Path(ref.stdout_path).read_bytes()).hexdigest(),
            stderr_sha256=hashlib.sha256(Path(ref.stderr_path).read_bytes()).hexdigest(),
            result_sha256=hashlib.sha256(result_bytes).hexdigest())


def _hf1b_supervisor_fixture(tmp_path, *, revalidate=lambda: None):
    from test_executive_os_sqlite import _hf1b_claim_fixture, _hf1b_issue
    runtime, root, work, command, definition, observation = _hf1b_claim_fixture(tmp_path)
    target = _hf1b_issue(definition, observation, revalidate=revalidate)
    adapter = Hf1bResultAdapter(FakeInspector(), runtime, work)
    supervisor = _supervisor(runtime, tmp_path, adapter,
        exact_target_provider=lambda job_id: target if job_id == work.job_id else None)
    # macOS temp directories inherit wheel; the fixture worker/home must agree.
    os.chown(adapter.provider_home, -1, os.getegid())
    return runtime, root, work, command, target, adapter, supervisor


def test_hf1b_supervisor_result_reaches_canonical_parent_consumer(tmp_path):
    from control_plane.executive_coo_cycle import CooCycle
    runtime, root, work, command, target, adapter, supervisor = _hf1b_supervisor_fixture(tmp_path)
    async def exercise():
        active = await supervisor.start_cycle_job(work.job_id, command_id=command)
        assert adapter.start_count == 1
        replay = await supervisor.start_cycle_job(work.job_id, command_id=command)
        assert not replay.claimed_now and adapter.start_count == 1
        adapter.inspector.live = False
        finished = await supervisor.finish_job(active)
        assert finished.job.status is JobStatus.COMPLETED
        assert finished.attempt.status is AttemptStatus.COMPLETED
        terminal = await supervisor.start_cycle_job(work.job_id, command_id=command)
        assert terminal.outcome == "TERMINAL" and adapter.start_count == 1
        assert runtime.store.get_event_by_command_id(command).payload["exact_worker_target"] == target.evidence()
        result = CooCycle(runtime).run_once(root.job_id)
        assert result.action == "HANDOFF_CREATED"
        return finished
    finished = asyncio.run(exercise())
    assert Path(finished.collection_receipt_path).is_file()
    assert Path(finished.assignment_seal_receipt_path).is_file()


def test_hf1b_source_fence_after_claim_fails_same_attempt_without_adapter_entry(tmp_path):
    def moved():
        raise SupervisorError("fixture target source moved")
    runtime, _, work, command, _, adapter, supervisor = _hf1b_supervisor_fixture(tmp_path, revalidate=moved)
    with pytest.raises(SupervisorError, match="target source moved"):
        asyncio.run(supervisor.start_cycle_job(work.job_id, command_id=command))
    assert adapter.start_count == 0
    attempts = runtime.attempts.list_attempts(work.job_id)
    assert len(attempts) == 1 and attempts[0].status is AttemptStatus.FAILED
    with runtime.store.read() as connection:
        assert connection.execute("SELECT held_attempt_id FROM worker_quota_classes WHERE worker_id=? AND quota_class=?", ("worker-a", "default")).fetchone()[0] is None
    assert runtime.store.get_event_by_command_id(command) is not None


def test_hf1b_recovered_claim_does_not_recreate_first_launch_permission(tmp_path):
    runtime, _, work, command, target, adapter, supervisor = _hf1b_supervisor_fixture(tmp_path)
    original = runtime.attempts.dispatch_cycle_job(work.job_id, command_id=command, exact_target=target, lease_owner=supervisor.instance_id)
    replay = asyncio.run(supervisor.start_cycle_job(work.job_id, command_id=command))
    assert replay.attempt.attempt_id == original.attempt.attempt_id and not replay.claimed_now
    assert adapter.start_count == 0
    assert runtime.attempts.get_attempt(original.attempt.attempt_id).status is AttemptStatus.CLAIMED


def test_hf1b_duplicate_delivery_during_adapter_start_leaves_original_live(tmp_path):
    runtime, _, work, command, _, adapter, supervisor = _hf1b_supervisor_fixture(tmp_path)
    async def exercise():
        adapter.entered, adapter.continue_start = asyncio.Event(), asyncio.Event()
        first = asyncio.create_task(supervisor.start_cycle_job(work.job_id, command_id=command))
        await asyncio.wait_for(adapter.entered.wait(), timeout=5)
        second = await supervisor.start_cycle_job(work.job_id, command_id=command)
        assert not second.claimed_now and adapter.start_count == 1
        assert second.attempt.status is AttemptStatus.CLAIMED
        adapter.continue_start.set()
        active = await asyncio.wait_for(first, timeout=5)
        assert runtime.attempts.get_attempt(active.lease.attempt.attempt_id).status is AttemptStatus.CHECKPOINTED
        adapter.inspector.live = False
        assert (await supervisor.finish_job(active)).job.status is JobStatus.COMPLETED
    asyncio.run(exercise())


def test_hf1b_lost_adapter_response_never_relaunches_on_replay(tmp_path):
    runtime, _, work, command, _, adapter, supervisor = _hf1b_supervisor_fixture(tmp_path)
    adapter.ambiguous_start = True
    with pytest.raises(SupervisorError):
        asyncio.run(supervisor.start_cycle_job(work.job_id, command_id=command))
    attempts = runtime.attempts.list_attempts(work.job_id)
    assert len(attempts) == 1 and adapter.start_count == 1
    replay = asyncio.run(supervisor.start_cycle_job(work.job_id, command_id=command))
    assert replay.attempt.attempt_id == attempts[0].attempt_id and adapter.start_count == 1


def test_hf1b_disconnected_completion_consumer_cannot_report_completed(tmp_path, monkeypatch):
    runtime, _, work, command, _, adapter, supervisor = _hf1b_supervisor_fixture(tmp_path)
    def unavailable(*args, **kwargs):
        raise StateConflict("fixture canonical completion unavailable")
    async def exercise():
        active = await supervisor.start_cycle_job(work.job_id, command_id=command)
        adapter.inspector.live = False
        monkeypatch.setattr(runtime.attempts, "complete_attempt", unavailable)
        with pytest.raises(StateConflict, match="canonical completion unavailable"):
            await supervisor.finish_job(active)
        assert runtime.jobs.get_job(work.job_id).status is not JobStatus.COMPLETED
        replay = await supervisor.start_cycle_job(work.job_id, command_id=command)
        assert not replay.claimed_now and adapter.start_count == 1
    asyncio.run(exercise())
