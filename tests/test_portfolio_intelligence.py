"""Offline contract tests for the bounded Mastermind Portfolio intelligence plane."""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from brain import portfolio_intelligence as pi
from portfolio import entry_engine, prophet_feed


def _day(days_ago: int = 0) -> str:
    return (datetime.now(UTC).date() - timedelta(days=days_ago)).isoformat()


def _write(root, rel: str, payload) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload if isinstance(payload, str) else json.dumps(payload))


@pytest.fixture
def macro_root(monkeypatch, tmp_path):
    root = tmp_path / "macro"
    monkeypatch.setattr(pi, "_V", root)
    return root


def test_context_catalog_maps_surfaces_and_reports_health(macro_root):
    _write(macro_root, "data/regime/latest.json", {"asof": _day(), "quad": "Q1"})
    _write(macro_root, "site/sectordata/sector_central.json", {"as_of": _day(12)})
    _write(macro_root, "site/intelligence/briefing.json", "{not-json")

    result = pi.context_catalog()
    by_id = {row["id"]: row for row in result["surfaces"]}

    assert result["policy"] == {
        "read_only": True,
        "bounded_allowlist": True,
        "arbitrary_filesystem_access": False,
        "signals_are_context_not_orders": True,
    }
    assert by_id["macro_context"]["status"] == "fresh"
    assert by_id["sector_central"]["status"] == "stale"
    assert by_id["intelligence_hub"]["status"] == "malformed"
    assert by_id["prophet"]["status"] == "missing"
    assert by_id["sector_central"]["url"] == "https://www.mastermind-x.com/sector_central.html#"
    assert all(not artifact["execution_authority"]
               for row in result["surfaces"] for artifact in row["artifacts"])


def test_prophet_board_separates_discovery_and_management(monkeypatch, macro_root):
    _write(macro_root, "site/prophet/index.json", {
        "schema": "prophet.index/v1", "asof": _day(), "authority_tier": "display"
    })
    plans = [
        {"ticker": "AAA", "plan_id": "a", "entry": 100, "invalidation": 90, "t1": 120,
         "t2": 140, "trigger": 101, "conviction": 90, "phase": "pre_trigger",
         "recommended_action": "enter", "signal_date": _day(1), "age_days": 1},
        {"ticker": "BBB", "plan_id": "b", "entry": 50, "invalidation": 45, "t1": 60,
         "t2": 70, "trigger": 51, "conviction": 80, "phase": "pre_trigger",
         "recommended_action": "wait", "signal_date": _day(2), "age_days": 2},
        {"ticker": "CCC", "plan_id": "c", "entry": 30, "invalidation": 27, "t1": 36,
         "t2": 42, "trigger": 31, "conviction": 85, "phase": "triggered_pre_t1",
         "recommended_action": "hold", "signal_date": _day(), "age_days": 0},
        {"ticker": "DDD", "plan_id": "d", "entry": 20, "invalidation": 18, "t1": 24,
         "t2": 28, "trigger": 21, "conviction": 70, "phase": "triggered_pre_t1",
         "recommended_action": "trail", "signal_date": _day(), "age_days": 0},
    ]
    monkeypatch.setattr(prophet_feed, "index", lambda: {
        "asof": _day(), "authority_tier": "display", "gate_go": False,
    })
    monkeypatch.setattr(prophet_feed, "plans", lambda: plans)

    result = pi.prophet_board(limit=10, held=["BBB", "ZZZ"])

    assert [row["ticker"] for row in result["discovery"]] == ["AAA"]
    assert [row["ticker"] for row in result["management"]] == ["BBB", "CCC", "DDD"]
    assert result["management"][0]["book_state"] == "held"
    assert result["held_without_active_plan"] == ["ZZZ"]
    assert result["discovery"][0]["geometry"]["reward_to_t1_r"] == 2.0
    assert result["authority_tier"] == "display"
    assert result["context_only"] is True


