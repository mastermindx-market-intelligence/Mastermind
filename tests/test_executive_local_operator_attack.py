"""Independent adversarial reproductions for the L4 Unix-socket door.

Each test asserts the SAFE behavior; a real finding is a failing test.
All sockets are fresh short paths under /tmp (the l4root fixture). No live
Executive service, no TCP port, no real subject or token is touched.
"""
import asyncio
import json
import logging
import os
import socket
import stat

import pytest

from integrations.executive_mcp.local_operator import (
    LocalOperatorApp,
    LocalOperatorAuthenticator,
    LocalOperatorBindError,
    LocalOperatorConfig,
    LocalOperatorListener,
)

FAKE_SUBJECT = "l4-attack-made-up-subject-20261110"  # not a real principal
FAKE_OTHER = "l4-attack-other-made-up-subject"
GET_REQ = b"GET /workspace/programs/current HTTP/1.0\r\nHost: x\r\n\r\n"
POST_CTX = (b"POST /os/executive/context HTTP/1.0\r\nHost: x\r\n"
            b"Content-Length: 2\r\n\r\n{}")


@pytest.fixture
def l4root(short_socket_root):
    return short_socket_root / "l4a"


def _config(root, name="x.sock", **kw):
    return LocalOperatorConfig(
        socket_path=root / name,
        allowed_uids=(os.getuid(),),
        operator_subject=kw.pop("subject", FAKE_SUBJECT), **kw)


class RecordingApp:
    def __init__(self, body=b'{"ok":true}'):
        self.scopes = []
        self.bodies = []
        self._body = body

    async def __call__(self, scope, receive, send):
        self.scopes.append(scope)
        while True:
            message = await receive()
            if message["type"] != "http.request":
                break
            self.bodies.append(message.get("body", b""))
            if not message.get("more_body", False):
                break
        await send({"type": "http.response.start", "status": 200,
                    "headers": [(b"content-type", b"application/json")]})
        await send({"type": "http.response.body", "body": self._body})


class RaisingApp:
    def __init__(self):
        self.calls = 0

    async def __call__(self, scope, receive, send):
        self.calls += 1
        raise RuntimeError("boom " + FAKE_SUBJECT)


def _run(listener, client, timeout=15):
    async def main():
        server = asyncio.create_task(listener.serve_forever())
        try:
            return await asyncio.wait_for(client(), timeout)
        finally:
            listener.stop()
            server.cancel()
            await asyncio.gather(server, return_exceptions=True)
    return asyncio.run(main())


async def _connect(loop, path):
    conn = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    conn.connect(str(path))
    conn.setblocking(False)
    return conn


async def _roundtrip(loop, path, wire, *, read_until_close=True):
    conn = await _connect(loop, path)
    try:
        chunks = []
        try:
            await loop.sock_sendall(conn, wire)
        except OSError:
            return b""  # the door closed mid-send: a refusal with no response
        while True:
            try:
                data = await asyncio.wait_for(loop.sock_recv(conn, 65536), 5)
            except ConnectionError:
                break
            if not data:
                break
            chunks.append(data)
            if not read_until_close:
                break
        return b"".join(chunks)
    finally:
        conn.close()


def _fd_count():
    return len(os.listdir("/dev/fd"))


# P1 ---------------------------------------------------------------- raising app

def test_p1_raising_app_answers_500_and_recovers(l4root):
    """A raising app must yield a clean 500; closing clients frees every task/fd."""
    app = RaisingApp()
    listener = LocalOperatorListener(_config(l4root), app)
    listener.bind()
    fds_before = _fd_count()

    async def client():
        loop = asyncio.get_running_loop()
        raws = []
        for _ in range(50):
            raw = await _roundtrip(loop, l4root / "x.sock", POST_CTX)
            head = raw.split(b"\r\n", 1)[0]
            assert head.startswith(b"HTTP/1.1 500"), raw
            assert b"operator_app_failed" in raw
            raws.append(raw)
        await asyncio.sleep(0.2)  # let done-callbacks run
        assert not listener._tasks, f"{len(listener._tasks)} leaked connection tasks"
        return raws

    raws = _run(listener, client)
    assert app.calls == 50
    assert _fd_count() <= fds_before + 2, "file descriptors leaked"
    for raw in raws:
        assert FAKE_SUBJECT.encode() not in raw  # exception text never on the wire


# P2 ---------------------------------------------------------------- idle connections

def test_p2_idle_connections_do_not_starve_service(l4root):
    """100 silent connections must not block a 101st request (no accept starvation)."""
    app = RecordingApp()
    listener = LocalOperatorListener(_config(l4root), app)
    listener.bind()

    async def client():
        loop = asyncio.get_running_loop()
        idle = [await _connect(loop, l4root / "x.sock") for _ in range(100)]
        try:
            raw = await asyncio.wait_for(
                _roundtrip(loop, l4root / "x.sock", GET_REQ), 5)
            assert raw.split(b"\r\n", 1)[0].startswith(b"HTTP/1.1 200"), raw[:80]
        finally:
            for conn in idle:
                conn.close()

    _run(listener, client)


