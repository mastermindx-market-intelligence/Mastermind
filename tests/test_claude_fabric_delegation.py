"""No-network coverage for the existing Claude and paid-operator Fabric entrypoints.

These tests verify installation and prompt delivery only. They never spawn,
authorize, or claim acceptance of a paid provider worker.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from ops.executive_os import provider_orchestrator_policy as policy
from ops.native_fabric.quota_continuity.candidate import fabric_operator_client as operator

ROOT = Path(__file__).resolve().parents[1]


def test_operator_staged_overlay_preserves_installed_source_preimage() -> None:
    native = ROOT / "ops/native_fabric/quota_continuity"
    pinned = json.loads((native / "rollout/native-preimages.json").read_text())
    source = (native / "source/fabric_operator_client.py").read_bytes()
    candidate = (native / "candidate/fabric_operator_client.py").read_bytes()
    assert hashlib.sha256(source).hexdigest() == pinned["files"]["fabric_operator_client.py"]
    assert b"mastermind.fabric_operator_child_request.v1" not in source
    assert b"mastermind.fabric_operator_child_request.v1" in candidate
    assert candidate != source


def test_claude_fabric_skill_is_exact_source_blob() -> None:
    path = ROOT / "skills/mastermind-claude-fabric-delegation/SKILL.md"
    raw = path.read_bytes()
    git_blob = hashlib.sha1(b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw).hexdigest()
    assert git_blob == policy.CLAUDE_FABRIC_SKILL_BLOB_SHA
    assert raw == policy._canonical_claude_fabric_skill()
    text = raw.decode("utf-8")
    for required in (
        "fabric_task.py", "fabric_request", "fabric_status", "fabric_result",
        "fabric_accept", "fabric_operator_scope", "fabric_child_request",
        "fabric_child_acknowledge", "FABRIC_IDENTITY_UNVERIFIED",
        "FABRIC_CLIENT_NOT_EXPOSED", "Grok 4.7", "not",
    ):
        assert required in text



def test_claude_fresh_session_login_and_trust_are_explicit_gates() -> None:
    skill = (ROOT / "skills/mastermind-claude-fabric-delegation/SKILL.md").read_text()
    for token in (
        "claude auth status",
        "loggedIn=false",
        "CLAUDE_LOGIN_REQUIRED",
        "OAuth session expired",
        "workspace trust",
        "FABRIC_IDENTITY_UNVERIFIED",
        "FABRIC_ADAPTER_SANDBOX_DENIED",
    ):
        assert token in skill
    assert "Do not edit" in skill
    assert "dispatch nothing" in skill

def test_scoped_claude_install_preserves_codex_and_verifies_drift(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    result = policy.apply_provider_policy(home, "claude")
    skill = home / ".claude/skills/mastermind-claude-fabric-delegation/SKILL.md"
    assert result["state"] == "READY"
    assert result["session_loading_proven"] is False
    assert result["runtime_admission_proven"] is False
    assert result["claude_fabric_skill_blob_sha"] == policy.CLAUDE_FABRIC_SKILL_BLOB_SHA
    assert skill.read_bytes() == policy._canonical_claude_fabric_skill()
    assert not (home / ".codex").exists()
    doc = (home / ".claude/CLAUDE.md").read_text()
    assert doc.count(policy.BEGIN) == doc.count(policy.END) == 1
    assert "mastermind-claude-fabric-delegation/SKILL.md" in doc
    assert "fabric_operator_scope" in doc
    assert policy.verify_policy(home, provider="claude")["state"] == "READY"

    original = skill.read_bytes()
    repeat = policy.apply_provider_policy(home, "claude")
    assert repeat["state"] == "READY"
    assert skill.read_bytes() == original

    skill.write_bytes(original + b"\n# unexpected override\n")
    drift = policy.verify_policy(home, provider="claude")
    assert drift["state"] == "DRIFT"
    assert "claude_fabric_skill.digest" in drift["issues"]


def test_refuse_modified_source_before_any_claude_install(tmp_path: Path, monkeypatch) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(policy, "CLAUDE_FABRIC_SKILL_BLOB_SHA", "0" * 40)
    with pytest.raises(policy.OrchestratorPolicyError, match="source digest mismatch"):
        policy.apply_provider_policy(home, "claude")
    assert list(home.iterdir()) == []


def test_operator_packet_gets_executable_discovery_contract_not_identity() -> None:
    instruction = operator.OPERATOR_INSTRUCTIONS
    for value in (
        "fabric_operator_scope", "fabric_child_request",
        "fabric_child_status", "fabric_child_wait",
        "fabric_child_result", "fabric_child_acknowledge",
        "mastermind.fabric_operator_child_request.v1",
        "child_budget_remaining", "C0_MECHANICAL", "C1_ROUTINE_BOUNDED",
        "run_id", "sha256", "not prove scope", "do not simulate",
    ):
        assert value.lower() in instruction.lower()
    shell_source = (ROOT / "ops/native_fabric/quota_continuity/source/remote_sub.sh").read_text()
    assert 'if [ "$OPERATOR_CHILD_BUDGET" != "0" ]; then' in shell_source
    assert "from fabric_operator_client import OPERATOR_INSTRUCTIONS" in shell_source
    assert "OPERATOR_INSTRUCTIONS.encode()" in shell_source
    assert "FABRIC_OPERATOR_CAPSULE" in shell_source
    assert operator.load_operator_environment(
        {"POOL_TASK_CLASS": "mechanical", "FABRIC_OPERATOR_CAPABILITY": "caller-bearer"},
        "a-regular-leaf", "grok", "grok-4.6", b"packet",
    ) == {"POOL_TASK_CLASS": "mechanical"}


def test_unadmitted_grok_47_cannot_mint_child_capability() -> None:
    with pytest.raises(ValueError, match="operator_capsule_scope"):
        operator.load_operator_environment(
            {"FABRIC_OPERATOR_CAPSULE": "lanes/tmp/run1.operator-cap.json",
             "POOL_TASK_CLASS": "domain_orchestration"},
            "run1", "grok", "grok-4.7", b"packet",
        )


def test_claude_fabric_only_installer_preserves_existing_native_twelve(tmp_path: Path) -> None:
    home = tmp_path / "home"
    provider = home / ".claude"
    provider.mkdir(parents=True)
    original = {"env": {
        "CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS": "12",
        "CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH": "1",
    }, "permissions": {"defaultMode": "bypassPermissions"}, "hooks": {
        "PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": "/private/existing-guard"}]}],
    }}
    settings = provider / "settings.json"
    settings.write_text(json.dumps(original, sort_keys=True) + "\n")
    original_settings = settings.read_bytes()
    claude_doc = provider / "CLAUDE.md"
    claude_doc.write_text("# Existing custom Claude guidance\n\nKeep my parallel sessions intact.\n")
    result = policy.apply_claude_fabric_entrypoint(home)
    assert result["state"] == "READY"
    assert result["native_capacity_modified"] is False
    assert result["provider_settings_modified"] is False
    assert settings.read_bytes() == original_settings
    assert not (home / ".codex").exists()
    assert not (provider / "hooks").exists()
    text = claude_doc.read_text()
    assert "Keep my parallel sessions intact." in text
    assert text.count(policy.FABRIC_ENTRY_BEGIN) == text.count(policy.FABRIC_ENTRY_END) == 1
    skill = provider / "skills/mastermind-claude-fabric-delegation/SKILL.md"
    assert skill.read_bytes() == policy._canonical_claude_fabric_skill()
    assert policy.verify_claude_fabric_entrypoint(home)["state"] == "READY"

    before = claude_doc.read_bytes()
    again = policy.apply_claude_fabric_entrypoint(home)
    assert again["state"] == "READY"
    assert claude_doc.read_bytes() == before
    assert settings.read_bytes() == original_settings

    skill.write_bytes(skill.read_bytes() + b"\nUntrusted edit\n")
    observed = policy.verify_claude_fabric_entrypoint(home)
    assert observed["state"] == "DRIFT"
    assert "claude_fabric_skill.digest" in observed["issues"]


def test_claude_fabric_only_installer_rejects_ambiguous_marker_before_writing(tmp_path: Path) -> None:
    home = tmp_path / "home"
    d = home / ".claude"
    d.mkdir(parents=True)
    source = d / "CLAUDE.md"
    bad = policy.FABRIC_ENTRY_BEGIN + "\n" + policy.FABRIC_ENTRY_BEGIN
    source.write_text(bad)
    with pytest.raises(policy.OrchestratorPolicyError, match="markers ambiguous"):
        policy.apply_claude_fabric_entrypoint(home)
    assert source.read_text() == bad
    assert not (d / "skills").exists()
