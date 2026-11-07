"""Bounded retained-root membership selection over the real existing owners.

S5 backend: the programs document legitimately carries responsibility rows
with more than one actual Runtime root (including terminal roots) — the
compositor's Blocker 1 shape, where ``root_job_id`` stays ``None``, the
candidates are the sorted distinct actual roots, ``root_job_ambiguous`` is
``True`` and ``runtime_root_state`` is ``CONFLICT``.  The two retained read
routes — ``result_references`` and the bounded role-result read — must admit
a selection that is an actual member of the paired publication's own bounded
candidate vector, while every other route keeps the sole-root ``_join``.

Real owners used unchanged throughout: the ``ServerConfig`` cache fixture and
its real paired validity publication, ``ExistingControlRoomCache``, the
whole-document ``_qualified`` gate, the Fabric v3 companion validators and
index composer, ``project_fabric_role_result`` and the OHF Runtime chain
builders.  Seams are labelled where a transport callable is injected: the
Fabric v3 companion acquire, the result route's ``result_acquire``/
``result_project`` pair, and the second-root cycle driver (the existing
all-severity builder is single-use on one store, so its own builders are
re-driven with fresh intent and OHF identity seeds).  No Job, Attempt or
Event is dispatched anywhere in this module, and no provider, host,
credential or live database outside ``tmp_path`` is touched.
"""
import asyncio
import copy
from types import SimpleNamespace

import pytest

from common.executive_workspace_contract import (
    FRAME_SCHEMA_V2, canonical, digest, error,
)
from control_plane import executive_runtime as er
from control_plane import fabric_result_projection as frp
from control_plane.ceo_intent import submit_intent
from control_plane.executive_coo_cycle import CooCycle
from control_plane.executive_orchestration_result import (
    canonical_digest as result_digest,
)
from control_plane.fabric_job_view import (
    ORCHESTRATION_TERMINAL_RECEIPT_SCHEMA, SCHEMA_V3, _TERMINAL_RECEIPT_KEYS,
    compose_fabric_result_reference_index,
)
from control_plane.workspace_read_service import (
    WorkspaceReadService,
    _join,
    _qualified,
    _qualified_retained_root,
    _retained_root_join,
    _valid_retained_root_id,
)
from control_plane.workspace_result_references import read_result_references
from integrations.mastermind_workspace_app.contract import (
    FRAME_SCHEMA, RESOURCE, SCOPE,
)
from scripts import chairman_control_room as ccr
from tests import test_executive_os_phase1fc as fc
from tests.test_executive_os_phase1fc import _complete_ohf_role, _v2_intent
from tests.test_fabric_result_projection import (
    _bound_reader, _release, _select_bound, complete_all_severity_chain,
)
from tests.test_mission_workspace import _inputs_v2
from tests.test_workspace_read_service import STAMP, cache_fixture

WORK_REF = "WS:ONE"
OTHER_REF = "WS:TWO"
ROOT_A = "JOB-001"
ROOT_B = "JOB-002"
ROOT_C = "JOB-003"
ROOTS = (ROOT_A, ROOT_B)
ATTEMPT = "ATT-" + "a" * 32
DIGEST = "d" * 64
ENVELOPE = "e" * 64
IDENTITY = "c" * 64


def _principal():
    return {"policy_id": "workspace-test", "issuer_digest": "a" * 64,
            "subject_digest": "b" * 64, "client_ref": "fixture-web",
            "resource": RESOURCE, "scopes": [SCOPE]}


def references_frame(selection):
    return {"schema": FRAME_SCHEMA_V2, "operation": "result_references",
            "selection": dict(selection), "principal": _principal()}


def v2_frame(operation, selection):
    return {"schema": FRAME_SCHEMA_V2, "operation": operation,
            "selection": dict(selection), "principal": _principal()}


def programs_frame():
    return {"schema": FRAME_SCHEMA, "operation": "programs",
            "selection": None, "principal": _principal()}


def cache_result_selection(root, job=None):
    return {"work_ref": WORK_REF, "root_job_id": root, "job_id": job or root,
            "attempt_id": ATTEMPT, "result_envelope_digest": ENVELOPE}


# ---------------------------------------------------------------------------
# Real cache fixture republished as one genuine multi-root CONFLICT row.
# ---------------------------------------------------------------------------


def multi_root_cache(tmp_path, roots=ROOTS, work_ref=WORK_REF):
    """The real cache fixture, republished as the compositor's multi-root row.

    The row shape is the actual Blocker 1 output (``root_job_id`` stays
    ``None``, candidates the sorted distinct roots, ambiguous ``True``,
    state ``CONFLICT``); the paired source-validity publication is the real
    ``ServerConfig`` owner's, keyed at ``(ref, None)`` exactly as the mapper
    publishes an ambiguous row.
    """
    owners, clock, cache = cache_fixture(tmp_path)
    doc = owners[0].state_cache["doc"]
    row = doc["autonomy"]["responsibilities"][0]
    row.update(disagreements=[])
    assert row["responsibility_ref"] == work_ref
    doc["sources"] = {"agent_os_state_generated_at": STAMP}
    publish_root_state(owners, clock, doc, row, roots)
    return owners, clock, cache, doc, row


def publish_root_state(owners, clock, doc, row, roots):
    row.update(root_job_id=None,
               root_job_candidates=(sorted(roots) if all(
                   type(candidate) is str for candidate in roots) else list(roots)),
               root_job_ambiguous=True, runtime_root_state="CONFLICT")
    with owners[0].state_lock:
        owners[0].state_cache["doc"] = doc
        ccr._publish_source_validity(owners[0], doc, tuple(clock), tuple(clock))


# ---------------------------------------------------------------------------
# Labelled transport seam: real Fabric v2 fixture + actual v3 index composer.
# ---------------------------------------------------------------------------


