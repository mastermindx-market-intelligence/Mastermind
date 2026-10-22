"""Optional source composition is inert and production Fabric stays unarmed."""
import asyncio
import hashlib
import json
import os
import socket
from pathlib import Path
from types import SimpleNamespace

import pytest

from control_plane import executive_worker_broker as broker
from control_plane.executive_fabric_adapter import AttendedFabricWorkerAdapter
from control_plane.executive_fabric_composition import FabricBindingSource
from control_plane.executive_runtime import Runtime
from control_plane.executive_supervisor import CleanupPolicy
from control_plane.mixed_worker_supervisor import MixedExecutionOwnerSupervisor
from control_plane.worker_execution_contract import CleanupPolicy as ContractCleanupPolicy
from control_plane.remote_attempt_transport import AttemptBoundRemoteWorkerAdapter
from scripts import executive_os_phase1c as cli
from test_ceo_submit_armed_composition import _raw, _write
from test_executive_fabric_composition import document, root_stats


def staged(tmp_path, raw):
    data = document()
    data["bindings"][0].update(worker_uid=raw["worker_uid"], worker_gid=raw["worker_gid"])
    contents = json.dumps(data).encode()
    path = tmp_path / "fabric-bindings.json"
    path.write_bytes(contents)
    path.chmod(0o600)
    return dict(fabric_bindings_path=str(path),
                fabric_bindings_sha256=hashlib.sha256(contents).hexdigest(),
                fabric_bridge_armed=False)


def compose(tmp_path, monkeypatch, raw, **kwargs):
    runtime = Runtime.at(tmp_path / "fixture-runtime")
    captured = {}
    client = object()
    monkeypatch.setattr(broker, "WorkerBrokerClient", lambda *args, **kwargs: client)
    monkeypatch.setattr(cli, "activate_launchd_socket", _workspace_aware_listener(raw))
    def service(config, **bindings):
        captured.update(bindings)
        return SimpleNamespace(config=config)
    monkeypatch.setattr(cli, "ExecutiveControlService", service)
    service = cli._service_from_config(raw, **kwargs)
    return service, captured["supervisor_factory"](runtime), client


def _workspace_aware_listener(raw):
    """Return a launchd listener factory that yields a real AF_UNIX socket for
    the workspace Control Room launchd name and ``object()`` for everything
    else. The room path is whatever the (possibly already patched) socket_path
    value in raw points at; tests that swap the canonical path must also patch
    ``control_plane.workspace_control_room_lifecycle._TRUSTED_SOCKET_PARENT_UID``.
    """
    import control_plane.workspace_control_room_lifecycle as lifecycle_mod
    from tests.executive_installed_control_fixture import unix_listener
    cache = {}

    def factory(name):
        if name == "WorkspaceControlRoom" and "workspace_control_room" in raw:
            if name not in cache:
                socket_path = raw["workspace_control_room"]["socket_path"]
                if os.path.exists(socket_path):
                    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                    listener.bind(socket_path)
                    os.chmod(socket_path, 0o600)
                    listener.listen(8)
                else:
                    listener, socket_path = unix_listener()
                    raw["workspace_control_room"]["socket_path"] = socket_path
                cache[name] = listener
            return cache[name]
        return object()

    return factory


def test_cleanup_policy_is_shared_contract_and_supervisor_reexport():
    assert CleanupPolicy is ContractCleanupPolicy


def test_default_config_and_factory_keep_dedicated_route(tmp_path, monkeypatch):
    raw = cli.load_control_config(_write(tmp_path, _raw(tmp_path)))
    assert not ({"fabric_bindings_path", "fabric_bindings_sha256", "fabric_bridge_armed"} & set(raw))
    _, supervisor, client = compose(tmp_path, monkeypatch, raw)
    assert type(supervisor.adapter) is broker.RemoteCodexWorkerAdapter
    assert type(supervisor.process_controller) is broker.RemoteWorkerProcessController
    assert supervisor.adapter.client is client
    assert supervisor.cleanup_policy is CleanupPolicy.DEDICATED_UID
    assert supervisor.require_complete_launch_attestation is False


