#!/usr/bin/env python3
"""Admitted-owner HTTP launcher for the public Product MCP source profile.

No listener, credential, service unit, OAuth client, token store or identity
binding is created at import or --describe time. An existing deployment owner
must supply a current policy and secured audit directory, and independently
admit the process, TLS proxy and ChatGPT account consent.
"""
from __future__ import annotations

import argparse
import json
import os
import stat
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from integrations.business_mcp_auth.audit import DurableAuthAuditSink
from integrations.business_mcp_auth.contracts import load_resource_policy
from integrations.business_mcp_auth.jwks import BoundedJwksCache, HttpxJwksFetcher
from integrations.business_mcp_auth.jwt_verifier import JwtAuthenticator
from integrations.product_access_mcp.deployment import (
    ProductRuntimeServices, _validate_transport_addresses, create_deployment,
)
from integrations.product_access_mcp.schemas import (
    SCHEMA_SNAPSHOT_SHA256, SCOPE, SERVER_VERSION, TOOL_SPECS,
)

MAX_POLICY_FILE_BYTES = 65536
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1"})


def _canonical_path(raw: str | None) -> Path:
    if type(raw) is not str or not raw or "\x00" in raw:
        raise ValueError("OWNER_PATH_REFUSED")
    path = Path(raw)
    if not path.is_absolute() or path.resolve(strict=True) != path:
        raise ValueError("OWNER_PATH_REFUSED")
    return path


def _closed_object(pairs: list[tuple[str, object]]) -> dict:
    output: dict[str, object] = {}
    for key, value in pairs:
        if key in output:
            raise ValueError("DUPLICATE_POLICY_FIELD")
        output[key] = value
    return output


def _no_constant(_value: str) -> object:
    raise ValueError("NONFINITE_POLICY_NUMBER")


def _load_policy(raw_path: str):
    """Load one exact owner-supplied 0600 policy without following a symlink."""
    path = _canonical_path(raw_path)
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    cloexec = getattr(os, "O_CLOEXEC", 0)
    if not nofollow or not cloexec:
        raise ValueError("POLICY_PLATFORM_REFUSED")
    fd = os.open(path, os.O_RDONLY | nofollow | cloexec)
    try:
        entry = os.fstat(fd)
        if (not stat.S_ISREG(entry.st_mode) or entry.st_uid != os.geteuid()
                or stat.S_IMODE(entry.st_mode) != 0o600 or entry.st_nlink != 1
                or not 0 < entry.st_size <= MAX_POLICY_FILE_BYTES):
            raise ValueError("POLICY_FILE_REFUSED")
        with os.fdopen(fd, "rb", closefd=False) as stream:
            raw = stream.read(MAX_POLICY_FILE_BYTES + 1)
        if len(raw) != entry.st_size:
            raise ValueError("POLICY_FILE_CHANGED")
        selected = load_resource_policy(json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_closed_object,
            parse_constant=_no_constant,
        ))
        if selected.required_scopes != (SCOPE,):
            raise ValueError("PRODUCT_SCOPE_REQUIRED")
        return selected
    finally:
        os.close(fd)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--describe", action="store_true")
    parser.add_argument("--policy-file", help="Absolute, canonical 0600 owner policy path")
    parser.add_argument("--audit-directory", help="Pre-existing owner-owned private directory")
    parser.add_argument("--host", default="127.0.0.1", help="127.0.0.1 or ::1 only")
    parser.add_argument("--port", type=int, help="Exact owner-selected loopback TCP port")
    parser.add_argument("--allowed-origin", action="append", default=[],
                        help="One exact owner-admitted browser Origin; may repeat")
    return parser


def describe() -> str:
    """Static catalog; no disk, network, token, service or audit acquisition."""
    return json.dumps({
        "schema": "mastermind.product_mcp_launcher_descriptor.v1",
        "server_version": SERVER_VERSION,
        "schema_sha256": SCHEMA_SNAPSHOT_SHA256,
        "tools": [entry["name"] for entry in TOOL_SPECS],
        "scope": SCOPE,
        "transport": "streamable-http",
        "binding": "owner-required; loopback-only",
        "capability_state": "BUILT_NOT_PROVEN",
    }, sort_keys=True, separators=(",", ":")) + "\n"


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.describe:
        print(describe(), end="")
        return 0

    # Before touching any policy or audit path, enforce the request-local
    # operator's explicit admission coordinates. No implicit production port.
    if args.host not in LOOPBACK_HOSTS:
        raise SystemExit("PRODUCT_LOOPBACK_REQUIRED")
    if type(args.port) is not int or not 1 <= args.port <= 65535:
        raise SystemExit("PRODUCT_PORT_REQUIRED")
    if not args.policy_file or not args.audit_directory:
        raise SystemExit("PRODUCT_OWNER_POLICY_AND_AUDIT_REQUIRED")

    try:
        policy = _load_policy(args.policy_file)
        audit_path = _canonical_path(args.audit_directory)
    except Exception as exc:
        raise SystemExit("PRODUCT_POLICY_OR_AUDIT_REFUSED") from None

    # The ingress Host must be the admitted resource's exact HTTPS authority,
    # never a selector supplied by the model, a wildcard, or a loopback alias.
    selected = urlsplit(policy.resource)
    if (selected.scheme != "https" or selected.path != "/mcp"
            or not selected.netloc or selected.query or selected.fragment
            or selected.username is not None or selected.password is not None):
        raise SystemExit("PRODUCT_RESOURCE_REFUSED")
    authority = selected.netloc
    # Refuse unadmitted ingress/Origin before opening an audit owner or socket.
    _validate_transport_addresses((authority,), tuple(args.allowed_origin))

    directory_fd = -1
    sink = None
    try:
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
        directory_fd = os.open(audit_path, flags)
        sink = DurableAuthAuditSink.open(directory_fd, policy_id=policy.policy_id)
        os.close(directory_fd)
        directory_fd = -1

        authenticator = JwtAuthenticator(
            policy=policy,
            jwks_cache=BoundedJwksCache(
                policy=policy,
                fetcher=HttpxJwksFetcher(policy),
                monotonic=time.monotonic,
            ),
        )
        app = create_deployment(ProductRuntimeServices(
            authenticator=authenticator,
            policy=policy,
            now=lambda: int(time.time()),
            utc_now=lambda: datetime.now(timezone.utc),
            audit_sink=sink,
            allowed_hosts=(authority,),
            allowed_origins=tuple(args.allowed_origin),
        ))

        import uvicorn

        uvicorn.run(
            app,
            host=args.host,
            port=args.port,
            log_level="info",
            access_log=False,
            proxy_headers=False,
            limit_concurrency=16,
            timeout_graceful_shutdown=5,
        )
        return 0
    finally:
        if directory_fd >= 0:
            os.close(directory_fd)
        if sink is not None:
            sink.close()


if __name__ == "__main__":
    raise SystemExit(main())
