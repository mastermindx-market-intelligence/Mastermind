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
        assert json.loads(in_tree.read_text())["schemaVersion"] == node_install.SCHEMA_VERSION
        assert json.loads(in_tree.read_text())["nodePath"] == receipt["nodePath"]
        # activation markers carry the same payload
        config = json.loads((root / "config" / "node-runtime.json").read_text())
        assert config["schemaVersion"] == node_install.SCHEMA_VERSION
        assert (root / "runtime" / "install-receipt.json").read_text() == in_tree.read_text()
        assert Path(receipt["nodePath"]).stat().st_mode & stat.S_IXUSR
        assert (root / "runtime" / "install-receipt.json").stat().st_mode & 0o077 == 0
        # the interpreter the runner must later use is recorded (item 13)
        recorded = (root / "config" / "python3-path").read_text().strip()
        assert os.path.isabs(recorded) and os.path.isfile(recorded)
        assert (root / "config" / "python3-path").stat().st_mode & 0o077 == 0
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
        assert json.loads((root / "config" / "node-runtime.json").read_text())["schemaVersion"] == node_install.SCHEMA_VERSION

    def test_repair_rerecords_the_interpreter(self, inputs, capsys):
        # Attack finding 1: a kill between the publish rename and the
        # interpreter write leaves config/python3-path absent; the retry takes
        # the repair branch. Repairing without re-recording the interpreter
        # printed success while every later runner start would exit 78.
        root, archive, checksum = inputs
        node_install.install_node(str(root), str(archive), str(checksum))
        (root / "config" / "python3-path").unlink()
        node_install.install_node(str(root), str(archive), str(checksum))
        out = capsys.readouterr().out
        assert "activation repaired" in out
        recorded = (root / "config" / "python3-path").read_text().strip()
        assert os.path.isabs(recorded) and os.path.isfile(recorded)

    def test_stale_python3_path_temp_cleaned_under_lock(self, inputs, capsys):
        # Attack finding 2: a kill during private_write(python3-path) leaves
        # config/python3-path.tmp; O_EXCL then refuses every later install
        # forever. The dead-leftover cleanup must remove it so the runbook's
        # "re-run this exact command" actually succeeds.
        root, archive, checksum = inputs
        node_install.install_node(str(root), str(archive), str(checksum))
        (root / "config" / "python3-path").unlink()
        (root / "config" / "python3-path.tmp").write_text("")
        node_install.install_node(str(root), str(archive), str(checksum))
        assert "activation repaired" in capsys.readouterr().out
        assert (root / "config" / "python3-path").is_file()
        assert not (root / "config" / "python3-path.tmp").exists()

    def test_marker_failure_after_publish_retry_completes_activation(self, inputs, capsys):
        # Attack finding 3: an OS error in the instant after the publish rename
        # (here: config/ unwritable exactly when the markers are written)
        # leaves the tree published with markers missing. The re-run must
        # complete the WHOLE activation — including the interpreter record —
        # not report success over an unstartable runtime.
        root, archive, checksum = inputs
        (root / "config").mkdir(mode=0o700)
        os.chmod(root / "config", 0o500)
        with pytest.raises(OSError):
            node_install.install_node(str(root), str(archive), str(checksum))
        # the publish rename happened: the tree (with its in-tree receipt) is
        # on disk — the honest intermediate state — but no config markers
        assert (root / "runtime" / PREFIX / "INSTALL_RECEIPT.json").is_file()
        assert not (root / "config" / "node-runtime.json").exists()
        os.chmod(root / "config", 0o700)
        node_install.install_node(str(root), str(archive), str(checksum))
        out = capsys.readouterr().out
        assert "activation repaired" in out
        assert (root / "config" / "node-runtime.json").is_file()
        recorded = (root / "config" / "python3-path").read_text().strip()
        assert os.path.isabs(recorded) and os.path.isfile(recorded)

    def test_staging_leftover_names_its_removal(self, inputs):
        # Attack finding 10: a non-directory .node-install-* leftover refused
        # without naming the removal, leaving the operator a one-line refusal
        # and no next action.
        root, archive, checksum = inputs
        staging = root / "runtime" / "staging"
        staging.mkdir(parents=True, mode=0o700)
        (staging / ".node-install-notadir").write_text("debris\n")
        with pytest.raises(node_install.InstallError, match=r"rm -rf"):
            node_install.install_node(str(root), str(archive), str(checksum))

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
        # recomputed over the tampered tree, planted in the tree AND in both
        # outside receipts — refuses: the published tree must still be
        # byte-identical to a fresh extraction of the official archive.
        forged = json.loads(planted.read_text())
        forged["version"] = "v" + node_install.VERSION
        forged["treeSha256"] = node_install.tree_sha256(root / "runtime" / PREFIX)
        payload = json.dumps(forged, indent=2) + "\n"
        planted.write_text(payload)
        (root / "runtime" / "install-receipt.json").write_text(payload)
        (root / "config" / "node-runtime.json").write_text(payload)
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

    def test_leftover_staging_from_dead_run_is_cleaned(self, inputs):
        # F5: a killed install leaves .node-install-* staging behind; the next
        # run holds the install lock, recognizes its own debris and succeeds.
        root, archive, checksum = inputs
        (root / "runtime/staging/.node-install-unfinished").mkdir(parents=True, mode=0o700)
        (root / "runtime/staging/.node-install-unfinished/junk").write_text("x")
        node_install.install_node(str(root), str(archive), str(checksum))
        assert (root / "config" / "node-runtime.json").is_file()
        assert os.listdir(root / "runtime" / "staging") == []

    def test_leftover_receipt_temp_from_dead_run_is_cleaned(self, inputs):
        # F6: a kill between open() and replace() leaves node-runtime.json.tmp;
        # the retry removes it under the lock instead of refusing forever.
        root, archive, checksum = inputs
        (root / "runtime" / "staging").mkdir(parents=True, mode=0o700)
        (root / "config").mkdir()
        (root / "config" / "node-runtime.json.tmp").write_text("")
        node_install.install_node(str(root), str(archive), str(checksum))
        assert (root / "config" / "node-runtime.json").is_file()
        assert not (root / "config" / "node-runtime.json.tmp").exists()

    def test_conflicting_outside_receipt_refuses_before_publish(self, inputs):
        # F4: a stale/foreign runtime/install-receipt.json must refuse with
        # nothing published: no destination tree, no activation marker.
        root, archive, checksum = inputs
        (root / "runtime" / "staging").mkdir(parents=True, mode=0o700)
        (root / "runtime" / "install-receipt.json").write_text('{"stale": true}\n')
        with pytest.raises(node_install.InstallError, match="conflicting existing receipt"):
            node_install.install_node(str(root), str(archive), str(checksum))
        assert not (root / "runtime" / PREFIX).exists()
        assert not (root / "config" / "node-runtime.json").exists()
        assert os.listdir(root / "runtime" / "staging") == []

    def test_second_installer_refuses_while_lock_held(self, inputs):
        # F5: the install lock means one installer at a time per root.
        root, archive, checksum = inputs
        import fcntl
        runtime = root / "runtime" / "staging"
        runtime.mkdir(parents=True, mode=0o700)
        lock_path = root / "runtime" / "install.lock"
        fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            with pytest.raises(node_install.InstallError, match="already running"):
                node_install.install_node(str(root), str(archive), str(checksum))
        finally:
            os.close(fd)
        # and once released the install proceeds
        node_install.install_node(str(root), str(archive), str(checksum))
        assert (root / "config" / "node-runtime.json").is_file()


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
    """A root whose receipts name an in-root pinned node tree and a fake dist.
    The in-tree receipt agrees with the config receipt on treeSha256, exactly
    as a real install leaves them (item 12)."""
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
    tree_digest = node_install.tree_sha256(install_dir)
    node_receipt = {
        "schemaVersion": node_install.SCHEMA_VERSION,
        "version": "v" + node_install.VERSION,
        "archiveSha256": node_install.OFFICIAL_SHA256,
        "nodePath": str(node), "installDir": str(install_dir),
        "treeSha256": tree_digest,
    }
    server_receipt = {
        "schemaVersion": node_install.SCHEMA_VERSION,
        "serverBin": str(build / "bin.mjs"),
        "buildDir": str(build),
    }
    (install_dir / "INSTALL_RECEIPT.json").write_text(json.dumps(node_receipt))
    (root / "config").mkdir()
    (root / "config" / "node-runtime.json").write_text(json.dumps(node_receipt))
    (root / "config" / "server-runtime.json").write_text(json.dumps(server_receipt))
    return root, node, build


