"""Executable-boundary proof for the CN/HK single-name-equity mandate."""

from __future__ import annotations

import asyncio
import json
from copy import deepcopy

import pytest


EQUITIES = {"china": "600519.SS", "hk": "0700.HK"}
ETFS = {"china": "510300.SS", "hk": "2800.HK"}


def _heatmaps() -> dict[str, dict]:
    return {
        "marketdata/china_heatmap.json": {
            "schema": "macro.market_heatmap.v1",
            "map_type": "stocks",
            "market": "china",
            "stockdata_dir": "chinastockdata",
            "n_tiles": 5,
            "tiles": [
                {"t": "600519.SS", "name": "Kweichow Moutai Co., Ltd.", "name_zh": "贵州茅台"},
                {"t": "002020.SZ", "name": "Zhejiang Jingxin Pharmaceutical Co., Ltd.", "name_zh": "京新药业"},
                {"t": "510300.SS", "name": "Huatai-PineBridge CSI 300 ETF", "name_zh": "沪深300ETF"},
                {"t": "159919.SZ", "name": "Harvest CSI 300 ETF", "name_zh": "沪深300ETF"},
                {"t": "000300.SS", "name": "CSI 300 Index", "name_zh": "沪深300指数"},
            ],
        },
        "marketdata/hk_heatmap.json": {
            "schema": "macro.market_heatmap.v1",
            "map_type": "stocks",
            "market": "hk",
            "stockdata_dir": "hkstockdata",
            "n_tiles": 3,
            "tiles": [
                {"t": "0700.HK", "name": "Tencent Holdings Limited", "name_zh": "腾讯控股"},
                {"t": "2800.HK", "name": "Tracker Fund of Hong Kong ETF", "name_zh": "盈富基金"},
                {"t": "3033.HK", "name": "CSOP Hang Seng TECH Index ETF", "name_zh": "南方恒生科技"},
            ],
        },
    }


@pytest.fixture
def trusted_heatmaps(tmp_path, monkeypatch):
    """Keep regional identity tests independent of the vendored/live Macro tree."""
    from brain import china_intake
    from portfolio import instrument_policy, registry

    payloads = _heatmaps()

    def fake_read(relative: str):
        payload = payloads.get(relative)
        return deepcopy(payload) if payload is not None else None

    monkeypatch.setattr(registry, "_ROOT", tmp_path)
    monkeypatch.setattr(instrument_policy, "_ROOT", tmp_path)
    monkeypatch.setattr(instrument_policy, "_read_macro_json", fake_read)
    # The identity layer may deliberately reuse the regional intake reader.  Patch
    # both trusted read surfaces so the test cannot fall through to workstation data.
    monkeypatch.setattr(china_intake, "_read", fake_read)
    china_intake.clear_name_cache()
    yield payloads
    china_intake.clear_name_cache()


@pytest.fixture
def regional_accounts(tmp_path, monkeypatch):
    from portfolio import instrument_policy, paper_account, registry

    monkeypatch.setattr(registry, "_ROOT", tmp_path)

    def classify(book: str, ticker: str) -> dict:
        ticker = str(ticker).upper().strip()
        if ticker == EQUITIES.get(book):
            return {
                "ticker": ticker,
                "kind": "common_stock",
                "status": f"trusted_{book}_stock_heatmap.v1",
                "verified": True,
                "market": book,
            }
        if ticker == ETFS.get(book):
            return {
                "ticker": ticker,
                "kind": "etf",
                "status": "trusted_regional_etf_metadata",
                "verified": True,
            }
        return {
            "ticker": ticker,
            "kind": "unknown",
            "status": "not_in_trusted_stock_heatmap",
            "verified": False,
        }

    monkeypatch.setattr(instrument_policy, "classify_instrument", classify)
    for book in ("china", "hk"):
        paper_account._save_account(
            {
                "inception_date": "2026-08-01",
                "starting_nav": 1_000.0,
                "cash": 1_000.0,
                "positions": {},
                "spy_shares": None,
                "spy_inception_price": None,
            },
            book,
        )
    return tmp_path


@pytest.mark.parametrize("book", ["autonomous", "china", "hk"])
def test_active_ai_books_declare_single_name_equity_policy(book):
    from portfolio import registry

    assert registry.get(book)["asset_policy"] == "single_name_equity_only"
    assert registry.asset_policy(book) == "single_name_equity_only"


