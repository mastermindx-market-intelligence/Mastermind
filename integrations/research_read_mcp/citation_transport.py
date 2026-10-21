"""Restricted prebound Unix citation transport for the existing Research process.

Import is inert. Production adopts one systemd-owned UNIX descriptor and binds
only the incumbent loopback TCP address. It never creates/chmods/unlinks a Unix
socket or expands service writable paths. No forwarded header supplies context.
"""
from __future__ import annotations

from dataclasses import dataclass
from contextlib import contextmanager
import signal
import threading
import inspect
import os
from pathlib import Path
import re
import socket
import stat

from .evidence_http import EvidenceHttpApp, ORIGIN, PREFIX

CITATION_SOCKET = "/run/mastermind-research/citation.sock"
ACTIVATION_NAME = "research-citation"
MCP_ADDRESS = ("127.0.0.1", 8767)
_ITEM_PATH = re.compile(re.escape(PREFIX) + r"rvitem\.v1\.[0-9a-f]{64}\Z")
_DENIAL = b'{"error":"ITEM_UNAVAILABLE"}'
_DENIAL_HEADERS = [(b"content-type", b"application/json"), (b"cache-control", b"no-store"),
                   (b"vary", b"Accept"), (b"x-robots-tag", b"noindex, nofollow"),
                   (b"content-length", str(len(_DENIAL)).encode())]


class TransportRefused(ValueError):
    def __init__(self):
        super().__init__("CITATION_TRANSPORT_REFUSED")


def _refuse():
    raise TransportRefused() from None


def _identity(info):
    return info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid, info.st_nlink


def _directory_identity(info):
    # Unrelated child directories change a parent's link count. Retain the
    # stable identity and permission fields, while socket links stay strict.
    return info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid


@dataclass(frozen=True, slots=True)
class UnixSocketPolicy:
    """Trusted composition input. Fixtures use their own directory UID explicitly."""
    path: str
    directory_uid: int
    socket_uid: int
    socket_gid: int

    @classmethod
    def production(cls, caddy_uid, caddy_gid):
        if (type(caddy_uid) is not int or caddy_uid <= 0
                or type(caddy_gid) is not int or caddy_gid <= 0):
            _refuse()
        return cls(CITATION_SOCKET, 0, caddy_uid, caddy_gid)

    def snapshot(self):
        try:
            if (type(self.path) is not str or not self.path.isascii()
                    or not 0 < len(self.path.encode()) <= 100
                    or any(type(value) is not int or value < 0 for value in
                           (self.directory_uid, self.socket_uid, self.socket_gid))):
                _refuse()
            path = Path(self.path)
            if (not path.is_absolute() or str(path) != self.path
                    or ".." in path.parts or "\\" in self.path or "\x00" in self.path):
                _refuse()
            chain = []
            for parent in path.parents:
                info = parent.lstat()
                if (not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode)
                        or info.st_uid not in {0, self.directory_uid} or info.st_mode & 0o022):
                    _refuse()
                if parent == path.parent and info.st_uid != self.directory_uid:
                    _refuse()
                chain.append((str(parent), _directory_identity(info)))
            info = path.lstat()
            if (not stat.S_ISSOCK(info.st_mode) or info.st_uid != self.socket_uid
                    or info.st_gid != self.socket_gid or stat.S_IMODE(info.st_mode) != 0o600
                    or info.st_nlink != 1):
                _refuse()
            return _identity(info), tuple(chain)
        except Exception:
            _refuse()


def _is_listening(value):
    # Linux deployment predicate. Unsupported kernels refuse; no production
    # connection-probe fallback or listen() mutation exists.
    return value.getsockopt(socket.SOL_SOCKET, socket.SO_ACCEPTCONN) == 1


def _socket_identity(value):
    if type(value) is not socket.socket or value.fileno() < 0:
        _refuse()
    if value.getsockopt(socket.SOL_SOCKET, socket.SO_TYPE) != socket.SOCK_STREAM:
        _refuse()
    if not _is_listening(value):
        _refuse()
    info = os.fstat(value.fileno())
    if not stat.S_ISSOCK(info.st_mode):
        _refuse()
    return value.family, value.getsockname(), _identity(info)


