"""Bounded lesson -> later accepted decision -> settled outcome trace contracts."""
from __future__ import annotations

import importlib
import json

import pytest

from brain import portfolio_learning as pl


def _lesson_file(tmp_path, book: str, code: str = "churn_hysteresis") -> str:
    scope = pl.BOOK_SCOPES[book]
    lesson_id = f"lesson.v1.{scope}.{code}"
    pl._write_json(
        tmp_path / book / "lessons.json",
        {
            "metrics": {},
            "lessons": [{
                "id": lesson_id,
                "code": code,
                "scope": scope,
                "source_book": book,
                "shareability": "market_specific",
                "status": "requested",
                "approval_status": "requested",
                "authority": pl.LESSON_AUTHORITY,
                "evidence_status": "threshold_met",
                "rule": "Require an explicit falsifier before a very early reversal.",
                "evidence": {"n": 12},
            }],
        },
    )
    return lesson_id


def _submission(lesson_ids: object, *, ticker: str = "AAPL") -> dict:
    return {
        "schema": "mastermind.target_book.v2",
        "holdings": [{
            "ticker": ticker,
            "weight": 0.20,
            "prior_target_weight": 0.0,
            "action_requested": "add",
            "action_effective": "add",
        }],
        "exit_decisions": [],
        "summary": "A complete accepted target with a measured behavioural change.",
        "decision_memo": {"lessons_applied": lesson_ids},
    }


def test_lesson_ids_scopes_and_cross_market_candidate_never_self_approve(monkeypatch, tmp_path):
    monkeypatch.setattr(pl, "_DIR", tmp_path)
    monkeypatch.setattr(pl, "_behaviour", lambda book: {
        "closed_n": 10,
        "three_days_or_less_n": 5,
        "post_sell": {},
        "cash": 0.20,
    })

    us = pl.derive_lessons("autonomous")["lessons"][0]
    cn = pl.derive_lessons("china")["lessons"][0]

    assert us["id"] == "lesson.v1.US_ONLY.churn_hysteresis"
    assert cn["id"] == "lesson.v1.CN_ONLY.churn_hysteresis"
    assert us["status"] == us["approval_status"] == "requested"
    assert us["authority"] == "research_request_only"

    candidate = pl._validated_universal_lessons()[0]
    assert candidate["id"] == "lesson.v1.CROSS_MARKET_CANDIDATE.churn_hysteresis"
    assert candidate["scope"] == "CROSS_MARKET_CANDIDATE"
    assert candidate["validated_in_books"] == ["autonomous", "china"]
    assert candidate["status"] == candidate["approval_status"] == "requested"
    assert candidate["authority"] == "research_request_only"

    pl._write_json(tmp_path / "operator_lesson_state.json", {"lessons": [{
        "id": us["id"],
        "status": "approved",
        "approved_by": "operator:test",
        "approved_at": "2026-08-11T12:00:00Z",
    }]})
    approved = next(row for row in pl.accessible_lessons("autonomous") if row["id"] == us["id"])
    assert approved["approval_status"] == approved["status"] == "approved"
    assert approved["authority"] == "operator_approved_advisory"
    assert approved["approved_by"] == "operator:test"


