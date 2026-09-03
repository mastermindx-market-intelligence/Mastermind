"""Closed validation for the exact Z0 Go/Zoekt experiment toolchain.

The committed JSON is data for auditability; this module independently pins
the security-relevant values so editing the data file cannot silently widen
the forge.  The only network-capable caller is Phase P in the manual workflow.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import subprocess
import tarfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Any, Final
from urllib.parse import urlparse

LOCK_SCHEMA_VERSION: Final = "mastermind.codeintel_experiment_toolchain_lock.v1"
SCHEMA_FILENAME: Final = "codeintel-experiment-toolchain-lock.schema.json"
SUPPORTED_MODE: Final = "Z0"
SUPPORTED_PLATFORM: Final = "linux-x86_64"
STRICT_JSON_MAX_BYTES: Final = 1_048_576

ZOEKT_REPOSITORY: Final = "sourcegraph/zoekt"
ZOEKT_SOURCE_URL: Final = "https://github.com/sourcegraph/zoekt.git"
ZOEKT_COMMIT: Final = "5f833dde1bc4b1a8f99007617b4b721e44506c4f"
ZOEKT_TREE: Final = "8135ec1d7329e7f8de43714ac5c7a2bad14bd7b5"
ZOEKT_GO_MOD_BLOB: Final = "db33117af57ea746dff8064e70ce56e3721e44ba"
ZOEKT_GO_MOD_SHA256: Final = (
    "c125539d727350ae76fcc7b37da0c4a091eeb50f1e623ed4aa2455a8ef2fc607"
)
ZOEKT_GO_SUM_BLOB: Final = "6f54532eef8a9628275d1aa870c1b26f89987dd0"
ZOEKT_GO_SUM_SHA256: Final = (
    "a1a6672855e89ef9a30780de23de96d81e5e7ee23ed87eef2d190cd31cb4b2b0"
)
ZOEKT_LICENSE_BLOB: Final = "261eeb9e9f8b2b4b0d119366dda99c6fd7d35c64"
ZOEKT_LICENSE_SHA256: Final = (
    "c71d239df91726fc519c6eb72d318ec65820627232b2f796219e87dcf35d0ab4"
)

GO_VERSION: Final = "1.26.5"
GO_ARCHIVE_FILENAME: Final = "go1.26.5.linux-amd64.tar.gz"
GO_ARCHIVE_URL: Final = f"https://go.dev/dl/{GO_ARCHIVE_FILENAME}"
GO_ARCHIVE_SHA256: Final = (
    "5c2c3b16caefa1d968a94c1daca04a7ca301a496d9b086e17ad77bb81393f053"
)
GO_ARCHIVE_SIZE: Final = 66_879_095
GO_SOURCE_REPOSITORY: Final = "golang/go"
GO_SOURCE_TAG: Final = "go1.26.5"
GO_SOURCE_COMMIT: Final = "c19862e5f8415b4f24b189d065ed739517c548ba"
GO_SOURCE_TREE: Final = "0bb2fb1cc06c334c36a2a92d2f0b07fea7236d74"
GO_LICENSE_BLOB: Final = "2a7cf70da6e498df9c11ab6a5eaa2ddd7af34da4"
GO_LICENSE_SHA256: Final = (
    "911f8f5782931320f5b8d1160a76365b83aea6447ee6c04fa6d5591467db9dad"
)

BUILD_RECIPE_SHA256: Final = (
    "fa55671482185857a29795df77b0bd5a15898bbd5dac7e993172273f1cf51335"
)
Z0_OPERATION_KEY: Final = "mastermind-codeintel-z0-discovery-falsifier-20260830-sol-001"

ACTION_COMMITS: Final = MappingProxyType(
    {
        "checkout": ("actions/checkout", "11bd71901bbe5b1630ceea73d27597364c9af683"),
        "download_artifact": (
            "actions/download-artifact",
            "d3f86a106a0bac45b974a628896c90dbdf5c8093",
        ),
        "upload_artifact": (
            "actions/upload-artifact",
            "ea165f8d65b6e75b540449e92b4886f43607fa02",
        ),
    }
)
ALLOWED_HOSTS: Final = (
    "api.github.com",
    "dl.google.com",
    "github.com",
    "go.dev",
    "proxy.golang.org",
    "storage.googleapis.com",
    "sum.golang.org",
)
HOST_UTILITY_CONFOUNDS: Final = (
    "/bin/bash",
    "/usr/bin/curl",
    "/usr/bin/env",
    "/usr/bin/git",
    "/usr/bin/gh",
    "/usr/bin/python3",
    "/usr/bin/tar",
    "/usr/bin/unshare",
    "/usr/sbin/ip",
)

_SHA1_RE: Final = re.compile(r"[0-9a-f]{40}\Z")
_SHA256_RE: Final = re.compile(r"[0-9a-f]{64}\Z")
_TOP_LEVEL_FIELDS: Final = frozenset(
    {
        "$schema",
        "schema_version",
        "mode",
        "platform",
        "acquisition",
        "zoekt",
        "go",
        "build",
        "universal_ctags",
        "consumer",
        "actions",
        "host_utility_confounds",
        "receipt",
        "limits",
    }
)


class ToolchainLockError(ValueError):
    """The toolchain lock or an acquired object violates the closed contract."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


