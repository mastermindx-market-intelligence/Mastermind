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
from urllib.parse import urlparse


class IndexManifestError(ValueError):
    """A reviewed source manifest is not a safe immutable index input."""


_SCHEMA_VERSION: Final = "mastermind.codeintel_index_manifest.v1"
_MAX_REPOSITORIES: Final = 32
_MAX_PATH_RULES: Final = 32
_MAX_WORKTREE_CENSUS_ENTRIES: Final = 250_000
_LOGICAL_ID_RE: Final = re.compile(r"[a-z0-9][a-z0-9._-]{0,127}\Z")
_REPOSITORY_NAME_RE: Final = re.compile(
    r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}/[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z"
)
_SHA1_RE: Final = re.compile(r"[0-9a-f]{40}\Z")
_SHA256_RE: Final = re.compile(r"[0-9a-f]{64}\Z")
_TOP_LEVEL_FIELDS: Final = frozenset({"schema_version", "repositories"})
_GIT_EXECUTABLE: Final = "/usr/bin/git"
_CLOSED_GIT_ENV: Final = {
    "PATH": "/usr/bin:/bin",
    "GIT_OPTIONAL_LOCKS": "0",
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_TERMINAL_PROMPT": "0",
    "GIT_ASKPASS": "/bin/false",
    "LANG": "C",
    "LC_ALL": "C",
    "TZ": "UTC",
}
_GIT_EXECUTION_FENCES: Final = (
    "-c",
    "core.fsmonitor=false",
    "-c",
    "core.useBuiltinFSMonitor=false",
    "-c",
    "core.hooksPath=/dev/null",
)
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
class _TrackedFile:
    """One exact path in both the Git tree and the checked-out worktree."""

    relative_path: str
    mode: str
    blob_sha: str
    content_blob_sha: str
    path: Path
    device: int
    inode: int
    size: int
    mtime_ns: int
    ctime_ns: int


@dataclass(frozen=True)
class _SnapshotSeal:
    """Immutable source and metadata facts frozen at manifest acceptance."""

    root_device: int
    root_inode: int
    common_dir: Path
    common_dir_device: int
    common_dir_inode: int
    ref_label: str
    remote: str
    commit_sha: str
    tree_sha: str
    tracked_files: tuple[_TrackedFile, ...]
    selected_source_tree_digest: str
    digest: str


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
    snapshot_seal: _SnapshotSeal | None = None

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
        payload = json.loads(
            manifest_path.read_text(encoding="utf-8"),
            object_pairs_hook=_reject_duplicate_json_keys,
            parse_constant=_reject_non_finite_json_constant,
        )
    except (OSError, UnicodeDecodeError, ValueError) as error:
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

    includes = _path_rules(included_prefixes, field="included_prefixes", required=True)
    excludes = _path_rules(excluded_globs, field="excluded_globs", required=False)
    seal = _collect_snapshot_seal(Path(source_snapshot_root), includes, excludes)
    return seal.selected_source_tree_digest


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
    includes = _path_rules(
        raw.get("included_prefixes"), field="included_prefixes", required=True
    )
    excludes = _path_rules(
        raw.get("excluded_globs"), field="excluded_globs", required=False
    )
    seal = _collect_snapshot_seal(root, includes, excludes)
    if seal.ref_label != ref_label:
        raise IndexManifestError("ref_label does not match checked-out branch")
    if _normalize_repository_remote(seal.remote) != repository_name:
        raise IndexManifestError("source_snapshot_root origin remote disagrees with repository_name")
    if seal.commit_sha != commit_sha:
        raise IndexManifestError(
            f"commit_sha does not match exact snapshot HEAD for {repository_id}"
        )
    if seal.selected_source_tree_digest != expected_tree_digest:
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
        source_tree_digest=seal.selected_source_tree_digest,
        snapshot_seal=seal,
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
    canonical_root = root.resolve()
    if not _filesystem_is_read_only(canonical_root):
        raise IndexManifestError("source_snapshot_root must be on an OS read-only filesystem")
    return canonical_root


