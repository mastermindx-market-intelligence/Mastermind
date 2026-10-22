"""Repository CI regression entrypoint for the versioned native Grok migration."""
from __future__ import annotations
from pathlib import Path
import subprocess
import sys
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]


class NativeFabricGrok47Qualification(unittest.TestCase):
    def test_grok47_selector_and_worker_contracts(self):
        script_dir = ROOT / 'ops/native_fabric/grok47'
        completed = subprocess.run([
            sys.executable, '-m', 'unittest', 'discover', '-s', str(script_dir),
            '-p', 'test_*.py', '-v',
        ], cwd=ROOT, timeout=40, capture_output=True, text=True)
        self.assertEqual(completed.returncode, 0,
                         (completed.stdout + '\n' + completed.stderr)[-5000:])
        match = re.search(r'Ran ([0-9]+) tests', completed.stderr)
        self.assertIsNotNone(match, completed.stderr[-1000:])
        self.assertGreaterEqual(int(match.group(1)), 11)


if __name__=='__main__':
    unittest.main()
