from __future__ import annotations

import json
from pathlib import Path

import pytest

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
    assert any(
        row.get("matcher") == "Write"
        for row in claude["hooks"]["PreToolUse"]
    )
    assert any(
        row.get("matcher") == "Agent|Task|Bash"
        for row in claude["hooks"]["PreToolUse"]
    )

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
        "claude_doc": (home / ".claude" / "CLAUDE.md").read_bytes(),
        "codex_hooks": (home / ".codex" / "hooks.json").read_bytes(),
        "claude_settings": (home / ".claude" / "settings.json").read_bytes(),
    }

    first = apply_policy(home)
    first_bytes = {
        path: path.read_bytes()
        for path in (
            home / ".codex" / "AGENTS.md",
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
        home / ".claude" / "CLAUDE.md.mastermind-orchestrator-backup"
    ).read_bytes() == originals["claude_doc"]
    assert (
        home / ".codex" / "hooks.json.mastermind-orchestrator-backup"
    ).read_bytes() == originals["codex_hooks"]
    assert (
        home / ".claude" / "settings.json.mastermind-orchestrator-backup"
    ).read_bytes() == originals["claude_settings"]


def test_apply_handles_prose_only_host_with_missing_codex_hooks(tmp_path: Path) -> None:
    """M1/mini4/MBP class: instructions exist but mechanical hooks are absent."""
    home = tmp_path / "home"
    (home / ".codex").mkdir(parents=True)
    (home / ".claude").mkdir(parents=True)
    legacy = """<!-- mastermind-ceo-async-ci-v1 -->
old async law
<!-- /mastermind-ceo-async-ci-v1 -->
<!-- mastermind-ceo-context-discipline-v1 -->
old context law
<!-- /mastermind-ceo-context-discipline-v1 -->
"""
    (home / ".codex" / "AGENTS.md").write_text(
        "# Storage rule\n\nKeep external SSD placement.\n\n" + legacy,
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

    result = apply_policy(home)

    assert result["state"] == "READY"
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
        assert text.count(BEGIN) == text.count(END) == 1


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


def _payload(cwd: Path, command: str, *, background: bool = False) -> dict[str, object]:
    return {
        "cwd": str(cwd),
        "tool_name": "Bash",
        "tool_input": {
            "command": command,
            **({"run_in_background": True} if background else {}),
        },
    }


def _emitted(capsys: pytest.CaptureFixture[str]) -> dict[str, object]:
    raw = capsys.readouterr().out.strip()
    assert raw
    return json.loads(raw)["hookSpecificOutput"]


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
