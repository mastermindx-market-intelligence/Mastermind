#!/usr/bin/env python3
"""scripts/mastermind_executive_app.py — BSC-E1 process entrypoint.

Runs :func:`integrations.mastermind_executive_app.app.create_app` under
uvicorn. Every security-relevant setting is an EXPLICIT, required flag —
there is no default policy file, no default mastermind/macro root, and no
default dedicated-ingress socket path — so this script is production-disabled
by construction: running it with no arguments does nothing but print usage
and exit non-zero.  It never installs anything, never arms a production
socket, and never widens any existing peer list; it is a pure CLIENT of an
already-installed dedicated CeoIngress socket, configured by an operator.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from integrations.executive_mcp.schemas import GatewayError, loopback_bind_host, refuse_production_path
from integrations.mastermind_executive_app.app import AppSettings, create_app
from integrations.mastermind_executive_app.gateway import load_app_policies


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="mastermind_executive_app",
        description=(
            "BSC-E1 authenticated Executive app: reused five-tool reads plus "
            "one dedicated-CeoIngress-only admission. Every flag below is "
            "required; there is no installed-by-default configuration."
        ),
    )
    parser.add_argument(
        "--policy",
        required=True,
        type=Path,
        help=(
            "Path to a policy-envelope JSON file (schema "
            "mastermind.executive_app_policy_example.v1) naming the 'read' "
            "and 'submit' ResourcePolicy objects. See "
            "config/business_mcp/executive_policy.example.json for the shape "
            "-- that file is an EXAMPLE and is never read automatically."
        ),
    )
    parser.add_argument(
        "--mastermind-root",
        required=True,
        type=Path,
        help="Absolute path to the Mastermind checkout this process reads grounding/state from.",
    )
    parser.add_argument(
        "--macro-root",
        default=None,
        help="Optional explicit Macro checkout path (falls back to the resolve_macro_root ladder).",
    )
    parser.add_argument(
        "--ceo-ingress-socket",
        required=True,
        type=Path,
        help="Absolute path to the ALREADY-INSTALLED dedicated CeoIngress AF_UNIX socket.",
    )
    parser.add_argument("--host", default="127.0.0.1", help="Bind host; loopback only.")
    parser.add_argument("--port", required=True, type=int, help="Bind port.")
    return parser.parse_args(argv)


def build_settings(args: argparse.Namespace) -> AppSettings:
    payload = json.loads(Path(args.policy).read_text(encoding="utf-8"))
    policies = load_app_policies(payload)

    mastermind_root = str(Path(args.mastermind_root).resolve())
    ceo_ingress_socket_path = refuse_production_path(
        str(Path(args.ceo_ingress_socket).resolve()), "ceo_ingress_socket_path"
    )
    loopback_bind_host(args.host)

    return AppSettings(
        policies=policies,
        mastermind_root=mastermind_root,
        macro_root_flag=args.macro_root,
        environ=dict(os.environ),
        ceo_ingress_socket_path=ceo_ingress_socket_path,
    )


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    try:
        settings = build_settings(args)
    except GatewayError as exc:
        print(f"mastermind_executive_app: refused: {exc.message}", file=sys.stderr)
        return 2
    except (OSError, ValueError) as exc:
        print(f"mastermind_executive_app: refused: {exc}", file=sys.stderr)
        return 2

    import uvicorn

    app = create_app(settings)
    uvicorn.run(app, host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
