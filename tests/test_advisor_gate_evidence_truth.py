"""Advisor gate evidence must stay closed from preliminary read through ADD proposal."""
from __future__ import annotations

import asyncio
import importlib
import json
import sys
import types


def _load_bot_mcp_with_fake_sdk(monkeypatch):
    fake = types.ModuleType("claude_agent_sdk")

    class ToolWrap:
        def __init__(self, name, handler):
            self.name = name
            self.handler = handler

    def tool(name, _description, _schema):
        def deco(fn):
            return ToolWrap(name, fn)
        return deco

    fake.tool = tool
    fake.create_sdk_mcp_server = lambda **kwargs: kwargs
    monkeypatch.setitem(sys.modules, "claude_agent_sdk", fake)
    sys.modules.pop("brain.bot_mcp", None)
    return importlib.import_module("brain.bot_mcp")


def _text(result):
    return result["content"][0]["text"]


def _payload(result):
    return json.loads(_text(result))


def _matrix(*, authority="up", confluence=0.5, vetoes=None):
    return {
        "subject": "AAPL",
        "kind": "name",
        "rows": [{"lens": "trend", "direction": "bull", "note": "confirmed"}],
        "synthesis": {
            "confluence": confluence,
            "size_authority": authority,
            "vetoes": list(vetoes or []),
            "divergences": [],
        },
    }


def _paper_args():
    return {
        "ticker": "AAPL",
        "report_md": "## Thesis\nDurable thesis.",
        "research_score": 90,
        "viability": "compelling",
        "recommend": True,
        "summary": "Durable thesis.",
        "key_risks": ["valuation"],
        "confidence": "high",
    }


def _wire_paper_side_effects(monkeypatch, bot_mcp, tmp_path):
    from brain import research_paper as rp
    from data_layer import polygon

    saved = []
    monkeypatch.setattr(bot_mcp, "_today", lambda: "2026-09-17")
    monkeypatch.setattr(bot_mcp, "_stock_price", lambda _t: 250.0)
    monkeypatch.setattr(polygon, "quotes", lambda _tickers: {})
    monkeypatch.setattr(rp, "save_paper", lambda paper: saved.append(dict(paper)) or (tmp_path / "paper.json"))
    monkeypatch.setattr(rp, "write_feed_note", lambda _paper: tmp_path / "note.md")
    return saved


def test_evaluate_gate_lens_exception_is_unknown_not_negative(monkeypatch):
    bot_mcp = _load_bot_mcp_with_fake_sdk(monkeypatch)
    from portfolio import lenses

    def explode(*_args, **_kwargs):
        raise RuntimeError("secret /Users/private/gate token=do-not-return")

    monkeypatch.setattr(lenses, "full", explode)
    raw = _text(asyncio.run(bot_mcp.evaluate_gate.handler({"ticker": "AAPL"})))
    payload = json.loads(raw)
    assert payload["read_status"] == "unavailable"
    assert payload["error"] == "advisor_gate_unavailable"
    assert payload["passed"] is None
    assert payload["confluence"] is None
    assert "secret" not in raw and "/Users/private" not in raw and "token=" not in raw


def test_evaluate_gate_malformed_synthesis_is_unknown(monkeypatch):
    bot_mcp = _load_bot_mcp_with_fake_sdk(monkeypatch)
    from portfolio import lenses

    monkeypatch.setattr(lenses, "full", lambda *_a, **_k: {"rows": [], "synthesis": {}})
    payload = _payload(asyncio.run(bot_mcp.evaluate_gate.handler({"ticker": "AAPL"})))
    assert payload["read_status"] == "unavailable"
    assert payload["passed"] is None


def test_evaluate_gate_nonfinite_confluence_is_unavailable(monkeypatch):
    bot_mcp = _load_bot_mcp_with_fake_sdk(monkeypatch)
    from portfolio import lenses

    monkeypatch.setattr(lenses, "full", lambda *_a, **_k: _matrix(authority="up", confluence=float("nan")))
    payload = _payload(asyncio.run(bot_mcp.evaluate_gate.handler({"ticker": "AAPL"})))
    assert payload["read_status"] == "unavailable"
    assert payload["passed"] is None


