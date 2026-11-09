"""Rev5 WorkspaceLease store: safety and eligibility contracts."""
from __future__ import annotations

import dataclasses
import json
import threading

import pytest

from control_plane import workspace_lease
from control_plane.workspace_lease import (
    KIND_ISOLATED_WORKTREE,
    KIND_READ_SNAPSHOT,
    KIND_SINGLE_WRITER,
    RETENTION_CLEAN,
    RETENTION_DIRTY,
    RETENTION_DIRTY_RETAINED,
    WorkspaceLeaseConflict,
    WorkspaceLeaseStore,
    allocations_blocked_under_pressure,
    host_cache_key,
    reclaim_eligible,
    workspace_lease_attach,
)

REPO = "gh:mastermind/fabric"
HOST = "host-a"
NOW = 1_700_000_000_000
REV = "a" * 40


def _fresh(path):
    return WorkspaceLeaseStore(path)


def _open(tmp_path, name):
    store = WorkspaceLeaseStore(str(tmp_path / name))
    return store


def test_one_writer_per_mutable_checkout(tmp_path):
    store = _open(tmp_path, "lease.sqlite")
    winner = store.acquire_single_writer(
        repo_ref=REPO, host_ref=HOST, native_workspace_owner="t3-workspace-1",
        workspace_ref="ws-1", base_revision=REV, writer_ref="worker-alpha",
        reserved_scratch_bytes=1024, now_ms=NOW, expires_ms=NOW + 60_000,
    )
    assert winner.writer_epoch == 1
    assert winner.lease_kind == KIND_SINGLE_WRITER
    loser = WorkspaceLeaseStore(str(tmp_path / "lease.sqlite"))
    try:
        with pytest.raises(WorkspaceLeaseConflict) as caught:
            loser.acquire_single_writer(
                repo_ref=REPO, host_ref=HOST, native_workspace_owner="t3-workspace-2",
                workspace_ref="ws-2", base_revision=REV, writer_ref="worker-beta",
                now_ms=NOW,
            )
    finally:
        loser.close()
    conflict = caught.value
    assert conflict.reason == "SINGLE_WRITER_ALREADY_HELD"
    assert conflict.details["writer_ref"] == "worker-alpha"
    assert conflict.details["writer_epoch"] == 1
    conflict.as_dict()

    # after release, a sequential writer lease takes over with a NEW epoch
    store.release(winner.lease_id, writer_epoch=1, now_ms=NOW + 1000)
    second = store.acquire_single_writer(
        repo_ref=REPO, host_ref=HOST, native_workspace_owner="t3-workspace-2",
        workspace_ref="ws-2", base_revision=REV, writer_ref="worker-beta", now_ms=NOW + 2000,
    )
    assert second.writer_epoch == 2
    assert second.writer_ref == "worker-beta"


def test_concurrent_acquire_single_writer_one_winner_precise_conflict(tmp_path):
    path = str(tmp_path / "lease.sqlite")
    handles = [WorkspaceLeaseStore(path), WorkspaceLeaseStore(path)]
    barrier = threading.Barrier(2, timeout=30)
    results = {}
    lock = threading.Lock()

    def attempt(index, writer):
        try:
            barrier.wait()
            record = handles[index].acquire_single_writer(
                repo_ref=REPO, host_ref=HOST, native_workspace_owner=f"owner-{writer}",
                workspace_ref=f"ws-{writer}", base_revision=REV, writer_ref=writer,
                now_ms=NOW,
            )
            with lock:
                results[index] = ("won", record)
        except WorkspaceLeaseConflict as conflict:
            with lock:
                results[index] = ("conflict", conflict)
        except Exception as error:  # pragma: no cover - diagnostics only
            with lock:
                results[index] = ("error", error)

    threads = [threading.Thread(target=attempt, args=(0, "worker-alpha")),
               threading.Thread(target=attempt, args=(1, "worker-beta"))]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(30)
    for handle in handles:
        handle.close()

    markers = sorted(item[0] for item in results.values())
    assert markers == ["conflict", "won"]
    winner = next(item for item in results.values() if item[0] == "won")[1]
    loser = next(item for item in results.values() if item[0] == "conflict")[1]
    assert loser.reason == "SINGLE_WRITER_ALREADY_HELD"
    assert loser.details["writer_ref"] == winner.writer_ref
    assert loser.details["writer_epoch"] == winner.writer_epoch
    assert loser.details["writer_epoch"] is not None


