"""SDK terminal-error outcome and no-replay boundary; all transports are fakes."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from test_provider_start_run_binding import RunBindingHarness


def terminal(*, is_error, text="Retained answer", subtype="success"):
    return SimpleNamespace(result=text, is_error=is_error, subtype=subtype,
                           total_cost_usd=0.0, session_id="synthetic-session", usage={})


@pytest.mark.parametrize("book", ["autonomous", "china", "hk"])
@pytest.mark.parametrize("text", [
    "Retained answer",
    "Your organization has disabled Claude subscription access for Claude Code",
    "429 usage limit reached",
    "Failed to authenticate. API Error: 401 OAuth access token has been revoked.",
])
def test_error_terminal_is_failed_and_never_rotates_its_text(monkeypatch, tmp_path, book, text):
    h = RunBindingHarness(monkeypatch, tmp_path)
    h.plans = [[terminal(is_error=True, text=text)]]
    result = asyncio.run(h.invoke(None, book=book))
    assert result["ok"] is False
    assert result["error"] == "sdk_terminal_error"
    assert result["text"] == text
    assert result["run_id"] == h.created[0]
    assert len(h.providers) == 1
    assert h.classifications == [] and h.cooling == [] and h.sessions == []


@pytest.mark.parametrize("arm", [False, True])
def test_earlier_error_cannot_be_overwritten_by_later_success_terminal(monkeypatch, tmp_path, arm):
    h = RunBindingHarness(monkeypatch, tmp_path)
    h.plans = [[terminal(is_error=True), terminal(is_error=False, text="Later terminal")]]
    result = asyncio.run(h.invoke(None, arm=arm))
    assert result["ok"] is False and result["error"] == "sdk_terminal_error"
    assert result["text"] == "Later terminal"
    assert len(h.providers) == 1 and not h.sessions


def test_success_terminal_keeps_existing_success_and_bookkeeping(monkeypatch, tmp_path):
    h = RunBindingHarness(monkeypatch, tmp_path)
    h.plans = [[terminal(is_error=False)]]
    result = asyncio.run(h.invoke(None))
    assert result["ok"] is True and "error" not in result
    assert result["text"] == "Retained answer"
    assert len(h.providers) == 1 and len(h.sessions) == 1
    assert h.cooling == []


@pytest.mark.parametrize("with_tool", [False, True])
def test_actual_waterfall_does_not_replay_terminal_error_on_another_credential(
    monkeypatch, tmp_path, with_tool,
):
    from brain import provider_waterfall as pw

    h = RunBindingHarness(monkeypatch, tmp_path)
    effects = []
    rows = []
    if with_tool:
        rows.append(SimpleNamespace(content=[
            SimpleNamespace(type="tool_use", name="mcp__desk__submit_book", input={})
        ]))
        rows.append(lambda: effects.append("accepted-target-evidence"))
    rows.append(terminal(is_error=True, text="401 429 usage limit reached"))
    h.plans = [rows]

    shared_lookups = []

    def unexpected_shared_modules():
        shared_lookups.append(True)
        raise AssertionError("owned SDK terminal cannot consult shared auth")

    monkeypatch.setattr(pw, "_shared_modules", unexpected_shared_modules)
    monkeypatch.setattr(pw, "provider_rungs", lambda _role: [
        {"provider": "oauth", "key_id": "fixture-a", "env_name": "SYNTHETIC_UNUSED_A", "cooling": False},
        {"provider": "oauth", "key_id": "fixture-b", "env_name": "SYNTHETIC_UNUSED_B", "cooling": False},
    ])
    result = asyncio.run(pw.reason(
        "Synthetic terminal-error boundary", role="deep", model="synthetic-model",
        arm=True, book="autonomous", allowed_tools=[], add_dirs=[], mcp_servers={},
        cwd=str(tmp_path), before_provider_start=None,
    ))
    assert result["ok"] is False and result["error"] == "sdk_terminal_error"
    assert len(result["provider_attempts"]) == len(h.providers) == 1
    assert result["provider_attempts"][0]["ok"] is False
    assert shared_lookups == [], "owned terminal consulted shared auth"
    assert effects == (["accepted-target-evidence"] if with_tool else [])
    assert result["tools_used"] == (["mcp__desk__submit_book"] if with_tool else [])
    assert h.classifications == [] and h.cooling == [] and h.sessions == []


@pytest.mark.parametrize("file_written", [False, True])
def test_original_portfolio_job_keeps_submission_authority_after_sdk_error(
    monkeypatch, tmp_path, file_written,
):
    import json
    from bot import autonomous, settle
    from brain import autonomous_mcp
    from portfolio import paper_account, registry

    monkeypatch.setattr(registry, "_ROOT", tmp_path / "books")
    monkeypatch.setattr(paper_account, "_current_price", lambda ticker: {"NVDA": 210.0, "SPY": 740.0}.get(ticker))
    monkeypatch.setattr(settle, "is_open", lambda _pid: True)
    h = RunBindingHarness(monkeypatch, tmp_path / "reasoning")
    h.root.mkdir()

    def retain_submission():
        if file_written:
            path = autonomous_mcp.submission_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({
                "holdings": [{"ticker": "NVDA", "weight": 0.4, "rationale": "Synthetic accepted intent"}],
                "summary": "Synthetic retained submission", "gross": 0.4,
            }))

    h.plans = [[retain_submission, terminal(is_error=True, text="401 429 usage limit reached")]]
    monkeypatch.setattr(autonomous, "_run_brain", lambda *_a, **_kw: asyncio.run(h.invoke(None)))
    result = autonomous.run_autonomous(asof="2026-06-21", armed=True)
    assert len(h.providers) == 1
    assert result["brain"]["ok"] is False
    assert result["brain"]["error"] == "sdk_terminal_error"
    assert result["decided"] is file_written
    if file_written:
        assert {row["ticker"] for row in result["executed"]} == {"NVDA"}
    else:
        assert result["target_status"] == "rejected_no_submission"
        assert result.get("executed") in (None, [])
    assert not h.cooling and not h.sessions
