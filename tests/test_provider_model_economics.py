from decimal import Decimal
from pathlib import Path

import pytest

from control_plane.provider_model_economics import (
    ModelEconomicsError,
    load_provider_model_catalog,
)

CATALOG = Path(__file__).parents[1] / "config" / "provider_model_economics.v1.json"


def test_catalog_loads_reviewed_routing_models_and_stays_inert():
    catalog = load_provider_model_catalog(CATALOG)
    import json
    raw = json.loads(CATALOG.read_text())
    assert raw["production_armed"] is False
    assert raw["authority"] == {
        "suitability": "model_router",
        "capacity_and_quota": "shared_ai_provider_control",
        "lifecycle_and_claim": "executive_os",
    }
    assert len(catalog.models) == 13


def test_model_capability_and_harness_overlay_remain_distinct():
    catalog = load_provider_model_catalog(CATALOG)
    base = catalog.effective_capabilities("xai.grok-4.6")
    cursor = catalog.effective_capabilities("xai.grok-4.6", surface="cursor")
    assert "browser" not in base
    assert "browser" in cursor
    assert catalog.effective_context_window("xai.grok-4.6") == 500_000
    assert catalog.effective_context_window("xai.grok-4.6", surface="cursor") == 256_000


def test_api_cash_estimates_are_exact_decimal_and_context_banded():
    catalog = load_provider_model_catalog(CATALOG)
    assert catalog.estimate_api_cash_usd(
        "openai.gpt-5.6-sol",
        surface="openai_api",
        context_tokens=100_000,
        input_tokens=1_000_000,
        output_tokens=1_000_000,
    ) == Decimal("24")
    assert catalog.estimate_api_cash_usd(
        "openai.gpt-5.6-luna",
        surface="openai_api",
        context_tokens=100_000,
        input_tokens=1_000_000,
        output_tokens=1_000_000,
    ) == Decimal("1.4")
    assert catalog.estimate_api_cash_usd(
        "xai.grok-4.6",
        surface="xai_api",
        context_tokens=200_000,
        input_tokens=1_000_000,
        output_tokens=1_000_000,
    ) == Decimal("16")
    assert catalog.estimate_api_cash_usd(
        "cursor.composer-2.5",
        surface="cursor",
        context_tokens=100_000,
        input_tokens=1_000_000,
        output_tokens=1_000_000,
    ) == Decimal("3")
    assert catalog.estimate_api_cash_usd(
        "minimax.minimax-m3",
        surface="minimax_api",
        context_tokens=600_000,
        input_tokens=1_000_000,
        output_tokens=1_000_000,
    ) == Decimal("3")
    assert catalog.estimate_api_cash_usd(
        "alibaba.qwen3.6-flash",
        surface="alibaba_model_studio",
        context_tokens=300_000,
        input_tokens=1_000_000,
        output_tokens=1_000_000,
    ) == Decimal("5")


def test_unknown_or_unreviewed_cash_rate_fails_closed():
    catalog = load_provider_model_catalog(CATALOG)
    with pytest.raises(ModelEconomicsError, match="no reviewed API rate"):
        catalog.api_rate_card("glm.glm-5.3", surface="glm_api", context_tokens=100_000)
    with pytest.raises(ModelEconomicsError, match="no unique reviewed rate"):
        catalog.api_rate_card("openai.gpt-5.6-sol", surface="openai_api", context_tokens=300_000)


def test_subscription_burn_method_is_declared_without_quota_balances():
    catalog = load_provider_model_catalog(CATALOG)
    assert catalog.subscription_burn_rule("glm.glm-5.3", surface="glm_coding_plan").method == "measured_native_delta"
    assert catalog.subscription_burn_rule("openai.gpt-5.6-sol", surface="chatgpt_work_codex").method == "measured_native_delta"
    assert catalog.subscription_burn_rule("minimax.minimax-m3", surface="minimax_token_plan").method == "measured_native_delta"
    raw = CATALOG.read_text()
    for forbidden in ('"remaining"', '"reset_at"', '"window_type"', '"observed_at"'):
        assert forbidden not in raw
