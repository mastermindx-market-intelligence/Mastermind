"""Contract tests for the pure Autonomy Control Room projection.

Frozen spec: ``PHASE_A_FROZEN_SPEC.md`` (operation
``ad-cr1a-zero-slack-autonomy-cockpit-20260901-claude3-002``).  Every test
here constructs an :class:`control_plane.executive_steward.
ExecutiveStewardSnapshot` directly and calls
:func:`control_plane.autonomy_control_room_projection.project_autonomy` —
fully offline, no I/O, no network, no clock dependence.
"""
from __future__ import annotations

import json

import pytest

from control_plane import autonomy_control_room_projection as proj
from control_plane import executive_steward as steward


# ---------------------------------------------------------------------------
# fixture helpers
# ---------------------------------------------------------------------------

def _source(owner: str, ref: str, *, observed_at="2026-09-01T00:00:00Z", freshness="CURRENT"):
    return steward.SourceRef(
        owner=getattr(steward.SourceOwner, owner),
        ref=ref,
        observed_at=observed_at,
        freshness=getattr(steward.Freshness, freshness),
    )


def _responsibility(
    *,
    ref="WS:AD-CR1A",
    title="Autonomy Control Room Phase A",
    seat="CHAIRMAN",
    state="active",
    root_job_id="JOB-AD-CR1A",
    observed_at="2026-09-01T00:00:00Z",
    freshness="CURRENT",
    source_ref=None,
):
    return steward.ResponsibilityFact(
        responsibility_ref=ref,
        title=title,
        accountable_seat=getattr(steward.Seat, seat),
        state=state,
        root_job_id=root_job_id,
        source=_source(
            "AGENT_OS",
            source_ref or f"agentos:{ref}",
            observed_at=observed_at,
            freshness=freshness,
        ),
    )


def _attention(
    *,
    attention_id,
    ref="WS:AD-CR1A",
    target="WORKER",
    kind="note",
    reason="An attention fact reason.",
    owner="EXECUTIVE_INBOX",
    observed_at="2026-09-01T00:00:00Z",
    freshness="CURRENT",
    source_ref=None,
):
    return steward.AttentionFact(
        attention_id=attention_id,
        responsibility_ref=ref,
        target_seat=getattr(steward.Seat, target),
        kind=kind,
        reason=reason,
        source=_source(
            owner,
            source_ref or f"{owner.lower()}:{attention_id}",
            observed_at=observed_at,
            freshness=freshness,
        ),
    )


def _runtime(
    *,
    ref="WS:AD-CR1A",
    root_job_id="JOB-AD-CR1A",
    seat="WORKER",
    attempt_id="ATT-1",
    worker_id="WORKER-1",
    status="RUNNING",
    effect_state="NONE",
    capacity_state="AVAILABLE",
    observed_at="2026-09-01T00:00:00Z",
    freshness="CURRENT",
    previous_attempt_id=None,
    movement_reason_code=None,
):
    return steward.RuntimeFact(
        responsibility_ref=ref,
        root_job_id=root_job_id,
        seat=getattr(steward.Seat, seat),
        attempt_id=attempt_id,
        worker_id=worker_id,
        status=status,
        session_alias="EXECUTIVE-ALIAS",
        runtime_binding_id=f"bind-{attempt_id}",
        binding_generation=1,
        continuation_state="ACKNOWLEDGED",
        effect_state=getattr(steward.EffectState, effect_state),
        capacity_state=getattr(steward.CapacityState, capacity_state),
        previous_attempt_id=previous_attempt_id,
        movement_reason_code=movement_reason_code,
        executive_source=_source(
            "EXECUTIVE_OS", f"executive:{attempt_id}", observed_at=observed_at, freshness=freshness
        ),
        binding_source=_source(
            "RUNTIME_BINDING", f"binding:{attempt_id}", observed_at=observed_at, freshness=freshness
        ),
    )


def _blocker(
    *,
    ref="WS:AD-CR1A",
    code="BLOCKED",
    explanation="A blocker explanation.",
    target="CHAIRMAN",
    effect_state="NONE",
    owner="EXECUTIVE_OS",
    observed_at="2026-09-01T00:00:00Z",
    freshness="CURRENT",
    source_ref=None,
):
    return steward.BlockerFact(
        responsibility_ref=ref,
        code=code,
        explanation=explanation,
        target_seat=getattr(steward.Seat, target),
        effect_state=getattr(steward.EffectState, effect_state),
        source=_source(
            owner,
            source_ref or f"{owner.lower()}:{code}",
            observed_at=observed_at,
            freshness=freshness,
        ),
    )


def _surface(
    *,
    ref="WS:AD-CR1A",
    role="CHAIRMAN",
    seat_ref=None,
    surface_ref="surface:1",
    provider="slack",
    locator_kind="permalink",
    reviewed_at="2026-09-01T00:00:00Z",
    observed_at="2026-09-01T00:00:00Z",
    freshness="CURRENT",
    source_ref=None,
):
    return steward.SurfaceFact(
        responsibility_ref=ref,
        role=getattr(steward.Seat, role),
        seat_ref=seat_ref,
        surface_ref=surface_ref,
        provider=provider,
        locator_kind=locator_kind,
        reviewed_at=reviewed_at,
        source=_source(
            "SURFACE_BINDINGS",
            source_ref or f"surface:{ref}:{role}",
            observed_at=observed_at,
            freshness=freshness,
        ),
    )


def _failure(*, owner="WAKE", code="failure_code", explanation="A failure explanation.", source_ref="src:1", observed_at=None):
    return steward.SourceFailure(
        owner=getattr(steward.SourceOwner, owner),
        code=code,
        explanation=explanation,
        source_ref=source_ref,
        observed_at=observed_at,
    )


def _declared(
    *,
    ref="WS:AD-CR1A",
    code="blocked_by",
    explanation="A declared blocker explanation.",
    target_seat="coo",
    owner="AGENT_OS",
    observed_at="2026-09-01T00:00:00Z",
    freshness="CURRENT",
    source_ref=None,
):
    """One ``declared_blockers`` row — plain data, never a Steward fact.

    Matches the exact shape :func:`declared_blockers_from_agent_os_state`
    returns, for tests that exercise :func:`project_autonomy`'s
    ``declared_blockers`` parameter directly without going through the
    real-data mapper.
    """
    return {
        "code": code,
        "explanation": explanation,
        "target_seat": target_seat,
        "source": _source(
            owner,
            source_ref or f"agent_os_state.workstreams:{ref}.blocked_by",
            observed_at=observed_at,
            freshness=freshness,
        ),
    }


def _snapshot(**overrides):
    values = {
        "responsibilities": (),
        "attention": (),
        "runtimes": (),
        "blockers": (),
        "surfaces": (),
        "source_failures": (),
    }
    values.update(overrides)
    return steward.ExecutiveStewardSnapshot(**values)


def _card(doc, ref):
    for card in doc["responsibilities"]:
        if card["responsibility_ref"] == ref:
            return card
    raise AssertionError(f"no card for {ref} in {[c['responsibility_ref'] for c in doc['responsibilities']]}")


# ---------------------------------------------------------------------------
# the twelve adverse states (frozen spec §6)
# ---------------------------------------------------------------------------

def test_state_active():
    ref = "WS:ACTIVE-1"
    resp = _responsibility(ref=ref)
    worker = _runtime(ref=ref, seat="WORKER", attempt_id="ATT-W1", worker_id="WORKER-A")
    sol = _runtime(ref=ref, seat="CEO", attempt_id="ATT-C1", worker_id="WORKER-B")
    snap = _snapshot(responsibilities=(resp,), runtimes=(worker, sol))

    doc = proj.project_autonomy(snap, generated_at="G")
    card = _card(doc, ref)

    assert card["current_worker"] is not None
    assert card["current_worker"]["attempt_id"] == "ATT-W1"
    assert card["current_sol_target"] is not None
    assert card["current_sol_target"]["attempt_id"] == "ATT-C1"


def test_state_waiting_capacity():
    ref = "WS:WAIT-CAP"
    resp = _responsibility(ref=ref)
    # WAITING_CAPACITY is now a literal-token-only no-producer placement
    # (frozen spec §4.3 as amended by the Phase A repair packet) — no
    # invented "capacity:<state>" convention.
    att = _attention(
        attention_id="ATT-CAP-1", ref=ref, target="COO",
        kind="WAITING_CAPACITY", reason="Capacity is constrained.",
    )
    snap = _snapshot(responsibilities=(resp,), attention=(att,))

    doc = proj.project_autonomy(snap, generated_at="G")
    card = _card(doc, ref)

    assert card["current_worker"] is None
    assert card["placement_state"] == {
        "value": "WAITING_CAPACITY",
        "observable": True,
        "reason": "fact_literal_token",
    }
    # NO Chairman account-selection prompt: this is not chairman-targeted.
    assert card["owed_turn"]["seat"] == "coo"
    assert card["chairman_decision_required"] is False


def test_state_activation_refused_pre_submit():
    ref = "WS:ACT-REFUSED"
    resp = _responsibility(ref=ref)
    blocker = _blocker(
        ref=ref,
        code="ACTIVATION_REFUSED_PRE_SUBMIT",
        explanation="Activation was refused before submission.",
        target="CHAIRMAN",
        effect_state="NONE",
    )
    snap = _snapshot(responsibilities=(resp,), blockers=(blocker,))

    doc = proj.project_autonomy(snap, generated_at="G")
    card = _card(doc, ref)

    assert card["placement_state"] == {
        "value": "ACTIVATION_REFUSED_PRE_SUBMIT",
        "observable": True,
        "reason": "fact_literal_token",
    }
    assert card["blocker"] is not None
    assert card["blocker"]["effect_state"] == "none"


def test_state_effect_unknown():
    ref = "WS:EFFECT-UNKNOWN"
    resp = _responsibility(ref=ref)
    worker = _runtime(ref=ref, seat="WORKER", attempt_id="ATT-EU", effect_state="EFFECT_UNKNOWN")
    blocker = _blocker(
        ref=ref,
        code="RETRY_NOT_PERMITTED",
        explanation="Runtime effect is unknown; retry is not permitted until reconciliation.",
        target="CHAIRMAN",
        effect_state="EFFECT_UNKNOWN",
    )
    snap = _snapshot(responsibilities=(resp,), runtimes=(worker,), blockers=(blocker,))

    doc = proj.project_autonomy(snap, generated_at="G")
    card = _card(doc, ref)

    # current_worker is structurally null here — get_current_runtime refuses
    # rather than exposing a fact with effect_state == effect_unknown.
    assert card["current_worker"] is None
    assert card["placement_state"]["value"] == "EFFECT_UNKNOWN"
    assert card["placement_state"]["observable"] is True

    # the card GENUINELY blocks retry/failover: the blocker redirects the
    # turn to the Chairman rather than leaving it as an automatic worker
    # retry — this is the actual retry-blocking mechanism, not just
    # fixture-string passthrough.
    assert card["owed_turn"]["seat"] == "chairman"
    assert card["owed_turn"]["reason"] == "blocker_targets_seat"
    assert card["chairman_decision_required"] is True
    assert card["chairman_decision_reason"] is not None

    assert card["blocker"] is not None
    assert card["blocker"]["target_seat"] == "chairman"
    assert card["blocker"]["effect_state"] == "effect_unknown"
    assert "retry" in card["blocker"]["explanation"].lower()
    assert "not permitted" in card["blocker"]["explanation"].lower()


def test_state_result_awaiting_sol_vs_sol_stop():
    ref_awaiting = "WS:AWAIT-SOL"
    ref_stop = "WS:SOL-STOP"
    resp_awaiting = _responsibility(ref=ref_awaiting)
    resp_stop = _responsibility(ref=ref_stop)
    att_awaiting = _attention(
        attention_id="ATT-AWAIT", ref=ref_awaiting, target="CEO",
        kind="result_awaiting_sol", reason="The result awaits Sol review.",
    )
    att_stop = _attention(
        attention_id="ATT-STOP", ref=ref_stop, target="CHAIRMAN",
        kind="sol_stop", reason="Sol has stopped this responsibility.",
    )
    snap = _snapshot(
        responsibilities=(resp_awaiting, resp_stop),
        attention=(att_awaiting, att_stop),
    )

    doc = proj.project_autonomy(snap, generated_at="G")
    card_awaiting = _card(doc, ref_awaiting)
    card_stop = _card(doc, ref_stop)

    assert card_awaiting["owed_turn"]["seat"] == "ceo"
    assert card_stop["owed_turn"]["seat"] == "chairman"
    assert card_awaiting["owed_turn"]["seat"] != card_stop["owed_turn"]["seat"]


def test_state_no_successor():
    ref = "WS:NO-SUCCESSOR"
    resp = _responsibility(ref=ref, state="active")
    snap = _snapshot(responsibilities=(resp,))

    doc = proj.project_autonomy(snap, generated_at="G")
    card = _card(doc, ref)

    assert card["state"] == "active"
    assert card["owed_turn"] == {
        "seat": "unknown", "reason": "no_owed_turn_signal", "source_refs": [],
    }


def test_state_stale():
    ref = "WS:STALE-1"
    resp = _responsibility(ref=ref, freshness="STALE")
    snap = _snapshot(responsibilities=(resp,))

    doc = proj.project_autonomy(snap, generated_at="G")
    card = _card(doc, ref)

    assert card["freshness"] == "stale"
    assert card["is_actionable"] is False
    assert card["actionability_reason"] == "stale_history"


def test_state_slack_outage():
    ref = "WS:SLACK-OUTAGE"
    resp = _responsibility(ref=ref, title="Canonical Title", state="in_progress")
    failure = _failure(
        owner="WAKE", code="wake_unavailable",
        explanation="Wake/Slack delivery channel is unavailable.",
        source_ref="wake:outage-1",
    )
    snap = _snapshot(responsibilities=(resp,), source_failures=(failure,))

    doc = proj.project_autonomy(snap, generated_at="G")
    card = _card(doc, ref)

    # canonical Agent OS / Executive truth stays visible and unchanged
    assert card["title"] == "Canonical Title"
    assert card["state"] == "in_progress"
    assert card["root_job_id"] == "JOB-AD-CR1A"

    # the failure is named at the top level, bounded to its owner
    assert doc["source_failures"] == [{
        "owner": "wake",
        "code": "wake_unavailable",
        "explanation": "Wake/Slack delivery channel is unavailable.",
        "source_ref": "wake:outage-1",
        "observed_at": None,
    }]

    # slack loss removes hot detail (attention/blocker queries consult WAKE)
    assert card["query_status"] != "ok"
    assert any(
        row["code"] == "wake_unavailable" and row["responsibility_ref"] == ref
        for row in doc["issues"]
    )


def test_state_conflicting_projections():
    ref = "WS:CONFLICTING"
    resp = _responsibility(ref=ref)
    att_a = _attention(
        attention_id="ATT-CONF-A", ref=ref, target="CEO", owner="WAKE",
        kind="DELIVERED_UNACKNOWLEDGED", reason="Wake reports delivered, unacknowledged.",
    )
    att_b = _attention(
        attention_id="ATT-CONF-B", ref=ref, target="CEO", owner="WAKE",
        kind="TARGET_ACKNOWLEDGED", reason="A later Wake read reports acknowledged.",
    )
    snap = _snapshot(responsibilities=(resp,), attention=(att_a, att_b))

    doc = proj.project_autonomy(snap, generated_at="G")
    card = _card(doc, ref)

    assert len(card["disagreements"]) == 1
    disagreement = card["disagreements"][0]
    assert disagreement["field"] == "wake_outcome"
    assert disagreement["values"] == ["DELIVERED_UNACKNOWLEDGED", "TARGET_ACKNOWLEDGED"]
    owners = {receipt["owner"] for receipt in disagreement["sources"]}
    assert owners == {"wake"}  # canonical owner identified
    assert len(disagreement["sources"]) == 2


def test_state_chairman_only_decision():
    ref = "WS:CHAIR-ONLY"
    resp = _responsibility(ref=ref)
    att = _attention(
        attention_id="ATT-CHAIR", ref=ref, target="CHAIRMAN",
        kind="needs_chairman_call", reason="Only the Chairman can decide this.",
    )
    snap = _snapshot(responsibilities=(resp,), attention=(att,))

    doc = proj.project_autonomy(snap, generated_at="G")
    card = _card(doc, ref)

    assert card["owed_turn"]["seat"] == "chairman"
    assert card["chairman_decision_required"] is True
    assert card["chairman_decision_reason"] is not None
    assert "chairman" in card["chairman_decision_reason"].lower()


def test_state_empty():
    snap = _snapshot()

    doc = proj.project_autonomy(snap, generated_at="G")

    assert doc["responsibilities"] == []
    assert doc["counts"] == {
        "total": 0, "actionable": 0, "stale": 0, "blocked": 0,
        "declared_blocked": 0, "empty": True,
    }
    assert doc["chairman_decisions"] == []
    assert doc["owed_by_seat"] == {
        "chairman": 0, "ceo": 0, "coo": 0, "worker": 0, "unknown": 0,
    }


def test_state_partial_source_failure():
    ref_ok = "WS:PARTIAL-OK"
    ref_touched = "WS:PARTIAL-TOUCHED"
    resp_ok = _responsibility(ref=ref_ok)
    resp_touched = _responsibility(ref=ref_touched)
    # ref_ok has its own, already-established owed turn (a live WORKER
    # runtime fact) — this is the genuinely-unaffected evidence a bounded
    # partial failure must never touch.
    worker_ok = _runtime(ref=ref_ok, seat="WORKER", attempt_id="ATT-PARTIAL-OK")
    failure = _failure(
        owner="EXECUTIVE_INBOX", code="inbox_unavailable",
        explanation="Executive Inbox read failed for this window.",
        source_ref="inbox:window-1",
    )
    snap = _snapshot(
        responsibilities=(resp_ok, resp_touched), runtimes=(worker_ok,),
        source_failures=(failure,),
    )

    doc = proj.project_autonomy(snap, generated_at="G")

    # exactly one, named, bounded failure at the top level
    assert doc["source_failures"] == [{
        "owner": "executive_inbox",
        "code": "inbox_unavailable",
        "explanation": "Executive Inbox read failed for this window.",
        "source_ref": "inbox:window-1",
        "observed_at": None,
    }]
    # both responsibilities still render — the failure never takes the
    # whole projection down.
    card_ok = _card(doc, ref_ok)
    card_touched = _card(doc, ref_touched)
    assert card_ok["title"] == "Autonomy Control Room Phase A"
    assert card_touched["title"] == "Autonomy Control Room Phase A"

    # "bounded" means genuinely unaffected, not identically-asserted: an
    # unrelated (EXECUTIVE_INBOX) owner's outage must never poison this
    # card's own canonical evidence freshness or erase its already-
    # established owed turn.  A mutation that force-degrades every card's
    # freshness to "unknown" (or blanket-suppresses actionability) whenever
    # ANY source failure exists anywhere must fail these assertions.
    assert card_ok["freshness"] == "current"
    assert card_touched["freshness"] == "current"
    assert card_ok["owed_turn"]["seat"] == "worker"
    assert card_ok["is_actionable"] is True
    assert card_ok["actionability_reason"] == "actionable"


# ---------------------------------------------------------------------------
# Phase A repair packet — dedicated regression tests (2026-09-01).
#
# Each test below reproduces the reviewer's exact triggering input for one
# numbered repair and asserts the corrected output.
# ---------------------------------------------------------------------------

def test_terminal_worker_status_does_not_assert_an_active_turn():
    """Repair 1a: owed_turn reason names PRESENCE, never ACTIVITY.

    The Steward exposes no terminal partition for RuntimeFact.status, so a
    crashed/completed runtime (status="CRASHED") is indistinguishable, at
    the Steward API, from a genuinely running one — the module must not
    claim the runtime is "active".
    """
    ref = "WS:TERMINAL-STATUS"
    resp = _responsibility(ref=ref)
    worker = _runtime(ref=ref, seat="WORKER", status="CRASHED")
    snap = _snapshot(responsibilities=(resp,), runtimes=(worker,))

    doc = proj.project_autonomy(snap, generated_at="G")
    card = _card(doc, ref)

    assert card["owed_turn"]["seat"] == "worker"
    assert card["owed_turn"]["reason"] == "worker_runtime_present"
    assert card["owed_turn"]["reason"] != "worker_runtime_active"


def test_chairman_decision_required_ignores_mere_runtime_presence():
    """Repair 1b: a present-but-unprovable-liveness runtime is not an
    automatic actor.

    owed_turn targets the Chairman (via a Chairman-targeted attention
    fact); a WORKER runtime fact is ALSO present (it could be crashed,
    completed, or genuinely running — the Steward cannot tell).  Presence
    alone must never suppress the Chairman decision: only a genuine
    CEO/COO-targeted attention fact may do that.
    """
    ref = "WS:CHAIR-WITH-RUNTIME-PRESENT"
    resp = _responsibility(ref=ref)
    att = _attention(
        attention_id="ATT-CHAIR-RT", ref=ref, target="CHAIRMAN",
        kind="needs_chairman_call", reason="Only the Chairman can decide this.",
    )
    worker = _runtime(ref=ref, seat="WORKER", status="CRASHED")
    snap = _snapshot(responsibilities=(resp,), attention=(att,), runtimes=(worker,))

    doc = proj.project_autonomy(snap, generated_at="G")
    card = _card(doc, ref)

    assert card["current_worker"] is not None
    assert card["owed_turn"]["seat"] == "chairman"
    assert card["chairman_decision_required"] is True
    assert card["chairman_decision_reason"] is not None
    assert "unprovable" in card["chairman_decision_reason"].lower()