class _StrictJsonViolation(ValueError):
    """A syntax extension that Python's default JSON decoder would accept."""


@dataclass(frozen=True)
class ToolchainLock:
    """One validated immutable Z0 lock."""

    payload: Mapping[str, Any]
    sha256: str
    build_recipe_sha256: str
    schema_version: str = LOCK_SCHEMA_VERSION
    mode: str = SUPPORTED_MODE


@dataclass(frozen=True)
class ArchiveMember:
    """A validated regular file or directory in a bounded archive."""

    name: str
    kind: str
    size: int
    mode: int


@dataclass(frozen=True)
class VerifiedZoektSource:
    """Observed immutable identities from an exact clean source checkout."""

    commit: str
    tree: str
    go_mod_blob: str
    go_sum_blob: str
    license_blob: str


def canonical_json_bytes(value: object) -> bytes:
    """Return the single JSON wire representation used for all identities."""

    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
            default=_canonical_json_default,
        ).encode("ascii")
    except (TypeError, ValueError, UnicodeEncodeError) as error:
        raise ToolchainLockError(
            "INVALID_JSON", "value is not canonical JSON"
        ) from error


def _canonical_json_default(value: object) -> object:
    """Expose immutable mappings to the JSON encoder without thawing the lock."""

    if isinstance(value, Mapping):
        return dict(value)
    raise TypeError(f"unsupported canonical JSON value: {type(value).__name__}")


def _strict_json_file(
    path: Path, *, invalid_code: str, unsafe_code: str
) -> tuple[object, bytes]:
    """Read one bounded regular file and reject non-standard JSON semantics."""

    candidate = Path(path)
    _regular_file_metadata(candidate, unsafe_code)
    descriptor = -1
    try:
        descriptor = os.open(
            candidate,
            os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0),
        )
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise ToolchainLockError(
                unsafe_code, f"{candidate.name} must be a regular file"
            )
        if metadata.st_size > STRICT_JSON_MAX_BYTES:
            raise ToolchainLockError(
                invalid_code,
                f"{candidate.name} exceeds the {STRICT_JSON_MAX_BYTES}-byte size ceiling",
            )
        with os.fdopen(descriptor, "rb") as source:
            descriptor = -1
            raw = source.read(STRICT_JSON_MAX_BYTES + 1)
    except ToolchainLockError:
        raise
    except OSError as error:
        raise ToolchainLockError(
            invalid_code, f"{candidate.name} is unreadable"
        ) from error
    finally:
        if descriptor >= 0:
            os.close(descriptor)

    if len(raw) > STRICT_JSON_MAX_BYTES:
        raise ToolchainLockError(
            invalid_code,
            f"{candidate.name} exceeds the {STRICT_JSON_MAX_BYTES}-byte size ceiling",
        )
    if len(raw) != metadata.st_size:
        raise ToolchainLockError(
            invalid_code, f"{candidate.name} changed while it was read"
        )

    try:
        text = raw.decode("utf-8", errors="strict")
        value = json.loads(
            text,
            object_pairs_hook=_strict_object_pairs,
            parse_constant=_reject_nonfinite_json_number,
        )
    except _StrictJsonViolation as error:
        raise ToolchainLockError(invalid_code, str(error)) from error
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ToolchainLockError(
            invalid_code, f"{candidate.name} must be UTF-8 JSON"
        ) from error
    return value, raw


