"""``paperclip_task`` result-return transport (MMOS lane T4b, build item 2).

A real stdlib ``http.server`` on an ephemeral 127.0.0.1 port stands in for the
dev Paperclip instance; every request it receives is captured.  The payload is
a REAL ``mastermind.execution_return/v1`` record produced by the projector, so
the transport is proven against the fields the seam actually hands it.

REV-CODE F1: the fake stamps attribution FROM THE AUTH IT RECEIVED, mirroring
the lead's live probe (dev board 3196, build 2026.1106.0): the board channel
posts as user/null and keeps clientRequestId; an agent bearer + a heartbeat
run id posts as agent/svc with clientRequestId DROPPED.  The transport writes
as the dedicated service agent (token file + one heartbeat run per delivery),
never the board, and the exactly-once scan matches the whole marker LINE on a
row authored by that agent.

Covered: delivered receipt shape (comment + document), exactly-once on retry
and across an empty-state restart, the agent-identity scan (board / foreign /
substring rows never suppress), transient mid-flight failures that refuse
honestly, the non-loopback construction refusal, the registry's unknown-kind
law, the token-file refusals, and the no-secrets rule for bodies, headers,
receipts, output and the state dir.
"""
from __future__ import annotations

import asyncio
import json
import re
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
    _quoted_worker_text,
    build_return_comment,
    return_marker_line,
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
# PF-3 item 1 / REV-CODE F1: the delivery writer is a dedicated service agent,
# never the board.  The fake mints a key for this agent and stamps attribution
# FROM THE AUTH IT RECEIVED, exactly mirroring the lead's live probe.
SERVICE_AGENT = "ag-pf-delivery"
# A FAKE bearer token (test material, not a real credential).  It rides only
# as an authorization header on agent writes; the tests prove it never leaks.
SERVICE_TOKEN = "fake-pf-service-bearer-2f8c1a9e"


def _request_id(attempt_id: str = ATTEMPT) -> str:
    """The deterministic uuid5 request id the transport posts with."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"paperclip-return:{attempt_id}"))


def _marker_line(attempt_id: str = ATTEMPT) -> str:
    """The exact whole-line dedupe marker (attempt + request id) — REV-CODE
    F1: the server DROPS clientRequestId on agent rows, so the request id
    rides IN the marker line instead of the row's clientRequestId field."""
    return return_marker_line(attempt_id, _request_id(attempt_id))


# --- the fake Paperclip instance -------------------------------------------


