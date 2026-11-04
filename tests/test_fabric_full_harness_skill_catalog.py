"""Opt-in real Codex combined seven-Skill catalog on a disposable user home.

Three existing source owners: protected OperatorPackage, Operator-first policy
installer and WorkerCraft/Bootstrap plugin. This never installs a live account,
changes a real provider preference or starts a model turn / Executive Attempt.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import uuid

import pytest

from control_plane.codex_operator_adapter import _CLIENT_INFO
from control_plane.executive_agent_capabilities import ExecutionCapabilityRegistry
from ops.fabric_launch.install import source_files
from ops.fabric_launch.plugin import assemble
from scripts.ohf.laboratory import AppServerClient
from scripts.ohf.protocol import (
    enabled_skill_names, extra_roots_set_params,
    parse_skills_list_strict, skills_list_params,
)

REPO = Path(__file__).resolve().parent.parent
OPERATOR_FIXTURE = (
    REPO / "scripts/ohf/fixtures/"
    "executive_agent_capabilities_v4_mastermind_operator.json"
)
ROLE_ROOT = REPO / "skills/mastermind-fabric-orchestration"


@pytest.mark.skipif(
    os.environ.get("MASTERMIND_REAL_FULL_HARNESS_SKILLS_TEST") != "1",
    reason="real combined Codex Skill catalog requires explicit opt-in",
)
def test_signed_operator_plus_new_role_plus_workforce_catalog(tmp_path, capsys):
    executable = shutil.which("codex")
    assert executable is not None
    source_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=REPO,
        check=True, capture_output=True, text=True, timeout=5,
    ).stdout.strip()
    registry = ExecutionCapabilityRegistry.load(OPERATOR_FIXTURE, source_root=REPO)
    assert not registry.production_armed
    old = registry.resolve("operator.appserver.readonly.mastermind-operator.v1")
    generation = registry.capability_packages["mastermind-operator.p1"]
    assert len(old.skill_grants) == 4

    root = tmp_path.resolve()
    original = REPO / "tests/fixtures/operator_first/provider_orchestrator_policy.baseline.txt"
    patch = REPO / "patches/operator-first/provider-orchestrator-policy.patch"
    installer_source = root / "source"
    installer_py = installer_source / "ops/executive_os/provider_orchestrator_policy.py"
    installer_py.parent.mkdir(parents=True)
    initial = original.read_bytes()
    assert hashlib.sha256(initial).hexdigest() == (
        "1d4658ac237217ac565e6feda922e55f9bc8a15a0448e8724d00d8ba5ec04594"
    )
    installer_py.write_bytes(initial)
    for option in ("--check", None):
        command = ["git", "apply"] + ([option] if option else []) + [str(patch)]
        subprocess.run(command, cwd=installer_source, capture_output=True,
                       check=True, timeout=10)
    shutil.copytree(ROLE_ROOT, installer_source / "skills/mastermind-fabric-orchestration")
    inert_guard = installer_source / "ops/executive_os/provider_orchestrator_guard.py"
    inert_guard.write_text("# disposable fixture, not an admission guard\n")
    spec = importlib.util.spec_from_file_location(
        "harness_fixture_policy_" + uuid.uuid4().hex, installer_py,
    )
    assert spec is not None and spec.loader is not None
    installer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(installer)
    home = root / "isolated-user"
    home.mkdir(mode=0o700)
    assert installer.apply_policy(home, guard_source=inert_guard)["state"] == "READY"
    receipt = installer.verify_policy(home, guard_source=inert_guard)
    assert receipt["state"] == "READY"
    assert receipt["runtime_admission_proven"] is False
    assert receipt["session_loading_proven"] is False

    # Existing Worker bootstrap packaging, not a reimplementation of its
    # source/Skill manifest. Stage only its public Skill files in this temp home.
    packaged = assemble(source_files(REPO, source_commit), source_commit, docs=False)
    assert packaged["BUILD.json"]
    build = json.loads(packaged["BUILD.json"])
    assert build["execution_authority"] is False
    assert build["native_skill_attested"] is False
    personal_skills = (home / ".agents/skills").resolve(strict=True)
    for name in ("mastermind-craft", "mastermind-worker-bootstrap"):
        for relative, bytes_value in packaged.items():
            prefix = f"skills/{name}/"
            if not relative.startswith(prefix):
                continue
            target = personal_skills / name / relative.removeprefix(prefix)
            target.parent.mkdir(parents=True, exist_ok=True)
            assert not target.exists()
            target.write_bytes(bytes_value)
            assert target.read_bytes() == bytes_value
    expected_personal = sorted((
        "mastermind-craft", "mastermind-fabric-orchestration",
        "mastermind-worker-bootstrap",
    ))
    protected_skills = (REPO / "plugins/mastermind-operator/skills").resolve(strict=True)
    workspace = root / "workspace"
    workspace.mkdir(mode=0o700)
    client = AppServerClient(
        [executable, "app-server", "--strict-config",
         "-c", 'sandbox_mode="read-only"',
         "-c", "skills.bundled.enabled=false", "-c", "features.plugins=false",
         "-c", "features.apps=false", "-c", "agents.enabled=false"],
        env={"PATH": os.environ.get("PATH", "/opt/homebrew/bin:/usr/bin:/bin"),
             "HOME": str(home), "CODEX_HOME": str(home / ".codex"),
             "LC_ALL": "C"},
        cwd=workspace, start_new_session=True,
    )
    exact_names: list[str] = []
    try:
        client.start()
        client.request(
            "initialize", {"clientInfo": _CLIENT_INFO,
                           "capabilities": {"experimentalApi": True}}, timeout=10,
        )
        client.notify("initialized", {})
        rows = parse_skills_list_strict(
            client.request("skills/list", skills_list_params(str(workspace)), timeout=10),
            expected_cwd=str(workspace),
        )
        assert sorted(enabled_skill_names(rows)) == expected_personal
        client.request("skills/extraRoots/set",
                       extra_roots_set_params([str(protected_skills)]), timeout=10)
        rows = parse_skills_list_strict(
            client.request("skills/list", skills_list_params(str(workspace)), timeout=10),
            expected_cwd=str(workspace),
        )
        exact_names = sorted(enabled_skill_names(rows))
        expected = sorted(expected_personal + [
            f"mastermind-operator:{grant.runtime_name}" for grant in old.skill_grants
        ])
        assert exact_names == expected
        assert len(rows) == 7
        for row in rows:
            assert row.get("enabled") is True
            name = str(row["name"])
            if name.startswith("mastermind-operator:"):
                short = name.removeprefix("mastermind-operator:")
                actual = protected_skills / short / "SKILL.md"
            else:
                actual = personal_skills / name / "SKILL.md"
            assert actual.resolve(strict=True).is_file()
            assert row.get("path") == str(actual.resolve(strict=True))
        client.request("skills/extraRoots/set", extra_roots_set_params([]), timeout=10)
        cleared = parse_skills_list_strict(
            client.request("skills/list", skills_list_params(str(workspace)), timeout=10),
            expected_cwd=str(workspace),
        )
        assert sorted(enabled_skill_names(cleared)) == expected_personal
    finally:
        client.close()
        assert not client.alive()
    with capsys.disabled():
        print(json.dumps({
            "schema": "mastermind.combined_native_skill_catalog/v1",
            "provider_names": exact_names,
            "installed_home": "DISPOSABLE_ONLY",
            "protected_generation": generation.package_generation_digest,
            "user_home_role_installer": "READY",
            "catalog_enabled_count": len(exact_names),
            "model_turns": 0, "production_armed": False,
            "credentials_read": False, "process_closed": True,
        }, sort_keys=True))