def test_chairman_decision_required_is_suppressed_only_by_ceo_or_coo_attention():
    """Repair 1c: a real automatic actor (CEO/COO-targeted attention) DOES
    suppress the Chairman decision even though the winning owed_turn is
    still Chairman-targeted (smallest attention_id wins the seat)."""
    ref = "WS:CHAIR-WITH-CEO-ATTENTION"
    resp = _responsibility(ref=ref)
    att_chair = _attention(
        attention_id="AAA-CHAIR", ref=ref, target="CHAIRMAN", kind="chair_needed",
    )
    att_ceo = _attention(
        attention_id="ZZZ-CEO", ref=ref, target="CEO", kind="ceo_handling",
    )
    snap = _snapshot(responsibilities=(resp,), attention=(att_chair, att_ceo))

    doc = proj.project_autonomy(snap, generated_at="G")
    card = _card(doc, ref)

    assert card["owed_turn"]["seat"] == "chairman"  # AAA-CHAIR wins (smallest id)
    assert card["chairman_decision_required"] is False
    assert card["chairman_decision_reason"] is None


def test_stale_runtime_evidence_reaches_contributing_sources():
    """Repair 2: stale sources folded from cw_result.issues (stale_runtime_join)
    must actually degrade the card's freshness — they were previously
    invisible because get_current_runtime returns data=None when stale."""
    ref = "WS:STALE-RUNTIME-ONLY"
    resp = _responsibility(ref=ref)  # CURRENT
    worker = _runtime(ref=ref, seat="WORKER", freshness="STALE")
    snap = _snapshot(responsibilities=(resp,), runtimes=(worker,))

    doc = proj.project_autonomy(snap, generated_at="G")
    card = _card(doc, ref)

    # get_current_runtime degrades to data=None on stale evidence.
    assert card["current_worker"] is None
    assert card["freshness"] == "stale"
    assert card["is_actionable"] is False
    assert card["actionability_reason"] == "stale_history"
    assert doc["counts"]["stale"] == 1


def test_capacity_code_convention_is_deleted_not_inferred_from_runtime_absence():
    """Repair 3: the invented "capacity:<state>" convention is gone. A CEO
    runtime fact is present (so this is NOT even the old bug's narrowest
    case) and an attention fact carries the old convention's token — the
    module must never infer WAITING_CAPACITY from it, only from the literal
    "WAITING_CAPACITY" token."""
    ref = "WS:NO-INVENTED-CAPACITY-CODE"
    resp = _responsibility(ref=ref)
    sol = _runtime(ref=ref, seat="CEO", attempt_id="ATT-SOL")
    att = _attention(
        attention_id="ATT-OLD-CAP", ref=ref, target="COO",
        kind="capacity:degraded", reason="Old capacity-code convention token.",
    )
    snap = _snapshot(responsibilities=(resp,), runtimes=(sol,), attention=(att,))

    doc = proj.project_autonomy(snap, generated_at="G")
    card = _card(doc, ref)

    assert card["current_sol_target"] is not None
    assert card["current_worker"] is None
    assert card["placement_state"]["value"] != "WAITING_CAPACITY"
    assert card["placement_state"] == {
        "value": "not_observable", "observable": False, "reason": "no_canonical_producer",
    }


def test_effect_unknown_not_fabricated_from_caller_authored_source_failure_code():
    """Repair 4: a caller-authored SourceFailure whose code happens to equal
    the Steward's internal "reconciliation_required" issue code must never
    be mistaken for a genuine EFFECT_UNKNOWN runtime.  Two WORKER-seat
    runtime facts for the same ref force get_current_runtime to REFUSE via
    ambiguous_runtime_join, which appends this unrelated SourceFailure's
    issue onto the REFUSED result — the exact leak the reviewer proved."""
    ref = "WS:FAKE-EFFECT-UNKNOWN"
    resp = _responsibility(ref=ref)
    worker_a = _runtime(ref=ref, seat="WORKER", attempt_id="ATT-A")
    worker_b = _runtime(ref=ref, seat="WORKER", attempt_id="ATT-B")
    failure = _failure(
        owner="EXECUTIVE_OS", code="reconciliation_required",
        explanation="An unrelated Executive OS disruption this cycle.",
        source_ref="executive_os:unrelated-1",
    )
    snap = _snapshot(
        responsibilities=(resp,), runtimes=(worker_a, worker_b), source_failures=(failure,),
    )

    doc = proj.project_autonomy(snap, generated_at="G")
    card = _card(doc, ref)

    assert card["current_worker"] is None
    assert card["placement_state"]["value"] != "EFFECT_UNKNOWN"


def test_no_effect_unknown_fact_anywhere_never_produces_effect_unknown_placement():
    """Repair 4 (general property): a snapshot containing no fact with
    EffectState.EFFECT_UNKNOWN anywhere must never produce placement value
    EFFECT_UNKNOWN, even in the presence of an unrelated source failure."""
    ref = "WS:NO-EFFECT-UNKNOWN-ANYWHERE"
    resp = _responsibility(ref=ref)
    worker = _runtime(ref=ref, seat="WORKER", effect_state="NONE")
    failure = _failure(
        owner="AGENT_OS", code="reconciliation_required",
        explanation="A misleadingly-named, totally unrelated Agent OS hiccup.",
        source_ref="agentos:unrelated-1",
    )
    snap = _snapshot(responsibilities=(resp,), runtimes=(worker,), source_failures=(failure,))

    doc = proj.project_autonomy(snap, generated_at="G")

    for card in doc["responsibilities"]:
        assert card["placement_state"]["value"] != "EFFECT_UNKNOWN"


def test_wake_outcome_disagreement_requires_wake_owner_gate():
    """Repair 5: two EXECUTIVE_INBOX-owned (not WAKE-owned) attention facts
    carrying different WAKE_OUTCOME_TOKENS must never produce a
    wake_outcome disagreement — a card must never simultaneously report a
    field "not_observable" and report a disagreement about that field."""
    ref = "WS:NON-WAKE-DISAGREEMENT"
    resp = _responsibility(ref=ref)
    att_a = _attention(
        attention_id="ATT-NW-A", ref=ref, target="CEO", owner="EXECUTIVE_INBOX",
        kind="DELIVERED_UNACKNOWLEDGED", reason="Executive Inbox claims delivered.",
    )
    att_b = _attention(
        attention_id="ATT-NW-B", ref=ref, target="CEO", owner="EXECUTIVE_INBOX",
        kind="TARGET_ACKNOWLEDGED", reason="Executive Inbox claims acknowledged.",
    )
    snap = _snapshot(responsibilities=(resp,), attention=(att_a, att_b))

    doc = proj.project_autonomy(snap, generated_at="G")
    card = _card(doc, ref)

    assert card["wake_outcome"] == "not_observable"
    assert card["disagreements"] == []


def test_healthy_responsibilities_produce_no_routine_absence_issues():
    """Repair 7a: three healthy responsibilities with zero real problems
    must produce zero issues — routine-absence codes (surface_unknown,
    runtime_unknown, blocker_unknown) are noise, not problems."""
    resp_a = _responsibility(ref="WS:HEALTHY-A")
    resp_b = _responsibility(ref="WS:HEALTHY-B")
    resp_c = _responsibility(ref="WS:HEALTHY-C")
    snap = _snapshot(responsibilities=(resp_a, resp_b, resp_c))

    doc = proj.project_autonomy(snap, generated_at="G")

    assert doc["issues"] == []
    for card in doc["responsibilities"]:
        assert card["query_status"] == "ok"


# ---------------------------------------------------------------------------
# Change A (repair packet, 2026-09-01): a routine `runtime_root_missing`
# absence — an Agent-OS-owned responsibility with no Executive root job —
# must read as a routine absence, not a refusal, when it is the ONLY
# blocking signal on a get_current_runtime result.  Every genuinely bad
# get_current_runtime shape (EFFECT_UNKNOWN/reconciliation_required, every
# ambiguous_* join, and runtime_root_missing alongside a real second
# problem) must keep refusing exactly as before.
# ---------------------------------------------------------------------------

def test_runtime_root_missing_alone_is_a_routine_absence_not_a_refusal():
    """A responsibility with no root_job_id and no other problem reads
    query_status "ok", not "refused" — having no Executive root job is the
    ordinary state for an Agent-OS-owned responsibility, exactly like the
    routine runtime_unknown/blocker_unknown/surface_unknown absences this
    module already neutralizes.  current_worker/current_sol_target still
    read null (get_current_runtime's `.data` is still None either way),
    and the runtime_root_missing issue still appears on the top-level
    `issues` list as a receipt — only query_status/is_actionable change."""
    ref = "WS:NO-ROOT-JOB"
    resp = _responsibility(ref=ref, root_job_id=None)
    snap = _snapshot(responsibilities=(resp,))  # zero source_failures

    doc = proj.project_autonomy(snap, generated_at="G")
    card = _card(doc, ref)

    assert card["query_status"] == "ok"
    assert card["current_worker"] is None
    assert card["current_sol_target"] is None
    assert card["root_job_id"] is None
    assert card["actionability_reason"] != "query_refused"
    assert any(
        row["code"] == "runtime_root_missing" and row["responsibility_ref"] == ref
        for row in doc["issues"]
    )


def test_runtime_root_missing_alone_allows_actionability_when_otherwise_healthy():
    """The practical consequence of the fix: with no root_job_id but a
    genuine blocker targeting a seat (and nothing else wrong), the card is
    actually actionable — query_status "ok" is not merely cosmetic, it
    unblocks §4.4's is_actionable the same way a routine runtime_unknown
    already does."""
    ref = "WS:NO-ROOT-JOB-ACTIONABLE"
    resp = _responsibility(ref=ref, root_job_id=None)
    blocker = _blocker(ref=ref, code="NEEDS_CHAIRMAN_INPUT", target="CHAIRMAN")
    snap = _snapshot(responsibilities=(resp,), blockers=(blocker,))

    doc = proj.project_autonomy(snap, generated_at="G")
    card = _card(doc, ref)

    assert card["query_status"] == "ok"
    assert card["is_actionable"] is True
    assert card["actionability_reason"] == "actionable"


def test_effect_unknown_still_refuses_query_status_after_change_a():
    """Change A must never neutralize the EFFECT_UNKNOWN path: a real
    root_job_id join with a WORKER runtime fact whose effect_state is
    EFFECT_UNKNOWN still REFUSES via "reconciliation_required" (two issues
    would never apply here — it is one issue, but its code is NOT
    "runtime_root_missing", so the narrow guard never matches it) and
    still drives the card's query_status to "refused"."""
    ref = "WS:EFFECT-UNKNOWN-QS"
    resp = _responsibility(ref=ref)  # real root_job_id (JOB-AD-CR1A default)
    worker = _runtime(
        ref=ref, seat="WORKER", attempt_id="ATT-EU-QS", effect_state="EFFECT_UNKNOWN",
    )
    snap = _snapshot(responsibilities=(resp,), runtimes=(worker,))

    doc = proj.project_autonomy(snap, generated_at="G")
    card = _card(doc, ref)

    assert card["query_status"] == "refused"
    assert card["placement_state"]["value"] == "EFFECT_UNKNOWN"
    assert card["current_worker"] is None
    assert card["is_actionable"] is False


def test_ambiguous_runtime_join_still_refuses_query_status_after_change_a():
    """Change A must never neutralize an ambiguous join: two current WORKER
    runtime candidates for the same responsibility (a real root_job_id, so
    runtime_root_missing never fires) force "ambiguous_runtime_join",
    which must still REFUSE and still drive the card's query_status to
    "refused"."""
    ref = "WS:AMBIG-RUNTIME-QS"
    resp = _responsibility(ref=ref)
    worker_a = _runtime(ref=ref, seat="WORKER", attempt_id="ATT-QS-A")
    worker_b = _runtime(ref=ref, seat="WORKER", attempt_id="ATT-QS-B")
    snap = _snapshot(responsibilities=(resp,), runtimes=(worker_a, worker_b))

    doc = proj.project_autonomy(snap, generated_at="G")
    card = _card(doc, ref)

    assert card["query_status"] == "refused"
    assert card["current_worker"] is None
    assert card["is_actionable"] is False


def test_runtime_root_missing_with_a_genuine_second_problem_still_refuses():
    """The narrow guard requires runtime_root_missing to be the SOLE
    blocking signal.  Here root_job_id is None (so the internal
    runtime_root_missing issue fires) AND a genuine RUNTIME_BINDING
    SourceFailure is present — RUNTIME_BINDING is one of the three owners
    get_current_runtime always folds into `source_issues` regardless of
    responsibility_ref — so the REFUSED result carries two issues, not
    one, and must stay refused."""
    ref = "WS:NO-ROOT-JOB-PLUS-FAILURE"
    resp = _responsibility(ref=ref, root_job_id=None)
    failure = _failure(
        owner="RUNTIME_BINDING", code="runtime_binding_outage",
        explanation="A genuine, unrelated RuntimeBinding source failure.",
        source_ref="runtime_binding:outage-1",
    )
    snap = _snapshot(responsibilities=(resp,), source_failures=(failure,))

    doc = proj.project_autonomy(snap, generated_at="G")
    card = _card(doc, ref)

    assert card["query_status"] == "refused"
    assert card["current_worker"] is None


def test_issues_list_is_deduplicated_across_call_sites():
    """Repair 7b: one SourceFailure must produce exactly one named issue row
    per responsibility, never once per internal call site that happens to
    consult its owner."""
    ref = "WS:DEDUPE-ONE"
    resp = _responsibility(ref=ref)
    failure = _failure(
        owner="AGENT_OS", code="agentos_flaky",
        explanation="Agent OS read is intermittently flaky.",
        source_ref="agentos:flaky-1",
    )
    snap = _snapshot(responsibilities=(resp,), source_failures=(failure,))

    doc = proj.project_autonomy(snap, generated_at="G")
    card = _card(doc, ref)

    routine_codes = {"surface_unknown", "runtime_unknown", "blocker_unknown"}
    assert not any(row["code"] in routine_codes for row in doc["issues"])

    matching = [
        row for row in doc["issues"]
        if row["code"] == "agentos_flaky" and row["responsibility_ref"] == ref
    ]
    assert len(matching) == 1
    assert card["query_status"] != "ok"


def test_untagged_issue_never_infers_responsibility_ref_from_message_prose():
    """Repair 8: an ambiguous_responsibility_join issue's message names the
    ref in free text ("WS:AMBIGUOUS-JOIN has 2 canonical candidates..."),
    but the ambiguous ref is EXCLUDED from card membership entirely — the
    untagged issue must never regex-scrape identity out of that prose."""
    ref = "WS:AMBIGUOUS-JOIN"
    resp_1 = _responsibility(ref=ref, source_ref="agentos:candidate-1")
    resp_2 = _responsibility(ref=ref, source_ref="agentos:candidate-2")
    snap = _snapshot(responsibilities=(resp_1, resp_2))

    doc = proj.project_autonomy(snap, generated_at="G")

    assert all(c["responsibility_ref"] != ref for c in doc["responsibilities"])
    matching = [row for row in doc["issues"] if row["code"] == "ambiguous_responsibility_join"]
    assert len(matching) == 1
    assert matching[0]["responsibility_ref"] is None


def test_counts_empty_is_false_when_membership_suppressed_by_ambiguous_join():
    """Repair 9a: zero cards because the ONLY responsibility ref present is
    ambiguous must never read as "nothing to do"."""
    ref = "WS:ONLY-AMBIGUOUS"
    resp_1 = _responsibility(ref=ref, source_ref="agentos:candidate-1")
    resp_2 = _responsibility(ref=ref, source_ref="agentos:candidate-2")
    snap = _snapshot(responsibilities=(resp_1, resp_2))

    doc = proj.project_autonomy(snap, generated_at="G")

    assert doc["responsibilities"] == []
    assert doc["counts"]["total"] == 0
    assert doc["counts"]["empty"] is False


def test_counts_empty_is_false_when_membership_suppressed_by_source_failure():
    """Repair 9b: a total Agent OS outage (zero responsibility facts, but an
    AGENT_OS SourceFailure) must never read as "nothing to do" either."""
    failure = _failure(
        owner="AGENT_OS", code="agentos_unreachable",
        explanation="Agent OS is entirely unreachable this cycle.",
        source_ref="agentos:outage-1",
    )
    snap = _snapshot(source_failures=(failure,))

    doc = proj.project_autonomy(snap, generated_at="G")

    assert doc["responsibilities"] == []
    assert doc["counts"]["total"] == 0
    assert doc["counts"]["empty"] is False


def test_counts_empty_is_true_when_genuinely_idle():
    """Repair 9 control case: a totally empty snapshot with no suppressing
    issue or source failure must still read empty=True (matches the state
    11 adverse test, restated here beside its two suppressed siblings)."""
    snap = _snapshot()

    doc = proj.project_autonomy(snap, generated_at="G")

    assert doc["responsibilities"] == []
    assert doc["counts"]["total"] == 0
    assert doc["counts"]["empty"] is True


def test_counts_empty_is_false_when_zero_mapped_but_unmapped_rows_exist():
    """Change B (repair packet, 2026-09-01): zero mapped responsibilities
    with non-empty unmapped_responsibilities must never read empty=True —
    the estate was NOT idle, every workstream was suppressed for an
    unrecognized owner.  Same law as the two membership_suppressed cases
    above, applied to the unmapped-as-suppression case."""
    snap = _snapshot()  # zero responsibility facts, zero source failures
    unmapped_rows = [
        {"responsibility_ref": "WS:UNRECOGNIZED-1", "reason": "owner_not_a_recognized_seat"},
    ]

    doc = proj.project_autonomy(
        snap, generated_at="G", unmapped_responsibilities=unmapped_rows,
    )

    assert doc["responsibilities"] == []
    assert doc["counts"]["total"] == 0
    assert doc["counts"]["empty"] is False


def test_counts_empty_stays_true_for_a_genuinely_idle_estate_with_no_unmapped_rows():
    """Change B control case: an idle estate with nothing mapped, nothing
    suppressed by a Steward-level issue, AND nothing suppressed as
    unmapped (the default None — never supplied) must still read
    empty=True."""
    snap = _snapshot()

    doc = proj.project_autonomy(snap, generated_at="G")

    assert doc["responsibilities"] == []
    assert doc["counts"]["total"] == 0
    assert doc["counts"]["empty"] is True
    assert doc["unmapped_responsibilities"] == []


# ---------------------------------------------------------------------------
# Second adversarial review pass, Phase A repair packet (2026-09-01):
# Repair A (freshness-fold exclusion) and Repair B (routine-absence /
# source-failure collision guard) — dedicated regression tests, one per
# residual path the review proved.
# ---------------------------------------------------------------------------

def test_reconciliation_required_with_stale_runtime_sources_is_stale():
    """Repair A, residual path 1: EFFECT_UNKNOWN precedes the staleness
    check in ``get_current_runtime`` (executive_steward.py ~894-907), so a
    single WORKER runtime candidate with both effect_state=EFFECT_UNKNOWN
    AND stale executive_source/binding_source returns REFUSED with issue
    code "reconciliation_required" *before* the sibling "stale_runtime_
    join" branch is ever reached.  The old eight-code stale_* allowlist
    never folded "reconciliation_required"'s sources, so the card read
    freshness "current" despite its only runtime evidence being entirely
    stale."""
    ref = "WS:RECON-STALE"
    resp = _responsibility(ref=ref)  # CURRENT
    worker = _runtime(
        ref=ref, seat="WORKER", attempt_id="ATT-RECON-STALE",
        effect_state="EFFECT_UNKNOWN", freshness="STALE",
    )
    snap = _snapshot(responsibilities=(resp,), runtimes=(worker,))

    doc = proj.project_autonomy(snap, generated_at="G")
    card = _card(doc, ref)

    assert card["freshness"] == "stale"
    assert card["is_actionable"] is False
    assert card["actionability_reason"] == "stale_history"
    assert doc["counts"]["stale"] == 1


def test_ambiguous_runtime_join_with_stale_sources_is_stale():
    """Repair A, residual path 2: two WORKER runtime candidates for the
    same responsibility force "ambiguous_runtime_join" (REFUSED), which
    also precedes the staleness check.  Both candidates' executive_source/
    binding_source are stale — the card must read stale, not current."""
    ref = "WS:AMBIG-RUNTIME-STALE"
    resp = _responsibility(ref=ref)
    worker_a = _runtime(
        ref=ref, seat="WORKER", attempt_id="ATT-AMBIG-RT-A", freshness="STALE",
    )
    worker_b = _runtime(
        ref=ref, seat="WORKER", attempt_id="ATT-AMBIG-RT-B", freshness="STALE",
    )
    snap = _snapshot(responsibilities=(resp,), runtimes=(worker_a, worker_b))

    doc = proj.project_autonomy(snap, generated_at="G")
    card = _card(doc, ref)

    assert card["current_worker"] is None
    assert card["freshness"] == "stale"
    assert card["is_actionable"] is False
    assert card["actionability_reason"] == "stale_history"
    assert doc["counts"]["stale"] == 1


def test_ambiguous_blocker_join_with_stale_sources_is_stale():
    """Repair A, residual path 3: two blocker facts for the same
    responsibility force "ambiguous_blocker_join" (REFUSED) in
    ``explain_blocker``, which also precedes any staleness check.  Both
    candidates' sources are stale — the card must read stale."""
    ref = "WS:AMBIG-BLOCKER-STALE"
    resp = _responsibility(ref=ref)
    blocker_a = _blocker(
        ref=ref, code="BLOCK-A", target="CHAIRMAN", freshness="STALE",
        source_ref="executive_os:block-a",
    )
    blocker_b = _blocker(
        ref=ref, code="BLOCK-B", target="CHAIRMAN", freshness="STALE",
        source_ref="executive_os:block-b",
    )
    snap = _snapshot(responsibilities=(resp,), blockers=(blocker_a, blocker_b))

    doc = proj.project_autonomy(snap, generated_at="G")
    card = _card(doc, ref)

    assert card["blocker"] is None
    assert card["freshness"] == "stale"
    assert card["is_actionable"] is False
    assert card["actionability_reason"] == "stale_history"
    assert doc["counts"]["stale"] == 1


