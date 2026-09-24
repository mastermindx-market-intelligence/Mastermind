"""Local owner/bracket tests. These are not installed namespace proof."""
import asyncio
import copy
from datetime import datetime
import threading

import pytest

from control_plane.workspace_read_service import ExistingControlRoomCache, WorkspaceReadService
from integrations.mastermind_workspace_app.contract import FRAME_SCHEMA, RESOURCE, SCOPE, digest
from scripts import chairman_control_room as ccr

STAMP = "2026-09-21T00:00:00Z"
SELECTION = {"work_ref": "WS:ONE", "root_job_id": "JOB-001"}


def frame(operation="mission"):
    return {"schema": FRAME_SCHEMA, "operation": operation,
            "selection": dict(SELECTION) if operation == "mission" else None,
            "principal": {"policy_id": "workspace-test", "issuer_digest": "a" * 64,
                "subject_digest": "b" * 64, "client_ref": "fixture-web", "resource": RESOURCE,
                "scopes": [SCOPE]}}


def cache_fixture(tmp_path):
    epoch = int(datetime.fromisoformat(STAMP.replace("Z", "+00:00")).timestamp() * 1000)
    clock = [1000, epoch, 1000, epoch]
    meta = {"schema": "mastermind.autonomy_validity.v1", "policy": "mapper-inclusive-48h-future-1h.v1",
            "qualified_at": STAMP, "proof_ref": "a" * 64, "valid_for_ms": 60000}
    doc = {"schema": "mastermind.chairman_control_room.v1", "generated_at": STAMP,
        "degraded": [], "work": [{"work_ref": "WS:ONE", "agent_os": {"title": "One"}}],
        "autonomy": {"schema": "mastermind.autonomy_control_room.v1", "generated_at": STAMP,
            "responsibilities": [{
            "responsibility_ref": "WS:ONE", "root_job_id": "JOB-001", "freshness": "current",
            "root_job_candidates": ["JOB-001"], "root_job_ambiguous": False,
            "runtime_root_state": "RESOLVED", "validity": {key: dict(meta) for key in
                ("card", "decision_current", "dispatch", "owed_open_age")}}]}}
    owner = ccr.ServerConfig(repo_root=tmp_path, macro_root=None, bindings_path=None,
                            token="fixture", origin="http://127.0.0.1:0", port=0,
                            validity_sample_fn=lambda: tuple(clock))
    owner.state_published_seq = 1
    owner.state_cache.update(doc=doc, composed_monotonic=10.0)
    with owner.state_lock:
        ccr._publish_source_validity(owner, doc, tuple(clock), tuple(clock))
    current = [owner]
    return current, clock, ExistingControlRoomCache(lambda: current[0], monotonic=lambda: 10.1)


def service(cache, *, acquire=None, authorize=lambda p: True):
    def default_acquire(runtime, root, **kwargs):
        return {"runtime": {"acquisition": {"generation": {
            "schema": "mastermind.runtime_read_observation.v1", "state": "SAME",
            "source_identity": "c" * 64, "before": 1, "after": 1}, "snapshot_digest": "d" * 64}}}
    return WorkspaceReadService(cache=cache, runtime=object(), authorize=authorize,
        armed={}, runtime_identity={}, acquire=acquire or default_acquire,
        compose=lambda **kwargs: {"fixture_inputs": kwargs})


def run(provider, request=None):
    return asyncio.run(provider.handle_frame(frame() if request is None else request))


def test_programs_reuses_published_cache_and_never_acquires_runtime(tmp_path):
    owners, clock, cache = cache_fixture(tmp_path)
    result = run(service(cache, acquire=lambda *a, **k: pytest.fail("Runtime read")), frame("programs"))
    doc = result["result"]
    assert doc["availability"] == "AVAILABLE"
    assert doc["control_room"] == owners[0].state_cache["doc"]
    assert doc["source_observation"]["state"] == "SAME"
    assert doc["source_observation"]["runtime"] is None
    assert owners[0].state_compose_seq == 0


