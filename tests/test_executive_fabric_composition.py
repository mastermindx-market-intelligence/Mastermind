"""Hostile composition inputs; fixture ownership metadata only, never chown."""
import copy
import dataclasses
import hashlib
import json
import os
import stat
from pathlib import Path
from types import SimpleNamespace

import pytest

from control_plane import executive_fabric_composition as module


def binding():
    return dict(socket_path="/var/run/mastermind/fabric.sock", host_ref="host-" + "1" * 64,
        worker_id="worker-1", worker_uid=1001, worker_gid=1001, provider="fixture",
        model="fixture-model", worker_source_config_digest="2" * 64,
        execution_profile_digest="3" * 64, service_source_sha256="4" * 64,
        provider_home="/srv/fabric/provider", binary_sha256="e" * 64,
        permission_profile_sha256="f" * 64, bridge_uid=501)


def document():
    return dict(schema_version=module.CONFIG_SCHEMA_VERSION, bindings=[binding()])


def altered(info, **changes):
    values = {name: getattr(info, name) for name in
        ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns",
         "st_uid", "st_gid", "st_mode", "st_nlink")}
    return SimpleNamespace(**{**values, **changes})


@pytest.fixture
def root_stats(monkeypatch):
    original_lstat, original_fstat = Path.lstat, os.fstat
    def root_lstat(path):
        info = original_lstat(path)
        changes = {"st_uid": 0}
        if stat.S_ISDIR(info.st_mode):
            changes["st_mode"] = info.st_mode & ~0o022
        return altered(info, **changes)
    monkeypatch.setattr(module.Path, "lstat", root_lstat)
    monkeypatch.setattr(module.os, "fstat", lambda fd: altered(original_fstat(fd), st_uid=0))


def installed(tmp_path, raw=None):
    path = tmp_path / "bindings.json"
    raw = json.dumps(document()).encode() if raw is None else raw
    path.write_bytes(raw)
    path.chmod(0o600)
    return path, hashlib.sha256(raw).hexdigest()


def test_exact_lookup_and_immutable_bindings(tmp_path, root_stats):
    path, digest = installed(tmp_path)
    source = module.FabricBindingSource.from_path(path, digest)
    assert source.bindings == (module.FabricHostBinding(**binding()),)
    assert source(binding()["host_ref"], "worker-1") is source.bindings[0]
    with pytest.raises(dataclasses.FrozenInstanceError):
        source.expected_sha256 = "0" * 64
    with pytest.raises(TypeError):
        source._index[("other", "worker")] = source.bindings[0]


@pytest.mark.parametrize("host,worker", [
    ("missing", "worker-1"), (binding()["host_ref"], "missing"),
    (binding()["host_ref"] + " ", "worker-1"), (None, "worker-1"),
])
def test_missing_or_altered_exact_key_refuses(tmp_path, root_stats, host, worker):
    path, digest = installed(tmp_path)
    source = module.FabricBindingSource.from_path(path, digest)
    with pytest.raises(module.FabricCompositionError):
        source(host, worker)


@pytest.mark.parametrize("mutate", [
    lambda d: d.update(factory="os.system"),
    lambda d: d.update(schema_version="other/v1"),
    lambda d: d.update(bindings=[]),
    lambda d: d.update(bindings={}),
    lambda d: d["bindings"][0].update(import_path="arbitrary.code"),
    lambda d: d["bindings"][0].pop("bridge_uid"),
    lambda d: d["bindings"][0].update(bridge_uid=0),
    lambda d: d["bindings"][0].update(bridge_uid=True),
    lambda d: d["bindings"][0].update(worker_uid=True),
    lambda d: d["bindings"][0].update(worker_gid=0),
    lambda d: d["bindings"][0].update(socket_path="relative.sock"),
    lambda d: d["bindings"][0].update(socket_path="/var/run/../other.sock"),
    lambda d: d["bindings"][0].update(socket_path="/var//run/socket"),
    lambda d: d["bindings"][0].update(provider_home="/srv/./home"),
    lambda d: d["bindings"][0].update(provider_home="/srv/\x00home"),
    lambda d: d["bindings"][0].update(host_ref=" leading-space"),
    lambda d: d["bindings"][0].update(model="injected\ncommand"),
    lambda d: d["bindings"][0].update(service_source_sha256="not-a-hash"),
    lambda d: d["bindings"].append(copy.deepcopy(d["bindings"][0])),
])
def test_hostile_closed_schema_and_paths_refuse(tmp_path, root_stats, mutate):
    data = document()
    mutate(data)
    path, digest = installed(tmp_path, json.dumps(data).encode())
    with pytest.raises(module.FabricCompositionError):
        module.FabricBindingSource.from_path(path, digest)


