"""Research-paper persistence has one canonical file effect and truthful auxiliary failure semantics."""
from __future__ import annotations

import asyncio
import importlib
import json
import os
import sys
import types
from pathlib import Path
from contextlib import contextmanager, nullcontext

import pytest


@contextmanager
def _bot_mcp_with_fake_sdk(monkeypatch):
    import brain

    missing = object()
    previous_module = sys.modules.get("brain.bot_mcp", missing)
    previous_attribute = vars(brain).get("bot_mcp", missing)
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
    with monkeypatch.context() as sdk_patch:
        sdk_patch.setitem(sys.modules, "claude_agent_sdk", fake)
        sys.modules.pop("brain.bot_mcp", None)
        vars(brain).pop("bot_mcp", None)
        try:
            yield importlib.import_module("brain.bot_mcp")
        finally:
            if previous_module is missing:
                sys.modules.pop("brain.bot_mcp", None)
            else:
                sys.modules["brain.bot_mcp"] = previous_module
            if previous_attribute is missing:
                vars(brain).pop("bot_mcp", None)
            else:
                setattr(brain, "bot_mcp", previous_attribute)


@pytest.fixture
def bot_mcp(monkeypatch):
    with _bot_mcp_with_fake_sdk(monkeypatch) as module:
        yield module


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
    monkeypatch.setattr(rp, "_NOTES", tmp_path / "notes")
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


