"""Actual realm/source/route consumers; only OS custody is virtualized.

No service, credential read, reference issuance, provider call or admission.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import types

import pytest

from control_plane import codex_provider_realm as realm
from control_plane import executive_fabric_composition as composition
from control_plane.executive_fabric_adapter import FabricHostBinding
from ops.executive_os.provider_realm_facts import NativeRealmIdentityObservation
from tests.test_native_subscription_capacity_enrollment import bound, encode, sha
from tests.test_subscription_realm_owner import enrolled


@pytest.fixture
def current(bound, monkeypatch, tmp_path):
    owner = bound.publish()
    binary = types.SimpleNamespace(sha256="d" * 64)
    monkeypatch.setattr(realm, "_observe_attended_claude_binary", lambda *args: binary)
    path = tmp_path / "bindings.json"
    route = dataclasses.asdict(FabricHostBinding(
        socket_path=str(tmp_path / "fixture.sock"),
        host_ref=bound.f.config["native_capacity_enrollment"]["host_ref"],
        worker_id="minimax-finite-01", worker_uid=470, worker_gid=470,
        bridge_uid=470, provider="minimax", model="MiniMax-M3",
        provider_home=str(bound.f.home), worker_source_config_digest=owner._config_sha256,
        execution_profile_digest="a" * 64, service_source_sha256="b" * 64,
        binary_sha256=binary.sha256, permission_profile_sha256="c" * 64))
    original_read = composition._read_pinned

    def protected_read(selected, expected):
        # Virtualize root ownership only. Real bytes/digest/inode, closed JSON,
        # route parser and repeated lookup all remain production behavior.
        raw = selected.read_bytes()
        if sha(raw) != expected:
            raise composition.FabricCompositionError("fixture source changed")
        return raw, composition._identity(selected.stat())

    monkeypatch.setattr(composition, "_read_pinned", protected_read)

    def publish():
        path.write_bytes(encode({"schema_version": composition.CONFIG_SCHEMA_VERSION,
                                 "bindings": [route]}))
        return {"bindings_path": path, "bindings_sha256": sha(path.read_bytes()),
                "host_ref": route["host_ref"]}

    return types.SimpleNamespace(bound=bound, owner=owner, binary=binary, route=route,
        path=path, publish=publish, original_read=original_read)


def test_current_worker_join_and_callback_do_not_read_credentials(current, monkeypatch):
    args = current.publish()
    credential_inode = current.bound.f.credential.stat().st_ino
    read = os.read

    def no_secret(fd, count):
        assert os.fstat(fd).st_ino != credential_inode
        return read(fd, count)

    monkeypatch.setattr(realm.os, "read", no_secret)
    value = current.owner.observe_current_identity(**args)
    assert type(value) is NativeRealmIdentityObservation
    assert value.host_ref == current.route["host_ref"]
    assert value.os_principal_ref == "principal-" + "2" * 64
    assert value.config_custody_ref == "custody-" + "3" * 64
    assert value.generation == 2
    assert value.source_config_sha256 == current.owner._config_sha256
    assert value.provider_binary_sha256 == current.binary.sha256
    assert str(current.bound.f.home) not in json.dumps(dataclasses.asdict(value))
    assert current.owner.require_current_identity(**args,
        os_principal_ref=value.os_principal_ref) is None
    with pytest.raises(realm.ProviderRealmError):
        current.owner.require_current_identity(**args, os_principal_ref="principal-" + "4" * 64)


@pytest.mark.parametrize("field,value", [
    ("host_ref", "host-" + "9" * 64), ("worker_id", "foreign-worker"),
    ("worker_uid", 471), ("worker_gid", 471), ("bridge_uid", 471),
    ("provider_home", "/foreign/home"), ("provider", "claude"),
    ("worker_source_config_digest", "9" * 64), ("binary_sha256", "9" * 64),
])
def test_wrong_physical_route_never_establishes_identity(current, field, value):
    current.route[field] = value
    with pytest.raises(realm.ProviderRealmError):
        current.owner.observe_current_identity(**current.publish())


def test_actual_worker_principal_is_required_even_with_valid_receipts(current, monkeypatch):
    args = current.publish()
    monkeypatch.setattr(realm.os, "geteuid", lambda: 471)
    with pytest.raises(realm.ProviderRealmError):
        current.owner.observe_current_identity(**args)


def test_route_change_during_acquisition_refuses(current, monkeypatch):
    args = current.publish()
    read = composition._read_pinned
    calls = []

    def changed(path, expected):
        value = read(path, expected)
        calls.append(1)
        if len(calls) == 1:
            current.path.write_bytes(b"{}")
        return value

    monkeypatch.setattr(composition, "_read_pinned", changed)
    with pytest.raises(realm.ProviderRealmError):
        current.owner.observe_current_identity(**args)


def test_root_config_change_during_acquisition_refuses(current, monkeypatch):
    args = current.publish()
    read = composition._read_pinned

    def changed(path, expected):
        value = read(path, expected)
        current.bound.f.path.write_bytes(b"{}")
        return value

    monkeypatch.setattr(composition, "_read_pinned", changed)
    with pytest.raises(realm.ProviderRealmError):
        current.owner.observe_current_identity(**args)


def test_untrusted_route_file_and_unsealed_owner_are_not_bearer_authority(current, monkeypatch):
    args = current.publish()
    monkeypatch.setattr(composition, "_read_pinned", current.original_read)
    with pytest.raises(realm.ProviderRealmError):
        current.owner.observe_current_identity(**args)
    fake = dataclasses.replace(current.owner, _seal=object())
    with pytest.raises(realm.ProviderRealmError):
        fake.observe_current_identity(**args)
