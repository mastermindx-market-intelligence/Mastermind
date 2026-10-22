"""Run the native and Web request-ceiling contracts in separate processes.

Only disposable fixtures are used; no provider, installed runtime or lease.
Fresh interpreters prevent candidate/baseline import contamination.
"""
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def _run(argv, *, timeout=60):
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(('POOL_', 'REMOTE_SUB_', 'FABRIC_'))}
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    result = subprocess.run(argv, cwd=ROOT, env=env, text=True,
                            capture_output=True, timeout=timeout)
    assert result.returncode == 0, (result.stdout + result.stderr)[-12000:]
    return result.stdout + result.stderr


def test_native_request_ceiling_and_original_profile():
    output = _run([sys.executable, '-m', 'unittest', 'discover', '-s',
        'ops/native_fabric/quota_continuity/tests', '-p', 'test_request_turn_budget.py'])
    assert 'Ran ' in output and 'Ran 0 tests' not in output
    assert 'OK' in output


def test_web_ceiling_and_original_facade():
    node = shutil.which('node')
    assert node, 'Node is required to qualify the Web-to-native request contract'
    output = _run([node, '--test', 'integrations/studio_direct_mcp/fabric-backend.test.mjs',
                   'integrations/studio_direct_mcp/fabric-turn-budget.test.mjs'])
    assert 'actual facade shell transport carries the ceiling' in output
    assert 'fail 0' in output


def test_existing_commission_deadlines_remain_binding():
    # Preserve the original inner deadlines. Hosted qualification must exercise
    # this affected transport contract, not silently omit local timing failures.
    output = _run([sys.executable, '-m', 'unittest', 'discover', '-s',
        'ops/native_fabric/quota_continuity/tests', '-p', 'test_commission_deadline.py'],
        timeout=240)
    assert 'Ran ' in output and 'Ran 0 tests' not in output
    assert 'OK' in output