class FakePaperclip:
    """Loopback HTTP stand-in mirroring the lead's live probe (build
    2026.1106.0, dev board 3196):

    * board channel (``x-instance-role: local_trusted``) posts as authorType
      "user", authorAgentId null, and KEEPS clientRequestId;
    * an agent bearer ALONE on a comment POST → 403 ("needs a run");
    * ``POST /api/agents/{id}/heartbeat/invoke`` with the bearer → 202 {id};
    * bearer + ``X-Paperclip-Run-Id`` for a run the fake issued to that agent
      → 201, authorType "agent", authorAgentId the agent, clientRequestId
      DROPPED (stored null);
    * cancelling a run with the agent key → 403 (board only) — the transport
      never cancels, so the fake exposes no cancel leg to it.
    """

    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []
        self.comments: dict[str, list[dict[str, Any]]] = {}
        self.documents: dict[tuple[str, str], dict[str, Any]] = {}
        self.fail_next_comment_post = False
        self.fail_next_heartbeat = False
        # token -> agent id (keys the test mints); run id -> agent id.
        self.agent_keys: dict[str, str] = {}
        self.runs: dict[str, str] = {}
        self._run_counter = 0
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

    # -- auth helpers -------------------------------------------------------

    @staticmethod
    def _auth(headers: dict[str, str]) -> tuple[str | None, str | None, bool]:
        auth = headers.get("authorization", "")
        bearer = auth[len("Bearer "):] if auth.startswith("Bearer ") else None
        run_id = headers.get("x-paperclip-run-id")
        board = headers.get("x-instance-role") == "local_trusted"
        return bearer, run_id, board

    def _agent_for_run(self, bearer: str | None, run_id: str | None
                       ) -> str | None:
        """The agent a bearer+run pair authenticates as, or None (403)."""
        if bearer is None:
            return None
        agent = self.agent_keys.get(bearer)
        if agent is None or run_id is None:
            return None
        if self.runs.get(run_id) != agent:
            return None
        return agent

    # -- request handling ---------------------------------------------------

    def _handle(self, handler: BaseHTTPRequestHandler, method: str) -> None:
        length = int(handler.headers.get("content-length") or 0)
        raw = handler.rfile.read(length) if length else b""
        path = urllib.parse.urlsplit(handler.path).path
        with self._lock:
            headers = {k.lower(): v for k, v in handler.headers.items()}
            self.requests.append({
                "method": method, "path": path,
                "headers": headers, "body": raw,
            })
            fail_comment = method == "POST" and path.endswith("/comments") \
                and self.fail_next_comment_post
            if fail_comment:
                self.fail_next_comment_post = False
            fail_heartbeat = method == "POST" \
                and path.endswith("/heartbeat/invoke") \
                and self.fail_next_heartbeat
            if fail_heartbeat:
                self.fail_next_heartbeat = False
        if fail_comment or fail_heartbeat:
            # A transient mid-flight failure: the connection dies with no
            # response, exactly what a restarting dev instance looks like.
            handler.close_connection = True
            handler.connection.close()
            return
        bearer, run_id, board = self._auth(headers)
        segments = [part for part in path.split("/") if part]
        # /api/agents/<agent>/heartbeat/invoke
        if len(segments) == 5 and segments[:2] == ["api", "agents"] \
                and segments[3] == "heartbeat" and segments[4] == "invoke":
            agent = segments[2]
            if method == "POST":
                with self._lock:
                    if bearer is None or self.agent_keys.get(bearer) != agent:
                        self._send(handler, 403, {"error": "forbidden"})
                        return
                    self._run_counter += 1
                    new_run = f"run-{self._run_counter}"
                    self.runs[new_run] = agent
                self._send(handler, 202, {"id": new_run})
                return
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
                # Attribution FROM THE AUTH (the probe): board → user/null
                # keeping clientRequestId; bearer+run → agent/svc with
                # clientRequestId DROPPED; bearer without a valid run → 403.
                if bearer is None and board:
                    attribution = {
                        "authorType": "user", "authorAgentId": None,
                        "authorUserId": "local-board",
                        "clientRequestId": body.get("clientRequestId")}
                else:
                    agent = self._agent_for_run(bearer, run_id)
                    if agent is None:
                        self._send(handler, 403, {
                            "error": "Cross-issue writes need a run to "
                                     "attribute them to (Heartbeat run "
                                     "context)."})
                        return
                    attribution = {
                        "authorType": "agent", "authorAgentId": agent,
                        "authorUserId": None,
                        "clientRequestId": None}  # server DROPS it
                with self._lock:
                    rows = self.comments.setdefault(issue, [])
                    row = {"id": f"cmt-{len(rows) + 1}",
                           "body": body.get("body", ""), **attribution}
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
                # the document write rides the same bearer+run as the comment
                # (board reads are allowed; a bearer write needs a valid run)
                if bearer is not None and self._agent_for_run(
                        bearer, run_id) is None:
                    self._send(handler, 403, {"error": "needs a run"})
                    return
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

    def heartbeat_invokes(self) -> list[dict[str, Any]]:
        return [row for row in self.requests
                if row["path"].endswith("/heartbeat/invoke")]


@pytest.fixture()
def paperclip(tmp_path_factory):
    fake = FakePaperclip()
    # The token file lives in a SEPARATE keys dir, never under the transport's
    # state_dir, so the no-secrets-in-state assertions can scan the state dir
    # without tripping over the (legitimate) token file itself.
    keys_dir = tmp_path_factory.mktemp("pf-keys")
    fake.token_path = keys_dir / "service-agent.bearer"
    fake.token_path.write_text(SERVICE_TOKEN, encoding="utf-8")
    fake.token_path.chmod(0o600)
    fake.agent_keys[SERVICE_TOKEN] = SERVICE_AGENT
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
    kwargs.setdefault("service_agent_token_path", paperclip.token_path)
    return PaperclipResultDeliveryTransport(
        base_url=paperclip.base_url, headers=DEV_HEADERS,
        state_dir=tmp_path, **kwargs)


def _deliver(transport: PaperclipResultDeliveryTransport,
             origin: OriginRef | None = None,
             payload: dict[str, Any] | None = None) -> dict[str, Any]:
    return asyncio.run(transport.deliver(
        origin or _origin(), payload if payload is not None else _record()))


