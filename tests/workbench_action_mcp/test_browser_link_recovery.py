"""Actual owner processes recover original Link resource evidence across restarts."""
import asyncio
from dataclasses import fields, replace
import json
import os
from pathlib import Path
import select
import signal
import subprocess
import sys
import tempfile
import threading
import time

import pytest

from integrations.mastermind_browser_link.native_channel import LinkEnrollment, INVENTORY_SCHEMA
from integrations.mastermind_browser_link.profile_grant import LinkProfileGrant, PROFILES_SCHEMA
from integrations.mastermind_browser_plugin.workbench_composition import compose_browser_owner_from_workbench
from integrations.mastermind_browser_plugin.workbench_service import (
    browser_broker_caller_from_lease, browser_caller_binding_from_action_caller,
)
from integrations.workbench_action_mcp import action_artifacts as artifacts, service
from integrations.workbench_action_mcp.contracts import ActionCaller
from integrations.workbench_browser_mcp.contracts import BrowserRefCodec
from tests.test_mastermind_browser_link_native import Peer
from tests.workbench_action_mcp.test_browser_link_service import configuration

ROOT = Path(__file__).resolve().parents[2]
OWNER_PROGRAM = r'''
import asyncio,json,sys
from integrations.workbench_action_mcp import service
from integrations.mastermind_browser_plugin.workbench_service import browser_broker_caller_from_lease
async def main():
    config=service.load_service_config(sys.argv[1])
    runtime=await service.create_runtime(config)
    deployment=service.create_browser_sibling(runtime,config)
    service.create_browser_sibling=lambda *_:deployment
    state=service.ServiceState()
    app=service.build_service_app(runtime,config,state)
    caller=browser_broker_caller_from_lease(config.lease)
    async with app.router.lifespan_context(app):
        resources=await deployment.observe_active_resources(caller)
        print(json.dumps({"activation":state.browser_activation,
                          "resources":[{"browser_ref":row.browser_ref,"pid":row.resource.relay_pid,
                                        "start_id":row.resource.start_action_id} for row in resources]}),flush=True)
        command=await asyncio.to_thread(sys.stdin.readline)
        if command.strip()=="close":
            for row in resources:
                await deployment.cleanup_resource(row.browser_ref,owner_state="released",effect_state="APPLIED")
asyncio.run(main())
'''


def altered_grant(grant, **changes):
    values = {field.name: getattr(grant, field.name) for field in fields(grant) if field.name != "profile_ref"}
    return LinkProfileGrant.create(**{**values, **changes})


def save_document(path, value):
    path.write_text(json.dumps(value))
    path.chmod(0o600)


def start_owner(config_path):
    child = subprocess.Popen([sys.executable, "-c", OWNER_PROGRAM, str(config_path)], cwd=ROOT,
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             text=True, bufsize=1)
    try:
        assert select.select([child.stdout], [], [], 15)[0], "owner did not finish initial activation"
        line = child.stdout.readline()
        if not line:
            raise AssertionError(child.stderr.read(12000))
        return child, json.loads(line)
    except BaseException:
        child.kill()
        child.wait(timeout=5)
        raise


def close_owner(child):
    if child.poll() is None:
        child.stdin.write("close\n")
        child.stdin.flush()
        child.wait(timeout=12)
    assert child.returncode == 0, child.stderr.read(12000)
    child.stdin.close()
    child.stdout.close()
    child.stderr.close()


def crash_owner_and_relay(child, receipt):
    relay_pid = receipt["resources"][0]["pid"]
    os.killpg(relay_pid, signal.SIGKILL)
    child.kill()
    child.wait(timeout=5)
    deadline = time.monotonic() + 8
    while True:
        try:
            os.killpg(relay_pid, 0)
        except ProcessLookupError:
            break
        if time.monotonic() >= deadline:
            raise AssertionError("test relay process group did not disappear")
        time.sleep(0.02)
    child.stdin.close()
    child.stdout.close()
    child.stderr.close()


