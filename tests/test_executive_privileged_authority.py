"""RED/GREEN tests for the immutable Job-bound readiness binding contract.

This substep (Task 4A) covers only Steps 1-2 of Task 4: the strict external
request contract, the logical family key and its ``pvrf-`` family aggregate
ID, the complete first-admission binding and its ``pvr-`` operation ID, and
the shared canonical-JSON/identifier/hash validators. No Runtime/Event
mutation, broker call, or controller logic is exercised here.
"""
from __future__ import annotations

import dataclasses
import hashlib
import inspect
import json
import math
import pathlib
import re

import pytest

from control_plane import executive_privileged_authority as epa


VALID_REQUEST = {
    "job_id": "JOB-001",
    "attempt_id": "ATT-" + "a" * 32,
    "fence_generation": 1,
}

VALID_BOOT_ID = "6f9d2fbc-6d31-4ebe-9e1d-a0b21d31eedb"
VALID_RELEASE_SHA = "a" * 40
VALID_POLICY_HASH = "b" * 64
VALID_GRANT_DIGEST = "c" * 64


def _valid_binding_kwargs(**overrides: object) -> dict[str, object]:
    kwargs: dict[str, object] = {
        "job_id": "JOB-001",
        "attempt_id": "ATT-" + "a" * 32,
        "worker_id": "codex-01",
        "quota_class": "codex-native",
        "fence_generation": 1,
        "authority_policy_hash": VALID_POLICY_HASH,
        "effective_grant_digest": None,
        "release_sha": VALID_RELEASE_SHA,
        "boot_id": VALID_BOOT_ID,
        "slot_id": "codex-01",
    }
    kwargs.update(overrides)
    return kwargs


# ---------------------------------------------------------------------------
# Strict external request contract
# ---------------------------------------------------------------------------


def test_request_accepts_exact_three_fields():
    request = epa.validate_readiness_request(VALID_REQUEST)
    assert request.job_id == "JOB-001"
    assert request.attempt_id == VALID_REQUEST["attempt_id"]
    assert request.fence_generation == 1


def test_request_rejects_missing_field():
    raw = dict(VALID_REQUEST)
    del raw["fence_generation"]
    with pytest.raises(epa.PrivilegedReadinessError):
        epa.validate_readiness_request(raw)


def test_request_rejects_extra_field():
    raw = dict(VALID_REQUEST, extra="nope")
    with pytest.raises(epa.PrivilegedReadinessError):
        epa.validate_readiness_request(raw)


@pytest.mark.parametrize(
    "forbidden_field",
    [
        "action",
        "worker",
        "worker_id",
        "slot",
        "slot_id",
        "host",
        "host_id",
        "release",
        "release_sha",
        "boot",
        "boot_id",
        "request_id",
        "executable",
        "path",
        "credential",
        "token",
        "retry",
        "force",
        "secret",
    ],
)
def test_request_rejects_every_caller_selected_forbidden_field(forbidden_field):
    raw = dict(VALID_REQUEST, **{forbidden_field: "x"})
    with pytest.raises(epa.PrivilegedReadinessError):
        epa.validate_readiness_request(raw)


def test_request_rejects_non_mapping():
    with pytest.raises(epa.PrivilegedReadinessError):
        epa.validate_readiness_request(["job_id", "attempt_id", "fence_generation"])  # type: ignore[arg-type]


def test_request_keys_and_schema_strings_are_pinned_literals():
    assert epa.REQUEST_KEYS == frozenset({"job_id", "attempt_id", "fence_generation"})
    assert epa.FAMILY_KEY_SCHEMA == "mastermind.executive_privileged_readiness_family_key/v1"
    assert epa.BINDING_SCHEMA == "mastermind.executive_privileged_readiness_binding/v1"
    assert epa.RESULT_SCHEMA == "mastermind.executive_privileged_readiness_result/v1"


# ---------------------------------------------------------------------------
# fence_generation type/range
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad_fence", [True, False, "1", 1.0, 0, -1, -100])
def test_fence_generation_refuses_bool_string_float_zero_negative(bad_fence):
    raw = dict(VALID_REQUEST, fence_generation=bad_fence)
    with pytest.raises(epa.PrivilegedReadinessError):
        epa.validate_readiness_request(raw)


def test_fence_generation_accepts_positive_integer():
    raw = dict(VALID_REQUEST, fence_generation=42)
    request = epa.validate_readiness_request(raw)
    assert request.fence_generation == 42


# ---------------------------------------------------------------------------
# Fixed action and observation scope
# ---------------------------------------------------------------------------


def test_fixed_action_constant():
    assert epa.FIXED_ACTION == "executive.worker_auth.verify_only"


def test_family_and_operation_id_prefixes_are_pinned_literals():
    assert epa.FAMILY_ID_PREFIX == "pvrf-"
    assert epa.OPERATION_ID_PREFIX == "pvr-"


