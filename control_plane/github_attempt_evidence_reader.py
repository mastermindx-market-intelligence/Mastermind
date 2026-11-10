"""Read-only GitHub lifecycle evidence for one coding attempt's own branch.

Director F integrator gap 3: the execution-return projection consumes a
``github`` facts block, but nothing read a coding attempt's own branch/PR/
checks/merge state into that shape.  This adapter is that reader.

Laws (mirror of ``github_review_result_reader`` conventions):
  * READ ONLY — no write, no label, no review, no comment is ever produced.
  * Injected port — tests inject fakes; the production port shells out to
    the installed ``gh`` CLI with a literal argv list and a timeout.  No
    test ever reaches the network.
  * One bounded read per call — ``read_attempt_github_evidence`` performs
    at most one ``pr_view`` and one ``pr_checks`` per invocation; there is
    no polling loop, no retry, no sleep.
  * Unknown-safe — every field is honestly ``None``/``"unknown"`` when the
    port fails, times out, or returns an unreadable shape; an unreadable
    fact is never coerced to a positive one (branch with no PR evidence
    stays branch-only; an unconcluded check keeps checks unknown).
"""
from __future__ import annotations

import json
import subprocess
from typing import Any, Mapping, Protocol

from control_plane.execution_return_projection import (
    CHECK_CONCLUSIONS,
    MERGE_STATES,
)

#: Wall-clock budget for one production ``gh`` invocation (seconds).
GH_CLI_TIMEOUT_SECONDS = 30

#: ``gh`` check conclusions mapped onto the projection's closed vocabulary.
#: Everything unrecognized maps to ``unknown`` — never guessed green.
_CHECK_CONCLUSION_MAP = {
    "success": "success",
    "skipped": "skipped",
    "failure": "failure",
    "failed": "failure",
    "timed_out": "failure",
    "action_required": "failure",
    "cancelled": "unknown",
    "canceled": "unknown",
    "stale": "unknown",
    "neutral": "unknown",
    "": "unknown",
}

#: ``gh`` PR states mapped onto the projection's merge vocabulary.  Only an
#: observed merge (non-empty ``mergedAt``) is ``merged``; open and closed-
#: unmerged are the observed negative; unread is unknown.
_PR_URL_MAX = 512
_PR_NUMBER_MAX = 10_000_000
_CHECK_NAMES_MAX = 64
_CHECK_NAME_MAX = 256


class GitHubEvidencePort(Protocol):
    """The two bounded reads the evidence reader needs."""

    def pr_view(self, repository: str, branch: str) -> Mapping[str, Any] | None:
        """The open/closed PR whose head is exactly ``branch``, or None."""

    def pr_checks(self, repository: str, pr_number: int) -> Any:
        """The check conclusions of one PR (a list or a mapping with a
        ``checks`` list), or None when unreadable."""


class GhCliEvidencePort:
    """Production port over the installed ``gh`` CLI (one call per method).

    Uses the literal argv form (never a shell string) with a timeout.  Any
    non-zero exit, timeout, or unparsable output returns ``None`` — the
    caller records an honest unknown, never a guess.
    """

    def __init__(self, *, timeout_seconds: int = GH_CLI_TIMEOUT_SECONDS) -> None:
        if type(timeout_seconds) is not int or timeout_seconds < 1:
            raise ValueError("timeout_seconds must be a positive int")
        self._timeout = timeout_seconds

    def _run(self, argv: list[str]) -> Any:
        try:
            completed = subprocess.run(
                argv, capture_output=True, timeout=self._timeout, check=False,
            )
        except (subprocess.TimeoutExpired, OSError):
            return None
        if completed.returncode != 0:
            return None
        try:
            return json.loads(completed.stdout.decode("utf-8"))
        except (ValueError, UnicodeError):
            return None

    def pr_view(self, repository: str, branch: str) -> Mapping[str, Any] | None:
        value = self._run([
            "gh", "pr", "view", branch, "--repo", repository,
            "--json", "number,url,state,mergedAt,headRefName",
        ])
        return value if isinstance(value, Mapping) else None

    def pr_checks(self, repository: str, pr_number: int) -> Any:
        # ``gh pr checks --json`` emits a TOP-LEVEL ARRAY; some gateway
        # wrappers emit {"checks": [...]}.  Both are accepted; anything
        # else reads as unreadable (None).
        return self._run([
            "gh", "pr", "checks", str(pr_number), "--repo", repository,
            "--json", "name,state,conclusion",
        ])


