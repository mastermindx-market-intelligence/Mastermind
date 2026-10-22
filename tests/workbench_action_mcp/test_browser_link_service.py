"""Normal service configuration, real relay/native processes, exact public tabs."""
import asyncio
from dataclasses import replace
import json
import os
from pathlib import Path
import sys
import tempfile
import threading

import pytest

from control_plane.codex_worker import ProcessInspector
from integrations.mastermind_browser_link.native_channel import LinkEnrollment, INVENTORY_SCHEMA
from integrations.mastermind_browser_link.profile_grant import LinkProfileGrant, PROFILES_SCHEMA
from integrations.mastermind_browser_link.tool_contract import LINK_TOOL_SCHEMA_DIGEST
from integrations.mastermind_browser_plugin.workbench_service import (
    browser_broker_caller_from_lease, browser_caller_binding_from_action_caller,
)
from integrations.mastermind_browser_plugin.workbench_composition import compose_browser_owner_from_workbench
from integrations.workbench_action_mcp import service
from integrations.workbench_action_mcp.contracts import ActionCaller
from tests.test_mastermind_browser_link_native import Peer
from tests.workbench_action_mcp.test_browser_fabric_startup import _v3_document


def configuration(tmp_path, short_root):
    document, _ = _v3_document(tmp_path)
    root = Path(__file__).resolve().parents[2]
    relay = short_root / "relay"
    native = short_root / "native"
    relay.mkdir(mode=0o700)
    native.mkdir(mode=0o700)
    lease = document["lease"]
    chrome = ProcessInspector().inspect(os.getpid())
    enrollment = LinkEnrollment("a" * 32, "b" * 64, native / "browser.sock")
    grant = LinkProfileGrant.create(
        owner_ref=lease["owner_ref"], operation_ref=lease["operation_ref"],
        generation=lease["generation"], host_id=document["host_id"],
        boot_session_id=ProcessInspector().boot_session_id(),
        expires_at_ms=lease["lease_expires_at_ms"], exclusive=True,
        enrollment=enrollment, chrome_pid=os.getpid(), chrome_start_identity=chrome.start_identity,
    )
    profiles = short_root / "profiles.json"
    profiles.write_text(json.dumps({"schema": PROFILES_SCHEMA, "profiles": [grant.document()]}))
    profiles.chmod(0o600)
    native_config = native / "enrollment.json"
    native_config.write_text(json.dumps(enrollment.document()))
    native_config.chmod(0o600)
    document["max_concurrency"] = 4
    document["io_timeout_seconds"] = 10.0
    document["browser"] = {
        "schema": "mastermind.workbench_browser_link_service.v1",
        "source_root": str(root), "python_executable": sys.executable,
        "relay_root": str(relay), "output_root": str(tmp_path / "output"),
        "startup_timeout_seconds": 5, "profiles_file": str(profiles),
    }
    return service.parse_service_config(document), grant, native_config, document


