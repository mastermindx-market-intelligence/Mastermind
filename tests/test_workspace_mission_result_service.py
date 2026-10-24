"""One Control Room bracket around one joint Runtime selection."""
import asyncio
import copy
import json
from contextlib import contextmanager

import pytest

from control_plane import executive_runtime as er
from control_plane import fabric_job_view as fjv
from control_plane import fabric_result_projection as frp
from control_plane import mission_workspace as mw
from integrations.mastermind_workspace_app.contract import canonical, error
from scripts import chairman_control_room as ccr
from tests.test_fabric_result_projection import (
    _bound_reader,
    _release,
    _select_bound,
    complete_all_severity_chain,
)
from tests.test_mission_workspace import _owner_observation_inputs
from tests.test_workspace_read_service import cache_fixture, frame
from tests.test_workspace_result_service import request as result_request
from tests.test_workspace_result_service import result_owner, service
from integrations.mastermind_workspace_app.contract import (
    MISSION_RESULT_FRAME_SCHEMA,
    MISSION_RESULT_OPERATION,
)


def _build_owner(tmp_path):
    writer, root, _work, review = complete_all_severity_chain(tmp_path / "runtime")
    keeper, namespace, binding, reader = _bound_reader(writer)
    snapshot, receipt = _select_bound(reader, root.job_id, review)
    selected = dict(
        work_ref=snapshot.root_metadata.work_ref or "WS:ONE",
        root_job_id=root.job_id,
        job_id=review.job.job_id,
        attempt_id=review.attempt.attempt_id,
        result_envelope_digest=review.result_digest,
    )
    owners, clock, cache = cache_fixture(tmp_path)
    doc = _owner_observation_inputs()["control_room"]
    doc = json.loads(
        json.dumps(doc)
        .replace("JOB-1", root.job_id)
        .replace("WS:ONE", selected["work_ref"])
        .replace("2026-09-20", "2026-09-21")
    )
    doc["generated_at"] = owners[0].state_cache["doc"]["generated_at"]
    doc["autonomy"]["generated_at"] = doc["generated_at"]
    doc["autonomy"]["schema"] = "mastermind.autonomy_control_room.v1"
    row = doc["autonomy"]["responsibilities"][0]
    row["freshness"] = "current"
    row["validity"] = owners[0].state_cache["doc"]["autonomy"]["responsibilities"][0]["validity"]
    owners[0].state_cache["doc"] = doc
    owners[0].state_cache.pop("source_validity_bounds", None)
    with owners[0].state_lock:
        ccr._publish_source_validity(owners[0], doc, tuple(clock), tuple(clock))
    return dict(
        writer=writer, reader=reader, namespace=namespace, binding=binding,
        keeper=keeper, owners=owners, clock=clock, cache=cache, selection=selected,
        snapshot=snapshot, receipt=receipt,
    )


@pytest.fixture
def content_owner(tmp_path, monkeypatch):
    import tests.test_executive_os_phase1fc as fixtures

    original = fixtures.result_canonical_bytes

    def encode(value):
        if isinstance(value, dict) and value.get("summary") == "bounded typed fixture result":
            value["summary"] = "漢" * 6000
        return original(value)

    monkeypatch.setattr(fixtures, "result_canonical_bytes", encode)
    owner = _build_owner(tmp_path)
    try:
        yield owner
    finally:
        _release(owner["keeper"], owner["binding"])


def mission_frame(owner, **selection):
    value = frame()
    value.update(
        schema=MISSION_RESULT_FRAME_SCHEMA,
        operation=MISSION_RESULT_OPERATION,
        selection=dict(owner["selection"], **selection),
    )
    return value


def call_pair(owner, **kwargs):
    return asyncio.run(service(owner, **kwargs).handle_frame(mission_frame(owner)))


def _forbid_second_selection(monkeypatch):
    monkeypatch.setattr(
        er.BoundedRuntimeReadObservation, "read_job_root_bounded",
        lambda *args, **kwargs: pytest.fail("second root selection"),
    )
    monkeypatch.setattr(
        er.BoundedRuntimeReadObservation, "read_role_result_bounded",
        lambda *args, **kwargs: pytest.fail("second result selection"),
    )
    monkeypatch.setattr(
        fjv, "read_fabric_view_v3_from_runtime",
        lambda *args, **kwargs: pytest.fail("second fabric observation"),
    )


def _trace(monkeypatch):
    traces = []
    original = er.sqlite3.connect

    def connect(*args, **kwargs):
        connection = original(*args, **kwargs)
        connection.set_trace_callback(traces.append)
        return connection

    monkeypatch.setattr(er.sqlite3, "connect", connect)
    return traces


