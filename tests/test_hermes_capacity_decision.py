"""H24-02 fixture proof only: no providers, claims, host sampling or installs."""
from __future__ import annotations

import copy
import dataclasses as dc
import hashlib
import itertools
import json
from concurrent.futures import ThreadPoolExecutor

import unittest
from unittest import mock
import tempfile
from pathlib import Path

from control_plane import hermes_capacity_decision as h
from control_plane import executive_placement_selection as ps
from control_plane.executive_capacity_join import CapacityJoin, RegisteredCapacityJoin
from control_plane.executive_host_capacity import canonical_host_capacity_json
from control_plane.executive_host_pressure import canonical_host_pressure_json
from control_plane.executive_physical_admission import _observed_pools
from control_plane.executive_physical_resources import physical_request_fingerprint
from control_plane.executive_runtime import (
    Attempt, AttemptStatus, ExpectedChildSelection, Job, JobStatus,
    Runtime, Worker, WorkerQuotaClass, WorkerStatus,
)
from control_plane.executive_steward import (
    CapacityState, EffectState, Freshness, ResponsibilityFact, Seat, SourceOwner, SourceRef,
)
from control_plane.model_router import ModelRouter, WorkRequest

NOW = 1_800_000_000_000
STAMP = "2027-01-15T08:00:00.000Z"


def job(name, **changes):
    values = dict(job_id=name, objective="fixture", department="engineering", priority=1,
        status=JobStatus.QUEUED, assigned_worker_id=None, assigned_quota_class=None,
        authority_level="READ", branch=None, worktree=None, checkpoint=None, result=None,
        created_at=STAMP, updated_at=STAMP)
    values.update(changes)
    return Job(**values)


def original():
    attempt = Attempt(attempt_id="plan-attempt", job_id="JOB-planner", attempt_number=1,
        worker_id="planner-worker", quota_class="plan", status=AttemptStatus.COMPLETED,
        fence_generation=1, lease_owner="fixture-owner", lease_expires_at=STAMP,
        heartbeat_at=STAMP, checkpoint_sequence=0, checkpoint=None, result=None, error=None,
        started_at=STAMP, finished_at=STAMP, version=2, authority_policy_hash="a" * 64,
        pid=None, pgid=None, process_start_identity=None, boot_id=None, provider_session_id=None,
        stdout_path=None, stderr_path=None, result_path=None, exit_code=0, launch_metadata={})
    expected = ExpectedChildSelection(root_job_id="JOB-root", parent_job_id="JOB-coordinator", job_id="JOB-child",
        plan_attempt_id=attempt.attempt_id, plan_digest="b" * 64, plan_step_id="step-1",
        repair_round=0, expected_current_attempt_id=None, attempt_ordinal=1,
        command_id="coo-cycle:JOB-coordinator:dispatch:JOB-child:attempt:1")
    child = job("JOB-child", root_job_id="JOB-root", parent_job_id="JOB-coordinator", plan_attempt_id=attempt.attempt_id,
        plan_digest=expected.plan_digest, plan_step_id=expected.plan_step_id, repair_round=0, orchestration_role="work")
    planner = job("JOB-planner", status=JobStatus.COMPLETED, root_job_id="JOB-root", parent_job_id="JOB-coordinator",
        current_attempt_id=attempt.attempt_id, orchestration_role="plan")
    return h.OriginalSelection(expected, child, planner, attempt,
        {"plan_attempt_id": attempt.attempt_id, "plan_digest": expected.plan_digest})


def source(owner, ref):
    return SourceRef(owner=owner, ref=ref, observed_at=STAMP, freshness=Freshness.CURRENT)


def refresh_physical(inputs):
    """Rebuild incumbent measured pools/digests after fixture changes."""
    raw = copy.deepcopy(inputs)
    pressure = raw.pressure_snapshot
    snapshot = raw.observations["host_capacity_evidence"]["snapshot"]
    snapshot.update(
        hp0_sha256=hashlib.sha256(canonical_host_pressure_json(pressure)).hexdigest(),
        logical_cpu_count=pressure["logical_cpu_count"], load1_milli=pressure["load1_milli"],
        load_ratio_milli=pressure["load_ratio_milli"], hp0_telemetry_status=pressure["telemetry_status"],
    )
    raw.observations["host_capacity_evidence"]["snapshot_sha256"] = hashlib.sha256(
        canonical_host_capacity_json(snapshot)).hexdigest()
    host = next(x for x in raw.policy["host_qualifications"] if x["host_id"] == raw.request["host_id"])
    raw.observations["pools"] = _observed_pools(host["profiles"][0], host, snapshot, pressure,
        raw.request["source_binding"]["destination"]["capacity_pool_id"])
    return raw


