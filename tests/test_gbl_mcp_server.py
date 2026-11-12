"""GBL-3 MCP edge tests (lane GBL, BUILD_PLAN row GBL-3, ADDENDUM §4b).

The edge is a static five-tool census behind business_mcp_auth's imported
token law (audience = the resource URL, scope mastermind.gbl.bridge),
serving RFC 9728 metadata and the WWW-Authenticate challenge, dispatching to
the GBL-2 bridge over its Unix socket.  The issuer is a TEST issuer: a local
RSA key pair with an in-process JWKS source — no network issuer, no real
tenant.  One suite binds a real HTTP listener to 127.0.0.1 on an ephemeral
port and stops it in the test.  All strings are harmless fixture words.
"""
from __future__ import annotations

import asyncio
import json
import os
import socket
import threading
import unittest
from datetime import datetime, timezone
from pathlib import Path

import httpx
import jwt
import uvicorn
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from common.gbl_contract import MAX_FRAME_BYTES
from integrations.business_mcp_auth.contracts import (
    AuthAuditEvent,
    AuthError,
    load_resource_policy,
    subject_digest,
)
from integrations.business_mcp_auth.jwt_verifier import JwtAuthenticator
from integrations.gbl.admission import PrincipalAdmission as AdmissionRow
from integrations.gbl.admission import (
    DEFAULT_ADMISSION_TABLE as EDGE_EMPTY_TABLE,
)
from integrations.gbl.message_send import (
    CommandResult,
    EnvironmentRow,
    MessageSender,
)
from integrations.gbl.mcp_server import (
    RESULT_SCHEMA,
    TOOL_ARGUMENT_KEYS,
    TOOL_NAMES,
    TOOL_SCHEMA_DIGEST,
    TOOL_SPECS,
    BridgeClient,
    GblEdgeError,
    create_gbl_mcp_app,
    tool_schema_digest,
    tool_schema_snapshot,
)

ISSUER = "https://identity.gbl.example.invalid"
RESOURCE = "https://gbl.bridge.example.invalid/mcp"
METADATA_URL = "https://gbl.bridge.example.invalid/.well-known/oauth-protected-resource"
SCOPE = "mastermind.gbl.bridge"
RESOURCE_PATH = "/mcp"
METADATA_PATH = "/.well-known/oauth-protected-resource"
CLOCK = 1_700_000_000
SUB = "grok-account-fixture-words"
KID = "fixture-gbl-key"
ENV_ID = "team-dev-1"
THREAD_REF = "th_team_dev_1"
T3_HOME = "/tmp/fixture-gbl-t3-home"

_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_PEM = _KEY.private_bytes(
    serialization.Encoding.PEM,
    serialization.PrivateFormat.PKCS8,
    serialization.NoEncryption(),
)
_JWK = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(_KEY.public_key()))
_JWK.update(kid=KID, alg="RS256", use="sig")
SUBJECT_DIGEST = subject_digest(issuer=ISSUER, subject=SUB)


class Keys:
    """In-process JWKS stand-in (the TEST issuer's key source)."""

    def __init__(self):
        self.calls = 0

    async def key_for(self, kid):
        self.calls += 1
        if kid != KID:
            raise LookupError("unknown fixture kid")
        return dict(_JWK)


class Audit:
    def __init__(self):
        self.events: list[AuthAuditEvent] = []

    def emit(self, event):
        self.events.append(event)


class FakeBridge:
    """Bridge stand-in: records ops, returns canned results.

    Repair-round law (panel A H1): rejects any argument key the real bridge
    op would not accept, so an edge/bridge schema drift fails loudly here
    instead of being masked by a permissive fake.
    """

    OP_ARGUMENTS = {
        "ask": {"kind", "principal", "target", "title", "body",
                "idempotency_key", "correlation", "asker"},
        "answer": {"principal", "ask_id", "answer", "idempotency_key"},
        "question": {"principal", "ask_id"},
        "result": {"principal", "ask_id"},
        "status": {"principal", "ask_id"},
        "reconcile": {"principal", "ask_id"},
    }

    def __init__(self, result=None, error=None):
        self.calls: list[tuple[str, dict]] = []
        self.result = result if result is not None else {"status": "FIXTURE"}
        self.error = error            # (code, detail) to raise typed

    def call(self, op, arguments):
        expected = self.OP_ARGUMENTS[op]
        unknown = set(arguments) - expected
        assert not unknown, f"edge sent unknown bridge kwargs: {unknown}"
        self.calls.append((op, dict(arguments)))
        if self.error is not None:
            from integrations.gbl.mcp_server import GblEdgeError
            raise GblEdgeError(self.error[0], self.error[1])
        return dict(self.result)


