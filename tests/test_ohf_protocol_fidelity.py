from __future__ import annotations

import io
import json
from contextlib import redirect_stdout

from scripts.ohf.fake_app_server import FakeAppServer
from scripts.ohf.protocol import (
    extra_roots_set_params,
    mcp_tool_names,
    parse_account_read,
    parse_skills_list,
    skill_names,
    skills_list_params,
    turn_texts,
)


def _rpc(server: FakeAppServer, method: str, params=None, request_id: int = 1) -> dict:
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        payload = {"method": method, "id": request_id}
        if params is not None:
            payload["params"] = params
        server.handle(payload)
    lines = [line for line in buffer.getvalue().splitlines() if line.strip()]
    return json.loads(lines[0])


def test_fake_skills_list_is_grouped_per_cwd(tmp_path, monkeypatch):
    monkeypatch.setenv("OHF_FAKE_WORKSPACE", str(tmp_path))
    monkeypatch.setenv("OHF_FAKE_SKILL_ROOT", str(tmp_path))
    skill = tmp_path / "ohf-probe"
    skill.mkdir()
    (skill / "SKILL.md").write_text("# ohf-probe\n", encoding="utf-8")
    server = FakeAppServer()
    _rpc(server, "initialize", {}, 1)
    result = _rpc(server, "skills/list", skills_list_params(str(tmp_path)), 2)["result"]
    assert "cwd" in result["data"][0]
    assert "skills" in result["data"][0]
    assert result["data"][0]["skills"][0]["name"] == "ohf-probe"
    assert parse_skills_list(result)
    assert skill_names(result) == ["ohf-probe"]


def test_flat_skills_list_is_rejected_by_parser():
    flat = {"data": [{"name": "ohf-probe", "path": "/tmp/ohf-probe"}]}
    assert parse_skills_list(flat) == []
    assert skill_names(flat) == []


def test_extra_roots_uses_extraRoots_not_roots(tmp_path, monkeypatch):
    monkeypatch.setenv("OHF_FAKE_WORKSPACE", str(tmp_path))
    extra = tmp_path / "extra"
    skill = extra / "ohf-probe"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("# ohf-probe\n", encoding="utf-8")
    server = FakeAppServer()
    _rpc(server, "initialize", {}, 1)
    _rpc(server, "skills/extraRoots/set", {"roots": [str(extra)]}, 2)
    assert server.extra_roots == []
    _rpc(server, "skills/extraRoots/set", extra_roots_set_params([str(extra)]), 3)
    assert server.extra_roots == [extra]
    params = extra_roots_set_params([str(extra)])
    assert "extraRoots" in params
    assert "roots" not in params


def test_account_read_parser_ignores_top_level_auth_mode():
    parsed = parse_account_read({"authMode": "chatgpt", "planType": "plus"})
    assert parsed["auth_type"] == "UNKNOWN"
    assert parsed["plan_type"] == "UNKNOWN"
    real = parse_account_read(
        {
            "account": {
                "type": "chatgpt",
                "email": "hidden@example.invalid",
                "planType": "plus",
            },
            "requiresOpenaiAuth": True,
        }
    )
    assert real["auth_type"] == "chatgpt"
    assert real["plan_type"] == "plus"
    assert real["requires_openai_auth"] is True
    assert "email" not in real


def test_mcp_tools_are_name_keyed_objects():
    listed = {
        "data": [
            {
                "name": "ohf_probe",
                "tools": {"ohf_probe_echo": {"name": "ohf_probe_echo"}},
            }
        ]
    }
    assert mcp_tool_names(listed) == ["ohf_probe_echo"]
    flat = {"data": [{"name": "ohf_probe", "tools": [{"name": "ohf_probe_echo"}]}]}
    # A list is the old fake shape; the live parser must still not require it.
    assert mcp_tool_names(flat) == ["ohf_probe_echo"]


def test_turn_texts_read_item_content():
    turns = [
        {
            "id": "turn_1",
            "items": [
                {"type": "agentMessage", "content": [{"type": "output_text", "text": "OHF_P0_ACK-P"}]}
            ],
        }
    ]
    assert "OHF_P0_ACK-P" in " ".join(turn_texts(turns))


def test_skills_list_params_are_array_of_cwd_objects():
    params = skills_list_params("/tmp/ws", ["/tmp/ws/.agents/skills"])
    assert params["cwds"] == ["/tmp/ws"]
    assert isinstance(params["perCwdExtraUserRoots"], list)
    assert params["perCwdExtraUserRoots"][0]["cwd"] == "/tmp/ws"
    assert not isinstance(params["perCwdExtraUserRoots"], dict)