# --- REV-CODE F1 (HIGH): the agent writer, exactly-once across a restart ----


def test_f1_agent_writer_restart_with_empty_state_posts_exactly_once(
        paperclip, tmp_path):
    """The fix for the failing-first defect (board writer double-posted,
    assert 2 == 1): with the service-agent writer the row is agent-authored,
    so a restart with an EMPTY state_dir dedupes from the issue's own comments
    and posts exactly once."""
    first = _deliver(_transport(paperclip, tmp_path))
    assert first["state"] == "delivered"
    row = paperclip.comments[ISSUE][0]
    assert row["authorType"] == "agent"
    assert row["authorAgentId"] == SERVICE_AGENT
    assert row["clientRequestId"] is None  # the server drops it on agent rows

    fresh = _transport(paperclip, tmp_path / "empty-state")
    receipt = _deliver(fresh)
    assert receipt["state"] == "delivered"
    assert receipt.get("note") == "already-delivered"
    assert len(paperclip.comment_posts()) == 1, "exactly one comment, ever"
    assert len(paperclip.comments[ISSUE]) == 1


def test_f1_agent_write_uses_bearer_and_run_board_read_does_not(
        paperclip, tmp_path):
    """One heartbeat run per delivery; the comment POST and document PUT ride
    bearer + that run id; the dedupe comment GET is a board read (no auth)."""
    assert _deliver(_transport(paperclip, tmp_path))["state"] == "delivered"

    invokes = paperclip.heartbeat_invokes()
    assert len(invokes) == 1, "exactly one heartbeat run per delivery"
    assert invokes[0]["headers"]["authorization"] == f"Bearer {SERVICE_TOKEN}"

    gets = [q for q in paperclip.requests
            if q["method"] == "GET" and q["path"].endswith("/comments")]
    assert gets and all("authorization" not in q["headers"] for q in gets)

    posts = paperclip.comment_posts()
    assert posts[0]["headers"]["authorization"] == f"Bearer {SERVICE_TOKEN}"
    run_id = posts[0]["headers"]["x-paperclip-run-id"]
    assert paperclip.runs.get(run_id) == SERVICE_AGENT
    puts = paperclip.document_puts()
    assert puts[0]["headers"]["authorization"] == f"Bearer {SERVICE_TOKEN}"
    assert puts[0]["headers"]["x-paperclip-run-id"] == run_id, "same run reused"


def test_f1_deduped_delivery_invokes_no_heartbeat(paperclip, tmp_path):
    """A delivery that short-circuits on the sidecar mark writes nothing, so
    it invokes no heartbeat run and posts nothing."""
    _deliver(_transport(paperclip, tmp_path))
    before = len(paperclip.heartbeat_invokes())
    receipt = _deliver(_transport(paperclip, tmp_path))
    assert receipt.get("note") == "already-delivered"
    assert len(paperclip.heartbeat_invokes()) == before
    assert len(paperclip.comment_posts()) == 1


def test_f1_board_row_with_exact_marker_line_is_not_ours(paperclip, tmp_path):
    """Owed (d)(2): a BOARD row carrying the exact whole marker line and our
    request id is still NOT our delivery — the board is a different actor
    (authorAgentId null).  The transport must post the real result."""
    paperclip.comments.setdefault(ISSUE, []).append({
        "id": "cmt-board-1",
        "body": f"[coding-job]\n{_marker_line()}\nboard paste",
        "clientRequestId": _request_id(),
        "authorType": "user", "authorAgentId": None,
        "authorUserId": "local-board", "createdAt": "2026-11-14T01:00:00Z"})

    receipt = _deliver(_transport(paperclip, tmp_path))
    assert receipt["state"] == "delivered"
    assert receipt.get("note") is None, "a board row must not suppress delivery"
    assert len(paperclip.comment_posts()) == 1


def test_f1_foreign_agent_row_with_marker_line_is_not_ours(paperclip, tmp_path):
    """Owed (d)(3): another agent's row with the exact marker line and our
    request id is NOT our delivery — only THIS service agent's row counts."""
    paperclip.comments.setdefault(ISSUE, []).append({
        "id": "cmt-other-1",
        "body": f"[coding-job]\n{_marker_line()}\nother agent",
        "clientRequestId": _request_id(),
        "authorType": "agent", "authorAgentId": "ag-someone-else",
        "authorUserId": None, "createdAt": "2026-11-14T01:00:00Z"})

    receipt = _deliver(_transport(paperclip, tmp_path))
    assert receipt["state"] == "delivered"
    assert receipt.get("note") is None, "a foreign agent row must not suppress"
    assert len(paperclip.comment_posts()) == 1


