"""Focused offline tests for the bounded portfolio forward-evaluation contract."""
from __future__ import annotations

import json
from pathlib import Path

import pytest


SHA_A = "a" * 40
SHA_B = "b" * 40


def _write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
                    encoding="utf-8")


@pytest.fixture()
def isolated_root(tmp_path: Path, monkeypatch) -> Path:
    from portfolio import forward_evaluation, registry

    monkeypatch.setattr(registry, "_ROOT", tmp_path)
    monkeypatch.setattr(forward_evaluation, "_utc_today", lambda: "2026-08-13")
    return tmp_path


def _activate_start() -> None:
    from portfolio import forward_evaluation

    forward_evaluation.initialize_start(SHA_A, "2026-08-11")
    forward_evaluation.finalize_start(SHA_A)


def _seed_legacy(book_dir: Path) -> None:
    _write_json(book_dir / "account.json", {
        "starting_nav": 1_000_000.0,
        "cash": 400_000.0,
        # Deliberately no current_price: concentration must prefer latest.json weights.
        "positions": {
            "AAPL": {"shares": 4_000.0, "avg_cost": 100.0},
            "MSFT": {"shares": 500.0, "avg_cost": 400.0},
        },
    })
    _write_json(book_dir / "latest.json", {
        "as_of": "2026-08-11",
        "gross": 0.60,
        "cash": 0.40,
        "positions": [
            {"ticker": "AAPL", "weight": 0.40},
            {"ticker": "MSFT", "weight": 0.20},
        ],
    })
    _write_jsonl(book_dir / "decisions.jsonl", [{
        "asof": "2026-08-11", "target_status": "executed", "decision_effective": True,
        "effective_holdings": [{"ticker": "AAPL", "action_effective": "hold"}],
    }])
    _write_jsonl(book_dir / "fills.jsonl", [{
        "date": "2026-08-11", "ticker": "AAPL", "side": "buy",
        "shares": 100.0, "price": 100.0, "value": 10_000.0,
    }])
    _write_jsonl(book_dir / "nav_history.jsonl", [{
        "date": "2026-08-11", "nav": 1_000_000.0, "cash": 400_000.0,
        "invested": 600_000.0, "spy_nav": 1_000_000.0, "benchmark": "SPY",
    }])
    _write_json(book_dir / "positions_ledger.json", {})


def _seed_forward(root: Path, book_dir: Path) -> None:
    _write_json(book_dir / "latest.json", {
        "as_of": "2026-08-13", "gross": 0.80, "cash": 0.20,
        "positions": [
            {"ticker": "AAPL", "weight": 0.50},
            {"ticker": "MSFT", "weight": 0.20},
            {"ticker": "GOOG", "weight": 0.10},
        ],
    })
    legacy_decision = json.loads((book_dir / "decisions.jsonl").read_text().splitlines()[0])
    decisions = [legacy_decision, {
        "asof": "2026-08-12",
        "target_status": "executed",
        "decision_effective": True,
        "effective_holdings": [{
            "ticker": "GOOG", "weight": 0.10, "action_effective": "add",
            "evidence": ["prophet:index:2026-08-12"],
            "source_provenance": ["prophet:index:2026-08-12"],
            "why_now": "Confirmed turn", "falsifier": "RS breaks",
            "expected_horizon": "21 sessions", "exit_plan": "Exit on falsifier",
        }],
        "requested_exit_decisions": [{"ticker": "AAPL", "reason": "rotate"}],
        "exit_decisions": [{
            "ticker": "AAPL", "reason": "rotate", "why_now": "leadership changed",
            "evidence": ["relative strength"],
        }],
        "submission_audit": {
            "blocked_exits": [{"ticker": "MSFT", "reason": "hysteresis"}],
            "carried": [{"ticker": "MSFT", "reason": "missing_explicit_exit_decision"}],
            "rejected": [],
        },
        "decision_memo": {
            "candidate_funnel": {
                "candidates": ["GOOG", "AMZN", "META"],
                "finalists": ["GOOG", "AMZN"],
            },
            "selected": [{
                "ticker": "GOOG", "source_provenance": ["prophet:index:2026-08-12"],
            }],
            "rejected": [
                {"ticker": "AMZN", "reason": "weaker confirmation", "sources": ["intake"]},
                {"ticker": "META", "reason": None, "sources": ["prophet"]},
            ],
        },
        "executed": [{"ticker": "GOOG", "side": "buy"}],
    }, {
        "asof": "2026-08-13",
        "target_status": "executed",
        "decision_effective": True,
        "effective_holdings": [{"ticker": "GOOG", "action_effective": "hold"}],
        "decision_memo": {
            "candidate_funnel": {"candidates": ["GOOG"], "finalists": ["GOOG"]},
            "selected": [{"ticker": "GOOG", "source_provenance": ["intake"]}],
            "rejected": [],
        },
    }]
    # Reorder the legacy row during compaction: content IDs, not line positions, own the boundary.
    _write_jsonl(book_dir / "decisions.jsonl", [decisions[1], decisions[0], decisions[2]])

    legacy_fill = json.loads((book_dir / "fills.jsonl").read_text().splitlines()[0])
    _write_jsonl(book_dir / "fills.jsonl", [
        {"date": "2026-08-12", "ticker": "GOOG", "side": "buy",
         "shares": 50.0, "price": 100.0, "value": 5_000.0},
        legacy_fill,
        {"date": "2026-08-13", "ticker": "AAPL", "side": "sell",
         "shares": 100.0, "price": 110.0, "value": 11_000.0},
    ])
    _write_jsonl(book_dir / "nav_history.jsonl", [
        {"date": "2026-08-11", "nav": 1_000_000.0, "cash": 400_000.0,
         "invested": 600_000.0, "spy_nav": 1_000_000.0, "benchmark": "SPY"},
        {"date": "2026-08-12", "nav": 1_010_000.0, "cash": 300_000.0,
         "invested": 710_000.0, "spy_nav": 1_005_000.0, "benchmark": "SPY"},
        {"date": "2026-08-13", "nav": 1_020_000.0, "cash": 204_000.0,
         "invested": 816_000.0, "spy_nav": 1_006_000.0, "benchmark": "SPY"},
    ])
    _write_json(book_dir / "positions_ledger.json", {
        "brain:GOOG": {
            "ticker": "GOOG", "sleeve": "brain", "still_open": False,
            "history": [
                {"event": "open", "as_of": "2026-08-12"},
                {"event": "close", "as_of": "2026-08-13"},
            ],
        },
    })
    _write_json(root / "data" / "portfolio_learning" / "autonomous" / "post_sell.json", {
        "schema": "portfolio.post_sell.v1", "book": "autonomous", "asof": "2026-08-13",
        "exits": [
            {"exit_id": "autonomous:2026-08-13:AAPL:2", "exit_date": "2026-08-13",
             "sale_kind": "full_exit", "decision": {
                 "reason": "rotate", "why_now": "leadership changed", "evidence": ["RS"],
             }},
            {"exit_id": "autonomous:2026-08-13:MSFT:3", "exit_date": "2026-08-13",
             "sale_kind": "partial_trim"},
        ],
    })


def test_not_started_and_archived_are_strict_no_write(isolated_root: Path) -> None:
    from portfolio import forward_evaluation

    active = forward_evaluation.evaluate("autonomous", "2026-08-11")
    assert active["status"] == "not_started"
    assert active["sample_counts"] == forward_evaluation._zero_sample_counts()
    assert not forward_evaluation._output_root().exists()

    archived = forward_evaluation.evaluate("flagship", "2026-08-11")
    assert archived["status"] == "archived"
    assert archived["write_permitted"] is False
    assert not forward_evaluation._output_root().exists()


