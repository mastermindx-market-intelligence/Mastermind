"""control_plane.executive_placement_selection — CAP-C1 tests.

``executive_placement_selection`` is a pure, closed, deterministic
selection capability over point-in-time secret-safe candidate facts. These
tests prove the FROZEN SPEC properties of the commission
``capacity-c1-deterministic-placement-20260901-claude5-001``:

  1. zero candidates -> NO_ELIGIBLE_CANDIDATE
  2. exactly one eligible -> SELECTED, and ``selected`` passes the Phase-B
     seam contract (``executive_orchestration_principal.
     validate_placement_snapshot``)
  3. multiple unequal (AVAILABLE vs DEGRADED) -> deterministic AVAILABLE winner
  4. exact tie handling (abstain / accepted tie-breaker / unrecognized token)
  5. stale capacity fact -> STALE_EVIDENCE
  6. BOUND_ELSEWHERE-only -> WAITING_CAPACITY
  7. OCCUPIED-only -> WAITING_CAPACITY
  8. capability / quota-class / provider mismatch -> NO_ELIGIBLE_CANDIDATE
  9. closure unproven -> NO_ELIGIBLE_CANDIDATE
 10. pre-submit refusal: responsibility.state != "waiting_capacity"
 11. EFFECT_UNKNOWN handling (sole candidate vs excluded-but-ignored)
 12. permutation invariance
 13. heuristic-mutation immunity (timestamps/account numbering/titles never rank)
 14. secret/leak safety + closed wire keys + no time/datetime/random import
 15. source-correction replay + duplicate-identity reconciliation

Plus: CONTRADICTORY occupancy -> RECONCILIATION_REQUIRED; CAPACITY_UNKNOWN
-> STALE_EVIDENCE; stale responsibility -> STALE_EVIDENCE; aggregate
precedence pinning; wire enum value pinning.
"""
from __future__ import annotations

import itertools
import json
from pathlib import Path

import pytest

from control_plane import executive_orchestration_principal as principal
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

_MODULE_PATH = Path(eps.__file__)


# ---------------------------------------------------------------------------
# fixture builders
# ---------------------------------------------------------------------------

def _source(owner: SourceOwner, ref: str, freshness: Freshness = Freshness.CURRENT, observed_at: str | None = "2026-09-01T00:00:00Z") -> SourceRef:
    return SourceRef(owner=owner, ref=ref, observed_at=observed_at, freshness=freshness)


def _responsibility(
    *,
    ref: str = "WS:CAP-C1",
    state: str | None = "waiting_capacity",
    freshness: Freshness = Freshness.CURRENT,
) -> ResponsibilityFact:
    return ResponsibilityFact(
        responsibility_ref=ref,
        title="Deterministic placement selection",
        accountable_seat=Seat.COO,
        state=state,
        root_job_id=None,
        source=_source(SourceOwner.AGENT_OS, "agentos/workstreams/WS-CAP-C1.md", freshness),
    )


def _demand(
    *,
    required_capabilities: frozenset[str] = frozenset({"cap_a"}),
    quota_class: str = "standard",
    provider: str | None = "acme",
) -> eps.PlacementDemand:
    return eps.PlacementDemand(
        required_capabilities=required_capabilities, quota_class=quota_class, provider=provider,
    )