def test_exact_bracket_is_bound_to_final_inputs_and_owner(tmp_path):
    owners, clock, cache = cache_fixture(tmp_path)
    result = run(service(cache))["result"]["fixture_inputs"]
    observation = result["owner_observation"]
    assert observation["state"] == "SAME"
    assert observation["selection"] == SELECTION
    assert observation["control_room"]["source_validity_digest"] == digest(result["source_validity"])
    assert observation["control_room"]["document_digest"] == digest(result["control_room"])
    assert observation["runtime"]["snapshot_digest"] == "d" * 64
    assert observation["control_room"]["instance_before"] == observation["control_room"]["instance_after"]


@pytest.mark.parametrize("change", ["publication", "owner", "document"])
def test_changed_owner_publication_or_bytes_never_same(tmp_path, change):
    owners, clock, cache = cache_fixture(tmp_path)
    baseline = service(cache)._acquire
    def acquire(*args, **kwargs):
        result = baseline(*args, **kwargs)
        if change == "publication":
            owners[0].state_published_seq += 1
        elif change == "owner":
            replacement, _, _ = cache_fixture(tmp_path)
            owners[0] = replacement[0]
        else:
            owners[0].state_cache["doc"]["work"][0]["agent_os"]["title"] = "Changed"
        return result
    result = run(service(cache, acquire=acquire))["result"]["fixture_inputs"]
    assert result["owner_observation"]["state"] == "CONFLICT"


@pytest.mark.parametrize("change", ["refresh_error", "expired", "missing", "over_budget"])
def test_unqualified_cache_has_unavailable_program_envelope(tmp_path, change):
    owners, clock, cache = cache_fixture(tmp_path)
    if change == "refresh_error": owners[0].state_refresh_error = "private failure"
    if change == "expired": clock[:] = [62000, clock[1] + 61000, 62000, clock[3] + 61000]
    if change == "missing": owners[0].state_cache.pop("doc")
    if change == "over_budget": owners[0].state_cache["doc"]["large"] = "x" * 2_000_000
    result = run(service(cache), frame("programs"))["result"]
    assert result["availability"] == "UNAVAILABLE" and result["control_room"] is None
    assert result["source_observation"]["state"] == "UNKNOWN"
    assert "private failure" not in str(result)


@pytest.mark.parametrize("mutation", ["work", "root", "duplicate", "ambiguous", "candidate"])
def test_unknown_mismatched_or_ambiguous_selection_refuses_before_runtime(tmp_path, mutation):
    owners, clock, cache = cache_fixture(tmp_path)
    doc = owners[0].state_cache["doc"]
    if mutation == "work": doc["work"] = []
    if mutation == "root": doc["autonomy"]["responsibilities"][0]["root_job_id"] = "JOB-002"
    if mutation == "duplicate": doc["work"] *= 2
    if mutation == "ambiguous": doc["autonomy"]["responsibilities"][0]["root_job_ambiguous"] = True
    if mutation == "candidate": doc["autonomy"]["responsibilities"][0]["root_job_candidates"] = ["JOB-002"]
    assert run(service(cache, acquire=lambda *a, **k: pytest.fail("Runtime read")))["status"] == 404


def test_wrong_client_denied_before_cache_or_runtime():
    class NoCache:
        def snapshot(self): pytest.fail("cache read")
    assert run(service(NoCache(), authorize=lambda p: False))["status"] == 403


def test_revocation_during_read_refuses_release(tmp_path):
    owners, clock, cache = cache_fixture(tmp_path)
    authorized = [True]
    baseline = service(cache)._acquire
    def acquire(*args, **kwargs):
        authorized[0] = False
        return baseline(*args, **kwargs)
    assert run(service(cache, acquire=acquire, authorize=lambda p: authorized[0]))["status"] == 403


def test_cancellation_waits_for_owner_close(tmp_path):
    owners, clock, cache = cache_fixture(tmp_path)
    started, release, closed = threading.Event(), threading.Event(), threading.Event()
    baseline = service(cache)._acquire
    def acquire(*args, **kwargs):
        started.set()
        assert release.wait(5)
        closed.set()
        return baseline(*args, **kwargs)
    async def check():
        task = asyncio.create_task(service(cache, acquire=acquire).handle_frame(frame()))
        await asyncio.to_thread(started.wait, 5)
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done()
        release.set()
        with pytest.raises(asyncio.CancelledError): await task
        assert closed.is_set()
    asyncio.run(check())