def test_isolated_worktrees_bounded_with_precise_refusal(tmp_path, monkeypatch):
    store = _open(tmp_path, "lease.sqlite")
    monkeypatch.setenv("MMOS_WORKSPACE_ISOLATED_WORKTREE_CAP", "2")
    first = store.acquire_isolated_worktree(
        repo_ref=REPO, host_ref=HOST, native_workspace_owner="t3-workspace-1",
        workspace_ref="iso-1", base_revision=REV, writer_ref="worker-a", now_ms=NOW)
    assert first.lease_kind == KIND_ISOLATED_WORKTREE
    assert first.writer_epoch is None
    store.acquire_isolated_worktree(
        repo_ref=REPO, host_ref=HOST, native_workspace_owner="t3-workspace-2",
        workspace_ref="iso-2", base_revision=REV, writer_ref="worker-b", now_ms=NOW)
    with pytest.raises(WorkspaceLeaseConflict) as caught:
        store.acquire_isolated_worktree(
            repo_ref=REPO, host_ref=HOST, native_workspace_owner="t3-workspace-3",
            workspace_ref="iso-3", base_revision=REV, writer_ref="worker-c", now_ms=NOW)
    conflict = caught.value
    assert conflict.reason == "ISOLATED_WORKTREE_CAP_EXCEEDED"
    assert conflict.details["cap"] == 2
    assert conflict.details["active_isolated_worktrees"] == 2

    # a different host is a separate bound
    other_host = store.acquire_isolated_worktree(
        repo_ref=REPO, host_ref="host-b", native_workspace_owner="t3-workspace-4",
        workspace_ref="iso-4", base_revision=REV, writer_ref="worker-d", now_ms=NOW)
    assert other_host.host_ref == "host-b"
    with monkeypatch.context() as scope:
        scope.delenv("MMOS_WORKSPACE_ISOLATED_WORKTREE_CAP", raising=False)
        assert store.isolated_worktree_cap() == workspace_lease.DEFAULT_ISOLATED_WORKTREE_CAP == 4


def test_readers_never_conflict_with_writer_and_never_blocked(tmp_path):
    store = _open(tmp_path, "lease.sqlite")
    writer = store.acquire_single_writer(
        repo_ref=REPO, host_ref=HOST, native_workspace_owner="t3-workspace-1",
        workspace_ref="ws-1", base_revision=REV, writer_ref="worker-alpha", now_ms=NOW)
    reader_one = store.register_read_snapshot(
        repo_ref=REPO, host_ref=HOST, native_workspace_owner="t3-workspace-2",
        workspace_ref="reader-1", base_revision=REV, now_ms=NOW)
    reader_two = store.register_read_snapshot(
        repo_ref=REPO, host_ref=HOST, native_workspace_owner="t3-workspace-3",
        workspace_ref="reader-2", base_revision=REV, now_ms=NOW)
    assert reader_one.lease_kind == KIND_READ_SNAPSHOT
    assert reader_two.writer_ref is None and reader_one.writer_epoch is None
    assert writer.lease_status == "active"
    # read-only snapshots never gate: registering under disk pressure is fine
    allocations_blocked_under_pressure(store, disk_pressure=True)
    reader_three = store.register_read_snapshot(
        repo_ref=REPO, host_ref=HOST, native_workspace_owner="t3-workspace-4",
        workspace_ref="reader-3", base_revision=REV, now_ms=NOW)
    _ = reader_three
    with pytest.raises(WorkspaceLeaseConflict) as caught:
        store.acquire_isolated_worktree(
            repo_ref=REPO, host_ref=HOST, native_workspace_owner="o",
            workspace_ref="iso-x", base_revision=REV, writer_ref="w", now_ms=NOW)
    assert caught.value.reason == "ALLOCATIONS_BLOCKED_DISK_PRESSURE"


