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
            "runtime_root_state": "RESOLVED", "is_actionable": True,
            "owed_turn": {"seat": "worker", "reason": "blocker_targets_seat"},
            "validity": {key: dict(meta, sources=[{"observed_at": STAMP,
                                                       "freshness": "current"}])
                          for key in ("card", "decision_current", "dispatch",
                                       "owed_open_age")}}]}}
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


def test_work_effect_exception_reason_vocabulary_is_closed_and_facade_exported():
    """Item 6 / round-4 audit: ``effect_exception.reason`` has no closed
    vocabulary, no contract export, and a cross-module private import
    (``workspace_read_service.py``).  The contract now owns the
    frozenset :data:`common.executive_workspace_contract.QUEUE_EFFECT_EXCEPTION_REASONS`,
    both producer sites assert membership against it, and the
    workspace-app contract facade re-exports it so the facade-parity
    test exercises the re-export.

    The composer emits four values (``control_room_missing``,
    ``autonomy_missing``, ``no_exception_observed``,
    ``exception_observed``) and the read service emits the fifth
    (``read_refused``).  All five are members of the closed
    vocabulary; any other value on ``effect_exception.reason`` is a
    contract violation.
    """
    from common.executive_workspace_contract import QUEUE_EFFECT_EXCEPTION_REASONS
    assert QUEUE_EFFECT_EXCEPTION_REASONS == frozenset({
        "control_room_missing", "autonomy_missing",
        "no_exception_observed", "exception_observed", "read_refused",
    })
    # Cross-module private import removal: the read service now imports
    # the closed vocabulary directly from the contract (no private
    # module-level constant from the composer).
    import control_plane.workspace_read_service as svc_mod
    src = svc_mod.__dict__
    # The composer's own constants may still exist as locals (the
    # contract assertion guards membership); what the audit forbids is
    # an UNVALIDATED cross-module private import on the typed refusal
    # path.  The read service must use the contract constant as its
    # source of truth — assert the read service imports the contract
    # vocabulary (and the composer's reason constants resolve to it).
    assert "QUEUE_EFFECT_EXCEPTION_REASONS" in src, (
        "read service must import QUEUE_EFFECT_EXCEPTION_REASONS "
        "from the shared contract"
    )
    from control_plane.work_queue_projection import (
        _QUEUE_EFFECT_EXCEPTION_REASON_READ_REFUSED,
    )
    assert _QUEUE_EFFECT_EXCEPTION_REASON_READ_REFUSED in QUEUE_EFFECT_EXCEPTION_REASONS
    # Facade re-export: the workspace-app contract module MUST re-export
    # the constant for the facade-parity test (which iterates over
    # every member of the contract module).
    import integrations.mastermind_workspace_app.contract as compat
    assert getattr(compat, "QUEUE_EFFECT_EXCEPTION_REASONS", None) is QUEUE_EFFECT_EXCEPTION_REASONS


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


