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
    LifecycleIssue,
    LifecycleVerdict,
    PreservationState,
    PullRequestLifecycleFacts,
    PullRequestState,
    SourceCoverage,
    WorkState,
    assess_draft_readiness,
    assess_pr_lifecycle,
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


@pytest.mark.parametrize("changes, readiness, verdict, reason", [
    (dict(draft=False), {}, DraftReadinessVerdict.NO_ACTION, DraftReadinessIssue.ALREADY_READY),
    (dict(state=PullRequestState.CLOSED), {}, DraftReadinessVerdict.NO_ACTION, DraftReadinessIssue.PR_NOT_OPEN),
    (dict(work_state=WorkState.UNKNOWN), {}, DraftReadinessVerdict.RECONCILE_REQUIRED, DraftReadinessIssue.WORK_STATE_UNKNOWN),
    (dict(work_state=WorkState.ACTIVE), dict(source_writer_active=True), DraftReadinessVerdict.KEEP_DRAFT, DraftReadinessIssue.SOURCE_WRITER_ACTIVE),
    (dict(source_coverage=SourceCoverage.PARTIAL), {}, DraftReadinessVerdict.RECONCILE_REQUIRED, DraftReadinessIssue.SOURCE_NOT_FULLY_READ),
    (dict(prior_effect_state=EffectState.EFFECT_UNKNOWN), {}, DraftReadinessVerdict.RECONCILE_REQUIRED, DraftReadinessIssue.PREVIOUS_EFFECT_UNKNOWN),
    (dict(explicit_disposition=ExplicitDisposition.NEVER_MERGE), {}, DraftReadinessVerdict.KEEP_DRAFT, DraftReadinessIssue.NEVER_MERGE),
])
def test_existing_lifecycle_holds_prevent_ready(changes, readiness, verdict, reason):
    x = assess_draft_readiness(ready(lifecycle=pr(**changes), **readiness))
    assert x.verdict is verdict
    assert x.issues == (reason,)


def test_active_work_state_with_no_source_writer_is_a_ready_candidate():
    """ACTIVE is live programme work, not an active source edit lease.

    A source-qualified Draft inside an ACTIVE programme must stay reviewable.
    Requiring the work state to become terminal before Ready would recreate a
    Draft/release deadlock for a carrier that is already source-qualified.
    """
    x = assess_draft_readiness(
        ready(lifecycle=pr(work_state=WorkState.ACTIVE), source_writer_active=False)
    )
    assert x.verdict is DraftReadinessVerdict.READY_CANDIDATE
    assert x.issues == (DraftReadinessIssue.SOURCE_QUALIFIED,)


@pytest.mark.parametrize("lifecycle, readiness, verdict, reason", [
    (dict(work_state=WorkState.ACTIVE), dict(source_writer_active=None), DraftReadinessVerdict.RECONCILE_REQUIRED, DraftReadinessIssue.WRITER_STATE_UNKNOWN),
    (dict(work_state=WorkState.ACTIVE), dict(explicit_draft_hold=True), DraftReadinessVerdict.KEEP_DRAFT, DraftReadinessIssue.DRAFT_HELD),
    (dict(work_state=WorkState.ACTIVE), dict(scope_complete=False), DraftReadinessVerdict.KEEP_DRAFT, DraftReadinessIssue.SCOPE_INCOMPLETE),
    (dict(work_state=WorkState.ACTIVE), dict(qualified_head_sha=OLD_HEAD), DraftReadinessVerdict.KEEP_DRAFT, DraftReadinessIssue.QUALIFICATION_STALE),
    (dict(work_state=WorkState.ACTIVE, prior_effect_state=EffectState.EFFECT_UNKNOWN), {}, DraftReadinessVerdict.RECONCILE_REQUIRED, DraftReadinessIssue.PREVIOUS_EFFECT_UNKNOWN),
])
def test_active_work_state_retains_other_blocking_evidence(lifecycle, readiness, verdict, reason):
    x = assess_draft_readiness(ready(lifecycle=pr(**lifecycle), **readiness))
    assert x.verdict is verdict
    assert x.issues == (reason,)


def test_active_work_state_still_keeps_the_lifecycle_carrier_open():
    """Readiness repair must not disturb the existing lifecycle closure."""
    closure = assess_pr_lifecycle(pr(work_state=WorkState.ACTIVE))
    assert closure.verdict is LifecycleVerdict.KEEP_ACTIVE
    assert closure.issues == (LifecycleIssue.ACTIVE_WORK,)


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


