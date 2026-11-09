"""Exact current 2055 edge -> accepted project controls, no load or network."""
import copy
import json
from pathlib import Path

import pytest

from ops.executive_os import os_public_edge as edge
from ops.executive_os.os_public_edge_transition import prepare_config, final_config
from tests.test_os_public_edge import manifest

FIXTURE = Path(__file__).parent / "fixtures/project-controls-edge-41297.json"


def predecessor():
    return json.loads(FIXTURE.read_text())["config"]


def method_routes(config):
    found = []
    def visit(node):
        if type(node) is dict:
            if node.get("match") and "method" in node["match"][0]:
                found.append(node)
            for child in node.values(): visit(child)
        elif type(node) is list:
            for child in node: visit(child)
    visit(config)
    return found


def test_only_four_fixed_reads_and_one_instruction_action_extend_the_actual_predecessor():
    old = method_routes(predecessor())
    assert set(old[0]["match"][0]["path"]) == set(edge.PRE_PROJECT_INSTRUCTIONS_GET_ROUTES) | set(edge.asset_routes(manifest()))
    assert old[1]["match"][0]["path"] == list(edge.PRE_INSTRUCTION_ADMISSION_POST_ROUTES)
    assert edge.PRE_MISSION_RESULT_GET_ROUTES == edge.PRE_PROJECT_INSTRUCTIONS_GET_ROUTES + (
        "/workspace/project-instructions/current", "/workspace/instruction-admission/current",
        "/workspace/instruction-admission/operation", "/workspace/project-access/current")
    assert edge.MISSION_RESULT_GET_ROUTES == edge.PRE_MISSION_RESULT_GET_ROUTES + ("/workspace/mission-result/current",)
    assert edge.PRE_MISSION_RESULT_POST_ROUTES == edge.PRE_INSTRUCTION_ADMISSION_POST_ROUTES + ("/workspace/instruction-admission/pause",)
    assert edge.SOURCE_POST_ROUTES == (
        "/workspace/source-operation/prepare", "/workspace/source-operation/submit",
        "/workspace/source-operation/reconcile", "/workspace/source-operation/advance")


@pytest.mark.parametrize("maker", [prepare_config, final_config])
def test_real_2055_caddy_predecessor_preserves_all_non_route_configuration(maker):
    old = predecessor()
    current = manifest()
    candidate = copy.deepcopy(current)
    for item in candidate["files"]:
        item["path"] = item["path"].replace("index-a.css", "index-next.css").replace("index-b.js", "index-next.js")
        item["sha256"] = "b" * 64
    expected = copy.deepcopy(old)
    expected_routes = method_routes(expected)
    expected_routes[0]["match"][0]["path"] = sorted(set(edge.GET_ROUTES) | set(edge.asset_routes(candidate)) |
        (set(edge.asset_routes(current)) if maker is prepare_config else set()))
    expected_routes[1]["match"][0]["path"] = list(edge.POST_ROUTES)
    for route in method_routes(expected)[3:5]:
        route["match"][0]["path"] = (
            list(edge.COMPLETE_MCP_METADATA_ROUTES)
            if route["match"][0]["method"] == ["GET"]
            else list(edge.COMPLETE_MCP_ROUTES))
    actual = maker(fullconfig=old, current_manifest=current, candidate_manifest=candidate, relay_port=49152)
    assert actual == expected
    assert old == predecessor()
    assert len(method_routes(actual)) == 5  # no duplicate source/MCP handlers


@pytest.mark.parametrize("fault", ["old-get-new-post", "new-get-old-post", "new-source-cap"])
def test_mixed_control_profiles_or_source_cap_refuse(fault):
    old = predecessor()
    routes = method_routes(old)
    if fault == "old-get-new-post":
        routes[1]["match"][0]["path"] = list(edge.POST_ROUTES)
    elif fault == "new-get-old-post":
        routes[0]["match"][0]["path"] = sorted(set(edge.GET_ROUTES) | set(edge.asset_routes(manifest())))
    else:
        # Walk through the actual Caddy subroute wrappers to the body limiter.
        def change(node):
            if type(node) is dict:
                if node.get("handler") == "request_body": node["max_size"] = 98305
                for child in node.values(): change(child)
            elif type(node) is list:
                for child in node: change(child)
        change(routes[2]["handle"])
    with pytest.raises(ValueError):
        final_config(fullconfig=old, current_manifest=manifest(), candidate_manifest=manifest(), relay_port=49152)
