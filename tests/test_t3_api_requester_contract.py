"""Explicit T3 API requester grant; no native identity or runtime activation.

The source profile is disabled. Tests enable a disposable installed policy and
mission through their real existing parsers. The native Hermes publication and
ConsumerSlot contracts are deliberately not part of this API-principal route.
"""
from __future__ import annotations

import asyncio
import copy
import dataclasses
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from common import coo_requester_return_contract as wire
from control_plane.coo_principal_host import MISSION_AUTHORITY_VERSION
from control_plane.executive_agent_capabilities import (
    CapabilityPolicyError, ExecutionCapabilityRegistry,
    HERMES_NATIVE_REQUESTER_RETURN_PROFILE_ID,
    PRINCIPAL_COO_REQUESTER_RETURN_MCP_CAPABILITY_ID,
    PRINCIPAL_COO_T3_API_REQUESTER_RETURN_MCP_CAPABILITY_ID as GRANT,
    T3_API_PRINCIPAL_EXECUTION_SURFACE,
    T3_API_REQUESTER_RETURN_PROFILE_ID as PROFILE,
    observed_mcp_tool_schema_digest,
)
from integrations.executive_mcp import coo, server
from integrations.mastermind_executive_app.coo_binding import principal_frame
from ops.executive_os.coo_principal_host import CooInstalledSource
from tests import test_hermes_selected_child_ingress as ingress
from tests.test_executive_coo_host import setup

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "config/executive_claude_principal_capabilities.json"
rsa_key = ingress.rsa_key


def enable_disposable_t3_requester_contract(host, configuration, path):
    """Explicitly enable this source profile in a fixture, never relabel Hermes."""
    raw = json.loads(path.read_bytes())
    assert raw["profiles"][PROFILE]["enabled"] is False
    assert PRINCIPAL_COO_REQUESTER_RETURN_MCP_CAPABILITY_ID not in raw["mcp_servers"]
    assert HERMES_NATIVE_REQUESTER_RETURN_PROFILE_ID not in raw["profiles"]
    raw["profiles"][PROFILE]["enabled"] = True
    path.write_text(json.dumps(raw))
    registry = ExecutionCapabilityRegistry.load(path, source_root=ROOT)
    profile = registry.profiles[PROFILE]
    configuration["missions"][0].update(
        authority_version=MISSION_AUTHORITY_VERSION,
        principal_actions=sorted(["bounded_intent", "governed_orchestration", wire.ACTION]),
        capability_profile_id=PROFILE, capability_profile_digest=profile.profile_digest)
    return profile


def test_new_disabled_profile_preserves_every_legacy_configuration_entry():
    raw = json.loads(POLICY.read_bytes())
    baseline = copy.deepcopy(raw)
    profile = baseline["profiles"].pop(PROFILE)
    grant = baseline["mcp_servers"].pop(GRANT)
    # Later explicit joint API entries have their own exact preservation
    # proof. Removing only those additions retains this v6/EG3 baseline.
    for family in ("t3", "paperclip"):
        baseline["profiles"].pop(f"principal.{family}-api.executive-coo.project-help-requester.v1")
        baseline["mcp_servers"].pop(f"mastermind-executive-coo-{family}-api-project-help-requester-v1")
    # The exact EG2 source policy remains unchanged after removing this pair.
    canonical = json.dumps(baseline, sort_keys=True, separators=(",", ":")).encode()
    assert hashlib.sha256(canonical).hexdigest() == "9522a6a65771748b000056378d096fb8cd2a1befa9ed9ed23b58044d2d493b53"
    assert profile["enabled"] is False and raw["production_armed"] is False
    assert profile["execution_surface"] == T3_API_PRINCIPAL_EXECUTION_SURFACE
    assert profile["mcp_servers"] == [GRANT]
    assert grant["tool_schema_digest"] == coo.coo_requester_return_tool_schema_digest()
    assert grant["tool_schema_digest"] == "29d6f504b79e806feefed6ab16f413338dd267de5019c7590fdc3655765537e3"
    assert set(grant["enabled_tools"]) == {s.name for s in coo.catalogue_specs(wire.CATALOGUE)}
    assert "executive_project_help" not in grant["enabled_tools"]
    registry = ExecutionCapabilityRegistry.load(POLICY, source_root=ROOT)
    with pytest.raises(CapabilityPolicyError):
        registry.resolve(PROFILE)
    assert CooInstalledSource._profile_catalogue(registry.profiles[PROFILE]) == wire.CATALOGUE


