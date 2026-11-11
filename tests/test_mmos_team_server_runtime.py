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

import pytest

REPO = Path(__file__).resolve().parent.parent
TOOL = REPO / "tools" / "mmos_team_server" / "node_install.py"
loader = importlib.util.spec_from_file_location("node_install", TOOL)
node_install = importlib.util.module_from_spec(loader)
loader.loader.exec_module(node_install)

PREFIX = f"node-v{node_install.VERSION}-darwin-arm64"


@pytest.fixture
def inputs(tmp_path, monkeypatch):
    root = tmp_path / "server"
    root.mkdir(mode=0o700)
    archive = tmp_path / node_install.ARCHIVE
    checksum = tmp_path / "SHASUMS256.txt"
    with tarfile.open(archive, "w:gz") as tf:
        def file(name, body, mode=0o755):
            info = tarfile.TarInfo(name)
            info.size = len(body)
            info.mode = mode
            tf.addfile(info, io.BytesIO(body))
        file(PREFIX + "/bin/node", b"never-executed-test-fixture\n")
        file(PREFIX + "/lib/node_modules/npm/package.json", b"{}")
        link = tarfile.TarInfo(PREFIX + "/bin/npm")
        link.type = tarfile.SYMTYPE
        link.linkname = node_install.ALLOWED_LINKS["npm"]
        tf.addfile(link)
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    checksum.write_text(f"{digest}  {archive.name}\n")
    # The real installer still checks its immutable official Node 24.22.2
    # digest; the fixture must not ship a 50-MB executable to test that logic.
    monkeypatch.setattr(node_install, "OFFICIAL_SHA256", digest)
    return root, archive, checksum


def hostile_archive(tmp_path, member_builder):
    """Write an archive under the pinned prefix plus one hostile member."""
    archive = tmp_path / node_install.ARCHIVE
    with tarfile.open(archive, "w:gz") as tf:
        ok = tarfile.TarInfo(PREFIX + "/bin/node")
        ok.size = 1
        ok.mode = 0o755
        tf.addfile(ok, io.BytesIO(b"x"))
        member_builder(tf)
    return archive


def members_of(archive):
    with tarfile.open(archive, "r:gz") as tf:
        return node_install.checked_members(tf, PREFIX)


