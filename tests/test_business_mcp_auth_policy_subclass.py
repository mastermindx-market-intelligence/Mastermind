from __future__ import annotations

import dataclasses

import pytest

from integrations.business_mcp_auth.contracts import (
    AUTH_POLICY_SCHEMA,
    AuthError,
    AuthErrorCode,
    ResourcePolicy,
    load_resource_policy,
    subject_digest,
)
from integrations.business_mcp_auth.metadata import protected_resource_metadata


class _EqualityBypassPolicy(ResourcePolicy):
    """Hostile subclass whose reflected equality lies about canonical identity."""

    def __eq__(self, other: object) -> bool:
        return True


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


def _subclassed_policy() -> ResourcePolicy:
    policy = _policy()
    return _EqualityBypassPolicy(
        **{
            field.name: getattr(policy, field.name)
            for field in dataclasses.fields(ResourcePolicy)
        }
    )


def test_resource_policy_subclass_cannot_override_canonical_equality() -> None:
    with pytest.raises(AuthError) as caught:
        protected_resource_metadata(_subclassed_policy())

    assert caught.value.code is AuthErrorCode.INVALID_POLICY
