"""Installed Session Bridge profile selection must be explicit and fail closed."""
from __future__ import annotations

import json

import pytest

from integrations.executive_mcp.web_ceo import validate_installed_mcp_profile
from integrations.executive_mcp.web_ceo_sessions import WEB_CEO_SESSIONS_PROFILE
from integrations.executive_mcp.web_ceo_v3 import (WEB_CEO_V3_PROFILE, validate_installed_mcp_profile_current)
from ops.executive_os import executive_mcp_entry as entry


def installed_document():
    return {
        "schema": entry.CONFIG_SCHEMA,
        "release_sha": "a" * 40,
        "service_uid": 458,
        "ceo_ingress_socket_path": "/var/run/mastermind-executive/ceo-ingress.sock",
        "port": 8443,
        "policies": {},
        "audit_root": "/var/log/mastermind-executive/mcp-auth",
        "executive_mcp_profile": WEB_CEO_SESSIONS_PROFILE,
    }


def test_current_installed_selector_accepts_sessions_without_expanding_frozen_v2():
    assert validate_installed_mcp_profile_current(WEB_CEO_SESSIONS_PROFILE) == WEB_CEO_SESSIONS_PROFILE
    with pytest.raises(ValueError):
        validate_installed_mcp_profile(WEB_CEO_SESSIONS_PROFILE)


def test_installed_document_accepts_exact_sessions_profile():
    raw = installed_document()
    assert entry.validate_document(raw) == raw


