"""Opt-in native parser test. Never starts a provider turn or reads real auth."""
import json
import os
from pathlib import Path
import re
import subprocess

import pytest

from ops.codex_fabric.orchestrator_bundle import (
    configuration_overrides, inspect_bundle, install_bundle,
)

CODEX = os.environ.get("MASTERMIND_CODEX_NATIVE_PROBE")


@pytest.mark.skipif(not CODEX, reason="explicit native Codex binary required")
def test_native_override_ceiling_survives_trusted_project_config(tmp_path):
    root = tmp_path.resolve()
    home = root / "home"; home.mkdir()
    codex_home = home / "codex"; codex_home.mkdir()
    project = root / "project"; project.mkdir()
    subprocess.run(["git", "init", "-q", str(project)], check=True, timeout=10)
    (project / ".codex").mkdir()
    (project / ".codex/config.toml").write_text(
        '[agents]\nenabled = true\nmax_concurrent_threads_per_session = 3\n'
        'default_subagent_model = "gpt-5.6-terra"\n'
        'default_subagent_reasoning_effort = "medium"\n'
    )
    (codex_home / "config.toml").write_text(
        'cli_auth_credentials_store = "file"\n'
        'mcp_oauth_credentials_store = "file"\n'
        f'[projects.{json.dumps(str(project))}]\ntrust_level = "trusted"\n'
    )
    receipt = inspect_bundle(codex_home)
    install_bundle(codex_home, expected_bundle_digest=receipt["bundle_digest"])
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"),
           "HOME": str(home), "CODEX_HOME": str(codex_home)}

    def render(overrides):
        argv = [CODEX, "-p", "mastermind-orchestrators"]
        for item in overrides: argv.extend(["-c", item])
        argv.extend(["debug", "prompt-input", "Configuration-only diagnostic."])
        result = subprocess.run(argv, cwd=project, env=env,
                                capture_output=True, text=True, timeout=30)
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        texts = [piece.get("text", "") for msg in payload
                 for piece in msg.get("content", []) if isinstance(piece, dict)]
        multi = "\n".join(t for t in texts if "<multi_agent_role>" in t)
        slots = re.findall(r"There are (\d+) available concurrency slots", multi)
        return texts, slots

    _, uncontrolled_slots = render(())
    assert uncontrolled_slots == ["4"], "fixture no longer demonstrates project precedence"
    overrides = configuration_overrides(codex_home, expected_bundle_digest=receipt["bundle_digest"])
    texts, bounded_slots = render(overrides)
    assert bounded_slots == ["2"]
    assert any("principal, not the default worker" in text for text in texts)
    assert receipt["role_selection_proven"] is False
    assert receipt["child_enforcement_proven"] is False
    assert not (codex_home / "auth.json").exists()
