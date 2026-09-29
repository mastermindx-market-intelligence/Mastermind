"""Pure publication plans for the disarmed Executive release owner.

This module does not inspect or mutate a host.  It compiles already supplied
resident and staged inputs into immutable metadata and detached payload bytes.
The returned predicates are requirements for a later privileged publisher;
they are not claims that those requirements have been observed or satisfied.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
import hashlib
from typing import Any

from control_plane.executive_authority import ReleaseControllerPolicy
from control_plane.executive_release_contract import (
    ReleaseContractError,
    canonical_release_bytes,
    parse_release_json,
)
from ops.executive_os.executive_mcp_entry import validate_document as validate_mcp_config
from ops.executive_os.release_owner_resident_inputs import (
    ReleaseOwnerInputError,
    canonical_file_bytes,
    compile_empty_registry,
    compile_installed_evidence,
    compile_registration,
    validate_issuer_binding_receipt,
)
from ops.executive_os.release_owner_staged_inputs import (
    StagedInputError,
    StagedInputs,
    compile_staged_inputs,
)

__all__ = [
    "PublicationPlanError",
    "PublicationFile",
    "PublicationPayload",
    "PublicationPlan",
    "compile_resident_publication_plan",
    "compile_staged_publication_plan",
]

_CONFIG_ROOT = "/Library/Application Support/MastermindExecutive/config"
_REGISTRATION_PATH = _CONFIG_ROOT + "/release-owner-registration.json"
_REGISTRY_PATH = _CONFIG_ROOT + "/release-owner-staged-transitions.json"
_EVIDENCE_PATH = _CONFIG_ROOT + "/release-owner-installed-evidence.json"
_STAGING_ROOT = "/Library/Application Support/MastermindExecutive/release-staging"
_RESIDENT_PATHS = (
    _REGISTRATION_PATH,
    _REGISTRY_PATH,
    _EVIDENCE_PATH,
)
_STAGED_NAMES = (
    "artifact-metadata.json",
    "compatibility-proof.json",
    "configuration-transition.json",
    "effect.json",
    "installer-profile.json",
    "preconditions-template.json",
    "preservation-plan.json",
    "release-artifact.bin",
    "rollback-evidence.json",
    "source-proof.json",
)
_ROOT_UID = 0
_WHEEL_GID = 0
_FILE_MODE = 0o400
_STAGING_DIRECTORY_MODE = 0o500


class PublicationPlanError(ValueError):
    """Closed diagnostic; rejected values are never included in its message."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _fail(code: str) -> None:
    raise PublicationPlanError(code)


@dataclass(frozen=True)
class PublicationFile:
    """Public metadata for one payload; it deliberately contains no bytes."""

    path: str
    length: int
    sha256: str
    mode: int
    uid: int
    gid: int


@dataclass(frozen=True, repr=False)
class PublicationPayload:
    """Detached immutable bytes; repr must not become a payload logging path."""

    path: str
    data: bytes = field(repr=False)


@dataclass(frozen=True)
class PublicationPlan:
    """One deterministic, permanently disarmed publication plan."""

    kind: str
    directory: str
    directory_mode: int | None
    files: tuple[PublicationFile, ...]
    predicates: tuple[str, ...]
    manifest_bytes: bytes = field(repr=False)
    manifest_sha256: str
    payloads: tuple[PublicationPayload, ...] = field(repr=False)


def _bytes(value: object, code: str) -> bytes:
    if type(value) is bytes:
        return bytes(value)
    if type(value) in (bytearray, memoryview):
        return bytes(value)
    _fail(code)


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical_document(raw: object, code: str) -> tuple[dict[str, Any], bytes]:
    payload = _bytes(raw, code)
    wire = payload[:-1] if payload.endswith(b"\n") else payload
    if not wire or b"\n" in wire:
        _fail(code)
    try:
        document = parse_release_json(wire).to_dict()
    except (ReleaseContractError, UnicodeError, ValueError, TypeError):
        _fail(code)
    expected = canonical_release_bytes(document)
    if payload not in (expected, expected + b"\n"):
        _fail(code)
    return document, payload


