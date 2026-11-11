"""Lane T7 team-roster tool: spec, settings-merge and refusal tests.

Pure unit tests — no server is started or contacted. They exercise
``tools/mmos_team_server/team_roster.py`` against throwaway directories.
"""

import importlib.util
import json
import os
import stat
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
TOOL = REPO / "tools" / "mmos_team_server" / "team_roster.py"

spec_loader = importlib.util.spec_from_file_location("team_roster", TOOL)
team_roster = importlib.util.module_from_spec(spec_loader)
spec_loader.loader.exec_module(team_roster)


def make_spec(tmp_path, root=None, home=None, port=3780):
    root = root or str(tmp_path / "t3-team")
    home = home or os.path.join(root, "home")
    return {
        "server": {"root": root, "home": home,
                   "t3_bin": "/bin/echo", "port": port,
                   "provider_source_instance": "capacity_fabric"},
        "project": {"title": "Team",
                    "workspace_root": os.path.join(root, "team-project")},
        "model": "glm-5.3",
        "deny_write_roots": ["/tmp"],
        "teammates": [
            {"name": "A", "slug": "a", "role": "qa", "role_line": "quality",
             "accent_color": "#e0b64d", "instance": "a",
             "charter": "# A charter\n"},
            {"name": "B", "slug": "b", "role": "designer",
             "role_line": "design", "accent_color": "#3fb6a8", "instance": "b",
             "charter": "# B charter\n"},
        ],
    }


def load(tmp_path, spec):
    path = tmp_path / "spec.json"
    path.write_text(json.dumps(spec))
    return team_roster.load_spec(str(path))


def fake_home(tmp_path, extra_instances=None, top_unknown=True):
    home = tmp_path / "t3-team" / "home"
    (home / "userdata").mkdir(parents=True)
    settings = {
        "providerInstances": {
            "capacity_fabric": {
                "driver": "claudeAgent", "displayName": "Capacity Fabric",
                "enabled": True, "environment": ["SHOULD_NOT_BE_COPIED"],
                "config": {"homePath": "/old", "customModels":
                           [{"slug": "glm-5.3", "name": "GLM 5.3"}]},
            },
            "someone_else": {"driver": "claudeAgent", "displayName": "Other"},
        },
    }
    if extra_instances:
        settings["providerInstances"].update(extra_instances)
    if top_unknown:
        settings["aFutureUnknownKey"] = {"keep": ["me"]}
    path = home / "userdata" / "settings.json"
    path.write_text(json.dumps(settings, indent=2))
    path.chmod(0o600)
    return home, path


class TestSpecValidation:
    def test_valid_spec_loads(self, tmp_path):
        spec = load(tmp_path, make_spec(tmp_path))
        assert spec["model"] == "glm-5.3"

    def test_missing_key_refused(self, tmp_path):
        spec = make_spec(tmp_path)
        del spec["project"]
        with pytest.raises(SystemExit):
            load(tmp_path, spec)

    @pytest.mark.parametrize("port", [3773, 3774])
    def test_reserved_ports_refused(self, tmp_path, port):
        with pytest.raises(SystemExit):
            load(tmp_path, make_spec(tmp_path, port=port))

    def test_root_at_dot_t3_refused(self, tmp_path):
        with pytest.raises(SystemExit):
            load(tmp_path,
                 make_spec(tmp_path, root=os.path.expanduser("~/.t3")))

    def test_root_inside_dot_t3_refused(self, tmp_path):
        with pytest.raises(SystemExit):
            load(tmp_path,
                 make_spec(tmp_path,
                           root=os.path.expanduser("~/.t3/anything")))

    def test_root_symlink_into_dot_t3_refused(self, tmp_path):
        link = tmp_path / "link-to-t3"
        os.symlink(os.path.expanduser("~/.t3"), link)
        with pytest.raises(SystemExit):
            load(tmp_path, make_spec(tmp_path, root=str(link)))

    def test_duplicate_name_refused(self, tmp_path):
        spec = make_spec(tmp_path)
        spec["teammates"][1]["name"] = "A"
        with pytest.raises(SystemExit):
            load(tmp_path, spec)

    def test_duplicate_accent_color_refused(self, tmp_path):
        spec = make_spec(tmp_path)
        spec["teammates"][1]["accent_color"] = \
            spec["teammates"][0]["accent_color"].upper()
        with pytest.raises(SystemExit):
            load(tmp_path, spec)

    def test_empty_teammates_refused(self, tmp_path):
        spec = make_spec(tmp_path)
        spec["teammates"] = []
        with pytest.raises(SystemExit):
            load(tmp_path, spec)


