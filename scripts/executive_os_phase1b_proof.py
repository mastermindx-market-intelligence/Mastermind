"""Explicit real-process acceptance proof for Executive OS Phase 1B.

Nothing runs on import.  The operator must supply ``--execute-real-codex`` plus
an absolute attested binary, manually authenticated private ``CODEX_HOME``, an
exact source commit, and a dedicated empty proof root.  The script performs one
bounded write job and one deliberate process-death/restart reconciliation.
It never commits, pushes, opens a PR, merges, deploys, or touches portfolio
state.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import signal
import stat
import sys
from pathlib import Path
from typing import Any

from control_plane.codex_worker import CodexWorkerAdapter
from control_plane.executive_runtime import JobPayload, Runtime
from control_plane.executive_supervisor import ExecutiveSupervisor
from control_plane.executive_workspace import prepare_credentialless_clone


_OPENAI_TEAM_IDENTIFIER = "2DC432GLL2"
_ARTIFACT_PATH = "research/executive_os_phase1b_worker_proof/receipt.md"


def _progress(message: str) -> None:
    print(f"[phase1b-proof] {message}", file=sys.stderr, flush=True)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the destructive-by-design Phase 1B kill proof.")
    parser.add_argument("--execute-real-codex", action="store_true", required=True)
    parser.add_argument("--proof-root", required=True, type=Path)
    parser.add_argument("--source-repository", required=True, type=Path)
    parser.add_argument("--base-sha", required=True)
    parser.add_argument("--codex-binary", required=True, type=Path)
    parser.add_argument("--codex-home", required=True, type=Path)
    parser.add_argument("--allowed-version", required=True)
    parser.add_argument("--model", default="gpt-5.6-sol")
    parser.add_argument("--effort", default="xhigh")
    return parser


def _prepare_root(path: Path) -> Path:
    if not path.is_absolute():
        raise ValueError("proof root must be absolute")
    if path.exists():
        if not path.is_dir() or any(path.iterdir()):
            raise ValueError("proof root must be absent or an empty directory")
    else:
        path.mkdir(parents=True, mode=0o700)
    path.chmod(0o700)
    return path.resolve(strict=True)


def _write_private_json(path: Path, value: Any) -> None:
    payload = (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode()
    descriptor = os.open(
        path,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0),
        0o600,
    )
    try:
        view = memoryview(payload)
        while view:
            view = view[os.write(descriptor, view) :]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    directory = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _validation_argv() -> list[str]:
    program = (
        "from pathlib import Path; "
        f"p=Path({_ARTIFACT_PATH!r}); "
        "t=p.read_text(encoding='utf-8'); "
        "assert t.startswith('# Phase 1B Worker Proof'); "
        "assert 'Job:' in t and 'Run:' in t and 'Base SHA:' in t"
    )
    return ["/usr/bin/python3", "-c", program]


def _register_worker(runtime: Runtime, *, model: str, effort: str) -> None:
    runtime.workers.register_worker(
        "codex-01",
        provider="codex",
        account_label="manual-local-auth",
        worker_type="codex-cli",
        capabilities=["research", "code", "tests"],
        quota_classes={
            "codex-native": {
                "capabilities": ["research", "code", "tests"],
                "model": model,
                "effort": effort,
                "cost_class": "proof",
            }
        },
        metadata={"phase": "1B", "provider_quota_measurement": "not-implemented"},
    )


async def _run(args: argparse.Namespace) -> dict[str, Any]:
    proof_root = _prepare_root(args.proof_root)
    _progress(f"proof root ready: {proof_root}")
    source = args.source_repository.resolve(strict=True)
    workspaces = proof_root / "workspaces"
    success_workspace = prepare_credentialless_clone(
        source,
        workspaces,
        job_id="success",
        base_sha=args.base_sha,
        branch="codex/phase1b-real-proof",
    )
    kill_workspace = prepare_credentialless_clone(
        source,
        workspaces,
        job_id="kill",
        base_sha=args.base_sha,
        branch="codex/phase1b-kill-proof",
    )
    _progress(f"two exact-SHA, no-remote workspaces prepared at {success_workspace.base_sha}")
    artifact_parent = Path(success_workspace.workspace_path) / Path(_ARTIFACT_PATH).parent
    artifact_parent.mkdir(parents=True, exist_ok=True)

    runtime = Runtime.at(proof_root, lease_seconds=60)
    _register_worker(runtime, model=args.model, effort=args.effort)
    validation = _validation_argv()
    success_job = runtime.jobs.create_job(
        (
            "Create exactly research/executive_os_phase1b_worker_proof/receipt.md. "
            "Use heading '# Phase 1B Worker Proof'. Include the Job and Run identifiers from "
            "the packet, the exact Base SHA, and state that this was a harmless isolated "
            "credential-free-clone proof. Do not run or self-attest the declared validation "
            "command; return validations=[] exactly. The supervisor will execute its exact "
            "argv directly after your process exits."
        ),
        department="control-plane-proof",
        worktree=success_workspace.workspace_path,
        branch=success_workspace.branch,
        requested_authorities=["READ", "RESEARCH", "WRITE_BRANCH", "RUN_TESTS"],
        allowed_write_paths=[_ARTIFACT_PATH],
        validation_commands=[validation],
        constraints={
            "provider": "codex",
            "model": args.model,
            "effort": args.effort,
            "cost_class": "proof",
            "base_sha": success_workspace.base_sha,
            "eligible_quota_classes": ["codex-native"],
            "required_capabilities": ["research", "code", "tests"],
        },
        attempt_limit=2,
    )

    adapter = CodexWorkerAdapter(
        args.codex_binary,
        codex_home=args.codex_home,
        allowed_versions=frozenset({args.allowed_version}),
        required_team_identifier=_OPENAI_TEAM_IDENTIFIER,
    )
    supervisor = ExecutiveSupervisor(
        runtime,
        adapter,
        runs_root=proof_root / "runs",
        instance_id="phase1b-proof-success",
    )
    success = await supervisor.run_once(success_job.job_id)
    if success.job.status.value != "COMPLETED":
        raise RuntimeError(f"real proof did not complete: {success.job.to_dict()}")
    artifact = Path(success_workspace.workspace_path) / _ARTIFACT_PATH
    if not artifact.is_file():
        raise RuntimeError("real proof artifact is missing")
    _progress(
        f"authenticated run completed: {success_job.job_id}/{success.attempt.attempt_id}"
    )

    reopened_after_success = Runtime.at(proof_root)
    reopened_job = reopened_after_success.jobs.get_job(success_job.job_id)
    reopened_attempt = reopened_after_success.attempts.get_attempt(success.attempt.attempt_id)
    reopened_quota = reopened_after_success.workers.get_quota_class(
        "codex-01", "codex-native"
    )
    if reopened_job is None or reopened_job.status.value != "COMPLETED":
        raise RuntimeError("completed job did not survive Runtime reconstruction")
    if reopened_attempt is None or reopened_attempt.status.value != "COMPLETED":
        raise RuntimeError("completed attempt did not survive Runtime reconstruction")
    if (
        reopened_quota is None
        or reopened_quota.status.value != "AVAILABLE"
        or reopened_quota.active_attempt_id is not None
    ):
        raise RuntimeError("successful attempt did not release its quota class")
    _progress("completed state reconstructed from a fresh Runtime instance")

    kill_job = reopened_after_success.jobs.create_job(
        (
            "Restart-loss proof only: do not run or self-attest the declared long validation "
            "argv, return validations=[] exactly, and do not write any file. The supervisor "
            "owns direct validation after process exit."
        ),
        department="control-plane-proof",
        worktree=kill_workspace.workspace_path,
        branch=kill_workspace.branch,
        requested_authorities=["READ", "RESEARCH", "RUN_TESTS"],
        validation_commands=[
            ["/usr/bin/python3", "-c", "import time; time.sleep(120)"]
        ],
        constraints={
            "provider": "codex",
            "model": args.model,
            "effort": args.effort,
            "cost_class": "proof",
            "base_sha": kill_workspace.base_sha,
            "eligible_quota_classes": ["codex-native"],
            "required_capabilities": ["research", "tests"],
        },
        attempt_limit=2,
    )
    killer = ExecutiveSupervisor(
        reopened_after_success,
        adapter,
        runs_root=proof_root / "runs",
        instance_id="phase1b-proof-before-restart",
    )
    active = await killer.start_job(kill_job.job_id)
    reopened_after_success.attempts.checkpoint_attempt(
        active.lease.attempt.attempt_id,
        fence_generation=active.lease.attempt.fence_generation,
        lease_token=active.lease.lease_token,
        payload=JobPayload(
            summary="Attested Codex process launched; deliberate kill pending",
            current_state="pre-kill checkpoint",
            next_actions=["restart supervisor and reconcile"],
        ),
    )
    _progress(
        "second attested Codex process was leased, launched, identity-recorded, and checkpointed: "
        f"pid={active.process_ref.pid}"
    )
    identity, pgid = adapter.inspector.identity(active.process_ref.pid)
    if identity != active.process_ref.process_start_identity or pgid != active.process_ref.pgid:
        raise RuntimeError("process identity changed before deliberate kill")
    os.killpg(active.process_ref.pgid, signal.SIGKILL)
    killed_collection = await adapter.collect_result(active.process_ref)
    if killed_collection.result.exit_code is None or killed_collection.result.exit_code >= 0:
        raise RuntimeError("kill proof did not observe signal termination")
    _progress(
        f"deliberate process-group kill observed: exit={killed_collection.result.exit_code}"
    )

    restarted_runtime = Runtime.at(proof_root, lease_seconds=60)
    restarted_adapter = CodexWorkerAdapter(
        args.codex_binary,
        codex_home=args.codex_home,
        allowed_versions=frozenset({args.allowed_version}),
        required_team_identifier=_OPENAI_TEAM_IDENTIFIER,
    )
    restarted = ExecutiveSupervisor(
        restarted_runtime,
        restarted_adapter,
        runs_root=proof_root / "runs",
        instance_id="phase1b-proof-after-restart",
    )
    reconciliation = restarted.reconcile_restart(requeue_lost=True)
    kill_attempt = restarted_runtime.attempts.get_attempt(active.lease.attempt.attempt_id)
    requeued_job = restarted_runtime.jobs.get_job(kill_job.job_id)
    if kill_attempt is None or kill_attempt.status.value != "LOST":
        raise RuntimeError("dead Codex attempt was not reconciled LOST")
    if requeued_job is None or requeued_job.status.value != "QUEUED":
        raise RuntimeError("LOST job was not requeued")
    if not requeued_job.checkpoint or requeued_job.checkpoint.get("current_state") != "pre-kill checkpoint":
        raise RuntimeError("pre-kill checkpoint was not preserved")
    _progress("fresh supervisor reconciled LOST, preserved checkpoint, and requeued job")

    database = restarted_runtime.store.path
    report = {
        "schema_version": "mastermind.executive_os_phase1b_proof/v1",
        "proof_root": str(proof_root),
        "base_sha": success_workspace.base_sha,
        "success_workspace": success_workspace.to_dict(),
        "kill_workspace": kill_workspace.to_dict(),
        "success": success.to_dict(),
        "reopened_success": {
            "job": reopened_job.to_dict(),
            "attempt": reopened_attempt.to_dict(),
            "quota_class": reopened_quota.to_dict(),
        },
        "artifact": {
            "path": str(artifact),
            "sha256": _sha256(artifact),
            "size": artifact.stat().st_size,
        },
        "kill": {
            "process_ref": {
                "pid": active.process_ref.pid,
                "pgid": active.process_ref.pgid,
                "process_start_identity": active.process_ref.process_start_identity,
                "boot_session_id": active.process_ref.boot_session_id,
            },
            "collection_status": killed_collection.result.status.value,
            "exit_code": killed_collection.result.exit_code,
            "provider_session_id": killed_collection.result.provider_session_id,
            "thread_started_observed": '"thread.started"' in Path(
                active.process_ref.stdout_path
            ).read_text(encoding="utf-8", errors="replace"),
            "stdout_sha256": killed_collection.stdout_sha256,
            "stderr_sha256": killed_collection.stderr_sha256,
            "result_sha256": killed_collection.result_sha256,
            "checkpoint": requeued_job.checkpoint,
            "attempt": kill_attempt.to_dict(),
            "job": requeued_job.to_dict(),
            "reconciliation": [item.to_dict() for item in reconciliation],
        },
        "database": {
            "path": str(database),
            "sha256": _sha256(database),
            "mode": oct(stat.S_IMODE(database.stat().st_mode)),
        },
        "event_count": len(restarted_runtime.events.list_events()),
    }
    report_path = proof_root / "phase1b-proof-report.json"
    _write_private_json(report_path, report)
    _progress(f"proof report persisted: {report_path}")
    return {"report_path": str(report_path), **report}


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.execute_real_codex is not True:  # pragma: no cover - argparse requires the flag
        raise SystemExit("--execute-real-codex is required")
    print(json.dumps(asyncio.run(_run(args)), indent=2, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
