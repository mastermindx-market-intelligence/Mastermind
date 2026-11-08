from __future__ import annotations

import json
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
    for name in (
        "POOL_EXECUTION_BINDING",
        "MASTERMIND_PLACEMENT_RECEIPT",
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
