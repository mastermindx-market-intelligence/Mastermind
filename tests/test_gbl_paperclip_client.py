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
"""
from __future__ import annotations

import itertools
import json
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest

from common.gbl_contract import build_ask
from integrations.gbl.bridge_service import (
    GblBridge,
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
            status = state.fail_status.get((method, self.path))
            length = int(self.headers.get("content-length") or 0)
            body = json.loads(self.rfile.read(length)) if length else None
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
    kwargs.update(over)
    return PaperclipAskClient(fake.base, COMPANY_ID, AGENT_ID, **kwargs)


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
    """The event without the comment-provenance keys the client adds."""
    return {k: v for k, v in event.items()
            if not k.startswith("comment_")}


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
        for state in ("ANSWERED", "CONSUMED"):
            fake.state.comments[issue_id].append({
                "id": str(uuid.uuid4()), "authorAgentId": AGENT_ID,
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
    def test_from_spec_builds_a_client(self, fake, tmp_path):
        spec = {
            "kind": "gbl_bridge_service_agent_dev",
            "paperclip": {
                "base_url": fake.base,
                "company_id": COMPANY_ID,
                "agent_id": AGENT_ID,
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
                              "company_id": COMPANY_ID, "agent_id": AGENT_ID}}
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
