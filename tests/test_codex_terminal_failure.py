"""Explicit Codex terminal failure is never success or permission to replay.

Transport, availability and credential materialization are synthetic. The adapter,
provider waterfall classifier and retained-submission consumer remain their real owners.
"""
from __future__ import annotations

import asyncio
import json

import pytest


def _message(text):
    return {"type": "item.completed", "item": {"type": "agent_message", "text": text}}


def _submit(status="completed", error=None):
    return {"type": "item.completed", "item": {
        "type": "mcp_tool_call", "tool": "mcp__desk__submit_book",
        "status": status, "error": error,
    }}


def _failure(error=None):
    row = {"type": "turn.failed"}
    if error is not None:
        row["error"] = error
    return row


def _fake_codex(monkeypatch, plans, *, returncodes=None, stderr=b"synthetic stderr"):
    from brain import codex_bridge

    launches = []
    codes = list(returncodes) if returncodes is not None else [0] * len(plans)

    class FakeProcess:
        def __init__(self, index):
            self.index = index
            self.returncode = codes[index]

        async def communicate(self, payload):
            rows = [{"type": "thread.started", "thread_id": f"synthetic-{self.index}"}]
            for row in plans[self.index]:
                if callable(row):
                    row()
                else:
                    rows.append(row)
            return "\n".join(json.dumps(row) for row in rows).encode(), stderr

    async def fake_exec(*argv, **kwargs):
        assert argv[0] == "/synthetic/codex", "Unexpected transport entry"
        index = len(launches)
        assert index < len(plans), "Unexpected extra provider launch"
        launches.append(list(argv))
        return FakeProcess(index)

    monkeypatch.setattr(codex_bridge, "codex_path", lambda: "/synthetic/codex")
    monkeypatch.setattr(codex_bridge, "available", lambda: True)
    monkeypatch.setattr(codex_bridge, "_subprocess_env", lambda: {})
    monkeypatch.setattr(codex_bridge, "_mcp_secret_bundle", lambda: (None, None))
    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    return launches


@pytest.mark.parametrize("returncode,text,diagnostic,later_success", [
    pytest.param(0, "Retained answer", {"message": "401 OAuth access token revoked"}, False,
                 id="zero-exit-with-text"),
    pytest.param(0, "Retained answer", None, True, id="no-diagnostic-then-success"),
    pytest.param(0, None, "429 usage limit reached", False, id="zero-exit-without-text"),
    pytest.param(1, "Retained answer", "access token could not be refreshed", False,
                 id="nonzero-exit-with-text"),
    pytest.param(1, None, None, False, id="nonzero-exit-stderr-evidence"),
])
def test_terminal_failure_cannot_be_green_or_expose_retry_diagnostics(
    monkeypatch, returncode, text, diagnostic, later_success,
):
    from brain import codex_bridge

    rows = [_submit()]
    if text is not None:
        rows.append(_message(text))
    rows.append(_failure(diagnostic))
    if later_success:
        rows += [
            _message("Later answer"),
            {"type": "turn.completed", "usage": {"input_tokens": 4, "output_tokens": 2}},
        ]
    launches = _fake_codex(monkeypatch, [rows], returncodes=[returncode])
    result = asyncio.run(codex_bridge.reason("Synthetic terminal boundary", allowed_tools=[]))

    assert result["ok"] is False
    assert result["error"] == "codex_terminal_error"
    expected_detail = str(diagnostic) if diagnostic is not None else (
        "synthetic stderr" if returncode else None
    )
    assert result["terminal_error_detail"] == expected_detail
    assert result["text"] == ("Later answer" if later_success else text)
    assert result["tools_used"] == ["mcp__desk__submit_book"]
    assert result["failed_write_tools"] == []
    assert result["usage"] == ({"input_tokens": 4, "output_tokens": 2} if later_success else {})
    assert result["session_id"] == "synthetic-0"
    assert result["cost_usd"] is None
    assert len(launches) == 1


