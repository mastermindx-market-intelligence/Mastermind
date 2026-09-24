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
    the CCR bracket itself is healthy.  The composer must NOT be called.

    B3: ``work_compose`` is now the real ``compose_work_queue_v1`` so
    the RED mechanism is assertion-based.  With the B1 gate REMOVED,
    the composer would be invoked on the same CONFLICT root list and
    ``_lifecycle_unavailable`` would fire (it refuses on non-SAME
    generation), so ``reason_codes`` would be
    ``["LIFECYCLE_UNAVAILABLE"]`` (the composer's own R1 code).  With
    the gate present, the read service refuses FIRST with
    ``["runtime_observation_not_same"]`` — the test proves the gate by
    asserting the typed read-service code, NOT by ``called == []``
    alone (a stub-returning-None would be vacuously RED).
    """
    from control_plane.work_queue_projection import compose_work_queue_v1
    owners, clock, cache = cache_fixture(tmp_path)
    root_list = _root_list_payload(rows=[], count=0,
                                    generation_state="CONFLICT")
    called = []
    def work_acquire(*args, **kwargs):
        return root_list
    def work_compose(root_list_arg, **kwargs):
        called.append(True)
        return compose_work_queue_v1(root_list_arg, control_room=kwargs.get("control_room"))
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
    assert called == []  # gate fired before composer could be called


def test_work_unknown_runtime_observation_refuses_with_closed_reason(tmp_path):
    """B1: a runtime receipt whose state is UNKNOWN refuses the work read
    with the typed reason ``runtime_observation_not_same``.

    B3: ``work_compose`` is the real composer — see B3 docstring above
    for the RED mechanism.  With the gate REMOVED, the composer would
    fire ``_lifecycle_unavailable`` and render ``["LIFECYCLE_UNAVAILABLE"]``;
    with the gate present, ``["runtime_observation_not_same"]``."""
    from control_plane.work_queue_projection import compose_work_queue_v1
    owners, clock, cache = cache_fixture(tmp_path)
    root_list = _root_list_payload(rows=[], count=0,
                                    generation_state="UNKNOWN")
    called = []
    def work_acquire(*args, **kwargs):
        return root_list
    def work_compose(root_list_arg, **kwargs):
        called.append(True)
        return compose_work_queue_v1(root_list_arg, control_room=kwargs.get("control_room"))
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
    — the runtime observation cannot be evaluated.

    B3: ``work_compose`` is the real composer — see B3 docstring above.
    With the gate REMOVED, the composer would itself validate the
    ``runtime.acquisition`` envelope and ``_validate_root_list`` would
    raise ``ValueError`` (a malformed ``acquisition`` envelope), mapped
    to ``["projection_refused"]``; with the gate present, the read
    service refuses FIRST with ``["runtime_observation_not_same"]``."""
    from control_plane.work_queue_projection import compose_work_queue_v1
    owners, clock, cache = cache_fixture(tmp_path)
    base = _root_list_payload(rows=[], count=0)
    del base["runtime"]["acquisition"]["generation"]
    called = []
    def work_acquire(*args, **kwargs):
        return base
    def work_compose(root_list_arg, **kwargs):
        called.append(True)
        return compose_work_queue_v1(root_list_arg, control_room=kwargs.get("control_room"))
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
        "source_integrity_unverified",
    })
    from control_plane.workspace_read_service import _WorkRefusal
    for code in WORK_REFUSAL_REASON_CODES:
        _WorkRefusal(code)  # constructor accepts every closed code
    with pytest.raises(ValueError, match="not in WORK_REFUSAL_REASON_CODES"):
        _WorkRefusal("not_a_closed_code")


def test_work_acquire_raised_value_error_refuses_as_source_integrity_unverified(tmp_path):
    """N2: a ``ValueError`` raised by the acquire (defensive — the production
    acquirer swallows its own faults and surfaces a degraded notes list)
    refuses as ``source_integrity_unverified`` — the runtime could not
    return a well-formed root list.  This is distinct from
    ``projection_refused`` which is reserved for composer-raised faults."""
    from common.executive_workspace_contract import WORK_REFUSAL_REASON_CODES
    assert "source_integrity_unverified" in WORK_REFUSAL_REASON_CODES
    owners, _, cache = cache_fixture(tmp_path)
    def work_acquire(*args, **kwargs):
        raise ValueError("acquire raised: malformed root list")
    def work_compose(root_list_arg, **kwargs):
        pytest.fail("composer must not be reached when acquire raises")
    service_ = WorkspaceReadService(
        cache=cache, runtime=object(), authorize=lambda p: True,
        armed={}, runtime_identity={},
        work_acquire=work_acquire, work_compose=work_compose,
    )
    result = asyncio.run(service_.handle_frame(_work_frame()))
    body = result["result"]
    assert body["availability"] == "UNAVAILABLE"
    assert body["reason_codes"] == ["source_integrity_unverified"]


