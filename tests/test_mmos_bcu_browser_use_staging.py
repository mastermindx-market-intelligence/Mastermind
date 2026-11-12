"""Lane BCU staged-install package tests.

Covers tools/mmos_browser_use/generate_staging.py, the generated install/
rollback/verify scripts, and the loopback fixture server — all against tmpdir
fixtures. Never runs install/rollback against a real provider home.
"""
import importlib.util
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
GENERATOR = REPO / "tools" / "mmos_browser_use" / "generate_staging.py"
GENERATED = REPO / "integrations" / "mmos" / "bcu" / "generated"
FIXTURE_SERVER = REPO / "integrations" / "mmos" / "bcu" / "fixtures" / "fixture_server.py"

MMOS_COMPUTER_USE_ENTRY = {
    "command": "/usr/bin/python3",
    "args": ["/Users/chriswong/.t3/mcp/mmos-computer-use/server.py"],
    "type": "stdio",
}
MMX_BROWSER_ENTRY = {
    "command": "/Users/chriswong/.local/share/mastermind-runtime/node/bin/node",
    "args": ["/Users/chriswong/.t3/mcp/mmx-browser/server.js"],
    "type": "stdio",
}
BCU_KEYS = ("mmos-computer-use", "mmx-browser")

HOME_NAME = "fake-home-a"
HOME_JSON = {
    "unrelated": {"keep": [1, 2, 3], "nested": {"a": True}},
    "mcpServers": {
        "other_server": {"command": "/bin/true", "args": [], "type": "stdio"},
    },
}
# A pre-existing mmx-browser registration with a value different from ours: an
# install must record it as MODIFIED (never added) and rollback must keep it.
PREEXISTING_MMX_BROWSER = {
    "command": "/bin/false",
    "args": ["/tmp/old-browser.js"],
    "type": "stdio",
}
COPY_SERVER_BODIES = {
    "server.py": "#!/usr/bin/env python3\n# fake computer-use server\n",
    "deny.json": '{"deny": []}\n',
    "runtime.json": '{"idle_seconds": 180}\n',
}


def run(*cmd, **kwargs):
    return subprocess.run([str(c) for c in cmd], capture_output=True, text=True, **kwargs)


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def backups(home_file):
    return sorted(Path(home_file).parent.glob(".claude.json.bak-pre-bcu-*"))


def mode_of(path):
    return stat.S_IMODE(os.stat(path).st_mode)


def load_script_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def stage_fake_home(tmp, with_mmx=True, home_json=None):
    """Create a fake provider home plus its staged install tree; returns paths."""
    home_dir = tmp / "homes" / HOME_NAME
    home_dir.mkdir(parents=True, exist_ok=True)
    home_file = home_dir / ".claude.json"
    home_file.write_text(json.dumps(home_json or HOME_JSON, indent=2) + "\n", encoding="utf-8")
    staging = tmp / "staging"
    cmd = [sys.executable, GENERATOR, "--home", home_file, "--out", staging]
    if with_mmx:
        cmd.append("--mmx-browser")
    proc = run(*cmd)
    assert proc.returncode == 0, proc.stderr
    return home_file, staging


class BcuStagingInstallTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="bcu-staging-")
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.home_file, self.staging = stage_fake_home(self.tmp)
        self.pre = read_json(self.home_file)

    def others_unchanged(self, label):
        post = read_json(self.home_file)
        for key, value in self.pre.items():
            if key == "mcpServers":
                continue
            self.assertEqual(post.get(key), value, label + ": key " + key)
        servers_pre = self.pre.get("mcpServers", {})
        for key, value in servers_pre.items():
            self.assertEqual(post["mcpServers"].get(key), value,
                             label + ": mcpServers key " + key)

    def test_install_adds_our_keys_backup_and_idempotence(self):
        # First install: our two keys added, unrelated keys preserved, one backup.
        proc = run(sys.executable, self.staging / "install.py", "--home", self.home_file)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("INSTALLED", proc.stdout)
        post = read_json(self.home_file)
        self.assertEqual(post["mcpServers"]["mmos-computer-use"], MMOS_COMPUTER_USE_ENTRY)
        self.assertEqual(post["mcpServers"]["mmx-browser"], MMX_BROWSER_ENTRY)
        self.others_unchanged("after install")
        self.assertEqual(len(backups(self.home_file)), 1)

        # Second install: idempotent — no new backup, keys unchanged.
        proc = run(sys.executable, self.staging / "install.py", "--home", self.home_file)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("ALREADY_INSTALLED", proc.stdout)
        self.assertEqual(len(backups(self.home_file)), 1, "no backup churn on re-run")
        post2 = read_json(self.home_file)
        self.assertEqual(post2["mcpServers"]["mmos-computer-use"], MMOS_COMPUTER_USE_ENTRY)
        self.assertEqual(post2["mcpServers"]["mmx-browser"], MMX_BROWSER_ENTRY)
        self.others_unchanged("after re-install")

    def test_verify_reports_entries_and_sha(self):
        run(sys.executable, self.staging / "install.py", "--home", self.home_file)
        proc = run(sys.executable, self.staging / "verify.py", "--home", self.home_file)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        out = proc.stdout
        self.assertIn("mmos-computer-use", out)
        self.assertIn("mmx-browser", out)
        self.assertIn("VERIFY mmos-computer-use PRESENT", out)
        self.assertIn("VERIFY mmx-browser PRESENT", out)
        self.assertIn("SHA256 ", out)
        # The printed sha equals the edited file's actual sha256.
        import hashlib
        actual = hashlib.sha256(self.home_file.read_bytes()).hexdigest()
        self.assertIn(actual, out)

    def test_tamper_aborts_preimage_mismatch(self):
        run(sys.executable, self.staging / "install.py", "--home", self.home_file)
        tampered = read_json(self.home_file)
        tampered["unrelated"]["keep"] = [9]
        self.home_file.write_text(json.dumps(tampered, indent=2) + "\n", encoding="utf-8")
        proc = run(sys.executable, self.staging / "install.py", "--home", self.home_file)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("PREIMAGE_MISMATCH", proc.stdout + proc.stderr)
        # Nothing was written on the aborted run.
        self.assertEqual(read_json(self.home_file)["unrelated"]["keep"], [9])
        self.assertEqual(read_json(self.home_file)["mcpServers"]["mmos-computer-use"],
                         MMOS_COMPUTER_USE_ENTRY)
        self.assertEqual(len(backups(self.home_file)), 1)

    def test_rollback_restores_backup(self):
        run(sys.executable, self.staging / "install.py", "--home", self.home_file)
        self.assertTrue(backups(self.home_file))
        proc = run(sys.executable, self.staging / "rollback.py", "--home", self.home_file)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("ROLLED_BACK_FROM", proc.stdout)
        post = read_json(self.home_file)
        servers = post.get("mcpServers", {})
        self.assertNotIn("mmos-computer-use", servers)
        self.assertNotIn("mmx-browser", servers)
        for key, value in HOME_JSON.items():
            self.assertEqual(post.get(key), value, "rollback key " + key)
        # File is byte-identical to the restored backup's content.
        newest = backups(self.home_file)[-1]
        self.assertEqual(self.home_file.read_bytes(), newest.read_bytes())
        # After rollback, verify reports absence and fails.
        proc = run(sys.executable, self.staging / "verify.py", "--home", self.home_file)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("VERIFY mmos-computer-use ABSENT", proc.stdout)

    def test_backup_postimage_and_home_modes_0600(self):
        # M12a: a 0600 original must produce a 0600 backup (never world-readable),
        # a 0600 postimage record, and the home file itself stays 0600.
        os.chmod(self.home_file, 0o600)
        original = self.home_file.read_bytes()
        proc = run(sys.executable, self.staging / "install.py", "--home", self.home_file)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(len(backups(self.home_file)), 1)
        self.assertEqual(mode_of(backups(self.home_file)[0]), 0o600)
        postimage = self.staging / HOME_NAME / "postimage.sha256"
        self.assertTrue(postimage.is_file())
        self.assertEqual(mode_of(postimage), 0o600)
        self.assertEqual(mode_of(self.home_file), 0o600)
        # The backup bytes equal the original's bytes.
        self.assertEqual(backups(self.home_file)[0].read_bytes(), original)

    def test_rollback_without_backup_and_manifest_refuses(self):
        # M12b: with no backup and no added-keys manifest, rollback must refuse
        # (exit nonzero) rather than delete staged keys — it cannot know which
        # keys pre-existed this install.
        run(sys.executable, self.staging / "install.py", "--home", self.home_file)
        for backup in backups(self.home_file):
            backup.unlink()
        (self.staging / HOME_NAME / "added-keys.json").unlink()
        proc = run(sys.executable, self.staging / "rollback.py", "--home", self.home_file)
        self.assertNotEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("NO_BACKUP", proc.stdout + proc.stderr)
        post = read_json(self.home_file)
        servers = post.get("mcpServers", {})
        self.assertIn("mmos-computer-use", servers)
        self.assertIn("mmx-browser", servers)
        self.assertEqual(servers.get("other_server"), HOME_JSON["mcpServers"]["other_server"])

    def test_rollback_without_backup_removes_only_added_keys(self):
        # M12c: a pre-existing mmx-browser (modified, not added) must survive a
        # no-backup rollback; only keys the install recorded as ADDED are removed.
        home_json = json.loads(json.dumps(HOME_JSON))
        home_json["mcpServers"]["mmx-browser"] = PREEXISTING_MMX_BROWSER
        self.home_file, self.staging = stage_fake_home(self.tmp, home_json=home_json)
        proc = run(sys.executable, self.staging / "install.py", "--home", self.home_file)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        manifest = read_json(self.staging / HOME_NAME / "added-keys.json")
        self.assertEqual(manifest["added"], ["mmos-computer-use"])
        self.assertEqual(manifest["modified"], ["mmx-browser"])
        for backup in backups(self.home_file):
            backup.unlink()
        proc = run(sys.executable, self.staging / "rollback.py", "--home", self.home_file)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("ROLLED_BACK_KEYS mmos-computer-use", proc.stdout)
        servers = read_json(self.home_file)["mcpServers"]
        self.assertNotIn("mmos-computer-use", servers)
        self.assertEqual(servers.get("mmx-browser"), PREEXISTING_MMX_BROWSER)
        self.assertEqual(servers.get("other_server"), HOME_JSON["mcpServers"]["other_server"])

    def test_atomic_write_rechecks_hash_before_replace(self):
        # M12d: the write helper aborts when the destination changed since the
        # caller's first read, and otherwise replaces atomically (temp file in
        # the same directory + os.replace, requested mode, no leftovers).
        mod = load_script_module(self.staging / "install.py", "bcu_install_mod_m12d")
        target = self.tmp / "atomic" / "target.json"
        target.parent.mkdir(parents=True)
        target.write_text("original-bytes", encoding="utf-8")
        first_sha = mod.sha256_file(target)
        target.write_text("mutated-bytes", encoding="utf-8")  # concurrent writer
        with self.assertRaises(mod.PreimageMismatch):
            mod.atomic_write(target, b"new-bytes", 0o600, expect_sha=first_sha)
        self.assertEqual(target.read_text(encoding="utf-8"), "mutated-bytes")
        # Positive path: content replaced, mode applied, no temp leftovers.
        mod.atomic_write(target, b"replaced-bytes", 0o600,
                         expect_sha=mod.sha256_file(target))
        self.assertEqual(target.read_bytes(), b"replaced-bytes")
        self.assertEqual(mode_of(target), 0o600)
        self.assertEqual([p.name for p in target.parent.iterdir()], ["target.json"])

    def test_rollback_atomic_write_rechecks_hash_before_replace(self):
        # M12d (rollback side): same temp-file + os.replace + hash re-check.
        mod = load_script_module(self.staging / "rollback.py", "bcu_rollback_mod_m12d")
        target = self.tmp / "atomic-rb" / "target.json"
        target.parent.mkdir(parents=True)
        target.write_text("original-bytes", encoding="utf-8")
        first_sha = mod.sha256_file(target)
        target.write_text("mutated-bytes", encoding="utf-8")  # concurrent writer
        with self.assertRaises(mod.PreimageMismatch):
            mod.atomic_write(target, b"restored-bytes", 0o600, expect_sha=first_sha)
        self.assertEqual(target.read_text(encoding="utf-8"), "mutated-bytes")
        mod.atomic_write(target, b"restored-bytes", 0o600,
                         expect_sha=mod.sha256_file(target))
        self.assertEqual(target.read_bytes(), b"restored-bytes")
        self.assertEqual(mode_of(target), 0o600)
        self.assertEqual([p.name for p in target.parent.iterdir()], ["target.json"])

    def test_refresh_preimage_rerecords_current_hash(self):
        # M12e: strict staged preimage without the flag; --refresh-preimage
        # (operator-only, explicit) re-records the current hash after printing
        # which staged keys are present / matching / changed.
        tampered = read_json(self.home_file)
        tampered["unrelated"]["keep"] = [9]
        self.home_file.write_text(json.dumps(tampered, indent=2) + "\n", encoding="utf-8")
        proc = run(sys.executable, self.staging / "install.py", "--home", self.home_file)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("PREIMAGE_MISMATCH", proc.stdout + proc.stderr)
        proc = run(sys.executable, self.staging / "install.py", "--home", self.home_file,
                   "--refresh-preimage")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        out = proc.stdout
        self.assertIn("REFRESH_PREIMAGE", out)
        self.assertIn("STAGED_KEYS_PRESENT", out)
        self.assertIn("STAGED_KEYS_CHANGED", out)
        import hashlib
        self.assertEqual((self.staging / HOME_NAME / "preimage.sha256").read_text().strip(),
                         hashlib.sha256(self.home_file.read_bytes()).hexdigest())
        proc = run(sys.executable, self.staging / "install.py", "--home", self.home_file)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("INSTALLED", proc.stdout)
        # After an install, drift, refresh again: the stale postimage is cleared
        # so a fresh install re-runs instead of claiming ALREADY_INSTALLED.
        tampered["unrelated"]["keep"] = [7]
        self.home_file.write_text(json.dumps(tampered, indent=2) + "\n", encoding="utf-8")
        proc = run(sys.executable, self.staging / "install.py", "--home", self.home_file)
        self.assertNotEqual(proc.returncode, 0)
        proc = run(sys.executable, self.staging / "install.py", "--home", self.home_file,
                   "--refresh-preimage")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        proc = run(sys.executable, self.staging / "install.py", "--home", self.home_file)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("INSTALLED", proc.stdout)

    def test_install_copy_server_copies_then_registers(self):
        src = self.tmp / "cusrc"
        src.mkdir()
        for name, body in COPY_SERVER_BODIES.items():
            (src / name).write_text(body, encoding="utf-8")
        mcp_root = self.tmp / "mcp"
        proc = run(sys.executable, self.staging / "install.py", "--home", self.home_file,
                   "--copy-server", src, "--mcp-root", mcp_root)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        server_dir = mcp_root / "mmos-computer-use"
        for name, body in COPY_SERVER_BODIES.items():
            copied = server_dir / name
            self.assertTrue(copied.is_file(), name)
            self.assertEqual(copied.read_text(encoding="utf-8"), body, name)
            self.assertEqual(mode_of(copied), 0o600, name)
        post = read_json(self.home_file)
        self.assertEqual(post["mcpServers"]["mmos-computer-use"], {
            "command": "/usr/bin/python3",
            "args": [str(server_dir / "server.py")],
            "type": "stdio",
        })
        manifest = read_json(self.staging / HOME_NAME / "added-keys.json")
        self.assertTrue(manifest["mcp_server_dir_created"])
        self.assertEqual(manifest["mcp_server_dir"], str(server_dir))
        proc = run(sys.executable, self.staging / "verify.py", "--home", self.home_file,
                   "--mcp-root", mcp_root)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("VERIFY mmos-computer-use PRESENT", proc.stdout)

    def test_rollback_remove_server_deletes_only_install_created_dir(self):
        src = self.tmp / "cusrc"
        src.mkdir()
        for name, body in COPY_SERVER_BODIES.items():
            (src / name).write_text(body, encoding="utf-8")
        mcp_root = self.tmp / "mcp"
        run(sys.executable, self.staging / "install.py", "--home", self.home_file,
            "--copy-server", src, "--mcp-root", mcp_root)
        proc = run(sys.executable, self.staging / "rollback.py", "--home", self.home_file,
                   "--remove-server")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("SERVER_DIR_REMOVED", proc.stdout)
        self.assertFalse((mcp_root / "mmos-computer-use").exists())

    def test_rollback_remove_server_keeps_foreign_dir(self):
        src = self.tmp / "cusrc"
        src.mkdir()
        for name, body in COPY_SERVER_BODIES.items():
            (src / name).write_text(body, encoding="utf-8")
        mcp_root = self.tmp / "mcp"
        server_dir = mcp_root / "mmos-computer-use"
        server_dir.mkdir(parents=True)
        sentinel = server_dir / "operator-marker.txt"
        sentinel.write_text("pre-existing", encoding="utf-8")
        proc = run(sys.executable, self.staging / "install.py", "--home", self.home_file,
                   "--copy-server", src, "--mcp-root", mcp_root)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        manifest = read_json(self.staging / HOME_NAME / "added-keys.json")
        self.assertFalse(manifest["mcp_server_dir_created"])
        proc = run(sys.executable, self.staging / "rollback.py", "--home", self.home_file,
                   "--remove-server")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("SERVER_DIR_KEPT", proc.stdout)
        self.assertTrue(server_dir.exists())
        self.assertTrue(sentinel.is_file())

    def test_install_without_copy_server_warns_missing_target(self):
        mcp_root = self.tmp / "mcp"  # absent — nothing copied there
        proc = run(sys.executable, self.staging / "install.py", "--home", self.home_file,
                   "--mcp-root", mcp_root)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("SERVER_TARGET_MISSING", proc.stderr)
        post = read_json(self.home_file)
        self.assertEqual(post["mcpServers"]["mmos-computer-use"]["args"],
                         [str(mcp_root / "mmos-computer-use" / "server.py")])

    def test_install_copy_server_warns_when_runtime_json_absent(self):
        src = self.tmp / "cusrc"
        src.mkdir()
        (src / "server.py").write_text(COPY_SERVER_BODIES["server.py"], encoding="utf-8")
        (src / "deny.json").write_text(COPY_SERVER_BODIES["deny.json"], encoding="utf-8")
        mcp_root = self.tmp / "mcp"
        proc = run(sys.executable, self.staging / "install.py", "--home", self.home_file,
                   "--copy-server", src, "--mcp-root", mcp_root)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("RUNTIME_JSON_ABSENT", proc.stderr)
        server_dir = mcp_root / "mmos-computer-use"
        self.assertTrue((server_dir / "server.py").is_file())
        self.assertTrue((server_dir / "deny.json").is_file())
        self.assertFalse((server_dir / "runtime.json").exists())

    def test_staged_entry_command_is_absolute_python(self):
        # atk#11: PATH-independent launcher, matching the roster entry.
        entries = read_json(self.staging / HOME_NAME / "entries.json")
        self.assertEqual(entries["mmos-computer-use"]["command"], "/usr/bin/python3")
        run(sys.executable, self.staging / "install.py", "--home", self.home_file)
        self.assertEqual(read_json(self.home_file)["mcpServers"]["mmos-computer-use"]["command"],
                         "/usr/bin/python3")

    def test_home_path_guards(self):
        # Missing --home entirely -> argparse error.
        proc = run(sys.executable, self.staging / "install.py")
        self.assertNotEqual(proc.returncode, 0)
        # --home not ending in .claude.json.
        for script in ("install.py", "rollback.py", "verify.py"):
            proc = run(sys.executable, self.staging / script, "--home", str(self.tmp / "homes"))
            self.assertNotEqual(proc.returncode, 0, script)
            self.assertIn("BAD_HOME_PATH", proc.stdout + proc.stderr, script)
            # --home pointing at a nonexistent .claude.json.
            proc = run(sys.executable, self.staging / script,
                       "--home", str(self.tmp / "nope" / ".claude.json"))
            self.assertNotEqual(proc.returncode, 0, script)
            self.assertIn("HOME_NOT_FOUND", proc.stdout + proc.stderr, script)


class BcuGeneratorGuardTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="bcu-gen-")
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)

    def test_generator_refuses_home_without_claude_json_suffix(self):
        proc = run(sys.executable, GENERATOR, "--home", str(self.tmp / "wrong.json"),
                   "--out", self.tmp / "staging")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("BAD_HOME_PATH", proc.stdout + proc.stderr)
        self.assertFalse((self.tmp / "staging").exists())

    def test_generator_refuses_missing_home_file(self):
        proc = run(sys.executable, GENERATOR, "--home", str(self.tmp / "x" / ".claude.json"),
                   "--out", self.tmp / "staging")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("HOME_NOT_FOUND", proc.stdout + proc.stderr)

    def test_generator_home_mode_writes_staging(self):
        home_dir = self.tmp / "gen-home"
        home_dir.mkdir()
        home_file = home_dir / ".claude.json"
        home_file.write_text(json.dumps(HOME_JSON, indent=2) + "\n", encoding="utf-8")
        staging = self.tmp / "staging"
        proc = run(sys.executable, GENERATOR, "--home", home_file,
                   "--mmx-browser", "--out", staging)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        entries = read_json(staging / "gen-home" / "entries.json")
        self.assertEqual(entries["mmos-computer-use"], MMOS_COMPUTER_USE_ENTRY)
        self.assertEqual(entries["mmx-browser"], MMX_BROWSER_ENTRY)
        import hashlib
        self.assertEqual((staging / "gen-home" / "preimage.sha256").read_text().strip(),
                         hashlib.sha256(home_file.read_bytes()).hexdigest())
        for script in ("install.py", "rollback.py", "verify.py"):
            self.assertTrue((staging / script).is_file(), script)

    def test_generator_refuses_mmx_browser_without_home(self):
        proc = run(sys.executable, GENERATOR, "--mmx-browser",
                   "--out", self.tmp / "staging")
        self.assertNotEqual(proc.returncode, 0)