def _strict_object_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise _StrictJsonViolation(f"duplicate object key: {key!r}")
        result[key] = value
    return result


def _reject_nonfinite_json_number(token: str) -> object:
    raise _StrictJsonViolation(f"non-finite number: {token}")


def _freeze_json(value: object) -> object:
    """Return a detached, recursively immutable representation of JSON data."""

    if isinstance(value, Mapping):
        return MappingProxyType(
            {key: _freeze_json(member) for key, member in value.items()}
        )
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_json(member) for member in value)
    return value


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path, *, max_bytes: int | None = None) -> str:
    """Hash a non-symlink regular file while enforcing an optional size ceiling."""

    candidate = Path(path)
    metadata = _regular_file_metadata(candidate, "FILE_UNSAFE")
    if max_bytes is not None and metadata.st_size > max_bytes:
        raise ToolchainLockError(
            "FILE_TOO_LARGE", f"{candidate.name} exceeds {max_bytes} bytes"
        )
    digest = hashlib.sha256()
    try:
        with candidate.open("rb") as source:
            while block := source.read(1024 * 1024):
                digest.update(block)
    except OSError as error:
        raise ToolchainLockError("FILE_UNREADABLE", candidate.name) from error
    return digest.hexdigest()


def git_blob_sha1(body: bytes) -> str:
    """Compute the Git SHA-1 object identity for raw blob bytes."""

    header = f"blob {len(body)}\0".encode("ascii")
    return hashlib.sha1(header + body).hexdigest()  # noqa: S324 - Git object identity


def load_toolchain_lock(
    path: Path, *, schema_path: Path | None = None
) -> ToolchainLock:
    """Load and independently validate the committed closed lock and schema."""

    lock_path = Path(path)
    payload, raw = _strict_json_file(
        lock_path, invalid_code="LOCK_INVALID", unsafe_code="LOCK_UNSAFE"
    )
    lock = validate_lock_payload(payload, raw_bytes=raw)
    if schema_path is not None:
        _validate_schema_file(Path(schema_path))
    return lock


