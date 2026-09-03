"""Deterministic hosted forge and network-sealed Z0 execution boundary.

Only the reviewed manual workflow calls the mutating commands in this module.
All dispatch values are reduced to one closed request identity; callers cannot
select a repository, URL, module, executable, command, path, or argv suffix.
"""

from __future__ import annotations

import argparse
import dataclasses
import enum
import errno
import gzip
import hashlib
import io
import json
import os
import platform
import re
import resource
import selectors
import shutil
import signal
import socket
import stat
import subprocess
import sys
import tarfile
import tempfile
import time
import zipfile
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Final
from urllib.parse import urljoin, urlparse

try:  # Support both ``python -m`` and the workflow's absolute script entry.
    from . import toolchain_lock as locks
except ImportError:  # pragma: no cover - exercised by the hosted workflow
    import toolchain_lock as locks  # type: ignore[no-redef]


RECEIPT_SCHEMA_VERSION: Final = "mastermind.codeintel_experiment_bundle.v1"
BUNDLE_MANIFEST_SCHEMA_VERSION: Final = "mastermind.codeintel_bundle_manifest.v1"
PHASE_P_PROVENANCE_SCHEMA_VERSION: Final = "mastermind.codeintel_phase_p_provenance.v1"
Z0_OPERATION_KEY: Final = locks.Z0_OPERATION_KEY
FIXED_REPOSITORY: Final = "mastermindx-market-intelligence/Mastermind"
FIXED_CONSUMER_MODULE: Final = "experiments.code_discovery.z0_runner"
FIXED_CONSUMER_BRANCH: Final = "codeintel-z0-consumer"
FIXED_WORKFLOW_PATH: Final = ".github/workflows/codeintel-experiment-bundle.yml"

_SHA1_RE: Final = re.compile(r"[0-9a-f]{40}\Z")
_SHA256_RE: Final = re.compile(r"[0-9a-f]{64}\Z")
_OPERATION_RE: Final = re.compile(r"[a-z0-9][a-z0-9-]{0,127}\Z")
_SAFE_BUNDLE_PART_RE: Final = re.compile(r"[A-Za-z0-9._+-]{1,128}\Z")
_SECRET_TEXT_PATTERNS: Final = (
    re.compile(r"(?i)authorization\s*:\s*(?:bearer|basic)\s+\S+"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"-----BEGIN (?:[A-Z ]+ )?PRIVATE KEY-----"),
    re.compile(r"\$\{\{\s*secrets\.", re.IGNORECASE),
    re.compile(r"\b(?:GITHUB|ACTIONS)_\w*TOKEN\b"),
)
_PRIVATE_PATH_PATTERNS: Final = (
    re.compile(r"(?:^|[\s'\"])/Users/[^\s'\"]+"),
    re.compile(r"(?:^|[\s'\"])/home/runner/(?:work|_work)/[^\s'\"]+"),
    re.compile(r"(?:^|[\s'\"])/private/(?:tmp|var)/[^\s'\"]+"),
)
_FORBIDDEN_KEY_RE: Final = re.compile(
    r"(?:^|_)(?:authorization|cookie|credential|password|private_key|token|secret)(?:_|$)",
    re.IGNORECASE,
)
_ALLOWED_CONSUMER_PREFIXES: Final = (
    "experiments/code_discovery/",
    "tests/code_discovery/",
    "tests/fixtures/code_discovery/",
)
_ALLOWED_CONSUMER_EXACT: Final = frozenset(
    {
        "research/code_intelligence_fabric/Z0_GLOBAL_DISCOVERY_FALSIFIER_RESULT.md",
        "research/code_intelligence_fabric/z0-path-policy.json",
        "research/code_intelligence_fabric/z0-result.schema.json",
    }
)
_REQUIRED_BUNDLE_FILES: Final = frozenset(
    {
        "bin/zoekt-git-index",
        "bin/zoekt-webserver",
        "meta/NOTICE.txt",
        "meta/provenance.json",
        "meta/sbom.json",
        "meta/toolchain-lock.json",
    }
)
_RECEIPT_STATE_PAIRS: Final = frozenset(
    {
        ("COMPLETED", "APPLIED"),
        ("REFUSED", "NOT_APPLIED"),
        ("RECONCILIATION_REQUIRED", "EFFECT_UNKNOWN"),
    }
)
_CONSUMER_BOOTSTRAP: Final = (
    "import runpy,sys;"
    "sys.path.insert(0,sys.argv.pop(1));"
    "runpy.run_module('experiments.code_discovery.z0_runner',run_name='__main__')"
)


class HostedRunnerError(RuntimeError):
    """A typed fail-closed runner refusal."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class ExperimentRequest:
    """The complete normalized identity of one fixed Z0 experiment request."""

    operation_key: str
    consumer_sha: str
    consumer_tree_sha: str
    forge_sha: str
    forge_tree_sha: str
    lock_sha256: str
    workflow_sha256: str
    mode: str = "Z0"
    repository: str = FIXED_REPOSITORY

    @classmethod
    def from_values(
        cls,
        *,
        operation_key: str,
        consumer_sha: str,
        consumer_tree_sha: str,
        forge_sha: str,
        forge_tree_sha: str,
        lock_sha256: str,
        workflow_sha256: str,
    ) -> ExperimentRequest:
        if (
            operation_key != Z0_OPERATION_KEY
            or _OPERATION_RE.fullmatch(operation_key) is None
        ):
            raise HostedRunnerError(
                "INVALID_REQUEST", "operation_key is not the fixed Z0 key"
            )
        for label, value, pattern in (
            ("consumer_sha", consumer_sha, _SHA1_RE),
            ("consumer_tree_sha", consumer_tree_sha, _SHA1_RE),
            ("forge_sha", forge_sha, _SHA1_RE),
            ("forge_tree_sha", forge_tree_sha, _SHA1_RE),
            ("lock_sha256", lock_sha256, _SHA256_RE),
            ("workflow_sha256", workflow_sha256, _SHA256_RE),
        ):
            if not isinstance(value, str) or pattern.fullmatch(value) is None:
                raise HostedRunnerError(
                    "INVALID_REQUEST", f"{label} must be an exact digest"
                )
        return cls(
            operation_key=operation_key,
            consumer_sha=consumer_sha,
            consumer_tree_sha=consumer_tree_sha,
            forge_sha=forge_sha,
            forge_tree_sha=forge_tree_sha,
            lock_sha256=lock_sha256,
            workflow_sha256=workflow_sha256,
        )

    @property
    def payload(self) -> dict[str, str]:
        return {
            "consumer_sha": self.consumer_sha,
            "consumer_tree_sha": self.consumer_tree_sha,
            "forge_sha": self.forge_sha,
            "forge_tree_sha": self.forge_tree_sha,
            "lock_sha256": self.lock_sha256,
            "mode": self.mode,
            "operation_key": self.operation_key,
            "repository": self.repository,
            "workflow_sha256": self.workflow_sha256,
        }

    @property
    def canonical_bytes(self) -> bytes:
        return locks.canonical_json_bytes(self.payload)

    @property
    def digest(self) -> str:
        return locks.sha256_bytes(self.canonical_bytes)


@dataclass(frozen=True)
class ConsumerIdentity:
    commit_sha: str
    tree_sha: str
    repository: str
    branch: str


@dataclass(frozen=True)
class BundleIdentity:
    path: Path
    name: str
    sha256: str
    size: int
    manifest_sha256: str


@dataclass(frozen=True)
class VerifiedBundle:
    path: Path
    sha256: str
    size: int
    manifest: Mapping[str, Any]
    manifest_sha256: str


class ReplayDisposition(enum.Enum):
    PROCEED = "PROCEED"
    RETURN_PRIOR = "RETURN_PRIOR"


@dataclass(frozen=True)
class ReplayResolution:
    disposition: ReplayDisposition
    receipt: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class NetworkSealProof:
    interfaces: tuple[str, ...]
    non_loopback_routes: tuple[str, ...]
    outbound_probe: str
    denial_errno: int | None


@dataclass(frozen=True)
class LaunchEvidence:
    returncode: int
    pid: int
    process_group: int
    stdout_sha256: str
    stderr_sha256: str
    stdout_bytes: int
    stderr_bytes: int
    user_seconds: float
    system_seconds: float
    max_rss_kib: int


@dataclass(frozen=True)
class CleanupEvidence:
    process_group_dead: bool
    unexpected_residue: tuple[str, ...]


def run_checked(
    argv: Sequence[str],
    *,
    cwd: Path,
    env: Mapping[str, str] | None = None,
    timeout: float = 60,
) -> subprocess.CompletedProcess[str]:
    """Run a fixed argv without shell interpretation and return bounded text."""

    if not argv or any(not isinstance(value, str) or "\x00" in value for value in argv):
        raise HostedRunnerError("INVALID_ARGV", "subprocess argv is malformed")
    try:
        completed = subprocess.run(
            list(argv),
            cwd=os.fspath(cwd),
            env=dict(env) if env is not None else None,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise HostedRunnerError("SUBPROCESS_FAILED", Path(argv[0]).name) from error
    if completed.returncode != 0:
        detail = _bounded_redacted(completed.stderr or completed.stdout, 2048)
        raise HostedRunnerError(
            "SUBPROCESS_FAILED",
            f"{Path(argv[0]).name} exited {completed.returncode}: {detail}",
        )
    return completed


def git_stdout(root: Path, *arguments: str) -> str:
    return run_checked(
        ["/usr/bin/git", "-C", os.fspath(root), *arguments],
        cwd=Path(root),
        timeout=30,
    ).stdout.strip()


def verify_consumer_checkout(
    consumer_root: Path, expected_sha: str, expected_tree_sha: str
) -> ConsumerIdentity:
    """Re-derive exact consumer identity from a clean same-repository checkout."""

    if (
        _SHA1_RE.fullmatch(expected_sha) is None
        or _SHA1_RE.fullmatch(expected_tree_sha) is None
    ):
        raise HostedRunnerError("CONSUMER_MISMATCH", "expected identity is not exact")
    root = _real_directory(consumer_root, "CONSUMER_MISMATCH")
    remote = git_stdout(root, "remote", "get-url", "origin")
    repository = _normalize_github_remote(remote)
    if repository != FIXED_REPOSITORY:
        raise HostedRunnerError(
            "CONSUMER_REPOSITORY_MISMATCH",
            "consumer origin is not the fixed repository",
        )
    if git_stdout(root, "status", "--porcelain=v1", "--untracked-files=all"):
        raise HostedRunnerError(
            "CONSUMER_DIRTY", "consumer checkout has uncommitted bytes"
        )
    head = git_stdout(root, "rev-parse", "--verify", "HEAD")
    tree = git_stdout(root, "rev-parse", "--verify", "HEAD^{tree}")
    if head != expected_sha or tree != expected_tree_sha:
        raise HostedRunnerError("CONSUMER_MISMATCH", "consumer HEAD/tree differs")
    try:
        branch = git_stdout(root, "symbolic-ref", "--quiet", "--short", "HEAD")
    except HostedRunnerError:
        branch = "DETACHED"
    if branch != FIXED_CONSUMER_BRANCH:
        raise HostedRunnerError(
            "CONSUMER_BRANCH_MISMATCH", "consumer is not bound to the fixed local role"
        )
    for raw in _git_bytes(root, "ls-files", "-s", "-z").split(b"\0"):
        if not raw:
            continue
        try:
            header, raw_path = raw.split(b"\t", 1)
            mode, object_id, stage = header.decode("ascii").split(" ")
            path = raw_path.decode("utf-8")
        except (UnicodeDecodeError, ValueError) as error:
            raise HostedRunnerError(
                "CONSUMER_CENSUS_INVALID", "malformed Git index"
            ) from error
        if (
            mode not in {"100644", "100755", "120000", "160000"}
            or stage != "0"
            or _SHA1_RE.fullmatch(object_id) is None
        ):
            raise HostedRunnerError(
                "CONSUMER_CENSUS_INVALID", f"consumer index row is invalid for {path}"
            )
    return ConsumerIdentity(head, tree, repository, branch)


def validate_consumer_paths(paths: Iterable[str]) -> tuple[str, ...]:
    """Validate the effective diff against the frozen Z0 source ceiling."""

    normalized: list[str] = []
    for value in paths:
        if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
            raise HostedRunnerError("CONSUMER_PATH_VIOLATION", "invalid changed path")
        candidate = PurePosixPath(value)
        if candidate.is_absolute() or any(
            part in {"", ".", ".."} for part in candidate.parts
        ):
            raise HostedRunnerError("CONSUMER_PATH_VIOLATION", value)
        canonical = candidate.as_posix()
        if not (
            canonical in _ALLOWED_CONSUMER_EXACT
            or any(
                canonical.startswith(prefix) for prefix in _ALLOWED_CONSUMER_PREFIXES
            )
        ):
            raise HostedRunnerError("CONSUMER_PATH_VIOLATION", canonical)
        normalized.append(canonical)
    if not normalized:
        raise HostedRunnerError("CONSUMER_PATH_VIOLATION", "consumer diff is empty")
    if len(set(normalized)) != len(normalized):
        raise HostedRunnerError(
            "CONSUMER_PATH_VIOLATION", "consumer diff has duplicates"
        )
    if "experiments/code_discovery/z0_runner.py" not in normalized:
        raise HostedRunnerError("CONSUMER_PATH_VIOLATION", "fixed Z0 runner is absent")
    return tuple(sorted(normalized))


def consumer_effective_paths(
    repository_root: Path, *, consumer_sha: str, forge_sha: str
) -> tuple[str, tuple[str, ...]]:
    """Derive the merge-base path census for the exact same-repository consumer."""

    root = _real_directory(repository_root, "CONSUMER_MISMATCH")
    for value in (consumer_sha, forge_sha):
        if _SHA1_RE.fullmatch(value) is None:
            raise HostedRunnerError("CONSUMER_MISMATCH", "commit identity is not exact")
        git_stdout(root, "cat-file", "-e", f"{value}^{{commit}}")
    base = git_stdout(root, "merge-base", consumer_sha, forge_sha)
    if _SHA1_RE.fullmatch(base) is None:
        raise HostedRunnerError("CONSUMER_MISMATCH", "merge-base is ambiguous")
    raw = _git_bytes(
        root,
        "diff",
        "--name-only",
        "--diff-filter=ACDMRTUXB",
        "-z",
        base,
        consumer_sha,
    )
    try:
        paths = [item.decode("utf-8") for item in raw.split(b"\0") if item]
    except UnicodeDecodeError as error:
        raise HostedRunnerError(
            "CONSUMER_PATH_VIOLATION", "non-UTF-8 changed path"
        ) from error
    validated = validate_consumer_paths(paths)
    tree_rows = _git_bytes(root, "ls-tree", "-z", consumer_sha, "--", *validated)
    observed: set[str] = set()
    for raw in tree_rows.split(b"\0"):
        if not raw:
            continue
        try:
            header, raw_path = raw.split(b"\t", 1)
            mode, kind, object_id = header.decode("ascii").split(" ")
            path = raw_path.decode("utf-8")
        except (UnicodeDecodeError, ValueError) as error:
            raise HostedRunnerError(
                "CONSUMER_CENSUS_INVALID", "malformed consumer tree row"
            ) from error
        if (
            mode not in {"100644", "100755"}
            or kind != "blob"
            or _SHA1_RE.fullmatch(object_id) is None
            or path not in validated
            or path in observed
        ):
            raise HostedRunnerError(
                "CONSUMER_FILE_UNSAFE", f"changed consumer path is not regular: {path}"
            )
        observed.add(path)
    if observed != set(validated):
        raise HostedRunnerError(
            "CONSUMER_FILE_UNSAFE",
            "changed consumer paths are absent from the exact tree",
        )
    return base, validated


def selected_source_digest(
    root: Path, *, includes: Sequence[str], excludes: Sequence[str]
) -> str:
    """Mirror the protected Z0 consumer's selected regular-file digest."""

    source_root = _real_directory(root, "CONSUMER_MISMATCH")
    rows: list[tuple[str, Path]] = []
    basenames: set[str] = set()
    raw = _git_bytes(source_root, "ls-files", "-s", "-z")
    for entry in raw.split(b"\0"):
        if not entry:
            continue
        header, raw_path = entry.split(b"\t", 1)
        mode, object_id, stage = header.decode("ascii").split(" ")
        relative = raw_path.decode("utf-8")
        path = PurePosixPath(relative)
        selected = any(path.match(rule) for rule in includes)
        omitted = any(path.match(rule) for rule in excludes)
        if selected and omitted:
            raise HostedRunnerError(
                "CONSUMER_PATH_VIOLATION", f"overlapping rule for {relative}"
            )
        if selected:
            if (
                mode not in {"100644", "100755"}
                or stage != "0"
                or _SHA1_RE.fullmatch(object_id) is None
            ):
                raise HostedRunnerError("CONSUMER_FILE_UNSAFE", relative)
            if path.name in basenames:
                raise HostedRunnerError(
                    "CONSUMER_FILE_UNSAFE", f"duplicate basename {path.name}"
                )
            basenames.add(path.name)
            file_path = source_root / relative
            metadata = file_path.lstat()
            if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
                raise HostedRunnerError("CONSUMER_FILE_UNSAFE", relative)
            rows.append((relative, file_path))
    if not rows:
        raise HostedRunnerError(
            "CONSUMER_PATH_VIOLATION", "index rules select no files"
        )
    digest = hashlib.sha256()
    for relative, file_path in sorted(rows):
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(file_path.read_bytes()).digest())
        digest.update(b"\0")
    return digest.hexdigest()