def _candidate(
    *,
    worker_id: str = "worker-1",
    provider: str = "acme",
    account_label: str = "account1",
    quota_class: str = "standard",
    capabilities: frozenset[str] = frozenset({"cap_a"}),
    observed_at_ms: int = 1000,
    occupancy: eps.OccupancyState = eps.OccupancyState.FREE,
    occupancy_freshness: Freshness = Freshness.CURRENT,
    capacity_state: CapacityState = CapacityState.AVAILABLE,
    capacity_freshness: Freshness = Freshness.CURRENT,
    host_source_closure_proven: bool = True,
    effect_state: EffectState = EffectState.NONE,
) -> eps.PlacementCandidateFact:
    return eps.PlacementCandidateFact(
        worker_id=worker_id,
        provider=provider,
        account_label=account_label,
        quota_class=quota_class,
        capabilities=capabilities,
        observed_at_ms=observed_at_ms,
        occupancy=occupancy,
        occupancy_source=_source(SourceOwner.RUNTIME_BINDING, f"binding/{worker_id}", occupancy_freshness),
        capacity_state=capacity_state,
        capacity_source=_source(SourceOwner.CAPACITY, f"capacity/{worker_id}", capacity_freshness),
        host_source_closure_proven=host_source_closure_proven,
        closure_source=_source(SourceOwner.CAPACITY, f"closure/{worker_id}"),
        effect_state=effect_state,
    )


# ---------------------------------------------------------------------------
# 1 — zero candidates
# ---------------------------------------------------------------------------

def test_zero_candidates_yields_no_eligible_candidate():
    decision = eps.select_placement(responsibility=_responsibility(), demand=_demand(), candidates=())
    assert decision.state is eps.SelectionState.NO_ELIGIBLE_CANDIDATE
    assert decision.selected is None
    assert decision.exclusions == ()
    assert decision.evaluated_candidates == 0


# ---------------------------------------------------------------------------
# 2 — exactly one eligible -> SELECTED, Phase-B seam contract
# ---------------------------------------------------------------------------

def test_single_eligible_candidate_is_selected_and_matches_phase_b_snapshot_seam():
    candidate = _candidate()
    decision = eps.select_placement(
        responsibility=_responsibility(), demand=_demand(), candidates=(candidate,),
    )
    assert decision.state is eps.SelectionState.SELECTED
    assert decision.selected is not None
    # Phase-B seam contract test: the selected snapshot must pass the
    # EXISTING executive_orchestration_principal validator untouched.
    revalidated = principal.validate_placement_snapshot(decision.selected)
    assert revalidated == dict(decision.selected)
    assert decision.selected["worker_id"] == "worker-1"
    assert decision.evaluated_candidates == 1


# ---------------------------------------------------------------------------
# 3 — unequal capacity states -> deterministic AVAILABLE winner
# ---------------------------------------------------------------------------

def test_available_beats_degraded_deterministically():
    available = _candidate(worker_id="worker-a", capacity_state=CapacityState.AVAILABLE)
    degraded = _candidate(worker_id="worker-b", capacity_state=CapacityState.DEGRADED)
    decision = eps.select_placement(
        responsibility=_responsibility(), demand=_demand(), candidates=(degraded, available),
    )
    assert decision.state is eps.SelectionState.SELECTED
    assert decision.selected["worker_id"] == "worker-a"


# ---------------------------------------------------------------------------
# 4 — tie handling
# ---------------------------------------------------------------------------

def test_exact_tie_without_tie_breaker_abstains():
    a = _candidate(worker_id="worker-a")
    b = _candidate(worker_id="worker-b")
    decision = eps.select_placement(responsibility=_responsibility(), demand=_demand(), candidates=(b, a))
    assert decision.state is eps.SelectionState.TIE_ABSTAINED
    assert decision.selected is None
    assert decision.tied_worker_ids == ("worker-a", "worker-b")
    assert decision.tie_breaker_used is None


def test_exact_tie_with_accepted_tie_breaker_picks_lexicographic_min():
    a = _candidate(worker_id="worker-a")
    b = _candidate(worker_id="worker-b")
    decision = eps.select_placement(
        responsibility=_responsibility(), demand=_demand(), candidates=(b, a),
        accepted_tie_breaker="worker_id_lexicographic",
    )
    assert decision.state is eps.SelectionState.SELECTED
    assert decision.selected["worker_id"] == "worker-a"
    assert decision.tie_breaker_used == "worker_id_lexicographic"
    assert decision.tied_worker_ids == ("worker-a", "worker-b")


