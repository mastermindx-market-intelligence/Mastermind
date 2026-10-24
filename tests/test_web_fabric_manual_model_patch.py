"""Run the integrated Web Fabric manual routing contract on the real facade.

The older source-only historical patch in this PR is retained as provenance,
not as a release recipe or current executable. No provider process is started.
"""
from pathlib import Path
import shutil
import subprocess
import pytest

SOURCE = Path(__file__).resolve().parents[1] / "integrations/studio_direct_mcp"


def test_web_fabric_manual_routing_integrated():
    if not shutil.which("node"):
        pytest.skip("Node unavailable")
    run = subprocess.run(["node", "--test", "fabric-backend.test.mjs"], cwd=SOURCE,
                         text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=75)
    assert run.returncode == 0, run.stdout[-14000:]
    # Node 20+ may emit either TAP ASCII or Unicode test summary prefixes.
    assert ("pass 46" in run.stdout and "fail 0" in run.stdout), run.stdout[-2500:]