def test_observation_scope_constant_has_no_ready_assertion():
    assert epa.OBSERVATION_SCOPE == "LOGIN_STATUS_ONLY_NO_READY_ASSERTION"


def test_module_contains_no_bare_ready_vocabulary():
    source = inspect.getsource(epa)
    for line in source.splitlines():
        if "READY" not in line:
            continue
        assert "NO_READY_ASSERTION" in line or "already-assigned" in line.lower() or line.strip().startswith("#") or line.strip().startswith('"""') or "no controller" in line.lower(), (
            f"unexpected bare READY vocabulary: {line!r}"
        )


# ---------------------------------------------------------------------------
# Canonical JSON bytes
# ---------------------------------------------------------------------------


def test_canonical_json_bytes_sorted_compact_utf8():
    payload = {"b": 1, "a": "x", "c": [1, 2]}
    encoded = epa.canonical_json_bytes(payload)
    assert encoded == b'{"a":"x","b":1,"c":[1,2]}'
    assert isinstance(encoded, bytes)


def test_canonical_json_bytes_rejects_nan():
    with pytest.raises(ValueError):
        epa.canonical_json_bytes({"x": math.nan})


# ---------------------------------------------------------------------------
# Logical family key and family aggregate ID (pvrf-...)
# ---------------------------------------------------------------------------


def test_family_key_canonical_dict_has_exact_keys():
    key = epa.ReadinessFamilyKey(job_id="JOB-001", attempt_id="ATT-" + "a" * 32, fence_generation=1)
    payload = key.to_canonical_dict()
    assert set(payload) == {"schema_version", "action", "job_id", "attempt_id", "fence_generation"}
    assert payload["action"] == epa.FIXED_ACTION
    assert payload["schema_version"] == epa.FAMILY_KEY_SCHEMA


def test_family_key_constructor_refuses_action_override():
    with pytest.raises(epa.PrivilegedReadinessError):
        epa.ReadinessFamilyKey(
            job_id="JOB-001",
            attempt_id="ATT-" + "a" * 32,
            fence_generation=1,
            action="executive.worker_auth.login",
        )


def test_family_id_format_and_stability():
    key = epa.ReadinessFamilyKey(job_id="JOB-001", attempt_id="ATT-" + "a" * 32, fence_generation=1)
    first = key.family_id
    second = epa.ReadinessFamilyKey(job_id="JOB-001", attempt_id="ATT-" + "a" * 32, fence_generation=1).family_id
    assert first == second
    assert first.startswith(epa.FAMILY_ID_PREFIX)
    hex_part = first[len(epa.FAMILY_ID_PREFIX) :]
    assert len(hex_part) == 48
    assert all(c in "0123456789abcdef" for c in hex_part)


def test_family_id_changes_with_fence_generation():
    base = epa.ReadinessFamilyKey(job_id="JOB-001", attempt_id="ATT-" + "a" * 32, fence_generation=1)
    other = epa.ReadinessFamilyKey(job_id="JOB-001", attempt_id="ATT-" + "a" * 32, fence_generation=2)
    assert base.family_id != other.family_id


def test_family_id_changes_with_job_or_attempt():
    base = epa.ReadinessFamilyKey(job_id="JOB-001", attempt_id="ATT-" + "a" * 32, fence_generation=1)
    other_job = epa.ReadinessFamilyKey(job_id="JOB-002", attempt_id="ATT-" + "a" * 32, fence_generation=1)
    other_attempt = epa.ReadinessFamilyKey(job_id="JOB-001", attempt_id="ATT-" + "b" * 32, fence_generation=1)
    assert base.family_id not in (other_job.family_id, other_attempt.family_id)


def test_family_key_from_request_matches_manual_key():
    request = epa.validate_readiness_request(VALID_REQUEST)
    derived = epa.family_key_from_request(request)
    manual = epa.ReadinessFamilyKey(
        job_id=request.job_id, attempt_id=request.attempt_id, fence_generation=request.fence_generation
    )
    assert derived.family_id == manual.family_id


def test_family_key_reproducible_only_from_its_own_inputs():
    key_a = epa.ReadinessFamilyKey(job_id="JOB-001", attempt_id="ATT-" + "a" * 32, fence_generation=1)
    key_b = epa.ReadinessFamilyKey(job_id="JOB-001", attempt_id="ATT-" + "a" * 32, fence_generation=1)
    assert key_a.to_canonical_dict() == key_b.to_canonical_dict()
    assert json.loads(epa.canonical_json_bytes(key_a.to_canonical_dict())) == key_a.to_canonical_dict()


# ---------------------------------------------------------------------------
# Boot identity
# ---------------------------------------------------------------------------


def test_boot_id_accepts_canonical_uuid_text():
    assert epa.validate_boot_id(VALID_BOOT_ID) == VALID_BOOT_ID


