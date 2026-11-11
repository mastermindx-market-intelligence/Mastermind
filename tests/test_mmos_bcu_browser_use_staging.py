"""Lane BCU staged-install package tests.

Covers tools/mmos_browser_use/generate_staging.py, the generated install/
rollback/verify scripts, and the loopback fixture server — all against tmpdir
fixtures. Never runs install/rollback against a real provider home.
"""
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
GENERATOR = REPO / "tools" / "mmos_browser_use" / "generate_staging.py"
FIXTURE_SERVER = REPO / "integrations" / "mmos" / "bcu" / "fixtures" / "fixture_server.py"

MMOS_COMPUTER_USE_ENTRY = {
    "command": "python3",
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


def run(*cmd, **kwargs):
    return subprocess.run([str(c) for c in cmd], capture_output=True, text=True, **kwargs)


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def backups(home_file):
    return sorted(Path(home_file).parent.glob(".claude.json.bak-pre-bcu-*"))


def stage_fake_home(tmp, with_mmx=True):
    """Create a fake provider home plus its staged install tree; returns paths."""
    home_dir = tmp / "homes" / HOME_NAME
    home_dir.mkdir(parents=True)
    home_file = home_dir / ".claude.json"
    home_file.write_text(json.dumps(HOME_JSON, indent=2) + "\n", encoding="utf-8")
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

    def test_rollback_without_backup_removes_only_our_keys(self):
        run(sys.executable, self.staging / "install.py", "--home", self.home_file)
        for backup in backups(self.home_file):
            backup.unlink()
        proc = run(sys.executable, self.staging / "rollback.py", "--home", self.home_file)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("ROLLED_BACK_KEYS", proc.stdout)
        post = read_json(self.home_file)
        servers = post.get("mcpServers", {})
        self.assertNotIn("mmos-computer-use", servers)
        self.assertNotIn("mmx-browser", servers)
        self.assertEqual(servers.get("other_server"), HOME_JSON["mcpServers"]["other_server"])
        self.assertEqual(post["unrelated"], HOME_JSON["unrelated"])

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
