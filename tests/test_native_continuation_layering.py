"""Native evidence is usable without importing a transport or callback owner."""
import subprocess
import sys
from pathlib import Path


def test_native_evidence_loads_in_sealed_runtime_without_integrations():
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run([sys.executable, "-S", "-c",
        "import sys; import control_plane.native_continuation; "
        "assert not any(n == 'integrations' or n.startswith('integrations.') for n in sys.modules); "
        "assert 'mcp' not in sys.modules"], cwd=root, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