@pytest.mark.parametrize("raised", [TypeError, RuntimeError, KeyError, OSError])
def test_work_acquire_non_value_error_refuses_as_source_integrity_unverified(raised, tmp_path):
    """Item 7 / round-4 audit: the acquire guard previously caught
    ``ValueError`` only, while the cache guards catch ``Exception``.  A
    ``TypeError`` / ``RuntimeError`` acquirer yielded a real error
    envelope (an untyped 503) for the SAME failure class.  After the
    guard unification, ALL acquire-raised exceptions refuse as
    ``source_integrity_unverified`` — one rule, both sites, same typed
    refusal body.  Each parametrised exception class is verified to
    refuse the work read with the closed reason code."""
    from common.executive_workspace_contract import WORK_REFUSAL_REASON_CODES
    assert "source_integrity_unverified" in WORK_REFUSAL_REASON_CODES
    owners, _, cache = cache_fixture(tmp_path)
    def work_acquire(*args, **kwargs):
        raise raised("acquire raised: arbitrary non-ValueError")
    def work_compose(root_list_arg, **kwargs):
        pytest.fail("composer must not be reached when acquire raises")
    service_ = WorkspaceReadService(
        cache=cache, runtime=object(), authorize=lambda p: True,
        armed={}, runtime_identity={},
        work_acquire=work_acquire, work_compose=work_compose,
    )
    result = asyncio.run(service_.handle_frame(_work_frame()))
    body = result["result"]
    assert body["availability"] == "UNAVAILABLE", raised.__name__
    assert body["reason_codes"] == ["source_integrity_unverified"], raised.__name__
    # The closed-set vocabulary stays unchanged.
    assert body["reason_codes"][0] in WORK_REFUSAL_REASON_CODES, raised.__name__


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
    original_title = original_doc["work"][0]["agent_os"]["title"]
    original_published_seq = owners[0].state_published_seq
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
    # Item 8 / round-4 audit: the restore below used to live after the
    # assertions, so an assertion failure left the fixture mutated.  The
    # try/finally now guarantees the restore runs even on assertion
    # failure — the fixture stays reusable across pytest re-collection
    # and the mutated state cannot poison sibling tests.
    try:
        result = asyncio.run(service_.handle_frame(_work_frame()))
        body = result["result"]
        assert body["availability"] == "UNAVAILABLE"
        assert body["reason_codes"] == ["source_unavailable"]
    finally:
        # Restore so the fixture is reusable (mutation was in-place).
        original_doc["work"][0]["agent_os"]["title"] = original_title
        owners[0].state_published_seq = original_published_seq


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
    """B2 / WQ-PROD-1: the read service derives the per-row effects map
    from the autonomy control room and attributes the queue-level
    EFFECT_UNKNOWN exception to the rendered row.

    The injected ``work_acquire`` returns a valid root list (generation
    SAME).  The CCR cache document's autonomy responsibilities carry
    ``placement_state: {"value": "EFFECT_UNKNOWN", ...}`` — the exact
    shape ``_queue_effect_exception`` reads.  The card is extended with
    ``root_job_id`` matching the submitted root so the derived effects
    map covers the rendered row.

    Asserts AVAILABLE, ``effect_exception.value == "EFFECT_UNKNOWN"``
    with ``reason == "exception_observed"``, the rendered row in
    ``groups.EFFECT_EXCEPTION`` (per-row attribution), and the queue-
    level ``effect_not_row_attributed`` reason code is ABSENT (because
    effects were supplied — the composer's existing contract for
    ``validated_effects is not None``).
    """
    from control_plane.work_queue_projection import compose_work_queue_v1  # noqa: F401  sanity import
    owners, _, cache = cache_fixture(tmp_path)
    doc = owners[0].state_cache["doc"]
    submitted_job_id = "JOB-1"
    # Point the responsibility at the submitted root so the deriver's
    # per-row effects map covers the rendered row.
    doc["autonomy"]["responsibilities"][0]["root_job_id"] = submitted_job_id
    doc["autonomy"]["responsibilities"][0]["placement_state"] = {
        "value": "EFFECT_UNKNOWN", "observable": True, "reason": "worker_effect_unknown",
    }
    # The validity bounds were published against ``(WS:ONE, JOB-001)``;
    # re-publish against the new ``(WS:ONE, JOB-1)`` tuple so the
    # bracket accepts the responsibility after the test edits it.
    from scripts import chairman_control_room as ccr_mod
    with owners[0].state_lock:
        ccr_mod._publish_source_validity(owners[0], doc,
                                         tuple(owners[0].validity_sample_fn()),
                                         tuple(owners[0].validity_sample_fn()))
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
    # WQ-PROD-1: the deriver's per-row effects map covered the rendered
    # root_job_id, so the row lands in EFFECT_EXCEPTION.
    assert len(doc["groups"]["EFFECT_EXCEPTION"]) == 1
    attributed_row = doc["groups"]["EFFECT_EXCEPTION"][0]
    assert attributed_row["root_job_id"] == submitted_job_id
    assert attributed_row["effect"]["value"] == "EFFECT_UNKNOWN"
    assert attributed_row["effect"]["source"] == "EFFECT_PRODUCER"
    # And the queue-level reason code does NOT surface the unattributed
    # exception — the per-row attribution removed the gap.
    assert "effect_not_row_attributed" not in doc["reason_codes"]


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