def test_success_with_failure_words_in_answer_keeps_existing_contract(monkeypatch):
    from brain import codex_bridge

    text = "This report discusses turn.failed and 401 errors."
    launches = _fake_codex(monkeypatch, [[
        _message(text),
        {"type": "turn.completed", "usage": {"input_tokens": 3, "output_tokens": 1}},
    ]])
    result = asyncio.run(codex_bridge.reason("Synthetic success control", allowed_tools=[]))
    assert result["ok"] is True
    assert result["error"] is None
    assert result["text"] == text
    assert result["usage"] == {"input_tokens": 3, "output_tokens": 1}
    assert "terminal_error_detail" not in result
    assert len(launches) == 1


@pytest.mark.parametrize("failed_phase", ["research", "sealed"])
def test_terminal_failure_stops_or_remains_failed_in_sealed_delegation(monkeypatch, failed_phase):
    from brain import codex_bridge

    research = [_message("Research artifact"), {"type": "turn.completed"}]
    sealed = [_submit(), _message("Submission evidence"), {"type": "turn.completed"}]
    (research if failed_phase == "research" else sealed).append(_failure("401 429 usage limit reached"))
    launches = _fake_codex(monkeypatch, [research, sealed])
    result = asyncio.run(codex_bridge.reason(
        "Synthetic governed book", book="autonomous",
        allowed_tools=["mcp__desk__get_my_book", "mcp__desk__submit_book", "Task"],
        mcp_servers={"bot": {}, "desk": {}},
    ))
    assert len(launches) == (1 if failed_phase == "research" else 2)
    assert result["ok"] is False
    assert result["error"] == "codex_terminal_error"
    assert result["terminal_error_detail"] == "401 429 usage limit reached"
    if failed_phase == "research":
        assert "delegated_research_completed" not in result
        assert result["text"] == "Research artifact"
    else:
        assert result["delegated_research_completed"] is True
        assert result["tools_used"] == ["mcp__desk__submit_book"]
        assert result["text"] == "Submission evidence"


def test_failed_write_keeps_existing_precedence_over_terminal_failure(monkeypatch):
    from brain import codex_bridge

    _fake_codex(monkeypatch, [[
        _submit("failed", {"message": "Synthetic write refusal " + _CANARY}),
        _message("Retained evidence"),
        _failure("401 429 usage limit reached " + _CANARY),
    ]])
    result = asyncio.run(codex_bridge.reason("Synthetic write boundary", allowed_tools=[]))
    assert result["ok"] is False
    assert result["error"] == codex_bridge.WRITE_TOOL_FAILURE_ERROR
    assert result["failed_write_tools"] == [
        {"tool": "mcp__desk__submit_book", "error": "Synthetic write refusal <redacted>"},
    ]
    assert result["terminal_error_detail"] == "401 429 usage limit reached <redacted>"
    assert result["text"] == "Retained evidence"
    assert _CANARY not in json.dumps(result)


@pytest.mark.parametrize("returncode", [0, 1])
@pytest.mark.parametrize("with_tool", [False, True])
def test_real_waterfall_never_replays_or_cools_a_terminal_failure(
    monkeypatch, returncode, with_tool,
):
    from brain import cli_bridge, provider_waterfall as pw
    import bot  # noqa: F401 - makes the pinned Macro engine importable
    from engine import llm_auth

    effects = []
    rows = []
    if with_tool:
        rows += [_submit(), lambda: effects.append("retained-effect-evidence")]
    rows += [_message("Retained answer"), _failure("access token could not be refreshed; 429 usage limit reached")]
    launches = _fake_codex(monkeypatch, [rows], returncodes=[returncode])
    sessions, cooling, unexpected_fallback = [], [], []

    class Pool:
        def record_session(self, *args, **kwargs):
            sessions.append((args, kwargs))

        def mark_cooling(self, *args, **kwargs):
            cooling.append((args, kwargs))

    monkeypatch.setattr(pw, "_shared_modules", lambda: (llm_auth, Pool()))
    monkeypatch.setattr(pw, "provider_rungs", lambda _role: [
        {"provider": "codex", "key_id": "codex_account", "env_name": None, "cooling": False},
        {"provider": "oauth", "key_id": "fixture-slot", "env_name": "SYNTHETIC_UNUSED", "cooling": False},
    ])
    monkeypatch.setattr(cli_bridge, "_record_cli_cost", lambda *_args, **_kwargs: None)
    original_reason = cli_bridge._reason

    async def dispatch(prompt, **kwargs):
        if kwargs.get("_backend_override") == "cli":
            unexpected_fallback.append("oauth")
            return {"ok": False, "text": None, "error": "unexpected synthetic fallback"}
        return await original_reason(prompt, **kwargs)

    monkeypatch.setattr(cli_bridge, "_reason", dispatch)
    result = asyncio.run(pw.reason(
        "Synthetic waterfall boundary", role="deep", allowed_tools=[], log_run=False,
    ))
    assert result["ok"] is False
    assert result["error"] == "codex_terminal_error"
    assert len(result["provider_attempts"]) == len(launches) == 1
    assert result["provider_attempts"][0]["ok"] is False
    assert result["tools_used"] == (["mcp__desk__submit_book"] if with_tool else [])
    assert effects == (["retained-effect-evidence"] if with_tool else [])
    assert sessions == [] and cooling == [] and unexpected_fallback == []


