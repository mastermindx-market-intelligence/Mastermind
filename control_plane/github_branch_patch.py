"""Pure, strict materialization for one existing GitHub text-file patch.

The caller is a trusted owner adapter that has already fetched the complete exact
blob.  Model-facing callers never supply ``original``.  This module performs no
I/O, network access, GitHub access, filesystem discovery, subprocess work, clock
access, randomness, mutation, credential selection, persistence, or retry.

It applies one bounded canonical unified diff at its declared positions with
zero fuzz and returns exact result bytes plus a secret-free deterministic
receipt.  Live GitHub prepare/commit/reconcile behavior belongs to a later
privilege-separated owner app.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import re
from enum import Enum
from typing import Final


MATERIALIZATION_SCHEMA: Final = "mastermind.github_branch_patch_materialization.v1"

_OPERATION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,191}$")
_PATH_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/@+\-]{0,239}$")
_OID_RE = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
_HUNK_RE = re.compile(
    r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(?: .*)?$"
)
_INDEX_RE = re.compile(
    r"^index ([0-9a-f]{4,64})\.\.([0-9a-f]{4,64})(?: ([0-7]{6}))?$"
)
_SECRET_PATTERNS = (
    re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b", re.IGNORECASE),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b", re.IGNORECASE),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{16,}\b", re.IGNORECASE),
    re.compile(r"\bsk-[A-Za-z0-9]{32,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bBearer [A-Za-z0-9._~-]{20,}\b", re.IGNORECASE),
)
_FORBIDDEN_METADATA_PREFIXES = (
    "new file mode ",
    "deleted file mode ",
    "old mode ",
    "new mode ",
    "similarity index ",
    "dissimilarity index ",
    "rename from ",
    "rename to ",
    "copy from ",
    "copy to ",
    "GIT binary patch",
    "Binary files ",
)


class PatchFailureCode(str, Enum):
    INPUT_INVALID = "INPUT_INVALID"
    OPERATION_KEY_INVALID = "OPERATION_KEY_INVALID"
    PATH_INVALID = "PATH_INVALID"
    BLOB_OID_INVALID = "BLOB_OID_INVALID"
    BLOB_MISMATCH = "BLOB_MISMATCH"
    ORIGINAL_TOO_LARGE = "ORIGINAL_TOO_LARGE"
    RESULT_TOO_LARGE = "RESULT_TOO_LARGE"
    PATCH_TOO_LARGE = "PATCH_TOO_LARGE"
    TEXT_ENCODING_UNSUPPORTED = "TEXT_ENCODING_UNSUPPORTED"
    LINE_ENDING_UNSUPPORTED = "LINE_ENDING_UNSUPPORTED"
    LINE_TOO_LONG = "LINE_TOO_LONG"
    PATCH_FORMAT_INVALID = "PATCH_FORMAT_INVALID"
    MULTI_FILE_PATCH_REFUSED = "MULTI_FILE_PATCH_REFUSED"
    FILE_OPERATION_REFUSED = "FILE_OPERATION_REFUSED"
    PATH_MISMATCH = "PATH_MISMATCH"
    HUNK_LIMIT_EXCEEDED = "HUNK_LIMIT_EXCEEDED"
    CHANGE_LIMIT_EXCEEDED = "CHANGE_LIMIT_EXCEEDED"
    HUNK_RANGE_INVALID = "HUNK_RANGE_INVALID"
    HUNK_COUNT_MISMATCH = "HUNK_COUNT_MISMATCH"
    HUNK_ORDER_INVALID = "HUNK_ORDER_INVALID"
    CONTEXT_MISMATCH = "CONTEXT_MISMATCH"
    SECRET_SHAPED_ADDITION = "SECRET_SHAPED_ADDITION"
    NO_CHANGE = "NO_CHANGE"


class PatchMaterializationError(ValueError):
    """A stable payload-free refusal from the strict patch materializer."""

    def __init__(self, code: PatchFailureCode) -> None:
        self.code = code
        super().__init__(code.value)


@dataclasses.dataclass(frozen=True)
class PatchLimits:
    max_original_bytes: int = 4 * 1024 * 1024
    max_result_bytes: int = 4 * 1024 * 1024
    max_patch_bytes: int = 128 * 1024
    max_patch_lines: int = 4096
    max_hunks: int = 16
    max_added_lines: int = 512
    max_deleted_lines: int = 512
    max_changed_lines: int = 768
    max_line_bytes: int = 64 * 1024

    def __post_init__(self) -> None:
        values = dataclasses.astuple(self)
        if any(type(value) is not int or value <= 0 for value in values):
            raise PatchMaterializationError(PatchFailureCode.INPUT_INVALID)


DEFAULT_LIMITS: Final = PatchLimits()


@dataclasses.dataclass(frozen=True)
class _HunkLine:
    operation: str
    text: str


@dataclasses.dataclass(frozen=True)
class _Hunk:
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    lines: tuple[_HunkLine, ...]


@dataclasses.dataclass(frozen=True)
class PatchMaterialization:
    schema: str
    operation_key: str
    path: str
    old_blob_oid: str
    new_blob_oid: str
    original_sha256: str
    result_sha256: str
    patch_sha256: str
    original_size: int
    result_size: int
    hunk_count: int
    addition_count: int
    deletion_count: int
    changed_line_count: int
    result: bytes = dataclasses.field(repr=False)

    def public_receipt(self) -> dict[str, object]:
        """Return the complete model-safe receipt; source and patch bytes are absent."""

        return {
            "schema": self.schema,
            "operation_key": self.operation_key,
            "path": self.path,
            "old_blob_oid": self.old_blob_oid,
            "new_blob_oid": self.new_blob_oid,
            "original_sha256": self.original_sha256,
            "result_sha256": self.result_sha256,
            "patch_sha256": self.patch_sha256,
            "original_size": self.original_size,
            "result_size": self.result_size,
            "hunk_count": self.hunk_count,
            "addition_count": self.addition_count,
            "deletion_count": self.deletion_count,
            "changed_line_count": self.changed_line_count,
        }

    def canonical_receipt_bytes(self) -> bytes:
        return (
            json.dumps(
                self.public_receipt(),
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=True,
                allow_nan=False,
            ).encode("utf-8")
            + b"\n"
        )


def _fail(code: PatchFailureCode) -> None:
    raise PatchMaterializationError(code)


def _validated_operation_key(value: object) -> str:
    if not isinstance(value, str) or _OPERATION_RE.fullmatch(value) is None:
        _fail(PatchFailureCode.OPERATION_KEY_INVALID)
    if len(value.encode("utf-8")) > 192:
        _fail(PatchFailureCode.OPERATION_KEY_INVALID)
    return value


def _validated_path(value: object) -> str:
    if not isinstance(value, str) or _PATH_RE.fullmatch(value) is None:
        _fail(PatchFailureCode.PATH_INVALID)
    if value.startswith("/") or "\\" in value or "//" in value:
        _fail(PatchFailureCode.PATH_INVALID)
    parts = value.split("/")
    if any(part in {"", ".", "..", ".git"} for part in parts):
        _fail(PatchFailureCode.PATH_INVALID)
    if len(value.encode("utf-8")) > 240:
        _fail(PatchFailureCode.PATH_INVALID)
    return value


def _validated_oid(value: object) -> str:
    if not isinstance(value, str) or _OID_RE.fullmatch(value) is None:
        _fail(PatchFailureCode.BLOB_OID_INVALID)
    return value


def _git_blob_oid(content: bytes, *, oid_length: int) -> str:
    framed = b"blob " + str(len(content)).encode("ascii") + b"\0" + content
    if oid_length == 40:
        return hashlib.sha1(framed, usedforsecurity=False).hexdigest()
    if oid_length == 64:
        return hashlib.sha256(framed).hexdigest()
    _fail(PatchFailureCode.BLOB_OID_INVALID)
    raise AssertionError("unreachable")


def _decode_source(original: bytes, *, limits: PatchLimits) -> tuple[str, list[str]]:
    if len(original) > limits.max_original_bytes:
        _fail(PatchFailureCode.ORIGINAL_TOO_LARGE)
    if b"\0" in original:
        _fail(PatchFailureCode.TEXT_ENCODING_UNSUPPORTED)
    try:
        text = original.decode("utf-8")
    except UnicodeDecodeError:
        _fail(PatchFailureCode.TEXT_ENCODING_UNSUPPORTED)
    if "\r" in text or not text.endswith("\n"):
        _fail(PatchFailureCode.LINE_ENDING_UNSUPPORTED)
    lines = text[:-1].split("\n")
    if any(len(line.encode("utf-8")) > limits.max_line_bytes for line in lines):
        _fail(PatchFailureCode.LINE_TOO_LONG)
    return text, lines


def _secret_shaped(value: str) -> bool:
    return any(pattern.search(value) is not None for pattern in _SECRET_PATTERNS)


def _validate_range(start: int, count: int) -> None:
    if start < 0 or count < 0:
        _fail(PatchFailureCode.HUNK_RANGE_INVALID)
    if count == 0:
        return
    if start == 0:
        _fail(PatchFailureCode.HUNK_RANGE_INVALID)


def _parse_diff(
    unified_diff: str,
    *,
    path: str,
    expected_blob_oid: str,
    limits: PatchLimits,
) -> tuple[tuple[_Hunk, ...], int, int, bytes]:
    if not isinstance(unified_diff, str):
        _fail(PatchFailureCode.INPUT_INVALID)
    if "\0" in unified_diff:
        _fail(PatchFailureCode.PATCH_FORMAT_INVALID)
    if "\r" in unified_diff or not unified_diff.endswith("\n"):
        _fail(PatchFailureCode.LINE_ENDING_UNSUPPORTED)
    try:
        patch_bytes = unified_diff.encode("utf-8")
    except UnicodeEncodeError:
        _fail(PatchFailureCode.TEXT_ENCODING_UNSUPPORTED)
    if len(patch_bytes) > limits.max_patch_bytes:
        _fail(PatchFailureCode.PATCH_TOO_LARGE)

    lines = unified_diff[:-1].split("\n")
    if not lines or len(lines) > limits.max_patch_lines:
        _fail(PatchFailureCode.PATCH_TOO_LARGE)
    if any(len(line.encode("utf-8")) > limits.max_line_bytes + 1 for line in lines):
        _fail(PatchFailureCode.LINE_TOO_LONG)

    index = 0
    expected_diff_header = f"diff --git a/{path} b/{path}"
    if lines[index].startswith("diff --git "):
        if lines[index] != expected_diff_header:
            _fail(PatchFailureCode.PATH_MISMATCH)
        index += 1
        seen_index = False
        while index < len(lines) and not lines[index].startswith("--- "):
            metadata = lines[index]
            if metadata.startswith(_FORBIDDEN_METADATA_PREFIXES):
                _fail(PatchFailureCode.FILE_OPERATION_REFUSED)
            match = _INDEX_RE.fullmatch(metadata)
            if match is None or seen_index:
                _fail(PatchFailureCode.PATCH_FORMAT_INVALID)
            old_oid, new_oid, mode = match.groups()
            if set(old_oid) == {"0"} or set(new_oid) == {"0"}:
                _fail(PatchFailureCode.FILE_OPERATION_REFUSED)
            if not expected_blob_oid.startswith(old_oid):
                _fail(PatchFailureCode.BLOB_MISMATCH)
            if mode is not None and mode != "100644":
                _fail(PatchFailureCode.FILE_OPERATION_REFUSED)
            seen_index = True
            index += 1

    if index + 2 > len(lines):
        _fail(PatchFailureCode.PATCH_FORMAT_INVALID)
    if lines[index] != f"--- a/{path}" or lines[index + 1] != f"+++ b/{path}":
        if lines[index].startswith("--- ") or lines[index + 1].startswith("+++ "):
            _fail(PatchFailureCode.PATH_MISMATCH)
        _fail(PatchFailureCode.PATCH_FORMAT_INVALID)
    index += 2

    hunks: list[_Hunk] = []
    total_added = 0
    total_deleted = 0

    while index < len(lines):
        header = lines[index]
        if header.startswith("diff --git ") or header.startswith("--- "):
            _fail(PatchFailureCode.MULTI_FILE_PATCH_REFUSED)
        match = _HUNK_RE.fullmatch(header)
        if match is None:
            if header.startswith(_FORBIDDEN_METADATA_PREFIXES):
                _fail(PatchFailureCode.FILE_OPERATION_REFUSED)
            _fail(PatchFailureCode.PATCH_FORMAT_INVALID)
        old_start = int(match.group(1))
        old_count = int(match.group(2)) if match.group(2) is not None else 1
        new_start = int(match.group(3))
        new_count = int(match.group(4)) if match.group(4) is not None else 1
        _validate_range(old_start, old_count)
        _validate_range(new_start, new_count)
        index += 1

        body: list[_HunkLine] = []
        old_seen = 0
        new_seen = 0
        while old_seen < old_count or new_seen < new_count:
            if index >= len(lines):
                _fail(PatchFailureCode.HUNK_COUNT_MISMATCH)
            raw = lines[index]
            if raw == "\\ No newline at end of file":
                _fail(PatchFailureCode.LINE_ENDING_UNSUPPORTED)
            if not raw or raw[0] not in {" ", "+", "-"}:
                _fail(PatchFailureCode.HUNK_COUNT_MISMATCH)
            operation = raw[0]
            value = raw[1:]
            if len(value.encode("utf-8")) > limits.max_line_bytes:
                _fail(PatchFailureCode.LINE_TOO_LONG)
            if operation == " ":
                old_seen += 1
                new_seen += 1
            elif operation == "-":
                old_seen += 1
                total_deleted += 1
            else:
                new_seen += 1
                total_added += 1
                if _secret_shaped(value):
                    _fail(PatchFailureCode.SECRET_SHAPED_ADDITION)
            if old_seen > old_count or new_seen > new_count:
                _fail(PatchFailureCode.HUNK_COUNT_MISMATCH)
            body.append(_HunkLine(operation=operation, text=value))
            index += 1

        if old_seen != old_count or new_seen != new_count:
            _fail(PatchFailureCode.HUNK_COUNT_MISMATCH)
        hunks.append(
            _Hunk(
                old_start=old_start,
                old_count=old_count,
                new_start=new_start,
                new_count=new_count,
                lines=tuple(body),
            )
        )
        if len(hunks) > limits.max_hunks:
            _fail(PatchFailureCode.HUNK_LIMIT_EXCEEDED)
        if (
            total_added > limits.max_added_lines
            or total_deleted > limits.max_deleted_lines
            or total_added + total_deleted > limits.max_changed_lines
        ):
            _fail(PatchFailureCode.CHANGE_LIMIT_EXCEEDED)

    if not hunks:
        _fail(PatchFailureCode.PATCH_FORMAT_INVALID)
    if total_added + total_deleted == 0:
        _fail(PatchFailureCode.NO_CHANGE)
    return tuple(hunks), total_added, total_deleted, patch_bytes


def _old_index(hunk: _Hunk) -> int:
    return hunk.old_start if hunk.old_count == 0 else hunk.old_start - 1


def _expected_new_start(output_line_count: int, hunk: _Hunk) -> int:
    return output_line_count if hunk.new_count == 0 else output_line_count + 1


def _apply_hunks(source: list[str], hunks: tuple[_Hunk, ...]) -> list[str]:
    output: list[str] = []
    cursor = 0

    for hunk in hunks:
        start = _old_index(hunk)
        if start < cursor:
            _fail(PatchFailureCode.HUNK_ORDER_INVALID)
        if start > len(source):
            _fail(PatchFailureCode.HUNK_RANGE_INVALID)

        output.extend(source[cursor:start])
        cursor = start
        if hunk.new_start != _expected_new_start(len(output), hunk):
            _fail(PatchFailureCode.HUNK_RANGE_INVALID)

        for item in hunk.lines:
            if item.operation in {" ", "-"}:
                if cursor >= len(source) or source[cursor] != item.text:
                    _fail(PatchFailureCode.CONTEXT_MISMATCH)
                if item.operation == " ":
                    output.append(item.text)
                cursor += 1
            else:
                output.append(item.text)

    output.extend(source[cursor:])
    return output


def materialize_strict_patch(
    *,
    operation_key: str,
    path: str,
    expected_blob_oid: str,
    original: bytes,
    unified_diff: str,
    limits: PatchLimits = DEFAULT_LIMITS,
) -> PatchMaterialization:
    """Materialize one exact existing-file patch or raise a stable refusal."""

    if not isinstance(limits, PatchLimits) or not isinstance(original, bytes):
        _fail(PatchFailureCode.INPUT_INVALID)
    operation = _validated_operation_key(operation_key)
    target_path = _validated_path(path)
    expected_oid = _validated_oid(expected_blob_oid)

    old_oid = _git_blob_oid(original, oid_length=len(expected_oid))
    if old_oid != expected_oid:
        _fail(PatchFailureCode.BLOB_MISMATCH)

    _source_text, source_lines = _decode_source(original, limits=limits)
    hunks, additions, deletions, patch_bytes = _parse_diff(
        unified_diff,
        path=target_path,
        expected_blob_oid=expected_oid,
        limits=limits,
    )
    result_lines = _apply_hunks(source_lines, hunks)
    if not result_lines:
        _fail(PatchFailureCode.LINE_ENDING_UNSUPPORTED)
    result = ("\n".join(result_lines) + "\n").encode("utf-8")
    if len(result) > limits.max_result_bytes:
        _fail(PatchFailureCode.RESULT_TOO_LARGE)
    if result == original:
        _fail(PatchFailureCode.NO_CHANGE)

    return PatchMaterialization(
        schema=MATERIALIZATION_SCHEMA,
        operation_key=operation,
        path=target_path,
        old_blob_oid=old_oid,
        new_blob_oid=_git_blob_oid(result, oid_length=len(expected_oid)),
        original_sha256=hashlib.sha256(original).hexdigest(),
        result_sha256=hashlib.sha256(result).hexdigest(),
        patch_sha256=hashlib.sha256(patch_bytes).hexdigest(),
        original_size=len(original),
        result_size=len(result),
        hunk_count=len(hunks),
        addition_count=additions,
        deletion_count=deletions,
        changed_line_count=additions + deletions,
        result=result,
    )


__all__ = [
    "DEFAULT_LIMITS",
    "MATERIALIZATION_SCHEMA",
    "PatchFailureCode",
    "PatchLimits",
    "PatchMaterialization",
    "PatchMaterializationError",
    "materialize_strict_patch",
]
