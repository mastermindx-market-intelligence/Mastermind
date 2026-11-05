"""New adapter is shipped in the exact remote closure; preceding code survives."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest


class RemoteBindingPublication(unittest.TestCase):
    def test_exact_closure_import_and_prior_generation_reuse(self):
        root = Path(__file__).resolve().parents[1]
        sys.path.insert(0, str(root / "source"))
        spec = importlib.util.spec_from_file_location("support_binding_fixture", root / "candidate/support_bundle.py")
        support = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(support)
        self.assertIn("native_runtime_bindings.py", support.SOURCE_FILES)
        self.assertEqual(len(support.SOURCE_FILES), 37)
        self.assertEqual(support.SOURCE_FILES - {"commission_deadline.py"},
                         support.PRE_COMMISSION_DEADLINE_SOURCE_FILES)
        self.assertEqual(len(support.PRE_COMMISSION_DEADLINE_SOURCE_FILES), 36)
        self.assertEqual(support.PRE_COMMISSION_DEADLINE_SOURCE_FILES - {"native_runtime_bindings.py"},
                         support.PRE_NATIVE_BINDING_SOURCE_FILES)
        self.assertEqual(len(support.PRE_NATIVE_BINDING_SOURCE_FILES), 35)
        shell = (root / "candidate/remote_sub.sh").read_text()
        names = set(re.search(r"SUPPORT_FILES=\(\n(.*?)\n\)", shell, re.S).group(1).split())
        self.assertEqual(names, support.SOURCE_FILES)
        with tempfile.TemporaryDirectory(prefix="native-remote-binding-") as directory:
            base = Path(directory).resolve()
            source = base / "source/ext"
            stable = base / "remote/ext"
            source.mkdir(parents=True)
            stable.mkdir(parents=True)
            (stable / "active").mkdir()
            (stable.parent / "support-releases").mkdir()
            policy = json.dumps({"routing": {}, "pools": {"grok": {"windows": {"weekly": {}}}}}) + "\n"
            for kit in (source.parent, stable.parent):
                (kit / "orch/fabric").mkdir(parents=True)
                (kit / "orch/fabric/pools.yaml").write_text(policy)
            manifest = {}
            for name in support.SOURCE_FILES:
                if name == "pools.yaml":
                    raw = policy.encode()
                elif name == "native_runtime_bindings.py":
                    raw = (root / 'candidate' / name).read_bytes()
                else:
                    raw = b"# Existing dependency is not executed by this fixture.\n"
                (source / name).write_bytes(raw)
                manifest[name] = hashlib.sha256(raw).hexdigest()
            published = support.publish(source, stable, manifest)
            program = (f"import sys;from pathlib import Path;sys.path.insert(0,{str(published)!r});"
                       "from native_runtime_bindings import owner_path;"
                       f"here=Path({str(published)!r});"
                       "assert owner_path(here/'hosts.json',here)==here/'hosts.json'")
            result = subprocess.run([sys.executable, "-B", "-c", program], text=True,
                                    capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            previous = {k: v for k, v in manifest.items() if k in support.PRE_NATIVE_BINDING_SOURCE_FILES}
            old_release = support.publish(source, stable, previous)
            self.assertNotEqual(old_release, published)
            self.assertEqual(support.publish(source, stable, previous), old_release)
            # Cleanup only our owned sealed test artifacts; never follow the
            # stable-state links into another runtime owner.
            for walked, directories, files in os.walk(base, followlinks=False):
                os.chmod(walked, 0o700)


if __name__ == "__main__":
    unittest.main(verbosity=2)