@pytest.mark.parametrize(
    ("book", "ticker"),
    [("china", "600519.SS"), ("china", "002020.SZ"), ("hk", "0700.HK")],
)
def test_trusted_stock_heatmap_positively_authenticates_regional_equity(
    trusted_heatmaps, book, ticker
):
    from portfolio import instrument_policy

    identity = instrument_policy.classify_instrument(book, ticker)
    assert identity["kind"] == "common_stock"
    assert identity["verified"] is True
    assert "heatmap" in identity["status"]
    assert instrument_policy.executable_equity_error(book, ticker) is None


@pytest.mark.parametrize(
    ("book", "ticker"),
    [
        ("china", "510300.SS"),
        ("china", "159919.SZ"),
        ("china", "000300.SS"),
        ("china", "600000.SS"),
        ("hk", "2800.HK"),
        ("hk", "3033.HK"),
        ("hk", "^HSI"),
        ("hk", "9999.HK"),
    ],
)
def test_regional_etfs_indexes_and_unknowns_never_authenticate(
    trusted_heatmaps, book, ticker
):
    from portfolio import instrument_policy

    identity = instrument_policy.classify_instrument(book, ticker)
    assert not (
        identity.get("kind") == "common_stock" and identity.get("verified") is True
    )
    assert instrument_policy.executable_equity_error(book, ticker).startswith(
        f"non_single_name_equity:{ticker}:"
    )


def test_reviewed_regional_benchmark_is_authorized_for_compliance_exit(
    trusted_heatmaps,
):
    from portfolio import instrument_policy

    identity = instrument_policy.classify_instrument("hk", "^HSI")

    assert identity["kind"] == "index"
    assert identity["verified"] is True
    assert instrument_policy.liquidation_authorized(identity) is True


@pytest.mark.parametrize(
    ("book", "relative", "field", "bad_value"),
    [
        ("china", "marketdata/china_heatmap.json", "map_type", "funds"),
        ("china", "marketdata/china_heatmap.json", "stockdata_dir", "stockdata"),
        ("hk", "marketdata/hk_heatmap.json", "market", "china"),
        ("hk", "marketdata/hk_heatmap.json", "n_tiles", 999),
    ],
)
def test_malformed_or_wrong_heatmap_contract_cannot_grant_execution_authority(
    trusted_heatmaps, monkeypatch, book, relative, field, bad_value
):
    from portfolio import instrument_policy

    broken = deepcopy(trusted_heatmaps[relative])
    broken[field] = bad_value
    monkeypatch.setattr(
        instrument_policy,
        "_read_macro_json",
        lambda rel: deepcopy(broken) if rel == relative else None,
    )

    identity = instrument_policy.classify_instrument(book, EQUITIES[book])
    assert identity.get("verified") is not True
    assert instrument_policy.executable_equity_error(book, EQUITIES[book]) is not None


def _proposal(ticker: str | None = None) -> dict:
    holdings = []
    if ticker:
        holdings = [
            {
                "ticker": ticker,
                "action": "add",
                "rationale": "single-name thesis",
                "conviction": "medium",
            }
        ]
    return {
        "holdings": holdings,
        "exit_decisions": [],
        "summary": "regional decision",
        "falsifiers": [],
        "evidence_planes": [],
        "source_provenance": [],
        "expected_failure_mode": "thesis fails",
        "risk_posture": "normal",
        "cash_rationale": "dry powder",
        "decision_memo": {},
    }


@pytest.mark.parametrize("book", ["china", "hk"])
def test_normalizer_cannot_opt_out_of_registry_asset_mandate(
    regional_accounts, monkeypatch, book
):
    from brain import decision_submission

    monkeypatch.setattr(decision_submission, "_latest_holdings", lambda _: {})
    submission, audit = decision_submission.normalize(
        book,
        _proposal(ETFS[book]),
        stock_only=False,
        deterministic_sizing=True,
        decision_asof="2026-08-11",
    )

    assert submission["holdings"] == []
    assert [row["ticker"] for row in audit["rejected"]] == [ETFS[book]]


