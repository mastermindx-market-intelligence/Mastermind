"""Submit and read back one bounded CEO intent over the private control socket.

The CEO-facing entrypoint for the Phase 1E-A write bridge
(:mod:`control_plane.ceo_intent`).  It sends ONE ``submit-ceo-intent`` request
over the existing AF_UNIX Executive control service and prints the receipt.

This client NEVER opens the SQLite database directly, NEVER executes a job, and
has no TCP/HTTP transport: the service is the only way in, and acceptance is not
execution — a submitted intent becomes a QUEUED Job and stops there.

Unlike ``scripts/ceo_boot_packet.py``, which fails OPEN because an orientation
gap must still hand the CEO a packet, this command is a MUTATING client and
fails CLOSED: a refused intent is a non-zero exit with the service's error code.

    python3 scripts/ceo_intent.py submit intent.json --socket /var/run/.../control.sock
    python3 scripts/ceo_intent.py submit intent.json --config /etc/.../control.json --json
    python3 scripts/ceo_intent.py status CEO-2026-08-13-A --socket /var/run/.../control.sock
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import stat
import sys
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[1]
if os.fspath(_ROOT) not in sys.path:
    sys.path.insert(0, os.fspath(_ROOT))

from control_plane.executive_service import (  # noqa: E402  (after sys.path bootstrap)
    ServiceError,
    send_control_request,
)

#: Job ids are minted by the runtime as ``JOB-%03d``; anything else given to
#: ``status`` is treated as an intent id.
_JOB_ID_RE = re.compile(r"^JOB-\d+$")

#: The reviewed control config key that names the live socket.
_CONFIG_SOCKET_KEY = "control_socket_path"


def _absolute_path(value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        raise argparse.ArgumentTypeError("path must be absolute")
    return path


def _add_shared(parser: argparse.ArgumentParser, *, subcommand: bool) -> None:
    """Accept the shared flags on either side of the subcommand.

    ``argparse.SUPPRESS`` on the subcommand copies is load-bearing: without it an
    unspecified ``--socket`` after the subcommand would write ``None`` over the
    value already parsed before it.
    """

    flag_default = argparse.SUPPRESS if subcommand else None
    parser.add_argument(
        "--socket",
        type=_absolute_path,
        default=flag_default,
        help="Absolute AF_UNIX control socket (same override the Phase 1C client takes).",
    )
    parser.add_argument(
        "--config",
        type=_absolute_path,
        default=flag_default,
        help=f"Reviewed control config to read {_CONFIG_SOCKET_KEY} from.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        default=argparse.SUPPRESS if subcommand else False,
        help="print the raw receipt JSON",
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Submit one typed CEO intent to the private Executive control service. "
            "Submission creates a QUEUED Job; it never executes anything."
        ),
    )
    _add_shared(parser, subcommand=False)
    sub = parser.add_subparsers(dest="command", required=True)

    submit = sub.add_parser("submit", help="Submit one mastermind.ceo_intent.v1 file.")
    submit.add_argument("intent_file", type=Path)
    _add_shared(submit, subcommand=True)

    status = sub.add_parser("status", help="Read back one intent_id or JOB-nnn.")
    status.add_argument("identifier")
    _add_shared(status, subcommand=True)
    return parser


def _socket_path(args: argparse.Namespace) -> Path:
    """Resolve the socket the same way the reviewed host composes it."""

    if args.socket is not None:
        return args.socket
    if args.config is None:
        raise ServiceError("client commands require --socket or --config")
    path = args.config
    try:
        info = path.lstat()
    except OSError as exc:
        raise ServiceError(f"control config is unavailable: {exc}") from exc
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise ServiceError("control config must be a regular file")
    if stat.S_IMODE(info.st_mode) & 0o022:
        raise ServiceError("control config is writable by group or other")
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ServiceError(f"control config is not valid UTF-8 JSON: {exc}") from exc
    value = config.get(_CONFIG_SOCKET_KEY) if isinstance(config, dict) else None
    if not isinstance(value, str) or not Path(value).is_absolute():
        raise ServiceError(f"control config {_CONFIG_SOCKET_KEY} must be an absolute path")
    return Path(value)


def _load_intent(path: Path) -> Any:
    try:
        raw = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise ServiceError(f"intent file is unreadable: {exc}") from exc
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ServiceError(f"intent file is not valid JSON: {exc}") from exc


def _render(receipt: dict[str, Any]) -> str:
    authority = receipt.get("authority") or {}
    grounding = receipt.get("grounding") or {}
    lines = [
        f"intent      {receipt.get('intent_id')}",
        f"job         {receipt.get('job_id')}  [{receipt.get('status')}]",
        f"accepted    {receipt.get('accepted')}"
        + ("  (duplicate — reconciled, no second job)" if receipt.get("duplicate") else ""),
        f"dispatched  {receipt.get('dispatched')}  (submission is never execution)",
        f"authority   {', '.join(authority.get('requested') or []) or '-'}"
        f"  level={authority.get('authority_level')}",
        f"policy      {authority.get('policy_sha256')}",
        f"grounding   mastermind={grounding.get('mastermind_sha')}",
        f"            macro={grounding.get('macro_sha')}",
        f"fingerprint {receipt.get('fingerprint')}",
    ]
    return "\n".join(lines) + "\n"


async def _run(args: argparse.Namespace) -> int:
    socket_path = _socket_path(args)
    if args.command == "submit":
        command, values = "submit-ceo-intent", {"intent": _load_intent(args.intent_file)}
    elif _JOB_ID_RE.fullmatch(args.identifier):
        command, values = "job", {"job_id": args.identifier}
    else:
        command, values = "ceo-intent-status", {"intent_id": args.identifier}

    response = await send_control_request(socket_path, command, values)
    if response.get("ok") is not True:
        error = response.get("error") or {}
        print(
            f"refused: [{error.get('code', 'unknown')}] {error.get('message', '')}",
            file=sys.stderr,
        )
        # Mutating client: a refusal is a failure, never a degraded success.
        return 2
    result = response.get("result")
    if args.json or command == "job" or not isinstance(result, dict):
        print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False))
    else:
        sys.stdout.write(_render(result))
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        return asyncio.run(_run(args))
    except (OSError, ServiceError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
