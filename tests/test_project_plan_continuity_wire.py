"""Closed v2 body and actual producer fixture; existing v1 remains valid."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

import pytest

from common.project_plan_continuity_contract import compose_body_v2, validate_continuity
from common.workspace_project_plan_contract import validate_body
from control_plane.workspace_project_plan import project_workstream_plan


FIXTURE = json.loads((Path(__file__).parent.parent / "app/mastermind_os/src/fixtures/project-plan-continuity-owner.json").read_bytes())
WORK = "WS:PLAN-TEST"
AUTHORED_BYTES = b"# Synthetic authored record bytes\n"


@pytest.mark.parametrize("name", list(FIXTURE["cases"]))
def test_actual_owner_fixture_survives_closed_transport_validation(name):
    value = deepcopy(FIXTURE["cases"][name])
    assert validate_continuity(value, WORK) == value
    returned = validate_continuity(value, WORK)
    returned["proposals"]["coverage"] = "mutated"
    assert value["proposals"]["coverage"] == "CAPTURED_ASSOCIATIONS_ONLY"


@pytest.mark.parametrize("change", [
    lambda v: v.update({"authority": True}),
    lambda v: v.update({"work_ref": "WS:OTHER"}),
    lambda v: v["adoption"]["adoption"].update({"granted": True}),
    lambda v: v["adoption"].update({"content": "Different content"}),
    lambda v: v["adoption"]["decision_source"].update({"path": "private.md"}),
    lambda v: v["proposals"]["items"][0]["comparison"].update({"identical": True}),
    lambda v: v["proposals"]["items"][0]["comparison"].update({"diff": "fake diff"}),
    lambda v: v["proposals"]["items"][0]["comparison"].update({"added_lines": True}),
    lambda v: v["proposals"]["items"][0]["comparison"].update({"identical": 0}),
    lambda v: v["proposals"]["items"][0].update({"comparison_basis": "RECORDED_SOURCE"}),
    lambda v: v["proposals"]["items"][0].update({"base_adoption": None}),
])
def test_tampered_nested_projection_is_refused_without_echo(change):
    value = deepcopy(FIXTURE["cases"]["available_pending"])
    change(value)
    with pytest.raises(ValueError, match="^invalid_project_plan_continuity$"):
        validate_continuity(value, WORK)


def base_plan():
    source = {"repository": "mastermindx-market-intelligence/macro", "commit": "a" * 40,
              "path": "agentos/workstreams/WS-PLAN-TEST.md", "content_sha256": hashlib.sha256(AUTHORED_BYTES).hexdigest()}
    return project_workstream_plan({"key": "PLAN-TEST", "title": "Authored record",
        "objective": "Real available objective.", "status": "active", "owner": "ceo",
        "next_action": "Read it", "waves": []}, work_ref=WORK, source=source)


def test_v2_summary_is_derived_from_actual_decision_and_preserves_authored_content():
    base = base_plan()
    continuity = FIXTURE["cases"]["available_pending"]
    body = compose_body_v2(base, continuity, authored_bytes=AUTHORED_BYTES)
    assert body["schema"] == "mastermind.workspace_project_plan.v2"
    assert body["plan"]["objective"] == base["plan"]["objective"]
    assert body["plan"]["adoption"]["state"] == "AVAILABLE"
    assert body["plan"]["adoption"]["matches_authored_record"] is False
    assert validate_body(body) == body
    assert validate_body(base) == base
    changed = deepcopy(body)
    changed["plan"]["adoption"]["matches_authored_record"] = True
    with pytest.raises(ValueError):
        validate_body(changed)
    changed = deepcopy(body)
    changed["source"]["commit"] = "b" * 40
    with pytest.raises(ValueError):
        validate_body(changed)


def test_v2_declared_missing_source_does_not_become_available_adoption():
    body = compose_body_v2(base_plan(), FIXTURE["cases"]["declared_source_unavailable"], authored_bytes=AUTHORED_BYTES)
    assert body["plan"]["adoption"] == {"state": "UNAVAILABLE", "reason": "SOURCE_UNAVAILABLE"}
    assert body["plan"]["objective"] == "Real available objective."