@pytest.mark.parametrize(
    ("book", "wrong_market_ticker"),
    [("china", "0700.HK"), ("hk", "600519.SS")],
)
def test_normalizer_enforces_exact_market_without_optional_venue_callback(
    trusted_heatmaps, monkeypatch, book, wrong_market_ticker
):
    from brain import decision_submission

    monkeypatch.setattr(decision_submission, "_latest_holdings", lambda _: {})

    submission, audit = decision_submission.normalize(
        book,
        _proposal(wrong_market_ticker),
        stock_only=False,
        deterministic_sizing=True,
        decision_asof="2026-08-11",
    )

    assert submission["holdings"] == []
    assert [row["ticker"] for row in audit["rejected"]] == [wrong_market_ticker]


@pytest.mark.parametrize("book", ["china", "hk"])
def test_verified_held_regional_etf_is_a_mandatory_exit_even_if_model_omits_it(
    regional_accounts, monkeypatch, book
):
    from brain import decision_submission

    ticker = ETFS[book]
    monkeypatch.setattr(
        decision_submission,
        "_latest_holdings",
        lambda _: {
            ticker: {
                "ticker": ticker,
                "weight": 0.20,
                "prior_target_weight": 0.20,
                "rationale": "inherited pre-policy holding",
                "conviction": "medium",
            }
        },
    )

    submission, audit = decision_submission.normalize(
        book,
        _proposal(),
        stock_only=False,
        deterministic_sizing=True,
        decision_asof="2026-08-11",
    )

    assert submission["holdings"] == []
    assert [row["ticker"] for row in submission["exit_decisions"]] == [ticker]
    assert submission["exit_decisions"][0]["reason_code"] == "legacy_instrument_migration"
    assert [row["ticker"] for row in audit["mandatory_instrument_migrations"]] == [
        ticker
    ]


@pytest.mark.parametrize("book", ["china", "hk"])
def test_unknown_held_regional_identity_freezes_instead_of_force_selling(
    regional_accounts, monkeypatch, book
):
    from brain import decision_submission

    ticker = "600000.SS" if book == "china" else "9999.HK"
    monkeypatch.setattr(
        decision_submission,
        "_latest_holdings",
        lambda _: {
            ticker: {
                "ticker": ticker,
                "weight": 0.20,
                "rationale": "identity unavailable",
                "conviction": "medium",
            }
        },
    )

    with pytest.raises(
        decision_submission.DecisionBoundaryFreeze,
        match=rf"held_instrument_identity_unverified:{ticker}:",
    ):
        decision_submission.normalize(
            book,
            _proposal(),
            stock_only=False,
            deterministic_sizing=True,
            decision_asof="2026-08-11",
        )


@pytest.mark.parametrize("book", ["china", "hk"])
def test_save_rejects_regional_etf_without_replacing_valid_queue(
    regional_accounts, book
):
    from portfolio import paper_account

    paper_account.save_pending_target(
        {EQUITIES[book]: 0.20}, "2026-08-11", portfolio_id=book
    )
    path = paper_account._pending_target_path(book)
    before = path.read_bytes()

    with pytest.raises(
        paper_account.InvalidTargetWeights,
        match=rf"non_single_name_equity:{ETFS[book]}:",
    ):
        paper_account.save_pending_target(
            {ETFS[book]: 0.20}, "2026-08-12", portfolio_id=book
        )

    assert path.read_bytes() == before


@pytest.mark.parametrize("book", ["china", "hk"])
def test_rebalance_and_single_fill_buy_reject_regional_etf_before_mutation(
    regional_accounts, book
):
    from portfolio import paper_account, registry

    account_path = registry.data_dir(book) / "account.json"
    before = account_path.read_bytes()
    with pytest.raises(paper_account.InvalidTargetWeights):
        paper_account.rebalance(
            {ETFS[book]: 0.20},
            {ETFS[book]: 100.0},
            "2026-08-12",
            portfolio_id=book,
        )
    with pytest.raises(paper_account.InvalidTargetWeights):
        paper_account.execute_fill(
            ETFS[book],
            "buy",
            shares=1.0,
            price=100.0,
            asof="2026-08-12",
            portfolio_id=book,
        )
    assert account_path.read_bytes() == before
    assert not (registry.data_dir(book) / "fills.jsonl").exists()
    assert not paper_account._transaction_path(book).exists()


