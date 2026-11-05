"""Offline C3 facade capacity/retention contract; no installed runtime access."""
import os
from pathlib import Path
import shutil
import subprocess


def test_generation_local_controller_capacity_contract(tmp_path):
    node = shutil.which('node')
    assert node, 'Node is required for the C3 controller capacity contract'
    result = subprocess.run(
        [node, '--test', 'integrations/studio_direct_mcp/fabric-backend-capacity.test.mjs'],
        cwd=Path(__file__).resolve().parents[1],
        env={'PATH': os.environ.get('PATH', ''), 'HOME': str(tmp_path)},
        text=True, capture_output=True, timeout=60,
    )
    output = result.stdout + result.stderr
    assert result.returncode == 0, output[-12000:]
    assert '513 concurrent preflights' in output
    assert 'no oldID is evicted' in output
    assert 'fail 0' in output
