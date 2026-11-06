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
        cls.temp = tempfile.TemporaryDirectory(prefix="portable-reader-proof-",
            dir=Path(os.environ.get("NATIVE_ROLLOUT_TEST_ROOT", Path.home())))
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
        run_id = "inert-" + self.home.name
        request = {"schema":"mastermind.original_delivery_read.v1", "run_id":run_id,
            "root":"inert-root", "parent":"inert-root", "host":"inert-host",
            "contract":{"schema":"mastermind.fabric_artifact_production.v1", "run_id":run_id,
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
        # Independent original class from pinned pre-overlay source 28af21eb.
        self.child("import hashlib\n"
                   "assert hashlib.sha256(delivery.remote_directory_chain_source().encode()).hexdigest()=="
                   "'7f25c408328b9879d3422c046dcda1627ae41a0c259dc233d2bf47e088688ba0'\n")

    def test_unknown_adapter_shapes_refuse_before_export(self):
        self.child("from unittest.mock import patch\n"
            "source=inspect.getsource(delivery.DirectoryChain)\n"
            "line='            path = owner_path(path, HERE)'\n"
            "for changed in (source.replace(line,''),source.replace(line,line+'\\n'+line),source.replace(line,line.replace('path =','path  ='))):\n"
            "    with patch('inspect.getsource',return_value=changed):\n"
            "        try:\n            delivery.remote_directory_chain_source()\n"
            "        except ValueError as error:\n            assert str(error)=='remote_directory_chain_source_changed'\n"
            "        else:\n            raise AssertionError('exported unknown shape')\n")

    @unittest.skipUnless(sys.platform.startswith("linux"), "remote artifact carrier requires a real /tmp directory, not the macOS symlink")
    def test_generated_original_reader_reads_complete_inert_result(self):
        self.child("ext=home/'lanes'/'ext'\next.mkdir(parents=True,mode=0o700)\n"
            "lanes=ext/'lanes'\nlanes.mkdir(mode=0o700)\nrid=request['run_id']\n"
            "for path,raw in [(ext/('lanes_'+rid+'.rc'),b'0\\n'),"
            "(ext/('lanes_'+rid+'.stdout'),b'inert result\\n'),(lanes/(rid+'.process.jsonl'),b'{}\\n')]:\n"
            "    path.write_bytes(raw)\n    path.chmod(0o600)\n"
            "scope={k:request[k] for k in ('root','parent','run_id')}\n"
            "directory=Path('/tmp/fabric-'+namespace['sha'](namespace['canonical'](scope))[:40])\n"
            "directory.mkdir(mode=0o700)\nartifact=directory/'result.patch'\n"
            "try:\n    artifact.write_bytes(b'inert patch\\n')\n    artifact.chmod(0o600)\n"
            "    result=namespace['remote_read'](request,home=home)\n"
            "    assert result['state']=='READ' and set(result['files'])=={'rc','process','stdout'}\n"
            "    assert len(result['artifacts'])==1 and result['artifacts'][0]['status']=='RETRIEVED'\n"
            "finally:\n    artifact.unlink()\n    directory.rmdir()\n")


if __name__ == "__main__":
    unittest.main(verbosity=2)
