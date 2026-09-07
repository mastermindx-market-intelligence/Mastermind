#!/usr/bin/env python3
"""Launch the bounded Executive OS MCP gateway.

    python3 scripts/executive_mcp.py --mode readonly
    python3 scripts/executive_mcp.py --mode fixture --config /tmp/fixture.json
    python3 scripts/executive_mcp.py --mode readonly --describe

There are exactly two modes (commission R8).  ``readonly`` exposes the four read
tools and refuses ``submit_ceo_intent`` with ``production_write_disabled``.
``fixture`` additionally submits to a TEMPORARY Executive control service named
explicitly in a JSON config; the installed production socket, config, runtime
root, and system root are refused as fixture targets.

There is no production write mode and no flag that creates one.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from integrations.executive_mcp.adapter import (  # noqa: E402
    ExecutiveMcpGateway,
    load_gateway_config,
)
from integrations.executive_mcp.schemas import (  # noqa: E402
    SCHEMA_SNAPSHOT_SHA256,
    GatewayError,
    ServerMode,
    canonical_json,
    refuse_production_path,
    schema_snapshot,
    schema_snapshot_sha256,
)


def _refuse_e1_production_coordinate(value: str, field: str) -> None:
    """Check lexical and symlink-resolved E1 startup coordinates before I/O."""

    normalized = refuse_production_path(value, field)
    refuse_production_path(str(Path(normalized).resolve()), field)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--mode",
        choices=[item.value for item in ServerMode],
        default=ServerMode.READONLY.value,
        help="readonly (default) or fixture; there is no production write mode",
    )
    parser.add_argument(
        "--config",
        default=None,
        help="JSON host config; required for fixture mode",
    )
    parser.add_argument(
        "--repo-root",
        default=None,
        help="Mastermind checkout to project state from (default: this repository)",
    )
    parser.add_argument(
        "--describe",
        action="store_true",
        help="print the frozen tool surface and its snapshot hash, then exit",
    )
    parser.add_argument("--profile", choices=("legacy", "e1-read"), default="legacy")
    parser.add_argument("--policy", default=None, help="E1 policy envelope path")
    parser.add_argument("--macro-root", default=None, help="explicit Macro checkout for E1")
    parser.add_argument("--read-runtime-root", default=None, help="explicit temporary E1 runtime")
    parser.add_argument("--port", type=int, default=None, help="explicit loopback E1 port")
    parser.add_argument("--host", default="127.0.0.1", help="loopback E1 bind host")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.profile == "e1-read":
        required = (args.policy, args.repo_root, args.macro_root, args.read_runtime_root, args.port)
        if args.mode != ServerMode.READONLY.value or args.config is not None or any(value is None for value in required):
            print("executive-mcp: invalid_input: e1-read requires readonly mode and explicit policy/repo/Macro/runtime/port without --config", file=sys.stderr, flush=True)
            return 2
        if not 1 <= args.port <= 65535:
            print("executive-mcp: invalid_input: port must be in 1..65535", file=sys.stderr, flush=True)
            return 2
        try:
            from integrations.executive_mcp.schemas import loopback_bind_host
            loopback_bind_host(args.host, "host")
            for field, value in (
                ("policy", args.policy),
                ("repo_root", args.repo_root),
                ("macro_root", args.macro_root),
                ("read_runtime_root", args.read_runtime_root),
            ):
                _refuse_e1_production_coordinate(value, field)
        except GatewayError as exc:
            print(f"executive-mcp: {exc.code}: {exc.message}", file=sys.stderr, flush=True)
            return 2
        if args.describe:
            from integrations.executive_mcp.e1_http import E1_PROFILE_SHA256

            print(canonical_json({"profile": "e1-read", "tools": ["executive_state", "executive_inbox", "executive_job", "ceo_intent_status"], "snapshot_sha256": E1_PROFILE_SHA256}).decode("utf-8"), flush=True)
            return 0
        try:
            import json

            from integrations.mastermind_executive_app.app import AppSettings
            from integrations.mastermind_executive_app.gateway import load_app_policies
            from integrations.executive_mcp.server import build_e1_mcp_app

            policies = load_app_policies(json.loads(Path(args.policy).read_text(encoding="utf-8")))

            class _AuditSink:
                def emit(self, _event: object) -> None:
                    pass

            app = build_e1_mcp_app(
                AppSettings(
                    policies=policies,
                    mastermind_root=Path(args.repo_root),
                    macro_root_flag=args.macro_root,
                    runtime_root=args.read_runtime_root,
                    environ={},
                    ceo_ingress_socket_path=None,
                    read_only=True,
                ),
                audit_sink=_AuditSink(),
            )
        except GatewayError as exc:
            print(f"executive-mcp: {exc.code}: {exc.message}", file=sys.stderr, flush=True)
            return 2
        except (OSError, ValueError):
            print("executive-mcp: invalid_input: E1 configuration is unavailable", file=sys.stderr, flush=True)
            return 2
        except Exception:
            print("executive-mcp: invalid_input: E1 configuration is unavailable", file=sys.stderr, flush=True)
            return 2
        return _serve_e1(app, args.host, args.port)
    try:
        config = load_gateway_config(args.mode, args.config, repo_root=args.repo_root)
    except GatewayError as exc:
        print(f"executive-mcp: {exc.code}: {exc.message}", file=sys.stderr, flush=True)
        return 2

    if args.describe:
        payload = schema_snapshot()
        payload["snapshot_sha256"] = schema_snapshot_sha256()
        payload["pinned_snapshot_sha256"] = SCHEMA_SNAPSHOT_SHA256
        payload["mode"] = config.mode.value
        print(canonical_json(payload).decode("utf-8"), flush=True)
        return 0

    # Imported here, not at module scope: `--describe` and every config refusal
    # must work on a host that has no MCP SDK installed (R5).
    from integrations.executive_mcp.server import run_stdio

    gateway = ExecutiveMcpGateway(config)
    try:
        asyncio.run(run_stdio(gateway))
    except KeyboardInterrupt:  # graceful shutdown (R12)
        return 0
    return 0


def _serve_e1(app: object, host: str, port: int) -> int:
    """Bind only after E1 input validation and composition have succeeded."""

    import uvicorn

    uvicorn.run(app, host=host, port=port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