def test_unrecognized_tie_breaker_token_raises_value_error():
    a = _candidate(worker_id="worker-a")
    b = _candidate(worker_id="worker-b")
    with pytest.raises(ValueError):
        eps.select_placement(
            responsibility=_responsibility(), demand=_demand(), candidates=(a, b),
            accepted_tie_breaker="most_recently_observed",
        )


# ---------------------------------------------------------------------------
# 5 — stale capacity fact -> STALE_EVIDENCE
# ---------------------------------------------------------------------------

def test_stale_capacity_fact_yields_stale_evidence():
    candidate = _candidate(capacity_freshness=Freshness.STALE)
    decision = eps.select_placement(responsibility=_responsibility(), demand=_demand(), candidates=(candidate,))
    assert decision.state is eps.SelectionState.STALE_EVIDENCE
    assert decision.exclusions == (
        eps.CandidateExclusion(worker_id="worker-1", reason=eps.ExclusionReason.STALE_CAPACITY_FACT),
    )


# ---------------------------------------------------------------------------
# 6/7 — occupancy-only exclusions -> WAITING_CAPACITY
# ---------------------------------------------------------------------------

def test_bound_elsewhere_only_yields_waiting_capacity():
    candidate = _candidate(occupancy=eps.OccupancyState.BOUND_ELSEWHERE)
    decision = eps.select_placement(responsibility=_responsibility(), demand=_demand(), candidates=(candidate,))
    assert decision.state is eps.SelectionState.WAITING_CAPACITY
    assert decision.exclusions[0].reason is eps.ExclusionReason.BOUND_ELSEWHERE


def test_occupied_only_yields_waiting_capacity():
    candidate = _candidate(occupancy=eps.OccupancyState.OCCUPIED)
    decision = eps.select_placement(responsibility=_responsibility(), demand=_demand(), candidates=(candidate,))
    assert decision.state is eps.SelectionState.WAITING_CAPACITY
    assert decision.exclusions[0].reason is eps.ExclusionReason.OCCUPIED


# ---------------------------------------------------------------------------
# 8 — mismatch exclusions -> NO_ELIGIBLE_CANDIDATE
# ---------------------------------------------------------------------------

def test_capability_mismatch_yields_no_eligible_candidate():
    candidate = _candidate(capabilities=frozenset({"cap_b"}))
    decision = eps.select_placement(responsibility=_responsibility(), demand=_demand(), candidates=(candidate,))
    assert decision.state is eps.SelectionState.NO_ELIGIBLE_CANDIDATE
    assert decision.exclusions[0].reason is eps.ExclusionReason.CAPABILITY_MISMATCH


def test_quota_class_mismatch_yields_no_eligible_candidate():
    candidate = _candidate(quota_class="premium")
    decision = eps.select_placement(responsibility=_responsibility(), demand=_demand(), candidates=(candidate,))
    assert decision.state is eps.SelectionState.NO_ELIGIBLE_CANDIDATE
    assert decision.exclusions[0].reason is eps.ExclusionReason.QUOTA_CLASS_MISMATCH


def test_provider_mismatch_yields_no_eligible_candidate():
    candidate = _candidate(provider="other")
    decision = eps.select_placement(responsibility=_responsibility(), demand=_demand(), candidates=(candidate,))
    assert decision.state is eps.SelectionState.NO_ELIGIBLE_CANDIDATE
    assert decision.exclusions[0].reason is eps.ExclusionReason.PROVIDER_MISMATCH


# ---------------------------------------------------------------------------
# 9 — closure unproven
# ---------------------------------------------------------------------------

def test_host_source_closure_unproven_yields_no_eligible_candidate():
    candidate = _candidate(host_source_closure_proven=False)
    decision = eps.select_placement(responsibility=_responsibility(), demand=_demand(), candidates=(candidate,))
    assert decision.state is eps.SelectionState.NO_ELIGIBLE_CANDIDATE
    assert decision.exclusions[0].reason is eps.ExclusionReason.HOST_SOURCE_UNPROVEN


# ---------------------------------------------------------------------------
# 10 — pre-submit refusal
# ---------------------------------------------------------------------------