def test_sector_rotation_is_ranked_projected_and_bounded(macro_root):
    def row(ticker, rank, score, kind="sector"):
        return {
            "id": ticker.lower(), "ticker": ticker, "name": ticker, "kind": kind,
            "conviction": {"score": score, "dir": "up"},
            "cycle": {"phase": "Expansion", "pos": 50, "proj": {"tilt": "tailwind"}},
            "momentum": {"rs_rank": rank, "lead": "leading"},
            "rotation": {"rank": rank, "score": score, "state": "FRESH BUY", "stale": False},
            "reasoning": [{"layer": "Momentum", "tier": "confirmer", "stance": "bullish",
                           "en": f"{ticker} leads"}],
        }

    _write(macro_root, "site/sectordata/sector_central.json", {
        "as_of": _day(),
        "market": {"risk_on": True, "headline_en": "rotation broadening"},
        "sectors": [row("XLB", 2, 70), row("XLK", 1, 80)],
        "baskets": [row("IGV", 1, 75, "basket"), row("ITA", 2, 72, "basket")],
    })

    result = pi.sector_rotation(limit=1)

    assert [row["ticker"] for row in result["sectors"]] == ["XLK"]
    assert [row["ticker"] for row in result["baskets"]] == ["IGV"]
    assert "components" not in result["sectors"][0]
    assert "reasoning" not in result["sectors"][0]
    assert result["health"]["status"] == "fresh"


def test_technical_packet_combines_typed_sources_and_denies_path_traversal(
    monkeypatch, macro_root
):
    _write(macro_root, "site/stockdata/AAPL.json", {
        "ticker": "AAPL", "name": "Apple", "sector": "Technology", "asof": _day(),
        "tech": {"price": 200, "above200": True, "rsi14": 61, "macd_pos": True,
                 "pct_vs_20dma": 2.0, "cmf20": 0.2},
        "mtf": {
            "D": {"macd_pos": True, "rsi14": 61, "stoch": 70, "spark_rsi": list(range(50))},
            "W": {"macd_pos": True, "rsi14": 58, "stoch": 60},
        },
        "signal": {"eligible": True, "tier_cascade": "T1", "ticks": 4},
        "entry_signal": {"status": "enter", "buy_zone": {"low": 195, "high": 201}},
        "ladder": {"state": "RALLY ON", "action": "BUY"},
    })
    _write(macro_root, "site/signals/AAPL.json", {
        "ticker": "AAPL", "asof": _day(), "tf": "3D", "state": "long-bias",
        "above200": True, "weekly_bull": True, "trail_stop": 185, "trail_breach": False,
        "markers": [{"date": str(i), "type": "buy"} for i in range(8)],
        "risk_flags": [False] * 8,
    })
    _write(macro_root, "site/options_structure/gex_state/AAPL.json", {
        "asof": _day(), "spot": 200, "gamma_regime": "DRIFT", "call_wall": 210,
        "authority_tier": "display",
    })
    _write(macro_root, "site/flow/AAPL.json", {
        "asof": _day(), "available": True, "spot": 200, "premium_mn": 500,
        "positioning": {"tone": "bullish", "top_build": list(range(100))},
        "verdict": {"tone": "bullish", "direction_reliable": False},
    })
    _write(macro_root, "site/prophet/index.json", {"asof": _day()})
    _write(macro_root, "site/factordata/contracts/golden_signals.json", {
        "schema": "signal_golden_vectors/v1", "as_of": _day(),
        "oracle": "engine.canon.confluence_signals", "math": {"rsiLen": 14},
        "symbols": [{"symbol": "AAPL", "region": "US", "inputs_hash": "sha256:x",
                     "n_signals": 20}],
    })
    _write(macro_root, "site/basketdata/oracle_state.json", {
        "schema": "oracle_state.v1", "asof": _day(), "regime": {"breadth": 0.7},
        "complexes": [{"id": "ai", "state": "active", "direction": "up"}],
    })
    _write(macro_root, "site/basketdata/oracle_reversion_state.json", {
        "schema": "oracle_reversion_state.v1", "asof": _day(), "tier": "display",
        "signals": [{"id": "r1", "fired_today": True, "authority_level": "display"}],
    })
    monkeypatch.setattr(entry_engine, "assess", lambda ticker: {
        "ticker": ticker, "verdict": "clean", "buyable": True, "entry_score": 80,
        "sources": ["stockdata", "signal_gate"],
    })
    plan = {"ticker": "AAPL", "plan_id": "p1", "entry": 198, "invalidation": 190,
            "t1": 214, "t2": 225, "trigger": 199, "conviction": 92,
            "phase": "triggered_pre_t1", "recommended_action": "hold", "age_days": 1}
    monkeypatch.setattr(prophet_feed, "plan_for", lambda ticker: plan)

    result = pi.technical_packet("aapl")

    assert result["ticker"] == "AAPL"
    assert result["entry_assessment"]["verdict"] == "clean"
    assert result["multi_timeframe"]["D"]["stoch"] == 70
    assert "spark_rsi" not in result["multi_timeframe"]["D"]
    assert len(result["terminal_signal"]["recent_markers"]) == 3
    assert result["golden_oracle"]["golden_contract"]["ticker_vector"]["symbol"] == "AAPL"
    assert result["options_structure"]["gex"]["call_wall"] == 210
    assert result["prophet_plan"]["provenance"]["context_only"] is True
    assert pi.technical_packet("../../etc/passwd")["status"] == "invalid_ticker"


