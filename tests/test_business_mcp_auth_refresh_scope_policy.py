from __future__ import annotations

import copy

import pytest

from integrations.business_mcp_auth.contracts import (
    AUTH_POLICY_SCHEMA,
    AuthError,
    AuthErrorCode,
    load_resource_policy,
    subject_digest,
)


ISSUER = "https://identity.example.test/"
RESOURCE = "https://mcp.example.test/mcp/steward/v1"


def _policy_wire() -> dict[str, object]:
    return {
        "schema": AUTH_POLICY_SCHEMA,
        "policy_id": "mastermind-steward-v1",
        "resource": RESOURCE,
        "resource_metadata_url": (
            "https://mcp.example.test/.well-known/"
            "oauth-protected-resource/mcp/steward/v1"
        ),
        "issuer": ISSUER,
        "authorization_servers": [ISSUER],
        "jwks_uri": "https://identity.example.test/.well-known/jwks.json",
        "required_scopes": ["mastermind.steward.read"],
        "allowed_subject_digests": [
            subject_digest(issuer=ISSUER, subject="chairman-a")
        ],
        "allowed_algorithms": ["RS256"],
        "clock_skew_seconds": 30,
        "max_token_lifetime_seconds": 900,
        "jwks_cache_ttl_seconds": 60,
        "unknown_kid_refresh_cooldown_seconds": 30,
        "fetch_failure_backoff_seconds": 5,
    }


def test_resource_policy_keeps_resource_scope_as_authority() -> None:
    policy = load_resource_policy(_policy_wire())

    assert policy.required_scopes == ("mastermind.steward.read",)
    assert "offline_access" not in policy.required_scopes


@pytest.mark.parametrize(
    "required_scopes",
    (
        ["offline_access"],
        ["mastermind.steward.read", "offline_access"],
        ["offline_access", "mastermind.steward.read"],
    ),
)
def test_resource_policy_refuses_refresh_scope_as_required_tool_authority(
    required_scopes: list[str],
) -> None:
    wire = copy.deepcopy(_policy_wire())
    wire["required_scopes"] = required_scopes

    with pytest.raises(AuthError) as caught:
        load_resource_policy(wire)

    assert caught.value.code is AuthErrorCode.INVALID_POLICY
    assert caught.value.public_message == "authentication policy refused"


def test_refusal_does_not_echo_the_non_authorizing_scope() -> None:
    wire = copy.deepcopy(_policy_wire())
    wire["required_scopes"] = ["offline_access"]

    with pytest.raises(AuthError) as caught:
        load_resource_policy(wire)

    rendered = repr(caught.value) + str(caught.value)
    assert "offline_access" not in rendered
