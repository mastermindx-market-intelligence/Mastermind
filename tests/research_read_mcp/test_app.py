"""L3 authenticated Research Read MCP tests. Offline, ephemeral RSA, contract-fake port."""
from __future__ import annotations

import asyncio
import hashlib
import importlib.metadata
import json
import logging
import unittest
from collections.abc import Mapping
from dataclasses import dataclass
from types import SimpleNamespace
from urllib.parse import urlsplit

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from mcp.server.lowlevel import Server
from mcp.shared.context import RequestContext

from control_plane.principal_projection import NeutralPrincipalProjection
from integrations.business_mcp_auth.contracts import (
    AUTH_AUDIT_SCHEMA,
    AuthAuditEvent,
    AuthError,
    AuthErrorCode,
    load_resource_policy,
    subject_digest,
)
from integrations.business_mcp_auth.jwt_verifier import JwtAuthenticator
from integrations.business_mcp_auth.metadata import (
    mcp_auth_error_result,
    protected_resource_metadata,
)
from integrations.research_read_mcp import CONTRACT
from integrations.research_read_mcp.app import create_authenticated_research_server
from integrations.research_read_mcp.contracts import (
    FORBIDDEN_FIELD_NAMES,
    INPUT_SCHEMAS,
    MAX_RESULT_BYTES,
    OUTPUT_SCHEMAS,
    TOOL_ANNOTATIONS,
    TOOL_NAMES,
    ContractViolation,
    error_payload,
    result_wire_bytes,
    validate_output,
)

ISSUER = "https://identity.research.example.invalid"
RESOURCE = "https://research.example.invalid/mcp/research/v1"
METADATA = "https://research.example.invalid/.well-known/oauth-protected-resource/mcp/research/v1"
SCOPE = "mastermind.research.read"
RESOURCE_PATH = "/mcp/research/v1"
CLOCK = 1_700_000_000
MARKER = "zz-do-not-echo-9f3c"
LICENSED = "LICENSED_PROSE_7f3a_DO_NOT_LEAK"
WITHHELD = "WITHHELD_RESULT_MARKER"
EVIDENCE_CANONICAL_PREFIX = "fixture-canonical-"
LEAK_R2 = "r2://bucket/opt/object-key.r2.cloudflarestorage.com"
KNOWN_REPORT = "rpt-1"

_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_PEM = _KEY.private_bytes(
    serialization.Encoding.PEM,
    serialization.PrivateFormat.PKCS8,
    serialization.NoEncryption(),
)
_JWK = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(_KEY.public_key()))
_JWK.update(kid="fixture-key", alg="RS256", use="sig")


class Keys:
    def __init__(self, jwk):
        self.jwk = jwk
        self.calls = 0

    async def key_for(self, kid):
        self.calls += 1
        if kid != "fixture-key":
            raise ValueError("synthetic unknown key")
        return self.jwk


class Audit:
    def __init__(self):
        self.events: list[AuthAuditEvent] = []
        self.fail = False

    def emit(self, event):
        if self.fail:
            raise RuntimeError("PRIVATE_AUDIT_FAILURE")
        self.events.append(event)


