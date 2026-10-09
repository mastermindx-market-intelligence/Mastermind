import json
import os
from pathlib import Path

import pytest

from integrations.mastermind_browser_plugin.native_host_install import (
    build_native_host_install_plan,
)
from integrations.mastermind_browser_plugin.native_host_materializer import (
    BrowserNativeHostMaterializeError,
    materialize_native_host,
)

EXTENSION_ID = "abcdefghijklmnopabcdefghijklmnop"


def plan(tmp_path: Path):
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    python = runtime / "python3"
    bridge = runtime / "bridge.py"
    python.write_bytes(b"#!/bin/sh\n")
    bridge.write_text("# bridge fixture\n")
    os.chmod(python, 0o700)
    os.chmod(bridge, 0o600)
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    return build_native_host_install_plan(
        extension_id=EXTENSION_ID,
        python_executable=str(python),
        bridge_path=str(bridge),
        enrollment_path=str(config_dir / "enrollment.json"),
        owner_socket_path=str(config_dir / "owner.sock"),
    )


def test_materializes_exact_launcher_enrollment_and_chrome_manifest(tmp_path):
    p = plan(tmp_path)
    native_dir = tmp_path / "NativeMessagingHosts"
    receipt = materialize_native_host(
        p,
        native_manifest_dir=native_dir,
        expected_owner_uid=os.getuid(),
    )
    assert receipt.applied is True
    assert receipt.is_browser_registration is False
    assert receipt.is_extension_installation is False
    assert receipt.host_manifest_path == str(
        native_dir / "com.mastermind.browser_link.json"
    )

    launcher = Path(p.launcher_path)
    enrollment = Path(p.enrollment_path)
    manifest = Path(receipt.host_manifest_path)
    assert launcher.read_text() == p.launcher_source
    assert json.loads(enrollment.read_text()) == p.enrollment
    assert json.loads(manifest.read_text()) == p.host_manifest
    assert launcher.stat().st_mode & 0o777 == 0o700
    assert enrollment.stat().st_mode & 0o777 == 0o600
    assert manifest.stat().st_mode & 0o777 == 0o644
    assert receipt.launcher_sha256
    assert receipt.enrollment_sha256
    assert receipt.host_manifest_sha256


def test_second_identical_materialization_is_idempotent(tmp_path):
    p = plan(tmp_path)
    native_dir = tmp_path / "NativeMessagingHosts"
    first = materialize_native_host(
        p, native_manifest_dir=native_dir, expected_owner_uid=os.getuid()
    )
    second = materialize_native_host(
        p, native_manifest_dir=native_dir, expected_owner_uid=os.getuid()
    )
    assert first == second


def test_conflicting_existing_file_refuses_without_partial_overwrite(tmp_path):
    p = plan(tmp_path)
    native_dir = tmp_path / "NativeMessagingHosts"
    native_dir.mkdir()
    manifest = native_dir / "com.mastermind.browser_link.json"
    manifest.write_text('{"foreign":true}\n')
    before = manifest.read_bytes()

    with pytest.raises(BrowserNativeHostMaterializeError):
        materialize_native_host(
            p, native_manifest_dir=native_dir, expected_owner_uid=os.getuid()
        )

    assert manifest.read_bytes() == before
    assert not Path(p.launcher_path).exists()
    assert not Path(p.enrollment_path).exists()


def test_foreign_existing_launcher_refuses_before_any_other_effect(tmp_path):
    p = plan(tmp_path)
    launcher = Path(p.launcher_path)
    launcher.write_text("#!/bin/sh\nexit 9\n")
    before = launcher.read_bytes()

    with pytest.raises(BrowserNativeHostMaterializeError):
        materialize_native_host(
            p,
            native_manifest_dir=tmp_path / "NativeMessagingHosts",
            expected_owner_uid=os.getuid(),
        )

    assert launcher.read_bytes() == before
    assert not Path(p.enrollment_path).exists()
    assert not (tmp_path / "NativeMessagingHosts").exists()


def test_symlink_and_non_directory_targets_refuse(tmp_path):
    p = plan(tmp_path)
    real = tmp_path / "real-native"
    real.mkdir()
    link = tmp_path / "NativeMessagingHosts"
    link.symlink_to(real, target_is_directory=True)
    with pytest.raises(BrowserNativeHostMaterializeError):
        materialize_native_host(
            p, native_manifest_dir=link, expected_owner_uid=os.getuid()
        )

    bad = tmp_path / "not-dir"
    bad.write_text("x")
    with pytest.raises(BrowserNativeHostMaterializeError):
        materialize_native_host(
            p, native_manifest_dir=bad, expected_owner_uid=os.getuid()
        )


def test_wrong_owner_and_bool_uid_refuse(tmp_path):
    p = plan(tmp_path)
    native_dir = tmp_path / "NativeMessagingHosts"
    for uid in (True, os.getuid() + 1):
        with pytest.raises(BrowserNativeHostMaterializeError):
            materialize_native_host(
                p, native_manifest_dir=native_dir, expected_owner_uid=uid
            )


def test_missing_or_non_regular_runtime_inputs_refuse(tmp_path):
    p = plan(tmp_path)
    native_dir = tmp_path / "NativeMessagingHosts"

    Path(p.bridge_path).unlink()
    with pytest.raises(BrowserNativeHostMaterializeError):
        materialize_native_host(
            p, native_manifest_dir=native_dir, expected_owner_uid=os.getuid()
        )

    Path(p.bridge_path).mkdir()
    with pytest.raises(BrowserNativeHostMaterializeError):
        materialize_native_host(
            p, native_manifest_dir=native_dir, expected_owner_uid=os.getuid()
        )


def test_materializer_never_starts_chrome_or_browser_owner(tmp_path, monkeypatch):
    p = plan(tmp_path)
    called = []

    def forbidden(*args, **kwargs):
        called.append((args, kwargs))
        raise AssertionError("process launch forbidden")

    monkeypatch.setattr(os, "system", forbidden)
    receipt = materialize_native_host(
        p,
        native_manifest_dir=tmp_path / "NativeMessagingHosts",
        expected_owner_uid=os.getuid(),
    )
    assert receipt.applied is True
    assert called == []