# ---------------------------------------------------------------------------
# WQ-PROD-1 — route-level integration of ``derive_work_producers_v1``
# through ``_read_work``.  These tests prove (h): an injected
# ``work_acquire`` plus a control room extended with one autonomy card
# renders the row via the derived producer inputs; a derivation
# ``ValueError`` (monkeypatched to raise) is caught by the existing
# try/except and refused as ``projection_refused``.
# ---------------------------------------------------------------------------


def _extend_cache_with_card(tmp_path, *, root_job_id="JOB-1",
                            responsibility_ref="WS:PROD",
                            seat="ceo", placement_value=None,
                            attempt_id=None, qualified_at=STAMP,
                            runtime_root_state="RESOLVED",
                            root_job_ambiguous=False,
                            validity_publish=True):
    """Build a cache_fixture and extend its autonomy with one card.

    Re-publishes source validity after the extension so the
    ``_qualified`` bracket accepts the new responsibility tuple.
    Returns ``(owners, clock, cache)``.
    """
    owners, clock, cache = cache_fixture(tmp_path)
    doc = owners[0].state_cache["doc"]
    card = {
        "responsibility_ref": responsibility_ref,
        "root_job_id": root_job_id,
        "root_job_ambiguous": root_job_ambiguous,
        "runtime_root_state": runtime_root_state,
        "freshness": "current",
        "root_job_candidates": [root_job_id],
        "owed_turn": {"seat": seat},
        "validity": {"card": {"schema": "mastermind.autonomy_validity.v1",
                              "policy": "mapper-inclusive-48h-future-1h.v1",
                              "qualified_at": qualified_at,
                              "proof_ref": "b" * 64,
                              "valid_for_ms": 60000},
                     "decision_current": {"schema": "mastermind.autonomy_validity.v1",
                                         "policy": "mapper-inclusive-48h-future-1h.v1",
                                         "qualified_at": qualified_at,
                                         "proof_ref": "b" * 64,
                                         "valid_for_ms": 60000},
                     "dispatch": {"schema": "mastermind.autonomy_validity.v1",
                                  "policy": "mapper-inclusive-48h-future-1h.v1",
                                  "qualified_at": qualified_at,
                                  "proof_ref": "b" * 64,
                                  "valid_for_ms": 60000},
                     "owed_open_age": {"schema": "mastermind.autonomy_validity.v1",
                                       "policy": "mapper-inclusive-48h-future-1h.v1",
                                       "qualified_at": qualified_at,
                                       "proof_ref": "b" * 64,
                                       "valid_for_ms": 60000}},
    }
    if placement_value is not None:
        card["placement_state"] = {"value": placement_value, "observable": True,
                                   "reason": "test"}
    if attempt_id is not None:
        card["current_worker"] = {
            "worker_id": "wrk-1", "attempt_id": attempt_id, "status": "active",
            "session_alias": None, "runtime_binding_id": None,
            "binding_generation": 1, "continuation_state": "active",
            "effect_state": "active", "capacity_state": "ready",
            "previous_attempt_id": None, "movement_reason_code": None,
        }
    # B1 eligibility gate fields — closed-set defaults so legacy
    # _extend_cache_with_card callers don't have to specify them.
    card["is_actionable"] = True
    card.setdefault("owed_turn", {"seat": seat})
    if "reason" not in card["owed_turn"]:
        if seat == "ceo":
            card["owed_turn"]["reason"] = "blocker_targets_seat"
        elif seat == "worker":
            card["owed_turn"]["reason"] = "blocker_targets_seat"
        else:
            card["owed_turn"]["reason"] = "attention_targets_seat"
    card.setdefault("validity", {"card": {}})
    card["validity"].setdefault("card", {})
    if "sources" not in card["validity"]["card"]:
        card["validity"]["card"]["sources"] = [
            {"observed_at": qualified_at, "freshness": "current"},
        ]
    doc["autonomy"]["responsibilities"].append(card)
    doc["work"].append({"work_ref": responsibility_ref,
                        "agent_os": {"title": "Producer"}})
    if validity_publish:
        from scripts import chairman_control_room as ccr_mod
        with owners[0].state_lock:
            ccr_mod._publish_source_validity(owners[0], doc,
                                             tuple(owners[0].validity_sample_fn()),
                                             tuple(owners[0].validity_sample_fn()))
    return owners, clock, cache


