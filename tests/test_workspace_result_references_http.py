"""Signed HTTP edge/transport proof for the retained-result-reference route.

Hermetic tests: every ``client.request`` is replaced by a fake recording the
exact frame it would have been sent.  The available reference envelope is
built around an index produced by the real Fabric reference-index composer
so the closed wrapper is exercised against genuine producer-shaped data;
local fixtures demonstrate transport behavior only and never claim an
installed machine source.
"""
from __future__ import annotations

import asyncio
import copy
from types import SimpleNamespace

import httpx
import pytest
from starlette.testclient import TestClient

from common import executive_workspace_contract as wire
from control_plane import fabric_job_view as view
from control_plane import workspace_result_references as references
from control_plane.executive_runtime import JobStatus
from integrations.mastermind_workspace_app.app import _result_references_envelope_response
from tests.test_workspace_read_app import (
    _FakeWorkspaceClient, _make_app, _workspace_token, rsa_key,
)

ROUTE = "/workspace/result-references/current"
SELECTED = {"work_ref": "WS:AA1", "root_job_id": "JOB-1"}
BODY_SCHEMA = "mastermind.workspace_result_references.v1"
ATTEMPT_ID = "ATT-" + "a" * 32


def _principal():
    return {"policy_id": "workspace-test", "issuer_digest": "a" * 64,
            "subject_digest": "b" * 64, "client_ref": "fixture-web",
            "resource": wire.RESOURCE, "scopes": [wire.SCOPE]}


def _reference_frame(selection=None):
    return {"schema": wire.FRAME_SCHEMA_V2, "operation": "result_references",
            "selection": dict(SELECTED if selection is None else selection),
            "principal": _principal()}


def _genuine_index():
    """One real ``mastermind.fabric_result_reference_index.v1`` from the
    existing composer — exactly the bounded rows the producer ships."""
    receipt = {
        "schema_version": "mastermind.orchestration_terminal_receipt/v1",
        "status": "COMPLETED", "job_id": "JOB-2", "attempt_id": ATTEMPT_ID,
        "orchestration_role": "work", "execution_mode": "OPERATOR_HARNESS",
        "result_seal_command_id": "orchestration-result-seal:" + ATTEMPT_ID,
        "result_evidence": None, "result_envelope": {"nested": True},
        "result_envelope_digest": "b" * 64, "artifact_receipt_digest": "c" * 64,
        "validation_receipt_digest": "d" * 64, "effective_grant_digest": "e" * 64,
        "terminal_evidence_digest": "f" * 64,
    }
    root = SimpleNamespace(
        job_id="JOB-1", root_job_id="JOB-1", status=JobStatus.QUEUED,
        orchestration_role="aggregation", current_attempt_id=None,
        result=None, parent_job_id=None,
    )
    job = SimpleNamespace(
        job_id="JOB-2", root_job_id="JOB-1", status=JobStatus.COMPLETED,
        orchestration_role="work", current_attempt_id=ATTEMPT_ID,
        result=receipt, parent_job_id="JOB-1",
    )
    attempt = SimpleNamespace(
        attempt_id=ATTEMPT_ID, job_id="JOB-2", status=JobStatus.COMPLETED,
        execution_mode="OPERATOR_HARNESS", result=receipt,
    )
    snapshot = SimpleNamespace(
        root_job_id="JOB-1", jobs=(root, job), attempts=(attempt,),
        jobs_truncated=False, attempts_truncated_job_ids=(),
        snapshot_digest="a" * 64,
    )
    generation = {"schema": "mastermind.runtime_read_observation.v1",
                  "state": "SAME", "source_identity": "a" * 32,
                  "before": 1, "after": 1}
    index = view.compose_fabric_result_reference_index(snapshot, generation)
    assert index["availability"] == "AVAILABLE" and index["refs"]
    return index


