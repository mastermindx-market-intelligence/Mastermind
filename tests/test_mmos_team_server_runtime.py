"""Pure TSH runtime install/doctor tests (no network, launchd or credentials)."""
import hashlib
import importlib.util
import io
import json
import os
import stat
import subprocess
import tarfile
from pathlib import Path
from unittest.mock import patch

import pytest

REPO = Path(__file__).resolve().parent.parent
TOOL = REPO / "tools" / "mmos_team_server" / "node_install.py"
loader = importlib.util.spec_from_file_location("node_install", TOOL)
node_install = importlib.util.module_from_spec(loader)
loader.loader.exec_module(node_install)


@pytest.fixture
def inputs(tmp_path, monkeypatch):
    root = tmp_path / "server"
    root.mkdir(mode=0o700)
    archive = tmp_path / node_install.ARCHIVE
    checksum = tmp_path / "SHASUMS256.txt"
    prefix = f"node-v{node_install.VERSION}-darwin-arm64"
    with tarfile.open(archive, "w:gz") as tf:
        def file(name, body, mode=0o755):
            info = tarfile.TarInfo(name)
            info.size = len(body)
            info.mode = mode
            tf.addfile(info, io.BytesIO(body))
        file(prefix + "/bin/node", b"never-executed-test-fixture\n")
        file(prefix + "/lib/node_modules/npm/package.json", b"{}")
        link = tarfile.TarInfo(prefix + "/bin/npm")
        link.type = tarfile.SYMTYPE
        link.linkname = "../lib/node_modules/npm/bin/npm-cli.js"
        tf.addfile(link)
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    checksum.write_text(f"{digest}  {archive.name}\n")
    # The real installer still checks its immutable official Node 24.22.2
    # digest; the fixture must not ship a 50-MB executable to test that logic.
    monkeypatch.setattr(node_install, "OFFICIAL_SHA256", digest)
    return root, archive, checksum


def test_install_private_atomic_receipt(inputs, capsys):
    root, archive, checksum = inputs
    receipt = node_install.install_node(str(root), str(archive), str(checksum))
    assert receipt["version"] == "v24.22.2"
    assert receipt["archiveSha256"] == hashlib.sha256(archive.read_bytes()).hexdigest()
    assert Path(receipt["nodePath"]).stat().st_mode & stat.S_IXUSR
    assert (root / "runtime/install-receipt.json").stat().st_mode & 0o077 == 0
    assert not list((root / "runtime/staging").iterdir())
    assert "NODE_INSTALLED version=v24.22.2" in capsys.readouterr().out
    with pytest.raises(node_install.InstallError, match="already exists"):
        node_install.install_node(str(root), str(archive), str(checksum))


def test_invalid_checksum_file_rejected(inputs):
    root, archive, checksum = inputs
    checksum.write_text("not-a-checksum\n")
    with pytest.raises(node_install.InstallError, match="exact archive entry"):
        node_install.install_node(str(root), str(archive), str(checksum))
    checksum.write_text("b" * 65 + "  " + archive.name + "\n")
    with pytest.raises(node_install.InstallError, match="invalid checksum"):
        node_install.install_node(str(root), str(archive), str(checksum))


def test_tampered_archive_rejected(inputs):
    root, archive, checksum = inputs
    archive.write_bytes(archive.read_bytes() + b"tampered")
    with pytest.raises(node_install.InstallError, match="tampered archive"):
        node_install.install_node(str(root), str(archive), str(checksum))
    assert not list(root.glob("runtime/node-v*"))


def test_symlinked_install_directory_rejected(inputs, tmp_path):
    root, archive, checksum = inputs
    outside = tmp_path / "outside"
    outside.mkdir()
    (root / "runtime").symlink_to(outside, target_is_directory=True)
    with pytest.raises(node_install.InstallError, match="symlinked directory"):
        node_install.install_node(str(root), str(archive), str(checksum))
    root2 = tmp_path / "root-link"
    root2.symlink_to(tmp_path / "other-private", target_is_directory=True)
    with pytest.raises(node_install.InstallError, match="symlinked directory"):
        node_install.install_node(str(root2), str(archive), str(checksum))


def test_foreign_uid_input_rejected(inputs, monkeypatch):
    root, archive, checksum = inputs
    real_stat = os.stat
    def foreign(path, **kwargs):
        result = real_stat(path, **kwargs)
        if os.path.abspath(path) == str(archive):
            values = tuple(result)
            return result.__class__(values[:4] + (0,) + values[5:])
        return result
    monkeypatch.setattr(node_install.os, "lstat", foreign)
    with pytest.raises(node_install.InstallError, match="another user"):
        node_install.install_node(str(root), str(archive), str(checksum))


def test_half_finished_staging_rejected(inputs):
    root, archive, checksum = inputs
    (root / "runtime/staging/.node-install-unfinished").mkdir(parents=True, mode=0o700)
    for p in (root / "runtime", root / "runtime/staging"):
        p.chmod(0o700)
    with pytest.raises(node_install.InstallError, match="half-finished"):
        node_install.install_node(str(root), str(archive), str(checksum))
    assert not (root / "config/node-runtime.json").exists()


def test_relative_archive_traversal_rejected(tmp_path):
    archive = tmp_path / node_install.ARCHIVE
    prefix = f"node-v{node_install.VERSION}-darwin-arm64"
    with tarfile.open(archive, "w:gz") as tf:
        info = tarfile.TarInfo(prefix + "/bin/../../outside")
        info.size = 1
        tf.addfile(info, io.BytesIO(b"x"))
    with pytest.raises(node_install.InstallError, match="archive member"):
        node_install.checked_members(str(archive))


def test_partial_runtime_rejected(tmp_path):
    root = tmp_path / "root"
    (root / "config").mkdir(parents=True, mode=0o700)
    node = tmp_path / "node"
    node.write_text("#!/bin/sh\n")
    node.chmod(0o700)
    base = {"schemaVersion": 1, "version": "v" + node_install.VERSION,
            "archiveSha256": node_install.OFFICIAL_SHA256,
            "nodePath": str(node), "installDir": str(tmp_path / "node-dir")}
    (root / "config/node-runtime.json").write_text(json.dumps(base))
    (root / "config/server-runtime.json").write_text(
        json.dumps({"schemaVersion": 1, "serverBin": str(tmp_path / "dist/bin.mjs"),
                    "buildDir": str(tmp_path / "dist")}))
    with pytest.raises(node_install.InstallError, match="outside"):
        node_install.runtime_paths(str(root))


def test_doctor_prints_only_metadata(tmp_path):
    root = tmp_path / "server"
    root.mkdir(mode=0o700)
    with patch.object(node_install, "runtime_paths",
                      side_effect=node_install.InstallError("missing packed runtime")):
        assert node_install.doctor(str(root), "com.mastermind.t3-team-dev-tsh") == 1
    assert "run/access.txt" not in str(node_install.doctor.__code__.co_consts)


def test_attack_reproducer_exists():
    attack = (REPO / "tools/mmos_team_server/attack_tsh_node_install.py").read_text()
    for scenario in ("tampered-archive", "invalid-checksum", "symlink-directory",
                     "foreign-owner", "half-finished"):
        assert scenario in attack
    r = subprocess.run(["/opt/homebrew/bin/python3.12", "-I", str(TOOL),
                        "install", "--root", "/nonexistent-root",
                        "--archive", "/missing", "--checksum", "/missing"],
                       capture_output=True, text=True)
    assert r.returncode == 1
    assert "team_runtime:" in r.stderr
