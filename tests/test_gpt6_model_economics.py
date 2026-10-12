"""Published-price regression tests; never infer included-plan balances."""
import json
from decimal import Decimal
from pathlib import Path

import pytest

from control_plane.provider_model_economics import ModelEconomicsError, load_provider_model_catalog

CATALOG = Path(__file__).parents[1] / "config" / "provider_model_economics.v1.json"
MODELS = ("openai.gpt-6-astra", "openai.gpt-6.1-sol")


@pytest.mark.parametrize("key,context,expected", [
    (MODELS[0], 272000, ("10", "1", "12.50", "50")),
    (MODELS[0], 272001, ("20", "2", "25", "75")),
    (MODELS[1], 272000, ("2", "0.10", "2.50", "10")),
    (MODELS[1], 272001, ("4", "0.20", "5", "15")),
])
def test_exact_context_boundary(key, context, expected):
    card = load_provider_model_catalog(CATALOG).api_rate_card(key, surface="openai_api", context_tokens=context)
    assert (card.input_per_million, card.cached_input_per_million, card.cache_write_per_million, card.output_per_million) == tuple(map(Decimal, expected))


@pytest.mark.parametrize("key", MODELS)
@pytest.mark.parametrize("context", [None, 1050001])
def test_unknown_or_unsupported_context_is_not_cheap(key, context):
    with pytest.raises(ModelEconomicsError):
        load_provider_model_catalog(CATALOG).api_rate_card(key, surface="openai_api", context_tokens=context)


@pytest.mark.parametrize("key", MODELS)
def test_model_limits_and_subscription_measurement_stay_distinct(key):
    c = load_provider_model_catalog(CATALOG)
    assert c.effective_context_window(key) == 1050000
    assert c.model(key).max_output_tokens == 128000
    assert c.subscription_burn_rule(key, surface="chatgpt_work_codex").method == "measured_native_delta"
    with pytest.raises(ModelEconomicsError):
        c.api_rate_card(key, surface="chatgpt_work_codex", context_tokens=100000)


def test_realistic_disjoint_token_example_and_relative_price():
    c = load_provider_model_catalog(CATALOG)
    # 100K prompt = 20K uncached + 80K cached, plus 10K output.
    kwargs = dict(surface="openai_api", context_tokens=100000, input_tokens=20000, cached_input_tokens=80000, output_tokens=10000)
    assert c.estimate_api_cash_usd(MODELS[0], **kwargs) == Decimal("0.78")
    assert c.estimate_api_cash_usd(MODELS[1], **kwargs) == Decimal("0.148")
    # Ratio depends on caching; it is not always exactly five.
    assert c.estimate_api_cash_usd(MODELS[0], **kwargs) / c.estimate_api_cash_usd(MODELS[1], **kwargs) > 5


def test_long_context_applies_to_entire_request_not_only_excess():
    c = load_provider_model_catalog(CATALOG)
    kwargs = dict(surface="openai_api", context_tokens=300000, input_tokens=50000, cached_input_tokens=250000, output_tokens=10000)
    assert c.estimate_api_cash_usd(MODELS[0], **kwargs) == Decimal("2.25")
    assert c.estimate_api_cash_usd(MODELS[1], **kwargs) == Decimal("0.40")


def test_price_provenance_and_no_runtime_activation():
    raw = json.loads(CATALOG.read_text())
    assert raw["production_armed"] is False
    for key in MODELS:
        row = raw["models"][key]
        assert row["provider_model"] == key.removeprefix("openai.")
        for rate in row["api_rates"]:
            source = raw["sources"][rate["source_id"]]
            assert source["verified_at"] == "2026-10-01"
            assert source["url"] == "https://developers.openai.com/api/docs/models/" + row["provider_model"]
        assert not {"remaining", "reset_at", "account_id", "eligible", "worker_id"}.intersection(row)


@pytest.mark.parametrize("key", MODELS)
def test_new_models_use_existing_router_capability_vocabulary(key):
    raw = json.loads(CATALOG.read_text())
    row = raw["models"][key]
    assert {"text_input", "text_output", "image_input", "coding", "tool_calling", "research", "tests"}.issubset(row["model_capabilities"])
    assert not {"text", "vision"}.intersection(row["model_capabilities"])
    assert row["positioning"] in {"frontier", "frontier_operator"}
    assert row["harness_overlays"][0]["source_ids"] == ["openai-codex-models-20261001"]
