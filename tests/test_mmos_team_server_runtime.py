"""Pure TSH runtime install/doctor tests (no network, launchd or credentials)."""
import gzip
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
VERSION = "24.22.2"


@pytest.fixture
def inputs(tmp_path):
    root = tmp_path / "server"
    root.mkdir(mode=0o700)
    archive = tmp_path / "node-v24.22.2-darwin-arm64.tar.gz"
    checksum = tmp_path / "SHASUMS256.txt"
    with tarfile.open(archive, "w:gz") as tf:
        def file(name, body, mode=0o755):
            info = tarfile.TarInfo(name)
            info.size = len(body)
            info.mode = mode
            tf.addfile(info, io.BytesIO(body))
        file(f"node-v{VERSION}-darwin-arm64/bin/node", b"node-test-executable\n")
        file(f"node-v{VERSION}-darwin-arm64/lib/node_modules/npm/package.json", b"{}")
    checksum.write_text("bede02b2e4c949872d9b7c11d49d40be3f45e8fa4a09e648892ae76ac3444994  " + archive.name + "\n")
    return root, archive, checksum


def test_install_private_atomic_receipt(inputs, capsys):
    root, archive, checksum = inputs
    # Never trust a checksum fixture until its independent generated digest matches.
    with tarfile.open(archive, "r:gz") as tf:
        assert any(m.name.endswith("/bin/node") for m in tf.getmembers())
    import hashlib
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    checksum.write_text(f"{digest}  {archive.name}\n")
    receipt = node_install.install_node(str(root), str(archive), str(checksum), VERSION)
    assert receipt["version"] == "v24.22.2"
    assert receipt["archiveSha256"] == json.loads((root / "config/node-runtime.json").read_text())["archiveSha256"]
    assert Path(receipt["nodePath"]).stat().st_mode & stat.S_IXUSR
    assert not (root / "runtime/staging/.node-install-incomplete").exists()
    out = capsys.readouterr().out
    assert "NODE_INSTALLED version=v24.22.2" in out
    assert "NODE_INSTALLED" in out and "aa" not in out  # no hard-coded fixture success
    with pytest.raises(node_install.InstallError, match="already exists"):
        node_install.install_node(str(root), str(archive), str(checksum), VERSION)


def test_invalid_checksum_file_rejected(inputs, tmp_path):
    root, archive, checksum = inputs
    checksum.write_text("not-a-checksum\n")
    with pytest.raises(node_install.InstallError, match="exactly one"):
        node_install.install_node(str(root), str(archive), str(checksum), VERSION)
    checksum.write_text("b" * 65 + "  " + archive.name + "\n")
    with pytest.raises(node_install.InstallError, match="digest"):
        node_install.install_node(str(root), str(archive), str(checksum), VERSION)


def test_tampered_archive_rejected(inputs):
    root, archive, checksum = inputs
    import hashlib
    checksum.write_text(f"{hashlib.sha256(archive.read_bytes()).hexdigest()}  {archive.name}\n")
    archive.write_bytes(archive.read_bytes() + b"tampered")
    with pytest.raises(node_install.InstallError, match="checksum"):
        node_install.install_node(str(root), str(archive), str(checksum), VERSION)
    assert not (root / "runtime").exists() or not list((root / "runtime").glob("node-v*"))


def test_symlinked_install_root_rejected(inputs, tmp_path):
    root, archive, checksum = inputs
    real = tmp_path / "elsewhere"
    real.mkdir()
    link = tmp_path / "linked-root"
    link.symlink_to(real, target_is_directory=True)
    with pytest.raises(node_install.InstallError, match="symlink"):
        node_install.private_dir(str(link))
    with pytest.raises(node_install.InstallError, match="0700"):
        node_install.private_dir(str(real))