class FakeRunner:
    """t3 CLI fake (the message_send runner)."""

    def __init__(self):
        self.calls: list[dict] = []
        self.responses: list[CommandResult] = []

    def run(self, argv, *, stdin, env):
        self.calls.append({"argv": list(argv), "stdin": stdin, "env": dict(env)})
        if self.responses:
            return self.responses.pop(0)
        return CommandResult(stdout='{"messages": []}', exit_code=0)


def _policy_document() -> dict:
    return {
        "schema": "mastermind.business_mcp_auth_policy.v1",
        "policy_id": "fixture.gbl.bridge",
        "resource": RESOURCE,
        "resource_metadata_url": METADATA_URL,
        "issuer": ISSUER,
        "authorization_servers": [ISSUER],
        "jwks_uri": ISSUER + "/jwks.json",
        "required_scopes": [SCOPE],
        "allowed_subject_digests": sorted([SUBJECT_DIGEST]),
        "allowed_algorithms": ["RS256"],
        "clock_skew_seconds": 0,
        "max_token_lifetime_seconds": 3600,
        "jwks_cache_ttl_seconds": 60,
        "unknown_kid_refresh_cooldown_seconds": 1,
        "fetch_failure_backoff_seconds": 1,
    }


def admission_table(**over) -> tuple:
    base = {
        "subject_digest": SUBJECT_DIGEST,
        "principal": "grok-account-main",
        "targets": frozenset({"secretary", "assurance"}),
        "kinds": frozenset({"delegate"}),
        "max_asks_per_hour": 20,
        "message_allowlist": ({"environment_id": ENV_ID,
                               "thread_ref": THREAD_REF},),
    }
    base.update(over)
    return (AdmissionRow(**base),)


def message_sender(runner) -> MessageSender:
    return MessageSender(
        runner=runner,
        allowlist=({"environment_id": ENV_ID, "thread_ref": THREAD_REF},),
        environments=(EnvironmentRow(environment_id=ENV_ID, t3code_home=T3_HOME),),
    )


class Harness:
    def __init__(self, *, table=None, bridge=None, runner=None):
        self.policy = load_resource_policy(_policy_document())
        self.auth = JwtAuthenticator(policy=self.policy, jwks_cache=Keys())
        self.audit = Audit()
        self.bridge = bridge if bridge is not None else FakeBridge()
        self.runner = runner if runner is not None else FakeRunner()
        self.sender = message_sender(self.runner)
        self.app = create_gbl_mcp_app(
            authenticator=self.auth,
            policy=self.policy,
            now=lambda: CLOCK,
            audit_sink=self.audit,
            admission_table=table if table is not None else admission_table(),
            bridge_client=self.bridge,
            message_sender=self.sender,
            allowed_hosts=("127.0.0.1", "127.0.0.1:*"),
        )
        self.client = None
        self._stop = None
        self._task = None

    async def start(self):
        ready = asyncio.Event()
        self._stop = asyncio.Event()

        async def own_lifespan():
            async with self.app.router.lifespan_context(self.app):
                ready.set()
                await self._stop.wait()

        self._task = asyncio.create_task(own_lifespan())
        await asyncio.wait_for(ready.wait(), timeout=5)
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app),
            base_url="http://127.0.0.1",
            timeout=10.0,
        )

    async def stop(self):
        if self.client is not None:
            await self.client.aclose()
            self.client = None
        if self._stop is not None:
            self._stop.set()
            await asyncio.wait_for(self._task, timeout=5)
            self._stop = None

    def token(self, **changes) -> str:
        payload = {
            "iss": ISSUER,
            "sub": SUB,
            "aud": RESOURCE,
            "iat": CLOCK - 10,
            "exp": CLOCK + 600,
            "scope": SCOPE,
            "client_id": "fixture-client",
        }
        payload.update(changes)
        return jwt.encode(payload, _PEM, algorithm="RS256",
                          headers={"kid": KID})

    async def rpc(self, method, params=None, *, token=None, rpc_id=1,
                  headers=None):
        request_headers = {
            "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": "2025-03-26",
        }
        if token is not None:
            request_headers["Authorization"] = "Bearer " + token
        if headers:
            request_headers.update(headers)
        return await self.client.post(
            RESOURCE_PATH,
            headers=request_headers,
            json={"jsonrpc": "2.0", "id": rpc_id, "method": method,
                  "params": params or {}},
        )

    async def call(self, tool, arguments, token=None):
        return await self.rpc("tools/call", {"name": tool,
                                             "arguments": arguments},
                              token=token)

    async def list_tools(self, token=None):
        return await self.rpc("tools/list", token=token)


