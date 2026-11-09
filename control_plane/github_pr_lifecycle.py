"""Pure PR-estate lifecycle assessment for Mastermind GitHub carriers.

This module performs no I/O, persistence, GitHub mutation, branch deletion, merge,
review, or lifecycle ownership. It classifies immutable, caller-supplied facts so
estate cleanup can distinguish live work from safely closable historical carriers.

A CLOSE_CANDIDATE verdict is evidence for a separately authorized caller. It is
never, by itself, authority to close a pull request.
"""
from __future__ import annotations

import dataclasses
import re
from enum import Enum


SCHEMA = "mastermind.github_pr_lifecycle_assessment.v1"
STALE_RECONCILE_DAYS = 14
_REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}$")
_SECRET_PATTERNS = (
    re.compile(r"github_pat_", re.IGNORECASE),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]", re.IGNORECASE),
    re.compile(r"\bxox[baprs]-", re.IGNORECASE),
    re.compile(r"\bsk-[A-Za-z0-9]", re.IGNORECASE),
    re.compile(
        r"\b(?:authorization|bearer|password|token|secret|credential)\s*[:=]\s*\S+",
        re.IGNORECASE,
    ),
    re.compile(r"-----BEGIN", re.IGNORECASE),
)


class LifecycleInputError(ValueError):
    """Raised when immutable lifecycle facts are malformed."""