def test_associated_pair_uses_one_selection_and_final_mission(result_owner, monkeypatch):
    owner = result_owner
    _forbid_second_selection(monkeypatch)
    for registry, method in (
        (owner["reader"].jobs, "list_jobs"),
        (owner["reader"].attempts, "list_attempts"),
        (owner["reader"].events, "list_events"),
    ):
        monkeypatch.setattr(registry, method, lambda *args, **kwargs: pytest.fail("unbounded acquisition"))
    traces = _trace(monkeypatch)
    before = owner["namespace"].entries
    response = call_pair(owner)
    assert response["ok"] is True, response
    body = response["result"]
    statements = [sql.strip().upper() for sql in traces]
    assert statements.count("PRAGMA DATA_VERSION") == 2
    assert not any(sql.startswith(("INSERT", "UPDATE", "DELETE")) for sql in statements)
    assert len(statements) <= er.BOUNDED_ROLE_RESULT_MAX_STATEMENTS
    assert owner["namespace"].entries == before + 1 == owner["namespace"].exits
    assert not owner["namespace"].active
    assert body["schema"] == "mastermind.workspace_mission_result.v1"
    assert body["availability"] == "AVAILABLE"
    assert body["reason_codes"] == []
    mission, role = body["mission"], body["role_result"]
    assert mission["schema"] == "mastermind.mission_workspace.v3"
    assert mission["read_state"]["state"] == "CURRENT"
    assert role["schema"] == "mastermind.workspace_role_result.v1"
    assert role["availability"] == "AVAILABLE"
    assert set(role) == {
        "schema", "selection", "availability", "reason_codes", "source_observation", "result",
    }
    identity = role["source_observation"]["runtime"]["source_identity"]
    assert mission["source"]["owner_observation"]["state"] == "SAME"
    assert mission["source"]["owner_observation"]["runtime"]["source_identity"] == identity
    assert mission["result_refs"]["generation"]["source_identity"] == identity
    assert mission["result_refs"]["generation"]["state"] == "SAME"
    assert any(
        ref["root_job_id"] == owner["selection"]["root_job_id"]
        and ref["job_id"] == owner["selection"]["job_id"]
        and ref["attempt_id"] == owner["selection"]["attempt_id"]
        and ref["result_envelope_digest"] == owner["selection"]["result_envelope_digest"]
        for ref in mission["result_refs"]["refs"]
    )
    assert role["result"]["review"]["verdict"] == "reject"
    assert role["result"]["execution_status"] == "COMPLETED"
    assert role["result"]["acceptance"] == "NOT_PROJECTED"
    assert role["selection"]["result_envelope_digest"] != role["result"]["review"]["reviewed_result_digest"]
    assert mission["acceptance"]["state"] == "NOT_PROJECTED"
    assert role["source_observation"]["control_room"] == mission["source"]["owner_observation"]["control_room"]
    assert len(canonical({"ok": True, "result": role})) + 1 <= 16384
    assert len(canonical({"ok": True, "result": body})) + 1 <= 2_000_000
    again = call_pair(owner)["result"]
    assert again["role_result"]["source_observation"]["runtime"]["source_identity"] != identity


def test_content_fallback_stays_inside_compound_available(content_owner, monkeypatch):
    _forbid_second_selection(monkeypatch)
    body = call_pair(content_owner)["result"]
    role = body["role_result"]
    assert body["availability"] == "AVAILABLE"
    assert body["reason_codes"] == []
    assert body["mission"]["read_state"]["state"] == "CURRENT"
    assert body["mission"]["schema"] == "mastermind.mission_workspace.v3"
    assert role["availability"] == "CONTENT_OVER_BUDGET"
    assert role["reason_codes"] == ["CONTENT_OVER_BUDGET"]
    assert role["result"]["availability"] == "CONTENT_OVER_BUDGET"
    assert role["result"]["content"] is None
    assert role["result"]["content_complete"] is False
    assert role["result"]["omitted"] == ["role_result", "summary", "next_actions"]
    assert role["result"]["review"]["verdict"] == "reject"
    assert role["result"]["execution_status"] == "COMPLETED"
    assert role["result"]["acceptance"] == "NOT_PROJECTED"
    assert any(
        ref["result_envelope_digest"] == content_owner["selection"]["result_envelope_digest"]
        for ref in body["mission"]["result_refs"]["refs"]
    )
    assert len(canonical({"ok": True, "result": role})) + 1 <= 16384
    assert len(canonical({"ok": True, "result": body})) + 1 <= 2_000_000


def test_noncurrent_mission_refuses_a_same_runtime_pair(result_owner, monkeypatch):
    owner = result_owner
    row = owner["owners"][0].state_cache["doc"]["autonomy"]["responsibilities"][0]
    row["dispatch"]["historical"] = True
    seen = {}
    original = mw.compose_mission_workspace_v3

    def compose(**kwargs):
        document = original(**kwargs)
        seen["state"] = document["read_state"]["state"]
        seen["refs"] = list(document["result_refs"]["refs"])
        return document

    monkeypatch.setattr(mw, "compose_mission_workspace_v3", compose)
    before = owner["namespace"].entries
    body = call_pair(owner)["result"]
    assert seen["state"] == "PARTIAL"
    assert seen["refs"] == []
    assert body["availability"] == "UNAVAILABLE"
    assert body["reason_codes"] == ["SOURCE_UNAVAILABLE"]
    assert body["mission"] is None and body["role_result"] is None
    assert owner["namespace"].entries == before + 1 == owner["namespace"].exits
    assert not owner["namespace"].active


