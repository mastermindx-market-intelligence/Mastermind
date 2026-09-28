"""Installed Personal Executive MCP read-profile acceptance."""
from __future__ import annotations

import asyncio
import inspect
import json
import sys
from pathlib import Path
from typing import Any

import pytest


def _auth_fixture():
    sys.path.insert(0, str(Path(__file__).parent))
    try:
        import test_mastermind_executive_app_asgi as fixture
        return fixture
    finally:
        sys.path.pop(0)


def test_personal_read_schema_is_exactly_four_readers_and_pinned():
    from integrations.executive_mcp import personal_read as profile
    from integrations.executive_mcp.schemas import MODIFYING_TOOL

    assert profile.PERSONAL_READ_PROFILE == "personal_read"
    assert profile.PERSONAL_READ_TOOL_NAMES == (
        "executive_state",
        "executive_inbox",
        "executive_job",
        "ceo_intent_status",
    )
    assert MODIFYING_TOOL not in profile.PERSONAL_READ_TOOL_NAMES
    assert [spec.name for spec in profile.PERSONAL_READ_TOOL_SPECS] == list(
        profile.PERSONAL_READ_TOOL_NAMES
    )
    assert all(spec.read_only for spec in profile.PERSONAL_READ_TOOL_SPECS)
    assert all(spec.annotations["readOnlyHint"] is True for spec in profile.PERSONAL_READ_TOOL_SPECS)
    assert all(spec.annotations["destructiveHint"] is False for spec in profile.PERSONAL_READ_TOOL_SPECS)
    assert profile.personal_read_schema_snapshot_sha256() == profile.PERSONAL_READ_SCHEMA_SNAPSHOT_SHA256


def test_personal_read_builder_has_no_submission_owner_imports():
    import integrations.executive_mcp.server as server

    source = inspect.getsource(server.build_personal_read_mcp_app)
    for forbidden in (
        "compose_admission",
        "reconcile_by_request_ref",
        "app_request_ref",
        "build_executive_mcp_app",
        "make_jwt_authenticators",
        "submit_ceo_intent",
    ):
        assert forbidden not in source


def test_installed_selector_accepts_personal_without_expanding_old_validator():
    from integrations.executive_mcp import web_ceo as v2
    from integrations.executive_mcp import web_ceo_v3 as current

    assert current.validate_installed_mcp_profile_current("personal_read") == "personal_read"
    with pytest.raises(ValueError):
        v2.validate_installed_mcp_profile("personal_read")


def test_installed_network_config_accepts_personal_and_refuses_optional_mounts():
    from ops.executive_os import executive_mcp_entry as entry

    raw = {
        "schema": "mastermind.executive_mcp_install.v1",
        "release_sha": "a" * 40,
        "service_uid": 458,
        "ceo_ingress_socket_path": "/var/run/mastermind-executive/ceo-ingress.sock",
        "port": 8444,
        "policies": {},
        "audit_root": "/var/log/mastermind-executive/mcp-auth",
        "executive_mcp_profile": "personal_read",
    }
    assert entry.validate_document(dict(raw)) == raw
    with pytest.raises(ValueError, match="refuses optional mounts"):
        entry.validate_document({**raw, "workspace": {}})
    with pytest.raises(ValueError, match="refuses optional mounts"):
        entry.validate_document({**raw, "steward": {}})


