"""Advisor gate evidence must stay closed from preliminary read through ADD proposal."""
from __future__ import annotations

import asyncio
import importlib
import json
import os
import sys
import types
from contextlib import contextmanager
from pathlib import Path

import pytest

from portfolio import instrument_policy as _instrument_policy

# Capture the canonical reader during collection, before the generic identity fixture.
_REAL_MACRO_READER = _instrument_policy._read_macro_json


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


def test_evaluate_gate_lens_exception_is_unknown_not_negative(bot_mcp, monkeypatch):
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


def test_evaluate_gate_malformed_synthesis_is_unknown(bot_mcp, monkeypatch):
    from portfolio import lenses

    monkeypatch.setattr(lenses, "full", lambda *_a, **_k: {"rows": [], "synthesis": {}})
    payload = _payload(asyncio.run(bot_mcp.evaluate_gate.handler({"ticker": "AAPL"})))
    assert payload["read_status"] == "unavailable"
    assert payload["passed"] is None


def test_evaluate_gate_nonfinite_confluence_is_unavailable(bot_mcp, monkeypatch):
    from portfolio import lenses

    monkeypatch.setattr(lenses, "full", lambda *_a, **_k: _matrix(authority="up", confluence=float("nan")))
    payload = _payload(asyncio.run(bot_mcp.evaluate_gate.handler({"ticker": "AAPL"})))
    assert payload["read_status"] == "unavailable"
    assert payload["passed"] is None


def test_evaluate_gate_legitimate_insufficient_data_stays_real_gate_result(bot_mcp, monkeypatch):
    from portfolio import lenses

    monkeypatch.setattr(lenses, "full", lambda *_a, **_k: _matrix(authority="insufficient_data", confluence=0.8))
    payload = _payload(asyncio.run(bot_mcp.evaluate_gate.handler({"ticker": "AAPL"})))
    assert payload["passed"] is False
    assert payload["size_authority"] == "insufficient_data"
    assert "read_status" not in payload
    assert "insufficient data" in payload["reason"].lower()


def test_evaluate_gate_healthy_up_shape_is_preserved(bot_mcp, monkeypatch):
    from portfolio import lenses

    monkeypatch.setattr(lenses, "full", lambda *_a, **_k: _matrix(authority="up", confluence=0.5))
    payload = _payload(asyncio.run(bot_mcp.evaluate_gate.handler({"ticker": "AAPL"})))
    assert payload["passed"] is True
    assert payload["confluence"] == 0.5
    assert payload["size_authority"] == "up"
    assert payload["vetoes"] == []
    assert "read_status" not in payload


def test_file_paper_unavailable_gate_never_persists(bot_mcp, monkeypatch, tmp_path):
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


def test_file_paper_blocked_gate_cannot_be_confirmed_or_persisted(bot_mcp, monkeypatch, tmp_path):
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


def test_file_paper_insufficient_data_cannot_turn_score_90_into_confirmed(bot_mcp, monkeypatch, tmp_path):
    from portfolio import lenses

    saved = _wire_paper_side_effects(monkeypatch, bot_mcp, tmp_path)
    monkeypatch.setattr(lenses, "full", lambda *_a, **_k: _matrix(
        authority="insufficient_data", confluence=1.0
    ))
    payload = _payload(asyncio.run(bot_mcp.file_research_paper.handler(_paper_args())))
    assert payload["error"] == "research_paper_preliminary_gate_failed"
    assert payload["paper_saved"] is False
    assert saved == []


def test_file_paper_valid_up_gate_preserves_success_and_persists(bot_mcp, monkeypatch, tmp_path):
    from portfolio import lenses

    saved = _wire_paper_side_effects(monkeypatch, bot_mcp, tmp_path)
    monkeypatch.setattr(lenses, "full", lambda *_a, **_k: _matrix(authority="up", confluence=0.5))
    raw = _text(asyncio.run(bot_mcp.file_research_paper.handler(_paper_args())))
    assert bot_mcp.PAPER_MARKER in raw
    assert len(saved) == 1
    assert saved[0]["confirmed"] is True
    assert saved[0]["combined"] >= 60