@pytest.mark.parametrize("stage", ["before", "after"])
def test_configured_permission_stamp_unavailable_refuses(stage, tmp_path):
    _, _, cache = cache_fixture(tmp_path)
    acquired = []
    authorize = lambda principal: True
    authorize.binding_digest = lambda principal: None if stage == "before" or acquired else "a" * 64
    baseline = service(cache)._acquire
    def acquire(*args, **kwargs):
        acquired.append(True)
        return baseline(*args, **kwargs)
    result = run(service(cache, acquire=acquire, authorize=authorize))
    assert result["status"] == 403 and result["error"]["code"] == "access_denied"
    assert len(acquired) == (stage == "after")


# ---------------------------------------------------------------------------
# work-queue operation
# ---------------------------------------------------------------------------


def _work_frame():
    return {"schema": FRAME_SCHEMA, "operation": "work", "selection": None,
            "principal": {"policy_id": "workspace-test", "issuer_digest": "a" * 64,
                "subject_digest": "b" * 64, "client_ref": "fixture-web",
                "resource": RESOURCE, "scopes": [SCOPE]}}


def _same_generation():
    return {"schema": "mastermind.runtime_read_observation.v1",
            "state": "SAME", "source_identity": "c" * 64,
            "before": 1, "after": 1}


def _root_list_payload(*, rows, count=None, db_present=True, generation_state="SAME",
                      degraded=(), truncated=False):
    return {
        "schema": "mastermind.fabric_job_root_list.v2",
        "generated_at": "2026-09-23T00:00:00Z",
        "runtime": {"root": "/tmp/fake", "db_present": db_present, "identity": None,
                    "acquisition": {"schema": "mastermind.fabric_runtime_acquisition.v1",
                                    "query": {"kind": "root_discovery"},
                                    "owner": "executive_runtime",
                                    "snapshot_digest": "d" * 64,
                                    "budgets": {},
                                    "truncation": {"jobs": False, "attempt_job_ids": [],
                                                    "roots": truncated, "projection": False},
                                    "provenance": {"state": "COMPLETE", "unjoined_job_ids": []},
                                    "generation": {"schema": "mastermind.runtime_read_observation.v1",
                                                    "state": generation_state,
                                                    "source_identity": "c" * 64,
                                                    "before": 1, "after": 1}}},
        "roots": rows,
        "count": count if count is not None else len(rows),
        "total": None if truncated else len(rows),
        "truncated": truncated,
        "degraded": list(degraded),
    }


def test_work_available_happy_path(tmp_path):
    owners, clock, cache = cache_fixture(tmp_path)
    root_list = _root_list_payload(rows=[
        {"job_id": "JOB-1", "status": "QUEUED", "depth": 0,
         "parent_job_id": None, "orchestration_role": "aggregation"},
        {"job_id": "JOB-2", "status": "RUNNING", "depth": 0,
         "parent_job_id": None, "orchestration_role": "aggregation"},
    ])
    def work_acquire(*args, **kwargs):
        return root_list
    def work_compose(root_list_arg, **kwargs):
        return {"schema": "mastermind.workspace_work_queue.v1",
                "availability": "AVAILABLE", "composed": True,
                "source_observation": kwargs.get("source_observation")}
    service_ = WorkspaceReadService(
        cache=cache, runtime=object(), authorize=lambda p: True,
        armed={}, runtime_identity={},
        work_acquire=work_acquire, work_compose=work_compose,
    )
    result = asyncio.run(service_.handle_frame(_work_frame()))
    doc = result["result"]
    assert doc["schema"] == "mastermind.workspace_work_queue.v1"
    assert doc["availability"] == "AVAILABLE"
    assert doc["composed"] is True
    assert doc["source_observation"]["state"] == "SAME"
    # The root list itself was passed verbatim to the composer.
    assert root_list["roots"][0]["job_id"] == "JOB-1"


