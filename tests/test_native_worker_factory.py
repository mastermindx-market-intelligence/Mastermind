"""Native account lifetime and exact worker-entrypoint composition contracts."""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

import pytest

from control_plane.codex_account_environment import CodexAccountError, native_codex_account_scope
from control_plane import codex_worker, codex_provider_realm
from scripts import executive_os_phase1c_worker as worker
from test_codex_account_environment import auth, private
from test_executive_codex_attestation_receipt import _fixture
from test_subscription_worker_config import _config, _write_config


def native_config(root):
    value = _config(root, schema=worker.NATIVE_CONFIG_SCHEMA_VERSION)
    value.update(native_provider="codex", native_realm_enrollment={
        "host_ref": "host-" + "1" * 64, "os_principal_ref": "os-principal-fixture"})
    return value


def test_native_schema_keeps_provider_fields_closed_and_unarmed_service_held(tmp_path):
    value = native_config(tmp_path)
    assert worker._load_config(_write_config(tmp_path, value), require_root_owner=False) == value
    with pytest.raises(worker.WorkerConfigError, match="autonomy admission"):
        worker._assert_service_activation_allowed(value)
    for field, bad in [("native_provider", "claude"), ("native_realm_enrollment", None),
                       ("harness_binding_id", "unreviewed")]:
        (tmp_path / "worker.json").unlink()
        with pytest.raises(worker.WorkerConfigError):
            worker._load_config(_write_config(tmp_path, {**value, field: bad}), require_root_owner=False)


def test_claude_config_shape_is_distinct_and_does_not_claim_implemented_factory(tmp_path):
    value = native_config(tmp_path)
    value["native_provider"] = "claude"
    for name in ("binary", "attestation_receipt"):
        value["claude_" + name] = value.pop("codex_" + name)
    value["allowed_claude_versions"] = ["2.1.275"]
    del value["allowed_codex_versions"], value["required_team_identifier"]
    assert worker._load_config(_write_config(tmp_path, value), require_root_owner=False) == value
    with pytest.raises(worker.WorkerConfigError, match="explicit SDK runtime"):
        worker._assert_service_activation_allowed(value)
    with pytest.raises(worker.WorkerConfigError, match="explicit SDK runtime"):
        worker._build_broker(value)
    path = tmp_path / "worker.json"
    path.unlink()
    value["claude_sdk_python"] = "/Library/Application Support/MastermindExecutive/providers/claude-agent-sdk/0.2.160/bin/python3.12"
    assert worker._load_config(_write_config(tmp_path, value), require_root_owner=False) == value
    path.unlink()
    value["claude_sdk_python"] = "python3"
    with pytest.raises(worker.WorkerConfigError, match="absolute path"):
        worker._load_config(_write_config(tmp_path, value), require_root_owner=False)


def test_wrong_principal_refused_before_native_scope_or_socket(tmp_path, monkeypatch):
    def should_not_open(*a, **kw):
        pytest.fail("wrong principal reached provider home")
    monkeypatch.setattr(worker, "native_codex_account_scope", should_not_open)
    config = {"worker_uid": os.geteuid()+1, "worker_gid": os.getegid(), "control_uid": os.geteuid()+1000}
    with pytest.raises(worker.WorkerConfigError, match="distinct worker principal"):
        asyncio.run(worker._serve(config))


def test_real_entrypoint_factory_constructs_existing_adapter_with_scoped_home(tmp_path, monkeypatch):
    root = tmp_path.resolve()
    binary, receipt = _fixture(root, monkeypatch)
    config = native_config(root)
    config.update(control_uid=os.geteuid() + 1000, allowed_supplementary_gids=[],
                  codex_binary=str(binary), codex_attestation_receipt=str(receipt))
    for field in ("workspace_root", "run_root", "provider_home"):
        Path(config[field]).mkdir(mode=0o700)
    home = Path(config["provider_home"])
    private(home / "auth.json", auth())
    observed = []
    def receipt_loader(path, **kwargs):
        observed.append(kwargs.copy())
        return codex_worker.load_codex_attestation_receipt(path, **kwargs,
                                                          expected_owner_uid=os.geteuid())
    monkeypatch.setattr(worker, "load_codex_attestation_receipt", receipt_loader)
    with pytest.raises(worker.WorkerConfigError, match="lifetime account scope"):
        worker._build_broker(config)
    with native_codex_account_scope(home) as environment:
        broker = worker._build_broker(config, native_account=environment)
        assert type(broker.adapter) is codex_worker.CodexWorkerAdapter
        assert broker.adapter.codex_home == home
        assert broker.adapter.provider_realm is None
        assert broker.adapter.provider_credential_loader is None
        assert observed[0] == {"expected_binary_path": binary,
                               "expected_owner_gid": os.getegid()}