def test_responsibility_state_must_be_waiting_capacity():
    responsibility = _responsibility(state="in_progress")
    with pytest.raises(ValueError):
        eps.select_placement(responsibility=responsibility, demand=_demand(), candidates=())


def test_responsibility_state_none_is_refused():
    responsibility = _responsibility(state=None)
    with pytest.raises(ValueError):
        eps.select_placement(responsibility=responsibility, demand=_demand(), candidates=())


# ---------------------------------------------------------------------------
# 11 — EFFECT_UNKNOWN handling
# ---------------------------------------------------------------------------

def test_effect_unknown_sole_candidate_yields_effect_unknown_state():
    candidate = _candidate(effect_state=EffectState.EFFECT_UNKNOWN)
    decision = eps.select_placement(responsibility=_responsibility(), demand=_demand(), candidates=(candidate,))
    assert decision.state is eps.SelectionState.EFFECT_UNKNOWN
    assert decision.exclusions[0].reason is eps.ExclusionReason.EFFECT_UNKNOWN


def test_effect_unknown_candidate_excluded_but_ignored_when_clean_candidate_exists():
    clean = _candidate(worker_id="worker-clean")
    unknown_effect = _candidate(worker_id="worker-unknown", effect_state=EffectState.EFFECT_UNKNOWN)
    decision = eps.select_placement(
        responsibility=_responsibility(), demand=_demand(), candidates=(unknown_effect, clean),
    )
    assert decision.state is eps.SelectionState.SELECTED
    assert decision.selected["worker_id"] == "worker-clean"
    assert eps.CandidateExclusion(
        worker_id="worker-unknown", reason=eps.ExclusionReason.EFFECT_UNKNOWN
    ) in decision.exclusions


# ---------------------------------------------------------------------------
# 12 — permutation invariance
# ---------------------------------------------------------------------------

def test_permutation_invariance_over_a_mixed_four_candidate_set():
    candidates = [
        _candidate(worker_id="worker-a", capacity_state=CapacityState.AVAILABLE),
        _candidate(worker_id="worker-b", occupancy=eps.OccupancyState.OCCUPIED),
        _candidate(worker_id="worker-c", capabilities=frozenset({"cap_b"})),
        _candidate(worker_id="worker-d", capacity_state=CapacityState.DEGRADED),
    ]
    reference = None
    reference_json = None
    for permutation in itertools.permutations(candidates):
        decision = eps.select_placement(
            responsibility=_responsibility(), demand=_demand(), candidates=permutation,
        )
        payload = json.dumps(decision.to_dict(), sort_keys=True)
        if reference is None:
            reference = decision
            reference_json = payload
        else:
            assert decision == reference
            assert payload == reference_json


# ---------------------------------------------------------------------------
# 13 — heuristic-mutation immunity
# ---------------------------------------------------------------------------

def test_tie_survives_observed_at_ms_and_account_label_and_title_mutation():
    a = _candidate(worker_id="worker-a", account_label="account9", observed_at_ms=999)
    b = _candidate(worker_id="worker-b", account_label="account2", observed_at_ms=1)
    responsibility = _responsibility()
    responsibility_mutated_title = ResponsibilityFact(
        responsibility_ref=responsibility.responsibility_ref,
        title="A totally different, much longer title that says nothing about priority",
        accountable_seat=responsibility.accountable_seat,
        state=responsibility.state,
        root_job_id=responsibility.root_job_id,
        source=responsibility.source,
    )
    decision_1 = eps.select_placement(responsibility=responsibility, demand=_demand(), candidates=(a, b))
    decision_2 = eps.select_placement(
        responsibility=responsibility_mutated_title, demand=_demand(), candidates=(b, a),
    )
    assert decision_1.state is eps.SelectionState.TIE_ABSTAINED
    assert decision_2.state is eps.SelectionState.TIE_ABSTAINED
    assert decision_1.tied_worker_ids == decision_2.tied_worker_ids == ("worker-a", "worker-b")


