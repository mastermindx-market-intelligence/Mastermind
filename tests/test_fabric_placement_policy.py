"""Rev5 D6 (Fable Wave 3 R5 §3D): parent-as-placement in the EXISTING broker.

The pure policy core (:mod:`control_plane.fabric_placement_policy`) and its
wiring into the incumbent claim path (``AttemptRegistry.claim_job`` — the
sole placement authority, WO-14, unchanged in its reservation semantics):

* soft preference reorders, never excludes; hard affinity — only for a
  DECLARED local dependency — queues when no host declares it
  (``NO_ELIGIBLE_CANDIDATE``) or when the declaring host is full; it never
  evades a cap.
* a parent on host X requesting 20 children reserves 0 local child slots
  (fabric_per_child; the descendant limit is a COUNTED admission cap at
  each child claim).
* child headroom: parents cannot consume the last ``max(1, slots // 4)``
  (``MMOS_FABRIC_CHILD_HEADROOM``-tunable) slots of a host; children may.
* bounded_native_fanout reserves the enforced fan-out envelope at the
  parent's host from the parent's ONE claim commitment (never double-
  reserving envelope + children).
* conservative turn: the parent's slot + root concurrency are held until
  settlement — no mid-turn release.
"""
from __future__ import annotations

import json

import pytest

from control_plane.child_execution_contracts import ExecutionBinding
from control_plane.fabric_placement_policy import (
    DESCENDANT_CONCURRENCY_EXHAUSTED,
    NO_ELIGIBLE_CANDIDATE,
    PARENT_HEADROOM_EXHAUSTED,
    ActorRole,
    ChildHeadroomPolicy,
    DescendantPolicy,
    LocalityClass,
    PlacementIntent,
    TurnReservation,
    apply_locality,
    classify_locality,
    descendant_admission,
    descendant_policy,
    fanout_envelope_slots,
    filter_hard_affinity_hosts,
    inflate_host_slot_demand,
    intent_digest,
    reserve_turn_for_intent,
    soft_preference_key,
)
from control_plane.executive_placement_authority import (
    HostObservation,
    PlacementObservations,
    SharedQuotaObservation,
    host_slot_pool,
    root_concurrency_pool,
    shared_quota_pool,
)
from control_plane.executive_runtime import (
    AttemptStatus,
    JobStatus,
    ResourceBroker,
    Runtime,
    StateConflict,
)

NOW = 1_800_000_000_000
REVISION = "registry-rev-1"
QUOTA = "glm:chairman-max"


class Clock:
    def __init__(self, value: int = NOW) -> None:
        self.value = value

    def __call__(self) -> int:
        return self.value


def _runtime(tmp_path) -> tuple[Runtime, Clock]:
    clock = Clock()
    return Runtime.at(tmp_path, clock=clock, lease_seconds=60), clock


def _worker(runtime: Runtime, worker_id: str, host_id: str,
            *, local_dependency_refs: list[str] | None = None) -> None:
    metadata: dict = {"host_id": host_id}
    if local_dependency_refs is not None:
        metadata["local_dependency_refs"] = local_dependency_refs
    runtime.workers.register_worker(
        worker_id, provider="codex", account_label=f"acct-{worker_id}",
        worker_type="mock", capabilities=["code"], metadata=metadata,
    )


def _request(key: str) -> dict:
    return {
        "root_ref": "hermes-root-1",
        "immediate_parent_run_ref": "hermes-run-7",
        "logical_child_key": key,
        "task_kind": "code",
        "requested_complexity": "C1_ROUTINE_BOUNDED",
        "budget_grant_ref": "grant-ref-1",
    }


def _spec(key: str, *, revision: str = REVISION) -> dict:
    return {
        "child_execution_request": _request(key),
        "effective_complexity": "C1_ROUTINE_BOUNDED",
        "registry_revision": revision,
        "route": {"provider_ref": "codex", "pool_ref": "glm"},
        "shared_quota_resource_refs": [QUOTA],
        "root_concurrency_limit": 32,
    }