def _terminal_receipt(job_id=ROOT_A, attempt_id=ATTEMPT):
    receipt = {
        "schema_version": ORCHESTRATION_TERMINAL_RECEIPT_SCHEMA,
        "status": "COMPLETED", "job_id": job_id, "attempt_id": attempt_id,
        "orchestration_role": "work", "execution_mode": "SEALED_WORKER",
        "result_seal_command_id": "seal-" + job_id,
        "result_evidence": {"note": "fixture"},
        "result_envelope": {"summary": "fixture"},
        "result_envelope_digest": ENVELOPE,
        "artifact_receipt_digest": "f" * 64,
        "validation_receipt_digest": "0" * 64,
        "effective_grant_digest": "1" * 64,
        "terminal_evidence_digest": "2" * 64,
    }
    assert set(receipt) == _TERMINAL_RECEIPT_KEYS
    return receipt


def _generation(state="SAME", before=1, after=1):
    return {"schema": "mastermind.runtime_read_observation.v1", "state": state,
            "source_identity": IDENTITY, "before": before, "after": after}


def _retained_snapshot(root):
    receipt = _terminal_receipt(job_id=root)
    job = SimpleNamespace(job_id=root, root_job_id=root, status="COMPLETED",
                          result=receipt, current_attempt_id=ATTEMPT,
                          orchestration_role="work")
    attempt = SimpleNamespace(job_id=root, attempt_id=ATTEMPT,
                              status="COMPLETED", result=receipt,
                              execution_mode="SEALED_WORKER")
    return SimpleNamespace(root_job_id=root, jobs=[job], attempts=[attempt],
                           jobs_truncated=False, attempts_truncated_job_ids=(),
                           snapshot_digest=DIGEST)


def _reference_acquire(roots=ROOTS):
    """Labelled transport seam, one companion per requested root."""
    def acquire(runtime, observed_root, **kwargs):
        expected = {"armed": {}, "runtime_identity": {}}
        if len(roots) > 1:
            expected["expected_work_ref"] = WORK_REF
        assert kwargs == expected
        assert observed_root in roots
        snapshot = _retained_snapshot(observed_root)
        fabric = _inputs_v2()["fabric_view"]
        fabric["generated_at"] = STAMP
        fabric["root"].update(job_id=observed_root, root_job_id=observed_root)
        fabric["runtime"]["acquisition"] = {
            "schema": "mastermind.fabric_runtime_acquisition.v1",
            "query": {"kind": "root_discovery", "root_job_id": observed_root},
            "owner": "executive_runtime", "snapshot_digest": snapshot.snapshot_digest,
            "budgets": {"roots": 64, "jobs": 17, "attempts_per_job": 20,
                        "attempts_total": 340, "creation_events_per_job": 1},
            "truncation": {"jobs": False, "attempt_job_ids": [], "roots": False,
                           "projection": False},
            "provenance": {"state": "COMPLETE", "unjoined_job_ids": []},
            "generation": _generation(),
        }
        return {"schema": SCHEMA_V3, "fabric_view": fabric,
                "result_refs": compose_fabric_result_reference_index(
                    snapshot, _generation())}

    return acquire


def references_owner(cache, acquire):
    return WorkspaceReadService(cache=cache, runtime=object(),
                                authorize=lambda principal: True, armed={},
                                runtime_identity={}, mission_v3_acquire=acquire)


def read_references(tmp_path, selection, *, roots=ROOTS, mutate=None,
                    acquire=None):
    owners, clock, cache, doc, row = multi_root_cache(tmp_path, roots)
    if mutate is not None:
        mutate(owners, clock)
    return read_result_references(
        references_owner(cache, acquire if acquire is not None
                         else _reference_acquire(roots)),
        references_frame(selection))


# ---------------------------------------------------------------------------
# Labelled transport seam pair for the cached bounded role-result route.
# ---------------------------------------------------------------------------


def _result_acquire_seam(roots=ROOTS):
    """Labelled transport seam: one bounded acquisition per requested root.

    The returned snapshot binds the requested selection tuple exactly, so the
    unchanged pre-projection binding law admits it; the real Runtime seam is
    exercised separately below over the actual OHF store.
    """
    def acquire(runtime, selected, **kwargs):
        assert kwargs == {"armed": {}, "runtime_identity": {}}
        assert selected["root_job_id"] in roots
        snapshot = SimpleNamespace(
            root_job_id=selected["root_job_id"], job_id=selected["job_id"],
            attempt_id=selected["attempt_id"],
            result_envelope_digest=selected["result_envelope_digest"],
            observation_source_identity=IDENTITY,
            root_metadata=SimpleNamespace(work_ref=WORK_REF))
        receipt = SimpleNamespace(
            state="SAME", source_identity=IDENTITY,
            to_dict=lambda: dict(_generation(), source_identity=IDENTITY))
        return snapshot, receipt

    return acquire


def _result_project(snapshot, receipt):
    """Labelled transport seam DTO: the shared complete/over-budget pair."""
    shared = {key: getattr(snapshot, key)
              for key in ("attempt_id", "job_id", "result_envelope_digest",
                          "root_job_id")}
    complete = {"selection": shared, "generation": receipt.to_dict(),
                "availability": "AVAILABLE"}
    return SimpleNamespace(complete=complete,
                           content_over_budget=dict(complete,
                                                    availability="CONTENT_OVER_BUDGET"))


def result_service(cache, *, authorize=lambda principal: True,
                   acquire=None, project=None, **kwargs):
    return WorkspaceReadService(
        cache=cache, runtime=object(), authorize=authorize, armed={},
        runtime_identity={},
        result_acquire=acquire if acquire is not None else _result_acquire_seam(),
        result_project=project if project is not None else _result_project,
        **kwargs)


# ---------------------------------------------------------------------------
# Membership law: the join, the old join, and the whole-document gate.
# ---------------------------------------------------------------------------


