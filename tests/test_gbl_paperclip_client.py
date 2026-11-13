"""GBL-4 Paperclip client tests (lane GBL, BUILD_PLAN row GBL-4 + repair 1).

The ``GblAskStore`` protocol (GBL-2, ``bridge_service.py:94``) implemented
over Paperclip issues+comments, driven against a fake HTTP server bound to
127.0.0.1 on an EPHEMERAL port — no real Paperclip instance is contacted.
BUILD_PLAN/notes law under test: one issue per ask assigned to the bridge
service agent; a create whose outcome is lost raises ``GblCreateEffectUnknown``
and is reconciled by read-back of the deterministic ask id — never a second
create; 4xx/5xx mapped to typed errors; the base URL is required, loopback
http only, never port 3100/3179 or any default; no credential ever rides a
request.  All strings are harmless fixture words.

Repair round 1 (panel B): pagination to exhaustion with fail-closed
counting (H2), robust envelope parsing that never reads corruption as
absence (H4), exact-key resolution (M3), fail-closed envelope shapes (M4,
M5), no redirect following and a per-request URL law (M6), ambiguous 4xx on
create as EFFECT_UNKNOWN (M7), ``HTTPException`` caught (M8), strict id
charset + percent-encoded path segments (M9), and comment author/order
provenance exposed for the bridge (M1/M2 client side).

Round 2 (GBL_REPAIR1_NOTES §1–§3): ``create_ask`` is CREATE-IF-ABSENT
(None when created, the existing record when the deterministic id is
present — never a second issue); every appended event is stamped with a
per-record strictly-increasing integer ``seq`` and authenticated by a
host-held HMAC v1 tag bound to (ask_id, seq, event) — a comment whose tag
is absent, malformed, cross-ask, or failing verification surfaces
``trusted: False`` and the bridge ignores it; the HMAC key is a harmless
FIXTURE value read from a file (never argv, never a log, never the wire).
"""
from __future__ import annotations

import hashlib
import hmac
import itertools
import json
import os
import stat
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest

from common.gbl_contract import build_ask
from integrations.gbl.bridge_service import (
    GblBridge,
    GblBridgeError,
    GblCreateEffectUnknown,
    PrincipalAdmission,
)
from integrations.gbl import paperclip_client as pc
from integrations.gbl.paperclip_client import (
    GblPaperclipClientError,
    GblPaperclipError,
    GblPaperclipServerError,
    GblPaperclipTransportError,
    PaperclipAskClient,
    create_service_agent,
    validate_paperclip_base_url,
)

COMPANY_ID = "11111111-1111-4111-8111-111111111111"
AGENT_ID = "22222222-2222-4222-8222-222222222222"
PRINCIPAL = "grok-account-fixture"

# The HMAC key fixture: harmless words, exactly 32 bytes (the v1 key size),
# read from a file the client is given — never argv, never a log, never a
# commit.  Every key in this suite is this value or os-generated noise.
KEY_BYTES = (b"gbl4-harmless-fixture-key-" * 2)[:32]
HMAC_KEY_PATH: Path | None = None        # set by the autouse fixture below


def envelope(key: str = "k-1", body: str = "A harmless fixture question.",
             principal: str = PRINCIPAL, **over) -> dict:
    kwargs = dict(kind="question", principal=principal, target=principal,
                  idempotency_key=key, title="Fixture ask", body=body,
                  now=datetime(2026, 11, 11, 12, 0, 0, tzinfo=timezone.utc))
    kwargs.update(over)
    return build_ask(**kwargs)


# ── The fake Paperclip HTTP server (127.0.0.1, ephemeral port) ──────────────


class FakePaperclipState:
    """In-memory Paperclip-ish state: issues, comments, agents, failures."""

    def __init__(self):
        self.issues: dict[str, dict] = {}
        self.order: list[str] = []          # issue ids in create order
        self.comments: dict[str, list[dict]] = {}
        self.agents: dict[str, dict] = {}
        self.requests: list[tuple[str, str]] = []
        self.headers_log: list[tuple[str, str, dict]] = []
        self.request_bodies: list[str] = []    # round 2: key-hygiene checks
        self.create_delay = 0.0             # sleep AFTER performing a create
        self.create_fail_status: int | None = None   # refuse BEFORE landing
        self.create_reply_status: int | None = None  # land, then answer this
        self.truncate_create = False        # land, then truncate the reply
        self.fail_status: dict[tuple[str, str], int] = {}
        self.slow_paths: dict[tuple[str, str], float] = {}   # sleep BEFORE
        self.next_created_at: str | None = None
        # repair-1 knobs
        self.ignore_offset = False          # pretend offset is unsupported
        self.list_envelope = "dict"         # dict | bare | unknown
        self.comments_envelope = "dict"     # dict | bare | unknown
        self.redirects: dict[tuple[str, str], str] = {}      # (m, path)→url
        self.comment_author = AGENT_ID      # authorAgentId on new comments
        # GBL-5 A1 knobs: the server's comment LISTING lags its own writes
        # (proof 1's 1.8 s read-your-write lag) — the next N posted comments
        # land but stay hidden from GET until reveal_lagged_comments().
        self.comment_visibility_lag = 0
        self.lagged_comment_ids: set[str] = set()
        # GBL-RETURN knobs: the dispatch/return surface.  The board stamps
        # the creator from the calling key (the client never sends it);
        # list projections can truncate long descriptions; comments carry
        # an author type the result-comment law keys on.
        self.created_by_agent_id: str | None = AGENT_ID
        self.comment_author_type = "agent"
        self.truncate_list_descriptions_at: int | None = None
        self._clock = itertools.count(1)    # strictly increasing timestamps

    def reveal_lagged_comments(self) -> None:
        """The listing catches up with the writes it had hidden."""
        self.lagged_comment_ids.clear()

    def touch(self, method: str, path: str, headers: dict) -> None:
        clean = path.split("?")[0]
        self.requests.append((method, clean))
        self.headers_log.append((method, clean, dict(headers)))

    def stamp(self) -> str:
        base = datetime.now(timezone.utc)
        return (base + timedelta(microseconds=next(self._clock))
                ).isoformat()

    def now_iso(self) -> str:
        if self.next_created_at is not None:
            value, self.next_created_at = self.next_created_at, None
            return value
        return self.stamp()

    def add_issue(self, title: str, description: str) -> str:
        """Insert an arbitrary (e.g. decoy) issue as the newest row."""
        issue_id = str(uuid.uuid4())
        self.issues[issue_id] = {"id": issue_id, "title": title,
                                 "description": description,
                                 "identifier": f"FX-{len(self.order) + 1}",
                                 "createdAt": self.now_iso(),
                                 "status": "todo"}
        self.order.append(issue_id)
        self.comments[issue_id] = []
        return issue_id

    def handle(self, method: str, path: str, query: dict[str, list[str]],
               body: dict | None):
        """Return (status, obj). 404 semantics mirror the real API."""
        parts = [p for p in path.split("/") if p]
        # /api/companies/{cid}/issues
        if (method == "POST" and len(parts) == 4
                and parts[0] == "api" and parts[1] == "companies"
                and parts[2] == COMPANY_ID and parts[3] == "issues"):
            if self.create_fail_status is not None:
                status, self.create_fail_status = self.create_fail_status, None
                return status, {"error": "fixture refusal"}
            row = dict(body or {})
            issue_id = str(uuid.uuid4())
            row.update({"id": issue_id,
                        "identifier": f"FX-{len(self.order) + 1}",
                        "createdAt": self.now_iso(),
                        "status": row.get("status") or "todo"})
            if self.created_by_agent_id is not None:
                row.setdefault("createdByAgentId", self.created_by_agent_id)
            self.issues[issue_id] = row
            self.order.append(issue_id)
            self.comments[issue_id] = []
            if self.create_delay:
                time.sleep(self.create_delay)
            if self.create_reply_status is not None:
                status = self.create_reply_status
                self.create_reply_status = None
                return status, {"error": "fixture ambiguity"}
            return 200, row
        # /api/companies/{cid}/issues (list, newest first, paginated)
        if (method == "GET" and len(parts) == 4
                and parts[0] == "api" and parts[1] == "companies"
                and parts[2] == COMPANY_ID and parts[3] == "issues"):
            limit = int(query.get("limit", ["50"])[0])
            offset = int(query.get("offset", ["0"])[0])
            if self.ignore_offset:
                offset = 0
            newest_first = [self.issues[iid] for iid in reversed(self.order)]
            parent = query.get("parentId", [None])[0]
            if parent is not None:
                # the children projection (RF walk): parentId-filtered
                newest_first = [row for row in newest_first
                                if str(row.get("parentId")) == parent]
            if self.truncate_list_descriptions_at is not None:
                cut = self.truncate_list_descriptions_at
                projections = []
                for row in newest_first:
                    description = row.get("description") or ""
                    if isinstance(description, str) and len(description) > cut:
                        row = dict(row)
                        row["description"] = description[:cut]
                        row["descriptionTruncated"] = True
                    projections.append(row)
                newest_first = projections
            page = newest_first[offset:offset + limit]
            if self.list_envelope == "bare":
                return 200, page
            if self.list_envelope == "unknown":
                return 200, {"data": page, "cursor": "fixture"}
            return 200, {"issues": page}
        # /api/companies/{cid}/agents
        if (method == "POST" and len(parts) == 4
                and parts[0] == "api" and parts[1] == "companies"
                and parts[2] == COMPANY_ID and parts[3] == "agents"):
            row = dict(body or {})
            agent_id = str(uuid.uuid4())
            row.update({"id": agent_id, "createdAt": self.now_iso()})
            self.agents[agent_id] = row
            return 200, row
        # /api/agents/me — the REAL board requires an AGENT actor here and
        # refuses this client's local-trusted header with 401 (no-seam
        # proof 1 finding, dev board 2026-11-12).  The fake mirrors that:
        # any client code path that still calls this route fails its test.
        if (method == "GET" and len(parts) == 3 and parts[0] == "api"
                and parts[1] == "agents" and parts[2] == "me"):
            return 401, {"error": "Agent authentication required"}
        # /api/issues/{id}
        if method == "GET" and len(parts) == 3 and parts[0] == "api" \
                and parts[1] == "issues":
            row = self.issues.get(parts[2])
            return (200, row) if row is not None else (404, {"error": "gone"})
        # PATCH /api/issues/{id} — the block relation (RF handle_ask law)
        if (method == "PATCH" and len(parts) == 3 and parts[0] == "api"
                and parts[1] == "issues"):
            row = self.issues.get(parts[2])
            if row is None:
                return 404, {"error": "gone"}
            row.update(body or {})
            return 200, row
        # /api/issues/{id}/comments
        if len(parts) == 4 and parts[0] == "api" and parts[1] == "issues" \
                and parts[3] == "comments":
            rows = self.comments.get(parts[2])
            if rows is None:
                return 404, {"error": "gone"}
            if method == "GET":
                served = [row for row in reversed(rows)   # newest first
                          if row["id"] not in self.lagged_comment_ids]
                if self.comments_envelope == "bare":
                    return 200, served
                if self.comments_envelope == "unknown":
                    return 200, {"data": served}
                return 200, {"comments": served}
            if method == "POST":
                row = dict(body or {})
                row.update({"id": str(uuid.uuid4()),
                            "authorAgentId": self.comment_author,
                            "authorType": self.comment_author_type,
                            "createdAt": self.now_iso()})
                rows.append(row)                    # the write LANDS…
                if self.comment_visibility_lag > 0:
                    self.comment_visibility_lag -= 1
                    self.lagged_comment_ids.add(row["id"])   # …but hides
                return 200, row
        return 404, {"error": "no such route"}


def make_handler(state: FakePaperclipState):
    class Handler(BaseHTTPRequestHandler):
        def _serve(self, method: str) -> None:
            split = urlsplit(self.path)
            clean = split.path
            state.touch(method, clean, dict(self.headers))
            target = state.redirects.get((method, clean))
            if target:
                self.send_response(302)
                self.send_header("Location", target)
                self.send_header("content-length", "0")
                self.end_headers()
                return
            delay = state.slow_paths.get((method, clean))
            if delay:
                time.sleep(delay)          # no mutation happened for these
            status = (state.fail_status.get((method, self.path))
                      if (method, self.path) in state.fail_status
                      else state.fail_status.get((method, clean)))
            length = int(self.headers.get("content-length") or 0)
            body = json.loads(self.rfile.read(length)) if length else None
            state.request_bodies.append(json.dumps(body)
                                        if body is not None else "")
            if status is None:
                status, payload = state.handle(method, clean,
                                               parse_qs(split.query), body)
            else:
                payload = {"error": "fixture failure"}
            raw = json.dumps(payload).encode()
            try:
                if (state.truncate_create and method == "POST" and clean ==
                        f"/api/companies/{COMPANY_ID}/issues"):
                    # the create landed; the reply body is cut in half
                    self.send_response(200)
                    self.send_header("content-type", "application/json")
                    self.send_header("content-length", str(len(raw)))
                    self.end_headers()
                    self.wfile.write(raw[:12])
                    self.close_connection = True
                    return
                self.send_response(status)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)
            except (BrokenPipeError, ConnectionResetError):
                pass                      # the client already timed out

        def do_GET(self):
            self._serve("GET")

        def do_POST(self):
            self._serve("POST")

        def do_PATCH(self):
            self._serve("PATCH")

        def log_message(self, *_args):     # silence the test log
            return

    return Handler


@pytest.fixture()
def fake():
    state = FakePaperclipState()
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(state))
    port = server.server_address[1]
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        yield SimpleNamespace(state=state, base=f"http://127.0.0.1:{port}",
                              port=port)
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=5)


def client(fake, **over) -> PaperclipAskClient:
    kwargs = dict(timeout_seconds=0.5)
    if HMAC_KEY_PATH is not None and "hmac_key_path" not in over:
        kwargs["hmac_key_path"] = HMAC_KEY_PATH
    kwargs.update(over)
    return PaperclipAskClient(fake.base, COMPANY_ID, AGENT_ID, **kwargs)


@pytest.fixture(autouse=True)
def fixture_key(tmp_path) -> Path:
    """Every client in this suite gets the harmless fixture key file (round
    2: the HMAC key is always read from a config-given path, never inlined)."""
    global HMAC_KEY_PATH
    path = tmp_path / "hmac_v1.key"
    path.write_bytes(KEY_BYTES)
    os.chmod(path, 0o600)
    HMAC_KEY_PATH = path
    yield path
    HMAC_KEY_PATH = None


def bridge_over(client_: PaperclipAskClient, **over) -> GblBridge:
    return GblBridge(
        client_,
        admission_table=(PrincipalAdmission(
            principal=PRINCIPAL,
            targets=frozenset({PRINCIPAL}),
            kinds=frozenset({"question"}),
            max_asks_per_hour=20,
        ),),
        now=lambda: datetime.now(timezone.utc),
        **over,
    )


def submits(**over) -> dict:
    args = dict(principal=PRINCIPAL, kind="question", target=PRINCIPAL,
                title="Fixture ask", body="A harmless fixture question.",
                idempotency_key="k-1")
    args.update(over)
    return args


def count(fake, method: str, path: str) -> int:
    return sum(1 for m, p in fake.state.requests if m == method and p == path)


def core_of(event: dict) -> dict:
    """The event without the keys the store adds on read (comment
    provenance is display metadata; seq/trusted are the store's stamps)."""
    return {k: v for k, v in event.items()
            if not k.startswith("comment_") and k not in ("seq", "trusted")}


def stored_comment(fake, issue_id: str, index: int = -1) -> dict:
    """The parsed JSON of a stored comment body (round 2 inspection)."""
    body = str(fake.state.comments[issue_id][index].get("body") or "")
    return json.loads(body[len(pc.EVENT_MARKER) + 1:])


def expect_tag(key: bytes, ask_id: str, seq: int, event: dict) -> str:
    """An INDEPENDENT recomputation of the §2 v1 tag (sorted keys, compact
    separators, UTF-8) — the test does not import the client's helper."""
    message = (ask_id + "\n" + str(seq) + "\n"
               + json.dumps(event, sort_keys=True, separators=(",", ":"),
                            ensure_ascii=False)).encode("utf-8")
    return "v1:" + hmac.new(key, message, hashlib.sha256).hexdigest()


ISSUES_PATH = f"/api/companies/{COMPANY_ID}/issues"


# ── The base URL: required, loopback http only, never a default/reserved port


class TestBaseUrlLaw:
    def test_base_url_is_required(self):
        with pytest.raises(TypeError):
            PaperclipAskClient()                      # type: ignore[call-arg]

    @pytest.mark.parametrize("url", [
        "https://127.0.0.1:3191",            # not http
        "http://example.com:3191",            # not loopback
        "http://10.1.2.3:3191",               # not loopback
        "http://127.0.0.1",                   # no explicit port (a default)
        "http://127.0.0.1:3100",              # the Chairman's instance
        "http://127.0.0.1:3179",              # the known fleet listener
        "http://127.0.0.1:0",                 # L8: port out of range
        "http://127.0.0.1:65536",
        "http://127.0.0.1:99999",
        "http://user:words@127.0.0.1:3191",   # userinfo (credential-shaped)
        "ftp://127.0.0.1:3191",
    ])
    def test_refused_base_urls(self, url):
        with pytest.raises(ValueError):
            PaperclipAskClient(url, COMPANY_ID, AGENT_ID)

    def test_loopback_with_explicit_port_is_accepted(self):
        url = validate_paperclip_base_url("http://localhost:3191/")
        assert url == "http://localhost:3191"

    def test_ipv6_loopback_accepted(self):
        assert validate_paperclip_base_url("http://[::1]:3191")

    def test_credential_header_is_refused(self):
        for header in ("authorization", "Authorization", "x-api-key",
                       "Cookie"):
            with pytest.raises(ValueError):
                PaperclipAskClient("http://127.0.0.1:3191", COMPANY_ID,
                                   AGENT_ID, headers={header: "x"})

    @pytest.mark.parametrize("header", [
        "x-api-token", "X-Secret-Label", "authentication", "bearer-token",
        "x-my-password", "proxy-credentials",
    ])
    def test_more_credential_shaped_headers_are_refused(self, header):
        # L7: the ban is by word, not by five exact names.
        with pytest.raises(ValueError):
            PaperclipAskClient("http://127.0.0.1:3191", COMPANY_ID, AGENT_ID,
                               headers={header: "x"})

    def test_custom_headers_merge_with_the_default(self, fake):
        # L6: a custom header must not silently drop the instance-role header.
        ask_client = PaperclipAskClient(fake.base, COMPANY_ID, AGENT_ID,
                                        headers={"x-custom": "v"})
        ask_client.create_ask(envelope())
        method, path, headers = fake.state.headers_log[-1]
        sent = {key.lower(): value for key, value in headers.items()}
        assert sent.get("x-instance-role") == "local_trusted"
        assert sent.get("x-custom") == "v"


