from __future__ import annotations

import copy
import dataclasses
import hashlib
import inspect
import json
from collections.abc import Iterator, Sequence
from datetime import datetime, timezone

import pytest

from control_plane import executive_host_placement_preference as ehpp
from control_plane import executive_placement_preference as epp
from control_plane import executive_placement_selection as eps
from control_plane import executive_selected_physical_reservation as espr
from control_plane.executive_capacity_join import (
    PROVIDER_CAPACITY_SCHEMA,
    CapacityJoin,
    RegisteredCapacityJoin,
)
from control_plane.executive_capacity_observation import (
    OBSERVATION_LIFETIME_MS,
    OBSERVATION_SCHEMA,
    CapacityObservationError,
)
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
DECISION_TIME_MS = 1_800_000_000_000


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


def _registered_join(*, worker_id: str, host_ref: str) -> RegisteredCapacityJoin:
    source_digest = hashlib.sha256(f"source:{worker_id}".encode("utf-8")).hexdigest()
    return RegisteredCapacityJoin(
        worker_id=worker_id,
        quota_class="routine",
        provider="openai",
        capacity_join=CapacityJoin(
            host_ref=host_ref,
            capacity_capability_id=f"capability-{worker_id}",
            provider_capacity_schema=PROVIDER_CAPACITY_SCHEMA,
            worker_source_config_digest=source_digest,
        ),
    )


def _utc_seconds(timestamp_ms: int) -> str:
    return datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


