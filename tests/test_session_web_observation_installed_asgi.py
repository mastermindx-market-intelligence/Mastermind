"""Actual signed HTTP -> installed CeoIngress -> original C2/native fixture.

Only root provisioning/profile home and browser APIs are synthetic. No live
profile, browser tab, runtime service, installed permission or role is changed.
"""
from __future__ import annotations

import asyncio
import dataclasses
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from types import SimpleNamespace

import httpx
import pytest

from common.session_bridge_private_contract import PRIVATE_SCHEMA
from integrations.executive_mcp import server
from integrations.session_bridge.installed import InstalledSessionBridgeClient, principal_frame
from integrations.session_bridge import installed_web_observation as observation
from integrations.session_bridge.web_observation_tools import OBSERVE_TOOL, CONTINUITY_TOOL
from tests import test_executive_mcp_web_ceo_sessions as host
from tests import test_mastermind_executive_app_asgi as auth
from tests.test_session_web_observation_installed import configured_owner, installation_document, bundle

rsa_key = host.rsa_key
short_socket_root = host.short_socket_root
settings = host.settings


@contextmanager
def native_profile(tmp_path, monkeypatch, binding):
    from control_plane import surface_bindings
    from integrations.chairman_surfaces import web_sol_instance as instance, web_sol_native_host as native
    home = tmp_path / "profile"
    path = home / "Library/Application Support/Mastermind/control-room/surface_bindings.json"
    path.parent.mkdir(parents=True, mode=0o700)
    home.chmod(0o700); path.parent.chmod(0o700)
    path.write_text(json.dumps({"schema": surface_bindings.SCHEMA, "bindings": [binding]}))
    path.chmod(0o600)
    monkeypatch.setattr(observation, "_profile_home", lambda uid: home)
    identity = instance.adapter_instance_id(binding)
    failures = []
    with tempfile.TemporaryDirectory(prefix="wo-", dir=tempfile.gettempdir()) as directory:
        directory = Path(directory); directory.chmod(0o700)
        original_path = instance.socket_path
        monkeypatch.setattr(instance, "socket_path",
            lambda selected, root=None: original_path(selected, root=directory))
        proc = subprocess.Popen(["node", str(Path(__file__).parents[1] / "tests/web_sol_native_census.test.cjs"),
            "--native-pipe", json.dumps({"instance": identity, "count": 2})],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0)
        def serve():
            try:
                native.run_native_host(proc.stdout, proc.stdin,
                    caller_origin=native.ALLOWED_EXTENSION_ORIGIN,
                    expected_instance_id=identity, socket_root=directory)
            except BaseException as exc:
                failures.append(exc)
        worker = threading.Thread(target=serve)
        worker.start()
        try:
            until = time.monotonic() + 5
            destination = instance.socket_path(identity)
            while not destination.exists() and not failures and time.monotonic() < until:
                time.sleep(.01)
            assert destination.exists(), ("synthetic native startup", failures)
            yield path
            assert not failures
        finally:
            proc.stdin.close()
            worker.join(6)
            if proc.poll() is None:
                proc.terminate()
            proc.wait(timeout=5)
            proc.stdout.close(); proc.stderr.close()
            assert not worker.is_alive(), "native fixture thread leaked"
            assert not list(directory.glob("*.sock")), "native fixture socket leaked"