@pytest.mark.parametrize("book", ["../autonomous", "autonomous/../../escape", "/tmp/escape"])
def test_book_paths_reject_request_controlled_segments(isolated_root: Path, book: str) -> None:
    from portfolio import forward_evaluation

    for resolver in (
        forward_evaluation._book_output_dir,
        forward_evaluation._post_sell_path,
        forward_evaluation._portfolio_data_dir,
    ):
        with pytest.raises(ValueError, match="unknown portfolio book"):
            resolver(book)
    assert not (isolated_root / "escape").exists()


def test_start_is_create_once_and_corrupt_existing_marker_freezes(isolated_root: Path) -> None:
    from portfolio import forward_evaluation, registry

    _seed_legacy(registry.data_dir("autonomous"))
    first = forward_evaluation.initialize_start(SHA_A, "2026-08-11")
    path = forward_evaluation._start_path()
    before = path.read_bytes()
    assert first["initialized"] is True
    assert first["release_state"] == "pending_health"
    assert first["books"]["autonomous"]["row_counts"]["decisions"] == 1
    assert first["books"]["autonomous"]["row_hashes"]["decisions"]

    pending = forward_evaluation.evaluate("autonomous", "2026-08-11")
    assert pending["status"] == "not_started"
    assert pending["missing_reason"] == "exact_v2_deployment_health_not_verified"
    assert not forward_evaluation._book_output_dir("autonomous").exists()

    second = forward_evaluation.initialize_start(SHA_A, "2026-08-12")
    assert second["initialized"] is False
    assert second["preserved_existing_start"] is True
    assert second["deployment_sha"] == SHA_A
    assert path.read_bytes() == before

    with pytest.raises(RuntimeError, match="different deployment"):
        forward_evaluation.initialize_start(SHA_B, "2026-08-12")
    finalized = forward_evaluation.finalize_start(SHA_A)
    assert finalized["release_state"] == "active"
    active_bytes = path.read_bytes()
    preserved = forward_evaluation.initialize_start(SHA_B, "2026-08-12")
    assert preserved["deployment_sha"] == SHA_A
    assert path.read_bytes() == active_bytes

    path.write_text("{broken", encoding="utf-8")
    broken = path.read_bytes()
    with pytest.raises(RuntimeError, match="invalid; refusing reset"):
        forward_evaluation.initialize_start(SHA_B, "2026-08-12")
    assert path.read_bytes() == broken


def test_release_cli_override_targets_canonical_live_data_only(
    isolated_root: Path, monkeypatch, capsys,
) -> None:
    from portfolio import forward_evaluation, registry

    canonical = isolated_root / "canonical-live-data"
    _write_jsonl(canonical / "portfolios" / "autonomous" / "decisions.jsonl", [{
        "decision_id": "canonical", "asof": "2026-08-11",
    }])
    _write_jsonl(registry.data_dir("autonomous") / "decisions.jsonl", [
        {"decision_id": "decoy-1", "asof": "2026-08-11"},
        {"decision_id": "decoy-2", "asof": "2026-08-11"},
    ])
    monkeypatch.setenv(forward_evaluation._RELEASE_STATE_ROOT_ENV, str(canonical))

    assert forward_evaluation._cli([
        "init", "--deployment-sha", SHA_A, "--asof", "2026-08-11",
    ]) == 0
    init_payload = json.loads(capsys.readouterr().out)
    marker = canonical / "portfolio_forward_evaluation" / "start.json"
    assert marker.exists()
    assert init_payload["books"]["autonomous"]["row_counts"]["decisions"] == 1
    assert not (isolated_root / "data" / "portfolio_forward_evaluation" / "start.json").exists()
    assert forward_evaluation.load_start() is None  # context reset; normal API sees only decoy data

    assert forward_evaluation._cli(["finalize", "--deployment-sha", SHA_A]) == 0
    capsys.readouterr()
    assert forward_evaluation._cli(["status"]) == 0
    status_payload = json.loads(capsys.readouterr().out)
    assert status_payload["release_state"] == "active"


def test_snapshot_filters_baseline_and_is_byte_idempotent(isolated_root: Path) -> None:
    from portfolio import forward_evaluation, registry

    book_dir = registry.data_dir("autonomous")
    _seed_legacy(book_dir)
    _activate_start()
    _seed_forward(isolated_root, book_dir)

    snapshot = forward_evaluation.evaluate("autonomous", "2026-08-13")
    metrics = snapshot["metrics"]
    assert snapshot["cohort"]["deployment_sha"] == SHA_A
    assert snapshot["sample_counts"] == {
        "marked_sessions": 2, "decisions": 2, "effective_decisions": 2,
        "fills": 2, "closed_positions": 1, "post_sell_sales": 2,
        "selected_names": 2, "rejected_names": 2,
    }
    assert metrics["top_1_weight_pct"]["value"] == 50.0
    assert metrics["top_3_weight_pct"]["value"] == 80.0
    assert metrics["position_hhi"]["value"] == 0.30
    assert metrics["gross_exposure_pct"]["sample_n"] == 1
    assert metrics["cash_pct"]["sample_n"] == 1
    assert metrics["net_exposure_pct"]["status"] == "available"
    assert metrics["decision_count"]["value"] == 2  # legacy row excluded
    assert metrics["fill_count"]["value"] == 2      # legacy buy excluded from count
    assert metrics["candidate_count"]["value"] == 4
    assert metrics["finalist_count"]["value"] == 3
    assert metrics["requested_exit_count"]["value"] == 1
    assert metrics["effective_exit_count"]["value"] == 1
    assert metrics["blocked_exit_count"]["value"] == 1
    assert metrics["omission_carried_exit_count"]["value"] == 1
    assert metrics["closed_hold_days_average"]["value"] == 1.0
    assert metrics["closed_within_1_day_rate_pct"]["value"] == 100.0
    assert metrics["closed_hold_sessions_average"]["value"] == 1.0
    assert metrics["full_exit_hit_rate_pct"]["value"] == 100.0
    assert metrics["full_exit_hit_rate_pct"]["status"] == "partial"
    assert metrics["full_exit_hit_rate_pct"]["missing_reason"] == (
        "some_durable_full_closes_lack_complete_fifo_basis"
    )
    assert metrics["benchmark_session_hit_rate_pct"]["sample_n"] == 1
    assert metrics["full_exit_explicit_memo_coverage_pct"]["value"] == 100.0
    assert metrics["partial_trim_explicit_memo_coverage_pct"]["value"] == 0.0
    assert metrics["entry_evidence_coverage_pct"]["value"] == 100.0
    assert metrics["early_max_adverse_excursion_pct"] == {
        "value": None, "sample_n": 0, "status": "missing",
        "missing_reason": "authoritative_point_in_time_per_ticker_price_path_unavailable",
    }
    assert metrics["return_contribution_by_sleeve_pct"]["status"] == "missing"
    assert all(set(metric) == {"value", "sample_n", "status", "missing_reason"}
               for metric in metrics.values())

    dated = forward_evaluation._book_output_dir("autonomous") / "2026-08-13.json"
    latest = forward_evaluation._book_output_dir("autonomous") / "latest.json"
    before = (dated.read_bytes(), latest.read_bytes(), dated.stat().st_mtime_ns,
              latest.stat().st_mtime_ns)
    repeated = forward_evaluation.evaluate("autonomous", "2026-08-13")
    after = (dated.read_bytes(), latest.read_bytes(), dated.stat().st_mtime_ns,
             latest.stat().st_mtime_ns)
    assert repeated == snapshot
    assert after == before


