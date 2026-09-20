from __future__ import annotations

import copy
import hashlib

import pytest

from control_plane import executive_host_placement_preference as ehpp
from control_plane import executive_placement_preference as epp
from control_plane import executive_placement_selection as eps
from control_plane.executive_host_capacity import canonical_host_capacity_json
from control_plane.executive_host_pressure import canonical_host_pressure_json
from control_plane.executive_physical_resources import PhysicalResourceRefusal
from control_plane.executive_steward import (
    CapacityState,
    EffectState,
    Freshness,
    ResponsibilityFact,
    Seat,
    SourceOwner,
    SourceRef,
)


HOST_M2 = "host-" + "1" * 64
HOST_M1 = "host-" + "2" * 64
HOST_M3 = "host-" + "3" * 64
BOOT_M2 = "boot-" + "4" * 64
BOOT_M1 = "boot-" + "5" * 64
BOOT_M3 = "boot-" + "6" * 64
POOL_M2 = "capacity-pool-" + "7" * 64
POOL_M1 = "capacity-pool-" + "8" * 64
POOL_M3 = "capacity-pool-" + "9" * 64
DECISION_TIME_MS = 100


def _source(
    owner: SourceOwner,
    ref: str,
    freshness: Freshness = Freshness.CURRENT,
) -> SourceRef:
    return SourceRef(
        owner=owner,
        ref=ref,
        observed_at="2026-09-19T22:00:00.000Z",
        freshness=freshness,
    )


def _responsibility() -> ResponsibilityFact:
    return ResponsibilityFact(
        responsibility_ref="WS:FLEET-FP2",
        title="Fleet host placement",
        accountable_seat=Seat.CEO,
        state="waiting_capacity",
        root_job_id=None,
        source=_source(SourceOwner.AGENT_OS, "agentos-fleet-fp2"),
    )


def _demand() -> eps.PlacementDemand:
    return eps.PlacementDemand(
        required_capabilities=frozenset({"worker"}),
        quota_class="routine",
        provider="openai",
        allowed_modes=frozenset({eps.PlacementMode.NEW_SESSION_MATERIALIZATION}),
    )


def _candidate(worker_id: str, account_label: str, observed_at_ms: int) -> eps.PlacementCandidateFact:
    return eps.PlacementCandidateFact(
        worker_id=worker_id,
        provider="openai",
        account_label=account_label,
        quota_class="routine",
        capabilities=frozenset({"worker"}),
        observed_at_ms=observed_at_ms,
        occupancy=eps.OccupancyState.FREE,
        occupancy_source=_source(SourceOwner.RUNTIME_BINDING, f"binding-{worker_id}"),
        capacity_state=CapacityState.AVAILABLE,
        capacity_source=_source(SourceOwner.CAPACITY, f"capacity-{worker_id}"),
        host_source_closure_proven=True,
        closure_source=_source(SourceOwner.CAPACITY, f"closure-{worker_id}"),
        effect_state=EffectState.NONE,
        mode=eps.PlacementMode.NEW_SESSION_MATERIALIZATION,
        creation_surface_accessible=True,
        session_creation_allowed=True,
    )


def _selection_candidates() -> tuple[eps.PlacementCandidateFact, ...]:
    # Lexical order deliberately conflicts with the current headroom order.
    return (
        _candidate("worker-a-overloaded", "m2-studio", 3000),
        _candidate("worker-m-usable", "m1-studio", 2000),
        _candidate("worker-z-headroom", "m3-macbook", 1000),
    )


def _decision() -> eps.PlacementSelectionDecision:
    decision = eps.select_placement(
        responsibility=_responsibility(),
        demand=_demand(),
        candidates=_selection_candidates(),
    )
    assert decision.state is eps.SelectionState.TIE_ABSTAINED
    return decision


def _memory_demand(boot_ref: str) -> dict:
    return {
        "dimension": "memory_bytes",
        "capacity_pool_id": "memory",
        "qualified_incremental_peak": 20,
        "window_binding": {
            "unit": "bytes",
            "window_ms": 1000,
            "baseline_id": "base-1",
            "boot_id": boot_ref,
        },
    }