def result_of(response: httpx.Response) -> dict:
    body = response.json()
    assert "result" in body, body
    return body["result"]


def tool_payload(response: httpx.Response) -> dict:
    result = result_of(response)
    assert result["isError"] is False, result
    return json.loads(result["content"][0]["text"])


def tool_error(response: httpx.Response) -> dict:
    result = result_of(response)
    assert result["isError"] is True, result
    payload = json.loads(result["content"][0]["text"])
    assert payload["schema"] == RESULT_SCHEMA
    assert payload["ok"] is False
    return payload["error"]


# ── The census: exactly five tools, digest-pinned ────────────────────────────


class TestCensus:
    def test_exactly_five_named_tools(self):
        assert TOOL_NAMES == frozenset({
            "team.delegate", "team.result", "team.question",
            "team.answer", "team.message",
        })

    def test_snapshot_sorted_and_digest_pinned(self):
        snapshot = tool_schema_snapshot()
        names = [row["name"] for row in snapshot]
        assert names == sorted(names)
        assert len(snapshot) == 5
        # The pinned literal equals the computed digest: any schema change
        # must update the literal and is visible in review.
        assert tool_schema_digest() == TOOL_SCHEMA_DIGEST

    def test_schemas_are_closed_objects(self):
        for row in tool_schema_snapshot():
            schema = row["input_schema"]
            assert schema["type"] == "object"
            assert schema.get("additionalProperties") is False


# ── Token admission: wrong scope / audience / revoked principal ─────────────


