from __future__ import annotations

import copy
import hashlib

import pytest

from integrations.business_mcp_auth.contracts import (
    AUTH_POLICY_SCHEMA,
    VerifiedPrincipal,
    load_resource_policy,
)
from integrations.mastermind_executive_app import gateway
from integrations.mastermind_executive_app.coo_binding import (
    BINDING_SCHEMA,
    COO_ACTION_SCOPE,
    COO_SCOPES,
    READ_SCOPE,
    coo_authorizer,
    principal_frame,
    validate_coo_binding,
)


ISSUER = "https://issuer.example.com"
RESOURCE = "https://mcp.mastermind-x.com/mcp"
SUBJECT = "1" * 64
CLIENT = "2" * 64
PERMISSION = "3" * 64


def policy():
    return load_resource_policy({
        "schema": AUTH_POLICY_SCHEMA,
        "policy_id": "mastermind-executive-coo",
        "resource": RESOURCE,
        "resource_metadata_url": "https://mcp.mastermind-x.com/.well-known/oauth-protected-resource",
        "issuer": ISSUER,
        "authorization_servers": [ISSUER],
        "jwks_uri": "https://issuer.example.com/.well-known/jwks.json",
        "required_scopes": list(COO_SCOPES),
        "allowed_subject_digests": [SUBJECT],
        "allowed_algorithms": ["RS256"],
        "clock_skew_seconds": 30,
        "max_token_lifetime_seconds": 900,
        "jwks_cache_ttl_seconds": 600,
        "unknown_kid_refresh_cooldown_seconds": 30,
        "fetch_failure_backoff_seconds": 30,
    })


def principal(*, client_ref=CLIENT, subject_digest=SUBJECT, issued_at=100, expires_at=200, jti_digest=None):
    return VerifiedPrincipal(
        policy_id="mastermind-executive-coo",
        issuer=ISSUER,
        issuer_digest=hashlib.sha256(ISSUER.encode()).hexdigest(),
        resource=RESOURCE,
        subject_digest=subject_digest,
        client_ref=client_ref,
        scopes=COO_SCOPES,
        issued_at=issued_at,
        expires_at=expires_at,
        jti_digest=jti_digest,
    )


def binding(*, enabled=True, client_ref=CLIENT, subject_digest=SUBJECT):
    if not enabled:
        return {"schema": BINDING_SCHEMA, "enabled": False, "binding": None}
    return {
        "schema": BINDING_SCHEMA,
        "enabled": True,
        "binding": {
            "policy_id": "mastermind-executive-coo",
            "issuer_digest": hashlib.sha256(ISSUER.encode()).hexdigest(),
            "subject_digest": subject_digest,
            "client_ref": client_ref,
            "resource": RESOURCE,
            "scopes": list(COO_SCOPES),
            "permission_digest": PERMISSION,
        },
    }


def test_coo_scope_is_distinct_from_ceo_submit_and_reuses_read_literal():
    assert READ_SCOPE == gateway.READ_SCOPE == "mastermind.executive.read"
    assert COO_ACTION_SCOPE == "mastermind.executive.coo.act"
    assert gateway.SUBMIT_SCOPE not in COO_SCOPES
    assert COO_SCOPES == tuple(sorted((READ_SCOPE, COO_ACTION_SCOPE)))


def test_exact_verified_principal_matches_one_sealed_binding():
    selected = validate_coo_binding(binding(), policy())
    assert selected == binding()
    gate = coo_authorizer(policy=policy(), load_binding=lambda: binding())
    assert gate(principal()) is True
    digest = gate.binding_digest(principal())
    assert isinstance(digest, str) and len(digest) == 64


def test_token_instance_fields_do_not_change_durable_binding_identity():
    gate = coo_authorizer(policy=policy(), load_binding=lambda: binding())
    first = gate.binding_digest(principal(issued_at=100, expires_at=200, jti_digest="4" * 64))
    second = gate.binding_digest(principal(issued_at=300, expires_at=400, jti_digest="5" * 64))
    assert first == second
    frame = principal_frame(principal())
    assert set(frame) == {"policy_id", "issuer_digest", "subject_digest", "client_ref", "resource", "scopes"}
    assert "issued_at" not in frame and "expires_at" not in frame and "jti_digest" not in frame


