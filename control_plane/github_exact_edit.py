"""Pure compiler for bounded exact-text repairs on an existing GitHub PR branch.

The caller supplies two kinds of data that must remain separate:

* an authority snapshot resolved from canonical GitHub/organizational owners; and
* a model-authored edit request containing only exact old/new text blocks.

This module performs no network access, filesystem discovery, credential selection,
clock access, subprocess work, mutation, or persistence.  It verifies the immutable
carrier/head/blob/path fences, applies only unique non-overlapping exact replacements
to caller-supplied complete UTF-8 file bytes, and returns deterministic post-images
plus a bounded public preview.  A later owner-specific GitHub app may bind the
compilation digest into a prepared token and perform at most one native branch commit.
"""
from __future__ import annotations

import dataclasses
import difflib
import hashlib
import json
import re
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping


INPUT_SCHEMA = "mastermind.github_exact_edit.input.v1"
OUTPUT_SCHEMA = "mastermind.github_exact_edit.compilation.v1"

MAX_FILES = 3
MAX_REPLACEMENTS_PER_FILE = 10
MAX_REPLACEMENTS_TOTAL = 16
MAX_ALLOWED_PATHS = 256
MAX_FILE_BYTES = 4 * 1024 * 1024
MAX_TOTAL_SOURCE_BYTES = 8 * 1024 * 1024
MAX_ANCHOR_BYTES = 64 * 1024
MAX_REPLACEMENT_BYTES = 128 * 1024
MAX_TOTAL_EDIT_BYTES = 256 * 1024
MAX_PREVIEW_BYTES = 128 * 1024

_OPERATION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,191}$")
_REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}$")
_REF_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,255}$")
_PATH_RE = re.compile(r"^[A-Za-z0-9._/-]{1,512}$")
_SOURCE_REF_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9:._/@#-]{0,255}$")
_OID_RE = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
_SECRET_PATTERNS = (
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{40,}\b", re.IGNORECASE),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b", re.IGNORECASE),
    re.compile(r"\bsk-[A-Za-z0-9_-]{30,}\b"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
)

_PROTECTED_EXACT_PATHS = frozenset(
    {
        "config/authority_map.yml",
        "config/executive_agent_capabilities.json",
    }
)
_PROTECTED_PATH_PREFIXES = (
    ".git/",
    ".github/",
    "docs/sol_skills/",
)
_SECRET_FILENAMES = frozenset(
    {
        ".env",
        "credentials.json",
        "secrets.json",
        "id_rsa",
        "id_ed25519",
    }
)
_SECRET_SUFFIXES = (".pem", ".key", ".p12", ".pfx")


