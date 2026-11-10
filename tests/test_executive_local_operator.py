"""Local operator mode (L4): off-by-default and fail-closed config gates.

The public tunnel reaches this gateway over loopback TCP, so loopback or
headers never carry admission; the socket door exists only when the installed
config block parses, and admission is the kernel peer uid.
"""
import pytest

from integrations.executive_mcp.local_operator import (
    LocalOperatorConfigError,
    parse_local_operator_config,
)

FAKE_SUBJECT = "test-local-operator-000"


def _block(**updates):
    value = {
        "socket_path": "/tmp/local-operator-test.sock",
        "allowed_uids": [501],
        "operator_subject": FAKE_SUBJECT,
    }
    value.update(updates)
    return value


def test_absent_block_keeps_mode_off():
    """(1) No block in config: parse returns None; no socket may be created."""
    assert parse_local_operator_config(None) is None


@pytest.mark.parametrize(
    "block",
    [
        _block(socket_path="relative/path.sock"),          # relative path
        _block(socket_path=""),                            # empty path
        _block(socket_path=b"/tmp/bytes.sock"),            # wrong type
        _block(socket_path="/tmp/a\0b.sock"),              # NUL byte
        _block(allowed_uids=[]),                           # empty uid list
        _block(allowed_uids=[501, 501]),                   # duplicate uids
        _block(allowed_uids=[501, True]),                  # bool is not an int uid
        _block(allowed_uids=[-2]),                         # negative uid
        _block(allowed_uids="501"),                        # wrong type
        _block(operator_subject=""),                       # empty subject
        _block(operator_subject=" padded "),               # padded subject
        _block(operator_subject="line\nbreak"),            # control character
        _block(operator_subject="x" * 129),                # oversized subject
        {"socket_path": "/tmp/s.sock", "allowed_uids": [1]},  # missing key
        _block(extra_key=1),                               # unexpected key
        ["socket_path", "/tmp/s.sock"],                    # not a mapping
    ],
)
def test_malformed_blocks_fail_closed(block):
    """(5) Every malformed row raises: no socket may be created."""
    with pytest.raises(LocalOperatorConfigError):
        parse_local_operator_config(block)


def test_well_formed_block_parses():
    parsed = parse_local_operator_config(_block(allowed_uids=[501, 0]))
    assert parsed.socket_path.as_posix() == "/tmp/local-operator-test.sock"
    assert parsed.allowed_uids == (501, 0)  # order preserved; membership only
    assert parsed.operator_subject == FAKE_SUBJECT


# --------------------------------------------------------------------------
# listener: admission is the kernel peer uid, never headers or file mode


import asyncio
import json
import os
import socket
import stat
from pathlib import Path

from integrations.executive_mcp.local_operator import (
    LocalOperatorBindError,
    LocalOperatorConfig,
    LocalOperatorListener,
)


def _config(l4root):
    return LocalOperatorConfig(
        socket_path=l4root / "l4.sock",
        allowed_uids=(os.getuid(),),
        operator_subject=FAKE_SUBJECT,
    )


class RecordingApp:
    def __init__(self):
        self.scopes = []

    async def __call__(self, scope, receive, send):
        self.scopes.append(scope)
        await send({"type": "http.response.start", "status": 200,
                    "headers": [(b"content-type", b"application/json")]})
        await send({"type": "http.response.body", "body": b'{"ok":true}'})


def _http_request(path):
    # HTTP/1.0: the listener closes after one response.
    return (f"POST {path} HTTP/1.0\r\nHost: mcp.mastermind-x.com\r\n"
            "Content-Type: application/json\r\nContent-Length: 2\r\n\r\n{}").encode()


def _run_with_listener(listener, client):
    async def main():
        server = asyncio.create_task(listener.serve_forever())
        try:
            return await asyncio.wait_for(client(), 10)
        finally:
            listener.stop()
            server.cancel()
            await asyncio.gather(server, return_exceptions=True)
    return asyncio.run(main())


@pytest.fixture
def l4root(short_socket_root):
    # pytest's nested tmp_path can exceed Darwin's 104-byte AF_UNIX budget;
    # the repo's short root keeps every socket path test-owned and short.
    return short_socket_root / "l4"


def test_socket_created_connectable_and_removed_on_stop(l4root):
    """(7) bind creates the socket (connectable mode); stop removes it."""
    listener = LocalOperatorListener(_config(l4root), RecordingApp())
    listener.bind()
    path = l4root / "l4.sock"
    assert stat.S_ISSOCK(os.lstat(str(path)).st_mode)
    assert os.stat(path).st_mode & 0o777 in (0o660, 0o666)  # amendment (b)
    listener.stop()
    assert not os.path.lexists(path)