def physical_inputs(origin):
    host_ref, boot_ref, pool_ref = "host-" + "2" * 64, "boot-" + "5" * 64, "capacity-pool-" + "8" * 64
    def demand(dimension, pool, unit, peak):
        return {"dimension": dimension, "capacity_pool_id": pool, "qualified_incremental_peak": peak,
            "window_binding": {"unit": unit, "window_ms": 1000, "baseline_id": "base-1", "boot_id": boot_ref}}
    demands = [demand("memory_bytes", "memory", "bytes", 20), demand("cpu_us_per_window", "cpu", "cpu_us", 200)]
    profile = {"profile": "ROUTINE_WORKER", "qualified_duration_ms": 1000,
        "qualification_evidence": ["synthetic-profile"], "effect_scope": ["provider_worker_effect"],
        "qualified_demands": copy.deepcopy(demands)}
    host = {"host_id": host_ref, "boot_id": boot_ref, "capacity_pool_ref": pool_ref,
        "qualification_revision": "synthetic-host-1", "qualification_evidence": ["synthetic-host"],
        "physical_pools": [{"capacity_pool_id": "memory", "protected_reserve": 10},
            {"capacity_pool_id": "cpu", "protected_reserve": 1}], "profiles": [profile],
        "windows": {"cpu_window_ms": 1000, "io_window_ms": 1000, "normalization_evidence": "synthetic-window"},
        "limits": {"cpu_budget_us": 1_000_000, "cpu_protected_us": 1, "memory_budget_bytes": 1_000_000,
            "memory_protected_bytes": 10, "internal_protected_bytes": 10, "external_protected_bytes": 10,
            "io_budget_bytes": 1_000_000, "io_protected_bytes": 1, "max_heavy_phases": 8}}
    policy = {"schema": "mastermind.physical_resource_policy.v2", "production_armed": True,
        "qualification": "SYNTHETIC_TEST_ONLY", "policy_revision": "fixture-policy-1",
        "authority_receipt": "synthetic-authority", "qualification_evidence": ["synthetic-evidence"],
        "canonical_runtime": {"runtime_id": "fixture-runtime", "host_id": "host-" + "e" * 64,
            "boot_id": "boot-" + "f" * 64, "endpoint": "synthetic://runtime",
            "database_identity": "fixture-db", "schema_identity": "fixture-schema"},
        "allowed_callers": [{"owner_id": "fixture-owner", "carrier_id": "fixture-carrier", "session_id": "fixture-session"}],
        "host_qualifications": [host], "freshness": {"sample_max_age_ms": 20,
            "sample_cadence_ms": 5, "decision_to_effect_max_ms": 10},
        "waits": {"service_request_max_ms": 20, "database_lock_max_ms": 15},
        "recovery": {"reservation_horizon_ms": 100, "reconciliation_interval_ms": 10}}
    request = {"operation_key": "finite-initial:JOB-child", "host_id": host_ref, "boot_id": boot_ref,
        "owner_id": "fixture-owner", "carrier_id": "fixture-carrier",
        "command_id": f"physical:{origin.expected.command_id}:reserve",
        "source_binding": {"commit_sha": "a" * 40, "helper_sha256": "b" * 64,
            "common_git_store": {"realpath": "/synthetic/git", "device": 1, "inode": 2},
            "destination": {"realpath": "/synthetic/worker", "device": 3, "capacity_pool_id": "memory"}},
        "policy_binding": {"revision": "fixture-policy-1", "sha256": "c" * 64},
        "caller_binding": {"session_id": "fixture-session", "pid": 123, "start_id": "fixture-start"},
        "acquisition_time_ms": NOW, "phases": [{"phase_key": "worker", "profile": "ROUTINE_WORKER",
            "duration_ms": 1000, "effect_scope": ["provider_worker_effect"], "demands": demands}]}
    pressure = {"schema": "mastermind.host_pressure_snapshot/v1", "host_ref": host_ref, "boot_ref": boot_ref,
        "observed_at_ms": NOW - 5, "sample_window_ms": 5, "logical_cpu_count": 8,
        "load1_milli": 2000, "load_ratio_milli": 250, "fseventsd_process_count": 0,
        "fseventsd_cpu_milli_pct": 0, "fseventsd_rss_bytes": 0, "telemetry_status": "COMPLETE", "unknown_fields": []}
    snapshot = {"schema": "mastermind.host_capacity_snapshot/v1", "host_ref": host_ref, "boot_ref": boot_ref,
        "observed_at_ms": NOW - 2, "sample_window_ms": 3, "total_observation_window_ms": 8,
        "capacity_pool_ref": pool_ref, "hp0_sha256": "0" * 64, "hp0_observed_at_ms": NOW - 5,
        "hp0_sample_window_ms": 5, "logical_cpu_count": 8, "load1_milli": 2000, "load_ratio_milli": 250,
        "hp0_telemetry_status": "COMPLETE", "physical_memory_bytes": 64 * 1024**3, "vm_page_size_bytes": 4096,
        "vm_free_pages": 100_000, "vm_inactive_pages": 50_000, "vm_speculative_pages": 10_000,
        "vm_compressed_pages": 1000, "swap_total_bytes": 4 * 1024**3, "swap_used_bytes": 0,
        "pool_total_bytes": 500 * 1024**3, "pool_free_bytes": 100 * 1024**3,
        "telemetry_status": "COMPLETE", "unknown_fields": []}
    observations = {"host_id": host_ref, "boot_id": boot_ref, "policy_revision": "fixture-policy-1",
        "sequence": 7, "required_sequence": 7, "observed_at_ms": NOW - 2, "pools": {},
        "host_capacity_evidence": {"snapshot": snapshot, "snapshot_sha256": "0" * 64}}
    return refresh_physical(h.PhysicalInputs(request, policy, (), observations, pressure))