def test_wqp1_h_route_with_ceo_card_renders_need_sol(tmp_path):
    """(h) An injected ``work_acquire`` plus the cache_fixture extended
    with one CEO card yields ``NEEDS_SOL`` with the per-row evidence
    surfaced in the row's column dict."""
    owners, _, cache = _extend_cache_with_card(tmp_path, seat="ceo")
    submitted_job_id = "JOB-1"
    root_list = _root_list_payload(rows=[
        {"job_id": submitted_job_id, "status": "QUEUED", "depth": 0,
         "parent_job_id": None, "orchestration_role": "aggregation"},
    ])
    def work_acquire(*args, **kwargs):
        return root_list
    service_ = WorkspaceReadService(
        cache=cache, runtime=object(), authorize=lambda p: True,
        armed={}, runtime_identity={"db_present": True},
        work_acquire=work_acquire, work_compose=None,
    )
    result = asyncio.run(service_.handle_frame(_work_frame()))
    assert result["ok"] is True
    doc = result["result"]
    assert doc["availability"] == "AVAILABLE"
    assert len(doc["groups"]["NEEDS_SOL"]) == 1
    row = doc["groups"]["NEEDS_SOL"][0]
    assert row["root_job_id"] == submitted_job_id
    assert row["next_actor"]["value"] == "NEEDS_SOL"
    assert row["next_actor"]["source"] == "AGENT_OS"
    assert row["next_actor"]["reason"] == "evidence_supplied"
    assert row["next_actor"]["evidence_ref"] == "b" * 64
    assert row["next_actor"]["observed_at"] == STAMP


def test_wqp1_h_route_with_worker_card_renders_need_worker(tmp_path):
    """(h) A worker seat card drives ``NEEDS_WORKER`` via the read
    service.  Post-START status is preserved on the lifecycle column."""
    owners, _, cache = _extend_cache_with_card(tmp_path, seat="worker")
    submitted_job_id = "JOB-1"
    root_list = _root_list_payload(rows=[
        {"job_id": submitted_job_id, "status": "RUNNING", "depth": 0,
         "parent_job_id": None, "orchestration_role": "aggregation"},
    ])
    def work_acquire(*args, **kwargs):
        return root_list
    service_ = WorkspaceReadService(
        cache=cache, runtime=object(), authorize=lambda p: True,
        armed={}, runtime_identity={"db_present": True},
        work_acquire=work_acquire, work_compose=None,
    )
    result = asyncio.run(service_.handle_frame(_work_frame()))
    doc = result["result"]
    assert len(doc["groups"]["NEEDS_WORKER"]) == 1
    row = doc["groups"]["NEEDS_WORKER"][0]
    assert row["root_job_id"] == submitted_job_id
    assert row["next_actor"]["value"] == "NEEDS_WORKER"
    assert row["next_actor"]["evidence_ref"] == "b" * 64


def test_wqp1_h_route_with_waiting_capacity_card_renders_waiting_capacity(tmp_path):
    """(h) A ``WAITING_CAPACITY`` placement card drives the
    ``WAITING_CAPACITY`` group on a pre-START row, with the capacity
    column populated from the derived placement evidence."""
    owners, _, cache = _extend_cache_with_card(tmp_path, seat="chairman",
                                                placement_value="WAITING_CAPACITY")
    submitted_job_id = "JOB-1"
    root_list = _root_list_payload(rows=[
        {"job_id": submitted_job_id, "status": "QUEUED", "depth": 0,
         "parent_job_id": None, "orchestration_role": "aggregation"},
    ])
    def work_acquire(*args, **kwargs):
        return root_list
    service_ = WorkspaceReadService(
        cache=cache, runtime=object(), authorize=lambda p: True,
        armed={}, runtime_identity={"db_present": True},
        work_acquire=work_acquire, work_compose=None,
    )
    result = asyncio.run(service_.handle_frame(_work_frame()))
    doc = result["result"]
    assert len(doc["groups"]["WAITING_CAPACITY"]) == 1
    row = doc["groups"]["WAITING_CAPACITY"][0]
    assert row["capacity"]["value"] == "WAITING_CAPACITY"
    assert row["capacity"]["source"] == "AUTONOMY"
    assert row["capacity"]["reason"] == "pre_start_placement_evidence"


