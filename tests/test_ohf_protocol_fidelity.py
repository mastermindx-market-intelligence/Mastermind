from __future__ import annotations

import io
import json
from contextlib import redirect_stdout

import pytest

from scripts.ohf.fake_app_server import FakeAppServer
from scripts.ohf.protocol import (
    SkillProtocolShapeError,
    enabled_skill_names,
    extra_roots_set_params,
    mcp_tool_names,
    parse_account_read,
    parse_skills_list,
    parse_skills_list_strict,
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


def _rpc_all(server: FakeAppServer, method: str, params=None, request_id: int = 1) -> list[dict]:
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        payload = {"method": method, "id": request_id}
        if params is not None:
            payload["params"] = params
        server.handle(payload)
    lines = [line for line in buffer.getvalue().splitlines() if line.strip()]
    return [json.loads(line) for line in lines]


def _grouped(rows: list, cwd: str = "/workspace") -> dict:
    return {"data": [{"cwd": cwd, "skills": rows}]}


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


# ---------------------------------------------------------------------------
# Strict CAP-S1 skills-protocol parser (parse_skills_list_strict)
# ---------------------------------------------------------------------------


def test_strict_parser_happy_grouped_path_preserves_duplicates_and_order():
    rows = [
        {"name": "alpha", "enabled": True, "path": "/skills/root-a/alpha/SKILL.md"},
        {"name": "beta", "enabled": False, "path": "/skills/root-a/beta/SKILL.md"},
        {"name": "alpha", "enabled": True, "path": "/skills/root-b/alpha/SKILL.md"},
        {"name": "gamma", "enabled": True},
    ]
    result = _grouped(rows)
    parsed = parse_skills_list_strict(result, expected_cwd="/workspace")
    assert parsed == rows
    assert [row["name"] for row in parsed] == ["alpha", "beta", "alpha", "gamma"]
    assert enabled_skill_names(parsed) == ["alpha", "alpha", "gamma"]


def test_strict_parser_rejects_flat_payload():
    flat = {"data": [{"name": "ohf-probe", "path": "/tmp/ohf-probe"}]}
    with pytest.raises(SkillProtocolShapeError):
        parse_skills_list_strict(flat, expected_cwd="/workspace")


def test_strict_parser_rejects_zero_groups():
    with pytest.raises(SkillProtocolShapeError):
        parse_skills_list_strict({"data": []}, expected_cwd="/workspace")


def test_strict_parser_rejects_two_groups():
    payload = {
        "data": [
            {"cwd": "/workspace", "skills": []},
            {"cwd": "/workspace", "skills": []},
        ]
    }
    with pytest.raises(SkillProtocolShapeError):
        parse_skills_list_strict(payload, expected_cwd="/workspace")


def test_strict_parser_rejects_wrong_cwd():
    payload = _grouped([], cwd="/some/other/cwd")
    with pytest.raises(SkillProtocolShapeError):
        parse_skills_list_strict(payload, expected_cwd="/workspace")


def test_strict_parser_rejects_blank_name():
    payload = _grouped([{"name": "   ", "enabled": True}])
    with pytest.raises(SkillProtocolShapeError):
        parse_skills_list_strict(payload, expected_cwd="/workspace")


def test_strict_parser_rejects_oversized_name():
    payload = _grouped([{"name": "a" * 300, "enabled": True}])
    with pytest.raises(SkillProtocolShapeError):
        parse_skills_list_strict(payload, expected_cwd="/workspace")


@pytest.mark.parametrize(
    "row",
    [
        {"name": "ohf-probe"},
        {"name": "ohf-probe", "enabled": "true"},
        {"name": "ohf-probe", "enabled": 1},
        {"name": "ohf-probe", "enabled": None},
    ],
)
def test_strict_parser_rejects_malformed_enabled(row):
    payload = _grouped([row])
    with pytest.raises(SkillProtocolShapeError):
        parse_skills_list_strict(payload, expected_cwd="/workspace")


@pytest.mark.parametrize(
    "path",
    [
        "relative/SKILL.md",
        "",
        "/" + "a" * 5000,
    ],
)
def test_strict_parser_rejects_malformed_path(path):
    payload = _grouped([{"name": "ohf-probe", "enabled": True, "path": path}])
    with pytest.raises(SkillProtocolShapeError):
        parse_skills_list_strict(payload, expected_cwd="/workspace")


def test_strict_parser_accepts_pathless_rows():
    payload = _grouped([{"name": "ohf-probe", "enabled": True}])
    parsed = parse_skills_list_strict(payload, expected_cwd="/workspace")
    assert parsed == [{"name": "ohf-probe", "enabled": True}]
    assert "path" not in parsed[0]


def test_strict_parser_errors_never_echo_caller_values():
    hostile_name = "sk-hostile-secret-should-never-leak"
    hostile_path = "/definitely/not/leaked/hostile-path-value"
    result = _grouped([{"name": hostile_name, "enabled": "true", "path": hostile_path}])
    with pytest.raises(SkillProtocolShapeError) as excinfo:
        parse_skills_list_strict(result, expected_cwd="/workspace")
    message = str(excinfo.value)
    assert hostile_name not in message
    assert hostile_path not in message

    oversized_name = "z" * 5000
    with pytest.raises(SkillProtocolShapeError) as excinfo2:
        parse_skills_list_strict(
            _grouped([{"name": oversized_name, "enabled": True}]), expected_cwd="/workspace"
        )
    assert oversized_name not in str(excinfo2.value)


# ---------------------------------------------------------------------------
# Fake-App-Server fidelity (drives FakeAppServer via the same _rpc pattern)
# ---------------------------------------------------------------------------


def test_fake_baseline_skills_list_is_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("OHF_FAKE_WORKSPACE", str(tmp_path))
    monkeypatch.setenv("OHF_FAKE_SKILL_ROOT", str(tmp_path / "no-such-root"))
    server = FakeAppServer()
    _rpc(server, "initialize", {}, 1)
    result = _rpc(server, "skills/list", skills_list_params(str(tmp_path)), 2)["result"]
    parsed = parse_skills_list_strict(result, expected_cwd=str(tmp_path))
    assert parsed == []


def test_fake_extra_root_yields_exact_rows(tmp_path, monkeypatch):
    monkeypatch.setenv("OHF_FAKE_WORKSPACE", str(tmp_path))
    monkeypatch.setenv("OHF_FAKE_SKILL_ROOT", str(tmp_path / "no-such-root"))
    extra = tmp_path / "extra"
    skill = extra / "ohf-probe"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("# ohf-probe\n", encoding="utf-8")
    server = FakeAppServer()
    _rpc(server, "initialize", {}, 1)
    _rpc(server, "skills/extraRoots/set", extra_roots_set_params([str(extra)]), 2)
    result = _rpc(server, "skills/list", skills_list_params(str(tmp_path)), 3)["result"]
    parsed = parse_skills_list_strict(result, expected_cwd=str(tmp_path))
    assert [row["name"] for row in parsed] == ["ohf-probe"]
    assert enabled_skill_names(parsed) == ["ohf-probe"]

    _rpc(server, "skills/extraRoots/set", extra_roots_set_params([]), 4)
    result_after_clear = _rpc(server, "skills/list", skills_list_params(str(tmp_path)), 5)["result"]
    parsed_after_clear = parse_skills_list_strict(result_after_clear, expected_cwd=str(tmp_path))
    assert parsed_after_clear == []


def test_fake_duplicate_same_name_from_two_roots_yields_two_rows(tmp_path, monkeypatch):
    root_a = tmp_path / "root_a"
    root_b = tmp_path / "root_b"
    for root in (root_a, root_b):
        skill = root / "ohf-probe"
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text("# ohf-probe\n", encoding="utf-8")
    monkeypatch.setenv("OHF_FAKE_WORKSPACE", str(tmp_path))
    monkeypatch.setenv("OHF_FAKE_SKILL_ROOT", str(root_a))
    server = FakeAppServer()
    _rpc(server, "initialize", {}, 1)
    _rpc(server, "skills/extraRoots/set", extra_roots_set_params([str(root_b)]), 2)
    result = _rpc(server, "skills/list", skills_list_params(str(tmp_path)), 3)["result"]
    parsed = parse_skills_list_strict(result, expected_cwd=str(tmp_path))
    assert [row["name"] for row in parsed] == ["ohf-probe", "ohf-probe"]
    paths = {row["path"] for row in parsed}
    assert len(paths) == 2


def test_fake_omit_path_mode_yields_pathless_rows(tmp_path, monkeypatch):
    skill = tmp_path / "ohf-probe"
    skill.mkdir()
    (skill / "SKILL.md").write_text("# ohf-probe\n", encoding="utf-8")
    monkeypatch.setenv("OHF_FAKE_WORKSPACE", str(tmp_path))
    monkeypatch.setenv("OHF_FAKE_SKILL_ROOT", str(tmp_path))
    monkeypatch.setenv("OHF_FAKE_SKILLS_OMIT_PATH", "1")
    server = FakeAppServer()
    _rpc(server, "initialize", {}, 1)
    result = _rpc(server, "skills/list", skills_list_params(str(tmp_path)), 2)["result"]
    parsed = parse_skills_list_strict(result, expected_cwd=str(tmp_path))
    assert parsed == [{"name": "ohf-probe", "enabled": True, "scope": "repo"}]
    assert "path" not in parsed[0]


@pytest.mark.parametrize("mode", ["missing", "string"])
def test_fake_malformed_enabled_modes_refuse_at_strict_parser(tmp_path, monkeypatch, mode):
    skill = tmp_path / "ohf-probe"
    skill.mkdir()
    (skill / "SKILL.md").write_text("# ohf-probe\n", encoding="utf-8")
    monkeypatch.setenv("OHF_FAKE_WORKSPACE", str(tmp_path))
    monkeypatch.setenv("OHF_FAKE_SKILL_ROOT", str(tmp_path))
    monkeypatch.setenv("OHF_FAKE_SKILLS_MALFORMED_ENABLED", mode)
    server = FakeAppServer()
    _rpc(server, "initialize", {}, 1)
    result = _rpc(server, "skills/list", skills_list_params(str(tmp_path)), 2)["result"]
    with pytest.raises(SkillProtocolShapeError):
        parse_skills_list_strict(result, expected_cwd=str(tmp_path))


def test_fake_ambient_skill_visible_with_empty_roots(tmp_path, monkeypatch):
    monkeypatch.setenv("OHF_FAKE_WORKSPACE", str(tmp_path))
    monkeypatch.setenv("OHF_FAKE_SKILL_ROOT", str(tmp_path / "no-such-root"))
    monkeypatch.setenv("OHF_FAKE_AMBIENT_SKILL", "ambient-ghost")
    server = FakeAppServer()
    _rpc(server, "initialize", {}, 1)
    result = _rpc(server, "skills/list", skills_list_params(str(tmp_path)), 2)["result"]
    parsed = parse_skills_list_strict(result, expected_cwd=str(tmp_path))
    assert [row["name"] for row in parsed] == ["ambient-ghost"]
    assert enabled_skill_names(parsed) == ["ambient-ghost"]


def test_fake_skills_changed_notification_after_extra_roots_set_when_enabled(tmp_path, monkeypatch):
    monkeypatch.setenv("OHF_FAKE_WORKSPACE", str(tmp_path))
    monkeypatch.setenv("OHF_FAKE_SKILLS_CHANGED", "1")
    server = FakeAppServer()
    _rpc(server, "initialize", {}, 1)
    messages = _rpc_all(server, "skills/extraRoots/set", extra_roots_set_params([]), 2)
    methods = [msg.get("method") for msg in messages if "method" in msg]
    assert "skills/changed" in methods


def test_fake_skills_changed_notification_off_by_default(tmp_path, monkeypatch):
    monkeypatch.setenv("OHF_FAKE_WORKSPACE", str(tmp_path))
    server = FakeAppServer()
    _rpc(server, "initialize", {}, 1)
    messages = _rpc_all(server, "skills/extraRoots/set", extra_roots_set_params([]), 2)
    methods = [msg.get("method") for msg in messages if "method" in msg]
    assert "skills/changed" not in methods


def test_fake_config_read_omits_bundled_by_default(tmp_path, monkeypatch):
    monkeypatch.setenv("OHF_FAKE_WORKSPACE", str(tmp_path))
    server = FakeAppServer()
    _rpc(server, "initialize", {}, 1)
    config = _rpc(server, "config/read", {"includeLayers": False}, 2)["result"]["config"]
    assert "skills" not in config


def test_fake_config_read_bundled_disabled_switch_adds_the_bundled_block(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("OHF_FAKE_WORKSPACE", str(tmp_path))
    monkeypatch.setenv("OHF_FAKE_BUNDLED_DISABLED", "1")
    server = FakeAppServer()
    _rpc(server, "initialize", {}, 1)
    config = _rpc(server, "config/read", {"includeLayers": False}, 2)["result"]["config"]
    assert config["skills"] == {"bundled": {"enabled": False}}


def test_turn_start_captures_valid_skill_item(tmp_path, monkeypatch):
    monkeypatch.setenv("OHF_FAKE_WORKSPACE", str(tmp_path))
    server = FakeAppServer()
    _rpc(server, "initialize", {}, 1)
    thread = _rpc(server, "thread/start", {"cwd": str(tmp_path)}, 2)["result"]["thread"]
    thread_id = thread["id"]
    skill_path = str(tmp_path / "ohf-probe" / "SKILL.md")
    input_items = [
        {"type": "text", "text": "hello"},
        {"type": "skill", "name": "ohf-probe", "path": skill_path},
    ]
    resp = _rpc(server, "turn/start", {"threadId": thread_id, "input": input_items}, 3)
    assert "result" in resp
    read = _rpc(server, "thread/read", {"threadId": thread_id}, 4)["result"]
    turns = read["thread"]["turns"]
    assert turns[-1]["inputSkills"] == [{"type": "skill", "name": "ohf-probe", "path": skill_path}]


def test_turn_start_rejects_malformed_skill_item(tmp_path, monkeypatch):
    monkeypatch.setenv("OHF_FAKE_WORKSPACE", str(tmp_path))
    server = FakeAppServer()
    _rpc(server, "initialize", {}, 1)
    thread = _rpc(server, "thread/start", {"cwd": str(tmp_path)}, 2)["result"]["thread"]
    thread_id = thread["id"]
    input_items = [{"type": "skill", "name": "ohf-probe", "path": "relative/not/absolute"}]
    resp = _rpc(server, "turn/start", {"threadId": thread_id, "input": input_items}, 3)
    assert "error" in resp
    read = _rpc(server, "thread/read", {"threadId": thread_id}, 4)["result"]
    assert read["thread"]["turns"] == []


def test_turn_start_text_only_unchanged(tmp_path, monkeypatch):
    monkeypatch.setenv("OHF_FAKE_WORKSPACE", str(tmp_path))
    server = FakeAppServer()
    _rpc(server, "initialize", {}, 1)
    thread = _rpc(server, "thread/start", {"cwd": str(tmp_path)}, 2)["result"]["thread"]
    thread_id = thread["id"]
    resp = _rpc(
        server, "turn/start", {"threadId": thread_id, "input": [{"type": "text", "text": "hi-P"}]}, 3
    )
    assert "result" in resp
    read = _rpc(server, "thread/read", {"threadId": thread_id}, 4)["result"]
    turns = read["thread"]["turns"]
    assert turns[-1]["text"].endswith("-P")
    assert turns[-1].get("inputSkills") == []
