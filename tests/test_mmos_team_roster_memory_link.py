"""Roster patch for lane HM: a teammate's optional `memory_link` block
becomes (1) exact MCP tool names in its gate config and (2) one
--mcp-config launch argument pointing at a server-private file."""
import json
import os

import pytest

from test_mmos_team_roster import make_spec, load, team_roster  # noqa: F401


def _with_link(tmp_path, tools=("mcp__memory-link__memory_recall",)):
    spec = make_spec(tmp_path)
    root = spec["server"]["root"]
    spec["teammates"][0]["memory_link"] = {
        "mcp_config": os.path.join(root, "config", "memory-link", "a.mcp.json"),
        "tools": list(tools)}
    return spec


def test_gate_config_carries_exact_tools(tmp_path):
    spec = load(tmp_path, _with_link(tmp_path))
    cfg = team_roster.gate_config(spec, spec["teammates"][0])
    assert cfg["allow_mcp_tools"] == ["mcp__memory-link__memory_recall"]
    other = team_roster.gate_config(spec, spec["teammates"][1])
    assert "allow_mcp_tools" not in other


def test_launch_args_carry_mcp_config(tmp_path):
    spec = load(tmp_path, _with_link(tmp_path))
    inst = team_roster.instance_for(spec, spec["teammates"][0])
    args = inst["config"]["launchArgs"].split(" ")
    i = args.index("--mcp-config")
    assert args[i + 1].endswith("/config/memory-link/a.mcp.json")
    plain = team_roster.instance_for(spec, spec["teammates"][1])
    assert "--mcp-config" not in plain["config"]["launchArgs"]


def test_tools_outside_namespace_refused(tmp_path):
    spec = _with_link(tmp_path, tools=("mcp__t3-code__delegate_task",))
    with pytest.raises(SystemExit):
        load(tmp_path, spec)


def test_mcp_config_must_live_in_server_config(tmp_path):
    spec = _with_link(tmp_path)
    spec["teammates"][0]["memory_link"]["mcp_config"] = os.path.join(
        spec["server"]["root"], "teammates", "a", "x.mcp.json")
    with pytest.raises(SystemExit):
        load(tmp_path, spec)


# --- Lane HM finding (pin 0770446): the server applies a settings.json write
# about 1 s later (fs.watch, 100 ms debounce, then registry rebuild). A thread
# start sent in that window is refused "Provider instance ... is disabled for
# project". The roster retries that ONE refusal after a short wait, bounded.

class _Proc:
    def __init__(self, rc, out="", err=""):
        self.returncode, self.stdout, self.stderr = rc, out, err


def test_start_retries_settings_lag_refusal(monkeypatch):
    calls = []
    seq = [_Proc(1, "", 'Provider instance "x" is disabled for project p.'),
           _Proc(0, '{"threadId": "mcp:1"}')]
    monkeypatch.setattr(team_roster, "t3", lambda *a, **k: (calls.append(a), seq.pop(0))[1])
    monkeypatch.setattr(team_roster.time, "sleep", lambda s: None)
    out = team_roster.start_thread_after_settings({"server": {}}, ["thread", "start"], "t3 thread start")
    assert out == {"threadId": "mcp:1"}
    assert len(calls) == 2


def test_start_does_not_retry_other_failures(monkeypatch):
    monkeypatch.setattr(team_roster, "t3", lambda *a, **k: _Proc(1, "", "some other error"))
    monkeypatch.setattr(team_roster.time, "sleep", lambda s: None)
    with pytest.raises(SystemExit):
        team_roster.start_thread_after_settings({"server": {}}, ["thread", "start"], "t3 thread start")


def test_start_gives_up_after_bounded_wait(monkeypatch):
    n = []
    monkeypatch.setattr(team_roster, "t3", lambda *a, **k: (n.append(1), _Proc(1, "", 'Provider instance "x" is disabled for project p.'))[1])
    monkeypatch.setattr(team_roster.time, "sleep", lambda s: None)
    with pytest.raises(SystemExit):
        team_roster.start_thread_after_settings({"server": {}}, ["thread", "start"], "t3 thread start")
    assert len(n) == team_roster.SETTINGS_LAG_ATTEMPTS


# --- RF-MEMLINK item (b): a write fence is never held by the hook alone. The
# history archive is read-only for the teammate (ruling 22 accepts a residual
# reader, never a writer), so `history` joins the roster's HOME_LOCKED set and
# the rule layer carries the deny. MED-2 of the 2026-11-12 independent review.


def test_history_is_in_the_roster_locked_set():
    assert "history" in team_roster.HOME_LOCKED


def test_tool_limits_deny_history_writes(tmp_path):
    spec = load(tmp_path, make_spec(tmp_path))
    mate = spec["teammates"][0]
    limits = team_roster.tool_limits(spec, mate)
    home = team_roster.teammate_home(spec, mate)
    deny = limits["permissions"]["deny"]
    assert f"Write(/{home}/history)" in deny
    assert f"Edit(/{home}/history)" in deny
    assert f"Write(/{home}/history/**)" in deny
    assert f"Edit(/{home}/history/**)" in deny
    # and no allow rule grants the archive itself
    allow = limits["permissions"]["allow"]
    assert not any(rule.startswith(f"Write(/{home}/history")
                   or rule.startswith(f"Edit(/{home}/history")
                   for rule in allow)


def test_rooted_home_write_rules_deny_history(tmp_path):
    spec = load(tmp_path, make_spec(tmp_path))
    mate = spec["teammates"][0]
    home = team_roster.teammate_home(spec, mate)
    os.makedirs(home, exist_ok=True)
    allow, deny = team_roster.rooted_home_write_rules(spec, mate)
    assert f"Write(/{home}/history/**)" in deny
    assert not any("history" in rule for rule in allow)


@pytest.mark.parametrize("name", ["history", "history/"])
def test_home_write_allow_history_refused(tmp_path, name):
    spec = make_spec(tmp_path)
    spec["home_write_allow"] = [name]
    with pytest.raises(SystemExit):
        load(tmp_path, spec)

