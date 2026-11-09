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
    "command",
    [
        "POOL_ORCHESTRATOR_ID=root-orch-1 POOL_PARENT_RUN_ID=hermes-run-7 "
        "POOL_TASK_CLASS=code pool run grok bounded /tmp grok-4.6",
        "POOL_ORCHESTRATOR_ID=root-orch-1 POOL_PARENT_RUN_ID=hermes-run-7 "
        "POOL_TASK_CLASS=code python3 /opt/mastermind/ext/slot.py grok -- "
        "grok -p bounded --output-format plain",
        "POOL_ORCHESTRATOR_ID=root-orch-1 POOL_PARENT_RUN_ID=hermes-run-7 "
        "POOL_TASK_CLASS=code /opt/mastermind/ext/remote_sub.sh ubuntu2 grok "
        "/tmp/packet.txt /home/ubuntu2/lanes/repo grok-4.6",
    ],
    ids=["pool-run", "slot-py", "remote-sub"],
)
def test_shared_placement_paid_launch_substituting_provider_is_refused(
    shared_placement: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    command: str,
) -> None:
    # The binding reserved pool glm / provider codex; the launch asks grok.
    _install(monkeypatch, tmp_path, _binding())
    with pytest.raises(SystemExit):
        _guard_launch(shared_placement, command)
    output = _emitted(capsys)
    assert output["permissionDecision"] == "deny"
    assert "provider substitution" in output["permissionDecisionReason"]
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
    # r6 (LANE_EXECUTIVE_DIRECTOR_C3 ledger, T-1): the nested-export and
    # dynamic-value rows are now refused by the ADMIT rule before the
    # projection check runs (an ``export`` builtin in the -c body / a
    # computed ``$OTHER`` assignment are not an admitted form). Verdict
    # unchanged (deny); the reason is the structural code.
    structural = {
        "export POOL_ORCHESTRATOR_ID": "R6_ENV_BUILTIN",
        "=$OTHER": "R6_EXPANSION",
    }
    code = next((c for marker, c in structural.items() if marker in command), "")
    if code:
        assert code in reason
    else:
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
            "R6_COMPOUND_LIST",  # r6 ledger T-2: was "provider substitution"
        ),
        # P3c: substituted first launch, matching later launch (regex
        # priority used to grab the later `pool run glm`).
        (
            "POOL_ORCHESTRATOR_ID=root-orch-1 POOL_PARENT_RUN_ID=hermes-run-7 "
            "POOL_TASK_CLASS=code /opt/mastermind/ext/sub.sh grok /tmp/p.txt "
            "/tmp grok-4.6; pool run glm a /tmp glm-5.3",
            "R6_COMPOUND_LIST",  # r6 ledger T-2: was "provider substitution"
        ),
        # P3d: decoy launch text inside an echo, real launch substituted.
        (
            'echo "pool run glm"; POOL_ORCHESTRATOR_ID=root-orch-1 '
            "POOL_PARENT_RUN_ID=hermes-run-7 POOL_TASK_CLASS=code "
            "/opt/mastermind/ext/sub.sh grok /tmp/p.txt /tmp grok-4.6",
            "R6_COMPOUND_LIST",  # r6 ledger T-2: was "provider substitution"
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
        "python3 /opt/mastermind/ext/slot.py deepseek -- run",
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
        # Quoted literal equal to the projection.
        "env \"POOL_ORCHESTRATOR_ID=root-orch-1\" pool run glm a /tmp glm-5.3",
        # The faithful spelling of the former env -i row (no -i).
        "env POOL_ORCHESTRATOR_ID=root-orch-1 POOL_PARENT_RUN_ID=hermes-run-7 "
        "POOL_TASK_CLASS=code pool run glm a /tmp glm-5.3",
    ):
        _guard_launch(shared_placement, command)
        assert capsys.readouterr().out == "", command
    # r6 (ledger T-3): two former ALLOW rows are now refused by the ADMIT
    # rule. ``env -i`` also strips the owner-projected binding/receipt
    # environment from the launched child, and a compound line (read;
    # export; launch) is not one plain launch — the same reads/exports
    # stay available as their own commands.
    for command, code in (
        (
            "env -i POOL_ORCHESTRATOR_ID=root-orch-1 POOL_PARENT_RUN_ID=hermes-run-7 "
            "POOL_TASK_CLASS=code pool run glm a /tmp glm-5.3",
            "R6_PREFIX_FORM",
        ),
        (
            'echo "$POOL_ORCHESTRATOR_ID ${POOL_PARENT_RUN_ID}"; '
            "export POOL_ORCHESTRATOR_ID; pool run glm a /tmp glm-5.3",
            "R6_COMPOUND_LIST",
        ),
    ):
        with pytest.raises(SystemExit):
            _guard_launch(shared_placement, command)
        assert code in _emitted(capsys)["permissionDecisionReason"], command


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
    for shape in shapes:  # each shape alone, matching: allowed
        _guard_launch(shared_placement, prefix + shape)
        assert capsys.readouterr().out == "", shape
    for shape in shapes:  # repeated in one command: second is unaccounted
        with pytest.raises(SystemExit):
            _guard_launch(shared_placement, f"{prefix}{shape} && {shape}")
        assert "unaccounted descendant" in _emitted(capsys)["permissionDecisionReason"]
    # A substituted launch anywhere in the command is found.
    with pytest.raises(SystemExit):
        _guard_launch(
            shared_placement,
            f"{prefix}pool run glm a /tmp m; true; true; /opt/x/remote_sub.sh h grok p",
        )
    # r6 ledger T-4: refused as a compound list before token comparison
    # (was asserted via the substituted token 'grok').
    assert "R6_COMPOUND_LIST" in _emitted(capsys)["permissionDecisionReason"]
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
    # r6 ledger T-5: the here-document itself refuses (was asserted via the
    # substituted token 'grok' found inside the heredoc body).
    reason = _emitted(capsys)["permissionDecisionReason"]
    assert "R6_HEREDOC" in reason


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
        + 'pool run glm "$x" /tmp glm-5.3; done',
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


