"""Research-paper persistence has one canonical file effect and truthful auxiliary failure semantics."""
from __future__ import annotations

import asyncio
import importlib
import json
import os
import sys
import types
from pathlib import Path

import pytest


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


def _paper(*, summary="new"):
    return {
        "schema": "research_paper.v1",
        "id": "2026-09-17-AAPL",
        "ticker": "AAPL",
        "asof": "2026-09-17",
        "generated_at": "2026-09-17T20:00:00+00:00",
        "mode": "portfolio_research_advisor",
        "research_score": 90,
        "viability": "compelling",
        "recommend": True,
        "summary": summary,
        "sections": {"thesis": summary},
        "key_risks": [],
    }


def _wire_paths(monkeypatch, rp, tmp_path):
    papers = tmp_path / "papers"
    papers.mkdir()
    monkeypatch.setattr(rp, "_PAPERS", papers)
    monkeypatch.setattr(rp, "_INDEX", papers / "index.jsonl")
    return papers


def test_canonical_replace_failure_preserves_previous_complete_paper(tmp_path, monkeypatch):
    from brain import research_paper as rp

    papers = _wire_paths(monkeypatch, rp, tmp_path)
    target = papers / "2026-09-17_AAPL.json"
    previous = _paper(summary="previous-good")
    target.write_text(json.dumps(previous))

    original_write_text = Path.write_text
    original_replace = os.replace

    def partial_direct_write(self, text, *args, **kwargs):
        if self == target:
            original_write_text(self, "{", *args, **kwargs)
            raise OSError("simulated partial canonical write")
        return original_write_text(self, text, *args, **kwargs)

    def fail_atomic_replace(src, dst):
        if Path(dst) == target:
            raise OSError("simulated atomic replace refusal")
        return original_replace(src, dst)

    monkeypatch.setattr(Path, "write_text", partial_direct_write)
    monkeypatch.setattr(os, "replace", fail_atomic_replace)

    with pytest.raises(OSError):
        rp.save_paper(_paper(summary="replacement"))

    assert json.loads(target.read_text()) == previous
    assert not list(papers.glob(".*.tmp"))


def test_auxiliary_index_failure_does_not_invalidate_canonical_save(tmp_path, monkeypatch):
    from brain import research_paper as rp

    papers = _wire_paths(monkeypatch, rp, tmp_path)
    original_open = Path.open

    def fail_index_open(self, *args, **kwargs):
        if self == rp._INDEX:
            raise OSError("secret /Users/private/index token=do-not-return")
        return original_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", fail_index_open)
    path = rp.save_paper(_paper(summary="canonical survives"))

    assert path.exists()
    saved = json.loads(path.read_text())
    assert saved["summary"] == "canonical survives"
    assert rp.load_papers()[0]["id"] == "2026-09-17-AAPL"


def test_successful_save_replaces_existing_paper_with_valid_json_and_no_temp(tmp_path, monkeypatch):
    from brain import research_paper as rp

    papers = _wire_paths(monkeypatch, rp, tmp_path)
    target = papers / "2026-09-17_AAPL.json"
    target.write_text(json.dumps(_paper(summary="old")))

    returned = rp.save_paper(_paper(summary="new-complete"))

    assert returned == target
    assert json.loads(target.read_text())["summary"] == "new-complete"
    assert not list(papers.glob(".*.tmp"))


def _up_matrix():
    return {
        "subject": "AAPL",
        "kind": "name",
        "rows": [{"lens": "trend", "direction": "bull"}],
        "synthesis": {
            "confluence": 0.5,
            "size_authority": "up",
            "vetoes": [],
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


def test_handler_canonical_save_failure_is_closed_and_reports_not_saved(tmp_path, monkeypatch):
    bot_mcp = _load_bot_mcp_with_fake_sdk(monkeypatch)
    from brain import research_paper as rp
    from portfolio import lenses
    from data_layer import polygon

    monkeypatch.setattr(lenses, "full", lambda *_a, **_k: _up_matrix())
    monkeypatch.setattr(bot_mcp, "_today", lambda: "2026-09-17")
    monkeypatch.setattr(bot_mcp, "_stock_price", lambda _t: 250.0)
    monkeypatch.setattr(polygon, "quotes", lambda _tickers: {})
    monkeypatch.setattr(rp, "save_paper", lambda _paper: (_ for _ in ()).throw(
        OSError("secret /Users/private/paper token=do-not-return")
    ))
    feed_calls = []
    monkeypatch.setattr(rp, "write_feed_note", lambda paper: feed_calls.append(paper))

    result = asyncio.run(bot_mcp.file_research_paper.handler(_paper_args()))
    raw = result["content"][0]["text"]
    payload = json.loads(raw)

    assert payload["error"] == "research_paper_save_unavailable"
    assert payload["paper_saved"] is False
    assert payload["write_status"] == "unavailable"
    assert feed_calls == []
    assert "secret" not in raw and "/Users/private" not in raw and "token=" not in raw


def test_feed_note_failure_does_not_undo_saved_canonical_paper(tmp_path, monkeypatch):
    bot_mcp = _load_bot_mcp_with_fake_sdk(monkeypatch)
    from brain import research_paper as rp
    from portfolio import lenses
    from data_layer import polygon

    saved = []
    monkeypatch.setattr(lenses, "full", lambda *_a, **_k: _up_matrix())
    monkeypatch.setattr(bot_mcp, "_today", lambda: "2026-09-17")
    monkeypatch.setattr(bot_mcp, "_stock_price", lambda _t: 250.0)
    monkeypatch.setattr(polygon, "quotes", lambda _tickers: {})
    monkeypatch.setattr(rp, "save_paper", lambda paper: saved.append(dict(paper)) or (tmp_path / "paper.json"))
    monkeypatch.setattr(rp, "write_feed_note", lambda _paper: (_ for _ in ()).throw(OSError("feed down")))

    raw = asyncio.run(bot_mcp.file_research_paper.handler(_paper_args()))["content"][0]["text"]

    assert bot_mcp.PAPER_MARKER in raw
    assert len(saved) == 1 and saved[0]["confirmed"] is True
