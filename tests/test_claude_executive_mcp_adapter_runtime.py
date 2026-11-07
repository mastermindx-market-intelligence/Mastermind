"""Executable localhost transport proof with disposable servers and no real OAuth."""
from pathlib import Path
import re
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def test_claude_adapter_executable_role_boundary():
    node = shutil.which("node")
    assert node, "Node is required for the executable Claude adapter contract"
    result = subprocess.run(
        [node, "--test", "--test-reporter=tap", "tests/claude_executive_mcp_adapter.test.mjs"],
        cwd=ROOT, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    total = re.search(r"^# tests (\d+)$", result.stdout, re.MULTILINE)
    passed = re.search(r"^# pass (\d+)$", result.stdout, re.MULTILINE)
    assert total and passed and int(total.group(1)) >= 28
    assert passed.group(1) == total.group(1)
    assert "# fail 0" in result.stdout and "# skipped 0" in result.stdout
