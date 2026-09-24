"""Focused filter-integrity regressions for the pure Executive Steward read core."""

from __future__ import annotations

from control_plane import executive_steward as steward


def _source(ref: str, *, freshness: steward.Freshness = steward.Freshness.CURRENT):
    return steward.SourceRef(
        owner=steward.SourceOwner.AGENT_OS,
        ref=ref,
        observed_at="2026-08-30T11:00:00Z",
        freshness=freshness,
    )


def _responsibility(
    ref: str,
    *,
    seat: steward.Seat,
    source_ref: str,
    freshness: steward.Freshness = steward.Freshness.CURRENT,
):
    return steward.ResponsibilityFact(
        responsibility_ref=ref,
        title=f"Responsibility {ref}",
        accountable_seat=seat,
        state="in_progress",
        root_job_id=f"JOB-{ref.removeprefix('WS:')}",
        source=_source(source_ref, freshness=freshness),
    )


def _attention(
    attention_id: str,
    *,
    ref: str,
    seat: steward.Seat,
    source_ref: str,
    freshness: steward.Freshness = steward.Freshness.CURRENT,
):
    return steward.AttentionFact(
        attention_id=attention_id,
        responsibility_ref=ref,
        target_seat=seat,
        kind="review_required",
        reason=f"Attention {attention_id} requires review.",
        source=steward.SourceRef(
            owner=steward.SourceOwner.EXECUTIVE_INBOX,
            ref=source_ref,
            observed_at="2026-08-30T11:01:00Z",
            freshness=freshness,
        ),
    )


def _issue(result, code: str):
    return next(issue for issue in result.issues if issue.code == code)


def test_filtered_responsibility_query_cannot_hide_cross_seat_identity_conflict():
    ceo = _responsibility(
        "WS:FILTER-INTEGRITY",
        seat=steward.Seat.CEO,
        source_ref="agentos:responsibility:ceo",
    )
    coo = _responsibility(
        "WS:FILTER-INTEGRITY",
        seat=steward.Seat.COO,
        source_ref="agentos:responsibility:coo",
    )
    snapshot = steward.ExecutiveStewardSnapshot(responsibilities=(ceo, coo))

    result = snapshot.list_responsibilities(target_seat=steward.Seat.CEO)

    assert result.status is steward.QueryStatus.DEGRADED
    assert result.data == ()
    issue = _issue(result, "ambiguous_responsibility_join")
    assert {source.ref for source in issue.sources} == {
        "agentos:responsibility:ceo",
        "agentos:responsibility:coo",
    }


def test_filtered_attention_query_cannot_hide_cross_seat_identity_conflict():
    responsibility = _responsibility(
        "WS:FILTER-INTEGRITY",
        seat=steward.Seat.CEO,
        source_ref="agentos:responsibility:one",
    )
    ceo = _attention(
        "attention-shared",
        ref="WS:FILTER-INTEGRITY",
        seat=steward.Seat.CEO,
        source_ref="executive-inbox:attention:ceo",
    )
    coo = _attention(
        "attention-shared",
        ref="WS:FILTER-INTEGRITY",
        seat=steward.Seat.COO,
        source_ref="executive-inbox:attention:coo",
    )
    snapshot = steward.ExecutiveStewardSnapshot(
        responsibilities=(responsibility,),
        attention=(ceo, coo),
    )

    result = snapshot.get_attention(target_seat=steward.Seat.CEO)

    assert result.status is steward.QueryStatus.DEGRADED
    assert result.data == ()
    issue = _issue(result, "ambiguous_attention_identity")
    assert {source.ref for source in issue.sources} == {
        "executive-inbox:attention:ceo",
        "executive-inbox:attention:coo",
    }


