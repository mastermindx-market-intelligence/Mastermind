"""RED-first contract tests for the bounded Executive terminal-return reducer."""
from __future__ import annotations

import asyncio
import dataclasses
import hashlib
import json
import os
import pwd
import sqlite3
import stat
import tempfile
from pathlib import Path

import pytest

from control_plane.ceo_intent import submit_intent
from control_plane.codex_worker import (
    CollectionReceipt,
    LAUNCH_ATTESTATION_SCHEMA_VERSION,
    WorkerResult,
    WorkerRunStatus,
)
from control_plane.executive_orchestration_result import (
    RESULT_SCHEMA,
    canonical_bytes,
    canonical_digest,
)
from control_plane.executive_runtime import (
    AttemptStatus,
    JobStatus,
    Runtime,
    StateConflict,
)
from control_plane.executive_supervisor import ExecutiveSupervisor
from control_plane.executive_terminal_return import (
    TerminalReturnError,
    reduce_terminal_return,
)
from tests.test_executive_os_phase1fc import (
    _complete_ohf_role,
    _cycle_through_completed_work,
    _register,
    _review_body,
    _v2_intent,
)
from tests.test_executive_supervisor import (
    FakeAdapter,
    FakeInspector,
    FakeProcessController,
)


_SEALED_WORKER_SECRET_CANARY = {
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
}


def _sealed_worker_path_identity(path: Path) -> dict[str, object]:
    resolved = path.resolve(strict=True)
    info = resolved.lstat()
    return {
        "path": str(resolved),
        "device": int(info.st_dev),
        "inode": int(info.st_ino),
        "mode": stat.S_IMODE(info.st_mode),
        "uid": int(info.st_uid),
        "gid": int(info.st_gid),
        "mtime_ns": int(info.st_mtime_ns),
    }


class _PlannerSealedWorkerAdapter(FakeAdapter):
    """Inert complete-launch adapter for one real SEALED_WORKER planner run."""

    def __init__(
        self,
        inspector: FakeInspector,
        *,
        root_job_id: str,
        provider_home: Path | None = None,
    ) -> None:
        super().__init__(inspector)
        self.root_job_id = root_job_id
        self._provider_home_guard = None
        if provider_home is None:
            self._provider_home_guard = tempfile.TemporaryDirectory(
                prefix="mmx-provider-home-",
            )
            provider_home = Path(self._provider_home_guard.name)
        self.provider_home = provider_home

    async def start(self, spec):
        ref = await super().start(spec)
        uid = os.geteuid()
        gid = os.getegid()
        self.ref = dataclasses.replace(
            ref,
            session_id=ref.pid,
            effective_uid=uid,
            effective_gid=gid,
            real_uid=uid,
            real_gid=gid,
        )
        return self.ref

    def launch_attestation(self, ref):
        assert ref == self.ref and self.spec is not None
        uid = os.geteuid()
        gid = os.getegid()
        worker_user = pwd.getpwuid(uid).pw_name
        return {
            "schema_version": LAUNCH_ATTESTATION_SCHEMA_VERSION,
            "created_at": ref.started_at,
            "executable_path": ref.binary.real_path,
            "binary": dataclasses.asdict(ref.binary),
            "rendered_argv": [ref.binary.real_path, "exec", "--json", "-"],
            "environment_keys": ["CODEX_HOME", "HOME", "PATH"],
            "permission_profile_sha256": "c" * 64,
            "prompt_sha256": hashlib.sha256(
                self.spec.prompt.encode("utf-8")
            ).hexdigest(),
            "expected_base_sha": self.spec.expected_base_sha,
            "observed_base_sha": ref.base_sha,
            "workspace_identity": {
                **_sealed_worker_path_identity(self.spec.workspace_path),
                "git_head": ref.base_sha,
            },
            "worker_identity": {
                "requested_user": worker_user,
                "observed_user": worker_user,
                "expected_uid": uid,
                "expected_gid": gid,
                "effective_uid": uid,
                "effective_gid": gid,
                "real_uid": uid,
                "real_gid": gid,
            },
            "provider_home_identity": _sealed_worker_path_identity(
                self.provider_home
            ),
            "secret_canary_verdict": dict(_SEALED_WORKER_SECRET_CANARY),
            "launch_nonce": ref.launch_nonce,
            "process_identity": {
                "pid": ref.pid,
                "pgid": ref.pgid,
                "session_id": ref.session_id,
                "start_identity": ref.process_start_identity,
                "boot_id": ref.boot_session_id,
                "effective_uid": ref.effective_uid,
                "effective_gid": ref.effective_gid,
                "real_uid": ref.real_uid,
                "real_gid": ref.real_gid,
            },
        }

    async def collect_result(self, ref):
        assert ref == self.ref and self.spec is not None
        envelope = {
            "schema_version": RESULT_SCHEMA,
            "job_id": self.spec.job_id,
            "run_id": self.spec.run_id,
            "worker_id": self.spec.worker_id,
            "role": "plan",
            "status": "COMPLETED",
            "role_result": {
                "schema_version": "mastermind.execution_plan/v1",
                "root_job_id": self.root_job_id,
                "plan_attempt_id": self.spec.run_id,
                "steps": [
                    {
                        "ordinal": 0,
                        "step_id": "step-1",
                        "objective": "Read one bounded source.",
                        "business_impact": "routine",
                        "review_required": False,
                        "requested_authorities": ["READ"],
                        "allowed_write_paths": [],
                        "validation_ids": [],
                        "attempt_limit": 1,
                        "cost_class": "small",
                    }
                ],
            },
            "summary": "sealed planner completed",
            "current_state": "complete",
            "next_actions": [],
            "errors": [],
            "validations": [],
        }
        result_path = Path(ref.result_path)
        result_path.write_bytes(canonical_bytes(envelope))
        result_path.chmod(0o600)
        provider_session_id = "thread-fixture"
        collected_ref = dataclasses.replace(
            ref,
            provider_session_id=provider_session_id,
        )
        result = WorkerResult(
            job_id=self.spec.job_id,
            run_id=self.spec.run_id,
            worker_id=self.spec.worker_id,
            status=WorkerRunStatus.SUCCEEDED,
            structured_output=envelope,
            artifact_manifest=(),
            git_manifest={"base_sha": "b" * 40, "head_sha": "b" * 40},
            usage={"input_tokens": 10, "output_tokens": 5},
            provider_session_id=provider_session_id,
            exit_code=0,
            started_at=ref.started_at,
            finished_at="2026-08-11T00:00:01+00:00",
            error=None,
        )
        return CollectionReceipt(
            process_ref=collected_ref,
            result=result,
            stdout_sha256=hashlib.sha256(
                Path(ref.stdout_path).read_bytes()
            ).hexdigest(),
            stderr_sha256=hashlib.sha256(
                Path(ref.stderr_path).read_bytes()
            ).hexdigest(),
            result_sha256=hashlib.sha256(result_path.read_bytes()).hexdigest(),
        )


