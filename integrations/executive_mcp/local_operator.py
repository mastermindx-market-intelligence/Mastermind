"""Local operator mode (L4): a Unix-socket door admitted by kernel peer uid.

Off unless the installed Executive config carries a ``local_operator`` block.
The public tunnel reaches the Executive only over loopback TCP, so loopback
source or request headers can never carry admission here: the only admission
fact is the connected socket's kernel peer uid (getpeereid(2)).
"""
from __future__ import annotations

import ctypes
import dataclasses
import hashlib
import time
from pathlib import Path


class LocalOperatorConfigError(ValueError):
    """Malformed local-operator block; no socket may be created."""


@dataclasses.dataclass(frozen=True)
class LocalOperatorConfig:
    socket_path: Path
    allowed_uids: tuple[int, ...]
    operator_subject: str


def parse_local_operator_config(block: object) -> LocalOperatorConfig | None:
    """Parse the config block; absent stays off, malformed fails closed."""
    if block is None:
        return None
    keys = {"socket_path", "allowed_uids", "operator_subject"}
    if type(block) is not dict or set(block) != keys:
        raise LocalOperatorConfigError("local_operator block keys differ")
    path = block["socket_path"]
    if type(path) is not str or not path or "\x00" in path or not path.startswith("/"):
        raise LocalOperatorConfigError("local_operator socket_path must be absolute")
    uids = block["allowed_uids"]
    if (type(uids) is not list or not uids
            or any(type(uid) is not int or isinstance(uid, bool) or uid < 0 for uid in uids)
            or len(set(uids)) != len(uids)):
        raise LocalOperatorConfigError("local_operator allowed_uids must be a non-empty int list")
    subject = block["operator_subject"]
    if (type(subject) is not str or not subject or len(subject) > 128
            or subject != subject.strip() or any(ord(ch) < 0x20 or ord(ch) == 0x7f for ch in subject)):
        raise LocalOperatorConfigError("local_operator operator_subject is invalid")
    return LocalOperatorConfig(Path(path), tuple(uids), subject)


def peer_uid(sock: object) -> int:
    """Kernel credential of the connected peer via getpeereid(2)."""
    direct = getattr(sock, "getpeereid", None)
    if callable(direct):
        uid, _gid = direct()
        return int(uid)
    libc = ctypes.CDLL(None, use_errno=True)
    uid, gid = ctypes.c_uint32(0), ctypes.c_uint32(0)
    if libc.getpeereid(ctypes.c_int(sock.fileno()), ctypes.byref(uid), ctypes.byref(gid)) != 0:
        errno = ctypes.get_errno()
        raise OSError(errno, f"getpeereid failed: {errno}")
    return int(uid.value)


class LocalOperatorBindError(RuntimeError):
    """Bind refused (a live listener already owns the socket path)."""


