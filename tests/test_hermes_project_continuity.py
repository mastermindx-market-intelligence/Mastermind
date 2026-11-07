"""Opt-in continuity through real existing owner contracts and native handler.

Synthetic HTTP transports only. No enrollment, credentials, browser access,
service activation, runtime admission or installed-role proof is inferred.
"""
from __future__ import annotations

import asyncio
import copy
import hashlib
import json

import httpx
import pytest

from common import workspace_project_plan_contract as wire
from common.project_plan_continuity_contract import compose_body_v2
from control_plane.workspace_project_plan import project_workstream_plan
from integrations.hermes_leadership import LeadershipReader
from integrations.hermes_leadership.native import native_handler
from integrations.secretary_team_access.client import SecretaryAccessClient
from tests.test_hermes_leadership import access_for, reader_for
from tests.test_secretary_team_mission import mission_body, _selection, _STAMP_EPOCH
from tests.test_workspace_result_service import result_owner
from tests.test_workspace_read_app import rsa_key, _make_app, _workspace_token

PLAN_ROUTE = "/workspace/project-plan/current"
MISSION_ROUTE = "/workspace/mission/v3/current"
NOW = _STAMP_EPOCH + 30
AUTHORED = b"synthetic authored record, not a transcript"


def plan_for(owner, *, objective="Canonical project objective",
             next_action="Reconcile the original effect before continuing"):
    work_ref = _selection(owner)["work_ref"]
    return project_workstream_plan({
        "key": work_ref[3:], "title": "Canonical project",
        "objective": objective, "status": "active", "owner": "secretary",
        "next_action": next_action,
        "waves": [{"id": "W1", "title": "First wave", "status": "in_progress"}],
    }, work_ref=work_ref, source={
        "repository": wire.CANONICAL_REPOSITORY, "commit": "a" * 40,
        "path": "agentos/workstreams/WS-" + work_ref[3:] + ".md",
        "content_sha256": hashlib.sha256(AUTHORED).hexdigest(),
    })


def adopted_plan(owner, *, content="PRIVATE_ADOPTION_SENTINEL", **fields):
    base = plan_for(owner, **fields)
    work_ref = base["selection"]["work_ref"]
    continuity = {
        "schema": "mastermind.project_plan_continuity.v1", "work_ref": work_ref,
        "adoption": {
            "state": "AVAILABLE", "decision_ref": "DEC:CURRENT",
            "decision_source": {
                "repository": wire.CANONICAL_REPOSITORY,
                "path": "agentos/decisions/DEC-CURRENT.md", "commit": "a" * 40,
                "content_sha256": "d" * 64,
            },
            "adoption": {
                "schema": "agentos.project_plan_adoption.v1", "work_ref": work_ref,
                "adopted_source": {
                    "repository": "mastermindx-market-intelligence/Mastermind",
                    "path": "docs/plans/adopted.md", "commit": "b" * 40,
                    "content_sha256": hashlib.sha256(content.encode()).hexdigest(),
                },
                "predecessor": None, "proposal_source": None,
                "display_revision": "Original adopted plan",
            },
            "decided_by": "synthetic-chairman", "decided_at": "2026-11-06",
            "content": content,
        },
        "proposals": {"state": "AVAILABLE", "items": [],
                      "coverage": "CAPTURED_ASSOCIATIONS_ONLY"},
    }
    return compose_body_v2(base, continuity, authored_bytes=AUTHORED)


def setup_read(mission_body, *, plan=None, plan_handler=None, clock=None, guard=None):
    body, owner = mission_body
    selected_plan = plan if plan is not None else plan_for(owner)
    calls = []

    async def handle(request):
        calls.append(request)
        if request.url.path == MISSION_ROUTE:
            return httpx.Response(200, json=body)
        assert request.url.path == PLAN_ROUTE
        if plan_handler:
            reply = plan_handler(request)
            return await reply if asyncio.iscoroutine(reply) else reply
        return httpx.Response(200, json=selected_plan)

    transport = httpx.AsyncClient(base_url="https://owner.test",
        transport=httpx.MockTransport(handle), follow_redirects=False,
        headers={"authorization": "Bearer synthetic-host-token"})
    access = SecretaryAccessClient(**_selection(owner), workspace=transport,
                                   clock=clock or (lambda: NOW))
    reader = LeadershipReader(charter_key="secretary", session_id="native-a",
        access=access, currentness_guard=guard or (lambda: True),
        include_project_continuity=True)
    return access, transport, reader, calls


