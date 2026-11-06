"""Source-only fallback economics; no provider, quota, claim or runtime writes."""
import json
from decimal import Decimal
from pathlib import Path

import pytest

from control_plane.provider_model_economics import (
    ModelEconomicsError,
    load_provider_model_catalog,
)

CATALOG = Path(__file__).parents[1] / "config" / "provider_model_economics.v1.json"


def _document():
    return json.loads(CATALOG.read_text())


def _load(tmp_path, doc):
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps(doc))
    return load_provider_model_catalog(path)


@pytest.mark.parametrize("key", [
    "cursor.composer-2.5", "xai.grok-4.6", "xai.grok-4.7",
])
def test_cursor_frontier_and_composer_share_declared_family(key):
    catalog = load_provider_model_catalog(CATALOG)
    assert catalog.subscription_pool_family(key, surface="cursor") == "cursor_models"


@pytest.mark.parametrize("key", [
    "openai.gpt-5.6-luna", "openai.gpt-5.6-terra", "anthropic.claude-sonnet-5.5",
])
def test_cursor_economical_fallbacks_use_other_models_family(key):
    catalog = load_provider_model_catalog(CATALOG)
    assert catalog.subscription_pool_family(key, surface="cursor") == "other_models"
    assert catalog.subscription_burn_rule(key, surface="cursor").method == "token_rate_card"
    assert "shell" in catalog.effective_capabilities(key, surface="cursor")


@pytest.mark.parametrize("key,short,long", [
    ("openai.gpt-5.6-luna", "1.4", "2.2"),
    ("openai.gpt-5.6-terra", "14", "22"),
])
def test_cursor_luna_terra_regular_rates_include_exact_long_context_boundary(key, short, long):
    catalog = load_provider_model_catalog(CATALOG)
    def quote(context):
        return catalog.estimate_api_cash_usd(
            key, surface="cursor", context_tokens=context,
            input_tokens=1_000_000, output_tokens=1_000_000,
        )
    assert quote(272_000) == Decimal(short)
    assert quote(272_001) == Decimal(long)
    assert quote(1_000_000) == Decimal(long)
    with pytest.raises(ModelEconomicsError):
        quote(1_000_001)
    with pytest.raises(ModelEconomicsError, match="context_tokens is required"):
        catalog.api_rate_card(key, surface="cursor", context_tokens=None)
    # Fast variants are distinct serving choices, never silently regular-priced.
    with pytest.raises(ModelEconomicsError, match="unknown model_key"):
        catalog.model(key + "-fast")


@pytest.mark.parametrize("key,surface,expected", [
    ("anthropic.claude-sonnet-5.5", "anthropic_api", "14.7"),
    ("anthropic.claude-sonnet-5.5", "cursor", "14.7"),
    ("anthropic.claude-haiku-4.5", "anthropic_api", "7.35"),
])
def test_claude_fallback_rates_preserve_disjoint_cache_categories(key, surface, expected):
    catalog = load_provider_model_catalog(CATALOG)
    assert catalog.estimate_api_cash_usd(
        key, surface=surface, context_tokens=100_000,
        input_tokens=1_000_000, cached_input_tokens=1_000_000,
        cache_write_tokens=1_000_000, output_tokens=1_000_000,
    ) == Decimal(expected)


def test_haiku_has_no_invented_cursor_entitlement_or_capacity():
    catalog = load_provider_model_catalog(CATALOG)
    key = "anthropic.claude-haiku-4.5"
    assert catalog.model(key).provider_model == "claude-haiku-4-5-20251001"
    assert catalog.effective_context_window(key) == 200_000
    with pytest.raises(ModelEconomicsError, match="no unique subscription burn"):
        catalog.subscription_pool_family(key, surface="cursor")
    with pytest.raises(ModelEconomicsError, match="no reviewed API rate"):
        catalog.api_rate_card(key, surface="cursor", context_tokens=100_000)
    assert catalog.subscription_burn_rule(key, surface="claude_code_subscription").method == "measured_native_delta"
    with pytest.raises(ModelEconomicsError, match="no reviewed pool family"):
        catalog.subscription_pool_family(key, surface="claude_code_subscription")


def test_legacy_catalog_remains_readable_but_cannot_infer_pool_family(tmp_path):
    doc = _document()
    for model in doc["models"].values():
        for burn in model["subscription_burn"]:
            burn.pop("pool_family", None)
    catalog = _load(tmp_path, doc)
    assert catalog.subscription_burn_rule("xai.grok-4.7", surface="cursor").pool_family is None
    with pytest.raises(ModelEconomicsError, match="no reviewed pool family"):
        catalog.subscription_pool_family("xai.grok-4.7", surface="cursor")


@pytest.mark.parametrize("value", [None, False, 1, [], {}, "", "unknown", "../other_models", "x" * 129])
def test_explicit_invalid_pool_family_is_rejected(tmp_path, value):
    doc = _document()
    doc["models"]["cursor.composer-2.5"]["subscription_burn"][0]["pool_family"] = value
    with pytest.raises(ModelEconomicsError):
        _load(tmp_path, doc)


@pytest.mark.parametrize("field,value", [
    ("surface", "unreviewed_surface"),
    ("method", "measured_native_delta"),
    ("native_unit", "provider_quota_units"),
])
def test_declared_cursor_pool_requires_compatible_surface_and_burn_unit(tmp_path, field, value):
    doc = _document()
    row = doc["models"]["cursor.composer-2.5"]["subscription_burn"][0]
    row["pool_family"] = "cursor_models"
    row[field] = value
    with pytest.raises(ModelEconomicsError):
        _load(tmp_path, doc)


