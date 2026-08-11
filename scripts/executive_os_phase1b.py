"""Operator CLI for the durable Executive OS Phase 1B runtime.

Run from the repository root with ``python -m scripts.executive_os_phase1b``.
Inspection and state-seeding commands are claim-neutral.  The explicit
``run-once`` command is the only path here that launches the attested provider;
importing this module has no side effects.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from control_plane.executive_runtime import Runtime, RuntimeProofError


def _json_value(value: Any) -> Any:
    if hasattr(value, "to_dict"):
        return _json_value(value.to_dict())
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


def _print(value: Any) -> None:
    print(json.dumps(_json_value(value), indent=2, sort_keys=True, ensure_ascii=False))


def _command_argv(value: str) -> list[str]:
    try:
        command = json.loads(value)
    except json.JSONDecodeError as exc:
        raise argparse.ArgumentTypeError(
            f"validation command must be a JSON argv array: {exc.msg}"
        ) from exc
    if (
        not isinstance(command, list)
        or not command
        or any(not isinstance(item, str) or not item for item in command)
    ):
        raise argparse.ArgumentTypeError(
            "validation command must be a non-empty JSON array of non-empty strings"
        )
    return command


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Inspect or seed the durable Mastermind Executive OS Phase 1B SQLite "
            "runtime; provider execution requires the explicit run-once command."
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

    register = sub.add_parser(
        "register-worker", help="Register durable worker capacity without claiming work."
    )
    register.add_argument("worker_id")
    register.add_argument("--provider", required=True)
    register.add_argument("--account-label", required=True)
    register.add_argument("--worker-type", default="codex")
    register.add_argument("--capability", action="append", default=[])
    register.add_argument(
        "--quota-class",
        action="append",
        default=[],
        help="Independent capacity class; repeat as needed (default: default).",
    )
    register.add_argument("--model")
    register.add_argument("--reasoning-effort")
    register.add_argument("--cost-class")

    create = sub.add_parser(
        "create-job", help="Create an authority-checked queued job without claiming it."
    )
    create.add_argument("objective")
    create.add_argument("--department", default="general")
    create.add_argument("--priority", type=int, default=0)
    create.add_argument("--authority-level", default="A0")
    create.add_argument("--branch")
    create.add_argument("--worktree")
    create.add_argument("--provider")
    create.add_argument("--model")
    create.add_argument("--reasoning-effort")
    create.add_argument("--cost-class")
    create.add_argument("--base-sha")
    create.add_argument("--capability", action="append", default=[])
    create.add_argument(
        "--quota-class",
        action="append",
        default=[],
        help="Eligible quota class; repeat to permit failover (default: default).",
    )
    create.add_argument(
        "--authority",
        action="append",
        default=[],
        help="Requested authority; repeat as needed (default: READ).",
    )
    create.add_argument(
        "--allowed-write-path",
        action="append",
        default=[],
        help="Worktree-relative write allowlist entry; repeat as needed.",
    )
    create.add_argument(
        "--validation-command",
        action="append",
        default=[],
        type=_command_argv,
        metavar="JSON_ARGV",
        help=(
            "Declared argv-only validation command as a JSON string array; "
            "repeat for multiple commands."
        ),
    )
    create.add_argument("--attempt-limit", type=int, default=10)

    sub.add_parser("workers", help="List durable worker identities and quota classes.")
    sub.add_parser("jobs", help="List durable jobs.")

    attempts = sub.add_parser("attempts", help="List durable attempts.")
    attempts.add_argument("--job-id")

    events = sub.add_parser("events", help="List the append-only durable event log.")
    events.add_argument("--job-id")
    events.add_argument("--attempt-id")

    for name, help_text in (
        ("run-once", "Explicitly claim and execute one queued job."),
        ("reconcile", "Inspect durable attempts after supervisor restart."),
    ):
        command = sub.add_parser(name, help=help_text)
        command.add_argument(
            "--codex-binary", required=True, type=Path, help="Absolute native Codex binary."
        )
        command.add_argument(
            "--codex-home", required=True, type=Path, help="Private manually authenticated CODEX_HOME."
        )
        command.add_argument(
            "--allowed-version",
            action="append",
            required=True,
            help="Exact allowed normalized Codex version; repeat only for a reviewed migration window.",
        )
    run_once = sub.choices["run-once"]
    run_once.add_argument("job_id")
    reconcile = sub.choices["reconcile"]
    reconcile.add_argument("--no-requeue", action="store_true")
    return parser


def _supervisor(args: argparse.Namespace, runtime: Runtime):
    from control_plane.codex_worker import CodexWorkerAdapter
    from control_plane.executive_supervisor import ExecutiveSupervisor

    adapter = CodexWorkerAdapter(
        args.codex_binary,
        allowed_versions=frozenset(args.allowed_version),
    )
    return ExecutiveSupervisor(runtime, adapter, codex_home=args.codex_home)


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        runtime = Runtime.at(args.root)
        if args.command == "register-worker":
            quota_names = args.quota_class or ["default"]
            quota_classes = {
                name: {
                    "provider": args.provider,
                    "model": args.model,
                    "effort": args.reasoning_effort,
                    "cost_class": args.cost_class,
                    "capabilities": args.capability,
                }
                for name in quota_names
            }
            _print(
                runtime.workers.register_worker(
                    args.worker_id,
                    provider=args.provider,
                    account_label=args.account_label,
                    worker_type=args.worker_type,
                    capabilities=args.capability,
                    quota_classes=quota_classes,
                )
            )
        elif args.command == "create-job":
            constraints = {
                "provider": args.provider,
                "model": args.model,
                "effort": args.reasoning_effort,
                "cost_class": args.cost_class,
                "base_sha": args.base_sha,
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
                    attempt_limit=args.attempt_limit,
                    requested_authorities=args.authority or None,
                    allowed_write_paths=args.allowed_write_path,
                    validation_commands=args.validation_command,
                )
            )
        elif args.command == "workers":
            _print(runtime.workers.list_workers())
        elif args.command == "jobs":
            _print(runtime.jobs.list_jobs())
        elif args.command == "attempts":
            _print(runtime.attempts.list_attempts(job_id=args.job_id))
        elif args.command == "events":
            _print(
                runtime.events.list_events(
                    job_id=args.job_id,
                    attempt_id=args.attempt_id,
                )
            )
        elif args.command == "run-once":
            _print(asyncio.run(_supervisor(args, runtime).run_once(args.job_id)))
        elif args.command == "reconcile":
            _print(
                _supervisor(args, runtime).reconcile_restart(
                    requeue_lost=not args.no_requeue
                )
            )
        else:  # pragma: no cover - argparse guarantees a known command
            raise AssertionError(args.command)
        return 0
    except RuntimeProofError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
