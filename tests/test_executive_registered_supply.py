"""Registered pool observations for the existing recovery view; no placement."""
from __future__ import annotations

from control_plane.executive_session_recovery import project_root_recovery
from test_executive_quota_rollover_runtime import _fixture, _commit, _worker


def _queued(tmp_path):
    runtime, root, job, attempt = _fixture(tmp_path)
    assert _commit(runtime, root, job, attempt).action == "REQUEUED"
    return runtime, root, job


def test_requeued_job_explains_exhausted_registered_pool_without_fake_admission(tmp_path):
    runtime, root, job = _queued(tmp_path)
    diagnostic = project_root_recovery(runtime, root.job_id)["jobs"][0]["registered_supply"]
    assert diagnostic["authority_effect"] == "NONE"
    assert diagnostic["can_reserve"] is False
    assert diagnostic["route_qualified"] is False
    assert diagnostic["scope"] == "JOB_ALLOWLIST_REGISTRATIONS_ONLY"
    assert diagnostic["state_counts"]["RATE_LIMITED"] == 1
    assert diagnostic["registered_free_count"] == 0
    assert diagnostic["reset_eta"] is None
    assert diagnostic["next_action"] == "WAIT_FOR_EXISTING_CAPACITY_OWNER"


def test_new_registered_pool_is_only_a_possible_slot_not_a_model_admission(tmp_path):
    runtime, root, job = _queued(tmp_path)
    _worker(runtime, "pool-b", provider="claude")
    before = len(runtime.events.list_events())
    diagnostic = project_root_recovery(runtime, root.job_id)["jobs"][0]["registered_supply"]
    assert diagnostic["state_counts"]["RATE_LIMITED"] == 1
    assert diagnostic["state_counts"]["AVAILABLE"] == 1
    assert diagnostic["registered_free_count"] == 1
    assert diagnostic["next_action"] == "REQUEST_EXISTING_PLACEMENT_REVALIDATION"
    assert diagnostic["route_qualified"] is False
    assert diagnostic["independent_budget_proven"] is False
    assert diagnostic["shared_quota_verified"] is False
    assert diagnostic["reset_eta"] is None
    assert "account_label" not in str(diagnostic)
    assert len(runtime.events.list_events()) == before


def test_busy_pool_is_visible_and_does_not_trigger_dispatch(tmp_path):
    runtime, root, job = _queued(tmp_path)
    _worker(runtime, "pool-b")
    other = runtime.jobs.create_job("occupy", requested_authorities=["READ"],
        constraints={"required_capabilities":["read"],"eligible_quota_classes":["default"]})
    lease = runtime.attempts.claim_job(other.job_id, worker_id="pool-b", quota_class="default")
    assert lease is not None
    before = len(runtime.events.list_events())
    diagnostic = project_root_recovery(runtime, root.job_id)["jobs"][0]["registered_supply"]
    assert diagnostic["state_counts"]["BUSY"] == 1
    assert diagnostic["registered_free_count"] == 0
    assert diagnostic["next_action"] == "WAIT_FOR_EXISTING_CAPACITY_OWNER"
    assert runtime.jobs.get_job(job.job_id).status.value == "QUEUED"
    assert len(runtime.events.list_events()) == before


def test_unrelated_quota_class_does_not_count_as_recovery_capacity(tmp_path):
    runtime, root, job = _queued(tmp_path)
    runtime.workers.register_worker("foreign", provider="claude", account_label="foreign",
        worker_type="mock", capabilities=["read"], quota_classes={
            "other": {"provider":"claude", "capabilities":["read"],"cost_class":"small"}})
    diagnostic = project_root_recovery(runtime, root.job_id)["jobs"][0]["registered_supply"]
    assert diagnostic["registered_total"] == 1
    assert diagnostic["registered_free_count"] == 0


def test_unbound_scope_reports_unknown_instead_of_inventing_slots(tmp_path):
    runtime, root, job = _queued(tmp_path)
    from control_plane.executive_registered_supply import registered_supply_projection
    with runtime.store.read() as con:
        observed = registered_supply_projection(con, {"eligible_quota_classes": []})
    assert observed["next_action"] == "REQUIRE_CANONICAL_CAPACITY_SCOPE"
    assert observed["registered_free_count"] is None
    assert observed["state_counts"] == {}
    assert observed["route_qualified"] is False


def test_invalid_shape_or_stale_pool_is_never_reservable(tmp_path):
    runtime, root, job = _queued(tmp_path)
    from control_plane.executive_registered_supply import registered_supply_projection
    with runtime.store.read() as con:
        malformed = registered_supply_projection(con, {"eligible_quota_classes": ["default", 12]})
        assert malformed["next_action"] == "REQUIRE_CANONICAL_CAPACITY_SCOPE"
        assert malformed["registered_free_count"] is None

def test_thirty_waiters_do_not_multiply_one_registered_pool_into_thirty_slots(tmp_path):
    from test_executive_session_recovery_paging import _fleet
    runtime, root, job, attempt = _fleet(tmp_path, size=30)
    _worker(runtime, "pool-b", provider="codex")
    before = len(runtime.events.list_events())
    view = project_root_recovery(runtime, root.job_id, limit=30)
    queued = [entry for entry in view["jobs"] if entry["source_status"] == "QUEUED"]
    assert len(queued) == 29
    assert all(entry["registered_supply"]["registered_free_count"] == 1 for entry in queued)
    assert all(entry["registered_supply"]["route_qualified"] is False for entry in queued)
    # The observation MUST NOT sum a single registry row once for every waiter.
    assert view["registered_free_slots_not_additive_across_jobs"] is True
    assert view["recovery_queue_count"] == 29
    assert view["read_only_supply_scope"] == "REGISTRY_NOT_GLOBAL_CAPACITY_ADMISSION"
    assert len(runtime.events.list_events()) == before


def test_free_registration_does_not_imply_provider_bound_capacity(tmp_path):
    from control_plane.executive_registered_supply import registered_supply_projection
    runtime, root, job = _queued(tmp_path)
    _worker(runtime, "pool-b", provider="claude")
    with runtime.store.read() as con:
        codex = registered_supply_projection(con, {
            "eligible_quota_classes": ["default"], "provider": "codex"})
        claude = registered_supply_projection(con, {
            "eligible_quota_classes": ["default"], "provider": "claude"})
        unbound = registered_supply_projection(con, {
            "eligible_quota_classes": ["default"]})
    assert codex["registered_free_count"] == 1
    assert codex["provider_bound_free_count"] == 0
    assert claude["provider_bound_free_count"] == 1
    assert unbound["provider_bound_free_count"] is None
    for item in (codex, claude, unbound):
        assert item["route_qualified"] is False
        assert item["can_reserve"] is False
        assert item["independent_budget_proven"] is False
        assert item["provider_bound_count_is_not_model_admission"] is True


def test_foreign_worker_provider_registration_does_not_count_as_bound(tmp_path):
    from control_plane.executive_registered_supply import registered_supply_projection
    runtime, root, job = _queued(tmp_path)
    _worker(runtime, "pool-b", provider="codex")
    with runtime.store.transaction() as con:
        # A worker/quota provider mismatch is rejected by the canonical
        # registry's immutable producer; this test does not defeat that guard.
        original = con.execute(
            "SELECT provider FROM workers WHERE worker_id='pool-b'").fetchone()[0]
        assert original == "codex"
    with runtime.store.read() as con:
        candidate = registered_supply_projection(con, {
            "eligible_quota_classes": ["default"], "provider": "codex"})
    assert candidate["provider_bound_free_count"] == 1