def test_only_exact_persisted_presented_ids_are_citeable(monkeypatch, tmp_path):
    monkeypatch.setattr(pl, "_DIR", tmp_path)
    us_id = _lesson_file(tmp_path, "autonomous")
    foreign_id = _lesson_file(tmp_path, "china")

    block = pl.prompt_block("autonomous", asof="2026-08-11")
    assert us_id in block
    assert foreign_id not in block
    presentation = pl._latest_presentation("autonomous", "2026-08-11")
    assert presentation["lesson_ids"] == [us_id]
    assert presentation["evidence_cohort"] == "portfolio_v2_lesson_trace"
    initial_submission = _submission([us_id])
    initial_trace = pl.attach_lesson_trace(
        "autonomous", "2026-08-11", initial_submission
    )
    assert initial_trace["ok"] is True

    # The identity seals what was presented, not merely the stable lesson id. Same-day evidence
    # or rule changes must create a distinct snapshot instead of deduping onto stale content.
    changed = json.loads((tmp_path / "autonomous" / "lessons.json").read_text())
    changed["lessons"][0]["rule"] = "Require two independent falsifiers before reversal."
    changed["lessons"][0]["evidence"] = {"n": 13}
    pl._write_json(tmp_path / "autonomous" / "lessons.json", changed)
    pl.prompt_block("autonomous", asof="2026-08-11")
    changed_presentation = pl._latest_presentation("autonomous", "2026-08-11")
    assert changed_presentation["presentation_id"] != presentation["presentation_id"]
    assert changed_presentation["lessons"][0]["rule"] == (
        "Require two independent falsifiers before reversal."
    )
    assert changed_presentation["lessons"][0]["evidence"] == {"n": 13}

    valid = _submission([us_id])
    first = pl.attach_lesson_trace("autonomous", "2026-08-11", valid)
    second = pl.prepare_lesson_trace("autonomous", "2026-08-11", valid)
    assert first["ok"] is True
    assert first["decision_id"] == second["decision_id"]
    assert first["application_id"] == second["application_id"]
    assert first["decision_id"] != initial_trace["decision_id"]
    assert first["application_id"] != initial_trace["application_id"]

    foreign = pl.attach_lesson_trace(
        "autonomous", "2026-08-11", _submission([foreign_id])
    )
    unknown = pl.attach_lesson_trace(
        "autonomous",
        "2026-08-11",
        _submission(["lesson.v1.US_ONLY.unknown_mechanism"]),
    )
    malformed = pl.attach_lesson_trace(
        "autonomous", "2026-08-11", _submission({"id": us_id})
    )
    assert foreign["ok"] is unknown["ok"] is malformed["ok"] is False
    assert foreign["error"] == unknown["error"] == "lesson_id_not_presented_or_foreign"
    assert malformed["error"] == "non_empty_lessons_applied_must_be_an_array"

    # Missing/legacy-empty values mean "no lesson cited" and remain backward-compatible.
    empty = pl.attach_lesson_trace("autonomous", "2026-08-11", _submission([]))
    legacy_empty = pl.attach_lesson_trace("autonomous", "2026-08-11", _submission({}))
    assert empty == legacy_empty == {
        "ok": True, "cited_ids": [], "application_required": False,
    }


def test_application_is_created_only_after_acceptance_and_is_idempotent(monkeypatch, tmp_path):
    monkeypatch.setattr(pl, "_DIR", tmp_path)
    lesson_id = _lesson_file(tmp_path, "autonomous")
    pl.prompt_block("autonomous", asof="2026-08-11")
    submission = _submission([lesson_id])
    assert pl.attach_lesson_trace("autonomous", "2026-08-11", submission)["ok"]

    rejected = pl.record_application(
        "autonomous",
        "2026-08-11",
        submission,
        {"AAPL": 0.20},
        target_status="rejected_packet_gate",
    )
    assert rejected == {"ok": True, "recorded": False, "reason": "target_not_accepted"}
    assert not (tmp_path / "autonomous" / "applications.jsonl").exists()
    rejected_links = pl.trace_links(submission, target_status="rejected_packet_gate")
    assert rejected_links["lesson_trace_status"] == "planned_not_accepted"
    assert "decision_id" not in rejected_links
    assert "lesson_application_ids" not in rejected_links
    assert rejected_links["planned_lesson_application_id"].startswith("application.v1.")
    pending_links = pl.trace_links(submission, target_status="queued")
    assert pending_links["lesson_trace_status"] == "accepted_application_pending"
    assert "lesson_application_ids" not in pending_links

    queued = pl.record_application(
        "autonomous",
        "2026-08-11",
        submission,
        {"AAPL": 0.20},
        target_status="queued",
    )
    replay = pl.record_application(
        "autonomous",
        "2026-08-11",
        submission,
        {"AAPL": 0.20},
        target_status="queued",
    )
    assert queued["recorded"] is True and queued["application"]["executed"] is False
    assert replay["deduplicated"] is True
    accepted_links = pl.trace_links(submission, target_status="queued")
    assert accepted_links["lesson_trace_status"] == "accepted_queued"
    assert accepted_links["lesson_application_ids"] == [queued["application"]["application_id"]]
    assert queued["application"]["lesson_basis"][0]["rule"] == (
        "Require an explicit falsifier before a very early reversal."
    )
    assert queued["application"]["lesson_basis"][0]["shareability"] == "market_specific"
    material = queued["application"]["material_difference"]
    assert material["adds"] == ["AAPL"]
    assert material["weights"] == {"AAPL": 0.2}
    assert material["no_change"] is False
    rows = (tmp_path / "autonomous" / "applications.jsonl").read_text().splitlines()
    assert len(rows) == 1


