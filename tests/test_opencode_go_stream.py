"""Single-account wire proof. All keys, responses and admissions are synthetic."""
import json
import threading
import traceback
from dataclasses import replace

import pytest

from control_plane import opencode_go_stream as wire
from control_plane.opencode_go_pooled_transport import (
    AccountChoice, OpenCodeGoEffectUnknown, OpenCodeGoTransportContractError,
    ProviderRequest,
)

CHOICE = AccountChoice("go", "a" * 64, "account-a")
SECRET = "synthetic-private-key"
DONE = b"data: [DONE]\n\n"
DELTA = b'data: {"choices":[{"delta":{"content":"hello"}}]}\n\n'


def request(path="chat/completions", **extra):
    value = {"model": "glm-5.3-flash", "stream": True,
             "messages": [{"role": "user", "content": "synthetic context"}]}
    value.update(extra)
    return ProviderRequest(path, "same-session", {"Content-Type": "application/json"},
                           json.dumps(value).encode())


class Response:
    def __init__(self, chunks=(), status=200, headers=None):
        self.status = status
        self.chunks = list(chunks)
        self.headers = headers or [("Content-Type", "text/event-stream")]
        self.closed = False
        self.fail_close = False
        self.on_read = lambda: None

    def getheaders(self):
        return self.headers

    def read1(self, _size):
        self.on_read()
        if not self.chunks:
            return b""
        value = self.chunks.pop(0)
        if isinstance(value, Exception):
            raise value
        return value

    def close(self):
        self.closed = True
        if self.fail_close:
            raise OSError(SECRET)


class Connection:
    def __init__(self, response):
        self.response = response
        self.sent = []
        self.closed = False
        self.sock = None
        self.fail_request = None

    def request(self, method, path, **kwargs):
        self.sent.append((method, path, kwargs))
        if self.fail_request:
            raise self.fail_request

    def getresponse(self):
        return self.response

    def close(self):
        self.closed = True


def run(response, *, req=None, check=lambda _r: None, key=None, sink=None, **kwargs):
    conn = Connection(response)
    calls, chunks = [], []

    def connect(host, **options):
        calls.append((host, options))
        return conn

    receipt = wire.stream_single_account(
        req or request(), choice=CHOICE,
        credential_loader=key or (lambda _a: SECRET), request_check=check,
        on_chunk=sink or chunks.append, connection_factory=connect, **kwargs)
    return receipt, conn, calls, chunks


def test_success_streams_raw_bytes_and_preserves_session_body_headers():
    req = request()
    response = Response([DELTA, DONE])
    checks = []
    receipt, conn, calls, chunks = run(response, req=req, check=lambda r: checks.append(r))
    assert chunks == [DELTA, DONE]
    assert receipt.terminal_observed and receipt.bytes_forwarded == len(DELTA + DONE)
    assert len(conn.sent) == len(calls) == 1
    assert calls[0][0] == "opencode.ai"
    method, path, data = conn.sent[0]
    assert method == "POST" and path == "/zen/go/v1/chat/completions"
    assert data["body"] == req.body
    assert data["headers"]["x-opencode-session"] == req.session_id
    assert data["headers"]["Authorization"] == "Bearer " + SECRET
    assert len(checks) == 2 and checks[0] is checks[1]
    assert conn.closed and response.closed
    assert SECRET not in repr(receipt)


@pytest.mark.parametrize("path, ending", [
    ("messages", b'event: message_stop\ndata: {"type":"message_stop"}\n\n'),
    ("responses", b'event: response.completed\ndata: {"type":"response.completed","response":{"status":"completed"}}\n\n'),
])
def test_protocol_specific_terminal_events(path, ending):
    receipt, *_ = run(Response([ending]), req=request(path))
    assert receipt.terminal_observed


@pytest.mark.parametrize("separator", [b"\n", b"\r\n", b"\r"])
def test_every_byte_chunk_boundary_and_line_endings(separator):
    data = DELTA.replace(b"\n", separator) + DONE.replace(b"\n", separator)
    # CR needs a following byte to disambiguate CRLF; add a harmless comment.
    if separator == b"\r":
        data += b":"
    receipt, _, _, chunks = run(Response([bytes([b]) for b in data]))
    assert receipt.terminal_observed
    assert b"".join(chunks).startswith(DELTA.replace(b"\n", separator))


@pytest.mark.parametrize("status", [301, 401, 403, 429, 500, 503])
def test_any_http_failure_is_one_account_one_request_no_retry(status):
    response = Response([b'{"error":"synthetic refusal"}'], status,
                        [("content-type", "application/json"), ("set-cookie", SECRET), ("retry-after", "60")])
    receipt, conn, calls, chunks = run(response)
    assert len(calls) == len(conn.sent) == 1 and not chunks
    assert not receipt.terminal_observed and receipt.error_response.status == status
    assert "set-cookie" not in receipt.error_response.headers
    assert receipt.error_response.headers["retry-after"] == "60"
    assert SECRET not in repr(receipt)


def test_missing_or_failed_offer_check_never_reads_key_or_connects():
    touched = []
    for check in (None, lambda r: (_ for _ in ()).throw(ValueError(SECRET)), lambda r: True):
        with pytest.raises(OpenCodeGoTransportContractError):
            wire.stream_single_account(request(), choice=CHOICE, request_check=check,
                credential_loader=lambda a: touched.append("key"), on_chunk=lambda b: None,
                connection_factory=lambda *a, **k: touched.append("connect"))
    assert touched == []