def test_runtime_root_mismatch_with_stale_runtime_is_stale():
    """Repair A, residual path 4: a single WORKER runtime candidate whose
    root_job_id does not join the responsibility's root_job_id forces
    "runtime_root_mismatch" (REFUSED) in ``get_current_runtime`` before any
    staleness check.  That one candidate's own sources are stale — the
    card must read stale."""
    ref = "WS:ROOT-MISMATCH-STALE"
    resp = _responsibility(ref=ref, root_job_id="JOB-CORRECT")
    worker = _runtime(
        ref=ref, seat="WORKER", attempt_id="ATT-ROOT-MISMATCH",
        root_job_id="JOB-WRONG", freshness="STALE",
    )
    snap = _snapshot(responsibilities=(resp,), runtimes=(worker,))

    doc = proj.project_autonomy(snap, generated_at="G")
    card = _card(doc, ref)

    assert card["current_worker"] is None
    assert card["freshness"] == "stale"
    assert card["is_actionable"] is False
    assert card["actionability_reason"] == "stale_history"
    assert doc["counts"]["stale"] == 1


def test_ambiguous_attention_identity_with_stale_attention_is_stale():
    """Repair A, residual path 5 (the reviewer's motivating exemplar): two
    AttentionFact rows sharing one attention_id force "ambiguous_attention_
    identity" in ``get_attention``, whose sources are both facts' own
    (stale) SourceRef.  This is the path that previously produced
    freshness "current", is_actionable True, actionability_reason
    "actionable", counts.stale 0 on a snapshot whose attention evidence
    was entirely stale."""
    ref = "WS:AMBIG-ATTENTION-STALE"
    resp = _responsibility(ref=ref)
    att_a = _attention(
        attention_id="ATT-DUP-ID", ref=ref, target="WORKER", kind="note_a",
        reason="First duplicate-identity attention fact.", freshness="STALE",
        source_ref="executive_inbox:dup-a",
    )
    att_b = _attention(
        attention_id="ATT-DUP-ID", ref=ref, target="WORKER", kind="note_b",
        reason="Second duplicate-identity attention fact.", freshness="STALE",
        source_ref="executive_inbox:dup-b",
    )
    snap = _snapshot(responsibilities=(resp,), attention=(att_a, att_b))

    doc = proj.project_autonomy(snap, generated_at="G")
    card = _card(doc, ref)

    assert card["freshness"] == "stale"
    assert card["is_actionable"] is False
    assert card["actionability_reason"] == "stale_history"
    assert doc["counts"]["stale"] == 1


def test_stale_surface_binding_does_not_stale_a_card_with_current_evidence():
    """Deliberate carve-out (module docstring point 5, point 7): a stale
    (or unreviewed) SURFACE_BINDINGS-owned surface binding is a navigation
    receipt, not evidence of the responsibility's own work state.  A card
    whose real work evidence (responsibility + current worker runtime) is
    entirely current must stay freshness "current" and is_actionable True
    even though its saved Chairman-facing surface is stale — the surface
    issue must still appear in the top-level issues list."""
    ref = "WS:SURFACE-CARVEOUT"
    resp = _responsibility(ref=ref)  # CURRENT
    worker = _runtime(ref=ref, seat="WORKER", attempt_id="ATT-SURFACE-CARVEOUT")  # CURRENT
    surface = _surface(ref=ref, role="CHAIRMAN", freshness="STALE")
    snap = _snapshot(responsibilities=(resp,), runtimes=(worker,), surfaces=(surface,))

    doc = proj.project_autonomy(snap, generated_at="G")
    card = _card(doc, ref)

    assert card["freshness"] == "current"
    assert card["query_status"] == "ok"
    assert card["is_actionable"] is True
    assert card["actionability_reason"] == "actionable"
    assert any(
        row["code"] == "stale_surface_binding" and row["responsibility_ref"] == ref
        for row in doc["issues"]
    )


def test_source_failure_coded_runtime_unknown_reaches_the_issues_list():
    """Repair B: a caller-authored SourceFailure whose free-text code
    collides with the routine-absence token "runtime_unknown" is a real
    outage (Executive OS runtime store unreachable), not a routine "no
    current runtime" absence — it must reach the top-level issues list,
    not vanish because ``_ROUTINE_ABSENCE_ISSUE_CODES`` matches on code
    alone."""
    ref = "WS:REPAIR-B-RUNTIME-UNKNOWN"
    resp = _responsibility(ref=ref)
    failure = _failure(
        owner="EXECUTIVE_OS", code="runtime_unknown",
        explanation="Executive OS runtime store is unreachable.",
        source_ref="executive_os:outage-1",
    )
    snap = _snapshot(responsibilities=(resp,), source_failures=(failure,))

    doc = proj.project_autonomy(snap, generated_at="G")

    matching = [
        row for row in doc["issues"]
        if row["code"] == "runtime_unknown"
        and row["message"] == "Executive OS runtime store is unreachable."
    ]
    assert len(matching) == 1
    assert matching[0]["responsibility_ref"] == ref


def test_source_failure_code_colliding_with_freshness_issue_does_not_poison_other_cards():
    """Repair A boundedness: ``_source_issues`` folds a matching-owner
    SourceFailure into EVERY card's per-seat/per-call issues, regardless of
    responsibility_ref (module docstring point 4).  A caller-authored
    SourceFailure whose code happens to collide with a genuine Steward-
    internal freshness-affecting code ("ambiguous_attention_identity") must
    still never fold into ANY card's freshness merely by being consulted —
    the ``code not in source_failure_codes`` exclusion (point 7) is what
    keeps the "bounded" partial-source-failure guarantee (frozen spec §6
    state 12) intact under the new exclusion-based fold.  Reverting the
    exclusion back to a blind fold-everything would drag both cards'
    freshness down to "unknown" (the failure's ``as_source()`` is
    hardcoded ``Freshness.UNKNOWN``), not merely "stale"."""
    ref_a = "WS:BOUND-COLLIDE-A"
    ref_b = "WS:BOUND-COLLIDE-B"
    resp_a = _responsibility(ref=ref_a)
    resp_b = _responsibility(ref=ref_b)
    worker_a = _runtime(ref=ref_a, seat="WORKER", attempt_id="ATT-BOUND-COLLIDE-A")
    failure = _failure(
        owner="WAKE", code="ambiguous_attention_identity",
        explanation="An unrelated Wake disruption this cycle.",
        source_ref="wake:unrelated-collide-1",
    )
    snap = _snapshot(
        responsibilities=(resp_a, resp_b), runtimes=(worker_a,), source_failures=(failure,),
    )

    doc = proj.project_autonomy(snap, generated_at="G")
    card_a = _card(doc, ref_a)
    card_b = _card(doc, ref_b)

    assert card_a["freshness"] == "current"
    assert card_b["freshness"] == "current"
    assert card_a["is_actionable"] is True
    assert card_a["actionability_reason"] == "actionable"


# ---------------------------------------------------------------------------
# determinism / ordering / OUTPUT_KEYS / purity
# ---------------------------------------------------------------------------

def test_determinism_is_byte_identical_json():
    ref = "WS:DETERMINISM"
    resp = _responsibility(ref=ref)
    worker = _runtime(ref=ref, seat="WORKER")
    att = _attention(attention_id="ATT-DET", ref=ref, target="COO", kind="note")
    blocker = _blocker(ref=ref, code="SOME_CODE", target="CEO")
    snap = _snapshot(
        responsibilities=(resp,), runtimes=(worker,), attention=(att,), blockers=(blocker,),
    )

    doc1 = proj.project_autonomy(snap, generated_at="2026-09-01T00:00:00Z")
    doc2 = proj.project_autonomy(snap, generated_at="2026-09-01T00:00:00Z")

    assert json.dumps(doc1, sort_keys=True) == json.dumps(doc2, sort_keys=True)


def test_responsibilities_ordering_is_total():
    """Frozen spec §5: sort key is (chairman_decision, actionable, seat_rank, ref).

    Refs are deliberately named so that a REF-ONLY ascending sort produces
    the exact reverse of the correct order — a mutation that drops any of
    the first three key components (chairman-decision-first, actionable,
    seat_rank) collapses to ref-only and must fail this test.
    """
    # Level 1 (chairman_decision_required) winner — worst ref ("Z...") but
    # must sort FIRST.
    ref_chair = "WS:ZZZ-CHAIR"
    resp_chair = _responsibility(ref=ref_chair)
    att_chair = _attention(
        attention_id="ATT-ORD-CHAIR", ref=ref_chair, target="CHAIRMAN", kind="x",
    )

    # Level 3 (seat_rank) pair: ceo (rank 1) must sort BEFORE worker
    # (rank 3) even though its ref ("Y...") is alphabetically AFTER the
    # worker refs ("C...").
    ref_ceo = "WS:YYY-CEO"
    resp_ceo = _responsibility(ref=ref_ceo)
    att_ceo = _attention(attention_id="ATT-ORD-CEO", ref=ref_ceo, target="CEO", kind="y")

    ref_worker_1 = "WS:CCC-WORKER"
    resp_worker_1 = _responsibility(ref=ref_worker_1)
    worker_1 = _runtime(ref=ref_worker_1, seat="WORKER", attempt_id="ATT-ORD-W1")

    # Ref tie-break within the same (chairman_decision, actionable,
    # seat_rank) bucket as ref_worker_1.
    ref_worker_2 = "WS:CCD-WORKER2"
    resp_worker_2 = _responsibility(ref=ref_worker_2)
    worker_2 = _runtime(ref=ref_worker_2, seat="WORKER", attempt_id="ATT-ORD-W2")

    # Level 2 (is_actionable) case: owed_turn seat is "unknown" (rank 4,
    # the worst) via a stale-runtime-only card, but its ref ("A...") is
    # alphabetically FIRST — must still sort LAST because it is not
    # actionable.
    ref_stale = "WS:AAA-STALE"
    resp_stale = _responsibility(ref=ref_stale)
    worker_stale = _runtime(ref=ref_stale, seat="WORKER", freshness="STALE")

    snap = _snapshot(
        responsibilities=(
            resp_chair, resp_ceo, resp_worker_1, resp_worker_2, resp_stale,
        ),
        attention=(att_chair, att_ceo),
        runtimes=(worker_1, worker_2, worker_stale),
    )

    doc = proj.project_autonomy(snap, generated_at="G")
    refs_in_order = [c["responsibility_ref"] for c in doc["responsibilities"]]

    correct_order = [ref_chair, ref_ceo, ref_worker_1, ref_worker_2, ref_stale]
    ref_only_order = sorted(correct_order)
    assert ref_only_order != correct_order  # the fixture is a real test of the other keys
    assert refs_in_order == correct_order

    card_chair = _card(doc, ref_chair)
    card_ceo = _card(doc, ref_ceo)
    card_worker_1 = _card(doc, ref_worker_1)
    card_worker_2 = _card(doc, ref_worker_2)
    card_stale = _card(doc, ref_stale)

    assert card_chair["chairman_decision_required"] is True
    assert card_chair["is_actionable"] is True

    assert card_ceo["chairman_decision_required"] is False
    assert card_ceo["is_actionable"] is True
    assert card_ceo["owed_turn"]["seat"] == "ceo"

    assert card_worker_1["chairman_decision_required"] is False
    assert card_worker_1["is_actionable"] is True
    assert card_worker_1["owed_turn"]["seat"] == "worker"
    assert card_worker_2["owed_turn"]["seat"] == "worker"

    assert card_stale["chairman_decision_required"] is False
    assert card_stale["is_actionable"] is False
    assert card_stale["actionability_reason"] == "stale_history"


def test_output_keys_is_a_closed_set():
    resp = _responsibility()
    snap = _snapshot(responsibilities=(resp,))

    doc = proj.project_autonomy(snap, generated_at="G")

    assert set(doc.keys()) == proj.OUTPUT_KEYS
    assert proj.OUTPUT_KEYS == frozenset({
        "schema", "generated_at", "responsibilities", "owed_by_seat",
        "chairman_decisions", "source_failures", "issues", "counts",
        "unmapped_responsibilities",
    })
    assert doc["unmapped_responsibilities"] == []
    for card in doc["responsibilities"]:
        assert set(card.keys()) == {
            "responsibility_ref", "title", "accountable_seat", "state",
            "root_job_id",
            # Blocker 1 (review 5106453403): explicit ambiguity/
            # reconciliation, distinct from plain "no Runtime evidence" —
            # root_job_id itself stays null in both cases (never a pick).
            "root_job_ambiguous", "root_job_candidates",
            "current_worker", "current_sol_target",
            "owed_turn", "placement_state", "wake_outcome", "blocker",
            "declared_blocker", "freshness", "is_actionable",
            "actionability_reason", "chairman_decision_required",
            "chairman_decision_reason", "disagreements", "source_receipts",
            "query_status",
        }


def test_purity_snapshot_is_not_mutated():
    ref = "WS:PURITY"
    resp = _responsibility(ref=ref)
    worker = _runtime(ref=ref, seat="WORKER")
    att = _attention(attention_id="ATT-PURITY", ref=ref, target="COO")
    blocker = _blocker(ref=ref, target="CHAIRMAN")
    failure = _failure()
    snap = _snapshot(
        responsibilities=(resp,), runtimes=(worker,), attention=(att,),
        blockers=(blocker,), source_failures=(failure,),
    )

    field_names = ("responsibilities", "attention", "runtimes", "blockers", "surfaces", "source_failures")
    before_identities = {name: id(getattr(snap, name)) for name in field_names}
    before_values = {name: getattr(snap, name) for name in field_names}

    proj.project_autonomy(snap, generated_at="G")

    after_identities = {name: id(getattr(snap, name)) for name in field_names}
    after_values = {name: getattr(snap, name) for name in field_names}

    assert before_identities == after_identities
    assert before_values == after_values
    assert snap.responsibilities == (resp,)
    assert snap.runtimes == (worker,)
    assert snap.attention == (att,)
    assert snap.blockers == (blocker,)
    assert snap.source_failures == (failure,)


# ---------------------------------------------------------------------------
# declared_blocker — plain-data, honestly Agent-OS-owned (bug-fix packet,
# 2026-09-01).  Exercises project_autonomy's declared_blockers parameter
# directly, with hand-built ExecutiveStewardSnapshot fixtures, independent
# of the real-data mapper tested further below.
# ---------------------------------------------------------------------------

def test_declared_blocker_present_with_ceo_target_seat_drives_owed_turn():
    ref = "WS:DECLARED-CEO"
    resp = _responsibility(ref=ref, seat="COO")
    snap = _snapshot(responsibilities=(resp,))
    declared_blockers = {ref: _declared(ref=ref, target_seat="ceo")}

    doc = proj.project_autonomy(snap, generated_at="G", declared_blockers=declared_blockers)
    card = _card(doc, ref)

    assert card["declared_blocker"] is not None
    assert card["declared_blocker"]["target_seat"] == "ceo"
    assert card["declared_blocker"]["code"] == "blocked_by"
    assert card["declared_blocker"]["source"]["owner"] == "agent_os"
    assert card["owed_turn"]["seat"] == "ceo"
    assert card["owed_turn"]["reason"] == "agent_os_declared_blocker_targets_seat"
    # Explicitly NOT the Steward-owned blocker field — never merged.
    assert card["blocker"] is None


def test_declared_blocker_present_with_accountable_seat_drives_owed_turn():
    ref = "WS:DECLARED-ACCOUNTABLE-SEAT"
    resp = _responsibility(ref=ref, seat="COO")
    snap = _snapshot(responsibilities=(resp,))
    declared_blockers = {ref: _declared(ref=ref, target_seat="coo")}

    doc = proj.project_autonomy(snap, generated_at="G", declared_blockers=declared_blockers)
    card = _card(doc, ref)

    assert card["declared_blocker"]["target_seat"] == "coo"
    assert card["owed_turn"]["seat"] == "coo"
    assert card["owed_turn"]["reason"] == "agent_os_declared_blocker_targets_seat"


def test_declared_blocker_with_null_target_seat_is_present_but_never_sets_an_owed_seat():
    ref = "WS:DECLARED-NULL-SEAT"
    resp = _responsibility(ref=ref, seat="COO")
    snap = _snapshot(responsibilities=(resp,))
    declared_blockers = {ref: _declared(ref=ref, target_seat=None)}

    doc = proj.project_autonomy(snap, generated_at="G", declared_blockers=declared_blockers)
    card = _card(doc, ref)

    # Present — the Chairman is still told the workstream is blocked.
    assert card["declared_blocker"] is not None
    assert card["declared_blocker"]["target_seat"] is None
    # But it never fabricates an owed seat: no attention/current worker
    # supplied here either, so this falls all the way through to "unknown".
    assert card["owed_turn"]["seat"] == "unknown"
    assert card["owed_turn"]["reason"] != "agent_os_declared_blocker_targets_seat"


def test_declared_blocker_absent_when_no_entry_supplied():
    ref = "WS:NO-DECLARED-BLOCKER"
    resp = _responsibility(ref=ref)
    snap = _snapshot(responsibilities=(resp,))

    doc = proj.project_autonomy(snap, generated_at="G")
    card = _card(doc, ref)

    assert card["declared_blocker"] is None
    assert card["blocker"] is None


def test_declared_blocker_ranks_after_the_steward_blocker():
    """Frozen spec §4.2's blocker rung still wins first — a genuine Steward
    ``BlockerFact`` outranks a declared_blocker every time."""
    ref = "WS:DECLARED-VS-STEWARD-BLOCKER"
    resp = _responsibility(ref=ref, seat="COO")
    blocker = _blocker(ref=ref, target="CHAIRMAN")
    snap = _snapshot(responsibilities=(resp,), blockers=(blocker,))
    declared_blockers = {ref: _declared(ref=ref, target_seat="ceo")}

    doc = proj.project_autonomy(snap, generated_at="G", declared_blockers=declared_blockers)
    card = _card(doc, ref)

    assert card["owed_turn"]["seat"] == "chairman"
    assert card["owed_turn"]["reason"] == "blocker_targets_seat"
    assert card["declared_blocker"] is not None  # still rendered, just not owed-turn-winning
    assert card["blocker"] is not None


def test_declared_blocker_ranks_before_attention():
    ref = "WS:DECLARED-BEFORE-ATTENTION"
    resp = _responsibility(ref=ref, seat="COO")
    att = _attention(attention_id="ATT-DECLARED-1", ref=ref, target="WORKER")
    snap = _snapshot(responsibilities=(resp,), attention=(att,))
    declared_blockers = {ref: _declared(ref=ref, target_seat="ceo")}

    doc = proj.project_autonomy(snap, generated_at="G", declared_blockers=declared_blockers)
    card = _card(doc, ref)

    assert card["owed_turn"]["seat"] == "ceo"
    assert card["owed_turn"]["reason"] == "agent_os_declared_blocker_targets_seat"


# ---------------------------------------------------------------------------
# build_autonomy_snapshot — real-data mapper (Phase A wiring packet)
# ---------------------------------------------------------------------------

import json as _json
from pathlib import Path as _Path

_CCR_FIXTURES = _Path(__file__).parent / "fixtures" / "chairman_control_room"


def _load_fixture(name: str):
    return _json.loads((_CCR_FIXTURES / name).read_text(encoding="utf-8"))


def _real_inputs():
    return dict(
        inbox=_load_fixture("executive_inbox_v2.json"),
        boot_packet=_load_fixture("boot_packet_v1.json"),
        active_builds=_load_fixture("active_builds_v1.json"),
        agent_os_state=_load_fixture("agent_os_state_v1.json"),
        runtime_jobs=_load_fixture("runtime_jobs_v1.json"),
        bindings=_load_fixture("bindings_v1.json"),
    )


def test_build_autonomy_snapshot_returns_a_snapshot():
    snap = proj.build_autonomy_snapshot(**_real_inputs())
    assert isinstance(snap, steward.ExecutiveStewardSnapshot)


def test_build_autonomy_snapshot_never_constructs_runtimes():
    """See module docstring point 8 — no genuine source for RuntimeFact.

    ``responsibilities``/``blockers`` are NOT asserted empty here any more
    (repair, 2026-09-01): the shared ``agent_os_state_v1.json`` fixture used
    by ``_real_inputs()`` happens to be a thin, three-row test fixture whose
    rows carry no ``owner``/``blocked_by`` fields at all (unlike the real
    compiled artifact), so responsibilities/blockers stay empty for THIS
    particular fixture as an honest consequence of every row's owner being
    unrecognized (missing) — see
    ``test_build_autonomy_snapshot_source_failure_only_when_agent_os_data_present``
    below for that assertion, and the dedicated
    ``test_build_autonomy_snapshot_constructs_*_from_owner_token``/
    ``test_build_autonomy_snapshot_end_to_end_with_realistic_multi_row_artifact``
    tests for proof the mapper DOES construct real cards from realistic rows.
    """
    snap = proj.build_autonomy_snapshot(**_real_inputs())
    assert snap.runtimes == ()


# ---------------------------------------------------------------------------
# bug-fix packet, 2026-09-01: the mapper must NEVER construct a BlockerFact
# from agent_os_state — BlockerFact.__post_init__ (executive_steward.py)
# refuses any source.owner other than EXECUTIVE_OS/EXECUTIVE_INBOX/WAKE, so
# the prior revision's SourceOwner.EXECUTIVE_OS stamp on a fact whose own
# ref names "agent_os_state.workstreams:<key>.blocked_by" was a false
# attribution — Agent OS data labelled as Executive OS data.
# ---------------------------------------------------------------------------