class TestItem12PinnedResolve:
    def test_runtime_paths_resolves_fake_tree_with_digest(self, tmp_path):
        # resolve verifies the tree digest by default (measured ~0.3s on the
        # real tree): the fake tree's digest was computed from the tree.
        root, node, build = fake_runtime(tmp_path)
        assert node_install.runtime_paths(str(root)) == (str(node), str(build / "bin.mjs"))

    def test_receipt_install_dir_not_pinned_refused(self, tmp_path):
        # Item 12: any other in-root directory with an executable bin/node
        # must be refused even though the shape checks pass.
        root, _, _ = fake_runtime(tmp_path)
        sneaky = root / "runtime" / "impostor"
        (sneaky / "bin").mkdir(parents=True)
        sneaky_node = sneaky / "bin" / "node"
        sneaky_node.write_text("#!/bin/sh\n")
        sneaky_node.chmod(0o700)
        receipt = json.loads((root / "config" / "node-runtime.json").read_text())
        receipt["installDir"] = str(sneaky)
        receipt["nodePath"] = str(sneaky_node)
        (root / "config" / "node-runtime.json").write_text(json.dumps(receipt))
        with pytest.raises(node_install.InstallError, match="pinned"):
            node_install.runtime_paths(str(root))

    def test_missing_in_tree_receipt_refused(self, tmp_path):
        root, _, _ = fake_runtime(tmp_path)
        (root / "runtime" / PREFIX / "INSTALL_RECEIPT.json").unlink()
        with pytest.raises(node_install.InstallError, match="in-tree"):
            node_install.runtime_paths(str(root))

    def test_in_tree_receipt_tree_digest_disagreement_refused(self, tmp_path):
        root, _, _ = fake_runtime(tmp_path)
        in_tree = root / "runtime" / PREFIX / "INSTALL_RECEIPT.json"
        tampered = json.loads(in_tree.read_text())
        tampered["treeSha256"] = "0" * 64
        in_tree.write_text(json.dumps(tampered))
        with pytest.raises(node_install.InstallError, match="disagree on treeSha256"):
            node_install.runtime_paths(str(root))

    def test_tampered_node_file_fails_digest_verify(self, tmp_path):
        # F23/item 12: resolve recomputes the digest and refuses a swapped
        # bin/node even when every receipt still agrees with itself.
        root, node, _ = fake_runtime(tmp_path)
        node.write_text("#!/bin/sh\n# replaced\n")
        node.chmod(0o700)
        with pytest.raises(node_install.InstallError, match="treeSha256"):
            node_install.runtime_paths(str(root))

    def test_no_verify_tree_skips_digest(self, tmp_path):
        root, node, build = fake_runtime(tmp_path)
        node.write_text("#!/bin/sh\n# replaced\n")
        node.chmod(0o700)
        assert node_install.runtime_paths(str(root), verify_tree=False) == \
            (str(node), str(build / "bin.mjs"))