@dataclass(frozen=True, slots=True)
class FakeEntitlement:
    subject_digest: str
    grant_id: str
    policy_id: str
    content_classes: frozenset[str]
    quote_limit_chars: int
    expires_at: int


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def build_fixture(tool: str, arguments: Mapping[str, object], marker: str = "") -> dict:
    if tool == "research_status":
        result = {
            "contract": CONTRACT,
            "source_state": "SOURCE_FRESH",
            "producer": {
                "last_success_at": marker or None,
                "age_seconds": 1,
                "stale": False,
            },
            "catalog": {
                "report_count": 1,
            },
            "coverage": {
                "full_text_ratio": 1.0,
                "rio_ratio": 0.0,
            },
            "degradation": [],
            "generation": {
                "server_contract": CONTRACT,
                "read_port_contract": "research.vault.read_port",
                "mastermind_commit": "b" * 40,
            },
        }
    elif tool == "research_search":
        result = {
            "contract": CONTRACT,
            "source_state": "SOURCE_FRESH",
            "candidates": [
                {
                    "report_id": KNOWN_REPORT,
                    "title": "Note",
                    "institution": "Example",
                    "side": None,
                    "published_at": None,
                    "rank": 1,
                },
                {
                    "report_id": KNOWN_REPORT + "-2",
                    "title": "Note",
                    "institution": "Example",
                    "side": "sell",
                    "published_at": "2026-01-02",
                    "rank": 2,
                },
            ],
            "coverage_state": None,
        }
    elif tool == "research_fetch":
        first_text = "fixture-text" + marker
        second_text = "fixture-tail"
        first_bytes = len(first_text.encode("utf-8"))
        second_bytes = len(second_text.encode("utf-8"))
        result = {
            "contract": CONTRACT,
            "source_state": "SOURCE_FRESH",
            "report": {
                "report_id": arguments.get("report_id", KNOWN_REPORT),
                "title": "Note",
                "institution": "Example",
                "side": "sell",
                "published_at": "2026-01-02",
            },
            "provenance": {
                "source_class": "mastermind_private_institutional",
                "license_class": "internal_licensed",
            },
            "text_layer_state": "full",
            "coverage_state": "FULL_TEXT",
            "segment_count_total": 3,
            "segments": [
                {
                    "segment_index": 0,
                    "page_start": None,
                    "page_end": None,
                    "byte_start": 0,
                    "byte_end": first_bytes,
                    "text": first_text,
                },
                {
                    "segment_index": 1,
                    "page_start": 2,
                    "page_end": 3,
                    "byte_start": first_bytes,
                    "byte_end": first_bytes + second_bytes,
                    "text": second_text,
                },
            ],
            "next_segment_start": 2,
            "rio_state": "CURRENT",
        }
    elif tool == "research_find_evidence":
        if marker:
            passage_raw = marker.encode("utf-8")
            byte_start = len(EVIDENCE_CANONICAL_PREFIX.encode("utf-8"))
            result = {
                "contract": CONTRACT,
                "source_state": "SOURCE_FRESH",
                "outcome": "FOUND",
                "passages": [{
                    "report_id": KNOWN_REPORT,
                    "passage_text": marker,
                    "byte_start": byte_start,
                    "byte_end": byte_start + len(passage_raw),
                    "text_sha256": _sha(marker),
                    "canonical_text_sha256": _sha(EVIDENCE_CANONICAL_PREFIX + marker),
                    "segment_index": 0,
                }],
                "rio_state": "CURRENT",
            }
        else:
            result = {
                "contract": CONTRACT,
                "source_state": "SOURCE_FRESH",
                "outcome": "NOT_FOUND",
                "passages": [],
                "rio_state": "NOT_REQUESTED",
            }
    else:
        raise AssertionError(tool)
    validate_output(tool, result)
    return result


def _policy_document(digests: list[str], scopes: list[str] | None = None) -> dict:
    return {
        "schema": "mastermind.business_mcp_auth_policy.v1",
        "policy_id": "fixture.research.read",
        "resource": RESOURCE,
        "resource_metadata_url": METADATA,
        "issuer": ISSUER,
        "authorization_servers": [ISSUER],
        "jwks_uri": ISSUER + "/jwks.json",
        "required_scopes": scopes or [SCOPE],
        "allowed_subject_digests": sorted(digests),
        "allowed_algorithms": ["RS256"],
        "clock_skew_seconds": 0,
        "max_token_lifetime_seconds": 3600,
        "jwks_cache_ttl_seconds": 60,
        "unknown_kid_refresh_cooldown_seconds": 1,
        "fetch_failure_backoff_seconds": 1,
    }


def _schema_keys(value: object):
    if isinstance(value, dict):
        for key, item in value.items():
            yield key
            yield from _schema_keys(item)
    elif isinstance(value, list):
        for item in value:
            yield from _schema_keys(item)


def _challenge(policy, code: AuthErrorCode) -> str:
    produced = mcp_auth_error_result(
        policy, AuthError(code), required_scopes=policy.required_scopes,
    )
    return produced["_meta"]["mcp/www_authenticate"][0]