def _typed_equal(left: object, right: object) -> bool:
    return type(left) is type(right) and left == right


def _specs(
    payloads: tuple[PublicationPayload, ...], *, mode: int
) -> tuple[PublicationFile, ...]:
    return tuple(
        PublicationFile(
            path=payload.path,
            length=len(payload.data),
            sha256=_sha(payload.data),
            mode=mode,
            uid=_ROOT_UID,
            gid=_WHEEL_GID,
        )
        for payload in payloads
    )


def _file_inventory(files: tuple[PublicationFile, ...]) -> list[dict[str, object]]:
    return [
        {
            "path": item.path,
            "length": item.length,
            "sha256": item.sha256,
            "mode": item.mode,
            "uid": item.uid,
            "gid": item.gid,
        }
        for item in files
    ]


def _plan(
    *,
    kind: str,
    directory: str,
    directory_mode: int | None,
    payloads: tuple[PublicationPayload, ...],
    predicates: tuple[str, ...],
    context: Mapping[str, object],
) -> PublicationPlan:
    files = _specs(payloads, mode=_FILE_MODE)
    manifest: dict[str, object] = {
        "schema": "mastermind.executive_release_owner_publication_plan/v1",
        "kind": kind,
        "directory": directory,
        "directory_uid": _ROOT_UID,
        "directory_gid": _WHEEL_GID,
        "files": _file_inventory(files),
        "predicates": list(predicates),
        "context": dict(context),
        "evidence_authentication": "UNAUTHENTICATED_UNTIL_INSTALLED_CONSUMER_REDERIVES",
        "production_disarming": {
            "commit_prepared_release_transition": False,
            "installer_arming": False,
            "worker_start": False,
        },
    }
    if directory_mode is not None:
        manifest["directory_mode"] = directory_mode
    try:
        manifest_bytes = canonical_file_bytes(manifest)
    except ReleaseOwnerInputError as error:
        raise PublicationPlanError(error.code) from None
    return PublicationPlan(
        kind=kind,
        directory=directory,
        directory_mode=directory_mode,
        files=files,
        predicates=predicates,
        manifest_bytes=manifest_bytes,
        manifest_sha256=_sha(manifest_bytes),
        payloads=payloads,
    )


def _resident_preimage(
    *,
    expected_registration: bytes,
    expected_registry: bytes,
    expected_evidence: bytes,
    existing_registration_bytes: object | None,
    existing_registry_bytes: object | None,
    existing_installed_evidence_bytes: object | None,
) -> str:
    values = (
        existing_registration_bytes,
        existing_registry_bytes,
        existing_installed_evidence_bytes,
    )
    if all(value is None for value in values):
        return "ABSENT"
    if any(value is None for value in values):
        _fail("RESIDENT_PREIMAGE_PARTIAL")
    registration, registration_raw = _canonical_document(
        existing_registration_bytes, "REGISTRATION_PREIMAGE_INVALID"
    )
    registry, registry_raw = _canonical_document(
        existing_registry_bytes, "REGISTRY_PREIMAGE_INVALID"
    )
    evidence, evidence_raw = _canonical_document(
        existing_installed_evidence_bytes, "EVIDENCE_PREIMAGE_INVALID"
    )
    expected_registration_document, _ = _canonical_document(
        expected_registration, "REGISTRATION_INVALID"
    )
    expected_evidence_document, _ = _canonical_document(
        expected_evidence, "EVIDENCE_INVALID"
    )
    if registration.get("enabled") is not False:
        _fail("REGISTRATION_ACTIVE")
    for name in ("owner_installation_id", "target_ref"):
        if not _typed_equal(registration.get(name), expected_registration_document[name]):
            _fail("IDENTITY_ROTATION_UNSUPPORTED")
        if not _typed_equal(evidence.get(name), expected_evidence_document[name]):
            _fail("IDENTITY_ROTATION_UNSUPPORTED")
    transitions = registry.get("transitions")
    if type(transitions) is not list:
        _fail("REGISTRY_PREIMAGE_INVALID")
    if transitions:
        _fail("REGISTRY_NOT_EMPTY")
    if registration_raw != expected_registration:
        _fail("REGISTRATION_PREIMAGE_MISMATCH")
    if registry_raw != expected_registry:
        _fail("REGISTRY_PREIMAGE_MISMATCH")
    if evidence_raw != expected_evidence:
        _fail("EVIDENCE_PREIMAGE_MISMATCH")
    return "EXACT"


