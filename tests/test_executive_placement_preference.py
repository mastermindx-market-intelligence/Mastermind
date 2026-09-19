from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Sequence
from dataclasses import replace

import pytest

from control_plane import executive_placement_preference as epp
from control_plane import executive_placement_selection as eps
from control_plane.executive_steward import (
    CapacityState,
    EffectState,
    Freshness,
    ResponsibilityFact,
    Seat,
    SourceOwner,
    SourceRef,
)


def _source(owner: SourceOwner, ref: str, freshness: Freshness = Freshness.CURRENT) -> SourceRef:
    return SourceRef(
        owner=owner,
        ref=ref,
        observed_at="2026-09-15T05:40:00.000Z",
        freshness=freshness,
    )


def _responsibility(ref: str = "WS:CAP-FABLE") -> ResponsibilityFact:
    return ResponsibilityFact(
        responsibility_ref=ref,
        title="Four Fable principal pool",
        accountable_seat=Seat.COO,
        state="waiting_capacity",
        root_job_id=None,
        source=_source(SourceOwner.AGENT_OS, "agentos-cap-fable"),
    )


def _demand() -> eps.PlacementDemand:
    return eps.PlacementDemand(
        required_capabilities=frozenset({"orchestrator"}),
        quota_class="max20x",
        provider="anthropic",
        allowed_modes=frozenset({eps.PlacementMode.NEW_SESSION_MATERIALIZATION}),
    )


def _candidate(
    worker_id: str,
    account_label: str,
    *,
    observed_at_ms: int,
    capacity_state: CapacityState = CapacityState.AVAILABLE,
) -> eps.PlacementCandidateFact:
    return eps.PlacementCandidateFact(
        worker_id=worker_id,
        provider="anthropic",
        account_label=account_label,
        quota_class="max20x",
        capabilities=frozenset({"orchestrator"}),
        observed_at_ms=observed_at_ms,
        occupancy=eps.OccupancyState.FREE,
        occupancy_source=_source(SourceOwner.RUNTIME_BINDING, f"bind-{worker_id}"),
        capacity_state=capacity_state,
        capacity_source=_source(SourceOwner.CAPACITY, f"capacity-{worker_id}"),
        host_source_closure_proven=True,
        closure_source=_source(SourceOwner.CAPACITY, f"closure-{worker_id}"),
        effect_state=EffectState.NONE,
        mode=eps.PlacementMode.NEW_SESSION_MATERIALIZATION,
        creation_surface_accessible=True,
        session_creation_allowed=True,
    )


def _fables() -> tuple[eps.PlacementCandidateFact, ...]:
    return (
        _candidate("fable-a", "claude20x-d", observed_at_ms=4000),
        _candidate("fable-b", "claude20x-c", observed_at_ms=3000),
        _candidate("fable-c", "claude20x-z", observed_at_ms=2000),
        _candidate("fable-d", "claude20x-a", observed_at_ms=1000),
    )


def _capacity_source(
    *, owner: SourceOwner = SourceOwner.CAPACITY, freshness: Freshness = Freshness.CURRENT
) -> SourceRef:
    return _source(owner, "capacity-fable-pool-generation-7", freshness)


def _base_tie(candidates=None):
    return eps.select_placement(
        responsibility=_responsibility(), demand=_demand(), candidates=candidates or _fables()
    )


def _preference(base=None, order=("fable-c", "fable-a", "fable-d", "fable-b")):
    return epp.make_capacity_preference(
        decision=base or _base_tie(),
        preference_order=order,
        capacity_source=_capacity_source(),
        generation=7,
    )


def test_v1_four_equivalent_fables_still_abstains():
    decision = _base_tie()
    assert decision.state is eps.SelectionState.TIE_ABSTAINED
    assert decision.tied_worker_ids == ("fable-a", "fable-b", "fable-c", "fable-d")
    assert decision.tie_breaker_used is None


def test_v2_without_preference_preserves_honest_abstention():
    decision = epp.select_placement_v2(
        responsibility=_responsibility(), demand=_demand(), candidates=_fables()
    )
    assert decision.state is eps.SelectionState.TIE_ABSTAINED
    assert decision.preference is None
    assert decision.selected is None
    assert decision.to_dict()["selection_is_commitment"] is False


