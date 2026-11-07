"""Research-desk escalation must distinguish clean, blocked, and unavailable engine evidence."""
from __future__ import annotations

import json

import pytest


def _proposal(*, subject="NVDA", lean="add"):
    return {
        "subject": subject,
        "lean": lean,
        "conviction": "high",
        "prob_correct": 0.75,
        "horizon_d": 21,
        "thesis": "model thesis",
        "evidence": ["model:e1"],
        "status": "proposed",
    }


def _wire_paths(monkeypatch, rd, ledger, tmp_path, rows):
    proposals = tmp_path / "proposals.jsonl"
    proposals.write_text("".join(json.dumps(r) + "\n" for r in rows))
    monkeypatch.setattr(rd, "_PROPOSALS", proposals)
    monkeypatch.setattr(ledger, "_LEDGER", tmp_path / "theses.jsonl")
    return proposals


def _healthy_matrix(*, authority="up", vetoes=None):
    return {
        "rows": [{"lens": "trend", "direction": "bull"}],
        "synthesis": {
            "size_authority": authority,
            "vetoes": list(vetoes or []),
            "confluence": 0.5,
            "divergences": [],
        },
    }


def test_engine_blocked_exception_is_unknown_not_clean(monkeypatch):
    from brain import research_desk as rd
    from portfolio import lenses

    monkeypatch.setattr(lenses, "full", lambda *_a, **_k: (_ for _ in ()).throw(
        RuntimeError("secret /Users/private/lens token=do-not-return")
    ))
    assert rd._engine_blocked("NVDA") is None


def test_engine_blocked_malformed_synthesis_is_unknown(monkeypatch):
    from brain import research_desk as rd
    from portfolio import lenses

    monkeypatch.setattr(lenses, "full", lambda *_a, **_k: {"rows": [], "synthesis": {}})
    assert rd._engine_blocked("NVDA") is None


def test_engine_blocked_valid_clean_and_blocked_states_stay_boolean(monkeypatch):
    from brain import research_desk as rd
    from portfolio import lenses

    monkeypatch.setattr(lenses, "full", lambda *_a, **_k: _healthy_matrix(authority="up"))
    assert rd._engine_blocked("NVDA") is False
    monkeypatch.setattr(lenses, "full", lambda *_a, **_k: _healthy_matrix(
        authority="blocked", vetoes=["parabolic"]
    ))
    assert rd._engine_blocked("NVDA") is True


def test_unknown_engine_state_deescalates_bullish_proposal_to_watch(tmp_path, monkeypatch):
    from brain import ledger
    from brain import research_desk as rd
    from portfolio import lenses

    proposals = _wire_paths(monkeypatch, rd, ledger, tmp_path, [_proposal(lean="add")])
    monkeypatch.setattr(lenses, "full", lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("lens down")))

    out = rd.ingest_proposals(asof="2026-09-17")

    assert out["ingested"] == 1
    assert out["theses"][0]["lean"] == "watch"
    assert out["theses"][0]["clamped"] is True
    stored = ledger.all_theses()[0]
    assert stored["lean"] == "watch"
    assert stored["conviction"] == "low"
    assert "unavailable" in (stored.get("dissent") or "").lower()
    persisted = [json.loads(line) for line in proposals.read_text().splitlines() if line.strip()]
    assert persisted[0]["status"] == "ingested"


def test_unknown_engine_state_does_not_make_bearish_thesis_more_bullish(tmp_path, monkeypatch):
    from brain import ledger
    from brain import research_desk as rd
    from portfolio import lenses

    _wire_paths(monkeypatch, rd, ledger, tmp_path, [_proposal(lean="underweight")])
    monkeypatch.setattr(lenses, "full", lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("lens down")))

    out = rd.ingest_proposals(asof="2026-09-17")

    assert out["ingested"] == 1
    assert out["theses"][0]["lean"] == "underweight"
    assert out["theses"][0]["clamped"] is False
    stored = ledger.all_theses()[0]
    assert stored["lean"] == "underweight"
    assert stored["conviction"] == "high"


def test_explicit_block_still_clamps_without_needing_engine_read(tmp_path, monkeypatch):
    from brain import ledger
    from brain import research_desk as rd

    _wire_paths(monkeypatch, rd, ledger, tmp_path, [_proposal(subject="TSLA", lean="overweight")])
    monkeypatch.setattr(rd, "_engine_blocked", lambda _subject: (_ for _ in ()).throw(
        AssertionError("explicit blocked set must short-circuit engine read")
    ))

    out = rd.ingest_proposals(asof="2026-09-17", blocked={"TSLA"})

    assert out["theses"][0]["lean"] == "watch"
    assert out["theses"][0]["clamped"] is True