# ── create / read / append / count over the fake server ─────────────────────


class TestStoreMapping:
    def test_create_ask_posts_one_issue_assigned_to_the_service_agent(
            self, fake):
        row = envelope()
        assert client(fake).create_ask(row) is None
        assert count(fake, "POST", ISSUES_PATH) == 1
        issue = fake.state.issues[fake.state.order[0]]
        assert issue["assigneeAgentId"] == AGENT_ID
        assert issue["status"] == "todo"
        assert row["ask_id"] in issue["title"]            # the [gb-…] marker
        description = issue["description"]
        marker, _, payload = description.partition("\n")
        assert marker.startswith("gbl-ask-v1")
        assert json.loads(payload)["ask_id"] == row["ask_id"]

    def test_read_ask_returns_envelope_plus_events(self, fake):
        row = envelope()
        client(fake).create_ask(row)
        record = client(fake).read_ask(row["ask_id"])
        assert record is not None
        assert {k: v for k, v in record.items() if k != "events"} == row
        assert record["events"] == []

    def test_read_ask_unknown_id_is_none(self, fake):
        assert client(fake).read_ask("gb-" + "0" * 32) is None

    def test_append_ask_event_is_one_comment_idempotent_by_content(
            self, fake):
        row = envelope()
        ask_client = client(fake)
        ask_client.create_ask(row)
        event = {"type": "answer", "answer_id": "gbm-" + "a" * 32,
                 "idempotency_key": "a-1", "text": "A harmless fixture answer."}
        ask_client.append_ask_event(row["ask_id"], event)
        ask_client.append_ask_event(row["ask_id"], event)   # redelivery
        issue_id = fake.state.order[0]
        comments_path = f"/api/issues/{issue_id}/comments"
        assert count(fake, "POST", comments_path) == 1      # ONE comment
        record = ask_client.read_ask(row["ask_id"])
        assert [core_of(e) for e in record["events"]] == [event]

    def test_events_are_returned_oldest_first(self, fake):
        ask_client = client(fake)
        row = envelope()
        ask_client.create_ask(row)
        first = {"type": "state", "state": "ANSWERED"}
        second = {"type": "state", "state": "CONSUMED"}
        ask_client.append_ask_event(row["ask_id"], first)
        ask_client.append_ask_event(row["ask_id"], second)
        # The fake answers newest-first, like the real API.
        assert [core_of(e) for e in
                ask_client.read_ask(row["ask_id"])["events"]] == [first, second]

    def test_foreign_comment_body_is_ignored_as_data(self, fake):
        ask_client = client(fake)
        row = envelope()
        ask_client.create_ask(row)
        issue_id = fake.state.order[0]
        fake.state.comments[issue_id].append({
            "id": str(uuid.uuid4()),
            "authorAgentId": "human-commenter-fixture",
            "createdAt": fake.state.now_iso(),
            "body": "human words, not a gbl event"})
        record = ask_client.read_ask(row["ask_id"])
        assert record["events"] == []            # untrusted text, never parsed

    def test_count_asks_filters_principal_and_window(self, fake):
        ask_client = client(fake)
        old = datetime.now(timezone.utc) - timedelta(hours=2)
        fake.state.next_created_at = old.isoformat()
        ask_client.create_ask(envelope(key="k-old"))
        ask_client.create_ask(envelope(key="k-new"))
        ask_client.create_ask(envelope(key="k-other",
                                       principal="grok-account-other"))
        since = (datetime.now(timezone.utc) - timedelta(hours=1)
                 ).strftime("%Y-%m-%dT%H:%M:%SZ")
        assert ask_client.count_asks(PRINCIPAL, since) == 1
        early = (datetime.now(timezone.utc) - timedelta(hours=3)
                 ).strftime("%Y-%m-%dT%H:%M:%SZ")
        assert ask_client.count_asks(PRINCIPAL, early) == 2

    def test_create_service_agent_payload(self, fake):
        row = create_service_agent(fake.base, COMPANY_ID,
                                   name="Grok Bridge", role="service")
        assert row["id"] in fake.state.agents
        agent = fake.state.agents[row["id"]]
        assert agent["name"] == "Grok Bridge"
        assert agent["adapterType"] == "process"
        assert agent["runtimeConfig"] == {"heartbeat": {"enabled": False}}


# ── H2: pagination to exhaustion; counting fails closed on any doubt ────────


class TestPagination:
    @pytest.fixture(autouse=True)
    def small_pages(self, monkeypatch):
        monkeypatch.setattr(pc, "LIST_PAGE_LIMIT", 2)

    def seed(self, fake, n: int, principal: str = PRINCIPAL) -> list[str]:
        ask_client = client(fake)
        ids = []
        for index in range(n):
            row = envelope(key=f"k-{index}", principal=principal)
            ask_client.create_ask(row)
            ids.append(row["ask_id"])
        return ids

    def test_count_asks_reads_every_page(self, fake):
        self.seed(fake, 5)
        fresh = client(fake)
        since = (datetime.now(timezone.utc) - timedelta(hours=1)
                 ).strftime("%Y-%m-%dT%H:%M:%SZ")
        assert fresh.count_asks(PRINCIPAL, since) == 5   # not the first page

    def test_scan_finds_an_ask_beyond_page_one(self, fake):
        ids = self.seed(fake, 3)
        record = client(fake).read_ask(ids[0])   # oldest, on page 2
        assert record is not None
        assert record["ask_id"] == ids[0]

    def test_bare_list_envelope_is_also_accepted(self, fake):
        self.seed(fake, 3)
        fake.state.list_envelope = "bare"
        since = (datetime.now(timezone.utc) - timedelta(hours=1)
                 ).strftime("%Y-%m-%dT%H:%M:%SZ")
        assert client(fake).count_asks(PRINCIPAL, since) == 3

    def test_server_ignoring_offset_fails_closed(self, fake):
        self.seed(fake, 3)
        fake.state.ignore_offset = True
        since = (datetime.now(timezone.utc) - timedelta(hours=1)
                 ).strftime("%Y-%m-%dT%H:%M:%SZ")
        with pytest.raises(GblPaperclipError):
            client(fake).count_asks(PRINCIPAL, since)
        with pytest.raises(GblPaperclipError):
            client(fake).read_ask("gb-" + "0" * 32)   # any scan

    def test_unknown_list_envelope_is_a_typed_error(self, fake):
        # M5: never read as "no asks" — that would duplicate creates.
        self.seed(fake, 1)
        fake.state.list_envelope = "unknown"
        since = (datetime.now(timezone.utc) - timedelta(hours=1)
                 ).strftime("%Y-%m-%dT%H:%M:%SZ")
        with pytest.raises(GblPaperclipTransportError):
            client(fake).count_asks(PRINCIPAL, since)
        with pytest.raises(GblPaperclipTransportError):
            client(fake).read_ask("gb-" + "1" * 32)

    def test_non_dict_rows_in_the_list_are_a_typed_error(self, fake,
                                                         monkeypatch):
        self.seed(fake, 1)
        real_handle = fake.state.handle

        def handle(method, path, query, body):
            if (method == "GET" and path == ISSUES_PATH
                    and fake.state.list_envelope != "unknown"):
                fake.state.list_envelope = "unknown"
                return 200, {"data": [1, 2]}          # junk rows
            return real_handle(method, path, query, body)

        fake.state.handle = handle
        since = (datetime.now(timezone.utc) - timedelta(hours=1)
                 ).strftime("%Y-%m-%dT%H:%M:%SZ")
        with pytest.raises(GblPaperclipTransportError):
            client(fake).count_asks(PRINCIPAL, since)


# ── H4: robust envelope parsing — corruption is never read as absence ───────


class TestRobustParse:
    def test_appended_footer_text_is_tolerated(self, fake):
        ask_client = client(fake)
        row = envelope()
        ask_client.create_ask(row)
        issue = fake.state.issues[fake.state.order[0]]
        issue["description"] += "\n-- forwarded by a human --\nsee also: none"
        record = ask_client.read_ask(row["ask_id"])
        assert record is not None
        assert record["ask_id"] == row["ask_id"]

    def test_reflowed_marker_mid_text_is_tolerated(self, fake):
        ask_client = client(fake)
        row = envelope()
        ask_client.create_ask(row)
        issue = fake.state.issues[fake.state.order[0]]
        payload = issue["description"].split("\n", 1)[1]
        issue["description"] = (f"some provenance header\nreplied: "
                                f"gbl-ask-v1 record follows\n{payload}\n"
                                f"tail note")
        record = ask_client.read_ask(row["ask_id"])
        assert record is not None
        assert record["ask_id"] == row["ask_id"]

    def test_corrupt_marker_payload_is_a_typed_error(self, fake):
        # Never "absent": reading corruption as absence duplicates creates.
        ask_client = client(fake)
        row = envelope()
        ask_client.create_ask(row)
        issue = fake.state.issues[fake.state.order[0]]
        issue["description"] = "gbl-ask-v1 record {broken json"
        with pytest.raises(GblPaperclipError) as err:
            ask_client.read_ask(row["ask_id"])
        assert "RECORD_INVALID" in err.value.code
        since = (datetime.now(timezone.utc) - timedelta(hours=1)
                 ).strftime("%Y-%m-%dT%H:%M:%SZ")
        with pytest.raises(GblPaperclipError):        # count fails closed too
            ask_client.count_asks(PRINCIPAL, since)

    def test_a_corrupt_decoy_bricks_the_scan_not_the_match(self, fake):
        ask_client = client(fake)
        row = envelope()
        ask_client.create_ask(row)
        fake.state.add_issue("GBL decoy", "gbl-ask-v1 { nope")
        with pytest.raises(GblPaperclipError):
            client(fake).read_ask(row["ask_id"])      # scan hits the decoy


# ── M3: exact-key resolution; a title substring never resolves ──────────────


class TestExactResolution:
    def test_decoy_title_substring_never_resolves(self, fake):
        ask_client = client(fake)
        row = envelope()
        ask_client.create_ask(row)
        real_issue = fake.state.order[0]
        decoy = fake.state.add_issue(
            f"GBL [{row['ask_id']}] embedded in a decoy title",
            "human words about {json} shapes")
        record_finder = client(fake)
        record = record_finder.read_ask(row["ask_id"])  # decoy sorts first
        assert record is not None
        assert record["ask_id"] == row["ask_id"]
        assert record_finder._issue_ids[row["ask_id"]] == real_issue
        # and a write goes to the real issue, never the decoy
        ask_client.append_ask_event(row["ask_id"],
                                    {"type": "state", "state": "ANSWERED"})
        assert fake.state.comments[decoy] == []
        assert len(fake.state.comments[real_issue]) == 1

    def test_decoy_only_presence_is_not_the_ask(self, fake):
        row = envelope()
        fake.state.add_issue(f"GBL [{row['ask_id']}] decoy",
                             "human words, no marker")
        assert client(fake).read_ask(row["ask_id"]) is None

    def test_cached_issue_that_stopped_matching_is_resolved_again(self, fake):
        ask_client = client(fake)
        row = envelope()
        ask_client.create_ask(row)
        assert ask_client.read_ask(row["ask_id"]) is not None
        issue = fake.state.issues[fake.state.order[0]]
        issue["description"] = "human edit erased the record"
        # the cache no longer holds this ask; never a false hit
        assert ask_client.read_ask(row["ask_id"]) is None


# ── §1.1: create_ask is CREATE-IF-ABSENT (no second record, ever) ────────────


class TestCreateIfAbsent:
    def test_second_create_returns_the_existing_record(self, fake):
        ask_client = client(fake)
        row = envelope()
        assert ask_client.create_ask(row) is None          # created
        again = client(fake).create_ask(row)               # fresh client
        assert again is not None                           # §1.1: the record
        assert again["ask_id"] == row["ask_id"]
        assert again["events"] == []
        assert count(fake, "POST", ISSUES_PATH) == 1       # never a second
        assert len(fake.state.order) == 1                  # issue

    def test_the_returned_record_is_a_copy(self, fake):
        ask_client = client(fake)
        row = envelope()
        ask_client.create_ask(row)
        again = ask_client.create_ask(row)
        assert again is not None
        again["title"] = "mutated by the caller"
        again["events"].append({"type": "state", "state": "ANSWERED"})
        fresh = ask_client.read_ask(row["ask_id"])
        assert fresh["title"] == row["title"]
        assert fresh["events"] == []

    def test_replay_through_the_bridge_never_duplicates(self, fake):
        core = bridge_over(client(fake))
        first = core.submit_ask(**submits())
        assert first["status"] == "CREATED"
        second = core.submit_ask(**submits())     # same key + same text
        assert second["status"] == "IDEMPOTENT"
        assert count(fake, "POST", ISSUES_PATH) == 1
        assert second["ask"]["ask_id"] == first["ask"]["ask_id"]

    def test_ambiguous_landing_then_replay_still_one_issue(self, fake):
        # M7 + §1.1: the 409 landed; the read-back reconcile classifies it,
        # and the NEXT create-if-absent check returns the record (no POST).
        fake.state.create_reply_status = 409
        core = bridge_over(client(fake))
        assert core.submit_ask(**submits())["status"] == "IDEMPOTENT"
        assert core.submit_ask(**submits())["status"] == "IDEMPOTENT"
        assert count(fake, "POST", ISSUES_PATH) == 1

    def test_precheck_failure_is_typed_not_effect_unknown(self, fake):
        # The pre-create absence check failing is NOT an unknown create
        # effect (nothing began): the typed read error propagates and no
        # create POST is issued.
        ask_client = client(fake)
        ask_client.create_ask(envelope())
        fake.state.fail_status[("GET", ISSUES_PATH)] = 503
        with pytest.raises(GblPaperclipServerError):
            ask_client.create_ask(envelope(key="k-2"))
        assert count(fake, "POST", ISSUES_PATH) == 1

    def test_key_reuse_with_new_text_is_conflict_not_duplicate(self, fake):
        core = bridge_over(client(fake))
        core.submit_ask(**submits())
        with pytest.raises(GblBridgeError) as err:
            core.submit_ask(**submits(body="Different harmless fixture text."))
        assert err.value.code == "CONFLICT"
        assert count(fake, "POST", ISSUES_PATH) == 1


class TestAmbiguousCreateGuard:
    """Panel B delta-2 F1: a foreign edit that removes the marker line
    entirely makes the ask read as ABSENT; a create replay of the same
    deterministic ask id must REFUSE (typed ``AMBIGUOUS_CREATE``) rather
    than mint a duplicate whose empty record strands the stored events."""

    def test_marker_removal_replay_refuses_and_strands_nothing(self, fake):
        ask_client = client(fake)
        row = envelope()
        assert ask_client.create_ask(row) is None
        ask_id = row["ask_id"]
        ask_client.append_ask_event(
            ask_id, {"type": "answer", "answer_id": "gbm-" + "a" * 32,
                     "idempotency_key": "a-1",
                     "text": "A harmless fixture answer."})
        issue_id = fake.state.order[0]
        original = fake.state.issues[issue_id]["description"]
        # A foreign edit blanks the description: no marker, no envelope.
        fake.state.issues[issue_id]["description"] = \
            "human prose, the record line removed"
        assert ask_client.read_ask(ask_id) is None      # reads as ABSENT
        with pytest.raises(GblPaperclipError) as err:
            ask_client.create_ask(row)                  # the replay
        assert err.value.code == "AMBIGUOUS_CREATE"
        # No duplicate was minted and nothing was sent.
        assert len(fake.state.order) == 1
        assert count(fake, "POST", ISSUES_PATH) == 1    # only the original
        # The stored answer is not stranded: the original issue still
        # holds its event comments, and restoring the description (the
        # out-of-band repair) reads the full record back.
        comments = fake.state.comments[issue_id]
        assert len(comments) == 1 and "harmless fixture answer" in \
            str(comments[0]["body"])
        fake.state.issues[issue_id]["description"] = original
        record = ask_client.read_ask(ask_id)
        assert record is not None and record["ask_id"] == ask_id
        assert [e["type"] for e in record["events"]] == ["answer"]
        assert all(e["trusted"] is True for e in record["events"])

    def test_the_guard_is_keyed_to_the_exact_ask_id(self, fake):
        # A different ask's create is never refused by this ask's issue:
        # the token is the exact bracketed id of the ask being created.
        ask_client = client(fake)
        row = envelope(key="k-1")
        assert ask_client.create_ask(row) is None
        issue_id = fake.state.order[0]
        fake.state.issues[issue_id]["description"] = "marker removed"
        assert ask_client.create_ask(envelope(key="k-2")) is None  # created
        assert len(fake.state.order) == 2           # the lawful second issue


# ── EFFECT_UNKNOWN: a lost create is reconciled by read-back, never retried ──