def compile_resident_publication_plan(
    *,
    owner_installation_id: str,
    target_ref: str,
    key_id: str,
    trust_generation: int,
    app_generation: int,
    registration_generation: int,
    registry_generation: int,
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
    mcp_config_bytes: bytes,
    requested_mcp_profile: str,
    now_seconds: int,
    existing_registration_bytes: bytes | None = None,
    existing_registry_bytes: bytes | None = None,
    existing_installed_evidence_bytes: bytes | None = None,
) -> PublicationPlan:
    """Compile the three resident documents without publishing or enabling them."""

    control = _bytes(control_config_bytes, "CONTROL_CONFIG")
    broker = _bytes(broker_config_bytes, "BROKER_CONFIG")
    authority_map = _bytes(authority_map_bytes, "AUTHORITY_MAP")
    provider = _bytes(provider_attestation_bytes, "PROVIDER_ATTESTATION")
    mcp, mcp_raw = _canonical_document(mcp_config_bytes, "MCP_CONFIG_INVALID")
    mcp_projection = dict(mcp)
    try:
        validated_mcp = validate_mcp_config(mcp_projection)
    except Exception:
        _fail("MCP_CONFIG_INVALID")
    if validated_mcp is not mcp_projection or validated_mcp != mcp:
        _fail("MCP_CONFIG_INVALID")
    active_profile = mcp.get("executive_mcp_profile", "legacy")
    if type(active_profile) is not str or type(requested_mcp_profile) is not str:
        _fail("MCP_PROFILE_INVALID")
    if requested_mcp_profile != active_profile:
        _fail("COEXISTENCE_UNPROVEN")
    policies = mcp.get("policies")
    if not isinstance(policies, Mapping):
        _fail("MCP_POLICIES_INVALID")
    try:
        mcp_policies_digest = _sha(canonical_release_bytes(policies))
    except ReleaseContractError:
        _fail("MCP_POLICIES_INVALID")
    try:
        registration = compile_registration(
            owner_installation_id=owner_installation_id,
            target_ref=target_ref,
            key_id=key_id,
            trust_generation=trust_generation,
            app_generation=app_generation,
            registration_generation=registration_generation,
            enabled=False,
        )
        registry = compile_empty_registry(
            registration_generation=registration_generation,
            registry_generation=registry_generation,
        )
        issuer = validate_issuer_binding_receipt(
            issuer_binding_receipt,
            owner_installation_id=owner_installation_id,
            target_ref=target_ref,
            release_commit=release_commit,
            release_tree=release_tree,
            boot_id=boot_id,
            policy=policy,
            app_peer_uid=app_peer_uid,
            _now_seconds=now_seconds,
        )
        evidence = compile_installed_evidence(
            registration=parse_release_json(registration[:-1]).to_dict(),
            release_commit=release_commit,
            release_tree=release_tree,
            control_config_bytes=control,
            broker_config_bytes=broker,
            authority_map_bytes=authority_map,
            python_runtime_provenance_digest=python_runtime_provenance_digest,
            provider_attestation_bytes=provider,
            provider_attestation_observed_at=provider_attestation_observed_at,
            issuer_binding_receipt=issuer_binding_receipt,
            issuer_binding_observed_at=issuer_binding_observed_at,
            boot_id=boot_id,
            policy=policy,
            app_peer_uid=app_peer_uid,
            _now_seconds=now_seconds,
        )
    except (ReleaseOwnerInputError, ReleaseContractError) as error:
        code = getattr(error, "code", "RESIDENT_INPUT_INVALID")
        raise PublicationPlanError(code) from None
    preimage = _resident_preimage(
        expected_registration=registration,
        expected_registry=registry,
        expected_evidence=evidence,
        existing_registration_bytes=existing_registration_bytes,
        existing_registry_bytes=existing_registry_bytes,
        existing_installed_evidence_bytes=existing_installed_evidence_bytes,
    )
    payloads = tuple(
        PublicationPayload(path, bytes(raw))
        for path, raw in zip(
            _RESIDENT_PATHS,
            (registration, registry, evidence),
            strict=True,
        )
    )
    predicates = (
        "resident_destinations_absent_or_exact_preimage",
        "resident_parent_direct_root_owned_nonwritable_directory",
        "temporary_files_root_wheel_single_link_same_filesystem",
        "temporary_files_fsync_before_mode_0400",
        "atomic_rename_each_file_then_fsync_parent",
        "readback_path_length_sha256_mode_uid_gid_exact",
        "registration_remains_disabled",
        "release_commit_remains_permanently_disarmed",
    )
    return _plan(
        kind="resident",
        directory=_CONFIG_ROOT,
        directory_mode=None,
        payloads=payloads,
        predicates=predicates,
        context={
            "owner_installation_id": owner_installation_id,
            "target_ref": target_ref,
            "release_commit": release_commit,
            "release_tree": release_tree,
            "boot_id": boot_id,
            "control_uid": 450,
            "policy_sha256": policy.sha256,
            "python_runtime_provenance_digest": python_runtime_provenance_digest,
            "provider_attestation_sha256": _sha(provider),
            "issuer_binding_sha256": _sha(issuer),
            "mcp_config_sha256": _sha(mcp_raw),
            "mcp_policies_sha256": mcp_policies_digest,
            "mcp_profile": active_profile,
            "resident_preimage": preimage,
        },
    )


