"""Independent source-census baseline for the Z0 paired evaluation.

This module deliberately searches the frozen source snapshot directly.  It is
not a Zoekt adapter and it never consumes candidate output, so its answer keys
remain useful when either candidate is incomplete, stale, or unavailable.
"""

from __future__ import annotations

import hashlib
import json
import re
import stat
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from time import monotonic
from typing import Final


_SHA1_RE: Final = re.compile(r"[0-9a-f]{40}\Z")
_MAX_SOURCE_BYTES: Final = 256
_EXCLUDED_PATH_PARTS: Final = frozenset({".git", "generated", "vendor", "node_modules"})
_BINARY_SUFFIXES: Final = frozenset({".bin", ".gif", ".jpg", ".jpeg", ".pdf", ".png", ".zip"})
_LANGUAGES: Final = {
    ".c": "c",
    ".cpp": "cpp",
    ".css": "css",
    ".go": "go",
    ".html": "html",
    ".java": "java",
    ".js": "javascript",
    ".json": "json",
    ".md": "markdown",
    ".py": "python",
    ".rs": "rust",
    ".sh": "shell",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".yaml": "yaml",
    ".yml": "yml",
}


class SourceCensusError(ValueError):
    """The source corpus cannot be represented as one immutable baseline."""


@dataclass(frozen=True)
class SourceSnapshot:
    """One exact repository/ref source epoch supplied by the host."""

    logical_repo_id: str
    canonical_repository: str
    ref: str
    commit: str
    tree: str
    root: Path


@dataclass(frozen=True)
class SourceRecord:
    """One regular, eligible source file and its independent source identity."""

    logical_repo_id: str
    canonical_repository: str
    ref: str
    commit: str
    tree: str
    path: str
    language: str
    text: str
    content_digest: str


@dataclass(frozen=True)
class ExcludedSource:
    """A receipted non-source path so omission is visible rather than silent."""

    logical_repo_id: str
    path: str
    reason: str
    content_digest: str | None


@dataclass(frozen=True)
class SourceCensus:
    """Canonical immutable source input for the baseline and answer-key grader."""

    records: tuple[SourceRecord, ...]
    excluded: tuple[ExcludedSource, ...]
    canonical_bytes: bytes
    digest: str


@dataclass(frozen=True)
class BaselineQuery:
    """The shared query budget and filters used by both paired candidates."""

    query: str
    regex: bool = False
    case_sensitive: bool = False
    repository_ids: tuple[str, ...] = ()
    refs: tuple[str, ...] = ()
    path_prefixes: tuple[str, ...] = ()
    languages: tuple[str, ...] = ()
    limit: int = 100
    context_lines: int = 0
    timeout_ms: int = 60_000


@dataclass(frozen=True)
class BaselineMatch:
    """A direct-source result with enough provenance for deterministic grading."""

    logical_repo_id: str
    canonical_repository: str
    ref: str
    commit: str
    path: str
    language: str
    line_start: int
    line_end: int
    preview: str
    context_before: tuple[str, ...]
    context_after: tuple[str, ...]
    source_content_digest: str

    @property
    def identity(self) -> tuple[str, str, str, str, int, int]:
        return (
            self.logical_repo_id,
            self.canonical_repository,
            self.ref,
            self.path,
            self.line_start,
            self.line_end,
        )


@dataclass(frozen=True)
class BaselineResult:
    """A bounded candidate-comparable result; truncation is always explicit."""

    matches: tuple[BaselineMatch, ...]
    total_match_count: int
    truncated: bool
    census_digest: str
    query_completed: bool = True
    failure_code: str | None = None


@dataclass(frozen=True)
class AnswerKey:
    """Source-derived expected/forbidden identities and immutable grader bytes."""

    case_id: str
    expected_identities: tuple[tuple[str, str, str, str, int, int], ...]
    forbidden_identities: tuple[tuple[str, str, str, str, int, int], ...]
    canonical_bytes: bytes
    digest: str


