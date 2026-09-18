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
