from __future__ import annotations

from control_plane.executive_inbox import build_inbox
from control_plane.executive_runtime import JobPayload, Runtime


_NOW = "2026-08-16T12:00:00+00:00"


def _register(runtime: Runtime, worker_id: str) -> None:
    runtime.workers.register_worker(
        worker_id,
        provider="codex",
        account_label=worker_id,
        worker_type="fixture",
        capabilities=["review"],
    )


def _complete(runtime: Runtime, job_id: str, worker_id: str, verdict: str = "") -> None:
    lease = runtime.attempts.claim_job(job_id, worker_id=worker_id)
    assert lease is not None
    runtime.jobs.complete_job(job_id, JobPayload(summary="done", verdict=verdict))


def _inbox(root) -> dict:
    return build_inbox(
        repo_root=root,
        include_boot_packet=False,
        environ={},
        now=_NOW,
    )


def test_inbox_v2_surfaces_living_child_aggregation_block_and_parent_fields(tmp_path):
    runtime = Runtime.at(tmp_path)
    _register(runtime, "worker-a")
    parent = runtime.jobs.create_job("Parent")
    runtime.jobs.create_job("Living child", parent_job_id=parent.job_id)

    inbox = _inbox(tmp_path)
    item = next(item for item in inbox["attention"] if item["job_id"] == parent.job_id)
    assert inbox["schema"] == "mastermind.executive_inbox.v2"
    assert item["kind"] == "aggregation_blocked"
    assert item["parent_job_id"] is None
    assert item["root_job_id"] == parent.job_id
    assert item["depth"] == 0
    assert item["owner_seat"] == "coo"
    assert item["business_impact"] == "routine"


def test_inbox_v2_surfaces_void_same_worker_review_and_blocks_parent(tmp_path):
    runtime = Runtime.at(tmp_path)
    _register(runtime, "worker-a")
    _register(runtime, "worker-b")
    parent = runtime.jobs.create_job("Parent")
    child = runtime.jobs.create_job(
        "Review-required child", parent_job_id=parent.job_id, review_required=True
    )
    review = runtime.jobs.create_job(
        "Review", parent_job_id=parent.job_id, reviews_job_id=child.job_id
    )
    _complete(runtime, child.job_id, "worker-a")
    _complete(runtime, review.job_id, "worker-a", verdict="approve")

    items = {
        item["job_id"]: item
        for item in _inbox(tmp_path)["attention"]
        if item["source"] == "runtime"
    }
    assert items[review.job_id]["kind"] == "review_not_independent"
    assert items[parent.job_id]["kind"] == "aggregation_blocked"
    assert items[review.job_id]["reviews_job_id"] == child.job_id


def test_inbox_v2_suppresses_parent_after_independent_approval(tmp_path):
    runtime = Runtime.at(tmp_path)
    _register(runtime, "worker-a")
    _register(runtime, "worker-b")
    parent = runtime.jobs.create_job("Parent")
    child = runtime.jobs.create_job(
        "Review-required child", parent_job_id=parent.job_id, review_required=True
    )
    review = runtime.jobs.create_job(
        "Review", parent_job_id=parent.job_id, reviews_job_id=child.job_id
    )
    _complete(runtime, child.job_id, "worker-a")
    _complete(runtime, review.job_id, "worker-b", verdict="approve")

    inbox = _inbox(tmp_path)
    assert not [item for item in inbox["attention"] if item["job_id"] in {parent.job_id, child.job_id, review.job_id}]
    assert inbox["suppressed"]["queued"] == 1
    assert inbox["suppressed"]["clean_completed"] == 2