@pytest.mark.parametrize("vetoes", [
    [None], [True], [7], [{}], [[]], [""], ["   "], ["parabolic", None],
])
def test_malformed_veto_member_is_unavailable(monkeypatch, vetoes):
    from brain import research_desk as rd
    from portfolio import lenses

    matrix = _healthy_matrix()
    matrix["synthesis"]["vetoes"] = vetoes
    monkeypatch.setattr(lenses, "full", lambda *_a, **_k: matrix)

    assert rd._engine_blocked("NVDA") is None


@pytest.mark.parametrize("vetoes", [[None], ["parabolic", None]])
def test_malformed_veto_evidence_persists_unavailable_dissent(tmp_path, monkeypatch, vetoes):
    from brain import ledger
    from brain import research_desk as rd
    from portfolio import lenses

    proposals = _wire_paths(monkeypatch, rd, ledger, tmp_path, [_proposal()])
    matrix = _healthy_matrix()
    matrix["synthesis"]["vetoes"] = vetoes
    monkeypatch.setattr(lenses, "full", lambda *_a, **_k: matrix)

    out = rd.ingest_proposals(asof="2026-09-17")

    assert out["ingested"] == 1
    assert out["theses"][0]["appended"] is True
    assert out["theses"][0]["clamped"] is True
    stored = ledger.all_theses()[0]
    assert stored["lean"] == "watch"
    assert stored["conviction"] == "low"
    dissent = stored["dissent"].lower()
    assert "unavailable" in dissent
    assert "engine-blocked" not in dissent
    assert stored["falsifier"]["check"]["kind"] == "none"
    assert json.loads(proposals.read_text().strip())["status"] == "ingested"
    assert rd.ingest_proposals(asof="2026-09-17")["ingested"] == 0
    assert len(ledger.all_theses()) == 1


@pytest.mark.parametrize("authority", ["up", "down", "hold", "insufficient_data"])
def test_valid_unblocked_evidence_preserves_actual_bullish_ingestion(tmp_path, monkeypatch, authority):
    from brain import ledger
    from brain import research_desk as rd
    from portfolio import lenses

    _wire_paths(monkeypatch, rd, ledger, tmp_path, [_proposal()])
    monkeypatch.setattr(lenses, "full", lambda *_a, **_k: _healthy_matrix(authority=authority))

    out = rd.ingest_proposals(asof="2026-09-17")

    assert out["ingested"] == 1
    assert out["theses"][0]["appended"] is True
    assert out["theses"][0]["clamped"] is False
    stored = ledger.all_theses()[0]
    assert stored["lean"] == "add"
    assert stored["conviction"] == "high"
    assert not stored["dissent"]
    assert stored["falsifier"]["check"]["kind"] == "rel_return"


@pytest.mark.parametrize("authority,vetoes", [("blocked", []), ("up", ["parabolic"])])
def test_valid_block_evidence_persists_engine_blocked_dissent(tmp_path, monkeypatch, authority, vetoes):
    from brain import ledger
    from brain import research_desk as rd
    from portfolio import lenses

    _wire_paths(monkeypatch, rd, ledger, tmp_path, [_proposal()])
    monkeypatch.setattr(lenses, "full", lambda *_a, **_k: _healthy_matrix(
        authority=authority, vetoes=vetoes,
    ))

    out = rd.ingest_proposals(asof="2026-09-17")

    assert out["ingested"] == 1
    assert out["theses"][0]["appended"] is True
    assert out["theses"][0]["clamped"] is True
    stored = ledger.all_theses()[0]
    assert stored["lean"] == "watch"
    assert stored["conviction"] == "low"
    dissent = stored["dissent"].lower()
    assert "engine-blocked" in dissent
    assert "unavailable" not in dissent


@pytest.mark.parametrize("lean", ["underweight", "watch"])
def test_malformed_veto_evidence_preserves_nonbullish_thesis(tmp_path, monkeypatch, lean):
    from brain import ledger
    from brain import research_desk as rd
    from portfolio import lenses

    _wire_paths(monkeypatch, rd, ledger, tmp_path, [_proposal(lean=lean)])
    matrix = _healthy_matrix()
    matrix["synthesis"]["vetoes"] = [None]
    monkeypatch.setattr(lenses, "full", lambda *_a, **_k: matrix)

    out = rd.ingest_proposals(asof="2026-09-17")

    assert out["ingested"] == 1
    assert out["theses"][0]["appended"] is True
    assert out["theses"][0]["clamped"] is False
    stored = ledger.all_theses()[0]
    assert stored["lean"] == lean
    assert stored["conviction"] == "high"
    assert not stored["dissent"]