def census_sources(snapshots: tuple[SourceSnapshot, ...]) -> SourceCensus:
    """Read exact source snapshots into a sorted, direct-searchable corpus.

    Symlinks and duplicate source identities are failures rather than a chance
    to quietly merge or escape a configured source epoch.  Generated, vendor,
    binary, and oversize files are skipped with a disposition receipt.
    """

    if not isinstance(snapshots, tuple) or not snapshots:
        raise SourceCensusError("snapshots must be a non-empty tuple")
    seen_logical: set[str] = set()
    seen_repository_ref: set[tuple[str, str]] = set()
    records: list[SourceRecord] = []
    excluded: list[ExcludedSource] = []
    for snapshot in snapshots:
        _validate_snapshot(snapshot, seen_logical, seen_repository_ref)
        root = snapshot.root
        for candidate in sorted(root.rglob("*"), key=lambda item: item.as_posix()):
            relative = candidate.relative_to(root).as_posix()
            mode = candidate.lstat().st_mode
            if stat.S_ISLNK(mode):
                raise SourceCensusError(f"symlink source entry is forbidden: {relative}")
            if not stat.S_ISREG(mode):
                continue
            disposition = _disposition(relative, candidate)
            if disposition is not None:
                excluded.append(
                    ExcludedSource(
                        logical_repo_id=snapshot.logical_repo_id,
                        path=relative,
                        reason=disposition,
                        content_digest=_optional_file_digest(candidate, disposition),
                    )
                )
                continue
            raw = candidate.read_bytes()
            if b"\x00" in raw:
                excluded.append(
                    ExcludedSource(
                        snapshot.logical_repo_id,
                        relative,
                        "binary",
                        hashlib.sha256(raw).hexdigest(),
                    )
                )
                continue
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError:
                excluded.append(
                    ExcludedSource(
                        snapshot.logical_repo_id,
                        relative,
                        "binary",
                        hashlib.sha256(raw).hexdigest(),
                    )
                )
                continue
            language = _LANGUAGES.get(candidate.suffix.lower())
            if language is None:
                excluded.append(
                    ExcludedSource(
                        snapshot.logical_repo_id,
                        relative,
                        "unsupported_language",
                        hashlib.sha256(raw).hexdigest(),
                    )
                )
                continue
            records.append(
                SourceRecord(
                    logical_repo_id=snapshot.logical_repo_id,
                    canonical_repository=snapshot.canonical_repository,
                    ref=snapshot.ref,
                    commit=snapshot.commit,
                    tree=snapshot.tree,
                    path=relative,
                    language=language,
                    text=text,
                    content_digest=hashlib.sha256(raw).hexdigest(),
                )
            )
    records.sort(key=lambda item: _record_order(item))
    excluded.sort(key=lambda item: (item.logical_repo_id, item.path, item.reason))
    canonical = _canonical_json(
        {
            "records": [_record_payload(item) for item in records],
            "excluded": [_excluded_payload(item) for item in excluded],
        }
    )
    return SourceCensus(
        records=tuple(records),
        excluded=tuple(excluded),
        canonical_bytes=canonical,
        digest=hashlib.sha256(canonical).hexdigest(),
    )


def baseline_search(
    census: SourceCensus,
    query: BaselineQuery,
    *,
    monotonic_clock: Callable[[], float] = monotonic,
) -> BaselineResult:
    """Search every eligible source line with shared filters and limits."""

    _validate_census(census)
    pattern = _compile_query(query)
    matches: list[BaselineMatch] = []
    deadline = monotonic_clock() + query.timeout_ms / 1000
    timed_out = False
    for record in census.records:
        if monotonic_clock() >= deadline:
            timed_out = True
            break
        if not _record_matches_filters(record, query):
            continue
        lines = record.text.split("\n")
        for offset, line in enumerate(lines):
            if monotonic_clock() >= deadline:
                timed_out = True
                break
            if pattern.search(line) is None:
                continue
            matches.append(
                BaselineMatch(
                    logical_repo_id=record.logical_repo_id,
                    canonical_repository=record.canonical_repository,
                    ref=record.ref,
                    commit=record.commit,
                    path=record.path,
                    language=record.language,
                    line_start=offset + 1,
                    line_end=offset + 1,
                    preview=line,
                    context_before=tuple(
                        lines[max(0, offset - query.context_lines) : offset]
                    ),
                    context_after=tuple(
                        lines[offset + 1 : offset + 1 + query.context_lines]
                    ),
                    source_content_digest=record.content_digest,
                )
            )
        if timed_out:
            break
    matches.sort(key=lambda item: (*item.identity, item.preview))
    return BaselineResult(
        matches=tuple(matches[: query.limit]),
        total_match_count=len(matches),
        truncated=timed_out or len(matches) > query.limit,
        census_digest=census.digest,
        query_completed=not timed_out,
        failure_code="TIMEOUT" if timed_out else None,
    )


