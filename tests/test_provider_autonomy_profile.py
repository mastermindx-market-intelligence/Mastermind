from __future__ import annotations

import json
from pathlib import Path

import pytest

from ops.executive_os.provider_autonomy_profile import (
    AutonomyProfileError,
    apply_claude,
    apply_codex,
    apply_profiles,
    verify_profiles,
)


def test_apply_preserves_unrelated_claude_settings(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text('{"model":"opus","permissions":{"allow":[]}}\n')
    apply_claude(path)
    value = json.loads(path.read_text())
    assert value["model"] == "opus"
    assert value["permissions"]["allow"] == []
    assert value["permissions"]["defaultMode"] == "bypassPermissions"
    assert json.loads((tmp_path / "settings.json.mastermind-backup").read_text())["model"] == "opus"


def test_apply_codex_sets_only_reviewed_top_level_keys_and_preserves_tables(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text('model = "gpt-6-astra"\nsandbox_mode = "read-only"\n\n[projects."/tmp/x"]\ntrust_level = "trusted"\n')
    apply_codex(path)
    text = path.read_text()
    assert 'model = "gpt-6-astra"' in text
    assert 'sandbox_mode = "danger-full-access"' in text
    assert 'approval_policy = "never"' in text
    assert '[projects."/tmp/x"]' in text
    assert 'trust_level = "trusted"' in text
    assert 'sandbox_mode = "read-only"' not in text
    assert (tmp_path / "config.toml.mastermind-backup").exists()


def test_apply_is_idempotent_and_does_not_replace_original_backup(tmp_path: Path) -> None:
    codex = tmp_path / "config.toml"
    claude = tmp_path / "settings.json"
    codex.write_text('model = "gpt-6-astra"\n')
    claude.write_text('{"permissions":{"allow":[]}}\n')
    apply_profiles(codex, claude)
    first_codex = codex.read_bytes()
    first_claude = claude.read_bytes()
    backup_codex = (tmp_path / "config.toml.mastermind-backup").read_bytes()
    backup_claude = (tmp_path / "settings.json.mastermind-backup").read_bytes()
    apply_profiles(codex, claude)
    assert codex.read_bytes() == first_codex
    assert claude.read_bytes() == first_claude
    assert (tmp_path / "config.toml.mastermind-backup").read_bytes() == backup_codex
    assert (tmp_path / "settings.json.mastermind-backup").read_bytes() == backup_claude


def test_verify_reports_drift_without_mutating(tmp_path: Path) -> None:
    codex = tmp_path / "config.toml"
    claude = tmp_path / "settings.json"
    codex.write_text('sandbox_mode = "workspace-write"\napproval_policy = "on-request"\n')
    claude.write_text('{"permissions":{"defaultMode":"default"}}\n')
    before = (codex.read_bytes(), claude.read_bytes())
    issues = verify_profiles(codex, claude)
    assert set(issues) == {"codex.sandbox_mode", "codex.approval_policy", "claude.permissions.defaultMode"}
    assert (codex.read_bytes(), claude.read_bytes()) == before


def test_verify_passes_after_apply(tmp_path: Path) -> None:
    codex = tmp_path / "config.toml"
    claude = tmp_path / "settings.json"
    codex.write_text('model = "gpt-6-astra"\n')
    claude.write_text('{}\n')
    apply_profiles(codex, claude)
    assert verify_profiles(codex, claude) == ()


def test_verify_detects_selected_profile_override(tmp_path: Path) -> None:
    codex = tmp_path / "config.toml"
    claude = tmp_path / "settings.json"
    codex.write_text(
        'sandbox_mode = "danger-full-access"\napproval_policy = "never"\n'
        'profile = "interactive"\n\n[profiles.interactive]\napproval_policy = "on-request"\n'
    )
    claude.write_text('{"permissions":{"defaultMode":"bypassPermissions"}}\n')
    issues = verify_profiles(codex, claude, codex_project_configs=())
    assert "codex.profile" in issues
    assert "codex.profiles.override" in issues


def test_verify_detects_project_layer_permission_override(tmp_path: Path) -> None:
    codex = tmp_path / "config.toml"
    claude = tmp_path / "settings.json"
    project = tmp_path / "project.toml"
    codex.write_text('sandbox_mode = "danger-full-access"\napproval_policy = "never"\n')
    claude.write_text('{"permissions":{"defaultMode":"bypassPermissions"}}\n')
    project.write_text('approval_policy = "on-request"\n')
    issues = verify_profiles(codex, claude, codex_project_configs=(project,))
    assert "codex.project.approval_policy" in issues


@pytest.mark.parametrize(
    "filename,payload",
    [
        ("config.toml", 'sandbox_mode = "unterminated\n'),
        ("settings.json", '{bad json'),
    ],
)
def test_malformed_provider_config_refuses_without_backup(tmp_path: Path, filename: str, payload: str) -> None:
    path = tmp_path / filename
    path.write_text(payload)
    before = path.read_bytes()
    with pytest.raises(AutonomyProfileError):
        if filename.endswith("toml"):
            apply_codex(path)
        else:
            apply_claude(path)
    assert path.read_bytes() == before
    assert not (tmp_path / f"{filename}.mastermind-backup").exists()
