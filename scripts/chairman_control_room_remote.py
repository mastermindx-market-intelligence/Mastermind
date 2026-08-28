#!/usr/bin/env python3
"""Unix-socket-only HTTP service for the remote read-only Control Room."""
from __future__ import annotations

import argparse
import grp
import importlib
import json
import os
import re
import socket
import socketserver
import stat
import sys
import threading
from collections import deque
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Any, Sequence
from urllib.parse import unquote_to_bytes

# ``python -I`` intentionally removes the script directory and working
# directory from sys.path. The unit starts this exact immutable entrypoint, so
# bootstrap only its enclosing, release-attested repository root.
_RELEASE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, os.fspath(_RELEASE_ROOT))
remote = importlib.import_module("control_plane.chairman_control_room_remote")


REMOTE_SOCKET = Path("/run/mastermind-control-room/remote.sock")
DEFAULT_STATIC_DIR = Path(__file__).resolve().parents[1] / "app" / "static" / "chairman_control"
STATIC_ROUTES = {
    "/": ("remote.html", "text/html; charset=utf-8"),
    "/static/control_room.css": ("control_room.css", "text/css; charset=utf-8"),
    "/static/control_room.js": ("control_room.js", "application/javascript; charset=utf-8"),
}
READ_ROUTES = frozenset((*STATIC_ROUTES, "/healthz", "/api/state"))
_BAD_PERCENT_RE = re.compile(r"%(?![0-9A-Fa-f]{2})")
_ENCODED_SEPARATOR_RE = re.compile(r"(?i)%(?:2f|5c)")


@dataclass
class RemoteServerConfig:
    socket_path: Path
    static_dir: Path
    cache: Any
    caddy_gid: int
    service_uid: int
    events: deque[dict[str, Any]] | None = None

    def __post_init__(self) -> None:
        if self.events is not None and (
            not isinstance(self.events, deque)
            or self.events.maxlen is None
            or self.events.maxlen <= 0
        ):
            raise ValueError("events must be a bounded test-only event sink")


def _prepare_socket_path(config: RemoteServerConfig) -> None:
    path = Path(config.socket_path)
    parent = path.parent
    if parent.exists():
        info = parent.lstat()
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
            raise RuntimeError("socket_parent_unsafe")
        if info.st_uid != config.service_uid:
            raise RuntimeError("socket_parent_foreign_owner")
    else:
        parent.mkdir(mode=0o750, parents=True)
    os.chmod(parent, 0o750)
    os.chown(parent, config.service_uid, config.caddy_gid)
    if os.path.lexists(path):
        info = path.lstat()
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISSOCK(info.st_mode):
            raise RuntimeError("socket_path_unsafe")
        if info.st_uid != config.service_uid:
            raise RuntimeError("socket_path_foreign_owner")
        path.unlink()


def _canonical_read_path(raw_target: str) -> tuple[str | None, int]:
    if type(raw_target) is not str or not raw_target.startswith("/"):
        return None, 400
    if "?" in raw_target or "#" in raw_target or "\\" in raw_target:
        return None, 400
    if "//" in raw_target or _BAD_PERCENT_RE.search(raw_target):
        return None, 400
    if _ENCODED_SEPARATOR_RE.search(raw_target):
        return None, 400
    try:
        decoded = unquote_to_bytes(raw_target).decode("utf-8", errors="strict")
    except (UnicodeError, ValueError):
        return None, 400
    if "\x00" in decoded or "\\" in decoded or "%" in decoded or "//" in decoded:
        return None, 400
    if decoded == "/":
        return decoded, 200
    segments = decoded.split("/")[1:]
    if any(segment in ("", ".", "..") for segment in segments):
        return None, 400
    if decoded not in READ_ROUTES:
        return None, 404
    return decoded, 200