class Harness:
    def __init__(self):
        self.clock = CLOCK
        self.keys = Keys(_JWK)
        self.audit = Audit()
        self.users = {"reader": "reader-a", "denied": "denied-canary"}
        self.subjects = {
            name: subject_digest(issuer=ISSUER, subject=sub)
            for name, sub in self.users.items()
        }
        self.policy = load_resource_policy(_policy_document(list(self.subjects.values())))
        self.auth = JwtAuthenticator(policy=self.policy, jwks_cache=self.keys)
        self.port_calls = 0
        self.port_seen: list[tuple] = []
        self.last_result = None
        self.projections: list[object] = []
        self.resolver_calls = 0
        self.resolver_mode = "allow"
        self.port_mode = "ok"
        self.result_marker = ""
        self.full = FakeEntitlement(
            subject_digest=self.subjects["reader"],
            grant_id="grant.fixture",
            policy_id=self.policy.policy_id,
            content_classes=frozenset({
                "catalog_metadata", "report_text", "evidence_passage", "rio_derived",
            }),
            quote_limit_chars=1200,
            expires_at=self.clock + 3600,
        )
        self.catalog_only = FakeEntitlement(
            subject_digest=self.subjects["reader"],
            grant_id="grant.fixture",
            policy_id=self.policy.policy_id,
            content_classes=frozenset({"catalog_metadata"}),
            quote_limit_chars=1200,
            expires_at=self.clock + 3600,
        )
        self.client = None
        self.lifespan_stop = None
        self.lifespan_task = None
        self.app = create_authenticated_research_server(
            authenticator=self.auth,
            policy=self.policy,
            now=lambda: self.clock,
            audit_sink=self.audit,
            port=self._port,
            entitlement_resolver=self._resolver,
            context_builder=self._context,
            allowed_hosts=("127.0.0.1", "127.0.0.1:*"),
        )

    def _resolver(self, projection):
        self.resolver_calls += 1
        self.projections.append(projection)
        if self.resolver_mode == "raise":
            raise RuntimeError("RESOLVER_PRIVATE")
        if self.resolver_mode == "missing-attr":
            return object()
        if self.resolver_mode == "set-classes":
            return SimpleNamespace(content_classes={"catalog_metadata", "report_text", "evidence_passage"})
        if self.resolver_mode == "flip" and self.resolver_calls >= 2:
            return None
        if projection.subject_digest == self.subjects["denied"]:
            return None
        if self.resolver_mode == "catalog-only":
            return self.catalog_only
        if projection.subject_digest == self.subjects["reader"]:
            return self.full
        return None

    def _context(self, entitlement):
        return {"marker": "l3-context", "subject_digest": getattr(entitlement, "subject_digest", None)}

    def _port(self, tool, arguments, caller_context):
        self.port_calls += 1
        recorded = dict(caller_context) if isinstance(caller_context, Mapping) else caller_context
        self.port_seen.append((tool, dict(arguments), recorded))
        if self.port_mode == "nonawaitable":
            self.last_result = {"leak": LEAK_R2}
            return self.last_result
        return self._run(tool, arguments)

    async def _run(self, tool, arguments):
        if self.port_mode == "licensed":
            raise RuntimeError(LICENSED)
        if self.port_mode == "rate":
            raise ContractViolation("RATE_LIMITED")
        if self.port_mode == "not-found":
            raise ContractViolation("NOT_FOUND")
        if self.port_mode == "invalid":
            self.last_result = {"leak": LEAK_R2}
            return self.last_result
        if self.port_mode == "too-many":
            candidate = build_fixture("research_search", {})["candidates"][0]
            candidates = []
            for index in range(21):
                item = dict(candidate)
                item["rank"] = index + 1
                item["report_id"] = f"rpt-{index + 1}"
                candidates.append(item)
            result = build_fixture("research_search", {})
            result["candidates"] = candidates
            result["leak"] = LEAK_R2
            self.last_result = result
            return result
        if self.port_mode == "long-text":
            result = build_fixture("research_fetch", {"report_id": KNOWN_REPORT})
            result["segments"][0]["text"] = LEAK_R2 + ("x" * 12001)
            self.last_result = result
            return result
        if self.port_mode == "huge":
            result = build_fixture("research_status", {})
            result["pad"] = "x" * 200000
            result["leak"] = LEAK_R2
            self.last_result = result
            return result
        if self.port_mode == "expire":
            self.clock += 100_000
        if tool == "research_fetch" and arguments.get("report_id") != KNOWN_REPORT:
            raise ContractViolation("NOT_FOUND")
        if tool == "research_find_evidence":
            report_ids = arguments.get("report_ids") or []
            if any(item != KNOWN_REPORT for item in report_ids):
                raise ContractViolation("NOT_FOUND")
        result = build_fixture(tool, arguments, self.result_marker)
        self.last_result = result
        return result

    async def start(self):
        ready = asyncio.Event()
        self.lifespan_stop = asyncio.Event()

        async def own_lifespan():
            async with self.app.router.lifespan_context(self.app):
                ready.set()
                await self.lifespan_stop.wait()

        self.lifespan_task = asyncio.create_task(own_lifespan())
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
        if self.lifespan_stop is not None:
            self.lifespan_stop.set()
            await asyncio.wait_for(self.lifespan_task, timeout=5)
            self.lifespan_stop = None

    def token(self, user="reader", **changes):
        payload = {
            "iss": ISSUER,
            "sub": self.users.get(user, user),
            "aud": RESOURCE,
            "iat": self.clock - 10,
            "exp": self.clock + 600,
            "scope": SCOPE,
            "client_id": "fixture-client",
        }
        payload.update(changes)
        return jwt.encode(payload, _PEM, algorithm="RS256", headers={"kid": "fixture-key"})

    async def rpc(self, method, params=None, *, token=None, rpc_id=1):
        headers = {
            "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": "2025-03-26",
        }
        if token is not None:
            headers["Authorization"] = "Bearer " + token
        return await self.client.post(
            RESOURCE_PATH,
            headers=headers,
            json={"jsonrpc": "2.0", "id": rpc_id, "method": method, "params": params or {}},
        )

    async def call(self, tool, arguments, **kwargs):
        return await self.rpc(
            "tools/call",
            {"name": tool, "arguments": arguments},
            **kwargs,
        )