def test_build_autonomy_snapshot_never_produces_a_blocker_fact_whose_source_ref_names_agent_os():
    """No BlockerFact this mapper ever builds may carry a source whose
    ``ref`` names an agent_os artifact — because it must never build a
    BlockerFact from agent_os_state at all (see the next test)."""
    agent_os_state = _agent_os_state(
        [
            _ws_row(
                "REAL-WS-STILL-BLOCKED",
                owner="coo-fable",
                blocked_by=["operator: rotate the R2 access key before wave 3"],
                needs_ceo=True,
            )
        ]
    )
    snap = proj.build_autonomy_snapshot(
        inbox=None, boot_packet=None, active_builds=None,
        agent_os_state=agent_os_state, runtime_jobs=None, bindings=None,
    )
    for blocker in snap.blockers:
        assert "agent_os" not in blocker.source.ref


def test_build_autonomy_snapshot_builds_zero_blocker_facts_from_a_realistic_agent_os_artifact():
    """The mapper must build zero BlockerFacts from agent_os_state, full
    stop — even when the artifact carries plenty of genuine, structured
    ``blocked_by``/``needs_ceo`` signal that a prior, buggy revision of this
    mapper would have turned into a mislabelled BlockerFact."""
    agent_os_state = _agent_os_state(
        [
            _ws_row(
                "REAL-WS-CEO-BLOCKED", owner="coo-fable",
                blocked_by=["operator: rotate the shared secret"], needs_ceo=True,
            ),
            _ws_row(
                "REAL-WS-OWNER-BLOCKED", owner="chairman",
                blocked_by=["operator: confirm backup retention window"],
            ),
            _ws_row(
                "REAL-WS-UNOWNED-BLOCKED", owner="ops",
                blocked_by=["operator: unresolved dependency"],
            ),
        ]
    )
    snap = proj.build_autonomy_snapshot(
        inbox=None, boot_packet=None, active_builds=None,
        agent_os_state=agent_os_state, runtime_jobs=None, bindings=None,
    )
    assert snap.blockers == ()


def test_build_autonomy_snapshot_constructs_real_attention_facts():
    snap = proj.build_autonomy_snapshot(**_real_inputs())
    assert len(snap.attention) > 0
    for fact in snap.attention:
        assert isinstance(fact, steward.AttentionFact)
        assert fact.source.owner is steward.SourceOwner.EXECUTIVE_INBOX
        assert fact.responsibility_ref.startswith("WS:")


def test_build_autonomy_snapshot_constructs_real_surface_facts_never_reviewed():
    snap = proj.build_autonomy_snapshot(**_real_inputs())
    assert len(snap.surfaces) > 0
    for fact in snap.surfaces:
        assert isinstance(fact, steward.SurfaceFact)
        assert fact.source.owner is steward.SourceOwner.SURFACE_BINDINGS
        # module docstring point 9: never fabricated as "reviewed".
        assert fact.reviewed_at is None


def test_build_autonomy_snapshot_never_reports_unrecognized_owners_as_source_failures():
    """Blast-radius repair packet, 2026-09-01: the thin fixture's three rows
    all lack an ``owner`` field, so every one is unmapped — but ``snapshot.
    source_failures`` must stay empty regardless (a SourceFailure is a
    global, source-level outage; an unrecognized owner is a bounded, per-row
    mapping gap, reported instead by
    ``unmapped_responsibilities_from_agent_os_state`` — see the dedicated
    ``test_unmapped_responsibilities_from_agent_os_state_*`` tests below).
    The old blanket ``accountable_seat_not_observable`` claim stays gone too
    — a prior repair packet removed it because it was false against the
    real compiled artifact.
    """
    inputs = _real_inputs()
    with_agent_os = proj.build_autonomy_snapshot(**inputs)
    assert with_agent_os.source_failures == ()

    inputs_no_agent_os = dict(inputs, boot_packet=None, agent_os_state=None)
    without_agent_os = proj.build_autonomy_snapshot(**inputs_no_agent_os)
    assert without_agent_os.source_failures == ()


def test_build_autonomy_snapshot_handles_every_input_absent():
    """No I/O-shaped crash when every gathered input is ``None``."""
    snap = proj.build_autonomy_snapshot(
        inbox=None, boot_packet=None, active_builds=None,
        agent_os_state=None, runtime_jobs=None, bindings=None,
    )
    assert snap.responsibilities == ()
    assert snap.attention == ()
    assert snap.runtimes == ()
    assert snap.blockers == ()
    assert snap.surfaces == ()
    assert snap.source_failures == ()


def test_build_autonomy_snapshot_skips_malformed_attention_rows_without_crashing():
    inputs = _real_inputs()
    malformed_inbox = {
        "schema": inputs["inbox"]["schema"],
        "generated_at": inputs["inbox"]["generated_at"],
        "attention": [
            {"attention_id": "eia-ok", "target": "ceo", "kind": "note",
             "reason": "a real reason", "workstream": "REAL-ONE", "source": "agent_os"},
            {"attention_id": "", "target": "ceo", "kind": "note",
             "reason": "blank id", "workstream": "REAL-TWO", "source": "agent_os"},
            {"attention_id": "eia-bad-target", "target": "not-a-seat", "kind": "note",
             "reason": "bad target", "workstream": "REAL-THREE", "source": "agent_os"},
            {"attention_id": "eia-no-ws", "target": "ceo", "kind": "note",
             "reason": "no workstream", "workstream": None, "source": "agent_os"},
            "not-a-mapping-at-all",
        ],
    }
    snap = proj.build_autonomy_snapshot(**dict(inputs, inbox=malformed_inbox))
    assert len(snap.attention) == 1
    assert snap.attention[0].attention_id == "eia-ok"
    assert snap.attention[0].responsibility_ref == "WS:REAL-ONE"


def test_build_autonomy_snapshot_skips_malformed_binding_rows_without_crashing():
    inputs = _real_inputs()
    malformed_bindings = {
        "schema": inputs["bindings"]["schema"],
        "bindings": [
            {"binding_id": "b-ok", "work_ref": "WS:REAL-ONE", "role": "worker",
             "seat_ref": None, "provider": "codex", "locator_kind": "codex_session",
             "observed_at": "2026-09-01T00:00:00Z", "last_verified_at": None},
            {"binding_id": "b-bad-role", "work_ref": "WS:REAL-TWO", "role": "not-a-seat",
             "seat_ref": None, "provider": "codex", "locator_kind": "codex_session",
             "observed_at": "2026-09-01T00:00:00Z", "last_verified_at": None},
            {"binding_id": "", "work_ref": "WS:REAL-THREE", "role": "worker",
             "seat_ref": None, "provider": "codex", "locator_kind": "codex_session",
             "observed_at": "2026-09-01T00:00:00Z", "last_verified_at": None},
            "not-a-mapping-at-all",
        ],
    }
    snap = proj.build_autonomy_snapshot(**dict(inputs, bindings=malformed_bindings))
    assert len(snap.surfaces) == 1
    assert snap.surfaces[0].surface_ref == "b-ok"


def test_build_autonomy_snapshot_is_pure_and_deterministic():
    """No I/O, no clock, no randomness: same inputs in -> an equal snapshot out."""
    import copy as _copy

    inputs = _real_inputs()
    frozen_inputs = _copy.deepcopy(inputs)

    snap_a = proj.build_autonomy_snapshot(**inputs)
    snap_b = proj.build_autonomy_snapshot(**inputs)

    # Inputs are never mutated.
    assert inputs == frozen_inputs

    def _sortable(snapshot):
        return _json.dumps(
            {
                "attention": [steward._encode(f) for f in snapshot.attention],
                "surfaces": [steward._encode(f) for f in snapshot.surfaces],
                "source_failures": [steward._encode(f) for f in snapshot.source_failures],
                "responsibilities": [steward._encode(f) for f in snapshot.responsibilities],
                "runtimes": [steward._encode(f) for f in snapshot.runtimes],
                "blockers": [steward._encode(f) for f in snapshot.blockers],
            },
            sort_keys=True,
        )

    assert _sortable(snap_a) == _sortable(snap_b)


def test_build_autonomy_snapshot_feeds_project_autonomy_end_to_end():
    """The real mapper output is a valid input to project_autonomy (integration smoke test).

    The shared ``agent_os_state_v1.json`` fixture's three rows all lack an
    ``owner`` field, so this particular run still yields zero responsibility
    cards — an honest gap, not the old false blanket claim that no
    compositor input ever names a seat.  Blast-radius repair packet,
    2026-09-01: this run's ``source_failures`` must stay empty regardless
    (an unrecognized owner is never a SourceFailure) — this test only feeds
    the mapper's own ``build_autonomy_snapshot`` output through
    ``project_autonomy`` without also threading
    ``unmapped_responsibilities_from_agent_os_state``, exactly the shape an
    existing caller that has not yet adopted the new parameter still gets.
    See ``test_build_autonomy_snapshot_end_to_end_with_realistic_multi_row_artifact``
    below for the proof that real owner-bearing rows DO produce real cards,
    and for the wired-up ``unmapped_responsibilities`` assertion.

    ``counts["empty"]`` reads ``True`` here (repair packet, 2026-09-01,
    correcting this test's prior expectation): with zero SourceFailures,
    ``snapshot.list_responsibilities()`` genuinely returns no suppression
    signal (module docstring point re: Repair 9 — that flag exists to
    distinguish "genuinely idle" from "we cannot see", and a bounded,
    honest per-row mapping gap is neither of those old two states — it is
    now its own, separately and honestly disclosed thing via
    ``unmapped_responsibilities_from_agent_os_state``, exercised below).
    The old ``False`` reading was itself a side effect of the same
    over-broad ``SourceFailure`` this packet removes.
    """
    snap = proj.build_autonomy_snapshot(**_real_inputs())
    doc = proj.project_autonomy(snap, generated_at="2026-09-01T00:00:00Z")
    assert set(doc.keys()) == proj.OUTPUT_KEYS
    assert doc["generated_at"] == "2026-09-01T00:00:00Z"
    assert doc["responsibilities"] == []
    assert doc["counts"]["empty"] is True
    assert doc["source_failures"] == []
    assert not any(
        row["code"] == "accountable_seat_not_observable" for row in doc["source_failures"]
    )
    # unmapped_responsibilities was not supplied to project_autonomy here —
    # defaults to empty, exactly like declared_blockers — but the real gap
    # is still honestly recoverable via the dedicated mapper function.
    assert doc["unmapped_responsibilities"] == []
    real_unmapped = proj.unmapped_responsibilities_from_agent_os_state(
        _real_inputs()["agent_os_state"]
    )
    assert len(real_unmapped) == 3
    assert all(row["reason"] == "owner_not_a_recognized_seat" for row in real_unmapped)


# ---------------------------------------------------------------------------
# build_autonomy_snapshot — real-shaped rows (Phase A repair packet,
# 2026-09-01): the mapper must build real ResponsibilityFact/BlockerFact
# cards from structured fields the real compiled agent_os_state.json
# artifact carries — key/title/status/owner/blocked_by/needs_ceo — and must
# NEVER derive a seat from prose, even prose that contains seat-like words.
# ---------------------------------------------------------------------------

def _ws_row(
    key,
    *,
    title="Some real workstream title",
    status="active",
    owner="__absent__",
    blocked_by=None,
    needs_ceo=None,
):
    row = {"key": key, "title": title, "status": status}
    if owner != "__absent__":
        row["owner"] = owner
    if blocked_by is not None:
        row["blocked_by"] = blocked_by
    if needs_ceo is not None:
        row["needs_ceo"] = needs_ceo
    return row


def _agent_os_state(rows, *, generated_at="2026-09-01T01:18:31Z"):
    return {
        "schema": "agent_os_state.v1",
        "generator": "scripts/agentos.py status",
        "generated_at": generated_at,
        "workstreams": rows,
    }


@pytest.mark.parametrize(
    "owner_token,expected_seat",
    [
        ("chairman", steward.Seat.CHAIRMAN),
        ("ceo-sol", steward.Seat.CEO),
        ("coo-fable", steward.Seat.COO),
        ("fable", steward.Seat.COO),
    ],
)
def test_build_autonomy_snapshot_maps_each_recognized_owner_token_to_its_seat(
    owner_token, expected_seat,
):
    agent_os_state = _agent_os_state(
        [_ws_row("REAL-WS-ONE", owner=owner_token, status="active")]
    )
    snap = proj.build_autonomy_snapshot(
        inbox=None, boot_packet=None, active_builds=None,
        agent_os_state=agent_os_state, runtime_jobs=None, bindings=None,
    )
    assert snap.source_failures == ()
    assert len(snap.responsibilities) == 1
    fact = snap.responsibilities[0]
    assert fact.responsibility_ref == "WS:REAL-WS-ONE"
    assert fact.accountable_seat is expected_seat
    assert fact.state == "active"
    assert fact.root_job_id is None
    assert fact.source.owner is steward.SourceOwner.AGENT_OS
    assert fact.source.observed_at == "2026-09-01T01:18:31Z"


@pytest.mark.parametrize(
    "key,owner_kwargs",
    [
        ("REAL-WS-OPS", {"owner": "ops"}),
        ("REAL-WS-TERMINAL", {"owner": "terminal-platform"}),
        ("REAL-WS-GROK", {"owner": "grok-cn-c"}),
        ("REAL-WS-NO-OWNER-KEY", {}),  # owner key entirely absent
        ("REAL-WS-EMPTY-OWNER", {"owner": ""}),
        (
            "REAL-WS-PROSE-OWNER",
            {"owner": "Eval-OS session (COO Fable lane)"},
        ),
    ],
)
def test_build_autonomy_snapshot_never_maps_an_unrecognized_owner_to_a_seat(key, owner_kwargs):
    """The prose case is the important one: it must NOT become COO merely
    because the words "COO" and "Fable" appear inside the sentence.

    Blast-radius repair packet, 2026-09-01: an unrecognized owner is now
    reported via ``unmapped_responsibilities_from_agent_os_state`` — a
    bounded, per-row report — never as a ``SourceFailure`` on the snapshot
    (a SourceFailure is a global, source-level outage the Steward folds
    into the issues of EVERY query; a per-row mapping gap must never
    contaminate every other, correctly-owned workstream)."""
    agent_os_state = _agent_os_state([_ws_row(key, **owner_kwargs)])
    snap = proj.build_autonomy_snapshot(
        inbox=None, boot_packet=None, active_builds=None,
        agent_os_state=agent_os_state, runtime_jobs=None, bindings=None,
    )
    assert snap.responsibilities == ()
    assert snap.source_failures == ()

    unmapped = proj.unmapped_responsibilities_from_agent_os_state(agent_os_state)
    assert len(unmapped) == 1
    row = unmapped[0]
    expected_ref = key if key.startswith("WS:") else f"WS:{key}"
    assert row["responsibility_ref"] == expected_ref
    assert row["reason"] == "owner_not_a_recognized_seat"
    assert set(row.keys()) == {"responsibility_ref", "reason"}
    # The raw owner prose must never leak anywhere in the unmapped row —
    # only the workstream ref and the fixed machine reason are named.
    raw_owner = owner_kwargs.get("owner")
    row_text = repr(row)
    if isinstance(raw_owner, str) and raw_owner:
        assert raw_owner not in row_text
    assert "Fable" not in row_text
    assert "COO" not in row_text


def test_build_autonomy_snapshot_blocked_by_and_needs_ceo_true_targets_the_ceo_seat():
    """Bug-fix packet, 2026-09-01: this signal is now represented as a
    ``declared_blocker`` — plain data, honestly Agent-OS-owned — not a
    BlockerFact.  See ``declared_blockers_from_agent_os_state`` tests below
    for the dedicated coverage of this exact fixture's target_seat/present/
    absent behavior; this test keeps the original name and fixture to prove
    the mapper itself builds no BlockerFact for it any more."""
    agent_os_state = _agent_os_state(
        [
            _ws_row(
                "REAL-WS-BLOCKED",
                owner="coo-fable",  # would otherwise map to COO
                blocked_by=["operator: rotate the R2 access key before wave 3"],
                needs_ceo=True,
            )
        ]
    )
    snap = proj.build_autonomy_snapshot(
        inbox=None, boot_packet=None, active_builds=None,
        agent_os_state=agent_os_state, runtime_jobs=None, bindings=None,
    )
    assert snap.blockers == ()

    declared = proj.declared_blockers_from_agent_os_state(agent_os_state)
    entry = declared["WS:REAL-WS-BLOCKED"]
    assert entry["target_seat"] == "ceo"
    assert entry["code"] == "blocked_by"
    assert entry["source"].owner is steward.SourceOwner.AGENT_OS
    assert "REAL-WS-BLOCKED" in entry["explanation"]
    assert "rotate the R2 access key" in entry["explanation"]


def test_build_autonomy_snapshot_empty_blocked_by_yields_no_blocker_fact():
    agent_os_state = _agent_os_state(
        [
            _ws_row("REAL-WS-UNBLOCKED-A", owner="chairman", blocked_by=[]),
            _ws_row("REAL-WS-UNBLOCKED-B", owner="chairman"),  # blocked_by absent entirely
        ]
    )
    snap = proj.build_autonomy_snapshot(
        inbox=None, boot_packet=None, active_builds=None,
        agent_os_state=agent_os_state, runtime_jobs=None, bindings=None,
    )
    assert snap.blockers == ()
    assert len(snap.responsibilities) == 2
    assert proj.declared_blockers_from_agent_os_state(agent_os_state) == {}


def test_build_autonomy_snapshot_blocked_by_with_unrecognized_owner_and_no_needs_ceo_builds_no_blocker():
    """No genuine seat exists to target without inventing one — the
    BlockerFact is (still, and now always) never built for this row, and
    the ``declared_blocker`` entry is present with a null ``target_seat``
    rather than being suppressed: the Chairman is still told the
    workstream is blocked even though nobody can be named accountable.

    Fix 2 (adversarial-review repair packet, 2026-09-01): this test used to
    assert that ``unmapped_responsibilities_from_agent_os_state``'s entry
    carried ONLY ``responsibility_ref``/``reason`` — which meant the
    ``declared_blockers_from_agent_os_state`` entry asserted just below was
    computed correctly but never actually reached the Chairman, since
    ``project_autonomy`` only reads ``declared_blockers`` for a ref with a
    real card, and an unrecognized-owner row never gets one.  That was
    the exact defect Fix 2 closes: the unmapped row itself now carries the
    same declared-blocker information, with no raw owner text."""
    agent_os_state = _agent_os_state(
        [
            _ws_row(
                "REAL-WS-BLOCKED-UNOWNED",
                owner="ops",
                blocked_by=["operator: confirm backup retention window"],
            )
        ]
    )
    snap = proj.build_autonomy_snapshot(
        inbox=None, boot_packet=None, active_builds=None,
        agent_os_state=agent_os_state, runtime_jobs=None, bindings=None,
    )
    assert snap.blockers == ()
    assert snap.responsibilities == ()
    # Blast-radius repair packet, 2026-09-01: never a SourceFailure — see
    # unmapped_responsibilities_from_agent_os_state below.
    assert snap.source_failures == ()

    unmapped = proj.unmapped_responsibilities_from_agent_os_state(agent_os_state)
    assert unmapped == (
        {
            "responsibility_ref": "WS:REAL-WS-BLOCKED-UNOWNED",
            "reason": "owner_not_a_recognized_seat",
            "declared_blocker": {
                "code": "blocked_by",
                "explanation": (
                    "workstream REAL-WS-BLOCKED-UNOWNED is blocked by: "
                    "operator: confirm backup retention window"
                ),
                "target_seat": None,
            },
        },
    )
    # No raw owner prose ("ops") anywhere in the receipt.
    assert "ops" not in repr(unmapped)

    declared = proj.declared_blockers_from_agent_os_state(agent_os_state)
    entry = declared["WS:REAL-WS-BLOCKED-UNOWNED"]
    assert entry["target_seat"] is None
    assert entry["source"].owner is steward.SourceOwner.AGENT_OS


