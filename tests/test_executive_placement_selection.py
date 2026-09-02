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
 14. secret/leak safety + closed wire keys + AST-closed import allowlist
 15. source-correction replay + duplicate-identity reconciliation

Plus: CONTRADICTORY occupancy -> RECONCILIATION_REQUIRED; CAPACITY_UNKNOWN
-> STALE_EVIDENCE; stale responsibility -> STALE_EVIDENCE; aggregate
precedence pinning; wire enum value pinning.
"""
from __future__ import annotations

import ast
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


#: Default: a demand that allows either mode — every EXISTING test in this
#: file predates the mode wave and asserts on outcomes that must stay
#: unchanged, so the default must never itself trigger MODE_NOT_ALLOWED.
_BOTH_MODES = frozenset({eps.PlacementMode.EXISTING_SESSION_REUSE, eps.PlacementMode.NEW_SESSION_MATERIALIZATION})


def _demand(
    *,
    required_capabilities: frozenset[str] = frozenset({"cap_a"}),
    quota_class: str = "standard",
    provider: str | None = "acme",
    allowed_modes: frozenset[eps.PlacementMode] = _BOTH_MODES,
) -> eps.PlacementDemand:
    return eps.PlacementDemand(
        required_capabilities=required_capabilities, quota_class=quota_class, provider=provider,
        allowed_modes=allowed_modes,
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
    # Mode wave defaults: a fresh lane whose creation bools are both True —
    # this is what every EXISTING (pre-mode-wave) test candidate implicitly
    # meant, so the default must never itself trigger CREATION_SURFACE_
    # INACCESSIBLE/SESSION_CREATION_DISALLOWED/MODE_NOT_ALLOWED.
    mode: eps.PlacementMode = eps.PlacementMode.NEW_SESSION_MATERIALIZATION,
    creation_surface_accessible: bool | None = True,
    session_creation_allowed: bool | None = True,
) -> eps.PlacementCandidateFact:
    return eps.PlacementCandidateFact(
        worker_id=worker_id,
        provider=provider,
        account_label=account_label,
        quota_class=quota_class,
        capabilities=capabilities,
        observed_at_ms=observed_at_ms,
        occupancy=occupancy,
        occupancy_source=_source(SourceOwner.RUNTIME_BINDING, f"binding-{worker_id}", occupancy_freshness),
        capacity_state=capacity_state,
        capacity_source=_source(SourceOwner.CAPACITY, f"capacity-{worker_id}", capacity_freshness),
        host_source_closure_proven=host_source_closure_proven,
        closure_source=_source(SourceOwner.CAPACITY, f"closure-{worker_id}"),
        effect_state=effect_state,
        mode=mode,
        creation_surface_accessible=creation_surface_accessible,
        session_creation_allowed=session_creation_allowed,
    )


def _reuse_candidate(*, worker_id: str = "worker-1", **kwargs) -> eps.PlacementCandidateFact:
    """An EXISTING_SESSION_REUSE-mode candidate — the closed shape rule
    requires both creation bools to be None for this mode."""
    return _candidate(
        worker_id=worker_id,
        mode=eps.PlacementMode.EXISTING_SESSION_REUSE,
        creation_surface_accessible=None,
        session_creation_allowed=None,
        **kwargs,
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


def test_addendum_a_any_non_null_tie_breaker_is_refused_worker_id_lexicographic():
    """Addendum A discriminator: C1 has NO tie-breaker authority. The
    formerly-recognized "worker_id_lexicographic" token — which used to
    resolve a tie to SELECTED — is now refused exactly like any other
    non-null token, and no decision is produced at all."""
    a = _candidate(worker_id="worker-a")
    b = _candidate(worker_id="worker-b")
    with pytest.raises(ValueError):
        eps.select_placement(
            responsibility=_responsibility(), demand=_demand(), candidates=(b, a),
            accepted_tie_breaker="worker_id_lexicographic",
        )


def test_addendum_a_any_non_null_tie_breaker_is_refused_unrecognized_token():
    a = _candidate(worker_id="worker-a")
    b = _candidate(worker_id="worker-b")
    with pytest.raises(ValueError):
        eps.select_placement(
            responsibility=_responsibility(), demand=_demand(), candidates=(a, b),
            accepted_tie_breaker="most_recently_observed",
        )


def test_addendum_a_tie_breaker_refusal_message_names_no_authority_not_the_token():
    a = _candidate(worker_id="worker-a")
    b = _candidate(worker_id="worker-b")
    with pytest.raises(ValueError) as excinfo:
        eps.select_placement(
            responsibility=_responsibility(), demand=_demand(), candidates=(a, b),
            accepted_tie_breaker="some_arbitrary_caller_supplied_token",
        )
    assert "some_arbitrary_caller_supplied_token" not in str(excinfo.value)
    assert "no tie-breaker authority" in str(excinfo.value)


def test_addendum_a_three_way_tie_still_abstains_with_every_tied_id():
    a = _candidate(worker_id="worker-a")
    b = _candidate(worker_id="worker-b")
    c = _candidate(worker_id="worker-c")
    decision = eps.select_placement(responsibility=_responsibility(), demand=_demand(), candidates=(c, a, b))
    assert decision.state is eps.SelectionState.TIE_ABSTAINED
    assert decision.selected is None
    assert decision.tied_worker_ids == ("worker-a", "worker-b", "worker-c")
    assert decision.tie_breaker_used is None


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


#: Provenance wave: an evidence row is now the decision's canonical INPUT
#: PROJECTION for one candidate, so it carries every PlacementCandidateFact
#: field — without provider/account_label/quota_class/capabilities/
#: observed_at_ms the decision cannot be recomputed from its own wire form.
_EVIDENCE_ROW_WIRE_KEYS = {
    "worker_id", "provider", "account_label", "quota_class", "capabilities",
    "observed_at_ms",
    "mode", "occupancy", "occupancy_source", "capacity_state",
    "capacity_source", "host_source_closure_proven", "closure_source",
    "effect_state", "creation_surface_accessible", "session_creation_allowed",
}
_DEMAND_WIRE_KEYS = {"required_capabilities", "quota_class", "provider", "allowed_modes"}
_SOURCE_REF_WIRE_KEYS = {"owner", "ref", "observed_at", "freshness"}


def test_wire_dict_keys_are_exactly_the_closed_set():
    candidate = _candidate()
    decision = eps.select_placement(responsibility=_responsibility(), demand=_demand(), candidates=(candidate,))
    payload = decision.to_dict()
    assert set(payload) == {
        "schema_version", "responsibility_ref", "responsibility_freshness",
        "demand", "state", "selected",
        "tie_breaker_used", "tied_worker_ids", "exclusions", "evaluated_candidates",
        "selection_is_commitment", "evidence", "selected_mode",
    }
    assert set(payload["demand"]) == _DEMAND_WIRE_KEYS
    assert payload["responsibility_freshness"] == "current"
    assert payload["selection_is_commitment"] is False
    assert payload["selected_mode"] == "new_session_materialization"
    assert set(payload["selected"]) == {
        "schema_version", "worker_id", "quota_class", "provider", "account_label", "observed_at_ms",
    }
    for exclusion in payload["exclusions"]:
        assert set(exclusion) == {"worker_id", "reason"}
    assert len(payload["evidence"]) == payload["evaluated_candidates"] == 1
    for row in payload["evidence"]:
        assert set(row) == _EVIDENCE_ROW_WIRE_KEYS
        assert set(row["occupancy_source"]) == _SOURCE_REF_WIRE_KEYS
        assert set(row["capacity_source"]) == _SOURCE_REF_WIRE_KEYS
        assert set(row["closure_source"]) == _SOURCE_REF_WIRE_KEYS
        assert row["mode"] == "new_session_materialization"
        assert row["creation_surface_accessible"] is True
        assert row["session_creation_allowed"] is True


def test_no_env_fields_or_agent_os_leak_into_wire_dict():
    """Addendum B deliberately puts source refs (owner/ref/observed_at/
    freshness) on the wire via ``evidence`` — that IS the consumer-evidence
    feature, so the candidate's own ``binding-``/``capacity-``/``closure-``
    refs are now EXPECTED in the blob. What must still never appear: the
    Python class name (an implementation detail, not a wire value) and any
    text this module has no channel to have produced at all, like the
    responsibility source's ``agent_os`` owner (a source this decision
    never carries — only candidate-side sources ever reach ``evidence``)."""
    candidate = _candidate()
    decision = eps.select_placement(responsibility=_responsibility(), demand=_demand(), candidates=(candidate,))
    payload = decision.to_dict()
    blob = json.dumps(payload)
    assert "SourceRef" not in blob
    assert "agent_os" not in blob
    # And the evidence refs ARE present — the positive half of the same
    # claim, so this test cannot silently pass on an empty evidence list.
    assert "binding-worker-1" in blob
    assert "capacity-worker-1" in blob
    assert "closure-worker-1" in blob


#: Reviewer n-10: the module's COMPLETE import set, closed. A literal grep
#: for three exact spellings ("import time"/"import datetime"/"import
#: random") only catches those three exact forms — `import time as t`,
#: `from time import monotonic`, `import os`, `import subprocess`, or any
#: other clock/randomness/I/O import would sail through unnoticed. This
#: allowlist is exact: any import this module does not already declare
#: fails the test below, whether or not it is one of the three originally
#: named culprits.
_ALLOWED_MODULE_IMPORTS: frozenset[tuple[str | None, str]] = frozenset({
    ("__future__", "annotations"),
    (None, "dataclasses"),
    (None, "enum"),
    ("collections.abc", "Mapping"),
    ("collections.abc", "Sequence"),
    ("typing", "Any"),
    ("control_plane.executive_orchestration_principal", "OrchestrationPrincipalError"),
    ("control_plane.executive_orchestration_principal", "build_placement_snapshot"),
    ("control_plane.executive_orchestration_principal", "validate_placement_snapshot"),
    ("control_plane.executive_steward", "CapacityState"),
    ("control_plane.executive_steward", "EffectState"),
    ("control_plane.executive_steward", "Freshness"),
    ("control_plane.executive_steward", "ResponsibilityFact"),
    # Provenance wave: rebuilding the responsibility gate fact for the
    # recomputation needs Seat. Pure enum from the same already-allowed
    # module — no clock, randomness, filesystem or network reaches here.
    ("control_plane.executive_steward", "Seat"),
    ("control_plane.executive_steward", "SourceOwner"),
    ("control_plane.executive_steward", "SourceRef"),
})


def test_module_import_set_is_exactly_the_closed_allowlist():
    """AST-based purity guard (reviewer n-10, replaces a three-literal grep).

    Parses the module and walks its COMPLETE syntax tree (``ast.walk``, not
    just module-level statements — a purity guard must also catch an import
    smuggled inside a function body) collecting every ``import``/``from ...
    import`` name as ``(module_or_None, imported_name)``. The result must
    equal :data:`_ALLOWED_MODULE_IMPORTS` exactly — no more, no fewer —
    which is what makes this a real purity gate rather than a denylist of
    three specific spellings: any future clock, randomness, filesystem, or
    network import (``time``, ``datetime``, ``random``, ``os``,
    ``subprocess``, ``pathlib``, ``requests``, an aliased or ``from``-style
    import of any of those, ...) fails it, not just the three originally
    named.
    """
    source = _MODULE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(_MODULE_PATH))

    found: set[tuple[str | None, str]] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.add((None, alias.name))
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                found.add((node.module, alias.name))

    assert found == set(_ALLOWED_MODULE_IMPORTS)


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


# ---------------------------------------------------------------------------
# repair wave — M-3: validate_placement_selection cross-field invariants
# ---------------------------------------------------------------------------

def test_validate_placement_selection_rejects_selected_present_when_state_not_selected():
    candidate = _candidate()
    decision = eps.select_placement(responsibility=_responsibility(), demand=_demand(), candidates=(candidate,))
    payload = dict(decision.to_dict())
    payload["state"] = "waiting_capacity"  # selected stays non-None -> now inconsistent
    with pytest.raises(ValueError):
        eps.validate_placement_selection(payload)


def test_validate_placement_selection_rejects_selected_state_with_no_selected_payload():
    candidate = _candidate()
    decision = eps.select_placement(responsibility=_responsibility(), demand=_demand(), candidates=(candidate,))
    payload = dict(decision.to_dict())
    payload["selected"] = None  # state stays "selected" -> now inconsistent
    with pytest.raises(ValueError):
        eps.validate_placement_selection(payload)


def test_validate_placement_selection_rejects_any_non_null_tie_breaker_used():
    """Addendum A: tie_breaker_used is RESERVED and must be null — ANY
    non-null value is refused, not just an unrecognized token (there is no
    longer a "recognized" set at all)."""
    candidate = _candidate()
    decision = eps.select_placement(responsibility=_responsibility(), demand=_demand(), candidates=(candidate,))
    assert decision.state is eps.SelectionState.SELECTED
    for token in ("worker_id_lexicographic", "most_recently_observed", ""):
        payload = dict(decision.to_dict())
        payload["tie_breaker_used"] = token
        with pytest.raises(ValueError):
            eps.validate_placement_selection(payload)


def test_validate_placement_selection_rejects_tie_breaker_used_without_two_tied_ids():
    candidate = _candidate()
    decision = eps.select_placement(responsibility=_responsibility(), demand=_demand(), candidates=(candidate,))
    payload = dict(decision.to_dict())
    payload["tie_breaker_used"] = "worker_id_lexicographic"  # state selected, tied_worker_ids still []
    with pytest.raises(ValueError):
        eps.validate_placement_selection(payload)


def test_validate_placement_selection_rejects_tie_breaker_used_on_a_non_selected_state():
    a, b = _candidate(worker_id="worker-a"), _candidate(worker_id="worker-b")
    decision = eps.select_placement(responsibility=_responsibility(), demand=_demand(), candidates=(a, b))
    assert decision.state is eps.SelectionState.TIE_ABSTAINED
    payload = dict(decision.to_dict())
    payload["tie_breaker_used"] = "worker_id_lexicographic"
    with pytest.raises(ValueError):
        eps.validate_placement_selection(payload)


def test_validate_placement_selection_rejects_tie_abstained_with_fewer_than_two_tied_ids():
    a, b = _candidate(worker_id="worker-a"), _candidate(worker_id="worker-b")
    decision = eps.select_placement(responsibility=_responsibility(), demand=_demand(), candidates=(a, b))
    payload = dict(decision.to_dict())
    payload["tied_worker_ids"] = ["worker-a"]
    with pytest.raises(ValueError):
        eps.validate_placement_selection(payload)


def test_validate_placement_selection_rejects_non_selected_non_tie_state_with_tied_ids():
    candidate = _candidate(occupancy=eps.OccupancyState.OCCUPIED)
    decision = eps.select_placement(responsibility=_responsibility(), demand=_demand(), candidates=(candidate,))
    assert decision.state is eps.SelectionState.WAITING_CAPACITY
    payload = dict(decision.to_dict())
    payload["tied_worker_ids"] = ["worker-1", "worker-2"]
    with pytest.raises(ValueError):
        eps.validate_placement_selection(payload)


def test_validate_placement_selection_rejects_evaluated_candidates_below_exclusion_count():
    candidate = _candidate(occupancy=eps.OccupancyState.OCCUPIED)
    decision = eps.select_placement(responsibility=_responsibility(), demand=_demand(), candidates=(candidate,))
    payload = dict(decision.to_dict())
    assert len(payload["exclusions"]) == 1
    payload["evaluated_candidates"] = 0
    with pytest.raises(ValueError):
        eps.validate_placement_selection(payload)


def test_validate_placement_selection_rejects_evaluated_candidates_below_tied_count():
    a, b = _candidate(worker_id="worker-a"), _candidate(worker_id="worker-b")
    decision = eps.select_placement(responsibility=_responsibility(), demand=_demand(), candidates=(a, b))
    payload = dict(decision.to_dict())
    assert len(payload["tied_worker_ids"]) == 2
    payload["evaluated_candidates"] = 1
    with pytest.raises(ValueError):
        eps.validate_placement_selection(payload)


def test_validate_placement_selection_rejects_unsorted_tied_worker_ids():
    a, b = _candidate(worker_id="worker-a"), _candidate(worker_id="worker-b")
    decision = eps.select_placement(responsibility=_responsibility(), demand=_demand(), candidates=(a, b))
    payload = dict(decision.to_dict())
    payload["tied_worker_ids"] = list(reversed(payload["tied_worker_ids"]))
    with pytest.raises(ValueError):
        eps.validate_placement_selection(payload)


def test_validate_placement_selection_rejects_unsorted_exclusions():
    a = _candidate(worker_id="worker-a", occupancy=eps.OccupancyState.OCCUPIED)
    b = _candidate(worker_id="worker-b", occupancy=eps.OccupancyState.OCCUPIED)
    decision = eps.select_placement(responsibility=_responsibility(), demand=_demand(), candidates=(a, b))
    payload = dict(decision.to_dict())
    assert len(payload["exclusions"]) == 2
    payload["exclusions"] = list(reversed(payload["exclusions"]))
    with pytest.raises(ValueError):
        eps.validate_placement_selection(payload)


# ---------------------------------------------------------------------------
# addendum B — validate_placement_selection: selection_is_commitment + evidence
# ---------------------------------------------------------------------------

def test_validate_placement_selection_rejects_missing_selection_is_commitment():
    candidate = _candidate()
    decision = eps.select_placement(responsibility=_responsibility(), demand=_demand(), candidates=(candidate,))
    payload = dict(decision.to_dict())
    del payload["selection_is_commitment"]
    with pytest.raises(ValueError):
        eps.validate_placement_selection(payload)


def test_validate_placement_selection_rejects_true_selection_is_commitment():
    candidate = _candidate()
    decision = eps.select_placement(responsibility=_responsibility(), demand=_demand(), candidates=(candidate,))
    payload = dict(decision.to_dict())
    payload["selection_is_commitment"] = True
    with pytest.raises(ValueError):
        eps.validate_placement_selection(payload)


def test_validate_placement_selection_rejects_evidence_row_missing_a_key():
    candidate = _candidate()
    decision = eps.select_placement(responsibility=_responsibility(), demand=_demand(), candidates=(candidate,))
    payload = dict(decision.to_dict())
    assert len(payload["evidence"]) == 1
    payload["evidence"] = [dict(payload["evidence"][0])]
    del payload["evidence"][0]["effect_state"]
    with pytest.raises(ValueError):
        eps.validate_placement_selection(payload)


def test_validate_placement_selection_rejects_evidence_row_extra_key():
    candidate = _candidate()
    decision = eps.select_placement(responsibility=_responsibility(), demand=_demand(), candidates=(candidate,))
    payload = dict(decision.to_dict())
    payload["evidence"] = [dict(payload["evidence"][0])]
    payload["evidence"][0]["extra"] = "nope"
    with pytest.raises(ValueError):
        eps.validate_placement_selection(payload)


def test_validate_placement_selection_rejects_evidence_row_bad_enum_value():
    candidate = _candidate()
    decision = eps.select_placement(responsibility=_responsibility(), demand=_demand(), candidates=(candidate,))
    payload = dict(decision.to_dict())
    payload["evidence"] = [dict(payload["evidence"][0])]
    payload["evidence"][0]["occupancy"] = "not_a_real_occupancy_state"
    with pytest.raises(ValueError):
        eps.validate_placement_selection(payload)


def test_validate_placement_selection_rejects_evidence_row_at_carrying_ref():
    candidate = _candidate()
    decision = eps.select_placement(responsibility=_responsibility(), demand=_demand(), candidates=(candidate,))
    payload = dict(decision.to_dict())
    payload["evidence"] = [dict(payload["evidence"][0])]
    payload["evidence"][0] = dict(payload["evidence"][0])
    payload["evidence"][0]["occupancy_source"] = dict(payload["evidence"][0]["occupancy_source"])
    payload["evidence"][0]["occupancy_source"]["ref"] = "binding@leaked"
    with pytest.raises(ValueError):
        eps.validate_placement_selection(payload)


def test_validate_placement_selection_rejects_evidence_source_ref_missing_key():
    candidate = _candidate()
    decision = eps.select_placement(responsibility=_responsibility(), demand=_demand(), candidates=(candidate,))
    payload = dict(decision.to_dict())
    payload["evidence"] = [dict(payload["evidence"][0])]
    payload["evidence"][0]["capacity_source"] = dict(payload["evidence"][0]["capacity_source"])
    del payload["evidence"][0]["capacity_source"]["freshness"]
    with pytest.raises(ValueError):
        eps.validate_placement_selection(payload)


def test_validate_placement_selection_rejects_evidence_host_source_closure_proven_non_bool():
    candidate = _candidate()
    decision = eps.select_placement(responsibility=_responsibility(), demand=_demand(), candidates=(candidate,))
    payload = dict(decision.to_dict())
    payload["evidence"] = [dict(payload["evidence"][0])]
    payload["evidence"][0]["host_source_closure_proven"] = "true"
    with pytest.raises(TypeError):
        eps.validate_placement_selection(payload)


def test_validate_placement_selection_rejects_unsorted_evidence():
    a = _candidate(worker_id="worker-a", occupancy=eps.OccupancyState.OCCUPIED)
    b = _candidate(worker_id="worker-b", occupancy=eps.OccupancyState.OCCUPIED)
    decision = eps.select_placement(responsibility=_responsibility(), demand=_demand(), candidates=(a, b))
    payload = dict(decision.to_dict())
    assert len(payload["evidence"]) == 2
    payload["evidence"] = list(reversed(payload["evidence"]))
    with pytest.raises(ValueError):
        eps.validate_placement_selection(payload)


def test_validate_placement_selection_rejects_evaluated_candidates_not_equal_to_evidence_count():
    candidate = _candidate()
    decision = eps.select_placement(responsibility=_responsibility(), demand=_demand(), candidates=(candidate,))
    payload = dict(decision.to_dict())
    assert payload["evaluated_candidates"] == len(payload["evidence"]) == 1
    payload["evaluated_candidates"] = 2
    with pytest.raises(ValueError):
        eps.validate_placement_selection(payload)


def test_validate_placement_selection_error_messages_never_interpolate_the_value():
    candidate = _candidate()
    decision = eps.select_placement(responsibility=_responsibility(), demand=_demand(), candidates=(candidate,))
    payload = dict(decision.to_dict())
    payload["state"] = "a_totally_bogus_state_value_xyz"
    with pytest.raises(ValueError) as excinfo:
        eps.validate_placement_selection(payload)
    assert "a_totally_bogus_state_value_xyz" not in str(excinfo.value)


# ---------------------------------------------------------------------------
# repair wave — M-1/M-2: eager construction-time Phase-B snapshot refusal
# ---------------------------------------------------------------------------

def test_construction_refuses_worker_id_that_fails_the_phase_b_snapshot_regex():
    # Passes this module's own token check (no whitespace/@//) but "!" is
    # outside executive_orchestration_principal._ID_RE.
    with pytest.raises(ValueError):
        _candidate(worker_id="worker!1")


def test_construction_refuses_provider_that_fails_the_phase_b_snapshot_regex():
    # _PROVIDER_RE is lowercase-only; this module's own token check does not
    # enforce case on its own.
    with pytest.raises(ValueError):
        _candidate(provider="ACME")


def test_construction_refuses_account_label_that_fails_the_phase_b_snapshot_regex():
    # _ACCOUNT_RE is lowercase-only.
    with pytest.raises(ValueError):
        _candidate(account_label="Account1")


def test_construction_refuses_quota_class_that_fails_the_phase_b_snapshot_regex():
    with pytest.raises(ValueError):
        _candidate(quota_class="standard!")


def test_construction_error_never_leaks_the_offending_value():
    with pytest.raises(ValueError) as excinfo:
        _candidate(provider="ACME")
    assert "ACME" not in str(excinfo.value)


def test_worker_id_rejects_at_symbol():
    with pytest.raises(ValueError):
        _candidate(worker_id="worker@1")


def test_provider_rejects_slash():
    with pytest.raises(ValueError):
        _candidate(provider="acme/inc")


def test_quota_class_rejects_at_symbol():
    with pytest.raises(ValueError):
        _candidate(quota_class="standard@tier")


def test_capability_token_rejects_slash():
    with pytest.raises(ValueError):
        _candidate(capabilities=frozenset({"cap/a"}))


def test_tie_breaker_used_field_is_reserved_and_rejects_any_non_none_value():
    """Addendum A: tie_breaker_used is RESERVED — construction refuses ANY
    non-None value, not merely a secret-shaped one (there is no longer a
    "recognized" token this field could legitimately hold)."""
    with pytest.raises(ValueError):
        eps.PlacementSelectionDecision(
            responsibility_ref="WS:CAP-C1",
            responsibility_freshness=Freshness.CURRENT,
            demand=_demand(),
            state=eps.SelectionState.SELECTED,
            selected=None,
            selected_mode=None,
            tie_breaker_used="worker_id@lexicographic",
            tied_worker_ids=(),
            exclusions=(),
            evaluated_candidates=0,
            evidence=(),
        )
    with pytest.raises(ValueError):
        eps.PlacementSelectionDecision(
            responsibility_ref="WS:CAP-C1",
            responsibility_freshness=Freshness.CURRENT,
            demand=_demand(),
            state=eps.SelectionState.TIE_ABSTAINED,
            selected=None,
            selected_mode=None,
            tie_breaker_used="worker_id_lexicographic",
            tied_worker_ids=("worker-a", "worker-b"),
            exclusions=(),
            evaluated_candidates=2,
            evidence=(),
        )


def test_demand_required_capability_rejects_at_symbol():
    with pytest.raises(ValueError):
        eps.PlacementDemand(
            required_capabilities=frozenset({"cap@a"}), quota_class="standard", provider="acme",
            allowed_modes=_BOTH_MODES,
        )


def test_demand_provider_rejects_slash():
    with pytest.raises(ValueError):
        eps.PlacementDemand(
            required_capabilities=frozenset(), quota_class="standard", provider="acme/inc",
            allowed_modes=_BOTH_MODES,
        )


def test_demand_allowed_modes_must_be_non_empty():
    with pytest.raises(ValueError):
        eps.PlacementDemand(
            required_capabilities=frozenset(), quota_class="standard", provider="acme",
            allowed_modes=frozenset(),
        )


def test_demand_allowed_modes_members_are_type_checked():
    with pytest.raises(TypeError):
        eps.PlacementDemand(
            required_capabilities=frozenset(), quota_class="standard", provider="acme",
            allowed_modes=frozenset({"existing_session_reuse"}),  # plain str, not PlacementMode
        )


# ---------------------------------------------------------------------------
# repair wave — M-4/n-9: gate-order refinement, mutant killers
# ---------------------------------------------------------------------------

def test_contradictory_candidate_excluded_but_clean_sibling_still_selected():
    """Ruling m-6, pinned: CONTRADICTORY is a PER-CANDIDATE exclusion — it
    never poisons a clean sibling's eligibility."""
    contradictory = _candidate(worker_id="worker-bad", occupancy=eps.OccupancyState.CONTRADICTORY)
    clean = _candidate(worker_id="worker-clean")
    decision = eps.select_placement(
        responsibility=_responsibility(), demand=_demand(), candidates=(contradictory, clean),
    )
    assert decision.state is eps.SelectionState.SELECTED
    assert decision.selected["worker_id"] == "worker-clean"
    assert eps.CandidateExclusion(
        worker_id="worker-bad", reason=eps.ExclusionReason.CONTRADICTORY_BINDING
    ) in decision.exclusions


