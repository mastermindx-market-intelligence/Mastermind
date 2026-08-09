"""Tests for the Claude Code reasoning bridge.

Pure-logic tests always run. A real round-trip is opt-in (BOT_TEST_LIVE_LLM=1) so the
default suite never spends subscription tokens.
"""
import os
from pathlib import Path

import pytest
import yaml

import bot  # noqa: F401

from brain import cli_bridge, client


def test_model_tier_routing():
    # the in-house policy: Opus=deep, Sonnet=medium/code, Haiku=high-volume
    assert cli_bridge.resolve_model("pm") == "opus"
    assert cli_bridge.resolve_model("deep") == "opus"
    assert cli_bridge.resolve_model("analyst") == "sonnet"
    assert cli_bridge.resolve_model("scout") == "haiku"
    assert cli_bridge.resolve_model("fable") == "fable"
    # explicit model wins over role
    assert cli_bridge.resolve_model("scout", model="claude-opus-4-8") == "claude-opus-4-8"


def test_deep_role_same_model_family_both_backends():
    """CLI and API backends must resolve role='deep' to the same model family.

    The CLI backend reads config/agents.yml roles.deep → 'opus' (a tier label);
    the API backend uses brain/client.py TIERS['deep']['model'] (a concrete API id).
    Both must target the opus family so a CLI-bridge dropout does not silently promote
    all five Brain books to Fable tokens.
    """
    cli_tier = cli_bridge.resolve_model("deep")        # reads config/agents.yml → 'opus'
    api_model = client.TIERS["deep"]["model"]          # reads brain/client.py TIERS dict
    # The CLI tier label 'opus' must appear somewhere in the API model id (e.g. 'claude-opus-4-8').
    # A mismatch here means one backend runs a different tier than the other.
    assert "opus" in cli_tier, f"CLI backend resolves 'deep' to '{cli_tier}', expected opus tier"
    assert "opus" in api_model, (
        f"API backend TIERS['deep'] model is '{api_model}', expected opus family; "
        "if this regresses the CLI bridge drops to Fable on all five Brain books"
    )


def test_backend_resolution(monkeypatch):
    monkeypatch.delenv("BOT_LLM_BACKEND", raising=False)
    assert client.backend() == "waterfall"                # authoritative checked-in policy
    monkeypatch.setenv("BOT_LLM_BACKEND", "api")
    assert client.backend() == "api"


def test_missing_or_malformed_config_fails_to_shared_waterfall(monkeypatch):
    from brain import provider_waterfall

    monkeypatch.delenv("BOT_LLM_BACKEND", raising=False)
    monkeypatch.setattr(cli_bridge, "_cfg", lambda: {})
    monkeypatch.setattr(provider_waterfall, "available", lambda: True)
    assert client.backend() == "waterfall"
    assert cli_bridge.available() is True

    def broken_config():
        raise ValueError("malformed")

    monkeypatch.setattr(cli_bridge, "_cfg", broken_config)
    assert client.backend() == "waterfall"
    assert cli_bridge.available() is True


def test_health_exposes_effective_reasoning_policy(monkeypatch):
    from app import main
    from brain import codex_bridge

    monkeypatch.delenv("BOT_LLM_BACKEND", raising=False)
    monkeypatch.setattr(client, "available", lambda: True)
    monkeypatch.setattr(codex_bridge, "available", lambda: True)
    health = main.health()

    assert health["reasoning_backend"] == "waterfall"
    assert health["reasoning_policy"] == "codex_first_claude_oauth_fallback"
    assert health["reasoning_policy_ok"] is True
    assert health["shared_reasoning_available"] is True
    assert health["codex_available"] is True
    assert health["reasoning_primary"] == "codex"
    assert health["reasoning_policy_scope"] == "scheduled_portfolio_reasoning"
    assert health["scheduled_portfolio_reasoning_backend"] == "waterfall"
    assert health["scheduled_portfolio_reasoning_policy"] == "codex_first_claude_oauth_fallback"
    assert health["scheduled_portfolio_reasoning_policy_ok"] is True
    assert health["scheduled_portfolio_reasoning_available"] is True
    assert health["advisor_chat_backend"] == "claude_agent_sdk"
    assert health["advisor_chat_uses_scheduled_reasoning_waterfall"] is False


def test_shared_waterfall_outage_never_uses_direct_api(monkeypatch):
    """Scheduled reasoning must not escape into a separate metered credential island."""
    monkeypatch.setenv("BOT_LLM_BACKEND", "waterfall")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-fake")
    monkeypatch.setattr(cli_bridge, "available", lambda: False)
    monkeypatch.setattr(client, "api_available", lambda: True)

    class ForbiddenAnthropic:
        def __init__(self, *args, **kwargs):
            raise AssertionError("direct Anthropic client must not be constructed")

    import anthropic

    monkeypatch.setattr(anthropic, "Anthropic", ForbiddenAnthropic)
    text, reason = client.call_model("system", "user", role="pm")

    assert text is None
    assert reason == "provider_waterfall_unavailable"