def test_queued_application_executes_only_via_exact_hash_bound_receipt(monkeypatch, tmp_path):
    from portfolio import paper_account, registry

    monkeypatch.setattr(pl, "_DIR", tmp_path / "learning")
    monkeypatch.setattr(registry, "_ROOT", tmp_path / "runtime")
    lesson_id = _lesson_file(tmp_path / "learning", "autonomous")
    pl.prompt_block("autonomous", asof="2026-08-11")
    submission = _submission([lesson_id])
    pl.attach_lesson_trace("autonomous", "2026-08-11", submission)

    paper_account._save_account(
        {
            "inception_date": "2026-08-01",
            "starting_nav": 1_000_000.0,
            "cash": 1_000_000.0,
            "positions": {},
            "spy_shares": None,
            "spy_inception_price": None,
        },
        "autonomous",
    )
    target = {"AAPL": 0.20}
    paper_account.save_pending_target(
        target,
        "2026-08-11",
        portfolio_id="autonomous",
        decision_snapshot=submission,
    )
    queued = pl.record_application(
        "autonomous",
        "2026-08-11",
        submission,
        target,
        target_status="queued",
    )["application"]
    assert queued["executed"] is False

    paper_account.settle_target(
        {"AAPL": 100.0, "SPY": 700.0},
        "2026-08-12",
        portfolio_id="autonomous",
    )
    receipt = paper_account.pending_settlement_receipts("autonomous")[0]
    assert receipt["target_sha256"] == queued["target_sha256"]

    transitioned = pl.settle_application("autonomous", submission, "2026-08-12")
    replay = pl.settle_application("autonomous", submission, "2026-08-12")
    assert transitioned["ok"] is True and transitioned["transitioned"] is True
    assert transitioned["application"]["executed"] is True
    assert transitioned["application"]["settlement_verified"] is True
    assert transitioned["application"]["settlement_transaction_id"] == receipt["transaction_id"]
    assert replay["deduplicated"] is True
    finalization = pl.application_finalization_status(
        "autonomous",
        submission,
        settlement_receipt_id=receipt["transaction_id"],
    )
    assert finalization["ok"] is True
    rows = (tmp_path / "learning" / "autonomous" / "applications.jsonl").read_text().splitlines()
    assert len(rows) == 2


def test_executed_application_without_verified_receipt_writes_no_row(monkeypatch, tmp_path):
    monkeypatch.setattr(pl, "_DIR", tmp_path)
    lesson_id = _lesson_file(tmp_path, "autonomous")
    pl.prompt_block("autonomous", asof="2026-08-11")
    submission = _submission([lesson_id])
    pl.attach_lesson_trace("autonomous", "2026-08-11", submission)

    result = pl.record_application(
        "autonomous",
        "2026-08-11",
        submission,
        {"AAPL": 0.20},
        target_status="executed",
    )

    assert result == {
        "ok": False,
        "recorded": False,
        "error": "executed_application_requires_settlement_receipt",
    }
    assert not (tmp_path / "autonomous" / "applications.jsonl").exists()


