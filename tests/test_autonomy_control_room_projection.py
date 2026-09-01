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
        "total": 0, "actionable": 0, "stale": 0, "blocked": 0, "empty": True,
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
    })
    for card in doc["responsibilities"]:
        assert set(card.keys()) == {
            "responsibility_ref", "title", "accountable_seat", "state",
            "root_job_id", "current_worker", "current_sol_target",
            "owed_turn", "placement_state", "wake_outcome", "blocker",
            "freshness", "is_actionable", "actionability_reason",
            "chairman_decision_required", "chairman_decision_reason",
            "disagreements", "source_receipts", "query_status",
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
