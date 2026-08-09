from __future__ import annotations

import asyncio
import json
import tomllib
from pathlib import Path

import pytest


def test_codex_role_mapping_is_sol_xhigh():
    from brain import codex_bridge

    for role in ("pm", "deep", "analyst", "scout", "fable"):
        assert codex_bridge.resolve_model(role) == ("gpt-5.6-sol", "xhigh")


def test_codex_jsonl_contract_parser():
    from brain.codex_bridge import _parse_jsonl

    raw = "\n".join([
        json.dumps({"type": "thread.started", "thread_id": "thread-1"}),
        json.dumps({
            "type": "item.completed",
            "item": {"type": "mcp_tool_call", "tool": "submit_book"},
        }),
        json.dumps({
            "type": "item.completed",
            "item": {"type": "agent_message", "text": "done"},
        }),
        json.dumps({
            "type": "turn.completed",
            "usage": {"input_tokens": 12, "output_tokens": 3},
        }),
    ])
    parsed = _parse_jsonl(raw)
    assert parsed["text"] == "done"
    assert parsed["session_id"] == "thread-1"
    assert parsed["tools_used"] == ["submit_book"]
    assert parsed["usage"]["input_tokens"] == 12
    assert parsed["error"] is None


def test_codex_response_ledger_provider_attribution():
    from brain import thinking_log

    row = thinking_log.build_row(
        question="q",
        answer="a",
        model="gpt-5.6-sol",
        backend="codex",
    )
    assert row["provider"] == "openai_codex"


def test_mcp_overrides_rebuild_only_authorized_server_names():
    from brain.codex_bridge import _mcp_overrides

    args = _mcp_overrides(
        {"bot": {"type": "sdk"}, "desk": {"type": "sdk"}},
        allowed_tools=["mcp__desk__get_my_book", "mcp__bot__get_regime"],
        book="autonomous",
        python="/venv/bin/python",
    )
    rendered = " ".join(args)
    assert "mcp_servers.bot.command" in rendered
    assert "mcp_servers.desk.command" in rendered
    assert "brain.codex_mcp_stdio" in rendered
    assert "autonomous" in rendered
    assert 'default_tools_approval_mode="approve"' in rendered
    assert 'mcp_servers.bot.enabled_tools=["get_regime"]' in rendered
    assert 'mcp_servers.desk.enabled_tools=["get_my_book"]' in rendered


def test_mcp_overrides_omit_unlisted_and_empty_surfaces():
    from brain.codex_bridge import _mcp_overrides

    only_desk = _mcp_overrides(
        {"bot": {}, "desk": {}},
        allowed_tools=["mcp__desk__get_my_book"],
        book="autonomous",
        python="python",
    )
    rendered = " ".join(only_desk)
    assert "mcp_servers.desk.command" in rendered
    assert "mcp_servers.bot.command" not in rendered
    assert _mcp_overrides(
        {"desk": {}}, allowed_tools=[], book="system", python="python"
    ) == []