def test_applications_ignore_malformed_hand_authored_execution_transitions(
    monkeypatch, tmp_path,
):
    monkeypatch.setattr(pl, "_DIR", tmp_path)
    lesson_id = _lesson_file(tmp_path, "autonomous")
    pl.prompt_block("autonomous", asof="2026-08-11")
    submission = _submission([lesson_id])
    pl.attach_lesson_trace("autonomous", "2026-08-11", submission)
    initial = pl.record_application(
        "autonomous",
        "2026-08-11",
        submission,
        {"AAPL": 0.20},
        target_status="queued",
    )["application"]
    transaction_id = "a" * 64
    fill_id = "b" * 64
    valid_shape = {
        "schema": "portfolio.lesson_application_transition.v1",
        "application_id": initial["application_id"],
        "decision_id": initial["decision_id"],
        "presentation_id": initial["presentation_id"],
        "book": "autonomous",
        "accepted_asof": initial["accepted_asof"],
        "target_sha256": initial["target_sha256"],
        "target_status": "executed",
        "executed": True,
        "executed_at": "2026-08-12",
        "settlement_verified": True,
        "settlement_transaction_id": transaction_id,
        "settlement_receipt_sha256": "c" * 64,
        "execution_evidence": "hash_bound_paper_settlement_receipt",
        "settled_fills": [{
            "fill_id": fill_id,
            "transaction_id": transaction_id,
            "date": "2026-08-12",
            "ticker": "AAPL",
            "side": "buy",
            "shares": 10,
            "price": 100.0,
            "value": 1_000.0,
        }],
        "authority": pl.APPLICATION_AUTHORITY,
        "evidence_cohort": pl.LESSON_TRACE_COHORT,
    }
    valid_shape["execution_proof_sha256"] = pl._execution_proof_sha256(valid_shape)
    malformed = []
    for key in ("execution_evidence", "executed_at", "settled_fills", "settlement_receipt_sha256"):
        row = json.loads(json.dumps(valid_shape))
        row.pop(key)
        row["execution_proof_sha256"] = pl._execution_proof_sha256(row)
        malformed.append((f"missing_{key}", row))
    missing_proof_digest = json.loads(json.dumps(valid_shape))
    missing_proof_digest.pop("execution_proof_sha256")
    malformed.append(("missing_execution_proof_sha256", missing_proof_digest))
    wrong_fill_transaction = json.loads(json.dumps(valid_shape))
    wrong_fill_transaction["settled_fills"][0]["transaction_id"] = "d" * 64
    wrong_fill_transaction["execution_proof_sha256"] = pl._execution_proof_sha256(
        wrong_fill_transaction
    )
    malformed.append(("wrong_fill_transaction", wrong_fill_transaction))
    wrong_target = json.loads(json.dumps(valid_shape))
    wrong_target["target_sha256"] = "e" * 64
    wrong_target["execution_proof_sha256"] = pl._execution_proof_sha256(wrong_target)
    malformed.append(("wrong_target", wrong_target))
    wrong_presentation = json.loads(json.dumps(valid_shape))
    wrong_presentation["presentation_id"] = f"presentation.v1.{'f' * 24}"
    wrong_presentation["execution_proof_sha256"] = pl._execution_proof_sha256(
        wrong_presentation
    )
    malformed.append(("wrong_presentation", wrong_presentation))

    path = tmp_path / "autonomous" / "applications.jsonl"
    for label, row in malformed:
        assert pl._append_jsonl(path, row), label
        observed = pl.applications("autonomous")
        assert len(observed) == 1, label
        assert observed[0]["executed"] is False, label
        assert "settlement_transaction_id" not in observed[0], label


def test_hash_mismatch_cannot_advance_queued_application(monkeypatch, tmp_path):
    monkeypatch.setattr(pl, "_DIR", tmp_path)
    lesson_id = _lesson_file(tmp_path, "autonomous")
    pl.prompt_block("autonomous", asof="2026-08-11")
    submission = _submission([lesson_id])
    pl.attach_lesson_trace("autonomous", "2026-08-11", submission)
    queued = pl.record_application(
        "autonomous",
        "2026-08-11",
        submission,
        {"AAPL": 0.20},
        target_status="queued",
    )["application"]
    wrong_hash = pl._target_sha256({"AAPL": 0.30})
    monkeypatch.setattr(pl, "_receipt_for_application", lambda *args: {
        "transaction_id": "a" * 64,
        "target": {"AAPL": 0.30},
        "target_sha256": wrong_hash,
        "decision_snapshot": {"target_sha256": wrong_hash},
        "fills": [],
    })

    result = pl.settle_application("autonomous", submission, "2026-08-12")

    assert result == {"ok": False, "error": "settlement_target_hash_mismatch"}
    assert pl.applications("autonomous")[0]["application_id"] == queued["application_id"]
    assert pl.applications("autonomous")[0]["executed"] is False
    assert len((tmp_path / "autonomous" / "applications.jsonl").read_text().splitlines()) == 1


