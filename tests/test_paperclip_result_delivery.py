"""``paperclip_task`` result-return transport (MMOS lane T4b, build item 2).

A real stdlib ``http.server`` on an ephemeral 127.0.0.1 port stands in for the
dev Paperclip instance; every request it receives is captured.  The payload is
a REAL ``mastermind.execution_return/v1`` record produced by the projector, so
the transport is proven against the fields the seam actually hands it.

Covered: delivered receipt shape (comment + document), exactly-once on retry,
a transient mid-flight failure that refuses honestly and does not double-post,
the non-loopback construction refusal, the registry's existing unknown-kind
law, and the no-secrets rule for bodies and headers.
"""
from __future__ import annotations

import asyncio
import json
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import pytest

from control_plane.execution_return_projection import project_execution_return
from control_plane.paperclip_result_delivery import (
    PAPERCLIP_ORIGIN_KIND,
    PAPERCLIP_RETURN_MARKER_PREFIX,
    PaperclipResultDeliveryTransport,
    build_return_comment,
)
from control_plane.result_delivery import (
    OriginRef,
    ResultDeliveryRegistry,
    UnknownOriginKindError,
)

ISSUE = "iss-1"
ATTEMPT = "ATT-1"
BRANCH = "t3/mmos-t4b-job-abc12345"
DEV_HEADERS = {"x-instance-role": "local_trusted"}


# --- the fake Paperclip instance -------------------------------------------


class FakePaperclip:
    """Loopback HTTP stand-in: issues, comments and documents endpoints."""

    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []
        self.comments: dict[str, list[dict[str, Any]]] = {}
        self.documents: dict[tuple[str, str], dict[str, Any]] = {}
        self.fail_next_comment_post = False
        self._lock = threading.Lock()
        outer = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *args: Any) -> None:  # silence the test log
                return

            def do_GET(self) -> None:
                outer._handle(self, "GET")

            def do_POST(self) -> None:
                outer._handle(self, "POST")

            def do_PUT(self) -> None:
                outer._handle(self, "PUT")

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.server.server_address[1]
        self.base_url = f"http://127.0.0.1:{self.port}"
        self._thread = threading.Thread(
            target=self.server.serve_forever, daemon=True)
        self._thread.start()

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()

    # -- request handling ---------------------------------------------------

    def _handle(self, handler: BaseHTTPRequestHandler, method: str) -> None:
        length = int(handler.headers.get("content-length") or 0)
        raw = handler.rfile.read(length) if length else b""
        path = urllib.parse.urlsplit(handler.path).path
        with self._lock:
            self.requests.append({
                "method": method,
                "path": path,
                "headers": {k.lower(): v for k, v in handler.headers.items()},
                "body": raw,
            })
            fail = method == "POST" and path.endswith("/comments") \
                and self.fail_next_comment_post
            if fail:
                self.fail_next_comment_post = False
        if fail:
            # A transient mid-flight failure: the connection dies with no
            # response, exactly what a restarting dev instance looks like.
            handler.close_connection = True
            handler.connection.close()
            return
        segments = [part for part in path.split("/") if part]
        # /api/issues/<issue>/comments
        if len(segments) == 4 and segments[:2] == ["api", "issues"] \
                and segments[3] == "comments":
            issue = segments[2]
            if method == "GET":
                with self._lock:
                    rows = list(self.comments.get(issue, []))
                self._send(handler, 200, {"comments": rows})
                return
            if method == "POST":
                body = json.loads(raw or b"{}")
                with self._lock:
                    rows = self.comments.setdefault(issue, [])
                    row = {"id": f"cmt-{len(rows) + 1}",
                           "body": body.get("body", "")}
                    rows.append(row)
                self._send(handler, 201, row)
                return
        # /api/issues/<issue>/documents/<key>
        if len(segments) == 5 and segments[:2] == ["api", "issues"] \
                and segments[3] == "documents":
            issue, key = segments[2], segments[4]
            if method == "GET":
                with self._lock:
                    document = self.documents.get((issue, key))
                if document is None:
                    self._send(handler, 404, {"error": "not_found"})
                else:
                    self._send(handler, 200, document)
                return
            if method == "PUT":
                body = json.loads(raw or b"{}")
                with self._lock:
                    self.documents[(issue, key)] = body
                self._send(handler, 200, {"key": key})
                return
        self._send(handler, 404, {"error": "not_found"})

    @staticmethod
    def _send(handler: BaseHTTPRequestHandler, status: int, payload: Any) -> None:
        raw = json.dumps(payload).encode("utf-8")
        handler.send_response(status)
        handler.send_header("content-type", "application/json")
        handler.send_header("content-length", str(len(raw)))
        handler.end_headers()
        handler.wfile.write(raw)

    # -- assertions helpers -------------------------------------------------

    def comment_posts(self) -> list[dict[str, Any]]:
        return [row for row in self.requests
                if row["method"] == "POST" and row["path"].endswith("/comments")]

    def document_puts(self) -> list[dict[str, Any]]:
        return [row for row in self.requests
                if row["method"] == "PUT" and "/documents/" in row["path"]]


