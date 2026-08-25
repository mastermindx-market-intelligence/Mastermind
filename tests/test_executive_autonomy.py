"""Pure contract tests for the receipt-gated Executive autonomy boundary."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from control_plane import executive_autonomy as autonomy


SHA = "a" * 40
ACCEPTANCE_DIGEST = "1" * 64
GATE_B_DIGEST = "2" * 64
READINESS_DIGEST = "3" * 64
PRIOR_CONTROL_DIGEST = "4" * 64
PRIOR_WORKER_DIGEST = "5" * 64
CONTROL_DIGEST = "6" * 64
WORKER_DIGEST = "7" * 64
CAPABILITY_DIGEST = "8" * 64
PROFILE_DIGEST = "9" * 64
HELPER_DIGEST = "a" * 64
SECURITY_DIGEST = "b" * 64
NOW = datetime(2026, 8, 24, 12, 0, 0, tzinfo=UTC)


def _metadata(**overrides):
    values = {
        "uid": 0,
        "gid": 0,
        "mode": 0o444,
        "nlink": 1,
        "is_regular": True,
        "is_symlink": False,
        "has_acl": False,
    }
    values.update(overrides)
    return autonomy.ReceiptMetadata(**values)


def _receipt(**overrides):
    value = {
        "schema_version": autonomy.RECEIPT_SCHEMA_VERSION,
        "state": "ARMED",
        "release_sha": SHA,
        "acceptance_receipt_sha256": ACCEPTANCE_DIGEST,
        "gate_b_receipt_sha256": GATE_B_DIGEST,
        "provider_readiness_receipt_sha256": READINESS_DIGEST,
        "readiness_observed_at": "2026-08-24T11:50:00Z",
        "credential_expires_at": "2026-08-25T12:00:00Z",
        "readiness_expires_at": "2026-08-24T14:00:00Z",
        "expected_credential_kind": "device-auth",
        "workspace_binding_class": autonomy.WORKSPACE_BINDING_CLASS,
        "prior_control_config_sha256": PRIOR_CONTROL_DIGEST,
        "prior_worker_config_sha256": PRIOR_WORKER_DIGEST,
        "control_config_sha256": CONTROL_DIGEST,
        "worker_config_sha256": WORKER_DIGEST,
        "capability_policy_digest": CAPABILITY_DIGEST,
        "execution_profile_digest": PROFILE_DIGEST,
        "native_helper_grant_digest": HELPER_DIGEST,
        "security_config_digest": SECURITY_DIGEST,
        "transaction_id": "autonomy-deadbeefcafe",
        "observed_at": "2026-08-24T12:00:00Z",
        "tool_version": autonomy.TOOL_VERSION,
        "predicates": {
            "acceptance_passed": True,
            "configs_validated": True,
            "gate_b_passed": True,
            "provider_readiness_passed": True,
            "runtime_quiescent": True,
            "service_uids_quiescent": True,
        },
    }
    value.update(overrides)
    return value


def _expectation(**overrides):
    values = {
        "release_sha": SHA,
        "control_config_sha256": CONTROL_DIGEST,
        "worker_config_sha256": WORKER_DIGEST,
        "provider_readiness_receipt_sha256": READINESS_DIGEST,
        "capability_policy_digest": CAPABILITY_DIGEST,
        "execution_profile_digest": PROFILE_DIGEST,
        "native_helper_grant_digest": HELPER_DIGEST,
        "security_config_digest": SECURITY_DIGEST,
    }
    values.update(overrides)
    return autonomy.AutonomyExpectation(**values)


def test_canonical_digest_is_stable_and_rejects_non_json_values():
    left = {"b": [2, 3], "a": {"x": True}}
    right = {"a": {"x": True}, "b": [2, 3]}
    assert autonomy.canonical_sha256(left) == autonomy.canonical_sha256(right)
    assert len(autonomy.canonical_sha256(left)) == 64

    with pytest.raises(autonomy.AutonomyRefusal) as raised:
        autonomy.canonical_sha256({"bad": float("nan")})
    assert raised.value.code == "non_canonical_json"


def test_exact_armed_receipt_validates_to_closed_binding():
    binding = autonomy.validate_receipt_document(
        _receipt(),
        metadata=_metadata(),
        expected=_expectation(),
        now=NOW,
    )

    assert binding.state == "ARMED"
    assert binding.release_sha == SHA
    assert binding.control_config_sha256 == CONTROL_DIGEST
    assert binding.worker_config_sha256 == WORKER_DIGEST
    assert binding.readiness_expires_at == datetime(
        2026, 8, 24, 14, 0, 0, tzinfo=UTC
    )
    assert binding.expected_credential_kind == "device-auth"


@pytest.mark.parametrize(
    ("metadata", "code"),
    [
        (_metadata(uid=501), "receipt_owner_mismatch"),
        (_metadata(gid=20), "receipt_group_mismatch"),
        (_metadata(mode=0o644), "receipt_mode_mismatch"),
        (_metadata(nlink=2), "receipt_link_count_mismatch"),
        (_metadata(is_regular=False), "receipt_not_regular"),
        (_metadata(is_symlink=True), "receipt_not_regular"),
        (_metadata(has_acl=True), "receipt_acl_unsafe"),
    ],
)
def test_receipt_metadata_is_exact(metadata, code):
    with pytest.raises(autonomy.AutonomyRefusal) as raised:
        autonomy.validate_receipt_document(
            _receipt(), metadata=metadata, expected=_expectation(), now=NOW
        )
    assert raised.value.code == code


@pytest.mark.parametrize(
    ("mutator", "code"),
    [
        (lambda value: value.pop("state"), "receipt_fields_mismatch"),
        (lambda value: value.__setitem__("token", "do-not-store"), "receipt_fields_mismatch"),
        (lambda value: value.__setitem__("schema_version", "v0"), "receipt_schema_mismatch"),
        (lambda value: value.__setitem__("state", "READY"), "receipt_state_invalid"),
        (lambda value: value.__setitem__("release_sha", "a" * 39), "receipt_release_invalid"),
        (lambda value: value.__setitem__("control_config_sha256", "f" * 64), "control_config_digest_mismatch"),
        (lambda value: value.__setitem__("worker_config_sha256", "f" * 64), "worker_config_digest_mismatch"),
        (lambda value: value.__setitem__("provider_readiness_receipt_sha256", "f" * 64), "provider_readiness_digest_mismatch"),
        (lambda value: value.__setitem__("capability_policy_digest", "f" * 64), "capability_policy_digest_mismatch"),
        (lambda value: value.__setitem__("execution_profile_digest", "f" * 64), "execution_profile_digest_mismatch"),
        (lambda value: value.__setitem__("native_helper_grant_digest", "f" * 64), "native_helper_digest_mismatch"),
        (lambda value: value.__setitem__("security_config_digest", "f" * 64), "security_config_digest_mismatch"),
        (lambda value: value.__setitem__("transaction_id", "free-form"), "transaction_id_invalid"),
        (lambda value: value.__setitem__("expected_credential_kind", "operator-copy"), "credential_kind_invalid"),
        (lambda value: value.__setitem__("workspace_binding_class", "personal"), "workspace_binding_mismatch"),
        (lambda value: value["predicates"].__setitem__("extra", True), "receipt_predicates_invalid"),
        (lambda value: value["predicates"].__setitem__("runtime_quiescent", False), "receipt_predicates_failed"),
    ],
)
def test_receipt_schema_and_bindings_fail_closed(mutator, code):
    value = _receipt()
    mutator(value)
    with pytest.raises(autonomy.AutonomyRefusal) as raised:
        autonomy.validate_receipt_document(
            value, metadata=_metadata(), expected=_expectation(), now=NOW
        )
    assert raised.value.code == code


@pytest.mark.parametrize(
    ("field", "value", "code"),
    [
        ("observed_at", "2026-08-24", "receipt_timestamp_malformed"),
        ("observed_at", "2026-08-24T12:00:01Z", "receipt_timestamp_in_future"),
        ("readiness_observed_at", "2026-08-24T12:01:00Z", "readiness_timestamp_order_invalid"),
        ("credential_expires_at", "2026-08-24T13:00:00Z", "readiness_expiry_bounds_invalid"),
        ("readiness_expires_at", "2026-08-24T12:00:00Z", "readiness_expired"),
        ("readiness_expires_at", "2026-08-24T12:29:59Z", "readiness_margin_insufficient"),
    ],
)
def test_time_bounds_are_strict(field, value, code):
    with pytest.raises(autonomy.AutonomyRefusal) as raised:
        autonomy.validate_receipt_document(
            _receipt(**{field: value}),
            metadata=_metadata(),
            expected=_expectation(),
            now=NOW,
        )
    assert raised.value.code == code


def test_read_only_status_can_parse_an_expired_receipt_without_admitting_work():
    binding = autonomy.validate_receipt_document(
        _receipt(readiness_expires_at="2026-08-24T11:59:59Z"),
        metadata=_metadata(),
        expected=_expectation(),
        now=NOW,
        require_current=False,
    )
    assert binding.readiness_expires_at < NOW


def test_disarmed_receipt_can_truthfully_omit_old_authority_evidence():
    value = _receipt(
        state="DISARMED",
        acceptance_receipt_sha256="0" * 64,
        gate_b_receipt_sha256="0" * 64,
        provider_readiness_receipt_sha256="0" * 64,
        readiness_observed_at="2026-08-24T12:00:00Z",
        credential_expires_at="2026-08-24T12:00:00Z",
        readiness_expires_at="2026-08-24T12:00:00Z",
        expected_credential_kind="none",
        workspace_binding_class="none",
        predicates={
            "acceptance_passed": False,
            "configs_validated": True,
            "gate_b_passed": False,
            "provider_readiness_passed": False,
            "runtime_quiescent": False,
            "service_uids_quiescent": True,
        },
    )
    binding = autonomy.validate_receipt_document(
        value,
        metadata=_metadata(),
        expected=_expectation(provider_readiness_receipt_sha256="0" * 64),
        now=NOW,
        require_current=False,
    )
    assert binding.state == "DISARMED"
    assert binding.expected_credential_kind == "none"


def test_receipt_bytes_are_secret_free_by_construction():
    encoded = json.dumps(_receipt(), sort_keys=True).lower()
    for forbidden in (
        "token",
        "cookie",
        "password",
        "prompt",
        "model_output",
        "provider_home",
        "account_id",
        "process_args",
        "http://",
        "https://",
    ):
        assert forbidden not in encoded


def _status(**overrides):
    values = {
        "transaction_present": False,
        "control_armed": True,
        "worker_armed": True,
        "receipt_state": "ARMED",
        "receipt_matches": True,
        "config_drift": False,
        "identity_reconciled": True,
        "service_state": "READY",
        "readiness_expires_at": NOW + timedelta(hours=2),
    }
    values.update(overrides)
    return autonomy.StatusEvidence(**values)


def test_closed_status_happy_paths_and_near_expiry():
    assert autonomy.classify_status(_status(), now=NOW) == "ARMED_READY"
    assert (
        autonomy.classify_status(
            _status(service_state="STOPPED"), now=NOW
        )
        == "ARMED_DEGRADED"
    )
    assert (
        autonomy.classify_status(
            _status(readiness_expires_at=NOW + timedelta(minutes=29)), now=NOW
        )
        == "ARMED_DEGRADED"
    )
    assert (
        autonomy.classify_status(
            _status(
                control_armed=False,
                worker_armed=False,
                receipt_state="DISARMED",
                readiness_expires_at=None,
                service_state="STOPPED",
            ),
            now=NOW,
        )
        == "UNARMED"
    )
    assert (
        autonomy.classify_status(
            _status(
                control_armed=False,
                worker_armed=False,
                receipt_state=None,
                receipt_matches=False,
                readiness_expires_at=None,
                service_state="STOPPED",
            ),
            now=NOW,
        )
        == "UNARMED"
    )


@pytest.mark.parametrize(
    ("evidence", "expected"),
    [
        (
            _status(
                transaction_present=True,
                config_drift=True,
                identity_reconciled=False,
                readiness_expires_at=NOW,
            ),
            "TRANSACTION_INCOMPLETE",
        ),
        (
            _status(
                control_armed=False,
                config_drift=False,
                identity_reconciled=False,
                readiness_expires_at=NOW,
            ),
            "CONFIG_DRIFT",
        ),
        (
            _status(
                config_drift=True,
                identity_reconciled=False,
                readiness_expires_at=NOW,
            ),
            "CONFIG_DRIFT",
        ),
        (
            _status(identity_reconciled=False, readiness_expires_at=NOW),
            "EFFECT_UNKNOWN",
        ),
        (_status(service_state="AMBIGUOUS", readiness_expires_at=NOW), "EFFECT_UNKNOWN"),
        (_status(readiness_expires_at=NOW), "READINESS_EXPIRED"),
    ],
)
def test_status_precedence_never_hides_the_more_unsafe_state(evidence, expected):
    assert autonomy.classify_status(evidence, now=NOW) == expected


@pytest.mark.parametrize(
    "evidence",
    [
        _status(receipt_state=None, receipt_matches=False),
        _status(receipt_state="DISARMED"),
        _status(control_armed=False, worker_armed=True),
        _status(config_drift=True),
    ],
)
def test_armed_config_requires_one_matching_armed_receipt(evidence):
    assert autonomy.classify_status(evidence, now=NOW) == "CONFIG_DRIFT"


@pytest.mark.parametrize(
    ("role", "own_digest"),
    [("control", CONTROL_DIGEST), ("worker", WORKER_DIGEST)],
)
def test_runtime_guard_binds_each_service_to_its_own_config(role, own_digest):
    binding = autonomy.validate_runtime_guard_document(
        _receipt(
            capability_policy_digest=autonomy.CAPABILITY_POLICY_DIGEST,
            execution_profile_digest=autonomy.EXECUTION_PROFILE_DIGEST,
            native_helper_grant_digest=autonomy.NATIVE_HELPER_GRANT_DIGEST,
            security_config_digest=autonomy.SECURITY_CONFIG_DIGEST,
        ),
        metadata=_metadata(),
        role=role,
        own_config_sha256=own_digest,
        release_sha=SHA,
        now=NOW,
    )
    assert binding.state == "ARMED"


@pytest.mark.parametrize("role", ["control", "worker"])
def test_runtime_guard_refuses_wrong_own_config_before_work(role):
    with pytest.raises(autonomy.AutonomyRefusal) as raised:
        autonomy.validate_runtime_guard_document(
            _receipt(
                capability_policy_digest=autonomy.CAPABILITY_POLICY_DIGEST,
                execution_profile_digest=autonomy.EXECUTION_PROFILE_DIGEST,
                native_helper_grant_digest=autonomy.NATIVE_HELPER_GRANT_DIGEST,
                security_config_digest=autonomy.SECURITY_CONFIG_DIGEST,
            ),
            metadata=_metadata(),
            role=role,
            own_config_sha256="f" * 64,
            release_sha=SHA,
            now=NOW,
        )
    expected = (
        "control_config_digest_mismatch"
        if role == "control"
        else "worker_config_digest_mismatch"
    )
    assert raised.value.code == expected


def test_runtime_guard_never_accepts_a_disarmed_receipt():
    value = _receipt(
        state="DISARMED",
        acceptance_receipt_sha256="0" * 64,
        gate_b_receipt_sha256="0" * 64,
        provider_readiness_receipt_sha256="0" * 64,
        readiness_observed_at="2026-08-24T12:00:00Z",
        credential_expires_at="2026-08-24T12:00:00Z",
        readiness_expires_at="2026-08-24T12:00:00Z",
        expected_credential_kind="none",
        workspace_binding_class="none",
        predicates={
            "acceptance_passed": False,
            "configs_validated": True,
            "gate_b_passed": False,
            "provider_readiness_passed": False,
            "runtime_quiescent": False,
            "service_uids_quiescent": True,
        },
        capability_policy_digest=autonomy.CAPABILITY_POLICY_DIGEST,
        execution_profile_digest=autonomy.EXECUTION_PROFILE_DIGEST,
        native_helper_grant_digest=autonomy.NATIVE_HELPER_GRANT_DIGEST,
        security_config_digest=autonomy.SECURITY_CONFIG_DIGEST,
    )
    with pytest.raises(autonomy.AutonomyRefusal) as raised:
        autonomy.validate_runtime_guard_document(
            value,
            metadata=_metadata(),
            role="control",
            own_config_sha256=CONTROL_DIGEST,
            release_sha=SHA,
            now=NOW,
        )
    assert raised.value.code == "receipt_not_armed"


def test_credential_rotation_interlock_requires_matching_disarmed_receipt():
    value = _receipt(
        state="DISARMED",
        acceptance_receipt_sha256="0" * 64,
        gate_b_receipt_sha256="0" * 64,
        provider_readiness_receipt_sha256="0" * 64,
        readiness_observed_at="2026-08-24T12:00:00Z",
        credential_expires_at="2026-08-24T12:00:00Z",
        readiness_expires_at="2026-08-24T12:00:00Z",
        expected_credential_kind="none",
        workspace_binding_class="none",
        predicates={
            "acceptance_passed": False,
            "configs_validated": True,
            "gate_b_passed": False,
            "provider_readiness_passed": False,
            "runtime_quiescent": False,
            "service_uids_quiescent": True,
        },
        capability_policy_digest=autonomy.CAPABILITY_POLICY_DIGEST,
        execution_profile_digest=autonomy.EXECUTION_PROFILE_DIGEST,
        native_helper_grant_digest=autonomy.NATIVE_HELPER_GRANT_DIGEST,
        security_config_digest=autonomy.SECURITY_CONFIG_DIGEST,
    )
    binding = autonomy.validate_disarmed_interlock_document(
        value,
        metadata=_metadata(),
        control_config_sha256=CONTROL_DIGEST,
        worker_config_sha256=WORKER_DIGEST,
        now=NOW,
    )
    assert binding.state == "DISARMED"

    with pytest.raises(autonomy.AutonomyRefusal) as raised:
        autonomy.validate_disarmed_interlock_document(
            value,
            metadata=_metadata(),
            control_config_sha256="f" * 64,
            worker_config_sha256=WORKER_DIGEST,
            now=NOW,
        )
    assert raised.value.code == "control_config_digest_mismatch"


def test_credential_rotation_interlock_rejects_armed_receipt():
    with pytest.raises(autonomy.AutonomyRefusal) as raised:
        autonomy.validate_disarmed_interlock_document(
            _receipt(
                capability_policy_digest=autonomy.CAPABILITY_POLICY_DIGEST,
                execution_profile_digest=autonomy.EXECUTION_PROFILE_DIGEST,
                native_helper_grant_digest=autonomy.NATIVE_HELPER_GRANT_DIGEST,
                security_config_digest=autonomy.SECURITY_CONFIG_DIGEST,
            ),
            metadata=_metadata(),
            control_config_sha256=CONTROL_DIGEST,
            worker_config_sha256=WORKER_DIGEST,
            now=NOW,
        )
    assert raised.value.code == "receipt_not_disarmed"
