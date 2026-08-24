"""Pure contract tests for the MAS-115 fixed Multilogin port policy."""
from __future__ import annotations

import copy
import json

import pytest

from integrations.chairman_surfaces import mas115_multilogin_port_policy as policy


PROFILE_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
FOLDER_ID = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"


def _metas(*, ports=None, mode="mask", auto=True):
    fingerprint = {} if ports is None else {"ports": ports}
    return {
        "status": {
            "error_code": "",
            "http_code": 200,
            "message": "List of profiles metadata",
        },
        "data": {
            "profiles": [{
                "id": PROFILE_ID,
                "folder_id": FOLDER_ID,
                "browser_type": "mimic",
                "in_use_by": "",
                "is_auto_update": auto,
                "parameters": {
                    "flags": {"ports_masking": mode},
                    "fingerprint": fingerprint,
                    "storage": {"is_local": False, "save_service_worker": False},
                },
                "last_update_at": "before",
                "last_updated_by": "synthetic",
            }]
        },
    }


def test_default_masked_classifies_and_builds_only_exact_body():
    """Catches accepting the default without constructing the one allowed delta."""
    snapshot = policy.classify_profile_metas(
        _metas(), profile_id=PROFILE_ID, folder_id=FOLDER_ID,
    )
    assert snapshot.state == policy.DEFAULT_MASKED
    assert snapshot.auto_update_core is True
    assert policy.build_partial_update_body(PROFILE_ID, snapshot) == {
        "profile_id": PROFILE_ID,
        "auto_update_core": True,
        "parameters": {
            "flags": {"ports_masking": "mask"},
            "fingerprint": {"ports": [65535]},
        },
    }


def test_exact_configured_is_idempotent_and_not_mutable():
    """Catches issuing an unnecessary second update for an exact profile."""
    snapshot = policy.classify_profile_metas(
        _metas(ports=[65535]), profile_id=PROFILE_ID, folder_id=FOLDER_ID,
    )
    assert snapshot.state == policy.EXACT_CONFIGURED
    with pytest.raises(policy.PortPolicyRefusal) as raised:
        policy.build_partial_update_body(PROFILE_ID, snapshot)
    assert raised.value.code == policy.UNSUPPORTED_PORT_STATE


def _mutated_metas(mutation: str):
    payload = _metas()
    profile = payload["data"]["profiles"][0]
    if mutation == "wrong-envelope":
        payload["extra"] = None
    elif mutation == "wrong-message":
        payload["status"]["message"] = "success"
    elif mutation == "two-profiles":
        payload["data"]["profiles"].append(copy.deepcopy(profile))
    elif mutation == "wrong-profile":
        profile["id"] = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
    elif mutation == "wrong-folder":
        profile["folder_id"] = "dddddddd-dddd-4ddd-8ddd-dddddddddddd"
    elif mutation == "wrong-browser":
        profile["browser_type"] = "stealthfox"
    elif mutation == "owned":
        profile["in_use_by"] = "someone"
    elif mutation == "missing-auto":
        profile.pop("is_auto_update")
    elif mutation == "integer-auto":
        profile["is_auto_update"] = 1
    elif mutation == "missing-parameters":
        profile.pop("parameters")
    elif mutation == "missing-flags":
        profile["parameters"].pop("flags")
    elif mutation == "missing-fingerprint":
        profile["parameters"].pop("fingerprint")
    elif mutation == "boolean-port":
        profile["parameters"]["fingerprint"]["ports"] = [True]
    elif mutation == "string-port":
        profile["parameters"]["fingerprint"]["ports"] = ["65535"]
    elif mutation == "duplicate-port":
        profile["parameters"]["fingerprint"]["ports"] = [65535, 65535]
    elif mutation == "extra-port":
        profile["parameters"]["fingerprint"]["ports"] = [65535, 4444]
    elif mutation in {"natural", "custom", "unknown-mode"}:
        profile["parameters"]["flags"]["ports_masking"] = mutation
    else:
        raise AssertionError(f"unknown test mutation: {mutation}")
    return payload


