from __future__ import annotations

import json
import math
from datetime import date

import pytest

from brain import decision_submission as ds


def _args(holdings=None, exits=None, posture="normal"):
    return {
        "holdings": holdings or [],
        "summary": "reviewed book",
        "exit_decisions": exits or [],
        "falsifiers": ["market frame breaks"],
        "evidence_planes": ["prophet", "sector_central"],
        "source_provenance": ["prophet:index:test"],
        "expected_failure_mode": "rotation reverses",
        "risk_posture": posture,
        "cash_rationale": "candidate quality determines residual cash",
        "decision_memo": {"candidate_funnel": {"reviewed": 8}, "rejected": ["XYZ"]},
    }


def _holding(ticker, *, action="add", conviction="high", weight=0.01, evidence=None):
    return {
        "ticker": ticker,
        "weight": weight,
        "rationale": f"reviewed thesis for {ticker}",
        "conviction": conviction,
        "action": action,
        "why_now": "confirmation is present now",
        "falsifier": "trend and catalyst both break",
        "evidence": evidence if evidence is not None else ["trusted:test"],
        "source_provenance": ["prophet:index:test"],
        "expected_horizon": "21 sessions",
        "exit_plan": "trail while thesis confirms",
    }


def _common_identity(ticker):
    return {"kind": "common_stock", "status": "test_common_stock", "verified": True}


def test_omission_is_carried_at_exact_prior_weight(monkeypatch):
    monkeypatch.setattr(
        ds,
        "_latest_holdings",
        lambda book: {
            "AAPL": {
                "ticker": "AAPL",
                "weight": 0.82,
                "rationale": "prior",
                "conviction": "high",
            },
        },
    )
    payload, audit = ds.normalize(
        "autonomous",
        _args([_holding("MSFT", weight=0.40)]),
        deterministic_sizing=False,
    )
    by_ticker = {row["ticker"]: row for row in payload["holdings"]}
    assert by_ticker["AAPL"]["weight"] == pytest.approx(0.82)
    assert by_ticker["MSFT"]["weight"] == pytest.approx(0.18)
    assert payload["scaled_to_no_leverage"] is True
    assert audit["carried"] == [
        {"ticker": "AAPL", "reason": "missing_explicit_exit_decision"}
    ]


def test_trim_is_explicit_evidenced_and_deterministic(monkeypatch):
    monkeypatch.setattr(
        ds,
        "_latest_holdings",
        lambda book: {
            "AAPL": {
                "ticker": "AAPL",
                "weight": 0.10,
                "rationale": "prior",
                "conviction": "high",
            },
        },
    )
    row = _holding("AAPL", action="trim", weight=0.99)
    row["trim_intensity"] = "standard"
    payload, _ = ds.normalize("autonomous", _args([row]), deterministic_sizing=True)
    result = payload["holdings"][0]
    assert result["proposed_weight"] == pytest.approx(0.99)
    assert result["weight"] == pytest.approx(0.06)
    assert result["action_requested"] == result["action_effective"] == "trim"
    assert result["weight_source"] == "deterministic_trim.v1"


def test_trim_anchors_to_prior_target_and_can_never_increase_actual(monkeypatch):
    monkeypatch.setattr(
        ds,
        "_latest_holdings",
        lambda book: {
            "AAPL": {
                "ticker": "AAPL",
                "weight": 0.10,
                "prior_target_weight": 0.08,
                "rationale": "prior",
                "conviction": "high",
            }
        },
    )
    row = _holding("AAPL", action="trim", weight=0.90)
    row["trim_intensity"] = "standard"
    payload, _ = ds.normalize("autonomous", _args([row]), deterministic_sizing=True)
    result = payload["holdings"][0]
    assert result["trim_anchor_weight"] == pytest.approx(0.08)
    assert result["weight"] == pytest.approx(0.048)