def test_f1_service_agent_row_with_marker_only_as_substring_is_not_ours(
        paperclip, tmp_path):
    """Owed (d)(4): even a row authored by OUR service agent is not ours when
    the marker is only a substring of a longer line — the scan demands the
    marker as a WHOLE line."""
    line = _marker_line()
    paperclip.comments.setdefault(ISSUE, []).append({
        "id": "cmt-sub-1",
        "body": f"prefix {line} suffix\nmore prose",  # embedded, not a whole line
        "clientRequestId": None,
        "authorType": "agent", "authorAgentId": SERVICE_AGENT,
        "authorUserId": None, "createdAt": "2026-11-14T01:00:00Z"})

    receipt = _deliver(_transport(paperclip, tmp_path))
    assert receipt["state"] == "delivered"
    assert receipt.get("note") is None, "a substring marker must not suppress"
    assert len(paperclip.comment_posts()) == 1


def test_f1_heartbeat_failure_refuses_before_any_comment_post(
        paperclip, tmp_path):
    """Owed (d)(7): a heartbeat invoke failure is a typed refusal and NO
    comment POST is attempted (the run is a precondition for the write)."""
    paperclip.fail_next_heartbeat = True
    posts_before = len(paperclip.comment_posts())
    receipt = _deliver(_transport(paperclip, tmp_path))
    assert receipt["state"] == "refused"
    assert receipt["refusal_code"] == "HEARTBEAT_INVOKE_FAILED"
    assert len(paperclip.comment_posts()) == posts_before, "no comment POST"
    assert paperclip.comments.get(ISSUE, []) == []


def test_f1_token_never_leaks_and_bad_token_files_refuse(
        paperclip, tmp_path, capsys):
    """Owed (d)(6): the bearer token never appears in stdout/stderr, receipts,
    the state dir or the comment body after a failed AND a successful
    delivery; a missing / 0644 / symlinked token file is a typed refusal that
    posts nothing."""
    paperclip.fail_next_comment_post = True
    refused = _deliver(_transport(paperclip, tmp_path))
    assert refused["state"] == "refused"
    delivered = _deliver(_transport(paperclip, tmp_path))
    assert delivered["state"] == "delivered"

    captured = capsys.readouterr()
    blob = captured.out + captured.err
    blob += json.dumps(refused) + json.dumps(delivered)
    for path in sorted(tmp_path.rglob("*")):
        if path.is_file():
            blob += path.read_text(encoding="utf-8", errors="replace")
    for row in paperclip.comments.get(ISSUE, []):
        blob += row["body"]
    assert SERVICE_TOKEN not in blob, "the token leaked to output/state/body"
    assert "Bearer" not in blob
    # the token rides ONLY as an authorization header, never in a request body
    for req in paperclip.requests:
        assert SERVICE_TOKEN not in req["body"].decode("utf-8", "replace")

    # Force a real post attempt for the bad-token legs: clear the issue's
    # comments so the scan finds no own row and the transport must reach the
    # token read (otherwise it would dedupe against the row posted above).
    paperclip.comments[ISSUE] = []
    posts_before = len(paperclip.comment_posts())
    # missing file
    r = _deliver(_transport(
        paperclip, tmp_path / "m",
        service_agent_token_path=tmp_path / "nope.bearer"))
    assert r["state"] == "refused"
    assert r["refusal_code"] == "SERVICE_TOKEN_UNAVAILABLE"
    # wrong mode (0644)
    bad = tmp_path / "bad.bearer"
    bad.write_text(SERVICE_TOKEN, encoding="utf-8")
    bad.chmod(0o644)
    r = _deliver(_transport(
        paperclip, tmp_path / "s", service_agent_token_path=bad))
    assert r["refusal_code"] == "SERVICE_TOKEN_UNAVAILABLE"
    # symlink (even to a valid 0600 file)
    link = tmp_path / "link.bearer"
    link.symlink_to(paperclip.token_path)
    r = _deliver(_transport(
        paperclip, tmp_path / "l", service_agent_token_path=link))
    assert r["refusal_code"] == "SERVICE_TOKEN_UNAVAILABLE"
    assert len(paperclip.comment_posts()) == posts_before, "no POST on bad token"


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
    assert _marker_line() in body.splitlines()   # the whole marker line
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
    assert _marker_line() in document["body"].splitlines()
    assert _record()["digest"] in document["body"]  # the full record is carried


