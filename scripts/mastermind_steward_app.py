#!/usr/bin/env python3
"""Launch the Mastermind Steward Business app over stdio or authenticated HTTP."""
from __future__ import annotations

import argparse
import asyncio
import dataclasses
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from control_plane.chairman_control_room import build_control_room
from integrations.business_mcp_auth.contracts import (
    AuthAuditEvent,
    load_resource_policy,
)
from integrations.business_mcp_auth.jwks import (
    BoundedJwksCache,
    HttpxJwksFetcher,
)
from integrations.business_mcp_auth.jwt_verifier import JwtAuthenticator
from integrations.business_mcp_auth.mcp_adapter import MastermindTokenVerifier
from integrations.mastermind_steward_app.app import build_authenticated_app
from integrations.mastermind_steward_app.projection import (
    ControlRoomStewardReadPort,
)
from integrations.mastermind_steward_app.server import (
    build_contract_server,
    describe,
    run_stdio,
)

_LOOPBACK = {"127.0.0.1", "::1", "localhost"}


class _StderrAuditSink:
    def emit(self, event: AuthAuditEvent) -> None:
        payload = dataclasses.asdict(event)
        print(
            json.dumps(
                {"event": "mastermind.business_mcp_auth", **payload},
                sort_keys=True,
                separators=(",", ":"),
            ),
            file=sys.stderr,
            flush=True,
        )


def _clock() -> datetime:
    return datetime.now(timezone.utc)


def _load_policy(path: Path):
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SystemExit("Steward policy file is unreadable or invalid") from exc
    return load_resource_policy(payload)


def _split_csv(value: str | None) -> tuple[str, ...]:
    if not value:
        return ()
    return tuple(
        token
        for token in (item.strip() for item in value.split(","))
        if token
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--transport",
        choices=("stdio", "http"),
        default="stdio",
        help="stdio is a private-tunnel read canary; HTTP always requires OAuth.",
    )
    parser.add_argument("--repo-root", default=str(_REPO_ROOT))
    parser.add_argument("--macro-root", default=None)
    parser.add_argument("--bindings-path", default=None)
    parser.add_argument("--stale-after-seconds", type=int, default=900)
    parser.add_argument("--policy-file", default=os.getenv("MASTERMIND_STEWARD_POLICY"))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument(
        "--extra-allowed-hosts",
        default=os.getenv("MASTERMIND_STEWARD_ALLOWED_HOSTS"),
    )
    parser.add_argument("--describe", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.describe:
        print(describe(), end="")
        return 0

    repo_root = Path(args.repo_root).expanduser().resolve()
    if not (repo_root / "pyproject.toml").is_file():
        raise SystemExit("repo-root is not a Mastermind checkout")

    def snapshot_provider() -> dict[str, Any]:
        return build_control_room(
            repo_root=repo_root,
            macro_root_flag=args.macro_root,
            bindings_path=args.bindings_path,
        )

    port = ControlRoomStewardReadPort(
        snapshot_provider,
        clock=_clock,
        stale_after_seconds=args.stale_after_seconds,
    )
    contract = build_contract_server(port)

    if args.transport == "stdio":
        asyncio.run(run_stdio(contract))
        return 0

    if args.host not in _LOOPBACK:
        raise SystemExit("HTTP transport must bind loopback")
    if isinstance(args.port, bool) or not 1 <= args.port <= 65535:
        raise SystemExit("port must be between 1 and 65535")
    if not args.policy_file:
        raise SystemExit("--policy-file is required for authenticated HTTP")

    policy = _load_policy(Path(args.policy_file).expanduser().resolve())
    cache = BoundedJwksCache(
        policy=policy,
        fetcher=HttpxJwksFetcher(policy),
        monotonic=time.monotonic,
    )
    authenticator = JwtAuthenticator(policy=policy, jwks_cache=cache)
    verifier = MastermindTokenVerifier(
        authenticator=authenticator,
        policy=policy,
        now=lambda: int(time.time()),
        audit_sink=_StderrAuditSink(),
    )
    app = build_authenticated_app(
        contract,
        policy=policy,
        token_verifier=verifier,
        extra_allowed_hosts=_split_csv(args.extra_allowed_hosts),
    )

    import uvicorn

    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        log_level="info",
        access_log=False,
        proxy_headers=False,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