def test_build_autonomy_snapshot_end_to_end_with_realistic_multi_row_artifact():
    """Feed a realistic multi-row artifact through build_autonomy_snapshot
    then project_autonomy and assert real populated cards come out with
    correct ordering (frozen spec §5: Chairman, then CEO, then COO, then
    worker, then unknown)."""
    agent_os_state = _agent_os_state(
        [
            _ws_row("REAL-WORKER-TARGET", owner="coo-fable", status="active"),
            _ws_row("REAL-CHAIRMAN-WS", owner="chairman", status="active"),
            _ws_row("REAL-CEO-WS", owner="ceo-sol", status="in_progress"),
            _ws_row(
                "REAL-BLOCKED-WS",
                owner="fable",
                status="blocked",
                blocked_by=["operator: rotate the shared secret"],
            ),
            _ws_row("REAL-UNRECOGNIZED-WS", owner="grok-cn-c", status="active"),
        ]
    )
    snap = proj.build_autonomy_snapshot(
        inbox=None, boot_packet=None, active_builds=None,
        agent_os_state=agent_os_state, runtime_jobs=None, bindings=None,
    )
    # Bug-fix packet, 2026-09-01: the real end-to-end wiring threads
    # declared_blockers_from_agent_os_state's plain data into
    # project_autonomy alongside the mapper's snapshot — this is exactly
    # what a caller (e.g. the compositor) does to get the SAME real card
    # ordering/owed-turn behavior the pre-fix BlockerFact stamp used to
    # (dishonestly) produce.  Blast-radius repair packet, 2026-09-01: the
    # real wiring threads unmapped_responsibilities_from_agent_os_state the
    # exact same additive way.
    declared_blockers = proj.declared_blockers_from_agent_os_state(agent_os_state)
    unmapped_responsibilities = proj.unmapped_responsibilities_from_agent_os_state(agent_os_state)
    doc = proj.project_autonomy(
        snap,
        generated_at="2026-09-01T00:00:00Z",
        declared_blockers=declared_blockers,
        unmapped_responsibilities=unmapped_responsibilities,
    )

    assert set(doc.keys()) == proj.OUTPUT_KEYS
    assert len(doc["responsibilities"]) == 4
    # Sort order is frozen spec §5's full key — chairman_decision_required,
    # then is_actionable, then owed_turn.seat rank, then responsibility_ref
    # — NOT a raw accountable_seat sort: the one card with a declared
    # blocker has an observable (non-"unknown") owed_turn.seat and sorts
    # first; the remaining three all have owed_turn.seat == "unknown" (no
    # blocker, no attention, no current worker supplied) and fall back to
    # alphabetical responsibility_ref order.
    refs_in_order = [row["responsibility_ref"] for row in doc["responsibilities"]]
    assert refs_in_order == [
        "WS:REAL-BLOCKED-WS",
        "WS:REAL-CEO-WS",
        "WS:REAL-CHAIRMAN-WS",
        "WS:REAL-WORKER-TARGET",
    ]
    seats_in_order = [row["accountable_seat"] for row in doc["responsibilities"]]
    assert seats_in_order == ["coo", "ceo", "chairman", "coo"]

    blocked_card = doc["responsibilities"][0]
    assert blocked_card["responsibility_ref"] == "WS:REAL-BLOCKED-WS"
    # No genuine BlockerFact was ever built from agent_os_state (bug-fix
    # packet) — the Steward-owned `blocker` field stays null.
    assert blocked_card["blocker"] is None
    assert blocked_card["declared_blocker"] is not None
    assert blocked_card["declared_blocker"]["target_seat"] == "coo"
    assert blocked_card["declared_blocker"]["source"]["owner"] == "agent_os"
    assert blocked_card["owed_turn"]["seat"] == "coo"
    assert blocked_card["owed_turn"]["reason"] == "agent_os_declared_blocker_targets_seat"

    # Blast-radius repair packet, 2026-09-01: the unrecognized-owner row
    # must produce zero SourceFailures, and none of the recognized cards'
    # actionability_reason may read "source_failure" any more — the whole
    # point of the fix.  (This fixture's cards are refused for an entirely
    # different, pre-existing, out-of-scope reason — every ResponsibilityFact
    # this mapper builds carries root_job_id=None by design, see module
    # docstring point 8, which makes get_current_runtime REFUSE with
    # `runtime_root_missing` regardless of source_failures; see the
    # dedicated `test_unrecognized_owner_never_contaminates_a_sibling_cards_
    # query_status` test below, built from manually-supplied facts with a
    # real root_job_id, for a clean proof of "query_status: ok".)
    assert doc["source_failures"] == []
    assert doc["unmapped_responsibilities"] == [
        {"responsibility_ref": "WS:REAL-UNRECOGNIZED-WS", "reason": "owner_not_a_recognized_seat"},
    ]
    for card in doc["responsibilities"]:
        assert card["actionability_reason"] != "source_failure"
    assert doc["counts"]["total"] == 4


# ---------------------------------------------------------------------------
# unmapped_responsibilities — blast-radius repair packet, 2026-09-01
#
# A SourceFailure is a global, source-level outage; executive_steward.
# ExecutiveStewardSnapshot folds every one of them into the issues of EVERY
# query it answers (module docstring point 7 / _source_issues), so a
# per-row condition — an unrecognized workstream owner — must never be
# reported as one.  These tests pin the fix: zero SourceFailures from that
# cause, a bounded unmapped_responsibilities report instead, and zero effect
# on any other card.
# ---------------------------------------------------------------------------

def test_unrecognized_owner_never_contaminates_a_sibling_cards_query_status():
    """A handful of unmapped rows threaded through project_autonomy's
    ``unmapped_responsibilities`` parameter must never contaminate a
    recognized sibling card's ``query_status``/``actionability_reason`` —
    the defect this repair packet fixes.  Uses manually-supplied facts
    (each with a real ``root_job_id``) rather than the real mapper, so
    ``query_status: "ok"`` is actually reachable: ``build_autonomy_snapshot``
    never sets ``root_job_id`` (module docstring point 8), which
    independently REFUSES ``get_current_runtime`` via ``runtime_root_
    missing`` — a separate, pre-existing, out-of-scope condition this test
    must not conflate with the fix under test.
    """
    refs = [f"WS:RECOGNIZED-{i}" for i in range(3)]
    resps = tuple(_responsibility(ref=ref, root_job_id=f"JOB-{ref}") for ref in refs)
    snap = _snapshot(responsibilities=resps)  # zero source_failures

    unmapped_rows = [
        {"responsibility_ref": f"WS:UNRECOGNIZED-{i}", "reason": "owner_not_a_recognized_seat"}
        for i in range(4)
    ]

    doc = proj.project_autonomy(
        snap, generated_at="G", unmapped_responsibilities=unmapped_rows,
    )

    assert doc["source_failures"] == []
    assert len(doc["responsibilities"]) == 3
    for card in doc["responsibilities"]:
        assert card["query_status"] == "ok"
        assert card["actionability_reason"] != "source_failure"

    assert doc["unmapped_responsibilities"] == sorted(
        unmapped_rows, key=lambda row: row["responsibility_ref"]
    )


def test_unmapped_responsibilities_lists_exactly_the_unrecognized_rows_with_no_raw_owner_text():
    """``unmapped_responsibilities`` names exactly the unrecognized-owner
    rows — never a recognized row, never the raw owner prose."""
    agent_os_state = _agent_os_state([
        _ws_row("REC-CHAIRMAN", owner="chairman"),
        _ws_row("REC-CEO", owner="ceo-sol"),
        _ws_row("UNREC-OPS", owner="ops"),
        _ws_row("UNREC-PROSE", owner="Eval-OS session (COO Fable lane)"),
        _ws_row("UNREC-EMPTY", owner=""),
    ])
    snap = proj.build_autonomy_snapshot(
        inbox=None, boot_packet=None, active_builds=None,
        agent_os_state=agent_os_state, runtime_jobs=None, bindings=None,
    )
    unmapped = proj.unmapped_responsibilities_from_agent_os_state(agent_os_state)
    doc = proj.project_autonomy(snap, generated_at="G", unmapped_responsibilities=unmapped)

    assert doc["unmapped_responsibilities"] == [
        {"responsibility_ref": "WS:UNREC-EMPTY", "reason": "owner_not_a_recognized_seat"},
        {"responsibility_ref": "WS:UNREC-OPS", "reason": "owner_not_a_recognized_seat"},
        {"responsibility_ref": "WS:UNREC-PROSE", "reason": "owner_not_a_recognized_seat"},
    ]
    mapped_refs = {c["responsibility_ref"] for c in doc["responsibilities"]}
    assert mapped_refs == {"WS:REC-CHAIRMAN", "WS:REC-CEO"}
    unmapped_refs = {row["responsibility_ref"] for row in doc["unmapped_responsibilities"]}
    assert mapped_refs.isdisjoint(unmapped_refs)

    doc_text = repr(doc["unmapped_responsibilities"])
    assert "ops" not in doc_text
    assert "Eval-OS" not in doc_text
    assert "Fable" not in doc_text
    assert "COO" not in doc_text


def test_unmapped_responsibilities_do_not_affect_other_cards_counts_freshness_or_actionability():
    """The presence of unmapped rows has zero effect on any card's
    ``query_status``, ``is_actionable``, ``actionability_reason``,
    ``freshness`` or on the document's ``counts`` — the whole document is
    identical whether or not ``unmapped_responsibilities`` is supplied,
    except for the ``unmapped_responsibilities`` key itself."""
    ref = "WS:UNCHANGED"
    resp = _responsibility(ref=ref, root_job_id="JOB-X")
    att = _attention(attention_id="ATT-X", ref=ref, target="CEO")
    snap = _snapshot(responsibilities=(resp,), attention=(att,))

    doc_without = proj.project_autonomy(snap, generated_at="G")
    doc_with = proj.project_autonomy(
        snap,
        generated_at="G",
        unmapped_responsibilities=[
            {"responsibility_ref": "WS:SOME-UNMAPPED", "reason": "owner_not_a_recognized_seat"},
        ],
    )

    assert doc_without["unmapped_responsibilities"] == []
    assert doc_with["unmapped_responsibilities"] == [
        {"responsibility_ref": "WS:SOME-UNMAPPED", "reason": "owner_not_a_recognized_seat"},
    ]

    without_sans_key = {k: v for k, v in doc_without.items() if k != "unmapped_responsibilities"}
    with_sans_key = {k: v for k, v in doc_with.items() if k != "unmapped_responsibilities"}
    assert without_sans_key == with_sans_key
    assert doc_with["counts"] == doc_without["counts"]


# ---------------------------------------------------------------------------
# Adversarial-review repair packet, 2026-09-01 — five fixes found by an
# adversarial review that blocked the merge.  See the module docstring's
# "Fix 1"/"Fix 2"/"Fix 3"/"Fix 4"/"Fix 5" annotations for the full account
# of each defect and its correction.
# ---------------------------------------------------------------------------

# --- Fix 1: real staleness --------------------------------------------------

def test_fix1_stale_agent_os_artifact_yields_stale_card_and_counts_stale():
    """The production defect this fix closes: an Agent OS artifact observed
    well outside the freshness budget (48h) before the compositor's own
    generated_at used to read freshness "current" with counts.stale == 0
    and could even be actionable.  Now it reads "stale", the card is not
    actionable (reason stale_history), and counts.stale counts it."""
    agent_os_state = _agent_os_state(
        [_ws_row("FIX1-STALE", owner="chairman", status="active")],
        generated_at="2026-08-20T00:00:00Z",  # nine days before reference
    )
    reference_at = "2026-08-29T00:00:00Z"
    snap = proj.build_autonomy_snapshot(
        inbox=None, boot_packet=None, active_builds=None,
        agent_os_state=agent_os_state, runtime_jobs=None, bindings=None,
        generated_at=reference_at,
    )
    doc = proj.project_autonomy(snap, generated_at=reference_at)
    card = _card(doc, "WS:FIX1-STALE")

    assert card["freshness"] == "stale"
    assert card["is_actionable"] is False
    assert card["actionability_reason"] == "stale_history"
    assert doc["counts"]["stale"] == 1
    assert doc["counts"]["actionable"] == 0


def test_fix1_agent_os_artifact_within_budget_stays_current():
    """An observation inside the 48h freshness budget stays current."""
    agent_os_state = _agent_os_state(
        [_ws_row("FIX1-FRESH", owner="chairman", status="active")],
        generated_at="2026-08-30T12:00:00Z",  # twelve hours before reference
    )
    reference_at = "2026-08-31T00:00:00Z"
    snap = proj.build_autonomy_snapshot(
        inbox=None, boot_packet=None, active_builds=None,
        agent_os_state=agent_os_state, runtime_jobs=None, bindings=None,
        generated_at=reference_at,
    )
    doc = proj.project_autonomy(snap, generated_at=reference_at)
    card = _card(doc, "WS:FIX1-FRESH")

    assert card["freshness"] == "current"
    assert doc["counts"]["stale"] == 0


@pytest.mark.parametrize(
    "bad_generated_at", [None, "", "not-a-timestamp", 12345, "2026-13-99T00:00:00Z"]
)
def test_fix1_absent_or_unparseable_observed_at_is_unknown_never_current(bad_generated_at):
    """An absent or unparseable observed_at reads freshness "unknown" —
    never "current" (the old, wrong default for any non-empty string)."""
    agent_os_state = _agent_os_state(
        [_ws_row("FIX1-UNKNOWN", owner="chairman", status="active")],
        generated_at=bad_generated_at,
    )
    reference_at = "2026-08-31T00:00:00Z"
    snap = proj.build_autonomy_snapshot(
        inbox=None, boot_packet=None, active_builds=None,
        agent_os_state=agent_os_state, runtime_jobs=None, bindings=None,
        generated_at=reference_at,
    )
    doc = proj.project_autonomy(snap, generated_at=reference_at)
    card = _card(doc, "WS:FIX1-UNKNOWN")

    assert card["freshness"] == "unknown"
    assert card["freshness"] != "current"


def test_fix1_unparseable_reference_timestamp_also_reads_unknown_never_current():
    """When the injected reference itself cannot be parsed, currency cannot
    be asserted either — unknown, not a silent fall-back to "current"."""
    agent_os_state = _agent_os_state(
        [_ws_row("FIX1-BAD-REFERENCE", owner="chairman", status="active")],
        generated_at="2026-08-30T00:00:00Z",
    )
    snap = proj.build_autonomy_snapshot(
        inbox=None, boot_packet=None, active_builds=None,
        agent_os_state=agent_os_state, runtime_jobs=None, bindings=None,
        generated_at="not-a-real-timestamp",
    )
    doc = proj.project_autonomy(snap, generated_at="not-a-real-timestamp")
    card = _card(doc, "WS:FIX1-BAD-REFERENCE")

    assert card["freshness"] == "unknown"


def test_fix1_freshness_computation_is_deterministic():
    """Same inputs in -> byte-identical output, twice, including the new
    age-based freshness computation (Fix 1 must stay pure and clock-free)."""
    agent_os_state = _agent_os_state(
        [_ws_row("FIX1-DETERM", owner="chairman", status="active")],
        generated_at="2026-08-20T00:00:00Z",
    )
    reference_at = "2026-08-29T00:00:00Z"

    def _run():
        snap = proj.build_autonomy_snapshot(
            inbox=None, boot_packet=None, active_builds=None,
            agent_os_state=agent_os_state, runtime_jobs=None, bindings=None,
            generated_at=reference_at,
        )
        doc = proj.project_autonomy(snap, generated_at=reference_at)
        return json.dumps(doc, sort_keys=True)

    assert _run() == _run()


# --- Fix 2: an unmapped-but-blocked workstream keeps its declared block ----

def test_fix2_unmapped_blocked_needs_ceo_true_gets_declared_blocker_with_ceo_seat():
    """A blocked workstream whose owner is unrecognized AND whose
    ``needs_ceo`` is literally ``True`` still names the CEO seat on its
    unmapped receipt — no raw owner prose leaks."""
    agent_os_state = _agent_os_state([
        _ws_row(
            "FIX2-CEO-BLOCKED", owner="grok-cn-c",
            blocked_by=["operator: needs CEO sign-off"], needs_ceo=True,
        )
    ])
    unmapped = proj.unmapped_responsibilities_from_agent_os_state(agent_os_state)

    assert len(unmapped) == 1
    row = unmapped[0]
    assert row["responsibility_ref"] == "WS:FIX2-CEO-BLOCKED"
    assert row["reason"] == "owner_not_a_recognized_seat"
    assert row["declared_blocker"]["code"] == "blocked_by"
    assert row["declared_blocker"]["target_seat"] == "ceo"
    assert "needs CEO sign-off" in row["declared_blocker"]["explanation"]
    assert "grok-cn-c" not in repr(row)


def test_fix2_unmapped_row_end_to_end_through_project_autonomy_carries_no_card():
    """The unmapped-but-blocked row's declared_blocker is visible via
    unmapped_responsibilities even after the whole document is composed —
    it never gets a real card (owner still unrecognized), but the block is
    not lost."""
    agent_os_state = _agent_os_state([
        _ws_row(
            "FIX2-END-TO-END", owner="ops",
            blocked_by=["operator: rotate the credential"],
        )
    ])
    snap = proj.build_autonomy_snapshot(
        inbox=None, boot_packet=None, active_builds=None,
        agent_os_state=agent_os_state, runtime_jobs=None, bindings=None,
    )
    declared_blockers = proj.declared_blockers_from_agent_os_state(agent_os_state)
    unmapped = proj.unmapped_responsibilities_from_agent_os_state(agent_os_state)
    doc = proj.project_autonomy(
        snap, generated_at="G",
        declared_blockers=declared_blockers,
        unmapped_responsibilities=unmapped,
    )

    assert doc["responsibilities"] == []
    assert len(doc["unmapped_responsibilities"]) == 1
    row = doc["unmapped_responsibilities"][0]
    assert row["responsibility_ref"] == "WS:FIX2-END-TO-END"
    assert row["declared_blocker"]["target_seat"] is None
    assert "rotate the credential" in row["declared_blocker"]["explanation"]


# --- Fix 3: root_job_id None with real runtime evidence must not neutralize -

def test_fix3_root_job_id_none_with_a_runtime_fact_is_not_neutralized():
    """Even though get_current_runtime always REFUSES with the SAME sole
    runtime_root_missing issue when root_job_id is None (it short-circuits
    before ever looking at candidates), a genuine RuntimeFact attached to
    this responsibility must keep the card REFUSED, not silently OK."""
    ref = "WS:FIX3-HIDDEN-RUNTIME"
    resp = _responsibility(ref=ref, root_job_id=None)
    worker = _runtime(ref=ref, seat="WORKER", attempt_id="ATT-FIX3-A")
    snap = _snapshot(responsibilities=(resp,), runtimes=(worker,))

    doc = proj.project_autonomy(snap, generated_at="G")
    card = _card(doc, ref)

    assert card["query_status"] == "refused"
    assert card["is_actionable"] is False
    assert card["current_worker"] is None  # still unanswerable via this call


def test_fix3_root_job_id_none_with_effect_unknown_runtime_is_not_neutralized():
    """The EFFECT_UNKNOWN case named explicitly in the fix: a runtime fact
    that would otherwise REFUSE via reconciliation_required is just as
    invisible to get_current_runtime once root_job_id is None — it must
    not be waved through as OK either."""
    ref = "WS:FIX3-HIDDEN-EFFECT-UNKNOWN"
    resp = _responsibility(ref=ref, root_job_id=None)
    worker = _runtime(
        ref=ref, seat="WORKER", attempt_id="ATT-FIX3-B", effect_state="EFFECT_UNKNOWN",
    )
    snap = _snapshot(responsibilities=(resp,), runtimes=(worker,))

    doc = proj.project_autonomy(snap, generated_at="G")
    card = _card(doc, ref)

    assert card["query_status"] == "refused"
    assert card["is_actionable"] is False


def test_fix3_root_job_id_none_and_genuinely_no_runtime_still_neutralizes():
    """Regression guard: the ordinary, genuinely-empty case (no runtimes
    anywhere in the snapshot) must still neutralize to OK — Fix 3 tightens
    the guard, it does not remove the routine-absence behavior Change A
    added it for."""
    ref = "WS:FIX3-GENUINELY-EMPTY"
    resp = _responsibility(ref=ref, root_job_id=None)
    snap = _snapshot(responsibilities=(resp,))  # runtimes=() by default

    doc = proj.project_autonomy(snap, generated_at="G")
    card = _card(doc, ref)

    assert card["query_status"] == "ok"


# --- Fix 4: source-failure code colliding with runtime_root_missing --------

def test_fix4_source_failure_coded_runtime_root_missing_does_not_neutralize():
    """A caller-authored SourceFailure whose code happens to collide with
    "runtime_root_missing" — for an entirely unrelated outage (here,
    SURFACE_BINDINGS, an owner get_current_runtime never even consults) —
    must not silently neutralize a genuinely root_job_id-less card's own
    REFUSED result to OK, mirroring _CardIssues's own collision guard."""
    ref = "WS:FIX4-COLLISION-ROOT-MISSING"
    resp = _responsibility(ref=ref, root_job_id=None)
    failure = _failure(
        owner="SURFACE_BINDINGS", code="runtime_root_missing",
        explanation="An unrelated surface-bindings outage sharing this code string.",
        source_ref="surface_bindings:collide-root-missing-1",
    )
    snap = _snapshot(responsibilities=(resp,), source_failures=(failure,))

    doc = proj.project_autonomy(snap, generated_at="G")
    card = _card(doc, ref)

    assert card["query_status"] == "refused"
    assert card["is_actionable"] is False


# --- Fix 5: an unreadable row gets a bounded receipt, never silence --------

def test_fix5_blank_key_row_gets_row_unreadable_receipt():
    agent_os_state = _agent_os_state([
        {"key": "", "title": "Has a title but a blank key", "status": "active"},
    ])
    unmapped = proj.unmapped_responsibilities_from_agent_os_state(agent_os_state)
    assert unmapped == (
        {"responsibility_ref": None, "reason": "row_unreadable"},
    )


def test_fix5_missing_key_row_gets_row_unreadable_receipt():
    agent_os_state = _agent_os_state([
        {"title": "No key field at all", "status": "active"},
    ])
    unmapped = proj.unmapped_responsibilities_from_agent_os_state(agent_os_state)
    assert unmapped == (
        {"responsibility_ref": None, "reason": "row_unreadable"},
    )


def test_fix5_blank_title_with_valid_key_gets_row_unreadable_receipt_with_ref():
    agent_os_state = _agent_os_state([
        _ws_row("FIX5-BLANK-TITLE", title="   ", owner="chairman"),
    ])
    unmapped = proj.unmapped_responsibilities_from_agent_os_state(agent_os_state)
    assert unmapped == (
        {"responsibility_ref": "WS:FIX5-BLANK-TITLE", "reason": "row_unreadable"},
    )


def test_fix5_construction_raise_gets_row_unreadable_receipt():
    """A status containing whitespace passes the mapper's own blank-string
    checks but fails ResponsibilityFact.__post_init__'s _require_text — the
    construction-raises path this fix also covers, distinct from the
    key/title-blank path above."""
    agent_os_state = _agent_os_state([
        _ws_row("FIX5-BAD-STATUS", owner="chairman", status="needs review"),
    ])
    snap = proj.build_autonomy_snapshot(
        inbox=None, boot_packet=None, active_builds=None,
        agent_os_state=agent_os_state, runtime_jobs=None, bindings=None,
    )
    assert snap.responsibilities == ()

    unmapped = proj.unmapped_responsibilities_from_agent_os_state(agent_os_state)
    assert unmapped == (
        {"responsibility_ref": "WS:FIX5-BAD-STATUS", "reason": "row_unreadable"},
    )