def _request(*, host_ref: str, boot_ref: str, worker_id: str) -> dict:
    return {
        "operation_key": f"fleet-placement-{worker_id}",
        "host_id": host_ref,
        "boot_id": boot_ref,
        "owner_id": "fleet-capacity",
        "carrier_id": "fleet-fp2",
        "command_id": f"physical:fleet:{worker_id}",
        "source_binding": {
            "commit_sha": "a" * 40,
            "helper_sha256": "b" * 64,
            "common_git_store": {
                "realpath": "/synthetic/git",
                "device": 1,
                "inode": 2,
            },
            "destination": {
                "realpath": f"/synthetic/{worker_id}",
                "device": 3,
                "capacity_pool_id": "memory",
            },
        },
        "policy_binding": {"revision": "fleet-policy-1", "sha256": "c" * 64},
        "caller_binding": {
            "session_id": "fleet-session",
            "pid": 123,
            "start_id": "fleet-start",
        },
        "acquisition_time_ms": DECISION_TIME_MS,
        "phases": [
            {
                "phase_key": "worker",
                "profile": "ROUTINE_WORKER",
                "duration_ms": 1000,
                "effect_scope": ["provider_worker_effect"],
                "demands": [_memory_demand(boot_ref)],
            }
        ],
    }


def _host_qualification(*, host_ref: str, boot_ref: str, pool_ref: str) -> dict:
    return {
        "host_id": host_ref,
        "boot_id": boot_ref,
        "capacity_pool_ref": pool_ref,
        "qualification_revision": "host-qualification-1",
        "qualification_evidence": ["fleet-host-evidence"],
        "physical_pools": [
            {"capacity_pool_id": "memory", "protected_reserve": 10}
        ],
        "profiles": [
            {
                "profile": "ROUTINE_WORKER",
                "qualified_duration_ms": 1000,
                "qualification_evidence": ["fleet-profile-evidence"],
                "effect_scope": ["provider_worker_effect"],
                "qualified_demands": [_memory_demand(boot_ref)],
            }
        ],
        "windows": {
            "cpu_window_ms": 1000,
            "io_window_ms": 1000,
            "normalization_evidence": "fleet-test",
        },
        "limits": {
            "cpu_budget_us": 1_000_000,
            "cpu_protected_us": 1,
            "memory_budget_bytes": 1_000_000,
            "memory_protected_bytes": 10,
            "internal_protected_bytes": 10,
            "external_protected_bytes": 10,
            "io_budget_bytes": 1_000_000,
            "io_protected_bytes": 1,
            "max_heavy_phases": 8,
        },
    }


def _fleet_policy() -> dict:
    return {
        "schema": "mastermind.physical_resource_policy.v2",
        "production_armed": True,
        "qualification": "SYNTHETIC_TEST_ONLY",
        "policy_revision": "fleet-policy-1",
        "authority_receipt": "fleet-authority",
        "qualification_evidence": ["fleet-multihost-evidence"],
        "canonical_runtime": {
            "runtime_id": "runtime-control",
            "host_id": "host-" + "e" * 64,
            "boot_id": "boot-" + "f" * 64,
            "endpoint": "synthetic://control-runtime",
            "database_identity": "fleet-db",
            "schema_identity": "fleet-schema",
        },
        "allowed_callers": [
            {
                "owner_id": "fleet-capacity",
                "carrier_id": "fleet-fp2",
                "session_id": "fleet-session",
            }
        ],
        "host_qualifications": [
            _host_qualification(host_ref=HOST_M2, boot_ref=BOOT_M2, pool_ref=POOL_M2),
            _host_qualification(host_ref=HOST_M1, boot_ref=BOOT_M1, pool_ref=POOL_M1),
            _host_qualification(host_ref=HOST_M3, boot_ref=BOOT_M3, pool_ref=POOL_M3),
        ],
        "freshness": {
            "sample_max_age_ms": 20,
            "sample_cadence_ms": 5,
            "decision_to_effect_max_ms": 10,
        },
        "waits": {"service_request_max_ms": 20, "database_lock_max_ms": 15},
        "recovery": {
            "reservation_horizon_ms": 100,
            "reconciliation_interval_ms": 10,
        },
    }


def _pressure_snapshot(
    *, host_ref: str, boot_ref: str, logical_cpu_count: int, load1_milli: int
) -> dict:
    return {
        "schema": "mastermind.host_pressure_snapshot/v1",
        "host_ref": host_ref,
        "boot_ref": boot_ref,
        "observed_at_ms": 95,
        "sample_window_ms": 5,
        "logical_cpu_count": logical_cpu_count,
        "load1_milli": load1_milli,
        "load_ratio_milli": load1_milli // logical_cpu_count,
        "fseventsd_process_count": 1,
        "fseventsd_cpu_milli_pct": 100,
        "fseventsd_rss_bytes": 4096,
        "telemetry_status": "COMPLETE",
        "unknown_fields": [],
    }