def test_optional_pool_family_does_not_relax_closed_burn_shape(tmp_path):
    doc = _document()
    row = doc["models"]["cursor.composer-2.5"]["subscription_burn"][0]
    row["pool_family"] = "cursor_models"
    row["remaining"] = 100
    with pytest.raises(ModelEconomicsError, match="wrong shape"):
        _load(tmp_path, doc)


def test_pool_family_is_not_account_identity_or_quota_evidence():
    raw = CATALOG.read_text()
    for forbidden in ('"remaining"', '"reset_at"', '"window_type"', '"observed_at"', '"account_id"'):
        assert forbidden not in raw
    assert _document()["production_armed"] is False
    # Equal family labels do not prove two subscriptions share an account.
    a = load_provider_model_catalog(CATALOG)
    b = load_provider_model_catalog(CATALOG)
    assert a.subscription_pool_family("xai.grok-4.7", surface="cursor") == b.subscription_pool_family("xai.grok-4.7", surface="cursor")
    assert not hasattr(a, "reserve") and not hasattr(a, "remaining")


def test_rates_and_source_dates_are_not_fabricated_launch_or_cash_permission():
    doc = _document()
    for key in ("openai.gpt-5.6-luna", "openai.gpt-5.6-terra", "anthropic.claude-sonnet-5.5"):
        rows = [r for r in doc["models"][key]["api_rates"] if r["surface"] == "cursor"]
        assert rows
        for rate in rows:
            assert rate["effective_from"] == "2026-10-05"
            assert "Base model-token value only" in rate["notes"]
            assert doc["sources"][rate["source_id"]]["url"].startswith("https://cursor.com/docs/models/")


@pytest.mark.parametrize("key,expected", [
    ("glm.glm-5.3-flash", "0.68"),
    ("glm.glm-5.3", "6.06"),
    ("minimax.minimax-m3", "1.56"),
    ("alibaba.qwen3.8-flash", "0.636"),
    ("alibaba.qwen3.8-max", "8.25"),
    ("openai.gpt-5.6-luna", "1.42"),
    ("xai.grok-4.6", "8.5"),
    ("xai.grok-4.7", "8.5"),
])
def test_opencode_reseller_value_is_surface_specific_not_new_quota(key, expected):
    catalog = load_provider_model_catalog(CATALOG)
    assert catalog.estimate_api_cash_usd(
        key, surface="opencode_go", context_tokens=100_000,
        input_tokens=1_000_000, cached_input_tokens=1_000_000,
        output_tokens=1_000_000,
    ) == Decimal(expected)
    rule = catalog.subscription_burn_rule(key, surface="opencode_go")
    assert rule.method == "measured_native_delta"
    assert rule.pool_family is None
    with pytest.raises(ModelEconomicsError, match="no reviewed pool family"):
        catalog.subscription_pool_family(key, surface="opencode_go")
    # Economic availability is not a new registered native harness.
    assert not any(o.surface == "opencode_go" for o in catalog.model(key).harness_overlays)


@pytest.mark.parametrize("key", ["xai.grok-4.6", "xai.grok-4.7"])
def test_opencode_grok_threshold_does_not_inherit_other_surface_boundary(key):
    catalog = load_provider_model_catalog(CATALOG)
    def quote(context):
        return catalog.estimate_api_cash_usd(
            key, surface="opencode_go", context_tokens=context,
            input_tokens=1_000_000, output_tokens=1_000_000,
        )
    assert quote(200_000) == Decimal("8")
    assert quote(200_001) == Decimal("16")
    assert catalog.estimate_api_cash_usd(
        key, surface="xai_api", context_tokens=200_000,
        input_tokens=1_000_000, output_tokens=1_000_000,
    ) == Decimal("16")


def test_opencode_rates_do_not_forge_unsupported_cache_write_price():
    catalog = load_provider_model_catalog(CATALOG)
    with pytest.raises(ModelEconomicsError, match="no write price"):
        catalog.estimate_api_cash_usd(
            "glm.glm-5.3", surface="opencode_go", context_tokens=100_000,
            input_tokens=0, cache_write_tokens=1,
        )
    assert catalog.estimate_api_cash_usd(
        "alibaba.qwen3.8-flash", surface="opencode_go", context_tokens=100_000,
        input_tokens=0, cache_write_tokens=1_000_000,
    ) == Decimal("0.20")


def test_opencode_luna_long_context_rate_uses_reseller_source():
    catalog = load_provider_model_catalog(CATALOG)
    assert catalog.estimate_api_cash_usd(
        "openai.gpt-5.6-luna", surface="opencode_go", context_tokens=272_001,
        input_tokens=1_000_000, cached_input_tokens=1_000_000,
        cache_write_tokens=1_000_000, output_tokens=1_000_000,
    ) == Decimal("2.74")
    doc = _document()
    assert doc["sources"]["opencode-go-models-20261005"]["url"] == "https://opencode.ai/zen/go/v1/models"
    for record in doc["models"].values():
        for row in record["api_rates"]:
            if row["surface"] == "opencode_go":
                assert row["source_id"] == "opencode-go-20261005"
                assert "not an independent per-model quota" in row["notes"]