class TestCreateEffectUnknown:
    def test_timeout_after_landing_raises_effect_unknown(self, fake):
        fake.state.create_delay = 1.5          # lands, then sleeps past 0.5s
        with pytest.raises(GblCreateEffectUnknown):
            client(fake).create_ask(envelope())
        assert count(fake, "POST", ISSUES_PATH) == 1   # the one create landed

    def test_read_back_finds_the_ask_after_a_lost_reply(self, fake):
        fake.state.create_delay = 1.5
        ask_client = client(fake)
        row = envelope()
        with pytest.raises(GblCreateEffectUnknown):
            ask_client.create_ask(row)
        record = ask_client.read_ask(row["ask_id"])     # the scan path
        assert record is not None
        assert record["ask_id"] == row["ask_id"]

    def test_bridge_reconciles_by_read_back_with_one_create_only(self, fake):
        fake.state.create_delay = 1.5
        ask_client = client(fake)
        core = bridge_over(ask_client)
        result = core.submit_ask(**submits())          # lost reply, landed
        assert result["status"] == "IDEMPOTENT"
        fake.state.create_delay = 0.0
        again = core.submit_ask(**submits())           # same key, replay
        assert again["status"] == "IDEMPOTENT"
        assert count(fake, "POST", ISSUES_PATH) == 1   # never a second create
        assert again["ask"]["ask_id"] == result["ask"]["ask_id"]

    def test_definite_refusal_is_not_effect_unknown(self, fake):
        ask_client = client(fake)
        core = bridge_over(ask_client)
        # A create the server refused before performing anything: a definite
        # refusal (4xx) surfaces as the typed client error, not as an
        # unknown effect — and no read-back reconcile is needed.
        fake.state.create_fail_status = 422
        with pytest.raises(GblPaperclipClientError):
            core.submit_ask(**submits())

    def test_transport_loss_without_landing_never_retries_the_create(self):
        # Nothing answers on this loopback port: the create cannot be proven
        # absent, so the law is the same — the client reports the lost
        # outcome (EffectUnknown) and the bridge's ONE reconcile read-back
        # surfaces the typed transport failure.  No code path issues a
        # second create.
        dead = PaperclipAskClient("http://127.0.0.1:1", COMPANY_ID, AGENT_ID,
                                  timeout_seconds=0.2)
        with pytest.raises(GblPaperclipTransportError):
            bridge_over(dead).submit_ask(**submits())

    @pytest.mark.parametrize("status", [408, 409, 425, 429, 499])
    def test_ambiguous_4xx_after_landing_is_effect_unknown(self, fake,
                                                           status):
        # M7: the create may already have landed — never "not created".
        fake.state.create_reply_status = status
        with pytest.raises(GblCreateEffectUnknown):
            client(fake).create_ask(envelope())

    def test_bridge_reconciles_after_an_ambiguous_409(self, fake):
        fake.state.create_reply_status = 409
        core = bridge_over(client(fake))
        result = core.submit_ask(**submits())
        assert result["status"] == "IDEMPOTENT"        # read-back found it
        assert count(fake, "POST", ISSUES_PATH) == 1

    @pytest.mark.parametrize("status", [400, 404, 422])
    def test_definite_4xx_stays_a_client_error(self, fake, status):
        fake.state.create_fail_status = status
        with pytest.raises(GblPaperclipClientError):
            client(fake).create_ask(envelope())

    def test_truncated_create_reply_is_effect_unknown(self, fake):
        # M8: http.client.IncompleteRead is an HTTPException — it must land
        # in the typed effect-unknown path, never escape raw.
        fake.state.truncate_create = True
        ask_client = client(fake)
        with pytest.raises(GblCreateEffectUnknown):
            ask_client.create_ask(envelope())
        assert len(fake.state.order) == 1              # it actually landed
        core = bridge_over(ask_client)
        assert core.submit_ask(**submits())["status"] == "IDEMPOTENT"
        assert count(fake, "POST", ISSUES_PATH) == 1   # reconciled, not redone


# ── M6: no redirect following; the URL law holds on every request ───────────


class TestNoRedirects:
    def test_3xx_is_a_typed_error_and_is_never_followed(self, fake):
        canary = f"http://127.0.0.1:{fake.port}/canary"
        fake.state.redirects[("GET", ISSUES_PATH)] = canary
        since = (datetime.now(timezone.utc) - timedelta(hours=1)
                 ).strftime("%Y-%m-%dT%H:%M:%SZ")
        with pytest.raises(pc.GblPaperclipRedirectError):
            client(fake).count_asks(PRINCIPAL, since)
        assert count(fake, "GET", "/canary") == 0      # never followed

    def test_redirect_on_create_is_effect_unknown(self, fake):
        canary = f"http://127.0.0.1:{fake.port}/canary"
        fake.state.redirects[("POST", ISSUES_PATH)] = canary
        with pytest.raises(GblCreateEffectUnknown):    # effect not certified
            client(fake).create_ask(envelope())
        assert count(fake, "GET", "/canary") == 0
        assert count(fake, "POST", "/canary") == 0


# ── M9: strict id charset; percent-encoded path segments ────────────────────


class TestIdLaw:
    @pytest.mark.parametrize("company_id", [
        "../x", "a/b", "a b", "a?b", "a#b", ".", "..", "", "a%2fb",
    ])
    def test_company_id_outside_the_charset_is_refused(self, company_id):
        with pytest.raises(ValueError):
            PaperclipAskClient("http://127.0.0.1:3191", company_id, AGENT_ID)

    @pytest.mark.parametrize("agent_id", ["../../admin", "a b", ""])
    def test_agent_id_outside_the_charset_is_refused(self, agent_id):
        with pytest.raises(ValueError):
            PaperclipAskClient("http://127.0.0.1:3191", COMPANY_ID, agent_id)

    def test_server_issue_id_outside_the_charset_is_a_typed_error(self, fake,
                                                                  monkeypatch):
        # A server row whose id could rewrite a path is refused, never used.
        real_handle = fake.state.handle

        def handle(method, path, query, body):
            status, payload = real_handle(method, path, query, body)
            if isinstance(payload, dict) and "id" in payload and \
                    payload.get("description"):
                payload = dict(payload)
                payload["id"] = "../../admin?x="      # hostile server data
            return status, payload

        fake.state.handle = handle
        with pytest.raises(GblCreateEffectUnknown):   # unusable create reply
            client(fake).create_ask(envelope())

    def test_hostile_list_row_id_is_refused(self, fake):
        fake.state.add_issue("GBL decoy", "human words")
        first = fake.state.order[0]
        fake.state.issues[first]["id"] = "../evil"
        since = (datetime.now(timezone.utc) - timedelta(hours=1)
                 ).strftime("%Y-%m-%dT%H:%M:%SZ")
        with pytest.raises(GblPaperclipError):
            client(fake).count_asks(PRINCIPAL, since)

    def test_legitimate_request_paths_are_unchanged(self, fake):
        ask_client = client(fake)
        row = envelope()
        ask_client.create_ask(row)
        assert count(fake, "POST", ISSUES_PATH) == 1
        assert client(fake).read_ask(row["ask_id"]) is not None  # a scan
        assert count(fake, "GET", ISSUES_PATH) >= 1              # same route
        assert count(fake, "POST", ISSUES_PATH) == 1             # no rewrite


# ── M4: comments envelope fails closed; M1/M2: provenance exposed ───────────


class TestCommentsFailClosed:
    def test_unknown_comments_envelope_is_a_typed_error(self, fake):
        # M4: never an empty list — invisible events would admit a second
        # answer.
        ask_client = client(fake)
        row = envelope()
        ask_client.create_ask(row)
        fake.state.comments_envelope = "unknown"
        with pytest.raises(GblPaperclipTransportError):
            ask_client.read_ask(row["ask_id"])

    def test_non_dict_comment_rows_are_a_typed_error(self, fake):
        ask_client = client(fake)
        row = envelope()
        ask_client.create_ask(row)
        issue_id = fake.state.order[0]
        fake.state.comments[issue_id].append("not a dict")
        with pytest.raises(GblPaperclipTransportError):
            ask_client.read_ask(row["ask_id"])


class TestCommentProvenance:
    def test_events_carry_author_and_a_total_order(self, fake):
        # M1/M2 client side: the bridge must be able to trust only the
        # bridge agent's own comments and order them totally.
        ask_client = client(fake)
        row = envelope()
        ask_client.create_ask(row)
        ask_client.append_ask_event(row["ask_id"],
                                    {"type": "state", "state": "ANSWERED"})
        fake.state.comment_author = "someone-else-fixture"   # a forged hand
        ask_client.append_ask_event(row["ask_id"],
                                    {"type": "state", "state": "CONSUMED"})
        record = ask_client.read_ask(row["ask_id"])
        events = record["events"]
        assert [core_of(e) for e in events] == [
            {"type": "state", "state": "ANSWERED"},
            {"type": "state", "state": "CONSUMED"}]
        assert events[0]["comment_author"] == AGENT_ID
        assert events[1]["comment_author"] == "someone-else-fixture"
        orders = [e["comment_order"] for e in events]
        assert orders == sorted(orders) and len(set(orders)) == len(orders)
        assert events[0]["comment_id"] and events[1]["comment_id"]

    def test_same_timestamp_ties_order_totally(self, fake):
        ask_client = client(fake)
        row = envelope()
        ask_client.create_ask(row)
        issue_id = fake.state.order[0]
        same = fake.state.now_iso()
        # Deterministic ids: the total order is (createdAt, id), so a random
        # uuid pair would make the expected order a coin flip.
        for index, state in enumerate(("ANSWERED", "CONSUMED"), start=1):
            fake.state.comments[issue_id].append({
                "id": f"c-{index}", "authorAgentId": AGENT_ID,
                "createdAt": same,
                "body": pc.EVENT_MARKER + " " +
                        json.dumps({"type": "state", "state": state},
                                   sort_keys=True, separators=(",", ":"))})
        events = ask_client.read_ask(row["ask_id"])["events"]
        orders = [e["comment_order"] for e in events]
        assert orders == sorted(orders) and len(set(orders)) == len(orders)
        assert [e["state"] for e in events] == ["ANSWERED", "CONSUMED"]

    def test_authorless_comment_reports_none(self, fake):
        ask_client = client(fake)
        row = envelope()
        ask_client.create_ask(row)
        issue_id = fake.state.order[0]
        fake.state.comments[issue_id].append({
            "id": str(uuid.uuid4()), "createdAt": fake.state.now_iso(),
            "body": pc.EVENT_MARKER + " " +
                    json.dumps({"type": "state", "state": "ANSWERED"},
                               sort_keys=True, separators=(",", ":"))})
        events = ask_client.read_ask(row["ask_id"])["events"]
        assert events[0]["comment_author"] is None


# ── §1.2 + §2: seq stamping, the HMAC v1 tag, untrusted surfacing ────────────


class TestEventSeqAndTrust:
    def seed_ask(self, fake, key: str = "k-1") -> tuple[PaperclipAskClient, dict]:
        ask_client = client(fake)
        row = envelope(key=key)
        assert ask_client.create_ask(row) is None
        return ask_client, row

    def test_appends_are_stamped_with_increasing_seq(self, fake):
        ask_client, row = self.seed_ask(fake)
        ask_client.append_ask_event(row["ask_id"],
                                    {"type": "state", "state": "ANSWERED"})
        ask_client.append_ask_event(row["ask_id"],
                                    {"type": "state", "state": "CONSUMED"})
        issue_id = fake.state.order[0]
        first = stored_comment(fake, issue_id, 0)
        second = stored_comment(fake, issue_id, 1)
        assert first["seq"] == 1 and type(first["seq"]) is int
        assert second["seq"] == 2

    def test_seq_is_per_record_and_stateless(self, fake):
        # A FRESH client (new bridge instance, empty cache) still continues
        # the record's sequence: derivation is from the stored record.
        ask_client, row = self.seed_ask(fake)
        ask_client.append_ask_event(row["ask_id"],
                                    {"type": "state", "state": "ANSWERED"})
        fresh = client(fake)                       # no shared state
        fresh.append_ask_event(row["ask_id"],
                               {"type": "state", "state": "CONSUMED"})
        issue_id = fake.state.order[0]
        assert [stored_comment(fake, issue_id, i)["seq"] for i in (0, 1)] == [1, 2]

    def test_the_tag_is_written_and_independently_verifies(self, fake):
        ask_client, row = self.seed_ask(fake)
        event = {"type": "answer", "answer_id": "gbm-" + "a" * 32,
                 "idempotency_key": "a-1", "text": "A harmless fixture answer."}
        ask_client.append_ask_event(row["ask_id"], event)
        issue_id = fake.state.order[0]
        stored = stored_comment(fake, issue_id)
        assert stored["tag"].startswith("v1:")
        # §2.2 message: ask_id + "\n" + str(seq) + "\n" + canonical JSON of
        # the event without the tag — recomputed here without the client.
        assert stored["tag"] == expect_tag(KEY_BYTES, row["ask_id"], 1, {
            **event, "seq": 1})

    def test_reads_surface_trusted_events_with_int_seq(self, fake):
        ask_client, row = self.seed_ask(fake)
        ask_client.append_ask_event(row["ask_id"],
                                    {"type": "state", "state": "ANSWERED"})
        events = ask_client.read_ask(row["ask_id"])["events"]
        assert len(events) == 1
        assert events[0]["trusted"] is True
        assert events[0]["seq"] == 1
        assert "tag" not in events[0]              # storage metadata only

    def test_nudge_settled_is_persisted_and_signed_like_any_event(self, fake):
        # GBL_REPAIR1_NOTES §3 at e5a69f9ff: `nudge_settled` is a first-class
        # event kind — the store stamps, signs and surfaces it generically,
        # exactly like a state or answer event.
        ask_client, row = self.seed_ask(fake)
        settled = {"type": "nudge_settled", "outcome": "NOT_DELIVERED",
                   "state": "ANSWERED", "at": "2026-11-11T22:33:00Z"}
        ask_client.append_ask_event(row["ask_id"], dict(settled))
        issue_id = fake.state.order[0]
        stored = stored_comment(fake, issue_id)
        assert stored["seq"] == 1
        assert stored["tag"] == expect_tag(
            KEY_BYTES, row["ask_id"], 1, {**settled, "seq": 1})
        events = ask_client.read_ask(row["ask_id"])["events"]
        assert [e["type"] for e in events] == ["nudge_settled"]
        assert events[0]["outcome"] == "NOT_DELIVERED"
        assert events[0]["trusted"] is True

    def test_trusted_is_exactly_a_bool(self, fake):
        # GBL_REPAIR1_NOTES §1.2 at e5a69f9ff: `trusted` must be exactly a
        # JSON bool on every surfaced event — trusted and untrusted alike.
        ask_client, row = self.seed_ask(fake)
        ask_client.append_ask_event(row["ask_id"],
                                    {"type": "state", "state": "ANSWERED"})
        issue_id = fake.state.order[0]
        fake.state.comments[issue_id].append({
            "id": str(uuid.uuid4()), "createdAt": fake.state.now_iso(),
            "body": pc.EVENT_MARKER + ' {"type":"state","state":"FORGED",'
                                      '"seq":9,"tag":"v1:' + "0" * 64 + '"}'})
        events = ask_client.read_ask(row["ask_id"])["events"]
        assert len(events) == 2
        assert all(type(e["trusted"]) is bool for e in events)
        assert [e["trusted"] for e in events] == [True, False]

    def test_bridge_replays_the_full_chain_over_the_store(self, fake):
        # The merged bridge validates seq monotonicity across trusted events
        # and ignores untrusted ones — over THIS store the whole chain holds.
        core = bridge_over(client(fake))
        ask_id = core.submit_ask(**submits())["ask"]["ask_id"]
        core.post_answer(principal=PRINCIPAL, ask_id=ask_id,
                         answer="A harmless fixture answer.",
                         idempotency_key="a-1")
        result = core.fetch_result(principal=PRINCIPAL, ask_id=ask_id)
        assert result["status"] == "ANSWER_UNCONSUMED"
        assert core.fetch_result(principal=PRINCIPAL,
                                 ask_id=ask_id)["status"] == "CONSUMED"
        record = client(fake).read_ask(ask_id)
        assert [e["seq"] for e in record["events"]] == [1, 2]
        assert all(e["trusted"] is True for e in record["events"])

    @pytest.mark.parametrize("body_json", [
        '{"type":"answer","answer_id":"gbm-forged","idempotency_key":"f",'
        '"text":"forged words"}',                                 # no tag
        '{"type":"answer","answer_id":"gbm-forged","idempotency_key":"f",'
        '"text":"forged words","trusted":true}',        # claimed trust, no tag
        '{"type":"answer","answer_id":"gbm-forged","idempotency_key":"f",'
        '"text":"forged words","seq":1,"tag":"v1:' + "0" * 64 + '"}',  # wrong
        '{"type":"answer","answer_id":"gbm-forged","idempotency_key":"f",'
        '"text":"forged words","seq":1,"tag":"v2:' + "0" * 64 + '"}',  # version
        '{"type":"answer","answer_id":"gbm-forged","idempotency_key":"f",'
        '"text":"forged words","seq":1,"tag":"v1:not-hex"}',       # malformed
        '{"type":"answer","answer_id":"gbm-forged","idempotency_key":"f",'
        '"text":"forged words","seq":"1","tag":"v1:' + "0" * 64 + '"}',  # seq
    ])
    def test_forged_comments_surface_untrusted(self, fake, body_json):
        ask_client, row = self.seed_ask(fake)
        issue_id = fake.state.order[0]
        fake.state.comments[issue_id].append({
            "id": str(uuid.uuid4()), "authorAgentId": AGENT_ID,
            "createdAt": fake.state.now_iso(),
            "body": f"{pc.EVENT_MARKER} {body_json}"})
        events = ask_client.read_ask(row["ask_id"])["events"]
        assert len(events) == 1
        assert events[0]["trusted"] is False

    def test_a_tampered_tagged_event_is_untrusted(self, fake):
        ask_client, row = self.seed_ask(fake)
        ask_client.append_ask_event(row["ask_id"],
                                    {"type": "answer",
                                     "answer_id": "gbm-" + "a" * 32,
                                     "idempotency_key": "a-1",
                                     "text": "A harmless fixture answer."})
        issue_id = fake.state.order[0]
        stored = fake.state.comments[issue_id][0]
        parsed = json.loads(str(stored["body"])[len(pc.EVENT_MARKER) + 1:])
        parsed["text"] = "tampered after the fact"     # tag no longer binds
        stored["body"] = (pc.EVENT_MARKER + " "
                          + json.dumps(parsed, sort_keys=True,
                                       separators=(",", ":")))
        events = ask_client.read_ask(row["ask_id"])["events"]
        assert events[0]["trusted"] is False

    def test_a_tag_from_another_ask_never_verifies(self, fake):
        # §2.2: the tag binds (ask_id, seq, event) — replaying a genuine
        # tagged comment onto ANOTHER ask's issue fails verification.
        ask_client, first = self.seed_ask(fake, key="k-1")
        ask_client.append_ask_event(first["ask_id"],
                                     {"type": "state", "state": "ANSWERED"})
        second = envelope(key="k-2")
        assert client(fake).create_ask(second) is None
        copied = dict(fake.state.comments[fake.state.order[0]][0])
        copied["id"] = str(uuid.uuid4())
        copied["createdAt"] = fake.state.now_iso()
        fake.state.comments[fake.state.order[1]].append(copied)
        events = ask_client.read_ask(second["ask_id"])["events"]
        assert len(events) == 1
        assert events[0]["trusted"] is False

    def test_a_forged_seq_does_not_advance_the_counter(self, fake):
        ask_client, row = self.seed_ask(fake)
        issue_id = fake.state.order[0]
        fake.state.comments[issue_id].append({
            "id": str(uuid.uuid4()), "createdAt": fake.state.now_iso(),
            "body": pc.EVENT_MARKER + ' {"type":"state","state":"ANSWERED",'
                                      '"seq":999,"tag":"v1:' + "0" * 64 + '"}'})
        ask_client.append_ask_event(row["ask_id"],
                                    {"type": "state", "state": "CONSUMED"})
        stored = stored_comment(fake, issue_id, 1)
        assert stored["seq"] == 1                     # forged 999 ignored

    def test_append_is_idempotent_by_core_content(self, fake):
        ask_client, row = self.seed_ask(fake)
        event = {"type": "state", "state": "ANSWERED"}
        ask_client.append_ask_event(row["ask_id"], event)
        ask_client.append_ask_event(row["ask_id"], dict(event))  # redelivery
        issue_id = fake.state.order[0]
        comments_path = f"/api/issues/{issue_id}/comments"
        assert count(fake, "POST", comments_path) == 1
        assert len(fake.state.comments[issue_id]) == 1

    def test_store_stamps_incoming_seq_and_tag_keys(self, fake):
        # The store is the only stamper (§1.2): incoming seq/tag/trusted keys
        # are never written through, whatever the caller passed.
        ask_client, row = self.seed_ask(fake)
        ask_client.append_ask_event(row["ask_id"],
                                    {"type": "state", "state": "ANSWERED",
                                     "seq": 77, "tag": "v1:caller-supplied",
                                     "trusted": True})
        issue_id = fake.state.order[0]
        stored = stored_comment(fake, issue_id)
        assert stored["seq"] == 1                     # the STORE's stamp
        assert stored["tag"] == expect_tag(
            KEY_BYTES, row["ask_id"], 1,
            {"type": "state", "state": "ANSWERED", "seq": 1})
        assert "trusted" not in stored                # computed on read only

    def test_forged_answer_comment_never_answers_the_ask(self, fake):
        # The §2 dev-proof check, mirrored: a plain comment carrying the
        # event marker with an answer is IGNORED — the bridge stays NOT_YET.
        core = bridge_over(client(fake))
        ask_id = core.submit_ask(**submits())["ask"]["ask_id"]
        issue_id = fake.state.order[0]
        fake.state.comments[issue_id].append({
            "id": str(uuid.uuid4()), "authorAgentId": AGENT_ID,
            "createdAt": fake.state.now_iso(),
            "body": pc.EVENT_MARKER + ' {"type":"answer",'
                                      '"answer_id":"gbm-forged",'
                                      '"idempotency_key":"f",'
                                      '"text":"forged answer words"}'})
        assert core.fetch_result(principal=PRINCIPAL,
                                 ask_id=ask_id)["status"] == "NOT_YET"

    def test_the_key_never_crosses_the_wire_or_the_store(self, fake):
        ask_client, row = self.seed_ask(fake)
        ask_client.append_ask_event(row["ask_id"],
                                    {"type": "state", "state": "ANSWERED"})
        ask_client.read_ask(row["ask_id"])
        wire = "\n".join(fake.state.request_bodies)
        wire += "\n" + "\n".join(f"{m} {p}" for m, p in fake.state.requests)
        for _m, _p, headers in fake.state.headers_log:
            wire += "\n" + " ".join(f"{k}:{v}" for k, v in headers.items())
        issue_id = fake.state.order[0]
        stored = "\n".join(str(c.get("body")) for c
                           in fake.state.comments[issue_id])
        assert KEY_BYTES.decode() not in wire          # never on the wire
        assert KEY_BYTES.decode() not in stored        # never in Paperclip