def test_p2_idle_connection_is_closed_by_connection_timeout(l4root):
    """An idle connection is bounded by the connection timeout (not infinite)."""
    listener = LocalOperatorListener(_config(l4root), RecordingApp())
    listener._CONNECTION_TIMEOUT = 0.3  # instance override; source untouched
    listener.bind()

    async def client():
        loop = asyncio.get_running_loop()
        conn = await _connect(loop, l4root / "x.sock")
        try:
            data = await asyncio.wait_for(loop.sock_recv(conn, 65536), 5)
            assert data == b"", f"idle connection not closed: {data!r}"
        finally:
            conn.close()
        await asyncio.sleep(0.2)
        assert not listener._tasks

    _run(listener, client)


# P3 ---------------------------------------------------------------- slow body

def test_p3_slow_body_is_bounded_by_connection_timeout(l4root):
    """Headers promising 10 bytes, then silence: bounded, then server still serves."""
    app = RecordingApp()
    listener = LocalOperatorListener(_config(l4root), app)
    listener._CONNECTION_TIMEOUT = 0.3
    listener.bind()

    async def client():
        loop = asyncio.get_running_loop()
        conn = await _connect(loop, l4root / "x.sock")
        try:
            await loop.sock_sendall(
                conn, b"POST /os/executive/context HTTP/1.0\r\nHost: x\r\n"
                      b"Content-Length: 10\r\n\r\n{")
            data = await asyncio.wait_for(loop.sock_recv(conn, 65536), 5)
            assert data == b"", "stalled body held the connection open"
        finally:
            conn.close()
        raw = await _roundtrip(loop, l4root / "x.sock", GET_REQ)
        assert raw.split(b"\r\n", 1)[0].startswith(b"HTTP/1.1 200")

    _run(listener, client)
    assert app.scopes and app.scopes[-1]["method"] == "GET"
    assert not any(s["method"] == "POST" for s in app.scopes)  # stalled POST never dispatched


# P4 ---------------------------------------------------------------- oversized inputs

def test_p4_oversized_header_block_is_refused(l4root):
    """A header block far beyond one read: closed, no response, app never called.

    Measured 2026-11-10: h11's 16 KiB cap applies to an INCOMPLETE event, so a
    20 KB block that arrives inside one 64 KiB read is parsed and answered. The
    bound that holds is one read plus 16 KiB; 200 KB must be refused.
    """
    app = RecordingApp()
    listener = LocalOperatorListener(_config(l4root), app)
    listener.bind()

    async def client():
        loop = asyncio.get_running_loop()
        wire = (b"GET /workspace/programs/current HTTP/1.0\r\nHost: x\r\n"
                b"X-Pad: " + b"a" * 200000 + b"\r\n\r\n")
        raw = await _roundtrip(loop, l4root / "x.sock", wire)
        assert raw == b"", f"oversized headers got a response: {raw[:80]}"
        raw2 = await _roundtrip(loop, l4root / "x.sock", GET_REQ)
        assert raw2.split(b"\r\n", 1)[0].startswith(b"HTTP/1.1 200")

    _run(listener, client)
    assert len(app.scopes) == 1  # only the follow-up request


def test_p4_oversized_body_is_refused_and_server_survives(l4root):
    """A body beyond the 16 MiB cap: no dispatch, no response, server keeps serving."""
    app = RecordingApp()
    listener = LocalOperatorListener(_config(l4root), app)
    listener.bind()

    async def client():
        loop = asyncio.get_running_loop()
        conn = await _connect(loop, l4root / "x.sock")

        async def sender():
            try:
                await loop.sock_sendall(
                    conn, b"POST /os/executive/context HTTP/1.0\r\nHost: x\r\n"
                          b"Transfer-Encoding: chunked\r\n\r\n")
                chunk = b"10000\r\n" + b"b" * 65536 + b"\r\n"
                for _ in range(260):  # ~17 MB
                    await loop.sock_sendall(conn, chunk)
            except OSError:
                pass

        send_task = asyncio.ensure_future(sender())
        chunks = []
        try:
            while True:
                data = await asyncio.wait_for(loop.sock_recv(conn, 65536), 10)
                if not data:
                    break
                chunks.append(data)
        finally:
            send_task.cancel()
            conn.close()
        assert b"".join(chunks) == b"", "oversized body got a response"
        raw = await _roundtrip(loop, l4root / "x.sock", GET_REQ)
        assert raw.split(b"\r\n", 1)[0].startswith(b"HTTP/1.1 200")

    _run(listener, client, timeout=60)
    assert [scope["method"] for scope in app.scopes] == ["GET"]  # follow-up only


