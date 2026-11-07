"""Run the native and Web request-ceiling contracts in separate processes.

Only disposable fixtures are used; no provider, installed runtime or lease.
Fresh interpreters prevent candidate/baseline import contamination.
"""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def _run(argv, *, timeout=60, extra_env=None):
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(('POOL_', 'REMOTE_SUB_', 'FABRIC_'))}
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    env.update(extra_env or {})
    from scripts.native_unittest_diagnostics import NativeInvocation, bind_facts, run_native, COMMISSION_ARGS, COMMISSION_SELECTION
    invocation = None; facts = None
    if argv == [sys.executable, '-m', 'unittest', *COMMISSION_ARGS]:
        invocation = NativeInvocation('tests', COMMISSION_SELECTION)
        result, facts = run_native('tests', timeout_seconds=timeout, root=ROOT, cwd=ROOT,
                                  invocation=invocation, selection=COMMISSION_SELECTION, env=env)
    else:
        result = subprocess.run(argv, cwd=ROOT, env=env, text=True,
                                capture_output=True, timeout=timeout)
    if result.returncode != 0:
        error = AssertionError((result.stdout + result.stderr)[-12000:])
        if facts is not None:
            bind_facts(error, facts, invocation,
                'tests/test_fabric_request_turn_budget.py::test_existing_commission_deadlines_remain_binding')
        raise error
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
    # The strict no-follow readers intentionally reject a symlinked /tmp on
    # macOS and world-writable temporary ancestors on every platform. Keep the
    # fixture beneath the private home, not the source tree or shared /tmp.
    # Production checks stay intact.
    with tempfile.TemporaryDirectory(prefix='.fabric-deadline-ci-', dir=Path.home()) as temporary:
        output = _run([sys.executable, '-m', 'unittest', 'discover', '-s',
            'ops/native_fabric/quota_continuity/tests', '-p', 'test_commission_deadline.py'],
            timeout=240, extra_env={
                'NATIVE_ROLLOUT_TEST_ROOT': str(Path(temporary).resolve(strict=True))})
    assert 'Ran ' in output and 'Ran 0 tests' not in output
    assert 'OK' in output