def _available_envelope(*, selection=None):
    body = {
        "schema": BODY_SCHEMA,
        "selection": dict(SELECTED if selection is None else selection),
        "availability": "AVAILABLE",
        "reason_codes": [],
        "index": _genuine_index(),
        "source_observation": {
            "schema": wire.OBSERVATION_SCHEMA, "state": "SAME",
            "selection": dict(SELECTED if selection is None else selection),
            "control_room": {
                "instance_before": "instance-a", "instance_after": "instance-a",
                "publication_before": 1, "publication_after": 1,
                "document_digest": "1" * 64, "source_validity_digest": "2" * 64,
                "cache_currentness_digest": "3" * 64,
            },
            "runtime": {"schema": "mastermind.runtime_read_observation.v1",
                        "state": "SAME", "source_identity": "a" * 32,
                        "before": 1, "after": 1},
        },
        "catalogue": {"generated_at": "2026-01-01T00:00:00Z", "freshness": "STALE"},
    }
    return {"ok": True, "result": body}


def test_v2_contract_pins_the_reference_operation():
    frame = _reference_frame()
    assert wire.validate_v2_frame(copy.deepcopy(frame)) == frame
    assert wire.v2_selection(dict(SELECTED), "result_references") == dict(SELECTED)
    for deviated in (
        {**SELECTED, "job_id": "JOB-1"},
        {**SELECTED, "attempt_id": ATTEMPT_ID},
        {**SELECTED, "result_envelope_digest": "0" * 64},
        {"work_ref": SELECTED["work_ref"]},
        {"root_job_id": SELECTED["root_job_id"]},
        {},
    ):
        with pytest.raises(ValueError):
            wire.v2_selection(deviated, "result_references")
    assert wire.response_ceiling_for("result_references") == wire.MAX_RESULT_RESPONSE_BYTES


def test_reference_route_is_get_only_at_the_exact_fixed_path(rsa_key):
    test_client, fake = _make_app(rsa_key, client=_FakeWorkspaceClient(
        envelope=references.unavailable(SELECTED, "SOURCE_UNAVAILABLE")))
    headers = {"Authorization": "Bearer " + _workspace_token(rsa_key)}
    assert test_client.post(ROUTE, headers=headers).status_code == 405
    assert test_client.head(ROUTE, headers=headers).status_code == 405
    assert test_client.get(ROUTE + "/", headers=headers).status_code == 404
    assert test_client.get("/workspace%2Fresult-references/current",
                           headers=headers).status_code == 400
    assert test_client.get("//workspace/result-references/current",
                           headers=headers).status_code in (400, 404)
    assert test_client.get("/workspace/result-references/current/other",
                           headers=headers).status_code == 404
    assert fake.calls == []


@pytest.mark.parametrize("query", [
    "",
    "?work_ref=WS:AA1",
    "?root_job_id=JOB-1",
    "?work_ref=WS:AA1&root_job_id=JOB-1&extra=x",
    "?work_ref=WS:AA1&root_job_id=JOB-1&root_job_id=JOB-1",
    "?work_ref=WS+AA1&root_job_id=JOB-1",
    "?%77ork_ref=WS:AA1&root_job_id=JOB-1",
    "?work_ref=WS:AA1&root_job_id=JOB-1;",
    "?work_ref=../private&root_job_id=JOB-1",
    "?work_ref=WS:AA1&root_job_id=JOB-x",
    "?work_ref=&root_job_id=JOB-1",
])
def test_deviated_queries_refuse_before_the_owner(rsa_key, query):
    test_client, fake = _make_app(rsa_key)
    response = test_client.get(
        ROUTE + query, headers={"Authorization": "Bearer " + _workspace_token(rsa_key)})
    assert response.status_code == 400
    assert fake.calls == []


def test_unauthenticated_requests_never_reach_the_owner(rsa_key):
    test_client, fake = _make_app(rsa_key, client=_FakeWorkspaceClient(envelope=_available_envelope()))
    for headers in ({}, {"Authorization": "Bearer garbled"}):
        response = test_client.get(ROUTE + "?work_ref=WS:AA1&root_job_id=JOB-1",
                                   headers=headers)
        assert response.status_code in (401, 403)
    assert fake.calls == []