def _result(response: httpx.Response) -> dict:
    assert response.status_code == 200, response.text[:400]
    body = response.json()
    assert "result" in body, body
    return body["result"]


def _assert_error(response: httpx.Response, code: str, marker: str | None = None) -> dict:
    result = _result(response)
    payload = error_payload(code)
    assert result["isError"] is True
    assert result["structuredContent"] == payload
    assert result["content"][0]["text"] == json.dumps(payload, separators=(",", ":"))
    if marker is not None:
        assert marker.encode() not in response.content
    return result


class ResearchReadAppTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.harness = Harness()
        await self.harness.start()

    async def asyncTearDown(self):
        await self.harness.stop()

    async def test_a1_tool_census_uses_sdk_client(self):
        harness = self.harness

        def factory(headers=None, timeout=None, auth=None):
            return httpx.AsyncClient(
                transport=httpx.ASGITransport(app=harness.app),
                headers=headers,
                timeout=timeout,
                auth=auth,
            )

        async with streamablehttp_client(
            "http://127.0.0.1" + RESOURCE_PATH,
            headers={"Authorization": "Bearer " + harness.token()},
            httpx_client_factory=factory,
            timeout=10,
        ) as (read, write, _session_id):
            async with ClientSession(read, write) as session:
                await session.initialize()
                listed = await session.list_tools()

        assert [tool.name for tool in listed.tools] == list(TOOL_NAMES)
        for tool in listed.tools:
            assert tool.inputSchema == INPUT_SCHEMAS[tool.name]
            assert tool.outputSchema == OUTPUT_SCHEMAS[tool.name]
            assert tool.annotations is not None
            assert tool.annotations.model_dump(exclude_none=True) == TOOL_ANNOTATIONS
            keys = set(_schema_keys(tool.inputSchema)) | set(_schema_keys(tool.outputSchema))
            assert keys.isdisjoint(FORBIDDEN_FIELD_NAMES)
        assert harness.port_calls == 0

    async def test_a2_challenge_refuses_before_port(self):
        harness = self.harness
        cases = [
            ("no-token", None, 401, AuthErrorCode.AUTHORIZATION_MISSING),
            ("audience", harness.token(aud="https://other.example.invalid/mcp"), 401, AuthErrorCode.RESOURCE_REFUSED),
            ("issuer", harness.token(iss="https://other.example.invalid"), 401, AuthErrorCode.ISSUER_REFUSED),
            ("expired", harness.token(iat=CLOCK - 120, exp=CLOCK - 30), 401, AuthErrorCode.TOKEN_EXPIRED),
            ("lifetime", harness.token(iat=CLOCK - 10, exp=CLOCK - 10 + 3601), 401, AuthErrorCode.TOKEN_LIFETIME_REFUSED),
            ("subject", harness.token(user="outsider"), 401, AuthErrorCode.SUBJECT_REFUSED),
            ("scope", harness.token(scope="mastermind.other.read"), 403, AuthErrorCode.SCOPE_REFUSED),
        ]
        for name, token, status, code in cases:
            harness.port_calls = 0
            harness.audit.events.clear()
            response = await harness.rpc(
                "tools/call",
                {"name": "research_status", "arguments": {}},
                token=token,
            )
            assert response.status_code == status, (name, response.status_code, response.text[:300])
            header = response.headers["www-authenticate"]
            assert header == _challenge(harness.policy, code), name
            assert "resource_metadata=" in header
            if code is AuthErrorCode.SCOPE_REFUSED:
                assert "insufficient_scope" in header
            assert harness.port_calls == 0, name
            assert len(harness.audit.events) == 1, name
            event = harness.audit.events[0]
            assert isinstance(event, AuthAuditEvent)
            assert event.schema == AUTH_AUDIT_SCHEMA
            assert event.policy_id == harness.policy.policy_id
            assert event.accepted is False
            assert event.code == code.value
            assert MARKER.encode() not in response.content

    async def test_a2_metadata_matches_public_document(self):
        harness = self.harness
        path = urlsplit(harness.policy.resource_metadata_url).path
        response = await harness.client.get(path)
        assert response.status_code == 200, response.text[:300]
        assert response.json() == protected_resource_metadata(harness.policy)
        assert harness.port_calls == 0
        assert harness.audit.events == []

    async def test_a2_accepted_audit_once(self):
        harness = self.harness
        response = await harness.call("research_status", {}, token=harness.token())
        result = _result(response)
        assert result["isError"] is False
        assert result["structuredContent"]["source_state"] == "SOURCE_FRESH"
        assert harness.port_calls == 1
        assert len(harness.audit.events) == 1
        event = harness.audit.events[0]
        assert event.accepted is True
        assert event.code == "accepted"
        assert event.schema == AUTH_AUDIT_SCHEMA
        assert event.policy_id == harness.policy.policy_id

    async def test_a2_audit_sink_failure_refuses_before_port(self):
        harness = self.harness
        harness.audit.fail = True
        response = await harness.call("research_status", {}, token=harness.token())
        assert response.status_code == 401, response.text[:300]
        assert harness.port_calls == 0
        assert b"PRIVATE_AUDIT_FAILURE" not in response.content
        assert "resource_metadata=" in response.headers["www-authenticate"]

    async def test_a3_denied_subject_is_not_an_oracle(self):
        harness = self.harness
        token = harness.token(user="denied")
        calls = [
            ("research_status", {}),
            ("research_search", {"query": "rates"}),
            ("research_fetch", {"report_id": KNOWN_REPORT}),
            ("research_find_evidence", {"claim": "rates rose", "report_ids": [KNOWN_REPORT]}),
        ]
        for tool, arguments in calls:
            response = await harness.call(tool, arguments, token=token, rpc_id=4)
            _assert_error(response, "NOT_ENTITLED", MARKER)
        assert harness.port_calls == 0

        existing = await harness.call(
            "research_fetch", {"report_id": KNOWN_REPORT}, token=token, rpc_id=4,
        )
        missing = await harness.call(
            "research_fetch", {"report_id": "missing-report"}, token=token, rpc_id=4,
        )
        assert existing.content == missing.content
        evidence_existing = await harness.call(
            "research_find_evidence",
            {"claim": "rates rose", "report_ids": [KNOWN_REPORT]},
            token=token,
            rpc_id=5,
        )
        evidence_missing = await harness.call(
            "research_find_evidence",
            {"claim": "rates rose", "report_ids": ["missing-report"]},
            token=token,
            rpc_id=5,
        )
        assert evidence_existing.content == evidence_missing.content
        assert harness.port_calls == 0

    async def test_a3_catalog_only_blocks_text_tools(self):
        harness = self.harness
        harness.resolver_mode = "catalog-only"
        token = harness.token()
        for tool, arguments in (
            ("research_fetch", {"report_id": KNOWN_REPORT}),
            ("research_fetch", {"report_id": "missing-report"}),
            ("research_find_evidence", {"claim": "rates rose", "report_ids": [KNOWN_REPORT]}),
            ("research_find_evidence", {"claim": "rates rose", "report_ids": ["missing-report"]}),
        ):
            before = harness.port_calls
            response = await harness.call(tool, arguments, token=token)
            _assert_error(response, "NOT_ENTITLED")
            assert harness.port_calls == before
        for tool, arguments in (
            ("research_status", {}),
            ("research_search", {"query": "rates"}),
        ):
            before = harness.port_calls
            response = await harness.call(tool, arguments, token=token)
            result = _result(response)
            assert result["isError"] is False
            assert harness.port_calls == before + 1
        assert [item[0] for item in harness.port_seen] == ["research_status", "research_search"]

    async def test_a3_bad_resolver_shape_and_raise(self):
        harness = self.harness
        token = harness.token()
        harness.resolver_mode = "missing-attr"
        response = await harness.call("research_status", {}, token=token)
        _assert_error(response, "NOT_ENTITLED")
        assert harness.port_calls == 0

        harness.resolver_mode = "set-classes"
        response = await harness.call("research_fetch", {"report_id": KNOWN_REPORT}, token=token)
        _assert_error(response, "NOT_ENTITLED")
        assert harness.port_calls == 0

        harness.resolver_mode = "raise"
        response = await harness.call("research_search", {"query": "rates"}, token=token)
        _assert_error(response, "INTERNAL_ERROR", "RESOLVER_PRIVATE")
        assert harness.port_calls == 0

    async def test_a4_invalid_input_is_not_echoed(self):
        harness = self.harness
        token = harness.token()
        long_id = MARKER + ("a" * (122 - len(MARKER)))
        cases = [
            ("research_search", {"query": MARKER + ("q" * 200)}, "INVALID_REQUEST"),
            ("research_search", {"query": {"nested": MARKER}}, "INVALID_REQUEST"),
            ("research_search", {"query": "rates", "extra": MARKER}, "INVALID_REQUEST"),
            ("research_search", {"query": MARKER + "\x00"}, "INVALID_REQUEST"),
            ("research_fetch", {"report_id": "../" + MARKER}, "INVALID_REQUEST"),
            ("research_fetch", {"report_id": "a/" + MARKER}, "INVALID_REQUEST"),
            ("research_fetch", {"report_id": "A" + MARKER}, "INVALID_REQUEST"),
            ("research_fetch", {"report_id": long_id}, "INVALID_REQUEST"),
            ("research_search", {"query": MARKER + ("q" * 5000)}, "INVALID_REQUEST"),
            ("no-such-tool", {"query": MARKER}, "TOOL_NOT_AVAILABLE"),
        ]
        for tool, arguments, code in cases:
            before = harness.port_calls
            response = await harness.call(tool, arguments, token=token)
            _assert_error(response, code, MARKER)
            assert harness.port_calls == before, tool

    async def test_a5_output_bounds(self):
        harness = self.harness
        token = harness.token()
        for tool, arguments in (
            ("research_status", {}),
            ("research_search", {"query": "rates"}),
            ("research_fetch", {"report_id": KNOWN_REPORT}),
            ("research_find_evidence", {"claim": "rates rose", "report_ids": [KNOWN_REPORT]}),
        ):
            response = await harness.call(tool, arguments, token=token)
            result = _result(response)
            assert result["isError"] is False
            payload = result["structuredContent"]
            validate_output(tool, payload)
            assert result_wire_bytes(payload) <= MAX_RESULT_BYTES
            encoded = json.dumps(payload)
            assert LEAK_R2 not in encoded
            assert "r2://" not in encoded
            assert "/opt/" not in encoded
            assert ".r2.cloudflarestorage.com" not in encoded
            assert "bucket" not in encoded
            assert "object-key" not in encoded
            assert LEAK_R2.encode() not in response.content
        assert harness.port_seen[0][2]["marker"] == "l3-context"

        for mode in ("invalid", "too-many", "long-text", "huge"):
            harness.port_mode = mode
            tool = "research_fetch" if mode == "long-text" else "research_status"
            arguments = {"report_id": KNOWN_REPORT} if tool == "research_fetch" else {}
            if mode == "too-many":
                tool, arguments = "research_search", {"query": "rates"}
            response = await harness.call(tool, arguments, token=token)
            _assert_error(response, "INTERNAL_ERROR", LEAK_R2)
            assert len(response.content) < 4096

    async def test_a5b_closed_v11_shapes_over_http(self):
        # Regression: the closed v1.1 success shapes must survive the public
        # HTTP app path, including the null and string search candidate forms.
        harness = self.harness
        token = harness.token()

        response = await harness.call("research_status", {}, token=token)
        payload = _result(response)["structuredContent"]
        validate_output("research_status", payload)
        assert payload["catalog"] == {"report_count": 1}
        assert payload["coverage"] == {"full_text_ratio": 1.0, "rio_ratio": 0.0}
        assert payload["degradation"] == []
        assert set(payload["generation"]) == {
            "server_contract", "read_port_contract", "mastermind_commit",
        }

        response = await harness.call("research_search", {"query": "rates"}, token=token)
        payload = _result(response)["structuredContent"]
        validate_output("research_search", payload)
        shapes = [(item["side"], item["published_at"]) for item in payload["candidates"]]
        assert (None, None) in shapes
        assert ("sell", "2026-01-02") in shapes
        assert payload["coverage_state"] is None

        response = await harness.call("research_fetch", {"report_id": KNOWN_REPORT}, token=token)
        payload = _result(response)["structuredContent"]
        validate_output("research_fetch", payload)
        assert payload["report"]["side"] == "sell"
        assert payload["report"]["published_at"] == "2026-01-02"
        assert payload["text_layer_state"] == "full"
        assert payload["coverage_state"] == "FULL_TEXT"
        first, second = payload["segments"]
        assert (first["page_start"], first["page_end"]) == (None, None)
        assert (second["page_start"], second["page_end"]) == (2, 3)
        first_raw = first["text"].encode("utf-8")
        second_raw = second["text"].encode("utf-8")
        assert (first["byte_start"], first["byte_end"]) == (0, len(first_raw))
        assert second["byte_start"] == first["byte_end"]
        assert second["byte_end"] - second["byte_start"] == len(second_raw)
        assert payload["segment_count_total"] == 3
        assert payload["next_segment_start"] == 2

        harness.result_marker = MARKER
        try:
            response = await harness.call(
                "research_find_evidence",
                {"claim": "rates rose", "report_ids": [KNOWN_REPORT]},
                token=token,
            )
        finally:
            harness.result_marker = ""
        payload = _result(response)["structuredContent"]
        validate_output("research_find_evidence", payload, quote_limit_chars=1200)
        passage = payload["passages"][0]
        raw = passage["passage_text"].encode("utf-8")
        assert passage["byte_start"] == len(EVIDENCE_CANONICAL_PREFIX.encode("utf-8"))
        assert passage["byte_end"] - passage["byte_start"] == len(raw)
        assert passage["text_sha256"] == _sha(MARKER)
        assert passage["canonical_text_sha256"] == _sha(EVIDENCE_CANONICAL_PREFIX + MARKER)
        assert passage["segment_index"] == 0
        assert harness.port_calls == 4


    async def test_a7_post_await_recheck(self):
        harness = self.harness
        token = harness.token()
        harness.result_marker = WITHHELD
        harness.port_mode = "expire"
        response = await harness.call(
            "research_fetch", {"report_id": KNOWN_REPORT}, token=token,
        )
        result = _assert_error(response, "AUTHENTICATION_REQUIRED", WITHHELD)
        assert "mcp/www_authenticate" in result["_meta"]
        assert WITHHELD in json.dumps(harness.last_result)
        assert harness.port_calls == 1

        # The expire case moved the injected clock past the token. This case
        # is a separate call, so put the clock back before the gate runs.
        harness.clock = CLOCK
        harness.port_calls = 0
        harness.port_mode = "ok"
        harness.resolver_mode = "flip"
        harness.resolver_calls = 0
        response = await harness.call(
            "research_fetch", {"report_id": KNOWN_REPORT}, token=token,
        )
        _assert_error(response, "NOT_ENTITLED", WITHHELD)
        assert harness.port_calls == 1
        assert WITHHELD in json.dumps(harness.last_result)

    async def test_a8_request_context_pin(self):
        assert importlib.metadata.version("mcp") == "1.28.1"
        assert isinstance(getattr(Server, "request_context"), property)
        assert "request" in RequestContext.__dataclass_fields__
        harness = self.harness
        response = await harness.call("research_status", {}, token=harness.token())
        assert _result(response)["isError"] is False
        assert harness.projections
        for projection in harness.projections:
            assert type(projection) is NeutralPrincipalProjection
            assert projection.subject_digest == harness.subjects["reader"]
            assert projection.policy_id == harness.policy.policy_id
            assert projection.resource == RESOURCE

    async def test_a4_unknown_tool_and_a8_share_no_port_on_bad_input(self):
        # Kept as a narrow extra assertion that pre-port refusal stays at 0
        # even when the bad value is the tool name itself.
        harness = self.harness
        before = harness.port_calls
        response = await harness.call("research_drop", {"note": MARKER}, token=harness.token())
        _assert_error(response, "TOOL_NOT_AVAILABLE", MARKER)
        assert harness.port_calls == before


