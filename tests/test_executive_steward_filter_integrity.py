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
