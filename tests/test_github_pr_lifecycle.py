import pytest

from control_plane.github_pr_lifecycle import (
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
    assess_pr_lifecycle,
)


def facts(**overrides):
    base = dict(
        repository="mastermindx-market-intelligence/macro",
        number=999,
        state=PullRequestState.OPEN,
        merged=False,
        draft=True,
        work_state=WorkState.NONE,
        explicit_disposition=ExplicitDisposition.NONE,
        integration_state=IntegrationState.UNKNOWN,
        preservation_state=PreservationState.UNKNOWN,
        source_coverage=SourceCoverage.COMPLETE,
        prior_effect_state=EffectState.NONE,
        owner=None,
        gate=None,
        release_condition=None,
        days_since_update=30,
    )
    base.update(overrides)
    return PullRequestLifecycleFacts(**base)


def test_disposable_never_merge_with_no_preservation_obligation_is_close_candidate():
    result = assess_pr_lifecycle(
        facts(
            explicit_disposition=ExplicitDisposition.NEVER_MERGE,
            integration_state=IntegrationState.NOT_INTEGRATED,
            preservation_state=PreservationState.NOT_REQUIRED,
            work_state=WorkState.TERMINAL,
        )
    )

    assert result.verdict is LifecycleVerdict.CLOSE_CANDIDATE
    assert result.issues == (LifecycleIssue.EXPLICIT_CLOSE_DISPOSITION,)


def test_active_hold_wins_over_explicit_future_close():
    result = assess_pr_lifecycle(
        facts(
            work_state=WorkState.GATED,
            explicit_disposition=ExplicitDisposition.CLOSE_UNMERGED,
            preservation_state=PreservationState.NOT_REQUIRED,
            owner="ceo-sol",
            gate="same-carrier terminal edge",
            release_condition="SOL ACCEPTED / STOP",
        )
    )

    assert result.verdict is LifecycleVerdict.KEEP_GATED
    assert LifecycleIssue.ACTIVE_HOLD_OR_GATE in result.issues


def test_hold_missing_owner_or_release_condition_requires_reconciliation():
    result = assess_pr_lifecycle(
        facts(
            work_state=WorkState.GATED,
            owner="ceo-sol",
            gate="review required",
            release_condition=None,
        )
    )

    assert result.verdict is LifecycleVerdict.RECONCILE_REQUIRED
    assert LifecycleIssue.GATE_IDENTITY_INCOMPLETE in result.issues


def test_fully_integrated_terminal_carrier_is_close_candidate():
    result = assess_pr_lifecycle(
        facts(
            work_state=WorkState.TERMINAL,
            integration_state=IntegrationState.EXACTLY_INTEGRATED,
            preservation_state=PreservationState.PRESERVED,
        )
    )

    assert result.verdict is LifecycleVerdict.CLOSE_CANDIDATE
    assert result.issues == (LifecycleIssue.CURRENT_DELTA_ALREADY_INTEGRATED,)


def test_superseded_terminal_carrier_with_preserved_history_is_close_candidate():
    result = assess_pr_lifecycle(
        facts(
            work_state=WorkState.TERMINAL,
            integration_state=IntegrationState.SUPERSEDED_BY_CURRENT,
            preservation_state=PreservationState.PRESERVED,
        )
    )

    assert result.verdict is LifecycleVerdict.CLOSE_CANDIDATE
    assert result.issues == (LifecycleIssue.CURRENT_DELTA_SUPERSEDED,)


def test_unique_unpreserved_delta_is_not_closed_just_because_it_is_old():
    result = assess_pr_lifecycle(
        facts(
            work_state=WorkState.TERMINAL,
            integration_state=IntegrationState.NOT_INTEGRATED,
            preservation_state=PreservationState.UNPRESERVED,
            days_since_update=40,
        )
    )

    assert result.verdict is LifecycleVerdict.RECONCILE_REQUIRED
    assert LifecycleIssue.UNIQUE_OR_UNINTEGRATED_DELTA in result.issues
    assert LifecycleIssue.PRESERVATION_UNPROVEN in result.issues
    assert LifecycleIssue.STALE_AGE_ONLY in result.issues


def test_age_alone_never_authorizes_close():
    result = assess_pr_lifecycle(
        facts(
            work_state=WorkState.UNKNOWN,
            days_since_update=365,
        )
    )

    assert result.verdict is LifecycleVerdict.RECONCILE_REQUIRED
    assert result.issues == (
        LifecycleIssue.CURRENT_WORK_STATE_UNKNOWN,
        LifecycleIssue.STALE_AGE_ONLY,
    )


def test_effect_unknown_blocks_close_candidate():
    result = assess_pr_lifecycle(
        facts(
            work_state=WorkState.TERMINAL,
            explicit_disposition=ExplicitDisposition.CLOSE_UNMERGED,
            preservation_state=PreservationState.NOT_REQUIRED,
            prior_effect_state=EffectState.EFFECT_UNKNOWN,
        )
    )

    assert result.verdict is LifecycleVerdict.RECONCILE_REQUIRED
    assert result.issues == (LifecycleIssue.PRIOR_EFFECT_UNKNOWN,)


def test_partial_source_coverage_fails_closed():
    result = assess_pr_lifecycle(
        facts(
            work_state=WorkState.TERMINAL,
            explicit_disposition=ExplicitDisposition.CLOSE_UNMERGED,
            preservation_state=PreservationState.NOT_REQUIRED,
            source_coverage=SourceCoverage.PARTIAL,
        )
    )

    assert result.verdict is LifecycleVerdict.RECONCILE_REQUIRED
    assert result.issues == (LifecycleIssue.SOURCE_COVERAGE_INCOMPLETE,)


def test_active_work_stays_open_even_when_old():
    result = assess_pr_lifecycle(
        facts(
            work_state=WorkState.ACTIVE,
            days_since_update=60,
            integration_state=IntegrationState.NOT_INTEGRATED,
            preservation_state=PreservationState.UNPRESERVED,
        )
    )

    assert result.verdict is LifecycleVerdict.KEEP_ACTIVE
    assert result.issues == (LifecycleIssue.ACTIVE_WORK,)


def test_closed_or_merged_pr_is_out_of_open_estate():
    closed = assess_pr_lifecycle(
        facts(state=PullRequestState.CLOSED, work_state=WorkState.TERMINAL)
    )
    merged = assess_pr_lifecycle(
        facts(
            state=PullRequestState.MERGED,
            merged=True,
            work_state=WorkState.TERMINAL,
        )
    )

    assert closed.verdict is LifecycleVerdict.NOT_OPEN
    assert merged.verdict is LifecycleVerdict.NOT_OPEN


def test_validation_rejects_inconsistent_open_merged_state():
    with pytest.raises(LifecycleInputError):
        assess_pr_lifecycle(facts(merged=True))