@pytest.mark.parametrize("failure", [None, "serve", "socket", "shutdown"])
def test_broker_scope_lives_through_shutdown_and_socket_cleanup(tmp_path, monkeypatch, failure):
    home = tmp_path.resolve() / "provider"
    home.mkdir(mode=0o700)
    private(home / "auth.json", auth())
    events = []
    class Socket:
        def close(self):
            events.append("socket_closed")
    def activate(name):
        if failure == "socket":
            raise RuntimeError("socket refused")
        return Socket()
    class Broker:
        async def serve(self, sock):
            events.append("serve")
            if failure == "serve":
                raise RuntimeError("serve refused")
        async def shutdown(self):
            events.append("shutdown")
            with pytest.raises(CodexAccountError, match="WRITER_BUSY"):
                with native_codex_account_scope(home):
                    pytest.fail("scope released before shutdown")
            if failure == "shutdown":
                raise RuntimeError("shutdown refused")
    def factory(config, **kwargs):
        assert kwargs["native_account"].home == home
        return Broker()
    monkeypatch.setattr(worker, "_build_broker", factory)
    monkeypatch.setattr(worker, "activate_launchd_socket", activate)
    config = {"provider_home": str(home), "launchd_socket_name": "WorkerBroker",
              "worker_uid": os.geteuid(), "worker_gid": os.getegid(), "control_uid": os.geteuid()+1000}
    if failure:
        with pytest.raises(RuntimeError, match=failure):
            asyncio.run(worker._serve(config))
    else:
        asyncio.run(worker._serve(config))
    assert "shutdown" in events
    if failure != "socket":
        assert events[-1] == "socket_closed"
    with native_codex_account_scope(home):
        pass


def test_identity_guard_consumes_exact_owner_and_rechecks_each_call(tmp_path, monkeypatch):
    config = native_config(tmp_path)
    path = _write_config(tmp_path, config)
    calls = []
    class Owner:
        stale = False
        def require_current_identity(self, host, principal):
            calls.append((host, principal))
            if self.stale:
                raise RuntimeError("private owner diagnostic")
    owner = Owner()
    def loader(actual_path, *, expected_config_sha256):
        assert actual_path == path
        assert expected_config_sha256 == worker.sha256_file(path)
        return owner
    # Only metadata ownership is simulated; production requires root.
    monkeypatch.setattr(worker, "_load_config", lambda *args, **kw: config.copy())
    monkeypatch.setattr(codex_provider_realm, "load_native_realm_owner", loader, raising=False)
    guard = worker._native_identity_guard(config, path)
    guard()
    assert len(calls) == 2
    owner.stale = True
    with pytest.raises(worker.WorkerConfigError, match="^native realm identity refused$"):
        guard()


def test_identity_guard_refuses_changed_config_and_data_only_owner(tmp_path, monkeypatch):
    config = native_config(tmp_path)
    path = _write_config(tmp_path, config)
    monkeypatch.setattr(worker, "_load_config", lambda *args, **kw: {**config, "worker_id": "different"})
    def should_not_load(*args, **kwargs):
        pytest.fail("changed config reached realm owner")
    monkeypatch.setattr(codex_provider_realm, "load_native_realm_owner", should_not_load, raising=False)
    with pytest.raises(worker.WorkerConfigError, match="config changed"):
        worker._native_identity_guard(config, path)
    monkeypatch.setattr(worker, "_load_config", lambda *args, **kw: config.copy())
    class DataOwner:
        def require_current_identity(self, *args):
            return True
    monkeypatch.setattr(codex_provider_realm, "load_native_realm_owner", lambda *a, **k: DataOwner())
    with pytest.raises(worker.WorkerConfigError, match="identity refused"):
        worker._native_identity_guard(config, path)
