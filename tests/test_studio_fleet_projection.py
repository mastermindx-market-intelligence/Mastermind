"""Qualify the real Studio fleet-status JS contract under protected pytest CI."""
from pathlib import Path
import subprocess


def test_studio_fleet_status_projection():
    root = Path(__file__).resolve().parents[1]
    source = root / "integrations/studio_direct_mcp/fleet-status.test.mjs"
    result = subprocess.run(
        ["node", "--test", str(source)],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, (
        f"Studio fleet projection suite returned {result.returncode}: "
        + (result.stdout + result.stderr)[-2500:]
    )
