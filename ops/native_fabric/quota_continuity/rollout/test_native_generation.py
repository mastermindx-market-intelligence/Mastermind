"""Offline process/race proofs. No provider, network, broker or live kit calls."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import native_generation as g
import native_install as installer


class NativeGenerationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="native-generation-proof-",
            dir=os.environ.get("NATIVE_ROLLOUT_TEST_ROOT"))
        self.base = Path(self.temp.name).resolve()
        # The real owner requires an enumerable Studio consumer root. Fixture
        # isolation prevents tests from consulting or changing production pins.
        self.studio_root = self.base / "studio-private"
        self.studio_root.mkdir()
        self._consumer_root_patch = mock.patch.object(
            installer.studio_consumer_owner, "STUDIO_CONSUMER_ROOT", self.studio_root,
        )
        self._consumer_root_patch.start()
        self.addCleanup(self._consumer_root_patch.stop)
        self.kit = self.base / "kit"
        self.ext = self.kit / "ext"
        self.ext.mkdir(parents=True)
        for name in ("state", "broker", "active", "lanes", "slots"):
            (self.ext / name).mkdir()
        (self.kit / "orch").mkdir()
        (self.base / "bin").mkdir()
        self.pool = self.base / "bin" / "pool"
        self.sources = {}
        self.processes = []
        self.make_source("V0", extended=False)
        for item in (self.sources["V0"] / "ext").iterdir():
            shutil.copyfile(item, self.ext / item.name)
        self.pool.write_bytes(self.original_pool())
        self.pool.chmod(0o755)
        for name in ("fabric_task.py", "remote_sub.sh"):
            (self.ext / name).chmod(0o755)

    def tearDown(self):
        for process in self.processes:
            if process.poll() is None:
                process.kill()
                process.communicate(timeout=5)
        # These are exclusively our throwaway publication fixtures. Do not
        # follow their state symlinks while undoing sealed directory modes.
        for root, directories, files in os.walk(self.base, topdown=True, followlinks=False):
            os.chmod(root, 0o700)
        self.temp.cleanup()

    def original_pool(self):
        return (f'#!/bin/bash\nset -u\nKIT_DIR="{self.kit}"\n'
                'case "${1:-}" in\n'
                ' run) shift; exec python3 "$KIT_DIR/ext/helper.py" "$@" ;;\n'
                ' remote) shift; exec bash "$KIT_DIR/ext/remote_sub.sh" "$@" ;;\n'
                ' *) exit 2 ;;\nesac\n').encode()

    def studio_consumer(self, pinned_sha, account="fabric-consumer-fixture"):
        directory = self.studio_root / account
        directory.mkdir(exist_ok=True)
        path = directory / "config.json"
        path.write_text(json.dumps({
            "fleetStatus": {
                "enabled": True,
                "fabricLauncherPath": str(self.pool),
                "fabricLauncherSha256": pinned_sha,
            },
        }))
        return path

    def make_source(self, version, extended=True):
        root = self.base / ("source-" + version)
        ext = root / "ext"
        ext.mkdir(parents=True)
        pool = installer.relocate_pool(self.original_pool())
        (root / "pool").write_bytes(pool)
        task = '''#!/usr/bin/env python3
"""A baseline API plus a foreground parent that can pause before its child."""
from __future__ import annotations
import subprocess
from pathlib import Path
import sys
HERE = Path(__file__).resolve().parent
API_VERSION = "V0"
def baseline_status():
    return API_VERSION
if __name__ == "__main__":
    if sys.argv[1:] == ["--hold-parent"]:
        print("PARENT_READY", flush=True)
        sys.stdin.readline()
    raise SystemExit(subprocess.call(["/bin/bash", str(HERE / "remote_sub.sh")]))
'''
        (ext / "fabric_task.py").write_text(task)
        helper = ("from pathlib import Path\n"
                  + ("from new_module import VERSION\n" if extended else f"VERSION = {version!r}\n")
                  + "print(VERSION)\n")
        (ext / "helper.py").write_text(helper)
        if extended:
            (ext / "new_module.py").write_text(f"VERSION = {version!r}\n")
        names = ["helper.py"] + (["new_module.py"] if extended else [])
        # Freeze the explicit support list in the running controller, hash once,
        # pause, then reopen/copy exactly that list like the real scp seam.
        remote = ("#!/bin/bash\nset -u\n"
                  'HERE="$(cd "$(dirname "$0")" && pwd -P)"\n'
                  f"exec {sys.executable!s} -u -c "
                  + __import__("shlex").quote('''import hashlib,json,subprocess,sys,tempfile
from pathlib import Path
here=Path(sys.argv[1]); names=json.loads(sys.argv[2])
hashed={n:hashlib.sha256((here/n).read_bytes()).hexdigest() for n in names}
if sys.argv[3:]==['--hold-transfer']:
    print(json.dumps({'ready':True,'here':str(here),'hashes':hashed}),flush=True)
    sys.stdin.readline()
with tempfile.TemporaryDirectory() as tmp:
    dest=Path(tmp)
    for name in names:
        body=(here/name).read_bytes()
        if hashlib.sha256(body).hexdigest()!=hashed[name]:
            raise SystemExit('MIXED_SOURCE_GENERATION')
        (dest/name).write_bytes(body)
    raise SystemExit(subprocess.call([sys.executable,str(dest/'helper.py')]))
''') + ' "$HERE" ' + __import__("shlex").quote(json.dumps(names)) + ' "$@"\n')
        (ext / "remote_sub.sh").write_text(remote)
        self.sources[version] = root
        return root

    def publish(self, version):
        source = self.sources[version]
        files = {"pool": g.digest((source / "pool").read_bytes())}
        files.update({"ext/" + p.name: g.digest(p.read_bytes()) for p in (source / "ext").iterdir()})
        return g.publish(source, self.ext, files)

    def run_cmd(self, command):
        result = subprocess.run(command, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.strip()

    def hold(self, command, expected):
        process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, text=True)
        self.processes.append(process)
        # The subprocess itself has no uncontrolled sleep/retry. This bounded
        # read waits for the exact source-transfer or parent-start handshake.
        import selectors
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            self.assertTrue(selector.select(timeout=5), "fixture did not reach barrier")
        line = process.stdout.readline().strip()
        self.assertIn(expected, line)
        return process, line

    def release(self, process):
        out, err = process.communicate("continue\n", timeout=10)
        self.assertEqual(process.returncode, 0, err)
        return out.strip()

    def install_target(self, version="V1"):
        self.make_source(version)
        release = self.publish(version)
        self.store = release.parent
        bundle = self.base / "bootstrap-plan"
        plan = installer.prepare(self.store, release.name, self.pool, bundle)
        installer.phase1(bundle)
        return release, bundle, plan

    def legacy_receipt(self, plan, disposition="settled"):
        receipt = {"schema": installer.DRAIN_SCHEMA, "plan_digest": plan["digest"],
                   "stable_ext": str(self.ext), "owner_evidence_ref": "offline-fixture/census",
                   "legacy_pool_producers": [], "legacy_task_producers": [
                       {"pid": 123, "start_identity": "fixture-pid-123-start",
                        "disposition": disposition, "evidence_ref": "fixture/terminal"}],
                   "unresolved_imported_mutating_callers": []}
        path = self.base / "legacy-reconciliation.json"
        path.write_text(json.dumps(receipt))
        return path

    def test_old_flat_transfer_keeps_complete_old_support_closure_during_phase1(self):
        old, _ = self.hold(["bash", str(self.ext / "remote_sub.sh"), "--hold-transfer"], '"ready": true')
        before = (self.ext / "helper.py").read_bytes()
        _, bundle, _ = self.install_target()
        self.assertEqual(self.run_cmd([str(self.pool), "remote"]), "V1")
        self.assertEqual(self.run_cmd([sys.executable, str(self.ext / "fabric_task.py")]), "V1")
        self.assertEqual((self.ext / "helper.py").read_bytes(), before)
        self.assertFalse((self.ext / "new_module.py").exists())
        self.assertEqual(self.release(old), "V0")
        installer.phase1(bundle)  # A retried finite install is idempotent.

    def test_running_generation_stays_pinned_across_atomic_selection(self):
        v1, _, _ = self.install_target()
        old, line = self.hold([str(self.pool), "remote", "--hold-transfer"], '"ready": true')
        self.assertEqual(json.loads(line)["here"], str(v1 / "ext"))
        self.make_source("V2")
        v2 = self.publish("V2")
        g.select(self.store, v2.name, v1.name)
        self.assertEqual(self.run_cmd([str(self.pool), "remote"]), "V2")
        self.assertEqual(self.release(old), "V1")
        self.assertEqual((v1 / "ext/state").resolve(), self.ext / "state")
        self.assertEqual((v2 / "ext/broker").resolve(), self.ext / "broker")
        self.assertEqual((v1 / "orch").resolve(), self.kit / "orch")

    def test_old_parent_finishes_before_phase2_and_imported_api_is_preserved(self):
        parent, _ = self.hold([sys.executable, str(self.ext / "fabric_task.py"), "--hold-parent"], "PARENT_READY")
        _, bundle, plan = self.install_target()
        with self.assertRaisesRegex(ValueError, "unsettled"):
            installer.phase2(bundle, self.legacy_receipt(plan, "running"))
        self.assertEqual(self.release(parent), "V0")
        spec = importlib.util.spec_from_file_location("flat_api_fixture", self.ext / "fabric_task.py")
        imported = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(imported)
        self.assertEqual(imported.baseline_status(), "V0")
        installer.phase2(bundle, self.legacy_receipt(plan))
        self.assertEqual(self.run_cmd(["bash", str(self.ext / "remote_sub.sh")]), "V1")

    def test_failed_selection_and_partial_bootstrap_do_not_damage_flat_code(self):
        self.make_source("V1")
        release = self.publish("V1")
        store = release.parent
        bundle = self.base / "plan"
        plan = installer.prepare(store, release.name, self.pool, bundle)
        with g.publication_lock(store):
            g._select_locked(store, release.name, None)
            installer._install_launcher(bundle, plan)
            installer._install_entry(bundle, plan, "pool")
        # Simulate interruption between pool and task. Each path works and the
        # second attempt finishes the same verified artifact transition.
        self.assertEqual(self.run_cmd([str(self.pool), "remote"]), "V1")
        self.assertEqual(self.run_cmd([sys.executable, str(self.ext / "fabric_task.py")]), "V0")
        installer.phase1(bundle)
        with self.assertRaisesRegex(ValueError, "compare-and-swap"):
            g.select(store, release.name, "0" * 64)
        with self.assertRaises((ValueError, FileNotFoundError)):
            g.select(store, "f" * 64, release.name)
        self.assertEqual(g.current(store)["generation"], release.name)

    def test_rollback_only_changes_future_ingress_and_does_not_follow_state_links(self):
        original_state_mode = (self.ext / "state").stat().st_mode & 0o777
        _, bundle, plan = self.install_target()
        old, _ = self.hold([str(self.pool), "remote", "--hold-transfer"], '"ready": true')
        installer.phase2(bundle, self.legacy_receipt(plan))
        (self.ext / "state" / "owner-proof").write_text("preserve")
        installer.rollback(bundle)
        self.assertEqual(self.run_cmd([str(self.pool), "remote"]), "V0")
        self.assertEqual(self.release(old), "V1")
        self.assertEqual((self.ext / "state" / "owner-proof").read_text(), "preserve")
        self.assertEqual((self.ext / "state").stat().st_mode & 0o777, original_state_mode)

    def test_publication_rejects_changed_missing_and_symlink_source(self):
        self.make_source("V1")
        source = self.sources["V1"]
        files = {"pool": g.digest((source / "pool").read_bytes())}
        files.update({"ext/" + p.name: g.digest(p.read_bytes()) for p in (source / "ext").iterdir()})
        helper = source / "ext/helper.py"
        wanted = helper.read_bytes()
        helper.write_bytes(wanted + b"# changed\n")
        with self.assertRaisesRegex(ValueError, "manifest"):
            g.publish(source, self.ext, files)
        helper.unlink()
        with self.assertRaises(FileNotFoundError):
            g.publish(source, self.ext, files)
        helper.symlink_to(self.ext / "helper.py")
        with self.assertRaises(OSError):
            g.publish(source, self.ext, files)

    def test_rollback_terminates_bootstrap_epoch_and_rejects_stale_drain_proof(self):
        release, bundle, plan = self.install_target()
        old_proof = self.legacy_receipt(plan)
        installer.phase2(bundle, old_proof)
        installer.rollback(bundle)
        # A fresh legacy parent can exist after rollback. Prior empty/settled
        # producer evidence must never authorize replacing its child ingress.
        parent, _ = self.hold([sys.executable, str(self.ext / "fabric_task.py"), "--hold-parent"], "PARENT_READY")
        with self.assertRaisesRegex(ValueError, "terminal after rollback"):
            installer.phase1(bundle)
        with self.assertRaisesRegex(ValueError, "terminal after rollback"):
            installer.phase2(bundle, old_proof)
        fresh_bundle = self.base / "fresh-bootstrap-plan"
        fresh_plan = installer.prepare(self.store, release.name, self.pool, fresh_bundle)
        self.assertNotEqual(fresh_plan["digest"], plan["digest"])
        installer.phase1(fresh_bundle)
        with self.assertRaisesRegex(ValueError, "not bound"):
            installer.phase2(fresh_bundle, old_proof)
        self.assertEqual(self.release(parent), "V0")

    def test_interrupted_unpublished_launcher_does_not_poison_retry(self):
        self.make_source("V1")
        release = self.publish("V1")
        bundle = self.base / "launcher-interruption-plan"
        plan = installer.prepare(release.parent, release.name, self.pool, bundle)
        real_replace = os.replace
        target = Path(plan["launcher_path"])
        def interrupted(source, destination):
            if Path(destination) == target:
                raise OSError("fixture interrupted before atomic launcher publication")
            return real_replace(source, destination)
        with mock.patch.object(g.os, "replace", side_effect=interrupted):
            with self.assertRaisesRegex(OSError, "fixture interrupted"):
                installer.phase1(bundle)
        self.assertFalse(target.exists())
        self.assertEqual(self.run_cmd([str(self.pool), "remote"]), "V0")
        installer.phase1(bundle)
        self.assertEqual(self.run_cmd([str(self.pool), "remote"]), "V1")


    def test_phase1_refuses_stale_studio_consumers_until_pins_are_coordinated(self):
        self.make_source("V1")
        release = self.publish("V1")
        plan_path = self.base / "consumer-pin-plan"
        plan = installer.prepare(release.parent, release.name, self.pool, plan_path)
        original_pool = self.pool.read_bytes()
        original_task = (self.ext / "fabric_task.py").read_bytes()
        cfg = self.studio_consumer(g.digest(original_pool))
        with self.assertRaisesRegex(ValueError, "STUDIO_CONSUMER_PIN_MIGRATION_REQUIRED"):
            installer.phase1(plan_path)
        self.assertEqual(self.pool.read_bytes(), original_pool)
        self.assertEqual((self.ext / "fabric_task.py").read_bytes(), original_task)
        self.assertIsNone(g.current(release.parent))

        # The coordinating Studio owner must separately perform this update.
        cfg.write_text(json.dumps({
            "fleetStatus": {
                "enabled": True,
                "fabricLauncherPath": str(self.pool),
                "fabricLauncherSha256": plan["entries"]["pool"]["bridge"],
            },
        }))
        receipt = installer.phase1(plan_path)
        self.assertEqual(receipt["phase"], 1)
        self.assertEqual(g.digest(self.pool.read_bytes()), plan["entries"]["pool"]["bridge"])

    def test_phase1_refuses_unavailable_owner_census_before_pool_effect(self):
        self.make_source("V1")
        release = self.publish("V1")
        plan_path = self.base / "no-census-plan"
        installer.prepare(release.parent, release.name, self.pool, plan_path)
        original = self.pool.read_bytes()
        self.studio_root.rmdir()
        with self.assertRaisesRegex(ValueError, "STUDIO_CONSUMER_CENSUS_REFUSED"):
            installer.phase1(plan_path)
        self.assertEqual(self.pool.read_bytes(), original)
        self.assertIsNone(g.current(release.parent))

    def test_rollback_refuses_to_break_newly_pinned_studio_consumers(self):
        _release, bundle, plan = self.install_target()
        cfg = self.studio_consumer(plan["entries"]["pool"]["bridge"])
        new_launcher = self.pool.read_bytes()
        with self.assertRaisesRegex(ValueError, "STUDIO_CONSUMER_PIN_MIGRATION_REQUIRED"):
            installer.rollback(bundle)
        self.assertEqual(self.pool.read_bytes(), new_launcher)

        cfg.write_text(json.dumps({
            "fleetStatus": {
                "enabled": True,
                "fabricLauncherPath": str(self.pool),
                "fabricLauncherSha256": plan["entries"]["pool"]["preimage"],
            },
        }))
        result = installer.rollback(bundle)
        self.assertEqual(result["phase"], "rollback")
        self.assertEqual(g.digest(self.pool.read_bytes()), plan["entries"]["pool"]["preimage"])

if __name__ == "__main__":
    unittest.main(verbosity=2)