def test_release_with_stale_epoch_refused_with_writer_identity(tmp_path):
    store = _open(tmp_path, "lease.sqlite")
    lease = store.acquire_single_writer(
        repo_ref=REPO, host_ref=HOST, native_workspace_owner="owner",
        workspace_ref="ws-1", base_revision=REV, writer_ref="worker-alpha", now_ms=NOW)
    with pytest.raises(WorkspaceLeaseConflict) as caught:
        store.release(lease.lease_id, writer_epoch=99, now_ms=NOW + 1)
    conflict = caught.value
    assert conflict.reason == "STALE_WRITER_RELEASE"
    assert conflict.details["writer_ref"] == "worker-alpha"
    assert conflict.details["writer_epoch"] == 1
    assert conflict.details["supplied_writer_epoch"] == 99
    # release with the live epoch works and keeps the retention artifacts
    released = store.release(lease.lease_id, writer_epoch=1, now_ms=NOW + 2,
                             retention_state=RETENTION_DIRTY_RETAINED,
                             result_artifact_refs=["patch:abc", "dir:out"])
    assert released.lease_status == "released"
    assert released.retention_state == RETENTION_DIRTY_RETAINED
    assert released.result_artifact_refs == ("patch:abc", "dir:out")


def test_renew_with_wrong_epoch_refused(tmp_path):
    store = _open(tmp_path, "lease.sqlite")
    lease = store.acquire_single_writer(
        repo_ref=REPO, host_ref=HOST, native_workspace_owner="owner",
        workspace_ref="ws-1", base_revision=REV, writer_ref="worker-alpha",
        now_ms=NOW, expires_ms=NOW + 1000)
    with pytest.raises(WorkspaceLeaseConflict) as caught:
        store.renew(lease.lease_id, writer_epoch=7, now_ms=NOW + 10, expires_ms=NOW + 9000)
    conflict = caught.value
    assert conflict.reason == "WRITER_EPOCH_MISMATCH"
    assert conflict.details["writer_epoch"] == 1
    assert conflict.details["supplied_writer_epoch"] == 7
    renewed = store.renew(lease.lease_id, writer_epoch=1, now_ms=NOW + 20, expires_ms=NOW + 9000)
    assert renewed.expires_ms == NOW + 9000
    with pytest.raises(WorkspaceLeaseConflict) as caught:
        store.renew(lease.lease_id, now_ms=NOW + 30, expires_ms=NOW + 10_000)
    assert caught.value.reason == "WRITER_EPOCH_REQUIRED"


def eligible_state(**overrides):
    base = {"workspace_ref": "ws-1", "native_activity_settled": True,
            "live_writer": False, "unresolved_effects": False,
            "retention_state": RETENTION_DIRTY_RETAINED, "active_assignments": ()}
    base.update(overrides)
    return base