@pytest.mark.parametrize(
    "bad_boot_id",
    [
        "",
        "   ",
        "not-a-uuid",
        "adapter-1234",
        "adapter-0",
        "12345678-1234-1234-1234",
        None,
        123,
        "00000000-0000-0000-0000-000000000000",
    ],
)
def test_boot_id_rejects_empty_malformed_and_adapter_fallback(bad_boot_id):
    with pytest.raises(epa.PrivilegedReadinessError):
        epa.validate_boot_id(bad_boot_id)


def test_boot_id_accepts_real_macos_uppercase_shape_and_canonicalizes_lowercase():
    upper = "6F9D2FBC-6D31-4EBE-9E1D-A0B21D31EEDB"
    assert epa.validate_boot_id(upper) == VALID_BOOT_ID


def test_boot_id_upper_and_lower_spellings_are_the_same_identity():
    upper = VALID_BOOT_ID.upper()
    assert epa.validate_boot_id(upper) == epa.validate_boot_id(VALID_BOOT_ID) == VALID_BOOT_ID


# ---------------------------------------------------------------------------
# Hashes and release SHA
# ---------------------------------------------------------------------------


def test_release_sha_accepts_lowercase_40_hex():
    assert epa.validate_release_sha(VALID_RELEASE_SHA) == VALID_RELEASE_SHA


@pytest.mark.parametrize("bad_release_sha", ["A" * 40, "a" * 39, "a" * 41, "g" * 40, "", None])
def test_release_sha_rejects_wrong_length_or_case_or_charset(bad_release_sha):
    with pytest.raises(epa.PrivilegedReadinessError):
        epa.validate_release_sha(bad_release_sha)


def test_sha256_hex_accepts_lowercase_64_hex():
    assert epa.validate_sha256_hex(VALID_POLICY_HASH, "authority_policy_hash") == VALID_POLICY_HASH


@pytest.mark.parametrize("bad_hash", ["A" * 64, "a" * 63, "a" * 65, "g" * 64, "", None])
def test_sha256_hex_rejects_wrong_length_or_case_or_charset(bad_hash):
    with pytest.raises(epa.PrivilegedReadinessError):
        epa.validate_sha256_hex(bad_hash, "authority_policy_hash")


def test_effective_grant_digest_accepts_none_or_sha256_hex():
    assert epa.validate_effective_grant_digest(None) is None
    assert epa.validate_effective_grant_digest(VALID_GRANT_DIGEST) == VALID_GRANT_DIGEST


def test_effective_grant_digest_rejects_malformed():
    with pytest.raises(epa.PrivilegedReadinessError):
        epa.validate_effective_grant_digest("not-a-hash")


# ---------------------------------------------------------------------------
# First-admission binding and operation ID (pvr-...)
# ---------------------------------------------------------------------------


def test_binding_canonical_dict_has_exact_keys():
    binding = epa.ReadinessBinding(**_valid_binding_kwargs())
    payload = binding.to_canonical_dict()
    assert set(payload) == {
        "schema_version",
        "action",
        "job_id",
        "attempt_id",
        "worker_id",
        "quota_class",
        "fence_generation",
        "authority_policy_hash",
        "effective_grant_digest",
        "release_sha",
        "boot_id",
        "slot_id",
    }
    assert payload["schema_version"] == epa.BINDING_SCHEMA
    assert payload["action"] == epa.FIXED_ACTION
    assert payload["effective_grant_digest"] is None
    assert set(payload) == epa.BINDING_CANONICAL_KEYS


def test_binding_constructor_refuses_action_override():
    with pytest.raises(epa.PrivilegedReadinessError):
        epa.ReadinessBinding(**_valid_binding_kwargs(action="executive.worker_auth.login"))


def test_binding_constructor_refuses_schema_version_override():
    with pytest.raises(epa.PrivilegedReadinessError):
        epa.ReadinessBinding(**_valid_binding_kwargs(schema_version="other/v2"))


def test_binding_serializes_only_secret_free_fields():
    binding = epa.ReadinessBinding(**_valid_binding_kwargs())
    payload = binding.to_canonical_dict()
    forbidden_terms = ("token", "secret", "password", "credential_material")
    for key, value in payload.items():
        haystack = f"{key}={value}".lower()
        for term in forbidden_terms:
            assert term not in haystack


def test_binding_constructor_requires_slot_id_equal_worker_id():
    with pytest.raises(epa.PrivilegedReadinessError):
        epa.ReadinessBinding(**_valid_binding_kwargs(slot_id="codex-02"))


def test_binding_constructor_rejects_bad_release_sha():
    with pytest.raises(epa.PrivilegedReadinessError):
        epa.ReadinessBinding(**_valid_binding_kwargs(release_sha="not-hex"))


def test_binding_constructor_rejects_bad_boot_id():
    with pytest.raises(epa.PrivilegedReadinessError):
        epa.ReadinessBinding(**_valid_binding_kwargs(boot_id="adapter-42"))