class ListenerBundle:
    """Own exactly two qualified descriptors; never remove a socket filename."""
    def __init__(self, tcp, unix, *, policy, tcp_address=MCP_ADDRESS):
        self.tcp, self.unix, self.policy, self.tcp_address = tcp, unix, policy, tcp_address
        try:
            if (type(policy) is not UnixSocketPolicy or type(tcp_address) is not tuple
                    or len(tcp_address) != 2 or tcp_address[0] != "127.0.0.1"
                    or type(tcp_address[1]) is not int or not 1 <= tcp_address[1] <= 65535
                    or tcp is unix):
                _refuse()
            self._tcp = _socket_identity(tcp)
            self._unix = _socket_identity(unix)
            if (self._tcp[:2] != (socket.AF_INET, tcp_address)
                    or self._unix[:2] != (socket.AF_UNIX, policy.path)):
                _refuse()
            self._path = policy.snapshot()
            self.verify()
        except Exception:
            _refuse()

    def verify(self):
        try:
            if (_socket_identity(self.tcp) != self._tcp or _socket_identity(self.unix) != self._unix
                    or self.policy.snapshot() != self._path):
                _refuse()
        except Exception:
            _refuse()

    def sockets(self):
        self.verify()
        return [self.tcp, self.unix]

    def close(self):
        # Idempotent descriptor close only; systemd owns filesystem lifecycle.
        self.tcp.close()
        self.unix.close()


def adopt_systemd_unix(policy, *, environment=None, first_fd=3):
    """Adopt only the expected socket-activation descriptor; no bind or fallback.

    Labels are necessary but insufficient: the actual descriptor, secure parent
    chain, path/owner/mode and listening state are independently qualified.
    first_fd is an explicit fixture seam; production calls use systemd's fd 3.
    """
    environment = os.environ if environment is None else environment
    duplicate = None
    duplicate_fd = None
    try:
        if (type(policy) is not UnixSocketPolicy or type(first_fd) is not int or first_fd < 3
                or environment.get("LISTEN_PID") != str(os.getpid())
                or environment.get("LISTEN_FDS") != "1"
                or environment.get("LISTEN_FDNAMES") != ACTIVATION_NAME):
            _refuse()
        before = policy.snapshot()
        duplicate_fd = os.dup(first_fd)
        duplicate = socket.socket(fileno=duplicate_fd)
        duplicate_fd = None  # The socket object now owns this acquired copy.
        observed = _socket_identity(duplicate)
        if observed[:2] != (socket.AF_UNIX, policy.path) or policy.snapshot() != before:
            _refuse()
        duplicate.set_inheritable(False)
        # Only after proof: relinquish the original activated descriptor. No
        # unknown/invalid ambient descriptor is closed on a refusal.
        os.close(first_fd)
        return duplicate
    except Exception:
        if duplicate is not None:
            duplicate.close()
        elif duplicate_fd is not None:
            os.close(duplicate_fd)
        _refuse()


def acquire_listeners(policy, *, environment=None, tcp_address=MCP_ADDRESS):
    """Production acquisition: same existing TCP endpoint plus activated Unix."""
    tcp = unix = None
    try:
        if tcp_address != MCP_ADDRESS:
            _refuse()
        unix = adopt_systemd_unix(policy, environment=environment)
        tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        tcp.set_inheritable(False)
        tcp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        tcp.bind(tcp_address)
        tcp.listen(socket.SOMAXCONN)
        return ListenerBundle(tcp, unix, policy=policy, tcp_address=tcp_address)
    except Exception:
        if tcp is not None:
            tcp.close()
        if unix is not None:
            unix.close()
        _refuse()


def _citation_scope(scope):
    try:
        path = scope.get("path")
        if (scope.get("type") != "http" or scope.get("method") != "GET"
                or type(path) is not str or _ITEM_PATH.fullmatch(path) is None
                or scope.get("raw_path") != path.encode("ascii")
                or scope.get("query_string") != b"" or scope.get("root_path", "") != ""
                or scope.get("scheme") != "http"):
            return None
        headers = {}
        for name, value in scope.get("headers", ()):
            if type(name) is not bytes or type(value) is not bytes:
                return None
            key = name.lower()
            if (key == b"forwarded" or key.startswith(b"x-forwarded-")
                    or key in {b"x-real-ip", b"cf-connecting-ip", b"eo-connecting-ip", b"eo-client-ip"}):
                return None
            if key in {b"host", b"accept", b"origin", b"authorization", b"content-length", b"transfer-encoding"}:
                if key in headers:
                    return None
                headers[key] = value
        if (headers.get(b"host") != b"mcp.mastermind-x.com"
                or headers.get(b"accept") != b"application/json"
                or headers.get(b"origin", ORIGIN.encode()) != ORIGIN.encode()
                or headers.get(b"content-length", b"0") != b"0"
                or b"transfer-encoding" in headers):
            return None
        qualified = dict(scope)
        qualified.update(scheme="https", server=("mcp.mastermind-x.com", 443))
        return qualified
    except Exception:
        return None