def test_reclaim_eligibility_matrix():
    # settled + no writer + no unresolved effects + retained -> eligible
    ok = reclaim_eligible([eligible_state()], now_ms=NOW)
    assert [entry["workspace_ref"] for entry in ok["eligible"]] == ["ws-1"]
    assert ok["ineligible"] == []
    assert "settled_native_activity" in ok["eligible"][0]["reasons"]

    # expiry alone never establishes safety: expired but no settled activity
    not_ok = reclaim_eligible(
        [eligible_state(lease_expired=True, native_activity_settled=False)], now_ms=NOW)
    assert not_ok["eligible"] == []
    assert not_ok["ineligible"][0]["blocked_by"] == ["native_activity_not_settled"]

    # expired but all four safety conditions hold is eligible on those alone
    expired_safe = reclaim_eligible(
        [eligible_state(lease_expired=True)], now_ms=NOW)
    assert [entry["workspace_ref"] for entry in expired_safe["eligible"]] == ["ws-1"]

    # live writer -> never eligible, even settled+retained
    blocked_writer = reclaim_eligible([eligible_state(live_writer=True)], now_ms=NOW)
    assert blocked_writer["eligible"] == []
    assert blocked_writer["ineligible"][0]["blocked_by"] == ["live_writer_present"]

    # dirty-not-retained -> never eligible
    dirty = reclaim_eligible(
        [eligible_state(retention_state=RETENTION_DIRTY)], now_ms=NOW)
    assert dirty["eligible"] == []
    assert dirty["ineligible"][0]["blocked_by"] == ["retention_state_not_reclaimable"]

    # unresolved effects -> not eligible
    unresolved = reclaim_eligible([eligible_state(unresolved_effects=True)], now_ms=NOW)
    assert unresolved["ineligible"][0]["blocked_by"] == ["unresolved_effects_present"]

    # settled miss -> not eligible
    unsettled = reclaim_eligible([eligible_state(native_activity_settled=False)], now_ms=NOW)
    assert unsettled["ineligible"][0]["blocked_by"] == ["native_activity_not_settled"]

    # still-assigned (active or uncertain) -> preserved, not eligible
    assigned = reclaim_eligible(
        [eligible_state(active_assignments=("assign-9",))], now_ms=NOW)
    assert assigned["ineligible"][0]["blocked_by"] == ["active_assignments_present"]

    # records are accepted directly
    record = workspace_lease.WorkspaceLeaseRecord(
        repo_ref=REPO, host_ref=HOST, native_workspace_owner="owner",
        workspace_ref="ws-r", base_revision=REV, writer_ref="w", writer_epoch=1,
        active_assignment_refs=(), reserved_scratch_bytes=0, observed_bytes=0,
        retention_state=RETENTION_CLEAN, result_artifact_refs=(),
        lease_kind=KIND_SINGLE_WRITER, lease_id="lease-r",
        native_activity_settled=True, unresolved_effects=False,
        lease_status="released", expires_ms=None)
    from_record = reclaim_eligible([record], now_ms=NOW)
    assert [entry["workspace_ref"] for entry in from_record["eligible"]] == ["ws-r"]


def test_no_second_sweeper_no_deletion_anywhere():
    """The lease module is ownership/eligibility only: no filesystem work."""
    import inspect
    source = inspect.getsource(workspace_lease)
    for token in ("os.remove", "unlink", "rmtree", "shutil"):
        assert token not in source, f"forbidden token present: {token}"


def test_store_driven_reclaim_view_and_pressure_posture(tmp_path):
    store = _open(tmp_path, "lease.sqlite")
    lease = store.acquire_single_writer(
        repo_ref=REPO, host_ref=HOST, native_workspace_owner="owner",
        workspace_ref="ws-live", base_revision=REV, writer_ref="worker-alpha",
        now_ms=NOW, expires_ms=NOW - 1, )  # expired while still held
    posture = allocations_blocked_under_pressure(store, disk_pressure=True)
    assert posture["allocations_blocked"] is True
    assert "ws-live" in posture["preserve_active_or_uncertain"]
    with pytest.raises(WorkspaceLeaseConflict):
        store.acquire_single_writer(
            repo_ref=REPO, host_ref="host-b", native_workspace_owner="o",
            workspace_ref="ws-other", base_revision=REV, writer_ref="w", now_ms=NOW)
    # drain the known owner: release with retained dirty output, settle, resolve
    store.release(lease.lease_id, writer_epoch=1, now_ms=NOW + 1,
                  retention_state=RETENTION_DIRTY_RETAINED)
    store.record_native_activity_settled(lease.lease_id, now_ms=NOW + 2)
    store.record_effects_resolved(lease.lease_id, now_ms=NOW + 3)
    view = store.reclaim_view(now_ms=NOW + 4)
    decision = reclaim_eligible(view, now_ms=NOW + 4)
    assert [entry["workspace_ref"] for entry in decision["eligible"]] == ["ws-live"]
    posture_after = allocations_blocked_under_pressure(store, disk_pressure=True)
    assert "ws-live" in posture_after["drain_candidates"]
    allocations_blocked_under_pressure(store, disk_pressure=False)
    assert store.allocations_blocked is False
    reopened = store.acquire_single_writer(
        repo_ref=REPO, host_ref="host-b", native_workspace_owner="o",
        workspace_ref="ws-other", base_revision=REV, writer_ref="w", now_ms=NOW + 5)
    assert reopened.writer_epoch == 1