def test_binding_constructor_rejects_bad_policy_hash():
    with pytest.raises(epa.PrivilegedReadinessError):
        epa.ReadinessBinding(**_valid_binding_kwargs(authority_policy_hash="short"))


def test_operation_id_format_and_stability():
    binding_a = epa.ReadinessBinding(**_valid_binding_kwargs())
    binding_b = epa.ReadinessBinding(**_valid_binding_kwargs())
    assert binding_a.operation_id == binding_b.operation_id
    assert binding_a.operation_id.startswith(epa.OPERATION_ID_PREFIX)
    hex_part = binding_a.operation_id[len(epa.OPERATION_ID_PREFIX) :]
    assert len(hex_part) == 48
    assert all(c in "0123456789abcdef" for c in hex_part)


def test_operation_id_sensitive_to_release_boot_and_policy():
    base = epa.ReadinessBinding(**_valid_binding_kwargs())
    other_release = epa.ReadinessBinding(**_valid_binding_kwargs(release_sha="d" * 40))
    other_boot = epa.ReadinessBinding(
        **_valid_binding_kwargs(boot_id="0f9d2fbc-6d31-4ebe-9e1d-a0b21d31eedb")
    )
    other_policy = epa.ReadinessBinding(**_valid_binding_kwargs(authority_policy_hash="e" * 64))
    other_grant = epa.ReadinessBinding(**_valid_binding_kwargs(effective_grant_digest=VALID_GRANT_DIGEST))
    ids = {
        base.operation_id,
        other_release.operation_id,
        other_boot.operation_id,
        other_policy.operation_id,
        other_grant.operation_id,
    }
    assert len(ids) == 5


def test_operation_id_identical_for_upper_and_lower_boot_id_spelling():
    lower = epa.ReadinessBinding(**_valid_binding_kwargs(boot_id=VALID_BOOT_ID))
    upper = epa.ReadinessBinding(**_valid_binding_kwargs(boot_id=VALID_BOOT_ID.upper()))
    assert lower.operation_id == upper.operation_id
    assert lower.to_canonical_dict() == upper.to_canonical_dict()
    assert upper.boot_id == VALID_BOOT_ID


def test_family_id_unaffected_by_release_boot_policy_movement():
    key = epa.ReadinessFamilyKey(job_id="JOB-001", attempt_id="ATT-" + "a" * 32, fence_generation=1)
    base = epa.ReadinessBinding(**_valid_binding_kwargs())
    other_release = epa.ReadinessBinding(**_valid_binding_kwargs(release_sha="d" * 40))
    assert base.operation_id != other_release.operation_id
    assert key.family_id == epa.ReadinessFamilyKey(
        job_id="JOB-001", attempt_id="ATT-" + "a" * 32, fence_generation=1
    ).family_id


def test_family_id_known_answer_vector():
    key = epa.ReadinessFamilyKey(job_id="JOB-001", attempt_id="ATT-" + "a" * 32, fence_generation=1)
    assert key.family_id == "pvrf-bedfa0cbb1c9d169c73d632da05cddd59b5de0ea6adfc8ea"


def test_operation_id_known_answer_vector():
    binding = epa.ReadinessBinding(**_valid_binding_kwargs())
    assert binding.operation_id == "pvr-5d43b77045ea6be5f77d1c547792f4c067f758dddf01e07a"


def test_family_id_known_answer_vector_breaks_if_hash_algorithm_changes():
    key = epa.ReadinessFamilyKey(job_id="JOB-001", attempt_id="ATT-" + "a" * 32, fence_generation=1)
    payload = key.to_canonical_dict()
    sha256_digest = hashlib.sha256(epa.canonical_json_bytes(payload)).hexdigest()
    sha512_digest = hashlib.sha512(epa.canonical_json_bytes(payload)).hexdigest()
    assert key.family_id == f"{epa.FAMILY_ID_PREFIX}{sha256_digest[:48]}"
    assert key.family_id != f"{epa.FAMILY_ID_PREFIX}{sha512_digest[:48]}"


def test_operation_id_known_answer_vector_breaks_if_encoding_is_noncanonical():
    binding = epa.ReadinessBinding(**_valid_binding_kwargs())
    payload = binding.to_canonical_dict()
    canonical_digest = hashlib.sha256(epa.canonical_json_bytes(payload)).hexdigest()
    noncanonical_digest = hashlib.sha256(repr(payload).encode("utf-8")).hexdigest()
    assert binding.operation_id == f"{epa.OPERATION_ID_PREFIX}{canonical_digest[:48]}"
    assert binding.operation_id != f"{epa.OPERATION_ID_PREFIX}{noncanonical_digest[:48]}"


