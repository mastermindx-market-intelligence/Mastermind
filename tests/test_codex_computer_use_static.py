"""Hermetic Codex Computer Use MCP adapter gate.

Runs only pure policy/facet tests. Never starts SkyComputerUseClient, launches
desktop applications, touches permissions, or connects to an external host.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "ops" / "codex_computer_use"


def test_computer_use_mcp_syntax_and_pure_contracts() -> None:
    node = shutil.which("node")
    assert node, "GitHub Actions sets up Node 22 for the mandatory repository gate"
    modules = sorted(PACKAGE.glob("*.mjs"))
    assert modules, "Codex Computer Use adapter sources are missing"

    for module in modules:
        check = subprocess.run(
            [node, "--check", str(module)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        assert check.returncode == 0, (
            f"JavaScript syntax failed: {module.name}\n"
            f"{(check.stderr + check.stdout)[-2400:]}"
        )

    tests = sorted(PACKAGE.glob("*.test.mjs"))
    assert len(tests) >= 3, "Policy, facet, and output containment tests required"
    result = subprocess.run(
        [node, "--test", *(str(test) for test in tests)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=35,
        check=False,
    )
    assert result.returncode == 0, (
        "Codex Computer Use pure-contract tests failed:\n"
        f"{(result.stdout + result.stderr)[-5500:]}"
    )