class BcuGeneratorDefaultOutGuardTests(unittest.TestCase):
    """atk#12: default --out must not overwrite the committed generated tree."""

    @classmethod
    def setUpClass(cls):
        cls.gen = load_script_module(GENERATOR, "bcu_generator_mod_guard")
        cls.gen_guard_default_out = cls.gen.DEFAULT_OUT

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="bcu-guard-")
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)

    def make_committed_tree(self, path):
        path.mkdir(parents=True)
        (path / "MANIFEST.json").write_text("{}\n", encoding="utf-8")
        (path / "install.py").write_text("#!/usr/bin/env python3\n", encoding="utf-8")

    def test_guard_refuses_default_out_and_lists_files(self):
        committed = self.tmp / "generated"
        self.make_committed_tree(committed)
        self.gen.DEFAULT_OUT = committed
        blocked = self.gen.check_default_out_guard(committed, force=False)
        self.addCleanup(setattr, self.gen, "DEFAULT_OUT", self.gen_guard_default_out)
        self.assertEqual(blocked, ["MANIFEST.json", "install.py"])

    def test_guard_allows_force(self):
        committed = self.tmp / "generated"
        self.make_committed_tree(committed)
        self.gen.DEFAULT_OUT = committed
        self.addCleanup(setattr, self.gen, "DEFAULT_OUT", self.gen_guard_default_out)
        self.assertIsNone(self.gen.check_default_out_guard(committed, force=True))

    def test_guard_allows_explicit_out_elsewhere(self):
        committed = self.tmp / "generated"
        self.make_committed_tree(committed)
        elsewhere = self.tmp / "elsewhere"
        elsewhere.mkdir()
        (elsewhere / "install.py").write_text("#!/usr/bin/env python3\n", encoding="utf-8")
        self.gen.DEFAULT_OUT = committed
        self.addCleanup(setattr, self.gen, "DEFAULT_OUT", self.gen_guard_default_out)
        self.assertIsNone(self.gen.check_default_out_guard(elsewhere, force=False))

    def test_generator_refuses_real_generated_tree(self):
        # Subprocess level against the real committed tree: refusal happens
        # before any write, so the committed files stay byte-identical.
        before = (GENERATED / "MANIFEST.json").read_bytes(), \
            (GENERATED / "install.py").read_bytes()
        proc = run(sys.executable, GENERATOR)  # no --out: default out
        self.assertNotEqual(proc.returncode, 0, proc.stdout)
        err = proc.stdout + proc.stderr
        self.assertIn("GENERATED_TREE_EXISTS", err)
        self.assertIn("install.py", err)
        self.assertIn("MANIFEST.json", err)
        self.assertEqual((GENERATED / "MANIFEST.json").read_bytes(), before[0])
        self.assertEqual((GENERATED / "install.py").read_bytes(), before[1])


