"""Execute generated remote code against inert local fixtures, without SSH."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class PortableOriginalReaderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # DirectoryChain deliberately rejects world-writable /tmp ancestry.
        cls.temp = tempfile.TemporaryDirectory(prefix="portable-reader-proof-", dir=Path.home())
        cls.base = Path(cls.temp.name)
        build = Path(__file__).resolve().with_name("build_review_stage.py")
        result = subprocess.run([sys.executable, str(build), "--output", str(cls.base)],
                                capture_output=True, text=True, timeout=30)
        if result.returncode:
            raise AssertionError(result.stdout + result.stderr)
        cls.ext = cls.base/"native-code-stage/ext"

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def setUp(self):
        self.fixture = tempfile.TemporaryDirectory(dir=self.base)
        self.home = Path(self.fixture.name)

    def tearDown(self):
        self.fixture.cleanup()

    def child(self, program):
        request = {"schema":"mastermind.original_delivery_read.v1", "run_id":"inert-fixture",
            "root":"inert-root", "parent":"inert-root", "host":"inert-host",
            "contract":{"schema":"mastermind.fabric_artifact_production.v1", "run_id":"inert-fixture",
                "root":"inert-root", "parent":"inert-root", "names":["result.patch"],
                "body_sha256":"1"*64, "support_digest":"2"*64}}
        prefix = ("import sys, os, inspect\nfrom pathlib import Path\n"
            f"sys.path.insert(0,{str(self.ext)!r})\n"
            "import original_delivery_collector as collector\nimport artifact_delivery as delivery\n"
            f"request={request!r}\nhome=Path({str(self.home)!r})\n"
            "code=collector.code_for_request(request)\nnamespace={}\n"
            "exec(compile(code[:code.rfind('\\ntry:\\n raw=')], 'generated-reader', 'exec'), namespace)\n"
            "Chain=namespace['DirectoryChain']\n")
        result = subprocess.run([sys.executable, "-B", "-c", prefix+program],
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)

    def test_generated_helper_has_no_native_mapping_dependency(self):
        self.child("assert 'owner_path' not in namespace and 'HERE' not in namespace\n"
                   "with Chain(home) as chain:\n    chain.verify()\n")

    def test_relative_and_dotdot_paths_remain_refused(self):
        self.child("for path in (Path('relative'), Path('/valid/../invalid')):\n"
                   "    try:\n        Chain(path)\n"
                   "    except ValueError as error:\n        assert str(error)=='directory_path_invalid'\n"
                   "    else:\n        raise AssertionError('accepted invalid path')\n")

    def test_symlink_directory_remains_refused(self):
        self.child("(home/'real').mkdir(mode=0o700)\n(home/'alias').symlink_to(home/'real')\n"
                   "try:\n    Chain(home/'alias')\nexcept OSError:\n    pass\n"
                   "else:\n    raise AssertionError('followed symlink')\n")

    def test_group_writable_directory_remains_refused(self):
        self.child("path=home/'writable'\npath.mkdir(mode=0o700)\npath.chmod(0o777)\n"
                   "try:\n    Chain(path)\nexcept ValueError as error:\n"
                   "    assert str(error)=='directory_owner_or_mode'\n"
                   "else:\n    raise AssertionError('accepted writable directory')\n")

    def test_replaced_directory_edge_remains_refused(self):
        self.child("path=home/'held'\npath.mkdir(mode=0o700)\n"
                   "with Chain(path) as chain:\n    path.rename(home/'old')\n    path.mkdir(mode=0o700)\n"
                   "    try:\n        chain.verify()\n    except ValueError as error:\n"
                   "        assert str(error)=='directory_chain_changed'\n"
                   "    else:\n        raise AssertionError('accepted replaced edge')\n")

    def test_generated_original_reader_returns_pending_for_inert_home(self):
        self.child("(home/'lanes'/'ext').mkdir(parents=True,mode=0o700)\n"
                   "result=namespace['remote_read'](request,home=home)\n"
                   "assert result['state']=='PENDING' and result['files']=={} and result['artifacts']==[]\n")

    def test_all_custody_checks_are_preserved_verbatim(self):
        self.child("source=inspect.getsource(delivery.DirectoryChain)\n"
                   "expected=source.replace('            path = owner_path(path, HERE)',"
                   "'            path = Path(path)',1)\n"
                   "assert delivery.remote_directory_chain_source()==expected\n")


if __name__ == "__main__":
    unittest.main(verbosity=2)