def test_three_actual_owner_epochs_recover_orphan_socket_without_rewriting_old_receipts(tmp_path):
    with tempfile.TemporaryDirectory(prefix="mmx-restart-", dir="/tmp") as directory:
        _config, grant, _native, document = configuration(tmp_path, Path(directory))
        config_path = tmp_path / "service.json"
        save_document(config_path, document)
        receipts = []
        original_results = {}
        child = None
        try:
            for epoch in range(3):
                child, receipt = start_owner(config_path)
                assert receipt["activation"][0]["status"] == "active", receipt
                assert len(receipt["resources"]) == 1
                resource = receipt["resources"][0]
                receipts.append(resource)
                result_path = Path(document["artifact_directory"]) / (resource["start_id"] + ".result")
                original_results[result_path] = result_path.read_bytes()
                assert grant.enrollment.socket_path.exists()
                if epoch < 2:
                    crash_owner_and_relay(child, receipt)
                    child = None
                    assert grant.enrollment.socket_path.exists(), "SIGKILL fixture must leave an orphan"
            assert len({row["start_id"] for row in receipts}) == 3
            assert len({row["pid"] for row in receipts}) == 3
            for path, original in original_results.items():
                assert path.read_bytes() == original
        finally:
            if child is not None:
                close_owner(child)
        assert not grant.enrollment.socket_path.exists()