def test_gate_order_contradictory_beats_effect_unknown_on_one_candidate():
    candidate = _candidate(occupancy=eps.OccupancyState.CONTRADICTORY, effect_state=EffectState.EFFECT_UNKNOWN)
    decision = eps.select_placement(responsibility=_responsibility(), demand=_demand(), candidates=(candidate,))
    assert decision.exclusions == (
        eps.CandidateExclusion(worker_id="worker-1", reason=eps.ExclusionReason.CONTRADICTORY_BINDING),
    )


def test_gate_order_effect_unknown_beats_stale_occupancy_fact_on_one_candidate():
    candidate = _candidate(effect_state=EffectState.EFFECT_UNKNOWN, occupancy_freshness=Freshness.STALE)
    decision = eps.select_placement(responsibility=_responsibility(), demand=_demand(), candidates=(candidate,))
    assert decision.exclusions == (
        eps.CandidateExclusion(worker_id="worker-1", reason=eps.ExclusionReason.EFFECT_UNKNOWN),
    )


def test_gate_order_stale_capacity_fact_beats_occupied_on_one_candidate():
    candidate = _candidate(capacity_freshness=Freshness.STALE, occupancy=eps.OccupancyState.OCCUPIED)
    decision = eps.select_placement(responsibility=_responsibility(), demand=_demand(), candidates=(candidate,))
    assert decision.exclusions == (
        eps.CandidateExclusion(worker_id="worker-1", reason=eps.ExclusionReason.STALE_CAPACITY_FACT),
    )