def create_content_addressed_bundle(
    payload_root: Path, output_directory: Path, *, context: Mapping[str, object]
) -> BundleIdentity:
    """Create canonical gzip/tar bytes and name them by their complete SHA-256."""

    root = _real_directory(payload_root, "BUNDLE_PAYLOAD_UNSAFE")
    files = _bundle_payload_census(root)
    missing = _REQUIRED_BUNDLE_FILES - {path for path, _file, _mode in files}
    if missing:
        raise HostedRunnerError(
            "BUNDLE_PAYLOAD_INCOMPLETE", f"missing {sorted(missing)}"
        )
    assert_secret_free(context)
    manifest_files = [
        {
            "path": relative,
            "role": _bundle_role(relative),
            "mode": f"{mode:04o}",
            "size": file_path.stat().st_size,
            "sha256": locks.sha256_file(file_path, max_bytes=locks.GO_ARCHIVE_SIZE * 2),
        }
        for relative, file_path, mode in files
    ]
    manifest = {
        "schema_version": BUNDLE_MANIFEST_SCHEMA_VERSION,
        "mode": "Z0",
        "context": dict(context),
        "files": manifest_files,
    }
    assert_secret_free(manifest)
    manifest_bytes = locks.canonical_json_bytes(manifest) + b"\n"
    manifest_sha256 = locks.sha256_bytes(manifest_bytes)

    output = _ensure_output_directory(output_directory)
    descriptor, temporary_name = tempfile.mkstemp(prefix=".codeintel-z0-", dir=output)
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        with temporary.open("wb") as raw_output:
            with gzip.GzipFile(
                filename="", fileobj=raw_output, mode="wb", compresslevel=9, mtime=0
            ) as compressed:
                with tarfile.open(
                    fileobj=compressed, mode="w", format=tarfile.GNU_FORMAT
                ) as archive:
                    directory_names = {
                        str(parent)
                        for relative, _file, _mode in files
                        for parent in PurePosixPath(relative).parents
                        if str(parent) != "."
                    }
                    for directory in sorted(directory_names):
                        _add_tar_directory(archive, directory)
                    for relative, file_path, mode in files:
                        _add_tar_file(archive, relative, file_path, mode)
                    _add_tar_bytes(archive, "manifest.json", manifest_bytes, 0o644)
        size = temporary.stat().st_size
        if size > 268_435_456:
            raise HostedRunnerError("BUNDLE_TOO_LARGE", str(size))
        digest = locks.sha256_file(temporary, max_bytes=268_435_456)
        name = f"codeintel-z0-{digest}.tar.gz"
        target = output / name
        if target.exists() or target.is_symlink():
            if (
                target.is_symlink()
                or not target.is_file()
                or locks.sha256_file(target, max_bytes=268_435_456) != digest
            ):
                raise HostedRunnerError("BUNDLE_OUTPUT_CONFLICT", name)
            temporary.unlink()
        else:
            os.replace(temporary, target)
        verified = verify_bundle(target, expected_sha256=digest)
        if verified.manifest_sha256 != manifest_sha256:
            raise HostedRunnerError("BUNDLE_MANIFEST_MISMATCH", name)
        return BundleIdentity(target, name, digest, size, manifest_sha256)
    finally:
        temporary.unlink(missing_ok=True)


def verify_bundle(bundle_path: Path, *, expected_sha256: str) -> VerifiedBundle:
    """Reverify complete archive bytes, member safety, manifest, roles and payload hashes."""

    if _SHA256_RE.fullmatch(expected_sha256) is None:
        raise HostedRunnerError(
            "BUNDLE_DIGEST_MISMATCH", "expected digest is not exact"
        )
    path = Path(bundle_path)
    try:
        metadata = path.lstat()
    except OSError as error:
        raise HostedRunnerError("BUNDLE_UNAVAILABLE", path.name) from error
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise HostedRunnerError("BUNDLE_UNSAFE", path.name)
    if metadata.st_size > 268_435_456:
        raise HostedRunnerError("BUNDLE_TOO_LARGE", path.name)
    observed_sha256 = locks.sha256_file(path, max_bytes=268_435_456)
    if observed_sha256 != expected_sha256:
        raise HostedRunnerError("BUNDLE_DIGEST_MISMATCH", path.name)
    try:
        with path.open("rb") as source:
            if source.read(2) != b"\x1f\x8b":
                raise HostedRunnerError("BUNDLE_UNSAFE", "bundle is not gzip")
        with tarfile.open(path, mode="r:gz") as archive:
            members = archive.getmembers()
            _validate_bundle_members(members)
            manifest_member = next(
                member for member in members if member.name == "manifest.json"
            )
            if manifest_member.size > 1_048_576:
                raise HostedRunnerError(
                    "BUNDLE_MANIFEST_INVALID", "manifest is oversized"
                )
            extracted = archive.extractfile(manifest_member)
            if extracted is None:
                raise HostedRunnerError(
                    "BUNDLE_MANIFEST_INVALID", "manifest unavailable"
                )
            manifest_bytes = extracted.read(1_048_577)
            if len(manifest_bytes) > 1_048_576:
                raise HostedRunnerError(
                    "BUNDLE_MANIFEST_INVALID", "manifest is oversized"
                )
            try:
                manifest = json.loads(manifest_bytes)
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise HostedRunnerError(
                    "BUNDLE_MANIFEST_INVALID", "manifest is not JSON"
                ) from error
            _validate_bundle_manifest(manifest)
            expected_rows = {row["path"]: row for row in manifest["files"]}
            actual_files = {
                member.name: member
                for member in members
                if member.isfile() and member.name != "manifest.json"
            }
            if set(expected_rows) != set(actual_files):
                raise HostedRunnerError(
                    "BUNDLE_MANIFEST_MISMATCH", "member census differs"
                )
            for relative, row in expected_rows.items():
                member = actual_files[relative]
                if (
                    member.size != row["size"]
                    or f"{member.mode & 0o777:04o}" != row["mode"]
                ):
                    raise HostedRunnerError("BUNDLE_MANIFEST_MISMATCH", relative)
                body_stream = archive.extractfile(member)
                if body_stream is None:
                    raise HostedRunnerError("BUNDLE_MANIFEST_MISMATCH", relative)
                digest = hashlib.sha256()
                remaining = member.size
                while remaining:
                    block = body_stream.read(min(1024 * 1024, remaining))
                    if not block:
                        raise HostedRunnerError("BUNDLE_TRUNCATED", relative)
                    digest.update(block)
                    remaining -= len(block)
                if body_stream.read(1) or digest.hexdigest() != row["sha256"]:
                    raise HostedRunnerError("BUNDLE_PAYLOAD_MISMATCH", relative)
    except HostedRunnerError:
        raise
    except (OSError, tarfile.TarError) as error:
        raise HostedRunnerError("BUNDLE_UNSAFE", "bundle cannot be parsed") from error
    return VerifiedBundle(
        path=path,
        sha256=observed_sha256,
        size=metadata.st_size,
        manifest=manifest,
        manifest_sha256=locks.sha256_bytes(manifest_bytes),
    )


def extract_verified_bundle(
    bundle: VerifiedBundle, destination: Path
) -> Mapping[str, Path]:
    """Extract a previously verified bundle without overwrite or link following."""

    root = Path(destination)
    if root.exists() or root.is_symlink():
        raise HostedRunnerError(
            "BUNDLE_DESTINATION_UNSAFE", "destination must be absent"
        )
    root.mkdir(parents=True, mode=0o700)
    paths: dict[str, Path] = {}
    with tarfile.open(bundle.path, mode="r:gz") as archive:
        for row in bundle.manifest["files"]:
            relative = row["path"]
            target = root.joinpath(*PurePosixPath(relative).parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists() or target.is_symlink():
                raise HostedRunnerError("BUNDLE_DESTINATION_UNSAFE", relative)
            member = archive.getmember(relative)
            source = archive.extractfile(member)
            if source is None:
                raise HostedRunnerError("BUNDLE_TRUNCATED", relative)
            descriptor = os.open(
                target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, int(row["mode"], 8)
            )
            try:
                with os.fdopen(descriptor, "wb", closefd=False) as output:
                    shutil.copyfileobj(source, output, length=1024 * 1024)
            finally:
                os.close(descriptor)
            os.chmod(target, int(row["mode"], 8))
            paths[relative] = target
    return paths


def write_semantic_receipt(
    path: Path,
    *,
    request: ExperimentRequest,
    status: str,
    effect: str,
    evidence: Mapping[str, object],
) -> Mapping[str, Any]:
    """Atomically persist a self-digested, secret-free semantic receipt."""

    _validate_receipt_state(status, effect)
    unsigned: dict[str, object] = {
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "mode": "Z0",
        "operation_key": request.operation_key,
        "request": request.payload,
        "request_digest": request.digest,
        "status": status,
        "effect": effect,
        "evidence": dict(evidence),
    }
    assert_secret_free(unsigned)
    payload = dict(unsigned)
    payload["semantic_digest"] = locks.sha256_bytes(
        locks.canonical_json_bytes(unsigned)
    )
    body = locks.canonical_json_bytes(payload) + b"\n"
    if len(body) > 1_048_576:
        raise HostedRunnerError("RECEIPT_TOO_LARGE", str(len(body)))
    _atomic_write_new_or_identical(Path(path), body, mode=0o600)
    return payload


def write_network_seal_boundary_receipt(
    request: ExperimentRequest,
    path: Path,
    *,
    effect_unknown: bool,
) -> Mapping[str, Any]:
    """Record a namespace-boundary refusal or conservative unknown effect."""

    if not isinstance(effect_unknown, bool):
        raise HostedRunnerError("RECEIPT_INVALID", "boundary state is not boolean")
    launch_evidence: dict[str, object] = (
        {"consumer_launch_state": "UNKNOWN"}
        if effect_unknown
        else {"consumer_launched": False}
    )
    return write_semantic_receipt(
        path,
        request=request,
        status="RECONCILIATION_REQUIRED" if effect_unknown else "REFUSED",
        effect="EFFECT_UNKNOWN" if effect_unknown else "NOT_APPLIED",
        evidence={
            "failure": {
                "code": (
                    "NETWORK_SEAL_EFFECT_UNKNOWN"
                    if effect_unknown
                    else "NETWORK_SEAL_UNAVAILABLE"
                ),
                "detail": (
                    "sealed child ended without a durable receipt"
                    if effect_unknown
                    else "user and network namespace probe failed"
                ),
            },
            **launch_evidence,
            "runner": _runner_confounds(),
        },
    )


def load_semantic_receipt(path: Path) -> Mapping[str, Any]:
    """Read and validate a receipt before any replay decision."""

    candidate = Path(path)
    try:
        metadata = candidate.lstat()
    except OSError as error:
        raise HostedRunnerError("RECEIPT_UNAVAILABLE", candidate.name) from error
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_size > 1_048_576
    ):
        raise HostedRunnerError("RECEIPT_UNSAFE", candidate.name)
    try:
        payload = json.loads(candidate.read_bytes())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise HostedRunnerError("RECEIPT_INVALID", candidate.name) from error
    if not isinstance(payload, Mapping):
        raise HostedRunnerError("RECEIPT_INVALID", "receipt is not an object")
    expected_fields = {
        "schema_version",
        "mode",
        "operation_key",
        "request",
        "request_digest",
        "status",
        "effect",
        "evidence",
        "semantic_digest",
    }
    if set(payload) != expected_fields:
        raise HostedRunnerError("RECEIPT_INVALID", "receipt fields differ")
    if (
        payload.get("schema_version") != RECEIPT_SCHEMA_VERSION
        or payload.get("mode") != "Z0"
        or payload.get("operation_key") != Z0_OPERATION_KEY
    ):
        raise HostedRunnerError("RECEIPT_INVALID", "receipt identity differs")
    unsigned = {
        key: value for key, value in payload.items() if key != "semantic_digest"
    }
    observed_digest = locks.sha256_bytes(locks.canonical_json_bytes(unsigned))
    if payload.get("semantic_digest") != observed_digest:
        raise HostedRunnerError("RECEIPT_DIGEST_MISMATCH", candidate.name)
    _validate_receipt_state(payload.get("status"), payload.get("effect"))
    if not isinstance(payload.get("evidence"), Mapping):
        raise HostedRunnerError("RECEIPT_INVALID", "receipt evidence is not an object")
    request_payload = payload.get("request")
    if not isinstance(request_payload, Mapping):
        raise HostedRunnerError("RECEIPT_INVALID", "request is absent")
    try:
        reconstructed = ExperimentRequest.from_values(
            operation_key=str(request_payload["operation_key"]),
            consumer_sha=str(request_payload["consumer_sha"]),
            consumer_tree_sha=str(request_payload["consumer_tree_sha"]),
            forge_sha=str(request_payload["forge_sha"]),
            forge_tree_sha=str(request_payload["forge_tree_sha"]),
            lock_sha256=str(request_payload["lock_sha256"]),
            workflow_sha256=str(request_payload["workflow_sha256"]),
        )
    except (KeyError, HostedRunnerError) as error:
        raise HostedRunnerError(
            "RECEIPT_INVALID", "request cannot be reconstructed"
        ) from error
    if (
        request_payload != reconstructed.payload
        or payload.get("request_digest") != reconstructed.digest
    ):
        raise HostedRunnerError("RECEIPT_INVALID", "request identity is inconsistent")
    assert_secret_free(payload)
    return dict(payload)


