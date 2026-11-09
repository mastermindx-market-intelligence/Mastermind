"""Entry custody behavior with explicit synthetic OS/runtime boundaries.

These cases exercise the real callback and refusal ordering. They do not
attest a host, execute a provider, or replace the actual Linux qualification.
"""
from __future__ import annotations

import copy
import os
from types import SimpleNamespace

import pytest

from tests.test_hermes_isolated_entry import INSTALLATION, Proxy, owner_module


@pytest.fixture
def custody_world(tmp_path):
    owner = owner_module()
    installation = copy.deepcopy(INSTALLATION)
    image_path = tmp_path / "approved-image"
    image_path.write_bytes(b"synthetic executable image")
    descriptor = os.open(image_path, os.O_RDONLY)
    info = os.fstat(descriptor)
    state = {
        "pid": 4242, "manifest": "a" * 64, "calls": [],
        "image": {
            "boot_id": "12345678-1234-1234-1234-123456789abc",
            "start_identity": "1234", "real_uid": 993, "effective_uid": 993,
            "real_gid": 980, "effective_gid": 980,
            "device": info.st_dev, "inode": info.st_ino, "mode": info.st_mode,
            "uid": info.st_uid, "gid": info.st_gid, "size": info.st_size,
            "mtime_ns": info.st_mtime_ns, "ctime_ns": info.st_ctime_ns,
            "sha256": installation["launch_python"]["sha256"],
        },
    }

    class ProcessError(RuntimeError):
        pass

    def inspect(pid):
        assert pid == 4242
        state["calls"].append(("image", pid))
        if state.get("process_error"):
            raise ProcessError("synthetic refused process")
        return dict(state["image"])

    process = SimpleNamespace(LinuxProcessIdentityError=ProcessError,
                              inspect_linux_process_image=inspect)
    owner.importlib = Proxy(owner.importlib, import_module=lambda name: process)
    owner.os = Proxy(owner.os, getpid=lambda: state["pid"],
                     getuid=lambda: 993, geteuid=lambda: 993,
                     getgid=lambda: 980, getegid=lambda: 980)
    owner.sys = Proxy(owner.sys, platform="linux", version_info=(3, 12, 0),
                      implementation=SimpleNamespace(name="cpython"),
                      executable=installation["launch_python"]["path"],
                      prefix="/usr", exec_prefix="/usr",
                      base_prefix="/usr", base_exec_prefix="/usr",
                      modules={name: None for name in owner._HERMES_SITE_NAMES},
                      flags=SimpleNamespace(isolated=1, no_site=1, no_user_site=1,
                                            dont_write_bytecode=1, safe_path=True))
    owner._HERMES_EARLY_NO_SITE = True
    source = SimpleNamespace(manifest_sha256=lambda: state["manifest"])
    finder = SimpleNamespace(check=lambda: state["calls"].append(("source",)))
    runtime = SimpleNamespace(launch_fd=descriptor,
                              check=lambda: state["calls"].append(("runtime",)))
    world = SimpleNamespace(owner=owner, installation=installation, source=source,
                            finder=finder, runtime=runtime, state=state)
    try:
        yield world
    finally:
        os.close(descriptor)


def observe(world):
    return world.owner._main_custody_observer(
        world.source, world.finder, world.runtime, world.installation)


def test_callback_qualifies_immediately_and_returns_fresh_closed_measurements(custody_world):
    w = custody_world
    callback = observe(w)
    assert sum(x[0] == "image" for x in w.state["calls"]) == 1
    first, second = callback(), callback()
    assert first == second and first is not second
    assert first == {
        "pid": 4242, "start_ticks": "1234", "uid": 993, "gid": 980,
        "manifest_sha256": "a" * 64,
        "image_sha256": INSTALLATION["launch_python"]["sha256"],
    }
    assert w.state["calls"][-2:] == [("runtime",), ("source",)]


@pytest.mark.parametrize("name", ["prefix", "exec_prefix", "base_prefix", "base_exec_prefix",
                                   "executable"])
def test_actual_startup_drift_refuses_before_another_image_read(custody_world, name):
    w = custody_world
    callback = observe(w)
    before = len(w.state["calls"])
    w.owner.sys.overrides[name] = "/foreign"
    with pytest.raises(w.owner.ReleaseManifestError, match="actual startup"):
        callback()
    assert not any(row[0] == "image" for row in w.state["calls"][before:])


@pytest.mark.parametrize("field,value", [
    ("device", 987654321), ("inode", 987654321), ("mode", 0),
    ("uid", 12345), ("gid", 12345), ("size", 987654321),
    ("mtime_ns", 0), ("ctime_ns", 0), ("sha256", "0" * 64),
    ("real_uid", 4242), ("effective_uid", 4242),
    ("real_gid", 4242), ("effective_gid", 4242),
])
def test_actual_kernel_image_and_principals_must_match_held_runtime(custody_world, field, value):
    w = custody_world
    callback = observe(w)
    w.state["image"][field] = value
    with pytest.raises(w.owner.ReleaseManifestError, match="custody differs"):
        callback()


@pytest.mark.parametrize("field,value", [
    ("start_identity", "9999"),
    ("boot_id", "00000000-1234-1234-1234-123456789abc"),
])
def test_main_birth_identity_cannot_change(custody_world, field, value):
    w = custody_world
    callback = observe(w)
    w.state["image"][field] = value
    with pytest.raises(w.owner.ReleaseManifestError, match="custody changed"):
        callback()


@pytest.mark.parametrize("mutation", ["fork", "manifest", "site", "early-policy", "no-site"])
def test_custody_cannot_be_rebound_or_backfilled(custody_world, mutation):
    w = custody_world
    callback = observe(w)
    if mutation == "fork":
        w.state["pid"] += 1
    elif mutation == "manifest":
        w.state["manifest"] = "b" * 64
    elif mutation == "site":
        w.owner.sys.modules["site"] = object()
    elif mutation == "early-policy":
        w.owner._HERMES_EARLY_NO_SITE = False
    else:
        w.owner.sys.flags.no_site = 0
    with pytest.raises(w.owner.ReleaseManifestError):
        callback()


def test_callback_detaches_the_validated_installation_input(custody_world):
    w = custody_world
    callback = observe(w)
    w.installation["roles"][0]["uid"] = 4242
    w.installation["launch_python"]["sha256"] = "0" * 64
    assert callback()["uid"] == 993
    assert callback()["image_sha256"] == INSTALLATION["launch_python"]["sha256"]


def test_unavailable_self_image_refuses_the_initial_callback(custody_world):
    w = custody_world
    w.state["process_error"] = True
    with pytest.raises(w.owner.ReleaseManifestError, match="main process is unavailable"):
        observe(w)


def test_late_dispatch_refuses_before_source_or_runtime_acquisition(custody_world):
    w = custody_world
    w.owner._HERMES_EARLY_NO_SITE = False
    def forbidden(*args, **kwargs):
        pytest.fail("late dispatch reached source acquisition")
    w.owner._HeldReleaseSources = forbidden
    with pytest.raises(w.owner.ReleaseManifestError, match="early isolated"):
        w.owner._hermes_runtime(["supervise"])