def test_client_uses_fixed_plan_route_and_canonical_validator(mission_body):
    body, owner = mission_body
    plan = plan_for(owner)

    async def exercise():
        access, transport, calls = access_for(plan, owner)
        async with transport:
            result = await access.read_project_plan()
            assert result == wire.validate_body(plan)
            assert result is not plan
            with pytest.raises(TypeError):
                await access.read_project_plan(work_ref="WS:OTHER")
        assert len(calls) == 1 and calls[0].method == "GET"
        assert calls[0].url.path == PLAN_ROUTE
        assert dict(calls[0].url.params) == {"work_ref": _selection(owner)["work_ref"]}
    asyncio.run(exercise())


def test_default_native_brief_remains_one_mission_read(mission_body):
    body, owner = mission_body

    async def exercise():
        access, transport, calls = access_for(body, owner)
        async with transport:
            result = json.loads(await native_handler(reader_for(access))({}, session_id="native-a"))
        assert result["state"] == "AVAILABLE"
        assert "project_plan" not in result["continuity"]
        assert len(calls) == 1 and calls[0].url.path == MISSION_ROUTE
    asyncio.run(exercise())


@pytest.mark.parametrize("flag", [None, 0, 1, "true", [], {}])
def test_opt_in_requires_exact_boolean(mission_body, flag):
    body, owner = mission_body

    async def exercise():
        access, transport, _ = access_for(body, owner)
        async with transport:
            with pytest.raises(ValueError, match="invalid_project_continuity_binding"):
                LeadershipReader(charter_key="secretary", session_id="native-a",
                    access=access, currentness_guard=lambda: True,
                    include_project_continuity=flag)
    asyncio.run(exercise())


def test_existing_native_handler_returns_separate_authored_continuity(mission_body):
    async def exercise():
        _, transport, reader, calls = setup_read(mission_body)
        async with transport:
            result = json.loads(await native_handler(reader)({}, session_id="native-a"))
        assert result["state"] == "AVAILABLE"
        ctx = result["continuity"]["project_plan"]
        assert ctx["state"] == "AVAILABLE"
        assert ctx["objective"] == "Canonical project objective"
        assert ctx["next_action"] == "Reconcile the original effect before continuing"
        assert ctx["content_basis"] == "AUTHORED_WORKSTREAM_RECORD"
        assert ctx["snapshot_relation"] == "SEPARATE_READS_NOT_ATOMIC"
        assert ctx["source_freshness"] == "NOT_REPORTED_BY_OWNER"
        assert ctx["root_job_binding"] == "NOT_ESTABLISHED"
        assert ctx["adoption"] == {"state": "UNAVAILABLE", "reason": "NOT_DECLARED"}
        assert ctx["source"]["commit"] == "a" * 40
        assert ctx["field_coverage"]["objective"]["state"] == "RETURNED"
        assert ctx["wave_coverage"] == {"total": 1, "returned": 1, "omitted": 0}
        assert ctx["waves"][0]["id"] == "W1"
        assert result["continuity"]["missing_fields"] == ["done_when", "unresolved_effects"]
        assert result["continuity"]["new_work_authorized"] is False
        assert result["continuity"]["next_action_is_recommendation"] is True
        assert not any(result[k] for k in ("admitted", "dispatched", "replay_authorized", "reasoning_wake"))
        assert [r.url.path for r in calls] == [MISSION_ROUTE, PLAN_ROUTE]
        assert "synthetic-host-token" not in json.dumps(result)
        assert len(json.dumps(result, ensure_ascii=False, separators=(",", ":")).encode()) <= 24576
    asyncio.run(exercise())


@pytest.mark.parametrize("variant", ["v1-null", "v2-mismatch", "v2-matching"])
def test_adoption_and_missingness_never_inferred(mission_body, variant):
    _, owner = mission_body
    if variant == "v1-null":
        plan = plan_for(owner, next_action=None)
    else:
        content = AUTHORED.decode() if variant == "v2-matching" else "PRIVATE_ADOPTION_SENTINEL"
        plan = adopted_plan(owner, content=content)

    async def exercise():
        _, transport, reader, _ = setup_read(mission_body, plan=plan)
        async with transport:
            result = await reader.read(session_id="native-a")
        ctx = result["continuity"]["project_plan"]
        if variant == "v1-null":
            assert ctx["next_action"] is None
            assert "next_action" in result["continuity"]["missing_fields"]
            assert ctx["field_coverage"]["next_action"]["state"] == "NOT_SUPPLIED_BY_OWNER"
        else:
            assert ctx["adoption"]["state"] == "AVAILABLE"
            assert ctx["adoption"]["matches_authored_record"] is (variant == "v2-matching")
        assert "PRIVATE_ADOPTION_SENTINEL" not in json.dumps(result)
        assert AUTHORED.decode() not in json.dumps(result)
        assert result["continuity"]["new_work_authorized"] is False
    asyncio.run(exercise())