@pytest.fixture()
def paperclip():
    fake = FakePaperclip()
    try:
        yield fake
    finally:
        fake.close()


# --- the real payload the seam hands the transport -------------------------


def _record() -> dict[str, Any]:
    """A real projected ``execution_return/v1`` record (branch_pushed)."""
    return project_execution_return({
        "original_requester": {
            "teammate_id": "paperclip-agent:ag-1",
            "conversation_id": f"paperclip-issue:{ISSUE}",
            "project_id": "paperclip-company:co-1",
            "authenticated_namespace": "t3-mastermind//principal-e2e",
        },
        "attempt": {
            "attempt_id": ATTEMPT,
            "root_id": f"roots/paperclip-{ISSUE}",
            "idempotency_key": "child-request:abc123",
            "authenticated_namespace": "t3-mastermind//principal-e2e",
            "t3_thread_id": "th-1",
            "t3_run_id": "run-1",
            "seal": {"schema": "mastermind terminal seal", "digest": "a" * 64},
        },
        "result": {
            "text": f"pushed branch {BRANCH}",
            "artifact_refs": [f"branch:{BRANCH}"],
            "acceptance": "not_accepted",
            "installation_claimed": False,
        },
        "github": {
            "branch": BRANCH, "pr_number": None, "pr_url": None,
            "checks": None, "merge_state": "unknown",
        },
    })


def _origin(ids: dict[str, str] | None = None) -> OriginRef:
    """The origin the wiring builds: the requester block's string fields."""
    return OriginRef(
        kind=PAPERCLIP_ORIGIN_KIND,
        ids=ids if ids is not None else {
            "teammate_id": "paperclip-agent:ag-1",
            "conversation_id": f"paperclip-issue:{ISSUE}",
            "project_id": "paperclip-company:co-1",
            "carrier_kind": PAPERCLIP_ORIGIN_KIND,
        },
    )


def _transport(paperclip: FakePaperclip, tmp_path, **kwargs: Any
               ) -> PaperclipResultDeliveryTransport:
    return PaperclipResultDeliveryTransport(
        base_url=paperclip.base_url, headers=DEV_HEADERS,
        state_dir=tmp_path, **kwargs)


def _deliver(transport: PaperclipResultDeliveryTransport,
             origin: OriginRef | None = None,
             payload: dict[str, Any] | None = None) -> dict[str, Any]:
    return asyncio.run(transport.deliver(
        origin or _origin(), payload if payload is not None else _record()))


# --- 1. delivered receipt shape --------------------------------------------