def test_active_missing_artifacts_never_become_zero(isolated_root: Path) -> None:
    from portfolio import forward_evaluation

    _activate_start()
    snapshot = forward_evaluation.evaluate("autonomous", "2026-08-11")
    assert snapshot["sample_counts"] == forward_evaluation._zero_sample_counts()
    assert snapshot["metrics"]["gross_exposure_pct"]["value"] is None
    assert snapshot["metrics"]["marked_session_count"]["value"] is None
    assert snapshot["metrics"]["decision_count"]["value"] is None
    assert snapshot["metrics"]["traded_value_turnover_pct"]["value"] is None
    assert snapshot["metrics"]["max_drawdown_pct"]["status"] == "insufficient_sample"


def test_pending_transaction_admits_only_post_baseline_rows_after_health(isolated_root: Path) -> None:
    from portfolio import forward_evaluation, registry

    forward_evaluation.initialize_start(SHA_A, "2026-08-11")
    _write_jsonl(registry.data_dir("autonomous") / "decisions.jsonl", [
        {"asof": "2026-08-11", "target_status": "executed", "decision_effective": True},
        {"asof": "2026-08-12", "target_status": "executed", "decision_effective": True},
    ])
    pending = forward_evaluation.evaluate("autonomous", "2026-08-12")
    assert pending["status"] == "not_started"
    assert not forward_evaluation._book_output_dir("autonomous").exists()
    forward_evaluation.finalize_start(SHA_A)
    snapshot = forward_evaluation.evaluate("autonomous", "2026-08-12")
    assert snapshot["sample_counts"]["decisions"] == 2
    assert snapshot["cohort"]["quarantined_start_day_sources"] == []
    assert snapshot["cohort"]["boundary"] == (
        "stopped_service_baseline_ids_plus_inclusive_date_window"
    )


def test_stopped_service_baseline_blocks_legacy_and_admits_target_same_day_rows(
    isolated_root: Path,
) -> None:
    from portfolio import forward_evaluation, registry

    book_dir = registry.data_dir("autonomous")
    _seed_legacy(book_dir)
    forward_evaluation.initialize_start(SHA_A, "2026-08-11")
    # The service is stopped at baseline creation. Any mutation after this point belongs to the
    # target v2 process; evaluation itself remains dormant until exact-SHA health activation.
    _write_jsonl(book_dir / "decisions.jsonl", [{
        "asof": "2026-08-11", "target_status": "executed", "decision_effective": True,
        "effective_holdings": [{"ticker": "AAPL", "action_effective": "add"}],
        "executed": [{"ticker": "AAPL", "side": "buy"}],
    }])
    _write_jsonl(book_dir / "fills.jsonl", [{
        "date": "2026-08-11", "ticker": "AAPL", "side": "buy",
        "shares": 101.0, "price": 100.0, "value": 10_100.0,
    }])
    _write_jsonl(book_dir / "nav_history.jsonl", [{
        "date": "2026-08-11", "nav": 1_001_000.0, "cash": 399_000.0,
        "invested": 602_000.0, "spy_nav": 1_000_500.0, "benchmark": "SPY",
    }])
    _write_json(book_dir / "positions_ledger.json", {
        "brain:AAPL": {"ticker": "AAPL", "still_open": False, "history": [
            {"event": "open", "as_of": "2026-08-11"},
            {"event": "close", "as_of": "2026-08-11"},
        ]},
    })
    _write_json(isolated_root / "data" / "portfolio_learning" / "autonomous" /
                "post_sell.json", {"exits": [{
                    "exit_id": "autonomous:2026-08-11:AAPL:1",
                    "exit_date": "2026-08-11", "sale_kind": "full_exit",
                }]})

    assert forward_evaluation.evaluate("autonomous", "2026-08-12")["status"] == "not_started"
    forward_evaluation.finalize_start(SHA_A)
    snapshot = forward_evaluation.evaluate("autonomous", "2026-08-12")
    assert snapshot["sample_counts"]["decisions"] == 1
    assert snapshot["sample_counts"]["fills"] == 1
    assert snapshot["sample_counts"]["closed_positions"] == 1
    assert snapshot["sample_counts"]["post_sell_sales"] == 1


def test_explicit_logical_id_prevents_mutable_legacy_row_resurrection(
    isolated_root: Path,
) -> None:
    from portfolio import forward_evaluation, registry

    path = registry.data_dir("autonomous") / "decisions.jsonl"
    _write_jsonl(path, [{
        "decision_id": "legacy-decision", "asof": "2026-08-11",
        "target_status": "executed", "decision_effective": True,
    }])
    _activate_start()
    _write_jsonl(path, [
        {"decision_id": "legacy-decision", "asof": "2026-08-11",
         "target_status": "executed", "decision_effective": True, "later_grade": "augmented"},
        {"decision_id": "v2-decision", "asof": "2026-08-11",
         "target_status": "executed", "decision_effective": True},
    ])
    snapshot = forward_evaluation.evaluate("autonomous", "2026-08-11")
    assert snapshot["sample_counts"]["decisions"] == 1


def test_same_asof_correction_preserves_prior_revision_and_receipt(isolated_root: Path) -> None:
    from portfolio import forward_evaluation, registry

    book_dir = registry.data_dir("autonomous")
    _seed_legacy(book_dir)
    _activate_start()
    _seed_forward(isolated_root, book_dir)
    prior = forward_evaluation.evaluate("autonomous", "2026-08-13")

    latest = json.loads((book_dir / "latest.json").read_text(encoding="utf-8"))
    latest["positions"][0]["weight"] = 0.45
    _write_json(book_dir / "latest.json", latest)
    replacement = forward_evaluation.evaluate("autonomous", "2026-08-13")
    assert replacement["metrics"]["top_1_weight_pct"]["value"] == 45.0

    out = forward_evaluation._book_output_dir("autonomous")
    revisions = list((out / "revisions" / "2026-08-13").glob("*.json"))
    receipts = list((out / "corrections" / "2026-08-13").glob("*.json"))
    assert len(revisions) == 1 and len(receipts) == 1
    assert json.loads(revisions[0].read_text(encoding="utf-8")) == prior
    receipt = json.loads(receipts[0].read_text(encoding="utf-8"))
    assert receipt["reason"] == "durable_source_artifact_changed_for_same_asof"
    assert receipt["prior_snapshot_sha256"] != receipt["replacement_snapshot_sha256"]

    forward_evaluation.evaluate("autonomous", "2026-08-13")
    assert len(list((out / "revisions" / "2026-08-13").glob("*.json"))) == 1
    assert len(list((out / "corrections" / "2026-08-13").glob("*.json"))) == 1


def test_read_only_api_serves_status_without_evaluating_or_writing(
    isolated_root: Path, monkeypatch,
) -> None:
    from app import web
    from portfolio import forward_evaluation

    _activate_start()
    forward_evaluation.evaluate("autonomous", "2026-08-11")
    tree = forward_evaluation._output_root()
    before = {path.relative_to(tree): path.read_bytes() for path in tree.rglob("*.json")}
    monkeypatch.setattr(
        forward_evaluation, "evaluate",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("API must not compute")),
    )

    response = web.api_forward_evaluation("autonomous", None)
    payload = json.loads(response.body)
    assert response.status_code == 200
    assert payload["status"] == "available"
    assert payload["snapshot"]["book"] == "autonomous"
    assert {path.relative_to(tree): path.read_bytes() for path in tree.rglob("*.json")} == before
    assert web.api_forward_evaluation("../../escape", None).status_code == 404