class TestInstall:
    def test_install_publishes_receipt_inside_destination_atomically(self, inputs, capsys):
        root, archive, checksum = inputs
        receipt = node_install.install_node(str(root), str(archive), str(checksum))
        destination = root / "runtime" / PREFIX
        # F1: the receipt traveled inside the staged tree; one rename published
        # tree and receipt together.
        in_tree = destination / "INSTALL_RECEIPT.json"
        assert in_tree.is_file()
        assert json.loads(in_tree.read_text())["schemaVersion"] == 1  # F2
        assert json.loads(in_tree.read_text())["nodePath"] == receipt["nodePath"]
        # activation markers carry the same payload
        config = json.loads((root / "config" / "node-runtime.json").read_text())
        assert config["schemaVersion"] == 1
        assert (root / "runtime" / "install-receipt.json").read_text() == in_tree.read_text()
        assert Path(receipt["nodePath"]).stat().st_mode & stat.S_IXUSR
        assert (root / "runtime" / "install-receipt.json").stat().st_mode & 0o077 == 0
        # staging is REALLY empty after success — no copy, no leftovers
        assert os.listdir(root / "runtime" / "staging") == []
        assert list(root.glob("runtime/.node-install-*")) == []
        assert "NODE_INSTALLED version=v24.22.2" in capsys.readouterr().out

    def test_retry_after_publish_repairs_activation(self, inputs, capsys):
        root, archive, checksum = inputs
        node_install.install_node(str(root), str(archive), str(checksum))
        # an interruption after the publish but before activation:
        (root / "config" / "node-runtime.json").unlink()
        node_install.install_node(str(root), str(archive), str(checksum))
        assert "activation repaired" in capsys.readouterr().out
        assert json.loads((root / "config" / "node-runtime.json").read_text())["schemaVersion"] == 1

    def test_destination_with_foreign_receipt_refused(self, inputs):
        root, archive, checksum = inputs
        node_install.install_node(str(root), str(archive), str(checksum))
        in_tree = root / "runtime" / PREFIX / "INSTALL_RECEIPT.json"
        in_tree.write_text("{}\n")
        with pytest.raises(node_install.InstallError, match="without this exact receipt"):
            node_install.install_node(str(root), str(archive), str(checksum))

    def test_invalid_checksum_file_rejected(self, inputs):
        root, archive, checksum = inputs
        checksum.write_text("not-a-checksum\n")
        with pytest.raises(node_install.InstallError, match="exact archive entry"):
            node_install.install_node(str(root), str(archive), str(checksum))
        checksum.write_text("b" * 65 + "  " + archive.name + "\n")
        with pytest.raises(node_install.InstallError, match="invalid checksum"):
            node_install.install_node(str(root), str(archive), str(checksum))

    def test_duplicate_shasums_entry_rejected(self, inputs):
        root, archive, checksum = inputs
        line = checksum.read_text()
        checksum.write_text(line + line)
        with pytest.raises(node_install.InstallError, match="one exact archive entry"):
            node_install.install_node(str(root), str(archive), str(checksum))

    def test_tampered_archive_rejected_before_any_destination(self, inputs):
        root, archive, checksum = inputs
        archive.write_bytes(archive.read_bytes() + b"tampered")
        with pytest.raises(node_install.InstallError, match="tampered archive"):
            node_install.install_node(str(root), str(archive), str(checksum))
        assert not list(root.glob("runtime/node-v*"))
        # F5's tamper check runs on the private copy; nothing leaked to staging
        if (root / "runtime" / "staging").exists():
            assert os.listdir(root / "runtime" / "staging") == []

    def test_symlinked_install_directory_rejected(self, inputs, tmp_path):
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

    def test_symlinked_root_rejected_before_realpath(self, inputs, tmp_path, monkeypatch):
        # F4: a symlinked root must be refused on its own spelling, before any
        # realpath could relocate the check onto its (harmless) target.
        root, archive, checksum = inputs
        real = tmp_path / "real-root"
        real.mkdir(mode=0o700)
        link = tmp_path / "linked-root"
        link.symlink_to(real, target_is_directory=True)
        with pytest.raises(node_install.InstallError, match="symlinked directory"):
            node_install.install_node(str(link), str(archive), str(checksum))

    def test_scope_refusal_follows_resolved_path(self, inputs, tmp_path, monkeypatch):
        # F4: the ~/.t3 scope refusal applies to the RESOLVED root. A root
        # reached through an intermediate symlink into a fake HOME's ~/.t3 is
        # refused even though its own spelling never mentions .t3.
        root, archive, checksum = inputs
        fake_home = tmp_path / "fake-home"
        (fake_home / ".t3" / "elsewhere" / "server").mkdir(parents=True, mode=0o700)
        monkeypatch.setenv("HOME", str(fake_home))
        link = tmp_path / "work"
        link.symlink_to(fake_home / ".t3" / "elsewhere", target_is_directory=True)
        with pytest.raises(node_install.InstallError, match="out of scope"):
            node_install.install_node(str(link / "server"),
                                      str(archive), str(checksum))

    def test_scope_refusal_creates_no_t3_directory(self, inputs, tmp_path, monkeypatch):
        # Attack finding 4: the ~/.t3 scope check runs on the lexical realpath
        # BEFORE makedirs, so a refused root never leaves a created ~/.t3/<x>
        # behind.
        root, archive, checksum = inputs
        fake_home = tmp_path / "fresh-home"
        fake_home.mkdir(mode=0o700)
        monkeypatch.setenv("HOME", str(fake_home))
        with pytest.raises(node_install.InstallError, match="out of scope"):
            node_install.install_node(str(fake_home / ".t3" / "team"),
                                      str(archive), str(checksum))
        assert not (fake_home / ".t3").exists()

    def test_retry_repair_refuses_tampered_tree(self, inputs):
        # Attack finding 5: a receipt planted over a DIFFERENT tree must not be
        # blessed by the repair branch; the treeSha256 in the receipt is
        # verified against the tree actually on disk.
        root, archive, checksum = inputs
        node_install.install_node(str(root), str(archive), str(checksum))
        target = root / "runtime" / PREFIX / "bin" / "node"
        target.write_text("replaced-by-attacker\n")
        target.chmod(0o700)
        with pytest.raises(node_install.InstallError, match="tree no longer matches"):
            node_install.install_node(str(root), str(archive), str(checksum))
        # a receipt with wrong fixed fields is refused as not-this-receipt
        planted = root / "runtime" / PREFIX / "INSTALL_RECEIPT.json"
        original = json.loads(planted.read_text())
        original["version"] = "v0.0.0"
        planted.write_text(json.dumps(original, indent=2) + "\n")
        with pytest.raises(node_install.InstallError, match="without this exact receipt"):
            node_install.install_node(str(root), str(archive), str(checksum))
        # even a FULLY forged receipt — correct fields plus a treeSha256
        # recomputed over the tampered tree — refuses: the published tree must
        # still be byte-identical to a fresh extraction of the official archive.
        forged = json.loads(planted.read_text())
        forged["version"] = "v" + node_install.VERSION
        forged["treeSha256"] = node_install.tree_sha256(root / "runtime" / PREFIX)
        planted.write_text(json.dumps(forged, indent=2) + "\n")
        with pytest.raises(node_install.InstallError, match="fresh extraction"):
            node_install.install_node(str(root), str(archive), str(checksum))

    def test_retry_repair_verifies_and_reports_tree(self, inputs, capsys):
        # The honest repair path names what it verified (attack finding 5).
        root, archive, checksum = inputs
        node_install.install_node(str(root), str(archive), str(checksum))
        (root / "config" / "node-runtime.json").unlink()
        node_install.install_node(str(root), str(archive), str(checksum))
        assert "activation repaired; tree verified" in capsys.readouterr().out

    def test_foreign_uid_input_rejected(self, inputs, monkeypatch):
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

    def test_owned_loose_subdir_tightened_not_refused(self, inputs):
        # A legacy root's 0755 runtime/config subdirs are tightened to 0700 by
        # the create path (the tool owns them); the root itself still refuses
        # when loose — that tightening is the operator's explicit act.
        root, archive, checksum = inputs
        root.chmod(0o755)
        with pytest.raises(node_install.InstallError, match="must be mode 0700"):
            node_install.install_node(str(root), str(archive), str(checksum))
        root.chmod(0o700)
        (root / "config").mkdir(mode=0o755)
        node_install.install_node(str(root), str(archive), str(checksum))
        assert stat.S_IMODE((root / "config").stat().st_mode) == 0o700

    def test_half_finished_staging_rejected(self, inputs):
        root, archive, checksum = inputs
        (root / "runtime/staging/.node-install-unfinished").mkdir(parents=True, mode=0o700)
        for p in (root / "runtime", root / "runtime/staging"):
            p.chmod(0o700)
        with pytest.raises(node_install.InstallError, match="half-finished"):
            node_install.install_node(str(root), str(archive), str(checksum))
        assert not (root / "config/node-runtime.json").exists()


