"""Paperclip-inspired presentation on the original authenticated Mission owner.

No separate agent/goal database, cross-role fanout, runner, or model-supplied
selection. Actual Mission fixtures exercise the owner producer/consumer chain.
"""
import asyncio
import copy
import json

import pytest

from integrations.hermes_leadership.organization import (
    SCHEMA, MAX_BYTES, organization_context,
)
from integrations.hermes_leadership import CHARTER_KEYS
from integrations.hermes_leadership.native import native_handler
from integrations.secretary_team_access.mission import summarize_mission
from tests.test_hermes_leadership import access_for, reader_for
from tests.test_secretary_team_mission import mission_body, _selection, _STAMP_EPOCH
from tests.test_workspace_result_service import result_owner


def summary_for(mission_body):
    body, owner = mission_body
    return summarize_mission(body, selection=_selection(owner), now=_STAMP_EPOCH + 30)


def test_all_charters_have_acyclic_company_path_with_human_root(mission_body):
    summary = summary_for(mission_body)
    for key in CHARTER_KEYS:
        view = organization_context(key, summary)
        assert view["schema"] == SCHEMA
        assert view["organization"]["human_root"]["key"] == "chairman"
        assert view["organization"]["live_roster_state"] == "NOT_OBSERVED"
        assert view["state"] == "SOURCE_LINKED_ADVISORY"
        assert view["admitted"] is False and view["dispatched"] is False
        assert view["reporting_lines_are_authoritative"] is False
        assert view["assignments_are_authoritative"] is False
        seats = view["organization"]["seats"]
        assert {row["key"] for row in seats} == set(CHARTER_KEYS)
        assert all(row["authority_grant"] is False
                   and row["live_enrollment"] == "NOT_OBSERVED" for row in seats)
        chain = view["organization"]["caller"]["advisory_reporting_path"]
        assert chain[0] == "chairman" and chain[-1] == key
        assert len(chain) == len(set(chain))
        assert len(json.dumps(view, ensure_ascii=False).encode()) <= MAX_BYTES


def test_goal_path_is_from_one_original_mission_and_never_claims_execution(mission_body):
    summary = summary_for(mission_body)
    untouched = copy.deepcopy(summary)
    view = organization_context("engineering", summary)
    goal = view["goal_lineage"]
    assert goal["company_goal"]["state"] == "NOT_PROJECTED"
    assert goal["workstream"]["work_ref"] == summary["selection"]["work_ref"]
    assert goal["workstream"]["title"] == summary["program"]["title"]
    assert goal["workstream"]["next_action"] == summary["program"]["next_action"]
    assert goal["execution_root"]["selected_root_job_id"] == summary["selection"]["root_job_id"]
    assert goal["execution_root"]["observed_root_job_id"] == summary["mission"]["root_job_id"]
    assert goal["execution_root"]["role_to_job_assignment"] == "NOT_ESTABLISHED"
    assert goal["evidence"]["result_reference_count"] == summary["coverage"]["result_refs"]["returned_count"]
    assert goal["evidence"]["original_parent_consumption"] == "NOT_ESTABLISHED"
    assert goal["evidence"]["acceptance_state"] == summary["acceptance"]["state"]
    assert goal["evidence"]["product_acceptance"] == "NOT_ESTABLISHED"
    assert goal["source"]["mission_fingerprint"] == summary["fingerprint"]
    assert summary == untouched
    view["organization"]["seats"][0]["title"] = "TAMPERED"
    view["goal_lineage"]["evidence"]["acceptance_reason_codes"].append("TAMPERED")
    assert "TAMPERED" not in json.dumps(organization_context("engineering", summary))


@pytest.mark.parametrize("mutation", [
    lambda s: s.update(schema="unknown"),
    lambda s: s["read_state"].update(state="PARTIAL"),
    lambda s: s.update(details_included=False),
    lambda s: s["freshness"]["local"].update(state="AGED"),
    lambda s: s["coverage"].update(full_fleet=True),
    lambda s: s["program"].update(work_ref="WS:ANOTHER"),
    lambda s: s["mission"].update(root_job_id="JOB-ANOTHER"),
    lambda s: s["acceptance"].update(reason_codes=["SECRET"]*33),
    lambda s: s["coverage"]["result_refs"].update(returned_count=True),
    lambda s: s.update(fingerprint="invalid"),
])
def test_invalid_or_unqualified_owner_summary_refuses(mission_body, mutation):
    summary = summary_for(mission_body)
    mutation(summary)
    with pytest.raises(ValueError):
        organization_context("secretary", summary)


@pytest.mark.parametrize("key", ["external", "", None, False])
def test_unknown_role_rejected_not_implicitly_hired(mission_body, key):
    with pytest.raises(ValueError):
        organization_context(key, summary_for(mission_body))


def test_existing_native_tool_delivers_goal_lineage_with_only_one_owner_read(mission_body):
    body, owner = mission_body

    async def exercise():
        access, transport, calls = access_for(body, owner)
        async with transport:
            reader = reader_for(access, key="secretary")
            handler = native_handler(reader)
            reply = json.loads(await handler({}, session_id="native-a"))
            assert reply["state"] == "AVAILABLE"
            assert reply["organization_context"]["organization"]["caller"]["charter_key"] == "secretary"
            assert reply["organization_context"]["goal_lineage"]["workstream"]["work_ref"] == owner["selection"]["work_ref"]
            assert reply["organization_context"]["goal_lineage"]["evidence"]["original_parent_consumption"] == "NOT_ESTABLISHED"
            assert reply["admitted"] is False and reply["dispatched"] is False
            assert len(calls) == 1
            assert calls[0].url.path == "/workspace/mission/v3/current"
            wrong = json.loads(await handler({}, session_id="other"))
            assert wrong["state"] == "REFUSED" and "organization_context" not in wrong
        assert len(calls) == 1

    asyncio.run(exercise())


def test_revoked_or_unavailable_read_does_not_disclose_the_chart(mission_body):
    body, owner = mission_body
    async def exercise():
        access, transport, calls = access_for(body, owner)
        async with transport:
            denied = reader_for(access, guard=lambda: False)
            result = await denied.read(session_id="native-a")
            assert result["state"] == "REFUSED"
            assert "organization_context" not in result
        assert calls == []
    asyncio.run(exercise())