# ── GBL-5 A: seq allocation is one atomic step ───────────────────────────────


class TestEventSeqAllocation:
    """GBL-5 A1 (proof 1's defect): the allocation read and the append POST
    were two separate steps, so two appenders could take the SAME number.
    In proof 1 the CONSUMED append re-issued seq 3 because its allocation
    read had not yet seen the nudge comment written 1.8 s earlier — every
    later read of that record then raised EVENT_SEQ_INVALID.  Both shapes
    are reproduced here: the read-lag interleave (proof 1) and two truly
    concurrent appender threads."""

    def seed_ask(self, fake, key: str = "k-1") -> tuple[PaperclipAskClient, dict]:
        ask_client = client(fake)
        row = envelope(key=key)
        assert ask_client.create_ask(row) is None
        return ask_client, row

    def test_read_lag_cannot_reissue_a_taken_seq(self, fake):
        # Proof 1's exact interleave: the server's comment listing lags its
        # own write, so the SECOND append's allocation read misses the FIRST
        # append's just-landed comment and derives the same next seq.
        ask_client, row = self.seed_ask(fake)
        ask_client.append_ask_event(row["ask_id"],
                                    {"type": "state", "state": "ANSWERED"})
        fake.state.comment_visibility_lag = 1        # the nudge write hides
        ask_client.append_ask_event(row["ask_id"],
                                    {"type": "state", "state": "NUDGED"})
        ask_client.append_ask_event(row["ask_id"],   # reads the stale list
                                    {"type": "state", "state": "CONSUMED"})
        fake.state.reveal_lagged_comments()
        issue_id = fake.state.order[0]
        seqs = [stored_comment(fake, issue_id, i)["seq"] for i in range(3)]
        assert seqs == [1, 2, 3]

    def test_concurrent_appenders_never_share_a_seq(self, fake):
        # The lock's own guarantee: two appender threads on one store
        # client take DIFFERENT numbers even while the first append's POST
        # is still in flight (its comment not yet landed).
        ask_client, row = self.seed_ask(fake)
        issue_id = fake.state.order[0]
        fake.state.slow_paths[
            ("POST", f"/api/issues/{issue_id}/comments")] = 0.3
        failures: list[BaseException | None] = [None, None]

        def appender(index: int, state: str) -> None:
            try:
                ask_client.append_ask_event(row["ask_id"],
                                            {"type": "state", "state": state})
            except BaseException as exc:              # recorded, re-raised
                failures[index] = exc

        first = threading.Thread(target=appender, args=(0, "ANSWERED"))
        first.start()
        time.sleep(0.1)          # the first append's POST is mid-flight
        second = threading.Thread(target=appender, args=(1, "CONSUMED"))
        second.start()
        first.join(timeout=5)
        second.join(timeout=5)
        assert failures == [None, None]
        fake.state.slow_paths.clear()
        stored = fake.state.comments[issue_id]
        seqs = sorted(json.loads(str(c["body"])[len(pc.EVENT_MARKER) + 1:])
                      ["seq"] for c in stored)
        assert seqs == [1, 2]


class TestEventSeqAcrossProcesses:
    """GBL-5 R2, RULING 19(b) (deputy round 2, H1): the A1/A2 lock and the
    ``_issued_seq`` floor were per client OBJECT — a second client, or the
    same store reached from a second PROCESS, could still mint the number
    another writer had just taken.  Numbering and append are serialised
    across every process on the host by ONE lock OUTSIDE the client object
    (flock on a fixed path under the GBL state dir, with a cross-process
    mint ledger for the listing-lag window).  Two real child processes,
    each with its OWN client, append to ONE ask over a lagging listing;
    the seqs come out distinct and the CONSUMED is never lost."""

    def test_two_processes_never_share_a_seq(self, fake):
        import subprocess
        import sys as _sys
        repo_root = str(Path(__file__).resolve().parent.parent)
        ask_client = client(fake)
        row = envelope(ttl_seconds=86400 * 365 * 10)   # never expires here
        ask_id = row["ask_id"]
        assert ask_client.create_ask(row) is None
        ask_client.append_ask_event(ask_id, {          # seq 1 (+ first-use key)
            "type": "answer", "answer_id": "gbm-" + "a" * 32,
            "idempotency_key": "gb-ans-1",
            "text": "A harmless fixture answer."})
        ask_client.append_ask_event(ask_id, {          # seq 2
            "type": "state", "state": "ANSWERED"})
        # The listing lags BOTH children's writes: each child's allocation
        # read cannot see the other child's just-landed comment — the exact
        # window in which per-object state re-issues a taken number.
        fake.state.comment_visibility_lag = 2
        cfg = {"base_url": fake.base, "company_id": COMPANY_ID,
               "agent_id": AGENT_ID, "hmac_key_path": str(HMAC_KEY_PATH),
               "ask_id": ask_id}
        events = ({"type": "state", "state": "CONSUMED"},
                  {"type": "nudge", "state": "ANSWERED"})
        children = [subprocess.Popen(
            [_sys.executable, "tests/gbl_append_child.py",
             json.dumps({**cfg, "event": event})],
            cwd=repo_root, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True) for event in events]
        try:
            outs = [child.communicate(timeout=60) for child in children]
        finally:
            for child in children:
                if child.poll() is None:
                    child.kill()
        assert all(child.returncode == 0 for child in children), outs
        assert all('"ok": true' in out for out, _err in outs), outs

        fake.state.reveal_lagged_comments()
        record = ask_client.read_ask(ask_id)           # replays readable
        seqs = [event["seq"] for event in record["events"]]
        assert sorted(seqs) == [1, 2, 3, 4]            # distinct: no re-issue
        consumed = [event for event in record["events"]
                    if event.get("type") == "state"
                    and event.get("state") == "CONSUMED"]
        assert len(consumed) == 1                      # the mark is never lost
        assert consumed[0]["trusted"] is True
        assert not any("defect" in event for event in record["events"])
        core = bridge_over(ask_client)
        assert core.fetch_result(principal=PRINCIPAL,
                                 ask_id=ask_id)["status"] == "CONSUMED"


class TestOneDeliveryMarkPerAnswer:
    """GBL-5 micro 3, RULING 19(a): the read/replay and the CONSUMED append
    are ONE decision under the same host lock the appends already take.

    ``fetch_result`` read the record, replayed it, and only then appended
    CONSUMED.  The flock serialised the two appends (seq N and N+1) but not
    the read-then-decide, so two callers on one ANSWERED ask could each
    observe ANSWERED and each be handed the answer as ANSWER_UNCONSUMED.
    "One connection at a time" is a property of today's server, not of the
    layer, so the decision itself must be serialised host-wide.  The
    read is re-taken INSIDE the lock, so the second caller sees the first
    caller's mark.
    """

    class _Shared:
        def __init__(self):
            self.lock = threading.Lock()
            self.readers = 0
            self.second_read = threading.Event()

    class _RacyStore:
        """Delegates to a real client but makes the read→mark window
        observable: the CONSUMED append waits (bounded) until a SECOND
        reader has read the record, which is exactly the interleaving that
        hands the same answer out twice.  ``result_delivery_lock`` is
        forwarded only when the client offers one, so the pre-fix run
        exercises the plain unlocked read path."""

        def __init__(self, inner, shared):
            self._inner = inner
            self._shared = shared
            self._lock_held = False

        def read_ask(self, ask_id):
            record = self._inner.read_ask(ask_id)
            if record is not None:
                with self._shared.lock:
                    self._shared.readers += 1
                    if self._shared.readers >= 2:
                        self._shared.second_read.set()
            return record

        def append_ask_event(self, ask_id, event):
            if (event.get("type") == "state"
                    and event.get("state") == "CONSUMED"
                    and not self._lock_held):
                self._shared.second_read.wait(timeout=5.0)
            return self._inner.append_ask_event(ask_id, event)

        def __getattr__(self, name):
            if name == "result_delivery_lock":
                inner = getattr(self._inner, "result_delivery_lock")

                @contextmanager
                def _held():
                    self._lock_held = True
                    try:
                        with inner():
                            yield
                    finally:
                        self._lock_held = False

                return _held
            return getattr(self._inner, name)

    def test_two_callers_share_one_delivery(self, fake):
        seed = client(fake)
        row = envelope(ttl_seconds=86400 * 365 * 10)
        ask_id = row["ask_id"]
        assert seed.create_ask(row) is None
        seed.append_ask_event(ask_id, {
            "type": "answer", "answer_id": "gbm-" + "a" * 32,
            "idempotency_key": "gb-ans-1",
            "text": "A harmless fixture answer."})
        seed.append_ask_event(ask_id, {"type": "state", "state": "ANSWERED"})

        shared = self._Shared()
        stores = [self._RacyStore(client(fake), shared) for _ in range(2)]
        cores = [bridge_over(store) for store in stores]
        barrier = threading.Barrier(2)
        results: dict[str, dict] = {}

        def fetch(name, core):
            barrier.wait(timeout=10)
            results[name] = core.fetch_result(principal=PRINCIPAL,
                                              ask_id=ask_id)

        workers = [threading.Thread(target=fetch, args=(name, core))
                   for name, core in zip(("a", "b"), cores)]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join(timeout=60)
        assert not any(worker.is_alive() for worker in workers), results
        assert sorted(result["status"] for result in results.values()) == [
            "ANSWER_UNCONSUMED", "CONSUMED"]
        assert sum(result["status"] == "ANSWER_UNCONSUMED"
                   for result in results.values()) == 1

        # The one mark is the store's, and it landed exactly once.
        marks = [event for event in seed.read_ask(ask_id)["events"]
                 if event.get("type") == "state"
                 and event.get("state") == "CONSUMED"]
        assert len(marks) == 1
        assert marks[0]["trusted"] is True


class TestDeliveryLedger:
    """GBL-5 micro 4 (principal's ruling, 10:55Z): a delivery decision is
    never taken from a read that can lag the host's own writes.

    The host lock serialised the decision but the decision SOURCE was the
    issue's comment listing, which this store's own proof 1 shows can lag
    a write that has already landed (``comment_visibility_lag``, the
    reason the mint ledger exists).  Caller A marks CONSUMED and is handed
    ANSWER_UNCONSUMED; caller B takes the lock, re-reads, sees a stale
    ANSWERED, finds no trusted CONSUMED to dedupe against, mints the next
    number and posts a SECOND CONSUMED — and is handed the answer again.

    The host already keeps a record that cannot lag: the append ledger
    file, held under the same flock.  The delivery (ask id + answer id)
    is recorded there BEFORE the CONSUMED post and consulted FIRST, so
    the second caller is CONSUMED whatever the listing shows.
    """

    def _answered(self, fake):
        seed = client(fake)
        row = envelope(ttl_seconds=86400 * 365 * 10)
        ask_id = row["ask_id"]
        assert seed.create_ask(row) is None
        seed.append_ask_event(ask_id, {
            "type": "answer", "answer_id": "gbm-" + "a" * 32,
            "idempotency_key": "gb-ans-4",
            "text": "A harmless fixture answer."})
        seed.append_ask_event(ask_id, {"type": "state", "state": "ANSWERED"})
        return seed, ask_id

    def test_a_lagging_listing_cannot_deliver_twice(self, fake):
        seed, ask_id = self._answered(fake)
        first = client(fake)                     # two callers, two clients
        second = client(fake)

        # The first caller's CONSUMED lands but is hidden from the listing
        # the second caller reads — exactly proof 1's read-your-write lag.
        fake.state.comment_visibility_lag = 1
        one = bridge_over(first).fetch_result(principal=PRINCIPAL,
                                              ask_id=ask_id)
        assert one["status"] == "ANSWER_UNCONSUMED"

        two = bridge_over(second).fetch_result(principal=PRINCIPAL,
                                               ask_id=ask_id)
        assert two["status"] == "CONSUMED"

        # Exactly one hand-over, and exactly one mark once the listing
        # catches up with the write it had hidden.
        fake.state.reveal_lagged_comments()
        marks = [event for event in seed.read_ask(ask_id)["events"]
                 if event.get("type") == "state"
                 and event.get("state") == "CONSUMED"]
        assert len(marks) == 1
        assert marks[0]["trusted"] is True

    def test_a_failed_mark_post_withholds_the_answer_and_reports_typed(
            self, fake):
        seed, ask_id = self._answered(fake)
        issue_id = fake.state.order[0]
        fake.state.fail_status[
            ("POST", f"/api/issues/{issue_id}/comments")] = 403

        core = bridge_over(client(fake))
        with pytest.raises(GblBridgeError) as caught:
            core.fetch_result(principal=PRINCIPAL, ask_id=ask_id)
        assert caught.value.code == "DELIVERY_MARK_POST_FAILED"

        # The delivery is recorded, so the answer stays WITHHELD: the retry
        # is CONSUMED (never a second ANSWER_UNCONSUMED) and no mark landed.
        again = bridge_over(client(fake)).fetch_result(
            principal=PRINCIPAL, ask_id=ask_id)
        assert again["status"] == "CONSUMED"
        assert not [event for event in seed.read_ask(ask_id)["events"]
                    if event.get("type") == "state"
                    and event.get("state") == "CONSUMED"]