def test_live_listener_at_bind_is_refused_stale_replaced(l4root):
    """(6) a live listener keeps its socket; a stale file is replaced."""
    incumbent = LocalOperatorListener(_config(l4root), RecordingApp())
    incumbent.bind()
    try:
        with pytest.raises(LocalOperatorBindError):
            LocalOperatorListener(_config(l4root), RecordingApp()).bind()
    finally:
        incumbent.stop()
    # Stale leftover: a bound-then-closed socket file nobody answers.
    leftover = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    leftover.bind(str(l4root / "l4.sock"))
    leftover.close()
    replacement = LocalOperatorListener(_config(l4root), RecordingApp())
    replacement.bind()  # unlinks the stale file, binds fresh
    replacement.stop()


def test_disallowed_peer_uid_refused_before_any_request(l4root):
    """(2) peer uid outside allowed_uids: connection refused, app never sees it."""
    app = RecordingApp()
    listener = LocalOperatorListener(
        _config(l4root), app, peer_uid_reader=lambda conn: 424242)
    listener.bind()

    async def client():
        loop = asyncio.get_running_loop()
        conn = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        conn.connect(str(l4root / "l4.sock"))
        conn.setblocking(False)  # asyncio sock_* multiplexes; never block the loop
        await loop.sock_sendall(conn, _http_request("/os/executive/context"))
        chunks = []
        while True:
            data = await loop.sock_recv(conn, 65536)
            if not data:
                break
            chunks.append(data)
        conn.close()
        return b"".join(chunks)

    assert _run_with_listener(listener, client) == b""
    assert app.scopes == []


def test_real_same_uid_socket_serves_request(l4root):
    """(2, positive) a real same-uid connection is admitted and served."""
    app = RecordingApp()
    listener = LocalOperatorListener(_config(l4root), app)  # real getpeereid
    listener.bind()

    async def client():
        loop = asyncio.get_running_loop()
        conn = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        conn.connect(str(l4root / "l4.sock"))
        conn.setblocking(False)  # asyncio sock_* multiplexes; never block the loop
        await loop.sock_sendall(conn, _http_request("/os/executive/context"))
        chunks = []
        while True:
            data = await loop.sock_recv(conn, 65536)
            if not data:
                break
            chunks.append(data)
        conn.close()
        return b"".join(chunks)

    response = _run_with_listener(listener, client)
    assert b"HTTP/1." in response and b"200" in response.split(b"\r\n", 1)[0]
    assert b'{"ok":true}' in response
    assert len(app.scopes) == 1


def test_operator_authenticator_attributes_by_digest_only():
    """(a) the operator principal carries the subject as a digest, never raw."""
    import hashlib
    from integrations.executive_mcp.local_operator import LocalOperatorAuthenticator

    clock = [1_800_000_000]
    auth = LocalOperatorAuthenticator(
        LocalOperatorConfig(socket_path=Path("/tmp/x.sock"), allowed_uids=(501,),
                            operator_subject=FAKE_SUBJECT),
        now=lambda: clock[0])
    principal = auth.principal()
    assert principal.subject_digest == hashlib.sha256(FAKE_SUBJECT.encode()).hexdigest()
    assert FAKE_SUBJECT not in repr(principal) and FAKE_SUBJECT not in str(principal)
    assert principal.issued_at == 1_800_000_000
    assert principal.expires_at - principal.issued_at == 60
    scope = auth.principal_scope()
    assert isinstance(scope, str) and scope and FAKE_SUBJECT not in scope
    assert scope == auth.principal_scope()  # deterministic: digest-derived only


# --------------------------------------------------------------------------
# (3) the admitted uid reads OS + workspace routes over the socket, no bearer


def _socket_config(l4root):
    from integrations.executive_mcp.local_operator import parse_local_operator_config
    return parse_local_operator_config({
        "socket_path": str(l4root / "l4.sock"),
        "allowed_uids": [os.getuid()],
        "operator_subject": FAKE_SUBJECT,
    })


def _response_json(raw: bytes):
    head, _, payload = raw.partition(b"\r\n\r\n")
    return head.split(b"\r\n", 1)[0], __import__("json").loads(payload)