def test_a9_factory_rejects_other_scopes():
    digests = [subject_digest(issuer=ISSUER, subject="reader-a")]
    for scopes in (["mastermind.other.read"], ["mastermind.other.read", SCOPE]):
        policy = load_resource_policy(_policy_document(digests, scopes))
        authenticator = JwtAuthenticator(policy=policy, jwks_cache=Keys(_JWK))
        with pytest.raises(ValueError):
            create_authenticated_research_server(
                authenticator=authenticator,
                policy=policy,
                now=lambda: CLOCK,
                audit_sink=Audit(),
                port=lambda *_args: None,
                entitlement_resolver=lambda _projection: None,
                context_builder=lambda _entitlement: {},
                allowed_hosts=("127.0.0.1",),
            )


def _record_blob(record: logging.LogRecord) -> str:
    parts = [record.getMessage(), str(record.args), str(record.exc_info), str(getattr(record, "exc_text", ""))]
    return "\n".join(parts)


async def _a6(caplog, capsys):
    harness = Harness()
    await harness.start()
    try:
        token = harness.token()
        harness.port_mode = "licensed"
        response = await harness.call("research_fetch", {"report_id": KNOWN_REPORT}, token=token)
        _assert_error(response, "INTERNAL_ERROR", LICENSED)
        assert harness.port_calls == 1

        harness.port_mode = "rate"
        response = await harness.call("research_status", {}, token=token)
        _assert_error(response, "INTERNAL_ERROR", "RATE_LIMITED")

        harness.port_mode = "nonawaitable"
        response = await harness.call("research_status", {}, token=token)
        _assert_error(response, "INTERNAL_ERROR", LEAK_R2)

        harness.port_mode = "not-found"
        response = await harness.call("research_fetch", {"report_id": KNOWN_REPORT}, token=token)
        _assert_error(response, "NOT_FOUND")

        for record in caplog.records:
            assert LICENSED not in _record_blob(record)
        captured = capsys.readouterr()
        assert LICENSED not in captured.out
        assert LICENSED not in captured.err
        for event in harness.audit.events:
            assert LICENSED not in json.dumps(event.__dict__, default=str)
    finally:
        await harness.stop()