def test_partial_inputs_taint_every_dependent_metric(isolated_root: Path) -> None:
    from portfolio import forward_evaluation, registry

    _activate_start()
    base = registry.data_dir("autonomous")
    (base / "decisions.jsonl").parent.mkdir(parents=True, exist_ok=True)
    (base / "decisions.jsonl").write_text(
        json.dumps({
            "asof": "2026-08-12", "target_status": "executed", "decision_effective": True,
            "effective_holdings": [{"ticker": "AAPL", "action_effective": "add",
                                    "evidence": ["x"]}],
        }) + "\n{broken\n", encoding="utf-8")
    (base / "fills.jsonl").write_text(
        json.dumps({"date": "2026-08-12", "ticker": "AAPL", "side": "buy",
                    "shares": 10, "price": 100}) + "\n" +
        json.dumps({"date": "2026-08-13", "ticker": "AAPL", "side": "sell",
                    "shares": 10, "price": 110}) + "\n{broken\n", encoding="utf-8")
    (base / "nav_history.jsonl").write_text(
        json.dumps({"date": "2026-08-12", "nav": 1000, "cash": 500,
                    "invested": 500, "spy_nav": 1000, "benchmark": "SPY"}) + "\n" +
        json.dumps({"date": "2026-08-13", "nav": 1010, "cash": 510,
                    "invested": 500, "spy_nav": 1005, "benchmark": "SPY"}) +
        "\n{broken\n", encoding="utf-8")

    metrics = forward_evaluation.evaluate("autonomous", "2026-08-13")["metrics"]
    for name in ("decision_count", "effective_decision_count", "entry_evidence_coverage_pct",
                 "marked_session_count", "inception_benchmark_relative_return_pct",
                 "max_drawdown_pct", "fill_count", "traded_value_turnover_pct",
                 "full_exit_hit_rate_pct"):
        assert metrics[name]["status"] != "available", name


def test_duplicate_nav_dates_are_one_partial_session(isolated_root: Path) -> None:
    from portfolio import forward_evaluation, registry

    _activate_start()
    _write_jsonl(registry.data_dir("autonomous") / "nav_history.jsonl", [
        {"date": "2026-08-12", "nav": 1000, "cash": 500, "invested": 500,
         "spy_nav": 1000, "benchmark": "SPY"},
        {"date": "2026-08-12", "nav": 1002, "cash": 502, "invested": 500,
         "spy_nav": 1001, "benchmark": "SPY"},
        {"date": "2026-08-13", "nav": 1010, "cash": 510, "invested": 500,
         "spy_nav": 1005, "benchmark": "SPY"},
    ])
    snapshot = forward_evaluation.evaluate("autonomous", "2026-08-13")
    assert snapshot["sample_counts"]["marked_sessions"] == 2
    assert snapshot["metrics"]["marked_session_count"]["value"] == 2
    assert snapshot["metrics"]["marked_session_count"]["status"] == "partial"
    assert snapshot["metrics"]["benchmark_session_hit_rate_pct"]["sample_n"] == 1
    assert snapshot["inputs"]["nav"]["deduplicated_row_count"] == 1


def test_latest_is_monotonic_and_future_asof_is_no_write(isolated_root: Path) -> None:
    from portfolio import forward_evaluation, registry

    _activate_start()
    _write_jsonl(registry.data_dir("autonomous") / "nav_history.jsonl", [
        {"date": "2026-08-12", "nav": 1000, "cash": 500, "invested": 500},
        {"date": "2026-08-13", "nav": 1010, "cash": 510, "invested": 500},
    ])
    forward_evaluation.evaluate("autonomous", "2026-08-13")
    forward_evaluation.evaluate("autonomous", "2026-08-12")
    assert forward_evaluation.load_snapshot("autonomous")["asof"] == "2026-08-13"
    future = forward_evaluation.evaluate("autonomous", "2026-08-14")
    assert future["status"] == "future_asof"
    assert not (forward_evaluation._book_output_dir("autonomous") / "2026-08-14.json").exists()


def test_stale_latest_weights_fall_back_to_current_account_marks(isolated_root: Path) -> None:
    from portfolio import forward_evaluation, registry

    _activate_start()
    base = registry.data_dir("autonomous")
    _write_jsonl(base / "nav_history.jsonl", [{
        "date": "2026-08-13", "nav": 1000, "cash": 500, "invested": 500,
    }])
    _write_json(base / "latest.json", {
        "as_of": "2026-08-12", "positions": [{"ticker": "AAPL", "weight": 0.8}],
    })
    _write_json(base / "account.json", {
        "cash": 500, "positions": {"AAPL": {"shares": 5, "current_price": 100}},
    })
    metric = forward_evaluation.evaluate("autonomous", "2026-08-13")["metrics"][
        "top_1_weight_pct"
    ]
    assert metric == {"value": 50.0, "sample_n": 1, "status": "available",
                      "missing_reason": None}


def test_malformed_nested_ledgers_are_missing_not_false_zero(isolated_root: Path) -> None:
    from portfolio import forward_evaluation, registry

    _activate_start()
    base = registry.data_dir("autonomous")
    _write_json(base / "positions_ledger.json", {"broken:AAPL": []})
    _write_json(isolated_root / "data" / "portfolio_learning" / "autonomous" /
                "post_sell.json", {
                    "schema": "portfolio.post_sell.v1", "exits": {"not": "a list"},
                })
    snapshot = forward_evaluation.evaluate("autonomous", "2026-08-11")
    assert snapshot["inputs"]["positions"]["status"] == "invalid"
    assert snapshot["inputs"]["post_sell"]["status"] == "invalid"
    assert snapshot["metrics"]["closed_position_count"]["value"] is None
    assert snapshot["metrics"]["post_sell_sale_count"]["value"] is None


def test_empty_latest_positions_cannot_claim_zero_concentration_with_exposure(
    isolated_root: Path,
) -> None:
    from portfolio import forward_evaluation, registry

    _activate_start()
    base = registry.data_dir("autonomous")
    _write_jsonl(base / "nav_history.jsonl", [{
        "date": "2026-08-13", "nav": 1000, "cash": 500, "invested": 500,
    }])
    _write_json(base / "latest.json", {"as_of": "2026-08-13", "positions": []})
    _write_json(base / "account.json", {
        "cash": 500, "positions": {"AAPL": {"shares": 5, "avg_cost": 100}},
    })
    metric = forward_evaluation.evaluate("autonomous", "2026-08-13")["metrics"][
        "top_1_weight_pct"
    ]
    assert metric["value"] is None
    assert metric["status"] == "partial"
    assert metric["missing_reason"] == "some_current_positions_lack_durable_weight_or_mark"


def test_effective_exits_lifecycle_and_failure_status_are_honest(
    isolated_root: Path, monkeypatch,
) -> None:
    from app import scheduler
    from portfolio import forward_evaluation, registry

    _activate_start()
    _write_jsonl(registry.data_dir("autonomous") / "decisions.jsonl", [{
        "asof": "2026-08-12", "target_status": "rejected_quote_gap",
        "decision_effective": False, "exit_decisions": [{"ticker": "AAPL"}],
    }])
    snapshot = forward_evaluation.evaluate("autonomous", "2026-08-12")
    assert snapshot["metrics"]["effective_exit_count"]["value"] == 0
    assert forward_evaluation.status("self_directed")["status"] == "unsupported_book"
    assert forward_evaluation.status("autonomous", "2026-08-10")["status"] == (
        "before_evaluation_start"
    )

    failures: list[dict] = []
    monkeypatch.setattr(forward_evaluation, "evaluate", lambda *_args, **_kwargs: (
        (_ for _ in ()).throw(RuntimeError("evaluation broke"))
    ))
    monkeypatch.setattr(scheduler, "_step_failed_event",
                        lambda *args, **kwargs: failures.append({"args": args, "kwargs": kwargs}))
    result = scheduler._post_mark_forward_evaluation("autonomous", asof="2026-08-13")
    assert result["status"] == "error"
    assert failures[0]["kwargs"]["severity"] == "FREEZE"
    assert forward_evaluation.status("autonomous")["status"] == "stale_after_error"