class TestRuntimePaths:
    def test_valid_runtime_resolves(self, tmp_path):
        root, node, build = fake_runtime(tmp_path)
        assert node_install.runtime_paths(str(root)) == (str(node), str(build / "bin.mjs"))

    def test_wrong_schema_version_rejected(self, tmp_path):
        root, _, _ = fake_runtime(tmp_path)
        receipt = json.loads((root / "config" / "server-runtime.json").read_text())
        receipt["schemaVersion"] = 1
        (root / "config" / "server-runtime.json").write_text(json.dumps(receipt))
        with pytest.raises(node_install.InstallError, match="reinstall"):
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
        # item 12: the pinned-installDir refusal fires before any escape check
        with pytest.raises(node_install.InstallError, match="pinned"):
            node_install.runtime_paths(str(root))

    def test_nodepath_install_dir_crosscheck(self, tmp_path):
        root, node, _ = fake_runtime(tmp_path)
        receipt = json.loads((root / "config" / "node-runtime.json").read_text())
        receipt["nodePath"] = str(root / "runtime" / PREFIX / "bin" / "node2")
        (root / "config" / "node-runtime.json").write_text(json.dumps(receipt))
        with pytest.raises(node_install.InstallError,
                           match="nodePath must be installDir/bin/node"):
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

    def test_doctor_never_prints_pairing_file_contents(self, tmp_path, capsys):
        # F26 (replaces the vacuous co_consts assert): a sentinel token in the
        # pairing file must never reach doctor's output.
        from unittest.mock import Mock, patch
        root, _, _ = fake_runtime(tmp_path)
        (root / "run").mkdir()
        (root / "run" / "port").write_text("50809\n")
        access = root / "run" / "access.txt"
        access.write_text("Token: PAIRTOKEN-SENSITIVE-123\n")
        access.chmod(0o600)
        with patch.object(node_install.subprocess, "run",
                          return_value=Mock(returncode=1, stdout="")):
            assert node_install.doctor(str(root), "com.mastermind.t3-team-dev-tsh") == 1
        out = capsys.readouterr().out
        assert "PAIRTOKEN-SENSITIVE-123" not in out
        assert "pairingFileAgeSeconds" in out

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
        assert "treeVerified=yes" in out  # F23: doctor rechecks the tree digest

    def test_doctor_success_path_returns_zero(self, tmp_path, capsys):
        # The reviewer found doctor's success path untested: loaded + answering
        # must return 0 and print the health rows.
        from unittest.mock import Mock, patch
        import threading
        from http.server import BaseHTTPRequestHandler, HTTPServer
        root, _, _ = fake_runtime(tmp_path)
        (root / "run").mkdir()
        port = 0
        holder = []

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"ok")

            def log_message(self, *args):
                pass

        server = HTTPServer(("127.0.0.1", 0), Handler)
        port = server.server_address[1]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        holder.append(server)
        try:
            (root / "run" / "port").write_text(f"{port}\n")
            with patch.object(node_install.subprocess, "run",
                              return_value=Mock(returncode=0, stdout="pid = 4242\n")):
                assert node_install.doctor(str(root), "com.mastermind.t3-team-dev-tsh") == 0
            out = capsys.readouterr().out
            assert "loaded=yes" in out and "pid=4242" in out
            assert f"answeringPort={port}" in out
            assert "treeVerified=yes" in out
        finally:
            server.shutdown()
            server.server_close()

    def test_doctor_failure_line_for_down_server(self, tmp_path, capsys):
        # Attack finding 6: the runbook documents "failure prints one line
        # doctor_error=<reason>"; the commonest failure (label not loaded)
        # used to print only the metadata block and exit 1.
        from unittest.mock import Mock, patch
        root, _, _ = fake_runtime(tmp_path)
        (root / "run").mkdir()
        (root / "run" / "port").write_text("50809\n")
        with patch.object(node_install.subprocess, "run",
                          return_value=Mock(returncode=1, stdout="")):
            assert node_install.doctor(str(root), "com.mastermind.t3-team-dev-tsh") == 1
        out = capsys.readouterr().out
        assert "doctor_error=" in out and "not loaded" in out

    def test_doctor_failure_line_for_unanswered_port(self, tmp_path, capsys):
        # Attack finding 6, second shape: loaded but not answering must also
        # print its one doctor_error= line, not just the metadata block.
        from unittest.mock import Mock, patch
        root, _, _ = fake_runtime(tmp_path)
        (root / "run").mkdir()
        (root / "run" / "port").write_text("50809\n")  # nothing listens here
        with patch.object(node_install.subprocess, "run",
                          return_value=Mock(returncode=0, stdout="pid = 4242\n")):
            assert node_install.doctor(str(root), "com.mastermind.t3-team-dev-tsh") == 1
        out = capsys.readouterr().out
        assert "doctor_error=port 50809 not answering" in out

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
