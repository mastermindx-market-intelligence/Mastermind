"""Hermetic regression checks for the existing-hook Parall account isolation rollout."""
from __future__ import annotations

import ast
import contextlib
import io
import json
import os
from pathlib import Path

import pytest

from scripts import install_claude_parall_isolation as rollout

BASELINE = (
    rollout.ROOT /
    "tests/fixtures/claude_parall_isolation/installed_guard_pre_isolation.py"
)
V1_BLOCK = rollout.ROOT / "tests/fixtures/claude_parall_isolation/installed_guard_block_v1.txt"
V2_BLOCK = rollout.ROOT / "tests/fixtures/claude_parall_isolation/installed_guard_before_review.txt"
V3_BLOCK = rollout.ROOT / "tests/fixtures/claude_parall_isolation/installed_guard_v3.txt"
V4_BLOCK = rollout.ROOT / "tests/fixtures/claude_parall_isolation/installed_guard_v4.txt"


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
    ("open -a claude", True),
    ("open -a CLAUDE", True),
    ("open -a " + chr(92) + chr(10) + "Claude", True),
    ("open -a C" + chr(92) + chr(10) + "laude", True),
    ('claude -p "Explain open -a ' + chr(92) + chr(10) + 'Claude"', False),
    ('osascript -e \'tell application "Claude Default" to activate\'', True),
    ('osascript -e \'tell application "Claude Official" to activate\'', True),
    ('osascript -e \'tell application "Claude 6" to activate\'', False),
    ("open CLAUDE://open/session", True),
    ("open -b COM.ANTHROPIC.CLAUDEFORDESKTOP", True),
    ('open -a "claude default"', True),
    ('open -a "Claude 6"', False),
    ('claude -p "Explain CLAUDE:// in text"', False),
    ("env - open -a Claude", True),
    ("command -p open -a Claude", True),
    ("exec -a harmless open -a Claude", True),
    ("nice -10 open -a Claude", True),
    ("time open -a Claude", True),
    ("caffeinate -i open -a Claude", True),
    ("caffeinate -t 30 -i open -a Claude", True),
    ("env - claude --resume native-session-id", False),
    ('command -p claude -p "Review this text"', False),
    ('nice -10 claude -p "Why open -a Claude breaks accounts"', False),
    ("time claude --resume native-session-id", False),
    ('caffeinate -i claude -p "Explain --desktop"', False),
    ("env -i open -a Claude", True),
    ("env -u PATH open -a Claude", True),
    ("env --ignore-environment open -a Claude", True),
    ("env --unset=HOME open -a Claude", True),
    ('env -S "open -a Claude"', True),
    ("sudo -n open -a Claude", True),
    ("sudo -u build -- open -a Claude", True),
    ("sudo -n env -i claude --desktop --resume session-id", True),
    ("nohup open -a Claude", True),
    ("command open -a Claude", True),
    ("exec open -a Claude", True),
    ("nice -n 10 open -a Claude", True),
    ('bash -lc "bash -lc \'open -a Claude\'"', True),
    ('zsh -c \'env -i open -b com.anthropic.claudefordesktop\'', True),
    ("env -i claude --resume session-id", False),
    ('sudo -n claude -p "Explain the --desktop flag"', False),
    ('nohup claude -p "Why open -a Claude breaks Parall"', False),
    ('bash -lc "bash -lc \'echo open -a Claude\'"', False),
    ("nice -n 10 claude --resume session-id", False),
    ("/Applications/Claude.app/Contents/MacOS/Claude", True),
    ('"/Applications/Claude Official.app/Contents/MacOS/Claude"', True),
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
    plan = rollout.prepare(home)
    changed = plan[-1]["path"]
    changed.write_text("different owner wrote here", encoding="utf-8")
    evidence = tmp_path / "not-created"
    with pytest.raises(ValueError, match="changed after preflight"):
        rollout.apply(plan, evidence)
    assert not evidence.exists()


def test_historical_pins_match_committed_exact_byte_fixtures():
    assert rollout.sha(BASELINE.read_bytes()) == rollout.KNOWN_PRE_ISOLATION_GUARD_SHA256
    normalized_v1 = V1_BLOCK.read_text().rstrip("\n") + "\n\n"
    assert rollout.sha(normalized_v1.encode()) == rollout.KNOWN_INSTALLED_V1_BLOCK_SHA256
    normalized_v2 = V2_BLOCK.read_text().rstrip("\n") + "\n\n"
    assert rollout.sha(normalized_v2.encode()) == rollout.KNOWN_INSTALLED_V2_BLOCK_SHA256
    normalized_v3 = V3_BLOCK.read_text().rstrip("\n") + "\n\n"
    assert rollout.sha(normalized_v3.encode()) == rollout.KNOWN_INSTALLED_V3_BLOCK_SHA256
    normalized_v4 = V4_BLOCK.read_text().rstrip("\n") + "\n\n"
    assert rollout.sha(normalized_v4.encode()) == rollout.KNOWN_INSTALLED_V4_BLOCK_SHA256


