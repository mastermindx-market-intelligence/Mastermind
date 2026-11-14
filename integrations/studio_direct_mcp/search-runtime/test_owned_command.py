import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest

spec=importlib.util.spec_from_file_location('owned_command',Path(__file__).with_name('owned_command.py'))
owner=importlib.util.module_from_spec(spec);spec.loader.exec_module(owner)

class OwnedCommandTests(unittest.TestCase):
    def test_timeout_terminates_child_grandchild_and_preserves_sentinel(self):
        with tempfile.TemporaryDirectory(prefix='issue1027-owner-') as folder:
            root=Path(folder)
            leaf=root/'leaf.py'
            leaf.write_text("import os,signal,time\nfrom pathlib import Path\nsignal.signal(signal.SIGTERM,signal.SIG_IGN)\nPath(__file__).with_suffix('.pid').write_text(str(os.getpid()))\nwhile True:time.sleep(.05)\n")
            child=root/'child.py'
            child.write_text("import os,signal,subprocess,sys,time\nfrom pathlib import Path\nsignal.signal(signal.SIGTERM,signal.SIG_IGN)\np=subprocess.Popen([sys.executable,str(Path(__file__).with_name('leaf.py'))])\nPath(__file__).with_suffix('.pid').write_text(str(os.getpid()))\nwhile True:time.sleep(.05)\n")
            parent=root/'parent.py'
            parent.write_text("import os,signal,subprocess,sys,time\nfrom pathlib import Path\nsignal.signal(signal.SIGTERM,signal.SIG_IGN)\np=subprocess.Popen([sys.executable,str(Path(__file__).with_name('child.py'))])\nPath(__file__).with_suffix('.pid').write_text(str(os.getpid()))\nwhile True:time.sleep(.05)\n")
            sentinel=subprocess.Popen([sys.executable,'-c','import time;time.sleep(20)'],start_new_session=True)
            began=time.monotonic()
            try:
                with self.assertRaises(subprocess.TimeoutExpired):
                    owner.run([sys.executable,str(parent)],root,root/'run.log',timeout=.5,grace=1)
                self.assertLess(time.monotonic()-began,3)
                pids=[int((root/(n+'.pid')).read_text()) for n in ('parent','child','leaf')]
                for pid in pids:
                    with self.assertRaises(ProcessLookupError):os.kill(pid,0)
                self.assertIsNone(sentinel.poll())
                print(json.dumps({'ownedPids':len(pids),'residualOwned':0,'sentinelUnaffected':True,'timeoutNonzero':True}))
            finally:
                sentinel.terminate();sentinel.wait(timeout=2)
                # Failure recovery targets only the group this fixture created.
                receipt=root/'parent.pid'
                if receipt.exists():
                    group=int(receipt.read_text())
                    try:os.killpg(group,signal.SIGKILL)
                    except ProcessLookupError:pass

    def test_success_does_not_hide_lingering_child(self):
        with tempfile.TemporaryDirectory(prefix='issue1027-linger-') as folder:
            root=Path(folder)
            leaf="import os,time;from pathlib import Path;Path('child.pid').write_text(str(os.getpid()));time.sleep(20)"
            parent="import subprocess,sys,time;subprocess.Popen([sys.executable,'-c',"+repr(leaf)+"]);time.sleep(.15)"
            with self.assertRaisesRegex(RuntimeError,'outlived successful'):
                owner.run([sys.executable,'-c',parent],root,root/'out.log',timeout=1,grace=.5)
            pid=int((root/'child.pid').read_text())
            with self.assertRaises(ProcessLookupError):os.kill(pid,0)

    def test_success_and_failure_status(self):
        with tempfile.TemporaryDirectory(prefix='issue1027-status-') as folder:
            root=Path(folder)
            owner.run([sys.executable,'-c','print("ok")'],root,root/'success.log',timeout=1,grace=.5)
            self.assertEqual((root/'success.log').read_text().strip(),'ok')
            with self.assertRaises(subprocess.CalledProcessError) as context:
                owner.run([sys.executable,'-c','raise SystemExit(7)'],root,root/'failure.log',timeout=1,grace=.5)
            self.assertEqual(context.exception.returncode,7)

if __name__=='__main__':unittest.main()