def test_sessions_profile_selects_authenticated_builder_over_existing_ceo_ingress(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from integrations.executive_mcp import server
    from integrations.mastermind_executive_app import gateway
    import uvicorn

    module = entry
    release = "a" * 40
    source = tmp_path / release
    module.__file__ = str(source / "ops/executive_os/executive_mcp_entry.py")
    monkeypatch.setattr(module, "sys", SimpleNamespace(
        flags=SimpleNamespace(isolated=True), dont_write_bytecode=True, path=[]))
    monkeypatch.setattr(module, "require_sealed_path", lambda *a, **k: None)
    monkeypatch.setattr(module.os, "geteuid", lambda: 458)

    raw = installed_document()
    config = tmp_path / "installed.json"
    config.write_text(json.dumps(raw))
    from tests.test_executive_mcp_app_composition import fixture
    policies = gateway.AppPolicies(read=fixture._read_policy(), submit=fixture._submit_policy())
    monkeypatch.setattr(gateway, "load_app_policies", lambda supplied: policies)
    monkeypatch.setattr(module, "build_optional_apps", lambda *a, **k: {})
    sink = SimpleNamespace(close=lambda: None)
    monkeypatch.setattr(module, "PolicyAuditSink", lambda *a, **k: sink)

    calls = []
    app = object()
    monkeypatch.setattr(
        server,
        "build_web_ceo_sessions_mcp_app",
        lambda settings, **kwargs: calls.append((settings, kwargs)) or app,
    )
    monkeypatch.setattr(
        server,
        "build_executive_mcp_app",
        lambda *a, **k: pytest.fail("sessions profile must not fall back to legacy"),
    )
    launches = []
    monkeypatch.setattr(uvicorn, "run", lambda *a, **k: launches.append((a, k)))

    assert module.main(["--config", str(config)]) == 0
    assert len(calls) == 1
    settings, kwargs = calls[0]
    assert settings.ceo_ingress_socket_path == raw["ceo_ingress_socket_path"]
    assert callable(kwargs["session_target_projector"])
    assert callable(kwargs["session_reply_handler"])
    assert callable(kwargs["session_summon_handler"])
    assert launches == [((app,), dict(
        host="127.0.0.1", port=8443, access_log=False,
        proxy_headers=True, forwarded_allow_ips="127.0.0.1",
    ))]

def test_control_daemon_sessions_profile_uses_v2_read_peer_not_legacy(tmp_path, monkeypatch):
    from control_plane.executive_service import CEO_WEB_CEO_V2_READ_SCHEMA
    from integrations.executive_mcp.web_ceo import WebCeoV2InstalledExecutiveReaders
    from tests.test_c1_ceo_ingress_composition import _app_raw, _capture_service, _module

    module = _module()
    raw = _app_raw(tmp_path)
    raw["executive_mcp_profile"] = WEB_CEO_SESSIONS_PROFILE
    captured = _capture_service(module, monkeypatch)
    module._service_from_config(raw)
    binding = captured["ceo_ingress_app_binding"]
    assert type(binding.read_provider) is WebCeoV2InstalledExecutiveReaders
    assert binding.read_schema == CEO_WEB_CEO_V2_READ_SCHEMA
    assert captured["ceo_ingress_armed"] is False


def test_control_daemon_v3_profile_mounts_existing_session_bridge_provider(tmp_path, monkeypatch):
    from tests.test_c1_ceo_ingress_composition import _app_raw, _capture_service, _module

    module = _module()
    raw = _app_raw(tmp_path)
    raw["executive_mcp_profile"] = WEB_CEO_V3_PROFILE
    captured = _capture_service(module, monkeypatch)
    module._service_from_config(raw)
    binding = captured["ceo_ingress_app_binding"]
    assert callable(binding.session_bridge_provider_factory)


@pytest.mark.parametrize("policy_source", ["approved", "revoked", "absent"])
def test_real_control_service_factory_binds_exact_installed_os_read_pair(
    tmp_path, short_socket_root, monkeypatch, policy_source,
):
    """The real Control factory, not a hand-built RuntimeReturn, supplies pairing.

    This is source-composition proof only: no installed production service,
    gateway token, native provider or parent consumption is exercised.
    """
    import asyncio
    import os
    from pathlib import Path
    from common.session_bridge_private_contract import SessionBridgeIngressOwner
    from integrations.mastermind_executive_app.gateway import AppPolicies
    from integrations.session_bridge import installed as bridge
    from tests import test_mastermind_executive_app_asgi as auth
    from tests.test_executive_mcp_installed_fabric_composition import factory_service

    canonical = Path("/Library/Application Support/MastermindExecutive/config/executive-mcp.json")
    root_policies = AppPolicies(read=auth._read_policy(), submit=auth._submit_policy())
    pair = entry.build_additional_policies({
        "executive_mcp_profile": WEB_CEO_V3_PROFILE,
        "os_executive_transport": True,
        "os_executive_resource": entry.OS_EXECUTIVE_RESOURCE,
    }, root_policies)[0]
    original_exists = Path.exists
    def exists(path):
        return policy_source != "absent" if path == canonical else original_exists(path)
    monkeypatch.setattr(Path, "exists", exists)

    selections, supplied = [], []
    def sealed_source(path, source, *, expected_uid):
        assert path == canonical
        assert source.is_absolute()
        assert expected_uid == os.geteuid()
        selections.append(path)
        if policy_source == "revoked":
            def withdrawn():
                raise ValueError("sealed gateway pair withdrawn")
            return withdrawn
        return lambda: pair
    monkeypatch.setattr(entry, "installed_os_session_policy_source", sealed_source)

    actual_build = bridge.build_runtime_session_bridge
    def capture_factory(runtime, **kwargs):
        supplied.append(kwargs["authorized_policies"])
        return actual_build(runtime, **kwargs)
    monkeypatch.setattr(bridge, "build_runtime_session_bridge", capture_factory)

    async def run():
        async with factory_service(tmp_path, short_socket_root, monkeypatch,
                profile=WEB_CEO_V3_PROFILE) as (service, _raw, _):
            await service.start()
            runtime = service._require_runtime()
            owner = service._ceo_ingress_app_binding.session_bridge_provider_factory(runtime)
            assert type(owner) is SessionBridgeIngressOwner
            assert len(supplied) == 1
            assert supplied[0] == (pair if policy_source == "approved" else None)
    asyncio.run(run())
    assert len(selections) == (0 if policy_source == "absent" else 1)