def derive_answer_key(census: SourceCensus, case_id: str, query: BaselineQuery) -> AnswerKey:
    """Derive a frozen answer key only from the direct-source baseline census."""

    if not isinstance(case_id, str) or not case_id:
        raise SourceCensusError("case_id must be non-empty text")
    unlimited = BaselineQuery(
        query=query.query,
        regex=query.regex,
        case_sensitive=query.case_sensitive,
        repository_ids=query.repository_ids,
        refs=query.refs,
        path_prefixes=query.path_prefixes,
        languages=query.languages,
        limit=100,
        context_lines=query.context_lines,
        timeout_ms=query.timeout_ms,
    )
    result = baseline_search(census, unlimited)
    if result.truncated:
        raise SourceCensusError("answer key exceeds frozen exhaustive baseline budget")
    expected = tuple(match.identity for match in result.matches)
    expected_set = set(expected)
    forbidden = tuple(
        identity
        for identity in sorted(_all_source_line_identities(census))
        if identity not in expected_set
    )
    canonical = _canonical_json(
        {
            "case_id": case_id,
            "census_digest": census.digest,
            "query": _query_payload(unlimited),
            "expected": [_match_payload(match) for match in result.matches],
            "forbidden": [list(identity) for identity in forbidden],
        }
    )
    return AnswerKey(
        case_id=case_id,
        expected_identities=expected,
        forbidden_identities=forbidden,
        canonical_bytes=canonical,
        digest=hashlib.sha256(canonical).hexdigest(),
    )


def _validate_snapshot(
    snapshot: SourceSnapshot,
    seen_logical: set[str],
    seen_repository_ref: set[tuple[str, str]],
) -> None:
    if not isinstance(snapshot, SourceSnapshot):
        raise SourceCensusError("snapshots must contain SourceSnapshot entries")
    if not all(isinstance(value, str) and value for value in (
        snapshot.logical_repo_id,
        snapshot.canonical_repository,
        snapshot.ref,
    )):
        raise SourceCensusError("source snapshot identity must be non-empty text")
    if _SHA1_RE.fullmatch(snapshot.commit) is None or _SHA1_RE.fullmatch(snapshot.tree) is None:
        raise SourceCensusError("source snapshot commit and tree must be lowercase SHA-1")
    if snapshot.logical_repo_id in seen_logical:
        raise SourceCensusError("duplicate logical_repo_id")
    repository_ref = (snapshot.canonical_repository, snapshot.ref)
    if repository_ref in seen_repository_ref:
        raise SourceCensusError("duplicate canonical repository/ref")
    try:
        mode = snapshot.root.lstat().st_mode
    except OSError as error:
        raise SourceCensusError("source root cannot be read") from error
    if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
        raise SourceCensusError("source root must be a real directory")
    seen_logical.add(snapshot.logical_repo_id)
    seen_repository_ref.add(repository_ref)


def _disposition(relative: str, candidate: Path) -> str | None:
    parts = tuple(relative.split("/"))
    if any(part in _EXCLUDED_PATH_PARTS for part in parts):
        if ".git" in parts:
            return "submodule"
        if "generated" in parts:
            return "generated"
        return "vendor"
    if candidate.suffix.lower() in _BINARY_SUFFIXES:
        return "binary"
    if candidate.stat().st_size > _MAX_SOURCE_BYTES:
        return "oversize"
    return None


def _optional_file_digest(candidate: Path, reason: str) -> str | None:
    if reason == "oversize":
        return None
    return hashlib.sha256(candidate.read_bytes()).hexdigest()


def _validate_census(census: SourceCensus) -> None:
    if not isinstance(census, SourceCensus):
        raise SourceCensusError("baseline requires a SourceCensus")
    if hashlib.sha256(census.canonical_bytes).hexdigest() != census.digest:
        raise SourceCensusError("source census digest does not bind its canonical bytes")


