"""WO-14 (MMOS V1): claim_job is the sole atomic placement authority.

OQ-1: Executive ``AttemptRegistry.claim_job`` reserves host slot + root
concurrency + every shared quota resource in ONE transaction, binds
attempt/host/route/fence_counter and issues ``ExecutionBinding.v1`` at the
JOB_CLAIMED ``claim_payload``.  The deployed Fabric lease broker is an
observation source only.  Required cases (Rev 4 l.146):

* stale fence -> settlement refused
* host cap exceeded -> no claim
* shared bucket exhausted -> queued with reason
* pre-start refusal -> original claim released
"""
from __future__ import annotations

import hashlib
import json
import sqlite3

import pytest

from control_plane.child_execution_contracts import (
    ChildExecutionRequest,
    ExecutionBinding,
)
from control_plane.executive_placement_authority import (
    HostObservation,
    PlacementObservations,
    SharedQuotaObservation,
    host_slot_pool,
    observations_from_projection,
    read_lease_broker_observation,
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


def _worker(runtime: Runtime, worker_id: str, host_id: str) -> None:
    runtime.workers.register_worker(
        worker_id, provider="codex", account_label=f"acct-{worker_id}",
        worker_type="mock", capabilities=["code"], metadata={"host_id": host_id},
    )


def _request(key: str) -> ChildExecutionRequest:
    return ChildExecutionRequest(
        root_ref="hermes-root-1", immediate_parent_run_ref="hermes-run-7",
        logical_child_key=key, task_kind="code",
        requested_complexity="C1_ROUTINE_BOUNDED",
        budget_grant_ref="grant-ref-1",
    )


def _spec(key: str, *, refs=(QUOTA,), revision: str = REVISION) -> dict:
    return {
        "child_execution_request": _request(key).to_dict(),
        "effective_complexity": "C1_ROUTINE_BOUNDED",
        "registry_revision": revision,
        "route": {"provider_ref": "codex", "pool_ref": "glm"},
        "shared_quota_resource_refs": list(refs),
        "root_concurrency_limit": 32,
    }


def _job(runtime: Runtime, key: str, **spec_kwargs):
    return runtime.jobs.create_job(
        f"placement child {key}", constraints={"child_placement": _spec(key, **spec_kwargs)}
    )


def _observations(*, hosts=None, cap: int = 4, external: int = 0, now: int = NOW,
                  cooldown_until_ms=None, revision: str = REVISION) -> PlacementObservations:
    hosts = hosts if hosts is not None else {"ubuntu0": 1}
    return PlacementObservations(
        registry_revision=revision, observed_at_ms=now,
        hosts={h: HostObservation(host_id=h, boot_id=f"boot-{h}", eligible_slots=n,
                                  observed_at_ms=now) for h, n in hosts.items()},
        shared_quota={QUOTA: SharedQuotaObservation(
            resource_ref=QUOTA, per_account_cap=cap, external_active_leases=external,
            cooldown_until_ms=cooldown_until_ms)},
    )


def _charges(runtime: Runtime, *pools: str) -> dict[str, int]:
    with runtime.store.read() as connection:
        live = ResourceBroker(runtime.store)._placement_pool_charges(connection, pools)
    return {pool: live.get(pool, 0) for pool in pools}


def _commitments(runtime: Runtime) -> list[dict]:
    with runtime.store.read() as connection:
        return [dict(r) for r in connection.execute(
            "SELECT * FROM physical_resource_commitments ORDER BY created_at_ms,commitment_id")]


def _quota_row(runtime: Runtime, worker_id: str) -> dict:
    with runtime.store.read() as connection:
        return dict(connection.execute(
            "SELECT * FROM worker_quota_classes WHERE worker_id=?", (worker_id,)).fetchone())


# --- the binding --------------------------------------------------------------

def test_claim_reserves_host_root_and_quota_in_one_commitment_and_issues_binding(tmp_path):
    runtime, _ = _runtime(tmp_path)
    _worker(runtime, "worker-a", "ubuntu0")
    job = _job(runtime, "child-1")

    lease = runtime.attempts.claim_job(job.job_id, placement_observations=_observations())

    assert lease is not None
    attempt = lease.attempt
    raw = runtime.attempts.execution_binding(attempt.attempt_id)
    binding = ExecutionBinding.from_dict(raw)
    assert binding.binds_request(_request("child-1"))
    assert binding.attempt_ref == attempt.attempt_id
    assert binding.job_ref == job.job_id
    assert binding.fence_counter == attempt.fence_generation == _quota_row(runtime, "worker-a")["fence_counter"]
    assert (binding.host_id, binding.worker_id, binding.host_boot_id) == ("ubuntu0", "worker-a", "boot-ubuntu0")
    assert binding.shared_quota_resource_refs == (QUOTA,)
    assert binding.provider_ref == "codex" and binding.pool_ref == "glm"
    assert binding.assignment_generation == attempt.attempt_number == 1
    # One physical commitment carries every demand, BEGUN by the claim.
    rows = _commitments(runtime)
    assert len(rows) == 1
    assert rows[0]["state"] == "EFFECT_MAY_HAVE_BEGUN" and rows[0]["carrier_id"] == attempt.attempt_id
    assert _charges(runtime, host_slot_pool("ubuntu0"), root_concurrency_pool(job.job_id),
                    shared_quota_pool(QUOTA)) == {
        host_slot_pool("ubuntu0"): 1, root_concurrency_pool(job.job_id): 1,
        shared_quota_pool(QUOTA): 1}
    claimed = [e for e in runtime.store.list_events(job_id=job.job_id) if e.event_type == "JOB_CLAIMED"]
    assert len(claimed) == 1
    assert claimed[0].payload["execution_binding"] == raw
    assert claimed[0].payload["placement_commitment"]["begin_event_id"] == rows[0]["begin_event_id"]


def test_legacy_claim_is_unchanged_and_refuses_observations(tmp_path):
    runtime, _ = _runtime(tmp_path)
    _worker(runtime, "worker-a", "ubuntu0")
    legacy = runtime.jobs.create_job("legacy work")
    with pytest.raises(StateConflict, match="child placement Job"):
        runtime.attempts.claim_job(legacy.job_id, placement_observations=_observations())
    lease = runtime.attempts.claim_job(legacy.job_id)
    assert lease is not None
    assert runtime.attempts.execution_binding(lease.attempt.attempt_id) is None
    assert _commitments(runtime) == []
    runtime.attempts.complete_attempt(
        lease.attempt.attempt_id, fence_generation=lease.attempt.fence_generation,
        lease_token=lease.lease_token, payload={"summary": "ok"})


# --- required case 1: stale fence -> settlement refused --------------------------

def test_stale_fence_settlement_is_refused_and_holds_the_reservation(tmp_path):
    runtime, _ = _runtime(tmp_path)
    _worker(runtime, "worker-a", "ubuntu0")
    job = _job(runtime, "child-1")
    lease = runtime.attempts.claim_job(job.job_id, placement_observations=_observations())
    attempt = lease.attempt

    for bad_fence in (attempt.fence_generation + 1, attempt.fence_generation + 7):
        with pytest.raises(StateConflict):
            runtime.attempts.complete_attempt(
                attempt.attempt_id, fence_generation=bad_fence,
                lease_token=lease.lease_token, payload={"summary": "stale"})
        with pytest.raises(StateConflict):
            runtime.attempts.fail_attempt(
                attempt.attempt_id, fence_generation=bad_fence,
                lease_token=lease.lease_token, payload={"error": "stale"})
    # Nothing settled: Attempt live, reservation still held.
    assert runtime.attempts.get_attempt(attempt.attempt_id).status is AttemptStatus.CLAIMED
    assert _commitments(runtime)[0]["state"] == "EFFECT_MAY_HAVE_BEGUN"

    runtime.attempts.complete_attempt(
        attempt.attempt_id, fence_generation=attempt.fence_generation,
        lease_token=lease.lease_token, payload={"summary": "done"})
    row = _commitments(runtime)[0]
    assert row["state"] == "SETTLED" and row["settlement_event_id"] is not None
    assert _charges(runtime, host_slot_pool("ubuntu0"), shared_quota_pool(QUOTA)) == {
        host_slot_pool("ubuntu0"): 0, shared_quota_pool(QUOTA): 0}
    # Settlement happens exactly once: a replayed settlement is refused.
    with pytest.raises(StateConflict):
        runtime.attempts.complete_attempt(
            attempt.attempt_id, fence_generation=attempt.fence_generation,
            lease_token=lease.lease_token, payload={"summary": "again"})


def test_superseded_attempt_fence_cannot_settle_after_reclaim(tmp_path):
    runtime, _ = _runtime(tmp_path)
    _worker(runtime, "worker-a", "ubuntu0")
    job = _job(runtime, "child-1")
    first = runtime.attempts.claim_job(job.job_id, placement_observations=_observations())
    runtime.attempts.release_unstarted_claim(
        first.attempt.attempt_id, fence_generation=first.attempt.fence_generation,
        lease_token=first.lease_token, reason="local pressure recheck refused")
    second = runtime.attempts.claim_job(job.job_id, placement_observations=_observations())
    assert second.attempt.fence_generation == first.attempt.fence_generation + 1

    with pytest.raises(StateConflict):
        runtime.attempts.complete_attempt(
            first.attempt.attempt_id, fence_generation=first.attempt.fence_generation,
            lease_token=first.lease_token, payload={"summary": "zombie"})
    with pytest.raises(StateConflict):
        runtime.attempts.complete_attempt(
            second.attempt.attempt_id, fence_generation=first.attempt.fence_generation,
            lease_token=second.lease_token, payload={"summary": "old fence"})
    binding = ExecutionBinding.from_dict(runtime.attempts.execution_binding(second.attempt.attempt_id))
    assert binding.fence_counter == second.attempt.fence_generation
    assert binding.assignment_generation == 2


# --- required case 2: host cap exceeded -> no claim ------------------------------

def test_host_cap_exceeded_makes_no_claim(tmp_path):
    runtime, _ = _runtime(tmp_path)
    _worker(runtime, "worker-a", "ubuntu0")
    _worker(runtime, "worker-b", "ubuntu0")
    first = runtime.attempts.claim_job(
        _job(runtime, "child-1").job_id, placement_observations=_observations())
    job = _job(runtime, "child-2")

    assert runtime.attempts.claim_job(job.job_id, placement_observations=_observations()) is None

    assert runtime.jobs.get_job(job.job_id).status is JobStatus.QUEUED
    assert runtime.attempts.list_attempts(job.job_id) == []
    assert _quota_row(runtime, "worker-b")["held_attempt_id"] is None
    assert _quota_row(runtime, "worker-b")["status"] == "AVAILABLE"
    assert len(_commitments(runtime)) == 1
    reason = runtime.attempts.placement_wait_reason(job.job_id)
    assert reason["reason_code"] == "HOST_CAPACITY_EXHAUSTED"
    assert reason["resource_ref"] == "ubuntu0"
    # Releasing the slot lets the queued Job place.
    runtime.attempts.complete_attempt(
        first.attempt.attempt_id, fence_generation=first.attempt.fence_generation,
        lease_token=first.lease_token, payload={"summary": "done"})
    assert runtime.attempts.claim_job(job.job_id, placement_observations=_observations()) is not None


def test_host_without_eligible_slots_never_claims_and_skips_to_eligible_host(tmp_path):
    runtime, _ = _runtime(tmp_path)
    _worker(runtime, "worker-a", "m2-studio")
    job = _job(runtime, "child-1")
    obs = _observations(hosts={"m2-studio": 0, "ubuntu1": 2})
    assert runtime.attempts.claim_job(job.job_id, placement_observations=obs) is None
    assert runtime.attempts.placement_wait_reason(job.job_id)["reason_code"] == "HOST_CAPACITY_EXHAUSTED"
    _worker(runtime, "worker-b", "ubuntu1")
    lease = runtime.attempts.claim_job(job.job_id, placement_observations=obs)
    assert lease.attempt.worker_id == "worker-b"
    assert runtime.attempts.placement_wait_reason(job.job_id) is None


# --- required case 3: shared bucket exhausted -> queued with reason --------------

def test_shared_bucket_exhausted_by_observed_leases_is_queued_with_reason(tmp_path):
    runtime, _ = _runtime(tmp_path)
    _worker(runtime, "worker-a", "ubuntu0")
    job = _job(runtime, "child-1")

    assert runtime.attempts.claim_job(
        job.job_id, placement_observations=_observations(cap=2, external=2)) is None

    assert runtime.jobs.get_job(job.job_id).status is JobStatus.QUEUED
    reason = runtime.attempts.placement_wait_reason(job.job_id)
    assert reason["reason_code"] == "SHARED_QUOTA_EXHAUSTED"
    assert reason["resource_ref"] == QUOTA
    assert reason["detail"] == "2/2 held"
    assert _commitments(runtime) == []
    # Unchanged reason is deduplicated (no event spam per poll).
    runtime.attempts.claim_job(job.job_id, placement_observations=_observations(cap=2, external=2))
    deferrals = [e for e in runtime.store.list_events(aggregate_type="job_placement",
                                                      aggregate_id=job.job_id)]
    assert len(deferrals) == 1


def test_shared_bucket_exhausted_by_executive_holds_across_hosts(tmp_path):
    runtime, _ = _runtime(tmp_path)
    _worker(runtime, "worker-a", "ubuntu0")
    _worker(runtime, "worker-b", "ubuntu1")
    obs = _observations(hosts={"ubuntu0": 2, "ubuntu1": 2}, cap=1)
    assert runtime.attempts.claim_job(_job(runtime, "child-1").job_id, placement_observations=obs)
    job = _job(runtime, "child-2")
    assert runtime.attempts.claim_job(job.job_id, placement_observations=obs) is None
    assert runtime.attempts.placement_wait_reason(job.job_id)["reason_code"] == "SHARED_QUOTA_EXHAUSTED"


def test_account_cooldown_registry_drift_and_stale_observations_queue_with_reason(tmp_path):
    runtime, clock = _runtime(tmp_path)
    _worker(runtime, "worker-a", "ubuntu0")
    job = _job(runtime, "child-1")
    cases = [
        (_observations(cooldown_until_ms=NOW + 60_000), "ACCOUNT_COOLDOWN"),
        (_observations(revision="registry-rev-2"), "REGISTRY_REVISION_MOVED"),
        (_observations(now=NOW - 120_000), "OBSERVATIONS_STALE"),
        (None, "PLACEMENT_OBSERVATIONS_UNAVAILABLE"),
    ]
    for observations, code in cases:
        assert runtime.attempts.claim_job(job.job_id, placement_observations=observations) is None
        assert runtime.attempts.placement_wait_reason(job.job_id)["reason_code"] == code
    assert _commitments(runtime) == []


# --- required case 4: pre-start refusal -> original claim released ---------------

def test_pre_start_refusal_releases_the_original_claim_exactly_once(tmp_path):
    runtime, _ = _runtime(tmp_path)
    _worker(runtime, "worker-a", "ubuntu0")
    job = _job(runtime, "child-1")
    lease = runtime.attempts.claim_job(job.job_id, placement_observations=_observations())
    attempt = lease.attempt

    with pytest.raises(StateConflict):  # stale fence cannot release
        runtime.attempts.release_unstarted_claim(
            attempt.attempt_id, fence_generation=attempt.fence_generation + 1,
            lease_token=lease.lease_token, reason="host pressure")
    released = runtime.attempts.release_unstarted_claim(
        attempt.attempt_id, fence_generation=attempt.fence_generation,
        lease_token=lease.lease_token, reason="host pressure")

    assert released.status is JobStatus.QUEUED
    assert runtime.attempts.get_attempt(attempt.attempt_id).status is AttemptStatus.FAILED
    quota = _quota_row(runtime, "worker-a")
    assert quota["held_attempt_id"] is None and quota["status"] == "AVAILABLE"
    row = _commitments(runtime)[0]
    assert row["state"] == "SETTLED"
    assert _charges(runtime, host_slot_pool("ubuntu0"), root_concurrency_pool(job.job_id),
                    shared_quota_pool(QUOTA)) == {
        host_slot_pool("ubuntu0"): 0, root_concurrency_pool(job.job_id): 0,
        shared_quota_pool(QUOTA): 0}
    with runtime.store.read() as connection:
        settle = json.loads(connection.execute(
            "SELECT payload_json FROM events WHERE event_id=?",
            (row["settlement_event_id"],)).fetchone()[0])
    assert settle["receipt"]["evidence"]["placement_release"] == "PRE_START_REFUSED:host pressure"
    with pytest.raises(StateConflict):  # exactly once
        runtime.attempts.release_unstarted_claim(
            attempt.attempt_id, fence_generation=attempt.fence_generation,
            lease_token=lease.lease_token, reason="host pressure")
    again = runtime.attempts.claim_job(job.job_id, placement_observations=_observations())
    assert again is not None and again.attempt.attempt_id != attempt.attempt_id


def test_started_attempt_cannot_use_pre_start_release(tmp_path):
    runtime, _ = _runtime(tmp_path)
    _worker(runtime, "worker-a", "ubuntu0")
    lease = runtime.attempts.claim_job(
        _job(runtime, "child-1").job_id, placement_observations=_observations())
    with runtime.store.transaction() as connection:
        connection.execute("UPDATE attempts SET status='RUNNING' WHERE attempt_id=?",
                           (lease.attempt.attempt_id,))
    with pytest.raises(StateConflict):
        runtime.attempts.release_unstarted_claim(
            lease.attempt.attempt_id, fence_generation=lease.attempt.fence_generation,
            lease_token=lease.lease_token, reason="too late")
    assert _commitments(runtime)[0]["state"] == "EFFECT_MAY_HAVE_BEGUN"


# --- REVIEW_2314 M-1: supervisor adoption re-issues the binding --------------------

def _record_process(runtime: Runtime, attempt_id: str) -> None:
    with runtime.store.transaction() as connection:  # what a supervisor START records
        connection.execute(
            "UPDATE attempts SET pid=4242,pgid=4242,process_start_identity='probe',"
            "boot_id='boot-probe' WHERE attempt_id=?", (attempt_id,))


def _settle_events(runtime: Runtime) -> list:
    return [e for e in runtime.store.list_events()
            if e.command_id and e.command_id.startswith("physical:placement:")
            and e.command_id.endswith(":settle")]


def test_adopted_attempt_settlement(tmp_path):
    runtime, _ = _runtime(tmp_path)
    _worker(runtime, "worker-a", "ubuntu0")
    job = _job(runtime, "child-1")
    lease = runtime.attempts.claim_job(job.job_id, placement_observations=_observations())
    attempt_id = lease.attempt.attempt_id
    claimed = ExecutionBinding.from_dict(runtime.attempts.execution_binding(attempt_id))
    _record_process(runtime, attempt_id)

    adopted = runtime.attempts.adopt_attempt(
        attempt_id, expected_fence_generation=lease.attempt.fence_generation,
        lease_owner="supervisor-2")

    assert adopted.attempt.fence_generation == lease.attempt.fence_generation + 1
    current = ExecutionBinding.from_dict(runtime.attempts.execution_binding(attempt_id))
    # Re-issued atomically at adoption: only the fence (and lease expiry) move.
    assert current.fence_counter == adopted.attempt.fence_generation
    assert current.fence_counter == _quota_row(runtime, "worker-a")["fence_counter"]
    assert current.lease_expiry
    assert {k: v for k, v in current.to_dict().items()
            if k not in {"fence_counter", "lease_expiry"}} == {
        k: v for k, v in claimed.to_dict().items()
        if k not in {"fence_counter", "lease_expiry"}}
    adoption = [e for e in runtime.store.list_events(job_id=job.job_id)
                if e.event_type == "ATTEMPT_ADOPTED"]
    assert len(adoption) == 1
    assert adoption[0].payload["execution_binding"] == current.to_dict()
    # The pre-restart owner is stale at both settlement verbs; nothing settles.
    with pytest.raises(StateConflict):
        runtime.attempts.complete_attempt(
            attempt_id, fence_generation=lease.attempt.fence_generation,
            lease_token=lease.lease_token, payload={"summary": "zombie"})
    with pytest.raises(StateConflict):
        runtime.attempts.fail_attempt(
            attempt_id, fence_generation=lease.attempt.fence_generation,
            lease_token=lease.lease_token, payload={"error": "zombie"})
    assert _commitments(runtime)[0]["state"] == "EFFECT_MAY_HAVE_BEGUN"

    runtime.attempts.complete_attempt(
        attempt_id, fence_generation=adopted.attempt.fence_generation,
        lease_token=adopted.lease_token, payload={"summary": "done"})

    assert runtime.attempts.get_attempt(attempt_id).status is AttemptStatus.COMPLETED
    assert _commitments(runtime)[0]["state"] == "SETTLED"
    assert _charges(runtime, host_slot_pool("ubuntu0"), root_concurrency_pool(job.job_id),
                    shared_quota_pool(QUOTA)) == {
        host_slot_pool("ubuntu0"): 0, root_concurrency_pool(job.job_id): 0,
        shared_quota_pool(QUOTA): 0}
    with pytest.raises(StateConflict):  # exactly once
        runtime.attempts.fail_attempt(
            attempt_id, fence_generation=adopted.attempt.fence_generation,
            lease_token=adopted.lease_token, payload={"error": "again"})
    assert len(_settle_events(runtime)) == 1

    # A second restart chains the re-issue; fail_attempt settles exactly once.
    other = _job(runtime, "child-2")
    lease2 = runtime.attempts.claim_job(other.job_id, placement_observations=_observations())
    _record_process(runtime, lease2.attempt.attempt_id)
    first = runtime.attempts.adopt_attempt(
        lease2.attempt.attempt_id, expected_fence_generation=lease2.attempt.fence_generation,
        lease_owner="supervisor-2")
    second = runtime.attempts.adopt_attempt(
        lease2.attempt.attempt_id, expected_fence_generation=first.attempt.fence_generation,
        lease_owner="supervisor-3")
    binding = ExecutionBinding.from_dict(runtime.attempts.execution_binding(lease2.attempt.attempt_id))
    assert binding.fence_counter == second.attempt.fence_generation
    with pytest.raises(StateConflict):
        runtime.attempts.fail_attempt(
            lease2.attempt.attempt_id, fence_generation=first.attempt.fence_generation,
            lease_token=first.lease_token, payload={"error": "superseded adopter"})
    runtime.attempts.fail_attempt(
        lease2.attempt.attempt_id, fence_generation=second.attempt.fence_generation,
        lease_token=second.lease_token, payload={"error": "failed"})
    assert [r["state"] for r in _commitments(runtime)] == ["SETTLED", "SETTLED"]
    assert len(_settle_events(runtime)) == 2


# --- REVIEW_2314 M-2: cancel + lease expiry settles the placement ----------------

def test_cancel_after_lease_expiry_settles_placement(tmp_path):
    runtime, clock = _runtime(tmp_path)
    _worker(runtime, "worker-a", "ubuntu0")
    job = _job(runtime, "child-1")
    lease = runtime.attempts.claim_job(job.job_id, placement_observations=_observations())
    runtime.jobs.cancel_job(job.job_id)
    clock.value = NOW + 10 * 60_000  # past the lease

    runtime.attempts.reconcile_expired()

    assert runtime.jobs.get_job(job.job_id).status is JobStatus.CANCELLED
    assert runtime.attempts.get_attempt(lease.attempt.attempt_id).status is AttemptStatus.LOST
    assert _quota_row(runtime, "worker-a")["held_attempt_id"] is None
    row = _commitments(runtime)[0]
    assert row["state"] == "SETTLED" and row["settlement_event_id"] is not None
    with runtime.store.read() as connection:
        settle = json.loads(connection.execute(
            "SELECT payload_json FROM events WHERE event_id=?",
            (row["settlement_event_id"],)).fetchone()[0])
    assert settle["receipt"]["evidence"]["placement_release"] == "LEASE_EXPIRED"
    assert _charges(runtime, host_slot_pool("ubuntu0"), root_concurrency_pool(job.job_id),
                    shared_quota_pool(QUOTA)) == {
        host_slot_pool("ubuntu0"): 0, root_concurrency_pool(job.job_id): 0,
        shared_quota_pool(QUOTA): 0}
    # Exactly once: a second reconcile pass and the dead verbs settle nothing more.
    runtime.attempts.reconcile_expired()
    with pytest.raises(Exception):
        runtime.jobs.requeue_job(job.job_id)
    assert len(_settle_events(runtime)) == 1
    # The freed host slot admits new work (worker-a's quota class is ERROR).
    _worker(runtime, "worker-b", "ubuntu0")
    fresh = _job(runtime, "child-2")
    assert runtime.attempts.claim_job(
        fresh.job_id, placement_observations=_observations(now=clock.value)) is not None


def test_lost_after_lease_expiry_holds_placement_until_requeue(tmp_path):
    """m-1: the non-cancel expiry branch keeps quota custody, so the placement
    commitment stays held too; requeue_job is the single release owner."""
    runtime, clock = _runtime(tmp_path)
    _worker(runtime, "worker-a", "ubuntu0")
    job = _job(runtime, "child-1")
    runtime.attempts.claim_job(job.job_id, placement_observations=_observations())
    clock.value = NOW + 10 * 60_000
    runtime.attempts.reconcile_expired()
    assert runtime.jobs.get_job(job.job_id).status is JobStatus.LOST
    assert _commitments(runtime)[0]["state"] == "EFFECT_MAY_HAVE_BEGUN"
    runtime.jobs.requeue_job(job.job_id)
    assert _commitments(runtime)[0]["state"] == "SETTLED"
    assert len(_settle_events(runtime)) == 1


# --- OQ-1: the deployed lease broker is an observation source only -----------------

def _lease_db(path) -> None:
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE leases (id TEXT PRIMARY KEY, orchestrator_id TEXT NOT NULL,
          pool TEXT NOT NULL, account TEXT NOT NULL, task_class TEXT NOT NULL,
          host TEXT NOT NULL, pid INTEGER NOT NULL, granted_at REAL NOT NULL,
          ttl INTEGER NOT NULL, last_heartbeat REAL NOT NULL, state TEXT NOT NULL,
          renewable INTEGER NOT NULL DEFAULT 1, model TEXT NOT NULL DEFAULT '',
          quota_outcome_sha256 TEXT, quota_scope TEXT, purpose TEXT NOT NULL DEFAULT 'WORKER');
        CREATE TABLE quota_cooldowns (scope TEXT PRIMARY KEY, observed_at REAL NOT NULL,
          until_ts REAL NOT NULL, failures INTEGER NOT NULL, kind TEXT NOT NULL,
          source_run TEXT NOT NULL, reset_source TEXT NOT NULL,
          mode TEXT NOT NULL DEFAULT 'HARD', soft_cap INTEGER);
        """)
    rows = [("l1", "held", "glm:chairman-max"), ("l2", "rented", "glm:chairman-max"),
            ("l3", "released", "glm:chairman-max"), ("l4", "held", "bailian:Ryan")]
    for lease_id, state, scope in rows:
        pool, account = scope.split(":")
        connection.execute(
            "INSERT INTO leases(id,orchestrator_id,pool,account,task_class,host,pid,granted_at,"
            "ttl,last_heartbeat,state,quota_scope) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (lease_id, "orch", pool, account, "code", "m2", 1, 1.0, 60, 1.0, state, scope))
    connection.execute(
        "INSERT INTO quota_cooldowns VALUES('bailian-adaptive429:Ryan',1.0,?,3,'unknown','r','x','HARD',NULL)",
        ((NOW + 60_000) / 1000,))
    connection.commit()
    connection.close()


def test_lease_broker_is_read_only_observation_feeding_the_claim(tmp_path):
    db = tmp_path / "leases.sqlite"
    _lease_db(db)
    before = hashlib.sha256(db.read_bytes()).hexdigest()

    observed = read_lease_broker_observation(db)

    assert hashlib.sha256(db.read_bytes()).hexdigest() == before
    assert observed["active_leases"] == {"glm:chairman-max": 2, "bailian:Ryan": 1}
    projection = {
        "registry_revision": REVISION,
        "shared_quota_resources": [
            {"provider": "glm", "account_name": "chairman-max", "enabled_flag": True,
             "per_account_cap": 2, "parked_until": None, "has_credential_ref": True},
            {"provider": "bailian", "account_name": "Ryan", "enabled_flag": True,
             "per_account_cap": 7, "parked_until": None, "has_credential_ref": True},
            # WO-03 emits a supplementary usage row for the same account; it
            # must never overwrite the account's cap/readiness.
            {"provider": "bailian", "account_name": "Ryan", "kind": "inline_key_bucket",
             "pct_7d": 98.56},
        ],
    }
    snapshot = {"schema": "mastermind.host_readiness_snapshot/v1", "host_id": "ubuntu0",
                "reachable": True, "observed_at_utc": "2027-01-15T08:00:00Z",
                "uptime_s": 100, "eligible_slots": 2, "proposed_worker_slots": 4,
                "proposed_thresholds": {"no_new_claims_after_s": 45}}
    host = HostObservation.from_host_readiness_snapshot(snapshot)
    obs = observations_from_projection(projection, host_snapshots=[snapshot],
                                       lease_observation=observed,
                                       observed_at_ms=host.observed_at_ms)
    assert obs.shared_quota[QUOTA].external_active_leases == 2
    assert obs.shared_quota["bailian:Ryan"].cooldown_until_ms == NOW + 60_000
    ryan = obs.shared_quota["bailian:Ryan"]
    assert (ryan.per_account_cap, ryan.enabled, ryan.credential_ready) == (7, True, True)
    assert ryan.window_usage_pct == 98.56
    assert obs.hosts["ubuntu0"].eligible_slots == 2  # never the proposed count

    runtime, clock = _runtime(tmp_path / "rt")
    clock.value = host.observed_at_ms
    _worker(runtime, "worker-a", "ubuntu0")
    job = _job(runtime, "child-1")
    assert runtime.attempts.claim_job(job.job_id, placement_observations=obs) is None
    assert runtime.attempts.placement_wait_reason(job.job_id)["reason_code"] == "SHARED_QUOTA_EXHAUSTED"
    assert hashlib.sha256(db.read_bytes()).hexdigest() == before
    with pytest.raises(sqlite3.OperationalError):
        ro = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
        try:
            ro.execute("DELETE FROM leases")
        finally:
            ro.close()


def test_unenrolled_snapshot_has_zero_eligible_slots():
    snapshot = {"schema": "mastermind.host_readiness_snapshot/v1", "host_id": "m2-studio",
                "reachable": True, "observed_at_utc": "2026-11-08T14:14:16Z",
                "uptime_s": 10, "eligible_slots": 0, "proposed_worker_slots": 0,
                "proposed_thresholds": {"no_new_claims_after_s": 45}}
    assert HostObservation.from_host_readiness_snapshot(snapshot).eligible_slots == 0
    unreachable = dict(snapshot, reachable=False, eligible_slots=3)
    assert HostObservation.from_host_readiness_snapshot(unreachable).eligible_slots == 0


def test_invalid_child_placement_spec_is_refused_at_creation(tmp_path):
    runtime, _ = _runtime(tmp_path)
    bad = _spec("child-1")
    bad["shared_quota_resource_refs"] = ["no-colon"]
    with pytest.raises(StateConflict, match="child placement"):
        runtime.jobs.create_job("bad", constraints={"child_placement": bad})
    tampered = _spec("child-1")
    tampered["child_execution_request"] = dict(tampered["child_execution_request"],
                                               logical_child_key="other")
    with pytest.raises(StateConflict, match="child placement"):
        runtime.jobs.create_job("bad", constraints={"child_placement": tampered})


# --- WO-17: the canonical decision ledger + correlated Hermes mmx-router JSONL --

from control_plane.child_execution_contracts import DecisionEvent  # noqa: E402
from control_plane.executive_decision_ledger import (  # noqa: E402
    JSONL_CORRELATION_KEYS, correlation_report, decision_event_from_claim,
    decision_for_attempt, decision_id_for_binding, decisions_for_job,
    hermes_jsonl_line, record_claim_decision,
)


def test_claimed_attempt_yields_one_correlated_decision_pair(tmp_path):
    """End-to-end: a real claim's JOB_CLAIMED record projects into the one
    shared decision schema, attaches to the Job/Attempt records, and
    correlates key-by-key to its mmx-router JSONL line."""
    runtime, clock = _runtime(tmp_path)
    _worker(runtime, "worker-a", "ubuntu0")
    job = _job(runtime, "child-1")

    lease = runtime.attempts.claim_job(job.job_id, placement_observations=_observations())
    assert lease is not None
    attempt = lease.attempt
    claimed = [e for e in runtime.store.list_events(job_id=job.job_id)
               if e.event_type == "JOB_CLAIMED"]
    assert len(claimed) == 1
    binding = ExecutionBinding.from_dict(claimed[0].payload["execution_binding"])

    # The canonical decision attaches to the existing Job/Attempt records,
    # idempotent by decision_id, without touching the Job event chain.
    with runtime.store.transaction() as connection:
        event = record_claim_decision(
            runtime.store, connection, job_id=job.job_id,
            claim_payload=claimed[0].payload, timestamp=clock(),
            spec=_spec("child-1"))
    assert event.event_kind == "binding_issued"
    assert event.decision_id == decision_id_for_binding(binding)
    assert event.attempt_ref == attempt.attempt_id == binding.attempt_ref
    assert event.fence_counter == binding.fence_counter == attempt.fence_generation
    assert (event.root_run_ref, event.immediate_parent_run_ref, event.logical_child_key) == (
        "hermes-root-1", "hermes-run-7", "child-1")
    assert event.effective_complexity == binding.effective_complexity == "C1_ROUTINE_BOUNDED"
    assert event.requested_complexity == "C1_ROUTINE_BOUNDED"
    # readable back from both record identities
    assert decision_for_attempt(runtime.store, attempt.attempt_id).decision_id == event.decision_id
    assert [d.decision_id for d in decisions_for_job(runtime.store, job.job_id)] == [event.decision_id]
    with runtime.store.transaction() as connection:
        replay = record_claim_decision(
            runtime.store, connection, job_id=job.job_id,
            claim_payload=claimed[0].payload, timestamp=clock(),
            spec=_spec("child-1"))
    assert replay.decision_id == event.decision_id
    assert len(decisions_for_job(runtime.store, job.job_id)) == 1
    claimed_after = [e for e in runtime.store.list_events(job_id=job.job_id)
                     if e.event_type == "JOB_CLAIMED"]
    assert len(claimed_after) == 1  # the Job chain itself is untouched

    # The correlated Hermes mmx-router JSONL line: base router fields verbatim,
    # correlation keys matching the Executive record on every key.
    line = hermes_jsonl_line(
        event, t="2026-11-08T12:00:00-0700", requested="routine", served="routine",
        task_class="C1", downgraded=False, note=None,
        capacity="capacity: no-input (no capacity_file configured)",
        route="byteplus-coding/deepseek-v4-1-flash-261017")
    report = correlation_report(event, line)
    assert set(report) == set(JSONL_CORRELATION_KEYS)
    assert all(entry["match"] for entry in report.values()), report
    parsed = json.loads(line)
    assert parsed["schema"] == event.to_dict()["schema"]
    assert parsed["requested"] == "routine" and parsed["served"] == "routine"
    assert parsed["route"] == "byteplus-coding/deepseek-v4-1-flash-261017"
    # A legacy router line with no correlation keys is uncorrelated, never
    # placement evidence; the Executive record stays the sole authority.
    legacy = json.dumps({"t": "2026-11-08T12:00:00-0700", "requested": "routine",
                         "served": "routine", "task_class": "C1", "downgraded": False,
                         "route": "byteplus-coding/deepseek-v4-1-flash-261017"})
    report = correlation_report(event, legacy)
    assert not any(entry["match"] for entry in report.values())


def test_decision_projection_refuses_a_claim_without_a_binding(tmp_path):
    runtime, _ = _runtime(tmp_path)
    with pytest.raises(ValueError, match="no ExecutionBinding"):
        decision_event_from_claim(job_id="legacy-job", claim_payload={"status": "RUNNING"})


# --- Rev 5 v1.1 (Director C): t3-native ExecutionBinding join at claim ----------

def _t3_spec(key: str) -> dict:
    spec = _spec(key)
    spec["route"] = {
        "provider_ref": "codex", "pool_ref": "glm", "adapter_id": "t3-native",
    }
    return spec


def test_t3_native_claim_issues_v1_1_binding_with_t3_idempotency_join(tmp_path):
    """Rev 5 §3A/§7: a t3-native route descriptor makes the claim-time
    binding itself carry the native idempotency join — runtime_kind from
    the registered descriptor, operation_key = the binding-derived T3
    clientRequestId — derived inside the SAME claim transaction, so a
    coordinator restart or lost reply replays the same upstream command
    key. caller_namespace stays EMPTY (REVIEW_C_E_OPUS_20261109 A2): the
    claim knows no OAuth principal; the adapter's port attests it at
    launch (see the claim->adapter equality test below)."""
    from control_plane.child_execution_contracts import EXECUTION_BINDING_SCHEMA_V1_1
    from control_plane.t3_execution_adapter import derive_t3_client_request_id

    runtime, _ = _runtime(tmp_path)
    runtime.workers.register_worker(
        "worker-t3", provider="codex", account_label="acct-t3",
        worker_type="mock", capabilities=["code"],
        quota_classes={"default": {"capabilities": ["code"],
                                     "metadata": {"adapter_id": "t3-native"}}},
        metadata={"host_id": "ubuntu0"},
    )
    job = runtime.jobs.create_job(
        "t3 placement child", constraints={"child_placement": _t3_spec("t3-child-1")}
    )

    lease = runtime.attempts.claim_job(
        job.job_id, placement_observations=_observations()
    )

    assert lease is not None
    raw = runtime.attempts.execution_binding(lease.attempt.attempt_id)
    assert raw is not None
    binding = ExecutionBinding.from_dict(raw)
    # The v1 identity is unchanged; only the v1.1 extension joins.
    assert binding.binds_request(_request("t3-child-1"))
    assert binding.schema == EXECUTION_BINDING_SCHEMA_V1_1
    assert binding.runtime_kind == "t3-native"
    assert binding.adapter_id == "t3-native"
    # A2: never the adapter's fixed namespace (which the adapter would wrap
    # a second time) and never an invented principal.
    assert binding.caller_namespace == ""
    assert raw["caller_namespace"] == ""
    # The persisted operation key IS the adapter's deterministic derivation
    # over this same binding — the join the adapter must reproduce at
    # launch, byte for byte, never a fresh key.
    assert binding.operation_key == derive_t3_client_request_id(binding)
    assert len(binding.operation_key) == 64 and binding.operation_key.islower()
    # The claim payload carries the joined v1.1 binding verbatim.
    claimed = [e for e in runtime.store.list_events(job_id=job.job_id)
               if e.event_type == "JOB_CLAIMED"]
    assert claimed[0].payload["execution_binding"] == raw
    assert claimed[0].payload["execution_binding"]["runtime_kind"] == "t3-native"



class _AttestingT3Port:
    """Fake T3NativeClientPort that records every envelope it is sent and,
    when given a principal, attests it through ``authenticated_namespace``
    (the OAuth client the real port authenticates with)."""

    def __init__(self, principal: str | None) -> None:
        self.envelopes: list = []
        if principal is not None:
            self.authenticated_namespace = lambda: principal

    async def launch_thread(self, envelope):
        from control_plane.t3_execution_adapter import T3ThreadLaunchReceipt

        self.envelopes.append(envelope)
        return T3ThreadLaunchReceipt(
            thread_id="thr-claim-1", run_id="t3run-claim-1", project_id="proj-1",
            status="running", link="https://t3.example/thread/thr-claim-1",
            created_at="2026-11-09T12:00:00+00:00",
            request_namespace=envelope.request_namespace,
            client_request_id=envelope.client_request_id,
        )

    async def read_thread(self, thread_id, run_id, cursor):  # pragma: no cover
        raise AssertionError("not exercised")

    async def interrupt_run(self, ref, reason):  # pragma: no cover
        raise AssertionError("not exercised")

    async def replay_launch(self, envelope):  # pragma: no cover
        raise AssertionError("not exercised")


class _NullInspector:
    def boot_session_id(self) -> str:
        return "boot-1"

    def identity(self, pid: int) -> tuple[str, int]:
        return (f"identity-{pid}", pid)

    def inspect(self, pid: int) -> object:
        return {"pid": pid}


@pytest.mark.parametrize("principal", ["oauth-client-X", None],
                         ids=["port-attests-principal", "port-without-principal"])
def test_t3_claim_binding_and_real_adapter_agree_on_namespace_and_key(
    tmp_path, principal
):
    """A2 claim->adapter equality: the binding claim_job issues is fed to
    the REAL T3ExecutionAdapter. One story, byte for byte: the binding's
    caller_namespace is empty, the namespace on the wire is exactly what
    the PORT attests (principal-qualified — never the fixed namespace
    wrapped in itself), and the clientRequestId on the wire is the claim's
    operation_key. The adapter's DURABLE launch record (a second store
    instance reading the same SQLite file) holds that same namespace/key
    and the same claim binding. A port that attests NO principal cannot
    prove which OAuth client's idempotency identity it runs under, so the
    reviewed adapter refuses the launch before any native call (audit #3,
    re-audit FIXED_CONFIRMED): nothing is sent and nothing is launched."""
    import asyncio
    from datetime import datetime, timezone
    from pathlib import Path

    from control_plane.t3_execution_adapter import (
        SQLiteT3AdapterStateStore,
        T3_REQUEST_NAMESPACE,
        T3ExecutionAdapter,
        t3_request_namespace,
    )
    from control_plane.worker_execution_contract import WorkerLaunchSpec

    runtime, _ = _runtime(tmp_path)
    runtime.workers.register_worker(
        "worker-t3", provider="codex", account_label="acct-t3",
        worker_type="mock", capabilities=["code"],
        quota_classes={"default": {"capabilities": ["code"],
                                     "metadata": {"adapter_id": "t3-native"}}},
        metadata={"host_id": "ubuntu0"},
    )
    job = runtime.jobs.create_job(
        "t3 namespace child", constraints={"child_placement": _t3_spec("t3-ns-1")}
    )
    lease = runtime.attempts.claim_job(job.job_id, placement_observations=_observations())
    raw = runtime.attempts.execution_binding(lease.attempt.attempt_id)
    claimed = [e for e in runtime.store.list_events(job_id=job.job_id)
               if e.event_type == "JOB_CLAIMED"][0].payload["execution_binding"]
    assert claimed == raw
    binding = ExecutionBinding.from_dict(raw)
    assert binding.caller_namespace == "" and raw["caller_namespace"] == ""

    port = _AttestingT3Port(principal)
    state_path = tmp_path / "t3_adapter_state.sqlite3"
    adapter = T3ExecutionAdapter(
        port, lambda spec: binding, _NullInspector(),
        clock=lambda: datetime.fromtimestamp(NOW / 1000, tz=timezone.utc),
        state_store=SQLiteT3AdapterStateStore(state_path),
    )
    spec = WorkerLaunchSpec(
        run_id=lease.attempt.attempt_id, job_id=job.job_id,
        worker_id=binding.worker_id, workspace_path=Path("/tmp/mmos-t3-ws"),
        run_dir=tmp_path / "run", prompt="bounded child",
        result_schema_path=tmp_path / "run" / "schema.json",
    )
    if principal is None:
        from control_plane.t3_execution_adapter import T3NamespaceAttestationError
        with pytest.raises(T3NamespaceAttestationError):
            asyncio.run(adapter.start(spec))
        assert port.envelopes == []
        durable = SQLiteT3AdapterStateStore(state_path).load_run(spec.run_id)
        assert durable is None or durable.receipt is None
        return
    asyncio.run(adapter.start(spec))

    expected_namespace = f"{T3_REQUEST_NAMESPACE}:oauth-client-X"
    assert expected_namespace == t3_request_namespace(principal)
    [envelope] = port.envelopes
    assert envelope.request_namespace == expected_namespace
    assert envelope.request_namespace.count(T3_REQUEST_NAMESPACE) == 1
    assert envelope.client_request_id == binding.operation_key == raw["operation_key"]

    durable = SQLiteT3AdapterStateStore(state_path).load_run(spec.run_id)
    assert durable.intent.request_namespace == envelope.request_namespace
    assert durable.intent.client_request_id == envelope.client_request_id
    assert durable.receipt.request_namespace == envelope.request_namespace
    assert durable.binding == binding
    assert durable.binding.to_dict() == raw


def test_plain_adapter_route_stays_a_v1_binding(tmp_path):
    """The join is scoped to the t3-native seam: a registered non-t3
    adapter (codex-cli) and an adapter-less route both claim unchanged v1
    bindings with no native extension fields."""
    runtime, _ = _runtime(tmp_path)
    runtime.workers.register_worker(
        "worker-codex", provider="codex", account_label="acct-codex",
        worker_type="mock", capabilities=["code"],
        quota_classes={"default": {"capabilities": ["code"],
                                     "metadata": {"adapter_id": "codex-cli"}}},
        metadata={"host_id": "ubuntu0"},
    )
    codex_spec = _spec("codex-child-1")
    codex_spec["route"] = {
        "provider_ref": "codex", "pool_ref": "glm", "adapter_id": "codex-cli",
    }
    job = runtime.jobs.create_job(
        "codex placement child", constraints={"child_placement": codex_spec}
    )
    lease = runtime.attempts.claim_job(
        job.job_id, placement_observations=_observations()
    )
    binding = ExecutionBinding.from_dict(
        runtime.attempts.execution_binding(lease.attempt.attempt_id)
    )
    assert binding.runtime_kind == "" and binding.operation_key == ""
    assert binding.caller_namespace == "" and binding.schema == "ExecutionBinding.v1"

    _worker(runtime, "worker-plain", "ubuntu1")
    plain = _job(runtime, "plain-child-1")
    plain_lease = runtime.attempts.claim_job(
        plain.job_id,
        placement_observations=_observations(
            hosts={"ubuntu0": 1, "ubuntu1": 1}),
    )
    plain_binding = ExecutionBinding.from_dict(
        runtime.attempts.execution_binding(plain_lease.attempt.attempt_id)
    )
    assert plain_binding.schema == "ExecutionBinding.v1"
    assert not plain_binding._has_v1_1_extensions


def test_unknown_route_adapter_fails_closed_inside_the_claim_transaction(tmp_path):
    """An adapter id that is not a reviewed descriptor refuses the claim
    with a typed StateConflict INSIDE the transaction: the placement
    commitment rolls back with it and the Job stays QUEUED — never a
    half-claimed attempt or an unattributable native launch."""
    runtime, _ = _runtime(tmp_path)
    runtime.workers.register_worker(
        "worker-bogus", provider="codex", account_label="acct-bogus",
        worker_type="mock", capabilities=["code"],
        quota_classes={"default": {"capabilities": ["code"],
                                     "metadata": {"adapter_id": "definitely-not-an-adapter"}}},
        metadata={"host_id": "ubuntu0"},
    )
    bogus_spec = _spec("bogus-child-1")
    bogus_spec["route"] = {
        "provider_ref": "codex", "pool_ref": "glm",
        "adapter_id": "definitely-not-an-adapter",
    }
    job = runtime.jobs.create_job(
        "bogus placement child", constraints={"child_placement": bogus_spec}
    )
    with pytest.raises(StateConflict, match="not a reviewed adapter"):
        runtime.attempts.claim_job(
            job.job_id, placement_observations=_observations()
        )
    assert _commitments(runtime) == []
    with runtime.store.read() as connection:
        status = connection.execute(
            "SELECT status FROM jobs WHERE job_id=?", (job.job_id,)
        ).fetchone()["status"]
        attempts = connection.execute(
            "SELECT COUNT(*) AS n FROM attempts WHERE job_id=?", (job.job_id,)
        ).fetchone()["n"]
    assert status == JobStatus.QUEUED.value and attempts == 0


def test_workspace_lease_join_stamps_containment_by_contract(tmp_path):
    """Rev 5 §4 join (Director C): attach_workspace_lease stamps the
    binding's v1.1 workspace-containment block from ONE real lease record
    (real SQLite store in a temp dir; no launch of any kind) — the
    binding's workspace_ref/base_ref/writer_epoch/lease_ref ARE the lease's
    values, t3_workspace_id stays the lease-side native join field, and a
    non-active lease refuses."""
    from control_plane.t3_execution_adapter import derive_t3_client_request_id
    from control_plane.workspace_lease import (
        WorkspaceLeaseStore,
        attach_workspace_lease,
    )

    runtime, _ = _runtime(tmp_path)
    runtime.workers.register_worker(
        "worker-t3", provider="codex", account_label="acct-t3",
        worker_type="mock", capabilities=["code"],
        quota_classes={"default": {"capabilities": ["code"],
                                     "metadata": {"adapter_id": "t3-native"}}},
        metadata={"host_id": "ubuntu0"},
    )
    job = runtime.jobs.create_job(
        "t3 workspace child", constraints={"child_placement": _t3_spec("t3-ws-1")}
    )
    lease = runtime.attempts.claim_job(
        job.job_id, placement_observations=_observations()
    )
    binding = ExecutionBinding.from_dict(
        runtime.attempts.execution_binding(lease.attempt.attempt_id)
    )
    assert binding.operation_key == derive_t3_client_request_id(binding)

    store = WorkspaceLeaseStore(str(tmp_path / "workspace-leases.sqlite"))
    record = store.acquire_single_writer(
        repo_ref="github.com:mastermindx/Mastermind", host_ref="ubuntu0",
        native_workspace_owner="t3-native",
        workspace_ref="workspace:///mastermind/t3-ws-1",
        base_revision="a" * 40, writer_ref="writer-t3-1",
        active_assignment_refs=(lease.attempt.attempt_id,),
        t3_workspace_id="t3ws-7f3a", now_ms=NOW,
    )
    joined = attach_workspace_lease(binding, record, now_ms=NOW)
    assert (joined.workspace_ref, joined.base_ref) == (
        record.workspace_ref, record.base_revision)
    assert (joined.writer_epoch, joined.lease_ref) == (
        record.writer_epoch, record.lease_id)
    # The lease-side native join field survives the round trip: the binding
    # reaches t3_workspace_id through lease_ref, and this module never
    # fabricates it into the binding.
    assert record.t3_workspace_id == "t3ws-7f3a"
    assert joined.lease_ref == record.lease_id
    # Joining again is idempotent; the input binding is unchanged.
    assert attach_workspace_lease(joined, record, now_ms=NOW) == joined
    assert binding.workspace_ref == "" and binding.lease_ref == ""

    store.release(record.lease_id, writer_epoch=record.writer_epoch, now_ms=NOW + 1)
    with pytest.raises(Exception, match="LEASE_NOT_ACTIVE"):
        attach_workspace_lease(joined, dataclasses_replace_status(record), now_ms=NOW)
    store.close()



def _claimed_t3_binding_and_lease(tmp_path, *, key: str, expires_ms=None,
                                  assignment_refs=None):
    from control_plane.workspace_lease import WorkspaceLeaseStore

    runtime, _ = _runtime(tmp_path)
    runtime.workers.register_worker(
        "worker-t3", provider="codex", account_label="acct-t3",
        worker_type="mock", capabilities=["code"],
        quota_classes={"default": {"capabilities": ["code"],
                                     "metadata": {"adapter_id": "t3-native"}}},
        metadata={"host_id": "ubuntu0"},
    )
    job = runtime.jobs.create_job(
        "t3 lease child", constraints={"child_placement": _t3_spec(key)}
    )
    lease = runtime.attempts.claim_job(job.job_id, placement_observations=_observations())
    binding = ExecutionBinding.from_dict(
        runtime.attempts.execution_binding(lease.attempt.attempt_id)
    )
    store = WorkspaceLeaseStore(str(tmp_path / "workspace-leases.sqlite"))
    refs = (lease.attempt.attempt_id,) if assignment_refs is None else assignment_refs
    record = store.acquire_single_writer(
        repo_ref="github.com:mastermindx/Mastermind", host_ref="ubuntu0",
        native_workspace_owner="t3-native",
        workspace_ref=f"workspace:///mastermind/{key}",
        base_revision="a" * 40, writer_ref=f"writer-{key}",
        active_assignment_refs=refs, now_ms=NOW, expires_ms=expires_ms,
    )
    return binding, record, store


def test_workspace_lease_join_refuses_an_active_but_expired_lease(tmp_path):
    """A3: lease_status alone used to admit an active lease whose expiry had
    passed (expires_ms=1). Expiry is judged against the injected now_ms."""
    from control_plane.workspace_lease import WorkspaceLeaseConflict, attach_workspace_lease

    binding, record, store = _claimed_t3_binding_and_lease(
        tmp_path, key="t3-exp-1", expires_ms=NOW + 60_000)
    assert attach_workspace_lease(binding, record, now_ms=NOW).lease_ref == record.lease_id
    for now in (NOW + 60_000, NOW + 60_001):  # at and after expiry
        with pytest.raises(WorkspaceLeaseConflict, match="LEASE_EXPIRED") as caught:
            attach_workspace_lease(binding, record, now_ms=now)
        assert caught.value.details["expires_ms"] == NOW + 60_000
    import dataclasses as _dc
    with pytest.raises(WorkspaceLeaseConflict, match="LEASE_EXPIRED"):
        attach_workspace_lease(binding, _dc.replace(record, expires_ms=1), now_ms=NOW)
    # The clock is required and typed (module convention: injected epoch-ms).
    with pytest.raises(TypeError):
        attach_workspace_lease(binding, record)
    for bad in (None, "1", -1, 1.5, True):
        with pytest.raises(WorkspaceLeaseConflict, match="INVALID_VALUE"):
            attach_workspace_lease(binding, record, now_ms=bad)
    store.close()


def test_workspace_lease_join_refuses_a_lease_assigned_to_another_attempt(tmp_path):
    """A3: active_assignment_refs naming a DIFFERENT attempt (or none) does
    not contain this binding's attempt — refused, never silently joined."""
    from control_plane.workspace_lease import WorkspaceLeaseConflict, attach_workspace_lease

    binding, record, store = _claimed_t3_binding_and_lease(
        tmp_path, key="t3-asg-1", assignment_refs=("ATT-someone-else",))
    with pytest.raises(WorkspaceLeaseConflict, match="LEASE_ASSIGNMENT_MISMATCH") as caught:
        attach_workspace_lease(binding, record, now_ms=NOW)
    assert caught.value.details["attempt_ref"] == binding.attempt_ref
    assert caught.value.details["active_assignment_refs"] == ["ATT-someone-else"]
    import dataclasses as _dc
    with pytest.raises(WorkspaceLeaseConflict, match="LEASE_ASSIGNMENT_MISMATCH"):
        attach_workspace_lease(binding, _dc.replace(record, active_assignment_refs=()),
                               now_ms=NOW)
    # Naming this attempt among others contains it.
    shared = _dc.replace(record, active_assignment_refs=("ATT-other", binding.attempt_ref))
    assert attach_workspace_lease(binding, shared, now_ms=NOW).lease_ref == record.lease_id
    store.close()