def test_delivered_receipt_posts_comment_with_identity_and_writes_document(
        paperclip, tmp_path):
    receipt = _deliver(_transport(paperclip, tmp_path))

    assert receipt["state"] == "delivered"
    assert receipt["schema"] == "mastermind.execution_return_delivery/v1"
    assert receipt["return_id"].startswith("execret-")
    assert receipt["return_digest"] == _record()["digest"]
    assert f"paperclip:issue:{ISSUE}" in receipt["transport_ref"]
    assert "document:" in receipt["transport_ref"]

    posts = paperclip.comment_posts()
    assert len(posts) == 1
    body = json.loads(posts[0]["body"])["body"]
    assert f"{PAPERCLIP_RETURN_MARKER_PREFIX} {ATTEMPT}" in body
    assert ATTEMPT in body                       # attempt id
    assert f"roots/paperclip-{ISSUE}" in body    # root id
    assert "child-request:abc123" in body        # idempotency key
    assert "th-1" in body and "run-1" in body    # t3 thread / run
    assert BRANCH in body                        # branch evidence
    assert "branch_pushed" in body               # the proven stage
    assert "not_accepted" in body                # delivery is not acceptance

    puts = paperclip.document_puts()
    assert len(puts) == 1
    document = json.loads(puts[0]["body"])
    assert document["format"] == "markdown"
    assert f"{PAPERCLIP_RETURN_MARKER_PREFIX} {ATTEMPT}" in document["body"]
    assert _record()["digest"] in document["body"]  # the full record is carried


def test_comment_body_never_invents_unobserved_github_evidence():
    body = build_return_comment(_record(), ATTEMPT)
    assert "pr: #" not in body
    assert "checks: green" not in body
    assert "merge: merged" not in body
    assert "no GitHub evidence observed" not in body  # a branch WAS observed
    assert f"branch: `{BRANCH}`" in body


# --- 2. exactly-once --------------------------------------------------------


def test_second_delivery_of_the_same_attempt_posts_nothing_new(paperclip, tmp_path):
    transport = _transport(paperclip, tmp_path)
    first = _deliver(transport)
    second = _deliver(transport)

    assert first["state"] == "delivered"
    assert second["state"] == "delivered"
    assert second.get("note") == "already-delivered"
    assert len(paperclip.comment_posts()) == 1, "exactly one comment POST, ever"
    assert len(paperclip.document_puts()) == 1, "exactly one document PUT, ever"
    assert len(paperclip.comments[ISSUE]) == 1


def test_a_fresh_transport_dedupes_from_the_issue_comments(paperclip, tmp_path):
    """The sidecar is the fast path; the issue's own comments are the
    authority — a new process with an empty state dir still posts once."""
    _deliver(_transport(paperclip, tmp_path))
    fresh = _transport(paperclip, tmp_path / "other-state")
    receipt = _deliver(fresh)
    assert receipt["state"] == "delivered"
    assert receipt.get("note") == "already-delivered"
    assert len(paperclip.comment_posts()) == 1


# --- 3. transient failure ---------------------------------------------------


def test_transient_failure_refuses_honestly_and_never_double_posts(
        paperclip, tmp_path):
    transport = _transport(paperclip, tmp_path)
    paperclip.fail_next_comment_post = True

    refused = _deliver(transport)
    assert refused["state"] == "refused"
    assert refused["refusal_code"] == "COMMENT_POST_FAILED"
    assert "unreachable" in refused["reason"] or "HTTP" in refused["reason"]
    assert paperclip.comments.get(ISSUE, []) == []

    delivered = _deliver(transport)
    assert delivered["state"] == "delivered"
    assert len(paperclip.comments[ISSUE]) == 1, "one successful comment only"
    assert len(paperclip.document_puts()) == 1


def test_document_failure_after_the_comment_refuses_without_reposting(
        paperclip, tmp_path):
    transport = _transport(paperclip, tmp_path)
    # The document endpoint is unreachable: the comment already landed.
    original = paperclip._handle

    def broken(handler, method):
        if method == "PUT":
            handler.close_connection = True
            handler.connection.close()
            return
        original(handler, method)

    paperclip._handle = broken  # type: ignore[method-assign]
    refused = _deliver(transport)
    assert refused["state"] == "refused"
    assert refused["refusal_code"] == "DOCUMENT_WRITE_FAILED"
    assert len(paperclip.comments[ISSUE]) == 1

    paperclip._handle = original  # type: ignore[method-assign]
    delivered = _deliver(transport)
    assert delivered["state"] == "delivered"
    assert len(paperclip.comments[ISSUE]) == 1, "the comment is not re-posted"
    assert len(paperclip.document_puts()) == 1