class TestCheckedMembers:
    def test_relative_archive_traversal_rejected(self, tmp_path):
        archive = tmp_path / node_install.ARCHIVE
        with tarfile.open(archive, "w:gz") as tf:
            info = tarfile.TarInfo(PREFIX + "/bin/../../outside")
            info.size = 1
            tf.addfile(info, io.BytesIO(b"x"))
        with pytest.raises(node_install.InstallError, match="archive member"):
            members_of(archive)

    def test_escaping_symlink_rejected(self, tmp_path):
        archive = hostile_archive(tmp_path, lambda tf: tf.addfile(_sym(
            PREFIX + "/bin/evil", "../../../etc/passwd")))
        with pytest.raises(node_install.InstallError, match="escaping archive link"):
            members_of(archive)

    def test_absolute_link_rejected(self, tmp_path):
        archive = hostile_archive(tmp_path, lambda tf: tf.addfile(_sym(
            PREFIX + "/lib/abs", "/etc/passwd")))
        with pytest.raises(node_install.InstallError, match="unsafe archive link"):
            members_of(archive)

    def test_hardlink_rejected(self, tmp_path):
        def add_hardlink(tf):
            info = tarfile.TarInfo(PREFIX + "/bin/hard")
            info.type = tarfile.LNKTYPE
            info.linkname = PREFIX + "/bin/node"
            tf.addfile(info)
        archive = hostile_archive(tmp_path, add_hardlink)
        with pytest.raises(node_install.InstallError, match="hardlink, device or special"):
            members_of(archive)

    def test_device_member_rejected(self, tmp_path):
        def add_device(tf):
            info = tarfile.TarInfo(PREFIX + "/dev/zero")
            info.type = tarfile.CHRTYPE
            info.devmajor, info.devminor = 1, 5
            tf.addfile(info)
        archive = hostile_archive(tmp_path, add_device)
        with pytest.raises(node_install.InstallError, match="hardlink, device or special"):
            members_of(archive)

    def test_privileged_mode_rejected(self, tmp_path):
        def add_setuid(tf):
            info = tarfile.TarInfo(PREFIX + "/bin/rootme")
            info.size = 1
            info.mode = 0o4755
            tf.addfile(info, io.BytesIO(b"x"))
        archive = hostile_archive(tmp_path, add_setuid)
        with pytest.raises(node_install.InstallError, match="privileged archive mode"):
            members_of(archive)

    def test_member_budget_enforced(self, tmp_path, monkeypatch):
        monkeypatch.setattr(node_install, "MEMBER_BUDGET", 2)
        archive = hostile_archive(tmp_path, lambda tf: [
            tf.addfile(tarfile.TarInfo(f"{PREFIX}/lib/f{i}"), io.BytesIO(b"x"))
            for i in range(3)])
        with pytest.raises(node_install.InstallError, match="budget"):
            members_of(archive)

    def test_byte_budget_enforced(self, tmp_path, monkeypatch):
        monkeypatch.setattr(node_install, "BYTE_BUDGET", 4)
        def add_big(tf):
            info = tarfile.TarInfo(PREFIX + "/lib/big")
            info.size = 16
            tf.addfile(info, io.BytesIO(b"x" * 16))
        archive = hostile_archive(tmp_path, add_big)
        with pytest.raises(node_install.InstallError, match="budget"):
            members_of(archive)

    def test_bin_link_target_mismatch_rejected(self, tmp_path):
        archive = hostile_archive(tmp_path, lambda tf: tf.addfile(_sym(
            PREFIX + "/bin/npm", "../lib/node_modules/npm/bin/evil.js")))
        with pytest.raises(node_install.InstallError, match="target mismatch"):
            members_of(archive)

    def test_unknown_bin_link_rejected(self, tmp_path):
        archive = hostile_archive(tmp_path, lambda tf: tf.addfile(_sym(
            PREFIX + "/bin/extra", "../lib/node_modules/npm/bin/npm-cli.js")))
        with pytest.raises(node_install.InstallError, match="unexpected archive link"):
            members_of(archive)


