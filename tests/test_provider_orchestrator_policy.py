from __future__ import annotations

import json
import os
import tomllib
from pathlib import Path
from typing import Any

import pytest

from control_plane.child_execution_contracts import ExecutionBinding
from ops.executive_os import provider_orchestrator_guard as guard
from ops.executive_os import provider_orchestrator_policy as policy
from ops.executive_os.provider_orchestrator_policy import (
    BEGIN,
    END,
    OrchestratorPolicyApplyIncomplete,
    OrchestratorPolicyError,
    apply_policy,
    verify_policy,
)


def _seed_home(home: Path) -> None:
    (home / ".codex").mkdir(parents=True)
    (home / ".claude").mkdir(parents=True)
    (home / ".codex" / "AGENTS.md").write_text(
        "# Existing Codex policy\n\nKeep this machine-local note.\n",
        encoding="utf-8",
    )
    (home / ".codex" / "config.toml").write_text(
        """model = "gpt-6.1-sol"

[agents]
max_concurrent_threads_per_session = 4
default_subagent_model = "gpt-5.6-sol"
enabled = false

[features]
hooks = true
""",
        encoding="utf-8",
    )
    (home / ".claude" / "CLAUDE.md").write_text(
        "# Existing Claude policy\n\nKeep this Claude note.\n",
        encoding="utf-8",
    )
    (home / ".claude" / "settings.json").write_text(
        json.dumps(
            {
                "model": "fable",
                "permissions": {"defaultMode": "bypassPermissions"},
                "hooks": {
                    "PreToolUse": [
                        {
                            "matcher": "Write",
                            "hooks": [
                                {
                                    "type": "command",
                                    "command": "python3 /opt/existing-write-guard.py",
                                }
                            ],
                        }
                    ]
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (home / ".codex" / "hooks.json").write_text(
        json.dumps(
            {
                "description": "Existing local hooks",
                "hooks": {
                    "SessionStart": [
                        {
                            "matcher": "^startup$",
                            "hooks": [
                                {
                                    "type": "command",
                                    "command": "python3 /opt/existing-start.py",
                                }
                            ],
                        }
                    ]
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )


def test_apply_preserves_unrelated_provider_policy_and_hooks(tmp_path: Path) -> None:
    home = tmp_path / "home"
    _seed_home(home)

    result = apply_policy(home)

    assert result["state"] == "READY"
    codex_doc = (home / ".codex" / "AGENTS.md").read_text(encoding="utf-8")
    claude_doc = (home / ".claude" / "CLAUDE.md").read_text(encoding="utf-8")
    assert "# Existing Codex policy" in codex_doc
    assert "Keep this machine-local note." in codex_doc
    assert "# Existing Claude policy" in claude_doc
    assert "Keep this Claude note." in claude_doc
    assert codex_doc.count(BEGIN) == codex_doc.count(END) == 1
    assert claude_doc.count(BEGIN) == claude_doc.count(END) == 1

    claude = json.loads((home / ".claude" / "settings.json").read_text())
    assert claude["model"] == "fable"
    assert claude["permissions"]["defaultMode"] == "bypassPermissions"
    assert claude["env"]["CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS"] == "2"
    assert claude["env"]["CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH"] == "1"
    assert any(
        row.get("matcher") == "Write"
        for row in claude["hooks"]["PreToolUse"]
    )
    assert any(
        row.get("matcher") == "Agent|Task|Bash"
        for row in claude["hooks"]["PreToolUse"]
    )

    codex_config = tomllib.loads((home / ".codex" / "config.toml").read_text())
    assert codex_config["model"] == "gpt-6.1-sol"
    assert codex_config["features"]["hooks"] is True
    assert codex_config["agents"]["enabled"] is False
    assert codex_config["agents"]["max_concurrent_threads_per_session"] == 1
    assert codex_config["agents"]["default_subagent_model"] == "gpt-5.6-sol"

    codex = json.loads((home / ".codex" / "hooks.json").read_text())
    assert codex["description"] == "Existing local hooks"
    assert codex["hooks"]["SessionStart"][0]["matcher"] == "^startup$"
    assert any(
        row.get("matcher") == "^Bash$"
        for row in codex["hooks"]["PreToolUse"]
    )

    codex_guard = home / ".codex" / "hooks" / "mastermind_fabric_routing_guard.py"
    claude_guard = home / ".claude" / "hooks" / "mastermind_fabric_routing_guard.py"
    assert codex_guard.read_bytes() == claude_guard.read_bytes()
    assert result["guard_sha256"]
    assert result["credentials_read"] is False
    assert result["permissions_changed"] is False
    assert result["lifecycle_created"] is False


def test_apply_is_idempotent_and_backups_keep_original_content(tmp_path: Path) -> None:
    home = tmp_path / "home"
    _seed_home(home)
    originals = {
        "codex_doc": (home / ".codex" / "AGENTS.md").read_bytes(),
        "codex_config": (home / ".codex" / "config.toml").read_bytes(),
        "claude_doc": (home / ".claude" / "CLAUDE.md").read_bytes(),
        "codex_hooks": (home / ".codex" / "hooks.json").read_bytes(),
        "claude_settings": (home / ".claude" / "settings.json").read_bytes(),
    }

    first = apply_policy(home)
    first_bytes = {
        path: path.read_bytes()
        for path in (
            home / ".codex" / "AGENTS.md",
            home / ".codex" / "config.toml",
            home / ".claude" / "CLAUDE.md",
            home / ".codex" / "hooks.json",
            home / ".claude" / "settings.json",
            home / ".codex" / "hooks" / "mastermind_fabric_routing_guard.py",
            home / ".claude" / "hooks" / "mastermind_fabric_routing_guard.py",
        )
    }
    second = apply_policy(home)

    assert first["state"] == second["state"] == "READY"
    assert {path: path.read_bytes() for path in first_bytes} == first_bytes
    assert (
        home / ".codex" / "AGENTS.md.mastermind-orchestrator-backup"
    ).read_bytes() == originals["codex_doc"]
    assert (
        home / ".codex" / "config.toml.mastermind-orchestrator-backup"
    ).read_bytes() == originals["codex_config"]
    assert (
        home / ".claude" / "CLAUDE.md.mastermind-orchestrator-backup"
    ).read_bytes() == originals["claude_doc"]
    assert (
        home / ".codex" / "hooks.json.mastermind-orchestrator-backup"
    ).read_bytes() == originals["codex_hooks"]
    assert (
        home / ".claude" / "settings.json.mastermind-orchestrator-backup"
    ).read_bytes() == originals["claude_settings"]


def test_managed_policy_retains_efficiency_and_hierarchy_laws() -> None:
    text = policy._managed_text("")
    required = (
        "accepted capability delta per root budget",
        "operator owns",
        "Omit a layer that adds only relay overhead",
        "compact capsules",
        "FRONTIER_WITNESS",
        "Capacity is a ceiling, not a target",
        "NO_DELTA_LOOP",
        "worker breaker",
        "Before starting a second semantic vertical",
        "Finalization ceremony is pre-yield only",
    )
    for phrase in required:
        assert phrase in text


def test_apply_handles_prose_only_host_with_missing_codex_hooks(tmp_path: Path) -> None:
    """M1/mini4/MBP class: instructions exist but mechanical hooks are absent."""
    home = tmp_path / "home"
    (home / ".codex").mkdir(parents=True)
    (home / ".claude").mkdir(parents=True)
    native_override = """## Native Codex CEO routing override

For local Mastermind CEO/orchestrator sessions, route routine worker parallelism through Fabric.

Native Codex child cap is **0 by default**. At most one exception may exist.

This is routing policy only. It grants no Fabric admission, provider capacity, source custody, effect clearance, or permission.

"""
    legacy = """<!-- mastermind-ceo-async-ci-v1 -->
old async law
<!-- /mastermind-ceo-async-ci-v1 -->
<!-- mastermind-ceo-context-discipline-v1 -->
old context law
<!-- /mastermind-ceo-context-discipline-v1 -->
<!-- mastermind-ceo-forward-execution -->
A CEO cycle is event/phase-scoped, not tool/turn-scoped.
Finalization ceremony is pre-yield only.
<!-- /mastermind-ceo-forward-execution -->
<!-- mastermind-orchestration-burn-guard-v1 -->
Capacity is a ceiling, not a utilization target.
<!-- /mastermind-orchestration-burn-guard-v1 -->
<!-- mastermind-fabric-routing-operational-v1 -->
Sol operating executive -> Fabric workers.
<!-- /mastermind-fabric-routing-operational-v1 -->
"""
    (home / ".codex" / "AGENTS.md").write_text(
        "# Storage rule\n\nKeep external SSD placement.\n\n"
        + native_override
        + legacy,
        encoding="utf-8",
    )
    (home / ".claude" / "CLAUDE.md").write_text(
        "# Storage rule\n\nKeep external SSD placement.\n\n" + legacy,
        encoding="utf-8",
    )
    (home / ".claude" / "settings.json").write_text(
        json.dumps(
            {
                "hooks": {
                    "WorktreeCreate": [
                        {
                            "hooks": [
                                {
                                    "type": "command",
                                    "command": "python3 /opt/worktree-create.py",
                                }
                            ]
                        }
                    ]
                }
            }
        )
        + "\n",
        encoding="utf-8",
    )
    assert not (home / ".codex" / "hooks.json").exists()
    assert not (home / ".codex" / "config.toml").exists()

    result = apply_policy(home)

    assert result["state"] == "READY"
    codex_config = tomllib.loads((home / ".codex" / "config.toml").read_text())
    assert codex_config["agents"] == {
        "max_concurrent_threads_per_session": 1,
        "enabled": False,
    }
    codex_hooks = json.loads((home / ".codex" / "hooks.json").read_text())
    assert len(codex_hooks["hooks"]["PreToolUse"]) == 1
    claude = json.loads((home / ".claude" / "settings.json").read_text())
    assert claude["hooks"]["WorktreeCreate"][0]["hooks"][0]["command"] == (
        "python3 /opt/worktree-create.py"
    )
    for path in (home / ".codex" / "AGENTS.md", home / ".claude" / "CLAUDE.md"):
        text = path.read_text(encoding="utf-8")
        assert "Keep external SSD placement." in text
        assert "mastermind-ceo-async-ci-v1" not in text
        assert "<!-- mastermind-ceo-forward-execution -->" not in text
        assert "<!-- /mastermind-ceo-forward-execution -->" not in text
        assert "## Native Codex CEO routing override" not in text
        assert "mastermind-orchestration-burn-guard-v1" not in text
        assert "mastermind-fabric-routing-operational-v1" not in text
        assert "A CEO cycle is event/phase-scoped, not tool/turn-scoped." in text
        assert "Finalization ceremony is pre-yield only." in text
        assert "Capacity is a ceiling, not a target." in text
        assert "operator owns" in text
        assert text.count(BEGIN) == text.count(END) == 1


def test_apply_migrates_native_override_before_existing_v2_block(
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    _seed_home(home)
    apply_policy(home)
    path = home / ".codex" / "AGENTS.md"
    current = path.read_text(encoding="utf-8")
    start = current.index(BEGIN)
    temporary = (
        "## Native Codex CEO routing override\n\n"
        "Native Codex child cap is **0 by default**.\n\n"
        "This is routing policy only. It grants no Fabric admission, provider capacity, "
        "source custody, effect clearance, or permission.\n\n"
    )
    path.write_text(
        current[:start] + temporary + current[start:],
        encoding="utf-8",
    )

    result = apply_policy(home)

    assert result["state"] == "READY"
    text = path.read_text(encoding="utf-8")
    assert "## Native Codex CEO routing override" not in text
    assert text.count(BEGIN) == text.count(END) == 1


def test_apply_refuses_ambiguous_unmarked_native_override(tmp_path: Path) -> None:
    home = tmp_path / "home"
    _seed_home(home)
    path = home / ".codex" / "AGENTS.md"
    original = path.read_text(encoding="utf-8")
    path.write_text(
        original
        + "\n## Native Codex CEO routing override\n\n"
        + "This is some unrelated text without the known migration sentinels.\n"
        + "\n## Following section\nkeep me\n",
        encoding="utf-8",
    )

    with pytest.raises(
        OrchestratorPolicyError,
        match="refuse ambiguous Native Codex CEO routing override migration",
    ):
        apply_policy(home)

    assert "This is some unrelated text" in path.read_text(encoding="utf-8")


def test_apply_replaces_legacy_managed_blocks_instead_of_stacking_policy(tmp_path: Path) -> None:
    home = tmp_path / "home"
    _seed_home(home)
    legacy = """<!-- mastermind-ceo-async-ci-v1 -->
old async law
<!-- /mastermind-ceo-async-ci-v1 -->
<!-- mastermind-ceo-context-discipline-v1 -->
old context law
<!-- /mastermind-ceo-context-discipline-v1 -->
"""
    current = (home / ".codex" / "AGENTS.md").read_text(encoding="utf-8")
    (home / ".codex" / "AGENTS.md").write_text(
        current + "\n" + legacy,
        encoding="utf-8",
    )

    apply_policy(home)

    text = (home / ".codex" / "AGENTS.md").read_text(encoding="utf-8")
    assert "mastermind-ceo-async-ci-v1" not in text
    assert "mastermind-ceo-context-discipline-v1" not in text
    assert text.count(BEGIN) == text.count(END) == 1
    assert "old async law" not in text
    assert "old context law" not in text
    assert "mastermind-orchestration-burn-guard-v1" not in text
    assert "mastermind-fabric-routing-operational-v1" not in text
    assert "A CEO cycle is event/phase-scoped, not tool/turn-scoped." in text
    assert "Finalization ceremony is pre-yield only." in text
    assert "Capacity is a ceiling, not a target." in text
    assert "operator owns" in text
    assert "# Existing Codex policy" in text


def test_verify_reports_drift_without_mutating(tmp_path: Path) -> None:
    home = tmp_path / "home"
    _seed_home(home)
    apply_policy(home)
    guard_path = home / ".codex" / "hooks" / "mastermind_fabric_routing_guard.py"
    guard_path.write_text("# drift\n", encoding="utf-8")
    before = guard_path.read_bytes()

    result = verify_policy(home)

    assert result["state"] == "DRIFT"
    assert "codex_guard.digest" in result["issues"]
    assert guard_path.read_bytes() == before


def test_verify_detects_managed_policy_content_drift(tmp_path: Path) -> None:
    home = tmp_path / "home"
    _seed_home(home)
    apply_policy(home)
    path = home / ".claude" / "CLAUDE.md"
    text = path.read_text(encoding="utf-8")
    path.write_text(
        text.replace(
            "Pending CI/release freezes that lane, not the mission.",
            "Pending CI/release may freeze the whole mission.",
        ),
        encoding="utf-8",
    )

    result = verify_policy(home)

    assert result["state"] == "DRIFT"
    assert "claude_doc.managed_block" in result["issues"]


def test_verify_rejects_matching_guard_command_with_non_command_type(tmp_path: Path) -> None:
    home = tmp_path / "home"
    _seed_home(home)
    apply_policy(home)
    path = home / ".claude" / "settings.json"
    value = json.loads(path.read_text(encoding="utf-8"))
    managed = next(
        row
        for row in value["hooks"]["PreToolUse"]
        if row.get("matcher") == "Agent|Task|Bash"
    )
    managed["hooks"][0]["type"] = "prompt"
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    result = verify_policy(home)

    assert result["state"] == "DRIFT"
    assert "claude_settings.pretool" in result["issues"]


def test_verify_rejects_wrong_managed_guard_timeout(tmp_path: Path) -> None:
    home = tmp_path / "home"
    _seed_home(home)
    apply_policy(home)
    path = home / ".codex" / "hooks.json"
    value = json.loads(path.read_text(encoding="utf-8"))
    managed = next(
        row
        for row in value["hooks"]["PreToolUse"]
        if row.get("matcher") == "^Bash$"
    )
    managed["hooks"][0]["timeout"] = 1
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    result = verify_policy(home)

    assert result["state"] == "DRIFT"
    assert "codex_hooks.pretool" in result["issues"]


def test_verify_rejects_async_managed_guard_registration(tmp_path: Path) -> None:
    home = tmp_path / "home"
    _seed_home(home)
    apply_policy(home)
    path = home / ".codex" / "hooks.json"
    value = json.loads(path.read_text(encoding="utf-8"))
    managed = next(
        row
        for row in value["hooks"]["PreToolUse"]
        if row.get("matcher") == "^Bash$"
    )
    managed["hooks"][0]["async"] = True
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    result = verify_policy(home)

    assert result["state"] == "DRIFT"
    assert "codex_hooks.pretool" in result["issues"]


def test_verify_rejects_extra_guard_reference_even_with_one_valid_hook(
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    _seed_home(home)
    apply_policy(home)
    path = home / ".codex" / "hooks.json"
    value = json.loads(path.read_text(encoding="utf-8"))
    managed = next(
        row
        for row in value["hooks"]["PreToolUse"]
        if row.get("matcher") == "^Bash$"
    )
    valid = dict(managed["hooks"][0])
    managed["hooks"].append(
        {
            "type": "prompt",
            "command": valid["command"],
            "timeout": 10,
        }
    )
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    result = verify_policy(home)

    assert result["state"] == "DRIFT"
    assert "codex_hooks.pretool" in result["issues"]


def test_apply_refuses_dotted_codex_agents_shape_before_rewrite(tmp_path: Path) -> None:
    home = tmp_path / "home"
    _seed_home(home)
    path = home / ".codex" / "config.toml"
    original = (
        'model = "gpt-6.1-sol"\n'
        'agents.enabled = true\n'
        'agents.max_concurrent_threads_per_session = 4\n'
    )
    path.write_text(original, encoding="utf-8")

    with pytest.raises(
        OrchestratorPolicyError,
        match=r"one explicit \[agents\] table",
    ):
        apply_policy(home)

    assert path.read_text(encoding="utf-8") == original


def test_verify_detects_codex_native_agent_cap_drift(tmp_path: Path) -> None:
    home = tmp_path / "home"
    _seed_home(home)
    apply_policy(home)
    path = home / ".codex" / "config.toml"
    text = path.read_text(encoding="utf-8")
    path.write_text(
        text.replace("enabled = false", "enabled = true").replace(
            "max_concurrent_threads_per_session = 1",
            "max_concurrent_threads_per_session = 4",
        ),
        encoding="utf-8",
    )

    result = verify_policy(home)

    assert result["state"] == "DRIFT"
    assert "codex_config.agents_enabled" in result["issues"]
    assert "codex_config.max_concurrent_threads" in result["issues"]


def test_verify_detects_claude_native_agent_cap_drift(tmp_path: Path) -> None:
    home = tmp_path / "home"
    _seed_home(home)
    apply_policy(home)
    path = home / ".claude" / "settings.json"
    value = json.loads(path.read_text(encoding="utf-8"))
    value["env"]["CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS"] = "8"
    value["env"]["CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH"] = "4"
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    result = verify_policy(home)

    assert result["state"] == "DRIFT"
    assert "claude_settings.max_concurrent_subagents" in result["issues"]
    assert "claude_settings.max_subagent_spawn_depth" in result["issues"]


def test_unsafe_provider_parent_is_refused_before_any_mutation(tmp_path: Path) -> None:
    home = tmp_path / "home"
    _seed_home(home)
    outside = tmp_path / "outside-hooks"
    outside.mkdir()
    (home / ".claude" / "hooks").symlink_to(outside, target_is_directory=True)
    before = {
        path: path.read_bytes()
        for path in (
            home / ".codex" / "AGENTS.md",
            home / ".claude" / "CLAUDE.md",
            home / ".codex" / "hooks.json",
            home / ".claude" / "settings.json",
        )
    }

    with pytest.raises(OrchestratorPolicyError, match="unsafe provider directory"):
        apply_policy(home)

    for path, payload in before.items():
        assert path.read_bytes() == payload
    assert not (home / ".codex" / "hooks").exists()
    assert list(outside.iterdir()) == []


def test_partial_apply_reports_modified_files_and_requires_same_home_verify(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    home = tmp_path / "home"
    _seed_home(home)
    real_atomic = policy._atomic_write
    calls = 0

    def fail_second(path: Path, payload: bytes) -> bool:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OrchestratorPolicyError("synthetic second-write failure")
        return real_atomic(path, payload)

    monkeypatch.setattr(policy, "_atomic_write", fail_second)

    with pytest.raises(OrchestratorPolicyApplyIncomplete) as captured:
        apply_policy(home)

    exc = captured.value
    assert exc.modified_files == (
        str(home / ".codex" / "hooks" / "mastermind_fabric_routing_guard.py"),
    )
    assert exc.verify_issues
    assert "do not switch carriers or blindly replay" in str(exc)
    assert (
        home / ".codex" / "hooks" / "mastermind_fabric_routing_guard.py"
    ).exists()
    assert not (
        home / ".claude" / "hooks" / "mastermind_fabric_routing_guard.py"
    ).exists()


def test_malformed_managed_markers_refuse_before_any_mutation(tmp_path: Path) -> None:
    home = tmp_path / "home"
    _seed_home(home)
    codex_doc = home / ".codex" / "AGENTS.md"
    codex_doc.write_text(BEGIN + "\nunterminated\n", encoding="utf-8")
    before = {
        path: path.read_bytes()
        for path in (
            codex_doc,
            home / ".claude" / "CLAUDE.md",
            home / ".codex" / "hooks.json",
            home / ".claude" / "settings.json",
        )
    }

    with pytest.raises(OrchestratorPolicyError):
        apply_policy(home)

    for path, payload in before.items():
        assert path.read_bytes() == payload
    assert not (home / ".codex" / "hooks").exists()
    assert not (home / ".claude" / "hooks").exists()


@pytest.fixture()
def mastermind_scope(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    cwd = home / "lanes" / "work"
    cwd.mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("MASTERMIND_CI_POLL_STATE_DIR", str(tmp_path / "poll-state"))
    return cwd


def _payload(
    cwd: Path,
    command: str,
    *,
    background: bool = False,
    session_id: str = "session-a",
) -> dict[str, object]:
    return {
        "cwd": str(cwd),
        "session_id": session_id,
        "tool_name": "Bash",
        "tool_input": {
            "command": command,
            **({"run_in_background": True} if background else {}),
        },
    }


def _emitted(capsys: pytest.CaptureFixture[str]) -> dict[str, Any]:
    raw = capsys.readouterr().out.strip()
    assert raw
    return json.loads(raw)["hookSpecificOutput"]


def test_guard_denies_fabric_launch_without_stable_root_identity(
    mastermind_scope: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in ("POOL_ORCHESTRATOR_ID", "POOL_PARENT_RUN_ID", "POOL_TASK_CLASS"):
        monkeypatch.delenv(name, raising=False)
    command = (
        "pool remote mini2 glm /tmp/packet.txt "
        "/Users/mini2/lanes/repos/Mastermind glm-5.3"
    )
    with pytest.raises(SystemExit):
        guard.guard_bash(
            _payload(mastermind_scope, command),
            {"command": command},
        )
    output = _emitted(capsys)
    assert output["permissionDecision"] == "deny"
    assert "Fabric root-budget guard" in output["permissionDecisionReason"]
    assert "POOL_ORCHESTRATOR_ID" in output["permissionDecisionReason"]
    assert "POOL_PARENT_RUN_ID" in output["permissionDecisionReason"]
    assert "POOL_TASK_CLASS" in output["permissionDecisionReason"]


def test_guard_denies_partially_annotated_fabric_launch(
    mastermind_scope: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in ("POOL_ORCHESTRATOR_ID", "POOL_PARENT_RUN_ID", "POOL_TASK_CLASS"):
        monkeypatch.delenv(name, raising=False)
    command = (
        "POOL_TASK_CLASS=review pool remote mini2 glm /tmp/packet.txt "
        "/Users/mini2/lanes/repos/Mastermind glm-5.3"
    )
    with pytest.raises(SystemExit):
        guard.guard_bash(_payload(mastermind_scope, command), {"command": command})
    output = _emitted(capsys)
    assert output["permissionDecision"] == "deny"
    assert "POOL_ORCHESTRATOR_ID" in output["permissionDecisionReason"]
    assert "POOL_PARENT_RUN_ID" in output["permissionDecisionReason"]


def test_guard_denies_explicit_empty_identity_over_inherited_value(
    mastermind_scope: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("POOL_ORCHESTRATOR_ID", "root-1")
    monkeypatch.setenv("POOL_PARENT_RUN_ID", "parent-1")
    monkeypatch.setenv("POOL_TASK_CLASS", "review")
    command = (
        "POOL_ORCHESTRATOR_ID='' pool remote mini2 glm /tmp/packet.txt "
        "/Users/mini2/lanes/repos/Mastermind glm-5.3"
    )
    with pytest.raises(SystemExit):
        guard.guard_bash(_payload(mastermind_scope, command), {"command": command})
    output = _emitted(capsys)
    assert output["permissionDecision"] == "deny"
    assert "POOL_ORCHESTRATOR_ID" in output["permissionDecisionReason"]


def test_guard_denies_rebinding_an_inherited_root(
    mastermind_scope: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("POOL_ORCHESTRATOR_ID", "root-original")
    monkeypatch.setenv("POOL_PARENT_RUN_ID", "parent-1")
    monkeypatch.setenv("POOL_TASK_CLASS", "review")
    command = (
        "POOL_ORCHESTRATOR_ID=root-reset pool run grok bounded /tmp grok-4.6"
    )
    with pytest.raises(SystemExit):
        guard.guard_bash(_payload(mastermind_scope, command), {"command": command})
    output = _emitted(capsys)
    assert output["permissionDecision"] == "deny"
    assert "may not be rebound" in output["permissionDecisionReason"]


def test_guard_allows_explicit_same_inherited_root(
    mastermind_scope: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("POOL_ORCHESTRATOR_ID", "root-original")
    monkeypatch.setenv("POOL_PARENT_RUN_ID", "parent-1")
    monkeypatch.setenv("POOL_TASK_CLASS", "review")
    command = (
        "POOL_ORCHESTRATOR_ID=root-original pool run grok bounded /tmp grok-4.6"
    )
    guard.guard_bash(_payload(mastermind_scope, command), {"command": command})
    assert capsys.readouterr().out == ""


def test_guard_denies_dynamic_root_identity_expansion(
    mastermind_scope: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ROOT_ID", "root-1")
    monkeypatch.delenv("POOL_ORCHESTRATOR_ID", raising=False)
    monkeypatch.delenv("POOL_PARENT_RUN_ID", raising=False)
    monkeypatch.delenv("POOL_TASK_CLASS", raising=False)
    command = (
        "POOL_ORCHESTRATOR_ID=$ROOT_ID POOL_PARENT_RUN_ID=parent-1 "
        "POOL_TASK_CLASS=review pool run grok bounded /tmp grok-4.6"
    )
    with pytest.raises(SystemExit):
        guard.guard_bash(_payload(mastermind_scope, command), {"command": command})
    output = _emitted(capsys)
    assert output["permissionDecision"] == "deny"
    assert "POOL_ORCHESTRATOR_ID" in output["permissionDecisionReason"]


def test_guard_denies_dynamic_command_substitution_root(
    mastermind_scope: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in ("POOL_ORCHESTRATOR_ID", "POOL_PARENT_RUN_ID", "POOL_TASK_CLASS"):
        monkeypatch.delenv(name, raising=False)
    command = (
        "POOL_ORCHESTRATOR_ID=$(uuidgen) POOL_PARENT_RUN_ID=parent-1 "
        "POOL_TASK_CLASS=review pool run grok bounded /tmp grok-4.6"
    )
    with pytest.raises(SystemExit):
        guard.guard_bash(_payload(mastermind_scope, command), {"command": command})
    output = _emitted(capsys)
    assert output["permissionDecision"] == "deny"
    assert "POOL_ORCHESTRATOR_ID" in output["permissionDecisionReason"]


def test_guard_denies_direct_remote_sub_wrapper_without_root_identity(
    mastermind_scope: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in ("POOL_ORCHESTRATOR_ID", "POOL_PARENT_RUN_ID", "POOL_TASK_CLASS"):
        monkeypatch.delenv(name, raising=False)
    command = (
        "/opt/mastermind/ext/remote_sub.sh ubuntu2 grok /tmp/packet.txt "
        "/home/ubuntu2/lanes/repo grok-4.6"
    )
    with pytest.raises(SystemExit):
        guard.guard_bash(_payload(mastermind_scope, command), {"command": command})
    output = _emitted(capsys)
    assert output["permissionDecision"] == "deny"
    assert "Fabric root-budget guard" in output["permissionDecisionReason"]


def test_guard_denies_direct_slot_launcher_without_root_identity(
    mastermind_scope: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in ("POOL_ORCHESTRATOR_ID", "POOL_PARENT_RUN_ID", "POOL_TASK_CLASS"):
        monkeypatch.delenv(name, raising=False)
    command = (
        "python3 /opt/mastermind/ext/slot.py grok -- "
        "grok -p bounded --output-format plain"
    )
    with pytest.raises(SystemExit):
        guard.guard_bash(_payload(mastermind_scope, command), {"command": command})
    output = _emitted(capsys)
    assert output["permissionDecision"] == "deny"
    assert "Fabric root-budget guard" in output["permissionDecisionReason"]


def test_guard_does_not_treat_wrapper_inspection_as_launch(
    mastermind_scope: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in ("POOL_ORCHESTRATOR_ID", "POOL_PARENT_RUN_ID", "POOL_TASK_CLASS"):
        monkeypatch.delenv(name, raising=False)
    for command in (
        "grep -n slot.py docs/runbook.md",
        "cat /opt/mastermind/ext/sub.sh",
        "/opt/mastermind/ext/sub.sh __glm_memory _ /tmp glm-5.3",
        "/opt/mastermind/ext/sub.sh __launch_plan glm /tmp",
    ):
        guard.guard_bash(_payload(mastermind_scope, command), {"command": command})
    assert capsys.readouterr().out == ""


def test_guard_allows_fabric_launch_with_explicit_root_identity(
    mastermind_scope: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in ("POOL_ORCHESTRATOR_ID", "POOL_PARENT_RUN_ID", "POOL_TASK_CLASS"):
        monkeypatch.delenv(name, raising=False)
    command = (
        "POOL_ORCHESTRATOR_ID=root-1 POOL_PARENT_RUN_ID=root-1 "
        "POOL_TASK_CLASS=review pool remote mini2 glm /tmp/packet.txt "
        "/Users/mini2/lanes/repos/Mastermind glm-5.3"
    )
    guard.guard_bash(_payload(mastermind_scope, command), {"command": command})
    assert capsys.readouterr().out == ""


def test_guard_allows_env_prefixed_fabric_launch_with_complete_identity(
    mastermind_scope: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in ("POOL_ORCHESTRATOR_ID", "POOL_PARENT_RUN_ID", "POOL_TASK_CLASS"):
        monkeypatch.delenv(name, raising=False)
    command = (
        "env POOL_ORCHESTRATOR_ID=root-1 POOL_PARENT_RUN_ID=parent-1 "
        "POOL_TASK_CLASS=review pool run grok bounded /tmp grok-4.6"
    )
    guard.guard_bash(_payload(mastermind_scope, command), {"command": command})
    assert capsys.readouterr().out == ""


def test_guard_allows_fabric_launch_with_inherited_root_identity(
    mastermind_scope: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("POOL_ORCHESTRATOR_ID", "root-1")
    monkeypatch.setenv("POOL_PARENT_RUN_ID", "parent-1")
    monkeypatch.setenv("POOL_TASK_CLASS", "execute")
    command = 'pool run grok "bounded task" /tmp grok-4.6'
    guard.guard_bash(_payload(mastermind_scope, command), {"command": command})
    assert capsys.readouterr().out == ""


def test_guard_does_not_treat_pool_observation_as_launch(
    mastermind_scope: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in ("POOL_ORCHESTRATOR_ID", "POOL_PARENT_RUN_ID", "POOL_TASK_CLASS"):
        monkeypatch.delenv(name, raising=False)
    command = "pool status"
    guard.guard_bash(_payload(mastermind_scope, command), {"command": command})
    assert capsys.readouterr().out == ""


def test_guard_denies_foreground_watch_at_polite_interval(
    mastermind_scope: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit):
        guard.guard_bash(
            _payload(
                mastermind_scope,
                "gh run watch 37180044700 --interval 150 --exit-status",
            ),
            {
                "command": "gh run watch 37180044700 --interval 150 --exit-status"
            },
        )
    output = _emitted(capsys)
    assert output["permissionDecision"] == "deny"
    assert "foreground GitHub watch" in output["permissionDecisionReason"]
    assert "run_in_background=true" in output["permissionDecisionReason"]


def test_guard_allows_background_watcher_and_orders_forward_work(
    mastermind_scope: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    command = "gh run watch 37180044700 --interval 150 --exit-status"
    with pytest.raises(SystemExit):
        guard.guard_bash(
            _payload(mastermind_scope, command, background=True),
            {"command": command, "run_in_background": True},
        )
    output = _emitted(capsys)
    assert "permissionDecision" not in output
    assert "CI WATCHER ARMED ASYNC" in output["additionalContext"]
    assert "Immediately start the next highest-value independent authorized project lane" in output["additionalContext"]


def test_guard_denies_foreground_ci_sleep_poll_loop(
    mastermind_scope: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    command = "for i in 1 2 3; do gh pr checks 8413; sleep 300; done"
    with pytest.raises(SystemExit):
        guard.guard_bash(
            _payload(mastermind_scope, command),
            {"command": command},
        )
    output = _emitted(capsys)
    assert output["permissionDecision"] == "deny"
    assert "CI status + sleep/poll loop" in output["permissionDecisionReason"]


def test_guard_blocks_repeat_single_status_read_but_not_first(
    mastermind_scope: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    command = "gh pr checks 8413"
    tool_input = {"command": command}
    guard.guard_bash(_payload(mastermind_scope, command), tool_input)
    assert capsys.readouterr().out == ""

    with pytest.raises(SystemExit):
        guard.guard_bash(_payload(mastermind_scope, command), tool_input)
    output = _emitted(capsys)
    assert output["permissionDecision"] == "deny"
    assert "redundant status read" in output["permissionDecisionReason"]
    assert "continue another independent authorized project lane" in output["permissionDecisionReason"]


def test_guard_does_not_share_cooldown_across_independent_sessions(
    mastermind_scope: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    command = "gh pr checks 8413 -R mastermindx-market-intelligence/macro"
    tool_input = {"command": command}

    guard.guard_bash(
        _payload(mastermind_scope, command, session_id="session-a"),
        tool_input,
    )
    guard.guard_bash(
        _payload(mastermind_scope, command, session_id="session-b"),
        tool_input,
    )

    assert capsys.readouterr().out == ""


def test_general_pr_view_remains_available_for_effect_readback(
    mastermind_scope: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A CI rate guard must not block post-mutation reconciliation reads."""
    command = "gh pr view 8413 --json state,headRefOid,labels"

    guard.guard_bash(_payload(mastermind_scope, command), {"command": command})
    guard.guard_bash(_payload(mastermind_scope, command), {"command": command})

    assert capsys.readouterr().out == ""


def test_repeat_cooldown_is_repo_scoped_for_same_pr_number(
    mastermind_scope: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    macro = "gh pr checks 8413 -R mastermindx-market-intelligence/macro"
    mastermind = "gh pr checks 8413 -R mastermindx-market-intelligence/Mastermind"

    guard.guard_bash(_payload(mastermind_scope, macro), {"command": macro})
    guard.guard_bash(_payload(mastermind_scope, mastermind), {"command": mastermind})

    assert capsys.readouterr().out == ""


def test_guard_is_inert_outside_mastermind_scope(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    home = tmp_path / "home"
    cwd = tmp_path / "unrelated"
    cwd.mkdir()
    monkeypatch.setenv("HOME", str(home))
    command = "gh run watch 123456 --interval 150"
    guard.guard_bash(_payload(cwd, command), {"command": command})
    assert capsys.readouterr().out == ""


def _accepted_native_codex_config(*, direct_message: bool = True, tools_complete: bool = True) -> str:
    denied = ('"send_message_to_thread", "create_thread", '
              '"fork_thread", "handoff_thread"')
    if not tools_complete:
        denied = '"create_thread", "fork_thread", "handoff_thread"'
    return (
        'model = "gpt-6.1-sol"\n'
        '[agents]\n'
        'enabled = true\n'
        'max_concurrent_threads_per_session = 2\n'
        'default_subagent_model = "gpt-5.6-terra"\n'
        '[features]\n'
        'hooks = true\n'
        '[features.multi_agent_v2]\n'
        'enabled = true\n'
        'max_concurrent_threads_per_session = 2\n'
        'disable_direct_message = ' + ('true' if direct_message else 'false') + '\n'
        '[plugins."codex-app-tools@openai-bundled".mcp_servers.codex_app]\n'
        'enabled = true\n'
        f'disabled_tools = [{denied}]\n'
    )


def test_accepted_october_reset_config_survives_apply_and_verify(tmp_path: Path) -> None:
    """The managed hook deployment cannot undo the accepted isolation reset."""
    home = tmp_path / "home"
    _seed_home(home)
    path = home / ".codex" / "config.toml"
    original = _accepted_native_codex_config()
    path.write_text(original, encoding="utf-8")
    first = apply_policy(home)
    assert first["state"] == "READY"
    assert path.read_text(encoding="utf-8") == original
    assert verify_policy(home)["state"] == "READY"
    again = apply_policy(home)
    assert again["state"] == "READY"
    assert path.read_text(encoding="utf-8") == original


@pytest.mark.parametrize("guard", ["direct_message", "disabled_tool", "missing_multi"])
def test_unsafe_enabled_native_profile_is_refused_before_any_write(
    tmp_path: Path, guard: str,
) -> None:
    home = tmp_path / "home"
    _seed_home(home)
    path = home / ".codex" / "config.toml"
    if guard == "direct_message":
        raw = _accepted_native_codex_config(direct_message=False)
    elif guard == "disabled_tool":
        raw = _accepted_native_codex_config(tools_complete=False)
    else:
        raw = _accepted_native_codex_config().replace(
            'disable_direct_message = true\n', ''
        )
    path.write_text(raw, encoding="utf-8")
    instructions = (home / ".codex" / "AGENTS.md").read_bytes()
    with pytest.raises(OrchestratorPolicyError, match="native|isolat|message"):
        apply_policy(home)
    assert path.read_text(encoding="utf-8") == raw
    assert (home / ".codex" / "AGENTS.md").read_bytes() == instructions
    assert not (home / ".codex" / "hooks").exists()
    assert not (home / ".claude" / "hooks").exists()


@pytest.mark.parametrize("guard", ["direct_message", "disabled_tool"])
def test_verify_cannot_report_ready_after_native_isolation_is_downgraded(
    tmp_path: Path, guard: str,
) -> None:
    home = tmp_path / "home"
    _seed_home(home)
    path = home / ".codex" / "config.toml"
    path.write_text(_accepted_native_codex_config(), encoding="utf-8")
    assert apply_policy(home)["state"] == "READY"
    if guard == "direct_message":
        path.write_text(_accepted_native_codex_config(direct_message=False), encoding="utf-8")
    else:
        path.write_text(_accepted_native_codex_config(tools_complete=False), encoding="utf-8")
    verified = verify_policy(home)
    assert verified["state"] == "DRIFT"
    assert "codex_config.native_message_isolation" in verified["issues"]


def test_existing_enabled_cap4_is_never_silently_downgraded(tmp_path: Path) -> None:
    home = tmp_path / "home"
    _seed_home(home)
    config = home / ".codex" / "config.toml"
    before = config.read_text()
    assert "enabled = false" in before
    config.write_text(before.replace("enabled = false", "enabled = true"))
    unacceptable = config.read_bytes()
    with pytest.raises(OrchestratorPolicyError, match="Codex native capacity differs"):
        apply_policy(home)
    assert config.read_bytes() == unacceptable
    assert not (home / ".codex" / "hooks").exists()
    assert not (home / ".agents").exists()
    assert not (home / ".claude" / "hooks").exists()
    assert not (home / ".claude" / "skills").exists()


# --- WO-11: engine-independent ExecutionBinding launch guard -------------------
#
# The four required refusal cases (missing binding, stale fence, provider
# substitution, unaccounted descendant) plus the scoped-arming and
# server-derived-projection invariants. Bindings are built with the REAL
# WO-02 contract and mirror the WO-14 issuer's claim_payload shape, proving
# the stdlib-only deployment guard validates what the broker actually issues.

_SHARED_LAUNCH = (
    'POOL_ORCHESTRATOR_ID=root-orch-1 POOL_PARENT_RUN_ID=hermes-run-7 '
    'POOL_TASK_CLASS=code pool run glm "bounded task" /tmp glm-5.3'
)


@pytest.fixture()
def shared_placement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Path:
    home = tmp_path / "home"
    cwd = home / "lanes" / "work"
    cwd.mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("MASTERMIND_CI_POLL_STATE_DIR", str(tmp_path / "poll-state"))
    monkeypatch.setenv("MASTERMIND_SHARED_PLACEMENT", "1")
    # r2 N-4: the owner positively asserts the receipt-channel owner uids.
    monkeypatch.setenv(
        "MASTERMIND_PLACEMENT_RECEIPT_OWNER_UIDS", str(os.geteuid())
    )
    # The placement owner runs as its own service account: simulate a fenced
    # principal whose uid/groups do NOT own the test's receipt files (the
    # real-principal case is exercised by the M-2 forge/replay tests).
    monkeypatch.setattr(
        guard,
        "_principal_ids",
        lambda: (os.geteuid() + 4242, frozenset()),
        raising=False,
    )
    for name in (
        "POOL_EXECUTION_BINDING",
        "MASTERMIND_PLACEMENT_RECEIPT",
        "MASTERMIND_PLACEMENT_RECEIPT_DIGEST",
        "POOL_ORCHESTRATOR_ID",
        "POOL_PARENT_RUN_ID",
        "POOL_TASK_CLASS",
    ):
        monkeypatch.delenv(name, raising=False)
    return cwd


def _binding(**over) -> dict[str, object]:
    row: dict[str, object] = {
        "root_run_ref": "hermes-root-1",
        "immediate_parent_run_ref": "hermes-run-7",
        "logical_child_key": "child-1",
        "request_digest": "a" * 64,
        "effective_complexity": "C1_ROUTINE_BOUNDED",
        "original_root_orchestrator_ref": "root-orch-1",
        "task_kind": "code",
        "job_ref": "job-1",
        "attempt_ref": "attempt-1",
        "provider_ref": "codex",
        "pool_ref": "glm",
        "host_id": "ubuntu0",
        "worker_id": "worker-a",
        "assignment_generation": 1,
        "fence_counter": 2,
    }
    row.update(over)
    return ExecutionBinding.from_dict(row).to_dict()


def _receipt(binding: dict[str, object], **over) -> dict[str, object]:
    row: dict[str, object] = {
        "schema": guard.PLACEMENT_RECEIPT_SCHEMA,
        "execution_binding": binding,
        "fence_counter": binding["fence_counter"],
        "attempt_ref": binding["attempt_ref"],
        "lease_state": "HELD",
        "lease_expires_at_ms": 4_102_444_800_000,
    }
    row.update(over)
    return row


def _install(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    binding: dict[str, object],
    *,
    receipt: dict[str, object] | None = None,
    env_binding: dict[str, object] | str | None = None,
) -> None:
    path = tmp_path / "placement-receipt.json"
    path.write_text(
        json.dumps(receipt if receipt is not None else _receipt(binding)),
        encoding="utf-8",
    )
    monkeypatch.setenv("MASTERMIND_PLACEMENT_RECEIPT", str(path))
    if env_binding is None:
        env_binding = binding
    monkeypatch.setenv(
        "POOL_EXECUTION_BINDING",
        env_binding if isinstance(env_binding, str) else json.dumps(env_binding),
    )


def _guard_launch(cwd: Path, command: str = _SHARED_LAUNCH) -> None:
    guard.guard_bash(_payload(cwd, command), {"command": command})


# --- required refusal 1: missing binding ---------------------------------------


def test_shared_placement_paid_launch_without_binding_is_refused(
    shared_placement: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _install(monkeypatch, tmp_path, _binding(), env_binding="")
    monkeypatch.delenv("POOL_EXECUTION_BINDING", raising=False)

    with pytest.raises(SystemExit):
        _guard_launch(shared_placement)
    output = _emitted(capsys)
    assert output["permissionDecision"] == "deny"
    assert "no" in output["permissionDecisionReason"]
    assert "broker-issued ExecutionBinding.v1" in output["permissionDecisionReason"]

    # Owner truth unavailable is equally refusing: never launch while
    # placement truth is uncertain (advisory-only fallback law).
    monkeypatch.delenv("MASTERMIND_PLACEMENT_RECEIPT", raising=False)
    monkeypatch.setenv("POOL_EXECUTION_BINDING", json.dumps(_binding()))
    with pytest.raises(SystemExit):
        _guard_launch(shared_placement)
    output = _emitted(capsys)
    assert output["permissionDecision"] == "deny"
    assert "placement receipt" in output["permissionDecisionReason"]
    assert "Never launch a paid child" in output["permissionDecisionReason"]


def test_shared_placement_native_delegation_without_binding_is_refused(
    shared_placement: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # The binding gate runs BEFORE the native-child routing fences, so a
    # delegation (Agent/Task) is refused on the binding, not the model.
    with pytest.raises(SystemExit):
        guard.guard_native_child({"model": "opus", "prompt": "help"})
    output = _emitted(capsys)
    assert output["permissionDecision"] == "deny"
    assert "broker-issued ExecutionBinding.v1" in output["permissionDecisionReason"]


def test_shared_placement_malformed_binding_is_refused(
    shared_placement: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    binding = _binding()
    _install(monkeypatch, tmp_path, binding, env_binding="{not json")
    with pytest.raises(SystemExit):
        _guard_launch(shared_placement)
    assert "not valid JSON" in _emitted(capsys)["permissionDecisionReason"]

    wrong_schema = dict(binding, schema="ExecutionBinding.v2")
    _install(monkeypatch, tmp_path, binding, env_binding=wrong_schema)
    with pytest.raises(SystemExit):
        _guard_launch(shared_placement)
    assert "schema must be ExecutionBinding.v1" in _emitted(capsys)[
        "permissionDecisionReason"
    ]

    bad_digest = dict(binding, request_digest="z" * 8)
    _install(monkeypatch, tmp_path, binding, env_binding=bad_digest)
    with pytest.raises(SystemExit):
        _guard_launch(shared_placement)
    assert "request_digest" in _emitted(capsys)["permissionDecisionReason"]


# --- required refusal 2: stale fence -------------------------------------------


def test_shared_placement_paid_launch_with_stale_fence_is_refused(
    shared_placement: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    # The owner's lease moved to fence 3; the session still holds fence 2.
    current = _binding(fence_counter=3)
    stale = _binding(fence_counter=2)
    _install(
        monkeypatch, tmp_path, stale,
        receipt=_receipt(current, fence_counter=3),
    )
    with pytest.raises(SystemExit):
        _guard_launch(shared_placement)
    output = _emitted(capsys)
    assert output["permissionDecision"] == "deny"
    assert "stale fence" in output["permissionDecisionReason"]
    assert "fence 3" in output["permissionDecisionReason"]

    # A released lease refuses even with matching fences.
    _install(
        monkeypatch, tmp_path, current,
        receipt=_receipt(current, lease_state="RELEASED"),
    )
    with pytest.raises(SystemExit):
        _guard_launch(shared_placement)
    assert "stale fence" in _emitted(capsys)["permissionDecisionReason"]

    # An expired lease refuses even while marked HELD.
    _install(
        monkeypatch, tmp_path, current,
        receipt=_receipt(current, lease_expires_at_ms=1),
    )
    with pytest.raises(SystemExit):
        _guard_launch(shared_placement)
    reason = _emitted(capsys)["permissionDecisionReason"]
    assert "stale fence" in reason and "lease expired" in reason


# --- required refusal 3: provider substitution ---------------------------------


@pytest.mark.parametrize(
    "command, expected",
    [
        (
            "POOL_ORCHESTRATOR_ID=root-orch-1 POOL_PARENT_RUN_ID=hermes-run-7 "
            "POOL_TASK_CLASS=code pool run grok bounded /tmp grok-4.6",
            "provider substitution",
        ),
        # REVIEW_2329 r3 B-1: an interpreter running the slot wrapper is
        # refused WHOLESALE as unobservable — its program text cannot be
        # read, so a substitution inside it is not this gate's to judge.
        (
            "POOL_ORCHESTRATOR_ID=root-orch-1 POOL_PARENT_RUN_ID=hermes-run-7 "
            "POOL_TASK_CLASS=code python3 /opt/mastermind/ext/slot.py grok -- "
            "grok -p bounded --output-format plain",
            "unobservable launch",
        ),
        (
            "POOL_ORCHESTRATOR_ID=root-orch-1 POOL_PARENT_RUN_ID=hermes-run-7 "
            "POOL_TASK_CLASS=code /opt/mastermind/ext/remote_sub.sh ubuntu2 grok "
            "/tmp/packet.txt /home/ubuntu2/lanes/repo grok-4.6",
            "provider substitution",
        ),
    ],
    ids=["pool-run", "slot-py", "remote-sub"],
)
def test_shared_placement_paid_launch_substituting_provider_is_refused(
    shared_placement: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    command: str,
    expected: str,
) -> None:
    # The binding reserved pool glm / provider codex; the launch asks grok.
    _install(monkeypatch, tmp_path, _binding())
    with pytest.raises(SystemExit):
        _guard_launch(shared_placement, command)
    output = _emitted(capsys)
    assert output["permissionDecision"] == "deny"
    assert expected in output["permissionDecisionReason"]
    if expected == "provider substitution":
        assert "'grok'" in output["permissionDecisionReason"]


# --- required refusal 4: unaccounted descendant --------------------------------


def test_shared_placement_launch_of_unaccounted_descendant_is_refused(
    shared_placement: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    # The owner's current assignment covers child-1 only; the session swaps
    # in a binding for child-2 to squeeze an extra paid child under the
    # same lease.
    _install(monkeypatch, tmp_path, _binding())
    monkeypatch.setenv(
        "POOL_EXECUTION_BINDING",
        json.dumps(_binding(logical_child_key="child-2")),
    )
    with pytest.raises(SystemExit):
        _guard_launch(shared_placement)
    output = _emitted(capsys)
    assert output["permissionDecision"] == "deny"
    assert "unaccounted descendant" in output["permissionDecisionReason"]
    assert "logical_child_key" in output["permissionDecisionReason"]

    # Native delegations are refused the same way.
    with pytest.raises(SystemExit):
        guard.guard_native_child({"model": "opus", "prompt": "help"})
    assert "unaccounted descendant" in _emitted(capsys)[
        "permissionDecisionReason"
    ]


# --- invariants: scoped arming, server-derived projections, allow path ---------


def test_shared_placement_gate_auto_arms_when_a_binding_is_projected(
    shared_placement: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    # A projected binding alone arms the gate: the owner cannot be bypassed
    # by leaving MASTERMIND_SHARED_PLACEMENT unset.
    monkeypatch.delenv("MASTERMIND_SHARED_PLACEMENT", raising=False)
    current = _binding(fence_counter=3)
    _install(
        monkeypatch, tmp_path, _binding(fence_counter=2),
        receipt=_receipt(current, fence_counter=3),
    )
    with pytest.raises(SystemExit):
        _guard_launch(shared_placement)
    assert "stale fence" in _emitted(capsys)["permissionDecisionReason"]


def test_unarmed_sessions_keep_the_legacy_launch_checks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Scoped arming (OQ-7): a session the owner did NOT arm keeps exactly
    # the legacy behavior — no binding required, identity checks unchanged.
    home = tmp_path / "home"
    cwd = home / "lanes" / "work"
    cwd.mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("MASTERMIND_CI_POLL_STATE_DIR", str(tmp_path / "poll-state"))
    for name in (
        "MASTERMIND_SHARED_PLACEMENT",
        "POOL_EXECUTION_BINDING",
        "MASTERMIND_PLACEMENT_RECEIPT",
    ):
        monkeypatch.delenv(name, raising=False)
    command = (
        "POOL_ORCHESTRATOR_ID=root-1 POOL_PARENT_RUN_ID=parent-1 "
        "POOL_TASK_CLASS=review pool run grok bounded /tmp grok-4.6"
    )
    guard.guard_bash(_payload(cwd, command), {"command": command})
    assert capsys.readouterr().out == ""


def test_shared_placement_launch_rebinding_server_derived_projection_is_refused(
    shared_placement: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _install(monkeypatch, tmp_path, _binding())
    command = (
        "POOL_ORCHESTRATOR_ID=root-other POOL_PARENT_RUN_ID=hermes-run-7 "
        "POOL_TASK_CLASS=code pool run glm \"bounded task\" /tmp glm-5.3"
    )
    with pytest.raises(SystemExit):
        _guard_launch(shared_placement, command)
    output = _emitted(capsys)
    assert output["permissionDecision"] == "deny"
    assert "server-derived projection" in output["permissionDecisionReason"]
    assert "POOL_ORCHESTRATOR_ID" in output["permissionDecisionReason"]

    # Inherited environment identity is held to the same projection
    # (no explicit assignment in the command, so the env value is effective).
    monkeypatch.setenv("POOL_PARENT_RUN_ID", "parent-forged")
    inherited = (
        "POOL_ORCHESTRATOR_ID=root-orch-1 POOL_TASK_CLASS=code "
        'pool run glm "bounded task" /tmp glm-5.3'
    )
    with pytest.raises(SystemExit):
        _guard_launch(shared_placement, inherited)
    assert "POOL_PARENT_RUN_ID" in _emitted(capsys)["permissionDecisionReason"]


def test_shared_placement_launch_matching_current_binding_is_allowed(
    shared_placement: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _install(monkeypatch, tmp_path, _binding())

    # Explicit literal assignments equal to the projections pass.
    _guard_launch(shared_placement)
    assert capsys.readouterr().out == ""

    # Inherited environment identity equal to the projections passes too.
    monkeypatch.setenv("POOL_ORCHESTRATOR_ID", "root-orch-1")
    monkeypatch.setenv("POOL_PARENT_RUN_ID", "hermes-run-7")
    monkeypatch.setenv("POOL_TASK_CLASS", "code")
    command = 'pool run glm "bounded task" /tmp glm-5.3'
    guard.guard_bash(_payload(shared_placement, command), {"command": command})
    assert capsys.readouterr().out == ""


# --- rework r2: regression tests for the distinct reviewer's MAJOR findings ---


@pytest.mark.parametrize(
    "command",
    [
        # M-1 (a): duplicate prefix assignment — the shell applies the LAST
        # one, so the child runs as root-other while the first is benign.
        "POOL_ORCHESTRATOR_ID=root-orch-1 POOL_ORCHESTRATOR_ID=root-other "
        "POOL_PARENT_RUN_ID=hermes-run-7 POOL_TASK_CLASS=code "
        'pool run glm "bounded task" /tmp glm-5.3',
        # M-1 (b): duplicate parent assignment re-parents the launch.
        "POOL_ORCHESTRATOR_ID=root-orch-1 POOL_PARENT_RUN_ID=hermes-run-7 "
        "POOL_PARENT_RUN_ID=parent-forged POOL_TASK_CLASS=code "
        'pool run glm "bounded task" /tmp glm-5.3',
        # M-1 (c): nested export inside a quoted sub-command overrides the
        # benign prefix assignment at runtime.
        "POOL_ORCHESTRATOR_ID=root-orch-1 POOL_PARENT_RUN_ID=hermes-run-7 "
        "POOL_TASK_CLASS=code bash -c 'export POOL_ORCHESTRATOR_ID=root-other; "
        'pool run glm "bounded task" /tmp glm-5.3\'',
        # M-1 (d): a benign explicit value followed by a dynamic one.
        "POOL_ORCHESTRATOR_ID=root-orch-1 POOL_ORCHESTRATOR_ID=$OTHER "
        "POOL_PARENT_RUN_ID=hermes-run-7 POOL_TASK_CLASS=code "
        'pool run glm "bounded task" /tmp glm-5.3',
    ],
    ids=["dup-root", "dup-parent", "nested-export", "dup-dynamic"],
)
def test_m1_every_identity_assignment_is_held_to_the_projection(
    shared_placement: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    command: str,
) -> None:
    _install(monkeypatch, tmp_path, _binding())
    with pytest.raises(SystemExit):
        _guard_launch(shared_placement, command)
    output = _emitted(capsys)
    assert output["permissionDecision"] == "deny"
    reason = output["permissionDecisionReason"]
    assert "server-derived projection" in reason
    assert "assignments of POOL_" in reason

    # The helper itself reports every occurrence in positional order.
    assert guard._command_assignments(
        "A=1 A=2 bash -c 'export A=3; x'", "A"
    ) == ["1", "2", "3"]

    # Duplicate assignments that all equal the projection remain allowed:
    # the check is on identity, not on spelling.
    same = (
        "POOL_ORCHESTRATOR_ID=root-orch-1 POOL_ORCHESTRATOR_ID=root-orch-1 "
        "POOL_PARENT_RUN_ID=hermes-run-7 POOL_TASK_CLASS=code "
        'pool run glm "bounded task" /tmp glm-5.3'
    )
    _guard_launch(shared_placement, same)
    assert capsys.readouterr().out == ""


def test_m1_legacy_rebind_check_judges_every_root_assignment(
    mastermind_scope: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Unarmed session: the pre-existing rebind guard used the FIRST
    # assignment; a benign first value followed by a forged one re-rooted
    # the child under approval.
    for name in ("MASTERMIND_SHARED_PLACEMENT", "POOL_EXECUTION_BINDING"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("POOL_ORCHESTRATOR_ID", "root-1")
    command = (
        "POOL_ORCHESTRATOR_ID=root-1 POOL_ORCHESTRATOR_ID=root-2 "
        "POOL_PARENT_RUN_ID=parent-1 POOL_TASK_CLASS=review "
        "pool run grok bounded /tmp grok-4.6"
    )
    with pytest.raises(SystemExit):
        guard.guard_bash(_payload(mastermind_scope, command), {"command": command})
    assert "may not be rebound" in _emitted(capsys)["permissionDecisionReason"]


def test_m2_pinned_receipt_refuses_rewritten_or_replayed_receipt(
    shared_placement: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import hashlib

    # Owner projects the binding AND the digest of the receipt it wrote.
    current = _binding(fence_counter=3)
    stale = _binding(fence_counter=2)
    _install(monkeypatch, tmp_path, stale, receipt=_receipt(current, fence_counter=3))
    path = Path(os.environ["MASTERMIND_PLACEMENT_RECEIPT"])
    monkeypatch.setenv(
        "MASTERMIND_PLACEMENT_RECEIPT_DIGEST",
        hashlib.sha256(path.read_bytes()).hexdigest(),
    )
    # Honest receipt: refused as a stale fence (lease moved to 3).
    with pytest.raises(SystemExit):
        _guard_launch(shared_placement)
    assert "stale fence" in _emitted(capsys)["permissionDecisionReason"]

    # The fenced principal rewrites the receipt to agree with its stale
    # binding (fence 2, HELD, far-future expiry) — identical content to a
    # forged/replayed self-consistent pair. The pin refuses it before any
    # receipt field is trusted.
    path.write_text(json.dumps(_receipt(stale)), encoding="utf-8")
    with pytest.raises(SystemExit):
        _guard_launch(shared_placement)
    reason = _emitted(capsys)["permissionDecisionReason"]
    assert "receipt integrity" in reason
    assert "rewritten, replayed or re-projected" in reason

    # Native delegations go through the same pinned receipt.
    with pytest.raises(SystemExit):
        guard.guard_native_child({"model": "opus", "prompt": "help"})
    assert "receipt integrity" in _emitted(capsys)["permissionDecisionReason"]

    # A malformed pin is a refusal, never a fall-through to the unpinned mode.
    monkeypatch.setenv("MASTERMIND_PLACEMENT_RECEIPT_DIGEST", "not-a-digest")
    with pytest.raises(SystemExit):
        _guard_launch(shared_placement)
    assert "64-char hex" in _emitted(capsys)["permissionDecisionReason"]

    # The pinned, owner-written current receipt still allows the launch.
    path.write_text(json.dumps(_receipt(current)), encoding="utf-8")
    monkeypatch.setenv("POOL_EXECUTION_BINDING", json.dumps(current))
    monkeypatch.setenv(
        "MASTERMIND_PLACEMENT_RECEIPT_DIGEST",
        hashlib.sha256(path.read_bytes()).hexdigest(),
    )
    _guard_launch(shared_placement)
    assert capsys.readouterr().out == ""

    # The pin is defence in depth; the trust basis is the owner-only
    # receipt channel, and what remains trusting is stated, not implied.
    doc = guard.validate_execution_binding.__doc__ or ""
    assert "owner-only channel" in doc and "OS uid boundary" in doc


def test_m2_receipt_internal_consistency_and_expiry_type_are_enforced(
    shared_placement: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    binding = _binding()
    # Top-level fence/attempt disagreeing with the embedded binding (m-4).
    _install(monkeypatch, tmp_path, binding, receipt=_receipt(binding, attempt_ref="attempt-9"))
    with pytest.raises(SystemExit):
        _guard_launch(shared_placement)
    assert "internally inconsistent" in _emitted(capsys)["permissionDecisionReason"]

    # A float expiry in the past no longer skips the expiry check (m-2).
    _install(monkeypatch, tmp_path, binding, receipt=_receipt(binding, lease_expires_at_ms=1.0))
    with pytest.raises(SystemExit):
        _guard_launch(shared_placement)
    assert "lease_expires_at_ms must be an integer" in _emitted(capsys)[
        "permissionDecisionReason"
    ]


@pytest.mark.parametrize(
    "command, expected",
    [
        # P3b: matching first launch, substituted second launch.
        (
            "POOL_ORCHESTRATOR_ID=root-orch-1 POOL_PARENT_RUN_ID=hermes-run-7 "
            "POOL_TASK_CLASS=code pool run glm a /tmp glm-5.3; "
            "pool run grok b /tmp grok-4.6",
            "provider substitution",
        ),
        # P3c: substituted first launch, matching later launch (regex
        # priority used to grab the later `pool run glm`).
        (
            "POOL_ORCHESTRATOR_ID=root-orch-1 POOL_PARENT_RUN_ID=hermes-run-7 "
            "POOL_TASK_CLASS=code /opt/mastermind/ext/sub.sh grok /tmp/p.txt "
            "/tmp grok-4.6; pool run glm a /tmp glm-5.3",
            "provider substitution",
        ),
        # P3d: decoy launch text inside an echo, real launch substituted.
        (
            'echo "pool run glm"; POOL_ORCHESTRATOR_ID=root-orch-1 '
            "POOL_PARENT_RUN_ID=hermes-run-7 POOL_TASK_CLASS=code "
            "/opt/mastermind/ext/sub.sh grok /tmp/p.txt /tmp grok-4.6",
            "provider substitution",
        ),
        # Two launches that BOTH match the reservation: one binding covers
        # exactly one attempt, so the second is an unaccounted descendant.
        (
            "POOL_ORCHESTRATOR_ID=root-orch-1 POOL_PARENT_RUN_ID=hermes-run-7 "
            "POOL_TASK_CLASS=code pool run glm a /tmp glm-5.3 && "
            "pool run glm b /tmp glm-5.3",
            "unaccounted descendant",
        ),
    ],
    ids=["second-substituted", "first-substituted", "echo-decoy", "two-matching"],
)
def test_m3_every_launch_in_a_compound_command_is_checked(
    shared_placement: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    command: str,
    expected: str,
) -> None:
    _install(monkeypatch, tmp_path, _binding())
    with pytest.raises(SystemExit):
        _guard_launch(shared_placement, command)
    output = _emitted(capsys)
    assert output["permissionDecision"] == "deny"
    assert expected in output["permissionDecisionReason"]

    # Token extraction is positional and per-launch.
    assert [token for _, token in guard.launch_provider_tokens(
        "sub.sh grok x; pool run glm y; python3 /x/slot.py minimax -- z"
    )] == ["grok", "glm", "minimax"]


def test_m4_launch_tokens_must_equal_the_reserved_pool_exactly(
    shared_placement: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _install(monkeypatch, tmp_path, _binding())  # pool glm / provider codex
    prefix = (
        "POOL_ORCHESTRATOR_ID=root-orch-1 POOL_PARENT_RUN_ID=hermes-run-7 "
        "POOL_TASK_CLASS=code "
    )
    # P3a: attacker-chosen composites with a reserved segment, and real
    # composites/provider names that are not the reserved pool: no
    # segment-wise acceptance — every one is a substitution.
    for token in (
        "glm-grok", "glm-deepseek", "codex-zebra", "glm_grok",
        "glm-codex", "codex-native", "codex", "go-claude",
    ):
        with pytest.raises(SystemExit):
            _guard_launch(shared_placement, f"{prefix}pool run {token} a /tmp m")
        reason = _emitted(capsys)["permissionDecisionReason"]
        assert "provider substitution" in reason and repr(token) in reason

    # The exact reserved pool passes, quoting does not matter.
    for token in ("glm", '"glm"', "GLM"):
        _guard_launch(shared_placement, f"{prefix}pool run {token} a /tmp m")
        assert capsys.readouterr().out == ""

    # A reservation of a composite pool admits exactly that composite.
    _install(monkeypatch, tmp_path, _binding(pool_ref="glm-codex"))
    _guard_launch(shared_placement, f"{prefix}sub.sh glm-codex task /tmp m")
    assert capsys.readouterr().out == ""
    with pytest.raises(SystemExit):
        _guard_launch(shared_placement, f"{prefix}sub.sh glm task /tmp m")
    assert "provider substitution" in _emitted(capsys)["permissionDecisionReason"]


@pytest.mark.parametrize(
    "launch",
    [
        "/opt/mastermind/ext/sub.sh zebra-glm task /tmp glm-5.3",  # P3e
        "/opt/mastermind/ext/sub.sh glm_x task /tmp glm-5.3",
        '/opt/mastermind/ext/sub.sh "grok" task /tmp grok-4.6',
        "/opt/mastermind/ext/remote_sub.sh ubuntu2 application p /tmp m",
        "/opt/mastermind/ext/slot.py deepseek -- run",
        "/opt/mastermind/ext/remote_sub.sh ubuntu2",
    ],
    ids=["off-list", "near-miss", "quoted-mode", "remote-off-list", "slot-off-list",
         "missing-mode"],
)
def test_m4_unknown_wrapper_modes_are_refused_never_ignored(
    shared_placement: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    launch: str,
) -> None:
    _install(monkeypatch, tmp_path, _binding())
    command = (
        "POOL_ORCHESTRATOR_ID=root-orch-1 POOL_PARENT_RUN_ID=hermes-run-7 "
        f"POOL_TASK_CLASS=code {launch}"
    )
    with pytest.raises(SystemExit):
        _guard_launch(shared_placement, command)
    reason = _emitted(capsys)["permissionDecisionReason"]
    assert "unknown wrapper mode" in reason or "provider substitution" in reason


def test_m4_off_list_wrapper_mode_is_observed_in_unarmed_sessions(
    mastermind_scope: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # P3e (unarmed): an off-list mode used to skip EVERY check; it is now an
    # observed launch held to the legacy identity law.
    for name in (
        "MASTERMIND_SHARED_PLACEMENT", "POOL_EXECUTION_BINDING",
        "POOL_ORCHESTRATOR_ID", "POOL_PARENT_RUN_ID", "POOL_TASK_CLASS",
    ):
        monkeypatch.delenv(name, raising=False)
    command = "/opt/mastermind/ext/sub.sh zebra-glm task /tmp glm-5.3"
    with pytest.raises(SystemExit):
        guard.guard_bash(_payload(mastermind_scope, command), {"command": command})
    assert "Fabric root-budget guard" in _emitted(capsys)["permissionDecisionReason"]


# --- rework r3: the orchestrator-ruled strengthening of M-1..M-3 ------------


@pytest.mark.parametrize(
    "command",
    [
        # env -i clears the inherited root/parent: the child re-roots.
        "env -i POOL_TASK_CLASS=code pool run glm a /tmp glm-5.3",
        # env -u / unset / export -n remove the projected identity.
        "env -u POOL_ORCHESTRATOR_ID pool run glm a /tmp glm-5.3",
        "env --unset=POOL_PARENT_RUN_ID pool run glm a /tmp glm-5.3",
        "unset POOL_ORCHESTRATOR_ID; pool run glm a /tmp glm-5.3",
        "export -n POOL_PARENT_RUN_ID; pool run glm a /tmp glm-5.3",
        # Assignment forms hidden from a plain NAME= scan.
        "env 'POOL_ORCHESTRATOR_ID=root-other' pool run glm a /tmp glm-5.3",
        'sh -c "POOL_ORCH""ESTRATOR_ID=root-other pool run glm a /tmp glm-5.3"',
        "POOL_ORCHESTRATOR_ID+=-x pool run glm a /tmp glm-5.3",
        "declare -x POOL_PARENT_RUN_ID=parent-forged; pool run glm a /tmp glm-5.3",
        "printf -v POOL_ORCHESTRATOR_ID root-other; pool run glm a /tmp glm-5.3",
        ": ${POOL_ORCHESTRATOR_ID:=root-other}; pool run glm a /tmp glm-5.3",
        # Environment changed outside lexical observation.
        'eval "$X"; pool run glm a /tmp glm-5.3',
        ". ./forged.env; pool run glm a /tmp glm-5.3",
        "BASH_ENV=./forged.env bash -c 'pool run glm a /tmp glm-5.3'",
        "export ${V}=root-other; pool run glm a /tmp glm-5.3",
    ],
)
def test_m1_identity_is_canonicalised_across_every_assignment_form(
    shared_placement: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    command: str,
) -> None:
    _install(monkeypatch, tmp_path, _binding())
    monkeypatch.setenv("POOL_ORCHESTRATOR_ID", "root-orch-1")
    monkeypatch.setenv("POOL_PARENT_RUN_ID", "hermes-run-7")
    monkeypatch.setenv("POOL_TASK_CLASS", "code")
    with pytest.raises(SystemExit):
        _guard_launch(shared_placement, command)
    reason = _emitted(capsys)["permissionDecisionReason"]
    assert "server-derived projection" in reason or "unobservable" in reason


def test_m1_canonical_identity_still_admits_faithful_launches(
    shared_placement: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _install(monkeypatch, tmp_path, _binding())
    monkeypatch.setenv("POOL_ORCHESTRATOR_ID", "root-orch-1")
    monkeypatch.setenv("POOL_PARENT_RUN_ID", "hermes-run-7")
    monkeypatch.setenv("POOL_TASK_CLASS", "code")
    for command in (
        # env -i followed by the projected identity is faithful.
        "env -i POOL_ORCHESTRATOR_ID=root-orch-1 POOL_PARENT_RUN_ID=hermes-run-7 "
        "POOL_TASK_CLASS=code pool run glm a /tmp glm-5.3",
        # Reads and bare re-exports of the inherited value change nothing.
        # (A computed read such as `echo "$VAR"` is refused as an
        # unobservable computed word per REVIEW_2329 r3 B-1, so the
        # read-decoy here is a bare re-export of both projections.)
        "export POOL_ORCHESTRATOR_ID; export POOL_PARENT_RUN_ID; "
        "pool run glm a /tmp glm-5.3",
        # Quoted literal equal to the projection.
        "env \"POOL_ORCHESTRATOR_ID=root-orch-1\" pool run glm a /tmp glm-5.3",
    ):
        _guard_launch(shared_placement, command)
        assert capsys.readouterr().out == "", command


def test_m2_receipt_the_fenced_principal_can_write_is_refused(
    shared_placement: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    # Reviewer P2a: the honest receipt says fence 3; the session holds fence
    # 2. Rewriting the receipt to fence 2 / HELD / far-future expiry used to
    # be ALLOWED. The receipt now must come from a path this principal
    # cannot write, so the forged file is refused before any field is read.
    real_ids = (os.geteuid(), frozenset({os.getegid(), *os.getgroups()}))
    current = _binding(fence_counter=3)
    stale = _binding(fence_counter=2)
    _install(monkeypatch, tmp_path, stale, receipt=_receipt(current, fence_counter=3))
    with pytest.raises(SystemExit):
        _guard_launch(shared_placement)
    assert "stale fence" in _emitted(capsys)["permissionDecisionReason"]

    monkeypatch.setattr(guard, "_principal_ids", lambda: real_ids)
    Path(os.environ["MASTERMIND_PLACEMENT_RECEIPT"]).write_text(
        json.dumps(_receipt(stale)), encoding="utf-8"
    )
    for launch in (
        lambda: _guard_launch(shared_placement),
        lambda: guard.guard_native_child({"model": "opus", "prompt": "help"}),
    ):
        with pytest.raises(SystemExit):
            launch()
        reason = _emitted(capsys)["permissionDecisionReason"]
        assert "not owner-authenticated" in reason
        assert "owned or writable by this session's principal" in reason

    # Reviewer P2b: replay of a prior session's self-consistent pair into a
    # principal-writable location is refused the same way.
    prior = _binding(fence_counter=1, attempt_ref="attempt-0")
    replay_dir = tmp_path / "replay"
    replay_dir.mkdir()
    _install(monkeypatch, replay_dir, prior)
    with pytest.raises(SystemExit):
        _guard_launch(shared_placement)
    assert "not owner-authenticated" in _emitted(capsys)["permissionDecisionReason"]


def test_m2_receipt_channel_checks_every_path_component(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real = (os.geteuid(), frozenset({os.getegid(), *os.getgroups()}))
    owner_file = Path("/etc/hosts")  # root-owned, root-owned ancestry
    if os.geteuid() == 0 or not owner_file.exists():
        pytest.skip("needs a non-root principal and a root-owned file")
    original = guard._principal_ids
    try:
        guard._principal_ids = lambda: real
        monkeypatch.setenv(
            "MASTERMIND_PLACEMENT_RECEIPT_OWNER_UIDS", str(os.geteuid())
        )
        assert guard._receipt_channel_problem(str(owner_file)) == ""
        # r2 N-4: without the owner-asserted allowlist the channel is no
        # longer defined positively and no path qualifies as owner-written.
        monkeypatch.delenv("MASTERMIND_PLACEMENT_RECEIPT_OWNER_UIDS")
        assert "allowlist" in guard._receipt_channel_problem(str(owner_file))
        monkeypatch.setenv(
            "MASTERMIND_PLACEMENT_RECEIPT_OWNER_UIDS", str(os.geteuid())
        )
        # A symlink the principal controls could be re-pointed at any
        # owner-written file (e.g. an older receipt): refused.
        link = tmp_path / "receipt.json"
        link.symlink_to(owner_file)
        assert "principal" in guard._receipt_channel_problem(str(link))
        assert guard._receipt_channel_problem(str(tmp_path / "absent"))
    finally:
        guard._principal_ids = original


def test_m3_every_wrapper_shape_is_enumerated_and_checked(
    shared_placement: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _install(monkeypatch, tmp_path, _binding())
    shapes = [
        "pool run glm a /tmp m",
        "pool remote ubuntu0 glm a /tmp m",
        "/opt/x/sub.sh glm a /tmp m",
        "/opt/x/remote_sub.sh ubuntu0 glm a /tmp m",
        "python3 /opt/x/slot.py glm -- run",
    ]
    command = " ; ".join(shapes + shapes)
    assert [token for _, token in guard.launch_provider_tokens(command)] == ["glm"] * 10
    prefix = (
        "POOL_ORCHESTRATOR_ID=root-orch-1 POOL_PARENT_RUN_ID=hermes-run-7 "
        "POOL_TASK_CLASS=code "
    )
    # Required shape 5 is a Python script: under shared placement the
    # interpreter is refused WHOLESALE as unobservable (REVIEW_2329 r3
    # B-1), so the direct-command allow/repeat legs use the other four.
    direct = [shape for shape in shapes if not shape.startswith("python3 ")]
    for shape in direct:  # each shape alone, matching: allowed
        _guard_launch(shared_placement, prefix + shape)
        assert capsys.readouterr().out == "", shape
    for shape in direct:  # repeated in one command: second is unaccounted
        with pytest.raises(SystemExit):
            _guard_launch(shared_placement, f"{prefix}{shape} && {shape}")
        assert "unaccounted descendant" in _emitted(capsys)["permissionDecisionReason"]
    # The interpreter-hosted slot wrapper cannot be attributed at all.
    with pytest.raises(SystemExit):
        _guard_launch(shared_placement, prefix + "python3 /opt/x/slot.py glm -- run")
    assert "unobservable launch" in _emitted(capsys)["permissionDecisionReason"]
    # A substituted launch anywhere in the command is found.
    with pytest.raises(SystemExit):
        _guard_launch(
            shared_placement,
            f"{prefix}pool run glm a /tmp m; true; true; /opt/x/remote_sub.sh h grok p",
        )
    assert "'grok'" in _emitted(capsys)["permissionDecisionReason"]
    # Wrapper source fed to a shell is not a visible invocation: refused.
    with pytest.raises(SystemExit):
        _guard_launch(shared_placement, f"{prefix}cat /opt/x/sub.sh | bash -s grok a")
    assert "unobservable launch" in _emitted(capsys)["permissionDecisionReason"]


def test_minor_heredoc_staged_wrapper_launch_is_judged_under_shared_placement(
    shared_placement: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    # Reviewer P4a (m-1): the staged script really contains `pool run grok`.
    _install(monkeypatch, tmp_path, _binding())
    command = (
        "cat > x.sh <<'EOF'\n"
        "POOL_ORCHESTRATOR_ID=root-orch-1 POOL_PARENT_RUN_ID=hermes-run-7 "
        "POOL_TASK_CLASS=code pool run grok b /tmp grok-4.6\nEOF\nbash x.sh"
    )
    with pytest.raises(SystemExit):
        _guard_launch(shared_placement, command)
    assert "'grok'" in _emitted(capsys)["permissionDecisionReason"]


def test_minor_binding_counters_are_required_and_generation_compared(
    shared_placement: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    # m-3 (P6e): a binding without fence_counter no longer passes as fence 0.
    binding = _binding()
    no_fence = {k: v for k, v in binding.items() if k != "fence_counter"}
    _install(
        monkeypatch, tmp_path, binding,
        env_binding=no_fence,
        receipt=_receipt(dict(binding, fence_counter=0), fence_counter=0),
    )
    with pytest.raises(SystemExit):
        _guard_launch(shared_placement)
    assert "fence_counter must be present" in _emitted(capsys)["permissionDecisionReason"]
    # n-2: assignment_generation is part of the owner's current assignment.
    _install(monkeypatch, tmp_path, binding, env_binding=dict(binding, assignment_generation=9))
    with pytest.raises(SystemExit):
        _guard_launch(shared_placement)
    assert "assignment_generation" in _emitted(capsys)["permissionDecisionReason"]
    # n-4: only the exact HELD state admits a launch.
    _install(monkeypatch, tmp_path, binding, receipt=_receipt(binding, lease_state="held "))
    with pytest.raises(SystemExit):
        _guard_launch(shared_placement)
    assert "stale fence" in _emitted(capsys)["permissionDecisionReason"]


def test_minor_native_delegation_allow_path(
    shared_placement: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    # m-5: with the owner projecting binding + identity, a native Opus
    # orchestration delegation passes the binding gate and the routing fence.
    _install(monkeypatch, tmp_path, _binding())
    monkeypatch.setenv("POOL_ORCHESTRATOR_ID", "root-orch-1")
    monkeypatch.setenv("POOL_PARENT_RUN_ID", "hermes-run-7")
    guard.guard_native_child({
        "model": "opus",
        "prompt": "ROUTE: ORCHESTRATION\nWHY OPUS: cross-module plan needs judgment",
    })
    assert capsys.readouterr().out == ""


# --- rework r4: round-2 review findings (N-1..N-4) ------------------------------

_NL = "\\\n"  # a literal backslash + newline: a POSIX line continuation

_IDENTITY_PREFIX = (
    "POOL_ORCHESTRATOR_ID=root-orch-1 POOL_PARENT_RUN_ID=hermes-run-7 "
    "POOL_TASK_CLASS=code "
)


@pytest.mark.parametrize(
    "command, expected",
    [
        # N-1/A1: the identity NAME is split by a line continuation; the
        # shell joins it with NOTHING, so the child receives
        # POOL_ORCHESTRATOR_ID=root-other while the projection check used
        # to see no assignment at all.
        (
            "POOL_ORCH" + _NL + "ESTRATOR_ID=root-other "
            "POOL_PARENT_RUN_ID=hermes-run-7 POOL_TASK_CLASS=code "
            "pool run glm a /tmp glm-5.3",
            "server-derived projection",
        ),
        # N-1/A1b: the same split re-parenting the launch.
        (
            _IDENTITY_PREFIX + "POOL_PARENT_R" + _NL
            + "UN_ID=parent-forged pool run glm a /tmp glm-5.3",
            "server-derived projection",
        ),
        # N-1/A2: the LAUNCH WORD is split — `pool ru\<NL>n grok` is a paid
        # launch the wrapper scan used to not observe at all.
        (
            _IDENTITY_PREFIX + "pool ru" + _NL + "n grok a /tmp grok-4.6",
            "provider substitution",
        ),
    ],
    ids=["split-root-name", "split-parent-name", "split-launch"],
)
def test_n1_posix_continuation_splits_are_canonicalised(
    shared_placement: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    command: str,
    expected: str,
) -> None:
    _install(monkeypatch, tmp_path, _binding())
    with pytest.raises(SystemExit):
        _guard_launch(shared_placement, command)
    output = _emitted(capsys)
    assert output["permissionDecision"] == "deny"
    assert expected in output["permissionDecisionReason"]


def test_n1_continuation_split_launch_reaches_the_binding_gate(
    shared_placement: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    # r2 A2 core: with a stale fence, `pool ru\<NL>n glm` used to return
    # before validate_execution_binding — an armed session executed a paid
    # launch with ZERO binding validation. The gate must run and refuse.
    current = _binding(fence_counter=3)
    _install(
        monkeypatch, tmp_path, _binding(fence_counter=2),
        receipt=_receipt(current, fence_counter=3),
    )
    command = _IDENTITY_PREFIX + "pool ru" + _NL + "n glm a /tmp glm-5.3"
    with pytest.raises(SystemExit):
        _guard_launch(shared_placement, command)
    assert "stale fence" in _emitted(capsys)["permissionDecisionReason"]

    # Observed means validated, not blanket-denied: under the CURRENT
    # binding the same continuation-split launch is allowed.
    _install(monkeypatch, tmp_path, _binding())
    _guard_launch(shared_placement, command)
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize(
    "command",
    [
        # N-2/C1: a for-loop body executes one lexical launch N times.
        "for i in 1 2; do " + _IDENTITY_PREFIX
        + "pool run glm a /tmp glm-5.3; done",
        # while/until bodies are the same runtime-multiplexing construct.
        "while read x; do " + _IDENTITY_PREFIX
        + "pool run glm a /tmp glm-5.3; done",
        # N-2/C2: xargs runs the wrapped command once per input item.
        "printf 'a\\nb\\n' | xargs -I{} env " + _IDENTITY_PREFIX
        + "pool run glm {} /tmp glm-5.3",
        # N-2/C3: parallel multiplies the launch across its argument source.
        "parallel -j2 env " + _IDENTITY_PREFIX
        + "pool run glm {} /tmp glm-5.3 ::: a b",
        # find -exec runs the wrapper once per matched file.
        "find /tmp -name '*.txt' -exec env " + _IDENTITY_PREFIX
        + "pool run glm {} /tmp glm-5.3 \\;",
    ],
    ids=["for-loop", "while-loop", "xargs", "parallel", "find-exec"],
)
def test_n2_runtime_multiplexed_launches_are_refused(
    shared_placement: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    command: str,
) -> None:
    # One lexical launch inside a construct that executes it N times is N
    # paid children under one binding's single attempt_ref.
    _install(monkeypatch, tmp_path, _binding())
    with pytest.raises(SystemExit):
        _guard_launch(shared_placement, command)
    output = _emitted(capsys)
    assert output["permissionDecision"] == "deny"
    reason = output["permissionDecisionReason"]
    assert "runtime-multiplexed" in reason
    assert "exactly one attempt" in reason


def test_n2_launch_feeding_a_batch_tool_stays_allowed(
    shared_placement: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    # A launch that runs ONCE and pipes into xargs is not multiplexed;
    # only a launch inside the executor's own argument tail is refused.
    _install(monkeypatch, tmp_path, _binding())
    _guard_launch(
        shared_placement,
        _IDENTITY_PREFIX + "pool run glm a /tmp glm-5.3 | xargs grep -l glm",
    )
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize(
    "command",
    [
        # N-3/C4: an interpreter one-liner assembles the launch at runtime;
        # the gate never ran at all (no five-shapes match).
        "python3 -c 'subprocess.run([\"pool\",\"run\",\"grok\",\"a\",\"/tmp\","
        "\"grok-4.6\"])'",
        # N-3/C4b: same carrier rewriting the identity inside the code.
        "python3 -c 'import os,subprocess; "
        "os.environ[\"POOL_ORCHESTRATOR_ID\"]=\"root-evil\"; "
        "subprocess.run([\"pool\",\"run\",\"glm\",\"a\",\"/tmp\",\"glm-5.3\"])'",
        # N-3/C5: perl exec of the wrapper.
        "perl -e 'exec(\"pool\",\"run\",\"grok\",\"a\",\"/tmp\",\"grok-4.6\")'",
        # N-3/C6: a variable-assembled command word.
        "P=pool; $P run grok a /tmp grok-4.6",
        "P=pool; ${P} run grok a /tmp grok-4.6",
        "P=pool; exec $P run grok a /tmp grok-4.6",
    ],
    ids=[
        "python-subprocess", "python-env-rewrite", "perl-exec",
        "variable-command", "braced-variable", "exec-runner",
    ],
)
def test_n3_computed_and_interpreter_launches_are_refused(
    shared_placement: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    command: str,
) -> None:
    _install(monkeypatch, tmp_path, _binding())
    monkeypatch.setenv("POOL_ORCHESTRATOR_ID", "root-orch-1")
    monkeypatch.setenv("POOL_PARENT_RUN_ID", "hermes-run-7")
    monkeypatch.setenv("POOL_TASK_CLASS", "code")
    with pytest.raises(SystemExit):
        _guard_launch(shared_placement, command)
    output = _emitted(capsys)
    assert output["permissionDecision"] == "deny"
    assert "unobservable launch" in output["permissionDecisionReason"]


def test_n3_computed_launch_refusal_stays_scoped_to_wrapper_tokens(
    shared_placement: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    # Without a wrapper NAME in the text, interpreter one-liners and
    # computed command words stay allowed (documented arbitrary-process
    # limit). An interpreter running a WRAPPER script does carry the name,
    # so it is refused wholesale (REVIEW_2329 r3 B-1) — pinned by the r5
    # interpreter tests below.
    _install(monkeypatch, tmp_path, _binding())
    monkeypatch.setenv("POOL_ORCHESTRATOR_ID", "root-orch-1")
    monkeypatch.setenv("POOL_PARENT_RUN_ID", "hermes-run-7")
    monkeypatch.setenv("POOL_TASK_CLASS", "code")
    for command in (
        "python3 -m pytest tests/test_provider_orchestrator_policy.py",
        "TOOL=ls; $TOOL -la /tmp",
    ):
        guard.guard_bash(
            _payload(shared_placement, command), {"command": command}
        )
        assert capsys.readouterr().out == "", command


def test_n4_receipt_channel_requires_a_positive_owner_allowlist(
    shared_placement: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    if os.geteuid() == 0:
        pytest.skip("positive-ownership legs need a non-root test principal")
    _install(monkeypatch, tmp_path, _binding())

    # No allowlist projected: the channel is no longer defined only
    # negatively ("anything the principal cannot write") — refuse.
    monkeypatch.delenv("MASTERMIND_PLACEMENT_RECEIPT_OWNER_UIDS")
    with pytest.raises(SystemExit):
        _guard_launch(shared_placement)
    reason = _emitted(capsys)["permissionDecisionReason"]
    assert "not owner-authenticated" in reason
    assert "owner-uid allowlist" in reason
    assert "is not projected" in reason

    # A malformed pin refuses, never falls through.
    monkeypatch.setenv("MASTERMIND_PLACEMENT_RECEIPT_OWNER_UIDS", "not-a-uid")
    with pytest.raises(SystemExit):
        _guard_launch(shared_placement)
    assert "malformed" in _emitted(capsys)["permissionDecisionReason"]

    # r2 N-4 core: a receipt owned by a uid OUTSIDE root+allowlist is
    # refused even though the fenced principal cannot write it — before,
    # any third local account's file qualified as an "owner channel".
    monkeypatch.setenv(
        "MASTERMIND_PLACEMENT_RECEIPT_OWNER_UIDS", str(os.geteuid() + 4242)
    )
    with pytest.raises(SystemExit):
        _guard_launch(shared_placement)
    reason = _emitted(capsys)["permissionDecisionReason"]
    assert "not owner-authenticated" in reason
    assert "owner-uid allowlist" in reason

    # The owner asserting its own uid admits the owner-written receipt.
    monkeypatch.setenv(
        "MASTERMIND_PLACEMENT_RECEIPT_OWNER_UIDS", str(os.geteuid())
    )
    _guard_launch(shared_placement)
    assert capsys.readouterr().out == ""


def test_guard_module_stays_stdlib_only() -> None:
    import ast
    import sys

    source = Path(guard.__file__).read_text(encoding="utf-8")
    roots = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0, "relative imports break verbatim-copy deployment"
            roots.add(str(node.module).split(".")[0])
    assert roots and roots <= set(sys.stdlib_module_names) | {"__future__"}


# --- rework r5: round-3 review findings (B-1, M-A, M-B) ----------------------
#
# The r3 reviewer's standing rule: a refusal that is a pattern ALLOWLIST over
# an open shell grammar is not closed — one flag letter, an unlisted runner,
# a stdin-fed program, a function body or a nested-shell eval restores the
# original bypass, and for the interpreter class that means an armed session
# launched with ZERO binding validation. These tests pin the STRUCTURAL
# refusals: every interpreter when a wrapper name is present, every computed
# word outside an assignment, every launch inside a brace group / function
# body / trap program / repeater, and eval/source/. anywhere in the text.


@pytest.mark.parametrize(
    "command",
    [
        # B-1 interpreter flags the r4 [cemr]-first-letter rule missed.
        "python3 -Sc 'import os; os.system(\"pool run grok a /tmp grok-4.6\")'",
        "python3 -Bc 'import os; os.system(\"pool run grok a /tmp grok-4.6\")'",
        "python3 -Ic 'import os; os.system(\"pool run grok a /tmp grok-4.6\")'",
        "python3 -uc 'import os; os.system(\"pool run grok a /tmp grok-4.6\")'",
        "perl -we 'exec(\"pool\",\"run\",\"grok\",\"a\",\"/tmp\",\"grok-4.6\")'",
        "perl -E 'exec \"pool run grok a /tmp grok-4.6\"'",
        "node -p 'require(\"child_process\").execSync(\"pool run grok a /tmp grok-4.6\")'",
        "node --eval 'require(\"child_process\").execSync(\"pool run grok a /tmp grok-4.6\")'",
        "ruby -ne 'exec \"pool run grok a /tmp grok-4.6\"'",
        "php -nr 'system(\"pool run grok a /tmp grok-4.6\");'",
        # B-1 programs fed on stdin: heredoc, pipe, bare `-`.
        "python3 - <<'EOF'\nimport os\nos.system(\"pool run grok a /tmp grok-4.6\")\nEOF",
        "python3 <<'EOF'\nimport os\nos.system(\"pool run grok a /tmp grok-4.6\")\nEOF",
        "echo 'import os; os.system(\"pool run grok a /tmp grok-4.6\")' | python3",
        # An interpreter running a wrapper SCRIPT is unreadable too.
        "python3 /opt/mastermind/ext/slot.py grok -- run",
    ],
    ids=[
        "py-Sc", "py-Bc", "py-Ic", "py-uc", "perl-we", "perl-E", "node-p",
        "node-eval", "ruby-ne", "php-nr", "heredoc-dash",
        "heredoc-bare", "pipe-stdin", "interpreter-slot-script",
    ],
)
def test_r5_b1_every_interpreter_is_refused_with_a_wrapper_name(
    shared_placement: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    command: str,
) -> None:
    _install(monkeypatch, tmp_path, _binding())
    with pytest.raises(SystemExit):
        _guard_launch(shared_placement, command)
    output = _emitted(capsys)
    assert output["permissionDecision"] == "deny"
    reason = output["permissionDecisionReason"]
    assert "unobservable launch" in reason
    assert "interpreter" in reason


@pytest.mark.parametrize(
    "prefix",
    [
        "time ",
        "sudo ",
        "sudo -n ",
        "caffeinate ",
        "script -q /dev/null ",
        "strace -f ",
        "flock /tmp/launch.lock ",
        "ssh host ",
        "su -c ",
        "{ ",
    ],
    ids=["time", "sudo", "sudo-n", "caffeinate", "script", "strace", "flock",
         "ssh-host", "su-c", "brace-group"],
)
def test_r5_b1_every_runner_carries_a_computed_word_past_the_gate(
    shared_placement: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    prefix: str,
) -> None:
    # The r4 refusal skipped a nine-word runner allowlist, so any other
    # runner (or a brace group) carried `$P` past the gate. Every computed
    # word outside an assignment is refused now.
    command = (
        "P=pool; { $P run grok a /tmp grok-4.6; }"
        if prefix == "{ "
        else "P=pool; " + prefix + "$P run grok a /tmp grok-4.6"
    )
    _install(monkeypatch, tmp_path, _binding())
    with pytest.raises(SystemExit):
        _guard_launch(shared_placement, command)
    output = _emitted(capsys)
    assert output["permissionDecision"] == "deny"
    reason = output["permissionDecisionReason"]
    assert "unobservable launch" in reason
    assert "$P" in reason


@pytest.mark.parametrize(
    "command",
    [
        # M-A: a function defined once, called twice (or recursing).
        _IDENTITY_PREFIX + "f(){ pool run glm a /tmp glm-5.3; }; f; f",
        _IDENTITY_PREFIX + "function f { pool run glm a /tmp glm-5.3; }; f",
        # M-A: bash brace-body loops, C-style arith header included.
        _IDENTITY_PREFIX + "for i in 1 2; { pool run glm a /tmp glm-5.3; }",
        _IDENTITY_PREFIX + "for ((i=0;i<2;i++)) { pool run glm a /tmp glm-5.3; }",
        # M-A: a trap program fires on each delivered signal.
        _IDENTITY_PREFIX
        + "trap 'pool run glm a /tmp glm-5.3' USR1; kill -USR1 $$",
        # M-A: repeaters.
        _IDENTITY_PREFIX + "watch -n 60 pool run glm a /tmp glm-5.3",
        _IDENTITY_PREFIX + "timeout --foreground 600 pool run glm a /tmp glm-5.3",
        # An awk program is a brace group as well: refused by the same
        # structural rule, one step earlier than the interpreter scan.
        "awk 'BEGIN{system(\"pool run grok a /tmp grok-4.6\")}'",
    ],
    ids=["function-twice", "function-keyword", "brace-for", "brace-arith-for",
         "trap", "watch", "timeout-foreground", "awk-brace-program"],
)
def test_r5_ma_function_brace_trap_and_repeater_launches_are_refused(
    shared_placement: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    command: str,
) -> None:
    _install(monkeypatch, tmp_path, _binding())
    with pytest.raises(SystemExit):
        _guard_launch(shared_placement, command)
    output = _emitted(capsys)
    assert output["permissionDecision"] == "deny"
    reason = output["permissionDecisionReason"]
    assert "runtime-multiplexed" in reason
    assert "exactly one attempt" in reason


@pytest.mark.parametrize(
    "command",
    [
        # M-B: eval inside the nested shell that performs the launch — the
        # separator-anchored regex never saw it after `-c '` canonicalisation.
        "X='export POOL_ORCH' Y='ESTRATOR_ID=root-other' bash -c "
        "'eval \"$X$Y\"; pool run glm a /tmp glm-5.3'",
        "bash -c 'eval \"$X\"; pool run glm a /tmp glm-5.3'",
        "sh -c '. ./env.sh; pool run glm a /tmp glm-5.3'",
        "bash -c 'source ./env.sh; pool run glm a /tmp glm-5.3'",
    ],
    ids=["nested-eval-concat", "nested-eval", "nested-dot", "nested-source"],
)
def test_r5_mb_eval_source_dot_inside_a_nested_shell_is_unobservable(
    shared_placement: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    command: str,
) -> None:
    _install(monkeypatch, tmp_path, _binding())
    with pytest.raises(SystemExit):
        _guard_launch(shared_placement, command)
    output = _emitted(capsys)
    assert output["permissionDecision"] == "deny"
    reason = output["permissionDecisionReason"]
    assert "unobservable launch environment" in reason


def test_r5_computed_assignment_does_not_refuse_a_faithful_launch(
    shared_placement: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    # The structural rule is scoped to NON-assignment words: a computed
    # value assigned to a variable is not a command the gate must read, so
    # the faithful launch around it still passes.
    _install(monkeypatch, tmp_path, _binding())
    for name, value in (
        ("POOL_ORCHESTRATOR_ID", "root-orch-1"),
        ("POOL_PARENT_RUN_ID", "hermes-run-7"),
        ("POOL_TASK_CLASS", "code"),
    ):
        monkeypatch.setenv(name, value)
    _guard_launch(
        shared_placement,
        "LABEL=$RANDOM; " + _IDENTITY_PREFIX + "pool run glm a /tmp glm-5.3",
    )
    assert capsys.readouterr().out == ""


# --- r6: REVIEW_2329 r4 closure (B-2 / M-A2 / m-2 / n-2) ---------------------


@pytest.mark.parametrize(
    "command",
    [
        # B-2/G1: `pool*` expands to the wrapper at runtime. No invocation
        # regex matches the glob word, so the armed session reached the
        # no-launch early return before validate_execution_binding: a
        # substituted paid launch (grok) with zero binding validation.
        _IDENTITY_PREFIX + "pool* run grok a /tmp grok-4.6",
        # B-2/G2: a shorter glob prefix behaves identically.
        _IDENTITY_PREFIX + "poo* run grok a /tmp grok-4.6",
        # B-2/G7: glob character class spelling.
        _IDENTITY_PREFIX + "poo[l] run grok a /tmp grok-4.6",
        # A leading glob expands onto a wrapper-looking command word.
        _IDENTITY_PREFIX + "*ool run grok a /tmp grok-4.6",
        # B-2/G3: no literal wrapper token survives at all — the glob IS
        # the wrapper name (`su?.sh` matches `sub.sh`).
        _IDENTITY_PREFIX + "su?.sh grok",
        # B-2/G4: the faithful shape is refused too: a glob in command
        # position makes the command word unreadable whatever it expands to.
        _IDENTITY_PREFIX + "pool* run glm a /tmp glm-5.3",
        # B-2/G5: faithful launch first, substituted glob launch second —
        # one lexical launch observed, a second paid child unaccounted.
        _IDENTITY_PREFIX
        + "pool run glm a /tmp glm-5.3 ; poo* run grok a /tmp grok-4.6",
        # Brace-expanded command word: `po{o,}l` expands to `pool`.
        _IDENTITY_PREFIX + "po{o,}l run grok a /tmp grok-4.6",
        # Argument-position glob with the wrapper token present (the
        # computed-word rule is scoped to non-assignment words, not to the
        # head alone, once a wrapper name is in the text).
        "sudo " + _IDENTITY_PREFIX + "pool* run grok a /tmp grok-4.6",
        # A quoted literal followed by a glob canonicalises to the glob word.
        _IDENTITY_PREFIX + '"pool"* run grok a /tmp grok-4.6',
        # Single-character class `[o]` inside the wrapper name.
        _IDENTITY_PREFIX + "po[o]l run grok a /tmp grok-4.6",
        # A bare glob command word with no wrapper letters at all: it can
        # expand onto ANY name in the PATH, wrapper included.
        _IDENTITY_PREFIX + "* run grok a /tmp grok-4.6",
    ],
    ids=[
        "glob-pool-star",
        "glob-poo-star",
        "glob-poo-class",
        "glob-leading-star",
        "glob-sub-question",
        "glob-faithful-pool-star",
        "glob-second-launch",
        "brace-expansion-head",
        "glob-argument-with-wrapper-token",
        "glob-quoted-literal-star",
        "glob-inner-class",
        "glob-bare-head",
    ],
)
def test_r6_b2_glob_expanded_command_words_are_refused(
    shared_placement: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    command: str,
) -> None:
    _install(monkeypatch, tmp_path, _binding())
    with pytest.raises(SystemExit):
        _guard_launch(shared_placement, command)
    output = _emitted(capsys)
    assert output["permissionDecision"] == "deny"
    reason = output["permissionDecisionReason"]
    assert "unobservable launch" in reason


def test_r6_b2_glob_outside_command_position_is_not_refused(
    shared_placement: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    # The glob refusal is structural, not "any asterisk": with no wrapper
    # name in the text an argument glob is none of this gate's business.
    _install(monkeypatch, tmp_path, _binding())
    _guard_launch(shared_placement, "ls -1 tests/*.py")
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize(
    "command",
    [
        # M-A2/G8: a paren-bodied function has no brace span, so one
        # lexical launch became N paid children under one attempt.
        _IDENTITY_PREFIX + "f() ( pool run glm a /tmp glm-5.3 ); f; f",
        # M-A2/G9: recursion through the same paren body.
        _IDENTITY_PREFIX + "f() ( pool run glm a /tmp glm-5.3; f ); f",
        # The `function` keyword spelling of the same body.
        _IDENTITY_PREFIX + "function f () ( pool run glm a /tmp glm-5.3 ); f",
        # Space between the name and the empty parameter list.
        _IDENTITY_PREFIX + "f () ( pool run glm a /tmp glm-5.3 ); f",
        # M-A2/G11: the launch sits in a while CONDITION, before `do`, so
        # the do…done span never covered it.
        _IDENTITY_PREFIX + "while pool run glm a /tmp glm-5.3; do :; done",
        # M-A2/G12: the until mirror.
        _IDENTITY_PREFIX + "until pool run glm a /tmp glm-5.3; do :; done",
    ],
    ids=[
        "paren-function-twice",
        "paren-function-recursive",
        "paren-function-keyword",
        "paren-function-spaced",
        "while-condition",
        "until-condition",
    ],
)
def test_r6_ma2_paren_function_bodies_and_loop_conditions_are_refused(
    shared_placement: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    command: str,
) -> None:
    _install(monkeypatch, tmp_path, _binding())
    with pytest.raises(SystemExit):
        _guard_launch(shared_placement, command)
    output = _emitted(capsys)
    assert output["permissionDecision"] == "deny"
    reason = output["permissionDecisionReason"]
    assert "runtime-multiplexed" in reason
    assert "exactly one attempt" in reason


def test_r6_ma2_single_subshell_group_is_still_allowed(
    shared_placement: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    # Control (r4 G10): a plain subshell group is not a function body and
    # runs the launch exactly once, so it stays a legitimate faithful launch.
    _install(monkeypatch, tmp_path, _binding())
    _guard_launch(
        shared_placement, _IDENTITY_PREFIX + "( pool run glm a /tmp glm-5.3 )"
    )
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize(
    "word",
    ["python3-3.12", "python-3.12", "perl-5.38"],
    ids=["python3-3.12", "python-3.12", "perl-5.38"],
)
def test_r6_m2_hyphenated_interpreter_spellings_are_refused(
    shared_placement: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    word: str,
) -> None:
    # m-2/G16: `python3-3.12` was not an interpreter word, so the identical
    # command was allowed while `python3` was refused wholesale.
    _install(monkeypatch, tmp_path, _binding())
    command = (
        _IDENTITY_PREFIX
        + f"{word} -c 'print(1)' ; pool run glm a /tmp glm-5.3"
    )
    with pytest.raises(SystemExit):
        _guard_launch(shared_placement, command)
    output = _emitted(capsys)
    assert output["permissionDecision"] == "deny"
    reason = output["permissionDecisionReason"]
    assert "unobservable launch" in reason
    assert "interpreter" in reason


def test_r6_n2_trap_program_span_covers_the_whole_quoted_program(
    shared_placement: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    # n-2: the trap span ended at the first `;` INSIDE the quoted program,
    # so a launch after an earlier statement in the same program was
    # classified as a computed word (the `$$` in the firing kill) instead
    # of runtime-multiplexed. The span is now quote-aware.
    _install(monkeypatch, tmp_path, _binding())
    command = (
        _IDENTITY_PREFIX
        + "trap 'echo hi; pool run glm a /tmp glm-5.3' USR1; kill -USR1 $$"
    )
    with pytest.raises(SystemExit):
        _guard_launch(shared_placement, command)
    output = _emitted(capsys)
    assert output["permissionDecision"] == "deny"
    reason = output["permissionDecisionReason"]
    assert "runtime-multiplexed" in reason
    assert "exactly one attempt" in reason


def test_r6_n2_trap_span_stops_at_the_program_end(
    shared_placement: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    # Precision control: a trap program that carries no launch must not
    # span the faithful launch that follows it.
    _install(monkeypatch, tmp_path, _binding())
    _guard_launch(
        shared_placement,
        _IDENTITY_PREFIX
        + "trap 'echo hi; echo bye' USR1; pool run glm a /tmp glm-5.3",
    )
    assert capsys.readouterr().out == ""


# --- r6 (continued): r4 residual case coverage + interpreter families,
# --- transparent-runner payloads (REVIEW_2329 r6 re-review B-3) ---------------


@pytest.mark.parametrize(
    "command",
    [
        # B-2/GN: a single `?` after the full wrapper name.
        _IDENTITY_PREFIX + "pool? run grok a /tmp grok-4.6",
        # B-2/GN2: `sub.sh?` keeps a literal `sub.sh` token but the word
        # still only becomes the wrapper after expansion.
        _IDENTITY_PREFIX + "sub.sh? grok a /tmp grok-4.6",
    ],
    ids=["glob-pool-question", "glob-sub-sh-question"],
)
def test_r6_b2_wrapper_glob_suffixes_are_refused(
    shared_placement: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    command: str,
) -> None:
    _install(monkeypatch, tmp_path, _binding())
    with pytest.raises(SystemExit):
        _guard_launch(shared_placement, command)
    output = _emitted(capsys)
    assert output["permissionDecision"] == "deny"
    assert "unobservable launch" in output["permissionDecisionReason"]


@pytest.mark.parametrize(
    ("word", "program"),
    [
        # B-3/N2: `pypy3` is an unlisted spelling of the python family —
        # the closed list let its programs launch with zero validation
        # while `python3` was refused wholesale.
        ("pypy3", "-c 'print(1)'"),
        ("pypy3.10", "-c 'print(1)'"),
        ("Rscript", "-e '1'"),
        ("tclsh8.6", "script.tcl"),
        ("lua5.4", "script.lua"),
        ("node-20", "-e '1'"),
        ("deno", "run -A script.ts"),
        ("bun", "run script.ts"),
        ("julia", "script.jl"),
        ("pwsh", "-Command '1'"),
    ],
    ids=[
        "pypy3",
        "pypy3.10",
        "Rscript",
        "tclsh8.6",
        "lua5.4",
        "node-20",
        "deno",
        "bun",
        "julia",
        "pwsh",
    ],
)
def test_r6_b3_interpreter_families_are_refused(
    shared_placement: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    word: str,
    program: str,
) -> None:
    # B-3: with a wrapper token present, interpreter FAMILIES are refused,
    # not a closed spelling list.
    _install(monkeypatch, tmp_path, _binding())
    command = f"{_IDENTITY_PREFIX}{word} {program} ; pool run glm a /tmp glm-5.3"
    with pytest.raises(SystemExit):
        _guard_launch(shared_placement, command)
    output = _emitted(capsys)
    assert output["permissionDecision"] == "deny"
    reason = output["permissionDecisionReason"]
    assert "unobservable launch" in reason
    assert "interpreter" in reason


def test_r6_b3_pypy3_argv_list_substituted_launch_is_refused(
    shared_placement: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    # B-3/N2 exact shape: the argv-list program forms no literal
    # `pool run` sequence, so only the interpreter-word refusal covers it.
    _install(monkeypatch, tmp_path, _binding())
    command = (
        _IDENTITY_PREFIX
        + "pypy3 -c 'subprocess.run([\"pool\",\"run\",\"grok\",\"a\","
        + "\"/tmp\",\"grok-4.6\"])'"
    )
    with pytest.raises(SystemExit):
        _guard_launch(shared_placement, command)
    output = _emitted(capsys)
    assert output["permissionDecision"] == "deny"
    reason = output["permissionDecisionReason"]
    assert "unobservable launch" in reason
    assert "interpreter" in reason


def test_r6_b3_symlink_veil_through_glob_is_refused(
    shared_placement: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    # B-3/N4: the glob in the symlink target is an expansion-dependent
    # word, so the B-2 rule kills the veil before `./p` ever runs.
    _install(monkeypatch, tmp_path, _binding())
    command = (
        _IDENTITY_PREFIX
        + "ln -s /usr/bin/pyth* p && ./p -c "
        + "'subprocess.run([\"pool\",\"run\",\"grok\",\"a\",\"/tmp\",\"grok-4.6\"])'"
    )
    with pytest.raises(SystemExit):
        _guard_launch(shared_placement, command)
    output = _emitted(capsys)
    assert output["permissionDecision"] == "deny"
    assert "unobservable launch" in output["permissionDecisionReason"]


def test_r6_b3_spelled_symlink_veil_stays_refused(
    shared_placement: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    # B-3/N5 control: the spelled-out symlink target is an interpreter
    # word and must keep being refused (only the veil was the hole).
    _install(monkeypatch, tmp_path, _binding())
    command = (
        _IDENTITY_PREFIX
        + "ln -s /usr/bin/python3 p && ./p -c "
        + "'subprocess.run([\"pool\",\"run\",\"grok\",\"a\",\"/tmp\",\"grok-4.6\"])'"
    )
    with pytest.raises(SystemExit):
        _guard_launch(shared_placement, command)
    output = _emitted(capsys)
    assert output["permissionDecision"] == "deny"
    reason = output["permissionDecisionReason"]
    assert "unobservable launch" in reason
    assert "interpreter" in reason


@pytest.mark.parametrize(
    "firing",
    [
        # M-A3/T1: no computed word anywhere — the firing is literal text.
        "pkill -USR1 -f lane9x7.sh",
        # M-A3/T1b: a literal pid discovered in a persistent session.
        "kill -USR1 4242",
    ],
    ids=["pkill-literal-text", "kill-literal-pid"],
)
def test_r6_ma3_trap_fired_by_literal_text_is_refused(
    shared_placement: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    firing: str,
) -> None:
    # M-A3: the quote-aware trap span covers the whole quoted program, so
    # the launch after `echo hi;` is runtime-multiplexed no matter how the
    # signal is later fired.
    _install(monkeypatch, tmp_path, _binding())
    command = (
        _IDENTITY_PREFIX
        + "trap 'echo hi; pool run glm a /tmp glm-5.3' USR1; "
        + firing
    )
    with pytest.raises(SystemExit):
        _guard_launch(shared_placement, command)
    output = _emitted(capsys)
    assert output["permissionDecision"] == "deny"
    reason = output["permissionDecisionReason"]
    assert "runtime-multiplexed" in reason
    assert "exactly one attempt" in reason


@pytest.mark.parametrize(
    "command",
    [
        # REVIEW_2329 r6 re-review B-3: the expansion-dependent wrapper sat
        # at argument position behind a transparent runner, outside both
        # the head-only scan and the wrapper-token scan (live-confirmed
        # against the real wrapper).
        _IDENTITY_PREFIX + "env poo[l] run grok a /tmp grok-4.6",
        _IDENTITY_PREFIX + "sudo poo? run grok a /tmp grok-4.6",
        # A runner flag that consumes an argument must not be mistaken for
        # the payload.
        _IDENTITY_PREFIX + "sudo -u root poo[l] run grok a /tmp grok-4.6",
        _IDENTITY_PREFIX + "nice -n 5 poo? run grok a /tmp grok-4.6",
        _IDENTITY_PREFIX + "exec po{o,}l run grok a /tmp grok-4.6",
        _IDENTITY_PREFIX + "/usr/bin/env poo? run grok a /tmp grok-4.6",
        _IDENTITY_PREFIX + "command poo[l] run grok a /tmp grok-4.6",
        _IDENTITY_PREFIX + "nohup poo? run grok a /tmp grok-4.6",
        _IDENTITY_PREFIX + "time poo? run grok a /tmp grok-4.6",
        _IDENTITY_PREFIX + "env -u POOL_TASK_CLASS poo[l] run grok a /tmp grok-4.6",
        "printf '%s\\n' a b | xargs -n 1 poo? run grok a /tmp grok-4.6",
    ],
    ids=[
        "env-class-glob",
        "sudo-glob",
        "sudo-user-arg-glob",
        "nice-adjust-glob",
        "exec-brace",
        "usr-bin-env-glob",
        "command-builtin-glob",
        "nohup-glob",
        "time-glob",
        "env-unset-arg-glob",
        "xargs-pipe-glob",
    ],
)
def test_r6_b2_expanded_wrapper_behind_transparent_runner_is_refused(
    shared_placement: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    command: str,
) -> None:
    _install(monkeypatch, tmp_path, _binding())
    with pytest.raises(SystemExit):
        _guard_launch(shared_placement, command)
    output = _emitted(capsys)
    assert output["permissionDecision"] == "deny"
    assert "unobservable launch" in output["permissionDecisionReason"]


@pytest.mark.parametrize(
    "command",
    [
        # A literal wrapper behind the same runners is a faithful launch:
        # the identity is readable and exactly one attempt runs.
        "time " + _IDENTITY_PREFIX + "pool run glm a /tmp glm-5.3",
        "nice -n 5 " + _IDENTITY_PREFIX + "pool run glm a /tmp glm-5.3",
        "env POOL_ORCHESTRATOR_ID=root-orch-1 "
        "POOL_PARENT_RUN_ID=hermes-run-7 POOL_TASK_CLASS=code "
        "pool run glm a /tmp glm-5.3",
    ],
    ids=["time-faithful", "nice-faithful", "env-assignments-faithful"],
)
def test_r6_b2_transparent_runner_with_literal_wrapper_is_allowed(
    shared_placement: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    command: str,
) -> None:
    _install(monkeypatch, tmp_path, _binding())
    _guard_launch(shared_placement, command)
    assert capsys.readouterr().out == ""


def test_r6_ma2_single_exec_if_condition_is_still_allowed(
    shared_placement: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    # Control (r4 Gif): an if-condition runs its launch exactly once, so
    # it stays a legitimate faithful launch.
    _install(monkeypatch, tmp_path, _binding())
    _guard_launch(
        shared_placement,
        _IDENTITY_PREFIX + "if pool run glm a /tmp glm-5.3; then :; fi",
    )
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize(
    "prefix",
    [
        # The interpreter families match by final path segment only: a
        # PATH-shaped word is not an interpreter invocation.
        "cp -r node_modules/.bin/pool vendor; ",
        "ls python3.12/bin; ",
    ],
    ids=["node-modules-path", "versioned-dir-path"],
)
def test_r6_b3_path_shaped_words_are_not_interpreter_words(
    shared_placement: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    prefix: str,
) -> None:
    _install(monkeypatch, tmp_path, _binding())
    _guard_launch(
        shared_placement,
        prefix + _IDENTITY_PREFIX + "pool run glm a /tmp glm-5.3",
    )
    assert capsys.readouterr().out == ""


def test_r6_unarmed_sessions_keep_the_legacy_glob_behavior(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Operator-first control: a session the owner did NOT arm keeps the
    # legacy behavior for every new refusal class — none of them applies
    # outside the shared-placement fence.
    home = tmp_path / "home"
    cwd = home / "lanes" / "work"
    cwd.mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("MASTERMIND_CI_POLL_STATE_DIR", str(tmp_path / "poll-state"))
    for name in (
        "MASTERMIND_SHARED_PLACEMENT",
        "POOL_EXECUTION_BINDING",
        "MASTERMIND_PLACEMENT_RECEIPT",
    ):
        monkeypatch.delenv(name, raising=False)
    for command in (
        "env poo[l] run grok bounded /tmp grok-4.6",
        "pypy3 -c 'print(1)'",
        "ls -1 tests/*.py",
    ):
        guard.guard_bash(_payload(cwd, command), {"command": command})
        assert capsys.readouterr().out == ""


# --- r7: REVIEW_2329 r5 closure (B-1 / M-1 / M-2 / M-3 / m-1) — the armed ---
# --- fail-closed posture -------------------------------------------------------
#
# The r5 final-gate review's standing lesson, endorsed by the orchestrator:
# five rounds of enumerating escape spellings always lost to the shell
# surface (a runner word, a --flag=value, a quoted program, an unlisted
# interpreter restored the bypass each time). The armed gate is therefore
# FAIL-CLOSED now: a command that carries a wrapper token — literal, or a
# shell-expanded WRAPPER-SHAPED word at a position the guard cannot reduce
# to a plain data argument — is admitted only if it fully reduces (every
# word canonical, every command head recognized, every span parseable);
# anything ambiguous is refused with a precise reason. The runner and
# interpreter vocabularies stay as optimizations: correctness no longer
# depends on their completeness. Unarmed/legacy legs keep the pre-posture
# behavior exactly (pinned by the unarmed test below).

_R7_FAITH = _IDENTITY_PREFIX + 'pool run glm "bounded task" /tmp glm-5.3'


@pytest.mark.parametrize(
    "command",
    [
        # B-1(a): runners absent from _TRANSPARENT_RUNNERS carried the
        # expanded wrapper at unscanned argument position (live-confirmed
        # by the r5 reviewer; `watch` multiplied it without bound).
        "timeout 5 poo[l] run grok a /tmp grok-4.6",
        "watch poo* run grok a /tmp grok-4.6",
        "watch -n 0.2 ./poo* run grok a /tmp grok-4.6",
        "strace -o /dev/null poo* run grok a /tmp grok-4.6",
        "setsid poo* run grok a /tmp grok-4.6",
        "stdbuf -o0 poo* run grok a /tmp grok-4.6",
        "arch -x86_64 poo* run grok a /tmp grok-4.6",
        "script -q /dev/null poo* run grok a /tmp grok-4.6",
        # The runner CHAIN: nohup is recognized, but its payload `timeout`
        # is unclassifiable, so the chain's tail is unprovable.
        "nohup timeout 5 poo[l] run grok a /tmp grok-4.6",
    ],
    ids=[
        "timeout", "watch", "watch-interval", "strace", "setsid", "stdbuf",
        "arch", "script", "nohup-timeout-chain",
    ],
)
def test_r7_b1_unlisted_runner_payloads_are_refused(
    shared_placement: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    command: str,
) -> None:
    _install(monkeypatch, tmp_path, _binding())
    with pytest.raises(SystemExit):
        _guard_launch(shared_placement, command)
    output = _emitted(capsys)
    assert output["permissionDecision"] == "deny"
    assert "unobservable launch" in output["permissionDecisionReason"]


@pytest.mark.parametrize(
    "command",
    [
        # THE POSTURE: runners that appear in NO vocabulary — the reviewer
        # will invent one more — are refused because their tail positions
        # cannot be reduced, not because they were enumerated.
        "faketime 5s poo* run grok a /tmp grok-4.6",
        "vrfy --mode x poo* run grok a /tmp grok-4.6",
        "unbuffer poo[l] run grok a /tmp grok-4.6",
        "valgrind -q poo? run grok a /tmp grok-4.6",
        "chroot / poo[l] run grok a /tmp grok-4.6",
        "zzz --flag=1 poo* run grok a /tmp grok-4.6",
        # An attached flag VALUE carrying the pattern is just as unprovable.
        "faketime --when=po* poo* run grok a /tmp grok-4.6",
        # A glob hidden behind a glued prefix inside a program string is
        # re-expanded by the child shell.
        "R -e 'system(\"poo* run grok x /tmp grok-4.6\")'",
    ],
    ids=[
        "faketime", "vrfy", "unbuffer", "valgrind", "chroot", "zzz",
        "attached-value", "program-string-glob",
    ],
)
def test_r7_posture_refuses_never_enumerated_runners(
    shared_placement: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    command: str,
) -> None:
    _install(monkeypatch, tmp_path, _binding())
    with pytest.raises(SystemExit):
        _guard_launch(shared_placement, command)
    output = _emitted(capsys)
    assert output["permissionDecision"] == "deny"
    assert "unobservable launch" in output["permissionDecisionReason"]


@pytest.mark.parametrize(
    "command",
    [
        # B-1(b): an ATTACHED =value consumed no further word, so the flag
        # swallowed the payload word and the expanded wrapper passed as a
        # flag argument (live-confirmed; the split forms already refused).
        "sudo --user=root poo[l] run grok a /tmp grok-4.6",
        "env --unset=FOO poo[l] run grok a /tmp grok-4.6",
        "nice --adjustment=5 poo* run grok a /tmp grok-4.6",
        "xargs --max-args=2 poo* </dev/null",
    ],
    ids=["sudo-user-eq", "env-unset-eq", "nice-adjust-eq", "xargs-max-eq"],
)
def test_r7_b1_attached_value_flags_do_not_swallow_the_payload(
    shared_placement: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    command: str,
) -> None:
    _install(monkeypatch, tmp_path, _binding())
    with pytest.raises(SystemExit):
        _guard_launch(shared_placement, command)
    output = _emitted(capsys)
    assert output["permissionDecision"] == "deny"
    assert "unobservable launch" in output["permissionDecisionReason"]


@pytest.mark.parametrize(
    "command",
    [
        # B-1(c): the glob sits inside a shell/ssh program string; the CHILD
        # shell expands it as its own command word (live-confirmed on macOS).
        "bash -c 'poo* run grok x /tmp grok-4.6'",
        "sh -c 'poo* run grok x /tmp grok-4.6'",
        "ssh h 'poo* run grok x /tmp grok-4.6'",
    ],
    ids=["bash-c", "sh-c", "ssh"],
)
def test_r7_b1_shell_program_payloads_are_refused(
    shared_placement: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    command: str,
) -> None:
    _install(monkeypatch, tmp_path, _binding())
    with pytest.raises(SystemExit):
        _guard_launch(shared_placement, command)
    output = _emitted(capsys)
    assert output["permissionDecision"] == "deny"
    assert "unobservable launch" in output["permissionDecisionReason"]


@pytest.mark.parametrize(
    "command",
    [
        # M-1: a do/done PAIR inside the condition truncated both the
        # condition span and the body span (live: 3 launches).
        _IDENTITY_PREFIX
        + "while echo do echo done; pool run glm a /tmp glm-5.3; do :; done",
        _IDENTITY_PREFIX
        + "until echo do echo done; pool run glm a /tmp glm-5.3; do :; done",
        # Precision pins (r5: these single-`do` shapes already refused):
        # the argument `do` must not be mistaken for the loop's `do`.
        _IDENTITY_PREFIX + "while echo do; pool run glm a /tmp glm-5.3; do :; done",
        _IDENTITY_PREFIX
        + "while grep -q do notes.txt; pool run glm a /tmp glm-5.3; do :; done",
        _IDENTITY_PREFIX
        + 'while [ "$x" = "do" ]; pool run glm a /tmp glm-5.3; do :; done',
    ],
    ids=["while-do-done-pair", "until-do-done-pair", "while-bare-do",
         "while-grep-do", "while-quoted-do"],
)
def test_r7_m1_do_done_pair_in_a_loop_condition_is_refused(
    shared_placement: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    command: str,
) -> None:
    _install(monkeypatch, tmp_path, _binding())
    with pytest.raises(SystemExit):
        _guard_launch(shared_placement, command)
    output = _emitted(capsys)
    assert output["permissionDecision"] == "deny"
    reason = output["permissionDecisionReason"]
    assert "runtime-multiplexed" in reason
    assert "exactly one attempt" in reason


@pytest.mark.parametrize(
    "command",
    [
        # M-1: the paren-body scanner allowed only [ \t] between () and the
        # body and measured quote-blind canon. Newlines, comments and a
        # quoted ")" are all legal bash (live: 2 launches each).
        _IDENTITY_PREFIX + "f()\n( pool run glm a /tmp glm-5.3 )\nf\nf",
        _IDENTITY_PREFIX + "f() # c\n( pool run glm a /tmp glm-5.3 ); f; f",
        _IDENTITY_PREFIX + 'f() ( echo ")"; pool run glm a /tmp glm-5.3 ); f; f',
    ],
    ids=["next-line", "behind-comment", "quoted-close-paren"],
)
def test_r7_m1_paren_body_edge_spans_are_refused(
    shared_placement: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    command: str,
) -> None:
    _install(monkeypatch, tmp_path, _binding())
    with pytest.raises(SystemExit):
        _guard_launch(shared_placement, command)
    output = _emitted(capsys)
    assert output["permissionDecision"] == "deny"
    reason = output["permissionDecisionReason"]
    assert "runtime-multiplexed" in reason
    assert "exactly one attempt" in reason


@pytest.mark.parametrize(
    "command",
    [
        # M-2: the trap scanner assumed one pure quoted string. Concatenated
        # sections, '\'' splices, "a""b" and a leading -- defeated it
        # (live: 2 launches via literal kill).
        _IDENTITY_PREFIX
        + "trap 'echo hi'\\;'pool run glm a /tmp glm-5.3' USR1; kill -USR1 4242",
        _IDENTITY_PREFIX
        + "trap 'echo '\\''hi'\\''; pool run glm a /tmp glm-5.3 ' USR1"
        + "; kill -USR1 4242",
        _IDENTITY_PREFIX
        + 'trap "echo hi""; pool run glm a /tmp glm-5.3" USR1; kill -USR1 4242',
        _IDENTITY_PREFIX
        + "trap -- 'echo hi; pool run glm a /tmp glm-5.3' USR1; kill -USR1 4242",
    ],
    ids=["backslash-concat", "quote-splice", "double-quote-concat", "dash-dash"],
)
def test_r7_m2_trap_program_concatenations_are_refused(
    shared_placement: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    command: str,
) -> None:
    _install(monkeypatch, tmp_path, _binding())
    with pytest.raises(SystemExit):
        _guard_launch(shared_placement, command)
    output = _emitted(capsys)
    assert output["permissionDecision"] == "deny"
    reason = output["permissionDecisionReason"]
    assert "runtime-multiplexed" in reason
    assert "exactly one attempt" in reason


def test_r7_m2_launch_free_trap_program_still_spans_precisely(
    shared_placement: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    # Precision control: `trap --` with a launch-free program must not span
    # the faithful launch that follows it (the span stops at the program).
    _install(monkeypatch, tmp_path, _binding())
    _guard_launch(
        shared_placement,
        _IDENTITY_PREFIX
        + "trap -- 'echo hi; echo bye' USR1; pool run glm a /tmp glm-5.3",
    )
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize(
    "command",
    [
        # M-3: the interpreter families were a closed list. The probed
        # spellings (R, sqlite3 .read, jshell) get the precise interpreter
        # reason now — and every UNLISTED program carrier is refused by the
        # posture as an unrecognized head, so closure no longer depends on
        # the family list.
        _IDENTITY_PREFIX + "R -e 'system(\"pool run grok x /tmp grok-4.6\")'",
        _IDENTITY_PREFIX
        + "R -e 'system(paste0(\"po\",\"ol run grok x\"))'; "
        + 'pool run glm "bounded task" /tmp glm-5.3',
        _IDENTITY_PREFIX
        + "R --file tools/snip.R; " + 'pool run glm "bounded task" /tmp glm-5.3',
        _IDENTITY_PREFIX
        + "sqlite3 db '.read e.sql'; "
        + 'pool run glm "bounded task" /tmp glm-5.3',
        _IDENTITY_PREFIX
        + "jshell -s tools/snip.jsh; " + 'pool run glm "bounded task" /tmp glm-5.3',
        _IDENTITY_PREFIX
        + "java -jar tools/App.jar; "
        + 'pool run glm "bounded task" /tmp glm-5.3',
    ],
    ids=["R-system", "R-paste0", "R-file", "sqlite3-read", "jshell", "java-jar"],
)
def test_r7_m3_unlisted_interpreters_beside_a_launch_are_refused(
    shared_placement: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    command: str,
) -> None:
    _install(monkeypatch, tmp_path, _binding())
    with pytest.raises(SystemExit):
        _guard_launch(shared_placement, command)
    output = _emitted(capsys)
    assert output["permissionDecision"] == "deny"
    reason = output["permissionDecisionReason"]
    assert "unobservable launch" in reason
    assert "interpreter" in reason


@pytest.mark.parametrize(
    "command",
    [
        # Same class, deliberately NOT in the family list — the posture
        # (unrecognized head beside a launch) refuses them anyway.
        _IDENTITY_PREFIX
        + "groovy -e 'println 1'; " + 'pool run glm "bounded task" /tmp glm-5.3',
        _IDENTITY_PREFIX
        + "make -f x.mk; " + 'pool run glm "bounded task" /tmp glm-5.3',
        _IDENTITY_PREFIX
        + "octave --eval 1; " + 'pool run glm "bounded task" /tmp glm-5.3',
        # A renamed wrapper: `./p` -> pool is an unrecognized head beside
        # the wrapper name carried in the symlink target.
        _IDENTITY_PREFIX + "ln -s /usr/local/bin/pool p && ./p run glm a /tmp glm-5.3",
        # An invented tool beside a faithful launch.
        _IDENTITY_PREFIX + "zzz --mode x; " + 'pool run glm "bounded task" /tmp glm-5.3',
    ],
    ids=["groovy", "make", "octave", "renamed-wrapper", "unknown-tool"],
)
def test_r7_m3_unrecognized_heads_beside_a_launch_are_refused(
    shared_placement: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    command: str,
) -> None:
    _install(monkeypatch, tmp_path, _binding())
    with pytest.raises(SystemExit):
        _guard_launch(shared_placement, command)
    output = _emitted(capsys)
    assert output["permissionDecision"] == "deny"
    assert "unobservable launch" in output["permissionDecisionReason"]


@pytest.mark.parametrize(
    "command",
    [
        # m-1: extglob words are expansion-dependent; the paren split used
        # to dismember them (`po+(o)l` -> `po+`/`o`/`l`).
        "po+(o)l run grok 'x' /tmp grok-4.6",
        "po?(o)l run grok 'x' /tmp grok-4.6",
        "su@(b).sh grok 'x'",
    ],
    ids=["plus-extglob", "question-extglob", "at-extglob"],
)
def test_r7_m1_extglob_words_are_refused(
    shared_placement: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    command: str,
) -> None:
    _install(monkeypatch, tmp_path, _binding())
    with pytest.raises(SystemExit):
        _guard_launch(shared_placement, command)
    output = _emitted(capsys)
    assert output["permissionDecision"] == "deny"
    assert "unobservable launch" in output["permissionDecisionReason"]


def test_r7_posture_stays_scoped_to_wrapper_shaped_patterns(
    shared_placement: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    # Precision controls: an expanded word that CANNOT be a wrapper, at the
    # same unprovable positions, is the documented arbitrary-process limit
    # — the posture refuses the irreducible wrapper shape, not every mark.
    _install(monkeypatch, tmp_path, _binding())
    for command in (
        "faketime 5s a+(b) run x",  # extglob, not wrapper-shaped
        "git add docs/*.md",  # data-only utility: argument globs are data
        "ls -1 tests/*.py",  # re-pinned r6 control under the posture
    ):
        _guard_launch(shared_placement, command)
        assert capsys.readouterr().out == "", command


def test_r7_posture_unparsed_runner_grammar_is_refused_even_literal(
    shared_placement: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    # Documented over-refusal, pinned deliberately: `timeout`'s duration
    # argument is grammar the guard does not model, so even a LITERAL
    # wrapper behind it is irreducible and refused. Runners whose grammar
    # IS modeled (time/nice/env, above) stay allowed.
    _install(monkeypatch, tmp_path, _binding())
    with pytest.raises(SystemExit):
        _guard_launch(
            shared_placement,
            "timeout 5 " + _IDENTITY_PREFIX + "pool run glm a /tmp glm-5.3",
        )
    assert "unobservable launch" in _emitted(capsys)["permissionDecisionReason"]


def test_r7_unarmed_sessions_keep_the_legacy_posture_behavior(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Scoped arming (OQ-7): every r7 refusal class is shared-placement
    # only — an unarmed session keeps the legacy freedom exactly.
    home = tmp_path / "home"
    cwd = home / "lanes" / "work"
    cwd.mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("MASTERMIND_CI_POLL_STATE_DIR", str(tmp_path / "poll-state"))
    for name in (
        "MASTERMIND_SHARED_PLACEMENT",
        "POOL_EXECUTION_BINDING",
        "MASTERMIND_PLACEMENT_RECEIPT",
    ):
        monkeypatch.delenv(name, raising=False)
    for command in (
        "timeout 5 poo[l] run grok bounded /tmp grok-4.6",
        "bash -c 'poo* run grok x /tmp grok-4.6'",
        "faketime 5s poo* run grok bounded /tmp grok-4.6",
        "po+(o)l run grok bounded /tmp grok-4.6",
    ):
        guard.guard_bash(_payload(cwd, command), {"command": command})
        assert capsys.readouterr().out == "", command


# --- rework r8: round-6 posture review blockers (B-R6-1/B-R6-2/M-R6-1) ---------
#
# REVIEW_2329 r6 posture verification found two no-third-state violations:
# armed commands ADMITTED while a wrapper-shaped, shell-expanded launch word
# sat where the token-free classifier never wrapper-shape-checked it. Both
# were live-confirmed to execute (echo stand-ins); B-R6-1 was also a
# REGRESSION (the identical command was refused at the r6 parent head).


@pytest.mark.parametrize(
    "command",
    [
        # B-R6-1: every word scanner treats a glued <( / >( word as a
        # redirection, but bash runs the payload in a SUBSHELL — the glob
        # expands to the wrapper there (live-confirmed via PATH stand-in;
        # an exploratory leg reached the real wrapper's economic policy).
        "cat <(poo* run grok 'x' /tmp grok-4.6)",
        "diff <(poo* run grok 'x' /tmp grok-4.6) /dev/null",
        "echo x > >(poo* run grok 'x' /tmp grok-4.6)",
        "cat <(su?.sh grok 'x')",
        # $( glued openers are executed constructs of the same genus.
        "cat $(poo* run grok 'x' /tmp grok-4.6)",
    ],
    ids=["cat-procsub", "diff-procsub", "write-procsub", "extglob-procsub",
         "command-sub"],
)
def test_r8_br61_process_substitution_glob_payloads_are_refused(
    shared_placement: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    command: str,
) -> None:
    _install(monkeypatch, tmp_path, _binding())
    with pytest.raises(SystemExit):
        _guard_launch(shared_placement, command)
    output = _emitted(capsys)
    assert output["permissionDecision"] == "deny"
    assert "unobservable launch" in output["permissionDecisionReason"]


@pytest.mark.parametrize(
    "command",
    [
        # PS-2: the escape BESIDE a faithful launch — a literal wrapper
        # token is present, so the wrapper-present leg runs, but the glued
        # <( / >( word was skipped by every scanner there too.
        _IDENTITY_PREFIX
        + "pool run glm a /tmp glm-5.3 && cat <(poo* run grok x /tmp grok-4.6)",
        _IDENTITY_PREFIX
        + "pool run glm a /tmp glm-5.3; echo x > >(poo* run grok x /tmp grok-4.6)",
        # The same escape shape with the substitution feeding the faithful
        # launch's own stdin.
        _IDENTITY_PREFIX
        + "pool run glm a /tmp glm-5.3 < <(poo* run grok x /tmp grok-4.6)",
    ],
    ids=["beside-faithful", "write-beside-faithful", "stdin-beside-faithful"],
)
def test_r8_br61_process_substitution_beside_faithful_launch_is_refused(
    shared_placement: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    command: str,
) -> None:
    _install(monkeypatch, tmp_path, _binding())
    with pytest.raises(SystemExit):
        _guard_launch(shared_placement, command)
    output = _emitted(capsys)
    assert output["permissionDecision"] == "deny"
    assert "unobservable launch" in output["permissionDecisionReason"]


@pytest.mark.parametrize(
    "command",
    [
        # B-R6-2: the keyword takes the command slot in
        # _expanded_command_word and the promoted head is never
        # wrapper-shape-checked in _unprovable_position_word — so the glob
        # condition of if/while/until/elif/! executed unobserved (the
        # while form also runtime-multiplexes: live stand-in ran twice).
        "if poo* run grok 'x' /tmp grok-4.6; then :; fi",
        "while poo* run grok 'x' /tmp grok-4.6; do :; done",
        "until poo* run grok 'x' /tmp grok-4.6; do :; done",
        "! poo* run grok 'x' /tmp grok-4.6",
        "if :; then :; elif poo* run grok 'x' /tmp grok-4.6; then :; fi",
        # M-R6-1's genus, spelled with the transparent-runner keyword: the
        # head-position check must not depend on 'time' being listed.
        "time poo? run grok 'x' /tmp grok-4.6",
    ],
    ids=["if", "while", "until", "negation", "elif", "time-glob"],
)
def test_r8_br62_keyword_condition_glob_heads_are_refused(
    shared_placement: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    command: str,
) -> None:
    _install(monkeypatch, tmp_path, _binding())
    with pytest.raises(SystemExit):
        _guard_launch(shared_placement, command)
    output = _emitted(capsys)
    assert output["permissionDecision"] == "deny"
    assert "unobservable launch" in output["permissionDecisionReason"]


def test_r8_mr61_time_entry_is_optimization_only(
    shared_placement: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    # M-R6-1: the r6 scratch falsification emptied _TRANSPARENT_RUNNERS and
    # the token-free `time poo? …` refusal DISAPPEARED (the entry was
    # load-bearing: without it `time` was skipped as a keyword and the
    # promoted head was never shape-checked). Since r8 the keyword/prefix
    # head no longer consumes the command slot and the resulting head is
    # wrapper-shape-checked, so removing the entry must NOT lose the
    # refusal — the list is optimization-only again.
    _install(monkeypatch, tmp_path, _binding())
    without_time = frozenset(guard._TRANSPARENT_RUNNERS - {"time"})
    assert "time" in guard._TRANSPARENT_RUNNERS  # the cell exists to remove
    monkeypatch.setattr(guard, "_TRANSPARENT_RUNNERS", without_time)
    with pytest.raises(SystemExit):
        _guard_launch(
            shared_placement, "time poo? run grok 'x' /tmp grok-4.6"
        )
    output = _emitted(capsys)
    assert output["permissionDecision"] == "deny"
    assert "unobservable launch" in output["permissionDecisionReason"]
    # And the listed-runner optimization still carries the flag grammar
    # when the entry IS present (pinned above, r6 time-faithful): a
    # faithful literal launch behind `time` stays allowed either way.
    _guard_launch(
        shared_placement, "time " + _IDENTITY_PREFIX + "pool run glm a /tmp glm-5.3"
    )
    assert capsys.readouterr().out == ""


def test_r8_process_substitution_without_wrapper_token_stays_allowed(
    shared_placement: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    # Controls: an ordinary process substitution with NO wrapper token is
    # an unarmed-style construct — the payload reduces to safe-data heads,
    # so it stays allowed in armed sessions.
    _install(monkeypatch, tmp_path, _binding())
    for command in (
        "cat <(ls)",
        "diff <(echo a) <(echo b)",
        "echo x > >(wc -l)",
    ):
        _guard_launch(shared_placement, command)
        assert capsys.readouterr().out == "", command


def test_r8_keyword_condition_without_wrapper_token_stays_allowed(
    shared_placement: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    # Controls: a keyword-headed condition whose head is a recognized
    # safe-data utility — with an argument glob, not a wrapper-shaped
    # command word — stays allowed (the condition position is judged as a
    # COMMAND position, and `ls`/`grep` are recognized heads). A `for`
    # loop's glob list is deliberately absent: its loop variable is an
    # UNRECOGNIZED head under the r7 posture, so that shape was already
    # refused before r8 (documented over-refusal, unchanged).
    _install(monkeypatch, tmp_path, _binding())
    for command in (
        "if ls *.py; then :; fi",
        "while grep -q pool README.md; do sleep 1; done",
    ):
        _guard_launch(shared_placement, command)
        assert capsys.readouterr().out == "", command


# --- rework r9: round-7 posture review blocker (B-R7-1) ------------------------
#
# REVIEW_2329 r7 measured the BACKTICK spelling of command substitution
# ADMITTED token-free behind a safe-data head: a substituted
# `poo* run grok …` argument was ALLOW because `_PROC_SUB_OPEN_RE`
# covered the `<(`/`>(`/`$(` openers but not the backtick sibling the r8
# fix's own docstring claims ("$(cmd) command substitution likewise").
# The backtick payload now gets the same recursive armed posture — while
# the substitution's RESULT still feeds the safe head as data, so
# pure-data payloads stay allowed.


@pytest.mark.parametrize(
    "command",
    [
        # B-R7-1's four measured shapes: cat head, echo head, the same
        # payload re-entered through a procsub payload the r8 recursion
        # judges, and the while-condition multiplexed variant.
        "cat `poo* run grok 'x' /tmp grok-4.6`",
        "echo `poo* run grok 'x' /tmp grok-4.6`",
        "cat <(echo `poo* run grok x`)",
        "while cat `poo* run grok x` >/dev/null; do :; done",
        # The class-glob spelling of the same payload (poo[l]).
        "cat `poo[l] run grok x`",
    ],
    ids=["cat-head", "echo-head", "procsub-nested", "while-multiplexed",
         "class-glob"],
)
def test_r9_br71_backtick_payloads_are_refused(
    shared_placement: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    command: str,
) -> None:
    _install(monkeypatch, tmp_path, _binding())
    with pytest.raises(SystemExit):
        _guard_launch(shared_placement, command)
    output = _emitted(capsys)
    assert output["permissionDecision"] == "deny"
    assert "unobservable launch" in output["permissionDecisionReason"]


def test_r9_backtick_pure_data_stays_allowed(
    shared_placement: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    # Controls: the substitution's RESULT feeds the safe head as data.
    # Every payload reduces to safe-data heads/builtins inside the
    # recursion, so the armed posture admits the command — B-R7-1 refuses
    # the PAYLOAD's launch, not the backtick.
    _install(monkeypatch, tmp_path, _binding())
    for command in (
        "cat `git describe --dirty`",
        "echo `date`",
        "cat `pwd`",
        "echo `echo hi`",
    ):
        _guard_launch(shared_placement, command)
        assert capsys.readouterr().out == "", command


def test_r9_unarmed_sessions_keep_the_backtick_shapes_allowed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Scoped arming (the r7 unarmed pattern): the r9 rule lives only
    # inside the armed `_deny_computed_launch`; an unarmed session keeps
    # the legacy freedom for every refusal shape above.
    home = tmp_path / "home"
    cwd = home / "lanes" / "work"
    cwd.mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("MASTERMIND_CI_POLL_STATE_DIR", str(tmp_path / "poll-state"))
    for name in (
        "MASTERMIND_SHARED_PLACEMENT",
        "POOL_EXECUTION_BINDING",
        "MASTERMIND_PLACEMENT_RECEIPT",
    ):
        monkeypatch.delenv(name, raising=False)
    for command in (
        "cat `poo* run grok 'x' /tmp grok-4.6`",
        "echo `poo* run grok 'x' /tmp grok-4.6`",
        "cat <(echo `poo* run grok x`)",
        "while cat `poo* run grok x` >/dev/null; do :; done",
        "cat `poo[l] run grok x`",
        "cat `git describe --dirty`",
    ):
        guard.guard_bash(_payload(cwd, command), {"command": command})
        assert capsys.readouterr().out == "", command