class TestSettingsMerge:
    def test_merge_adds_instances_and_keeps_neighbours(self, tmp_path):
        home, path = fake_home(tmp_path)
        spec = load(tmp_path, make_spec(tmp_path, home=str(home)))
        changed = team_roster.ensure_instances(spec)
        assert changed == ["a", "b"]
        settings = json.loads(path.read_text())
        assert "someone_else" in settings["providerInstances"]
        assert settings["aFutureUnknownKey"] == {"keep": ["me"]}
        assert settings["providerInstances"]["a"]["displayName"] == "A"
        assert settings["providerInstances"]["a"]["accentColor"] == "#e0b64d"
        assert settings["providerInstances"]["a"]["config"]["customModels"] == \
            [{"slug": "glm-5.3", "name": "GLM 5.3"}]
        # the source instance's environment values are never copied
        assert settings["providerInstances"]["a"]["environment"] == []

    def test_merge_is_idempotent(self, tmp_path):
        home, path = fake_home(tmp_path)
        spec = load(tmp_path, make_spec(tmp_path, home=str(home)))
        team_roster.ensure_instances(spec)
        first = path.read_text()
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
        changed = team_roster.ensure_instances(spec)
        assert changed == []
        assert path.read_text() == first

    def test_merge_updates_stale_teammate_instance(self, tmp_path):
        home, path = fake_home(tmp_path, extra_instances={
            "a": {"driver": "claudeAgent", "displayName": "Old Name"}})
        spec = load(tmp_path, make_spec(tmp_path, home=str(home)))
        changed = team_roster.ensure_instances(spec)
        assert changed == ["a", "b"]  # a was stale, b was new
        settings = json.loads(path.read_text())
        assert settings["providerInstances"]["a"]["displayName"] == "A"


class TestToolLimits:
    def test_home_allowed_workspace_denied(self, tmp_path):
        spec = load(tmp_path, make_spec(tmp_path))
        mate = spec["teammates"][0]
        limits = team_roster.tool_limits(spec, mate)
        home = team_roster.teammate_home(spec, mate)
        workspace = team_roster.expand(spec["project"]["workspace_root"])
        joined = " ".join(limits["permissions"]["allow"] +
                          limits["permissions"]["deny"])
        assert f"Write(/{home}/**)" in limits["permissions"]["allow"]
        assert f"Write(/{workspace}/**)" in limits["permissions"]["deny"]
        assert "Bash" in limits["permissions"]["deny"]
        assert "Write(//tmp/**)" in joined