def test_fix5_unreadable_rows_never_suppress_a_sibling_rows_mapping():
    """One unreadable row must never suppress a genuinely readable sibling
    row in the same artifact."""
    agent_os_state = _agent_os_state([
        {"title": "No key at all", "status": "active"},
        _ws_row("FIX5-SIBLING-OK", owner="chairman", status="active"),
    ])
    snap = proj.build_autonomy_snapshot(
        inbox=None, boot_packet=None, active_builds=None,
        agent_os_state=agent_os_state, runtime_jobs=None, bindings=None,
    )
    assert len(snap.responsibilities) == 1
    assert snap.responsibilities[0].responsibility_ref == "WS:FIX5-SIBLING-OK"

    unmapped = proj.unmapped_responsibilities_from_agent_os_state(agent_os_state)
    assert unmapped == (
        {"responsibility_ref": None, "reason": "row_unreadable"},
    )


# ---------------------------------------------------------------------------
# Final adversarial review repair packet, 2026-09-01 — three more fixes
# found by the FINAL adversarial review (distinct from the "Fix 1"..."Fix 5"
# adversarial-review repair packet tested above): (1) an unbounded forward
# clock-skew tolerance let a far-future observed_at read CURRENT; (2) the
# ledger's "gated" count was Steward-blocker-only with no separate visible
# count of Agent-OS-declared blocks, so the summary could contradict a
# card/unmapped row's own detail; (3) FRESHNESS_BUDGET_HOURS was an unpinned
# free parameter — the whole 48h suite stayed green under several mutated
# values because no test pinned the constant itself or its exact boundary.
# ---------------------------------------------------------------------------

# --- Final Fix 1: bounded forward clock-skew tolerance ---------------------

def test_final_fix1_far_future_observed_at_reads_unknown_never_current():
    """The production defect: an artifact stamped in the far future
    (2999-01-01) composed against a 2026 reference used to read freshness
    "current" with counts["stale"] == 0 unconditionally, since a negative
    age is trivially <= FRESHNESS_BUDGET no matter how large in magnitude.
    Now it reads "unknown" — never "current" and never "stale"."""
    agent_os_state = _agent_os_state(
        [_ws_row("FINALFIX1-FAR-FUTURE", owner="chairman", status="active")],
        generated_at="2999-01-01T00:00:00Z",
    )
    reference_at = "2026-08-31T00:00:00Z"
    snap = proj.build_autonomy_snapshot(
        inbox=None, boot_packet=None, active_builds=None,
        agent_os_state=agent_os_state, runtime_jobs=None, bindings=None,
        generated_at=reference_at,
    )
    doc = proj.project_autonomy(snap, generated_at=reference_at)
    card = _card(doc, "WS:FINALFIX1-FAR-FUTURE")

    assert card["freshness"] == "unknown"
    assert card["freshness"] != "current"
    assert card["freshness"] != "stale"
    assert doc["counts"]["stale"] == 0


def test_final_fix1_modest_future_overshoot_beyond_tolerance_reads_unknown():
    """A more modest overshoot — well past the one-hour skew tolerance but
    nowhere near as extreme as the 2999 case — must read the same way:
    unknown, never current."""
    agent_os_state = _agent_os_state(
        [_ws_row("FINALFIX1-MODEST-FUTURE", owner="chairman", status="active")],
        generated_at="2026-09-02T00:00:00Z",  # one full day ahead of reference
    )
    reference_at = "2026-09-01T00:00:00Z"
    snap = proj.build_autonomy_snapshot(
        inbox=None, boot_packet=None, active_builds=None,
        agent_os_state=agent_os_state, runtime_jobs=None, bindings=None,
        generated_at=reference_at,
    )
    doc = proj.project_autonomy(snap, generated_at=reference_at)
    card = _card(doc, "WS:FINALFIX1-MODEST-FUTURE")

    assert card["freshness"] == "unknown"


def test_final_fix1_timestamp_inside_skew_tolerance_still_reads_current():
    """Genuine host clock skew — observed_at a few minutes ahead of the
    reference, well inside FUTURE_SKEW_TOLERANCE — must still read
    current, exactly as the pre-existing "at/after reference_at is skew,
    not staleness" rule always promised."""
    agent_os_state = _agent_os_state(
        [_ws_row("FINALFIX1-SKEW-OK", owner="chairman", status="active")],
        generated_at="2026-09-01T00:05:00Z",  # five minutes ahead of reference
    )
    reference_at = "2026-09-01T00:00:00Z"
    snap = proj.build_autonomy_snapshot(
        inbox=None, boot_packet=None, active_builds=None,
        agent_os_state=agent_os_state, runtime_jobs=None, bindings=None,
        generated_at=reference_at,
    )
    doc = proj.project_autonomy(snap, generated_at=reference_at)
    card = _card(doc, "WS:FINALFIX1-SKEW-OK")

    assert card["freshness"] == "current"


def test_final_fix1_far_future_card_is_never_actionable():
    """A composed-card proof: a far-future-stamped artifact must never
    become actionable — the exact "actionable on evidence that has not
    happened yet" failure mode this fix exists to close."""
    agent_os_state = _agent_os_state(
        [_ws_row("FINALFIX1-NOT-ACTIONABLE", owner="chairman", status="active")],
        generated_at="2999-01-01T00:00:00Z",
    )
    reference_at = "2026-08-31T00:00:00Z"
    snap = proj.build_autonomy_snapshot(
        inbox=None, boot_packet=None, active_builds=None,
        agent_os_state=agent_os_state, runtime_jobs=None, bindings=None,
        generated_at=reference_at,
    )
    doc = proj.project_autonomy(snap, generated_at=reference_at)
    card = _card(doc, "WS:FINALFIX1-NOT-ACTIONABLE")

    assert card["is_actionable"] is False
    assert card["actionability_reason"] == "freshness_unknown"
    assert doc["counts"]["actionable"] == 0


# --- Final Fix 2: the ledger's declared-block count must not read zero -----

def test_final_fix2_declared_block_count_is_never_zero_when_a_block_is_declared():
    """The production contradiction: counts["blocked"] (Steward-owned
    only) could read 0 while a real card's own declared_blocker field, or
    an unmapped row's declared_blocker sub-object, showed a genuine
    Agent-OS-declared block.  counts["declared_blocked"] must count both
    surfaces and must never read 0 when either one carries a block."""
    agent_os_state = _agent_os_state([
        _ws_row(
            "FINALFIX2-MAPPED-BLOCKED", owner="chairman",
            blocked_by=["Agent OS: blocked by upstream outage"],
        ),
        _ws_row(
            "FINALFIX2-UNMAPPED-BLOCKED", owner="grok-cn-c",
            blocked_by=["Agent OS: blocked by missing credential"],
        ),
    ])
    snap = proj.build_autonomy_snapshot(
        inbox=None, boot_packet=None, active_builds=None,
        agent_os_state=agent_os_state, runtime_jobs=None, bindings=None,
    )
    declared_blockers = proj.declared_blockers_from_agent_os_state(agent_os_state)
    unmapped = proj.unmapped_responsibilities_from_agent_os_state(agent_os_state)
    doc = proj.project_autonomy(
        snap, generated_at="G",
        declared_blockers=declared_blockers,
        unmapped_responsibilities=unmapped,
    )

    # Steward-owned "blocked" stays 0 — no BlockerFact exists anywhere in
    # this snapshot (Agent OS data can never build one; see module
    # docstring point 8).  The point of this fix: that must not be the
    # only number the Chairman sees.
    assert doc["counts"]["blocked"] == 0
    assert doc["counts"]["declared_blocked"] == 2
    assert doc["counts"]["declared_blocked"] != 0

    mapped_card = _card(doc, "WS:FINALFIX2-MAPPED-BLOCKED")
    assert mapped_card["declared_blocker"] is not None
    unmapped_row = doc["unmapped_responsibilities"][0]
    assert unmapped_row["responsibility_ref"] == "WS:FINALFIX2-UNMAPPED-BLOCKED"
    assert unmapped_row["declared_blocker"] is not None


def test_final_fix2_steward_and_declared_blocks_stay_separately_countable():
    """A Steward-owned blocker and an Agent-OS-declared block must remain
    two distinct counters — never merged into one number — even when both
    are present at once in the same snapshot."""
    ref = "WS:FINALFIX2-BOTH-KINDS"
    resp = _responsibility(ref=ref)
    blocker = _blocker(
        ref=ref,
        code="BLOCKED",
        explanation="A real Steward-owned blocker.",
        target="WORKER",
        effect_state="NONE",
    )
    snap = _snapshot(responsibilities=(resp,), blockers=(blocker,))

    agent_os_state = _agent_os_state([
        _ws_row(
            "SIDECAR-DECLARED", owner="grok-cn-c",
            blocked_by=["Agent OS: a wholly separate declared block"],
        ),
    ])
    unmapped = proj.unmapped_responsibilities_from_agent_os_state(agent_os_state)

    doc = proj.project_autonomy(
        snap, generated_at="G", unmapped_responsibilities=unmapped,
    )
    card = _card(doc, ref)

    assert card["blocker"] is not None
    # Both kinds present at once: each has its own count, each == 1, and
    # they are two distinct dict entries — not one merged figure.
    assert doc["counts"]["blocked"] == 1
    assert doc["counts"]["declared_blocked"] == 1
    assert "blocked" in doc["counts"] and "declared_blocked" in doc["counts"]


# --- Final Fix 3: pin the freshness budget as a value, not just a shape ----

def test_final_fix3_freshness_budget_hours_is_pinned_at_48():
    """The review mutated FRESHNESS_BUDGET_HOURS to 13, 150, and 215 and
    the whole suite stayed green — an unpinned free parameter.  Pin the
    exact value so a silent mutation is caught here directly."""
    assert proj.FRESHNESS_BUDGET_HOURS == 48


def test_final_fix3_exactly_at_budget_boundary_is_current():
    """observed_at exactly FRESHNESS_BUDGET_HOURS (48h) before the
    reference — the closed edge of the CURRENT interval."""
    agent_os_state = _agent_os_state(
        [_ws_row("FINALFIX3-EXACT-BOUNDARY", owner="chairman", status="active")],
        generated_at="2026-08-30T00:00:00Z",
    )
    reference_at = "2026-09-01T00:00:00Z"  # exactly 48h later
    snap = proj.build_autonomy_snapshot(
        inbox=None, boot_packet=None, active_builds=None,
        agent_os_state=agent_os_state, runtime_jobs=None, bindings=None,
        generated_at=reference_at,
    )
    doc = proj.project_autonomy(snap, generated_at=reference_at)
    card = _card(doc, "WS:FINALFIX3-EXACT-BOUNDARY")

    assert card["freshness"] == "current"


def test_final_fix3_one_microsecond_past_budget_boundary_is_stale():
    """observed_at one microsecond OLDER than the 48h budget — the open
    edge, immediately across the boundary from the case above."""
    agent_os_state = _agent_os_state(
        [_ws_row("FINALFIX3-PAST-BOUNDARY", owner="chairman", status="active")],
        generated_at="2026-08-29T23:59:59.999999Z",
    )
    reference_at = "2026-09-01T00:00:00Z"  # 48h + 1 microsecond later
    snap = proj.build_autonomy_snapshot(
        inbox=None, boot_packet=None, active_builds=None,
        agent_os_state=agent_os_state, runtime_jobs=None, bindings=None,
        generated_at=reference_at,
    )
    doc = proj.project_autonomy(snap, generated_at=reference_at)
    card = _card(doc, "WS:FINALFIX3-PAST-BOUNDARY")

    assert card["freshness"] == "stale"


# ---------------------------------------------------------------------------
# Sol review addenda (2026-09-03): stale history must never read as urgency
#
# On the real all-stale evidence packet the product could still raise
# "YOUR CALL / Only you can decide" on a card simultaneously labelled
# HISTORY / not actionable.  Urgency is a claim about NOW, so it requires
# CURRENT evidence.  Two of the four below are mutation-killing against the
# freshness gate (the stale BlockerFact and stale declared-blocker cases);
# the EFFECT_UNKNOWN case is a POSITIVE control that must survive the revert,
# and the stale-attention case is defended by the pre-existing owed-turn
# classifier rather than by this repair — its docstring says so.  Recorded
# precisely because "each of these kills the mutation" was the claim an
# independent review corrected.  Nothing is erased — every case below
# re-asserts that the historical owed turn, attribution and receipts survive.
# ---------------------------------------------------------------------------


def test_addendum_stale_chairman_attention_keeps_history_but_is_not_urgent():
    """A STALE Chairman-targeted AttentionFact owes the turn but is history."""
    snap = _snapshot(
        responsibilities=(_responsibility(freshness="STALE"),),
        attention=(_attention(attention_id="ATT-STALE-CHAIR", target="CHAIRMAN", freshness="STALE"),),
    )
    doc = proj.project_autonomy(snap, generated_at="2026-09-01T00:00:00Z")
    card = _card(doc, "WS:AD-CR1A")

    assert card["freshness"] == "stale"
    assert card["chairman_decision_required"] is False
    assert "WS:AD-CR1A" not in doc["chairman_decisions"]
    # Recorded here because it is easy to assume otherwise: a STALE attention
    # already yields no owed-turn signal at all, so this card is defended by
    # the pre-existing owed-turn classifier rather than by the freshness gate.
    # The identical CURRENT fact does produce seat "chairman" via
    # "attention_targets_seat" — see the EFFECT_UNKNOWN positive control below.
    assert card["owed_turn"]["seat"] == "unknown"
    assert card["owed_turn"]["reason"] == "no_owed_turn_signal"
    assert card["source_receipts"]  # receipts survive regardless


def test_addendum_stale_chairman_blocker_keeps_history_but_is_not_urgent():
    """A STALE Chairman-targeted BlockerFact: same rule, different fact kind."""
    snap = _snapshot(
        responsibilities=(_responsibility(freshness="STALE"),),
        blockers=(_blocker(target="CHAIRMAN", freshness="STALE"),),
    )
    doc = proj.project_autonomy(snap, generated_at="2026-09-01T00:00:00Z")
    card = _card(doc, "WS:AD-CR1A")

    assert card["freshness"] == "stale"
    assert card["chairman_decision_required"] is False
    assert "WS:AD-CR1A" not in doc["chairman_decisions"]
    assert card["blocker"] is not None  # attribution survives
    assert card["owed_turn"]["seat"] == "chairman"


def test_addendum_stale_declared_blocker_participates_in_freshness():
    """Repair A1: a declared blocker's SourceRef is a contributing source.

    Before the repair its receipt participated in freshness NOWHERE, so a
    stale Agent-OS declared block could drive a Chairman turn on a card that
    still resolved CURRENT.
    """
    snap = _snapshot(responsibilities=(_responsibility(),))  # identity is CURRENT
    doc = proj.project_autonomy(
        snap,
        generated_at="2026-09-01T00:00:00Z",
        declared_blockers={
            "WS:AD-CR1A": _declared(target_seat="chairman", freshness="STALE"),
        },
    )
    card = _card(doc, "WS:AD-CR1A")

    # the stale declared receipt drags the whole card's freshness down
    assert card["freshness"] == "stale"
    assert card["chairman_decision_required"] is False
    assert "WS:AD-CR1A" not in doc["chairman_decisions"]
    # the declared block itself stays visible and separately attributed
    assert card["declared_blocker"] is not None
    assert card["declared_blocker"]["source"]["owner"] == "agent_os"
    assert card["blocker"] is None  # never merged into the Steward blocker


def test_addendum_current_effect_unknown_still_requires_a_chairman_decision():
    """Positive control: the gate is FRESHNESS, deliberately not actionability.

    A CURRENT canonical EFFECT_UNKNOWN reconciliation blocker is a genuine
    Chairman decision even though retry/operation actionability is false.  A
    gate on ``is_actionable`` would have wrongly silenced this.
    """
    snap = _snapshot(
        responsibilities=(_responsibility(),),
        blockers=(_blocker(target="CHAIRMAN", effect_state="EFFECT_UNKNOWN"),),
    )
    doc = proj.project_autonomy(snap, generated_at="2026-09-01T00:00:00Z")
    card = _card(doc, "WS:AD-CR1A")

    assert card["freshness"] == "current"
    assert card["is_actionable"] is False
    assert card["chairman_decision_required"] is True
    assert "WS:AD-CR1A" in doc["chairman_decisions"]


# ---------------------------------------------------------------------------
# dispatch-consumption projection (AD-CR1A commissioning packet, 2026-09-03)
#
# ``project_dispatch_consumption`` is a SECOND pure pass over already-produced
# responsibility cards (the exact ``responsibility_ref``/``root_job_id`` pair
# each card already carries — Law 1's exact join key, never title/provider
# label/newest-timestamp).  It answers one question the rest of this module
# never asks: was a dispatched piece of work actually picked up and started,
# or sent into a void?  The real owners (wake_ledger.reconstruct_status,
# sol_action_target.resolve_sol_action_target, operator_continuity_
# projection's attempt/continuation facts, the Agent Dialogue TurnDecision/
# ObservationReceipt) all require I/O or live outside control_plane's
# importable surface, so this module never calls them — every test here
# hands the mapper already-gathered plain data through ``dispatch_evidence``,
# exactly as ``declared_blockers``/``unmapped_responsibilities`` already do
# for ``project_autonomy``.
# ---------------------------------------------------------------------------

_DISPATCH_GENERATED_AT = "2026-09-01T00:00:00Z"
_DISPATCH_STALE_OBSERVED_AT = "2026-08-20T00:00:00Z"  # >48h before generated_at


def _dcard(ref="WS:AD-CR1A", root_job_id="JOB-AD-CR1A"):
    return {"responsibility_ref": ref, "root_job_id": root_job_id}


def _drow(
    ref="WS:AD-CR1A",
    root_job_id="JOB-AD-CR1A",
    *,
    observed_at=_DISPATCH_GENERATED_AT,
    obligation_status=None,
    action_target_state=None,
    action_target_reason=None,
    binding_evidence_state=None,
    attempt_state=None,
    effect_state=None,
    watch_child_ref=None,
    watch_operation=None,
    watch_carrier_ref=None,
    watch_mechanism=None,
    watch_baseline_receipt=None,
    return_kind=None,
    return_child_ref=None,
    return_operation=None,
    return_carrier_ref=None,
    return_edge_ref=None,
    return_observed_at=None,
    sol_decision=None,
    sol_decision_carrier_ref=None,
    sol_decision_child_ref=None,
    sol_decision_operation=None,
    sol_decision_at=None,
):
    return {
        "responsibility_ref": ref,
        "root_job_id": root_job_id,
        "observed_at": observed_at,
        "obligation_status": obligation_status,
        "action_target_state": action_target_state,
        "action_target_reason": action_target_reason,
        "binding_evidence_state": binding_evidence_state,
        "attempt_state": attempt_state,
        "effect_state": effect_state,
        "watch_child_ref": watch_child_ref,
        "watch_operation": watch_operation,
        "watch_carrier_ref": watch_carrier_ref,
        "watch_mechanism": watch_mechanism,
        "watch_baseline_receipt": watch_baseline_receipt,
        "return_kind": return_kind,
        "return_child_ref": return_child_ref,
        "return_operation": return_operation,
        "return_carrier_ref": return_carrier_ref,
        "return_edge_ref": return_edge_ref,
        "return_observed_at": return_observed_at,
        "sol_decision": sol_decision,
        "sol_decision_carrier_ref": sol_decision_carrier_ref,
        "sol_decision_child_ref": sol_decision_child_ref,
        "sol_decision_operation": sol_decision_operation,
        "sol_decision_at": sol_decision_at,
    }


#: A fully proven watch + return receipt: the base 5-field watch proof PLUS
#: Blocker 3's return receipt (closed return_kind, exact child/operation/
#: carrier identity matching the watch_* fields, an observed edge, and an
#: observation time) — everything a terminal Attempt needs to legitimately
#: reach RETURNED.
_RETURN_OBSERVED_AT = "2026-08-31T12:00:00Z"  # before _DISPATCH_GENERATED_AT


def _proven_watch(**overrides):
    values = {
        "watch_child_ref": "child:JOB-AD-CR1A",
        "watch_operation": "op:AD-CR1A",
        "watch_carrier_ref": "carrier:C0123",
        "watch_mechanism": "cron",
        "watch_baseline_receipt": "receipt:abc123",
        "return_kind": "RESULT",
        "return_child_ref": "child:JOB-AD-CR1A",
        "return_operation": "op:AD-CR1A",
        "return_carrier_ref": "carrier:C0123",
        "return_edge_ref": "edge:1",
        "return_observed_at": _RETURN_OBSERVED_AT,
    }
    values.update(overrides)
    return values


def _dcard_of(doc, ref):
    for card in doc["cards"]:
        if card["responsibility_ref"] == ref:
            return card
    raise AssertionError(f"no dispatch card for {ref}")


def test_dispatch_unconsumed_delivery():
    """Law 2: a delivery with no valid exact receiver ACK is DELIVERY_UNCONSUMED."""
    doc = proj.project_dispatch_consumption(
        [_dcard()],
        generated_at=_DISPATCH_GENERATED_AT,
        dispatch_evidence=[_drow(obligation_status="DELIVERED_UNACKNOWLEDGED")],
    )
    card = _dcard_of(doc, "WS:AD-CR1A")
    assert card["dispatch_state"] == "DELIVERY_UNCONSUMED"
    assert card["actionable"] is False


def test_dispatch_ack_without_start():
    """Law 3: PICKUP_ACKNOWLEDGED stays distinct from STARTED with no attempt evidence."""
    doc = proj.project_dispatch_consumption(
        [_dcard()],
        generated_at=_DISPATCH_GENERATED_AT,
        dispatch_evidence=[_drow(obligation_status="TARGET_ACKNOWLEDGED")],
    )
    card = _dcard_of(doc, "WS:AD-CR1A")
    assert card["dispatch_state"] == "PICKUP_ACKNOWLEDGED"
    assert card["dispatch_state"] != "STARTED"
    assert card["actionable"] is False