def test_daily_mark_book_failure_has_visible_step_event() -> None:
    import inspect
    from app import scheduler

    source = inspect.getsource(scheduler._daily_mark_job)
    assert '_step_failed_event("daily_mark", pid, f"mark:{pid}", exc, severity="FREEZE")' in source


@pytest.mark.parametrize(
    ("job_name", "module_name", "runner_name", "book"),
    [
        ("_autonomous_job", "bot.autonomous", "run_autonomous", "autonomous"),
        ("_china_job", "bot.china", "run_china", "china"),
        ("_hk_job", "bot.hk", "run_hk", "hk"),
    ],
)
def test_scheduled_post_mark_evaluation_runs_inside_book_lock(
    monkeypatch, job_name: str, module_name: str, runner_name: str, book: str,
) -> None:
    import importlib
    from app import scheduler
    from portfolio import forward_evaluation

    locked = {"active": False}
    calls: list[tuple[str, str]] = []

    class Lock:
        def __enter__(self):
            locked["active"] = True
            return self

        def __exit__(self, *_args):
            locked["active"] = False

    from control_plane import locks
    monkeypatch.setattr(locks, "acquire_or_log", lambda *args, **kwargs: Lock())
    module = importlib.import_module(module_name)

    def runner():
        assert locked["active"] is True
        return {"asof": "2026-08-12"}

    def evaluate(pid, asof):
        assert locked["active"] is True
        calls.append((pid, asof))
        return {"status": "available"}

    monkeypatch.setattr(module, runner_name, runner)
    monkeypatch.setattr(forward_evaluation, "evaluate", evaluate)
    monkeypatch.setattr(scheduler, "_ledger_start", lambda *args, **kwargs: None)
    monkeypatch.setattr(scheduler, "_ledger_end", lambda *args, **kwargs: None)
    monkeypatch.setattr(scheduler, "_maybe_schedule_brain_retry", lambda *args, **kwargs: None)

    getattr(scheduler, job_name)()
    assert calls == [(book, "2026-08-12")]
    assert locked["active"] is False


def test_status_qualifies_closed_day_marks_without_rewriting_or_recomputing(
    isolated_root: Path, monkeypatch,
) -> None:
    """A recorded holiday valuation is retained but cannot certify a session gate."""
    from datetime import date
    from portfolio import forward_evaluation as fe, market_calendar

    book_dir = fe._portfolio_data_dir("autonomous")
    _seed_legacy(book_dir)
    _activate_start()
    legacy = json.loads((book_dir / "nav_history.jsonl").read_text().splitlines()[0])
    rows = [legacy] + [
        {"date": day, "nav": 1_000_000.0, "cash": 400_000.0,
         "invested": 600_000.0, "spy_nav": 1_000_000.0, "benchmark": "SPY"}
        for day in ("2026-09-04", "2026-09-07", "2026-09-08")
    ]
    _write_jsonl(book_dir / "nav_history.jsonl", rows)
    monkeypatch.setattr(fe, "_utc_today", lambda: "2026-09-08")
    saved = fe.evaluate("autonomous", "2026-09-08")
    assert not market_calendar.is_trading_day(date(2026, 9, 7))
    assert saved["metrics"]["marked_session_count"]["value"] == 3
    # Preserve explicit behavior when the older calendar contract is installed.
    monkeypatch.delattr(market_calendar, "session_date_evidence", raising=False)

    def inventory() -> dict[str, bytes]:
        return {str(p.relative_to(isolated_root)): p.read_bytes()
                for p in isolated_root.rglob("*") if p.is_file()}

    before = inventory()

    def forbidden(*args, **kwargs):
        raise AssertionError("status must not recompute or write evaluation evidence")

    for name in ("evaluate", "_read_inputs", "_read_jsonl"):
        monkeypatch.setattr(fe, name, forbidden)

    for response in (fe.status("autonomous"), fe.status("autonomous", "2026-09-08")):
        assert response["snapshot"] == saved
        q = response["observation_qualification"]
        assert q["reported_mark_count"] == 3
        assert q["count_unit"] == "recorded_nav_date_labels"
        assert q["calendar_session_count"] is None
        assert q["price_qualified_session_count"] is None
        assert q["eligible_for_session_gate"] is False
    by_book = {row["book"]: row for row in fe.status()["books"]}
    assert by_book["autonomous"]["observation_qualification"]["reported_mark_count"] == 3
    assert by_book["china"]["observation_qualification"]["reported_mark_count"] is None
    assert by_book["hk"]["observation_qualification"]["reported_mark_count"] is None
    assert inventory() == before


@pytest.mark.parametrize("value,metric_status,expected", [
    (0, "available", 0),
    (4, "partial", 4),
    (None, "missing", None),
    (False, "available", None),
    (-1, "available", None),
    ("49", "available", None),
    (49, {"available": True}, None),
])
def test_mark_qualification_preserves_real_zero_and_withholds_unusable_counts(
    value, metric_status, expected,
) -> None:
    from copy import deepcopy
    from portfolio import forward_evaluation as fe

    original = {
        "book": "autonomous",
        "snapshot": {
            "schema": fe.SCHEMA, "book": "autonomous", "asof": "2026-10-16",
            "metrics": {"marked_session_count": {"value": value, "status": metric_status}},
        },
    }
    before = deepcopy(original)
    result = fe._qualify_mark_observations(original)
    q = result["observation_qualification"]
    assert q["reported_mark_count"] == expected
    assert q["reported_mark_count_status"] == (
        metric_status if expected is not None else "unavailable")
    assert q["calendar_session_count"] is None
    assert q["price_qualified_session_count"] is None
    assert q["eligible_for_session_gate"] is False
    assert original == before
    assert result["snapshot"] == before["snapshot"]


def test_status_withholds_mark_count_from_wrong_book_snapshot(
    isolated_root: Path,
) -> None:
    from portfolio import forward_evaluation as fe

    _activate_start()
    wrong_book = {
        "schema": fe.SCHEMA, "book": "china", "asof": "2026-10-16",
        "metrics": {"marked_session_count": {"value": 49, "status": "available"}},
    }
    _write_json(fe._book_output_dir("autonomous") / "latest.json", wrong_book)
    result = fe.status("autonomous")
    assert result["snapshot"] == wrong_book
    q = result["observation_qualification"]
    assert q["reported_mark_count"] is None
    assert q["reported_mark_count_missing_reason"] == "stored_snapshot_identity_unverified"
    assert q["eligible_for_session_gate"] is False


# 06A frozen NAV-date basis: saved evidence must not be rebuilt from a later journal.
def _seed_nav_date_basis(root: Path) -> tuple[Path, dict]:
    from portfolio import forward_evaluation as fe

    book_dir = fe._portfolio_data_dir("autonomous")
    _seed_legacy(book_dir)
    _activate_start()
    _seed_forward(root, book_dir)
    return book_dir, fe.evaluate("autonomous", "2026-08-13")


def test_nav_date_basis_is_captured_in_the_actual_saved_snapshot(isolated_root):
    from portfolio import forward_evaluation as fe

    book_dir, saved = _seed_nav_date_basis(isolated_root)
    basis = saved["nav_date_basis"]
    assert basis["status"] == "available"
    assert basis["date_labels"] == ["2026-08-12", "2026-08-13"]
    assert basis["selected_row_count"] == 2
    assert basis["book"] == "autonomous"
    assert basis["evaluation_start"] == "2026-08-11"
    assert basis["asof"] == "2026-08-13"
    assert basis["deployment_sha"] == SHA_A
    assert basis["marker_fingerprint"] == fe._digest(fe.load_start())
    rows = [json.loads(line) for line in (book_dir / "nav_history.jsonl").read_text().splitlines()]
    assert basis["selected_rows_fingerprint"] == fe._digest(rows[1:])
    assert json.loads((fe._book_output_dir("autonomous") / "latest.json").read_text()) == saved
    assert fe.status("autonomous")["observation_qualification"]["date_basis"]["date_labels"] == basis["date_labels"]