@pytest.mark.parametrize("raw", [
    b'{"schema_version":"one","schema_version":"two","bindings":[]}',
    b'{"schema_version":"x","bindings":[{"worker_uid":1,"worker_uid":2}]}',
    b'{"schema_version":"x","bindings":[NaN]}',
    b'{"schema_version":"x","bindings":[Infinity]}',
    b'{"schema_version":"x","bindings":[1e999]}',
    b'{"schema_version":"x","bindings":["\\ud800"]}',
    b'\xff', b'{} trailing',
])
def test_duplicate_nonfinite_and_invalid_json_refuse(tmp_path, root_stats, raw):
    path, digest = installed(tmp_path, raw)
    with pytest.raises(module.FabricCompositionError):
        module.FabricBindingSource.from_path(path, digest)


@pytest.mark.parametrize("expected", ["bad", "F" * 64, True, None])
def test_invalid_approved_hash_refuses(tmp_path, root_stats, expected):
    path, _ = installed(tmp_path)
    with pytest.raises(module.FabricCompositionError):
        module.FabricBindingSource.from_path(path, expected)


def test_hash_checked_before_binding_construction(tmp_path, root_stats, monkeypatch):
    path, _ = installed(tmp_path)
    def forbidden(**kwargs):
        pytest.fail("Binding construction occurred before approved hash check")
    monkeypatch.setattr(module, "FabricHostBinding", forbidden)
    with pytest.raises(module.FabricCompositionError, match="hash"):
        module.FabricBindingSource.from_path(path, "0" * 64)


@pytest.mark.parametrize("mode", [0o620, 0o602, 0o666])
def test_group_or_world_writable_file_refuses(tmp_path, root_stats, mode):
    path, digest = installed(tmp_path)
    path.chmod(mode)
    with pytest.raises(module.FabricCompositionError, match="protected file"):
        module.FabricBindingSource.from_path(path, digest)


def test_non_root_file_refuses(tmp_path, root_stats, monkeypatch):
    path, digest = installed(tmp_path)
    original = module.os.fstat
    monkeypatch.setattr(module.os, "fstat", lambda fd: altered(original(fd), st_uid=501))
    with pytest.raises(module.FabricCompositionError, match="root-owned"):
        module.FabricBindingSource.from_path(path, digest)


@pytest.mark.parametrize("changes", [{"st_uid": 501}, {"st_mode": stat.S_IFDIR | 0o777}])
def test_untrusted_parent_namespace_refuses(tmp_path, root_stats, monkeypatch, changes):
    path, digest = installed(tmp_path)
    original = module.Path.lstat
    def untrusted(item):
        info = original(item)
        return altered(info, **changes) if item == path.parent else info
    monkeypatch.setattr(module.Path, "lstat", untrusted)
    with pytest.raises(module.FabricCompositionError, match="parent"):
        module.FabricBindingSource.from_path(path, digest)


def test_symlink_final_and_parent_refuse(tmp_path, root_stats):
    path, digest = installed(tmp_path)
    link = tmp_path / "link.json"
    link.symlink_to(path)
    with pytest.raises(module.FabricCompositionError, match="symlink"):
        module.FabricBindingSource.from_path(link, digest)
    directory = tmp_path / "link-dir"
    directory.symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(module.FabricCompositionError, match="parent"):
        module.FabricBindingSource.from_path(directory / path.name, digest)


@pytest.mark.parametrize("raw", [b"", b" " * (module.MAX_CONFIG_BYTES + 1)])
def test_empty_or_oversized_file_refuses(tmp_path, root_stats, raw):
    path, digest = installed(tmp_path, raw)
    with pytest.raises(module.FabricCompositionError, match="bounded"):
        module.FabricBindingSource.from_path(path, digest)


def test_nonregular_file_refuses_without_opening_fifo(tmp_path, root_stats):
    path = tmp_path / "fifo"
    os.mkfifo(path)
    with pytest.raises(module.FabricCompositionError, match="regular file"):
        module.FabricBindingSource.from_path(path, "0" * 64)


@pytest.mark.parametrize("change", ["bytes", "replacement", "metadata", "deleted", "permissions"])
def test_lookup_rereads_original_pinned_source(tmp_path, root_stats, change):
    path, digest = installed(tmp_path)
    source = module.FabricBindingSource.from_path(path, digest)
    raw = path.read_bytes()
    if change == "bytes":
        data = document()
        data["bindings"][0]["model"] = "changed-model"
        path.write_text(json.dumps(data))
    elif change == "replacement":
        alternate = tmp_path / "replacement"
        alternate.write_bytes(raw)
        alternate.chmod(0o600)
        alternate.replace(path)
    elif change == "metadata":
        info = path.stat()
        os.utime(path, ns=(info.st_atime_ns, info.st_mtime_ns + 1))
    elif change == "permissions":
        path.chmod(0o666)
    else:
        path.unlink()
    with pytest.raises(module.FabricCompositionError):
        source(binding()["host_ref"], "worker-1")


def test_relative_config_path_refuses(tmp_path, root_stats):
    with pytest.raises(module.FabricCompositionError, match="absolute"):
        module.FabricBindingSource.from_path("bindings.json", "0" * 64)