async def _sender():  # pragma: no cover - helper placeholder
    return None


def _identity(x):  # pragma: no cover - helper placeholder
    return x


# P5 ---------------------------------------------------------------- framing confusion

def test_p5_conflicting_content_lengths_refused_before_app(l4root):
    """Two different Content-Length values: h11 refuses; app sees nothing."""
    app = RecordingApp()
    listener = LocalOperatorListener(_config(l4root), app)
    listener.bind()

    async def client():
        loop = asyncio.get_running_loop()
        wire = (b"POST /os/executive/context HTTP/1.0\r\nHost: x\r\n"
                b"Content-Length: 1\r\nContent-Length: 2\r\n\r\n{}")
        raw = await _roundtrip(loop, l4root / "x.sock", wire)
        assert raw == b"", f"conflicting CL got a response: {raw[:80]}"

    _run(listener, client)
    assert app.scopes == []  # refused before dispatch, not merely answered empty


def test_p5_te_plus_content_length_single_parser(l4root):
    """CL+TE together: one parser, TE wins; no second parser to smuggle through."""
    app = RecordingApp()
    listener = LocalOperatorListener(_config(l4root), app)
    listener.bind()

    async def client():
        loop = asyncio.get_running_loop()
        wire = (b"POST /os/executive/context HTTP/1.0\r\nHost: x\r\n"
                b"Content-Length: 50\r\nTransfer-Encoding: chunked\r\n\r\n"
                b"5\r\nhello\r\n0\r\n\r\n")
        raw = await _roundtrip(loop, l4root / "x.sock", wire)
        assert raw.split(b"\r\n", 1)[0].startswith(b"HTTP/1.1 200"), raw[:80]

    _run(listener, client)
    assert app.bodies == [b"hello"]  # dechunked; CL=50 never delivered trailing bytes


# P6 ---------------------------------------------------------------- header-borne identity

def test_p6_identity_headers_do_not_change_attribution(l4root):
    """Authorization / X-Forwarded-For / subject headers never change the principal."""
    config = _config(l4root)
    app = LocalOperatorApp(LocalOperatorAuthenticator(config))
    listener = LocalOperatorListener(config, app)
    listener.bind()

    async def client():
        loop = asyncio.get_running_loop()
        plain = await _roundtrip(loop, l4root / "x.sock", POST_CTX)
        forged = await _roundtrip(loop, l4root / "x.sock",
            b"POST /os/executive/context HTTP/1.0\r\nHost: x\r\n"
            b"Authorization: Bearer forged-token-value\r\n"
            b"X-Forwarded-For: 127.0.0.1\r\n"
            b"X-Operator-Subject: " + FAKE_OTHER.encode() + b"\r\n"
            b"Content-Length: 2\r\n\r\n{}")
        return plain, forged

    plain, forged = _run(listener, client)
    for raw in (plain, forged):
        assert raw.split(b"\r\n", 1)[0].startswith(b"HTTP/1.1 200")
        assert FAKE_SUBJECT.encode() not in raw
        assert FAKE_OTHER.encode() not in raw
    scope_p = json.loads(plain.split(b"\r\n\r\n", 1)[1])["principal_scope"]
    scope_f = json.loads(forged.split(b"\r\n\r\n", 1)[1])["principal_scope"]
    assert scope_p == scope_f


# P7 ---------------------------------------------------------------- peer uid check

@pytest.mark.parametrize("reader", [
    pytest.param(lambda conn: (_ for _ in ()).throw(OSError(57, "not connected")),
                 id="raises"),
    pytest.param(lambda conn: 999999, id="wrong-uid"),
    pytest.param(lambda conn: str(os.getuid()), id="string-uid"),
    pytest.param(lambda conn: None, id="none"),
])
def test_p7_peer_uid_failure_refuses_before_any_byte(l4root, reader):
    """A failed/foreign peer-uid result: closed before parsing, app never called."""
    app = RecordingApp()
    listener = LocalOperatorListener(_config(l4root), app, peer_uid_reader=reader)
    listener.bind()

    async def client():
        loop = asyncio.get_running_loop()
        raw = await _roundtrip(loop, l4root / "x.sock", POST_CTX)
        assert raw == b"", f"unadmitted peer got bytes: {raw[:80]}"

    _run(listener, client)
    assert app.scopes == []


# P8 ---------------------------------------------------------------- bind path safety