def test_failed_application_transition_retains_receipt_and_republishes_on_retry(
    monkeypatch, tmp_path,
):
    """A crash at the observational append boundary cannot consume the numeric outbox."""
    import sys
    import types

    from bot import settle
    from bridge import build_portfolio
    from portfolio import paper_account, position_log, registry

    monkeypatch.setattr(pl, "_DIR", tmp_path / "learning")
    monkeypatch.setattr(registry, "_ROOT", tmp_path / "runtime")
    lesson_id = _lesson_file(tmp_path / "learning", "autonomous")
    pl.prompt_block("autonomous", asof="2026-08-11")
    submission = _submission([lesson_id])
    pl.attach_lesson_trace("autonomous", "2026-08-11", submission)
    target = {"AAPL": 0.20}
    paper_account._save_account({
        "inception_date": "2026-08-01",
        "starting_nav": 1_000_000.0,
        "cash": 1_000_000.0,
        "positions": {},
        "spy_shares": None,
        "spy_inception_price": None,
    }, "autonomous")
    paper_account.save_pending_target(
        target,
        "2026-08-11",
        portfolio_id="autonomous",
        decision_snapshot=submission,
    )
    pl.record_application(
        "autonomous", "2026-08-11", submission, target, target_status="queued"
    )

    monkeypatch.setattr(settle, "is_open", lambda pid: True)
    monkeypatch.setattr(
        settle,
        "_price_and_sources",
        lambda pid, symbols, _open_price_fn=None: (
            {symbol: 100.0 for symbol in symbols},
            {symbol: "test_open" for symbol in symbols},
        ),
    )
    monkeypatch.setattr(paper_account, "_current_price", lambda ticker: 100.0)
    monkeypatch.setattr(paper_account, "mark", lambda *args, **kwargs: None)
    monkeypatch.setattr(position_log, "update", lambda *args, **kwargs: None)
    monkeypatch.setattr(build_portfolio, "write", lambda *args, **kwargs: {})
    fake_mcp = types.ModuleType("brain.autonomous_mcp")
    fake_mcp.read_submission = lambda *args, **kwargs: submission
    monkeypatch.setitem(sys.modules, "brain.autonomous_mcp", fake_mcp)

    real_append = pl._append_jsonl
    failure = {"done": False}

    def fail_transition_once(path, row):
        if (
            row.get("schema") == "portfolio.lesson_application_transition.v1"
            and not failure["done"]
        ):
            failure["done"] = True
            return False
        return real_append(path, row)

    monkeypatch.setattr(pl, "_append_jsonl", fail_transition_once)
    first = settle.settle_open("autonomous", "2026-08-12")

    assert first["ok"] is False
    assert first["receipt_retained"] is True
    assert first["republish"]["error"] == "lesson_application_not_durable"
    receipts = paper_account.pending_settlement_receipts("autonomous")
    assert len(receipts) == 1
    transaction_id = receipts[0]["transaction_id"]
    assert pl.application_finalization_status(
        "autonomous", submission, settlement_receipt_id=transaction_id
    )["ok"] is False

    second = settle.settle_open("autonomous", "2026-08-12")

    assert second["ok"] is True
    assert second["receipt_acknowledged"] is True
    assert not paper_account.pending_settlement_receipts("autonomous")
    finalization = pl.application_finalization_status(
        "autonomous", submission, settlement_receipt_id=transaction_id
    )
    assert finalization["ok"] is True
    assert pl.applications("autonomous")[0]["settlement_transaction_id"] == transaction_id