def test_responsibility_filter_cannot_hide_attention_identity_conflict():
    alpha = _responsibility(
        "WS:ALPHA",
        seat=steward.Seat.CEO,
        source_ref="agentos:responsibility:alpha",
    )
    beta = _responsibility(
        "WS:BETA",
        seat=steward.Seat.CEO,
        source_ref="agentos:responsibility:beta",
    )
    alpha_attention = _attention(
        "attention-cross-workstream",
        ref="WS:ALPHA",
        seat=steward.Seat.CEO,
        source_ref="executive-inbox:attention:alpha",
    )
    beta_attention = _attention(
        "attention-cross-workstream",
        ref="WS:BETA",
        seat=steward.Seat.CEO,
        source_ref="executive-inbox:attention:beta",
    )
    snapshot = steward.ExecutiveStewardSnapshot(
        responsibilities=(alpha, beta),
        attention=(alpha_attention, beta_attention),
    )

    result = snapshot.get_attention(responsibility_ref="WS:ALPHA")

    assert result.status is steward.QueryStatus.DEGRADED
    assert result.data == ()
    issue = _issue(result, "ambiguous_attention_identity")
    assert {source.ref for source in issue.sources} == {
        "executive-inbox:attention:alpha",
        "executive-inbox:attention:beta",
    }


def test_stale_orphan_candidate_participates_before_attention_join_pruning():
    responsibility = _responsibility(
        "WS:ALPHA",
        seat=steward.Seat.CEO,
        source_ref="agentos:responsibility:alpha",
    )
    current = _attention(
        "attention-orphan-conflict",
        ref="WS:ALPHA",
        seat=steward.Seat.CEO,
        source_ref="executive-inbox:attention:current",
    )
    stale_orphan = _attention(
        "attention-orphan-conflict",
        ref="WS:ORPHAN",
        seat=steward.Seat.CEO,
        source_ref="executive-inbox:attention:stale-orphan",
        freshness=steward.Freshness.STALE,
    )
    snapshot = steward.ExecutiveStewardSnapshot(
        responsibilities=(responsibility,),
        attention=(current, stale_orphan),
    )

    result = snapshot.get_attention(responsibility_ref="WS:ALPHA")

    assert result.status is steward.QueryStatus.DEGRADED
    assert result.data == ()
    issue = _issue(result, "ambiguous_attention_identity")
    assert {source.ref for source in issue.sources} == {
        "executive-inbox:attention:current",
        "executive-inbox:attention:stale-orphan",
    }


def test_ambiguous_identity_is_order_stable_and_unrelated_identity_survives():
    responsibility = _responsibility(
        "WS:ALPHA",
        seat=steward.Seat.CEO,
        source_ref="agentos:responsibility:alpha",
    )
    conflicting_ceo = _attention(
        "attention-conflict",
        ref="WS:ALPHA",
        seat=steward.Seat.CEO,
        source_ref="executive-inbox:attention:conflict-ceo",
    )
    conflicting_coo = _attention(
        "attention-conflict",
        ref="WS:ALPHA",
        seat=steward.Seat.COO,
        source_ref="executive-inbox:attention:conflict-coo",
    )
    unique = _attention(
        "attention-unique",
        ref="WS:ALPHA",
        seat=steward.Seat.CEO,
        source_ref="executive-inbox:attention:unique",
    )

    left = steward.ExecutiveStewardSnapshot(
        responsibilities=(responsibility,),
        attention=(conflicting_ceo, conflicting_coo, unique),
    ).get_attention(target_seat=steward.Seat.CEO)
    right = steward.ExecutiveStewardSnapshot(
        responsibilities=(responsibility,),
        attention=(unique, conflicting_coo, conflicting_ceo),
    ).get_attention(target_seat=steward.Seat.CEO)

    assert left.to_dict() == right.to_dict()
    assert [fact.attention_id for fact in left.data] == ["attention-unique"]
    issue = _issue(left, "ambiguous_attention_identity")
    assert {source.ref for source in issue.sources} == {
        "executive-inbox:attention:conflict-ceo",
        "executive-inbox:attention:conflict-coo",
    }


