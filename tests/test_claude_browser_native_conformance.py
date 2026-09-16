"""Unit tests only; importing the native fixture never starts a provider or CLI."""
import importlib.util
import json
from pathlib import Path

import pytest

FIXTURE = Path(__file__).with_name("claude_browser_native_conformance.py")


def test_native_browser_fixture_exists():
    assert FIXTURE.is_file(), "Native Claude/browser conformance consumer is missing"


@pytest.fixture
def api():
    if not FIXTURE.is_file():
        pytest.skip("native fixture absent for the initial RED")
    spec = importlib.util.spec_from_file_location("native_browser_fixture", FIXTURE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_protocol_response_has_balanced_tool_stream(api):
    _, raw = api.answer([{"type": "tool_use", "id": "one", "name": "fixture", "input": {}}], "fixture", stream=True)
    events = [json.loads(x[6:]) for x in raw.decode().splitlines() if x.startswith("data: ")]
    assert events[0]["type"] == "message_start"
    assert events[-1]["type"] == "message_stop"


def test_result_must_match_the_emitted_tool_id(api):
    messages = [{"role": "user", "content": [{"type": "tool_result", "tool_use_id": "wrong", "content": "done"}]}]
    assert api.tool_result(messages, "expected") is None


def test_duplicate_result_identity_refused(api):
    result = {"type": "tool_result", "tool_use_id": "one", "content": "done"}
    with pytest.raises(ValueError, match="duplicate"):
        api.tool_result([{"role": "user", "content": [result, result]}], "one")


def test_environment_has_no_ambient_provider_credentials(api, monkeypatch, tmp_path):
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "DO-NOT-INHERIT")
    monkeypatch.setenv("HTTP_PROXY", "http://not-the-fixture.invalid")
    env = api.fixture_environment(tmp_path, 12345)
    assert env["ANTHROPIC_API_KEY"] == "fixture-not-a-real-key"
    assert env["ANTHROPIC_BASE_URL"] == "http://127.0.0.1:12345"
    assert "CLAUDE_CODE_OAUTH_TOKEN" not in env and "HTTP_PROXY" not in env


def test_image_receipts_reject_non_images(api):
    assert api.image_receipts({"content": [{"type": "text", "text": "pretend screenshot"}]}) == []


def test_denied_control_can_request_the_deliberately_absent_tool(api):
    oracle = api.Oracle("denied", "http://127.0.0.1:12345", "nonce", "value")
    oracle.stage = 1
    request = {"tools": [{"name": "mcp__fixtureBrowser__browser_navigate"}], "messages": [
        {"role": "user", "content": api.ROOT_MARKER},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "toolu_browser_0", "content": "ready"}]},
    ]}
    blocks = oracle.respond(request)
    assert blocks[0]["name"] == "mcp__fixtureBrowser__browser_fill_form"
    assert oracle.submission is None


def test_error_marked_native_result_is_not_accepted(api):
    assert hasattr(api, "native_result_matches"), "Final native result is not validated"
    assert not api.native_result_matches({"is_error": True, "result": "EXPECTED"}, "EXPECTED")


def test_wrong_native_result_cannot_be_success(api):
    assert hasattr(api, "native_result_matches"), "Final native result is not validated"
    assert not api.native_result_matches({"is_error": False, "result": "wrong"}, "EXPECTED")
    assert api.native_result_matches({"is_error": False, "result": "EXPECTED"}, "EXPECTED")


def test_sdk_fixture_options_preserve_the_real_projection(api, tmp_path):
    assert hasattr(api, "sdk_fixture_options"), "SDK config has no native consumer"
    config = {"mcp_servers": {}, "allowed_tools": [], "strict_mcp_config": True}
    options = api.sdk_fixture_options(config, Path("/exact/claude"), tmp_path)
    assert all(options[k] == v for k, v in config.items())
    assert options["cli_path"] == "/exact/claude"
    assert options["setting_sources"] == [] and options["tools"] == []
    assert options["permission_mode"] == "dontAsk"
    assert options["extra_args"] == {"bare": None, "no-chrome": None, "no-session-persistence": None}


def test_sdk_fixture_refuses_non_strict_projection(api, tmp_path):
    assert hasattr(api, "sdk_fixture_options"), "SDK config has no native consumer"
    with pytest.raises(ValueError, match="strict"):
        api.sdk_fixture_options({"mcp_servers": {}, "allowed_tools": []}, Path("/exact/claude"), tmp_path)


@pytest.mark.parametrize("case", ["child-denied", "child-generated-deny", "child-explicit-deny"])
def test_child_denial_is_consumed_on_exact_parent_result(api, case):
    oracle = api.Oracle(case, "http://127.0.0.1:12345", "nonce", "value")
    oracle.parent_started = True
    oracle.denied = True
    request = {"tools": [{"name": "Agent"}], "messages": [
        {"role": "user", "content": api.ROOT_MARKER},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "toolu_browser_child",
          "content": "EXPECTED_BROWSER_PERMISSION_DENIAL:nonce"}]},
    ]}
    blocks = oracle.respond(request)
    assert oracle.parent_consumed is True
    assert blocks[0]["text"] == "PARENT_CONSUMED:nonce"


@pytest.mark.parametrize("case", ["child-denied", "child-generated-deny", "child-explicit-deny"])
def test_child_denial_cannot_consume_an_error_result(api, case):
    oracle = api.Oracle(case, "http://127.0.0.1:12345", "nonce", "value")
    oracle.parent_started = True
    oracle.denied = True
    request = {"tools": [{"name": "Agent"}], "messages": [
        {"role": "user", "content": api.ROOT_MARKER},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "toolu_browser_child",
          "is_error": True, "content": "EXPECTED_BROWSER_PERMISSION_DENIAL:nonce"}]},
    ]}
    oracle.respond(request)
    assert oracle.parent_consumed is False