def test_gate_order_occupied_beats_closure_unproven_on_one_candidate():
    candidate = _candidate(occupancy=eps.OccupancyState.OCCUPIED, host_source_closure_proven=False)
    decision = eps.select_placement(responsibility=_responsibility(), demand=_demand(), candidates=(candidate,))
    assert decision.exclusions == (
        eps.CandidateExclusion(worker_id="worker-1", reason=eps.ExclusionReason.OCCUPIED),
    )


def test_gate_order_closure_unproven_beats_capability_mismatch_on_one_candidate():
    candidate = _candidate(host_source_closure_proven=False, capabilities=frozenset({"cap_b"}))
    decision = eps.select_placement(responsibility=_responsibility(), demand=_demand(), candidates=(candidate,))
    assert decision.exclusions == (
        eps.CandidateExclusion(worker_id="worker-1", reason=eps.ExclusionReason.HOST_SOURCE_UNPROVEN),
    )


def _evidence_row(
    worker_id: str,
    *,
    mode: eps.PlacementMode = eps.PlacementMode.NEW_SESSION_MATERIALIZATION,
    creation_surface_accessible: bool | None = True,
    session_creation_allowed: bool | None = True,
) -> eps.CandidateEvidence:
    return eps.CandidateEvidence(
        worker_id=worker_id,
        provider="acme",
        account_label="account1",
        quota_class="standard",
        capabilities=frozenset({"cap_a"}),
        observed_at_ms=1000,
        mode=mode,
        occupancy=eps.OccupancyState.FREE,
        occupancy_source=_source(SourceOwner.RUNTIME_BINDING, f"binding-{worker_id}"),
        capacity_state=CapacityState.AVAILABLE,
        capacity_source=_source(SourceOwner.CAPACITY, f"capacity-{worker_id}"),
        host_source_closure_proven=True,
        closure_source=_source(SourceOwner.CAPACITY, f"closure-{worker_id}"),
        effect_state=EffectState.NONE,
        creation_surface_accessible=creation_surface_accessible,
        session_creation_allowed=session_creation_allowed,
    )


def test_to_dict_sorts_deliberately_unsorted_exclusions_tied_worker_ids_and_evidence():
    decision = eps.PlacementSelectionDecision(
        responsibility_ref="WS:CAP-C1",
        responsibility_freshness=Freshness.CURRENT,
        demand=_demand(),
        state=eps.SelectionState.TIE_ABSTAINED,
        selected=None,
        selected_mode=None,
        tie_breaker_used=None,
        tied_worker_ids=("worker-z", "worker-a"),
        exclusions=(
            eps.CandidateExclusion(worker_id="worker-z", reason=eps.ExclusionReason.OCCUPIED),
            eps.CandidateExclusion(worker_id="worker-a", reason=eps.ExclusionReason.CAPABILITY_MISMATCH),
        ),
        evaluated_candidates=4,
        evidence=(
            _evidence_row("worker-z"),
            _evidence_row("worker-c"),
            _evidence_row("worker-a"),
            _evidence_row("worker-b"),
        ),
    )
    payload = decision.to_dict()
    assert payload["tied_worker_ids"] == ["worker-a", "worker-z"]
    assert payload["exclusions"] == [
        {"worker_id": "worker-a", "reason": "capability_mismatch"},
        {"worker_id": "worker-z", "reason": "occupied"},
    ]
    assert [row["worker_id"] for row in payload["evidence"]] == [
        "worker-a", "worker-b", "worker-c", "worker-z",
    ]


def test_decision_construction_refuses_evidence_count_mismatching_evaluated_candidates():
    with pytest.raises(ValueError):
        eps.PlacementSelectionDecision(
            responsibility_ref="WS:CAP-C1",
            responsibility_freshness=Freshness.CURRENT,
            demand=_demand(),
            state=eps.SelectionState.NO_ELIGIBLE_CANDIDATE,
            selected=None,
            selected_mode=None,
            tie_breaker_used=None,
            tied_worker_ids=(),
            exclusions=(),
            evaluated_candidates=2,
            evidence=(_evidence_row("worker-a"),),
        )


def test_non_adjacent_duplicate_worker_ids_yield_reconciliation_required():
    dup1 = _candidate(worker_id="worker-dup")
    other = _candidate(worker_id="worker-other")
    dup2 = _candidate(worker_id="worker-dup")
    decision = eps.select_placement(
        responsibility=_responsibility(), demand=_demand(), candidates=(dup1, other, dup2),
    )
    assert decision.state is eps.SelectionState.RECONCILIATION_REQUIRED
    assert decision.exclusions == (
        eps.CandidateExclusion(worker_id="worker-dup", reason=eps.ExclusionReason.DUPLICATE_IDENTITY),
    )


def test_capacity_rank_map_is_total_over_capacity_state():
    """Pins reviewer n-11's import-time assertion: every CapacityState
    member is ranked, or is exactly CapacityState.UNKNOWN."""
    ranked_or_unknown = set(eps._CAPACITY_RANK) | {CapacityState.UNKNOWN}
    assert ranked_or_unknown == set(CapacityState)


# ---------------------------------------------------------------------------
# MODE WAVE — Sol correction: existing-session reuse vs new-session
# materialization. Eight named discriminators (commission D.1-D.8).
# ---------------------------------------------------------------------------

def test_mode_discriminator_1_occupied_reuse_excluded_fresh_lane_selected():
    reuse = _reuse_candidate(worker_id="worker-a", account_label="account1", occupancy=eps.OccupancyState.OCCUPIED)
    fresh = _candidate(worker_id="worker-b", account_label="account1")
    decision = eps.select_placement(responsibility=_responsibility(), demand=_demand(), candidates=(reuse, fresh))
    assert decision.state is eps.SelectionState.SELECTED
    assert decision.selected["worker_id"] == "worker-b"
    assert decision.selected_mode is eps.PlacementMode.NEW_SESSION_MATERIALIZATION
    assert eps.CandidateExclusion(worker_id="worker-a", reason=eps.ExclusionReason.OCCUPIED) in decision.exclusions


def test_mode_discriminator_2_reuse_only_demand_excludes_fresh_lane_mode_not_allowed():
    reuse = _reuse_candidate(worker_id="worker-a", account_label="account1", occupancy=eps.OccupancyState.OCCUPIED)
    fresh = _candidate(worker_id="worker-b", account_label="account1")
    demand = _demand(allowed_modes=frozenset({eps.PlacementMode.EXISTING_SESSION_REUSE}))
    decision = eps.select_placement(responsibility=_responsibility(), demand=demand, candidates=(reuse, fresh))
    # The occupied reuse candidate dominates the aggregate fallthrough over
    # the fresh lane's MODE_NOT_ALLOWED (which is not in any aggregate
    # bucket — it falls through, same as HOST_SOURCE_UNPROVEN/mismatches).
    assert decision.state is eps.SelectionState.WAITING_CAPACITY
    assert eps.CandidateExclusion(worker_id="worker-a", reason=eps.ExclusionReason.OCCUPIED) in decision.exclusions
    assert eps.CandidateExclusion(
        worker_id="worker-b", reason=eps.ExclusionReason.MODE_NOT_ALLOWED
    ) in decision.exclusions


def test_mode_discriminator_3_fresh_lane_capacity_unknown():
    candidate = _candidate(capacity_state=CapacityState.UNKNOWN)
    decision = eps.select_placement(responsibility=_responsibility(), demand=_demand(), candidates=(candidate,))
    assert decision.exclusions == (
        eps.CandidateExclusion(worker_id="worker-1", reason=eps.ExclusionReason.CAPACITY_UNKNOWN),
    )


def test_mode_discriminator_3_fresh_lane_capacity_source_stale():
    candidate = _candidate(capacity_freshness=Freshness.STALE)
    decision = eps.select_placement(responsibility=_responsibility(), demand=_demand(), candidates=(candidate,))
    assert decision.exclusions == (
        eps.CandidateExclusion(worker_id="worker-1", reason=eps.ExclusionReason.STALE_CAPACITY_FACT),
    )


def test_mode_discriminator_3_fresh_lane_creation_surface_inaccessible():
    candidate = _candidate(creation_surface_accessible=False)
    decision = eps.select_placement(responsibility=_responsibility(), demand=_demand(), candidates=(candidate,))
    assert decision.exclusions == (
        eps.CandidateExclusion(worker_id="worker-1", reason=eps.ExclusionReason.CREATION_SURFACE_INACCESSIBLE),
    )


def test_mode_discriminator_3_fresh_lane_session_creation_disallowed():
    candidate = _candidate(session_creation_allowed=False)
    decision = eps.select_placement(responsibility=_responsibility(), demand=_demand(), candidates=(candidate,))
    assert decision.exclusions == (
        eps.CandidateExclusion(worker_id="worker-1", reason=eps.ExclusionReason.SESSION_CREATION_DISALLOWED),
    )


