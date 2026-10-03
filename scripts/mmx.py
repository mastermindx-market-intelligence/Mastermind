#!/usr/bin/env python3
"""Thin local shell for the canonical Mastermind Executive control service.

This command is a client only. It owns no lifecycle, queue, scheduler, retry,
placement, credential, or provider state. All requests go through the existing
Executive AF_UNIX control socket and retain the service's authority/effect law.

The first release deliberately supports local control-socket transport only.
Remote fleet access must compose an accepted authenticated transport; this CLI
must never turn SSH, TCP, or an arbitrary URL into a second Executive ingress.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any, Sequence

_ROOT = Path(__file__).resolve().parents[1]
if os.fspath(_ROOT) not in sys.path:
    sys.path.insert(0, os.fspath(_ROOT))

from control_plane.executive_service import ServiceError, send_control_request  # noqa: E402

DEFAULT_CONTROL_SOCKET = Path("/var/run/mastermind-executive/control.sock")


class MmxCliError(RuntimeError):
    """Closed client-side refusal with no Executive side effect."""


def _absolute_path(value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        raise argparse.ArgumentTypeError("path must be absolute")
    return path


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mmx",
        description="Thin client for existing Mastermind control surfaces.",
    )
    root = parser.add_subparsers(dest="surface", required=True)

    executive = root.add_parser(
        "executive",
        help="Use the canonical local Executive OS control socket.",
    )
    executive.add_argument(
        "--socket",
        type=_absolute_path,
        default=DEFAULT_CONTROL_SOCKET,
        help=f"Executive AF_UNIX socket (default: {DEFAULT_CONTROL_SOCKET}).",
    )
    executive.add_argument(
        "--json",
        action="store_true",
        help="Print the exact Executive result envelope as JSON.",
    )
    sub = executive.add_subparsers(dest="command", required=True)

    sub.add_parser("state", help="Read Executive service/runtime status.")
    sub.add_parser("workers", help="Read current Executive worker registry.")
    sub.add_parser("jobs", help="Read current Executive jobs.")

    job = sub.add_parser("job", help="Read one Executive Job.")
    job.add_argument("job_id")

    intent = sub.add_parser("intent", help="Read one previously submitted CEO intent.")
    intent.add_argument("intent_id")

    submit = sub.add_parser(
        "submit",
        help="Submit one existing mastermind.ceo_intent.v1 JSON document. Admission is not execution.",
    )
    submit.add_argument("intent_file", type=Path)
    return parser


def _load_json_object(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise MmxCliError(f"intent file is unreadable: {exc}") from exc
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise MmxCliError(f"intent file is not valid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise MmxCliError("intent file must contain one JSON object")
    return value


def _request(args: argparse.Namespace) -> tuple[str, dict[str, Any]]:
    if args.surface != "executive":
        raise MmxCliError("unsupported surface")
    if args.command == "state":
        return "status", {}
    if args.command == "workers":
        return "workers", {}
    if args.command == "jobs":
        return "jobs", {}
    if args.command == "job":
        return "job", {"job_id": args.job_id}
    if args.command == "intent":
        return "ceo-intent-status", {"intent_id": args.intent_id}
    if args.command == "submit":
        return "submit-ceo-intent", {"intent": _load_json_object(args.intent_file)}
    raise MmxCliError("unsupported Executive command")


def _render(command: str, result: Any) -> str:
    if command == "submit-ceo-intent" and isinstance(result, dict):
        return (
            f"intent      {result.get('intent_id')}\n"
            f"job         {result.get('job_id')}  [{result.get('status')}]\n"
            f"accepted    {result.get('accepted')}\n"
            f"dispatched  {result.get('dispatched')}  (submission is not execution)\n"
        )
    return json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


async def _run(args: argparse.Namespace) -> int:
    command, values = _request(args)
    response = await send_control_request(args.socket, command, values)
    if response.get("ok") is not True:
        error = response.get("error")
        if isinstance(error, dict):
            code = error.get("code", "unknown")
            message = error.get("message", "")
        else:
            code, message = "unknown", ""
        print(f"refused: [{code}] {message}", file=sys.stderr)
        return 2
    result = response.get("result")
    if args.json:
        print(json.dumps(response, indent=2, sort_keys=True, ensure_ascii=False))
    else:
        sys.stdout.write(_render(command, result))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(list(argv) if argv is not None else None)
    try:
        return asyncio.run(_run(args))
    except (MmxCliError, ServiceError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