def test_signed_installed_private_native_vertical_and_mid_read_revocation(
        tmp_path, monkeypatch, settings, rsa_key, short_socket_root):
    from ops.executive_os import executive_mcp_entry as entry, coo_principal_host
    from tests import test_executive_mcp_installed_fabric_composition as control
    from integrations.chairman_surfaces import web_sol_client
    from tests.test_executive_ceo_ingress import _raw_ceo_request

    b = configured_owner(tmp_path, monkeypatch, clock=lambda: datetime.now(timezone.utc))
    original_owner = entry.installed_web_observation_owner
    constructors = []
    def installed_owner(path, source, *, expected_uid, **kwargs):
        constructors.append((path, source, expected_uid))
        assert path == b.path and expected_uid == os.geteuid()
        # The synthetic release directory stands in for the installed sealed
        # source; the actual sealed-projection constructor remains in the path.
        return original_owner(path, b.source, expected_uid=expected_uid,
                              clock=lambda: datetime.now(timezone.utc), **kwargs)
    monkeypatch.setattr(entry, "installed_web_observation_owner", installed_owner)
    monkeypatch.setattr(coo_principal_host, "DEFAULT_INSTALL_PATH", b.path)
    original_raw = control._raw_for_factory
    def qualified_raw(*args, **kwargs):
        raw = original_raw(*args, **kwargs)
        # An honestly matching fixture process, not a setuid or HOME operation.
        raw["control_uid"] = os.geteuid()
        raw["allowed_peer_uids"] = (os.geteuid(),)
        return raw
    monkeypatch.setattr(control, "_raw_for_factory", qualified_raw)
    calls, revoke = [], [False]
    original_census = web_sol_client.census_via_extension
    def census(binding, **kwargs):
        calls.append((binding["binding_id"], kwargs))
        result = original_census(binding, **kwargs)
        if revoke[0]:
            withdrawn = json.loads(b.path.read_text())
            withdrawn["session_web_observation"]["permissions"] = {
                "generation": "e" * 64, "principals": []}
            replacement = b.path.with_name("revoked.json")
            replacement.write_text(json.dumps(withdrawn)); replacement.chmod(0o600)
            replacement.replace(b.path)
        return result
    monkeypatch.setattr(web_sol_client, "census_via_extension", census)

    async def run():
        async with control.factory_service(tmp_path / "control", short_socket_root, monkeypatch,
                                           profile="web_ceo_v3") as (service, raw, _):
            await service.start()
            client = InstalledSessionBridgeClient(raw["ceo_ingress_socket_path"])
            selected_settings = dataclasses.replace(settings, read_from_ceo_ingress=True,
                clock=lambda: int(time.time()), ceo_ingress_socket_path=str(raw["ceo_ingress_socket_path"]))
            async def unused(**kwargs):
                pytest.fail("session observation reached MDM")
            app = server.build_web_ceo_v3_mcp_app(selected_settings, audit_sink=host.Sink(),
                mdm_reader=SimpleNamespace(list_macos_devices=unused, device=unused),
                session_target_projector=client.targets, session_reply_handler=client.send,
                session_summon_handler=client.summon, session_web_read_tools=b.owner.network_tools(client))
            now = int(time.time())
            token = auth._read_token(rsa_key, iat=now - 1, nbf=now - 1, exp=now + 300)
            async with app._app.router.lifespan_context(app._app):
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                             base_url="http://127.0.0.1") as http:
                    listed = await host.rpc(http, token, "tools/list")
                    assert listed.status_code == 200 and "result" in listed.json(), listed.text
                    names = {tool["name"] for tool in listed.json()["result"]["tools"]}
                    assert OBSERVE_TOOL in names and CONTINUITY_TOOL not in names
                    response, result = await host.call(http, token, OBSERVE_TOOL, {"max_rows": 1})
                    assert response.status_code == 200 and result["ok"] is True, result
                    data = result["data"]
                    assert data["account_history_coverage"] == "UNKNOWN"
                    source = data["sources"][0]
                    assert source["adapter_instance_id"] == b.adapter
                    assert source["source_counts"]["initial_tab_count"] == 2
                    assert source["returned_rows"] == 1 and source["output_omitted_rows"] == 1
                    assert source["rows"][0]["runtime_status"] == "UNKNOWN"
                    assert len(calls) == 1
                    # Same OAuth subject, another client: no inferred shared role grant.
                    foreign = auth._read_token(rsa_key, iat=now - 1, nbf=now - 1,
                                               exp=now + 300, client_id="another-client")
                    _, empty = await host.call(http, foreign, OBSERVE_TOOL, {})
                    assert empty["ok"] is True and empty["data"]["sources"] == [], empty
                    assert len(calls) == 1
                    # A caller cannot smuggle a profile selector into the private tool.
                    malformed = await _raw_ceo_request(Path(raw["ceo_ingress_socket_path"]), (
                        json.dumps({"schema": PRIVATE_SCHEMA, "tool": observation.PRIVATE_TOOL,
                            "principal": principal_frame(dataclasses.replace(b.principal,
                                issued_at=now - 1, expires_at=now + 300)),
                            "arguments": {"profile_owner_uid": os.geteuid()}}) + "\n").encode())
                    assert malformed["ok"] is False and len(calls) == 1
                    # The original App-peer kernel-identity check precedes this owner.
                    with monkeypatch.context() as peer:
                        peer.setattr("control_plane.executive_service._peer_uid",
                                     lambda connection: os.geteuid() + 500)
                        denied = await _raw_ceo_request(Path(raw["ceo_ingress_socket_path"]), (
                            json.dumps({"schema": PRIVATE_SCHEMA, "tool": observation.PRIVATE_TOOL,
                                "principal": principal_frame(b.principal), "arguments": {}}) + "\n").encode())
                        assert denied["ok"] is False and len(calls) == 1
                    # Revoke after the real native read but before private completion.
                    revoke[0] = True
                    _, withheld = await host.call(http, token, OBSERVE_TOOL, {})
                    assert withheld["ok"] is False and withheld["data"] is None
                    assert len(calls) == 2
                    _, empty = await host.call(http, token, OBSERVE_TOOL, {})
                    assert empty["ok"] is True and empty["data"]["sources"] == [], empty
                    assert len(calls) == 2, "withdrawn permission must not re-enter C2"
            assert constructors, "the actual Control factory never composed the installed owner"

    with native_profile(tmp_path, monkeypatch, b.binding):
        asyncio.run(run())