def test_allowed_uid_reads_os_and_workspace_routes_no_bearer(l4root):
    """(3) same real uid: OS context + workspace read, attributed, no bearer."""
    from types import SimpleNamespace
    from integrations.executive_mcp.local_operator import LocalOperatorAuthenticator
    from integrations.executive_mcp.server import build_local_operator_mcp_app

    config = _socket_config(l4root)
    seen = []

    def provider(principal):
        seen.append(principal.subject_digest)
        return {"schema": "mastermind.workspace.programs.v1", "programs": []}

    app = build_local_operator_mcp_app(
        SimpleNamespace(read_from_ceo_ingress=True),
        local_operator_config=config, workspace_programs=provider)
    listener = LocalOperatorListener(config, app)
    listener.bind()

    async def journey():
        loop = asyncio.get_running_loop()
        responses = []
        for method, path, body in (
            ("POST", "/os/executive/context", b"{}"),
            ("GET", "/workspace/programs/current", b""),
        ):
            conn = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            conn.connect(str(l4root / "l4.sock"))
            conn.setblocking(False)
            request = (f"{method} {path} HTTP/1.0\r\nHost: mcp.mastermind-x.com\r\n"
                       f"Content-Length: {len(body)}\r\n\r\n").encode() + body
            await loop.sock_sendall(conn, request)
            chunks = []
            while True:
                data = await loop.sock_recv(conn, 65536)
                if not data:
                    break
                chunks.append(data)
            conn.close()
            responses.append(b"".join(chunks))
        return responses

    raw_os, raw_ws = _run_with_listener(listener, journey)
    status, payload = _response_json(raw_os)
    assert status.startswith(b"HTTP/1.1 200")
    assert payload["schema"] == "mastermind.os.executive.owner_context.v1"
    assert payload["principal_scope"] == LocalOperatorAuthenticator(config).principal_scope()
    assert FAKE_SUBJECT.encode() not in raw_os  # digest only, never the subject

    raw = raw_ws
    status, payload = _response_json(raw)
    assert status.startswith(b"HTTP/1.1 200")
    assert FAKE_SUBJECT.encode() not in raw
    assert payload["programs"] == []
    assert payload["principal_scope"] == LocalOperatorAuthenticator(config).principal_scope()
    assert seen and seen[0] == LocalOperatorAuthenticator(config).subject_digest


# --------------------------------------------------------------------------
# (4) TCP with forged loopback/forwarded/invented local-operator headers

from tests import test_mastermind_os_executive_transport as _os_fixture

rsa_key = _os_fixture.rsa_key  # the existing signed-token fixture, reused


def test_tcp_forged_headers_get_exactly_todays_refusal(rsa_key, tmp_path, short_socket_root):
    """(4) No header can open or influence the TCP path; refusals are exact."""
    import dataclasses
    from tests import test_mastermind_os_executive_transport as os_fixture

    mastermind = tmp_path / "mastermind"
    macro = tmp_path / "macro"
    os_fixture.fixture._git_repo(mastermind)
    (macro / "scripts").mkdir(parents=True)
    (macro / "scripts" / "agentos.py").write_text("")
    (macro / "agentos").mkdir()
    (macro / "agentos" / ".keep").write_text("")
    os_fixture.fixture._git_repo(macro)
    base = os_fixture.fixture._real_app_settings(
        rsa_key, mastermind_root=mastermind, macro_root=macro,
        ceo_ingress_socket_path=short_socket_root / "ceo-ingress.sock")
    settings = dataclasses.replace(base, read_from_ceo_ingress=True)
    app = os_fixture._v3_app(settings)  # the real TCP app object

    def drive(headers):
        events = []

        async def send(event):
            events.append(event)

        async def receive():
            return {"type": "http.request", "body": b"{}", "more_body": False}

        asyncio.run(app({
            "type": "http", "asgi": {"version": "3.0", "spec_version": "2.3"},
            "http_version": "1.1", "scheme": "https", "method": "POST",
            "path": "/os/executive/context", "raw_path": b"/os/executive/context",
            "query_string": b"", "headers": headers,
            "client": ("127.0.0.1", 9000), "server": ("127.0.0.1", 9001),
        }, receive, send))
        return events

    forged = [
        (b"host", b"mcp.mastermind-x.com"),
        (b"content-type", b"application/json"),
        (b"x-forwarded-for", b"127.0.0.1"),
        (b"x-local-operator", b"1"),
        (b"x-mastermind-local-operator", b"admit"),
    ]
    events = drive(forged)  # no authorization at all
    start = events[0]
    body = json.loads(b"".join(e.get("body", b"") for e in events[1:]))
    assert start["status"] == 403
    assert body == {"ok": False, "error": {"code": "transport_refused",
                                           "message": "fixed OS transport refused"}}

    events = drive(forged + [(b"authorization", b"Bearer forged.token.value")])
    start = events[0]
    body = json.loads(b"".join(e.get("body", b"") for e in events[1:]))
    assert start["status"] == 401
    assert body == {"ok": False, "error": {"code": "authentication_required",
                                           "message": "authentication required"}}
    assert (b"www-authenticate", b"Bearer") in [tuple(h) for h in start["headers"]]