def _completed_planner(tmp_path):
    runtime, _cycle, _dispatches, _root, planner, _work, _seal = (
        _cycle_through_completed_work(
            tmp_path / "runtime",
            intent_id="CEO-TERMINAL-RETURN-PLANNER",
            review_workers=["worker-b"],
        )
    )
    job = runtime.jobs.get_job(planner.job_id)
    attempt = runtime.attempts.get_attempt(planner.attempt.attempt_id)
    assert job is not None and attempt is not None
    return runtime, job, attempt


def _completed_planner_with_runtime(tmp_path):
    runtime, _cycle, _dispatches, _root, planner, _work, _seal = (
        _cycle_through_completed_work(
            tmp_path / "runtime-material",
            intent_id="CEO-TERMINAL-RETURN-RUNTIME-MATERIAL",
            review_workers=["worker-b"],
        )
    )
    job = runtime.jobs.get_job(planner.job_id)
    attempt = runtime.attempts.get_attempt(planner.attempt.attempt_id)
    assert job is not None and attempt is not None
    return runtime, job, attempt


def test_runtime_refuses_dialogue_source_digest_without_source(tmp_path: Path) -> None:
    runtime, job, attempt = _completed_planner_with_runtime(tmp_path)
    root_id = job.root_job_id
    with runtime.store.read() as connection:
        row = connection.execute(
            """SELECT event_id,payload_json FROM events
               WHERE event_type='JOB_CREATED' AND job_id=?""",
            (root_id,),
        ).fetchone()
    assert row is not None
    payload = json.loads(str(row["payload_json"]))
    assert "dialogue_source" not in payload["provenance"]
    payload["provenance"]["dialogue_source_digest"] = "a" * 64

    connection = sqlite3.connect(runtime.store.path)
    try:
        connection.execute("DROP TRIGGER events_are_immutable_update")
        connection.execute(
            "UPDATE events SET payload_json=? WHERE event_id=?",
            (
                json.dumps(payload, sort_keys=True, separators=(",", ":")),
                int(row["event_id"]),
            ),
        )
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(StateConflict, match="dialogue source drifted"):
        runtime.validated_role_completion(
            job.job_id,
            expected_attempt_id=attempt.attempt_id,
        )


