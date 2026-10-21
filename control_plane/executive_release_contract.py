"""Pure P4 release records: structural consistency, never live authority.

These validators neither authenticate a principal/seal nor authorize a release.
Consumers must independently verify current trust, policy, arming and original
Runtime evidence. In particular, historical records remain structurally valid
after expiry. No key, clock, process or Runtime is consulted here.
"""

from __future__ import annotations

import base64
import binascii
from collections.abc import Mapping, Iterator
from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any
from uuid import UUID

from control_plane.ceo_request import CeoRequestError, app_request_ref

__all__ = [
    "validate_principal_projection",
    "validate_release_policy",
    "validate_release_grant",
    "validate_normalized_effect",
    "validate_approval_evidence",
    "validate_precondition_manifest",
    "validate_admission",
    "validate_prepared_payload",
    "approval_ref_for",
    "request_fingerprint_for",
    "broker_request_id_for",
    "canonical_release_bytes",
    "parse_release_json",
    "validate_release_terminal_status",
    "validate_release_terminal_receipt",
    "validate_release_prestart_reservation",
    "validate_release_prestart_cancellation",
    "validate_release_publication_intent",
    "validate_release_recovery_origin",
]

_MAX_BYTES = 16 * 1024
_MAX_DEPTH = 8
_MAX_INT = (1 << 63) - 1
_ACTIONS = ("executive.release.rollback", "executive.release.upgrade")
# Derived from the two return modes of the pinned owner contract
# ops/executive_os/install_source_policy.py::validate_install_source. Importing
# that IO module would add filesystem inspection to this pure dependency graph.
_SOURCE_MODES = ("exact_protected_master", "frozen_accepted_ancestor")
_CONFIRMATIONS = ("required", "delegated")
_SUBMIT_SCOPE = "mastermind.executive.intent.submit"
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,159}", re.ASCII)
_HEX64 = re.compile(r"[0-9a-f]{64}", re.ASCII)
_HEX40 = re.compile(r"[0-9a-f]{40}", re.ASCII)
_BROKER_ID = re.compile(r"p4r-[0-9a-f]{48}", re.ASCII)
_FP_DOMAIN = b"MMX_EXECUTIVE_RELEASE_REQUEST_V1\0"
_FP_FIELDS = (
    "operation_key",
    "approved_transition_ref",
    "approval_evidence_digest",
    "authenticated_principal_digest",
    "target_ref",
    "action_family",
    "normalized_requested_effect_digest",
)


class ReleaseContractError(ValueError):
    """A bounded field/code diagnostic; never echoes rejected input."""

    def __init__(self, field: str, code: str):
        self.field, self.code = field, code
        super().__init__(f"{field}:{code}")


@dataclass(frozen=True, slots=True)
class ReleaseRecord(Mapping[str, Any]):
    """Detached immutable JSON object. A record is evidence, not authority.

    Obtain validated records through the named validators. Construction of a
    Python object, including this class, conveys no trust to an owner consumer.
    """

    _items: tuple[tuple[str, Any], ...]

    def __getitem__(self, key: str) -> Any:
        for name, value in self._items:
            if name == key:
                return value
        raise KeyError(key)

    def __iter__(self) -> Iterator[str]:
        return (name for name, _ in self._items)

    def __len__(self) -> int:
        return len(self._items)

    def to_dict(self) -> dict[str, Any]:
        """Return an independent mutable projection, not the stored objects."""
        return _plain(self)


def _fail(field: str, code: str = "INVALID") -> None:
    raise ReleaseContractError(field, code)


def _plain(value: Any, depth: int = 1) -> Any:
    if depth > _MAX_DEPTH and (
        isinstance(value, Mapping) or type(value) in (list, tuple)
    ):
        _fail("payload", "DEPTH")
    if isinstance(value, Mapping):
        if any(type(key) is not str for key in value):
            _fail("payload", "KEY_TYPE")
        for key in value:
            # JSON member names are also untrusted Unicode. Never leak a bad
            # key through an encoder's payload-bearing Unicode exception.
            _plain(key, depth + 1)
        return {key: _plain(item, depth + 1) for key, item in value.items()}
    if type(value) in (list, tuple):
        return [_plain(item, depth + 1) for item in value]
    if type(value) is bool:
        return value
    if type(value) is int and 0 <= value <= _MAX_INT:
        return value
    if type(value) is str:
        try:
            encoded = value.encode("utf-8", errors="strict")
        except UnicodeError:
            _fail("payload", "UTF8")
        if len(encoded) > _MAX_BYTES:
            _fail("payload", "SIZE")
        return value
    _fail("payload", "VALUE_TYPE")


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return ReleaseRecord(
            tuple((key, _freeze(item)) for key, item in sorted(value.items()))
        )
    if type(value) in (list, tuple):
        return tuple(_freeze(item) for item in value)
    return value


def canonical_release_bytes(validated_value: Any) -> bytes:
    """Encode bounded JSON. Encoding alone does not perform schema validation."""
    value = _plain(validated_value)
    if not isinstance(value, dict):
        _fail("payload", "OBJECT_REQUIRED")
    raw = json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    if len(raw) > _MAX_BYTES:
        _fail("payload", "SIZE")
    return raw


def parse_release_json(raw_bytes: bytes) -> ReleaseRecord:
    """Parse the canonical wire object before applying its schema validator."""
    if type(raw_bytes) is not bytes or not 0 < len(raw_bytes) <= _MAX_BYTES:
        _fail("payload", "SIZE_OR_TYPE")
    # Bound nesting before the JSON decoder allocates/recurses. Braces inside
    # strings and escaped quotes do not contribute to structural depth.
    depth, quoted, escaped = 0, False, False
    for byte in raw_bytes:
        if quoted:
            if escaped:
                escaped = False
            elif byte == 92:
                escaped = True
            elif byte == 34:
                quoted = False
        elif byte == 34:
            quoted = True
        elif byte in (91, 123):
            depth += 1
            if depth > _MAX_DEPTH:
                _fail("payload", "DEPTH")
        elif byte in (93, 125):
            depth -= 1

    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                _fail("payload", "DUPLICATE_KEY")
            result[key] = value
        return result

    def reject_number(_: str) -> None:
        _fail("payload", "NUMBER_TYPE")

    def bounded_integer(text: str) -> int:
        if len(text) > 19 or text.startswith("-"):
            _fail("payload", "INTEGER_RANGE")
        return _integer(int(text), "payload")

    try:
        value = json.loads(
            raw_bytes.decode("utf-8", errors="strict"),
            object_pairs_hook=pairs,
            parse_float=reject_number,
            parse_constant=reject_number,
            parse_int=bounded_integer,
        )
    except (UnicodeError, json.JSONDecodeError, RecursionError):
        raise ReleaseContractError("payload", "INVALID_JSON") from None
    if canonical_release_bytes(value) != raw_bytes:
        _fail("payload", "NONCANONICAL")
    return _freeze(value)


