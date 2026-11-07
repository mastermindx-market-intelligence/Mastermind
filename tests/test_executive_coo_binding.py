from __future__ import annotations

import copy
import hashlib
import json

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
    COO_BINDING_SCHEMA_V2,
    COO_SCOPES,
    MAX_COO_BINDINGS,
    MAX_COO_BINDING_MATERIAL_BYTES,
    READ_SCOPE,
    coo_authorizer,
    coo_binding_records,
    principal_frame,
    select_coo_binding,
    validate_coo_binding,
)


ISSUER = "https://issuer.example.com"
RESOURCE = "https://mcp.mastermind-x.com/mcp"
SUBJECT = "1" * 64
CLIENT = "2" * 64
OTHER_CLIENT = "4" * 64
PERMISSION = "3" * 64
ROTATED_PERMISSION = "5" * 64


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


def principal(*, client_ref=CLIENT, subject_digest=SUBJECT, issued_at=100, expires_at=200,
              jti_digest=None, scopes=COO_SCOPES, resource=RESOURCE, issuer_digest=None,
              policy_id="mastermind-executive-coo"):
    return VerifiedPrincipal(
        policy_id=policy_id,
        issuer=ISSUER,
        issuer_digest=(
            hashlib.sha256(ISSUER.encode()).hexdigest()
            if issuer_digest is None else issuer_digest
        ),
        resource=resource,
        subject_digest=subject_digest,
        client_ref=client_ref,
        scopes=scopes,
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


def record(*, client_ref=CLIENT, subject_digest=SUBJECT, permission_digest=PERMISSION):
    """One exact enrolled-client record in the shared seven-field shape."""
    return {
        "policy_id": "mastermind-executive-coo",
        "issuer_digest": hashlib.sha256(ISSUER.encode()).hexdigest(),
        "subject_digest": subject_digest,
        "client_ref": client_ref,
        "resource": RESOURCE,
        "scopes": list(COO_SCOPES),
        "permission_digest": permission_digest,
    }


def record_digest(row):
    """The canonical record digest, re-derived independently of the owner."""
    return hashlib.sha256(
        json.dumps(
            row, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()


def v2_binding(rows, *, enabled=True):
    """A v2 document whose records are stored in ascending digest order."""
    return {
        "schema": COO_BINDING_SCHEMA_V2,
        "enabled": enabled,
        "bindings": sorted(rows, key=record_digest) if enabled else [],
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


def test_v1_document_is_never_normalized_into_v2():
    v1 = validate_coo_binding(binding(), policy())
    assert v1["schema"] == BINDING_SCHEMA
    assert "bindings" not in v1
    v2 = validate_coo_binding(v2_binding([record()]), policy())
    assert v2["schema"] == COO_BINDING_SCHEMA_V2
    assert "binding" not in v2


def test_coo_binding_records_returns_none_one_or_the_validated_tuple():
    assert coo_binding_records(binding(enabled=False), policy()) == ()
    assert coo_binding_records(binding(), policy()) == (binding()["binding"],)
    rows = [record(), record(client_ref=OTHER_CLIENT)]
    document = v2_binding(rows)
    assert coo_binding_records(document, policy()) == tuple(document["bindings"])
    assert [row["client_ref"] for row in coo_binding_records(document, policy())] == [
        row["client_ref"] for row in document["bindings"]
    ]


def test_v2_records_are_stored_in_ascending_canonical_digest_order():
    rows = [record(), record(client_ref=OTHER_CLIENT), record(client_ref="7" * 64)]
    document = v2_binding(rows)
    digests = [record_digest(row) for row in document["bindings"]]
    assert digests == sorted(digests)
    normalized = validate_coo_binding(document, policy())
    assert [record_digest(row) for row in normalized["bindings"]] == digests


def test_two_enrolled_clients_each_match_only_their_own_record():
    document = v2_binding([record(), record(client_ref=OTHER_CLIENT)])
    gate = coo_authorizer(policy=policy(), load_binding=lambda: document)

    first = gate.binding_digest(principal())
    second = gate.binding_digest(principal(client_ref=OTHER_CLIENT))
    assert first == record_digest(record())
    assert second == record_digest(record(client_ref=OTHER_CLIENT))
    assert first != second
    assert gate(principal()) is True
    assert gate(principal(client_ref=OTHER_CLIENT)) is True

    # An unenrolled client matches nothing and is never substituted.
    assert gate(principal(client_ref="9" * 64)) is False
    assert gate.binding_digest(principal(client_ref="9" * 64)) is None
    assert select_coo_binding(document, policy(), principal_frame(principal(client_ref="9" * 64))) is None


def test_foreign_scope_resource_subject_or_issuer_is_refused():
    document = v2_binding([record()])
    gate = coo_authorizer(policy=policy(), load_binding=lambda: document)
    assert gate.binding_digest(principal(scopes=(READ_SCOPE,))) is None
    assert gate.binding_digest(principal(resource="https://other.example.com/mcp")) is None
    assert gate.binding_digest(principal(subject_digest="8" * 64)) is None
    assert gate.binding_digest(principal(issuer_digest="7" * 64)) is None
    assert gate.binding_digest(principal(policy_id="other-policy")) is None


def test_select_coo_binding_requires_the_exact_six_field_frame():
    document = v2_binding([record()])
    frame = principal_frame(principal())
    assert set(frame) == {
        "policy_id", "issuer_digest", "subject_digest", "client_ref", "resource", "scopes",
    }
    selected = select_coo_binding(document, policy(), frame)
    assert selected == record()

    # A frame with an extra, a missing or a malformed field fails closed.
    assert select_coo_binding(document, policy(), {**frame, "role": "coo"}) is None
    assert select_coo_binding(
        document, policy(),
        {key: value for key, value in frame.items() if key != "client_ref"},
    ) is None
    assert select_coo_binding(document, policy(), "not-a-frame") is None
    assert select_coo_binding(document, policy(), None) is None
    # A malformed installed document also fails closed rather than granting.
    assert select_coo_binding({"schema": COO_BINDING_SCHEMA_V2}, policy(), frame) is None


def test_a_role_label_or_plain_dict_cannot_replace_a_verified_principal():
    document = v2_binding([record()])
    gate = coo_authorizer(policy=policy(), load_binding=lambda: document)
    assert gate({"role": "coo"}) is False
    assert gate.binding_digest({"role": "coo"}) is None
    assert gate.binding_digest(dict(principal_frame(principal()))) is None
    with pytest.raises(ValueError, match="access_denied"):
        principal_frame(dict(principal_frame(principal())))


@pytest.mark.parametrize(
    "mutation",
    [
        "same_identity_other_receipt",
        "duplicate_record",
        "unsorted",
        "extra_field",
        "raw_subject",
        "raw_client_id",
        "wrong_scope",
        "wrong_resource",
        "foreign_subject",
        "malformed_record",
        "unsupported_schema",
        "v1_envelope",
        "empty_enabled",
        "disabled_with_records",
        "over_limit",
    ],
)
def test_v2_binding_contract_fails_closed_on_ambiguous_or_malformed_input(mutation):
    rows = [record(), record(client_ref=OTHER_CLIENT)]
    if mutation == "same_identity_other_receipt":
        rows = [record(), record(permission_digest=ROTATED_PERMISSION)]
    elif mutation == "duplicate_record":
        rows = [record(), record()]
    elif mutation == "unsorted":
        document = {
            "schema": COO_BINDING_SCHEMA_V2,
            "enabled": True,
            "bindings": list(reversed(sorted(rows, key=record_digest))),
        }
        with pytest.raises(ValueError, match="access_denied"):
            validate_coo_binding(document, policy())
        return
    elif mutation == "extra_field":
        rows[0]["unexpected"] = True
    elif mutation == "raw_subject":
        rows[0]["subject"] = rows[0].pop("subject_digest")
    elif mutation == "raw_client_id":
        rows[0]["client_id"] = rows[0].pop("client_ref")
    elif mutation == "wrong_scope":
        rows[0]["scopes"] = [READ_SCOPE]
    elif mutation == "wrong_resource":
        rows[0]["resource"] = "https://other.example.com/mcp"
    elif mutation == "foreign_subject":
        rows[0]["subject_digest"] = "8" * 64
    elif mutation == "malformed_record":
        rows[0] = "not-a-record"
    elif mutation == "unsupported_schema":
        document = v2_binding(rows)
        document["schema"] = "mastermind.executive_coo_principal_binding.v3"
        with pytest.raises(ValueError, match="access_denied"):
            validate_coo_binding(document, policy())
        return
    elif mutation == "v1_envelope":
        document = {"schema": COO_BINDING_SCHEMA_V2, "enabled": True, "binding": record()}
        with pytest.raises(ValueError, match="access_denied"):
            validate_coo_binding(document, policy())
        return
    elif mutation == "empty_enabled":
        document = {"schema": COO_BINDING_SCHEMA_V2, "enabled": True, "bindings": []}
        with pytest.raises(ValueError, match="access_denied"):
            validate_coo_binding(document, policy())
        return
    elif mutation == "disabled_with_records":
        document = {
            "schema": COO_BINDING_SCHEMA_V2, "enabled": False,
            "bindings": sorted(rows, key=record_digest),
        }
        with pytest.raises(ValueError, match="access_denied"):
            validate_coo_binding(document, policy())
        return
    elif mutation == "over_limit":
        rows = [record(client_ref=f"{index:064x}") for index in range(MAX_COO_BINDINGS + 1)]
    with pytest.raises(ValueError, match="access_denied"):
        validate_coo_binding(v2_binding(rows), policy())


def test_maximum_v2_document_is_accepted_and_inside_the_byte_ceiling():
    rows = [record(client_ref=f"{index:064x}") for index in range(MAX_COO_BINDINGS)]
    document = v2_binding(rows)
    material = json.dumps(
        document, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")
    assert len(material) <= MAX_COO_BINDING_MATERIAL_BYTES
    assert validate_coo_binding(document, policy())["enabled"] is True


def test_disabled_v2_binding_grants_nothing():
    document = {"schema": COO_BINDING_SCHEMA_V2, "enabled": False, "bindings": []}
    assert validate_coo_binding(document, policy()) == document
    assert coo_binding_records(document, policy()) == ()
    gate = coo_authorizer(policy=policy(), load_binding=lambda: document)
    assert gate(principal()) is False
    assert gate.binding_digest(principal()) is None


def test_another_client_never_moves_the_retained_client_stamp():
    one = v2_binding([record()])
    two = v2_binding([record(), record(client_ref=OTHER_CLIENT)])
    stamp_one = coo_authorizer(policy=policy(), load_binding=lambda: one).binding_digest(principal())
    stamp_two = coo_authorizer(policy=policy(), load_binding=lambda: two).binding_digest(principal())
    v1_stamp = coo_authorizer(policy=policy(), load_binding=lambda: binding()).binding_digest(principal())
    assert stamp_one == stamp_two == v1_stamp == record_digest(record())

    # Removing the other client leaves the retained client's stamp unchanged.
    assert coo_authorizer(
        policy=policy(), load_binding=lambda: v2_binding([record(), record(client_ref="8" * 64)])
    ).binding_digest(principal()) == stamp_one


def test_authorizer_observes_revocation_on_the_next_call():
    current = {"value": v2_binding([record(), record(client_ref=OTHER_CLIENT)])}

    def load():
        return copy.deepcopy(current["value"])

    gate = coo_authorizer(policy=policy(), load_binding=load)
    assert gate(principal()) is True

    # Revoking the retained client removes exactly that grant.
    current["value"] = v2_binding([record(client_ref=OTHER_CLIENT)])
    assert gate(principal()) is False
    assert gate.binding_digest(principal()) is None
    assert gate(principal(client_ref=OTHER_CLIENT)) is True

    # A top-level disable grants nothing to anybody.
    current["value"] = {"schema": COO_BINDING_SCHEMA_V2, "enabled": False, "bindings": []}
    assert gate(principal()) is False
    assert gate(principal(client_ref=OTHER_CLIENT)) is False


def test_repeated_refresh_is_stable():
    document = v2_binding([record(), record(client_ref=OTHER_CLIENT)])
    gate = coo_authorizer(policy=policy(), load_binding=lambda: copy.deepcopy(document))
    first = gate.binding_digest(principal())
    second = gate.binding_digest(principal())
    assert first == second == record_digest(record())
    assert coo_binding_records(document, policy()) == coo_binding_records(
        copy.deepcopy(document), policy()
    )


def test_rotating_a_permission_receipt_moves_that_record_only():
    before = coo_authorizer(
        policy=policy(), load_binding=lambda: v2_binding([record()])
    ).binding_digest(principal())
    after = coo_authorizer(
        policy=policy(),
        load_binding=lambda: v2_binding([record(permission_digest=ROTATED_PERMISSION)]),
    ).binding_digest(principal())
    assert before != after
    assert after == record_digest(record(permission_digest=ROTATED_PERMISSION))
    assert validate_coo_binding(
        v2_binding([record(permission_digest=ROTATED_PERMISSION)]), policy()
    )["enabled"] is True


def test_returned_records_are_detached_from_the_installed_document():
    document = v2_binding([record(), record(client_ref=OTHER_CLIENT)])
    records = coo_binding_records(document, policy())
    target = next(item for item in records if item["client_ref"] == CLIENT)
    target["client_ref"] = "0" * 64
    target["scopes"].append("mastermind.executive.submit")

    again = coo_binding_records(document, policy())
    assert all(item["scopes"] == list(COO_SCOPES) for item in again)
    assert all(item["client_ref"] != "0" * 64 for item in again)
    assert all(item["client_ref"] != "0" * 64 for item in document["bindings"])
    assert len({id(item) for item in records}) == len(records)

    selected = select_coo_binding(document, policy(), principal_frame(principal()))
    selected["client_ref"] = "0" * 64
    assert select_coo_binding(document, policy(), principal_frame(principal()))["client_ref"] == CLIENT