@pytest.mark.parametrize("file_written", [False, True])
def test_original_portfolio_job_keeps_submission_authority_after_codex_terminal_failure(
    monkeypatch, tmp_path, file_written,
):
    from bot import autonomous, settle
    from brain import autonomous_mcp, codex_bridge
    from portfolio import paper_account, registry

    monkeypatch.setattr(registry, "_ROOT", tmp_path / "books")
    monkeypatch.setattr(paper_account, "_current_price", lambda ticker: {"NVDA": 210.0, "SPY": 740.0}.get(ticker))
    monkeypatch.setattr(settle, "is_open", lambda _pid: True)

    def retain_submission():
        if file_written:
            path = autonomous_mcp.submission_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({
                "holdings": [{"ticker": "NVDA", "weight": 0.4, "rationale": "Synthetic accepted intent"}],
                "summary": "Synthetic retained submission", "gross": 0.4,
            }))

    rows = [retain_submission]
    if file_written:
        rows.append(_submit())
    rows += [_message("Retained answer"), _failure("401 429 usage limit reached")]
    launches = _fake_codex(monkeypatch, [rows])
    monkeypatch.setattr(autonomous, "_run_brain", lambda *_a, **_kw: asyncio.run(
        codex_bridge.reason("Synthetic accepted-target boundary", allowed_tools=[], book="autonomous")
    ))
    result = autonomous.run_autonomous(asof="2026-06-21", armed=True)
    assert len(launches) == 1
    assert result["brain"]["ok"] is False
    assert result["brain"]["error"] == "codex_terminal_error"
    assert result["decided"] is file_written
    if file_written:
        assert {row["ticker"] for row in result["executed"]} == {"NVDA"}
    else:
        assert result["target_status"] == "rejected_no_submission"
        assert result.get("executed") in (None, [])


# Synthetic, deliberately non-live credential shapes. The base64url canary also
# catches truncation before redaction when the surviving fragment is under 32 chars.
_CANARY = "M7qD2vX9sK4nR8cT1yB6pL3wF5hJ0aUeG2zV7kN9rQ4mC6xS1dP8bY3tW5jH0fL"
_REDACTION_CASES = [
    pytest.param(_CANARY, 20, id="base64url-fragment"),
    pytest.param("sk-ant-" + _CANARY, 10, id="prefixed-fragment"),
]


