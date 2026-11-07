"""Trusted GitHub PR change census for the risk-tiered review fast lane.

The caller MUST bind this Protocol to the incumbent installation-scoped GitHub
reader, not to webhook JSON, author claims, PR text, labels, or a new credential.
This module creates no GitHub client, review Job, permission, release or writer.
A current source head is read both before and after complete file pagination.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from control_plane.github_review_risk_policy import (
    ReviewChangeFacts,
    ReviewFileStat,
    ReviewRiskAssessment,
    RiskPolicyInputError,
    assess_review_risk,
)

MAX_FILES = 256
PAGE_SIZE = 100
ALLOWED_STATUSES = frozenset({
    "added", "modified", "removed", "renamed", "copied", "changed",
})
_BINARY_SUFFIXES = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".pdf", ".woff", ".woff2")
_PATCHLESS_EVIDENCE_PREFIXES = (
    "research/evidence/", "mockups/evidence/", "ux-evidence/",
    "terminal/docs/", "docs/verification/",
)
_PATCHLESS_EVIDENCE_SUFFIXES = (".log", ".json", ".yml", ".yaml", ".md", ".txt", ".csv")


class RiskSourceUnavailable(RuntimeError):
    """The snapshot is untrusted, inconsistent, truncated or no longer current."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        # Structured producer code, never arbitrary upstream exception text.
        self.code = code if type(code) is str else None


@dataclass(frozen=True)
class SourcePR:
    repository: str
    pull_number: int
    head_sha: str
    base_sha: str
    head_repository: str
    base_repository: str
    open: bool
    draft: bool
    changed_files: int
    additions: int
    deletions: int


@dataclass(frozen=True)
class SourceFile:
    filename: str
    status: str
    additions: int
    deletions: int
    previous_filename: str | None = None
    patch_available: bool = True


class RiskGitHubReadPort(Protocol):
    """Authenticated current GitHub installation reader bound by its real owner."""

    def read_pr_risk_source(self, *, repository: str, pull_number: int) -> SourcePR:
        ...

    def read_pr_risk_file_page(
        self, *, repository: str, pull_number: int, page: int, per_page: int
    ) -> tuple[SourceFile, ...]:
        ...


def _validate_pr(value: object, repo: str, pr: int) -> SourcePR:
    if type(value) is not SourcePR or value.repository != repo or value.pull_number != pr:
        raise RiskSourceUnavailable("PR_SOURCE_IDENTITY_UNKNOWN")
    if type(value.open) is not bool or type(value.draft) is not bool:
        raise RiskSourceUnavailable("PR_SOURCE_STATE_INVALID")
    if not value.open or value.draft:
        raise RiskSourceUnavailable("PR_NOT_REVIEWABLE")
    if value.head_repository != repo or value.base_repository != repo:
        raise RiskSourceUnavailable("PR_HEAD_NOT_IN_SAME_REPOSITORY")
    for name in ("changed_files", "additions", "deletions"):
        item = getattr(value, name)
        if type(item) is not int or item < 0 or item > 10_000_000:
            raise RiskSourceUnavailable("PR_FILE_STATS_INVALID")
    if value.changed_files < 1 or value.changed_files > MAX_FILES:
        raise RiskSourceUnavailable("PR_FILES_OUT_OF_SCOPE")
    try:
        assess_review_risk(ReviewChangeFacts(
            repository=repo, pull_number=pr, head_sha=value.head_sha,
            changed_paths=(), additions=0, deletions=0,
            complete_source_verified=False,
        ))
        assess_review_risk(ReviewChangeFacts(
            repository=repo, pull_number=pr, head_sha=value.base_sha,
            changed_paths=(), additions=0, deletions=0,
            complete_source_verified=False,
        ))
    except RiskPolicyInputError as exc:
        raise RiskSourceUnavailable("PR_SHA_MALFORMED") from exc
    return value