def _intent(role: str, child: str, *, limit=None, policy=None, preferred=None,
            required_refs=(), root="fabric-root-1", profile=None,
            deadline_ms=None, expiry_ms=None, priority=None) -> dict:
    raw = {
        "schema": "mastermind.fabric_placement_intent.v1",
        "root_run_id": root,
        "immediate_parent_run_id": "fabric-run-1",
        "logical_child_id": child,
        "operation_id": f"op-{child}",
        "actor_role": role,
    }
    if limit is not None:
        raw["descendant_parallelism_limit"] = limit
    if policy is not None:
        raw["descendant_policy"] = policy
    if preferred:
        raw["preferred_host"] = preferred
    if required_refs:
        raw["required_local_dependency_refs"] = list(required_refs)
    if profile is not None:
        raw["resource_profile"] = profile
    if deadline_ms is not None:
        raw["deadline_ms"] = deadline_ms
    if expiry_ms is not None:
        raw["expiry_ms"] = expiry_ms
    if priority is not None:
        raw["priority"] = priority
    return raw


def _job(runtime: Runtime, key: str, *, parent=None):
    constraints = {"child_placement": _spec(key)}
    return runtime.jobs.create_job(
        f"fabric {key}", constraints=constraints, parent_job_id=(
            parent.job_id if parent is not None else None
        ),
    )


def _claim(runtime: Runtime, job, hosts, *, intent=None, cap: int = 20, now: int = NOW):
    observations = PlacementObservations(
        registry_revision=REVISION, observed_at_ms=now,
        hosts={h: HostObservation(host_id=h, boot_id=f"boot-{h}", eligible_slots=n,
                                  observed_at_ms=now) for h, n in hosts.items()},
        shared_quota={QUOTA: SharedQuotaObservation(
            resource_ref=QUOTA, per_account_cap=cap, external_active_leases=0)},
    )
    return runtime.attempts.claim_job(
        job.job_id, placement_observations=observations,
        fabric_placement_intent=intent,
    )


def _charges(runtime: Runtime, *pools: str) -> dict[str, int]:
    with runtime.store.read() as connection:
        live = ResourceBroker(runtime.store)._placement_pool_charges(connection, pools)
    return {pool: live.get(pool, 0) for pool in pools}


def _commitment_states(runtime: Runtime) -> list[str]:
    with runtime.store.read() as connection:
        return [r["state"] for r in connection.execute(
            "SELECT state FROM physical_resource_commitments "
            "ORDER BY created_at_ms,commitment_id")]


def _claimed_payload(runtime: Runtime, job_id: str) -> dict:
    events = [e for e in runtime.store.list_events(job_id=job_id)
              if e.event_type == "JOB_CLAIMED"]
    assert len(events) == 1
    return events[0].payload


def _complete(runtime: Runtime, lease) -> None:
    runtime.attempts.complete_attempt(
        lease.attempt.attempt_id,
        fence_generation=lease.attempt.fence_generation,
        lease_token=lease.lease_token, payload={"summary": "done"})


# ===========================================================================
# pure policy: the PlacementIntent.v1 record and its laws
# ===========================================================================

def test_intent_record_round_trips_bounded_fields_and_digest():
    intent = PlacementIntent.from_dict(_intent(
        "parent", "coo-1", limit=20,
        profile={"resident_memory_bytes": 4096, "active_tools": ["edit", "shell"]},
        deadline_ms=NOW + 1000, expiry_ms=NOW + 2000, priority=3,
    ))
    assert intent.actor_role is ActorRole.PARENT
    assert intent.resource_profile.resident_memory_bytes == 4096
    assert intent.resource_profile.active_tools == ("edit", "shell")
    assert PlacementIntent.from_dict(intent.to_dict()) == intent
    assert intent_digest(intent) == intent_digest(
        PlacementIntent.from_dict(intent.to_dict()))
    assert intent_digest(intent) != intent_digest(
        PlacementIntent.from_dict(_intent("parent", "coo-2", limit=20)))