def test_reason_enforces_bounded_tools_secret_env_and_prompt_only_profile(
    tmp_path, monkeypatch, caplog
):
    from brain import codex_bridge

    calls: list[dict] = []

    class FakeProcess:
        returncode = 0

        async def communicate(self, payload):
            raw = "\n".join([
                json.dumps({"type": "thread.started", "thread_id": "t1"}),
                json.dumps({
                    "type": "item.completed",
                    "item": {"type": "agent_message", "text": "done"},
                }),
                json.dumps({"type": "turn.completed", "usage": {}}),
            ])
            return raw.encode(), b""

    async def fake_exec(*argv, **kwargs):
        env = dict(kwargs.get("env") or {})
        secret_path = env.get("MASTERMIND_CODEX_MCP_SECRET_FILE")
        calls.append({
            "argv": list(argv),
            "env": env,
            "mcp_secret_bundle": (
                json.loads(Path(secret_path).read_text(encoding="utf-8"))
                if secret_path else None
            ),
            "mcp_secret_mode": (
                Path(secret_path).stat().st_mode & 0o777 if secret_path else None
            ),
        })
        return FakeProcess()

    monkeypatch.setattr(codex_bridge, "codex_path", lambda: "/usr/bin/codex")
    monkeypatch.setattr(codex_bridge, "available", lambda: True)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    monkeypatch.setenv("MASTERMIND_CODEX_WEB_SEARCH", "1")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "must-not-cross")
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN_3", "must-not-cross")
    monkeypatch.setenv("POLYGON_API_KEY", "read-vendor-canary")
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    # A machine-global MCP must be invisible to the portfolio invocation.  Codex retains auth from
    # CODEX_HOME while --ignore-user-config prevents this server from entering the effective map.
    (codex_home / "config.toml").write_text(
        '[mcp_servers.evil]\ncommand = "steal-secrets"\n', encoding="utf-8"
    )
    monkeypatch.setenv("CODEX_HOME", str(codex_home))

    typed = asyncio.run(codex_bridge.reason(
        "research",
        allowed_tools=["mcp__desk__get_my_book", "WebSearch"],
        mcp_servers={"desk": {}, "bot": {}},
        book="autonomous",
    ))
    prompt_only = asyncio.run(codex_bridge.reason(
        "bounded counts",
        allowed_tools=[],
        mcp_servers={"desk": {}},
        book="system",
    ))

    assert typed["ok"] and prompt_only["ok"]
    typed_argv = " ".join(calls[0]["argv"])
    assert "--ephemeral" in calls[0]["argv"]
    assert "agents.enabled=false" in typed_argv
    assert "--ignore-user-config" in calls[0]["argv"]
    assert calls[0]["argv"].count("--disable") == 7
    assert "shell_tool" in calls[0]["argv"] and "unified_exec" in calls[0]["argv"]
    assert 'shell_environment_policy.inherit="core"' in typed_argv
    assert "shell_environment_policy.ignore_default_excludes=false" in typed_argv
    assert 'default_permissions="mastermind_typed_reasoning"' in typed_argv
    assert "projects={" in typed_argv and "trust_level" in typed_argv
    assert 'mcp_servers.desk.enabled_tools=["get_my_book"]' in typed_argv
    assert "mcp_servers.bot.command" not in typed_argv
    assert 'web_search="live"' in typed_argv
    assert calls[0]["env"]["CODEX_HOME"] == str(codex_home)
    assert "steal-secrets" not in typed_argv and "mcp_servers.evil" not in typed_argv
    assert "ANTHROPIC_API_KEY" not in calls[0]["env"]
    assert "CLAUDE_CODE_OAUTH_TOKEN_3" not in calls[0]["env"]
    assert "POLYGON_API_KEY" not in calls[0]["env"]
    assert "read-vendor-canary" not in typed_argv
    assert calls[0]["mcp_secret_bundle"] == {"POLYGON_API_KEY": "read-vendor-canary"}
    assert calls[0]["mcp_secret_mode"] == 0o600
    assert "read-vendor-canary" not in caplog.text

    prompt_argv = " ".join(calls[1]["argv"])
    assert 'default_permissions="mastermind_prompt_only"' in prompt_argv
    assert calls[1]["argv"].count("--disable") == 7
    assert 'web_search="disabled"' in prompt_argv
    assert "mcp_servers.desk.command" not in prompt_argv
    prompt_cwd = calls[1]["argv"][calls[1]["argv"].index("-C") + 1]
    assert Path(prompt_cwd) != Path(codex_bridge._ROOT)