@pytest.mark.parametrize("state", ["pending", "unknown", "unmapped"])
def test_old_page_uncertainty_blocks_new_owner_without_unlink_or_replay(tmp_path, state):
    with tempfile.TemporaryDirectory(prefix="mmx-history-", dir="/tmp") as directory:
        _config, grant, _native, document = configuration(tmp_path, Path(directory))
        config_path = tmp_path / "service.json"
        save_document(config_path, document)
        first, receipt = start_owner(config_path)
        resource = receipt["resources"][0]
        artifact_root = Path(document["artifact_directory"])
        fd = os.open(artifact_root, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
        try:
            store = artifacts.adopt_artifact_store(fd)
            original = artifacts.classify_named_action(store, resource["start_id"]).claim.identity
            action = replace(original, action_id="e" * 32, purpose="browser_action",
                             relative_path=f"browser:{resource['start_id']}:browser_link_action")
            with artifacts.acquire_store_writer(store):
                artifacts.claim_action(store, action, claimed_at_ms=int(time.time() * 1000))
                if state == "unknown":
                    artifacts.finalize_action(store, action, effect_state="EFFECT_UNKNOWN", observed_sha256=None,
                                              completed_at_ms=int(time.time() * 1000), durability="durable")
        finally:
            os.close(fd)
        crash_owner_and_relay(first, receipt)
        before = grant.enrollment.socket_path.stat()
        if state == "unmapped":
            for kind in ("claim", "result", "process"):
                (artifact_root / (resource["start_id"] + "." + kind)).unlink()
        second, refused = start_owner(config_path)
        try:
            assert refused["resources"] == []
            expected = "BROWSER_ACTION_HISTORY_UNMAPPED" if state == "unmapped" else "BROWSER_EFFECT_UNRESOLVED"
            assert refused["activation"][0]["code"] == expected, refused
            after = grant.enrollment.socket_path.stat()
            assert (before.st_dev, before.st_ino, before.st_ctime_ns) == (after.st_dev, after.st_ino, after.st_ctime_ns)
        finally:
            close_owner(second)


def test_normal_lifespan_activates_public_fleet_and_isolates_absent_profile(tmp_path, monkeypatch):
    with tempfile.TemporaryDirectory(prefix="mmx-lifespan-", dir="/tmp") as directory:
        config, grant, native_config, document = configuration(tmp_path, Path(directory))
        unavailable = altered_grant(grant,
            enrollment=LinkEnrollment("a" * 32, "d" * 64, Path(directory) / "native" / "absent.sock"),
            chrome_pid=2147483646, chrome_start_identity="absent-chrome")
        save_document(Path(config.browser.profiles_file),
                      {"schema": PROFILES_SCHEMA, "profiles": [grant.document(), unavailable.document()]})

        async def exercise():
            runtime = await service.create_runtime(config)
            factory = service.create_browser_sibling
            deployment = factory(runtime, config)
            monkeypatch.setattr(service, "create_browser_sibling", lambda *_: deployment)
            state = service.ServiceState()
            app = service.build_service_app(runtime, config, state)
            caller = browser_broker_caller_from_lease(config.lease)
            peer = None
            reader = None
            stop = threading.Event()
            async with app.router.lifespan_context(app):
                assert [row["status"] for row in state.browser_activation] == ["active", "unavailable"]
                assert state.browser_activation[1]["code"] == "LINK_CHROME_UNAVAILABLE"
                active = await deployment.observe_active_resources(caller)
                assert len(active) == 1
                # Reconstructed facade reuses the original claim/process, not a new start.
                second = factory(runtime, config)
                again = await second.activate_configured_profiles(caller, config.lease.project_ref)
                assert again[0]["status"] == "active"
                assert (await second.observe_active_resources(caller))[0].browser_ref == active[0].browser_ref
                peer = Peer(grant.enrollment, native_config)
                peer.ready()
                def observe():
                    try:
                        while not stop.is_set():
                            message = peer.receive()
                            peer.send({"schema": INVENTORY_SCHEMA, "request_id": message["request_id"],
                                       "connection_generation": peer.generation,
                                       "shared_tabs": [{"tab_id": 7, "origin": "https://example.test",
                                           "consent_id": "human-consent", "document_revision": 0,
                                           "state": "shared", "allow_create": False}]})
                    except Exception:
                        pass
                reader = threading.Thread(target=observe, daemon=True)
                reader.start()
                try:
                    composition = compose_browser_owner_from_workbench(
                        deployment=deployment, signing_key=b"o" * 32, clock_ms=runtime.services.clock_ms,
                        caller_binding=browser_caller_binding_from_action_caller, broker_caller=caller,
                        expected_backend_schema_digest=service._browser_backend_digest(config.browser))
                    outer = ActionCaller(subject_digest="e" * 64, client_ref="outer-agent",
                                         resource="https://browser.example/mcp", scopes=("browser.control",),
                                         expires_at=caller.expires_at)
                    fleet = await composition.owner.browser_fleet(outer, {"limit": 10})
                    assert len(fleet["browsers"]) == 1
                    tabs = await composition.owner.browser_tabs(outer, {"browser_ref": fleet["browsers"][0]["browser_ref"]})
                    assert len(tabs["tabs"]) == 1
                finally:
                    await deployment.cleanup_resource(active[0].browser_ref, owner_state="released", effect_state="APPLIED")
                    stop.set()
                    peer.close()
                    reader.join(timeout=3)
            assert state.lifespan_completed
        asyncio.run(exercise())


def test_store_identity_and_activation_budget_cannot_be_silently_changed(tmp_path):
    with tempfile.TemporaryDirectory(prefix="mmx-store-grant-", dir="/tmp") as directory:
        config, _grant, _native, document = configuration(tmp_path, Path(directory))
        document["io_timeout_seconds"] = document["browser"]["startup_timeout_seconds"]
        with pytest.raises(service.ServiceConfigurationError, match="BROWSER_ACTIVATION_BUDGET_TOO_SMALL"):
            service.parse_service_config(document)
        async def exercise():
            runtime = await service.create_runtime(config)
            try:
                path = Path(config.browser.profiles_file)
                rows = json.loads(path.read_text())
                row = rows["profiles"][0]
                row["store_inode"] += 1
                row["profile_ref"] = LinkProfileGrant._address({key: value for key, value in row.items() if key != "profile_ref"})
                save_document(path, rows)
                with pytest.raises(service.ServiceConfigurationError):
                    service.create_browser_sibling(runtime, config)
            finally:
                runtime.revoke()
                await runtime.aclose(timeout=5)
        asyncio.run(exercise())


def test_lifespan_timeout_preserves_original_physical_attempt_then_activates_next_profile(tmp_path, monkeypatch):
    with tempfile.TemporaryDirectory(prefix="mmx-activation-timeout-", dir="/tmp") as directory:
        config, grant, _native, _document = configuration(tmp_path, Path(directory))
        other = altered_grant(grant,
            enrollment=LinkEnrollment("a" * 32, "f" * 64, Path(directory) / "native" / "second.sock"))
        save_document(Path(config.browser.profiles_file),
                      {"schema": PROFILES_SCHEMA, "profiles": [grant.document(), other.document()]})
        release = threading.Event()
        entered = threading.Event()

        async def exercise():
            runtime = await service.create_runtime(config)
            deployment = service.create_browser_sibling(runtime, config)
            actual_activation = deployment.resource_port.activate_configured_profile
            actual_builder = deployment.resource_port._relay_command_builder
            launched = []
            first = True
            def slow_once(caller, *, project_ref, profile_ref):
                nonlocal first
                if first:
                    first = False
                    entered.set()
                    assert release.wait(5)
                return actual_activation(caller, project_ref=project_ref, profile_ref=profile_ref)
            def count_launches(**kwargs):
                launched.append(kwargs["prepared"].profile_ref)
                return actual_builder(**kwargs)
            monkeypatch.setattr(deployment.resource_port, "activate_configured_profile", slow_once)
            monkeypatch.setattr(deployment.resource_port, "_relay_command_builder", count_launches)
            monkeypatch.setattr(service, "create_browser_sibling", lambda *_: deployment)
            monkeypatch.setattr(service, "BROWSER_ACTIVATION_INTERVAL_SECONDS", 0.02)
            # Inject a shorter caller deadline after configuration validation;
            # the real incumbent executor retains the entered operation.
            runtime._io_timeout_seconds = 0.05
            state = service.ServiceState()
            app = service.build_service_app(runtime, config, state)
            caller = browser_broker_caller_from_lease(config.lease)
            try:
                async with app.router.lifespan_context(app):
                    assert entered.is_set()
                    assert [row["status"] for row in state.browser_activation] == ["pending", "deferred"]
                    assert launched == []
                    await asyncio.sleep(0.08)
                    assert launched == [], "periodic observation must not duplicate the entered callback"
                    runtime._io_timeout_seconds = 10
                    release.set()
                    deadline = time.monotonic() + 5
                    while [row["status"] for row in state.browser_activation] != ["active", "active"]:
                        assert time.monotonic() < deadline, state.browser_activation
                        await asyncio.sleep(0.02)
                    assert launched.count(grant.profile_ref) == launched.count(other.profile_ref) == 1
                    active = await deployment.observe_active_resources(caller)
                    assert len(active) == 2
                    for row in active:
                        await deployment.cleanup_resource(row.browser_ref, owner_state="released", effect_state="APPLIED")
            finally:
                release.set()
        asyncio.run(exercise())


def test_stalled_profile_observation_cannot_block_another_actions_durable_result(tmp_path, monkeypatch):
    from integrations.mastermind_browser_link.tool_contract import ACTION_TOOL
    from integrations.workbench_browser_mcp.resource_port import BrowserResourceRefused
    from tests.test_mastermind_browser_link_native import arguments
    with tempfile.TemporaryDirectory(prefix="mmx-maintenance-", dir="/tmp") as directory:
        config, grant, native_config, _document = configuration(tmp_path, Path(directory))
        second = altered_grant(grant,
            enrollment=LinkEnrollment("a" * 32, "d" * 64, Path(directory) / "native" / "second.sock"))
        third = altered_grant(grant,
            enrollment=LinkEnrollment("a" * 32, "e" * 64, Path(directory) / "native" / "third.sock"))
        save_document(Path(config.browser.profiles_file),
                      {"schema": PROFILES_SCHEMA, "profiles": [row.document() for row in (grant, second, third)]})
        stalled = threading.Event()
        release = threading.Event()

        async def exercise():
            runtime = await service.create_runtime(config)
            deployment = service.create_browser_sibling(runtime, config)
            caller = browser_broker_caller_from_lease(config.lease)
            peer = None
            maintenance = None
            try:
                started = []
                for row in (grant, second):
                    prepared = await deployment.prepare_resource(caller, config.lease.project_ref, "extension", row.profile_ref)
                    started.append(await deployment.start_resource(caller, prepared))
                assert all(row["effect_state"] == "APPLIED" for row in started)
                unused_start = await deployment.prepare_resource(caller, config.lease.project_ref, "extension", third.profile_ref)
                original_status = deployment.resource_port._status
                def slow_status(start, process):
                    if start.profile_ref == second.profile_ref:
                        stalled.set()
                        assert release.wait(5), "test did not release the independent profile"
                    return original_status(start, process)
                monkeypatch.setattr(deployment.resource_port, "_status", slow_status)
                peer = Peer(grant.enrollment, native_config)
                await asyncio.to_thread(peer.ready)
                browser_ref = started[0]["browser_ref"]
                prepared = await deployment.prepare_action(caller, browser_ref, ACTION_TOOL, arguments())
                action = asyncio.create_task(deployment.run_action(caller, browser_ref, prepared))
                command = await asyncio.to_thread(peer.receive)
                assert deployment.action_port.has_active_actions()
                # The same action owner prevents a long new launch while this
                # already-dispatched action still needs to save its result.
                with pytest.raises(BrowserResourceRefused, match="BROWSER_ACTIVATION_DEFERRED"):
                    await deployment.start_resource(caller, unused_start)
                assert not third.enrollment.socket_path.exists()
                maintenance = asyncio.create_task(deployment.activate_configured_profiles(caller, config.lease.project_ref))
                assert await asyncio.to_thread(stalled.wait, 2)
                peer.result(command, output={"scrolled": True})
                result = await asyncio.wait_for(action, 2)
                assert result["effect_state"] == "APPLIED", result
                assert not release.is_set(), "status observation must still be stalled"
                assert not maintenance.done()
                assert (await deployment.reconcile_action(caller, browser_ref, prepared))["effect_state"] == "APPLIED"
                # No false uncertainty hold was introduced on the healthy profile.
                another = await deployment.prepare_action(caller, browser_ref, ACTION_TOOL, arguments())
                next_action = asyncio.create_task(deployment.run_action(caller, browser_ref, another))
                peer.result(await asyncio.to_thread(peer.receive), output={"scrolled": True})
                assert (await asyncio.wait_for(next_action, 2))["effect_state"] == "APPLIED"
                release.set()
                await asyncio.wait_for(maintenance, 5)
                maintenance = None
            finally:
                release.set()
                if maintenance is not None:
                    await asyncio.wait_for(maintenance, 5)
                for row in await deployment.observe_active_resources(caller):
                    await deployment.cleanup_resource(row.browser_ref, owner_state="released", effect_state="APPLIED")
                if peer is not None:
                    peer.close()
                await runtime.aclose(timeout=5)
        asyncio.run(exercise())


def test_expected_runtime_revocation_stops_maintenance_without_failing_shutdown(tmp_path, monkeypatch):
    with tempfile.TemporaryDirectory(prefix="mmx-maintenance-close-", dir="/tmp") as directory:
        config, _grant, _native, _document = configuration(tmp_path, Path(directory))
        async def exercise():
            runtime = await service.create_runtime(config)
            deployment = service.create_browser_sibling(runtime, config)
            monkeypatch.setattr(service, "create_browser_sibling", lambda *_: deployment)
            monkeypatch.setattr(service, "BROWSER_ACTIVATION_INTERVAL_SECONDS", 0.01)
            state = service.ServiceState()
            app = service.build_service_app(runtime, config, state)
            caller = browser_broker_caller_from_lease(config.lease)
            async with app.router.lifespan_context(app):
                for row in await deployment.observe_active_resources(caller):
                    await deployment.cleanup_resource(row.browser_ref, owner_state="released", effect_state="APPLIED")
                runtime.revoke()
                await asyncio.sleep(0.05)
            assert state.lifespan_completed
            assert state.shutdown_outcome == service.ShutdownOutcome.CLEAN
        asyncio.run(exercise())
