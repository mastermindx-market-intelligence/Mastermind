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