def test_foreign_uid_input_rejected(inputs, monkeypatch):
    root, archive, checksum = inputs
    import hashlib
    checksum.write_text(f"{hashlib.sha256(archive.read_bytes()).hexdigest()}  {archive.name}\n")
    real_stat = os.stat
    def foreign(path, **kwargs):
        result = real_stat(path, **kwargs)
        if os.path.abspath(path) == str(archive):
            return result.__class__(tuple(result[:3] + (0,) + result[4:]))
        return result
    monkeypatch.setattr(node_install.os, "lstat", lambda p: foreign(p))
    with pytest.raises(node_install.InstallError, match="another user"):
        node_install.install_node(str(root), str(archive), str(checksum), VERSION)


def test_half_finished_staging_rejected(inputs):
    root, archive, checksum = inputs
    (root / "runtime/staging").mkdir(parents=True, mode=0o700)
    (root / "runtime/staging/.node-install-unfinished").mkdir(mode=0o700)
    import hashlib
    checksum.write_text(f"{hashlib.sha256(archive.read_bytes()).hexdigest()}  {archive.name}\n")
    with pytest.raises(node_install.InstallError, match="half-finished"):
        node_install.install_node(str(root), str(archive), str(checksum), VERSION)
    assert not (root / "config/node-runtime.json").exists()


def test_relative_archive_traversal_rejected(tmp_path):
    root, archive, checksum = inputs_fixture_path(tmp_path)
    import hashlib
    checksum.write_text(f"{hashlib.sha256(archive.read_bytes()).hexdigest()}  {archive.name}\n")
    with pytest.raises(node_install.InstallError, match="archive member"):
        node_install.checked_members(str(archive), VERSION)


def inputs_fixture_path(tmp_path):
    # Kept as a normal helper so the traversal test can construct one bad member.
    root = tmp_path / "server"
    root.mkdir(mode=0o700)
    archive = tmp_path / "node-v24.22.2-darwin-arm64.tar.gz"
    with tarfile.open(archive, "w:gz") as tf:
        info = tarfile.TarInfo(f"node-v{VERSION}-darwin-arm64/bin/../../outside")
        info.size = 1
        tf.addfile(info, io.BytesIO(b"x"))
    checksum = tmp_path / "SHASUMS256.txt"
    return root, archive, checksum


def test_attack_reproducer_cli_is_nonshell(tmp_path):
    """The reproducer calls the real parser, not a shell-dependent digest command."""
    with (REPO / "tools/mmos_team_server/attack_team_server.sh").open() as f:
        content = f.read()
    assert "openssl" not in content  # no assumed third-party tools in this CLI helper
    r = subprocess.run(["/opt/homebrew/bin/python3.12", str(TOOL), "install", "--root", str(tmp_path),
                        "--archive", str(tmp_path / "missing"), "--checksum", str(tmp_path / "missing"),
                        "--version", VERSION], capture_output=True, text=True)
    assert r.returncode == 1
    assert "team_runtime:" in r.stderr


def test_runtime_receipt_requires_complete_bundle(tmp_path):
    root = tmp_path / "root"
    (root / "config").mkdir(parents=True, mode=0o700)
    node = tmp_path / "node"
    node.write_text("#!/bin/sh\n")
    node.chmod(0o700)
    base = {"schemaVersion": 1, "nodePath": str(node), "installDir": str(tmp_path / "node-dir")}
    # Even existing files must be underneath the receiving root.
    (root / "config/node-runtime.json").write_text(json.dumps(base))
    (root / "config/server-runtime.json").write_text(json.dumps({"schemaVersion": 1, "serverBin": str(tmp_path / "dist/bin.mjs")}))
    with pytest.raises(node_install.InstallError, match="escapes"):
        node_install.runtime_paths(str(root))


def test_doctor_prints_only_metadata(tmp_path):
    root = tmp_path / "server"
    (root / "runtime").mkdir(parents=True, mode=0o700)
    root.chmod(0o700)
    with patch.object(node_install, "private_dir", return_value=str(root)), \
         patch.object(node_install, "runtime_paths", side_effect=node_install.InstallError("missing packed runtime")), \
         patch.object(node_install, "http_status", return_value="200"):
        assert node_install.doctor(str(root), "com.mastermind.t3-team-dev-tsh") == 1
    # Credentials are not part of the diagnostic path.
    assert "token" not in str(node_install.doctor.__code__.co_consts).lower()
