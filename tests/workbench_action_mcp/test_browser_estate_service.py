import asyncio
from dataclasses import asdict, replace
import json
from pathlib import Path
import tempfile

import pytest

from integrations.workbench_action_mcp import service
from integrations.workbench_action_mcp.contracts import ActionCaller
from integrations.mastermind_browser_plugin.workbench_estate import WorkbenchEstateComposition
from tests.workbench_action_mcp.test_browser_link_service import configuration
from tests.test_mastermind_browser_workbench_transport import Host


def test_v4_normal_service_lifespan_opens_estate_without_contacting_offline_route(tmp_path, monkeypatch):
    with tempfile.TemporaryDirectory(prefix="mmx-estate-", dir="/tmp") as directory:
        config, grant, _native, document = configuration(tmp_path, Path(directory))
        remote = Host("remote")
        route_path = tmp_path / "routes.json"
        route_path.write_text(json.dumps({"schema": "mastermind.browser_fabric_routes.v1", "routes": [
            {**asdict(remote.route), "credential_file": str(tmp_path / "absent-owner-credential.json")}]}))
        route_path.chmod(0o600)
        document.update(schema=service.SERVICE_SCHEMA_V4, browser_fabric_routes_file=str(route_path))
        config = service.parse_service_config(document)
        created = []
        original = service.create_browser_fabric_sibling
        def capture(*args, **kwargs):
            result = original(*args, **kwargs)
            created.append(result)
            return result
        monkeypatch.setattr(service, "create_browser_fabric_sibling", capture)
        async def exercise():
            runtime = await service.create_runtime(config)
            state = service.ServiceState()
            app = service.build_service_app(runtime, config, state)
            estate = created[0].composition
            assert type(estate) is WorkbenchEstateComposition
            assert len(estate.transports) == 1 and not estate.transports[0]._opened
            outer = ActionCaller("e" * 64, "outer-client", "https://browser.example/mcp",
                                 ("browser.control",), config.lease.lease_expires_at_ms // 1000)
            async with app.router.lifespan_context(app):
                assert state.lifespan_started and estate.transports[0]._opened
                assert state.browser_activation
                # Missing outgoing credential degrades that host; no socket,
                # token issuance or alternate endpoint is attempted.
                fleet = await estate.owner.browser_fleet(outer, {"limit": 10})
                assert fleet["observation_status"] == "partial"
                assert next(row for row in fleet["hosts"] if row["host_ref"] == "remote")["status"] == "unavailable"
            assert not estate.transports[0]._opened and not estate.transports[0]._active
            assert state.runtime_close_attempted and state.lifespan_completed
        asyncio.run(exercise())


def test_v4_route_configuration_is_closed_and_v3_cannot_smuggle_routes(tmp_path):
    with tempfile.TemporaryDirectory(prefix="mmx-estate-config-", dir="/tmp") as directory:
        _config, _grant, _native, document = configuration(tmp_path, Path(directory))
        upgraded = {**document, "schema": service.SERVICE_SCHEMA_V4,
                    "browser_fabric_routes_file": str(tmp_path / "routes.json")}
        assert service.parse_service_config(upgraded).browser_fabric_routes_file == upgraded["browser_fabric_routes_file"]
        for invalid in (
            {**upgraded, "browser_fabric_routes_file": None},
            {**upgraded, "browser_fabric_routes_file": "relative.json"},
            {**upgraded, "schema": service.SERVICE_SCHEMA_V3},
            {key: value for key, value in upgraded.items() if key != "browser_fabric_routes_file"},
            {**upgraded, "remote_url": "https://unreviewed.test/mcp"},
        ):
            with pytest.raises(service.ServiceConfigurationError):
                service.parse_service_config(invalid)