class TestEventSeqDuplicateLaw:
    """GBL-5 A3 (proof 1's bricked record) kept the record READABLE by
    demoting the later holder of a duplicate number per event.  GBL-5 R2,
    RULING 19(a) (deputy round 2, H2): that demotion was by POSITION with
    no type check — on the MMO-1 shape it dropped the CONSUMED, replay
    re-derived ANSWERED, and the next fetch handed the SAME answer out a
    second time.  A delivery mark written by the trusted writer is never
    demoted, ignored or re-derived away: when a duplicate or out-of-order
    seq leaves the order unclear for a STATE event, the reading refuses
    typed (EVENT_ORDER_AMBIGUOUS) and NOTHING is delivered — neither a
    second delivery nor a 'healed' CONSUMED indistinguishable from a
    first.  Non-state duplicates keep the per-event demotion (readable,
    first holder authoritative); a strictly LOWER seq after a higher one
    is a chain anomaly and refuses (deputy MED-1)."""

    def seed_proof1_shape(self, fake):
        """answer(1), nudge_attempt(2), nudge(3) — then the caller injects
        the proof-1 duplicate row re-issuing seq 3."""
        ask_client = client(fake)
        row = envelope(ttl_seconds=86400 * 365 * 10)   # never expires here
        ask_id = row["ask_id"]
        assert ask_client.create_ask(row) is None
        ask_client.append_ask_event(ask_id, {
            "type": "answer", "answer_id": "gbm-" + "a" * 32,
            "idempotency_key": "gb-ans-1",
            "text": "A harmless fixture answer."})                 # seq 1
        ask_client.append_ask_event(ask_id, {
            "type": "nudge_attempt", "outcome": "SENT"})           # seq 2
        ask_client.append_ask_event(ask_id, {
            "type": "nudge", "state": "ANSWERED"})                 # seq 3
        return ask_client, ask_id

    def inject_tagged(self, fake, ask_id: str, seq: int, core: dict) -> None:
        """A genuinely store-stamped row re-issuing ``seq`` — tag and all
        VALID (the pre-R2 store really did mint these)."""
        issue_id = fake.state.order[0]
        stamped = {**core, "seq": seq}
        tagged = {**stamped,
                  "tag": expect_tag(KEY_BYTES, ask_id, seq, stamped)}
        fake.state.comments[issue_id].append({
            "id": str(uuid.uuid4()), "authorAgentId": AGENT_ID,
            "createdAt": fake.state.now_iso(),
            "body": pc.EVENT_MARKER + " " + json.dumps(
                tagged, sort_keys=True, separators=(",", ":"))})

    def test_state_duplicate_refuses_typed_and_delivers_nothing(self, fake):
        # RULING 19(a): the MMO-1 shape — a store-stamped CONSUMED
        # re-issuing the nudge's seq 3.  Demoting it by position re-derived
        # the record to ANSWERED and delivered the answer a SECOND time;
        # healing forward minted a CONSUMED indistinguishable from a first
        # delivery.  Now every path refuses EVENT_ORDER_AMBIGUOUS and
        # delivers nothing.
        ask_client, ask_id = self.seed_proof1_shape(fake)
        self.inject_tagged(fake, ask_id, 3, {"type": "state",
                                             "state": "CONSUMED"})

        def refuses(op):
            with pytest.raises(GblPaperclipError) as err:
                op()
            assert err.value.code == "EVENT_ORDER_AMBIGUOUS"

        refuses(lambda: ask_client.read_ask(ask_id))          # the read
        core = bridge_over(ask_client)
        refuses(lambda: core.ask_status(principal=PRINCIPAL,
                                        ask_id=ask_id))       # status
        refuses(lambda: core.fetch_result(principal=PRINCIPAL,
                                          ask_id=ask_id))     # delivery
        refuses(lambda: ask_client.append_ask_event(          # no blind
            ask_id, {"type": "state", "state": "CONSUMED"}))  # healing
        # Nothing was re-derived away: the comments still hold all four
        # rows, CONSUMED included — the refusal withholds, it never erases.
        issue_id = fake.state.order[0]
        bodies = [str(c["body"]) for c in fake.state.comments[issue_id]]
        assert sum('"CONSUMED"' in b for b in bodies) == 1

    def test_nonstate_duplicate_still_demotes_per_event(self, fake):
        # The A3 law for everything that is not a delivery mark: the LATER
        # holder of a duplicate number is demoted for that event, the first
        # stays authoritative, and the record reads on.  No CONSUMED ever
        # existed here, so the fetch is a FIRST delivery (seq 4), never a
        # second one.
        ask_client, ask_id = self.seed_proof1_shape(fake)
        self.inject_tagged(fake, ask_id, 3, {"type": "nudge",
                                             "state": "ANSWERED"})

        record = ask_client.read_ask(ask_id)          # no refusal on read
        assert [e["seq"] for e in record["events"]] == [1, 2, 3, 3]
        assert [e["trusted"] for e in record["events"]] == [True] * 3 + [False]
        assert record["events"][3]["defect"] == "EVENT_SEQ_DUPLICATE"
        core = bridge_over(ask_client)
        assert core.ask_status(principal=PRINCIPAL,
                               ask_id=ask_id)["state"] == "ANSWERED"
        first = core.fetch_result(principal=PRINCIPAL, ask_id=ask_id)
        assert first["status"] == "ANSWER_UNCONSUMED"     # the FIRST fetch
        assert core.fetch_result(principal=PRINCIPAL,
                                 ask_id=ask_id)["status"] == "CONSUMED"
        events = ask_client.read_ask(ask_id)["events"]
        assert [e["seq"] for e in events] == [1, 2, 3, 3, 4]
        assert events[4]["trusted"] is True

    def test_lower_seq_after_a_higher_one_refuses_typed(self, fake):
        # Deputy MED-1: a strictly LOWER trusted seq after a higher one is
        # a chain anomaly (a delayed or torn append), not a duplicate —
        # silently dropping it once made a legitimate state vanish.  It
        # refuses EVENT_ORDER_AMBIGUOUS; nothing is re-derived.
        ask_client, ask_id = self.seed_proof1_shape(fake)
        self.inject_tagged(fake, ask_id, 5, {"type": "state",
                                             "state": "CONSUMED"})
        # a delayed append that minted 4 landing AFTER the 5 (3 is taken
        # by the real nudge; 4 is the next unseen number below the mark)
        self.inject_tagged(fake, ask_id, 4, {"type": "nudge",
                                             "state": "ANSWERED"})
        with pytest.raises(GblPaperclipError) as err:
            ask_client.read_ask(ask_id)
        assert err.value.code == "EVENT_ORDER_AMBIGUOUS"
        with pytest.raises(GblPaperclipError) as err:
            ask_client.append_ask_event(ask_id,
                                        {"type": "nudge_settled",
                                         "outcome": "NOT_DELIVERED"})
        assert err.value.code == "EVENT_ORDER_AMBIGUOUS"


# ── GBL-5 micro 1 (RULING 19a): a marking only the store may set ────────────


class TestStoreOnlyMarkings:
    """A FOREIGN comment must never be able to spend the trusted writer's
    re-nudge budget, cooldown or settlement.

    The read stripped only ``tag`` and ``trusted`` from a stored event, so
    a comment carrying ``"defect": "EVENT_SEQ_DUPLICATE"`` survived the
    read.  It failed HMAC verification (``trusted: False``), so the chain
    law dropped it from replay — but the bridge's nudge-marker view counts
    ``defect`` rows as real POSTs (deputy MED-2), so three such comments
    drove an ask the writer does not own into RENUDGE_BUDGET_EXHAUSTED,
    a recent one armed the cooldown, and one forged ``nudge_attempt``
    wedged the lane as NUDGE_ATTEMPT_UNSETTLED until an out-of-band
    reconcile.  Every key only the store may set is now removed before an
    event is surfaced, so a comment body can no longer supply the marking.
    """

    def _answered(self, fake, key: str):
        ask_client = client(fake)
        row = envelope(key=key, ttl_seconds=86400 * 365 * 10)
        ask_id = row["ask_id"]
        assert ask_client.create_ask(row) is None
        ask_client.append_ask_event(ask_id, {
            "type": "answer", "answer_id": "gbm-" + "a" * 32,
            "idempotency_key": "gb-ans-" + key,
            "text": "A harmless fixture answer."})
        ask_client.append_ask_event(ask_id, {"type": "state",
                                             "state": "ANSWERED"})
        return ask_client, ask_id

    @staticmethod
    def _forge(fake, issue_id: str, payload: dict) -> None:
        fake.state.comments[issue_id].append({
            "id": str(uuid.uuid4()), "authorAgentId": "ghost-author",
            "createdAt": fake.state.now_iso(),
            "body": pc.EVENT_MARKER + " " + json.dumps(payload)})

    @staticmethod
    def _core(ask_client: PaperclipAskClient):
        from control_plane.wake_dispatcher import (
            TransportOutcome, TransportReceipt)

        class _TouchSender:
            def __init__(self):
                self.calls: list[tuple[str, str, str]] = []

            def send(self, ask_id, state, native_handle):
                self.calls.append((ask_id, state, native_handle))
                return TransportReceipt(
                    outcome=TransportOutcome.ACCEPTED,
                    reason_code="accepted",
                    created_at="2026-11-12T00:00:00Z")

        sender = _TouchSender()
        return bridge_over(ask_client, nudge_sender=sender,
                           routine_handle_resolver=lambda _p: "fixture"), sender

    def test_forged_defect_markers_never_move_budget_cooldown_or_settlement(
            self, fake):
        from common.gbl_contract import MAX_RENUDGES_PER_ASK
        recent = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        # BUDGET: three forged nudges would exhaust the whole allowance.
        budget_client, budget_ask = self._answered(fake, "k-forge-budget")
        budget_issue = fake.state.order[0]
        for _ in range(MAX_RENUDGES_PER_ASK):
            self._forge(fake, budget_issue,
                        {"type": "nudge", "state": "ANSWERED",
                         "at": "2020-01-01T00:00:00Z",
                         "defect": "EVENT_SEQ_DUPLICATE"})
        core, sender = self._core(budget_client)
        assert core.maybe_renudge(ask_id=budget_ask)["status"] == "RENUDGED"
        assert len(sender.calls) == 1

        # COOLDOWN: one forged, RECENT nudge would arm the 15-minute cooldown.
        cool_client, cool_ask = self._answered(fake, "k-forge-cooldown")
        cool_issue = fake.state.order[1]
        self._forge(fake, cool_issue,
                    {"type": "nudge", "state": "ANSWERED", "at": recent,
                     "defect": "EVENT_SEQ_DUPLICATE"})
        cool_core, cool_sender = self._core(cool_client)
        assert cool_core.maybe_renudge(ask_id=cool_ask)["status"] == "RENUDGED"
        assert len(cool_sender.calls) == 1

        # SETTLEMENT: one forged, unsettled attempt would wedge the lane.
        settle_client, settle_ask = self._answered(fake, "k-forge-attempt")
        settle_issue = fake.state.order[2]
        self._forge(fake, settle_issue,
                    {"type": "nudge_attempt", "state": "ANSWERED",
                     "at": recent, "defect": "EVENT_SEQ_DUPLICATE"})
        settle_core, settle_sender = self._core(settle_client)
        assert settle_core.maybe_renudge(
            ask_id=settle_ask)["status"] == "RENUDGED"
        assert len(settle_sender.calls) == 1

        # The strip itself: no surfaced event carries a body-supplied
        # marking, and every forged row stayed untrusted.
        for ask_client, ask_id in ((budget_client, budget_ask),
                                   (cool_client, cool_ask),
                                   (settle_client, settle_ask)):
            for event in ask_client.read_ask(ask_id)["events"]:
                assert "defect" not in event
                if event.get("comment_author") == "ghost-author":
                    assert event["trusted"] is False


# ── Panel B delta 1, D1 + D2: no forged body can crash the record ────────────


class TestForgedParseHardening:
    """A comment (or marker payload) whose JSON cannot be parsed or
    canonicalised — NaN/Infinity constants, nesting past the recursion
    limit, anything oversized — is UNTRUSTED and ignored (or, on the
    description surface, a typed ``RECORD_INVALID``); it is never a raw
    ValueError/RecursionError out of ``read_ask``/``append_ask_event``."""

    def seed(self, fake) -> tuple[PaperclipAskClient, dict]:
        ask_client = client(fake)
        row = envelope()
        assert ask_client.create_ask(row) is None
        ask_client.append_ask_event(row["ask_id"],
                                    {"type": "state", "state": "ANSWERED"})
        return ask_client, row

    def plant(self, fake, payload: str) -> None:
        issue_id = fake.state.order[0]
        fake.state.comments[issue_id].append({
            "id": str(uuid.uuid4()), "createdAt": fake.state.now_iso(),
            "body": f"{pc.EVENT_MARKER} {payload}"})

    def assert_record_healthy(self, fake, ask_client, row) -> None:
        """The ask still reads and appends normally with the forgery in
        place: the forged comment is gone from the surfaced events, and
        the next append keeps the trusted sequence going."""
        record = ask_client.read_ask(row["ask_id"])
        assert [e.get("state") for e in record["events"]] == ["ANSWERED"]
        assert all(e["trusted"] is True for e in record["events"])
        ask_client.append_ask_event(row["ask_id"],
                                    {"type": "state", "state": "CONSUMED"})
        issue_id = fake.state.order[0]
        assert stored_comment(fake, issue_id, 2)["seq"] == 2   # counter intact
        assert ask_client.read_ask(row["ask_id"])["events"][-1][
            "state"] == "CONSUMED"

    @pytest.mark.parametrize("constant", ["NaN", "Infinity", "-Infinity"])
    def test_nan_like_forged_events_are_ignored(self, fake, constant):
        # D1: json.loads ACCEPTS these constants; canonicalisation
        # (allow_nan=False) then raised a raw ValueError out of BOTH
        # read_ask and append_ask_event while the comment existed.
        ask_client, row = self.seed(fake)
        self.plant(fake, '{"seq":2,"tag":"v1:' + "0" * 64 + '",'
                         '"type":"answer","x":' + constant + '}')
        self.assert_record_healthy(fake, ask_client, row)

    def test_deeply_nested_forged_event_is_ignored(self, fake):
        # D2: a ~20k-deep forged body raised RecursionError out of
        # json.loads, which the ValueError-only except let escape raw.
        ask_client, row = self.seed(fake)
        depth = 20000
        self.plant(fake, '{"seq":2,"tag":"v1:' + "0" * 64 + '",'
                         '"type":"state","d":' + "[" * depth
                         + "]" * depth + '}')
        self.assert_record_healthy(fake, ask_client, row)

    def test_oversized_forged_event_is_ignored(self, fake):
        # "too large": beyond the event-JSON cap the body is foreign by
        # definition (the store's own writes stay far below it) and is
        # never parsed.
        ask_client, row = self.seed(fake)
        self.plant(fake, '{"seq":2,"tag":"v1:' + "0" * 64 + '",'
                         '"type":"state","x":"'
                         + "A" * (pc.MAX_EVENT_JSON_CHARS + 1) + '"}')
        self.assert_record_healthy(fake, ask_client, row)

    def test_deeply_nested_marker_payload_is_a_typed_record_error(self, fake):
        # D2's sibling surface: the issue DESCRIPTION is foreign-writable
        # too; a deep marker payload crashed read_ask the same raw way.
        # On this surface the law is the typed RECORD_INVALID (panel B H4:
        # corruption is never read as absence), never a raw exception.
        ask_client = client(fake)
        row = envelope()
        assert ask_client.create_ask(row) is None
        issue = fake.state.issues[fake.state.order[0]]
        depth = 20000
        issue["description"] = (pc.ASK_MARKER + ' {"d":' + "[" * depth
                                + "]" * depth + "}")
        with pytest.raises(GblPaperclipError) as err:
            ask_client.read_ask(row["ask_id"])
        assert err.value.code == "RECORD_INVALID"

    def test_nan_marker_payload_is_a_typed_record_error(self, fake):
        # D1's sibling surface: the marker payload is the store's OWN
        # strict-JSON format; a NaN constant is unparseable under it and
        # must refuse as RECORD_INVALID, not surface float('nan') data.
        ask_client = client(fake)
        row = envelope()
        assert ask_client.create_ask(row) is None
        issue = fake.state.issues[fake.state.order[0]]
        issue["description"] = pc.ASK_MARKER + ' {"x":NaN}'
        with pytest.raises(GblPaperclipError) as err:
            ask_client.read_ask(row["ask_id"])
        assert err.value.code == "RECORD_INVALID"


# ── §2.1: the host-held key — file law, fail-closed everywhere ───────────────