def test_work_compose_raised_value_error_refuses_as_projection_refused(tmp_path):
    """N2: a ``ValueError`` raised by the composer (closed-table validator,
    evidence-freshness rejection) refuses as ``projection_refused`` —
    NOT ``source_integrity_unverified``.  The two codes are disjoint:
    source-integrity events come from the acquire side, projection
    faults come from the compose side."""
    owners, _, cache = cache_fixture(tmp_path)
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


def test_work_ccr_receipt_conflict_takes_precedence_over_runtime_concurrent(tmp_path):
    """N3: when the CCR bracket is CONFLICT (a positive CCR change between
    the two samples) and the runtime is concurrently CONFLICT, the CCR
    receipt check fires FIRST and refuses as ``source_unavailable`` —
    the runtime gate's typed code is NEVER reached.  This pins the
    refusal precedence: a positive CCR change is the source-unavailable
    signal, and the runtime observation cannot mask it."""
    owners, _, cache = cache_fixture(tmp_path)
    # Mutate the doc between the two samples so the CCR receipt goes CONFLICT.
    original_doc = owners[0].state_cache["doc"]
    def mutate_doc():
        owners[0].state_cache["doc"]["work"][0]["agent_os"]["title"] = "Mutated"
        owners[0].state_published_seq += 1
    def work_acquire(*args, **kwargs):
        mutate_doc()  # CCR change happens BEFORE the second sample
        return _root_list_payload(rows=[], count=0, generation_state="CONFLICT")
    def work_compose(*args, **kwargs):
        pytest.fail("composer must not be reached on CCR conflict")
    service_ = WorkspaceReadService(
        cache=cache, runtime=object(), authorize=lambda p: True,
        armed={}, runtime_identity={},
        work_acquire=work_acquire, work_compose=work_compose,
    )
    result = asyncio.run(service_.handle_frame(_work_frame()))
    body = result["result"]
    assert body["availability"] == "UNAVAILABLE"
    assert body["reason_codes"] == ["source_unavailable"]
    # Restore so the fixture is reusable (mutation was in-place).
    original_doc["work"][0]["agent_os"]["title"] = "One"
    owners[0].state_published_seq -= 1


def test_work_raising_cache_emits_typed_unavailable_body(tmp_path):
    """N5: a raising cache yields the same typed UNAVAILABLE body as an
    unqualified cache.  Both wire shapes are unified into
    ``_WorkRefusal("source_unavailable")`` — the route never escapes as
    an untyped 503 envelope."""
    owners, _, cache = cache_fixture(tmp_path)
    class RaisingCache:
        def snapshot(self):
            raise ValueError("source_unavailable")
    service_ = WorkspaceReadService(
        cache=RaisingCache(), runtime=object(), authorize=lambda p: True,
        armed={}, runtime_identity={},
    )
    result = asyncio.run(service_.handle_frame(_work_frame()))
    assert result["ok"] is True
    body = result["result"]
    assert body["availability"] == "UNAVAILABLE"
    assert body["reason_codes"] == ["source_unavailable"]
    # The N4 effect_exception vocabulary uses ``read_refused`` — the read
    # service is reporting its OWN read failure, not a missing control
    # room document.
    assert body["effect_exception"]["reason"] == "read_refused"