def test_nav_date_basis_saved_api_survives_later_journal_changes_without_reading_it(
    isolated_root, monkeypatch,
):
    from portfolio import forward_evaluation as fe
    from app import web

    book_dir, saved = _seed_nav_date_basis(isolated_root)
    from portfolio import market_calendar
    monkeypatch.delattr(market_calendar, "session_date_evidence", raising=False)
    (book_dir / "nav_history.jsonl").unlink()

    def forbidden(*args, **kwargs):
        raise AssertionError("read-only status must serve captured evidence, not reconstruct it")

    for name in ("_read_inputs", "_read_jsonl", "build_snapshot", "evaluate"):
        monkeypatch.setattr(fe, name, forbidden)
    before = {str(p): p.read_bytes() for p in isolated_root.rglob("*") if p.is_file()}
    for _ in range(2):
        response = json.loads(web.api_forward_evaluation(portfolio="autonomous").body)
        assert response["snapshot"] == saved
        q = response["observation_qualification"]
        assert q["date_basis"]["date_labels"] == ["2026-08-12", "2026-08-13"]
        assert q["date_basis"]["selected_rows_fingerprint"] == saved["nav_date_basis"]["selected_rows_fingerprint"]
        assert q["calendar_session_count"] is None
        assert q["price_qualified_session_count"] is None
        assert q["eligible_for_session_gate"] is False
    assert {str(p): p.read_bytes() for p in isolated_root.rglob("*") if p.is_file()} == before


def test_nav_date_basis_legacy_snapshot_is_not_backfilled_from_current_data(isolated_root, monkeypatch):
    from portfolio import forward_evaluation as fe

    _, saved = _seed_nav_date_basis(isolated_root)
    saved.pop("nav_date_basis", None)
    _write_json(fe._book_output_dir("autonomous") / "latest.json", saved)

    def forbidden(*args, **kwargs):
        raise AssertionError("legacy snapshot cannot acquire a reconstructed date basis")

    monkeypatch.setattr(fe, "_read_inputs", forbidden)
    monkeypatch.setattr(fe, "_read_jsonl", forbidden)
    result = fe.status("autonomous")
    assert result["snapshot"] == saved
    q = result["observation_qualification"]
    assert q["reported_mark_count"] == 2
    assert q["date_basis"]["status"] == "unavailable"
    assert q["date_basis"]["missing_reason"] == "not_recorded_with_snapshot"
    assert q["date_basis"]["date_labels"] is None


@pytest.mark.parametrize("field,value", [("date", "2026-08-14"), ("nav", 1_234_567.0)])
def test_nav_date_basis_fingerprint_changes_when_same_count_evidence_changes(
    isolated_root, field, value,
):
    from portfolio import forward_evaluation as fe

    book_dir, _ = _seed_nav_date_basis(isolated_root)
    before = fe.build_snapshot("autonomous", "2026-08-15")
    rows = [json.loads(line) for line in (book_dir / "nav_history.jsonl").read_text().splitlines()]
    rows[-1][field] = value
    _write_jsonl(book_dir / "nav_history.jsonl", rows)
    after = fe.build_snapshot("autonomous", "2026-08-15")
    assert before["metrics"]["marked_session_count"] == after["metrics"]["marked_session_count"]
    assert before["nav_date_basis"]["selected_row_count"] == after["nav_date_basis"]["selected_row_count"] == 2
    assert before["nav_date_basis"]["selected_rows_fingerprint"] != after["nav_date_basis"]["selected_rows_fingerprint"]
    assert before["nav_date_basis"]["fingerprint"] != after["nav_date_basis"]["fingerprint"]


def test_nav_date_basis_retains_real_zero_without_certifying_price_or_calendar(isolated_root):
    from portfolio import forward_evaluation as fe

    book_dir = fe._portfolio_data_dir("autonomous")
    _write_jsonl(book_dir / "nav_history.jsonl", [])
    _activate_start()
    saved = fe.evaluate("autonomous", "2026-08-13")
    assert saved["nav_date_basis"]["status"] == "available"
    assert saved["nav_date_basis"]["date_labels"] == []
    assert saved["nav_date_basis"]["selected_rows_fingerprint"] == fe._digest([])
    q = fe.status("autonomous")["observation_qualification"]
    assert q["reported_mark_count"] == 0
    assert q["date_basis"]["selected_row_count"] == 0
    assert q["eligible_for_session_gate"] is False


@pytest.mark.parametrize("damage", ["invalid_line", "duplicate_date"])
def test_nav_date_basis_carries_partial_source_and_original_deduplication(
    isolated_root, damage,
):
    from portfolio import forward_evaluation as fe

    book_dir, _ = _seed_nav_date_basis(isolated_root)
    path = book_dir / "nav_history.jsonl"
    if damage == "invalid_line":
        with path.open("a") as stream:
            stream.write("malformed-record\n")
    else:
        rows = [json.loads(line) for line in path.read_text().splitlines()]
        rows.append({**rows[-1], "nav": 1_111_111.0})
        _write_jsonl(path, rows)
    saved = fe.evaluate("autonomous", "2026-08-13")
    basis = saved["nav_date_basis"]
    assert basis["status"] == "partial"
    assert basis["missing_reason"] == "partial_nav_artifact"
    assert basis["date_labels"] == ["2026-08-12", "2026-08-13"]
    assert basis["selected_row_count"] == saved["metrics"]["marked_session_count"]["value"] == 2
    assert basis["forward_duplicate_date_rows"] == (1 if damage == "duplicate_date" else 0)
    assert fe.status("autonomous")["observation_qualification"]["date_basis"]["status"] == "partial"


def test_nav_date_basis_limit_withholds_labels_without_changing_original_count(isolated_root, monkeypatch):
    from portfolio import forward_evaluation as fe

    _seed_nav_date_basis(isolated_root)
    monkeypatch.setattr(fe, "_MAX_NAV_DATE_LABELS", 1)
    saved = fe.evaluate("autonomous", "2026-08-13")
    assert saved["sample_counts"]["marked_sessions"] == 2
    assert saved["metrics"]["marked_session_count"]["value"] == 2
    assert saved["nav_date_basis"]["status"] == "unavailable"
    assert saved["nav_date_basis"]["missing_reason"] == "date_label_limit_exceeded"
    assert saved["nav_date_basis"]["date_labels"] is None
    assert fe.status("autonomous")["observation_qualification"]["date_basis"]["status"] == "unavailable"


@pytest.mark.parametrize("field,value", [
    ("schema", "unsupported"),
    ("book", "china"),
    ("evaluation_start", "2026-08-10"),
    ("asof", "2026-08-14"),
    ("deployment_sha", SHA_B),
    ("selected_row_count", True),
    ("date_labels", ["2026-08-12", "2026-08-12"]),
    ("date_labels", ["2026-08-13", "2026-08-12"]),
    ("date_labels", ["2026-08-10", "2026-08-12"]),
    ("date_labels", ["2026-08-12", "2026-08-13T00:00:00Z"]),
    ("marker_fingerprint", "bad"),
    ("selected_rows_fingerprint", "bad"),
    ("forward_duplicate_date_rows", -1),
])
def test_nav_date_basis_rejects_rehashed_but_inconsistent_saved_basis(
    isolated_root, field, value,
):
    from portfolio import forward_evaluation as fe

    _, saved = _seed_nav_date_basis(isolated_root)
    basis = saved["nav_date_basis"]
    basis[field] = value
    # A matching checksum alone must not override book/window/type validation.
    basis["fingerprint"] = fe._digest({k: v for k, v in basis.items() if k != "fingerprint"})
    _write_json(fe._book_output_dir("autonomous") / "latest.json", saved)
    result = fe.status("autonomous")
    assert result["snapshot"] == saved
    q = result["observation_qualification"]
    assert q["reported_mark_count"] == 2
    assert q["date_basis"]["status"] == "unavailable"
    assert q["date_basis"]["date_labels"] is None
    assert q["eligible_for_session_gate"] is False


