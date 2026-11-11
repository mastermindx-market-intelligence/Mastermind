"""GBL-4 Paperclip client tests (lane GBL, BUILD_PLAN row GBL-4).

The ``GblAskStore`` protocol (GBL-2, ``bridge_service.py:94``) implemented
over Paperclip issues+comments, driven against a fake HTTP server bound to
127.0.0.1 on an EPHEMERAL port — no real Paperclip instance is contacted.
BUILD_PLAN/notes law under test: one issue per ask assigned to the bridge
service agent; a create whose outcome is lost raises ``GblCreateEffectUnknown``
and is reconciled by read-back of the deterministic ask id — never a second
create; 4xx/5xx mapped to typed errors; the base URL is required, loopback
http only, never port 3100/3179 or any default; no credential ever rides a
request.  All strings are harmless fixture words.
"""
from __future__ import annotations

import json
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace
from urllib.parse import urlsplit

import pytest

from common.gbl_contract import build_ask
from integrations.gbl.bridge_service import (
    GblBridge,
    GblCreateEffectUnknown,
    GblBridgeError,
    PrincipalAdmission,
)
from integrations.gbl.paperclip_client import (
    GblPaperclipClientError,
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
        self.create_delay = 0.0             # sleep AFTER performing a create
        self.create_fail_status: int | None = None
        self.fail_status: dict[tuple[str, str], int] = {}
        self.slow_paths: dict[tuple[str, str], float] = {}   # sleep BEFORE
        self.next_created_at: str | None = None

    def touch(self, method: str, path: str) -> None:
        self.requests.append((method, path.split("?")[0]))

    def now_iso(self) -> str:
        if self.next_created_at is not None:
            value, self.next_created_at = self.next_created_at, None
            return value
        return datetime.now(timezone.utc).isoformat(timespec="milliseconds")

    def handle(self, method: str, path: str, body: dict | None):
        """Return (status, obj). 404 semantics mirror the real API."""
        parts = [p for p in path.split("?")[0].split("/") if p]
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
            return 200, row
        # /api/companies/{cid}/issues (list, newest first)
        if (method == "GET" and len(parts) == 4
                and parts[0] == "api" and parts[1] == "companies"
                and parts[2] == COMPANY_ID and parts[3] == "issues"):
            rows = [self.issues[iid] for iid in reversed(self.order)]
            return 200, {"issues": rows}
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
                return 200, {"comments": list(reversed(rows))}  # newest first
            if method == "POST":
                row = dict(body or {})
                row.update({"id": str(uuid.uuid4()),
                            "createdAt": self.now_iso()})
                rows.append(row)
                return 200, row
        return 404, {"error": "no such route"}


def make_handler(state: FakePaperclipState):
    class Handler(BaseHTTPRequestHandler):
        def _serve(self, method: str) -> None:
            split = urlsplit(self.path)
            state.touch(method, split.path)
            delay = state.slow_paths.get((method, split.path.split("?")[0]))
            if delay:
                time.sleep(delay)          # no mutation happened for these
            status = state.fail_status.get((method, split.path))
            length = int(self.headers.get("content-length") or 0)
            body = json.loads(self.rfile.read(length)) if length else None
            if status is None:
                status, payload = state.handle(method, split.path, body)
            else:
                payload = {"error": "fixture failure"}
            try:
                raw = json.dumps(payload).encode()
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
        assert record["events"] == [event]

    def test_events_are_returned_oldest_first(self, fake):
        ask_client = client(fake)
        row = envelope()
        ask_client.create_ask(row)
        first = {"type": "state", "state": "ANSWERED"}
        second = {"type": "state", "state": "CONSUMED"}
        ask_client.append_ask_event(row["ask_id"], first)
        ask_client.append_ask_event(row["ask_id"], second)
        # The fake answers newest-first, like the real API.
        assert ask_client.read_ask(row["ask_id"])["events"] == [first, second]

    def test_foreign_comment_body_is_ignored_as_data(self, fake):
        ask_client = client(fake)
        row = envelope()
        ask_client.create_ask(row)
        issue_id = fake.state.order[0]
        fake.state.comments[issue_id].append({
            "id": str(uuid.uuid4()),
            "createdAt": datetime.now(timezone.utc).isoformat(),
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

    def test_transport_loss_without_landing_surfaces_effect_unknown(self):
        # Nothing answers on this loopback port: the create cannot be proven
        # absent, so the law is the same — unknown effect, reconcile by
        # read-back, never a second create.
        dead = PaperclipAskClient("http://127.0.0.1:1", COMPANY_ID, AGENT_ID,
                                  timeout_seconds=0.2)
        with pytest.raises(GblBridgeError) as err:
            bridge_over(dead).submit_ask(**submits())
        assert err.value.code == "EFFECT_UNKNOWN"


# ── 4xx / 5xx → typed errors ────────────────────────────────────────────────


class TestTypedHttpErrors:
    def test_4xx_is_a_client_error(self, fake):
        fake.state.create_fail_status = 422
        with pytest.raises(GblPaperclipClientError) as err:
            client(fake).create_ask(envelope())
        assert "422" in err.value.code

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
