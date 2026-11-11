"""Reviewed M3.1 token values must not invent entitlement, task fit or wallets."""
import json
from decimal import Decimal

import pytest

from control_plane.provider_model_economics import (
    DEFAULT_CATALOG_PATH, ModelEconomicsError, load_provider_model_catalog,
)

CASES = [
    ("minimax.minimax-m3.1-flash", "minimax", "MiniMax-M3.1-Flash", "minimax_api", "minimax_token_plan"),
    ("opencode.minimax-m3.1-flash", "opencode", "minimax-m3.1-flash", "opencode_go", "opencode_go"),
]


@pytest.mark.parametrize("key,provider,wire,surface,burn_surface", CASES)
def test_exact_provider_identity_and_reviewed_flat_rates(key, provider, wire, surface, burn_surface):
    catalog = load_provider_model_catalog()
    model = catalog.model(key)
    assert (model.provider, model.provider_model) == (provider, wire)
    card = catalog.api_rate_card(key, surface=surface, context_tokens=100_000)
    assert card.input_per_million == Decimal("0.15")
    assert card.output_per_million == Decimal("0.60")
    assert card.cached_input_per_million == Decimal("0.015")
    assert card.cache_write_per_million is None
    assert catalog.estimate_api_cash_usd(
        key, surface=surface, input_tokens=1_000, cached_input_tokens=50_000,
        output_tokens=100, context_tokens=100_000,
    ) == Decimal("0.00096")
    # A rate card does not prove a serving context/output limit or task quality.
    assert model.context_window_tokens is None
    assert model.max_output_tokens is None
    assert model.harness_overlays == ()
    assert model.model_capabilities == frozenset({"text_input", "text_output"})


@pytest.mark.parametrize("key,provider,wire,surface,burn_surface", CASES)
def test_no_synthetic_subscription_balance_or_cache_write_price(key, provider, wire, surface, burn_surface):
    catalog = load_provider_model_catalog()
    burn = catalog.subscription_burn_rule(key, surface=burn_surface)
    assert burn.method == "measured_native_delta"
    assert burn.native_unit == "provider_quota_units"
    assert burn.pool_family is None
    with pytest.raises(ModelEconomicsError, match="no reviewed pool family"):
        catalog.subscription_pool_family(key, surface=burn_surface)
    with pytest.raises(ModelEconomicsError, match="no write price"):
        catalog.estimate_api_cash_usd(
            key, surface=surface, context_tokens=1000,
            input_tokens=0, cache_write_tokens=1,
        )


def test_surfaces_and_preview_alias_are_not_silent_substitutions():
    catalog = load_provider_model_catalog()
    for key, _, _, surface, _ in CASES:
        wrong_surface = "opencode_go" if surface == "minimax_api" else "minimax_api"
        with pytest.raises(ModelEconomicsError, match="no reviewed API rate"):
            catalog.api_rate_card(key, surface=wrong_surface, context_tokens=1000)
    with pytest.raises(ModelEconomicsError, match="unknown model_key"):
        catalog.model("minimax.minimax-m3.1-flash-preview")
    # The historical model retains its original distinct identity for accounting.
    assert catalog.model("minimax.minimax-m3").provider_model == "MiniMax-M3"


def test_reviewed_sources_are_dated_and_production_is_not_armed():
    raw = json.loads(DEFAULT_CATALOG_PATH.read_text())
    assert raw["production_armed"] is False
    assert raw["scope"] == "routing_models_only"
    assert raw["authority"] == {
        "suitability": "model_router",
        "capacity_and_quota": "shared_ai_provider_control",
        "lifecycle_and_claim": "executive_os",
    }
    for key, *_ in CASES:
        row = raw["models"][key]
        assert row["positioning"] == "task_evaluation_required"
        assert all(raw["sources"][source]["verified_at"] == "2026-11-10" for source in row["source_ids"])
        assert row["api_rates"][0]["effective_from"] == "2026-11-10"
        assert "independent model allowance" in row["api_rates"][0]["notes"]