def test_existing_remote_source_keeps_attempt_bound_route(tmp_path, monkeypatch):
    raw = cli.load_control_config(_write(tmp_path, _raw(tmp_path)))
    source = lambda host, worker: pytest.fail("No claim exists during composition")
    _, supervisor, _ = compose(tmp_path, monkeypatch, raw, remote_worker_binding_source=source)
    assert type(supervisor.adapter) is AttemptBoundRemoteWorkerAdapter
    assert supervisor.adapter.binding_source is source
    assert supervisor.cleanup_policy is CleanupPolicy.DEDICATED_UID


def test_valid_staged_config_is_data_only_and_preserves_default(tmp_path, monkeypatch, root_stats):
    raw = _raw(tmp_path)
    raw.update(staged(tmp_path, raw))
    loaded = cli.load_control_config(_write(tmp_path, raw))
    source = cli._staged_fabric_binding_source(loaded)
    assert type(source) is FabricBindingSource
    assert loaded["fabric_bridge_armed"] is False
    _, supervisor, _ = compose(tmp_path, monkeypatch, loaded)
    assert type(supervisor.adapter) is broker.RemoteCodexWorkerAdapter
    assert supervisor.cleanup_policy is CleanupPolicy.DEDICATED_UID


def test_trusted_in_process_factory_uses_exact_fabric_contract(tmp_path, monkeypatch, root_stats):
    raw = _raw(tmp_path)
    settings = staged(tmp_path, raw)
    source = FabricBindingSource.from_path(settings["fabric_bindings_path"], settings["fabric_bindings_sha256"])
    loaded = cli.load_control_config(_write(tmp_path, raw))
    service, mixed, client = compose(tmp_path, monkeypatch, loaded, fabric_worker_binding_source=source)
    assert type(mixed) is MixedExecutionOwnerSupervisor
    primary = mixed.primary
    assert type(primary.adapter) is broker.RemoteCodexWorkerAdapter
    assert primary.adapter.client is client
    assert primary.cleanup_policy is CleanupPolicy.DEDICATED_UID
    assert mixed.owners[service.config.worker_id] is primary
    for binding in source.bindings:
        owner = mixed.owners[binding.worker_id]
        assert type(owner.adapter) is AttendedFabricWorkerAdapter
        assert owner.adapter.runtime is mixed.runtime
        assert owner.adapter.binding_source is source
        assert owner.process_controller is owner.adapter
        assert owner.cleanup_policy is CleanupPolicy.FABRIC_PROCESS_GROUP
        assert owner.require_complete_launch_attestation is True
        assert owner.instance_id == primary.instance_id


def test_fabric_binding_cannot_replace_primary_worker(tmp_path, monkeypatch, root_stats):
    raw = _raw(tmp_path)
    settings = staged(tmp_path, raw)
    source = cli._staged_fabric_binding_source({**raw, **settings})
    raw["worker_id"] = source.bindings[0].worker_id
    monkeypatch.setattr(broker, "WorkerBrokerClient", lambda *args, **kwargs: pytest.fail("collision reached client"))
    with pytest.raises(cli.ServiceError, match="primary worker"):
        cli._service_from_config(raw, fabric_worker_binding_source=source)