def test_intent_record_refuses_unbounded_and_unknown_fields():
    with pytest.raises(ValueError, match="unknown keys"):
        PlacementIntent.from_dict(dict(_intent("child", "c"), injecting="x"))
    for bad in (
        {"root_run_id": "has space"},
        {"operation_id": "a@b"},
        {"logical_child_id": "trailing/"},
        {"descendant_parallelism_limit": 0},
        {"descendant_parallelism_limit": "20"},
        {"priority": 5000},
        {"source_scope_digest": "nothex"},
    ):
        with pytest.raises(ValueError):
            PlacementIntent.from_dict(dict(_intent("child", "c"), **bad))
    root_only = dict(_intent("child", "c"))
    root_only.pop("immediate_parent_run_ref", None)
    with pytest.raises(ValueError, match="missing"):
        PlacementIntent.from_dict(
            {k: v for k, v in _intent("child", "c").items()
             if k not in {"root_run_id"}})


def test_bounded_native_fanout_requires_an_envelope():
    with pytest.raises(ValueError, match="descendant_parallelism_limit is required"):
        PlacementIntent.from_dict(
            _intent("parent", "coo-1", policy="bounded_native_fanout"))
    intent = PlacementIntent.from_dict(
        _intent("parent", "coo-1", policy="bounded_native_fanout", limit=4))
    assert descendant_policy(intent) is DescendantPolicy.BOUNDED_NATIVE_FANOUT


# --- soft preference reorders, never excludes --------------------------------

def test_soft_preference_reorders_by_score_only_and_never_excludes():
    intent = PlacementIntent.from_dict(
        _intent("child", "reader-1", preferred="ubuntu1"))
    assert classify_locality(intent) is LocalityClass.SOFT_PREFERENCE
    ordered, blocking = apply_locality(
        ["ubuntu0", "ubuntu1", "ubuntu2", "ubuntu3"], intent)
    assert blocking is None
    assert list(ordered) == ["ubuntu1", "ubuntu0", "ubuntu2", "ubuntu3"]
    # an unknown preferred host changes nothing; nothing is ever dropped
    other = PlacementIntent.from_dict(
        _intent("child", "reader-1", preferred="saturn"))
    assert apply_locality(["ubuntu0", "ubuntu1"], other) == (
        ("ubuntu0", "ubuntu1"), None)
    assert soft_preference_key("ubuntu1", intent) == 0
    assert soft_preference_key("ubuntu0", intent) == 1


def test_hard_affinity_requires_a_declared_dependency_and_queues_when_none():
    intent = PlacementIntent.from_dict(
        _intent("child", "svc-child", required_refs=["svc:ubuntu3"]))
    assert classify_locality(intent) is LocalityClass.HARD_AFFINITY
    # a host that declares exactly the ref is kept, every other host excluded
    kept, blocking = filter_hard_affinity_hosts(
        ["ubuntu0", "ubuntu3", "ubuntu1"], intent,
        declare=lambda host: host == "ubuntu3")
    assert kept == ("ubuntu3",) and blocking is None
    # NO host declares it -> the work QUEUES with a precise blocked reason
    kept, blocking = filter_hard_affinity_hosts(
        ["ubuntu0", "ubuntu1"], intent, declare=lambda host: False)
    assert kept == () and blocking == NO_ELIGIBLE_CANDIDATE


def test_one_instance_is_explicit():
    intent = PlacementIntent.from_dict(_intent("child", "c", required_refs=["svc:x"]))
    assert filter_hard_affinity_hosts(["a"], intent, declare=lambda h: True)[0] == ("a",)


# --- the parent reserves 0 local child slots ----------------------------------