def test_retained_join_admits_each_published_root_and_old_join_refuses(tmp_path):
    owners, clock, cache, doc, row = multi_root_cache(tmp_path)
    snapshot = cache.snapshot()
    for root in ROOTS:
        selected = {"work_ref": WORK_REF, "root_job_id": root}
        assert _retained_root_join(doc, selected) is row
        assert _qualified_retained_root(snapshot, selected) is True
        # The existing sole-root join keeps refusing the multi-root row for
        # every route that did not opt into retained membership.
        with pytest.raises(LookupError):
            _join(doc, selected)


def test_full_publication_gate_admits_multi_row_old_selected_path_refuses(tmp_path):
    owners, clock, cache, doc, row = multi_root_cache(tmp_path)
    snapshot = cache.snapshot()
    selected = {"work_ref": WORK_REF, "root_job_id": ROOT_B}
    # The helper's gate is the unchanged whole-document qualification: the
    # multi-root publication is a healthy Programmes publication, while the
    # old selected path (whose internal join is the sole-root law) refuses.
    assert _qualified(snapshot, None) is True
    with pytest.raises(LookupError):
        _qualified(snapshot, selected)


def test_candidate_id_shape_matches_the_result_reader_law():
    from common.executive_workspace_contract import _check_job_id
    for value in ("JOB-001", "JOB- 9", "", "ROOT-1", "job-1", "JOB-alpha",
                  "JOB-" + "1" * 20, "JOB-1\n", "JOB-1\t", 7, None, True):
        assert _valid_retained_root_id(value) == _check_job_id(value)


def test_candidate_vector_boundary_is_bounded_admission(tmp_path):
    owners, clock, cache, doc, row = multi_root_cache(tmp_path)
    vector = [f"JOB-{n:04d}" for n in range(48)] + [ROOT_A, ROOT_B]
    assert len(vector) == 50
    publish_root_state(owners, clock, doc, row, vector)
    assert _retained_root_join(doc, {"work_ref": WORK_REF,
                                     "root_job_id": ROOT_B}) is row
    publish_root_state(owners, clock, doc, row, vector + [ROOT_C])
    with pytest.raises(LookupError):
        _retained_root_join(doc, {"work_ref": WORK_REF, "root_job_id": ROOT_B})


@pytest.mark.parametrize("vector", [
    "JOB-001",                                # not a list
    [],                                       # empty — membership needs a vector
    [ROOT_A, ROOT_A, ROOT_B],                 # duplicated candidates
    ["ROOT-9", ROOT_B],                       # non JOB- token
    ["JOB- 9", ROOT_B],                       # whitespace token
    ["", ROOT_B],                             # blank token
    [[ROOT_A], ROOT_B],                      # unhashable malformed candidate
    [ROOT_A],                                 # CONFLICT must actually be multiple
    ["JOB-alpha", ROOT_B],                    # reader-ineligible candidate
    [7, ROOT_B],                              # non-string candidate
    [f"JOB-{n:04d}" for n in range(50)] + [ROOT_A, ROOT_B],  # over the bound
])
def test_malformed_vectors_never_admit_before_runtime(tmp_path, vector):
    owners, clock, cache, doc, row = multi_root_cache(tmp_path)
    publish_root_state(owners, clock, doc, row, vector)

    def acquire(*args, **kwargs):
        pytest.fail("Runtime read before retained-root admission")

    with pytest.raises(LookupError):
        _retained_root_join(doc, {"work_ref": WORK_REF, "root_job_id": ROOT_A})
    with pytest.raises(LookupError):
        read_result_references(
            references_owner(cache, acquire),
            references_frame({"work_ref": WORK_REF, "root_job_id": ROOT_A}))


@pytest.mark.parametrize("mutation", [
    {"root_job_id": ROOT_B},           # a pick: never admitted
    {"root_job_ambiguous": False},     # ambiguous flag withdrawn
    {"runtime_root_state": "RESOLVED"},
    {"runtime_root_state": "UNKNOWN"},
    {"root_job_candidates": None},
])
def test_row_shape_lies_never_admit(tmp_path, mutation):
    owners, clock, cache, doc, row = multi_root_cache(tmp_path)
    row.update(mutation)
    with pytest.raises(LookupError):
        _retained_root_join(doc, {"work_ref": WORK_REF, "root_job_id": ROOT_A})


@pytest.mark.parametrize("duplicate", ["work", "responsibilities"])
def test_duplicate_identity_rows_never_admit(tmp_path, duplicate):
    owners, clock, cache, doc, row = multi_root_cache(tmp_path)
    if duplicate == "work":
        doc["work"] = doc["work"] * 2
    else:
        doc["autonomy"]["responsibilities"] = (
            doc["autonomy"]["responsibilities"] * 2)

    def acquire(*args, **kwargs):
        pytest.fail("Runtime read on a duplicated identity row")

    with pytest.raises(LookupError):
        _retained_root_join(doc, {"work_ref": WORK_REF, "root_job_id": ROOT_A})
    with pytest.raises(LookupError):
        read_result_references(
            references_owner(cache, acquire),
            references_frame({"work_ref": WORK_REF, "root_job_id": ROOT_A}))


# ---------------------------------------------------------------------------
# Selection law: unlisted, unrelated and cross-workstream refusals.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("selection", [
    {"work_ref": WORK_REF, "root_job_id": "JOB-404"},   # unlisted root
    {"work_ref": OTHER_REF, "root_job_id": ROOT_A},     # no such workstream
    {"work_ref": OTHER_REF, "root_job_id": ROOT_C},     # no such workstream
])
def test_unlisted_or_unrelated_selections_refuse_before_runtime(tmp_path,
                                                                selection):
    owners, clock, cache, doc, row = multi_root_cache(tmp_path)

    def acquire(*args, **kwargs):
        pytest.fail("Runtime read before retained-root admission")

    with pytest.raises(LookupError):
        read_result_references(references_owner(cache, acquire),
                               references_frame(selection))


