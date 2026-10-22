"""Current bridge output reaches the mounted reader through its actual book owner.

SDK transport, market inputs and ancillary policy/learning seams are synthetic,
as in the existing real-book fixture. The collector, seeded run log, accepted
submission, queued decision and API projections are real.
"""
from __future__ import annotations

import copy
import importlib
import importlib.metadata
import json
import sys
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient

from test_provider_diagnostic_read import snapshot
from test_sdk_diagnostic_bridge import Harness
from test_sdk_diagnostic_terminal_composition import waterfall_call


def test_fresh_sdk_terminal_diagnostics_reach_mounted_accepted_decision(
    monkeypatch, tmp_path,
):
    from app import auth, response_cache, web
    from bot import autonomous, decision_rows, settle
    from brain import (
        autonomous_mcp, cost_guard, decision_submission, portfolio_learning,
        provider_waterfall, runlog,
    )
    from claude_agent_sdk import ResultMessage
    from control_plane import packet_gate
    from portfolio import advisor_trade, firm_exposure, paper_account, registry, safety

    # Harness owns the fake transport and routing probes. Restore the actual
    # logger, including its required _meta seed and final index publication.
    real_logging = {name: getattr(runlog, name) for name in (
        "start_run", "log_step", "end_run",
    )}
    real_version = importlib.metadata.version
    real_cli_version = importlib.import_module("claude_agent_sdk._cli_version")
    h = Harness(monkeypatch)
    for name, function in real_logging.items():
        monkeypatch.setattr(runlog, name, function)
    monkeypatch.setattr(importlib.metadata, "version", real_version)
    monkeypatch.setitem(sys.modules, "claude_agent_sdk._cli_version", real_cli_version)
    logs = tmp_path / "runs"
    monkeypatch.setattr(runlog, "_RUNS_DIR", logs)
    monkeypatch.setattr(runlog, "_INDEX", logs / "index.jsonl")

    # Reuse the existing real-book fixture's synthetic market and ancillary
    # seams; submission allocation, queue persistence and decision identity stay real.
    monkeypatch.setattr(registry, "_ROOT", tmp_path / "books")
    monkeypatch.setattr(cost_guard, "over_budget", lambda *a, **kw: False)
    monkeypatch.setattr(cost_guard, "record", lambda *a, **kw: None)
    monkeypatch.setattr(advisor_trade, "pending_proposals", lambda **kw: [])
    monkeypatch.setattr(paper_account, "_current_price", lambda ticker: {
        "AAPL": 200.0, "SPY": 500.0,
    }.get(ticker))
    monkeypatch.setattr(decision_submission, "_instrument_identity", lambda ticker: {
        "kind": "common_stock", "status": "fixture_common_stock", "verified": True,
    })
    monkeypatch.setattr(settle, "is_open", lambda portfolio_id: False)
    monkeypatch.setattr(packet_gate, "process", lambda *a, **kw: None)
    monkeypatch.setattr(portfolio_learning, "attach_lesson_trace", lambda *a, **kw: {
        "ok": True, "cited_ids": [],
    })
    monkeypatch.setattr(portfolio_learning, "record_application", lambda *a, **kw: {
        "ok": True, "recorded": False,
    })
    monkeypatch.setattr(firm_exposure, "caps_enabled", lambda: False)
    monkeypatch.setattr(safety, "compute_safety", lambda *a, **kw: {})
    monkeypatch.setattr(safety, "gross_overlay", lambda *a, **kw: {"gross_mult": 1.0})
    monkeypatch.setattr(safety, "persist", lambda *a, **kw: None)

    submitted = []

    async def accept_submission():
        reply = await autonomous_mcp.submit_book.handler({
            "holdings": [{
                "ticker": "AAPL", "action": "add", "conviction": "high",
                "rationale": "Synthetic accepted thesis",
                "evidence": ["Synthetic research"], "why_now": "Synthetic catalyst",
            }],
            "summary": "Synthetic accepted thesis", "exit_decisions": [],
        })
        accepted = autonomous_mcp.read_submission("autonomous")
        assert accepted and len(accepted["holdings"]) == 1
        assert "SUBMISSION REJECTED" not in json.dumps(reply)
        submitted.append(copy.deepcopy(accepted))

    private = "synthetic private diagnostic prose"
    h.plans = [[
        accept_submission,
        ResultMessage(
            subtype="success", duration_ms=1, duration_api_ms=1, is_error=True,
            num_turns=1, session_id="synthetic-sdk-session",
            result="401 429 usage limit reached " + private,
            api_error_status=503, terminal_reason="api_error", stop_reason="error",
        ),
        ResultMessage(
            subtype="success", duration_ms=2, duration_api_ms=2, is_error=False,
            num_turns=2, session_id="synthetic-sdk-session",
            result=private + " later success terminal",
        ),
    ]]
    invoke, entries, classifications = waterfall_call(h, monkeypatch)
    monkeypatch.setattr(autonomous, "_run_brain", lambda *a, **kw: invoke())
    asof = datetime.now(timezone.utc).date().isoformat()
    outcome = autonomous.run_autonomous(asof=asof, armed=True)

    assert outcome["brain"]["ok"] is False
    assert outcome["brain"]["error"] == "sdk_terminal_error"
    assert outcome["decided"] is True and outcome["target_status"] == "queued"
    assert outcome["decision_effective"] is True and outcome["executed"] == []
    assert not outcome.get("decision_log_error")
    assert len(submitted) == len(h.providers) == len(entries) == 1
    assert classifications == ["sdk_terminal_error"]
    assert h.classifications == h.cooling == h.sessions == []

    run_id = outcome["brain"]["run_id"]
    decisions = autonomous.load_decisions()
    assert len(decisions) == 1
    decision = decisions[0]
    assert decision["run_id"] == run_id
    assert decision["error"] == "sdk_terminal_error"
    assert decision["decision_effective"] is True and decision["target_status"] == "queued"
    pending = json.loads(paper_account._pending_target_path("autonomous").read_text())
    expected_target = {row["ticker"]: row["weight"] for row in submitted[0]["holdings"]}
    assert pending["target"] == expected_target and expected_target
    assert paper_account.pending_target_contract_error(pending, "autonomous") is None
    pending_decision = pending["decision_snapshot"]
    assert pending_decision["submission"] == submitted[0]
    assert pending_decision["portfolio_id"] == "autonomous"
    assert pending_decision["accepted_asof"] == decision["accepted_asof"] == asof
    assert pending_decision["decision_log_required"] is True
    assert pending_decision["target_sha256"] == decision["target_sha256"]
    assert pending_decision["accepted_target_sha256"] == decision["target_sha256"]
    # The queue retains the submission and target hash, rather than duplicating
    # the ledger's decision ID. Its owner derives that identity and proves that
    # exactly one durable queued decision row matches this accepted instruction.
    assert decision_rows.validate_queued_decision_snapshot(
        "autonomous", pending_decision,
    ) == {
        "ok": True, "required": True,
        "decision_id": decision["decision_id"],
        "target_sha256": decision["target_sha256"],
    }
    base = registry.data_dir("autonomous")
    account = json.loads((base / "account.json").read_text())
    assert not account["positions"]

    rows = [json.loads(line) for line in (logs / (run_id + ".jsonl")).read_text().splitlines()]
    seeds = [row["_meta"] for row in rows if "_meta" in row]
    assert len(seeds) == 1 and seeds[0]["run_id"] == run_id
    assert seeds[0]["kind"] == "research"
    assert [row["run_id"] for row in runlog.list_runs()] == [run_id]
    events = [row for row in rows if row.get("type") == "provider_diagnostic"]
    assert len(events) == 1
    emitted = events[0]["provider_diagnostic"]
    assert events[0]["provider_diagnostic_capture"]["status"] == "available"
    assert emitted["exit"]["end_state"] == "exhausted"
    assert emitted["exception"]["observed"] is False
    assert emitted["terminals"]["count"] == 2
    assert private in emitted["terminals"]["first"]["retained_failure_text"]

    observed = datetime.now(timezone.utc) + timedelta(seconds=1)

    class InspectionClock(datetime):
        @classmethod
        def now(cls, tz=None):
            return observed if tz is None else observed.astimezone(tz)

    monkeypatch.setattr(web, "datetime", InspectionClock)

    forbidden_calls = []

    def forbidden(*args, **kwargs):
        forbidden_calls.append(True)
        raise AssertionError("diagnostic read attempted an effect or replacement read")

    # The read must use the exact persisted run directly. It may not invoke a
    # provider, search the run index, reconstruct an account, obtain a quote or write.
    for name in ("start_run", "log_step", "end_run", "list_runs", "read_run"):
        monkeypatch.setattr(runlog, name, forbidden)
    monkeypatch.setattr(h.cb, "_sdk_query", forbidden)
    monkeypatch.setattr(h.cb, "_via_subprocess", forbidden)
    monkeypatch.setattr(provider_waterfall, "reason", forbidden)
    for name in (
        "_current_price", "_load_account", "_load_account_file", "_fresh_account",
        "mark", "nav", "settle_target", "rebalance", "preflight_pending_target",
        "quarantine_pending_target", "accrue_cash_yield",
        "_recover_paper_transaction_unlocked",
    ):
        monkeypatch.setattr(paper_account, name, forbidden)

    app = FastAPI()
    app.include_router(web.router)
    response_cache.install(app)
    auth.install(app)
    response_cache.clear()
    before = snapshot(tmp_path)
    documents = []
    with TestClient(app) as client:
        for _ in range(2):
            response = client.get("/api/portfolio?portfolio=autonomous&view=decision_availability")
            assert response.status_code == 200
            assert response.headers["cache-control"] == "no-store"
            assert "x-mm-cache" not in response.headers
            assert private not in response.text
            data = response.json()
            documents.append(data)
            assert data["latest_attempt_kind"] == "accepted_with_error"
            assert data["latest_attempt"]["run_id"] == run_id
            assert data["last_valid_decision"]["run_id"] == run_id
            assert data["accepted_target"]["decision_id"] == decision["decision_id"]
            assert data["accepted_target"]["target_status"] == "queued"
            assert data["accepted_target"]["weights"] == expected_target
            # This read-only projection compares stored fields; it does not
            # derive the queue's decision ID as the settlement owner does above.
            projected_pending = data["accepted_target"]["pending"]
            assert projected_pending["status"] == "queued"
            assert projected_pending["target"] == expected_target
            assert projected_pending["asof"] == asof
            assert projected_pending["queued_at"] == pending["queued_at"]
            assert projected_pending["clock_status"] == "available"
            assert projected_pending["decision_id"] is None
            assert projected_pending["lineage_status"] == "partial"
            assert data["account"]["cash"] == account["cash"]
            diagnostic = data["provider_diagnostic_inspection"]
            assert diagnostic["status"] == diagnostic["source"]["status"] == "available"
            assert diagnostic["run_binding"] == "matched_recorded_run_id"
            assert diagnostic["decision_binding_consistency"] == "observed_stable"
            assert diagnostic["decision_history_status"] == "available"
            assert diagnostic["run_id"] == run_id and diagnostic["portfolio_id"] == "autonomous"
            assert diagnostic["diagnostic_events_observed"] == diagnostic["candidates_observed"] == 1
            candidate, = diagnostic["candidates"]
            assert candidate["identity"] == {
                "run_id": run_id, "book": "autonomous", "role": "deep", "candidate_ordinal": 0,
            }
            assert candidate["status"] == "available"
            assert candidate["exit"]["end_state"] == "exhausted"
            assert candidate["exception"]["observed"] is False
            assert candidate["completeness"] == "complete_limited_to_observed_sdk_messages"
            assert candidate["observation"]["sdk_messages_observed"] == 2
            assert candidate["observation"]["contradictory_terminals_observed"] == 1
            assert candidate["terminals"]["count"] == 2
            first, last = candidate["terminals"]["first"], candidate["terminals"]["last"]
            assert first["subtype"] == last["subtype"] == "success"
            assert first["is_error"] is True and last["is_error"] is False
            assert first["reported_contradiction"] is True
            assert last["reported_contradiction"] is False
            assert first["api_error_status"] == 503
            assert diagnostic["provider_start"] == "not_proven"
            assert diagnostic["effect_reconciliation"] == "not_performed"
            assert diagnostic["attempt_coverage"] == "partial"
    assert documents[0] == documents[1]
    assert snapshot(tmp_path) == before
    assert len(h.providers) == len(entries) == 1
    assert forbidden_calls == []
    assert not response_cache._CACHE
