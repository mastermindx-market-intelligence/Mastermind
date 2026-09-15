"""Submit exactly one strict-v2 CEO intent through the dedicated ingress."""
from __future__ import annotations

import argparse
import asyncio
import json
import stat
from pathlib import Path
from typing import Any

from control_plane import executive_ceo_ingress


_PRODUCTION_CONTROL_SOCKET = Path("/var/run/mastermind-executive/control.sock")


def _absolute_path(value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        raise argparse.ArgumentTypeError("path must be absolute")
    return path


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Submit one strict-v2 CEO intent to CeoIngress.")
    parser.add_argument("--socket", type=_absolute_path)
    parser.add_argument("--config", type=_absolute_path)
    parser.add_argument("--request-ref", required=True)
    parser.add_argument("--objective", required=True)
    parser.add_argument("--workstream", required=True)
    parser.add_argument("--mastermind-sha", default="")
    parser.add_argument("--macro-sha", default="")
    parser.add_argument("--boot-packet-schema", default=executive_ceo_ingress.BOOT_PACKET_SCHEMA)
    parser.add_argument("--dry-run", action="store_true")
    return parser


def build_frame(request_ref: str, request: dict[str, Any], grounding: dict[str, str]) -> dict[str, Any]:
    return {
        "schema": executive_ceo_ingress.SUBMIT_SCHEMA_V2,
        "request_ref": request_ref,
        "observed_grounding": grounding,
        "request": request,
    }


def _socket_path(args: argparse.Namespace) -> Path:
    if args.socket is not None:
        path = args.socket
        if path.resolve(strict=False) == _PRODUCTION_CONTROL_SOCKET.resolve(strict=False):
            raise ValueError("refusing Operator control socket")
        return path
    if args.config is None:
        raise ValueError("client commands require --socket or --config")
    info = args.config.lstat()
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) & 0o022:
        raise ValueError("control config must be a private regular file")
    value = json.loads(args.config.read_text(encoding="utf-8"))
    ingress = value.get("ceo_ingress_socket_path") if isinstance(value, dict) else None
    control = value.get("control_socket_path") if isinstance(value, dict) else None
    if not isinstance(ingress, str) or not Path(ingress).is_absolute():
        raise ValueError("control config ceo_ingress_socket_path must be absolute")
    if isinstance(control, str) and Path(ingress).resolve(strict=False) == Path(control).resolve(strict=False):
        raise ValueError("ceo_ingress_socket_path must differ from control_socket_path")
    return Path(ingress)


def _frame(args: argparse.Namespace) -> dict[str, Any]:
    grounding = {
        "mastermind_sha": args.mastermind_sha,
        "macro_sha": args.macro_sha,
        "boot_packet_schema": args.boot_packet_schema,
    }
    return build_frame(args.request_ref, {"objective": args.objective, "workstream": args.workstream}, grounding)


async def _run(args: argparse.Namespace) -> int:
    frame = _frame(args)
    if args.dry_run:
        print(json.dumps(frame, sort_keys=True, separators=(",", ":")))
        return 0
    path = _socket_path(args)
    reader, writer = await asyncio.open_unix_connection(path=str(path))
    try:
        writer.write((json.dumps(frame, sort_keys=True, separators=(",", ":")) + "\n").encode())
        await writer.drain()
        response = json.loads((await reader.readuntil(b"\n")).decode())
    finally:
        writer.close()
        await writer.wait_closed()
    if response.get("ok") is not True:
        error = response.get("error") or {}
        print(f"refused: [{error.get('code', 'unknown')}]", file=__import__("sys").stderr)
        return 2
    print(json.dumps(response.get("result"), sort_keys=True))
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        return asyncio.run(_run(args))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=__import__("sys").stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