class ExactEditIssue(str, Enum):
    INPUT_SCHEMA_INVALID = "INPUT_SCHEMA_INVALID"
    OPERATION_IDENTITY_INVALID = "OPERATION_IDENTITY_INVALID"
    AUTHORITY_IDENTITY_INVALID = "AUTHORITY_IDENTITY_INVALID"
    CARRIER_NOT_EXACT = "CARRIER_NOT_EXACT"
    WRITER_NOT_EXACT = "WRITER_NOT_EXACT"
    PULL_REQUEST_NOT_OPEN = "PULL_REQUEST_NOT_OPEN"
    DEFAULT_BRANCH_REFUSED = "DEFAULT_BRANCH_REFUSED"
    PROTECTED_BRANCH_REFUSED = "PROTECTED_BRANCH_REFUSED"
    ALLOWED_PATH_COVERAGE_INCOMPLETE = "ALLOWED_PATH_COVERAGE_INCOMPLETE"
    HEAD_MOVED = "HEAD_MOVED"
    FILE_COUNT_INVALID = "FILE_COUNT_INVALID"
    REPLACEMENT_COUNT_INVALID = "REPLACEMENT_COUNT_INVALID"
    PATH_INVALID = "PATH_INVALID"
    PATH_PROTECTED = "PATH_PROTECTED"
    PATH_NOT_ALLOWED = "PATH_NOT_ALLOWED"
    DUPLICATE_PATH = "DUPLICATE_PATH"
    SNAPSHOT_SET_MISMATCH = "SNAPSHOT_SET_MISMATCH"
    BLOB_MOVED = "BLOB_MOVED"
    FILE_MODE_REFUSED = "FILE_MODE_REFUSED"
    FILE_TOO_LARGE = "FILE_TOO_LARGE"
    TOTAL_SOURCE_TOO_LARGE = "TOTAL_SOURCE_TOO_LARGE"
    INVALID_UTF8 = "INVALID_UTF8"
    BINARY_REFUSED = "BINARY_REFUSED"
    EMPTY_ANCHOR = "EMPTY_ANCHOR"
    NOOP_REPLACEMENT = "NOOP_REPLACEMENT"
    EDIT_TOO_LARGE = "EDIT_TOO_LARGE"
    TOTAL_EDIT_TOO_LARGE = "TOTAL_EDIT_TOO_LARGE"
    SECRET_SHAPED_CONTENT = "SECRET_SHAPED_CONTENT"
    ANCHOR_NOT_FOUND = "ANCHOR_NOT_FOUND"
    ANCHOR_NOT_UNIQUE = "ANCHOR_NOT_UNIQUE"
    EDIT_OVERLAP = "EDIT_OVERLAP"
    POST_IMAGE_TOO_LARGE = "POST_IMAGE_TOO_LARGE"
    PREVIEW_TOO_LARGE = "PREVIEW_TOO_LARGE"


class CarrierState(str, Enum):
    EXACT = "EXACT"
    CONFLICT = "CONFLICT"
    UNKNOWN = "UNKNOWN"


class WriterState(str, Enum):
    EXACT = "EXACT"
    CONFLICT = "CONFLICT"
    UNKNOWN = "UNKNOWN"


class PullRequestState(str, Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    MERGED = "MERGED"
    UNKNOWN = "UNKNOWN"


class ExactEditError(ValueError):
    """A deterministic exact-edit input, authority, or compilation refusal."""

    def __init__(self, code: ExactEditIssue, message: str) -> None:
        self.code = code
        super().__init__(f"{code.value}: {message}")


@dataclasses.dataclass(frozen=True)
class ExactEditAuthority:
    """Server-resolved authority and GitHub carrier facts.

    None of these fields are inferred from the edit request.  The future live
    adapter must obtain them from the accepted operation/carrier owner and exact
    GitHub reads immediately before preparation.
    """

    operation_key: str
    carrier_ref: str
    source_ref: str
    repository: str
    default_branch: str
    branch: str
    pull_request_number: int
    pull_request_state: PullRequestState
    branch_protected: bool
    carrier_state: CarrierState
    writer_state: WriterState
    observed_head_oid: str
    allowed_paths: tuple[str, ...]
    allowed_paths_complete: bool


@dataclasses.dataclass(frozen=True)
class ExactTextReplacement:
    old_text: str
    new_text: str


@dataclasses.dataclass(frozen=True)
class ExactFileEditRequest:
    path: str
    expected_blob_oid: str
    replacements: tuple[ExactTextReplacement, ...]


@dataclasses.dataclass(frozen=True)
class ExactEditRequest:
    schema: str
    operation_key: str
    expected_head_oid: str
    files: tuple[ExactFileEditRequest, ...]


@dataclasses.dataclass(frozen=True)
class ExactFileSnapshot:
    """Complete immutable bytes fetched by the trusted GitHub owner."""

    path: str
    blob_oid: str
    mode: str
    content: bytes


@dataclasses.dataclass(frozen=True)
class CompiledReplacement:
    ordinal: int
    start_byte: int
    end_byte: int
    old_sha256: str
    new_sha256: str
    old_bytes: int
    new_bytes: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "ordinal": self.ordinal,
            "start_byte": self.start_byte,
            "end_byte": self.end_byte,
            "old_sha256": self.old_sha256,
            "new_sha256": self.new_sha256,
            "old_bytes": self.old_bytes,
            "new_bytes": self.new_bytes,
        }