def test_add_proposal_rechecks_current_gate_and_refuses_blocked_legacy_paper(bot_mcp, monkeypatch):
    from brain import research_paper as rp
    from portfolio import advisor_trade, lenses

    monkeypatch.setattr(rp, "latest_for", lambda _ticker, **_kwargs: {"ticker": "AAPL", "confirmed": True})
    monkeypatch.setattr(lenses, "full", lambda *_a, **_k: _matrix(authority="blocked", confluence=0.9, vetoes=["parabolic"]))
    calls = []
    monkeypatch.setattr(advisor_trade, "propose_action", lambda *a, **k: calls.append((a, k)) or {"ok": True})
    raw = _text(asyncio.run(bot_mcp.propose_portfolio_action.handler({
        "ticker": "AAPL", "action": "add", "thesis": "x", "evidence": ["e"], "urgency": "routine"
    })))
    assert "REFUSED" in raw
    assert "preliminary" in raw.lower()
    assert calls == []


def test_add_proposal_paper_read_failure_is_closed_before_queue(bot_mcp, monkeypatch):
    from brain import research_paper as rp
    from portfolio import advisor_trade

    def explode(_ticker, **_kwargs):
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


def test_trim_remains_ungated_de_risking_proposal(bot_mcp, monkeypatch):
    from brain import research_paper as rp
    from portfolio import advisor_trade, lenses

    monkeypatch.setattr(rp, "latest_for", lambda _ticker, **_kwargs: (_ for _ in ()).throw(AssertionError("trim must not read paper")))
    monkeypatch.setattr(lenses, "full", lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("trim must not read ADD gate")))
    proposal = {"id": "p-trim", "ticker": "AAPL", "action": "trim"}
    monkeypatch.setattr(advisor_trade, "propose_action", lambda *a, **k: {"ok": True, "proposal": proposal, "note": "context only"})
    raw = _text(asyncio.run(bot_mcp.propose_portfolio_action.handler({
        "ticker": "AAPL", "action": "trim", "thesis": "risk", "evidence": ["e"], "urgency": "routine"
    })))
    assert "PROPOSAL_QUEUED" in raw


def test_add_proposal_confirmed_paper_and_current_up_gate_still_queues(bot_mcp, monkeypatch):
    from brain import research_paper as rp
    from portfolio import advisor_trade, lenses

    monkeypatch.setattr(rp, "latest_for", lambda _ticker, **_kwargs: {"ticker": "AAPL", "confirmed": True})
    monkeypatch.setattr(lenses, "full", lambda *_a, **_k: _matrix(authority="up", confluence=0.5))
    proposal = {"id": "p1", "ticker": "AAPL", "action": "add"}
    monkeypatch.setattr(advisor_trade, "propose_action", lambda *a, **k: {"ok": True, "proposal": proposal, "note": "context only"})
    raw = _text(asyncio.run(bot_mcp.propose_portfolio_action.handler({
        "ticker": "AAPL", "action": "add", "thesis": "x", "evidence": ["e"], "urgency": "routine"
    })))
    assert "PROPOSAL_QUEUED" in raw
    assert '"ticker": "AAPL"' in raw


@pytest.mark.parametrize(
    ("lens", "note"),
    [(None, "ok"), (7, "ok"), ("trend", {"secret": "do-not-return"})],
    ids=["null-lens", "numeric-lens", "mapping-note"],
)
def test_malformed_gate_display_stays_unavailable(bot_mcp, monkeypatch, lens, note):
    from portfolio import lenses

    matrix = _matrix()
    matrix["rows"] = [{"direction": "bull", "lens": lens, "note": note}]
    monkeypatch.setattr(lenses, "full", lambda *_a, **_k: matrix)
    raw = _text(asyncio.run(bot_mcp.evaluate_gate.handler({"ticker": "AAPL"})))
    payload = json.loads(raw)
    assert payload["error"] == "advisor_gate_unavailable"
    assert payload["passed"] is None
    assert "secret" not in raw and "do-not-return" not in raw


@pytest.mark.parametrize("malformation", ["cycle", "nonfinite"])
def test_nested_divergence_evidence_is_closed(bot_mcp, monkeypatch, malformation):
    from portfolio import lenses

    matrix = _matrix()
    evidence = []
    evidence.append(evidence if malformation == "cycle" else {"score": float("nan")})
    matrix["synthesis"]["divergences"] = evidence
    monkeypatch.setattr(lenses, "full", lambda *_a, **_k: matrix)
    payload = _payload(asyncio.run(bot_mcp.evaluate_gate.handler({"ticker": "AAPL"})))
    assert payload["error"] == "advisor_gate_unavailable"
    assert payload["passed"] is None


def _saved_paper(*, confirmed=True, generated_at="2026-09-17T20:00:00+00:00", identity="paper-old"):
    return {
        "id": identity, "ticker": "AAPL", "confirmed": confirmed,
        "generated_at": generated_at,
    }