def test_cross_workstream_selection_refuses_both_ways(tmp_path):
    owners, clock, cache, doc, row = multi_root_cache(tmp_path)
    # A second genuine workstream whose own published root is ROOT_C.
    doc["work"].append({"work_ref": OTHER_REF, "agent_os": {"title": "Two"}})
    other = copy.deepcopy(row)
    other.update(responsibility_ref=OTHER_REF, root_job_id=ROOT_C,
                 root_job_candidates=[ROOT_C], root_job_ambiguous=False,
                 runtime_root_state="RESOLVED")
    doc["autonomy"]["responsibilities"].append(other)
    with owners[0].state_lock:
        ccr._publish_source_validity(owners[0], doc, tuple(clock), tuple(clock))

    def acquire(*args, **kwargs):
        pytest.fail("Runtime read on a cross-workstream selection")

    for selection in ({"work_ref": OTHER_REF, "root_job_id": ROOT_A},
                      {"work_ref": WORK_REF, "root_job_id": ROOT_C}):
        with pytest.raises(LookupError):
            read_result_references(references_owner(cache, acquire),
                                   references_frame(selection))


def test_singleton_resolved_row_still_admits_only_its_root(tmp_path):
    owners, clock, cache = cache_fixture(tmp_path)
    doc = owners[0].state_cache["doc"]
    doc["sources"] = {"agent_os_state_generated_at": STAMP}

    def acquire(*args, **kwargs):
        pytest.fail("Runtime read outside the sole root")

    assert _retained_root_join(doc, {"work_ref": WORK_REF,
                                     "root_job_id": ROOT_A}) is (
        doc["autonomy"]["responsibilities"][0])
    with pytest.raises(LookupError):
        _retained_root_join(doc, {"work_ref": WORK_REF,
                                  "root_job_id": ROOT_B})
    body = read_result_references(
        references_owner(cache, _reference_acquire((ROOT_A,))),
        references_frame({"work_ref": WORK_REF, "root_job_id": ROOT_A}))
    assert body["result"]["availability"] == "AVAILABLE"


# ---------------------------------------------------------------------------
# Qualification stays the whole publication; no caller bypass flag exists.
# ---------------------------------------------------------------------------


def test_expired_publication_refuses_even_for_a_listed_root(tmp_path):
    owners, clock, cache, doc, row = multi_root_cache(tmp_path)

    def expire(new_owners, new_clock):
        new_clock[:] = [62000, new_clock[1] + 61000, 62000, new_clock[3] + 61000]

    body = read_references(tmp_path, {"work_ref": WORK_REF,
                                      "root_job_id": ROOT_A},
                           mutate=expire)["result"]
    assert body["availability"] == "UNAVAILABLE"
    assert body["reason_codes"] == ["SOURCE_UNAVAILABLE"]
    assert body["index"] is None
    assert body["catalogue"] == {"generated_at": None, "freshness": "UNKNOWN"}


def test_unqualified_snapshot_returns_false_before_membership(tmp_path):
    owners, clock, cache, doc, row = multi_root_cache(tmp_path)
    clock[:] = [62000, clock[1] + 61000, 62000, clock[3] + 61000]
    snapshot = cache.snapshot()
    assert _qualified_retained_root(snapshot, {"work_ref": WORK_REF,
                                               "root_job_id": ROOT_A}) is False


# ---------------------------------------------------------------------------
# Both roots read; the published row is never refreshed or rewritten.
# ---------------------------------------------------------------------------


def test_both_retained_roots_read_references_without_row_rewrite(tmp_path):
    owners, clock, cache, doc, row = multi_root_cache(tmp_path)
    published = canonical(owners[0].state_cache["doc"])
    for root in ROOTS:
        result = read_result_references(
            references_owner(cache, _reference_acquire(ROOTS)),
            references_frame({"work_ref": WORK_REF, "root_job_id": root}))
        body = result["result"]
        assert body["availability"] == "AVAILABLE" and body["reason_codes"] == []
        assert body["selection"] == {"work_ref": WORK_REF, "root_job_id": root}
        assert body["index"]["root_job_id"] == root
        assert body["index"]["generation"]["state"] == "SAME"
        assert body["catalogue"] == {"generated_at": STAMP, "freshness": "CURRENT"}
        assert body["source_observation"]["state"] == "SAME"
    # The published row keeps its honest CONFLICT facts, byte for byte, and
    # no compositor refresh ran behind the reads.
    assert canonical(owners[0].state_cache["doc"]) == published
    assert (row["root_job_id"], row["root_job_ambiguous"],
            row["runtime_root_state"]) == (None, True, "CONFLICT")
    assert row["root_job_candidates"] == [ROOT_A, ROOT_B]
    assert owners[0].state_compose_seq == 0


def test_result_route_reads_each_retained_root(tmp_path):
    owners, clock, cache, doc, row = multi_root_cache(tmp_path)
    published = canonical(owners[0].state_cache["doc"])
    seen = []

    def project(snapshot, receipt):
        projected = _result_project(snapshot, receipt)
        seen.append(projected)
        return projected

    service = result_service(cache, project=project)
    for root in ROOTS:
        response = asyncio.run(service.handle_frame(
            v2_frame("result", cache_result_selection(root))))
        assert response["ok"] is True
        body = response["result"]
        assert body["availability"] == "AVAILABLE" and body["reason_codes"] == []
        assert body["selection"] == cache_result_selection(root)
        assert body["source_observation"]["state"] == "SAME"
        assert body["source_observation"]["runtime"]["state"] == "SAME"
        # The route serves the projector's own complete document unchanged.
        assert body["result"] == seen[-1].complete
    assert canonical(owners[0].state_cache["doc"]) == published
    assert owners[0].state_compose_seq == 0