class TestToolLimitsCredentials:
    """Review R2a finding 1: a teammate cannot read credentials or other
    teammates' homes, and cannot rewrite its own limits or charter."""

    def test_server_private_and_other_homes_unreadable(self, tmp_path):
        spec = load(tmp_path, make_spec(tmp_path))
        mate, other = spec["teammates"][0], spec["teammates"][1]
        root = team_roster.expand(spec["server"]["root"])
        os.makedirs(os.path.join(root, "run"), exist_ok=True)
        os.makedirs(team_roster.teammate_home(spec, other), exist_ok=True)
        deny = team_roster.tool_limits(spec, mate)["permissions"]["deny"]
        assert f"Read(/{root}/run/**)" in deny
        assert f"Read(/{team_roster.teammate_home(spec, other)}/**)" in deny
        home = team_roster.teammate_home(spec, mate)
        assert not any(d.startswith(f"Read(/{home}/**") for d in deny)
        assert f"Read(/{home}/cutover-preimage.json)" in deny

    def test_own_limits_and_charter_not_writable(self, tmp_path):
        spec = load(tmp_path, make_spec(tmp_path))
        mate = spec["teammates"][0]
        home = team_roster.teammate_home(spec, mate)
        deny = team_roster.tool_limits(spec, mate)["permissions"]["deny"]
        for name in ("tool-limits.json", "CHARTER.md", "carrier.json",
                     "cutover-preimage.json"):
            assert f"Write(/{home}/{name})" in deny
            assert f"Edit(/{home}/{name})" in deny
        assert not any("CLAUDE.md" in d for d in deny)

    def test_own_claude_configuration_not_writable(self, tmp_path):
        """The home is the teammate's Claude configuration folder: a settings
        file, an MCP entry, a skill or a plugin written there would run."""
        spec = load(tmp_path, make_spec(tmp_path))
        mate = spec["teammates"][0]
        home = team_roster.teammate_home(spec, mate)
        deny = team_roster.tool_limits(spec, mate)["permissions"]["deny"]
        for name in ("settings.json", "settings.local.json", ".claude.json",
                     ".mcp.json", "plugins", "skills", "agents", "commands",
                     "hooks", "rules", ".claude"):
            for tool in ("Write", "Edit"):
                assert f"{tool}(/{home}/{name})" in deny
                assert f"{tool}(/{home}/{name}/**)" in deny
        assert not any("CLAUDE.md" in d for d in deny)
        allow = team_roster.tool_limits(spec, mate)["permissions"]["allow"]
        assert f"Write(/{home}/**)" in allow

    def test_spec_roots_and_siblings(self, tmp_path):
        raw = make_spec(tmp_path)
        secret_dir = tmp_path / "elsewhere" / "secrets"
        secret_dir.mkdir(parents=True)
        raw["deny_read_roots"] = [str(secret_dir)]
        raw["deny_read_root_siblings"] = True
        spec = load(tmp_path, raw)
        root = team_roster.expand(spec["server"]["root"])
        os.makedirs(root, exist_ok=True)
        sibling = os.path.join(os.path.dirname(root), "sibling-proofs")
        os.makedirs(sibling, exist_ok=True)
        mate = spec["teammates"][0]
        deny = team_roster.tool_limits(spec, mate)["permissions"]["deny"]
        assert f"Read(/{secret_dir}/**)" in deny
        assert f"Read(/{sibling}/**)" in deny
        assert not any(d.startswith(f"Read(/{root}/**") for d in deny)


class TestFileAssets:
    def test_write_and_rewrite_home(self, tmp_path):
        spec = load(tmp_path, make_spec(tmp_path))
        mate = spec["teammates"][0]
        wrote = team_roster.write_file_assets(spec, mate)
        assert set(wrote) == {"CLAUDE.md", "CHARTER.md", "tool-limits.json"}
        home = team_roster.teammate_home(spec, mate)
        assert stat.S_IMODE(os.stat(home).st_mode) == 0o700
        assert stat.S_IMODE(
            os.stat(os.path.join(home, "CHARTER.md")).st_mode) == 0o600
        assert team_roster.write_file_assets(spec, mate) == []
        mate["charter"] = "# changed\n"
        assert team_roster.write_file_assets(spec, mate) == ["CHARTER.md"]

    def test_memory_file_never_rewritten_by_apply(self, tmp_path):
        # CLAUDE.md is the teammate's live long-term memory: once it exists,
        # apply must leave it alone even though it differs from the seed.
        spec = load(tmp_path, make_spec(tmp_path))
        mate = spec["teammates"][0]
        team_roster.write_file_assets(spec, mate)
        memory = os.path.join(team_roster.teammate_home(spec, mate), "CLAUDE.md")
        remembered = open(memory).read() + "- check-in word: MARLIN-77\n"
        open(memory, "w").write(remembered)
        wrote = team_roster.write_file_assets(spec, mate)
        assert "CLAUDE.md" not in wrote
        assert open(memory).read() == remembered