@dataclasses.dataclass(frozen=True)
class CompiledFileEdit:
    path: str
    before_blob_oid: str
    before_sha256: str
    after_sha256: str
    before_bytes: int
    after_bytes: int
    additions: int
    deletions: int
    replacements: tuple[CompiledReplacement, ...]
    preview_patch: str
    post_image: bytes = dataclasses.field(repr=False)

    def to_public_dict(self) -> dict[str, Any]:
        """Return the bounded model-visible projection, never the full post-image."""

        return {
            "path": self.path,
            "before_blob_oid": self.before_blob_oid,
            "before_sha256": self.before_sha256,
            "after_sha256": self.after_sha256,
            "before_bytes": self.before_bytes,
            "after_bytes": self.after_bytes,
            "additions": self.additions,
            "deletions": self.deletions,
            "replacements": [item.to_dict() for item in self.replacements],
            "preview_patch": self.preview_patch,
            "preview_sha256": _sha256(self.preview_patch.encode("utf-8")),
        }


@dataclasses.dataclass(frozen=True)
class ExactEditCompilation:
    schema: str
    operation_key: str
    carrier_ref: str
    authority_source_ref: str
    repository: str
    branch: str
    pull_request_number: int
    expected_head_oid: str
    observed_head_oid: str
    files: tuple[CompiledFileEdit, ...]
    canonical_digest: str

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "operation_key": self.operation_key,
            "carrier_ref": self.carrier_ref,
            "authority_source_ref": self.authority_source_ref,
            "repository": self.repository,
            "branch": self.branch,
            "pull_request_number": self.pull_request_number,
            "expected_head_oid": self.expected_head_oid,
            "observed_head_oid": self.observed_head_oid,
            "files": [item.to_public_dict() for item in self.files],
            "canonical_digest": self.canonical_digest,
        }

    def post_images(self) -> Mapping[str, bytes]:
        """Return exact post-images for the owner-native GitHub commit adapter."""

        return MappingProxyType({item.path: item.post_image for item in self.files})


@dataclasses.dataclass(frozen=True)
class _LocatedReplacement:
    ordinal: int
    start: int
    end: int
    old: bytes
    new: bytes


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _fail(code: ExactEditIssue, message: str) -> None:
    raise ExactEditError(code, message)


def _bounded_token(value: object, *, field: str, pattern: re.Pattern[str]) -> str:
    if not isinstance(value, str):
        _fail(ExactEditIssue.AUTHORITY_IDENTITY_INVALID, f"{field} must be text")
    if pattern.fullmatch(value) is None:
        _fail(ExactEditIssue.AUTHORITY_IDENTITY_INVALID, f"{field} is malformed")
    return value


def _oid(value: object, *, field: str, issue: ExactEditIssue) -> str:
    if not isinstance(value, str) or _OID_RE.fullmatch(value) is None:
        _fail(issue, f"{field} must be a lowercase Git object id")
    return value


def _path(value: object, *, issue: ExactEditIssue = ExactEditIssue.PATH_INVALID) -> str:
    if not isinstance(value, str) or _PATH_RE.fullmatch(value) is None:
        _fail(issue, "repository path is malformed")
    if (
        value.startswith("/")
        or value.endswith("/")
        or "//" in value
        or "\\" in value
        or any(part in {"", ".", ".."} for part in value.split("/"))
    ):
        _fail(issue, "repository path is not canonical")
    return value