@pytest.mark.parametrize("variant", ["wrong-selection", "extra-field", "invalid-adoption",
                                    "duplicate-json", "5xx", "redirect", "202", "exception"])
def test_invalid_plan_never_leaks_or_substitutes_cached_facts(mission_body, variant):
    _, owner = mission_body
    plan = adopted_plan(owner)
    if variant == "wrong-selection": plan["selection"]["work_ref"] = "WS:FOREIGN"
    if variant == "extra-field": plan["private"] = "PRIVATE_REJECTED_SENTINEL"
    if variant == "invalid-adoption": plan["continuity"]["adoption"]["content"] = "PRIVATE_REJECTED_SENTINEL"

    def handler(request):
        if variant == "exception": raise RuntimeError("PRIVATE_REJECTED_SENTINEL")
        if variant == "duplicate-json":
            return httpx.Response(200, content=b'{"schema":"one","schema":"PRIVATE_REJECTED_SENTINEL"}')
        status = {"5xx": 503, "redirect": 302, "202": 202}.get(variant, 200)
        return httpx.Response(status, json=plan)

    async def exercise():
        _, transport, reader, calls = setup_read(mission_body, plan_handler=handler)
        async with transport:
            result = await reader.read(session_id="native-a")
        assert result["state"] == "AVAILABLE"
        assert result["continuity"]["project_plan"]["state"] == "UNAVAILABLE"
        assert result["continuity"]["missing_fields"] == ["objective", "done_when", "next_action", "unresolved_effects"]
        assert "PRIVATE_REJECTED_SENTINEL" not in json.dumps(result)
        assert "PRIVATE_ADOPTION_SENTINEL" not in json.dumps(result)
        assert len(calls) == 2
    asyncio.run(exercise())


class InterruptedBody(httpx.AsyncByteStream):
    async def __aiter__(self):
        yield b"{"
        raise httpx.ReadError("PRIVATE_TRANSPORT_SENTINEL")


@pytest.mark.parametrize("status", [401, 403])
@pytest.mark.parametrize("body_kind", ["json", "empty", "malformed", "oversized", "interrupted"])
def test_observed_auth_refusal_discards_earlier_mission_even_with_bad_body(mission_body, status, body_kind):
    def handler(request):
        if body_kind == "interrupted":
            return httpx.Response(status, stream=InterruptedBody())
        raw = {
            "json": b'{"error":{"code":"access_denied"}}',
            "empty": b"", "malformed": b"PRIVATE_REFUSAL_SENTINEL",
            "oversized": b"x" * (wire.MAX_RESPONSE_BYTES + 1),
        }[body_kind]
        return httpx.Response(status, content=raw)

    async def exercise():
        _, transport, reader, calls = setup_read(mission_body, plan_handler=handler)
        async with transport:
            result = await reader.read(session_id="native-a")
        assert result["state"] == "REFUSED"
        assert not {"mission", "continuity", "organization_context", "charter"} & result.keys()
        assert "PRIVATE_" not in json.dumps(result)
        assert len(calls) == 2
    asyncio.run(exercise())


@pytest.mark.parametrize("change", ["guard", "selection", "client", "clock"])
def test_binding_drift_during_plan_discards_everything(mission_body, change):
    current = [True]
    holder = {}

    def handler(request):
        access = holder["access"]
        if change == "guard": current[0] = False
        if change == "selection": access.selection["work_ref"] = "WS:FOREIGN"
        if change == "client": access._workspace = object()
        if change == "clock": access._clock = lambda: NOW
        return httpx.Response(200, json=plan_for(mission_body[1]))

    async def exercise():
        access, transport, reader, calls = setup_read(mission_body,
            plan_handler=handler, guard=lambda: current[0])
        holder["access"] = access
        async with transport:
            result = await reader.read(session_id="native-a")
        assert result["state"] == "REFUSED" and result["reason"] == "binding_not_current"
        assert "mission" not in result and len(calls) == 2
    asyncio.run(exercise())