def test_dispatch_start_without_valid_binding():
    """Law 4+7: attempt evidence exists but the binding is missing -> reconciliation, not STARTED."""
    doc = proj.project_dispatch_consumption(
        [_dcard()],
        generated_at=_DISPATCH_GENERATED_AT,
        dispatch_evidence=[_drow(
            obligation_status="TARGET_ACKNOWLEDGED",
            attempt_state="RUNNING",
            action_target_state="UNAVAILABLE",
            action_target_reason="ROOT_TARGET_MISSING",
        )],
    )
    card = _dcard_of(doc, "WS:AD-CR1A")
    assert card["dispatch_state"] == "RUNTIME_BINDING_RECONCILIATION_REQUIRED"
    assert card["dispatch_state"] != "STARTED"
    assert card["actionable"] is False


def test_dispatch_post_start_contradictory_rebind():
    """Law 7: a later CONFLICT demotes even though attempt evidence still reads RUNNING."""
    doc = proj.project_dispatch_consumption(
        [_dcard()],
        generated_at=_DISPATCH_GENERATED_AT,
        dispatch_evidence=[_drow(
            obligation_status="TARGET_ACKNOWLEDGED",
            attempt_state="RUNNING",
            action_target_state="CONFLICT",
            binding_evidence_state="CURRENT",
        )],
    )
    card = _dcard_of(doc, "WS:AD-CR1A")
    assert card["dispatch_state"] == "RUNTIME_BINDING_RECONCILIATION_REQUIRED"


def test_dispatch_result_awaiting_sol():
    """Law 5: RETURNED remains awaiting Sol with no valid CONTINUE/STOP yet."""
    doc = proj.project_dispatch_consumption(
        [_dcard()],
        generated_at=_DISPATCH_GENERATED_AT,
        dispatch_evidence=[_drow(
            obligation_status="TARGET_ACKNOWLEDGED",
            attempt_state="COMPLETED",
            action_target_state="RESOLVED",
            binding_evidence_state="CURRENT",
            **_proven_watch(),
        )],
    )
    card = _dcard_of(doc, "WS:AD-CR1A")
    assert card["dispatch_state"] == "RETURNED"
    assert card["actionable"] is True


def test_dispatch_continue():
    doc = proj.project_dispatch_consumption(
        [_dcard()],
        generated_at=_DISPATCH_GENERATED_AT,
        dispatch_evidence=[_drow(
            obligation_status="TARGET_ACKNOWLEDGED",
            attempt_state="COMPLETED",
            action_target_state="RESOLVED",
            binding_evidence_state="CURRENT",
            sol_decision="CONTINUE",
            sol_decision_carrier_ref="carrier:C0123",
            sol_decision_child_ref="child:JOB-AD-CR1A",
            sol_decision_operation="op:AD-CR1A",
            sol_decision_at="2026-08-31T13:00:00Z",
            **_proven_watch(),
        )],
    )
    card = _dcard_of(doc, "WS:AD-CR1A")
    assert card["dispatch_state"] == "CONTINUED"
    assert card["actionable"] is False


def test_dispatch_stop():
    doc = proj.project_dispatch_consumption(
        [_dcard()],
        generated_at=_DISPATCH_GENERATED_AT,
        dispatch_evidence=[_drow(
            obligation_status="TARGET_ACKNOWLEDGED",
            attempt_state="COMPLETED",
            action_target_state="RESOLVED",
            binding_evidence_state="CURRENT",
            sol_decision="STOP",
            sol_decision_carrier_ref="carrier:C0123",
            sol_decision_child_ref="child:JOB-AD-CR1A",
            sol_decision_operation="op:AD-CR1A",
            sol_decision_at="2026-08-31T13:00:00Z",
            **_proven_watch(),
        )],
    )
    card = _dcard_of(doc, "WS:AD-CR1A")
    assert card["dispatch_state"] == "STOPPED"
    assert card["actionable"] is False


def test_dispatch_continue_from_a_different_carrier_is_not_trusted():
    """Law 5 + Blocker 4: 'valid same-carrier' — a decision from a different
    carrier never resolves RETURNED, even with a valid child/operation/timing."""
    doc = proj.project_dispatch_consumption(
        [_dcard()],
        generated_at=_DISPATCH_GENERATED_AT,
        dispatch_evidence=[_drow(
            obligation_status="TARGET_ACKNOWLEDGED",
            attempt_state="COMPLETED",
            action_target_state="RESOLVED",
            binding_evidence_state="CURRENT",
            sol_decision="CONTINUE",
            sol_decision_carrier_ref="carrier:SOMEONE_ELSE",
            sol_decision_child_ref="child:JOB-AD-CR1A",
            sol_decision_operation="op:AD-CR1A",
            sol_decision_at="2026-08-31T13:00:00Z",
            **_proven_watch(),
        )],
    )
    card = _dcard_of(doc, "WS:AD-CR1A")
    assert card["dispatch_state"] == "RETURNED"


def test_dispatch_decision_on_wrong_child_is_not_trusted():
    """Blocker 4: a decision naming the wrong exact child never closes the dialogue."""
    doc = proj.project_dispatch_consumption(
        [_dcard()],
        generated_at=_DISPATCH_GENERATED_AT,
        dispatch_evidence=[_drow(
            obligation_status="TARGET_ACKNOWLEDGED",
            attempt_state="COMPLETED",
            action_target_state="RESOLVED",
            binding_evidence_state="CURRENT",
            sol_decision="STOP",
            sol_decision_carrier_ref="carrier:C0123",
            sol_decision_child_ref="child:SOME-OTHER-JOB",
            sol_decision_operation="op:AD-CR1A",
            sol_decision_at="2026-08-31T13:00:00Z",
            **_proven_watch(),
        )],
    )
    card = _dcard_of(doc, "WS:AD-CR1A")
    assert card["dispatch_state"] == "RETURNED"


def test_dispatch_decision_on_wrong_operation_is_not_trusted():
    """Blocker 4: a decision naming the wrong exact operation never closes the dialogue."""
    doc = proj.project_dispatch_consumption(
        [_dcard()],
        generated_at=_DISPATCH_GENERATED_AT,
        dispatch_evidence=[_drow(
            obligation_status="TARGET_ACKNOWLEDGED",
            attempt_state="COMPLETED",
            action_target_state="RESOLVED",
            binding_evidence_state="CURRENT",
            sol_decision="CONTINUE",
            sol_decision_carrier_ref="carrier:C0123",
            sol_decision_child_ref="child:JOB-AD-CR1A",
            sol_decision_operation="op:SOME-OTHER-OP",
            sol_decision_at="2026-08-31T13:00:00Z",
            **_proven_watch(),
        )],
    )
    card = _dcard_of(doc, "WS:AD-CR1A")
    assert card["dispatch_state"] == "RETURNED"


def test_dispatch_stale_decision_at_or_before_the_return_is_not_trusted():
    """Blocker 4: a decision edge must be causally AFTER the return — a
    decision timestamped at or before the return's own observation time
    (a stale/replayed decision) never closes the dialogue."""
    at_or_before = proj.project_dispatch_consumption(
        [_dcard()],
        generated_at=_DISPATCH_GENERATED_AT,
        dispatch_evidence=[_drow(
            obligation_status="TARGET_ACKNOWLEDGED",
            attempt_state="COMPLETED",
            action_target_state="RESOLVED",
            binding_evidence_state="CURRENT",
            sol_decision="CONTINUE",
            sol_decision_carrier_ref="carrier:C0123",
            sol_decision_child_ref="child:JOB-AD-CR1A",
            sol_decision_operation="op:AD-CR1A",
            sol_decision_at=_RETURN_OBSERVED_AT,  # exactly AT the return, not after
            **_proven_watch(),
        )],
    )
    card = _dcard_of(at_or_before, "WS:AD-CR1A")
    assert card["dispatch_state"] == "RETURNED"

    before = proj.project_dispatch_consumption(
        [_dcard()],
        generated_at=_DISPATCH_GENERATED_AT,
        dispatch_evidence=[_drow(
            obligation_status="TARGET_ACKNOWLEDGED",
            attempt_state="COMPLETED",
            action_target_state="RESOLVED",
            binding_evidence_state="CURRENT",
            sol_decision="STOP",
            sol_decision_carrier_ref="carrier:C0123",
            sol_decision_child_ref="child:JOB-AD-CR1A",
            sol_decision_operation="op:AD-CR1A",
            sol_decision_at="2026-08-30T00:00:00Z",  # before the return
            **_proven_watch(),
        )],
    )
    card2 = _dcard_of(before, "WS:AD-CR1A")
    assert card2["dispatch_state"] == "RETURNED"


def test_dispatch_missing_watcher_receipt():
    """Law 6 + Blocker 4: WATCH_PROVEN requires exact child + operation +
    carrier + mechanism + baseline receipt."""
    doc = proj.project_dispatch_consumption(
        [_dcard()],
        generated_at=_DISPATCH_GENERATED_AT,
        dispatch_evidence=[_drow(
            obligation_status="TARGET_ACKNOWLEDGED",
            attempt_state="COMPLETED",
            action_target_state="RESOLVED",
            binding_evidence_state="CURRENT",
            watch_child_ref="child:JOB-AD-CR1A",
            watch_carrier_ref="carrier:C0123",
            # watch_operation, watch_mechanism and watch_baseline_receipt are missing
        )],
    )
    card = _dcard_of(doc, "WS:AD-CR1A")
    assert card["dispatch_state"] == "WATCH_UNPROVEN"
    assert card["watch_proven"] is False
    assert card["actionable"] is False


def test_dispatch_terminal_attempt_with_no_return_receipt_is_never_returned():
    """Blocker 3: 'Attempt terminality ALONE is never a worker return.' A
    FAILED/LOST/CANCELLED Attempt with the full base watch proof but NO
    return receipt (no return_kind/child/operation/carrier/edge/observed_at)
    must render WATCH_UNPROVEN, never RETURNED — and must never be
    actionable."""
    for terminal in ("FAILED", "LOST", "CANCELLED"):
        doc = proj.project_dispatch_consumption(
            [_dcard()],
            generated_at=_DISPATCH_GENERATED_AT,
            dispatch_evidence=[_drow(
                obligation_status="TARGET_ACKNOWLEDGED",
                attempt_state=terminal,
                action_target_state="RESOLVED",
                binding_evidence_state="CURRENT",
                watch_child_ref="child:JOB-AD-CR1A",
                watch_operation="op:AD-CR1A",
                watch_carrier_ref="carrier:C0123",
                watch_mechanism="cron",
                watch_baseline_receipt="receipt:abc123",
                # no return_* fields at all: no genuine Observer receipt.
            )],
        )
        card = _dcard_of(doc, "WS:AD-CR1A")
        assert card["dispatch_state"] == "WATCH_UNPROVEN", (terminal, card)
        assert card["dispatch_state"] != "RETURNED"
        assert card["actionable"] is False


def test_dispatch_return_receipt_wrong_child_or_operation_is_not_proven():
    """Blocker 3: the return receipt must name the EXACT SAME child and
    operation the watcher was actually bound to — not merely non-blank
    strings — or the terminal Attempt stays WATCH_UNPROVEN."""
    wrong_child = proj.project_dispatch_consumption(
        [_dcard()],
        generated_at=_DISPATCH_GENERATED_AT,
        dispatch_evidence=[_drow(
            obligation_status="TARGET_ACKNOWLEDGED",
            attempt_state="COMPLETED",
            action_target_state="RESOLVED",
            binding_evidence_state="CURRENT",
            **_proven_watch(return_child_ref="child:SOME-OTHER-JOB"),
        )],
    )
    assert _dcard_of(wrong_child, "WS:AD-CR1A")["dispatch_state"] == "WATCH_UNPROVEN"

    wrong_operation = proj.project_dispatch_consumption(
        [_dcard()],
        generated_at=_DISPATCH_GENERATED_AT,
        dispatch_evidence=[_drow(
            obligation_status="TARGET_ACKNOWLEDGED",
            attempt_state="COMPLETED",
            action_target_state="RESOLVED",
            binding_evidence_state="CURRENT",
            **_proven_watch(return_operation="op:SOME-OTHER-OP"),
        )],
    )
    assert _dcard_of(wrong_operation, "WS:AD-CR1A")["dispatch_state"] == "WATCH_UNPROVEN"


def test_dispatch_return_receipt_unrecognized_kind_is_not_proven():
    """Blocker 3: return_kind must be from the closed BLOCKED/DECISION_REQUEST/
    RESULT vocabulary — anything else (including a caller-invented token)
    fails closed."""
    doc = proj.project_dispatch_consumption(
        [_dcard()],
        generated_at=_DISPATCH_GENERATED_AT,
        dispatch_evidence=[_drow(
            obligation_status="TARGET_ACKNOWLEDGED",
            attempt_state="COMPLETED",
            action_target_state="RESOLVED",
            binding_evidence_state="CURRENT",
            **_proven_watch(return_kind="SUCCESS"),
        )],
    )
    card = _dcard_of(doc, "WS:AD-CR1A")
    # An out-of-vocabulary return_kind is itself rejected by the Blocker 2
    # validator (closed vocabulary), so the whole row fails closed.
    assert card["dispatch_state"] == "UNKNOWN"
    assert card["actionable"] is False


def test_dispatch_missed_fire_is_stale_returned_never_actionable():
    """A proven-watch terminal attempt whose evidence has gone stale must not be actionable."""
    doc = proj.project_dispatch_consumption(
        [_dcard()],
        generated_at=_DISPATCH_GENERATED_AT,
        dispatch_evidence=[_drow(
            observed_at=_DISPATCH_STALE_OBSERVED_AT,
            obligation_status="TARGET_ACKNOWLEDGED",
            attempt_state="COMPLETED",
            action_target_state="RESOLVED",
            binding_evidence_state="CURRENT",
            **_proven_watch(),
        )],
    )
    card = _dcard_of(doc, "WS:AD-CR1A")
    assert card["dispatch_state"] == "RETURNED"
    assert card["historical"] is True
    assert card["actionable"] is False, "stale evidence must never leave an actuator open"


def test_dispatch_stale_evidence_marks_non_returned_steps_historical_too():
    """Law 9: a stale contributing source makes the projected step historical, not just RETURNED."""
    doc = proj.project_dispatch_consumption(
        [_dcard()],
        generated_at=_DISPATCH_GENERATED_AT,
        dispatch_evidence=[_drow(
            observed_at=_DISPATCH_STALE_OBSERVED_AT,
            obligation_status="ACCEPTED",
        )],
    )
    card = _dcard_of(doc, "WS:AD-CR1A")
    assert card["dispatch_state"] == "DELIVERY_SENT"
    assert card["historical"] is True


def test_dispatch_effect_unknown_outranks_optimistic_progress():
    """Law 8: EFFECT_UNKNOWN outranks optimistic progress and disables every actuator."""
    doc = proj.project_dispatch_consumption(
        [_dcard()],
        generated_at=_DISPATCH_GENERATED_AT,
        dispatch_evidence=[_drow(
            obligation_status="TARGET_ACKNOWLEDGED",
            attempt_state="COMPLETED",
            action_target_state="RESOLVED",
            binding_evidence_state="CURRENT",
            effect_state="effect_unknown",
            **_proven_watch(),
        )],
    )
    card = _dcard_of(doc, "WS:AD-CR1A")
    assert card["dispatch_state"] == "EFFECT_UNKNOWN"
    assert card["actionable"] is False


def test_dispatch_absent_owner_input_renders_unknown_never_a_success():
    """Absent dispatch_evidence: every card reads UNKNOWN, never a fabricated
    success stage, and Blocker 5: absent evidence is always historical too
    (unknown freshness, never the CURRENT-implying default)."""
    doc = proj.project_dispatch_consumption(
        [_dcard(), _dcard(ref="WS:OTHER", root_job_id="JOB-OTHER")],
        generated_at=_DISPATCH_GENERATED_AT,
        dispatch_evidence=None,
    )
    for card in doc["cards"]:
        assert card["dispatch_state"] == "UNKNOWN"
        assert card["actionable"] is False
        assert card["historical"] is True
    assert doc["counts"]["UNKNOWN"] == 2
    assert all(state == 0 for token, state in doc["counts"].items() if token != "UNKNOWN")


def test_dispatch_no_exact_join_match_renders_unknown_not_a_fuzzy_pick():
    """Law 1: exact join only — a mismatched root_job_id never matches by ref
    alone.  Blocker 5: an unmatched card is always historical too."""
    doc = proj.project_dispatch_consumption(
        [_dcard(root_job_id="JOB-REAL")],
        generated_at=_DISPATCH_GENERATED_AT,
        dispatch_evidence=[_drow(root_job_id="JOB-DIFFERENT", obligation_status="TARGET_ACKNOWLEDGED")],
    )
    card = _dcard_of(doc, "WS:AD-CR1A")
    assert card["dispatch_state"] == "UNKNOWN"
    assert card["historical"] is True
    assert card["actionable"] is False


def test_dispatch_ambiguous_evidence_is_unknown_and_historical():
    """Blocker 5: two rows sharing the same exact (responsibility_ref,
    root_job_id) join key must render UNKNOWN, non-actionable, AND
    historical — never resolved by recency or list order."""
    doc = proj.project_dispatch_consumption(
        [_dcard()],
        generated_at=_DISPATCH_GENERATED_AT,
        dispatch_evidence=[
            _drow(obligation_status="ACCEPTED"),
            _drow(obligation_status="TARGET_ACKNOWLEDGED"),
        ],
    )
    card = _dcard_of(doc, "WS:AD-CR1A")
    assert card["dispatch_state"] == "UNKNOWN"
    assert card["reason"] == "ambiguous_dispatch_evidence"
    assert card["historical"] is True
    assert card["actionable"] is False


def test_dispatch_pending_retryable_is_unresolved_never_progress():
    """TESTS: 'PENDING_RETRYABLE is unresolved not progress.'  It must never
    render as a delivered/started/returned stage."""
    doc = proj.project_dispatch_consumption(
        [_dcard()],
        generated_at=_DISPATCH_GENERATED_AT,
        dispatch_evidence=[_drow(obligation_status="PENDING_RETRYABLE")],
    )
    card = _dcard_of(doc, "WS:AD-CR1A")
    assert card["dispatch_state"] not in (
        "DELIVERY_SENT", "PICKUP_ACKNOWLEDGED", "STARTED", "RETURNED",
        "CONTINUED", "STOPPED",
    )
    assert card["dispatch_state"] in ("WAITING_CAPACITY", "RECEIVER_SELECTED")
    assert card["actionable"] is False


# ---------------------------------------------------------------------------
# Blocker 2: closed, bounded, secret-safe evidence validator.
# ---------------------------------------------------------------------------

def test_dispatch_evidence_non_mapping_row_is_ignored_not_crashed():
    """A non-mapping row (string/list/int/None) cannot be attributed to any
    card and must never raise — it degrades exactly like absent evidence."""
    doc = proj.project_dispatch_consumption(
        [_dcard()],
        generated_at=_DISPATCH_GENERATED_AT,
        dispatch_evidence=["not-a-mapping", 42, ["also", "not"], None],
    )
    card = _dcard_of(doc, "WS:AD-CR1A")
    assert card["dispatch_state"] == "UNKNOWN"
    assert card["historical"] is True
    assert card["actionable"] is False


def test_dispatch_evidence_unknown_key_fails_closed():
    """Blocker 2: an unrecognized key on an otherwise-valid row fails the
    WHOLE row closed to the fixed rejection reason — never silently ignored,
    never echoed."""
    row = _drow(obligation_status="ACCEPTED")
    row["not_a_real_field"] = "smuggled-value"
    doc = proj.project_dispatch_consumption(
        [_dcard()], generated_at=_DISPATCH_GENERATED_AT, dispatch_evidence=[row],
    )
    card = _dcard_of(doc, "WS:AD-CR1A")
    assert card["dispatch_state"] == "UNKNOWN"
    assert card["reason"] == "dispatch_evidence_rejected"
    assert card["evidence"] is None
    assert card["historical"] is True
    dumped = json.dumps(doc)
    assert "smuggled-value" not in dumped
    assert "not_a_real_field" not in dumped


def test_dispatch_evidence_secret_shaped_value_is_rejected_and_never_echoed():
    """Blocker 2: a path/secret-shaped value fails closed and never appears
    in ANY output string, including the rejection reason."""
    row = _drow(
        obligation_status="ACCEPTED",
        watch_baseline_receipt="/Users/chriswong/.ssh/id_rsa",
    )
    doc = proj.project_dispatch_consumption(
        [_dcard()], generated_at=_DISPATCH_GENERATED_AT, dispatch_evidence=[row],
    )
    card = _dcard_of(doc, "WS:AD-CR1A")
    assert card["dispatch_state"] == "UNKNOWN"
    assert card["reason"] == "dispatch_evidence_rejected"
    assert card["evidence"] is None
    dumped = json.dumps(doc)
    assert "id_rsa" not in dumped
    assert ".ssh" not in dumped


def test_dispatch_evidence_oversized_value_is_rejected():
    """Blocker 2: a value beyond the bounded per-field byte ceiling fails
    closed rather than being silently truncated or accepted."""
    row = _drow(obligation_status="ACCEPTED", watch_mechanism="x" * 10_000)
    doc = proj.project_dispatch_consumption(
        [_dcard()], generated_at=_DISPATCH_GENERATED_AT, dispatch_evidence=[row],
    )
    card = _dcard_of(doc, "WS:AD-CR1A")
    assert card["dispatch_state"] == "UNKNOWN"
    assert card["reason"] == "dispatch_evidence_rejected"
    assert card["evidence"] is None