def test_mode_discriminator_3_fresh_lane_closure_unproven():
    candidate = _candidate(host_source_closure_proven=False)
    decision = eps.select_placement(responsibility=_responsibility(), demand=_demand(), candidates=(candidate,))
    assert decision.exclusions == (
        eps.CandidateExclusion(worker_id="worker-1", reason=eps.ExclusionReason.HOST_SOURCE_UNPROVEN),
    )


def test_mode_discriminator_3_fresh_lane_effect_unknown():
    candidate = _candidate(effect_state=EffectState.EFFECT_UNKNOWN)
    decision = eps.select_placement(responsibility=_responsibility(), demand=_demand(), candidates=(candidate,))
    assert decision.exclusions == (
        eps.CandidateExclusion(worker_id="worker-1", reason=eps.ExclusionReason.EFFECT_UNKNOWN),
    )


def test_mode_discriminator_4_shared_account_label_candidates_never_collapse():
    a = _candidate(worker_id="worker-a", account_label="account1")
    b = _candidate(worker_id="worker-b", account_label="account1")
    c = _candidate(worker_id="worker-c", account_label="account1")
    decision = eps.select_placement(responsibility=_responsibility(), demand=_demand(), candidates=(a, b, c))
    assert decision.evaluated_candidates == 3
    payload = decision.to_dict()
    assert len(payload["evidence"]) == 3
    assert {row["worker_id"] for row in payload["evidence"]} == {"worker-a", "worker-b", "worker-c"}
    # No dedup, no rank-by-account_label: identical capacity_state across
    # all three -> an exact tie that abstains, never a silent collapse to
    # "the account".
    assert decision.state is eps.SelectionState.TIE_ABSTAINED
    assert decision.tied_worker_ids == ("worker-a", "worker-b", "worker-c")


def test_mode_discriminator_4_account_label_numbering_never_changes_the_outcome():
    a = _candidate(worker_id="worker-a", account_label="account9")
    b = _candidate(worker_id="worker-b", account_label="account2")
    c = _candidate(worker_id="worker-c", account_label="account1")
    decision = eps.select_placement(responsibility=_responsibility(), demand=_demand(), candidates=(a, b, c))
    assert decision.state is eps.SelectionState.TIE_ABSTAINED
    assert decision.tied_worker_ids == ("worker-a", "worker-b", "worker-c")


def test_mode_discriminator_5_busy_exact_session_excluded_alongside_clean_fresh_selection():
    reuse = _reuse_candidate(worker_id="worker-a", account_label="account1", occupancy=eps.OccupancyState.OCCUPIED)
    fresh = _candidate(worker_id="worker-b", account_label="account1")
    decision = eps.select_placement(responsibility=_responsibility(), demand=_demand(), candidates=(reuse, fresh))
    assert decision.state is eps.SelectionState.SELECTED
    assert decision.selected["worker_id"] == "worker-b"
    assert decision.exclusions == (
        eps.CandidateExclusion(worker_id="worker-a", reason=eps.ExclusionReason.OCCUPIED),
    )


def test_mode_discriminator_6_reuse_candidate_with_non_null_bools_refuses():
    with pytest.raises(ValueError):
        _candidate(
            mode=eps.PlacementMode.EXISTING_SESSION_REUSE,
            creation_surface_accessible=True, session_creation_allowed=None,
        )
    with pytest.raises(ValueError):
        _candidate(
            mode=eps.PlacementMode.EXISTING_SESSION_REUSE,
            creation_surface_accessible=None, session_creation_allowed=False,
        )


def test_mode_discriminator_6_fresh_candidate_with_null_bools_refuses():
    with pytest.raises(ValueError):
        _candidate(
            mode=eps.PlacementMode.NEW_SESSION_MATERIALIZATION,
            creation_surface_accessible=None, session_creation_allowed=True,
        )
    with pytest.raises(ValueError):
        _candidate(
            mode=eps.PlacementMode.NEW_SESSION_MATERIALIZATION,
            creation_surface_accessible=True, session_creation_allowed=None,
        )


def test_mode_discriminator_6_demand_with_empty_allowed_modes_refuses():
    with pytest.raises(ValueError):
        _demand(allowed_modes=frozenset())


def test_mode_discriminator_7_permutation_invariance_over_mixed_mode_candidates():
    candidates = [
        _reuse_candidate(worker_id="worker-a", occupancy=eps.OccupancyState.OCCUPIED),
        _candidate(worker_id="worker-b", capacity_state=CapacityState.DEGRADED),
        _candidate(worker_id="worker-c", creation_surface_accessible=False),
        _reuse_candidate(worker_id="worker-d"),
    ]
    reference = None
    reference_json = None
    for permutation in itertools.permutations(candidates):
        decision = eps.select_placement(responsibility=_responsibility(), demand=_demand(), candidates=permutation)
        payload = json.dumps(decision.to_dict(), sort_keys=True)
        if reference is None:
            reference = decision
            reference_json = payload
        else:
            assert decision == reference
            assert payload == reference_json
    assert reference.state is eps.SelectionState.SELECTED
    assert reference.selected["worker_id"] == "worker-d"
    assert reference.selected_mode is eps.PlacementMode.EXISTING_SESSION_REUSE


def test_mode_discriminator_7_correction_replay_creation_disallowed_then_allowed():
    disallowed = _candidate(worker_id="worker-1", session_creation_allowed=False)
    decision_1 = eps.select_placement(responsibility=_responsibility(), demand=_demand(), candidates=(disallowed,))
    assert decision_1.state is eps.SelectionState.NO_ELIGIBLE_CANDIDATE
    assert decision_1.exclusions[0].reason is eps.ExclusionReason.SESSION_CREATION_DISALLOWED

    corrected = _candidate(worker_id="worker-1", session_creation_allowed=True)
    decision_2 = eps.select_placement(responsibility=_responsibility(), demand=_demand(), candidates=(corrected,))
    assert decision_2.state is eps.SelectionState.SELECTED
    assert decision_2.selected["worker_id"] == "worker-1"
    assert decision_2.selected_mode is eps.PlacementMode.NEW_SESSION_MATERIALIZATION


def test_reuse_vs_fresh_exact_tie_still_abstains_and_mode_never_ranks():
    """Frozen spec A.5: ranking is capacity_state ONLY — mode never ranks.
    A reuse candidate and a fresh candidate at the SAME capacity_state
    still abstain on an exact tie, exactly like two same-mode candidates
    would."""
    reuse = _reuse_candidate(worker_id="worker-a")
    fresh = _candidate(worker_id="worker-b")
    decision = eps.select_placement(responsibility=_responsibility(), demand=_demand(), candidates=(reuse, fresh))
    assert decision.state is eps.SelectionState.TIE_ABSTAINED
    assert decision.tied_worker_ids == ("worker-a", "worker-b")
    assert decision.selected_mode is None


def test_mode_discriminator_8_evidence_row_bad_mode_enum_value_refused():
    candidate = _candidate()
    decision = eps.select_placement(responsibility=_responsibility(), demand=_demand(), candidates=(candidate,))
    payload = dict(decision.to_dict())
    payload["evidence"] = [dict(payload["evidence"][0])]
    payload["evidence"][0]["mode"] = "not_a_real_mode"
    with pytest.raises(ValueError):
        eps.validate_placement_selection(payload)


def test_mode_discriminator_8_evidence_reuse_row_with_non_null_bool_refused():
    reuse = _reuse_candidate(worker_id="worker-1", occupancy=eps.OccupancyState.OCCUPIED)
    decision = eps.select_placement(responsibility=_responsibility(), demand=_demand(), candidates=(reuse,))
    payload = dict(decision.to_dict())
    payload["evidence"] = [dict(payload["evidence"][0])]
    payload["evidence"][0]["creation_surface_accessible"] = True
    with pytest.raises(ValueError):
        eps.validate_placement_selection(payload)


def test_mode_discriminator_8_evidence_fresh_row_with_null_bool_refused():
    candidate = _candidate()
    decision = eps.select_placement(responsibility=_responsibility(), demand=_demand(), candidates=(candidate,))
    payload = dict(decision.to_dict())
    payload["evidence"] = [dict(payload["evidence"][0])]
    payload["evidence"][0]["session_creation_allowed"] = None
    with pytest.raises(ValueError):
        eps.validate_placement_selection(payload)


def test_mode_discriminator_8_selected_mode_without_selected_state_refused():
    candidate = _candidate()
    decision = eps.select_placement(responsibility=_responsibility(), demand=_demand(), candidates=(candidate,))
    payload = dict(decision.to_dict())
    payload["state"] = "waiting_capacity"
    with pytest.raises(ValueError):
        eps.validate_placement_selection(payload)


def test_mode_discriminator_8_selected_state_without_selected_mode_refused():
    candidate = _candidate()
    decision = eps.select_placement(responsibility=_responsibility(), demand=_demand(), candidates=(candidate,))
    payload = dict(decision.to_dict())
    payload["selected_mode"] = None
    with pytest.raises(ValueError):
        eps.validate_placement_selection(payload)


def test_mode_discriminator_8_bad_selected_mode_enum_value_refused():
    candidate = _candidate()
    decision = eps.select_placement(responsibility=_responsibility(), demand=_demand(), candidates=(candidate,))
    payload = dict(decision.to_dict())
    payload["selected_mode"] = "not_a_real_mode"
    with pytest.raises(ValueError):
        eps.validate_placement_selection(payload)


def test_candidate_evidence_reuse_row_with_non_null_bools_refuses_at_construction():
    with pytest.raises(ValueError):
        eps.CandidateEvidence(
            worker_id="worker-1", provider="acme", account_label="account1", quota_class="standard",
            capabilities=frozenset({"cap_a"}), observed_at_ms=1000,
            mode=eps.PlacementMode.EXISTING_SESSION_REUSE,
            occupancy=eps.OccupancyState.FREE,
            occupancy_source=_source(SourceOwner.RUNTIME_BINDING, "binding-worker-1"),
            capacity_state=CapacityState.AVAILABLE,
            capacity_source=_source(SourceOwner.CAPACITY, "capacity-worker-1"),
            host_source_closure_proven=True,
            closure_source=_source(SourceOwner.CAPACITY, "closure-worker-1"),
            effect_state=EffectState.NONE,
            creation_surface_accessible=True,
            session_creation_allowed=None,
        )


def test_candidate_evidence_fresh_row_with_null_bool_refuses_at_construction():
    with pytest.raises(ValueError):
        eps.CandidateEvidence(
            worker_id="worker-1", provider="acme", account_label="account1", quota_class="standard",
            capabilities=frozenset({"cap_a"}), observed_at_ms=1000,
            mode=eps.PlacementMode.NEW_SESSION_MATERIALIZATION,
            occupancy=eps.OccupancyState.FREE,
            occupancy_source=_source(SourceOwner.RUNTIME_BINDING, "binding-worker-1"),
            capacity_state=CapacityState.AVAILABLE,
            capacity_source=_source(SourceOwner.CAPACITY, "capacity-worker-1"),
            host_source_closure_proven=True,
            closure_source=_source(SourceOwner.CAPACITY, "closure-worker-1"),
            effect_state=EffectState.NONE,
            creation_surface_accessible=None,
            session_creation_allowed=True,
        )


def test_placement_mode_wire_values_pinned():
    assert eps.PlacementMode.EXISTING_SESSION_REUSE.value == "existing_session_reuse"
    assert eps.PlacementMode.NEW_SESSION_MATERIALIZATION.value == "new_session_materialization"


def test_new_exclusion_reason_wire_values_pinned():
    assert eps.ExclusionReason.MODE_NOT_ALLOWED.value == "mode_not_allowed"
    assert eps.ExclusionReason.CREATION_SURFACE_INACCESSIBLE.value == "creation_surface_inaccessible"
    assert eps.ExclusionReason.SESSION_CREATION_DISALLOWED.value == "session_creation_disallowed"