@pytest.mark.parametrize("mutation", ["owner", "publication", "document"])
def test_control_room_change_discards_the_pair(result_owner, mutation):
    owner = result_owner
    original = owner["cache"].snapshot

    def snapshot():
        current = original()
        if not hasattr(snapshot, "seen"):
            snapshot.seen = 1
            return current
        if mutation == "owner":
            owners, _clock, _cache = cache_fixture(owner["writer"].store.root)
            owner["owners"][0] = owners[0]
        elif mutation == "publication":
            owner["owners"][0].state_published_seq += 1
        else:
            owner["owners"][0].state_cache["doc"]["work"][0]["agent_os"]["title"] = "changed"
        return original()

    owner["cache"].snapshot = snapshot
    body = call_pair(owner)["result"]
    assert body["availability"] == "UNAVAILABLE"
    assert body["reason_codes"] == ["SOURCE_CHANGED"]
    assert body["mission"] is None and body["role_result"] is None


def test_wrong_digest_and_close_uncertainty_discard_both(result_owner, monkeypatch):
    owner = result_owner
    before = owner["namespace"].entries
    wrong = asyncio.run(service(owner).handle_frame(
        mission_frame(owner, result_envelope_digest="ab" * 32),
    ))["result"]
    assert wrong["reason_codes"] == ["SOURCE_UNAVAILABLE"]
    assert wrong["mission"] is None and wrong["role_result"] is None
    assert not owner["namespace"].active
    original = er.RuntimeStore._close_read_connection

    def close(store, connection):
        original(store, connection)
        if store is owner["reader"].store:
            raise er.RuntimeReadUnavailable("fixture close uncertainty")

    monkeypatch.setattr(er.RuntimeStore, "_close_read_connection", close)
    closed = call_pair(owner)["result"]
    assert closed["reason_codes"] == ["SOURCE_UNAVAILABLE"]
    assert closed["mission"] is None and closed["role_result"] is None
    assert "source_identity" not in json.dumps(closed)
    assert owner["namespace"].entries >= before
    assert owner["namespace"].entries == owner["namespace"].exits
    assert not owner["namespace"].active


def test_combined_statement_ceiling_discards_both_without_a_half_pair(result_owner, monkeypatch):
    monkeypatch.setattr(er, "BOUNDED_ROLE_RESULT_MAX_STATEMENTS", 3)
    before = result_owner["namespace"].entries
    body = call_pair(result_owner)["result"]
    assert body["availability"] == "UNAVAILABLE"
    assert body["reason_codes"] == ["OVER_BUDGET"]
    assert body["mission"] is None and body["role_result"] is None
    assert result_owner["namespace"].entries == result_owner["namespace"].exits
    assert result_owner["namespace"].entries >= before
    assert not result_owner["namespace"].active


def test_neither_result_representation_discards_the_compound(result_owner):
    def project(snapshot, receipt):
        value = frp.project_fabric_role_result(snapshot, receipt)
        complete = copy.deepcopy(value.complete)
        fallback = copy.deepcopy(value.content_over_budget)
        complete["content"]["summary"] = "漢" * 6000
        fallback["omitted"] = ["x" * 20000]
        return frp.FabricRoleResultProjection(complete=complete, content_over_budget=fallback)

    body = call_pair(result_owner, result_project=project)["result"]
    assert body["availability"] == "UNAVAILABLE"
    assert body["reason_codes"] == ["RESPONSE_OVER_BUDGET"]
    assert body["mission"] is None and body["role_result"] is None


@pytest.mark.parametrize("stage", ["before", "after"])
def test_permission_reload_returns_no_pair(result_owner, stage, monkeypatch):
    authority = {"enabled": True, "digest": "a" * 64}

    def authorize(principal):
        return authority["enabled"]

    authorize.binding_digest = lambda principal: authority["digest"]
    owner = result_owner
    original = er.Runtime.observe_bounded_read

    @contextmanager
    def observed(runtime):
        with original(runtime) as read:
            yield read
        if runtime is owner["reader"] and stage == "after":
            authority["enabled"] = False

    monkeypatch.setattr(er.Runtime, "observe_bounded_read", observed)
    if stage == "before":
        authority["enabled"] = False
    before = owner["namespace"].entries
    response = call_pair(owner, authorize=authorize)
    assert response == error("access_denied", 403)
    assert "reject" not in json.dumps(response)
    assert "role_result" not in json.dumps(response)
    assert owner["namespace"].entries - before == (stage == "after")


def test_missing_join_is_not_found_before_runtime(result_owner):
    result_owner["owners"][0].state_cache["doc"]["work"] = []
    before = result_owner["namespace"].entries
    assert call_pair(result_owner) == error("selection_not_found", 404)
    assert result_owner["namespace"].entries == before


def test_standalone_result_route_remains_available(result_owner):
    response = asyncio.run(service(result_owner).handle_frame(result_request(result_owner)))
    assert response["ok"] is True
    assert response["result"]["schema"] == "mastermind.workspace_role_result.v1"
    assert response["result"]["availability"] == "AVAILABLE"
