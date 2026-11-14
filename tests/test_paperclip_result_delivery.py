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
import uuid
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
# PF-3 item 1: the delivery writer is a dedicated service agent, never the
# board.  The fake instance stamps its posts with this agent attribution.
SERVICE_AGENT = "ag-pf-delivery"


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
                # the real Paperclip API requires a UUID clientRequestId
                # (invalid_format 400 otherwise — hit live on 2026-11-10)
                try:
                    uuid.UUID(str(body.get("clientRequestId") or ""))
                except ValueError:
                    self._send(handler, 400, {
                        "error": "Validation error",
                        "details": [{"code": "invalid_format",
                                     "format": "uuid"}]})
                    return
                with self._lock:
                    rows = self.comments.setdefault(issue, [])
                    # PF-3 item 1: the delivery channel is a dedicated
                    # service agent, so the instance stamps agent
                    # attribution — authorType "agent", authorAgentId the
                    # service agent (the H2 attribution shape).  Board-user
                    # posts (authorType "user", authorAgentId null) are a
                    # DIFFERENT actor and never this transport's delivery.
                    row = {"id": f"cmt-{len(rows) + 1}",
                           "body": body.get("body", ""),
                           "clientRequestId": body.get("clientRequestId"),
                           "authorType": "agent",
                           "authorAgentId": SERVICE_AGENT,
                           "authorUserId": None}
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
    kwargs.setdefault("service_agent_id", SERVICE_AGENT)
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
    authority — a new process with an empty state dir still posts once.
    T4c repair round 1, R2: the scan counts only THIS transport's own
    earlier delivery (the deterministic uuid5 clientRequestId it posts
    with, echoed on a row authored by THIS service agent — PF-3 item 1),
    never a bare marker string."""
    _deliver(_transport(paperclip, tmp_path))
    fresh = _transport(paperclip, tmp_path / "other-state")
    receipt = _deliver(fresh)
    assert receipt["state"] == "delivered"
    assert receipt.get("note") == "already-delivered"
    assert len(paperclip.comment_posts()) == 1


def test_r2_a_forged_marker_in_another_authors_comment_does_not_suppress(
        paperclip, tmp_path):
    """T4c repair round 1, R2 (panel MED, 2026-11-11): the dedupe scan was a
    plain substring test over every comment body, so ANY comment carrying
    ``paperclip-return-attempt: <id>`` suppressed the real delivery, wrote
    the sidecar mark and made the receipt claim already-delivered — the
    attempt id is public (the worker prompt names it).  A row now counts
    only when it is this transport's OWN delivery: the deterministic
    clientRequestId this code posts with (uuid5 keyed on the attempt),
    echoed on a row authored by THIS service agent (PF-3 item 1).  Another
    agent's row carries a different authorAgentId and a board-user row has
    none, so neither can suppress a delivery."""
    marker = f"{PAPERCLIP_RETURN_MARKER_PREFIX} {ATTEMPT}"

    # a teammate agent forges the marker (agent-authored, right marker,
    # even a plausible clientRequestId — but its OWN, not the uuid5)
    paperclip.comments.setdefault(ISSUE, []).append({
        "id": "cmt-evil-1", "body": f"[coding-job] {marker}\nforged",
        "clientRequestId": str(uuid.uuid4()),
        "authorType": "agent", "authorAgentId": "ag-evil",
        "authorUserId": None, "createdAt": "2026-11-11T01:00:00Z"})
    # a board-user comment pastes the marker but carries no request id
    paperclip.comments[ISSUE].append({
        "id": "cmt-evil-2", "body": f"saw this already? {marker}",
        "clientRequestId": None,
        "authorType": "user", "authorAgentId": None,
        "authorUserId": "someone-else", "createdAt": "2026-11-11T02:00:00Z"})

    transport = _transport(paperclip, tmp_path)
    receipt = _deliver(transport)

    # neither forged row suppressed the delivery: the real comment posted
    assert receipt["state"] == "delivered"
    assert receipt.get("note") is None, "the receipt must not claim already-delivered"
    assert len(paperclip.comment_posts()) == 1
    assert transport._marks(ATTEMPT) == {"comment", "document"}
    posted = paperclip.comment_posts()[0]
    assert marker in posted["body"].decode("utf-8")

    # and the honest result IS on the issue: the transport's own row, not
    # the forgeries, is what a later fresh transport dedupes against
    fresh = _transport(paperclip, tmp_path / "other-state")
    second = _deliver(fresh)
    assert second["state"] == "delivered"
    assert second.get("note") == "already-delivered"
    assert len(paperclip.comment_posts()) == 1, "still exactly one real delivery"


def test_r2_a_genuine_earlier_delivery_row_still_dedupes(
        paperclip, tmp_path):
    """R2's other leg: the authenticated scan must still find the
    transport's own earlier delivery — the exact row shape this transport
    posts (uuid5 clientRequestId, authored by THIS service agent — PF-3
    item 1), planted by hand as a crashed predecessor's POST-success/
    response-lost window would leave it: no sidecar, the row already on
    the issue."""
    expected_request_id = str(uuid.uuid5(
        uuid.NAMESPACE_URL, f"paperclip-return:{ATTEMPT}"))
    paperclip.comments.setdefault(ISSUE, []).append({
        "id": "cmt-real-1",
        "body": build_return_comment(_record(), ATTEMPT),
        "clientRequestId": expected_request_id,
        "authorType": "agent", "authorAgentId": SERVICE_AGENT,
        "authorUserId": None,
        "createdAt": "2026-11-11T03:00:00Z"})

    transport = _transport(paperclip, tmp_path)
    receipt = _deliver(transport)
    assert receipt["state"] == "delivered"
    assert receipt.get("note") == "already-delivered"
    assert len(paperclip.comment_posts()) == 0, "no re-post of a genuine delivery"
    assert len(paperclip.document_puts()) == 1, "the document step still completes"
    assert len(paperclip.comments[ISSUE]) == 1
    assert transport._marks(ATTEMPT) == {"comment", "document"}


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
            base_url=base, headers=DEV_HEADERS, state_dir=tmp_path,
            service_agent_id=SERVICE_AGENT)


@pytest.mark.parametrize("base", [
    "http://127.0.0.1:3190", "http://localhost:3190", "http://[::1]:3190",
])
def test_loopback_bases_construct(base, tmp_path):
    PaperclipResultDeliveryTransport(
        base_url=base, headers=DEV_HEADERS, state_dir=tmp_path,
        service_agent_id=SERVICE_AGENT)


# --- PF-3 item 1: the service-agent writer identity -------------------------


def test_service_agent_id_is_required(paperclip, tmp_path):
    """The transport cannot be built without a writer identity: delivering
    as the board is exactly the defect PF-3 item 1 removes."""
    with pytest.raises(TypeError):
        PaperclipResultDeliveryTransport(
            base_url=paperclip.base_url, headers=DEV_HEADERS,
            state_dir=tmp_path)


@pytest.mark.parametrize("bad", ["", "   ", None, 7, ["ag-x"]])
def test_service_agent_id_must_be_a_non_empty_string(bad, tmp_path):
    with pytest.raises(ValueError, match="service_agent_id"):
        PaperclipResultDeliveryTransport(
            base_url="http://127.0.0.1:3190", headers=DEV_HEADERS,
            state_dir=tmp_path, service_agent_id=bad)


def test_board_user_row_with_our_request_id_is_not_ours(paperclip, tmp_path):
    """Owed (a): a board-user comment carrying OUR deterministic
    clientRequestId and the marker is still NOT our delivery — the board
    is a different actor.  The transport must post the real result."""
    marker = f"{PAPERCLIP_RETURN_MARKER_PREFIX} {ATTEMPT}"
    our_request_id = str(uuid.uuid5(
        uuid.NAMESPACE_URL, f"paperclip-return:{ATTEMPT}"))
    paperclip.comments.setdefault(ISSUE, []).append({
        "id": "cmt-board-1", "body": f"[coding-job] {marker}\nboard paste",
        "clientRequestId": our_request_id,
        "authorType": "user", "authorAgentId": None,
        "authorUserId": "local-board", "createdAt": "2026-11-14T01:00:00Z"})

    receipt = _deliver(_transport(paperclip, tmp_path))
    assert receipt["state"] == "delivered"
    assert receipt.get("note") is None, "a board row must not suppress delivery"
    assert len(paperclip.comment_posts()) == 1


def test_foreign_agent_row_with_our_request_id_is_not_ours(paperclip, tmp_path):
    """Owed (b): another agent's comment with OUR clientRequestId and the
    marker is NOT our delivery — only THIS service agent's row counts."""
    marker = f"{PAPERCLIP_RETURN_MARKER_PREFIX} {ATTEMPT}"
    our_request_id = str(uuid.uuid5(
        uuid.NAMESPACE_URL, f"paperclip-return:{ATTEMPT}"))
    paperclip.comments.setdefault(ISSUE, []).append({
        "id": "cmt-other-1", "body": f"[coding-job] {marker}\nother agent",
        "clientRequestId": our_request_id,
        "authorType": "agent", "authorAgentId": "ag-someone-else",
        "authorUserId": None, "createdAt": "2026-11-14T01:00:00Z"})

    receipt = _deliver(_transport(paperclip, tmp_path))
    assert receipt["state"] == "delivered"
    assert receipt.get("note") is None, "a foreign agent row must not suppress"
    assert len(paperclip.comment_posts()) == 1