class TestHmacKeyLaw:
    @staticmethod
    def _created(fake, ask_client) -> str:
        row = envelope()
        assert ask_client.create_ask(row) is None
        return row["ask_id"]

    def test_key_is_generated_on_first_use_mode_0600(self, fake, tmp_path):
        path = tmp_path / "state" / "hmac_v1.key"
        path.parent.mkdir()
        ask_client = client(fake, hmac_key_path=path)
        ask_id = self._created(fake, ask_client)
        assert not path.exists()                       # lazy: nothing yet
        ask_client.append_ask_event(ask_id,
                                    {"type": "state", "state": "ANSWERED"})
        assert path.exists()
        assert path.stat().st_size == 32
        assert stat.S_IMODE(path.stat().st_mode) & 0o777 == 0o600

    def test_wrong_length_key_is_a_typed_error(self, fake, tmp_path):
        path = tmp_path / "short.key"
        path.write_bytes(KEY_BYTES[:31])
        os.chmod(path, 0o600)
        ask_client = client(fake, hmac_key_path=path)
        ask_id = self._created(fake, ask_client)
        with pytest.raises(GblPaperclipError) as err:
            ask_client.append_ask_event(ask_id, {"type": "state",
                                                 "state": "ANSWERED"})
        assert "HMAC_KEY" in err.value.code

    def test_group_readable_key_is_a_typed_error(self, fake, tmp_path):
        path = tmp_path / "loose.key"
        path.write_bytes(KEY_BYTES)
        os.chmod(path, 0o644)
        ask_client = client(fake, hmac_key_path=path)
        ask_id = self._created(fake, ask_client)
        with pytest.raises(GblPaperclipError) as err:
            ask_client.append_ask_event(ask_id, {"type": "state",
                                                 "state": "ANSWERED"})
        assert "HMAC_KEY" in err.value.code

    def test_missing_state_dir_is_a_typed_error_never_mkdir(self, fake,
                                                            tmp_path):
        path = tmp_path / "nowhere" / "hmac_v1.key"
        ask_client = client(fake, hmac_key_path=path)
        ask_id = self._created(fake, ask_client)
        with pytest.raises(GblPaperclipError) as err:
            ask_client.append_ask_event(ask_id,
                                        {"type": "state",
                                         "state": "ANSWERED"})
        assert "HMAC_KEY" in err.value.code
        assert not (tmp_path / "nowhere").exists()     # no directory minted

    # -- panel B delta 1: key-anchor hardening (D3 dangling symlink, D5) -------

    def test_dangling_symlink_key_is_a_typed_error(self, fake, tmp_path):
        # D3: a dangling symlink used to loop stat→create(O_EXCL)→
        # FileExistsError→recurse until a raw RecursionError.
        path = tmp_path / "dangling.key"
        os.symlink(tmp_path / "absent.key", path)
        ask_client = client(fake, hmac_key_path=path)
        ask_id = self._created(fake, ask_client)
        with pytest.raises(GblPaperclipError) as err:
            ask_client.append_ask_event(ask_id,
                                        {"type": "state",
                                         "state": "ANSWERED"})
        assert "HMAC_KEY" in err.value.code
        assert not (tmp_path / "absent.key").exists()  # nothing minted

    def test_symlink_to_a_valid_key_is_refused(self, fake, tmp_path):
        # D5: stat()/read_bytes() FOLLOW symlinks, so a symlink to a valid
        # 0600 32-byte key used to be adopted verbatim.  lstat + S_ISLNK
        # refuses the anchor shape itself.
        target = tmp_path / "real.key"
        target.write_bytes(KEY_BYTES)
        os.chmod(target, 0o600)
        path = tmp_path / "link.key"
        os.symlink(target, path)
        ask_client = client(fake, hmac_key_path=path)
        ask_id = self._created(fake, ask_client)
        with pytest.raises(GblPaperclipError) as err:
            ask_client.append_ask_event(ask_id,
                                        {"type": "state",
                                         "state": "ANSWERED"})
        assert "HMAC_KEY" in err.value.code

    def test_group_writable_state_dir_is_a_typed_error(self, fake, tmp_path):
        # D5: a group-/other-writable state root allows unlink+replace of
        # the anchor; the load refuses it (a normal 0755 root stays legal —
        # only the WRITE bits are refused).
        state = tmp_path / "state"
        state.mkdir()
        os.chmod(state, 0o770)
        try:
            path = state / "hmac_v1.key"
            ask_client = client(fake, hmac_key_path=path)
            ask_id = self._created(fake, ask_client)
            with pytest.raises(GblPaperclipError) as err:
                ask_client.append_ask_event(
                    ask_id, {"type": "state", "state": "ANSWERED"})
            assert "HMAC_KEY" in err.value.code
            assert not path.exists()               # nothing generated
        finally:
            os.chmod(state, 0o700)

    def test_state_dir_without_group_write_stays_legal(self, fake, tmp_path):
        # Compatibility guard: the dev/production state roots are ordinary
        # 0755 directories (r-x group/other); only group/other WRITE bits
        # are refused.
        state = tmp_path / "state"
        state.mkdir()
        os.chmod(state, 0o755)
        try:
            path = state / "hmac_v1.key"
            ask_client = client(fake, hmac_key_path=path)
            ask_id = self._created(fake, ask_client)
            ask_client.append_ask_event(ask_id,
                                        {"type": "state",
                                         "state": "ANSWERED"})
            assert path.exists()
            assert stat.S_IMODE(path.stat().st_mode) & 0o777 == 0o600
        finally:
            os.chmod(state, 0o700)

    # -- panel B delta 2, F3: first-use create/write failures stay typed -------

    def test_unwritable_state_dir_is_a_typed_error(self, fake, tmp_path):
        # F3: EACCES from the first-use os.open escaped untyped — the open
        # sits inside the FileNotFoundError handler, out of the outer
        # typed catch's reach.
        state = tmp_path / "state"
        state.mkdir()
        os.chmod(state, 0o555)               # readable, not writable
        try:
            path = state / "hmac_v1.key"
            ask_client = client(fake, hmac_key_path=path)
            ask_id = self._created(fake, ask_client)
            with pytest.raises(GblPaperclipError) as err:
                ask_client.append_ask_event(
                    ask_id, {"type": "state", "state": "ANSWERED"})
            assert "HMAC_KEY" in err.value.code
        finally:
            os.chmod(state, 0o700)

    def test_failed_first_use_write_is_a_typed_error(self, fake, tmp_path,
                                                     monkeypatch):
        # F3: an OSError out of the first-use os.write (ENOSPC family)
        # also escaped untyped.
        state = tmp_path / "state"
        state.mkdir()
        path = state / "hmac_v1.key"
        ask_client = client(fake, hmac_key_path=path)
        ask_id = self._created(fake, ask_client)

        def refused(_fd, _data):
            raise OSError(28, "simulated no space left on device")

        monkeypatch.setattr(pc.os, "write", refused)
        with pytest.raises(GblPaperclipError) as err:
            ask_client.append_ask_event(ask_id,
                                        {"type": "state",
                                         "state": "ANSWERED"})
        assert "HMAC_KEY" in err.value.code

    def test_short_first_use_write_is_a_typed_error(self, fake, tmp_path,
                                                    monkeypatch):
        # GBL-5 B3 (panel B old-code #3): os.write's return count was
        # never checked — a short write left a truncated key on disk while
        # the client returned (and cached) the full 32 bytes; the NEXT
        # process would fail closed on HMAC_KEY_INVALID with no hint why.
        state = tmp_path / "state"
        state.mkdir()
        path = state / "hmac_v1.key"
        ask_client = client(fake, hmac_key_path=path)
        ask_id = self._created(fake, ask_client)

        def short_write(_fd, data):
            return len(data) - 5          # 27 of 32 bytes land

        monkeypatch.setattr(pc.os, "write", short_write)
        with pytest.raises(GblPaperclipError) as err:
            ask_client.append_ask_event(ask_id,
                                        {"type": "state",
                                         "state": "ANSWERED"})
        assert err.value.code == "HMAC_KEY_UNWRITABLE"

    def test_failing_close_after_first_use_write_is_not_a_raw_escape(
            self, tmp_path, monkeypatch):
        # GBL-5 B4 (panel B old-code #4): the first-use finally called
        # os.close(handle) bare — an OSError there escaped RAW, past every
        # typed guard, after the key was already fully written.  Called
        # directly (no HTTP fixture) so the patched os.close is scoped to
        # this one call.
        state = tmp_path / "state"
        state.mkdir()
        path = state / "hmac_v1.key"

        def refusing_close(_fd):
            raise OSError(9, "simulated bad file descriptor")

        monkeypatch.setattr(pc.os, "close", refusing_close)
        try:
            data = pc._load_or_create_hmac_key(path)
        finally:
            monkeypatch.undo()
        assert len(data) == pc.HMAC_KEY_BYTES
        assert path.read_bytes() == data          # the write itself landed

    def test_a_tagged_event_without_a_configured_key_is_typed(self, fake):
        # Not silent "untrusted": a tagged event proves a key exists; a
        # client with no key configured fails closed and visibly.
        keyed = client(fake)
        row = envelope()
        keyed.create_ask(row)
        keyed.append_ask_event(row["ask_id"],
                               {"type": "state", "state": "ANSWERED"})
        keyless = client(fake, hmac_key_path=None)
        with pytest.raises(GblPaperclipError) as err:
            keyless.read_ask(row["ask_id"])
        assert "HMAC_KEY" in err.value.code

    def test_append_without_a_configured_key_is_typed(self, fake):
        ask_client = client(fake, hmac_key_path=None)
        ask_id = self._created(fake, ask_client)
        with pytest.raises(GblPaperclipError) as err:
            ask_client.append_ask_event(ask_id, {"type": "state",
                                                 "state": "ANSWERED"})
        assert "HMAC_KEY" in err.value.code


# ── 4xx / 5xx → typed errors ────────────────────────────────────────────────


class TestTypedHttpErrors:
    def test_4xx_is_a_client_error(self, fake):
        fake.state.create_fail_status = 422
        with pytest.raises(GblPaperclipClientError) as err:
            client(fake).create_ask(envelope())
        assert "422" in err.value.code
        assert err.value.status == 422

    def test_5xx_on_create_is_effect_unknown(self, fake):
        fake.state.create_fail_status = 500
        with pytest.raises(GblCreateEffectUnknown):
            client(fake).create_ask(envelope())

    def test_5xx_on_read_is_a_server_error(self, fake):
        ask_client = client(fake)
        ask_client.create_ask(envelope())
        issue_id = fake.state.order[0]
        fake.state.fail_status[("GET", f"/api/issues/{issue_id}")] = 503
        with pytest.raises(GblPaperclipServerError):
            ask_client.read_ask(envelope()["ask_id"])

    def test_4xx_on_comment_is_a_client_error(self, fake):
        ask_client = client(fake)
        ask_client.create_ask(envelope())
        issue_id = fake.state.order[0]
        fake.state.fail_status[
            ("POST", f"/api/issues/{issue_id}/comments")] = 400
        with pytest.raises(GblPaperclipClientError):
            ask_client.append_ask_event(envelope()["ask_id"],
                                        {"type": "state", "state": "ANSWERED"})

    def test_transport_timeout_is_a_transport_error(self, fake):
        ask_client = client(fake)
        ask_client.create_ask(envelope())
        fake.state.slow_paths[
            ("GET", f"/api/companies/{COMPANY_ID}/issues")] = 1.0
        with pytest.raises(GblPaperclipTransportError):
            client(fake).count_asks(PRINCIPAL, "2026-11-11T00:00:00Z")


# ── The dev roster spec ──────────────────────────────────────────────────────


class TestSpecLoading:
    def test_from_spec_builds_a_client(self, fake, tmp_path, fixture_key):
        spec = {
            "kind": "gbl_bridge_service_agent_dev",
            "paperclip": {
                "base_url": fake.base,
                "company_id": COMPANY_ID,
                "agent_id": AGENT_ID,
                "agent_name": "Grok Bridge Fixture",
                "hmac_key_path": str(fixture_key),
            },
        }
        path = tmp_path / "spec.json"
        path.write_text(json.dumps(spec))
        ask_client = PaperclipAskClient.from_spec(path)
        # the display name is spec-held; /api/agents/me is NEVER called
        # (the fake board 401s that route for this client, like the real one)
        assert ask_client._agent_name == "Grok Bridge Fixture"
        row = envelope()
        ask_client.create_ask(row)
        assert ask_client.read_ask(row["ask_id"]) is not None

    def test_from_spec_agent_name_is_optional_and_typed(self, fake, tmp_path,
                                                        fixture_key):
        base = {
            "kind": "gbl_bridge_service_agent_dev",
            "paperclip": {
                "base_url": fake.base,
                "company_id": COMPANY_ID,
                "agent_id": AGENT_ID,
                "hmac_key_path": str(fixture_key),
            },
        }
        path = tmp_path / "spec.json"
        # absent -> the neutral fallback, never a board read
        path.write_text(json.dumps(base))
        assert PaperclipAskClient.from_spec(path)._agent_name == \
            "the Grok bridge"
        # a non-string name is refused at load, not stringified silently
        bad = json.loads(json.dumps(base))
        bad["paperclip"]["agent_name"] = 42
        path.write_text(json.dumps(bad))
        with pytest.raises(ValueError, match="agent_name"):
            PaperclipAskClient.from_spec(path)

    def test_from_spec_refuses_a_bad_base_url(self, tmp_path):
        spec = {"paperclip": {"base_url": "http://127.0.0.1:3100",
                              "company_id": COMPANY_ID, "agent_id": AGENT_ID,
                              "hmac_key_path": str(tmp_path / "k.key")}}
        path = tmp_path / "spec.json"
        path.write_text(json.dumps(spec))
        with pytest.raises(ValueError):
            PaperclipAskClient.from_spec(path)

    def test_from_spec_requires_the_instance_fields(self, tmp_path):
        path = tmp_path / "spec.json"
        path.write_text(json.dumps({"paperclip": {"base_url":
                                                  "http://127.0.0.1:3191"}}))
        with pytest.raises(ValueError):
            PaperclipAskClient.from_spec(path)

    def test_from_spec_requires_the_hmac_key_path(self, fake, tmp_path):
        # Round 2 fail-closed law: no spec silently configures a client that
        # could read tagged events without the key (trust-absent mode).
        spec = {"paperclip": {"base_url": fake.base, "company_id": COMPANY_ID,
                              "agent_id": AGENT_ID}}
        path = tmp_path / "spec.json"
        path.write_text(json.dumps(spec))
        with pytest.raises(ValueError):
            PaperclipAskClient.from_spec(path)


# ── P0-2 option (a): the production-board opt-in ─────────────────────────────
# Principal ruling 2026-11-12 14:13Z (narrow): validate_paperclip_base_url
# grows a keyword-only production_board=False; the default law is UNCHANGED
# (3100 and 3179 refuse); True admits EXACTLY port 3100 and nothing else —
# 3179 is never admitted by anything.  Only PaperclipAskClient.from_spec may
# pass True, and only for the ONE canonical production spec: realpath ==
# <home>/.mastermind/gbl/spec.json with home from the PASSWORD DATABASE for
# the current uid (never $HOME), a regular non-symlink file owned by the
# current uid, mode exactly 0600.  The field anywhere else — any other path,
# mode, owner, or a non-true value — is the typed refusal
# PRODUCTION_BOARD_NOT_ALLOWED_HERE; it never silently falls back.
# create_service_agent and every other direct caller keep refusing 3100.


def _prod_spec(base_url="http://127.0.0.1:3100", *, flag=True,
               key="/tmp/gpb-unused-k.key"):
    block = {"base_url": base_url, "company_id": COMPANY_ID,
             "agent_id": AGENT_ID, "hmac_key_path": key}
    if flag is not None:
        block["production_board"] = flag
    return {"paperclip": block}


class TestProductionBoardOptIn:
    def _place_canonical(self, tmp_path, monkeypatch, spec, *, mode=0o600):
        """Write the spec at <injected-home>/.mastermind/gbl/spec.json and
        point the module's home lookup at that temp root (test injection of
        the pwd lookup ONLY — never an env var the server reads)."""
        home = tmp_path / "home"
        spec_dir = home / ".mastermind" / "gbl"
        spec_dir.mkdir(parents=True)
        spec_path = spec_dir / "spec.json"
        spec_path.write_text(json.dumps(spec))
        spec_path.chmod(mode)
        monkeypatch.setattr(pc, "_current_home", lambda: str(home))
        return spec_path

    # -- the URL law itself ---------------------------------------------------

    def test_default_still_refuses_3100_and_3179(self):
        for port in (3100, 3179):
            with pytest.raises(ValueError):
                pc.validate_paperclip_base_url(f"http://127.0.0.1:{port}",
                                               production_board=False)

    def test_opt_in_admits_exactly_3100(self):
        assert pc.validate_paperclip_base_url(
            "http://127.0.0.1:3100", production_board=True
        ) == "http://127.0.0.1:3100"
        # every OTHER rule of the law still holds under the opt-in
        with pytest.raises(ValueError):
            pc.validate_paperclip_base_url("http://example.invalid:3100",
                                           production_board=True)
        with pytest.raises(ValueError):
            pc.validate_paperclip_base_url("https://127.0.0.1:3100",
                                           production_board=True)

    def test_opt_in_never_admits_3179(self):
        with pytest.raises(ValueError):
            pc.validate_paperclip_base_url("http://127.0.0.1:3179",
                                           production_board=True)

    def test_opt_in_flag_must_be_a_real_bool(self):
        for truthy in ("true", 1, [3100]):
            with pytest.raises(ValueError):
                pc.validate_paperclip_base_url("http://127.0.0.1:3100",
                                               production_board=truthy)

    # -- the from_spec gate ---------------------------------------------------

    def test_from_spec_admits_3100_at_the_canonical_spec(self, tmp_path,
                                                         monkeypatch):
        spec_path = self._place_canonical(
            tmp_path, monkeypatch, _prod_spec(key=str(tmp_path / "k.key")))
        ask_client = pc.PaperclipAskClient.from_spec(spec_path)
        # construction only — NO request was made to 3100 (nothing to make
        # one to: the fixture board does not exist here)
        assert ask_client._port == 3100

    def test_from_spec_opt_in_still_refuses_3179(self, tmp_path, monkeypatch):
        spec_path = self._place_canonical(
            tmp_path, monkeypatch,
            _prod_spec("http://127.0.0.1:3179", key=str(tmp_path / "k.key")))
        with pytest.raises(ValueError):
            pc.PaperclipAskClient.from_spec(spec_path)

    def test_field_at_another_path_is_a_typed_refusal(self, tmp_path,
                                                      monkeypatch):
        # a perfect 0600 uid-owned regular file — just NOT the canonical path
        spec_path = tmp_path / "spec.json"
        spec_path.write_text(json.dumps(_prod_spec()))
        spec_path.chmod(0o600)
        monkeypatch.setattr(pc, "_current_home",
                            lambda: str(tmp_path / "home"))
        with pytest.raises(GblPaperclipError) as err:
            pc.PaperclipAskClient.from_spec(spec_path)
        assert err.value.code == "PRODUCTION_BOARD_NOT_ALLOWED_HERE"

    def test_wrong_mode_is_a_typed_refusal(self, tmp_path, monkeypatch):
        spec_path = self._place_canonical(tmp_path, monkeypatch, _prod_spec(),
                                          mode=0o644)
        with pytest.raises(GblPaperclipError) as err:
            pc.PaperclipAskClient.from_spec(spec_path)
        assert err.value.code == "PRODUCTION_BOARD_NOT_ALLOWED_HERE"

    def test_symlink_is_a_typed_refusal(self, tmp_path, monkeypatch):
        home = tmp_path / "home"
        spec_dir = home / ".mastermind" / "gbl"
        spec_dir.mkdir(parents=True)
        real = tmp_path / "real-spec.json"
        real.write_text(json.dumps(_prod_spec()))
        real.chmod(0o600)
        (spec_dir / "spec.json").symlink_to(real)
        monkeypatch.setattr(pc, "_current_home", lambda: str(home))
        with pytest.raises(GblPaperclipError) as err:
            pc.PaperclipAskClient.from_spec(spec_dir / "spec.json")
        assert err.value.code == "PRODUCTION_BOARD_NOT_ALLOWED_HERE"

    def test_wrong_owner_is_a_typed_refusal(self, tmp_path, monkeypatch):
        spec_path = self._place_canonical(tmp_path, monkeypatch, _prod_spec())
        monkeypatch.setattr(pc, "_current_uid", lambda: os.getuid() + 1)
        with pytest.raises(GblPaperclipError) as err:
            pc.PaperclipAskClient.from_spec(spec_path)
        assert err.value.code == "PRODUCTION_BOARD_NOT_ALLOWED_HERE"

    def test_non_true_flag_value_is_a_typed_refusal(self, tmp_path,
                                                    monkeypatch):
        spec_path = self._place_canonical(tmp_path, monkeypatch,
                                          _prod_spec(flag="true"))
        with pytest.raises(GblPaperclipError) as err:
            pc.PaperclipAskClient.from_spec(spec_path)
        assert err.value.code == "PRODUCTION_BOARD_NOT_ALLOWED_HERE"

    def test_env_home_never_opts_in(self, tmp_path, monkeypatch):
        # $HOME is NOT the home lookup: a spec under an env-var home is just
        # "another path" — typed refusal, no fallback, no admission.
        envhome = tmp_path / "envhome"
        spec_dir = envhome / ".mastermind" / "gbl"
        spec_dir.mkdir(parents=True)
        spec_path = spec_dir / "spec.json"
        spec_path.write_text(json.dumps(_prod_spec()))
        spec_path.chmod(0o600)
        monkeypatch.setenv("HOME", str(envhome))
        with pytest.raises(GblPaperclipError) as err:
            pc.PaperclipAskClient.from_spec(spec_path)
        assert err.value.code == "PRODUCTION_BOARD_NOT_ALLOWED_HERE"

    def test_no_flag_keeps_the_default_law_at_the_canonical_path(
            self, tmp_path, monkeypatch):
        spec_path = self._place_canonical(
            tmp_path, monkeypatch, _prod_spec(flag=None,
                                              key=str(tmp_path / "k.key")))
        with pytest.raises(ValueError):
            pc.PaperclipAskClient.from_spec(spec_path)

    # -- other callers keep refusing ------------------------------------------

    def test_create_service_agent_still_refuses_3100(self):
        # the principal creates the production agent BY HAND (install step 4)
        with pytest.raises(ValueError):
            pc.create_service_agent("http://127.0.0.1:3100", COMPANY_ID,
                                    name="Grok Bridge")

    def test_direct_construction_still_refuses_3100(self):
        with pytest.raises(ValueError):
            pc.PaperclipAskClient("http://127.0.0.1:3100", COMPANY_ID,
                                  AGENT_ID)

    # -- no spec in the repo opts in ------------------------------------------

    def test_no_repo_spec_carries_the_field(self):
        specs_root = (Path(__file__).resolve().parents[1]
                      / "tools" / "gbl" / "specs")
        assert specs_root.is_dir(), f"{specs_root} missing"
        found = sorted(specs_root.rglob("*.json"))
        assert found, "no spec files scanned"
        for spec_file in found:
            stack = [json.loads(spec_file.read_text(encoding="utf-8"))]
            while stack:
                node = stack.pop()
                if isinstance(node, dict):
                    assert pc.PRODUCTION_BOARD_FIELD not in node, (
                        f"{spec_file} carries {pc.PRODUCTION_BOARD_FIELD} — "
                        "only the principal adds it, when placing the real "
                        "spec at ~/.mastermind/gbl/spec.json")
                    stack.extend(node.values())
                elif isinstance(node, list):
                    stack.extend(node)