def test_market_packet_is_compact_start_of_session_overview(monkeypatch, macro_root, tmp_path):
    repo = tmp_path / "repo"
    monkeypatch.setattr(pi, "_ROOT", repo)
    _write(repo, "data/portfolios/autonomous/latest.json", {
        "as_of": _day(), "nav": 1_010_000, "gross": 0.72, "cash": 0.28,
        "summary": "stock-first book", "positions": [
            {"ticker": "AAPL", "weight": 0.12, "held_days": 15},
            {"ticker": "MSFT", "weight": 0.10, "held_days": 10},
        ],
    })
    _write(repo, "data/portfolios/autonomous/account.json", {
        "cash": 282_800, "positions": {"AAPL": {}, "MSFT": {}}
    })
    _write(macro_root, "data/regime/latest.json", {
        "asof": _day(), "quad": "Q1", "quad_name": "Goldilocks",
        "sector_rs": [{"ticker": "XLK", "rank": 1}],
    })
    _write(macro_root, "site/sectordata/sector_central.json", {
        "as_of": _day(), "market": {"risk_on": True}, "sectors": [], "baskets": [],
    })
    _write(macro_root, "site/prophet/index.json", {"asof": _day()})
    monkeypatch.setattr(prophet_feed, "index", lambda: {
        "asof": _day(), "authority_tier": "display", "gate_go": False,
    })
    monkeypatch.setattr(prophet_feed, "plans", list)

    result = pi.market_packet()

    assert result["book"]["book"] == "autonomous"
    assert result["book"]["n_positions"] == 2
    assert result["regime"]["quad"] == "Q1"
    assert result["sector_rotation"]["market"]["risk_on"] is True
    assert result["prophet"]["held_without_active_plan"] == ["AAPL", "MSFT"]
    assert {row["id"] for row in result["data_health"]["critical"]} == {
        "macro_context", "sector_central", "prophet", "technical_lab", "neural_web"
    }
    assert result["usage"]["signals_are_context_not_orders"] is True