class PullRequestState(str, Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    MERGED = "MERGED"
    UNKNOWN = "UNKNOWN"


class WorkState(str, Enum):
    ACTIVE = "ACTIVE"
    GATED = "GATED"
    TERMINAL = "TERMINAL"
    NONE = "NONE"
    UNKNOWN = "UNKNOWN"


class ExplicitDisposition(str, Enum):
    NONE = "NONE"
    KEEP_OPEN = "KEEP_OPEN"
    CLOSE_UNMERGED = "CLOSE_UNMERGED"
    NEVER_MERGE = "NEVER_MERGE"


class IntegrationState(str, Enum):
    EXACTLY_INTEGRATED = "EXACTLY_INTEGRATED"
    SUPERSEDED_BY_CURRENT = "SUPERSEDED_BY_CURRENT"
    NOT_INTEGRATED = "NOT_INTEGRATED"
    UNKNOWN = "UNKNOWN"


class PreservationState(str, Enum):
    PRESERVED = "PRESERVED"
    NOT_REQUIRED = "NOT_REQUIRED"
    UNPRESERVED = "UNPRESERVED"
    UNKNOWN = "UNKNOWN"


class SourceCoverage(str, Enum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    UNKNOWN = "UNKNOWN"


class EffectState(str, Enum):
    NONE = "NONE"
    APPLIED = "APPLIED"
    EFFECT_UNKNOWN = "EFFECT_UNKNOWN"


class LifecycleVerdict(str, Enum):
    KEEP_ACTIVE = "KEEP_ACTIVE"
    KEEP_GATED = "KEEP_GATED"
    CLOSE_CANDIDATE = "CLOSE_CANDIDATE"
    RECONCILE_REQUIRED = "RECONCILE_REQUIRED"
    NOT_OPEN = "NOT_OPEN"


class LifecycleIssue(str, Enum):
    PR_NOT_OPEN = "PR_NOT_OPEN"
    PR_STATE_UNKNOWN = "PR_STATE_UNKNOWN"
    SOURCE_COVERAGE_INCOMPLETE = "SOURCE_COVERAGE_INCOMPLETE"
    PRIOR_EFFECT_UNKNOWN = "PRIOR_EFFECT_UNKNOWN"
    ACTIVE_WORK = "ACTIVE_WORK"
    ACTIVE_HOLD_OR_GATE = "ACTIVE_HOLD_OR_GATE"
    GATE_IDENTITY_INCOMPLETE = "GATE_IDENTITY_INCOMPLETE"
    EXPLICIT_CLOSE_DISPOSITION = "EXPLICIT_CLOSE_DISPOSITION"
    EXPLICIT_KEEP_OPEN = "EXPLICIT_KEEP_OPEN"
    CURRENT_DELTA_ALREADY_INTEGRATED = "CURRENT_DELTA_ALREADY_INTEGRATED"
    CURRENT_DELTA_SUPERSEDED = "CURRENT_DELTA_SUPERSEDED"
    INTEGRATION_STATE_UNKNOWN = "INTEGRATION_STATE_UNKNOWN"
    UNIQUE_OR_UNINTEGRATED_DELTA = "UNIQUE_OR_UNINTEGRATED_DELTA"
    PRESERVATION_UNPROVEN = "PRESERVATION_UNPROVEN"
    STALE_AGE_ONLY = "STALE_AGE_ONLY"
    CURRENT_WORK_STATE_UNKNOWN = "CURRENT_WORK_STATE_UNKNOWN"
    KEEP_OPEN_CONTRADICTS_WORK_STATE = "KEEP_OPEN_CONTRADICTS_WORK_STATE"


@dataclasses.dataclass(frozen=True)
class PullRequestLifecycleFacts:
    repository: str
    number: int
    state: PullRequestState
    merged: bool
    draft: bool
    work_state: WorkState
    explicit_disposition: ExplicitDisposition
    integration_state: IntegrationState
    preservation_state: PreservationState
    source_coverage: SourceCoverage
    prior_effect_state: EffectState
    owner: str | None = None
    gate: str | None = None
    release_condition: str | None = None
    days_since_update: int | None = None


@dataclasses.dataclass(frozen=True)
class LifecycleAssessment:
    schema: str
    verdict: LifecycleVerdict
    issues: tuple[LifecycleIssue, ...]


def _validate(facts: PullRequestLifecycleFacts) -> None:
    if type(facts) is not PullRequestLifecycleFacts:
        raise LifecycleInputError("facts must be exact PullRequestLifecycleFacts")
    if not _REPOSITORY_RE.fullmatch(facts.repository):
        raise LifecycleInputError("repository must be owner/name")
    if type(facts.number) is not int or facts.number <= 0:
        raise LifecycleInputError("number must be a positive integer")
    if type(facts.merged) is not bool or type(facts.draft) is not bool:
        raise LifecycleInputError("merged and draft must be booleans")
    enum_fields = (
        ("state", facts.state, PullRequestState),
        ("work_state", facts.work_state, WorkState),
        ("explicit_disposition", facts.explicit_disposition, ExplicitDisposition),
        ("integration_state", facts.integration_state, IntegrationState),
        ("preservation_state", facts.preservation_state, PreservationState),
        ("source_coverage", facts.source_coverage, SourceCoverage),
        ("prior_effect_state", facts.prior_effect_state, EffectState),
    )
    for name, value, expected in enum_fields:
        if type(value) is not expected:
            raise LifecycleInputError(f"{name} must be exact {expected.__name__}")
    for name, value in (
        ("owner", facts.owner),
        ("gate", facts.gate),
        ("release_condition", facts.release_condition),
    ):
        if value is not None and (type(value) is not str or not value.strip()):
            raise LifecycleInputError(f"{name} must be null or non-empty string")
        if value is not None:
            if len(value) > 512:
                raise LifecycleInputError(f"{name} exceeds 512 characters")
            if any(pattern.search(value) for pattern in _SECRET_PATTERNS):
                raise LifecycleInputError(f"{name} contains secret-shaped material")
    if facts.days_since_update is not None:
        if type(facts.days_since_update) is not int or facts.days_since_update < 0:
            raise LifecycleInputError(
                "days_since_update must be null or non-negative integer"
            )
    if facts.state is PullRequestState.MERGED and not facts.merged:
        raise LifecycleInputError("MERGED state requires merged=true")
    if facts.merged and facts.state is PullRequestState.OPEN:
        raise LifecycleInputError("open pull request cannot be merged")


def _assessment(
    verdict: LifecycleVerdict, *issues: LifecycleIssue
) -> LifecycleAssessment:
    return LifecycleAssessment(
        schema=SCHEMA,
        verdict=verdict,
        issues=tuple(dict.fromkeys(issues)),
    )


def assess_pr_lifecycle(facts: PullRequestLifecycleFacts) -> LifecycleAssessment:
    """Classify one exact pull request without performing any effect."""

    _validate(facts)

    if facts.state in (PullRequestState.CLOSED, PullRequestState.MERGED) or facts.merged:
        return _assessment(LifecycleVerdict.NOT_OPEN, LifecycleIssue.PR_NOT_OPEN)

    if facts.state is PullRequestState.UNKNOWN:
        return _assessment(
            LifecycleVerdict.RECONCILE_REQUIRED,
            LifecycleIssue.PR_STATE_UNKNOWN,
        )

    if facts.source_coverage is not SourceCoverage.COMPLETE:
        return _assessment(
            LifecycleVerdict.RECONCILE_REQUIRED,
            LifecycleIssue.SOURCE_COVERAGE_INCOMPLETE,
        )

    if facts.prior_effect_state is EffectState.EFFECT_UNKNOWN:
        return _assessment(
            LifecycleVerdict.RECONCILE_REQUIRED,
            LifecycleIssue.PRIOR_EFFECT_UNKNOWN,
        )

    if facts.work_state is WorkState.UNKNOWN:
        issues = [LifecycleIssue.CURRENT_WORK_STATE_UNKNOWN]
        if facts.explicit_disposition is ExplicitDisposition.KEEP_OPEN:
            issues.append(LifecycleIssue.EXPLICIT_KEEP_OPEN)
        if (
            facts.days_since_update is not None
            and facts.days_since_update >= STALE_RECONCILE_DAYS
        ):
            issues.append(LifecycleIssue.STALE_AGE_ONLY)
        return _assessment(LifecycleVerdict.RECONCILE_REQUIRED, *issues)

    if facts.explicit_disposition is ExplicitDisposition.KEEP_OPEN:
        if facts.work_state is WorkState.ACTIVE:
            return _assessment(
                LifecycleVerdict.KEEP_ACTIVE,
                LifecycleIssue.EXPLICIT_KEEP_OPEN,
                LifecycleIssue.ACTIVE_WORK,
            )
        if facts.work_state is WorkState.GATED:
            if not (facts.owner and facts.gate and facts.release_condition):
                return _assessment(
                    LifecycleVerdict.RECONCILE_REQUIRED,
                    LifecycleIssue.EXPLICIT_KEEP_OPEN,
                    LifecycleIssue.ACTIVE_HOLD_OR_GATE,
                    LifecycleIssue.GATE_IDENTITY_INCOMPLETE,
                )
            return _assessment(
                LifecycleVerdict.KEEP_GATED,
                LifecycleIssue.EXPLICIT_KEEP_OPEN,
                LifecycleIssue.ACTIVE_HOLD_OR_GATE,
            )
        return _assessment(
            LifecycleVerdict.RECONCILE_REQUIRED,
            LifecycleIssue.EXPLICIT_KEEP_OPEN,
            LifecycleIssue.KEEP_OPEN_CONTRADICTS_WORK_STATE,
        )

    if facts.work_state is WorkState.ACTIVE:
        return _assessment(LifecycleVerdict.KEEP_ACTIVE, LifecycleIssue.ACTIVE_WORK)

    if facts.work_state is WorkState.GATED:
        if not (facts.owner and facts.gate and facts.release_condition):
            return _assessment(
                LifecycleVerdict.RECONCILE_REQUIRED,
                LifecycleIssue.ACTIVE_HOLD_OR_GATE,
                LifecycleIssue.GATE_IDENTITY_INCOMPLETE,
            )
        return _assessment(
            LifecycleVerdict.KEEP_GATED,
            LifecycleIssue.ACTIVE_HOLD_OR_GATE,
        )

    close_requested = facts.explicit_disposition in (
        ExplicitDisposition.CLOSE_UNMERGED,
        ExplicitDisposition.NEVER_MERGE,
    )
    preserved = facts.preservation_state in (
        PreservationState.PRESERVED,
        PreservationState.NOT_REQUIRED,
    )
    integrated = facts.integration_state in (
        IntegrationState.EXACTLY_INTEGRATED,
        IntegrationState.SUPERSEDED_BY_CURRENT,
    )

    if close_requested:
        issues = [LifecycleIssue.EXPLICIT_CLOSE_DISPOSITION]
        if not preserved:
            issues.append(LifecycleIssue.PRESERVATION_UNPROVEN)
            if facts.integration_state is IntegrationState.NOT_INTEGRATED:
                issues.append(LifecycleIssue.UNIQUE_OR_UNINTEGRATED_DELTA)
            return _assessment(LifecycleVerdict.RECONCILE_REQUIRED, *issues)
        return _assessment(LifecycleVerdict.CLOSE_CANDIDATE, *issues)

    if integrated:
        issue = (
            LifecycleIssue.CURRENT_DELTA_ALREADY_INTEGRATED
            if facts.integration_state is IntegrationState.EXACTLY_INTEGRATED
            else LifecycleIssue.CURRENT_DELTA_SUPERSEDED
        )
        if not preserved:
            return _assessment(
                LifecycleVerdict.RECONCILE_REQUIRED,
                issue,
                LifecycleIssue.PRESERVATION_UNPROVEN,
            )
        return _assessment(LifecycleVerdict.CLOSE_CANDIDATE, issue)

    issues = []
    if facts.integration_state is IntegrationState.NOT_INTEGRATED:
        issues.append(LifecycleIssue.UNIQUE_OR_UNINTEGRATED_DELTA)
    if facts.preservation_state in (
        PreservationState.UNPRESERVED,
        PreservationState.UNKNOWN,
    ):
        issues.append(LifecycleIssue.PRESERVATION_UNPROVEN)
    if facts.integration_state is IntegrationState.UNKNOWN:
        issues.append(LifecycleIssue.INTEGRATION_STATE_UNKNOWN)
    if (
        facts.days_since_update is not None
        and facts.days_since_update >= STALE_RECONCILE_DAYS
    ):
        issues.append(LifecycleIssue.STALE_AGE_ONLY)
    return _assessment(LifecycleVerdict.RECONCILE_REQUIRED, *issues)


# Draft reviewability is a *separate advisory question* from closing/merging
# a PR. It belongs to this existing lifecycle decision owner rather than to
# another GitHub bot, watcher, queue, or release authority.
DRAFT_READINESS_SCHEMA = "mastermind.github_pr_draft_readiness.v1"
_SHA40_RE = re.compile(r"^[0-9a-f]{40}$")


class DraftReadinessVerdict(str, Enum):
    READY_CANDIDATE = "READY_CANDIDATE"
    KEEP_DRAFT = "KEEP_DRAFT"
    RECONCILE_REQUIRED = "RECONCILE_REQUIRED"
    NO_ACTION = "NO_ACTION"


class DraftReadinessIssue(str, Enum):
    PR_NOT_OPEN = "PR_NOT_OPEN"
    ALREADY_READY = "ALREADY_READY"
    SOURCE_NOT_FULLY_READ = "SOURCE_NOT_FULLY_READ"
    PREVIOUS_EFFECT_UNKNOWN = "PREVIOUS_EFFECT_UNKNOWN"
    WORK_STATE_UNKNOWN = "WORK_STATE_UNKNOWN"
    CURRENT_HEAD_UNVERIFIED = "CURRENT_HEAD_UNVERIFIED"
    DRAFT_HOLD_UNVERIFIED = "DRAFT_HOLD_UNVERIFIED"
    DRAFT_HELD = "DRAFT_HELD"
    WRITER_STATE_UNKNOWN = "WRITER_STATE_UNKNOWN"
    SOURCE_WRITER_ACTIVE = "SOURCE_WRITER_ACTIVE"
    SCOPE_COMPLETENESS_UNKNOWN = "SCOPE_COMPLETENESS_UNKNOWN"
    SCOPE_INCOMPLETE = "SCOPE_INCOMPLETE"
    QUALIFICATION_MISSING = "QUALIFICATION_MISSING"
    QUALIFICATION_STALE = "QUALIFICATION_STALE"
    NEVER_MERGE = "NEVER_MERGE"
    SOURCE_QUALIFIED = "SOURCE_QUALIFIED"


@dataclasses.dataclass(frozen=True)
class DraftReadinessFacts:
    """Caller-verified, head-bound evidence; not PR-text or CI inference.

    The source owner must supply full current-head and qualification evidence.
    Unknown is distinct from false. A current local/affected-test qualification
    is represented by its immutable head SHA; never derive it from a green CI
    checkbox, time-since-update, author prose, or review requests.
    """

    lifecycle: PullRequestLifecycleFacts
    current_head_sha: str | None
    qualified_head_sha: str | None
    scope_complete: bool | None
    explicit_draft_hold: bool | None
    source_writer_active: bool | None


@dataclasses.dataclass(frozen=True)
class DraftReadinessAssessment:
    schema: str
    verdict: DraftReadinessVerdict
    issues: tuple[DraftReadinessIssue, ...]


def _draft_assessment(
    verdict: DraftReadinessVerdict, issue: DraftReadinessIssue
) -> DraftReadinessAssessment:
    return DraftReadinessAssessment(
        schema=DRAFT_READINESS_SCHEMA, verdict=verdict, issues=(issue,)
    )


def assess_draft_readiness(facts: DraftReadinessFacts) -> DraftReadinessAssessment:
    """Advise a qualified Draft -> Ready transition; never perform that write.

    Hosted CI may be pending or red: it is a *merge* gate and does not on its
    own disqualify a stable candidate from review. A claimed Ready candidate
    is not a review request, formal approval, merge-on-green opt-in, queue
    admission, deployment, or proof of source qualification by this module.
    """

    if type(facts) is not DraftReadinessFacts:
        raise LifecycleInputError("readiness facts must be exact DraftReadinessFacts")
    _validate(facts.lifecycle)
    for name, sha in (
        ("current_head_sha", facts.current_head_sha),
        ("qualified_head_sha", facts.qualified_head_sha),
    ):
        if sha is not None and (
            type(sha) is not str or _SHA40_RE.fullmatch(sha) is None
        ):
            raise LifecycleInputError(f"{name} must be null or lowercase SHA40")
    for name, value in (
        ("scope_complete", facts.scope_complete),
        ("explicit_draft_hold", facts.explicit_draft_hold),
        ("source_writer_active", facts.source_writer_active),
    ):
        if value is not None and type(value) is not bool:
            raise LifecycleInputError(f"{name} must be null or boolean")

    pr = facts.lifecycle
    if pr.state in (PullRequestState.CLOSED, PullRequestState.MERGED) or pr.merged:
        return _draft_assessment(DraftReadinessVerdict.NO_ACTION, DraftReadinessIssue.PR_NOT_OPEN)
    if pr.state is PullRequestState.UNKNOWN:
        return _draft_assessment(DraftReadinessVerdict.RECONCILE_REQUIRED, DraftReadinessIssue.WORK_STATE_UNKNOWN)
    if not pr.draft:
        return _draft_assessment(DraftReadinessVerdict.NO_ACTION, DraftReadinessIssue.ALREADY_READY)
    if pr.source_coverage is not SourceCoverage.COMPLETE:
        return _draft_assessment(DraftReadinessVerdict.RECONCILE_REQUIRED, DraftReadinessIssue.SOURCE_NOT_FULLY_READ)
    if pr.prior_effect_state is EffectState.EFFECT_UNKNOWN:
        return _draft_assessment(DraftReadinessVerdict.RECONCILE_REQUIRED, DraftReadinessIssue.PREVIOUS_EFFECT_UNKNOWN)
    if pr.work_state is WorkState.UNKNOWN:
        return _draft_assessment(DraftReadinessVerdict.RECONCILE_REQUIRED, DraftReadinessIssue.WORK_STATE_UNKNOWN)
    if pr.explicit_disposition in (ExplicitDisposition.NEVER_MERGE, ExplicitDisposition.CLOSE_UNMERGED):
        return _draft_assessment(DraftReadinessVerdict.KEEP_DRAFT, DraftReadinessIssue.NEVER_MERGE)
    if facts.current_head_sha is None:
        return _draft_assessment(DraftReadinessVerdict.RECONCILE_REQUIRED, DraftReadinessIssue.CURRENT_HEAD_UNVERIFIED)
    if facts.explicit_draft_hold is None:
        return _draft_assessment(DraftReadinessVerdict.RECONCILE_REQUIRED, DraftReadinessIssue.DRAFT_HOLD_UNVERIFIED)
    if facts.explicit_draft_hold:
        return _draft_assessment(DraftReadinessVerdict.KEEP_DRAFT, DraftReadinessIssue.DRAFT_HELD)
    if facts.source_writer_active is None:
        return _draft_assessment(DraftReadinessVerdict.RECONCILE_REQUIRED, DraftReadinessIssue.WRITER_STATE_UNKNOWN)
    # WorkState.ACTIVE is live programme work, not an active source edit lease.
    # A source-qualified Draft inside an ACTIVE programme stays reviewable, so
    # only the distinct source_writer_active fact (or its unknown state, which
    # is reconciled above) holds a Draft in place.  Requiring a terminal work
    # state before Ready would recreate a Draft/release deadlock.
    if facts.source_writer_active:
        return _draft_assessment(DraftReadinessVerdict.KEEP_DRAFT, DraftReadinessIssue.SOURCE_WRITER_ACTIVE)
    if facts.scope_complete is None:
        return _draft_assessment(DraftReadinessVerdict.RECONCILE_REQUIRED, DraftReadinessIssue.SCOPE_COMPLETENESS_UNKNOWN)
    if not facts.scope_complete:
        return _draft_assessment(DraftReadinessVerdict.KEEP_DRAFT, DraftReadinessIssue.SCOPE_INCOMPLETE)
    if facts.qualified_head_sha is None:
        return _draft_assessment(DraftReadinessVerdict.RECONCILE_REQUIRED, DraftReadinessIssue.QUALIFICATION_MISSING)
    if facts.qualified_head_sha != facts.current_head_sha:
        return _draft_assessment(DraftReadinessVerdict.KEEP_DRAFT, DraftReadinessIssue.QUALIFICATION_STALE)
    return _draft_assessment(DraftReadinessVerdict.READY_CANDIDATE, DraftReadinessIssue.SOURCE_QUALIFIED)