def reconcile_receipt(path: Path, request: ExperimentRequest) -> ReplayResolution:
    """Return an identical completed result, conflict on drift, or hold unknown effects."""

    candidate = Path(path)
    if not candidate.exists() and not candidate.is_symlink():
        return ReplayResolution(ReplayDisposition.PROCEED)
    receipt = load_semantic_receipt(candidate)
    if receipt["operation_key"] != request.operation_key:
        raise HostedRunnerError("REQUEST_CONFLICT", "operation key is already occupied")
    if (
        receipt["request_digest"] != request.digest
        or receipt["request"] != request.payload
    ):
        raise HostedRunnerError("REQUEST_CONFLICT", "normalized request changed")
    if receipt["effect"] == "EFFECT_UNKNOWN":
        raise HostedRunnerError(
            "EFFECT_UNKNOWN_REPLAY_BLOCKED", "canonical effect must be reconciled first"
        )
    if (receipt["status"], receipt["effect"]) in {
        ("COMPLETED", "APPLIED"),
        ("REFUSED", "NOT_APPLIED"),
    }:
        return ReplayResolution(ReplayDisposition.RETURN_PRIOR, receipt)
    raise HostedRunnerError(
        "REPLAY_BLOCKED", "prior request is not terminally replayable"
    )


def workflow_run_name(request: ExperimentRequest) -> str:
    """Return the exact run-name contract also embedded in the workflow."""

    return (
        f"codeintel-z0|op={request.operation_key}|consumer={request.consumer_sha}|"
        f"tree={request.consumer_tree_sha}|forge={request.forge_sha}"
    )


def operation_artifact_name() -> str:
    digest = hashlib.sha256(Z0_OPERATION_KEY.encode("ascii")).hexdigest()
    return f"codeintel-z0-operation-{digest}"


def reconcile_prior_runs(
    request: ExperimentRequest,
    *,
    current_run_id: int,
    destination: Path,
    github_output: Path | None = None,
) -> ReplayResolution:
    """Reconcile all prior same-operation workflow runs before any new build."""

    if current_run_id <= 0:
        raise HostedRunnerError("REPLAY_LOOKUP_INVALID", "current run id is invalid")
    expected_title = workflow_run_name(request)
    operation_prefix = f"codeintel-z0|op={request.operation_key}|"
    raw_runs = _gh_paginated_rows(
        "repos/mastermindx-market-intelligence/Mastermind/actions/workflows/"
        "codeintel-experiment-bundle.yml/runs?event=workflow_dispatch",
        field="workflow_runs",
        max_rows=10_000,
    )
    matching_runs: list[Mapping[str, Any]] = []
    for raw_run in raw_runs:
        if not isinstance(raw_run, Mapping):
            raise HostedRunnerError(
                "REPLAY_LOOKUP_INVALID", "workflow run row malformed"
            )
        run_id = raw_run.get("id")
        if run_id == current_run_id:
            continue
        title = raw_run.get("display_title")
        if not isinstance(title, str) or not title.startswith(operation_prefix):
            continue
        if title != expected_title:
            raise HostedRunnerError(
                "REQUEST_CONFLICT",
                "the fixed operation already has changed normalized input",
            )
        matching_runs.append(raw_run)
    if not matching_runs:
        resolution = ReplayResolution(ReplayDisposition.PROCEED)
        if github_output is not None:
            _append_github_outputs(
                github_output, {"disposition": resolution.disposition.value}
            )
        return resolution

    receipts: list[tuple[bytes, Mapping[str, Any]]] = []
    for raw_run in matching_runs:
        run_id = raw_run.get("id")
        if not isinstance(run_id, int) or run_id <= 0:
            raise HostedRunnerError("REPLAY_LOOKUP_INVALID", "prior run id malformed")
        status = raw_run.get("status")
        if status != "completed":
            raise HostedRunnerError(
                "EFFECT_UNKNOWN_REPLAY_BLOCKED", f"prior run {run_id} is {status}"
            )
        artifacts = _gh_paginated_rows(
            f"repos/{FIXED_REPOSITORY}/actions/runs/{run_id}/artifacts",
            field="artifacts",
            max_rows=1_000,
        )
        candidates = [
            artifact
            for artifact in artifacts
            if isinstance(artifact, Mapping)
            and artifact.get("name") == operation_artifact_name()
            and artifact.get("expired") is False
        ]
        if len(candidates) != 1:
            raise HostedRunnerError(
                "EFFECT_UNKNOWN_REPLAY_BLOCKED",
                f"prior run {run_id} has no unique durable semantic receipt",
            )
        artifact_size = candidates[0].get("size_in_bytes")
        if (
            isinstance(artifact_size, bool)
            or not isinstance(artifact_size, int)
            or not 0 < artifact_size <= 4_194_304
        ):
            raise HostedRunnerError(
                "REPLAY_LOOKUP_INVALID", "receipt artifact size is unsafe"
            )
        artifact_id = candidates[0].get("id")
        if not isinstance(artifact_id, int) or artifact_id <= 0:
            raise HostedRunnerError("REPLAY_LOOKUP_INVALID", "artifact id malformed")
        with tempfile.TemporaryDirectory(prefix="codeintel-prior-") as temporary:
            zip_path = Path(temporary) / "receipt.zip"
            _gh_download_artifact(artifact_id, zip_path)
            receipt_bytes = _read_receipt_from_artifact_zip(zip_path)
            receipt_path = Path(temporary) / "semantic-receipt.json"
            receipt_path.write_bytes(receipt_bytes)
            receipt = load_semantic_receipt(receipt_path)
            resolution = reconcile_receipt(receipt_path, request)
            if resolution.disposition is not ReplayDisposition.RETURN_PRIOR:
                raise HostedRunnerError(
                    "REPLAY_LOOKUP_INVALID", "prior artifact is not terminal"
                )
            receipts.append((receipt_bytes, receipt))
    first_bytes, first_receipt = receipts[0]
    if any(body != first_bytes for body, _receipt in receipts[1:]):
        raise HostedRunnerError(
            "EFFECT_UNKNOWN_REPLAY_BLOCKED", "prior semantic receipts disagree"
        )
    output = Path(destination)
    _atomic_write_new_or_identical(output, first_bytes, mode=0o600)
    if github_output is not None:
        if first_receipt["status"] == "REFUSED":
            returncode = 1
        else:
            observed_returncode = (
                first_receipt.get("evidence", {}).get("launch", {}).get("returncode", 0)
            )
            if isinstance(observed_returncode, bool) or not isinstance(
                observed_returncode, int
            ):
                raise HostedRunnerError("RECEIPT_INVALID", "return code is malformed")
            returncode = 0 if observed_returncode == 0 else 1
        _append_github_outputs(
            github_output,
            {
                "disposition": ReplayDisposition.RETURN_PRIOR.value,
                "prior_returncode": str(returncode),
            },
        )
    return ReplayResolution(ReplayDisposition.RETURN_PRIOR, first_receipt)


def _gh_download_artifact(artifact_id: int, destination: Path) -> None:
    try:
        with destination.open("xb") as output:
            completed = subprocess.run(
                [
                    "/usr/bin/gh",
                    "api",
                    "-H",
                    "Accept: application/vnd.github+json",
                    f"repos/{FIXED_REPOSITORY}/actions/artifacts/{artifact_id}/zip",
                ],
                check=False,
                stdin=subprocess.DEVNULL,
                stdout=output,
                stderr=subprocess.PIPE,
                timeout=60,
            )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise HostedRunnerError(
            "REPLAY_LOOKUP_INVALID", "artifact download failed"
        ) from error
    if completed.returncode != 0:
        detail = _bounded_redacted(
            completed.stderr.decode("utf-8", errors="replace"), 1024
        )
        raise HostedRunnerError(
            "REPLAY_LOOKUP_INVALID", f"artifact download rejected: {detail}"
        )
    if destination.stat().st_size > 4_194_304:
        raise HostedRunnerError(
            "REPLAY_LOOKUP_INVALID", "receipt artifact is oversized"
        )


def _read_receipt_from_artifact_zip(path: Path) -> bytes:
    try:
        with zipfile.ZipFile(path) as archive:
            infos = archive.infolist()
            if len(infos) != 1:
                raise HostedRunnerError(
                    "REPLAY_LOOKUP_INVALID", "receipt artifact member census differs"
                )
            info = infos[0]
            mode = (info.external_attr >> 16) & 0o170000
            if (
                info.filename != "semantic-receipt.json"
                or info.is_dir()
                or mode == stat.S_IFLNK
                or info.file_size > 1_048_576
            ):
                raise HostedRunnerError(
                    "REPLAY_LOOKUP_INVALID", "receipt artifact member is unsafe"
                )
            body = archive.read(info)
    except HostedRunnerError:
        raise
    except (OSError, zipfile.BadZipFile, KeyError) as error:
        raise HostedRunnerError(
            "REPLAY_LOOKUP_INVALID", "receipt artifact is invalid"
        ) from error
    if len(body) > 1_048_576:
        raise HostedRunnerError("REPLAY_LOOKUP_INVALID", "receipt is oversized")
    return body


def sanitized_consumer_environment(scratch_root: Path) -> dict[str, str]:
    """Construct the complete credential-free environment inherited by candidate processes."""

    root = Path(scratch_root)
    if root.exists() or root.is_symlink():
        root = _real_directory(root, "SCRATCH_UNSAFE")
    else:
        root.mkdir(parents=True, mode=0o700)
    home = root / "home"
    temporary = root / "tmp"
    home.mkdir(mode=0o700, exist_ok=True)
    temporary.mkdir(mode=0o700, exist_ok=True)
    return {
        "HOME": os.fspath(home.resolve()),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PATH": "/usr/bin:/bin",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONHASHSEED": "0",
        "TMPDIR": os.fspath(temporary.resolve()),
        "TZ": "UTC",
    }


def assert_secret_free(value: object) -> None:
    """Reject credential-like fields/values and private absolute workspace paths."""

    def visit(item: object, *, key: str | None = None) -> None:
        if key is not None and key != "secret_free" and _FORBIDDEN_KEY_RE.search(key):
            raise HostedRunnerError("SECRET_BEARING_OUTPUT", f"forbidden field {key}")
        if isinstance(item, Mapping):
            for child_key, child in item.items():
                if not isinstance(child_key, str):
                    raise HostedRunnerError(
                        "SECRET_BEARING_OUTPUT", "non-text metadata key"
                    )
                visit(child, key=child_key)
        elif isinstance(item, Sequence) and not isinstance(
            item, (str, bytes, bytearray)
        ):
            for child in item:
                visit(child)
        elif isinstance(item, str):
            if any(pattern.search(item) for pattern in _SECRET_TEXT_PATTERNS):
                raise HostedRunnerError("SECRET_BEARING_OUTPUT", "credential-like text")
            if any(pattern.search(item) for pattern in _PRIVATE_PATH_PATTERNS):
                raise HostedRunnerError(
                    "SECRET_BEARING_OUTPUT", "private absolute path"
                )
        elif isinstance(item, bytes):
            text = item.decode("utf-8", errors="ignore")
            if any(pattern.search(text) for pattern in _SECRET_TEXT_PATTERNS):
                raise HostedRunnerError(
                    "SECRET_BEARING_OUTPUT", "credential-like bytes"
                )
            if any(pattern.search(text) for pattern in _PRIVATE_PATH_PATTERNS):
                raise HostedRunnerError(
                    "SECRET_BEARING_OUTPUT", "private absolute path"
                )

    visit(value)