# --------------------------------------------------------------------------
# the principal's three h11-loop concerns: 100-continue, chunked body,
# and an app that raises mid-response


class BodyEchoApp:
    def __init__(self):
        self.bodies = []

    async def __call__(self, scope, receive, send):
        body = bytearray()
        while True:
            message = await receive()
            if message["type"] != "http.request":
                break
            body += message.get("body", b"")
            if not message.get("more_body", False):
                break
        self.bodies.append(bytes(body))
        await send({"type": "http.response.start", "status": 200,
                    "headers": [(b"content-type", b"text/plain")]})
        await send({"type": "http.response.body", "body": b"echoed"})


def _socket_roundtrip(l4root, listener, drive):
    async def client():
        loop = asyncio.get_running_loop()
        conn = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        conn.connect(str(l4root / "l4.sock"))
        conn.setblocking(False)
        result = await drive(conn, loop)
        conn.close()
        return result
    return _run_with_listener(listener, client)


async def _read_until(conn, loop, needle):
    chunks = []
    while needle not in b"".join(chunks):
        data = await asyncio.wait_for(loop.sock_recv(conn, 65536), 5)
        if not data:
            break
        chunks.append(data)
    return b"".join(chunks)


def test_chunked_request_body_is_dechunked(l4root):
    """(h11-B) chunked framing decodes; the app sees the dechunked body."""
    app = BodyEchoApp()
    listener = LocalOperatorListener(_config(l4root), app)
    listener.bind()

    async def drive(conn, loop):
        request = (b"POST /os/executive/context HTTP/1.1\r\nHost: x\r\n"
                   b"Transfer-Encoding: chunked\r\n\r\n"
                   b"5\r\nhello\r\n3\r\nabc\r\n0\r\n\r\n")
        await loop.sock_sendall(conn, request)
        return await _read_until(conn, loop, b"echoed")

    raw = _socket_roundtrip(l4root, listener, drive)
    assert raw.startswith(b"HTTP/1.1 200")
    assert app.bodies == [b"helloabc"]


def test_expect_100_continue_gets_interim_response(l4root):
    """(h11-A) Expect: 100-continue must not stall to the 300s timeout."""
    app = BodyEchoApp()
    listener = LocalOperatorListener(_config(l4root), app)
    listener.bind()

    async def drive(conn, loop):
        head = (b"POST /os/executive/context HTTP/1.1\r\nHost: x\r\n"
                b"Expect: 100-continue\r\nContent-Length: 5\r\n\r\n")
        await loop.sock_sendall(conn, head)
        interim = await asyncio.wait_for(loop.sock_recv(conn, 65536), 5)
        # h11 emits an empty reason phrase on the interim line, like the 200.
        assert interim.split(b"\r\n", 1)[0].startswith(b"HTTP/1.1 100")
        await loop.sock_sendall(conn, b"hello")
        return interim + await _read_until(conn, loop, b"echoed")

    raw = _socket_roundtrip(l4root, listener, drive)
    assert b"HTTP/1.1 100" in raw and b"echoed" in raw
    assert app.bodies == [b"hello"]


class CrashingApp:
    async def __call__(self, scope, receive, send):
        await send({"type": "http.response.start", "status": 200,
                    "headers": [(b"content-type", b"text/plain")]})
        await send({"type": "http.response.body", "body": b"partial"})
        raise RuntimeError("operator app exploded")


def test_app_raising_mid_response_gets_clean_500(l4root):
    """(h11-C) an app crash mid-response yields a clean 500, not a hang."""
    listener = LocalOperatorListener(_config(l4root), CrashingApp())
    listener.bind()

    async def drive(conn, loop):
        await loop.sock_sendall(conn, _http_request("/os/executive/context"))
        chunks = []
        while True:
            data = await asyncio.wait_for(loop.sock_recv(conn, 65536), 5)
            if not data:
                break
            chunks.append(data)
        return b"".join(chunks)

    raw = _socket_roundtrip(l4root, listener, drive)
    assert raw.startswith(b"HTTP/1.1 500")
    assert b"operator_app_failed" in raw