def test_portfolio_delegation_separates_persisted_research_from_sealed_submission(
    monkeypatch,
):
    from brain import codex_bridge

    calls: list[dict] = []

    class FakeProcess:
        def __init__(self, phase: int):
            self.phase = phase

        returncode = 0

        async def communicate(self, payload):
            if self.phase == 0:
                thread_id = "t-research"
                message = "proposed governed book"
                tool = "mcp__research__get_regime"
                usage = {"input_tokens": 11, "output_tokens": 5}
            else:
                thread_id = "t-submit"
                message = "submitted governed book"
                tool = "mcp__desk__submit_book"
                usage = {"input_tokens": 7, "output_tokens": 3}
            return ("\n".join([
                json.dumps({"type": "thread.started", "thread_id": thread_id}),
                json.dumps({
                    "type": "item.completed",
                    "item": {"type": "mcp_tool_call", "tool": tool},
                }),
                json.dumps({
                    "type": "item.completed",
                    "item": {"type": "agent_message", "text": message},
                }),
                json.dumps({"type": "turn.completed", "usage": usage}),
            ]).encode(), b"")

    async def fake_exec(*argv, **kwargs):
        phase = len(calls)
        calls.append({
            "argv": list(argv),
            "env": dict(kwargs.get("env") or {}),
        })
        return FakeProcess(phase)

    monkeypatch.setattr(codex_bridge, "codex_path", lambda: "/usr/bin/codex")
    monkeypatch.setattr(codex_bridge, "available", lambda: True)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)

    out = asyncio.run(codex_bridge.reason(
        "delegate one read-only check",
        role="deep",
        allowed_tools=[
            "mcp__bot__get_regime",
            "mcp__desk__get_my_book",
            "mcp__desk__submit_book",
            "Task",
        ],
        mcp_servers={"bot": {}, "desk": {}},
        book="autonomous",
    ))

    assert out["ok"] is True
    assert out["session_id"] == "t-submit"
    assert out["research_session_id"] == "t-research"
    assert out["delegated_research_completed"] is True
    assert out["research_tools_used"] == ["mcp__research__get_regime"]
    assert out["tools_used"] == ["mcp__desk__submit_book"]
    assert out["usage"] == {"input_tokens": 18, "output_tokens": 8}
    assert len(calls) == 2

    research_argv = calls[0]["argv"]
    research = " ".join(research_argv)
    assert "--ephemeral" not in research_argv
    assert "agents.enabled=true" in research
    assert "agents.max_concurrent_threads_per_session=3" in research
    assert "mcp_servers.research.command=" in research
    assert "mcp_servers.research.enabled_tools=" in research
    assert 'mcp_servers.bot.command="/usr/bin/false"' in research
    assert 'mcp_servers.desk.command="/usr/bin/false"' in research
    assert 'mcp_servers.bot.args=' not in research
    assert 'mcp_servers.desk.args=' not in research
    assert "submit_book" not in research
    assert calls[0]["env"]["MASTERMIND_CODEX_BOOK"] == "autonomous"
    # Agent layers mention certified market servers, so absent transports are inert placeholders.
    for server in ("bot", "desk", "china", "hk"):
        assert f"mcp_servers.{server}.enabled=false" in research
    assert research_argv.count("--disable") == 7

    submission_argv = calls[1]["argv"]
    submission = " ".join(submission_argv)
    assert "--ephemeral" in submission_argv
    assert "agents.enabled=false" in submission
    assert "agents.enabled=true" not in submission
    assert "mcp_servers.research.command=" not in submission
    assert 'mcp_servers.bot.enabled_tools=["get_regime"]' in submission
    assert 'mcp_servers.desk.enabled_tools=["get_my_book", "submit_book"]' in submission
    assert "mcp_servers.china.command=" not in submission
    assert "mcp_servers.hk.command=" not in submission
    assert submission_argv.count("--disable") == 7


@pytest.mark.parametrize(
    ("book", "servers", "tools", "submit_tool", "server"),
    [
        (
            "autonomous",
            {"bot": {}, "desk": {}},
            ["mcp__bot__get_regime", "mcp__desk__get_my_book", "mcp__desk__submit_book", "Task"],
            "mcp__desk__submit_book",
            "desk",
        ),
        (
            "china",
            {"china": {}},
            ["mcp__china__get_my_book", "mcp__china__submit_book", "Task"],
            "mcp__china__submit_book",
            "china",
        ),
        (
            "hk",
            {"hk": {}},
            ["mcp__hk__get_my_book", "mcp__hk__submit_book", "Task"],
            "mcp__hk__submit_book",
            "hk",
        ),
    ],
)
def test_each_active_book_restores_its_submit_surface_only_after_research(
    book, servers, tools, submit_tool, server, monkeypatch,
):
    from brain import codex_bridge

    calls: list[list[str]] = []

    class FakeProcess:
        returncode = 0

        def __init__(self, phase: int):
            self.phase = phase

        async def communicate(self, payload):
            tool = "mcp__research__get_my_book" if self.phase == 0 else submit_tool
            message = "read-only artifact" if self.phase == 0 else "submitted"
            return ("\n".join([
                json.dumps({"type": "thread.started", "thread_id": f"{book}-{self.phase}"}),
                json.dumps({
                    "type": "item.completed",
                    "item": {"type": "mcp_tool_call", "tool": tool},
                }),
                json.dumps({
                    "type": "item.completed",
                    "item": {"type": "agent_message", "text": message},
                }),
                json.dumps({"type": "turn.completed", "usage": {}}),
            ]).encode(), b"")

    async def fake_exec(*argv, **kwargs):
        phase = len(calls)
        calls.append(list(argv))
        return FakeProcess(phase)

    monkeypatch.setattr(codex_bridge, "codex_path", lambda: "/usr/bin/codex")
    monkeypatch.setattr(codex_bridge, "available", lambda: True)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)

    out = asyncio.run(codex_bridge.reason(
        f"govern {book}",
        allowed_tools=tools,
        mcp_servers=servers,
        book=book,
    ))

    assert out["ok"] is True
    assert out["tools_used"] == [submit_tool]
    assert len(calls) == 2
    research = " ".join(calls[0])
    submission = " ".join(calls[1])
    assert "--ephemeral" not in calls[0]
    assert "mcp_servers.research.command=" in research
    assert "submit_book" not in research
    assert 'web_search="disabled"' in research
    assert "--ephemeral" in calls[1]
    assert "agents.enabled=false" in submission
    assert f"mcp_servers.{server}.command=" in submission
    assert f'mcp_servers.{server}.enabled_tools=' in submission
    assert submit_tool.split("__")[-1] in submission


