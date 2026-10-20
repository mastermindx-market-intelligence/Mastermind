"""Hermetic regression checks for the existing-hook Parall account isolation rollout."""
from __future__ import annotations

import ast
import contextlib
import io
import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts import install_claude_parall_isolation as rollout

BASELINE = (
    rollout.ROOT /
    "research/execution_friction_20261011/fixtures/installed_routing_guard.py"
)


def legacy_source():
    return BASELINE.read_text(encoding="utf-8")


def fixture_home(tmp_path):
    home = tmp_path / "home"
    files = {
        "guard": legacy_source(),
        "codex": "Before\n" + rollout.DOC_ANCHORS["codex"] + "\nAfter\n",
        "claude": "Before\n" + rollout.DOC_ANCHORS["claude"] + "\nAfter\n",
    }
    for kind, content in files.items():
        dest = home / rollout.TARGETS[kind]
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content, encoding="utf-8")
        dest.chmod(0o640)
    return home


def test_known_legacy_guard_installs_and_is_idempotent():
    source = legacy_source()
    with patch.object(rollout, "KNOWN_PRE_ISOLATION_GUARD_SHA256",
                      rollout.sha(source.encode())):
        installed = rollout.render("guard", source)
        assert installed != source
        ast.parse(installed)
        assert rollout.render("guard", installed) == installed
        assert installed.count("unmanaged_desktop") >= 2


@pytest.mark.parametrize("command,denied", [
    ("open -a Claude", True),
    ("open -b com.anthropic.claudefordesktop", True),
    ("open claude://open/session", True),
    ("claude --desktop --resume session-id", True),
    ("open /Applications/Claude Default.app", True),
    ("claude -p 'analyze supplied snippet'", False),
    ("claude --resume native-session-id", False),
    ("claude --version", False),
    ("open -a '/Applications/Claude 6.app'", False),
    ("bash -lc 'open -a Claude'", True),
    ("env CLAUDE_TEST=1 claude --desktop --resume id", True),
    ('osascript -e \'tell application "Claude" to activate\'', True),
    ('claude -p "Explain the --desktop flag"', False),
    ('claude -p "Why does open -a Claude break Parall?"', False),
    ('echo "open -a Claude"', False),
    ('git commit -m "explain claude --desktop behavior"', False),
])
def test_installed_hook_respects_cli_desktop_boundary(command, denied):
    source = legacy_source()
    with patch.object(rollout, "KNOWN_PRE_ISOLATION_GUARD_SHA256",
                      rollout.sha(source.encode())):
        code = rollout.render("guard", source)
    namespace = {"__name__": "guard_fixture"}
    exec(compile(code, "guard_fixture.py", "exec"), namespace)
    payload = {
        "cwd": "/Volumes/Mastermind 2/agent-workspaces/sol/test",
        "tool_name": "Bash",
        "tool_input": {"command": command},
    }
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        try:
            namespace["guard_bash"](payload, payload["tool_input"])
        except SystemExit as exit_info:
            assert exit_info.code == 0
    observed = bool(output.getvalue()) and (
        json.loads(output.getvalue())["hookSpecificOutput"].get("permissionDecision") == "deny"
    )
    assert observed is denied


def test_all_three_targets_installed_with_backups_and_idempotent(tmp_path):
    home = fixture_home(tmp_path)
    source = legacy_source()
    with patch.object(rollout, "KNOWN_PRE_ISOLATION_GUARD_SHA256",
                      rollout.sha(source.encode())):
        plan = rollout.prepare(home)
        assert len(plan) == 3 and all(x["before"] != x["after"] for x in plan)
        evidence = tmp_path / "proof"
        result = rollout.apply(plan, evidence)
        assert result["status"] == "INSTALLED"
        assert len(result["written"]) == 3
        for item in plan:
            assert item["path"].read_bytes() == item["after"]
            assert (evidence / (item["kind"] + ".before")).read_bytes() == item["before"]
            assert (item["path"].stat().st_mode & 0o777) == 0o640
        again = rollout.prepare(home)
        assert all(p["after"] == p["before"] for p in again)


def test_unrecognized_guard_and_instruction_drift_refused(tmp_path):
    home = fixture_home(tmp_path)
    guard_path = home / rollout.TARGETS["guard"]
    guard_path.write_text("print('foreign guard')\n", encoding="utf-8")
    before = guard_path.read_bytes()
    with pytest.raises(ValueError, match="unrecognized guard"):
        rollout.prepare(home)
    assert guard_path.read_bytes() == before
    doc = "hello\n" + rollout.DOC_MARKER + "\n" + rollout.DOC_ANCHORS["codex"]
    with pytest.raises(ValueError, match="drift"):
        rollout.render("codex", doc)


def test_concurrent_target_change_blocks_effects(tmp_path):
    home = fixture_home(tmp_path)
    source = legacy_source()
    with patch.object(rollout, "KNOWN_PRE_ISOLATION_GUARD_SHA256",
                      rollout.sha(source.encode())):
        plan = rollout.prepare(home)
        changed = plan[-1]["path"]
        changed.write_text("different owner wrote here", encoding="utf-8")
        evidence = tmp_path / "not-created"
        with pytest.raises(ValueError, match="changed after preflight"):
            rollout.apply(plan, evidence)
        assert not evidence.exists()


def test_exact_previous_guard_block_migrates_once_without_other_edits():
    source = legacy_source()
    before_fragment = (
        rollout.GUARD_START + " the shared Anthropic application identity.\n"
        + "    # previously installed body\n"
    )
    assert source.count(rollout.GUARD_ANCHOR) == 1
    old = source.replace(
        rollout.GUARD_ANCHOR,
        before_fragment + rollout.GUARD_ANCHOR, 1,
    )
    with patch.object(
        rollout, "KNOWN_INSTALLED_V1_BLOCK_SHA256",
        rollout.sha(before_fragment.encode()),
    ):
        updated = rollout.render("guard", old)
        assert before_fragment not in updated
        assert rollout.template("guard") in updated
        assert rollout.render("guard", updated) == updated


def test_unknown_previous_guard_block_refuses_before_write():
    source = legacy_source()
    fragment = rollout.GUARD_START + " unknown edit\n"
    old = source.replace(
        rollout.GUARD_ANCHOR, fragment + rollout.GUARD_ANCHOR, 1
    )
    with pytest.raises(ValueError, match="unrecognized guard block"):
        rollout.render("guard", old)