def test_personal_read_mcp_uses_only_v1_ceo_ingress_and_has_no_write_route(tmp_path, monkeypatch):
    auth = _auth_fixture()
    import httpx
    from control_plane import executive_ceo_ingress
    from integrations.executive_mcp import personal_read as profile
    from integrations.executive_mcp import schemas as legacy
    import integrations.executive_mcp.server as server
    from integrations.mastermind_executive_app.app import AppSettings
    import integrations.mastermind_executive_app.gateway as gateway_module
    from integrations.mastermind_executive_app.gateway import AppPolicies

    class Sink:
        def emit(self, _event: Any) -> None:
            pass

    frames: list[dict[str, Any]] = []

    class FakeClient:
        def __init__(self, *, connect_timeout: float, read_timeout: float) -> None:
            assert connect_timeout == 5.0
            assert read_timeout == 10.0

        async def send_frame(self, socket_path: Any, frame: dict[str, Any]):
            assert str(socket_path) == "/tmp/personal-ceo-ingress.sock"
            frames.append(dict(frame))
            result = legacy.result_envelope(
                frame["tool"],
                mode=legacy.ServerMode.READONLY,
                generated_at="2026-09-24T11:45:00Z",
                data={"source": "installed-v1"},
            )
            return gateway_module.CeoIngressResponse(
                transport=gateway_module.TRANSPORT_SENT_OK,
                ok=True,
                result=result,
            )

    monkeypatch.setattr(gateway_module, "CeoIngressClient", FakeClient)
    key = auth.rsa_key.__wrapped__()
    settings = AppSettings(
        policies=AppPolicies(read=auth._read_policy(), submit=auth._submit_policy()),
        mastermind_root=tmp_path / "unused-source",
        macro_root_flag=None,
        environ={},
        ceo_ingress_socket_path="/tmp/personal-ceo-ingress.sock",
        read_from_ceo_ingress=True,
        jwks_cache=auth._FakeJwksCache(key),
        clock=lambda: auth.NOW,
    )
    app = server.build_personal_read_mcp_app(settings, audit_sink=Sink())

    async def exercise() -> None:
        outer = app._app
        async with outer.router.lifespan_context(outer):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1"
            ) as client:
                metadata = await client.get(auth.METADATA_PATH)
                assert metadata.status_code == 200
                serialized_metadata = json.dumps(metadata.json(), sort_keys=True)
                assert "mastermind.executive.read" in serialized_metadata
                assert "mastermind.executive.intent.submit" not in serialized_metadata

                headers = {
                    "authorization": f"Bearer {auth._read_token(key)}",
                    "accept": "application/json, text/event-stream",
                    "mcp-protocol-version": "2025-06-18",
                }
                initialized = await client.post(
                    "/mcp",
                    headers=headers,
                    json={
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "initialize",
                        "params": {
                            "protocolVersion": "2025-06-18",
                            "capabilities": {},
                            "clientInfo": {"name": "test", "version": "1"},
                        },
                    },
                )
                assert initialized.status_code == 200
                assert initialized.json()["result"]["serverInfo"] == {
                    "name": profile.PERSONAL_READ_SERVER_NAME,
                    "version": profile.PERSONAL_READ_SERVER_VERSION,
                }
                listed = await client.post(
                    "/mcp",
                    headers=headers,
                    json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
                )
                assert listed.status_code == 200
                tools = listed.json()["result"]["tools"]
                assert [tool["name"] for tool in tools] == list(profile.PERSONAL_READ_TOOL_NAMES)
                assert all(tool["annotations"]["readOnlyHint"] is True for tool in tools)
                assert all(tool["annotations"]["destructiveHint"] is False for tool in tools)
                assert "submit_ceo_intent" not in json.dumps(tools)

                cases = (
                    (3, "executive_state", {}),
                    (4, "executive_inbox", {}),
                    (5, "executive_job", {"job_id": "JOB-1"}),
                    (6, "ceo_intent_status", {"intent_id": "INTENT-A"}),
                )
                for request_id, name, arguments in cases:
                    called = await client.post(
                        "/mcp",
                        headers=headers,
                        json={
                            "jsonrpc": "2.0",
                            "id": request_id,
                            "method": "tools/call",
                            "params": {"name": name, "arguments": arguments},
                        },
                    )
                    assert called.status_code == 200, called.text
                    envelope = json.loads(called.json()["result"]["content"][0]["text"])
                    assert envelope["ok"] is True
                    assert envelope["tool"] == name
                    assert envelope["server_version"] == profile.PERSONAL_READ_SERVER_VERSION
                    assert envelope["data"] == {"source": "installed-v1"}

                assert [frame["tool"] for frame in frames] == list(profile.PERSONAL_READ_TOOL_NAMES)
                assert all(
                    frame["schema"] == executive_ceo_ingress.APP_READ_SCHEMA for frame in frames
                )

                before = list(frames)
                denied = await client.post(
                    "/mcp",
                    headers=headers,
                    json={
                        "jsonrpc": "2.0",
                        "id": 7,
                        "method": "tools/call",
                        "params": {"name": "submit_ceo_intent", "arguments": {}},
                    },
                )
                assert denied.status_code == 200
                denied_payload = json.loads(
                    denied.json()["result"]["content"][0]["text"]
                )
                assert denied_payload["ok"] is False
                assert denied_payload["error"]["code"] == "not_found"
                assert frames == before

                assert (
                    await client.post(
                        "/v1/tools/submit_ceo_intent", headers=headers, json={}
                    )
                ).status_code == 404
                assert (
                    await client.post(
                        "/v1/tools/submit_ceo_intent/reconcile", headers=headers, json={}
                    )
                ).status_code == 404
                assert frames == before

    asyncio.run(exercise())
