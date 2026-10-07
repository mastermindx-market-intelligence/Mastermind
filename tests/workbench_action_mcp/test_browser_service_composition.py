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


def test_browser_fabric_sibling_reuses_same_deployment_key_and_lease_broker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    document, _, _ = _document(tmp_path)
    document["schema"] = service.SERVICE_SCHEMA_V2
    document["browser"] = _browser_block(tmp_path)
    selected = service.parse_service_config(document)
    captured = {}
    deployment = SimpleNamespace()

    import integrations.mastermind_browser_plugin.workbench_service as browser_fabric

    def fake_create(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(app=object(), owner=object())

    monkeypatch.setattr(
        browser_fabric,
        "create_workbench_browser_fabric_http_app",
        fake_create,
    )

    async def authenticate(_request):
        return None

    async def exercise():
        runtime = await service.create_runtime(selected)
        try:
            sibling = service.create_browser_fabric_sibling(
                runtime,
                selected,
                deployment,
                authenticate=authenticate,
                auth_challenge='Bearer resource_metadata="https://browser.test/meta"',
            )
            assert sibling is not None
            assert captured["deployment"] is deployment
            assert captured["action_token_key"] == runtime.services.action_token_key
            assert captured["clock_ms"] is runtime.services.clock_ms
            assert captured["caller_binding"] is browser_fabric.browser_caller_binding_from_action_caller
            assert captured["broker_caller"].subject_digest == selected.lease.expected_subject_digest
            assert captured["broker_caller"].client_ref == selected.lease.expected_client_ref
            assert captured["broker_caller"].resource == selected.lease.resource
            assert captured["broker_caller"].scopes == selected.lease.required_scopes
            assert captured["allowed_hosts"] == list(runtime.services.allowed_hosts)
            assert captured["allowed_origins"] == runtime.services.allowed_origins
        finally:
            runtime.revoke()
            await runtime.aclose(timeout=5.0)

    asyncio.run(exercise())


def test_service_routes_add_browser_fabric_only_with_explicit_auth(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    from starlette.applications import Starlette
    from starlette.responses import PlainTextResponse
    from starlette.routing import Route

    document, _, _ = _document(tmp_path)
    document["schema"] = service.SERVICE_SCHEMA_V2
    document["browser"] = _browser_block(tmp_path)
    selected = service.parse_service_config(document)

    class FakeManager:
        def run(self):
            raise AssertionError("route inspection must not enter low-level lifespan")

    class FakeBrowserServer:
        session_manager = FakeManager()

        def streamable_http_app(self):
            async def app(scope, receive, send):
                raise AssertionError("route inspection only")
            return app

    low = SimpleNamespace(server=FakeBrowserServer())
    monkeypatch.setattr(service, "create_browser_sibling", lambda runtime, config: low)

    async def endpoint(_request):
        return PlainTextResponse("browser-fabric")

    high_app = Starlette(routes=[Route("/browser-fabric", endpoint, methods=["POST"])])
    high = SimpleNamespace(app=high_app)
    captured = {}

    def fake_high(runtime, config, deployment, **kwargs):
        captured["runtime"] = runtime
        captured["config"] = config
        captured["deployment"] = deployment
        captured.update(kwargs)
        return high

    monkeypatch.setattr(service, "create_browser_fabric_sibling", fake_high)

    async def authenticate(_request):
        return None

    async def exercise():
        runtime = await service.create_runtime(selected)
        try:
            without = service.build_service_app(
                runtime,
                selected,
                service.ServiceState(),
            )
            assert [route.path for route in without.routes] == [
                "/healthz",
                "/readyz",
                "/browser",
                "",
            ]

            with_fabric = service.build_service_app(
                runtime,
                selected,
                service.ServiceState(),
                browser_fabric_authenticate=authenticate,
                browser_fabric_auth_challenge="Bearer synthetic",
            )
            assert [route.path for route in with_fabric.routes] == [
                "/healthz",
                "/readyz",
                "/browser",
                "/browser-fabric",
                "",
            ]
            assert captured["runtime"] is runtime
            assert captured["config"] is selected
            assert captured["deployment"] is low
            assert captured["authenticate"] is authenticate
            assert captured["auth_challenge"] == "Bearer synthetic"
        finally:
            runtime.revoke()
            await runtime.aclose(timeout=5.0)

    asyncio.run(exercise())


def test_service_refuses_partial_browser_fabric_auth_configuration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    document, _, _ = _document(tmp_path)
    document["schema"] = service.SERVICE_SCHEMA_V2
    document["browser"] = _browser_block(tmp_path)
    selected = service.parse_service_config(document)
    fake = SimpleNamespace(
        server=SimpleNamespace(
            streamable_http_app=lambda: object(),
            session_manager=SimpleNamespace(),
        )
    )
    monkeypatch.setattr(service, "create_browser_sibling", lambda runtime, config: fake)

    async def authenticate(_request):
        return None

    async def exercise():
        runtime = await service.create_runtime(selected)
        try:
            with pytest.raises(service.ServiceConfigurationError):
                service.build_service_app(
                    runtime,
                    selected,
                    service.ServiceState(),
                    browser_fabric_authenticate=authenticate,
                )
            with pytest.raises(service.ServiceConfigurationError):
                service.build_service_app(
                    runtime,
                    selected,
                    service.ServiceState(),
                    browser_fabric_auth_challenge="Bearer synthetic",
                )
        finally:
            runtime.revoke()
            await runtime.aclose(timeout=5.0)

    asyncio.run(exercise())


def test_real_browser_fabric_mount_initializes_seven_tool_service(
    tmp_path: Path,
):
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

    from integrations.workbench_action_mcp.contracts import ActionCaller

    outer = ActionCaller(
        subject_digest="e" * 64,
        client_ref="browser-fixture-client",
        resource="browser-resource",
        scopes=("browser.control",),
        expires_at=2_000_000_000,
    )

    async def authenticate(request):
        if request.headers.get("x-browser-fixture") == "outer":
            return outer
        return None

    async def make():
        runtime = await service.create_runtime(selected)
        app = service.build_service_app(
            runtime,
            selected,
            service.ServiceState(),
            browser_fabric_authenticate=authenticate,
            browser_fabric_auth_challenge='Bearer realm="mastermind-browser-test"',
        )
        return runtime, app

    runtime, app = asyncio.run(make())
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-11-25",
            "capabilities": {},
            "clientInfo": {"name": "browser-fabric-route", "version": "1"},
        },
    }
    headers = {
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
        "x-browser-fixture": "outer",
    }
    try:
        with TestClient(
            app,
            base_url=f"http://{selected.incoming_authority}",
        ) as client:
            denied = client.post("/browser-fabric", json=payload)
            assert denied.status_code == 401
            initialized = client.post(
                "/browser-fabric",
                json=payload,
                headers=headers,
            )
            assert initialized.status_code == 200, initialized.text
            assert (
                initialized.json()["result"]["serverInfo"]["name"]
                == "mastermind-browser"
            )
            tools = client.post(
                "/browser-fabric",
                headers=headers,
                json={
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/list",
                },
            )
            assert tools.status_code == 200
            assert len(tools.json()["result"]["tools"]) == 7
            fleet = client.post(
                "/browser-fabric",
                headers=headers,
                json={
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "tools/call",
                    "params": {
                        "name": "browser_fleet",
                        "arguments": {"limit": 10},
                    },
                },
            )
            assert fleet.status_code == 200
            assert (
                fleet.json()["result"]["structuredContent"]["data"]["browsers"]
                == []
            )
            assert client.post("/browser-fabric-extra", json=payload).status_code == 404
    finally:
        if not getattr(runtime, "_closed", False):
            runtime.revoke()
            asyncio.run(runtime.aclose(timeout=5.0))
