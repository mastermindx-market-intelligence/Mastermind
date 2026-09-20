from __future__ import annotations

import copy
import dataclasses
import hashlib
import inspect
import json
from datetime import datetime, timezone

import pytest

from control_plane import executive_host_placement_preference as ehpp
from control_plane import executive_placement_preference as epp
from control_plane import executive_placement_selection as eps
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


def test_host_preference_emits_resolvable_content_addressed_artifact() -> None:
    artifact = ehpp.make_host_capacity_preference(
        decision=_decision(),
        candidates=_qualify(),
        generation=11,
    )
    assert isinstance(artifact, ehpp.HostCapacityPreferenceArtifact)
    source_ref = artifact.preference.capacity_source.ref
    assert source_ref == (
        "capacity-source-sha256:"
        + hashlib.sha256(artifact.source_bytes).hexdigest()
    )
    assert artifact.resolved_capacity_sources() == {
        source_ref: artifact.source_bytes
    }


def test_source_artifact_rejects_hidden_policy_fields() -> None:
    artifact = ehpp.make_host_capacity_preference(
        decision=_decision(),
        candidates=_qualify(),
        generation=11,
    )
    source = json.loads(artifact.source_bytes)
    source["hidden_hostname_policy"] = "m3-before-m1-before-m2"
    tampered_bytes = json.dumps(
        source,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    tampered_source = SourceRef(
        owner=SourceOwner.CAPACITY,
        ref=(
            "capacity-source-sha256:"
            + hashlib.sha256(tampered_bytes).hexdigest()
        ),
        observed_at=artifact.preference.capacity_source.observed_at,
        freshness=Freshness.CURRENT,
    )
    tampered_preference = epp.make_capacity_preference(
        decision=_decision(),
        preference_order=artifact.preference.preference_order,
        capacity_source=tampered_source,
        generation=11,
    )
    with pytest.raises(ehpp.HostPlacementPreferenceError) as error:
        ehpp.HostCapacityPreferenceArtifact(
            preference=tampered_preference,
            source_bytes=tampered_bytes,
        )
    assert error.value.code == "SOURCE_ARTIFACT_INVALID"


def test_source_artifact_binds_preference_observation_time() -> None:
    decision = _decision()
    artifact = ehpp.make_host_capacity_preference(
        decision=decision,
        candidates=_qualify(),
        generation=11,
    )
    moved_source = SourceRef(
        owner=SourceOwner.CAPACITY,
        ref=artifact.preference.capacity_source.ref,
        observed_at="ms-999",
        freshness=Freshness.CURRENT,
    )
    moved_preference = epp.make_capacity_preference(
        decision=decision,
        preference_order=artifact.preference.preference_order,
        capacity_source=moved_source,
        generation=11,
    )
    with pytest.raises(
        ehpp.HostPlacementPreferenceError,
        match="SOURCE_ARTIFACT_PREFERENCE_MISMATCH",
    ) as error:
        ehpp.HostCapacityPreferenceArtifact(
            preference=moved_preference,
            source_bytes=artifact.source_bytes,
        )
    assert error.value.code == "SOURCE_ARTIFACT_PREFERENCE_MISMATCH"


def test_source_artifact_rejects_order_not_derived_from_scores() -> None:
    decision = _decision()
    artifact = ehpp.make_host_capacity_preference(
        decision=decision,
        candidates=_qualify(),
        generation=11,
    )
    source = json.loads(artifact.source_bytes)
    source["preference_order"] = list(reversed(source["preference_order"]))
    tampered_bytes = json.dumps(
        source,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    tampered_source = SourceRef(
        owner=SourceOwner.CAPACITY,
        ref=(
            "capacity-source-sha256:"
            + hashlib.sha256(tampered_bytes).hexdigest()
        ),
        observed_at=artifact.preference.capacity_source.observed_at,
        freshness=Freshness.CURRENT,
    )
    tampered_preference = epp.make_capacity_preference(
        decision=decision,
        preference_order=tuple(source["preference_order"]),
        capacity_source=tampered_source,
        generation=11,
    )
    with pytest.raises(
        ehpp.HostPlacementPreferenceError,
        match="SOURCE_ARTIFACT_ORDER_MISMATCH",
    ) as error:
        ehpp.HostCapacityPreferenceArtifact(
            preference=tampered_preference,
            source_bytes=tampered_bytes,
        )
    assert error.value.code == "SOURCE_ARTIFACT_ORDER_MISMATCH"


def test_source_artifact_rejects_candidate_receipt_mismatch() -> None:
    decision = _decision()
    artifact = ehpp.make_host_capacity_preference(
        decision=decision,
        candidates=_qualify(),
        generation=11,
    )
    source = json.loads(artifact.source_bytes)
    source["candidates"][0]["score"][0] += 1
    tampered_bytes = json.dumps(
        source,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    tampered_source = SourceRef(
        owner=SourceOwner.CAPACITY,
        ref=(
            "capacity-source-sha256:"
            + hashlib.sha256(tampered_bytes).hexdigest()
        ),
        observed_at=artifact.preference.capacity_source.observed_at,
        freshness=Freshness.CURRENT,
    )
    tampered_preference = epp.make_capacity_preference(
        decision=decision,
        preference_order=artifact.preference.preference_order,
        capacity_source=tampered_source,
        generation=11,
    )
    with pytest.raises(
        ehpp.HostPlacementPreferenceError,
        match="QUALIFICATION_RECEIPT_MISMATCH",
    ) as error:
        ehpp.HostCapacityPreferenceArtifact(
            preference=tampered_preference,
            source_bytes=tampered_bytes,
        )
    assert error.value.code == "QUALIFICATION_RECEIPT_MISMATCH"


@pytest.mark.parametrize("resolved", [None, "moved"])
def test_missing_or_moved_source_preserves_v1_abstention(resolved: str | None) -> None:
    candidates = _selection_candidates()
    artifact = ehpp.make_host_capacity_preference(
        decision=_decision(),
        candidates=_qualify(),
        generation=11,
    )
    source_ref = artifact.preference.capacity_source.ref
    resolved_sources = (
        {} if resolved is None else {source_ref: b"moved-source"}
    )
    result = epp.select_placement_v2(
        responsibility=_responsibility(),
        demand=_demand(),
        candidates=candidates,
        preference=artifact.preference,
        resolved_capacity_sources=resolved_sources,
    )
    assert result.state is eps.SelectionState.TIE_ABSTAINED
    assert result.selected is None
    assert result.to_dict()["preference_admissibility"] == "inadmissible"
    assert result.to_dict()["preference_refusal"] == {
        "code": epp.CAPACITY_SOURCE_UNRESOLVED,
        "source_ref": source_ref,
    }


def test_registered_join_must_match_candidate_and_physical_host() -> None:
    candidate_mismatch = _physical_inputs()["worker-z-headroom"]
    candidate_mismatch["registered_join"] = _registered_join(
        worker_id="worker-other", host_ref=HOST_M3
    )
    candidate_mismatch["capacity_observation"] = _capacity_observation(
        candidate_mismatch["registered_join"]
    )
    with pytest.raises(ehpp.HostPlacementPreferenceError) as error:
        ehpp.qualify_host_candidate(**candidate_mismatch)
    assert error.value.code == "CANDIDATE_JOIN_MISMATCH"

    host_mismatch = _physical_inputs()["worker-z-headroom"]
    host_mismatch["registered_join"] = _registered_join(
        worker_id="worker-z-headroom", host_ref=HOST_M1
    )
    host_mismatch["capacity_observation"] = _capacity_observation(
        host_mismatch["registered_join"]
    )
    with pytest.raises(ehpp.HostPlacementPreferenceError) as error:
        ehpp.qualify_host_candidate(**host_mismatch)
    assert error.value.code == "CAPACITY_JOIN_HOST_MISMATCH"


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        ("generation_unready", "CAPACITY_OBSERVE_GENERATION_UNREADY"),
        ("stale", "CAPACITY_OBSERVE_STALE"),
    ],
)
def test_worker_capacity_observation_must_be_ready_and_current(
    mutation: str, expected_code: str
) -> None:
    inputs = _physical_inputs()["worker-z-headroom"]
    observation = copy.deepcopy(inputs["capacity_observation"])
    if mutation == "generation_unready":
        observation["broker_generation_ready"] = False
    else:
        observed_at_ms = DECISION_TIME_MS - 30_000
        observation["observed_at"] = _utc_seconds(observed_at_ms)
        observation["expires_at"] = _utc_seconds(
            observed_at_ms + OBSERVATION_LIFETIME_MS
        )
    inputs["capacity_observation"] = _resign_capacity_observation(observation)
    with pytest.raises(CapacityObservationError) as error:
        ehpp.qualify_host_candidate(**inputs)
    assert error.value.code == expected_code


def test_qualified_candidate_rejects_score_or_evidence_tamper() -> None:
    qualified = _qualify()[0]
    for changes in (
        {"score": tuple(value + 1 for value in qualified.score)},
        {"physical_evidence_digest": "f" * 64},
    ):
        with pytest.raises(
            ehpp.HostPlacementPreferenceError,
            match="QUALIFICATION_RECEIPT_MISMATCH",
        ) as error:
            dataclasses.replace(qualified, **changes)
        assert error.value.code == "QUALIFICATION_RECEIPT_MISMATCH"


def test_qualified_identity_is_rechecked_against_the_exact_v1_decision() -> None:
    inputs = _physical_inputs()
    row = inputs["worker-a-overloaded"]
    row["placement_candidate"] = dataclasses.replace(
        row["placement_candidate"], provider="anthropic"
    )
    row["registered_join"] = RegisteredCapacityJoin(
        worker_id=row["registered_join"].worker_id,
        quota_class=row["registered_join"].quota_class,
        provider="anthropic",
        capacity_join=row["registered_join"].capacity_join,
    )
    qualified = list(_qualify(inputs))
    with pytest.raises(ehpp.HostPlacementPreferenceError) as error:
        ehpp.make_host_capacity_preference(
            decision=_decision(),
            candidates=tuple(qualified),
            generation=11,
        )
    assert error.value.code == "CANDIDATE_IDENTITY_MISMATCH"


def test_current_host_evidence_prefers_headroom_without_hostname_or_worker_order() -> None:
    qualified = _qualify()
    artifact = ehpp.make_host_capacity_preference(
        decision=_decision(),
        candidates=qualified,
        generation=11,
    )
    preference = artifact.preference
    assert preference.preference_order == (
        "worker-z-headroom",
        "worker-m-usable",
        "worker-a-overloaded",
    )
    assert preference.preference_order != tuple(sorted(preference.preference_order))
    assert preference.capacity_source.owner is SourceOwner.CAPACITY
    assert preference.capacity_source.freshness is Freshness.CURRENT
    assert preference.capacity_source.ref.startswith("capacity-source-sha256:")
    assert HOST_M2 not in preference.capacity_source.ref
    assert HOST_M1 not in preference.capacity_source.ref
    assert HOST_M3 not in preference.capacity_source.ref


def test_host_preference_resolves_only_the_existing_v1_tie() -> None:
    candidates = _selection_candidates()
    decision = _decision()
    artifact = ehpp.make_host_capacity_preference(
        decision=decision,
        candidates=_qualify(),
        generation=11,
    )
    selected = epp.select_placement_v2(
        responsibility=_responsibility(),
        demand=_demand(),
        candidates=candidates,
        preference=artifact.preference,
        resolved_capacity_sources=artifact.resolved_capacity_sources(),
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
    inputs["observations"]["observed_at_ms"] = DECISION_TIME_MS + 30
    inputs["decision_time_ms"] = DECISION_TIME_MS + 30
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
    assert replacement.preference.preference_order == old.preference.preference_order
    assert (
        replacement.preference.capacity_source.ref
        != old.preference.capacity_source.ref
    )
    assert replacement.preference.receipt_id != old.preference.receipt_id
    assert replacement.source_bytes != old.source_bytes
    with pytest.raises(ehpp.HostPlacementPreferenceError) as error:
        ehpp.validate_current_host_capacity_preference(
            artifact=old,
            decision=decision,
            candidates=moved_candidates,
            generation=12,
        )
    assert error.value.code == "PREFERENCE_NOT_CURRENT"


def test_equal_host_scores_have_no_secondary_tie_plane() -> None:
    parameters = inspect.signature(ehpp.make_host_capacity_preference).parameters
    assert "capacity_tie_order" not in parameters
    assert "capacity_tie_source" not in parameters


def test_equal_host_scores_refuse_without_hidden_fallback() -> None:
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

def test_candidate_set_refuses_duplicate_registered_capacity_identity() -> None:
    inputs = _physical_inputs()
    source = inputs["worker-z-headroom"]
    duplicate = inputs["worker-m-usable"]
    duplicate["registered_join"] = RegisteredCapacityJoin(
        worker_id="worker-m-usable",
        quota_class=source["registered_join"].quota_class,
        provider=source["registered_join"].provider,
        capacity_join=source["registered_join"].capacity_join,
    )
    duplicate["capacity_observation"] = copy.deepcopy(
        source["capacity_observation"]
    )
    duplicate["request"] = copy.deepcopy(source["request"])
    duplicate["policy"] = copy.deepcopy(source["policy"])
    duplicate["current_charges"] = copy.deepcopy(source["current_charges"])
    duplicate["observations"] = copy.deepcopy(source["observations"])

    # Keep both individual qualifications valid while making the duplicate
    # physical identity produce a different score. The set-level owner must
    # reject the duplicate rather than rank two views of one capability.
    snapshot = duplicate["observations"]["host_capacity_evidence"]["snapshot"]
    snapshot["load1_milli"] = 6_000
    snapshot["load_ratio_milli"] = 6_000 // snapshot["logical_cpu_count"]
    duplicate["observations"]["host_capacity_evidence"][
        "snapshot_sha256"
    ] = hashlib.sha256(canonical_host_capacity_json(snapshot)).hexdigest()

    qualified = _qualify(inputs)
    with pytest.raises(ehpp.HostPlacementPreferenceError) as error:
        ehpp.make_host_capacity_preference(
            decision=_decision(),
            candidates=qualified,
            generation=14,
        )
    assert error.value.code == "DUPLICATE_CAPACITY_JOIN"