def _sym(name, target):
    info = tarfile.TarInfo(name)
    info.type = tarfile.SYMTYPE
    info.linkname = target
    return info


def fake_runtime(tmp_path):
    """A root whose receipts name an in-root node and a complete fake dist."""
    root = tmp_path / "server"
    root.mkdir(mode=0o700)
    install_dir = root / "runtime" / PREFIX
    (install_dir / "bin").mkdir(parents=True)
    node = install_dir / "bin" / "node"
    node.write_text("#!/bin/sh\n")
    node.chmod(0o700)
    build = root / "runtime" / "packed" / "dist"
    for name in node_install.REQUIRED_DIST_FILES:
        target = build / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("x")
    node_receipt = {
        "schemaVersion": 1, "version": "v" + node_install.VERSION,
        "archiveSha256": node_install.OFFICIAL_SHA256,
        "nodePath": str(node), "installDir": str(install_dir),
    }
    server_receipt = {
        "schemaVersion": 1, "serverBin": str(build / "bin.mjs"),
        "buildDir": str(build),
    }
    (root / "config").mkdir()
    (root / "config" / "node-runtime.json").write_text(json.dumps(node_receipt))
    (root / "config" / "server-runtime.json").write_text(json.dumps(server_receipt))
    return root, node, build


class TestRuntimePaths:
    def test_valid_runtime_resolves(self, tmp_path):
        root, node, build = fake_runtime(tmp_path)
        assert node_install.runtime_paths(str(root)) == (str(node), str(build / "bin.mjs"))

    def test_wrong_schema_version_rejected(self, tmp_path):
        root, _, _ = fake_runtime(tmp_path)
        receipt = json.loads((root / "config" / "server-runtime.json").read_text())
        receipt["schemaVersion"] = 2
        (root / "config" / "server-runtime.json").write_text(json.dumps(receipt))
        with pytest.raises(node_install.InstallError, match="unsupported runtime receipt"):
            node_install.runtime_paths(str(root))

    def test_symlinked_node_rejected(self, tmp_path):
        root, node, _ = fake_runtime(tmp_path)
        node.unlink()
        elsewhere = tmp_path / "elsewhere-node"
        elsewhere.write_text("#!/bin/sh\n")
        elsewhere.chmod(0o700)
        node.symlink_to(elsewhere)
        with pytest.raises(node_install.InstallError, match="must not be a symlink"):
            node_install.runtime_paths(str(root))

    def test_non_executable_node_rejected(self, tmp_path):
        root, node, _ = fake_runtime(tmp_path)
        node.chmod(0o600)
        with pytest.raises(node_install.InstallError, match="not executable"):
            node_install.runtime_paths(str(root))

    def test_missing_sibling_file_rejected(self, tmp_path):
        root, _, build = fake_runtime(tmp_path)
        (build / "client" / "index.html").unlink()
        with pytest.raises(node_install.InstallError, match="missing client/index.html"):
            node_install.runtime_paths(str(root))

    def test_missing_server_bin_rejected(self, tmp_path):
        root, _, build = fake_runtime(tmp_path)
        (build / "bin.mjs").unlink()
        # F6: the refusal comes from resolve, not at launchd start time.
        with pytest.raises(node_install.InstallError, match="entrypoint is missing"):
            node_install.runtime_paths(str(root))

    def test_escape_outside_root_rejected(self, tmp_path):
        root, _, _ = fake_runtime(tmp_path)
        receipt = json.loads((root / "config" / "node-runtime.json").read_text())
        outside = tmp_path / "outside"
        outside.mkdir()
        receipt["installDir"] = str(outside)
        receipt["nodePath"] = str(outside / "bin" / "node")
        (root / "config" / "node-runtime.json").write_text(json.dumps(receipt))
        with pytest.raises(node_install.InstallError, match="escapes the server root"):
            node_install.runtime_paths(str(root))

    def test_nodepath_install_dir_crosscheck(self, tmp_path):
        root, node, _ = fake_runtime(tmp_path)
        receipt = json.loads((root / "config" / "node-runtime.json").read_text())
        receipt["nodePath"] = str(root / "runtime" / PREFIX / "bin" / "node2")
        (root / "config" / "node-runtime.json").write_text(json.dumps(receipt))
        with pytest.raises(node_install.InstallError,
                           match="does not resolve to installDir/bin/node"):
            node_install.runtime_paths(str(root))

    def test_resolve_validates_root_like_install(self, tmp_path, monkeypatch):
        # F8: resolve applies install's root validation, not a weaker one.
        root, _, _ = fake_runtime(tmp_path)
        assert node_install.resolve_command(str(root), "node").endswith("/bin/node")
        fake_home = tmp_path / "fake-home"
        (fake_home / ".t3" / "x").mkdir(parents=True, mode=0o700)
        monkeypatch.setenv("HOME", str(fake_home))
        with pytest.raises(node_install.InstallError, match="out of scope"):
            node_install.resolve_command(str(fake_home / ".t3" / "x"), "node")