# --- 4. the dev-loopback law ------------------------------------------------


@pytest.mark.parametrize("base", [
    "http://10.0.0.5:3190",
    "http://192.168.1.20:3190",
    "https://paperclip.example.com",
    "http://127.0.0.1.evil.example:3190",
])
def test_non_loopback_base_url_is_refused_at_construction(base, tmp_path):
    with pytest.raises(ValueError, match="non-loopback"):
        PaperclipResultDeliveryTransport(
            base_url=base, headers=DEV_HEADERS, state_dir=tmp_path)


@pytest.mark.parametrize("base", [
    "http://127.0.0.1:3190", "http://localhost:3190", "http://[::1]:3190",
])
def test_loopback_bases_construct(base, tmp_path):
    PaperclipResultDeliveryTransport(
        base_url=base, headers=DEV_HEADERS, state_dir=tmp_path)


# --- 5. the registry's existing unknown-kind law ----------------------------


def test_registry_without_this_transport_refuses_the_kind():
    registry = ResultDeliveryRegistry()
    with pytest.raises(UnknownOriginKindError) as caught:
        registry.lookup(PAPERCLIP_ORIGIN_KIND)
    assert caught.value.kind == PAPERCLIP_ORIGIN_KIND
    assert registry.has(PAPERCLIP_ORIGIN_KIND) is False


def test_registry_routes_the_kind_once_registered(paperclip, tmp_path):
    registry = ResultDeliveryRegistry()
    registry.register(PAPERCLIP_ORIGIN_KIND, _transport(paperclip, tmp_path))
    receipt = asyncio.run(
        registry.lookup(PAPERCLIP_ORIGIN_KIND).deliver(_origin(), _record()))
    assert receipt["state"] == "delivered"
    assert len(paperclip.comments[ISSUE]) == 1


# --- honest refusals --------------------------------------------------------


def test_origin_without_an_issue_refuses_and_posts_nothing(paperclip, tmp_path):
    receipt = _deliver(
        _transport(paperclip, tmp_path),
        origin=_origin({"teammate_id": "paperclip-agent:ag-1"}))
    assert receipt["state"] == "refused"
    assert receipt["refusal_code"] == "ORIGIN_ISSUE_MISSING"
    assert paperclip.requests == []


def test_origin_naming_the_issue_directly_is_accepted(paperclip, tmp_path):
    receipt = _deliver(
        _transport(paperclip, tmp_path), origin=_origin({"issue": ISSUE}))
    assert receipt["state"] == "delivered"
    assert len(paperclip.comments[ISSUE]) == 1


def test_payload_without_an_attempt_id_refuses(paperclip, tmp_path):
    payload = _record()
    payload["attempt"] = {k: v for k, v in payload["attempt"].items()
                          if k != "attempt_id"}
    receipt = _deliver(_transport(paperclip, tmp_path), payload=payload)
    assert receipt["state"] == "refused"
    assert receipt["refusal_code"] == "ATTEMPT_ID_MISSING"
    assert paperclip.requests == []


def test_wrong_origin_kind_refuses(paperclip, tmp_path):
    receipt = _deliver(
        _transport(paperclip, tmp_path),
        origin=OriginRef(kind="hermes_conversation", ids={"issue": ISSUE}))
    assert receipt["state"] == "refused"
    assert receipt["refusal_code"] == "ORIGIN_KIND_MISMATCH"


# --- 6. no secrets ----------------------------------------------------------


def test_no_token_material_in_bodies_or_headers(paperclip, tmp_path):
    _deliver(_transport(paperclip, tmp_path))
    assert paperclip.requests, "the fake server saw the delivery"
    for row in paperclip.requests:
        headers = row["headers"]
        # The configured dev header is the ONLY auth material sent.
        assert headers.get("x-instance-role") == "local_trusted"
        assert "authorization" not in headers
        assert "cookie" not in headers
        text = row["body"].decode("utf-8", "replace")
        assert "local_trusted" not in text
        assert "Bearer" not in text
        assert "authorization" not in text.lower()
        assert "x-instance-role" not in text
