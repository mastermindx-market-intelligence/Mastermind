from __future__ import annotations

import ast
import asyncio
import dataclasses
import hashlib
from pathlib import Path

import pytest

from integrations.business_mcp_auth.contracts import (
    AUTH_AUDIT_SCHEMA,
    AUTH_POLICY_SCHEMA,
    AuthAuditEvent,
    AuthError,
    AuthErrorCode,
    ResourcePolicy,
    VerifiedPrincipal,
    load_resource_policy,
    subject_digest,
)
from integrations.business_mcp_auth.jwt_verifier import JwtAuthenticator
from integrations.business_mcp_auth.mcp_adapter import MastermindTokenVerifier
from integrations.business_mcp_auth.metadata import protected_resource_metadata


NOW = 1_788_000_100
_PRIVATE_POLICY_MARKER = "PRIVATE-POLICY-MARKER"


class _EqualityBypassPolicy(ResourcePolicy):
    """Hostile subclass whose reflected equality lies about canonical identity."""

    def __eq__(self, other: object) -> bool:
        return True


class _ProjectionAuthenticator(JwtAuthenticator):
    def __init__(self, *, policy: ResourcePolicy, result: VerifiedPrincipal) -> None:
        self._policy = policy
        self.result = result
        self.calls: list[tuple[object, int]] = []

    async def verify_token(self, token: object, *, now: int) -> VerifiedPrincipal:
        self.calls.append((token, now))
        return self.result


class _AwaitPolicyDriftAuthenticator(JwtAuthenticator):
    def __init__(
        self,
        *,
        policy: ResourcePolicy,
        replacement_policy: ResourcePolicy,
        result: VerifiedPrincipal,
    ) -> None:
        self._policy = policy
        self.replacement_policy = replacement_policy
        self.result = result
        self.calls: list[tuple[object, int]] = []
        self.verifier: MastermindTokenVerifier | None = None

    async def verify_token(self, token: object, *, now: int) -> VerifiedPrincipal:
        self.calls.append((token, now))
        await asyncio.sleep(0)
        assert self.verifier is not None
        self._policy = self.replacement_policy
        self.verifier._policy = self.replacement_policy
        return self.result


class _Sink:
    def __init__(self) -> None:
        self.events: list[AuthAuditEvent] = []

    def emit(self, event: AuthAuditEvent) -> None:
        self.events.append(event)


def _run(coroutine):
    return asyncio.run(coroutine)


def _policy() -> ResourcePolicy:
    issuer = "https://identity.example.test/"
    return load_resource_policy(
        {
            "schema": AUTH_POLICY_SCHEMA,
            "policy_id": "mastermind-steward-v1",
            "resource": "https://mcp.example.test/mcp/steward/v1",
            "resource_metadata_url": (
                "https://mcp.example.test/.well-known/"
                "oauth-protected-resource/mcp/steward/v1"
            ),
            "issuer": issuer,
            "authorization_servers": [issuer],
            "jwks_uri": "https://identity.example.test/.well-known/jwks.json",
            "required_scopes": ["mastermind.steward.read"],
            "allowed_subject_digests": [
                subject_digest(issuer=issuer, subject="chairman-a")
            ],
            "allowed_algorithms": ["RS256"],
            "clock_skew_seconds": 30,
            "max_token_lifetime_seconds": 900,
            "jwks_cache_ttl_seconds": 60,
            "unknown_kid_refresh_cooldown_seconds": 30,
            "fetch_failure_backoff_seconds": 5,
        }
    )


def _replacement_policy() -> ResourcePolicy:
    issuer = "https://identity.example.test/"
    return load_resource_policy(
        {
            "schema": AUTH_POLICY_SCHEMA,
            "policy_id": "mastermind-company-v1",
            "resource": "https://mcp.example.test/mcp/company/v1",
            "resource_metadata_url": (
                "https://mcp.example.test/.well-known/"
                "oauth-protected-resource/mcp/company/v1"
            ),
            "issuer": issuer,
            "authorization_servers": [issuer],
            "jwks_uri": "https://identity.example.test/.well-known/jwks.json",
            "required_scopes": ["mastermind.company.read"],
            "allowed_subject_digests": [
                subject_digest(issuer=issuer, subject="chairman-b")
            ],
            "allowed_algorithms": ["RS256"],
            "clock_skew_seconds": 30,
            "max_token_lifetime_seconds": 900,
            "jwks_cache_ttl_seconds": 60,
            "unknown_kid_refresh_cooldown_seconds": 30,
            "fetch_failure_backoff_seconds": 5,
        }
    )


def _subclassed_policy() -> ResourcePolicy:
    policy = _policy()
    return _EqualityBypassPolicy(
        **{
            field.name: getattr(policy, field.name)
            for field in dataclasses.fields(ResourcePolicy)
        }
    )


def _tainted_policy(
    *,
    policy_id: str = "mastermind-steward-v1",
) -> ResourcePolicy:
    return dataclasses.replace(
        _policy(),
        policy_id=policy_id,
        required_scopes=("mastermind.steward.read", "offline_access"),
    )


def _principal(policy: ResourcePolicy) -> VerifiedPrincipal:
    return VerifiedPrincipal(
        policy_id=policy.policy_id,
        issuer=policy.issuer,
        issuer_digest=hashlib.sha256(policy.issuer.encode("utf-8")).hexdigest(),
        resource=policy.resource,
        subject_digest=policy.allowed_subject_digests[0],
        client_ref="2" * 64,
        scopes=policy.required_scopes,
        issued_at=1_788_000_000,
        expires_at=1_788_000_600,
        jti_digest=None,
    )