def test_result_references_route_reads_each_retained_root(tmp_path):
    owners, clock, cache, doc, row = multi_root_cache(tmp_path)
    service = references_owner(cache, _reference_acquire(ROOTS))
    for root in ROOTS:
        response = asyncio.run(service.handle_frame(
            v2_frame("result_references", {"work_ref": WORK_REF,
                                           "root_job_id": root})))
        assert response["ok"] is True
        assert response["result"]["availability"] == "AVAILABLE"
        assert response["result"]["index"]["root_job_id"] == root


# ---------------------------------------------------------------------------
# Post-acquisition change: source, candidates and permission.
# ---------------------------------------------------------------------------


def test_source_change_during_read_is_typed_conflict(tmp_path):
    owners, clock, cache, doc, row = multi_root_cache(tmp_path)
    baseline = _reference_acquire(ROOTS)

    def acquire(runtime, root, **kwargs):
        companion = baseline(runtime, root, **kwargs)
        doc["work"][0]["agent_os"]["title"] = "Changed"
        return companion

    body = read_result_references(
        references_owner(cache, acquire),
        references_frame({"work_ref": WORK_REF, "root_job_id": ROOT_A}))["result"]
    assert body["availability"] == "UNAVAILABLE"
    assert body["reason_codes"] == ["SOURCE_CHANGED"]
    assert body["source_observation"]["state"] == "CONFLICT"
    assert body["index"] is None


def test_result_route_reports_source_change_after_acquisition(tmp_path):
    owners, clock, cache, doc, row = multi_root_cache(tmp_path)
    baseline = _result_acquire_seam(ROOTS)

    def acquire(runtime, selected, **kwargs):
        pair = baseline(runtime, selected, **kwargs)
        doc["work"][0]["agent_os"]["title"] = "Changed"
        return pair

    service = result_service(cache, acquire=acquire)
    response = asyncio.run(service.handle_frame(
        v2_frame("result", cache_result_selection(ROOT_A))))
    body = response["result"]
    assert body["availability"] == "UNAVAILABLE"
    assert body["reason_codes"] == ["SOURCE_CHANGED"]
    assert body["source_observation"]["state"] == "CONFLICT"
    assert body["result"] is None


def test_candidate_change_after_acquisition_keeps_existing_refusal_order(tmp_path):
    owners, clock, cache, doc, row = multi_root_cache(tmp_path)
    baseline = _reference_acquire(ROOTS)

    def acquire(runtime, root, **kwargs):
        companion = baseline(runtime, root, **kwargs)
        # The publication reconciles to a different root set while the read
        # is in flight: the after-bracket membership join refuses exactly as
        # the existing sole-root join refused, before any body is built.
        publish_root_state(owners, clock, doc, row, (ROOT_C,))
        return companion

    with pytest.raises(LookupError):
        read_result_references(
            references_owner(cache, acquire),
            references_frame({"work_ref": WORK_REF, "root_job_id": ROOT_A}))


def test_result_route_reports_candidate_change_as_source_change(tmp_path):
    owners, clock, cache, doc, row = multi_root_cache(tmp_path)
    baseline = _result_acquire_seam(ROOTS)

    def acquire(runtime, selected, **kwargs):
        pair = baseline(runtime, selected, **kwargs)
        publish_root_state(owners, clock, doc, row, (ROOT_C,))
        return pair

    service = result_service(cache, acquire=acquire)
    response = asyncio.run(service.handle_frame(
        v2_frame("result", cache_result_selection(ROOT_A))))
    body = response["result"]
    assert body["availability"] == "UNAVAILABLE"
    assert body["reason_codes"] == ["SOURCE_CHANGED"]


def test_validity_expiry_between_brackets_is_source_unavailable(tmp_path):
    owners, clock, cache, doc, row = multi_root_cache(tmp_path)
    baseline = _result_acquire_seam(ROOTS)

    def acquire(runtime, selected, **kwargs):
        pair = baseline(runtime, selected, **kwargs)
        clock[:] = [62000, clock[1] + 61000, 62000, clock[3] + 61000]
        return pair

    service = result_service(cache, acquire=acquire)
    response = asyncio.run(service.handle_frame(
        v2_frame("result", cache_result_selection(ROOT_A))))
    body = response["result"]
    assert body["reason_codes"] == ["SOURCE_UNAVAILABLE"]
    assert body["result"] is None


def test_permission_change_after_acquisition_denies(tmp_path):
    owners, clock, cache, doc, row = multi_root_cache(tmp_path)
    calls = []

    def authorize(principal):
        calls.append(1)
        return len(calls) == 1

    service = result_service(cache, authorize=authorize)
    response = asyncio.run(service.handle_frame(
        v2_frame("result", cache_result_selection(ROOT_A))))
    assert response == error("access_denied", 403)


def test_permission_change_after_references_read_denies(tmp_path):
    owners, clock, cache, doc, row = multi_root_cache(tmp_path)
    calls = []

    def authorize(principal):
        calls.append(1)
        return len(calls) == 1

    service = WorkspaceReadService(
        cache=cache, runtime=object(), authorize=authorize, armed={},
        runtime_identity={}, mission_v3_acquire=_reference_acquire(ROOTS))
    response = asyncio.run(service.handle_frame(
        v2_frame("result_references", {"work_ref": WORK_REF,
                                       "root_job_id": ROOT_A})))
    assert response == error("access_denied", 403)


# ---------------------------------------------------------------------------
# Scope: Mission and the programs list keep their existing law exactly.
# ---------------------------------------------------------------------------