def test_neural_web_packet_unions_requested_and_held_with_hard_authority_fence(
    monkeypatch, macro_root, tmp_path
):
    repo = tmp_path / "repo"
    monkeypatch.setattr(pi, "_ROOT", repo)
    _write(repo, "data/portfolios/autonomous/latest.json", {
        "as_of": _day(), "positions": [
            {"ticker": "AAPL", "weight": 0.2},
            {"ticker": "MSFT", "weight": 0.15},
        ],
    })
    _write(repo, "data/portfolios/autonomous/account.json", {
        "cash": 650_000, "positions": {"AAPL": {}, "MSFT": {}},
    })
    candidate = {
        "bottom": {"as_of": _day(), "bottom_state": "WATCH", "coiled": True,
                   "dist_21d_low_pct": 4.2},
        "valuation": {"ev_sales": 8.0, "ev_ebit": 25.0, "p_fcf": 30.0, "pe": 28.0},
        "structural": {"decline_geometry": "base", "sponsorship_state": "tailwind"},
        "earnings_ctx": {"days_to_earnings": 14, "is_blackout": False},
        "options": {"as_of": _day(), "iv30": 0.25, "gamma_regime": "long",
                    "evidence_quality": "full", "wall_up_dist_pct": 5.0},
        "kernel": {"fdr_cleared": False, "note": "annotate only"},
        "allowed_behavior": "annotate_only",
    }
    _write(macro_root, "site/neuralwebdata/mastermind_context.json", {
        "schema": "neural_web_mastermind_context.v1",
        "as_of": _day(),
        "freshest_market_asof": _day(),
        # Even a malformed/upgraded artifact cannot grant authority through this reader.
        "authority": {"can_add_candidates": True, "can_raise_size": True,
                      "can_block_entry": True, "notes": "fixture attempts escalation"},
        "freshness": {"market": {"as_of": _day(), "stale": False}},
        "lobes": {
            "market": {
                "verdict": {"verdict": "RISK_ON", "score": 70},
                "radar": {"state": "calm", "ceiling": 80},
                "vol": {"asof": _day(), "regime": "normal", "vix": 15},
                "breadth": {"date": _day(), "pct_above_50": 70},
            },
            "macro_weather": {"state": "constructive", "details": ["x" * 500] * 30},
            "reliability": {"standing_law": "display only"},
        },
        "lobe_manifest": [
            {"artifact_id": f"lobe-{i}", "asof": _day(), "stale": False,
             "tier": "display", "horizon_role": "context", "has_rich_summary": True}
            for i in range(30)
        ],
        "candidate_context": {"AAPL": candidate, "NVDA": candidate},
        "book_context": {
            "top_macro_contradictions": [{"pair_id": "credit-equity", "note": "x" * 500}] * 10,
            "decaying_families": ["decay " + "x" * 400] * 20,
            "bottom_summary_counts": {"bottom_state": {"WATCH": 100}},
        },
        "gap_notes": ["HK candidate context is not published"],
    })

    result = pi.neural_web_packet("autonomous", ["NVDA", "../../secret"])

    assert result["book"] == "autonomous"
    assert [row["ticker"] for row in result["candidates"]] == ["NVDA", "AAPL", "MSFT"]
    assert result["candidates"][0]["origin"] == "requested"
    assert result["candidates"][1]["origin"] == "held"
    assert result["candidates"][2]["available"] is False
    assert result["candidate_coverage"]["rejected_tickers"] == ["../../secret"]
    assert result["authority"]["artifact_declaration"]["can_add_candidates"] is True
    assert not any(result["authority"]["effective"].values())
    assert result["provenance"]["artifact"] == "site/neuralwebdata/mastermind_context.json"
    assert len(json.dumps(result, ensure_ascii=False).encode()) <= 8_000