@pytest.mark.parametrize(
    "mutation",
    (
        "wrong-envelope", "wrong-message", "two-profiles", "wrong-profile",
        "wrong-folder", "wrong-browser", "owned", "missing-auto", "integer-auto",
        "missing-parameters", "missing-flags", "missing-fingerprint",
        "boolean-port", "string-port", "duplicate-port", "extra-port",
        "natural", "custom", "unknown-mode",
    ),
)
def test_profile_metas_drift_never_classifies_as_mutable(mutation):
    """Catches treating any malformed, foreign, busy, or widened state as mutable."""
    with pytest.raises(policy.PortPolicyRefusal):
        policy.classify_profile_metas(
            _mutated_metas(mutation), profile_id=PROFILE_ID, folder_id=FOLDER_ID,
        )


def test_preservation_digest_ignores_only_target_and_vendor_audit_fields():
    """Catches missing non-target drift while permitting target/audit changes."""
    before = policy.classify_profile_metas(
        _metas(), profile_id=PROFILE_ID, folder_id=FOLDER_ID,
    )
    after_payload = _metas(ports=[65535])
    row = after_payload["data"]["profiles"][0]
    row["last_update_at"] = "after"
    row["last_updated_by"] = "vendor-user"
    after = policy.classify_profile_metas(
        after_payload, profile_id=PROFILE_ID, folder_id=FOLDER_ID,
    )
    assert before.preservation_digest == after.preservation_digest
    row["parameters"]["storage"]["save_service_worker"] = True
    drifted = policy.classify_profile_metas(
        after_payload, profile_id=PROFILE_ID, folder_id=FOLDER_ID,
    )
    assert drifted.preservation_digest != before.preservation_digest


@pytest.mark.parametrize(
    ("code", "verdict"),
    (
        ("CONFIGURED", "PASS"),
        ("ALREADY_CONFIGURED", "PASS"),
        ("CONFIGURED_AFTER_RECONCILIATION", "PASS"),
        ("EFFECT_UNKNOWN", "HOLD"),
        ("PRESERVATION_DRIFT", "HOLD"),
        ("AUTH_EXPIRED_NO_PROOF", "REFUSED"),
        ("REJECTED_NO_PROOF", "REFUSED"),
        ("UNSUPPORTED_PORT_STATE", "REFUSED"),
        ("VENDOR_ERROR", "REFUSED"),
    ),
)
def test_configuration_receipt_is_closed_and_redacted(code, verdict):
    """Catches receipt schema drift or leakage-prone caller-controlled detail."""
    receipt = policy.configuration_receipt(
        code,
        updated=code == "CONFIGURED",
        reconciled=code == "CONFIGURED_AFTER_RECONCILIATION",
        preservation_unchanged=verdict == "PASS",
        auto_update_unchanged=verdict == "PASS",
        exact_profile_stopped=True,
    )
    assert set(receipt) == {"schema", "verdict", "code", "updated", "reconciled", "predicates"}
    assert set(receipt["predicates"]) == {
        "preservation_unchanged", "auto_update_unchanged", "exact_profile_stopped",
    }
    assert receipt["verdict"] == verdict
    serialized = json.dumps(receipt, sort_keys=True)
    for forbidden in (
        "://", PROFILE_ID, FOLDER_ID, "profile-name", "private-note",
        "proxy-password", "synthetic-credential",
    ):
        assert forbidden not in serialized


def test_configuration_receipt_rejects_unknown_code_and_non_boolean_predicates():
    """Catches arbitrary receipt codes and truthy values entering evidence."""
    with pytest.raises(ValueError, match="unknown configuration result"):
        policy.configuration_receipt(
            "UNKNOWN", updated=False, reconciled=False,
            preservation_unchanged=False, auto_update_unchanged=False,
            exact_profile_stopped=False,
        )
    with pytest.raises(ValueError, match="boolean"):
        policy.configuration_receipt(
            "CONFIGURED", updated=1, reconciled=False,
            preservation_unchanged=True, auto_update_unchanged=True,
            exact_profile_stopped=True,
        )