def test_degraded_never_beats_available_despite_newer_observed_at_ms():
    stale_but_available = _candidate(worker_id="worker-old", capacity_state=CapacityState.AVAILABLE, observed_at_ms=1)
    fresh_but_degraded = _candidate(worker_id="worker-new", capacity_state=CapacityState.DEGRADED, observed_at_ms=999_999)
    decision = eps.select_placement(
        responsibility=_responsibility(), demand=_demand(), candidates=(fresh_but_degraded, stale_but_available),
    )
    assert decision.state is eps.SelectionState.SELECTED
    assert decision.selected["worker_id"] == "worker-old"


# ---------------------------------------------------------------------------
# 14 — secret/leak safety, closed wire keys, no time/datetime/random import
# ---------------------------------------------------------------------------

def test_account_label_rejects_email_shape():
    with pytest.raises(ValueError):
        _candidate(account_label="person@example.com")


def test_account_label_rejects_whitespace():
    with pytest.raises(ValueError):
        _candidate(account_label="account one")


def test_account_label_rejects_path_shape():
    with pytest.raises(ValueError):
        _candidate(account_label="path/to/account")


def test_wire_dict_keys_are_exactly_the_closed_set():
    candidate = _candidate()
    decision = eps.select_placement(responsibility=_responsibility(), demand=_demand(), candidates=(candidate,))
    payload = decision.to_dict()
    assert set(payload) == {
        "schema_version", "responsibility_ref", "state", "selected",
        "tie_breaker_used", "tied_worker_ids", "exclusions", "evaluated_candidates",
    }
    assert set(payload["selected"]) == {
        "schema_version", "worker_id", "quota_class", "provider", "account_label", "observed_at_ms",
    }
    for exclusion in payload["exclusions"]:
        assert set(exclusion) == {"worker_id", "reason"}


def test_no_source_ref_or_env_fields_leak_into_wire_dict():
    candidate = _candidate()
    decision = eps.select_placement(responsibility=_responsibility(), demand=_demand(), candidates=(candidate,))
    payload = decision.to_dict()
    blob = json.dumps(payload)
    assert "binding/" not in blob
    assert "capacity/" not in blob
    assert "closure/" not in blob
    assert "SourceRef" not in blob
    assert "agent_os" not in blob


def test_module_imports_no_clock_or_randomness():
    source = _MODULE_PATH.read_text(encoding="utf-8")
    for banned in ("import time", "import datetime", "import random"):
        assert banned not in source, f"{banned!r} must never appear in {_MODULE_PATH}"


# ---------------------------------------------------------------------------
# 15 — source-correction replay + duplicate identity
# ---------------------------------------------------------------------------

def test_source_correction_flips_the_decision_across_fresh_calls():
    occupied = _candidate(occupancy=eps.OccupancyState.OCCUPIED)
    decision_1 = eps.select_placement(responsibility=_responsibility(), demand=_demand(), candidates=(occupied,))
    assert decision_1.state is eps.SelectionState.WAITING_CAPACITY

    corrected = _candidate(occupancy=eps.OccupancyState.FREE)
    decision_2 = eps.select_placement(responsibility=_responsibility(), demand=_demand(), candidates=(corrected,))
    assert decision_2.state is eps.SelectionState.SELECTED
    assert decision_2.selected["worker_id"] == "worker-1"


def test_duplicate_worker_id_in_one_call_yields_reconciliation_required():
    a = _candidate(worker_id="worker-dup")
    b = _candidate(worker_id="worker-dup")
    decision = eps.select_placement(responsibility=_responsibility(), demand=_demand(), candidates=(a, b))
    assert decision.state is eps.SelectionState.RECONCILIATION_REQUIRED
    assert decision.exclusions == (
        eps.CandidateExclusion(worker_id="worker-dup", reason=eps.ExclusionReason.DUPLICATE_IDENTITY),
    )