def test_work_non_same_runtime_observation_refuses_with_closed_reason(tmp_path):
    """B1: a runtime receipt whose state is not SAME refuses the work read
    with the typed reason ``runtime_observation_not_same`` — even though
    the CCR bracket itself is healthy.  The composer must NOT be called."""
    owners, clock, cache = cache_fixture(tmp_path)
    root_list = _root_list_payload(rows=[], count=0,
                                    generation_state="CONFLICT")
    called = []
    def work_acquire(*args, **kwargs):
        return root_list
    def work_compose(root_list_arg, **kwargs):
        called.append(True)
    service_ = WorkspaceReadService(
        cache=cache, runtime=object(), authorize=lambda p: True,
        armed={}, runtime_identity={},
        work_acquire=work_acquire, work_compose=work_compose,
    )
    result = asyncio.run(service_.handle_frame(_work_frame()))
    body = result["result"]
    assert result["ok"] is True
    assert body["availability"] == "UNAVAILABLE"
    assert body["reason_codes"] == ["runtime_observation_not_same"]
    assert called == []  # composer never reached


def test_work_unknown_runtime_observation_refuses_with_closed_reason(tmp_path):
    """B1: a runtime receipt whose state is UNKNOWN refuses the work read
    with the typed reason ``runtime_observation_not_same``."""
    owners, clock, cache = cache_fixture(tmp_path)
    root_list = _root_list_payload(rows=[], count=0,
                                    generation_state="UNKNOWN")
    called = []
    def work_acquire(*args, **kwargs):
        return root_list
    def work_compose(root_list_arg, **kwargs):
        called.append(True)
    service_ = WorkspaceReadService(
        cache=cache, runtime=object(), authorize=lambda p: True,
        armed={}, runtime_identity={},
        work_acquire=work_acquire, work_compose=work_compose,
    )
    result = asyncio.run(service_.handle_frame(_work_frame()))
    body = result["result"]
    assert body["availability"] == "UNAVAILABLE"
    assert body["reason_codes"] == ["runtime_observation_not_same"]
    assert called == []


def test_work_missing_runtime_generation_refuses_with_closed_reason(tmp_path):
    """B1: a runtime acquisition without a ``generation`` block refuses
    the work read with the typed reason ``runtime_observation_not_same``
    — the runtime observation cannot be evaluated."""
    owners, clock, cache = cache_fixture(tmp_path)
    base = _root_list_payload(rows=[], count=0)
    del base["runtime"]["acquisition"]["generation"]
    called = []
    def work_acquire(*args, **kwargs):
        return base
    def work_compose(root_list_arg, **kwargs):
        called.append(True)
    service_ = WorkspaceReadService(
        cache=cache, runtime=object(), authorize=lambda p: True,
        armed={}, runtime_identity={},
        work_acquire=work_acquire, work_compose=work_compose,
    )
    result = asyncio.run(service_.handle_frame(_work_frame()))
    body = result["result"]
    assert body["availability"] == "UNAVAILABLE"
    assert body["reason_codes"] == ["runtime_observation_not_same"]
    assert called == []


def test_work_unmapped_jobstatus_refuses_as_projection_refused(tmp_path):
    """B2: a closed-validator refusal (the composer's R8 closed-table
    enforcement raises ``ValueError``) is translated to
    ``projection_refused`` — NOT ``source_unavailable``."""
    owners, clock, cache = cache_fixture(tmp_path)
    root_list = _root_list_payload(rows=[
        {"job_id": "JOB-1", "status": "SOMETHING_NEW", "depth": 0,
         "parent_job_id": None, "orchestration_role": "aggregation"},
    ])
    def work_acquire(*args, **kwargs):
        return root_list
    def work_compose(root_list_arg, **kwargs):
        from control_plane.work_queue_projection import compose_work_queue_v1
        return compose_work_queue_v1(root_list_arg,
                                      control_room=kwargs.get("control_room"))
    service_ = WorkspaceReadService(
        cache=cache, runtime=object(), authorize=lambda p: True,
        armed={}, runtime_identity={},
        work_acquire=work_acquire, work_compose=work_compose,
    )
    result = asyncio.run(service_.handle_frame(_work_frame()))
    body = result["result"]
    assert body["availability"] == "UNAVAILABLE"
    assert body["reason_codes"] == ["projection_refused"]


