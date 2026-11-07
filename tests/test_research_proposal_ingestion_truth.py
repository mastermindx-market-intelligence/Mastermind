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


import pytest


_MISSING_ID = object()
_INVALID_IDS = [
    pytest.param(_MISSING_ID, id="missing"),
    pytest.param(None, id="null"),
    pytest.param(True, id="boolean"),
    pytest.param(7, id="integer"),
    pytest.param(7.5, id="float"),
    pytest.param("", id="empty"),
    pytest.param(" \t\n", id="whitespace"),
]


def _identified_row(identity, subject="NVDA", **extra):
    row = {"subject": subject, "lean": "watch", **extra}
    if identity is not _MISSING_ID:
        row["id"] = identity
    return row


@pytest.mark.parametrize("identity", _INVALID_IDS)
@pytest.mark.parametrize("already_open", [False, True])
def test_invalid_new_identity_never_appends_or_deduplicates(
    tmp_path, monkeypatch, identity, already_open
):
    _rd, ledger, _queue = _wire(tmp_path, monkeypatch)
    prior = _identified_row("canonical", "NVDA" if already_open else "MSFT")
    previous = json.dumps(prior) + "\n"
    ledger._LEDGER.write_text(previous)

    with pytest.raises(ValueError, match="thesis id"):
        ledger.append_receipt(_identified_row(identity))

    assert ledger._LEDGER.read_text() == previous
    assert not list(tmp_path.glob(".*.tmp"))


@pytest.mark.parametrize("identity", _INVALID_IDS)
def test_invalid_existing_identity_cannot_advance_queue_or_sql(tmp_path, monkeypatch, identity):
    rd, ledger, queue = _wire(tmp_path, monkeypatch)
    previous_ledger = json.dumps(_identified_row(identity)) + "\n"
    previous_queue = json.dumps(_proposal()) + "\n"
    ledger._LEDGER.write_text(previous_ledger)
    queue.write_text(previous_queue)
    from data_layer import store
    sql_writes = []
    monkeypatch.setattr(store, "insert_thesis", lambda _con, doc: sql_writes.append(doc))

    with pytest.raises(ValueError, match="thesis id"):
        rd.ingest_proposals(asof="2026-09-17", con=object())

    assert sql_writes == []
    assert ledger._LEDGER.read_text() == previous_ledger
    assert queue.read_text() == previous_queue


@pytest.mark.parametrize("same_id", [False, True])
def test_ambiguous_open_identity_is_not_arbitrarily_selected(tmp_path, monkeypatch, same_id):
    rd, ledger, queue = _wire(tmp_path, monkeypatch)
    previous_ledger = "".join(json.dumps(row) + "\n" for row in [
        _identified_row("first"),
        _identified_row("first" if same_id else "second", status="open"),
    ])
    previous_queue = json.dumps(_proposal()) + "\n"
    ledger._LEDGER.write_text(previous_ledger)
    queue.write_text(previous_queue)
    from data_layer import store
    sql_writes = []
    monkeypatch.setattr(store, "insert_thesis", lambda _con, doc: sql_writes.append(doc))

    with pytest.raises(ValueError, match="multiple open theses"):
        rd.ingest_proposals(asof="2026-09-17", con=object())

    assert sql_writes == []
    assert ledger._LEDGER.read_text() == previous_ledger
    assert queue.read_text() == previous_queue


def test_missing_open_subject_evidence_is_not_silently_skipped(tmp_path, monkeypatch):
    _rd, ledger, _queue = _wire(tmp_path, monkeypatch)
    previous = json.dumps({"id": "unattributed", "status": "open"}) + "\n"
    ledger._LEDGER.write_text(previous)

    with pytest.raises(KeyError, match="subject"):
        ledger.append_receipt(_identified_row("new"))

    assert ledger._LEDGER.read_text() == previous


def test_receipt_identity_is_the_captured_canonical_row(tmp_path, monkeypatch):
    _rd, ledger, _queue = _wire(tmp_path, monkeypatch)
    doc = _identified_row("captured")
    original_write = ledger._atomic_write

    def write_and_mutate_caller(rows):
        original_write(rows)
        doc["id"] = "caller-mutated-after-publication"
        doc["subject"] = "MSFT"

    monkeypatch.setattr(ledger, "_atomic_write", write_and_mutate_caller)
    receipt = ledger.append_receipt(doc)

    assert receipt == {"appended": True, "thesis_id": "captured", "reason": None}
    assert ledger.all_theses() == [{"id": "captured", "subject": "NVDA", "lean": "watch", "status": "open"}]
    assert doc["id"] != receipt["thesis_id"]


def test_valid_identity_spelling_and_boolean_compatibility_are_exact(tmp_path, monkeypatch):
    _rd, ledger, _queue = _wire(tmp_path, monkeypatch)
    identity = "  exact-canonical-id\t"
    first = ledger.append_receipt(_identified_row(identity))
    duplicate = ledger.append_receipt(_identified_row("proposed-only"))

    assert first == {"appended": True, "thesis_id": identity, "reason": None}
    assert duplicate == {"appended": False, "thesis_id": identity, "reason": "open_subject_exists"}
    assert type(first["appended"]) is bool and type(duplicate["appended"]) is bool
    assert ledger.all_theses()[0]["id"] == identity
    assert ledger.append(_identified_row("another", "MSFT")) is True
    assert ledger.append(_identified_row("rejected", "MSFT")) is False
    previous = ledger._LEDGER.read_text()
    with pytest.raises(ValueError, match="thesis id"):
        ledger.append(_identified_row(None, "AAPL"))
    assert ledger._LEDGER.read_text() == previous


