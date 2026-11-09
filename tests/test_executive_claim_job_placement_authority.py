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