class TestDoctor:
    def test_doctor_prints_only_metadata(self, tmp_path):
        from unittest.mock import patch
        root = tmp_path / "server"
        root.mkdir(mode=0o700)
        with patch.object(node_install, "runtime_paths",
                          side_effect=node_install.InstallError("missing packed runtime")):
            assert node_install.doctor(str(root), "com.mastermind.t3-team-dev-tsh") == 1
        assert "run/access.txt" not in str(node_install.doctor.__code__.co_consts)

    def test_doctor_never_executes_the_installed_node(self, tmp_path, capsys):
        # Attack finding 6: doctor attests provenance and must never execute
        # the binary under inspection; the version is receipt-attested.
        # launchctl probing is allowed; running the node path is not.
        from unittest.mock import Mock, patch
        root, node, _ = fake_runtime(tmp_path)
        (root / "run").mkdir()
        (root / "run" / "port").write_text("50809\n")
        def guard(argv, **kwargs):
            assert list(argv)[0] != node, f"doctor executed the installed binary: {argv}"
            return Mock(returncode=1, stdout="")
        with patch.object(node_install.subprocess, "run", side_effect=guard):
            node_install.doctor(str(root), "com.mastermind.t3-team-dev-tsh")
        out = capsys.readouterr().out
        assert "nodeExecCheck=skipped-receipt-attested" in out
        assert f"nodeVersion=v{node_install.VERSION}" in out

    def test_attack_reproducer_exists(self):
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
