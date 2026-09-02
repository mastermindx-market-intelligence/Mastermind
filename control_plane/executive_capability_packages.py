"""Immutable capability-package contracts (Sol Capability Fabric, CAP-S1 foundation).

This module owns exactly two things, per the acyclic identity graph frozen in
``docs/superpowers/specs/2026-09-01-sol-capability-fabric-package-identity-amendment.md``:

- pure, deterministic canonical-JSON digesting of one immutable source-package
  generation (file rows -> package content digest -> package source digest ->
  skill grant digests -> package generation digest), and construction of the
  typed contract from an untrusted raw mapping, trusting no declared digest; and
- bounded, descriptor-relative, symlink-refusing, race-fenced local
  verification of that generation against real files on disk.

It loads no policy file, resolves no profile, starts no process, invokes no
Git or provider, and mutates no filesystem. ``control_plane.executive_agent_capabilities``
is the sole capability-policy owner and the only caller of this module.

Error messages are bounded to a field name and a closed reason token. They
never echo a caller-supplied path, digest, or identifier value.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import re
import stat
from pathlib import Path
from typing import Callable, Mapping, NoReturn

# ---------------------------------------------------------------------------
# Schema tokens and bounds
# ---------------------------------------------------------------------------

CAPABILITY_PACKAGE_CONTENT_SCHEMA = "mastermind.capability_package_content/v1"
EFFECTIVE_SKILL_CLOSURE_SCHEMA = "mastermind.effective_skill_closure/v1"
CAPABILITY_PACKAGE_SOURCE_SCHEMA = "mastermind.capability_package_source/v1"
EFFECTIVE_SKILL_GRANT_SCHEMA = "mastermind.effective_skill_grant/v1"
CAPABILITY_PACKAGE_GENERATION_SCHEMA = "mastermind.capability_package_generation/v1"

PACKAGE_KIND_SKILLS_ONLY_SOURCE = "skills-only-source"
PACKAGE_SOURCE_STATE_PROTECTED = "SOURCE_PROTECTED"

MAX_PACKAGE_FILES = 64
MAX_PACKAGE_FILE_BYTES = 1024 * 1024
MAX_PACKAGE_TOTAL_BYTES = 8 * 1024 * 1024
MAX_SKILLS_PER_PACKAGE = 32
MAX_CLOSURE_FILES = 32
MAX_PACKAGE_DIRECTORIES = 32
MAX_PACKAGE_TREE_DEPTH = 8
MAX_PATH_SEGMENT_BYTES = 255
MAX_RELATIVE_PATH_BYTES = 512
MAX_REPOSITORY_BYTES = 200
MAX_PACKAGE_TRAVERSAL_ENTRIES = MAX_PACKAGE_FILES + MAX_PACKAGE_DIRECTORIES

_READ_CHUNK_BYTES = 65536

# Every regex below is validated with `.fullmatch()`, never `.match()`: `$`
# in Python regex matches at the end of the string OR immediately before a
# single trailing newline, so `.match()` against a `$`-anchored pattern lets
# a value like "example.pkg1\n" (or a 64-hex sha256 / 40-hex commit plus a
# trailing "\n") through undetected. `fullmatch()` requires the pattern to
# consume the entire string, closing that gap regardless of anchors.
_IDENTIFIER_RE = re.compile(r"[a-z0-9][a-z0-9._-]{0,95}")
_SHA256_RE = re.compile(r"[0-9a-f]{64}")
_HEX40_RE = re.compile(r"[0-9a-f]{40}")
_REPOSITORY_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,99}/[A-Za-z0-9][A-Za-z0-9._-]{0,99}")
_CONTROL_CHARS = frozenset(chr(c) for c in range(0x20)) | {chr(0x7F)}

_O_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
_O_DIRECTORY = getattr(os, "O_DIRECTORY", 0)
_O_NONBLOCK = getattr(os, "O_NONBLOCK", 0)
_O_CLOEXEC = getattr(os, "O_CLOEXEC", 0)

_RAW_KEYS = frozenset(
    {
        "kind",
        "repository",
        "source_commit",
        "source_tree_sha",
        "package_root",
        "manifest_path",
        "generation",
        "source_state",
        "revoked",
        "package_content_digest",
        "package_source_digest",
        "files",
        "skills",
        "required_app_references",
        "package_generation_digest",
    }
)
_FILE_ROW_KEYS = frozenset({"relative_path", "sha256", "byte_length", "executable"})
_SKILL_ROW_KEYS = frozenset({"runtime_name", "entrypoint_path", "closure_paths", "skill_content_digest", "grant_digest"})


class CapabilityPackageError(ValueError):
    """One capability-package row, digest, or source verification refused."""


def _refuse(field: str, reason: str) -> NoReturn:
    raise CapabilityPackageError(f"{field}: {reason}")


def _utf8_byte_length(value: str, field: str) -> int:
    """`len(value.encode("utf-8"))`, refusing bounded instead of leaking a
    naked UnicodeEncodeError for a str containing a lone surrogate (which
    cannot be encoded to UTF-8 at all)."""
    try:
        return len(value.encode("utf-8"))
    except UnicodeEncodeError:
        _refuse(field, "invalid_utf8")


# ---------------------------------------------------------------------------
# Immutable contract types
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class CapabilityPackageFile:
    relative_path: str
    sha256: str
    byte_length: int
    executable: bool


@dataclasses.dataclass(frozen=True)
class EffectiveSkillGrant:
    capability_id: str
    runtime_name: str
    entrypoint_path: str
    closure_paths: tuple[str, ...]
    skill_content_digest: str
    package_capability_id: str
    package_generation: str
    package_source_digest: str
    grant_digest: str


@dataclasses.dataclass(frozen=True)
class CapabilityPackageGeneration:
    capability_id: str
    kind: str
    repository: str
    source_commit: str
    source_tree_sha: str
    package_root: str
    manifest_path: str
    generation: str
    source_state: str
    revoked: bool
    package_content_digest: str
    package_source_digest: str
    files: tuple[CapabilityPackageFile, ...]
    skills: tuple[EffectiveSkillGrant, ...]
    required_app_references: tuple[str, ...]
    package_generation_digest: str


@dataclasses.dataclass(frozen=True)
class VerifiedCapabilityPackage:
    capability_id: str
    generation: str
    package_root: str
    package_content_digest: str
    file_count: int
    total_bytes: int
    skill_content_digests: tuple[tuple[str, str], ...]
    package_source_digest: str
    package_generation_digest: str
    source_state: str
    revoked: bool


# ---------------------------------------------------------------------------
# Canonical JSON law
# ---------------------------------------------------------------------------


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _file_row_projection(row: CapabilityPackageFile) -> dict:
    return {
        "relative_path": row.relative_path,
        "sha256": row.sha256,
        "byte_length": row.byte_length,
        "executable": row.executable,
    }


def _require_valid_file_row(row: object, field: str) -> None:
    """Exact row type plus the same per-field validation the builder applies.

    The two public digest helpers below accept a bare tuple of file rows
    from ANY caller, not only the trusted builder -- a directly constructed
    invalid or subclassed row must never be allowed to yield a
    canonical-looking digest.
    """
    if type(row) is not CapabilityPackageFile:
        _refuse(field, "invalid_row")
    _validate_relative_path(row.relative_path, f"{field}.relative_path")
    _validate_sha256_value(row.sha256, f"{field}.sha256")
    _validate_byte_length(row.byte_length, f"{field}.byte_length")
    _validate_executable_flag(row.executable, f"{field}.executable")


def _require_valid_file_rows(files: object, field: str) -> None:
    if type(files) is not tuple:
        _refuse(field, "invalid_shape")
    for row in files:
        _require_valid_file_row(row, f"{field}[]")


def capability_package_content_digest(files: tuple[CapabilityPackageFile, ...]) -> str:
    _require_valid_file_rows(files, "files")
    ordered = sorted(files, key=lambda f: f.relative_path)
    projection = {
        "schema_version": CAPABILITY_PACKAGE_CONTENT_SCHEMA,
        "files": [_file_row_projection(row) for row in ordered],
    }
    return _sha256_hex(_canonical_bytes(projection))


def effective_skill_content_digest(
    *,
    runtime_name: str,
    entrypoint_path: str,
    closure_files: tuple[CapabilityPackageFile, ...],
) -> str:
    _require_valid_file_rows(closure_files, "closure_files")
    ordered = sorted(closure_files, key=lambda f: f.relative_path)
    projection = {
        "schema_version": EFFECTIVE_SKILL_CLOSURE_SCHEMA,
        "skill_name": runtime_name,
        "entrypoint_path": entrypoint_path,
        "files": [_file_row_projection(row) for row in ordered],
    }
    return _sha256_hex(_canonical_bytes(projection))


def _package_source_digest(
    *,
    capability_id: str,
    kind: str,
    repository: str,
    source_commit: str,
    source_tree_sha: str,
    package_root: str,
    manifest_path: str,
    package_content_digest: str,
    required_app_references: tuple[str, ...],
) -> str:
    projection = {
        "schema_version": CAPABILITY_PACKAGE_SOURCE_SCHEMA,
        "capability_id": capability_id,
        "kind": kind,
        "repository": repository,
        "source_commit": source_commit,
        "source_tree_sha": source_tree_sha,
        "package_root": package_root,
        "manifest_path": manifest_path,
        "package_content_digest": package_content_digest,
        "required_app_references": list(required_app_references),
    }
    return _sha256_hex(_canonical_bytes(projection))


def _skill_grant_digest(
    *,
    capability_id: str,
    runtime_name: str,
    entrypoint_path: str,
    closure_paths: tuple[str, ...],
    skill_content_digest: str,
    package_capability_id: str,
    package_generation: str,
    package_source_digest: str,
) -> str:
    projection = {
        "schema_version": EFFECTIVE_SKILL_GRANT_SCHEMA,
        "capability_id": capability_id,
        "runtime_name": runtime_name,
        "entrypoint_path": entrypoint_path,
        "closure_paths": list(closure_paths),
        "skill_content_digest": skill_content_digest,
        "package_capability_id": package_capability_id,
        "package_generation": package_generation,
        "package_source_digest": package_source_digest,
    }
    return _sha256_hex(_canonical_bytes(projection))


def _package_generation_digest(
    *,
    capability_id: str,
    generation: str,
    source_state: str,
    revoked: bool,
    package_source_digest: str,
    skills_ordered: tuple[tuple[str, str], ...],
) -> str:
    projection = {
        "schema_version": CAPABILITY_PACKAGE_GENERATION_SCHEMA,
        "capability_id": capability_id,
        "generation": generation,
        "source_state": source_state,
        "revoked": revoked,
        "package_source_digest": package_source_digest,
        "skills": [[cid, grant_digest] for cid, grant_digest in skills_ordered],
    }
    return _sha256_hex(_canonical_bytes(projection))


# ---------------------------------------------------------------------------
# Field-level validation (raw-input law)
# ---------------------------------------------------------------------------


def _validate_identifier(value: object, field: str) -> str:
    if not isinstance(value, str) or _IDENTIFIER_RE.fullmatch(value) is None:
        _refuse(field, "invalid_identifier")
    return value  # type: ignore[return-value]


def _validate_relative_path(value: object, field: str) -> str:
    if not isinstance(value, str) or value == "":
        _refuse(field, "empty_path")
    assert isinstance(value, str)
    if _utf8_byte_length(value, field) > MAX_RELATIVE_PATH_BYTES:
        _refuse(field, "path_too_long")
    if value.startswith("/"):
        _refuse(field, "absolute_path")
    if "\\" in value:
        _refuse(field, "backslash")
    if any(ch in _CONTROL_CHARS for ch in value):
        _refuse(field, "control_character")
    for part in value.split("/"):
        if part == "":
            _refuse(field, "empty_path_component")
        if part in (".", ".."):
            _refuse(field, "dot_component")
        if _utf8_byte_length(part, field) > MAX_PATH_SEGMENT_BYTES:
            _refuse(field, "path_segment_too_long")
    return value


def _validate_sha256_value(value: object, field: str) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        _refuse(field, "invalid_sha256")
    return value  # type: ignore[return-value]


def _validate_hex40(value: object, field: str) -> str:
    if not isinstance(value, str) or _HEX40_RE.fullmatch(value) is None:
        _refuse(field, "invalid_source_reference")
    return value  # type: ignore[return-value]


def _validate_repository(value: object, field: str) -> str:
    if not isinstance(value, str):
        _refuse(field, "invalid_repository")
    assert isinstance(value, str)
    if _utf8_byte_length(value, field) > MAX_REPOSITORY_BYTES:
        _refuse(field, "invalid_repository")
    if _REPOSITORY_RE.fullmatch(value) is None:
        _refuse(field, "invalid_repository")
    return value


def _validate_byte_length(value: object, field: str) -> int:
    if type(value) is not int:
        _refuse(field, "invalid_byte_length")
    assert isinstance(value, int)
    if value < 0 or value > MAX_PACKAGE_FILE_BYTES:
        _refuse(field, "invalid_byte_length")
    return value


def _validate_executable_flag(value: object, field: str) -> bool:
    if type(value) is not bool:
        _refuse(field, "invalid_executable_flag")
    return value  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Row/collection builders for build_capability_package_generation
# ---------------------------------------------------------------------------


def _build_file_row(raw_row: object, field: str) -> CapabilityPackageFile:
    if not isinstance(raw_row, Mapping) or set(raw_row.keys()) != _FILE_ROW_KEYS:
        _refuse(field, "invalid_shape")
    relative_path = _validate_relative_path(raw_row["relative_path"], f"{field}.relative_path")
    sha256_value = _validate_sha256_value(raw_row["sha256"], f"{field}.sha256")
    byte_length = _validate_byte_length(raw_row["byte_length"], f"{field}.byte_length")
    executable = _validate_executable_flag(raw_row["executable"], f"{field}.executable")
    return CapabilityPackageFile(
        relative_path=relative_path,
        sha256=sha256_value,
        byte_length=byte_length,
        executable=executable,
    )


def _build_files(raw_files: object) -> tuple[CapabilityPackageFile, ...]:
    if not isinstance(raw_files, list) or len(raw_files) == 0:
        _refuse("files", "invalid_shape")
    assert isinstance(raw_files, list)
    if len(raw_files) > MAX_PACKAGE_FILES:
        _refuse("files", "too_many_files")

    rows = tuple(_build_file_row(row, "files[]") for row in raw_files)

    seen_casefold: set[str] = set()
    total_bytes = 0
    previous_path: str | None = None
    for row in rows:
        if previous_path is not None and row.relative_path <= previous_path:
            _refuse("files", "unsorted_or_duplicate_rows")
        previous_path = row.relative_path

        folded = row.relative_path.casefold()
        if folded in seen_casefold:
            _refuse("files", "case_fold_collision")
        seen_casefold.add(folded)

        total_bytes += row.byte_length

    if total_bytes > MAX_PACKAGE_TOTAL_BYTES:
        _refuse("files", "package_too_large")

    return rows


def _build_skills(
    raw_skills: object,
    *,
    files_by_path: Mapping[str, CapabilityPackageFile],
    package_capability_id: str,
    package_generation: str,
    package_source_digest: str,
) -> tuple[EffectiveSkillGrant, ...]:
    if not isinstance(raw_skills, Mapping):
        _refuse("skills", "invalid_shape")
    assert isinstance(raw_skills, Mapping)
    if len(raw_skills) == 0:
        _refuse("skills", "invalid_shape")
    if len(raw_skills) > MAX_SKILLS_PER_PACKAGE:
        _refuse("skills", "too_many_skills")

    grants: list[EffectiveSkillGrant] = []
    seen_runtime_names: set[str] = set()

    for skill_capability_id in sorted(raw_skills.keys()):
        _validate_identifier(skill_capability_id, "skills.capability_id")
        raw_skill = raw_skills[skill_capability_id]
        if not isinstance(raw_skill, Mapping) or set(raw_skill.keys()) != _SKILL_ROW_KEYS:
            _refuse("skills[]", "invalid_shape")

        runtime_name = _validate_identifier(raw_skill["runtime_name"], "skills[].runtime_name")
        if runtime_name in seen_runtime_names:
            _refuse("skills", "duplicate_runtime_name")
        seen_runtime_names.add(runtime_name)

        entrypoint_path = _validate_relative_path(raw_skill["entrypoint_path"], "skills[].entrypoint_path")

        raw_closure_paths = raw_skill["closure_paths"]
        if not isinstance(raw_closure_paths, list) or len(raw_closure_paths) == 0:
            _refuse("skills[].closure_paths", "invalid_shape")
        if len(raw_closure_paths) > MAX_CLOSURE_FILES:
            _refuse("skills[].closure_paths", "closure_too_large")
        closure_paths = tuple(
            _validate_relative_path(p, "skills[].closure_paths[]") for p in raw_closure_paths
        )

        previous_path: str | None = None
        for path in closure_paths:
            if previous_path is not None and path <= previous_path:
                _refuse("skills[].closure_paths", "closure_unsorted_or_duplicate")
            previous_path = path

        if entrypoint_path not in closure_paths:
            _refuse("skills[].closure_paths", "closure_missing_entrypoint")

        for path in closure_paths:
            if path not in files_by_path:
                _refuse("skills[].closure_paths", "closure_path_unknown")

        if entrypoint_path not in files_by_path:
            _refuse("skills[].entrypoint_path", "entrypoint_path_unknown")

        declared_skill_content_digest = _validate_sha256_value(
            raw_skill["skill_content_digest"], "skills[].skill_content_digest"
        )
        declared_grant_digest = _validate_sha256_value(raw_skill["grant_digest"], "skills[].grant_digest")

        closure_files = tuple(files_by_path[path] for path in closure_paths)
        recomputed_skill_content_digest = effective_skill_content_digest(
            runtime_name=runtime_name,
            entrypoint_path=entrypoint_path,
            closure_files=closure_files,
        )
        if recomputed_skill_content_digest != declared_skill_content_digest:
            _refuse("skills[].skill_content_digest", "digest_mismatch")

        recomputed_grant_digest = _skill_grant_digest(
            capability_id=skill_capability_id,
            runtime_name=runtime_name,
            entrypoint_path=entrypoint_path,
            closure_paths=closure_paths,
            skill_content_digest=recomputed_skill_content_digest,
            package_capability_id=package_capability_id,
            package_generation=package_generation,
            package_source_digest=package_source_digest,
        )
        if recomputed_grant_digest != declared_grant_digest:
            _refuse("skills[].grant_digest", "digest_mismatch")

        grants.append(
            EffectiveSkillGrant(
                capability_id=skill_capability_id,
                runtime_name=runtime_name,
                entrypoint_path=entrypoint_path,
                closure_paths=closure_paths,
                skill_content_digest=recomputed_skill_content_digest,
                package_capability_id=package_capability_id,
                package_generation=package_generation,
                package_source_digest=package_source_digest,
                grant_digest=recomputed_grant_digest,
            )
        )

    return tuple(grants)


def build_capability_package_generation(
    *,
    capability_id: str,
    raw: Mapping[str, object],
) -> CapabilityPackageGeneration:
    _validate_identifier(capability_id, "capability_id")

    if not isinstance(raw, Mapping) or set(raw.keys()) != _RAW_KEYS:
        _refuse("raw", "unexpected_shape")

    kind = raw["kind"]
    if kind != PACKAGE_KIND_SKILLS_ONLY_SOURCE:
        _refuse("kind", "unsupported_value")
    assert isinstance(kind, str)

    repository = _validate_repository(raw["repository"], "repository")
    source_commit = _validate_hex40(raw["source_commit"], "source_commit")
    source_tree_sha = _validate_hex40(raw["source_tree_sha"], "source_tree_sha")
    package_root = _validate_relative_path(raw["package_root"], "package_root")
    manifest_path = _validate_relative_path(raw["manifest_path"], "manifest_path")
    generation = _validate_identifier(raw["generation"], "generation")

    source_state = raw["source_state"]
    if source_state != PACKAGE_SOURCE_STATE_PROTECTED:
        _refuse("source_state", "unsupported_value")
    assert isinstance(source_state, str)

    revoked = raw["revoked"]
    if type(revoked) is not bool:
        _refuse("revoked", "invalid_type")
    assert isinstance(revoked, bool)

    raw_required_app_references = raw["required_app_references"]
    if not isinstance(raw_required_app_references, list):
        _refuse("required_app_references", "invalid_type")
    assert isinstance(raw_required_app_references, list)
    if len(raw_required_app_references) != 0:
        _refuse("required_app_references", "required_app_references_not_empty")
    required_app_references: tuple[str, ...] = ()

    files = _build_files(raw["files"])
    files_by_path = {row.relative_path: row for row in files}

    if manifest_path not in files_by_path:
        _refuse("manifest_path", "manifest_path_unknown")

    declared_content_digest = _validate_sha256_value(raw["package_content_digest"], "package_content_digest")
    recomputed_content_digest = capability_package_content_digest(files)
    if recomputed_content_digest != declared_content_digest:
        _refuse("package_content_digest", "digest_mismatch")

    declared_source_digest = _validate_sha256_value(raw["package_source_digest"], "package_source_digest")
    recomputed_source_digest = _package_source_digest(
        capability_id=capability_id,
        kind=kind,
        repository=repository,
        source_commit=source_commit,
        source_tree_sha=source_tree_sha,
        package_root=package_root,
        manifest_path=manifest_path,
        package_content_digest=recomputed_content_digest,
        required_app_references=required_app_references,
    )
    if recomputed_source_digest != declared_source_digest:
        _refuse("package_source_digest", "digest_mismatch")

    skills = _build_skills(
        raw["skills"],
        files_by_path=files_by_path,
        package_capability_id=capability_id,
        package_generation=generation,
        package_source_digest=recomputed_source_digest,
    )

    declared_generation_digest = _validate_sha256_value(
        raw["package_generation_digest"], "package_generation_digest"
    )
    recomputed_generation_digest = _package_generation_digest(
        capability_id=capability_id,
        generation=generation,
        source_state=source_state,
        revoked=revoked,
        package_source_digest=recomputed_source_digest,
        skills_ordered=tuple((grant.capability_id, grant.grant_digest) for grant in skills),
    )
    if recomputed_generation_digest != declared_generation_digest:
        _refuse("package_generation_digest", "digest_mismatch")

    return CapabilityPackageGeneration(
        capability_id=capability_id,
        kind=kind,
        repository=repository,
        source_commit=source_commit,
        source_tree_sha=source_tree_sha,
        package_root=package_root,
        manifest_path=manifest_path,
        generation=generation,
        source_state=source_state,
        revoked=revoked,
        package_content_digest=recomputed_content_digest,
        package_source_digest=recomputed_source_digest,
        files=files,
        skills=skills,
        required_app_references=required_app_references,
        package_generation_digest=recomputed_generation_digest,
    )


# ---------------------------------------------------------------------------
# Untrusted-generation re-derivation (identity amendment: the verifier must
# never trust a publicly constructed CapabilityPackageGeneration; it is only
# ever entitled to trust the output of build_capability_package_generation).
# ---------------------------------------------------------------------------


def _generation_to_raw(generation: CapabilityPackageGeneration) -> dict:
    """Exact inverse of build_capability_package_generation's raw contract.

    Round-tripping a genuinely-built generation through this projection and
    back through the builder must reproduce it byte-for-byte; any hand
    edit to a digest, a scalar field, or a file/skill row changes the
    reconstructed raw mapping and is caught by the builder's own recomputation
    (or by dataclass inequality against the untrusted input) before a single
    filesystem byte is touched.
    """
    return {
        "kind": generation.kind,
        "repository": generation.repository,
        "source_commit": generation.source_commit,
        "source_tree_sha": generation.source_tree_sha,
        "package_root": generation.package_root,
        "manifest_path": generation.manifest_path,
        "generation": generation.generation,
        "source_state": generation.source_state,
        "revoked": generation.revoked,
        "package_content_digest": generation.package_content_digest,
        "package_source_digest": generation.package_source_digest,
        "files": [
            {
                "relative_path": row.relative_path,
                "sha256": row.sha256,
                "byte_length": row.byte_length,
                "executable": row.executable,
            }
            for row in generation.files
        ],
        "skills": {
            grant.capability_id: {
                "runtime_name": grant.runtime_name,
                "entrypoint_path": grant.entrypoint_path,
                "closure_paths": list(grant.closure_paths),
                "skill_content_digest": grant.skill_content_digest,
                "grant_digest": grant.grant_digest,
            }
            for grant in generation.skills
        },
        "required_app_references": list(generation.required_app_references),
        "package_generation_digest": generation.package_generation_digest,
    }


def _require_exact_type(value: object, expected: type, field: str) -> None:
    if type(value) is not expected:
        _refuse(field, "untrusted_generation_refused")


def _require_trusted_generation(generation: CapabilityPackageGeneration) -> None:
    # Exact-type boundary (identity amendment clarification 5505160491,
    # item 1): a dataclass's generated __eq__ returns NotImplemented when
    # `other.__class__ is not self.__class__`, so Python falls back to the
    # OTHER object's __eq__ -- a subclass overriding __eq__ to always
    # return True can make an otherwise-differing object compare equal to a
    # genuine rebuild. Refuse any non-exact type, recursively, BEFORE ever
    # reaching an equality check, rather than trusting the comparison to
    # catch it.
    _require_exact_type(generation, CapabilityPackageGeneration, "generation")
    _require_exact_type(generation.files, tuple, "generation.files")
    for row in generation.files:
        _require_exact_type(row, CapabilityPackageFile, "generation.files[]")
    _require_exact_type(generation.skills, tuple, "generation.skills")
    for grant in generation.skills:
        _require_exact_type(grant, EffectiveSkillGrant, "generation.skills[]")
    _require_exact_type(generation.required_app_references, tuple, "generation.required_app_references")
    for value in generation.required_app_references:
        _require_exact_type(value, str, "generation.required_app_references[]")

    try:
        rebuilt = build_capability_package_generation(
            capability_id=generation.capability_id,
            raw=_generation_to_raw(generation),
        )
    except CapabilityPackageError:
        _refuse("generation", "untrusted_generation_refused")

    # Compare via dataclasses.astuple (recursively converting every nested
    # dataclass -- files, skills -- into plain tuples of primitive scalar
    # values) rather than `rebuilt != generation`: even with the exact-type
    # checks above in place, this ensures the identity decision is never
    # made by invoking any object's own __eq__, only by comparing raw,
    # unspoofable scalars.
    if dataclasses.astuple(rebuilt) != dataclasses.astuple(generation):
        _refuse("generation", "untrusted_generation_refused")


def _derive_allowed_directories(declared_relative_paths: "frozenset[str] | set[str]") -> frozenset[str]:
    """Ancestor directories (package-root relative) implied by declared files."""
    dirs: set[str] = set()
    for relative_path in declared_relative_paths:
        parts = relative_path.split("/")
        for i in range(1, len(parts)):
            dirs.add("/".join(parts[:i]))
    return frozenset(dirs)


# ---------------------------------------------------------------------------
# Bounded, no-follow, descriptor-relative, race-fenced source verification
# ---------------------------------------------------------------------------


def _stat_identity(st: os.stat_result) -> tuple:
    return (
        st.st_dev,
        st.st_ino,
        st.st_mode,
        st.st_nlink,
        st.st_uid,
        st.st_gid,
        st.st_size,
        st.st_mtime_ns,
        st.st_ctime_ns,
    )


def _same_object(a: os.stat_result, b: os.stat_result) -> bool:
    """dev+ino equality between two stat results, naming the same filesystem object.

    Factored into its own module-level function (rather than inlined at each
    call site) so a test can disable this exact fence deterministically via
    monkeypatch and demonstrate that the swap it exists to catch would
    otherwise slip through undetected -- proving the fence itself is
    load-bearing rather than relying on this platform's inode-reuse behavior
    (or lack of it) to make the point. Every retained-object identity check
    in this module -- the census-time open, the post-census re-check, and
    the terminal fence -- routes through this single comparison.
    """
    return (a.st_dev, a.st_ino) == (b.st_dev, b.st_ino)


def verify_capability_package_source(
    source_root: str | Path,
    generation: CapabilityPackageGeneration,
    *,
    _before_terminal_fence: "Callable[[], None] | None" = None,
    _before_final_stat: "Callable[[], None] | None" = None,
    _before_file_open: "Callable[[str], None] | None" = None,
    _between_read_chunks: "Callable[[str], None] | None" = None,
) -> VerifiedCapabilityPackage:
    if _O_NOFOLLOW == 0 or _O_DIRECTORY == 0 or _O_NONBLOCK == 0 or _O_CLOEXEC == 0:
        _refuse("platform", "nofollow_directory_unavailable")

    # A publicly constructed CapabilityPackageGeneration is never trusted:
    # reconstruct the canonical raw mapping and require it to rebuild, via
    # build_capability_package_generation, into something dataclass-equal to
    # what was handed in. Any hand edit -- a zeroed digest, a malformed
    # provenance field, an inconsistent declared file sha256 -- either fails
    # the builder's own recomputation or fails this equality check, and is
    # refused before a single filesystem byte is touched.
    _require_trusted_generation(generation)

    # Defense-in-depth: never trust a hand-constructed generation's path
    # fields either, even though build_capability_package_generation already
    # validates them.
    package_root = _validate_relative_path(generation.package_root, "package_root")
    _validate_relative_path(generation.manifest_path, "manifest_path")
    for row in generation.files:
        _validate_relative_path(row.relative_path, "files[].relative_path")
    for skill in generation.skills:
        _validate_relative_path(skill.entrypoint_path, "skills[].entrypoint_path")
        for path in skill.closure_paths:
            _validate_relative_path(path, "skills[].closure_paths[]")

    declared_entries = {row.relative_path for row in generation.files}
    declared_by_path: dict[str, CapabilityPackageFile] = {
        row.relative_path: row for row in generation.files
    }
    allowed_dirs = _derive_allowed_directories(declared_entries)

    # Bound the declared shape BEFORE any descriptor is opened beyond the
    # package root itself: an adversarial (or merely pathological) file
    # declaration can imply an oversized or over-deep directory forest with
    # only a handful of file rows.
    if len(allowed_dirs) > MAX_PACKAGE_DIRECTORIES:
        _refuse("package_root", "too_many_directories")
    for candidate in (*declared_entries, *allowed_dirs):
        if candidate.count("/") + 1 > MAX_PACKAGE_TREE_DEPTH:
            _refuse("package_root", "package_tree_too_deep")

    # Hostile source_root inputs (an embedded NUL byte, or a non-str/
    # non-PathLike type) must refuse the same bounded CapabilityPackageError
    # way as everything else, never leak a naked TypeError (from Path()
    # construction) or ValueError (os.lstat()/os.open() reject an embedded
    # NUL byte with "embedded null character/byte in path", which is NOT an
    # OSError subclass and was previously uncaught).
    try:
        source_root_path = Path(source_root)
    except TypeError:
        _refuse("source_root", "source_root_invalid")
    package_root_parts = package_root.split("/")

    # Step 1: lexical, non-resolving symlink checks (never call resolve()).
    try:
        source_root_lstat = os.lstat(str(source_root_path))
    except (OSError, ValueError):
        _refuse("source_root", "source_root_unavailable")
    if stat.S_ISLNK(source_root_lstat.st_mode) or not stat.S_ISDIR(source_root_lstat.st_mode):
        _refuse("source_root", "source_root_symlink_refused")

    lexical_path = source_root_path
    for part in package_root_parts:
        lexical_path = lexical_path / part
        try:
            component_lstat = os.lstat(str(lexical_path))
        except (OSError, ValueError):
            _refuse("package_root", "package_root_unavailable")
        if stat.S_ISLNK(component_lstat.st_mode):
            _refuse("package_root", "package_symlink_refused")

    all_retained: list[tuple[int, tuple]] = []
    package_dirs: dict[str, int] = {}

    def _track(fd: int) -> None:
        all_retained.append((fd, _stat_identity(os.fstat(fd))))

    try:
        try:
            root_fd = os.open(str(source_root_path), os.O_RDONLY | _O_NOFOLLOW | _O_DIRECTORY)
        except (OSError, ValueError):
            _refuse("source_root", "source_root_unavailable")
        _track(root_fd)

        current_fd = root_fd
        for part in package_root_parts:
            try:
                component_stat = os.lstat(part, dir_fd=current_fd)
            except OSError:
                _refuse("package_root", "package_root_unavailable")
            if stat.S_ISLNK(component_stat.st_mode):
                _refuse("package_root", "package_symlink_refused")
            if not stat.S_ISDIR(component_stat.st_mode):
                _refuse("package_root", "package_root_unavailable")
            try:
                child_fd = os.open(part, os.O_RDONLY | _O_NOFOLLOW | _O_DIRECTORY, dir_fd=current_fd)
            except OSError:
                _refuse("package_root", "package_symlink_refused")
            _track(child_fd)
            current_fd = child_fd
        package_root_fd = current_fd
        package_dirs[""] = package_root_fd

        traversal_counts = {"entries": 0, "dirs": 0}
        # Parent-descriptor + name for every declared directory opened
        # during the first census, used by the terminal-fence identity
        # check below: a directory removed and replaced by a fresh
        # same-named directory (a different inode) presents an IDENTICAL
        # name set to any purely name-based census.
        dir_parent_link: dict[str, tuple[int, str]] = {}
        # Retained-object bookkeeping for every DECLARED regular file: the
        # fd opened and retained for the whole verification transaction
        # (never reopened for hashing), the (parent_fd, name) pair used by
        # the post-census and terminal-fence freshness re-checks, and the
        # fstat captured the moment the fd was opened (the "census" stat
        # every later check compares against). Object retention -- not a
        # numeric (dev, ino) snapshot compared across two separate opens --
        # is what makes recycled-inode swaps distinguishable: as long as
        # this fd stays open, the kernel cannot free its inode for reuse by
        # a replacement created at the same name, so a genuine swap is
        # GUARANTEED to surface as a fresh, distinct object rather than
        # risking a numerically-coincident (dev, ino) collision on a
        # filesystem that aggressively recycles freed inode numbers.
        retained_file_fds: dict[str, int] = {}
        file_parent_link: dict[str, tuple[int, str]] = {}
        file_open_stat: dict[str, os.stat_result] = {}
        byte_counts = {"total": 0}

        def _check_traversal_entry(name: str, child_rel: str, counts: dict) -> None:
            if _utf8_byte_length(name, "package_root") > MAX_PATH_SEGMENT_BYTES:
                _refuse("package_root", "path_segment_too_long")
            if _utf8_byte_length(child_rel, "package_root") > MAX_RELATIVE_PATH_BYTES:
                _refuse("package_root", "path_too_long")
            counts["entries"] += 1
            if counts["entries"] > MAX_PACKAGE_TRAVERSAL_ENTRIES:
                _refuse("package_root", "too_many_entries")

        def _walk(dir_fd: int, rel_prefix: str, depth: int, file_entries: set[str], dir_entries: set[str]) -> None:
            # Stream the directory via os.scandir rather than materializing
            # the full listing with os.listdir: an attacker-controlled (or
            # merely pathological) directory must never be read into memory
            # before the per-entry budget below has a chance to stop the
            # scan -- the budget check runs on every entry as it is yielded,
            # and the iterator is abandoned (never drained) the moment it
            # trips.
            try:
                scan_iter = os.scandir(dir_fd)
            except OSError:
                _refuse("package_root", "package_root_unavailable")
            try:
                for entry in scan_iter:
                    name = entry.name
                    child_rel = name if rel_prefix == "" else f"{rel_prefix}/{name}"
                    # Bound the scan (bytes + total entry count) BEFORE
                    # lstat-ing or opening anything: an unbounded (or
                    # hostile) directory entry set must never be able to
                    # exhaust descriptors or recursion before any per-file
                    # bound applies.
                    _check_traversal_entry(name, child_rel, traversal_counts)
                    try:
                        entry_stat = os.lstat(name, dir_fd=dir_fd)
                    except OSError:
                        _refuse("package_root", "package_file_set_mismatch")
                    if stat.S_ISLNK(entry_stat.st_mode):
                        _refuse("package_root", "package_symlink_refused")
                    elif stat.S_ISDIR(entry_stat.st_mode):
                        # Refuse any directory not implied by the declaration
                        # BEFORE opening or recursing into it -- an undeclared
                        # directory (empty, or the root of an arbitrarily deep
                        # forest) must never consume a descriptor or a stack
                        # frame.
                        if child_rel not in allowed_dirs:
                            _refuse("package_root", "package_file_set_mismatch")
                        traversal_counts["dirs"] += 1
                        if traversal_counts["dirs"] > MAX_PACKAGE_DIRECTORIES:
                            _refuse("package_root", "too_many_directories")
                        new_depth = depth + 1
                        if new_depth > MAX_PACKAGE_TREE_DEPTH:
                            _refuse("package_root", "package_tree_too_deep")
                        try:
                            child_fd = os.open(
                                name, os.O_RDONLY | _O_NOFOLLOW | _O_DIRECTORY, dir_fd=dir_fd
                            )
                        except OSError:
                            _refuse("package_root", "package_symlink_refused")
                        _track(child_fd)
                        package_dirs[child_rel] = child_fd
                        dir_parent_link[child_rel] = (dir_fd, name)
                        dir_entries.add(child_rel)
                        _walk(child_fd, child_rel, new_depth, file_entries, dir_entries)
                    elif stat.S_ISREG(entry_stat.st_mode):
                        file_entries.add(child_rel)
                        declared_row = declared_by_path.get(child_rel)
                        if declared_row is None:
                            # Undeclared entries refuse BEFORE opening: the
                            # retained-descriptor budget below is spent only
                            # on DECLARED files (already bounded to
                            # MAX_PACKAGE_FILES by the trusted generation).
                            # This entry is still visible to the traversal
                            # budget above and to the first_file_entries !=
                            # declared_entries refusal once the walk
                            # completes, uniformly with every other kind of
                            # undeclared-shape mismatch.
                            continue

                        if _before_file_open is not None:
                            _before_file_open(child_rel)

                        try:
                            file_fd = os.open(
                                name,
                                os.O_RDONLY | _O_NOFOLLOW | _O_NONBLOCK | _O_CLOEXEC,
                                dir_fd=dir_fd,
                            )
                        except FileNotFoundError:
                            _refuse("package_root", "package_file_set_mismatch")
                        except PermissionError:
                            _refuse("package_root", "package_file_unreadable")
                        except OSError:
                            # Covers ELOOP (a symlink swapped in under
                            # O_NOFOLLOW), ENXIO/EOPNOTSUPP (a FIFO or
                            # socket swapped in), and any other open-time
                            # refusal. Never blocks: O_NONBLOCK makes a
                            # FIFO open return immediately even with no
                            # writer attached, so a hostile swap is refused
                            # rather than hung.
                            _refuse("package_root", "package_open_refused")

                        # RETAIN immediately: every refusal from this point
                        # forward still closes this fd via the outer
                        # `finally`'s all_retained sweep.
                        _track(file_fd)

                        try:
                            opened_stat = os.fstat(file_fd)
                        except OSError:
                            _refuse("package_root", "package_file_unreadable")

                        if not stat.S_ISREG(opened_stat.st_mode):
                            _refuse("package_root", "package_non_regular_file_refused")
                        if opened_stat.st_nlink != 1:
                            _refuse("package_root", "package_hardlink_refused")

                        # Census-to-open identity binding, now evaluated
                        # against the RETAINED fd's own fstat rather than a
                        # numeric snapshot compared across two independent
                        # opens.
                        if not _same_object(entry_stat, opened_stat):
                            _refuse("package_root", "package_file_identity_mismatch")

                        if opened_stat.st_size != declared_row.byte_length:
                            _refuse("package_root", "package_file_size_mismatch")
                        if opened_stat.st_size > MAX_PACKAGE_FILE_BYTES:
                            _refuse("package_root", "package_too_large")
                        byte_counts["total"] += opened_stat.st_size
                        if byte_counts["total"] > MAX_PACKAGE_TOTAL_BYTES:
                            _refuse("package_root", "package_too_large")

                        actual_executable = bool(
                            opened_stat.st_mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
                        )
                        if actual_executable != declared_row.executable:
                            _refuse("package_root", "package_executable_mismatch")

                        retained_file_fds[child_rel] = file_fd
                        file_parent_link[child_rel] = (dir_fd, name)
                        file_open_stat[child_rel] = opened_stat
                    else:
                        _refuse("package_root", "package_non_regular_file_refused")
            finally:
                scan_iter.close()

        first_file_entries: set[str] = set()
        first_dir_entries: set[str] = set()
        _walk(package_root_fd, "", 0, first_file_entries, first_dir_entries)

        if first_file_entries != declared_entries or first_dir_entries != allowed_dirs:
            _refuse("package_root", "package_file_set_mismatch")

        def _check_retained_file_identity() -> None:
            """Fresh no-follow lstat of every declared file's NAME, through
            its retained PARENT directory descriptor, required to resolve to
            the SAME object as that file's own retained fd.

            Mirrors the existing dir_parent_link check below but for files:
            a file removed and replaced by a fresh same-named file (even one
            with byte-for-byte identical declared content) does not
            necessarily disturb the retained fd's OWN fstat identity (only
            the PARENT's directory entries changed) -- only a fresh lookup
            of the name through the parent can see it. Called once right
            after the first census (closing races that unfold while later
            entries are still being walked) and once more at the terminal
            fence (closing races that unfold during hashing).
            """
            for child_rel, (parent_fd, name) in file_parent_link.items():
                try:
                    fresh_lstat = os.lstat(name, dir_fd=parent_fd)
                except OSError:
                    _refuse("package_root", "package_file_identity_mismatch")
                if not stat.S_ISREG(fresh_lstat.st_mode):
                    _refuse("package_root", "package_file_identity_mismatch")
                if not _same_object(fresh_lstat, file_open_stat[child_rel]):
                    _refuse("package_root", "package_file_identity_mismatch")

        # Point 3 of the retained-object design: re-verify every declared
        # file's identity immediately after the complete first census (and
        # after every per-file race hook that fired during it), before any
        # hashing begins.
        _check_retained_file_identity()

        actual_files_by_path: dict[str, CapabilityPackageFile] = {}

        for row in generation.files:
            file_fd = retained_file_fds[row.relative_path]
            first_stat = file_open_stat[row.relative_path]
            actual_executable = bool(
                first_stat.st_mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
            )

            # Hash and final-fstat the SAME retained fd opened during the
            # census -- never reopen the path for hashing. The fd's read
            # position starts at 0 (nothing has read from it before now),
            # so streaming begins from the start of the file exactly as a
            # fresh open would.
            hasher = hashlib.sha256()
            bytes_read = 0
            while True:
                try:
                    chunk = os.read(file_fd, _READ_CHUNK_BYTES)
                except OSError:
                    _refuse("package_root", "package_file_unreadable")
                if not chunk:
                    break
                bytes_read += len(chunk)
                # Refuse the moment cumulative bytes exceed either the
                # declared length or the absolute per-file ceiling --
                # never read to EOF first: a file that grows mid-read
                # (past the initial fstat above) must not be able to
                # make this loop do unbounded work before the drift is
                # detected.
                if bytes_read > row.byte_length or bytes_read > MAX_PACKAGE_FILE_BYTES:
                    _refuse("package_root", "package_file_size_mismatch")
                hasher.update(chunk)
                if _between_read_chunks is not None:
                    _between_read_chunks(row.relative_path)

            if bytes_read != row.byte_length:
                _refuse("package_root", "package_file_size_mismatch")

            if _before_final_stat is not None:
                _before_final_stat()

            final_stat = os.fstat(file_fd)
            if _stat_identity(final_stat) != _stat_identity(first_stat):
                _refuse("package_root", "package_file_identity_mismatch")

            actual_files_by_path[row.relative_path] = CapabilityPackageFile(
                relative_path=row.relative_path,
                sha256=hasher.hexdigest(),
                byte_length=first_stat.st_size,
                executable=actual_executable,
            )

        actual_files_ordered = tuple(actual_files_by_path[row.relative_path] for row in generation.files)
        recomputed_content_digest = capability_package_content_digest(actual_files_ordered)
        if recomputed_content_digest != generation.package_content_digest:
            _refuse("package_root", "package_content_digest_mismatch")

        skill_digest_pairs: list[tuple[str, str]] = []
        for skill in generation.skills:
            closure_files = tuple(actual_files_by_path[path] for path in skill.closure_paths)
            recomputed_skill_digest = effective_skill_content_digest(
                runtime_name=skill.runtime_name,
                entrypoint_path=skill.entrypoint_path,
                closure_files=closure_files,
            )
            if recomputed_skill_digest != skill.skill_content_digest:
                _refuse("package_root", "skill_content_digest_mismatch")
            skill_digest_pairs.append((skill.capability_id, recomputed_skill_digest))

        # Terminal fence (identity amendment §6): repeat the complete-tree
        # census through the retained descriptors and require every retained
        # directory's identity to be unchanged, closing the post-first-census
        # insertion/removal/rename race.
        if _before_terminal_fence is not None:
            _before_terminal_fence()

        second_file_entries: set[str] = set()
        second_dir_entries: set[str] = set()
        # A fresh, independent budget for the terminal-fence re-scan: a
        # hostile actor could grow a retained directory's entry count
        # AFTER the first census (but before the fence) just as easily as
        # before it, so this walk must never materialize an unbounded
        # listing either.
        second_traversal_counts = {"entries": 0}
        for rel_path, dir_fd in package_dirs.items():
            try:
                scan_iter = os.scandir(dir_fd)
            except OSError:
                _refuse("package_root", "package_file_set_mismatch")
            try:
                for entry in scan_iter:
                    name = entry.name
                    child_rel = name if rel_path == "" else f"{rel_path}/{name}"
                    _check_traversal_entry(name, child_rel, second_traversal_counts)
                    try:
                        entry_stat = os.lstat(name, dir_fd=dir_fd)
                    except OSError:
                        _refuse("package_root", "package_file_set_mismatch")
                    if stat.S_ISDIR(entry_stat.st_mode):
                        # Unlike the first census, a directory is NEVER
                        # skipped here: a directory inserted after the first
                        # census (even one holding its own file) must be
                        # visible to the terminal fence, not silently
                        # ignored.
                        second_dir_entries.add(child_rel)
                    elif stat.S_ISREG(entry_stat.st_mode):
                        second_file_entries.add(child_rel)
                    else:
                        _refuse("package_root", "package_file_set_mismatch")
            finally:
                scan_iter.close()

        if second_file_entries != declared_entries or second_dir_entries != allowed_dirs:
            _refuse("package_root", "package_file_set_mismatch")

        # Parent-entry-vs-retained-descriptor identity check: a declared
        # directory removed and replaced by a FRESH same-named directory
        # (a different inode) presents an identical name set to the
        # purely name-based census above, and does not necessarily disturb
        # any retained descriptor's own fstat identity either (only its
        # PARENT's directory entries changed). A fresh lookup of the name
        # through the parent is the only thing that can see it.
        for child_rel, (parent_fd, name) in dir_parent_link.items():
            try:
                fresh_lstat = os.lstat(name, dir_fd=parent_fd)
            except OSError:
                _refuse("package_root", "package_directory_identity_mismatch")
            if not stat.S_ISDIR(fresh_lstat.st_mode):
                _refuse("package_root", "package_directory_identity_mismatch")
            retained_fd = package_dirs[child_rel]
            retained_fstat = os.fstat(retained_fd)
            if not _same_object(fresh_lstat, retained_fstat):
                _refuse("package_root", "package_directory_identity_mismatch")

        # Point 5 of the retained-object design: repeat the SAME
        # retained-fd/path equality fence used post-census (point 3) once
        # more at the terminal fence, for every declared FILE -- closing
        # races that unfolded during the hash phase itself.
        _check_retained_file_identity()

        for fd, initial_identity in all_retained:
            if _stat_identity(os.fstat(fd)) != initial_identity:
                _refuse("package_root", "package_directory_identity_mismatch")

        return VerifiedCapabilityPackage(
            capability_id=generation.capability_id,
            generation=generation.generation,
            package_root=generation.package_root,
            package_content_digest=recomputed_content_digest,
            file_count=len(generation.files),
            total_bytes=sum(row.byte_length for row in generation.files),
            skill_content_digests=tuple(skill_digest_pairs),
            package_source_digest=generation.package_source_digest,
            package_generation_digest=generation.package_generation_digest,
            source_state=generation.source_state,
            revoked=generation.revoked,
        )
    finally:
        for fd, _identity in all_retained:
            try:
                os.close(fd)
            except OSError:
                pass
