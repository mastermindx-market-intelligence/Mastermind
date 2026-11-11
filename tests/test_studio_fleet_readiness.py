"""Run the Studio fleet producer's real unittest suite under protected pytest CI."""
from pathlib import Path
import subprocess
import sys


def test_studio_fleet_status_readiness_contract():
    studio = Path(__file__).resolve().parents[1] / 'integrations' / 'studio_direct_mcp'
    result = subprocess.run(
        [sys.executable, '-m', 'unittest', '-q',
         'studio_direct_control_test', 'test_fleet_readiness_regression'],
        cwd=studio, capture_output=True, text=True, timeout=30, check=False,
    )
    assert result.returncode == 0, (
        'Studio readiness unit tests failed: '
        + result.stdout[-2000:] + result.stderr[-2000:]
    )