@pytest.mark.parametrize("new_clock", [NOW + 1000, NOW - 1, float("nan"), float("inf")])
def test_mission_freshness_rechecked_after_plan(mission_body, new_clock):
    clock = [NOW]

    def handler(request):
        clock[0] = new_clock
        return httpx.Response(200, json=plan_for(mission_body[1]))

    async def exercise():
        _, transport, reader, _ = setup_read(mission_body,
            plan_handler=handler, clock=lambda: clock[0])
        async with transport:
            result = await reader.read(session_id="native-a")
        assert result["state"] == "UNAVAILABLE"
        assert result["reason"] == "source_not_fresh" and "mission" not in result
    asyncio.run(exercise())


def test_large_valid_v2_uses_wire_cap_but_omits_large_authored_fields(mission_body):
    _, owner = mission_body
    plan = adopted_plan(owner, content="PRIVATE_ADOPTION_SENTINEL" + "x" * 70000,
        objective="漢" * 4000, next_action="\x01" * 4000)
    encoded = json.dumps(plan, ensure_ascii=False, separators=(",", ":")).encode()
    assert 65536 < len(encoded) < wire.MAX_RESPONSE_BYTES
    assert wire.validate_body(plan) == plan

    async def exercise():
        _, transport, reader, calls = setup_read(mission_body, plan=plan)
        async with transport:
            result = await reader.read(session_id="native-a")
        ctx = result["continuity"]["project_plan"]
        assert result["state"] == "AVAILABLE" and ctx["state"] == "AVAILABLE"
        assert ctx["objective"] is None and ctx["next_action"] is None
        assert all(ctx["field_coverage"][f]["state"] == "OMITTED_OVER_BUDGET"
                   for f in ("objective", "next_action"))
        assert result["continuity"]["missing_fields"] == ["objective", "done_when", "next_action", "unresolved_effects"]
        assert "PRIVATE_ADOPTION_SENTINEL" not in json.dumps(result)
        assert len(json.dumps(result, ensure_ascii=False, separators=(",", ":")).encode()) <= 24576
        assert len(calls) == 2
    asyncio.run(exercise())


def test_whole_brief_budget_can_omit_optional_plan_without_losing_current_mission(mission_body, monkeypatch):
    from integrations.hermes_leadership import reader as module

    async def exercise():
        _, transport, reader, _ = setup_read(mission_body)
        async with transport:
            first = await reader.read(session_id="native-a")
            size = len(json.dumps(first, ensure_ascii=False, separators=(",", ":")).encode())
            monkeypatch.setattr(module, "MAX_BYTES", size - 20)
            second = await reader.read(session_id="native-a")
        assert second["state"] == "AVAILABLE"
        assert second["mission"] == first["mission"]
        assert second["continuity"]["project_plan"]["state"] == "UNAVAILABLE"
        assert second["continuity"]["project_plan"]["reason"] == "brief_capacity_exceeded"
        assert len(json.dumps(second, ensure_ascii=False, separators=(",", ":")).encode()) <= size - 20
    asyncio.run(exercise())


def test_no_plan_cache_after_a_successful_read(mission_body):
    count = [0]
    def handler(request):
        count[0] += 1
        return httpx.Response(200 if count[0] == 1 else 503, json=plan_for(mission_body[1]))

    async def exercise():
        _, transport, reader, calls = setup_read(mission_body, plan_handler=handler)
        async with transport:
            first = await reader.read(session_id="native-a")
            second = await reader.read(session_id="native-a")
        assert first["continuity"]["project_plan"]["state"] == "AVAILABLE"
        assert second["continuity"]["project_plan"]["state"] == "UNAVAILABLE"
        assert "Canonical project objective" not in json.dumps(second)
        assert len(calls) == 4
    asyncio.run(exercise())


def test_plan_cancellation_propagates_without_returning_partial_brief(mission_body):
    async def handler(request):
        raise asyncio.CancelledError()
    async def exercise():
        _, transport, reader, calls = setup_read(mission_body, plan_handler=handler)
        async with transport:
            with pytest.raises(asyncio.CancelledError):
                await reader.read(session_id="native-a")
        assert len(calls) == 2
    asyncio.run(exercise())


