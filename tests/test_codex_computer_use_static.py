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


def test_rich_codex_skill_profile_does_not_ambiently_grant_computer_use() -> None:
    """A merged Computer Use adapter is not a host/tool/app/session entitlement.

    Real nonplanner Worker/Operator selection must still present the exact
    owner-qualified Computer Use MCP, current physical macOS TCC state and
    per-app owner policy. Neither file presence nor a visible Skill grants it.
    """
    import json

    from control_plane.executive_agent_capabilities import ExecutionCapabilityRegistry

    config = ROOT / "scripts/ohf/fixtures/"
    registry = ExecutionCapabilityRegistry.load(
        config / "executive_agent_capabilities_v4_rich_write_operator.json",
        source_root=ROOT,
    )
    profile = registry.resolve("operator.appserver.write.mastermind-operator.v1")
    assert not registry.production_armed
    assert profile.execution_surface == "codex-app-server"
    assert profile.write_capable
    assert profile.native_helper_policy.value == "DISABLED"
    assert not profile.mcp_servers
    assert not profile.resource_grants
    assert not profile.plugins

    # The checked-in JSON is an example policy, not installed host consent.
    example = json.loads((PACKAGE / "policy.example.json").read_text())
    assert example["schema"] == "mastermind.codex_computer_use_policy.v1"
    assert len(example["apps"]) == 1
    assert example["apps"][0]["bundle_id"] == "com.apple.calculator"
    assert example["apps"][0]["write"] is False
    default_registry = json.loads(
        (ROOT / "config/executive_agent_capabilities.json").read_text()
    )
    assert default_registry["production_armed"] is False