def test_restart_dedupe_same_and_fresh_state_dir_posts_exactly_once(
        paperclip, tmp_path):
    """Owed (c): our service agent's row IS ours.  Across a restart — a new
    transport instance on the SAME state dir, and another on a FRESH empty
    state dir — exactly one comment is ever posted."""
    first = _deliver(_transport(paperclip, tmp_path))
    assert first["state"] == "delivered"

    same_state = _deliver(_transport(paperclip, tmp_path))
    assert same_state["state"] == "delivered"
    assert same_state.get("note") == "already-delivered"

    fresh_state = _deliver(_transport(paperclip, tmp_path / "fresh-empty"))
    assert fresh_state["state"] == "delivered"
    assert fresh_state.get("note") == "already-delivered"

    assert len(paperclip.comment_posts()) == 1, "exactly one comment, ever"
    assert len(paperclip.comments[ISSUE]) == 1


def test_ruling19_written_mark_is_never_rederived_away(paperclip, tmp_path):
    """Owed (d), ruling 19: once the 'comment' mark is written it is never
    re-derived away.  A later comments listing that LACKS our row (or holds
    only foreign rows) causes no second post and no mark removal/rewrite."""
    transport = _transport(paperclip, tmp_path)
    assert _deliver(transport)["state"] == "delivered"
    marks_path = tmp_path / "paperclip_result_delivery_marks.jsonl"
    before = marks_path.read_bytes()
    assert transport._marks(ATTEMPT) == {"comment", "document"}

    # the listing now holds only a foreign row — our own row is gone
    paperclip.comments[ISSUE] = [{
        "id": "cmt-foreign", "body": "unrelated board chatter",
        "clientRequestId": str(uuid.uuid4()),
        "authorType": "user", "authorAgentId": None,
        "authorUserId": "local-board", "createdAt": "2026-11-14T02:00:00Z"}]

    restarted = _transport(paperclip, tmp_path)
    receipt = _deliver(restarted)
    assert receipt["state"] == "delivered"
    assert receipt.get("note") == "already-delivered"
    assert len(paperclip.comment_posts()) == 1, "no second post"
    assert restarted._marks(ATTEMPT) == {"comment", "document"}
    assert marks_path.read_bytes() == before, "the mark is never rewritten"


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