def _normalize_repository_remote(remote: str) -> str | None:
    """Accept only canonical GitHub transports and reduce them to owner/repository."""

    candidate = remote.strip()
    if candidate.startswith("git@github.com:"):
        path = candidate.removeprefix("git@github.com:")
    else:
        parsed = urlparse(candidate)
        if parsed.scheme not in {"https", "ssh"} or parsed.hostname != "github.com":
            return None
        if parsed.scheme == "ssh" and parsed.username != "git":
            return None
        path = parsed.path.lstrip("/")
    if path.endswith(".git"):
        path = path[:-4]
    if _REPOSITORY_NAME_RE.fullmatch(path) is None:
        return None
    return path


def _git_stdout(root: Path, *arguments: str) -> str:
    completed = _run_closed_git(root, *arguments)
    if completed.returncode != 0:
        raise IndexManifestError("source_snapshot_root must be a Git worktree")
    try:
        return completed.stdout.decode("utf-8").strip()
    except UnicodeDecodeError as error:
        raise IndexManifestError("source_snapshot_root Git output is not UTF-8") from error


def _git_stdout_or_none(root: Path, *arguments: str) -> str | None:
    completed = _run_closed_git(root, *arguments)
    if completed.returncode != 0:
        return None
    try:
        return completed.stdout.decode("utf-8").strip() or None
    except UnicodeDecodeError as error:
        raise IndexManifestError("source_snapshot_root Git output is not UTF-8") from error


def _run_closed_git(root: Path, *arguments: str) -> subprocess.CompletedProcess[bytes]:
    """Run only exact, local, read-only Git plumbing behind a frozen environment."""

    try:
        return subprocess.run(
            [_GIT_EXECUTABLE, *_GIT_EXECUTION_FENCES, "-C", os.fspath(root), *arguments],
            check=False,
            capture_output=True,
            timeout=15,
            env=dict(_CLOSED_GIT_ENV),
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise IndexManifestError("source_snapshot_root Git inspection failed") from error


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
    tracked_files: Sequence[_TrackedFile], includes: Sequence[str], excludes: Sequence[str]
) -> str:
    selected: list[_TrackedFile] = []
    overlapping: list[str] = []
    for tracked in tracked_files:
        included = any(_matches(tracked.relative_path, rule) for rule in includes)
        excluded = any(_matches(tracked.relative_path, rule) for rule in excludes)
        if included and excluded:
            overlapping.append(tracked.relative_path)
        elif included:
            selected.append(tracked)
    if overlapping:
        raise IndexManifestError(
            f"included/excluded overlap selects {', '.join(sorted(overlapping)[:3])}"
        )
    if not selected:
        raise IndexManifestError("included_prefixes select no regular tracked files")

    digest = hashlib.sha256()
    for tracked in sorted(selected, key=lambda item: item.relative_path):
        digest.update(tracked.relative_path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(tracked.path.read_bytes()).digest())
        digest.update(b"\0")
    return digest.hexdigest()


def _tracked_regular_files(root: Path) -> tuple[_TrackedFile, ...]:
    completed = _run_closed_git(root, "ls-files", "-s", "-z")
    if completed.returncode != 0:
        raise IndexManifestError("source_snapshot_root must be a Git worktree")

    tree_completed = _run_closed_git(root, "ls-tree", "-r", "-z", "HEAD")
    if tree_completed.returncode != 0:
        raise IndexManifestError("source_snapshot_root Git tree is unavailable")
    index_entries = _parse_index_entries(completed.stdout)
    tree_entries = _parse_tree_entries(tree_completed.stdout)
    if index_entries != tree_entries:
        raise IndexManifestError("source_snapshot_root index disagrees with exact Git tree")

    files: list[_TrackedFile] = []
    for relative, mode, blob_sha in index_entries:
        file_path = root / relative
        try:
            metadata = file_path.lstat()
        except OSError as error:
            raise IndexManifestError(f"tracked source path disappeared: {relative}") from error
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
            raise IndexManifestError(
                f"source snapshot must contain only regular tracked files: {relative}"
            )
        if _is_lfs_pointer(file_path):
            raise IndexManifestError(f"source snapshot contains unresolved LFS pointer: {relative}")
        content_blob_sha = _git_blob_sha1(file_path)
        if content_blob_sha != blob_sha:
            raise IndexManifestError(f"source snapshot worktree bytes disagree: {relative}")
        files.append(
            _TrackedFile(
                relative_path=relative,
                mode=mode,
                blob_sha=blob_sha,
                content_blob_sha=content_blob_sha,
                path=file_path,
                device=metadata.st_dev,
                inode=metadata.st_ino,
                size=metadata.st_size,
                mtime_ns=metadata.st_mtime_ns,
                ctime_ns=metadata.st_ctime_ns,
            )
        )
    _reject_untracked_or_special_paths(root, files)
    return tuple(files)