def _capacity_snapshot(
    *,
    host_ref: str,
    boot_ref: str,
    pool_ref: str,
    logical_cpu_count: int,
    load1_milli: int,
    physical_memory_bytes: int,
    free_pages: int,
    inactive_pages: int,
    speculative_pages: int,
    compressed_pages: int,
    swap_used_bytes: int,
    pool_free_bytes: int,
) -> dict:
    pressure = _pressure_snapshot(
        host_ref=host_ref,
        boot_ref=boot_ref,
        logical_cpu_count=logical_cpu_count,
        load1_milli=load1_milli,
    )
    return {
        "schema": "mastermind.host_capacity_snapshot/v1",
        "host_ref": host_ref,
        "boot_ref": boot_ref,
        "observed_at_ms": 98,
        "sample_window_ms": 3,
        "total_observation_window_ms": 8,
        "capacity_pool_ref": pool_ref,
        "hp0_sha256": hashlib.sha256(
            canonical_host_pressure_json(pressure)
        ).hexdigest(),
        "hp0_observed_at_ms": 95,
        "hp0_sample_window_ms": 5,
        "logical_cpu_count": logical_cpu_count,
        "load1_milli": load1_milli,
        "load_ratio_milli": load1_milli // logical_cpu_count,
        "hp0_telemetry_status": "COMPLETE",
        "physical_memory_bytes": physical_memory_bytes,
        "vm_page_size_bytes": 4096,
        "vm_free_pages": free_pages,
        "vm_inactive_pages": inactive_pages,
        "vm_speculative_pages": speculative_pages,
        "vm_compressed_pages": compressed_pages,
        "swap_total_bytes": 4 * 1024**3,
        "swap_used_bytes": swap_used_bytes,
        "pool_total_bytes": 500 * 1024**3,
        "pool_free_bytes": pool_free_bytes,
        "telemetry_status": "COMPLETE",
        "unknown_fields": [],
    }


def _observations(*, host_ref: str, boot_ref: str, snapshot: dict) -> dict:
    return {
        "host_id": host_ref,
        "boot_id": boot_ref,
        "policy_revision": "fleet-policy-1",
        "sequence": 7,
        "required_sequence": 7,
        "observed_at_ms": 98,
        "pools": {
            "memory": {
                "available": 100,
                "baseline_id": "base-1",
                "included_materializations": [],
            }
        },
        "host_capacity_evidence": {
            "snapshot": copy.deepcopy(snapshot),
            "snapshot_sha256": hashlib.sha256(
                canonical_host_capacity_json(snapshot)
            ).hexdigest(),
        },
    }


def _physical_inputs() -> dict[str, dict]:
    policy = _fleet_policy()
    rows = {
        "worker-a-overloaded": (
            HOST_M2,
            BOOT_M2,
            POOL_M2,
            _capacity_snapshot(
                host_ref=HOST_M2,
                boot_ref=BOOT_M2,
                pool_ref=POOL_M2,
                logical_cpu_count=24,
                load1_milli=127_000,
                physical_memory_bytes=64 * 1024**3,
                free_pages=100_000,
                inactive_pages=50_000,
                speculative_pages=10_000,
                compressed_pages=800_000,
                swap_used_bytes=3 * 1024**3,
                pool_free_bytes=100 * 1024**3,
            ),
        ),
        "worker-m-usable": (
            HOST_M1,
            BOOT_M1,
            POOL_M1,
            _capacity_snapshot(
                host_ref=HOST_M1,
                boot_ref=BOOT_M1,
                pool_ref=POOL_M1,
                logical_cpu_count=10,
                load1_milli=5_800,
                physical_memory_bytes=32 * 1024**3,
                free_pages=700_000,
                inactive_pages=300_000,
                speculative_pages=100_000,
                compressed_pages=100_000,
                swap_used_bytes=512 * 1024**2,
                pool_free_bytes=250 * 1024**3,
            ),
        ),
        "worker-z-headroom": (
            HOST_M3,
            BOOT_M3,
            POOL_M3,
            _capacity_snapshot(
                host_ref=HOST_M3,
                boot_ref=BOOT_M3,
                pool_ref=POOL_M3,
                logical_cpu_count=12,
                load1_milli=3_000,
                physical_memory_bytes=36 * 1024**3,
                free_pages=900_000,
                inactive_pages=400_000,
                speculative_pages=150_000,
                compressed_pages=80_000,
                swap_used_bytes=256 * 1024**2,
                pool_free_bytes=300 * 1024**3,
            ),
        ),
    }
    result = {}
    for worker_id, (host_ref, boot_ref, _pool_ref, snapshot) in rows.items():
        result[worker_id] = {
            "worker_id": worker_id,
            "request": _request(
                host_ref=host_ref, boot_ref=boot_ref, worker_id=worker_id
            ),
            "policy": copy.deepcopy(policy),
            "current_charges": [],
            "observations": _observations(
                host_ref=host_ref, boot_ref=boot_ref, snapshot=snapshot
            ),
            "decision_time_ms": DECISION_TIME_MS,
        }
    return result