class RemoteControlRoomHandler(BaseHTTPRequestHandler):
    server_version = "MastermindControlRoomRemote/1"
    sys_version = ""

    @property
    def _config(self) -> RemoteServerConfig:
        return self.server.config

    def parse_request(self) -> bool:
        # BaseHTTPRequestHandler deliberately collapses a leading `//` before
        # exposing `self.path`. Preserve the original request target so our
        # closed route boundary can reject that ambiguity instead of accepting
        # its normalized form.
        accepted = super().parse_request()
        self.raw_target = self.path
        try:
            request_line = self.raw_requestline.decode("iso-8859-1").rstrip("\r\n")
            parts = request_line.split()
            if len(parts) == 3:
                self.raw_target = parts[1]
        except (UnicodeError, AttributeError):
            self.raw_target = "<invalid>"
        return accepted

    def log_message(self, _format: str, *_args) -> None:
        # All events are emitted explicitly after path normalization.  Never log
        # browser headers, credentials, raw queries, or exception text.
        return

    def _event(self, path: str | None, status: int) -> None:
        if self._config.events is not None:
            self._config.events.append({
                "method": self.command if self.command in ("GET", "HEAD") else "MUTATION",
                "path": path if path is not None else "<rejected>",
                "status": status,
            })

    def _send(self, status: int, body: bytes, content_type: str, *, path: str | None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "private, no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)
        self._event(path, status)

    def _json(self, status: int, value: dict[str, Any], *, path: str | None) -> None:
        body = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
        self._send(status, body, "application/json; charset=utf-8", path=path)

    def _read(self) -> None:
        path, status = _canonical_read_path(self.raw_target)
        if path is None:
            self._json(status, {"ok": False, "error": {"code": "route_rejected"}}, path=None)
            return
        if path in STATIC_ROUTES:
            relative, content_type = STATIC_ROUTES[path]
            try:
                body = (self._config.static_dir / relative).read_bytes()
            except OSError:
                self._json(503, {"ok": False, "error": {"code": "static_unavailable"}}, path=path)
                return
            self._send(200, body, content_type, path=path)
            return
        if path == "/healthz":
            self._send(200, b"ok\n", "text/plain; charset=utf-8", path=path)
            return
        document = self._config.cache.snapshot()
        if document is None:
            self._json(
                503,
                {"ok": False, "error": {"code": "state_unavailable"}},
                path=path,
            )
            return
        self._json(200, {"ok": True, "control_room": document}, path=path)

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler contract
        self._read()

    def do_HEAD(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler contract
        self._read()

    def _mutation(self) -> None:
        self.send_response(405)
        self.send_header("Allow", "GET, HEAD")
        self.send_header("Content-Length", "0")
        self.send_header("Cache-Control", "private, no-store")
        self.end_headers()
        self._event(None, 405)

    do_POST = _mutation
    do_PUT = _mutation
    do_PATCH = _mutation
    do_DELETE = _mutation


class ControlRoomUnixServer(socketserver.UnixStreamServer):
    address_family = socket.AF_UNIX
    allow_reuse_address = False

    def __init__(self, socket_path: Path, handler, config: RemoteServerConfig):
        self.config = config
        _prepare_socket_path(config)
        super().__init__(os.fspath(socket_path), handler)
        os.chmod(socket_path, 0o660)
        os.chown(socket_path, config.service_uid, config.caddy_gid)

    def server_close(self) -> None:
        path = Path(self.server_address)
        try:
            super().server_close()
        finally:
            try:
                info = path.lstat()
            except FileNotFoundError:
                info = None
            if info is not None and stat.S_ISSOCK(info.st_mode) and info.st_uid == self.config.service_uid:
                path.unlink()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", required=True, type=Path)
    parser.add_argument("--macro-root", required=True, type=Path)
    parser.add_argument("--expected-commit", required=True)
    parser.add_argument("--build-metadata", required=True, type=Path)
    parser.add_argument("--interval-seconds", type=float, default=300.0)
    parser.add_argument("--stale-after-seconds", type=float, default=900.0)
    parser.add_argument("--timeout-seconds", type=float, default=60.0)
    parser.add_argument("--max-output-bytes", type=int, default=4 * 1024 * 1024)
    return parser


def _load_build_identity(
    repo_root: Path, path: Path, expected_commit: str
) -> remote.BuildIdentity:
    try:
        return remote.verify_release_identity(
            repo_root,
            expected_commit=expected_commit,
            build_metadata=path,
        )
    except remote.ReleaseError as exc:
        raise RuntimeError("build_identity_unavailable") from exc


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    identity = _load_build_identity(
        args.repo_root, args.build_metadata, args.expected_commit
    )
    caddy_gid = grp.getgrnam("caddy").gr_gid
    collector = remote.CollectorConfig(
        repo_root=args.repo_root,
        macro_root=args.macro_root,
        active_builds_directory_group_gid=caddy_gid,
        active_builds_group_gid=caddy_gid,
        interval_seconds=args.interval_seconds,
        stale_after_seconds=args.stale_after_seconds,
        timeout_seconds=args.timeout_seconds,
        max_output_bytes=args.max_output_bytes,
    )
    cache = remote.RemoteStateCache(collector, identity)
    stop = threading.Event()
    refresh_thread = threading.Thread(target=cache.run, args=(stop,), daemon=True)
    config = RemoteServerConfig(
        socket_path=REMOTE_SOCKET,
        static_dir=DEFAULT_STATIC_DIR,
        cache=cache,
        caddy_gid=caddy_gid,
        service_uid=os.geteuid(),
    )
    httpd = ControlRoomUnixServer(REMOTE_SOCKET, RemoteControlRoomHandler, config)
    refresh_thread.start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        httpd.server_close()
        refresh_thread.join(timeout=min(5.0, collector.timeout_seconds))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