def fixed_consumer_argv(
    *,
    python_executable: Path,
    consumer_root: Path,
    manifest: Path,
    path_policy: Path,
    indexer: Path,
    indexer_sha256: str,
    webserver: Path,
    webserver_sha256: str,
    shard_root: Path,
    log_root: Path,
    result: Path,
    report: Path,
) -> list[str]:
    """Return the one repository-owned consumer module and complete fixed argv."""

    for label, digest in (
        ("indexer", indexer_sha256),
        ("webserver", webserver_sha256),
    ):
        if _SHA256_RE.fullmatch(digest) is None:
            raise HostedRunnerError("INVALID_REQUEST", f"{label} digest is not exact")
    values = [
        python_executable,
        consumer_root,
        manifest,
        path_policy,
        indexer,
        webserver,
        shard_root,
        log_root,
        result,
        report,
    ]
    if any(not Path(value).is_absolute() for value in values):
        raise HostedRunnerError(
            "INVALID_REQUEST", "consumer paths must be host-owned absolutes"
        )
    return [
        os.fspath(python_executable),
        "-I",
        "-c",
        _CONSUMER_BOOTSTRAP,
        os.fspath(consumer_root),
        "--manifest",
        os.fspath(manifest),
        "--path-policy",
        os.fspath(path_policy),
        "--indexer",
        os.fspath(indexer),
        "--indexer-sha256",
        indexer_sha256,
        "--webserver",
        os.fspath(webserver),
        "--webserver-sha256",
        webserver_sha256,
        "--shard-root",
        os.fspath(shard_root),
        "--log-root",
        os.fspath(log_root),
        "--result",
        os.fspath(result),
        "--report",
        os.fspath(report),
        "--startup-timeout-seconds",
        "10",
    ]


def observe_network_seal() -> NetworkSealProof:
    """Prove the caller is in a loopback-only namespace and outbound connect is denied."""

    try:
        interfaces = tuple(sorted(name for _index, name in socket.if_nameindex()))
    except OSError as error:
        raise HostedRunnerError(
            "NETWORK_SEAL_UNAVAILABLE", "interface census failed"
        ) from error
    routes: list[str] = []
    route_file = Path("/proc/net/route")
    try:
        rows = route_file.read_text(encoding="ascii").splitlines()
    except (OSError, UnicodeDecodeError) as error:
        raise HostedRunnerError(
            "NETWORK_SEAL_UNAVAILABLE", "Linux route table unavailable"
        ) from error
    for row in rows[1:]:
        fields = row.split()
        if fields and fields[0] != "lo":
            routes.append(row)
    denial: int | None = None
    probe_state = "CONNECTED"
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    probe.settimeout(1.0)
    try:
        probe.connect(("1.1.1.1", 443))
    except OSError as error:
        denial = error.errno
        if denial in {
            errno.ENETUNREACH,
            errno.EHOSTUNREACH,
            errno.ENETDOWN,
            errno.EACCES,
        }:
            probe_state = "DENIED"
        else:
            probe_state = f"INCONCLUSIVE_ERRNO_{denial}"
    finally:
        probe.close()
    return NetworkSealProof(interfaces, tuple(routes), probe_state, denial)


def prove_then_launch(
    *,
    probe: Callable[[], NetworkSealProof],
    launch: Callable[[], LaunchEvidence],
) -> tuple[NetworkSealProof, LaunchEvidence]:
    """Enforce the causality edge: successful denial proof strictly precedes launch."""

    proof = probe()
    if (
        proof.interfaces != ("lo",)
        or proof.non_loopback_routes
        or proof.outbound_probe != "DENIED"
        or proof.denial_errno
        not in {errno.ENETUNREACH, errno.EHOSTUNREACH, errno.ENETDOWN, errno.EACCES}
    ):
        raise HostedRunnerError(
            "NETWORK_SEAL_UNAVAILABLE", "loopback-only outbound denial was not proven"
        )
    return proof, launch()


def validate_cleanup(evidence: CleanupEvidence) -> bool:
    if not evidence.process_group_dead or evidence.unexpected_residue:
        raise HostedRunnerError(
            "CLEANUP_LEAK", "candidate process or scratch residue remains"
        )
    return True


def load_request(path: Path) -> ExperimentRequest:
    """Load a canonical request file and rederive every normalized field."""

    candidate = Path(path)
    try:
        metadata = candidate.lstat()
        raw = candidate.read_bytes()
        value = json.loads(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise HostedRunnerError(
            "INVALID_REQUEST", "request file is unavailable"
        ) from error
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_size > 65_536
        or not isinstance(value, Mapping)
    ):
        raise HostedRunnerError("INVALID_REQUEST", "request file is unsafe")
    expected_fields = {
        "consumer_sha",
        "consumer_tree_sha",
        "forge_sha",
        "forge_tree_sha",
        "lock_sha256",
        "mode",
        "operation_key",
        "repository",
        "workflow_sha256",
    }
    if set(value) != expected_fields:
        raise HostedRunnerError("INVALID_REQUEST", "request fields differ")
    request = ExperimentRequest.from_values(
        operation_key=str(value["operation_key"]),
        consumer_sha=str(value["consumer_sha"]),
        consumer_tree_sha=str(value["consumer_tree_sha"]),
        forge_sha=str(value["forge_sha"]),
        forge_tree_sha=str(value["forge_tree_sha"]),
        lock_sha256=str(value["lock_sha256"]),
        workflow_sha256=str(value["workflow_sha256"]),
    )
    if value != request.payload or raw != request.canonical_bytes + b"\n":
        raise HostedRunnerError("INVALID_REQUEST", "request is not canonical")
    return request


def derive_request(
    forge_root: Path,
    *,
    operation_key: str,
    consumer_sha: str,
    consumer_tree_sha: str,
) -> ExperimentRequest:
    """Derive forge, lock, and workflow identity rather than trusting the caller."""

    root = _real_directory(forge_root, "FORGE_SOURCE_MISMATCH")
    if git_stdout(root, "status", "--porcelain=v1", "--untracked-files=all"):
        raise HostedRunnerError("FORGE_SOURCE_DIRTY", "forge checkout is not clean")
    forge_sha = git_stdout(root, "rev-parse", "--verify", "HEAD")
    forge_tree = git_stdout(root, "rev-parse", "--verify", "HEAD^{tree}")
    lock_path = (
        root
        / "research/code_intelligence_fabric/codeintel-experiment-toolchain-lock.v1.json"
    )
    schema_path = (
        root
        / "research/code_intelligence_fabric/codeintel-experiment-toolchain-lock.schema.json"
    )
    lock = locks.load_toolchain_lock(lock_path, schema_path=schema_path)
    workflow_path = root / FIXED_WORKFLOW_PATH
    workflow_sha256 = locks.sha256_file(workflow_path, max_bytes=1_048_576)
    return ExperimentRequest.from_values(
        operation_key=operation_key,
        consumer_sha=consumer_sha,
        consumer_tree_sha=consumer_tree_sha,
        forge_sha=forge_sha,
        forge_tree_sha=forge_tree,
        lock_sha256=lock.sha256,
        workflow_sha256=workflow_sha256,
    )


def prepare_phase_p(
    forge_root: Path,
    request: ExperimentRequest,
    *,
    scratch_root: Path,
    output_directory: Path,
    github_output: Path | None = None,
) -> Mapping[str, Any]:
    """Acquire, verify, repeat-build, inventory, and bundle the exact Z0 toolchain."""

    root = _real_directory(forge_root, "FORGE_SOURCE_MISMATCH")
    derived = derive_request(
        root,
        operation_key=request.operation_key,
        consumer_sha=request.consumer_sha,
        consumer_tree_sha=request.consumer_tree_sha,
    )
    if derived != request:
        raise HostedRunnerError("REQUEST_CONFLICT", "forge request identity moved")
    lock_path = (
        root
        / "research/code_intelligence_fabric/codeintel-experiment-toolchain-lock.v1.json"
    )
    schema_path = (
        root
        / "research/code_intelligence_fabric/codeintel-experiment-toolchain-lock.schema.json"
    )
    lock = locks.load_toolchain_lock(lock_path, schema_path=schema_path)
    scratch = _fresh_directory(scratch_root, "SCRATCH_CONFLICT")
    output = _ensure_output_directory(output_directory)
    downloads = scratch / "downloads"
    extracted = scratch / "extracted"
    source = scratch / "zoekt-source"
    builds = scratch / "builds"
    payload = scratch / "payload"
    for directory in (downloads, extracted, builds, payload / "bin", payload / "meta"):
        directory.mkdir(parents=True, mode=0o700)

    go_archive = downloads / locks.GO_ARCHIVE_FILENAME
    effective_url = _download_exact_go_archive(go_archive)
    limits = lock.payload["limits"]
    locks.safe_extract_tar(
        go_archive,
        extracted,
        expected_sha256=locks.GO_ARCHIVE_SHA256,
        expected_size=locks.GO_ARCHIVE_SIZE,
        expected_top_level="go",
        max_archive_bytes=int(limits["archive_bytes"]),
        max_member_bytes=int(limits["archive_member_bytes"]),
        max_total_bytes=int(limits["archive_total_bytes"]),
    )
    go_root = extracted / "go"
    go_binary = go_root / "bin/go"
    _verify_go_distribution(go_root, go_binary)
    go_source_metadata = _verify_go_source_metadata()

    _checkout_exact_zoekt(source)
    source_before = locks.verify_zoekt_source(source, lock)
    build = _repeat_build_zoekt(
        source,
        go_binary=go_binary,
        scratch=builds,
        payload_bin=payload / "bin",
    )
    source_after = locks.verify_zoekt_source(source, lock)
    if source_before != source_after:
        raise HostedRunnerError("SOURCE_DRIFT", "Zoekt identity changed during build")

    module_inventory = build["modules"]
    sbom = {
        "schema_version": "mastermind.codeintel_go_module_inventory.v1",
        "main_module": locks.ZOEKT_REPOSITORY,
        "go_version": locks.GO_VERSION,
        "go_mod_blob_sha1": locks.ZOEKT_GO_MOD_BLOB,
        "go_sum_blob_sha1": locks.ZOEKT_GO_SUM_BLOB,
        "modules": module_inventory,
    }
    assert_secret_free(sbom)
    sbom_bytes = locks.canonical_json_bytes(sbom) + b"\n"
    (payload / "meta/sbom.json").write_bytes(sbom_bytes)

    notice = (
        "Mastermind CodeIntel Z0 disposable experiment bundle\n"
        f"Zoekt {locks.ZOEKT_COMMIT} — Apache-2.0; exact LICENSE follows.\n"
        f"Go {locks.GO_VERSION} ({locks.GO_SOURCE_COMMIT}) — BSD-3-Clause; exact "
        "LICENSE follows.\n"
        "Universal Ctags: DISABLED; no Ctags bytes are present.\n\n"
        "===== ZOEKT LICENSE =====\n"
    ).encode("utf-8")
    notice += (source / "LICENSE").read_bytes()
    notice += b"\n===== GO LICENSE =====\n"
    notice += (go_root / "LICENSE").read_bytes()
    (payload / "meta/NOTICE.txt").write_bytes(notice)
    shutil.copyfile(lock_path, payload / "meta/toolchain-lock.json")

    provenance = {
        "schema_version": PHASE_P_PROVENANCE_SCHEMA_VERSION,
        "request_digest": request.digest,
        "lock_sha256": lock.sha256,
        "build_recipe_sha256": lock.build_recipe_sha256,
        "phase": "P",
        "network": {
            "state": "ENABLED_FOR_ALLOWLISTED_ACQUISITION_ONLY",
            "allowed_hosts": list(locks.ALLOWED_HOSTS),
            "go_archive_effective_host": urlparse(effective_url).hostname,
        },
        "runner": _runner_confounds(),
        "actions": lock.payload["actions"],
        "host_utility_confounds": list(locks.HOST_UTILITY_CONFOUNDS),
        "go": {
            "version": locks.GO_VERSION,
            "archive_filename": locks.GO_ARCHIVE_FILENAME,
            "archive_sha256": locks.GO_ARCHIVE_SHA256,
            "archive_size": locks.GO_ARCHIVE_SIZE,
            "source": go_source_metadata,
            "license_blob_sha1": locks.GO_LICENSE_BLOB,
            "license_sha256": locks.GO_LICENSE_SHA256,
        },
        "zoekt": {
            **dataclasses.asdict(source_before),
            "go_mod_sha256": locks.ZOEKT_GO_MOD_SHA256,
            "go_sum_sha256": locks.ZOEKT_GO_SUM_SHA256,
            "license_sha256": locks.ZOEKT_LICENSE_SHA256,
        },
        "module_inventory_sha256": locks.sha256_bytes(sbom_bytes),
        "binaries": build["binaries"],
        "source_before": dataclasses.asdict(source_before),
        "source_after": dataclasses.asdict(source_after),
        "universal_ctags": {
            "enabled": False,
            "observation": "NO_CTAGS_BYTES_BUNDLED_OR_RESOLVED",
        },
    }
    assert_secret_free(provenance)
    provenance_bytes = locks.canonical_json_bytes(provenance) + b"\n"
    (payload / "meta/provenance.json").write_bytes(provenance_bytes)

    bundle = create_content_addressed_bundle(
        payload,
        output,
        context={
            "request_digest": request.digest,
            "lock_sha256": lock.sha256,
            "build_recipe_sha256": lock.build_recipe_sha256,
            "module_inventory_sha256": locks.sha256_bytes(sbom_bytes),
            "provenance_sha256": locks.sha256_bytes(provenance_bytes),
        },
    )
    result = {
        "schema_version": "mastermind.codeintel_phase_p_result.v1",
        "request_digest": request.digest,
        "bundle_name": bundle.name,
        "bundle_sha256": bundle.sha256,
        "bundle_size": bundle.size,
        "manifest_sha256": bundle.manifest_sha256,
        "lock_sha256": lock.sha256,
        "build_recipe_sha256": lock.build_recipe_sha256,
        "module_inventory_sha256": locks.sha256_bytes(sbom_bytes),
        "provenance_sha256": locks.sha256_bytes(provenance_bytes),
        "binary_digests": {
            name: row["sha256"] for name, row in build["binaries"].items()
        },
    }
    assert_secret_free(result)
    result_path = output / "phase-p-result.json"
    _atomic_write_new_or_identical(
        result_path, locks.canonical_json_bytes(result) + b"\n", mode=0o600
    )
    if github_output is not None:
        _append_github_outputs(
            github_output,
            {
                "bundle_name": bundle.name,
                "bundle_sha256": bundle.sha256,
                "manifest_sha256": bundle.manifest_sha256,
            },
        )
    return result


