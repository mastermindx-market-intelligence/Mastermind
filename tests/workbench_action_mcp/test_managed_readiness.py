"""Managed startup evidence from real service acquisition and bounded local HTTP."""
from __future__ import annotations

import asyncio
import copy
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import socket
import stat
import tempfile
import threading
import time
from types import SimpleNamespace

import httpx
import pytest

from control_plane.codex_worker import ProcessInspector
from integrations.studio_direct_mcp import workbench_host_service as host
from integrations.workbench_action_mcp import service
from integrations.workbench_action_mcp.acquisition import AcquisitionReceipt, document_fingerprint, projection
from integrations.workbench_action_mcp.readiness import MEDIA_TYPE, config_fingerprint, verify_snapshot
from tests.workbench_action_mcp.test_browser_link_service import configuration


def expected_for(config):
    persistent = {}
    for name in ("project_root", "artifact_directory", "audit_directory", "browser_fabric_audit_directory"):
        path = getattr(config, name)
        info = Path(path).stat()
        persistent[name] = dict(path=path, device=info.st_dev, inode=info.st_ino,
                                uid=info.st_uid, mode=stat.S_IMODE(info.st_mode))
    persistent["action_key"] = dict(path=config.action_key_file, sha256=hashlib.sha256(
        service._secure_action_key(config.action_key_file)).hexdigest())
    dependencies = {}
    for name, path in (("policy", config.policy_file), ("browser_policy", config.browser_fabric_policy_file),
                       ("profiles", config.browser.profiles_file), ("routes", config.browser_fabric_routes_file),
                       ("credentials", config.browser_fabric_credentials_file)):
        if path is not None:
            dependencies[name] = dict(path=path, sha256=document_fingerprint(json.loads(Path(path).read_bytes())))
    return projection(config_fingerprint(config), persistent, dependencies)


@pytest.fixture
def fixture(tmp_path, monkeypatch):
    with tempfile.TemporaryDirectory(prefix="mmx-proof-", dir="/tmp") as short:
        config, _grant, _native, _document = configuration(tmp_path, Path(short))
        expected = expected_for(config)
        activations = []
        actual = service.create_browser_sibling

        def sibling(runtime, selected, **kwargs):
            deployed = actual(runtime, selected, **kwargs)
            async def activate(caller, project_ref):
                # No real relay or Chrome is launched by this startup test.
                assert kwargs["acquisition"].digest == document_fingerprint(expected)
                activations.append((caller, project_ref))
                return ()
            return replace(deployed, activate_configured_profiles=activate)

        monkeypatch.setattr(service, "create_browser_sibling", sibling)
        yield SimpleNamespace(config=config, expected=expected, activations=activations)


def test_actual_acquisition_signed_readiness_and_closed_http_request(fixture):
    config, expected = fixture.config, fixture.expected
    async def exercise():
        acquisition = AcquisitionReceipt(expected)
        runtime = await service.create_runtime(config, acquisition=acquisition)
        state = service.ServiceState(socket_owned=True)
        try:
            app = service.build_service_app(runtime, config, state, acquisition=acquisition)
            assert acquisition.digest is None and not fixture.activations
            async with app.router.lifespan_context(app):
                assert len(fixture.activations) == 1
                assert acquisition.digest == state.acquisition_sha256 == document_fingerprint(expected)
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                             base_url="http://" + config.incoming_authority) as client:
                    assert (await client.get("/readyz")).text == "READY\n"
                    nonce = "a" * 64
                    response = await client.get("/readyz?nonce=" + nonce, headers={"Accept": MEDIA_TYPE})
                    assert response.status_code == 200
                    assert response.headers["cache-control"] == "no-store"
                    observed = response.json()
                    inspector = ProcessInspector()
                    process = dict(pid=os.getpid(), process_start_identity=inspector.inspect(os.getpid()).start_identity,
                                   service_uid=os.geteuid(), boot_session_id=inspector.boot_session_id())
                    bindings = dict(key=runtime.services.action_token_key, nonce=nonce, process=process,
                                    host_id=config.host_id, config_sha256=config_fingerprint(config),
                                    acquisition_sha256=document_fingerprint(expected))
                    assert verify_snapshot(observed, **bindings)
                    assert observed["fleet_observation"] == "unobserved"
                    for change in ({"nonce": "b" * 64}, {"key": b"wrong" * 8},
                                   {"acquisition_sha256": "f" * 64}, {"config_sha256": "e" * 64},
                                   {"process": dict(process, pid=process["pid"] + 1)}):
                        assert not verify_snapshot(observed, **dict(bindings, **change))
                    for change in ({"ready": False}, {"fleet_observation": "online"}, {"extra": True}):
                        assert not verify_snapshot(dict(observed, **change), **bindings)
                    for query in ("", "?nonce=" + nonce + "&nonce=" + nonce, "?extra=1&nonce=" + nonce):
                        assert (await client.get("/readyz" + query, headers={"Accept": MEDIA_TYPE})).status_code == 400
                    assert (await client.get("/readyz?nonce=invalid", headers={"Accept": MEDIA_TYPE})).status_code == 503
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, client=("192.0.2.10", 1234)),
                                             base_url="http://" + config.incoming_authority) as client:
                    assert (await client.get("/readyz?nonce=" + nonce, headers={"Accept": MEDIA_TYPE})).status_code == 400
            assert state.lifespan_completed
        finally:
            await runtime.aclose(timeout=5)
    asyncio.run(exercise())


