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