def validate_lock_payload(
    payload: object, *, raw_bytes: bytes | None = None
) -> ToolchainLock:
    """Reject every value not belonging to the one reviewed Z0 lock."""

    if not isinstance(payload, Mapping):
        raise ToolchainLockError("LOCK_INVALID", "lock must be an object")
    supplied = set(payload)
    if supplied != _TOP_LEVEL_FIELDS:
        raise ToolchainLockError(
            "LOCK_SHAPE_MISMATCH",
            f"top-level fields differ: missing={sorted(_TOP_LEVEL_FIELDS - supplied)} "
            f"unknown={sorted(supplied - _TOP_LEVEL_FIELDS)}",
        )

    _pin(payload, ("$schema",), SCHEMA_FILENAME)
    _pin(payload, ("schema_version",), LOCK_SCHEMA_VERSION)
    _pin(payload, ("mode",), SUPPORTED_MODE)

    _require_exact_mapping(
        payload,
        ("platform",),
        {
            "id": SUPPORTED_PLATFORM,
            "os": "linux",
            "arch": "amd64",
            "runner_label": "ubuntu-24.04",
        },
    )
    _require_exact_mapping(
        payload,
        ("acquisition",),
        {
            "network_enabled_phase": "P",
            "network_sealed_phase": "E",
            "allowed_hosts": list(ALLOWED_HOSTS),
            "fresh_empty_caches": True,
            "floating_resolution": False,
            "github_cache": False,
        },
    )

    expected_zoekt = {
        "repository": ZOEKT_REPOSITORY,
        "source_url": ZOEKT_SOURCE_URL,
        "commit": ZOEKT_COMMIT,
        "tree": ZOEKT_TREE,
        "go_mod": {
            "path": "go.mod",
            "git_blob_sha1": ZOEKT_GO_MOD_BLOB,
            "sha256": ZOEKT_GO_MOD_SHA256,
            "size": 7104,
            "go_directive": "1.25.9",
            "toolchain_directive": "go1.26.5",
        },
        "go_sum": {
            "path": "go.sum",
            "git_blob_sha1": ZOEKT_GO_SUM_BLOB,
            "sha256": ZOEKT_GO_SUM_SHA256,
            "size": 51863,
        },
        "license": {
            "path": "LICENSE",
            "spdx": "Apache-2.0",
            "git_blob_sha1": ZOEKT_LICENSE_BLOB,
            "sha256": ZOEKT_LICENSE_SHA256,
            "size": 11357,
        },
        "binaries": {
            "zoekt-git-index": "./cmd/zoekt-git-index",
            "zoekt-webserver": "./cmd/zoekt-webserver",
        },
    }
    _require_exact_mapping(payload, ("zoekt",), expected_zoekt)

    expected_go = {
        "version": GO_VERSION,
        "archive": {
            "filename": GO_ARCHIVE_FILENAME,
            "url": GO_ARCHIVE_URL,
            "sha256": GO_ARCHIVE_SHA256,
            "size": GO_ARCHIVE_SIZE,
            "kind": "archive",
            "os": "linux",
            "arch": "amd64",
        },
        "source": {
            "repository": GO_SOURCE_REPOSITORY,
            "tag": GO_SOURCE_TAG,
            "commit": GO_SOURCE_COMMIT,
            "tree": GO_SOURCE_TREE,
            "license_blob_sha1": GO_LICENSE_BLOB,
            "license_sha256": GO_LICENSE_SHA256,
            "license_spdx": "BSD-3-Clause",
        },
    }
    _require_exact_mapping(payload, ("go",), expected_go)

    expected_recipe = {
        "environment": {
            "CGO_ENABLED": "0",
            "GOARCH": "amd64",
            "GONOSUMDB": "off",
            "GOOS": "linux",
            "GOPRIVATE": "",
            "GOPROXY": "https://proxy.golang.org",
            "GOSUMDB": "sum.golang.org",
            "GOTOOLCHAIN": "local",
        },
        "go_build_flags": ["-trimpath", "-buildvcs=false", "-ldflags=-buildid="],
        "packages": {
            "zoekt-git-index": "./cmd/zoekt-git-index",
            "zoekt-webserver": "./cmd/zoekt-webserver",
        },
        "repeat_builds": 2,
    }
    build = _mapping_at(payload, ("build",))
    if set(build) != {"recipe", "recipe_sha256"}:
        raise ToolchainLockError("LOCK_SHAPE_MISMATCH", "build fields differ")
    if build.get("recipe") != expected_recipe:
        raise ToolchainLockError("PIN_MISMATCH", "build.recipe differs")
    recipe_digest = sha256_bytes(canonical_json_bytes(build["recipe"]))
    if recipe_digest != BUILD_RECIPE_SHA256:
        raise ToolchainLockError("PIN_MISMATCH", "computed build recipe differs")
    _pin(payload, ("build", "recipe_sha256"), BUILD_RECIPE_SHA256)

    _require_exact_mapping(
        payload,
        ("universal_ctags",),
        {
            "enabled": False,
            "reason": "disabled_until_separately_content_addressed_and_admitted",
        },
    )
    _require_exact_mapping(
        payload,
        ("consumer",),
        {
            "repository": "mastermindx-market-intelligence/Mastermind",
            "pull_request": 407,
            "carrier_ref": "refs/pull/407/head",
            "operation_key": Z0_OPERATION_KEY,
            "module": "experiments.code_discovery.z0_runner",
            "local_branch": "codeintel-z0-consumer",
            "path_policy": "research/code_intelligence_fabric/z0-path-policy.json",
            "index_includes": ["experiments/code_discovery/*"],
            "index_excludes": [],
            "path_ceiling": [
                "experiments/code_discovery/",
                "tests/code_discovery/",
                "tests/fixtures/code_discovery/",
                "research/code_intelligence_fabric/Z0_GLOBAL_DISCOVERY_FALSIFIER_RESULT.md",
                "research/code_intelligence_fabric/z0-path-policy.json",
                "research/code_intelligence_fabric/z0-result.schema.json",
            ],
        },
    )
    expected_actions = {
        name: {"repository": repository, "commit": commit}
        for name, (repository, commit) in ACTION_COMMITS.items()
    }
    _require_exact_mapping(payload, ("actions",), expected_actions)
    _pin(payload, ("host_utility_confounds",), list(HOST_UTILITY_CONFOUNDS))
    _require_exact_mapping(
        payload,
        ("receipt",),
        {
            "schema_version": "mastermind.codeintel_experiment_bundle.v1",
            "effects": ["NOT_APPLIED", "APPLIED", "EFFECT_UNKNOWN"],
            "secret_free": True,
            "absolute_private_paths": False,
        },
    )
    _require_exact_mapping(
        payload,
        ("limits",),
        {
            "archive_bytes": 134217728,
            "archive_member_bytes": 100663296,
            "archive_total_bytes": 536870912,
            "bundle_bytes": 268435456,
            "log_bytes_each": 1048576,
            "receipt_bytes": 1048576,
            "consumer_seconds": 900,
        },
    )

    _validate_urls(payload)
    encoded = raw_bytes if raw_bytes is not None else canonical_json_bytes(payload)
    material = _freeze_json(payload)
    if not isinstance(material, Mapping):  # pragma: no cover - guarded above
        raise ToolchainLockError("LOCK_INVALID", "lock must be an object")
    return ToolchainLock(
        payload=material,
        sha256=sha256_bytes(encoded),
        build_recipe_sha256=recipe_digest,
    )