def test_mission_keeps_sole_root_join_on_multi_row(tmp_path):
    owners, clock, cache, doc, row = multi_root_cache(tmp_path)

    def acquire(*args, **kwargs):
        pytest.fail("Mission touched Runtime for a multi-root row")

    service = WorkspaceReadService(cache=cache, runtime=object(),
                                   authorize=lambda principal: True, armed={},
                                   runtime_identity={}, mission_v3_acquire=acquire)
    response = asyncio.run(service.handle_frame(
        v2_frame("mission_v3", {"work_ref": WORK_REF, "root_job_id": ROOT_A})))
    assert response == error("selection_not_found", 404)


def test_programs_list_still_publishes_the_multi_root_row(tmp_path):
    owners, clock, cache, doc, row = multi_root_cache(tmp_path)

    def acquire(*args, **kwargs):
        pytest.fail("Programs read acquired Runtime")

    service = WorkspaceReadService(cache=cache, runtime=object(),
                                   authorize=lambda principal: True, armed={},
                                   runtime_identity={}, acquire=acquire)
    response = asyncio.run(service.handle_frame(programs_frame()))
    assert response["ok"] is True
    body = response["result"]
    assert body["availability"] == "AVAILABLE"
    published = body["control_room"]["autonomy"]["responsibilities"][0]
    assert published["root_job_candidates"] == [ROOT_A, ROOT_B]
    assert (published["root_job_id"], published["root_job_ambiguous"],
            published["runtime_root_state"]) == (None, True, "CONFLICT")
    assert owners[0].state_compose_seq == 0


# ---------------------------------------------------------------------------
# Real bounded Runtime: two actual roots in one store, read through the
# unchanged production seam (existing OHF chain builders; no dispatch).
# ---------------------------------------------------------------------------


def _second_completed_root(store):
    """Second actual root in the SAME store, with a validated completion.

    The existing ``complete_all_severity_chain`` builder is single-use on one
    store (fixed intent id and OHF identity seeds), so this driver reuses its
    exact builders — the existing intent/cycle/OHF completion helpers — with
    second-chain seeds.  Every boundary is the same inert OHF Runtime
    boundary; no provider, worker or dispatch outside this store is touched.
    """
    runtime = er.Runtime.at(store)
    receipt = submit_intent(runtime, _v2_intent(intent_id="CEO-BOUNDED-SECOND-ROOT", workstream=WORK_REF))
    root = runtime.jobs.get_job(receipt["job_id"])
    assert root is not None
    dispatches = []

    def accepted_dispatch(job_id, command_id):
        outcome = runtime.attempts.dispatch_cycle_job(
            job_id, command_id=command_id, worker_id="worker-a")
        dispatches.append(outcome)
        return outcome

    cycle = CooCycle(runtime, dispatcher=accepted_dispatch)
    assert cycle.run_once(root.job_id).action == "PLANNER_CREATED"
    assert cycle.run_once(root.job_id).action == "DISPATCHED"
    planner = dispatches[-1]
    plan_body = {
        "schema_version": "mastermind.execution_plan/v1",
        "root_job_id": root.job_id,
        "plan_attempt_id": planner.attempt.attempt_id,
        "steps": [{
            "ordinal": 0,
            "step_id": "step-1",
            "objective": "Perform one bounded read-only task.",
            "business_impact": "routine",
            "review_required": True,
            "requested_authorities": ["READ"],
            "allowed_write_paths": [],
            "validation_ids": [],
            "attempt_limit": 1,
            "cost_class": "small",
        }],
    }
    _complete_ohf_role(runtime, planner, plan_body, identity_seed=4201)
    assert cycle.run_once(root.job_id).action == "PLAN_ADMITTED"
    assert cycle.run_once(root.job_id).action == "DISPATCHED"
    work = dispatches[-1]
    work_body = {
        "schema_version": "mastermind.work_result/v1",
        "root_job_id": root.job_id,
        "plan_attempt_id": planner.attempt.attempt_id,
        "plan_digest": result_digest(plan_body),
        "plan_step_id": "step-1",
        "repair_round": 0,
        "artifacts": [],
        "evidence_digests": [],
    }
    _complete_ohf_role(runtime, work, work_body, identity_seed=4202)
    completion = runtime.validated_role_completion(
        work.attempt.job_id, expected_attempt_id=work.attempt.attempt_id)
    return runtime, root, completion


def _store_state(runtime):
    """Read-only digest of the store's jobs and events, for effect proofs."""
    jobs = sorted((job.job_id, job.status, job.current_attempt_id)
                  for job in runtime.jobs.list_jobs())
    events = sorted((event.aggregate_type, event.aggregate_id, event.sequence,
                     event.event_type)
                    for event in runtime.events.list_events())
    return digest(jobs), digest(events)


@pytest.fixture
def two_root_runtime(tmp_path, monkeypatch):
    """One actual store, two actual roots, each with a validated completion.

    Root A comes from the existing all-severity chain builder (review
    completion); root B comes from the same builders re-driven with fresh
    intent and OHF identity seeds (work completion).  The candidate vector
    the CCR fixture publishes cites exactly these two actual store roots;
    the workstream-to-candidates mapping itself is the fixture publication;
    both roots' actual immutable JOB_CREATED Events independently carry WORK_REF.
    """
    # Input to the actual strict-v2 producer, before JOB_CREATED; never a
    # metadata/validator patch. Both immutable Events carry this real join.
    original_intent = fc._v2_intent
    monkeypatch.setattr(fc, "_v2_intent", lambda **kw: original_intent(workstream=WORK_REF, **kw))
    store = tmp_path / "runtime"
    runtime, root_a, _work_a, review_a = complete_all_severity_chain(store)
    runtime_b, root_b, work_b = _second_completed_root(store)
    assert runtime_b.store.root == runtime.store.root
    assert root_b.job_id != root_a.job_id
    keeper, namespace, binding, reader = _bound_reader(runtime)
    try:
        yield SimpleNamespace(runtime=runtime, reader=reader,
                              namespace=namespace, root_a=root_a,
                              review_a=review_a, root_b=root_b, work_b=work_b)
    finally:
        _release(keeper, binding)


