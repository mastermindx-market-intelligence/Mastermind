"""Compatibility operator CLI for the durable Executive OS runtime.

Run from the repository root with ``python -m scripts.executive_os_phase1a``.
No command in this module launches an AI provider or touches portfolio state.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from control_plane.worker_runtime import (
    JobPayload,
    Runtime,
    RuntimeProofError,
    WorkerStatus,
)


def _print(value: Any) -> None:
    if hasattr(value, "to_dict"):
        value = value.to_dict()
    elif isinstance(value, list):
        value = [item.to_dict() if hasattr(item, "to_dict") else item for item in value]
    print(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False))


def _add_payload_arguments(parser: argparse.ArgumentParser, *, error_required: bool = False) -> None:
    parser.add_argument("--summary", required=not error_required)
    parser.add_argument("--completed-step", action="append", default=[])
    parser.add_argument("--current-state", default="")
    parser.add_argument("--artifact", action="append", default=[])
    parser.add_argument("--next-action", action="append", default=[])
    parser.add_argument("--error", action="append", default=[], required=error_required)


def _payload(args: argparse.Namespace) -> JobPayload:
    return JobPayload(
        summary=args.summary or "Job failed",
        completed_steps=args.completed_step,
        current_state=args.current_state,
        artifacts=args.artifact,
        next_actions=args.next_action,
        errors=args.error,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Operate the Mastermind Executive OS compatibility state machine "
            "backed by durable SQLite."
        )
    )
    parser.add_argument(
        "--root",
        type=Path,
        help=(
            "Repository/state root override; the durable database is "
            "data/control_plane/executive.sqlite3 beneath it."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    register = sub.add_parser("register-worker")
    register.add_argument("worker_id")
    register.add_argument("--provider", required=True)
    register.add_argument("--account-label", required=True)
    register.add_argument("--worker-type", default="mock")
    register.add_argument("--capability", action="append", default=[])
    register.add_argument(
        "--quota-class",
        action="append",
        default=[],
        help="Independent capacity class; repeat as needed (default: default).",
    )

    create = sub.add_parser("create-job")
    create.add_argument("objective")
    create.add_argument("--department", default="general")
    create.add_argument("--priority", type=int, default=0)
    create.add_argument("--authority-level", default="A0")
    create.add_argument("--branch")
    create.add_argument("--worktree")
    create.add_argument("--provider")
    create.add_argument("--capability", action="append", default=[])
    create.add_argument(
        "--quota-class",
        action="append",
        default=[],
        help="Eligible quota/capability class; repeat to allow failover classes.",
    )

    sub.add_parser("workers")
    sub.add_parser("jobs")

    dispatch = sub.add_parser("dispatch")
    dispatch.add_argument("job_id")

    checkpoint = sub.add_parser("checkpoint")
    checkpoint.add_argument("job_id")
    _add_payload_arguments(checkpoint)

    status = sub.add_parser("worker-status")
    status.add_argument("worker_id")
    status.add_argument(
        "status",
        choices=[item.value for item in WorkerStatus if item != WorkerStatus.BUSY],
    )
    status.add_argument(
        "--quota-class",
        help="Change one independent capacity class instead of the whole worker identity.",
    )

    requeue = sub.add_parser("requeue")
    requeue.add_argument("job_id")

    complete = sub.add_parser("complete")
    complete.add_argument("job_id")
    _add_payload_arguments(complete)

    fail = sub.add_parser("fail")
    fail.add_argument("job_id")
    _add_payload_arguments(fail, error_required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    runtime = Runtime.at(args.root)
    try:
        if args.command == "register-worker":
            _print(
                runtime.workers.register_worker(
                    args.worker_id,
                    provider=args.provider,
                    account_label=args.account_label,
                    worker_type=args.worker_type,
                    capabilities=args.capability,
                    quota_classes=args.quota_class or None,
                )
            )
        elif args.command == "create-job":
            constraints = {
                "provider": args.provider,
                "required_capabilities": args.capability,
                "eligible_quota_classes": args.quota_class,
            }
            _print(
                runtime.jobs.create_job(
                    args.objective,
                    department=args.department,
                    priority=args.priority,
                    authority_level=args.authority_level,
                    branch=args.branch,
                    worktree=args.worktree,
                    constraints=constraints,
                )
            )
        elif args.command == "workers":
            _print(runtime.workers.list_workers())
        elif args.command == "jobs":
            _print(runtime.jobs.list_jobs())
        elif args.command == "dispatch":
            worker = runtime.broker.dispatch(args.job_id)
            if worker is None:
                _print({"assigned_worker_id": None, "job_id": args.job_id, "status": "NO_WORKER"})
                return 3
            _print(
                {
                    "assigned_worker_id": worker.worker_id,
                    "assigned_quota_class": runtime.jobs.get_job(
                        args.job_id
                    ).assigned_quota_class,  # type: ignore[union-attr]
                    "job": runtime.jobs.get_job(args.job_id).to_dict(),  # type: ignore[union-attr]
                }
            )
        elif args.command == "checkpoint":
            _print(runtime.jobs.checkpoint_job(args.job_id, _payload(args)))
        elif args.command == "worker-status":
            _print(
                runtime.workers.set_worker_status(
                    args.worker_id,
                    args.status,
                    quota_class=args.quota_class,
                )
            )
        elif args.command == "requeue":
            _print(runtime.jobs.requeue_job(args.job_id))
        elif args.command == "complete":
            _print(runtime.jobs.complete_job(args.job_id, _payload(args)))
        elif args.command == "fail":
            _print(runtime.jobs.fail_job(args.job_id, _payload(args)))
        else:  # pragma: no cover - argparse guarantees a known command
            raise AssertionError(args.command)
        return 0
    except RuntimeProofError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
