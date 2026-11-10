"""Real SDK/App -> original Unix client -> Control -> current DATA/plan owners.

Collectable in the cloud; execution requires the existing AF_UNIX capability
and belongs to the authorized M2 qualification host. No socket, peer check,
namespace custody or private service handler is mocked. Source publication,
OAuth and provider edges retain the incumbent disposable fixture limits.
No model, native session, installed profile or runtime activation is performed.
"""
from __future__ import annotations

import asyncio
from copy import deepcopy
from dataclasses import asdict, replace
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace

import pytest

from common import coo_agentos_context_contract as context_wire
from common import coo_project_help_contract as wire
from control_plane.executive_service import ExecutiveControlService, CeoIngressAppBinding
from integrations.hermes_harness.tests.test_native_project_help import hermes_signed
from integrations.mastermind_executive_app.coo_installed import CooFactsClient
from integrations.session_bridge.installed import build_runtime_session_bridge, principal_frame as session_frame
from tests import test_t3_project_help_api as api
from tests.test_coo_project_help_authority import (
    qualified_help, full_joined, owner, env, isolated_git_env, identity,
)
from tests.test_executive_service import _config, _FakeSupervisor

rsa_key = api.rsa_key


def test_installed_factory_captures_original_help_client_and_current_catalogue(
        hermes_signed, tmp_path, monkeypatch):
    """Actual factory/registry, with the incumbent explicit root-seal edge.

    No socket is opened and no installed UID, root seal or activation is
    claimed. The separately authenticated principal is the real JWT fixture.
    """
    from ops.executive_os import executive_mcp_entry as entry
    from ops.executive_os.coo_principal_host import CLAUDE_PRINCIPAL_POLICY
    from integrations.mastermind_executive_app.gateway import APP_POLICY_ENVELOPE_SCHEMA
    from integrations.mastermind_workspace_app.installed import CeoIngressWorkspaceClient

    s = hermes_signed
    source = tmp_path / ("a" * 40)
    source.mkdir()
    policy_path = source / CLAUDE_PRINCIPAL_POLICY
    policy_path.parent.mkdir(parents=True, exist_ok=True)
    policy_path.write_bytes(s.f.policy_path.read_bytes())
    raw = {"schema": entry.CONFIG_SCHEMA, "release_sha": source.name,
        "service_uid": 458, "port": 8443,
        "ceo_ingress_socket_path": "/var/run/mastermind-executive/ceo-ingress.sock",
        "audit_root": "/var/log/mastermind-executive/mcp-auth",
        "executive_mcp_profile": "web_ceo_v3",
        "policies": {"schema": APP_POLICY_ENVELOPE_SCHEMA,
            "read": asdict(s.settings.executive.policies.read),
            "submit": asdict(s.settings.executive.policies.submit)},
        "coo": deepcopy(s.f.coo)}
    raw = json.loads(json.dumps(raw))
    config_path = tmp_path / "executive-mcp.json"
    config_path.write_text(json.dumps(raw))
    seals = []
    monkeypatch.setattr(entry, "require_sealed_path", lambda path, **kw: seals.append((path, kw)))
    monkeypatch.setattr(entry.os, "geteuid", lambda: 458)
    settings = entry.build_installed_coo_settings(raw, source, config_path, s.settings.executive)
    client = settings.project_help_provider.__self__
    assert type(client) is CooFactsClient
    for name in ("authority_provider", "mission_provider", "agentos_context_provider",
                 "agentos_current_context_provider", "agentos_discovery_context_provider",
                 "project_help_context_provider", "project_help_provider"):
        assert getattr(settings, name).__self__ is client
    assert type(client._client) is CeoIngressWorkspaceClient
    assert client._client.socket_path == Path(raw["ceo_ingress_socket_path"])
    assert settings.catalogue_provider(s.principal, s.f.work) == wire.CATALOGUE
    assert settings.load_binding() == raw["coo"]["binding"]
    assert seals and any(path == policy_path for path, _ in seals)
    raw["coo"]["missions"][0]["enabled"] = False
    config_path.write_text(json.dumps(raw))
    with pytest.raises(ValueError):
        settings.catalogue_provider(s.principal, s.f.work)