@pytest.mark.parametrize("submit_calls", [0, 2])
def test_sealed_phase_fails_closed_without_exactly_one_submit(submit_calls, monkeypatch):
    from brain import codex_bridge

    phase = 0

    class FakeProcess:
        returncode = 0

        def __init__(self, current: int):
            self.current = current

        async def communicate(self, payload):
            items = []
            if self.current:
                items.extend(
                    json.dumps({
                        "type": "item.completed",
                        "item": {"type": "mcp_tool_call", "tool": "mcp__desk__submit_book"},
                    })
                    for _ in range(submit_calls)
                )
            items.extend([
                json.dumps({"type": "thread.started", "thread_id": f"t-{self.current}"}),
                json.dumps({
                    "type": "item.completed",
                    "item": {"type": "agent_message", "text": "artifact"},
                }),
            ])
            return "\n".join(items).encode(), b""

    async def fake_exec(*argv, **kwargs):
        nonlocal phase
        current = phase
        phase += 1
        return FakeProcess(current)

    monkeypatch.setattr(codex_bridge, "codex_path", lambda: "/usr/bin/codex")
    monkeypatch.setattr(codex_bridge, "available", lambda: True)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)

    out = asyncio.run(codex_bridge.reason(
        "govern autonomous",
        allowed_tools=["mcp__desk__get_my_book", "mcp__desk__submit_book", "Task"],
        mcp_servers={"bot": {}, "desk": {}},
        book="autonomous",
    ))

    assert out["ok"] is False
    assert f"observed {submit_calls} call(s)" in out["error"]


def test_delegation_refuses_unknown_or_unclassified_mcp_authority(monkeypatch):
    from brain import codex_bridge

    async def must_not_exec(*argv, **kwargs):
        raise AssertionError("unsafe delegated invocation must fail before subprocess launch")

    monkeypatch.setattr(codex_bridge, "codex_path", lambda: "/usr/bin/codex")
    monkeypatch.setattr(codex_bridge, "available", lambda: True)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", must_not_exec)

    unknown = asyncio.run(codex_bridge.reason(
        "delegate",
        allowed_tools=["mcp__evil__submit_book", "Task"],
        mcp_servers={"evil": {}},
        book="autonomous",
    ))
    unclassified = asyncio.run(codex_bridge.reason(
        "delegate",
        allowed_tools=["mcp__desk__new_write_surface", "Task"],
        mcp_servers={"bot": {}, "desk": {}},
        book="autonomous",
    ))

    assert unknown["ok"] is False
    assert "uncertified MCP server" in unknown["error"]
    assert unclassified["ok"] is False
    assert "unclassified MCP tool" in unclassified["error"]


def test_every_codex_agent_layer_denies_parent_portfolio_writes():
    from brain import codex_bridge

    agents_dir = codex_bridge._ROOT / ".codex" / "agents"
    profiles = {}
    for path in agents_dir.glob("*.toml"):
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        profiles[data["name"]] = data

    assert codex_bridge._DELEGATION_AGENT_NAMES <= profiles.keys()
    for name in codex_bridge._DELEGATION_AGENT_NAMES:
        assert profiles[name]["sandbox_mode"] == "read-only"
        servers = profiles[name]["mcp_servers"]
        for server, denied in codex_bridge._DELEGATION_DENIED_TOOLS.items():
            actual = set(servers[server]["disabled_tools"])
            assert denied <= actual
            # Codex applies disabled_tools after the parent's enabled_tools. Therefore every
            # certified write is absent while the parent-selected read list remains unchanged.
            parent_enabled = codex_bridge._DELEGATION_READ_TOOLS[server] | denied
            effective_child = parent_enabled - actual
            assert not (effective_child & denied)
            assert codex_bridge._DELEGATION_READ_TOOLS[server] <= effective_child
        research = servers["research"]
        assert research["command"] == "sh"
        assert research["args"] == [
            "-c", 'exec "$MASTERMIND_CODEX_PYTHON" -m brain.codex_mcp_stdio '
            "--book-env MASTERMIND_CODEX_BOOK --server research",
        ]
        expected_reads = set().union(*codex_bridge._DELEGATION_READ_TOOLS.values())
        assert set(research["enabled_tools"]) == expected_reads
        assert not (
            set(research["enabled_tools"])
            & set().union(*codex_bridge._DELEGATION_DENIED_TOOLS.values())
        )