def _parse_index_entries(payload: bytes) -> tuple[tuple[str, str, str], ...]:
    entries: list[tuple[str, str, str]] = []
    for raw_entry in payload.split(b"\0"):
        if not raw_entry:
            continue
        try:
            index_entry, raw_path = raw_entry.split(b"\t", 1)
            mode, blob_sha, stage = index_entry.decode("ascii").split(" ")
            relative = _repository_relative_path(raw_path)
        except UnicodeDecodeError as error:
            raise IndexManifestError("source snapshot contains a non-UTF-8 path") from error
        except ValueError as error:
            raise IndexManifestError("source snapshot Git index census is malformed") from error
        if stage != "0" or _SHA1_RE.fullmatch(blob_sha) is None:
            raise IndexManifestError("source snapshot Git index census is ambiguous")
        if mode == "120000":
            raise IndexManifestError(f"source snapshot contains tracked symlink: {relative}")
        if mode == "160000":
            raise IndexManifestError(f"source snapshot contains submodule: {relative}")
        if mode not in {"100644", "100755"}:
            raise IndexManifestError(f"source snapshot contains special tracked path: {relative}")
        entries.append((relative, mode, blob_sha))
    if len({relative for relative, _mode, _blob in entries}) != len(entries):
        raise IndexManifestError("source snapshot Git index census is ambiguous")
    return tuple(sorted(entries))


def _parse_tree_entries(payload: bytes) -> tuple[tuple[str, str, str], ...]:
    entries: list[tuple[str, str, str]] = []
    for raw_entry in payload.split(b"\0"):
        if not raw_entry:
            continue
        try:
            tree_entry, raw_path = raw_entry.split(b"\t", 1)
            mode, kind, blob_sha = tree_entry.decode("ascii").split(" ")
            relative = _repository_relative_path(raw_path)
        except UnicodeDecodeError as error:
            raise IndexManifestError("source snapshot contains a non-UTF-8 path") from error
        except ValueError as error:
            raise IndexManifestError("source snapshot Git tree census is malformed") from error
        if mode == "120000":
            raise IndexManifestError(f"source snapshot contains tracked symlink: {relative}")
        if mode == "160000":
            raise IndexManifestError(f"source snapshot contains submodule: {relative}")
        if kind != "blob" or _SHA1_RE.fullmatch(blob_sha) is None:
            raise IndexManifestError("source snapshot Git tree census is ambiguous")
        if mode not in {"100644", "100755"}:
            raise IndexManifestError(f"source snapshot contains special tracked path: {relative}")
        entries.append((relative, mode, blob_sha))
    if len({relative for relative, _mode, _blob in entries}) != len(entries):
        raise IndexManifestError("source snapshot Git tree census is ambiguous")
    return tuple(sorted(entries))


