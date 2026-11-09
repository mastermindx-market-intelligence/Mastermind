"""Qualify the actual provider-free Node Attempt consumer in hosted Python CI."""
from pathlib import Path
import os
import shutil
import subprocess


def test_node_dsh_attempt_overlay_closure():
    node = shutil.which("node")
    assert node, "Node is needed to qualify the DSH Attempt consumer"
    source = Path(__file__).resolve().parents[1]
    suite = source / "tests/harness_convergence/test_dsh_attempt_overlay.mjs"
    result = subprocess.run(
        [node, "--test", "--test-reporter=tap", str(suite)],
        cwd=source,
        env={"PATH": os.environ.get("PATH", "/usr/bin:/bin")},
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, (result.stdout[-3500:], result.stderr[-3500:])
    assert "# fail 0" in result.stdout
    assert "# pass 4" in result.stdout