class TestMcpToolSwitch:
    """Per-teammate tool switch (browser_use / computer_use), default off."""

    def test_default_off_writes_no_mcp_file_and_no_flag(self, tmp_path):
        spec = load(tmp_path, make_spec(tmp_path))
        mate = spec["teammates"][0]
        wrote = team_roster.write_file_assets(spec, mate)
        home = team_roster.teammate_home(spec, mate)
        assert "mcp-servers.json" not in wrote
        assert not os.path.exists(os.path.join(home, "mcp-servers.json"))
        inst = team_roster.instance_for(spec, mate)
        assert "--mcp-config" not in inst["config"]["launchArgs"]

    def test_switch_on_writes_locked_file_and_flag(self, tmp_path):
        raw = make_spec(tmp_path)
        raw["teammates"][0]["tools"] = {"browser_use": True,
                                        "computer_use": True}
        spec = load(tmp_path, raw)
        mate = spec["teammates"][0]
        wrote = team_roster.write_file_assets(spec, mate)
        home = team_roster.teammate_home(spec, mate)
        path = os.path.join(home, "mcp-servers.json")
        assert "mcp-servers.json" in wrote
        assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
        entries = json.load(open(path))
        assert set(entries) == {"mmx-browser", "mmos-computer-use"}
        assert entries["mmos-computer-use"]["command"] == "/usr/bin/python3"
        inst = team_roster.instance_for(spec, mate)
        assert inst["config"]["launchArgs"].endswith("mcp-servers.json")
        assert "--mcp-config" in inst["config"]["launchArgs"]

    def test_one_flag_writes_only_that_entry(self, tmp_path):
        raw = make_spec(tmp_path)
        raw["teammates"][1]["tools"] = {"browser_use": True}
        spec = load(tmp_path, raw)
        mate = spec["teammates"][1]
        team_roster.write_file_assets(spec, mate)
        entries = json.load(open(os.path.join(
            team_roster.teammate_home(spec, mate), "mcp-servers.json")))
        assert set(entries) == {"mmx-browser"}

    def test_switch_off_removes_stale_file(self, tmp_path):
        raw = make_spec(tmp_path)
        raw["teammates"][0]["tools"] = {"browser_use": True}
        spec = load(tmp_path, raw)
        mate = spec["teammates"][0]
        team_roster.write_file_assets(spec, mate)
        path = os.path.join(team_roster.teammate_home(spec, mate),
                            "mcp-servers.json")
        assert os.path.exists(path)
        mate["tools"] = {}
        wrote = team_roster.write_file_assets(spec, mate)
        assert "mcp-servers.json" not in wrote
        assert not os.path.exists(path)
        inst = team_roster.instance_for(spec, mate)
        assert "--mcp-config" not in inst["config"]["launchArgs"]

    def test_mcp_file_is_home_locked(self):
        assert "mcp-servers.json" in team_roster.HOME_LOCKED

    def test_bad_tools_shape_refused(self, tmp_path):
        raw = make_spec(tmp_path)
        raw["teammates"][0]["tools"] = {"browser_use": "yes"}
        with pytest.raises(SystemExit):
            load(tmp_path, raw)

    def test_unknown_tool_key_refused(self, tmp_path):
        raw = make_spec(tmp_path)
        raw["teammates"][0]["tools"] = {"shell": True}
        with pytest.raises(SystemExit):
            load(tmp_path, raw)