def _object(
    value: Any,
    fields: str,
    label: str,
    schema: str | None = None,
    schema_key: str = "schema",
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        _fail(label, "OBJECT_REQUIRED")
    # Detach input first. Subsequent checks and final records see the same bytes.
    result = _plain(value)
    canonical_release_bytes(result)
    if set(result) != set(fields.split()):
        _fail(label, "FIELDS")
    if schema is not None and result[schema_key] != schema:
        _fail(schema_key, "SCHEMA")
    return result


def _pattern(value: Any, field: str, pattern: re.Pattern[str]) -> str:
    if type(value) is not str or pattern.fullmatch(value) is None:
        _fail(field, "FORMAT")
    return value


def _id(value: Any, field: str) -> str:
    return _pattern(value, field, _ID)


def _digest(value: Any, field: str) -> str:
    return _pattern(value, field, _HEX64)


def _integer(value: Any, field: str, minimum: int = 0, maximum: int = _MAX_INT) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        _fail(field, "INTEGER_RANGE")
    return value


def _enum(value: Any, field: str, values: tuple[str, ...]) -> str:
    if type(value) is not str or value not in values:
        _fail(field, "ENUM")
    return value


def _uuid(value: Any, field: str) -> str:
    if type(value) is not str:
        _fail(field, "UUID")
    try:
        parsed = UUID(value)
    except (ValueError, AttributeError):
        _fail(field, "UUID")
    if parsed.int == 0 or str(parsed) != value:
        _fail(field, "UUID")
    return value


def _array(value: Any, field: str, check: Any, maximum: int = 32) -> None:
    if type(value) not in (list, tuple) or not 1 <= len(value) <= maximum:
        _fail(field, "ARRAY_BOUND")
    for item in value:
        check(item, field)
    if list(value) != sorted(set(value)):
        _fail(field, "SORTED_UNIQUE")


def _client(value: Any, field: str) -> str:
    _id(value, field)
    if value == "oauth-client-unavailable":
        _fail(field, "CLIENT_UNAVAILABLE")
    return value


def _lifetime(
    value: Mapping[str, Any], start: str, end: str, scale: int = 1000
) -> None:
    before = _integer(value[start], start)
    after = _integer(value[end], end)
    if not 0 < after - before <= 300 * scale:
        _fail(end, "LIFETIME")


def _hash(value: Any) -> str:
    return hashlib.sha256(canonical_release_bytes(value)).hexdigest()


def _equal(actual: Any, expected: Any, field: str) -> None:
    if actual != expected:
        _fail(field, "MISMATCH")


def _request_ref(operation_key: Any) -> str:
    try:
        return app_request_ref(operation_key)
    except CeoRequestError:
        raise ReleaseContractError("operation_key", "FORMAT") from None


def approval_ref_for(operation_key: str) -> str:
    return "p4-approval:" + _request_ref(operation_key)


def validate_principal_projection(value: Any) -> ReleaseRecord:
    v = _object(
        value,
        "policy_id issuer_digest resource_digest subject_digest client_ref scopes",
        "principal",
    )
    _id(v["policy_id"], "policy_id")
    for key in ("issuer_digest", "resource_digest", "subject_digest"):
        _digest(v[key], key)
    _client(v["client_ref"], "client_ref")
    _array(v["scopes"], "scopes", _id, 16)
    return _freeze(v)


def validate_release_policy(value: Any) -> ReleaseRecord:
    v = _object(
        value,
        "schema policy_id generation enabled issuer_digest resource_digest subject_digests client_refs required_scopes actions target_refs installer_profile_digests source_policy_modes max_approval_lifetime_seconds confirmation_requirement",
        "policy",
        "mastermind.executive_release_controller_policy/v1",
    )
    _id(v["policy_id"], "policy_id")
    _integer(v["generation"], "generation", 1)
    if type(v["enabled"]) is not bool:
        _fail("enabled", "BOOLEAN")
    for key in ("issuer_digest", "resource_digest"):
        _digest(v[key], key)
    for key in ("subject_digests", "target_refs", "installer_profile_digests"):
        _array(v[key], key, _digest)
    _array(v["client_refs"], "client_refs", _client)
    _array(v["required_scopes"], "required_scopes", _id, 16)
    if _SUBMIT_SCOPE not in v["required_scopes"]:
        _fail("required_scopes", "SUBMIT_REQUIRED")
    _array(v["actions"], "actions", lambda x, k: _enum(x, k, _ACTIONS), 2)
    _array(
        v["source_policy_modes"],
        "source_policy_modes",
        lambda x, k: _enum(x, k, _SOURCE_MODES),
    )
    _integer(
        v["max_approval_lifetime_seconds"], "max_approval_lifetime_seconds", 1, 300
    )
    _enum(v["confirmation_requirement"], "confirmation_requirement", _CONFIRMATIONS)
    return _freeze(v)


def validate_release_grant(value: Any) -> ReleaseRecord:
    v = _object(
        value,
        "schema principal_digest authority_policy_hash policy_id policy_generation action target_ref transition_digest installer_profile_digest confirmation_requirement confirmation_evidence_digest granted_at_ms expires_at_ms",
        "grant",
        "mastermind.executive_release_grant/v1",
    )
    for key in (
        "principal_digest",
        "authority_policy_hash",
        "target_ref",
        "transition_digest",
        "installer_profile_digest",
        "confirmation_evidence_digest",
    ):
        _digest(v[key], key)
    _id(v["policy_id"], "policy_id")
    _integer(v["policy_generation"], "policy_generation", 1)
    _enum(v["action"], "action", _ACTIONS)
    _enum(v["confirmation_requirement"], "confirmation_requirement", _CONFIRMATIONS)
    _lifetime(v, "granted_at_ms", "expires_at_ms")
    return _freeze(v)


def validate_normalized_effect(value: Any) -> ReleaseRecord:
    v = _object(
        value,
        "schema repository protected_source_sha source_policy_mode installer_source_commit installer_source_tree installer_profile_digest from_release_commit from_release_tree from_installed_manifest_digest to_release_commit to_release_tree staged_artifact_digest staged_content_metadata_digest platform architecture configuration_transition_digest compatibility_proof_digest preservation_plan_digest rollback_evidence action",
        "effect",
        "mastermind.executive_release_effect/v1",
    )
    _equal(v["repository"], "mastermindx-market-intelligence/Mastermind", "repository")
    _enum(v["source_policy_mode"], "source_policy_mode", _SOURCE_MODES)
    _equal(v["platform"], "darwin", "platform")
    _enum(v["architecture"], "architecture", ("arm64", "x86_64"))
    _enum(v["action"], "action", _ACTIONS)
    for key in (
        "protected_source_sha",
        "installer_source_commit",
        "installer_source_tree",
        "from_release_commit",
        "from_release_tree",
        "to_release_commit",
        "to_release_tree",
    ):
        _pattern(v[key], key, _HEX40)
    for key in (
        "installer_profile_digest",
        "from_installed_manifest_digest",
        "staged_artifact_digest",
        "staged_content_metadata_digest",
        "configuration_transition_digest",
        "compatibility_proof_digest",
        "preservation_plan_digest",
    ):
        _digest(v[key], key)
    _equal(
        v["installer_source_commit"],
        v["protected_source_sha"],
        "installer_source_commit",
    )
    if v["source_policy_mode"] == "exact_protected_master":
        _equal(v["to_release_commit"], v["protected_source_sha"], "to_release_commit")
        _equal(v["to_release_tree"], v["installer_source_tree"], "to_release_tree")
    elif v["to_release_commit"] == v["protected_source_sha"]:
        _fail("to_release_commit", "STRICT_ANCESTOR_REQUIRED")
    upgrade = v["action"] == "executive.release.upgrade"
    keys = (
        "kind rollback_readiness_digest"
        if upgrade
        else "kind original_upgrade_request_id original_terminal_or_reconciliation_digest retained_artifact_digest preimage_digest current_compatibility_digest"
    )
    rollback = _object(v["rollback_evidence"], keys, "rollback_evidence")
    _equal(
        rollback["kind"], "upgrade" if upgrade else "rollback", "rollback_evidence.kind"
    )
    for key, item in rollback.items():
        if key == "original_upgrade_request_id":
            _pattern(item, key, _BROKER_ID)
        elif key != "kind":
            _digest(item, key)
    return _freeze(v)


def validate_approval_evidence(value: Any) -> ReleaseRecord:
    v = _object(
        value,
        "schema operation_key request_ref approved_transition_ref action owner_installation_id target_ref principal_projection normalized_requested_effect transition_digest grant effective_grant_digest created_at_ms expires_at_ms owner_seal",
        "approval",
        "mastermind.executive_release_approval/v1",
    )
    _equal(v["request_ref"], _request_ref(v["operation_key"]), "request_ref")
    _equal(
        v["approved_transition_ref"],
        approval_ref_for(v["operation_key"]),
        "approved_transition_ref",
    )
    _uuid(v["owner_installation_id"], "owner_installation_id")
    _digest(v["target_ref"], "target_ref")
    _enum(v["action"], "action", _ACTIONS)
    principal = validate_principal_projection(v["principal_projection"])
    effect = validate_normalized_effect(v["normalized_requested_effect"])
    grant = validate_release_grant(v["grant"])
    _equal(v["action"], effect["action"], "action")
    _equal(v["transition_digest"], _hash(effect), "transition_digest")
    _equal(v["effective_grant_digest"], _hash(grant), "effective_grant_digest")
    _equal(grant["principal_digest"], _hash(principal), "grant.principal_digest")
    _equal(grant["policy_id"], principal["policy_id"], "grant.policy_id")
    for key in ("action", "target_ref", "transition_digest"):
        _equal(grant[key], v[key], "grant." + key)
    _equal(
        grant["installer_profile_digest"],
        effect["installer_profile_digest"],
        "grant.installer_profile_digest",
    )
    _lifetime(v, "created_at_ms", "expires_at_ms")
    if (
        v["created_at_ms"] < grant["granted_at_ms"]
        or v["expires_at_ms"] > grant["expires_at_ms"]
    ):
        _fail("expires_at_ms", "OUTSIDE_GRANT")
    seal = _object(v["owner_seal"], "key_id trust_generation mac", "owner_seal")
    _id(seal["key_id"], "key_id")
    _integer(seal["trust_generation"], "trust_generation", 1)
    mac = seal["mac"]
    if type(mac) is not str or re.fullmatch(r"[A-Za-z0-9_-]{43}", mac) is None:
        _fail("owner_seal.mac", "FORMAT")
    try:
        decoded = base64.b64decode(mac + "=", altchars=b"-_", validate=True)
    except (ValueError, binascii.Error):
        _fail("owner_seal.mac", "FORMAT")
    if (
        len(decoded) != 32
        or base64.urlsafe_b64encode(decoded).decode("ascii").rstrip("=") != mac
    ):
        _fail("owner_seal.mac", "NONCANONICAL")
    return _freeze(v)


def validate_precondition_manifest(value: Any) -> ReleaseRecord:
    v = _object(
        value,
        "schema owner_installation_id target_ref boot_id from_installed_manifest_digest installed_configuration_digest python_runtime_provenance_digest provider_binary_attestation_digest authority_policy_hash grant_digest approval_evidence_digest staged_artifact_digest staged_content_metadata_digest compatibility_proof_digest preservation_plan_digest issuer_binding_digest admission_contract_digest production_arming_digest",
        "preconditions",
        "mastermind.executive_release_preconditions/v1",
    )
    for key, item in v.items():
        if key in ("owner_installation_id", "boot_id"):
            _uuid(item, key)
        elif key != "schema":
            _digest(item, key)
    return _freeze(v)


def validate_admission(value: Any) -> ReleaseRecord:
    v = _object(
        value,
        "schema operation_key approved_transition_ref target_ref owner_installation_id boot_id request_fingerprint effective_grant_digest maintenance_sequence admission_event_command_id target_observation_digest admission_contract_digest",
        "admission",
        "mastermind.executive_release_admission/v1",
    )
    request_ref = _request_ref(v["operation_key"])
    _equal(
        v["approved_transition_ref"],
        "p4-approval:" + request_ref,
        "approved_transition_ref",
    )
    _equal(
        v["admission_event_command_id"],
        "p4-admit:" + request_ref,
        "admission_event_command_id",
    )
    for key in ("owner_installation_id", "boot_id"):
        _uuid(v[key], key)
    for key in (
        "target_ref",
        "request_fingerprint",
        "effective_grant_digest",
        "target_observation_digest",
        "admission_contract_digest",
    ):
        _digest(v[key], key)
    _integer(v["maintenance_sequence"], "maintenance_sequence", 1)
    return _freeze(v)


def _fingerprint(fields: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        _FP_DOMAIN + canonical_release_bytes({key: fields[key] for key in _FP_FIELDS})
    ).hexdigest()


def request_fingerprint_for(validated_approval: Any) -> str:
    # Revalidate even a caller-constructed ReleaseRecord: type is not provenance.
    v = validate_approval_evidence(validated_approval)
    fields = {
        key: v[key]
        for key in ("operation_key", "approved_transition_ref", "target_ref")
    }
    fields.update(
        approval_evidence_digest=_hash(v),
        authenticated_principal_digest=_hash(v["principal_projection"]),
        action_family=v["action"],
        normalized_requested_effect_digest=_hash(v["normalized_requested_effect"]),
    )
    return _fingerprint(fields)


def broker_request_id_for(request_fingerprint: str) -> str:
    return "p4r-" + _digest(request_fingerprint, "request_fingerprint")[:48]


def validate_prepared_payload(value: Any) -> ReleaseRecord:
    v = _object(
        value,
        "token_schema app_id owner_installation_id app_generation schema_digest trust_generation key_id authenticated_principal_digest approved_transition_ref approval_evidence_digest policy_id policy_generation authority_policy_hash effective_grant_digest action_target_digest confirmation_requirement privilege_class operation_key action_family request_fingerprint target_ref boot_id platform normalized_requested_effect normalized_requested_effect_digest expected_source_and_precondition_digest admission_contract_digest issued_at_ms expires_at_ms issued_monotonic_ns expires_monotonic_ns",
        "prepared",
        "mastermind.executive_release_prepared.v1",
        "token_schema",
    )
    _equal(v["app_id"], "mastermind.executive", "app_id")
    _equal(v["privilege_class"], "EXECUTIVE_RELEASE_TRANSITION", "privilege_class")
    _equal(v["platform"], "darwin", "platform")
    _equal(
        v["approved_transition_ref"],
        approval_ref_for(v["operation_key"]),
        "approved_transition_ref",
    )
    for key in ("owner_installation_id", "boot_id"):
        _uuid(v[key], key)
    for key in ("app_generation", "trust_generation", "policy_generation"):
        _integer(v[key], key, 1)
    for key in ("key_id", "policy_id"):
        _id(v[key], key)
    for key in (
        "schema_digest",
        "authenticated_principal_digest",
        "approval_evidence_digest",
        "authority_policy_hash",
        "effective_grant_digest",
        "action_target_digest",
        "request_fingerprint",
        "target_ref",
        "normalized_requested_effect_digest",
        "expected_source_and_precondition_digest",
        "admission_contract_digest",
    ):
        _digest(v[key], key)
    _enum(v["confirmation_requirement"], "confirmation_requirement", _CONFIRMATIONS)
    _enum(v["action_family"], "action_family", _ACTIONS)
    effect = validate_normalized_effect(v["normalized_requested_effect"])
    _equal(v["action_family"], effect["action"], "action_family")
    _equal(
        v["normalized_requested_effect_digest"],
        _hash(effect),
        "normalized_requested_effect_digest",
    )
    _equal(v["request_fingerprint"], _fingerprint(v), "request_fingerprint")
    _lifetime(v, "issued_at_ms", "expires_at_ms")
    _lifetime(v, "issued_monotonic_ns", "expires_monotonic_ns", 1_000_000_000)
    return _freeze(v)


# ---------------------------------------------------------------------------
# P4 terminal status and receipt joins (R1). These correlate an already
# recorded attempt with its canonical approval. Nothing below authenticates a
# principal or seal, reads a journal, file, process or clock, or grants
# release, retry, rollback or recovery authority.
# ---------------------------------------------------------------------------

_STATUS_SCHEMA = "mastermind.executive_release_terminal_status/v1"
_RECEIPT_SCHEMA = "mastermind.executive_release_terminal_receipt/v1"
_NOT_FOUND = "NOT_FOUND"
_SUCCEEDED = "SUCCEEDED"
_ROLLED_BACK = "ROLLED_BACK"
_FAILED_NOT_APPLIED = "FAILED_NOT_APPLIED"
_RECORDED_STATES = ("STARTED", "PUBLISHED", "BROKER_RESTART_PENDING", "RECOVERING")
_TERMINAL_STATES = (_SUCCEEDED, _ROLLED_BACK, _FAILED_NOT_APPLIED)
_STATES = (_NOT_FOUND,) + _RECORDED_STATES + _TERMINAL_STATES
_SERVICE_ROLES = ("control", "worker", "relay", "gateway", "broker")
_STATUS_COMMON_FIELDS = (
    "schema state request_id request_fingerprint operation_key"
    " approved_transition_ref approval_evidence_digest"
    " authenticated_principal_digest effective_grant_digest"
    " normalized_requested_effect_digest action_family action_target_digest"
    " owner_installation_id target_ref from_release_commit to_release_commit"
)
_STATUS_RECORDED_FIELDS = (
    " actuator_generation journal_generation started_at_ms preconditions"
    " expected_precondition_digest admission admission_digest"
)
_STATUS_RECEIPT_FIELD = " terminal_receipt"
_IDENTITY_FIELDS = (
    "release_commit release_tree installed_manifest_digest"
    " configuration_digest broker_source_commit broker_source_tree"
    " broker_binary_digest service_generation_digests"
)
_IDENTITY_COMMITS = (
    "release_commit release_tree broker_source_commit broker_source_tree"
)
_IDENTITY_DIGESTS = (
    "installed_manifest_digest configuration_digest broker_binary_digest"
)
_SERVICE_ROLE_FIELDS = " control worker relay gateway broker"
_RECEIPT_FIELDS = (
    "schema request_id request_fingerprint approval_evidence_digest"
    " expected_precondition_digest admission_digest actuator_generation"
    " journal_generation started_at_ms completed_at_ms outcome before after"
    " rollback postcondition_digest"
)
_RECEIPT_STATUS_FIELDS = (
    "request_id request_fingerprint approval_evidence_digest"
    " expected_precondition_digest admission_digest actuator_generation"
    " journal_generation started_at_ms"
)
_PRECONDITION_EFFECT_FIELDS = (
    "from_installed_manifest_digest staged_artifact_digest"
    " staged_content_metadata_digest compatibility_proof_digest"
    " preservation_plan_digest"
)


def _status_field_set(state: str) -> str:
    # Key sets are exact per state: NOT_FOUND keeps only common fields, a
    # terminal state is the only state carrying a receipt member.
    if state == _NOT_FOUND:
        return _STATUS_COMMON_FIELDS
    fields = _STATUS_COMMON_FIELDS + _STATUS_RECORDED_FIELDS
    if state in _TERMINAL_STATES:
        return fields + _STATUS_RECEIPT_FIELD
    return fields


def _validate_installed_identity(value: Any, field: str) -> dict[str, Any]:
    """Installed content identity. Not a PID, process birth or run state."""
    v = _object(value, _IDENTITY_FIELDS, field)
    for key in _IDENTITY_COMMITS.split():
        _pattern(v[key], field + "." + key, _HEX40)
    for key in _IDENTITY_DIGESTS.split():
        _digest(v[key], field + "." + key)
    roles = _object(
        v["service_generation_digests"],
        _SERVICE_ROLE_FIELDS,
        field + ".service_generation_digests",
    )
    for key in _SERVICE_ROLES:
        _digest(roles[key], field + ".service_generation_digests." + key)
    v["service_generation_digests"] = roles
    return v


def _validate_rollback(value: Any, outcome: str, before: Mapping[str, Any]) -> None:
    # The rollback union is fixed by outcome: only ROLLED_BACK may carry a
    # restored preimage digest, and only of the saved content before-state.
    restored = outcome == _ROLLED_BACK
    v = _object(
        value,
        "attempted restored_preimage_digest" if restored else "attempted",
        "rollback",
    )
    if type(v["attempted"]) is not bool:
        _fail("rollback.attempted", "BOOLEAN")
    if v["attempted"] is not restored:
        _fail("rollback.attempted", "MISMATCH")
    if not restored:
        return
    _digest(v["restored_preimage_digest"], "rollback.restored_preimage_digest")
    _equal(
        v["restored_preimage_digest"],
        _hash(before),
        "rollback.restored_preimage_digest",
    )


def _validate_legacy_terminal_receipt(
    value: Any,
    status: Mapping[str, Any],
    approval: Mapping[str, Any],
    field: str,
) -> dict[str, Any]:
    v = _object(value, _RECEIPT_FIELDS, field, _RECEIPT_SCHEMA)
    for key in ("actuator_generation", "journal_generation"):
        _integer(v[key], key, 1)
    _integer(v["started_at_ms"], "started_at_ms")
    for key in _RECEIPT_STATUS_FIELDS.split():
        _equal(v[key], status[key], key)
    _enum(v["outcome"], "outcome", _TERMINAL_STATES)
    _equal(v["outcome"], status["state"], "outcome")
    # Completion may legitimately land after approval expiry; only the
    # ordering against this attempt's own start is structural.
    _integer(v["completed_at_ms"], "completed_at_ms", v["started_at_ms"])
    _digest(v["postcondition_digest"], "postcondition_digest")
    effect = approval["normalized_requested_effect"]
    before = _validate_installed_identity(v["before"], "before")
    after = _validate_installed_identity(v["after"], "after")
    _equal(
        before["release_commit"],
        effect["from_release_commit"],
        "before.release_commit",
    )
    _equal(before["release_tree"], effect["from_release_tree"], "before.release_tree")
    _equal(
        before["installed_manifest_digest"],
        effect["from_installed_manifest_digest"],
        "before.installed_manifest_digest",
    )
    _equal(
        before["configuration_digest"],
        status["preconditions"]["installed_configuration_digest"],
        "before.configuration_digest",
    )
    _equal(
        before["broker_source_commit"],
        before["release_commit"],
        "before.broker_source_commit",
    )
    _equal(
        before["broker_source_tree"],
        before["release_tree"],
        "before.broker_source_tree",
    )
    _equal(
        after["broker_source_commit"],
        after["release_commit"],
        "after.broker_source_commit",
    )
    _equal(
        after["broker_source_tree"],
        after["release_tree"],
        "after.broker_source_tree",
    )
    if v["outcome"] == _SUCCEEDED:
        _equal(
            after["release_commit"],
            effect["to_release_commit"],
            "after.release_commit",
        )
        _equal(after["release_tree"], effect["to_release_tree"], "after.release_tree")
    elif canonical_release_bytes(after) != canonical_release_bytes(before):
        _fail("after", "NOT_CONTENT_PREIMAGE")
    _validate_rollback(v["rollback"], v["outcome"], before)
    v["before"], v["after"] = before, after
    return v


def _validated_legacy_status_fields(
    value: Any, expected_approval: Any, *, validate_receipt: bool
) -> tuple[dict[str, Any], ReleaseRecord]:
    # The expected approval is revalidated on every path. A caller-constructed
    # ReleaseRecord is a Python object, never provenance.
    approval = validate_approval_evidence(expected_approval)
    if not isinstance(value, Mapping):
        _fail("status", "OBJECT_REQUIRED")
    # Read the caller's mapping once. The discriminator, exact field set and
    # returned record must describe this same bounded detached snapshot.
    snapshot = _plain(value)
    canonical_release_bytes(snapshot)
    state = snapshot.get("state")
    if type(state) is not str or state not in _STATES:
        _fail("state", "ENUM")
    v = _object(snapshot, _status_field_set(state), "status", _STATUS_SCHEMA)
    effect = approval["normalized_requested_effect"]
    grant = approval["grant"]
    fingerprint = request_fingerprint_for(approval)
    _pattern(v["request_id"], "request_id", _BROKER_ID)
    for key in (
        "request_fingerprint",
        "approval_evidence_digest",
        "authenticated_principal_digest",
        "effective_grant_digest",
        "normalized_requested_effect_digest",
        "action_target_digest",
        "target_ref",
    ):
        _digest(v[key], key)
    _uuid(v["owner_installation_id"], "owner_installation_id")
    for key in ("from_release_commit", "to_release_commit"):
        _pattern(v[key], key, _HEX40)
    _enum(v["action_family"], "action_family", _ACTIONS)
    # A matching shortened id alone never validates a family: the full
    # fingerprint is required as well.
    _equal(v["request_fingerprint"], fingerprint, "request_fingerprint")
    _equal(v["request_id"], broker_request_id_for(fingerprint), "request_id")
    for key in (
        "operation_key",
        "approved_transition_ref",
        "owner_installation_id",
        "target_ref",
        "effective_grant_digest",
    ):
        _equal(v[key], approval[key], key)
    _equal(
        v["approval_evidence_digest"], _hash(approval), "approval_evidence_digest"
    )
    _equal(
        v["authenticated_principal_digest"],
        _hash(approval["principal_projection"]),
        "authenticated_principal_digest",
    )
    _equal(
        v["normalized_requested_effect_digest"],
        _hash(effect),
        "normalized_requested_effect_digest",
    )
    _equal(v["action_family"], approval["action"], "action_family")
    _equal(
        v["action_target_digest"],
        _hash({"action": approval["action"], "target_ref": approval["target_ref"]}),
        "action_target_digest",
    )
    _equal(
        v["from_release_commit"],
        effect["from_release_commit"],
        "from_release_commit",
    )
    _equal(v["to_release_commit"], effect["to_release_commit"], "to_release_commit")
    if state == _NOT_FOUND:
        # Common fields only. This validator cannot establish the physical
        # fact that a qualified owner found no journal family, and it neither
        # fabricates a start identity nor authorizes dispatch or retry.
        return v, approval
    _integer(v["actuator_generation"], "actuator_generation", 1)
    _integer(v["journal_generation"], "journal_generation", 1)
    started = _integer(v["started_at_ms"], "started_at_ms")
    # Historical ordering inside the original lifetime, not current-time proof.
    if not approval["created_at_ms"] <= started < approval["expires_at_ms"]:
        _fail("started_at_ms", "OUTSIDE_APPROVAL_LIFETIME")
    preconditions = validate_precondition_manifest(v["preconditions"])
    admission = validate_admission(v["admission"])
    v["preconditions"], v["admission"] = preconditions, admission
    _equal(
        v["expected_precondition_digest"],
        _hash(preconditions),
        "expected_precondition_digest",
    )
    _equal(v["admission_digest"], _hash(admission), "admission_digest")
    for key in ("owner_installation_id", "target_ref"):
        _equal(preconditions[key], approval[key], "preconditions." + key)
    _equal(
        preconditions["approval_evidence_digest"],
        _hash(approval),
        "preconditions.approval_evidence_digest",
    )
    _equal(
        preconditions["grant_digest"], _hash(grant), "preconditions.grant_digest"
    )
    _equal(
        preconditions["authority_policy_hash"],
        grant["authority_policy_hash"],
        "preconditions.authority_policy_hash",
    )
    for key in _PRECONDITION_EFFECT_FIELDS.split():
        _equal(preconditions[key], effect[key], "preconditions." + key)
    for key in (
        "operation_key",
        "approved_transition_ref",
        "target_ref",
        "owner_installation_id",
        "effective_grant_digest",
    ):
        _equal(admission[key], approval[key], "admission." + key)
    _equal(
        admission["request_fingerprint"], fingerprint, "admission.request_fingerprint"
    )
    _equal(admission["boot_id"], preconditions["boot_id"], "admission.boot_id")
    _equal(
        admission["admission_contract_digest"],
        preconditions["admission_contract_digest"],
        "admission.admission_contract_digest",
    )
    # admission.target_observation_digest keeps only its existing strict digest
    # grammar: the canonical Runtime producer owns its derivation, and no
    # durable Event write or maintenance exclusion is proved here.
    if state in _TERMINAL_STATES and validate_receipt:
        v["terminal_receipt"] = _validate_legacy_terminal_receipt(
            v["terminal_receipt"], v, approval, "terminal_receipt"
        )
    return v, approval


_V2_STATUS_SCHEMA = "mastermind.executive_release_terminal_status/v2"
_V2_RECEIPT_SCHEMA = "mastermind.executive_release_terminal_receipt/v2"
_V2_START_FIELDS = " before start_deadline_monotonic_ns root_qualification_digest"
_V2_RECEIPT_FIELDS = " after_actuator_generation publication_intent_digest recovery_origin_digest"


def _publication_start_from_status(status):
    return {
        "schema": "mastermind.executive_release_publication_start/v1",
        **{key: status[key] for key in (
            "operation_key", "request_fingerprint", "root_qualification_digest",
            "actuator_generation", "started_at_ms", "start_deadline_monotonic_ns",
            "before")},
    }


def _validate_terminal_receipt(value, status, approval, field):
    if status["schema"] == _STATUS_SCHEMA:
        return _validate_legacy_terminal_receipt(value, status, approval, field)
    receipt = _object(value, _RECEIPT_FIELDS + _V2_RECEIPT_FIELDS,
                      field, _V2_RECEIPT_SCHEMA)
    # Keep all legacy approval/content/rollback/timing joins. No schema escape.
    old = {k: receipt[k] for k in _RECEIPT_FIELDS.split()}
    old["schema"] = _RECEIPT_SCHEMA
    _validate_legacy_terminal_receipt(old, status, approval, field)
    if receipt["outcome"] not in (_SUCCEEDED, _ROLLED_BACK):
        _fail("outcome", "NO_APPLY_PROOF_UNAVAILABLE")
    _integer(receipt["after_actuator_generation"], "after_actuator_generation", 1)
    _equal(receipt["after_actuator_generation"], status["actuator_generation"] +
           (1 if receipt["outcome"] == _SUCCEEDED else 2), "after_actuator_generation")
    for key, record_key in (("publication_intent_digest", "publication_intent"),
                            ("recovery_origin_digest", "recovery_origin")):
        _digest(receipt[key], key)
        _equal(receipt[key], _hash(status[record_key]), key)
    _equal(canonical_release_bytes(receipt["before"]),
           canonical_release_bytes(status["before"]), "before")
    if receipt["completed_at_ms"] < status["publication_intent"]["intent_at_ms"]:
        _fail("completed_at_ms", "ORDER")
    return receipt


def _validated_status_fields(value, expected_approval, *, validate_receipt):
    # Preserve the closed historical protocol, including old terminal records.
    if not isinstance(value, Mapping):
        _fail("status", "OBJECT_REQUIRED")
    snapshot = _plain(value)
    canonical_release_bytes(snapshot)
    if snapshot.get("schema") == _STATUS_SCHEMA:
        return _validated_legacy_status_fields(snapshot, expected_approval,
                                               validate_receipt=validate_receipt)
    state = snapshot.get("state")
    allowed = ("STARTED", "PUBLICATION_INTENT", "PUBLISHED",
               "BROKER_RESTART_PENDING", "RECOVERING", _SUCCEEDED, _ROLLED_BACK)
    _enum(state, "state", allowed)
    fields = _STATUS_COMMON_FIELDS + _STATUS_RECORDED_FIELDS + _V2_START_FIELDS
    if state != "STARTED":
        fields += " publication_intent"
    recovering = state in ("RECOVERING", _SUCCEEDED, _ROLLED_BACK)
    if recovering:
        fields += " recovery_origin"
    if state in _TERMINAL_STATES:
        fields += _STATUS_RECEIPT_FIELD
    status = _object(snapshot, fields, "status", _V2_STATUS_SCHEMA)
    old_fields = _status_field_set("STARTED" if state == "PUBLICATION_INTENT" else state)
    old = {k: status[k] for k in old_fields.split()}
    old["schema"] = _STATUS_SCHEMA
    if state == "PUBLICATION_INTENT":
        old["state"] = "STARTED"
    _, approval = _validated_legacy_status_fields(old, expected_approval,
                                                  validate_receipt=False)
    n = _integer(status["actuator_generation"], "actuator_generation", 1, _MAX_INT - 2)
    _integer(status["start_deadline_monotonic_ns"], "start_deadline_monotonic_ns", 1)
    _digest(status["root_qualification_digest"], "root_qualification_digest")
    if status["root_qualification_digest"] == "0" * 64:
        _fail("root_qualification_digest", "ZERO")
    before = _validate_installed_identity(status["before"], "before")
    effect = approval["normalized_requested_effect"]
    for key, wanted in (
        ("release_commit", effect["from_release_commit"]),
        ("release_tree", effect["from_release_tree"]),
        ("installed_manifest_digest", effect["from_installed_manifest_digest"]),
        ("configuration_digest", status["preconditions"]["installed_configuration_digest"]),
        ("broker_source_commit", before["release_commit"]),
        ("broker_source_tree", before["release_tree"]),
    ):
        _equal(before[key], wanted, "before." + key)
    status["before"] = before
    generation = {"STARTED": 1, "PUBLICATION_INTENT": 2,
                  "PUBLISHED": 3, "BROKER_RESTART_PENDING": 4}.get(state)
    if state != "STARTED":
        status["publication_intent"] = validate_release_publication_intent(
            status["publication_intent"], expected_start=_publication_start_from_status(status))
    if recovering:
        status["recovery_origin"] = validate_release_recovery_origin(
            status["recovery_origin"], expected_intent=status["publication_intent"],
            expected_start=_publication_start_from_status(status))
        generation = status["recovery_origin"]["from_journal_generation"] + (
            1 if state == "RECOVERING" else 2)
    _equal(status["journal_generation"], generation, "journal_generation")
    if state in _TERMINAL_STATES and validate_receipt:
        status["terminal_receipt"] = _validate_terminal_receipt(
            status["terminal_receipt"], status, approval, "terminal_receipt")
    return status, approval


def validate_release_terminal_status(
    value: Any, *, expected_approval: Any
) -> ReleaseRecord:
    """Validate one recorded status state against its canonical approval.

    Detached evidence only. Consistency proves no journal write, effect,
    observation, exclusion or recovery ever happened, and a valid NOT_FOUND
    record authorizes neither dispatch nor retry.
    """
    v, _ = _validated_status_fields(value, expected_approval, validate_receipt=True)
    return _freeze(v)


def validate_release_terminal_receipt(
    value: Any, *, expected_status: Any, expected_approval: Any
) -> ReleaseRecord:
    """Validate a supplied receipt against a complete terminal status header.

    The expected status header is revalidated through the shared private
    helper, which does not validate that status's embedded receipt, so no
    status to receipt to status recursion exists. The supplied receipt must
    equal the embedded one in canonical bytes. Correlation with the canonical
    approval cannot be suppressed by any argument.
    """
    status, approval = _validated_status_fields(
        expected_status, expected_approval, validate_receipt=False
    )
    _enum(status["state"], "state", _TERMINAL_STATES)
    receipt = _validate_terminal_receipt(value, status, approval, "receipt")
    if canonical_release_bytes(receipt) != canonical_release_bytes(
        status["terminal_receipt"]
    ):
        _fail("receipt", "EMBEDDED_MISMATCH")
    return _freeze(receipt)


# ---------------------------------------------------------------------------
# P4 prestart reservation and cancellation contracts (R1). These are detached
# structural records only: they neither prove persistence, fresh observation,
# absence of an effect, cancellation delivery, fence release, dispatch,
# current authority nor any right to execute.
# ---------------------------------------------------------------------------

_RESERVATION_SCHEMA = "mastermind.executive_release_prestart_reservation/v1"
_CANCELLATION_SCHEMA = "mastermind.executive_release_prestart_cancellation/v1"
_RESERVATION_FIELDS = (
    "schema request_id request_fingerprint operation_key"
    " approved_transition_ref approval_evidence_digest"
    " authenticated_principal_digest effective_grant_digest"
    " normalized_requested_effect_digest action_family action_target_digest"
    " owner_installation_id target_ref from_release_commit to_release_commit"
    " reservation_generation reserved_at_ms reserved_monotonic_ns"
    " preconditions expected_precondition_digest prepared_payload"
    " prepared_token_digest before target_observation_digest"
)
_CANCELLATION_FIELDS = (
    "schema request_id request_fingerprint operation_key"
    " approved_transition_ref approval_evidence_digest"
    " authenticated_principal_digest effective_grant_digest"
    " normalized_requested_effect_digest action_family action_target_digest"
    " owner_installation_id target_ref from_release_commit to_release_commit"
    " reservation_generation root_qualification_digest admission_digest"
    " cancellation_generation cancelled_at_ms cancelled_monotonic_ns reason"
    " before current original_target_observation_digest"
    " current_target_observation_digest current_precondition_digest"
    " authority_evidence_digest"
)
_CANCELLATION_REASONS = (
    "PREPARED_TOKEN_EXPIRED",
    "PRINCIPAL_EXPIRED",
    "GRANT_EXPIRED",
    "AUTHORITY_REVOKED",
    "PRECONDITIONS_CHANGED",
    "TARGET_OBSERVATION_CHANGED",
)
_PUBLICATION_START_SCHEMA = "mastermind.executive_release_publication_start/v1"
_PUBLICATION_START_FIELDS = (
    "schema operation_key request_fingerprint root_qualification_digest"
    " actuator_generation started_at_ms start_deadline_monotonic_ns before"
)
_PUBLICATION_INTENT_SCHEMA = "mastermind.executive_release_publication_intent/v1"
_PUBLICATION_INTENT_FIELDS = (
    "schema operation_key request_fingerprint root_qualification_digest"
    " start_actuator_generation target_actuator_generation"
    " rollback_actuator_generation before_digest"
    " original_deadline_monotonic_ns intent_at_ms intent_monotonic_ns"
    " intent_journal_generation"
)
_RECOVERY_ORIGIN_SCHEMA = "mastermind.executive_release_recovery_origin/v1"
_RECOVERY_ORIGIN_FIELDS = (
    "schema operation_key request_fingerprint publication_intent_digest"
    " from_state from_journal_generation"
)
_PUBLICATION_PHASES = {
    "PUBLICATION_INTENT": 2,
    "PUBLISHED": 3,
    "BROKER_RESTART_PENDING": 4,
}
_RESERVATION_COMMON_DIGEST_FIELDS = (
    "request_fingerprint approval_evidence_digest"
    " authenticated_principal_digest effective_grant_digest"
    " normalized_requested_effect_digest action_target_digest target_ref"
    " prepared_token_digest target_observation_digest"
)
_CANCELLATION_COMMON_DIGEST_FIELDS = (
    "request_fingerprint approval_evidence_digest"
    " authenticated_principal_digest effective_grant_digest"
    " normalized_requested_effect_digest action_target_digest target_ref"
    " root_qualification_digest admission_digest"
    " original_target_observation_digest current_target_observation_digest"
    " current_precondition_digest authority_evidence_digest"
)
_PREPARED_IDENTITY_FIELDS = (
    "owner_installation_id operation_key approved_transition_ref target_ref"
    " effective_grant_digest approval_evidence_digest"
    " authenticated_principal_digest normalized_requested_effect_digest"
    " action_target_digest action_family request_fingerprint"
)


def _validate_common_approval_identity(
    value: Mapping[str, Any], approval: ReleaseRecord
) -> None:
    effect = approval["normalized_requested_effect"]
    fingerprint = request_fingerprint_for(approval)
    for key in (
        "request_fingerprint",
        "approval_evidence_digest",
        "authenticated_principal_digest",
        "effective_grant_digest",
        "normalized_requested_effect_digest",
        "action_target_digest",
        "target_ref",
    ):
        _digest(value[key], key)
    _uuid(value["owner_installation_id"], "owner_installation_id")
    for key in ("from_release_commit", "to_release_commit"):
        _pattern(value[key], key, _HEX40)
    _enum(value["action_family"], "action_family", _ACTIONS)
    _equal(value["request_fingerprint"], fingerprint, "request_fingerprint")
    _equal(value["request_id"], broker_request_id_for(fingerprint), "request_id")
    for key in (
        "operation_key",
        "approved_transition_ref",
        "owner_installation_id",
        "target_ref",
        "effective_grant_digest",
    ):
        _equal(value[key], approval[key], key)
    _equal(
        value["approval_evidence_digest"], _hash(approval), "approval_evidence_digest"
    )
    _equal(
        value["authenticated_principal_digest"],
        _hash(approval["principal_projection"]),
        "authenticated_principal_digest",
    )
    _equal(
        value["normalized_requested_effect_digest"],
        _hash(effect),
        "normalized_requested_effect_digest",
    )
    _equal(value["action_family"], approval["action"], "action_family")
    _equal(
        value["action_target_digest"],
        _hash({"action": approval["action"], "target_ref": approval["target_ref"]}),
        "action_target_digest",
    )
    _equal(
        value["from_release_commit"],
        effect["from_release_commit"],
        "from_release_commit",
    )
    _equal(value["to_release_commit"], effect["to_release_commit"], "to_release_commit")


def _validate_prestart_preconditions(
    value: Any, approval: ReleaseRecord
) -> ReleaseRecord:
    preconditions = validate_precondition_manifest(value)
    effect = approval["normalized_requested_effect"]
    grant = approval["grant"]
    for key in ("owner_installation_id", "target_ref"):
        _equal(preconditions[key], approval[key], "preconditions." + key)
    _equal(
        preconditions["approval_evidence_digest"],
        _hash(approval),
        "preconditions.approval_evidence_digest",
    )
    _equal(preconditions["grant_digest"], _hash(grant), "preconditions.grant_digest")
    _equal(
        preconditions["authority_policy_hash"],
        grant["authority_policy_hash"],
        "preconditions.authority_policy_hash",
    )
    for key in _PRECONDITION_EFFECT_FIELDS.split():
        _equal(preconditions[key], effect[key], "preconditions." + key)
    return preconditions


def _validate_prestart_prepared_payload(
    value: Any,
    reservation: Mapping[str, Any],
    approval: ReleaseRecord,
    preconditions: Mapping[str, Any],
) -> ReleaseRecord:
    prepared = validate_prepared_payload(value)
    grant = approval["grant"]
    for key in _PREPARED_IDENTITY_FIELDS.split():
        _equal(prepared[key], reservation[key], "prepared." + key)
    if canonical_release_bytes(prepared["normalized_requested_effect"]) != (
        canonical_release_bytes(approval["normalized_requested_effect"])
    ):
        _fail("prepared.normalized_requested_effect", "MISMATCH")
    for key in (
        "policy_id",
        "policy_generation",
        "authority_policy_hash",
        "confirmation_requirement",
    ):
        _equal(prepared[key], grant[key], "prepared." + key)
    _equal(
        prepared["trust_generation"],
        approval["owner_seal"]["trust_generation"],
        "prepared.trust_generation",
    )
    _equal(prepared["key_id"], approval["owner_seal"]["key_id"], "prepared.key_id")
    _equal(prepared["boot_id"], preconditions["boot_id"], "prepared.boot_id")
    _equal(
        prepared["expected_source_and_precondition_digest"],
        _hash(preconditions),
        "prepared.expected_source_and_precondition_digest",
    )
    _equal(
        prepared["admission_contract_digest"],
        preconditions["admission_contract_digest"],
        "prepared.admission_contract_digest",
    )
    if not approval["created_at_ms"] <= prepared["issued_at_ms"]:
        _fail("prepared.issued_at_ms", "OUTSIDE_APPROVAL_LIFETIME")
    if not prepared["expires_at_ms"] <= approval["expires_at_ms"]:
        _fail("prepared.expires_at_ms", "OUTSIDE_APPROVAL_LIFETIME")
    wall_duration_ns = (
        prepared["expires_at_ms"] - prepared["issued_at_ms"]
    ) * 1_000_000
    if (
        prepared["expires_monotonic_ns"] - prepared["issued_monotonic_ns"]
        != wall_duration_ns
    ):
        _fail("prepared.expires_monotonic_ns", "LIFETIME")
    return prepared


def _snapshot_exact_object(
    value: Any, fields: str, label: str, schema: str
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        _fail(label, "OBJECT_REQUIRED")
    snapshot = _plain(value)
    canonical_release_bytes(snapshot)
    return _object(snapshot, fields, label, schema)


def validate_release_prestart_reservation(
    value: Any, *, expected_approval: Any
) -> ReleaseRecord:
    """Validate a detached prestart reservation against its canonical approval."""
    approval = validate_approval_evidence(expected_approval)
    v = _snapshot_exact_object(
        value, _RESERVATION_FIELDS, "reservation", _RESERVATION_SCHEMA
    )
    _integer(v["reservation_generation"], "reservation_generation", 1, 1)
    _validate_common_approval_identity(v, approval)
    for key in _RESERVATION_COMMON_DIGEST_FIELDS.split():
        _digest(v[key], key)
    preconditions = _validate_prestart_preconditions(v["preconditions"], approval)
    _digest(v["expected_precondition_digest"], "expected_precondition_digest")
    _equal(
        v["expected_precondition_digest"],
        _hash(preconditions),
        "expected_precondition_digest",
    )
    prepared = _validate_prestart_prepared_payload(
        v["prepared_payload"], v, approval, preconditions
    )
    reserved_at_ms = _integer(v["reserved_at_ms"], "reserved_at_ms")
    reserved_monotonic_ns = _integer(
        v["reserved_monotonic_ns"], "reserved_monotonic_ns"
    )
    if not prepared["issued_at_ms"] <= reserved_at_ms < prepared["expires_at_ms"]:
        _fail("reserved_at_ms", "OUTSIDE_PREPARED_LIFETIME")
    if not (
        prepared["issued_monotonic_ns"]
        <= reserved_monotonic_ns
        < prepared["expires_monotonic_ns"]
    ):
        _fail("reserved_monotonic_ns", "OUTSIDE_PREPARED_LIFETIME")
    before = _validate_installed_identity(v["before"], "before")
    effect = approval["normalized_requested_effect"]
    _equal(
        before["release_commit"], effect["from_release_commit"], "before.release_commit"
    )
    _equal(before["release_tree"], effect["from_release_tree"], "before.release_tree")
    _equal(
        before["installed_manifest_digest"],
        effect["from_installed_manifest_digest"],
        "before.installed_manifest_digest",
    )
    _equal(
        before["configuration_digest"],
        preconditions["installed_configuration_digest"],
        "before.configuration_digest",
    )
    _equal(
        before["broker_source_commit"],
        before["release_commit"],
        "before.broker_source_commit",
    )
    _equal(
        before["broker_source_tree"],
        before["release_tree"],
        "before.broker_source_tree",
    )
    v["preconditions"] = preconditions
    v["prepared_payload"] = prepared
    v["before"] = before
    return _freeze(v)


def _validate_cancellation_before_current(
    cancellation: Mapping[str, Any],
    reservation: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    before = _validate_installed_identity(cancellation["before"], "before")
    expected_bytes = canonical_release_bytes(reservation["before"])
    if canonical_release_bytes(before) != expected_bytes:
        _fail("before", "CONTENT_CHANGED")
    current = _validate_installed_identity(cancellation["current"], "current")
    if canonical_release_bytes(current) != expected_bytes:
        _fail("current", "CONTENT_CHANGED")
    return before, current


def validate_release_prestart_cancellation(
    value: Any,
    *,
    expected_reservation: Any,
    expected_admission: Any,
    expected_approval: Any,
) -> ReleaseRecord:
    """Validate a detached prestart cancellation against immutable ancestors."""
    approval = validate_approval_evidence(expected_approval)
    reservation = validate_release_prestart_reservation(
        expected_reservation, expected_approval=approval
    )
    admission = validate_admission(expected_admission)
    for key in (
        "operation_key",
        "approved_transition_ref",
        "target_ref",
        "owner_installation_id",
        "effective_grant_digest",
        "request_fingerprint",
    ):
        _equal(admission[key], reservation[key], "admission." + key)
    _equal(
        admission["boot_id"],
        reservation["preconditions"]["boot_id"],
        "admission.boot_id",
    )
    _equal(
        admission["admission_contract_digest"],
        reservation["preconditions"]["admission_contract_digest"],
        "admission.admission_contract_digest",
    )
    _equal(
        admission["target_observation_digest"],
        reservation["target_observation_digest"],
        "admission.target_observation_digest",
    )
    v = _snapshot_exact_object(
        value, _CANCELLATION_FIELDS, "cancellation", _CANCELLATION_SCHEMA
    )
    _integer(v["reservation_generation"], "reservation_generation", 1, 1)
    _integer(v["cancellation_generation"], "cancellation_generation", 1, 1)
    _validate_common_approval_identity(v, approval)
    for key in _CANCELLATION_COMMON_DIGEST_FIELDS.split():
        _digest(v[key], key)
    _equal(
        v["root_qualification_digest"], _hash(reservation), "root_qualification_digest"
    )
    _equal(v["admission_digest"], _hash(admission), "admission_digest")
    cancelled_at_ms = _integer(v["cancelled_at_ms"], "cancelled_at_ms")
    cancelled_monotonic_ns = _integer(
        v["cancelled_monotonic_ns"], "cancelled_monotonic_ns"
    )
    if cancelled_at_ms < reservation["reserved_at_ms"]:
        _fail("cancelled_at_ms", "ORDER")
    if cancelled_monotonic_ns < reservation["reserved_monotonic_ns"]:
        _fail("cancelled_monotonic_ns", "ORDER")
    _enum(v["reason"], "reason", _CANCELLATION_REASONS)
    v["before"], v["current"] = _validate_cancellation_before_current(v, reservation)
    _equal(
        v["original_target_observation_digest"],
        reservation["target_observation_digest"],
        "original_target_observation_digest",
    )
    prepared = reservation["prepared_payload"]
    reason = v["reason"]
    if reason == "PREPARED_TOKEN_EXPIRED":
        if not (
            cancelled_at_ms >= prepared["expires_at_ms"]
            or cancelled_monotonic_ns >= prepared["expires_monotonic_ns"]
        ):
            _fail("reason", "PREDICATE")
    if reason == "GRANT_EXPIRED":
        if cancelled_at_ms < approval["grant"]["expires_at_ms"]:
            _fail("reason", "PREDICATE")
    if reason == "PRECONDITIONS_CHANGED":
        if (
            v["current_precondition_digest"]
            == reservation["expected_precondition_digest"]
        ):
            _fail("reason", "PREDICATE")
    if reason == "TARGET_OBSERVATION_CHANGED":
        if (
            v["current_target_observation_digest"]
            == reservation["target_observation_digest"]
        ):
            _fail("reason", "PREDICATE")
    return _freeze(v)


def validate_release_publication_intent(
    value: Any, *, expected_start: Any
) -> ReleaseRecord:
    """Validate a detached operation-local plan; never allocate or authorize.

    The supplied context is structural evidence, not publisher custody.
    """
    start = _object(
        expected_start,
        _PUBLICATION_START_FIELDS,
        "expected_start",
        _PUBLICATION_START_SCHEMA,
    )
    _request_ref(start["operation_key"])
    for key in ("request_fingerprint", "root_qualification_digest"):
        _digest(start[key], key)
        if start[key] == "0" * 64:
            _fail(key, "ZERO")
    start_actuator_generation = _integer(
        start["actuator_generation"], "actuator_generation", 1
    )
    _integer(start["started_at_ms"], "started_at_ms")
    original_deadline = _integer(
        start["start_deadline_monotonic_ns"], "start_deadline_monotonic_ns", 1
    )
    start["before"] = _validate_installed_identity(start["before"], "before")
    for key, reference in (("broker_source_commit", "release_commit"),
                           ("broker_source_tree", "release_tree")):
        _equal(start["before"][key], start["before"][reference], "before." + key)

    v = _object(value, _PUBLICATION_INTENT_FIELDS, "intent", _PUBLICATION_INTENT_SCHEMA)
    _equal(v["operation_key"], start["operation_key"], "operation_key")
    _equal(
        v["request_fingerprint"], start["request_fingerprint"], "request_fingerprint"
    )
    _equal(
        v["root_qualification_digest"],
        start["root_qualification_digest"],
        "root_qualification_digest",
    )
    for key in ("request_fingerprint", "root_qualification_digest", "before_digest"):
        _digest(v[key], key)
    _equal(v["before_digest"], _hash(start["before"]), "before_digest")

    declared_start_generation = _integer(
        v["start_actuator_generation"], "start_actuator_generation", 1
    )
    target_generation = _integer(
        v["target_actuator_generation"], "target_actuator_generation", 1
    )
    rollback_generation = _integer(
        v["rollback_actuator_generation"], "rollback_actuator_generation", 1
    )
    if (
        declared_start_generation != start_actuator_generation
        or target_generation != declared_start_generation + 1
        or rollback_generation != declared_start_generation + 2
        or rollback_generation > _MAX_INT
    ):
        _fail("start_actuator_generation", "SEQUENCE")
    _equal(
        v["original_deadline_monotonic_ns"],
        original_deadline,
        "original_deadline_monotonic_ns",
    )
    intent_at_ms = _integer(v["intent_at_ms"], "intent_at_ms")
    _integer(
        v["intent_monotonic_ns"], "intent_monotonic_ns", 1, original_deadline - 1
    )
    if intent_at_ms < start["started_at_ms"]:
        _fail("intent_at_ms", "ORDER")
    _integer(v["intent_journal_generation"], "intent_journal_generation", 2, 2)
    return _freeze(v)


def validate_release_recovery_origin(
    value: Any, *, expected_intent: Any, expected_start: Any
) -> ReleaseRecord:
    """Validate the durable publication phase from which recovery began."""
    intent = validate_release_publication_intent(
        expected_intent, expected_start=expected_start
    )
    v = _object(
        value, _RECOVERY_ORIGIN_FIELDS, "origin", _RECOVERY_ORIGIN_SCHEMA
    )
    _equal(v["operation_key"], intent["operation_key"], "operation_key")
    _equal(
        v["request_fingerprint"],
        intent["request_fingerprint"],
        "request_fingerprint",
    )
    _digest(v["publication_intent_digest"], "publication_intent_digest")
    _equal(v["publication_intent_digest"], _hash(intent), "publication_intent_digest")
    from_state = _enum(v["from_state"], "from_state", tuple(_PUBLICATION_PHASES))
    expected_generation = _PUBLICATION_PHASES[from_state]
    _integer(
        v["from_journal_generation"],
        "from_journal_generation",
        expected_generation,
        expected_generation,
    )
    return _freeze(v)