def _path_is_protected(path: str) -> bool:
    if ".git" in path.split("/"):
        return True
    if path in _PROTECTED_EXACT_PATHS:
        return True
    if any(path == prefix[:-1] or path.startswith(prefix) for prefix in _PROTECTED_PATH_PREFIXES):
        return True
    name = path.rsplit("/", 1)[-1].lower()
    if name in _SECRET_FILENAMES or name.startswith(".env."):
        return True
    return name.endswith(_SECRET_SUFFIXES)


def _secret_shaped(text: str) -> bool:
    return any(pattern.search(text) is not None for pattern in _SECRET_PATTERNS)


def _find_all(haystack: bytes, needle: bytes, *, stop_after: int = 2) -> list[int]:
    positions: list[int] = []
    start = 0
    while len(positions) < stop_after:
        position = haystack.find(needle, start)
        if position < 0:
            break
        positions.append(position)
        start = position + 1
    return positions


def _validate_authority(authority: ExactEditAuthority) -> tuple[str, ...]:
    if not isinstance(authority, ExactEditAuthority):
        _fail(ExactEditIssue.AUTHORITY_IDENTITY_INVALID, "authority has wrong type")
    if (
        not isinstance(authority.operation_key, str)
        or _OPERATION_RE.fullmatch(authority.operation_key) is None
    ):
        _fail(ExactEditIssue.AUTHORITY_IDENTITY_INVALID, "operation_key is malformed")
    _bounded_token(authority.carrier_ref, field="carrier_ref", pattern=_SOURCE_REF_RE)
    _bounded_token(authority.source_ref, field="source_ref", pattern=_SOURCE_REF_RE)
    _bounded_token(authority.repository, field="repository", pattern=_REPOSITORY_RE)
    _bounded_token(authority.default_branch, field="default_branch", pattern=_REF_RE)
    _bounded_token(authority.branch, field="branch", pattern=_REF_RE)
    if (
        authority.default_branch.startswith("refs/")
        or authority.branch.startswith("refs/")
        or authority.default_branch == "HEAD"
        or authority.branch == "HEAD"
    ):
        _fail(
            ExactEditIssue.AUTHORITY_IDENTITY_INVALID,
            "branch identities must be short branch names",
        )
    _oid(
        authority.observed_head_oid,
        field="observed_head_oid",
        issue=ExactEditIssue.AUTHORITY_IDENTITY_INVALID,
    )
    if type(authority.pull_request_number) is not int or authority.pull_request_number <= 0:
        _fail(
            ExactEditIssue.AUTHORITY_IDENTITY_INVALID,
            "pull_request_number must be a positive integer",
        )
    if authority.carrier_state is not CarrierState.EXACT:
        _fail(ExactEditIssue.CARRIER_NOT_EXACT, "operation carrier is not exact")
    if authority.writer_state is not WriterState.EXACT:
        _fail(ExactEditIssue.WRITER_NOT_EXACT, "current writer is not exact")
    if authority.pull_request_state is not PullRequestState.OPEN:
        _fail(ExactEditIssue.PULL_REQUEST_NOT_OPEN, "pull request is not open")
    if authority.branch == authority.default_branch:
        _fail(ExactEditIssue.DEFAULT_BRANCH_REFUSED, "default branch cannot be edited")
    if authority.branch_protected is not False:
        _fail(ExactEditIssue.PROTECTED_BRANCH_REFUSED, "protected branch cannot be edited")
    if authority.allowed_paths_complete is not True:
        _fail(
            ExactEditIssue.ALLOWED_PATH_COVERAGE_INCOMPLETE,
            "current PR changed-path coverage is incomplete",
        )
    if not isinstance(authority.allowed_paths, tuple) or not authority.allowed_paths:
        _fail(
            ExactEditIssue.ALLOWED_PATH_COVERAGE_INCOMPLETE,
            "allowed_paths must be a non-empty tuple",
        )
    if len(authority.allowed_paths) > MAX_ALLOWED_PATHS:
        _fail(
            ExactEditIssue.ALLOWED_PATH_COVERAGE_INCOMPLETE,
            "allowed_paths exceeds the reviewed bound",
        )
    normalized = tuple(_path(path) for path in authority.allowed_paths)
    if len(set(normalized)) != len(normalized):
        _fail(ExactEditIssue.DUPLICATE_PATH, "allowed_paths contains duplicates")
    return tuple(sorted(normalized))