def test_responsibility_identity_conflict_survives_both_seat_filters_and_unfiltered():
    ceo = _responsibility(
        "WS:SYMMETRIC-RESPONSIBILITY",
        seat=steward.Seat.CEO,
        source_ref="agentos:responsibility:symmetric-ceo",
    )
    chairman = _responsibility(
        "WS:SYMMETRIC-RESPONSIBILITY",
        seat=steward.Seat.CHAIRMAN,
        source_ref="agentos:responsibility:symmetric-chairman",
    )
    snapshot = steward.ExecutiveStewardSnapshot(
        responsibilities=(ceo, chairman),
    )
    expected_sources = {
        "agentos:responsibility:symmetric-ceo",
        "agentos:responsibility:symmetric-chairman",
    }

    for target_seat in (steward.Seat.CEO, steward.Seat.CHAIRMAN, None):
        result = snapshot.list_responsibilities(target_seat=target_seat)

        assert result.status is steward.QueryStatus.DEGRADED
        assert result.data == ()
        issue = _issue(result, "ambiguous_responsibility_join")
        assert {source.ref for source in issue.sources} == expected_sources


def test_attention_identity_conflict_survives_both_seat_filters_and_unfiltered():
    responsibility = _responsibility(
        "WS:SYMMETRIC-ATTENTION-SEAT",
        seat=steward.Seat.CEO,
        source_ref="agentos:responsibility:attention-seat",
    )
    ceo = _attention(
        "attention-symmetric-seat",
        ref="WS:SYMMETRIC-ATTENTION-SEAT",
        seat=steward.Seat.CEO,
        source_ref="executive-inbox:attention:symmetric-ceo",
    )
    chairman = _attention(
        "attention-symmetric-seat",
        ref="WS:SYMMETRIC-ATTENTION-SEAT",
        seat=steward.Seat.CHAIRMAN,
        source_ref="executive-inbox:attention:symmetric-chairman",
    )
    snapshot = steward.ExecutiveStewardSnapshot(
        responsibilities=(responsibility,),
        attention=(ceo, chairman),
    )
    expected_sources = {
        "executive-inbox:attention:symmetric-ceo",
        "executive-inbox:attention:symmetric-chairman",
    }

    for target_seat in (steward.Seat.CEO, steward.Seat.CHAIRMAN, None):
        result = snapshot.get_attention(target_seat=target_seat)

        assert result.status is steward.QueryStatus.DEGRADED
        assert result.data == ()
        issue = _issue(result, "ambiguous_attention_identity")
        assert {source.ref for source in issue.sources} == expected_sources


def test_attention_identity_conflict_survives_both_responsibility_filters_and_unfiltered():
    alpha = _responsibility(
        "WS:SYMMETRIC-ALPHA",
        seat=steward.Seat.CEO,
        source_ref="agentos:responsibility:symmetric-alpha",
    )
    beta = _responsibility(
        "WS:SYMMETRIC-BETA",
        seat=steward.Seat.CEO,
        source_ref="agentos:responsibility:symmetric-beta",
    )
    alpha_attention = _attention(
        "attention-symmetric-responsibility",
        ref="WS:SYMMETRIC-ALPHA",
        seat=steward.Seat.CEO,
        source_ref="executive-inbox:attention:symmetric-alpha",
    )
    beta_attention = _attention(
        "attention-symmetric-responsibility",
        ref="WS:SYMMETRIC-BETA",
        seat=steward.Seat.CEO,
        source_ref="executive-inbox:attention:symmetric-beta",
    )
    snapshot = steward.ExecutiveStewardSnapshot(
        responsibilities=(alpha, beta),
        attention=(alpha_attention, beta_attention),
    )
    expected_sources = {
        "executive-inbox:attention:symmetric-alpha",
        "executive-inbox:attention:symmetric-beta",
    }

    for responsibility_ref in ("WS:SYMMETRIC-ALPHA", "WS:SYMMETRIC-BETA", None):
        result = snapshot.get_attention(responsibility_ref=responsibility_ref)

        assert result.status is steward.QueryStatus.DEGRADED
        assert result.data == ()
        issue = _issue(result, "ambiguous_attention_identity")
        assert {source.ref for source in issue.sources} == expected_sources