def test_rejected_target_never_becomes_next_trim_anchor(tmp_path, monkeypatch):
    from portfolio import paper_account, registry

    (tmp_path / "latest.json").write_text(
        json.dumps({"positions": [{"ticker": "AAPL", "rationale": "live holding"}]}),
        encoding="utf-8",
    )
    accepted = {
        "asof": "2026-08-07",
        "target_status": "executed",
        "decision_effective": True,
        "effective_holdings": [{"ticker": "AAPL", "weight": 0.10}],
        "holdings": [{"ticker": "AAPL", "weight": 0.10}],
    }
    rejected = {
        "asof": "2026-08-08",
        "target_status": "frozen_held_quote_fallback",
        "decision_effective": False,
        "effective_holdings": [],
        "holdings": [{"ticker": "AAPL", "weight": 0.06}],
    }
    (tmp_path / "decisions.jsonl").write_text(
        "\n".join(json.dumps(row) for row in (accepted, rejected)) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(registry, "data_dir", lambda book: tmp_path)
    monkeypatch.setattr(registry, "currency", lambda book: "USD")
    monkeypatch.setattr(
        paper_account,
        "_load_account",
        lambda book: {
            "cash": 900.0,
            "positions": {"AAPL": {"shares": 1.0, "avg_cost": 100.0}},
        },
    )
    monkeypatch.setattr(paper_account, "_current_price", lambda ticker: 100.0)

    latest = ds._latest_holdings("autonomous")
    assert latest["AAPL"]["prior_target_weight"] == pytest.approx(0.10)

    trim = _holding("AAPL", action="trim", weight=0.99)
    trim["trim_intensity"] = "standard"
    payload, _ = ds.normalize(
        "autonomous", _args([trim]), deterministic_sizing=True
    )
    assert payload["holdings"][0]["weight"] == pytest.approx(0.06)


def test_trim_without_evidence_fails_closed_to_hold(monkeypatch):
    monkeypatch.setattr(
        ds,
        "_latest_holdings",
        lambda book: {
            "AAPL": {
                "ticker": "AAPL",
                "weight": 0.10,
                "rationale": "prior",
                "conviction": "high",
            },
        },
    )
    row = _holding("AAPL", action="trim", evidence=[])
    payload, audit = ds.normalize("autonomous", _args([row]), deterministic_sizing=True)
    result = payload["holdings"][0]
    assert result["weight"] == pytest.approx(0.10)
    assert result["action_requested"] == "trim"
    assert result["action_effective"] == "hold"
    assert audit["blocked_actions"][0]["reason"] == "trim_requires_why_now_and_evidence"


def test_actual_account_recovers_quote_outage_with_avg_cost(tmp_path, monkeypatch):
    from portfolio import paper_account, registry

    (tmp_path / "latest.json").write_text(
        json.dumps(
            {
                "positions": [
                    {
                        "ticker": "BIIB",
                        "rationale": "published thesis",
                        "conviction": "high",
                    }
                ],
            }
        )
    )
    monkeypatch.setattr(registry, "data_dir", lambda book: tmp_path)
    monkeypatch.setattr(
        paper_account,
        "_load_account",
        lambda book: {
            "cash": 500.0,
            "positions": {"BIIB": {"shares": 5.0, "avg_cost": 100.0}},
        },
    )
    monkeypatch.setattr(paper_account, "_current_price", lambda ticker: None)
    rows = ds._latest_holdings("autonomous")
    assert rows["BIIB"]["weight"] == pytest.approx(0.5)
    assert rows["BIIB"]["holding_mark_source"] == "account_avg_cost_fallback"
    assert rows["BIIB"]["rationale"] == "published thesis"


def test_actual_account_missing_quote_and_cost_freezes(monkeypatch):
    from portfolio import paper_account

    monkeypatch.setattr(
        paper_account,
        "_load_account",
        lambda book: {
            "cash": 500.0,
            "positions": {"BIIB": {"shares": 5.0, "avg_cost": None}},
        },
    )
    monkeypatch.setattr(paper_account, "_current_price", lambda ticker: None)
    with pytest.raises(
        ds.DecisionBoundaryFreeze, match="unpriceable_held_position:BIIB"
    ):
        ds._latest_holdings("autonomous")


def test_actual_account_converts_live_mark_to_regional_book_currency(
    tmp_path, monkeypatch
):
    from portfolio import fx, paper_account, registry

    monkeypatch.setattr(registry, "data_dir", lambda book: tmp_path)
    monkeypatch.setattr(registry, "currency", lambda book: "CNY")
    monkeypatch.setattr(
        paper_account,
        "_load_account",
        lambda book: {
            "cash": 700.0,
            "positions": {"600519.SS": {"shares": 1.0, "avg_cost": 600.0}},
        },
    )
    monkeypatch.setattr(paper_account, "_current_price", lambda ticker: 100.0)
    monkeypatch.setattr(fx, "usd_to", lambda price, currency: price * 7.0)
    rows = ds._latest_holdings("china")
    assert rows["600519.SS"]["weight"] == pytest.approx(0.5)
    assert rows["600519.SS"]["holding_mark_source"] == "live_quote"


def test_hysteresis_counts_exchange_sessions_not_calendar_days(monkeypatch):
    from portfolio import trade_history

    monkeypatch.setattr(
        trade_history,
        "_load_fills",
        lambda book: [
            {"ticker": "BIIB", "side": "buy", "shares": 10, "date": "2026-07-02"},
        ],
    )
    # 2026-07-03 is the observed Independence Day closure, followed by a weekend.
    assert ds._held_sessions("autonomous", "BIIB", date(2026, 7, 7)) == 3
    assert ds._held_sessions("autonomous", "BIIB", date(2026, 7, 8)) == 4


def test_blocked_exit_is_requested_but_never_effective(monkeypatch):
    monkeypatch.setattr(
        ds,
        "_latest_holdings",
        lambda book: {
            "BIIB": {
                "ticker": "BIIB",
                "weight": 0.10,
                "rationale": "prior",
                "conviction": "medium",
            },
        },
    )
    monkeypatch.setattr(ds, "_held_sessions", lambda *args: None)
    soft = [
        {
            "ticker": "BIIB",
            "action": "exit",
            "reason": "changed my mind",
            "reason_code": "thesis_change",
            "evidence": ["fresh review"],
            "why_now": "today",
        }
    ]
    payload, audit = ds.normalize(
        "autonomous",
        _args(exits=soft),
        early_exit_hysteresis=True,
        deterministic_sizing=True,
    )
    assert [row["ticker"] for row in payload["requested_exit_decisions"]] == ["BIIB"]
    assert payload["exit_decisions"] == []
    assert payload["holdings"][0]["action_effective"] == "hold"
    assert audit["blocked_exits"][0]["held_sessions"] is None


def test_hard_exit_bypasses_early_hysteresis(monkeypatch):
    monkeypatch.setattr(
        ds,
        "_latest_holdings",
        lambda book: {
            "BIIB": {
                "ticker": "BIIB",
                "weight": 0.10,
                "rationale": "prior",
                "conviction": "medium",
            },
        },
    )
    monkeypatch.setattr(ds, "_held_sessions", lambda *args: 1)
    hard = [
        {
            "ticker": "BIIB",
            "action": "exit",
            "reason": "stop and trend broke",
            "reason_code": "technical_break",
            "evidence": ["daily close below stop"],
            "why_now": "close",
        }
    ]
    payload, audit = ds.normalize(
        "autonomous",
        _args(exits=hard),
        early_exit_hysteresis=True,
        deterministic_sizing=True,
    )
    assert payload["holdings"] == []
    assert payload["exit_decisions"][0]["ticker"] == "BIIB"
    assert audit["blocked_early_exits"] == []


def test_us_stock_only_deterministic_sizing_and_identity(monkeypatch):
    monkeypatch.setattr(ds, "_latest_holdings", lambda book: {})
    monkeypatch.setattr(
        ds,
        "_instrument_identity",
        lambda ticker: (
            {"kind": "etf", "status": "trusted_etf_metadata", "verified": True}
            if ticker == "SPY"
            else _common_identity(ticker)
        ),
    )
    names = [_holding(f"S{i}") for i in range(8)] + [_holding("SPY")]
    payload, audit = ds.normalize(
        "autonomous",
        _args(names),
        stock_only=True,
        deterministic_sizing=True,
    )
    assert "SPY" not in {h["ticker"] for h in payload["holdings"]}
    assert round(sum(h["weight"] for h in payload["holdings"]), 4) == 0.8
    assert all(h["weight"] <= 0.15 for h in payload["holdings"])
    assert all(
        h["weight_source"] == "deterministic_conviction_allocator.v2"
        for h in payload["holdings"]
    )
    assert audit["sizing"]["model_weight_is_advisory_only"] is True
    assert audit["rejected"] == [{"ticker": "SPY", "reason": "trusted_etf_metadata"}]


def test_hold_quantization_never_rounds_valid_full_book_over_one(monkeypatch):
    from portfolio import paper_account

    tickers = [f"HOLD{i}" for i in range(6)]
    monkeypatch.setattr(
        ds,
        "_latest_holdings",
        lambda book: {
            ticker: {
                "ticker": ticker,
                "weight": 0.1666666,
                "rationale": "existing position",
                "conviction": "medium",
            }
            for ticker in tickers
        },
    )
    payload, audit = ds.normalize(
        "autonomous",
        _args([_holding(ticker, action="hold") for ticker in tickers]),
        deterministic_sizing=True,
    )
    target = {row["ticker"]: row["weight"] for row in payload["holdings"]}

    assert math.fsum(target.values()) <= 1.0
    assert math.fsum(target.values()) <= math.fsum([0.1666666] * 6)
    assert all(weight > 0.0 for weight in target.values())
    assert paper_account.validate_target_weights(target) == target
    assert audit["sizing"]["weight_quantization"]["gross_increased"] is False


def test_legacy_etf_is_quarantined_until_explicit_migration(monkeypatch):
    monkeypatch.setattr(
        ds,
        "_latest_holdings",
        lambda book: {
            "SPY": {
                "ticker": "SPY",
                "weight": 0.20,
                "rationale": "legacy",
                "conviction": "low",
            },
        },
    )
    monkeypatch.setattr(
        ds,
        "_instrument_identity",
        lambda ticker: {
            "kind": "etf",
            "status": "trusted_etf_metadata",
            "verified": True,
        },
    )
    payload, audit = ds.normalize(
        "autonomous",
        _args(),
        stock_only=True,
        early_exit_hysteresis=True,
        deterministic_sizing=True,
    )
    row = payload["holdings"][0]
    assert row["ticker"] == "SPY" and row["weight"] == pytest.approx(0.20)
    assert row["action_effective"] == "quarantine_hold" and row["quarantined"] is True
    assert audit["quarantined"] == [{"ticker": "SPY", "reason": "trusted_etf_metadata"}]

    migration = [
        {
            "ticker": "SPY",
            "action": "exit",
            "reason": "audited stock-only migration",
            "reason_code": "legacy_instrument_migration",
            "evidence": ["legacy ETF inventory"],
            "why_now": "stock-only launch",
        }
    ]
    payload, _ = ds.normalize(
        "autonomous",
        _args(exits=migration),
        stock_only=True,
        early_exit_hysteresis=True,
        deterministic_sizing=True,
    )
    assert payload["holdings"] == []
    assert payload["exit_decisions"][0]["reason_code"] == "legacy_instrument_migration"


def test_unverified_new_us_instrument_fails_closed(monkeypatch):
    monkeypatch.setattr(ds, "_latest_holdings", lambda book: {})
    monkeypatch.setattr(
        ds,
        "_instrument_identity",
        lambda ticker: {
            "kind": "unknown",
            "status": "unverified_instrument_identity",
            "verified": False,
        },
    )
    payload, audit = ds.normalize(
        "autonomous",
        _args([_holding("MYSTERY")]),
        stock_only=True,
        deterministic_sizing=True,
    )
    assert payload["holdings"] == []
    assert audit["rejected"] == [
        {"ticker": "MYSTERY", "reason": "unverified_instrument_identity"}
    ]


def test_nested_trusted_metadata_identifies_non_allowlisted_etf(monkeypatch):
    # Keep the identity contract hermetic: CI intentionally does not receive the
    # VPS-owned signal/data tree. ARKK is outside the retired ETF desk's narrow
    # allowlist, while a trusted nested Macro contract explicitly identifies it
    # as an ETF. A mere ticker artifact cannot authenticate a common stock.
    from brain import intake
    from portfolio import etf_universe

    monkeypatch.setattr(etf_universe, "is_etf", lambda ticker: False)
    monkeypatch.setattr(etf_universe, "name_of", lambda ticker: None)
    monkeypatch.setattr(
        intake,
        "_read",
        lambda rel: {"meta": {"grp": "Macro ETF"}} if rel == "gex/ARKK.json" else {},
    )
    identity = ds._instrument_identity("ARKK")
    assert identity["kind"] == "etf" and identity["verified"] is True


def test_symbol_level_gex_artifact_cannot_authenticate_etf_as_common_stock(monkeypatch):
    # IBIT has local GEX/flow artifacts, but those prove observation—not security
    # type. It has no positively classified company stock-data contract and must
    # never slip through the US stock-only gate merely by being absent from the
    # retired ETF desk's finite allowlist.
    identity = ds._instrument_identity("IBIT")
    assert identity["kind"] != "common_stock"

    monkeypatch.setattr(ds, "_latest_holdings", lambda book: {})
    payload, audit = ds.normalize(
        "autonomous",
        _args([_holding("IBIT")]),
        stock_only=True,
        deterministic_sizing=True,
    )
    assert payload["holdings"] == []
    assert audit["rejected"] == [
        {"ticker": "IBIT", "reason": identity["status"]}
    ]


def test_regional_allocator_ignores_numeric_weights_without_forcing_names(monkeypatch):
    monkeypatch.setattr(ds, "_latest_holdings", lambda book: {})
    high = _holding("600519.SS", conviction="high", weight=0.01)
    low = _holding("300750.SZ", conviction="low", weight=0.99)
    payload, audit = ds.normalize(
        "china", _args([high, low]), deterministic_sizing=True
    )
    by_ticker = {row["ticker"]: row for row in payload["holdings"]}
    assert by_ticker["600519.SS"]["weight"] == pytest.approx(0.18)
    assert by_ticker["300750.SZ"]["weight"] == pytest.approx(0.06)
    assert by_ticker["300750.SZ"]["proposed_weight"] == pytest.approx(0.99)
    assert (
        audit["sizing"]["policy"] == "deterministic_incremental_regional_allocator.v1"
    )
    assert audit["sizing"]["no_forced_marginal_names"] is True


def test_regional_schema_requires_action_evidence_but_not_numeric_weight():
    schema = ds.enhance_schema(
        {
            "type": "object",
            "properties": {
                "holdings": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {"weight": {"type": "number"}},
                        "required": ["ticker", "weight"],
                    },
                }
            },
            "required": ["holdings", "summary"],
        }
    )
    required = set(schema["properties"]["holdings"]["items"]["required"])
    assert {
        "action",
        "conviction",
        "evidence",
        "why_now",
        "falsifier",
        "exit_plan",
    } <= required
    assert "weight" not in required
    assert (
        "legacy_instrument_migration"
        in (
            schema["properties"]["exit_decisions"]["items"]["properties"][
                "reason_code"
            ]["enum"]
        )
    )


