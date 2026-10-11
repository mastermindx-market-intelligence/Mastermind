from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest
from starlette.testclient import TestClient

import integrations.workbench_action_mcp.service as service
from tests.workbench_action_mcp.test_service import _document


def _browser_block(tmp_path: Path) -> dict[str, object]:
    roots = {}
    for name in ("source", "relay", "output", "home", "tmp"):
        path = tmp_path / name
        path.mkdir(mode=0o700)
        os.chmod(path, 0o700)
        roots[name] = str(path)
    catalog = tmp_path / "catalog.json"
    catalog.write_text(json.dumps({"tools": []}), encoding="utf-8")
    os.chmod(catalog, 0o600)
    return {
        "source_root": roots["source"],
        "python_executable": "/usr/bin/python3",
        "node_executable": "/opt/homebrew/bin/node",
        "mcp_cli_path": "/tmp/mcp/node_modules/@playwright/mcp/cli.js",
        "chrome_executable": "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "relay_root": roots["relay"],
        "output_root": roots["output"],
        "home_dir": roots["home"],
        "tmp_dir": roots["tmp"],
        "tool_catalog_file": str(catalog),
        "startup_timeout_seconds": 10.0,
    }


def test_v1_service_config_remains_action_only(tmp_path: Path):
    document, _, _ = _document(tmp_path)
    selected = service.parse_service_config(document)
    assert selected.schema == service.SERVICE_SCHEMA
    assert selected.browser is None


def test_v2_service_config_adds_one_closed_browser_sibling(tmp_path: Path):
    document, _, _ = _document(tmp_path)
    document["schema"] = service.SERVICE_SCHEMA_V2
    document["browser"] = _browser_block(tmp_path)
    selected = service.parse_service_config(document)
    assert selected.schema == service.SERVICE_SCHEMA_V2
    assert selected.browser is not None
    assert selected.browser.mount_path == "/browser"
    assert selected.browser.tool_catalog_file.endswith("/catalog.json")


@pytest.mark.parametrize(
    "mutate",
    [
        lambda b: b.update({"profile_dir": "/tmp/ambient-profile"}),
        lambda b: b.update({"mount_path": "/custom"}),
        lambda b: b.update({"node_executable": "node"}),
        lambda b: b.update({"startup_timeout_seconds": 0}),
    ],
)
def test_v2_browser_config_is_closed_and_host_selected(tmp_path: Path, mutate):
    document, _, _ = _document(tmp_path)
    document["schema"] = service.SERVICE_SCHEMA_V2
    block = _browser_block(tmp_path)
    mutate(block)
    document["browser"] = block
    with pytest.raises(service.ServiceConfigurationError):
        service.parse_service_config(document)


def test_v1_rejects_browser_block_instead_of_silently_widening(tmp_path: Path):
    document, _, _ = _document(tmp_path)
    document["browser"] = _browser_block(tmp_path)
    with pytest.raises(service.ServiceConfigurationError):
        service.parse_service_config(document)


def test_browser_sibling_reuses_exact_existing_runtime_services(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    document, _, _ = _document(tmp_path)
    document["schema"] = service.SERVICE_SCHEMA_V2
    document["browser"] = _browser_block(tmp_path)
    selected = service.parse_service_config(document)
    captured = {}

    import integrations.workbench_browser_mcp.deployment as browser_deployment

    def fake_create_browser_deployment(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(server=object())

    monkeypatch.setattr(
        browser_deployment,
        "create_browser_deployment",
        fake_create_browser_deployment,
    )

    async def exercise():
        runtime = await service.create_runtime(selected)
        try:
            sibling = service.create_browser_sibling(runtime, selected)
            assert sibling is not None
            assert captured["services"] is runtime.services
            assert captured["profile_resolver"]("any-profile") is None
            assert captured["host_config"].source_root == Path(
                selected.browser.source_root
            )
        finally:
            runtime.revoke()
            await runtime.aclose(timeout=5.0)

    asyncio.run(exercise())


def test_service_routes_keep_action_root_and_add_fixed_browser_sibling(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    document, _, _ = _document(tmp_path)
    document["schema"] = service.SERVICE_SCHEMA_V2
    document["browser"] = _browser_block(tmp_path)
    selected = service.parse_service_config(document)

    class FakeManager:
        def run(self):
            raise AssertionError("route inspection must not enter lifespan")

    class FakeBrowserServer:
        session_manager = FakeManager()

        def streamable_http_app(self):
            async def app(scope, receive, send):
                raise AssertionError("route inspection only")
            return app

    fake = SimpleNamespace(server=FakeBrowserServer())
    monkeypatch.setattr(service, "create_browser_sibling", lambda runtime, config: fake)

    async def exercise():
        runtime = await service.create_runtime(selected)
        try:
            app = service.build_service_app(runtime, selected, service.ServiceState())
            assert [route.path for route in app.routes] == [
                "/healthz",
                "/readyz",
                "/browser",
                "",
            ]
            assert app.routes[2].app is not None
        finally:
            runtime.revoke()
            await runtime.aclose(timeout=5.0)

    asyncio.run(exercise())


def test_v1_service_routes_remain_without_browser_mount(tmp_path: Path):
    document, _, _ = _document(tmp_path)
    selected = service.parse_service_config(document)

    async def exercise():
        runtime = await service.create_runtime(selected)
        try:
            app = service.build_service_app(runtime, selected, service.ServiceState())
            assert [route.path for route in app.routes] == [
                "/healthz",
                "/readyz",
                "",
            ]
        finally:
            runtime.revoke()
            await runtime.aclose(timeout=5.0)

    asyncio.run(exercise())


def test_real_browser_mount_reaches_companion_auth_boundary(tmp_path: Path):
    document, _, _ = _document(tmp_path)
    document["schema"] = service.SERVICE_SCHEMA_V2
    block = _browser_block(tmp_path)
    root = Path(__file__).resolve().parents[2]
    block["source_root"] = str(root)
    block["python_executable"] = sys.executable
    block["tool_catalog_file"] = str(
        root / "research" / "evidence" / "claude_browser_mcp_tools_0_0_79.json"
    )
    document["browser"] = block
    selected = service.parse_service_config(document)

    async def make():
        runtime = await service.create_runtime(selected)
        app = service.build_service_app(runtime, selected, service.ServiceState())
        return runtime, app

    runtime, app = asyncio.run(make())
    try:
        with TestClient(app) as client:
            payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-03-26",
                    "capabilities": {},
                    "clientInfo": {"name": "route-probe", "version": "1"},
                },
            }
            action = client.post(
                "/mcp",
                json=payload,
                headers={"Accept": "application/json, text/event-stream"},
            )
            browser = client.post(
                "/browser/mcp",
                json={**payload, "id": 2},
                headers={"Accept": "application/json, text/event-stream"},
            )
            assert action.status_code in {401, 403}
            assert browser.status_code in {401, 403}
            assert browser.status_code != 404
    finally:
        if not getattr(runtime, "_closed", False):
            runtime.revoke()
            asyncio.run(runtime.aclose(timeout=5.0))