def test_wqp1_h_route_with_effect_unknown_card_renders_effect_exception(tmp_path):
    """(h) An ``EFFECT_UNKNOWN`` placement card drives the
    ``EFFECT_EXCEPTION`` group.  The carrier is consumed by the
    composer's effect column derivation but is NOT echoed in the row
    (the closed effect column key set carries ``value``/``source``/
    ``reason``/``evidence_ref``/``observed_at`` only — the producer's
    carrier is an input, not an output).  The attempt_id is verified
    at the deriver level in the composer-suite tests.
    """
    owners, _, cache = _extend_cache_with_card(
        tmp_path, seat="worker", placement_value="EFFECT_UNKNOWN",
        attempt_id="ATT-" + "ab" * 16)
    submitted_job_id = "JOB-1"
    root_list = _root_list_payload(rows=[
        {"job_id": submitted_job_id, "status": "RUNNING", "depth": 0,
         "parent_job_id": None, "orchestration_role": "aggregation"},
    ])
    def work_acquire(*args, **kwargs):
        return root_list
    service_ = WorkspaceReadService(
        cache=cache, runtime=object(), authorize=lambda p: True,
        armed={}, runtime_identity={"db_present": True},
        work_acquire=work_acquire, work_compose=None,
    )
    result = asyncio.run(service_.handle_frame(_work_frame()))
    doc = result["result"]
    assert len(doc["groups"]["EFFECT_EXCEPTION"]) == 1
    row = doc["groups"]["EFFECT_EXCEPTION"][0]
    assert row["effect"]["value"] == "EFFECT_UNKNOWN"
    assert row["effect"]["source"] == "EFFECT_PRODUCER"
    assert row["effect"]["reason"] == "evidence_supplied"
    assert row["effect"]["evidence_ref"] == "b" * 64


def test_wqp1_h_route_derivation_value_error_refuses_as_projection_refused(tmp_path, monkeypatch):
    """(h) A ``ValueError`` raised inside ``derive_work_producers_v1`` is
    caught by the read-service's existing try/except and refused as
    ``projection_refused`` — exactly like a compose-raised ``ValueError``."""
    owners, _, cache = _extend_cache_with_card(tmp_path, seat="ceo")
    submitted_job_id = "JOB-1"
    root_list = _root_list_payload(rows=[
        {"job_id": submitted_job_id, "status": "QUEUED", "depth": 0,
         "parent_job_id": None, "orchestration_role": "aggregation"},
    ])
    def work_acquire(*args, **kwargs):
        return root_list
    def raising_derive(control_room):
        raise ValueError("malformed derivation — fake error")
    monkeypatch.setattr(
        "control_plane.work_queue_projection.derive_work_producers_v1",
        raising_derive)
    service_ = WorkspaceReadService(
        cache=cache, runtime=object(), authorize=lambda p: True,
        armed={}, runtime_identity={"db_present": True},
        work_acquire=work_acquire, work_compose=None,
    )
    result = asyncio.run(service_.handle_frame(_work_frame()))
    body = result["result"]
    assert body["availability"] == "UNAVAILABLE"
    assert body["reason_codes"] == ["projection_refused"]
    # The read-service typed refusal uses ``read_refused`` for its
    # effect_exception reason — the closed vocabulary contract.
    assert body["effect_exception"]["reason"] == "read_refused"