def verify_zoekt_source(source_root: Path, lock: ToolchainLock) -> VerifiedZoektSource:
    """Verify the acquired checkout without trusting tags, paths, or ambient Git state."""

    root = Path(source_root)
    try:
        metadata = root.lstat()
    except OSError as error:
        raise ToolchainLockError(
            "SOURCE_UNAVAILABLE", "Zoekt checkout is absent"
        ) from error
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        raise ToolchainLockError(
            "SOURCE_UNSAFE", "Zoekt checkout must be a real directory"
        )
    if _git(root, "status", "--porcelain=v1", "--untracked-files=all"):
        raise ToolchainLockError("SOURCE_DIRTY", "Zoekt checkout is not clean")
    remote = _git(root, "remote", "get-url", "origin")
    if remote.rstrip("/") != ZOEKT_SOURCE_URL:
        raise ToolchainLockError(
            "SOURCE_REPOSITORY_MISMATCH", "Zoekt origin is not fixed"
        )
    observed_commit = _git(root, "rev-parse", "HEAD")
    observed_tree = _git(root, "rev-parse", "HEAD^{tree}")
    if observed_commit != ZOEKT_COMMIT or observed_tree != ZOEKT_TREE:
        raise ToolchainLockError(
            "SOURCE_IDENTITY_MISMATCH", "Zoekt commit/tree differs"
        )

    expected_blobs = {
        "go.mod": ZOEKT_GO_MOD_BLOB,
        "go.sum": ZOEKT_GO_SUM_BLOB,
        "LICENSE": ZOEKT_LICENSE_BLOB,
    }
    observed_blobs: dict[str, str] = {}
    for line in _git(root, "ls-tree", "HEAD", "--", *expected_blobs).splitlines():
        try:
            header, name = line.split("\t", 1)
            mode, kind, object_id = header.split(" ")
        except ValueError as error:
            raise ToolchainLockError(
                "SOURCE_CENSUS_INVALID", "malformed Git tree row"
            ) from error
        if mode != "100644" or kind != "blob":
            raise ToolchainLockError("SOURCE_FILE_UNSAFE", name)
        observed_blobs[name] = object_id
    if observed_blobs != expected_blobs:
        raise ToolchainLockError(
            "SOURCE_BLOB_MISMATCH", "Zoekt module/license blob differs"
        )

    for path, expected_sha, expected_size in (
        ("go.mod", ZOEKT_GO_MOD_SHA256, 7104),
        ("go.sum", ZOEKT_GO_SUM_SHA256, 51863),
        ("LICENSE", ZOEKT_LICENSE_SHA256, 11357),
    ):
        body = (root / path).read_bytes()
        if len(body) != expected_size or sha256_bytes(body) != expected_sha:
            raise ToolchainLockError("SOURCE_CONTENT_MISMATCH", path)
        if git_blob_sha1(body) != expected_blobs[path]:
            raise ToolchainLockError("SOURCE_BLOB_MISMATCH", path)

    for line in _git(root, "ls-tree", "-r", "HEAD").splitlines():
        header, _name = line.split("\t", 1)
        mode, kind, _object_id = header.split(" ")
        if kind != "blob" or mode not in {"100644", "100755"}:
            raise ToolchainLockError(
                "SOURCE_FILE_UNSAFE",
                "Zoekt tree contains symlink/submodule/special entry",
            )
    return VerifiedZoektSource(
        commit=observed_commit,
        tree=observed_tree,
        go_mod_blob=observed_blobs["go.mod"],
        go_sum_blob=observed_blobs["go.sum"],
        license_blob=observed_blobs["LICENSE"],
    )