class BcuGeneratedScriptSyncTests(unittest.TestCase):
    def test_generated_scripts_match_generator_strings(self):
        gen = load_script_module(GENERATOR, "bcu_generator_mod_sync")
        for name, attr in (("install.py", "SCRIPT_INSTALL"),
                           ("rollback.py", "SCRIPT_ROLLBACK"),
                           ("verify.py", "SCRIPT_VERIFY")):
            self.assertEqual((GENERATED / name).read_text(encoding="utf-8"),
                             getattr(gen, attr), name)


class BcuFixtureServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location(
            "bcu_fixture_server_under_test", FIXTURE_SERVER)
        cls.fixture = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.fixture)

    def test_fixture_serves_loopback_only(self):
        server = self.fixture.make_server(port=0)
        self.addCleanup(server.server_close)
        host, port = server.server_address[0], server.server_address[1]
        self.assertEqual(host, "127.0.0.1")
        import threading
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with urllib.request.urlopen("http://127.0.0.1:%d/fixture.html" % port,
                                        timeout=5) as response:
                body = response.read().decode("utf-8")
            self.assertEqual(response.status, 200)
            self.assertIn("BCU_FIXTURE_PAGE1", body)
            self.assertIn('id="note"', body)
            self.assertIn('id="reveal"', body)
            self.assertIn('id="status" hidden', body)
            self.assertIn('href="#page2"', body)
            self.assertIn("BCU_FIXTURE_PAGE2", body)
            # Unrelated paths 404 rather than leaking other directories.
            with self.assertRaises(urllib.error.HTTPError) as caught:
                urllib.request.urlopen("http://127.0.0.1:%d/generate_staging.py" % port,
                                       timeout=5)
            self.assertEqual(caught.exception.code, 404)
        finally:
            server.shutdown()
            thread.join(timeout=5)
            self.assertFalse(thread.is_alive())


if __name__ == "__main__":
    unittest.main()