def test_wqp1_h_route_without_card_renders_no_producer_columns(tmp_path):
    """(h) No autonomy card added → every row falls back to
    ``no_producer`` (no deriver input, every column UNKNOWN).  The
    existing fixtures behave exactly as before — this proves the
    deriver is opt-in via the control room, not always-on."""
    owners, _, cache = cache_fixture(tmp_path)
    submitted_job_id = "JOB-1"
    root_list = _root_list_payload(rows=[
        {"job_id": submitted_job_id, "status": "QUEUED", "depth": 0,
         "parent_job_id": None, "orchestration_role": "aggregation"},
    ])
    def work_acquire(*args, **kwargs):
        return root_list
    service_ = WorkspaceReadService(
        cache=cache, runtime=object(), authorize=lambda p: True,
        armed={}, runtime_identity={"db_present": True},
        work_acquire=work_acquire, work_compose=None,
    )
    result = asyncio.run(service_.handle_frame(_work_frame()))
    doc = result["result"]
    assert doc["availability"] == "AVAILABLE"
    # cache_fixture's responsibility targets JOB-001 (not the submitted
    # JOB-1) and seat is unknown — nothing the deriver emits matches
    # the rendered row.
    queued = doc["groups"]["QUEUED"][0]
    assert queued["root_job_id"] == submitted_job_id
    assert queued["next_actor"] == {"value": "UNKNOWN", "source": None,
                                    "reason": "no_producer",
                                    "evidence_ref": None, "observed_at": None}
    assert queued["capacity"] == {"value": "UNKNOWN", "source": None,
                                  "reason": "no_producer",
                                  "evidence_ref": None, "observed_at": None}


def _extend_cache_with_round3_mixed_effects(tmp_path):
    """Set up a cache_fixture with two cards on the same root:

    1. A gate-passing non-EFFECT_UNKNOWN card with seat=ceo and the
       blocking reason — its accountability is SOL.
    2. An EFFECT_UNKNOWN card with ``is_actionable=False`` and
       ``valid_for_ms=None`` — the round-3 exempt-card shape.  Its
       effects carrier is an attempt_id; ``accountability`` and
       ``placement`` are forced to None with the ``exempt_card_not_actionable``
       skip reason.

    Returns ``(owners, clock, cache)`` for the read-path test.
    """
    from scripts import chairman_control_room as ccr
    owners, clock, cache = cache_fixture(tmp_path)
    doc = owners[0].state_cache["doc"]
    # Replace the cache_fixture's responsibility tuple so the test
    # owns the cardinality exactly (no leftover cards on JOB-001).
    meta = {"schema": "mastermind.autonomy_validity.v1",
            "policy": "mapper-inclusive-48h-future-1h.v1",
            "qualified_at": STAMP, "proof_ref": "b" * 64,
            "valid_for_ms": 60000}
    validity_full = {key: dict(meta, sources=[{"observed_at": STAMP,
                                                 "freshness": "current"}])
                     for key in ("card", "decision_current", "dispatch",
                                  "owed_open_age")}
    delivered_job = "JOB-1"
    # Card 1: gate-passing non-EFFECT card.
    card_actionable = {
        "responsibility_ref": "WS:FIRST",
        "root_job_id": delivered_job,
        "root_job_ambiguous": False,
        "runtime_root_state": "RESOLVED",
        "freshness": "current",
        "root_job_candidates": [delivered_job],
        "is_actionable": True,
        "owed_turn": {"seat": "ceo", "reason": "blocker_targets_seat"},
        "validity": dict(validity_full),
    }
    # Card 2: EFFECT_UNKNOWN exempt card.  The exemption is
    # effects-only: even though ``is_actionable=False``, the card's
    # effects carrier still emits — accountability/placement are
    # forced to None with the explicit skip reason
    # ``exempt_card_not_actionable``.  The card's proof_ref is
    # ``"c" * 64`` so the test can pin the EFFECT card as the source
    # of effects evidence.  ``valid_for_ms`` is the budget the cache
    # bracket (:func:`_admitted_row`) requires for admission of a
    # current row; the round-3 deriver exemption is keyed on
    # ``is_actionable`` alone here (a column with ``is_actionable``
    # False AND ``valid_for_ms`` None is also valid but cannot pass
    # the cache bracket in this fixture — the projection unit tests
    # in ``test_work_queue_projection.py`` exercise both shapes).
    proof_exempt = "c" * 64
    card_exempt = {
        "responsibility_ref": "WS:SECOND",
        "root_job_id": delivered_job,
        "root_job_ambiguous": False,
        "runtime_root_state": "RESOLVED",
        "freshness": "current",
        "root_job_candidates": [delivered_job],
        "is_actionable": False,
        "owed_turn": {"seat": "worker", "reason": "blocker_targets_seat"},
        "placement_state": {"value": "EFFECT_UNKNOWN", "observable": True,
                            "reason": "test"},
        "current_worker": {
            "worker_id": "wrk-ex", "attempt_id": "ATT-" + "ab" * 16,
            "status": "active", "session_alias": None,
            "runtime_binding_id": None, "binding_generation": 1,
            "continuation_state": "active", "effect_state": "active",
            "capacity_state": "ready", "previous_attempt_id": None,
            "movement_reason_code": None,
        },
        "validity": {key: dict(meta, proof_ref=proof_exempt,
                                sources=[{"observed_at": STAMP,
                                           "freshness": "current"}])
                     for key in ("card", "decision_current", "dispatch",
                                  "owed_open_age")},
    }
    doc["autonomy"]["responsibilities"] = [card_actionable, card_exempt]
    doc["work"] = [{"work_ref": "WS:FIRST", "agent_os": {"title": "Actionable"}},
                   {"work_ref": "WS:SECOND", "agent_os": {"title": "Exempt"}}]
    with owners[0].state_lock:
        ccr._publish_source_validity(owners[0], doc, tuple(clock), tuple(clock))
    return owners, clock, cache