def test_actual_service_factory_subprocess_and_two_tab_public_actions(tmp_path):
    with tempfile.TemporaryDirectory(prefix="mmx-link-service-", dir="/tmp") as directory:
        config, grant, native_config, _ = configuration(tmp_path, Path(directory))
        async def exercise():
            runtime = await service.create_runtime(config)
            deployment = service.create_browser_sibling(runtime, config)
            # No injected relay builder, profile resolver or backend digest.
            app = service.build_service_app(runtime, config, service.ServiceState())
            assert "/browser-fabric" in [route.path for route in app.routes]
            caller = browser_broker_caller_from_lease(config.lease)
            peer = None
            browser_ref = None
            reader = None
            errors = []
            commands = []
            try:
                start_ref = await deployment.prepare_resource(caller, config.lease.project_ref, "extension", grant.profile_ref)
                started = await deployment.start_resource(caller, start_ref)
                assert started["effect_state"] == "APPLIED", started
                browser_ref = started["browser_ref"]
                peer = Peer(grant.enrollment, native_config)
                peer.ready()
                rows = [{"tab_id": tab, "origin": "https://example.test", "consent_id": f"consent-{tab}",
                         "document_revision": 0, "state": "shared"} for tab in (7, 8)]
                def serve_native():
                    writes = []
                    try:
                        while True:
                            message = peer.receive()
                            if message["schema"] == "mastermind.browser_link.observe.v1":
                                peer.send({"schema": INVENTORY_SCHEMA, "request_id": message["request_id"],
                                           "connection_generation": peer.generation, "shared_tabs": rows})
                            else:
                                commands.append(message)
                                if message["command"] in {"snapshot", "screenshot"}:
                                    peer.result(message, effect="NOT_APPLIED", output={"nodes": []})
                                else:
                                    writes.append(message)
                                    # Neither write gets a reply until both crossed the
                                    # real resource relay and native channel concurrently.
                                    if len(writes) == 2:
                                        for command in writes:
                                            peer.result(command, output={"scrolled": True})
                    except Exception as exc:
                        errors.append(type(exc).__name__)
                reader = threading.Thread(target=serve_native, daemon=True)
                reader.start()
                composition = compose_browser_owner_from_workbench(
                    deployment=deployment, signing_key=b"o" * 32, clock_ms=runtime.services.clock_ms,
                    caller_binding=browser_caller_binding_from_action_caller, broker_caller=caller,
                    expected_backend_schema_digest=service._browser_backend_digest(config.browser),
                )
                owner = composition.owner
                outer = ActionCaller(subject_digest="e" * 64, client_ref="outer-agent",
                                     resource="https://browser.example/mcp", scopes=("browser.control",),
                                     expires_at=caller.expires_at)
                fleet = await owner.browser_fleet(outer, {"limit": 10})
                assert len(fleet["browsers"]) == 1
                tabs = (await owner.browser_tabs(outer, {"browser_ref": fleet["browsers"][0]["browser_ref"]}))["tabs"]
                assert len(tabs) == 2
                assert tabs[0]["tab_ref"] != tabs[1]["tab_ref"]
                read = await owner.browser_snapshot(outer, {"tab_ref": tabs[0]["tab_ref"]})
                assert read["isError"] is False
                prepared = [await owner.prepare_browser_action(outer, {
                    "tab_ref": tab["tab_ref"], "action": "scroll", "args": {"delta_x": 0, "delta_y": 100}
                }) for tab in tabs]
                results = await asyncio.gather(*[
                    owner.run_browser_action(outer, {"tab_ref": tab["tab_ref"], "action_ref": action["action_ref"]})
                    for tab, action in zip(tabs, prepared)
                ])
                assert [result["effect"] for result in results] == ["APPLIED", "APPLIED"], results
                mutations = [command for command in commands if command["command"] == "scroll"]
                assert {command["tab_id"] for command in mutations} == {7, 8}
                assert len(mutations) == 2
                repeated = await owner.run_browser_action(outer, {
                    "tab_ref": tabs[0]["tab_ref"], "action_ref": prepared[0]["action_ref"]})
                assert repeated["effect"] == "APPLIED"
                assert len([command for command in commands if command["command"] == "scroll"]) == 2
                assert errors == []
            finally:
                if browser_ref is not None:
                    cleanup = await deployment.cleanup_resource(browser_ref, owner_state="released", effect_state="APPLIED")
                    assert cleanup["released"] is True
                if peer is not None:
                    peer.close()
                if reader is not None:
                    reader.join(timeout=6)
                runtime.revoke()
                await runtime.aclose(timeout=5)
            assert not grant.enrollment.socket_path.exists()
        asyncio.run(exercise())


def test_link_profile_ref_cannot_be_remapped(tmp_path):
    with tempfile.TemporaryDirectory(prefix="mmx-link-grant-", dir="/tmp") as directory:
        _config, grant, _native, _document = configuration(tmp_path, Path(directory))
        assert LinkProfileGrant.from_document(grant.document()) == grant
        for name, value in (("chrome_pid", os.getpid() + 1), ("generation", "other-generation"),
                            ("chrome_start_identity", "other-start")):
            changed = grant.document()
            changed[name] = value
            with pytest.raises(ValueError):
                LinkProfileGrant.from_document(changed)


def test_link_configuration_cannot_be_silently_used_as_legacy_v2(tmp_path):
    with tempfile.TemporaryDirectory(prefix="mmx-link-config-", dir="/tmp") as directory:
        _config, _grant, _native, document = configuration(tmp_path, Path(directory))
        document["schema"] = service.SERVICE_SCHEMA_V2
        document.pop("browser_fabric_policy_file")
        document.pop("browser_fabric_audit_directory")
        with pytest.raises(service.ServiceConfigurationError):
            service.parse_service_config(document)