def test_health_fails_policy_when_shared_waterfall_unavailable(monkeypatch):
    from app import main
    from brain import codex_bridge

    monkeypatch.setenv("BOT_LLM_BACKEND", "waterfall")
    monkeypatch.setattr(client, "available", lambda: False)
    # Binary/auth availability alone is not an operational shared waterfall.
    monkeypatch.setattr(codex_bridge, "available", lambda: True)

    health = main.health()

    assert health["reasoning_backend"] == "waterfall"
    assert health["shared_reasoning_available"] is False
    assert health["reasoning_policy_ok"] is False
    assert health["scheduled_portfolio_reasoning_available"] is False
    assert health["scheduled_portfolio_reasoning_policy_ok"] is False
    assert health["codex_available"] is True
    assert health["reasoning_primary"] == "unavailable"


def test_config_has_readonly_tools():
    rc = cli_bridge._cfg()["reasoning"]
    assert "Read" in rc["allowed_tools"]
    assert not (set(rc["allowed_tools"]) & {"Write", "Edit", "Bash"})   # read-only reasoning layer


def test_claude_portfolio_delegation_falls_back_to_single_root_pm():
    from brain import autonomous_mcp

    original_servers = autonomous_mcp.build_servers()
    tools, servers, error = cli_bridge._claude_delegation_surface(
        autonomous_mcp.allowed_tools(),
        original_servers,
        "autonomous",
    )

    assert error is None
    assert "Task" not in tools
    assert not any(tool.startswith("Task(") for tool in tools)
    assert servers is original_servers
    assert set(servers) == {"bot", "desk"}
    assert "mcp__desk__submit_book" in tools

    _, _, wrong_book = cli_bridge._claude_delegation_surface(
        autonomous_mcp.allowed_tools(),
        autonomous_mcp.build_servers(),
        "hk",
    )
    _, _, missing_book = cli_bridge._claude_delegation_surface(
        autonomous_mcp.allowed_tools(),
        autonomous_mcp.build_servers(),
        None,
    )
    assert "reviewed MCP servers" in wrong_book
    assert "explicit active portfolio" in missing_book


def test_claude_child_profiles_have_no_raw_cross_book_or_runtime_file_tools():
    profiles_dir = Path(cli_bridge._ROOT) / ".claude" / "agents"
    for name in cli_bridge._CLAUDE_AGENT_NAMES:
        raw = (profiles_dir / f"{name}.md").read_text(encoding="utf-8")
        frontmatter = yaml.safe_load(raw.split("---", 2)[1])
        tools = set(frontmatter["tools"])
        assert tools
        assert all(tool.startswith("mcp__research__") for tool in tools)
        assert not (tools & {"Read", "Grep", "Glob", "Bash", "Write", "Edit"})
        assert "mcp__research__submit_book" not in tools
        assert "mcp__research__request_context_upgrade" not in tools

    from brain.codex_mcp_stdio import research_tool_names
    us = set(research_tool_names("autonomous"))
    china = set(research_tool_names("china"))
    hk = set(research_tool_names("hk"))
    assert "get_prophet_board" in us
    assert "get_prophet_board" not in china | hk
    assert "get_china_intake" not in us
    assert "get_china_intake" in china & hk


def test_research_signal_reader_allows_published_contract_but_denies_env_file():
    import asyncio

    from brain import autonomous_mcp

    reader = next(tool for tool in autonomous_mcp._READ_TOOLS if tool.name == "read_signal")
    allowed = asyncio.run(reader.handler({"path": "vendor/macro/site/china_brief.json"}))
    denied = asyncio.run(reader.handler({"path": ".env"}))
    allowed_text = allowed["content"][0]["text"]
    denied_text = denied["content"][0]["text"]
    assert '"schema"' in allowed_text
    assert "DENIED: path outside the allowed data roots" in denied_text


def test_reason_graceful_without_cli(monkeypatch):
    # if the CLI binary isn't found, reason() returns a structured failure, never raises
    monkeypatch.setenv("BOT_LLM_BACKEND", "cli")
    monkeypatch.setattr(cli_bridge, "cli_path", lambda: None)
    import asyncio
    out = asyncio.run(cli_bridge.reason("hi", role="scout"))
    assert out["ok"] is False and out["backend"] == "none" and out["model"] == "haiku"


@pytest.mark.skipif(not os.environ.get("BOT_TEST_LIVE_LLM"), reason="set BOT_TEST_LIVE_LLM=1 for a real round-trip")
def test_live_round_trip():
    assert cli_bridge.available()
    out = cli_bridge.reason_sync("Reply with exactly: PONG", role="scout", max_turns=1)
    assert out["ok"] and "PONG" in (out["text"] or "")
