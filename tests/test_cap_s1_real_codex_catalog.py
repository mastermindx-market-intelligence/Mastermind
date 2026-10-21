"""Opt-in, credential-free real Codex Skill-catalog qualification.

This exercises only App Server initialization and source-verified Skill catalog
projection, not a provider account, model turn, Runtime admission or worker job.
CI skips it unless MASTERMIND_REAL_CODEX_SKILLS_CATALOG_TEST=1 is explicit.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
from types import SimpleNamespace

import pytest

from control_plane.codex_operator_adapter import (
    CodexOperatorAdapter, _CLIENT_INFO, parse_config_read, _observed_network_state,
)
from control_plane.executive_agent_capabilities import (
    ExecutionCapabilityRegistry, app_server_security_config_digest,
)
from scripts.ohf.capability_skill_projection import (
    ORIGIN_VERIFIED_EPHEMERAL_GIT_ARCHIVE,
    cleanup_skill_projection, create_ephemeral_archive_origin,
    stage_skill_projection,
)
from scripts.ohf.laboratory import AppServerClient
from scripts.ohf.protocol import (
    enabled_skill_names, extra_roots_set_params, parse_skills_list_strict,
    skills_list_params,
)

REPO = Path(__file__).resolve().parent.parent
FIXTURE = (
    REPO / "scripts/ohf/fixtures/"
    "executive_agent_capabilities_v4_rich_write_operator.json"
)
PROFILE = "operator.appserver.write.mastermind-operator.v1"


@pytest.mark.skipif(
    os.environ.get("MASTERMIND_REAL_CODEX_SKILLS_CATALOG_TEST") != "1",
    reason="real Codex App Server catalog preflight requires explicit opt-in",
)
def test_credential_free_real_codex_namespaced_skill_catalog(tmp_path, capsys):
    binary = shutil.which("codex")
    assert binary is not None, "opt-in real Codex binary unavailable"
    root = tmp_path.resolve()
    attempt = root / "attempt"; attempt.mkdir(mode=0o700)
    home = root / "codex-home"; home.mkdir(mode=0o700)
    workspace = root / "workspace"; workspace.mkdir(mode=0o700)
    reg = ExecutionCapabilityRegistry.load(FIXTURE, source_root=REPO)
    assert reg.production_armed is False
    profile = reg.resolve(PROFILE)
    generation = reg.capability_packages["mastermind-operator.p1"]
    git_dir = subprocess.run(
        ["git", "rev-parse", "--absolute-git-dir"], cwd=REPO,
        capture_output=True, text=True, check=True, timeout=5,
    ).stdout.strip()
    origin = create_ephemeral_archive_origin(
        repository_git_dir=git_dir, source_commit=generation.source_commit,
        package_root=generation.package_root, scratch_root=root,
        expected_package_tree_sha=generation.source_tree_sha,
    )
    projection = stage_skill_projection(
        generation=generation,
        origin_mode=ORIGIN_VERIFIED_EPHEMERAL_GIT_ARCHIVE,
        origin_root=origin.origin_root, attempt_root=attempt,
        owning_operation_id="real-codex-catalog-noauth-optin",
        owning_process_generation="gen1", origin_receipt=origin,
    )
    # Render the exact V4 write+Skills profile into the actual App Server.
    # The filesystem sandbox config is observed, never exercised with a turn.
    args = [binary, "app-server", "--strict-config"]
    for override in profile.app_server_config_overrides():
        args.extend(("-c", override))
    # Only a disposable credential-free CODEX_HOME; no ambient token inherited.
    environment = {
        "PATH": os.environ.get("PATH", "/opt/homebrew/bin:/usr/bin:/bin"),
        "HOME": str(home), "CODEX_HOME": str(home), "LC_ALL": "C",
    }
    client = AppServerClient(
        args, env=environment, cwd=workspace, start_new_session=True,
    )
    names = ()
    cleared = ()
    success = False
    try:
        client.start()
        client.request(
            "initialize", {"clientInfo": _CLIENT_INFO,
                           "capabilities": {"experimentalApi": True}},
            timeout=10,
        )
        client.notify("initialized", {})
        config = parse_config_read(client.request(
            "config/read", {"includeLayers": False}, timeout=10,
        ))
        assert config.get("sandbox_mode") == "workspace-write"
        assert config.get("approval_policy") == "never"
        assert _observed_network_state(config) == "disabled"
        assert app_server_security_config_digest(config) == profile.expected_config_digest
        client.request("skills/extraRoots/set", extra_roots_set_params([]), timeout=10)
        before = parse_skills_list_strict(
            client.request("skills/list", skills_list_params(str(workspace)), timeout=10),
            expected_cwd=str(workspace),
        )
        assert enabled_skill_names(before) == []
        client.request(
            "skills/extraRoots/set",
            extra_roots_set_params([projection.skills_root]), timeout=10,
        )
        raw_rows = parse_skills_list_strict(
            client.request("skills/list", skills_list_params(str(workspace)), timeout=10),
            expected_cwd=str(workspace),
        )
        names = tuple(sorted(enabled_skill_names(raw_rows)))
        namespace = Path(generation.package_root).name
        assert names == tuple(sorted(
            f"{namespace}:{name}" for name in profile.skills
        ))
        binding = SimpleNamespace(
            generation=generation, profile=profile,
            protocol_receipt=SimpleNamespace(supports_skill_input_path=True),
        )
        observed, precision = CodexOperatorAdapter._reduce_skill_observation(
            raw_rows, skills_root=projection.skills_root, binding=binding,
        )
        assert precision == "path_precise"
        assert tuple(row[0] for row in observed) == tuple(sorted(profile.skills))
        assert {row[0]: row[3] for row in observed} == {
            grant.runtime_name: grant.skill_content_digest
            for grant in profile.skill_grants
        }
        client.request("skills/extraRoots/set", extra_roots_set_params([]), timeout=10)
        after = parse_skills_list_strict(
            client.request("skills/list", skills_list_params(str(workspace)), timeout=10),
            expected_cwd=str(workspace),
        )
        cleared = tuple(sorted(enabled_skill_names(after)))
        assert cleared == ()
        success = True
    finally:
        client.close()
        cleanup = cleanup_skill_projection(projection)
        assert not client.alive()
        assert cleanup.verified_absent
    assert success
    with capsys.disabled():
        print(json.dumps({
            "schema": "mastermind.real_codex_skill_catalog_preflight/v1",
            "candidate_armed": False, "model_turns": 0,
            "profile_sandbox": "workspace-write",
            "effective_config_digest": profile.expected_config_digest,
            "provider_names": names,
            "canonical_names": sorted(profile.skills),
            "after_clear": cleared,
            "projection_removed": True, "process_closed": True,
        }, sort_keys=True))
