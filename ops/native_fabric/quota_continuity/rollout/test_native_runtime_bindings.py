"""Real-reader alias proof using only staged code and temporary dummy state."""
import os
from pathlib import Path
import subprocess
import sys
import unittest

import test_native_generation as fixtures


class NativeRuntimeBindingTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.NativeGenerationTests()
        self.fixture.setUp()
        f = self.fixture
        staged = Path(__file__).resolve().parents[1] / "source"
        overlays = Path(__file__).resolve().parents[1] / 'candidate'
        source = f.make_source("V1")
        ext = source / "ext"
        (ext / "native_runtime_bindings.py").write_bytes(
            (overlays / "native_runtime_bindings.py").read_bytes())
        (ext / "artifact_reader.py").write_bytes((staged / "artifact_reader.py").read_bytes())
        for name in ("glm_host_account_source.py", "artifact_delivery.py",
                     "native_prestart_reconcile.py", "native_preexec_reconcile.py"):
            (ext / name).write_bytes((overlays / name).read_bytes())
        (f.ext / "hosts.json").write_text('{"fixture": true}\n')
        (f.ext / "state/remote_sub").mkdir()
        (f.ext / "state/remote_sub/proof.log").write_text("dummy evidence\n")
        self.release = f.publish("V1")
        self.here = self.release / "ext"

    def tearDown(self):
        self.fixture.tearDown()

    def child(self, program):
        prefix = ("import sys\nfrom pathlib import Path\n"
                  f"sys.path.insert(0, {str(self.here)!r})\nHERE=Path({str(self.here)!r})\n"
                  "from native_runtime_bindings import owner_path\n")
        return subprocess.run([sys.executable, "-B", "-c", prefix + program],
                              capture_output=True, text=True, timeout=10)

    def test_real_account_reader_accepts_declared_owner_and_rejects_owner_leaf_symlink(self):
        result = self.child("from glm_host_account_source import owned_bytes\n"
            "assert owned_bytes(HERE/'hosts.json') == b'{\"fixture\": true}\\n'\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        path = self.fixture.ext / "hosts.json"
        target = self.fixture.ext / "other-hosts.json"
        target.write_text("must not be read")
        path.unlink()
        path.symlink_to(target)
        result = self.child("from glm_host_account_source import owned_bytes\n"
            "try:\n    owned_bytes(HERE/'hosts.json')\n"
            "except OSError:\n    pass\nelse:\n    raise AssertionError('followed original owner leaf symlink')\n")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_alias_translation_keeps_state_internal_symlinks_visible(self):
        outside = self.fixture.ext / "outside"
        outside.mkdir()
        (outside / "entry").write_text("must not be read")
        link = self.fixture.ext / "state/untrusted"
        link.symlink_to(outside, target_is_directory=True)
        result = self.child("from glm_host_account_source import owned_bytes\n"
            f"assert owner_path(HERE/'state/untrusted/entry', HERE) == Path({str(link/'entry')!r})\n"
            "try:\n    owned_bytes(HERE/'state/untrusted/entry')\n"
            "except OSError:\n    pass\nelse:\n    raise AssertionError('resolved hidden state-internal symlink')\n")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_tampered_declared_alias_fails_closed(self):
        self.here.chmod(0o755)
        alias = self.here / "hosts.json"
        alias.unlink()
        alias.symlink_to(self.fixture.ext / "other-hosts.json")
        self.here.chmod(0o555)
        result = self.child("try:\n    owner_path(HERE/'hosts.json', HERE)\n"
            "except ValueError as exc:\n    assert 'visible alias changed' in str(exc)\n"
            "else:\n    raise AssertionError('accepted changed alias')\n")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_historical_reader_leaf_helpers_keep_custody_without_running_recovery(self):
        # Only read dummy local fixture bytes. No status/reconcile functions,
        # remote probes, held run IDs or historical evidence are invoked.
        result = self.child("import native_prestart_reconcile as start\n"
            "import native_preexec_reconcile as preexec\n"
            "assert start._regular(HERE/'hosts.json', 4096, field='fixture') == b'{\"fixture\": true}\\n'\n"
            "start._safe_owner(HERE/'hosts.json', 'fixture')\n"
            "assert preexec.regular(HERE/'hosts.json', 4096) == b'{\"fixture\": true}\\n'\n")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_real_artifact_directory_chain_on_trusted_fixture_ancestry(self):
        # The incumbent DirectoryChain correctly refuses world-writable /tmp
        # and /workspace ancestors. For this particular proof, the caller can
        # supply an owned 0700 fixture parent under a trusted home directory.
        baseline = self.child("import artifact_delivery as delivery\n"
            f"delivery.local_file(Path({str(self.fixture.ext/'hosts.json')!r}))\n")
        if baseline.returncode and "directory_owner_or_mode" in baseline.stderr:
            self.skipTest("set NATIVE_ROLLOUT_TEST_ROOT to a trusted owned fixture parent for DirectoryChain proof")
        self.assertEqual(baseline.returncode, 0, baseline.stderr)
        result = self.child("import artifact_delivery as delivery\n"
            "assert delivery.local_file(HERE/'hosts.json') == b'{\"fixture\": true}\\n'\n"
            "assert delivery.local_file(HERE/'state/remote_sub/proof.log') == b'dummy evidence\\n'\n"
            "with delivery.DirectoryChain(HERE/'state/remote_sub') as chain:\n    chain.verify()\n")
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