def _clean_identifier(value: Any, *, limit: int) -> str | None:
    if type(value) is not str or not value or len(value) > limit:
        return None
    return value


def _map_checks(raw: Any) -> list[dict[str, str]] | None:
    """Reduce ``gh pr checks --json`` rows onto {name, conclusion}.

    Unknown-safe: any malformed row or unrecognized conclusion maps to
    ``unknown``, which the projection treats as not-green.  Returns None
    only when the whole payload is not a list.
    """
    if not isinstance(raw, list):
        return None
    rows: list[dict[str, str]] = []
    for item in raw[:_CHECK_NAMES_MAX]:
        if not isinstance(item, Mapping):
            rows.append({"name": "unreadable-check", "conclusion": "unknown"})
            continue
        name = _clean_identifier(item.get("name"), limit=_CHECK_NAME_MAX)
        raw_conclusion = item.get("conclusion")
        conclusion = (
            _CHECK_CONCLUSION_MAP.get(str(raw_conclusion or "").strip().lower())
            if isinstance(raw_conclusion, str) else None
        )
        rows.append({
            "name": name if name is not None else "unreadable-check",
            "conclusion": conclusion if conclusion in CHECK_CONCLUSIONS else "unknown",
        })
    # Duplicated names would be refused downstream; keep the first honest read.
    deduped: list[dict[str, str]] = []
    seen: set[str] = set()
    for row in rows:
        if row["name"] in seen:
            continue
        seen.add(row["name"])
        deduped.append(row)
    return deduped


def _map_merge_state(view: Mapping[str, Any]) -> str:
    merged_at = view.get("mergedAt")
    if isinstance(merged_at, str) and merged_at.strip():
        return "merged"
    state = str(view.get("state") or "").strip().lower()
    if state in ("open", "closed"):
        return "not_merged"
    return "unknown"


def read_attempt_github_evidence(
    *,
    repository: str,
    branch: str,
    port: GitHubEvidencePort,
) -> dict[str, Any]:
    """One bounded read of a coding attempt's own branch/PR/checks/merge.

    Returns exactly the ``github`` facts block ``project_execution_return``
    consumes.  Every field is unknown-safe: no PR / failed read keeps
    ``pr_number``/``pr_url``/``checks`` None and ``merge_state`` unknown —
    the derived stage then honestly stops at ``branch_pushed`` (or
    ``result_only`` when even the branch is unobserved upstream).
    """
    if not isinstance(repository, str) or not repository.strip():
        raise ValueError("repository must be a non-empty string")
    if not isinstance(branch, str) or not branch.strip():
        raise ValueError("branch must be a non-empty string")
    evidence: dict[str, Any] = {
        "branch": branch,
        "pr_number": None,
        "pr_url": None,
        "checks": None,
        "merge_state": "unknown",
    }
    try:
        view = port.pr_view(repository, branch)
    except Exception:
        view = None
    if not isinstance(view, Mapping):
        return evidence
    state = str(view.get("state") or "").strip().lower()
    if state not in ("open", "closed", "merged"):
        # An unreadable PR view is not evidence of a PR: stay branch-only.
        return evidence
    number = view.get("number")
    if type(number) is int and 0 < number < _PR_NUMBER_MAX:
        evidence["pr_number"] = number
    url = _clean_identifier(view.get("url"), limit=_PR_URL_MAX)
    if url is not None and url.startswith("https://"):
        evidence["pr_url"] = url
    merge_state = _map_merge_state(view)
    evidence["merge_state"] = (
        merge_state if merge_state in MERGE_STATES else "unknown")
    if evidence["pr_number"] is None:
        return evidence
    try:
        checks_payload = port.pr_checks(repository, evidence["pr_number"])
    except Exception:
        checks_payload = None
    if isinstance(checks_payload, list):
        evidence["checks"] = _map_checks(checks_payload)
    elif isinstance(checks_payload, Mapping):
        mapped = _map_checks(checks_payload.get("checks"))
        if mapped is not None:
            evidence["checks"] = mapped
    return evidence


__all__ = [
    "GH_CLI_TIMEOUT_SECONDS",
    "GitHubEvidencePort",
    "GhCliEvidencePort",
    "read_attempt_github_evidence",
]
