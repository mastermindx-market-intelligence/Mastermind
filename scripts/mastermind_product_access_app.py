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

from control_plane.fs_security import FilesystemSecurityError, has_macos_acl
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


# These are the only explicitly admitted shared temporary ancestors. The
# sticky bit prevents foreign users from replacing an owner-owned entry.
_ROOT_STICKY_DIRECTORIES = frozenset({
    Path("/tmp"), Path("/var/tmp"), Path("/private/tmp"), Path("/private/var/tmp"),
})


def _file_identity(info: os.stat_result) -> tuple[int, ...]:
    """Bind an opened policy file to a stable inode and observable content epoch."""
    return (
        info.st_dev, info.st_ino, info.st_uid, info.st_gid,
        info.st_mode, info.st_nlink, info.st_size,
        info.st_mtime_ns, info.st_ctime_ns,
    )


def _check_directory(fd: int, path: Path) -> None:
    info = os.fstat(fd)
    mode = stat.S_IMODE(info.st_mode)
    sticky_root_temp = (
        path in _ROOT_STICKY_DIRECTORIES
        and info.st_uid == 0
        and mode == 0o1777
    )
    if (not stat.S_ISDIR(info.st_mode)
            or info.st_uid not in (0, os.geteuid())
            or (mode & 0o022 and not sticky_root_temp)):
        raise ValueError("POLICY_DIRECTORY_REFUSED")
    try:
        if has_macos_acl(path, expected_identity=info, descriptor=fd):
            raise ValueError("POLICY_DIRECTORY_REFUSED")
    except FilesystemSecurityError:
        raise ValueError("POLICY_DIRECTORY_REFUSED") from None


def _open_verified_directory(path: Path) -> int:
    """Walk the full parent chain through O_NOFOLLOW directory descriptors.

    Each admitted directory is root-owned or owned by the current service
    principal. Other writers and unqualified extended macOS ACLs are refused.
    The returned descriptor is owned by the caller and must be closed.
    """
    directory = getattr(os, "O_DIRECTORY", 0)
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    cloexec = getattr(os, "O_CLOEXEC", 0)
    if not directory or not nofollow or not cloexec:
        raise ValueError("POLICY_PLATFORM_REFUSED")
    flags = os.O_RDONLY | directory | nofollow | cloexec | getattr(os, "O_NONBLOCK", 0)
    fd = os.open("/", flags)
    current = Path("/")
    try:
        _check_directory(fd, current)
        for component in path.parts[1:]:
            # Inspect the actual directory entry relative to the proven parent,
            # then bind the opened child to that same entry's identity.
            before = os.stat(component, dir_fd=fd, follow_symlinks=False)
            next_fd = os.open(component, flags, dir_fd=fd)
            try:
                opened = os.fstat(next_fd)
                if (not stat.S_ISDIR(before.st_mode)
                        or (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino)):
                    raise ValueError("POLICY_DIRECTORY_CHANGED")
                current = current / component
                _check_directory(next_fd, current)
                after = os.stat(component, dir_fd=fd, follow_symlinks=False)
                if (after.st_dev, after.st_ino) != (opened.st_dev, opened.st_ino):
                    raise ValueError("POLICY_DIRECTORY_CHANGED")
            except BaseException:
                os.close(next_fd)
                raise
            try:
                os.close(fd)
            except BaseException:
                os.close(next_fd)
                raise
            fd = next_fd
        return fd
    except BaseException:
        os.close(fd)
        raise


def _read_policy_fd(fd: int) -> bytes:
    with os.fdopen(fd, "rb", closefd=False) as stream:
        return stream.read(MAX_POLICY_FILE_BYTES + 1)


def _load_policy(raw_path: str):
    """Load one descriptor-bound, ACL-free, stable owner-only policy file."""
    path = _canonical_path(raw_path)
    dir_fd = _open_verified_directory(path.parent)
    fd = -1
    try:
        before_named = os.stat(path.name, dir_fd=dir_fd, follow_symlinks=False)
        flags = (os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC
                 | getattr(os, "O_NONBLOCK", 0))
        fd = os.open(path.name, flags, dir_fd=dir_fd)
        before = os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode)
                or before.st_uid != os.geteuid()
                or stat.S_IMODE(before.st_mode) != 0o600 or before.st_nlink != 1
                or not 0 < before.st_size <= MAX_POLICY_FILE_BYTES):
            raise ValueError("POLICY_FILE_REFUSED")
        if _file_identity(before_named) != _file_identity(before):
            raise ValueError("POLICY_FILE_CHANGED")
        try:
            if has_macos_acl(path, expected_identity=before, descriptor=fd):
                raise ValueError("POLICY_FILE_REFUSED")
        except FilesystemSecurityError:
            raise ValueError("POLICY_FILE_REFUSED") from None
        raw = _read_policy_fd(fd)
        after = os.fstat(fd)
        after_named = os.stat(path.name, dir_fd=dir_fd, follow_symlinks=False)
        if (len(raw) != before.st_size
                or _file_identity(before) != _file_identity(after)
                or _file_identity(after) != _file_identity(after_named)):
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
        if fd >= 0:
            os.close(fd)
        os.close(dir_fd)


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
        # Bind the audit directory through the same owned, ACL-free ancestor
        # chain before handing its descriptor to the existing durable owner.
        # This pre-acquisition failure is safe to coarsen; failures inside the
        # durable sink retain their original effect/cleanup classification.
        try:
            directory_fd = _open_verified_directory(audit_path)
        except (OSError, ValueError):
            raise SystemExit("PRODUCT_AUDIT_DIRECTORY_REFUSED") from None
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
