"""Fail-closed Draft reviewability in incumbent PR lifecycle owner."""
from dataclasses import replace

import pytest

from control_plane.github_pr_lifecycle import (
    DRAFT_READINESS_SCHEMA,
    DraftReadinessFacts,
    DraftReadinessIssue,
    DraftReadinessVerdict,
    EffectState,
    ExplicitDisposition,
    IntegrationState,
    LifecycleInputError,
    PreservationState,
    PullRequestLifecycleFacts,
    PullRequestState,
    SourceCoverage,
    WorkState,
    assess_draft_readiness,
)

HEAD = "a" * 40
OLD_HEAD = "b" * 40


def pr(**kwargs):
    props = dict(
        repository="mastermindx-market-intelligence/macro",
        number=10752,
        state=PullRequestState.OPEN,
        merged=False,
        draft=True,
        work_state=WorkState.NONE,
        explicit_disposition=ExplicitDisposition.NONE,
        integration_state=IntegrationState.UNKNOWN,
        preservation_state=PreservationState.UNKNOWN,
        source_coverage=SourceCoverage.COMPLETE,
        prior_effect_state=EffectState.NONE,
    )
    props.update(kwargs)
    return PullRequestLifecycleFacts(**props)


def ready(**kwargs):
    props = dict(
        lifecycle=pr(),
        current_head_sha=HEAD,
        qualified_head_sha=HEAD,
        scope_complete=True,
        explicit_draft_hold=False,
        source_writer_active=False,
    )
    props.update(kwargs)
    return DraftReadinessFacts(**props)


def test_exact_head_qualified_source_is_advisory_ready_candidate():
    x = assess_draft_readiness(ready())
    assert x.schema == DRAFT_READINESS_SCHEMA
    assert x.verdict is DraftReadinessVerdict.READY_CANDIDATE
    assert x.issues == (DraftReadinessIssue.SOURCE_QUALIFIED,)


@pytest.mark.parametrize("field, value, verdict, reason", [
    ("current_head_sha", None, DraftReadinessVerdict.RECONCILE_REQUIRED, DraftReadinessIssue.CURRENT_HEAD_UNVERIFIED),
    ("qualified_head_sha", None, DraftReadinessVerdict.RECONCILE_REQUIRED, DraftReadinessIssue.QUALIFICATION_MISSING),
    ("qualified_head_sha", OLD_HEAD, DraftReadinessVerdict.KEEP_DRAFT, DraftReadinessIssue.QUALIFICATION_STALE),
    ("explicit_draft_hold", None, DraftReadinessVerdict.RECONCILE_REQUIRED, DraftReadinessIssue.DRAFT_HOLD_UNVERIFIED),
    ("explicit_draft_hold", True, DraftReadinessVerdict.KEEP_DRAFT, DraftReadinessIssue.DRAFT_HELD),
    ("source_writer_active", None, DraftReadinessVerdict.RECONCILE_REQUIRED, DraftReadinessIssue.WRITER_STATE_UNKNOWN),
    ("source_writer_active", True, DraftReadinessVerdict.KEEP_DRAFT, DraftReadinessIssue.SOURCE_WRITER_ACTIVE),
    ("scope_complete", None, DraftReadinessVerdict.RECONCILE_REQUIRED, DraftReadinessIssue.SCOPE_COMPLETENESS_UNKNOWN),
    ("scope_complete", False, DraftReadinessVerdict.KEEP_DRAFT, DraftReadinessIssue.SCOPE_INCOMPLETE),
])
def test_missing_or_negative_source_evidence_fails_closed(field, value, verdict, reason):
    x = assess_draft_readiness(ready(**{field: value}))
    assert x.verdict is verdict
    assert x.issues == (reason,)


@pytest.mark.parametrize("changes, verdict, reason", [
    (dict(draft=False), DraftReadinessVerdict.NO_ACTION, DraftReadinessIssue.ALREADY_READY),
    (dict(state=PullRequestState.CLOSED), DraftReadinessVerdict.NO_ACTION, DraftReadinessIssue.PR_NOT_OPEN),
    (dict(work_state=WorkState.UNKNOWN), DraftReadinessVerdict.RECONCILE_REQUIRED, DraftReadinessIssue.WORK_STATE_UNKNOWN),
    (dict(work_state=WorkState.ACTIVE), DraftReadinessVerdict.KEEP_DRAFT, DraftReadinessIssue.SOURCE_WRITER_ACTIVE),
    (dict(source_coverage=SourceCoverage.PARTIAL), DraftReadinessVerdict.RECONCILE_REQUIRED, DraftReadinessIssue.SOURCE_NOT_FULLY_READ),
    (dict(prior_effect_state=EffectState.EFFECT_UNKNOWN), DraftReadinessVerdict.RECONCILE_REQUIRED, DraftReadinessIssue.PREVIOUS_EFFECT_UNKNOWN),
    (dict(explicit_disposition=ExplicitDisposition.NEVER_MERGE), DraftReadinessVerdict.KEEP_DRAFT, DraftReadinessIssue.NEVER_MERGE),
])
def test_existing_lifecycle_holds_prevent_ready(changes, verdict, reason):
    x = assess_draft_readiness(ready(lifecycle=pr(**changes)))
    assert x.verdict is verdict
    assert x.issues == (reason,)


@pytest.mark.parametrize("field, invalid", [
    ("current_head_sha", "deadbeef"),
    ("current_head_sha", "A" * 40),
    ("qualified_head_sha", ""),
    ("source_writer_active", 1),
    ("explicit_draft_hold", "false"),
    ("scope_complete", 0),
])
def test_untrusted_or_malformed_facts_rejected(field, invalid):
    with pytest.raises(LifecycleInputError):
        assess_draft_readiness(ready(**{field: invalid}))


def test_lifecycle_rejects_malformed_parent_and_never_infers_approval_or_release():
    with pytest.raises(LifecycleInputError):
        assess_draft_readiness(ready(lifecycle=replace(pr(), number=0)))
    assessment = assess_draft_readiness(ready(lifecycle=pr(work_state=WorkState.GATED)))
    assert assessment.verdict is DraftReadinessVerdict.READY_CANDIDATE
    # A separate CI/review/release owner must still make every downstream decision.
    assert all("MERGE" not in item.value for item in DraftReadinessVerdict)