def prepare_phase_p_or_record_refusal(
    forge_root: Path,
    request: ExperimentRequest,
    *,
    scratch_root: Path,
    output_directory: Path,
    github_output: Path,
    receipt_path: Path,
) -> Mapping[str, Any]:
    """Run Phase P or durably preserve its known pre-consumer refusal."""

    try:
        return prepare_phase_p(
            forge_root,
            request,
            scratch_root=scratch_root,
            output_directory=output_directory,
            github_output=github_output,
        )
    except (HostedRunnerError, locks.ToolchainLockError) as error:
        _write_phase_p_refusal(
            request,
            receipt_path,
            code=getattr(error, "code", "PHASE_P_FAILED"),
            detail=_bounded_redacted(getattr(error, "detail", str(error)), 512),
        )
        raise
    except OSError as cause:
        error = HostedRunnerError(
            "PHASE_P_IO_FAILED", "Phase P filesystem operation failed"
        )
        _write_phase_p_refusal(
            request,
            receipt_path,
            code=error.code,
            detail=error.detail,
        )
        raise error from cause


def _write_phase_p_refusal(
    request: ExperimentRequest,
    receipt_path: Path,
    *,
    code: str,
    detail: str,
) -> None:
    write_semantic_receipt(
        receipt_path,
        request=request,
        status="REFUSED",
        effect="NOT_APPLIED",
        evidence={
            "failure": {"code": code, "detail": detail},
            "phase": "P",
            "consumer_launched": False,
            "runner": _runner_confounds(),
        },
    )


def run_phase_e(
    forge_root: Path,
    consumer_root: Path,
    request: ExperimentRequest,
    *,
    bundle_path: Path,
    bundle_sha256: str,
    scratch_root: Path,
    result_directory: Path,
    receipt_path: Path,
) -> Mapping[str, Any]:
    """Reverify exact inputs, prove the seal, and invoke only the fixed Z0 module."""

    forge = _real_directory(forge_root, "FORGE_SOURCE_MISMATCH")
    derived = derive_request(
        forge,
        operation_key=request.operation_key,
        consumer_sha=request.consumer_sha,
        consumer_tree_sha=request.consumer_tree_sha,
    )
    if derived != request:
        raise HostedRunnerError("REQUEST_CONFLICT", "forge request identity moved")
    lock_path = (
        forge
        / "research/code_intelligence_fabric/codeintel-experiment-toolchain-lock.v1.json"
    )
    schema_path = (
        forge
        / "research/code_intelligence_fabric/codeintel-experiment-toolchain-lock.schema.json"
    )
    lock = locks.load_toolchain_lock(lock_path, schema_path=schema_path)
    if lock.sha256 != request.lock_sha256:
        raise HostedRunnerError("REQUEST_CONFLICT", "lock bytes moved")
    expected_name = f"codeintel-z0-{bundle_sha256}.tar.gz"
    if Path(bundle_path).name != expected_name:
        raise HostedRunnerError(
            "BUNDLE_SUBSTITUTION", "bundle name does not bind complete bytes"
        )
    verified_before = verify_bundle(bundle_path, expected_sha256=bundle_sha256)

    consumer = verify_consumer_checkout(
        consumer_root, request.consumer_sha, request.consumer_tree_sha
    )
    merge_base, changed_paths = consumer_effective_paths(
        consumer_root,
        consumer_sha=request.consumer_sha,
        forge_sha=request.forge_sha,
    )
    consumer_policy = lock.payload["consumer"]
    includes = tuple(consumer_policy["index_includes"])
    excludes = tuple(consumer_policy["index_excludes"])
    source_before = selected_source_digest(
        consumer_root, includes=includes, excludes=excludes
    )
    scratch = _fresh_directory(scratch_root, "SCRATCH_CONFLICT")
    outputs = _ensure_output_directory(result_directory)
    extracted = extract_verified_bundle(verified_before, scratch / "bundle")
    indexer = _verified_executable(
        extracted["bin/zoekt-git-index"],
        expected_sha256=_manifest_file_digest(
            verified_before.manifest, "bin/zoekt-git-index"
        ),
    )
    webserver = _verified_executable(
        extracted["bin/zoekt-webserver"],
        expected_sha256=_manifest_file_digest(
            verified_before.manifest, "bin/zoekt-webserver"
        ),
    )
    binary_before = {
        "zoekt-git-index": locks.sha256_file(indexer, max_bytes=100_663_296),
        "zoekt-webserver": locks.sha256_file(webserver, max_bytes=100_663_296),
    }

    input_root = scratch / "input"
    input_root.mkdir(mode=0o700)
    path_policy = (Path(consumer_root) / str(consumer_policy["path_policy"])).resolve()
    _require_within_root(path_policy, Path(consumer_root))
    _regular_file(path_policy, "CONSUMER_PATH_POLICY_UNSAFE", max_bytes=1_048_576)
    manifest = input_root / "manifest.json"
    manifest_payload = {
        "schema_version": "mastermind.codeintel_index_manifest.v1",
        "repositories": [
            {
                "repository_id": "mastermind",
                "repository_name": FIXED_REPOSITORY,
                "source_snapshot_root": os.fspath(Path(consumer_root).resolve()),
                "ref_label": FIXED_CONSUMER_BRANCH,
                "commit_sha": request.consumer_sha,
                "included_prefixes": list(includes),
                "excluded_globs": list(excludes),
                "source_tree_digest": source_before,
            }
        ],
    }
    manifest.write_bytes(locks.canonical_json_bytes(manifest_payload) + b"\n")
    os.chmod(manifest, 0o600)

    shard_root = scratch / "shards"
    log_root = scratch / "logs"
    environment_root = scratch / "consumer-environment"
    result_path = outputs / "z0-result.json"
    report_path = outputs / "z0-report.md"
    argv = fixed_consumer_argv(
        python_executable=Path(sys.executable).resolve(),
        consumer_root=Path(consumer_root).resolve(),
        manifest=manifest.resolve(),
        path_policy=path_policy,
        indexer=indexer,
        indexer_sha256=binary_before["zoekt-git-index"],
        webserver=webserver,
        webserver_sha256=binary_before["zoekt-webserver"],
        shard_root=shard_root.resolve(),
        log_root=log_root.resolve(),
        result=result_path.resolve(),
        report=report_path.resolve(),
    )
    environment = sanitized_consumer_environment(environment_root)
    proof: NetworkSealProof | None = None
    launch: LaunchEvidence | None = None
    launched = False
    try:

        def launch_fixed() -> LaunchEvidence:
            nonlocal launched
            launched = True
            return _launch_fixed_consumer(
                argv,
                cwd=Path(consumer_root).resolve(),
                env=environment,
                timeout_seconds=int(lock.payload["limits"]["consumer_seconds"]),
                log_limit=int(lock.payload["limits"]["log_bytes_each"]),
            )

        proof, launch = prove_then_launch(
            probe=observe_network_seal,
            launch=launch_fixed,
        )
        source_after = selected_source_digest(
            consumer_root, includes=includes, excludes=excludes
        )
        binary_after = {
            "zoekt-git-index": locks.sha256_file(indexer, max_bytes=100_663_296),
            "zoekt-webserver": locks.sha256_file(webserver, max_bytes=100_663_296),
        }
        verified_after = verify_bundle(bundle_path, expected_sha256=bundle_sha256)
        if (
            source_after != source_before
            or binary_after != binary_before
            or verified_after.manifest_sha256 != verified_before.manifest_sha256
        ):
            raise HostedRunnerError(
                "POST_LAUNCH_IDENTITY_DRIFT", "source, binary, or bundle bytes moved"
            )
        cleanup = _cleanup_candidate_scratch(
            process_group=launch.process_group,
            shard_root=shard_root,
            log_root=log_root,
        )
        validate_cleanup(cleanup)
        artifacts = _result_artifact_census(outputs)
        evidence = {
            "forge": {
                "commit_sha": request.forge_sha,
                "tree_sha": request.forge_tree_sha,
                "workflow_sha256": request.workflow_sha256,
                "lock_sha256": request.lock_sha256,
            },
            "consumer": {
                **dataclasses.asdict(consumer),
                "carrier_ref": consumer_policy["carrier_ref"],
                "pull_request": consumer_policy["pull_request"],
                "merge_base": merge_base,
                "changed_paths": list(changed_paths),
                "source_digest_before": source_before,
                "source_digest_after": source_after,
            },
            "bundle": {
                "name": expected_name,
                "sha256_before": verified_before.sha256,
                "sha256_after": verified_after.sha256,
                "manifest_sha256_before": verified_before.manifest_sha256,
                "manifest_sha256_after": verified_after.manifest_sha256,
                "binary_digests_before": binary_before,
                "binary_digests_after": binary_after,
            },
            "network_seal": dataclasses.asdict(proof),
            "consumer_invocation": {
                "role": "Z0_DISPOSABLE_FALSIFIER",
                "module": FIXED_CONSUMER_MODULE,
                "argv_contract": [
                    "python3",
                    "-I",
                    "-c",
                    "FIXED_BOOTSTRAP",
                    "CONSUMER_ROOT",
                    "--manifest",
                    "HOST_MANIFEST",
                    "--path-policy",
                    "FIXED_Z0_PATH_POLICY",
                    "--indexer",
                    "BUNDLE_ZOEKT_GIT_INDEX",
                    "--indexer-sha256",
                    "PINNED_SHA256",
                    "--webserver",
                    "BUNDLE_ZOEKT_WEBSERVER",
                    "--webserver-sha256",
                    "PINNED_SHA256",
                    "--shard-root",
                    "BOUNDED_SCRATCH",
                    "--log-root",
                    "BOUNDED_SCRATCH",
                    "--result",
                    "RESULT_JSON",
                    "--report",
                    "RESULT_MARKDOWN",
                    "--startup-timeout-seconds",
                    "10",
                ],
                "environment_keys": sorted(environment),
                "sensitive_environment_inherited": False,
            },
            "launch": dataclasses.asdict(launch),
            "artifacts": artifacts,
            "cleanup": dataclasses.asdict(cleanup),
            "failures": [],
            "truncation": {
                "stdout": False,
                "stderr": False,
                "limit_bytes_each": int(lock.payload["limits"]["log_bytes_each"]),
            },
            "runner": _runner_confounds(),
        }
        receipt = write_semantic_receipt(
            receipt_path,
            request=request,
            status="COMPLETED",
            effect="APPLIED",
            evidence=evidence,
        )
        if launch.returncode != 0:
            raise HostedRunnerError(
                "CONSUMER_RETURNED_NONZERO", f"known return code {launch.returncode}"
            )
        return receipt
    except HostedRunnerError as error:
        if not Path(receipt_path).exists():
            if launched:
                status = "RECONCILIATION_REQUIRED"
                effect = "EFFECT_UNKNOWN"
            else:
                status = "REFUSED"
                effect = "NOT_APPLIED"
            failure_evidence: dict[str, object] = {
                "failure": {
                    "code": error.code,
                    "detail": _bounded_redacted(error.detail, 512),
                },
                "consumer_launch_state": (
                    "COMPLETED_PROCESS"
                    if launch is not None
                    else "ATTEMPTED_UNKNOWN" if launched else "NOT_LAUNCHED"
                ),
                "network_seal": (
                    dataclasses.asdict(proof) if proof is not None else None
                ),
                "runner": _runner_confounds(),
            }
            if launch is not None:
                failure_evidence["launch"] = dataclasses.asdict(launch)
                try:
                    failure_cleanup = _cleanup_candidate_scratch(
                        process_group=launch.process_group,
                        shard_root=shard_root,
                        log_root=log_root,
                    )
                    failure_evidence["cleanup"] = dataclasses.asdict(failure_cleanup)
                except HostedRunnerError as cleanup_error:
                    failure_evidence["cleanup"] = {
                        "state": "FAILED",
                        "code": cleanup_error.code,
                    }
            write_semantic_receipt(
                receipt_path,
                request=request,
                status=status,
                effect=effect,
                evidence=failure_evidence,
            )
        raise