def test_all_three_daily_logs_preserve_per_name_governance(tmp_path, monkeypatch):
    from bot import autonomous, china, hk
    from portfolio import registry

    monkeypatch.setattr(registry, "data_dir", lambda book: tmp_path / book)
    holding = {
        **_holding("TEST", action="trim", weight=0.06),
        "proposed_weight": 0.99,
        "weight_source": "deterministic_trim.v1",
        "action_requested": "trim",
        "action_effective": "trim",
        "trim_intensity": "standard",
        "carried_forward": False,
    }
    submission = {"holdings": [holding], "summary": "audited"}
    target = {"TEST": 0.06}
    autonomous._append_decision_log(
        "2026-08-08", submission, [], [], {},
        target_status="executed", effective_target=target,
    )
    china._append_decision_log(
        "2026-08-08", submission, [], [], {},
        target_status="executed", effective_target=target,
    )
    hk._append_decision_log(
        "2026-08-08", submission, [], [], {},
        target_status="executed", effective_target=target,
    )
    for book in ("autonomous", "china", "hk"):
        row = json.loads(
            (tmp_path / book / "decisions.jsonl").read_text().splitlines()[-1]
        )
        logged = row["holdings"][0]
        assert logged["action_requested"] == logged["action_effective"] == "trim"
        assert logged["trim_intensity"] == "standard"
        assert logged["proposed_weight"] == pytest.approx(0.99)
        assert logged["weight_source"] == "deterministic_trim.v1"
        assert logged["evidence"] == ["trusted:test"]
        assert logged["source_provenance"] == ["prophet:index:test"]
        assert row["target_status"] == "executed"
        assert row["decision_effective"] is True
        assert row["effective_holdings"][0]["weight"] == pytest.approx(0.06)
