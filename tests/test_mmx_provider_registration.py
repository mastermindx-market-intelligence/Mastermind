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

BR-MICRO3 class rule (principal, 17:32Z 2026-11-12): a change to one value
in a settings file other programs own leaves every byte outside that value
as it was, and the test proves it by comparing bytes. The real files are
unsorted, carry non-ASCII text and floats, one is ~81 KB, and running
sessions rewrite them — so the switch must replace the JSON-encoded old
path in the RAW BYTES (exactly one occurrence, else OLD_VALUE_NOT_UNIQUE
refuses the whole run before any write), never re-serialise, and report a
write error that is not a digest mismatch as what it is (WRITE_FAILED with
the errno name), not WRITE_RACE. The byte-preservation, uniqueness and
classification tests below fail first on 2186a6684, where the switch still
wrote every file back through json_bytes (indent 2, sorted, ASCII escapes,
trailing newline added) and folded every write error into WRITE_RACE.
"""
from __future__ import annotations

import errno as errno_module
import hashlib
import json
import os
from pathlib import Path
import stat
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

    def raw_fixture(self, extra_pair="", trailing_newline=False):
        """A .claude.json shaped like the REAL files, not like json_bytes:
        unsorted keys, raw non-ASCII text, a float spelling (0.00001234)
        that a re-serialise would rewrite as 1.234e-05, and a trailing
        newline only when asked. The old server path sits in args exactly
        once unless extra_pair says otherwise."""
        raw = ('{"numStartups": 7, "hasCompletedOnboarding": true, '
               '"note": "café — 日本語 · Übersicht", "rate": 0.00001234, '
               '"mcpServers": {"mmx-browser": {"command": "node", "args": ['
               + json.dumps(self.old_path, ensure_ascii=False)
               + ']}, "zzz-keep": {"command": "keep", "args": ["me"]}}'
               + extra_pair + '}')
        return (raw + ("\n" if trailing_newline else "")).encode("utf-8")

    def write_home_raw(self, home, raw, mode=0o600):
        path = self.providers / home / ".claude.json"
        path.unlink(missing_ok=True)
        path.write_bytes(raw)
        path.chmod(mode)

    def expected_swap(self, raw):
        needle = json.dumps(self.old_path, ensure_ascii=False).encode("utf-8")
        replacement = json.dumps(self.new_path, ensure_ascii=False).encode("utf-8")
        self.assertEqual(raw.count(needle), 1, "fixture must carry the needle exactly once")
        return raw.replace(needle, replacement)

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

    # ---- BR-MICRO3: the byte-preservation class rule (items a + b) ----

    def test_switch_replaces_only_the_one_value_leaving_every_other_byte(self):
        # unsorted keys, raw non-ASCII, a 0.00001234 float spelling, NO
        # trailing newline — a re-serialise would change all four
        raw = self.raw_fixture()
        self.write_home_raw("experiential-claude", raw, mode=0o600)
        receipt = self.switch()
        self.assertEqual(receipt["state"], "PROVIDER_ARGS_SWITCHED")
        path = self.providers / "experiential-claude" / ".claude.json"
        out = path.read_bytes()
        self.assertEqual(out, self.expected_swap(raw))
        # the class rule, byte by byte: order, non-ASCII, float, no newline
        self.assertIn("café — 日本語 · Übersicht".encode("utf-8"), out)
        self.assertIn(b'"rate": 0.00001234', out)
        self.assertIn(b'"numStartups": 7', out)  # still first — unsorted
        self.assertFalse(out.endswith(b"\n"))
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        # the backup holds the exact prior bytes
        backups = list(path.parent.glob(".claude.json.previous.*"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_bytes(), raw)

    def test_switch_preserves_a_trailing_newline_and_the_file_mode(self):
        raw = self.raw_fixture(trailing_newline=True)
        self.write_home_raw("fabric-experiential", raw, mode=0o644)
        self.switch()
        path = self.providers / "fabric-experiential" / ".claude.json"
        out = path.read_bytes()
        self.assertEqual(out, self.expected_swap(raw))
        self.assertTrue(out.endswith(b"\n"))
        self.assertEqual(out.count(b"\n"), raw.count(b"\n"))  # no added newline
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o644)

    def test_old_value_in_another_string_refuses_the_whole_run(self):
        # the old path also sits, exactly, in another string value: the
        # JSON-encoded old value occurs TWICE in the raw bytes, so no
        # replacement is safe — refuse BEFORE any write in ANY home
        raw = self.raw_fixture(extra_pair=', "previousServer": '
                               + json.dumps(self.old_path, ensure_ascii=False))
        self.write_home_raw("fabric-unified-router", raw)
        before = folder_hash(self.providers)
        with self.assertRaises(reg.SwitchRefusal) as caught:
            self.switch()
        message = str(caught.exception)
        self.assertIn("OLD_VALUE_NOT_UNIQUE", message)
        self.assertIn("fabric-unified-router", message)
        self.assertEqual(folder_hash(self.providers), before)
        self.assertEqual(list(self.providers.rglob(".claude.json.previous.*")), [])

    def test_old_path_inside_a_longer_string_is_left_byte_identical(self):
        # the quoted JSON-encoded value occurs exactly once even though the
        # path TEXT also appears inside a longer string — that longer string
        # is outside the value, so every byte of it survives
        raw = self.raw_fixture(extra_pair=', "history": '
                               + json.dumps("was " + self.old_path + " before"))
        self.write_home_raw("fabric-anthropic-oauth", raw)
        self.switch()
        path = self.providers / "fabric-anthropic-oauth" / ".claude.json"
        out = path.read_bytes()
        self.assertEqual(out, self.expected_swap(raw))
        self.assertIn(("was " + self.old_path + " before").encode("utf-8"), out)

    # ---- BR-MICRO3 item c: a write error reports what it is ----

    def test_a_write_error_that_is_not_a_digest_mismatch_reports_errno(self):
        original = reg.write_owned
        target = self.providers / "fabric-anthropic-oauth" / ".claude.json"
        before_target = target.read_bytes()

        def failing_write(path, content, mode=0o600, expected=None):
            if Path(path) == target:
                raise PermissionError(errno_module.EACCES, "Permission denied")
            return original(path, content, mode, expected=expected)

        reg.write_owned = failing_write
        try:
            receipt = self.switch()
        finally:
            reg.write_owned = original
        self.assertEqual(receipt["state"], "PROVIDER_ARGS_SWITCHED_WITH_RACES")
        rows = {row["home"]: row for row in receipt["homes"]}
        self.assertEqual(rows["fabric-anthropic-oauth"]["status"], "WRITE_FAILED")
        self.assertIn("EACCES", json.dumps(rows["fabric-anthropic-oauth"]))
        # the other homes still switch
        self.assertEqual(rows["experiential-claude"]["status"], "SWITCHED")
        # the failed home: file untouched, no backup
        self.assertEqual(target.read_bytes(), before_target)
        self.assertEqual(list(target.parent.glob(".claude.json.previous.*")), [])

    def test_a_digest_mismatch_still_reports_write_race(self):
        # the other half of item c: only a digest mismatch is a WRITE_RACE
        original = reg.write_owned
        target = self.providers / "fabric-experiential" / ".claude.json"

        def racing_write(path, content, mode=0o600, expected=None):
            if Path(path) == target:
                document = json.loads(target.read_bytes())
                document["numStartups"] = 9
                target.write_bytes(json_bytes(document))
            return original(path, content, mode, expected=expected)

        reg.write_owned = racing_write
        try:
            receipt = self.switch()
        finally:
            reg.write_owned = original
        rows = {row["home"]: row for row in receipt["homes"]}
        self.assertEqual(rows["fabric-experiential"]["status"], "WRITE_RACE")
        self.assertNotIn("detail", rows["fabric-experiential"])

    # ---- BR-MICRO3 item d: what a re-run does after a WRITE_RACE ----

    def test_rerun_after_a_write_race_switches_only_the_raced_home(self):
        original = reg.write_owned
        target = self.providers / "fabric-anthropic-oauth" / ".claude.json"

        def racing_write(path, content, mode=0o600, expected=None):
            if Path(path) == target:
                # a running session rewrites the file after the check phase
                document = json.loads(target.read_bytes())
                document["numStartups"] = 8
                target.write_bytes(json_bytes(document))
            return original(path, content, mode, expected=expected)

        reg.write_owned = racing_write
        try:
            first = self.switch()
        finally:
            reg.write_owned = original
        self.assertEqual(first["state"], "PROVIDER_ARGS_SWITCHED_WITH_RACES")
        statuses = {row["home"]: row["status"] for row in first["homes"]}
        self.assertEqual(statuses["fabric-anthropic-oauth"], "WRITE_RACE")
        self.assertEqual({statuses[home] for home in HOMES
                          if home != "fabric-anthropic-oauth"}, {"SWITCHED"})
        # the race left NO effect on that home: the session's bytes stand,
        # and the CAS refusal happened before any backup was written
        self.assertEqual(self.read_home("fabric-anthropic-oauth")["numStartups"], 8)
        self.assertEqual(self.read_home("fabric-anthropic-oauth")
                         ["mcpServers"]["mmx-browser"]["args"], [self.old_path])
        self.assertEqual(list(target.parent.glob(".claude.json.previous.*")), [])
        # the re-run: the raced home is still PLANNED and switches now; the
        # already-switched homes are skipped without a second write or backup
        second = self.switch()
        self.assertEqual(second["state"], "PROVIDER_ARGS_SWITCHED")
        statuses = {row["home"]: row["status"] for row in second["homes"]}
        self.assertEqual(statuses["fabric-anthropic-oauth"], "SWITCHED")
        self.assertEqual({statuses[home] for home in HOMES
                          if home != "fabric-anthropic-oauth"}, {"ALREADY_SWITCHED"})
        # the session's own value survives the late byte-preserving switch
        self.assertEqual(self.read_home("fabric-anthropic-oauth")["numStartups"], 8)
        self.assertEqual(self.read_home("fabric-anthropic-oauth")
                         ["mcpServers"]["mmx-browser"]["args"], [self.new_path])
        for home in HOMES:
            backups = list((self.providers / home).glob(".claude.json.previous.*"))
            self.assertEqual(len(backups), 1, home)

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