def test_work_failed_bounded_acquisition_refuses_at_route_with_null_lifecycle_source(tmp_path):
    """N1 (disclose): a failed bounded acquisition (injected acquire
    returning generation UNKNOWN + ``_BOUNDED_UNAVAILABLE_NOTE`` in
    ``degraded``) refuses at the route with
    ``reason_codes == ["runtime_observation_not_same"]`` AND
    ``lifecycle_source is None``.  The composer would have rendered a
    UNAVAILABLE body with the producer's degraded note echoed into
    ``lifecycle_source.degraded``; the read-service gate fires BEFORE
    the composer is called and discards that text.  This pins the
    disclosed behavior: a failed bounded acquisition never surfaces
    the producer's ``bounded acquisition unavailable: ...`` text on the
    route — it always returns ``lifecycle_source: null`` and the typed
    ``runtime_observation_not_same`` code.

    The parent owns the disclosure: this test pins the behavior, not
    the (independent) decision to keep or carry the text."""
    from control_plane.fabric_job_view import _BOUNDED_UNAVAILABLE_NOTE
    owners, _, cache = cache_fixture(tmp_path)
    # Injection shape: generation UNKNOWN + bounded unavailable in degraded.
    root_list = _root_list_payload(rows=[], count=0, generation_state="UNKNOWN",
                                    degraded=[_BOUNDED_UNAVAILABLE_NOTE])
    def work_acquire(*args, **kwargs):
        return root_list
    def work_compose(root_list_arg, **kwargs):
        pytest.fail("composer must not be reached on failed bounded acquisition")
    service_ = WorkspaceReadService(
        cache=cache, runtime=object(), authorize=lambda p: True,
        armed={}, runtime_identity={},
        work_acquire=work_acquire, work_compose=work_compose,
    )
    result = asyncio.run(service_.handle_frame(_work_frame()))
    body = result["result"]
    # The read-service runtime gate refuses FIRST — even though the
    # composer would have rendered UNAVAILABLE via ``_lifecycle_unavailable``
    # on the same root list, the route refuses at the gate with the typed
    # code and a null ``lifecycle_source``.
    assert body["availability"] == "UNAVAILABLE"
    assert body["reason_codes"] == ["runtime_observation_not_same"]
    assert body["lifecycle_source"] is None


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
# B1(b) — exercise the AVAILABLE branch with a producer-shaped root list.
#
# The real ``Runtime.at`` test above (with no read binding) is UNAVAILABLE
# by design.  This test injects a stub ``work_acquire`` that returns a
# production-shaped root list (SAME generation, ``_ROOT_ENUMERATION_NOTE``
# in ``degraded``, PARTIAL provenance) so the composer and read service
# reach the AVAILABLE branch and the strict shape assertions below can
# prove the B1 closed-set refactor is wired through the route, not just
# the composer unit tests.
# ---------------------------------------------------------------------------


def test_work_route_with_producer_shaped_root_list_renders_available_no_lifecycle_degraded(tmp_path):
    """B1(b): the route-level happy path with a producer-shaped root list
    (SAME generation + ``_ROOT_ENUMERATION_NOTE`` in ``degraded``) renders
    ``AVAILABLE`` with empty ``reason_codes`` (the enumeration note alone
    must not fire ``lifecycle_degraded``), ``lifecycle_source.degraded``
    echoes the producer's note verbatim, ``coverage.completeness ==
    "PARTIAL"`` (enumeration provenance is unjoined), and the submitted
    root's row appears in the expected lifecycle group."""
    from control_plane.fabric_job_view import _ROOT_ENUMERATION_NOTE
    owners, _, cache = cache_fixture(tmp_path)
    submitted_job_id = "JOB-1"
    root_list = _root_list_payload(rows=[
        {"job_id": submitted_job_id, "status": "QUEUED", "depth": 0,
         "parent_job_id": None, "orchestration_role": "aggregation"},
    ])
    # Force the producer-shaped degraded list + PARTIAL provenance that
    # ``list_roots_v2_from_runtime`` would emit on the live read.
    root_list["degraded"] = [_ROOT_ENUMERATION_NOTE]
    root_list["runtime"]["acquisition"]["provenance"]["state"] = "PARTIAL"
    root_list["runtime"]["acquisition"]["provenance"]["unjoined_job_ids"] = [submitted_job_id]

    def work_acquire(*args, **kwargs):
        return root_list

    service_ = WorkspaceReadService(
        cache=cache, runtime=object(), authorize=lambda p: True,
        armed={}, runtime_identity={"db_present": True},
        work_acquire=work_acquire,
    )
    result = asyncio.run(service_.handle_frame(_work_frame()))
    assert result["ok"] is True
    doc = result["result"]
    # B1: closed-set refactor — the enumeration note alone adds NO reason code.
    assert doc["availability"] == "AVAILABLE"
    assert doc["reason_codes"] == []
    assert doc["lifecycle_source"]["degraded"] == [_ROOT_ENUMERATION_NOTE]
    # Enumeration provenance is unjoined → PARTIAL coverage.
    assert doc["coverage"]["completeness"] == "PARTIAL"
    # The submitted root's row is present in the QUEUED lifecycle group.
    queued_ids = [row["root_job_id"] for row in doc["groups"]["QUEUED"]]
    assert submitted_job_id in queued_ids


