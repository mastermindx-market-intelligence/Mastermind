"""Exact old/new verifier boundary; disposable artifacts, no business execution."""
import hashlib
import os
from pathlib import Path
import tempfile
import types
import unittest
from unittest import mock

import native_generation as generation


class LegacyLauncherBoundary(unittest.TestCase):
    def test_late_old_launcher_refuses_before_business_exec(self):
        current_source = Path(generation.__file__).read_bytes()
        # The host-pull plist admission is later than the paired-upgrade launcher.
        # The historical 8bc verifier is this file with that one block removed.
        admission = (
            b"    # One vetted flat plist. Not a suffix rule and not a directory walk.\n"
            b"    if relative == \"ext/host_pull_launchd.plist.template\":\n"
            b"        return\n")
        self.assertEqual(current_source.count(admission), 1)
        current_source = current_source.replace(admission, b"")
        current_fragment = (b'or parts[1] in {"yes", "host_pull_probe.template",\n'
                            b'                        "paid_pyyaml_6_0_3.zip", "paid_pyyaml_provenance.json"})')
        previous_fragment = b'or parts[1] in {"yes", "host_pull_probe.template"})'
        self.assertEqual(current_source.count(current_fragment), 1)
        previous_source = current_source.replace(current_fragment, previous_fragment)
        self.assertEqual(hashlib.sha256(previous_source).hexdigest(),
                         "8bc1153289914d793264ca5d684eb7206f2b5d38fcbaadc3de9f9cc04a9baa88")
        old = types.ModuleType("exact_previous_launcher")
        exec(compile(previous_source, "<sealed-8bc-launcher>", "exec"), old.__dict__)

        with tempfile.TemporaryDirectory(prefix="late-launcher-boundary-") as temp:
            root = Path(temp).resolve()
            source = root / "source"
            (source / "ext").mkdir(parents=True)
            ext = root / "kit/ext"
            ext.mkdir(parents=True)
            files = {"pool": b"# inert pool\n",
                     "ext/fabric_task.py": b"raise AssertionError('business must not execute')\n",
                     "ext/remote_sub.sh": b"# inert remote\n"}
            for name, raw in files.items():
                (source / name).write_bytes(raw)
            digest = lambda raw: hashlib.sha256(raw).hexdigest()
            prior = generation.publish(source, ext, {n: digest(b) for n, b in files.items()})
            store = ext.parent / generation.STORE_NAME
            generation.select(store, prior.name, None)
            pinned_source = (prior / "ext/fabric_task.py").read_bytes()

            for name in ("ext/paid_pyyaml_6_0_3.zip", "ext/paid_pyyaml_provenance.json"):
                files[name] = b"inert closed-name fixture"
                (source / name).write_bytes(files[name])
            target = generation.publish(source, ext, {n: digest(b) for n, b in files.items()})
            generation.select(store, target.name, prior.name)

            with mock.patch.object(os, "execve", side_effect=AssertionError("business exec")) as execute:
                with self.assertRaisesRegex(ValueError, "manifest must explicitly name"):
                    old.launch(store, "task", ["request", "--id", "never-admitted"])
                execute.assert_not_called()
            with mock.patch.object(os, "execve") as execute:
                generation.launch(store, "task", ["--help"])
                self.assertEqual(execute.call_count, 1)
                _, argv, env = execute.call_args.args
                self.assertEqual(argv[1], str(target / "ext/fabric_task.py"))
                self.assertEqual(env["FABRIC_NATIVE_CODE_GENERATION"], target.name)
            self.assertEqual((prior / "ext/fabric_task.py").read_bytes(), pinned_source)
            self.assertEqual(generation.verify(store, prior.name)[0], prior)
            # Only these disposable sealed fixtures are made writable for cleanup.
            for directory, _, _ in os.walk(root, followlinks=False):
                os.chmod(directory, 0o700)


if __name__ == "__main__":
    unittest.main()