def _download_exact_go_archive(destination: Path) -> str:
    target = Path(destination)
    parent = _real_directory(target.parent, "DOWNLOAD_DESTINATION_UNSAFE")
    if target.exists() or target.is_symlink():
        raise HostedRunnerError(
            "DOWNLOAD_DESTINATION_UNSAFE", "Go archive destination is occupied"
        )
    current_url = _validated_acquisition_url(locks.GO_ARCHIVE_URL)
    visited: set[str] = set()
    for _hop in range(5):
        if current_url in visited:
            raise HostedRunnerError(
                "ACQUISITION_REDIRECT_FORBIDDEN", "Go archive redirect cycle"
            )
        visited.add(current_url)
        completed = run_checked(
            [
                "/usr/bin/curl",
                "--fail",
                "--silent",
                "--show-error",
                "--max-redirs",
                "0",
                "--proto",
                "=https",
                "--tlsv1.2",
                "--connect-timeout",
                "30",
                "--max-time",
                "300",
                "--output",
                os.fspath(target),
                "--write-out",
                "%{http_code}\n%{url_effective}\n%{redirect_url}\n",
                current_url,
            ],
            cwd=parent,
            timeout=330,
        )
        fields = completed.stdout.splitlines()
        if len(fields) != 3 or re.fullmatch(r"[0-9]{3}", fields[0]) is None:
            raise HostedRunnerError(
                "ACQUISITION_RESPONSE_INVALID", "Go archive response is malformed"
            )
        status, effective_url, redirect_url = fields
        if effective_url != current_url:
            raise HostedRunnerError(
                "ACQUISITION_REDIRECT_FORBIDDEN", "curl changed the validated URL"
            )
        if status == "200":
            if redirect_url:
                raise HostedRunnerError(
                    "ACQUISITION_RESPONSE_INVALID", "successful response redirects"
                )
            break
        if status.startswith("3") and redirect_url:
            target.unlink(missing_ok=True)
            current_url = _validated_acquisition_url(urljoin(current_url, redirect_url))
            continue
        raise HostedRunnerError(
            "ACQUISITION_RESPONSE_INVALID", f"Go archive returned HTTP {status}"
        )
    else:
        raise HostedRunnerError(
            "ACQUISITION_REDIRECT_FORBIDDEN", "Go archive redirect ceiling exceeded"
        )
    if target.stat().st_size != locks.GO_ARCHIVE_SIZE:
        raise HostedRunnerError("ARCHIVE_SIZE_MISMATCH", locks.GO_ARCHIVE_FILENAME)
    if locks.sha256_file(target, max_bytes=134_217_728) != locks.GO_ARCHIVE_SHA256:
        raise HostedRunnerError("ARCHIVE_DIGEST_MISMATCH", locks.GO_ARCHIVE_FILENAME)
    return current_url


def _validated_acquisition_url(value: str) -> str:
    try:
        parsed = urlparse(value)
        port = parsed.port
    except ValueError as error:
        raise HostedRunnerError(
            "ACQUISITION_REDIRECT_FORBIDDEN", "Go archive URL is malformed"
        ) from error
    if (
        parsed.scheme != "https"
        or parsed.hostname not in locks.ALLOWED_HOSTS
        or parsed.username is not None
        or parsed.password is not None
        or port is not None
        or not parsed.path.startswith("/")
        or parsed.query
        or parsed.fragment
    ):
        raise HostedRunnerError(
            "ACQUISITION_REDIRECT_FORBIDDEN", "Go archive left the allowlist"
        )
    return value


def _verify_go_distribution(go_root: Path, go_binary: Path) -> None:
    root = _real_directory(go_root, "GO_ARCHIVE_INVALID")
    binary = _verified_executable(go_binary, expected_sha256=None)
    version = run_checked(
        [os.fspath(binary), "version"],
        cwd=root,
        env={
            "HOME": os.fspath(root),
            "LANG": "C",
            "LC_ALL": "C",
            "PATH": "/usr/bin:/bin",
            "GOTOOLCHAIN": "local",
        },
        timeout=30,
    ).stdout.strip()
    if version != f"go version go{locks.GO_VERSION} linux/amd64":
        raise HostedRunnerError("GO_VERSION_MISMATCH", version)
    version_file = root / "VERSION"
    if (
        version_file.read_text(encoding="utf-8").splitlines()[0]
        != f"go{locks.GO_VERSION}"
    ):
        raise HostedRunnerError("GO_VERSION_MISMATCH", "VERSION file differs")
    license_bytes = (root / "LICENSE").read_bytes()
    if (
        locks.git_blob_sha1(license_bytes) != locks.GO_LICENSE_BLOB
        or locks.sha256_bytes(license_bytes) != locks.GO_LICENSE_SHA256
    ):
        raise HostedRunnerError("GO_LICENSE_MISMATCH", "archive license differs")


def _verify_go_source_metadata() -> Mapping[str, str]:
    tag = _gh_json(f"repos/golang/go/git/ref/tags/{locks.GO_SOURCE_TAG}")
    tag_object = tag.get("object")
    if not isinstance(tag_object, Mapping):
        raise HostedRunnerError("GO_SOURCE_MISMATCH", "tag object absent")
    if (
        tag_object.get("type") != "commit"
        or tag_object.get("sha") != locks.GO_SOURCE_COMMIT
    ):
        raise HostedRunnerError("GO_SOURCE_MISMATCH", "tag commit differs")
    commit = _gh_json(f"repos/golang/go/git/commits/{locks.GO_SOURCE_COMMIT}")
    tree = commit.get("tree")
    if not isinstance(tree, Mapping) or tree.get("sha") != locks.GO_SOURCE_TREE:
        raise HostedRunnerError("GO_SOURCE_MISMATCH", "source tree differs")
    license_object = _gh_json(
        f"repos/golang/go/contents/LICENSE?ref={locks.GO_SOURCE_COMMIT}"
    )
    if license_object.get("sha") != locks.GO_LICENSE_BLOB:
        raise HostedRunnerError("GO_LICENSE_MISMATCH", "source license blob differs")
    return {
        "repository": locks.GO_SOURCE_REPOSITORY,
        "tag": locks.GO_SOURCE_TAG,
        "commit": locks.GO_SOURCE_COMMIT,
        "tree": locks.GO_SOURCE_TREE,
        "license_blob_sha1": locks.GO_LICENSE_BLOB,
    }


def _gh_json(endpoint: str) -> Mapping[str, Any]:
    completed = run_checked(
        ["/usr/bin/gh", "api", endpoint],
        cwd=Path.cwd(),
        timeout=60,
    )
    try:
        value = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise HostedRunnerError("UPSTREAM_METADATA_INVALID", endpoint) from error
    if not isinstance(value, Mapping):
        raise HostedRunnerError("UPSTREAM_METADATA_INVALID", endpoint)
    return value


def _gh_paginated_rows(
    endpoint: str,
    *,
    field: str,
    max_rows: int,
) -> list[Mapping[str, Any]]:
    """Read one complete bounded GitHub collection or fail closed on movement."""

    if (
        not endpoint
        or "page=" in endpoint
        or "per_page=" in endpoint
        or re.fullmatch(r"[a-z_]{1,64}", field) is None
        or max_rows <= 0
    ):
        raise HostedRunnerError(
            "REPLAY_LOOKUP_INVALID", "pagination request is invalid"
        )
    separator = "&" if "?" in endpoint else "?"
    expected_total: int | None = None
    page = 1
    rows: list[Mapping[str, Any]] = []
    seen_ids: set[int] = set()
    while expected_total is None or len(rows) < expected_total:
        response = _gh_json(f"{endpoint}{separator}per_page=100&page={page}")
        total = response.get("total_count")
        raw_rows = response.get(field)
        if (
            isinstance(total, bool)
            or not isinstance(total, int)
            or total < 0
            or not isinstance(raw_rows, list)
        ):
            raise HostedRunnerError(
                "REPLAY_LOOKUP_INVALID", "paginated response is malformed"
            )
        if total > max_rows:
            raise HostedRunnerError(
                "REPLAY_LOOKUP_INVALID", "paginated response exceeds safety ceiling"
            )
        if expected_total is None:
            expected_total = total
        elif total != expected_total:
            raise HostedRunnerError(
                "EFFECT_UNKNOWN_REPLAY_BLOCKED", "GitHub collection moved during census"
            )
        if not raw_rows and len(rows) < expected_total:
            raise HostedRunnerError(
                "REPLAY_LOOKUP_INVALID", "paginated response ended early"
            )
        for raw_row in raw_rows:
            if not isinstance(raw_row, Mapping):
                raise HostedRunnerError(
                    "REPLAY_LOOKUP_INVALID", "paginated row is malformed"
                )
            row_id = raw_row.get("id")
            if (
                isinstance(row_id, bool)
                or not isinstance(row_id, int)
                or row_id <= 0
                or row_id in seen_ids
            ):
                raise HostedRunnerError(
                    "EFFECT_UNKNOWN_REPLAY_BLOCKED", "GitHub collection is ambiguous"
                )
            seen_ids.add(row_id)
            rows.append(raw_row)
        if len(rows) > expected_total:
            raise HostedRunnerError(
                "EFFECT_UNKNOWN_REPLAY_BLOCKED", "GitHub collection grew during census"
            )
        page += 1
    return rows


def _checkout_exact_zoekt(destination: Path) -> None:
    if destination.exists() or destination.is_symlink():
        raise HostedRunnerError("SOURCE_CONFLICT", destination.name)
    destination.mkdir(parents=True, mode=0o700)
    run_checked(["/usr/bin/git", "init", "-q"], cwd=destination)
    run_checked(
        [
            "/usr/bin/git",
            "remote",
            "add",
            "origin",
            locks.ZOEKT_SOURCE_URL,
        ],
        cwd=destination,
    )
    run_checked(
        [
            "/usr/bin/git",
            "-c",
            "protocol.version=2",
            "fetch",
            "--no-tags",
            "--depth=1",
            "origin",
            locks.ZOEKT_COMMIT,
        ],
        cwd=destination,
        timeout=300,
    )
    run_checked(
        ["/usr/bin/git", "checkout", "--detach", "--quiet", locks.ZOEKT_COMMIT],
        cwd=destination,
        timeout=60,
    )


def _repeat_build_zoekt(
    source: Path,
    *,
    go_binary: Path,
    scratch: Path,
    payload_bin: Path,
) -> Mapping[str, Any]:
    go = _verified_executable(go_binary, expected_sha256=None)
    module_cache = scratch / "gomodcache"
    go_path = scratch / "gopath"
    home = scratch / "home"
    for directory in (module_cache, go_path, home):
        directory.mkdir(parents=True, mode=0o700)
    common_env = {
        "CGO_ENABLED": "0",
        "GOARCH": "amd64",
        "GONOSUMDB": "off",
        "GOOS": "linux",
        "GOPATH": os.fspath(go_path),
        "GOMODCACHE": os.fspath(module_cache),
        "GOPRIVATE": "",
        "GOPROXY": "https://proxy.golang.org",
        "GOSUMDB": "sum.golang.org",
        "GOTOOLCHAIN": "local",
        "HOME": os.fspath(home),
        "LANG": "C",
        "LC_ALL": "C",
        "PATH": f"{go.parent}:/usr/bin:/bin",
        "TZ": "UTC",
    }
    run_checked(
        [os.fspath(go), "mod", "download", "-json", "all"],
        cwd=source,
        env={**common_env, "GOCACHE": os.fspath(scratch / "download-cache")},
        timeout=600,
    )
    run_checked(
        [os.fspath(go), "mod", "verify"],
        cwd=source,
        env={**common_env, "GOCACHE": os.fspath(scratch / "verify-cache")},
        timeout=300,
    )
    inventory_output = run_checked(
        [os.fspath(go), "list", "-mod=readonly", "-m", "-json", "all"],
        cwd=source,
        env={**common_env, "GOCACHE": os.fspath(scratch / "list-cache")},
        timeout=300,
    ).stdout
    modules = _normalize_go_module_inventory(inventory_output)

    builds: list[dict[str, Mapping[str, object]]] = []
    packages = {
        "zoekt-git-index": "./cmd/zoekt-git-index",
        "zoekt-webserver": "./cmd/zoekt-webserver",
    }
    for attempt in (1, 2):
        output = scratch / f"build-{attempt}"
        cache = scratch / f"gocache-{attempt}"
        output.mkdir(mode=0o700)
        cache.mkdir(mode=0o700)
        rows: dict[str, Mapping[str, object]] = {}
        env = {**common_env, "GOCACHE": os.fspath(cache)}
        for name, package in packages.items():
            target = output / name
            run_checked(
                [
                    os.fspath(go),
                    "build",
                    "-mod=readonly",
                    "-trimpath",
                    "-buildvcs=false",
                    "-ldflags=-buildid=",
                    "-o",
                    os.fspath(target),
                    package,
                ],
                cwd=source,
                env=env,
                timeout=900,
            )
            executable = _verified_executable(target, expected_sha256=None)
            rows[name] = {
                "sha256": locks.sha256_file(executable, max_bytes=100_663_296),
                "size": executable.stat().st_size,
                "mode": "0755",
                "build_attempt": attempt,
            }
        builds.append(rows)
    first, second = builds
    for name in packages:
        if (
            first[name]["sha256"] != second[name]["sha256"]
            or first[name]["size"] != second[name]["size"]
        ):
            raise HostedRunnerError(
                "NONDETERMINISTIC_BUILD", f"{name} differs across clean caches"
            )
        source_binary = scratch / "build-1" / name
        target = payload_bin / name
        shutil.copyfile(source_binary, target)
        os.chmod(target, 0o755)
        if locks.sha256_file(target, max_bytes=100_663_296) != first[name]["sha256"]:
            raise HostedRunnerError("BINARY_COPY_MISMATCH", name)
    final_rows = {
        name: {
            "sha256": first[name]["sha256"],
            "size": first[name]["size"],
            "mode": "0755",
            "repeat_builds": 2,
            "byte_identical": True,
        }
        for name in packages
    }
    return {"modules": modules, "binaries": final_rows}


