"""Proposal ingestion must never claim a thesis effect that the canonical ledger refused."""
from __future__ import annotations

import json


def _proposal(subject="NVDA", lean="add"):
    return {
        "source": "claude_cli",
        "status": "proposed",
        "subject": subject,
        "lean": lean,
        "conviction": "high",
        "horizon_d": 21,
        "thesis": f"{subject} thesis",
        "evidence": ["e1"],
        "prob_correct": 0.72,
        "logged_at": "2026-09-17T20:00:00+00:00",
    }


def _rows(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _wire(tmp_path, monkeypatch):
    from brain import ledger
    from brain import research_desk as rd

    queue = tmp_path / "proposals.jsonl"
    ledger_path = tmp_path / "theses.jsonl"
    monkeypatch.setattr(rd, "_PROPOSALS", queue)
    monkeypatch.setattr(ledger, "_LEDGER", ledger_path)
    monkeypatch.setattr(rd, "_engine_blocked", lambda _subject: False)
    return rd, ledger, queue


def test_duplicate_open_subject_is_deduplicated_to_existing_thesis(tmp_path, monkeypatch):
    rd, ledger, queue = _wire(tmp_path, monkeypatch)
    assert ledger.append({"id": "existing-nvda", "subject": "NVDA", "lean": "watch"}) is True
    queue.write_text(json.dumps(_proposal("NVDA")) + "\n")

    out = rd.ingest_proposals(asof="2026-09-17")

    assert out["ingested"] == 0
    assert out["deduplicated"] == 1
    assert out["theses"][0]["appended"] is False
    assert out["theses"][0]["id"] == "existing-nvda"
    rows = _rows(queue)
    assert rows[0]["status"] == "deduplicated"
    assert rows[0]["thesis_id"] == "existing-nvda"
    assert rows[0]["proposed_thesis_id"] != "existing-nvda"


def test_duplicate_refusal_does_not_write_phantom_sql_thesis(tmp_path, monkeypatch):
    rd, ledger, queue = _wire(tmp_path, monkeypatch)
    assert ledger.append({"id": "existing-aapl", "subject": "AAPL", "lean": "watch"}) is True
    queue.write_text(json.dumps(_proposal("AAPL")) + "\n")

    from data_layer import store
    sql_writes = []
    monkeypatch.setattr(store, "insert_thesis", lambda _con, doc: sql_writes.append(dict(doc)) or True)

    out = rd.ingest_proposals(asof="2026-09-17", con=object())

    assert out["ingested"] == 0
    assert out["deduplicated"] == 1
    assert sql_writes == []


def test_same_batch_duplicate_links_to_first_real_thesis(tmp_path, monkeypatch):
    rd, ledger, queue = _wire(tmp_path, monkeypatch)
    queue.write_text(
        json.dumps(_proposal("MSFT", "add")) + "\n" +
        json.dumps(_proposal("MSFT", "overweight")) + "\n"
    )

    out = rd.ingest_proposals(asof="2026-09-17")

    assert out["ingested"] == 1
    assert out["deduplicated"] == 1
    assert out["theses"][0]["appended"] is True
    assert out["theses"][1]["appended"] is False
    assert out["theses"][1]["id"] == out["theses"][0]["id"]
    rows = _rows(queue)
    assert [row["status"] for row in rows] == ["ingested", "deduplicated"]
    assert rows[1]["thesis_id"] == rows[0]["thesis_id"]
    assert len(ledger.all_theses()) == 1


def test_ledger_append_receipt_keeps_bool_append_api_compatible(tmp_path, monkeypatch):
    from brain import ledger
    monkeypatch.setattr(ledger, "_LEDGER", tmp_path / "theses.jsonl")

    first = ledger.append_receipt({"id": "d1", "subject": "NVDA", "lean": "add"})
    second = ledger.append_receipt({"id": "d2", "subject": "NVDA", "lean": "watch"})

    assert first == {"appended": True, "thesis_id": "d1", "reason": None}
    assert second == {"appended": False, "thesis_id": "d1", "reason": "open_subject_exists"}
    assert ledger.append({"id": "d3", "subject": "MSFT", "lean": "add"}) is True
    assert ledger.append({"id": "d4", "subject": "MSFT", "lean": "watch"}) is False
