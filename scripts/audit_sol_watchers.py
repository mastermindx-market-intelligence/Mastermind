#!/usr/bin/env python3
"""Read-only account-local audit for temporary Sol watcher task exports."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Sequence

from control_plane.sol_watcher_contract import (
    MAX_EXPORT_TASKS,
    MAX_TASK_ID_BYTES,
    MAX_TASK_PROMPT_BYTES,
    MAX_TASK_TITLE_BYTES,
    TaskExportLimitError,
    audit_tasks,
)


MAX_INPUT_BYTES = 1_048_576


class _InputError(ValueError):
    """A fixed, non-echoing error for hostile local export input."""


class _DuplicateJsonKeyError(_InputError):
    pass


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
    try:
        if source == "-":
            stream = getattr(sys.stdin, "buffer", None)
            raw = (
                stream.read(MAX_INPUT_BYTES + 1)
                if stream is not None
                else sys.stdin.read(MAX_INPUT_BYTES + 1).encode("utf-8")
            )
        else:
            with Path(source).open("rb") as handle:
                raw = handle.read(MAX_INPUT_BYTES + 1)
    except (OSError, UnicodeError) as exc:
        raise _InputError("input cannot be read") from exc
    if len(raw) > MAX_INPUT_BYTES:
        raise _InputError("input exceeds maximum allowed size")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise _InputError("input is not valid UTF-8") from exc


def _reject_duplicate_json_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateJsonKeyError("duplicate JSON object keys are not allowed")
        result[key] = value
    return result


def _tasks_from_payload(payload: Any) -> list[Any]:
    if isinstance(payload, dict):
        payload = payload.get("tasks")
    if not isinstance(payload, list):
        raise _InputError("input must be a JSON list or an object containing a tasks list")
    if len(payload) > MAX_EXPORT_TASKS:
        raise _InputError("task count exceeds maximum allowed size")
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
        payload = json.loads(
            _read_text(args.input), object_pairs_hook=_reject_duplicate_json_keys
        )
        tasks = _tasks_from_payload(payload)
        report = audit_tasks(tasks)
    except _InputError as exc:
        _print_error(str(exc))
        return 2
    except TaskExportLimitError:
        _print_error("task count exceeds maximum allowed size")
        return 2
    except (json.JSONDecodeError, RecursionError, ValueError, UnicodeError, OSError):
        _print_error("input is invalid")
        return 2

    print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
    return 0 if report.valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