@pytest.mark.parametrize("revoke", [False, True])
def test_actual_signed_workspace_routes_reach_existing_native_brief(mission_body, rsa_key, revoke):
    body, owner = mission_body
    plan = plan_for(owner)
    frames = []
    allowed = [True]

    class FixtureOwners:
        async def request(self, frame):
            frames.append(frame)
            if frame["operation"] == "mission_v3":
                assert frame["selection"] == _selection(owner)
                return {"ok": True, "result": copy.deepcopy(body)}
            assert frame["operation"] == "project_plan"
            assert frame["selection"] == {"work_ref": _selection(owner)["work_ref"]}
            if revoke: allowed[0] = False
            return {"ok": True, "result": copy.deepcopy(plan)}

    web, _ = _make_app(rsa_key, client=FixtureOwners(), authorize=lambda _: allowed[0])

    async def exercise():
        async with httpx.AsyncClient(base_url="https://workspace.test",
                transport=httpx.ASGITransport(app=web.app), follow_redirects=False,
                headers={"authorization": "Bearer " + _workspace_token(rsa_key)}) as transport:
            access = SecretaryAccessClient(**_selection(owner), workspace=transport, clock=lambda: NOW)
            reader = LeadershipReader(charter_key="meta_ceo", session_id="native-a",
                access=access, currentness_guard=lambda: True, include_project_continuity=True)
            result = json.loads(await native_handler(reader)({}, session_id="native-a"))
        if revoke:
            assert result["state"] == "REFUSED"
            assert "mission" not in result and "continuity" not in result
        else:
            assert result["state"] == "AVAILABLE"
            assert result["continuity"]["project_plan"]["objective"] == plan["plan"]["objective"]
        assert [f["operation"] for f in frames] == ["mission_v3", "project_plan"]
        assert all(f["principal"]["subject_digest"] for f in frames)
        assert result["admitted"] is False and result["dispatched"] is False
    asyncio.run(exercise())


def test_revocation_before_plan_prevents_the_second_request(mission_body):
    checks = [0]
    def guard():
        checks[0] += 1
        return checks[0] < 3

    async def exercise():
        _, transport, reader, calls = setup_read(mission_body, guard=guard)
        async with transport:
            result = await reader.read(session_id="native-a")
        assert result["state"] == "REFUSED" and "mission" not in result
        assert len(calls) == 1 and calls[0].url.path == MISSION_ROUTE
    asyncio.run(exercise())


@pytest.mark.parametrize("change", ["expired", "revoked"])
def test_adviser_meter_after_plan_cannot_release_stale_or_revoked_context(mission_body, change):
    clock, allowed = [NOW], [True]

    async def meter():
        if change == "expired": clock[0] = NOW + 1000
        else: allowed[0] = False
        return {}

    async def exercise():
        access, transport, _, calls = setup_read(mission_body, clock=lambda: clock[0])
        reader = LeadershipReader(charter_key="grok_adviser", session_id="native-a",
            access=access, currentness_guard=lambda: allowed[0],
            include_project_continuity=True, adviser_budget_reader=meter)
        async with transport:
            result = await reader.read(session_id="native-a")
        assert result["state"] == ("REFUSED" if change == "revoked" else "UNAVAILABLE")
        assert not {"mission", "continuity", "adviser_budget"} & result.keys()
        assert len(calls) == 2
    asyncio.run(exercise())


@pytest.mark.parametrize("variant", ["typed-unavailable", "wire-over-budget"])
def test_unavailable_plan_is_explicit_and_bounded(mission_body, variant):
    work_ref = _selection(mission_body[1])["work_ref"]
    def handler(request):
        if variant == "typed-unavailable":
            return httpx.Response(200, json=wire.unavailable(work_ref, "SOURCE_UNAVAILABLE"))
        return httpx.Response(200, content=b" " * (wire.MAX_RESPONSE_BYTES + 1))

    async def exercise():
        _, transport, reader, _ = setup_read(mission_body, plan_handler=handler)
        async with transport:
            result = await reader.read(session_id="native-a")
        assert result["state"] == "AVAILABLE"
        ctx = result["continuity"]["project_plan"]
        assert ctx["state"] == "UNAVAILABLE"
        if variant == "typed-unavailable":
            assert ctx["owner_reason_codes"] == ["SOURCE_UNAVAILABLE"]
    asyncio.run(exercise())