def _validate_request(request: ExactEditRequest, authority: ExactEditAuthority) -> None:
    if not isinstance(request, ExactEditRequest):
        _fail(ExactEditIssue.INPUT_SCHEMA_INVALID, "request has wrong type")
    if request.schema != INPUT_SCHEMA:
        _fail(ExactEditIssue.INPUT_SCHEMA_INVALID, "request schema is unsupported")
    if (
        not isinstance(request.operation_key, str)
        or _OPERATION_RE.fullmatch(request.operation_key) is None
    ):
        _fail(ExactEditIssue.OPERATION_IDENTITY_INVALID, "operation_key is malformed")
    if request.operation_key != authority.operation_key:
        _fail(
            ExactEditIssue.OPERATION_IDENTITY_INVALID,
            "request operation does not match resolved authority",
        )
    _oid(
        request.expected_head_oid,
        field="expected_head_oid",
        issue=ExactEditIssue.OPERATION_IDENTITY_INVALID,
    )
    if request.expected_head_oid != authority.observed_head_oid:
        _fail(ExactEditIssue.HEAD_MOVED, "candidate branch head moved")
    if not isinstance(request.files, tuple) or not (1 <= len(request.files) <= MAX_FILES):
        _fail(ExactEditIssue.FILE_COUNT_INVALID, "file count is outside the reviewed bound")


def _validate_file_request(
    request: ExactFileEditRequest,
    *,
    allowed_paths: frozenset[str],
) -> tuple[str, tuple[ExactTextReplacement, ...]]:
    if not isinstance(request, ExactFileEditRequest):
        _fail(ExactEditIssue.INPUT_SCHEMA_INVALID, "file request has wrong type")
    path = _path(request.path)
    if _path_is_protected(path):
        _fail(ExactEditIssue.PATH_PROTECTED, f"path {path!r} is protected")
    if path not in allowed_paths:
        _fail(ExactEditIssue.PATH_NOT_ALLOWED, f"path {path!r} is not in the current PR surface")
    _oid(
        request.expected_blob_oid,
        field="expected_blob_oid",
        issue=ExactEditIssue.BLOB_MOVED,
    )
    if not isinstance(request.replacements, tuple) or not (
        1 <= len(request.replacements) <= MAX_REPLACEMENTS_PER_FILE
    ):
        _fail(
            ExactEditIssue.REPLACEMENT_COUNT_INVALID,
            f"replacement count for {path!r} is outside the reviewed bound",
        )
    return path, request.replacements


def _validate_snapshot(snapshot: ExactFileSnapshot, *, path: str) -> bytes:
    if not isinstance(snapshot, ExactFileSnapshot):
        _fail(ExactEditIssue.SNAPSHOT_SET_MISMATCH, "snapshot has wrong type")
    if _path(snapshot.path) != path:
        _fail(ExactEditIssue.SNAPSHOT_SET_MISMATCH, "snapshot path mismatch")
    _oid(snapshot.blob_oid, field="snapshot blob_oid", issue=ExactEditIssue.BLOB_MOVED)
    if snapshot.mode != "100644":
        _fail(ExactEditIssue.FILE_MODE_REFUSED, f"path {path!r} is not a regular 100644 file")
    if not isinstance(snapshot.content, bytes):
        _fail(ExactEditIssue.INVALID_UTF8, f"path {path!r} content must be immutable bytes")
    if len(snapshot.content) > MAX_FILE_BYTES:
        _fail(ExactEditIssue.FILE_TOO_LARGE, f"path {path!r} exceeds the file-size bound")
    if b"\x00" in snapshot.content:
        _fail(ExactEditIssue.BINARY_REFUSED, f"path {path!r} contains NUL bytes")
    try:
        snapshot.content.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise ExactEditError(
            ExactEditIssue.INVALID_UTF8,
            f"path {path!r} is not valid UTF-8",
        ) from exc
    return snapshot.content