def validate_tar_archive(
    archive_path: Path,
    *,
    expected_sha256: str | None = None,
    expected_size: int | None = None,
    expected_top_level: str,
    max_archive_bytes: int,
    max_member_bytes: int,
    max_total_bytes: int,
) -> tuple[ArchiveMember, ...]:
    """Validate a gzip tar without extracting or accepting link-like entries."""

    path = Path(archive_path)
    metadata = _regular_file_metadata(path, "ARCHIVE_UNSAFE")
    if metadata.st_size > max_archive_bytes:
        raise ToolchainLockError("ARCHIVE_UNSAFE", "archive exceeds byte ceiling")
    if expected_size is not None and metadata.st_size != expected_size:
        raise ToolchainLockError("ARCHIVE_SIZE_MISMATCH", path.name)
    if expected_sha256 is not None:
        _require_digest(expected_sha256, 64, "expected archive SHA-256")
        if sha256_file(path, max_bytes=max_archive_bytes) != expected_sha256:
            raise ToolchainLockError("ARCHIVE_DIGEST_MISMATCH", path.name)
    try:
        with path.open("rb") as source:
            if source.read(2) != b"\x1f\x8b":
                raise ToolchainLockError("ARCHIVE_UNSAFE", "archive is not gzip")
        with tarfile.open(path, mode="r:gz") as archive:
            raw_members = archive.getmembers()
    except ToolchainLockError:
        raise
    except (OSError, tarfile.TarError) as error:
        raise ToolchainLockError(
            "ARCHIVE_UNSAFE", "archive cannot be parsed"
        ) from error

    if not raw_members:
        raise ToolchainLockError("ARCHIVE_UNSAFE", "archive is empty")
    seen: set[str] = set()
    total = 0
    validated: list[ArchiveMember] = []
    for member in raw_members:
        name = _safe_archive_name(member.name, expected_top_level)
        if name in seen:
            raise ToolchainLockError("ARCHIVE_UNSAFE", f"duplicate member {name}")
        seen.add(name)
        if member.isdir():
            kind = "directory"
            size = 0
        elif member.isreg():
            kind = "file"
            size = member.size
        else:
            raise ToolchainLockError("ARCHIVE_UNSAFE", f"link/special member {name}")
        if member.mode & (stat.S_IWOTH | stat.S_ISUID | stat.S_ISGID | stat.S_ISVTX):
            raise ToolchainLockError("ARCHIVE_UNSAFE", f"unsafe mode for {name}")
        if size < 0 or size > max_member_bytes:
            raise ToolchainLockError("ARCHIVE_UNSAFE", f"oversized member {name}")
        total += size
        if total > max_total_bytes:
            raise ToolchainLockError(
                "ARCHIVE_UNSAFE", "expanded archive exceeds ceiling"
            )
        validated.append(
            ArchiveMember(name=name, kind=kind, size=size, mode=member.mode)
        )
    return tuple(sorted(validated, key=lambda member: member.name))


