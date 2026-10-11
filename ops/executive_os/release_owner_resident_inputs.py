"""Pure, disarmed compilers for release-owner resident input documents.

The functions in this module perform no file, environment, network, clock-source
selection, key-generation, registration, staging, service, or host mutation.
They compile only caller-supplied nonsecret evidence.  In particular, an issuer
binding receipt must already exist and a later filesystem wrapper must pass the
Codex attestation receipt through ``load_codex_attestation_receipt`` against the
installed executable before supplying its exact bytes here.
"""

from __future__ import annotations

from collections.abc import Mapping
import calendar
from datetime import datetime
import hashlib
import json
import math
import re
import time
from typing import Any
from uuid import UUID

from control_plane import executive_authority as authority
from control_plane.executive_authority import ReleaseControllerPolicy
from control_plane.executive_privileged_broker import PrivilegedBrokerConfig
from control_plane.executive_release_contract import (
    ReleaseContractError,
    canonical_release_bytes,
    parse_release_json,
    validate_release_policy,
)

__all__ = [
    "ReleaseOwnerInputError",
    "canonical_file_bytes",
    "compile_registration",
    "compile_empty_registry",
    "validate_issuer_binding_receipt",
    "compile_installed_evidence",
    "decode_installed_evidence_v2",
]

_MAX_FILE_BYTES = 16 * 1024
_MAX_INT = (1 << 63) - 1
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,159}", re.ASCII)
_HEX40 = re.compile(r"[0-9a-f]{40}", re.ASCII)
_HEX64 = re.compile(r"[0-9a-f]{64}", re.ASCII)
_REGISTRATION_FIELDS = frozenset(
    {
        "schema",
        "owner_installation_id",
        "target_ref",
        "key_id",
        "trust_generation",
        "app_generation",
        "registration_generation",
        "enabled",
    }
)
_ISSUER_FIELDS = frozenset(
    {
        "schema",
        "owner_installation_id",
        "target_ref",
        "release_commit",
        "release_tree",
        "boot_id",
        "role",
        "control_uid",
        "app_peer_uid",
        "policy",
        "binding_evidence_digest",
        "observed_at",
    }
)
_EVIDENCE_V2_SCHEMA = "mastermind.executive_release_owner_installed_evidence/v2"
_EVIDENCE_V1_FIELDS = frozenset(
    {
        "schema",
        "owner_installation_id",
        "target_ref",
        "registration_generation",
        "release_commit",
        "release_tree",
        "control_config_digest",
        "broker_config_digest",
        "installed_configuration_digest",
        "python_runtime_provenance_digest",
        "provider_binary_attestation_digest",
        "provider_attestation_role",
        "provider_attestation_boot_id",
        "issuer_binding_digest",
        "issuer_binding_owner_installation_id",
        "issuer_binding_role",
        "issuer_binding_release_commit",
        "issuer_binding_boot_id",
        "issuer_binding_observed_at",
        "provider_attestation_observed_at",
        "production_disarming",
    }
)
_EVIDENCE_V2_ADDITIONS = frozenset(
    {
        "actuator_generation",
        "before",
        "publication_operation_key",
        "predecessor_evidence_digest",
    }
)
_EVIDENCE_V2_FIELDS = _EVIDENCE_V1_FIELDS | _EVIDENCE_V2_ADDITIONS
_BEFORE_FIELDS = frozenset(
    {
        "release_commit",
        "release_tree",
        "installed_manifest_digest",
        "configuration_digest",
        "broker_source_commit",
        "broker_source_tree",
        "broker_binary_digest",
        "service_generation_digests",
    }
)
_SERVICE_ROLES = ("control", "worker", "relay", "gateway", "broker")
_DISARMING_FIELDS = frozenset(
    {
        "schema",
        "commit_prepared_release_transition",
        "installer_arming",
        "worker_start",
    }
)
_EXPECTED_DISARMING = {
    "schema": "mastermind.executive_release_disarming/v1",
    "commit_prepared_release_transition": False,
    "installer_arming": False,
    "worker_start": False,
}


