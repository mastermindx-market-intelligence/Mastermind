"""Versioned multi-member enrollment in the existing Workspace permission owner.

Pure fixtures only: no JWT mint, credentials, installed config or socket write.
"""
import copy
import hashlib

import pytest

from integrations.business_mcp_auth.contracts import AUTH_POLICY_SCHEMA, load_resource_policy
from integrations.mastermind_workspace_app.contract import (
    BINDINGS_SCHEMA, RESOURCE, SCOPE, validate_workspace_bindings,
    workspace_authorizers, permission_stamp,
)

V2 = "mastermind.workspace_acquisition_bindings.v2"
ISSUER = "https://issuer.mastermind.example.test"


def fixture(count=4):
    subjects = [hashlib.sha256(f"opaque-member-{n}".encode()).hexdigest() for n in range(count)]
    policy = load_resource_policy({
        "schema": AUTH_POLICY_SCHEMA, "policy_id": "workspace-members-test", "resource": RESOURCE,
        "resource_metadata_url": RESOURCE + "/.well-known/oauth-protected-resource",
        "issuer": ISSUER, "authorization_servers": [ISSUER],
        "jwks_uri": ISSUER + "/.well-known/jwks.json", "required_scopes": [SCOPE],
        "allowed_subject_digests": sorted(subjects), "allowed_algorithms": ["RS256"],
        "clock_skew_seconds": 30, "max_token_lifetime_seconds": 900,
        "jwks_cache_ttl_seconds": 300, "unknown_kid_refresh_cooldown_seconds": 30,
        "fetch_failure_backoff_seconds": 5,
    })
    # Multiple members legitimately share one public OAuth client. Subject +
    # client identifies the enrollment; the email label is never an authority.
    profiles = {f"member-{i}": {"enabled": True, "binding": {
        "policy_id": policy.policy_id, "issuer_digest": hashlib.sha256(ISSUER.encode()).hexdigest(),
        "subject_digest": subject, "client_ref": "c" * 64, "resource": RESOURCE, "scopes": [SCOPE],
        "permission_digest": hashlib.sha256(f"enrollment-{i}".encode()).hexdigest(),
    }} for i, subject in enumerate(subjects)}
    return policy, {"schema": V2, "profiles": profiles, "primary_profile": "member-0"}


def principal(source, name="member-0"):
    return {k: copy.deepcopy(v) for k, v in source["profiles"][name]["binding"].items()
            if k != "permission_digest"}


def test_all_enrolled_subjects_can_share_one_oauth_client_without_a_second_registry():
    policy, source = fixture()
    _, authorize = workspace_authorizers(policy=policy, load_bindings=lambda: source)
    assert all(authorize(principal(source, name)) for name in source["profiles"])
    assert len({permission_stamp(authorize, principal(source, name)) for name in source["profiles"]}) == 4


def test_member_revocation_is_immediate_and_does_not_revoke_other_members():
    policy, source = fixture()
    _, authorize = workspace_authorizers(policy=policy, load_bindings=lambda: source)
    old = principal(source)
    source["profiles"]["member-0"]["enabled"] = False
    assert not authorize(old)
    assert all(authorize(principal(source, name)) for name in ["member-1", "member-2", "member-3"])


def test_rotated_permission_receipt_changes_only_the_selected_members_stamp():
    policy, source = fixture()
    _, authorize = workspace_authorizers(policy=policy, load_bindings=lambda: source)
    first, second = principal(source), principal(source, "member-1")
    stamps = permission_stamp(authorize, first), permission_stamp(authorize, second)
    source["profiles"]["member-0"]["binding"]["permission_digest"] = "f" * 64
    assert permission_stamp(authorize, first) != stamps[0]
    assert permission_stamp(authorize, second) == stamps[1]


def test_primary_profile_is_a_designation_not_a_privilege_escalation():
    policy, source = fixture()
    _, authorize = workspace_authorizers(policy=policy, load_bindings=lambda: source)
    admin = principal(source)
    for forged in ["admin@mastermind-x.com", {}, dict(admin, email="admin@mastermind-x.com"),
                   dict(admin, role="admin"), dict(admin, scopes=[SCOPE, "mastermind.executive.intent.submit"]),
                   dict(admin, subject_digest="0" * 64), dict(admin, client_ref="0" * 64)]:
        assert not authorize(forged)
    source["primary_profile"] = "member-2"
    assert authorize(admin) and authorize(principal(source, "member-2"))


@pytest.mark.parametrize("mutation", ["duplicate", "foreign_subject", "foreign_issuer", "scope", "email_slot", "extra", "bad_primary", "unbounded", "enabled_without_binding"])
def test_multi_member_schema_remains_closed_and_fail_dark(mutation):
    policy, source = fixture()
    if mutation == "duplicate": source["profiles"]["clone"] = copy.deepcopy(source["profiles"]["member-0"])
    if mutation == "foreign_subject": source["profiles"]["member-0"]["binding"]["subject_digest"] = "0" * 64
    if mutation == "foreign_issuer": source["profiles"]["member-0"]["binding"]["issuer_digest"] = "0" * 64
    if mutation == "scope": source["profiles"]["member-0"]["binding"]["scopes"] = ["mastermind.workspace.control"]
    if mutation == "email_slot": source["profiles"]["admin@mastermind-x.com"] = source["profiles"].pop("member-0")
    if mutation == "extra": source["admin"] = True
    if mutation == "bad_primary": source["primary_profile"] = "not-enrolled"
    if mutation == "unbounded": source["profiles"].update({f"disabled-{n}": {"enabled": False, "binding": None} for n in range(129)})
    if mutation == "enabled_without_binding": source["profiles"]["member-0"]["binding"] = None
    with pytest.raises(ValueError, match="access_denied"):
        validate_workspace_bindings(source, policy)


def test_v1_stays_exactly_two_profile_slots_with_its_original_client_uniqueness():
    policy, source = fixture()
    legacy = {"schema": BINDINGS_SCHEMA, "profiles": {
        "web": source["profiles"]["member-0"], "mac": {"enabled": False, "binding": None}}}
    assert validate_workspace_bindings(legacy, policy) == legacy
    bad = copy.deepcopy(legacy); bad["profiles"]["member-2"] = source["profiles"]["member-2"]
    with pytest.raises(ValueError): validate_workspace_bindings(bad, policy)
    bad = copy.deepcopy(legacy); bad["profiles"]["mac"] = source["profiles"]["member-1"]
    with pytest.raises(ValueError): validate_workspace_bindings(bad, policy)


def test_multi_member_validation_returns_detached_closed_bytes():
    policy, source = fixture()
    result = validate_workspace_bindings(source, policy)
    result["profiles"]["member-0"]["binding"]["permission_digest"] = "e" * 64
    assert result != source
    assert set(result) == {"schema", "profiles", "primary_profile"}
