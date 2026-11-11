"""Pure plan-content comparison for already-captured AT28/33 planning bodies.

This module is a bounded, side-effect-free comparator over immutable bodies that
the caller already holds in memory. It never resolves a repository path, never
performs IO (no network, no filesystem, no Git, no clock, no credentials), and
never grants adoption, currency, or Job admission. ``base_source`` and
``candidate_sha256`` are plain data describing supplied bytes; they carry no
source-read authority of their own.

Result contract
---------------

An available result is a closed dict with exactly the keys::

    state, base_source, candidate_sha256, base_text, candidate_text,
    diff, identical, added_lines, removed_lines

with ``state == "AVAILABLE"``.

Every refused result is a closed dict of exactly::

    {"state": "UNAVAILABLE", "reason": <REASON>}

with one of four value-free reason codes:

``SOURCE_UNAVAILABLE``
    One or both bodies were supplied as ``None``. Metadata and digest shapes
    are still validated first.
``SOURCE_BYTES_MISMATCH``
    A supplied body's actual SHA-256 does not match its recorded digest, or a
    body is not valid UTF-8.
``INVALID_CONTENT``
    Malformed metadata or a body that is present but not ``bytes``.
``CONTENT_OVER_BUDGET``
    A body length outside its inclusive input range, or the serialized
    AVAILABLE result would exceed the fixed 65536-byte output budget. No
    partial diff or body is ever returned.

Ordinary malformed plain-data inputs never raise and never echo caller values;
only the closed reason is returned.
"""

import difflib
import hashlib
import json
import re

__all__ = ["compare_plan_content"]

_DIFF_FROM_LABEL = "recorded-base"
_DIFF_TO_LABEL = "proposal-candidate"
_DIFF_CONTEXT_LINES = 3
_RESULT_BUDGET_BYTES = 65536
_MIN_BODY_BYTES = 1
_BASE_BODY_MAX_BYTES = 262144
_CANDIDATE_BODY_MAX_BYTES = 131072

_ALLOWED_REPOSITORIES = (
    "mastermindx-market-intelligence/macro",
    "mastermindx-market-intelligence/Mastermind",
)

_COMMIT_RE = re.compile(r"[0-9a-f]{40}")
_SHA256_RE = re.compile(r"[0-9a-f]{64}")

_SOURCE_FIELDS = frozenset(
    {"repository", "path", "commit", "content_sha256"}
)

_STATE_AVAILABLE = "AVAILABLE"
_STATE_UNAVAILABLE = "UNAVAILABLE"

_REASON_SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"
_REASON_BYTES_MISMATCH = "SOURCE_BYTES_MISMATCH"
_REASON_INVALID_CONTENT = "INVALID_CONTENT"
_REASON_CONTENT_OVER_BUDGET = "CONTENT_OVER_BUDGET"


def _unavailable(reason):
    """Return the single closed shape shared by every refused outcome."""
    return {"state": _STATE_UNAVAILABLE, "reason": reason}


def _valid_path(path):
    """Validate one recorded relative ``.md`` path as plain data."""
    if not isinstance(path, str):
        return False
    if not 1 <= len(path) <= 512:
        return False
    if path.startswith("/"):
        return False
    if "\\" in path:
        return False
    for forbidden in ("\x00", "\r", "\n"):
        if forbidden in path:
            return False
    if not path.endswith(".md"):
        return False
    for component in path.split("/"):
        if component in ("", ".", ".."):
            return False
    return True


def _validated_source_fields(base_source):
    """Return the four detached field values, or ``None`` when malformed.

    Strict plain-data validation: no coercion, bools are not strings, extra
    and missing fields are refused alike.
    """
    if not isinstance(base_source, dict):
        return None
    if set(base_source.keys()) != _SOURCE_FIELDS:
        return None
    repository = base_source["repository"]
    path = base_source["path"]
    commit = base_source["commit"]
    content_sha256 = base_source["content_sha256"]
    if not isinstance(repository, str) or repository not in _ALLOWED_REPOSITORIES:
        return None
    if not _valid_path(path):
        return None
    if not isinstance(commit, str) or _COMMIT_RE.fullmatch(commit) is None:
        return None
    if (
        not isinstance(content_sha256, str)
        or _SHA256_RE.fullmatch(content_sha256) is None
    ):
        return None
    return repository, path, commit, content_sha256