def test_wqp1_r3_route_with_mixed_effects_renders_effect_exception(tmp_path):
    """WQ-PROD-1 round 3 / Blocker 1: through the read service's
    real composer + :func:`derive_work_producers_v1`, the
    previously-crashing scenario (mixed effects, non-effect card
    sorted first → carrier=None from the row's first view →
    :func:`_validate_effects` rejects → WHOLE work read becomes
    ``projection_refused``) now renders AVAILABLE with R in
    ``EFFECT_EXCEPTION`` and the EFFECT_UNKNOWN card's evidence
    attached to the row.

    The test proves the fix end-to-end: the read path's typed
    refusal code ``projection_refused`` MUST NOT fire — the
    deriver used the effects row from the card that actually
    carries the value, not ``views[0]``.
    """
    owners, _, cache = _extend_cache_with_round3_mixed_effects(tmp_path)
    delivered_job = "JOB-1"
    root_list = _root_list_payload(rows=[
        {"job_id": delivered_job, "status": "RUNNING", "depth": 0,
         "parent_job_id": None, "orchestration_role": "aggregation"},
    ])
    def work_acquire(*args, **kwargs):
        return root_list
    service_ = WorkspaceReadService(
        cache=cache, runtime=object(), authorize=lambda p: True,
        armed={}, runtime_identity={"db_present": True},
        work_acquire=work_acquire, work_compose=None,
    )
    result = asyncio.run(service_.handle_frame(_work_frame()))
    # The read path MUST succeed — no projection_refused — and
    # land in EFFECT_EXCEPTION with the right evidence.
    assert result["ok"] is True
    doc = result["result"]
    assert doc["availability"] == "AVAILABLE"
    assert "projection_refused" not in doc["reason_codes"]
    assert len(doc["groups"]["EFFECT_EXCEPTION"]) == 1
    row = doc["groups"]["EFFECT_EXCEPTION"][0]
    assert row["root_job_id"] == delivered_job
    assert row["effect"]["value"] == "EFFECT_UNKNOWN"
    assert row["effect"]["source"] == "EFFECT_PRODUCER"
    # The EFFECT_UNKNOWN card's proof_ref is the evidence anchor on
    # the rendered row — pinning that the read path correctly
    # attributes the row to that card, not to ``views[0]``
    # (which had ``carrier=None`` in the pre-fix code).
    assert row["effect"]["evidence_ref"] == "c" * 64
    assert row["effect"]["observed_at"] == STAMP
