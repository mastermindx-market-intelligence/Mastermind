#!/usr/bin/env python3
"""Read-only account-local audit for temporary Sol watcher task exports."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Mapping, Sequence

from control_plane.sol_watcher_contract import audit_tasks


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validate an account-local JSON export of temporary Sol watcher tasks. "
            "This command never connects to or mutates a task store."
        )
    )
    parser.add_argument(
        "input",
        nargs="?",
        default="-",
        help="JSON file path, or '-' to read stdin",
    )
    return parser


def _read_text(source: str) -> str:
    if source == "-":
        return sys.stdin.read()
    return Path(source).read_text(encoding="utf-8")


def _tasks_from_payload(payload: Any) -> list[Mapping[str, Any]]:
    if isinstance(payload, dict):
        payload = payload.get("tasks")
    if not isinstance(payload, list):
        raise ValueError("input must be a JSON list or an object containing a tasks list")
    if not all(isinstance(item, dict) for item in payload):
        raise ValueError("every task must be a JSON object")
    return payload


def _print_error(message: str) -> None:
    print(
        json.dumps(
            {
                "schema": "mastermind.sol_watcher_audit_error.v1",
                "error": "INVALID_INPUT",
                "message": message,
            },
            sort_keys=True,
        ),
        file=sys.stderr,
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        payload = json.loads(_read_text(args.input))
        tasks = _tasks_from_payload(payload)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        _print_error(str(exc))
        return 2

    report = audit_tasks(tasks)
    print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
    return 0 if report.valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