def _locate_replacements(
    path: str,
    source: bytes,
    replacements: tuple[ExactTextReplacement, ...],
) -> tuple[tuple[_LocatedReplacement, ...], int]:
    located: list[_LocatedReplacement] = []
    total_edit_bytes = 0
    for ordinal, replacement in enumerate(replacements):
        if not isinstance(replacement, ExactTextReplacement):
            _fail(ExactEditIssue.INPUT_SCHEMA_INVALID, "replacement has wrong type")
        if not isinstance(replacement.old_text, str) or not isinstance(replacement.new_text, str):
            _fail(ExactEditIssue.INPUT_SCHEMA_INVALID, "replacement text must be text")
        old = replacement.old_text.encode("utf-8")
        new = replacement.new_text.encode("utf-8")
        if not old:
            _fail(ExactEditIssue.EMPTY_ANCHOR, f"path {path!r} has an empty old_text anchor")
        if old == new:
            _fail(ExactEditIssue.NOOP_REPLACEMENT, f"path {path!r} has a no-op replacement")
        if len(old) > MAX_ANCHOR_BYTES or len(new) > MAX_REPLACEMENT_BYTES:
            _fail(ExactEditIssue.EDIT_TOO_LARGE, f"path {path!r} has an oversized replacement")
        total_edit_bytes += len(old) + len(new)
        if total_edit_bytes > MAX_TOTAL_EDIT_BYTES:
            _fail(ExactEditIssue.TOTAL_EDIT_TOO_LARGE, "total edit payload exceeds the bound")
        if _secret_shaped(replacement.old_text) or _secret_shaped(replacement.new_text):
            _fail(
                ExactEditIssue.SECRET_SHAPED_CONTENT,
                f"path {path!r} replacement contains secret-shaped content",
            )
        positions = _find_all(source, old)
        if not positions:
            _fail(ExactEditIssue.ANCHOR_NOT_FOUND, f"path {path!r} anchor was not found")
        if len(positions) != 1:
            _fail(ExactEditIssue.ANCHOR_NOT_UNIQUE, f"path {path!r} anchor is not unique")
        start = positions[0]
        located.append(
            _LocatedReplacement(
                ordinal=ordinal,
                start=start,
                end=start + len(old),
                old=old,
                new=new,
            )
        )

    by_start = sorted(located, key=lambda item: (item.start, item.end, item.ordinal))
    for previous, current in zip(by_start, by_start[1:]):
        if current.start < previous.end:
            _fail(ExactEditIssue.EDIT_OVERLAP, f"path {path!r} replacements overlap")
    return tuple(located), total_edit_bytes


def _apply(source: bytes, located: tuple[_LocatedReplacement, ...]) -> bytes:
    result = source
    for replacement in sorted(
        located,
        key=lambda item: (item.start, item.end, item.ordinal),
        reverse=True,
    ):
        if result[replacement.start : replacement.end] != replacement.old:
            # This is unreachable after non-overlap validation, but keeping the
            # check makes later refactors fail closed instead of corrupting bytes.
            _fail(ExactEditIssue.EDIT_OVERLAP, "replacement coordinates became invalid")
        result = result[: replacement.start] + replacement.new + result[replacement.end :]
    return result


