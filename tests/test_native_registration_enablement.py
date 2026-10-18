"""Closed native registration V2; enablement never replaces sealed acquisition."""
from __future__ import annotations

import copy
import hashlib
import json

import pytest

from ops.executive_os import capacity_source_contract as source
from tests.test_native_subscription_capacity_enrollment import bound, enrolled


def sign(row):
    unsigned = {key: value for key, value in row.items() if key != "registration_receipt_digest"}
    row["registration_receipt_digest"] = hashlib.sha256(json.dumps(
        unsigned, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        allow_nan=False).encode()).hexdigest()
    return row


def documents(*, version=2, enabled=False):
    row = {"schema": f"mastermind.provider_native_capability_registration/v{version}",
        "capacity_capability_id": "cap.fixture", "capability_generation": 3,
        "provider": "minimax", "billing_mode": "subscription", "credential_kind": "api_key",
        "execution_surface": "native_cli", "registration_state": "registered",
        "material_source_digest": "a" * 64}
    if version == 2:
        row["provider_enabled"] = enabled
    sign(row)
    document = {"repository_commit": "b" * 40, "previous_repository_commit": "c" * 40,
                "material_source_digest": "a" * 64, "registrations": [row]}
    config = {"capacity_capability_id": "cap.fixture", "native_capacity_enrollment": {
        "schema_version": "mastermind.native_subscription_capacity_enrollment/v1",
        "host_ref": "host-" + "1" * 64, "os_principal_ref": "principal-" + "2" * 64,
        "config_custody_ref": "custody-" + "3" * 64, "enrollment_state": "enrolled",
        "registration_source": {"release_commit": "b" * 40, "previous_release_commit": "c" * 40,
                                "material_source_digest": "a" * 64, "export_sha256": "d" * 64}}}
    return config, document, row


@pytest.mark.parametrize("version,enabled", [(1, False), (2, False), (2, True)])
def test_recognized_export_returns_exact_detached_selected_row(version, enabled):
    config, document, row = documents(version=version, enabled=enabled)
    result = source.validate_native_registration_document(config, document)
    assert result == row and result is not row
    assert ("provider_enabled" in result) is (version == 2)
    if version == 2:
        assert result["provider_enabled"] is enabled
    result["registration_state"] = "revoked"
    assert row["registration_state"] == "registered"


@pytest.mark.parametrize("bad", [None, 0, 1, "false", "true", [], {}])
def test_v2_strict_bool_even_with_a_matching_receipt(bad):
    config, document, row = documents()
    row["provider_enabled"] = bad
    sign(row)
    with pytest.raises(source.CapacitySourceContractError, match="^NATIVE_REGISTRATION_INVALID$"):
        source.validate_native_registration_document(config, document)


@pytest.mark.parametrize("edge", ["v1-field", "v2-missing", "extra-auth", "unknown-schema",
                                   "schema-object", "schema-bool", "missing-schema"])
def test_closed_version_shapes_refuse(edge):
    config, document, row = documents(version=1 if edge == "v1-field" else 2)
    if edge == "v1-field": row["provider_enabled"] = False
    if edge == "v2-missing": del row["provider_enabled"]
    if edge == "extra-auth": row["authenticated"] = True
    if edge == "unknown-schema": row["schema"] += "-unknown"
    if edge == "schema-object": row["schema"] = {}
    if edge == "schema-bool": row["schema"] = True
    if edge == "missing-schema": del row["schema"]
    sign(row)
    with pytest.raises(source.CapacitySourceContractError, match="^NATIVE_REGISTRATION_INVALID$"):
        source.validate_native_registration_document(config, document)


def test_enablement_tamper_requires_new_receipt():
    config, document, row = documents()
    row["provider_enabled"] = True
    with pytest.raises(source.CapacitySourceContractError, match="^NATIVE_REGISTRATION_DIGEST_MISMATCH$"):
        source.validate_native_registration_document(config, document)
    sign(row)
    assert source.validate_native_registration_document(config, document)["provider_enabled"] is True


@pytest.mark.parametrize("foreign_first", [False, True])
@pytest.mark.parametrize("edge", ["mixed-version", "bad-bool", "revoked-enabled",
                                   "wrong-source", "duplicate", "bad-digest", "not-a-row"])
def test_foreign_rows_receive_same_validation_before_selection(foreign_first, edge):
    config, document, row = documents()
    foreign = copy.deepcopy(row)
    foreign["capacity_capability_id"] = "cap.other"
    if edge == "mixed-version":
        foreign["schema"] = "mastermind.provider_native_capability_registration/v1"
        del foreign["provider_enabled"]
    if edge == "bad-bool": foreign["provider_enabled"] = 1
    if edge == "revoked-enabled":
        foreign.update(registration_state="revoked", provider_enabled=True)
    if edge == "wrong-source": foreign["material_source_digest"] = "0" * 64
    if edge == "duplicate": foreign["capacity_capability_id"] = row["capacity_capability_id"]
    sign(foreign)
    if edge == "bad-digest": foreign["registration_receipt_digest"] = "0" * 64
    if edge == "not-a-row": foreign = []
    document["registrations"] = [foreign, row] if foreign_first else [row, foreign]
    with pytest.raises(source.CapacitySourceContractError):
        source.validate_native_registration_document(config, document)


def test_revoked_disabled_foreign_row_is_retained_but_cannot_be_selected():
    config, document, row = documents()
    foreign = sign(dict(row, capacity_capability_id="cap.other", registration_state="revoked"))
    document["registrations"].append(foreign)
    assert source.validate_native_registration_document(config, document) == row
    config["capacity_capability_id"] = "cap.other"
    with pytest.raises(source.CapacitySourceContractError, match="^NATIVE_REGISTRATION_NOT_CURRENT$"):
        source.validate_native_registration_document(config, document)


@pytest.mark.parametrize("field", ["repository_commit", "previous_repository_commit", "material_source_digest"])
def test_v2_preserves_exact_source_binding(field):
    config, document, row = documents(enabled=True)
    document[field] = "0" * len(document[field])
    with pytest.raises(source.CapacitySourceContractError, match="^NATIVE_REGISTRATION_SOURCE_MISMATCH$"):
        source.validate_native_registration_document(config, document)


@pytest.mark.parametrize("enabled", [False, True])
def test_existing_realm_acquisition_carries_only_sealed_selected_enablement(bound, enabled):
    bound.row.update(schema="mastermind.provider_native_capability_registration/v2",
                     provider_enabled=enabled)
    sign(bound.row)
    owner = bound.publish()
    result = source.acquire_native_registration(owner)
    assert result["provider_enabled"] is enabled
    assert result["registration_receipt_digest"] == bound.row["registration_receipt_digest"]
    assert result["source_receipt_digest"] == bound.f.config[
        "native_capacity_enrollment"]["registration_source"]["export_sha256"]
    # Identity enrollment remains its original contract, without readiness claims.
    enrollment = owner.observe_capacity_enrollment()
    assert "provider_enabled" not in enrollment
    assert "realm_auth" not in enrollment and "quota_horizons" not in enrollment


def test_changed_v2_export_cannot_reuse_prior_root_digest(bound):
    bound.row.update(schema="mastermind.provider_native_capability_registration/v2",
                     provider_enabled=False)
    sign(bound.row)
    owner = bound.publish()
    bound.row["provider_enabled"] = True
    sign(bound.row)
    bound.export.write_text(json.dumps(bound.document))
    from control_plane.codex_provider_realm import ProviderRealmError
    with pytest.raises((source.CapacitySourceContractError, ProviderRealmError)):
        source.acquire_native_registration(owner)
