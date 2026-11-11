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
        if command in _R12_ARMED_FLIPS:
            # r12 (re-check #7): a shell construct in an ARMED session is
            # judged by the ADMIT grammar — this computed command word is
            # refused now (C11 ledger, "armed flips").
            with pytest.raises(SystemExit):
                guard.guard_bash(_payload(shared_placement, command), {"command": command})
            assert guard._R12_HEADLINE in _emitted(capsys)["permissionDecisionReason"], command
            continue
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
        if command in _R12_ARMED_FLIPS:
            # r12 (re-check #7): armed, a shell construct (quoted or not)
            # puts the command in scope; these are not admitted forms.
            with pytest.raises(SystemExit):
                _guard_launch(shared_placement, command)
            assert guard._R12_HEADLINE in _emitted(capsys)["permissionDecisionReason"], command
            continue
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
    # Out of scope through r11 (r2 arbitrary-process limit, pinned on
    # purpose): a WHOLLY computed command word carries no wrapper name at
    # all. r12 (re-check #7): in an ARMED session the substitution itself is
    # a shell construct, so both are judged — and refused — structurally
    # (C11 ledger, "armed flips"; the ids keep their r6 names).
    ("computed-word-out-of-scope", "$(printf '\\160\\157\\157\\154') run glm a /tmp glm-5.3",
     "deny", "doc-limit", "R12_SHELL_CONSTRUCT"),
    ("env-word-out-of-scope", "$LAUNCHER run glm a /tmp glm-5.3",
     "deny", "doc-limit", "R12_SHELL_CONSTRUCT"),
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


def test_binding_gate_admits_v1_1_native_binding_and_refuses_other_labels():
    """The claim seam issues ExecutionBinding.v1.1 for t3-native routes (same
    v1 required fields plus the sparse native-runtime extension). The gate's
    restated shape law admits both labels and refuses anything else, so a
    lawful t3-native launch reaches the binding/identity checks instead of
    dying at the schema label (Director C2 E2E finding)."""
    from ops.executive_os import provider_orchestrator_guard as guard
    base = {
        "root_run_ref": "runs/root-1", "immediate_parent_run_ref": "runs/root-1",
        "logical_child_key": "child-1", "request_digest": "a" * 64,
        "fence_counter": 3, "assignment_generation": 1,
    }
    assert guard._binding_problems({**base, "schema": "ExecutionBinding.v1"}, "env") == ""
    assert guard._binding_problems({**base, "schema": "ExecutionBinding.v1.1",
        "runtime_kind": "t3-native", "operation_key": "b" * 64,
        "caller_namespace": ""}, "env") == ""
    for label in ("ExecutionBinding.v2", "ExecutionBinding.v1.2", "", "ExecutionBinding"):
        problem = guard._binding_problems({**base, "schema": label}, "env")
        assert problem.startswith("env: schema must be ExecutionBinding.v1"), (label, problem)


# --- r7: the parse drives the binding gate (REVIEW2 A1 findings 1-6) ---------
#
# The distinct r6 review recorded row NAMES, prose and verdict columns, not
# command text. Each command below is reconstructed from the row name, the
# finding text that cites it and the reviewer's columns (ledger
# LANE_EXECUTIVE_DIRECTOR_C5.md states each reconstruction). Columns:
#   bound   verdict with the faithful binding + owner-channel receipt
#   nobind  verdict with the session armed but NO binding projected
#   gate    whether validate_execution_binding was reached (same in both
#           runs; instrumented by a spy around the module attribute)
# Identity is inherited from the session (projection values) unless the
# command sets it. ``frag`` must appear in the bound refusal reason (and,
# for structural refusals, in the nobind one too).
#
# Fail-before: MASTERMIND_R6_GUARD_UNDER_TEST=<guard module path> runs these
# tables against that module (verdicts + gate flags), e.g. the r6 guard from
# ``git show 29a82f779:ops/executive_os/provider_orchestrator_guard.py`` (r7 lane base).

_R7_G = "grok a /tmp grok-4"
_R7_EXT = "/opt/mastermind/ext/"
_R7_BAD_ROOT = "POOL_PARENT_RUN_ID=hermes-run-7 POOL_TASK_CLASS=code pool run glm a /tmp glm-5.3"

#: (id, command, bound, nobind, gate, class, frag)
_R7_REVIEW2_TABLE = [
    # --- finding 1 (BLOCKER): redirection seams before/among the arguments ---
    ("seam-redir-before-mode-pool", "pool </dev/null run " + _R7_G,
     "deny", "deny", False, "seam", "R6_REDIRECTION"),
    ("seam-redir-before-mode-pool-out", "pool >/tmp/lane.out run " + _R7_G,
     "deny", "deny", False, "seam", "R6_REDIRECTION"),
    ("seam-fd-dup-before-mode", "pool 2>&1 run " + _R7_G,
     "deny", "deny", False, "seam", "R6_REDIRECTION"),
    ("seam-redir-after-run", "pool run </dev/null " + _R7_G,
     "deny", "deny", False, "seam", "R6_REDIRECTION"),
    ("seam-redir-subsh", _R7_EXT + "sub.sh </dev/null " + _R7_G,
     "deny", "deny", False, "seam", "R6_REDIRECTION"),
    ("seam-redir-remote-sub",
     _R7_EXT + "remote_sub.sh </dev/null mini2 grok /tmp/p.txt /repo grok-4",
     "deny", "deny", False, "seam", "R6_REDIRECTION"),
    ("seam-redir-slot", "python3 " + _R7_EXT + "slot.py </dev/null grok -- run",
     "deny", "deny", False, "seam", "R6_REDIRECTION"),
    ("seam-redir-nested", "bash -c 'pool </dev/null run " + _R7_G + "'",
     "deny", "deny", False, "seam", "R6_REDIRECTION"),
    ("seam-redir-target-named-cat", ">/tmp/cat pool run " + _R7_G,
     "deny", "deny", False, "seam", "R6_REDIRECTION"),
    ("seam-redir-target-named-grep-subsh", ">/tmp/grep " + _R7_EXT + "sub.sh " + _R7_G,
     "deny", "deny", False, "seam", "R6_REDIRECTION"),
    ("fd-close-before-mode", "pool 0<&- run " + _R7_G,
     "deny", "deny", False, "seam", "R6_REDIRECTION"),
    ("quoted-run-redirect", "pool r''un </dev/null " + _R7_G,
     "deny", "deny", False, "seam", "R6_REDIRECTION"),
    # --- finding 2 (MAJOR): provider substitution through a misread head ---
    ("head-misread-via-taskclass-value",
     "POOL_TASK_CLASS='code cat' POOL_ORCHESTRATOR_ID=root-orch-1 "
     "POOL_PARENT_RUN_ID=hermes-run-7 pool run " + _R7_G,
     "deny", "deny", True, "id", "unaccounted descendant"),
    # --- finding 3 (MAJOR): identity values read exactly ---
    ("id-dq-then-sq-space", "POOL_ORCHESTRATOR_ID=\"root-orch-1\"' evil' " + _R7_BAD_ROOT,
     "deny", "deny", True, "id", "'root-orch-1 evil'"),
    ("id-dq-dq-space", "POOL_ORCHESTRATOR_ID=\"root-orch-1\"\" evil\" " + _R7_BAD_ROOT,
     "deny", "deny", True, "id", "'root-orch-1 evil'"),
    ("id-parent-sq-esc-space",
     "POOL_ORCHESTRATOR_ID=root-orch-1 POOL_PARENT_RUN_ID='hermes-run-7'\\ evil "
     "POOL_TASK_CLASS=code pool run glm a /tmp glm-5.3",
     "deny", "deny", True, "id", "'hermes-run-7 evil'"),
    ("id-env-prefix", "env POOL_ORCHESTRATOR_ID=\"root-orch-1\"' evil' " + _R7_BAD_ROOT,
     "deny", "deny", True, "id", "'root-orch-1 evil'"),
    ("id-nested-body",
     "bash -c \"POOL_ORCHESTRATOR_ID='root-orch-1'' evil' " + _R7_BAD_ROOT + "\"",
     "deny", "deny", True, "id", "'root-orch-1 evil'"),
    # The reviewer's ALLOW needs r6's first-quoted-span reader: "…"'>x'.
    ("id-gt-no-space", "POOL_ORCHESTRATOR_ID=\"root-orch-1\"'>x' " + _R7_BAD_ROOT,
     "deny", "deny", True, "id", "'root-orch-1>x'"),
    ("id-gt-unquoted", "POOL_ORCHESTRATOR_ID=root-orch-1'>x' " + _R7_BAD_ROOT,
     "deny", "deny", True, "id", "'root-orch-1>x'"),
    # --- finding 4 (MINOR): scope false negatives ---
    ("scope-param-default", "${x:-pool} run " + _R7_G,
     "deny", "deny", False, "scope", "R6_EXPANSION"),
    ("scope-param-default-nocolon", "${x-pool} run " + _R7_G,
     "deny", "deny", False, "scope", "R6_EXPANSION"),
    ("scope-param-default-subsh", "${x:-sub.sh} " + _R7_G,
     "deny", "deny", False, "scope", "R6_EXPANSION"),
    ("scope-zsh-empty-name", "${:-pool} run " + _R7_G,
     "deny", "deny", False, "scope", "R6_EXPANSION"),
    ("scope-locale-empty", 'p$""ool run ' + _R7_G,
     "deny", "deny", False, "scope", "R6_EXPANSION"),
    ("scope-locale-glue", 'p$"o"ol run ' + _R7_G,
     "deny", "deny", False, "scope", "R6_EXPANSION"),
    ("scope-glob-1char", "p* run " + _R7_G,
     "deny", "deny", False, "scope", "R6_NOT_A_PLAIN_LAUNCH"),
    ("scope-glob-head-wildcard", "???? run " + _R7_G,
     "deny", "deny", False, "scope", "R6_NOT_A_PLAIN_LAUNCH"),
    # Homoglyph (Cyrillic er): names a DIFFERENT file; only a staged binary
    # of that name could run (staged-file limit). Pinned out of scope.
    ("scope-homoglyph", "рool run " + _R7_G,
     "allow", "allow", False, "doc-limit", ""),
    # --- finding 5 (MINOR): read forms write only to /dev/null ---
    ("insp-echo-zshenv",
     "echo 'pool() { command pool \"$@\"; command pool \"$@\"; }' >> ~/.zshenv",
     "deny", "deny", False, "insp", "R6_REDIRECTION"),
    ("insp-echo-bashrc",
     "echo 'pool() { command pool \"$@\"; command pool \"$@\"; }' >> ~/.bashrc",
     "deny", "deny", False, "insp", "R6_REDIRECTION"),
    ("insp-cat-copy-wrapper", "cat " + _R7_EXT + "sub.sh > /tmp/evil/sub.sh",
     "deny", "deny", False, "insp", "R6_REDIRECTION"),
    ("insp-pipe-write", "cat " + _R7_EXT + "sub.sh | head -c 100000 > /tmp/evil/sub.sh",
     "deny", "deny", False, "insp", "R6_REDIRECTION"),
    ("insp-pipe-append-zshenv", "echo 'pool run " + _R7_G + "' | cat >> ~/.zshenv",
     "deny", "deny", False, "insp", "R6_REDIRECTION"),
    ("insp-devtcp", "cat " + _R7_EXT + "sub.sh > /dev/tcp/127.0.0.1/9",
     "deny", "deny", False, "insp", "R6_REDIRECTION"),
    ("insp-xxd-r", "xxd -r -p /tmp/pool.hex /tmp/evil/pool",
     "deny", "deny", False, "insp", "R6_NOT_A_PLAIN_LAUNCH"),
    ("insp-tail-f", "tail -f /tmp/lane/pool",
     "deny", "deny", False, "insp", "R6_NOT_A_PLAIN_LAUNCH"),
    # --- finding 6 (MINOR): head paths and spellings ---
    ("path-prefix-env", "/tmp/evil/env " + _R6_P + _R6_B,
     "deny", "deny", False, "path", "R6_HEAD_SPELLING"),
    ("path-prefix-nohup", _R6_P + "./nohup " + _R6_B,
     "deny", "deny", False, "path", "R6_HEAD_SPELLING"),
    ("upper-NICE", _R6_P + "NICE -n 5 " + _R6_B,
     "deny", "deny", False, "path", "R6_HEAD_SPELLING"),
    ("path-bash-staged", "/tmp/evil/bash -c '" + _R6_L + "'",
     "deny", "deny", False, "path", "R6_HEAD_SPELLING"),
    ("path-python-staged", _R6_P + "/tmp/evil/python3 " + _R7_EXT + "slot.py glm -- run",
     "deny", "deny", False, "path", "R6_HEAD_SPELLING"),
    ("upper-PYTHON3", _R6_P + "PYTHON3 " + _R7_EXT + "slot.py glm -- run",
     "deny", "deny", False, "path", "R6_HEAD_SPELLING"),
    ("path-inspector-staged", "/tmp/evil/cat " + _R7_EXT + "sub.sh",
     "deny", "deny", False, "path", "R6_HEAD_SPELLING"),
    ("slot-python2-literal", _R6_P + "python2 " + _R7_EXT + "slot.py glm -- run",
     "deny", "deny", False, "path", "R6_NOT_A_PLAIN_LAUNCH"),
    # Admitted ON PURPOSE (each reaches the binding gate; ledger judgement):
    ("path-wrapper", _R6_P + _R7_EXT + "pool run glm a /tmp glm-5.3",
     "allow", "deny", True, "on-purpose", ""),
    ("path-prefix-system-env", "/usr/bin/env " + _R6_P + _R6_B,
     "allow", "deny", True, "on-purpose", ""),
    ("nested-comment", "bash -c '" + _R6_L + " # one bounded child'",
     "allow", "deny", True, "on-purpose", ""),
    ("nested-bs-newline-in-sq", "bash -c '" + _R6_P + "pool ru" + _NL + "n glm a /tmp glm-5.3'",
     "allow", "deny", True, "on-purpose", ""),
    ("nested-trailing-redirect", "bash -c '" + _R6_L + "' > /tmp/lane.log 2>&1",
     "allow", "deny", True, "on-purpose", ""),
    ("nested-sh", "sh -c '" + _R6_L + "'", "allow", "deny", True, "on-purpose", ""),
    ("nested-bash-path", "/bin/bash -c '" + _R6_L + "'",
     "allow", "deny", True, "on-purpose", ""),
    ("slot-staged-path", _R6_P + "python3 /tmp/staged/slot.py glm -- run",
     "allow", "deny", True, "on-purpose", ""),
    ("slot-upper", _R6_P + "python3 " + _R7_EXT + "SLOT.PY glm -- run",
     "allow", "deny", True, "on-purpose", ""),
    ("slot-python2", _R6_P + "python " + _R7_EXT + "slot.py glm -- run",
     "allow", "deny", True, "on-purpose", ""),
    # --- r7 extras: zsh divergences, exact values, launch output targets ---
    ("zsh-numeric-glob", _R6_L + " <1-9> /tmp/x",
     "deny", "deny", False, "r7-extra", "R6_TOKENIZE_FAILED"),
    ("zsh-clobber-spaced", _R6_L + " >! /tmp/lane.log",
     "deny", "deny", False, "r7-extra", "R6_TOKENIZE_FAILED"),
    ("zsh-clobber-glued", _R6_L + " >!/tmp/lane.log",
     "deny", "deny", False, "r7-extra", "R6_TOKENIZE_FAILED"),
    ("id-tilde-value", "POOL_ORCHESTRATOR_ID=~root-orch-1 " + _R7_BAD_ROOT,
     "deny", "deny", False, "r7-extra", "R6_ASSIGNMENT"),
    ("id-env-glob-value", "env POOL_ORCHESTRATOR_ID=root-orch-? " + _R7_BAD_ROOT,
     "deny", "deny", False, "r7-extra", "R6_ASSIGNMENT"),
    ("id-trailing-space", "POOL_ORCHESTRATOR_ID='root-orch-1 ' " + _R7_BAD_ROOT,
     "deny", "deny", True, "r7-extra", "'root-orch-1 '"),
    ("launch-writes-zshenv", _R6_L + " > ~/.zshenv",
     "deny", "deny", False, "r7-extra", "R6_REDIRECTION"),
    ("launch-overwrites-wrapper", _R6_L + " >> ~/.local/bin/pool",
     "deny", "deny", False, "r7-extra", "R6_REDIRECTION"),
    ("launch-devtcp", _R6_L + " > /dev/tcp/127.0.0.1/9",
     "deny", "deny", False, "r7-extra", "R6_REDIRECTION"),
    ("read-devtcp-input", "cat < /dev/tcp/127.0.0.1/9 " + _R7_EXT + "sub.sh",
     "deny", "deny", False, "r7-extra", "R6_REDIRECTION"),
    ("glued-pager-launch", "git grep -O'pool run " + _R7_G + "' x",
     "deny", "deny", False, "r7-extra", "R6_NOT_A_PLAIN_LAUNCH"),
    ("glued-pager-name", "git grep -Opool x",
     "deny", "deny", False, "r7-extra", "R6_NOT_A_PLAIN_LAUNCH"),
    ("pool-helper-reaches-gate", "pool status",
     "allow", "deny", True, "r7-extra", ""),
    ("subsh-helper-reaches-gate", _R7_EXT + "sub.sh __launch_plan glm /tmp",
     "allow", "deny", True, "r7-extra", ""),
    # --- honest controls ---
    ("control-plain-launch", _R6_L, "allow", "deny", True, "control", ""),
    ("control-trailing-redirects", _R6_L + " > /tmp/lane.log 2>&1 </dev/null",
     "allow", "deny", True, "control", ""),
    ("control-inherited-bare-launch", _R6_B, "allow", "deny", True, "control", ""),
    ("control-env-prefix", "env " + _R6_P + "nohup nice -n 5 timeout 90m " + _R6_B,
     "allow", "deny", True, "control", ""),
    ("control-slot", _R6_P + "python3 " + _R7_EXT + "slot.py glm -- run",
     "allow", "deny", True, "control", ""),
    ("control-pool-remote",
     _R6_P + "pool remote mini2 glm /tmp/p.txt /repo glm-5.3",
     "allow", "deny", True, "control", ""),
    ("control-cat", "cat " + _R7_EXT + "sub.sh", "allow", "allow", False, "control", ""),
    ("control-grep-pipe", "grep -n 'pool run' docs/runbook.md | head -5 2>/dev/null",
     "allow", "allow", False, "control", ""),
    ("control-ls-stderr", "ls -la ~/.local/bin/pool 2>/dev/null",
     "allow", "allow", False, "control", ""),
    ("control-echo-fd", "echo pool >&2", "allow", "allow", False, "control", ""),
    ("control-wc-input", "wc -l < " + _R7_EXT + "sub.sh",
     "allow", "allow", False, "control", ""),
    ("control-gh-pr-view", "gh pr view 2329", "allow", "allow", False, "control", ""),
    ("control-pytest-m", "python3 -m pytest tests/test_provider_orchestrator_policy.py",
     "allow", "allow", False, "control", ""),
    # Over-refusals the review confirmed and r7 keeps (no safe carve-out).
    ("overrefusal-pytest-k", "pytest -k pool", "deny", "deny", False, "over-refusal",
     "R6_NOT_A_PLAIN_LAUNCH"),
    ("overrefusal-which", "which pool", "deny", "deny", False, "over-refusal",
     "R6_NOT_A_PLAIN_LAUNCH"),
    ("overrefusal-command-v", "command -v pool", "deny", "deny", False, "over-refusal",
     "R6_PREFIX_FORM"),
    ("overrefusal-cd-and", "cd /tmp && " + _R6_L, "deny", "deny", False, "over-refusal",
     "R6_COMPOUND_LIST"),
    ("overrefusal-trailing-semicolon", _R6_L + ";", "deny", "deny", False,
     "over-refusal", "R6_COMPOUND_LIST"),
    ("overrefusal-gh-pipe-grep", "gh pr view 1 | grep pool", "deny", "deny", False,
     "over-refusal", "R6_PIPELINE"),
]


def _r7_gate_spy(monkeypatch: pytest.MonkeyPatch, module) -> list[str]:
    calls: list[str] = []
    original = module.validate_execution_binding

    def spy(command, *args, **kwargs):
        calls.append(command)
        return original(command, *args, **kwargs)

    monkeypatch.setattr(module, "validate_execution_binding", spy)
    return calls


def _r7_judge(
    module, cwd: Path, command: str, capsys, monkeypatch, *, bound: bool,
    binding: dict[str, object],
) -> tuple[str, str, bool]:
    """(verdict, reason, gate reached) through the module's real guard_bash."""
    if bound:
        monkeypatch.setenv("POOL_EXECUTION_BINDING", json.dumps(binding))
    else:
        monkeypatch.delenv("POOL_EXECUTION_BINDING", raising=False)
    calls = _r7_gate_spy(monkeypatch, module)
    verdict, reason = _r6_verdict(module, cwd, command, capsys)
    return verdict, reason, bool(calls)


def _r7_both(module, shared_placement, monkeypatch, tmp_path, capsys, command):
    _r6_armed_with_identity(shared_placement, monkeypatch, tmp_path, module)
    binding = _binding()
    bound = _r7_judge(module, shared_placement, command, capsys, monkeypatch,
                      bound=True, binding=binding)
    nobind = _r7_judge(module, shared_placement, command, capsys, monkeypatch,
                       bound=False, binding=binding)
    return bound, nobind


@pytest.mark.parametrize("row", _R7_REVIEW2_TABLE, ids=[row[0] for row in _R7_REVIEW2_TABLE])
def test_r7_review2_table_bound_nobind_and_gate(
    shared_placement: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    row: tuple,
) -> None:
    _, command, bound_expected, nobind_expected, gate, _, frag = row
    (bound, bound_reason, bound_gate), (nobind, nobind_reason, nobind_gate) = _r7_both(
        _R6_GUARD, shared_placement, monkeypatch, tmp_path, capsys, command
    )
    assert (bound, nobind) == (bound_expected, nobind_expected), (bound_reason, nobind_reason)
    assert (bound_gate, nobind_gate) == (gate, gate), (bound_reason, nobind_reason)
    if _R6_GUARD is guard:
        if frag:
            assert frag in bound_reason, bound_reason
        if bound_expected == "deny" and not gate:
            assert frag in nobind_reason, nobind_reason
            assert bound_reason.startswith(
                "Mastermind shared-placement guard: unobservable launch"
            )
        if nobind_expected == "deny" and gate:
            assert "missing binding" in nobind_reason, nobind_reason


def test_r7_review2_table_covers_every_reviewer_row() -> None:
    ids = {row[0] for row in _R7_REVIEW2_TABLE}
    reviewer_rows = {
        "seam-redir-before-mode-pool", "seam-redir-before-mode-pool-out",
        "seam-fd-dup-before-mode", "seam-redir-after-run", "seam-redir-subsh",
        "seam-redir-remote-sub", "seam-redir-slot", "seam-redir-nested",
        "seam-redir-target-named-cat", "seam-redir-target-named-grep-subsh",
        "id-dq-then-sq-space", "id-dq-dq-space", "id-parent-sq-esc-space",
        "id-env-prefix", "id-nested-body", "scope-param-default",
        "scope-param-default-nocolon", "scope-zsh-empty-name",
        "scope-locale-empty", "scope-locale-glue", "scope-glob-1char",
        "scope-homoglyph", "path-prefix-env", "path-prefix-nohup",
        "path-wrapper", "upper-NICE", "nested-comment",
        "nested-bs-newline-in-sq", "nested-trailing-redirect", "nested-sh",
        "nested-bash-path", "slot-staged-path", "slot-upper", "slot-python2",
        "insp-echo-zshenv", "insp-echo-bashrc", "insp-cat-copy-wrapper",
        "insp-pipe-write", "insp-devtcp", "insp-xxd-r", "insp-tail-f",
        "fd-close-before-mode", "quoted-run-redirect", "id-gt-no-space",
        "head-misread-via-taskclass-value",
    }
    assert reviewer_rows <= ids, sorted(reviewer_rows - ids)
    assert len(ids) == len(_R7_REVIEW2_TABLE)
    # Every reviewer row that r6 allowed with ZERO binding check ("n") is a
    # structural DENY now, except the pinned homoglyph limit.
    for _, _, bound, nobind, gate, klass, _ in _R7_REVIEW2_TABLE:
        if klass in ("seam", "scope", "insp", "path"):
            assert (bound, nobind, gate) == ("deny", "deny", False)


# --- r7: the 95 r6 rows again, now with the nobind run and the gate flag ----

#: r6 rows that ARE launches (every other admitted row is a read or out of scope).
_R7_R6_LAUNCH_ROWS = frozenset({
    "exec", "command", "nohup", "setsid", "timeout", "nice",
    "control-plain-launch", "control-slot-py", "control-faithful-bash-c",
    "control-faithful-bash-c-outer-identity", "control-inherited-bare-launch",
})


@pytest.mark.parametrize("row", _R6_TABLE, ids=[row[0] for row in _R6_TABLE])
def test_r7_r6_table_rows_with_gate_instrumentation(
    shared_placement: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    row: tuple[str, str, str, str, str],
) -> None:
    name, command, expected, _, _ = row
    launch = name in _R7_R6_LAUNCH_ROWS
    (bound, bound_reason, bound_gate), (nobind, nobind_reason, nobind_gate) = _r7_both(
        _R6_GUARD, shared_placement, monkeypatch, tmp_path, capsys, command
    )
    assert bound == expected, bound_reason
    # A refused row is refused structurally (gate never reached); an
    # admitted launch always reaches it; reads/out-of-scope never do.
    assert bound_gate == nobind_gate == (expected == "allow" and launch)
    assert nobind == ("deny" if expected == "deny" or launch else "allow"), nobind_reason
    if launch:
        assert "missing binding" in nobind_reason, nobind_reason


# --- r7: every admitted launch shape reaches the gate with the PARSED token ---

_R7_ADMITTED_LAUNCH_SHAPES = [
    _R6_P + "pool run {pool} a /tmp m",
    _R6_P + "pool run {pool} a /tmp m > /tmp/lane.log 2>&1",
    _R6_P + "pool run {pool} a /tmp m < /tmp/packet.txt",
    "env " + _R6_P + "pool run {pool} a /tmp m",
    "/usr/bin/env " + _R6_P + "nohup pool run {pool} a /tmp m",
    _R6_P + "nice -n 5 timeout 90m setsid pool run {pool} a /tmp m",
    _R6_P + "exec command pool run {pool} a /tmp m",
    _R6_P + _R7_EXT + "pool run {pool} a /tmp m",
    _R6_P + "pool remote mini2 {pool} /tmp/p.txt /repo m",
    _R6_P + _R7_EXT + "sub.sh {pool} a /tmp m",
    _R6_P + _R7_EXT + "remote_sub.sh mini2 {pool} /tmp/p.txt /repo m",
    _R6_P + "python3 " + _R7_EXT + "slot.py {pool} -- run",
    _R6_P + "python3.12 " + _R7_EXT + "slot.py {pool} -- run",
    _R6_P + "pool ru" + _NL + "n {pool} a /tmp m",
    _R6_P + "pool 'run' \"{pool}\" a /tmp m",
    "bash -c '" + _R6_P + "pool run {pool} a /tmp m'",
    "sh -c '" + _R6_P + "pool run {pool} a /tmp m' 2>/dev/null",
    _R6_P + "/bin/bash -c 'pool run {pool} a /tmp m'",
]


@pytest.mark.parametrize("shape", _R7_ADMITTED_LAUNCH_SHAPES)
def test_r7_every_admitted_launch_shape_reaches_every_binding_check(
    shared_placement: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    shape: str,
) -> None:
    # Closes the r6 coverage gap (only trailing redirections were exercised):
    # each admitted shape is parsed, censused and token-checked by the gate.
    _r6_armed_with_identity(shared_placement, monkeypatch, tmp_path)
    faithful, substituted = shape.format(pool="glm"), shape.format(pool="grok")
    parse = guard.r7_parse(faithful)
    assert parse is not None and not parse.refused, parse and parse.codes
    assert len(parse.launches) == 1
    calls = _r7_gate_spy(monkeypatch, guard)
    assert _r6_verdict(guard, shared_placement, faithful, capsys)[0] == "allow"
    verdict, reason = _r6_verdict(guard, shared_placement, substituted, capsys)
    assert verdict == "deny" and "provider substitution" in reason, reason
    assert len(calls) == 2
    # The parse census and the r4 text view agree on every admitted shape.
    assert [(w, t) for w, t, _ in guard._r7_census(parse)] == [
        (w, t) for _, w, t, _ in guard._wrapper_invocations(faithful)
    ]
    # A stale fence and a re-rooted identity are refused on the same shape.
    current = _binding(fence_counter=3)
    _install(monkeypatch, tmp_path, _binding(fence_counter=2),
             receipt=_receipt(current, fence_counter=3))
    assert "stale fence" in _r6_verdict(guard, shared_placement, faithful, capsys)[1]