def test_reducer_projects_positive_canonical_sealed_worker_completion(
    tmp_path: Path,
) -> None:
    runtime_root = tmp_path / "runtime"
    runtime = Runtime.at(runtime_root)
    _register(runtime, "worker-a")

    workspace_root = tmp_path / "workspaces"
    workspace = workspace_root / "planner"
    workspace.mkdir(parents=True, mode=0o700)
    admitted = submit_intent(
        runtime,
        _v2_intent(
            intent_id="CEO-SEALED-WORKER-TERMINAL-RETURN",
            execution_contract={
                "requested_authorities": ["READ"],
                "worktree": str(workspace),
                "attempt_limit": 2,
                "constraints": {"base_sha": "b" * 40},
            },
        ),
        workspace_root=workspace_root,
    )
    root = runtime.jobs.get_job(admitted["job_id"])
    assert root is not None
    planner = runtime.jobs.create_cycle_planner(
        root.job_id,
        command_id=f"coo-cycle:{root.job_id}:create-planner:0",
    )
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir(mode=0o700)
    adapter = _PlannerSealedWorkerAdapter(
        FakeInspector(),
        root_job_id=root.job_id,
        provider_home=codex_home,
    )
    uid = os.geteuid()
    gid = os.getegid()
    worker_user = pwd.getpwuid(uid).pw_name
    supervisor = ExecutiveSupervisor(
        runtime,
        adapter,
        runs_root=tmp_path / "runs",
        isolation_roots=(workspace_root, tmp_path / "runs"),
        worker_user=worker_user,
        worker_uid=uid,
        worker_gid=gid,
        heartbeat_interval_seconds=0.01,
        inspector=adapter.inspector,
        process_controller=FakeProcessController(adapter.inspector),
        secret_canary_verdict=_SEALED_WORKER_SECRET_CANARY,
        require_complete_launch_attestation=True,
        instance_id="supervisor-fixture",
    )
    receipt = asyncio.run(
        supervisor.run_cycle_once(
            planner.job_id,
            command_id=(
                f"coo-cycle:{root.job_id}:dispatch:"
                f"{planner.job_id}:attempt:1"
            ),
        )
    )

    assert receipt.job.status is JobStatus.COMPLETED
    assert receipt.attempt.status is AttemptStatus.COMPLETED
    assert receipt.attempt.execution_mode == "SEALED_WORKER"
    assert receipt.job.result == receipt.attempt.result
    assert adapter.direct_validation_calls == []

    reopened = Runtime.at(runtime_root)
    material = reopened.validated_role_completion(
        planner.job_id,
        expected_attempt_id=receipt.attempt.attempt_id,
    )
    candidate = reduce_terminal_return(material=material)

    terminal = material.terminal_receipt
    evidence = terminal["result_evidence"]
    assert material.execution_mode == "SEALED_WORKER"
    assert terminal["execution_mode"] == "SEALED_WORKER"
    assert terminal["result_seal_command_id"] == (
        f"sealed-worker-result:{receipt.attempt.attempt_id}"
    )
    assert set(evidence) == {
        "schema_version",
        "collection_receipt",
        "collection_receipt_digest",
        "validation_receipts",
        "validation_receipts_digest",
        "assignment_seal_receipt",
        "assignment_seal_receipt_digest",
    }
    assert evidence["schema_version"] == (
        "mastermind.sealed_worker_result_evidence/v1"
    )
    assert evidence["collection_receipt_digest"] == canonical_digest(
        evidence["collection_receipt"]
    )
    assert evidence["validation_receipts_digest"] == canonical_digest(
        evidence["validation_receipts"]
    )
    assert evidence["assignment_seal_receipt_digest"] == canonical_digest(
        evidence["assignment_seal_receipt"]
    )
    assert (
        evidence["collection_receipt"]["collection"]["result"][
            "structured_output"
        ]
        == material.result_envelope
    )
    assert terminal["artifact_receipt_digest"] == canonical_digest([])
    assert terminal["validation_receipt_digest"] == (
        evidence["validation_receipts_digest"]
    )
    assert terminal["result_envelope_digest"] == material.result_digest
    assert terminal["terminal_evidence_digest"] == canonical_digest(
        {
            key: value
            for key, value in terminal.items()
            if key != "terminal_evidence_digest"
        }
    )
    assert material.role_result_digest == canonical_digest(
        material.result_envelope["role_result"]
    )

    assert candidate.role == "plan"
    assert candidate.root_job_id == root.job_id
    assert candidate.summary == "sealed planner completed"
    assert candidate.result_digest == material.result_digest
    assert candidate.terminal_digest == terminal["terminal_evidence_digest"]
    assert candidate.result_envelope_digest == terminal["result_envelope_digest"]
    assert candidate.terminal_evidence_digest == terminal["terminal_evidence_digest"]
    assert candidate.artifact_receipt_digest == terminal["artifact_receipt_digest"]
    assert candidate.validation_receipt_digest == terminal["validation_receipt_digest"]
    assert candidate.effective_grant_digest == terminal["effective_grant_digest"]
    assert candidate.message_key == (
        f"asd-exec-result-{terminal['terminal_evidence_digest']}"
    )

    event_types = {
        event.event_type
        for event in reopened.events.list_events(
            attempt_id=receipt.attempt.attempt_id
        )
    }
    assert "ORCHESTRATION_ROLE_RESULT_SEALED" not in event_types
    assert {
        "ATTEMPT_PROCESS_RECORDED",
        "ATTEMPT_RUNNING",
        "ATTEMPT_PROCESS_EXITED",
        "JOB_COMPLETED",
    }.issubset(event_types)