# ---------------------------------------------------------------------------
# extra — contradictory occupancy, capacity-unknown, stale responsibility
# ---------------------------------------------------------------------------

def test_contradictory_occupancy_yields_reconciliation_required():
    candidate = _candidate(occupancy=eps.OccupancyState.CONTRADICTORY)
    decision = eps.select_placement(responsibility=_responsibility(), demand=_demand(), candidates=(candidate,))
    assert decision.state is eps.SelectionState.RECONCILIATION_REQUIRED
    assert decision.exclusions[0].reason is eps.ExclusionReason.CONTRADICTORY_BINDING


def test_capacity_unknown_yields_stale_evidence():
    candidate = _candidate(capacity_state=CapacityState.UNKNOWN)
    decision = eps.select_placement(responsibility=_responsibility(), demand=_demand(), candidates=(candidate,))
    assert decision.state is eps.SelectionState.STALE_EVIDENCE
    assert decision.exclusions[0].reason is eps.ExclusionReason.CAPACITY_UNKNOWN


def test_stale_responsibility_yields_stale_evidence():
    responsibility = _responsibility(freshness=Freshness.STALE)
    decision = eps.select_placement(responsibility=responsibility, demand=_demand(), candidates=())
    assert decision.state is eps.SelectionState.STALE_EVIDENCE
    assert decision.exclusions == ()


# ---------------------------------------------------------------------------
# aggregate precedence pinning
# ---------------------------------------------------------------------------

def test_aggregate_precedence_contradictory_beats_everything():
    contradictory = _candidate(worker_id="worker-a", occupancy=eps.OccupancyState.CONTRADICTORY)
    occupied = _candidate(worker_id="worker-b", occupancy=eps.OccupancyState.OCCUPIED)
    effect_unknown = _candidate(worker_id="worker-c", effect_state=EffectState.EFFECT_UNKNOWN)
    decision = eps.select_placement(
        responsibility=_responsibility(), demand=_demand(), candidates=(contradictory, occupied, effect_unknown),
    )
    assert decision.state is eps.SelectionState.RECONCILIATION_REQUIRED


def test_aggregate_precedence_effect_unknown_beats_stale_and_waiting():
    stale = _candidate(worker_id="worker-a", capacity_freshness=Freshness.STALE)
    occupied = _candidate(worker_id="worker-b", occupancy=eps.OccupancyState.OCCUPIED)
    effect_unknown = _candidate(worker_id="worker-c", effect_state=EffectState.EFFECT_UNKNOWN)
    decision = eps.select_placement(
        responsibility=_responsibility(), demand=_demand(), candidates=(stale, occupied, effect_unknown),
    )
    assert decision.state is eps.SelectionState.EFFECT_UNKNOWN


def test_aggregate_precedence_stale_beats_waiting_capacity():
    stale = _candidate(worker_id="worker-a", capacity_freshness=Freshness.STALE)
    occupied = _candidate(worker_id="worker-b", occupancy=eps.OccupancyState.OCCUPIED)
    decision = eps.select_placement(
        responsibility=_responsibility(), demand=_demand(), candidates=(stale, occupied),
    )
    assert decision.state is eps.SelectionState.STALE_EVIDENCE


def test_aggregate_precedence_only_mismatches_yields_no_eligible_candidate():
    mismatch_a = _candidate(worker_id="worker-a", capabilities=frozenset({"cap_b"}))
    mismatch_b = _candidate(worker_id="worker-b", quota_class="premium")
    unproven = _candidate(worker_id="worker-c", host_source_closure_proven=False)
    decision = eps.select_placement(
        responsibility=_responsibility(), demand=_demand(), candidates=(mismatch_a, mismatch_b, unproven),
    )
    assert decision.state is eps.SelectionState.NO_ELIGIBLE_CANDIDATE


# ---------------------------------------------------------------------------
# wire enum values pinned exactly (mutation-hardening)
# ---------------------------------------------------------------------------

