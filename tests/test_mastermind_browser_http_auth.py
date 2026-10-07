from __future__ import annotations

import asyncio
from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from integrations.business_mcp_auth.contracts import (
    AUTH_POLICY_SCHEMA,
    AuthErrorCode,
    load_resource_policy,
    subject_digest,
)
from integrations.business_mcp_auth.jwt_verifier import JwtAuthenticator
from integrations.mastermind_browser_plugin.http_auth import (
    BROWSER_CONTROL_SCOPE,
    BrowserHttpAuth,
    build_browser_http_auth,
)
from integrations.workbench_action_mcp.contracts import ActionCaller

ISSUER = "https://tenant.example/"
RESOURCE = "https://browser.example/mcp"
METADATA = "https://browser.example/.well-known/oauth-protected-resource/mcp"
SUBJECT = "user-a"
SUBJECT_DIGEST = subject_digest(issuer=ISSUER, subject=SUBJECT)


def policy(scope=BROWSER_CONTROL_SCOPE):
    return load_resource_policy(
        {
            "schema": AUTH_POLICY_SCHEMA,
            "policy_id": "browser-auth-test",
            "resource": RESOURCE,
            "resource_metadata_url": METADATA,
            "issuer": ISSUER,
            "authorization_servers": [ISSUER],
            "jwks_uri": "https://tenant.example/.well-known/jwks.json",
            "required_scopes": [scope],
            "allowed_subject_digests": [SUBJECT_DIGEST],
            "allowed_algorithms": ["RS256"],
            "clock_skew_seconds": 30,
            "max_token_lifetime_seconds": 900,
            "jwks_cache_ttl_seconds": 300,
            "unknown_kid_refresh_cooldown_seconds": 10,
            "fetch_failure_backoff_seconds": 10,
        }
    )


class Audit:
    def __init__(self, *, fail=False):
        self.events = []
        self.fail = fail

    def emit(self, event):
        if self.fail:
            raise RuntimeError("audit unavailable")
        self.events.append(event)


@dataclass
class Access:
    subject: str = SUBJECT_DIGEST
    client_id: str = "c" * 64
    resource: str = RESOURCE
    scopes: list[str] | None = None
    expires_at: int = 2_000_000_000

    def __post_init__(self):
        if self.scopes is None:
            self.scopes = [BROWSER_CONTROL_SCOPE]


class Verifier:
    def __init__(self, access=None):
        self.access = Access() if access is None else access
        self.tokens = []

    async def verify_token(self, token):
        self.tokens.append(token)
        return self.access


def request(*headers):
    if len(headers) % 2:
        raise ValueError("header fixture requires name/value pairs")
    rows = [
        (headers[index], headers[index + 1])
        for index in range(0, len(headers), 2)
    ]
    return SimpleNamespace(
        scope={
            "headers": [
                (name.encode("ascii"), value.encode("ascii"))
                for name, value in rows
            ]
        }
    )


def auth(*, verifier=None, audit=None):
    selected_audit = audit or Audit()
    return (
        BrowserHttpAuth(
            policy=policy(),
            token_verifier=verifier or Verifier(),
            audit_sink=selected_audit,
        ),
        selected_audit,
    )


def call_auth(adapter, inbound):
    return asyncio.run(adapter.authenticate(inbound))


def test_valid_bearer_projects_pseudonymous_action_caller_only():
    verifier = Verifier()
    adapter, audit = auth(verifier=verifier)
    caller = call_auth(
        adapter,
        request("authorization", "Bearer aaa.bbb.ccc"),
    )
    assert caller == ActionCaller(
        subject_digest=SUBJECT_DIGEST,
        client_ref="c" * 64,
        resource=RESOURCE,
        scopes=(BROWSER_CONTROL_SCOPE,),
        expires_at=2_000_000_000,
    )
    assert verifier.tokens == ["aaa.bbb.ccc"]
    assert audit.events == []
    assert adapter.auth_challenge == f'Bearer resource_metadata="{METADATA}"'