def _bind_resident_context(
    *,
    registration_bytes: object,
    registry_bytes: object,
    installed_evidence_bytes: object,
    authority_policy_bytes: object,
    installed_context: Mapping[str, object],
) -> tuple[bytes, bytes, bytes, bytes]:
    registration, registration_raw = _canonical_document(
        registration_bytes, "REGISTRATION_INVALID"
    )
    registry, registry_raw = _canonical_document(registry_bytes, "REGISTRY_INVALID")
    evidence, evidence_raw = _canonical_document(
        installed_evidence_bytes, "EVIDENCE_INVALID"
    )
    authority = _bytes(authority_policy_bytes, "AUTHORITY_MAP")
    if registration.get("enabled") is not False:
        _fail("REGISTRATION_ACTIVE")
    transitions = registry.get("transitions")
    if type(transitions) is not list:
        _fail("REGISTRY_INVALID")
    if transitions:
        _fail("REGISTRY_NOT_EMPTY")
    joins = {
        "owner_installation_id": registration.get("owner_installation_id"),
        "target_ref": registration.get("target_ref"),
        "boot_id": evidence.get("provider_attestation_boot_id"),
        "from_release_commit": evidence.get("release_commit"),
        "from_release_tree": evidence.get("release_tree"),
        "installed_configuration_digest": evidence.get(
            "installed_configuration_digest"
        ),
        "python_runtime_provenance_digest": evidence.get(
            "python_runtime_provenance_digest"
        ),
        "provider_binary_attestation_digest": evidence.get(
            "provider_binary_attestation_digest"
        ),
        "authority_policy_hash": _sha(authority),
        "issuer_binding_digest": evidence.get("issuer_binding_digest"),
    }
    if not isinstance(installed_context, Mapping):
        _fail("INSTALLED_CONTEXT_INVALID")
    if any(
        name not in installed_context
        or not _typed_equal(installed_context[name], expected)
        for name, expected in joins.items()
    ):
        _fail("RESIDENT_CONTEXT_MISMATCH")
    if not _typed_equal(
        registry.get("registration_generation"),
        registration.get("registration_generation"),
    ):
        _fail("RESIDENT_CONTEXT_MISMATCH")
    return registration_raw, registry_raw, evidence_raw, authority


