"""Pure compiler for bounded exact-text repairs on an existing GitHub PR branch.

The caller supplies two disjoint inputs:

* an authority snapshot resolved from canonical GitHub and organizational owners;
* a model-authored request containing exact old/new text blocks.

The compiler performs no network, filesystem, credential, clock, subprocess,
mutation, or persistence work.  It validates immutable carrier/head/blob/path
fences, verifies every complete source snapshot against its Git object id, and
materializes exact post-images outside model context.  Only bounded previews and
digests are model-visible.
"""
from __future__ import annotations

import dataclasses
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
_PROTECTED_PATH_PREFIXES = (".git/", ".github/", "docs/sol_skills/")
_SECRET_FILENAMES = frozenset(
    {".env", "credentials.json", "secrets.json", "id_rsa", "id_ed25519"}
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
    SOURCE_BLOB_CONTENT_MISMATCH = "SOURCE_BLOB_CONTENT_MISMATCH"
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
    """Deterministic payload-bounded refusal."""

    def __init__(self, code: ExactEditIssue, message: str) -> None:
        self.code = code
        super().__init__(f"{code.value}: {message}")


@dataclasses.dataclass(frozen=True)
class ExactEditAuthority:
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
        return dataclasses.asdict(self)


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
        return MappingProxyType({item.path: item.post_image for item in self.files})


@dataclasses.dataclass(frozen=True)
class _LocatedReplacement:
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


def _git_blob_oid(content: bytes, *, width: int) -> str:
    framed = b"blob " + str(len(content)).encode("ascii") + b"\0" + content
    if width == 40:
        return hashlib.sha1(framed, usedforsecurity=False).hexdigest()
    if width == 64:
        return hashlib.sha256(framed).hexdigest()
    raise AssertionError("validated OID width must be 40 or 64")


def _fail(code: ExactEditIssue, message: str) -> None:
    raise ExactEditError(code, message)


def _bounded_token(value: object, *, field: str, pattern: re.Pattern[str]) -> str:
    if not isinstance(value, str) or pattern.fullmatch(value) is None:
        _fail(ExactEditIssue.AUTHORITY_IDENTITY_INVALID, f"{field} is malformed")
    return value


def _oid(value: object, *, field: str, issue: ExactEditIssue) -> str:
    if not isinstance(value, str) or _OID_RE.fullmatch(value) is None:
        _fail(issue, f"{field} must be a lowercase Git object id")
    return value


def _branch(value: object, *, field: str) -> str:
    token = _bounded_token(value, field=field, pattern=_REF_RE)
    if (
        token.startswith("refs/")
        or token == "HEAD"
        or token.startswith("-")
        or token.endswith(".")
        or token.endswith(".lock")
        or ".." in token
        or "//" in token
        or "@{" in token
    ):
        _fail(ExactEditIssue.AUTHORITY_IDENTITY_INVALID, f"{field} is not canonical")
    return token


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
    if ".git" in path.split("/") or path in _PROTECTED_EXACT_PATHS:
        return True
    if any(path == prefix[:-1] or path.startswith(prefix) for prefix in _PROTECTED_PATH_PREFIXES):
        return True
    name = path.rsplit("/", 1)[-1].lower()
    return (
        name in _SECRET_FILENAMES
        or name.startswith(".env.")
        or name.endswith(_SECRET_SUFFIXES)
    )


def _secret_shaped(text: str) -> bool:
    return any(pattern.search(text) is not None for pattern in _SECRET_PATTERNS)


def _validate_authority(authority: ExactEditAuthority) -> tuple[str, ...]:
    if not isinstance(authority, ExactEditAuthority):
        _fail(ExactEditIssue.AUTHORITY_IDENTITY_INVALID, "authority has wrong type")
    if not isinstance(authority.operation_key, str) or _OPERATION_RE.fullmatch(authority.operation_key) is None:
        _fail(ExactEditIssue.AUTHORITY_IDENTITY_INVALID, "operation_key is malformed")
    _bounded_token(authority.carrier_ref, field="carrier_ref", pattern=_SOURCE_REF_RE)
    _bounded_token(authority.source_ref, field="source_ref", pattern=_SOURCE_REF_RE)
    _bounded_token(authority.repository, field="repository", pattern=_REPOSITORY_RE)
    default_branch = _branch(authority.default_branch, field="default_branch")
    branch = _branch(authority.branch, field="branch")
    _oid(
        authority.observed_head_oid,
        field="observed_head_oid",
        issue=ExactEditIssue.AUTHORITY_IDENTITY_INVALID,
    )
    if type(authority.pull_request_number) is not int or authority.pull_request_number <= 0:
        _fail(ExactEditIssue.AUTHORITY_IDENTITY_INVALID, "pull_request_number must be positive")
    if authority.carrier_state is not CarrierState.EXACT:
        _fail(ExactEditIssue.CARRIER_NOT_EXACT, "operation carrier is not exact")
    if authority.writer_state is not WriterState.EXACT:
        _fail(ExactEditIssue.WRITER_NOT_EXACT, "current writer is not exact")
    if authority.pull_request_state is not PullRequestState.OPEN:
        _fail(ExactEditIssue.PULL_REQUEST_NOT_OPEN, "pull request is not open")
    if branch == default_branch:
        _fail(ExactEditIssue.DEFAULT_BRANCH_REFUSED, "default branch cannot be edited")
    if authority.branch_protected is not False:
        _fail(ExactEditIssue.PROTECTED_BRANCH_REFUSED, "protected branch cannot be edited")
    if authority.allowed_paths_complete is not True:
        _fail(
            ExactEditIssue.ALLOWED_PATH_COVERAGE_INCOMPLETE,
            "current PR changed-path coverage is incomplete",
        )
    if not isinstance(authority.allowed_paths, tuple) or not authority.allowed_paths:
        _fail(ExactEditIssue.ALLOWED_PATH_COVERAGE_INCOMPLETE, "allowed_paths must be non-empty")
    if len(authority.allowed_paths) > MAX_ALLOWED_PATHS:
        _fail(ExactEditIssue.ALLOWED_PATH_COVERAGE_INCOMPLETE, "allowed_paths exceeds bound")
    normalized = tuple(_path(item) for item in authority.allowed_paths)
    if len(set(normalized)) != len(normalized):
        _fail(ExactEditIssue.DUPLICATE_PATH, "allowed_paths contains duplicates")
    return tuple(sorted(normalized))


def _validate_request(request: ExactEditRequest, authority: ExactEditAuthority) -> None:
    if not isinstance(request, ExactEditRequest) or request.schema != INPUT_SCHEMA:
        _fail(ExactEditIssue.INPUT_SCHEMA_INVALID, "request schema/type is unsupported")
    if not isinstance(request.operation_key, str) or _OPERATION_RE.fullmatch(request.operation_key) is None:
        _fail(ExactEditIssue.OPERATION_IDENTITY_INVALID, "operation_key is malformed")
    if request.operation_key != authority.operation_key:
        _fail(ExactEditIssue.OPERATION_IDENTITY_INVALID, "operation does not match authority")
    _oid(
        request.expected_head_oid,
        field="expected_head_oid",
        issue=ExactEditIssue.OPERATION_IDENTITY_INVALID,
    )
    if request.expected_head_oid != authority.observed_head_oid:
        _fail(ExactEditIssue.HEAD_MOVED, "candidate branch head moved")
    if not isinstance(request.files, tuple) or not 1 <= len(request.files) <= MAX_FILES:
        _fail(ExactEditIssue.FILE_COUNT_INVALID, "file count is outside bound")


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
    _oid(request.expected_blob_oid, field="expected_blob_oid", issue=ExactEditIssue.BLOB_MOVED)
    if not isinstance(request.replacements, tuple) or not 1 <= len(request.replacements) <= MAX_REPLACEMENTS_PER_FILE:
        _fail(ExactEditIssue.REPLACEMENT_COUNT_INVALID, "replacement count is outside bound")
    return path, request.replacements


def _validate_snapshot(snapshot: ExactFileSnapshot, *, path: str) -> bytes:
    if not isinstance(snapshot, ExactFileSnapshot):
        _fail(ExactEditIssue.SNAPSHOT_SET_MISMATCH, "snapshot has wrong type")
    if _path(snapshot.path) != path:
        _fail(ExactEditIssue.SNAPSHOT_SET_MISMATCH, "snapshot path mismatch")
    oid = _oid(snapshot.blob_oid, field="snapshot blob_oid", issue=ExactEditIssue.BLOB_MOVED)
    if snapshot.mode != "100644":
        _fail(ExactEditIssue.FILE_MODE_REFUSED, f"path {path!r} is not an ordinary 100644 file")
    if not isinstance(snapshot.content, bytes):
        _fail(ExactEditIssue.INVALID_UTF8, f"path {path!r} content must be immutable bytes")
    if len(snapshot.content) > MAX_FILE_BYTES:
        _fail(ExactEditIssue.FILE_TOO_LARGE, f"path {path!r} exceeds file-size bound")
    if b"\x00" in snapshot.content:
        _fail(ExactEditIssue.BINARY_REFUSED, f"path {path!r} contains NUL bytes")
    try:
        snapshot.content.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise ExactEditError(ExactEditIssue.INVALID_UTF8, f"path {path!r} is not UTF-8") from exc
    if _git_blob_oid(snapshot.content, width=len(oid)) != oid:
        _fail(
            ExactEditIssue.SOURCE_BLOB_CONTENT_MISMATCH,
            f"path {path!r} bytes do not match the claimed Git blob id",
        )
    return snapshot.content


def _find_all(haystack: bytes, needle: bytes) -> list[int]:
    positions: list[int] = []
    start = 0
    while len(positions) < 2:
        position = haystack.find(needle, start)
        if position < 0:
            break
        positions.append(position)
        start = position + 1
    return positions


def _locate_replacements(
    path: str,
    source: bytes,
    replacements: tuple[ExactTextReplacement, ...],
) -> tuple[tuple[_LocatedReplacement, ...], int]:
    located: list[_LocatedReplacement] = []
    total = 0
    for replacement in replacements:
        if not isinstance(replacement, ExactTextReplacement):
            _fail(ExactEditIssue.INPUT_SCHEMA_INVALID, "replacement has wrong type")
        if not isinstance(replacement.old_text, str) or not isinstance(replacement.new_text, str):
            _fail(ExactEditIssue.INPUT_SCHEMA_INVALID, "replacement text must be text")
        old = replacement.old_text.encode("utf-8")
        new = replacement.new_text.encode("utf-8")
        if not old:
            _fail(ExactEditIssue.EMPTY_ANCHOR, f"path {path!r} has empty old_text")
        if old == new:
            _fail(ExactEditIssue.NOOP_REPLACEMENT, f"path {path!r} has no-op replacement")
        if len(old) > MAX_ANCHOR_BYTES or len(new) > MAX_REPLACEMENT_BYTES:
            _fail(ExactEditIssue.EDIT_TOO_LARGE, f"path {path!r} has oversized replacement")
        total += len(old) + len(new)
        if total > MAX_TOTAL_EDIT_BYTES:
            _fail(ExactEditIssue.TOTAL_EDIT_TOO_LARGE, "total edit payload exceeds bound")
        if _secret_shaped(replacement.old_text) or _secret_shaped(replacement.new_text):
            _fail(ExactEditIssue.SECRET_SHAPED_CONTENT, f"path {path!r} contains secret-shaped text")
        positions = _find_all(source, old)
        if not positions:
            _fail(ExactEditIssue.ANCHOR_NOT_FOUND, f"path {path!r} anchor not found")
        if len(positions) != 1:
            _fail(ExactEditIssue.ANCHOR_NOT_UNIQUE, f"path {path!r} anchor is not unique")
        located.append(
            _LocatedReplacement(
                start=positions[0],
                end=positions[0] + len(old),
                old=old,
                new=new,
            )
        )
    canonical = sorted(located, key=lambda item: (item.start, item.end, _sha256(item.old), _sha256(item.new)))
    for previous, current in zip(canonical, canonical[1:]):
        if current.start < previous.end:
            _fail(ExactEditIssue.EDIT_OVERLAP, f"path {path!r} replacements overlap")
    return tuple(canonical), total


def _apply(source: bytes, located: tuple[_LocatedReplacement, ...]) -> bytes:
    result = source
    for item in reversed(located):
        if result[item.start : item.end] != item.old:
            _fail(ExactEditIssue.EDIT_OVERLAP, "replacement coordinates became invalid")
        result = result[: item.start] + item.new + result[item.end :]
    return result


def _render_preview_line(prefix: str, line: str) -> str:
    rendered = prefix + line
    if not line.endswith(("\n", "\r")):
        rendered += "\n\\ No newline at end of replacement\n"
    return rendered


def _replacement_preview(item: _LocatedReplacement, *, ordinal: int) -> tuple[str, int, int]:
    old_lines = item.old.decode("utf-8").splitlines(keepends=True)
    new_lines = item.new.decode("utf-8").splitlines(keepends=True)
    prefix = 0
    while prefix < min(len(old_lines), len(new_lines)) and old_lines[prefix] == new_lines[prefix]:
        prefix += 1
    suffix = 0
    while (
        suffix < len(old_lines) - prefix
        and suffix < len(new_lines) - prefix
        and old_lines[-suffix - 1] == new_lines[-suffix - 1]
    ):
        suffix += 1
    old_end = len(old_lines) - suffix
    new_end = len(new_lines) - suffix
    before = old_lines[max(0, prefix - 3) : prefix]
    old_changed = old_lines[prefix:old_end]
    new_changed = new_lines[prefix:new_end]
    after = old_lines[old_end : min(len(old_lines), old_end + 3)]
    parts = [
        f"@@ exact-replacement {ordinal} bytes {item.start}:{item.end} "
        f"old_sha256={_sha256(item.old)} new_sha256={_sha256(item.new)} @@\n"
    ]
    parts.extend(_render_preview_line(" ", line) for line in before)
    parts.extend(_render_preview_line("-", line) for line in old_changed)
    parts.extend(_render_preview_line("+", line) for line in new_changed)
    parts.extend(_render_preview_line(" ", line) for line in after)
    return "".join(parts), len(new_changed), len(old_changed)


def _preview(path: str, located: tuple[_LocatedReplacement, ...]) -> tuple[str, int, int]:
    parts = [f"--- a/{path}\n", f"+++ b/{path}\n"]
    additions = deletions = 0
    for ordinal, item in enumerate(located):
        rendered, add, delete = _replacement_preview(item, ordinal=ordinal)
        parts.append(rendered)
        additions += add
        deletions += delete
    patch = "".join(parts)
    if len(patch.encode("utf-8")) > MAX_PREVIEW_BYTES:
        _fail(ExactEditIssue.PREVIEW_TOO_LARGE, f"path {path!r} preview exceeds bound")
    if _secret_shaped(patch):
        _fail(ExactEditIssue.SECRET_SHAPED_CONTENT, f"path {path!r} preview contains secret-shaped text")
    return patch, additions, deletions


def compile_exact_edit(
    request: ExactEditRequest,
    authority: ExactEditAuthority,
    snapshots: tuple[ExactFileSnapshot, ...],
) -> ExactEditCompilation:
    """Compile one bounded exact repair without an external effect."""

    allowed = frozenset(_validate_authority(authority))
    _validate_request(request, authority)
    if not isinstance(snapshots, tuple):
        _fail(ExactEditIssue.SNAPSHOT_SET_MISMATCH, "snapshots must be a tuple")

    requests: dict[str, ExactFileEditRequest] = {}
    replacement_count = 0
    for row in request.files:
        path, replacements = _validate_file_request(row, allowed_paths=allowed)
        if path in requests:
            _fail(ExactEditIssue.DUPLICATE_PATH, f"path {path!r} requested twice")
        requests[path] = row
        replacement_count += len(replacements)
    if replacement_count > MAX_REPLACEMENTS_TOTAL:
        _fail(ExactEditIssue.REPLACEMENT_COUNT_INVALID, "total replacement count exceeds bound")

    snapshot_map: dict[str, ExactFileSnapshot] = {}
    for snapshot in snapshots:
        if not isinstance(snapshot, ExactFileSnapshot):
            _fail(ExactEditIssue.SNAPSHOT_SET_MISMATCH, "snapshot has wrong type")
        path = _path(snapshot.path)
        if path in snapshot_map:
            _fail(ExactEditIssue.DUPLICATE_PATH, f"snapshot path {path!r} duplicated")
        snapshot_map[path] = snapshot
    if set(snapshot_map) != set(requests):
        _fail(ExactEditIssue.SNAPSHOT_SET_MISMATCH, "snapshot paths must exactly equal requested paths")

    compiled: list[CompiledFileEdit] = []
    total_source = total_edit = 0
    for path in sorted(requests):
        file_request = requests[path]
        snapshot = snapshot_map[path]
        source = _validate_snapshot(snapshot, path=path)
        if snapshot.blob_oid != file_request.expected_blob_oid:
            _fail(ExactEditIssue.BLOB_MOVED, f"path {path!r} blob moved")
        total_source += len(source)
        if total_source > MAX_TOTAL_SOURCE_BYTES:
            _fail(ExactEditIssue.TOTAL_SOURCE_TOO_LARGE, "total source bytes exceed bound")
        located, edit_bytes = _locate_replacements(path, source, file_request.replacements)
        total_edit += edit_bytes
        if total_edit > MAX_TOTAL_EDIT_BYTES:
            _fail(ExactEditIssue.TOTAL_EDIT_TOO_LARGE, "total edit payload exceeds bound")
        post_image = _apply(source, located)
        if len(post_image) > MAX_FILE_BYTES:
            _fail(ExactEditIssue.POST_IMAGE_TOO_LARGE, f"path {path!r} post-image is too large")
        if b"\x00" in post_image:
            _fail(ExactEditIssue.BINARY_REFUSED, f"path {path!r} post-image contains NUL")
        try:
            post_image.decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise ExactEditError(ExactEditIssue.INVALID_UTF8, f"path {path!r} post-image is not UTF-8") from exc
        preview, additions, deletions = _preview(path, located)
        replacements = tuple(
            CompiledReplacement(
                ordinal=index,
                start_byte=item.start,
                end_byte=item.end,
                old_sha256=_sha256(item.old),
                new_sha256=_sha256(item.new),
                old_bytes=len(item.old),
                new_bytes=len(item.new),
            )
            for index, item in enumerate(located)
        )
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
                replacements=replacements,
                preview_patch=preview,
                post_image=post_image,
            )
        )

    payload = {
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
    digest = _sha256(_canonical_bytes(payload))
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
        canonical_digest=digest,
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
