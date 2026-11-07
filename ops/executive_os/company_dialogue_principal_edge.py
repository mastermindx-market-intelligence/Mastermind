"""Installed principal Company Dialogue stdio edge over the shared immutable MCP runtime.

This entrypoint deliberately does not provision Python, install packages, own the
Executive listener, select a principal/child, or create lifecycle state. It
reuses the existing company_mcp_edge runtime receipt and only binds a distinct,
root-owned principal edge config plus this exact release entrypoint.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
import re
import stat
import sys


SOURCE = Path(__file__).absolute().parents[2]
if str(SOURCE) not in sys.path:
    sys.path.insert(0, str(SOURCE))

from ops.executive_os import company_mcp_edge as shared  # noqa: E402


SYSTEM = shared.SYSTEM
CONFIG = SYSTEM / "config/company-dialogue-principal-edge.json"
SOCKET = "/var/run/mastermind-executive/company-dialogue-principal.sock"
SCHEMA = "mastermind.company_dialogue_principal_edge/v1"
CONFIG_KEYS = {
    "schema",
    "release_sha",
    "control_uid",
    "worker_uid",
    "runtime_entry_sha256",
    "principal_entry_sha256",
    "receipt_sha256",
}
ENV = shared.ENV


class PrincipalEdgeError(RuntimeError):
    pass


def _digest(value: object, *, field: str) -> str:
    if type(value) is not str or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise PrincipalEdgeError(f"{field} differs")
    return value


def read_config() -> dict[str, object]:
    try:
        shared.sealed(CONFIG)
        if stat.S_IMODE(CONFIG.stat().st_mode) != 0o444:
            raise PrincipalEdgeError("principal edge config mode differs")
        raw = json.loads(CONFIG.read_bytes())
    except PrincipalEdgeError:
        raise
    except Exception as exc:
        raise PrincipalEdgeError("principal edge config is unavailable") from exc
    if (
        type(raw) is not dict
        or set(raw) != CONFIG_KEYS
        or raw.get("schema") != SCHEMA
        or type(raw.get("release_sha")) is not str
        or re.fullmatch(r"[0-9a-f]{40}", raw["release_sha"]) is None
        or any(
            type(raw.get(key)) is not int or raw[key] <= 0
            for key in ("control_uid", "worker_uid")
        )
        or raw["control_uid"] == raw["worker_uid"]
    ):
        raise PrincipalEdgeError("principal edge config differs")
    for key in (
        "runtime_entry_sha256",
        "principal_entry_sha256",
        "receipt_sha256",
    ):
        _digest(raw.get(key), field=key)
    return dict(raw)


def verify(config: dict[str, object] | None = None):
    current = read_config() if config is None else dict(config)
    if set(current) != CONFIG_KEYS or current.get("schema") != SCHEMA:
        raise PrincipalEdgeError("principal edge config fields differ")
    if current.get("release_sha") != SOURCE.name:
        raise PrincipalEdgeError("principal edge release binding differs")
    if current.get("principal_entry_sha256") != shared.digest(Path(__file__)):
        raise PrincipalEdgeError("principal edge source binding differs")
    if current.get("runtime_entry_sha256") != shared.digest(Path(shared.__file__)):
        raise PrincipalEdgeError("shared MCP edge source binding differs")
    shared_config = {
        "schema": shared.SCHEMA,
        "release_sha": current["release_sha"],
        "control_uid": current["control_uid"],
        "worker_uid": current["worker_uid"],
        "entry_sha256": current["runtime_entry_sha256"],
        "receipt_sha256": current["receipt_sha256"],
    }
    try:
        root, receipt = shared.verify(shared_config)
    except Exception as exc:
        raise PrincipalEdgeError("shared immutable MCP runtime differs") from exc
    return root, receipt


def _require_isolated_runtime() -> None:
    if not sys.flags.isolated or not sys.dont_write_bytecode:
        raise PrincipalEdgeError(
            "principal edge requires isolated Python without bytecode"
        )


def _interpreter_identity() -> tuple[Path, Path, Path]:
    return Path(sys.executable).absolute(), Path(sys.prefix), Path(sys.base_prefix)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("verify", "stdio", "sdk-stdio"))
    args = parser.parse_args(argv)
    _require_isolated_runtime()
    config = read_config()
    root, _ = verify(config)
    if args.command == "verify":
        return 0
    if os.geteuid() != config["worker_uid"]:
        raise PrincipalEdgeError(
            "principal Company stdio requires the installed worker UID"
        )
    python = root / "bin/python3.12"
    if args.command == "stdio":
        os.execve(
            python,
            [str(python), "-I", "-B", str(Path(__file__)), "sdk-stdio"],
            ENV,
        )
    executable, prefix, base_prefix = _interpreter_identity()
    if (
        executable != python
        or prefix != root
        or base_prefix != shared.BASE_PYTHON.parents[1]
    ):
        raise PrincipalEdgeError("principal Company SDK interpreter differs")
    from integrations.company_dialogue_principal_host_transport import (
        run_principal_company_dialogue_stdio,
    )

    asyncio.run(
        run_principal_company_dialogue_stdio(
            socket_path=SOCKET,
            server_uid=config["control_uid"],
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