def test_signed_reference_read_sends_the_closed_frame_and_body(rsa_key):
    envelope = _available_envelope()
    test_client, fake = _make_app(rsa_key, client=_FakeWorkspaceClient(envelope=envelope))
    response = test_client.get(ROUTE, params=dict(SELECTED),
                               headers={"Authorization": "Bearer " + _workspace_token(rsa_key)})
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == envelope["result"]
    assert len(fake.calls) == 1
    sent = fake.calls[0]
    assert wire.validate_v2_frame(sent) == sent
    assert sent["operation"] == "result_references"
    assert sent["selection"] == dict(SELECTED)
    assert sent["principal"]["resource"] == wire.RESOURCE
    assert sent["principal"]["scopes"] == [wire.SCOPE]


def test_selection_mismatch_between_query_and_body_refuses(rsa_key):
    envelope = _available_envelope(selection={"work_ref": "WS:AA1", "root_job_id": "JOB-999"})
    test_client, fake = _make_app(rsa_key, client=_FakeWorkspaceClient(envelope=envelope))
    response = test_client.get(ROUTE, params=dict(SELECTED),
                               headers={"Authorization": "Bearer " + _workspace_token(rsa_key)})
    assert response.status_code == 503
    assert len(fake.calls) == 1
    assert "JOB-999" not in response.text


@pytest.mark.parametrize("mutation", [
    "extra_body_key", "wrong_schema", "missing_catalogue_key",
    "extra_catalogue_key", "bad_availability", "index_foreign_root",
])
def test_edge_closed_validator_refuses_mutated_reference_bodies(mutation):
    envelope = _available_envelope()
    body = envelope["result"]
    if mutation == "extra_body_key":
        body["mission_current"] = True
    elif mutation == "wrong_schema":
        body["schema"] = wire.RESULT_BODY_SCHEMA
    elif mutation == "missing_catalogue_key":
        body["catalogue"].pop("freshness")
    elif mutation == "extra_catalogue_key":
        body["catalogue"]["mission_current"] = False
    elif mutation == "bad_availability":
        body["availability"] = "PARTIAL"
    else:
        body["index"]["root_job_id"] = "JOB-foreign"
    response = _result_references_envelope_response(envelope)
    assert response.status_code == 503
    assert response.headers["cache-control"] == "no-store"
    assert b"mission_current" not in response.body


def test_unavailable_projection_is_typed_503_and_keeps_no_content(rsa_key):
    envelope = references.unavailable(SELECTED, "SOURCE_CHANGED")
    test_client, fake = _make_app(rsa_key, client=_FakeWorkspaceClient(envelope=envelope))
    response = test_client.get(ROUTE, params=dict(SELECTED),
                               headers={"Authorization": "Bearer " + _workspace_token(rsa_key)})
    assert response.status_code == 503
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == envelope["result"]
    body = response.json()
    assert body["availability"] == "UNAVAILABLE"
    assert body["index"] is None
    assert body["catalogue"] == {"generated_at": None, "freshness": "UNKNOWN"}
    assert body["source_observation"]["control_room"] is None
    assert body["source_observation"]["runtime"] is None
    assert "JOB-2" not in response.text


def test_over_budget_response_is_refused_never_truncated(rsa_key):
    envelope = _available_envelope()
    index = envelope["result"]["index"]
    index["absent_job_ids"] = ["JOB-%d" % n for n in range(1, 4000)]
    assert len(wire.canonical(envelope)) > wire.MAX_RESULT_RESPONSE_BYTES
    test_client, fake = _make_app(rsa_key, client=_FakeWorkspaceClient(envelope=envelope))
    response = test_client.get(ROUTE, params=dict(SELECTED),
                               headers={"Authorization": "Bearer " + _workspace_token(rsa_key)})
    assert response.status_code == 503
    assert response.headers["cache-control"] == "no-store"
    assert b"JOB-3999" not in response.content