def test_workspace_lease_join_refuses_rebinding_to_a_different_lease(tmp_path):
    """A3: re-attaching a DIFFERENT lease used to replace lease_ref /
    workspace_ref silently. Now LEASE_REBIND_REFUSED; the same lease stays
    idempotent; a drifted same-id lease and pre-stamped containment refuse."""
    import dataclasses as _dc

    from control_plane.workspace_lease import WorkspaceLeaseConflict, attach_workspace_lease

    binding, record, store = _claimed_t3_binding_and_lease(tmp_path, key="t3-rb-1")
    joined = attach_workspace_lease(binding, record, now_ms=NOW)
    assert attach_workspace_lease(joined, record, now_ms=NOW) == joined
    other = _dc.replace(record, lease_id="lease-other",
                        workspace_ref="workspace:///mastermind/elsewhere")
    with pytest.raises(WorkspaceLeaseConflict, match="LEASE_REBIND_REFUSED") as caught:
        attach_workspace_lease(joined, other, now_ms=NOW)
    assert caught.value.details["bound_lease_ref"] == record.lease_id
    drifted = _dc.replace(record, writer_epoch=(record.writer_epoch or 0) + 1)
    with pytest.raises(WorkspaceLeaseConflict, match="LEASE_REBIND_REFUSED"):
        attach_workspace_lease(joined, drifted, now_ms=NOW)
    pre_stamped = _dc.replace(binding, workspace_ref="workspace:///mastermind/forged")
    with pytest.raises(WorkspaceLeaseConflict, match="LEASE_REBIND_REFUSED"):
        attach_workspace_lease(pre_stamped, record, now_ms=NOW)
    # The refused attempts left the joined binding untouched.
    assert joined.lease_ref == record.lease_id
    store.close()


def dataclasses_replace_status(record):
    import dataclasses as _dc
    from control_plane.workspace_lease import STATUS_RELEASED
    return _dc.replace(record, lease_status=STATUS_RELEASED)
