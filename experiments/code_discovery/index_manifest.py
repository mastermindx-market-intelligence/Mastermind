"""Reviewed immutable source snapshots for the disposable Z0 index.

The manifest is host-owned input.  It deliberately names local snapshot roots,
but those roots are excluded from the material digest and never cross the
model-facing discovery facade.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Final


class IndexManifestError(ValueError):
    """A reviewed source manifest is not a safe immutable index input."""


_SCHEMA_VERSION: Final = "mastermind.codeintel_index_manifest.v1"
_MAX_REPOSITORIES: Final = 32
_MAX_PATH_RULES: Final = 32
_LOGICAL_ID_RE: Final = re.compile(r"[a-z0-9][a-z0-9._-]{0,127}\Z")
_REPOSITORY_NAME_RE: Final = re.compile(
    r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}/[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z"
)
_SHA1_RE: Final = re.compile(r"[0-9a-f]{40}\Z")
_SHA256_RE: Final = re.compile(r"[0-9a-f]{64}\Z")
_TOP_LEVEL_FIELDS: Final = frozenset({"schema_version", "repositories"})
_REPOSITORY_FIELDS: Final = frozenset(
    {
        "repository_id",
        "repository_name",
        "source_snapshot_root",
        "ref_label",
        "commit_sha",
        "included_prefixes",
        "excluded_globs",
        "source_tree_digest",
    }
)


@dataclass(frozen=True)
class RepositorySpec:
    """One exact repository/ref source snapshot eligible for Z0 indexing."""

    repository_id: str
    repository_name: str
    source_snapshot_root: Path
    ref_label: str
    commit_sha: str
    included_prefixes: tuple[str, ...]
    excluded_globs: tuple[str, ...]
    source_tree_digest: str

    @property
    def shard_namespace(self) -> str:
        """Return a stable identity namespace that cannot collapse basenames."""

        material = "\0".join(
            (
                self.repository_id,
                self.repository_name,
                self.ref_label,
                self.commit_sha,
                self.source_tree_digest,
            )
        ).encode("utf-8")
        return f"z0-{hashlib.sha256(material).hexdigest()[:24]}"


@dataclass(frozen=True)
class IndexManifest:
    """Validated material source rows and their host-local snapshot locations."""

    schema_version: str
    repositories: tuple[RepositorySpec, ...]


def load_index_manifest(path: Path) -> IndexManifest:
    """Load a closed manifest and verify every referenced immutable snapshot."""

    manifest_path = Path(path)
    _require_regular_file(manifest_path, "manifest")
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise IndexManifestError("manifest must be valid UTF-8 JSON") from error
    if not isinstance(payload, Mapping):
        raise IndexManifestError("manifest must be an object")
    _reject_unknown(payload, _TOP_LEVEL_FIELDS, "manifest")
    if payload.get("schema_version") != _SCHEMA_VERSION:
        raise IndexManifestError(f"schema_version must equal {_SCHEMA_VERSION!r}")

    raw_repositories = payload.get("repositories")
    if not isinstance(raw_repositories, list) or not raw_repositories:
        raise IndexManifestError("repositories must be a non-empty list")
    if len(raw_repositories) > _MAX_REPOSITORIES:
        raise IndexManifestError(f"repositories must contain at most {_MAX_REPOSITORIES} rows")

    repositories = tuple(
        _parse_repository(raw, position=index)
        for index, raw in enumerate(raw_repositories, start=1)
    )
    _reject_duplicate_identities(repositories)
    return IndexManifest(schema_version=_SCHEMA_VERSION, repositories=repositories)


def material_source_manifest_digest(manifest: IndexManifest) -> str:
    """Hash source identity and policy, excluding host-local snapshot roots."""

    rows = [
        {
            "repository_id": spec.repository_id,
            "repository_name": spec.repository_name,
            "ref_label": spec.ref_label,
            "commit_sha": spec.commit_sha,
            "included_prefixes": spec.included_prefixes,
            "excluded_globs": spec.excluded_globs,
            "source_tree_digest": spec.source_tree_digest,
        }
        for spec in manifest.repositories
    ]
    rows.sort(
        key=lambda row: (
            row["repository_id"],
            row["repository_name"],
            row["ref_label"],
        )
    )
    encoded = json.dumps(
        {"schema_version": manifest.schema_version, "repositories": rows},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")
    return hashlib.sha256(encoded).hexdigest()


def source_tree_digest(
    source_snapshot_root: Path,
    included_prefixes: Sequence[str],
    excluded_globs: Sequence[str],
) -> str:
    """Hash the sorted, selected regular files in a clean exact Git snapshot."""

    root = _validate_snapshot_root(Path(source_snapshot_root))
    includes = _path_rules(included_prefixes, field="included_prefixes", required=True)
    excludes = _path_rules(excluded_globs, field="excluded_globs", required=False)
    return _digest_selected_files(root, includes, excludes)


def _parse_repository(raw: object, *, position: int) -> RepositorySpec:
    if not isinstance(raw, Mapping):
        raise IndexManifestError(f"repository row {position} must be an object")
    _reject_unknown(raw, _REPOSITORY_FIELDS, f"repository row {position}")

    repository_id = _logical_identifier(raw.get("repository_id"), "repository_id")
    repository_name = _repository_name(raw.get("repository_name"))
    ref_label = _logical_identifier(raw.get("ref_label"), "ref_label")
    commit_sha = _digest(raw.get("commit_sha"), field="commit_sha", pattern=_SHA1_RE)
    expected_tree_digest = _digest(
        raw.get("source_tree_digest"), field="source_tree_digest", pattern=_SHA256_RE
    )

    root_value = raw.get("source_snapshot_root")
    if not isinstance(root_value, str) or not root_value:
        raise IndexManifestError("source_snapshot_root must be an absolute host path")
    root = Path(root_value)
    if not root.is_absolute():
        raise IndexManifestError("source_snapshot_root must be an absolute host path")
    root = _validate_snapshot_root(root)

    includes = _path_rules(
        raw.get("included_prefixes"), field="included_prefixes", required=True
    )
    excludes = _path_rules(
        raw.get("excluded_globs"), field="excluded_globs", required=False
    )
    observed_commit = _git_stdout(root, "rev-parse", "--verify", "HEAD")
    if observed_commit != commit_sha:
        raise IndexManifestError(
            f"commit_sha does not match exact snapshot HEAD for {repository_id}"
        )

    observed_tree_digest = _digest_selected_files(root, includes, excludes)
    if observed_tree_digest != expected_tree_digest:
        raise IndexManifestError(
            f"source_tree_digest does not match selected source for {repository_id}"
        )

    return RepositorySpec(
        repository_id=repository_id,
        repository_name=repository_name,
        source_snapshot_root=root,
        ref_label=ref_label,
        commit_sha=commit_sha,
        included_prefixes=includes,
        excluded_globs=excludes,
        source_tree_digest=observed_tree_digest,
    )


def _reject_duplicate_identities(repositories: Sequence[RepositorySpec]) -> None:
    identifiers: set[str] = set()
    repository_refs: set[tuple[str, str]] = set()
    roots: set[Path] = set()
    for spec in repositories:
        if spec.repository_id in identifiers:
            raise IndexManifestError(f"duplicate repository_id: {spec.repository_id}")
        identifiers.add(spec.repository_id)
        pair = (spec.repository_name, spec.ref_label)
        if pair in repository_refs:
            raise IndexManifestError(
                "duplicate repository_name/ref combination: "
                f"{spec.repository_name}@{spec.ref_label}"
            )
        repository_refs.add(pair)
        canonical_root = spec.source_snapshot_root.resolve()
        if canonical_root in roots:
            raise IndexManifestError(
                f"duplicate source_snapshot_root: {spec.source_snapshot_root}"
            )
        roots.add(canonical_root)


def _require_regular_file(path: Path, label: str) -> None:
    try:
        metadata = path.lstat()
    except OSError as error:
        raise IndexManifestError(f"{label} does not exist") from error
    if stat.S_ISLNK(metadata.st_mode):
        raise IndexManifestError(f"{label} must not be a symlink")
    if not stat.S_ISREG(metadata.st_mode):
        raise IndexManifestError(f"{label} must be a regular file")


def _validate_snapshot_root(root: Path) -> Path:
    try:
        metadata = root.lstat()
    except OSError as error:
        raise IndexManifestError("source_snapshot_root does not exist") from error
    if stat.S_ISLNK(metadata.st_mode):
        raise IndexManifestError("source_snapshot_root must not be a symlink")
    if not stat.S_ISDIR(metadata.st_mode):
        raise IndexManifestError("source_snapshot_root must be a directory")

    status = _git_stdout(
        root, "status", "--porcelain=v1", "--untracked-files=all", "--ignored=matching"
    )
    if status:
        raise IndexManifestError("source_snapshot_root must be a clean Git snapshot")
    return root


def _git_stdout(root: Path, *arguments: str) -> str:
    try:
        completed = subprocess.run(
            ["git", "-C", os.fspath(root), *arguments],
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise IndexManifestError("source_snapshot_root Git inspection failed") from error
    if completed.returncode != 0:
        raise IndexManifestError("source_snapshot_root must be a Git worktree")
    return completed.stdout.strip()


def _path_rules(value: object, *, field: str, required: bool) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise IndexManifestError(f"{field} must be a list")
    if required and not value:
        raise IndexManifestError(f"{field} must not be empty")
    if len(value) > _MAX_PATH_RULES:
        raise IndexManifestError(f"{field} must contain at most {_MAX_PATH_RULES} rules")

    rules: list[str] = []
    for raw_rule in value:
        if not isinstance(raw_rule, str) or not raw_rule:
            raise IndexManifestError(f"{field} values must be non-empty strings")
        if raw_rule.startswith("/") or "\\" in raw_rule:
            raise IndexManifestError(f"{field} values must be repository-relative")
        segments = raw_rule.split("/")
        if any(segment in {"", ".", ".."} for segment in segments):
            raise IndexManifestError(f"{field} values must not contain traversal")
        if any("**" in segment and segment != "**" for segment in segments):
            raise IndexManifestError(f"{field} has an unsupported recursive glob")
        if PurePosixPath(raw_rule).is_absolute():
            raise IndexManifestError(f"{field} values must be repository-relative")
        rules.append(raw_rule)
    if len(set(rules)) != len(rules):
        raise IndexManifestError(f"{field} must not contain duplicate rules")
    return tuple(rules)


def _digest_selected_files(
    root: Path, includes: Sequence[str], excludes: Sequence[str]
) -> str:
    tracked_paths = _tracked_regular_files(root)
    selected: list[tuple[str, Path]] = []
    overlapping: list[str] = []
    for relative, file_path in tracked_paths:
        included = any(_matches(relative, rule) for rule in includes)
        excluded = any(_matches(relative, rule) for rule in excludes)
        if included and excluded:
            overlapping.append(relative)
        elif included:
            selected.append((relative, file_path))
    if overlapping:
        raise IndexManifestError(
            f"included/excluded overlap selects {', '.join(sorted(overlapping)[:3])}"
        )
    if not selected:
        raise IndexManifestError("included_prefixes select no regular tracked files")

    digest = hashlib.sha256()
    for relative, file_path in sorted(selected):
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(file_path.read_bytes()).digest())
        digest.update(b"\0")
    return digest.hexdigest()


def _tracked_regular_files(root: Path) -> tuple[tuple[str, Path], ...]:
    try:
        completed = subprocess.run(
            ["git", "-C", os.fspath(root), "ls-files", "-z"],
            check=False,
            capture_output=True,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise IndexManifestError("source snapshot file enumeration failed") from error
    if completed.returncode != 0:
        raise IndexManifestError("source_snapshot_root must be a Git worktree")

    files: list[tuple[str, Path]] = []
    for raw_path in completed.stdout.split(b"\0"):
        if not raw_path:
            continue
        try:
            relative = raw_path.decode("utf-8")
        except UnicodeDecodeError as error:
            raise IndexManifestError("source snapshot contains a non-UTF-8 path") from error
        file_path = root / relative
        try:
            metadata = file_path.lstat()
        except OSError as error:
            raise IndexManifestError(f"tracked source path disappeared: {relative}") from error
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
            raise IndexManifestError(
                f"source snapshot must contain only regular tracked files: {relative}"
            )
        files.append((relative, file_path))
    return tuple(files)


def _matches(relative_path: str, rule: str) -> bool:
    """Use the manifest's small, repository-relative glob grammar."""

    return PurePosixPath(relative_path).match(rule)


def _reject_unknown(
    supplied: Mapping[str, object], allowed: frozenset[str], label: str
) -> None:
    unknown = set(supplied) - allowed
    if unknown:
        raise IndexManifestError(f"{label} has unknown fields: {sorted(unknown)}")
    missing = allowed - set(supplied)
    if missing and label.startswith("repository row"):
        raise IndexManifestError(f"{label} is missing fields: {sorted(missing)}")


def _logical_identifier(value: object, field: str) -> str:
    if not isinstance(value, str) or _LOGICAL_ID_RE.fullmatch(value) is None:
        raise IndexManifestError(f"{field} must be a logical identifier")
    return value


def _repository_name(value: object) -> str:
    if not isinstance(value, str) or _REPOSITORY_NAME_RE.fullmatch(value) is None:
        raise IndexManifestError("repository_name must be an owner/repository identity")
    return value


def _digest(value: object, *, field: str, pattern: re.Pattern[str]) -> str:
    if not isinstance(value, str) or pattern.fullmatch(value) is None:
        raise IndexManifestError(f"{field} must be an exact lowercase digest")
    return value