class TestTokenRefusals(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.harness = Harness()
        await self.harness.start()

    async def asyncTearDown(self):
        await self.harness.stop()

    async def test_wrong_scope_refused_before_dispatch(self):
        response = await self.harness.rpc(
            "tools/list",
            token=self.harness.token(scope="mastermind.gbl.other"))
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "scope_refused"
        challenge = response.headers["WWW-Authenticate"]
        assert challenge.startswith("Bearer resource_metadata=")
        assert 'error="insufficient_scope"' in challenge
        assert self.harness.bridge.calls == []

    async def test_wrong_audience_refused_before_dispatch(self):
        response = await self.harness.rpc(
            "tools/list",
            token=self.harness.token(aud="https://other.example.invalid/mcp"))
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "resource_refused"
        assert self.harness.bridge.calls == []

    async def test_revoked_principal_refused_before_dispatch(self):
        response = await self.harness.rpc(
            "tools/list", token=self.harness.token(sub="revoked-fixture"))
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "subject_refused"
        assert self.harness.bridge.calls == []

    async def test_missing_token_gets_challenge(self):
        response = await self.harness.rpc("tools/list")
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "authorization_missing"
        challenge = response.headers["WWW-Authenticate"]
        assert challenge.startswith("Bearer resource_metadata=")

    async def test_api_key_header_variant_refused(self):
        # The connector's optional static-header path is NOT admission.
        response = await self.harness.rpc(
            "tools/list", headers={"X-API-Key": "ak-fixture-words"})
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "authorization_missing"
        assert self.harness.bridge.calls == []

    async def test_bearer_api_key_refused_typed(self):
        response = await self.harness.rpc(
            "tools/list",
            headers={"Authorization": "Bearer ak-fixture-static-key"})
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "authorization_malformed"
        assert self.harness.bridge.calls == []

    async def test_valid_token_lists_five_tools(self):
        response = await self.harness.list_tools(token=self.harness.token())
        assert response.status_code == 200
        tools = result_of(response)["tools"]
        assert {tool["name"] for tool in tools} == set(TOOL_NAMES)


# ── Edge admission: the table is the door ────────────────────────────────────


class TestEdgeAdmission(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.harness = Harness()
        await self.harness.start()

    async def asyncTearDown(self):
        await self.harness.stop()

    async def test_empty_admission_table_refuses_valid_token(self):
        harness = Harness(table=EDGE_EMPTY_TABLE)
        await harness.start()
        try:
            response = await harness.call(
                "team.result", {"ask_id": "gb-" + "1" * 32},
                token=harness.token())
            error = tool_error(response)
            assert error["code"] == "ADMISSION_EMPTY"
            assert harness.bridge.calls == []
        finally:
            await harness.stop()

    async def test_principal_not_in_table_typed_refusal(self):
        # Token law passes (the subject IS policy-admitted) but the table
        # holds a different principal: typed PRINCIPAL_NOT_ADMITTED.
        other = "e" * 64
        harness = Harness(table=admission_table(subject_digest=other))
        await harness.start()
        try:
            error = tool_error(await harness.call(
                "team.result", {"ask_id": "gb-" + "1" * 32},
                token=harness.token()))
            assert error["code"] == "PRINCIPAL_NOT_ADMITTED"
            assert harness.bridge.calls == []
        finally:
            await harness.stop()

    async def test_caller_cannot_override_admission_fields(self):
        harness = self.harness
        smuggled = {
            "target": "secretary",
            "title": "Standing check",
            "body": "Fixture brief words.",
            "idempotency_key": "gb-3-0001",
            "principal": "chairman-fixture",        # not a tool argument
        }
        error = tool_error(await harness.call("team.delegate", smuggled,
                                              token=harness.token()))
        assert error["code"] == "INVALID_ARGUMENTS"
        assert harness.bridge.calls == []

    async def test_principal_comes_from_the_token_not_arguments(self):
        harness = self.harness
        payload = tool_payload(await harness.call(
            "team.delegate",
            {"target": "secretary", "title": "Standing check",
             "body": "Fixture brief words.", "idempotency_key": "gb-3-0002"},
            token=harness.token()))
        assert payload["ok"] is True
        op, arguments = harness.bridge.calls[0]
        assert op == "ask"
        assert arguments["principal"] == "grok-account-main"
        assert arguments["kind"] == "delegate"

    async def test_target_not_in_table_refused(self):
        harness = self.harness
        error = tool_error(await harness.call(
            "team.delegate",
            {"target": "nobody", "title": "Standing check",
             "body": "Fixture brief words.", "idempotency_key": "gb-3-0003"},
            token=harness.token()))
        assert error["code"] == "TARGET_NOT_ALLOWED"
        assert harness.bridge.calls == []


# ── Bounded wire: oversized payload, unknown tool ────────────────────────────


class TestBoundedWire(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.harness = Harness()
        await self.harness.start()

    async def asyncTearDown(self):
        await self.harness.stop()

    async def test_oversized_payload_frame_too_large(self):
        harness = self.harness
        huge = "a" * (MAX_FRAME_BYTES + 4096)
        error = tool_error(await harness.call(
            "team.delegate",
            {"target": "secretary", "title": "Standing check",
             "body": huge, "idempotency_key": "gb-3-0004"},
            token=harness.token()))
        assert error["code"] == "FRAME_TOO_LARGE"
        assert harness.bridge.calls == []

    async def test_no_dynamic_tool_registration(self):
        harness = self.harness
        error = tool_error(await harness.call(
            "team.admin", {"anything": "words"}, token=harness.token()))
        assert error["code"] == "TOOL_NOT_AVAILABLE"
        assert harness.bridge.calls == []
        # The census itself is frozen: list_tools returns exactly the five.
        tools = result_of(await harness.list_tools(token=harness.token()))["tools"]
        assert len(tools) == 5


# ── team.message: allowlist, thread gate, exactly-once ───────────────────────


class TestTeamMessage(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.harness = Harness()
        await self.harness.start()

    async def asyncTearDown(self):
        await self.harness.stop()

    async def test_empty_message_allowlist_refused(self):
        harness = Harness(table=admission_table(message_allowlist=()))
        await harness.start()
        try:
            error = tool_error(await harness.call(
                "team.message",
                {"environment_id": ENV_ID, "thread_ref": THREAD_REF,
                 "body": "Fixture status words.", "idempotency_key": "gb-m-1"},
                token=harness.token()))
            assert error["code"] == "ALLOWLIST_EMPTY"
            assert harness.runner.calls == []
        finally:
            await harness.stop()

    async def test_unlisted_thread_refused(self):
        harness = self.harness
        error = tool_error(await harness.call(
            "team.message",
            {"environment_id": ENV_ID, "thread_ref": "th_other",
             "body": "Fixture status words.", "idempotency_key": "gb-m-2"},
            token=harness.token()))
        assert error["code"] == "THREAD_NOT_ALLOWED"
        assert harness.runner.calls == []

    async def test_redelivered_message_sent_exactly_once(self):
        harness = self.harness
        token = harness.token()
        arguments = {"environment_id": ENV_ID, "thread_ref": THREAD_REF,
                     "body": "Fixture status words.",
                     "idempotency_key": "gb-m-3"}
        first = tool_payload(await harness.call("team.message", arguments,
                                                token=token))
        assert first["result"]["status"] == "SENT"
        # The thread now contains the marker; the redelivery scan sees it.
        marker_line = harness.runner.calls[1]["stdin"].splitlines()[0]
        import json as _json
        harness.runner.responses.append(
            CommandResult(stdout=_json.dumps(
                {"messages": [{"id": "m0", "text": marker_line}]}),
                exit_code=0))
        second = tool_payload(await harness.call("team.message", arguments,
                                                 token=token))
        assert second["result"]["status"] == "ALREADY_SENT"
        sends = [c for c in harness.runner.calls if c["argv"][2:3] == ["send"]]
        assert len(sends) == 1            # exactly one send, ever
        # The message is quoted data with the marker as the first line.
        lines = sends[0]["stdin"].splitlines()
        assert lines[0].startswith("[gb-gbm-")
        assert lines[1].startswith("GBL message from outside party")


# ── The edge really calls the GBL-2 bridge over its Unix socket ─────────────


class RecordingStore:
    """GblAskStore fake (the GBL-2 interface) for a real bridge core."""

    GBL_TEST_DOUBLE = True       # no host delivery lock: see GBL-5 micro 4


    def __init__(self):
        self.asks: dict[str, dict] = {}

    def create_ask(self, ask):
        self.asks[ask["ask_id"]] = {**ask, "events": []}

    def read_ask(self, ask_id):
        return self.asks.get(ask_id)

    def append_ask_event(self, ask_id, event):
        self.asks[ask_id]["events"].append(dict(event))

    def count_asks(self, principal, since_iso):
        return sum(1 for record in self.asks.values()
                   if record["principal"] == principal)


class TestRealBridgeSocket(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from integrations.gbl.bridge_service import (
            BridgeServer,
            BridgeServiceConfig,
            GblBridge,
            PrincipalAdmission as BridgeAdmission,
        )
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()
        self.store = RecordingStore()
        core = GblBridge(
            self.store,
            admission_table=(BridgeAdmission(
                principal="grok-account-main",
                targets=frozenset({"secretary", "assurance"}),
                kinds=frozenset({"delegate", "question"}),
                max_asks_per_hour=20),),
            now=lambda: datetime(2026, 11, 11, 12, 0, 0,
                                 tzinfo=timezone.utc))
        self.server = BridgeServer(
            BridgeServiceConfig(
                socket_path=Path(self.tmp.name) / "gbl.sock",
                allowed_peer_uids=(os.getuid(),)),
            core)
        self.server.open()
        self.client = BridgeClient(Path(self.tmp.name) / "gbl.sock")
        self.harness = Harness(bridge=self.client)
        await self.harness.start()

    async def asyncTearDown(self):
        await self.harness.stop()
        self.server.close()
        self.tmp.cleanup()

    async def test_delegate_reaches_the_real_bridge(self):
        response = await self.harness.call(
            "team.delegate",
            {"target": "secretary", "title": "Standing check",
             "body": "Fixture brief words.", "idempotency_key": "gb-3-1000"},
            token=self.harness.token())
        payload = tool_payload(response)
        assert payload["ok"] is True
        assert payload["result"]["status"] == "CREATED"
        ask_id = payload["result"]["ask"]["ask_id"]
        assert ask_id.startswith("gb-")
        assert self.store.read_ask(ask_id) is not None

    async def test_team_answer_reaches_the_real_bridge(self):
        # H1 end-to-end: the edge's team.answer drives the REAL bridge op
        # (post_answer over the socket), then team.result returns it.
        created = tool_payload(await self.harness.call(
            "team.delegate",
            {"target": "secretary", "title": "Standing check",
             "body": "Fixture brief words.", "idempotency_key": "gb-3-2000"},
            token=self.harness.token()))
        ask_id = created["result"]["ask"]["ask_id"]
        answered = tool_payload(await self.harness.call(
            "team.answer",
            {"ask_id": ask_id, "answer": "The bot's harmless fixture answer.",
             "idempotency_key": "gb-3-2001"},
            token=self.harness.token()))
        assert answered["ok"] is True
        assert answered["result"]["status"] == "ANSWERED"
        assert answered["result"]["answer_id"].startswith("gbm-")
        result = tool_payload(await self.harness.call(
            "team.result", {"ask_id": ask_id},
            token=self.harness.token()))
        assert result["result"]["status"] == "ANSWER_UNCONSUMED"
        assert result["result"]["answer"] == "The bot's harmless fixture answer."


# ── Door transport failures surface typed (LATER.md, principal 13:27Z) ──────


class TestBridgeClientTransportErrors(unittest.TestCase):
    """The door refuses BEFORE it reads and may close mid-exchange, so a
    send/recv can meet a closed or missing socket.  Every such OSError must
    surface as the typed BRIDGE_UNREACHABLE — never a raw OSError escaping
    the edge."""

    def test_missing_socket_is_typed_bridge_unreachable(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            client = BridgeClient(Path(tmp) / "no-such.sock")
            with self.assertRaises(GblEdgeError) as ctx:
                client.call("status", {"principal": "probe",
                                       "ask_id": "gb-fixture-1"})
            self.assertEqual(ctx.exception.code, "BRIDGE_UNREACHABLE")
            self.assertEqual(ctx.exception.detail, "FileNotFoundError")

    def test_silent_door_times_out_typed(self):
        # A door that accepts and then never replies raises socket.timeout
        # (an OSError) on recv — it must surface typed too.  Deterministic
        # stand-in for the close-races (EPIPE/ECONNRESET), whose outcome
        # depends on kernel timing and would make THIS test the flaky one.
        import tempfile
        from integrations.gbl import mcp_server
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "gbl.sock")
            server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            server.bind(path)
            server.listen(1)
            held = []

            def _accept_and_hold():
                connection, _ = server.accept()
                held.append(connection)      # never reply, never close

            threading.Thread(target=_accept_and_hold, daemon=True).start()
            original = mcp_server.BRIDGE_TIMEOUT_SECONDS
            mcp_server.BRIDGE_TIMEOUT_SECONDS = 0.2
            try:
                client = BridgeClient(path)
                with self.assertRaises(GblEdgeError) as ctx:
                    client.call("status", {"principal": "probe",
                                           "ask_id": "gb-fixture-2"})
                self.assertEqual(ctx.exception.code, "BRIDGE_UNREACHABLE")
                self.assertEqual(ctx.exception.detail, "TimeoutError")
            finally:
                mcp_server.BRIDGE_TIMEOUT_SECONDS = original
                for connection in held:
                    connection.close()
                server.close()


# ── One real HTTP listener on 127.0.0.1, ephemeral, stopped in the test ─────


class TestRealListener(unittest.IsolatedAsyncioTestCase):
    async def test_serves_metadata_and_refusals_over_loopback(self):
        harness = Harness()
        config = uvicorn.Config(harness.app, host="127.0.0.1", port=0,
                                log_level="warning", lifespan="on")
        server = uvicorn.Server(config)
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.bind(("127.0.0.1", 0))
        listener.listen(8)
        port = listener.getsockname()[1]
        thread = threading.Thread(target=server.run,
                                  kwargs={"sockets": [listener]}, daemon=True)
        thread.start()
        try:
            for _ in range(200):
                if server.started:
                    break
                await asyncio.sleep(0.05)
            assert server.started
            base = f"http://127.0.0.1:{port}"
            async with httpx.AsyncClient(base_url=base, timeout=10.0) as client:
                metadata = await client.get(METADATA_PATH)
                assert metadata.status_code == 200
                assert metadata.json() == {
                    "resource": RESOURCE,
                    "authorization_servers": [ISSUER],
                    "scopes_supported": [SCOPE],
                }
                denied = await client.post(
                    RESOURCE_PATH,
                    headers={"Accept": "application/json, text/event-stream",
                             "MCP-Protocol-Version": "2025-03-26"},
                    json={"jsonrpc": "2.0", "id": 1,
                          "method": "tools/list", "params": {}})
                assert denied.status_code == 401
                assert denied.headers["WWW-Authenticate"].startswith(
                    "Bearer resource_metadata=")
                allowed = await client.post(
                    RESOURCE_PATH,
                    headers={"Accept": "application/json, text/event-stream",
                             "MCP-Protocol-Version": "2025-03-26",
                             "Authorization": "Bearer " + harness.token()},
                    json={"jsonrpc": "2.0", "id": 2,
                          "method": "tools/list", "params": {}})
                assert allowed.status_code == 200
                tools = allowed.json()["result"]["tools"]
                assert {tool["name"] for tool in tools} == set(TOOL_NAMES)
        finally:
            server.should_exit = True
            thread.join(timeout=10)
            listener.close()
            await harness.stop()


# ── Repair round 1 (panel A H1 edge half + LOW advertised caps) ──────────────


class TestRepairAnswerSchema:
    def test_team_answer_uses_the_shared_contract_schema(self):
        from common.gbl_contract import ANSWER_ARGUMENT_KEYS
        assert set(TOOL_ARGUMENT_KEYS["team.answer"]) == (
            set(ANSWER_ARGUMENT_KEYS) - {"principal"})
        schema = {spec.name: spec for spec in TOOL_SPECS}["team.answer"]
        assert "answer" in schema.input_schema["properties"]
        assert "text" not in schema.input_schema["properties"]


class TestAdvertisedCaps(unittest.IsolatedAsyncioTestCase):
    """The advertised maxLength/pattern are enforced at the edge door."""

    async def _run(self, tool, arguments):
        harness = Harness()
        await harness.start()
        try:
            response = await harness.call(tool, arguments, token=harness.token())
            return harness, tool_error(response)
        finally:
            await harness.stop()

    async def test_over_cap_body_refused_before_bridge(self):
        from common.gbl_contract import BODY_MAX_CHARS
        harness = Harness()
        await harness.start()
        try:
            error = tool_error(await harness.call(
                "team.message",
                {"environment_id": ENV_ID, "thread_ref": THREAD_REF,
                 "body": "x" * (BODY_MAX_CHARS + 1),
                 "idempotency_key": "gb-m-cap"},
                token=harness.token()))
            assert error["code"] == "INVALID_ARGUMENTS"
            assert harness.runner.calls == []
        finally:
            await harness.stop()

    async def test_malformed_ask_id_refused_before_bridge(self):
        harness = Harness()
        await harness.start()
        try:
            error = tool_error(await harness.call(
                "team.result", {"ask_id": "not-an-ask-id"},
                token=harness.token()))
            assert error["code"] == "INVALID_ARGUMENTS"
            assert harness.bridge.calls == []
        finally:
            await harness.stop()

    async def test_malformed_idempotency_key_refused_before_bridge(self):
        harness = Harness()
        await harness.start()
        try:
            error = tool_error(await harness.call(
                "team.delegate",
                {"target": "secretary", "title": "Standing check",
                 "body": "Fixture brief words.",
                 "idempotency_key": "bad key with spaces!"},
                token=harness.token()))
            assert error["code"] == "INVALID_ARGUMENTS"
            assert harness.bridge.calls == []
        finally:
            await harness.stop()

    async def test_trailing_newline_is_refused_before_bridge(self):
        # re.match with a $-anchored pattern admits a trailing newline; the
        # bridge validates with fullmatch. The edge must agree: a value that
        # only passes because of the newline is refused at the door.
        harness = Harness()
        await harness.start()
        try:
            error = tool_error(await harness.call(
                "team.delegate",
                {"target": "secretary", "title": "Standing check",
                 "body": "Fixture brief words.",
                 "idempotency_key": "gb-edge-key-1\n"},
                token=harness.token()))
            assert error["code"] == "INVALID_ARGUMENTS"
            assert harness.bridge.calls == []
        finally:
            await harness.stop()