def _collect_snapshot_seal(
    source_snapshot_root: Path,
    includes: Sequence[str],
    excludes: Sequence[str],
) -> _SnapshotSeal:
    """Read and bind every source fact that must stay unchanged through indexing."""

    root = _validate_snapshot_root(source_snapshot_root)
    try:
        root_metadata = root.stat()
        worktree = Path(_git_stdout(root, "rev-parse", "--show-toplevel")).resolve()
        common_text = _git_stdout(root, "rev-parse", "--git-common-dir")
        common_dir = Path(common_text)
        if not common_dir.is_absolute():
            common_dir = root / common_dir
        common_dir = common_dir.resolve()
        common_metadata = common_dir.stat()
    except OSError as error:
        raise IndexManifestError("source_snapshot_root Git common-dir is unavailable") from error
    if worktree != root:
        raise IndexManifestError("source_snapshot_root worktree identity disagrees")
    if not stat.S_ISDIR(common_metadata.st_mode):
        raise IndexManifestError("source_snapshot_root Git common-dir is not a directory")
    if not _filesystem_is_read_only(common_dir):
        raise IndexManifestError("source_snapshot_root Git common-dir must be on an OS read-only filesystem")

    ref_label = _git_stdout_or_none(root, "symbolic-ref", "--quiet", "--short", "HEAD")
    if ref_label is None:
        raise IndexManifestError("source_snapshot_root must have a checked-out branch")
    remote = _git_stdout_or_none(
        root, "config", "--no-includes", "--local", "--get", "remote.origin.url"
    )
    if remote is None:
        raise IndexManifestError("source_snapshot_root origin remote is unavailable")
    commit_sha = _git_stdout(root, "rev-parse", "--verify", "HEAD")
    tree_sha = _git_stdout(root, "rev-parse", "--verify", "HEAD^{tree}")
    if _SHA1_RE.fullmatch(commit_sha) is None or _SHA1_RE.fullmatch(tree_sha) is None:
        raise IndexManifestError("source_snapshot_root Git identity is malformed")
    tracked_files = _tracked_regular_files(root)
    selected_source_tree_digest = _digest_selected_files(tracked_files, includes, excludes)
    digest = _snapshot_seal_digest(
        root_metadata=root_metadata,
        common_metadata=common_metadata,
        ref_label=ref_label,
        remote=remote,
        commit_sha=commit_sha,
        tree_sha=tree_sha,
        tracked_files=tracked_files,
        selected_source_tree_digest=selected_source_tree_digest,
    )
    return _SnapshotSeal(
        root_device=root_metadata.st_dev,
        root_inode=root_metadata.st_ino,
        common_dir=common_dir,
        common_dir_device=common_metadata.st_dev,
        common_dir_inode=common_metadata.st_ino,
        ref_label=ref_label,
        remote=remote,
        commit_sha=commit_sha,
        tree_sha=tree_sha,
        tracked_files=tracked_files,
        selected_source_tree_digest=selected_source_tree_digest,
        digest=digest,
    )


def verify_repository_spec(spec: RepositorySpec) -> None:
    """Reverify the manifest's frozen snapshot seal immediately before/after use."""

    expected = spec.snapshot_seal
    if expected is None:
        raise IndexManifestError("source snapshot seal is unavailable")
    observed = _collect_snapshot_seal(
        spec.source_snapshot_root, spec.included_prefixes, spec.excluded_globs
    )
    if (
        observed.ref_label != spec.ref_label
        or observed.remote != expected.remote
        or _normalize_repository_remote(observed.remote) != spec.repository_name
        or observed.commit_sha != spec.commit_sha
        or observed.selected_source_tree_digest != spec.source_tree_digest
        or observed != expected
    ):
        raise IndexManifestError("source snapshot seal changed")


def _filesystem_is_read_only(path: Path) -> bool:
    """Trust filesystem mount state, never mutable permission bits or caller claims."""

    try:
        flags = os.statvfs(os.fspath(path)).f_flag
    except OSError as error:
        raise IndexManifestError("source snapshot read-only evidence is unavailable") from error
    return bool(flags & getattr(os, "ST_RDONLY", 1))


def _repository_relative_path(raw_path: bytes) -> str:
    relative = raw_path.decode("utf-8")
    if not relative or relative.startswith("/") or "\\" in relative:
        raise IndexManifestError("source snapshot contains an unsafe Git path")
    segments = relative.split("/")
    if any(segment in {"", ".", ".."} for segment in segments):
        raise IndexManifestError("source snapshot contains an unsafe Git path")
    return relative