def test_new_exclusion_reasons_fall_through_to_no_eligible_candidate():
    """Ratified: MODE_NOT_ALLOWED/CREATION_SURFACE_INACCESSIBLE/
    SESSION_CREATION_DISALLOWED are absent from every _AGGREGATE_PRECEDENCE
    bucket — durable ineligibility, like HOST_SOURCE_UNPROVEN — so with
    ONLY these reasons present the aggregate falls through to
    NO_ELIGIBLE_CANDIDATE."""
    mode_blocked = _candidate(
        worker_id="worker-a",
        mode=eps.PlacementMode.NEW_SESSION_MATERIALIZATION,
    )
    demand = _demand(allowed_modes=frozenset({eps.PlacementMode.EXISTING_SESSION_REUSE}))
    creation_blocked = _candidate(worker_id="worker-b", creation_surface_accessible=False)
    session_blocked = _candidate(worker_id="worker-c", session_creation_allowed=False)
    decision = eps.select_placement(
        responsibility=_responsibility(), demand=demand,
        candidates=(mode_blocked, creation_blocked, session_blocked),
    )
    assert decision.state is eps.SelectionState.NO_ELIGIBLE_CANDIDATE
    reasons = {e.reason for e in decision.exclusions}
    # mode_blocked's own mode is ALSO not in allowed_modes, but its creation
    # bools default True so it never reaches the earlier gates and reports
    # MODE_NOT_ALLOWED; creation_blocked and session_blocked each fail an
    # EARLIER gate (11/12) than MODE_NOT_ALLOWED (13), even though their
    # mode is equally not-allowed — first failing gate wins.
    assert reasons == {
        eps.ExclusionReason.MODE_NOT_ALLOWED,
        eps.ExclusionReason.CREATION_SURFACE_INACCESSIBLE,
        eps.ExclusionReason.SESSION_CREATION_DISALLOWED,
    }


# ---------------------------------------------------------------------------
# wire-integrity repair — source-authority binding
#
# Review 5084378111 BLOCKER 1: `validate_placement_selection` validated
# `selected`, `selected_mode`, `exclusions`, `tied_worker_ids` and
# `evidence` INDEPENDENTLY and never bound them together, so a caller could
# staple a separately valid snapshot for worker B onto evidence for worker
# A — a document `select_placement()` could never have produced — and
# `compose_control_room()` would render it as the canonical decision.
#
# Every forgery below is built by MUTATING a real `select_placement()`
# output, so each test proves the validator (not the selector) is what
# refuses it.
# ---------------------------------------------------------------------------

def _selected_payload(**kwargs) -> dict:
    """A real SELECTED decision's wire dict — the base every forgery mutates."""
    decision = eps.select_placement(
        responsibility=_responsibility(), demand=_demand(),
        candidates=(_candidate(**kwargs),),
    )
    assert decision.state is eps.SelectionState.SELECTED
    return decision.to_dict()


def test_wire_rejects_selected_snapshot_for_a_worker_with_no_evidence_row():
    """The headline forgery: a SEPARATELY VALID Phase-B snapshot for worker
    B, spliced onto a decision whose evidence is entirely about worker A."""
    payload = _selected_payload(worker_id="worker-a")
    foreign = principal.build_placement_snapshot(
        worker_id="worker-b", quota_class="standard", provider="acme",
        account_label="account1", observed_at_ms=1000,
    )
    # The spliced snapshot is itself valid — the forgery is that nothing
    # in this decision ever OBSERVED worker-b.
    assert principal.validate_placement_snapshot(foreign) == foreign
    payload["selected"] = foreign
    assert [row["worker_id"] for row in payload["evidence"]] == ["worker-a"]
    with pytest.raises(ValueError):
        eps.validate_placement_selection(payload)


def test_wire_rejects_selected_mode_that_contradicts_the_selected_workers_evidence():
    payload = _selected_payload(mode=eps.PlacementMode.NEW_SESSION_MATERIALIZATION)
    assert payload["selected_mode"] == "new_session_materialization"
    assert payload["evidence"][0]["mode"] == "new_session_materialization"
    payload["selected_mode"] = "existing_session_reuse"
    with pytest.raises(ValueError):
        eps.validate_placement_selection(payload)


def test_wire_rejects_a_selected_worker_that_is_also_excluded():
    """`select_placement` can never do this — the winner is by construction
    eligible, and only non-eligible candidates are excluded."""
    decision = eps.select_placement(
        responsibility=_responsibility(), demand=_demand(),
        candidates=(
            _candidate(worker_id="worker-a"),
            _candidate(worker_id="worker-b", capabilities=frozenset({"cap_other"})),
        ),
    )
    assert decision.state is eps.SelectionState.SELECTED
    payload = decision.to_dict()
    assert payload["selected"]["worker_id"] == "worker-a"
    assert [e["worker_id"] for e in payload["exclusions"]] == ["worker-b"]
    payload["exclusions"] = [
        {"worker_id": "worker-a", "reason": payload["exclusions"][0]["reason"]}
    ]
    with pytest.raises(ValueError):
        eps.validate_placement_selection(payload)


def test_wire_rejects_a_selected_worker_that_is_also_tied():
    """Foreclosed twice over: `tied_worker_ids` must be empty unless the
    state is 'tie_abstained', AND a selected worker may never be tied. The
    property under test is that the document is refused, not which rule
    fires first."""
    payload = _selected_payload(worker_id="worker-a")
    payload["tied_worker_ids"] = ["worker-a"]
    with pytest.raises(ValueError):
        eps.validate_placement_selection(payload)


def test_wire_rejects_an_exclusion_id_absent_from_evidence():
    decision = eps.select_placement(
        responsibility=_responsibility(), demand=_demand(),
        candidates=(_candidate(worker_id="worker-a", capabilities=frozenset({"cap_other"})),),
    )
    payload = decision.to_dict()
    assert len(payload["exclusions"]) == 1
    payload["exclusions"] = [
        {"worker_id": "worker-ghost", "reason": payload["exclusions"][0]["reason"]}
    ]
    with pytest.raises(ValueError):
        eps.validate_placement_selection(payload)


def test_wire_rejects_a_tied_id_absent_from_evidence():
    decision = eps.select_placement(
        responsibility=_responsibility(), demand=_demand(),
        candidates=(_candidate(worker_id="worker-a"), _candidate(worker_id="worker-b")),
    )
    assert decision.state is eps.SelectionState.TIE_ABSTAINED
    payload = decision.to_dict()
    assert payload["tied_worker_ids"] == ["worker-a", "worker-b"]
    # still sorted, so the sortedness rule cannot be what refuses this
    payload["tied_worker_ids"] = ["worker-a", "worker-ghost"]
    with pytest.raises(ValueError):
        eps.validate_placement_selection(payload)


def test_wire_stays_fail_closed_when_the_selected_worker_has_duplicate_evidence():
    """Duplicate identity is exactly the case `select_placement` refuses to
    select on at all (it returns RECONCILIATION_REQUIRED). The validator
    must NOT resolve the ambiguity by picking a row — two rows for the
    selected worker is a refusal, not a lookup."""
    payload = _selected_payload(worker_id="worker-a")
    payload["evidence"] = [payload["evidence"][0], dict(payload["evidence"][0])]
    payload["evaluated_candidates"] = 2
    with pytest.raises(ValueError):
        eps.validate_placement_selection(payload)


# ---------------------------------------------------------------------------
# wire-integrity repair — evidence source AUTHORITY (owner), not just shape
#
# Review 5084378111 BLOCKER 2: `PlacementCandidateFact` pins occupancy to
# RUNTIME_BINDING, capacity to CAPACITY and closure to CAPACITY|EXECUTIVE_OS,
# but `CandidateEvidence.__post_init__` and `_validate_evidence_row`
# weakened that to "is a SourceRef" / "is a recognized SourceOwner" — so a
# fabricated row could attribute occupancy to Agent OS/Wake, capacity to
# Executive Inbox, or closure to Surface Bindings and still pass.
# ---------------------------------------------------------------------------

def _evidence(**kwargs) -> eps.CandidateEvidence:
    base = dict(
        worker_id="worker-a",
        provider="acme",
        account_label="account1",
        quota_class="standard",
        capabilities=frozenset({"cap_a"}),
        observed_at_ms=1000,
        occupancy=eps.OccupancyState.FREE,
        occupancy_source=_source(SourceOwner.RUNTIME_BINDING, "binding-a"),
        capacity_state=CapacityState.AVAILABLE,
        capacity_source=_source(SourceOwner.CAPACITY, "capacity-a"),
        host_source_closure_proven=True,
        closure_source=_source(SourceOwner.CAPACITY, "closure-a"),
        effect_state=EffectState.NONE,
        mode=eps.PlacementMode.NEW_SESSION_MATERIALIZATION,
        creation_surface_accessible=True,
        session_creation_allowed=True,
    )
    base.update(kwargs)
    return eps.CandidateEvidence(**base)


def test_candidate_evidence_accepts_the_authoritative_owners():
    assert _evidence() is not None
    # closure may come from EITHER owner in the pinned pair
    assert _evidence(closure_source=_source(SourceOwner.EXECUTIVE_OS, "closure-a")) is not None


@pytest.mark.parametrize(
    "field, owner",
    [
        ("occupancy_source", SourceOwner.AGENT_OS),
        ("occupancy_source", SourceOwner.WAKE),
        ("occupancy_source", SourceOwner.CAPACITY),
        ("capacity_source", SourceOwner.EXECUTIVE_INBOX),
        ("capacity_source", SourceOwner.RUNTIME_BINDING),
        ("closure_source", SourceOwner.SURFACE_BINDINGS),
        ("closure_source", SourceOwner.AGENT_OS),
    ],
)
def test_candidate_evidence_rejects_a_non_authoritative_source_owner(field, owner):
    """Direct-object regression: the dataclass must pin the SAME owner sets
    PlacementCandidateFact already pins."""
    with pytest.raises(ValueError):
        _evidence(**{field: _source(owner, "forged-ref")})


@pytest.mark.parametrize(
    "field, owner",
    [
        ("occupancy_source", "agent_os"),
        ("occupancy_source", "wake"),
        ("occupancy_source", "capacity"),
        ("capacity_source", "executive_inbox"),
        ("capacity_source", "runtime_binding"),
        ("closure_source", "surface_bindings"),
        ("closure_source", "agent_os"),
    ],
)
def test_wire_rejects_a_non_authoritative_evidence_source_owner(field, owner):
    """Wire regression mirroring the direct-object one: a fabricated
    document must not be able to re-attribute a fact to an owner that has
    no authority over it."""
    payload = _selected_payload(worker_id="worker-a")
    assert len(payload["evidence"]) == 1  # single row: sortedness cannot be the refusal
    payload["evidence"][0][field]["owner"] = owner
    with pytest.raises(ValueError):
        eps.validate_placement_selection(payload)


def test_wire_accepts_executive_os_as_a_closure_owner():
    """The pinned closure pair is CAPACITY|EXECUTIVE_OS — the repair must
    pin the exact set, not collapse it to a single owner."""
    payload = _selected_payload(worker_id="worker-a")
    payload["evidence"][0]["closure_source"]["owner"] = "executive_os"
    assert eps.validate_placement_selection(payload)["evidence"][0]["closure_source"]["owner"] == "executive_os"


# ---------------------------------------------------------------------------
# wire-integrity repair — MAJOR 3: no caller-controlled key echo
# ---------------------------------------------------------------------------

def test_top_level_key_error_never_echoes_caller_supplied_key_names():
    """`compose_control_room()` appends `str(exc)` from this validator into
    Chairman-visible `degraded`, so the top-level exact-key error must name
    FIELDS only — never the caller's own keys."""
    secret = "AWS_SECRET_ACCESS_KEY_AKIAIOSFODNN7EXAMPLE"
    with pytest.raises(ValueError) as excinfo:
        eps.validate_placement_selection({secret: "x", "another_caller_key": "y"})
    message = str(excinfo.value)
    assert secret not in message
    assert "another_caller_key" not in message
    # every key it DOES name is one of this module's own constants
    for key in _SELECTION_KEYS_FOR_TEST:
        assert key in message


_SELECTION_KEYS_FOR_TEST = sorted(eps._SELECTION_KEYS)


def test_top_level_error_on_a_non_mapping_never_echoes_the_value_or_its_type():
    class AKIAIOSFODNN7EXAMPLE:  # a type name is caller-controlled too
        pass

    with pytest.raises(ValueError) as excinfo:
        eps.validate_placement_selection(AKIAIOSFODNN7EXAMPLE())
    assert "AKIAIOSFODNN7EXAMPLE" not in str(excinfo.value)


# ---------------------------------------------------------------------------
# wire-integrity repair — the repair must not narrow any GENUINE decision
# ---------------------------------------------------------------------------