def test_a6_sanitized_failure(caplog, capsys):
    caplog.set_level(logging.DEBUG)
    caplog.set_level(logging.DEBUG, logger="integrations.research_read_mcp.app")
    asyncio.run(_a6(caplog, capsys))


async def _a10(caplog) -> str:
    harness = Harness()
    harness.result_marker = LICENSED
    await harness.start()
    try:
        response = await harness.call(
            "research_fetch", {"report_id": KNOWN_REPORT}, token=harness.token(),
        )
        result = _result(response)
        assert result["isError"] is False
        assert LICENSED in result["structuredContent"]["segments"][0]["text"]
        return harness.subjects["reader"]
    finally:
        await harness.stop()


def test_a10_tool_log_line(caplog):
    caplog.set_level(logging.DEBUG)
    caplog.set_level(logging.DEBUG, logger="integrations.research_read_mcp.app")
    digest = asyncio.run(_a10(caplog))
    records = [record for record in caplog.records if record.name == "integrations.research_read_mcp.app"]
    assert len(records) == 1
    record = records[0]
    assert record.code == "OK"
    assert record.tool == "research_fetch"
    assert record.subject_digest == digest
    assert record.report_ids == (KNOWN_REPORT,)
    assert type(record.latency_ms) is int and record.latency_ms >= 0
    assert LICENSED not in _record_blob(record)