@pytest.mark.parametrize("book", ["china", "hk"])
def test_deep_transaction_boundary_rejects_and_retains_regional_etf_buy_wal(
    regional_accounts, book
):
    from portfolio import paper_account, registry

    before = paper_account._load_account(book)
    after = deepcopy(before)
    after["cash"] = 900.0
    after["positions"] = {ETFS[book]: {"shares": 1.0, "avg_cost": 100.0}}
    fill = {
        "date": "2026-08-12",
        "ticker": ETFS[book],
        "side": "buy",
        "shares": 1.0,
        "price": 100.0,
        "value": 100.0,
    }
    account_path = registry.data_dir(book) / "account.json"
    account_before = account_path.read_bytes()

    with pytest.raises(
        paper_account.PaperTransactionConflict,
        match=rf"{book} WAL BUY violates mandate: non_single_name_equity:{ETFS[book]}:",
    ):
        paper_account._commit_account_and_fills(
            before,
            after,
            [fill],
            asof="2026-08-12",
            portfolio_id=book,
        )

    assert account_path.read_bytes() == account_before
    assert paper_account._transaction_path(book).exists()


@pytest.mark.parametrize("book", ["china", "hk"])
def test_settle_quarantines_persisted_regional_etf_before_mutation(
    regional_accounts, book
):
    from portfolio import paper_account, registry

    payload = {
        "target": {ETFS[book]: 0.20},
        "asof": "2026-08-11",
        "queued_at": "2026-08-11T23:00:00Z",
    }
    paper_account._pending_target_path(book).write_text(json.dumps(payload), encoding="utf-8")
    account_path = registry.data_dir(book) / "account.json"
    before = account_path.read_bytes()

    with pytest.raises(paper_account.PendingTargetQuarantined):
        paper_account.settle_target(
            {ETFS[book]: 100.0}, "2026-08-12", portfolio_id=book
        )

    assert account_path.read_bytes() == before
    assert not paper_account.pending_target_file_exists(book)
    assert list(registry.data_dir(book).glob("pending_target.quarantine.*.json"))


@pytest.mark.parametrize("book", ["china", "hk"])
def test_direct_sell_remains_available_for_legacy_regional_etf(
    regional_accounts, book
):
    from portfolio import paper_account, registry

    paper_account._save_account(
        {
            "inception_date": "2026-08-01",
            "starting_nav": 1_000.0,
            "cash": 800.0,
            "positions": {ETFS[book]: {"shares": 2.0, "avg_cost": 100.0}},
            "spy_shares": None,
            "spy_inception_price": None,
        },
        book,
    )

    result = paper_account.execute_fill(
        ETFS[book],
        "sell",
        price=100.0,
        asof="2026-08-12",
        portfolio_id=book,
    )

    assert result["ok"] is True
    assert paper_account._load_account(book)["positions"] == {}
    rows = [
        json.loads(line)
        for line in (registry.data_dir(book) / "fills.jsonl").read_text().splitlines()
    ]
    assert [(row["ticker"], row["side"]) for row in rows] == [(ETFS[book], "sell")]


@pytest.mark.parametrize("book", ["china", "hk"])
def test_malformed_persisted_regional_target_is_recoverably_quarantined(
    regional_accounts, book
):
    from portfolio import paper_account, registry

    payload = {
        "target": {EQUITIES[book]: "0.20"},
        "asof": "2026-08-11",
        "queued_at": "2026-08-11T23:00:00Z",
    }
    paper_account._pending_target_path(book).write_text(json.dumps(payload), encoding="utf-8")

    result = paper_account.preflight_pending_target(book)

    assert result["ok"] is False and result["quarantined"] is True
    assert result["quarantine"]["reason"].startswith("invalid_target:non_numeric_weight:")
    assert not paper_account.pending_target_file_exists(book)
    assert list(registry.data_dir(book).glob("pending_target.quarantine.*.json"))


def test_archived_etf_and_self_directed_books_do_not_inherit_ai_stock_policy(
    regional_accounts, monkeypatch
):
    from portfolio import instrument_policy, paper_account

    monkeypatch.setattr(
        instrument_policy,
        "classify_instrument",
        lambda *_: (_ for _ in ()).throw(AssertionError("out-of-scope classifier called")),
    )
    assert paper_account.validate_target_weights(
        {"SPY": 0.20}, portfolio_id="etf"
    ) == {"SPY": 0.20}
    assert paper_account.validate_target_weights(
        {"SPY": 0.20}, portfolio_id="self_directed"
    ) == {"SPY": 0.20}