def _preview(path: str, before: bytes, after: bytes) -> tuple[str, int, int]:
    before_text = before.decode("utf-8", errors="strict")
    after_text = after.decode("utf-8", errors="strict")
    patch = "".join(
        difflib.unified_diff(
            before_text.splitlines(keepends=True),
            after_text.splitlines(keepends=True),
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
            n=3,
        )
    )
    encoded = patch.encode("utf-8")
    if len(encoded) > MAX_PREVIEW_BYTES:
        _fail(ExactEditIssue.PREVIEW_TOO_LARGE, f"path {path!r} preview exceeds the bound")
    if _secret_shaped(patch):
        _fail(
            ExactEditIssue.SECRET_SHAPED_CONTENT,
            f"path {path!r} preview contains secret-shaped content",
        )
    additions = 0
    deletions = 0
    for line in patch.splitlines():
        if line.startswith("+++") or line.startswith("---"):
            continue
        if line.startswith("+"):
            additions += 1
        elif line.startswith("-"):
            deletions += 1
    return patch, additions, deletions


def _compiled_replacement(
    item: _LocatedReplacement,
    *,
    canonical_ordinal: int,
) -> CompiledReplacement:
    return CompiledReplacement(
        ordinal=canonical_ordinal,
        start_byte=item.start,
        end_byte=item.end,
        old_sha256=_sha256(item.old),
        new_sha256=_sha256(item.new),
        old_bytes=len(item.old),
        new_bytes=len(item.new),
    )