def test_nav_date_basis_rejects_changed_labels_with_original_checksum(isolated_root):
    from portfolio import forward_evaluation as fe

    _, saved = _seed_nav_date_basis(isolated_root)
    saved["nav_date_basis"]["date_labels"] = ["2026-08-11", "2026-08-13"]
    _write_json(fe._book_output_dir("autonomous") / "latest.json", saved)
    q = fe.status("autonomous")["observation_qualification"]
    assert q["date_basis"]["status"] == "unavailable"
    assert q["date_basis"]["date_labels"] is None


def test_nav_date_basis_fingerprint_failure_preserves_snapshot_and_status(isolated_root):
    from portfolio import forward_evaluation as fe
    from app import web

    _, saved = _seed_nav_date_basis(isolated_root)
    marker = fe.load_start()
    marker["unusable_legacy_note"] = "\ud800"
    # Metadata serialization failure must not change the original metric result.
    calculated = fe.build_snapshot("autonomous", "2026-08-13", start=marker)
    assert calculated["metrics"] == saved["metrics"]
    assert calculated["nav_date_basis"]["status"] == "unavailable"
    assert calculated["nav_date_basis"]["missing_reason"] == "source_fingerprint_unavailable"
    # The loaded marker remains valid JSON but cannot be UTF-8 fingerprinted.
    fe._start_path().write_text(json.dumps(marker, ensure_ascii=True), encoding="utf-8")
    before = {str(p): p.read_bytes() for p in isolated_root.rglob("*") if p.is_file()}
    response = json.loads(web.api_forward_evaluation(portfolio="autonomous").body)
    assert response["snapshot"] == saved
    q = response["observation_qualification"]
    assert q["reported_mark_count"] == 2
    assert q["date_basis"]["status"] == "unavailable"
    assert q["date_basis"]["missing_reason"] == "stored_date_basis_cohort_unverified"
    assert {str(p): p.read_bytes() for p in isolated_root.rglob("*") if p.is_file()} == before


@pytest.fixture()
def calendar_wire(monkeypatch):
    """Controlled wire fixture; composed proof separately uses the real owner method."""
    from datetime import date, timedelta
    from portfolio import market_calendar as us, china_calendar as asia

    state = {"calls": [], "mutate": lambda value: value, "fail": False}

    def read(venue, begin, end):
        state["calls"].append((venue, begin.isoformat(), end.isoformat()))
        if state["fail"]:
            raise RuntimeError("isolated calendar source failure")
        owner = us if venue == "US" else asia
        holidays = (us._HOLIDAYS if venue == "US" else
                    asia._HKEX_HOLIDAYS if venue == "HK" else asia._HOLIDAYS)
        covered = date(2026, 1, 1) <= begin <= end <= date(2026, 12, 31)
        days = ([begin + timedelta(days=i) for i in range((end - begin).days + 1)]
                if covered else [])
        scheduled = [
            day.isoformat() for day in days
            if (owner.is_trading_day(day) if venue == "US"
                else owner.is_trading_day(day, venue=venue))
        ]
        wire = {
            "schema": "mastermind.cash_session_date_evidence.v1",
            "calendar_owner": "portfolio.market_calendar" if venue == "US"
                              else "portfolio.china_calendar",
            "venue": venue, "start": begin.isoformat(), "end": end.isoformat(),
            "coverage_start": "2026-01-01", "coverage_end": "2026-12-31",
            "source_checked_on": "2026-10-18",
            "source_refs": ["https://example.test/isolated-calendar-wire"],
            "scope": "published_static_cash_session_dates",
            "exceptional_closures": "listed_only",
            "price_or_cutoff_qualified": False,
            "rule_version": "monday_friday_excluding_listed_closures.v1",
            "full_day_closures": sorted(day.isoformat() for day in holidays
                                       if day.year == 2026),
            "scheduled_dates": scheduled if covered else None,
            "status": "available" if covered else "unavailable",
            "missing_reason": None if covered else "outside_published_calendar_coverage",
        }
        return state["mutate"](wire)

    monkeypatch.setattr(us, "session_date_evidence",
                        lambda begin, end: read("US", begin, end), raising=False)
    monkeypatch.setattr(asia, "session_date_evidence",
                        lambda begin, end, venue="CN": read(venue, begin, end), raising=False)
    return state


def _seed_calendar_nav(root, monkeypatch, book, dates, asof=None):
    from portfolio import forward_evaluation as fe

    base = fe._portfolio_data_dir(book)
    _seed_legacy(base)
    _activate_start()
    legacy = json.loads((base / "nav_history.jsonl").read_text().splitlines()[0])
    rows = [legacy] + [
        {"date": day, "nav": 1_000_000.0, "cash": 400_000.0, "invested": 600_000.0,
         "spy_nav": 1_000_000.0, "benchmark": "SPY"}
        for day in dates
    ]
    _write_jsonl(base / "nav_history.jsonl", rows)
    end = asof or (max(dates) if dates else "2026-08-13")
    monkeypatch.setattr(fe, "_utc_today", lambda: end)
    return base, fe.evaluate(book, end)


@pytest.mark.parametrize("book,dates,closed", [
    ("autonomous", ["2026-09-04", "2026-09-07", "2026-09-08"], "2026-09-07"),
    ("china", ["2026-09-24", "2026-09-25", "2026-09-28"], "2026-09-25"),
    ("hk", ["2026-09-30", "2026-10-01", "2026-10-02"], "2026-10-01"),
])
def test_calendar_join_qualifies_saved_dates_through_actual_api_without_rewriting(
    isolated_root, monkeypatch, calendar_wire, book, dates, closed,
):
    from portfolio import forward_evaluation as fe
    from app import web

    base, saved = _seed_calendar_nav(isolated_root, monkeypatch, book, dates)
    (base / "nav_history.jsonl").unlink()
    before = {str(p): p.read_bytes() for p in isolated_root.rglob("*") if p.is_file()}

    def forbidden(*args, **kwargs):
        raise AssertionError("calendar join must not read or reconstruct NAV inputs")

    for name in ("_read_inputs", "_read_jsonl", "build_snapshot", "evaluate"):
        monkeypatch.setattr(fe, name, forbidden)
    response = json.loads(web.api_forward_evaluation(portfolio=book).body)
    q = response["observation_qualification"]
    assert response["snapshot"] == saved
    assert q["schema"] == "mastermind.portfolio_forward_evaluation.observation_qualification.v2"
    assert q["source_scope"] == "stored_snapshot_and_current_calendar_evidence"
    assert q["reported_mark_count"] == 3
    assert q["calendar_session_count"] == 2
    assert q["calendar_status"] == "available"
    assert q["calendar_count_unit"] == "selected_nav_dates_on_scheduled_cash_sessions"
    assert q["calendar_basis"]["selected_session_dates"] == [day for day in dates if day != closed]
    assert q["calendar_basis"]["non_session_mark_dates"] == [closed]
    assert q["calendar_basis"]["interpretation"] == "current_published_calendar_on_saved_nav_dates"
    assert q["calendar_basis"]["nav_date_basis_fingerprint"] == saved["nav_date_basis"]["fingerprint"]
    assert "2026-08-11" in q["calendar_basis"]["scheduled_dates_without_forward_mark"]
    assert q["calendar_basis"]["scheduled_session_count"] > 2
    assert q["price_qualified_session_count"] is None
    assert q["price_status"] == "not_checked"
    assert q["eligible_for_session_gate"] is False
    assert len(calendar_wire["calls"]) == 1
    assert {str(p): p.read_bytes() for p in isolated_root.rglob("*") if p.is_file()} == before


