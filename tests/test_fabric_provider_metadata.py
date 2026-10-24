"""Exercise the real provider wrapper with synthetic private metadata in CI."""
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def test_permission_history_and_closed_metadata_wrapper():
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(('POOL_', 'REMOTE_SUB_', 'FABRIC_'))}
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    result = subprocess.run([sys.executable, '-m', 'unittest', 'discover', '-s',
        'ops/native_fabric/quota_continuity/tests', '-p', 'test_permission_history.py'],
        cwd=ROOT, env=env, text=True, capture_output=True, timeout=30)
    output = result.stdout + result.stderr
    assert result.returncode == 0, output[-12000:]
    assert 'Ran ' in output and 'Ran 0 tests' not in output and 'OK' in output