def _validate_file(value: object) -> SourceFile:
    if type(value) is not SourceFile or type(value.filename) is not str:
        raise RiskSourceUnavailable("PR_FILE_SHAPE_INVALID")
    if type(value.status) is not str or value.status not in ALLOWED_STATUSES:
        raise RiskSourceUnavailable("PR_FILE_STATUS_UNSUPPORTED")
    for n in ("additions", "deletions"):
        item = getattr(value, n)
        if type(item) is not int or item < 0 or item > 10_000_000:
            raise RiskSourceUnavailable("PR_FILE_STATS_INVALID")
    if type(value.patch_available) is not bool:
        raise RiskSourceUnavailable("PR_FILE_PATCH_UNKNOWN")
    if value.status == "renamed":
        if type(value.previous_filename) is not str or not value.previous_filename:
            raise RiskSourceUnavailable("PR_PREVIOUS_PATH_MISSING")
    elif value.previous_filename is not None:
        raise RiskSourceUnavailable("PR_PREVIOUS_PATH_MISMATCH")
    patchless_noncode = value.filename.lower().endswith(_BINARY_SUFFIXES) or (
        value.filename.lower().startswith(_PATCHLESS_EVIDENCE_PREFIXES)
        and value.filename.lower().endswith(_PATCHLESS_EVIDENCE_SUFFIXES)
    )
    if not value.patch_available and not patchless_noncode:
        raise RiskSourceUnavailable("PR_CODE_PATCH_MISSING")
    return value


def assess_current_pr_risk_with_final(
    reader: RiskGitHubReadPort, *, repository: str, pull_number: int
) -> tuple[ReviewRiskAssessment, SourcePR]:
    """Read complete authentic files, fence moved heads, then classify.

    Any missing page, renamed sensitive previous file, mismatched stats, stale
    head, unrecognized file shape or unsupported source refuses; no FAST path.
    The caller must not convert errors into permission to auto-review or merge.
    """
    first = _validate_pr(
        reader.read_pr_risk_source(repository=repository, pull_number=pull_number),
        repository, pull_number,
    )
    page_count = (first.changed_files + PAGE_SIZE - 1) // PAGE_SIZE
    files: list[SourceFile] = []
    for page in range(1, page_count + 1):
        batch = reader.read_pr_risk_file_page(
            repository=repository, pull_number=pull_number,
            page=page, per_page=PAGE_SIZE,
        )
        if type(batch) is not tuple or len(batch) != min(PAGE_SIZE, first.changed_files - len(files)):
            raise RiskSourceUnavailable("PR_SOURCE_PAGINATION_INCOMPLETE")
        files.extend(_validate_file(value) for value in batch)
    final = _validate_pr(
        reader.read_pr_risk_source(repository=repository, pull_number=pull_number),
        repository, pull_number,
    )
    if first != final:
        raise RiskSourceUnavailable("PR_SOURCE_MOVED_DURING_CENSUS")
    if len(files) != first.changed_files:
        raise RiskSourceUnavailable("PR_SOURCE_FILES_INCOMPLETE")
    if sum(f.additions for f in files) != first.additions or sum(f.deletions for f in files) != first.deletions:
        raise RiskSourceUnavailable("PR_SOURCE_STATS_INCONSISTENT")
    paths: list[str] = []
    hints: set[str] = set()
    for file in files:
        paths.append(file.filename)
        if file.previous_filename is not None:
            paths.append(file.previous_filename)
        if file.status == "removed":
            hints.add("destructive_change")
    try:
        assessment = assess_review_risk(ReviewChangeFacts(
            repository=repository, pull_number=pull_number,
            head_sha=first.head_sha, changed_paths=tuple(paths),
            additions=first.additions, deletions=first.deletions,
            complete_source_verified=True, risk_hints=tuple(sorted(hints)),
            file_metrics=tuple(ReviewFileStat(
                path=f.filename, additions=f.additions, deletions=f.deletions,
                previous_path=f.previous_filename
            ) for f in files),
        ))
        return assessment, final
    except RiskPolicyInputError as exc:
        raise RiskSourceUnavailable("PR_SOURCE_INVALID_FOR_POLICY") from exc


def assess_current_pr_risk(
    reader: RiskGitHubReadPort, *, repository: str, pull_number: int
) -> ReviewRiskAssessment:
    """Backward-compatible assessment, with no redundant source read."""
    assessment, _ = assess_current_pr_risk_with_final(
        reader, repository=repository, pull_number=pull_number,
    )
    return assessment