@pytest.mark.parametrize(
    ("module_name", "book", "equity", "etf", "board_key"),
    [
        ("brain.china_mcp", "china", "600519.SS", "510300.SS", "a_share_buy"),
        ("brain.hk_mcp", "hk", "0700.HK", "2800.HK", "hk_buy"),
    ],
)
def test_regional_research_tools_never_present_etfs_as_eligible_candidates(
    trusted_heatmaps, monkeypatch, module_name, book, equity, etf, board_key
):
    import importlib

    module = importlib.import_module(module_name)
    board_path = (
        "factordata/china_standouts.json"
        if book == "china"
        else "factordata/hk_standouts.json"
    )
    monkeypatch.setattr(
        module.china_intake,
        "_read",
        lambda relative: {
            "buy": [
                {"ticker": equity, "name": "Operating company"},
                {"ticker": etf, "name": "Index ETF"},
            ]
        }
        if relative == board_path
        else {},
    )

    payload = json.loads(
        asyncio.run(module.get_china_standouts.handler({}))["content"][0]["text"]
    )

    assert [row["ticker"] for row in payload[board_key]] == [equity]


@pytest.mark.parametrize(
    ("module_name", "book", "equity", "etf", "off_venue"),
    [
        ("brain.china_mcp", "china", "600519.SS", "510300.SS", "0700.HK"),
        ("brain.hk_mcp", "hk", "0700.HK", "2800.HK", "600519.SS"),
    ],
)
def test_regional_intake_filters_full_funnel_before_requested_limit(
    trusted_heatmaps,
    monkeypatch,
    module_name,
    book,
    equity,
    etf,
    off_venue,
):
    import importlib

    module = importlib.import_module(module_name)
    build_limits: list[int] = []

    def build(limit: int):
        build_limits.append(limit)
        rows = [
            {"ticker": off_venue, "venue": "HK" if book == "china" else "A-share"},
            {"ticker": etf, "venue": "A-share" if book == "china" else "HK"},
            {"ticker": equity, "venue": "A-share" if book == "china" else "HK"},
        ]
        for score, row in zip((0.9, 0.8, 0.7), rows):
            row.update(
                score=score,
                n_sources=1,
                lean=1,
                sources=["test"],
                reasons=["ranked candidate"],
                falsifier="thesis fails",
            )
        return {
            "as_of": "2026-08-11",
            "macro_context": {},
            "n_universe": len(rows),
            "candidates": rows[:limit],
            "note": "test funnel",
        }

    monkeypatch.setattr(module.china_intake, "build", build)
    monkeypatch.setattr(module.china_intake, "display_name", lambda ticker: ticker)

    payload = json.loads(
        asyncio.run(module.get_china_intake.handler({"limit": 1}))["content"][0]["text"]
    )

    assert build_limits == [10_000]
    assert [row["ticker"] for row in payload["candidates"]] == [equity]
    assert payload["n_off_venue_filtered"] == 1
    assert payload["n_ineligible_filtered"] == 1
    assert payload["n_eligible_universe"] == 1


@pytest.mark.parametrize(
    ("module_name", "book", "etf"),
    [
        ("brain.china_mcp", "china", "510300.SS"),
        ("brain.hk_mcp", "hk", "2800.HK"),
    ],
)
def test_priceable_regional_etf_is_still_ineligible(
    trusted_heatmaps, monkeypatch, module_name, book, etf
):
    import importlib

    from portfolio import fx, paper_account

    module = importlib.import_module(module_name)
    monkeypatch.setattr(paper_account, "_current_price", lambda _: 100.0)
    monkeypatch.setattr(fx, "usd_to", lambda value, _: value)
    monkeypatch.setattr(fx, "rate_per_usd", lambda _: 1.0)

    payload = json.loads(
        asyncio.run(module.get_quote.handler({"ticker": etf}))["content"][0]["text"]
    )

    assert payload["quote_available"] is True
    assert payload["eligible"] is False
    assert payload["priceable"] is False


def test_regional_personas_make_etf_prohibition_explicit():
    from bot import china, hk

    for persona in (china._PERSONA, hk._PERSONA):
        assert "ETFs" in persona
        assert "PROHIBITED" in persona
        assert "single-company" in persona