def test_capacity_preference_resolves_four_fable_tie():
    pref = _preference()
    decision = epp.select_placement_v2(
        responsibility=_responsibility(), demand=_demand(), candidates=_fables(), preference=pref
    )
    assert decision.state is eps.SelectionState.SELECTED
    assert decision.selected["worker_id"] == "fable-c"
    assert decision.selected["account_label"] == "claude20x-z"
    assert decision.preference.receipt_id == pref.receipt_id
    assert decision.to_dict()["selection_is_commitment"] is False
    assert epp.validate_placement_selection_v2(decision.to_dict()) == decision.to_dict()


def test_preference_not_account_label_or_timestamp_heuristic():
    # Lexicographically smallest account and oldest observation belong to fable-d;
    # Capacity deliberately prefers fable-c. The resolver follows the receipt only.
    pref = _preference(order=("fable-c", "fable-d", "fable-b", "fable-a"))
    decision = epp.select_placement_v2(
        responsibility=_responsibility(), demand=_demand(), candidates=_fables(), preference=pref
    )
    assert decision.selected["worker_id"] == "fable-c"


def test_candidate_permutation_is_byte_identical():
    base = _base_tie()
    pref = _preference(base=base)
    first = epp.select_placement_v2(
        responsibility=_responsibility(), demand=_demand(), candidates=_fables(), preference=pref
    )
    second = epp.select_placement_v2(
        responsibility=_responsibility(), demand=_demand(), candidates=tuple(reversed(_fables())), preference=pref
    )
    assert json.dumps(first.to_dict(), sort_keys=True) == json.dumps(second.to_dict(), sort_keys=True)


def test_candidate_fact_movement_invalidates_old_receipt():
    pref = _preference()
    changed = list(_fables())
    changed[2] = _candidate("fable-c", "claude20x-z", observed_at_ms=9999)
    with pytest.raises(epp.PlacementPreferenceError, match="does not bind"):
        epp.select_placement_v2(
            responsibility=_responsibility(), demand=_demand(), candidates=tuple(changed), preference=pref
        )


def test_capacity_state_change_that_removes_tie_refuses_old_preference():
    pref = _preference()
    changed = list(_fables())
    changed[0] = _candidate(
        "fable-a", "claude20x-d", observed_at_ms=4000, capacity_state=CapacityState.DEGRADED
    )
    # Three AVAILABLE candidates still tie, but the old four-member receipt no longer covers it.
    with pytest.raises(epp.PlacementPreferenceError):
        epp.select_placement_v2(
            responsibility=_responsibility(), demand=_demand(), candidates=tuple(changed), preference=pref
        )


def test_unique_v1_winner_refuses_preference():
    candidates = (
        _candidate("fable-a", "claude20x-a", observed_at_ms=1),
        _candidate(
            "fable-b", "claude20x-b", observed_at_ms=2, capacity_state=CapacityState.DEGRADED
        ),
    )
    unique = eps.select_placement(
        responsibility=_responsibility(), demand=_demand(), candidates=candidates
    )
    assert unique.state is eps.SelectionState.SELECTED
    with pytest.raises(epp.PlacementPreferenceError, match="only for an exact v1 tie"):
        epp.make_capacity_preference(
            decision=unique,
            preference_order=("fable-a", "fable-b"),
            capacity_source=_capacity_source(),
            generation=1,
        )


def test_preference_requires_current_capacity_source():
    with pytest.raises(epp.PlacementPreferenceError, match="must be current"):
        epp.make_capacity_preference(
            decision=_base_tie(),
            preference_order=("fable-a", "fable-b", "fable-c", "fable-d"),
            capacity_source=_capacity_source(freshness=Freshness.STALE),
            generation=1,
        )


def test_preference_requires_capacity_owner():
    with pytest.raises(epp.PlacementPreferenceError, match="owner must be Capacity"):
        epp.make_capacity_preference(
            decision=_base_tie(),
            preference_order=("fable-a", "fable-b", "fable-c", "fable-d"),
            capacity_source=_capacity_source(owner=SourceOwner.EXECUTIVE_OS),
            generation=1,
        )