def test_stale_orphan_identity_conflict_survives_filter_and_join_pruning():
    responsibility = _responsibility(
        "WS:STALE-ORPHAN-PRIMARY",
        seat=steward.Seat.CEO,
        source_ref="agentos:responsibility:stale-orphan-primary",
    )
    current = _attention(
        "attention-stale-orphan-symmetric",
        ref="WS:STALE-ORPHAN-PRIMARY",
        seat=steward.Seat.CEO,
        source_ref="executive-inbox:attention:stale-orphan-current",
    )
    stale_orphan = _attention(
        "attention-stale-orphan-symmetric",
        ref="WS:STALE-ORPHAN-MISSING",
        seat=steward.Seat.CEO,
        source_ref="executive-inbox:attention:stale-orphan-conflict",
        freshness=steward.Freshness.STALE,
    )
    snapshot = steward.ExecutiveStewardSnapshot(
        responsibilities=(responsibility,),
        attention=(current, stale_orphan),
    )
    expected_sources = {
        "executive-inbox:attention:stale-orphan-current",
        "executive-inbox:attention:stale-orphan-conflict",
    }

    queries = (
        {"target_seat": steward.Seat.CEO},
        {"responsibility_ref": "WS:STALE-ORPHAN-PRIMARY"},
        {"responsibility_ref": "WS:STALE-ORPHAN-MISSING"},
        {},
    )
    for query in queries:
        result = snapshot.get_attention(**query)

        assert result.status is steward.QueryStatus.DEGRADED
        assert result.data == ()
        issue = _issue(result, "ambiguous_attention_identity")
        assert {source.ref for source in issue.sources} == expected_sources


def test_filter_before_grouping_mutation_guard_covers_both_public_queries():
    responsibility_ceo = _responsibility(
        "WS:MUTATION-GUARD",
        seat=steward.Seat.CEO,
        source_ref="agentos:responsibility:mutation-ceo",
    )
    responsibility_chairman = _responsibility(
        "WS:MUTATION-GUARD",
        seat=steward.Seat.CHAIRMAN,
        source_ref="agentos:responsibility:mutation-chairman",
    )
    responsibility_result = steward.ExecutiveStewardSnapshot(
        responsibilities=(responsibility_ceo, responsibility_chairman),
    ).list_responsibilities(target_seat=steward.Seat.CEO)

    assert responsibility_result.status is steward.QueryStatus.DEGRADED
    assert responsibility_result.data == ()
    responsibility_issue = _issue(
        responsibility_result,
        "ambiguous_responsibility_join",
    )
    assert {source.ref for source in responsibility_issue.sources} == {
        "agentos:responsibility:mutation-ceo",
        "agentos:responsibility:mutation-chairman",
    }

    alpha = _responsibility(
        "WS:MUTATION-ALPHA",
        seat=steward.Seat.CEO,
        source_ref="agentos:responsibility:mutation-alpha",
    )
    beta = _responsibility(
        "WS:MUTATION-BETA",
        seat=steward.Seat.CEO,
        source_ref="agentos:responsibility:mutation-beta",
    )
    alpha_attention = _attention(
        "attention-mutation-guard",
        ref="WS:MUTATION-ALPHA",
        seat=steward.Seat.CEO,
        source_ref="executive-inbox:attention:mutation-alpha",
    )
    beta_attention = _attention(
        "attention-mutation-guard",
        ref="WS:MUTATION-BETA",
        seat=steward.Seat.CEO,
        source_ref="executive-inbox:attention:mutation-beta",
    )
    attention_result = steward.ExecutiveStewardSnapshot(
        responsibilities=(alpha, beta),
        attention=(alpha_attention, beta_attention),
    ).get_attention(responsibility_ref="WS:MUTATION-ALPHA")

    assert attention_result.status is steward.QueryStatus.DEGRADED
    assert attention_result.data == ()
    attention_issue = _issue(attention_result, "ambiguous_attention_identity")
    assert {source.ref for source in attention_issue.sources} == {
        "executive-inbox:attention:mutation-alpha",
        "executive-inbox:attention:mutation-beta",
    }