def real_result_service(cache, fixture, *, authorize=lambda principal: True,
                        **kwargs):
    def bound(actual):
        assert actual is fixture.runtime
        return fixture.reader

    return WorkspaceReadService(cache=cache, runtime=fixture.runtime,
                                authorize=authorize, armed={},
                                runtime_identity={"db_present": True},
                                bounded_runtime=bound, **kwargs)


def real_selection(fixture, root):
    completion = (fixture.review_a if root == fixture.root_a.job_id
                  else fixture.work_b)
    return {"work_ref": WORK_REF, "root_job_id": root,
            "job_id": completion.job.job_id,
            "attempt_id": completion.attempt.attempt_id,
            "result_envelope_digest": completion.result_digest}


def test_each_listed_root_reads_the_real_runtime(two_root_runtime, tmp_path):
    fixture = two_root_runtime
    owners, clock, cache, doc, row = multi_root_cache(
        tmp_path, (fixture.root_a.job_id, fixture.root_b.job_id))
    captured = []

    def project(snapshot, receipt):
        captured.append((snapshot, receipt))
        return frp.project_fabric_role_result(snapshot, receipt)

    service = real_result_service(cache, fixture, result_project=project)
    before_state = _store_state(fixture.runtime)
    namespace_entries = fixture.namespace.entries
    for root in (fixture.root_a.job_id, fixture.root_b.job_id):
        selected = real_selection(fixture, root)
        response = asyncio.run(service.handle_frame(v2_frame("result", selected)))
        assert response["ok"] is True
        body = response["result"]
        assert body["availability"] == "AVAILABLE" and body["reason_codes"] == []
        assert body["selection"] == selected
        # The route serves the real projector's document for the actual
        # bounded snapshot it acquired — deep root/job/attempt/digest
        # provenance over the store's own evidence.
        snapshot, receipt = captured[-1]
        assert body["result"] == frp.project_fabric_role_result(
            snapshot, receipt).complete
        assert (snapshot.root_job_id, snapshot.job_id, snapshot.attempt_id,
                snapshot.result_envelope_digest) == (
            selected["root_job_id"], selected["job_id"],
            selected["attempt_id"], selected["result_envelope_digest"])
        assert snapshot.root_metadata.work_ref == WORK_REF
        assert receipt.state == "SAME"
        assert body["source_observation"]["state"] == "SAME"
        assert body["source_observation"]["runtime"] == body["result"]["generation"]
    # Read-only: the store's jobs and events are unchanged, every observation
    # closed, and the published CCR row still carries its honest CONFLICT.
    assert _store_state(fixture.runtime) == before_state
    assert fixture.namespace.entries == namespace_entries + 2
    assert fixture.namespace.entries == fixture.namespace.exits
    assert not fixture.namespace.active
    assert (row["root_job_id"], row["root_job_ambiguous"],
            row["runtime_root_state"]) == (None, True, "CONFLICT")


def test_listed_root_with_no_store_evidence_refuses(two_root_runtime, tmp_path):
    fixture = two_root_runtime
    owners, clock, cache, doc, row = multi_root_cache(
        tmp_path, (fixture.root_a.job_id, fixture.root_b.job_id))
    service = real_result_service(cache, fixture)
    before_state = _store_state(fixture.runtime)
    namespace_entries = fixture.namespace.entries
    # Root B is a genuine member of the published vector, but the selection
    # carries root A's job/attempt/digest: the actual acquisition refuses.
    cross = dict(real_selection(fixture, fixture.root_b.job_id),
                 job_id=fixture.review_a.job.job_id,
                 attempt_id=fixture.review_a.attempt.attempt_id,
                 result_envelope_digest=fixture.review_a.result_digest)
    response = asyncio.run(service.handle_frame(v2_frame("result", cross)))
    body = response["result"]
    assert body["availability"] == "UNAVAILABLE"
    assert body["reason_codes"] == ["SOURCE_UNAVAILABLE"]
    assert body["result"] is None
    assert body["source_observation"]["control_room"] is None
    assert body["source_observation"]["runtime"] is None
    assert _store_state(fixture.runtime) == before_state
    # One observation opened and physically closed; nothing leaked.
    assert fixture.namespace.entries == namespace_entries + 1
    assert fixture.namespace.entries == fixture.namespace.exits
    assert not fixture.namespace.active


def test_cross_root_evidence_refuses_on_the_real_binding_law(two_root_runtime,
                                                             tmp_path):
    fixture = two_root_runtime
    owners, clock, cache, doc, row = multi_root_cache(
        tmp_path, (fixture.root_a.job_id, fixture.root_b.job_id))
    # Labelled seam: the acquisition returns the OTHER root's real bounded
    # snapshot and finalized receipt; the refusing guard below is the
    # unchanged production pre-projection binding law, not the seam.
    snapshot_a, receipt_a = _select_bound(fixture.reader,
                                          fixture.root_a.job_id,
                                          fixture.review_a)

    def acquire(runtime, selected, **kwargs):
        assert selected["root_job_id"] == fixture.root_b.job_id
        return snapshot_a, receipt_a

    service = real_result_service(cache, fixture, result_acquire=acquire)
    response = asyncio.run(service.handle_frame(
        v2_frame("result", real_selection(fixture, fixture.root_b.job_id))))
    body = response["result"]
    assert body["availability"] == "UNAVAILABLE"
    assert body["reason_codes"] == ["SOURCE_UNAVAILABLE"]
    assert body["result"] is None
    assert body["source_observation"]["control_room"] is None