def test_family_and_operation_ids_differ_and_separate_namespaces():
    key = epa.ReadinessFamilyKey(job_id="JOB-001", attempt_id="ATT-" + "a" * 32, fence_generation=1)
    binding = epa.ReadinessBinding(**_valid_binding_kwargs())
    assert key.family_id != binding.operation_id
    assert key.family_id.startswith(epa.FAMILY_ID_PREFIX)
    assert binding.operation_id.startswith(epa.OPERATION_ID_PREFIX)
    assert not binding.operation_id.startswith(epa.FAMILY_ID_PREFIX)
    assert not key.family_id.startswith(epa.OPERATION_ID_PREFIX)


# ---------------------------------------------------------------------------
# Bounded safe identifiers
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad_worker_id", ["", "Codex-01", "codex_01", "codex 01", "../etc", "co" + "x" * 100])
def test_worker_id_rejects_unsafe_values(bad_worker_id):
    with pytest.raises(epa.PrivilegedReadinessError):
        epa.ReadinessBinding(**_valid_binding_kwargs(worker_id=bad_worker_id, slot_id=bad_worker_id))


@pytest.mark.parametrize("bad_job_id", ["", "job-001", "JOB_001", "JOB-", "JOB-abc"])
def test_job_id_rejects_malformed_values(bad_job_id):
    raw = dict(VALID_REQUEST, job_id=bad_job_id)
    with pytest.raises(epa.PrivilegedReadinessError):
        epa.validate_readiness_request(raw)


@pytest.mark.parametrize(
    "bad_job_id",
    [
        pytest.param("JOB-000", id="zero_three_digit"),
        pytest.param("JOB-1", id="one_digit"),
        pytest.param("JOB-01", id="two_digit_leading_zero"),
        pytest.param("JOB-0001", id="four_digit_leading_zero"),
        pytest.param("JOB-0100", id="four_digit_leading_zero_alt"),
        pytest.param("JOB-" + "1" * 19, id="nineteen_digits_too_long"),
        pytest.param("JOB-" + "1" * 10000, id="unbounded_ten_thousand_digits"),
    ],
)
def test_job_id_rejects_aliases_and_unbounded_shapes(bad_job_id):
    with pytest.raises(epa.PrivilegedReadinessError):
        epa.validate_job_id(bad_job_id)


@pytest.mark.parametrize(
    "good_job_id",
    ["JOB-001", "JOB-999", "JOB-1000", "JOB-9999", "JOB-1" + "2" * 17],
)
def test_job_id_accepts_canonical_runtime_shapes(good_job_id):
    assert epa.validate_job_id(good_job_id) == good_job_id


@pytest.mark.parametrize("bad_attempt_id", ["", "att-" + "a" * 32, "ATT-" + "g" * 32, "ATT-short"])
def test_attempt_id_rejects_malformed_values(bad_attempt_id):
    raw = dict(VALID_REQUEST, attempt_id=bad_attempt_id)
    with pytest.raises(epa.PrivilegedReadinessError):
        epa.validate_readiness_request(raw)


# ---------------------------------------------------------------------------
# Frozen dataclasses
# ---------------------------------------------------------------------------


def test_readiness_request_is_frozen():
    request = epa.validate_readiness_request(VALID_REQUEST)
    with pytest.raises(dataclasses.FrozenInstanceError):
        request.job_id = "JOB-002"  # type: ignore[misc]


def test_family_key_is_frozen():
    key = epa.ReadinessFamilyKey(job_id="JOB-001", attempt_id="ATT-" + "a" * 32, fence_generation=1)
    with pytest.raises(dataclasses.FrozenInstanceError):
        key.fence_generation = 2  # type: ignore[misc]


def test_binding_is_frozen():
    binding = epa.ReadinessBinding(**_valid_binding_kwargs())
    with pytest.raises(dataclasses.FrozenInstanceError):
        binding.worker_id = "codex-02"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Task 4B: pure result-projection contract (design sections 8, 10 and 11).
#
# These exercise only the deterministic result/phase value objects that live
# beside the request/binding primitives. No Runtime transaction, Event append,
# broker socket, or controller admission is touched here; the Runtime/Event
# owner seam remains held behind its source-custody reconciliation.
# ---------------------------------------------------------------------------


VALID_RECEIPT = {
    "schema": "mastermind.privileged_action_receipt/v1",
    "request_id": "pvr-" + "0" * 48,
    "action": epa.FIXED_ACTION,
    "status": "TERMINAL",
}


def _terminal_kwargs(**overrides: object) -> dict[str, object]:
    kwargs: dict[str, object] = {
        "family_id": epa.FAMILY_ID_PREFIX + "1" * 48,
        "operation_id": epa.OPERATION_ID_PREFIX + "2" * 48,
        "state": epa.ReadinessResultState.TERMINAL,
        "replayed": False,
        "observed_at_ms": 1800000000000,
        "evidence_currency": epa.ReadinessEvidenceCurrency.CURRENT,
        "binding": epa.ReadinessBinding(**_valid_binding_kwargs()),
        "receipt": VALID_RECEIPT,
        "reason_origin": None,
        "reason_code": None,
    }
    kwargs.update(overrides)
    return kwargs


