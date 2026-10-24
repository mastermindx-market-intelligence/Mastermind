"""Opt-in real Codex catalog proof for the source-candidate Workforce package.

Tests ONLY temporary credentials-free App Server Skills discovery, not a model
turn, provider login, Skill grant, global install, or Executive Job admission.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

from control_plane.codex_operator_adapter import _CLIENT_INFO
from ops.fabric_launch.install import source_files
from ops.fabric_launch.plugin import assemble
from scripts.ohf.laboratory import AppServerClient
from scripts.ohf.protocol import (
    enabled_skill_names, extra_roots_set_params,
    parse_skills_list_strict, skills_list_params,
)

REPO = Path(__file__).resolve().parent.parent
PROFILE = "MASTERMIND_REAL_WORKFORCE_SKILLS_CATALOG_TEST"
SKILLS = ("mastermind-craft", "mastermind-worker-bootstrap", "mastermind-fabric-orchestration")


@pytest.mark.skipif(
    os.environ.get(PROFILE) != "1",
    reason="credential-free real Workforce Skills catalog must be explicitly enabled",
)
def test_source_derived_workforce_skills_discovered_by_real_app_server(tmp_path, capsys):
    binary = shutil.which("codex")
    assert binary is not None, "explicitly requested Codex binary unavailable"
    source_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=REPO, check=True,
        capture_output=True, text=True, timeout=5,
    ).stdout.strip()
    files = source_files(REPO, source_sha, include_orchestration_roles=True)
    artifact = assemble(files, source_sha, docs=False)
    assert ".mcp.json" not in artifact
    build = json.loads(artifact["BUILD.json"])
    assert build["source_state"] == "SOURCE_CANDIDATE"
    assert build["execution_authority"] is False
    assert build["native_skill_attested"] is False

    root = tmp_path.resolve()
    package = root / "mastermind-workforce"
    workspace = root / "workspace"
    home = root / "codex-home"
    workspace.mkdir(mode=0o700)
    home.mkdir(mode=0o700)
    for relative, data in artifact.items():
        destination = package / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
        assert hashlib.sha256(destination.read_bytes()).digest() == hashlib.sha256(data).digest()
    skills_root = (package / "skills").resolve(strict=True)
    args = [
        binary, "app-server", "--strict-config",
        "-c", 'sandbox_mode="read-only"',
        "-c", "skills.bundled.enabled=false",
        "-c", "features.plugins=false",
        "-c", "features.apps=false",
        "-c", "agents.enabled=false",
    ]
    # Deliberately do not inherit any ambient provider credential variables.
    environment = {
        "PATH": os.environ.get("PATH", "/opt/homebrew/bin:/usr/bin:/bin"),
        "HOME": str(home), "CODEX_HOME": str(home), "LC_ALL": "C",
    }
    client = AppServerClient(args, env=environment, cwd=workspace, start_new_session=True)
    successful = False
    names: tuple[str, ...] = ()
    try:
        client.start()
        response = client.request(
            "initialize", {
                "clientInfo": _CLIENT_INFO,
                "capabilities": {"experimentalApi": True},
            }, timeout=10,
        )
        client.notify("initialized", {})
        client.request("skills/extraRoots/set", extra_roots_set_params([]), timeout=10)
        baseline = parse_skills_list_strict(
            client.request("skills/list", skills_list_params(str(workspace)), timeout=10),
            expected_cwd=str(workspace),
        )
        assert enabled_skill_names(baseline) == []
        client.request(
            "skills/extraRoots/set", extra_roots_set_params([str(skills_root)]),
            timeout=10,
        )
        rows = parse_skills_list_strict(
            client.request("skills/list", skills_list_params(str(workspace)), timeout=10),
            expected_cwd=str(workspace),
        )
        enabled = [row for row in rows if row.get("enabled") is True]
        names = tuple(sorted(enabled_skill_names(rows)))
        assert names == tuple(sorted(f"mastermind-workforce:{name}" for name in SKILLS))
        for row in enabled:
            short_name = str(row["name"]).removeprefix("mastermind-workforce:")
            assert short_name in SKILLS
            expected = (skills_root / short_name / "SKILL.md").resolve(strict=True)
            assert str(row.get("path")) == str(expected)
            assert expected.is_file() and not expected.is_symlink()
            assert expected.read_bytes() == artifact[f"skills/{short_name}/SKILL.md"]
        client.request("skills/extraRoots/set", extra_roots_set_params([]), timeout=10)
        cleared = parse_skills_list_strict(
            client.request("skills/list", skills_list_params(str(workspace)), timeout=10),
            expected_cwd=str(workspace),
        )
        assert enabled_skill_names(cleared) == []
        assert str(response.get("userAgent") or "")
        successful = True
    finally:
        client.close()
        assert not client.alive()
    assert successful
    with capsys.disabled():
        print(json.dumps({
            "schema": "mastermind.real_workforce_skill_catalog/v1",
            "source_sha": source_sha,
            "candidate_only": True, "installed": False,
            "provider_names": names, "credential_home_isolated": True,
            "model_turns": 0, "clear_to_empty": True, "process_closed": True,
        }, sort_keys=True))