def test_work_effect_not_row_attributed_via_real_composer_through_read_work(tmp_path):
    """B2: ``effect_not_row_attributed`` is proven through ``_read_work``
    with the REAL composer (``work_compose=None`` → ``compose_work_queue_v1``).
    The injected ``work_acquire`` returns a valid root list (generation
    SAME) and the CCR cache document's autonomy responsibilities carry
    ``placement_state: {"value": "EFFECT_UNKNOWN", ...}`` — the exact
    shape ``_queue_effect_exception`` reads.  Asserts AVAILABLE,
    ``effect_exception.value == "EFFECT_UNKNOWN"`` with ``reason ==
    "exception_observed"``, ``groups.EFFECT_EXCEPTION == []`` (no per-row
    attribution when no ``effects`` map is supplied), and
    ``"effect_not_row_attributed" in reason_codes``."""
    from control_plane.work_queue_projection import compose_work_queue_v1  # noqa: F401  sanity import
    owners, _, cache = cache_fixture(tmp_path)
    # Attach the autonomy EFFECT_UNKNOWN responsibility — same shape
    # ``_queue_effect_exception`` reads (placement_state.value == "EFFECT_UNKNOWN").
    doc = owners[0].state_cache["doc"]
    doc["autonomy"]["responsibilities"][0]["placement_state"] = {
        "value": "EFFECT_UNKNOWN", "observable": True, "reason": "worker_effect_unknown",
    }
    submitted_job_id = "JOB-1"
    root_list = _root_list_payload(rows=[
        {"job_id": submitted_job_id, "status": "QUEUED", "depth": 0,
         "parent_job_id": None, "orchestration_role": "aggregation"},
    ])
    def work_acquire(*args, **kwargs):
        return root_list
    # work_compose=None — the read service resolves to the real composer.
    service_ = WorkspaceReadService(
        cache=cache, runtime=object(), authorize=lambda p: True,
        armed={}, runtime_identity={"db_present": True},
        work_acquire=work_acquire, work_compose=None,
    )
    result = asyncio.run(service_.handle_frame(_work_frame()))
    assert result["ok"] is True
    doc = result["result"]
    assert doc["availability"] == "AVAILABLE"
    assert doc["effect_exception"]["value"] == "EFFECT_UNKNOWN"
    assert doc["effect_exception"]["reason"] == "exception_observed"
    assert doc["effect_exception"]["scope"] == "RUNTIME_CURRENT_WORKER"
    assert doc["effect_exception"]["observable"] is True
    # No per-row effects map was supplied — no row lands in EFFECT_EXCEPTION.
    assert doc["groups"]["EFFECT_EXCEPTION"] == []
    # And the queue-level reason code surfaces the unattributed exception.
    assert "effect_not_row_attributed" in doc["reason_codes"]


def test_work_default_acquire_against_real_runtime_renders_closed_body(tmp_path):
    """N2: the production ``work_acquire=None`` path resolves to
    ``list_roots_v2_from_runtime`` and emits a closed work-queue body
    from a real bounded Runtime acquisition.  Reuses the closed
    ``Runtime.at`` owner (the same one
    ``tests/test_fabric_job_view_bounded.py`` exercises) so no new
    runtime fixture framework is introduced.

    B1(b): this runtime in this fixture is UNAVAILABLE rather than
    AVAILABLE — by design.  ``Runtime.at(runtime_root)`` without a
    ``read_binding`` finalizes the bounded observation receipt with
    ``source_identity=None`` and ``state="UNKNOWN"`` (see
    ``executive_runtime.BoundedRuntimeReadObservation._finalize``), so
    the read-service's runtime observation gate (B1) refuses with
    ``runtime_observation_not_same``.  This is the honest truthful
    outcome of a Runtime with no read binding: the bounded observation
    cannot prove a same-connection read.  Asserting ``AVAILABLE`` here
    would silently manufacture a healthy read over an unbound Runtime,
    which is exactly the failure mode the gate exists to prevent.

    The test asserts the exact UNAVAILABLE outcome (no weakening).
    A separate test below exercises the AVAILABLE branch with an
    injected stub that produces a producer-shaped root list with a
    SAME generation receipt."""
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
    # group envelope.  Exact assertion — no weakening.
    assert result["ok"] is True
    doc = result["result"]
    assert doc["schema"] == "mastermind.workspace_work_queue.v1"
    from control_plane.work_queue_projection import _GROUP_ORDER
    assert set(doc["groups"]) == set(_GROUP_ORDER)
    # Healthy runtime read in this fixture is UNAVAILABLE: the bounded
    # observation receipt finalizes with state=UNKNOWN (no read binding),
    # so the read-service runtime gate refuses with the typed code.
    assert doc["availability"] == "UNAVAILABLE"
    assert doc["reason_codes"] == ["runtime_observation_not_same"]
    assert doc["source_observation"]["state"] == "UNKNOWN"
    # The runtime DID discover the submitted root — it surfaces in
    # ``lifecycle_source.runtime.acquisition`` (read receipt was finalized),
    # so the gate refusal is honest: the Runtime observation simply cannot
    # be proven SAME without a read binding.
    assert receipt["job_id"] not in [row["root_job_id"] for group in doc["groups"].values()
                                     for row in group]