def test_explicit_raw_read_surface_keeps_readonly_shell_profile(monkeypatch):
    """Generic code-analysis calls may opt into raw reads; typed portfolio PMs may not."""
    from brain import codex_bridge

    calls: list[list[str]] = []

    class FakeProcess:
        returncode = 0

        async def communicate(self, payload):
            return ("\n".join([
                json.dumps({"type": "thread.started", "thread_id": "t-read"}),
                json.dumps({
                    "type": "item.completed",
                    "item": {"type": "agent_message", "text": "done"},
                }),
            ]).encode(), b"")

    async def fake_exec(*argv, **kwargs):
        calls.append(list(argv))
        return FakeProcess()

    monkeypatch.setattr(codex_bridge, "codex_path", lambda: "/usr/bin/codex")
    monkeypatch.setattr(codex_bridge, "available", lambda: True)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)

    out = asyncio.run(codex_bridge.reason("inspect contract", allowed_tools=["Read", "Grep"]))

    assert out["ok"] is True
    rendered = " ".join(calls[0])
    assert 'default_permissions="mastermind_reasoning"' in rendered
    assert "--disable" not in calls[0]


def test_codex_mcp_surface_matches_existing_book_surface():
    from brain.codex_mcp_stdio import server_instance

    bot = server_instance("autonomous", "bot")
    desk = server_instance("autonomous", "desk")
    assert bot.create_initialization_options().server_name == "bot"
    assert desk.create_initialization_options().server_name == "desk"


def test_codex_research_mcp_is_active_book_only_and_read_only():
    import pytest

    from brain.codex_mcp_stdio import server_instance

    research = server_instance("autonomous", "research")
    assert research.create_initialization_options().server_name == "research"
    with pytest.raises(SystemExit, match="explicit active portfolio"):
        server_instance("system", "research")


def test_codex_mcp_secret_loader_accepts_only_owner_only_read_vendor_bundle(
    tmp_path, monkeypatch,
):
    from brain import codex_mcp_stdio

    monkeypatch.delenv("POLYGON_API_KEY", raising=False)
    good = tmp_path / "good.json"
    good.write_text(json.dumps({"POLYGON_API_KEY": "local-reader"}), encoding="utf-8")
    good.chmod(0o600)
    assert codex_mcp_stdio._load_secret_env(str(good)) == {"POLYGON_API_KEY"}
    assert codex_mcp_stdio.os.environ["POLYGON_API_KEY"] == "local-reader"

    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"ANTHROPIC_API_KEY": "must-stay-out"}), encoding="utf-8")
    bad.chmod(0o600)
    assert codex_mcp_stdio._load_secret_env(str(bad)) == set()
    assert codex_mcp_stdio.os.environ.get("ANTHROPIC_API_KEY") != "must-stay-out"


def test_codex_available_requires_cli_and_auth(tmp_path, monkeypatch):
    from brain import codex_bridge

    monkeypatch.setenv("CODEX_HOME", str(tmp_path))
    monkeypatch.setattr(codex_bridge.shutil, "which", lambda name: "/usr/bin/codex")
    assert not codex_bridge.available()
    (tmp_path / "auth.json").write_text("{}")
    assert codex_bridge.available()


def test_external_macro_plane_skips_git_refresh(monkeypatch):
    from data_layer import macro_refresh

    monkeypatch.setenv("MASTERMIND_MACRO_MANAGED_EXTERNALLY", "1")
    monkeypatch.setattr(
        macro_refresh,
        "refresh",
        lambda log=print: (_ for _ in ()).throw(AssertionError("must not refresh")),
    )
    monkeypatch.setattr(
        macro_refresh,
        "check_and_warn",
        lambda block=False, log=print: {"asof": "2026-07-29", "freeze": False},
    )
    out = macro_refresh.refresh_and_check(log=lambda _: None)
    assert out["asof"] == "2026-07-29"
    assert out["refreshed_to"] is None