def test_owner_permission_revocation_after_read_refuses(rsa_key):
    permitted = [True, False]

    def authorize(_principal):
        return permitted.pop(0)

    test_client, fake = _make_app(rsa_key, authorize=authorize,
                                  client=_FakeWorkspaceClient(envelope=_available_envelope()))
    response = test_client.get(ROUTE, params=dict(SELECTED),
                               headers={"Authorization": "Bearer " + _workspace_token(rsa_key)})
    assert response.status_code == 403
    assert len(fake.calls) == 1


class _RecordingProducer:
    """Substitute for the producer delegation seam inside the read service."""

    def __init__(self, behavior):
        self.behavior = behavior
        self.frames = []

    def read_result_references(self, owner, frame):
        self.frames.append((owner, frame))
        return self.behavior(frame)


def _wired_service(monkeypatch, behavior):
    from control_plane.workspace_read_service import WorkspaceReadService

    producer = _RecordingProducer(behavior)
    monkeypatch.setattr(references, "read_result_references",
                        producer.read_result_references, raising=True)
    service = WorkspaceReadService(
        cache=object(), runtime=object(), authorize=lambda _principal: True,
        armed={}, runtime_identity={},
    )
    return service, producer


def test_read_service_delegates_the_reference_operation(monkeypatch):
    envelope = _available_envelope()
    service, producer = _wired_service(monkeypatch, lambda _frame: envelope)
    result = asyncio.run(service.handle_frame(_reference_frame()))
    assert result is envelope
    owner, frame = producer.frames[0]
    assert owner is service and frame["operation"] == "result_references"


def test_unexpected_producer_failure_is_a_typed_unavailable_body(monkeypatch):
    service, _ = _wired_service(
        monkeypatch, lambda _frame: (_ for _ in ()).throw(RuntimeError("producer failed")))
    result = asyncio.run(service.handle_frame(_reference_frame()))
    assert result == references.unavailable(SELECTED, "SOURCE_UNAVAILABLE")
    assert result["result"]["index"] is None


def test_missing_programme_stays_a_typed_404(monkeypatch):
    service, _ = _wired_service(
        monkeypatch, lambda _frame: (_ for _ in ()).throw(LookupError("no programme")))
    result = asyncio.run(service.handle_frame(_reference_frame()))
    assert result == {"ok": False, "status": 404,
                      "error": {"code": "selection_not_found",
                                "message": "workspace read refused"}}


class _Mount:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def __call__(self, scope, receive, send):
        self.calls.append(scope["path"])
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"owned mount"})


def test_route_mounts_through_the_executive_mcp_transport_allowlist(rsa_key, tmp_path):
    pytest.importorskip("mcp")
    import test_executive_mcp_app_composition as existing
    import test_mastermind_executive_app_asgi as mcp_fixture
    from integrations.executive_mcp import server as mcp_server

    mastermind = tmp_path / "mastermind"
    macro = tmp_path / "macro"
    mcp_fixture._git_repo(mastermind)
    (macro / "scripts").mkdir(parents=True)
    (macro / "scripts" / "agentos.py").write_text("")
    (macro / "agentos").mkdir()
    (macro / "agentos" / ".keep").write_text("")
    mcp_fixture._git_repo(macro)
    settings = mcp_fixture._real_app_settings(
        rsa_key, mastermind_root=mastermind, macro_root=macro,
        ceo_ingress_socket_path=tmp_path / "ceo-ingress.sock")
    workspace = _Mount()
    app = mcp_server.build_executive_mcp_app(settings, audit_sink=existing.Sink(),
                                             workspace_app=workspace)

    async def check():
        async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="https://mcp.mastermind-x.com") as client:
            response = await client.get(
                "/workspace/result-references/current?work_ref=WS:AA1&root_job_id=JOB-1")
            assert response.status_code == 200, response.text
            for method in ("post", "put", "delete"):
                response = await client.request(method, ROUTE + "?work_ref=WS:AA1&root_job_id=JOB-1")
                assert response.status_code == 404, (method, response.status_code)
            for url in (ROUTE + "/", "/workspace%2Fresult-references/current"):
                response = await client.get(url)
                assert response.status_code == 404, (url, response.status_code)
    asyncio.run(check())
    assert workspace.calls == [ROUTE]