def test_installed_network_entry_passes_one_original_client_to_optional_read(tmp_path, monkeypatch):
    from tests.test_executive_mcp_entry import _module
    from integrations.session_bridge import installed
    import uvicorn
    from control_plane import fs_security

    module = _module()
    b = bundle()
    raw = installation_document(b.block)
    source = tmp_path / raw["release_sha"]
    source.mkdir()
    module.__file__ = str(source / "ops/executive_os/executive_mcp_entry.py")
    config = tmp_path / "installed.json"
    config.write_text(json.dumps(raw)); config.chmod(0o600)
    monkeypatch.setattr(module, "sys", SimpleNamespace(
        flags=SimpleNamespace(isolated=True), dont_write_bytecode=True, path=[]))
    monkeypatch.setattr(module, "require_sealed_path", lambda *a, **kw: None)
    monkeypatch.setattr(fs_security, "has_macos_acl", lambda *a, **kw: False)
    monkeypatch.setattr(module.os, "geteuid", lambda: 458)
    monkeypatch.setattr(module, "build_optional_apps", lambda *a: {})
    closed = []
    monkeypatch.setattr(module, "PolicyAuditSink",
        lambda *a, **kw: SimpleNamespace(close=lambda: closed.append(True)))
    created, built, listeners = [], [], []
    original_init = installed.InstalledSessionBridgeClient.__init__
    def init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        created.append(self)
    monkeypatch.setattr(installed.InstalledSessionBridgeClient, "__init__", init)
    def builder(settings, **kwargs):
        built.append(kwargs)
        return object()
    monkeypatch.setattr(server, "build_web_ceo_v3_mcp_app", builder)
    monkeypatch.setattr(uvicorn, "run", lambda *a, **kw: listeners.append((a, kw)))
    assert module.main(["--config", str(config)]) == 0
    assert len(created) == len(built) == len(listeners) == 1 and closed == [True]
    assert built[0]["session_target_projector"] == created[0].targets
    assert built[0]["session_reply_handler"] == created[0].send
    specs = built[0]["session_web_read_tools"].tool_specs()
    assert [spec.name for spec in specs] == [OBSERVE_TOOL]
    assert specs[0].read_only is True