@pytest.mark.parametrize("old_fragment", [
    lambda: V1_BLOCK.read_text().rstrip("\n") + "\n\n",
    lambda: V2_BLOCK.read_text().rstrip("\n") + "\n\n",
    lambda: V3_BLOCK.read_text().rstrip("\n") + "\n\n",
    lambda: V4_BLOCK.read_text().rstrip("\n") + "\n\n",
])
def test_exact_previous_guard_blocks_migrate_without_other_edits(old_fragment):
    source = legacy_source()
    old_block = old_fragment()
    assert source.count(rollout.GUARD_ANCHOR) == 1
    old = source.replace(rollout.GUARD_ANCHOR, old_block + rollout.GUARD_ANCHOR, 1)
    updated = rollout.render("guard", old)
    assert old_block not in updated
    assert rollout.template("guard") in updated
    assert rollout.NEW_WORKSPACE_ROOT in updated
    assert rollout.render("guard", updated) == updated


def test_unknown_previous_guard_block_refuses_before_write():
    source = legacy_source()
    fragment = rollout.GUARD_START + " unknown edit\n"
    old = source.replace(
        rollout.GUARD_ANCHOR, fragment + rollout.GUARD_ANCHOR, 1
    )
    with pytest.raises(ValueError, match="unrecognized guard block"):
        rollout.render("guard", old)



@pytest.mark.parametrize("cwd", ["/tmp", "/Users/chriswong/Downloads"])
@pytest.mark.parametrize("command,blocked", [
    ("open -a Claude", True),
    ("open -a claude", True),
    ("open -a CLAUDE", True),
    ("open -a " + chr(92) + chr(10) + "Claude", True),
    ("open -a C" + chr(92) + chr(10) + "laude", True),
    ('claude -p "Explain open -a ' + chr(92) + chr(10) + 'Claude"', False),
    ('osascript -e \'tell application "Claude Default" to activate\'', True),
    ('osascript -e \'tell application "Claude Official" to activate\'', True),
    ('osascript -e \'tell application "Claude 6" to activate\'', False),
    ("open CLAUDE://open/session", True),
    ("open -b COM.ANTHROPIC.CLAUDEFORDESKTOP", True),
    ('open -a "claude default"', True),
    ('open -a "Claude 6"', False),
    ('claude -p "Explain CLAUDE:// in text"', False),
    ("env - open -a Claude", True),
    ("command -p open -a Claude", True),
    ("exec -a harmless open -a Claude", True),
    ("nice -10 open -a Claude", True),
    ("time open -a Claude", True),
    ("caffeinate -i open -a Claude", True),
    ("caffeinate -t 30 -i open -a Claude", True),
    ("env - claude --resume native-session-id", False),
    ('command -p claude -p "Review this text"', False),
    ('nice -10 claude -p "Why open -a Claude breaks accounts"', False),
    ("time claude --resume native-session-id", False),
    ('caffeinate -i claude -p "Explain --desktop"', False),
    ("env -i open -a Claude", True),
    ("sudo -n open -a Claude", True),
    ("nohup open -a Claude", True),
    ("bash -lc \"bash -lc 'open -a Claude'\"", True),
    ("claude --desktop --resume real-session", True),
    ('claude -p "Explain the phrase open -a Claude"', False),
    ("claude --resume real-session", False),
    ("git push origin audit-branch", False),
    ("gh pr checks 1653 --watch", False),
])
def test_gui_denial_covers_shell_tools_outside_mastermind(cwd, command, blocked):
    installed = rollout.render("guard", legacy_source())
    assert rollout.SCOPED_GUARD_START not in installed
    assert rollout.GLOBAL_GUI_GUARD_START in installed
    assert installed.index(rollout.REMAINING_SCOPE_GATE + rollout.GUARD_ANCHOR) > installed.index(
        "    if unmanaged_desktop:"
    )
    namespace = {"__name__": "guard_fixture"}
    exec(compile(installed, "guard_fixture.py", "exec"), namespace)
    payload = {"cwd": cwd, "tool_name": "Bash", "tool_input": {"command": command}}
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        try:
            namespace["guard_bash"](payload, payload["tool_input"])
        except SystemExit as exit_info:
            assert exit_info.code == 0
    denied = '"permissionDecision": "deny"' in output.getvalue()
    assert denied is blocked, (cwd, command, output.getvalue())



def test_previously_global_guard_migrates_without_losing_scope_tail():
    original = legacy_source()
    previous = V4_BLOCK.read_text().rstrip("\n") + "\n\n"
    old = original.replace(
        rollout.GUARD_ANCHOR, previous + rollout.GUARD_ANCHOR, 1
    )
    old = old.replace(
        rollout.SCOPED_GUARD_START, rollout.GLOBAL_GUI_GUARD_START, 1
    )
    old = old.replace(
        rollout.GUARD_ANCHOR,
        rollout.REMAINING_SCOPE_GATE + rollout.GUARD_ANCHOR,
        1,
    )
    assert old.count(rollout.REMAINING_SCOPE_GATE + rollout.GUARD_ANCHOR) == 1
    updated = rollout.render("guard", old)
    assert rollout.template("guard") in updated
    assert updated.count(rollout.REMAINING_SCOPE_GATE + rollout.GUARD_ANCHOR) == 1
    assert rollout.SCOPED_GUARD_START not in updated
    assert rollout.render("guard", updated) == updated