def test_calendar_join_missing_owner_is_explicit_and_never_uses_weekday_fallback(
    isolated_root, monkeypatch,
):
    from portfolio import forward_evaluation as fe, market_calendar as us

    _seed_calendar_nav(isolated_root, monkeypatch, "autonomous", ["2026-08-12"])
    monkeypatch.delattr(us, "session_date_evidence", raising=False)
    q = fe.status("autonomous")["observation_qualification"]
    assert q["reported_mark_count"] == 1
    assert q["calendar_session_count"] is None
    assert q["calendar_status"] == "not_checked"
    assert q["calendar_missing_reason"] == "calendar_evidence_contract_unavailable"


def test_calendar_join_legacy_basis_never_calls_current_calendar(
    isolated_root, monkeypatch, calendar_wire,
):
    from portfolio import forward_evaluation as fe

    _, saved = _seed_calendar_nav(isolated_root, monkeypatch, "autonomous", ["2026-08-12"])
    saved.pop("nav_date_basis")
    for name in ("latest.json", "2026-08-12.json"):
        _write_json(fe._book_output_dir("autonomous") / name, saved)
    calendar_wire["fail"] = True
    q = fe.status("autonomous")["observation_qualification"]
    assert q["reported_mark_count"] == 1
    assert q["calendar_session_count"] is None
    assert q["calendar_missing_reason"] == "saved_nav_date_basis_unavailable"
    assert not calendar_wire["calls"]


@pytest.mark.parametrize("dates", [[], ["2026-09-07"]])
def test_calendar_join_preserves_real_zero_for_no_selected_session_dates(
    isolated_root, monkeypatch, calendar_wire, dates,
):
    from portfolio import forward_evaluation as fe

    _seed_calendar_nav(isolated_root, monkeypatch, "autonomous", dates)
    q = fe.status("autonomous")["observation_qualification"]
    assert q["reported_mark_count"] == len(dates)
    assert q["calendar_session_count"] == 0
    assert q["calendar_status"] == "available"
    assert q["calendar_basis"]["non_session_mark_dates"] == dates
    assert q["eligible_for_session_gate"] is False


def test_calendar_join_partial_input_never_becomes_complete_evidence(
    isolated_root, monkeypatch, calendar_wire,
):
    from portfolio import forward_evaluation as fe

    base, _ = _seed_calendar_nav(isolated_root, monkeypatch, "autonomous", ["2026-08-12"])
    with (base / "nav_history.jsonl").open("a") as f:
        f.write("{broken\n")
    saved = fe.evaluate("autonomous", "2026-08-12")
    q = fe.status("autonomous")["observation_qualification"]
    assert saved["metrics"]["marked_session_count"]["status"] == "partial"
    assert q["calendar_session_count"] == 1
    assert q["calendar_status"] == "partial"
    assert q["calendar_missing_reason"] == "partial_nav_date_basis"
    assert q["calendar_basis"]["nav_date_basis_status"] == "partial"
    assert q["eligible_for_session_gate"] is False


def test_calendar_join_withholds_a_window_outside_calendar_coverage(
    isolated_root, monkeypatch, calendar_wire,
):
    from portfolio import forward_evaluation as fe

    _seed_calendar_nav(isolated_root, monkeypatch, "china", ["2027-01-04"])
    q = fe.status("china")["observation_qualification"]
    assert q["reported_mark_count"] == 1
    assert q["calendar_session_count"] is None
    assert q["calendar_status"] == "unavailable"
    assert q["calendar_missing_reason"] == "outside_published_calendar_coverage"


def test_calendar_join_source_failure_cannot_erase_original_snapshot(
    isolated_root, monkeypatch, calendar_wire,
):
    from portfolio import forward_evaluation as fe
    from app import web

    _, saved = _seed_calendar_nav(isolated_root, monkeypatch, "autonomous", ["2026-08-12"])
    calendar_wire["fail"] = True
    response = json.loads(web.api_forward_evaluation(portfolio="autonomous").body)
    assert response["snapshot"] == saved
    q = response["observation_qualification"]
    assert q["reported_mark_count"] == 1
    assert q["calendar_session_count"] is None
    assert q["calendar_status"] == "unavailable"
    assert q["calendar_missing_reason"] == "calendar_source_failed"


@pytest.mark.parametrize("field,value", [
    ("schema", "unknown"),
    ("calendar_owner", "portfolio.china_calendar"),
    ("venue", "HK"),
    ("start", "2026-08-10"),
    ("end", "2026-08-13"),
    ("coverage_start", "2026-08-13"),
    ("scope", "actual_executed_sessions"),
    ("price_or_cutoff_qualified", True),
    ("rule_version", "weekday_guess"),
    ("scheduled_dates", ["2026-08-12"]),
    ("scheduled_dates", ["2026-08-11", "2026-08-11", "2026-08-12"]),
    ("full_day_closures", ["2026-08-12"]),
    ("source_refs", ["https://example.test/fixture"] * 9),
    ("source_refs", ["https://example.test/\ud800"]),
])
def test_calendar_join_rejects_wrong_truncated_or_inconsistent_calendar(
    isolated_root, monkeypatch, calendar_wire, field, value,
):
    from portfolio import forward_evaluation as fe

    _, saved = _seed_calendar_nav(isolated_root, monkeypatch, "autonomous", ["2026-08-12"])
    calendar_wire["mutate"] = lambda wire: {**wire, field: value}
    response = fe.status("autonomous")
    assert response["snapshot"] == saved
    q = response["observation_qualification"]
    assert q["reported_mark_count"] == 1
    assert q["calendar_session_count"] is None
    assert q["calendar_status"] == "unavailable"
    assert q["calendar_missing_reason"] == "calendar_source_invalid"
    assert q["calendar_basis"] is None


def test_calendar_join_content_change_is_versioned_without_mutating_saved_cohort(
    isolated_root, monkeypatch, calendar_wire,
):
    from datetime import date
    from portfolio import forward_evaluation as fe, market_calendar as us

    _, saved = _seed_calendar_nav(isolated_root, monkeypatch, "autonomous",
                                  ["2026-08-12", "2026-08-13"])
    before_files = {str(p): p.read_bytes() for p in isolated_root.rglob("*") if p.is_file()}
    before = fe.status("autonomous")["observation_qualification"]
    monkeypatch.setattr(us, "_HOLIDAYS", us._HOLIDAYS | {date(2026, 8, 12)})
    response = fe.status("autonomous")
    after = response["observation_qualification"]
    assert response["snapshot"] == saved
    assert before["reported_mark_count"] == after["reported_mark_count"] == 2
    assert before["calendar_session_count"] == 2
    assert after["calendar_session_count"] == 1
    assert before["calendar_basis"]["calendar_content_fingerprint"] != after["calendar_basis"]["calendar_content_fingerprint"]
    assert before["calendar_basis"]["fingerprint"] != after["calendar_basis"]["fingerprint"]
    assert before["date_basis"] == after["date_basis"]
    assert {str(p): p.read_bytes() for p in isolated_root.rglob("*") if p.is_file()} == before_files
