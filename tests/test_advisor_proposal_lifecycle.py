"""Focused contracts for the Portfolio Advisor -> active US PM proposal lifecycle."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

from brain import bot_mcp
from portfolio import advisor_trade


def _rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _propose(ticker: str, action: str, *, asof: str = "2026-08-08") -> dict:
    return advisor_trade.propose_action(
        ticker,
        action,
        thesis=f"Independent research case for {action.upper()} {ticker}.",
        evidence=[f"research:{asof}-{ticker}", "decision_matrix:confirmed"],
        urgency="next_cycle",
        asof=asof,
    )


def test_advisor_rejects_etf_add_but_keeps_etf_exit_researchable(tmp_path, monkeypatch):
    queue = tmp_path / "recommendations.jsonl"
    monkeypatch.setattr(advisor_trade, "_PROPOSALS", queue)

    rejected = _propose("USMV", "add")
    exit_proposal = _propose("USMV", "exit")

    assert rejected == {
        "ok": False,
        "executed": False,
        "ticker": "USMV",
        "action": "add",
        "error": "US portfolio proposals are verified-common-stock-only",
        "identity_status": "trusted_etf_metadata",
    }
    assert exit_proposal["ok"] is True
    assert exit_proposal["proposal"]["executed"] is False
    assert [row["action"] for row in advisor_trade.pending_proposals()] == ["exit"]


def test_advisor_book_reader_uses_active_us_product_default(tmp_path, monkeypatch):
    from portfolio import registry

    flagship = tmp_path / "flagship"
    autonomous = tmp_path / "autonomous"
    flagship.mkdir()
    autonomous.mkdir()
    (flagship / "latest.json").write_text(
        json.dumps({"positions": [{"ticker": "LEGACY"}]}), encoding="utf-8"
    )
    (autonomous / "latest.json").write_text(
        json.dumps({"positions": [{"ticker": "AAPL"}]}), encoding="utf-8"
    )
    monkeypatch.setattr(
        registry,
        "data_dir",
        lambda portfolio_id=None: autonomous
        if portfolio_id == registry.DASHBOARD_DEFAULT_ID
        else flagship,
    )

    result = asyncio.run(bot_mcp.get_portfolio.handler({}))
    payload = json.loads(result["content"][0]["text"])

    assert payload["portfolio_id"] == "autonomous"
    assert payload["positions"] == [{"ticker": "AAPL"}]
    assert payload["active"] is True


def test_validated_queue_prompt_review_and_idempotency_have_no_fill_path(tmp_path, monkeypatch):
    queue = tmp_path / "recommendations.jsonl"
    monkeypatch.setattr(advisor_trade, "_PROPOSALS", queue)
    queue.write_text(
        json.dumps({
            "source": "claude_cli", "status": "paper", "ticker": "OLD",
            "action": "buy", "rationale": "legacy bypass", "weight": 0.25,
        })
        + "\n{malformed-json\n",
        encoding="utf-8",
    )

    # A proposal review must remain unable to reach either historical mutation seam.
    from portfolio import paper_account, position_log
    monkeypatch.setattr(
        paper_account,
        "execute_fill",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("unexpected fill")),
    )
    monkeypatch.setattr(
        position_log,
        "record_manual",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("unexpected ledger write")),
        raising=False,
    )

    aapl = _propose("AAPL", "add")
    duplicate = _propose("AAPL", "add")
    tsla = _propose("TSLA", "exit")
    assert aapl["ok"] and tsla["ok"]
    assert duplicate["deduplicated"] is True
    assert duplicate["proposal"]["id"] == aapl["proposal"]["id"]

    pending = advisor_trade.pending_proposals()
    assert {row["id"] for row in pending} == {
        aapl["proposal"]["id"],
        tsla["proposal"]["id"],
    }
    context = advisor_trade.prompt_context()
    assert "Pending Portfolio Advisor proposals" in context
    assert "ADD AAPL" in context and "EXIT TSLA" in context
    assert "Selection never fills a trade" in context

    # The exact compact context is consumed by the active US nightly PM prompt.
    from bot import autonomous
    from brain import portfolio_learning, risk_lens
    monkeypatch.setattr(paper_account, "_load_account", lambda portfolio_id: {
        "cash": 1_000_000.0, "positions": {},
    })
    monkeypatch.setattr(autonomous, "_regime_brief", lambda: "")
    monkeypatch.setattr(autonomous, "_regime_dict", dict)
    monkeypatch.setattr(risk_lens, "briefing", lambda *args, **kwargs: "")
    monkeypatch.setattr(portfolio_learning, "prompt_block", lambda portfolio_id: "")
    prompt = autonomous._build_prompt("2026-08-08", inaugural=True)
    assert "ADD AAPL" in prompt and "EXIT TSLA" in prompt

    invalid = advisor_trade.review_submitted_book(
        {"holdings": [{"ticker": "AAPL"}], "exit_decisions": []},
        asof="2026-08-08",
        portfolio_id="autonomous",
        proposal_ids=[row["id"] for row in pending],
    )
    assert invalid["ok"] is False and invalid["reviewed"] == 0
    assert {row["status"] for row in advisor_trade.pending_proposals()} == {"proposed"}

    reviewed = advisor_trade.review_submitted_book(
        {
            "schema": "mastermind.target_book.v2",
            # Real normalized submissions preserve requested/effective actions, not the raw
            # schema's ``action`` key. The review must credit only the effective action.
            "holdings": [{"ticker": "AAPL", "action_requested": "add",
                          "action_effective": "add"}],
            "exit_decisions": [],
        },
        asof="2026-08-08",
        portfolio_id="autonomous",
        proposal_ids=[row["id"] for row in pending],
    )
    assert reviewed == {
        "ok": True,
        "reviewed": 2,
        "selected": 1,
        "not_selected": 1,
        "selected_ids": [aapl["proposal"]["id"]],
        "not_selected_ids": [tsla["proposal"]["id"]],
        "executed": False,
    }

    rows = _rows(queue)
    assert len(rows) == 2
    assert {row["schema"] for row in rows} == {advisor_trade.SCHEMA}
    assert {row["ticker"]: row["status"] for row in rows} == {
        "AAPL": "selected",
        "TSLA": "not_selected",
    }
    assert all(row["executed"] is False for row in rows)
    assert not any(advisor_trade._FORBIDDEN_FIELDS & set(row) for row in rows)

    # A replay cannot create a second transition or mutate review timestamps.
    before = queue.read_bytes()
    replay = advisor_trade.review_submitted_book(
        {
            "holdings": [{"ticker": "AAPL", "action_requested": "add",
                          "action_effective": "add"}],
            "exit_decisions": [],
        },
        asof="2026-08-08",
        portfolio_id="autonomous",
        proposal_ids=[row["id"] for row in pending],
    )
    assert replay["reviewed"] == 0
    assert queue.read_bytes() == before

    quarantine = _rows(tmp_path / "recommendations.quarantine.jsonl")
    assert len(quarantine) == 2
    assert {row["schema"] for row in quarantine} == {advisor_trade.QUARANTINE_SCHEMA}
    assert {row["reason"] for row in quarantine} == {"foreign_schema", "invalid_json"}
    assert any("legacy bypass" in row["raw"] for row in quarantine)
    assert any("malformed-json" in row["raw"] for row in quarantine)

    source = Path(advisor_trade.__file__).read_text(encoding="utf-8")
    assert "paper_account" not in source and "position_log" not in source
    assert not hasattr(advisor_trade, "execute")


def test_active_us_run_reviews_only_snapshotted_proposals_after_final_submission(
    tmp_path, monkeypatch,
):
    from bot import autonomous, settle
    from brain import autonomous_mcp, cost_guard
    from portfolio import firm_exposure, paper_account, registry

    monkeypatch.setattr(registry, "_ROOT", tmp_path, raising=False)
    monkeypatch.setattr(advisor_trade, "_PROPOSALS", tmp_path / "recommendations.jsonl")
    monkeypatch.setenv("MASTERMIND_PACKET_GATE", "off")
    monkeypatch.setattr(cost_guard, "over_budget", lambda portfolio_id, asof: False)
    monkeypatch.setattr(cost_guard, "record", lambda *args, **kwargs: None)
    monkeypatch.setattr(firm_exposure, "caps_enabled", lambda: False)
    monkeypatch.setattr(paper_account, "_current_price", lambda ticker: {"SPY": 740.0}.get(ticker))

    proposal = _propose("AAPL", "exit")
    settle_calls: list[dict] = []

    def fake_brain(asof, inaugural):
        path = autonomous_mcp.submission_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({
            "schema": "mastermind.target_book.v2",
            "holdings": [],
            "exit_decisions": [{"ticker": "AAPL", "action": "exit"}],
            "summary": "Reviewed the advisor proposal without opening or filling a line.",
            "gross": 0.0,
        }), encoding="utf-8")
        return {"ok": True, "text": "submitted", "cost_usd": 0.0, "model": "test"}

    def fake_settle(portfolio_id, target, prices, asof, *, decision_snapshot=None):
        assert decision_snapshot and decision_snapshot.get("schema") == "mastermind.target_book.v2"
        settle_calls.append(dict(target))
        return {"executed": [], "queued": False}

    monkeypatch.setattr(autonomous, "_run_brain", fake_brain)
    monkeypatch.setattr(settle, "execute_or_queue", fake_settle)
    monkeypatch.setattr(settle, "is_open", lambda portfolio_id: False)

    out = autonomous.run_autonomous(asof="2026-08-08", armed=True)
    assert out["advisor_proposals_presented"] == 1
    assert out["advisor_proposal_review"]["selected_ids"] == [proposal["proposal"]["id"]]
    assert out["advisor_proposal_review"]["executed"] is False
    assert out["executed"] == [] and settle_calls == [{}]
    assert _rows(advisor_trade._PROPOSALS)[0]["status"] == "selected"


def test_rejected_us_target_leaves_presented_advisor_proposal_pending(
    tmp_path, monkeypatch,
):
    from bot import autonomous, settle
    from brain import autonomous_mcp, cost_guard
    from control_plane import packet_gate
    from portfolio import firm_exposure, paper_account, registry

    monkeypatch.setattr(registry, "_ROOT", tmp_path, raising=False)
    monkeypatch.setattr(advisor_trade, "_PROPOSALS", tmp_path / "recommendations.jsonl")
    monkeypatch.setattr(cost_guard, "over_budget", lambda portfolio_id, asof: False)
    monkeypatch.setattr(cost_guard, "record", lambda *args, **kwargs: None)
    monkeypatch.setattr(firm_exposure, "caps_enabled", lambda: False)
    monkeypatch.setattr(
        paper_account,
        "_current_price",
        lambda ticker: {"AAPL": 100.0, "SPY": 740.0}.get(ticker),
    )

    proposal = _propose("AAPL", "add")

    def fake_brain(asof, inaugural):
        path = autonomous_mcp.submission_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "schema": "mastermind.target_book.v2",
                    "holdings": [
                        {
                            "ticker": "AAPL",
                            "weight": 0.10,
                            "action_requested": "add",
                            "action_effective": "add",
                        }
                    ],
                    "exit_decisions": [],
                    "summary": "Reviewed but rejected at the trusted packet boundary.",
                    "gross": 0.10,
                }
            ),
            encoding="utf-8",
        )
        return {"ok": True, "text": "submitted", "cost_usd": 0.0, "model": "test"}

    class RejectedPacket:
        ok = False
        packet_id = "packet-rejected"

        @staticmethod
        def to_meta():
            return {"ok": False, "reason": "test_rejection"}

    monkeypatch.setattr(autonomous, "_run_brain", fake_brain)
    monkeypatch.setattr(packet_gate, "process", lambda *args, **kwargs: RejectedPacket())
    monkeypatch.setattr(
        settle,
        "execute_or_queue",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("rejected target reached execution")
        ),
    )
    monkeypatch.setattr(settle, "is_open", lambda portfolio_id: False)

    out = autonomous.run_autonomous(asof="2026-08-08", armed=True)
    row = _rows(advisor_trade._PROPOSALS)[0]
    assert row["id"] == proposal["proposal"]["id"]
    assert row["status"] == "proposed" and row["executed"] is False
    assert out["target_status"] == "rejected_packet_gate"
    assert out["advisor_proposal_review"]["deferred"] is True
    assert out["advisor_proposal_review"]["reviewed"] == 0


def test_legacy_recommend_action_is_not_on_advisor_mcp_surface(tmp_path, monkeypatch):
    assert "mcp__bot__recommend_action" not in bot_mcp.TOOL_NAMES
    assert "mcp__bot__recommend_action" not in bot_mcp.armed_allowed_tools()
    assert "mcp__bot__propose_portfolio_action" in bot_mcp.TOOL_NAMES

    # Keep the old direct handler available to unrelated internal callers, but isolate its
    # incompatible status=paper contract from the validated Portfolio Advisor queue.
    monkeypatch.setattr(bot_mcp, "_RESEARCH", tmp_path)
    result = asyncio.run(bot_mcp.recommend_action.handler({
        "ticker": "AAPL", "action": "watch", "rationale": "legacy research consumer",
    }))
    assert "legacy recommendation logged" in result["content"][0]["text"]
    assert (tmp_path / "legacy_recommendations.jsonl").exists()
    assert not (tmp_path / "recommendations.jsonl").exists()