def _within_body_range(body, max_bytes):
    return _MIN_BODY_BYTES <= len(body) <= max_bytes


def compare_plan_content(
    *,
    base_source,
    base_bytes,
    candidate_sha256,
    candidate_bytes,
):
    """Compare a recorded base plan body against a candidate plan body.

    Both bodies are exact ``bytes`` already captured by the caller. Digests are
    verified against the actual bytes; decoding is strict UTF-8 with no
    normalization, so LF/CRLF and BOM differences stay meaningful. The diff
    labels are fixed constants and never derived from caller paths.
    """
    fields = _validated_source_fields(base_source)
    if fields is None:
        return _unavailable(_REASON_INVALID_CONTENT)
    if (
        not isinstance(candidate_sha256, str)
        or _SHA256_RE.fullmatch(candidate_sha256) is None
    ):
        return _unavailable(_REASON_INVALID_CONTENT)
    for body in (base_bytes, candidate_bytes):
        if body is not None and not isinstance(body, bytes):
            return _unavailable(_REASON_INVALID_CONTENT)
    if base_bytes is None or candidate_bytes is None:
        return _unavailable(_REASON_SOURCE_UNAVAILABLE)
    if not _within_body_range(base_bytes, _BASE_BODY_MAX_BYTES):
        return _unavailable(_REASON_CONTENT_OVER_BUDGET)
    if not _within_body_range(candidate_bytes, _CANDIDATE_BODY_MAX_BYTES):
        return _unavailable(_REASON_CONTENT_OVER_BUDGET)
    if hashlib.sha256(base_bytes).hexdigest() != base_source["content_sha256"]:
        return _unavailable(_REASON_BYTES_MISMATCH)
    if hashlib.sha256(candidate_bytes).hexdigest() != candidate_sha256:
        return _unavailable(_REASON_BYTES_MISMATCH)
    try:
        base_text = base_bytes.decode("utf-8")
        candidate_text = candidate_bytes.decode("utf-8")
    except UnicodeDecodeError:
        return _unavailable(_REASON_BYTES_MISMATCH)

    base_lines = base_text.splitlines(keepends=True)
    candidate_lines = candidate_text.splitlines(keepends=True)
    diff_text = "".join(
        difflib.unified_diff(
            base_lines,
            candidate_lines,
            fromfile=_DIFF_FROM_LABEL,
            tofile=_DIFF_TO_LABEL,
            n=_DIFF_CONTEXT_LINES,
        )
    )
    # Same matcher construction difflib.unified_diff uses internally, so the
    # counts always agree with the pinned diff text, headers excluded.
    matcher = difflib.SequenceMatcher(None, base_lines, candidate_lines)
    added_lines = 0
    removed_lines = 0
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "insert":
            added_lines += j2 - j1
        elif tag == "delete":
            removed_lines += i2 - i1
        elif tag == "replace":
            added_lines += j2 - j1
            removed_lines += i2 - i1

    repository, path, commit, content_sha256 = fields
    result = {
        "state": _STATE_AVAILABLE,
        "base_source": {
            "repository": repository,
            "path": path,
            "commit": commit,
            "content_sha256": content_sha256,
        },
        "candidate_sha256": candidate_sha256,
        "base_text": base_text,
        "candidate_text": candidate_text,
        "diff": diff_text,
        "identical": base_bytes == candidate_bytes,
        "added_lines": added_lines,
        "removed_lines": removed_lines,
    }
    encoded = json.dumps(
        result,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    ).encode("utf-8")
    if len(encoded) > _RESULT_BUDGET_BYTES:
        return _unavailable(_REASON_CONTENT_OVER_BUDGET)
    return result