def test_comment_body_never_invents_unobserved_github_evidence():
    body = build_return_comment(_record(), ATTEMPT, _request_id())
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
    The scan counts only THIS transport's own earlier delivery: the whole
    marker line (attempt + uuid5 request id) on a row authored by THIS
    service agent (REV-CODE F1), never a bare marker string."""
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
    the marker suppressed the real delivery.  A row now counts only when it
    is this transport's OWN delivery: the whole marker line on a row authored
    by THIS service agent.  Another agent's row carries a different
    authorAgentId and a board-user row has none, so neither can suppress."""
    # a teammate agent forges the exact marker line (right marker, right
    # request id — but its OWN authorAgentId, not the service agent)
    paperclip.comments.setdefault(ISSUE, []).append({
        "id": "cmt-evil-1",
        "body": f"[coding-job]\n{_marker_line()}\nforged",
        "clientRequestId": _request_id(),
        "authorType": "agent", "authorAgentId": "ag-evil",
        "authorUserId": None, "createdAt": "2026-11-11T01:00:00Z"})
    # a board-user comment pastes the marker line but is a different actor
    paperclip.comments[ISSUE].append({
        "id": "cmt-evil-2",
        "body": f"saw this already?\n{_marker_line()}",
        "clientRequestId": None,
        "authorType": "user", "authorAgentId": None,
        "authorUserId": "someone-else", "createdAt": "2026-11-11T02:00:00Z"})

    transport = _transport(paperclip, tmp_path)
    receipt = _deliver(transport)

    assert receipt["state"] == "delivered"
    assert receipt.get("note") is None, "the receipt must not claim already-delivered"
    assert len(paperclip.comment_posts()) == 1
    assert transport._marks(ATTEMPT) == {"comment", "document"}
    posted = paperclip.comment_posts()[0]
    assert _marker_line() in posted["body"].decode("utf-8")

    # the honest result IS on the issue: the transport's own row, not the
    # forgeries, is what a later fresh transport dedupes against
    fresh = _transport(paperclip, tmp_path / "other-state")
    second = _deliver(fresh)
    assert second["state"] == "delivered"
    assert second.get("note") == "already-delivered"
    assert len(paperclip.comment_posts()) == 1, "still exactly one real delivery"