@pytest.mark.parametrize("changed", ["policy", "action_key", "project_root", "artifact_directory", "audit_directory"])
def test_runtime_acquisition_refuses_changed_approved_input_before_use(fixture, changed):
    config = fixture.config
    if changed == "policy":
        path = Path(config.policy_file)
        value = json.loads(path.read_bytes())
        value["policy_id"] = "changed.policy"
        path.write_text(json.dumps(value))
    elif changed == "action_key":
        Path(config.action_key_file).write_text("8" * 64 + "\n")
    else:
        path = Path(getattr(config, changed))
        path.rename(path.with_name(path.name + "-original"))
        path.mkdir(mode=0o700)
    async def exercise():
        with pytest.raises((ValueError, service.ServiceConfigurationError)):
            await service.create_runtime(config, acquisition=AcquisitionReceipt(fixture.expected))
        assert not fixture.activations
    asyncio.run(exercise())


@pytest.mark.parametrize("changed", ["browser_policy", "profiles", "browser_fabric_audit_directory", "incomplete"])
def test_sibling_acquisition_completes_before_any_profile_activation(fixture, changed):
    config = fixture.config
    async def exercise():
        acquisition = AcquisitionReceipt(fixture.expected)
        runtime = await service.create_runtime(config, acquisition=acquisition)
        try:
            if changed in {"browser_policy", "profiles"}:
                path = Path(config.browser_fabric_policy_file if changed == "browser_policy" else config.browser.profiles_file)
                value = json.loads(path.read_bytes())
                value["unexpected_input"] = True
                path.write_text(json.dumps(value))
                with pytest.raises(service.ServiceConfigurationError):
                    service.build_service_app(runtime, config, service.ServiceState(socket_owned=True), acquisition=acquisition)
            else:
                state = service.ServiceState(socket_owned=True)
                app = service.build_service_app(runtime, config, state, acquisition=acquisition)
                if changed == "browser_fabric_audit_directory":
                    path = Path(config.browser_fabric_audit_directory)
                    path.rename(path.with_name("original-browser-audit"))
                    path.mkdir(mode=0o700)
                else:
                    # Simulate an omitted producer receipt, without changing the
                    # approved plan or giving the activation hook any authority.
                    acquisition._dependencies.pop("profiles")
                with pytest.raises(Exception) as refused:
                    async with app.router.lifespan_context(app):
                        pytest.fail("incomplete acquisition reached serving")
                def leaves(error):
                    if isinstance(error, BaseExceptionGroup):
                        return [leaf for child in error.exceptions for leaf in leaves(child)]
                    return [error]
                observed = leaves(refused.value)
                assert observed and all(isinstance(error, ValueError)
                                        and str(error).startswith("SERVICE_ACQUISITION_") for error in observed)
            assert not fixture.activations and acquisition.digest is None
        finally:
            await runtime.aclose(timeout=5)
    asyncio.run(exercise())


def test_receipt_uses_consumed_object_and_open_descriptor_after_path_replacement(fixture):
    config = fixture.config
    receipt = AcquisitionReceipt(fixture.expected)
    original = json.loads(Path(config.policy_file).read_bytes())
    path = Path(config.project_root)
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        path.rename(path.with_name("original-project"))
        path.mkdir(mode=0o700)
        Path(config.policy_file).write_text("{}")
        receipt.document("policy", config.policy_file, original)
        receipt.directory("project_root", config.project_root, descriptor)
        assert receipt._dependencies["policy"] == fixture.expected["dependencies"]["policy"]
        assert receipt._persistent["project_root"] == fixture.expected["persistent"]["project_root"]
        replacement = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
        try:
            with pytest.raises(ValueError, match="SERVICE_ACQUISITION_BINDING_CHANGED"):
                receipt.directory("project_root", config.project_root, replacement)
        finally:
            os.close(replacement)
        with pytest.raises(ValueError, match="SERVICE_ACQUISITION_BINDING_CHANGED"):
            receipt.document("policy", config.policy_file, {})
    finally:
        os.close(descriptor)


def test_readiness_probe_absolute_deadline_closes_dripping_socket(fixture):
    listener = socket.socket()
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    listener.settimeout(2)
    port = listener.getsockname()[1]
    stopped = threading.Event()
    disconnected = threading.Event()
    errors = []
    def drip():
        try:
            connection, _ = listener.accept()
            with connection:
                connection.settimeout(1)
                request = b""
                while b"\r\n\r\n" not in request:
                    request += connection.recv(4096)
                connection.sendall(b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: 4000\r\n\r\n")
                while not stopped.wait(.02):
                    try:
                        connection.sendall(b" ")
                    except (BrokenPipeError, ConnectionResetError):
                        disconnected.set()
                        return
        except Exception as error:
            errors.append(type(error).__name__)
        finally:
            listener.close()
    worker = threading.Thread(target=drip)
    worker.start()
    config = replace(fixture.config, bind_port=port, incoming_authority=f"127.0.0.1:{port}")
    plan = dict(fixture.expected)
    try:
        started = time.monotonic()
        assert host._probe(None, config, plan, {}, timeout=.15) is None
        assert time.monotonic() - started < 1.0
        assert disconnected.wait(1.0), "timed-out response retained its physical connection"
    finally:
        stopped.set()
        worker.join(timeout=2)
        listener.close()
    assert not worker.is_alive() and errors == []