def test_result_state_enum_is_exactly_three_closed_values():
    assert {item.value for item in epa.ReadinessResultState} == {
        "TERMINAL",
        "REFUSED",
        "EFFECT_UNKNOWN",
    }


def test_no_result_state_or_currency_value_can_assert_ready():
    vocabulary = {item.value for item in epa.ReadinessResultState}
    vocabulary |= {item.value for item in epa.ReadinessEvidenceCurrency}
    vocabulary |= {item.value for item in epa.ReadinessEventPhase}
    assert not any("READY" in value for value in vocabulary)


def test_evidence_currency_enum_is_exactly_two_closed_values():
    assert {item.value for item in epa.ReadinessEvidenceCurrency} == {
        "CURRENT",
        "HISTORICAL",
    }


def test_event_phase_enum_is_the_six_reviewed_durable_phases():
    assert {item.value for item in epa.ReadinessEventPhase} == {
        "PRIVILEGED_READINESS_INTENT",
        "PRIVILEGED_READINESS_ATTEMPTED",
        "PRIVILEGED_READINESS_TERMINAL",
        "PRIVILEGED_READINESS_BROKER_REFUSED",
        "PRIVILEGED_READINESS_EFFECT_UNKNOWN",
        "PRIVILEGED_READINESS_RECONCILED",
    }


def test_event_aggregate_type_is_the_reviewed_literal():
    assert epa.READINESS_AGGREGATE_TYPE == "privileged_readiness"


def test_broker_refusal_reason_codes_reuse_the_merged_broker_domain():
    # The merged PR #613 broker emits exactly four wire error codes. Only three
    # of them are refusals; EFFECT_UNKNOWN is an effect state, never a refusal.
    assert epa.BROKER_REFUSAL_REASON_CODES == frozenset(
        {"PEER_UNAUTHORIZED", "REQUEST_ID_CONFLICT", "REFUSED"}
    )
    assert "EFFECT_UNKNOWN" not in epa.BROKER_REFUSAL_REASON_CODES


def test_broker_effect_unknown_error_maps_to_effect_unknown_state_not_refused():
    assert (
        epa.result_state_for_broker_error("EFFECT_UNKNOWN")
        is epa.ReadinessResultState.EFFECT_UNKNOWN
    )


@pytest.mark.parametrize("code", ["PEER_UNAUTHORIZED", "REQUEST_ID_CONFLICT", "REFUSED"])
def test_broker_refusal_errors_map_to_refused_state(code):
    assert epa.result_state_for_broker_error(code) is epa.ReadinessResultState.REFUSED


def test_unknown_broker_error_refuses_rather_than_defaulting():
    with pytest.raises(epa.PrivilegedReadinessError):
        epa.result_state_for_broker_error("SOMETHING_NEW")


def test_terminal_result_canonical_dict_has_exact_reviewed_keys():
    result = epa.ReadinessResult(**_terminal_kwargs())
    assert frozenset(result.to_canonical_dict()) == epa.RESULT_CANONICAL_KEYS
    assert frozenset(result.to_canonical_dict()) == frozenset(
        {
            "schema_version",
            "family_id",
            "operation_id",
            "state",
            "replayed",
            "observed_at_ms",
            "evidence_currency",
            "observation_scope",
            "binding",
            "receipt",
            "reason_origin",
            "reason_code",
        }
    )


def test_every_result_state_carries_the_fixed_observation_scope():
    terminal = epa.ReadinessResult(**_terminal_kwargs()).to_canonical_dict()
    refused = epa.ReadinessResult(
        **_terminal_kwargs(
            state=epa.ReadinessResultState.REFUSED,
            receipt=None,
            reason_origin="BROKER",
            reason_code="REFUSED",
        )
    ).to_canonical_dict()
    unknown = epa.ReadinessResult(
        **_terminal_kwargs(state=epa.ReadinessResultState.EFFECT_UNKNOWN, receipt=None)
    ).to_canonical_dict()
    for projection in (terminal, refused, unknown):
        assert projection["observation_scope"] == epa.OBSERVATION_SCOPE
        assert projection["schema_version"] == epa.RESULT_SCHEMA


def test_terminal_result_requires_a_receipt():
    with pytest.raises(epa.PrivilegedReadinessError):
        epa.ReadinessResult(**_terminal_kwargs(receipt=None))


