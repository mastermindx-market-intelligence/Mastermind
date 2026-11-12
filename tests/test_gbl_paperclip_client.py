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
        self._clock = itertools.count(1)    # strictly increasing timestamps

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
        # /api/issues/{id}
        if method == "GET" and len(parts) == 3 and parts[0] == "api" \
                and parts[1] == "issues":
            row = self.issues.get(parts[2])
            return (200, row) if row is not None else (404, {"error": "gone"})
        # /api/issues/{id}/comments
        if len(parts) == 4 and parts[0] == "api" and parts[1] == "issues" \
                and parts[3] == "comments":
            rows = self.comments.get(parts[2])
            if rows is None:
                return 404, {"error": "gone"}
            if method == "GET":
                served = list(reversed(rows))          # newest first
                if self.comments_envelope == "bare":
                    return 200, served
                if self.comments_envelope == "unknown":
                    return 200, {"data": served}
                return 200, {"comments": served}
            if method == "POST":
                row = dict(body or {})
                row.update({"id": str(uuid.uuid4()),
                            "authorAgentId": self.comment_author,
                            "createdAt": self.now_iso()})
                rows.append(row)
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


def bridge_over(client_: PaperclipAskClient) -> GblBridge:
    return GblBridge(
        client_,
        admission_table=(PrincipalAdmission(
            principal=PRINCIPAL,
            targets=frozenset({PRINCIPAL}),
            kinds=frozenset({"question"}),
            max_asks_per_hour=20,
        ),),
        now=lambda: datetime.now(timezone.utc),
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
                "hmac_key_path": str(fixture_key),
            },
        }
        path = tmp_path / "spec.json"
        path.write_text(json.dumps(spec))
        ask_client = PaperclipAskClient.from_spec(path)
        row = envelope()
        ask_client.create_ask(row)
        assert ask_client.read_ask(row["ask_id"]) is not None

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