# ── GBL-RETURN item 8 (principal ruling 16:05Z): three review LOWs closed ───
# (a) LOW-3: under the production_board flag the host must be the LITERAL
#     127.0.0.1 — localhost and [::1] with port 3100 get the typed refusal
#     PRODUCTION_BOARD_NOT_ALLOWED_HERE, not an admission.
# (b) LOW-4: a non-ASCII base URL is refused typed (BASE_URL_NOT_ASCII) with
#     or without the flag — fullwidth digits normalize consistently through
#     isdigit()/int(), but the returned base kept the non-ASCII netloc and
#     died raw (UnicodeEncodeError) at request time.
# (c) LOW-2: the FIELD NAME production_board anywhere in the spec other than
#     paperclip.production_board is the typed refusal, whatever its value —
#     the runtime gate now mirrors the repo hygiene test's whole-tree scan.
# Every new-behaviour test below fails first at 117ab5180.


class TestItem8ProductionBoardNarrowing:
    def _place_canonical(self, tmp_path, monkeypatch, spec, *, mode=0o600):
        home = tmp_path / "home"
        spec_dir = home / ".mastermind" / "gbl"
        spec_dir.mkdir(parents=True)
        spec_path = spec_dir / "spec.json"
        spec_path.write_text(json.dumps(spec))
        spec_path.chmod(mode)
        monkeypatch.setattr(pc, "_current_home", lambda: str(home))
        return spec_path

    # -- (a) LOW-3: the literal host under the flag ----------------------------

    def test_opt_in_refuses_localhost_alias(self):
        with pytest.raises(GblPaperclipError) as err:
            pc.validate_paperclip_base_url("http://localhost:3100",
                                           production_board=True)
        assert err.value.code == "PRODUCTION_BOARD_NOT_ALLOWED_HERE"

    def test_opt_in_refuses_uppercase_localhost_alias(self):
        with pytest.raises(GblPaperclipError) as err:
            pc.validate_paperclip_base_url("http://LOCALHOST:3100",
                                           production_board=True)
        assert err.value.code == "PRODUCTION_BOARD_NOT_ALLOWED_HERE"

    def test_opt_in_refuses_ipv6_loopback(self):
        with pytest.raises(GblPaperclipError) as err:
            pc.validate_paperclip_base_url("http://[::1]:3100",
                                           production_board=True)
        assert err.value.code == "PRODUCTION_BOARD_NOT_ALLOWED_HERE"

    def test_opt_in_refuses_alias_on_any_port(self):
        # the flag binds the host on EVERY port, not only 3100
        with pytest.raises(GblPaperclipError) as err:
            pc.validate_paperclip_base_url("http://localhost:8080",
                                           production_board=True)
        assert err.value.code == "PRODUCTION_BOARD_NOT_ALLOWED_HERE"

    # -- (b) LOW-4: non-ASCII base URLs refuse typed ---------------------------

    def test_non_ascii_port_refused_with_flag(self):
        with pytest.raises(GblPaperclipError) as err:
            pc.validate_paperclip_base_url("http://127.0.0.1:３１００",
                                           production_board=True)
        assert err.value.code == "BASE_URL_NOT_ASCII"

    def test_non_ascii_port_refused_without_flag(self):
        with pytest.raises(GblPaperclipError) as err:
            pc.validate_paperclip_base_url("http://127.0.0.1:８０８０")
        assert err.value.code == "BASE_URL_NOT_ASCII"

    def test_non_ascii_host_refused(self):
        with pytest.raises(GblPaperclipError) as err:
            pc.validate_paperclip_base_url("http://１２７.０.０.１:8080")
        assert err.value.code == "BASE_URL_NOT_ASCII"

    # -- (c) LOW-2: the field name is honored at exactly one place -------------

    def test_stray_top_level_field_is_a_typed_refusal(self, tmp_path,
                                                      monkeypatch):
        spec = _prod_spec("http://127.0.0.1:8080", flag=None,
                          key=str(tmp_path / "k.key"))
        spec["production_board"] = True      # stray, OUTSIDE the block
        spec_path = self._place_canonical(tmp_path, monkeypatch, spec)
        with pytest.raises(GblPaperclipError) as err:
            pc.PaperclipAskClient.from_spec(spec_path)
        assert err.value.code == "PRODUCTION_BOARD_NOT_ALLOWED_HERE"

    def test_stray_nested_field_is_refused_whatever_its_value(
            self, tmp_path, monkeypatch):
        spec = _prod_spec("http://127.0.0.1:8080", flag=None,
                          key=str(tmp_path / "k.key"))
        spec["edge"] = {"environments": [{"production_board": False}]}
        spec_path = self._place_canonical(tmp_path, monkeypatch, spec)
        with pytest.raises(GblPaperclipError) as err:
            pc.PaperclipAskClient.from_spec(spec_path)
        assert err.value.code == "PRODUCTION_BOARD_NOT_ALLOWED_HERE"

    def test_stray_copy_beside_the_honored_field_is_refused(
            self, tmp_path, monkeypatch):
        spec = _prod_spec(key=str(tmp_path / "k.key"))   # paperclip flag true
        spec["routine"] = {"production_board": True}     # stray copy
        spec_path = self._place_canonical(tmp_path, monkeypatch, spec)
        with pytest.raises(GblPaperclipError) as err:
            pc.PaperclipAskClient.from_spec(spec_path)
        assert err.value.code == "PRODUCTION_BOARD_NOT_ALLOWED_HERE"

    def test_stray_field_refused_even_at_a_noncanonical_path(
            self, tmp_path, monkeypatch):
        # the scan runs wherever from_spec parses: a stray field is the typed
        # refusal even when the paperclip block carries no flag at all and
        # the path gate would never fire — base constructs this silently
        spec = _prod_spec("http://127.0.0.1:8080", flag=None)
        spec["production_board"] = "yes"
        spec_path = tmp_path / "elsewhere.json"
        spec_path.write_text(json.dumps(spec))
        spec_path.chmod(0o600)
        monkeypatch.setattr(pc, "_current_home",
                            lambda: str(tmp_path / "home"))
        with pytest.raises(GblPaperclipError) as err:
            pc.PaperclipAskClient.from_spec(spec_path)
        assert err.value.code == "PRODUCTION_BOARD_NOT_ALLOWED_HERE"


# ── GBL-RETURN: the delegate dispatch/return capability ─────────────────────


TARGET_AGENT_ID = "33333333-3333-4333-8333-333333333333"


def _delegate_envelope(key: str = "d-1",
                       body: str = "Do the harmless fixture work.",
                       **over) -> dict:
    return envelope(key, kind="delegate", target="secretary",
                    title="Fixture delegate", body=body, **over)