def _git_blob_sha1(path: Path) -> str:
    try:
        content = path.read_bytes()
    except OSError as error:
        raise IndexManifestError(f"tracked source path disappeared: {path.name}") from error
    digest = hashlib.sha1()
    digest.update(f"blob {len(content)}\0".encode("ascii"))
    digest.update(content)
    return digest.hexdigest()


def _reject_untracked_or_special_paths(root: Path, tracked_files: Sequence[_TrackedFile]) -> None:
    """Census the entire worktree without invoking status, filters, or fsmonitor."""

    tracked_paths = {tracked.relative_path for tracked in tracked_files}
    tracked_directories: set[str] = set()
    seen_entries = 0
    for relative in tracked_paths:
        parent = PurePosixPath(relative).parent
        while parent != PurePosixPath("."):
            tracked_directories.add(parent.as_posix())
            parent = parent.parent

    def visit(directory: Path, prefix: str) -> None:
        nonlocal seen_entries
        try:
            entries = sorted(os.scandir(directory), key=lambda entry: entry.name)
        except OSError as error:
            raise IndexManifestError("source snapshot filesystem census failed") from error
        for entry in entries:
            if not prefix and entry.name == ".git":
                continue
            seen_entries += 1
            if seen_entries > _MAX_WORKTREE_CENSUS_ENTRIES:
                raise IndexManifestError("source snapshot filesystem census exceeds its bound")
            relative = f"{prefix}/{entry.name}" if prefix else entry.name
            try:
                metadata = entry.stat(follow_symlinks=False)
            except OSError as error:
                raise IndexManifestError("source snapshot filesystem census failed") from error
            if stat.S_ISLNK(metadata.st_mode):
                raise IndexManifestError(f"source snapshot contains symlink: {relative}")
            if stat.S_ISDIR(metadata.st_mode):
                if relative not in tracked_directories:
                    raise IndexManifestError(
                        f"source_snapshot_root must be a clean Git snapshot: untracked path {relative}"
                    )
                visit(Path(entry.path), relative)
                continue
            if not stat.S_ISREG(metadata.st_mode):
                raise IndexManifestError(f"source snapshot contains special path: {relative}")
            if relative not in tracked_paths:
                raise IndexManifestError(
                    f"source_snapshot_root must be a clean Git snapshot: untracked path {relative}"
                )

    visit(root, "")


def _snapshot_seal_digest(
    *,
    root_metadata: os.stat_result,
    common_metadata: os.stat_result,
    ref_label: str,
    remote: str,
    commit_sha: str,
    tree_sha: str,
    tracked_files: Sequence[_TrackedFile],
    selected_source_tree_digest: str,
) -> str:
    digest = hashlib.sha256()
    for value in (
        "mastermind.codeintel_snapshot_seal.v1",
        str(root_metadata.st_dev),
        str(root_metadata.st_ino),
        str(common_metadata.st_dev),
        str(common_metadata.st_ino),
        ref_label,
        remote,
        commit_sha,
        tree_sha,
        selected_source_tree_digest,
    ):
        digest.update(value.encode("utf-8"))
        digest.update(b"\0")
    for tracked in tracked_files:
        for value in (
            tracked.relative_path,
            tracked.mode,
            tracked.blob_sha,
            tracked.content_blob_sha,
            str(tracked.device),
            str(tracked.inode),
            str(tracked.size),
            str(tracked.mtime_ns),
            str(tracked.ctime_ns),
        ):
            digest.update(value.encode("utf-8"))
            digest.update(b"\0")
    return digest.hexdigest()


def _reject_duplicate_json_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    payload: dict[str, object] = {}
    for key, value in pairs:
        if key in payload:
            raise ValueError("manifest JSON contains duplicate keys")
        payload[key] = value
    return payload


def _reject_non_finite_json_constant(value: str) -> object:
    raise ValueError(f"manifest JSON constant is forbidden: {value}")


def _is_lfs_pointer(path: Path) -> bool:
    try:
        prefix = path.read_bytes()[:256]
    except OSError as error:
        raise IndexManifestError(f"tracked source path disappeared: {path.name}") from error
    return prefix.startswith(b"version https://git-lfs.github.com/spec/v1\n") and b"oid sha256:" in prefix


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
