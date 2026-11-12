"""BR-MICRO2 item 3: guarded switch of the registered mmx-browser server path.

Runbook step 4 repoints ``mcpServers.mmx-browser.args`` in four provider
homes' ``.claude.json`` (``experiential-claude``, ``fabric-experiential``,
``fabric-unified-router``, ``fabric-anthropic-oauth``) from the flat
``$MMX/server.js`` to ``$MMX/current/server.js``;
``fabric-unified-router-worker`` has no entry and must stay that way.
Running sessions rewrite ``.claude.json``, so a hand edit can lose a race
either way, and no source writer ever registered mmx-browser there (the
repo's only ``.claude.json`` writer is the subscription worker's sandboxed
onboarding stub). The guarded command therefore: checks every file BEFORE
the first write, refuses unless each entry is exactly the expected old
path, keeps a ``.previous.<16hex>`` backup per file, prints file names
only — never contents — and reads every file back after a short wait.

Fails first on 9bb79b899: the module does not exist there — the runbook
said "edit ... backup each first" by hand. Every test here runs on FIXTURE
files only; the real provider homes are never opened by this lane.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from integrations.hermes_harness import mmx_provider_registration as reg
from integrations.hermes_harness.install_browser import json_bytes, write_owned

ROOT = Path(__file__).resolve().parents[1]
HOMES = ("experiential-claude", "fabric-experiential",
         "fabric-unified-router", "fabric-anthropic-oauth")
WORKER = "fabric-unified-router-worker"
OLD_COMMIT = "5" * 40


def folder_hash(folder: Path) -> str:
    if not folder.exists():
        return "absent"
    entries = []
    for path in sorted(folder.rglob("*")):
        relative = str(path.relative_to(folder))
        if path.is_symlink():
            entries.append((relative, "link", os.readlink(path)))
        elif path.is_file():
            entries.append((relative, oct(path.stat().st_mode & 0o777),
                            hashlib.sha256(path.read_bytes()).hexdigest()))
        else:
            entries.append((relative, "dir", ""))
    return hashlib.sha256(json.dumps(entries).encode()).hexdigest()


class ProviderRegistrationSwitch(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="mb-prov-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.providers = self.root / "providers"
        self.mmx = self.root / "mmx-browser"
        # the pin fixture: flat server.js plus a delivered versioned pin that
        # "current" resolves to, so the new target exists (migrate ran first).
        live = self.mmx / "runtimes" / OLD_COMMIT
        write_owned(live / "server.js", b"// fixture server (opaque bytes)\n", 0o600)
        write_owned(self.mmx / "server.js", b"// fixture server (opaque bytes)\n", 0o600)
        (self.mmx / "current").symlink_to(live, target_is_directory=True)
        self.old_path = str((self.mmx / "server.js").resolve())
        # the switch writes the literal current/server.js path — NOT its
        # resolved runtimes/<commit> target — so a later migration only
        # re-points the symlink and never has to touch .claude.json again
        self.new_path = str(self.mmx / "current" / "server.js")
        for home in HOMES:
            self.write_home(home)
        # the worker home: a .claude.json WITHOUT an mmx-browser entry
        write_owned(self.providers / WORKER / ".claude.json",
                    json_bytes({"hasCompletedOnboarding": True,
                                "mcpServers": {"other": {"command": "true", "args": []}}}),
                    0o600)

    def write_home(self, home, server_path=None, extra=True):
        document = {"hasCompletedOnboarding": True, "numStartups": 7}
        if extra:
            document["mcpServers"] = {
                "mmx-browser": {"command": "node",
                                "args": [server_path or self.old_path]},
                "unrelated-server": {"command": "keep", "args": ["me"]}}
        path = self.providers / home / ".claude.json"
        path.unlink(missing_ok=True)  # fixtures replace; write_owned never overwrites without CAS
        write_owned(path, json_bytes(document), 0o600)

    def read_home(self, home):
        return json.loads((self.providers / home / ".claude.json").read_bytes())

    def switch(self, **kwargs):
        kwargs.setdefault("pause", lambda seconds: None)
        return reg.switch(self.providers, self.mmx, **kwargs)

    def test_switches_all_four_homes_with_backups_and_preserves_the_rest(self):
        before = {home: (self.providers / home / ".claude.json").read_bytes() for home in HOMES}
        receipt = self.switch()
        self.assertEqual(receipt["state"], "PROVIDER_ARGS_SWITCHED")
        self.assertEqual({row["status"] for row in receipt["homes"]}, {"SWITCHED"})
        for home in HOMES:
            document = self.read_home(home)
            args = document["mcpServers"]["mmx-browser"]["args"]
            self.assertEqual(args, [self.new_path])
            # everything else in the file survives the round-trip
            self.assertEqual(document["mcpServers"]["unrelated-server"],
                             {"command": "keep", "args": ["me"]})
            self.assertTrue(document["hasCompletedOnboarding"])
            self.assertEqual(document["numStartups"], 7)
            # a .previous.<16hex> backup holds the exact prior bytes
            backups = list((self.providers / home).glob(".claude.json.previous.*"))
            self.assertEqual(len(backups), 1, home)
            self.assertEqual(backups[0].read_bytes(), before[home])
        # the receipt names files only — never contents
        serialized = json.dumps(receipt)
        for secret in ("hasCompletedOnboarding", "numStartups", "unrelated-server", "node"):
            self.assertNotIn(secret, serialized)

    def test_worker_home_never_gets_an_entry_and_is_never_written(self):
        worker_file = self.providers / WORKER / ".claude.json"
        before = folder_hash(self.providers / WORKER)
        self.switch()
        self.assertEqual(folder_hash(self.providers / WORKER), before)
        self.assertNotIn("mmx-browser", self.read_home(WORKER).get("mcpServers", {}))
        self.assertFalse(list((self.providers / WORKER).glob(".claude.json.previous.*")))
        self.assertTrue(worker_file.is_file())

    def test_worker_home_with_an_entry_refuses_the_whole_run(self):
        self.write_home(WORKER)  # an entry that must not be there
        before = folder_hash(self.providers)
        with self.assertRaises(reg.SwitchRefusal) as caught:
            self.switch()
        self.assertIn(WORKER, str(caught.exception))
        self.assertIn("WORKER_HAS_ENTRY", str(caught.exception))
        self.assertEqual(folder_hash(self.providers), before)

    def test_a_single_wrong_entry_refuses_everything_before_the_first_write(self):
        foreign = "/somewhere/else/server.js"
        self.write_home("fabric-unified-router", server_path=foreign)
        before = folder_hash(self.providers)
        with self.assertRaises(reg.SwitchRefusal) as caught:
            self.switch()
        message = str(caught.exception)
        self.assertIn("fabric-unified-router", message)
        self.assertIn("ARGS_INVALID", message)
        # file names and codes only — never contents
        self.assertNotIn(foreign, message)
        # nothing was written anywhere: no backups, no changed bytes
        self.assertEqual(folder_hash(self.providers), before)
        self.assertEqual(list(self.providers.rglob(".claude.json.previous.*")), [])

    def test_missing_entry_and_invalid_json_refuse_naming_the_home(self):
        self.write_home("experiential-claude", extra=False)
        with self.assertRaises(reg.SwitchRefusal) as caught:
            self.switch()
        self.assertIn("experiential-claude", str(caught.exception))
        self.assertIn("ENTRY_MISSING", str(caught.exception))
        self.write_home("experiential-claude")
        (self.providers / "experiential-claude" / ".claude.json").write_bytes(b"{dup")
        with self.assertRaises(reg.SwitchRefusal) as caught:
            self.switch()
        self.assertIn("experiential-claude", str(caught.exception))
        self.assertIn("JSON_INVALID", str(caught.exception))

    def test_new_target_must_exist_before_any_spawn_is_pointed_at_it(self):
        (self.mmx / "current").unlink()
        before = folder_hash(self.providers)
        with self.assertRaises(reg.SwitchRefusal) as caught:
            self.switch()
        self.assertIn("NEW_TARGET_MISSING", str(caught.exception))
        self.assertEqual(folder_hash(self.providers), before)

    def test_rerun_reports_already_switched_and_rewrites_nothing(self):
        self.switch()
        after_first = folder_hash(self.providers)
        receipt = self.switch()
        self.assertEqual(receipt["state"], "PROVIDER_ARGS_SWITCHED")
        self.assertEqual({row["status"] for row in receipt["homes"]}, {"ALREADY_SWITCHED"})
        self.assertEqual(folder_hash(self.providers), after_first)  # no second backup

    def test_readback_catches_a_session_that_rewrote_a_file(self):
        raced = self.providers / "fabric-experiential" / ".claude.json"

        def racing_pause(seconds):
            # a running session rewrites the file back to the flat path
            # between the write and the readback
            document = json.loads(raced.read_bytes())
            document["mcpServers"]["mmx-browser"]["args"] = [self.old_path]
            raced.write_bytes(json_bytes(document))

        receipt = self.switch(pause=racing_pause)
        self.assertEqual(receipt["state"], "PROVIDER_ARGS_SWITCHED_WITH_RACES")
        statuses = {row["home"]: row["status"] for row in receipt["homes"]}
        self.assertEqual(statuses["fabric-experiential"], "READBACK_RACE_REVERTED")
        self.assertEqual(statuses["fabric-unified-router"], "SWITCHED")

    def test_write_cas_refuses_when_the_file_changed_since_the_check(self):
        original = reg.write_owned
        target = self.providers / "fabric-anthropic-oauth" / ".claude.json"

        def racing_write(path, content, mode=0o600, expected=None):
            if Path(path) == target:
                # a running session rewrites the file after the check phase
                document = json.loads(target.read_bytes())
                document["numStartups"] = 8
                target.write_bytes(json_bytes(document))
            return original(path, content, mode, expected=expected)

        patched = reg
        old_attribute = patched.write_owned
        patched.write_owned = racing_write
        try:
            receipt = self.switch()
        finally:
            patched.write_owned = old_attribute
        self.assertEqual(receipt["state"], "PROVIDER_ARGS_SWITCHED_WITH_RACES")
        statuses = {row["home"]: row["status"] for row in receipt["homes"]}
        self.assertEqual(statuses["fabric-anthropic-oauth"], "WRITE_RACE")
        # the raced file kept the session's bytes — the switch did not land
        self.assertEqual(self.read_home("fabric-anthropic-oauth")["numStartups"], 8)
        self.assertEqual(self.read_home("fabric-anthropic-oauth")
                         ["mcpServers"]["mmx-browser"]["args"], [self.old_path])
        self.assertEqual(original, old_attribute)

    def test_cli_requires_both_roots_and_writes_nothing_without_them(self):
        before = folder_hash(self.root)
        completed = subprocess.run(
            [sys.executable, "-m", "integrations.hermes_harness.mmx_provider_registration"],
            capture_output=True, text=True, cwd=ROOT, timeout=60,
            env={**os.environ, "HOME": str(self.root / "no-home")},
        )
        self.assertEqual(completed.returncode, 2, completed.stderr)
        self.assertIn("--providers-root", completed.stderr)
        self.assertIn("usage", completed.stderr.lower())
        self.assertEqual(folder_hash(self.root), before)
        self.assertFalse((self.root / "no-home").exists())

    def test_cli_switches_fixtures_and_prints_a_names_only_receipt(self):
        completed = subprocess.run(
            [sys.executable, "-m", "integrations.hermes_harness.mmx_provider_registration",
             "--providers-root", str(self.providers), "--mmx-root", str(self.mmx),
             "--readback-wait", "0"],
            capture_output=True, text=True, cwd=ROOT, timeout=60,
            env={**os.environ, "HOME": str(self.root / "cli-home"), "TMPDIR": "/tmp"},
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        receipt = json.loads(completed.stdout)
        self.assertEqual(receipt["state"], "PROVIDER_ARGS_SWITCHED")
        self.assertEqual({row["home"] for row in receipt["homes"]}, set(HOMES))
        self.assertNotIn("numStartups", completed.stdout)
        for home in HOMES:
            self.assertEqual(self.read_home(home)["mcpServers"]["mmx-browser"]["args"],
                             [self.new_path])


if __name__ == "__main__":
    unittest.main(verbosity=2)
