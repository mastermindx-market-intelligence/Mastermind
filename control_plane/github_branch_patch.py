"""Pure, deterministic strict materialization for one GitHub branch-file patch.

This module is intentionally transport-free. A trusted owner must acquire the exact
repository, branch head, and complete Git blob, then pass those immutable facts here.
The model-facing layer must never expose ``materialized_bytes``; it should return only
``public_receipt()`` and bind the complete materialization into an owner-local prepared
action token.

The kernel performs no I/O, network access, mutation, credential selection, clock
access, subprocess work, filesystem discovery, persistence, fuzzy hunk placement, or
three-way merge.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import re
from enum import Enum
from pathlib import PurePosixPath
from typing import Any


INPUT_SCHEMA = "mastermind.github_branch_patch.input.v1"
OUTPUT_SCHEMA = "mastermind.github_branch_patch.materialization.v1"
PUBLIC_RECEIPT_SCHEMA = "mastermind.github_branch_patch.preview.v1"

MAX_SOURCE_BYTES = 8 * 1024 * 1024
MAX_RESULT_BYTES = 8 * 1024 * 1024
MAX_PATCH_BYTES = 128 * 1024
MAX_HUNKS = 32
MAX_CHANGED_LINES = 512
MAX_PATH_BYTES = 1024
MAX_OPERATION_BYTES = 192

_SHA1_RE = re.compile(r"^[0-9a-f]{40}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}$")
_REF_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,255}$")
_OPERATION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,191}$")
_HUNK_RE = re.compile(
    r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(?: [^\r\n]*)?\n$"
)

_HIGH_CONFIDENCE_SECRET_PATTERNS = (
    re.compile(r"github_pat_[A-Za-z0-9_]{20,}", re.IGNORECASE),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}", re.IGNORECASE),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}", re.IGNORECASE),
    re.compile(r"\bsk-[A-Za-z0-9]{20,}", re.IGNORECASE),
    re.compile(
        r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
        re.IGNORECASE,
    ),
)


class BranchPatchIssue(str, Enum):
    INPUT_SCHEMA_INVALID = "INPUT_SCHEMA_INVALID"
    INPUT_INVALID = "INPUT_INVALID"
    PATH_INVALID = "PATH_INVALID"
    PATH_MISMATCH = "PATH_MISMATCH"
    SOURCE_LIMIT_EXCEEDED = "SOURCE_LIMIT_EXCEEDED"
    SOURCE_FORMAT_UNSUPPORTED = "SOURCE_FORMAT_UNSUPPORTED"
    SOURCE_BLOB_MISMATCH = "SOURCE_BLOB_MISMATCH"
    PATCH_LIMIT_EXCEEDED = "PATCH_LIMIT_EXCEEDED"
    PATCH_FORMAT_INVALID = "PATCH_FORMAT_INVALID"
    HUNK_LIMIT_EXCEEDED = "HUNK_LIMIT_EXCEEDED"
    CHANGED_LINE_LIMIT_EXCEEDED = "CHANGED_LINE_LIMIT_EXCEEDED"
    HUNK_ORDER_INVALID = "HUNK_ORDER_INVALID"
    HUNK_RANGE_INVALID = "HUNK_RANGE_INVALID"
    HUNK_CONTEXT_MISMATCH = "HUNK_CONTEXT_MISMATCH"
    SECRET_SHAPED_ADDITION = "SECRET_SHAPED_ADDITION"
    RESULT_LIMIT_EXCEEDED = "RESULT_LIMIT_EXCEEDED"
    NO_CHANGE = "NO_CHANGE"


class BranchPatchError(ValueError):
    """Stable, payload-free refusal from the strict patch kernel."""

    def __init__(self, issue: BranchPatchIssue) -> None:
        self.issue = issue
        super().__init__(issue.value)


@dataclasses.dataclass(frozen=True)
class BranchPatchInput:
    schema: str
    operation_key: str
    repository: str
    branch: str
    path: str
    expected_head_sha: str
    expected_blob_sha: str
    source_bytes: bytes
    patch: str


@dataclasses.dataclass(frozen=True)
class BranchPatchMaterialization:
    schema: str
    operation_key: str
    repository: str
    branch: str
    path: str
    expected_head_sha: str
    source_blob_sha: str
    source_sha256: str
    patch_sha256: str
    result_sha256: str
    source_bytes_length: int
    result_bytes_length: int
    hunk_count: int
    added_line_count: int
    removed_line_count: int
    canonical_digest: str
    materialized_bytes: bytes = dataclasses.field(repr=False)

    def public_receipt(self) -> dict[str, Any]:
        """Return the bounded secret-free preview; never expose full file bytes."""

        return {
            "schema": PUBLIC_RECEIPT_SCHEMA,
            "operation_key": self.operation_key,
            "repository": self.repository,
            "branch": self.branch,
            "path": self.path,
            "expected_head_sha": self.expected_head_sha,
            "source_blob_sha": self.source_blob_sha,
            "source_sha256": self.source_sha256,
            "patch_sha256": self.patch_sha256,
            "result_sha256": self.result_sha256,
            "source_bytes_length": self.source_bytes_length,
            "result_bytes_length": self.result_bytes_length,
            "hunk_count": self.hunk_count,
            "added_line_count": self.added_line_count,
            "removed_line_count": self.removed_line_count,
            "canonical_digest": self.canonical_digest,
        }


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def git_blob_sha(source_bytes: bytes) -> str:
    """Compute the canonical SHA-1 object id used by ordinary GitHub Git blobs."""

    payload = b"blob " + str(len(source_bytes)).encode("ascii") + b"\0" + source_bytes
    try:
        digest = hashlib.sha1(payload, usedforsecurity=False)
    except TypeError:  # pragma: no cover - compatibility with older Python builds
        digest = hashlib.sha1(payload)
    return digest.hexdigest()


def _validate_path(path: str) -> str:
    if not isinstance(path, str):
        raise BranchPatchError(BranchPatchIssue.PATH_INVALID)
    encoded = path.encode("utf-8", errors="strict")
    if not encoded or len(encoded) > MAX_PATH_BYTES or "\\" in path or "\x00" in path:
        raise BranchPatchError(BranchPatchIssue.PATH_INVALID)
    candidate = PurePosixPath(path)
    if (
        candidate.is_absolute()
        or str(candidate) != path
        or path.endswith("/")
        or any(part in {"", ".", ".."} for part in candidate.parts)
        or candidate.parts[0] == ".git"
    ):
        raise BranchPatchError(BranchPatchIssue.PATH_INVALID)
    return path


def _validate_input(value: BranchPatchInput) -> None:
    if not isinstance(value, BranchPatchInput):
        raise BranchPatchError(BranchPatchIssue.INPUT_INVALID)
    if value.schema != INPUT_SCHEMA:
        raise BranchPatchError(BranchPatchIssue.INPUT_SCHEMA_INVALID)
    if (
        not isinstance(value.operation_key, str)
        or len(value.operation_key.encode("utf-8")) > MAX_OPERATION_BYTES
        or _OPERATION_RE.fullmatch(value.operation_key) is None
        or not isinstance(value.repository, str)
        or _REPOSITORY_RE.fullmatch(value.repository) is None
        or not isinstance(value.branch, str)
        or _REF_RE.fullmatch(value.branch) is None
        or value.branch.startswith("refs/")
        or _SHA1_RE.fullmatch(value.expected_head_sha) is None
        or _SHA1_RE.fullmatch(value.expected_blob_sha) is None
        or not isinstance(value.source_bytes, bytes)
        or not isinstance(value.patch, str)
    ):
        raise BranchPatchError(BranchPatchIssue.INPUT_INVALID)
    _validate_path(value.path)


def _range_index(start: int, count: int) -> int:
    if start < 0 or count < 0:
        raise BranchPatchError(BranchPatchIssue.HUNK_RANGE_INVALID)
    if count == 0:
        return start
    if start == 0:
        raise BranchPatchError(BranchPatchIssue.HUNK_RANGE_INVALID)
    return start - 1


def _scan_addition(line: str) -> None:
    for pattern in _HIGH_CONFIDENCE_SECRET_PATTERNS:
        if pattern.search(line):
            raise BranchPatchError(BranchPatchIssue.SECRET_SHAPED_ADDITION)


def apply_strict_unified_patch(value: BranchPatchInput) -> BranchPatchMaterialization:
    """Apply one exact-path unified patch with zero offset, fuzz, or merge behavior."""

    _validate_input(value)

    source = value.source_bytes
    if len(source) > MAX_SOURCE_BYTES:
        raise BranchPatchError(BranchPatchIssue.SOURCE_LIMIT_EXCEEDED)
    if b"\x00" in source or b"\r" in source or (source and not source.endswith(b"\n")):
        raise BranchPatchError(BranchPatchIssue.SOURCE_FORMAT_UNSUPPORTED)
    try:
        source_text = source.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise BranchPatchError(BranchPatchIssue.SOURCE_FORMAT_UNSUPPORTED) from exc

    observed_blob_sha = git_blob_sha(source)
    if observed_blob_sha != value.expected_blob_sha:
        raise BranchPatchError(BranchPatchIssue.SOURCE_BLOB_MISMATCH)

    try:
        patch_bytes = value.patch.encode("utf-8", errors="strict")
    except UnicodeEncodeError as exc:
        raise BranchPatchError(BranchPatchIssue.PATCH_FORMAT_INVALID) from exc
    if len(patch_bytes) > MAX_PATCH_BYTES:
        raise BranchPatchError(BranchPatchIssue.PATCH_LIMIT_EXCEEDED)
    if not patch_bytes or b"\x00" in patch_bytes or b"\r" in patch_bytes:
        raise BranchPatchError(BranchPatchIssue.PATCH_FORMAT_INVALID)
    if not patch_bytes.endswith(b"\n"):
        raise BranchPatchError(BranchPatchIssue.PATCH_FORMAT_INVALID)

    patch_lines = value.patch.splitlines(keepends=True)
    expected_old = f"--- a/{value.path}\n"
    expected_new = f"+++ b/{value.path}\n"
    if len(patch_lines) < 3 or patch_lines[0] != expected_old or patch_lines[1] != expected_new:
        if len(patch_lines) >= 2 and (
            patch_lines[0].startswith("--- ") or patch_lines[1].startswith("+++ ")
        ):
            raise BranchPatchError(BranchPatchIssue.PATH_MISMATCH)
        raise BranchPatchError(BranchPatchIssue.PATCH_FORMAT_INVALID)

    source_lines = source_text.splitlines(keepends=True)
    result_lines: list[str] = []
    source_cursor = 0
    hunk_count = 0
    added_line_count = 0
    removed_line_count = 0
    line_index = 2

    while line_index < len(patch_lines):
        header = patch_lines[line_index]
        match = _HUNK_RE.fullmatch(header)
        if match is None:
            raise BranchPatchError(BranchPatchIssue.PATCH_FORMAT_INVALID)
        hunk_count += 1
        if hunk_count > MAX_HUNKS:
            raise BranchPatchError(BranchPatchIssue.HUNK_LIMIT_EXCEEDED)

        old_start = int(match.group(1))
        old_count = int(match.group(2) or "1")
        new_start = int(match.group(3))
        new_count = int(match.group(4) or "1")
        old_index = _range_index(old_start, old_count)
        new_index = _range_index(new_start, new_count)
        if old_index < source_cursor or old_index > len(source_lines):
            raise BranchPatchError(BranchPatchIssue.HUNK_ORDER_INVALID)
        if new_index != len(result_lines) + (old_index - source_cursor):
            raise BranchPatchError(BranchPatchIssue.HUNK_RANGE_INVALID)

        result_lines.extend(source_lines[source_cursor:old_index])
        pointer = old_index
        old_seen = 0
        new_seen = 0
        line_index += 1

        if line_index >= len(patch_lines) or patch_lines[line_index].startswith("@@ "):
            if old_count != 0 or new_count != 0:
                raise BranchPatchError(BranchPatchIssue.PATCH_FORMAT_INVALID)

        while line_index < len(patch_lines) and not patch_lines[line_index].startswith("@@ "):
            patch_line = patch_lines[line_index]
            if not patch_line.endswith("\n") or patch_line == "\\ No newline at end of file\n":
                raise BranchPatchError(BranchPatchIssue.PATCH_FORMAT_INVALID)
            prefix = patch_line[:1]
            body = patch_line[1:]
            if prefix == " ":
                if pointer >= len(source_lines) or source_lines[pointer] != body:
                    raise BranchPatchError(BranchPatchIssue.HUNK_CONTEXT_MISMATCH)
                result_lines.append(body)
                pointer += 1
                old_seen += 1
                new_seen += 1
            elif prefix == "-":
                if pointer >= len(source_lines) or source_lines[pointer] != body:
                    raise BranchPatchError(BranchPatchIssue.HUNK_CONTEXT_MISMATCH)
                pointer += 1
                old_seen += 1
                removed_line_count += 1
            elif prefix == "+":
                _scan_addition(body)
                result_lines.append(body)
                new_seen += 1
                added_line_count += 1
            else:
                raise BranchPatchError(BranchPatchIssue.PATCH_FORMAT_INVALID)
            if added_line_count + removed_line_count > MAX_CHANGED_LINES:
                raise BranchPatchError(BranchPatchIssue.CHANGED_LINE_LIMIT_EXCEEDED)
            line_index += 1

        if old_seen != old_count or new_seen != new_count:
            raise BranchPatchError(BranchPatchIssue.HUNK_RANGE_INVALID)
        source_cursor = pointer

    if hunk_count == 0:
        raise BranchPatchError(BranchPatchIssue.PATCH_FORMAT_INVALID)

    result_lines.extend(source_lines[source_cursor:])
    result = "".join(result_lines).encode("utf-8")
    if len(result) > MAX_RESULT_BYTES:
        raise BranchPatchError(BranchPatchIssue.RESULT_LIMIT_EXCEEDED)
    if result == source:
        raise BranchPatchError(BranchPatchIssue.NO_CHANGE)

    source_sha256 = _sha256(source)
    patch_sha256 = _sha256(patch_bytes)
    result_sha256 = _sha256(result)
    public_core = {
        "schema": OUTPUT_SCHEMA,
        "operation_key": value.operation_key,
        "repository": value.repository,
        "branch": value.branch,
        "path": value.path,
        "expected_head_sha": value.expected_head_sha,
        "source_blob_sha": observed_blob_sha,
        "source_sha256": source_sha256,
        "patch_sha256": patch_sha256,
        "result_sha256": result_sha256,
        "source_bytes_length": len(source),
        "result_bytes_length": len(result),
        "hunk_count": hunk_count,
        "added_line_count": added_line_count,
        "removed_line_count": removed_line_count,
    }
    canonical_digest = _sha256(_canonical_bytes(public_core))
    if _SHA256_RE.fullmatch(canonical_digest) is None:
        raise AssertionError("invalid canonical digest")

    return BranchPatchMaterialization(
        **public_core,
        canonical_digest=canonical_digest,
        materialized_bytes=result,
    )


__all__ = [
    "INPUT_SCHEMA",
    "OUTPUT_SCHEMA",
    "PUBLIC_RECEIPT_SCHEMA",
    "BranchPatchError",
    "BranchPatchInput",
    "BranchPatchIssue",
    "BranchPatchMaterialization",
    "apply_strict_unified_patch",
    "git_blob_sha",
]