def _resign(value):
    value = copy.deepcopy(value)
    value.pop("observation_digest", None)
    value["observation_digest"] = hashlib.sha256(json.dumps(value, sort_keys=True,
        separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode()).hexdigest()
    return value


def _readiness(registered):
    from datetime import datetime, timezone
    join = registered.capacity_join
    def stamp(ms):
        return datetime.fromtimestamp(ms / 1000, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return _resign({"schema_version": "mastermind.executive_worker_capacity_observation/v1",
        "host_ref": join.host_ref, "capacity_capability_id": join.capacity_capability_id,
        "realm_metadata_valid": True, "credential_present": True, "credential_metadata_valid": True,
        "provider_binary_attested": True, "broker_generation_ready": True,
        "source_config_digest": join.worker_source_config_digest,
        "observed_at": stamp(NOW - 1000), "expires_at": stamp(NOW + 14000)})


def candidate(router, origin, name="worker-a", alias="fast.engineering"):
    model = router.resolve_model_alias(alias)
    epoch = h.OwnerEpoch("capacity-owner-fixture", 17, "c" * 64)
    physical = physical_inputs(origin)
    join = CapacityJoin(physical.request["host_id"], "capability-a", "mastermind.provider_capacity.v1", "d" * 64)
    registered = RegisteredCapacityJoin(name, "routine", model.provider_alias, join)
    metadata = {key: getattr(model, key) for key in (
        "execution_profile_id", "execution_profile_digest", "capability_policy_version", "capability_policy_digest")}
    metadata.update(model_alias=alias, routing_policy_version=router.policy_version, capacity_join=join.to_dict())
    worker = Worker(name, model.provider_alias, "opaque-account-a", model.adapter_id, WorkerStatus.AVAILABLE,
        ["code", "tests"], None, STAMP, {}, {})
    quota = WorkerQuotaClass(name, "routine", WorkerStatus.AVAILABLE, model.provider_alias, model.model,
        model.effort, model.cost_class, ["code", "tests"], None, None, 3, STAMP, metadata)
    fact = ps.PlacementCandidateFact(worker_id=name, provider=model.provider_alias, account_label=worker.account_label,
        quota_class="routine", capabilities=frozenset({"code", "tests"}), observed_at_ms=NOW - 2,
        occupancy=ps.OccupancyState.FREE, occupancy_source=source(SourceOwner.RUNTIME_BINDING, "runtime-a"),
        capacity_state=CapacityState.AVAILABLE, capacity_source=source(SourceOwner.CAPACITY, "capacity-a"),
        host_source_closure_proven=True, closure_source=source(SourceOwner.CAPACITY, "closure-a"),
        effect_state=EffectState.NONE, mode=ps.PlacementMode.NEW_SESSION_MATERIALIZATION,
        creation_surface_accessible=True, session_creation_allowed=True)
    facts = h.OwnerCapacityFacts(epoch, NOW - 2, NOW + 14_998, h.ObservationCoverage.COMPLETE,
        name, "routine", 3, alias, model.execution_profile_digest, join.host_ref,
        physical.request["boot_id"], "lane-a", join.capacity_capability_id, join.worker_source_config_digest,
        True, True, True, True, 128_000, 3, False, 2, 0,
        physical_request_fingerprint(physical.request))
    return h.CandidateInputs(worker, quota, fact, epoch, facts, epoch,
        _readiness(registered), physical)


def qualified_inputs():
    """Reproducible documented fixture, never a live-source acquisition API."""
    router = ModelRouter.load()
    work = WorkRequest("implementation")
    origin = original()
    responsibility = ResponsibilityFact("WS:H24-02", "Fixture selected child", Seat.CEO,
        "waiting_capacity", "JOB-root", source(SourceOwner.AGENT_OS, "h24-fixture"))
    member = {"provider_realm": "codex", "quota_class": "routine"}
    request = h.HermesCapacityRequest(h.TaskRequirements(work, True, False, 4096), router.route(work), origin,
        responsibility, (member,), (copy.deepcopy(member),), copy.deepcopy(member),
        ps.PlacementDemand(frozenset({"code"}), "routine", "codex",
            frozenset({ps.PlacementMode.NEW_SESSION_MATERIALIZATION})),
        (candidate(router, origin),), NOW, h.EvaluationMode.FIXTURE_ONLY)
    return request, router


def decide(good, **changes):
    request, router = good
    return h.decide_hermes_capacity(dc.replace(request, **changes), router=router).to_dict()


def change_facts(good, **changes):
    request, _ = good
    item = request.candidates[0]
    return decide(good, candidates=(dc.replace(item, facts=dc.replace(item.facts, **changes)),))


def codes(result):
    return {result["code"], *(row["code"] for row in result["trace"])}


def cases(names, values):
    """Expand finite fixture cases into ordinary unittest methods."""
    def decorate(function):
        function._h24_cases = values
        function._h24_single = isinstance(names, str) and "," not in names
        return function
    return decorate


def expand_cases(cls):
    for name, function in list(vars(cls).items()):
        if not hasattr(function, "_h24_cases"):
            continue
        delattr(cls, name)
        for index, value in enumerate(function._h24_cases):
            arguments = (value,) if function._h24_single else tuple(value)
            def method(self, original=function, arguments=arguments):
                return original(self, *arguments)
            method.__doc__ = f"{name}: {value!r}"
            setattr(cls, f"{name}_{index:02d}", method)
    return cls


@expand_cases
class TestHermesCapacityDecision(unittest.TestCase):
    def setUp(self):
        self.good = qualified_inputs()
        self.tmp_path = Path(self.enterContext(tempfile.TemporaryDirectory()))

    def test_qualified_source_matches_incumbent_and_is_not_admitted(self):
        good = self.good
        request, router = good
        result = decide(good)
        assert result["state"] == "CANDIDATE", result
        selected = result["candidate"]
        incumbent = router.route(request.requirements.work)
        assert selected["model_alias"] in incumbent.preferred_model_aliases
        assert selected["execution_profile_digest"] == incumbent.execution_profile_digest
        assert selected["source"]["generation"] == 17
        assert selected["physical_qualification"] == "SYNTHETIC_TEST_ONLY"
        for key in ("selection_is_commitment", "capacity_reserved", "admitted_capacity", "worker_started"):
            assert result[key] is False
        assert result["claim_time_revalidation_required"] is True
        assert result["provenance"]["origin"]["plan_attempt_id"] == "plan-attempt"
        assert result["provenance"]["origin"]["expected_current_attempt_id"] is None
        assert result == decide(good)


    @cases("changes,expected", [
        ({"supports_tools": False}, "MODEL_CAPABILITY_MISMATCH"),
        ({"supports_tools": None}, "MODEL_CAPABILITY_UNKNOWN"),
        ({"context_window_tokens": 1024}, "MODEL_CONTEXT_INSUFFICIENT"),
        ({"context_window_tokens": None}, "MODEL_CONTEXT_UNKNOWN"),
        ({"model_enabled": False}, "MODEL_DISABLED_OR_UNENTITLED"),
        ({"model_entitled": False}, "MODEL_DISABLED_OR_UNENTITLED"),
        ({"model_entitled": None}, "MODEL_ENTITLEMENT_UNKNOWN"),
        ({"startable_jobs": None}, "CAPACITY_UNKNOWN"),
        ({"startable_jobs": 0}, "CAPACITY_EXHAUSTED"),
        ({"cooldown_active": None}, "CAPACITY_UNKNOWN"),
        ({"cooldown_active": True}, "CAPACITY_COOLDOWN"),
        ({"lane_limit": None}, "CAPACITY_UNKNOWN"),
        ({"lane_in_use": None}, "CAPACITY_UNKNOWN"),
        ({"lane_in_use": 2}, "CAPACITY_EXHAUSTED"),
        ({"lane_in_use": 3}, "CAPACITY_EXHAUSTED"),
        ({"coverage": h.ObservationCoverage.PARTIAL}, "OBSERVATION_INCOMPLETE"),
        ({"coverage": h.ObservationCoverage.DISCONNECTED}, "OBSERVATION_INCOMPLETE"),
        ({"observed_at_ms": NOW - 20_000, "expires_at_ms": NOW - 5000}, "OBSERVATION_EXPIRED"),
        ({"observed_at_ms": NOW - 15_000, "expires_at_ms": NOW}, "OBSERVATION_EXPIRED"),
        ({"observed_at_ms": NOW + 1}, "OBSERVATION_EXPIRED"),
        ({"expires_at_ms": NOW + 60_000}, "OBSERVATION_TTL_INVALID"),
        ({"quota_fence_generation": 4}, "REGISTERED_IDENTITY_MISMATCH"),
        ({"worker_source_config_digest": "0" * 64}, "CAPACITY_JOIN_MISMATCH"),
        ({"boot_ref": "boot-" + "0" * 64}, "PHYSICAL_GENERATION_CHANGED"),
        ({"model_alias": "hard.engineering"}, "MODEL_OUTSIDE_INCUMBENT_TIER"),
        ({"lane_in_use": False}, "INPUT_INVALID"),
        ({"startable_jobs": -1}, "INPUT_INVALID"),
        ({"supports_tools": 1}, "INPUT_INVALID"),
    ])
    def test_owner_fact_refusal_matrix(self, changes, expected):
        good = self.good
        result = change_facts(good, **changes)
        assert result["candidate"] is None
        assert expected in codes(result), result


    def test_vision_requirement_and_missing_granted_tool(self):
        good = self.good
        request, _ = good
        vision = dc.replace(request.requirements, requires_vision=True)
        item = request.candidates[0]
        result = decide(good, requirements=vision, candidates=(dc.replace(item, facts=dc.replace(item.facts, supports_vision=False)),))
        assert "MODEL_CAPABILITY_MISMATCH" in codes(result)
        result = decide(good, requirements=dc.replace(request.requirements, required_profile_capabilities=frozenset({"ungranted-tool"})))
        assert "PROFILE_CAPABILITY_MISMATCH" in codes(result)


    @cases("dimension", ["memory", "cpu"])
    def test_host_pressure_is_measured_by_incumbent_policy(self, dimension):
        good = self.good
        request, _ = good
        item = request.candidates[0]
        p = copy.deepcopy(item.physical)
        if dimension == "memory":
            snapshot = p.observations["host_capacity_evidence"]["snapshot"]
            for key in ("vm_free_pages", "vm_inactive_pages", "vm_speculative_pages"):
                snapshot[key] = 0
        else:
            pressure = p.pressure_snapshot
            pressure["load1_milli"] = pressure["logical_cpu_count"] * 2000
            pressure["load_ratio_milli"] = 2000
        result = decide(good, candidates=(dc.replace(item, physical=refresh_physical(p)),))
        assert result["state"] == "UNAVAILABLE", result
        assert "OWNER_EVIDENCE_UNAVAILABLE" in codes(result)
        assert result["trace"][0]["owner_code"] == "INSUFFICIENT_CAPACITY"


    @cases("field", ["current_charges", "observations", "pressure_snapshot"])
    def test_disconnected_physical_facts_never_become_zero_load(self, field):
        good = self.good
        request, _ = good
        item = request.candidates[0]
        result = decide(good, candidates=(dc.replace(item, physical=dc.replace(item.physical, **{field: None})),))
        assert result["state"] == "UNAVAILABLE"
        assert "PHYSICAL_OBSERVATION_UNAVAILABLE" in codes(result)


    def test_partial_host_snapshot_and_invented_available_pool_refuse(self):
        good = self.good
        request, _ = good
        item = request.candidates[0]
        p = copy.deepcopy(item.physical)
        snapshot = p.observations["host_capacity_evidence"]["snapshot"]
        for key in ("swap_total_bytes", "swap_used_bytes"):
            snapshot[key] = None
        snapshot["unknown_fields"] = ["swap_total_bytes", "swap_used_bytes"]
        snapshot["telemetry_status"] = "PARTIAL"
        result = decide(good, candidates=(dc.replace(item, physical=p),))
        assert result["state"] == "UNAVAILABLE", result
        assert "PHYSICAL_OBSERVATION_INCOMPLETE" in codes(result)
        p = copy.deepcopy(item.physical)
        p.observations["pools"]["memory"]["available"] += 1
        assert "PHYSICAL_OBSERVATION_MISMATCH" in codes(decide(good, candidates=(dc.replace(item, physical=p),)))


    def test_existing_physical_charges_are_counted_without_reserving(self):
        good = self.good
        request, _ = good
        item = request.candidates[0]
        charge = {"dimension": "memory_bytes", "capacity_pool_id": "memory", "remaining_charge": 1_000_000}
        result = decide(good, candidates=(dc.replace(item, physical=dc.replace(item.physical, current_charges=(charge,))),))
        assert result["state"] == "UNAVAILABLE"


    @cases("which", ["source_before", "source_after"])
    def test_source_aba_uses_generation_even_when_digest_returns_to_a(self, which):
        good = self.good
        request, _ = good
        item = request.candidates[0]
        changed = dc.replace(item.facts.epoch, generation=item.facts.epoch.generation + 2)
        assert changed.source_digest == item.facts.epoch.source_digest
        result = decide(good, candidates=(dc.replace(item, **{which: changed}),))
        assert result["state"] == "UNAVAILABLE"
        assert "SOURCE_CHANGED_OR_ABA" in codes(result)


    @cases("which", ["source_before", "source_after", "facts", "readiness", "quota"])
    def test_missing_owner_inputs_are_unavailable(self, which):
        good = self.good
        request, _ = good
        result = decide(good, candidates=(dc.replace(request.candidates[0], **{which: None}),))
        assert result["state"] == "UNAVAILABLE"
        assert result["candidate"] is None


    def test_stale_readiness_is_not_refreshed(self):
        good = self.good
        request, _ = good
        item = copy.deepcopy(request.candidates[0])
        item.readiness["observed_at"] = "2000-01-01T00:00:00Z"
        item.readiness["expires_at"] = "2000-01-01T00:00:15Z"
        item = dc.replace(item, readiness=_resign(item.readiness))
        result = decide(good, candidates=(item,))
        assert result["state"] == "UNAVAILABLE"


    def test_original_attempt_absence_wrong_root_and_replay_are_distinct(self):
        good = self.good
        request, _ = good
        missing = dc.replace(request.origin, original_attempt=None)
        assert decide(good, origin=missing)["code"] == "ORIGINAL_ATTEMPT_MISSING"
        wrong_root = dc.replace(request.origin, planner_job=dc.replace(request.origin.planner_job, root_job_id="other-root"))
        assert decide(good, origin=wrong_root)["code"] == "ORIGINAL_ATTEMPT_MISMATCH"
        replay = dc.replace(request.origin, expected=dc.replace(request.origin.expected, expected_current_attempt_id="existing"))
        assert decide(good, origin=replay)["code"] == "EXISTING_ATTEMPT_REQUIRES_REOBSERVATION"
        wrong_command = dc.replace(request.origin, expected=dc.replace(request.origin.expected, command_id="different-command"))
        assert decide(good, origin=wrong_command)["state"] == "REFUSED"


    def test_wrong_union_and_inherited_narrowing(self):
        good = self.good
        request, _ = good
        foreign = {"provider_realm": "other-provider", "quota_class": "routine"}
        assert decide(good, inherited_work_placement_union=(foreign,))["code"] == "PLACEMENT_UNION_WIDENED"
        assert decide(good, inherited_work_placement_union=())["state"] == "REFUSED"
        child = dc.replace(request.origin.child, constraints={"preferred_model_aliases": ["standard.engineering"]})
        result = decide(good, origin=dc.replace(request.origin, child=child))
        assert "MODEL_OUTSIDE_INCUMBENT_TIER" in codes(result)
        result = decide(good, selected_placement={"provider_realm": "codex", "quota_class": "other"})
        assert result["state"] == "REFUSED"
        assert result["candidate"] is None


    @cases("constraints", [
        {"excluded_worker_ids": ["worker-a"]},
        {"required_capabilities": ["ungranted-tool"]},
        {"task_kind": "tests"}, {"risk": "critical"}, {"ambiguity": "high"},
        {"paid_execution_route": {"model_alias": "unapproved"}},
        {"attended_route": {"model_alias": "unapproved"}},
        {"work_placement_union": [{"provider_realm": "other", "quota_class": "routine"}]},
    ])
    def test_inherited_child_requirements_cannot_be_omitted(self, constraints):
        request, _ = self.good
        child = dc.replace(request.origin.child, constraints=constraints)
        result = decide(self.good, origin=dc.replace(request.origin, child=child))
        assert result["state"] == "REFUSED", result
        assert result["candidate"] is None


    def test_inherited_exclusion_carried_into_router_still_excludes_worker(self):
        request, router = self.good
        child = dc.replace(request.origin.child, constraints={"excluded_worker_ids": ["worker-a"]})
        work = dc.replace(request.requirements.work, excluded_worker_ids=("worker-a",))
        result = decide(self.good, origin=dc.replace(request.origin, child=child),
            requirements=dc.replace(request.requirements, work=work), suitability=router.route(work))
        assert "REGISTERED_ROUTE_MISMATCH" in codes(result), result
        assert result["candidate"] is None


    @cases("mutation", [
        {"orchestration_role": "plan"}, {"orchestration_role": "review"},
        {"status": JobStatus.COMPLETED}, {"status": JobStatus.CANCELLED},
    ])
    def test_only_fresh_queued_work_or_repair_children_can_be_candidates(self, mutation):
        request, _ = self.good
        child = dc.replace(request.origin.child, **mutation)
        result = decide(self.good, origin=dc.replace(request.origin, child=child))
        assert result["code"] == "FRESH_WORK_CHILD_REQUIRED", result


    def test_unfinished_planner_and_incompatible_worker_adapter_refuse(self):
        request, _ = self.good
        planner = dc.replace(request.origin.planner_job, status=JobStatus.RUNNING)
        assert decide(self.good, origin=dc.replace(request.origin, planner_job=planner))["code"] == "ORIGINAL_PLAN_UNFINISHED"
        item = request.candidates[0]
        worker = dc.replace(item.worker, worker_type="unqualified-adapter")
        result = decide(self.good, candidates=(dc.replace(item, worker=worker),))
        assert "WORKER_ADAPTER_MISMATCH" in codes(result), result


    def test_synthetic_inputs_require_explicit_fixture_mode(self):
        request, _ = self.good
        default_mode = h.HermesCapacityRequest.__dataclass_fields__["evaluation_mode"].default
        assert default_mode is h.EvaluationMode.OWNER_QUALIFIED
        result = decide(self.good, evaluation_mode=default_mode)
        assert result["state"] == "UNAVAILABLE", result
        assert result["candidate"] is None
        assert result["trace"][0]["owner_code"] == "SYNTHETIC_POLICY_REFUSED"
        assert result["provenance"]["evaluation_mode"] == "OWNER_QUALIFIED"
        assert decide(self.good)["provenance"]["evaluation_mode"] == "FIXTURE_ONLY"
        assert decide(self.good, evaluation_mode="FIXTURE_ONLY")["state"] == "REFUSED"


    def test_physical_request_is_bound_to_qualified_worker_lane(self):
        request, _ = self.good
        item = copy.deepcopy(request.candidates[0])
        item.physical.request["source_binding"]["destination"]["realpath"] = "/synthetic/other-lane"
        result = decide(self.good, candidates=(item,))
        assert "PHYSICAL_LANE_BINDING_MISMATCH" in codes(result), result
        assert result["candidate"] is None


    def test_stale_physical_sample_is_unavailable(self):
        result = decide(self.good, now_ms=NOW + 100)
        assert result["state"] == "UNAVAILABLE", result
        assert "OWNER_EVIDENCE_UNAVAILABLE" in codes(result)


    def test_no_observed_routes_is_explicitly_unavailable(self):
        result = decide(self.good, candidates=())
        assert result["state"] == "UNAVAILABLE", result
        assert result["code"] == "NO_ELIGIBLE_CANDIDATE"
        assert result["candidate"] is None


    def test_suitability_is_recomputed_by_current_router(self):
        good = self.good
        request, _ = good
        stale = dc.replace(request.suitability, policy_version="different")
        assert decide(good, suitability=stale)["code"] == "SUITABILITY_CHANGED"
        changed_work = dc.replace(request.requirements, work=WorkRequest("tests"))
        assert decide(good, requirements=changed_work)["code"] == "SUITABILITY_CHANGED"


    def test_disabled_current_provider_and_profile_cannot_pass(self):
        good = self.good
        request, router = good
        router.providers["codex"] = dc.replace(router.providers["codex"], enabled=False)
        assert "PROVIDER_DISABLED" in codes(decide(good))
        router.providers["codex"] = dc.replace(router.providers["codex"], enabled=True)
        profile_id = request.suitability.execution_profile_id
        profile = router.capability_registry.profiles[profile_id]
        router.capability_registry.profiles[profile_id] = dc.replace(profile, enabled=False)
        assert decide(good)["state"] == "REFUSED"


    @cases("changes", [{"policy_digest": "0" * 64}, {"policy_version": "changed-policy"}])
    def test_current_capability_registry_identity_must_match_model(self, changes):
        _, router = self.good
        router.capability_registry = dc.replace(router.capability_registry, **changes)
        result = decide(self.good)
        assert "MODEL_BINDING_MISMATCH" in codes(result), result
        assert result["candidate"] is None


    def test_incumbent_ties_abstain_and_account_labels_do_not_rank(self):
        good = self.good
        request, router = good
        second = candidate(router, request.origin, name="worker-z", alias="standard.engineering")
        for order in itertools.permutations((request.candidates[0], second)):
            result = decide(good, candidates=order)
            assert result["state"] == "UNAVAILABLE", result
            assert result["incumbent_selection"]["state"] == "tie_abstained"
        assert decide(good, candidates=(request.candidates[0], second)) == decide(good, candidates=(second, request.candidates[0]))


    def test_clean_sibling_survives_unavailable_lane_and_incumbent_rank_is_preserved(self):
        good = self.good
        request, router = good
        second = candidate(router, request.origin, name="worker-z", alias="standard.engineering")
        blocked = dc.replace(request.candidates[0], facts=dc.replace(request.candidates[0].facts, cooldown_active=True))
        result = decide(good, candidates=(blocked, second))
        assert result["candidate"]["model_alias"] == "standard.engineering"
        degraded = dc.replace(request.candidates[0], placement_fact=dc.replace(request.candidates[0].placement_fact, capacity_state=CapacityState.DEGRADED))
        result = decide(good, candidates=(degraded, second))
        assert result["candidate"]["worker_id"] == "worker-z"
        assert result["candidate"]["model_alias"] in router.route(request.requirements.work).preferred_model_aliases


    @cases("mutation", [
        {"occupancy": ps.OccupancyState.OCCUPIED},
        {"effect_state": EffectState.EFFECT_UNKNOWN},
        {"host_source_closure_proven": False},
        {"capacity_state": CapacityState.UNKNOWN},
        {"creation_surface_accessible": False},
        {"session_creation_allowed": False},
    ])
    def test_incumbent_placement_exclusions_remain_authoritative(self, mutation):
        good = self.good
        request, _ = good
        item = request.candidates[0]
        result = decide(good, candidates=(dc.replace(item, placement_fact=dc.replace(item.placement_fact, **mutation)),))
        assert result["state"] == "UNAVAILABLE"
        assert result["candidate"] is None


    def test_closed_types_invalid_numbers_and_duplicate_identities(self):
        good = self.good
        request, _ = good
        assert decide(good, now_ms=True)["state"] == "REFUSED"
        assert decide(good, candidates=list(request.candidates))["state"] == "REFUSED"
        assert decide(good, candidates=request.candidates * 4)["state"] == "REFUSED"
        assert decide(good, candidates=request.candidates * 2)["code"] == "DUPLICATE_WORKER"
        assert decide(good, selected_placement={**request.selected_placement, "api_key": "DO_NOT_ECHO"})["state"] == "REFUSED"
        with self.assertRaises(TypeError):
            h.OwnerEpoch("owner", 1, "a" * 64, api_key="DO_NOT_ACCEPT")


    def test_unrelated_metadata_never_enters_output(self):
        good = self.good
        request, _ = good
        item = copy.deepcopy(request.candidates[0])
        item.quota.metadata["credential"] = "DO_NOT_ECHO"
        item.worker.metadata["provider_home"] = "/DO_NOT_ECHO"
        result = decide(good, candidates=(item,))
        assert result["state"] == "CANDIDATE"
        assert "DO_NOT_ECHO" not in json.dumps(result)
        changed = dc.replace(item, facts=dc.replace(item.facts, host_ref="/DO_NOT_ECHO"))
        assert "DO_NOT_ECHO" not in json.dumps(decide(good, candidates=(changed,)))


    def test_native_wire_is_revalidated_without_provider_normalization(self):
        good = self.good
        request, _ = good
        item = request.candidates[0]
        result = decide(good, candidates=(dc.replace(item, native_snapshot={"schema": "unknown"}, native_join={}),))
        assert result["state"] == "UNAVAILABLE"
        assert result["candidate"] is None


    def test_physical_evidence_is_bound_to_original_child(self):
        good = self.good
        request, _ = good
        item = copy.deepcopy(request.candidates[0])
        item.physical.request["operation_key"] = "finite-initial:different-child"
        assert "PHYSICAL_ORIGIN_MISMATCH" in codes(decide(good, candidates=(item,)))


    def test_concurrent_readers_leave_canonical_owner_state_unchanged(self):
        good = self.good
        tmp_path = self.tmp_path
        request, router = good
        runtime = Runtime.at(tmp_path)
        item = request.candidates[0]
        runtime.workers.register_worker(item.worker.worker_id, provider=item.worker.provider,
            account_label=item.worker.account_label, worker_type=item.worker.worker_type, capabilities=item.worker.capabilities)
        runtime.workers.register_quota_class(item.worker.worker_id, item.quota.quota_class,
            provider=item.quota.provider, model=item.quota.model, effort=item.quota.effort,
            cost_class=item.quota.cost_class, capabilities=item.quota.capabilities, metadata=item.quota.metadata)
        registered_worker = runtime.workers.get_worker(item.worker.worker_id)
        registered_quota = runtime.workers.get_quota_class(item.worker.worker_id, item.quota.quota_class)
        item = dc.replace(item, worker=registered_worker, quota=registered_quota,
            facts=dc.replace(item.facts, quota_fence_generation=registered_quota.fence_generation))
        request = dc.replace(request, candidates=(item,))
        def state():
            with runtime.store.read() as connection:
                return tuple(connection.iterdump())
        before = state()
        original_input = copy.deepcopy(request)
        with ThreadPoolExecutor(max_workers=8) as executor:
            results = list(executor.map(lambda _: h.decide_hermes_capacity(request, router=router).to_dict(), range(32)))
        assert all(value["state"] == "CANDIDATE" for value in results), results[0]
        assert all(value == results[0] for value in results)
        assert state() == before
        assert request == original_input


    def test_decision_is_defensive_and_adapter_does_no_io(self):
        good = self.good
        request, router = good
        def forbidden(*args, **kwargs):
            raise AssertionError("pure adapter attempted I/O")
        import builtins
        import socket
        import subprocess
        import time
        self.enterContext(mock.patch.object(builtins, "open", forbidden))
        self.enterContext(mock.patch.object(socket, "socket", forbidden))
        self.enterContext(mock.patch.object(subprocess, "Popen", forbidden))
        self.enterContext(mock.patch.object(time, "time", forbidden))
        self.enterContext(mock.patch.object(time, "time_ns", forbidden))
        self.enterContext(mock.patch.object(ModelRouter, "load", forbidden))
        result = h.decide_hermes_capacity(request, router=router)
        assert result.state is h.DecisionState.CANDIDATE, result.to_dict()
        wire = result.to_dict()
        wire["candidate"]["worker_id"] = "changed"
        assert result.to_dict()["candidate"]["worker_id"] == "worker-a"

if __name__ == "__main__":
    unittest.main()