def test_refused_result_requires_null_receipt_and_closed_broker_reason():
    with pytest.raises(epa.PrivilegedReadinessError):
        epa.ReadinessResult(
            **_terminal_kwargs(
                state=epa.ReadinessResultState.REFUSED,
                receipt=VALID_RECEIPT,
                reason_origin="BROKER",
                reason_code="REFUSED",
            )
        )
    with pytest.raises(epa.PrivilegedReadinessError):
        epa.ReadinessResult(
            **_terminal_kwargs(
                state=epa.ReadinessResultState.REFUSED,
                receipt=None,
                reason_origin="BROKER",
                reason_code="EFFECT_UNKNOWN",
            )
        )
    with pytest.raises(epa.PrivilegedReadinessError):
        epa.ReadinessResult(
            **_terminal_kwargs(
                state=epa.ReadinessResultState.REFUSED,
                receipt=None,
                reason_origin="CONTROLLER",
                reason_code="REFUSED",
            )
        )


def test_effect_unknown_result_carries_no_receipt_and_no_reason():
    with pytest.raises(epa.PrivilegedReadinessError):
        epa.ReadinessResult(
            **_terminal_kwargs(state=epa.ReadinessResultState.EFFECT_UNKNOWN, receipt=VALID_RECEIPT)
        )
    with pytest.raises(epa.PrivilegedReadinessError):
        epa.ReadinessResult(
            **_terminal_kwargs(
                state=epa.ReadinessResultState.EFFECT_UNKNOWN,
                receipt=None,
                reason_origin="BROKER",
                reason_code="REFUSED",
            )
        )


def test_terminal_result_refuses_a_reason_origin_or_code():
    with pytest.raises(epa.PrivilegedReadinessError):
        epa.ReadinessResult(**_terminal_kwargs(reason_origin="BROKER"))
    with pytest.raises(epa.PrivilegedReadinessError):
        epa.ReadinessResult(**_terminal_kwargs(reason_code="REFUSED"))


@pytest.mark.parametrize("bad_observed_at", [0, -1, True, 1.0, "1800000000000", None])
def test_observed_at_ms_must_be_a_positive_non_bool_integer(bad_observed_at):
    with pytest.raises(epa.PrivilegedReadinessError):
        epa.ReadinessResult(**_terminal_kwargs(observed_at_ms=bad_observed_at))


@pytest.mark.parametrize("bad_replayed", [0, 1, "false", None])
def test_replayed_must_be_a_real_bool(bad_replayed):
    with pytest.raises(epa.PrivilegedReadinessError):
        epa.ReadinessResult(**_terminal_kwargs(replayed=bad_replayed))


def test_result_refuses_family_or_operation_id_prefix_swap():
    with pytest.raises(epa.PrivilegedReadinessError):
        epa.ReadinessResult(**_terminal_kwargs(family_id=epa.OPERATION_ID_PREFIX + "1" * 48))
    with pytest.raises(epa.PrivilegedReadinessError):
        epa.ReadinessResult(**_terminal_kwargs(operation_id=epa.FAMILY_ID_PREFIX + "2" * 48))


def test_result_is_frozen():
    result = epa.ReadinessResult(**_terminal_kwargs())
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.state = epa.ReadinessResultState.REFUSED  # type: ignore[misc]


def test_replayed_terminal_reproduces_the_identical_receipt_and_scope():
    fresh = epa.ReadinessResult(**_terminal_kwargs())
    replayed = epa.ReadinessResult(**_terminal_kwargs(replayed=True))
    fresh_projection = fresh.to_canonical_dict()
    replayed_projection = replayed.to_canonical_dict()
    assert replayed_projection["receipt"] == fresh_projection["receipt"]
    assert replayed_projection["observation_scope"] == fresh_projection["observation_scope"]
    assert replayed_projection["state"] == "TERMINAL"
    assert replayed_projection["replayed"] is True


def test_historical_currency_never_downgrades_state_or_drops_the_receipt():
    historical = epa.ReadinessResult(
        **_terminal_kwargs(
            replayed=True, evidence_currency=epa.ReadinessEvidenceCurrency.HISTORICAL
        )
    ).to_canonical_dict()
    assert historical["state"] == "TERMINAL"
    assert historical["evidence_currency"] == "HISTORICAL"
    assert historical["receipt"] == VALID_RECEIPT
    assert historical["observation_scope"] == epa.OBSERVATION_SCOPE


def test_evidence_currency_is_current_only_on_exact_three_fact_equality():
    binding = epa.ReadinessBinding(**_valid_binding_kwargs())
    assert (
        epa.evidence_currency_for(
            binding,
            current_boot_id=VALID_BOOT_ID,
            current_release_sha=VALID_RELEASE_SHA,
            current_authority_policy_hash=VALID_POLICY_HASH,
        )
        is epa.ReadinessEvidenceCurrency.CURRENT
    )