def test_post_sell_outcome_uses_exact_fill_transaction_application_lineage(monkeypatch, tmp_path):
    from portfolio import registry, trade_history

    monkeypatch.setattr(pl, "_DIR", tmp_path / "learning")
    monkeypatch.setattr(registry, "data_dir", lambda book: tmp_path / "runtime" / book)
    presentation_id = f"presentation.v1.{'c' * 24}"
    accepted_asof = "2026-08-11"
    submission_hash = "1" * 64
    lesson_ids = ["lesson.v1.US_ONLY.churn_hysteresis"]
    decision_id = (
        f"decision.v1.{pl._sha256(['autonomous', accepted_asof, presentation_id, submission_hash])[:24]}"
    )
    application_id = (
        f"application.v1.{pl._sha256([decision_id, presentation_id, lesson_ids])[:24]}"
    )
    transaction_id = "d" * 64
    fill_id = "e" * 64
    target_hash = pl._target_sha256({"AAPL": 0.20})
    settled_fill = {
        "date": "2026-08-12",
        "ticker": "AAPL",
        "side": "sell",
        "shares": 2,
        "price": 110.0,
        "value": 220.0,
        "transaction_id": transaction_id,
        "fill_id": fill_id,
    }
    app_path = tmp_path / "learning" / "autonomous" / "applications.jsonl"
    app_path.parent.mkdir(parents=True)
    initial_row = {
        "schema": "portfolio.lesson_application.v1",
        "application_id": application_id,
        "decision_id": decision_id,
        "presentation_id": presentation_id,
        "book": "autonomous",
        "book_scope": "US_ONLY",
        "accepted_asof": accepted_asof,
        "submission_sha256": submission_hash,
        "target_sha256": target_hash,
        "target_status": "queued",
        "lesson_ids": lesson_ids,
        "lesson_basis": [{"id": lesson_ids[0]}],
        "material_difference": {"trims": ["AAPL"], "no_change": False},
        "executed": False,
        "executed_at": None,
        "authority": pl.APPLICATION_AUTHORITY,
        "evidence_cohort": pl.LESSON_TRACE_COHORT,
    }
    transition_row = {
        "schema": "portfolio.lesson_application_transition.v1",
        "application_id": application_id,
        "decision_id": decision_id,
        "presentation_id": presentation_id,
        "book": "autonomous",
        "accepted_asof": accepted_asof,
        "target_sha256": target_hash,
        "target_status": "executed",
        "executed": True,
        "executed_at": "2026-08-12",
        "settlement_verified": True,
        "settlement_transaction_id": transaction_id,
        "settlement_receipt_sha256": "2" * 64,
        "execution_evidence": "hash_bound_paper_settlement_receipt",
        "settled_fills": [settled_fill],
        "authority": pl.APPLICATION_AUTHORITY,
        "evidence_cohort": pl.LESSON_TRACE_COHORT,
    }
    transition_row["execution_proof_sha256"] = pl._execution_proof_sha256(transition_row)
    app_path.write_text(
        "\n".join(json.dumps(row) for row in [initial_row, transition_row]) + "\n",
        encoding="utf-8",
    )
    decision_dir = registry.data_dir("autonomous")
    decision_dir.mkdir(parents=True)
    decisions = [{
        "asof": accepted_asof,
        "decision_effective": True,
        "target_status": "queued",
        "holdings": [{
            "ticker": "AAPL",
            "action_effective": "trim",
            "rationale": "Exact transaction-bound rationale.",
        }],
        "decision_id": decision_id,
    }, {
        # This is closer by date but belongs to another target. It must never capture the fill.
        "asof": "2026-08-12",
        "decision_effective": True,
        "target_status": "queued",
        "holdings": [{
            "ticker": "AAPL",
            "action_effective": "trim",
            "rationale": "Wrong nearest-date rationale.",
        }],
        "decision_id": f"decision.v1.{'9' * 24}",
    }]
    decision_dir.joinpath("decisions.jsonl").write_text(
        "\n".join(json.dumps(row) for row in decisions) + "\n", encoding="utf-8"
    )
    monkeypatch.setattr(trade_history, "_load_fills", lambda book: [
        {"date": "2026-08-01", "ticker": "AAPL", "side": "buy", "shares": 10,
         "price": 100.0, "value": 1_000.0, "_seq": 0},
        {**settled_fill, "_seq": 1},
    ])
    monkeypatch.setattr(registry, "benchmark", lambda book: "SPY")
    monkeypatch.setattr(pl, "_series", lambda ticker: None)

    result = pl.refresh_post_sell("autonomous", asof="2026-08-12")

    outcome = result["exits"][0]
    assert outcome["sale_kind"] == "partial_trim"
    assert outcome["exit_id"] == f"autonomous:fill:{fill_id}"
    assert outcome["decision"]["rationale"] == "Exact transaction-bound rationale."
    assert outcome["decision_lineage"]["method"] == "settlement_transaction"
    assert outcome["lesson_trace"]["decision_id"] == decision_id
    assert outcome["lesson_trace"]["lesson_application_ids"] == [application_id]
    assert outcome["lesson_trace"]["settlement_transaction_id"] == transaction_id
    assert outcome["lesson_trace"]["fill_id"] == fill_id

    # A syntactically valid but wrong fill id under the same transaction is not receipt proof.
    (tmp_path / "learning" / "autonomous" / "post_sell.json").unlink()
    wrong_fill = {**settled_fill, "fill_id": "9" * 64, "_seq": 1}
    monkeypatch.setattr(trade_history, "_load_fills", lambda book: [
        {"date": "2026-08-01", "ticker": "AAPL", "side": "buy", "shares": 10,
         "price": 100.0, "value": 1_000.0, "_seq": 0},
        wrong_fill,
    ])

    corrupt = pl.refresh_post_sell("autonomous", asof="2026-08-12")["exits"][0]

    assert "decision" not in corrupt
    assert "lesson_trace" not in corrupt
    assert corrupt["decision_lineage"]["status"] == "unbound_fill_not_in_settlement_proof"
    corrupt_proof = pl._decision_exit(
        "autonomous",
        "AAPL",
        "2026-08-12",
        transaction_id=transaction_id,
        fill_id=fill_id,
        fill={**settled_fill, "price": 999.0},
    )
    assert corrupt_proof["_decision_lineage"]["status"] == "fill_proof_mismatch"