class CitationDispatcher:
    def __init__(self, *, mcp_app, citation_app, listeners):
        if (not callable(mcp_app) or not callable(citation_app) or type(listeners) is not ListenerBundle):
            _refuse()
        listeners.verify()
        self.mcp_app, self.citation_app, self.listeners = mcp_app, citation_app, listeners

    async def __call__(self, scope, receive, send):
        if scope.get("type") == "lifespan":
            # One root application owns the one server's lifecycle.
            await self.mcp_app(scope, receive, send)
            return
        qualified = None
        try:
            self.listeners.verify()
            if scope.get("type") == "http" and scope.get("server") == self.listeners.tcp_address:
                await self.mcp_app(scope, receive, send)
                return
            if scope.get("server") == (self.listeners.policy.path, None):
                qualified = _citation_scope(scope)
        except TransportRefused:
            pass
        if qualified is not None:
            await self.citation_app(qualified, receive, send)
            return
        if scope.get("type") == "websocket":
            await send({"type": "websocket.close", "code": 1008})
            return
        await send({"type": "http.response.start", "status": 404, "headers": _DENIAL_HEADERS})
        await send({"type": "http.response.body", "body": _DENIAL})


@dataclass(frozen=True, slots=True)
class RuntimeBindings:
    """References retained by the original factories, never another auth owner."""
    service: object
    adapter: object
    authenticator: object
    grant_owner: object
    clock: object
    audit_sink: object


def build_citation_consumer(policy, bindings):
    if type(bindings) is not RuntimeBindings or getattr(bindings.adapter, "service", None) is not bindings.service:
        _refuse()
    # Required future adapter seam must use the incumbent limiter and actual
    # F10 context. No replacement executor or unresolved-item implementation.
    resolver = getattr(bindings.adapter, "resolve_evidence_item", None)
    if (not callable(getattr(bindings.service, "resolve_evidence_item", None))
            or not inspect.iscoroutinefunction(resolver)):
        _refuse()
    try:
        return EvidenceHttpApp(policy=policy, authenticator=bindings.authenticator,
            grant_owner=bindings.grant_owner, context_builder=bindings.adapter.context_builder,
            item_resolver=resolver, clock=bindings.clock, audit_sink=bindings.audit_sink)
    except Exception:
        _refuse()


def _draining_server_type():
    import uvicorn
    if uvicorn.__version__ != "0.52.4":
        _refuse()
    class DrainingServer(uvicorn.Server):
        # Qualified against Uvicorn 0.52.4 capture_signals/handle_exit source.
        # One server owns the same handlers while running. Do not re-raise a
        # completed stop signal before the outer durable audit owner can close.
        @contextmanager
        def capture_signals(self):
            if threading.current_thread() is not threading.main_thread():
                raise TransportRefused()
            previous = {}
            try:
                for signum in (signal.SIGINT, signal.SIGTERM):
                    previous[signum] = signal.signal(signum, self.handle_exit)
                yield
            finally:
                for signum, handler in previous.items():
                    signal.signal(signum, handler)
    return DrainingServer


def run_mcp_server(*, app, host, port, server_factory=None):
    """Preserve the single loopback route and let its audit owner close on stop."""
    import uvicorn
    from .runtime import _LOOPBACK
    if type(host) is not str or host not in _LOOPBACK or type(port) is not int or not 1 <= port <= 65535:
        _refuse()
    config = uvicorn.Config(app, host=host, port=port, loop="asyncio", http="h11",
        lifespan="on", proxy_headers=False, access_log=False, log_level="warning", workers=1)
    server = (server_factory or _draining_server_type())(config)
    server.run()
    if not server.started:
        _refuse()


def run_dual_server(*, mcp_app, citation_app, listeners, server_factory=None):
    """One public Server.run owns signals, draining and lifespan; audit stays open.

    A completed graceful stop returns normally (exit status 0 at the launcher),
    after restoring signal handlers, so the caller can close its audit owner.
    Caller closes its one audit owner only after this function returns. Uvicorn's
    synchronous run closes its event loop/default executor before returning.
    """
    try:
        import uvicorn
        dispatch = CitationDispatcher(mcp_app=mcp_app, citation_app=citation_app, listeners=listeners)
        config = uvicorn.Config(dispatch, host=MCP_ADDRESS[0], port=MCP_ADDRESS[1],
            loop="asyncio", http="h11", lifespan="on", proxy_headers=False,
            access_log=False, log_level="warning", workers=1)
        server = (server_factory or _draining_server_type())(config)
        server.run(sockets=listeners.sockets())
        if not server.started:
            _refuse()
    finally:
        listeners.close()