def test_t3_workspace_id_join_field_present_and_nullable(tmp_path):
    store = _open(tmp_path, "lease.sqlite")
    fields = {f.name for f in dataclasses.fields(workspace_lease.WorkspaceLeaseRecord)}
    assert "t3_workspace_id" in fields
    assert "source_scope_digest" in fields
    lease = store.acquire_single_writer(
        repo_ref=REPO, host_ref=HOST, native_workspace_owner="owner",
        workspace_ref="ws-1", base_revision=REV, writer_ref="w",
        source_scope_digest="b" * 64, now_ms=NOW)
    assert lease.t3_workspace_id is None  # never fabricated
    tagged = store.acquire_single_writer(
        repo_ref="repo-2", host_ref=HOST, native_workspace_owner="owner",
        workspace_ref="ws-2", base_revision=REV, writer_ref="w2",
        t3_workspace_id="t3ws-77", now_ms=NOW)
    assert tagged.t3_workspace_id == "t3ws-77"
    store.close()


def test_host_cache_record_round_trip(tmp_path):
    store = _open(tmp_path, "lease.sqlite")
    key = host_cache_key(lockfiles=["uv.lock", "poetry.lock"], platform="linux", toolchain="py3.12")
    cached = store.register_host_cache(
        repo_ref=REPO, host_ref=HOST, lockfiles=["uv.lock", "poetry.lock"],
        platform="linux", toolchain="py3.12", observed_bytes=4096, now_ms=NOW)
    assert cached.cache_key == key
    assert cached.lease_kind == "host_cache"
    back = store.read(cached.lease_id)
    assert back is not None and back.cache_key == key and back.observed_bytes == 4096
    # idempotent refresh, same (repo, host), changed toolchain changes the key
    refreshed = store.register_host_cache(
        repo_ref=REPO, host_ref=HOST, lockfiles=["uv.lock", "poetry.lock"],
        platform="linux", toolchain="py3.13", observed_bytes=8192, now_ms=NOW + 1)
    assert refreshed.lease_id == cached.lease_id
    assert refreshed.cache_key != key
    assert len(store.inspect(repo_ref=REPO, host_ref=HOST, lease_kind="host_cache")) == 1
    different_host = store.register_host_cache(
        repo_ref=REPO, host_ref="host-b", lockfiles=["uv.lock"], platform="linux",
        toolchain="py3.12", now_ms=NOW)
    assert different_host.lease_id != cached.lease_id


def test_attach_factory(tmp_path):
    store = workspace_lease_attach(str(tmp_path / "attached.sqlite"))
    try:
        lease = store.acquire_single_writer(
            repo_ref=REPO, host_ref=HOST, native_workspace_owner="owner",
            workspace_ref="ws-1", base_revision=REV, writer_ref="w", now_ms=NOW)
        assert store.read(lease.lease_id).lease_status == "active"
    finally:
        store.close()
