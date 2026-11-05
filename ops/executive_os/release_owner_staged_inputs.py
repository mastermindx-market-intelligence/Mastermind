"""Compile supplied, already-qualified R6 observations into immutable stage bytes.

No filesystem, clock, network, key, registration or publication effects occur.
The caller still owns actual receipt qualification, source protection/ancestry,
installed identity and root custody. These bytes establish none of those facts.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib

from control_plane import executive_release_contract as contract
from control_plane import executive_release_factory as factory
from control_plane.executive_release_consumer import ReleaseConsumerError

# The R6 opaque artifact ceiling, expressed in bytes.
_MAX_ARTIFACT_BYTES = 536_870_912
_CONTEXT_FIELDS = (
    "owner_installation_id target_ref boot_id from_release_commit from_release_tree "
    "from_installed_manifest_digest installed_configuration_digest "
    "python_runtime_provenance_digest provider_binary_attestation_digest "
    "authority_policy_hash issuer_binding_digest"
).split()
_IDENTITIES = "from_release_commit from_release_tree to_release_commit to_release_tree".split()
_ROLLBACK_FIELDS = (
    "original_upgrade_request_id original_terminal_or_reconciliation_digest "
    "retained_artifact_digest preimage_digest current_compatibility_digest"
).split()
_PRODUCER = "ops/executive_os/install.sh:"


class StagedInputError(ValueError):
    """Closed error: never include caller content or an internal traceback chain."""

    def __init__(self, field: str, code: str) -> None:
        self.field, self.code = field, code
        super().__init__(f"{field}:{code}")


@dataclass(frozen=True)
class StagedInputs:
    """Detached output only; no authority, approval or readiness state."""

    transition_digest: str
    files: tuple[tuple[str, bytes], ...]


def _hash(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _digest(value) -> str:
    return _hash(contract.canonical_release_bytes(value))


def _wire(value) -> bytes:
    raw = contract.canonical_release_bytes(value) + b"\n"
    factory.file_document(raw)  # Effective limit includes the final delimiter.
    return raw


def _document(raw, suffix, fields, *, producer=None):
    value = factory._object(
        factory.file_document(raw), "schema " + fields + (" producer" if producer else ""),
        "mastermind.executive_release_" + suffix + "/v1",
    )
    if producer:
        factory._join(value, {"producer": _PRODUCER + producer + "-v1"})
    return value


def _context(value):
    if (type(value) is not dict or any(type(key) is not str for key in value)
            or set(value) != set(_CONTEXT_FIELDS)
            or any(type(item) is not str for item in value.values())):
        raise StagedInputError("installed_context", "FIELDS_OR_TYPE")
    result = dict(value)
    for name in ("owner_installation_id", "boot_id"):
        factory._canonical_uuid(result[name], name)
    for name in _CONTEXT_FIELDS:
        if name not in ("owner_installation_id", "boot_id"):
            factory._match(result[name], factory._HEX40 if name in (
                "from_release_commit", "from_release_tree") else factory._HEX64)
    return result


def compile_staged_inputs(
    *, artifact: bytes, installer_profile: bytes, configuration_transition: bytes,
    source_proof: bytes, compatibility_proof: bytes, rollback_evidence: bytes,
    retained_paths: list[str], excluded_secret_classes: list[str],
    now_seconds: int, installed_context: dict[str, str],
) -> StagedInputs:
    """Compile one upgrade/rollback without establishing receipt authenticity.

    Input JSON is exact canonical UTF-8 plus one LF. ``now_seconds`` and the
    closed eleven-field installed context are explicit observations supplied by
    the qualified caller. Missing function arguments remain ordinary TypeErrors.
    """
    try:
        context = _context(installed_context)
        if type(now_seconds) is not int or not 0 <= now_seconds <= (1 << 63) - 1:
            raise StagedInputError("now_seconds", "INTEGER_RANGE")
        if type(artifact) is not bytes or not 1 <= len(artifact) <= _MAX_ARTIFACT_BYTES:
            raise StagedInputError("artifact", "BYTES_OR_SIZE")
        profile = _document(installer_profile, "installer_profile",
            "profile_id profile_version repository platform architecture source_policy_mode action")
        factory._match(profile["profile_id"], factory._IDENTIFIER)
        if (type(profile["profile_version"]) is not int
                or not 1 <= profile["profile_version"] <= (1 << 31) - 1):
            raise StagedInputError("profile_version", "INTEGER_RANGE")
        configuration = _document(configuration_transition, "configuration_transition",
            "from_configuration_digest to_configuration_digest changed_keys restart_roles")
        factory._join(configuration, {"from_configuration_digest": context["installed_configuration_digest"]})
        factory._match(configuration["to_configuration_digest"], factory._HEX64)
        factory._array(configuration["changed_keys"], 32)
        factory._array(configuration["restart_roles"], 32)
        source = _document(source_proof, "source_proof",
            "repository source_policy_mode protected_source_sha protected_source_tree "
            "installer_source_commit installer_source_tree to_release_commit to_release_tree "
            "from_release_commit from_release_tree observed_at", producer="protected-source-proof")
        factory.observed_at(source["observed_at"], now_seconds, admission=True)
        factory._join(source, {
            "repository": profile["repository"], "source_policy_mode": profile["source_policy_mode"],
            "from_release_commit": context["from_release_commit"],
            "from_release_tree": context["from_release_tree"],
            "protected_source_tree": source["installer_source_tree"],
        })
        identities = {key: source[key] for key in _IDENTITIES}
        compatibility = _document(compatibility_proof, "compatibility_proof",
            "from_release_commit from_release_tree to_release_commit to_release_tree "
            "platform architecture installer_profile_digest checks result", producer="compatibility-proof")
        factory._join(compatibility, {**identities, "platform": profile["platform"],
            "architecture": profile["architecture"], "installer_profile_digest": _digest(profile), "result": "PASS"})
        factory._array(compatibility["checks"], 64)
        upgrade = profile["action"] == "executive.release.upgrade"
        rollback = _document(rollback_evidence, "rollback_evidence",
            "action from_release_commit from_release_tree to_release_commit to_release_tree checks result"
            + ("" if upgrade else " " + " ".join(_ROLLBACK_FIELDS)), producer="rollback-evidence")
        factory._join(rollback, {**identities, "action": profile["action"], "result": "PASS"})
        factory._array(rollback["checks"], 64)
        factory._array(retained_paths, 128, paths=True)
        factory._array(excluded_secret_classes, 128)
        metadata = {
            "schema": "mastermind.executive_release_artifact_metadata/v1",
            "artifact_filename": "release-artifact.bin",
            "media_type": "application/vnd.mastermind.executive.release.v1",
            "artifact_size_bytes": len(artifact), "artifact_sha256": _hash(artifact),
        }
        preservation = {
            "schema": "mastermind.executive_release_preservation_plan/v1",
            "from_installed_manifest_digest": context["from_installed_manifest_digest"],
            "configuration_transition_digest": _digest(configuration),
            "retained_paths": list(retained_paths), "excluded_secret_classes": list(excluded_secret_classes),
            "rollback_evidence_digest": _digest(rollback), "producer": _PRODUCER + "preservation-plan-v1",
        }
        # All immutable leaf hashes precede the effect. No leaf contains the
        # effect/transition hash, a self hash, grant, approval or owner seal.
        effect = {
            "schema": "mastermind.executive_release_effect/v1",
            **{key: source[key] for key in (
                "repository", "protected_source_sha", "source_policy_mode",
                "installer_source_commit", "installer_source_tree", *_IDENTITIES)},
            "installer_profile_digest": _digest(profile),
            "from_installed_manifest_digest": context["from_installed_manifest_digest"],
            "staged_artifact_digest": _hash(artifact), "staged_content_metadata_digest": _digest(metadata),
            "platform": profile["platform"], "architecture": profile["architecture"],
            "configuration_transition_digest": _digest(configuration),
            "compatibility_proof_digest": _digest(compatibility),
            "preservation_plan_digest": _digest(preservation), "action": profile["action"],
            "rollback_evidence": (
                {"kind": "upgrade", "rollback_readiness_digest": _digest(rollback)} if upgrade else
                {"kind": "rollback", **{key: rollback[key] for key in _ROLLBACK_FIELDS}}
            ),
        }
        effect = contract.validate_normalized_effect(effect).to_dict()
        preconditions = {
            "schema": "mastermind.executive_release_preconditions/v1",
            **{key: context[key] for key in _CONTEXT_FIELDS if key not in (
                "from_release_commit", "from_release_tree")},
            **{key: effect[key] for key in ("staged_artifact_digest", "staged_content_metadata_digest",
                                           "compatibility_proof_digest", "preservation_plan_digest")},
            "admission_contract_digest": _digest(factory._ADMISSION_MAP),
            "production_arming_digest": _digest(factory._DISARMED),
        }
        files = {
            "effect.json": _wire(effect), "preconditions-template.json": _wire(preconditions),
            "release-artifact.bin": artifact, "artifact-metadata.json": _wire(metadata),
            "installer-profile.json": installer_profile, "configuration-transition.json": configuration_transition,
            "source-proof.json": source_proof, "compatibility-proof.json": compatibility_proof,
            "preservation-plan.json": _wire(preservation), "rollback-evidence.json": rollback_evidence,
        }
        return StagedInputs(_digest(effect), tuple(sorted(files.items())))
    except StagedInputError as error:
        raise error from None
    except (factory.FactoryInputError, contract.ReleaseContractError, ReleaseConsumerError):
        raise StagedInputError("inputs", "INVALID") from None