def test_dispatch_evidence_non_serializable_value_is_rejected():
    """Blocker 2: a non-string value on a string-only field (a nested
    mapping/list/float/bool — never JSON-serializable as this schema
    expects) fails closed rather than being copied through verbatim."""
    for bad_value in ({"nested": "object"}, ["a", "list"], 3.14, True, 12345):
        row = _drow(obligation_status="ACCEPTED")
        row["watch_mechanism"] = bad_value
        doc = proj.project_dispatch_consumption(
            [_dcard()], generated_at=_DISPATCH_GENERATED_AT, dispatch_evidence=[row],
        )
        card = _dcard_of(doc, "WS:AD-CR1A")
        assert card["dispatch_state"] == "UNKNOWN", bad_value
        assert card["reason"] == "dispatch_evidence_rejected", bad_value
        assert card["evidence"] is None, bad_value


def test_dispatch_evidence_out_of_vocabulary_token_is_rejected_and_never_echoed():
    """Blocker 2: a field with a closed vocabulary (e.g. obligation_status)
    rejects any value outside that vocabulary, and the bad token itself
    never reaches any output string (the reason is fixed, not built from
    the caller's value)."""
    row = _drow(obligation_status="NOT_A_REAL_STATUS_TOKEN__INJECTED")
    doc = proj.project_dispatch_consumption(
        [_dcard()], generated_at=_DISPATCH_GENERATED_AT, dispatch_evidence=[row],
    )
    card = _dcard_of(doc, "WS:AD-CR1A")
    assert card["dispatch_state"] == "UNKNOWN"
    assert card["reason"] == "dispatch_evidence_rejected"
    dumped = json.dumps(doc)
    assert "NOT_A_REAL_STATUS_TOKEN__INJECTED" not in dumped


def test_dispatch_waiting_capacity_and_receiver_selected_happy_path():
    """Mission-suggested mapping: NOT_SEEN with no receiver -> WAITING_CAPACITY;
    ActionTargetState.RESOLVED with no delivery evidence -> RECEIVER_SELECTED."""
    waiting = proj.project_dispatch_consumption(
        [_dcard()],
        generated_at=_DISPATCH_GENERATED_AT,
        dispatch_evidence=[_drow(obligation_status="NOT_SEEN", action_target_state="UNKNOWN")],
    )
    assert _dcard_of(waiting, "WS:AD-CR1A")["dispatch_state"] == "WAITING_CAPACITY"

    selected = proj.project_dispatch_consumption(
        [_dcard()],
        generated_at=_DISPATCH_GENERATED_AT,
        dispatch_evidence=[_drow(obligation_status="NOT_SEEN", action_target_state="RESOLVED")],
    )
    assert _dcard_of(selected, "WS:AD-CR1A")["dispatch_state"] == "RECEIVER_SELECTED"


def test_dispatch_reconciliation_required_direct_signal():
    doc = proj.project_dispatch_consumption(
        [_dcard()],
        generated_at=_DISPATCH_GENERATED_AT,
        dispatch_evidence=[_drow(obligation_status="RECONCILIATION_REQUIRED")],
    )
    assert _dcard_of(doc, "WS:AD-CR1A")["dispatch_state"] == "RUNTIME_BINDING_RECONCILIATION_REQUIRED"


def test_dispatch_no_actuator_renders_for_any_unsafe_state():
    """No owed-action Open control may render for an unsafe state (mirrors the FROZEN SPEC UI law)."""
    unsafe_rows = {
        "DELIVERY_UNCONSUMED": _drow(obligation_status="DELIVERED_UNACKNOWLEDGED"),
        "WATCH_UNPROVEN": _drow(
            obligation_status="TARGET_ACKNOWLEDGED", attempt_state="COMPLETED",
            action_target_state="RESOLVED", binding_evidence_state="CURRENT",
        ),
        "RUNTIME_BINDING_RECONCILIATION_REQUIRED": _drow(obligation_status="RECONCILIATION_REQUIRED"),
        "EFFECT_UNKNOWN": _drow(effect_state="effect_unknown"),
        "UNKNOWN": _drow(obligation_status="not-a-real-token"),
    }
    for expected_state, row in unsafe_rows.items():
        doc = proj.project_dispatch_consumption(
            [_dcard()], generated_at=_DISPATCH_GENERATED_AT, dispatch_evidence=[row],
        )
        card = _dcard_of(doc, "WS:AD-CR1A")
        assert card["dispatch_state"] == expected_state, (expected_state, card)
        assert card["actionable"] is False, f"{expected_state} must never expose an actuator"


def test_dispatch_purity_same_input_twice_is_byte_identical():
    dispatch_evidence = [_drow(obligation_status="ACCEPTED")]
    first = proj.project_dispatch_consumption(
        [_dcard()], generated_at=_DISPATCH_GENERATED_AT, dispatch_evidence=dispatch_evidence,
    )
    second = proj.project_dispatch_consumption(
        [_dcard()], generated_at=_DISPATCH_GENERATED_AT, dispatch_evidence=dispatch_evidence,
    )
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


# ---------------------------------------------------------------------------
# Non-author review follow-up (2026-09-03): three findings on the dispatch
# projection, each pinned here.
# ---------------------------------------------------------------------------

_RV_W = {
    "watch_child_ref": "c1", "watch_operation": "op1", "watch_carrier_ref": "carr1",
    "watch_mechanism": "cron", "watch_baseline_receipt": "b1",
}
_RV_R = {
    "return_kind": "RESULT", "return_child_ref": "c1", "return_operation": "op1",
    "return_carrier_ref": "carr1", "return_edge_ref": "e1",
    "return_observed_at": "2026-09-03T10:00:00Z",
}
_RV_BASE = {
    "responsibility_ref": "WS:X", "root_job_id": "JOB-1",
    "observed_at": "2026-09-03T11:30:00Z",
}
_RV_G = "2026-09-03T12:00:00Z"


def _rv_card(row):
    doc = proj.project_dispatch_consumption(
        [{"responsibility_ref": "WS:X", "root_job_id": "JOB-1"}],
        generated_at=_RV_G, dispatch_evidence=[row],
    )
    return doc["cards"][0]


@pytest.mark.parametrize(
    "token",
    [
        "sk-live-QQLEAKQQ11111111",
        "sk-ant-QQLEAKQQ11111111",
        "xoxb-1234567890-QQLEAKQQ",
        "ghp_QQLEAKQQ1234567890AB",
        "glpat-QQLEAKQQ1234567890",
        "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJRUUxFQUtRUSJ9",
    ],
)
def test_review_secret_shaped_tokens_are_refused_and_never_echoed(token):
    """The earlier refusal matched credential NAMES (`api_key=`) but not bare
    live tokens, so a leak test using a named key passed while `sk-live-...`
    was accepted and rendered verbatim into `evidence.watch_mechanism`."""
    # Carry real progress evidence so the row COULD reach an actionable state
    # if the refusal failed — the earlier version asserted `actionable is
    # False` on a row that could never be actionable anyway, so that half of
    # the test was satisfied by a fully broken refusal (an independent review
    # produced leaking rows that were non-actionable for exactly this reason).
    card = _rv_card({
        **_RV_BASE, **_RV_W, **_RV_R, "attempt_state": "COMPLETED",
        "action_target_state": "RESOLVED", "binding_evidence_state": "CURRENT",
        "watch_mechanism": token,
    })

    assert card["reason"] == "dispatch_evidence_rejected", "row was accepted"
    assert card["actionable"] is False
    assert "QQLEAKQQ" not in json.dumps(card), "secret-shaped value reached the document"


def test_review_absent_binding_evidence_cannot_yield_attempt_progress():
    """Declaring UNKNOWN was demoted while OMITTING the same two fields was
    trusted as a resolved, current binding — so a row that said nothing was
    believed more than one that admitted ignorance.  The gather omits exactly
    these fields in the degraded release, so the degraded reader was strictly
    more optimistic than the complete one."""
    running = _rv_card({**_RV_BASE, **_RV_W, **_RV_R, "attempt_state": "RUNNING"})
    terminal = _rv_card({**_RV_BASE, **_RV_W, **_RV_R, "attempt_state": "FAILED"})

    assert running["dispatch_state"] == "RUNTIME_BINDING_RECONCILIATION_REQUIRED"
    assert terminal["dispatch_state"] == "RUNTIME_BINDING_RECONCILIATION_REQUIRED"
    assert running["reason"] == "runtime_binding_evidence_absent"


def test_review_resolved_binding_still_reaches_started_and_returned():
    """Positive control: the gate above must not be inert.  A guard that
    refuses everything passes every adversarial test for the wrong reason."""
    resolved = {"action_target_state": "RESOLVED", "binding_evidence_state": "CURRENT"}
    running = _rv_card({**_RV_BASE, **_RV_W, **_RV_R, **resolved, "attempt_state": "RUNNING"})
    terminal = _rv_card({**_RV_BASE, **_RV_W, **_RV_R, **resolved, "attempt_state": "FAILED"})

    assert running["dispatch_state"] == "STARTED"
    assert terminal["dispatch_state"] == "RETURNED"


def test_review_absent_binding_does_not_overwrite_delivery_derived_states():
    """Absence is deliberately narrower than a declared problem: a delivery is
    observed through the wake ledger and is true whether or not a
    RuntimeBinding was ever resolved, so demoting "delivered, never picked up"
    to a binding problem would trade an honest adverse state for a vaguer one."""
    unconsumed = _rv_card({**_RV_BASE, "obligation_status": "DELIVERED_UNACKNOWLEDGED"})
    acked = _rv_card({**_RV_BASE, "obligation_status": "TARGET_ACKNOWLEDGED"})

    assert unconsumed["dispatch_state"] == "DELIVERY_UNCONSUMED"
    assert acked["dispatch_state"] == "PICKUP_ACKNOWLEDGED"


def test_review_return_receipt_from_the_future_is_not_a_return():
    """`return_observed_at` was only required to PARSE, so a receipt stamped
    2999 read as a genuine return and permanently foreclosed CONTINUED/STOPPED
    for that row, since no real decision can ever postdate it."""
    resolved = {"action_target_state": "RESOLVED", "binding_evidence_state": "CURRENT"}
    card = _rv_card({
        **_RV_BASE, **_RV_W, **resolved, "attempt_state": "FAILED",
        **{**_RV_R, "return_observed_at": "2999-01-01T00:00:00Z"},
    })

    assert card["dispatch_state"] != "RETURNED"
    assert card["actionable"] is False


def test_review_validator_never_raises_on_a_hostile_mapping():
    """`_validate_dispatch_row` documents "never raises" but called
    `raw.keys()` on caller-supplied data; a mapping whose keys() raises took
    the whole document down, and unlike placement_selection the autonomy
    block is not wrapped."""
    class _Hostile(dict):
        def keys(self):
            raise RuntimeError("hostile mapping")

    card = _rv_card(_Hostile(responsibility_ref="WS:X", root_job_id="JOB-1"))
    # The property this test names is "did not raise" — reaching this line at
    # all is the assertion. The state must also be the fail-closed one.
    assert card["dispatch_state"] == "UNKNOWN"
    assert card["actionable"] is False


@pytest.mark.parametrize(
    "value",
    [
        "AIzaQQLEAKQQ1234567890abcdefghij",
        "ya29.QQLEAKQQ-abcdefghijklmnopqr",
        "postgres://user:QQLEAKQQ@db.internal/mydb",
        "QQLEAKQQ@example.com",
    ],
)
def test_review_structural_refusal_covers_shapes_no_prefix_list_would(value):
    """Enumerating credential prefixes was a losing shape.

    Two rounds of "add the ones we missed" still missed the next: after
    sk-/ghp_/JWT were added, a Google key, an OAuth token, a credential URL
    and an e-mail address all still reached the rendered document. These
    fields carry identifiers, refs and receipts, and no legitimate value of
    that kind contains a URL scheme or an at-sign, so those two characters
    are refused structurally rather than by family.
    """
    card = _rv_card({**_RV_BASE, "watch_mechanism": value})

    assert card["actionable"] is False
    assert "QQLEAKQQ" not in json.dumps(card)


@pytest.mark.parametrize(
    "value",
    [
        "a1b2c3d4e5f60718293a4b5c6d7e8f9012345678",  # a real SHA-shaped receipt
        "cron",
        "WS:AD-CR1A/job-1",
    ],
)
def test_review_structural_refusal_still_accepts_legitimate_identifiers(value):
    """Positive control: the refusal must not swallow the field's real use.

    A 40-hex value is exactly what `watch_baseline_receipt` is for, so
    refusing high-entropy strings outright would have broken the contract
    while looking like extra safety.
    """
    card = _rv_card({**_RV_BASE, "watch_mechanism": value})

    assert card["reason"] != "dispatch_evidence_rejected"


# ---------------------------------------------------------------------------
# Blocker 1 (review 5106453403): real responsibility -> Executive root join.
# ``build_autonomy_snapshot`` must stop discarding ``runtime_jobs`` and
# thread a genuinely resolved, deduplicated Runtime root into
# ``ResponsibilityFact.root_job_id`` -- never an inferred pick by title,
# newest, max, or provider.  Zero roots stays null/UNKNOWN; MULTIPLE
# distinct roots is explicit ambiguity/reconciliation, surfaced on the card
# as ``root_job_ambiguous``/``root_job_candidates`` -- never a pick.
# ---------------------------------------------------------------------------

def test_build_autonomy_snapshot_threads_the_unique_runtime_root_into_the_card():
    agent_os_state = _agent_os_state([_ws_row("ROOT-JOIN-WS", owner="coo-fable")])
    runtime_jobs = [
        {"job_id": "job-1", "status": "running", "workstream": "WS:ROOT-JOIN-WS",
         "root_job_id": "JOB-ROOT-AAAA"},
    ]
    snap = proj.build_autonomy_snapshot(
        inbox=None, boot_packet=None, active_builds=None,
        agent_os_state=agent_os_state, runtime_jobs=runtime_jobs, bindings=None,
    )
    assert len(snap.responsibilities) == 1
    assert snap.responsibilities[0].root_job_id == "JOB-ROOT-AAAA"

    doc = proj.project_autonomy(
        snap, generated_at="2026-09-03T00:00:00Z",
        runtime_root_candidates=proj.runtime_root_candidates_from_runtime_jobs(runtime_jobs),
    )
    card = _card(doc, "WS:ROOT-JOIN-WS")
    assert card["root_job_id"] == "JOB-ROOT-AAAA"
    assert card["root_job_ambiguous"] is False
    assert card["root_job_candidates"] == ["JOB-ROOT-AAAA"]


def test_build_autonomy_snapshot_zero_runtime_roots_stays_null():
    agent_os_state = _agent_os_state([_ws_row("NO-RUNTIME-WS", owner="coo-fable")])
    snap_no_jobs = proj.build_autonomy_snapshot(
        inbox=None, boot_packet=None, active_builds=None,
        agent_os_state=agent_os_state, runtime_jobs=None, bindings=None,
    )
    assert snap_no_jobs.responsibilities[0].root_job_id is None

    # A runtime job exists but cites a DIFFERENT workstream: still zero
    # roots for THIS one.
    runtime_jobs = [
        {"job_id": "job-x", "status": "running", "workstream": "WS:SOME-OTHER-WS",
         "root_job_id": "JOB-OTHER-1"},
    ]
    snap_unrelated = proj.build_autonomy_snapshot(
        inbox=None, boot_packet=None, active_builds=None,
        agent_os_state=agent_os_state, runtime_jobs=runtime_jobs, bindings=None,
    )
    assert snap_unrelated.responsibilities[0].root_job_id is None
    doc = proj.project_autonomy(
        snap_unrelated, generated_at="2026-09-03T00:00:00Z",
        runtime_root_candidates=proj.runtime_root_candidates_from_runtime_jobs(runtime_jobs),
    )
    card = _card(doc, "WS:NO-RUNTIME-WS")
    assert card["root_job_ambiguous"] is False
    assert card["root_job_candidates"] == []


def test_build_autonomy_snapshot_multiple_distinct_runtime_roots_is_never_picked():
    """Two DISTINCT Runtime roots cite the same workstream: this must read
    as explicit ambiguity/reconciliation on the card, never a silent pick
    of one candidate -- not the alphabetically first, not the
    alphabetically last, not the one that appears first/last in the input
    list."""
    agent_os_state = _agent_os_state([_ws_row("AMBIGUOUS-WS", owner="coo-fable")])
    runtime_jobs = [
        # Deliberately out of sort order and NOT last-wins: a naive
        # "first seen"/"last seen"/max()/min() pick would return one of
        # these two, never None.
        {"job_id": "job-z", "status": "running", "workstream": "WS:AMBIGUOUS-WS",
         "root_job_id": "JOB-ZZZZ-LATE"},
        {"job_id": "job-a", "status": "queued", "workstream": "WS:AMBIGUOUS-WS",
         "root_job_id": "JOB-AAAA-EARLY"},
    ]
    snap = proj.build_autonomy_snapshot(
        inbox=None, boot_packet=None, active_builds=None,
        agent_os_state=agent_os_state, runtime_jobs=runtime_jobs, bindings=None,
    )
    assert snap.responsibilities[0].root_job_id is None

    doc = proj.project_autonomy(
        snap, generated_at="2026-09-03T00:00:00Z",
        runtime_root_candidates=proj.runtime_root_candidates_from_runtime_jobs(runtime_jobs),
    )
    card = _card(doc, "WS:AMBIGUOUS-WS")
    assert card["root_job_id"] is None
    assert card["root_job_ambiguous"] is True
    assert card["root_job_candidates"] == ["JOB-AAAA-EARLY", "JOB-ZZZZ-LATE"]


def test_build_autonomy_snapshot_deleting_the_runtime_job_join_makes_the_root_vanish():
    """Falsifier: passing ``runtime_jobs=None`` (the join deleted) must make
    the previously-threaded root vanish -- proves the card's
    ``root_job_id`` is genuinely DERIVED from ``runtime_jobs``, not a
    coincidence/hardcode."""
    agent_os_state = _agent_os_state([_ws_row("DELETE-JOIN-WS", owner="coo-fable")])
    runtime_jobs = [
        {"job_id": "job-1", "status": "running", "workstream": "WS:DELETE-JOIN-WS",
         "root_job_id": "JOB-PRESENT-1"},
    ]
    with_join = proj.build_autonomy_snapshot(
        inbox=None, boot_packet=None, active_builds=None,
        agent_os_state=agent_os_state, runtime_jobs=runtime_jobs, bindings=None,
    )
    without_join = proj.build_autonomy_snapshot(
        inbox=None, boot_packet=None, active_builds=None,
        agent_os_state=agent_os_state, runtime_jobs=None, bindings=None,
    )
    assert with_join.responsibilities[0].root_job_id == "JOB-PRESENT-1"
    assert without_join.responsibilities[0].root_job_id is None


# ---------------------------------------------------------------------------
# Blocker 4 (review 5106453403): consume the durable terminal APPLIED
# receipt.  A valid ``terminal_return_state="APPLIED"`` row (the gather
# layer's own closed marker for a matching
# ``EXECUTIVE_TERMINAL_RETURN_APPLIED`` receipt) lets a terminal Attempt
# project RETURNED even with no Dialogue/Observer watch proof -- but
# terminal Attempt status ALONE (no applied marker at all) still stays
# WATCH_UNPROVEN, and live CONTINUE/STOP stays unavailable (no
# ``sol_decision`` owner exists yet).
# ---------------------------------------------------------------------------

def test_dispatch_terminal_return_applied_receipt_projects_returned():
    doc = proj.project_dispatch_consumption(
        [_dcard()],
        generated_at=_DISPATCH_GENERATED_AT,
        dispatch_evidence=[_drow(
            obligation_status="TARGET_ACKNOWLEDGED",
            attempt_state="COMPLETED",
            action_target_state="RESOLVED",
            binding_evidence_state="CURRENT",
        ) | {"terminal_return_state": "APPLIED"}],
    )
    card = _dcard_of(doc, "WS:AD-CR1A")
    assert card["dispatch_state"] == "RETURNED"
    assert card["actionable"] is True


def test_dispatch_terminal_attempt_alone_without_applied_marker_stays_unproven():
    """Terminal Attempt alone remains insufficient -- no watch proof AND no
    terminal_return_state marker must still render WATCH_UNPROVEN, never
    RETURNED."""
    doc = proj.project_dispatch_consumption(
        [_dcard()],
        generated_at=_DISPATCH_GENERATED_AT,
        dispatch_evidence=[_drow(
            obligation_status="TARGET_ACKNOWLEDGED",
            attempt_state="COMPLETED",
            action_target_state="RESOLVED",
            binding_evidence_state="CURRENT",
        )],
    )
    card = _dcard_of(doc, "WS:AD-CR1A")
    assert card["dispatch_state"] == "WATCH_UNPROVEN"
    assert card["actionable"] is False


def test_dispatch_terminal_return_applied_never_unlocks_live_continue_stop():
    """Live CONTINUE/STOP stays explicitly UNKNOWN until the W3C-I1 owner
    protects: an applied-return-proven row with NO sol_decision evidence
    must still render plain RETURNED, never CONTINUED/STOPPED."""
    doc = proj.project_dispatch_consumption(
        [_dcard()],
        generated_at=_DISPATCH_GENERATED_AT,
        dispatch_evidence=[_drow(
            obligation_status="TARGET_ACKNOWLEDGED",
            attempt_state="COMPLETED",
            action_target_state="RESOLVED",
            binding_evidence_state="CURRENT",
            sol_decision="CONTINUE",
        ) | {"terminal_return_state": "APPLIED"}],
    )
    card = _dcard_of(doc, "WS:AD-CR1A")
    # sol_decision alone, with none of the required exact-carrier/child/
    # operation identity fields, can never validate -- RETURNED stands.
    assert card["dispatch_state"] == "RETURNED"
