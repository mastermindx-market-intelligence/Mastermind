#!/usr/bin/env python3
"""Run the inert Studio/Paper public OAuth edge on one loopback listener.

This launcher never creates OAuth clients, changes Auth0, enables a public
tunnel, selects a Paper target, or starts Studio Direct. It requires an
already-approved exact resource policy and an already-running tailnet Studio
design route.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import socket
import stat
import sys
import time

import uvicorn

# Production launch uses Python isolated mode. Bind first-party imports only to
# the immutable checkout containing this exact reviewed launcher; never to cwd
# or a caller-supplied PYTHONPATH.
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
_repo_root = os.fspath(_REPO_ROOT)
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)

from integrations.business_mcp_auth.audit import DurableAuthAuditSink
from integrations.business_mcp_auth.contracts import load_resource_policy
from integrations.studio_direct_mcp.cloud_auth_gateway import (
    HttpxStudioForwarder,
    build_business_auth_verifier,
    create_studio_cloud_app,
)

MAX_POLICY_BYTES = 64 * 1024


def _read_policy(path_value: str):
    path = pathlib.Path(path_value).expanduser()
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC
    fd = os.open(path, flags)
    try:
        st = os.fstat(fd)
        if (
            not stat.S_ISREG(st.st_mode)
            or st.st_uid != os.geteuid()
            or stat.S_IMODE(st.st_mode) != 0o600
            or st.st_nlink != 1
            or st.st_size <= 0
            or st.st_size > MAX_POLICY_BYTES
        ):
            raise RuntimeError("Studio cloud policy file security refused")
        raw = os.read(fd, MAX_POLICY_BYTES + 1)
        if len(raw) != st.st_size or len(raw) > MAX_POLICY_BYTES:
            raise RuntimeError("Studio cloud policy read refused")
        return load_resource_policy(json.loads(raw.decode("utf-8", errors="strict")))
    finally:
        os.close(fd)


def _open_audit(directory_value: str, policy_id: str) -> DurableAuthAuditSink:
    directory = pathlib.Path(directory_value).expanduser()
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    host_fd = os.open(directory, flags)
    try:
        return DurableAuthAuditSink.open(host_fd, policy_id=policy_id)
    finally:
        os.close(host_fd)


def _bound_socket(host: str, port: int) -> socket.socket:
    if host != "127.0.0.1" or type(port) is not int or not 1 <= port <= 65535:
        raise RuntimeError("Studio cloud listener must be exact loopback")
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
        sock.set_inheritable(False)
        sock.bind((host, port))
        sock.listen(128)
        return sock
    except BaseException:
        sock.close()
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", required=True)
    parser.add_argument("--audit-dir", required=True)
    parser.add_argument("--upstream-url", required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", required=True, type=int)
    args = parser.parse_args(argv)

    policy = _read_policy(args.policy)
    audit = _open_audit(args.audit_dir, policy.policy_id)
    sock: socket.socket | None = None
    close_error: BaseException | None = None
    try:
        verifier = build_business_auth_verifier(
            policy=policy,
            now=lambda: int(time.time()),
            monotonic=time.monotonic,
            audit_sink=audit,
        )
        forwarder = HttpxStudioForwarder(args.upstream_url)
        app = create_studio_cloud_app(
            policy=policy,
            verifier=verifier,
            forwarder=forwarder,
        )
        sock = _bound_socket(args.host, args.port)
        config = uvicorn.Config(
            app,
            host=None,
            port=None,
            log_level="info",
            access_log=False,
            proxy_headers=False,
            server_header=False,
            date_header=False,
        )
        server = uvicorn.Server(config)
        import asyncio

        asyncio.run(server.serve(sockets=[sock]))
        return 0 if server.started else 1
    finally:
        if sock is not None:
            try:
                sock.close()
            except BaseException as error:
                close_error = error
        try:
            audit.close()
        except BaseException as error:
            close_error = close_error or error
        if close_error is not None:
            raise RuntimeError("Studio cloud edge cleanup is uncertain") from close_error


if __name__ == "__main__":
    raise SystemExit(main())