def test_evidence_expiring_during_key_load_blocks_post_and_closes_connection():
    response = Response([DONE])
    conn = Connection(response)
    count = [0]

    def guard(_r):
        count[0] += 1
        if count[0] == 2:
            raise ValueError("offer expired")

    with pytest.raises(OpenCodeGoTransportContractError, match="evidence refused"):
        wire.stream_single_account(request(), choice=CHOICE, request_check=guard,
            credential_loader=lambda a: SECRET, on_chunk=lambda b: None,
            connection_factory=lambda *a, **k: conn)
    assert not conn.sent and conn.closed


@pytest.mark.parametrize("chunks", [[], [DELTA], [DELTA, TimeoutError(SECRET)],
    [b'event: error\ndata: {"type":"error"}\n\n'], [b'data: invalid-json\n\n'],
    [b'data: {"error": {"message":"failure"}}\n\n']])
def test_eof_partial_and_error_streams_never_become_success(chunks):
    response = Response(chunks)
    with pytest.raises(OpenCodeGoEffectUnknown) as exc:
        run(response)
    assert exc.value.attempted_accounts == ("account-a",)
    assert response.closed
    assert SECRET not in "".join(traceback.format_exception(exc.type, exc.value, exc.tb))


def test_sink_failure_after_provider_effect_is_not_a_pre_effect_refusal():
    def sink(_):
        raise OpenCodeGoTransportContractError(SECRET)
    with pytest.raises(OpenCodeGoEffectUnknown):
        run(Response([DELTA, DONE]), sink=sink)


def test_cancel_before_submission_never_loads_credential():
    cancelled = threading.Event(); cancelled.set()
    touched = []
    with pytest.raises(OpenCodeGoTransportContractError, match="before submission"):
        run(Response([DONE]), cancel=cancelled, key=lambda a: touched.append(a))
    assert touched == []


def test_cancel_during_read_does_not_forward_pending_chunk_or_retry():
    cancelled = threading.Event()
    response = Response([DELTA, DONE]); response.on_read = cancelled.set
    chunks = []
    with pytest.raises(wire.OpenCodeGoStreamCancelled):
        run(response, cancel=cancelled, sink=chunks.append)
    assert not chunks and response.closed


def test_total_deadline_checks_read_progress_not_just_idle_timeout():
    clock = [0.0]
    response = Response([DELTA] * 10 + [DONE])
    response.on_read = lambda: clock.__setitem__(0, clock[0] + 0.6)
    with pytest.raises(OpenCodeGoEffectUnknown):
        run(response, monotonic=lambda: clock[0], total_timeout_seconds=1.0)
    assert response.closed


@pytest.mark.parametrize("kw", [{"idle_timeout_seconds": float("nan")},
    {"total_timeout_seconds": float("inf")}, {"idle_timeout_seconds": True},
    {"total_timeout_seconds": 0}, {"cancel": object()}])
def test_invalid_execution_limits_refuse_before_io(kw):
    with pytest.raises(OpenCodeGoTransportContractError):
        run(Response([DONE]), **kw)


@pytest.mark.parametrize("extra", [{"stream": False}, {"stream": 1}, {"background": True}])
def test_only_foreground_stream_mode(extra):
    with pytest.raises(OpenCodeGoTransportContractError):
        run(Response([DONE]), req=request(**extra))


def test_success_is_not_reported_when_cleanup_fails():
    response = Response([DONE]); response.fail_close = True
    with pytest.raises(OpenCodeGoEffectUnknown):
        run(response)


def test_response_type_must_be_stream():
    with pytest.raises(OpenCodeGoEffectUnknown):
        run(Response([DONE], headers=[("content-type", "application/json")]))


def test_event_size_and_error_response_bounds(monkeypatch):
    monkeypatch.setattr(wire, "MAX_EVENT_BYTES", 32)
    with pytest.raises(OpenCodeGoEffectUnknown):
        run(Response([b"data: " + b"x" * 40]))
    monkeypatch.setattr(wire, "MAX_ERROR_BYTES", 32)
    with pytest.raises(OpenCodeGoEffectUnknown):
        run(Response([b"x" * 40], status=429))


def test_request_exception_is_effect_unknown_and_connection_is_closed():
    conn = Connection(Response([])); conn.fail_request = OSError(SECRET)
    with pytest.raises(OpenCodeGoEffectUnknown):
        wire.stream_single_account(request(), choice=CHOICE,
            credential_loader=lambda a: SECRET, request_check=lambda r: None,
            on_chunk=lambda b: None, connection_factory=lambda *a, **kw: conn)
    assert len(conn.sent) == 1 and conn.closed


def test_bare_cr_terminal_at_end_of_stream():
    receipt, *_ = run(Response([DONE.replace(b"\n", b"\r")]))
    assert receipt.terminal_observed


def test_unterminated_terminal_line_does_not_count_as_completion():
    with pytest.raises(OpenCodeGoEffectUnknown):
        run(Response([b"data: [DONE]"]))


def test_real_loopback_http_stream_delivers_before_terminal_without_buffering():
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    import http.client
    delivered = threading.Event()
    received = []
    failures = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            received.append((self.path, self.rfile.read(int(self.headers["Content-Length"]))))
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            self.wfile.write(DELTA); self.wfile.flush()
            if not delivered.wait(2):
                failures.append("first chunk was buffered")
            self.wfile.write(DONE); self.wfile.flush()

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    chunks = []

    def sink(chunk):
        chunks.append(chunk)
        delivered.set()

    def test_connection(host, timeout):
        assert host == "opencode.ai"
        return http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=timeout)

    try:
        req = request()
        receipt = wire.stream_single_account(req, choice=CHOICE,
            credential_loader=lambda a: SECRET, request_check=lambda r: None,
            on_chunk=sink, connection_factory=test_connection, total_timeout_seconds=5)
        assert receipt.terminal_observed and not failures
        assert b"".join(chunks) == DELTA + DONE
        assert received == [("/zen/go/v1/chat/completions", req.body)]
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=2)
    assert not thread.is_alive()