def test_singleton_row_still_reads_the_real_runtime_unchanged(two_root_runtime,
                                                              tmp_path):
    fixture = two_root_runtime
    owners, clock, cache, doc, row = multi_root_cache(
        tmp_path, (fixture.root_a.job_id,))
    # Reconciled publication: the sole root is resolved again.
    row.update(root_job_id=fixture.root_a.job_id,
               root_job_candidates=[fixture.root_a.job_id],
               root_job_ambiguous=False, runtime_root_state="RESOLVED")
    with owners[0].state_lock:
        ccr._publish_source_validity(owners[0], doc, tuple(clock), tuple(clock))
    captured = []

    def project(snapshot, receipt):
        captured.append((snapshot, receipt))
        return frp.project_fabric_role_result(snapshot, receipt)

    service = real_result_service(cache, fixture, result_project=project)
    selected = real_selection(fixture, fixture.root_a.job_id)
    response = asyncio.run(service.handle_frame(v2_frame("result", selected)))
    assert response["ok"] is True
    body = response["result"]
    assert body["availability"] == "AVAILABLE"
    assert body["selection"] == selected
    assert body["source_observation"]["state"] == "SAME"
    snapshot, receipt = captured[-1]
    assert body["result"] == frp.project_fabric_role_result(
        snapshot, receipt).complete
    assert (snapshot.root_job_id, snapshot.root_job_id) == (
        fixture.root_a.job_id, selected["root_job_id"])


def test_unlisted_root_refuses_before_the_real_runtime(two_root_runtime,
                                                       tmp_path):
    fixture = two_root_runtime
    owners, clock, cache, doc, row = multi_root_cache(
        tmp_path, (fixture.root_a.job_id, fixture.root_b.job_id))

    def acquire(runtime, selected, **kwargs):
        pytest.fail("Runtime read for an unlisted root")

    service = real_result_service(cache, fixture, result_acquire=acquire)
    response = asyncio.run(service.handle_frame(
        v2_frame("result", dict(real_selection(fixture, fixture.root_a.job_id),
                                root_job_id="JOB-404"))))
    assert response == error("selection_not_found", 404)


@pytest.mark.parametrize("cause", ["disagreement", "other_issue", "global_issue", "source_failure"])
def test_root_choice_does_not_resolve_any_other_conflict(tmp_path, cause):
    owners, clock, cache, doc, row = multi_root_cache(tmp_path)
    if cause == "disagreement":
        row["disagreements"] = [{"field": "wake_outcome", "values": ["a", "b"]}]
    elif cause == "source_failure":
        doc["autonomy"]["source_failures"] = [{"code": "runtime_unavailable"}]
    else:
        doc["autonomy"]["issues"] = [{"responsibility_ref": WORK_REF if cause == "other_issue" else None,
                                      "code": "reconciliation_required"}]
    with pytest.raises(LookupError):
        _retained_root_join(doc, {"work_ref": WORK_REF, "root_job_id": ROOT_A})


def test_actual_strict_v2_roots_list_and_read_through_both_normal_owners(two_root_runtime, tmp_path):
    f = two_root_runtime
    _, _, cache, _, row = multi_root_cache(tmp_path, (f.root_a.job_id, f.root_b.job_id))
    service = real_result_service(cache, f)
    before = _store_state(f.runtime)
    for root in (f.root_a.job_id, f.root_b.job_id):
        pair = {"work_ref": WORK_REF, "root_job_id": root}
        listing = asyncio.run(service.handle_frame(v2_frame("result_references", pair)))["result"]
        assert listing["availability"] == "AVAILABLE"
        expected = real_selection(f, root)
        assert any(all(ref[k] == expected[k] for k in ("root_job_id", "job_id", "attempt_id", "result_envelope_digest"))
                   for ref in listing["index"]["refs"])
        detail = asyncio.run(service.handle_frame(v2_frame("result", expected)))["result"]
        assert detail["availability"] == "AVAILABLE"
        assert detail["selection"] == expected
    assert _store_state(f.runtime) == before
    assert row["runtime_root_state"] == "CONFLICT" and row["root_job_id"] is None
    assert f.namespace.entries == f.namespace.exits and not f.namespace.active


@pytest.mark.parametrize("actual_work_ref", [None, OTHER_REF])
def test_multi_result_requires_actual_nonnull_matching_workstream(tmp_path, actual_work_ref):
    _, _, cache, _, _ = multi_root_cache(tmp_path)
    def acquire(runtime, selected, **kwargs):
        snapshot, receipt = _result_acquire_seam()(runtime, selected, **kwargs)
        snapshot.root_metadata.work_ref = actual_work_ref
        return snapshot, receipt
    response = asyncio.run(result_service(cache, acquire=acquire).handle_frame(
        v2_frame("result", cache_result_selection(ROOT_A))))
    assert response["result"]["availability"] == "UNAVAILABLE"
    assert response["result"]["result"] is None


def test_actual_workstream_cannot_be_rebound_by_a_listed_cache_candidate(two_root_runtime, tmp_path):
    f = two_root_runtime
    owners, clock, cache, doc, row = multi_root_cache(tmp_path, (f.root_a.job_id, f.root_b.job_id))
    # A different source publication is not permission to rewrite the actual
    # strict-v2 JOB_CREATED workstream in either normal Runtime reader.
    doc["work"][0]["work_ref"] = OTHER_REF
    row["responsibility_ref"] = OTHER_REF
    publish_root_state(owners, clock, doc, row, (f.root_a.job_id, f.root_b.job_id))
    service = real_result_service(cache, f)
    pair = {"work_ref": OTHER_REF, "root_job_id": f.root_a.job_id}
    listed = asyncio.run(service.handle_frame(v2_frame("result_references", pair)))["result"]
    assert listed["availability"] == "UNAVAILABLE" and listed["index"] is None
    selection = dict(real_selection(f, f.root_a.job_id), work_ref=OTHER_REF)
    detail = asyncio.run(service.handle_frame(v2_frame("result", selection)))["result"]
    assert detail["availability"] == "UNAVAILABLE" and detail["result"] is None
    assert f.namespace.entries == f.namespace.exits and not f.namespace.active