def test_evaluate_gate_legitimate_insufficient_data_stays_real_gate_result(monkeypatch):
    bot_mcp = _load_bot_mcp_with_fake_sdk(monkeypatch)
    from portfolio import lenses

    monkeypatch.setattr(lenses, "full", lambda *_a, **_k: _matrix(authority="insufficient_data", confluence=0.8))
    payload = _payload(asyncio.run(bot_mcp.evaluate_gate.handler({"ticker": "AAPL"})))
    assert payload["passed"] is False
    assert payload["size_authority"] == "insufficient_data"
    assert "read_status" not in payload
    assert "insufficient data" in payload["reason"].lower()


def test_evaluate_gate_healthy_up_shape_is_preserved(monkeypatch):
    bot_mcp = _load_bot_mcp_with_fake_sdk(monkeypatch)
    from portfolio import lenses

    monkeypatch.setattr(lenses, "full", lambda *_a, **_k: _matrix(authority="up", confluence=0.5))
    payload = _payload(asyncio.run(bot_mcp.evaluate_gate.handler({"ticker": "AAPL"})))
    assert payload["passed"] is True
    assert payload["confluence"] == 0.5
    assert payload["size_authority"] == "up"
    assert payload["vetoes"] == []
    assert "read_status" not in payload


def test_file_paper_unavailable_gate_never_persists(monkeypatch, tmp_path):
    bot_mcp = _load_bot_mcp_with_fake_sdk(monkeypatch)
    from portfolio import lenses

    saved = _wire_paper_side_effects(monkeypatch, bot_mcp, tmp_path)
    monkeypatch.setattr(lenses, "full", lambda *_a, **_k: (_ for _ in ()).throw(
        RuntimeError("secret /Users/private/paper api_key=do-not-return")
    ))
    raw = _text(asyncio.run(bot_mcp.file_research_paper.handler(_paper_args())))
    payload = json.loads(raw)
    assert payload["read_status"] == "unavailable"
    assert payload["error"] == "research_paper_gate_unavailable"
    assert payload["paper_saved"] is False
    assert saved == []
    assert "secret" not in raw and "/Users/private" not in raw and "api_key" not in raw


def test_file_paper_blocked_gate_cannot_be_confirmed_or_persisted(monkeypatch, tmp_path):
    bot_mcp = _load_bot_mcp_with_fake_sdk(monkeypatch)
    from portfolio import lenses

    saved = _wire_paper_side_effects(monkeypatch, bot_mcp, tmp_path)
    monkeypatch.setattr(lenses, "full", lambda *_a, **_k: _matrix(
        authority="blocked", confluence=0.9, vetoes=["parabolic"]
    ))
    payload = _payload(asyncio.run(bot_mcp.file_research_paper.handler(_paper_args())))
    assert payload["error"] == "research_paper_preliminary_gate_failed"
    assert payload["paper_saved"] is False
    assert payload["size_authority"] == "blocked"
    assert payload["vetoes"] == ["parabolic"]
    assert saved == []


def test_file_paper_insufficient_data_cannot_turn_score_90_into_confirmed(monkeypatch, tmp_path):
    bot_mcp = _load_bot_mcp_with_fake_sdk(monkeypatch)
    from portfolio import lenses

    saved = _wire_paper_side_effects(monkeypatch, bot_mcp, tmp_path)
    monkeypatch.setattr(lenses, "full", lambda *_a, **_k: _matrix(
        authority="insufficient_data", confluence=1.0
    ))
    payload = _payload(asyncio.run(bot_mcp.file_research_paper.handler(_paper_args())))
    assert payload["error"] == "research_paper_preliminary_gate_failed"
    assert payload["paper_saved"] is False
    assert saved == []


def test_file_paper_valid_up_gate_preserves_success_and_persists(monkeypatch, tmp_path):
    bot_mcp = _load_bot_mcp_with_fake_sdk(monkeypatch)
    from portfolio import lenses

    saved = _wire_paper_side_effects(monkeypatch, bot_mcp, tmp_path)
    monkeypatch.setattr(lenses, "full", lambda *_a, **_k: _matrix(authority="up", confluence=0.5))
    raw = _text(asyncio.run(bot_mcp.file_research_paper.handler(_paper_args())))
    assert bot_mcp.PAPER_MARKER in raw
    assert len(saved) == 1
    assert saved[0]["confirmed"] is True
    assert saved[0]["combined"] >= 60