def test_dedup_metadata_describes_rejected_proposal_not_canonical_thesis(tmp_path, monkeypatch):
    rd, ledger, queue = _wire(tmp_path, monkeypatch)
    assert ledger.append(_identified_row("canonical-watch")) is True
    previous_ledger = ledger._LEDGER.read_text()
    queue.write_text(json.dumps(_proposal(lean="add")) + "\n")

    out = rd.ingest_proposals(asof="2026-09-17")
    item = out["theses"][0]

    assert item["id"] == "canonical-watch" and item["appended"] is False
    assert item["deduplicated"] is True and item["proposed_id"] != item["id"]
    assert "lean" not in item and "falsifier_kind" not in item
    assert item["proposed_lean"] == "add"
    assert item["proposed_falsifier_kind"] == "rel_return"
    assert item["clamped"] is False and out["clamped"] == 0
    assert ledger._LEDGER.read_text() == previous_ledger


def _connect_private_store(tmp_path, monkeypatch):
    from data_layer import store
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr(store, "_DB", tmp_path / "projection.db")
    return store, store.connect()


def test_same_batch_has_one_real_sql_projection_and_canonical_binding(tmp_path, monkeypatch):
    rd, ledger, queue = _wire(tmp_path, monkeypatch)
    store, con = _connect_private_store(tmp_path, monkeypatch)
    sql_calls = []
    original_insert = store.insert_thesis

    def insert(connection, doc):
        sql_calls.append(dict(doc))
        return original_insert(connection, doc)

    monkeypatch.setattr(store, "insert_thesis", insert)
    queue.write_text(json.dumps(_proposal("MSFT", "add")) + "\n"
                     + json.dumps(_proposal("MSFT", "overweight")) + "\n")
    try:
        out = rd.ingest_proposals(asof="2026-09-17", con=con)
        rows = [dict(row) for row in con.execute("SELECT id,subject,lean,status FROM theses")]
        assert out["ingested"] == 1 and out["deduplicated"] == 1
        assert len(sql_calls) == 1
        canonical = ledger.all_theses()
        assert len(canonical) == 1
        identity = canonical[0]["id"]
        assert rows == [{"id": identity, "subject": "MSFT", "lean": "add", "status": "open"}]
        assert sql_calls[0]["id"] == identity
        assert [item["id"] for item in out["theses"]] == [identity, identity]
        assert set(out["theses"][0]) == {
            "id", "subject", "lean", "clamped", "appended", "falsifier_kind",
        }
        assert out["theses"][1]["proposed_lean"] == "overweight"
        assert [row["thesis_id"] for row in _rows(queue)] == [identity, identity]
        assert [row["status"] for row in _rows(queue)] == ["ingested", "deduplicated"]
        again = rd.ingest_proposals(asof="2026-09-17", con=con)
        assert again["ingested"] == 0 and "deduplicated" not in again
        assert len(sql_calls) == 1
    finally:
        con.close()


@pytest.mark.parametrize("outcome_unknown", [False, True])
def test_queue_mark_failure_retains_exact_append_and_dedup_receipts(
    tmp_path, monkeypatch, outcome_unknown
):
    rd, ledger, queue = _wire(tmp_path, monkeypatch)
    _store, con = _connect_private_store(tmp_path, monkeypatch)
    previous = json.dumps(_proposal()) + "\n" + json.dumps(_proposal(lean="overweight")) + "\n"
    queue.write_text(previous)
    original_write = rd._atomic_write_proposals
    writes = []

    def failed_mark(path, rows):
        writes.append(path)
        if outcome_unknown:
            original_write(path, rows)
            raise OSError("controlled exception after queue publication")
        raise rd._ProposalQueueNotCommittedError("controlled failure before queue publication")

    monkeypatch.setattr(rd, "_atomic_write_proposals", failed_mark)
    try:
        out = rd.ingest_proposals(asof="2026-09-17", con=con)
        identity = ledger.all_theses()[0]["id"]
        assert out["ingested"] == 1 and out["deduplicated"] == 1
        assert [item["appended"] for item in out["theses"]] == [True, False]
        assert [item["id"] for item in out["theses"]] == [identity, identity]
        assert out["proposal_rows_marked"] is (None if outcome_unknown else False)
        assert out["proposal_queue_status"] == ("unknown" if outcome_unknown else "unavailable")
        assert writes == [queue]
        assert [row["id"] for row in con.execute("SELECT id FROM theses")] == [identity]
        if outcome_unknown:
            assert [row["status"] for row in _rows(queue)] == ["ingested", "deduplicated"]
        else:
            assert queue.read_text() == previous
    finally:
        con.close()


def test_later_invalid_identity_preserves_earlier_effect_for_reconciliation(tmp_path, monkeypatch):
    rd, ledger, queue = _wire(tmp_path, monkeypatch)
    previous_ledger = json.dumps(_identified_row(None, "MSFT")) + "\n"
    ledger._LEDGER.write_text(previous_ledger)
    previous_queue = json.dumps(_proposal("NVDA")) + "\n" + json.dumps(_proposal("MSFT")) + "\n"
    queue.write_text(previous_queue)
    _store, con = _connect_private_store(tmp_path, monkeypatch)
    try:
        with pytest.raises(ValueError, match="thesis id"):
            rd.ingest_proposals(asof="2026-09-17", con=con)
        canonical = ledger.all_theses()
        assert len(canonical) == 2
        assert canonical[0] == _identified_row(None, "MSFT")
        assert canonical[1]["subject"] == "NVDA" and canonical[1]["status"] == "open"
        assert [row["id"] for row in con.execute("SELECT id FROM theses")] == [canonical[1]["id"]]
        assert queue.read_text() == previous_queue
    finally:
        con.close()