@pytest.mark.parametrize("change", [
    {"fabric_bindings_path": "/Library/fabric.json"},
    {"fabric_bindings_sha256": "a" * 64},
    {"fabric_bridge_armed": "false"},
    {"fabric_bridge_armed": 0},
    {"fabric_bindings_path": "relative.json", "fabric_bindings_sha256": "a" * 64},
    {"fabric_bindings_path": "/var/../fabric.json", "fabric_bindings_sha256": "a" * 64},
    {"fabric_bindings_path": "/var//fabric.json", "fabric_bindings_sha256": "a" * 64},
    {"fabric_bindings_path": "/var/fabric.json", "fabric_bindings_sha256": "BAD"},
    {"fabric_bindings_path": "/var/fabric.json", "fabric_bindings_sha256": "A" * 64},
])
def test_malformed_config_refuses_without_service_effects(tmp_path, monkeypatch, change):
    monkeypatch.setattr(cli, "activate_launchd_socket", lambda *args: pytest.fail("Must refuse before socket activation"))
    with pytest.raises(cli.ServiceError):
        cli.load_control_config(_write(tmp_path, _raw(tmp_path, **change)))


@pytest.mark.parametrize("entrypoint", ["load", "factory", "serve"])
def test_true_arm_is_typed_refusal_before_live_construction(tmp_path, monkeypatch, entrypoint):
    raw = _raw(tmp_path, fabric_bridge_armed=True)
    def forbidden(*args, **kwargs):
        pytest.fail("Unqualified Fabric activation reached a live owner")
    monkeypatch.setattr(cli, "activate_launchd_socket", forbidden)
    monkeypatch.setattr(broker, "WorkerBrokerClient", forbidden)
    monkeypatch.setattr(cli, "_load_control_environment_attestation", forbidden)
    with pytest.raises(cli.FabricActivationRefused, match="backend and isolation profile"):
        if entrypoint == "load":
            cli.load_control_config(_write(tmp_path, raw))
        elif entrypoint == "factory":
            cli._service_from_config(raw)
        else:
            monkeypatch.setattr(cli, "load_control_config", lambda path: raw)
            asyncio.run(cli._serve_from_config(tmp_path / "control.json"))


def test_staged_wrong_hash_refuses_before_default_broker_boot(tmp_path, monkeypatch, root_stats):
    raw = _raw(tmp_path)
    raw.update(staged(tmp_path, raw))
    raw["fabric_bindings_sha256"] = "0" * 64
    monkeypatch.setattr(broker, "WorkerBrokerClient", lambda *args, **kwargs: pytest.fail("No broker call before validation"))
    with pytest.raises(cli.ServiceError, match="Staged Fabric binding source refused"):
        cli.load_control_config(_write(tmp_path, raw))


@pytest.mark.parametrize("source", [object(), lambda host, worker: None])
def test_factory_refuses_untrusted_source_before_clients(monkeypatch, source):
    monkeypatch.setattr(broker, "WorkerBrokerClient", lambda *args, **kwargs: pytest.fail("Invalid source reached client creation"))
    with pytest.raises(cli.ServiceError, match="exact root-installed binding source"):
        cli._service_from_config({}, fabric_worker_binding_source=source)


def test_fabric_conflicts_with_existing_remote_source(tmp_path, monkeypatch, root_stats):
    raw = _raw(tmp_path)
    settings = staged(tmp_path, raw)
    source = cli._staged_fabric_binding_source({**raw, **settings})
    monkeypatch.setattr(broker, "WorkerBrokerClient", lambda *args, **kwargs: pytest.fail("Conflicting source reached clients"))
    with pytest.raises(cli.ServiceError, match="sources conflict"):
        cli._service_from_config(raw, fabric_worker_binding_source=source,
                                 remote_worker_binding_source=lambda host, worker: None)


def test_fabric_owner_uses_its_physical_principal_without_rewriting_primary(tmp_path, monkeypatch, root_stats):
    raw = _raw(tmp_path)
    settings = staged(tmp_path, raw)
    source = cli._staged_fabric_binding_source({**raw, **settings})
    raw["worker_uid"] += 1
    raw["worker_gid"] += 2
    service, mixed, _ = compose(tmp_path, monkeypatch, raw, fabric_worker_binding_source=source)
    assert mixed.primary.worker_uid == raw['worker_uid']
    assert mixed.primary.worker_gid == raw['worker_gid']
    for physical in source.bindings:
        owner = mixed.owners[physical.worker_id]
        assert owner.worker_uid == physical.worker_uid
        assert owner.worker_gid == physical.worker_gid
        assert owner.shared_run_gid == raw['shared_run_gid']
        assert owner.instance_id == mixed.primary.instance_id
        assert owner.cleanup_policy is CleanupPolicy.FABRIC_PROCESS_GROUP