class LocalOperatorListener:
    """Serve one ASGI app on a Unix socket, admitting by kernel peer uid.

    Admission is per connection, before any request byte is served: the
    connected socket's peer uid must be in ``allowed_uids``. File permissions
    never carry admission (contract amendment b): the socket is connectable
    (explicit mode) and the parent traversable.
    """

    def __init__(self, config, app, *, peer_uid_reader=peer_uid, mode=0o666):
        if not isinstance(config, LocalOperatorConfig):
            raise TypeError("LocalOperatorConfig required")
        if mode not in (0o660, 0o666):
            raise ValueError("socket mode must be 0660 or 0666")
        if not callable(getattr(app, "__call__", None)):
            raise TypeError("an ASGI app is required")
        if not callable(peer_uid_reader):
            raise TypeError("peer_uid_reader must be callable")
        self._config = config
        self._app = app
        self._read_peer_uid = peer_uid_reader
        self._mode = mode
        self._sock = None
        self._inode = None
        self._tasks = set()

    def bind(self) -> None:
        """Create the socket; refuse a live listener, replace a stale file."""
        import os
        import socket
        import stat as _stat

        path = self._config.socket_path
        if os.path.lexists(path):
            stale = False
            probe = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            try:
                probe.settimeout(0.5)
                probe.connect(str(path))
            except (ConnectionRefusedError, FileNotFoundError):
                stale = True
            except OSError:
                stale = False  # unreachable/timeout: treat as live, never unlink
            finally:
                probe.close()
            if not stale:
                raise LocalOperatorBindError(
                    "local operator socket path is owned by a live listener")
            os.unlink(path)
        parent = path.parent
        if not parent.is_dir():
            parent.mkdir(parents=True, exist_ok=True)
            os.chmod(parent, 0o755)
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            sock.bind(str(path))
            os.chmod(path, self._mode)
            sock.listen(128)
            sock.setblocking(False)
        except BaseException:
            sock.close()
            raise
        self._sock = sock
        self._inode = os.lstat(path).st_ino

    def stop(self) -> None:
        """Close the listener and remove only the socket file we created."""
        import os
        import stat as _stat

        sock, self._sock = self._sock, None
        if sock is not None:
            sock.close()
        self._tasks.discard(None)
        for task in list(self._tasks):
            task.cancel()
        self._tasks.clear()
        path = self._config.socket_path
        try:
            info = os.lstat(path)
        except OSError:
            return
        if info.st_ino == self._inode and _stat.S_ISSOCK(info.st_mode):
            try:
                os.unlink(path)
            except OSError:
                pass

    # ------------------------------------------------------------ serving

    _CONNECTION_TIMEOUT = 300.0
    _MAX_RESPONSE_BYTES = 16 * 1024 * 1024

    async def serve_forever(self) -> None:
        """Accept loop; each connection is admitted before any byte is read."""
        import asyncio

        loop = asyncio.get_running_loop()
        while True:
            try:
                conn, _ = await loop.sock_accept(self._sock)
            except asyncio.CancelledError:
                raise
            except OSError:
                if self._sock is None:
                    return  # stopped
                continue
            task = asyncio.create_task(self._serve_connection(conn))
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)

    async def _serve_connection(self, conn) -> None:
        import asyncio

        try:
            uid = self._read_peer_uid(conn)
            if uid not in self._config.allowed_uids:
                conn.close()  # refused before any request byte is served
                return
            conn.setblocking(False)
            await asyncio.wait_for(self._serve_http(conn), self._CONNECTION_TIMEOUT)
        except Exception:
            pass
        finally:
            try:
                conn.close()
            except OSError:
                pass

    async def _serve_http(self, sock) -> None:
        """One admitted connection: HTTP/1.1 via h11, dispatched to the app."""
        import asyncio
        import h11

        loop = asyncio.get_running_loop()
        http = h11.Connection(h11.SERVER)
        while True:
            request, body = None, bytearray()
            while True:
                try:
                    event = http.next_event()
                except Exception:
                    return
                if event is h11.NEED_DATA:
                    data = await loop.sock_recv(sock, 65536)
                    if data:
                        http.receive_data(data)
                    else:
                        http.receive_eof()
                    continue
                if isinstance(event, h11.Request) and request is None:
                    request = event
                    continue
                if isinstance(event, h11.Data):
                    if len(body) + len(event.data) > self._MAX_RESPONSE_BYTES:
                        return
                    body += event.data
                    continue
                if isinstance(event, h11.EndOfMessage) and request is not None:
                    break
                return  # closed or unsupported framing
            try:
                keep = await self._respond(loop, sock, http, request, bytes(body))
            except Exception:
                return
            if not keep:
                return

    async def _respond(self, loop, sock, http, request, body: bytes) -> bool:
        """Serve exactly one request; True when the connection may continue."""
        import h11

        path, _, query = request.target.partition(b"?")
        scope = {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.3"},
            "http_version": request.http_version.decode("latin-1"),
            "scheme": "http",
            "method": request.method.decode("latin-1"),
            "path": path.decode("latin-1"),
            "raw_path": path,
            "query_string": query,
            "headers": [(k.lower(), v) for k, v in request.headers],
            "root_path": "",
            "client": ("local-operator-socket", 0),
            "server": ("local-operator-socket", 0),
        }
        served = {"done": False}

        async def receive():
            if served["done"]:
                return {"type": "http.disconnect"}
            served["done"] = True
            return {"type": "http.request", "body": body, "more_body": False}

        start, chunks = {"message": None}, []

        async def send(message):
            if message["type"] == "http.response.start":
                start["message"] = message
            elif message["type"] == "http.response.body":
                chunks.append(message.get("body", b""))

        await self._app(scope, receive, send)
        if start["message"] is None:
            return False
        payload = b"".join(chunks)
        if len(payload) > self._MAX_RESPONSE_BYTES:
            return False
        status = start["message"]["status"]
        headers = list(start["message"].get("headers") or [])
        headers.append((b"content-length", str(len(payload)).encode("ascii")))
        head = http.send(h11.Response(status_code=status, headers=headers))
        await loop.sock_sendall(sock, head)
        await loop.sock_sendall(sock, http.send(h11.Data(data=payload)))
        await loop.sock_sendall(sock, http.send(h11.EndOfMessage()))
        try:
            keep = http.they_should_keep_alive()
            http.start_next_cycle()
            return keep
        except Exception:
            return False


class LocalOperatorAuthenticator:
    """Attribute socket-admitted requests to the configured operator subject.

    There is no token: the listener's kernel peer-uid check is the whole
    admission, and this class projects the configured subject into the same
    pseudonymous principal shape the OS/workspace transports consume. The raw
    subject never leaves this class; downstream material carries only its
    SHA-256 digest.
    """

    ISSUER = "local-operator-socket"
    POLICY_ID = "local-operator.socket"
    RESOURCE = "local-operator-socket"
    LIFETIME_SECONDS = 60
    CLIENT_REF = "oauth-client-unavailable"

    def __init__(self, config, *, now=None):
        if not isinstance(config, LocalOperatorConfig):
            raise TypeError("LocalOperatorConfig required")
        if now is None:
            now = time.time
        if not callable(now):
            raise TypeError("now must be callable")
        self._subject = config.operator_subject
        self._subject_digest = hashlib.sha256(
            config.operator_subject.encode("utf-8")).hexdigest()
        self._issuer_digest = hashlib.sha256(
            self.ISSUER.encode("utf-8")).hexdigest()
        self._now = now

    @property
    def subject_digest(self) -> str:
        return self._subject_digest

    def principal(self):
        """One bounded operator principal; the scope derives from the digest."""
        from integrations.business_mcp_auth.contracts import VerifiedPrincipal

        issued = int(self._now())
        return VerifiedPrincipal(
            policy_id=self.POLICY_ID, issuer=self.ISSUER,
            issuer_digest=self._issuer_digest, resource=self.RESOURCE,
            subject_digest=self._subject_digest, client_ref=self.CLIENT_REF,
            scopes=("mastermind.executive.read",), issued_at=issued,
            expires_at=issued + self.LIFETIME_SECONDS, jti_digest=None)

    def principal_scope(self) -> str:
        """The same opaque owner namespace the OS transport derives."""
        from integrations.mastermind_executive_app.os_transport import (
            principal_scope_from_identity,
        )
        return principal_scope_from_identity(
            issuer_digest=self._issuer_digest,
            subject_digest=self._subject_digest,
            client_ref=self.CLIENT_REF)