# --- PF-3 item 1: header values never leak ----------------------------------


def test_header_values_never_leak_after_failed_and_successful_delivery(
        paperclip, tmp_path, capsys):
    """An authorization header value must never appear in captured
    stdout/stderr, in any receipt, or in ANY file under the state dir —
    after a failed AND a successful delivery (fake HTTP layer)."""
    sentinel = "SENTINEL-AUTH-9f3e2d1c"
    headers = {"x-instance-role": "local_trusted",
               "authorization": f"Bearer {sentinel}"}
    transport = PaperclipResultDeliveryTransport(
        base_url=paperclip.base_url, headers=headers,
        state_dir=tmp_path, service_agent_id=SERVICE_AGENT)

    paperclip.fail_next_comment_post = True
    refused = _deliver(transport)
    assert refused["state"] == "refused"
    delivered = _deliver(transport)
    assert delivered["state"] == "delivered"

    captured = capsys.readouterr()
    blob = captured.out + captured.err
    blob += json.dumps(refused) + json.dumps(delivered)
    for path in sorted(tmp_path.rglob("*")):
        if path.is_file():
            blob += path.read_text(encoding="utf-8", errors="replace")
    assert sentinel not in blob, "a header value leaked to output or state"
    assert "Bearer" not in blob


def test_invalid_header_value_never_leaks_into_the_receipt(paperclip, tmp_path):
    """http.client rejects a header value containing a newline with a
    ValueError that QUOTES the value.  That exception text must never reach
    the receipt reason (the last-resort fence embeds str(exc))."""
    sentinel = "SENTINEL-INVALID-7b1a"
    headers = {"authorization": f"Bearer {sentinel}\ninjected"}
    transport = PaperclipResultDeliveryTransport(
        base_url=paperclip.base_url, headers=headers,
        state_dir=tmp_path, service_agent_id=SERVICE_AGENT)
    receipt = _deliver(transport)
    assert receipt["state"] == "refused"
    assert sentinel not in json.dumps(receipt), \
        "the invalid-header exception quoted the secret into the receipt"