def test_reducer_projects_one_exact_sealed_completed_child(tmp_path) -> None:
    runtime, job, attempt = _completed_planner(tmp_path)
    assert job.result == attempt.result

    material = runtime.validated_role_completion(
        job.job_id,
        expected_attempt_id=attempt.attempt_id,
    )
    candidate = reduce_terminal_return(material=material)

    assert candidate.job_id == job.job_id
    assert candidate.attempt_id == attempt.attempt_id
    assert candidate.worker_id == attempt.worker_id
    assert candidate.root_job_id == job.root_job_id
    assert candidate.role == "plan"
    assert candidate.runtime_status == "COMPLETED"
    assert candidate.result_status == "RESULT"
    assert candidate.operation_key == f"exec-{job.job_id.lower()}"
    assert candidate.session_ref == f"asd-session-exec-{job.job_id.lower()}"
    assert candidate.result_digest == job.result["result_envelope_digest"]
    assert candidate.terminal_digest == job.result["terminal_evidence_digest"]
    assert attempt.finished_at.endswith("+00:00")
    assert candidate.terminal_at == attempt.finished_at.removesuffix("+00:00") + "Z"
    assert candidate.message_key == f"asd-exec-result-{candidate.terminal_digest}"
    assert candidate.summary == "bounded typed fixture result"
    assert candidate.review_verdict is None


def _completed_review(tmp_path, verdict: str):
    runtime, cycle, dispatches, root, planner, work, work_seal = _cycle_through_completed_work(
        tmp_path / verdict,
        intent_id=f"CEO-TERMINAL-RETURN-{verdict.upper()}",
        review_workers=["worker-b"],
    )
    assert cycle.run_once(root.job_id).action == "REVIEW_CREATED"
    assert cycle.run_once(root.job_id).action == "DISPATCHED"
    review = dispatches[-1]
    work_job = runtime.jobs.get_job(work.attempt.job_id)
    assert work_job is not None
    _complete_ohf_role(
        runtime,
        review,
        _review_body(
            root_id=root.job_id,
            plan_attempt_id=planner.attempt.attempt_id,
            plan_digest=str(work_job.plan_digest),
            target_job_id=work.attempt.job_id,
            target_attempt_id=work.attempt.attempt_id,
            target_result_digest=work_seal["role_result_digest"],
            repair_round=0,
            verdict=verdict,
        ),
        identity_seed=744 if verdict == "approve" else 745,
    )
    job = runtime.jobs.get_job(review.attempt.job_id)
    attempt = runtime.attempts.get_attempt(review.attempt.attempt_id)
    assert job is not None and attempt is not None
    return runtime, job, attempt


@pytest.mark.parametrize("verdict", ["approve", "reject"])
def test_reducer_is_deterministic_and_preserves_review_verdict_shape(
    tmp_path, verdict
) -> None:
    runtime, job, attempt = _completed_review(tmp_path, verdict)
    material = runtime.validated_role_completion(
        job.job_id,
        expected_attempt_id=attempt.attempt_id,
    )

    first = reduce_terminal_return(material=material)
    second = reduce_terminal_return(material=material)

    assert first == second
    assert first.review_verdict == verdict