def test_neural_web_packet_caps_candidate_context_and_reports_omissions(
    monkeypatch, macro_root, tmp_path
):
    repo = tmp_path / "repo"
    monkeypatch.setattr(pi, "_ROOT", repo)
    _write(repo, "data/portfolios/hk/latest.json", {"as_of": _day(), "positions": []})
    _write(repo, "data/portfolios/hk/account.json", {"cash": 1_000_000, "positions": {}})
    names = [f"{i:04d}.HK" for i in range(1, 10)]
    _write(macro_root, "site/neuralwebdata/mastermind_context.json", {
        "schema": "neural_web_mastermind_context.v1", "as_of": _day(),
        "authority": {}, "lobes": {}, "candidate_context": {
            ticker: {"kernel": {"fdr_cleared": False}, "allowed_behavior": "annotate_only"}
            for ticker in names
        },
    })

    result = pi.neural_web_packet("hk", names)

    assert result["candidate_coverage"]["returned"] == 6
    assert result["candidate_coverage"]["omitted_tickers"] == names[6:]
    assert len(result["candidates"]) == 6
    assert len(json.dumps(result, ensure_ascii=False).encode()) <= 8_000
    assert pi.neural_web_packet("flagship")["status"] == "unsupported_book"
    assert pi.neural_web_packet("hk", {"ticker": "0700.HK"})["status"] == "invalid_tickers_type"


def test_surface_packet_reads_only_catalog_ids_and_bounds_large_contract(macro_root):
    queue = [
        {"ticker": f"T{i:03d}", "priority": 100 - i, "confidence": "high",
         "read": "x" * 2_000, "evidence": ["e" * 1_000] * 20}
        for i in range(100)
    ]
    _write(macro_root, "site/intelligence/briefing.json", {
        "schema": "intelligence.briefing.v1", "is_context_only": True, "as_of": _day(),
        "macro_context": {"regime": "risk-on"}, "n_priority": 100,
        "priority_queue": queue, "divergences": queue,
    })

    result = pi.surface_packet("intelligence_hub", limit=5)
    invalid = pi.surface_packet("../../data/regime/latest.json")

    assert result["surface_id"] == "intelligence_hub"
    assert result["execution_authority"] is False
    assert result["artifacts"][0]["source"]["artifact"] == "site/intelligence/briefing.json"
    assert len(result["artifacts"][0]["content"]["priority_queue"]) <= 5
    assert len(json.dumps(result, ensure_ascii=False).encode()) <= 8_000
    assert invalid["status"] == "invalid_surface_id"
    assert invalid["execution_authority"] is False


def test_surface_packet_preserves_each_allowlisted_artifact_under_shared_budget(macro_root):
    ranked = [{"underlying": f"T{i:03d}", "score": i, "note": "x" * 1_000} for i in range(50)]
    _write(macro_root, "site/options_ivspread/latest.json", {
        "schema": "iv/v1", "as_of": _day(), "ranked": ranked, "n": 50,
    })
    _write(macro_root, "site/options_skew/latest.json", {
        "schema": "skew/v1", "as_of": _day(), "ranked": ranked, "n": 50,
    })
    _write(macro_root, "site/basketdata/options_witness.json", {
        "schema": "witness/v1", "as_of": _day(),
        "themes": {f"theme_{i}": {"note": "x" * 1_000} for i in range(50)},
    })

    result = pi.surface_packet("options", limit=8)

    assert len(result["artifacts"]) == 3
    assert {row["source"]["artifact"] for row in result["artifacts"]} == {
        "site/options_ivspread/latest.json",
        "site/options_skew/latest.json",
        "site/basketdata/options_witness.json",
    }
    assert result["per_artifact_limit"] == 2
    assert len(json.dumps(result, ensure_ascii=False).encode()) <= 8_000


def test_every_catalog_surface_id_is_a_valid_bounded_request(macro_root):
    for spec in pi._SURFACES:
        result = pi.surface_packet(spec["id"], limit=2)
        assert result["surface_id"] == spec["id"]
        assert result["status"] in {"ok", "unavailable"}
        assert result["execution_authority"] is False
        assert len(json.dumps(result, ensure_ascii=False).encode()) <= 8_000