def test_r2_a_genuine_earlier_delivery_row_still_dedupes(paperclip, tmp_path):
    """R2's other leg: the authenticated scan must still find the transport's
    own earlier delivery — the exact row shape this transport posts (whole
    marker line, authored by THIS service agent, clientRequestId dropped by
    the server), planted by hand as a crashed predecessor's POST-success/
    response-lost window would leave it: no sidecar, the row already there."""
    paperclip.comments.setdefault(ISSUE, []).append({
        "id": "cmt-real-1",
        "body": build_return_comment(_record(), ATTEMPT, _request_id()),
        "clientRequestId": None,  # the server drops it on agent rows
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
            service_agent_id=SERVICE_AGENT,
            service_agent_token_path=str(tmp_path / "t.bearer"))


@pytest.mark.parametrize("base", [
    "http://127.0.0.1:3190", "http://localhost:3190", "http://[::1]:3190",
])
def test_loopback_bases_construct(base, tmp_path):
    PaperclipResultDeliveryTransport(
        base_url=base, headers=DEV_HEADERS, state_dir=tmp_path,
        service_agent_id=SERVICE_AGENT,
        service_agent_token_path=str(tmp_path / "t.bearer"))


# --- PF-3 item 1 / REV-CODE F1: the service-agent writer identity -----------


def test_service_agent_id_is_required(paperclip, tmp_path):
    """The transport cannot be built without a writer identity: delivering
    as the board is exactly the defect PF-3 item 1 removes."""
    with pytest.raises(TypeError):
        PaperclipResultDeliveryTransport(
            base_url=paperclip.base_url, headers=DEV_HEADERS,
            service_agent_token_path=paperclip.token_path,
            state_dir=tmp_path)


def test_service_agent_token_path_is_required(paperclip, tmp_path):
    """REV-CODE F1: the agent writer needs its token file path; without it
    the transport cannot be built (no board fallback)."""
    with pytest.raises(TypeError):
        PaperclipResultDeliveryTransport(
            base_url=paperclip.base_url, headers=DEV_HEADERS,
            service_agent_id=SERVICE_AGENT, state_dir=tmp_path)


@pytest.mark.parametrize("bad", ["", "   ", None, 7, ["ag-x"]])
def test_service_agent_id_must_be_a_non_empty_string(bad, tmp_path):
    with pytest.raises(ValueError, match="service_agent_id"):
        PaperclipResultDeliveryTransport(
            base_url="http://127.0.0.1:3190", headers=DEV_HEADERS,
            state_dir=tmp_path, service_agent_id=bad,
            service_agent_token_path=str(tmp_path / "t.bearer"))


@pytest.mark.parametrize("bad", [
    " ag-pf-delivery", "ag-pf-delivery ", "\tag-pf-delivery",
    "ag-pf-delivery\n", " ag-pf-delivery "])
def test_f5_service_agent_id_with_surrounding_whitespace_is_refused(bad, tmp_path):
    """REV-CODE F5: a padded id would never equal the server's authorAgentId
    and would silently break the exactly-once scan — refuse, never strip."""
    with pytest.raises(ValueError, match="service_agent_id"):
        PaperclipResultDeliveryTransport(
            base_url="http://127.0.0.1:3190", headers=DEV_HEADERS,
            state_dir=tmp_path, service_agent_id=bad,
            service_agent_token_path=str(tmp_path / "t.bearer"))


def test_board_user_row_with_our_request_id_is_not_ours(paperclip, tmp_path):
    """A board-user comment carrying OUR deterministic request id and the
    marker line is still NOT our delivery — the board is a different actor."""
    paperclip.comments.setdefault(ISSUE, []).append({
        "id": "cmt-board-1",
        "body": f"[coding-job]\n{_marker_line()}\nboard paste",
        "clientRequestId": _request_id(),
        "authorType": "user", "authorAgentId": None,
        "authorUserId": "local-board", "createdAt": "2026-11-14T01:00:00Z"})

    receipt = _deliver(_transport(paperclip, tmp_path))
    assert receipt["state"] == "delivered"
    assert receipt.get("note") is None, "a board row must not suppress delivery"
    assert len(paperclip.comment_posts()) == 1


def test_foreign_agent_row_with_our_request_id_is_not_ours(paperclip, tmp_path):
    """Another agent's comment with OUR request id and the marker line is NOT
    our delivery — only THIS service agent's row counts."""
    paperclip.comments.setdefault(ISSUE, []).append({
        "id": "cmt-other-1",
        "body": f"[coding-job]\n{_marker_line()}\nother agent",
        "clientRequestId": _request_id(),
        "authorType": "agent", "authorAgentId": "ag-someone-else",
        "authorUserId": None, "createdAt": "2026-11-14T01:00:00Z"})

    receipt = _deliver(_transport(paperclip, tmp_path))
    assert receipt["state"] == "delivered"
    assert receipt.get("note") is None, "a foreign agent row must not suppress"
    assert len(paperclip.comment_posts()) == 1


def test_restart_dedupe_same_and_fresh_state_dir_posts_exactly_once(
        paperclip, tmp_path):
    """Our service agent's row IS ours.  Across a restart — a new transport
    instance on the SAME state dir, and another on a FRESH empty state dir —
    exactly one comment is ever posted."""
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
    """Owed (d)(5), ruling 19: once the 'comment' mark is written it is never
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


def test_token_rides_only_as_auth_header_never_in_bodies(paperclip, tmp_path):
    """The bearer token is confined to the authorization header on agent
    writes; no request body, comment body or board read carries it."""
    _deliver(_transport(paperclip, tmp_path))
    assert paperclip.requests, "the fake server saw the delivery"
    for row in paperclip.requests:
        text = row["body"].decode("utf-8", "replace")
        assert SERVICE_TOKEN not in text
        assert "Bearer" not in text
        assert "authorization" not in text.lower()
        if row["method"] == "GET":
            # board reads carry the dev header, never an authorization
            assert row["headers"].get("x-instance-role") == "local_trusted"
            assert "authorization" not in row["headers"]
    for comment in paperclip.comments[ISSUE]:
        assert SERVICE_TOKEN not in comment["body"]


def test_header_values_never_leak_after_failed_and_successful_delivery(
        paperclip, tmp_path, capsys):
    """A configured authorization header value must never appear in captured
    stdout/stderr, in any receipt, or in ANY file under the state dir —
    after a failed AND a successful delivery (fake HTTP layer)."""
    sentinel = "SENTINEL-AUTH-9f3e2d1c"
    headers = {"x-instance-role": "local_trusted",
               "authorization": f"Bearer {sentinel}"}
    transport = PaperclipResultDeliveryTransport(
        base_url=paperclip.base_url, headers=headers,
        service_agent_token_path=paperclip.token_path,
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
        service_agent_token_path=paperclip.token_path,
        state_dir=tmp_path, service_agent_id=SERVICE_AGENT)
    receipt = _deliver(transport)
    assert receipt["state"] == "refused"
    assert sentinel not in json.dumps(receipt), \
        "the invalid-header exception quoted the secret into the receipt"


def test_f4_last_resort_fence_scrubs_before_truncating(
        paperclip, tmp_path, monkeypatch):
    """REV-CODE F4: a secret straddling the 300-char reason cap must be fully
    redacted — scrub the WHOLE text first, then truncate (the old fence
    truncated first and could leave a fragment of the secret)."""
    secret = "Z" * 40
    headers = {"x-instance-role": "local_trusted",
               "authorization": f"Bearer {secret}"}
    transport = PaperclipResultDeliveryTransport(
        base_url=paperclip.base_url, headers=headers,
        service_agent_token_path=paperclip.token_path,
        state_dir=tmp_path, service_agent_id=SERVICE_AGENT)
    # embed the full header VALUE ("Bearer " + secret) and position it so a
    # truncate-first cap would cut through the secret, leaving a fragment the
    # scrubber can no longer match (it redacts the whole value, not a prefix)
    message = "x" * 250 + f"Bearer {secret}" + "tail"

    def boom(*args, **kwargs):
        raise RuntimeError(message)

    monkeypatch.setattr(transport, "_marks", boom)
    receipt = asyncio.run(transport.deliver(_origin(), _record()))
    assert receipt["state"] == "refused"
    assert receipt["refusal_code"] == "TRANSPORT_FAILED"
    assert secret not in receipt["reason"]
    assert "Z" * 6 not in receipt["reason"], "no fragment of the secret survives"
    assert len(receipt["reason"]) <= 300


# --- F7: direct _scrub unit + fence edge cases ------------------------------


def test_f7_scrub_redacts_raw_and_repr_forms(tmp_path):
    value = "Bearer abc\ndef"  # a newline so the raw and %r forms differ
    transport = PaperclipResultDeliveryTransport(
        base_url="http://127.0.0.1:3190", headers={"authorization": value},
        service_agent_id=SERVICE_AGENT,
        service_agent_token_path=str(tmp_path / "t.bearer"), state_dir=tmp_path)
    raw = transport._scrub(f"raw {value} end")
    assert "abc" not in raw and "[redacted-header]" in raw
    rep = transport._scrub(f"repr {value!r} end")
    assert "abc" not in rep and "[redacted-header]" in rep


@pytest.mark.parametrize("text", [
    "line1\r\nline2",        # CRLF
    "line1\rline2",          # lone CR
    "a\nb",                  # LF
    "``` inner ```",         # a backtick run inside the worker text
    "`````",                 # a long backtick run
    "",                      # empty
])
def test_f7_fence_wraps_worker_text_verbatim(text):
    fenced = _quoted_worker_text(text)
    longest = max((len(m) for m in re.findall(r"`+", text)), default=0)
    fence = "`" * max(3, longest + 1)
    assert fenced == f"{fence}\n{text}\n{fence}"


def test_f7_empty_result_text_is_placeholder():
    payload = _record()
    payload["result"] = dict(payload["result"], text="")
    body = build_return_comment(payload, ATTEMPT, _request_id())
    assert "(no result text recorded)" in body


def test_f7_marker_line_stays_whole_with_newline_in_stage():
    """A newline in the stage/title line never breaks the marker line: the
    marker is always its own whole line, recoverable by the scan."""
    payload = _record()
    payload["stage"] = "branch_pushed\ninjected"
    body = build_return_comment(payload, ATTEMPT, _request_id())
    assert _marker_line() in body.splitlines()