def safe_extract_tar(
    archive_path: Path,
    destination: Path,
    *,
    expected_sha256: str | None = None,
    expected_size: int | None = None,
    expected_top_level: str,
    max_archive_bytes: int,
    max_member_bytes: int,
    max_total_bytes: int,
) -> tuple[ArchiveMember, ...]:
    """Extract validated files without following links or overwriting any path."""

    members = validate_tar_archive(
        archive_path,
        expected_sha256=expected_sha256,
        expected_size=expected_size,
        expected_top_level=expected_top_level,
        max_archive_bytes=max_archive_bytes,
        max_member_bytes=max_member_bytes,
        max_total_bytes=max_total_bytes,
    )
    root = Path(destination)
    try:
        if root.exists() or root.is_symlink():
            metadata = root.lstat()
            if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
                raise ToolchainLockError(
                    "DESTINATION_UNSAFE", "destination is not a directory"
                )
        else:
            root.mkdir(parents=True, mode=0o700)
    except OSError as error:
        raise ToolchainLockError(
            "DESTINATION_UNSAFE", "destination unavailable"
        ) from error

    try:
        with tarfile.open(archive_path, mode="r:gz") as archive:
            archive_members = {member.name.rstrip("/"): member for member in archive}
            for member in sorted(
                members, key=lambda row: (row.name.count("/"), row.name)
            ):
                target = root.joinpath(*PurePosixPath(member.name).parts)
                _assert_existing_parents_are_directories(root, target.parent)
                if member.kind == "directory":
                    if target.exists() or target.is_symlink():
                        metadata = target.lstat()
                        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(
                            metadata.st_mode
                        ):
                            raise ToolchainLockError("DESTINATION_UNSAFE", member.name)
                    else:
                        target.mkdir(mode=member.mode & 0o755)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
                if hasattr(os, "O_NOFOLLOW"):
                    flags |= os.O_NOFOLLOW
                descriptor = os.open(target, flags, member.mode & 0o755)
                try:
                    raw_member = archive_members.get(member.name)
                    source = (
                        archive.extractfile(raw_member)
                        if raw_member is not None
                        else None
                    )
                    if source is None:
                        raise ToolchainLockError("ARCHIVE_UNSAFE", member.name)
                    with os.fdopen(descriptor, "wb", closefd=False) as output:
                        remaining = member.size
                        while remaining:
                            block = source.read(min(1024 * 1024, remaining))
                            if not block:
                                raise ToolchainLockError(
                                    "ARCHIVE_TRUNCATED", member.name
                                )
                            output.write(block)
                            remaining -= len(block)
                        if source.read(1):
                            raise ToolchainLockError(
                                "ARCHIVE_SIZE_MISMATCH", member.name
                            )
                finally:
                    os.close(descriptor)
    except ToolchainLockError:
        raise
    except (OSError, tarfile.TarError) as error:
        raise ToolchainLockError(
            "DESTINATION_UNSAFE", "archive extraction failed"
        ) from error
    return members


def _validate_schema_file(path: Path) -> None:
    schema, _ = _strict_json_file(
        path, invalid_code="SCHEMA_INVALID", unsafe_code="SCHEMA_UNSAFE"
    )
    if not isinstance(schema, Mapping):
        raise ToolchainLockError("SCHEMA_INVALID", "schema must be an object")
    expected = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": SCHEMA_FILENAME,
        "type": "object",
        "additionalProperties": False,
    }
    for key, value in expected.items():
        if schema.get(key) != value:
            raise ToolchainLockError("SCHEMA_INVALID", f"schema {key} differs")
    properties = schema.get("properties")
    if not isinstance(properties, Mapping):
        raise ToolchainLockError("SCHEMA_INVALID", "schema properties missing")
    for key in _TOP_LEVEL_FIELDS:
        if key not in properties:
            raise ToolchainLockError("SCHEMA_INVALID", f"schema omits {key}")
    if set(schema.get("required", ())) != _TOP_LEVEL_FIELDS:
        raise ToolchainLockError("SCHEMA_INVALID", "schema required fields differ")
    if properties.get("mode") != {"const": "Z0"}:
        raise ToolchainLockError("SCHEMA_INVALID", "schema mode is not fixed")


def _validate_urls(payload: Mapping[str, object]) -> None:
    urls = (
        _value_at(payload, ("zoekt", "source_url")),
        _value_at(payload, ("go", "archive", "url")),
    )
    for value in urls:
        if not isinstance(value, str):
            raise ToolchainLockError("PIN_MISMATCH", "acquisition URL is not text")
        parsed = urlparse(value)
        if (
            parsed.scheme != "https"
            or parsed.hostname not in ALLOWED_HOSTS
            or parsed.username is not None
            or parsed.password is not None
            or parsed.port is not None
            or parsed.query
            or parsed.fragment
        ):
            raise ToolchainLockError("ACQUISITION_URL_FORBIDDEN", value)