@pytest.mark.parametrize("boundary", ["current", "revoked_after_original_read"])
def test_actual_project_help_private_frames_reach_original_unix_service(
        hermes_signed, tmp_path, monkeypatch, boundary):
    s = hermes_signed
    f, runtime = s.f, s.f.j["runtime"]
    seen = []
    original = f.provider.read_project_help
    async def observed(frame, **options):
        # This wrapper only records the actual decoded frame and invokes the
        # original method. It does not construct/replace a read response.
        value = await original(frame, **options)
        seen.append(json.loads(json.dumps(frame)))
        if boundary == "revoked_after_original_read":
            f.coo["missions"][0]["enabled"] = False
        return value
    monkeypatch.setattr(f.provider, "read_project_help", observed)

    async def run():
        with tempfile.TemporaryDirectory(prefix="mmx-help-v6-", dir="/tmp") as directory:
            sockets = Path(directory)
            service_root = tmp_path / "help-unix-owner"
            service_root.mkdir()
            config = _config(service_root, socket_root=sockets, runtime_root=runtime.store.root,
                coo_autonomy_armed=False, ceo_submit_armed=False)
            bridge = build_runtime_session_bridge(runtime, dialogue_socket_path=sockets / "unused-dialogue.sock")
            def facts(actual):
                assert actual is runtime
                return f.provider
            def targets(actual):
                assert actual is runtime
                return bridge
            binding = CeoIngressAppBinding(peer_uid=os.geteuid(), armed=True,
                grounding_provider=SimpleNamespace(observe=lambda: {}),
                principal_facts_factory=facts, session_bridge_provider_factory=targets)
            service = ExecutiveControlService(config, runtime_factory=lambda root: runtime,
                supervisor_factory=lambda actual: _FakeSupervisor(actual),
                ceo_ingress_socket_path=sockets / "help.sock", ceo_ingress_peer_uid=os.geteuid() + 1,
                ceo_ingress_grounding_provider=SimpleNamespace(observe=lambda: {}),
                ceo_ingress_app_binding=binding)
            await service.start()
            old_bounded = f.workspace._bounded_runtime
            try:
                assert service.runtime is runtime
                f.workspace._bounded_runtime = service._namespace_custody.bound_runtime
                client = CooFactsClient(sockets / "help.sock")
                s.settings = replace(s.settings,
                    executive=replace(s.settings.executive, ceo_ingress_socket_path=sockets / "help.sock"),
                    authority_provider=client.authority, mission_provider=client.mission,
                    project_help_context_provider=client.project_help_context,
                    project_help_provider=client.project_help)
                before = api._events(f)
                async with api._session(s) as (session, _):
                    tools = await session.list_tools()
                    assert {wire.TOOL, context_wire.CURRENT_TOOL} <= {tool.name for tool in tools.tools}
                    base = await session.call_tool(context_wire.CURRENT_TOOL, {"work_ref": f.work})
                    assert base.isError is False, api._payload(base)
                    base_value = api._payload(base)["data"]
                    assert base_value["schema"] == context_wire.HELP_CONTEXT_RESULT_SCHEMA
                    assert base_value["receipt"]["source_mode"] == "CANONICAL_PROJECT_DATA"
                    result = await session.call_tool(wire.TOOL, {"work_ref": f.work})
                payload = api._payload(result)
                assert seen and seen[0]["schema"] == wire.FRAME_SCHEMA
                assert seen[0]["session_principal"] == session_frame(s.principal)
                assert seen[0]["principal_context"] == f.frame["principal_context"]
                assert seen[0]["workspace_principal"] == f.frame["workspace_principal"]
                assert api._events(f) == before
                if boundary == "current":
                    assert result.isError is False, payload
                    data = payload["data"]
                    assert data["scope"] == f.scope
                    assert data["observation"]["mission"]["mission_read_state"] == "PARTIAL"
                    assert data["targets"]["state"] == "AVAILABLE"
                    assert data["targets"]["items"] == []
                    assert len(seen) == 2 and data["execution_authority"] is False
                else:
                    assert result.isError is True and payload.get("data") is None
                    assert len(seen) == 1
            finally:
                f.workspace._bounded_runtime = old_bounded
                await service.close()
    asyncio.run(run())