def test_fabric_per_child_parent_reserves_zero_local_child_slots():
    parent = PlacementIntent.from_dict(_intent("parent", "coo-1", limit=20))
    assert descendant_policy(parent) is DescendantPolicy.FABRIC_PER_CHILD
    assert fanout_envelope_slots(parent) == 0
    assert reserve_turn_for_intent(parent).envelope_slots == 0
    # the cap is a counted admission check at the CHILD claim, not slots
    assert descendant_admission(parent, 19).ok  # cap checks happen at children
    child = PlacementIntent.from_dict(_intent("child", "c-1", limit=20))
    assert descendant_admission(child, 19).ok
    verdict = descendant_admission(child, 20)
    assert not verdict.ok
    assert verdict.reason == DESCENDANT_CONCURRENCY_EXHAUSTED


def test_bounded_native_fanout_parent_reserves_envelope_and_children_skip():
    parent = PlacementIntent.from_dict(
        _intent("parent", "coo-1", policy="bounded_native_fanout", limit=7,
                profile={"resident_memory_bytes": 512, "active_tools": ["native"]}))
    assert fanout_envelope_slots(parent) == 7
    envelope_child = PlacementIntent.from_dict(dict(
        _intent("child", "c-1", limit=7), descendant_policy="bounded_native_fanout"))
    # children under the envelope are NOT counted again: their capacity was
    # reserved at the parent's claim — never double-reserve envelope + children
    assert descendant_admission(envelope_child, 999).ok
    assert reserve_turn_for_intent(parent).to_dict()["mid_turn_release"] is False


def test_no_eligible_candidate_beats_headroom_only_when_no_host_declares():  # specificity guard
    intent = PlacementIntent.from_dict(
        _intent("child", "c-1", required_refs=["svc:z"], limit=1))
    kept, blocking = filter_hard_affinity_hosts([], intent, declare=lambda h: True)
    assert (kept, blocking) == ((), NO_ELIGIBLE_CANDIDATE)


# --- child headroom -----------------------------------------------------------

def test_headroom_blocks_parents_from_the_last_reserved_child_slots():
    policy = ChildHeadroomPolicy()
    # 4 slots -> 1 reserved; 3 children hold 3 slots: a parent may NOT take
    # the last free slot (children still may).
    blocked = policy.admit_against_headroom(4, 0, 3, is_parent=True)
    assert not blocked.ok
    assert blocked.reason == PARENT_HEADROOM_EXHAUSTED
    assert policy.admit_against_headroom(4, 0, 3, is_parent=False).ok
    assert policy.admit_against_headroom(4, 0, 2, is_parent=True).ok
    # children may fill the reserved slots themselves
    assert policy.admit_against_headroom(4, 0, 4, is_parent=False).ok
    # 9 slots -> 2 headroom; 7 children: parent blocked
    assert not policy.admit_against_headroom(9, 0, 7, is_parent=True).ok
    assert policy.admit_against_headroom(9, 0, 6, is_parent=True).ok


def test_headroom_env_override_is_bounded_and_zero_disables():
    policy = ChildHeadroomPolicy.from_env({"MMOS_FABRIC_CHILD_HEADROOM": "0"})
    assert policy.reserved_child_slots(4) == 0
    assert policy.admit_against_headroom(4, 0, 3, is_parent=True).ok
    two = ChildHeadroomPolicy.from_env({"MMOS_FABRIC_CHILD_HEADROOM": "2"})
    assert two.reserved_child_slots(4) == 2
    assert not two.admit_against_headroom(4, 0, 2, is_parent=True).ok
    clamped = ChildHeadroomPolicy.from_env({"MMOS_FABRIC_CHILD_HEADROOM": "9"})
    assert clamped.reserved_child_slots(4) == 4
    for bad in ("-1", "many"):
        with pytest.raises(ValueError):
            ChildHeadroomPolicy.from_env({"MMOS_FABRIC_CHILD_HEADROOM": bad})