def _wire_real_proposal(monkeypatch, tmp_path):
    from brain import research_paper as rp
    from portfolio import advisor_trade, instrument_policy, lenses

    papers = tmp_path / "papers"
    papers.mkdir()
    proposals = tmp_path / "recommendations.jsonl"
    monkeypatch.setattr(rp, "_PAPERS", papers)
    monkeypatch.setattr(advisor_trade, "_PROPOSALS", proposals)
    monkeypatch.setattr(instrument_policy, "_ROOT", tmp_path)
    monkeypatch.setattr(instrument_policy, "_read_macro_json", _REAL_MACRO_READER)
    identity = tmp_path / "vendor" / "macro" / "site" / "stockdata" / "AAPL.json"
    identity.parent.mkdir(parents=True)
    identity.write_text(json.dumps({
        "ticker": "AAPL", "name": "Apple Inc.", "security_type": "common_stock",
    }))
    monkeypatch.setattr(lenses, "full", lambda *_a, **_k: _matrix())
    return rp, papers, proposals


def _add(bot_mcp):
    return _text(asyncio.run(bot_mcp.propose_portfolio_action.handler({
        "ticker": "AAPL", "action": "add", "thesis": "Durable thesis.",
        "evidence": ["research:private-confirmed-paper"], "urgency": "routine",
    })))


@pytest.mark.parametrize("malformation", [
    "malformed_json", "unreadable", "directory", "dangling",
    "bad_shape", "bad_generation", "bad_ticker",
])
def test_actual_incomplete_paper_store_refuses_older_confirmed_fallback(
    bot_mcp, monkeypatch, tmp_path, malformation,
):
    rp, papers, proposals = _wire_real_proposal(monkeypatch, tmp_path)
    (papers / "old.json").write_text(json.dumps(_saved_paper()))
    target = papers / "new.json"
    new = _saved_paper(identity="paper-new", generated_at="2026-09-18T20:00:00+00:00")
    if malformation == "malformed_json":
        target.write_text("{secret-token=do-not-return")
    elif malformation == "unreadable":
        target.write_text(json.dumps(new))
        target.chmod(0)
    elif malformation == "directory":
        target.mkdir()
    elif malformation == "dangling":
        target.symlink_to(tmp_path / "absent-private-paper")
    elif malformation == "bad_shape":
        target.write_text("[]")
    elif malformation == "bad_generation":
        new["generated_at"] = "not-a-clock"
        target.write_text(json.dumps(new))
    elif malformation == "bad_ticker":
        new["ticker"] = {"secret": "do-not-return"}
        target.write_text(json.dumps(new))
    try:
        if malformation == "unreadable":
            with pytest.raises(PermissionError):
                target.read_text()
        raw = _add(bot_mcp)
        assert "REFUSED" in raw and "state is unavailable" in raw
        assert not proposals.exists()
        assert "secret-token" not in raw and "do-not-return" not in raw
        assert str(tmp_path) not in raw
        assert json.loads((papers / "old.json").read_text())["confirmed"] is True
    finally:
        if malformation == "unreadable":
            target.chmod(0o600)


@pytest.mark.parametrize("store_kind", ["missing_leaf", "missing_ancestor", "empty"])
def test_actual_absent_paper_store_is_no_confirmed_paper(
    bot_mcp, monkeypatch, tmp_path, store_kind,
):
    rp, papers, proposals = _wire_real_proposal(monkeypatch, tmp_path)
    if store_kind == "missing_leaf":
        papers.rmdir()
    elif store_kind == "missing_ancestor":
        monkeypatch.setattr(rp, "_PAPERS", tmp_path / "absent-parent" / "papers")
    raw = _add(bot_mcp)
    assert "no CONFIRMED research paper" in raw
    assert "unavailable" not in raw
    assert not proposals.exists()


@pytest.mark.parametrize("store_kind", [
    "dangling_leaf", "dangling_ancestor", "unreadable", "not_directory",
])
def test_actual_unavailable_paper_directory_is_not_absence(
    bot_mcp, monkeypatch, tmp_path, store_kind,
):
    rp, papers, proposals = _wire_real_proposal(monkeypatch, tmp_path)
    if store_kind == "dangling_leaf":
        papers.rmdir()
        papers.symlink_to(tmp_path / "absent-target", target_is_directory=True)
    elif store_kind == "dangling_ancestor":
        link = tmp_path / "linked-parent"
        link.symlink_to(tmp_path / "absent-target", target_is_directory=True)
        monkeypatch.setattr(rp, "_PAPERS", link / "papers")
    elif store_kind == "unreadable":
        papers.chmod(0)
    elif store_kind == "not_directory":
        papers.rmdir()
        papers.write_text("not a directory")
    try:
        if store_kind == "unreadable":
            with pytest.raises(PermissionError):
                list(papers.iterdir())
        raw = _add(bot_mcp)
        assert "REFUSED" in raw and "state is unavailable" in raw
        assert not proposals.exists()
        assert str(tmp_path) not in raw
    finally:
        if store_kind == "unreadable":
            papers.chmod(0o700)


