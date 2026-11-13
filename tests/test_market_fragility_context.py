"""Read-time fences for the optional canonical Macro gamma observation."""
from copy import deepcopy
from datetime import datetime, timezone
import json

import bot  # noqa: F401 - incumbent vendored Macro library bootstrap
import pytest

from brain.market_fragility_context import project_market_fragility

NOW = datetime(2026, 11, 13, 14, tzinfo=timezone.utc)


def payload():
    return {
        "schema": "market_fragility/v1", "scope": "gamma_structure_observation",
        "state": "amplifying", "data_status": "ready",
        "source": {"id": "cboe/gex_SPX", "instrument": "SPX", "position_basis": "assumption",
                   "actual_dealer_inventory_observed": False},
        "clocks": {"computed_at": "2026-11-13T13:00:00Z", "source_session": "2026-11-12",
                   "source_observed_at": None, "source_available_at": None, "age_sessions": 0},
        "current": {"usable": True, "reported_gamma_regime": "short", "reported_net_gex_bn": -2.0,
                    "net_gex_unit": "USD_bn_per_1pct_underlying_move", "gamma_flip": None},
        "history": {"source": "cboe/gex_SPX", "window_sessions": 20, "observed_sessions": 18,
                    "unknown_sessions": 2, "short_sessions": 13, "long_sessions": 5,
                    "coverage_fraction": 0.9, "short_share_observed": 13 / 18,
                    "window_end": "2026-11-12", "sign_changes": 6, "adjacent_pairs_observed": 16,
                    "terminal_regime": "short", "terminal_run_sessions": 2,
                    "terminal_run_left_censored": False, "counts_are_independent_trials": False},
        "quality": {"point_in_time_qualified": False, "predictive_validation": "not_established", "reasons": []},
        "authority": {"display_only": True, "directional_signal": False, "ranking": False,
                      "position_sizing": False, "risk_override": False, "trade_execution": False},
    }


def test_fresh_source_is_compact_descriptive_and_not_mutated():
    data = payload()
    original = deepcopy(data)
    result = project_market_fragility(data, now=NOW)
    assert result["state"] == "amplifying" and result["status"] == "current"
    assert result["source_age_sessions_at_read"] == 0
    assert result["authority"]["position_sizing"] is False
    assert result["source_available_at"] is None
    assert result["history"]["counts_are_independent_trials"] is False
    assert data == original
    assert len(json.dumps(result, allow_nan=False).encode()) < 3000


def test_read_time_rechecks_age_instead_of_trusting_saved_age_zero():
    data = payload()
    result = project_market_fragility(data, now=datetime(2026, 11, 16, 14, tzinfo=timezone.utc))
    assert result["status"] == "stale" and result["state"] == "unknown"
    assert result["source_age_sessions_at_read"] == 1
    assert result["reported_gamma_regime"] == "short"
    assert "source_stale_at_read" in result["reasons"]


@pytest.mark.parametrize("value", [None, [], "short", {"schema": "new_schema"}])
def test_absent_and_unknown_schema_fail_closed(value):
    out = project_market_fragility(value, now=NOW)
    assert out["state"] == "unknown"
    assert out["authority"]["trade_execution"] is False


@pytest.mark.parametrize("key", ["source", "clocks", "current", "quality", "history", "authority"])
def test_malformed_nested_sections_fail_closed(key):
    data = payload()
    data[key] = []
    assert project_market_fragility(data, now=NOW)["reason"] == "invalid_contract"


@pytest.mark.parametrize("key", ["position_sizing", "risk_override", "trade_execution", "ranking", "directional_signal"])
def test_new_authority_is_not_silently_accepted(key):
    data = payload()
    data["authority"][key] = True
    out = project_market_fragility(data, now=NOW)
    assert out["reason"] == "unexpected_authority" and out["state"] == "unknown"


@pytest.mark.parametrize("field,value", [("instrument", "SPY"), ("id", "other/gex"),
                                         ("position_basis", "observed"), ("actual_dealer_inventory_observed", True)])
def test_source_basis_cannot_be_upgraded(field, value):
    data = payload()
    data["source"][field] = value
    assert project_market_fragility(data, now=NOW)["reason"] == "unsupported_source_basis"


def test_predictive_promotion_requires_another_contract_not_a_boolean_flip():
    data = payload()
    data["quality"]["point_in_time_qualified"] = True
    assert project_market_fragility(data, now=NOW)["reason"] == "unsupported_validation_claim"


def test_mixed_spy_history_is_refused():
    data = payload()
    data["history"]["source"] = "cboe/index_gex_history_SPY"
    assert project_market_fragility(data, now=NOW)["reason"] == "mixed_history_source"


@pytest.mark.parametrize("stamp", [None, "bad", "2026-11-13T13:00:00", "2026-11-14T13:00:00Z"])
def test_invalid_computation_clock_does_not_create_freshness(stamp):
    data = payload()
    data["clocks"]["computed_at"] = stamp
    assert project_market_fragility(data, now=NOW)["reason"] == "invalid_computation_clock"


def test_future_source_date_is_not_current():
    data = payload()
    data["clocks"]["source_session"] = "2026-11-16"
    out = project_market_fragility(data, now=NOW)
    assert out["state"] == "unknown" and out["status"] == "unavailable"


def test_future_availability_is_refused():
    data = payload()
    data["clocks"]["source_available_at"] = "2026-11-14T13:00:00Z"
    assert project_market_fragility(data, now=NOW)["reason"] == "invalid_source_clock"


def test_mismatched_state_and_sign_cannot_reach_agent():
    data = payload()
    data["current"]["reported_gamma_regime"] = "long"
    assert project_market_fragility(data, now=NOW)["reason"] == "inconsistent_state"


def test_bad_quality_is_not_silently_cleared():
    data = payload()
    data["quality"]["reasons"] = ["source_stale"]
    assert project_market_fragility(data, now=NOW)["reason"] == "inconsistent_quality"


def test_context_reaged_independently_and_no_raw_clock_claim():
    data = payload()
    data["context"] = {
        "vvix": {"value": 96.6, "source_session": "2026-11-10", "status": "reported"},
        "macro_liquidity": {"value": "contracting", "source_session": "2026-11-12", "status": "reported"},
    }
    out = project_market_fragility(data, now=NOW)
    assert out["state"] == "amplifying"
    assert out["context"]["vvix"]["status"] == "stale"
    assert out["context"]["vvix"]["age_sessions_at_read"] == 2
    assert out["context"]["macro_liquidity"]["status"] == "reported"
    assert out["context"]["market_depth_available"] is False


def test_nonfinite_optional_metric_does_not_enter_transport():
    data = payload()
    data["current"]["reported_net_gex_bn"] = float("inf")
    out = project_market_fragility(data, now=NOW)
    assert out["reported_net_gex_bn"] is None
    json.dumps(out, allow_nan=False)


def test_units_cannot_be_silently_relabelled():
    data = payload()
    data["current"]["net_gex_unit"] = "contracts"
    assert project_market_fragility(data, now=NOW)["reason"] == "unsupported_units"


def test_source_session_cannot_postdate_computation():
    data = payload()
    data["clocks"]["computed_at"] = "2026-11-11T21:00:00Z"
    assert project_market_fragility(data, now=NOW)["reason"] == "source_postdates_computation"