def _plain(length):
    # Keep padding out of the sanitizer's long-token class and end at a boundary.
    return ("note " * ((length + 4) // 5))[:length - 1] + " "


@pytest.mark.parametrize("canary,visible_prefix", _REDACTION_CASES)
def test_terminal_diagnostic_redacts_complete_message_before_500_bound(
    monkeypatch, canary, visible_prefix,
):
    from brain import codex_bridge

    diagnostic = _plain(500 - visible_prefix) + canary + " trailing context"
    _fake_codex(monkeypatch, [[_message("Retained answer"), _failure(diagnostic)]])
    result = asyncio.run(codex_bridge.reason("Synthetic redaction boundary", allowed_tools=[]))
    assert result["ok"] is False and result["error"] == "codex_terminal_error"
    detail = result["terminal_error_detail"]
    assert "<redacted>" in detail
    assert canary[:visible_prefix] not in json.dumps(result)
    assert canary not in json.dumps(result)
    assert len(detail) <= 1000


@pytest.mark.parametrize("canary,visible_prefix,as_mapping", [
    pytest.param(_CANARY, 20, True, id="mapping-base64url-fragment"),
    pytest.param("sk-ant-" + _CANARY, 10, False, id="scalar-prefixed-fragment"),
])
def test_failed_write_diagnostic_redacts_complete_message_before_1000_bound(
    monkeypatch, canary, visible_prefix, as_mapping,
):
    from brain import codex_bridge

    diagnostic = _plain(1000 - visible_prefix) + canary + " trailing context"
    error = {"message": diagnostic} if as_mapping else diagnostic
    _fake_codex(monkeypatch, [[_submit("failed", error), _message("Retained answer")]])
    result = asyncio.run(codex_bridge.reason("Synthetic failed-write redaction", allowed_tools=[]))
    assert result["ok"] is False and result["error"] == codex_bridge.WRITE_TOOL_FAILURE_ERROR
    detail = result["failed_write_tools"][0]["error"]
    assert "<redacted>" in detail
    assert canary[:visible_prefix] not in json.dumps(result)
    assert canary not in json.dumps(result)
    assert len(detail) <= 1000


def test_terminal_diagnostic_redacts_before_aggregate_1000_bound(monkeypatch):
    from brain import codex_bridge

    first = _plain(500)
    second = _plain(478) + _CANARY + " trailing context"
    _fake_codex(monkeypatch, [[
        {"type": "error", "message": first}, _message("Retained answer"), _failure(second),
    ]])
    result = asyncio.run(codex_bridge.reason("Synthetic aggregate redaction", allowed_tools=[]))
    assert result["ok"] is False and result["error"] == "codex_terminal_error"
    detail = result["terminal_error_detail"]
    assert "<redacted>" in detail
    assert _CANARY[:20] not in json.dumps(result)
    assert _CANARY not in json.dumps(result)
    assert len(detail) <= 1000


def test_terminal_stderr_redacts_complete_text_before_1000_tail_bound(monkeypatch):
    from brain import codex_bridge

    stderr = _CANARY + " " + _plain(979)
    _fake_codex(monkeypatch, [[_message("Retained answer"), _failure()]],
                returncodes=[1], stderr=stderr.encode())
    result = asyncio.run(codex_bridge.reason("Synthetic stderr redaction", allowed_tools=[]))
    assert result["ok"] is False and result["error"] == "codex_terminal_error"
    detail = result["terminal_error_detail"]
    assert "<redacted>" in detail
    assert _CANARY[-20:] not in json.dumps(result)
    assert _CANARY not in json.dumps(result)
    assert len(detail) <= 1000


@pytest.mark.parametrize("terminal_failure", [False, True])
def test_failed_write_without_diagnostic_preserves_none(monkeypatch, terminal_failure):
    from brain import codex_bridge

    rows = [_submit("failed"), _message("Retained answer")]
    if terminal_failure:
        rows.append(_failure())
    _fake_codex(monkeypatch, [rows])
    result = asyncio.run(codex_bridge.reason("Synthetic missing diagnostic", allowed_tools=[]))
    assert result["ok"] is False and result["error"] == codex_bridge.WRITE_TOOL_FAILURE_ERROR
    assert result["failed_write_tools"] == [{"tool": "mcp__desk__submit_book", "error": None}]
    if terminal_failure:
        assert result["terminal_error_detail"] is None
    else:
        assert "terminal_error_detail" not in result


def test_nonterminal_classifier_error_input_is_unchanged(monkeypatch):
    from brain import codex_bridge

    diagnostic = "401 Unauthorized\n  retry denied (upstream diagnostic) " * 20
    _fake_codex(monkeypatch, [[
        _message("Retained answer"), {"type": "error", "message": diagnostic},
    ]], returncodes=[1])
    result = asyncio.run(codex_bridge.reason("Synthetic nonterminal control", allowed_tools=[]))
    assert result["ok"] is False
    assert result["error"] == diagnostic[:500]
    assert "terminal_error_detail" not in result