@pytest.mark.parametrize("confirmed", [None, "false", 1, [], {}])
def test_actual_paper_requires_boolean_confirmation(
    bot_mcp, monkeypatch, tmp_path, confirmed,
):
    rp, papers, proposals = _wire_real_proposal(monkeypatch, tmp_path)
    (papers / "paper.json").write_text(json.dumps(_saved_paper(confirmed=confirmed)))
    raw = _add(bot_mcp)
    assert "REFUSED" in raw and "state is unavailable" in raw
    assert not proposals.exists()


def test_actual_unconfirmed_paper_remains_a_known_refusal(bot_mcp, monkeypatch, tmp_path):
    rp, papers, proposals = _wire_real_proposal(monkeypatch, tmp_path)
    (papers / "paper.json").write_text(json.dumps(_saved_paper(confirmed=False)))
    raw = _add(bot_mcp)
    assert "no CONFIRMED research paper" in raw and "unavailable" not in raw
    assert not proposals.exists()


def test_strict_latest_paper_uses_comparable_generation_clocks(bot_mcp, monkeypatch, tmp_path):
    rp, papers, proposals = _wire_real_proposal(monkeypatch, tmp_path)
    older = _saved_paper(confirmed=True, generated_at="2026-09-18T10:00:00+02:00")
    newer = _saved_paper(
        confirmed=False, generated_at="2026-09-18T09:00:00+00:00", identity="paper-new",
    )
    (papers / "older.json").write_text(json.dumps(older))
    (papers / "newer.json").write_text(json.dumps(newer))
    assert rp.latest_for("AAPL", strict=True)["id"] == "paper-new"
    # The default reader's historical string ordering is preserved for its callers.
    assert rp.latest_for("AAPL")["id"] == "paper-old"
    raw = _add(bot_mcp)
    assert "no CONFIRMED research paper" in raw and not proposals.exists()


def test_default_paper_reader_keeps_tolerant_read_compatibility(monkeypatch, tmp_path):
    from brain import research_paper as rp

    monkeypatch.setattr(rp, "_PAPERS", tmp_path)
    (tmp_path / "good.json").write_text(json.dumps(_saved_paper()))
    (tmp_path / "broken.json").write_text("{")
    assert rp.load_papers() == [_saved_paper()]
    with pytest.raises(json.JSONDecodeError):
        rp.load_papers(strict=True)


def test_actual_confirmed_gate_queues_only_a_nonexecuting_proposal(
    bot_mcp, monkeypatch, tmp_path,
):
    from portfolio import paper_account, position_log

    rp, papers, proposals = _wire_real_proposal(monkeypatch, tmp_path)
    paper = _saved_paper()
    canonical = papers / "paper.json"
    canonical.write_text(json.dumps(paper))
    before = canonical.read_bytes()
    monkeypatch.setattr(paper_account, "execute_fill", lambda *_a, **_k: pytest.fail("execution"))
    monkeypatch.setattr(position_log, "record_manual", lambda *_a, **_k: pytest.fail("ledger"))
    raw = _add(bot_mcp)
    assert "PROPOSAL_QUEUED" in raw and "no order was sized or filled" in raw
    row = json.loads(proposals.read_text())
    assert row["status"] == "proposed" and row["executed"] is False
    assert row["sizing_authority"] == "deterministic_scheduled_engine_only"
    assert not ({"weight", "size", "shares", "notional", "price", "fill"} & set(row))
    assert canonical.read_bytes() == before


def test_actual_proposal_keeps_instrument_identity_policy(bot_mcp, monkeypatch, tmp_path):
    rp, papers, proposals = _wire_real_proposal(monkeypatch, tmp_path)
    (papers / "paper.json").write_text(json.dumps(_saved_paper()))
    identity = tmp_path / "vendor" / "macro" / "site" / "stockdata" / "AAPL.json"
    identity.unlink()
    raw = _add(bot_mcp)
    assert "verified-common-stock-only" in raw
    assert not proposals.exists()


