"""Validation for the closed B0 Code Intelligence supply lock.

This module deliberately has no network, process, archive, or installer surface.
It only decides whether a source-controlled lock is complete enough for a future
hosted execution.  An incomplete lock is unavailable; it is never repaired from
an ambient package manager, a mutable ref, or a caller supplied URL.
"""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Mapping


LOCK_SCHEMA = "mastermind.codeintel_experiment_toolchain_lock.v1"
LOCK_OPERATION = "mastermind-codeintel-b0-hosted-tool-bundle-forge-20260902-sol-001"
SUPPORTED_PLATFORMS = ("linux-x64",)
REQUIRED_COMPONENTS = frozenset(
    {
        "serena",
        "pyright",
        "typescript_language_server",
        "typescript",
        "zoekt",
        "node_runtime",
        "go_runtime",
    }
)

_HEX40 = re.compile(r"^[0-9a-f]{40}$")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_RECIPE_KINDS = frozenset({"exact_source_build", "published_artifact"})


class LockValidationError(ValueError):
    """Raised when a supply identity is missing, inconsistent, or stale."""


class SupplyEvidenceError(ValueError):
    """Raised when Phase-P observations do not match the committed lock."""


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode(
        "utf-8"
    )


def lock_digest(document: Mapping[str, Any]) -> str:
    """Return the content digest, excluding the self-referential digest field."""

    canonical = deepcopy(dict(document))
    canonical.pop("lock_digest", None)
    return hashlib.sha256(_canonical_json(canonical)).hexdigest()


