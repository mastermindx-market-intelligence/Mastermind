"""Explicit joint API catalogue; no native publication or installed activation."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from common import coo_project_help_contract as help_wire
from common import coo_requester_return_contract as return_wire
from control_plane.coo_principal_host import generation
from control_plane.executive_agent_capabilities import (
    CapabilityPolicyError, ExecutionCapabilityRegistry,
    T3_API_PROJECT_HELP_REQUESTER_PROFILE_ID,
    PAPERCLIP_API_PROJECT_HELP_REQUESTER_PROFILE_ID,
    PRINCIPAL_COO_T3_API_PROJECT_HELP_REQUESTER_MCP_CAPABILITY_ID,
    PRINCIPAL_COO_PAPERCLIP_API_PROJECT_HELP_REQUESTER_MCP_CAPABILITY_ID,
)
from integrations.executive_mcp import coo
from ops.executive_os.coo_principal_host import CooInstalledSource
from tests.test_executive_coo_host import setup

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "config/executive_claude_principal_capabilities.json"
PAIRS = (
    (T3_API_PROJECT_HELP_REQUESTER_PROFILE_ID,
     PRINCIPAL_COO_T3_API_PROJECT_HELP_REQUESTER_MCP_CAPABILITY_ID, "t3-api-principal"),
    (PAPERCLIP_API_PROJECT_HELP_REQUESTER_PROFILE_ID,
     PRINCIPAL_COO_PAPERCLIP_API_PROJECT_HELP_REQUESTER_MCP_CAPABILITY_ID, "paperclip-api-principal"),
)


def enable_joint_profile(configuration, path, *, family, scope):
    """Disposable fixture enrollment through the actual source parser."""
    profile_id, _, _ = next(pair for pair in PAIRS if pair[2] == family + "-api-principal")
    raw = json.loads(path.read_bytes())
    assert raw["profiles"][profile_id]["enabled"] is False
    raw["profiles"][profile_id]["enabled"] = True
    path.write_text(json.dumps(raw))
    registry = ExecutionCapabilityRegistry.load(path, source_root=ROOT)
    profile = registry.profiles[profile_id]
    configuration["missions"][0].update(
        authority_version=4,
        principal_actions=sorted(["bounded_intent", "governed_orchestration",
                                  help_wire.ACTION, return_wire.ACTION]),
        capability_profile_id=profile_id, capability_profile_digest=profile.profile_digest,
        project_help=copy.deepcopy(help_wire.scope(scope)))
    return profile


def _scope(work="WS:EXECUTIVE-CAPACITY-FABRIC", root="JOB-001"):
    # Shape-only fixture, never used as an adopted-source/Mission proof.
    return {"schema": help_wire.SCOPE_SCHEMA, "root_job_id": root,
        "source_plan": {"schema": help_wire.PLAN_SCHEMA, "work_ref": work,
            "source": {"repository": "mastermindx-market-intelligence/Mastermind",
                "commit": "a" * 40, "path": "docs/plans/fixture-plan.md", "content_sha256": "b" * 64},
            "contract_sha256": "c" * 64}}


def test_joint_catalogue_has_new_digest_and_preserves_every_prior_descriptor():
    assert coo.coo_project_help_requester_tool_schema_digest() == "f98abf1e3928b1c56d6e58aeeeb2eacba04db07e6d96f8e38aeb8d9f1b65b905"
    assert coo.coo_project_help_tool_schema_digest() == "0b7d9e4b7c336d0330665f40ebd8f2156997c3e42a0245c641dda625893a3e6e"
    assert coo.coo_requester_return_tool_schema_digest() == "29d6f504b79e806feefed6ab16f413338dd267de5019c7590fdc3655765537e3"
    joint = {item.name: item for item in coo.catalogue_specs(help_wire.API_REQUESTER_CATALOGUE)}
    original = {item.name: item for item in coo.catalogue_specs(help_wire.CATALOGUE)}
    assert set(joint) == set(original)
    for name in joint:
        if name != "mmx_delegate":
            assert joint[name] is original[name]
    assert joint["mmx_delegate"] is next(item for item in coo.catalogue_specs(return_wire.CATALOGUE)
                                       if item.name == "mmx_delegate")


def test_joint_configuration_is_only_two_disabled_exact_profile_grant_pairs():
    raw = json.loads(POLICY.read_bytes())
    old = copy.deepcopy(raw)
    for profile, grant, surface in PAIRS:
        configured = old["profiles"].pop(profile)
        descriptor = old["mcp_servers"].pop(grant)
        assert configured["enabled"] is False and configured["execution_surface"] == surface
        assert configured["mcp_servers"] == [grant]
        assert descriptor["tool_schema_digest"] == coo.coo_project_help_requester_tool_schema_digest()
        assert set(descriptor["enabled_tools"]) == {item.name for item in coo.COO_PROJECT_HELP_REQUESTER_TOOL_SPECS}
    # Every EG3/v6/legacy source entry stays byte-equivalent as JSON values.
    assert hashlib.sha256(json.dumps(old, sort_keys=True, separators=(",", ":")).encode()).hexdigest() == "5f08078cac95438476304376c1215b772c27c5538295b11276e8c7678bc27d3d"
    assert raw["production_armed"] is False
    registry = ExecutionCapabilityRegistry.load(POLICY, source_root=ROOT)
    for profile, _, _ in PAIRS:
        with pytest.raises(CapabilityPolicyError):
            registry.resolve(profile)
        assert CooInstalledSource._profile_catalogue(registry.profiles[profile]) == help_wire.API_REQUESTER_CATALOGUE


@pytest.mark.parametrize("family", ["t3", "paperclip"])
@pytest.mark.parametrize("fault", ["borrow_other_grant", "native_surface", "unknown_profile", "union", "write", "wrong_url"])
def test_joint_registry_refuses_borrowed_or_widened_grants(tmp_path, family, fault):
    raw = json.loads(POLICY.read_bytes())
    pair = next(row for row in PAIRS if row[2] == family + "-api-principal")
    other = next(row for row in PAIRS if row != pair)
    profile, grant = raw["profiles"][pair[0]], raw["mcp_servers"][pair[1]]
    if fault == "borrow_other_grant": profile["mcp_servers"] = [other[1]]
    elif fault == "native_surface": profile["execution_surface"] = "hermes-native-principal"
    elif fault == "unknown_profile": raw["profiles"][pair[0] + ".unknown"] = raw["profiles"].pop(pair[0])
    elif fault == "union": profile["mcp_servers"].append("mastermind-executive-coo-v1")
    elif fault == "write": profile["write_capable"] = True
    else: grant["url"] = "https://foreign.invalid/mcp/coo"
    path = tmp_path / "policy.json"
    path.write_text(json.dumps(raw))
    with pytest.raises(CapabilityPolicyError):
        ExecutionCapabilityRegistry.load(path, source_root=ROOT)


@pytest.mark.parametrize("family", ["t3", "paperclip"])
@pytest.mark.parametrize("fault", ["help_action", "ack_action", "old_mission", "foreign_root", "changed_source", "disabled"])
def test_installed_joint_scope_requires_current_actions_root_and_generation(tmp_path, family, fault):
    host, configuration, principal, path = setup(tmp_path)
    work = configuration["missions"][0]["work_ref"]
    enable_joint_profile(configuration, path, family=family, scope=_scope(work))
    row, _, authority = host.source.for_principal(principal, work)
    original_generation = generation(row)
    assert host.source.catalogue_for_principal(principal, work_ref=work) == help_wire.API_REQUESTER_CATALOGUE
    assert host.source.has_context_read_grant() is True
    host._require_selected_child_project_scope(row, work, "JOB-001")
    mutable = configuration["missions"][0]
    if fault in {"help_action", "ack_action"}:
        mutable["principal_actions"].remove(help_wire.ACTION if fault == "help_action" else return_wire.ACTION)
    elif fault == "old_mission":
        mutable["authority_version"] = 2
        mutable.pop("project_help")
        mutable["principal_actions"].remove(help_wire.ACTION)
    elif fault == "foreign_root":
        mutable["project_help"]["root_job_id"] = "JOB-002"
        current, _, _ = host.source.for_principal(principal, work)
        with pytest.raises(ValueError, match="project scope"):
            host._require_selected_child_project_scope(current, work, "JOB-001")
        assert generation(current) != original_generation
        return
    elif fault == "changed_source":
        mutable["project_help"]["source_plan"]["source"]["commit"] = "d" * 40
        current, _, current_authority = host.source.for_principal(principal, work)
        assert generation(current) != original_generation
        assert current_authority.authority_generation_digest != authority.authority_generation_digest
        return
    else:
        mutable["enabled"] = False
    with pytest.raises(ValueError):
        host.source.catalogue_for_principal(principal, work_ref=work)