def test_every_genuine_decision_state_still_round_trips_byte_identically():
    """The binding rules are derived from properties `select_placement`
    already guarantees, so EVERY real decision — including the duplicate
    (reconciliation_required) and tie paths the new rules talk about — must
    still round-trip unchanged."""
    reuse_demand = _demand(allowed_modes=frozenset({eps.PlacementMode.EXISTING_SESSION_REUSE}))
    cases = {
        "selected": (_demand(), (_candidate(worker_id="worker-a"),)),
        "selected_reuse_mode": (reuse_demand, (_reuse_candidate(worker_id="worker-a"),)),
        "tie_abstained": (_demand(), (_candidate(worker_id="worker-a"), _candidate(worker_id="worker-b"))),
        "reconciliation_required_duplicate": (
            _demand(), (_candidate(worker_id="worker-a"), _candidate(worker_id="worker-a")),
        ),
        "no_eligible_candidate": (
            _demand(), (_candidate(worker_id="worker-a", capabilities=frozenset({"cap_other"})),),
        ),
        "no_candidates": (_demand(), ()),
    }
    seen_states = set()
    for name, (demand, candidates) in cases.items():
        decision = eps.select_placement(
            responsibility=_responsibility(), demand=demand, candidates=candidates,
        )
        seen_states.add(decision.state)
        payload = decision.to_dict()
        revalidated = eps.validate_placement_selection(payload)
        assert revalidated == payload, name
        assert json.dumps(revalidated, sort_keys=True) == json.dumps(payload, sort_keys=True), name
        assert payload["selection_is_commitment"] is False, name
    # the duplicate and tie paths really were exercised
    assert eps.SelectionState.RECONCILIATION_REQUIRED in seen_states
    assert eps.SelectionState.TIE_ABSTAINED in seen_states
    assert eps.SelectionState.SELECTED in seen_states


def test_stale_evidence_decision_still_round_trips():
    decision = eps.select_placement(
        responsibility=_responsibility(freshness=Freshness.STALE), demand=_demand(),
        candidates=(_candidate(worker_id="worker-a"),),
    )
    assert decision.state is eps.SelectionState.STALE_EVIDENCE
    payload = decision.to_dict()
    assert eps.validate_placement_selection(payload) == payload


def test_permutation_invariance_survives_the_repair():
    candidates = (
        _candidate(worker_id="worker-a"),
        _candidate(worker_id="worker-b", capacity_state=CapacityState.DEGRADED),
        _candidate(worker_id="worker-c", capabilities=frozenset({"cap_other"})),
    )
    baseline = None
    for permutation in itertools.permutations(candidates):
        decision = eps.select_placement(
            responsibility=_responsibility(), demand=_demand(), candidates=permutation,
        )
        payload = json.dumps(decision.to_dict(), sort_keys=True)
        assert eps.validate_placement_selection(decision.to_dict()) == decision.to_dict()
        if baseline is None:
            baseline = payload
        assert payload == baseline


def test_nested_selected_snapshot_error_never_echoes_caller_supplied_key_names():
    """Sibling of the top-level echo, found by the exact-head review: the
    `selected` sub-mapping is ALSO caller-controlled, and it is validated by
    `executive_orchestration_principal.validate_placement_snapshot`, whose
    own closed-key error still renders `sorted(value)`. Its
    `OrchestrationPrincipalError` subclasses ValueError, so
    `compose_control_room()` appends it to Chairman-visible `degraded` just
    like any other. This module owns the boundary, so it re-raises a
    constant field-only error rather than relaying that text."""
    secret = "AWS_SECRET_ACCESS_KEY_AKIA5EXAMPLE"
    token = "sk-ant-api03-LEAKED-TOKEN-TAIL"
    payload = _selected_payload(worker_id="worker-a")
    payload["selected"] = {secret: 1, token: 2}
    with pytest.raises(ValueError) as excinfo:
        eps.validate_placement_selection(payload)
    message = str(excinfo.value)
    assert secret not in message
    assert token not in message


def test_nested_selected_snapshot_error_never_echoes_a_caller_value():
    """The same boundary for a non-mapping and for a valid-shaped snapshot
    carrying a bad VALUE — neither may relay caller text."""
    payload = _selected_payload(worker_id="worker-a")
    payload["selected"] = {
        "schema_version": "mastermind.executive_placement_snapshot/v1",
        "worker_id": "worker-a",
        "quota_class": "standard",
        "provider": "acme",
        "account_label": "SUPER-SECRET-ACCOUNT-VALUE",
        "observed_at_ms": "not-an-int",
    }
    with pytest.raises(ValueError) as excinfo:
        eps.validate_placement_selection(payload)
    assert "SUPER-SECRET-ACCOUNT-VALUE" not in str(excinfo.value)


#: The constant this module raises when `selected` fails the Phase-B
#: snapshot contract. Asserted BY TEXT on purpose: merely asserting
#: "some ValueError" cannot tell a real refusal apart from silently
#: swallowing the error and setting `selected = None`, which then trips the
#: unrelated present-iff-state rule and raises a DIFFERENT ValueError. A
#: mutation probe proved that weaker assertion passes for the wrong reason.
_BAD_SNAPSHOT_MESSAGE = "selected is not a well-formed placement snapshot"


@pytest.mark.parametrize(
    "bad_selected",
    [
        {"totally": "wrong"},
        "not even a mapping",
        {"AWS_SECRET_ACCESS_KEY_AKIA5EXAMPLE": 1},
        None.__class__,  # a type object, not a mapping
    ],
)
def test_selected_must_still_be_a_wellformed_snapshot(bad_selected):
    """The constant re-raise must REFUSE, not silently become an accept —
    and it must refuse at the snapshot boundary specifically."""
    payload = _selected_payload(worker_id="worker-a")
    payload["selected"] = bad_selected
    with pytest.raises(ValueError) as excinfo:
        eps.validate_placement_selection(payload)
    assert str(excinfo.value) == _BAD_SNAPSHOT_MESSAGE


# ---------------------------------------------------------------------------
# provenance wave — the decision must be one select_placement() would emit
#
# Review 5084660789 BLOCKER: identity+mode binding closed symptoms, not the
# root cause. The wire now carries its own canonical input projection
# (responsibility freshness, the complete PlacementDemand, and a complete
# PlacementCandidateFact projection per evidence row), and
# validate_placement_selection() recomputes the decision through the ONE
# existing selector and demands equality.
#
# Every forgery below MUTATES a genuine select_placement() output, so each
# test proves the validator refuses it — not that the selector cannot emit it.
# ---------------------------------------------------------------------------

#: Constant, value-free refusal for a decision that is not what the selector
#: would have produced from its own declared inputs.
_PROVENANCE_MESSAGE = (
    "decision does not match the result of recomputing it from its own "
    "declared inputs"
)


def _two_candidate_selected() -> dict:
    """A genuine SELECTED decision over one AVAILABLE and one DEGRADED
    candidate — worker-a wins, worker-b is neither excluded nor tied."""
    decision = eps.select_placement(
        responsibility=_responsibility(), demand=_demand(),
        candidates=(
            _candidate(worker_id="worker-a"),
            _candidate(worker_id="worker-b", capacity_state=CapacityState.DEGRADED),
        ),
    )
    assert decision.state is eps.SelectionState.SELECTED
    payload = decision.to_dict()
    assert payload["selected"]["worker_id"] == "worker-a"
    return payload


def _row(payload: dict, worker_id: str) -> dict:
    return [r for r in payload["evidence"] if r["worker_id"] == worker_id][0]


@pytest.mark.parametrize(
    "field, forged",
    [
        ("provider", "attacker-cloud"),
        ("account_label", "victim-billing-account"),
        ("quota_class", "unlimited"),
        ("observed_at_ms", 999999999),
    ],
)
def test_wire_rejects_a_selected_snapshot_field_unbound_to_the_candidate(field, forged):
    """The residual half of the staple-a-snapshot forgery: same worker_id and
    same mode, but a snapshot field the evidence row now contradicts."""
    payload = _two_candidate_selected()
    assert payload["selected"][field] != forged
    payload["selected"][field] = forged
    with pytest.raises(ValueError) as excinfo:
        eps.validate_placement_selection(payload)
    assert str(excinfo.value) == _PROVENANCE_MESSAGE


@pytest.mark.parametrize(
    "mutation",
    [
        {"occupancy": "occupied"},
        {"occupancy": "bound_elsewhere"},
        {"occupancy": "contradictory"},
        {"capacity_state": "unknown"},
        {"host_source_closure_proven": False},
        {"effect_state": "effect_unknown"},
        {"creation_surface_accessible": False},
        {"session_creation_allowed": False},
    ],
)
def test_wire_rejects_a_selected_worker_its_own_evidence_makes_ineligible(mutation):
    """Exact conditions `_first_exclusion_reason()` excludes on. Before the
    provenance gate the validator happily accepted `state=selected` beside
    an evidence row saying the winner was occupied/unknown/unproven."""
    payload = _two_candidate_selected()
    _row(payload, "worker-a").update(mutation)
    with pytest.raises(ValueError) as excinfo:
        eps.validate_placement_selection(payload)
    assert str(excinfo.value) == _PROVENANCE_MESSAGE


@pytest.mark.parametrize("source_field", ["occupancy_source", "capacity_source"])
@pytest.mark.parametrize("freshness", ["stale", "unknown"])
def test_wire_rejects_a_selected_worker_whose_source_freshness_excludes_it(source_field, freshness):
    payload = _two_candidate_selected()
    _row(payload, "worker-a")[source_field]["freshness"] = freshness
    with pytest.raises(ValueError) as excinfo:
        eps.validate_placement_selection(payload)
    assert str(excinfo.value) == _PROVENANCE_MESSAGE


def test_wire_rejects_a_forged_aggregate_state_over_eligible_evidence():
    payload = _two_candidate_selected()
    payload.update(state="no_eligible_candidate", selected=None, selected_mode=None)
    with pytest.raises(ValueError) as excinfo:
        eps.validate_placement_selection(payload)
    assert str(excinfo.value) == _PROVENANCE_MESSAGE


def test_wire_rejects_a_duplicate_identity_exclusion_with_no_duplicate_in_evidence():
    payload = _two_candidate_selected()
    payload.update(
        state="reconciliation_required", selected=None, selected_mode=None,
        exclusions=[{"worker_id": "worker-a", "reason": "duplicate_identity"}],
    )
    with pytest.raises(ValueError) as excinfo:
        eps.validate_placement_selection(payload)
    assert str(excinfo.value) == _PROVENANCE_MESSAGE


def test_wire_rejects_an_exclusion_reason_its_own_evidence_row_contradicts():
    """worker-b's evidence is free/available/current/closure-proven, so
    `occupied` is a reason the selector could not have produced for it."""
    payload = _two_candidate_selected()
    payload["exclusions"] = [{"worker_id": "worker-b", "reason": "occupied"}]
    with pytest.raises(ValueError) as excinfo:
        eps.validate_placement_selection(payload)
    assert str(excinfo.value) == _PROVENANCE_MESSAGE


def test_wire_rejects_a_tie_between_candidates_of_unequal_capacity_rank():
    """worker-a is AVAILABLE and worker-b DEGRADED — `_CAPACITY_RANK` can
    never tie them."""
    payload = _two_candidate_selected()
    payload.update(
        state="tie_abstained", selected=None, selected_mode=None,
        tied_worker_ids=["worker-a", "worker-b"],
    )
    with pytest.raises(ValueError) as excinfo:
        eps.validate_placement_selection(payload)
    assert str(excinfo.value) == _PROVENANCE_MESSAGE


def test_wire_rejects_a_forged_tie_membership_on_a_genuine_tie():
    """Two equal candidates genuinely tie; swapping one tied id for the
    other worker's is refused even though both ids appear in evidence."""
    decision = eps.select_placement(
        responsibility=_responsibility(), demand=_demand(),
        candidates=(
            _candidate(worker_id="worker-a"),
            _candidate(worker_id="worker-b"),
            _candidate(worker_id="worker-c", capacity_state=CapacityState.DEGRADED),
        ),
    )
    assert decision.state is eps.SelectionState.TIE_ABSTAINED
    payload = decision.to_dict()
    assert payload["tied_worker_ids"] == ["worker-a", "worker-b"]
    payload["tied_worker_ids"] = ["worker-a", "worker-c"]  # still sorted
    with pytest.raises(ValueError) as excinfo:
        eps.validate_placement_selection(payload)
    assert str(excinfo.value) == _PROVENANCE_MESSAGE


@pytest.mark.parametrize(
    "mutation",
    [
        {"required_capabilities": ["cap_zzz"]},
        {"quota_class": "premium"},
        {"provider": "other-cloud"},
        {"allowed_modes": ["existing_session_reuse"]},
    ],
)
def test_wire_rejects_a_demand_the_decision_was_not_computed_against(mutation):
    """The demand is an INPUT: swapping it changes which candidates are
    eligible, so the recomputed decision no longer matches."""
    payload = _two_candidate_selected()
    payload["demand"].update(mutation)
    with pytest.raises(ValueError) as excinfo:
        eps.validate_placement_selection(payload)
    assert str(excinfo.value) == _PROVENANCE_MESSAGE