def compile_exact_edit(
    request: ExactEditRequest,
    authority: ExactEditAuthority,
    snapshots: tuple[ExactFileSnapshot, ...],
) -> ExactEditCompilation:
    """Compile one bounded exact repair without performing any external effect.

    ``authority`` and ``snapshots`` are source-owned inputs.  ``request`` contains
    only the proposed exact edits and immutable expected identities.  On success,
    the returned ``post_images`` are suitable for an owner-native prepared action;
    the model-visible ``to_public_dict`` deliberately omits full file contents.
    """

    allowed = frozenset(_validate_authority(authority))
    _validate_request(request, authority)

    if not isinstance(snapshots, tuple):
        _fail(ExactEditIssue.SNAPSHOT_SET_MISMATCH, "snapshots must be a tuple")

    file_requests: dict[str, ExactFileEditRequest] = {}
    replacement_total = 0
    for file_request in request.files:
        path, replacements = _validate_file_request(file_request, allowed_paths=allowed)
        if path in file_requests:
            _fail(ExactEditIssue.DUPLICATE_PATH, f"path {path!r} is requested twice")
        file_requests[path] = file_request
        replacement_total += len(replacements)
    if replacement_total > MAX_REPLACEMENTS_TOTAL:
        _fail(
            ExactEditIssue.REPLACEMENT_COUNT_INVALID,
            "total replacement count exceeds the reviewed bound",
        )

    snapshot_map: dict[str, ExactFileSnapshot] = {}
    for snapshot in snapshots:
        if not isinstance(snapshot, ExactFileSnapshot):
            _fail(ExactEditIssue.SNAPSHOT_SET_MISMATCH, "snapshot has wrong type")
        path = _path(snapshot.path)
        if path in snapshot_map:
            _fail(ExactEditIssue.DUPLICATE_PATH, f"snapshot path {path!r} is duplicated")
        snapshot_map[path] = snapshot
    if set(snapshot_map) != set(file_requests):
        _fail(
            ExactEditIssue.SNAPSHOT_SET_MISMATCH,
            "snapshot paths must exactly equal requested paths",
        )

    compiled: list[CompiledFileEdit] = []
    total_source_bytes = 0
    total_edit_bytes = 0
    for path in sorted(file_requests):
        file_request = file_requests[path]
        snapshot = snapshot_map[path]
        source = _validate_snapshot(snapshot, path=path)
        if snapshot.blob_oid != file_request.expected_blob_oid:
            _fail(ExactEditIssue.BLOB_MOVED, f"path {path!r} blob moved")
        total_source_bytes += len(source)
        if total_source_bytes > MAX_TOTAL_SOURCE_BYTES:
            _fail(
                ExactEditIssue.TOTAL_SOURCE_TOO_LARGE,
                "total source bytes exceed the reviewed bound",
            )
        located, edit_bytes = _locate_replacements(path, source, file_request.replacements)
        total_edit_bytes += edit_bytes
        if total_edit_bytes > MAX_TOTAL_EDIT_BYTES:
            _fail(ExactEditIssue.TOTAL_EDIT_TOO_LARGE, "total edit payload exceeds the bound")
        post_image = _apply(source, located)
        if len(post_image) > MAX_FILE_BYTES:
            _fail(ExactEditIssue.POST_IMAGE_TOO_LARGE, f"path {path!r} post-image is too large")
        if b"\x00" in post_image:
            _fail(ExactEditIssue.BINARY_REFUSED, f"path {path!r} post-image contains NUL bytes")
        try:
            post_image.decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise ExactEditError(
                ExactEditIssue.INVALID_UTF8,
                f"path {path!r} post-image is not valid UTF-8",
            ) from exc
        preview_patch, additions, deletions = _preview(path, source, post_image)
        compiled.append(
            CompiledFileEdit(
                path=path,
                before_blob_oid=snapshot.blob_oid,
                before_sha256=_sha256(source),
                after_sha256=_sha256(post_image),
                before_bytes=len(source),
                after_bytes=len(post_image),
                additions=additions,
                deletions=deletions,
                replacements=tuple(
                    _compiled_replacement(item, canonical_ordinal=canonical_ordinal)
                    for canonical_ordinal, item in enumerate(
                        sorted(
                            located,
                            key=lambda value: (
                                value.start,
                                value.end,
                                _sha256(value.old),
                                _sha256(value.new),
                            ),
                        )
                    )
                ),
                preview_patch=preview_patch,
                post_image=post_image,
            )
        )

    digest_payload = {
        "schema": OUTPUT_SCHEMA,
        "operation_key": authority.operation_key,
        "carrier_ref": authority.carrier_ref,
        "authority_source_ref": authority.source_ref,
        "repository": authority.repository,
        "branch": authority.branch,
        "pull_request_number": authority.pull_request_number,
        "expected_head_oid": request.expected_head_oid,
        "observed_head_oid": authority.observed_head_oid,
        "files": [item.to_public_dict() for item in compiled],
    }
    canonical_digest = _sha256(_canonical_bytes(digest_payload))
    return ExactEditCompilation(
        schema=OUTPUT_SCHEMA,
        operation_key=authority.operation_key,
        carrier_ref=authority.carrier_ref,
        authority_source_ref=authority.source_ref,
        repository=authority.repository,
        branch=authority.branch,
        pull_request_number=authority.pull_request_number,
        expected_head_oid=request.expected_head_oid,
        observed_head_oid=authority.observed_head_oid,
        files=tuple(compiled),
        canonical_digest=canonical_digest,
    )


__all__ = [
    "INPUT_SCHEMA",
    "OUTPUT_SCHEMA",
    "MAX_FILES",
    "MAX_REPLACEMENTS_PER_FILE",
    "MAX_REPLACEMENTS_TOTAL",
    "MAX_ALLOWED_PATHS",
    "MAX_FILE_BYTES",
    "MAX_TOTAL_SOURCE_BYTES",
    "MAX_ANCHOR_BYTES",
    "MAX_REPLACEMENT_BYTES",
    "MAX_TOTAL_EDIT_BYTES",
    "MAX_PREVIEW_BYTES",
    "CarrierState",
    "CompiledFileEdit",
    "CompiledReplacement",
    "ExactEditAuthority",
    "ExactEditCompilation",
    "ExactEditError",
    "ExactEditIssue",
    "ExactEditRequest",
    "ExactFileEditRequest",
    "ExactFileSnapshot",
    "ExactTextReplacement",
    "PullRequestState",
    "WriterState",
    "compile_exact_edit",
]