@pytest.mark.parametrize("fault", [
    "borrowed_by_hermes", "wrong_surface", "legacy_grant", "help_grant",
    "catalogue_union", "wrong_url", "wrong_auth", "unknown_t3_profile",
    "write_capability", "native_helpers",
])
def test_registry_rejects_cross_family_or_widened_t3_grants(tmp_path, fault):
    raw = json.loads(POLICY.read_bytes())
    profile, grant = raw["profiles"][PROFILE], raw["mcp_servers"][GRANT]
    if fault == "borrowed_by_hermes":
        raw["profiles"]["principal.hermes-native.executive-coo.v1"]["mcp_servers"] = [GRANT]
    elif fault == "wrong_surface":
        profile["execution_surface"] = "hermes-native-principal"
    elif fault == "legacy_grant":
        profile["mcp_servers"] = ["mastermind-executive-coo-v1"]
    elif fault == "help_grant":
        profile["mcp_servers"] = ["mastermind-executive-coo-project-help-v1"]
    elif fault == "catalogue_union":
        profile["mcp_servers"].append("mastermind-executive-coo-project-help-v1")
    elif fault == "wrong_url":
        grant["url"] = "https://example.invalid/mcp/coo"
    elif fault == "wrong_auth":
        grant["auth_status"] = "unsupported"
    elif fault == "unknown_t3_profile":
        raw["profiles"]["principal.t3-api.unreviewed.v1"] = raw["profiles"].pop(PROFILE)
    elif fault == "write_capability":
        profile["write_capable"] = True
    else:
        profile["native_helper_policy"] = "unrestricted"
    path = tmp_path / "capabilities.json"
    path.write_text(json.dumps(raw))
    with pytest.raises(CapabilityPolicyError):
        ExecutionCapabilityRegistry.load(path, source_root=ROOT)


@pytest.mark.parametrize("fault", ["old_digest", "extra_tool"])
def test_installed_catalogue_requires_the_exact_ack_descriptor(tmp_path, fault):
    raw = json.loads(POLICY.read_bytes())
    grant = raw["mcp_servers"][GRANT]
    if fault == "old_digest":
        grant["tool_schema_digest"] = coo.coo_tool_schema_digest()
    else:
        grant["enabled_tools"].append("executive_project_help")
    path = tmp_path / "capabilities.json"
    path.write_text(json.dumps(raw))
    registry = ExecutionCapabilityRegistry.load(path, source_root=ROOT)
    with pytest.raises(ValueError):
        CooInstalledSource._profile_catalogue(registry.profiles[PROFILE])


@pytest.mark.parametrize("fault", ["missing_action", "stale_digest", "disabled_profile", "disabled_mission", "foreign_principal"])
def test_actual_installed_source_requires_current_exact_principal_profile_and_action(tmp_path, fault):
    host, config, principal, path = setup(tmp_path)
    profile = enable_disposable_t3_requester_contract(host, config, path)
    work = config["missions"][0]["work_ref"]
    assert host.source.catalogue_for_principal(principal, work_ref=work) == wire.CATALOGUE
    assert host.source.snapshot(work)[2].capability_profile_digest == profile.profile_digest
    assert host.source.has_context_read_grant() is False
    if fault == "missing_action":
        config["missions"][0]["principal_actions"].remove(wire.ACTION)
    elif fault == "stale_digest":
        config["missions"][0]["capability_profile_digest"] = "f" * 64
    elif fault == "disabled_profile":
        raw = json.loads(path.read_bytes())
        raw["profiles"][PROFILE]["enabled"] = False
        path.write_text(json.dumps(raw))
    elif fault == "disabled_mission":
        config["missions"][0]["enabled"] = False
    else:
        principal = dict(principal, client_ref="foreign-client")
    with pytest.raises(ValueError):
        host.source.catalogue_for_principal(principal, work_ref=work)


def test_actual_mcp_factory_negotiates_t3_ack_catalogue_with_one_resource(tmp_path, rsa_key):
    """Actual signed OAuth/MCP catalogue proof; no private dispatch is invoked."""
    host, config, _principal, path = setup(tmp_path)
    enable_disposable_t3_requester_contract(host, config, path)
    bundle = SimpleNamespace(host=host, authority_config=config, target=ingress._target())

    async def exercise():
        settings, token = await ingress._installed_app(bundle, rsa_key,
            socket_path=tmp_path / "never-opened.sock")
        settings = dataclasses.replace(settings, catalogue_provider=lambda principal, work_ref=None:
            host.source.catalogue_for_principal(principal_frame(principal), work_ref=work_ref))
        app = server._build_coo_mcp_app(settings, audit_sink=ingress.app_fixture.Sink())
        async with app._app.router.lifespan_context(app._app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                base_url="http://127.0.0.1", headers={"authorization": "Bearer " + token}) as http_client:
                assert "x-mastermind-workspace-authorization" not in http_client.headers
                async with streamable_http_client("http://127.0.0.1/mcp/coo", http_client=http_client) as (read, write, _):
                    async with ClientSession(read, write) as session:
                        initialized = await session.initialize()
                        assert initialized.serverInfo.name == "mastermind-executive-coo"
                        tools = await session.list_tools()
                        observed = {"tools": {t.name: {"name": t.name, "inputSchema": t.inputSchema,
                            "annotations": t.annotations.model_dump(exclude_none=True) if t.annotations else {}}
                            for t in tools.tools}}
                        assert observed_mcp_tool_schema_digest(observed) == coo.coo_requester_return_tool_schema_digest()
                        assert "executive_project_help" not in {t.name for t in tools.tools}

    asyncio.run(exercise())
