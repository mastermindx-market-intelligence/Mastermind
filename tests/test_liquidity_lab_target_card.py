"""T12: the GLT broad target card V1 -- the outcome ruler frozen before any outcome is read.

Acceptance map:
* C21 (each target uses its actual return basis and its own session/maturity rule):
  ``test_tlt_yield_change_in_basis_points_is_not_a_fund_return`` (T7),
  ``test_fx_quote_or_inversion_is_not_a_return_basis`` (T8),
  ``test_underlying_market_holiday_is_still_a_us_session`` (T9),
  ``test_calendar_helpers_anchor_count_and_refuse_outside_coverage`` (T13),
  ``test_missing_exit_close_keeps_outcome_immature_and_never_shifts`` (T14).
* C22 (BTC and single-name motivating examples stay archived/excluded):
  ``test_btc_baba_and_non_macro_proxy_roles_are_excluded`` (T3).
"""
from __future__ import annotations

import ast
import dataclasses
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path

import pytest

from brain.liquidity_lab import target_card as card_module
from brain.liquidity_lab.contracts import (
    HORIZONS_BDAYS,
    TARGET_BY_ID,
    TARGETS,
    ContractError,
    TargetSpec,
)
from brain.liquidity_lab.target_card import (
    BASIS_RULINGS,
    BROAD_TARGET_CARD_V1 as CARD,
    BROAD_TARGET_CARD_V1_SHA256,
    CARD_VERSION,
    PLANNING_HORIZONS,
    UNDERLYING_HOLIDAY_NOTE,
    V1_FROZEN_AT,
    anchor_session,
    build_broad_target_card,
    is_target_session,
    nth_session_after,
    outcome_is_mature,
    validate_return_basis,
)

EXPECTED_IDS = ("spy", "qqq", "smh", "igv", "iwm", "tlt", "hyg", "lqd", "gld", "slv",
                "dbc", "uso", "cper", "efa", "eem", "fxi", "mchi", "kweb")
NON_US_EQUITY_IDS = ("efa", "eem", "fxi", "mchi", "kweb")
MODULE_PATH = Path(card_module.__file__)


def test_card_entries_are_the_eighteen_macro_proxies_in_registry_order():
    assert CARD.target_ids() == EXPECTED_IDS
    registry_order = [t.target_id for t in TARGETS if t.target_id in EXPECTED_IDS]
    assert tuple(registry_order) == EXPECTED_IDS
    for entry in CARD.entries:
        spec = TARGET_BY_ID[entry.target_id]
        assert (entry.symbol, entry.asset_class, entry.region, entry.benchmark) == (
            spec.symbol, spec.asset_class, spec.region, spec.benchmark)


def test_building_the_card_never_mutates_the_registry():
    before = (tuple(TARGETS), len(TARGETS), [dataclasses.asdict(t) for t in TARGETS],
              dict(TARGET_BY_ID), HORIZONS_BDAYS)
    build_broad_target_card(frozen_at=date(2026, 10, 13))
    with pytest.raises(ContractError, match="frozen at 2026-10-13"):
        build_broad_target_card(frozen_at=date(2026, 10, 14))
    after = (tuple(TARGETS), len(TARGETS), [dataclasses.asdict(t) for t in TARGETS],
             dict(TARGET_BY_ID), HORIZONS_BDAYS)
    assert before == after
    assert len(TARGETS) == 20
    assert HORIZONS_BDAYS == (1, 5, 10, 20, 40, 60, 90, 120)


def test_btc_baba_and_non_macro_proxy_roles_are_excluded():
    ids = set(CARD.target_ids())
    assert {"btc", "baba"}.isdisjoint(ids)
    assert not {t.target_id for t in TARGETS if t.role != "macro_proxy"} & ids
    assert tuple(target_id for target_id, _ in CARD.excluded) == ("btc", "baba")
    for target_id, reason in CARD.excluded:
        assert reason and "C22" in reason
        with pytest.raises(ContractError, match="excluded") as refused:
            CARD.entry(target_id)
        assert reason in str(refused.value)
    with pytest.raises(ContractError, match="not a .* entry"):
        CARD.entry("not_a_target")


def test_horizon_roles_are_planning_only_and_card_is_not_validated():
    assert CARD.horizon_roles["planning_candidates"] == PLANNING_HORIZONS == (5, 20, 60)
    assert set(PLANNING_HORIZONS) <= set(HORIZONS_BDAYS)
    assert CARD.horizon_roles["primary"] is None
    assert CARD.validated is False
    assert CARD.card_version == CARD_VERSION == "glt_broad_target_card.v1"
    assert CARD.frozen_at == date(2026, 10, 13)
    with pytest.raises(ContractError, match="never validated"):
        dataclasses.replace(CARD, validated=True)


