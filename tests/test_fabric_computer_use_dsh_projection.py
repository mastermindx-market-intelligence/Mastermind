"""Existing Computer Use owner catalog -> existing unarmed DSH policy projection.

No host application, native signed helper, MCP listener, callback dispatch,
credential, authenticated principal, installer or production profile is used.
Synthetic grants test compatibility, not admission or Runtime tool permissions.
"""
from __future__ import annotations

import copy
import dataclasses
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

from control_plane.dsh_mcp_client_projection import (
    DshMcpProjectionError, project_dsh_mcp_tools,
)
from control_plane.executive_agent_capabilities import (
    ExecutionCapabilityRegistry, observed_mcp_tool_schema_digest,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = (
    ROOT / "scripts/ohf/fixtures/"
    "executive_agent_capabilities_v4_mastermind_operator.json"
)
READ = ("cuse_get_app_state", "cuse_list_apps")
WRITE = ("cuse_click", "cuse_press_key", "cuse_type_text")


def _original_js_catalog(tmp_path, *, allow_read=True, allow_write=False, recorder=False):
    """Ask the REAL source-only JS facet what a test owner permits NOW.

    This is a pure listTools call. The injected dispatcher always fails if
    reached; there is no node screenshot, desktop operation or provider auth.
    """
    node = shutil.which("node")
    assert node is not None
    root = tmp_path / "isolated-node-home"
    root.mkdir(exist_ok=True)
    script = f'''
import {{createComputerUseFacet}} from "./ops/codex_computer_use/remote-facet.mjs";
let dispatches=0;let records=0;
const facet=createComputerUseFacet({{
  authorize: async (_ctx,request)=>({{
    allowed:(request.mode==="read" ? {str(allow_read).lower()} : {str(allow_write).lower()}),
    canRead:{str(allow_read).lower()}, canWrite:{str(allow_write).lower()},
    principalRef:"synthetic-principal",bindingRef:"synthetic-binding",operationRef:"synthetic-operation"
  }}),
  dispatch:async()=>{{dispatches++;throw Error("UNAUTHORIZED_DISPATCH");}},
  {('recordUncertainEffect:async()=>{records++;},' if recorder else '')}
}});
const catalog=await facet.listTools({{principalRef:"synthetic-principal"}});
console.log(JSON.stringify({{catalog,dispatches,records}}));
'''
    proc = subprocess.run(
        [node, "--input-type=module", "-e", script],
        cwd=ROOT, capture_output=True, text=True, timeout=12, check=False,
        env={"PATH": "/opt/homebrew/bin:/usr/bin:/bin",
             "HOME": str(root), "LC_ALL": "C"},
    )
    assert proc.returncode == 0, proc.stderr[-1000:]
    value = json.loads(proc.stdout)
    assert value["dispatches"] == value["records"] == 0
    return value["catalog"]


def _project_synthetic_existing_dsh_grant(catalog, selected):
    """Produce no grant; exercise the existing closed projection in isolation."""
    registry = ExecutionCapabilityRegistry.load(FIXTURE, source_root=ROOT)
    assert registry.production_armed is False
    base = registry.resolve("operator.browser.local-review.v1")
    assert base.enabled and len(base.mcp_server_grants) >= 1
    incumbent = next(g for g in base.mcp_server_grants if g.transport == "stdio")
    by_name = {row["name"]: row for row in catalog["tools"]}
    digest = observed_mcp_tool_schema_digest(
        {"tools": {name: by_name[name] for name in selected if name in by_name}}
    )
    capability = "fixture.cuse.owner.bound.v1"
    signed = dataclasses.replace(
        incumbent, capability_id=capability,
        config_name="CuseOwnerFixture", transport="streamable-http",
        url="https://cuse-fixture.example/mcp", command=None, args=(),
        required=True, enabled_tools=tuple(selected),
        server_identity="Mastermind Computer Use Fixture",
        server_version="source-only", default_tools_approval_mode="approve",
        tool_schema_digest=digest,
        grant_digest=hashlib.sha256(b"UNARMED_CUSE_FIXTURE_GRANT").hexdigest(),
    )
    profile = dataclasses.replace(
        base, profile_id="fixture.cuse.dsh.projection",
        mcp_server_grants=(signed,),
        profile_digest=hashlib.sha256(b"UNARMED_CUSE_FIXTURE_PROFILE").hexdigest(),
    )
    return project_dsh_mcp_tools(
        profile, capability_id=capability, observed_tool_catalog=catalog,
    ).configuration()


def test_real_owner_catalog_read_only_stays_approval_required_and_unarmed(tmp_path):
    catalog = _original_js_catalog(tmp_path, allow_read=True)
    assert sorted(row["name"] for row in catalog["tools"]) == list(READ)
    assert all(row["annotations"]["readOnlyHint"] is True
               and row["annotations"]["destructiveHint"] is False
               for row in catalog["tools"])
    result = _project_synthetic_existing_dsh_grant(catalog, READ)
    assert result["production_armed"] is False
    assert result["approvalMode"] == "approve"
    assert result["target"] == {
        "serverName": "CuseOwnerFixture",
        "transport": "streamable-http",
        "url": "https://cuse-fixture.example/mcp",
    }
    assert [tool["name"] for tool in result["tools"]] == list(READ)
    assert result["source"]["tool_schema_digest"]


def test_only_explicit_write_owner_with_effect_recorder_surfaces_write_catalog(tmp_path):
    # Write owner grant alone is insufficient: current original facet also
    # requires the Runtime's existing uncertain-effect recorder callback.
    no_recorder = _original_js_catalog(
        tmp_path, allow_read=True, allow_write=True, recorder=False,
    )
    assert sorted(t["name"] for t in no_recorder["tools"]) == list(READ)
    approved = _original_js_catalog(
        tmp_path, allow_read=True, allow_write=True, recorder=True,
    )
    assert sorted(row["name"] for row in approved["tools"]) == sorted(READ + WRITE)
    result = _project_synthetic_existing_dsh_grant(approved, tuple(sorted(READ + WRITE)))
    assert not result["production_armed"]
    assert result["approvalMode"] == "approve"
    by_name = {row["name"]: row for row in result["tools"]}
    assert set(by_name) == set(READ + WRITE)
    assert all(by_name[name]["annotations"]["destructiveHint"] is True
               and by_name[name]["annotations"]["readOnlyHint"] is False
               for name in WRITE)
    assert all(by_name[name]["annotations"]["readOnlyHint"] is True for name in READ)


def test_policy_absent_refuses_projection_and_never_dispatches(tmp_path):
    denied = _original_js_catalog(tmp_path, allow_read=False, allow_write=False)
    assert denied["tools"] == []
    with pytest.raises(DshMcpProjectionError):
        _project_synthetic_existing_dsh_grant(denied, READ)


def test_existing_digest_verifier_refuses_schema_and_annotation_drift(tmp_path):
    approved = _original_js_catalog(tmp_path, allow_read=True)
    original = _project_synthetic_existing_dsh_grant(approved, READ)
    assert original["production_armed"] is False
    # Derive an exact synthetic source grant from original good observation,
    # then present altered catalog WITHOUT changing the grant/digest.
    registry = ExecutionCapabilityRegistry.load(FIXTURE, source_root=ROOT)
    base = registry.resolve("operator.browser.local-review.v1")
    incumbent = next(g for g in base.mcp_server_grants if g.transport == "stdio")
    by_name = {row["name"]: row for row in approved["tools"]}
    digest = observed_mcp_tool_schema_digest({"tools": by_name})
    grant = dataclasses.replace(
        incumbent, capability_id="fixture.cuse.owner.bound.v1",
        config_name="CuseOwnerFixture", transport="streamable-http",
        url="https://cuse-fixture.example/mcp", command=None, args=(),
        required=True, enabled_tools=READ,
        server_identity="Mastermind Computer Use Fixture", server_version="source-only",
        default_tools_approval_mode="approve", tool_schema_digest=digest,
        grant_digest=hashlib.sha256(b"UNARMED_CUSE_FIXTURE_GRANT").hexdigest(),
    )
    profile = dataclasses.replace(
        base, profile_id="fixture.cuse.dsh.projection",
        mcp_server_grants=(grant,),
        profile_digest=hashlib.sha256(b"UNARMED_CUSE_FIXTURE_PROFILE").hexdigest(),
    )
    for mutated in (
        {"tools": approved["tools"][:-1]},
        {"tools": [*approved["tools"], approved["tools"][0]]},
        {"tools": approved["tools"], "nextCursor": "more"},
    ):
        with pytest.raises(DshMcpProjectionError):
            project_dsh_mcp_tools(
                profile, capability_id=grant.capability_id,
                observed_tool_catalog=mutated,
            )
    for field, value in (("inputSchema", {"type": "null"}),
                         ("annotations", {"readOnlyHint": False})):
        altered = copy.deepcopy(approved)
        altered["tools"][0][field] = value
        with pytest.raises(DshMcpProjectionError):
            project_dsh_mcp_tools(
                profile, capability_id=grant.capability_id,
                observed_tool_catalog=altered,
            )