def _compile_query(query: BaselineQuery) -> re.Pattern[str]:
    if not isinstance(query, BaselineQuery):
        raise SourceCensusError("baseline query must be a BaselineQuery")
    if not isinstance(query.query, str) or not query.query:
        raise SourceCensusError("query must be non-empty text")
    if type(query.regex) is not bool or type(query.case_sensitive) is not bool:
        raise SourceCensusError("query regex and case_sensitive must be booleans")
    if type(query.limit) is not int or not 1 <= query.limit <= 100:
        raise SourceCensusError("query limit must be in 1..100")
    if type(query.context_lines) is not int or not 0 <= query.context_lines <= 8:
        raise SourceCensusError("query context_lines must be in 0..8")
    if type(query.timeout_ms) is not int or not 1 <= query.timeout_ms <= 60_000:
        raise SourceCensusError("query timeout_ms must be in 1..60000")
    for values, label in (
        (query.repository_ids, "repository_ids"),
        (query.refs, "refs"),
        (query.path_prefixes, "path_prefixes"),
        (query.languages, "languages"),
    ):
        if not isinstance(values, tuple) or any(not isinstance(value, str) or not value for value in values):
            raise SourceCensusError(f"{label} must be a tuple of non-empty text")
        if len(values) != len(set(values)):
            raise SourceCensusError(f"{label} must not contain duplicates")
    flags = 0 if query.case_sensitive else re.IGNORECASE
    try:
        return re.compile(query.query if query.regex else re.escape(query.query), flags)
    except re.error as error:
        raise SourceCensusError("query regex is invalid") from error


def _record_matches_filters(record: SourceRecord, query: BaselineQuery) -> bool:
    return (
        (not query.repository_ids or record.logical_repo_id in query.repository_ids)
        and (not query.refs or record.ref in query.refs)
        and (
            not query.path_prefixes
            or any(record.path == prefix.rstrip("/") or record.path.startswith(prefix.rstrip("/") + "/") for prefix in query.path_prefixes)
        )
        and (not query.languages or record.language in query.languages)
    )


def _record_order(record: SourceRecord) -> tuple[str, str, str, str, str]:
    return (
        record.canonical_repository,
        record.ref,
        record.logical_repo_id,
        record.path,
        record.content_digest,
    )


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode("utf-8")


def _record_payload(record: SourceRecord) -> dict[str, str]:
    return {
        "logical_repo_id": record.logical_repo_id,
        "canonical_repository": record.canonical_repository,
        "ref": record.ref,
        "commit": record.commit,
        "tree": record.tree,
        "path": record.path,
        "language": record.language,
        "content_digest": record.content_digest,
    }


def _excluded_payload(record: ExcludedSource) -> dict[str, str | None]:
    return {
        "logical_repo_id": record.logical_repo_id,
        "path": record.path,
        "reason": record.reason,
        "content_digest": record.content_digest,
    }


def _query_payload(query: BaselineQuery) -> dict[str, object]:
    return {
        "query": query.query,
        "regex": query.regex,
        "case_sensitive": query.case_sensitive,
        "repository_ids": list(query.repository_ids),
        "refs": list(query.refs),
        "path_prefixes": list(query.path_prefixes),
        "languages": list(query.languages),
        "limit": query.limit,
        "context_lines": query.context_lines,
        "timeout_ms": query.timeout_ms,
    }


def _match_payload(match: BaselineMatch) -> dict[str, object]:
    return {
        "identity": list(match.identity),
        "preview": match.preview,
        "source_content_digest": match.source_content_digest,
    }


def _all_source_line_identities(
    census: SourceCensus,
) -> set[tuple[str, str, str, str, int, int]]:
    """Enumerate direct-source lines that a candidate must not invent as answers."""

    identities: set[tuple[str, str, str, str, int, int]] = set()
    for record in census.records:
        for offset, _line in enumerate(record.text.split("\n")):
            identities.add(
                (
                    record.logical_repo_id,
                    record.canonical_repository,
                    record.ref,
                    record.path,
                    offset + 1,
                    offset + 1,
                )
            )
    return identities
