"""Real file-publication checks; systemd and privileged metadata are fixture inputs."""
from __future__ import annotations

import dataclasses
import hashlib
import os
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest

from test_linux_secondary_worker_enrollment import ROOT, _identities, _load
from test_hermes_installed_source_join import (
    INSTALLATION, Proxy, _root_info, _write_manifest, release,
)


@pytest.fixture
def world(release, tmp_path, monkeypatch):
    m = _load()
    _write_manifest(release, INSTALLATION)
    units = tmp_path / "units"
    units.mkdir()
    unit = units / m._GATEWAY_UNIT
    before = b"[Unit]\nDescription=original inert gateway\n"
    unit.write_bytes(before)
    unit.chmod(0o644)
    config_path = tmp_path / "preserved-config.json"
    raw = b"original protected configuration"
    config_path.write_bytes(raw)
    config = SimpleNamespace(
        hermes_role_metadata_read=SimpleNamespace(implementation_sha=release.name))
    args = m.Args(
        source_repo=ROOT, expected_sha="b" * 40, expected_tree="c" * 40,
        component="hermes-host-observation", hermes_runtime=INSTALLATION,
        expected_gateway_unit_sha256=hashlib.sha256(before).hexdigest(),
    )
    monkeypatch.setattr(m, "UNIT_ROOT", units)
    monkeypatch.setattr(m, "RELEASES_ROOT", release.parent)
    ancestors = {(p.stat().st_dev, p.stat().st_ino) for p in units.parents}
    monkeypatch.setattr(m, "os", Proxy(
        os,
        stat=lambda *a, **k: _root_info(os.stat(*a, **k), ancestors),
        fstat=lambda fd: _root_info(os.fstat(fd), ancestors),
        fchown=lambda *_: None,
    ))
    monkeypatch.setattr(m, "_observation_input", lambda *_: (raw, config))
    monkeypatch.setattr(m, "_observation_config_adoption",
                        lambda observed, _: config_path.read_bytes() == observed)
    state = {
        "Id": m._GATEWAY_UNIT, "LoadState": "loaded", "ActiveState": "inactive",
        "SubState": "dead", "UnitFileState": "static", "MainPID": "0",
        "ControlPID": "0", "Job": "", "FragmentPath": str(unit), "DropInPaths": "",
    }
    calls = []
    def run(argv, **kwargs):
        calls.append(argv)
        assert argv[:3] == ["/usr/bin/systemctl", "show", "--no-pager"]
        return subprocess.CompletedProcess(
            argv, 0, "".join(f"{key}={value}\n" for key, value in state.items()).encode(), b"")
    monkeypatch.setattr(m, "_run", run)
    return SimpleNamespace(m=m, args=args, raw=raw, config=config, identities=_identities(m),
                           unit=unit, before=before, config_path=config_path, state=state,
                           calls=calls, release=release)


def test_exact_inert_unit_replacement_preserves_config_and_remains_single_use(world):
    w = world
    inode = w.unit.stat().st_ino
    config_identity = (w.config_path.stat().st_ino, w.config_path.read_bytes())
    with w.m._InertGatewayReplacement(w.args, w.raw, w.config, w.identities) as predecessor:
        after = predecessor.desired
        w.m._write_root_unit(w.unit, after, predecessor=predecessor)
        assert predecessor.published
        assert predecessor.replacement_sha256 == hashlib.sha256(after).hexdigest()
        with pytest.raises(w.m.EnrollmentError, match="already_consumed"):
            predecessor.publish(w.unit, after)
    assert w.unit.read_bytes() == after
    assert w.unit.stat().st_ino != inode
    assert (w.config_path.stat().st_ino, w.config_path.read_bytes()) == config_identity
    assert len(w.calls) >= 3
    assert not list(w.unit.parent.glob(f".{w.m._GATEWAY_UNIT}.*"))
    with pytest.raises(w.m.EnrollmentError, match="systemd_unit_conflict"):
        w.m._write_root_unit(w.unit, b"unspecified replacement")


@pytest.mark.parametrize("property,value", [
    ("ActiveState", "active"), ("MainPID", "42"), ("ControlPID", "42"),
    ("Job", "19"), ("DropInPaths", "/tmp/override.conf"), ("UnitFileState", "enabled"),
])
def test_active_or_modified_manager_state_refuses_before_publication(world, property, value):
    w = world
    w.state[property] = value
    with pytest.raises(w.m.EnrollmentError, match="not_inert"):
        w.m._InertGatewayReplacement(w.args, w.raw, w.config, w.identities)
    assert w.unit.read_bytes() == w.before


def test_wrong_predecessor_digest_and_role_input_refuse(world):
    w = world
    for args, reason in (
        (dataclasses.replace(w.args, expected_gateway_unit_sha256="0" * 64), "unit_conflict"),
        (dataclasses.replace(w.args, hermes_runtime=None), "role_input_conflict"),
    ):
        with pytest.raises(w.m.EnrollmentError, match=reason):
            w.m._InertGatewayReplacement(args, w.raw, w.config, w.identities)
    assert w.unit.read_bytes() == w.before


