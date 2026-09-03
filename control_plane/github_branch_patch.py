"""Pure strict branch-patch preparation for the Mastermind GitHub owner.

This module materializes a bounded unified diff against exact caller-supplied
GitHub blob bytes. It performs no network access, filesystem access, mutation,
credential selection, clock access, subprocess work, persistence, branch
selection, or authority resolution. A live owner must resolve the operation's
repository, feature branch, protected refs, and exact allowed paths before
calling :func:`prepare_branch_patch`.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import re
from enum import Enum
from typing import Iterable, Mapping


INPUT_SCHEMA = "mastermind.github_branch_patch.input.v1"
PREVIEW_SCHEMA = "mastermind.github_branch_patch_preview.v1"

MAX_FILES = 3
MAX_PATCH_BYTES_PER_FILE = 65_536
MAX_PATCH_BYTES_TOTAL = 131_072
MAX_SOURCE_BYTES_PER_FILE = 4 * 1024 * 1024
MAX_RESULT_BYTES_PER_FILE = 4 * 1024 * 1024
MAX_HUNKS_PER_FILE = 100
MAX_CHANGED_LINES_PER_FILE = 2_000
MAX_CHANGED_LINES_TOTAL = 4_000
MAX_PATH_BYTES = 512

_OPERATION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,191}$")
_REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}$")
_BRANCH_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,254}$")
_OID_RE = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
_HUNK_RE = re.compile(
    r"^@@ -(?P<old_start>0|[1-9][0-9]*)"
    r"(?:,(?P<old_count>[0-9]+))?"
    r" \+(?P<new_start>0|[1-9][0-9]*)"
    r"(?:,(?P<new_count>[0-9]+))?"
    r" @@(?: .*)?$"
)
_SECRET_PATTERNS = (
    re.compile(r"github_pat_[A-Za-z0-9_]{40,}"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{32,}\b"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{32,}\b"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
)


class PatchErrorCode(str, Enum):
    INPUT_SCHEMA_INVALID = "INPUT_SCHEMA_INVALID"
    OPERATION_KEY_INVALID = "OPERATION_KEY_INVALID"
    REPOSITORY_INVALID = "REPOSITORY_INVALID"
    BRANCH_INVALID = "BRANCH_INVALID"
    PROTECTED_BRANCH_REFUSED = "PROTECTED_BRANCH_REFUSED"
    EXPECTED_HEAD_INVALID = "EXPECTED_HEAD_INVALID"
    FILE_COUNT_REFUSED = "FILE_COUNT_REFUSED"
    DUPLICATE_PATH = "DUPLICATE_PATH"
    PATH_INVALID = "PATH_INVALID"
    PATH_NOT_OWNED = "PATH_NOT_OWNED"
    MATERIALIZED_FILE_SET_MISMATCH = "MATERIALIZED_FILE_SET_MISMATCH"
    BLOB_OID_INVALID = "BLOB_OID_INVALID"
    BLOB_OID_MISMATCH = "BLOB_OID_MISMATCH"
    SOURCE_TYPE_REFUSED = "SOURCE_TYPE_REFUSED"
    SOURCE_EMPTY_REFUSED = "SOURCE_EMPTY_REFUSED"
    SOURCE_TOO_LARGE = "SOURCE_TOO_LARGE"
    SOURCE_NUL_REFUSED = "SOURCE_NUL_REFUSED"
    SOURCE_CRLF_REFUSED = "SOURCE_CRLF_REFUSED"
    SOURCE_FINAL_NEWLINE_REQUIRED = "SOURCE_FINAL_NEWLINE_REQUIRED"
    PATCH_TYPE_REFUSED = "PATCH_TYPE_REFUSED"
    PATCH_TOO_LARGE = "PATCH_TOO_LARGE"
    PATCH_NUL_REFUSED = "PATCH_NUL_REFUSED"
    PATCH_CRLF_REFUSED = "PATCH_CRLF_REFUSED"
    PATCH_FINAL_NEWLINE_REQUIRED = "PATCH_FINAL_NEWLINE_REQUIRED"
    PATCH_HEADER_INVALID = "PATCH_HEADER_INVALID"
    PATCH_PATH_MISMATCH = "PATCH_PATH_MISMATCH"
    HUNK_HEADER_INVALID = "HUNK_HEADER_INVALID"
    HUNK_BODY_INVALID = "HUNK_BODY_INVALID"
    HUNK_COUNT_MISMATCH = "HUNK_COUNT_MISMATCH"
    HUNK_ANCHOR_REQUIRED = "HUNK_ANCHOR_REQUIRED"
    HUNK_ORDER_INVALID = "HUNK_ORDER_INVALID"
    HUNK_RANGE_INVALID = "HUNK_RANGE_INVALID"
    HUNK_CONTEXT_MISMATCH = "HUNK_CONTEXT_MISMATCH"
    HUNK_NEW_POSITION_MISMATCH = "HUNK_NEW_POSITION_MISMATCH"
    HUNK_LIMIT_EXCEEDED = "HUNK_LIMIT_EXCEEDED"
    CHANGE_LIMIT_EXCEEDED = "CHANGE_LIMIT_EXCEEDED"
    RESULT_TOO_LARGE = "RESULT_TOO_LARGE"
    SECRET_SHAPE_REFUSED = "SECRET_SHAPE_REFUSED"
    NO_EFFECT = "NO_EFFECT"


class BranchPatchError(ValueError):
    """Stable payload-free refusal from the pure patch kernel."""

    def __init__(self, code: PatchErrorCode) -> None:
        self.code = code
        super().__init__(code.value)


@dataclasses.dataclass(frozen=True)
class PatchFileIntent:
    path: str
    expected_blob_oid: str
    unified_diff: str


@dataclasses.dataclass(frozen=True)
class BranchPatchInput:
    schema: str
    operation_key: str
    repository: str
    branch: str
    expected_head_oid: str
    files: tuple[PatchFileIntent, ...]


@dataclasses.dataclass(frozen=True)
class MaterializedFile:
    path: str
    observed_blob_oid: str
    content: str


@dataclasses.dataclass(frozen=True)
class PreparedFilePatch:
    path: str
    expected_blob_oid: str
    before_sha256: str
    after_sha256: str
    patch_sha256: str
    before_bytes: int
    after_bytes: int
    additions: int
    deletions: int
    hunk_count: int
    result_content: str = dataclasses.field(repr=False)

    def public_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "expected_blob_oid": self.expected_blob_oid,
            "before_sha256": self.before_sha256,
            "after_sha256": self.after_sha256,
            "patch_sha256": self.patch_sha256,
            "before_bytes": self.before_bytes,
            "after_bytes": self.after_bytes,
            "additions": self.additions,
            "deletions": self.deletions,
            "hunk_count": self.hunk_count,
        }


@dataclasses.dataclass(frozen=True)
class BranchPatchPreparation:
    schema: str
    operation_key: str
    repository: str
    branch: str
    expected_head_oid: str
    files: tuple[PreparedFilePatch, ...]
    total_additions: int
    total_deletions: int
    normalized_effect_digest: str

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "operation_key": self.operation_key,
            "repository": self.repository,
            "branch": self.branch,
            "expected_head_oid": self.expected_head_oid,
            "files": [item.public_dict() for item in self.files],
            "total_additions": self.total_additions,
            "total_deletions": self.total_deletions,
            "normalized_effect_digest": self.normalized_effect_digest,
        }


@dataclasses.dataclass(frozen=True)
class _Hunk:
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    lines: tuple[tuple[str, str], ...]


@dataclasses.dataclass(frozen=True)
class _AppliedPatch:
    result_content: str
    additions: int
    deletions: int
    hunk_count: int


def _refuse(code: PatchErrorCode) -> None:
    raise BranchPatchError(code)


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def git_blob_oid(content: str, *, algorithm: str = "sha1") -> str:
    """Return the Git object ID for UTF-8 text under SHA-1 or SHA-256."""

    raw = content.encode("utf-8")
    framed = b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw
    if algorithm == "sha1":
        return hashlib.sha1(framed, usedforsecurity=False).hexdigest()
    if algorithm == "sha256":
        return hashlib.sha256(framed).hexdigest()
    raise ValueError("algorithm must be sha1 or sha256")


def _validate_path(value: object) -> str:
    if not isinstance(value, str):
        _refuse(PatchErrorCode.PATH_INVALID)
    path = value
    try:
        encoded = path.encode("utf-8")
    except UnicodeError:
        _refuse(PatchErrorCode.PATH_INVALID)
    if not path or len(encoded) > MAX_PATH_BYTES:
        _refuse(PatchErrorCode.PATH_INVALID)
    if path.startswith("/") or path.endswith("/") or "\\" in path or "//" in path:
        _refuse(PatchErrorCode.PATH_INVALID)
    if any(ord(char) < 32 or ord(char) == 127 for char in path):
        _refuse(PatchErrorCode.PATH_INVALID)
    parts = path.split("/")
    if any(part in {"", ".", "..", ".git"} for part in parts):
        _refuse(PatchErrorCode.PATH_INVALID)
    return path


def _validate_oid(value: object, code: PatchErrorCode) -> str:
    if not isinstance(value, str) or _OID_RE.fullmatch(value) is None:
        _refuse(code)
    return value


def _validate_request(
    request: BranchPatchInput,
    *,
    allowed_paths: frozenset[str],
    protected_branches: frozenset[str],
) -> tuple[PatchFileIntent, ...]:
    if request.schema != INPUT_SCHEMA:
        _refuse(PatchErrorCode.INPUT_SCHEMA_INVALID)
    if not isinstance(request.operation_key, str) or _OPERATION_RE.fullmatch(request.operation_key) is None:
        _refuse(PatchErrorCode.OPERATION_KEY_INVALID)
    if not isinstance(request.repository, str) or _REPOSITORY_RE.fullmatch(request.repository) is None:
        _refuse(PatchErrorCode.REPOSITORY_INVALID)
    if request.repository.split("/")[-1] in {".", ".."}:
        _refuse(PatchErrorCode.REPOSITORY_INVALID)
    if (
        not isinstance(request.branch, str)
        or _BRANCH_RE.fullmatch(request.branch) is None
        or request.branch.startswith("-")
        or request.branch.endswith(".")
        or ".." in request.branch
        or "//" in request.branch
        or "@{" in request.branch
        or request.branch.endswith(".lock")
    ):
        _refuse(PatchErrorCode.BRANCH_INVALID)
    if request.branch in protected_branches:
        _refuse(PatchErrorCode.PROTECTED_BRANCH_REFUSED)
    _validate_oid(request.expected_head_oid, PatchErrorCode.EXPECTED_HEAD_INVALID)
    if not isinstance(request.files, tuple) or not 1 <= len(request.files) <= MAX_FILES:
        _refuse(PatchErrorCode.FILE_COUNT_REFUSED)

    validated: list[PatchFileIntent] = []
    seen: set[str] = set()
    for item in request.files:
        if not isinstance(item, PatchFileIntent):
            _refuse(PatchErrorCode.FILE_COUNT_REFUSED)
        path = _validate_path(item.path)
        if path in seen:
            _refuse(PatchErrorCode.DUPLICATE_PATH)
        if path not in allowed_paths:
            _refuse(PatchErrorCode.PATH_NOT_OWNED)
        seen.add(path)
        _validate_oid(item.expected_blob_oid, PatchErrorCode.BLOB_OID_INVALID)
        validated.append(item)
    return tuple(sorted(validated, key=lambda row: row.path))


def _validate_source(materialized: MaterializedFile, expected_blob_oid: str) -> tuple[str, bytes]:
    if not isinstance(materialized, MaterializedFile) or not isinstance(materialized.content, str):
        _refuse(PatchErrorCode.SOURCE_TYPE_REFUSED)
    if materialized.content == "":
        _refuse(PatchErrorCode.SOURCE_EMPTY_REFUSED)
    if "\0" in materialized.content:
        _refuse(PatchErrorCode.SOURCE_NUL_REFUSED)
    if "\r" in materialized.content:
        _refuse(PatchErrorCode.SOURCE_CRLF_REFUSED)
    if not materialized.content.endswith("\n"):
        _refuse(PatchErrorCode.SOURCE_FINAL_NEWLINE_REQUIRED)
    raw = materialized.content.encode("utf-8")
    if len(raw) > MAX_SOURCE_BYTES_PER_FILE:
        _refuse(PatchErrorCode.SOURCE_TOO_LARGE)

    observed = _validate_oid(materialized.observed_blob_oid, PatchErrorCode.BLOB_OID_INVALID)
    if observed != expected_blob_oid:
        _refuse(PatchErrorCode.BLOB_OID_MISMATCH)
    algorithm = "sha1" if len(observed) == 40 else "sha256"
    if git_blob_oid(materialized.content, algorithm=algorithm) != observed:
        _refuse(PatchErrorCode.BLOB_OID_MISMATCH)
    return materialized.content, raw


def _parse_unified_diff(path: str, value: object) -> tuple[_Hunk, ...]:
    if not isinstance(value, str):
        _refuse(PatchErrorCode.PATCH_TYPE_REFUSED)
    if "\0" in value:
        _refuse(PatchErrorCode.PATCH_NUL_REFUSED)
    if "\r" in value:
        _refuse(PatchErrorCode.PATCH_CRLF_REFUSED)
    if not value.endswith("\n"):
        _refuse(PatchErrorCode.PATCH_FINAL_NEWLINE_REQUIRED)
    if len(value.encode("utf-8")) > MAX_PATCH_BYTES_PER_FILE:
        _refuse(PatchErrorCode.PATCH_TOO_LARGE)

    lines = value[:-1].split("\n")
    if len(lines) < 3 or lines[0] != f"--- a/{path}" or lines[1] != f"+++ b/{path}":
        if len(lines) >= 2 and (lines[0].startswith("--- ") or lines[1].startswith("+++ ")):
            _refuse(PatchErrorCode.PATCH_PATH_MISMATCH)
        _refuse(PatchErrorCode.PATCH_HEADER_INVALID)

    hunks: list[_Hunk] = []
    index = 2
    while index < len(lines):
        if len(hunks) >= MAX_HUNKS_PER_FILE:
            _refuse(PatchErrorCode.HUNK_LIMIT_EXCEEDED)
        match = _HUNK_RE.fullmatch(lines[index])
        if match is None:
            _refuse(PatchErrorCode.HUNK_HEADER_INVALID)
        old_start = int(match.group("old_start"))
        old_count = int(match.group("old_count") or "1")
        new_start = int(match.group("new_start"))
        new_count = int(match.group("new_count") or "1")
        if (old_start == 0 and old_count != 0) or (new_start == 0 and new_count != 0):
            _refuse(PatchErrorCode.HUNK_HEADER_INVALID)

        index += 1
        body: list[tuple[str, str]] = []
        while index < len(lines) and not lines[index].startswith("@@ "):
            line = lines[index]
            if not line or line[0] not in {" ", "+", "-"}:
                _refuse(PatchErrorCode.HUNK_BODY_INVALID)
            body.append((line[0], line[1:]))
            index += 1
        if not body:
            _refuse(PatchErrorCode.HUNK_BODY_INVALID)

        observed_old = sum(prefix in {" ", "-"} for prefix, _ in body)
        observed_new = sum(prefix in {" ", "+"} for prefix, _ in body)
        if observed_old != old_count or observed_new != new_count:
            _refuse(PatchErrorCode.HUNK_COUNT_MISMATCH)
        if not any(prefix in {" ", "-"} for prefix, _ in body):
            _refuse(PatchErrorCode.HUNK_ANCHOR_REQUIRED)
        if not any(prefix in {"+", "-"} for prefix, _ in body):
            _refuse(PatchErrorCode.NO_EFFECT)

        hunks.append(
            _Hunk(
                old_start=old_start,
                old_count=old_count,
                new_start=new_start,
                new_count=new_count,
                lines=tuple(body),
            )
        )
    return tuple(hunks)


def _apply_hunks(source: str, hunks: tuple[_Hunk, ...]) -> _AppliedPatch:
    source_lines = source[:-1].split("\n")
    output: list[str] = []
    source_cursor = 0
    additions = 0
    deletions = 0

    for hunk in hunks:
        old_index = hunk.old_start - 1 if hunk.old_count else hunk.old_start
        new_index = hunk.new_start - 1 if hunk.new_count else hunk.new_start
        if old_index < source_cursor:
            _refuse(PatchErrorCode.HUNK_ORDER_INVALID)
        if old_index > len(source_lines):
            _refuse(PatchErrorCode.HUNK_RANGE_INVALID)

        output.extend(source_lines[source_cursor:old_index])
        if len(output) != new_index:
            _refuse(PatchErrorCode.HUNK_NEW_POSITION_MISMATCH)
        source_cursor = old_index

        for prefix, text in hunk.lines:
            if prefix in {" ", "-"}:
                if source_cursor >= len(source_lines):
                    _refuse(PatchErrorCode.HUNK_RANGE_INVALID)
                if source_lines[source_cursor] != text:
                    _refuse(PatchErrorCode.HUNK_CONTEXT_MISMATCH)
                if prefix == " ":
                    output.append(text)
                else:
                    deletions += 1
                source_cursor += 1
            elif prefix == "+":
                output.append(text)
                additions += 1
            else:
                _refuse(PatchErrorCode.HUNK_BODY_INVALID)

    output.extend(source_lines[source_cursor:])
    result = "\n".join(output) + "\n"
    if result == source:
        _refuse(PatchErrorCode.NO_EFFECT)
    if additions + deletions > MAX_CHANGED_LINES_PER_FILE:
        _refuse(PatchErrorCode.CHANGE_LIMIT_EXCEEDED)
    for pattern in _SECRET_PATTERNS:
        for hunk in hunks:
            if any(prefix == "+" and pattern.search(text) for prefix, text in hunk.lines):
                _refuse(PatchErrorCode.SECRET_SHAPE_REFUSED)
    return _AppliedPatch(
        result_content=result,
        additions=additions,
        deletions=deletions,
        hunk_count=len(hunks),
    )


def prepare_branch_patch(
    request: BranchPatchInput,
    materialized_files: Mapping[str, MaterializedFile],
    *,
    allowed_paths: Iterable[str],
    protected_branches: Iterable[str] = ("master", "main"),
) -> BranchPatchPreparation:
    """Strictly prepare resultant content for one owner-authorized branch patch.

    ``allowed_paths`` and ``protected_branches`` are server/owner facts, not
    model-authored policy. The returned object contains resultant file content
    for the owner-native commit port, while :meth:`public_dict` omits that
    content from model-visible receipts.
    """

    if not isinstance(request, BranchPatchInput) or not isinstance(materialized_files, Mapping):
        _refuse(PatchErrorCode.INPUT_SCHEMA_INVALID)

    allowed = frozenset(_validate_path(path) for path in allowed_paths)
    protected = frozenset(str(branch) for branch in protected_branches)
    intents = _validate_request(request, allowed_paths=allowed, protected_branches=protected)

    expected_paths = {item.path for item in intents}
    if set(materialized_files) != expected_paths:
        _refuse(PatchErrorCode.MATERIALIZED_FILE_SET_MISMATCH)

    prepared: list[PreparedFilePatch] = []
    total_patch_bytes = 0
    total_additions = 0
    total_deletions = 0

    for intent in intents:
        materialized = materialized_files[intent.path]
        if materialized.path != intent.path:
            _refuse(PatchErrorCode.MATERIALIZED_FILE_SET_MISMATCH)
        source, source_raw = _validate_source(materialized, intent.expected_blob_oid)
        patch_raw = intent.unified_diff.encode("utf-8") if isinstance(intent.unified_diff, str) else b""
        total_patch_bytes += len(patch_raw)
        if total_patch_bytes > MAX_PATCH_BYTES_TOTAL:
            _refuse(PatchErrorCode.PATCH_TOO_LARGE)

        hunks = _parse_unified_diff(intent.path, intent.unified_diff)
        applied = _apply_hunks(source, hunks)
        result_raw = applied.result_content.encode("utf-8")
        if len(result_raw) > MAX_RESULT_BYTES_PER_FILE:
            _refuse(PatchErrorCode.RESULT_TOO_LARGE)

        total_additions += applied.additions
        total_deletions += applied.deletions
        if total_additions + total_deletions > MAX_CHANGED_LINES_TOTAL:
            _refuse(PatchErrorCode.CHANGE_LIMIT_EXCEEDED)

        prepared.append(
            PreparedFilePatch(
                path=intent.path,
                expected_blob_oid=intent.expected_blob_oid,
                before_sha256=_sha256(source_raw),
                after_sha256=_sha256(result_raw),
                patch_sha256=_sha256(patch_raw),
                before_bytes=len(source_raw),
                after_bytes=len(result_raw),
                additions=applied.additions,
                deletions=applied.deletions,
                hunk_count=applied.hunk_count,
                result_content=applied.result_content,
            )
        )

    prepared_tuple = tuple(sorted(prepared, key=lambda row: row.path))
    normalized_effect = {
        "schema": PREVIEW_SCHEMA,
        "operation_key": request.operation_key,
        "repository": request.repository,
        "branch": request.branch,
        "expected_head_oid": request.expected_head_oid,
        "files": [item.public_dict() for item in prepared_tuple],
        "total_additions": total_additions,
        "total_deletions": total_deletions,
    }
    return BranchPatchPreparation(
        schema=PREVIEW_SCHEMA,
        operation_key=request.operation_key,
        repository=request.repository,
        branch=request.branch,
        expected_head_oid=request.expected_head_oid,
        files=prepared_tuple,
        total_additions=total_additions,
        total_deletions=total_deletions,
        normalized_effect_digest=_sha256(_canonical_bytes(normalized_effect)),
    )


__all__ = [
    "INPUT_SCHEMA",
    "PREVIEW_SCHEMA",
    "MAX_CHANGED_LINES_PER_FILE",
    "MAX_CHANGED_LINES_TOTAL",
    "MAX_FILES",
    "MAX_HUNKS_PER_FILE",
    "MAX_PATCH_BYTES_PER_FILE",
    "MAX_PATCH_BYTES_TOTAL",
    "MAX_RESULT_BYTES_PER_FILE",
    "MAX_SOURCE_BYTES_PER_FILE",
    "BranchPatchError",
    "BranchPatchInput",
    "BranchPatchPreparation",
    "MaterializedFile",
    "PatchErrorCode",
    "PatchFileIntent",
    "PreparedFilePatch",
    "git_blob_oid",
    "prepare_branch_patch",
]