def test_card_and_entries_are_immutable():
    with pytest.raises(dataclasses.FrozenInstanceError):
        CARD.validated = True  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        CARD.entries[0].return_basis = "price"  # type: ignore[misc]
    with pytest.raises(TypeError):
        CARD.horizon_roles["primary"] = 20  # type: ignore[index]
    with pytest.raises(TypeError):
        CARD.basis_rulings["crypto"] = "anything"  # type: ignore[index]
    assert isinstance(CARD.entries, tuple) and isinstance(CARD.excluded, tuple)
    assert all(isinstance(pair, tuple) for pair in CARD.excluded)
    assert all(isinstance(entry.allowed_bases, tuple) for entry in CARD.entries)
    assert isinstance(CARD.calendar_coverage, tuple)


def test_frozen_at_is_caller_supplied_and_build_is_deterministic():
    with pytest.raises(TypeError):
        build_broad_target_card()  # type: ignore[call-arg]
    with pytest.raises(ContractError):
        build_broad_target_card(frozen_at=datetime(2026, 10, 13, tzinfo=timezone.utc))
    with pytest.raises(ContractError):
        build_broad_target_card(frozen_at="2026-10-13")  # type: ignore[arg-type]
    first = build_broad_target_card(frozen_at=date(2026, 10, 13))
    second = build_broad_target_card(frozen_at=date(2026, 10, 13))
    assert first == second == CARD
    assert first.to_dict() == second.to_dict()
    encoded = json.dumps(first.to_dict())
    assert json.dumps(json.loads(encoded)) == encoded
    assert first.to_dict()["frozen_at"] == "2026-10-13"
    assert first.to_dict()["validated"] is False
    digest = hashlib.sha256(
        json.dumps(first.to_dict(), sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    assert digest == BROAD_TARGET_CARD_V1_SHA256 == (
        "f53d9296ae1556544a0d55d1a3d742bbc169138c0ae04b5a458ceb6eaf3c5537"
    )
    assert V1_FROZEN_AT == date(2026, 10, 13)
    with pytest.raises(ContractError, match="frozen at 2026-10-13"):
        build_broad_target_card(frozen_at=date(2026, 10, 12))


def test_tlt_yield_change_in_basis_points_is_not_a_fund_return():
    with pytest.raises(ContractError, match="basis points"):
        validate_return_basis("tlt", "yield_change_bp")
    assert validate_return_basis("tlt", "total_return") == "total_return"


@pytest.mark.parametrize("target_id,basis", [
    ("fxi", "fx_inverted_usdhkd"),
    ("mchi", "USDCNH_inverse"),
    ("kweb", "local_currency_return"),
    ("eem", "fx_return"),
])
def test_fx_quote_or_inversion_is_not_a_return_basis(target_id, basis):
    with pytest.raises(ContractError, match="FX"):
        validate_return_basis(target_id, basis)
    assert all(entry.quote_currency == "USD" for entry in CARD.entries)
    assert "local-currency" in CARD.fx_note and "FX" in CARD.fx_note
    assert "does not define" in CARD.fx_note


def test_underlying_market_holiday_is_still_a_us_session():
    from portfolio.china_calendar import is_hkex_holiday

    national_day = date(2026, 10, 1)
    assert is_hkex_holiday(national_day) is True
    assert is_target_session(national_day) is True
    assert is_target_session(date(2026, 11, 26)) is False  # US Thanksgiving
    for target_id in NON_US_EQUITY_IDS:
        assert CARD.entry(target_id).underlying_holiday_note == UNDERLYING_HOLIDAY_NOTE
    for entry in CARD.entries:
        assert entry.session_calendar == "us_equity_sessions"
        if entry.target_id not in NON_US_EQUITY_IDS:
            assert entry.underlying_holiday_note is None


def test_excess_vs_benchmark_only_where_a_benchmark_is_declared():
    for target_id in ("qqq", "efa", "fxi", "kweb"):
        assert validate_return_basis(target_id, "excess_vs_benchmark") == "excess_vs_benchmark"
    for target_id in ("spy", "tlt", "gld"):
        with pytest.raises(ContractError, match="no declared benchmark"):
            validate_return_basis(target_id, "excess_vs_benchmark")
    ids = set(CARD.target_ids())
    for entry in CARD.entries:
        assert entry.benchmark is None or entry.benchmark in ids


def test_every_entry_defaults_to_its_ruled_total_return_basis():
    for entry in CARD.entries:
        assert entry.return_basis == "total_return"
        assert entry.basis_rationale == BASIS_RULINGS[entry.asset_class]
        assert entry.allowed_bases[:2] == ("price", "total_return")
    for basis in ("log_price", ""):
        with pytest.raises(ContractError, match="unknown return basis"):
            validate_return_basis("spy", basis)
    assert "crypto" not in BASIS_RULINGS


def test_unruled_asset_class_fails_closed(monkeypatch):
    real_targets = TARGETS
    extra = TargetSpec("ethx", "ETHX", "crypto", "global", "crypto")
    assert extra.role == "macro_proxy"
    monkeypatch.setattr(card_module, "TARGETS", tuple(TARGETS) + (extra,))
    monkeypatch.setattr(card_module, "TARGET_BY_ID", {**TARGET_BY_ID, "ethx": extra})
    with pytest.raises(ContractError, match="no return-basis ruling"):
        card_module.build_broad_target_card(frozen_at=date(2026, 10, 13))
    assert card_module.TARGETS is not real_targets
    monkeypatch.undo()
    assert card_module.TARGETS is real_targets and len(real_targets) == 20


def test_registry_field_drift_cannot_stay_labelled_v1(monkeypatch):
    real = TARGET_BY_ID["spy"]
    drifted = dataclasses.replace(real, region="global")
    targets = tuple(drifted if t.target_id == "spy" else t for t in TARGETS)
    monkeypatch.setattr(card_module, "TARGETS", targets)
    monkeypatch.setattr(card_module, "TARGET_BY_ID", {**TARGET_BY_ID, "spy": drifted})
    with pytest.raises(ContractError, match="content hash drifted"):
        card_module.build_broad_target_card(frozen_at=date(2026, 10, 13))
    monkeypatch.undo()
    assert card_module.build_broad_target_card(frozen_at=date(2026, 10, 13)) == CARD


def test_calendar_helpers_anchor_count_and_refuse_outside_coverage():
    # 2026-09-04 is a Friday; Monday 2026-09-07 is Labor Day, so the anchor is Tuesday 9/8.
    assert anchor_session(date(2026, 9, 4)) == date(2026, 9, 8)
    # sessions after 9/8: 9/9, 9/10, 9/11, 9/14, 9/15 -> the fifth is 9/15.
    assert nth_session_after(date(2026, 9, 8), 5) == date(2026, 9, 15)
    with pytest.raises(ContractError, match="not a registered"):
        nth_session_after(date(2026, 9, 8), 7)
    with pytest.raises(ContractError, match="not a registered"):
        nth_session_after(date(2026, 9, 8), True)  # type: ignore[arg-type]
    with pytest.raises(ContractError, match="not a declared-calendar session"):
        nth_session_after(date(2026, 9, 7), 5)
    with pytest.raises(ContractError, match="outside declared calendar coverage"):
        is_target_session(date(2028, 1, 3))
    with pytest.raises(ContractError, match="outside declared calendar coverage"):
        nth_session_after(date(2027, 12, 30), 5)
    with pytest.raises(ContractError):
        is_target_session(datetime(2026, 9, 8, tzinfo=timezone.utc))
    with pytest.raises(ContractError):
        anchor_session(datetime(2026, 9, 4, 20, tzinfo=timezone.utc))


def test_missing_exit_close_keeps_outcome_immature_and_never_shifts():
    anchor = date(2026, 9, 8)
    before_exit = {anchor + timedelta(days=offset) for offset in range(1, 7)}  # 9/9..9/14
    assert outcome_is_mature(anchor=anchor, horizon_bdays=5,
                             available_close_dates=before_exit) is False
    assert outcome_is_mature(anchor=anchor, horizon_bdays=5,
                             available_close_dates=before_exit | {date(2026, 9, 15)}) is True
    later_only = before_exit | {date(2026, 9, 16), date(2026, 9, 17)}
    assert outcome_is_mature(anchor=anchor, horizon_bdays=5,
                             available_close_dates=later_only) is False
    with pytest.raises(ContractError):
        outcome_is_mature(anchor=anchor, horizon_bdays=5,
                          available_close_dates=[datetime(2026, 9, 15, tzinfo=timezone.utc)])


def test_card_module_reads_no_prices_and_no_clock():
    source = MODULE_PATH.read_text()
    allowed = {"__future__", "dataclasses", "datetime", "types", "typing", "collections.abc",
               "brain.liquidity_lab.contracts"}
    for node in ast.parse(source).body:
        if isinstance(node, ast.Import):
            assert {alias.name for alias in node.names} <= allowed
        elif isinstance(node, ast.ImportFrom):
            assert node.module in allowed
    for forbidden in ("pandas", "numpy", "yfinance", "requests", "now(", "today("):
        assert forbidden not in source


def test_estimator_horizons_are_the_untouched_contracts_constant():
    from brain.liquidity_lab import contracts, estimator

    assert estimator.HORIZONS_BDAYS is contracts.HORIZONS_BDAYS is HORIZONS_BDAYS
    assert card_module.HORIZONS_BDAYS is contracts.HORIZONS_BDAYS