def test_conservative_turn_reservation_never_releases_mid_turn():
    turn = TurnReservation()
    assert turn.host_slot and turn.root_concurrency
    assert turn.to_dict()["mid_turn_release"] is False
    with pytest.raises(ValueError, match="no mid-turn release"):
        TurnReservation(host_slot=False)
    profile_intent = PlacementIntent.from_dict(dict(
        _intent("parent", "coo-1", limit=2),
        descendant_policy="bounded_native_fanout",
        resource_profile={"resident_memory_bytes": 2048, "active_tools": ["edit"]},
    ))
    reserved = reserve_turn_for_intent(profile_intent)
    assert (reserved.resident_memory_bytes, reserved.active_tools,
            reserved.envelope_slots) == (2048, ("edit",), 2)


def test_envelope_folds_into_the_host_slot_demand():
    request = {"phases": [{"demands": [
        {"dimension": "heavy_phase_count", "capacity_pool_id": "host:ubuntu3",
         "qualified_incremental_peak": 1},
        {"dimension": "heavy_phase_count", "capacity_pool_id": "root:r1",
         "qualified_incremental_peak": 1},
    ]}]}
    folded = inflate_host_slot_demand(
        request, host_slot_pool_id="host:ubuntu3", envelope=5)
    peaks = {d["capacity_pool_id"]: d["qualified_incremental_peak"]
              for d in folded["phases"][0]["demands"]}
    assert peaks == {"host:ubuntu3": 6, "root:r1": 1}
    with pytest.raises(ValueError):
        inflate_host_slot_demand(request, host_slot_pool_id="host:nowhere",
                                 envelope=2)
    assert inflate_host_slot_demand(request, host_slot_pool_id="host:ubuntu3",
                                    envelope=0) == request


# ===========================================================================
# integration through AttemptRegistry.claim_job (the EXISTING claim path)
# ===========================================================================

def test_parent_claim_reserves_only_its_own_slot(tmp_path):
    runtime, _ = _runtime(tmp_path)
    _worker(runtime, "worker-a", "ubuntu0")
    job = _job(runtime, "coo-1")
    intent = _intent("parent", "coo-1", limit=20, preferred="ubuntu0")

    lease = _claim(runtime, job, {"ubuntu0": 4}, intent=intent)

    assert lease is not None
    binding = ExecutionBinding.from_dict(
        runtime.attempts.execution_binding(lease.attempt.attempt_id))
    assert binding.host_id == "ubuntu0"
    # 20 requested children reserved ZERO extra local slots: the ONE
    # commitment charges exactly the parent's own slot.
    assert _charges(runtime, host_slot_pool("ubuntu0")) == {host_slot_pool("ubuntu0"): 1}
    payload = _claimed_payload(runtime, job.job_id)
    record = payload["fabric_placement_intent"]
    assert record["schema_version"] == "mastermind.fabric_placement_intent.v1"
    assert record["locality"] == "soft_preference"
    assert record["envelope_slots"] == 0
    assert record["intent"]["actor_role"] == "parent"
    assert record["turn_reservation"]["held"] == ["host_slot", "root_concurrency"]
    assert record["turn_reservation"]["mid_turn_release"] is False


def test_parent_reorders_to_its_preferred_host_and_soft_never_excludes(tmp_path):
    runtime, _ = _runtime(tmp_path)
    _worker(runtime, "worker-z", "ubuntu1")
    _worker(runtime, "worker-a", "ubuntu0")

    # soft preference REORDERS candidates: the warm/cheaper preferred host is
    # selected first even though the other host ranks earlier by default.
    child = _job(runtime, "warm-child")
    intent = _intent("child", "warm-child", preferred="ubuntu1")
    lease = _claim(runtime, child, {"ubuntu1": 2, "ubuntu0": 4}, intent=intent)
    assert lease is not None and lease.attempt.worker_id == "worker-z"
    record = _claimed_payload(runtime, child.job_id)["fabric_placement_intent"]
    assert record["locality"] == "soft_preference"

    # soft preference never excludes: a zero-capacity preferred host costs
    # only the reorder, and the child still places on the other host.
    second = _job(runtime, "warm-child-2")
    second_intent = _intent("child", "warm-child-2", preferred="saturn")
    lease = _claim(runtime, second, {"ubuntu1": 2, "ubuntu0": 4},
                   intent=second_intent)
    assert lease is not None and lease.attempt.worker_id == "worker-a"