def _capacity_observation(join: RegisteredCapacityJoin) -> dict:
    observed_at_ms = DECISION_TIME_MS - 1_000
    without_digest = {
        "schema_version": OBSERVATION_SCHEMA,
        "host_ref": join.capacity_join.host_ref,
        "capacity_capability_id": join.capacity_join.capacity_capability_id,
        "realm_metadata_valid": True,
        "credential_present": True,
        "credential_metadata_valid": True,
        "provider_binary_attested": True,
        "broker_generation_ready": True,
        "source_config_digest": join.capacity_join.worker_source_config_digest,
        "observed_at": _utc_seconds(observed_at_ms),
        "expires_at": _utc_seconds(observed_at_ms + OBSERVATION_LIFETIME_MS),
    }
    rendered = json.dumps(
        without_digest,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    return {
        **without_digest,
        "observation_digest": hashlib.sha256(rendered).hexdigest(),
    }


def _resign_capacity_observation(value: dict) -> dict:
    unsigned = copy.deepcopy(value)
    unsigned.pop("observation_digest", None)
    rendered = json.dumps(
        unsigned,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    return {
        **unsigned,
        "observation_digest": hashlib.sha256(rendered).hexdigest(),
    }


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
        "observed_at_ms": DECISION_TIME_MS - 5,
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
        "observed_at_ms": DECISION_TIME_MS - 2,
        "sample_window_ms": 3,
        "total_observation_window_ms": 8,
        "capacity_pool_ref": pool_ref,
        "hp0_sha256": hashlib.sha256(
            canonical_host_pressure_json(pressure)
        ).hexdigest(),
        "hp0_observed_at_ms": DECISION_TIME_MS - 5,
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
        "observed_at_ms": DECISION_TIME_MS - 2,
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
    placement_candidates = {
        candidate.worker_id: candidate for candidate in _selection_candidates()
    }
    result = {}
    for worker_id, (host_ref, boot_ref, _pool_ref, snapshot) in rows.items():
        registered_join = _registered_join(worker_id=worker_id, host_ref=host_ref)
        result[worker_id] = {
            "placement_candidate": placement_candidates[worker_id],
            "registered_join": registered_join,
            "capacity_observation": _capacity_observation(registered_join),
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




def _artifact_selection_inputs():
    inputs = _physical_inputs()
    qualified = _qualify(inputs)
    decision = _decision()
    artifact = ehpp.make_host_capacity_preference(
        decision=decision,
        candidates=qualified,
        generation=11,
    )
    selection = epp.select_placement_v2(
        responsibility=_responsibility(),
        demand=_demand(),
        candidates=_selection_candidates(),
        preference=artifact.preference,
        resolved_capacity_sources=artifact.resolved_capacity_sources(),
    )
    assert selection.state is eps.SelectionState.SELECTED
    assert selection.selected is not None
    return artifact, selection, inputs, qualified


class _TraversalCountingCandidates(Sequence[ehpp.QualifiedHostCandidate]):
    def __init__(self, values: Sequence[ehpp.QualifiedHostCandidate]) -> None:
        self._values = tuple(values)
        self.traversals = 0

    def __len__(self) -> int:
        return len(self._values)

    def __getitem__(self, index):
        return self._values[index]

    def __iter__(self) -> Iterator[ehpp.QualifiedHostCandidate]:
        self.traversals += 1
        return iter(self._values)


def _package():
    artifact, selection, inputs, qualified = _artifact_selection_inputs()
    winner = selection.selected["worker_id"]
    package = espr.make_selected_physical_reservation_package(
        selection=selection,
        artifact=artifact,
        qualified_candidates=qualified,
        **inputs[winner],
    )
    return package, artifact, selection, inputs, qualified


def test_package_creation_freezes_qualified_candidates_once() -> None:
    artifact, selection, inputs, qualified = _artifact_selection_inputs()
    winner_inputs = inputs[selection.selected["worker_id"]]
    candidates = _TraversalCountingCandidates(qualified)

    package = espr.make_selected_physical_reservation_package(
        selection=selection,
        artifact=artifact,
        qualified_candidates=candidates,
        **winner_inputs,
    )

    assert package.selected_worker_id == "worker-z-headroom"
    assert candidates.traversals == 1


def test_commit_evaluation_freezes_qualified_candidates_once() -> None:
    package, artifact, selection, inputs, qualified = _package()
    winner_inputs = inputs[package.selected_worker_id]
    candidates = _TraversalCountingCandidates(qualified)

    result = package.evaluate_for_commit(
        selection=selection,
        artifact=artifact,
        qualified_candidates=candidates,
        policy=winner_inputs["policy"],
        current_charges=winner_inputs["current_charges"],
        observations=winner_inputs["observations"],
        decision_time_ms=DECISION_TIME_MS,
    )

    assert result["selected_worker_id"] == "worker-z-headroom"
    assert candidates.traversals == 1


def test_package_binds_resolved_selection_to_exact_selected_physical_inputs() -> None:
    package, artifact, selection, inputs, qualified = _package()
    wire = package.to_dict()

    assert package.selected_worker_id == "worker-z-headroom"
    assert package.host_ref == HOST_M3
    assert package.boot_ref == BOOT_M3
    assert wire["schema"] == espr.PACKAGE_SCHEMA
    assert wire["selection_v2"] == selection.to_dict()
    assert wire["capacity_source"] == json.loads(artifact.source_bytes)
    assert wire["qualified_candidates"] == [
        candidate.to_dict() for candidate in sorted(qualified, key=lambda row: row.worker_id)
    ]
    assert wire["reservation_input"]["request"] == inputs["worker-z-headroom"]["request"]
    assert wire["reservation_input"]["decision_time_ms"] == DECISION_TIME_MS
    assert wire["selection_v2"]["selection_is_commitment"] is False
    assert espr.validate_selected_physical_reservation_package(wire) == wire


def test_commit_evaluation_reuses_existing_physical_owner_without_effect() -> None:
    package, artifact, selection, inputs, qualified = _package()
    winner_inputs = inputs[package.selected_worker_id]

    result = package.evaluate_for_commit(
        selection=selection,
        artifact=artifact,
        qualified_candidates=qualified,
        policy=winner_inputs["policy"],
        current_charges=winner_inputs["current_charges"],
        observations=winner_inputs["observations"],
        decision_time_ms=DECISION_TIME_MS,
    )

    assert set(result) == {
        "package_id",
        "selected_worker_id",
        "host_ref",
        "boot_ref",
        "request",
        "reservation",
    }
    assert result["package_id"] == package.package_id
    assert result["selected_worker_id"] == "worker-z-headroom"
    assert result["host_ref"] == HOST_M3
    assert result["boot_ref"] == BOOT_M3
    assert result["request"] == winner_inputs["request"]
    assert result["reservation"]["admitted"] is True
    assert result["reservation"]["code"] == "RESERVED"
    assert result["reservation"]["fresh_begin"] is False
    assert result["reservation"]["request_fingerprint"] == wire_candidate(
        package, "worker-z-headroom"
    )["request_fingerprint"]


def wire_candidate(package, worker_id: str) -> dict:
    return next(
        row for row in package.to_dict()["qualified_candidates"]
        if row["worker_id"] == worker_id
    )


def test_nonselected_candidate_movement_invalidates_prior_preference() -> None:
    package, artifact, selection, inputs, qualified = _package()
    moved = copy.deepcopy(inputs)
    snapshot = moved["worker-m-usable"]["observations"]["host_capacity_evidence"]["snapshot"]
    snapshot["pool_free_bytes"] -= 1
    moved["worker-m-usable"]["observations"]["host_capacity_evidence"]["snapshot_sha256"] = hashlib.sha256(
        canonical_host_capacity_json(snapshot)
    ).hexdigest()
    moved_qualified = _qualify(moved)
    winner_inputs = inputs[package.selected_worker_id]

    with pytest.raises(espr.SelectedPhysicalReservationError) as raised:
        package.evaluate_for_commit(
            selection=selection,
            artifact=artifact,
            qualified_candidates=moved_qualified,
            policy=winner_inputs["policy"],
            current_charges=winner_inputs["current_charges"],
            observations=winner_inputs["observations"],
            decision_time_ms=DECISION_TIME_MS,
        )
    assert raised.value.code == "QUALIFIED_CANDIDATES_MOVED"


@pytest.mark.parametrize(
    ("field", "code"),
    [
        ("policy", "POLICY_MOVED"),
        ("current_charges", "CURRENT_CHARGES_MOVED"),
        ("observations", "OBSERVATIONS_MOVED"),
    ],
)
def test_commit_inputs_must_match_selected_qualification(
    field: str, code: str
) -> None:
    package, artifact, selection, inputs, qualified = _package()
    winner_inputs = copy.deepcopy(inputs[package.selected_worker_id])
    if field == "policy":
        winner_inputs[field]["authority_receipt"] = "moved-authority"
    elif field == "current_charges":
        winner_inputs[field].append(
            {
                "capacity_pool_id": "memory",
                "remaining_charge": 1,
                "dimension": "memory_bytes",
            }
        )
    else:
        winner_inputs[field]["sequence"] += 1

    with pytest.raises(espr.SelectedPhysicalReservationError) as raised:
        package.evaluate_for_commit(
            selection=selection,
            artifact=artifact,
            qualified_candidates=qualified,
            policy=winner_inputs["policy"],
            current_charges=winner_inputs["current_charges"],
            observations=winner_inputs["observations"],
            decision_time_ms=DECISION_TIME_MS,
        )
    assert raised.value.code == code


def test_stale_evidence_refuses_at_commit_recheck() -> None:
    package, artifact, selection, inputs, qualified = _package()
    winner_inputs = inputs[package.selected_worker_id]

    with pytest.raises(PhysicalResourceRefusal) as raised:
        package.evaluate_for_commit(
            selection=selection,
            artifact=artifact,
            qualified_candidates=qualified,
            policy=winner_inputs["policy"],
            current_charges=winner_inputs["current_charges"],
            observations=winner_inputs["observations"],
            decision_time_ms=DECISION_TIME_MS + 100,
        )
    assert raised.value.code == "STALE_OBSERVATION"


def test_package_creation_rejects_selected_inputs_that_do_not_reproduce_winner() -> None:
    artifact, selection, inputs, qualified = _artifact_selection_inputs()
    wrong = copy.deepcopy(inputs["worker-m-usable"])

    with pytest.raises(espr.SelectedPhysicalReservationError) as raised:
        espr.make_selected_physical_reservation_package(
            selection=selection,
            artifact=artifact,
            qualified_candidates=qualified,
            **wrong,
        )
    assert raised.value.code == "SELECTED_INPUT_MISMATCH"


def test_unresolved_capacity_source_cannot_mint_package() -> None:
    artifact, _selection, inputs, qualified = _artifact_selection_inputs()
    unresolved = epp.select_placement_v2(
        responsibility=_responsibility(),
        demand=_demand(),
        candidates=_selection_candidates(),
        preference=artifact.preference,
        resolved_capacity_sources=None,
    )

    with pytest.raises(espr.SelectedPhysicalReservationError) as raised:
        espr.make_selected_physical_reservation_package(
            selection=unresolved,
            artifact=artifact,
            qualified_candidates=qualified,
            **inputs["worker-z-headroom"],
        )
    assert raised.value.code == "SELECTION_NOT_RESOLVED"


def test_caller_mutation_after_creation_cannot_change_package() -> None:
    artifact, selection, inputs, qualified = _artifact_selection_inputs()
    winner_inputs = inputs[selection.selected["worker_id"]]
    package = espr.make_selected_physical_reservation_package(
        selection=selection,
        artifact=artifact,
        qualified_candidates=qualified,
        **winner_inputs,
    )
    before = package.to_dict()

    winner_inputs["request"]["operation_key"] = "mutated"
    winner_inputs["policy"]["authority_receipt"] = "mutated"
    winner_inputs["observations"]["sequence"] = 999
    qualified = tuple(reversed(qualified))

    assert package.to_dict() == before


def test_closed_wire_and_package_id_reject_tamper() -> None:
    package, *_ = _package()
    tampered = package.to_dict()
    tampered["reservation_input"]["request"]["operation_key"] = "other-operation"

    with pytest.raises(espr.SelectedPhysicalReservationError) as raised:
        espr.validate_selected_physical_reservation_package(tampered)
    assert raised.value.code == "PACKAGE_ID_MISMATCH"


def test_evaluate_requires_same_resolved_selection_and_artifact() -> None:
    package, artifact, selection, inputs, qualified = _package()
    winner_inputs = inputs[package.selected_worker_id]
    moved_source = bytearray(artifact.source_bytes)
    moved_source[-1] = ord(" ")

    with pytest.raises((ehpp.HostPlacementPreferenceError, espr.SelectedPhysicalReservationError)):
        ehpp.HostCapacityPreferenceArtifact(
            preference=artifact.preference,
            source_bytes=bytes(moved_source),
        )

    abstained = epp.select_placement_v2(
        responsibility=_responsibility(),
        demand=_demand(),
        candidates=_selection_candidates(),
    )
    with pytest.raises(espr.SelectedPhysicalReservationError) as raised:
        package.evaluate_for_commit(
            selection=abstained,
            artifact=artifact,
            qualified_candidates=qualified,
            policy=winner_inputs["policy"],
            current_charges=winner_inputs["current_charges"],
            observations=winner_inputs["observations"],
            decision_time_ms=DECISION_TIME_MS,
        )
    assert raised.value.code == "SELECTION_MOVED"


def _resign_package(value: dict) -> dict:
    unsigned = copy.deepcopy(value)
    unsigned.pop("package_id", None)
    rendered = json.dumps(
        unsigned,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    return {**unsigned, "package_id": hashlib.sha256(rendered).hexdigest()}


def test_resigned_capacity_source_tamper_is_not_self_authorizing() -> None:
    package, *_ = _package()
    tampered = package.to_dict()
    tampered["capacity_source"]["generation"] += 1
    tampered = _resign_package(tampered)

    with pytest.raises(espr.SelectedPhysicalReservationError) as raised:
        espr.validate_selected_physical_reservation_package(tampered)
    assert raised.value.code == "PACKAGE_INVALID"


def test_resigned_selected_qualification_tamper_is_reproduced_and_refused() -> None:
    package, *_ = _package()
    tampered = package.to_dict()
    tampered["selected_qualification"]["request_fingerprint"] = "f" * 64
    tampered = _resign_package(tampered)

    with pytest.raises(espr.SelectedPhysicalReservationError) as raised:
        espr.validate_selected_physical_reservation_package(tampered)
    assert raised.value.code == "SELECTED_INPUT_MISMATCH"


def test_current_capacity_source_movement_refuses_even_before_reservation() -> None:
    package, _artifact, selection, inputs, qualified = _package()
    moved_inputs = copy.deepcopy(inputs)
    snapshot = moved_inputs["worker-a-overloaded"]["observations"]["host_capacity_evidence"]["snapshot"]
    snapshot["pool_free_bytes"] -= 1
    moved_inputs["worker-a-overloaded"]["observations"]["host_capacity_evidence"]["snapshot_sha256"] = hashlib.sha256(
        canonical_host_capacity_json(snapshot)
    ).hexdigest()
    moved_qualified = _qualify(moved_inputs)
    moved_artifact = ehpp.make_host_capacity_preference(
        decision=selection.base_v1,
        candidates=moved_qualified,
        generation=12,
    )
    winner_inputs = inputs[package.selected_worker_id]

    with pytest.raises(espr.SelectedPhysicalReservationError) as raised:
        package.evaluate_for_commit(
            selection=selection,
            artifact=moved_artifact,
            qualified_candidates=qualified,
            policy=winner_inputs["policy"],
            current_charges=winner_inputs["current_charges"],
            observations=winner_inputs["observations"],
            decision_time_ms=DECISION_TIME_MS,
        )
    assert raised.value.code == "CAPACITY_SOURCE_MOVED"


def test_candidate_input_order_is_not_a_hidden_preference() -> None:
    package, artifact, selection, inputs, qualified = _package()
    winner_inputs = inputs[package.selected_worker_id]

    result = package.evaluate_for_commit(
        selection=selection,
        artifact=artifact,
        qualified_candidates=tuple(reversed(qualified)),
        policy=winner_inputs["policy"],
        current_charges=winner_inputs["current_charges"],
        observations=winner_inputs["observations"],
        decision_time_ms=DECISION_TIME_MS,
    )
    assert result["selected_worker_id"] == "worker-z-headroom"


def test_package_constructor_cannot_be_called_without_producer_seal() -> None:
    with pytest.raises(espr.SelectedPhysicalReservationError) as raised:
        espr.SelectedPhysicalReservationPackage({}, _seal=object())
    assert raised.value.code == "UNSEALED_PACKAGE"


def test_resigned_physical_input_tamper_must_reproduce_selected_receipt() -> None:
    package, *_ = _package()
    tampered = package.to_dict()
    tampered["reservation_input"]["policy"]["authority_receipt"] = "other-authority"
    tampered = _resign_package(tampered)

    with pytest.raises(espr.SelectedPhysicalReservationError) as raised:
        espr.validate_selected_physical_reservation_package(tampered)
    assert raised.value.code == "SELECTED_INPUT_MISMATCH"
