"""Explicit no-credential Codex Skill-catalog qualification for Operator-first role split.

The old protected Operator package and the separate new role candidate can be
seen together by an actual App Server. Visibility does NOT prove loading in an
Executive Job, account authentication, role selection or authority to delegate.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil

import pytest

from control_plane.codex_operator_adapter import _CLIENT_INFO
from control_plane.executive_agent_capabilities import ExecutionCapabilityRegistry
from scripts.ohf.laboratory import AppServerClient
from scripts.ohf.protocol import (
    enabled_skill_names, extra_roots_set_params, parse_skills_list_strict,
    skills_list_params,
)

REPO = Path(__file__).resolve().parents[1]
PINNED_REGISTRY = (
    REPO / "scripts/ohf/fixtures/"
    "executive_agent_capabilities_v4_mastermind_operator.json"
)
ROLE_ROOT = REPO / "skills/mastermind-fabric-orchestration"
ROLE_PINS = REPO / "patches/operator-first/source-pins.json"
ENV_KEY = "MASTERMIND_REAL_OPERATOR_ROLE_CATALOG_TEST"


@pytest.mark.skipif(
    os.environ.get(ENV_KEY) != "1",
    reason="real App Server read-only Skill-catalog proof requires explicit opt-in",
)
def test_immutable_operator_package_and_separate_role_are_discoverable(tmp_path, capsys):
    binary = shutil.which("codex")
    assert binary, "the explicit Codex binary is required for this opt-in test"
    registry = ExecutionCapabilityRegistry.load(PINNED_REGISTRY, source_root=REPO)
    assert registry.production_armed is False
    operator = registry.resolve("operator.appserver.readonly.mastermind-operator.v1")
    generation = registry.capability_packages["mastermind-operator.p1"]
    assert generation.source_commit == "12c2cb8993f78e81c6cb9e9a75a9829f9b194dab"
    assert len(operator.skill_grants) == 4
    assert not operator.write_capable

    # The new role core and its five references are NOT a new protected
    # Operator package generation. Recheck their own source candidate pins.
    pins = json.loads(ROLE_PINS.read_text(encoding="utf-8"))["role_source_sha256"]
    assert len(pins) == 6
    for relative, digest in pins.items():
        source = ROLE_ROOT / relative
        assert source.is_file() and not source.is_symlink()
        assert hashlib.sha256(source.read_bytes()).hexdigest() == digest

    root = tmp_path.resolve()
    home = root / "codex-home"
    workspace = root / "workspace"
    home.mkdir(mode=0o700)
    workspace.mkdir(mode=0o700)
    extra_role_root = root / "role-source-candidate" / "skills"
    candidate = extra_role_root / "mastermind-fabric-orchestration"
    shutil.copytree(ROLE_ROOT, candidate, symlinks=False)
    for relative, digest in pins.items():
        assert hashlib.sha256((candidate / relative).read_bytes()).hexdigest() == digest

    immutable_root = (REPO / "plugins/mastermind-operator/skills").resolve(strict=True)
    extra_role_root = extra_role_root.resolve(strict=True)
    args = [
        binary, "app-server", "--strict-config",
        "-c", 'sandbox_mode="read-only"',
        "-c", "skills.bundled.enabled=false",
        "-c", "features.plugins=false",
        "-c", "features.apps=false",
        "-c", "agents.enabled=false",
    ]
    # A fresh CODEX_HOME, not the user's authenticated account or MCP registry.
    environment = {
        "PATH": os.environ.get("PATH", "/opt/homebrew/bin:/usr/bin:/bin"),
        "HOME": str(home), "CODEX_HOME": str(home), "LC_ALL": "C",
    }
    client = AppServerClient(args, env=environment, cwd=workspace, start_new_session=True)
    expected = sorted(
        [f"mastermind-operator:{g.runtime_name}" for g in operator.skill_grants]
        + ["mastermind-fabric-orchestration"]
    )
    result: dict[str, object] = {
        "schema": "mastermind.real_operator_separate_role_catalog/v1",
        "package_generation": generation.package_generation_digest,
        "protected_source_commit": generation.source_commit,
        "production_armed": False, "model_turns": 0, "installed": False,
        "credential_home_isolated": True,
    }
    roots_cleared = False
    try:
        client.start()
        client.request(
            "initialize",
            {"clientInfo": _CLIENT_INFO, "capabilities": {"experimentalApi": True}},
            timeout=10,
        )
        client.notify("initialized", {})
        client.request("skills/extraRoots/set", extra_roots_set_params([]), timeout=10)
        baseline = parse_skills_list_strict(
            client.request("skills/list", skills_list_params(str(workspace)), timeout=10),
            expected_cwd=str(workspace),
        )
        assert enabled_skill_names(baseline) == []
        client.request(
            "skills/extraRoots/set",
            extra_roots_set_params([str(immutable_root), str(extra_role_root)]),
            timeout=10,
        )
        observed = parse_skills_list_strict(
            client.request("skills/list", skills_list_params(str(workspace)), timeout=10),
            expected_cwd=str(workspace),
        )
        names = sorted(enabled_skill_names(observed))
        assert names == expected
        assert len(observed) == 5
        for row in observed:
            assert row.get("enabled") is True
            name = str(row["name"])
            if name.startswith("mastermind-operator:"):
                short = name.removeprefix("mastermind-operator:")
                assert short in {grant.runtime_name for grant in operator.skill_grants}
                source = immutable_root / short / "SKILL.md"
            else:
                assert name == "mastermind-fabric-orchestration"
                source = extra_role_root / name / "SKILL.md"
            source = source.resolve(strict=True)
            assert str(row.get("path")) == str(source)
            assert source.is_file() and not source.is_symlink()
        result["provider_names"] = names
        result["path_precise"] = True
        client.request("skills/extraRoots/set", extra_roots_set_params([]), timeout=10)
        cleared = parse_skills_list_strict(
            client.request("skills/list", skills_list_params(str(workspace)), timeout=10),
            expected_cwd=str(workspace),
        )
        assert enabled_skill_names(cleared) == []
        roots_cleared = True
    finally:
        if client.alive() and not roots_cleared:
            try:
                client.request("skills/extraRoots/set", extra_roots_set_params([]), timeout=3)
            except Exception:
                pass  # A failed test remains failed; close and clean disposable home.
        client.close()
        assert not client.alive()
    assert roots_cleared
    result["after_clear"] = []
    result["process_closed"] = True
    with capsys.disabled():
        print(json.dumps(result, sort_keys=True))