def _qualify(inputs: dict | None = None) -> tuple[ehpp.QualifiedHostCandidate, ...]:
    rows = inputs or _physical_inputs()
    return tuple(ehpp.qualify_host_candidate(**rows[key]) for key in sorted(rows))


def test_current_host_evidence_prefers_headroom_without_hostname_or_worker_order() -> None:
    qualified = _qualify()
    preference = ehpp.make_host_capacity_preference(
        decision=_decision(),
        candidates=qualified,
        generation=11,
    )
    assert preference.preference_order == (
        "worker-z-headroom",
        "worker-m-usable",
        "worker-a-overloaded",
    )
    assert preference.preference_order != tuple(sorted(preference.preference_order))
    assert preference.capacity_source.owner is SourceOwner.CAPACITY
    assert preference.capacity_source.freshness is Freshness.CURRENT
    assert preference.capacity_source.ref.startswith("host-placement-")
    assert HOST_M2 not in preference.capacity_source.ref
    assert HOST_M1 not in preference.capacity_source.ref
    assert HOST_M3 not in preference.capacity_source.ref


def test_host_preference_resolves_only_the_existing_v1_tie() -> None:
    candidates = _selection_candidates()
    decision = _decision()
    preference = ehpp.make_host_capacity_preference(
        decision=decision,
        candidates=_qualify(),
        generation=11,
    )
    selected = epp.select_placement_v2(
        responsibility=_responsibility(),
        demand=_demand(),
        candidates=candidates,
        preference=preference,
    )
    assert selected.state is eps.SelectionState.SELECTED
    assert selected.selected["worker_id"] == "worker-z-headroom"
    assert selected.to_dict()["selection_is_commitment"] is False


def test_qualification_uses_existing_physical_reserve_and_rejects_insufficient_host() -> None:
    inputs = _physical_inputs()
    inputs["worker-z-headroom"]["observations"]["pools"]["memory"]["available"] = 25
    with pytest.raises(PhysicalResourceRefusal) as error:
        ehpp.qualify_host_candidate(**inputs["worker-z-headroom"])
    assert error.value.code == "INSUFFICIENT_CAPACITY"


def test_stale_host_capacity_refuses_before_preference() -> None:
    inputs = _physical_inputs()["worker-z-headroom"]
    inputs["observations"]["observed_at_ms"] = 130
    inputs["decision_time_ms"] = 130
    with pytest.raises(PhysicalResourceRefusal) as error:
        ehpp.qualify_host_candidate(**inputs)
    assert error.value.code == "HOST_CAPACITY_STALE"


def test_evidence_movement_invalidates_prior_preference_even_when_order_is_unchanged() -> None:
    decision = _decision()
    old_inputs = _physical_inputs()
    old_candidates = _qualify(old_inputs)
    old = ehpp.make_host_capacity_preference(
        decision=decision,
        candidates=old_candidates,
        generation=11,
    )

    moved_inputs = _physical_inputs()
    for value in moved_inputs.values():
        value["observations"]["sequence"] = 8
        value["observations"]["required_sequence"] = 8
    moved_candidates = _qualify(moved_inputs)
    replacement = ehpp.make_host_capacity_preference(
        decision=decision,
        candidates=moved_candidates,
        generation=12,
    )
    assert replacement.preference_order == old.preference_order
    assert replacement.capacity_source.ref != old.capacity_source.ref
    assert replacement.receipt_id != old.receipt_id
    with pytest.raises(ehpp.HostPlacementPreferenceError) as error:
        ehpp.validate_current_host_capacity_preference(
            preference=old,
            decision=decision,
            candidates=moved_candidates,
            generation=12,
        )
    assert error.value.code == "PREFERENCE_NOT_CURRENT"