def test_missing_duplicate_and_malformed_authorization_fail_before_verifier():
    cases = [
        (request(), AuthErrorCode.AUTHORIZATION_MISSING.value),
        (
            request(
                "authorization", "Bearer aaa.bbb.ccc",
                "authorization", "Bearer ddd.eee.fff",
            ),
            AuthErrorCode.AUTHORIZATION_MALFORMED.value,
        ),
        (
            request("authorization", "Basic aaa.bbb.ccc"),
            AuthErrorCode.AUTHORIZATION_MALFORMED.value,
        ),
        (
            request("authorization", "Bearer too few"),
            AuthErrorCode.AUTHORIZATION_MALFORMED.value,
        ),
        (
            request("authorization", "Bearer aaa.bbb.ccc "),
            AuthErrorCode.AUTHORIZATION_MALFORMED.value,
        ),
    ]
    for inbound, expected_code in cases:
        verifier = Verifier()
        adapter, audit = auth(verifier=verifier)
        assert call_auth(adapter, inbound) is None
        assert verifier.tokens == []
        assert audit.events[-1].code == expected_code
        assert audit.events[-1].accepted is False
        assert audit.events[-1].policy_id == "browser-auth-test"


def test_audit_failure_on_preverification_refusal_stays_fail_closed():
    verifier = Verifier()
    adapter, _audit = auth(verifier=verifier, audit=Audit(fail=True))
    assert call_auth(adapter, request()) is None
    assert verifier.tokens == []


def test_verifier_refusal_is_not_retried_or_reinterpreted():
    verifier = Verifier(access=None)
    verifier.access = None
    adapter, audit = auth(verifier=verifier)
    assert (
        call_auth(adapter,
            request("authorization", "Bearer aaa.bbb.ccc")
        )
        is None
    )
    assert verifier.tokens == ["aaa.bbb.ccc"]
    assert audit.events == []


@pytest.mark.parametrize(
    "access",
    [
        Access(subject="f" * 64),
        Access(client_id="not-a-digest"),
        Access(resource="https://other.example/mcp"),
        Access(scopes=["other.scope"]),
        Access(expires_at=0),
    ],
)
def test_mismatched_verified_projection_stays_fail_closed(access):
    adapter, audit = auth(verifier=Verifier(access=access))
    assert (
        call_auth(adapter,
            request("authorization", "Bearer aaa.bbb.ccc")
        )
        is None
    )
    assert audit.events[-1].code == AuthErrorCode.INTERNAL_ERROR.value
    assert audit.events[-1].accepted is False


def test_builder_reuses_existing_jwt_verifier_contract_without_network():
    class Keys:
        async def key_for(self, _kid):
            raise AssertionError("builder must not fetch keys")

    selected = policy()
    authenticator = JwtAuthenticator(policy=selected, jwks_cache=Keys())
    audit = Audit()
    adapter = build_browser_http_auth(
        authenticator=authenticator,
        policy=selected,
        now=lambda: 1_800_000_000,
        audit_sink=audit,
    )
    assert isinstance(adapter, BrowserHttpAuth)
    assert adapter.policy == selected
    assert adapter.auth_challenge == f'Bearer resource_metadata="{METADATA}"'
    assert audit.events == []


def test_builder_refuses_non_browser_scope_and_policy_mismatch():
    class Keys:
        async def key_for(self, _kid):
            raise AssertionError

    browser = policy()
    wrong = policy("workbench.action")
    with pytest.raises(TypeError):
        build_browser_http_auth(
            authenticator=JwtAuthenticator(policy=wrong, jwks_cache=Keys()),
            policy=wrong,
            now=lambda: 1_800_000_000,
            audit_sink=Audit(),
        )
    with pytest.raises(TypeError):
        build_browser_http_auth(
            authenticator=JwtAuthenticator(policy=browser, jwks_cache=Keys()),
            policy=wrong,
            now=lambda: 1_800_000_000,
            audit_sink=Audit(),
        )


def test_adapter_holds_no_token_or_session_store_fields():
    adapter, _ = auth()
    names = set(adapter.__dataclass_fields__)
    for forbidden in {
        "token",
        "access_token",
        "refresh_token",
        "session",
        "cookie",
        "credential",
        "cache",
        "registry",
    }:
        assert forbidden not in names