@pytest.mark.parametrize("change", ["unit", "config", "active"])
def test_drift_after_preflight_never_overwrites_the_original_target(world, change):
    w = world
    with w.m._InertGatewayReplacement(w.args, w.raw, w.config, w.identities) as predecessor:
        expected_unit = w.before
        if change == "unit":
            expected_unit = b"another writer's selected bytes"
            w.unit.write_bytes(expected_unit)
        elif change == "config":
            w.config_path.write_bytes(b"another config")
        else:
            w.state["MainPID"] = "99"
        with pytest.raises(w.m.EnrollmentError):
            predecessor.publish(w.unit, predecessor.desired)
        assert not predecessor.published
    assert w.unit.read_bytes() == expected_unit
    assert not list(w.unit.parent.glob(f".{w.m._GATEWAY_UNIT}.*"))


def test_concurrent_predecessor_owner_refuses_without_replacing(world):
    w = world
    with w.m._InertGatewayReplacement(w.args, w.raw, w.config, w.identities):
        with pytest.raises(w.m.EnrollmentError, match="unqualified"):
            w.m._InertGatewayReplacement(w.args, w.raw, w.config, w.identities)
    assert w.unit.read_bytes() == w.before


def test_wrong_target_refuses_even_with_valid_predecessor(world):
    w = world
    with w.m._InertGatewayReplacement(w.args, w.raw, w.config, w.identities) as predecessor:
        with pytest.raises(w.m.EnrollmentError, match="target_invalid"):
            predecessor.publish(w.unit.parent / "another.service", b"no")
    assert w.unit.read_bytes() == w.before


def test_predecessor_flag_is_closed_to_observation_component(monkeypatch):
    m = _load()
    monkeypatch.setattr(m, "apply_enrollment",
                        lambda *_: pytest.fail("invalid CLI reached enrollment"))
    common = ["--source-repo", "/root/source", "--expected-sha", "a" * 40,
              "--expected-tree", "b" * 40]
    assert m.main(common + [
        "--codex-source-binary", "/tmp/codex", "--codex-version", "0.157.1",
        "--codex-sha256", "c" * 64, "--expected-gateway-unit-sha256", "d" * 64,
    ]) == 64
    assert m.main(common + [
        "--component", "hermes-host-observation", "--gateway-config-file", "/tmp/input",
        "--gateway-config-sha256", "c" * 64, "--expected-gateway-unit-sha256", "wrong",
    ]) == 64

def test_lost_completion_recovers_exact_postimage_without_another_replace(world, monkeypatch):
    w = world
    real_fsync = os.fsync
    with w.m._InertGatewayReplacement(w.args, w.raw, w.config, w.identities) as predecessor:
        def fail_after_replace(fd):
            if predecessor.published:
                raise OSError("injected directory sync interruption")
            return real_fsync(fd)
        with monkeypatch.context() as scoped:
            scoped.setattr(w.m.os, "fsync", fail_after_replace)
            with pytest.raises(w.m.EnrollmentError, match="postimage_requires_reconciliation"):
                predecessor.publish(w.unit, predecessor.desired)
        assert predecessor.published
        after = predecessor.desired
    inode = w.unit.stat().st_ino
    assert w.unit.read_bytes() == after
    with w.m._InertGatewayReplacement(w.args, w.raw, w.config, w.identities) as recovered:
        assert recovered.recovered and recovered.published
        monkeypatch.setattr(w.m.os, "replace",
                            lambda *a, **k: pytest.fail("recovery rewrote the unit"))
        recovered.publish(w.unit, recovered.desired)
        assert recovered.replacement_sha256 == hashlib.sha256(after).hexdigest()
    assert w.unit.stat().st_ino == inode


@pytest.mark.parametrize("change", ["source", "unit", "config"])
def test_drift_during_final_observation_does_not_produce_a_success_receipt(world, monkeypatch, change):
    from ops.executive_os.release_manifest import MANIFEST_NAME
    w = world
    run = w.m._run
    with w.m._InertGatewayReplacement(w.args, w.raw, w.config, w.identities) as predecessor:
        def final_observation(argv, **kwargs):
            result = run(argv, **kwargs)
            if predecessor.published:
                if change == "source":
                    (w.release / MANIFEST_NAME).chmod(0o644)
                elif change == "unit":
                    data = w.unit.read_bytes()
                    w.unit.unlink()
                    w.unit.write_bytes(data)
                else:
                    w.config_path.write_bytes(b"changed during observation")
            return result
        monkeypatch.setattr(w.m, "_run", final_observation)
        with pytest.raises(w.m.EnrollmentError, match="postimage_requires_reconciliation"):
            predecessor.publish(w.unit, predecessor.desired)
        assert predecessor.published
        assert predecessor.replacement_sha256 is None