def _normalize_go_module_inventory(raw: str) -> list[Mapping[str, object]]:
    decoder = json.JSONDecoder()
    offset = 0
    modules: list[Mapping[str, object]] = []
    while True:
        while offset < len(raw) and raw[offset].isspace():
            offset += 1
        if offset == len(raw):
            break
        try:
            value, offset = decoder.raw_decode(raw, offset)
        except json.JSONDecodeError as error:
            raise HostedRunnerError(
                "DEPENDENCY_GRAPH_INVALID", "go list output is malformed"
            ) from error
        if not isinstance(value, Mapping):
            raise HostedRunnerError(
                "DEPENDENCY_GRAPH_INVALID", "module row is not an object"
            )
        path = value.get("Path")
        if not isinstance(path, str) or not path:
            raise HostedRunnerError("DEPENDENCY_GRAPH_INVALID", "module path is absent")
        row: dict[str, object] = {
            "path": path,
            "main": bool(value.get("Main", False)),
        }
        for source_key, target_key in (
            ("Version", "version"),
            ("Sum", "sum"),
            ("GoModSum", "go_mod_sum"),
        ):
            if source_key in value:
                field = value[source_key]
                if not isinstance(field, str) or not field:
                    raise HostedRunnerError(
                        "DEPENDENCY_GRAPH_INVALID", f"{source_key} is malformed"
                    )
                row[target_key] = field
        replace = value.get("Replace")
        if replace is not None:
            if not isinstance(replace, Mapping):
                raise HostedRunnerError(
                    "DEPENDENCY_GRAPH_INVALID", "replace row is malformed"
                )
            replacement_path = replace.get("Path")
            replacement_version = replace.get("Version")
            replacement_sum = replace.get("Sum")
            if (
                not isinstance(replacement_path, str)
                or not isinstance(replacement_version, str)
                or not isinstance(replacement_sum, str)
            ):
                raise HostedRunnerError(
                    "DEPENDENCY_GRAPH_INVALID",
                    "local or incompletely summed replacement is forbidden",
                )
            row["replace"] = {
                "path": replacement_path,
                "version": replacement_version,
                "sum": replacement_sum,
            }
        if not row["main"] and (
            "version" not in row or "sum" not in row or "go_mod_sum" not in row
        ):
            raise HostedRunnerError(
                "DEPENDENCY_GRAPH_INVALID", f"incomplete sums for {path}"
            )
        modules.append(row)
    if not modules or sum(bool(row["main"]) for row in modules) != 1:
        raise HostedRunnerError(
            "DEPENDENCY_GRAPH_INVALID", "main module census differs"
        )
    modules.sort(key=lambda row: (str(row["path"]), str(row.get("version", ""))))
    assert_secret_free(modules)
    return modules


def _verified_executable(path: Path, *, expected_sha256: str | None) -> Path:
    candidate = Path(path)
    try:
        metadata = candidate.lstat()
    except OSError as error:
        raise HostedRunnerError("EXECUTABLE_UNAVAILABLE", candidate.name) from error
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISREG(metadata.st_mode)
        or not metadata.st_mode & 0o111
        or metadata.st_mode & (stat.S_IWOTH | stat.S_ISUID | stat.S_ISGID)
    ):
        raise HostedRunnerError("EXECUTABLE_UNSAFE", candidate.name)
    if expected_sha256 is not None:
        if _SHA256_RE.fullmatch(expected_sha256) is None:
            raise HostedRunnerError("EXECUTABLE_DIGEST_MISMATCH", candidate.name)
        if locks.sha256_file(candidate, max_bytes=100_663_296) != expected_sha256:
            raise HostedRunnerError("EXECUTABLE_DIGEST_MISMATCH", candidate.name)
    return candidate.resolve()


def _runner_confounds() -> Mapping[str, object]:
    value = {
        "runner_os": os.environ.get("RUNNER_OS", platform.system()),
        "runner_arch": os.environ.get("RUNNER_ARCH", platform.machine()),
        "runner_image": os.environ.get("ImageOS", "UNAVAILABLE"),
        "runner_image_version": os.environ.get("ImageVersion", "UNAVAILABLE"),
        "kernel_release": platform.release(),
        "python": platform.python_version(),
        "production_inert": True,
    }
    assert_secret_free(value)
    return value


def _fresh_directory(path: Path, code: str) -> Path:
    candidate = Path(path)
    if candidate.exists() or candidate.is_symlink():
        raise HostedRunnerError(code, f"{candidate.name} already exists")
    candidate.mkdir(parents=True, mode=0o700)
    return _real_directory(candidate, code)


def _append_github_outputs(path: Path, values: Mapping[str, str]) -> None:
    output = Path(path)
    if output.exists() or output.is_symlink():
        try:
            metadata = output.lstat()
        except OSError as error:
            raise HostedRunnerError("OUTPUT_UNSAFE", output.name) from error
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
            raise HostedRunnerError("OUTPUT_UNSAFE", output.name)
    for key, value in values.items():
        if re.fullmatch(r"[a-z_]{1,64}", key) is None:
            raise HostedRunnerError("OUTPUT_UNSAFE", "invalid output key")
        if re.fullmatch(r"[A-Za-z0-9._+-]{1,256}", value) is None:
            raise HostedRunnerError("OUTPUT_UNSAFE", f"invalid output value for {key}")
    with output.open("a", encoding="utf-8", newline="\n") as stream:
        for key, value in values.items():
            stream.write(f"{key}={value}\n")


def _manifest_file_digest(manifest: Mapping[str, Any], relative: str) -> str:
    rows = manifest.get("files")
    if not isinstance(rows, list):
        raise HostedRunnerError("BUNDLE_MANIFEST_INVALID", "file rows absent")
    matching = [
        row for row in rows if isinstance(row, Mapping) and row.get("path") == relative
    ]
    if len(matching) != 1 or not isinstance(matching[0].get("sha256"), str):
        raise HostedRunnerError("BUNDLE_MANIFEST_INVALID", relative)
    digest = matching[0]["sha256"]
    if _SHA256_RE.fullmatch(digest) is None:
        raise HostedRunnerError("BUNDLE_MANIFEST_INVALID", relative)
    return digest


def _require_within_root(path: Path, root: Path) -> None:
    try:
        path.resolve().relative_to(root.resolve())
    except (OSError, ValueError) as error:
        raise HostedRunnerError(
            "CONSUMER_PATH_POLICY_UNSAFE", "path escaped consumer root"
        ) from error


def _regular_file(path: Path, code: str, *, max_bytes: int) -> Path:
    candidate = Path(path)
    try:
        metadata = candidate.lstat()
    except OSError as error:
        raise HostedRunnerError(code, candidate.name) from error
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_size > max_bytes
        or metadata.st_mode & stat.S_IWOTH
    ):
        raise HostedRunnerError(code, candidate.name)
    return candidate.resolve()


def _launch_fixed_consumer(
    argv: Sequence[str],
    *,
    cwd: Path,
    env: Mapping[str, str],
    timeout_seconds: int,
    log_limit: int,
) -> LaunchEvidence:
    started = time.monotonic()
    before = resource.getrusage(resource.RUSAGE_CHILDREN)

    def limits() -> None:
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        resource.setrlimit(resource.RLIMIT_CPU, (timeout_seconds, timeout_seconds + 1))
        resource.setrlimit(resource.RLIMIT_NOFILE, (256, 256))
        resource.setrlimit(resource.RLIMIT_NPROC, (256, 256))
        resource.setrlimit(resource.RLIMIT_FSIZE, (536_870_912, 536_870_912))

    try:
        process = subprocess.Popen(
            list(argv),
            cwd=os.fspath(cwd),
            env=dict(env),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
            preexec_fn=limits,
        )
    except OSError as error:
        raise HostedRunnerError(
            "CONSUMER_LAUNCH_FAILED", "fixed process unavailable"
        ) from error
    assert process.stdout is not None
    assert process.stderr is not None
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ, "stdout")
    selector.register(process.stderr, selectors.EVENT_READ, "stderr")
    streams = {"stdout": bytearray(), "stderr": bytearray()}
    timed_out = False
    overflow: str | None = None
    try:
        while selector.get_map():
            remaining = timeout_seconds - (time.monotonic() - started)
            if remaining <= 0:
                timed_out = True
                break
            events = selector.select(timeout=min(1.0, remaining))
            if not events and process.poll() is not None:
                # A final nonblocking pass delivers EOF for both pipes.
                events = selector.select(timeout=0)
                if not events:
                    break
            for key, _mask in events:
                chunk = os.read(key.fileobj.fileno(), 65_536)
                if not chunk:
                    selector.unregister(key.fileobj)
                    key.fileobj.close()
                    continue
                target = streams[str(key.data)]
                target.extend(chunk)
                if len(target) > log_limit:
                    overflow = str(key.data)
                    break
            if overflow:
                break
        if timed_out or overflow:
            _kill_process_group(process.pid)
        returncode = process.wait(timeout=15)
    except (OSError, subprocess.TimeoutExpired) as error:
        _kill_process_group(process.pid)
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            pass
        raise HostedRunnerError(
            "CONSUMER_EFFECT_UNKNOWN", "process result could not be reconciled"
        ) from error
    finally:
        selector.close()
        for stream in (process.stdout, process.stderr):
            try:
                stream.close()
            except OSError:
                pass
    if timed_out:
        raise HostedRunnerError("CONSUMER_TIMEOUT", str(timeout_seconds))
    if overflow:
        raise HostedRunnerError("LOG_LIMIT_EXCEEDED", overflow)
    after = resource.getrusage(resource.RUSAGE_CHILDREN)
    stdout = bytes(streams["stdout"])
    stderr = bytes(streams["stderr"])
    assert_secret_free(stdout)
    assert_secret_free(stderr)
    return LaunchEvidence(
        returncode=returncode,
        pid=process.pid,
        process_group=process.pid,
        stdout_sha256=hashlib.sha256(stdout).hexdigest(),
        stderr_sha256=hashlib.sha256(stderr).hexdigest(),
        stdout_bytes=len(stdout),
        stderr_bytes=len(stderr),
        user_seconds=max(0.0, after.ru_utime - before.ru_utime),
        system_seconds=max(0.0, after.ru_stime - before.ru_stime),
        max_rss_kib=max(0, int(after.ru_maxrss)),
    )


def _kill_process_group(process_group: int) -> None:
    try:
        os.killpg(process_group, signal.SIGKILL)
    except ProcessLookupError:
        return
    except OSError as error:
        raise HostedRunnerError(
            "CLEANUP_LEAK", "process group could not be killed"
        ) from error


def _process_group_dead(process_group: int) -> bool:
    try:
        os.killpg(process_group, 0)
    except ProcessLookupError:
        return True
    except PermissionError:
        return False
    return False


def _cleanup_candidate_scratch(
    *, process_group: int, shard_root: Path, log_root: Path
) -> CleanupEvidence:
    for path in (shard_root, log_root):
        try:
            metadata = path.lstat()
        except FileNotFoundError:
            continue
        except OSError as error:
            raise HostedRunnerError(
                "CLEANUP_LEAK", "candidate scratch could not be inspected"
            ) from error
        if stat.S_ISDIR(metadata.st_mode) and not stat.S_ISLNK(metadata.st_mode):
            try:
                shutil.rmtree(path)
            except OSError as error:
                raise HostedRunnerError(
                    "CLEANUP_LEAK", "candidate scratch could not be removed"
                ) from error
    residue = tuple(
        label
        for label, path in (("shards", shard_root), ("logs", log_root))
        if path.exists() or path.is_symlink()
    )
    return CleanupEvidence(
        process_group_dead=_process_group_dead(process_group),
        unexpected_residue=residue,
    )


def _result_artifact_census(output: Path) -> Mapping[str, object]:
    rows: dict[str, object] = {}
    for relative in ("z0-result.json", "z0-report.md"):
        path = output / relative
        if path.exists() or path.is_symlink():
            candidate = _regular_file(
                path, "RESULT_ARTIFACT_UNSAFE", max_bytes=1_048_576
            )
            body = candidate.read_bytes()
            assert_secret_free(body)
            rows[relative] = {
                "name": relative,
                "size": candidate.stat().st_size,
                "sha256": locks.sha256_bytes(body),
            }
        else:
            rows[relative] = {"name": relative, "state": "ABSENT"}
    assert_secret_free(rows)
    return rows


def _bundle_payload_census(root: Path) -> list[tuple[str, Path, int]]:
    rows: list[tuple[str, Path, int]] = []
    for path in sorted(
        root.rglob("*"), key=lambda value: value.relative_to(root).as_posix()
    ):
        relative = path.relative_to(root).as_posix()
        _safe_bundle_name(relative)
        metadata = path.lstat()
        if stat.S_ISLNK(metadata.st_mode):
            raise HostedRunnerError("BUNDLE_PAYLOAD_UNSAFE", f"symlink {relative}")
        if stat.S_ISDIR(metadata.st_mode):
            if metadata.st_mode & stat.S_IWOTH:
                raise HostedRunnerError(
                    "BUNDLE_PAYLOAD_UNSAFE", f"world-writable {relative}"
                )
            continue
        if not stat.S_ISREG(metadata.st_mode):
            raise HostedRunnerError("BUNDLE_PAYLOAD_UNSAFE", f"special file {relative}")
        if metadata.st_mode & (stat.S_IWOTH | stat.S_ISUID | stat.S_ISGID):
            raise HostedRunnerError("BUNDLE_PAYLOAD_UNSAFE", f"unsafe mode {relative}")
        mode = 0o755 if metadata.st_mode & 0o111 else 0o644
        if relative.startswith("bin/") and mode != 0o755:
            raise HostedRunnerError(
                "BUNDLE_PAYLOAD_UNSAFE", f"non-executable binary {relative}"
            )
        if not relative.startswith("bin/") and mode != 0o644:
            raise HostedRunnerError(
                "BUNDLE_PAYLOAD_UNSAFE", f"executable metadata {relative}"
            )
        if metadata.st_size > 100_663_296:
            raise HostedRunnerError(
                "BUNDLE_PAYLOAD_UNSAFE", f"oversized file {relative}"
            )
        body = path.read_bytes()
        assert_secret_free(body)
        rows.append((relative, path, mode))
    return rows


def _bundle_role(relative: str) -> str:
    roles = {
        "bin/zoekt-git-index": "Z0_INDEXER_EXECUTABLE",
        "bin/zoekt-webserver": "Z0_SEARCH_EXECUTABLE",
        "meta/NOTICE.txt": "RIGHTS_AND_NOTICES",
        "meta/provenance.json": "PHASE_P_PROVENANCE",
        "meta/sbom.json": "GO_MODULE_INVENTORY",
        "meta/toolchain-lock.json": "EXACT_TOOLCHAIN_LOCK",
    }
    try:
        return roles[relative]
    except KeyError as error:
        raise HostedRunnerError("BUNDLE_PAYLOAD_UNEXPECTED", relative) from error