def test_add_proposal_rechecks_current_gate_and_refuses_blocked_legacy_paper(monkeypatch):
    bot_mcp = _load_bot_mcp_with_fake_sdk(monkeypatch)
    from brain import research_paper as rp
    from portfolio import advisor_trade, lenses

    monkeypatch.setattr(rp, "latest_for", lambda _ticker: {"ticker": "AAPL", "confirmed": True})
    monkeypatch.setattr(lenses, "full", lambda *_a, **_k: _matrix(authority="blocked", confluence=0.9, vetoes=["parabolic"]))
    calls = []
    monkeypatch.setattr(advisor_trade, "propose_action", lambda *a, **k: calls.append((a, k)) or {"ok": True})
    raw = _text(asyncio.run(bot_mcp.propose_portfolio_action.handler({
        "ticker": "AAPL", "action": "add", "thesis": "x", "evidence": ["e"], "urgency": "routine"
    })))
    assert "REFUSED" in raw
    assert "preliminary" in raw.lower()
    assert calls == []


def test_add_proposal_paper_read_failure_is_closed_before_queue(monkeypatch):
    bot_mcp = _load_bot_mcp_with_fake_sdk(monkeypatch)
    from brain import research_paper as rp
    from portfolio import advisor_trade

    def explode(_ticker):
        raise RuntimeError("secret /Users/private/papers token=do-not-return")

    monkeypatch.setattr(rp, "latest_for", explode)
    calls = []
    monkeypatch.setattr(advisor_trade, "propose_action", lambda *a, **k: calls.append((a, k)))
    raw = _text(asyncio.run(bot_mcp.propose_portfolio_action.handler({
        "ticker": "AAPL", "action": "add", "thesis": "x", "evidence": ["e"], "urgency": "routine"
    })))
    assert "REFUSED" in raw and "paper" in raw.lower()
    assert calls == []
    assert "secret" not in raw and "/Users/private" not in raw and "token=" not in raw


def test_trim_remains_ungated_de_risking_proposal(monkeypatch):
    bot_mcp = _load_bot_mcp_with_fake_sdk(monkeypatch)
    from brain import research_paper as rp
    from portfolio import advisor_trade, lenses

    monkeypatch.setattr(rp, "latest_for", lambda _ticker: (_ for _ in ()).throw(AssertionError("trim must not read paper")))
    monkeypatch.setattr(lenses, "full", lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("trim must not read ADD gate")))
    proposal = {"id": "p-trim", "ticker": "AAPL", "action": "trim"}
    monkeypatch.setattr(advisor_trade, "propose_action", lambda *a, **k: {"ok": True, "proposal": proposal, "note": "context only"})
    raw = _text(asyncio.run(bot_mcp.propose_portfolio_action.handler({
        "ticker": "AAPL", "action": "trim", "thesis": "risk", "evidence": ["e"], "urgency": "routine"
    })))
    assert "PROPOSAL_QUEUED" in raw


def test_add_proposal_confirmed_paper_and_current_up_gate_still_queues(monkeypatch):
    bot_mcp = _load_bot_mcp_with_fake_sdk(monkeypatch)
    from brain import research_paper as rp
    from portfolio import advisor_trade, lenses

    monkeypatch.setattr(rp, "latest_for", lambda _ticker: {"ticker": "AAPL", "confirmed": True})
    monkeypatch.setattr(lenses, "full", lambda *_a, **_k: _matrix(authority="up", confluence=0.5))
    proposal = {"id": "p1", "ticker": "AAPL", "action": "add"}
    monkeypatch.setattr(advisor_trade, "propose_action", lambda *a, **k: {"ok": True, "proposal": proposal, "note": "context only"})
    raw = _text(asyncio.run(bot_mcp.propose_portfolio_action.handler({
        "ticker": "AAPL", "action": "add", "thesis": "x", "evidence": ["e"], "urgency": "routine"
    })))
    assert "PROPOSAL_QUEUED" in raw
    assert '"ticker": "AAPL"' in raw