@pytest.mark.parametrize(
    "overrides",
    [
        {"current_boot_id": "1f9d2fbc-6d31-4ebe-9e1d-a0b21d31eedb"},
        {"current_release_sha": "d" * 40},
        {"current_authority_policy_hash": "e" * 64},
    ],
)
def test_any_single_fact_mismatch_yields_historical(overrides):
    binding = epa.ReadinessBinding(**_valid_binding_kwargs())
    facts = {
        "current_boot_id": VALID_BOOT_ID,
        "current_release_sha": VALID_RELEASE_SHA,
        "current_authority_policy_hash": VALID_POLICY_HASH,
    }
    facts.update(overrides)
    assert (
        epa.evidence_currency_for(binding, **facts)
        is epa.ReadinessEvidenceCurrency.HISTORICAL
    )


@pytest.mark.parametrize(
    "unprovable",
    ["current_boot_id", "current_release_sha", "current_authority_policy_hash"],
)
def test_an_unprovable_fact_yields_historical_rather_than_current(unprovable):
    binding = epa.ReadinessBinding(**_valid_binding_kwargs())
    facts = {
        "current_boot_id": VALID_BOOT_ID,
        "current_release_sha": VALID_RELEASE_SHA,
        "current_authority_policy_hash": VALID_POLICY_HASH,
    }
    facts[unprovable] = None
    assert (
        epa.evidence_currency_for(binding, **facts)
        is epa.ReadinessEvidenceCurrency.HISTORICAL
    )


def test_evidence_currency_compares_boot_id_case_insensitively_after_canonicalization():
    binding = epa.ReadinessBinding(**_valid_binding_kwargs())
    assert (
        epa.evidence_currency_for(
            binding,
            current_boot_id=VALID_BOOT_ID.upper(),
            current_release_sha=VALID_RELEASE_SHA,
            current_authority_policy_hash=VALID_POLICY_HASH,
        )
        is epa.ReadinessEvidenceCurrency.CURRENT
    )


def test_evidence_currency_refuses_a_malformed_current_boot_id():
    binding = epa.ReadinessBinding(**_valid_binding_kwargs())
    assert (
        epa.evidence_currency_for(
            binding,
            current_boot_id="adapter-17",
            current_release_sha=VALID_RELEASE_SHA,
            current_authority_policy_hash=VALID_POLICY_HASH,
        )
        is epa.ReadinessEvidenceCurrency.HISTORICAL
    )


def test_result_projection_exposes_no_secret_bearing_field_at_any_depth():
    forbidden = {
        "lease_token",
        "token",
        "credential",
        "credentials",
        "auth_path",
        "auth_json",
        "password",
        "provider_account",
        "environ",
        "environment",
        "home",
    }

    def _walk(value):
        if isinstance(value, dict):
            for key, item in value.items():
                assert key not in forbidden, f"secret-bearing key {key!r} reached the result"
                _walk(item)
        elif isinstance(value, (list, tuple)):
            for item in value:
                _walk(item)

    _walk(epa.ReadinessResult(**_terminal_kwargs()).to_canonical_dict())


def test_result_projection_is_canonical_json_serializable():
    projection = epa.ReadinessResult(**_terminal_kwargs()).to_canonical_dict()
    reloaded = json.loads(epa.canonical_json_bytes(projection).decode("utf-8"))
    assert reloaded == projection


def test_result_binding_projection_matches_the_binding_canonical_dict():
    binding = epa.ReadinessBinding(**_valid_binding_kwargs())
    projection = epa.ReadinessResult(**_terminal_kwargs(binding=binding)).to_canonical_dict()
    assert projection["binding"] == binding.to_canonical_dict()


def test_result_refuses_a_non_binding_binding():
    with pytest.raises(epa.PrivilegedReadinessError):
        epa.ReadinessResult(**_terminal_kwargs(binding={"job_id": "JOB-001"}))


def test_no_projected_result_value_can_be_read_as_a_ready_claim():
    """Every value a consumer can read off a result is READY-free by construction."""

    projection = epa.ReadinessResult(**_terminal_kwargs()).to_canonical_dict()
    rendered = epa.canonical_json_bytes(projection).decode("utf-8")
    assert "READY" not in rendered.replace("NO_READY_ASSERTION", "")
    assert not hasattr(epa.ReadinessResult, "ready")


def test_broker_reason_domain_is_derived_from_the_merged_broker_source():
    """The reused domain must break if the merged broker owner adds a code.

    Read as source text rather than importing: the broker module is a merged
    root actuator and must not be imported, loaded or exercised by this pure
    contract test.
    """

    broker_source = (
        pathlib.Path(__file__).resolve().parents[1]
        / "control_plane"
        / "executive_privileged_broker.py"
    ).read_text(encoding="utf-8")
    emitted = set(re.findall(r'_wire_error\(\s*"([A-Z_]+)"', broker_source))
    assert emitted, "no broker wire error codes were located"
    assert emitted == epa.BROKER_REFUSAL_REASON_CODES | {epa.BROKER_EFFECT_UNKNOWN_ERROR}
    for code in emitted:
        assert isinstance(epa.result_state_for_broker_error(code), epa.ReadinessResultState)