@pytest.mark.parametrize(
    "relaxation",
    [
        {"required_capabilities": []},
        {"provider": None},
    ],
)
def test_an_outcome_preserving_demand_relaxation_is_accepted_by_design(relaxation):
    """Pins the gate's EXACT contract, so a later reader does not mistake
    this for a hole.

    A demand relaxation that excludes nobody new leaves the recomputed
    decision identical, so the document really is one `select_placement()`
    would emit from the inputs it declares — which is precisely what this
    gate authenticates. It does NOT attest that the declared demand was the
    demand some upstream caller actually held; nothing on a self-describing
    wire could. A consumer that cares which demand was in force must READ
    `demand` off the document (it is carried for exactly that reason), not
    infer it from the decision having validated.
    """
    payload = _two_candidate_selected()
    payload["demand"].update(relaxation)
    revalidated = eps.validate_placement_selection(payload)
    # accepted, and the relaxed demand is what the consumer is shown
    assert revalidated["demand"] == payload["demand"]
    # the selection itself is unchanged — no new worker became selectable
    assert revalidated["selected"] == payload["selected"]
    assert revalidated["state"] == "selected"


def test_wire_rejects_a_flipped_responsibility_freshness():
    """A non-CURRENT responsibility short-circuits to STALE_EVIDENCE, so the
    gate fact cannot be restated without changing the outcome."""
    payload = _two_candidate_selected()
    payload["responsibility_freshness"] = "stale"
    with pytest.raises(ValueError) as excinfo:
        eps.validate_placement_selection(payload)
    assert str(excinfo.value) == _PROVENANCE_MESSAGE


def test_provenance_refusal_is_value_free_for_a_secret_shaped_forgery():
    payload = _two_candidate_selected()
    payload["selected"]["account_label"] = "AKIAIOSFODNN7EXAMPLESECRET"
    with pytest.raises(ValueError) as excinfo:
        eps.validate_placement_selection(payload)
    assert "AKIAIOSFODNN7EXAMPLESECRET" not in str(excinfo.value)


def test_validation_calls_the_one_existing_selector_exactly_once(monkeypatch):
    """The gate must RECOMPUTE through the single canonical owner, never
    reimplement ranking/exclusion policy in a second validator."""
    payload = _two_candidate_selected()
    calls = []
    real = eps.select_placement

    def counting(**kwargs):
        calls.append(kwargs)
        return real(**kwargs)

    monkeypatch.setattr(eps, "select_placement", counting)
    assert eps.validate_placement_selection(payload) == payload
    assert len(calls) == 1
    # and it was handed rebuilt TYPED inputs, not the raw wire dict
    assert isinstance(calls[0]["demand"], eps.PlacementDemand)
    assert all(isinstance(c, eps.PlacementCandidateFact) for c in calls[0]["candidates"])


def test_every_genuine_state_round_trips_byte_identically_under_provenance():
    """Including the correction/duplicate and tie paths the new rules talk
    about, and every permutation of the candidate list."""
    reuse_demand = _demand(allowed_modes=frozenset({eps.PlacementMode.EXISTING_SESSION_REUSE}))
    cases = {
        "selected": (_responsibility(), _demand(), (_candidate(worker_id="worker-a"),)),
        "selected_reuse": (_responsibility(), reuse_demand, (_reuse_candidate(worker_id="worker-a"),)),
        "tie": (_responsibility(), _demand(), (_candidate(worker_id="worker-a"), _candidate(worker_id="worker-b"))),
        "duplicate": (_responsibility(), _demand(), (_candidate(worker_id="worker-a"), _candidate(worker_id="worker-a"))),
        "stale": (_responsibility(freshness=Freshness.STALE), _demand(), (_candidate(worker_id="worker-a"),)),
        "no_eligible": (_responsibility(), _demand(), (_candidate(worker_id="worker-a", capabilities=frozenset({"other"})),)),
        "empty": (_responsibility(), _demand(), ()),
    }
    seen = set()
    for name, (responsibility, demand, candidates) in cases.items():
        decision = eps.select_placement(
            responsibility=responsibility, demand=demand, candidates=candidates,
        )
        seen.add(decision.state)
        payload = decision.to_dict()
        assert eps.validate_placement_selection(payload) == payload, name
        assert json.dumps(eps.validate_placement_selection(payload), sort_keys=True) == json.dumps(
            payload, sort_keys=True
        ), name
    assert {
        eps.SelectionState.SELECTED,
        eps.SelectionState.TIE_ABSTAINED,
        eps.SelectionState.RECONCILIATION_REQUIRED,
        eps.SelectionState.STALE_EVIDENCE,
    } <= seen


def test_permutation_invariance_holds_under_the_provenance_gate():
    candidates = (
        _candidate(worker_id="worker-a"),
        _candidate(worker_id="worker-b", capacity_state=CapacityState.DEGRADED),
        _candidate(worker_id="worker-c", capabilities=frozenset({"cap_other"})),
    )
    baseline = None
    for permutation in itertools.permutations(candidates):
        payload = eps.select_placement(
            responsibility=_responsibility(), demand=_demand(), candidates=permutation,
        ).to_dict()
        assert eps.validate_placement_selection(payload) == payload
        rendered = json.dumps(payload, sort_keys=True)
        baseline = rendered if baseline is None else baseline
        assert rendered == baseline


#: Passes `_require_token` (non-empty, no whitespace/'@'/'/') but fails the
#: Phase-B snapshot's stricter `_PROVIDER_RE` (lowercase only). Lets a wire
#: row be individually well-shaped yet unable to become a typed candidate.
_TOKEN_OK_BUT_NOT_SNAPSHOT_SAFE = "ACME"


def test_wire_refuses_evidence_that_cannot_be_rebuilt_into_typed_candidates():
    """The reconstruction step must REFUSE, never fall through to accepting
    the supplied document.

    A mutation probe proved this needed its own test: making the failed
    reconstruction return the document instead of raising survived the whole
    suite, because every other forgery rebuilds fine and is caught later by
    the equality check. This row cannot be rebuilt at all.
    """
    payload = _two_candidate_selected()
    _row(payload, "worker-a")["provider"] = _TOKEN_OK_BUT_NOT_SNAPSHOT_SAFE
    with pytest.raises(ValueError) as excinfo:
        eps.validate_placement_selection(payload)
    assert str(excinfo.value) == "decision inputs do not form a valid selector invocation"
    # value-free: the offending token never appears in the message
    assert _TOKEN_OK_BUT_NOT_SNAPSHOT_SAFE not in str(excinfo.value)


def test_evidence_carries_the_candidates_own_values_not_fixture_defaults():
    """Pins that each candidate fact is really CARRIED per row.

    A mutation probe proved this needed its own test: hard-coding
    `provider` to the fixture default in `CandidateEvidence.to_dict()`
    survived the whole suite, because every other fixture used that same
    default. These values are deliberately distinct from every default in
    this file.
    """
    candidate = _candidate(
        worker_id="worker-a",
        provider="zeta-cloud",
        account_label="acct-9",
        quota_class="premium",
        capabilities=frozenset({"cap_a", "cap_b"}),
        observed_at_ms=4242,
    )
    decision = eps.select_placement(
        responsibility=_responsibility(),
        demand=_demand(
            required_capabilities=frozenset({"cap_a"}),
            quota_class="premium",
            provider="zeta-cloud",
        ),
        candidates=(candidate,),
    )
    assert decision.state is eps.SelectionState.SELECTED
    payload = decision.to_dict()

    row = payload["evidence"][0]
    assert row["provider"] == "zeta-cloud"
    assert row["account_label"] == "acct-9"
    assert row["quota_class"] == "premium"
    assert row["capabilities"] == ["cap_a", "cap_b"]
    assert row["observed_at_ms"] == 4242
    # and the snapshot the Chairman sees is bound to those same values
    assert payload["selected"]["provider"] == "zeta-cloud"
    assert payload["selected"]["account_label"] == "acct-9"
    assert payload["selected"]["quota_class"] == "premium"
    assert payload["selected"]["observed_at_ms"] == 4242
    assert eps.validate_placement_selection(payload) == payload


# ---------------------------------------------------------------------------
# exact-head review of 19227a64 — round-trip closure + token-law gaps
#
# All three are PRE-EXISTING (they predate the provenance wave) and all three
# are fixed the same way: ONE shared helper serves both construction and wire
# revalidation, so the two sides cannot disagree by construction.
# ---------------------------------------------------------------------------

def _candidate_fields() -> dict:
    """Every PlacementCandidateFact field as a plain dict, so a test can
    substitute a whole SourceRef (which `_candidate()` builds internally)."""
    return dict(
        worker_id="worker-a", provider="acme", account_label="account1",
        quota_class="standard", capabilities=frozenset({"cap_a"}),
        observed_at_ms=1000,
        occupancy=eps.OccupancyState.FREE,
        occupancy_source=_source(SourceOwner.RUNTIME_BINDING, "binding-a"),
        capacity_state=CapacityState.AVAILABLE,
        capacity_source=_source(SourceOwner.CAPACITY, "capacity-a"),
        host_source_closure_proven=True,
        closure_source=_source(SourceOwner.CAPACITY, "closure-a"),
        effect_state=EffectState.NONE,
        mode=eps.PlacementMode.NEW_SESSION_MATERIALIZATION,
        creation_surface_accessible=True, session_creation_allowed=True,
    )


@pytest.mark.parametrize(
    "observed_at",
    [
        "2026-09-01T00:00:00Z/run-9",       # a path-ish segment
        "2026-09-01T00:00:00Z@studio",      # an at-sign
    ],
)
@pytest.mark.parametrize(
    "source_field", ["occupancy_source", "capacity_source", "closure_source"],
)
def test_candidate_refuses_a_source_observed_at_the_wire_could_not_carry(source_field, observed_at):
    """Round-trip closure, the `.observed_at` half.

    `PlacementCandidateFact` already eagerly token-checks each
    `*_source.ref` precisely so a candidate cannot construct cleanly and
    then emit a decision its OWN wire validator rejects. The same closure
    was missing for `*_source.observed_at`: `SourceRef` permits `@`/`/`
    there, but `_validate_source_ref_dict` applies `_require_token`. The
    result was a genuine `select_placement()` output that failed its own
    validator, so the real Control Room dropped a real decision.
    """
    owners = {
        "occupancy_source": SourceOwner.RUNTIME_BINDING,
        "capacity_source": SourceOwner.CAPACITY,
        "closure_source": SourceOwner.CAPACITY,
    }
    fields = _candidate_fields()
    fields[source_field] = SourceRef(
        owner=owners[source_field], ref="ref-a",
        observed_at=observed_at, freshness=Freshness.CURRENT,
    )
    with pytest.raises(ValueError):
        eps.PlacementCandidateFact(**fields)


#: Values chosen to straddle every boundary the token law draws, so the
#: sweep below exercises BOTH outcomes: refused-at-construction and
#: constructs-and-must-revalidate.
_CLOSURE_SWEEP_VALUES = [
    "plain-token", "colon:token", "plus+token", "dot.token",      # legal
    "2026-09-01T00:00:00Z", "2026-09-01T00:00:00+05:45",          # legal timestamps
    "has space", "has@at", "has/slash", "has\\backslash",           # illegal separators
    "nul\x00byte", "esc\x1b[31m", "bell\x07", "del\x7f", "",        # illegal controls/empty
]

#: Every string-valued field that reaches the wire, with a setter that puts
#: a value into a candidate's field dict. `responsibility_ref` is swept
#: separately since it belongs to the responsibility, not the candidate.
_CLOSURE_SWEEP_FIELDS = {
    "worker_id": lambda f, v: f.__setitem__("worker_id", v),
    "provider": lambda f, v: f.__setitem__("provider", v),
    "account_label": lambda f, v: f.__setitem__("account_label", v),
    "quota_class": lambda f, v: f.__setitem__("quota_class", v),
    "capabilities_item": lambda f, v: f.__setitem__("capabilities", frozenset({v})),
    "occupancy_source.ref": lambda f, v: f.__setitem__(
        "occupancy_source", SourceRef(owner=SourceOwner.RUNTIME_BINDING, ref=v,
                                      observed_at="2026-09-01T00:00:00Z",
                                      freshness=Freshness.CURRENT)),
    "capacity_source.ref": lambda f, v: f.__setitem__(
        "capacity_source", SourceRef(owner=SourceOwner.CAPACITY, ref=v,
                                     observed_at="2026-09-01T00:00:00Z",
                                     freshness=Freshness.CURRENT)),
    "closure_source.ref": lambda f, v: f.__setitem__(
        "closure_source", SourceRef(owner=SourceOwner.CAPACITY, ref=v,
                                    observed_at="2026-09-01T00:00:00Z",
                                    freshness=Freshness.CURRENT)),
    "occupancy_source.observed_at": lambda f, v: f.__setitem__(
        "occupancy_source", SourceRef(owner=SourceOwner.RUNTIME_BINDING, ref="ref-a",
                                      observed_at=v, freshness=Freshness.CURRENT)),
    "capacity_source.observed_at": lambda f, v: f.__setitem__(
        "capacity_source", SourceRef(owner=SourceOwner.CAPACITY, ref="ref-b",
                                     observed_at=v, freshness=Freshness.CURRENT)),
    "closure_source.observed_at": lambda f, v: f.__setitem__(
        "closure_source", SourceRef(owner=SourceOwner.CAPACITY, ref="ref-c",
                                    observed_at=v, freshness=Freshness.CURRENT)),
}


