import json
import os
import stat
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import stage_teammates as st  # noqa: E402


def roster():
    return {"server": {"root": "/r"}, "teammates": [
        {"slug": "old", "name": "Old", "instance": "old"},
        {"slug": "eng", "name": "Eng", "instance": "eng",
         "paperclip_agent_id": "a1"},
    ]}


def plan(write=True):
    return {
        "server_root": "/r", "omh_bin": "/o/omh", "omh_home": "/h/.omh",
        "python_bin": "/py", "server_script": "/r/bin/memory_link_server.py",
        "write_enabled": write,
        "spec_template": {"paperclip_base": "http://127.0.0.1:1",
                          "binding": {"environmentId": "e", "projectId": "p"}},
        "teammates": {"old": {"notes_dir": "/n/old"},
                      "eng": {"new": True, "notes_dir": "/n/eng"}},
    }


def load(p):
    return json.loads(Path(p).read_text())


def test_every_planned_teammate_gets_its_own_link(tmp_path):
    st.stage(roster(), plan(), str(tmp_path))
    staged = load(tmp_path / "roster/team_roster.staged.json")
    for mate in staged["teammates"]:
        link = mate["memory_link"]
        assert link["mcp_config"] == f"/r/config/memory-link/{mate['slug']}.mcp.json"
        assert "mcp__memory-link__memory_save" in link["tools"]
        cfg = load(tmp_path / f"memory-link/{mate['slug']}.config.json")
        assert cfg["teammate"] == mate["slug"]
        assert cfg["write_enabled"] is True
        assert cfg["hermes_home_for_omh"].endswith(f"home-{mate['slug']}")
        mcp = load(tmp_path / f"memory-link/{mate['slug']}.mcp.json")
        args = mcp["mcpServers"]["memory-link"]["args"]
        assert args[-1] == f"/r/config/memory-link/{mate['slug']}.config.json"


def test_save_tool_absent_when_writing_off(tmp_path):
    st.stage(roster(), plan(write=False), str(tmp_path))
    staged = load(tmp_path / "roster/team_roster.staged.json")
    for mate in staged["teammates"]:
        assert "mcp__memory-link__memory_save" not in mate["memory_link"]["tools"]


def test_spec_only_for_new_teammates_with_own_instance(tmp_path):
    out = st.stage(roster(), plan(), str(tmp_path))
    assert out["specs"] == ["eng"]
    spec = load(tmp_path / "specs/eng.installed.json")
    assert spec["agent_id"] == "a1"
    assert spec["binding"]["providerInstanceId"] == "eng"
    assert spec["binding"]["primaryThreadId"] == st.PRIMARY_PLACEHOLDER
    assert spec["agent_dir"] == "/r/teammates/eng"
    assert not (tmp_path / "specs/old.installed.json").exists()


def test_files_are_private(tmp_path):
    st.stage(roster(), plan(), str(tmp_path))
    for p in tmp_path.rglob("*.json"):
        assert stat.S_IMODE(os.stat(p).st_mode) == 0o600


def test_instance_must_equal_slug(tmp_path):
    r = roster()
    r["teammates"][1]["instance"] = "capacity_fabric"
    with pytest.raises(SystemExit):
        st.stage(r, plan(), str(tmp_path))


def test_unknown_slug_refused(tmp_path):
    p = plan()
    p["teammates"]["ghost"] = {}
    with pytest.raises(SystemExit):
        st.stage(roster(), p, str(tmp_path))