def _safe_bundle_name(name: str) -> str:
    if not name or "\\" in name or "\x00" in name:
        raise HostedRunnerError("BUNDLE_PAYLOAD_UNSAFE", "invalid path")
    candidate = PurePosixPath(name)
    if candidate.is_absolute() or any(
        part in {"", ".", ".."} for part in candidate.parts
    ):
        raise HostedRunnerError("BUNDLE_PAYLOAD_UNSAFE", name)
    if any(_SAFE_BUNDLE_PART_RE.fullmatch(part) is None for part in candidate.parts):
        raise HostedRunnerError("BUNDLE_PAYLOAD_UNSAFE", name)
    return candidate.as_posix()


def _add_tar_directory(archive: tarfile.TarFile, relative: str) -> None:
    info = tarfile.TarInfo(relative)
    info.type = tarfile.DIRTYPE
    info.size = 0
    info.mode = 0o755
    _canonicalize_tar_info(info)
    archive.addfile(info)


def _add_tar_file(
    archive: tarfile.TarFile, relative: str, source: Path, mode: int
) -> None:
    info = tarfile.TarInfo(relative)
    info.type = tarfile.REGTYPE
    info.size = source.stat().st_size
    info.mode = mode
    _canonicalize_tar_info(info)
    with source.open("rb") as stream:
        archive.addfile(info, stream)


def _add_tar_bytes(
    archive: tarfile.TarFile, relative: str, body: bytes, mode: int
) -> None:
    info = tarfile.TarInfo(relative)
    info.type = tarfile.REGTYPE
    info.size = len(body)
    info.mode = mode
    _canonicalize_tar_info(info)
    archive.addfile(info, io.BytesIO(body))


def _canonicalize_tar_info(info: tarfile.TarInfo) -> None:
    info.uid = 0
    info.gid = 0
    info.uname = ""
    info.gname = ""
    info.mtime = 0
    info.pax_headers = {}


def _validate_bundle_members(members: Sequence[tarfile.TarInfo]) -> None:
    if not members:
        raise HostedRunnerError("BUNDLE_UNSAFE", "bundle is empty")
    seen: set[str] = set()
    total = 0
    for member in members:
        name = _safe_bundle_name(member.name)
        if name in seen:
            raise HostedRunnerError("BUNDLE_UNSAFE", f"duplicate {name}")
        seen.add(name)
        if not (member.isdir() or member.isreg()):
            raise HostedRunnerError("BUNDLE_UNSAFE", f"link/special {name}")
        if member.mode & (stat.S_IWOTH | stat.S_ISUID | stat.S_ISGID | stat.S_ISVTX):
            raise HostedRunnerError("BUNDLE_UNSAFE", f"unsafe mode {name}")
        if member.uid != 0 or member.gid != 0 or member.mtime != 0:
            raise HostedRunnerError("BUNDLE_NONDETERMINISTIC", name)
        if member.isreg():
            if member.size < 0 or member.size > 100_663_296:
                raise HostedRunnerError("BUNDLE_UNSAFE", f"oversized {name}")
            total += member.size
            if total > 536_870_912:
                raise HostedRunnerError(
                    "BUNDLE_UNSAFE", "expanded bundle exceeds ceiling"
                )
    if "manifest.json" not in seen:
        raise HostedRunnerError("BUNDLE_MANIFEST_INVALID", "manifest absent")


def _validate_bundle_manifest(value: object) -> None:
    if not isinstance(value, Mapping):
        raise HostedRunnerError("BUNDLE_MANIFEST_INVALID", "manifest must be an object")
    if set(value) != {"schema_version", "mode", "context", "files"}:
        raise HostedRunnerError("BUNDLE_MANIFEST_INVALID", "manifest fields differ")
    if (
        value.get("schema_version") != BUNDLE_MANIFEST_SCHEMA_VERSION
        or value.get("mode") != "Z0"
    ):
        raise HostedRunnerError("BUNDLE_MANIFEST_INVALID", "manifest identity differs")
    context = value.get("context")
    rows = value.get("files")
    if not isinstance(context, Mapping) or not isinstance(rows, list):
        raise HostedRunnerError(
            "BUNDLE_MANIFEST_INVALID", "manifest content is malformed"
        )
    expected_fields = {"path", "role", "mode", "size", "sha256"}
    paths: set[str] = set()
    for row in rows:
        if not isinstance(row, Mapping) or set(row) != expected_fields:
            raise HostedRunnerError("BUNDLE_MANIFEST_INVALID", "file row fields differ")
        path = row.get("path")
        if (
            not isinstance(path, str)
            or _safe_bundle_name(path) != path
            or path in paths
        ):
            raise HostedRunnerError("BUNDLE_MANIFEST_INVALID", "file path is invalid")
        paths.add(path)
        if row.get("role") != _bundle_role(path):
            raise HostedRunnerError(
                "BUNDLE_MANIFEST_INVALID", f"role differs for {path}"
            )
        expected_mode = "0755" if path.startswith("bin/") else "0644"
        if row.get("mode") != expected_mode:
            raise HostedRunnerError(
                "BUNDLE_MANIFEST_INVALID", f"mode differs for {path}"
            )
        if not isinstance(row.get("size"), int) or not 0 <= row["size"] <= 100_663_296:
            raise HostedRunnerError(
                "BUNDLE_MANIFEST_INVALID", f"size differs for {path}"
            )
        if (
            not isinstance(row.get("sha256"), str)
            or _SHA256_RE.fullmatch(row["sha256"]) is None
        ):
            raise HostedRunnerError(
                "BUNDLE_MANIFEST_INVALID", f"digest differs for {path}"
            )
    if paths != _REQUIRED_BUNDLE_FILES:
        raise HostedRunnerError("BUNDLE_MANIFEST_INVALID", "payload roles differ")
    assert_secret_free(value)


def _ensure_output_directory(path: Path) -> Path:
    output = Path(path)
    if output.exists() or output.is_symlink():
        return _real_directory(output, "OUTPUT_UNSAFE")
    output.mkdir(parents=True, mode=0o700)
    return _real_directory(output, "OUTPUT_UNSAFE")


def _real_directory(path: Path, code: str) -> Path:
    candidate = Path(path)
    try:
        metadata = candidate.lstat()
    except OSError as error:
        raise HostedRunnerError(code, f"{candidate.name} is unavailable") from error
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        raise HostedRunnerError(code, f"{candidate.name} is not a real directory")
    return candidate.resolve()


def _normalize_github_remote(remote: str) -> str | None:
    candidate = remote.strip()
    if candidate.startswith("git@github.com:"):
        path = candidate.removeprefix("git@github.com:")
    else:
        parsed = urlparse(candidate)
        if parsed.scheme not in {"https", "ssh"} or parsed.hostname != "github.com":
            return None
        if parsed.scheme == "ssh" and parsed.username != "git":
            return None
        if parsed.username is not None and parsed.scheme == "https":
            return None
        path = parsed.path.lstrip("/")
    if path.endswith(".git"):
        path = path[:-4]
    return path if path == FIXED_REPOSITORY else None


def _git_bytes(root: Path, *arguments: str) -> bytes:
    try:
        completed = subprocess.run(
            ["/usr/bin/git", "-C", os.fspath(root), *arguments],
            check=False,
            capture_output=True,
            timeout=30,
            env={
                "PATH": "/usr/bin:/bin:/usr/local/bin",
                "LANG": "C",
                "LC_ALL": "C",
            },
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise HostedRunnerError(
            "GIT_INSPECTION_FAILED", "Git invocation failed"
        ) from error
    if completed.returncode != 0:
        raise HostedRunnerError("GIT_INSPECTION_FAILED", "Git rejected identity census")
    return completed.stdout


def _atomic_write_new_or_identical(path: Path, body: bytes, *, mode: int) -> None:
    parent = _ensure_output_directory(path.parent)
    target = parent / path.name
    if target.exists() or target.is_symlink():
        if target.is_symlink() or not target.is_file():
            raise HostedRunnerError("RECEIPT_CONFLICT", target.name)
        if target.read_bytes() == body:
            return
        raise HostedRunnerError("RECEIPT_CONFLICT", "existing receipt bytes differ")
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=parent)
    temporary = Path(temporary_name)
    descriptor_open = True
    try:
        os.fchmod(descriptor, mode)
        with os.fdopen(descriptor, "wb") as output:
            descriptor_open = False
            output.write(body)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, target)
    finally:
        if descriptor_open:
            try:
                os.close(descriptor)
            except OSError:
                pass
        temporary.unlink(missing_ok=True)


def _bounded_redacted(value: str, limit: int) -> str:
    text = value[:limit]
    for pattern in _SECRET_TEXT_PATTERNS:
        text = pattern.sub("<redacted>", text)
    for pattern in _PRIVATE_PATH_PATTERNS:
        text = pattern.sub(" <private-path>", text)
    return text.replace("\x00", "?")


def _validate_receipt_state(status: object, effect: object) -> None:
    if (status, effect) not in _RECEIPT_STATE_PAIRS:
        raise HostedRunnerError(
            "RECEIPT_INVALID", "status and effect are not one exact semantic state"
        )


def _require_linux_amd64() -> None:
    machine = platform.machine().lower()
    if sys.platform != "linux" or machine not in {"x86_64", "amd64"}:
        raise HostedRunnerError(
            "UNSUPPORTED_PLATFORM", f"{sys.platform}/{machine or 'unknown'}"
        )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    derive = commands.add_parser("derive-request")
    derive.add_argument("--forge-root", type=Path, required=True)
    derive.add_argument("--operation-key", required=True)
    derive.add_argument("--consumer-sha", required=True)
    derive.add_argument("--consumer-tree-sha", required=True)
    derive.add_argument("--output", type=Path, required=True)
    derive.add_argument("--github-output", type=Path)

    reconcile = commands.add_parser("reconcile-prior-runs")
    reconcile.add_argument("--request", type=Path, required=True)
    reconcile.add_argument("--current-run-id", type=int, required=True)
    reconcile.add_argument("--destination", type=Path, required=True)
    reconcile.add_argument("--github-output", type=Path, required=True)

    phase_p = commands.add_parser("phase-p")
    phase_p.add_argument("--forge-root", type=Path, required=True)
    phase_p.add_argument("--request", type=Path, required=True)
    phase_p.add_argument("--scratch", type=Path, required=True)
    phase_p.add_argument("--output", type=Path, required=True)
    phase_p.add_argument("--github-output", type=Path, required=True)
    phase_p.add_argument("--receipt", type=Path, required=True)

    verify = commands.add_parser("verify-bundle")
    verify.add_argument("--bundle", type=Path, required=True)
    verify.add_argument("--sha256", required=True)

    phase_e = commands.add_parser("run-phase-e")
    phase_e.add_argument("--forge-root", type=Path, required=True)
    phase_e.add_argument("--consumer-root", type=Path, required=True)
    phase_e.add_argument("--request", type=Path, required=True)
    phase_e.add_argument("--bundle", type=Path, required=True)
    phase_e.add_argument("--bundle-sha256", required=True)
    phase_e.add_argument("--scratch", type=Path, required=True)
    phase_e.add_argument("--result-directory", type=Path, required=True)
    phase_e.add_argument("--receipt", type=Path, required=True)

    seal_refusal = commands.add_parser("record-network-seal-refusal")
    seal_refusal.add_argument("--request", type=Path, required=True)
    seal_refusal.add_argument("--receipt", type=Path, required=True)

    seal_unknown = commands.add_parser("record-network-seal-effect-unknown")
    seal_unknown.add_argument("--request", type=Path, required=True)
    seal_unknown.add_argument("--receipt", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        if arguments.command == "derive-request":
            request = derive_request(
                arguments.forge_root,
                operation_key=arguments.operation_key,
                consumer_sha=arguments.consumer_sha,
                consumer_tree_sha=arguments.consumer_tree_sha,
            )
            _atomic_write_new_or_identical(
                arguments.output, request.canonical_bytes + b"\n", mode=0o600
            )
            if arguments.github_output is not None:
                _append_github_outputs(
                    arguments.github_output,
                    {
                        "request_digest": request.digest,
                        "run_name": workflow_run_name(request),
                    },
                )
        elif arguments.command == "reconcile-prior-runs":
            request = load_request(arguments.request)
            reconcile_prior_runs(
                request,
                current_run_id=arguments.current_run_id,
                destination=arguments.destination,
                github_output=arguments.github_output,
            )
        elif arguments.command == "phase-p":
            _require_linux_amd64()
            prepare_phase_p_or_record_refusal(
                arguments.forge_root,
                load_request(arguments.request),
                scratch_root=arguments.scratch,
                output_directory=arguments.output,
                github_output=arguments.github_output,
                receipt_path=arguments.receipt,
            )
        elif arguments.command == "verify-bundle":
            _require_linux_amd64()
            verified = verify_bundle(arguments.bundle, expected_sha256=arguments.sha256)
            print(
                json.dumps(
                    {
                        "bundle_sha256": verified.sha256,
                        "manifest_sha256": verified.manifest_sha256,
                        "size": verified.size,
                    },
                    sort_keys=True,
                )
            )
        elif arguments.command == "run-phase-e":
            _require_linux_amd64()
            run_phase_e(
                arguments.forge_root,
                arguments.consumer_root,
                load_request(arguments.request),
                bundle_path=arguments.bundle,
                bundle_sha256=arguments.bundle_sha256,
                scratch_root=arguments.scratch,
                result_directory=arguments.result_directory,
                receipt_path=arguments.receipt,
            )
        elif arguments.command == "record-network-seal-refusal":
            write_network_seal_boundary_receipt(
                load_request(arguments.request),
                arguments.receipt,
                effect_unknown=False,
            )
        elif arguments.command == "record-network-seal-effect-unknown":
            write_network_seal_boundary_receipt(
                load_request(arguments.request),
                arguments.receipt,
                effect_unknown=True,
            )
        else:  # pragma: no cover - argparse is exhaustive
            raise HostedRunnerError("INVALID_COMMAND", str(arguments.command))
    except (HostedRunnerError, locks.ToolchainLockError) as error:
        print(
            f"{getattr(error, 'code', 'RUNNER_FAILED')}: "
            f"{_bounded_redacted(getattr(error, 'detail', str(error)), 1024)}",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
