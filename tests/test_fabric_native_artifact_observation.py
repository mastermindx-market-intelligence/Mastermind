"""Qualify the staged runtime in isolation, including the prior admission cases."""
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
NATIVE = ROOT / 'ops/native_fabric/quota_continuity'


def test_staged_current_and_historical_artifact_observation(tmp_path):
    built = subprocess.run([sys.executable, str(NATIVE / 'rollout/build_review_stage.py'),
                            '--output', str(tmp_path)], capture_output=True, text=True, timeout=30)
    assert built.returncode == 0, built.stdout + built.stderr
    assert (tmp_path / 'native-code-stage/ext/run_observation_delivery.py').read_bytes() == (
        NATIVE / 'candidate/run_observation_delivery.py').read_bytes()
    env = {**os.environ, 'PYTHONPATH': str(tmp_path / 'native-code-stage/ext'),
           'PYTHONDONTWRITEBYTECODE': '1'}
    result = subprocess.run([
        sys.executable, '-m', 'pytest', '--import-mode=importlib', '-o', 'addopts=', '-q',
        str(ROOT / 'integrations/session_bridge/artifact_original_observation/test_artifact_observation.py'),
        str(NATIVE / 'rollout/qualify_artifact_observation.py'),
    ], cwd=ROOT, env=env, capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'passed' in result.stdout
    # The same staged consumer must retain both historical and v2 acquisition
    # semantics; the historical proposal directory is not the source subject.
    collected = subprocess.run([
        sys.executable,
        str(ROOT / 'integrations/session_bridge/original_validator_compat/test_collector_validator_compat.py'),
        str(tmp_path / 'native-code-stage/ext'),
    ], cwd=ROOT, env=env, capture_output=True, text=True, timeout=120)
    assert collected.returncode == 0, collected.stdout + collected.stderr
    assert 'Ran 0 tests' not in collected.stderr
