"""Exact-source tests for the incumbent provider-policy amendment.

All installations below use disposable homes. No provider request or live hook
installation occurs; metadata and role text are not admission authority.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/native_provider_role_reserve"
PATCH_ROOT = ROOT / "ops/native_fabric/patches"
MANIFEST = PATCH_ROOT / "provider_role_reserve.json"


def _hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def candidate(tmp_path):
    manifest = json.loads(MANIFEST.read_text())
    target = tmp_path / "candidate" / "ops" / "executive_os"
    target.mkdir(parents=True)
    for row in manifest["files"]:
        data = (FIXTURE / (Path(row["path"]).name + ".txt")).read_bytes()
        assert _hash(data) == row["before_sha256"]
        (target / Path(row["path"]).name).write_bytes(data)
    patch = (PATCH_ROOT / manifest["patch"]).read_bytes()
    if patch:
        result = subprocess.run(
            ["patch", "--batch", "--forward", "-p1"],
            input=patch, cwd=tmp_path / "candidate", capture_output=True,
            timeout=10, check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr
    for row in manifest["files"]:
        assert _hash((target / Path(row["path"]).name).read_bytes()) == row["after_sha256"]
    return (
        _load(target / "provider_orchestrator_policy.py", "role_reserve_policy"),
        _load(target / "provider_orchestrator_guard.py", "role_reserve_guard"),
        target,
    )


def _native_prompt() -> str:
    return (
        "ROUTE: ORCHESTRATION\n"
        "WHY OPUS: Resolve the admitted subsystem integration decision.\n"
        "MODE: READ_ONLY\n"
    )


@pytest.mark.parametrize("model", [
    "not-opus", "opus-sonnet", "sonnet-opus", "opus_fake", "gpt-6-sol-opus",
    "claude-opus-5-5-extra", "unapproved/opus", "opus\nignored", "xopusx",
])
def test_substring_must_not_admit_an_unknown_native_model(candidate, capsys, model):
    _, guard, _ = candidate
    with pytest.raises(SystemExit):
        guard.guard_native_child({"model": model, "prompt": _native_prompt()})
    reply = json.loads(capsys.readouterr().out)["hookSpecificOutput"]
    assert reply["permissionDecision"] == "deny"


@pytest.mark.parametrize("model", [
    "opus", "Opus", "claude-opus-5-5", "claude-opus-5.5", "claude-opus-4-6-20260201",
])
def test_exact_native_opus_aliases_retain_existing_exception(candidate, capsys, model):
    _, guard, _ = candidate
    assert guard.guard_native_child({"model": model, "prompt": _native_prompt()}) is None
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize("model", [
    "sonnet", "haiku", "fable", "terra", "luna", "", "claude-sonnet-5-5",
    "claude-haiku-4-5-20251001", "gpt-5.6-terra", "gpt-6-luna",
])
def test_native_cheap_models_and_second_fable_remain_blocked(candidate, capsys, model):
    _, guard, _ = candidate
    with pytest.raises(SystemExit):
        guard.guard_native_child({"model": model, "prompt": _native_prompt()})
    reply = json.loads(capsys.readouterr().out)["hookSpecificOutput"]
    assert reply["permissionDecision"] == "deny"


@pytest.mark.parametrize("required", [
    "MODEL_DUTY_POLICY: role-reserve-v1-20261005",
    "Sol 6.1 or qualified Opus 5.5",
    "Grok, full GLM 5.3, Opus, or Sol",
    "Astra and Fable",
    "Sonnet and Terra are excluded",
    "Codex/Claude subscription allowances",
    "Luna or Haiku",
    "not the CLI executable",
    "Expiry preference never overrides",
    "human Chairman remains",
    "No model is infallible",
])
def test_canonical_installer_carries_current_role_and_reserve_policy(candidate, required):
    policy, _, _ = candidate
    assert required in policy.POLICY_BODY


def test_existing_native_guards_and_source_authority_are_preserved(candidate):
    policy, guard, _ = candidate
    assert "Every descendant preserves the original root identity" in policy.POLICY_BODY
    assert "independent review" in policy.POLICY_BODY
    assert "current protected task-complexity/routing law" in policy.POLICY_BODY
    assert "creates no lifecycle" in policy.POLICY_BODY
    assert guard.MIN_WATCH_INTERVAL_S == 60
    assert guard.POLL_COOLDOWN_S == 300
    assert guard._FABRIC_IDENTITY_NAMES == (
        "POOL_ORCHESTRATOR_ID", "POOL_PARENT_RUN_ID", "POOL_TASK_CLASS",
    )


def test_installer_propagates_policy_into_both_disposable_homes(candidate, tmp_path):
    policy, _, target = candidate
    home = tmp_path / "home"
    (home / ".codex").mkdir(parents=True)
    (home / ".claude").mkdir()
    (home / ".codex/AGENTS.md").write_text("# Unrelated Codex note\n")
    (home / ".codex/config.toml").write_text('model = "gpt-6.1-sol"\n')
    (home / ".claude/CLAUDE.md").write_text("# Unrelated Claude note\n")
    (home / ".claude/settings.json").write_text('{"model":"opus"}\n')
    guard_source = target / "provider_orchestrator_guard.py"
    policy.apply_policy(home, guard_source=guard_source)
    first = {}
    for relative in [".codex/AGENTS.md", ".claude/CLAUDE.md"]:
        text = (home / relative).read_text()
        assert "Unrelated" in text
        assert text.count("MODEL_DUTY_POLICY: role-reserve-v1-20261005") == 1
        assert "Sonnet and Terra are excluded" in text
        first[relative] = text
    policy.apply_policy(home, guard_source=guard_source)
    for relative, text in first.items():
        assert (home / relative).read_text() == text
    assert 'model = "gpt-6.1-sol"' in (home / ".codex/config.toml").read_text()
    assert json.loads((home / ".claude/settings.json").read_text())["model"] == "opus"
    assert policy.verify_policy(home, guard_source=guard_source)["state"] == "READY"


@pytest.mark.parametrize("command", [
    'pool run cursor "bounded task" /tmp claude-sonnet-5-5',
    'pool run go-codex "bounded task" /tmp gpt-5.6-terra',
    'pool remote mini4 cursor packet.json /tmp gpt-5.6-terra',
    'env SAFE=1 pool run cursor "task" /tmp sonnet',
    '/usr/local/bin/cursor-agent --model=claude-sonnet-5-5 -p "task"',
    'agent --model gpt-5.6-terra -p "task"',
    'command claude --model sonnet -p "task"',
    'exec codex exec -m gpt-5.6-terra "task"',
    'codex exec -c model=gpt-5.6-terra "task"',
    'sub.sh cursor "task" /tmp sonnet',
    'remote_sub.sh mini4 go-claude packet.json /tmp claude-sonnet-5-5',
    'printf done; cursor-agent --model sonnet -p "task"',
    'printf done\ncursor-agent --model sonnet -p "task"',
])
def test_explicit_sonnet_terra_launch_is_denied_before_other_checks(candidate, monkeypatch, capsys, command):
    _, guard, _ = candidate
    monkeypatch.setattr(guard, "is_project_scope", lambda payload: True)
    for name, value in [("POOL_ORCHESTRATOR_ID", "root-1"), ("POOL_PARENT_RUN_ID", "parent-1"), ("POOL_TASK_CLASS", "routine")]:
        monkeypatch.setenv(name, value)
    with pytest.raises(SystemExit):
        guard.guard_bash({}, {"command": command})
    reply = json.loads(capsys.readouterr().out)["hookSpecificOutput"]
    assert reply["permissionDecision"] == "deny"
    assert "model-exclusion" in reply["permissionDecisionReason"]


@pytest.mark.parametrize("command", [
    'codex exec -m gpt-6-luna "task"',
    'claude --model haiku -p "task"',
    'env SAFE=1 claude --model=claude-haiku-4-5-20251001 -p "task"',
    'codex exec --model "$MODEL" "task"',
    'cursor-agent --model "$MODEL" -p "task"',
    'pool run cursor "task" /tmp "$MODEL"',
    'pool run cursor "task" /tmp',
])
def test_cheap_native_or_unresolved_multimodel_launch_is_held(candidate, monkeypatch, capsys, command):
    _, guard, _ = candidate
    monkeypatch.setattr(guard, "is_project_scope", lambda payload: True)
    for name, value in [("POOL_ORCHESTRATOR_ID", "root-1"), ("POOL_PARENT_RUN_ID", "parent-1"), ("POOL_TASK_CLASS", "routine")]:
        monkeypatch.setenv(name, value)
    with pytest.raises(SystemExit):
        guard.guard_bash({}, {"command": command})
    reply = json.loads(capsys.readouterr().out)["hookSpecificOutput"]
    assert reply["permissionDecision"] == "deny"
    assert "reserve" in reply["permissionDecisionReason"]


@pytest.mark.parametrize("command", [
    'pool run go-codex "task" /tmp gpt-6-luna',
    'pool run go-claude "task" /tmp haiku',
    'pool run glm "task" /tmp',
    'pool run minimax "task" /tmp MiniMax-M3',
    'pool run cursor "hard task" /tmp grok-4.7',
    'claude --model opus -p "orchestrate"',
    'codex exec -m gpt-6.1-sol "orchestrate"',
    'printf "%s" "claude --model sonnet -p example"',
    'echo "Sonnet and Terra are excluded"',
    'codex --help',
    'claude --model sonnet --help',
])
def test_nonbanned_literal_launch_or_documentation_is_not_newly_denied(candidate, monkeypatch, capsys, command):
    _, guard, _ = candidate
    monkeypatch.setattr(guard, "is_project_scope", lambda payload: True)
    for name, value in [("POOL_ORCHESTRATOR_ID", "root-1"), ("POOL_PARENT_RUN_ID", "parent-1"), ("POOL_TASK_CLASS", "routine")]:
        monkeypatch.setenv(name, value)
    assert guard.guard_bash({}, {"command": command}) is None
    assert capsys.readouterr().out == ""
    # No new allow/permission receipt is issued. Funding and admission remain
    # with the existing owners; a pass is not proof an external offer is funded.


def test_same_model_checks_do_not_widen_native_hook_scope(candidate, monkeypatch, capsys):
    _, guard, _ = candidate
    monkeypatch.setattr(guard, "is_project_scope", lambda payload: False)
    assert guard.guard_bash({}, {"command": 'claude --model sonnet -p "task"'}) is None
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize("command", [
    'codex exec -m gpt-6.1-sol -- "--model=sonnet"',
    'pool remote mini4 cursor packet.json /tmp --dry-run',
])
def test_literal_prompt_or_remote_dry_run_is_not_model_inference(candidate, monkeypatch, capsys, command):
    _, guard, _ = candidate
    monkeypatch.setattr(guard, "is_project_scope", lambda payload: True)
    for name, value in [("POOL_ORCHESTRATOR_ID", "root-1"), ("POOL_PARENT_RUN_ID", "parent-1"), ("POOL_TASK_CLASS", "routine")]:
        monkeypatch.setenv(name, value)
    assert guard.guard_bash({}, {"command": command}) is None
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize("model", ["sonnet", "gpt-5.6-terra"])
def test_actual_hook_entrypoint_returns_deny_for_banned_literal_model(candidate, tmp_path, model):
    import os
    import sys

    _, _, target = candidate
    env = dict(os.environ)
    env.update({
        "HOME": str(tmp_path), "MASTERMIND_SCOPE_ROOTS": str(tmp_path),
        "POOL_ORCHESTRATOR_ID": "root-1", "POOL_PARENT_RUN_ID": "parent-1",
        "POOL_TASK_CLASS": "routine", "PYTHONDONTWRITEBYTECODE": "1",
    })
    payload = {"tool_name": "Bash", "cwd": str(tmp_path), "tool_input": {
        "command": f'pool run cursor "bounded task" /tmp {model}',
    }}
    result = subprocess.run(
        [sys.executable, str(target / "provider_orchestrator_guard.py")],
        input=json.dumps(payload), text=True, capture_output=True, env=env,
        cwd=tmp_path, check=False, timeout=10,
    )
    assert result.returncode == 0
    assert json.loads(result.stdout)["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert result.stderr == ""


def test_patch_preserves_existing_installer_and_lifecycle_function_bodies(candidate):
    import ast

    _, _, target = candidate
    for name in ("provider_orchestrator_policy.py", "provider_orchestrator_guard.py"):
        original = (FIXTURE / (name + ".txt")).read_text()
        updated = (target / name).read_text()
        if name.endswith("guard.py"):
            updated = updated.replace("    guard_selected_model_launches(clean)\n", "")
        before = {node.name: ast.dump(node) for node in ast.parse(original).body if isinstance(node, (ast.FunctionDef, ast.ClassDef))}
        after = {node.name: ast.dump(node) for node in ast.parse(updated).body if isinstance(node, (ast.FunctionDef, ast.ClassDef))}
        for key, value in before.items():
            if key != "family":
                assert after[key] == value, key
        added = set(after) - set(before)
        assert added == ({"_literal_launches", "guard_selected_model_launches"} if name.endswith("guard.py") else set())
