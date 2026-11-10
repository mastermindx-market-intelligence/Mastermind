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
import os
import socket
import stat
from pathlib import Path

from integrations.executive_mcp.local_operator import (
    LocalOperatorBindError,
    LocalOperatorConfig,
    LocalOperatorListener,
)


def _config(tmp_path):
    return LocalOperatorConfig(
        socket_path=tmp_path / "l4.sock",
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


def test_socket_created_connectable_and_removed_on_stop(tmp_path):
    """(7) bind creates the socket (connectable mode); stop removes it."""
    listener = LocalOperatorListener(_config(tmp_path), RecordingApp())
    listener.bind()
    path = tmp_path / "l4.sock"
    assert stat.S_ISSOCK(os.lstat(str(path)).st_mode)
    assert os.stat(path).st_mode & 0o777 in (0o660, 0o666)  # amendment (b)
    listener.stop()
    assert not os.path.lexists(path)


def test_live_listener_at_bind_is_refused_stale_replaced(tmp_path):
    """(6) a live listener keeps its socket; a stale file is replaced."""
    incumbent = LocalOperatorListener(_config(tmp_path), RecordingApp())
    incumbent.bind()
    try:
        with pytest.raises(LocalOperatorBindError):
            LocalOperatorListener(_config(tmp_path), RecordingApp()).bind()
    finally:
        incumbent.stop()
    # Stale leftover: a bound-then-closed socket file nobody answers.
    leftover = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    leftover.bind(str(tmp_path / "l4.sock"))
    leftover.close()
    replacement = LocalOperatorListener(_config(tmp_path), RecordingApp())
    replacement.bind()  # unlinks the stale file, binds fresh
    replacement.stop()


def test_disallowed_peer_uid_refused_before_any_request(tmp_path):
    """(2) peer uid outside allowed_uids: connection refused, app never sees it."""
    app = RecordingApp()
    listener = LocalOperatorListener(
        _config(tmp_path), app, peer_uid_reader=lambda conn: 424242)
    listener.bind()

    async def client():
        loop = asyncio.get_running_loop()
        conn = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        conn.connect(str(tmp_path / "l4.sock"))
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


def test_real_same_uid_socket_serves_request(tmp_path):
    """(2, positive) a real same-uid connection is admitted and served."""
    app = RecordingApp()
    listener = LocalOperatorListener(_config(tmp_path), app)  # real getpeereid
    listener.bind()

    async def client():
        loop = asyncio.get_running_loop()
        conn = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        conn.connect(str(tmp_path / "l4.sock"))
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