def test_conflicting_host_principals_for_same_worker_refuse_before_clients(tmp_path, monkeypatch, root_stats):
    raw = _raw(tmp_path)
    settings = staged(tmp_path, raw)
    path = Path(settings['fabric_bindings_path'])
    data = json.loads(path.read_text())
    other = dict(data['bindings'][0], host_ref='second-host', worker_uid=raw['worker_uid']+1)
    data['bindings'].append(other)
    contents = json.dumps(data).encode(); path.write_bytes(contents)
    settings['fabric_bindings_sha256'] = hashlib.sha256(contents).hexdigest()
    source = cli._staged_fabric_binding_source({**raw, **settings})
    monkeypatch.setattr(broker, 'WorkerBrokerClient', lambda *a, **kw: pytest.fail('ambiguous owner reached client'))
    with pytest.raises(cli.ServiceError, match='conflicting physical principals'):
        cli._service_from_config(raw, fabric_worker_binding_source=source)


def test_distinct_fabric_workers_keep_distinct_owners_and_local_group(tmp_path, monkeypatch, root_stats):
    raw = _raw(tmp_path)
    settings = staged(tmp_path, raw)
    path = Path(settings['fabric_bindings_path']); data = json.loads(path.read_text())
    first = data['bindings'][0]
    second = dict(first, host_ref='second-host', worker_id='second-worker', worker_uid=1000, worker_gid=1001)
    data['bindings'].append(second)
    contents = json.dumps(data).encode(); path.write_bytes(contents)
    settings['fabric_bindings_sha256'] = hashlib.sha256(contents).hexdigest()
    source = cli._staged_fabric_binding_source({**raw, **settings})
    _, mixed, _ = compose(tmp_path, monkeypatch, raw, fabric_worker_binding_source=source)
    a, b = (mixed.owners[p.worker_id] for p in source.bindings)
    assert a is not b and a is not mixed.primary and b is not mixed.primary
    assert (b.worker_uid,b.worker_gid)==(1000,1001)
    assert b.shared_run_gid == a.shared_run_gid == raw['shared_run_gid']
    assert a.runtime is b.runtime is mixed.runtime


def test_dedicated_worker_canary_cannot_promote_fabric_factory(tmp_path, monkeypatch, root_stats):
    raw = _raw(tmp_path)
    settings = staged(tmp_path, raw)
    source = cli._staged_fabric_binding_source({**raw, **settings})
    monkeypatch.setattr(broker, "WorkerBrokerClient", lambda *args, **kwargs: pytest.fail("Dedicated canary reached Fabric composition"))
    with pytest.raises(cli.FabricActivationRefused, match="dedicated-worker canary"):
        cli._service_from_config(raw, fabric_worker_binding_source=source, initial_canary={"passed": True})


def test_serve_validates_staged_file_before_canary_or_service(tmp_path, monkeypatch, root_stats):
    raw = _raw(tmp_path)
    raw.update(staged(tmp_path, raw))
    Path(raw["fabric_bindings_path"]).write_text("changed bytes")
    monkeypatch.setattr(cli, "load_control_config", lambda path: raw)
    monkeypatch.setattr(cli, "_load_control_environment_attestation", lambda *args, **kwargs: pytest.fail("Changed staged source reached attestation"))
    with pytest.raises(cli.ServiceError, match="Staged Fabric binding source refused"):
        asyncio.run(cli._serve_from_config(tmp_path / "control.json"))
