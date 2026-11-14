"""BR-COMPATFIX: the mmx-browser pin writer never targets a loaded folder.

Ruling-15 class rule applied to the pin switch (runbook step 4): a running
bridge server captured ``runtime.json`` at startup, re-verifies it before
every dispatch, and was spawned from the ``server.js`` its pin resolved —
editing either under a running server fails every live session (the first
install attempt's 31-server ``NATIVE_SOURCE_CLOSURE_STALE`` outage). The
guarded writer therefore:

* has no default target at all — every command requires ``--mmx-root``;
* never edits the flat live pin files (``$MMX/runtime.json``, ``$MMX/server.js``);
* never writes inside the folder ``$MMX/current`` resolves to (that folder is
  loaded by every server spawned since the last switch);
* treats a delivered ``runtimes/<commit>/runtime.json`` as permanent
  (ruling 19: a delivery mark is never overwritten or re-derived away);
* switches only by an atomic symlink replace, so running servers keep their
  already-resolved files and only the next spawn sees the new pin.

Fails first on 72de0bab3: ``integrations.hermes_harness.runtime_pin`` does
not exist there — the pin write was unguarded inline runbook python.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from integrations.hermes_harness.install_browser import digest, json_bytes, write_owned
from integrations.hermes_harness import runtime_pin

ROOT = Path(__file__).resolve().parents[1]
OLD = "5" * 40
NEW = "6" * 40
SERVER_BYTES = b"// scratch server.js stand-in (opaque bytes; never executed here)\n"
PROTOCOL = "integrations/chairman_surfaces/web_sol_protocol.py"
BRIDGE = "integrations/hermes_harness/browser_bridge.py"


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


class RuntimePinGuard(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="mb-pin-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.mmx = self.root / "mmx-browser"
        self.base = self.root / "install"
        (self.base / "releases" / OLD).mkdir(parents=True)
        (self.base / "releases" / NEW).mkdir(parents=True)
        self.flat_pin = dict(
            schema="mastermind.browser.mcp_runtime/v1", release_commit=OLD,
            source_root=str(self.base / "releases" / OLD), python_executable=sys.executable,
            profile_home=str(self.root / "t3-home"),
            bindings_path=str(self.base / "deployments-v2.json"),
            source_files={PROTOCOL: "a" * 64, BRIDGE: "b" * 64},
            upload_roots=[str(self.root / "uploads")],
            artifact_root=str(self.root / "artifacts"))
        write_owned(self.mmx / "runtime.json", json_bytes(self.flat_pin))
        write_owned(self.mmx / "server.js", SERVER_BYTES, 0o644)
        manifest = dict(schema="mastermind.browser_direct_build.v1", source_commit=NEW,
                        files={PROTOCOL: "c" * 64, BRIDGE: "d" * 64,
                               "tests/test_web_sol_transport_compat.py": "e" * 64})
        self.manifest_path = self.root / "BUILD-new.json"
        write_owned(self.manifest_path, json_bytes(manifest))

    def migrate(self):
        return runtime_pin.migrate(self.mmx, OLD, NEW, self.manifest_path)

    def read_json(self, path):
        return json.loads(path.read_bytes())

    def test_migrate_delivers_both_versioned_pins_and_points_current_at_old(self):
        before_flat = (folder_hash(self.mmx / "runtime.json"), folder_hash(self.mmx / "server.js"))
        receipt = self.migrate()
        self.assertEqual(receipt["state"], "PIN_MIGRATED")
        old_folder = self.mmx / "runtimes" / OLD
        new_folder = self.mmx / "runtimes" / NEW
        # OLD carries the verbatim live pin and byte-identical server.js.
        self.assertEqual(old_folder.joinpath("runtime.json").read_bytes(),
                         json_bytes(self.flat_pin))
        self.assertEqual((old_folder / "server.js").read_bytes(), SERVER_BYTES)
        # NEW carries the updated pin: new commit, new source root, updated closure hashes.
        new_pin = self.read_json(new_folder / "runtime.json")
        self.assertEqual(new_pin["release_commit"], NEW)
        self.assertEqual(new_pin["source_root"], str(self.base / "releases" / NEW))
        self.assertEqual(new_pin["source_files"], {PROTOCOL: "c" * 64, BRIDGE: "d" * 64})
        self.assertEqual((new_folder / "server.js").read_bytes(), SERVER_BYTES)
        # current -> OLD first: no behavior change until the explicit switch.
        self.assertEqual((self.mmx / "current").resolve(), old_folder.resolve())
        # The flat live pin files were never edited in place.
        self.assertEqual((folder_hash(self.mmx / "runtime.json"),
                          folder_hash(self.mmx / "server.js")), before_flat)
        # Pins are owner-only: server.js refuses group/world-writable pins.
        self.assertEqual(new_folder.joinpath("runtime.json").stat().st_mode & 0o777, 0o600)

    def test_migration_is_one_time_and_refuses_a_second_run(self):
        self.migrate()
        with self.assertRaises(RuntimeError) as caught:
            self.migrate()
        self.assertIn("current", str(caught.exception))

    def test_delivered_pin_is_permanent_and_never_overwritten(self):
        self.migrate()
        with self.assertRaises(RuntimeError) as caught:
            runtime_pin.deliver(self.mmx, NEW, self.flat_pin, SERVER_BYTES)
        message = str(caught.exception)
        self.assertIn("permanent", message)
        self.assertIn(str(self.mmx / "runtimes" / NEW), message)
        # The delivered bytes are unchanged.
        self.assertEqual(self.read_json(self.mmx / "runtimes" / NEW / "runtime.json")
                         ["release_commit"], NEW)

    def test_writing_the_live_versioned_folder_refuses_naming_it(self):
        self.migrate()
        runtime_pin.switch(self.mmx, NEW)
        # current -> runtimes/NEW is now loaded by every freshly spawned server;
        # even a differently-shaped write into it must refuse.
        live = self.mmx / "runtimes" / NEW
        before = folder_hash(live)
        with self.assertRaises(RuntimeError) as caught:
            runtime_pin.deliver(self.mmx, NEW, dict(self.flat_pin, release_commit=NEW),
                                SERVER_BYTES)
        self.assertIn("permanent", str(caught.exception))
        self.assertEqual(folder_hash(live), before)  # the live folder is untouched
        with self.assertRaises(RuntimeError) as caught:
            runtime_pin.migrate(self.mmx, OLD, NEW, self.manifest_path)
        self.assertIn("current", str(caught.exception))

    def test_switch_is_an_atomic_repoint_and_leaves_the_old_folder_untouched(self):
        self.migrate()
        before_old = folder_hash(self.mmx / "runtimes" / OLD)
        receipt = runtime_pin.switch(self.mmx, NEW)
        self.assertEqual(receipt["state"], "PIN_SWITCHED")
        self.assertEqual((self.mmx / "current").resolve(),
                         (self.mmx / "runtimes" / NEW).resolve())
        # A running server's resolved files are byte-identical after the switch.
        self.assertEqual(folder_hash(self.mmx / "runtimes" / OLD), before_old)
        # And the switch back is the rollback: same mechanism, no rewrite.
        runtime_pin.switch(self.mmx, OLD)
        self.assertEqual((self.mmx / "current").resolve(),
                         (self.mmx / "runtimes" / OLD).resolve())
        self.assertEqual(folder_hash(self.mmx / "runtimes" / OLD), before_old)

    def test_switch_refuses_an_undelivered_commit(self):
        self.migrate()
        with self.assertRaises(RuntimeError) as caught:
            runtime_pin.switch(self.mmx, "7" * 40)
        self.assertIn("not a delivered runtime pin", str(caught.exception))

    def test_invalid_commit_and_missing_flat_pin_refuse(self):
        with self.assertRaises(RuntimeError):
            runtime_pin.migrate(self.mmx, "not-a-commit", NEW, self.manifest_path)
        empty = self.root / "empty-mmx"
        empty.mkdir()
        with self.assertRaises(RuntimeError) as caught:
            runtime_pin.migrate(empty, OLD, NEW, self.manifest_path)
        self.assertIn("no flat", str(caught.exception))

    def test_manifest_must_name_the_new_commit(self):
        foreign = dict(schema="mastermind.browser_direct_build.v1", source_commit=OLD,
                       files={PROTOCOL: "c" * 64})
        path = self.root / "BUILD-foreign.json"
        write_owned(path, json_bytes(foreign))
        with self.assertRaises(RuntimeError) as caught:
            runtime_pin.migrate(self.mmx, OLD, NEW, path)
        self.assertIn("does not name the new commit", str(caught.exception))

    def test_migrate_checks_both_targets_before_its_first_write(self):
        # BR-MICRO2 item 1 (plan 48): an apply that can refuse does so before
        # its first write. NEW is already delivered (e.g. a prior partial
        # round); the pre-fix code created runtimes/<OLD> before it hit the
        # NEW refusal, leaving the tree half-migrated. The refusal must fire
        # with the WHOLE mmx tree unchanged, and a re-run must behave
        # identically (refuse again, still nothing written).
        runtime_pin.deliver(self.mmx, NEW, dict(self.flat_pin, release_commit=NEW),
                            SERVER_BYTES)
        before = folder_hash(self.mmx)
        with self.assertRaises(RuntimeError) as caught:
            self.migrate()
        self.assertIn("already delivered", str(caught.exception))
        self.assertEqual(folder_hash(self.mmx), before)
        self.assertFalse((self.mmx / "runtimes" / OLD).exists())
        # the re-run behaves correctly: same refusal, tree still untouched
        with self.assertRaises(RuntimeError) as caught:
            self.migrate()
        self.assertIn("already delivered", str(caught.exception))
        self.assertEqual(folder_hash(self.mmx), before)
        self.assertFalse((self.mmx / "runtimes" / OLD).exists())

    def test_deliver_refuses_while_another_process_holds_the_delivery_lock(self):
        # Ruling 19 fold-in: the delivery mark is check-then-write; a second
        # process must not pass the check while the first is writing. The
        # O_EXCL lock file stands in for the other process's held lock.
        lock = self.mmx / ".deliver.lock"
        write_owned(lock, b"held by another process\n", 0o600)
        before = folder_hash(self.mmx)
        with self.assertRaises(RuntimeError) as caught:
            runtime_pin.deliver(self.mmx, NEW, self.flat_pin, SERVER_BYTES)
        self.assertIn("delivery lock", str(caught.exception))
        self.assertEqual(folder_hash(self.mmx), before)
        self.assertFalse((self.mmx / "runtimes" / NEW).exists())
        # The foreign lock is not ours to remove.
        self.assertTrue(lock.exists())

    def test_deliver_holds_the_lock_across_its_writes_and_releases_it(self):
        seen = []
        original = runtime_pin.write_owned

        def watching(path, payload, mode=0o600):
            seen.append((self.mmx / ".deliver.lock").exists())
            return original(path, payload, mode)

        runtime_pin.write_owned = watching
        try:
            runtime_pin.deliver(self.mmx, NEW, self.flat_pin, SERVER_BYTES)
        finally:
            runtime_pin.write_owned = original
        self.assertTrue(seen, "deliver wrote nothing")
        self.assertTrue(all(seen), "the lock must cover every delivery write")
        self.assertFalse((self.mmx / ".deliver.lock").exists())
        # A refusal also releases the lock; the permanent mark still refuses.
        with self.assertRaises(RuntimeError) as caught:
            runtime_pin.deliver(self.mmx, NEW, self.flat_pin, SERVER_BYTES)
        self.assertIn("permanent", str(caught.exception))
        self.assertFalse((self.mmx / ".deliver.lock").exists())

    def test_migrate_refuses_while_the_delivery_lock_is_held(self):
        lock = self.mmx / ".deliver.lock"
        write_owned(lock, b"held by another process\n", 0o600)
        before = folder_hash(self.mmx)
        with self.assertRaises(RuntimeError) as caught:
            self.migrate()
        self.assertIn("delivery lock", str(caught.exception))
        self.assertEqual(folder_hash(self.mmx), before)
        self.assertFalse((self.mmx / "current").exists())
        self.assertTrue(lock.exists())

    def test_migrate_holds_one_lock_across_both_deliveries(self):
        seen = []
        original = runtime_pin.write_owned

        def watching(path, payload, mode=0o600):
            seen.append((self.mmx / ".deliver.lock").exists())
            return original(path, payload, mode)

        runtime_pin.write_owned = watching
        try:
            self.migrate()
        finally:
            runtime_pin.write_owned = original
        # Four delivery writes (server.js + runtime.json for OLD and NEW),
        # every one under the same held lock; released once at the end.
        self.assertEqual(len(seen), 4)
        self.assertTrue(all(seen))
        self.assertFalse((self.mmx / ".deliver.lock").exists())

    def test_cli_has_no_default_root_and_requires_mmx_root(self):
        # The class rule at the CLI: no default target exists; omitting the
        # root is a usage error that writes nothing.
        completed = subprocess.run(
            [sys.executable, "-m", "integrations.hermes_harness.runtime_pin",
             "switch", "--commit", NEW],
            capture_output=True, text=True, cwd=ROOT, timeout=60,
            env={**os.environ, "HOME": str(self.root / "no-home")},
        )
        self.assertEqual(completed.returncode, 2, completed.stderr)
        self.assertIn("--mmx-root", completed.stderr)
        self.assertIn("usage", completed.stderr.lower())
        self.assertFalse((self.root / "no-home").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