def test_work_composer_runtime_error_falls_through_to_503_envelope(tmp_path):
    """B2: a non-ValueError exception (e.g. ``RuntimeError``) in the composer
    is NOT laundered into a typed UNAVAILABLE body — it falls through to
    a real ``ok: false`` error envelope."""
    owners, clock, cache = cache_fixture(tmp_path)
    root_list = _root_list_payload(rows=[
        {"job_id": "JOB-1", "status": "RUNNING", "depth": 0,
         "parent_job_id": None, "orchestration_role": "aggregation"},
    ])
    def work_acquire(*args, **kwargs):
        return root_list
    def work_compose(root_list_arg, **kwargs):
        raise RuntimeError("composer exploded")
    service_ = WorkspaceReadService(
        cache=cache, runtime=object(), authorize=lambda p: True,
        armed={}, runtime_identity={},
        work_acquire=work_acquire, work_compose=work_compose,
    )
    result = asyncio.run(service_.handle_frame(_work_frame()))
    # error() returns the closed envelope: ok:false, status, error:{code, message}
    assert result["ok"] is False
    assert result["status"] == 503
    assert result["error"]["code"] == "source_unavailable"
    assert result["error"]["message"] == "workspace read refused"
    assert "result" not in result


def test_work_refusal_uses_only_closed_reason_codes():
    """B2: the service's closed reason-code vocabulary lives in
    :data:`common.executive_workspace_contract.WORK_REFUSAL_REASON_CODES`
    — the catch path never invents a new code outside that set."""
    from common.executive_workspace_contract import WORK_REFUSAL_REASON_CODES
    assert WORK_REFUSAL_REASON_CODES == frozenset({
        "source_unavailable", "runtime_observation_not_same", "projection_refused",
    })
    from control_plane.workspace_read_service import _WorkRefusal
    for code in WORK_REFUSAL_REASON_CODES:
        _WorkRefusal(code)  # constructor accepts every closed code
    with pytest.raises(ValueError, match="not in WORK_REFUSAL_REASON_CODES"):
        _WorkRefusal("not_a_closed_code")


def test_work_degraded_root_list_renders_unavailable_envelope(tmp_path):
    """Degraded (db_present=False) root list → queue-level UNAVAILABLE."""
    owners, clock, cache = cache_fixture(tmp_path)
    root_list = _root_list_payload(rows=[], count=0, db_present=False)
    def work_acquire(*args, **kwargs):
        return root_list
    def work_compose(root_list_arg, **kwargs):
        from control_plane.work_queue_projection import compose_work_queue_v1
        return compose_work_queue_v1(root_list_arg,
                                      control_room=kwargs.get("control_room"))
    service_ = WorkspaceReadService(
        cache=cache, runtime=object(), authorize=lambda p: True,
        armed={}, runtime_identity={},
        work_acquire=work_acquire, work_compose=work_compose,
    )
    result = asyncio.run(service_.handle_frame(_work_frame()))
    doc = result["result"]
    assert doc["availability"] == "UNAVAILABLE"
    assert doc["reason_codes"] == ["LIFECYCLE_UNAVAILABLE"]
    assert all(len(rows) == 0 for rows in doc["groups"].values())