# Parent-adjudicated vectors from the separate bounded fixture worker. State
# fields below use the actual enum contract, never coercion of raw strings/null.
@pytest.mark.parametrize("case, work_state, lifecycle, qualification, verdict, issue", [
    ("active", WorkState.ACTIVE, {}, {}, "READY_CANDIDATE", "SOURCE_QUALIFIED"),
    ("closed", WorkState.ACTIVE, {"state": PullRequestState.CLOSED}, {}, "NO_ACTION", "PR_NOT_OPEN"),
    ("merged", WorkState.ACTIVE, {"state": PullRequestState.MERGED, "merged": True}, {}, "NO_ACTION", "PR_NOT_OPEN"),
    ("state-unknown", WorkState.ACTIVE, {"state": PullRequestState.UNKNOWN}, {}, "RECONCILE_REQUIRED", "WORK_STATE_UNKNOWN"),
    ("already-ready", WorkState.ACTIVE, {"draft": False}, {}, "NO_ACTION", "ALREADY_READY"),
    ("partial-source", WorkState.ACTIVE, {"source_coverage": SourceCoverage.PARTIAL}, {}, "RECONCILE_REQUIRED", "SOURCE_NOT_FULLY_READ"),
    ("effect-unknown", WorkState.ACTIVE, {"prior_effect_state": EffectState.EFFECT_UNKNOWN}, {}, "RECONCILE_REQUIRED", "PREVIOUS_EFFECT_UNKNOWN"),
    ("work-unknown", WorkState.UNKNOWN, {}, {}, "RECONCILE_REQUIRED", "WORK_STATE_UNKNOWN"),
    ("work-none", WorkState.NONE, {}, {}, "READY_CANDIDATE", "SOURCE_QUALIFIED"),
    ("work-gated", WorkState.GATED, {}, {}, "READY_CANDIDATE", "SOURCE_QUALIFIED"),
    ("work-terminal", WorkState.TERMINAL, {}, {}, "READY_CANDIDATE", "SOURCE_QUALIFIED"),
    ("never-merge", WorkState.ACTIVE, {"explicit_disposition": ExplicitDisposition.NEVER_MERGE}, {}, "KEEP_DRAFT", "NEVER_MERGE"),
    ("close-unmerged", WorkState.ACTIVE, {"explicit_disposition": ExplicitDisposition.CLOSE_UNMERGED}, {}, "KEEP_DRAFT", "NEVER_MERGE"),
    ("head-unknown", WorkState.ACTIVE, {}, {"current_head_sha": None}, "RECONCILE_REQUIRED", "CURRENT_HEAD_UNVERIFIED"),
    ("hold-unknown", WorkState.ACTIVE, {}, {"explicit_draft_hold": None}, "RECONCILE_REQUIRED", "DRAFT_HOLD_UNVERIFIED"),
    ("held", WorkState.ACTIVE, {}, {"explicit_draft_hold": True}, "KEEP_DRAFT", "DRAFT_HELD"),
    ("writer-unknown", WorkState.ACTIVE, {}, {"source_writer_active": None}, "RECONCILE_REQUIRED", "WRITER_STATE_UNKNOWN"),
    ("writer-active", WorkState.ACTIVE, {}, {"source_writer_active": True}, "KEEP_DRAFT", "SOURCE_WRITER_ACTIVE"),
    ("scope-unknown", WorkState.ACTIVE, {}, {"scope_complete": None}, "RECONCILE_REQUIRED", "SCOPE_COMPLETENESS_UNKNOWN"),
    ("scope-incomplete", WorkState.ACTIVE, {}, {"scope_complete": False}, "KEEP_DRAFT", "SCOPE_INCOMPLETE"),
    ("qualification-unknown", WorkState.ACTIVE, {}, {"qualified_head_sha": None}, "RECONCILE_REQUIRED", "QUALIFICATION_MISSING"),
    ("qualification-stale", WorkState.ACTIVE, {}, {"qualified_head_sha": OLD_HEAD}, "KEEP_DRAFT", "QUALIFICATION_STALE"),
    ("writer-before-stale", WorkState.ACTIVE, {}, {"source_writer_active": True, "qualified_head_sha": OLD_HEAD}, "KEEP_DRAFT", "SOURCE_WRITER_ACTIVE"),
    ("hold-before-scope", WorkState.ACTIVE, {}, {"explicit_draft_hold": True, "scope_complete": False}, "KEEP_DRAFT", "DRAFT_HELD"),
])
def test_parent_adjudicated_readiness_vectors(case, work_state, lifecycle, qualification, verdict, issue):
    result = assess_draft_readiness(
        ready(lifecycle=pr(work_state=work_state, **lifecycle), **qualification)
    )
    assert result.verdict.value == verdict, case
    assert tuple(item.value for item in result.issues) == (issue,), case


@pytest.mark.parametrize("invalid_state", [None, "closed", "merged"])
def test_raw_fixture_state_is_rejected_not_coerced(invalid_state):
    # Three raw generated vectors used non-enum states. Preserve the strict
    # validation contract rather than silently normalizing untrusted facts.
    with pytest.raises(LifecycleInputError):
        assess_draft_readiness(ready(lifecycle=pr(state=invalid_state)))