def compile_staged_publication_plan(
    *,
    artifact: bytes,
    installer_profile: bytes,
    configuration_transition: bytes,
    source_proof: bytes,
    compatibility_proof: bytes,
    rollback_evidence: bytes,
    retained_paths: list[str],
    excluded_secret_classes: list[str],
    now_seconds: int,
    installed_context: dict[str, str],
    resident_registration_bytes: bytes,
    resident_registry_bytes: bytes,
    resident_installed_evidence_bytes: bytes,
    authority_policy_bytes: bytes,
    destination_state: str,
    pending_state: str,
) -> PublicationPlan:
    """Compile the exact ten staged files and their publication predicates."""

    registration, registry, evidence, authority = _bind_resident_context(
        registration_bytes=resident_registration_bytes,
        registry_bytes=resident_registry_bytes,
        installed_evidence_bytes=resident_installed_evidence_bytes,
        authority_policy_bytes=authority_policy_bytes,
        installed_context=installed_context,
    )
    if destination_state != "ABSENT":
        _fail("STAGE_DESTINATION_OCCUPIED")
    if pending_state != "ABSENT":
        _fail("PENDING_DESTINATION_OCCUPIED")
    try:
        staged: StagedInputs = compile_staged_inputs(
            artifact=_bytes(artifact, "STAGED_INPUT_INVALID"),
            installer_profile=_bytes(installer_profile, "STAGED_INPUT_INVALID"),
            configuration_transition=_bytes(
                configuration_transition, "STAGED_INPUT_INVALID"
            ),
            source_proof=_bytes(source_proof, "STAGED_INPUT_INVALID"),
            compatibility_proof=_bytes(
                compatibility_proof, "STAGED_INPUT_INVALID"
            ),
            rollback_evidence=_bytes(rollback_evidence, "STAGED_INPUT_INVALID"),
            retained_paths=list(retained_paths),
            excluded_secret_classes=list(excluded_secret_classes),
            now_seconds=now_seconds,
            installed_context=dict(installed_context),
        )
    except (StagedInputError, TypeError, ValueError) as error:
        code = getattr(error, "code", "STAGED_INPUT_INVALID")
        raise PublicationPlanError(code) from None
    if tuple(name for name, _ in staged.files) != _STAGED_NAMES:
        _fail("STAGED_FILE_SET_MISMATCH")
    directory = _STAGING_ROOT + "/" + staged.transition_digest
    pending_directory = _STAGING_ROOT + "/.pending-" + staged.transition_digest
    payloads = tuple(
        PublicationPayload(directory + "/" + name, bytes(raw))
        for name, raw in staged.files
    )
    predicates = (
        "destination_directory_absent",
        "pending_directory_absent_and_direct_child_of_staging_root",
        "pending_and_destination_parent_same_filesystem",
        "write_each_file_root_wheel_then_fsync",
        "set_each_file_mode_0400_before_directory_seal",
        "set_pending_directory_root_wheel_mode_0500_then_fsync",
        "atomic_rename_pending_directory_to_destination",
        "fsync_staging_root_after_rename",
        "readback_directory_and_all_ten_files_exact",
        "registry_unchanged_until_installed_consumer_rederives",
        "release_commit_remains_permanently_disarmed",
    )
    return _plan(
        kind="staged",
        directory=directory,
        directory_mode=_STAGING_DIRECTORY_MODE,
        payloads=payloads,
        predicates=predicates,
        context={
            "transition_digest": staged.transition_digest,
            "pending_directory": pending_directory,
            "resident_registration_sha256": _sha(registration),
            "resident_registry_sha256": _sha(registry),
            "resident_installed_evidence_sha256": _sha(evidence),
            "authority_policy_sha256": _sha(authority),
            "owner_installation_id": installed_context["owner_installation_id"],
            "target_ref": installed_context["target_ref"],
            "from_release_commit": installed_context["from_release_commit"],
            "from_release_tree": installed_context["from_release_tree"],
            "destination_preimage": destination_state,
            "pending_preimage": pending_state,
        },
    )