@pytest.mark.parametrize(
    "mutation",
    [
        pytest.param("missing", id="missing"),
        pytest.param("unknown", id="unknown"),
        pytest.param([], id="unhashable-list"),
    ],
)
def test_reducer_refuses_noncanonical_review_verdict(tmp_path, mutation) -> None:
    runtime, job, attempt = _completed_review(tmp_path, "approve")
    material = runtime.validated_role_completion(
        job.job_id,
        expected_attempt_id=attempt.attempt_id,
    )
    changed = dict(material.result_envelope)
    role_result = dict(changed["role_result"])
    if mutation == "missing":
        role_result.pop("verdict")
    else:
        role_result["verdict"] = mutation
    changed["role_result"] = role_result

    with pytest.raises(TerminalReturnError) as refused:
        reduce_terminal_return(
            material=dataclasses.replace(material, result_envelope=changed)
        )

    assert refused.value.code == "EVIDENCE_REFUSED"


@pytest.mark.parametrize(
    "job_change,attempt_change",
    [
        ({"parent_job_id": "JOB-999"}, {}),
        ({"current_attempt_id": "ATT-stale"}, {}),
        ({}, {"job_id": "JOB-foreign"}),
        ({}, {"worker_id": "worker-other"}),
    ],
)
def test_reducer_refuses_parent_attempt_or_worker_identity_drift(
    tmp_path, job_change, attempt_change
) -> None:
    runtime, job, attempt = _completed_planner(tmp_path)
    material = runtime.validated_role_completion(
        job.job_id,
        expected_attempt_id=attempt.attempt_id,
    )

    with pytest.raises(TerminalReturnError) as raised:
        reduce_terminal_return(
            material=dataclasses.replace(
                material,
                job=dataclasses.replace(job, **job_change),
                attempt=dataclasses.replace(attempt, **attempt_change),
            )
        )

    assert raised.value.code in {
        "IDENTITY_REFUSED",
        "BINDING_REFUSED",
        "EVIDENCE_REFUSED",
    }


def test_reducer_refuses_mutated_noncanonical_or_unsealed_receipt(tmp_path) -> None:
    runtime, job, attempt = _completed_planner(tmp_path)
    material = runtime.validated_role_completion(
        job.job_id,
        expected_attempt_id=attempt.attempt_id,
    )
    changed = dict(material.terminal_receipt)
    changed.pop("terminal_evidence_digest")

    with pytest.raises(TerminalReturnError) as raised:
        reduce_terminal_return(material=dataclasses.replace(material, terminal_receipt=changed))

    assert raised.value.code == "EVIDENCE_REFUSED"


def test_reducer_refuses_nan_nested_in_the_terminal_receipt(tmp_path) -> None:
    runtime, job, attempt = _completed_planner(tmp_path)
    material = runtime.validated_role_completion(
        job.job_id,
        expected_attempt_id=attempt.attempt_id,
    )
    changed = dict(material.result_envelope)
    changed["summary"] = float("nan")

    with pytest.raises(TerminalReturnError) as raised:
        reduce_terminal_return(material=dataclasses.replace(material, result_envelope=changed))

    assert raised.value.code == "EVIDENCE_REFUSED"


def test_reducer_refuses_missing_execution_mode_binding(tmp_path) -> None:
    runtime, job, attempt = _completed_planner(tmp_path)
    material = runtime.validated_role_completion(
        job.job_id,
        expected_attempt_id=attempt.attempt_id,
    )

    with pytest.raises(TerminalReturnError) as raised:
        reduce_terminal_return(
            material=dataclasses.replace(material, execution_mode="SEALED_WORKER"),
        )

    assert raised.value.code == "BINDING_REFUSED"


def test_reducer_treats_historical_null_execution_mode_as_sealed_worker(
    tmp_path,
) -> None:
    runtime, job, attempt = _completed_planner_with_runtime(tmp_path)
    material = runtime.validated_role_completion(
        job.job_id,
        expected_attempt_id=attempt.attempt_id,
    )

    candidate = reduce_terminal_return(
        material=dataclasses.replace(
            material,
            attempt=dataclasses.replace(attempt, execution_mode=None),
            execution_mode="SEALED_WORKER",
        )
    )

    assert candidate.attempt_id == attempt.attempt_id


@pytest.mark.parametrize("status", [AttemptStatus.FAILED, AttemptStatus.LOST, AttemptStatus.CANCELLED, AttemptStatus.RATE_LIMITED])
def test_reducer_gates_noncompleted_terminal_families(tmp_path, status) -> None:
    runtime, job, attempt = _completed_planner(tmp_path)
    material = runtime.validated_role_completion(
        job.job_id,
        expected_attempt_id=attempt.attempt_id,
    )

    with pytest.raises(TerminalReturnError) as raised:
        reduce_terminal_return(
            material=dataclasses.replace(
                material,
                job=dataclasses.replace(job, status=JobStatus(status.value)),
                attempt=dataclasses.replace(attempt, status=status),
            )
        )

    assert raised.value.code == "NOT_APPLICABLE"