def test_exit_remains_ungated_de_risking_proposal(bot_mcp, monkeypatch):
    from brain import research_paper as rp
    from portfolio import advisor_trade, lenses

    monkeypatch.setattr(rp, "latest_for", lambda *_a, **_k: pytest.fail("exit paper read"))
    monkeypatch.setattr(lenses, "full", lambda *_a, **_k: pytest.fail("exit ADD gate"))
    monkeypatch.setattr(advisor_trade, "propose_action", lambda *a, **k: {
        "ok": True, "proposal": {"ticker": "AAPL", "action": "exit"}, "note": "context only",
    })
    raw = _text(asyncio.run(bot_mcp.propose_portfolio_action.handler({
        "ticker": "AAPL", "action": "exit", "thesis": "risk", "evidence": ["e"],
        "urgency": "routine",
    })))
    assert "PROPOSAL_QUEUED" in raw


@pytest.mark.parametrize("prior_present", [True, False])
def test_sdk_fixture_restores_module_and_package_identity(monkeypatch, prior_present):
    import brain

    with monkeypatch.context() as state:
        if prior_present:
            previous = types.ModuleType("brain.bot_mcp")
            state.setitem(sys.modules, "brain.bot_mcp", previous)
            state.setattr(brain, "bot_mcp", previous, raising=False)
        else:
            state.delitem(sys.modules, "brain.bot_mcp", raising=False)
            state.delattr(brain, "bot_mcp", raising=False)
        with pytest.raises(RuntimeError, match="fixture body"):
            with _bot_mcp_with_fake_sdk(monkeypatch):
                raise RuntimeError("fixture body")
        if prior_present:
            assert sys.modules["brain.bot_mcp"] is previous
            assert brain.bot_mcp is previous
        else:
            assert "brain.bot_mcp" not in sys.modules
            assert "bot_mcp" not in vars(brain)


@pytest.mark.parametrize("identity", [None, "", False, 0, [], {}])
def test_strict_paper_rejects_malformed_identity(bot_mcp, monkeypatch, tmp_path, identity):
    rp, papers, proposals = _wire_real_proposal(monkeypatch, tmp_path)
    paper = _saved_paper()
    paper["id"] = identity
    (papers / "paper.json").write_text(json.dumps(paper))
    raw = _add(bot_mcp)
    assert "state is unavailable" in raw
    assert not proposals.exists()


def test_cross_ticker_identity_collision_cannot_restore_old_confirmation(
    bot_mcp, monkeypatch, tmp_path,
):
    rp, papers, proposals = _wire_real_proposal(monkeypatch, tmp_path)
    (papers / "old.json").write_text(json.dumps(_saved_paper()))
    rejected = _saved_paper(
        confirmed=False, identity="shared", generated_at="2026-09-18T20:00:00+00:00",
    )
    other = _saved_paper(identity="shared", generated_at="2026-09-19T20:00:00+00:00")
    other["ticker"] = "MSFT"
    (papers / "rejected.json").write_text(json.dumps(rejected))
    (papers / "other.json").write_text(json.dumps(other))
    raw = _add(bot_mcp)
    assert "state is unavailable" in raw and not proposals.exists()


def test_conflicting_same_time_revisions_are_unavailable(bot_mcp, monkeypatch, tmp_path):
    rp, papers, proposals = _wire_real_proposal(monkeypatch, tmp_path)
    (papers / "old.json").write_text(json.dumps(_saved_paper()))
    rejected = _saved_paper(
        confirmed=False, identity="shared", generated_at="2026-09-18T20:00:00+00:00",
    )
    confirmed = dict(rejected, confirmed=True)
    (papers / "rejected.json").write_text(json.dumps(rejected))
    (papers / "confirmed.json").write_text(json.dumps(confirmed))
    raw = _add(bot_mcp)
    assert "state is unavailable" in raw and not proposals.exists()


def test_malformed_ticker_cannot_hide_a_newer_rejection(bot_mcp, monkeypatch, tmp_path):
    rp, papers, proposals = _wire_real_proposal(monkeypatch, tmp_path)
    (papers / "old.json").write_text(json.dumps(_saved_paper()))
    rejected = _saved_paper(
        confirmed=False, identity="new", generated_at="2026-09-18T20:00:00+00:00",
    )
    rejected["ticker"] = "AAPL "
    (papers / "rejected.json").write_text(json.dumps(rejected))
    raw = _add(bot_mcp)
    assert "state is unavailable" in raw and not proposals.exists()