class ReleaseOwnerInputError(ValueError):
    """A closed diagnostic that never echoes rejected evidence."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _fail(code: str) -> None:
    raise ReleaseOwnerInputError(code)


def _closed_text_tree(value: Any) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if type(key) is not str:
                _fail("DOCUMENT_INVALID")
            _closed_text_tree(key)
            _closed_text_tree(item)
        return
    if type(value) in (list, tuple):
        for item in value:
            _closed_text_tree(item)
        return
    if type(value) is str and any(not 32 <= ord(char) <= 126 for char in value):
        _fail("TEXT_INVALID")


def _canonical_mapping(document: Mapping[str, object], code: str) -> dict[str, Any]:
    if not isinstance(document, Mapping):
        _fail(code)
    _closed_text_tree(document)
    try:
        return parse_release_json(canonical_release_bytes(document)).to_dict()
    except (ReleaseContractError, UnicodeError, ValueError, TypeError):
        _fail(code)


def canonical_file_bytes(document: Mapping[str, object]) -> bytes:
    """Return exact canonical release JSON plus one LF, bounded as a file."""

    detached = _canonical_mapping(document, "DOCUMENT_INVALID")
    try:
        raw = canonical_release_bytes(detached) + b"\n"
    except ReleaseContractError:
        _fail("DOCUMENT_INVALID")
    if len(raw) > _MAX_FILE_BYTES:
        _fail("DOCUMENT_SIZE")
    return raw


def _uuid(value: object, code: str) -> str:
    if type(value) is not str or len(value) != 36:
        _fail(code)
    try:
        parsed = UUID(value)
    except (ValueError, AttributeError, TypeError):
        _fail(code)
    if parsed.int == 0 or str(parsed) != value:
        _fail(code)
    return value


def _identifier(value: object, code: str) -> str:
    if type(value) is not str or _ID.fullmatch(value) is None:
        _fail(code)
    return value


def _hex(value: object, pattern: re.Pattern[str], code: str) -> str:
    if (
        type(value) is not str
        or pattern.fullmatch(value) is None
        or set(value) == {"0"}
    ):
        _fail(code)
    return value


def _positive_integer(value: object, code: str) -> int:
    if type(value) is not int or not 1 <= value <= _MAX_INT:
        _fail(code)
    return value


def _fixed_timestamp(value: object, code: str) -> str:
    if type(value) is not str or len(value) != 20:
        _fail(code)
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        _fail(code)
    if parsed.strftime("%Y-%m-%dT%H:%M:%SZ") != value:
        _fail(code)
    return value


def _validate_installed_evidence_v2(document: Mapping[str, Any]) -> dict[str, Any]:
    """Validate inherited and v2 fields; return a canonical detached mapping."""

    if not isinstance(document, Mapping) or set(document) != _EVIDENCE_V2_FIELDS:
        _fail("EVIDENCE_V2_FIELDS")
    if document["schema"] != _EVIDENCE_V2_SCHEMA:
        _fail("EVIDENCE_V2_SCHEMA")
    _uuid(document["owner_installation_id"], "EVIDENCE_IDENTITY")
    _hex(document["target_ref"], _HEX64, "EVIDENCE_TARGET")
    _positive_integer(
        document["registration_generation"], "EVIDENCE_REGISTRATION_GENERATION"
    )
    release_commit = _hex(document["release_commit"], _HEX40, "EVIDENCE_RELEASE")
    release_tree = _hex(document["release_tree"], _HEX40, "EVIDENCE_RELEASE")
    _hex(document["control_config_digest"], _HEX64, "EVIDENCE_DIGEST")
    _hex(document["broker_config_digest"], _HEX64, "EVIDENCE_DIGEST")
    _hex(
        document["installed_configuration_digest"], _HEX64, "EVIDENCE_DIGEST"
    )
    _hex(document["python_runtime_provenance_digest"], _HEX64, "EVIDENCE_DIGEST")
    _hex(
        document["provider_binary_attestation_digest"], _HEX64, "EVIDENCE_DIGEST"
    )
    if document["provider_attestation_role"] != "codex_worker":
        _fail("EVIDENCE_ATTESTATION_ROLE")
    _uuid(document["provider_attestation_boot_id"], "EVIDENCE_BOOT")
    _hex(document["issuer_binding_digest"], _HEX64, "EVIDENCE_DIGEST")
    _uuid(
        document["issuer_binding_owner_installation_id"], "EVIDENCE_IDENTITY"
    )
    if document["issuer_binding_owner_installation_id"] != document["owner_installation_id"]:
        _fail("EVIDENCE_ISSUER_MISMATCH")
    if document["issuer_binding_role"] != "control":
        _fail("EVIDENCE_ISSUER_ROLE")
    if document["issuer_binding_release_commit"] != release_commit:
        _fail("EVIDENCE_ISSUER_MISMATCH")
    if document["issuer_binding_boot_id"] != document["provider_attestation_boot_id"]:
        _fail("EVIDENCE_BOOT_MISMATCH")
    _fixed_timestamp(
        document["issuer_binding_observed_at"],
        code="EVIDENCE_TIMESTAMP",
    )
    _fixed_timestamp(
        document["provider_attestation_observed_at"],
        code="EVIDENCE_TIMESTAMP",
    )
    disarming = document["production_disarming"]
    if not isinstance(disarming, Mapping) or set(disarming) != _DISARMING_FIELDS:
        _fail("EVIDENCE_DISARMING_FIELDS")
    if any(disarming[name] is not False for name in _DISARMING_FIELDS - {"schema"}):
        _fail("EVIDENCE_NOT_DISARMED")
    if _canonical_mapping(disarming, "EVIDENCE_DISARMING_FIELDS") != _EXPECTED_DISARMING:
        _fail("EVIDENCE_DISARMING_FIELDS")

    generation = document["actuator_generation"]
    if type(generation) is not int or not 1 <= generation <= _MAX_INT:
        _fail("EVIDENCE_ACTUATOR_GENERATION")
    _hex(
        document["predecessor_evidence_digest"], _HEX64, "EVIDENCE_PREDECESSOR"
    )
    if type(document["publication_operation_key"]) is not str:
        _fail("EVIDENCE_OPERATION_KEY")
    _identifier(document["publication_operation_key"], "EVIDENCE_OPERATION_KEY")
    before = document["before"]
    if not isinstance(before, Mapping) or set(before) != _BEFORE_FIELDS:
        _fail("EVIDENCE_BEFORE_FIELDS")
    _canonical_mapping(before, "EVIDENCE_BEFORE_FIELDS")
    if before["release_commit"] != release_commit:
        _fail("EVIDENCE_BEFORE_RELEASE_MISMATCH")
    if before["release_tree"] != release_tree:
        _fail("EVIDENCE_BEFORE_RELEASE_MISMATCH")
    if before["broker_source_commit"] != release_commit:
        _fail("EVIDENCE_BEFORE_RELEASE_MISMATCH")
    if before["broker_source_tree"] != release_tree:
        _fail("EVIDENCE_BEFORE_RELEASE_MISMATCH")
    for name in (
        "installed_manifest_digest",
        "configuration_digest",
        "broker_binary_digest",
    ):
        _hex(before[name], _HEX64, "EVIDENCE_BEFORE_DIGEST")
    if before["configuration_digest"] != document["installed_configuration_digest"]:
        _fail("EVIDENCE_CONFIG_JOIN")
    roles = before["service_generation_digests"]
    if not isinstance(roles, Mapping) or set(roles) != set(_SERVICE_ROLES):
        _fail("EVIDENCE_SERVICE_FIELDS")
    _canonical_mapping(roles, "EVIDENCE_SERVICE_FIELDS")
    for role in _SERVICE_ROLES:
        _hex(roles[role], _HEX64, "EVIDENCE_SERVICE_DIGEST")
    return _canonical_mapping(document, "EVIDENCE_V2_FIELDS")


def _validate_registration(document: Mapping[str, object]) -> dict[str, Any]:
    if not isinstance(document, Mapping) or set(document) != _REGISTRATION_FIELDS:
        _fail("REGISTRATION_FIELDS")
    if document["schema"] != "mastermind.executive_release_owner_registration/v1":
        _fail("REGISTRATION_SCHEMA")
    _uuid(document["owner_installation_id"], "REGISTRATION_OWNER")
    _hex(document["target_ref"], _HEX64, "REGISTRATION_TARGET")
    _identifier(document["key_id"], "REGISTRATION_KEY")
    for field in (
        "trust_generation",
        "app_generation",
        "registration_generation",
    ):
        _positive_integer(document[field], "REGISTRATION_GENERATION")
    if type(document["enabled"]) is not bool or document["enabled"]:
        _fail("REGISTRATION_ARMED")
    return _canonical_mapping(document, "REGISTRATION_INVALID")


def compile_registration(
    *,
    owner_installation_id: str,
    target_ref: str,
    key_id: str,
    trust_generation: int,
    app_generation: int,
    registration_generation: int,
    enabled: bool = False,
) -> bytes:
    """Compile the initial disabled registration; this API cannot enable it."""

    value = {
        "schema": "mastermind.executive_release_owner_registration/v1",
        "owner_installation_id": owner_installation_id,
        "target_ref": target_ref,
        "key_id": key_id,
        "trust_generation": trust_generation,
        "app_generation": app_generation,
        "registration_generation": registration_generation,
        "enabled": enabled,
    }
    return canonical_file_bytes(_validate_registration(value))


def compile_empty_registry(
    *, registration_generation: int, registry_generation: int
) -> bytes:
    """Compile an exact empty staged-transition registry."""

    _positive_integer(registration_generation, "REGISTRY_GENERATION")
    _positive_integer(registry_generation, "REGISTRY_GENERATION")
    return canonical_file_bytes(
        {
            "schema": "mastermind.executive_release_owner_staged_registry/v1",
            "registration_generation": registration_generation,
            "registry_generation": registry_generation,
            "transitions": [],
        }
    )


def _policy_mapping(policy: ReleaseControllerPolicy) -> dict[str, Any]:
    if type(policy) is not ReleaseControllerPolicy:
        _fail("POLICY_INVALID")
    try:
        parsed = authority._parse_release_controller_policy(policy._raw)
        reparsed_policy = ReleaseControllerPolicy.from_bytes(policy._raw)
        reparsed = authority._parse_release_controller_policy(reparsed_policy._raw)
        if parsed is None or reparsed is None:
            _fail("POLICY_UNCONFIGURED")
        left = canonical_release_bytes(parsed)
        right = canonical_release_bytes(reparsed)
        if left != right or policy.sha256 != reparsed_policy.sha256:
            _fail("POLICY_CHANGED")
        return validate_release_policy(parsed).to_dict()
    except ReleaseOwnerInputError:
        raise
    except Exception:
        _fail("POLICY_INVALID")


def _timestamp(value: object, *, now_seconds: int | None, code: str) -> str:
    if type(value) is not str or len(value) != 20:
        _fail(code)
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        _fail(code)
    if parsed.strftime("%Y-%m-%dT%H:%M:%SZ") != value:
        _fail(code)
    observed = calendar.timegm(parsed.utctimetuple())
    now = int(time.time()) if now_seconds is None else now_seconds
    if type(now) is not int or now < 0 or observed > now:
        _fail(code)
    return value


def validate_issuer_binding_receipt(
    receipt: Mapping[str, object],
    *,
    owner_installation_id: str,
    target_ref: str,
    release_commit: str,
    release_tree: str,
    boot_id: str,
    policy: ReleaseControllerPolicy,
    control_uid: int = 450,
    app_peer_uid: int,
    _now_seconds: int | None = None,
) -> bytes:
    """Validate and canonicalize supplied issuer evidence; never manufacture it."""

    value = _canonical_mapping(receipt, "ISSUER_BINDING_INVALID")
    if set(value) != _ISSUER_FIELDS:
        _fail("ISSUER_BINDING_FIELDS")
    if value["schema"] != "mastermind.executive_release_issuer_binding/v1":
        _fail("ISSUER_BINDING_SCHEMA")
    _uuid(owner_installation_id, "ISSUER_OWNER")
    _hex(target_ref, _HEX64, "ISSUER_TARGET")
    _hex(release_commit, _HEX40, "ISSUER_RELEASE")
    _hex(release_tree, _HEX40, "ISSUER_RELEASE")
    _uuid(boot_id, "ISSUER_BOOT")
    _positive_integer(control_uid, "ISSUER_UID")
    _positive_integer(app_peer_uid, "ISSUER_UID")
    if control_uid != 450 or control_uid == app_peer_uid:
        _fail("ISSUER_UID")
    expected = {
        "owner_installation_id": owner_installation_id,
        "target_ref": target_ref,
        "release_commit": release_commit,
        "release_tree": release_tree,
        "boot_id": boot_id,
        "role": "control",
        "control_uid": control_uid,
        "app_peer_uid": app_peer_uid,
    }
    if any(
        type(value[field]) is not type(expected_value)
        or value[field] != expected_value
        for field, expected_value in expected.items()
    ):
        _fail("ISSUER_BINDING_MISMATCH")
    policy_mapping = _policy_mapping(policy)
    try:
        supplied_policy = validate_release_policy(value["policy"]).to_dict()
    except Exception:
        _fail("ISSUER_POLICY")
    if canonical_release_bytes(supplied_policy) != canonical_release_bytes(policy_mapping):
        _fail("ISSUER_POLICY")
    value["policy"] = policy_mapping
    _hex(value["binding_evidence_digest"], _HEX64, "ISSUER_EVIDENCE")
    _timestamp(value["observed_at"], now_seconds=_now_seconds, code="ISSUER_TIME")
    return canonical_file_bytes(value)


def _raw_bytes(value: object, code: str) -> bytes:
    if type(value) is not bytes or not value:
        _fail(code)
    return value


def _strict_json(raw: bytes, code: str) -> dict[str, Any]:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                _fail(code)
            result[key] = value
        return result

    def constant(_: str) -> None:
        _fail(code)

    def finite_float(text: str) -> float:
        value = float(text)
        if not math.isfinite(value):
            _fail(code)
        return value

    try:
        value = json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=pairs,
            parse_float=finite_float,
            parse_constant=constant,
        )
    except ReleaseOwnerInputError:
        raise
    except (UnicodeError, json.JSONDecodeError, RecursionError):
        _fail(code)
    if not isinstance(value, dict):
        _fail(code)
    return value


def compile_installed_evidence(
    *,
    registration: Mapping[str, object],
    release_commit: str,
    release_tree: str,
    control_config_bytes: bytes,
    broker_config_bytes: bytes,
    authority_map_bytes: bytes,
    python_runtime_provenance_digest: str,
    provider_attestation_bytes: bytes,
    provider_attestation_observed_at: str,
    issuer_binding_receipt: Mapping[str, object],
    issuer_binding_observed_at: str,
    boot_id: str,
    policy: ReleaseControllerPolicy,
    app_peer_uid: int,
    physical_evidence: Mapping[str, object] | None = None,
    _now_seconds: int | None = None,
) -> bytes:
    """Compile disarmed installed evidence from independently supplied inputs."""

    registration_value = _validate_registration(registration)
    release_commit = _hex(release_commit, _HEX40, "INSTALLED_RELEASE")
    release_tree = _hex(release_tree, _HEX40, "INSTALLED_RELEASE")
    _uuid(boot_id, "INSTALLED_BOOT")
    _positive_integer(app_peer_uid, "INSTALLED_UID")
    provenance = _hex(
        python_runtime_provenance_digest, _HEX64, "INSTALLED_PROVENANCE"
    )
    control = _raw_bytes(control_config_bytes, "CONTROL_CONFIG")
    broker = _raw_bytes(broker_config_bytes, "BROKER_CONFIG")
    authority_map = _raw_bytes(authority_map_bytes, "AUTHORITY_MAP")
    provider = _raw_bytes(provider_attestation_bytes, "PROVIDER_ATTESTATION")
    if type(policy) is not ReleaseControllerPolicy or authority_map != policy._raw:
        _fail("AUTHORITY_POLICY_MISMATCH")
    control_document = _strict_json(control, "CONTROL_CONFIG")
    if (
        control_document.get("proof_base_sha") != release_commit
        or control_document.get("python_runtime_provenance_digest") != provenance
        or type(control_document.get("control_uid")) is not int
        or control_document["control_uid"] != 450
    ):
        _fail("CONTROL_CONFIG_MISMATCH")
    broker_document = _strict_json(broker, "BROKER_CONFIG")
    try:
        broker_config = PrivilegedBrokerConfig.from_mapping(broker_document)
    except (TypeError, ValueError):
        raise ReleaseOwnerInputError("BROKER_CONFIG_MISMATCH") from None
    expected_release_root = (
        "/Library/Application Support/MastermindExecutive/releases/" + release_commit
    )
    if str(broker_config.release_root) != expected_release_root:
        _fail("BROKER_CONFIG_MISMATCH")
    provider_time = _timestamp(
        provider_attestation_observed_at,
        now_seconds=_now_seconds,
        code="PROVIDER_TIME",
    )
    if not isinstance(issuer_binding_receipt, Mapping):
        _fail("ISSUER_BINDING_INVALID")
    if issuer_binding_observed_at != issuer_binding_receipt.get("observed_at"):
        _fail("ISSUER_TIME_MISMATCH")
    issuer_bytes = validate_issuer_binding_receipt(
        issuer_binding_receipt,
        owner_installation_id=registration_value["owner_installation_id"],
        target_ref=registration_value["target_ref"],
        release_commit=release_commit,
        release_tree=release_tree,
        boot_id=boot_id,
        policy=policy,
        app_peer_uid=app_peer_uid,
        _now_seconds=_now_seconds,
    )
    issuer_value = parse_release_json(issuer_bytes[:-1]).to_dict()
    files = [
        {"path": "config/control.json", "sha256": hashlib.sha256(control).hexdigest()},
        {"path": "config/authority_map.yml", "sha256": hashlib.sha256(authority_map).hexdigest()},
        {"path": "config/privileged-broker.json", "sha256": hashlib.sha256(broker).hexdigest()},
    ]
    configuration_digest = hashlib.sha256(
        canonical_release_bytes(
            {
                "schema": "mastermind.executive_installed_configuration_set/v1",
                "files": files,
            }
        )
    ).hexdigest()
    disarming = {
        "schema": "mastermind.executive_release_disarming/v1",
        "commit_prepared_release_transition": False,
        "installer_arming": False,
        "worker_start": False,
    }
    document = {
        "schema": "mastermind.executive_release_owner_installed_evidence/v1",
        "owner_installation_id": registration_value["owner_installation_id"],
        "target_ref": registration_value["target_ref"],
        "registration_generation": registration_value["registration_generation"],
        "release_commit": release_commit,
        "release_tree": release_tree,
        "control_config_digest": hashlib.sha256(control).hexdigest(),
        "broker_config_digest": hashlib.sha256(broker).hexdigest(),
        "installed_configuration_digest": configuration_digest,
        "python_runtime_provenance_digest": provenance,
        "provider_binary_attestation_digest": hashlib.sha256(provider).hexdigest(),
        "provider_attestation_role": "codex_worker",
        "provider_attestation_boot_id": boot_id,
        "issuer_binding_digest": hashlib.sha256(issuer_bytes).hexdigest(),
        "issuer_binding_owner_installation_id": issuer_value["owner_installation_id"],
        "issuer_binding_role": issuer_value["role"],
        "issuer_binding_release_commit": issuer_value["release_commit"],
        "issuer_binding_boot_id": issuer_value["boot_id"],
        "issuer_binding_observed_at": issuer_value["observed_at"],
        "provider_attestation_observed_at": provider_time,
        "production_disarming": disarming,
    }
    if physical_evidence is None:
        return canonical_file_bytes(document)
    if not isinstance(physical_evidence, Mapping) or set(physical_evidence) != _EVIDENCE_V2_ADDITIONS:
        _fail("EVIDENCE_V2_ADDITIONS")
    document["schema"] = _EVIDENCE_V2_SCHEMA
    document.update(physical_evidence)
    return canonical_file_bytes(_validate_installed_evidence_v2(document))


def decode_installed_evidence_v2(raw: bytes) -> dict[str, Any]:
    """Decode canonical exact v2 evidence into a deep detached mapping."""

    if type(raw) is not bytes or not 1 <= len(raw) <= _MAX_FILE_BYTES:
        _fail("EVIDENCE_V2_BYTES")
    try:
        decoded = _strict_json(raw, "EVIDENCE_V2_BYTES")
    except ReleaseOwnerInputError:
        _fail("EVIDENCE_V2_BYTES")
    validated = _validate_installed_evidence_v2(decoded)
    try:
        encoded = canonical_file_bytes(validated)
    except ReleaseOwnerInputError:
        _fail("EVIDENCE_V2_BYTES")
    if raw != encoded:
        _fail("EVIDENCE_V2_NONCANONICAL")
    return validated