def test_resource_policy_subclass_cannot_override_canonical_equality() -> None:
    with pytest.raises(AuthError) as caught:
        protected_resource_metadata(_subclassed_policy())

    assert caught.value.code is AuthErrorCode.INVALID_POLICY


def test_tainted_authenticator_policy_cannot_construct_mcp_verifier() -> None:
    valid_policy = _policy()
    tainted_policy = _tainted_policy()
    authenticator = _ProjectionAuthenticator(
        policy=tainted_policy,
        result=_principal(valid_policy),
    )

    with pytest.raises(AuthError) as caught:
        MastermindTokenVerifier(
            authenticator=authenticator,
            policy=valid_policy,
            now=lambda: NOW,
            audit_sink=_Sink(),
        )

    assert caught.value.code is AuthErrorCode.INVALID_POLICY


def test_runtime_policy_drift_cannot_taint_refusal_audit_identity() -> None:
    valid_policy = _policy()
    drifted_policy = _tainted_policy(policy_id=_PRIVATE_POLICY_MARKER)
    authenticator = _ProjectionAuthenticator(
        policy=valid_policy,
        result=_principal(valid_policy),
    )
    sink = _Sink()
    clock_calls: list[bool] = []

    def _clock() -> int:
        clock_calls.append(True)
        return NOW

    verifier = MastermindTokenVerifier(
        authenticator=authenticator,
        policy=valid_policy,
        now=_clock,
        audit_sink=sink,
    )
    verifier._policy = drifted_policy
    authenticator._policy = drifted_policy

    assert _run(verifier.verify_token("opaque-token")) is None
    assert clock_calls == []
    assert authenticator.calls == []
    assert sink.events == [
        AuthAuditEvent(
            schema=AUTH_AUDIT_SCHEMA,
            policy_id=valid_policy.policy_id,
            code=AuthErrorCode.INTERNAL_ERROR.value,
            accepted=False,
        )
    ]
    assert _PRIVATE_POLICY_MARKER not in repr(sink.events)


def test_same_valid_policy_drift_cannot_replace_accepted_authority() -> None:
    original_policy = _policy()
    replacement_policy = _replacement_policy()
    authenticator = _ProjectionAuthenticator(
        policy=original_policy,
        result=_principal(replacement_policy),
    )
    sink = _Sink()
    clock_calls: list[bool] = []

    def _clock() -> int:
        clock_calls.append(True)
        return NOW

    verifier = MastermindTokenVerifier(
        authenticator=authenticator,
        policy=original_policy,
        now=_clock,
        audit_sink=sink,
    )
    verifier._policy = replacement_policy
    authenticator._policy = replacement_policy

    assert _run(verifier.verify_token("opaque-token")) is None
    assert clock_calls == []
    assert authenticator.calls == []
    assert sink.events == [
        AuthAuditEvent(
            schema=AUTH_AUDIT_SCHEMA,
            policy_id=original_policy.policy_id,
            code=AuthErrorCode.INTERNAL_ERROR.value,
            accepted=False,
        )
    ]


def test_policy_drift_during_await_cannot_project_replacement_authority() -> None:
    original_policy = _policy()
    replacement_policy = _replacement_policy()
    authenticator = _AwaitPolicyDriftAuthenticator(
        policy=original_policy,
        replacement_policy=replacement_policy,
        result=_principal(replacement_policy),
    )
    sink = _Sink()
    verifier = MastermindTokenVerifier(
        authenticator=authenticator,
        policy=original_policy,
        now=lambda: NOW,
        audit_sink=sink,
    )
    authenticator.verifier = verifier

    assert _run(verifier.verify_token("opaque-token")) is None
    assert authenticator.calls == [("opaque-token", NOW)]
    assert sink.events == [
        AuthAuditEvent(
            schema=AUTH_AUDIT_SCHEMA,
            policy_id=original_policy.policy_id,
            code=AuthErrorCode.INTERNAL_ERROR.value,
            accepted=False,
        )
    ]
    assert replacement_policy.policy_id not in repr(sink.events)


def _assigned_names(tree: ast.Module) -> set[str]:
    names: set[str] = set()
    for node in tree.body:
        targets: list[ast.expr] = []
        if isinstance(node, ast.Assign):
            targets = list(node.targets)
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
        for target in targets:
            if isinstance(target, ast.Name):
                names.add(target.id)
    return names


def _contract_imports(tree: ast.Module) -> set[str]:
    names: set[str] = set()
    for node in tree.body:
        if (
            isinstance(node, ast.ImportFrom)
            and node.module == "integrations.business_mcp_auth.contracts"
        ):
            names.update(alias.name for alias in node.names)
    return names


def test_non_authorizing_scope_vocabulary_has_one_contract_owner() -> None:
    root = Path(__file__).resolve().parents[1]
    contracts_tree = ast.parse(
        (root / "integrations/business_mcp_auth/contracts.py").read_text(
            encoding="utf-8"
        )
    )
    claims_tree = ast.parse(
        (root / "integrations/business_mcp_auth/claims.py").read_text(
            encoding="utf-8"
        )
   )

    assert "NON_AUTHORIZING_OAUTH_SCOPES" in _assigned_names(contracts_tree)
    assert not {
        name
        for name in _assigned_names(claims_tree)
        if "NON_AUTHORIZING_OAUTH_SCOPES" in name
    }
    assert "NON_AUTHORIZING_OAUTH_SCOPES" in _contract_imports(claims_tree)