@pytest.mark.parametrize(
    "mutate",
    [
        lambda row: row["binding"].__setitem__("subject_digest", "e" * 64),
        lambda row: row["binding"].__setitem__("policy_id", "other-policy"),
        lambda row: row["binding"].__setitem__("resource", "https://other.example.com/mcp"),
        lambda row: row["binding"].__setitem__("scopes", [READ_SCOPE]),
        lambda row: row["binding"].__setitem__("permission_digest", "bad"),
        lambda row: row.__setitem__("unexpected", True),
    ],
)
def test_binding_contract_fails_closed_on_identity_or_shape_drift(mutate):
    row = copy.deepcopy(binding())
    mutate(row)
    with pytest.raises(ValueError, match="access_denied"):
        validate_coo_binding(row, policy())


def test_installed_client_ref_may_rotate_but_only_exact_current_client_is_authorized():
    rotated = binding(client_ref="f" * 64)
    assert validate_coo_binding(rotated, policy()) == rotated

    gate = coo_authorizer(policy=policy(), load_binding=lambda: rotated)
    assert gate(principal(client_ref=CLIENT)) is False
    assert gate.binding_digest(principal(client_ref=CLIENT)) is None
    assert gate(principal(client_ref="f" * 64)) is True
    assert isinstance(gate.binding_digest(principal(client_ref="f" * 64)), str)


def test_unenrolled_or_wrong_client_principal_is_refused():
    gate = coo_authorizer(policy=policy(), load_binding=lambda: binding())
    assert gate(principal(client_ref="9" * 64)) is False
    assert gate(principal(subject_digest="8" * 64)) is False
    assert gate.binding_digest(principal(client_ref="oauth-client-unavailable")) is None


def test_binding_reload_revokes_without_process_local_grant_cache():
    current = {"value": binding()}
    calls = {"count": 0}

    def load():
        calls["count"] += 1
        return copy.deepcopy(current["value"])

    gate = coo_authorizer(policy=policy(), load_binding=load)
    after_construction = calls["count"]
    assert gate(principal()) is True
    assert calls["count"] == after_construction + 1

    current["value"] = binding(enabled=False)
    assert gate(principal()) is False
    assert gate.binding_digest(principal()) is None
    assert calls["count"] == after_construction + 3


def test_disabled_binding_is_valid_configuration_but_grants_nothing():
    assert validate_coo_binding(binding(enabled=False), policy())["enabled"] is False
    gate = coo_authorizer(policy=policy(), load_binding=lambda: binding(enabled=False))
    assert gate(principal()) is False


def test_policy_must_be_exact_coo_read_plus_action_scope():
    wrong = load_resource_policy({
        "schema": AUTH_POLICY_SCHEMA,
        "policy_id": "mastermind-executive-read",
        "resource": RESOURCE,
        "resource_metadata_url": "https://mcp.mastermind-x.com/.well-known/oauth-protected-resource",
        "issuer": ISSUER,
        "authorization_servers": [ISSUER],
        "jwks_uri": "https://issuer.example.com/.well-known/jwks.json",
        "required_scopes": [READ_SCOPE],
        "allowed_subject_digests": [SUBJECT],
        "allowed_algorithms": ["RS256"],
        "clock_skew_seconds": 30,
        "max_token_lifetime_seconds": 900,
        "jwks_cache_ttl_seconds": 600,
        "unknown_kid_refresh_cooldown_seconds": 30,
        "fetch_failure_backoff_seconds": 30,
    })
    with pytest.raises(ValueError, match="access_denied"):
        validate_coo_binding(binding(), wrong)


def test_binding_validator_never_accepts_raw_subject_or_client_id_fields():
    row = copy.deepcopy(binding())
    row["binding"]["subject"] = "raw-user-id"
    with pytest.raises(ValueError, match="access_denied"):
        validate_coo_binding(row, policy())
    row = copy.deepcopy(binding())
    row["binding"]["client_id"] = "raw-client-id"
    with pytest.raises(ValueError, match="access_denied"):
        validate_coo_binding(row, policy())