class TestDelegateDispatch:
    """The dispatch/return arm of the client: the RF carrier's shapes
    replicated field-for-field (child create payload, end-anchored ask
    marker, reuse scan, self-owned block descriptor, ambiguous-create
    reconcile, result-comment law, bounded delegate scan).  The fake board
    stamps ``createdByAgentId`` from the calling key exactly like the real
    one; the client never sends it."""

    def _client(self, fake) -> PaperclipAskClient:
        return client(fake, target_agents={"secretary": TARGET_AGENT_ID},
                      service_agent_name="Grok Bridge Fixture")

    def _created_ask(self, fake, key: str = "d-1"):
        store = self._client(fake)
        env = _delegate_envelope(key)
        assert store.create_ask(env) is None
        parent = store._issue_for(env["ask_id"])
        assert parent is not None
        return store, env, parent

    def _post_comment(self, store, issue_id: str, body: str) -> None:
        store._request("POST", f"/api/issues/{issue_id}/comments",
                       {"body": body})

    def test_resolve_target_agent_is_server_side_only(self, fake):
        store = self._client(fake)
        assert store.resolve_target_agent("secretary") == TARGET_AGENT_ID
        with pytest.raises(GblPaperclipError) as err:
            store.resolve_target_agent("nobody")
        assert err.value.code == "TARGET_AGENT_NOT_CONFIGURED"

    def test_targets_table_validates_at_construction(self, fake):
        with pytest.raises(ValueError):
            client(fake, target_agents={"": TARGET_AGENT_ID})
        with pytest.raises(ValueError):
            client(fake, target_agents={"secretary": "not a token!"})
        with pytest.raises(ValueError):
            client(fake, target_agents={"secretary": 42})

    def test_dispatch_creates_the_rf_shaped_child_and_blocks_parent(
            self, fake):
        store, env, parent = self._created_ask(fake)
        outcome = store.dispatch_delegate(env)
        assert outcome["target_agent"] == TARGET_AGENT_ID
        assert outcome["reused"] is False
        child = fake.state.issues[outcome["child_issue_id"]]
        assert child["parentId"] == parent["id"]
        assert child["assigneeAgentId"] == TARGET_AGENT_ID
        assert child["status"] == "todo"
        assert child["createdByAgentId"] == AGENT_ID   # stamped by the board
        assert child["title"] == "Fixture delegate"
        full_parent = store._full_issue(parent["id"])
        expected_op = pc._rf_expected_ask_op(full_parent)
        assert child["description"].endswith(f"[{expected_op}]")
        assert "Asked by Grok Bridge Fixture on " in child["description"]
        assert "Do the harmless fixture work." in child["description"]
        # the parent is blocked on the child with a SELF-owned descriptor
        blocked = fake.state.issues[parent["id"]]
        assert blocked["status"] == "blocked"
        assert outcome["child_issue_id"] in blocked["blockedByIssueIds"]
        descriptor = blocked["unblockDescriptor"]
        assert descriptor["owner"] == {"agentId": AGENT_ID}
        assert child["identifier"] in descriptor["action"]
        assert descriptor["action"].startswith("secretary completes ")

    def test_dispatch_twice_reuses_one_child(self, fake):
        store, env, parent = self._created_ask(fake)
        first = store.dispatch_delegate(env)
        second = store.dispatch_delegate(env)
        assert second["child_issue_id"] == first["child_issue_id"]
        assert second["reused"] is True
        children = [row for row in fake.state.issues.values()
                    if row.get("parentId") == parent["id"]]
        assert len(children) == 1

    def test_ambiguous_create_landed_reconciles_by_rescan(self, fake):
        store, env, parent = self._created_ask(fake)
        fake.state.create_reply_status = 409   # the row LANDS; reply is lost
        outcome = store.dispatch_delegate(env)
        assert outcome["reused"] is True       # reconciled, never re-created
        children = [row for row in fake.state.issues.values()
                    if row.get("parentId") == parent["id"]]
        assert len(children) == 1
        assert outcome["child_issue_id"] == children[0]["id"]

    def test_ambiguous_create_not_landed_is_effect_unknown(self, fake):
        store, env, parent = self._created_ask(fake)
        fake.state.create_fail_status = 409    # refused BEFORE landing
        with pytest.raises(GblCreateEffectUnknown):
            store.dispatch_delegate(env)
        children = [row for row in fake.state.issues.values()
                    if row.get("parentId") == parent["id"]]
        assert children == []                  # nothing was created twice

    def test_definite_create_refusal_stays_typed(self, fake):
        store, env, _parent = self._created_ask(fake)
        fake.state.create_fail_status = 422    # a definite refusal
        with pytest.raises(GblPaperclipClientError) as err:
            store.dispatch_delegate(env)
        assert err.value.code == "HTTP_422"

    def test_unknown_target_refuses_before_touching_the_board(self, fake):
        store, env, parent = self._created_ask(fake)
        before = len(fake.state.issues)
        with pytest.raises(GblPaperclipError) as err:
            store.dispatch_delegate(dict(env, target="nobody"))
        assert err.value.code == "TARGET_AGENT_NOT_CONFIGURED"
        assert len(fake.state.issues) == before

    def test_missing_record_is_typed(self, fake):
        store = self._client(fake)
        with pytest.raises(GblPaperclipError) as err:
            store.dispatch_delegate(_delegate_envelope("never-created"))
        assert err.value.code == "ASK_RECORD_MISSING"

    def test_swapped_record_is_a_typed_mismatch(self, fake, monkeypatch):
        store, env, parent = self._created_ask(fake)
        stale = dict(store._issue_for(env["ask_id"]))
        # a foreign edit replaces the record between the resolve and the
        # full read: dispatch must refuse, never act on the wrong text
        fake.state.issues[parent["id"]]["description"] = "foreign rewrite"
        monkeypatch.setattr(store, "_issue_for", lambda ask_id: stale)
        with pytest.raises(GblPaperclipError) as err:
            store._ask_parent_row(env["ask_id"])
        assert err.value.code == "ASK_RECORD_MISMATCH"

    def test_ambiguous_block_patch_is_effect_unknown_then_reuse_heals(
            self, fake):
        store, env, parent = self._created_ask(fake)
        fake.state.fail_status[("PATCH", f"/api/issues/{parent['id']}")] = 503
        with pytest.raises(GblCreateEffectUnknown):
            store.dispatch_delegate(env)
        children = [row for row in fake.state.issues.values()
                    if row.get("parentId") == parent["id"]]
        assert len(children) == 1              # the child exists; relation lost
        del fake.state.fail_status[("PATCH", f"/api/issues/{parent['id']}")]
        outcome = store.dispatch_delegate(env)
        assert outcome["reused"] is True       # never a second child
        blocked = fake.state.issues[parent["id"]]
        assert blocked["status"] == "blocked"
        assert outcome["child_issue_id"] in blocked["blockedByIssueIds"]

    def test_read_dispatch_child_identity_law(self, fake):
        store, env, parent = self._created_ask(fake)
        outcome = store.dispatch_delegate(env)
        child_id = outcome["child_issue_id"]
        row = store.read_dispatch_child(env["ask_id"], child_id)
        assert row["id"] == child_id
        # a decoy issue is refused, naming the failed checks
        decoy = fake.state.add_issue("Decoy issue", "no marker here")
        with pytest.raises(GblPaperclipError) as err:
            store.read_dispatch_child(env["ask_id"], decoy)
        assert err.value.code == "RETURN_CHILD_NOT_OURS"
        assert "parent" in err.value.detail
        # a nonexistent child is refused, never an untyped 404
        with pytest.raises(GblPaperclipError) as err:
            store.read_dispatch_child(env["ask_id"], str(uuid.uuid4()))
        assert err.value.code == "RETURN_CHILD_NOT_OURS"
        # the board clearing the blocker relation at resolution must not
        # strand the return edge (RF handle_return: empty set ⇒ fall back)
        fake.state.issues[parent["id"]].pop("blockedByIssueIds", None)
        fake.state.issues[parent["id"]]["status"] = "in_progress"
        assert store.read_dispatch_child(env["ask_id"], child_id)["id"] == \
            child_id

    def test_null_creator_is_ours_foreign_creator_is_not(self, fake):
        # Real-board finding (no-seam dev proof, 2026-11-12): a board
        # serving this client's local-trusted role stamps
        # createdByAgentId=null on its creates — the creator identity is
        # not recorded.  Null is still OUR child everywhere the law is
        # applied; a NON-NULL foreign id is still refused/skipped.
        fake.state.created_by_agent_id = None
        store, env, parent = self._created_ask(fake)
        first = store.dispatch_delegate(env)
        child_id = first["child_issue_id"]
        assert fake.state.issues[child_id].get("createdByAgentId") is None
        second = store.dispatch_delegate(env)          # the reuse scan
        assert second["child_issue_id"] == child_id    # still finds it
        assert second["reused"] is True
        assert store.read_dispatch_child(env["ask_id"], child_id)["id"] == \
            child_id
        # a foreign non-null creator: refused by the return identity law
        # and invisible to the dispatch reuse scan
        fake.state.issues[child_id]["createdByAgentId"] = str(uuid.uuid4())
        with pytest.raises(GblPaperclipError) as err:
            store.read_dispatch_child(env["ask_id"], child_id)
        assert err.value.code == "RETURN_CHILD_NOT_OURS"
        assert "creator" in err.value.detail
        third = store.dispatch_delegate(env)
        assert third["reused"] is False
        assert third["child_issue_id"] != child_id
        children = [row for row in fake.state.issues.values()
                    if row.get("parentId") == parent["id"]]
        assert len(children) == 2                      # never reuses foreign

    def test_read_child_result_states_and_comment_law(self, fake):
        store, env, _parent = self._created_ask(fake)
        outcome = store.dispatch_delegate(env)
        child_id = outcome["child_issue_id"]
        identifier = fake.state.issues[child_id]["identifier"]
        # not done yet
        assert store.read_child_result(env["ask_id"], child_id) == \
            {"done": False, "cancelled": False, "answer": None,
             "child_identifier": identifier}
        # cancelled is terminal and carries nothing back
        fake.state.issues[child_id]["status"] = "cancelled"
        assert store.read_child_result(env["ask_id"], child_id) == \
            {"done": False, "cancelled": True, "answer": None,
             "child_identifier": identifier}
        # done with the assignee's own comment: the verbatim answer
        fake.state.issues[child_id]["status"] = "done"
        fake.state.comment_author = TARGET_AGENT_ID
        self._post_comment(store, child_id, "[coding-job] machine noise")
        self._post_comment(store, child_id, "The harmless fixture answer.")
        result = store.read_child_result(env["ask_id"], child_id)
        assert result == {"done": True, "cancelled": False,
                          "answer": "The harmless fixture answer.",
                          "child_identifier": identifier}

    def test_read_child_result_fallback_and_no_comment_none(self, fake):
        store, env, _parent = self._created_ask(fake, key="d-fb")
        outcome = store.dispatch_delegate(env)
        child_id = outcome["child_issue_id"]
        fake.state.issues[child_id]["status"] = "done"
        # R1 item 3: a done child with no comment at all yields None —
        # never a placeholder string return_delegate would post as the
        # ask's one permanent answer
        assert store.read_child_result(env["ask_id"], child_id)["answer"] \
            is None
        # Principal ruling INFO-1: a comment by anyone other than the
        # child's assignee is never the answer, with or without a
        # disclaimer — it would be permanent (ruling 19) and chosen by
        # whoever can comment on the child issue
        fake.state.comment_author = AGENT_ID       # not the child's assignee
        self._post_comment(store, child_id, "Some bystander comment.")
        assert store.read_child_result(env["ask_id"], child_id)["answer"] \
            is None
        # the assignee's own comment, older than a newer bystander comment,
        # is still the answer
        fake.state.comment_author = TARGET_AGENT_ID
        self._post_comment(store, child_id, "The teammate's own answer.")
        fake.state.comment_author = AGENT_ID
        self._post_comment(store, child_id, "A later bystander comment.")
        assert store.read_child_result(env["ask_id"], child_id)["answer"] \
            == "The teammate's own answer."

    def test_done_child_with_no_comment_yields_none_not_a_placeholder(
            self, fake):
        # R1 item 3: a done child with no non-machine comment used to yield
        # the string "(no answer comment on the child issue)", which
        # return_delegate posted as the ask's ONE answer — permanent under
        # ruling 19, poisoning the record even when the real answer landed
        # later.  It must yield None so the bridge reports
        # NO_ANSWER_COMMENT, posts nothing, and the next wake/scan re-reads.
        store, env, _parent = self._created_ask(fake, key="d-noans")
        outcome = store.dispatch_delegate(env)
        child_id = outcome["child_issue_id"]
        fake.state.issues[child_id]["status"] = "done"
        result = store.read_child_result(env["ask_id"], child_id)
        assert result["done"] is True
        assert result["answer"] is None        # never a placeholder string
        # machine-only comments are still no answer
        self._post_comment(store, child_id, "[coding-job] machine noise")
        result = store.read_child_result(env["ask_id"], child_id)
        assert result["answer"] is None

    def test_no_comment_delegate_reports_no_answer_and_rereads(self, fake):
        # R1 item 3 end-to-end through the REAL client (fake board), not
        # the store double: done child, no comment ⇒ NO_ANSWER_COMMENT and
        # nothing posted; the next return RE-READS (never latches), and the
        # assignee's real comment later becomes the one answer.
        store = self._client(fake)
        core = GblBridge(
            store,
            admission_table=(PrincipalAdmission(
                principal=PRINCIPAL,
                targets=frozenset({"secretary"}),
                kinds=frozenset({"delegate"}),
                max_asks_per_hour=20),),
            now=lambda: datetime.now(timezone.utc),
        )
        res = core.submit_ask(principal=PRINCIPAL, kind="delegate",
                              target="secretary", title="Fixture delegate",
                              body="Do the harmless fixture work.",
                              idempotency_key="r1-noans-e2e")
        assert res["status"] == "CREATED"
        ask_id = res["ask"]["ask_id"]
        child_id = res["dispatch"]["child_issue_id"]
        fake.state.issues[child_id]["status"] = "done"
        first = core.return_delegate(ask_id=ask_id)
        assert first["status"] == "NO_ANSWER_COMMENT"
        second = core.return_delegate(ask_id=ask_id)
        assert second["status"] == "NO_ANSWER_COMMENT"   # re-reads, no latch
        # the real answer arrives afterwards: it — not a placeholder — is
        # the ask's one answer
        fake.state.comment_author = TARGET_AGENT_ID
        fake.state.comment_author_type = "agent"
        self._post_comment(store, child_id, "The harmless fixture answer.")
        third = core.return_delegate(ask_id=ask_id)
        assert third["status"] == "RETURNED"
        record = store.read_ask(ask_id)
        answers = [e for e in record["events"] if e.get("type") == "answer"]
        assert len(answers) == 1
        assert answers[0]["text"] == "The harmless fixture answer."

    def test_identifier_recorded_is_whole_token(self):
        # R1 item 5: the block-PATCH skip compared identifiers by
        # substring — MMO-9 inside a recorded MMO-91 skipped the PATCH
        # that records the new child as a blocker, losing its
        # blockers-resolved wake.  Whole-token comparison only.
        assert pc._identifier_recorded(
            "MMO-9", "secretary completes MMO-9: fixture")
        assert pc._identifier_recorded(
            "MMO-91", "secretary completes MMO-91: fixture")
        assert not pc._identifier_recorded(
            "MMO-9", "secretary completes MMO-91: fixture")
        assert not pc._identifier_recorded(
            "MMO-9", "secretary completes MMO-90: fixture")
        assert not pc._identifier_recorded("MMO-9", "xMMO-9 fixture")
        assert not pc._identifier_recorded("MMO-9", "")
        assert not pc._identifier_recorded("", "secretary completes MMO-9")

    def test_block_patch_skip_never_matches_a_longer_identifier(self, fake):
        # R1 item 5 integration: the recorded descriptor names a previous
        # child FX-31; the reuse scan will not find child1 (foreign
        # creator), so dispatch creates FX-3 — a substring of the recorded
        # action but NOT the same token.  The PATCH must fire and record
        # FX-3 as a blocker; the exact-token case still skips.
        store, env, parent = self._created_ask(fake, key="d-tok")
        first = store.dispatch_delegate(env)
        child1 = first["child_issue_id"]
        fake.state.issues[child1]["createdByAgentId"] = str(uuid.uuid4())
        blocked = fake.state.issues[parent["id"]]
        blocked["unblockDescriptor"] = {
            "owner": {"agentId": AGENT_ID},
            "action": "secretary completes FX-31: Fixture delegate"}
        second = store.dispatch_delegate(env)
        child2 = second["child_issue_id"]
        assert child2 != child1
        assert fake.state.issues[child2]["identifier"] == "FX-3"
        blocked = fake.state.issues[parent["id"]]
        assert blocked["status"] == "blocked"
        assert child2 in blocked["blockedByIssueIds"]    # the PATCH fired
        assert "FX-3:" in blocked["unblockDescriptor"]["action"]
        # the exact-token case still skips: re-dispatch reuses child2 and
        # finds its whole identifier already recorded
        before = count(fake, "PATCH", f"/api/issues/{parent['id']}")
        third = store.dispatch_delegate(env)
        assert third["reused"] is True
        assert third["child_issue_id"] == child2
        assert count(fake, "PATCH", f"/api/issues/{parent['id']}") == before

    def test_scan_delegate_asks_is_bounded_kind_filtered_and_truncation_aware(
            self, fake):
        store = self._client(fake)
        env1 = _delegate_envelope("s-1")
        env2 = _delegate_envelope("s-2", body="fixture words. " * 120)
        env3 = envelope("s-3")                     # a question ask
        env4 = _delegate_envelope("s-4")
        for env in (env1, env2, env3, env4):
            assert store.create_ask(env) is None
        done_row = store._issue_for(env4["ask_id"])
        fake.state.issues[done_row["id"]]["status"] = "done"
        found = store.scan_delegate_asks()
        assert set(found) == {env1["ask_id"], env2["ask_id"]}
        # a list projection that CUTS the long envelope must not misread it
        # as corrupt or foreign: the row is re-read in full before parsing
        fake.state.truncate_list_descriptions_at = 300
        assert env2["ask_id"] in store.scan_delegate_asks()

    def test_scan_delegate_asks_caps_at_the_bound(self, fake):
        store = self._client(fake)
        envs = [_delegate_envelope(f"cap-{i}")
                for i in range(pc.SCAN_DELEGATE_ASKS_MAX + 5)]
        for env in envs:
            assert store.create_ask(env) is None
        assert len(store.scan_delegate_asks()) == pc.SCAN_DELEGATE_ASKS_MAX


class TestDurableLedgerLines:
    """GBL-5 micro 5a (principal, 11:45Z): a ledger line is ON DISK before
    the writer that produced it returns.

    Both ledger lines decide what this host must never do again — re-issue
    a taken number (mint ledger) and hand the same answer out twice
    (delivery ledger).  A line still sitting in a buffered stream when the
    process dies cannot make that decision, so each write is followed by
    flush → ``os.fsync`` → ``F_FULLFSYNC`` (macOS).  A sync that fails
    refuses typed with the existing ``APPEND_LOCK_UNWRITABLE``: nothing is
    posted and no answer is handed over.
    """

    @staticmethod
    def _boom(*_args, **_kwargs):
        raise OSError("sync refused (fixture)")

    @staticmethod
    def _answered(fake):
        seed = client(fake)
        row = envelope(ttl_seconds=86400 * 365 * 10)
        ask_id = row["ask_id"]
        assert seed.create_ask(row) is None
        seed.append_ask_event(ask_id, {
            "type": "answer", "answer_id": "gbm-" + "a" * 32,
            "idempotency_key": "gb-ans-5a",
            "text": "A harmless fixture answer."})
        seed.append_ask_event(ask_id, {"type": "state", "state": "ANSWERED"})
        return seed, ask_id

    def test_a_failed_mint_sync_refuses_and_posts_nothing(self, fake,
                                                          monkeypatch):
        seed = client(fake)
        row = envelope()
        assert seed.create_ask(row) is None
        comments = f"/api/issues/{fake.state.order[0]}/comments"
        monkeypatch.setattr(pc, "_sync_ledger_line", self._boom,
                            raising=False)

        with pytest.raises(GblPaperclipError) as caught:
            seed.append_ask_event(row["ask_id"],
                                  {"type": "state", "state": "ANSWERED"})

        assert caught.value.code == "APPEND_LOCK_UNWRITABLE"
        assert count(fake, "POST", comments) == 0

    def test_a_failed_delivery_sync_refuses_and_hands_nothing_over(
            self, fake, monkeypatch):
        seed, ask_id = self._answered(fake)
        comments = f"/api/issues/{fake.state.order[0]}/comments"
        before = count(fake, "POST", comments)
        monkeypatch.setattr(pc, "_sync_ledger_line", self._boom,
                            raising=False)

        with pytest.raises(GblPaperclipError) as caught:
            bridge_over(client(fake)).fetch_result(principal=PRINCIPAL,
                                                   ask_id=ask_id)

        assert caught.value.code == "APPEND_LOCK_UNWRITABLE"
        # No CONSUMED post landed, so nothing was marked *or* handed over.
        assert count(fake, "POST", comments) == before
        assert not [event for event in seed.read_ask(ask_id)["events"]
                    if event.get("type") == "state"
                    and event.get("state") == "CONSUMED"]

    def test_both_ledger_writes_sync_the_line(self, fake, monkeypatch):
        original = getattr(pc, "_sync_ledger_line", None)
        assert original is not None, "ledger writes must sync the line"
        calls = []

        def recording(handle):
            calls.append(handle)
            return original(handle)

        monkeypatch.setattr(pc, "_sync_ledger_line", recording)
        seed = client(fake)
        row = envelope(ttl_seconds=86400 * 365 * 10)
        ask_id = row["ask_id"]
        assert seed.create_ask(row) is None
        seed.append_ask_event(ask_id, {"type": "state", "state": "ANSWERED"})
        seed.record_delivery(ask_id, "gbm-" + "a" * 32)

        assert len(calls) == 2      # one mint line, one delivery line


class _RecordingNudgeSender:
    """A nudge transport that records every call.  The host-record arm
    under test must never reach it."""

    def __init__(self):
        self.calls: list[tuple[str, str, str]] = []
        self.reconcile_calls: list[tuple[str, str, str]] = []

    @staticmethod
    def _receipt():
        from control_plane.wake_dispatcher import (
            TransportOutcome, TransportReceipt)
        return TransportReceipt(outcome=TransportOutcome.ACCEPTED,
                                reason_code="accepted",
                                created_at="2026-11-11T12:00:00Z")

    def send(self, ask_id, state, native_handle):
        self.calls.append((ask_id, state, native_handle))
        return self._receipt()

    def reconcile(self, ask_id, state, native_handle):
        self.reconcile_calls.append((ask_id, state, native_handle))
        return self._receipt()


class TestHostRecordWinsEverywhere:
    """GBL-5 micro 5b (principal, 11:45Z): once the HOST's delivery record
    exists for an ask, every later decision reads it — never the listing.

    The listing can lag this host's own writes (``comment_visibility_lag``)
    and a failed CONSUMED post never lands at all.  Before this fix the
    record was consulted only by ``fetch_result``: after
    ``DELIVERY_MARK_POST_FAILED`` that call was CONSUMED while
    ``ask_status`` still said ANSWER_UNCONSUMED and both nudge arms kept
    POSTing wakes until the budget was gone.  The record is the one source
    that cannot lag, so it wins here too.  A store explicitly marked
    ``GBL_TEST_DOUBLE`` keeps the plain listing read (it keeps no record).
    """

    @staticmethod
    def _answered_with_failed_mark(fake):
        """The report's exact shape: the delivery record is written, then
        the CONSUMED post fails, so the listing still shows ANSWERED."""
        seed = client(fake)
        row = envelope(ttl_seconds=86400 * 365 * 10)
        ask_id = row["ask_id"]
        assert seed.create_ask(row) is None
        seed.append_ask_event(ask_id, {
            "type": "answer", "answer_id": "gbm-" + "a" * 32,
            "idempotency_key": "gb-ans-5b",
            "text": "A harmless fixture answer."})
        seed.append_ask_event(ask_id, {"type": "state", "state": "ANSWERED"})
        path = f"/api/issues/{fake.state.order[0]}/comments"
        fake.state.fail_status[("POST", path)] = 403
        with pytest.raises(GblBridgeError) as caught:
            bridge_over(client(fake)).fetch_result(principal=PRINCIPAL,
                                                   ask_id=ask_id)
        assert caught.value.code == "DELIVERY_MARK_POST_FAILED"
        # Later appends succeed again; the CONSUMED post itself never
        # landed, so the listing is still (truthfully) ANSWERED.
        fake.state.fail_status.pop(("POST", path))
        return seed, ask_id

    def test_status_reports_consumed_once_the_record_exists(self, fake):
        _seed, ask_id = self._answered_with_failed_mark(fake)

        status = bridge_over(client(fake)).ask_status(principal=PRINCIPAL,
                                                      ask_id=ask_id)

        assert status["status"] == "CONSUMED"
        assert status["state"] == "CONSUMED"

    def test_renudge_sends_nothing_once_the_record_exists(self, fake):
        _seed, ask_id = self._answered_with_failed_mark(fake)
        sender = _RecordingNudgeSender()
        core = bridge_over(client(fake), nudge_sender=sender,
                           routine_handle_resolver=lambda _p: "fixture-handle")

        result = core.maybe_renudge(ask_id=ask_id)

        assert result["status"] == "ALREADY_DELIVERED"
        assert sender.calls == []           # the sender was never called

    def test_reconcile_sends_nothing_once_the_record_exists(self, fake):
        seed, ask_id = self._answered_with_failed_mark(fake)
        # An unsettled attempt on the listing: the reconcile lane's whole
        # job is to observe the transport for it.  A delivered answer owes
        # no reconcile, so it must not be observed at all.
        seed.append_ask_event(ask_id, {"type": "nudge_attempt",
                                       "state": "ANSWERED",
                                       "at": "2026-11-11T12:00:00Z"})
        sender = _RecordingNudgeSender()
        core = bridge_over(client(fake), nudge_sender=sender,
                           routine_handle_resolver=lambda _p: "fixture-handle")

        result = core.reconcile_nudge(principal=PRINCIPAL, ask_id=ask_id)

        assert result["status"] == "ALREADY_DELIVERED"
        assert sender.reconcile_calls == []  # the sender was never called
