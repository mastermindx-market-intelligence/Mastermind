"""Measure the fixed maximum row envelope over a real SQLite fixture.

This row-volume fixture has no installed namespace custody and makes no CURRENT
claim. The real HTTP currentness fixture is separate.
"""
import asyncio
import json

from control_plane.executive_runtime import Runtime, JobPayload
from control_plane.fabric_job_view import read_fabric_view_v2_from_runtime
from control_plane.workspace_read_service import WorkspaceReadService
from integrations.mastermind_workspace_app.contract import MAX_RESPONSE_BYTES, canonical
from tests.test_workspace_read_service import cache_fixture, frame


def test_maximum_bounded_jobs_attempts_and_ccr_response_budget(tmp_path):
    runtime = Runtime.at(tmp_path / "volume-runtime")
    root = runtime.jobs.create_job("Root " + "planned work " * 100, attempt_limit=20)
    jobs = [root] + [runtime.jobs.create_job("Child " + str(i) + " bounded work " * 100,
        parent_job_id=root.job_id, attempt_limit=20) for i in range(16)]
    runtime.workers.register_worker("volume-worker", provider="codex", account_label="fixture", worker_type="mock", capabilities=["code", "research"])
    for job in reversed(jobs):
        for index in range(20):
            assert runtime.attempts.claim_job(job.job_id) is not None
            runtime.jobs.fail_job(job.job_id, JobPayload(errors=[f"Attempt {index}: " + "bounded diagnostic " * 50]))
            if index < 19:
                runtime.jobs.requeue_job(job.job_id)
    snapshot = runtime.read_job_root_bounded(root.job_id)
    assert len(snapshot.jobs) == 17 and len(snapshot.attempts) == 340
    owners, _, cache = cache_fixture(tmp_path)
    row = owners[0].state_cache["doc"]["autonomy"]["responsibilities"][0]
    row.update(root_job_id=root.job_id, root_job_candidates=[root.job_id])
    # Re-publish using the existing source-validity owner after the selection changes.
    from scripts import chairman_control_room as ccr
    with owners[0].state_lock:
        owners[0].state_cache.pop("source_validity_bounds", None)
        sample = ccr._sample_source_clock(owners[0])
        ccr._publish_source_validity(owners[0], owners[0].state_cache["doc"], sample, sample)
    service = WorkspaceReadService(cache=cache, runtime=runtime, authorize=lambda p: True,
                                   armed={}, runtime_identity={"db_present": True})
    request = frame()
    request["selection"]["root_job_id"] = root.job_id
    response = asyncio.run(service.handle_frame(request))
    assert response["ok"] is True, response
    fabric = read_fabric_view_v2_from_runtime(runtime, root.job_id, armed={}, runtime_identity={"db_present": True})
    measured = {"jobs": 17, "attempts": 340, "fabric_bytes": len(canonical(fabric)),
                "mission_response_bytes": len(canonical(response)) + 1,
                "control_room_bytes": len(canonical(owners[0].state_cache["doc"])),
                "response_ceiling": MAX_RESPONSE_BYTES}
    measured["headroom_bytes"] = MAX_RESPONSE_BYTES - measured["mission_response_bytes"]
    assert measured["headroom_bytes"] > 0
    print("BOUNDED_VOLUME=" + json.dumps(measured, sort_keys=True))