def test_modern_unbound_fill_does_not_fall_back_to_nearest_date(monkeypatch, tmp_path):
    from portfolio import registry, trade_history

    monkeypatch.setattr(pl, "_DIR", tmp_path / "learning")
    monkeypatch.setattr(registry, "data_dir", lambda book: tmp_path / "runtime" / book)
    decision_dir = registry.data_dir("autonomous")
    decision_dir.mkdir(parents=True)
    decision_dir.joinpath("decisions.jsonl").write_text(json.dumps({
        "asof": "2026-08-11",
        "decision_effective": True,
        "target_status": "queued",
        "holdings": [{"ticker": "AAPL", "rationale": "Must not be date matched."}],
        "decision_id": f"decision.v1.{'a' * 24}",
    }) + "\n", encoding="utf-8")
    monkeypatch.setattr(trade_history, "_load_fills", lambda book: [
        {"date": "2026-08-01", "ticker": "AAPL", "side": "buy", "shares": 10,
         "price": 100.0, "value": 1_000.0, "_seq": 0},
        {"date": "2026-08-12", "ticker": "AAPL", "side": "sell", "shares": 2,
         "price": 110.0, "value": 220.0, "_seq": 1,
         "transaction_id": "d" * 64, "fill_id": "e" * 64},
    ])
    monkeypatch.setattr(registry, "benchmark", lambda book: "SPY")
    monkeypatch.setattr(pl, "_series", lambda ticker: None)

    outcome = pl.refresh_post_sell("autonomous", asof="2026-08-12")["exits"][0]

    assert "decision" not in outcome
    assert "lesson_trace" not in outcome
    assert outcome["decision_lineage"]["status"] == "unbound_no_lesson_application"


def test_legacy_fill_keeps_explicitly_labelled_date_heuristic(monkeypatch, tmp_path):
    from portfolio import registry, trade_history

    monkeypatch.setattr(pl, "_DIR", tmp_path / "learning")
    monkeypatch.setattr(registry, "data_dir", lambda book: tmp_path / "runtime" / book)
    decision_dir = registry.data_dir("autonomous")
    decision_dir.mkdir(parents=True)
    decision_dir.joinpath("decisions.jsonl").write_text(json.dumps({
        "asof": "2026-08-11",
        "decision_effective": True,
        "target_status": "queued",
        "holdings": [{"ticker": "AAPL", "rationale": "Legacy rationale."}],
        "decision_id": f"decision.v1.{'a' * 24}",
        "lesson_application_ids": [f"application.v1.{'b' * 24}"],
        "lesson_ids_cited": ["lesson.v1.US_ONLY.churn_hysteresis"],
        "lesson_presentation_id": f"presentation.v1.{'c' * 24}",
        "lesson_trace_cohort": pl.LESSON_TRACE_COHORT,
    }) + "\n", encoding="utf-8")
    monkeypatch.setattr(trade_history, "_load_fills", lambda book: [
        {"date": "2026-08-01", "ticker": "AAPL", "side": "buy", "shares": 10,
         "price": 100.0, "value": 1_000.0, "_seq": 0},
        {"date": "2026-08-12", "ticker": "AAPL", "side": "sell", "shares": 2,
         "price": 110.0, "value": 220.0, "_seq": 1},
    ])
    monkeypatch.setattr(registry, "benchmark", lambda book: "SPY")
    monkeypatch.setattr(pl, "_series", lambda ticker: None)

    outcome = pl.refresh_post_sell("autonomous", asof="2026-08-12")["exits"][0]

    assert outcome["decision"]["rationale"] == "Legacy rationale."
    assert outcome["decision_lineage"]["method"] == "legacy_date_heuristic"
    assert outcome["lesson_trace"]["lesson_trace_status"] == "accepted_legacy_fill"