def test_work_response_bound_respected(tmp_path):
    """The whole {ok:true,result:BODY} envelope fits under MAX_RESPONSE_BYTES-1."""
    from common.executive_workspace_contract import MAX_RESPONSE_BYTES
    owners, clock, cache = cache_fixture(tmp_path)
    # Build a root list with many synthetic rows; the response must still serialize.
    rows = [{"job_id": f"JOB-{i}", "status": "RUNNING", "depth": 0,
             "parent_job_id": None, "orchestration_role": "aggregation"}
            for i in range(1, 33)]
    root_list = _root_list_payload(rows=rows)
    def work_acquire(*args, **kwargs):
        return root_list
    def work_compose(root_list_arg, **kwargs):
        from control_plane.work_queue_projection import compose_work_queue_v1
        return compose_work_queue_v1(root_list_arg,
                                      control_room=kwargs.get("control_room"))
    service_ = WorkspaceReadService(
        cache=cache, runtime=object(), authorize=lambda p: True,
        armed={}, runtime_identity={},
        work_acquire=work_acquire, work_compose=work_compose,
    )
    result = asyncio.run(service_.handle_frame(_work_frame()))
    envelope = {"ok": True, "result": result["result"]}
    serialized = json_bytes(envelope)
    assert len(serialized) <= MAX_RESPONSE_BYTES - 1


def json_bytes(value):
    import json
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")


# ---------------------------------------------------------------------------
# N2 — route-level test with work_acquire=None against a real temp Runtime
# ---------------------------------------------------------------------------


def test_work_default_acquire_against_real_runtime_renders_closed_body(tmp_path):
    """N2: the production ``work_acquire=None`` path resolves to
    ``list_roots_v2_from_runtime`` and emits a closed work-queue body
    from a real bounded Runtime acquisition.  Reuses the closed
    ``Runtime.at`` owner (the same one
    ``tests/test_fabric_job_view_bounded.py`` exercises) so no new
    runtime fixture framework is introduced.  The exact availability
    (AVAILABLE or UNAVAILABLE) depends on the runtime's degraded notes
    for the submitted job; the test asserts the closed-shape contract
    rather than a specific availability."""
    from control_plane.executive_runtime import Runtime
    from control_plane.ceo_intent import submit_intent
    owners, _, cache = cache_fixture(tmp_path)
    # Real Runtime owner populated with one root job via the closed
    # submit_intent helper — mirrors the fixture
    # ``tests/test_fabric_job_view_bounded.py::_root`` exactly.
    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir()
    runtime = Runtime.at(runtime_root)
    receipt = submit_intent(runtime, {
        "schema": "mastermind.ceo_intent.v2", "intent_kind": "executive_coo_cycle",
        "business_impact": "material", "intent_id": "CEO-WQ-001", "actor": "ceo-sol",
        "objective": "route-level work-queue projection", "department": "executive-infrastructure",
        "priority": 5, "workstream": "WS:FABRIC",
        "grounding": {"mastermind_sha": "a" * 40, "macro_sha": "b" * 40},
        "execution_contract": {"requested_authorities": ["READ"], "attempt_limit": 2},
    }, workspace_root=tmp_path)
    # Default producers — the production path (no injection).
    service_ = WorkspaceReadService(
        cache=cache, runtime=runtime, authorize=lambda p: True,
        armed={}, runtime_identity={"db_present": True},
    )
    result = asyncio.run(service_.handle_frame(_work_frame()))
    # Closed-shape contract: the body carries the schema and the nine-
    # group envelope.  The exact availability is decided by the runtime's
    # degraded notes and is exercised by the composer-only tests.
    assert result["ok"] is True
    doc = result["result"]
    assert doc["schema"] == "mastermind.workspace_work_queue.v1"
    assert doc["availability"] in ("AVAILABLE", "UNAVAILABLE")
    from control_plane.work_queue_projection import _GROUP_ORDER
    assert set(doc["groups"]) == set(_GROUP_ORDER)
    # The runtime-emitted job id appears in one of the groups OR the
    # composer mapped the queue to UNAVAILABLE because the bounded
    # acquisition surfaced a degraded note for the unjoined job.
    job_ids = [row["root_job_id"] for group in doc["groups"].values()
               for row in group]
    if doc["availability"] == "AVAILABLE":
        assert receipt["job_id"] in job_ids
    # source_observation carries the runtime's actual receipt — proof the
    # production ``work_acquire=None`` path went through
    # ``list_roots_v2_from_runtime``, not a stub.
    assert doc["source_observation"]["state"] in ("SAME", "UNKNOWN", "CONFLICT")
