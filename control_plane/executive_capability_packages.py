"""Immutable source-package identities and fail-closed local verification.

This module extends the existing execution-capability registry with pure data and
verification primitives. It does not install packages, start providers, select
workers, or own any lifecycle state.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import re
import stat
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Any

CAPABILITY_PACKAGE_CONTENT_SCHEMA = "mastermind.capability_package_content/v1"
CAPABILITY_PACKAGE_SOURCE_SCHEMA = "mastermind.capability_package_source/v1"
EFFECTIVE_SKILL_CLOSURE_SCHEMA = "mastermind.effective_skill_closure/v1"
EFFECTIVE_SKILL_GRANT_SCHEMA = "mastermind.effective_skill_grant/v1"
CAPABILITY_PACKAGE_GENERATION_SCHEMA = "mastermind.capability_package_generation/v1"

PACKAGE_KIND_SKILLS_ONLY_SOURCE = "skills-only-source"
PACKAGE_SOURCE_STATE_PROTECTED = "SOURCE_PROTECTED"

MAX_PACKAGE_FILES = 64
MAX_PACKAGE_FILE_BYTES = 1024 * 1024
MAX_PACKAGE_TOTAL_BYTES = 8 * 1024 * 1024
MAX_SKILLS_PER_PACKAGE = 32
MAX_CLOSURE_FILES = 32
MAX_RELATIVE_PATH_BYTES = 512
MAX_REPOSITORY_BYTES = 192

_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,95}$")
_RUNTIME_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
_GIT_OID_RE = re.compile(r"^[0-9a-f]{40}$")
_REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]{1,96}/[A-Za-z0-9_.-]{1,96}$")

_PACKAGE_KEYS = frozenset(
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
_FILE_KEYS = frozenset({"relative_path", "sha256", "byte_length", "executable"})
_SKILL_KEYS = frozenset(
    {
        "runtime_name",
        "entrypoint_path",
        "closure_paths",
        "skill_content_digest",
        "grant_digest",
    }
)


class CapabilityPackageError(ValueError):
    """The immutable package contract or opened source snapshot is unsafe."""


def _canonical_bytes(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise CapabilityPackageError("canonical package projection is invalid") from exc


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _identifier(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or _ID_RE.fullmatch(value) is None:
        raise CapabilityPackageError(f"{field} must be a bounded lowercase identifier")
    return value


def _runtime_name(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or _RUNTIME_NAME_RE.fullmatch(value) is None:
        raise CapabilityPackageError(f"{field} must be a bounded lowercase runtime name")
    return value


def _digest_value(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or _DIGEST_RE.fullmatch(value) is None:
        raise CapabilityPackageError(f"{field} must be a lowercase SHA-256 digest")
    return value


def _git_oid(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or _GIT_OID_RE.fullmatch(value) is None:
        raise CapabilityPackageError(f"{field} must be a lowercase 40-hex Git object ID")
    return value


def _repository(value: Any) -> str:
    if (
        not isinstance(value, str)
        or len(value.encode("utf-8")) > MAX_REPOSITORY_BYTES
        or _REPOSITORY_RE.fullmatch(value) is None
    ):
        raise CapabilityPackageError("repository must be a bounded owner/name identity")
    return value


def _relative_path(value: Any, *, field: str) -> str:
    if not isinstance(value, str):
        raise CapabilityPackageError(f"{field} must be a package-relative POSIX path")
    if not value or len(value.encode("utf-8")) > MAX_RELATIVE_PATH_BYTES:
        raise CapabilityPackageError(f"{field} must be a bounded package-relative POSIX path")
    if value.startswith("/") or value.endswith("/") or "\\" in value:
        raise CapabilityPackageError(f"{field} must be a normalized package-relative POSIX path")
    if any(ord(char) < 0x20 or ord(char) == 0x7F for char in value):
        raise CapabilityPackageError(f"{field} contains a forbidden control character")
    parts = value.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise CapabilityPackageError(f"{field} contains a forbidden path component")
    normalized = PurePosixPath(value).as_posix()
    if normalized != value:
        raise CapabilityPackageError(f"{field} must be normalized")
    return value


def _closed_keys(raw: Mapping[str, object], expected: frozenset[str], *, field: str) -> None:
    if set(raw) != expected:
        raise CapabilityPackageError(f"{field} fields drifted")


def _canonical_file_projection(row: "CapabilityPackageFile") -> dict[str, object]:
    return {
        "relative_path": row.relative_path,
        "sha256": row.sha256,
        "byte_length": row.byte_length,
        "executable": row.executable,
    }


@dataclasses.dataclass(frozen=True)
class CapabilityPackageFile:
    relative_path: str
    sha256: str
    byte_length: int
    executable: bool

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "relative_path",
            _relative_path(self.relative_path, field="package file relative_path"),
        )
        object.__setattr__(
            self,
            "sha256",
            _digest_value(self.sha256, field="package file sha256"),
        )
        if type(self.byte_length) is not int or not (
            0 <= self.byte_length <= MAX_PACKAGE_FILE_BYTES
        ):
            raise CapabilityPackageError("package file byte_length is out of bounds")
        if type(self.executable) is not bool:
            raise CapabilityPackageError("package file executable must be boolean")


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
    package_source_digest: str
    package_generation_digest: str
    file_count: int
    total_bytes: int
    skill_content_digests: tuple[tuple[str, str], ...]


def _validated_file_rows(
    files: Sequence[CapabilityPackageFile], *, require_sorted: bool
) -> tuple[CapabilityPackageFile, ...]:
    if isinstance(files, (str, bytes)) or not isinstance(files, Sequence):
        raise CapabilityPackageError("package files must be a bounded sequence")
    rows = tuple(files)
    if not rows or len(rows) > MAX_PACKAGE_FILES:
        raise CapabilityPackageError("package files must contain 1-64 rows")
    if any(not isinstance(row, CapabilityPackageFile) for row in rows):
        raise CapabilityPackageError("package files contain an invalid row")
    ordered = tuple(sorted(rows, key=lambda row: row.relative_path.encode("utf-8")))
    if require_sorted and rows != ordered:
        raise CapabilityPackageError("package files must be sorted by relative_path")
    paths = [row.relative_path for row in ordered]
    if len(set(paths)) != len(paths):
        raise CapabilityPackageError("package files contain a duplicate relative_path")
    folded = [path.casefold() for path in paths]
    if len(set(folded)) != len(folded):
        raise CapabilityPackageError("package files contain a case-fold collision")
    total = sum(row.byte_length for row in ordered)
    if total > MAX_PACKAGE_TOTAL_BYTES:
        raise CapabilityPackageError("package total bytes exceed the reviewed bound")
    return ordered


def capability_package_content_digest(
    files: tuple[CapabilityPackageFile, ...],
) -> str:
    ordered = _validated_file_rows(files, require_sorted=False)
    return _digest(
        {
            "schema_version": CAPABILITY_PACKAGE_CONTENT_SCHEMA,
            "files": [_canonical_file_projection(row) for row in ordered],
        }
    )


def effective_skill_content_digest(
    *,
    runtime_name: str,
    entrypoint_path: str,
    closure_files: tuple[CapabilityPackageFile, ...],
) -> str:
    name = _runtime_name(runtime_name, field="skill runtime_name")
    entrypoint = _relative_path(entrypoint_path, field="skill entrypoint_path")
    rows = _validated_file_rows(closure_files, require_sorted=False)
    if len(rows) > MAX_CLOSURE_FILES:
        raise CapabilityPackageError("skill closure exceeds the reviewed file bound")
    if entrypoint not in {row.relative_path for row in rows}:
        raise CapabilityPackageError("skill closure does not contain its entrypoint")
    return _digest(
        {
            "schema_version": EFFECTIVE_SKILL_CLOSURE_SCHEMA,
            "skill_name": name,
            "entrypoint_path": entrypoint,
            "files": [_canonical_file_projection(row) for row in rows],
        }
    )


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
    return _digest(
        {
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
    )


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
    return _digest(
        {
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
    )


def _package_generation_digest(
    *,
    capability_id: str,
    generation: str,
    source_state: str,
    revoked: bool,
    package_source_digest: str,
    skills: tuple[EffectiveSkillGrant, ...],
) -> str:
    return _digest(
        {
            "schema_version": CAPABILITY_PACKAGE_GENERATION_SCHEMA,
            "capability_id": capability_id,
            "generation": generation,
            "source_state": source_state,
            "revoked": revoked,
            "package_source_digest": package_source_digest,
            "skills": [
                {
                    "capability_id": skill.capability_id,
                    "grant_digest": skill.grant_digest,
                }
                for skill in skills
            ],
        }
    )


def _parse_file_rows(raw: object) -> tuple[CapabilityPackageFile, ...]:
    if not isinstance(raw, list):
        raise CapabilityPackageError("package files must be a list")
    rows: list[CapabilityPackageFile] = []
    for value in raw:
        if not isinstance(value, Mapping):
            raise CapabilityPackageError("package file row must be an object")
        _closed_keys(value, _FILE_KEYS, field="package file")
        rows.append(
            CapabilityPackageFile(
                relative_path=value.get("relative_path"),
                sha256=value.get("sha256"),
                byte_length=value.get("byte_length"),
                executable=value.get("executable"),
            )
        )
    return _validated_file_rows(tuple(rows), require_sorted=True)


def build_capability_package_generation(
    *,
    capability_id: str,
    raw: Mapping[str, object],
) -> CapabilityPackageGeneration:
    package_id = _identifier(capability_id, field="package capability_id")
    if not isinstance(raw, Mapping):
        raise CapabilityPackageError("capability package must be an object")
    _closed_keys(raw, _PACKAGE_KEYS, field="capability package")

    kind = raw.get("kind")
    if kind != PACKAGE_KIND_SKILLS_ONLY_SOURCE:
        raise CapabilityPackageError("capability package kind is unsupported")
    repository = _repository(raw.get("repository"))
    source_commit = _git_oid(raw.get("source_commit"), field="source_commit")
    source_tree_sha = _git_oid(raw.get("source_tree_sha"), field="source_tree_sha")
    package_root = _relative_path(raw.get("package_root"), field="package_root")
    manifest_path = _relative_path(raw.get("manifest_path"), field="manifest_path")
    generation = _identifier(raw.get("generation"), field="package generation")
    if raw.get("source_state") != PACKAGE_SOURCE_STATE_PROTECTED:
        raise CapabilityPackageError("capability package source_state is unsupported")
    source_state = PACKAGE_SOURCE_STATE_PROTECTED
    revoked = raw.get("revoked")
    if type(revoked) is not bool:
        raise CapabilityPackageError("capability package revoked must be boolean")
    required_apps = raw.get("required_app_references")
    if required_apps != []:
        raise CapabilityPackageError("required_app_references must remain empty")
    required_app_references: tuple[str, ...] = ()

    files = _parse_file_rows(raw.get("files"))
    if manifest_path not in {row.relative_path for row in files}:
        raise CapabilityPackageError("capability package manifest is not in the file inventory")
    computed_content_digest = capability_package_content_digest(files)
    declared_content_digest = _digest_value(
        raw.get("package_content_digest"), field="package_content_digest"
    )
    if declared_content_digest != computed_content_digest:
        raise CapabilityPackageError("package_content_digest does not match the file inventory")

    computed_source_digest = _package_source_digest(
        capability_id=package_id,
        kind=kind,
        repository=repository,
        source_commit=source_commit,
        source_tree_sha=source_tree_sha,
        package_root=package_root,
        manifest_path=manifest_path,
        package_content_digest=computed_content_digest,
        required_app_references=required_app_references,
    )
    declared_source_digest = _digest_value(
        raw.get("package_source_digest"), field="package_source_digest"
    )
    if declared_source_digest != computed_source_digest:
        raise CapabilityPackageError("package_source_digest does not match package provenance")

    skills_raw = raw.get("skills")
    if (
        not isinstance(skills_raw, Mapping)
        or not skills_raw
        or len(skills_raw) > MAX_SKILLS_PER_PACKAGE
    ):
        raise CapabilityPackageError("capability package skills must contain 1-32 grants")
    file_by_path = {row.relative_path: row for row in files}
    skills: list[EffectiveSkillGrant] = []
    runtime_names: set[str] = set()
    raw_skill_ids = list(skills_raw)
    if raw_skill_ids != sorted(raw_skill_ids, key=lambda item: str(item).encode("utf-8")):
        raise CapabilityPackageError("capability package skills must be sorted by capability_id")
    for raw_skill_id, value in skills_raw.items():
        skill_id = _identifier(raw_skill_id, field="skill capability_id")
        if not isinstance(value, Mapping):
            raise CapabilityPackageError("skill grant must be an object")
        _closed_keys(value, _SKILL_KEYS, field="skill grant")
        runtime_name = _runtime_name(
            value.get("runtime_name"), field="skill runtime_name"
        )
        if runtime_name in runtime_names:
            raise CapabilityPackageError("package contains a duplicate skill runtime_name")
        runtime_names.add(runtime_name)
        entrypoint = _relative_path(
            value.get("entrypoint_path"), field="skill entrypoint_path"
        )
        raw_closure_paths = value.get("closure_paths")
        if (
            not isinstance(raw_closure_paths, list)
            or not raw_closure_paths
            or len(raw_closure_paths) > MAX_CLOSURE_FILES
        ):
            raise CapabilityPackageError("skill closure_paths must contain 1-32 paths")
        closure_paths = tuple(
            _relative_path(item, field="skill closure path")
            for item in raw_closure_paths
        )
        if closure_paths != tuple(
            sorted(closure_paths, key=lambda item: item.encode("utf-8"))
        ):
            raise CapabilityPackageError("skill closure_paths must be sorted")
        if len(set(closure_paths)) != len(closure_paths):
            raise CapabilityPackageError("skill closure_paths contain a duplicate")
        if len({item.casefold() for item in closure_paths}) != len(closure_paths):
            raise CapabilityPackageError("skill closure_paths contain a case-fold collision")
        if entrypoint not in closure_paths:
            raise CapabilityPackageError("skill closure does not contain its entrypoint")
        try:
            closure_files = tuple(file_by_path[item] for item in closure_paths)
        except KeyError as exc:
            raise CapabilityPackageError("skill closure references an unknown package file") from exc
        computed_skill_content_digest = effective_skill_content_digest(
            runtime_name=runtime_name,
            entrypoint_path=entrypoint,
            closure_files=closure_files,
        )
        declared_skill_content_digest = _digest_value(
            value.get("skill_content_digest"), field="skill_content_digest"
        )
        if declared_skill_content_digest != computed_skill_content_digest:
            raise CapabilityPackageError(
                "skill_content_digest does not match the effective closure"
            )
        computed_grant_digest = _skill_grant_digest(
            capability_id=skill_id,
            runtime_name=runtime_name,
            entrypoint_path=entrypoint,
            closure_paths=closure_paths,
            skill_content_digest=computed_skill_content_digest,
            package_capability_id=package_id,
            package_generation=generation,
            package_source_digest=computed_source_digest,
        )
        declared_grant_digest = _digest_value(
            value.get("grant_digest"), field="skill grant_digest"
        )
        if declared_grant_digest != computed_grant_digest:
            raise CapabilityPackageError("skill grant_digest does not match the grant")
        skills.append(
            EffectiveSkillGrant(
                capability_id=skill_id,
                runtime_name=runtime_name,
                entrypoint_path=entrypoint,
                closure_paths=closure_paths,
                skill_content_digest=computed_skill_content_digest,
                package_capability_id=package_id,
                package_generation=generation,
                package_source_digest=computed_source_digest,
                grant_digest=computed_grant_digest,
            )
        )
    skill_tuple = tuple(skills)
    computed_generation_digest = _package_generation_digest(
        capability_id=package_id,
        generation=generation,
        source_state=source_state,
        revoked=revoked,
        package_source_digest=computed_source_digest,
        skills=skill_tuple,
    )
    declared_generation_digest = _digest_value(
        raw.get("package_generation_digest"), field="package_generation_digest"
    )
    if declared_generation_digest != computed_generation_digest:
        raise CapabilityPackageError(
            "package_generation_digest does not match the package generation"
        )

    return CapabilityPackageGeneration(
        capability_id=package_id,
        kind=kind,
        repository=repository,
        source_commit=source_commit,
        source_tree_sha=source_tree_sha,
        package_root=package_root,
        manifest_path=manifest_path,
        generation=generation,
        source_state=source_state,
        revoked=revoked,
        package_content_digest=computed_content_digest,
        package_source_digest=computed_source_digest,
        files=files,
        skills=skill_tuple,
        required_app_references=required_app_references,
        package_generation_digest=computed_generation_digest,
    )


_StatIdentity = tuple[int, int, int, int, int, int, int, int, int]


def _stat_identity(value: os.stat_result) -> _StatIdentity:
    return (
        value.st_dev,
        value.st_ino,
        value.st_mode,
        value.st_nlink,
        value.st_uid,
        value.st_gid,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )


def _lexical_absolute(path: Path) -> Path:
    expanded = path.expanduser()
    if not expanded.is_absolute():
        expanded = Path(os.path.abspath(os.fspath(expanded)))
    return expanded


def _reject_symlink_components(path: Path) -> None:
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current = current / part
        try:
            info = os.lstat(current)
        except OSError as exc:
            raise CapabilityPackageError("source root is unavailable") from exc
        if stat.S_ISLNK(info.st_mode):
            raise CapabilityPackageError("source root contains a symlink component")


def _open_directory(name: str | Path, *, dir_fd: int | None = None) -> int:
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    directory = getattr(os, "O_DIRECTORY", 0)
    if not nofollow or not directory:
        raise CapabilityPackageError("host lacks required no-follow directory primitives")
    try:
        return os.open(
            os.fspath(name),
            os.O_RDONLY | nofollow | directory,
            dir_fd=dir_fd,
        )
    except OSError as exc:
        raise CapabilityPackageError("package directory could not be opened safely") from exc


def _census_open_directories(
    package_fd: int,
) -> tuple[tuple[str, ...], tuple[str, ...], dict[str, int], dict[str, tuple[int, int, int, int, int, int, int, int, int]]]:
    file_paths: list[str] = []
    directory_paths: list[str] = []
    retained: dict[str, int] = {"": os.dup(package_fd)}
    identities: dict[str, tuple[int, int, int, int, int, int, int, int, int]] = {
        "": _stat_identity(os.fstat(retained[""]))
    }

    def walk(relative_dir: str) -> None:
        fd = retained[relative_dir]
        try:
            names = sorted(os.listdir(fd), key=lambda item: item.encode("utf-8"))
        except OSError as exc:
            raise CapabilityPackageError("package tree could not be enumerated safely") from exc
        folded: set[str] = set()
        for name in names:
            if name.casefold() in folded:
                raise CapabilityPackageError("package tree contains a case-fold collision")
            folded.add(name.casefold())
            relative = f"{relative_dir}/{name}" if relative_dir else name
            normalized = _relative_path(relative, field="opened package path")
            try:
                info = os.stat(name, dir_fd=fd, follow_symlinks=False)
            except OSError as exc:
                raise CapabilityPackageError("package tree entry could not be inspected") from exc
            if stat.S_ISLNK(info.st_mode):
                raise CapabilityPackageError("package tree contains a symlink")
            if stat.S_ISDIR(info.st_mode):
                child = _open_directory(name, dir_fd=fd)
                child_info = os.fstat(child)
                if not stat.S_ISDIR(child_info.st_mode):
                    os.close(child)
                    raise CapabilityPackageError("package directory identity changed")
                retained[normalized] = child
                identities[normalized] = _stat_identity(child_info)
                directory_paths.append(normalized)
                walk(normalized)
            elif stat.S_ISREG(info.st_mode):
                file_paths.append(normalized)
            else:
                raise CapabilityPackageError("package tree contains a non-regular entry")

    try:
        walk("")
        return (
            tuple(sorted(file_paths, key=lambda item: item.encode("utf-8"))),
            tuple(sorted(directory_paths, key=lambda item: item.encode("utf-8"))),
            retained,
            identities,
        )
    except BaseException:
        for fd in retained.values():
            try:
                os.close(fd)
            except OSError:
                pass
        raise


def _census_temporary(package_fd: int) -> tuple[tuple[str, ...], tuple[str, ...]]:
    files: list[str] = []
    directories: list[str] = []

    def walk(fd: int, relative_dir: str) -> None:
        try:
            names = sorted(os.listdir(fd), key=lambda item: item.encode("utf-8"))
        except OSError as exc:
            raise CapabilityPackageError("package tree could not be re-enumerated") from exc
        folded: set[str] = set()
        for name in names:
            if name.casefold() in folded:
                raise CapabilityPackageError("package tree contains a case-fold collision")
            folded.add(name.casefold())
            relative = f"{relative_dir}/{name}" if relative_dir else name
            normalized = _relative_path(relative, field="opened package path")
            try:
                info = os.stat(name, dir_fd=fd, follow_symlinks=False)
            except OSError as exc:
                raise CapabilityPackageError("package tree entry could not be re-inspected") from exc
            if stat.S_ISLNK(info.st_mode):
                raise CapabilityPackageError("package tree contains a symlink")
            if stat.S_ISDIR(info.st_mode):
                directories.append(normalized)
                child = _open_directory(name, dir_fd=fd)
                try:
                    walk(child, normalized)
                finally:
                    os.close(child)
            elif stat.S_ISREG(info.st_mode):
                files.append(normalized)
            else:
                raise CapabilityPackageError("package tree contains a non-regular entry")

    walk(package_fd, "")
    return (
        tuple(sorted(files, key=lambda item: item.encode("utf-8"))),
        tuple(sorted(directories, key=lambda item: item.encode("utf-8"))),
    )


def _declared_directories(files: tuple[CapabilityPackageFile, ...]) -> tuple[str, ...]:
    values: set[str] = set()
    for row in files:
        parts = row.relative_path.split("/")[:-1]
        for end in range(1, len(parts) + 1):
            values.add("/".join(parts[:end]))
    return tuple(sorted(values, key=lambda item: item.encode("utf-8")))


def _hash_opened_file(
    *,
    parent_fd: int,
    name: str,
    row: CapabilityPackageFile,
) -> tuple[str, tuple[int, int, int, int, int, int, int, int, int]]:
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    if not nofollow:
        raise CapabilityPackageError("host lacks required no-follow file primitive")
    try:
        fd = os.open(name, os.O_RDONLY | nofollow, dir_fd=parent_fd)
    except OSError as exc:
        raise CapabilityPackageError("package file could not be opened safely") from exc
    try:
        first = os.fstat(fd)
        if not stat.S_ISREG(first.st_mode):
            raise CapabilityPackageError("package file is not regular")
        if first.st_nlink != 1:
            raise CapabilityPackageError("package file has an unsupported link count")
        if first.st_size != row.byte_length or first.st_size > MAX_PACKAGE_FILE_BYTES:
            raise CapabilityPackageError("package file byte length drifted")
        actual_executable = bool(stat.S_IMODE(first.st_mode) & 0o111)
        if actual_executable is not row.executable:
            raise CapabilityPackageError("package file executable bit drifted")
        hasher = hashlib.sha256()
        total = 0
        while True:
            chunk = os.read(fd, 64 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > row.byte_length or total > MAX_PACKAGE_FILE_BYTES:
                raise CapabilityPackageError("package file exceeded its declared bound")
            hasher.update(chunk)
        final = os.fstat(fd)
        if _stat_identity(first) != _stat_identity(final):
            raise CapabilityPackageError("package file changed while being read")
        if total != row.byte_length or hasher.hexdigest() != row.sha256:
            raise CapabilityPackageError("package file content drifted")
        try:
            path_stat = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        except OSError as exc:
            raise CapabilityPackageError("package file path changed while being read") from exc
        if _stat_identity(first) != _stat_identity(path_stat):
            raise CapabilityPackageError("package file path identity changed")
        return hasher.hexdigest(), _stat_identity(first)
    finally:
        os.close(fd)


def _verify_capability_package_source(
    source_root: Path,
    generation: CapabilityPackageGeneration,
    *,
    before_final_census: Callable[[], None] | None = None,
) -> VerifiedCapabilityPackage:
    if not isinstance(generation, CapabilityPackageGeneration):
        raise CapabilityPackageError("generation must be a CapabilityPackageGeneration")
    lexical_root = _lexical_absolute(Path(source_root))
    _reject_symlink_components(lexical_root)
    source_fd = _open_directory(lexical_root)
    path_component_fds: list[int] = [source_fd]
    path_component_identities = [_stat_identity(os.fstat(source_fd))]
    retained: dict[str, int] = {}
    try:
        current_fd = source_fd
        for component in generation.package_root.split("/"):
            child = _open_directory(component, dir_fd=current_fd)
            path_component_fds.append(child)
            path_component_identities.append(_stat_identity(os.fstat(child)))
            current_fd = child
        package_fd = current_fd
        initial_files, initial_dirs, retained, retained_identities = (
            _census_open_directories(package_fd)
        )
        declared_files = tuple(row.relative_path for row in generation.files)
        declared_dirs = _declared_directories(generation.files)
        if initial_files != declared_files or initial_dirs != declared_dirs:
            raise CapabilityPackageError("opened package tree does not match the declaration")

        file_identities = {}
        for row in generation.files:
            path = PurePosixPath(row.relative_path)
            parent_path = path.parent.as_posix()
            if parent_path == ".":
                parent_path = ""
            parent_fd = retained.get(parent_path)
            if parent_fd is None:
                raise CapabilityPackageError("declared package file parent is unavailable")
            _, identity = _hash_opened_file(
                parent_fd=parent_fd,
                name=path.name,
                row=row,
            )
            file_identities[row.relative_path] = identity

        if capability_package_content_digest(generation.files) != generation.package_content_digest:
            raise CapabilityPackageError("opened package content digest is inconsistent")
        file_by_path = {row.relative_path: row for row in generation.files}
        verified_skills = []
        for skill in generation.skills:
            closure = tuple(file_by_path[path] for path in skill.closure_paths)
            observed = effective_skill_content_digest(
                runtime_name=skill.runtime_name,
                entrypoint_path=skill.entrypoint_path,
                closure_files=closure,
            )
            if observed != skill.skill_content_digest:
                raise CapabilityPackageError("opened skill closure digest drifted")
            verified_skills.append((skill.capability_id, observed))

        if before_final_census is not None:
            before_final_census()

        final_files, final_dirs = _census_temporary(package_fd)
        if (
            final_files != initial_files
            or final_dirs != initial_dirs
            or final_files != declared_files
            or final_dirs != declared_dirs
        ):
            raise CapabilityPackageError("package tree changed after the initial census")
        for relative_dir, fd in retained.items():
            if _stat_identity(os.fstat(fd)) != retained_identities[relative_dir]:
                raise CapabilityPackageError("package directory changed during verification")
        for fd, identity in zip(path_component_fds, path_component_identities, strict=True):
            if _stat_identity(os.fstat(fd)) != identity:
                raise CapabilityPackageError("source package path changed during verification")
        for row in generation.files:
            path = PurePosixPath(row.relative_path)
            parent_path = path.parent.as_posix()
            if parent_path == ".":
                parent_path = ""
            try:
                current = os.stat(
                    path.name,
                    dir_fd=retained[parent_path],
                    follow_symlinks=False,
                )
            except OSError as exc:
                raise CapabilityPackageError("package file vanished after verification") from exc
            if _stat_identity(current) != file_identities[row.relative_path]:
                raise CapabilityPackageError("package file changed after verification")

        return VerifiedCapabilityPackage(
            capability_id=generation.capability_id,
            generation=generation.generation,
            package_root=generation.package_root,
            package_content_digest=generation.package_content_digest,
            package_source_digest=generation.package_source_digest,
            package_generation_digest=generation.package_generation_digest,
            file_count=len(generation.files),
            total_bytes=sum(row.byte_length for row in generation.files),
            skill_content_digests=tuple(verified_skills),
        )
    except CapabilityPackageError:
        raise
    except (KeyError, OSError, ValueError) as exc:
        raise CapabilityPackageError("capability package source verification failed") from exc
    finally:
        for fd in retained.values():
            try:
                os.close(fd)
            except OSError:
                pass
        for fd in reversed(path_component_fds):
            try:
                os.close(fd)
            except OSError:
                pass


def verify_capability_package_source(
    source_root: Path,
    generation: CapabilityPackageGeneration,
) -> VerifiedCapabilityPackage:
    """Verify one exact complete package tree without following links.

    The public result contains only bounded source identities. No installation,
    provider, credential, route, lifecycle, or mutable runtime state is created.
    """

    return _verify_capability_package_source(Path(source_root), generation)


__all__ = [
    "CAPABILITY_PACKAGE_CONTENT_SCHEMA",
    "CAPABILITY_PACKAGE_GENERATION_SCHEMA",
    "CAPABILITY_PACKAGE_SOURCE_SCHEMA",
    "EFFECTIVE_SKILL_CLOSURE_SCHEMA",
    "EFFECTIVE_SKILL_GRANT_SCHEMA",
    "MAX_CLOSURE_FILES",
    "MAX_PACKAGE_FILES",
    "MAX_PACKAGE_FILE_BYTES",
    "MAX_PACKAGE_TOTAL_BYTES",
    "MAX_SKILLS_PER_PACKAGE",
    "PACKAGE_KIND_SKILLS_ONLY_SOURCE",
    "PACKAGE_SOURCE_STATE_PROTECTED",
    "CapabilityPackageError",
    "CapabilityPackageFile",
    "CapabilityPackageGeneration",
    "EffectiveSkillGrant",
    "VerifiedCapabilityPackage",
    "build_capability_package_generation",
    "capability_package_content_digest",
    "effective_skill_content_digest",
    "verify_capability_package_source",
]