def test_hard_affinity_wiring_declares_hosts_and_queues_strangers(tmp_path):
    runtime, _ = _runtime(tmp_path)
    _worker(runtime, "worker-a", "ubuntu1", local_dependency_refs=["svc:ubuntu3", "dep:llvm"])
    _worker(runtime, "worker-b", "ubuntu0")

    # hard affinity: only the host whose capability snapshot DECLARES the
    # dependency qualifies.
    hard = _job(runtime, "hard-child")
    hard_intent = _intent("child", "hard-child", required_refs=["dep:llvm"])
    lease = _claim(runtime, hard, {"ubuntu1": 2, "ubuntu0": 4}, intent=hard_intent)
    assert lease is not None
    assert lease.attempt.worker_id == "worker-a"  # the only declaring host
    record = _claimed_payload(runtime, hard.job_id)["fabric_placement_intent"]
    assert record["locality"] == "hard_affinity"

    # an undeclared dependency queues with NO_ELIGIBLE_CANDIDATE — it never
    # places on a host that lacks the declared local service (no cap evasion).
    stranger = _job(runtime, "stranger-child")
    stranger_intent = _intent("child", "stranger-child", required_refs=["svc:nowhere"])
    assert _claim(runtime, stranger, {"ubuntu1": 2, "ubuntu0": 4},
                  intent=stranger_intent) is None
    assert runtime.jobs.get_job(stranger.job_id).status is JobStatus.QUEUED
    reason = runtime.attempts.placement_wait_reason(stranger.job_id)
    assert reason["reason_code"] == NO_ELIGIBLE_CANDIDATE
    assert "svc:nowhere" in reason["detail"]


def test_hard_affinity_child_queues_when_its_host_is_full(tmp_path):
    runtime, _ = _runtime(tmp_path)
    _worker(runtime, "worker-a", "ubuntu2", local_dependency_refs=["svc:ubuntu2"])
    _worker(runtime, "worker-b", "ubuntu2", local_dependency_refs=["svc:ubuntu2"])
    job = _job(runtime, "pinned-1")
    intent = _intent("child", "pinned-1", required_refs=["svc:ubuntu2"])
    lease = _claim(runtime, job, {"ubuntu2": 1}, intent=intent)
    assert lease is not None

    blocked = _job(runtime, "pinned-2")
    blocked_intent = _intent("child", "pinned-2", required_refs=["svc:ubuntu2"])
    assert _claim(runtime, blocked, {"ubuntu2": 1}, intent=blocked_intent) is None
    assert runtime.jobs.get_job(blocked.job_id).status is JobStatus.QUEUED
    reason = runtime.attempts.placement_wait_reason(blocked.job_id)
    assert reason["reason_code"] == "HOST_CAPACITY_EXHAUSTED"
    assert reason["resource_ref"] == "ubuntu2"
    _complete(runtime, lease)
    assert _claim(runtime, blocked, {"ubuntu2": 1}, intent=blocked_intent) is not None