def _require_mapping(value: object, code: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise LockValidationError(code)
    return value


def _require_exact_keys(value: Mapping[str, Any], expected: set[str], code: str) -> None:
    if set(value) != expected:
        raise LockValidationError(code)


def _require_text(value: object, code: str) -> str:
    if not isinstance(value, str) or not value:
        raise LockValidationError(code)
    return value


def _require_hex(value: object, width: int, code: str) -> str:
    text = _require_text(value, code)
    expression = _HEX40 if width == 40 else _HEX64
    if not expression.fullmatch(text):
        raise LockValidationError(code)
    return text


def _validate_source(value: object) -> None:
    source = _require_mapping(value, "SOURCE_MISSING")
    _require_exact_keys(source, {"repository", "commit", "tree_sha1"}, "SOURCE_KEYS_INVALID")
    repository = _require_text(source["repository"], "SOURCE_REPOSITORY_MISSING")
    if repository.count("/") != 1 or repository.startswith("/") or repository.endswith("/"):
        raise LockValidationError("SOURCE_REPOSITORY_INVALID")
    _require_hex(source["commit"], 40, "SOURCE_COMMIT_INVALID")
    _require_hex(source["tree_sha1"], 40, "SOURCE_TREE_INVALID")


def _validate_dependency_lock(value: object, *, required: bool) -> None:
    if value is None and not required:
        return
    lock = _require_mapping(value, "DEPENDENCY_LOCK_MISSING")
    _require_exact_keys(lock, {"path", "blob_sha1"}, "DEPENDENCY_LOCK_KEYS_INVALID")
    path = _require_text(lock["path"], "DEPENDENCY_LOCK_PATH_MISSING")
    if path.startswith("/") or ".." in Path(path).parts:
        raise LockValidationError("DEPENDENCY_LOCK_PATH_INVALID")
    _require_hex(lock["blob_sha1"], 40, "DEPENDENCY_LOCK_BLOB_INVALID")


def _validate_license(value: object) -> None:
    license_value = _require_mapping(value, "LICENSE_MISSING")
    _require_exact_keys(license_value, {"spdx", "blobs"}, "LICENSE_KEYS_INVALID")
    _require_text(license_value["spdx"], "LICENSE_SPDX_MISSING")
    blobs = license_value["blobs"]
    if not isinstance(blobs, list) or not blobs:
        raise LockValidationError("LICENSE_BLOBS_MISSING")
    for blob in blobs:
        item = _require_mapping(blob, "LICENSE_BLOB_INVALID")
        _require_exact_keys(item, {"path", "sha1"}, "LICENSE_BLOB_KEYS_INVALID")
        path = _require_text(item["path"], "LICENSE_BLOB_PATH_MISSING")
        if path.startswith("/") or ".." in Path(path).parts:
            raise LockValidationError("LICENSE_BLOB_PATH_INVALID")
        _require_hex(item["sha1"], 40, "LICENSE_BLOB_SHA1_INVALID")


def _validate_artifacts(value: object, *, required: bool) -> None:
    if not isinstance(value, list):
        raise LockValidationError("ARTIFACTS_INVALID")
    if required and not value:
        raise LockValidationError("ARTIFACT_CHECKSUM_MISSING")
    for artifact in value:
        item = _require_mapping(artifact, "ARTIFACT_INVALID")
        if "checksum" not in item:
            raise LockValidationError("ARTIFACT_CHECKSUM_MISSING")
        _require_exact_keys(
            item,
            {"filename", "publisher", "locator", "checksum", "platform"},
            "ARTIFACT_KEYS_INVALID",
        )
        _require_text(item["filename"], "ARTIFACT_FILENAME_MISSING")
        _require_text(item["publisher"], "ARTIFACT_PUBLISHER_MISSING")
        locator = _require_text(item["locator"], "ARTIFACT_LOCATOR_MISSING")
        if not (locator.startswith("https://") or locator.startswith("github-release:")):
            raise LockValidationError("ARTIFACT_LOCATOR_INVALID")
        platform = _require_text(item["platform"], "ARTIFACT_PLATFORM_MISSING")
        if platform not in {"any", *SUPPORTED_PLATFORMS}:
            raise LockValidationError("UNSUPPORTED_PLATFORM")
        checksum = _require_mapping(item["checksum"], "ARTIFACT_CHECKSUM_MISSING")
        _require_exact_keys(checksum, {"algorithm", "value"}, "ARTIFACT_CHECKSUM_KEYS_INVALID")
        algorithm = _require_text(checksum["algorithm"], "ARTIFACT_CHECKSUM_ALGORITHM_INVALID")
        digest = _require_text(checksum["value"], "ARTIFACT_CHECKSUM_MISSING")
        if algorithm == "sha256":
            _require_hex(digest, 64, "ARTIFACT_CHECKSUM_INVALID")
        elif algorithm == "sha512-base64":
            if not re.fullmatch(r"[A-Za-z0-9+/]{86}==", digest):
                raise LockValidationError("ARTIFACT_CHECKSUM_INVALID")
        else:
            raise LockValidationError("ARTIFACT_CHECKSUM_ALGORITHM_INVALID")


def _validate_recipe(value: object) -> str:
    recipe = _require_mapping(value, "BUILD_RECIPE_MISSING")
    _require_exact_keys(recipe, {"kind", "steps", "sha256"}, "BUILD_RECIPE_KEYS_INVALID")
    kind = _require_text(recipe["kind"], "BUILD_RECIPE_KIND_INVALID")
    if kind not in _RECIPE_KINDS:
        raise LockValidationError("BUILD_RECIPE_KIND_INVALID")
    steps = recipe["steps"]
    if not isinstance(steps, list) or not steps or not all(
        isinstance(step, str) and re.fullmatch(r"[a-z0-9-]+", step) for step in steps
    ):
        raise LockValidationError("BUILD_RECIPE_STEPS_INVALID")
    claimed = _require_hex(recipe["sha256"], 64, "BUILD_RECIPE_DIGEST_INVALID")
    actual = hashlib.sha256(_canonical_json({"kind": kind, "steps": steps})).hexdigest()
    if claimed != actual:
        raise LockValidationError("BUILD_RECIPE_DIGEST_MISMATCH")
    return kind


def _validate_component(name: str, value: object) -> None:
    component = _require_mapping(value, "COMPONENT_INVALID")
    _require_exact_keys(
        component,
        {"source", "dependency_lock", "license", "artifacts", "platforms", "build_recipe"},
        "COMPONENT_KEYS_INVALID",
    )
    _validate_source(component["source"])
    kind = _validate_recipe(component["build_recipe"])
    _validate_dependency_lock(
        component["dependency_lock"], required=kind == "exact_source_build"
    )
    _validate_license(component["license"])
    _validate_artifacts(component["artifacts"], required=kind == "published_artifact")
    platforms = component["platforms"]
    if not isinstance(platforms, list) or platforms != list(SUPPORTED_PLATFORMS):
        raise LockValidationError("UNSUPPORTED_PLATFORM")


def validate_toolchain_lock(document: Mapping[str, Any]) -> dict[str, Any]:
    """Fail closed unless every required B0 supply identity is pinned exactly."""

    root = _require_mapping(document, "LOCK_DOCUMENT_INVALID")
    _require_exact_keys(
        root,
        {"schema", "lock_version", "operation_key", "supported_platforms", "components", "lock_digest"},
        "LOCK_KEYS_INVALID",
    )
    if root["schema"] != LOCK_SCHEMA:
        raise LockValidationError("LOCK_SCHEMA_INVALID")
    if root["lock_version"] != 1:
        raise LockValidationError("LOCK_VERSION_INVALID")
    if root["operation_key"] != LOCK_OPERATION:
        raise LockValidationError("LOCK_OPERATION_INVALID")
    if root["supported_platforms"] != list(SUPPORTED_PLATFORMS):
        raise LockValidationError("UNSUPPORTED_PLATFORM")
    components = _require_mapping(root["components"], "COMPONENTS_INVALID")
    if set(components) != REQUIRED_COMPONENTS:
        raise LockValidationError("COMPONENT_SET_INVALID")
    for name in sorted(REQUIRED_COMPONENTS):
        _validate_component(name, components[name])
    claimed_digest = _require_hex(root["lock_digest"], 64, "LOCK_DIGEST_INVALID")
    if claimed_digest != lock_digest(root):
        raise LockValidationError("LOCK_DIGEST_MISMATCH")
    return deepcopy(dict(root))


def load_toolchain_lock(path: Path) -> dict[str, Any]:
    """Load and validate a UTF-8 JSON lock without following any external input."""

    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise LockValidationError("LOCK_UNAVAILABLE") from error
    return validate_toolchain_lock(document)


def _evidence_mapping(value: object, code: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise SupplyEvidenceError(code)
    return value


def _evidence_exact_keys(value: Mapping[str, Any], expected: set[str], code: str) -> None:
    if set(value) != expected:
        raise SupplyEvidenceError(code)


def verify_phase_p_evidence(
    document: Mapping[str, Any], evidence: Mapping[str, Any]
) -> dict[str, Any]:
    """Match Phase-P source/blob/artifact observations against the closed lock.

    The caller is responsible for obtaining each observation from the immutable
    upstream source or staged bytes. This pure comparison intentionally performs
    no network or filesystem retrieval, so it cannot replace the future hosted
    retrieval verifier; it prevents that verifier from silently accepting an
    observation that differs from the reviewed lock.
    """

    locked = validate_toolchain_lock(document)
    observed = _evidence_mapping(evidence, "PHASE_P_EVIDENCE_INVALID")
    _evidence_exact_keys(observed, {"platform", "components"}, "PHASE_P_EVIDENCE_KEYS_INVALID")
    if observed["platform"] != locked["supported_platforms"][0]:
        raise SupplyEvidenceError("PHASE_P_PLATFORM_MISMATCH")
    observed_components = _evidence_mapping(
        observed["components"], "PHASE_P_COMPONENTS_INVALID"
    )
    if set(observed_components) != REQUIRED_COMPONENTS:
        raise SupplyEvidenceError("PHASE_P_COMPONENT_SET_INVALID")
    locked_components = _require_mapping(locked["components"], "COMPONENTS_INVALID")
    for name in sorted(REQUIRED_COMPONENTS):
        expected = _require_mapping(locked_components[name], "COMPONENT_INVALID")
        component = _evidence_mapping(observed_components[name], "PHASE_P_COMPONENT_INVALID")
        _evidence_exact_keys(
            component,
            {"source", "dependency_lock", "license", "artifacts"},
            "PHASE_P_COMPONENT_KEYS_INVALID",
        )
        source = _evidence_mapping(component["source"], "SOURCE_EVIDENCE_INVALID")
        expected_source = _require_mapping(expected["source"], "SOURCE_MISSING")
        _evidence_exact_keys(source, {"repository", "commit", "tree_sha1"}, "SOURCE_EVIDENCE_KEYS_INVALID")
        if source["repository"] != expected_source["repository"]:
            raise SupplyEvidenceError("SOURCE_REPOSITORY_MISMATCH")
        if source["commit"] != expected_source["commit"]:
            raise SupplyEvidenceError("SOURCE_COMMIT_MISMATCH")
        if source["tree_sha1"] != expected_source["tree_sha1"]:
            raise SupplyEvidenceError("SOURCE_TREE_MISMATCH")
        if component["dependency_lock"] != expected["dependency_lock"]:
            raise SupplyEvidenceError("DEPENDENCY_LOCK_MISMATCH")
        if component["license"] != expected["license"]:
            raise SupplyEvidenceError("LICENSE_EVIDENCE_MISMATCH")
        if component["artifacts"] != expected["artifacts"]:
            raise SupplyEvidenceError("ARTIFACT_EVIDENCE_MISMATCH")
    return deepcopy(dict(observed))
