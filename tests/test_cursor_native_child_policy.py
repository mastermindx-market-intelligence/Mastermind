"""Bounded Cursor/Claude hook compatibility tests, entirely offline."""
from __future__ import annotations

import io
import json
from pathlib import Path
import subprocess
import sys

import pytest

from integrations.cursor_agent_mastermind import install
from ops.executive_os import cursor_native_child_policy as cursor_policy
from ops.executive_os import provider_orchestrator_guard as guard


@pytest.fixture
def cursor_project(tmp_path: Path):
    w = tmp_path / "repo"
    w.mkdir()
    subprocess.run(["git", "init", "-q", str(w)], check=True)
    install.project(w, "apply")
    payload = {
        "hook_event_name": "preToolUse",
        "tool_name": "Task",
        "cursor_version": "3.25.9",
        "model": "composer-2.5",  # Cursor's PARENT model, never a child model proof.
        "cwd": str(w),
        "workspace_roots": [str(w)],
        "tool_input": {
            "subagent_type": "mmx-repo-explorer",
            "prompt": "Read fixture.txt in read-only mode",
            "description": "Inspect fixture",
            "run_in_background": False,
        },
    }
    env = {"CURSOR_VERSION": "3.25.9", "CURSOR_PROJECT_DIR": str(w)}
    return w, payload, env


def test_exact_readonly_cursor_helper_is_eligible(cursor_project) -> None:
    w, payload, env = cursor_project
    result = cursor_policy.evaluate_cursor_task(payload, env)
    assert result.admitted is True
    assert result.declared_model == "gemini-3.7-flash-high"
    assert result.code == "READ_ONLY_CURSOR_HELPER_DECLARED"
    payload["tool_input"]["subagent_type"] = "mmx-independent-reviewer"
    assert cursor_policy.evaluate_cursor_task(payload, env).declared_model == "grok-4.7-medium"


@pytest.mark.parametrize("delta,code", [
    ({"subagent_type": "mmx-implementation-worker"}, "CURSOR_TASK_ROLE_NOT_ADMITTED"),
    ({"subagent_type": "mmx-fabric-operator"}, "CURSOR_TASK_ROLE_NOT_ADMITTED"),
    ({"subagent_type": "explore"}, "CURSOR_TASK_ROLE_NOT_ADMITTED"),
    ({"run_in_background": True}, "CURSOR_BACKGROUND_NOT_ADMITTED"),
    ({"model": "claude-fable-5"}, "CURSOR_TASK_ARGS_UNVERIFIED"),
    ({"prompt": ""}, "CURSOR_TASK_PROMPT_INVALID"),
])
def test_dangerous_or_unverified_task_args_fail_closed(cursor_project, delta, code) -> None:
    w, payload, env = cursor_project
    payload["tool_input"].update(delta)
    result = cursor_policy.evaluate_cursor_task(payload, env)
    assert not result.admitted and result.code == code


def test_runtime_origin_and_workspace_are_not_model_claims(cursor_project) -> None:
    w, payload, env = cursor_project
    assert cursor_policy.evaluate_cursor_task(payload, {}).code == "CURSOR_RUNTIME_UNVERIFIED"
    env["CURSOR_PROJECT_DIR"] = str(w.parent)
    assert cursor_policy.evaluate_cursor_task(payload, env).code == "CURSOR_ROOT_BINDING_MISMATCH"
    env["CURSOR_PROJECT_DIR"] = str(w)
    payload["workspace_roots"] = [str(w.parent)]
    assert cursor_policy.evaluate_cursor_task(payload, env).code == "CURSOR_ROOT_BINDING_MISMATCH"
    payload.pop("cursor_version")
    assert cursor_policy.evaluate_cursor_task(payload, env).code == "CURSOR_RUNTIME_UNVERIFIED"


def test_project_local_role_tampering_and_symlink_are_refused(cursor_project) -> None:
    w, payload, env = cursor_project
    p = w / ".cursor/agents/mmx-repo-explorer.md"
    p.write_text(p.read_text() + "\nmodel: claude-fable-5\n")
    assert cursor_policy.evaluate_cursor_task(payload, env).code == "CURSOR_ROLE_DIGEST_MISMATCH"
    p.unlink()
    p.symlink_to(w / "fixture.txt")
    assert cursor_policy.evaluate_cursor_task(payload, env).code == "CURSOR_ROLE_SOURCE_UNTRUSTED"


def test_symlinked_cursor_agent_directory_refused(cursor_project) -> None:
    w, payload, env = cursor_project
    p = w / ".cursor/agents"
    backup = w / "agent-copy"
    p.rename(backup)
    p.symlink_to(backup)
    assert cursor_policy.evaluate_cursor_task(payload, env).code == "CURSOR_ROLE_SOURCE_UNTRUSTED"


def test_existing_guard_distinguishes_cursor_and_claude(cursor_project, monkeypatch, capsys) -> None:
    w, payload, env = cursor_project
    monkeypatch.setenv("MASTERMIND_SCOPE_ROOTS", str(w))
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
    with pytest.raises(SystemExit) as e:
        guard.main()
    assert e.value.code == 0
    output = json.loads(capsys.readouterr().out)
    assert "read-only Cursor role declaration" in output["hookSpecificOutput"]["additionalContext"]
    assert "UNVERIFIED" in output["hookSpecificOutput"]["additionalContext"]

    monkeypatch.delenv("CURSOR_VERSION")
    monkeypatch.delenv("CURSOR_PROJECT_DIR")
    payload.pop("cursor_version")
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
    with pytest.raises(SystemExit) as e:
        guard.main()
    assert e.value.code == 0
    denied = json.loads(capsys.readouterr().out)
    assert denied["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "native Claude children" in denied["hookSpecificOutput"]["permissionDecisionReason"]