@pytest.mark.parametrize(
    ("book", "module_name", "foreign_id"),
    [
        ("autonomous", "bot.autonomous", "lesson.v1.CN_ONLY.churn_hysteresis"),
        ("china", "bot.china", "lesson.v1.US_ONLY.churn_hysteresis"),
        ("hk", "bot.hk", "lesson.v1.US_ONLY.churn_hysteresis"),
    ],
)
def test_regional_runs_fail_closed_before_execution_on_foreign_citation(
    monkeypatch, tmp_path, book, module_name, foreign_id,
):
    """The regional wiring cannot treat a model-authored foreign id as executable intent."""
    import sys
    import types

    import brain as brain_package
    from bot import settle
    from brain import cost_guard
    from bridge import build_portfolio
    from data_layer import feed_health
    from portfolio import paper_account, registry

    module = importlib.import_module(module_name)
    mcp_attr = {"autonomous": "autonomous_mcp", "china": "china_mcp", "hk": "hk_mcp"}[book]
    mcp_name = f"brain.{mcp_attr}"
    submission_path = tmp_path / "submissions" / f"{book}.json"
    fake_mcp = types.ModuleType(mcp_name)
    fake_mcp.submission_path = lambda *args, **kwargs: submission_path
    fake_mcp.clear_submission = lambda *args, **kwargs: submission_path.unlink(missing_ok=True)

    def read_submission(*args, **kwargs):
        return json.loads(submission_path.read_text()) if submission_path.exists() else None

    fake_mcp.read_submission = read_submission
    monkeypatch.setitem(sys.modules, mcp_name, fake_mcp)
    monkeypatch.setattr(brain_package, mcp_attr, fake_mcp, raising=False)
    monkeypatch.setattr(pl, "_DIR", tmp_path / "learning")
    monkeypatch.setattr(registry, "_ROOT", tmp_path / "runtime")
    _lesson_file(tmp_path / "learning", book)
    pl.prompt_block(book, asof="2026-08-11")
    monkeypatch.setattr(cost_guard, "over_budget", lambda *args, **kwargs: False)
    monkeypatch.setattr(cost_guard, "record", lambda *args, **kwargs: None)
    monkeypatch.setattr(feed_health, "status", lambda *args, **kwargs: {"status": "up"})
    monkeypatch.setattr(paper_account, "mark", lambda *args, **kwargs: None)
    monkeypatch.setattr(paper_account, "_current_price", lambda ticker: 100.0)
    monkeypatch.setattr(build_portfolio, "write", lambda *args, **kwargs: {})
    monkeypatch.setattr(
        settle,
        "execute_or_queue",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("foreign citation executed")),
    )
    monkeypatch.setattr(settle, "is_open", lambda *args, **kwargs: False)
    monkeypatch.setattr(pl, "refresh_post_sell", lambda *args, **kwargs: {"summary": {}})
    monkeypatch.setattr(pl, "derive_lessons", lambda *args, **kwargs: {"lessons": []})
    monkeypatch.setattr(module, "_translate_report", lambda *args, **kwargs: False, raising=False)

    ticker = {"autonomous": "AAPL", "china": "600519.SS", "hk": "0700.HK"}[book]

    def fake_brain(asof, inaugural):
        submission = _submission([foreign_id], ticker=ticker)
        if book == "autonomous":
            from brain import autonomous_mcp as mcp
            path = mcp.submission_path(book)
        elif book == "china":
            from brain import china_mcp as mcp
            path = mcp.submission_path()
        else:
            from brain import hk_mcp as mcp
            path = mcp.submission_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(submission), encoding="utf-8")
        return {"ok": True, "cost_usd": 0.0, "model": "test"}

    monkeypatch.setattr(module, "_run_brain", fake_brain)
    runner = getattr(module, f"run_{book}")
    out = runner(asof="2026-08-11", armed=True)

    assert out["target_status"] == "rejected_lesson_citations"
    assert out["decision_effective"] is False
    assert "application_id" not in out["lesson_citations"]
    assert "lesson_application_ids" not in out["lesson_citations"]
    assert not (tmp_path / "learning" / book / "applications.jsonl").exists()