def test_descendant_cap_blocks_the_n_plus_oneth_concurrent_child(tmp_path):
    runtime, _ = _runtime(tmp_path)
    _worker(runtime, "worker-a", "ubuntu0")
    _worker(runtime, "worker-b", "ubuntu0")
    _worker(runtime, "worker-c", "ubuntu0")
    _worker(runtime, "worker-d", "ubuntu0")
    parent = _job(runtime, "coo-1")
    parent_intent = _intent("parent", "coo-1", limit=2)
    lease = _claim(runtime, parent, {"ubuntu0": 4}, intent=parent_intent)
    assert lease is not None  # the parent claims BEFORE its children exist
    start_charges = _charges(runtime, host_slot_pool("ubuntu0"))
    assert start_charges == {host_slot_pool("ubuntu0"): 1}

    children = [_job(runtime, f"child-{n}", parent=parent) for n in (1, 2, 3)]
    leases = []
    for child, number in zip(children, (1, 2, 3)):
        leases.append(_claim(runtime, child, {"ubuntu0": 4},
                             intent=_intent("child", f"child-{number}", limit=2)))
    assert leases[0] is not None and leases[1] is not None
    assert leases[2] is None  # the N+1th concurrent child is refused
    assert runtime.jobs.get_job(children[2].job_id).status is JobStatus.QUEUED
    reason = runtime.attempts.placement_wait_reason(children[2].job_id)
    assert reason["reason_code"] == DESCENDANT_CONCURRENCY_EXHAUSTED
    assert reason["resource_ref"] == parent.job_id  # the root run
    assert _charges(runtime, host_slot_pool("ubuntu0")) == {
        host_slot_pool("ubuntu0"): 3}

    # settle one sibling: the counted cap frees and the queued child places
    _complete(runtime, leases[0])
    retried = _claim(runtime, children[2], {"ubuntu0": 4},
                     intent=_intent("child", "child-3", limit=2))
    assert retried is not None


def test_child_headroom_blocks_a_parent_but_never_a_child(tmp_path):
    runtime, _ = _runtime(tmp_path)
    for worker in ("worker-a", "worker-b", "worker-c", "worker-d"):
        _worker(runtime, worker, "ubuntu1")
    leases = []
    for number in (1, 2, 3):  # three readers HOLD the host but its last slot
        child = _job(runtime, f"reader-{number}")
        leases.append(_claim(runtime, child, {"ubuntu1": 4},
                             intent=_intent("child", f"reader-{number}", limit=10)))
        assert leases[-1] is not None
    assert _charges(runtime, host_slot_pool("ubuntu1")) == {host_slot_pool("ubuntu1"): 3}

    parent = _job(runtime, "coo-waiting")
    blocked = _claim(runtime, parent, {"ubuntu1": 4},
                     intent=_intent("parent", "coo-waiting", limit=5))
    assert blocked is None  # the parent may not consume the headroom slot
    reason = runtime.attempts.placement_wait_reason(parent.job_id)
    assert reason["reason_code"] == PARENT_HEADROOM_EXHAUSTED
    assert reason["resource_ref"] == "ubuntu1"

    fourth = _job(runtime, "reader-4")
    fourth_lease = _claim(runtime, fourth, {"ubuntu1": 4},
                          intent=_intent("child", "reader-4", limit=10))
    assert fourth_lease is not None  # CHILDREN may use the reserved slots
    assert _charges(runtime, host_slot_pool("ubuntu1")) == {host_slot_pool("ubuntu1"): 4}

    # the queued parent stays outside the headroom until child slots free up
    _complete(runtime, fourth_lease)
    assert _claim(runtime, parent, {"ubuntu1": 4},
                  intent=_intent("parent", "coo-waiting", limit=5)) is None
    _complete(runtime, leases[0])
    released = _claim(runtime, parent, {"ubuntu1": 4},
                      intent=_intent("parent", "coo-waiting", limit=5))
    assert released is not None
    assert _charges(runtime, host_slot_pool("ubuntu1")) == {host_slot_pool("ubuntu1"): 3}