def test_handler_canonical_save_failure_is_closed_and_reports_not_saved(tmp_path, monkeypatch, bot_mcp):
    from brain import research_paper as rp
    from portfolio import lenses
    from data_layer import polygon

    _wire_paths(monkeypatch, rp, tmp_path)
    monkeypatch.setattr(lenses, "full", lambda *_a, **_k: _up_matrix())
    monkeypatch.setattr(bot_mcp, "_today", lambda: "2026-09-17")
    monkeypatch.setattr(bot_mcp, "_stock_price", lambda _t: 250.0)
    monkeypatch.setattr(polygon, "quotes", lambda _tickers: {})
    monkeypatch.setattr(rp, "save_paper", lambda _paper: (_ for _ in ()).throw(
        rp._PaperSaveNotCommittedError("secret /Users/private/paper token=do-not-return")
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


def test_feed_note_failure_does_not_undo_saved_canonical_paper(tmp_path, monkeypatch, bot_mcp):
    from brain import research_paper as rp
    from portfolio import lenses
    from data_layer import polygon

    _wire_paths(monkeypatch, rp, tmp_path)
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


def _wire_handler(monkeypatch, bot_mcp, rp, tmp_path):
    from data_layer import polygon
    from portfolio import lenses

    papers = _wire_paths(monkeypatch, rp, tmp_path)
    monkeypatch.setattr(lenses, "full", lambda *_a, **_k: _up_matrix())
    monkeypatch.setattr(bot_mcp, "_today", lambda: "2026-09-17")
    monkeypatch.setattr(bot_mcp, "_stock_price", lambda _t: 250.0)
    monkeypatch.setattr(polygon, "quotes", lambda _tickers: {})
    return papers


def _fail_staging_at(monkeypatch, rp, phase, error_type=OSError):
    original_factory = rp.tempfile.NamedTemporaryFile

    def failure():
        return error_type("secret /Users/private/staging token=do-not-return")

    if phase == "fsync":
        def fail_fsync(_fd):
            raise failure()
        monkeypatch.setattr(rp.os, "fsync", fail_fsync)
        return

    class FailingStaging:
        def __init__(self, wrapped):
            self.wrapped = wrapped

        def __getattr__(self, name):
            return getattr(self.wrapped, name)

        def __enter__(self):
            self.wrapped.__enter__()
            return self

        def __exit__(self, *args):
            result = self.wrapped.__exit__(*args)
            if phase == "close":
                raise failure()
            return result

        def write(self, text):
            if phase == "write":
                self.wrapped.write("{")
                raise failure()
            return self.wrapped.write(text)

        def flush(self):
            if phase == "flush":
                raise failure()
            return self.wrapped.flush()

    monkeypatch.setattr(
        rp.tempfile,
        "NamedTemporaryFile",
        lambda **kwargs: FailingStaging(original_factory(**kwargs)),
    )


def _assert_private_error(raw):
    assert "secret" not in raw
    assert "/Users/private" not in raw
    assert "token=" not in raw


@pytest.mark.parametrize("phase", ["write", "flush", "fsync", "close"])
def test_real_handler_reports_only_proven_pre_replace_failure(
    tmp_path, monkeypatch, bot_mcp, phase
):
    from brain import research_paper as rp

    papers = _wire_handler(monkeypatch, bot_mcp, rp, tmp_path)
    target = papers / "2026-09-17_AAPL.json"
    previous = _paper(summary="previous-good")
    target.write_text(json.dumps(previous))
    previous_bytes = target.read_bytes()
    _fail_staging_at(monkeypatch, rp, phase)
    replace_calls = []
    original_replace = os.replace

    def record_replace(src, dst):
        replace_calls.append((src, dst))
        return original_replace(src, dst)

    monkeypatch.setattr(os, "replace", record_replace)
    feed_calls = []
    monkeypatch.setattr(rp, "write_feed_note", lambda paper: feed_calls.append(paper))

    raw = asyncio.run(bot_mcp.file_research_paper.handler(_paper_args()))["content"][0]["text"]
    payload = json.loads(raw)

    assert payload["error"] == "research_paper_save_unavailable"
    assert payload["write_status"] == "unavailable"
    assert payload["paper_saved"] is False
    assert target.read_bytes() == previous_bytes
    assert replace_calls == []
    assert feed_calls == []
    assert bot_mcp.PAPER_MARKER not in raw
    assert not list(papers.glob(".*.tmp"))
    assert not rp._NOTES.exists()
    _assert_private_error(raw)


@pytest.mark.parametrize("replace_completed", [False, True])
def test_real_replace_exception_is_unknown_without_retry_or_false_failure(
    tmp_path, monkeypatch, bot_mcp, replace_completed
):
    from brain import research_paper as rp

    papers = _wire_handler(monkeypatch, bot_mcp, rp, tmp_path)
    target = papers / "2026-09-17_AAPL.json"
    previous = _paper(summary="previous-good")
    target.write_text(json.dumps(previous))
    calls = []
    original_replace = os.replace

    def uncertain_replace(src, dst):
        calls.append((src, dst))
        if replace_completed:
            original_replace(src, dst)
        raise OSError("secret /Users/private/replacement token=do-not-return")

    monkeypatch.setattr(os, "replace", uncertain_replace)
    feed_calls = []
    monkeypatch.setattr(rp, "write_feed_note", lambda paper: feed_calls.append(paper))

    raw = asyncio.run(bot_mcp.file_research_paper.handler(_paper_args()))["content"][0]["text"]
    payload = json.loads(raw)

    assert payload["error"] == "research_paper_save_outcome_unknown"
    assert payload["write_status"] == "unknown"
    assert payload["paper_saved"] is None
    saved = json.loads(target.read_text())
    assert saved["summary"] == ("Durable thesis." if replace_completed else "previous-good")
    assert len(calls) == 1
    assert feed_calls == []
    assert bot_mcp.PAPER_MARKER not in raw
    assert not list(papers.glob(".*.tmp"))
    assert not rp._NOTES.exists()
    _assert_private_error(raw)


@pytest.mark.parametrize("error_type", [OSError, RuntimeError])
def test_unclassified_save_exception_does_not_assert_no_effect(
    tmp_path, monkeypatch, bot_mcp, error_type
):
    from brain import research_paper as rp

    _wire_handler(monkeypatch, bot_mcp, rp, tmp_path)
    calls = []

    def fail_save(paper):
        calls.append(paper)
        raise error_type("secret /Users/private/unknown token=do-not-return")

    monkeypatch.setattr(rp, "save_paper", fail_save)
    feed_calls = []
    monkeypatch.setattr(rp, "write_feed_note", lambda paper: feed_calls.append(paper))

    raw = asyncio.run(bot_mcp.file_research_paper.handler(_paper_args()))["content"][0]["text"]
    payload = json.loads(raw)

    assert payload["error"] == "research_paper_save_outcome_unknown"
    assert payload["paper_saved"] is None
    assert payload["write_status"] == "unknown"
    assert len(calls) == 1
    assert feed_calls == []
    assert bot_mcp.PAPER_MARKER not in raw
    _assert_private_error(raw)


@pytest.mark.parametrize("phase", ["open", "write", "close"])
def test_real_handler_keeps_canonical_success_after_index_and_feed_failures(
    tmp_path, monkeypatch, bot_mcp, phase
):
    from brain import research_paper as rp

    papers = _wire_handler(monkeypatch, bot_mcp, rp, tmp_path)
    original_open = Path.open

    class FailingIndex:
        def __init__(self, wrapped):
            self.wrapped = wrapped

        def __enter__(self):
            self.wrapped.__enter__()
            return self

        def __exit__(self, *args):
            result = self.wrapped.__exit__(*args)
            if phase == "close":
                raise OSError("secret index close token=do-not-return")
            return result

        def write(self, text):
            if phase == "write":
                self.wrapped.write("{")
                raise OSError("secret index write token=do-not-return")
            return self.wrapped.write(text)

    def index_open(path, *args, **kwargs):
        if path == rp._INDEX:
            if phase == "open":
                raise OSError("secret index open token=do-not-return")
            return FailingIndex(original_open(path, *args, **kwargs))
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", index_open)
    feed_calls = []

    def fail_feed(paper):
        feed_calls.append(dict(paper))
        raise OSError("secret /Users/private/feed token=do-not-return")

    monkeypatch.setattr(rp, "write_feed_note", fail_feed)

    raw = asyncio.run(bot_mcp.file_research_paper.handler(_paper_args()))["content"][0]["text"]

    assert bot_mcp.PAPER_MARKER in raw
    assert len(feed_calls) == 1
    target = papers / "2026-09-17_AAPL.json"
    saved = json.loads(target.read_text())
    assert saved["summary"] == "Durable thesis."
    assert saved["confirmed"] is True
    assert saved["execution_provenance"] == {"source": "claude_cli"}
    assert rp.latest_for("aapl") == saved
    assert rp.load_papers() == [saved]
    assert not list(papers.glob(".*.tmp"))
    assert not rp._NOTES.exists()
    _assert_private_error(raw)


@pytest.mark.parametrize("previously_present", [False, True])
@pytest.mark.parametrize("failure", ["none", "body", "import"])
def test_fake_sdk_fixture_restores_both_module_cache_surfaces(
    monkeypatch, previously_present, failure
):
    import brain

    missing = object()
    sdk_before = sys.modules.get("claude_agent_sdk", missing)
    previous_module = types.ModuleType("previous_brain_bot_mcp")
    previous_attribute = object()
    if previously_present:
        monkeypatch.setitem(sys.modules, "brain.bot_mcp", previous_module)
        monkeypatch.setattr(brain, "bot_mcp", previous_attribute, raising=False)
    else:
        monkeypatch.delitem(sys.modules, "brain.bot_mcp", raising=False)
        monkeypatch.delattr(brain, "bot_mcp", raising=False)

    if failure == "import":
        original_import = importlib.import_module

        def fail_import(name, *args, **kwargs):
            if name == "brain.bot_mcp":
                raise ImportError("controlled fixture import")
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr(importlib, "import_module", fail_import)

    expected = (
        pytest.raises(ImportError, match="controlled fixture import")
        if failure == "import"
        else pytest.raises(AssertionError, match="controlled fixture body")
        if failure == "body"
        else nullcontext()
    )
    with expected:
        with _bot_mcp_with_fake_sdk(monkeypatch) as loaded:
            assert sys.modules["brain.bot_mcp"] is loaded
            assert vars(brain)["bot_mcp"] is loaded
            assert loaded is not previous_module
            if failure == "body":
                raise AssertionError("controlled fixture body")

    if previously_present:
        assert sys.modules["brain.bot_mcp"] is previous_module
        assert vars(brain)["bot_mcp"] is previous_attribute
    else:
        assert "brain.bot_mcp" not in sys.modules
        assert "bot_mcp" not in vars(brain)
    if sdk_before is missing:
        assert "claude_agent_sdk" not in sys.modules
    else:
        assert sys.modules["claude_agent_sdk"] is sdk_before


@pytest.mark.parametrize("boundary", ["handler", "owner"])
def test_paper_cancellation_propagates_without_a_false_failure_response(
    tmp_path, monkeypatch, bot_mcp, boundary
):
    from brain import research_paper as rp

    class ControlledCancellation(BaseException):
        pass

    papers = _wire_handler(monkeypatch, bot_mcp, rp, tmp_path)
    target = papers / "2026-09-17_AAPL.json"
    previous = _paper(summary="previous-good")
    target.write_text(json.dumps(previous))
    previous_bytes = target.read_bytes()
    feed_calls = []
    monkeypatch.setattr(rp, "write_feed_note", lambda paper: feed_calls.append(paper))

    if boundary == "handler":
        def cancel_save(_paper):
            raise ControlledCancellation("controlled cancellation")
        monkeypatch.setattr(rp, "save_paper", cancel_save)
    else:
        _fail_staging_at(monkeypatch, rp, "write", ControlledCancellation)

    with pytest.raises(ControlledCancellation):
        asyncio.run(bot_mcp.file_research_paper.handler(_paper_args()))

    assert target.read_bytes() == previous_bytes
    assert feed_calls == []
    assert not list(papers.glob(".*.tmp"))