def test_occupancy_state_wire_values_pinned():
    assert eps.OccupancyState.FREE.value == "free"
    assert eps.OccupancyState.OCCUPIED.value == "occupied"
    assert eps.OccupancyState.BOUND_ELSEWHERE.value == "bound_elsewhere"
    assert eps.OccupancyState.CONTRADICTORY.value == "contradictory"


def test_selection_state_wire_values_pinned():
    assert eps.SelectionState.SELECTED.value == "selected"
    assert eps.SelectionState.WAITING_CAPACITY.value == "waiting_capacity"
    assert eps.SelectionState.RECONCILIATION_REQUIRED.value == "reconciliation_required"
    assert eps.SelectionState.NO_ELIGIBLE_CANDIDATE.value == "no_eligible_candidate"
    assert eps.SelectionState.STALE_EVIDENCE.value == "stale_evidence"
    assert eps.SelectionState.EFFECT_UNKNOWN.value == "effect_unknown"
    assert eps.SelectionState.TIE_ABSTAINED.value == "tie_abstained"


def test_exclusion_reason_wire_values_pinned():
    assert eps.ExclusionReason.CAPABILITY_MISMATCH.value == "capability_mismatch"
    assert eps.ExclusionReason.QUOTA_CLASS_MISMATCH.value == "quota_class_mismatch"
    assert eps.ExclusionReason.PROVIDER_MISMATCH.value == "provider_mismatch"
    assert eps.ExclusionReason.OCCUPIED.value == "occupied"
    assert eps.ExclusionReason.BOUND_ELSEWHERE.value == "bound_elsewhere"
    assert eps.ExclusionReason.CONTRADICTORY_BINDING.value == "contradictory_binding"
    assert eps.ExclusionReason.STALE_OCCUPANCY_FACT.value == "stale_occupancy_fact"
    assert eps.ExclusionReason.STALE_CAPACITY_FACT.value == "stale_capacity_fact"
    assert eps.ExclusionReason.UNKNOWN_FRESHNESS.value == "unknown_freshness"
    assert eps.ExclusionReason.HOST_SOURCE_UNPROVEN.value == "host_source_unproven"
    assert eps.ExclusionReason.EFFECT_UNKNOWN.value == "effect_unknown"
    assert eps.ExclusionReason.CAPACITY_UNKNOWN.value == "capacity_unknown"
    assert eps.ExclusionReason.DUPLICATE_IDENTITY.value == "duplicate_identity"


def test_schema_pin():
    assert eps.SELECTION_SCHEMA == "mastermind.executive_placement_selection.v1"


# ---------------------------------------------------------------------------
# validate_placement_selection
# ---------------------------------------------------------------------------

def test_validate_placement_selection_round_trips_a_valid_decision():
    candidate = _candidate()
    decision = eps.select_placement(responsibility=_responsibility(), demand=_demand(), candidates=(candidate,))
    payload = decision.to_dict()
    revalidated = eps.validate_placement_selection(payload)
    assert revalidated == payload


def test_validate_placement_selection_rejects_unknown_key():
    candidate = _candidate()
    decision = eps.select_placement(responsibility=_responsibility(), demand=_demand(), candidates=(candidate,))
    payload = dict(decision.to_dict())
    payload["extra"] = "nope"
    with pytest.raises(ValueError):
        eps.validate_placement_selection(payload)


def test_validate_placement_selection_rejects_missing_key():
    candidate = _candidate()
    decision = eps.select_placement(responsibility=_responsibility(), demand=_demand(), candidates=(candidate,))
    payload = dict(decision.to_dict())
    del payload["tie_breaker_used"]
    with pytest.raises(ValueError):
        eps.validate_placement_selection(payload)


def test_validate_placement_selection_rejects_bad_schema_version():
    candidate = _candidate()
    decision = eps.select_placement(responsibility=_responsibility(), demand=_demand(), candidates=(candidate,))
    payload = dict(decision.to_dict())
    payload["schema_version"] = "wrong"
    with pytest.raises(ValueError):
        eps.validate_placement_selection(payload)