@pytest.mark.parametrize(
    "order",
    [
        ("fable-a", "fable-b", "fable-c"),
        ("fable-a", "fable-b", "fable-c", "fable-c"),
        ("fable-a", "fable-b", "fable-c", "fable-d", "fable-e"),
    ],
)
def test_preference_order_must_exactly_cover_tied_set(order):
    with pytest.raises(epp.PlacementPreferenceError):
        epp.make_capacity_preference(
            decision=_base_tie(),
            preference_order=order,
            capacity_source=_capacity_source(),
            generation=1,
        )


def test_content_addressed_preference_detects_tampering():
    wire = _preference().to_dict()
    assert epp.validate_capacity_preference(wire).to_dict() == wire
    tampered = copy.deepcopy(wire)
    tampered["preference_order"] = list(reversed(tampered["preference_order"]))
    with pytest.raises(epp.PlacementPreferenceError, match="receipt_id"):
        epp.validate_capacity_preference(tampered)


def test_preference_responsibility_mismatch_refuses():
    pref = _preference()
    wire = pref.to_dict()
    wire["responsibility_ref"] = "WS:OTHER"
    payload = dict(wire)
    payload.pop("receipt_id")
    wire["receipt_id"] = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    ).hexdigest()
    changed = epp.validate_capacity_preference(wire)
    with pytest.raises(epp.PlacementPreferenceError, match="responsibility does not match"):
        epp.select_placement_v2(
            responsibility=_responsibility(), demand=_demand(), candidates=_fables(), preference=changed
        )


def test_v2_wire_rejects_selected_worker_tampering():
    decision = epp.select_placement_v2(
        responsibility=_responsibility(), demand=_demand(), candidates=_fables(), preference=_preference()
    )
    wire = copy.deepcopy(decision.to_dict())
    wire["selected"]["worker_id"] = "fable-d"
    with pytest.raises(epp.PlacementPreferenceError):
        epp.validate_placement_selection_v2(wire)


def test_v2_wire_rejects_removed_preference_from_resolved_tie():
    decision = epp.select_placement_v2(
        responsibility=_responsibility(), demand=_demand(), candidates=_fables(), preference=_preference()
    )
    wire = copy.deepcopy(decision.to_dict())
    wire["preference"] = None
    with pytest.raises(epp.PlacementPreferenceError):
        epp.validate_placement_selection_v2(wire)


class MovingCandidates(Sequence):
    """Deterministically change candidate facts after the first traversal."""

    def __init__(self, before, after):
        self.before = before
        self.after = after
        self.iterations = 0

    def __len__(self):
        return len(self.before)

    def __getitem__(self, index):
        return self.before[index]

    def __iter__(self):
        self.iterations += 1
        return iter(self.before if self.iterations == 1 else self.after)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("account_label", "unreviewed-account"),
        ("quota_class", "unreviewed-quota"),
        ("provider", "openai-codex"),
        ("observed_at_ms", 9999),
    ],
)
def test_v2_keeps_the_v1_frozen_candidate_snapshot(field, value):
    before = _fables()
    after = list(before)
    after[2] = replace(before[2], **{field: value})
    moving = MovingCandidates(before, tuple(after))

    result = epp.select_placement_v2(
        responsibility=_responsibility(),
        demand=_demand(),
        candidates=moving,
        preference=_preference(),
    )

    wire = result.to_dict()
    assert epp.validate_placement_selection_v2(wire) == wire
    assert wire["selected"][field] == getattr(before[2], field)


def test_unchanged_tuple_snapshot_remains_valid():
    result = epp.select_placement_v2(
        responsibility=_responsibility(),
        demand=_demand(),
        candidates=_fables(),
        preference=_preference(),
    )
    assert epp.validate_placement_selection_v2(result.to_dict()) == result.to_dict()


@pytest.mark.parametrize(
    "candidate_factory",
    [
        lambda: "fable-a",
        lambda: b"fable-a",
        lambda: iter(_fables()),
    ],
)
def test_v2_preserves_v1_candidate_sequence_refusal(candidate_factory):
    with pytest.raises(TypeError, match="candidates must be a sequence"):
        epp.select_placement_v2(
            responsibility=_responsibility(),
            demand=_demand(),
            candidates=candidate_factory(),
        )