def test_public_edge_allowlist_and_caddy_template_carry_the_exact_path():
    from ops.executive_os.os_public_edge import GET_ROUTES, POST_ROUTES

    assert GET_ROUTES.count(ROUTE) == 1
    assert GET_ROUTES.index(ROUTE) == GET_ROUTES.index("/workspace/result/current") + 1
    assert not any("result-references" in route for route in POST_ROUTES)
    names = ["index.html", "assets/index-a.css", "assets/index-b.js"]
    from integrations.mastermind_executive_app.os_assets import os_asset_mimes
    manifest = {"schema": "mastermind.os_assets.v1", "files": [
        {"path": name, "byte_count": 1, "sha256": "a" * 64, "mime": mime}
        for name, mime in os_asset_mimes(names).items()
    ]}
    from ops.executive_os.os_public_edge import render
    config = render(manifest, 49152)
    assert config.count(ROUTE) == 1
    assert "/workspace/result/current /workspace/result-references/current" in config
    assert "/workspace/result-references/current /workspace/plan/current" in config


def test_producer_failure_still_rechecks_permission_before_typed_unavailable(monkeypatch):
    permitted = [True]
    def fail_after_revocation(_frame):
        permitted[0] = False
        raise RuntimeError("producer failed after policy changed")
    service, producer = _wired_service(monkeypatch, fail_after_revocation)
    service.authorize = lambda _principal: permitted[0]
    result = asyncio.run(service.handle_frame(_reference_frame()))
    assert result["ok"] is False and result["status"] == 403
    assert "result" not in result
    assert len(producer.frames) == 1


def test_signed_http_joins_the_real_reference_producer_and_finalized_runtime(tmp_path, rsa_key):
    """Actual A1 edge + service + cache/producer; Runtime data remains a fixture."""
    from tests.test_workspace_result_references import (
        SELECTION as producer_selection, _acquire, owner,
    )
    from tests.test_workspace_read_service import STAMP, cache_fixture
    from scripts import chairman_control_room as ccr

    owners, clock, cache = cache_fixture(tmp_path)
    doc = owners[0].state_cache["doc"]
    doc["sources"] = {"agent_os_state_generated_at": "2026-09-20T00:00:00Z"}
    row = doc["autonomy"]["responsibilities"][0]
    row["freshness"] = "stale"
    row["validity"]["card"]["valid_for_ms"] = None
    with owners[0].state_lock:
        ccr._publish_source_validity(owners[0], doc, tuple(clock), tuple(clock))
    service = owner(cache, _acquire())
    calls = []
    class FixtureTransport:
        async def request(self, frame):
            calls.append(frame)
            return await service.handle_frame(frame)
    client, _ = _make_app(rsa_key, client=FixtureTransport())
    response = client.get(ROUTE, params=producer_selection,
                          headers={"Authorization": "Bearer " + _workspace_token(rsa_key)})
    assert response.status_code == 200
    body = response.json()
    assert body["availability"] == "AVAILABLE"
    assert body["catalogue"] == {"generated_at": "2026-09-20T00:00:00Z", "freshness": "STALE"}
    assert body["source_observation"]["runtime"]["state"] == "SAME"
    assert body["index"]["refs"][0]["job_id"] == "JOB-001"
    assert body["selection"] == producer_selection
    assert calls[0]["operation"] == "result_references"
    assert set(calls[0]["selection"]) == {"work_ref", "root_job_id"}
    assert "mission_current" not in body and doc["generated_at"] == STAMP