def test_p8_bind_refuses_symlink_and_preserves_target(l4root):
    """A symlink at the socket path (to nothing, or to a live socket) is refused."""
    l4root.mkdir(parents=True)
    dangling = l4root / "dangling.sock"
    dangling.symlink_to(l4root / "nonexistent-target")
    listener = LocalOperatorListener(_config(l4root, "dangling.sock"), RecordingApp())
    with pytest.raises(LocalOperatorBindError):
        listener.bind()
    assert dangling.is_symlink()  # never unlinked

    live_target = l4root / "live.sock"
    raw_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    raw_sock.bind(str(live_target))
    raw_sock.listen(1)
    link = l4root / "link.sock"
    link.symlink_to(live_target)
    listener2 = LocalOperatorListener(_config(l4root, "link.sock"), RecordingApp())
    try:
        with pytest.raises(LocalOperatorBindError):
            listener2.bind()
    finally:
        raw_sock.close()
    assert link.is_symlink() and stat.S_ISSOCK(os.lstat(live_target).st_mode)


def test_p8_bind_refuses_regular_file(l4root):
    """An attacker-planted regular file at the path: refused, content preserved."""
    l4root.mkdir(parents=True)
    planted = l4root / "planted.sock"
    planted.write_bytes(b"attacker-content")
    listener = LocalOperatorListener(_config(l4root, "planted.sock"), RecordingApp())
    with pytest.raises(LocalOperatorBindError):
        listener.bind()
    assert planted.read_bytes() == b"attacker-content"


def test_p8_socket_mode_exact_under_restrictive_umask(l4root):
    """Explicit chmod defeats umask: requested mode lands exactly, before serving."""
    for mode in (0o666, 0o660):
        old = os.umask(0o077)
        try:
            listener = LocalOperatorListener(
                _config(l4root, f"m{mode:o}.sock"), RecordingApp(), mode=mode)
            listener.bind()
            try:
                got = stat.S_IMODE(os.lstat(l4root / f"m{mode:o}.sock").st_mode)
                assert got == mode, f"umask leaked into socket mode: {got:o}"
            finally:
                listener.stop()
        finally:
            os.umask(old)


# P9 ---------------------------------------------------------------- subject in logs

def test_p9_subject_never_reaches_logs_or_error_bodies(l4root, caplog):
    """DEBUG logging during requests + a raising app: the subject appears nowhere."""
    config = _config(l4root)
    app = RaisingApp()
    listener = LocalOperatorListener(config, app)
    listener.bind()

    async def client():
        loop = asyncio.get_running_loop()
        return await _roundtrip(loop, l4root / "x.sock",
            b"POST /os/executive/context HTTP/1.0\r\nHost: x\r\n"
            b"X-Operator-Subject: " + FAKE_SUBJECT.encode() + b"\r\n"
            b"Content-Length: 2\r\n\r\n{}")

    with caplog.at_level(logging.DEBUG):
        raw = _run(listener, client)
    assert raw.split(b"\r\n", 1)[0].startswith(b"HTTP/1.1 500")
    assert FAKE_SUBJECT.encode() not in raw
    assert FAKE_SUBJECT not in caplog.text


# P10 --------------------------------------------------------------- TCP app unchanged

from tests import test_mastermind_os_executive_transport as _os_fixture  # noqa: E402

rsa_key = _os_fixture.rsa_key  # the existing signed-token fixture, reused

def test_p10_tcp_app_refusals_identical_with_listener_bound(
        rsa_key, tmp_path, short_socket_root):
    """Binding the socket door must not change the TCP app's refusal behavior."""
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
    tcp_app = os_fixture._v3_app(settings)

    forged = [
        (b"host", b"mcp.mastermind-x.com"),
        (b"content-type", b"application/json"),
        (b"x-forwarded-for", b"127.0.0.1"),
        (b"x-local-operator", b"1"),
    ]

    def drive():
        events = []

        async def send(event):
            events.append(event)

        async def receive():
            return {"type": "http.request", "body": b"{}", "more_body": False}

        asyncio.run(tcp_app({
            "type": "http", "asgi": {"version": "3.0", "spec_version": "2.3"},
            "http_version": "1.1", "scheme": "https", "method": "POST",
            "path": "/os/executive/context", "raw_path": b"/os/executive/context",
            "query_string": b"", "headers": forged,
            "client": ("127.0.0.1", 9000), "server": ("127.0.0.1", 9001),
        }, receive, send))
        return events

    before = drive()
    config = LocalOperatorConfig(
        socket_path=short_socket_root / "l4a" / "x.sock",
        allowed_uids=(os.getuid(),), operator_subject=FAKE_SUBJECT)
    listener = LocalOperatorListener(config, RecordingApp())
    listener.bind()
    try:
        after = drive()
    finally:
        listener.stop()
    assert [e.get("status") for e in before if e["type"] == "http.response.start"] == \
           [e.get("status") for e in after if e["type"] == "http.response.start"]
    assert [e.get("body") for e in before if e["type"] == "http.response.body"] == \
           [e.get("body") for e in after if e["type"] == "http.response.body"]
