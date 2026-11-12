"""Existing native briefing + authenticated HTTP facade, synthetic owners only."""
import asyncio
from datetime import datetime, timezone
import json

import httpx
import pytest

from integrations.hermes_leadership import LeadershipReader
from integrations.hermes_leadership.native import native_handler
from integrations.secretary_team_access.client import SecretaryAccessClient
from tests.test_paperclip_connections import snapshot
from tests.test_secretary_team_mission import mission_body, _selection, _STAMP_EPOCH
from tests.test_workspace_result_service import result_owner


def setup(mission_body, *, enabled=True, company_status=200, revoke=False, malformed_refusal=False):
    body, owner = mission_body
    selection, calls, current = _selection(owner), [], [True]
    company = snapshot()
    company["observedAt"] = datetime.fromtimestamp(_STAMP_EPOCH + 20, timezone.utc).isoformat()
    company["projectBindings"][0]["workRef"] = selection["work_ref"]

    async def handle(request):
        calls.append(request)
        if request.url.path == "/workspace/mission/v3/current": return httpx.Response(200, json=body)
        assert request.url.path == "/workspace/company/current" and dict(request.url.params) == {"view": "overview"}
        assert request.headers["authorization"] == "Bearer synthetic-host-token"
        if revoke: current[0] = False
        if malformed_refusal: return httpx.Response(company_status, content=b"not-json")
        return httpx.Response(company_status, json=company)

    transport = httpx.AsyncClient(base_url="https://owner.test", transport=httpx.MockTransport(handle),
        follow_redirects=False, headers={"authorization": "Bearer synthetic-host-token"})
    access = SecretaryAccessClient(**selection, workspace=transport, clock=lambda: _STAMP_EPOCH + 30)
    reader = LeadershipReader(charter_key="secretary", session_id="native-a", access=access,
        currentness_guard=lambda: current[0], include_company_context=enabled)
    return transport, reader, access, calls


def test_original_native_tool_gets_bounded_company_context(mission_body):
    async def exercise():
        transport, reader, _, calls = setup(mission_body)
        async with transport:
            result = json.loads(await native_handler(reader)({}, session_id="native-a"))
        assert result["state"] == "AVAILABLE" and result["company_context"]["state"] == "AVAILABLE"
        assert result["company_context"]["newWorkAuthorized"] is False
        assert len(calls) == 2 and all(request.method == "GET" for request in calls)
        assert result["admitted"] is result["dispatched"] is result["replay_authorized"] is False
        assert result["continuity"]["missing_fields"] == ["objective", "done_when", "next_action", "unresolved_effects"]
    asyncio.run(exercise())


def test_default_keeps_original_one_read_and_no_new_route(mission_body):
    async def exercise():
        transport, reader, _, calls = setup(mission_body, enabled=False)
        async with transport: result = await reader.read(session_id="native-a")
        assert result["state"] == "AVAILABLE" and "company_context" not in result and len(calls) == 1
    asyncio.run(exercise())


@pytest.mark.parametrize("kwargs", [{"company_status": 403}, {"company_status": 401, "malformed_refusal": True}, {"revoke": True}])
def test_refusal_or_revocation_discards_prior_mission_and_org_facts(mission_body, kwargs):
    async def exercise():
        transport, reader, _, _ = setup(mission_body, **kwargs)
        async with transport: result = await reader.read(session_id="native-a")
        assert result["state"] == "REFUSED"
        assert not {"mission", "organization_context", "company_context"} & result.keys()
    asyncio.run(exercise())


def test_non_permission_failure_preserves_current_mission_with_explicit_unavailability(mission_body):
    async def exercise():
        transport, reader, _, _ = setup(mission_body, company_status=503)
        async with transport: result = await reader.read(session_id="native-a")
        assert result["state"] == "AVAILABLE" and result["mission"]
        assert result["company_context"]["state"] == "UNAVAILABLE"
    asyncio.run(exercise())


def test_model_cannot_select_company_project_or_credentials(mission_body):
    async def exercise():
        transport, reader, access, calls = setup(mission_body)
        async with transport:
            with pytest.raises(TypeError): await access.read_company_context(company_id="other")
            result = json.loads(await native_handler(reader)({"companyId": "other"}, session_id="native-a"))
        assert result["state"] == "REFUSED" and calls == []
    asyncio.run(exercise())