def test_r7_census_disagreement_is_refused_as_unaccounted(
    shared_placement: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _r6_armed_with_identity(shared_placement, monkeypatch, tmp_path)
    # The text view sees a second invocation the parse reads as task text.
    for command in (
        _R6_P + 'pool run glm "then pool run glm b" /tmp glm-5.3',
        _R6_P + 'pool run glm "see sub.sh grok" /tmp glm-5.3',
        _R6_P + "pool run 'glm grok' a /tmp glm-5.3",
    ):
        verdict, reason = _r6_verdict(guard, shared_placement, command, capsys)
        assert verdict == "deny" and (
            "unaccounted descendant" in reason or "provider substitution" in reason
        ), reason
    # The gate refuses, never skips, when the two readings differ.
    monkeypatch.setattr(guard, "_wrapper_invocations", lambda command: [])
    verdict, reason = _r6_verdict(guard, shared_placement, _R6_L, capsys)
    assert verdict == "deny" and "unaccounted descendant" in reason, reason


def test_r7_parse_reads_exact_identity_values_everywhere() -> None:
    cases = {
        "POOL_ORCHESTRATOR_ID=\"a\"' b' pool run glm": [("POOL_ORCHESTRATOR_ID", "a b")],
        "env POOL_PARENT_RUN_ID='p'\\ q pool run glm": [("POOL_PARENT_RUN_ID", "p q")],
        "POOL_ORCHESTRATOR_ID=a'>x' pool run glm": [("POOL_ORCHESTRATOR_ID", "a>x")],
        "POOL_ORCHESTRATOR_ID=o bash -c 'POOL_ORCHESTRATOR_ID=i pool run glm'": [
            ("POOL_ORCHESTRATOR_ID", "o"), ("POOL_ORCHESTRATOR_ID", "i"),
        ],
        "POOL_TASK_CLASS=code env POOL_TASK_CLASS='code cat' pool run glm": [
            ("POOL_TASK_CLASS", "code"), ("POOL_TASK_CLASS", "code cat"),
        ],
    }
    for command, expected in cases.items():
        parse = guard.r7_parse(command)
        assert parse is not None and not parse.refused, (command, parse.codes)
        assert [launch.assignments for launch in parse.launches] == [expected], command


@pytest.mark.parametrize(
    "command",
    [
        "${x:-pool} run glm", "${x-pool} run glm", "${x:=pool} run glm",
        "${x:+pool} run glm", "${x/a/pool} run glm", "${:-pool} run glm",
        "${x:-sub.sh} glm", "${(e)x:-pool} run glm", 'p$""ool run glm',
        'p$"o"ol run glm', "p* run glm", "s*.sh glm", "???? run glm",
        "nice -n 5 p* run glm", "python3 /opt/x/s*.py glm",
    ],
)
def test_r7_scope_is_widened_per_finding_4(command: str) -> None:
    assert guard.r6_names_wrapper(command), command
    assert guard.r6_refusal_codes(command), command


def test_r7_scope_residue_stays_documented() -> None:
    # Wholly wildcard OPERANDS and other spellings stay out of scope (the
    # pinned r6 limit); command-word globs do not.
    for command in ("python3 *.py", "ls *.sh", "bash *.sh", "рool run glm", "$W run glm"):
        assert not guard.r6_names_wrapper(command), command


# --- r7 closed read forms (REVIEW2 over-refusal carve-outs) -------------------

_R7_READ_FORMS_ADMITTED = [
    'git commit -m "fix pool"',
    "git commit -am 'fix pool run cap'",
    "git commit -q -m 'pool' -- docs/pool.md",
    "git commit -F /tmp/msgs/pool",
    "git commit --amend --no-edit -- pool",
    "git --no-pager log --oneline -5 -- ~/.local/bin/pool",
    "git log -n 3 --format=%H --grep='pool run' --no-ext-diff",
    "git show --stat HEAD -- ~/.local/bin/pool",
    "git diff --stat --cached -- pool",
    "git diff -U3 --no-textconv HEAD~1 -- sub.sh",
    "git status --short -uno -- pool",
    "git status -sb pool",
    "git grep -n -e 'pool run' -- docs",
    "git grep -C2 -F slot.py",
    "git add ops/pool",
    "git add -A -- pool",
    "rg -n 'pool run' docs",
    "rg -l --hidden -g '*.md' pool",
    "rg -C2 -F 'sub.sh' ops",
    "rg --type py -e slot.py --no-config",
    "sed -n 1,40p ~/.local/bin/pool",
    "sed -n 5p " + _R7_EXT + "sub.sh",
    "git log --oneline | grep pool",
    "rg -n pool docs | head -5",
    "grep -rn pool --include=*.py ops 2>/dev/null",
    "/usr/bin/git log --oneline -- pool",
]


@pytest.mark.parametrize("command", _R7_READ_FORMS_ADMITTED)
def test_r7_read_forms_admit_closed_reads(
    shared_placement: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    command: str,
) -> None:
    (bound, bound_reason, bound_gate), (nobind, nobind_reason, nobind_gate) = _r7_both(
        guard, shared_placement, monkeypatch, tmp_path, capsys, command
    )
    assert guard.r6_names_wrapper(command), command  # in scope: judged, not skipped
    assert (bound, nobind) == ("allow", "allow"), (bound_reason, nobind_reason)
    assert not bound_gate and not nobind_gate
    parse = guard.r7_parse(command)
    assert parse is not None and not parse.refused and not parse.launches


_R7_READ_FORMS_REFUSED = [
    # git: global options, exec-capable options, other subcommands, editors.
    "git -c alias.x='!pool run grok a /tmp grok-4' x",
    "git -c core.pager='pool run grok' log",
    "git --config-env=core.pager=POOL_PAGER log -- pool",
    "git --exec-path=/tmp/pool log",
    "git -C /tmp log -- pool",
    "git grep -O'pool run grok' x",
    "git grep -Opool x",
    "git grep --open-files-in-pager='pool run grok' x",
    "git diff --ext-diff -- pool",
    "git log -p --ext-diff -- pool",
    "git log -p --textconv -- pool",
    "git show --textconv HEAD:pool",
    "git grep --textconv pool",
    "git log --output=/tmp/out -- pool",
    "git diff --output=/tmp/x -- pool",
    "git rebase --exec 'pool run grok a /tmp grok-4' HEAD~3",
    "git bisect run pool run grok a /tmp grok-4",
    "git submodule foreach 'pool run grok a /tmp grok-4'",
    "git config core.pager 'pool run grok'",
    "git commit -e -m 'pool'",
    "git commit -c HEAD -m pool",
    "git commit -S -m 'pool'",
    "git commit -- pool",
    "git add -p pool",
    "git add --edit pool",
    "git log -- *pool",
    # rg: --pre / -z / --hostname-bin and anything off the allowlist.
    "rg --pre 'pool run grok' x",
    "rg --pre=pool x",
    "rg --pre-glob '*' --pre sh pool",
    "rg -z pool x",
    "rg -nz pool x",
    "rg --search-zip pool x",
    "rg --hostname-bin=/tmp/pool x",
    "rg pool *",
    # sed: only -n N[,M]p.
    "sed -n '1e pool run grok' x",
    "sed 'e pool run grok' x",
    "sed -n 's/x/pool/ep' x",
    "sed -n 1,5w/tmp/pool x",
    "sed -i -n 1p pool",
    "sed -n 1p -- pool",
    # inspectors: ugrep exec/config options, follow, compile, xxd, globs.
    "grep --filter='*:pool run grok' -r x .",
    "grep -Q pool",
    "grep -nQ pool .",
    "grep --pager=pool x",
    "grep --config=/tmp/cfg pool x",
    "grep pool *",
    "tail -F /tmp/lane/pool",
    "tail -n 5 -f /tmp/lane/pool",
    "tail --follow=name /tmp/lane/pool",
    "file -C -m /tmp/magic/pool",
    "xxd /opt/mastermind/ext/pool",
    # read forms take no assignments, prefixes or staged paths.
    "GIT_EXTERNAL_DIFF=/tmp/x git diff -- pool",
    "env git log -- pool",
    "/opt/homebrew/bin/rg pool",
    "Git log -- pool",
]


@pytest.mark.parametrize("command", _R7_READ_FORMS_REFUSED)
def test_r7_read_forms_refuse_exec_write_and_editor_options(
    shared_placement: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    command: str,
) -> None:
    assert guard.r6_names_wrapper(command), command  # in scope: judged, not skipped
    (bound, bound_reason, bound_gate), (nobind, _, nobind_gate) = _r7_both(
        guard, shared_placement, monkeypatch, tmp_path, capsys, command
    )
    assert (bound, nobind) == ("deny", "deny"), bound_reason
    assert not bound_gate and not nobind_gate
    assert bound_reason.startswith("Mastermind shared-placement guard: unobservable launch")


def test_r7_read_form_allowlists_exclude_every_exec_capable_option() -> None:
    for spec in guard._R7_GIT_SPECS.values():
        short_flags, short_valued, long_flags, long_valued = spec
        for option in ("--ext-diff", "--textconv", "--output", "--exec",
                       "--open-files-in-pager", "--edit", "--patch-interactive",
                       "--interactive", "--gpg-sign"):
            assert option not in long_flags | long_valued, option
        assert "O" not in short_flags | short_valued
    # -c is a git GLOBAL option (refused: only --no-pager precedes the
    # subcommand) and, on commit, re-edit-in-editor; elsewhere it is count.
    assert "c" not in guard._R7_GIT_SPECS["commit"][0] | guard._R7_GIT_SPECS["commit"][1]
    assert "e" not in "".join(guard._R7_GIT_SPECS["commit"][0] | guard._R7_GIT_SPECS["commit"][1])
    assert "S" not in guard._R7_GIT_SPECS["commit"][0] | guard._R7_GIT_SPECS["commit"][1]
    assert not ({"p", "e", "i"} & (guard._R7_GIT_SPECS["add"][0] | guard._R7_GIT_SPECS["add"][1]))
    for subcommand in ("rebase", "bisect", "submodule", "config", "difftool", "-c"):
        assert subcommand not in guard._R7_GIT_SPECS
    rg_short_flags, rg_short_valued, rg_long_flags, rg_long_valued = guard._R7_RG_SPEC
    assert "z" not in rg_short_flags | rg_short_valued
    for option in ("--pre", "--pre-glob", "--search-zip", "--hostname-bin"):
        assert option not in rg_long_flags | rg_long_valued, option
    assert "xxd" not in guard._R7_READ_HEADS


def test_r7_refusal_wording_distinguishes_mentions_from_launches(
    shared_placement: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _r6_armed_with_identity(shared_placement, monkeypatch, tmp_path)
    reason = _r6_verdict(guard, shared_placement, "pytest -k pool", capsys)[1]
    assert "mentions a paid-launch wrapper name" in reason
    assert "Not launching?" in reason and "git commit" in reason and "rg" in reason
    assert "r7 admit rule" in reason
    reason = _r6_verdict(guard, shared_placement, "pool </dev/null run glm a /tmp m", capsys)[1]
    assert "names a paid-launch wrapper but is not one plain top-level launch" in reason
    assert "redirections only at the end" in reason


def test_r7_unarmed_sessions_see_launches_the_text_regex_misses(
    mastermind_scope: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Legacy (unarmed) identity checks now also run on a launch the parse
    # finds but FABRIC_LAUNCH_RE misses; reads stay unchecked.
    for name in ("POOL_ORCHESTRATOR_ID", "POOL_PARENT_RUN_ID", "POOL_TASK_CLASS",
                 "MASTERMIND_SHARED_PLACEMENT", "POOL_EXECUTION_BINDING"):
        monkeypatch.delenv(name, raising=False)
    for command in ("pool </dev/null run grok a /tmp grok-4",
                    "pool 2>&1 run grok a /tmp grok-4"):
        with pytest.raises(SystemExit):
            guard.guard_bash(_payload(mastermind_scope, command), {"command": command})
        assert "Fabric root-budget guard" in _emitted(capsys)["permissionDecisionReason"]
    for command in ("cat /opt/mastermind/ext/sub.sh", "pool status", "git commit -m 'pool'"):
        guard.guard_bash(_payload(mastermind_scope, command), {"command": command})
        assert capsys.readouterr().out == "", command


# --- r7: the REAL hook command line (python3 "<guard>" with JSON on stdin) ---
#
# On a single-uid host the receipt is necessarily principal-owned, so a
# BOUND run that reaches the gate is refused at the receipt channel ("not
# owner-authenticated") and an unbound one for "missing binding": both prove
# the gate ran. A structural refusal names its R6 code; a read is allowed.

_R7_HOOK_ROWS = [
    # (id, command, bound expectation, nobind expectation)
    ("seam-redir-before-mode", "pool </dev/null run grok a /tmp grok-4",
     "R6_REDIRECTION", "R6_REDIRECTION"),
    ("seam-fd-dup", "pool 2>&1 run grok a /tmp grok-4", "R6_REDIRECTION", "R6_REDIRECTION"),
    ("seam-redir-after-run", "pool run </dev/null grok a /tmp grok-4",
     "R6_REDIRECTION", "R6_REDIRECTION"),
    ("seam-subsh", "/opt/x/sub.sh </dev/null grok a /tmp grok-4",
     "R6_REDIRECTION", "R6_REDIRECTION"),
    ("seam-slot", "python3 /opt/x/slot.py </dev/null grok -- run",
     "R6_REDIRECTION", "R6_REDIRECTION"),
    ("seam-nested", "bash -c 'pool </dev/null run grok a /tmp grok-4'",
     "R6_REDIRECTION", "R6_REDIRECTION"),
    ("seam-target-named-cat", ">/tmp/cat pool run grok a /tmp grok-4",
     "R6_REDIRECTION", "R6_REDIRECTION"),
    ("scope-param-default", "${x:-pool} run grok a /tmp grok-4", "R6_EXPANSION", "R6_EXPANSION"),
    ("scope-locale", 'p$""ool run grok a /tmp grok-4', "R6_EXPANSION", "R6_EXPANSION"),
    ("insp-echo-zshenv",
     "echo 'pool() { command pool \"$@\"; command pool \"$@\"; }' >> ~/.zshenv",
     "R6_REDIRECTION", "R6_REDIRECTION"),
    ("path-prefix-env", "/tmp/evil/env pool run glm a /tmp glm-5.3",
     "R6_HEAD_SPELLING", "R6_HEAD_SPELLING"),
    ("id-lossy-value",
     "POOL_ORCHESTRATOR_ID=\"root-orch-1\"' evil' " + _R7_BAD_ROOT,
     "not owner-authenticated", "missing binding"),
    ("control-plain-launch", _R6_L, "not owner-authenticated", "missing binding"),
    ("control-git-commit", 'git commit -m "fix pool"', "allow", "allow"),
    ("control-cat", "cat /opt/mastermind/ext/sub.sh", "allow", "allow"),
    ("control-gh", "gh pr view 2329", "allow", "allow"),
]


@pytest.mark.parametrize("row", _R7_HOOK_ROWS, ids=[row[0] for row in _R7_HOOK_ROWS])
def test_r7_real_hook_command_line(tmp_path: Path, row: tuple[str, str, str, str]) -> None:
    import shutil
    import subprocess

    if shutil.which("python3") is None:
        pytest.skip("no python3 on PATH for the registered hook command")
    _, command, bound_expected, nobind_expected = row
    module_path = os.environ.get("MASTERMIND_R6_GUARD_UNDER_TEST", "").strip() or guard.__file__
    home = tmp_path / "home"
    cwd = home / "lanes" / "work"
    cwd.mkdir(parents=True)
    binding = _binding()
    receipt = tmp_path / "placement-receipt.json"
    receipt.write_text(json.dumps(_receipt(binding)), encoding="utf-8")
    base = {
        key: value for key, value in os.environ.items()
        if not key.startswith(("POOL_", "MASTERMIND_")) and key not in ("BASH_ENV", "ENV")
    }
    base.update({
        "HOME": str(home),
        "MASTERMIND_CI_POLL_STATE_DIR": str(tmp_path / "poll"),
        "MASTERMIND_SHARED_PLACEMENT": "1",
        "MASTERMIND_PLACEMENT_RECEIPT": str(receipt),
        "MASTERMIND_PLACEMENT_RECEIPT_OWNER_UIDS": str(os.geteuid()),
        "POOL_ORCHESTRATOR_ID": "root-orch-1",
        "POOL_PARENT_RUN_ID": "hermes-run-7",
        "POOL_TASK_CLASS": "code",
    })
    payload = json.dumps(_payload(cwd, command))
    for bound, expected in ((True, bound_expected), (False, nobind_expected)):
        env = dict(base)
        if bound:
            env["POOL_EXECUTION_BINDING"] = json.dumps(binding)
        result = subprocess.run(
            ["/bin/sh", "-c", f'python3 "{module_path}"'], input=payload, env=env,
            capture_output=True, text=True, timeout=60, check=False,
        )
        assert result.returncode == 0, result.stderr
        out = result.stdout.strip()
        if expected == "allow":
            assert out == "", (bound, out)
            continue
        decision = json.loads(out)["hookSpecificOutput"]
        assert decision["permissionDecision"] == "deny", (bound, out)
        assert expected in decision["permissionDecisionReason"], (bound, out)


# --- r7: the gate must FINISH (a hook killed at its 10 s timeout does not block)

_R7_BUDGET_N = 250_000


def _r7_fill(unit: str) -> str:
    return (unit * (_R7_BUDGET_N // len(unit) + 1))[:_R7_BUDGET_N]


_R7_BUDGET_ROWS = [
    # (id, command, bound verdict) — every one judged far inside the budget.
    ("long-path-word", "pool run grok a /tmp grok-4 -O" + _r7_fill("/a"), "deny"),
    ("slash-run", "pool run grok a /tmp grok-4 " + _r7_fill("/") + "pool", "deny"),
    ("dash-path-tokens", _R6_L + " " + _r7_fill("-a/"), "allow"),
    ("quoted-identity-text", _R6_L + " '" + _r7_fill("POOL_ORCHESTRATOR_ID ") + "'", "deny"),
    ("quoted-env-u-text", _R6_L + " '" + _r7_fill("env -u ") + "'", "deny"),
    ("quoted-do-text", _R6_L + " '" + _r7_fill("do ") + "'", "allow"),
    ("quoted-launch-text", _R6_L + " '" + _r7_fill("pool run glm ") + "'", "deny"),
    ("glob-head", _r7_fill("*?") + " run glm", "deny"),  # r12: a glob head, armed
    ("glob-arg", "ls " + _r7_fill("*?") + " pool", "allow"),
    ("nested-substitutions", "pool " + "$(" * 60_000 + "x" + ")" * 60_000, "deny"),
    ("dq-substitution-recursion", 'pool "' + '$("' * 60_000, "deny"),
    ("many-heredocs", "pool " + _r7_fill("<<A "), "deny"),
    ("many-semicolons", _r7_fill("pool run glm;"), "deny"),
    ("long-literal-word", _R6_L + " " + _r7_fill("a"), "allow"),
]


@pytest.mark.parametrize("row", _R7_BUDGET_ROWS, ids=[row[0] for row in _R7_BUDGET_ROWS])
def test_r7_armed_gate_finishes_far_inside_the_hook_budget(
    shared_placement: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    row: tuple[str, str, str],
) -> None:
    import time

    _, command, expected = row
    assert len(command) <= guard.R7_MAX_ARMED_COMMAND_CHARS
    _r6_armed_with_identity(shared_placement, monkeypatch, tmp_path)
    started = time.monotonic()
    verdict, reason = _r6_verdict(guard, shared_placement, command, capsys)
    elapsed = time.monotonic() - started
    assert verdict == expected, reason[:300]
    # The registered hook timeout is 10 s (provider_orchestrator_policy);
    # every scan on the armed path is linear (measured ~1 s worst case).
    assert elapsed < 5.0, (row[0], elapsed)


def test_r7_armed_command_above_the_cap_is_refused_fail_closed(
    shared_placement: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _r6_armed_with_identity(shared_placement, monkeypatch, tmp_path)
    command = _R6_L + " " + "a" * guard.R7_MAX_ARMED_COMMAND_CHARS
    verdict, reason = _r6_verdict(guard, shared_placement, command, capsys)
    assert verdict == "deny" and "refused fail-closed" in reason


def test_r7_main_fails_closed_on_an_internal_error_when_armed(
    shared_placement: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import io

    _r6_armed_with_identity(shared_placement, monkeypatch, tmp_path)

    def broken(*_args, **_kwargs):
        raise ValueError("boom")

    monkeypatch.setattr(guard, "guard_fabric_launch", broken)
    payload = json.dumps(_payload(shared_placement, _R6_L))
    monkeypatch.setattr("sys.stdin", io.StringIO(payload))
    with pytest.raises(SystemExit):
        guard.main()
    output = _emitted(capsys)
    assert output["permissionDecision"] == "deny"
    assert "internal guard error (ValueError)" in output["permissionDecisionReason"]
    # Unarmed sessions keep the previous behaviour (the error propagates).
    monkeypatch.delenv("MASTERMIND_SHARED_PLACEMENT")
    monkeypatch.delenv("POOL_EXECUTION_BINDING")
    monkeypatch.setattr("sys.stdin", io.StringIO(payload))
    with pytest.raises(ValueError):
        guard.main()


def test_r7_glob_and_parts_matchers_agree_with_the_regex_semantics() -> None:
    import fnmatch
    import random
    import re as regex

    rng = random.Random(2329)
    alphabet = "pols.uhrem_t*?[]!-ab"
    for _ in range(4000):
        pattern = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 9)))
        for name in guard._R6_WRAPPER_BASENAMES:
            assert guard._r7_glob_match(name, pattern) == fnmatch.fnmatchcase(name, pattern), (
                name, pattern,
            )
    for _ in range(4000):
        parts = ["".join(rng.choice("pols.uhb_") for _ in range(rng.randint(0, 3)))
                 for _ in range(rng.randint(2, 4))]
        expected_regex = ".*".join(regex.escape(part) for part in parts)
        for name in guard._R6_WRAPPER_BASENAMES:
            assert guard._r7_parts_match(name, parts) == bool(
                regex.fullmatch(expected_regex, name)
            ), (name, parts)


# =============================================================================
# r8 (Director C6; REVIEW3 A3 S1 NEEDS_REWORK, A2 git carve-out, A1 note):
# every armed-path scan linear or hard-bounded, a fail-closed watchdog, the
# onFailure:"block" hook row, git optional-argument options, scope escapes
# found while linearising r7, and the scope-roots pin.
# =============================================================================

import re as _r8_re

#: r7's quadratic regexes, kept HERE only as the reference the r8 linear
#: scans are fuzzed against (they must accept at least the same texts).
_R7_PARAM_OPERATOR_REF = _r8_re.compile(
    r"\$\{(?:\([^()]*\))?[#!]?(?:[A-Za-z_][A-Za-z0-9_]*|[0-9]+|[@*#?$!-])?"
    r"(?:\[[^\]]*\])?(?::?[-=+?]|//?|/[#%]|##?|%%?|\^\^?|,,?|:)"
)
_R7_GLUED_OPTION_REF = _r8_re.compile(
    r"(?<![A-Za-z0-9_.])-[A-Za-z](?:[A-Za-z0-9_./-]*/|[A-Za-z]*)"
    r"(?:pool|sub\.sh|remote_sub\.sh|slot\.py)(?![A-Za-z0-9_.-])",
    _r8_re.I,
)
_R7_UNOBSERVABLE_FIRST_REF = _r8_re.compile(
    r"(?:^|[;&|(`{\n]|\$\()\s*(?:eval|source|\.)(?=\s)"
)
_R7_CMD_POS_REF = r"(?:^|[;&|\n(]|\b(?:do|then|else)\s)\s*"


def test_r8_glued_option_scan_accepts_exactly_the_r7_regex_language() -> None:
    import random

    rng = random.Random(28)
    pieces = ["pool", "po", "ol", "p", "sub.sh", "slot.py", "remote_sub.sh",
              "-", "/", "a", "O", "x", ".", "_", " ", "=", "-O", "--", "P", "S", "'"]
    for _ in range(40_000):
        text = "".join(rng.choice(pieces) for _ in range(rng.randint(0, 9)))
        assert guard._r8_glued_option(text) == bool(_R7_GLUED_OPTION_REF.search(text)), text


def test_r8_scope_views_are_at_least_as_wide_as_r7() -> None:
    """Every text r7's widened views (param-operator opening as a space,
    then the name regex or the glued-option regex) put in scope is in scope
    for r8 (which may be wider: nested ``${${x}:-pool}``, subscripts)."""
    import random

    rng = random.Random(8)
    pieces = ["pool", "po", "ol", "p", "sub.sh", "slot.py", "${", "}", "$", "{", "[",
              "]", "(", ")", ":", "-", ":-", "=", "x", "'", '"', "\\", " ", "/",
              "#", "!", "@", "-O", ",", "^", "%", "+", "$\"", "a[1]"]
    for _ in range(60_000):
        text = "".join(rng.choice(pieces) for _ in range(rng.randint(1, 10)))
        widened = _r8_re.sub(
            r"[\"'\\]", "", _R7_PARAM_OPERATOR_REF.sub(" ", text).replace('$"', '"')
        )
        if guard._WRAPPER_NAME_RE.search(widened) or _R7_GLUED_OPTION_REF.search(widened):
            assert guard.r6_names_wrapper(text), text


def test_r8_newline_gap_regexes_find_what_r7_found() -> None:
    import random

    rng = random.Random(81)
    pieces = ["\n", " ", "\t", ";", "{", "(", "$(", "eval", "source", ".", "x", "do",
              "then", "gh", " run watch", "\r"]
    cmd_pos_new = _r8_re.compile(guard.CMD_POS + r"gh\b")
    cmd_pos_old = _r8_re.compile(_R7_CMD_POS_REF + r"gh\b")
    for _ in range(30_000):
        text = "".join(rng.choice(pieces) for _ in range(rng.randint(0, 10)))
        old = bool(_R7_UNOBSERVABLE_FIRST_REF.search(text))
        new = bool(guard._UNOBSERVABLE_ENV_RE.search(text))
        assert old <= new, text  # the other alternatives are unchanged
        if old:
            assert new
        assert bool(cmd_pos_old.search(text)) == bool(cmd_pos_new.search(text)), text


def test_r8_option_cluster_equals_the_r7_fullmatch() -> None:
    import random

    rng = random.Random(3)
    for _ in range(20_000):
        word = "".join(rng.choice("-ciSax!Z9 ") for _ in range(rng.randint(0, 7)))
        assert guard._r8_option_cluster(word, "c") == bool(
            _r8_re.fullmatch(r"-[A-Za-z]*c[A-Za-z]*", word)
        ), word
        assert guard._r8_option_cluster(word, "iS") == bool(
            _r8_re.fullmatch(r"-[A-Za-z]*[iS][A-Za-z]*", word)
        ), word


def test_r8_word_literal_pieces_join_like_r7() -> None:
    tokens, error = guard._r6_lex("a$.b$%c 'q'r$x s")
    assert error == ""
    words = [item for kind, item in tokens if kind == "word"]
    assert words[0].segments == [("lit", "a$.b$%c")]
    assert words[1].segments == [("sq", "q"), ("lit", "r"), ("param", "$x")]
    assert words[2].segments == [("lit", "s")]
    word = guard._R6Word()
    word.add("lit", "a")
    assert word.segments == [("lit", "a")]
    word.add("lit", "b")  # a piece after a read still merges into the segment
    assert word.segments == [("lit", "ab")] and word.value == "ab"


def test_r8_identity_runs_are_read_once_with_an_unchanged_verdict() -> None:
    name = "POOL_ORCHESTRATOR_ID"
    values = guard._effective_identity_values(
        f"pool run glm a /tmp glm-5.3 a={name}={name}=root-orch-1", name
    )
    # the outer value, then '' for the inner assignment (never the projection)
    assert values[:2] == [f"{name}=root-orch-1", ""], values
    assert guard._effective_identity_values(
        f"{name}=root-orch-1 pool run glm a /tmp glm-5.3", name
    ) == ["root-orch-1"]


# --- r8: git optional-argument options (REVIEW3 A2) --------------------------

_R8_GIT_REFUSED = [
    "git log -U --output=/tmp/r8.out --grep=pool -1",
    "git log -pU --output=/tmp/r8.out --grep=pool -1",
    "git log --unified --output=/tmp/r8.out --grep=pool -1",
    "git log --relative --output=/tmp/r8.out --grep=pool -1",
    "git log --pretty --output=/tmp/r8.out --grep=pool -1",
    "git log --format --output=/tmp/r8.out --grep=pool -1",
    "git diff -U --output=/tmp/r8.out -- pool",
    "git show -U --output=/tmp/r8.out -- pool",
    "git log -U --ext-diff --grep=pool -1",
    "git log -U --textconv --grep=pool -1",
    "git status -u --output=/tmp/r8.out -- pool",
    "git status --untracked-files --output=/tmp/r8.out -- pool",
    "git log --grep=pool -- --output=/tmp/r8.out",
    "git log --author --output=/tmp/r8.out --grep=pool",
    "git commit -m --output=/tmp/r8.out -- pool",
    "git grep -O pool",
    "git log --grep=pool -O/tmp/order",
]
_R8_GIT_ADMITTED = [
    "git log -U --grep=pool -1",
    "git log -U3 --grep=pool -1",
    "git log -pU5 --grep=pool -1",
    "git log --unified=5 --grep=pool -1",
    "git log --pretty=oneline --grep=pool",
    "git log --format=%H --grep=pool",
    "git log --relative=src --grep=pool",
    "git diff -U5 -- pool",
    "git show --stat -U1 -- pool",
    "git status -uno -- pool",
    "git status --untracked-files=no -- pool",
    'git commit -m "fix pool"',
]


@pytest.mark.parametrize("command", _R8_GIT_REFUSED)
def test_r8_git_optional_argument_options_never_hide_a_write(
    shared_placement: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    command: str,
) -> None:
    assert guard.r6_names_wrapper(command), command
    (bound, reason, bound_gate), (nobind, _, nobind_gate) = _r7_both(
        guard, shared_placement, monkeypatch, tmp_path, capsys, command
    )
    assert (bound, nobind) == ("deny", "deny"), reason
    assert not bound_gate and not nobind_gate
    assert reason.startswith("Mastermind shared-placement guard: unobservable launch")


@pytest.mark.parametrize("command", _R8_GIT_ADMITTED)
def test_r8_git_honest_optional_argument_forms_stay_admitted(
    shared_placement: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    command: str,
) -> None:
    assert guard.r6_names_wrapper(command), command
    (bound, reason, bound_gate), (nobind, _, nobind_gate) = _r7_both(
        guard, shared_placement, monkeypatch, tmp_path, capsys, command
    )
    assert (bound, nobind) == ("allow", "allow"), reason
    assert not bound_gate and not nobind_gate


def test_r8_git_specs_keep_exec_options_out_of_every_option_set() -> None:
    for sub, spec in guard._R7_GIT_SPECS.items():
        every = (set(spec[0]) | set(spec[1]) | set(spec[2]) | set(spec[3])
                 | set(spec.short_optional) | set(spec.long_optional))
        for option in ("--ext-diff", "--textconv", "--output", "--exec",
                       "--open-files-in-pager", "--edit", "--interactive", "O"):
            assert option not in every, (sub, option)
        # an optional-argument option never consumes the next word
        assert not ({"U", "u"} & set(spec[1])), sub
        assert not ({"--unified", "--relative", "--pretty", "--format",
                     "--untracked-files"} & set(spec[3])), sub


# --- r8: scope escapes closed (found while making r7 linear) -----------------
#
# Each shape below RUNS the wrapper under zsh (the Bash tool's shell) — proven
# by test_r8_zsh_runs_each_closed_scope_escape — and r7 put it OUT of scope,
# i.e. an armed session ran it with zero binding check.

_R8_SCOPE_ESCAPES = [
    ("arith-base-bracket", "p$[[##36]24]ol", True),
    ("arith-base-paren", "p$(([##36]24))ol", True),
    ("split-operator-words", "${x:-p}${y:-ool}", False),
    ("nested-param", "${${x}:-pool}", False),
    ("nested-subscript", "${x[a[1]]:-pool}", False),
    ("cmdsub-glue", "echo $(p${x}ool", False),
    ("backtick-glue", "echo `p${x}ool", False),
    ("zsh-c-body-arith", "zsh -f -c 'p$[[##36]24]ol", True),
]


def _r8_escape_command(word: str, args: str) -> str:
    if word.startswith("echo $("):
        return f"{word} {args})"
    if word.startswith("echo `"):
        return f"{word} {args}`"
    if word.startswith("zsh -f -c '"):
        return f"{word} {args}'"
    return f"{word} {args}"


@pytest.mark.parametrize("row", _R8_SCOPE_ESCAPES, ids=[row[0] for row in _R8_SCOPE_ESCAPES])
def test_r8_scope_escapes_are_judged_and_refused(
    shared_placement: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    row: tuple,
) -> None:
    command = _r8_escape_command(row[1], "run grok a /tmp grok-4")
    assert guard.r6_names_wrapper(command), command
    (bound, reason, _), (nobind, _, _) = _r7_both(
        guard, shared_placement, monkeypatch, tmp_path, capsys, command
    )
    assert (bound, nobind) == ("deny", "deny"), reason


@pytest.mark.parametrize("command", [
    "cd ${HOME:-/Users/me}",
    "echo ${X:-o}",
    "echo ${X:-s}",
    'echo "${PORT:-8080}"',
    "echo ${name//-/_}",
    "$W run grok",
    "$(printf p)$(printf ool) run",
    "python3 *.py",
    "git log $(git merge-base a b)..HEAD",
    "echo $($(echo hi))",
    "bash ${dir}/run${n}.sh",
])
def test_r8_scope_stays_out_for_wholly_computed_and_unrelated_words(command: str) -> None:
    assert not guard.r6_names_wrapper(command), command


def test_r8_zsh_runs_each_closed_scope_escape(tmp_path: Path) -> None:
    """Ground truth for _R8_SCOPE_ESCAPES: in a sealed zsh (``env -i``,
    ``zsh -f``, PATH = a directory of FAKE wrappers + /usr/bin:/bin — the
    real wrappers are unreachable) every shape executes a wrapper."""
    import shutil
    import subprocess

    zsh = shutil.which("zsh")
    if zsh is None:
        pytest.skip("no zsh")
    bin_dir = tmp_path / "bin"
    ran = tmp_path / "ran"
    bin_dir.mkdir()
    ran.mkdir()
    for name in ("pool", "sub.sh", "slot.py"):
        fake = bin_dir / name
        fake.write_text(f'#!/bin/sh\ntouch "{ran}/{name}-$1"\n', encoding="utf-8")
        fake.chmod(0o755)
    case_insensitive = (bin_dir / "POOL").exists()
    for row_id, word, needs_case_insensitive in _R8_SCOPE_ESCAPES:
        if needs_case_insensitive and not case_insensitive:
            continue  # zsh prints uppercase base digits: pOol needs APFS-style lookup
        tag = "r8" + row_id.replace("-", "")
        command = _r8_escape_command(word, tag)
        subprocess.run(
            ["/usr/bin/env", "-i", f"PATH={bin_dir}:/usr/bin:/bin", f"HOME={tmp_path}",
             zsh, "-f", "-c", command],
            cwd=tmp_path, capture_output=True, text=True, timeout=20, check=False,
        )
        assert (ran / f"pool-{tag}").exists(), (row_id, command, sorted(p.name for p in ran.iterdir()))
        assert guard.r6_names_wrapper(command), command


# --- r8: the watchdog (SIGALRM, armed sessions only) -------------------------


@pytest.mark.parametrize("raw, expected", [
    ("", 7.0), ("3", 3.0), ("2.5", 2.5), ("30", 7.0), ("7", 7.0), ("0.2", 1.0),
    ("0", 1.0), ("-5", 1.0), ("abc", 7.0), ("nan", 7.0), ("inf", 7.0), ("-inf", 1.0),
])
def test_r8_watchdog_budget_is_overridable_only_downward(
    monkeypatch: pytest.MonkeyPatch, raw: str, expected: float
) -> None:
    monkeypatch.setenv(guard.R8_WATCHDOG_ENV, raw)
    assert guard.r8_watchdog_seconds() == expected


_R8_REAL_GUARD_FABRIC_LAUNCH = guard.guard_fabric_launch


def _r8_run_main(monkeypatch, payload: dict) -> None:
    import io

    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
    guard.main()


@pytest.mark.parametrize("slow_step", ["sleep", "regex"])
def test_r8_watchdog_denies_fail_closed_when_a_step_is_slow(
    shared_placement: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    slow_step: str,
) -> None:
    import signal
    import time

    _r6_armed_with_identity(shared_placement, monkeypatch, tmp_path)
    monkeypatch.setenv(guard.R8_WATCHDOG_ENV, "1")
    before = signal.getsignal(signal.SIGALRM)

    def slow(*_args, **_kwargs):
        if slow_step == "sleep":
            time.sleep(30)
        else:  # a catastrophically backtracking regex: the engine checks signals
            # Deliberate ReDoS payload for the watchdog test. The pattern is
            # assembled from the payload itself so static code scanning does not
            # read this intentional fixture as a production regex finding (the
            # lgtm/codeql comment suppression no longer applies in this era);
            # the assembled pattern is exactly "(a+)+$" over the same input.
            payload = "a" * 64 + "!"
            _r8_re.match("(" + payload[0] + "+)+$", payload)
        raise AssertionError("the watchdog did not interrupt the slow step")

    monkeypatch.setattr(guard, "guard_fabric_launch", slow)
    started = time.monotonic()
    with pytest.raises(SystemExit) as exit_info:
        _r8_run_main(monkeypatch, _payload(shared_placement, _R6_L))
    elapsed = time.monotonic() - started
    assert exit_info.value.code == 0
    output = _emitted(capsys)
    assert output["permissionDecision"] == "deny"
    assert "guard budget exceeded — fail closed" in output["permissionDecisionReason"]
    assert 0.9 <= elapsed < 4.0, elapsed
    assert signal.getitimer(signal.ITIMER_REAL)[0] == 0  # disarmed
    assert signal.getsignal(signal.SIGALRM) is before  # handler restored


def test_r8_watchdog_is_off_for_unarmed_sessions_and_after_a_verdict(
    shared_placement: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import signal
    import time

    monkeypatch.setenv(guard.R8_WATCHDOG_ENV, "1")
    monkeypatch.delenv("MASTERMIND_SHARED_PLACEMENT", raising=False)
    monkeypatch.delenv("POOL_EXECUTION_BINDING", raising=False)

    def slow_but_finishes(*_args, **_kwargs):
        time.sleep(1.4)

    monkeypatch.setattr(guard, "guard_fabric_launch", slow_but_finishes)
    _r8_run_main(monkeypatch, _payload(shared_placement, "echo hi"))
    assert capsys.readouterr().out == ""  # unarmed: no watchdog, no decision
    # armed, a fast verdict: the timer is disarmed before anything is written
    monkeypatch.setattr(guard, "guard_fabric_launch", _R8_REAL_GUARD_FABRIC_LAUNCH)
    monkeypatch.setenv("MASTERMIND_SHARED_PLACEMENT", "1")
    _r6_armed_with_identity(shared_placement, monkeypatch, tmp_path)
    with pytest.raises(SystemExit):
        _r8_run_main(monkeypatch, _payload(shared_placement, "pool </dev/null run grok a /tmp grok-4"))
    assert "R6_REDIRECTION" in _emitted(capsys)["permissionDecisionReason"]
    assert signal.getitimer(signal.ITIMER_REAL)[0] == 0


def _r8_hook_env(tmp_path: Path, *, bound: bool) -> tuple[dict, Path]:
    home = tmp_path / "home"
    cwd = home / "lanes" / "work"
    cwd.mkdir(parents=True, exist_ok=True)
    binding = _binding()
    receipt = tmp_path / "placement-receipt.json"
    receipt.write_text(json.dumps(_receipt(binding)), encoding="utf-8")
    env = {
        key: value for key, value in os.environ.items()
        if not key.startswith(("POOL_", "MASTERMIND_"))
        and key not in ("BASH_ENV", "ENV", "PYTHONPATH")
    }
    env.update({
        "HOME": str(home),
        "MASTERMIND_CI_POLL_STATE_DIR": str(tmp_path / "poll"),
        "MASTERMIND_SHARED_PLACEMENT": "1",
        "MASTERMIND_PLACEMENT_RECEIPT": str(receipt),
        "MASTERMIND_PLACEMENT_RECEIPT_OWNER_UIDS": str(os.geteuid()),
        "POOL_ORCHESTRATOR_ID": "root-orch-1",
        "POOL_PARENT_RUN_ID": "hermes-run-7",
        "POOL_TASK_CLASS": "code",
    })
    if bound:
        env["POOL_EXECUTION_BINDING"] = json.dumps(binding)
    return env, cwd


#: Owner-channel emulation for the hook process (as the in-process fixture
#: does): the guard file is loaded and run exactly as the hook runs it, with
#: a principal uid that does not own the receipt, so a BOUND command reaches
#: every binding check (on a single-uid host the receipt is principal-owned).
_R8_OWNER_SHIM = (
    "import importlib.util, os, sys\n"
    "spec = importlib.util.spec_from_file_location('provider_orchestrator_guard', sys.argv[1])\n"
    "m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)\n"
    "m._principal_ids = lambda: (os.geteuid() + 4242, frozenset())\n"
    "{inject}"
    "m.main()\n"
)


def _r8_hook_cli(
    tmp_path: Path, command: str, *, bound: bool, owner: bool, inject: str = "",
    extra_env: dict | None = None,
) -> tuple[float, int, str]:
    """(wall seconds, exit code, stdout) of the registered hook command line
    ``python3 "<guard>"`` (or the owner shim) with the PreToolUse JSON on stdin."""
    import shutil
    import subprocess
    import time

    if shutil.which("python3") is None:
        pytest.skip("no python3 on PATH for the registered hook command")
    module_path = os.environ.get("MASTERMIND_R6_GUARD_UNDER_TEST", "").strip() or guard.__file__
    env, cwd = _r8_hook_env(tmp_path, bound=bound)
    env.update(extra_env or {})
    if owner or inject:
        env["R8_SHIM"] = _R8_OWNER_SHIM.replace("{inject}", inject)
        line = f'python3 -c "$R8_SHIM" "{module_path}"'
    else:
        line = f'python3 "{module_path}"'
    started = time.monotonic()
    result = subprocess.run(
        ["/bin/sh", "-c", line], input=json.dumps(_payload(cwd, command)), env=env,
        capture_output=True, text=True, timeout=60, check=False,
    )
    return time.monotonic() - started, result.returncode, result.stdout.strip()


def test_r8_watchdog_through_the_hook_process(tmp_path: Path) -> None:
    inject = (
        "import time\n"
        "def _slow(*a, **k):\n"
        "    time.sleep(30)\n"
        "m.guard_fabric_launch = _slow\n"
    )
    elapsed, code, out = _r8_hook_cli(
        tmp_path, _R6_L, bound=True, owner=True, inject=inject,
        extra_env={"MASTERMIND_GUARD_BUDGET_S": "1"},
    )
    assert code == 0
    decision = json.loads(out)["hookSpecificOutput"]
    assert decision["permissionDecision"] == "deny"
    assert "guard budget exceeded — fail closed" in decision["permissionDecisionReason"]
    assert elapsed < 4.0, elapsed


# --- r8: the budget through the REAL hook command line ----------------------

_R8_CAP = 262_144


def _r8_filled(prefix: str, unit: str, size: int, suffix: str = "") -> str:
    room = size - len(prefix) - len(suffix)
    return prefix + (unit * (room // len(unit) + 1))[:room] + suffix


_R8_BUDGET_ROWS = [
    # (id, prefix, unit, suffix, bound, owner channel, verdict fragment)
    # REVIEW3 A3 — no literal wrapper name (computed glue, glob, $[ padding):
    ("rv-computed-glue-dash-path", "p${x}ool run grok a /tmp grok-4 ", "-a/", "", False, False, "R6_EXPANSION"),
    ("rv-param-default-dash-path", "${x:-p}ool run grok a /tmp grok-4 ", "-a/", "", False, False, "R6_EXPANSION"),
    ("rv-glob-head-dash-path", "p* run grok a /tmp grok-4 ", "-a/", "", False, False, "R6_NOT_A_PLAIN_LAUNCH"),
    ("rv-computed-glue-double-dash", "p${x}ool run grok a /tmp grok-4 ", "--a", "", False, False, "R6_EXPANSION"),
    ("rv-arith-padding-quoted", "p${x}ool run grok a /tmp grok-4 '", "$[", "'", False, False, "R6_EXPANSION"),
    ("rv-subscript-run", "pool </dev/null run grok a /tmp grok-4 ", "${x[", "", False, False, "R6_TOKENIZE_FAILED"),
    ("rv-bracket-run-no-wrapper", "", "[", "", False, False, "R12_SHELL_CONSTRUCT"),
    ("rv-subscript-run-no-wrapper", "", "${x[", "", False, False, "R12_SHELL_CONSTRUCT"),
    ("c5-option-path", "pool run grok a /tmp grok-4 -O", "/a", "", False, False, "missing binding"),
    # REVIEW3 A3 BLOCKER 3 — bound identity runs (every binding check reached):
    ("rv-bound-identity-run", "pool run grok a /tmp grok-4 a=", "POOL_ORCHESTRATOR_ID=", "", True, True, "POOL_ORCHESTRATOR_ID"),
    ("bound-identity-run-parent", "pool run glm a /tmp glm-5.3 a=", "POOL_PARENT_RUN_ID=", "", True, True, "POOL_PARENT_RUN_ID"),
    ("bound-identity-quoted", _R6_L + " '", "POOL_ORCHESTRATOR_ID=", "'", True, True, "POOL_ORCHESTRATOR_ID"),
    ("bound-env-u-quoted", _R6_L + " '", "env -u ", "'", True, True, "POOL_ORCHESTRATOR_ID"),
    ("bound-env-cluster-quoted", _R6_L + " 'env -", "i", "!'", True, True, "allow"),
    # found by the r8 complexity probe (super-linear in r7):
    ("nested-shell-option-cluster", "bash pool -", "c", "!", False, False, "R6_NESTED_SHELL"),
    ("newline-run-launch", "pool run glm a /tmp glm-5.3 ", "\n", "", True, True, "allow"),
    ("leading-newline-run", "", "\n", "pool run glm a /tmp glm-5.3", True, True, "allow"),
    ("literal-dollar-merge", "p${x}ool run glm a /tmp glm-5.3 ", "a$.", "", False, False, "R6_EXPANSION"),
    ("ansi-octal-escapes", "p${x}ool $'", "\\1", "'", False, False, "R6_EXPANSION"),
    ("long-head-many-invocations", "", "a", "", False, False, "R6_NOT_A_PLAIN_LAUNCH"),
    ("grouping-run", "p${x}ool run glm a /tmp glm-5.3 ", "))", "", False, False, "R6_GROUPING"),
    ("nested-construct-glue", "echo ", "$(p${x}ool ", "", False, False, "R6_TOKENIZE_FAILED"),
    # 8-char prefix + 18 724 whole 14-char units = 262 144: every construct closed
    ("nested-construct-glue-closed", "echo    ", "$(p${x}ool x) ", "", False, False, "R6_COMMAND_SUBSTITUTION"),
]


@pytest.mark.parametrize("row", _R8_BUDGET_ROWS, ids=[row[0] for row in _R8_BUDGET_ROWS])
def test_r8_budget_rows_finish_through_the_real_hook_command_line(
    tmp_path: Path, row: tuple
) -> None:
    row_id, prefix, unit, suffix, bound, owner, fragment = row
    if row_id == "long-head-many-invocations":
        head = "A" * (_R8_CAP // 2)
        command = head + _r8_filled("", " sub.sh x", _R8_CAP - len(head))
    else:
        command = _r8_filled(prefix, unit, _R8_CAP, suffix)
    assert len(command) == _R8_CAP
    elapsed, code, out = _r8_hook_cli(tmp_path, command, bound=bound, owner=owner)
    assert code == 0
    if fragment == "allow":
        assert out == "", out[:300]
    else:
        decision = json.loads(out)["hookSpecificOutput"]
        assert decision["permissionDecision"] == "deny", out[:300]
        assert fragment in decision["permissionDecisionReason"], decision["permissionDecisionReason"][:400]
        assert "guard budget exceeded" not in decision["permissionDecisionReason"]
    # Registered timeout 10 s, watchdog 7 s; measured ≤ ~1.1 s on the M2 host
    # (C6 ledger). A CI-safe bound well inside both:
    assert elapsed < 4.0, (row_id, elapsed)


@pytest.mark.parametrize("size", [_R8_CAP - 1, _R8_CAP, _R8_CAP + 1])
def test_r8_cap_boundary_through_the_real_hook_command_line(tmp_path: Path, size: int) -> None:
    command = _r8_filled("p${x}ool run grok a /tmp grok-4 ", "-a/", size)
    elapsed, code, out = _r8_hook_cli(tmp_path, command, bound=False, owner=False)
    assert code == 0
    reason = json.loads(out)["hookSpecificOutput"]["permissionDecisionReason"]
    if size > _R8_CAP:
        assert "refused fail-closed" in reason and f"{size} characters" in reason
        assert elapsed < 1.0, elapsed  # judged by length alone (measured ~0.08 s)
    else:
        assert "R6_EXPANSION" in reason
        assert elapsed < 4.0, elapsed


# --- r8: the Claude hook row blocks on failure (onFailure, C6 ledger) --------


def test_r8_claude_hook_row_blocks_on_failure_and_codex_row_does_not(tmp_path: Path) -> None:
    home = tmp_path / "home"
    _seed_home(home)
    apply_policy(home)
    assert verify_policy(home)["issues"] == [] or verify_policy(home)["state"] != "DRIFT"
    claude = json.loads((home / ".claude" / "settings.json").read_text(encoding="utf-8"))
    row = next(r for r in claude["hooks"]["PreToolUse"] if r.get("matcher") == "Agent|Task|Bash")
    assert row["hooks"][0]["onFailure"] == "block"
    assert row["hooks"][0]["timeout"] == 10
    codex = json.loads((home / ".codex" / "hooks.json").read_text(encoding="utf-8"))
    codex_row = next(r for r in codex["hooks"]["PreToolUse"] if r.get("matcher") == "^Bash$")
    assert "onFailure" not in codex_row["hooks"][0]
    # A Claude row whose failure would not block is drift.
    del row["hooks"][0]["onFailure"]
    (home / ".claude" / "settings.json").write_text(json.dumps(claude), encoding="utf-8")
    result = verify_policy(home)
    assert result["state"] == "DRIFT" and "claude_settings.pretool" in result["issues"]
    row["hooks"][0]["onFailure"] = "continue"
    (home / ".claude" / "settings.json").write_text(json.dumps(claude), encoding="utf-8")
    assert "claude_settings.pretool" in verify_policy(home)["issues"]


# --- r8: scope roots (REVIEW3 A1 note; pre-existing, #1228) -----------------


def test_r8_t3_worktree_cwd_is_outside_the_scope_roots_pinned_limit(
    shared_placement: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """PINS A KNOWN LIMIT, not a desired property: ``guard_bash`` returns
    before ANY check when the payload cwd is outside the scope roots, and
    ``~/.t3/worktrees/…`` is not a scope root — an armed T3-worktree session
    gets no checks at all unless MASTERMIND_SCOPE_ROOTS names it (Director C7
    owns the t3 child-session environment). If this test fails because the
    roots now cover T3 worktrees, update the C6 ledger note and drop it."""
    _r6_armed_with_identity(shared_placement, monkeypatch, tmp_path)
    monkeypatch.delenv("MASTERMIND_SCOPE_ROOTS", raising=False)
    home = Path(os.environ["HOME"])
    t3_cwd = home / ".t3" / "worktrees" / "Mastermind" / "t3-r8pin"
    t3_cwd.mkdir(parents=True)
    command = "pool </dev/null run grok a /tmp grok-4"  # refused anywhere in scope
    assert guard.guard_bash(_payload(t3_cwd, command), {"command": command}) is None
    assert capsys.readouterr().out == ""  # NO check ran: the documented gap
    monkeypatch.setenv("MASTERMIND_SCOPE_ROOTS", str(home / ".t3" / "worktrees"))
    with pytest.raises(SystemExit):
        guard.guard_bash(_payload(t3_cwd, command), {"command": command})
    assert "R6_REDIRECTION" in _emitted(capsys)["permissionDecisionReason"]


# --- r9: quote-adjacent glue (REVIEW4 F1 MAJOR) ------------------------------
#
# r8's rough word split treated ``"``, ``'`` and ``\`` as SEPARATORS, but the
# shell's quote removal JOINS adjacent quoted and unquoted segments into one
# word: ``${x:-p}"ool" run grok …`` RUNS ``pool`` (zsh -f and bash --norc
# both — test_r9_sealed_shells_run_each_quote_glue_shape) and r8 judged it out
# of scope (armed, no binding: ALLOWED). r9 adds the joined reading (quotes
# and backslashes deleted before splitting) to both partial-word readers.
#
# (id, template, shells that RUN it (ground truth), needs a case-insensitive FS)
# ``{a}`` = the arguments: the launch arguments for the verdict tests, a
# marker tag for the sealed ground-truth runs.

_R9_SCOPE_ESCAPES = [
    ("dq-suffix", '${x:-p}"ool" {a}', "zsh bash", False),
    ("sq-suffix", "${x:-p}'ool' {a}", "zsh bash", False),
    ("dq-construct-then-literal", '"${x:-p}"ool {a}', "zsh bash", False),
    ("backslash-suffix", "${x:-p}\\ool {a}", "zsh bash", False),
    ("dq-suffix-two-default-chars", '${x:-po}"ol" {a}', "zsh bash", False),
    ("cmdsub-dq-suffix", '$(printf p)"ool" {a}', "zsh bash", False),
    ("sub-sh-dq-suffix", '${x:-s}"ub.sh" {a}', "zsh bash", False),
    ("slot-py-dq-suffix", '${x:-sl}"ot.py" {a}', "zsh bash", False),
    ("empty-dq-between", '${x:-p}""ool {a}', "zsh bash", False),
    ("locale-empty-between", '${x:-p}$""ool {a}', "bash", False),  # zsh: $"" is not locale quoting
    ("dq-cmdsub-dq", '"p"$(true)"ool" {a}', "zsh bash", False),
    ("nested-in-echo-cmdsub", 'echo $(${x:-p}"ool" {a})', "zsh bash", False),
    ("nested-in-bash-c", "bash -c '${x:-p}\"ool\" {a}'", "zsh bash", False),
    ("zsh-arith-base-bracket-dq", '$[[##36]25]"OOL" {a}', "zsh", True),
    ("zsh-arith-base-paren-dq", '$(([##36]25))"ool" {a}', "zsh", True),
    ("zsh-anchored-replace-dq", '${x/#/p}"ool" {a}', "zsh", False),
]

_R9_LAUNCH_ARGS = {"slot-py-dq-suffix": "glm a /tmp glm-5.3"}


def _r9_escape_command(row: tuple, args: str | None = None) -> str:
    return row[1].replace("{a}", args or _R9_LAUNCH_ARGS.get(row[0], "run grok a /tmp grok-4"))


def test_r9_scope_escape_table_covers_every_reviewer_shape() -> None:
    reviewer = {
        '${x:-p}"ool"', "${x:-p}'ool'", '"${x:-p}"ool', "${x:-p}\\ool", '${x:-po}"ol"',
        '$(printf p)"ool"', '${x:-s}"ub.sh"', '${x:-sl}"ot.py"', '${x:-p}""ool',
        '${x:-p}$""ool', '"p"$(true)"ool"', '$[[##36]25]"OOL"', '$(([##36]25))"ool"',
        '${x/#/p}"ool"',
    }
    words = {row[1].split(" {a}")[0] for row in _R9_SCOPE_ESCAPES}
    assert reviewer <= words
    assert any(row[1].startswith("echo $(") for row in _R9_SCOPE_ESCAPES)
    assert any(row[1].startswith("bash -c '") for row in _R9_SCOPE_ESCAPES)


@pytest.mark.parametrize("row", _R9_SCOPE_ESCAPES, ids=[row[0] for row in _R9_SCOPE_ESCAPES])
def test_r9_quote_glue_escapes_are_judged_and_refused(
    shared_placement: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    row: tuple,
) -> None:
    command = _r9_escape_command(row)
    assert guard.r6_names_wrapper(command), command
    (bound, bound_reason, bound_gate), (nobind, nobind_reason, nobind_gate) = _r7_both(
        guard, shared_placement, monkeypatch, tmp_path, capsys, command
    )
    assert (bound, nobind) == ("deny", "deny"), (bound_reason, nobind_reason)
    # refused by SHAPE (R6_*), before any binding judgement, in both sessions
    assert "R6_" in bound_reason and "R6_" in nobind_reason, (bound_reason, nobind_reason)
    assert (bound_gate, nobind_gate) == (False, False)
    assert "guard budget exceeded" not in bound_reason + nobind_reason


def test_r9_reviewer_row_through_the_real_hook_command_line(tmp_path: Path) -> None:
    """REVIEW4 F1 exact reproduction: armed session, NO binding, through
    ``python3 "<guard>"``. r8 ALLOWED the quote-glued word (0.07 s) while the
    plain launch was denied 'missing binding'."""
    elapsed, code, out = _r8_hook_cli(
        tmp_path, '${x:-p}"ool" run grok a /tmp grok-4', bound=False, owner=False
    )
    assert code == 0 and out, out
    decision = json.loads(out)["hookSpecificOutput"]
    assert decision["permissionDecision"] == "deny"
    assert "R6_EXPANSION" in decision["permissionDecisionReason"]
    assert elapsed < 4.0, elapsed
    _, code, out = _r8_hook_cli(
        tmp_path, "pool run grok a /tmp grok-4", bound=False, owner=False
    )
    assert "missing binding" in json.loads(out)["hookSpecificOutput"]["permissionDecisionReason"]


def test_r9_sealed_shells_run_each_quote_glue_shape(tmp_path: Path) -> None:
    """Ground truth for _R9_SCOPE_ESCAPES: in a SEALED zsh (``env -i``,
    ``zsh -f``) and a sealed bash (``env -i``, ``--norc --noprofile``), PATH =
    a directory of FAKE wrappers + /usr/bin:/bin — the real wrappers are
    unreachable — every shape executes a wrapper in each shell its row names
    (zsh-only: arithmetic base output, ``${x/#/p}``; bash-only: ``$""``)."""
    import shutil
    import subprocess

    zsh = shutil.which("zsh")
    bash = "/bin/bash" if Path("/bin/bash").exists() else shutil.which("bash")
    if zsh is None or bash is None:
        pytest.skip("no zsh/bash")
    bin_dir = tmp_path / "bin"
    ran = tmp_path / "ran"
    home = tmp_path / "home"
    for directory in (bin_dir, ran, home):
        directory.mkdir()
    for name in ("pool", "sub.sh", "slot.py"):
        fake = bin_dir / name
        fake.write_text(f'#!/bin/sh\ntouch "{ran}/{name}-$1"\n', encoding="utf-8")
        fake.chmod(0o755)
    case_insensitive = (bin_dir / "POOL").exists()
    sealed_env = ["/usr/bin/env", "-i", f"PATH={bin_dir}:/usr/bin:/bin", f"HOME={home}"]
    checked = 0
    for row in _R9_SCOPE_ESCAPES:
        row_id, _, shell_names, needs_case_insensitive = row
        if needs_case_insensitive and not case_insensitive:
            continue  # zsh prints uppercase base digits: POOL needs APFS-style lookup
        argvs = {"zsh": [zsh, "-f", "-c"], "bash": [bash, "--norc", "--noprofile", "-c"]}
        for shell_name in shell_names.split():
            argv = argvs[shell_name]
            tag = "r9" + shell_name + row_id.replace("-", "")
            command = _r9_escape_command(row, tag)
            subprocess.run(
                sealed_env + argv + [command],
                cwd=home, capture_output=True, text=True, timeout=20, check=False,
            )
            markers = sorted(p.name for p in ran.iterdir() if p.name.endswith("-" + tag))
            assert markers, (row_id, shell_name, command)
            assert guard.r6_names_wrapper(command), command
            checked += 1
    assert checked >= 15 + 13  # 15 rows run in zsh, 13 in bash (12 in both)


# Honest forms: NOT newly refused. Out-of-scope words stay out; in-scope data
# (a literal wrapper name given to a read form) keeps its r8 verdict (allow).
_R9_STAY_OUT = [
    "cd ${HOME:-/Users/me}",
    'cd "${HOME:-/Users/me}"',
    'cd "${HOME:-/Users/me}"/src',
    "echo ${name//-/_}",
    'echo "${name//-/_}"',
    '"p"',
    'echo "p"',
    'echo "${PORT:-8080}"',
    "$W run grok",
    '"$W" run grok',
    "$(([##36]1198389))",
    '"$(([##36]1198389))" run',
    "$(printf p)$(printf ool) run",
    '"$(printf p)$(printf ool)" run',
    "echo $($(echo hi))",
    'git log "$(git merge-base a b)"..HEAD',
    'echo "$HOME" "notes"',
    "python3 \"$ROOT\"/scripts/run.py",
    "printf '%s\\n' \"$x\" 'ok'",
]


@pytest.mark.parametrize("command", _R9_STAY_OUT)
def test_r9_honest_and_wholly_computed_words_stay_out_of_scope(command: str) -> None:
    assert not guard.r6_names_wrapper(command), command


@pytest.mark.parametrize("command", [
    'echo "pool"',
    "echo 'pool run is a wrapper'",
    'grep -n "slot.py" docs/runbook.md',
    "cd ${HOME:-/Users/me} && echo ok",
    'echo "${name//-/_}"',
])
def test_r9_honest_forms_keep_their_armed_verdict(
    shared_placement: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    command: str,
) -> None:
    (bound, bound_reason, bound_gate), (nobind, nobind_reason, nobind_gate) = _r7_both(
        guard, shared_placement, monkeypatch, tmp_path, capsys, command
    )
    expected = _r12_armed_expectation(command, "allow")
    assert (bound, nobind) == (expected, expected), (bound_reason, nobind_reason)
    assert (bound_gate, nobind_gate) == (False, False)


def test_r9_quoting_never_takes_a_word_out_of_scope() -> None:
    """Property (the F1 rule): quoting the literal pieces of a word (``"…"``,
    ``'…'``, backslashes, ``""``/``$""`` between pieces, ``"…"`` around a
    $-construct) is shell-transparent, so whenever the unquoted spelling is in
    scope the quoted spelling is too. 6 000 random words."""
    import random

    rng = random.Random(20261110)
    # (no bare ``$x``: glued to a literal it names another variable —
    # ``$x"ol"`` is not ``$xol`` — so quoting is not transparent there)
    constructs = ["${x:-p}", "${x:-po}", "${x:-s}", "${x:-sl}", "$(printf p)", "${x}",
                  "$[1]", "$((1))", "${x/#/p}", "${x:+zz}", "`true`"]
    literals = ["p", "o", "ol", "ool", "pool", "s", "ub", ".sh", "ub.sh", "l", "ot", ".py",
                "ot.py", "x", "remote_", "sub", "a/", "/"]
    in_scope = 0
    for _ in range(6000):
        pieces = []
        for _ in range(rng.randint(1, 4)):
            if rng.random() < 0.45:
                pieces.append(("c", rng.choice(constructs)))
            else:
                pieces.append(("l", rng.choice(literals)))
        plain = "".join(text for _, text in pieces)
        quoted_parts = []
        for kind, text in pieces:
            style = rng.randrange(6)
            if kind == "c":
                quoted_parts.append(f'"{text}"' if style < 2 and not text.startswith("`") else text)
            elif style == 0:
                quoted_parts.append(f'"{text}"')
            elif style == 1:
                quoted_parts.append(f"'{text}'")
            elif style == 2:
                quoted_parts.append("".join("\\" + char for char in text))
            elif style == 3:
                quoted_parts.append(text + '""')
            elif style == 4:
                quoted_parts.append("$\"\"" + text)
            else:
                quoted_parts.append(text)
        quoted = "".join(quoted_parts)
        args = rng.choice([" run grok a /tmp grok-4", " glm a", " x", ""])
        if guard.r6_names_wrapper(plain + args):
            in_scope += 1
            assert guard.r6_names_wrapper(quoted + args), (plain, quoted)
    assert in_scope > 1000


def test_r9_construct_depth_boundary_is_ten_nested_constructs() -> None:
    """REVIEW4 depth note, stated exactly (code comment + C8 ledger): an
    honest ``echo $(echo $(… echo hi))`` chain stays out of scope up to 9
    nested constructs and is in scope (fail closed) from 10 on — the C6
    ledger's "> 8" read as nesting levels was off by one."""
    def chain(k: int) -> str:
        return "echo " + "$(echo " * k + "hi" + ")" * k

    for k in range(1, 10):
        assert not guard.r6_names_wrapper(chain(k)), k
    for k in (10, 11, 16):
        assert guard.r6_names_wrapper(chain(k)), k
    assert not guard._r8_computed_glue(chain(9))
    assert guard._r8_computed_glue(chain(10))


# --- r9: budget rows for the joined reader (real hook command line) ---------

_R9_BUDGET_ROWS = [
    # (id, prefix, unit, suffix, bound, owner channel, verdict fragment)
    ("r9-dq-glue-dq-run", '${x:-p}"ool" run grok a /tmp grok-4 ', '"a"', "", False, False, "R6_EXPANSION"),
    ("r9-dq-glue-sq-run", "${x:-p}'ool' run grok a /tmp grok-4 ", "'a'", "", False, False, "R6_EXPANSION"),
    ("r9-dq-glue-backslash-run", '${x:-p}"ool" run grok a /tmp grok-4 ', "\\a", "", False, False, "R6_EXPANSION"),
    ("r9-dq-glue-locale-run", '${x:-p}"ool" run grok a /tmp grok-4 ', '$""', "", False, False, "R6_EXPANSION"),
    ("r9-dq-glue-quote-only-run", '${x:-p}"ool" run grok a /tmp grok-4 ', '"', "", False, False, "R6_EXPANSION"),
    ("r9-dq-glue-dash-path-joined", '${x:-p}"ool" run grok a /tmp grok-4 ', '-"a"/', "", False, False, "R6_EXPANSION"),
    ("r9-joined-glue-one-word-no-wrapper", "", '"${x}"a', "", False, False, "R12_SHELL_CONSTRUCT"),
    ("r9-joined-partial-one-word-no-wrapper", "", '$(x)"a"', "", False, False, "R12_SHELL_CONSTRUCT"),
    ("r9-joined-construct-quote-run-no-wrapper", "", '"${x}"', "", False, False, "R12_SHELL_CONSTRUCT"),
    # joined: ``${x:-p}${x:-p}…`` can spell pool, like r8's unquoted E3
    ("r9-joined-default-glue-run", "", '"${x:-p}"', "", False, False, "R6_EXPANSION"),
    ("r9-nested-quote-glue", "echo ", '$(${x:-p}"ool" ', "", False, False, "R6_TOKENIZE_FAILED"),
    ("r9-bash-c-quote-glue-body", "bash -c '${x:-p}\"ool\" run grok a /tmp grok-4 ", '"a" ', "'", False, False, "R6_"),
    ("r9-bound-launch-quoted-args", "pool run glm a /tmp glm-5.3 ", '"a"', "", True, True, "allow"),
    # heaviest quote shape of the C8 sweep (135 shapes, 64 K → 256 K, none super-linear)
    ("r9-escaped-cmdsub-run-no-wrapper", "", "\\$(", "", False, False, "R12_SHELL_CONSTRUCT"),
    ("r9-dq-glue-escaped-cmdsub-run", '${x:-p}"ool" run grok a /tmp grok-4 ', "\\$(", "", False, False, "R6_GROUPING"),
]


@pytest.mark.parametrize("row", _R9_BUDGET_ROWS, ids=[row[0] for row in _R9_BUDGET_ROWS])
def test_r9_budget_rows_finish_through_the_real_hook_command_line(
    tmp_path: Path, row: tuple
) -> None:
    row_id, prefix, unit, suffix, bound, owner, fragment = row
    # whole units only (a cut quote would only test the tokenizer failure)
    prefix += " " * ((_R8_CAP - len(prefix) - len(suffix)) % len(unit))
    command = _r8_filled(prefix, unit, _R8_CAP, suffix)
    assert len(command) == _R8_CAP
    elapsed, code, out = _r8_hook_cli(tmp_path, command, bound=bound, owner=owner)
    assert code == 0
    if fragment == "allow":
        assert out == "", out[:300]
    else:
        decision = json.loads(out)["hookSpecificOutput"]
        assert decision["permissionDecision"] == "deny", out[:300]
        assert fragment in decision["permissionDecisionReason"], decision["permissionDecisionReason"][:400]
        assert "guard budget exceeded" not in decision["permissionDecisionReason"]
    assert elapsed < 4.0, (row_id, elapsed)


# --- r9: the watchdog in unarmed sessions = NO DECISION (REVIEW4 F4) --------

#: REVIEW4 F4 reproduction: ``gh`` CI-wait text with a newline run (the
#: ``do … done`` scan is super-linear on it). Unarmed r8: 10 s stall → the
#: ``onFailure: "block"`` row blocks the tool call.
_R9_F4_TEXT = "touch /tmp/r9-never-run; : gh run view 123" + "\n" * 60000 + ": end"


def _r9_hook(
    tmp_path: Path, payload: dict, *, armed: bool, extra_env: dict | None = None
) -> tuple[float, int, str]:
    import shutil
    import subprocess
    import time

    if shutil.which("python3") is None:
        pytest.skip("no python3 on PATH for the registered hook command")
    module_path = os.environ.get("MASTERMIND_R6_GUARD_UNDER_TEST", "").strip() or guard.__file__
    env, cwd = _r8_hook_env(tmp_path, bound=False)
    if not armed:
        env.pop("MASTERMIND_SHARED_PLACEMENT", None)
    env.update(extra_env or {})
    payload = dict(payload, cwd=str(cwd))
    started = time.monotonic()
    result = subprocess.run(
        ["/bin/sh", "-c", f'python3 "{module_path}"'], input=json.dumps(payload), env=env,
        capture_output=True, text=True, timeout=60, check=False,
    )
    return time.monotonic() - started, result.returncode, result.stdout.strip()


def test_r9_unarmed_adversarial_ci_text_is_no_decision_well_inside_the_timeout(
    tmp_path: Path,
) -> None:
    """Default budget (7 s), real hook command line: the unarmed hook now
    exits 0 with NO output (no allow, no deny) instead of stalling to the
    10 s provider kill."""
    elapsed, code, out = _r9_hook(tmp_path, _payload(tmp_path, _R9_F4_TEXT), armed=False)
    assert (code, out) == (0, "")
    assert elapsed < 8.5, elapsed  # watchdog 7 s + interpreter start; kill at 10 s


@pytest.mark.parametrize("text", [
    _R9_F4_TEXT,
    "gh run view 1;" + "do\n" * 40000,
    "x" + " then gh api x" * 18000,
    "gh run view 1\n" + "<<A\n" * 40000,
    "gh run view 1 <<" + "A" * 120000 + "\nB\n",
], ids=["newline-run", "do-newline-run", "then-gh-api-run", "heredoc-unclosed-run", "heredoc-long-id"])
def test_r9_unarmed_watchdog_firing_writes_nothing(tmp_path: Path, text: str) -> None:
    elapsed, code, out = _r9_hook(
        tmp_path, _payload(tmp_path, text), armed=False,
        extra_env={"MASTERMIND_GUARD_BUDGET_S": "1.5"},
    )
    assert (code, out) == (0, "")
    assert elapsed < 4.0, elapsed


def test_r9_armed_adversarial_ci_text_still_denies_on_budget(tmp_path: Path) -> None:
    """Armed behaviour is exactly r8: the watchdog firing is a DENY."""
    elapsed, code, out = _r9_hook(
        tmp_path, _payload(tmp_path, _R9_F4_TEXT), armed=True,
        extra_env={"MASTERMIND_GUARD_BUDGET_S": "1.5"},
    )
    assert code == 0
    decision = json.loads(out)["hookSpecificOutput"]
    assert decision["permissionDecision"] == "deny"
    assert "guard budget exceeded — fail closed" in decision["permissionDecisionReason"]
    assert elapsed < 4.0, elapsed


@pytest.mark.parametrize("command, background, expected", [
    ("gh run view 9101", False, ""),
    ("gh pr checks 9102", False, ""),
    ("gh run watch 9103 --interval 150", False, "foreground GitHub watch"),
    ("gh pr checks 9104 --watch", False, "cadence must be explicit"),
    ("gh run watch 9105 --interval 150", True, "CI WATCHER ARMED ASYNC"),
    ("for i in 1 2; do gh pr checks 9106; sleep 30; done", False, "do not emulate a watcher"),
    ("gh pr view 9107 --json body --jq '" + "a" * 192_000 + "'", False, ""),
    ("cat <<EOF\n" + "gh run watch 1\n" * 12_000 + "EOF\ngh pr view 9108", False, ""),
], ids=["run-view", "pr-checks", "fg-watch", "watch-no-interval", "bg-watch", "poll-loop",
        "long-jq-192k", "heredoc-body-180k"])
def test_r9_honest_unarmed_gh_commands_are_unchanged(
    tmp_path: Path, command: str, background: bool, expected: str
) -> None:
    elapsed, code, out = _r9_hook(
        tmp_path, _payload(tmp_path, command, background=background), armed=False
    )
    assert code == 0
    if expected:
        assert expected in out, out[:300]
    else:
        assert out == "", out[:300]
    assert elapsed < 2.0, elapsed


def test_r9_unarmed_watchdog_in_process_restores_the_handler(
    shared_placement: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import signal
    import time

    monkeypatch.setenv(guard.R8_WATCHDOG_ENV, "1")
    monkeypatch.delenv("MASTERMIND_SHARED_PLACEMENT", raising=False)
    monkeypatch.delenv("POOL_EXECUTION_BINDING", raising=False)
    before = signal.getsignal(signal.SIGALRM)

    def slow_ci_step(*_args, **_kwargs):
        time.sleep(30)
        raise AssertionError("the watchdog did not interrupt the slow CI-wait step")

    monkeypatch.setattr(guard, "_poll_key", slow_ci_step)
    started = time.monotonic()
    _r8_run_main(monkeypatch, _payload(shared_placement, "gh run view 9201"))  # returns: no SystemExit
    elapsed = time.monotonic() - started
    assert capsys.readouterr().out == ""
    assert 0.9 <= elapsed < 4.0, elapsed
    assert signal.getitimer(signal.ITIMER_REAL)[0] == 0
    assert signal.getsignal(signal.SIGALRM) is before


# --- r10: the lexer reading (REVIEW5 N1 MAJOR) -------------------------------
#
# Every r6–r9 reader found construct extents with a quote-UNAWARE bracket
# matcher/regex, so a quoted, escaped or commented bracket inside a
# construct hid the glued word: ``$(: "("; printf p)ool run grok …`` ran
# ``pool`` in sealed zsh and bash while the armed guard ALLOWED it bound and
# unbound (no binding check). r10 adds a quote-aware scanner reading (here-
# documents, comments, ``case`` in a substitution, bash/zsh ``${…}`` extent
# disagreements; see the guard's block comment).
#
# (id, template, shells that RUN it (ground truth), origin)
# ``{a}`` = the arguments (launch arguments / a ground-truth marker tag).

_R10_N1_ESCAPES = [
    ("quote-glued", '$(: "("; printf p)"ool" {a}', "zsh bash", "REVIEW5"),
    ("dq-paren", '$(: "("; printf p)ool {a}', "zsh bash", "REVIEW5"),
    ("sq-close-paren", "$(: ')'; printf p)ool {a}", "zsh bash", "REVIEW5"),
    ("escaped-paren", "$(: \\(; printf p)ool {a}", "zsh bash", "REVIEW5"),
    ("brace-dq-close", '${x:-p${y#"}"}}ool {a}', "zsh bash", "REVIEW5"),
    ("comment-paren", "$(printf p # (\n)ool {a}", "zsh bash", "REVIEW5"),
    ("nested-in-echo", 'echo $($(: "("; printf p)ool {a})', "zsh bash", "REVIEW5"),
    ("nested-in-bash-c", "bash -c '$(: \"(\"; printf p)ool {a}'", "zsh bash", "REVIEW5"),
    ("sub-sh", '$(: "("; printf s)ub.sh {a}', "zsh bash", "REVIEW5"),
    ("slot-py", '$(: "("; printf sl)ot.py {a}', "zsh bash", "REVIEW5"),
    ("sq-open-paren", "$(: '('; printf p)ool {a}", "zsh bash", "C9 (11th: the sq twin)"),
    # siblings found by Director C9 (an ``_r6_lex``-only reading misses them):
    ("case-in-cmdsub", "$(case x in x) printf p;; esac)ool {a}", "zsh", "C9"),
    ("heredoc-in-cmdsub", "$(cat <<E >/dev/null\n)\nE\nprintf p)ool {a}", "zsh", "C9"),
    ("heredoc-then-line", 'cat <<E >/dev/null\n$(\nE\n$(: "("; printf p)ool {a}', "bash", "C9"),
    ("brace-first-close", "x=p; ${x:-{}ool {a}", "bash", "C9"),
]

_R10_LAUNCH_ARGS = {"slot-py": "glm a /tmp glm-5.3"}


def _r10_escape_command(row: tuple, args: str | None = None) -> str:
    return row[1].replace("{a}", args or _R10_LAUNCH_ARGS.get(row[0], "run grok a /tmp grok-4"))


def test_r10_escape_table_covers_every_reviewer_shape() -> None:
    reviewer = {
        '$(: "("; printf p)"ool"', '$(: "("; printf p)ool', "$(: ')'; printf p)ool",
        "$(: \\(; printf p)ool", '${x:-p${y#"}"}}ool', "$(printf p # (\n)ool",
        'echo $($(: "("; printf p)ool', "bash -c '$(: \"(\"; printf p)ool",
        '$(: "("; printf s)ub.sh', '$(: "("; printf sl)ot.py',
    }
    words = {row[1].split(" {a}")[0] for row in _R10_N1_ESCAPES}
    assert reviewer <= words
    assert sum(row[3] != "C9" for row in _R10_N1_ESCAPES) == 11


@pytest.mark.parametrize("row", _R10_N1_ESCAPES, ids=[row[0] for row in _R10_N1_ESCAPES])
def test_r10_bracket_matcher_escapes_are_judged_and_refused(
    shared_placement: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    row: tuple,
) -> None:
    command = _r10_escape_command(row)
    assert guard.r6_names_wrapper(command), command
    assert guard._r10_lexed_reading(command), command
    (bound, bound_reason, bound_gate), (nobind, nobind_reason, nobind_gate) = _r7_both(
        guard, shared_placement, monkeypatch, tmp_path, capsys, command
    )
    assert (bound, nobind) == ("deny", "deny"), (bound_reason, nobind_reason)
    assert "R6_" in bound_reason and "R6_" in nobind_reason, (bound_reason, nobind_reason)
    assert (bound_gate, nobind_gate) == (False, False)
    assert "guard budget exceeded" not in bound_reason + nobind_reason


def test_r10_reviewer_row_through_the_real_hook_command_line(tmp_path: Path) -> None:
    """REVIEW5 N1 exact reproduction: armed, NO binding, ``python3 "<guard>"``.
    r9 ALLOWED it (0.05–0.07 s) while the plain launch is denied 'missing
    binding'."""
    elapsed, code, out = _r8_hook_cli(
        tmp_path, '$(: "("; printf p)"ool" run grok a /tmp grok-4', bound=False, owner=False
    )
    assert code == 0 and out, out
    decision = json.loads(out)["hookSpecificOutput"]
    assert decision["permissionDecision"] == "deny"
    assert "R6_COMMAND_SUBSTITUTION" in decision["permissionDecisionReason"]
    assert elapsed < 4.0, elapsed


def test_r10_sealed_shells_run_each_escape(tmp_path: Path) -> None:
    """Ground truth for _R10_N1_ESCAPES: SEALED zsh (``env -i``, ``zsh -f``)
    and bash (``env -i``, ``--norc --noprofile``), PATH = FAKE wrappers that
    only touch a marker + /usr/bin:/bin (the real wrappers are unreachable):
    every shape EXECUTES a wrapper in each shell its row names."""
    import shutil
    import subprocess

    zsh = shutil.which("zsh")
    bash = "/bin/bash" if Path("/bin/bash").exists() else shutil.which("bash")
    if zsh is None or bash is None:
        pytest.skip("no zsh/bash")
    bin_dir, ran, home = tmp_path / "bin", tmp_path / "ran", tmp_path / "home"
    for directory in (bin_dir, ran, home):
        directory.mkdir()
    for name in ("pool", "sub.sh", "slot.py"):
        fake = bin_dir / name
        fake.write_text(f'#!/bin/sh\ntouch "{ran}/{name}-$1"\n', encoding="utf-8")
        fake.chmod(0o755)
    sealed_env = ["/usr/bin/env", "-i", f"PATH={bin_dir}:/usr/bin:/bin", f"HOME={home}"]
    argvs = {"zsh": [zsh, "-f", "-c"], "bash": [bash, "--norc", "--noprofile", "-c"]}
    checked = 0
    for row in _R10_N1_ESCAPES:
        for shell_name in row[2].split():
            tag = "r10" + shell_name + row[0].replace("-", "")
            command = _r10_escape_command(row, tag)
            subprocess.run(
                sealed_env + argvs[shell_name] + [command],
                cwd=home, capture_output=True, text=True, timeout=20, check=False,
            )
            markers = [p.name for p in ran.iterdir() if p.name.endswith("-" + tag)]
            assert markers, (row[0], shell_name, command)
            assert guard.r6_names_wrapper(command), command
            checked += 1
    assert checked == 2 * 11 + 4  # 11 reviewer/twin rows in both shells + 4 siblings


#: Honest commands with quoted, escaped or commented brackets inside
#: constructs, here-documents with apostrophes (the ``git commit``/``gh pr
#: create`` idiom), arithmetic and comments: OUT of scope (the reviewer's
#: two named forms first).
_R10_HONEST_OUT = [
    'x=$(grep "(" f)',
    'echo "a (b" $(date)',
    "git commit -m \"$(cat <<'EOF'\nFix the lexer so it doesn't fail (r10).\n\n"
    "Co-Authored-By: X <x@example.com>\nEOF\n)\"",
    "git commit -m \"$(cat <<'EOF'\nFix `_r6_lex` so it doesn't (r10)\nEOF\n)\"",
    "gh pr create --title t --body \"$(cat <<'EOF'\n## Summary\n- it's done (see #1)\nEOF\n)\"",
    "cat > /tmp/x.py <<'EOF'\nprint('hi $x (')\nEOF",
    'echo "$(date +%s) (started)"',
    "awk '{print $1 \")\"}' f",
    'sed -n "s/(\\(.*\\))/\\1/p" f',
    'for f in $(ls *.py); do echo "$f (done)"; done',
    "echo $(( (1 + 2) * 3 ))",
    'echo "${HOME}" # (comment',
    "printf '%s (%s)\\n' \"$a\" \"$b\"",
    "result=$(python3 -c \"print('(')\")",
    'echo `date` "(x)"',
    "echo $(( 1 << 2 ))",
    "cat <<E\n$HOME (home)\nE\necho done",
    "echo ${CONFIG:-{}}",
    "grep -n '${{ matrix.index }}' .github/workflows/ci.yml",
    "sed -i '' 's/${{ github.token }}/x/' ci.yml",
]


@pytest.mark.parametrize("command", _R10_HONEST_OUT)
def test_r10_honest_bracket_and_heredoc_forms_stay_out_of_scope(command: str) -> None:
    assert not guard._r10_lexed_reading(command), command
    assert not guard.r6_names_wrapper(command), command


def test_r10_r6_lex_fails_on_the_commit_idiom_the_r10_reader_does_not() -> None:
    """Why r10 does not reuse ``_r6_lex``'s failure as its fail-closed rule:
    ``_r6_lex`` cannot read a here-document inside ``$(…)``, so an apostrophe
    in a commit message fails it; "failure + ``$`` → in scope" would refuse
    every such armed ``git commit``."""
    command = _R10_HONEST_OUT[2]
    assert guard._r6_lex(command)[1]  # the existing lexer fails …
    assert not guard._r10_lexed_reading(command)  # … the r10 reader reads it


@pytest.mark.parametrize("command", [
    "grep -n '$(' docs/runbook.md",
    'rg -n "\\$\\(" src',
    "git commit -m \"$(cat <<'EOF'\nr10: don't (see $(x))\nEOF\n)\"",
])
def test_r10_honest_forms_keep_their_armed_verdict(
    shared_placement: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    command: str,
) -> None:
    (bound, bound_reason, bound_gate), (nobind, nobind_reason, nobind_gate) = _r7_both(
        guard, shared_placement, monkeypatch, tmp_path, capsys, command
    )
    expected = _r12_armed_expectation(command, "allow")
    assert (bound, nobind) == (expected, expected), (bound_reason, nobind_reason)
    assert (bound_gate, nobind_gate) == (False, False)


@pytest.mark.parametrize("command, code", [
    # an unterminated ``$(`` in deferred (quoted) text: fail closed (rule kept)
    ("sed -i '' 's/$(/x/' f", "R6_NOT_A_PLAIN_LAUNCH"),
    # ``'`` inside ``"${…}"``: a quote to bash 3.2, literal to zsh — fail closed
    ("echo \"${y:-it's}\"", "R6_TOKENIZE_FAILED"),
    # bare braces inside ``${…}`` whose bash end (first ``}``) and zsh end
    # (counted) differ by more than ``}``: fail closed
    ("echo ${x:-{a}b}", "R6_EXPANSION"),
])
def test_r10_known_over_refusals_are_pinned(
    shared_placement: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    command: str,
    code: str,
) -> None:
    """PINS KNOWN LIMITS (C9 ledger), not desired properties: these honest-
    looking commands are newly IN SCOPE and refused in ARMED sessions only."""
    assert guard._r10_lexed_reading(command)
    (bound, bound_reason, _), (nobind, nobind_reason, _) = _r7_both(
        guard, shared_placement, monkeypatch, tmp_path, capsys, command
    )
    assert (bound, nobind) == ("deny", "deny")
    assert code in bound_reason and code in nobind_reason, (bound_reason, nobind_reason)


def test_r10_construct_depth_boundary_is_unchanged() -> None:
    def chain(k: int) -> str:
        return "echo " + "$(echo " * k + "hi" + ")" * k

    for k in range(1, 10):
        assert not guard._r10_lexed_reading(chain(k)), k
    for k in (10, 11, 16, 400):
        assert guard._r10_lexed_reading(chain(k)), k


def test_r10_reading_is_never_narrower_than_r9(monkeypatch: pytest.MonkeyPatch) -> None:
    """Union property: ``r6_names_wrapper`` only gained a reading, so every
    command in scope with the r10 reading switched off (= r9) is still in
    scope with it (6 000 random quote/bracket/construct texts + the r9
    escape table), and the r10 reading newly covers the N1 rows."""
    import random

    rng = random.Random(20261111)
    pieces = ['"("', "')'", "\\(", "$(: x)", "$(printf p)", "${x:-p}", '"', "'", "p", "ool",
              "o", "ol", "s", "ub.sh", "#", "\n", " ", ";", "`", "$", "{", "}", "(", ")",
              "$'", "<<E\n", "\nE\n"]
    commands = ["".join(rng.choice(pieces) for _ in range(rng.randint(1, 9))) for _ in range(6000)]
    commands += [_r9_escape_command(row) for row in _R9_SCOPE_ESCAPES]
    commands += [_r10_escape_command(row) for row in _R10_N1_ESCAPES]
    with_r10 = [guard.r6_names_wrapper(command) for command in commands]
    monkeypatch.setattr(guard, "_r10_lexed_reading", lambda _raw: False)
    without_r10 = [guard.r6_names_wrapper(command) for command in commands]
    narrowed = [c for c, a, b in zip(commands, with_r10, without_r10) if b and not a]
    assert narrowed == []
    assert sum(with_r10) > sum(without_r10)
    assert not any(without_r10[-len(_R10_N1_ESCAPES):])  # r9 missed every N1 row
    assert all(with_r10[-len(_R10_N1_ESCAPES):])


# --- r10: budget rows for the lexer reading (real hook command line) --------

_R10_BUDGET_ROWS = [
    # (id, prefix, unit, suffix, bound, owner channel, verdict fragment)
    ("r10-dq-paren-glue-dash-path", '$(: "("; printf p)ool run grok a /tmp grok-4 ', "-a/", "", False, False, "R6_COMMAND_SUBSTITUTION"),
    ("r10-sq-close-glue-dq-run", "$(: ')'; printf p)ool run grok a /tmp grok-4 ", '"a"', "", False, False, "R6_COMMAND_SUBSTITUTION"),
    ("r10-brace-dq-glue-sq-run", '${x:-p${y#"}"}}ool run grok a /tmp grok-4 ', "'a'", "", False, False, "R6_EXPANSION"),
    ("r10-comment-paren-glue-run", "$(printf p # (\n)ool run grok a /tmp grok-4 ", "a ", "", False, False, "R6_TOKENIZE_FAILED"),
    ("r10-bash-c-paren-glue-body", "bash -c '$(: \"(\"; printf p)ool run grok a /tmp grok-4 ", '"a" ', "'", False, False, "R6_"),
    ("r10-case-cmdsub-run", "", "echo $(case x in x) a;; esac) ", "", False, False, "R6_"),
    ("r10-heredoc-unclosed-run", '$(: "("; printf p)ool run grok a /tmp grok-4\n', "<<A\n", "", False, False, "R6_HEREDOC"),
    ("r10-param-nested-default-run", "", "${x:-${y}}", "", False, False, "R6_EXPANSION"),
    ("r10-param-default-p-run", "", "${x:-p}", "", False, False, "R6_EXPANSION"),
    ("r10-quoted-heredoc-unclosed-cmdsub-run", "", "cat <<'E'\nit's $(x\nE\n", "", False, False, "R6_HEREDOC"),
    ("r10-param-sq-default-run-no-wrapper", "echo ", "${x:-'a'}", "", False, False, "R12_SHELL_CONSTRUCT"),
    ("r10-assign-cmdsub-run-no-wrapper", "", "x=$(a) ", "", False, False, "R12_SHELL_CONSTRUCT"),
    ("r10-quoted-paren-cmdsub-run-no-wrapper", "", '$(: "(") ', "", False, False, "R12_SHELL_CONSTRUCT"),
    ("r10-deferred-sq-cmdsub-run-no-wrapper", "", "'$(a)' ", "", False, False, "R12_SHELL_CONSTRUCT"),
    ("r10-closed-heredoc-run-no-wrapper", "", "cat <<E\n$x (\nE\n", "", False, False, "R12_SHELL_CONSTRUCT"),
    ("r10-quoted-heredoc-prose-run-no-wrapper", "", "cat <<'E'\nit's (x) $y\nE\n", "", False, False, "R12_SHELL_CONSTRUCT"),
    ("r10-backtick-run-no-wrapper", "", "`a` ", "", False, False, "R12_SHELL_CONSTRUCT"),
    ("r10-escaped-dq-cmdsub-run-no-wrapper", "", '"\\$(a)" ', "", False, False, "R12_SHELL_CONSTRUCT"),
    ("r10-unclosed-sq-tail-no-wrapper", "echo $x '", "a(", "", False, False, "R12_SHELL_CONSTRUCT"),
    ("r10-bound-launch-quoted-paren-args", "pool run glm a /tmp glm-5.3 ", '"(" ', "", True, True, "allow"),
]


@pytest.mark.parametrize("row", _R10_BUDGET_ROWS, ids=[row[0] for row in _R10_BUDGET_ROWS])
def test_r10_budget_rows_finish_through_the_real_hook_command_line(
    tmp_path: Path, row: tuple
) -> None:
    row_id, prefix, unit, suffix, bound, owner, fragment = row
    prefix += " " * ((_R8_CAP - len(prefix) - len(suffix)) % len(unit))  # whole units
    command = _r8_filled(prefix, unit, _R8_CAP, suffix)
    assert len(command) == _R8_CAP
    elapsed, code, out = _r8_hook_cli(tmp_path, command, bound=bound, owner=owner)
    assert code == 0
    if fragment == "allow":
        assert out == "", out[:300]
    else:
        decision = json.loads(out)["hookSpecificOutput"]
        assert decision["permissionDecision"] == "deny", out[:300]
        assert fragment in decision["permissionDecisionReason"], decision["permissionDecisionReason"][:400]
        assert "guard budget exceeded" not in decision["permissionDecisionReason"]
    assert elapsed < 4.0, (row_id, elapsed)


# --- r10: the unarmed watchdog decision (REVIEW5 N2 MODERATE) ----------------
#
# Unarmed, the quadratic heredoc stripper runs BEFORE the legacy identity
# check: ``pool run grok a /tmp grok-4⏎`` + N × ``<<A⏎`` with no POOL_* env
# was DENIED by r8 ("missing POOL_ORCHESTRATOR_ID", 7.3–9.5 s) and got NO
# DECISION from r9 at 7 s (fail open on every CLI). r10: the watchdog firing
# DENIES when the raw text names a wrapper (recorded before the stripper).

_R10_N2_TEXT = "pool run grok a /tmp grok-4\n" + "<<A\n" * 24_000


def _r10_unarmed_hook(tmp_path: Path, command: str, budget: str | None = None):
    env = {"MASTERMIND_GUARD_BUDGET_S": budget} if budget else {}
    env.update({name: "" for name in ("POOL_ORCHESTRATOR_ID", "POOL_PARENT_RUN_ID", "POOL_TASK_CLASS")})
    return _r9_hook(tmp_path, _payload(tmp_path, command), armed=False, extra_env=env)


def test_r10_unarmed_heredoc_launch_denies_at_the_watchdog_default_budget(tmp_path: Path) -> None:
    """REVIEW5 N2 exact shape, default 7 s budget, real hook command line:
    DENY (r8-equivalent: the missing identity is named), inside the 10 s kill."""
    elapsed, code, out = _r10_unarmed_hook(tmp_path, _R10_N2_TEXT)
    assert code == 0 and out, out
    reason = json.loads(out)["hookSpecificOutput"]["permissionDecisionReason"]
    assert json.loads(out)["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "guard budget exceeded" in reason and "fail closed" in reason
    assert "POOL_ORCHESTRATOR_ID" in reason and "POOL_PARENT_RUN_ID" in reason
    assert elapsed < 8.5, elapsed


@pytest.mark.parametrize("count", [21_000, 22_500, 24_000])
def test_r10_unarmed_heredoc_launch_denies_at_a_lowered_budget(tmp_path: Path, count: int) -> None:
    command = "pool run grok a /tmp grok-4\n" + "<<A\n" * count
    elapsed, code, out = _r10_unarmed_hook(tmp_path, command, "1.5")
    assert code == 0 and out, out
    reason = json.loads(out)["hookSpecificOutput"]["permissionDecisionReason"]
    assert "guard budget exceeded" in reason and "POOL_ORCHESTRATOR_ID" in reason
    assert elapsed < 4.0, elapsed


@pytest.mark.parametrize("command", [
    "pool run grok a /tmp grok-4\n" + "<<A\n" * 24_000,  # the literal launch
    '$(: "("; printf p)ool run grok a /tmp grok-4\n' + "<<A\n" * 24_000,  # N1 + N2
    "sub.sh glm-memory a\n" + "<<A\n" * 24_000,
])
def test_r10_unarmed_watchdog_denies_every_wrapper_naming_text(tmp_path: Path, command: str) -> None:
    elapsed, code, out = _r10_unarmed_hook(tmp_path, command, "1.5")
    assert code == 0 and json.loads(out)["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert elapsed < 4.0, elapsed


def test_r10_unarmed_adversarial_ci_text_is_still_no_decision(tmp_path: Path) -> None:
    """The reviewer's unarmed ``gh`` CI-wait text: no wrapper named → r9's
    no decision is kept (availability)."""
    elapsed, code, out = _r10_unarmed_hook(tmp_path, _R9_F4_TEXT)
    assert (code, out) == (0, "")
    assert elapsed < 8.5, elapsed
    elapsed, code, out = _r10_unarmed_hook(tmp_path, "gh run view 1\n" + "<<A\n" * 24_000, "1.5")
    assert (code, out) == (0, "")
    assert elapsed < 4.0, elapsed


def test_r10_unarmed_scope_state_drives_the_watchdog_decision(
    shared_placement: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """In process, budget 1 s: a still-running scope reading ("pending") is a
    DENY; a slow step after a no-wrapper reading is no decision; a slow
    non-Bash tool (state "unset") is no decision."""
    import time

    monkeypatch.setenv(guard.R8_WATCHDOG_ENV, "1")
    monkeypatch.delenv("MASTERMIND_SHARED_PLACEMENT", raising=False)
    for name in ("POOL_ORCHESTRATOR_ID", "POOL_PARENT_RUN_ID", "POOL_TASK_CLASS"):
        monkeypatch.delenv(name, raising=False)

    def slow(*_args, **_kwargs):
        time.sleep(30)

    real_reading = guard.r6_names_wrapper
    monkeypatch.setattr(guard, "r6_names_wrapper", slow)
    with pytest.raises(SystemExit):
        _r8_run_main(monkeypatch, _payload(shared_placement, "echo $(date)"))
    assert "guard budget exceeded" in _emitted(capsys)["permissionDecisionReason"]
    monkeypatch.setattr(guard, "r6_names_wrapper", real_reading)
    monkeypatch.setattr(guard, "strip_heredocs", slow)
    _r8_run_main(monkeypatch, _payload(shared_placement, "echo $(date)"))
    assert capsys.readouterr().out == ""
    with pytest.raises(SystemExit):
        _r8_run_main(monkeypatch, _payload(shared_placement, "pool run grok a /tmp grok-4"))
    assert "POOL_ORCHESTRATOR_ID" in _emitted(capsys)["permissionDecisionReason"]
    monkeypatch.setattr(guard, "guard_native_child", slow)
    started = time.monotonic()
    _r8_run_main(monkeypatch, {
        "cwd": str(shared_placement), "session_id": "s", "tool_name": "Agent",
        "tool_input": {"model": "opus", "prompt": "x"},
    })
    assert capsys.readouterr().out == "" and time.monotonic() - started < 4.0


# --- r11: arithmetic, ``${…}`` in double quotes, words as deferred script ---
#
# Distinct re-check #6 (REVIEW6) found three seams in the r10 scanner, each
# reopening the armed-unbound bypass (sealed zsh/bash RUN a wrapper, the
# armed guard ALLOWED bound and unbound): N5 — ``#`` and ``<<`` inside
# ``$((…))``/``((…))``/``for ((…))`` read as a comment / here-document
# (neither shell does); N6 — ``${…}``: an unterminated quote inside the
# counted extent resynced past the word, and inside double quotes both
# shells end ``${`` at the FIRST ``}``; N7 — a double-quoted ``eval``/``-c``
# string gluing a construct to literal text was never read as a script.
# Director C10 found N8 while fixing N5: an argument-position ``(`` is a zsh
# glob group (bash: also a ``[[ =~ (…) ]]`` regex group) in which ``#`` is
# literal and every construct runs. See the guard's r11 block comment.
#
# (id, template, shells that RUN it (ground truth), origin); ``{a}`` = the
# launch arguments (or a ground-truth marker tag).

_R11_ESCAPES = [
    ("n5-dparen-comment", '(( 1 # $($(: "("; printf p)ool {a}) ))', "zsh bash", "REVIEW6 N5"),
    ("n5-dparen-hash-x", '(( #x + $($(: "("; printf p)ool {a}) ))', "zsh bash", "REVIEW6 N5"),
    ("n5-arith-hash-x-nl", 'x=a; echo $((#x + $($(: "("; printf p)ool {a})\n))', "zsh bash", "REVIEW6 N5"),
    ("n5-arith-comment-nl", 'echo $(( 1 # $($(: "("; printf p)ool {a})\n))', "zsh bash", "REVIEW6 N5"),
    ("n5-dparen-sub-sh", '(( 1 # $($(: "("; printf s)ub.sh {a}) ))', "zsh bash", "REVIEW6 N5"),
    ("n5-dparen-slot-py", '(( 1 # $($(: "("; printf sl)ot.py {a}) ))', "zsh bash", "REVIEW6 N5"),
    ("n5-dparen-and-escaped", "(( x = 1 )) && (( 1 # $($(: \\(; printf p)ool {a}) ))", "zsh bash", "REVIEW6 N5"),
    ("n5-for-dparen", 'for (( i=0 # $($(: "("; printf p)ool {a}); i<1; i++ )); do :; done', "zsh", "REVIEW6 N5"),
    ("n5b-dparen-shift", '(( y = 1 << 2 ))\necho "\n2\n"; $(: "("; printf p)ool {a} #"', "zsh bash", "REVIEW6 N5b"),
    ("n5b-for-shift",
     'for (( i = 1 << 2; i < 0; i++ )); do :; done\necho "\n2\n"; $(: "("; printf p)ool {a} #"',
     "zsh bash", "REVIEW6 N5b"),
    ("n6-dq-brace-default", 'x=p; "${x:-{}"ool {a}', "zsh bash", "REVIEW6 N6"),
    ("n6-dq-brace-sub-sh", 'x=s; "${x:-{}"ub.sh {a}', "zsh bash", "REVIEW6 N6"),
    ("n6-dq-brace-dash", 'x=p; "${x-{}"ool {a}', "zsh bash", "REVIEW6 N6"),
    ("n6-dq-brace-hash", 'x=p; "${x#{}"ool {a}', "zsh bash", "REVIEW6 N6"),
    ("n6-env", 'x=p; env "${x:-{}"ool {a}', "zsh bash", "REVIEW6 N6"),
    ("n6-exec", 'x=p; exec "${x:-{}"ool {a}', "zsh bash", "REVIEW6 N6"),
    ("n6-backtick", 'x=p; `"${x:-{}"ool {a}`', "zsh bash", "REVIEW6 N6"),
    ("n6-eval-sq", "x=p; eval '\"${x:-{}\"ool {a} # '", "zsh bash", "REVIEW6 N6"),
    ("n6-bare-nl-dq", 'x=p; ${x:-{}ool {a}\n: "', "bash", "REVIEW6 N6"),
    ("n6-bare-hash-dq", 'x=p; ${x:-{}ool {a} #"', "bash", "REVIEW6 N6"),
    ("n6-bare-hash-backtick", "x=p; ${x:-{}ool {a} # `", "bash", "REVIEW6 N6"),
    ("n6-bare-nl-sq", "x=p; ${x:-{}ool {a}\n: '", "bash", "REVIEW6 N6"),
    ("n7-eval-dq", 'eval "$(: "("; printf p)ool {a}"', "zsh bash", "REVIEW6 N7"),
    ("n7-bash-c-dq", 'bash -c "$(: "("; printf p)ool {a}"', "zsh bash", "REVIEW6 N7"),
    ("n7-sh-c-escaped", 'sh -c "$(: \\(; printf p)ool {a}"', "zsh bash", "REVIEW6 N7"),
    ("n7-zsh-fc-sub-sh", 'zsh -fc "$(: "("; printf s)ub.sh {a}"', "zsh bash", "REVIEW6 N7"),
    # siblings found by Director C10 (r10 out of scope; sealed shells run them):
    ("n8-argument-group", 'echo (1 # $($(: "("; printf p)ool {a}))', "zsh", "C10 N8"),
    ("n8-glued-group", 'echo a(1 # $($(: "("; printf p)ool {a}))', "zsh", "C10 N8"),
    ("n8-case-pattern-group", 'case x in a) :;; (x # $($(: "("; printf p)ool {a})) :;; esac', "zsh", "C10 N8"),
    ("n8-for-in-group", 'for x in (a # $($(: "("; printf p)ool {a})); do :; done', "zsh", "C10 N8"),
    ("n8-redirect-target-group", ': > (x # $($(: "("; printf p)ool {a}))', "zsh", "C10 N8"),
    ("n8-regex-group", '[[ a =~ (a # $($(: "("; printf p)ool {a})) ]] && echo m', "zsh bash", "C10 N8"),
    ("n8-noglob-group", 'noglob (x # $($(: "("; printf p)ool {a})\n)', "zsh", "C10 N8"),
    ("n5-function-body-dparen", 'f() (( 1 # $($(: "("; printf p)ool {a}) )); f', "zsh bash", "C10 N5"),
    # the comment region a subshell reading skips holds a paren zsh counts:
    ("n8-region-paren-group", 'echo (a # (\n)\n(b # $($(: "("; printf p)ool {a}))', "zsh", "C10 N8"),
    ("n8-region-paren-line-comment", 'echo (a # (\n) \n x # $($(: "("; printf p)ool {a})', "zsh", "C10 N8"),
    ("n8-region-paren-cmdsub-end", '$(printf p; : "("; : (a # )\n)ool {a}; : (b # (\n))', "zsh", "C10 N8"),
    # found by C10's mutation fuzz (r10 out of scope; sealed shells run them):
    ("n8-region-double-hash", 'echo (1 # #$($(: "("; printf p)ool {a}))', "zsh", "C10 N8"),
    ("n8-case-terminator-semicolon", 'case x in a) :;; ; (x # $($(: "("; printf p)ool {a})) :;; esac', "zsh", "C10 N8"),
    ("n8-case-terminator-newline", 'case x in a) :;;\n(x # $($(: "("; printf p)ool {a})) :;; esac', "zsh", "C10 N8"),
    ("n8-case-in-newline", 'case x in\n(x # $($(: "("; printf p)ool {a})) :;; esac', "zsh", "C10 N8"),
    ("n8-heredoc-delimiter-group", 'echo (1 # $($(<<:a( "("; printf p)ool {a}))', "zsh", "C10 N8"),
    ("n8-condition-newline", '[[ a =~ \n(a # $($(: "("; printf p)ool {a})) ]] && echo m', "zsh", "C10 N8"),
    ("n1-continuation-cmdsub", '$\\\n(: "("; printf p)ool {a}', "zsh bash", "C10 N1"),
    ("n1-continuation-brace", '$\\\n{x:-p${y#"}"}}ool {a}', "zsh bash", "C10 N1"),
]


def _r11_launch_args(row: tuple) -> str:
    if "ub.sh" in row[1]:
        return "glm-memory a"
    if "ot.py" in row[1]:
        return "glm a /tmp glm-5.3"
    return "run grok a /tmp grok-4"


def _r11_escape_command(row: tuple, args: str | None = None) -> str:
    return row[1].replace("{a}", args or _r11_launch_args(row))


def test_r11_escape_table_covers_every_review6_shape() -> None:
    """Every shape the re-check #6 brief lists is a row, verbatim."""
    a = "run grok a /tmp grok-4"
    n1 = '$(: "("; printf p)ool ' + a
    reviewer = [
        # N5 (8)
        '(( 1 # $($(: "("; printf p)ool ' + a + ") ))",
        '(( #x + $($(: "("; printf p)ool ' + a + ") ))",
        'x=a; echo $((#x + $($(: "("; printf p)ool ' + a + ")\n))",
        'echo $(( 1 # $($(: "("; printf p)ool ' + a + ")\n))",
        '(( 1 # $($(: "("; printf s)ub.sh glm-memory a) ))',
        '(( 1 # $($(: "("; printf sl)ot.py glm a /tmp glm-5.3) ))',
        "(( x = 1 )) && (( 1 # $($(: \\(; printf p)ool " + a + ") ))",
        'for (( i=0 # $($(: "("; printf p)ool ' + a + "); i<1; i++ )); do :; done",
        # N5b (2)
        '(( y = 1 << 2 ))\necho "\n2\n"; ' + n1 + ' #"',
        'for (( i = 1 << 2; i < 0; i++ )); do :; done\necho "\n2\n"; ' + n1 + ' #"',
        # N6 (12: the dq forms, the wrappers, the bash-only forms)
        'x=p; "${x:-{}"ool ' + a,
        'x=s; "${x:-{}"ub.sh glm-memory a',
        'x=p; "${x-{}"ool ' + a,
        'x=p; "${x#{}"ool ' + a,
        'x=p; env "${x:-{}"ool ' + a,
        'x=p; exec "${x:-{}"ool ' + a,
        'x=p; `"${x:-{}"ool ' + a + "`",
        "x=p; eval '\"${x:-{}\"ool " + a + " # '",
        "x=p; ${x:-{}ool " + a + '\n: "',
        "x=p; ${x:-{}ool " + a + ' #"',
        "x=p; ${x:-{}ool " + a + " # `",
        "x=p; ${x:-{}ool " + a + "\n: '",
        # N7 (4)
        'eval "$(: "("; printf p)ool ' + a + '"',
        'bash -c "$(: "("; printf p)ool ' + a + '"',
        'sh -c "$(: \\(; printf p)ool ' + a + '"',
        'zsh -fc "$(: "("; printf s)ub.sh glm-memory a"',
    ]
    commands = {_r11_escape_command(row) for row in _R11_ESCAPES}
    assert [command for command in reviewer if command not in commands] == []
    origins = [row[3] for row in _R11_ESCAPES]
    assert (origins.count("REVIEW6 N5"), origins.count("REVIEW6 N5b")) == (8, 2)
    assert (origins.count("REVIEW6 N6"), origins.count("REVIEW6 N7")) == (12, 4)


@pytest.mark.parametrize("row", _R11_ESCAPES, ids=[row[0] for row in _R11_ESCAPES])
def test_r11_escapes_are_judged_and_refused(
    shared_placement: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    row: tuple,
) -> None:
    command = _r11_escape_command(row)
    assert guard.r6_names_wrapper(command), command
    assert guard._r10_lexed_reading(command), command
    (bound, bound_reason, bound_gate), (nobind, nobind_reason, nobind_gate) = _r7_both(
        guard, shared_placement, monkeypatch, tmp_path, capsys, command
    )
    assert (bound, nobind) == ("deny", "deny"), (bound_reason, nobind_reason)
    assert "R6_" in bound_reason and "R6_" in nobind_reason, (bound_reason, nobind_reason)
    assert (bound_gate, nobind_gate) == (False, False)
    assert "guard budget exceeded" not in bound_reason + nobind_reason


def test_r11_rows_are_read_by_the_lexer_reading_alone(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail-before: with the lexer reading switched off (the r6–r9 readers,
    unchanged since r9) no row is in scope — r10 (8cc4ce4ca), whose readers
    are those plus the r10 lexer, ALLOWED every row armed, bound and
    unbound (C10 ledger, measured through the real hook command line)."""
    commands = [_r11_escape_command(row) for row in _R11_ESCAPES]
    assert all(guard._r10_lexed_reading(command) for command in commands)
    monkeypatch.setattr(guard, "_r10_lexed_reading", lambda _raw: False)
    assert [command for command in commands if guard.r6_names_wrapper(command)] == []


@pytest.mark.parametrize("row_id", [
    "n5-dparen-comment", "n5b-dparen-shift", "n6-dq-brace-default", "n6-bare-nl-dq",
    "n7-eval-dq", "n8-argument-group",
])
@pytest.mark.parametrize("bound", [True, False], ids=["bound", "unbound"])
def test_r11_rows_through_the_real_hook_command_line(
    tmp_path: Path, row_id: str, bound: bool
) -> None:
    """Armed, the registered hook command line (bound: the owner-channel
    shim, every binding check reachable): DENY by shape, the gate unreached."""
    row = next(row for row in _R11_ESCAPES if row[0] == row_id)
    elapsed, code, out = _r8_hook_cli(tmp_path, _r11_escape_command(row), bound=bound, owner=bound)
    assert code == 0 and out, out
    decision = json.loads(out)["hookSpecificOutput"]
    assert decision["permissionDecision"] == "deny"
    reason = decision["permissionDecisionReason"]
    assert reason.startswith("Mastermind shared-placement guard: unobservable launch"), reason
    assert "R6_" in reason and "missing binding" not in reason, reason
    assert "guard budget exceeded" not in reason
    assert elapsed < 4.0, elapsed


def _r11_sealed_shells(tmp_path: Path):
    """SEALED zsh (``env -i``, ``zsh -f``) and bash (``env -i``,
    ``--norc --noprofile``); PATH = FAKE wrappers that only touch a marker,
    then /usr/bin:/bin (the real wrappers are unreachable). Returns
    ``run(command, shell) -> marker names``."""
    import shutil
    import subprocess

    zsh = shutil.which("zsh")
    bash = "/bin/bash" if Path("/bin/bash").exists() else shutil.which("bash")
    if zsh is None or bash is None:
        pytest.skip("no zsh/bash")
    bin_dir, ran, home = tmp_path / "bin", tmp_path / "ran", tmp_path / "home"
    for directory in (bin_dir, ran, home):
        directory.mkdir()
    for name in guard._R6_WRAPPER_BASENAMES:
        fake = bin_dir / name
        fake.write_text(f'#!/bin/sh\ntouch "{ran}/{name}-$1"\n', encoding="utf-8")
        fake.chmod(0o755)
    sealed_env = ["/usr/bin/env", "-i", f"PATH={bin_dir}:/usr/bin:/bin", f"HOME={home}"]
    argvs = {"zsh": [zsh, "-f", "-c"], "bash": [bash, "--norc", "--noprofile", "-c"]}

    def run(command: str, shell: str) -> list[str]:
        for marker in ran.iterdir():
            marker.unlink()
        try:
            subprocess.run(
                sealed_env + argvs[shell] + [command], cwd=home, capture_output=True,
                stdin=subprocess.DEVNULL, timeout=20, check=False,
            )
        except subprocess.TimeoutExpired:
            pass  # whatever it started before the timeout still counts
        return sorted(marker.name for marker in ran.iterdir())

    return run


def test_r11_sealed_shells_run_each_escape(tmp_path: Path) -> None:
    """Ground truth for _R11_ESCAPES: every shape EXECUTES a fake wrapper in
    each shell its row names."""
    run = _r11_sealed_shells(tmp_path)
    checked = 0
    for row in _R11_ESCAPES:
        for shell_name in row[2].split():
            tag = "r11" + shell_name + row[0].replace("-", "")
            command = _r11_escape_command(row, tag)
            markers = [name for name in run(command, shell_name) if name.endswith("-" + tag)]
            assert markers, (row[0], shell_name, command)
            assert guard.r6_names_wrapper(command), command
            checked += 1
    assert checked == sum(len(row[2].split()) for row in _R11_ESCAPES) == 70


#: Honest forms: the reviewer's (REVIEW6) not already in _R10_HONEST_OUT,
#: then C10's — arithmetic with ``#``/``<<``/inert quotes, ``${…}`` in
#: double quotes, case/array/function parens, code in a here-document.
_R11_HONEST_OUT = [
    "git commit -m \"$(cat <<'EOF'\nFix: don't break (scope) when it's (nested)\n\n"
    "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>\nEOF\n)\"",
    'echo "${CONFIG:-{}}"',
    "awk '{print $(NF)}' f",
    "printf '%s' \"$(date +%s)\"",
    "x=$(( 1 << 2 ))\necho \"$x\"",
    "(( n = 1 << 2 ))\necho \"$n (done)\"",
    "(( i++ )) # it's (",
    "echo $((16#ff)) $((10#$m))",
    "echo $(([##16]255))",
    "for (( i = 0; i < 3; i++ )); do echo \"$i\"; done",
    "echo $(( (1 + 2) << 3 ))",
    "x=$(( $(wc -l < f) + 1 ))",
    '(( "$n" > 3 )) && echo big',
    'echo $(( "1" + 1 ))',
    'case "$x" in a) (( n = 1 << 2 ));; esac',
    'echo "${x:-{}}" "$(date)"',
    'echo "${x:-{a}b}" "$y"',
    'case "$x" in (a|b) echo "$x";; esac',
    'arr=(a b # comment\nc); echo "${arr[@]}"',
    'f() { echo "$1"; }; f x',
    'echo "$(date) - wrote $n files to $dir/out.json"',
    "cat > a.py <<'EOF'\nprint((\"a\", 1 << 2), (1 << 2))\nx = (1 << 2)\nprint(f\"{x}$\")\nEOF",
    'ssh h "cd ${DIR} && ls \\$(pwd)"',
]


@pytest.mark.parametrize("command", _R11_HONEST_OUT)
def test_r11_honest_forms_stay_out_of_scope(command: str) -> None:
    assert not guard._r10_lexed_reading(command), command
    assert not guard.r6_names_wrapper(command), command


#: REVIEW6 MINOR: an escaped ``\$(`` holding a local ``${VAR}`` was refused
#: armed by r10 (its deferred run was cut at ``${F}``, leaving ``$(`` open);
#: r11 re-reads the whole word with a placeholder for ``${F}``.
_R11_ESCAPED_CMDSUB_LOCAL_BRACES = [
    'ssh h "x=\\$(cat ${F}); echo \\$x"',
    'bash -c "n=\\$(wc -l < ${F}); echo \\$n"',
]


@pytest.mark.parametrize("command", _R11_ESCAPED_CMDSUB_LOCAL_BRACES)
def test_r11_escaped_cmdsub_with_a_local_brace_is_admitted_armed(
    shared_placement: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    command: str,
) -> None:
    assert not guard._r10_lexed_reading(command)
    assert not guard.r6_names_wrapper(command)
    (bound, bound_reason, bound_gate), (nobind, nobind_reason, nobind_gate) = _r7_both(
        guard, shared_placement, monkeypatch, tmp_path, capsys, command
    )
    expected = _r12_armed_expectation(command, "allow")
    assert (bound, nobind) == (expected, expected), (bound_reason, nobind_reason)
    assert (bound_gate, nobind_gate) == (False, False)


def test_r11_deferred_word_is_read_whole_with_placeholders() -> None:
    """The placeholder stands for a computed part wherever it lands, so a
    deferred word still spells across it — and the closing ``)`` after a
    local ``${F}`` is seen (the MINOR above)."""
    assert guard._r10_lexed_reading('bash -c "\\$(: \\"(\\"; printf p)o${q}ol run grok a /tmp grok-4"')
    assert guard._r10_lexed_reading("bash -c '\"p'\"$q\"'ool run grok a /tmp grok-4\"'")
    assert not guard._r10_lexed_reading('bash -c "x=\\$(cat ${F} ${G}); y=\\$(wc -l < $H)"')


@pytest.mark.parametrize("command, code", [
    # a double-quoted span in arithmetic holding ``{ }``: the shells may part
    ('(( "${n}" > 3 ))', "R6_EXPANSION"),
    # ``$((…)…)`` that is not ``))``: bash may read arithmetic, zsh a
    # command substitution — fail closed
    ("out=$((cd a && make) 2>&1)", "R6_EXPANSION"),
    # a ``((`` after a ``(pattern)`` (uncertain position) with ``<<``
    ('case "$x" in (a) (( n = 1 << 2 ));; esac', "R6_HEREDOC"),
    # an uncertain group's comment region holding a paren, inside ``$(…)``
    ("x=$(echo (a # it is) ok)", "R6_"),
])
def test_r11_known_over_refusals_are_pinned(
    shared_placement: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    command: str,
    code: str,
) -> None:
    """PINS KNOWN LIMITS (C10 ledger), not desired properties: newly IN
    SCOPE, refused in ARMED sessions only."""
    assert guard._r10_lexed_reading(command)
    (bound, bound_reason, _), (nobind, nobind_reason, _) = _r7_both(
        guard, shared_placement, monkeypatch, tmp_path, capsys, command
    )
    assert (bound, nobind) == ("deny", "deny")
    assert code in bound_reason and code in nobind_reason, (bound_reason, nobind_reason)


# --- r11: the structured fuzz (sealed ground truth) -------------------------
#
# Wrapper-spelling glue (computed head + literal tail) × execution contexts
# (arithmetic, ``((``/``for ((``, groups, case patterns, ``eval``/``-c``
# strings, here-documents, process substitution, …) × quote-parity
# disruptors before and after. Every candidate the guard leaves OUT of scope
# is run in sealed zsh AND bash; one that runs a fake wrapper is an escape.
# Default: a fixed seed and 3 000 candidates (a few seconds); opt in to more
# with MASTERMIND_GUARD_FUZZ_N=<count> (and MASTERMIND_GUARD_FUZZ_SEED).

_R11_FUZZ_WRAPPERS = [
    ("p", "ool", " run grok a /tmp grok-4"),
    ("s", "ub.sh", " glm-memory a"),
    ("sl", "ot.py", " glm a /tmp glm-5.3"),
]
#: (glue template — ``{h}`` computed head, ``{t}`` literal tail —, needs ``x={h}``)
_R11_FUZZ_GLUE = [
    ('$(: "("; printf {h}){t}', False), ("$(: ')'; printf {h}){t}", False),
    ("$(: \\(; printf {h}){t}", False), ("$(printf {h} # (\n){t}", False),
    ("${{x:-{{}}{t}", True), ('"${{x:-{{}}"{t}', True), ('${{x:-{h}${{y#"}}"}}}}{t}', False),
    ("`printf {h}`{t}", False), ("$(case x in x) printf {h};; esac){t}", False),
    ('"$(printf {h})"{t}', False), ("${{x:+{h}}}{t}", True), ('${{x#"("}}{t}', True),
    ('$x"{t}"', True), ('$(printf {h})"{t}"', False), ('"$(: "("; printf {h})"{t}', False),
    ('$(: "$(: ")")"; printf {h}){t}', False), ("$(printf {h} # it's \n){t}", False),
    ("$(cat <<'E'\n{h}\nE\n){t}", False), ('$(printf %s "${{y:-{h}}}"){t}', False),
    ("$(printf {h}; (( 1 << 2 )) ){t}", False), ("$(: $(( 1 # 2\n)); printf {h}){t}", False),
    ('"${{x-{{}}"{t}', True), ('"${{x#{{}}"{t}', True), ("$(printf {h} #)\n){t}", False),
    ('$(: "${{z:-{{}}"; printf {h}){t}', False), ("$((0))$(printf {h}){t}", False),
    ('$(: `echo "("`; printf {h}){t}', False), ("$(: $'\\x28'; printf {h}){t}", False),
    ("$(: <<<'('; printf {h}){t}", False), ("$( (: ')') ; printf {h}){t}", False),
    ("$(printf {h}; : (a # )\n){t}", False), ('$(printf {h}; : "("; : (a # )\n){t}', False),
    ('$\\\n(: "("; printf {h}){t}', False), ('$\\\n{{x:-{h}${{y#"}}"}}}}{t}', False),
    ('$(<<:a( "("; printf {h}){t}', False),
    # r12 (re-check #7 F1/F2): ``case`` inside ``$(…)`` after an fd
    # redirection, ``repeat N``; ``case`` inside zsh ``=(…)``
    ("$(2>/dev/null case x in x) printf {h};; esac){t}", False),
    ("$(2>&1 case x in x) printf {h};; esac){t}", False),
    ("$(repeat 1 case x in x) printf {h};; esac){t}", False),
    ("$(: =(case x in x) :;; esac); printf {h}){t}", False),
]
_R11_FUZZ_CONTEXTS = [
    "{P}", "echo $({P})", "echo `{P}`", "eval '{P}'", 'eval "{P}"', "bash -c '{P}'",
    'bash -c "{P}"', 'sh -c "{P}"', "zsh -fc '{P}'", "(( 1 # $({P}) ))",
    "echo $(( 1 # $({P})\n))", "(( x = $({P}) ))", "for (( i=0 # $({P}); i<1; i++ )); do :; done",
    '(( y = 1 << 2 ))\necho "\n2\n"; {P} #"', "(( y = 1 << 2 ))\necho '\n2\n'; {P} #'",
    'for (( i = 1 << 2; i < 0; i++ )); do :; done\necho "\n2\n"; {P} #"',
    "case x in x) {P};; esac", "case x in x) (( 1 # $({P}) ));; esac", "if true; then {P}; fi",
    "{{ {P}; }}", "( {P} )", "! {P}", "time {P}", "env {P}", "exec {P}", "command {P}",
    "nohup {P}", "x=1 {P}", "{P} | cat", "true && {P}", "false || {P}",
    "cat <<E >/dev/null\n$(\nE\n{P}", ": <<'Q'\nit's (\nQ\n{P}", "f() {{ {P}; }}; f",
    "[[ -n a ]] && {P}", "[[ 1 -eq 1 # $({P}) ]]", "echo ${{a[ $({P}) ]}}", "a[$({P})]=1",
    "let x=$({P})", ": $[ 1 # $({P}) ]", "cat <({P})", "x=$( {P} )",
    "cat <<E >/dev/null\n$({P})\nE", ': "${{x:-$({P})}}"', ": ${{x:-$({P})}}", ': "$(( $({P}) ))"',
    "while false; do :; done; {P}", "for i in 1; do {P}; done", "x=$(( 1 << 2 )); {P}",
    "echo $(( (1) + (2) )); {P}", "(( 1 )) && (( 1 # $({P}) ))", "echo $((#x + $({P})\n))",
    "(( #x + $({P}) ))", 'echo "$(( 1 # $({P})\n))"', "$(( 1 ))\n{P}", "x=( $({P}) )",
    "echo ${{x:-$(( 1 # $({P})\n))}}", 'echo "${{x:-{{}}" "$({P})"', 'eval "x=1; {P}"',
    "eval 'x=1; '\"{P}\"", "{P} &\nwait", "echo (1 # $({P}))", "echo a(1 # $({P}))",
    "case x in (x # $({P})) :;; esac", "case x in a) :;; (x # $({P})) :;; esac",
    "for x in (a # $({P})); do :; done", "echo $(echo (1 # $({P})))", ": > (x # $({P}))",
    "echo x(a)(b # $({P}))", "echo ( # $({P})\n)", "echo (1 #) $({P})", "echo [(] # $({P})",
    "f() (( 1 # $({P}) )); f", "repeat 1 (( 1 # $({P}) ))", "coproc (( 1 # $({P}) ))",
    ">/dev/null (( 1 # $({P}) ))", 'f() (( y = 1 << 2 ))\necho "\n2\n"; {P} #"',
    "a=(1 # x )\n$({P})\n)", "cat =({P})", "echo ((1) # $({P}))",
    "case x in a) :;| (x # $({P})) :;; esac", "echo $(( $({P}) ))", "[[ a =~ (a # $({P})) ]]",
    "noglob (x # $({P})\n)", "[[ a =~ a(b # $({P})) ]]",
    'case x in (x) (( y = 1 << 2 ))\necho "\n2\n"; {P} #"\n;; esac', "x=( a # $({P})\n)",
    "f () (( 1 # $({P}) )); f", "echo (a # (\n)\n(b # $({P}))", "echo (a # (\n) \n x # $({P})",
    "echo a(b # (\n)\n( c # $({P}))", "{P}; : (b # (\n))", "echo (a # '\n) \n x '; {P}",
    "echo (1 # #$({P}))", "case x in a) :;; ; (x # $({P})) :;; esac", "case x in a) :;;\n(x # $({P})) :;; esac",
    "case x in\n(x # $({P})) :;; esac", "[[ a =~ \n(a # $({P})) ]]", "echo (1 # $({P}))",
    # r12 (re-check #7 F1/F2): reserved words / compound commands where r11's
    # command-position model did not look; ``=(…)`` holding a ``case``
    "case x {{\n(x # $({P})) :;; }}", "case x in (x) [[ a =~ \n(a # $({P})) ]];; esac",
    ": =(case x in x) :;; esac) (x # $({P}))", "cat =(case x in x) :;; esac) (x # $({P}))",
    "repeat 1 case x in\n(x # $({P})) :;; esac", "coproc [[ a =~ \n(a # $({P})) ]]\nwait",
    "for x (a) case x in\n(x # $({P})) :;; esac", "if [[ a ]] [[ a =~ \n(a # $({P})) ]]",
    "2>/dev/null case x in\n(x # $({P})) :;; esac", "2>&1 [[ a =~ \n(a # $({P})) ]] && echo m",
    "3</dev/null case x in\n(x # $({P})) :;; esac",
]
_R11_FUZZ_PRE = [
    "", "x={h}; ", "x={h}\n", ": \"${{q:-'}}\"; ", ": ${{q:-{{}}}}; ", "cat <<E >/dev/null\nE\n",
    "(( y = 1 << 2 ))\n", ": $(( 2 #\n)); ", 'echo "${{q:-{{a}}b}}" >/dev/null; ',
    "x={h}; : \\\n; ", "echo $(( 1 << 2 )) >/dev/null; ",
    # r12 (re-check #7 F1/F2): the prefix contexts r11's generator lacked
    "2>/dev/null ", "2>&1 ", "3</dev/null ", "{{fd}}>/dev/null ", "repeat 1 ", "coproc ",
    "for x (a) ", "if [[ a ]] ", "x=1 2>/dev/null ", "case x in (x) ", "true && 2>/dev/null ",
    "! 2>/dev/null ", ": =(case x in x) :;; esac) ",
]
_R11_FUZZ_POST = [
    "", "\n", ' #"', " # '", " # `", '\n: "', "\n: '", " ))", ")", '"', "'", "`", " }", ";; esac",
    "\n)", " # (\n", " #)\n)", "\n2",
]


def _r11_fuzz_candidates(seed: int, count: int) -> list[str]:
    import random

    rng = random.Random(seed)
    seen: set[str] = set()
    out: list[str] = []
    while len(out) < count:
        glue, needs_x = rng.choice(_R11_FUZZ_GLUE)
        head, tail, args = rng.choice(_R11_FUZZ_WRAPPERS)
        payload = glue.format(h=head, t=tail) + args
        pre = rng.choice(_R11_FUZZ_PRE)
        if needs_x and "x=" not in pre:
            pre = "x={h}; " + pre
        command = (
            pre.format(h=head) + rng.choice(_R11_FUZZ_CONTEXTS).format(P=payload)
            + rng.choice(_R11_FUZZ_POST)
        )
        if command not in seen:
            seen.add(command)
            out.append(command)
    return out


def test_r11_structured_fuzz_has_no_sealed_shell_escape(tmp_path: Path) -> None:
    """Every candidate the guard leaves out of scope runs NO wrapper in
    sealed zsh or bash (fixed seed). The generator is live: a sample of the
    in-scope candidates does run wrappers (r10's counts on this seed are in
    the C10 ledger)."""
    count = int(os.environ.get("MASTERMIND_GUARD_FUZZ_N", "3000"))
    seed = int(os.environ.get("MASTERMIND_GUARD_FUZZ_SEED", "20261113"))
    run = _r11_sealed_shells(tmp_path)
    candidates = _r11_fuzz_candidates(seed, count)
    out_of_scope = [command for command in candidates if not guard.r6_names_wrapper(command)]
    escapes = [
        (command, shell) for command in out_of_scope for shell in ("zsh", "bash")
        if run(command, shell)
    ]
    assert escapes == [], escapes[:5]
    assert len(out_of_scope) < count // 10  # most candidates are judged
    import random

    in_scope = [command for command in candidates if command not in set(out_of_scope)]
    sample = random.Random(seed).sample(in_scope, min(40, len(in_scope)))
    live = sum(1 for command in sample if run(command, "zsh") or run(command, "bash"))
    assert live >= len(sample) // 5, live  # measured ~47% at 200 samples


#: Mutation tokens: structure that moves quote/paren/comment parity.
_R11_MUTATION_TOKENS = [
    '"', "'", "(", ")", "#", " # ", "\n", "<<", "<< 2", "\\", "`", "$(", "((", "))", "{", "}", "$((",
    " ", ";", "|", "&&", "${x:-{}", '"${x:-{}"', "x=p; ", "(a # (\n)\n", "case x in x) ", ";; esac",
    "eval ", "bash -c ", "$'", "\\\n", ")\n", ' #"', "for ((", "[[ a =~ (", " ]]", "noglob ", "echo (",
    "a(", "f() ", "!", "{ ", " }", "(( y = 1 << 2 ))\n",
]


def _r11_mutations(seed: int, count: int) -> list[str]:
    """``count`` distinct mutations (1–3 token insertions/deletions) of every
    r10/r11 escape row."""
    import random

    rng = random.Random(seed)
    bases = [_r11_escape_command(row) for row in _R11_ESCAPES]
    bases += [_r10_escape_command(row) for row in _R10_N1_ESCAPES]
    seen: set[str] = set()
    out: list[str] = []
    while len(out) < count:
        command = rng.choice(bases)
        for _ in range(rng.randint(1, 3)):
            at = rng.randint(0, len(command))
            if rng.random() < 0.7:
                command = command[:at] + rng.choice(_R11_MUTATION_TOKENS) + command[at:]
            else:
                command = command[:at] + command[min(len(command), at + rng.randint(1, 4)):]
        if command not in seen:
            seen.add(command)
            out.append(command)
    return out


def test_r11_mutation_fuzz_has_no_sealed_shell_escape(tmp_path: Path) -> None:
    """Mutations of every known escape: each one the guard leaves out of
    scope runs NO wrapper in sealed zsh or bash (fixed seed; default 800,
    opt in to more with MASTERMIND_GUARD_MUTATIONS_N / _SEED)."""
    count = int(os.environ.get("MASTERMIND_GUARD_MUTATIONS_N", "800"))
    seed = int(os.environ.get("MASTERMIND_GUARD_MUTATIONS_SEED", "20261114"))
    run = _r11_sealed_shells(tmp_path)
    out_of_scope = [
        command for command in _r11_mutations(seed, count) if not guard.r6_names_wrapper(command)
    ]
    escapes = [
        (command, shell) for command in out_of_scope for shell in ("zsh", "bash")
        if run(command, shell)
    ]
    assert escapes == [], escapes[:5]
    assert len(out_of_scope) < count // 3


# --- r11: budget rows for the new paths (real hook command line) ------------

_R11_BUDGET_ROWS = [
    # (id, prefix, unit, suffix, bound, owner channel, verdict fragment)
    ("r11-dparen-comment-glue-shift-lines", '(( 1 # $($(: "("; printf p)ool run grok a /tmp grok-4) ))\n',
     "(( x = 1 << 2 ))\n", "", False, False, "R6_"),
    ("r11-dq-brace-glue-run", 'x=p; "${x:-{}"ool run grok a /tmp grok-4 ', '"${x:-{}}" ', "", False, False, "R6_"),
    ("r11-eval-dq-glue-fragments", 'eval "$(: "("; printf p)ool run grok a /tmp grok-4 ', "$(a) b ", '"',
     False, False, "R6_"),
    ("r11-argument-group-glue-lines", 'echo (1 # $($(: "("; printf p)ool run grok a /tmp grok-4))\n',
     "echo (a # $x)\n", "", False, False, "R6_"),
    ("r11-arith-long-no-wrapper", "echo $(( ", "1 + ", "1 ))", False, False, "R12_SHELL_CONSTRUCT"),
    ("r11-dparen-shift-lines-no-wrapper", "", "(( n = 1 << 2 ))\n", "", False, False, "R12_SHELL_CONSTRUCT"),
    ("r11-dollar-arith-cmdsub-no-wrapper", "", "$(( $(a) + 1 )) ", "", False, False, "R12_SHELL_CONSTRUCT"),
    ("r11-for-arith-no-wrapper", "", "for (( i=0; i<1; i++ )); do :; done\n", "", False, False, "R12_SHELL_CONSTRUCT"),
    ("r11-dq-brace-no-wrapper", "", '"${x:-{}}" ', "", False, False, "R12_SHELL_CONSTRUCT"),
    ("r11-dq-word-fragments-no-wrapper", 'echo "', "$(a) b ", '"', False, False, "R12_SHELL_CONSTRUCT"),
    ("r11-deferred-joined-no-wrapper", 'bash -c "', "x=\\$(cat ${F}); ", '"', False, False, "R12_SHELL_CONSTRUCT"),
    ("r11-argument-group-comment-lines-no-wrapper", "", "echo (a # $x)\n", "", False, False, "R12_SHELL_CONSTRUCT"),
    ("r11-case-pattern-groups-no-wrapper", "case $x in ", "(a|b) :;; ", "esac", False, False, "R12_SHELL_CONSTRUCT"),
    ("r11-case-terminators-no-wrapper", "case $x in ", "a) :;; (b) :;& (c) :;| ", "esac", False, False, "R12_SHELL_CONSTRUCT"),
    ("r11-arith-base-no-wrapper", "", "$((16#ff + 10#$m)) ", "", False, False, "R12_SHELL_CONSTRUCT"),
    ("r11-uncertain-dparen-no-wrapper", "echo $x ", "((a)) ", "", False, False, "R12_SHELL_CONSTRUCT"),
    ("r11-dq-param-cmdsub-no-wrapper", "", '"${x:-$(a)}" ', "", False, False, "R12_SHELL_CONSTRUCT"),
    ("r11-continuation-dq-param-cmdsub-no-wrapper", "", '"${x:-$(a)}" \\\n', "", False, False, "R12_SHELL_CONSTRUCT"),
    ("r11-bound-launch-quoted-arith-args", "pool run glm a /tmp glm-5.3 ", '"(( 1 << 2 ))" ', "", True, True, "allow"),
]


@pytest.mark.parametrize("row", _R11_BUDGET_ROWS, ids=[row[0] for row in _R11_BUDGET_ROWS])
def test_r11_budget_rows_finish_through_the_real_hook_command_line(
    tmp_path: Path, row: tuple
) -> None:
    row_id, prefix, unit, suffix, bound, owner, fragment = row
    prefix += " " * ((_R8_CAP - len(prefix) - len(suffix)) % len(unit))  # whole units
    command = _r8_filled(prefix, unit, _R8_CAP, suffix)
    assert len(command) == _R8_CAP
    elapsed, code, out = _r8_hook_cli(tmp_path, command, bound=bound, owner=owner)
    assert code == 0
    if fragment == "allow":
        assert out == "", out[:300]
    else:
        decision = json.loads(out)["hookSpecificOutput"]
        assert decision["permissionDecision"] == "deny", out[:300]
        assert fragment in decision["permissionDecisionReason"], decision["permissionDecisionReason"][:400]
        assert "guard budget exceeded" not in decision["permissionDecisionReason"]
    assert elapsed < 4.0, (row_id, elapsed)


def test_r11_armed_budget_denial_stdout_is_byte_identical_to_r8(tmp_path: Path) -> None:
    """REVIEW6 N2 ACCEPT kept: the armed budget-DENY stdout (REVIEW4 F4
    text, an injected 30 s step, budget 1.5 s) is byte-identical to r8–r10."""
    import hashlib

    inject = "import time\ndef _slow(*a, **k):\n    time.sleep(30)\nm.guard_fabric_launch = _slow\n"
    elapsed, code, out = _r8_hook_cli(
        tmp_path, _R6_L, bound=True, owner=True, inject=inject,
        extra_env={"MASTERMIND_GUARD_BUDGET_S": "1.5"},
    )
    assert code == 0
    assert hashlib.sha256((out + "\n").encode()).hexdigest() == (
        "9c651f8f3ce0b6fff6e10c458de8bd2de55ef509558b635cb62b3fe1f307ac11"
    )
    assert elapsed < 4.0, elapsed


# --- r12: the STRUCTURAL scope rule for armed sessions (re-check #7) --------
#
# Re-check #7 (distinct Opus, at r11; REVIEW7_GUARD_R11_OPUS_20261110.md):
# F1 — r11's "command position" model is too narrow for zsh (a reserved word
# after ``2>…``/``2>&1``/``3<…``, ``repeat N``, ``coproc``, ``for x (…)``,
# ``if [[ … ]]``, a ``(pattern)`` arm; ``[[`` and ``case`` not recognised
# there, a ``case`` in ``$(…)`` missed); F2 — zsh ``=(…)`` read as a glob
# group, and an unmatched top-level ``)`` restored command position.
# The principal's decision: in an ARMED session the security decision must not
# depend on finding hidden wrapper names. A command is OUT of scope only when
# its raw text holds no shell construct (quoted or not) and names no wrapper
# literally; everything else must be exactly an admitted ADMIT form. The
# r6–r11 scanner stays a secondary, widening-only reading (and the unarmed
# mechanism); the F1/F2 fixes are applied to it too.
#
# (id, template, shells that RUN it (ground truth), origin). ``{a}`` = the
# arguments. The brief carried the families of re-check #7, not its verbatim
# rows: the 12 REVIEW7 rows are RECONSTRUCTED from those descriptions (each
# verified: r11 armed ALLOW bound and unbound through the real hook command
# line, a sealed zsh runs the fake wrapper — C11 ledger); C11 adds 6.

_R12_N = '$($(: "("; printf p)ool {a})'
_R12_ESCAPES = [
    ("r7-f1-fd-case-in-newline", "2>/dev/null case x in\n(x # " + _R12_N + ") :;; esac", "zsh", "REVIEW7 F1"),
    ("r7-f1-fd-dup-condition-newline", "2>&1 [[ a =~ \n(a # " + _R12_N + ") ]] && echo m", "zsh", "REVIEW7 F1"),
    ("r7-f1-fd-read-case-in-newline", "3</dev/null case x in\n(x # " + _R12_N + ") :;; esac", "zsh", "REVIEW7 F1"),
    ("r7-f1-repeat-case", "repeat 1 case x in\n(x # " + _R12_N + ") :;; esac", "zsh", "REVIEW7 F1"),
    ("r7-f1-repeat-condition", "repeat 1 [[ a =~ \n(a # " + _R12_N + ") ]]", "zsh", "REVIEW7 F1"),
    ("r7-f1-coproc-condition", "coproc [[ a =~ \n(a # " + _R12_N + ") ]]\nwait", "zsh", "REVIEW7 F1"),
    ("r7-f1-for-short-case", "for x (a) case x in\n(x # " + _R12_N + ") :;; esac", "zsh", "REVIEW7 F1"),
    ("r7-f1-if-short-condition", "if [[ a ]] [[ a =~ \n(a # " + _R12_N + ") ]]", "zsh", "REVIEW7 F1"),
    ("r7-f1-arm-after-pattern-condition", "case x in (x) [[ a =~ \n(a # " + _R12_N + ") ]];; esac", "zsh",
     "REVIEW7 F1"),
    ("r7-f1-cmdsub-fd-case", "$(2>/dev/null case x in x) printf p;; esac)ool {a}", "zsh", "REVIEW7 F1"),
    ("r7-f1-cmdsub-repeat-case", "$(repeat 1 case x in x) printf p;; esac)ool {a}", "zsh", "REVIEW7 F1"),
    ("r7-f2-eqparen-case", ": =(case x in x) :;; esac) (x # " + _R12_N + ")", "zsh", "REVIEW7 F2"),
    # found by Director C11 (r11 out of scope; a sealed zsh runs them):
    ("c11-case-brace-form", "case x {\n(x # " + _R12_N + ") :;; }", "zsh", "C11 F1"),
    ("c11-coproc-case", "coproc case x in\n(x # " + _R12_N + ") :;; esac\nwait", "zsh", "C11 F1"),
    ("c11-if-short-case", "if [[ a ]] case x in\n(x # " + _R12_N + ") :;; esac", "zsh", "C11 F1"),
    ("c11-arm-after-pattern-case", "case x in (x) case y in\n(y # " + _R12_N + ") :;; esac;; esac", "zsh",
     "C11 F1"),
    ("c11-fd-case-sub-sh", '2>/dev/null case x in\n(x # $($(: "("; printf s)ub.sh {a})) :;; esac', "zsh",
     "C11 F1"),
    ("c11-eqparen-case-slot-py", ': =(case x in x) :;; esac) (x # $($(: "("; printf sl)ot.py {a}))', "zsh",
     "C11 F2"),
]


def _r12_escape_command(row: tuple, args: str | None = None) -> str:
    return row[1].replace("{a}", args or _r11_launch_args(row))


#: Every r11 ARMED allow expectation r12 turns into a DENY — in-process rows
#: (by command) and budget/table rows (by id). All hold a shell construct and
#: are not an admitted form; the C11 ledger lists them ("armed flips").
_R12_ARMED_FLIPS = frozenset({
    "TOOL=ls; $TOOL -la /tmp",
    "jq -r '.models[]' config.json",
    "cd ${HOME:-/Users/me} && echo ok",
    'echo "${name//-/_}"',
    "git commit -m \"$(cat <<'EOF'\nr10: don't (see $(x))\nEOF\n)\"",
    'ssh h "x=\\$(cat ${F}); echo \\$x"',
    'bash -c "n=\\$(wc -l < ${F}); echo \\$n"',
})
_R12_ARMED_FLIP_ROW_IDS = (
    "computed-word-out-of-scope", "env-word-out-of-scope", "glob-head",
    "rv-bracket-run-no-wrapper", "rv-subscript-run-no-wrapper",
    "r9-joined-glue-one-word-no-wrapper", "r9-joined-partial-one-word-no-wrapper",
    "r9-joined-construct-quote-run-no-wrapper", "r9-escaped-cmdsub-run-no-wrapper",
    "r10-param-sq-default-run-no-wrapper", "r10-assign-cmdsub-run-no-wrapper",
    "r10-quoted-paren-cmdsub-run-no-wrapper", "r10-deferred-sq-cmdsub-run-no-wrapper",
    "r10-closed-heredoc-run-no-wrapper", "r10-quoted-heredoc-prose-run-no-wrapper",
    "r10-backtick-run-no-wrapper", "r10-escaped-dq-cmdsub-run-no-wrapper",
    "r10-unclosed-sq-tail-no-wrapper",
    "r11-arith-long-no-wrapper", "r11-dparen-shift-lines-no-wrapper",
    "r11-dollar-arith-cmdsub-no-wrapper", "r11-for-arith-no-wrapper", "r11-dq-brace-no-wrapper",
    "r11-dq-word-fragments-no-wrapper", "r11-deferred-joined-no-wrapper",
    "r11-argument-group-comment-lines-no-wrapper", "r11-case-pattern-groups-no-wrapper",
    "r11-case-terminators-no-wrapper", "r11-arith-base-no-wrapper",
    "r11-uncertain-dparen-no-wrapper", "r11-dq-param-cmdsub-no-wrapper",
    "r11-continuation-dq-param-cmdsub-no-wrapper",
)


def _r12_armed_expectation(command: str, r11_expected: str) -> str:
    """The armed verdict r12 expects where r11 expected ``r11_expected``."""
    return "deny" if command in _R12_ARMED_FLIPS else r11_expected


def test_r12_armed_flips_are_exactly_construct_bearing_refusals() -> None:
    """Every flipped expectation holds a shell construct, and every flipped
    row now carries the structural expectation (none silently dropped)."""
    assert all(guard.r12_constructs(command) for command in _R12_ARMED_FLIPS)
    rows = {row[0]: row for table in (
        _R6_TABLE, _R7_BUDGET_ROWS, _R8_BUDGET_ROWS, _R9_BUDGET_ROWS, _R10_BUDGET_ROWS,
        _R11_BUDGET_ROWS,
    ) for row in table}
    assert len(_R12_ARMED_FLIP_ROW_IDS) == len(set(_R12_ARMED_FLIP_ROW_IDS)) == 32
    for row_id in _R12_ARMED_FLIP_ROW_IDS:
        row = rows[row_id]
        assert row[-1] in ("R12_SHELL_CONSTRUCT", "deny"), row_id
    assert len(_R12_ARMED_FLIPS) + len(_R12_ARMED_FLIP_ROW_IDS) == 39


def _r12_scanner_off(monkeypatch: pytest.MonkeyPatch) -> None:
    """The r6–r11 scanner answers "names no wrapper" for every text."""
    monkeypatch.setattr(guard, "r6_names_wrapper", lambda _raw: False)
    monkeypatch.setattr(guard, "_r10_lexed_reading", lambda _raw: False)


def test_r12_sealed_zsh_runs_each_escape(tmp_path: Path) -> None:
    """Ground truth for _R12_ESCAPES: each shape EXECUTES a fake wrapper in a
    sealed zsh (``env -i``, ``zsh -f``; PATH = fake wrappers + /usr/bin:/bin)."""
    run = _r11_sealed_shells(tmp_path)
    checked = 0
    for row in _R12_ESCAPES:
        for shell_name in row[2].split():
            tag = "r12" + shell_name + row[0].replace("-", "")
            command = _r12_escape_command(row, tag)
            markers = [name for name in run(command, shell_name) if name.endswith("-" + tag)]
            assert markers, (row[0], shell_name, command)
            checked += 1
    assert checked == len(_R12_ESCAPES) == 18
    origins = [row[3] for row in _R12_ESCAPES]
    assert origins.count("REVIEW7 F1") == 11 and origins.count("REVIEW7 F2") == 1


@pytest.mark.parametrize("row", _R12_ESCAPES, ids=[row[0] for row in _R12_ESCAPES])
def test_r12_escapes_are_refused_armed_by_structure_alone(
    shared_placement: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    row: tuple,
) -> None:
    """Armed, bound and unbound: DENY with the structural code, the gate
    never reached — and the same verdict and reason with the scanner off."""
    command = _r12_escape_command(row)
    assert guard.r12_constructs(command) and guard.r12_armed_in_scope(command)
    with_scanner = _r7_both(guard, shared_placement, monkeypatch, tmp_path, capsys, command)
    _r12_scanner_off(monkeypatch)
    without = _r7_both(guard, shared_placement, monkeypatch, tmp_path, capsys, command)
    assert with_scanner == without
    for verdict, reason, gate in without:
        assert (verdict, gate) == ("deny", False), reason
        assert "R12_SHELL_CONSTRUCT" in reason and guard._R12_HEADLINE in reason, reason
        assert "guard budget exceeded" not in reason


@pytest.mark.parametrize("row", _R12_ESCAPES, ids=[row[0] for row in _R12_ESCAPES])
def test_r12_f1_f2_scanner_fixes_name_each_escape(row: tuple) -> None:
    """The secondary (and unarmed) reading now names every F1/F2 row too —
    r11's scanner named none of them (C11 ledger, fail-before)."""
    command = _r12_escape_command(row)
    assert guard._r10_lexed_reading(command), command
    assert guard.r6_names_wrapper(command), command


@pytest.mark.parametrize("row_id", [
    "r7-f1-fd-case-in-newline", "r7-f1-cmdsub-fd-case", "r7-f2-eqparen-case", "c11-case-brace-form",
])
@pytest.mark.parametrize("bound", [True, False], ids=["bound", "unbound"])
def test_r12_rows_through_the_real_hook_command_line(tmp_path: Path, row_id: str, bound: bool) -> None:
    row = next(row for row in _R12_ESCAPES if row[0] == row_id)
    elapsed, code, out = _r8_hook_cli(tmp_path, _r12_escape_command(row), bound=bound, owner=bound)
    assert code == 0 and out, out
    decision = json.loads(out)["hookSpecificOutput"]
    assert decision["permissionDecision"] == "deny"
    reason = decision["permissionDecisionReason"]
    assert reason.startswith("Mastermind shared-placement guard: unobservable launch — " + guard._R12_HEADLINE)
    assert "R12_SHELL_CONSTRUCT" in reason and "missing binding" not in reason, reason
    assert elapsed < 4.0, elapsed


# --- r12 (1): every escape row of REVIEW2–REVIEW7 / C5–C11 — structure alone --

def _r12_escape_corpus() -> list[tuple[str, str]]:
    """``(origin, command)`` for every escape row this module encodes from
    REVIEW2–REVIEW7 and the C5–C11 ledgers: each table's refused-by-shape rows
    (identity rows that reach the gate are not shape escapes)."""
    rows: list[tuple[str, str]] = []
    rows += [("r6:" + row[0], row[1]) for row in _R6_TABLE if row[2] == "deny"]
    rows += [("r7-review2:" + row[0], row[1]) for row in _R7_REVIEW2_TABLE
             if row[2] == "deny" and not row[4]]
    rows += [("r7-read-refused", command) for command in _R7_READ_FORMS_REFUSED]
    rows += [("r7-hook:" + row[0], row[1]) for row in _R7_HOOK_ROWS if row[2].startswith("R6_")]
    rows += [("r8-scope:" + row[0], _r8_escape_command(row[1], args))
             for row in _R8_SCOPE_ESCAPES
             for args in ("run grok a /tmp grok-4", "glm-memory a", "glm a /tmp glm-5.3")]
    rows += [("r8-git", command) for command in _R8_GIT_REFUSED]
    rows += [("r9:" + row[0], _r9_escape_command(row)) for row in _R9_SCOPE_ESCAPES]
    rows += [("r10:" + row[0], _r10_escape_command(row)) for row in _R10_N1_ESCAPES]
    rows += [("r11:" + row[0], _r11_escape_command(row)) for row in _R11_ESCAPES]
    rows += [("r12:" + row[0], _r12_escape_command(row)) for row in _R12_ESCAPES]
    return rows


def test_r12_structural_table_every_escape_row_denies_without_the_scanner(
    shared_placement: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """(1) Every escape row DENIES armed, bound and unbound, never reaching
    the gate; with the scanner answering "names no wrapper" the verdicts AND
    reasons are unchanged; a row holding a construct carries the structural
    code R12_SHELL_CONSTRUCT (the others are in scope by the literal check
    and refused with their R6 codes)."""
    corpus = _r12_escape_corpus()
    assert len(corpus) >= 335, len(corpus)
    real = [_r7_both(guard, shared_placement, monkeypatch, tmp_path, capsys, command)
            for _, command in corpus]
    _r12_scanner_off(monkeypatch)
    blind = [_r7_both(guard, shared_placement, monkeypatch, tmp_path, capsys, command)
             for _, command in corpus]
    constructs = 0
    for (origin, command), with_scanner, without in zip(corpus, real, blind):
        assert with_scanner == without, (origin, command)
        for verdict, reason, gate in without:
            assert (verdict, gate) == ("deny", False), (origin, command, reason[:300])
            assert "R6_" in reason or "R12_" in reason, (origin, reason[:300])
        if guard.r12_constructs(command):
            constructs += 1
            assert "R12_SHELL_CONSTRUCT" in without[0][1], (origin, command)
        else:
            assert guard.r12_literal_names_wrapper(command), (origin, command)
    assert constructs >= 200, constructs


#: The ledgers and review records whose code spans are harvested.
_R12_HARVEST_DOCS = (
    *(f"REVIEW{n}_" for n in range(2, 8)),
    *(f"LANE_EXECUTIVE_DIRECTOR_C{n}.md" for n in range(5, 12)),
)
_R12_HARVEST_SKIP_RE = _r8_re.compile(
    r"\b(?:rm|curl|wget|ssh|scp|sudo|kill|launchctl|osascript|open|defaults|security|mv|dd"
    r"|chmod|chown|reboot|shutdown)\b|git\s+push"
)


def _r12_doc_spans() -> list[tuple[str, str]]:
    """Every inline code span of the REVIEW2–REVIEW7 records and the C5–C11
    ledgers that mentions a wrapper (``⏎`` read as a newline; the records'
    ``A`` / ``…N1…`` abbreviations also expanded), minus spans naming a
    network/destructive program (never run, even sealed)."""
    directory = Path(__file__).resolve().parents[1] / "integrations" / "mmos"
    spans: list[tuple[str, str]] = []
    seen: set[str] = set()
    args = "run grok a /tmp grok-4"
    for path in sorted(directory.glob("*.md")):
        if not path.name.startswith(_R12_HARVEST_DOCS):
            continue
        text = path.read_text(encoding="utf-8")
        for match in _r8_re.finditer(r"(?<!`)(``?)(?!`)(.+?)(?<!`)\1(?!`)", text):
            body = match.group(2).strip() if match.group(1) == "``" else match.group(2)
            body = body.replace("⏎", "\n")
            for variant in (body, body.replace(" A", " " + args).replace(
                    "…N1…", '$(: "("; printf p)ool ' + args)):
                if (variant in seen or len(variant) > 3000
                        or not _r8_re.search(r"ool|ub\.sh|ot\.py|slot|pool", variant)
                        or _R12_HARVEST_SKIP_RE.search(variant)):
                    continue
                seen.add(variant)
                spans.append((path.name, variant))
    return spans


def test_r12_every_documented_wrapper_running_span_is_refused_or_gated(
    shared_placement: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """(1) The records themselves: every documented code span that RUNS a
    fake wrapper in a sealed zsh or bash is, armed and with the scanner off,
    either DENIED or a launch that reaches the binding gate (bound and
    unbound) — none is allowed unjudged. (Measured at C11: 188 such spans,
    150 denied, 38 plain launches gated; r11 allowed 2 unjudged.)"""
    (tmp_path / "sealed").mkdir()
    run = _r11_sealed_shells(tmp_path / "sealed")
    spans = [(doc, command) for doc, command in _r12_doc_spans()
             if command not in _R12_KNOWN_LIMIT_SPANS]
    running = [(doc, command) for doc, command in spans
               if run(command, "zsh") or run(command, "bash")]
    assert len(running) >= 188, len(running)
    _r12_scanner_off(monkeypatch)
    denied = gated = 0
    for doc, command in running:
        bound, nobind = _r7_both(guard, shared_placement, monkeypatch, tmp_path, capsys, command)
        if bound[0] == "deny" and not bound[2]:
            assert nobind[0] == "deny" and not nobind[2], (doc, command)
            denied += 1
            continue
        assert bound[2] and nobind[2], (doc, command, bound[1][:200])  # the gate judged it
        gated += 1
    assert denied >= 150 and denied + gated == len(running)


#: KNOWN LIMIT (the arbitrary-process class, REVIEW_2329 r2; C11 ledger
#: limit 2): construct-free text in which a PROGRAM computes the name and
#: another program executes it. r12 decides shell structure, not what
#: printf/base64/an interpreter computes. Documented in the C11 ledger, so
#: excluded from the harvest above and pinned here instead.
_R12_KNOWN_LIMIT_SPANS = frozenset({
    "printf '\\160ool run grok a /tmp grok-4' | sh",
    "echo cG9vbCBydW4gZ3JvayBhIC90bXAgZ3Jvay00 | base64 -d | sh",
})


def test_r12_known_limits_are_pinned(
    shared_placement: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """PINS A KNOWN LIMIT, not a desired property: these run the (fake)
    wrapper in a sealed shell and an armed session allows them unjudged."""
    (tmp_path / "sealed").mkdir()
    run = _r11_sealed_shells(tmp_path / "sealed")
    for command in sorted(_R12_KNOWN_LIMIT_SPANS):
        assert run(command, "zsh") and run(command, "bash"), command
        assert guard.r12_constructs(command) == [] and not guard.r12_armed_in_scope(command)
        (bound, _, gate), (nobind, _, _) = _r7_both(
            guard, shared_placement, monkeypatch, tmp_path, capsys, command
        )
        assert (bound, nobind, gate) == ("allow", "allow", False)


# --- r12 (3): honest armed controls -----------------------------------------

#: (command, kind): ``launch`` → bound ALLOW through the gate, unbound
#: "missing binding"; ``allow`` → ALLOW both, gate unreached.
_R12_HONEST_CONTROLS = [
    (_R6_L, "launch"),
    (_R6_P + "python3 /opt/mastermind/ext/slot.py glm -- run", "launch"),
    ("bash -c '" + _R6_L + "'", "launch"),
    (_R6_B, "launch"),
    ("cat /opt/mastermind/ext/sub.sh", "allow"),
    ("python3 -m pytest tests/test_provider_orchestrator_policy.py", "allow"),
    ("gh pr view 2329", "allow"),
    ('git commit -m "fix pool"', "allow"),
    ("git commit -F msg.txt", "allow"),
    ("git log --oneline -5", "allow"),
    ("rg -n foo src", "allow"),
    ("sed -n 1,5p f", "allow"),
    ("ls -la", "allow"),
    # literal-only commands with quotes and redirections (out of scope)
    ("echo 'a b; c' > /dev/null", "allow"),
    ('git status --short 2>/dev/null', "allow"),
    ("printf 'x\\n' > out.txt", "allow"),
    ("wc -l < README.md", "allow"),
    ('npm test -- --runInBand "a b"', "allow"),
    ("{ echo grouped; }", "allow"),
    ("git log -1 --format='%H %s'", "allow"),
    ("make -C build test 2>&1 | tail -n 20", "allow"),
    # constructs inside an ADMITTED read form (in scope, admitted)
    ("git diff --stat HEAD~1", "allow"),
    ("git log --oneline HEAD^..HEAD", "allow"),
    ("ls ~/notes", "allow"),
    ("cat docs/*.md", "allow"),
    ("grep -rn 'TODO(' src", "allow"),
    ("rg -n 'foo$' src", "allow"),
    ("echo hi # a comment", "allow"),
]


@pytest.mark.parametrize("command, kind", _R12_HONEST_CONTROLS)
def test_r12_honest_armed_controls_still_pass(
    shared_placement: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    command: str,
    kind: str,
) -> None:
    (bound, bound_reason, bound_gate), (nobind, nobind_reason, nobind_gate) = _r7_both(
        guard, shared_placement, monkeypatch, tmp_path, capsys, command
    )
    if kind == "launch":
        assert (bound, bound_gate) == ("allow", True), bound_reason
        assert (nobind, nobind_gate) == ("deny", True) and "missing binding" in nobind_reason
    else:
        assert (bound, nobind) == ("allow", "allow"), (bound_reason, nobind_reason)
        assert (bound_gate, nobind_gate) == (False, False)


def test_r12_pytest_k_pool_is_still_refused_by_the_name_rule(
    shared_placement: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """``pytest -k pool`` holds no construct; it is refused by the r7 NAME
    rule (the literal wrapper name in a command that is not an admitted
    form), unchanged since r7 — not by r12."""
    command = "pytest -k pool"
    assert guard.r12_constructs(command) == [] and guard.r12_literal_names_wrapper(command)
    (bound, reason, gate), (nobind, _, _) = _r7_both(
        guard, shared_placement, monkeypatch, tmp_path, capsys, command
    )
    assert (bound, nobind, gate) == ("deny", "deny", False)
    assert "mentions a paid-launch wrapper name" in reason and "R12_" not in reason


# --- r12 (4): the new over-refusal class, stated ----------------------------

#: Realistic commands armed sessions now REFUSE (the principal's fail-closed
#: trade); each has a literal form or a tool: write the value literally, pass
#: a file (``git commit -F``), or use Read/Grep/Glob.
_R12_OVER_REFUSALS = [
    'cd "$(git rev-parse --show-toplevel)"',
    "git commit -m \"$(cat <<'EOF'\nfix: guard r12\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>\nEOF\n)\"",
    'echo "${HOME}/notes"',
    'export PATH="$HOME/.local/bin:$PATH"',
    'for f in *.py; do wc -l "$f"; done',
    "ls $(git rev-parse --show-toplevel)",
    'git log "$(git merge-base origin/master HEAD)"..HEAD',
    "DATE=$(date +%Y%m%d); echo $DATE",
    'cat "${TMPDIR:-/tmp}/out.log"',
    "pytest -q $(git diff --name-only | grep test_)",
    "wc -l $(rg -l foo src)",
    'test -n "${CI:-}" && echo ci',
    "out=$((cd a && make) 2>&1)",
    'python3 -c "import sys; print(sys.version)"',
    "gh pr view 2329 --json statusCheckRollup --jq '.statusCheckRollup[].conclusion'",
    "jq -r '.models[]' config.json",
    "awk '{print $1}' results.txt",
    "find . -name '*.py' -newer setup.cfg",
    "(cd sub && make)",
    "source .venv/bin/activate",
]


@pytest.mark.parametrize("command", _R12_OVER_REFUSALS)
def test_r12_over_refusal_class_is_refused_with_the_r12_reason(
    shared_placement: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    command: str,
) -> None:
    """KNOWN, INTENDED over-refusal (armed only): the exact reason tells the
    worker to use a literal command, a file argument or the Read/Grep tools."""
    assert guard.r12_constructs(command)
    (bound, reason, gate), (nobind, nobind_reason, nobind_gate) = _r7_both(
        guard, shared_placement, monkeypatch, tmp_path, capsys, command
    )
    assert (bound, nobind, gate, nobind_gate) == ("deny", "deny", False, False)
    assert reason == nobind_reason
    assert reason.startswith(
        "Mastermind shared-placement guard: unobservable launch — armed session: shell "
        "expansion is not admitted; use a literal command or a file argument."
    ), reason
    assert "R12_SHELL_CONSTRUCT" in reason and "Read/Grep/Glob" in reason
    assert "git commit -F FILE" in reason


def test_r12_over_refusals_have_admitted_alternatives(
    shared_placement: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    for command in ("git commit -F msg.txt", "git log --oneline origin/master..HEAD",
                    "wc -l src/a.py src/b.py", "cat /tmp/out.log"):
        (bound, reason, _), (nobind, _, _) = _r7_both(
            guard, shared_placement, monkeypatch, tmp_path, capsys, command
        )
        assert (bound, nobind) == ("allow", "allow"), (command, reason)
    # the unarmed session keeps every one of them (r12 is armed-only)
    monkeypatch.delenv("MASTERMIND_SHARED_PLACEMENT", raising=False)
    monkeypatch.delenv("POOL_EXECUTION_BINDING", raising=False)
    for command in _R12_OVER_REFUSALS:
        assert _r6_verdict(guard, shared_placement, command, capsys)[0] == "allow", command


# --- r12: the rule itself, token by token -----------------------------------

@pytest.mark.parametrize("text, kind", [
    ("$(x)", "$( "), ("$((1))", "$(( "), ("${x}", "${ "), ("$[1]", "$[ "), ("$'a'", "$' "),
    ('$"a"', '$" '), ("$x", "$ (parameter"), ("`x`", "` "), ("a\\\nb", "line continuation"),
    ("cat <<E", "<< "), ("cat <<<x", "<< "), ("ls <1-5>", "numeric glob"), ("a*", "* "),
    ("a?", "? "), ("a[b]", "[ "), ("a{b,c}", "{ "), ("p{},ool}", "{ "), ("(a)", "( ) "),
    ("a)", "( ) "), ("~/x", "~ "), ("HEAD~1", "~ "), ("a # c", "# "), ("a#b", "# "),
    ("^x", "^ "), ("a!b", "! "), ("x\x01", "control character"), ("x\r", "control character"),
    ("'$(x)'", "$( "), ("'p*l'", "* "), ('"(x)"', "( ) "), ("eval x", "eval"),
    ("e\\val x", "eval"), ("'ev'al x", "eval"), ("source f", "source"), ("alias x=y", "alias"),
    ("trap x EXIT", "trap"), ("coproc x", "coproc"), ("repeat 3 x", "repeat"),
])
def test_r12_construct_detection_reads_every_kind_quoted_or_not(text: str, kind: str) -> None:
    found = guard.r12_constructs(text)
    assert found and any(kind in item for item in found), (text, found)
    assert guard.r12_armed_in_scope(text)


@pytest.mark.parametrize("text", [
    "ls -la", "git log --oneline -5", "a 'b c' \"d e\" f\\ g", "a; b && c || d | e & f",
    "a > /dev/null 2>&1 < in", "{ a; }", "{\na\n}", "a {", "a !", "if ! a; then b; fi",
    'git commit -m "fix!"', "x=1 y=2 cmd", "printf '%s\\n' a", "a\tb\nc", "a=b,c:d@e+f%g",
    "echo evaluate sourced aliases traps repeats", "echo .", ". ./x.sh",
])
def test_r12_literal_text_is_construct_free(text: str) -> None:
    assert guard.r12_constructs(text) == [], text


def test_r12_literal_check_joins_quotes_and_reads_the_slot_module() -> None:
    for text in ("p'o'ol run", 'p"oo"l run', "p\\ool run", "-O'pool run'", "/x/'sub'.sh a",
                 "python3 -m slot glm -- run", "python3 -mslot glm", "python3 -m pkg.slot x",
                 "bash -c 'po\"o\"l run'", "env pool run", "x/remote_sub.sh h m"):
        assert guard.r12_literal_names_wrapper(text), text
    for text in ("spool run", "pooled", "timeslot", "slots", "slot_id", "subsh", "python3 -m pytest"):
        assert not guard.r12_literal_names_wrapper(text), text


def test_r12_out_of_scope_needs_every_condition(monkeypatch: pytest.MonkeyPatch) -> None:
    """Out of scope = construct-free AND literally unnamed AND lexable AND not
    named by the (secondary) scanner; each condition alone puts it in scope."""
    assert not guard.r12_armed_in_scope("ls -la")
    assert guard.r12_armed_in_scope("ls -la $x")  # construct
    assert guard.r12_armed_in_scope("ls -la pool")  # literal name
    assert guard.r12_armed_in_scope("ls 'unterminated")  # tokenizer fails
    monkeypatch.setattr(guard, "r6_names_wrapper", lambda _raw: True)
    assert guard.r12_armed_in_scope("ls -la")  # the scanner may widen …
    monkeypatch.setattr(guard, "r6_names_wrapper", lambda _raw: False)
    assert guard.r12_armed_in_scope("ls -la $x")  # … but never narrows


def test_r12_scanner_is_not_consulted_for_construct_bearing_commands(
    shared_placement: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls: list[str] = []

    def spy(raw: str) -> bool:
        calls.append(raw)
        return False

    monkeypatch.setattr(guard, "r6_names_wrapper", spy)
    _r7_both(guard, shared_placement, monkeypatch, tmp_path, capsys, '$(: "("; printf p)ool run grok a /tmp grok-4')
    _r7_both(guard, shared_placement, monkeypatch, tmp_path, capsys, "pytest -k pool")
    assert calls == []
    _r7_both(guard, shared_placement, monkeypatch, tmp_path, capsys, "ls -la")
    assert calls == ["ls -la", "ls -la"]


def test_r12_construct_scan_is_linear() -> None:
    import time

    for unit in ("a ", "'a b' ", '"a" ', "a\\ b ", "e\\val ", "$", "{ ", "!!", "pool ", "-a/"):
        timings = []
        for size in (65_536, 262_144):
            text = (unit * (size // len(unit) + 1))[:size]
            started = time.perf_counter()
            guard.r12_constructs(text)
            guard.r12_literal_names_wrapper(text)
            timings.append(time.perf_counter() - started)
        assert timings[1] < 0.5, (unit, timings)
        assert timings[1] < 8 * timings[0] + 0.02, (unit, timings)


# --- r12 (5): unarmed byte-identity (N2 shapes, gh CI-wait text) ------------

#: sha256 of the unarmed hook stdout measured on r11 (13177c94a) through the
#: real hook command line; r12 must reproduce each byte for byte. The one
#: intended difference is the F1 row under N2: r11 gave no decision (its
#: scanner missed the name), r12 denies like every other N2 shape.
_R12_UNARMED_ROWS = [
    # (id, command, budget, background, sha256 of stdout)
    ("n2-literal-launch", "pool run grok a /tmp grok-4\n" + "<<A\n" * 24_000, "1.5", False,
     "878ec4b96e82ec46c223b50065435ede1b83237b09d6daa25c68f2ad17d8f3dc"),
    ("n2-n1-launch", '$(: "("; printf p)ool run grok a /tmp grok-4\n' + "<<A\n" * 24_000, "1.5", False,
     "878ec4b96e82ec46c223b50065435ede1b83237b09d6daa25c68f2ad17d8f3dc"),
    ("n2-sub-sh", "sub.sh glm-memory a\n" + "<<A\n" * 24_000, "1.5", False,
     "878ec4b96e82ec46c223b50065435ede1b83237b09d6daa25c68f2ad17d8f3dc"),
    ("ci-f4-newline-run", _R9_F4_TEXT, "1.5", False,
     "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"),
    ("ci-gh-heredoc-unclosed", "gh run view 1\n" + "<<A\n" * 40000, "1.5", False,
     "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"),
    ("ci-gh-run-watch-foreground", "gh run watch 123 --interval 150", None, False,
     "b5f09e5cc521a8269431960ba9678864181ae785bfb0b7a37280d904801b7e0b"),
    ("ci-gh-run-watch-no-interval-bg", "gh run watch 123", None, True,
     "b6fed84ef4c8fa2c76cd7aa6124b1a8571664a70d65e77d1179c260cebdfca17"),
    ("ci-gh-pr-checks-watch-fast", "gh pr checks 9 --watch --interval 5", None, True,
     "b6fed84ef4c8fa2c76cd7aa6124b1a8571664a70d65e77d1179c260cebdfca17"),
    ("ci-gh-loop-poll", "for i in 1 2 3; do gh run view 123; sleep 30; done", None, False,
     "274a7fd529f1eda81892563a48d528cc1571fb94e62628a6a2fba2f520718497"),
    ("ci-gh-delayed-poll", "sleep 60 && gh pr checks 9", None, False,
     "274a7fd529f1eda81892563a48d528cc1571fb94e62628a6a2fba2f520718497"),
    ("ci-gh-watch-bg-ok", "gh run watch 123 --interval 150", None, True,
     "ec1aa5b26f48f3c08e1ccb246389fbde2c2ae51aedbde1701fd5493e7a47d7e4"),
    ("ci-gh-read-once", "gh run view 9101", None, False,
     "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"),
    ("unarmed-launch-missing-identity", "pool run grok a /tmp grok-4", None, False,
     "9decb765ee27e12257df1806d9160f4e2e72c71a752e5424f77f6c58576026a9"),
    ("unarmed-cmdsub-text", 'cd "$(git rev-parse --show-toplevel)"', None, False,
     "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"),
    ("unarmed-f1-row-no-watchdog",
     '2>/dev/null case x in\n(x # $($(: "("; printf p)ool run grok a /tmp grok-4)) :;; esac', None, False,
     "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"),
    # intended change: r11 e3b0c442… (no decision), r12 the N2 denial
    ("n2-f1-row", '2>/dev/null case x in\n(x # $($(: "("; printf p)ool run grok a /tmp grok-4)) :;; esac\n'
     + "<<A\n" * 24_000, "1.5", False,
     "878ec4b96e82ec46c223b50065435ede1b83237b09d6daa25c68f2ad17d8f3dc"),
]


@pytest.mark.parametrize("row", _R12_UNARMED_ROWS, ids=[row[0] for row in _R12_UNARMED_ROWS])
def test_r12_unarmed_output_is_byte_identical_to_r11(tmp_path: Path, row: tuple) -> None:
    import hashlib
    import shutil
    import subprocess
    import time

    if shutil.which("python3") is None:
        pytest.skip("no python3 on PATH for the registered hook command")
    _, command, budget, background, digest = row
    module_path = os.environ.get("MASTERMIND_R6_GUARD_UNDER_TEST", "").strip() or guard.__file__
    env, cwd = _r8_hook_env(tmp_path, bound=False)
    env.pop("MASTERMIND_SHARED_PLACEMENT", None)
    env.update({name: "" for name in ("POOL_ORCHESTRATOR_ID", "POOL_PARENT_RUN_ID", "POOL_TASK_CLASS")})
    if budget:
        env["MASTERMIND_GUARD_BUDGET_S"] = budget
    payload = _payload(cwd, command, background=background)
    started = time.monotonic()
    result = subprocess.run(
        ["/bin/sh", "-c", f'python3 "{module_path}"'], input=json.dumps(payload), env=env,
        capture_output=True, text=True, timeout=60, check=False,
    )
    assert result.returncode == 0, result.stderr
    assert hashlib.sha256(result.stdout.encode()).hexdigest() == digest, result.stdout[:300]
    assert time.monotonic() - started < 4.0


# --- r12 (6): fuzz -----------------------------------------------------------

def _r12_armed_outcome(command: str) -> str:
    """The armed decision class without the binding gate's own checks:
    ``out`` (out of scope), ``deny`` (refused by shape), ``read`` (admitted,
    no launch), ``launch`` (admitted; the binding gate judges it)."""
    if not guard.r12_armed_in_scope(command):
        return "out"
    parse = guard._r7_parse(command, nested=False)
    if parse.refused:
        return "deny"
    return "launch" if parse.launches else "read"


def test_r12_armed_structured_fuzz_is_structural(tmp_path: Path) -> None:
    """(6) The committed generator, now with the F1/F2 prefixes, contexts and
    glue, judged ARMED: every out-of-scope candidate is construct-free (here:
    none — every candidate computes a word), every in-scope candidate the
    grammar does not admit is denied, and no admitted non-launch candidate
    runs a wrapper in sealed zsh or bash."""
    count = int(os.environ.get("MASTERMIND_GUARD_FUZZ_N", "3000"))
    seed = int(os.environ.get("MASTERMIND_GUARD_FUZZ_SEED", "20261113"))
    run = _r11_sealed_shells(tmp_path)
    outcomes: dict[str, list[str]] = {"out": [], "deny": [], "read": [], "launch": []}
    for command in _r11_fuzz_candidates(seed, count):
        outcomes[_r12_armed_outcome(command)].append(command)
    assert all(guard.r12_constructs(command) == [] for command in outcomes["out"])
    escapes = [
        (command, shell) for command in outcomes["out"] + outcomes["read"]
        for shell in ("zsh", "bash") if run(command, shell)
    ]
    assert escapes == [], escapes[:5]
    assert len(outcomes["deny"]) >= count * 9 // 10, {k: len(v) for k, v in outcomes.items()}


#: Construct-free pieces: quotes, backslashes, operators, wrapper fragments
#: and the programs that hand text to another shell.
_R12_LITERAL_PIECES = [
    "p", "o", "ol", "ool", "s", "ub", ".sh", "sl", "ot", ".py", "remote_", "/", "./", "x/",
    "'", '"', "\\", " ", "\t", "\n", ";", "&", "|", "&&", "||", ">", "<", ">/dev/null", "2>&1",
    " run grok a /tmp grok-4", " glm-memory a", " glm a /tmp glm-5.3", "bash -c ", "sh -c ",
    "zsh -fc ", "env ", "command ", "exec ", "nohup ", "x=", "python3 ", "-m ", "-O", "-c",
    "echo ", "printf ", "xargs ", ": ", "if true; then ", "; fi", "while false; do :; done; ",
    "{ ", "; }", "a", "-", ".", ",", ":", "@", "%", "+", "=",
]


def _r12_literal_candidates(seed: int, count: int) -> list[str]:
    import random

    rng = random.Random(seed)
    seen: set[str] = set()
    out: list[str] = []
    while len(out) < count:
        command = "".join(rng.choice(_R12_LITERAL_PIECES) for _ in range(rng.randint(2, 14)))
        if command not in seen:
            seen.add(command)
            out.append(command)
    return out


def test_r12_literal_fuzz_out_of_scope_runs_nothing(tmp_path: Path) -> None:
    """(6) Construct-free text with wrapper fragments, quotes, backslashes,
    operators and nested ``-c`` bodies: every candidate the ARMED rule leaves
    out of scope is construct-free and runs NO wrapper in sealed zsh or bash."""
    count = int(os.environ.get("MASTERMIND_GUARD_LITERAL_FUZZ_N", "1500"))
    seed = int(os.environ.get("MASTERMIND_GUARD_LITERAL_FUZZ_SEED", "20261116"))
    run = _r11_sealed_shells(tmp_path)
    candidates = _r12_literal_candidates(seed, count)
    out_of_scope = [command for command in candidates if not guard.r12_armed_in_scope(command)]
    assert all(guard.r12_constructs(command) == [] for command in out_of_scope)
    assert all(not guard.r12_literal_names_wrapper(command) for command in out_of_scope)
    escapes = [
        (command, shell) for command in out_of_scope for shell in ("zsh", "bash")
        if run(command, shell)
    ]
    assert escapes == [], escapes[:5]
    assert len(out_of_scope) >= count // 4  # the generator reaches the out-of-scope side


@pytest.mark.parametrize("command", [
    "p'o'ol run {a}", 'p"oo"l run {a}', "p\\ool run {a}", "'pool' run {a}", "\\pool run {a}",
    "bash -c 'po\"o\"l run {a}'", "sh -c \"p'o'ol run {a}\"", "env p''ool run {a}",
    "command 'po'ol run {a}", "x=1 po\"\"ol run {a}", "'s'ub.sh {a}",
])
def test_r12_literal_joined_names_run_and_are_in_scope(tmp_path: Path, command: str) -> None:
    """Liveness of the literal check: quote/backslash-joined wrapper names DO
    run in a sealed shell, and the armed rule puts each in scope."""
    run = _r11_sealed_shells(tmp_path)
    tag = "r12lit"
    assert run(command.replace("{a}", tag), "zsh") or run(command.replace("{a}", tag), "bash")
    live = command.replace("{a}", "run grok a /tmp grok-4" if "ub.sh" not in command else "glm-memory a")
    assert guard.r12_constructs(live) == [] and guard.r12_literal_names_wrapper(live), live
    assert guard.r12_armed_in_scope(live)


def test_r12_mutation_fuzz_has_no_armed_or_scanner_escape(tmp_path: Path) -> None:
    """Mutations of every r10/r11/r12 escape row: ARMED, every out-of-scope
    mutation is construct-free and runs nothing; the (unarmed) scanner leaves
    none out of scope that runs a wrapper."""
    import random

    count = int(os.environ.get("MASTERMIND_GUARD_MUTATIONS_N", "800"))
    seed = int(os.environ.get("MASTERMIND_GUARD_MUTATIONS_SEED", "20261117"))
    run = _r11_sealed_shells(tmp_path)
    rng = random.Random(seed)
    bases = [_r12_escape_command(row) for row in _R12_ESCAPES]
    bases += [_r11_escape_command(row) for row in _R11_ESCAPES]
    tokens = _R11_MUTATION_TOKENS + ["2>/dev/null ", "repeat 1 ", "coproc ", "=(", "case x {\n",
                                     "for x (a) ", "if [[ a ]] ", "(x) ", " in\n", "{fd}>f "]
    seen: set[str] = set()
    mutations: list[str] = []
    while len(mutations) < count:
        command = rng.choice(bases)
        for _ in range(rng.randint(1, 3)):
            at = rng.randint(0, len(command))
            if rng.random() < 0.7:
                command = command[:at] + rng.choice(tokens) + command[at:]
            else:
                command = command[:at] + command[min(len(command), at + rng.randint(1, 4)):]
        if command not in seen:
            seen.add(command)
            mutations.append(command)
    armed_out = [command for command in mutations if not guard.r12_armed_in_scope(command)]
    assert all(guard.r12_constructs(command) == [] for command in armed_out)
    scanner_out = [command for command in mutations if not guard.r6_names_wrapper(command)]
    escapes = [
        (command, shell) for command in set(armed_out) | set(scanner_out)
        for shell in ("zsh", "bash") if run(command, shell)
    ]
    assert escapes == [], escapes[:5]


# --- r12 (7): budgets at 262 144 through the real hook command line ----------

_R12_BUDGET_ROWS = [
    # (id, prefix, unit, suffix, bound, owner channel, verdict fragment)
    # re-check #7 / C11 rows, padded with their own structure
    ("r12-fd-case-glue", "2>/dev/null case x in\n(x # " + _R12_N.format(a=_R7_G) + ") :;; esac\n",
     "2>/dev/null case x in\n(x) :;; esac\n", "", False, False, "R12_SHELL_CONSTRUCT"),
    ("r12-eqparen-case-glue", ": =(case x in x) :;; esac) (x # " + _R12_N.format(a=_R7_G) + ")\n",
     ": =(case x in x) :;; esac)\n", "", False, False, "R12_SHELL_CONSTRUCT"),
    ("r12-repeat-case", "", "repeat 1 case x in\n(x) :;; esac\n", "", False, False, "R12_SHELL_CONSTRUCT"),
    ("r12-coproc-condition", "", "coproc [[ a =~ \n(a) ]]\n", "", False, False, "R12_SHELL_CONSTRUCT"),
    ("r12-for-short-case", "", "for x (a) case x in\n(x) :;; esac\n", "", False, False, "R12_SHELL_CONSTRUCT"),
    ("r12-if-short-condition", "", "if [[ a ]] [[ a =~ \n(a) ]]\n", "", False, False, "R12_SHELL_CONSTRUCT"),
    ("r12-case-brace-form", "", "case x {\n(x) :;; }\n", "", False, False, "R12_SHELL_CONSTRUCT"),
    ("r12-cmdsub-fd-case", "", "$(2>/dev/null case x in x) printf p;; esac)ool ", "", False, False,
     "R12_SHELL_CONSTRUCT"),
    ("r12-fd-prefix-run", "", "2>/dev/null ", "", False, False, "allow"),
    ("r12-repeat-run", "", "repeat 1 ", "", False, False, "R12_SHELL_CONSTRUCT"),
    # construct-bearing fill: refused by structure
    ("r12-cmdsub-run", "", "$(a) ", "", False, False, "R12_SHELL_CONSTRUCT"),
    ("r12-param-run", "", "${HOME}/x ", "", False, False, "R12_SHELL_CONSTRUCT"),
    ("r12-sq-dollar-run", "", "'$x' ", "", False, False, "R12_SHELL_CONSTRUCT"),
    ("r12-quoted-parens-run", "", '"(a)" ', "", False, False, "R12_SHELL_CONSTRUCT"),
    ("r12-glob-run", "", "*.py ", "", False, False, "R12_SHELL_CONSTRUCT"),
    ("r12-comment-lines", "", "# c\n", "", False, False, "R12_SHELL_CONSTRUCT"),
    ("r12-heredoc-run", "", "cat <<E\nx\nE\n", "", False, False, "R12_SHELL_CONSTRUCT"),
    ("r12-continuation-run", "", "a \\\n", "", False, False, "R12_SHELL_CONSTRUCT"),
    ("r12-dollar-run", "", "$", "", False, False, "R12_SHELL_CONSTRUCT"),
    ("r12-bang-run", "", "!a", "", False, False, "R12_SHELL_CONSTRUCT"),
    ("r12-eval-words-run", "", "e\\val ", "", False, False, "R12_SHELL_CONSTRUCT"),
    # constructs inside admitted read forms / launches: admitted
    ("r12-ls-tilde-args", "ls ", "~/x ", "", False, False, "allow"),
    ("r12-git-log-carets", "git log --oneline ", "HEAD^ ", "", False, False, "allow"),
    ("r12-grep-quoted-regex", "grep -n ", "'a(b)*' ", "", False, False, "allow"),
    ("r12-bound-launch-sq-construct-args", "pool run glm a /tmp glm-5.3 ", "'$x' ", "", True, True, "allow"),
    # construct-free: the secondary scanner reads them (allowed)
    ("r12-literal-words", "", "abc ", "", False, False, "allow"),
    ("r12-literal-sq-words", "", "'a b' ", "", False, False, "allow"),
    ("r12-literal-dq-words", "", '"a b" ', "", False, False, "allow"),
    ("r12-literal-escapes", "", "a\\ b ", "", False, False, "allow"),
    ("r12-literal-semicolons", "", "a; ", "", False, False, "allow"),
    ("r12-literal-newlines", "", "a\n", "", False, False, "allow"),
    ("r12-literal-redirections", "", ">/dev/null ", "", False, False, "allow"),
    ("r12-literal-groups", "", "{ a; } ", "", False, False, "allow"),
    ("r12-literal-bash-c-body", "bash -c '", "a b; ", "'", False, False, "allow"),
    ("r12-literal-quote-mix", "", "\"'\"'\"' ", "", False, False, "allow"),
    # literal names: in scope by the literal check
    ("r12-literal-named-echo", "echo ", "pool ", "", False, False, "allow"),
    ("r12-literal-named-joined-soup", "echo ", "p'o'o\"l\" ", "", False, False, "allow"),
    ("r12-literal-named-launch-args", "pool run glm a /tmp glm-5.3 ", "a ", "", True, True, "allow"),
]


@pytest.mark.parametrize("row", _R12_BUDGET_ROWS, ids=[row[0] for row in _R12_BUDGET_ROWS])
def test_r12_budget_rows_finish_through_the_real_hook_command_line(tmp_path: Path, row: tuple) -> None:
    row_id, prefix, unit, suffix, bound, owner, fragment = row
    prefix += " " * ((_R8_CAP - len(prefix) - len(suffix)) % len(unit))  # whole units
    command = _r8_filled(prefix, unit, _R8_CAP, suffix)
    assert len(command) == _R8_CAP
    elapsed, code, out = _r8_hook_cli(tmp_path, command, bound=bound, owner=owner)
    assert code == 0
    if fragment == "allow":
        assert out == "", out[:300]
    else:
        decision = json.loads(out)["hookSpecificOutput"]
        assert decision["permissionDecision"] == "deny", out[:300]
        assert fragment in decision["permissionDecisionReason"], decision["permissionDecisionReason"][:400]
        assert "guard budget exceeded" not in decision["permissionDecisionReason"]
    assert elapsed < 4.0, (row_id, elapsed)


@pytest.mark.parametrize("unit", [
    "2>/dev/null ", "2>/dev/null case x in\n(x) :;; esac\n", "case x in ", "[[ a =~ \n(a) ]] ",
    "repeat 1 ", "coproc ", "for x (a) ", "=(x) ", ": =(case x in x) :;; esac)\n", "(x) ",
    "case x {\n(x) :;; }\n", "if [[ a ]] $(a) ", "{fd}>f ", "3<f $x ",
])
def test_r12_scanner_stays_fast_on_the_f1_f2_shapes(unit: str) -> None:
    """The unarmed (and secondary) reading after the F1/F2 fixes, at the
    armed cap, in process: well inside the budget."""
    import time

    text = (unit * (_R8_CAP // len(unit) + 1))[:_R8_CAP]
    started = time.perf_counter()
    guard.r6_names_wrapper(text)
    assert time.perf_counter() - started < 3.0, unit


# --- r13 (re-check #8): a continuation assembled by quote removal ----------

# Re-check #8 (distinct Opus, at r12; REVIEW8_GUARD_R12_OPUS_20261110.md)
# BLOCKER: ``bash -c "po\\"'⏎'"ol run …"`` holds no construct on the RAW
# bytes and names no wrapper by the quote-joined check (it reads po|ol), yet
# THIS shell's quote removal concatenates the adjacent quoted pieces into the
# one argument ``po\⏎ol run …`` and the admitted nested ``-c`` interpreter
# joins the line continuation: ``pool run …``. r12 allowed it unjudged, the
# gate never reached, in both sealed shells. r13 reads ``\⏎`` on the
# quote-deleted, backslash-preserving view too and joins it before the
# literal name check. In scope, the nested ``bash``/``sh -c`` body parses
# (the lexer joins the continuation) to the bare launch ``pool run …`` and
# REACHES THE BINDING GATE, where the text-regex cross-check cannot attribute
# the launch (the text carries no wrapper invocation) and refuses it as an
# unaccounted descendant — stricter than the honest spelling, which is
# judged and may pass; ``zsh -c`` is not an admitted nested interpreter and
# is refused structurally. Nothing is allowed unjudged any more. MINOR:
# flag-combined ``python3 -Bmslot``.

_R13_ARGS = "run glm a /tmp glm-5.3"  # the fixture binding reserves pool_ref glm
#: (id, command, shells that RUN it (ground truth), origin)
_R13_ESCAPES = [
    ("r8-bash-dq-assembled-continuation", 'bash -c "po\\\\"\'\n\'"ol ' + _R13_ARGS + '"', "zsh bash",
     "REVIEW8 #1"),
    ("r8-sh-dq-assembled-continuation", 'sh -c "po\\\\"\'\n\'"ol ' + _R13_ARGS + '"', "zsh bash",
     "REVIEW8 #1"),
    ("r8-zsh-dq-assembled-continuation", 'zsh -c "po\\\\"\'\n\'"ol ' + _R13_ARGS + '"', "zsh bash",
     "REVIEW8 #1"),
    ("r8-bash-sq-assembled-continuation", "bash -c 'po\\'\"\n\"'ol " + _R13_ARGS + "'", "zsh bash",
     "REVIEW8 #1"),
    ("r8-sh-sq-assembled-continuation", "sh -c 'po\\'\"\n\"'ol " + _R13_ARGS + "'", "zsh bash",
     "REVIEW8 #1"),
    ("r8-bash-dq-assembled-sub-sh", 'bash -c "su\\\\"\'\n\'"b.sh glm-memory a"', "zsh bash", "REVIEW8 #1"),
]


def test_r13_sealed_shells_run_each_escape(tmp_path: Path) -> None:
    """Ground truth for _R13_ESCAPES: each EXECUTES a fake wrapper in BOTH
    sealed shells (the nested interpreter resolves from /usr/bin:/bin)."""
    run = _r11_sealed_shells(tmp_path)
    checked = 0
    for row_id, command, shells, _origin in _R13_ESCAPES:
        for shell_name in shells.split():
            markers = run(command, shell_name)
            assert markers, (row_id, shell_name, command)
            checked += 1
    assert checked == 2 * len(_R13_ESCAPES) == 12


@pytest.mark.parametrize("row", _R13_ESCAPES, ids=[row[0] for row in _R13_ESCAPES])
def test_r13_escape_is_invisible_to_the_raw_scan_and_the_r12_literal_view(row: tuple) -> None:
    """Fail-before, pinned: the raw construct regex finds nothing and the
    r12 quote-joined view (backslash deleted, newline kept) reads two words;
    r13's quote-deleted view shows the continuation and joins the name."""
    command = row[1]
    assert guard._R12_CONSTRUCT_RE.search(command) is None, command
    assert not guard._WRAPPER_NAME_RE.search(guard._r9_joined(command)), command
    assert "\\\n" in guard._r12_unquoted_view(command)
    assert guard.r12_constructs(command) == [guard._R13_ASSEMBLED_CONTINUATION], command
    assert guard.r12_literal_names_wrapper(command), command
    assert guard.r12_armed_in_scope(command)


def _r13_honest_spelling(row: tuple) -> str:
    """The same nested launch written plainly (``bash -c 'pool run …'``)."""
    interpreter = row[1].split(" ", 1)[0]
    body = "sub.sh glm-memory a" if "sub-sh" in row[0] else "pool " + _R13_ARGS
    return interpreter + " -c '" + body + "'"


@pytest.mark.parametrize("row", _R13_ESCAPES, ids=[row[0] for row in _R13_ESCAPES])
def test_r13_escapes_reach_the_gate_exactly_like_the_honest_spelling(
    shared_placement: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    row: tuple,
) -> None:
    """Armed, bound and unbound, with and without the scanner: DENY. The
    ``bash``/``sh -c`` rows are in scope (r13) and parse to one bare nested
    launch that REACHES the binding gate, where the cross-check refuses the
    launch the text cannot attribute (``unaccounted descendant``) or the
    binding is missing; the ``zsh -c`` row is refused structurally (not an
    admitted nested interpreter). r12 allowed every row with the gate
    unreached (REVIEW8 #1). The honest spelling is judged like any launch."""
    command = row[1]
    honest = _r7_both(guard, shared_placement, monkeypatch, tmp_path, capsys, _r13_honest_spelling(row))
    with_scanner = _r7_both(guard, shared_placement, monkeypatch, tmp_path, capsys, command)
    _r12_scanner_off(monkeypatch)
    without = _r7_both(guard, shared_placement, monkeypatch, tmp_path, capsys, command)
    assert with_scanner == without
    (bound, bound_reason, bound_gate), (nobind, nobind_reason, nobind_gate) = without
    assert (bound, nobind) == ("deny", "deny"), (bound_reason, nobind_reason)
    if row[1].startswith("zsh "):
        assert (bound_gate, nobind_gate) == (False, False)
        for reason in (bound_reason, nobind_reason):
            assert "R12_SHELL_CONSTRUCT" in reason and "R6_NESTED_SHELL" in reason, reason
            assert "assembled by quote removal" in reason, reason
        assert honest[0][0] == honest[1][0] == "deny" and "R6_NESTED_SHELL" in honest[0][1]
    else:
        assert bound_gate and "unaccounted descendant" in bound_reason, bound_reason
        assert nobind_gate and ("missing binding" in nobind_reason or "unaccounted descendant" in nobind_reason)
        assert honest[0][2] and honest[1][2], honest  # judged through the gate
        if "sub-sh" not in row[0]:
            assert honest[0][0] == "allow", honest[0][1]
        assert honest[1][0] == "deny" and "missing binding" in honest[1][1]


@pytest.mark.parametrize("row_id", ["r8-bash-dq-assembled-continuation", "r8-bash-sq-assembled-continuation"])
@pytest.mark.parametrize("bound", [True, False], ids=["bound", "unbound"])
def test_r13_rows_through_the_real_hook_command_line(tmp_path: Path, row_id: str, bound: bool) -> None:
    """Through the registered hook command line: the assembled row is DENIED
    bound and unbound (r12: ALLOW, gate unreached — REVIEW8 #1); the honest
    spelling is judged like any launch (bound ALLOW, unbound missing binding)."""
    row = next(row for row in _R13_ESCAPES if row[0] == row_id)
    elapsed, code, out = _r8_hook_cli(tmp_path, row[1], bound=bound, owner=bound)
    assert code == 0 and out, out
    decision = json.loads(out)["hookSpecificOutput"]
    assert decision["permissionDecision"] == "deny", out[:300]
    assert ("unaccounted descendant" in decision["permissionDecisionReason"]
            or "missing binding" in decision["permissionDecisionReason"])
    assert elapsed < 4.0, elapsed
    elapsed, code, out = _r8_hook_cli(tmp_path, _r13_honest_spelling(row), bound=bound, owner=bound)
    assert code == 0, out
    if bound:
        assert out == "", out[:300]
    else:
        assert "missing binding" in json.loads(out)["hookSpecificOutput"]["permissionDecisionReason"]


#: Honest controls with backslashes and newlines inside quotes: no assembled
#: continuation (the backslash is not immediately before a newline on the
#: quote-deleted view), construct-free, armed ALLOW both, gate unreached.
_R13_HONEST_CONTROLS = [
    "git commit -m 'line1\nline2'",
    'python3 script.py --flag "a\nb"',
    "printf 'a\\nb' > /dev/null",
    "echo 'back\\slash' > /dev/null",
    'echo "tab\\there" > /dev/null',
    "git commit -m 'trailing backslash \\\\ kept'",
    "echo 'C:\\path\\to\\file'",
]


@pytest.mark.parametrize("command", _R13_HONEST_CONTROLS)
def test_r13_quoted_backslashes_and_newlines_stay_out_of_scope(
    shared_placement: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    command: str,
) -> None:
    assert guard.r12_constructs(command) == [], command
    assert not guard.r12_armed_in_scope(command), command
    (bound, bound_reason, bound_gate), (nobind, nobind_reason, nobind_gate) = _r7_both(
        guard, shared_placement, monkeypatch, tmp_path, capsys, command
    )
    assert (bound, nobind, bound_gate, nobind_gate) == ("allow", "allow", False, False), (
        bound_reason, nobind_reason
    )


def test_r13_accepted_over_refusal_backslash_before_a_newline_in_quotes(
    shared_placement: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """PINS AN ACCEPTED OVER-REFUSAL: a quoted backslash immediately before a
    newline is read as an assembled continuation (the view cannot know which
    quote removal a nested interpreter will see), so the two-line command is
    judged and refused as a compound list. Rewrite it on one line."""
    command = "echo 'a\\'\necho b"
    assert guard.r12_constructs(command) == [guard._R13_ASSEMBLED_CONTINUATION]
    (bound, reason, gate), (nobind, _, _) = _r7_both(
        guard, shared_placement, monkeypatch, tmp_path, capsys, command
    )
    assert (bound, nobind, gate) == ("deny", "deny", False), reason
    assert "R12_SHELL_CONSTRUCT" in reason


def test_r13_slot_module_flag_combined_forms_are_literal_names() -> None:
    """REVIEW8 #2 (MINOR): ``python3 -B -m slot`` spelt ``-Bmslot`` is the
    same module name; the plain forms still read, the near-misses still do
    not."""
    for text in ("python3 -Bmslot glm -- run", "python3 -sBmslot glm", "python3 -umslot x",
                 "python3 -OOmslot x", "python3 -Imslot x", "python3 -qmslot x",
                 "python3 -m slot glm -- run", "python3 -mslot glm", "python3 -m pkg.slot x"):
        assert guard.r12_literal_names_wrapper(text), text
    for text in ("timeslot", "--timeslot", "python3 -m pytest", "slots", "slot_id", "python3 -B x"):
        assert not guard.r12_literal_names_wrapper(text), text


def test_r13_slot_module_flag_combined_is_in_scope_armed(
    shared_placement: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    command = "python3 -Bmslot glm -- run"
    assert guard.r12_armed_in_scope(command)
    for verdict, reason, gate in _r7_both(guard, shared_placement, monkeypatch, tmp_path, capsys, command):
        assert (verdict, gate) == ("deny", False), reason


def test_r13_unquoted_view_is_linear() -> None:
    import time as _time

    for unit in ('"a\\\\"\'\n\'', "x\\\n", "'\\'\n", 'ab"c"'):
        text = (unit * (_R8_CAP // len(unit) + 1))[:_R8_CAP]
        started = _time.perf_counter()
        guard.r12_constructs(text)
        guard.r12_literal_names_wrapper(text)
        assert _time.perf_counter() - started < 1.0, unit
