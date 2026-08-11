"""Executable-boundary proof for the US Brain's common-stock-only mandate."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture
def stock_only_book(tmp_path, monkeypatch):
    from portfolio import instrument_policy, paper_account, registry

    monkeypatch.setattr(registry, "_ROOT", tmp_path)
    monkeypatch.setattr(instrument_policy, "_ROOT", tmp_path)
    stockdata = tmp_path / "vendor" / "macro" / "site" / "stockdata"
    stockdata.mkdir(parents=True)
    (stockdata / "AAPL.json").write_text(
        json.dumps(
            {
                "ticker": "AAPL",
                "name": "Apple Inc.",
                "sector": "Information Technology",
                "security_type": "common stock",
            }
        ),
        encoding="utf-8",
    )
    (stockdata / "FRT.json").write_text(
        json.dumps(
            {
                "ticker": "FRT",
                "name": "Federal Realty Investment Trust",
                "sector": "Real Estate",
            }
        ),
        encoding="utf-8",
    )
    (stockdata / "IJH.json").write_text(
        json.dumps(
            {"ticker": "IJH", "name": "IJH", "sector": "ETF / macro"}
        ),
        encoding="utf-8",
    )
    (stockdata / "RH.json").write_text(
        json.dumps(
            {
                "ticker": "RH",
                "name": "RH",
                "sector": "Consumer Discretionary",
                "profile": {
                    "exchange": "NYSE",
                    "sic_description": "Retail-Furniture Stores",
                },
            }
        ),
        encoding="utf-8",
    )
    (stockdata / "AGCO.json").write_text(
        json.dumps(
            {
                "ticker": "AGCO",
                "name": "AGCO",
                "sector": "Industrials",
                "profile": {
                    "description": "AGCO Corporation is an agricultural machinery manufacturer."
                },
            }
        ),
        encoding="utf-8",
    )
    (stockdata / "ECHOETF.json").write_text(
        json.dumps(
            {
                "ticker": "ECHOETF",
                "name": "ECHOETF",
                "sector": "Financial Services",
                "profile": {"exchange": "NYSE Arca"},
            }
        ),
        encoding="utf-8",
    )
    weak_sector_companies = {
        "ET": "Energy Transfer LP",
        "GSK": "GSK plc",
        "MELI": "MercadoLibre, Inc.",
        "ENB": "Enbridge Inc.",
        "BBIO": "BridgeBio Pharma, Inc.",
        "FTAI": "FTAI Aviation Ltd.",
        "MKL": "Markel Group Inc.",
        "LPLA": "LPL Financial Holdings Inc.",
    }
    for ticker, name in weak_sector_companies.items():
        (stockdata / f"{ticker}.json").write_text(
            json.dumps(
                {
                    "ticker": ticker,
                    "name": name,
                    # This weak analytical label is observed on real company
                    # snapshots; it is not a security-master classification.
                    "sector": "ETF / macro",
                }
            ),
            encoding="utf-8",
        )
    (stockdata / "MIDCAPX.json").write_text(
        json.dumps(
            {
                "ticker": "MIDCAPX",
                "name": "iShares Core S&P Mid-Cap",
                "sector": "ETF / macro",
            }
        ),
        encoding="utf-8",
    )
    (stockdata / "EXPF.json").write_text(
        json.dumps(
            {
                "ticker": "EXPF",
                "name": "Example Exchange-Traded Fund",
                "sector": "ETF / macro",
            }
        ),
        encoding="utf-8",
    )
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
    return registry.data_dir("autonomous")


def _fills(book_dir: Path) -> list[dict]:
    path = book_dir / "fills.jsonl"
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _migration_snapshot(preserved: list[str], positions: dict) -> dict:
    from portfolio import paper_account

    positions_digest = paper_account.positions_sha256(positions)
    return {
        "schema": "mastermind.target_book.v2",
        "holdings": [
            {"ticker": ticker, "weight": 0.20, "action": "hold"}
            for ticker in preserved
        ],
        "operator_migration": {
            "schema": "autonomous_legacy_etf_migration.v1",
            "paper_only": True,
            "preserved_common_stocks": list(preserved),
            "legacy_etfs": ["USMV"],
            "migration_id": "a" * 64,
            "positions_sha256": positions_digest,
        },
    }


def _preserve_constraint(
    target: dict[str, float], tickers: list[str], positions: dict
) -> dict:
    from portfolio import paper_account

    return {
        "schema": "execution_constraints.v1",
        "mode": "preserve_existing_shares",
        "tickers": list(tickers),
        "target_sha256": paper_account._target_sha256(target),
        "positions_sha256": paper_account.positions_sha256(positions),
    }


@pytest.mark.parametrize("ticker", ["SPY", "USMV", "XLP", "XLV", "IBIT", "ARKK"])
def test_validate_rejects_known_etfs_but_accepts_verified_aapl(
    stock_only_book, ticker
):
    from portfolio import paper_account

    assert paper_account.validate_target_weights(
        {"AAPL": 0.20}, portfolio_id="autonomous"
    ) == {"AAPL": 0.20}
    with pytest.raises(
        paper_account.InvalidTargetWeights,
        match=rf"non_common_stock:{ticker}:",
    ):
        paper_account.validate_target_weights(
            {ticker: 0.20}, portfolio_id="autonomous"
        )


def test_validate_rejects_unknown_symbol_without_positive_stockdata(stock_only_book):
    from portfolio import paper_account

    with pytest.raises(
        paper_account.InvalidTargetWeights,
        match=r"non_common_stock:MYSTERY:missing_canonical_stockdata",
    ):
        paper_account.validate_target_weights(
            {"MYSTERY": 0.20}, portfolio_id="autonomous"
        )


def test_company_investment_trust_name_is_not_misclassified_as_etf(stock_only_book):
    from portfolio import instrument_policy, paper_account

    identity = instrument_policy.classify_us_instrument("FRT")
    assert identity == {
        "ticker": "FRT",
        "kind": "common_stock",
        "status": "trusted_company_stockdata.v1",
        "verified": True,
    }
    assert paper_account.validate_target_weights(
        {"FRT": 0.20}, portfolio_id="autonomous"
    ) == {"FRT": 0.20}


@pytest.mark.parametrize("ticker", ["RH", "AGCO"])
def test_ticker_named_company_with_profile_evidence_remains_executable(
    stock_only_book, ticker
):
    from portfolio import instrument_policy, paper_account

    identity = instrument_policy.classify_us_instrument(ticker)
    assert identity == {
        "ticker": ticker,
        "kind": "common_stock",
        "status": "trusted_company_profile.v1",
        "verified": True,
    }
    assert paper_account.validate_target_weights(
        {ticker: 0.20}, portfolio_id="autonomous"
    ) == {ticker: 0.20}


def test_ticker_echo_without_company_profile_evidence_still_fails_closed(
    stock_only_book,
):
    from portfolio import instrument_policy, paper_account

    identity = instrument_policy.classify_us_instrument("ECHOETF")
    assert identity["kind"] == "unknown"
    assert identity["verified"] is False
    with pytest.raises(
        paper_account.InvalidTargetWeights,
        match="non_common_stock:ECHOETF:",
    ):
        paper_account.validate_target_weights(
            {"ECHOETF": 0.20}, portfolio_id="autonomous"
        )


def test_etf_macro_sector_alone_is_not_identity_or_liquidation_authority(
    stock_only_book,
):
    from portfolio import instrument_policy, paper_account

    identity = instrument_policy.classify_us_instrument("IJH")
    assert identity == {
        "ticker": "IJH",
        "kind": "unknown",
        "status": "weak_etf_taxonomy_not_identity_authority",
        "verified": False,
    }
    with pytest.raises(paper_account.InvalidTargetWeights, match="non_common_stock:IJH"):
        paper_account.validate_target_weights(
            {"IJH": 0.20}, portfolio_id="autonomous"
        )


@pytest.mark.parametrize(
    "ticker",
    ["ET", "GSK", "MELI", "ENB", "BBIO", "FTAI", "MKL", "LPLA"],
)
def test_real_company_with_weak_etf_macro_sector_remains_common_stock(
    stock_only_book, ticker
):
    from portfolio import instrument_policy, paper_account

    identity = instrument_policy.classify_us_instrument(ticker)
    assert identity == {
        "ticker": ticker,
        "kind": "common_stock",
        "status": "trusted_company_stockdata.v1",
        "verified": True,
    }
    assert paper_account.validate_target_weights(
        {ticker: 0.20}, portfolio_id="autonomous"
    ) == {ticker: 0.20}


def test_weak_etf_taxonomy_with_fund_brand_name_is_not_common_stock(stock_only_book):
    from portfolio import instrument_policy, paper_account

    identity = instrument_policy.classify_us_instrument("MIDCAPX")
    assert identity == {
        "ticker": "MIDCAPX",
        "kind": "unknown",
        "status": "weak_etf_taxonomy_not_identity_authority",
        "verified": False,
    }
    with pytest.raises(
        paper_account.InvalidTargetWeights,
        match="non_common_stock:MIDCAPX:weak_etf_taxonomy_not_identity_authority",
    ):
        paper_account.validate_target_weights(
            {"MIDCAPX": 0.20}, portfolio_id="autonomous"
        )


def test_explicit_exchange_traded_identity_label_is_verified_etf(stock_only_book):
    from portfolio import instrument_policy

    identity = instrument_policy.classify_us_instrument("EXPF")
    assert identity == {
        "ticker": "EXPF",
        "kind": "etf",
        "status": "trusted_macro_etf_metadata",
        "verified": True,
    }


def test_normalizer_never_mandatory_exits_held_frt(stock_only_book, monkeypatch):
    from brain import decision_submission

    monkeypatch.setattr(
        decision_submission,
        "_latest_holdings",
        lambda book: {
            "FRT": {
                "ticker": "FRT",
                "weight": 0.20,
                "rationale": "held real-estate company",
                "conviction": "medium",
            }
        },
    )
    submission, audit = decision_submission.normalize(
        "autonomous",
        {
            "holdings": [],
            "exit_decisions": [],
            "summary": "no migration requested",
            "falsifiers": [],
            "evidence_planes": [],
            "source_provenance": [],
            "expected_failure_mode": "none",
            "risk_posture": "normal",
            "cash_rationale": "not relevant",
            "decision_memo": {},
        },
        stock_only=True,
        deterministic_sizing=True,
        decision_asof="2026-08-11",
    )

    assert [row["ticker"] for row in submission["holdings"]] == ["FRT"]
    assert submission["exit_decisions"] == []
    assert audit["mandatory_instrument_migrations"] == []


def test_normalizer_freezes_instead_of_force_selling_weak_sector_held_name(
    stock_only_book, monkeypatch
):
    from brain import decision_submission

    monkeypatch.setattr(
        decision_submission,
        "_latest_holdings",
        lambda book: {
            "IJH": {
                "ticker": "IJH",
                "weight": 0.20,
                "rationale": "held instrument awaiting authoritative identity",
                "conviction": "medium",
            }
        },
    )
    with pytest.raises(
        decision_submission.DecisionBoundaryFreeze,
        match=(
            "held_instrument_identity_unverified:IJH:"
            "weak_etf_taxonomy_not_identity_authority"
        ),
    ):
        decision_submission.normalize(
            "autonomous",
            {
                "holdings": [],
                "exit_decisions": [],
                "summary": "no liquidation authority",
                "falsifiers": [],
                "evidence_planes": [],
                "source_provenance": [],
                "expected_failure_mode": "none",
                "risk_posture": "normal",
                "cash_rationale": "not relevant",
                "decision_memo": {},
            },
            stock_only=True,
            deterministic_sizing=True,
            decision_asof="2026-08-11",
        )


def test_save_rejects_etf_without_replacing_valid_queue(stock_only_book):
    from portfolio import paper_account

    paper_account.save_pending_target(
        {"AAPL": 0.20}, "2026-08-11", portfolio_id="autonomous"
    )
    path = paper_account._pending_target_path("autonomous")
    before = path.read_bytes()

    with pytest.raises(paper_account.InvalidTargetWeights, match="non_common_stock:SPY"):
        paper_account.save_pending_target(
            {"SPY": 0.20}, "2026-08-12", portfolio_id="autonomous"
        )

    assert path.read_bytes() == before
    assert _fills(stock_only_book) == []


def test_preflight_recoverably_quarantines_versioned_etf_target_without_account_mutation(
    stock_only_book,
):
    from portfolio import paper_account

    account_path = stock_only_book / "account.json"
    account_before = account_path.read_bytes()
    payload = {
        "schema_version": paper_account.PENDING_TARGET_SCHEMA_V2,
        "engine_version": paper_account.US_BRAIN_ENGINE_V2,
        "portfolio_id": "autonomous",
        "target": {"USMV": 0.25},
        "asof": "2026-08-11",
        "queued_at": "2026-08-11T23:00:00Z",
    }
    paper_account._pending_target_path("autonomous").write_text(
        json.dumps(payload), encoding="utf-8"
    )

    result = paper_account.preflight_pending_target("autonomous")

    assert result["ok"] is False
    assert result["quarantined"] is True
    assert result["quarantine"]["status"] == "quarantined"
    assert result["quarantine"]["reason"].startswith(
        "invalid_target:non_common_stock:USMV:"
    )
    assert account_path.read_bytes() == account_before
    assert _fills(stock_only_book) == []
    assert not paper_account.pending_target_file_exists("autonomous")
    assert list(stock_only_book.glob("pending_target.quarantine.*.json"))


def test_settle_quarantines_persisted_etf_before_account_or_fill_mutation(
    stock_only_book,
):
    from portfolio import paper_account

    account_path = stock_only_book / "account.json"
    account_before = account_path.read_bytes()
    payload = {
        "schema_version": paper_account.PENDING_TARGET_SCHEMA_V2,
        "engine_version": paper_account.US_BRAIN_ENGINE_V2,
        "portfolio_id": "autonomous",
        "target": {"IBIT": 0.25},
        "asof": "2026-08-11",
        "queued_at": "2026-08-11T23:00:00Z",
    }
    paper_account._pending_target_path("autonomous").write_text(
        json.dumps(payload), encoding="utf-8"
    )

    with pytest.raises(paper_account.PendingTargetQuarantined):
        paper_account.settle_target(
            {"IBIT": 50.0}, "2026-08-12", portfolio_id="autonomous"
        )

    assert account_path.read_bytes() == account_before
    assert _fills(stock_only_book) == []
    assert not paper_account._transaction_path("autonomous").exists()


def test_execute_or_queue_rejects_etf_scratch_target_before_queue_or_account(
    stock_only_book,
):
    from bot import settle
    from portfolio import paper_account

    account_path = stock_only_book / "account.json"
    before = account_path.read_bytes()
    result = settle.execute_or_queue(
        "autonomous",
        {"USMV": 0.20},
        {"USMV": 100.0},
        "2026-08-11",
        market_open=False,
    )

    assert result["skipped"] == "invalid_target_weights"
    assert result["invalid_target_reason"].startswith("non_common_stock:USMV:")
    assert account_path.read_bytes() == before
    assert _fills(stock_only_book) == []
    assert not paper_account.pending_target_file_exists("autonomous")


@pytest.mark.parametrize("ticker", ["XLV", "MYSTERY"])
def test_direct_rebalance_rejects_non_stock_before_account_load(monkeypatch, ticker):
    from portfolio import instrument_policy, paper_account

    monkeypatch.setattr(
        instrument_policy,
        "_ROOT",
        Path("/definitely/missing/instrument-metadata-root"),
    )
    monkeypatch.setattr(
        paper_account,
        "_load_account",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("non-stock target reached account state")
        ),
    )

    with pytest.raises(paper_account.InvalidTargetWeights, match=f"non_common_stock:{ticker}"):
        paper_account.rebalance(
            {ticker: 0.20},
            {ticker: 100.0},
            "2026-08-12",
            portfolio_id="autonomous",
        )


@pytest.mark.parametrize("ticker", ["SPY", "MYSTERY"])
def test_single_fill_buy_rejects_non_stock_before_account_load(monkeypatch, ticker):
    from portfolio import instrument_policy, paper_account

    monkeypatch.setattr(
        instrument_policy,
        "_ROOT",
        Path("/definitely/missing/instrument-metadata-root"),
    )
    monkeypatch.setattr(
        paper_account,
        "_load_account",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("non-stock single-fill buy reached account state")
        ),
    )

    with pytest.raises(paper_account.InvalidTargetWeights, match=f"non_common_stock:{ticker}"):
        paper_account.execute_fill(
            ticker,
            "buy",
            shares=1.0,
            price=100.0,
            asof="2026-08-12",
            portfolio_id="autonomous",
        )


def test_single_fill_sell_can_exit_legacy_etf(stock_only_book):
    from portfolio import paper_account

    paper_account._save_account(
        {
            "inception_date": "2026-08-01",
            "starting_nav": 1_000.0,
            "cash": 800.0,
            "positions": {"USMV": {"shares": 2.0, "avg_cost": 100.0}},
            "spy_shares": None,
            "spy_inception_price": None,
        },
        "autonomous",
    )

    result = paper_account.execute_fill(
        "USMV",
        "sell",
        price=100.0,
        asof="2026-08-12",
        portfolio_id="autonomous",
    )

    assert result["ok"] is True
    assert result["ticker"] == "USMV" and result["side"] == "sell"
    assert paper_account._load_account("autonomous")["positions"] == {}
    assert [(row["ticker"], row["side"]) for row in _fills(stock_only_book)] == [
        ("USMV", "sell")
    ]


def test_legacy_etf_inventory_remains_exitable_when_omitted(stock_only_book):
    from portfolio import paper_account

    paper_account._save_account(
        {
            "inception_date": "2026-08-01",
            "starting_nav": 1_000.0,
            "cash": 700.0,
            "positions": {
                "AAPL": {"shares": 1.0, "avg_cost": 100.0},
                "USMV": {"shares": 2.0, "avg_cost": 100.0},
            },
            "spy_shares": None,
            "spy_inception_price": None,
        },
        "autonomous",
    )

    paper_account.rebalance(
        {"AAPL": 0.10},
        {"AAPL": 100.0, "USMV": 100.0},
        "2026-08-12",
        portfolio_id="autonomous",
    )

    account = paper_account._load_account("autonomous")
    assert set(account["positions"]) == {"AAPL"}
    assert account["positions"]["AAPL"] == {"shares": 1.0, "avg_cost": 100.0}
    assert account["cash"] == pytest.approx(900.0)
    fills = _fills(stock_only_book)
    assert [(row["ticker"], row["side"]) for row in fills] == [("USMV", "sell")]


def test_stock_only_policy_is_scoped_to_autonomous_book(stock_only_book):
    from portfolio import paper_account

    # The ETF book is archived but its historical execution contract remains
    # separately testable/readable; regional books likewise retain their own venue gates.
    assert paper_account.validate_target_weights(
        {"SPY": 0.20}, portfolio_id="etf"
    ) == {"SPY": 0.20}
    assert paper_account.validate_target_weights(
        {"0700.HK": 0.20}, portfolio_id="hk"
    ) == {"0700.HK": 0.20}


def test_queued_operator_migration_preserves_exact_shares_through_two_x_price_drift(
    stock_only_book,
):
    from portfolio import paper_account

    paper_account._save_account(
        {
            "inception_date": "2026-08-01",
            "starting_nav": 1_200.0,
            "cash": 0.0,
            "positions": {
                "AAPL": {"shares": 10.0, "avg_cost": 100.0},
                "USMV": {"shares": 2.0, "avg_cost": 100.0},
            },
            "spy_shares": None,
            "spy_inception_price": None,
        },
        "autonomous",
    )
    target = {"AAPL": 10.0 / 12.0}
    positions = paper_account._load_account("autonomous")["positions"]
    paper_account.save_pending_target(
        target,
        "2026-08-11",
        portfolio_id="autonomous",
        decision_snapshot=_migration_snapshot(["AAPL"], positions),
        execution_constraints=_preserve_constraint(target, ["AAPL"], positions),
    )

    # Cash accrual/withdrawal and market-price drift are outside the held-lot authority digest.
    # Neither may manufacture a resize of the preserved common-stock position.
    drifted = paper_account._load_account("autonomous")
    drifted["cash"] = 50.0
    paper_account._save_account(drifted, "autonomous")

    paper_account.settle_target(
        {"AAPL": 200.0, "USMV": 100.0},
        "2026-08-12",
        portfolio_id="autonomous",
    )

    account = paper_account._load_account("autonomous")
    assert account["positions"] == {
        "AAPL": {"shares": 10.0, "avg_cost": 100.0}
    }
    assert account["cash"] == pytest.approx(250.0)
    assert [(row["ticker"], row["side"], row["shares"]) for row in _fills(stock_only_book)] == [
        ("USMV", "sell", 2.0)
    ]


def test_unauthorized_preserve_constraint_fails_without_replacing_queue(stock_only_book):
    from portfolio import paper_account

    paper_account.save_pending_target(
        {"AAPL": 0.20}, "2026-08-11", portfolio_id="autonomous"
    )
    path = paper_account._pending_target_path("autonomous")
    before = path.read_bytes()
    target = {"AAPL": 0.30}
    with pytest.raises(
        paper_account.InvalidExecutionConstraints,
        match="unauthorized_operator_migration",
    ):
        paper_account.save_pending_target(
            target,
            "2026-08-12",
            portfolio_id="autonomous",
            decision_snapshot={"schema": "ordinary_pm_decision"},
            execution_constraints=_preserve_constraint(target, ["AAPL"], {}),
        )
    assert path.read_bytes() == before
    assert _fills(stock_only_book) == []


def test_constraint_and_operator_snapshot_positions_digest_must_match(stock_only_book):
    from portfolio import paper_account

    target = {"AAPL": 0.20}
    positions = {
        "AAPL": {"shares": 1.0, "avg_cost": 100.0},
        "USMV": {"shares": 2.0, "avg_cost": 100.0},
    }
    snapshot = _migration_snapshot(["AAPL"], positions)
    snapshot["operator_migration"]["positions_sha256"] = "0" * 64
    with pytest.raises(
        paper_account.InvalidExecutionConstraints,
        match="migration_positions_sha256_mismatch",
    ):
        paper_account.save_pending_target(
            target,
            "2026-08-11",
            portfolio_id="autonomous",
            decision_snapshot=snapshot,
            execution_constraints=_preserve_constraint(
                target, ["AAPL"], positions
            ),
        )


def test_require_pending_absent_cas_never_replaces_raced_queue(stock_only_book):
    from portfolio import paper_account

    paper_account.save_pending_target(
        {"AAPL": 0.10}, "2026-08-11", portfolio_id="autonomous"
    )
    path = paper_account._pending_target_path("autonomous")
    raced_queue = path.read_bytes()
    target = {"AAPL": 0.20}
    positions = paper_account._load_account("autonomous")["positions"]

    with pytest.raises(paper_account.PendingTargetCASConflict):
        paper_account.save_pending_target(
            target,
            "2026-08-11",
            portfolio_id="autonomous",
            decision_snapshot=_migration_snapshot(["AAPL"], positions),
            execution_constraints=_preserve_constraint(
                target, ["AAPL"], positions
            ),
            require_pending_absent=True,
        )

    assert path.read_bytes() == raced_queue
    assert _fills(stock_only_book) == []
    assert not paper_account._transaction_path("autonomous").exists()


def test_operator_constraint_cannot_queue_after_held_lot_snapshot_changes(
    stock_only_book,
):
    from portfolio import paper_account

    original_positions = {
        "AAPL": {"shares": 1.0, "avg_cost": 100.0},
        "USMV": {"shares": 2.0, "avg_cost": 100.0},
    }
    state = paper_account._load_account("autonomous")
    state["positions"] = json.loads(json.dumps(original_positions))
    paper_account._save_account(state, "autonomous")
    target = {"AAPL": 0.10}
    snapshot = _migration_snapshot(["AAPL"], original_positions)
    constraint = _preserve_constraint(target, ["AAPL"], original_positions)

    changed = paper_account._load_account("autonomous")
    changed["positions"]["USMV"]["shares"] = 3.0
    paper_account._save_account(changed, "autonomous")
    account_before = (stock_only_book / "account.json").read_bytes()
    with pytest.raises(
        paper_account.InvalidExecutionConstraints,
        match="positions_snapshot_changed_before_queue",
    ):
        paper_account.save_pending_target(
            target,
            "2026-08-11",
            portfolio_id="autonomous",
            decision_snapshot=snapshot,
            execution_constraints=constraint,
            require_pending_absent=True,
        )

    assert (stock_only_book / "account.json").read_bytes() == account_before
    assert not paper_account.pending_target_file_exists("autonomous")
    assert _fills(stock_only_book) == []
    assert not paper_account._transaction_path("autonomous").exists()


@pytest.mark.parametrize("drift", ["added_common_stock", "changed_etf_shares"])
def test_migration_held_lot_drift_freezes_and_retains_exact_queue(
    stock_only_book, drift
):
    from portfolio import paper_account

    paper_account._save_account(
        {
            "inception_date": "2026-08-01",
            "starting_nav": 1_000.0,
            "cash": 700.0,
            "positions": {
                "AAPL": {"shares": 1.0, "avg_cost": 100.0},
                "USMV": {"shares": 2.0, "avg_cost": 100.0},
            },
            "spy_shares": None,
            "spy_inception_price": None,
        },
        "autonomous",
    )
    target = {"AAPL": 0.10}
    queued_positions = paper_account._load_account("autonomous")["positions"]
    paper_account.save_pending_target(
        target,
        "2026-08-11",
        portfolio_id="autonomous",
        decision_snapshot=_migration_snapshot(["AAPL"], queued_positions),
        execution_constraints=_preserve_constraint(
            target, ["AAPL"], queued_positions
        ),
    )
    state = paper_account._load_account("autonomous")
    if drift == "added_common_stock":
        state["positions"]["NVDA"] = {"shares": 1.0, "avg_cost": 50.0}
    else:
        state["positions"]["USMV"]["shares"] = 3.0
    paper_account._save_account(state, "autonomous")

    account_path = stock_only_book / "account.json"
    pending_path = paper_account._pending_target_path("autonomous")
    account_before = account_path.read_bytes()
    pending_before = pending_path.read_bytes()
    with pytest.raises(
        paper_account.InvalidExecutionConstraints,
        match="positions_snapshot_mismatch",
    ):
        paper_account.settle_target(
            {"AAPL": 200.0, "USMV": 100.0, "NVDA": 50.0},
            "2026-08-12",
            portfolio_id="autonomous",
        )

    assert account_path.read_bytes() == account_before
    assert pending_path.read_bytes() == pending_before
    assert _fills(stock_only_book) == []
    assert not paper_account._transaction_path("autonomous").exists()


def test_malformed_persisted_preserve_constraint_is_quarantined(stock_only_book):
    from portfolio import paper_account

    target = {"AAPL": 0.20}
    positions = paper_account._load_account("autonomous")["positions"]
    paper_account.save_pending_target(
        target,
        "2026-08-11",
        portfolio_id="autonomous",
        decision_snapshot=_migration_snapshot(["AAPL"], positions),
        execution_constraints=_preserve_constraint(target, ["AAPL"], positions),
    )
    path = paper_account._pending_target_path("autonomous")
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["execution_constraints"]["target_sha256"] = "0" * 64
    path.write_text(json.dumps(payload), encoding="utf-8")
    account_before = (stock_only_book / "account.json").read_bytes()

    result = paper_account.preflight_pending_target("autonomous")

    assert result["ok"] is False and result["quarantined"] is True
    assert result["quarantine"]["reason"] == (
        "invalid_execution_constraints:constraint_target_sha256_mismatch"
    )
    assert (stock_only_book / "account.json").read_bytes() == account_before
    assert _fills(stock_only_book) == []
    assert list(stock_only_book.glob("pending_target.quarantine.*.json"))


@pytest.mark.parametrize("wal_kind", ["clear_pending_target", "legacy_pending_orders"])
def test_pre_upgrade_etf_buy_wal_freezes_before_account_or_fill_replay(
    stock_only_book, monkeypatch, wal_kind
):
    from portfolio import paper_account

    before = paper_account._load_account("autonomous")
    after = json.loads(json.dumps(before))
    after["cash"] -= 100.0
    after["positions"]["SPY"] = {"shares": 1.0, "avg_cost": 100.0}
    if wal_kind == "clear_pending_target":
        pending = {
            "schema_version": paper_account.PENDING_TARGET_SCHEMA_V2,
            "engine_version": paper_account.US_BRAIN_ENGINE_V2,
            "portfolio_id": "autonomous",
            "target": {"SPY": 0.20},
            "asof": "2026-08-10",
            "queued_at": "2026-08-10T23:00:00Z",
        }
        paper_account._pending_target_path("autonomous").write_text(
            json.dumps(pending), encoding="utf-8"
        )
        followup = paper_account._pending_clear_transition("autonomous")
    else:
        followup = paper_account._pending_orders_transition([], "autonomous")

    account_path = stock_only_book / "account.json"
    account_before = account_path.read_bytes()
    real_recover = paper_account._recover_paper_transaction_unlocked
    monkeypatch.setattr(
        paper_account,
        "_recover_paper_transaction_unlocked",
        lambda portfolio_id=None: (_ for _ in ()).throw(RuntimeError("simulated-old-process-death")),
    )
    with pytest.raises(RuntimeError, match="simulated-old-process-death"):
        paper_account._commit_account_and_fills(
            before,
            after,
            [
                {
                    "date": "2026-08-10",
                    "ticker": "SPY",
                    "side": "buy",
                    "shares": 1.0,
                    "price": 100.0,
                    "value": 100.0,
                }
            ],
            asof="2026-08-10",
            portfolio_id="autonomous",
            followup=followup,
        )
    monkeypatch.setattr(
        paper_account, "_recover_paper_transaction_unlocked", real_recover
    )

    with pytest.raises(paper_account.PaperTransactionConflict, match="violates mandate"):
        paper_account.recover_paper_transaction("autonomous")

    assert account_path.read_bytes() == account_before
    assert _fills(stock_only_book) == []
    assert paper_account._transaction_path("autonomous").exists()
    if wal_kind == "clear_pending_target":
        assert paper_account.pending_target_file_exists("autonomous")


def test_legacy_pending_order_buy_cannot_bypass_stock_only_boundary(stock_only_book):
    from portfolio import paper_account

    pending_path = paper_account._paths("autonomous")["pending"]
    pending_path.write_text(
        json.dumps(
            [
                {
                    "ticker": "USMV",
                    "side": "buy",
                    "shares": 10,
                    "status": "pending",
                }
            ]
        ),
        encoding="utf-8",
    )
    account_path = stock_only_book / "account.json"
    before = account_path.read_bytes()

    with pytest.raises(
        paper_account.InvalidTargetWeights,
        match="non_common_stock:USMV",
    ):
        paper_account.fill_pending(
            {"USMV": 100.0}, "2026-08-12", portfolio_id="autonomous"
        )

    assert account_path.read_bytes() == before
    assert _fills(stock_only_book) == []
    assert pending_path.exists()


def test_legacy_pending_order_sell_keeps_etf_exit_open(stock_only_book):
    from portfolio import paper_account

    paper_account._save_account(
        {
            "inception_date": "2026-08-01",
            "starting_nav": 1_000.0,
            "cash": 800.0,
            "positions": {"USMV": {"shares": 2.0, "avg_cost": 100.0}},
            "spy_shares": None,
            "spy_inception_price": None,
        },
        "autonomous",
    )
    paper_account._save_pending(
        [
            {
                "ticker": "USMV",
                "side": "sell",
                "shares": 2.0,
                "status": "pending",
            }
        ],
        "autonomous",
    )

    fills = paper_account.fill_pending(
        {"USMV": 100.0}, "2026-08-12", portfolio_id="autonomous"
    )

    assert [(row["ticker"], row["side"]) for row in fills] == [("USMV", "sell")]
    assert paper_account._load_account("autonomous")["positions"] == {}