def test_equal_host_scores_require_current_capacity_owned_tie_evidence() -> None:
    inputs = _physical_inputs()
    source = inputs["worker-z-headroom"]["observations"]["host_capacity_evidence"]
    for worker_id in ("worker-a-overloaded", "worker-m-usable"):
        target = inputs[worker_id]["observations"]["host_capacity_evidence"]
        snapshot = copy.deepcopy(source["snapshot"])
        request = inputs[worker_id]["request"]
        snapshot["host_ref"] = request["host_id"]
        snapshot["boot_ref"] = request["boot_id"]
        snapshot["capacity_pool_ref"] = next(
            row["capacity_pool_ref"]
            for row in inputs[worker_id]["policy"]["host_qualifications"]
            if row["host_id"] == request["host_id"]
        )
        target["snapshot"] = snapshot
        target["snapshot_sha256"] = hashlib.sha256(
            canonical_host_capacity_json(snapshot)
        ).hexdigest()
    qualified = _qualify(inputs)
    with pytest.raises(ehpp.HostPlacementPreferenceError) as error:
        ehpp.make_host_capacity_preference(
            decision=_decision(),
            candidates=qualified,
            generation=13,
        )
    assert error.value.code == "HOST_SCORE_TIE_UNRESOLVED"

    tie_source = _source(SourceOwner.CAPACITY, "capacity-fairness-generation-13")
    preference = ehpp.make_host_capacity_preference(
        decision=_decision(),
        candidates=qualified,
        generation=13,
        capacity_tie_order=(
            "worker-m-usable",
            "worker-z-headroom",
            "worker-a-overloaded",
        ),
        capacity_tie_source=tie_source,
    )
    assert preference.preference_order == (
        "worker-m-usable",
        "worker-z-headroom",
        "worker-a-overloaded",
    )


def test_tie_evidence_cannot_expand_capacity_authority() -> None:
    inputs = _physical_inputs()
    source_snapshot = inputs["worker-z-headroom"]["observations"][
        "host_capacity_evidence"
    ]["snapshot"]
    for worker_id in ("worker-a-overloaded", "worker-m-usable"):
        request = inputs[worker_id]["request"]
        snapshot = copy.deepcopy(source_snapshot)
        snapshot["host_ref"] = request["host_id"]
        snapshot["boot_ref"] = request["boot_id"]
        snapshot["capacity_pool_ref"] = next(
            row["capacity_pool_ref"]
            for row in inputs[worker_id]["policy"]["host_qualifications"]
            if row["host_id"] == request["host_id"]
        )
        evidence = inputs[worker_id]["observations"]["host_capacity_evidence"]
        evidence["snapshot"] = snapshot
        evidence["snapshot_sha256"] = hashlib.sha256(
            canonical_host_capacity_json(snapshot)
        ).hexdigest()
    qualified = _qualify(inputs)
    order = ("worker-z-headroom", "worker-m-usable", "worker-a-overloaded")
    for source in (
        _source(SourceOwner.EXECUTIVE_OS, "not-capacity"),
        _source(SourceOwner.CAPACITY, "stale-capacity", Freshness.STALE),
    ):
        with pytest.raises(ehpp.HostPlacementPreferenceError) as error:
            ehpp.make_host_capacity_preference(
                decision=_decision(),
                candidates=qualified,
                generation=13,
                capacity_tie_order=order,
                capacity_tie_source=source,
            )
        assert error.value.code == "TIE_SOURCE_INVALID"


def test_candidate_set_must_exactly_match_the_existing_v1_tie() -> None:
    with pytest.raises(ehpp.HostPlacementPreferenceError) as error:
        ehpp.make_host_capacity_preference(
            decision=_decision(),
            candidates=_qualify()[:-1],
            generation=11,
        )
    assert error.value.code == "CANDIDATE_SET_MISMATCH"


def test_qualification_freezes_one_evidence_snapshot() -> None:
    inputs = _physical_inputs()["worker-z-headroom"]
    qualified = ehpp.qualify_host_candidate(**inputs)
    before = qualified.to_dict()
    inputs["observations"]["sequence"] = 999
    inputs["observations"]["host_capacity_evidence"]["snapshot"][
        "load1_milli"
    ] = 999_999
    assert qualified.to_dict() == before


def test_unused_tie_order_is_refused_instead_of_becoming_hidden_policy() -> None:
    with pytest.raises(ehpp.HostPlacementPreferenceError) as error:
        ehpp.make_host_capacity_preference(
            decision=_decision(),
            candidates=_qualify(),
            generation=11,
            capacity_tie_order=(
                "worker-z-headroom",
                "worker-m-usable",
                "worker-a-overloaded",
            ),
            capacity_tie_source=_source(
                SourceOwner.CAPACITY, "capacity-fairness-unused"
            ),
        )
    assert error.value.code == "TIE_SOURCE_UNUSED"