def test_env_headroom_frees_parents_when_disabled(tmp_path, monkeypatch):
    monkeypatch.setenv("MMOS_FABRIC_CHILD_HEADROOM", "0")
    runtime, _ = _runtime(tmp_path)
    _worker(runtime, "worker-a", "ubuntu1")
    _worker(runtime, "worker-b", "ubuntu1")
    _worker(runtime, "worker-c", "ubuntu1")
    _worker(runtime, "worker-d", "ubuntu1")
    for n in (1, 2, 3):
        child = _job(runtime, f"reader-{n}")
        assert _claim(runtime, child, {"ubuntu1": 4},
                      intent=_intent("child", f"reader-{n}", limit=10)) is not None
    parent = _job(runtime, "coo-waiting")
    assert _claim(runtime, parent, {"ubuntu1": 4},
                  intent=_intent("parent", "coo-waiting", limit=5)) is not None
    monkeypatch.delenv("MMOS_FABRIC_CHILD_HEADROOM")


def test_fanout_envelope_reserved_at_parents_host_until_settlement(tmp_path):
    runtime, _ = _runtime(tmp_path)
    _worker(runtime, "worker-a", "ubuntu0")
    _worker(runtime, "worker-b", "ubuntu0")
    _worker(runtime, "worker-c", "ubuntu0")
    parent = _job(runtime, "coo-native")
    intent = _intent("parent", "coo-native", policy="bounded_native_fanout",
                     limit=2, profile={"resident_memory_bytes": 1024})
    host_pool = host_slot_pool("ubuntu0")

    lease = _claim(runtime, parent, {"ubuntu0": 3}, intent=intent)

    assert lease is not None
    # ONE commitment holds 1 (own slot) + 2 (envelope) charges at the parent's host
    assert _charges(runtime, host_pool) == {host_pool: 3}
    payload = _claimed_payload(runtime, parent.job_id)
    record = payload["fabric_placement_intent"]
    assert record["envelope_slots"] == 2
    assert record["turn_reservation"]["envelope_slots"] == 2
    assert record["turn_reservation"]["resident_memory_bytes"] == 1024
    commitment = payload["placement_commitment"]
    assert record["digest"]  # the intent record is digest-stamped

    # conservative turn: NO mid-turn release — the envelope holds while the
    # parent waits inside its opaque native turn...
    with runtime.store.read() as connection:
        running = connection.execute(
            "SELECT status FROM attempts WHERE attempt_id=?",
            (lease.attempt.attempt_id,)).fetchone()
    assert running["status"] == AttemptStatus.CLAIMED.value
    assert all(state == "EFFECT_MAY_HAVE_BEGUN" for state in _commitment_states(runtime))
    assert _charges(runtime, host_pool) == {host_pool: 3}

    # ... and releases ONLY at settlement of the whole turn
    _complete(runtime, lease)
    assert _charges(runtime, host_pool) == {host_pool: 0}
    assert all(state == "SETTLED" for state in _commitment_states(runtime))


def test_invalid_fabric_intent_is_refused_before_any_mutation(tmp_path):
    runtime, _ = _runtime(tmp_path)
    _worker(runtime, "worker-a", "ubuntu0")
    job = _job(runtime, "child-1")
    for bad in (
        {"wheel": "re-invented"},
        dict(_intent("child", "child-1"), actor_role="fleet"),
        dict(_intent("child", "child-1"), root_run_id=""),
        dict(_intent("parent", "coo", policy="bounded_native_fanout")),
    ):
        with pytest.raises(StateConflict, match="fabric placement intent"):
            _claim(runtime, job, {"ubuntu0": 1}, intent=bad)
    with pytest.raises(StateConflict, match="requires a child placement Job"):
        runtime.attempts.claim_job(
            runtime.jobs.create_job("legacy").job_id,
            fabric_placement_intent=_intent("child", "c"))
    with runtime.store.read() as connection:
        assert connection.execute("SELECT COUNT(*) FROM attempts").fetchone()[0] == 0
        assert connection.execute(
            "SELECT COUNT(*) FROM events WHERE event_type='JOB_CLAIMED'"
        ).fetchone()[0] == 0