@pytest.mark.parametrize("field", sorted(_CLOSURE_SWEEP_FIELDS))
def test_every_constructible_candidate_produces_a_revalidatable_decision(field):
    """The CLOSURE property, actually swept.

    If a candidate can be BUILT, the decision it produces MUST pass this
    module's own validator. The two validators are separate code paths, so
    any field where construction is more permissive than revalidation
    yields a genuine decision the Chairman silently loses — that is exactly
    how the `*_source.observed_at` gap shipped.

    Exact-head review N-3: the previous version of this test claimed this
    property while exercising three benign timestamps, and did NOT fail
    when the observed_at hunk was reverted. It now sweeps every
    string-valued field that reaches the wire against values straddling
    every boundary the token law draws, and asserts BOTH outcomes occur so
    the sweep cannot silently degenerate into all-refused.
    """
    setter = _CLOSURE_SWEEP_FIELDS[field]
    constructed = refused = 0
    for value in _CLOSURE_SWEEP_VALUES:
        fields = _candidate_fields()
        try:
            setter(fields, value)
            candidate = eps.PlacementCandidateFact(**fields)
        except (ValueError, TypeError):
            refused += 1
            continue
        constructed += 1
        # The demand is deliberately NOT matched to the mutated field: an
        # evidence row is emitted for every candidate whether it is eligible
        # or excluded, so the mutated value reaches the wire either way and
        # the closure property applies regardless of the outcome state.
        payload = eps.select_placement(
            responsibility=_responsibility(), demand=_demand(), candidates=(candidate,),
        ).to_dict()
        # THE closure assertion: constructed => its own wire form revalidates
        assert eps.validate_placement_selection(payload) == payload, (field, value)
    # the sweep really exercised both sides of the boundary
    assert constructed, f"{field}: nothing constructed — sweep is vacuous"
    assert refused, f"{field}: nothing refused — sweep is vacuous"


@pytest.mark.parametrize("value", _CLOSURE_SWEEP_VALUES)
def test_responsibility_ref_closure_is_symmetric(value):
    """Same closure property for `responsibility_ref`: if
    `select_placement` accepts it, the decision it produces must
    revalidate; if this module's token law refuses it, that refusal must
    happen in step-1 input refusal, never mid-algorithm (review N-1)."""
    ref = f"WS:{value}"
    try:
        responsibility = _responsibility(ref=ref)
    except (ValueError, TypeError):
        return  # the steward refused it first; nothing for this module to do
    # Instrument the first algorithm step that touches candidates. A step-1
    # input refusal must happen BEFORE this runs; a late raise from
    # PlacementSelectionDecision.__post_init__ happens after it. Asserting
    # only "some ValueError" cannot tell those apart — that is exactly how
    # the previous version of this test passed while N-1 was live.
    ran = []
    real_evidence = eps._evidence_from_candidates

    def _tracking(candidates):
        ran.append(True)
        return real_evidence(candidates)

    monkeypatch_target = eps
    original = monkeypatch_target._evidence_from_candidates
    monkeypatch_target._evidence_from_candidates = _tracking
    try:
        try:
            decision = eps.select_placement(
                responsibility=responsibility, demand=_demand(),
                candidates=(_candidate(worker_id="worker-a"),),
            )
        except ValueError:
            assert not ran, (
                f"{ref!r} was refused only AFTER the algorithm ran — a "
                "non-representable responsibility_ref must be refused in "
                "step-1 input refusal, never mid-algorithm"
            )
            return
    finally:
        monkeypatch_target._evidence_from_candidates = original
    payload = decision.to_dict()
    assert eps.validate_placement_selection(payload) == payload, ref


@pytest.mark.parametrize(
    "responsibility_ref",
    [
        "WS:/Users/chriswong/.ssh/id_rsa",
        "WS:daniela33777555@gmail.com",
        "WS:teams/alpha",
    ],
)
def test_responsibility_ref_obeys_the_modules_own_token_law(responsibility_ref):
    """`_require_token`'s contract says an email address or a filesystem
    path can never flow through ANY token field, but `responsibility_ref`
    had its own looser check and reached the Chairman wire verbatim."""
    with pytest.raises(ValueError):
        eps._require_responsibility_ref(responsibility_ref)


def test_a_decision_cannot_carry_a_path_shaped_responsibility_ref():
    """Both sides: construction refuses it, so the selector can never emit
    one, and the wire validator refuses it too."""
    payload = _selected_payload(worker_id="worker-a")
    payload["responsibility_ref"] = "WS:/Users/chriswong/.ssh/id_rsa"
    with pytest.raises(ValueError):
        eps.validate_placement_selection(payload)


@pytest.mark.parametrize(
    "token",
    [
        "qc\x00-1",                    # NUL
        "\x1b[2J\x1b[31mqc-1",         # ANSI terminal escape
        "C:\\Users\\chriswong\\secrets.txt",  # a Windows path
        "line\x07bell",                # BEL
    ],
)
def test_token_law_rejects_control_characters_and_backslash_paths(token):
    """`str.isspace()` does not cover NUL, ESC or BEL, and `/` alone does
    not cover a backslash path — so these reached the composed document and
    on to a terminal renderer."""
    with pytest.raises(ValueError):
        eps._require_token("t", token)


@pytest.mark.parametrize(
    "escape", ["\x1b[2J\x1b[31mref\x00-1", "ref\x07bell", "C:\\Users\\x\\id_rsa"],
)
def test_a_decision_cannot_carry_a_terminal_escape_in_a_source_ref(escape):
    """Exact-head review N-2: this previously mutated `demand.quota_class`
    and passed for the WRONG reason — rewriting the demand flips the
    recomputed state, so the PROVENANCE gate raised and the token law was
    never exercised at all (proved by reverting the token hunk: the old
    test still passed). `evidence[*].occupancy_source.ref` does not perturb
    the recomputation, so only the token law can refuse it."""
    payload = _selected_payload(worker_id="worker-a")
    payload["evidence"][0]["occupancy_source"]["ref"] = escape
    with pytest.raises(ValueError) as excinfo:
        eps.validate_placement_selection(payload)
    # the token law, not the provenance gate
    assert "must be a non-empty token" in str(excinfo.value)


# ---------------------------------------------------------------------------
# review 5086941171 BLOCKER 1 — CandidateEvidence's SourceRef token asymmetry
#
# PlacementCandidateFact validates owner + `.ref` + non-null `.observed_at`,
# and the wire validator does the same. CandidateEvidence only ran
# `_require_source_owner`, which checks type and owner but NEITHER token
# field — so a directly constructed evidence row could serialize a source
# value this module's own wire validator then refuses.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "field, owner",
    [
        ("occupancy_source", SourceOwner.RUNTIME_BINDING),
        ("capacity_source", SourceOwner.CAPACITY),
        ("closure_source", SourceOwner.CAPACITY),
    ],
)
@pytest.mark.parametrize("bad", ["has/slash", "has@at", "has\\back", "esc\x1b[31m"])
def test_candidate_evidence_applies_the_token_law_to_source_ref(field, owner, bad):
    with pytest.raises(ValueError):
        _evidence(**{field: SourceRef(
            owner=owner, ref=bad,
            observed_at="2026-09-01T00:00:00Z", freshness=Freshness.CURRENT,
        )})


@pytest.mark.parametrize(
    "field, owner",
    [
        ("occupancy_source", SourceOwner.RUNTIME_BINDING),
        ("capacity_source", SourceOwner.CAPACITY),
        ("closure_source", SourceOwner.CAPACITY),
    ],
)
@pytest.mark.parametrize("bad", ["2026-09-01T00:00:00Z/run", "2026-09-01T00:00:00Z@host"])
def test_candidate_evidence_applies_the_token_law_to_source_observed_at(field, owner, bad):
    with pytest.raises(ValueError):
        _evidence(**{field: SourceRef(
            owner=owner, ref="ref-a", observed_at=bad, freshness=Freshness.CURRENT,
        )})


def test_candidate_evidence_still_accepts_a_null_observed_at_under_unknown_freshness():
    """The token law applies to a PRESENT observed_at only — `SourceRef`
    legitimately allows `None` when freshness is UNKNOWN, and tightening
    must not turn that into a refusal."""
    assert _evidence(capacity_source=SourceRef(
        owner=SourceOwner.CAPACITY, ref="ref-a",
        observed_at=None, freshness=Freshness.UNKNOWN,
    )) is not None


# ---------------------------------------------------------------------------
# review 5086941171 BLOCKER 2 — unmasked source-freshness discriminators
#
# `_first_exclusion_reason` gate order is: CONTRADICTORY, EFFECT_UNKNOWN,
# occupancy STALE, occupancy UNKNOWN, capacity STALE, capacity UNKNOWN,
# capacity_state UNKNOWN, ... Each case below therefore keeps every EARLIER
# gate clean, so the gate under test is the one that actually fires — the
# previous stale-occupancy case was masked by EFFECT_UNKNOWN and proved
# nothing about the stale gate.
# ---------------------------------------------------------------------------

def _sole_exclusion(**candidate_kwargs):
    decision = eps.select_placement(
        responsibility=_responsibility(), demand=_demand(),
        candidates=(_candidate(worker_id="worker-a", **candidate_kwargs),),
    )
    assert len(decision.exclusions) == 1
    return decision, decision.exclusions[0].reason


def test_stale_occupancy_source_is_excluded_unmasked():
    decision, reason = _sole_exclusion(
        occupancy_freshness=Freshness.STALE,
        # every EARLIER gate deliberately clean
        occupancy=eps.OccupancyState.FREE, effect_state=EffectState.NONE,
    )
    assert reason is eps.ExclusionReason.STALE_OCCUPANCY_FACT
    assert decision.state is eps.SelectionState.STALE_EVIDENCE


def test_unknown_occupancy_source_freshness_is_excluded_unmasked():
    decision, reason = _sole_exclusion(
        occupancy_freshness=Freshness.UNKNOWN,
        occupancy=eps.OccupancyState.FREE, effect_state=EffectState.NONE,
    )
    assert reason is eps.ExclusionReason.UNKNOWN_FRESHNESS
    assert decision.state is eps.SelectionState.STALE_EVIDENCE


def test_unknown_capacity_source_freshness_is_excluded_unmasked():
    decision, reason = _sole_exclusion(
        capacity_freshness=Freshness.UNKNOWN,
        # occupancy gates all clean so the CAPACITY-source gate is what fires
        occupancy_freshness=Freshness.CURRENT,
        occupancy=eps.OccupancyState.FREE, effect_state=EffectState.NONE,
    )
    assert reason is eps.ExclusionReason.UNKNOWN_FRESHNESS
    assert decision.state is eps.SelectionState.STALE_EVIDENCE


def test_stale_capacity_source_is_excluded_unmasked():
    decision, reason = _sole_exclusion(
        capacity_freshness=Freshness.STALE, occupancy_freshness=Freshness.CURRENT,
        occupancy=eps.OccupancyState.FREE, effect_state=EffectState.NONE,
    )
    assert reason is eps.ExclusionReason.STALE_CAPACITY_FACT
    assert decision.state is eps.SelectionState.STALE_EVIDENCE


def test_freshness_discriminators_are_not_masked_by_an_earlier_gate():
    """Guards the masking failure itself: with EFFECT_UNKNOWN present the
    stale-occupancy reason is NOT reported, which is exactly why the old
    stale case proved nothing. If a future edit reorders the gates so the
    freshness cases stop being reachable, this pins the difference."""
    _, masked = _sole_exclusion(
        occupancy_freshness=Freshness.STALE, effect_state=EffectState.EFFECT_UNKNOWN,
    )
    assert masked is eps.ExclusionReason.EFFECT_UNKNOWN
    _, unmasked = _sole_exclusion(
        occupancy_freshness=Freshness.STALE, effect_state=EffectState.NONE,
    )
    assert unmasked is eps.ExclusionReason.STALE_OCCUPANCY_FACT