def _pin(
    payload: Mapping[str, object], path: tuple[str, ...], expected: object
) -> None:
    observed = _value_at(payload, path)
    if observed != expected:
        raise ToolchainLockError("PIN_MISMATCH", f"{'.'.join(path)} differs")


def _require_exact_mapping(
    payload: Mapping[str, object], path: tuple[str, ...], expected: Mapping[str, object]
) -> None:
    observed = _value_at(payload, path)
    if observed != expected:
        raise ToolchainLockError("PIN_MISMATCH", f"{'.'.join(path)} differs")


def _mapping_at(
    payload: Mapping[str, object], path: tuple[str, ...]
) -> Mapping[str, object]:
    value = _value_at(payload, path)
    if not isinstance(value, Mapping):
        raise ToolchainLockError(
            "LOCK_SHAPE_MISMATCH", f"{'.'.join(path)} is not an object"
        )
    return value


def _value_at(payload: Mapping[str, object], path: tuple[str, ...]) -> object:
    current: object = payload
    for component in path:
        if not isinstance(current, Mapping) or component not in current:
            raise ToolchainLockError("LOCK_SHAPE_MISMATCH", f"{'.'.join(path)} missing")
        current = current[component]
    return current


def _require_digest(value: object, length: int, label: str) -> str:
    pattern = _SHA1_RE if length == 40 else _SHA256_RE
    if not isinstance(value, str) or pattern.fullmatch(value) is None:
        raise ToolchainLockError("INVALID_DIGEST", label)
    return value


def _regular_file_metadata(path: Path, code: str) -> os.stat_result:
    try:
        metadata = path.lstat()
    except OSError as error:
        raise ToolchainLockError(code, f"{path.name} is unavailable") from error
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise ToolchainLockError(code, f"{path.name} is not a regular file")
    return metadata


def _safe_archive_name(name: str, expected_top_level: str) -> str:
    if not name or "\\" in name or "\x00" in name:
        raise ToolchainLockError("ARCHIVE_UNSAFE", "invalid member name")
    candidate = PurePosixPath(name)
    if candidate.is_absolute() or name.startswith("/"):
        raise ToolchainLockError("ARCHIVE_UNSAFE", "absolute member path")
    parts = candidate.parts
    if any(part in {"", ".", ".."} for part in parts):
        raise ToolchainLockError("ARCHIVE_UNSAFE", "traversal member path")
    if not parts or parts[0] != expected_top_level:
        raise ToolchainLockError("ARCHIVE_UNSAFE", "unexpected archive root")
    if len(name.encode("utf-8")) > 4096 or any(
        len(part.encode("utf-8")) > 255
        or any(ord(character) < 32 or ord(character) == 127 for character in part)
        for part in parts
    ):
        raise ToolchainLockError("ARCHIVE_UNSAFE", "unsupported member name")
    normalized = candidate.as_posix().rstrip("/")
    if not normalized:
        raise ToolchainLockError("ARCHIVE_UNSAFE", "empty member path")
    return normalized


def _assert_existing_parents_are_directories(root: Path, parent: Path) -> None:
    try:
        relative = parent.relative_to(root)
    except ValueError as error:
        raise ToolchainLockError(
            "DESTINATION_UNSAFE", "path escaped destination"
        ) from error
    cursor = root
    for part in relative.parts:
        cursor /= part
        if cursor.exists() or cursor.is_symlink():
            metadata = cursor.lstat()
            if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
                raise ToolchainLockError("DESTINATION_UNSAFE", cursor.name)


def _git(root: Path, *arguments: str) -> str:
    try:
        completed = subprocess.run(
            ["/usr/bin/git", "-C", os.fspath(root), *arguments],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
            env={"PATH": "/usr/bin:/bin:/usr/local/bin", "LANG": "C", "LC_ALL": "C"},
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ToolchainLockError(
            "GIT_INSPECTION_FAILED", "Git invocation failed"
        ) from error
    if completed.returncode != 0:
        raise ToolchainLockError(
            "GIT_INSPECTION_FAILED", "Git rejected source checkout"
        )
    return completed.stdout.strip()