def test_n2_launch_feeding_a_batch_tool_is_refused_under_r6(
    shared_placement: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    # r6 ledger T-6 (was ..._stays_allowed): the r6 ADMIT rule admits a
    # pipe only between read-only inspectors; ``xargs`` executes a program
    # per input line, so a launch piped into it is no longer one plain
    # launch. The plain launch alone stays admitted.
    _install(monkeypatch, tmp_path, _binding())
    with pytest.raises(SystemExit):
        _guard_launch(
            shared_placement,
            _IDENTITY_PREFIX + "pool run glm a /tmp glm-5.3 | xargs grep -l glm",
        )
    assert "R6_PIPELINE" in _emitted(capsys)["permissionDecisionReason"]
    _guard_launch(shared_placement, _IDENTITY_PREFIX + "pool run glm a /tmp glm-5.3")
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
    # limit); a wrapper run as a plain script argument stays observed.
    _install(monkeypatch, tmp_path, _binding())
    monkeypatch.setenv("POOL_ORCHESTRATOR_ID", "root-orch-1")
    monkeypatch.setenv("POOL_PARENT_RUN_ID", "hermes-run-7")
    monkeypatch.setenv("POOL_TASK_CLASS", "code")
    for command in (
        "python3 -m pytest tests/test_provider_orchestrator_policy.py",
        "TOOL=ls; $TOOL -la /tmp",
        "python3 /opt/mastermind/ext/slot.py glm -- run",
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


# --- rework r5: REVIEW_2329 r3 structural findings (B-1 / M-A / M-B) -----------
#
# Review-item -> test mapping (REVIEW_2329_r3.md §4; every shape the review
# named plus the obvious variants, all under a REAL armed session with the
# faithful binding installed):
#
#   B-1 (BLOCKER; r2 N-3 reopened) interpreter one-liners and computed
#   command words carrying the literal wrapper name escape the whole gate:
#     python3 -Sc/-Bc/-Ic/-uc, perl -we/-E, node -p/--eval, ruby -ne,
#     php -nr, python3 -X dev -c, osascript -l JavaScript -e .... test_r5_b1_interpreter_option_forms
#     python3 - <<'EOF' (option + heredoc feed) .............. test_r5_b1_interpreter_stdin_fed
#     python3 <<'EOF' (bare heredoc feed, no option) ......... test_r5_b1_interpreter_stdin_fed
#     echo 'code' | python3 (pipe feed) ...................... test_r5_b1_interpreter_stdin_fed
#     awk 'system("pool …")', sed e-command, jq filter ........ test_r5_b1_always_inline_interpreters
#     time/sudo -n/caffeinate/script/strace/flock/systemd-run/
#     unbuffer/ionice/doas/chrt/ssh host/su -c … $P run grok . test_r5_b1_computed_words_through_unlisted_runners
#     { $P run grok …; } (computed word inside a brace group) . test_r5_b1_computed_words_through_unlisted_runners
#     P=sub.sh; sudo -n $P glm … (non-pool wrapper shadow) ... test_r5_b1_computed_words_through_unlisted_runners
#     pool run glm a /tmp $(date +%s) and `date` arguments .... test_r5_b1_command_substitution_arguments
#     controls: script-file slot.py launch, nested faithful -c
#     launch, no-wrapper-token computed/interpreter commands,
#     inspector reads, heredoc JSON write ................... test_r5_b1_structural_refusals_stay_scoped
#
#   M-A (MAJOR; r2 N-2 residual) runtime multiplication outside do…done:
#     f() { launch; }; f; f and single-call and recursion ..... test_r5_ma_function_definition_bodies
#     function f { launch; } ................................ test_r5_ma_function_definition_bodies
#     f() ( subshell-body launch ) ........................... test_r5_ma_function_definition_bodies
#     for i in 1 2; { launch; } .............................. test_r5_ma_brace_body_loops
#     for ((i=0;i<2;i++)) { launch; } ........................ test_r5_ma_brace_body_loops
#     while read x; { launch; } .............................. test_r5_ma_brace_body_loops
#     trap 'launch' USR1; kill -USR1 $$ twice ................ test_r5_ma_trap_payloads_and_watch_repeaters
#     watch -n 60 launch and watch -g 'launch' ............... test_r5_ma_trap_payloads_and_watch_repeaters
#
#   M-B (new; M-1 class) eval/source/'.' inside the nested -c launcher:
#     X/Y-split eval "$X$Y" identity assembly (live L11) ...... test_r5_mb_nested_eval_source_dot
#     bash -c 'eval "$X"; launch' ............................ test_r5_mb_nested_eval_source_dot
#     sh -c '. ./env.sh; launch' ............................. test_r5_mb_nested_eval_source_dot
#     bash -c 'source ./env.sh; launch' ...................... test_r5_mb_nested_eval_source_dot
#     bash -c 'eval "pool run grok …"' (literal launch) ...... test_r5_mb_nested_eval_source_dot
#     control: bash -c '. ./env.sh'; launch (separate
#     process — N5-ctl2 stays allowed) ....................... test_r5_mb_separate_process_dot_stays_allowed

_R5_LAUNCH = _IDENTITY_PREFIX + "pool run glm a /tmp glm-5.3"


def _r5_armed(
    shared_placement: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _install(monkeypatch, tmp_path, _binding())


@pytest.mark.parametrize(
    "command",
    [
        # r3 E1/E2/F1/F2: bundled option clusters hide the -c.
        "python3 -Sc 'subprocess.run([\"pool\",\"run\",\"grok\",\"a\",\"/tmp\",\"grok-4.6\"])'",
        "python3 -Bc 'os.system(\"pool run grok a /tmp grok-4.6\")'",
        "python3 -Ic 'os.system(\"pool run grok a /tmp grok-4.6\")'",
        "python3 -uc 'os.system(\"pool run grok a /tmp grok-4.6\")'",
        # r3 E3/E4: perl option clusters.
        "perl -we 'exec(\"pool\",\"run\",\"grok\",\"a\",\"/tmp\",\"grok-4.6\")'",
        "perl -E 'exec(\"pool\",\"run\",\"grok\",\"a\",\"/tmp\",\"grok-4.6\")'",
        # r3 E5/E6: node short and long program options.
        "node -p 'require(\"child_process\").execSync(\"pool run grok a /tmp grok-4.6\")'",
        "node --eval 'require(\"child_process\").exec(\"pool run grok a /tmp grok-4.6\")'",
        # r3 E10/F4: ruby / php option clusters.
        "ruby -ne 'system(\"pool run grok a /tmp grok-4.6\")'",
        "php -nr 'shell_exec(\"pool run grok a /tmp grok-4.6\");'",
        # r2 F5/F6 relatives with the same delivery shape.
        "python3 -X dev -c 'os.system(\"pool run grok a /tmp grok-4.6\")'",
        "osascript -l JavaScript -e 'app.doShellScript(\"pool run grok a /tmp grok-4.6\")'",
    ],
    ids=[
        "python-Sc", "python-Bc", "python-Ic", "python-uc",
        "perl-we", "perl-E", "node-p", "node-eval",
        "ruby-ne", "php-nr", "python-X-dev-c", "osascript-e",
    ],
)
def test_r5_b1_interpreter_option_forms(
    shared_placement: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    command: str,
) -> None:
    # Structural rule: an interpreter is judged by HOW its program is
    # delivered (here: inline option text), never by which letters the
    # options spell — so every cluster/long-form variant is one class.
    _r5_armed(shared_placement, monkeypatch, tmp_path)
    with pytest.raises(SystemExit):
        _guard_launch(shared_placement, command)
    reason = _emitted(capsys)["permissionDecisionReason"]
    assert "unobservable launch" in reason
    assert "plain command" in reason


@pytest.mark.parametrize(
    "command",
    [
        # r3 E7: option + heredoc feed.
        "python3 - <<'EOF'\nimport subprocess\nsubprocess.run([\"pool\",\"run\",\"grok\"])\nEOF",
        # r3 E8: bare heredoc feed (no option word at all).
        "python3 <<'EOF'\nimport subprocess\nsubprocess.run([\"pool\",\"run\",\"grok\"])\nEOF",
        # r3 E9: pipe-fed program text.
        "echo 'import subprocess; subprocess.run([\"pool\",\"run\",\"grok\"])' | python3",
    ],
    ids=["heredoc-dash", "heredoc-bare", "pipe-fed"],
)
def test_r5_b1_interpreter_stdin_fed(
    shared_placement: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    command: str,
) -> None:
    _r5_armed(shared_placement, monkeypatch, tmp_path)
    with pytest.raises(SystemExit):
        _guard_launch(shared_placement, command)
    reason = _emitted(capsys)["permissionDecisionReason"]
    assert "unobservable launch" in reason


@pytest.mark.parametrize(
    "command",
    [
        # Interpreters whose program text is ALWAYS an inline argument.
        "awk 'BEGIN{system(\"pool run grok a /tmp grok-4.6\")}'",
        "sed 's/x/e pool run grok a \\/tmp grok-4.6/e' notes.txt # pool run grok",
        "jq --raw-output '\"pool run grok a /tmp grok-4.6\"' cfg.json",
    ],
    ids=["awk-system", "sed-e-command", "jq-filter"],
)
def test_r5_b1_always_inline_interpreters(
    shared_placement: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    command: str,
) -> None:
    # No script-file form exists for these: any invocation with a wrapper
    # token in the text is an inline-program launch.
    _r5_armed(shared_placement, monkeypatch, tmp_path)
    with pytest.raises(SystemExit):
        _guard_launch(shared_placement, command)
    assert "unobservable launch" in _emitted(capsys)["permissionDecisionReason"]


@pytest.mark.parametrize(
    "command",
    [
        # r3 N3-R: runners outside the old nine-word allowlist.
        "P=pool; time $P run grok a /tmp grok-4.6",
        "P=pool; sudo -n $P run grok a /tmp grok-4.6",
        "P=pool; caffeinate $P run grok a /tmp grok-4.6",
        "P=pool; script -q /dev/null $P run grok a /tmp grok-4.6",
        "P=pool; strace -f $P run grok a /tmp grok-4.6",
        "P=pool; flock /tmp/lock $P run grok a /tmp grok-4.6",
        "P=pool; systemd-run $P run grok a /tmp grok-4.6",
        "P=pool; unbuffer $P run grok a /tmp grok-4.6",
        "P=pool; ionice -c2 $P run grok a /tmp grok-4.6",
        "P=pool; doas $P run grok a /tmp grok-4.6",
        "P=pool; chrt -r 10 $P run grok a /tmp grok-4.6",
        "P=pool; ssh ubuntu0 $P run grok a /tmp grok-4.6",
        "P=pool; su -c '$P run grok a /tmp grok-4.6' root",
        # r3 E12/E13/E14: computed word inside a brace group.
        "P=pool; { $P run grok a /tmp grok-4.6; }",
        # Non-pool wrapper shadowed through a runner.
        "P=sub.sh; sudo -n $P grok a /tmp grok-4.6",
    ],
    ids=[
        "time", "sudo", "caffeinate", "script", "strace", "flock",
        "systemd-run", "unbuffer", "ionice", "doas", "chrt", "ssh",
        "su-c", "brace-group", "subsh-shadow",
    ],
)
def test_r5_b1_computed_words_through_unlisted_runners(
    shared_placement: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    command: str,
) -> None:
    # Structural rule (shadow substitution): when replacing a computed word
    # with a wrapper name would complete a paid launch, the launch cannot be
    # attributed — with no runner allowlist left to evade.
    _r5_armed(shared_placement, monkeypatch, tmp_path)
    with pytest.raises(SystemExit):
        _guard_launch(shared_placement, command)
    reason = _emitted(capsys)["permissionDecisionReason"]
    assert "unobservable launch" in reason
    assert "literal name" in reason


@pytest.mark.parametrize(
    "command",
    [
        _IDENTITY_PREFIX + "pool run glm a /tmp $(date +%s)",
        _IDENTITY_PREFIX + "pool run glm a /tmp `date +%s`",
    ],
    ids=["command-substitution", "backtick"],
)
def test_r5_b1_command_substitution_arguments(
    shared_placement: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    command: str,
) -> None:
    # $(…)/backticks execute inside this very shell: even as launch
    # arguments they can construct or hide a second paid launch.
    _r5_armed(shared_placement, monkeypatch, tmp_path)
    with pytest.raises(SystemExit):
        _guard_launch(shared_placement, command)
    reason = _emitted(capsys)["permissionDecisionReason"]
    assert "unobservable" in reason
    assert "command substitution" in reason


def test_r5_b1_structural_refusals_stay_scoped(
    shared_placement: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    # The structural layer must not swallow the forms it does not own:
    # the script-file interpreter launch stays OBSERVED (judged by the
    # normal launch pipeline), the nested faithful -c launch stays
    # allowed, and no-wrapper-token commands keep the documented
    # arbitrary-process limit.
    _r5_armed(shared_placement, monkeypatch, tmp_path)
    for command in (
        # Documented launch shape: slot.py through python3, no options —
        # an OBSERVED launch judged by the normal pipeline, so it carries
        # the faithful identity projection like every launch.
        _IDENTITY_PREFIX + "python3 /opt/mastermind/ext/slot.py glm -- run",
        # Faithful nested -c launch: identity prefix assignments on the
        # bash invocation itself (inherited by everything the body runs).
        _IDENTITY_PREFIX + "bash -c 'pool run glm a /tmp glm-5.3'",
        # Wrapper name present but only as data for inspectors/printers.
        "cat results.txt | grep pool",
        "{ echo grouped; }",
        # Computed/interpreter commands with NO wrapper token anywhere.
        "TOOL=ls; $TOOL -la /tmp",
        "python3 -m pytest tests/test_provider_orchestrator_policy.py",
        "jq -r '.models[]' config.json",
    ):
        _guard_launch(shared_placement, command)
        assert capsys.readouterr().out == "", command
    # r6 ledger T-7: a here-document in a command that names a wrapper is
    # refused (its body is program text for whatever reads it); write such
    # a file with a non-shell tool or without the wrapper word.
    with pytest.raises(SystemExit):
        _guard_launch(
            shared_placement,
            "cat > /tmp/pool.json <<'EOF'\n{\"pool\": \"glm\"}\nEOF",
        )
    assert "R6_HEREDOC" in _emitted(capsys)["permissionDecisionReason"]


@pytest.mark.parametrize(
    "command",
    [
        # r3 E2: defined once, called twice.
        "f() { " + _R5_LAUNCH + "; }; f; f",
        # r3 E2 single call: the body itself is still a deferred repeat.
        "f() { " + _R5_LAUNCH + "; }; f",
        # r3 E3: recursion.
        "f() { " + _R5_LAUNCH + "; f; }; f",
        # ksh/bash function keyword form.
        "function f { " + _R5_LAUNCH + "; }; f; f",
        # POSIX subshell body.
        "f() ( " + _R5_LAUNCH + " ); f; f",
    ],
    ids=["called-twice", "called-once", "recursive", "function-keyword", "subshell-body"],
)
def test_r5_ma_function_definition_bodies(
    shared_placement: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    command: str,
) -> None:
    _r5_armed(shared_placement, monkeypatch, tmp_path)
    with pytest.raises(SystemExit):
        _guard_launch(shared_placement, command)
    reason = _emitted(capsys)["permissionDecisionReason"]
    assert "runtime-multiplexed" in reason
    assert "exactly one attempt" in reason


@pytest.mark.parametrize(
    "command",
    [
        # r3 E1/E9: bash brace bodies instead of do…done.
        "for i in 1 2; { " + _R5_LAUNCH + "; }",
        "for ((i=0;i<2;i++)) { " + _R5_LAUNCH + "; }",
        "while read x; { " + _R5_LAUNCH + "; }",
    ],
    ids=["for-brace", "arith-for-brace", "while-brace"],
)
def test_r5_ma_brace_body_loops(
    shared_placement: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    command: str,
) -> None:
    _r5_armed(shared_placement, monkeypatch, tmp_path)
    with pytest.raises(SystemExit):
        _guard_launch(shared_placement, command)
    reason = _emitted(capsys)["permissionDecisionReason"]
    assert "runtime-multiplexed" in reason
    assert "exactly one attempt" in reason


@pytest.mark.parametrize(
    "command",
    [
        # r3 E12: trap fires per signal — one lexical launch, N children.
        "trap '" + _R5_LAUNCH + "' USR1; kill -USR1 $$; kill -USR1 $$",
        # r3 E4: watch repeats the launch forever.
        "watch -n 60 " + _R5_LAUNCH,
        "watch -g '" + _R5_LAUNCH + "'",
    ],
    ids=["trap-payload", "watch-interval", "watch-glob"],
)
def test_r5_ma_trap_payloads_and_watch_repeaters(
    shared_placement: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    command: str,
) -> None:
    _r5_armed(shared_placement, monkeypatch, tmp_path)
    with pytest.raises(SystemExit):
        _guard_launch(shared_placement, command)
    reason = _emitted(capsys)["permissionDecisionReason"]
    assert "runtime-multiplexed" in reason
    assert "exactly one attempt" in reason


@pytest.mark.parametrize(
    "command",
    [
        # r3 M-B / live L11: identity re-assembled inside the launcher.
        "X='export POOL_ORCH' Y='ESTRATOR_ID=root-other' bash -c "
        "'eval \"$X$Y\"; " + _IDENTITY_PREFIX + "pool run glm a /tmp glm-5.3'",
        # r3 N5-a.
        "bash -c 'eval \"$X\"; " + _IDENTITY_PREFIX + "pool run glm a /tmp glm-5.3'",
        # r3 N5-b.
        "sh -c '. ./env.sh; " + _IDENTITY_PREFIX + "pool run glm a /tmp glm-5.3'",
        # r3 N5-c.
        "bash -c 'source ./env.sh; " + _IDENTITY_PREFIX + "pool run glm a /tmp glm-5.3'",
        # eval staging even a LITERAL launch inside the nested body.
        "bash -c 'eval \"pool run grok a /tmp grok-4.6\"'",
    ],
    ids=["eval-split-identity", "eval-word", "dot-source", "source-word", "eval-literal-launch"],
)
def test_r5_mb_nested_eval_source_dot(
    shared_placement: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    command: str,
) -> None:
    _r5_armed(shared_placement, monkeypatch, tmp_path)
    with pytest.raises(SystemExit):
        _guard_launch(shared_placement, command)
    reason = _emitted(capsys)["permissionDecisionReason"]
    assert "unobservable launch environment" in reason


def test_r5_mb_separate_process_dot_is_refused_under_r6(
    shared_placement: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    # r6 ledger T-8 (was ..._stays_allowed, N5-ctl2): one LINE carrying the
    # nested source AND the launch is a compound list, refused by the r6
    # ADMIT rule. The N5-ctl2 intent survives as two separate commands:
    # the sourcing shell names no wrapper (out of scope) and the plain
    # launch is admitted.
    _r5_armed(shared_placement, monkeypatch, tmp_path)
    with pytest.raises(SystemExit):
        _guard_launch(shared_placement, "bash -c '. ./env.sh'; " + _R5_LAUNCH)
    assert "R6_COMPOUND_LIST" in _emitted(capsys)["permissionDecisionReason"]
    for command in ("bash -c '. ./env.sh'", _R5_LAUNCH):
        _guard_launch(shared_placement, command)
        assert capsys.readouterr().out == "", command


# --- rework r6: REVIEW_C_E_OPUS_20261109 A1 (findings 1-4) — ADMIT rule ---------
#
# The reviewer's adversarial-shape table, row for row, as the regression
# suite (ledger: integrations/mmos/LANE_EXECUTIVE_DIRECTOR_C3.md). Classes
# follow the review: MULT (one visible launch run N times), ID (identity
# rewritten unseen), REG (r4 refused), r5-deny (already refused by r5),
# obs-1 (honest single launch observed), deferred, doc-limit (finding 4),
# control (honest launches/reads). Expected verdicts: every MULT/ID/REG and
# r5-deny row DENY; obs-1 rows ALLOW when the shape is in the r6 admit
# grammar (exec/command/nohup/setsid/timeout/nice) and DENY otherwise
# (env -S, zsh -c, fish -c, chroot, tmux, screen — outside the closed
# grammar by design, ledger "obs-1 verdict changes"); controls ALLOW.
#
# Fail-before: MASTERMIND_R6_GUARD_UNDER_TEST=<path to a guard module> runs
# this same table against that module (verdicts only), e.g. the r5 guard
# from ``git show f6ed10a32:ops/executive_os/provider_orchestrator_guard.py``.

_R6_P = _IDENTITY_PREFIX  # faithful projected identity prefix
_R6_L = _R6_P + "pool run glm a /tmp glm-5.3"  # faithful plain launch
_R6_B = "pool run glm a /tmp glm-5.3"  # bare launch (inherited identity)
_R6_SPLIT = "X='export POOL_ORCH' Y='ESTRATOR_ID=root-other'"
_R6_PY_LOOP = "import os\nfor _ in range(3): os.system(\"" + _R6_L + "\")"

#: (id, command, expected verdict, review class, r6 code that must appear)
_R6_TABLE = [
    # --- r5 already refused these; r6 must keep refusing them ---
    ("xargs-sh-c", "printf 'a\\nb\\n' | xargs -I{} sh -c '" + _R6_L + "'",
     "deny", "r5-deny", "R6_PIPELINE"),
    ("find-exec-sh-c", "find /tmp -name '*.txt' -exec sh -c '" + _R6_L + "' \\;",
     "deny", "r5-deny", "R6_NOT_A_PLAIN_LAUNCH"),
    ("awk-BEGIN-system",
     "awk 'BEGIN{for(i=0;i<3;i++) system(\"" + _R6_L + "\")}'",
     "deny", "r5-deny", "R6_NOT_A_PLAIN_LAUNCH"),
    ("perl-e", "perl -e 'system(\"" + _R6_L + "\") for 1..3'",
     "deny", "r5-deny", "R6_NOT_A_PLAIN_LAUNCH"),
    ("ruby-e", "ruby -e '3.times { system(\"" + _R6_L + "\") }'",
     "deny", "r5-deny", "R6_NOT_A_PLAIN_LAUNCH"),
    ("node-e", "node -e 'for (let i = 0; i < 3; i++) "
     "require(\"child_process\").execSync(\"" + _R6_L + "\")'",
     "deny", "r5-deny", "R6_NOT_A_PLAIN_LAUNCH"),
    ("python3-m", "python3 -m timeit -n 3 'import os; os.system(\"" + _R6_L + "\")'",
     "deny", "r5-deny", "R6_NOT_A_PLAIN_LAUNCH"),
    ("indirection", "P=pool; Q=P; ${!Q} run glm a /tmp glm-5.3",
     "deny", "r5-deny", "R6_EXPANSION"),
    ("eval-cmdsubst", 'eval "$(echo ' + _R6_B + ')"',
     "deny", "r5-deny", "R6_COMMAND_SUBSTITUTION"),
    ("here-string-python", "python3 <<< 'import os; os.system(\"" + _R6_L + "\")'",
     "deny", "r5-deny", "R6_HEREDOC"),
    ("here-string-bash", "bash <<< '" + _R6_L + "'",
     "deny", "r5-deny", "R6_HEREDOC"),
    ("procsubst-bash", "bash <(echo '" + _R6_L + "')",
     "deny", "r5-deny", "R6_PROCESS_SUBSTITUTION"),
    ("bash-lc-eval-split", _R6_SPLIT + " bash -lc 'eval \"$X$Y\"; " + _R6_L + "'",
     "deny", "r5-deny", "R6_NESTED_SHELL"),
    ("env-bash-c-eval-split",
     "env " + _R6_SPLIT + " bash -c 'eval \"$X$Y\"; " + _R6_L + "'",
     "deny", "r5-deny", "R6_ENV_BUILTIN"),
    ("sudo-bash-c-eval", "sudo -n bash -c 'eval \"$X\"; " + _R6_L + "'",
     "deny", "r5-deny", "R6_NOT_A_PLAIN_LAUNCH"),
    ("osascript-js",
     "osascript -l JavaScript -e 'app.doShellScript(\"" + _R6_L + "\")'",
     "deny", "r5-deny", "R6_NOT_A_PLAIN_LAUNCH"),
    ("php-r", "php -r 'for ($i = 0; $i < 3; $i++) shell_exec(\"" + _R6_L + "\");'",
     "deny", "r5-deny", "R6_NOT_A_PLAIN_LAUNCH"),
    ("lua-e", "lua -e 'for i = 1, 3 do os.execute(\"" + _R6_L + "\") end'",
     "deny", "r5-deny", "R6_NOT_A_PLAIN_LAUNCH"),
    ("expect-c", "expect -c 'spawn " + _R6_B + "; expect eof'",
     "deny", "r5-deny", "R6_NOT_A_PLAIN_LAUNCH"),
    ("dash-c-eval", "dash -c 'eval \"$X\"; " + _R6_L + "'",
     "deny", "r5-deny", "R6_NESTED_SHELL"),
    ("mksh-c-eval", "mksh -c 'eval \"$X\"; " + _R6_L + "'",
     "deny", "r5-deny", "R6_NESTED_SHELL"),
    ("pwsh-c", "pwsh -c '1..3 | ForEach-Object { " + _R6_B + " }'",
     "deny", "r5-deny", "R6_NESTED_SHELL"),
    ("julia-e", "julia -e 'for i in 1:3; run(`" + _R6_B + "`); end'",
     "deny", "r5-deny", "R6_NOT_A_PLAIN_LAUNCH"),
    ("python3.12-c", "python3.12 -c 'import os; os.system(\"" + _R6_L + "\")'",
     "deny", "r5-deny", "R6_NOT_A_PLAIN_LAUNCH"),
    ("path-python-c", "/usr/bin/python3 -c 'import os; os.system(\"" + _R6_L + "\")'",
     "deny", "r5-deny", "R6_NOT_A_PLAIN_LAUNCH"),
    ("bash-norc-c-source", "bash --norc -c 'source ./forged.env; " + _R6_L + "'",
     "deny", "r5-deny", "R6_NESTED_SHELL"),
    ("bash-c-function-twice", "bash -c 'f() { " + _R6_L + "; }; f; f'",
     "deny", "r5-deny", "R6_GROUPING"),
    ("set-a-dot-top", "set -a; . ./forged.env; " + _R6_B,
     "deny", "r5-deny", "R6_ENV_BUILTIN"),
    ("BASH_ENV-export", "export BASH_ENV=./forged.env; bash -c '" + _R6_L + "'",
     "deny", "r5-deny", "R6_COMPOUND_LIST"),
    # --- obs-1 (honest single launch observed by r5) ---
    ("env-S", "env -S '" + _R6_L + "'", "deny", "obs-1", "R6_PREFIX_FORM"),
    ("exec", _R6_P + "exec " + _R6_B, "allow", "obs-1", ""),
    ("command", _R6_P + "command " + _R6_B, "allow", "obs-1", ""),
    ("zsh-c", "zsh -c '" + _R6_L + "'", "deny", "obs-1", "R6_NESTED_SHELL"),
    ("fish-c-single", "fish -c '" + _R6_L + "'", "deny", "obs-1", "R6_NESTED_SHELL"),
    ("nohup", _R6_P + "nohup " + _R6_B, "allow", "obs-1", ""),
    ("setsid", _R6_P + "setsid " + _R6_B, "allow", "obs-1", ""),
    ("timeout", _R6_P + "timeout 600 " + _R6_B, "allow", "obs-1", ""),
    ("nice", _R6_P + "nice -n 5 " + _R6_B, "allow", "obs-1", ""),
    ("chroot", _R6_P + "chroot / " + _R6_B, "deny", "obs-1", "R6_NOT_A_PLAIN_LAUNCH"),
    ("tmux", "tmux new-session -d '" + _R6_L + "'",
     "deny", "obs-1", "R6_NOT_A_PLAIN_LAUNCH"),
    ("screen", "screen -dmS lane sh -c '" + _R6_L + "'",
     "deny", "obs-1", "R6_NOT_A_PLAIN_LAUNCH"),
    ("at-now", "echo '" + _R6_L + "' | at now", "deny", "deferred", "R6_PIPELINE"),
    # --- MULT: one visible launch executed N times ---
    ("array-expansion-twice", "a=(" + _R6_B + '); "${a[@]}"; "${a[@]}"',
     "deny", "MULT", "R6_EXPANSION"),
    ("var-wordsplit-twice", "C='" + _R6_B + "'; $C; $C", "deny", "MULT", "R6_EXPANSION"),
    ("script-file-multiplied",
     "yes '" + _R6_L + "' | head -n 3 > /tmp/lane.sh; bash /tmp/lane.sh",
     "deny", "MULT", "R6_COMPOUND_LIST"),
    # One visible recipe line, three targets: make runs it three times.
    ("make-stdin", "printf 'all: a b c\\na b c:\\n\\t" + _R6_L + "\\n' | make -f -",
     "deny", "MULT", "R6_PIPELINE"),
    ("printf-format-reuse-sh-file",
     "printf '" + _R6_L + "\\n%.0s' 1 2 3 > /tmp/lane.sh; sh /tmp/lane.sh",
     "deny", "MULT", "R6_COMPOUND_LIST"),
    ("bash-lc-function-twice", "bash -lc 'f() { " + _R6_L + "; }; f; f'",
     "deny", "MULT", "R6_NESTED_SHELL"),
    ("env-bash-c-function-twice", "env bash -c 'f() { " + _R6_L + "; }; f; f'",
     "deny", "MULT", "R6_GROUPING"),
    ("busybox-sh-c-fn", "busybox sh -c 'f() { " + _R6_L + "; }; f; f'",
     "deny", "MULT", "R6_NOT_A_PLAIN_LAUNCH"),
    ("zsh-repeat", "zsh -c 'repeat 3 " + _R6_L + "'", "deny", "MULT", "R6_NESTED_SHELL"),
    ("zsh-for-short", "zsh -c 'for i (1 2 3) " + _R6_L + "'",
     "deny", "MULT", "R6_NESTED_SHELL"),
    ("fish-c-loop", "fish -c 'for i in 1 2 3; " + _R6_L + "; end'",
     "deny", "MULT", "R6_NESTED_SHELL"),
    ("tcsh-c-repeat", "tcsh -c 'repeat 3 env " + _R6_L + "'",
     "deny", "MULT", "R6_NESTED_SHELL"),
    ("func-if-body", "f() if true; then " + _R6_L + "; fi; f; f",
     "deny", "MULT", "R6_GROUPING"),
    ("func-case-body", "f() case x in x) " + _R6_L + ";; esac; f; f",
     "deny", "MULT", "R6_GROUPING"),
    ("alias-reuse", "shopt -s expand_aliases\nalias launch='" + _R6_L
     + "'\nlaunch\nlaunch", "deny", "MULT", "R6_ENV_BUILTIN"),
    ("builtin-trap", "builtin trap '" + _R6_L + "' USR1; kill -USR1 $$; kill -USR1 $$",
     "deny", "MULT", "R6_ENV_BUILTIN"),
    ("hyperfine", "hyperfine --runs 3 '" + _R6_L + "'",
     "deny", "MULT", "R6_NOT_A_PLAIN_LAUNCH"),
    ("git-bisect-run", "git bisect run env " + _R6_L,
     "deny", "MULT", "R6_NOT_A_PLAIN_LAUNCH"),
    ("entr", "ls notes.txt | entr env " + _R6_L, "deny", "MULT", "R6_PIPELINE"),
    ("launchctl-submit", "launchctl submit -l lane -- env " + _R6_L,
     "deny", "MULT", "R6_NOT_A_PLAIN_LAUNCH"),
    ("crontab", "echo '* * * * * " + _R6_L + "' | crontab -",
     "deny", "MULT", "R6_PIPELINE"),
    ("swift-stdin", "echo 'import Foundation; for _ in 0..<3 { let p = Process(); "
     "p.launchPath = \"/usr/bin/env\"; p.arguments = [\"pool\", \"run\", \"glm\"]; "
     "try! p.run() }' | swift -", "deny", "MULT", "R6_PIPELINE"),
    ("Rscript-loop", "Rscript -e 'for (i in 1:3) system(\"" + _R6_L + "\")'",
     "deny", "MULT", "R6_NOT_A_PLAIN_LAUNCH"),
    ("R-e-loop", "R -e 'for (i in 1:3) system(\"" + _R6_L + "\")'",
     "deny", "MULT", "R6_NOT_A_PLAIN_LAUNCH"),
    ("env-python3-c-loop", "env python3 -c '" + _R6_PY_LOOP + "'",
     "deny", "REG", "R6_NOT_A_PLAIN_LAUNCH"),
    ("sudo-perl-e-loop", "sudo -n perl -e 'system(\"" + _R6_L + "\") for 1..3'",
     "deny", "REG", "R6_NOT_A_PLAIN_LAUNCH"),
    ("nice-node-e", "nice node -e 'for (let i = 0; i < 3; i++) "
     "require(\"child_process\").execSync(\"" + _R6_L + "\")'",
     "deny", "REG", "R6_NOT_A_PLAIN_LAUNCH"),
    ("timeout-ruby-e", "timeout 60 ruby -e '3.times { system(\"" + _R6_L + "\") }'",
     "deny", "REG", "R6_NOT_A_PLAIN_LAUNCH"),
    ("exec-python3-c", "exec python3 -c '" + _R6_PY_LOOP + "'",
     "deny", "REG", "R6_NOT_A_PLAIN_LAUNCH"),
    ("uv-run-python-c", "uv run python -c '" + _R6_PY_LOOP + "'",
     "deny", "REG", "R6_NOT_A_PLAIN_LAUNCH"),
    ("command-awk", "command awk 'BEGIN{for(i=0;i<3;i++) system(\"" + _R6_L + "\")}'",
     "deny", "MULT", "R6_NOT_A_PLAIN_LAUNCH"),
    # --- ID: launch identity rewritten unseen ---
    ("builtin-eval-split-identity", _R6_SPLIT + '; builtin eval "$X$Y"; ' + _R6_B,
     "deny", "ID", "R6_ENV_BUILTIN"),
    ("then-eval-split-identity",
     _R6_SPLIT + '; if :; then eval "$X$Y"; fi; ' + _R6_B,
     "deny", "ID", "R6_KEYWORD"),
    ("bash-lc-dot-source", "bash -lc '. ./forged.env; " + _R6_B + "'",
     "deny", "ID", "R6_NESTED_SHELL"),
    ("env-bash-c-dot-source", "env bash -c '. ./forged.env; " + _R6_B + "'",
     "deny", "ID", "R6_ENV_BUILTIN"),
    ("bash-xc-source", "bash -xc 'source ./forged.env; " + _R6_B + "'",
     "deny", "ID", "R6_NESTED_SHELL"),
    ("builtin-source-top", "builtin source ./forged.env; " + _R6_B,
     "deny", "ID", "R6_ENV_BUILTIN"),
    ("command-dot-top", "command . ./forged.env; " + _R6_B,
     "deny", "ID", "R6_ENV_BUILTIN"),
    ("if-source-top", "if source ./forged.env; then " + _R6_B + "; fi",
     "deny", "ID", "R6_KEYWORD"),
    ("zsh-ZDOTDIR", "ZDOTDIR=/tmp/evil zsh -c '" + _R6_B + "'",
     "deny", "ID", "R6_ASSIGNMENT"),
    # --- doc-limit (finding 4): partial wrapper names now name the wrapper ---
    ("ansi-c-quoting", "$'\\x70ool' run glm a /tmp glm-5.3",
     "deny", "doc-limit", "R6_EXPANSION"),
    ("ansi-c-quoting-token-elsewhere", _R6_L + "; $'\\x70ool' run glm a /tmp glm-5.3",
     "deny", "doc-limit", "R6_COMPOUND_LIST"),
    ("param-glue", "p=po; ${p}ol run glm a /tmp glm-5.3",
     "deny", "doc-limit", "R6_EXPANSION"),
    # Still out of scope (r2 arbitrary-process limit, pinned on purpose): a
    # WHOLLY computed command word carries no wrapper name at all.
    ("computed-word-out-of-scope", "$(printf '\\160\\157\\157\\154') run glm a /tmp glm-5.3",
     "allow", "doc-limit", ""),
    ("env-word-out-of-scope", "$LAUNCHER run glm a /tmp glm-5.3",
     "allow", "doc-limit", ""),
    # --- honest controls ---
    ("control-plain-launch", _R6_L, "allow", "control", ""),
    ("control-slot-py", _R6_P + "python3 /opt/mastermind/ext/slot.py glm -- run",
     "allow", "control", ""),
    ("control-faithful-bash-c", "bash -c '" + _R6_L + "'", "allow", "control", ""),
    ("control-faithful-bash-c-outer-identity", _R6_P + "bash -c '" + _R6_B + "'",
     "allow", "control", ""),
    ("control-inherited-bare-launch", _R6_B, "allow", "control", ""),
    ("control-cat-sub-sh", "cat /opt/mastermind/ext/sub.sh", "allow", "control", ""),
    ("control-python3-m-pytest",
     "python3 -m pytest tests/test_provider_orchestrator_policy.py",
     "allow", "control", ""),
    ("control-gh-pr-view", "gh pr view 2329", "allow", "control", ""),
]


def _r6_guard_under_test():
    """The guard module the r6 table judges: this repository's guard, or —
    for fail-before evidence only — the module at
    ``MASTERMIND_R6_GUARD_UNDER_TEST``."""
    path = os.environ.get("MASTERMIND_R6_GUARD_UNDER_TEST", "").strip()
    if not path:
        return guard
    import importlib.util

    spec = importlib.util.spec_from_file_location("r6_guard_under_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_R6_GUARD = _r6_guard_under_test()


def _r6_armed_with_identity(
    shared_placement: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
    module=guard,
) -> None:
    monkeypatch.setattr(
        module, "_principal_ids",
        lambda: (os.geteuid() + 4242, frozenset()), raising=False,
    )
    _install(monkeypatch, tmp_path, _binding())
    monkeypatch.setenv("POOL_ORCHESTRATOR_ID", "root-orch-1")
    monkeypatch.setenv("POOL_PARENT_RUN_ID", "hermes-run-7")
    monkeypatch.setenv("POOL_TASK_CLASS", "code")
    monkeypatch.delenv("BASH_ENV", raising=False)
    monkeypatch.delenv("ENV", raising=False)


def _r6_verdict(module, cwd: Path, command: str, capsys) -> tuple[str, str]:
    try:
        module.guard_bash(_payload(cwd, command), {"command": command})
    except SystemExit:
        output = _emitted(capsys)
        return output.get("permissionDecision", "context"), output.get(
            "permissionDecisionReason", ""
        )
    return ("allow", "") if capsys.readouterr().out == "" else ("context", "")


@pytest.mark.parametrize("row", _R6_TABLE, ids=[row[0] for row in _R6_TABLE])
def test_r6_reviewer_adversarial_shape_table(
    shared_placement: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    row: tuple[str, str, str, str, str],
) -> None:
    _, command, expected, _, code = row
    _r6_armed_with_identity(shared_placement, monkeypatch, tmp_path, _R6_GUARD)
    verdict, reason = _r6_verdict(_R6_GUARD, shared_placement, command, capsys)
    assert verdict == expected, reason
    if _R6_GUARD is guard and expected == "deny":
        # The structural ADMIT rule is what refused, with its typed code.
        assert code in reason, reason
        assert reason.startswith(
            "Mastermind shared-placement guard: unobservable launch"
        )


def test_r6_table_covers_every_review_class() -> None:
    classes: dict[str, int] = {}
    for _, _, _, klass, _ in _R6_TABLE:
        classes[klass] = classes.get(klass, 0) + 1
    # Review totals: 31 MULT incl. 6 REG + command-awk, 9 ID, 2 doc-limit
    # (+1 finding-4 ${p}ol row and 2 pinned out-of-scope rows), 12 obs-1,
    # 1 deferred, 29 r5-deny, 8 control rows (7 controls; faithful bash -c
    # in both identity placements).
    assert classes["MULT"] + classes["REG"] == 31
    assert classes["REG"] == 6
    assert classes["ID"] == 9
    assert classes["obs-1"] == 12 and classes["deferred"] == 1
    assert classes["r5-deny"] == 29
    assert classes["doc-limit"] == 5
    assert classes["control"] == 8
    assert all(
        expected == "deny"
        for _, _, expected, klass, _ in _R6_TABLE
        if klass in ("MULT", "REG", "ID", "r5-deny", "deferred")
    )


@pytest.mark.parametrize(
    "command, code",
    [
        # Tokenizer failure refuses (never guessed).
        (_R6_L + " 'unterminated", "R6_TOKENIZE_FAILED"),
        (_R6_P + "pool run glm a\r /tmp glm-5.3", "R6_TOKENIZE_FAILED"),
        (_R6_L + " >", "R6_TOKENIZE_FAILED"),
        # Partial wrapper names glued to patterns name the wrapper.
        ("/opt/mastermind/ext/po?l run glm a /tmp glm-5.3", "R6_NOT_A_PLAIN_LAUNCH"),
        ("{p,}ool run glm a /tmp glm-5.3", "R6_NOT_A_PLAIN_LAUNCH"),
        ('"$p"ool run glm a /tmp glm-5.3', "R6_EXPANSION"),
        ("/opt/mastermind/ext/$s.sh glm a /tmp glm-5.3", "R6_EXPANSION"),
        ("$'\\160ool' run glm a /tmp glm-5.3", "R6_EXPANSION"),
        # Nested shell grammar: exactly bash/sh -c '<one plain launch>'.
        ("bash -c \"bash -c '" + _R6_B + "'\"", "R6_NESTED_SHELL"),
        ("bash -c '" + _R6_L + "' arg0", "R6_NESTED_SHELL"),
        ("bash -c -- '" + _R6_L + "'", "R6_NESTED_SHELL"),
        ("bash -c 'cat /opt/mastermind/ext/sub.sh'", "R6_NOT_A_PLAIN_LAUNCH"),
        ('bash -c "' + _R6_P + 'pool run glm $X /tmp glm-5.3"', "R6_EXPANSION"),
        # Interpreter/runner lists are not load-bearing: unlisted ones refuse.
        ("guile -c '(system \"" + _R6_L + "\")'", "R6_NOT_A_PLAIN_LAUNCH"),
        ("elixir -e 'System.cmd(\"pool\", [\"run\", \"glm\"])'", "R6_NOT_A_PLAIN_LAUNCH"),
        ("rg --pre 'pool run glm' -n x docs", "R6_NOT_A_PLAIN_LAUNCH"),
        ("less /opt/mastermind/ext/sub.sh", "R6_NOT_A_PLAIN_LAUNCH"),
        # Assignment allowlist: only literal projected identity names.
        ("FOO=1 " + _R6_L, "R6_ASSIGNMENT"),
        ("PATH=/tmp/evil:/usr/bin " + _R6_L, "unobservable launch environment"),
        ("env 'BASH_FUNC_pool%%=() { :; }' " + _R6_B, "R6_NOT_A_PLAIN_LAUNCH"),
        ("POOL_ORCHESTRATOR_ID+=-x " + _R6_B, "R6_ASSIGNMENT"),
        ("env -u POOL_ORCHESTRATOR_ID " + _R6_B, "R6_PREFIX_FORM"),
        # Transparent prefixes take no other options.
        (_R6_P + "timeout -s KILL 60 " + _R6_B, "R6_PREFIX_FORM"),
        (_R6_P + "exec -a pool " + _R6_B, "R6_PREFIX_FORM"),
        (_R6_P + "time " + _R6_B, "R6_KEYWORD"),
        # Globs/braces in launch words and unadmitted redirections.
        (_R6_P + "pool run glm a /tmp/*.txt glm-5.3", "R6_GLOB_OR_BRACE"),
        (_R6_L + " <> /tmp/lane.io", "R6_REDIRECTION"),
        # Background / subshell / brace group around a single launch.
        (_R6_L + " &", "R6_COMPOUND_LIST"),
        ("( " + _R6_L + " )", "R6_GROUPING"),
        ("{ " + _R6_L + "; }", "R6_KEYWORD"),
        ("! " + _R6_L, "R6_KEYWORD"),
        # A pipe out of a launch or into a non-inspector.
        (_R6_L + " | tee /tmp/lane.log", "R6_PIPELINE"),
        ("grep -n pool docs/x.md | sh", "R6_PIPELINE"),
        # python3 is admitted only with slot.py as its literal first operand.
        (_R6_P + "python3 -u /opt/mastermind/ext/slot.py glm -- run", "R6_NOT_A_PLAIN_LAUNCH"),
        (_R6_P + "python3 /opt/x/other.py /opt/mastermind/ext/slot.py glm",
         "R6_NOT_A_PLAIN_LAUNCH"),
    ],
)
def test_r6_admit_rule_refuses_everything_outside_the_closed_grammar(
    shared_placement: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    command: str,
    code: str,
) -> None:
    _r6_armed_with_identity(shared_placement, monkeypatch, tmp_path)
    verdict, reason = _r6_verdict(guard, shared_placement, command, capsys)
    assert verdict == "deny", command
    assert code in reason, reason


@pytest.mark.parametrize(
    "command",
    [
        # Plain redirections with literal targets.
        _R6_L + " > /tmp/lane.log 2>&1",
        _R6_L + " < /tmp/packet.txt",
        # Whitespace/comment framing and a POSIX continuation are not shapes.
        _R6_L + "\n",
        "\n" + _R6_L,
        _R6_L + "  # one bounded child",
        _R6_P + "pool ru" + _NL + "n glm a /tmp glm-5.3",
        # Quoted literal arguments and a quoted wrapper path.
        _R6_P + "pool run glm 'fix the pool; then (x) $5' /tmp glm-5.3",
        _R6_P + 'pool run glm "fix the pool; then (x)" /tmp glm-5.3',
        _R6_P + '"/opt/mastermind/ext/sub.sh" glm a /tmp glm-5.3',
        # Stacked transparent prefixes and env identity assignments.
        "env " + _R6_P + "nohup nice -n 5 timeout 90m " + _R6_B,
        "exec env " + _R6_P + _R6_B,
        # Inspector-only reads (single and piped) naming a wrapper.
        "grep -n 'pool run' docs/runbook.md | head -5",
        "ls /opt/mastermind/ext/*.sh",
        "echo pool",
        # Non-launch wrapper invocations stay plain invocations.
        "pool status",
        "/opt/mastermind/ext/sub.sh __launch_plan glm /tmp",
    ],
)
def test_r6_admit_rule_admits_the_closed_grammar(
    shared_placement: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    command: str,
) -> None:
    _r6_armed_with_identity(shared_placement, monkeypatch, tmp_path)
    assert guard.r6_refusal_codes(command) == [], command
    verdict, reason = _r6_verdict(guard, shared_placement, command, capsys)
    assert verdict == "allow", reason


def test_r6_admitted_launch_still_reaches_every_binding_check(
    shared_placement: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    # Admission is structural only: an admitted plain launch is still held
    # to the binding gate (stale fence, projection, token equality, count).
    _r6_armed_with_identity(shared_placement, monkeypatch, tmp_path)
    substituted = _R6_P + "pool run grok a /tmp grok-4.6"
    assert guard.r6_refusal_codes(substituted) == []
    assert _r6_verdict(guard, shared_placement, substituted, capsys)[1].count(
        "provider substitution") == 1
    rerooted = "POOL_ORCHESTRATOR_ID=root-other " + _R6_B
    assert "server-derived projection" in _r6_verdict(
        guard, shared_placement, rerooted, capsys)[1]
    # A second wrapper invocation inside a quoted argument is still counted.
    nested_text = _R6_P + 'pool run glm "then pool run glm b" /tmp glm-5.3'
    assert guard.r6_refusal_codes(nested_text) == []
    assert "unaccounted descendant" in _r6_verdict(
        guard, shared_placement, nested_text, capsys)[1]
    current = _binding(fence_counter=3)
    _install(monkeypatch, tmp_path, _binding(fence_counter=2),
             receipt=_receipt(current, fence_counter=3))
    assert "stale fence" in _r6_verdict(guard, shared_placement, _R6_L, capsys)[1]


def test_r6_nested_shell_refused_when_the_session_sets_bash_env(
    shared_placement: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _r6_armed_with_identity(shared_placement, monkeypatch, tmp_path)
    faithful = "bash -c '" + _R6_L + "'"
    assert _r6_verdict(guard, shared_placement, faithful, capsys)[0] == "allow"
    monkeypatch.setenv("BASH_ENV", "/tmp/forged.env")
    verdict, reason = _r6_verdict(guard, shared_placement, faithful, capsys)
    assert verdict == "deny" and "BASH_ENV" in reason and "R6_NESTED_SHELL" in reason


def test_r6_scope_stays_the_documented_wrapper_name_limit() -> None:
    # In scope: literal names, decoded ANSI-C, expansion/glob-glued partials.
    for command in (
        "cat sub.sh", "x=pool", "$'\\x70ool' run", "${p}ol run", "po?l run",
        "{p,}ool run", "$(echo p)ool run", "/opt/x/$s.sh glm", "p'oo'l run",
    ):
        assert guard.r6_names_wrapper(command), command
    # Out of scope (REVIEW_2329 r2 arbitrary-process limit): no wrapper name.
    for command in (
        "$W run glm", "$(printf x) run glm", "ls *.sh", "python3 *.py",
        "pytest tests/test_provider_orchestrator_policy.py", "gh pr view 2329",
        "echo pool_ref", "TOOL=ls; $TOOL -la /tmp",
    ):
        assert not guard.r6_names_wrapper(command), command


def test_r6_dead_interpreter_lists_are_gone() -> None:
    # Finding 1 (R|Rscript dead regex): the r5 interpreter/always-inline
    # head regexes are deleted — no list is load-bearing under r6.
    for name in ("_INTERPRETER_HEAD_RE", "_ALWAYS_INLINE_HEAD_RE",
                 "_deny_structurally_unobservable", "_SHELL_FEED_RE"):
        assert not hasattr(guard, name), name
