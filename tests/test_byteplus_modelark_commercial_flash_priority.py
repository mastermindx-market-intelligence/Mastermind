"""Source-only commercial Flash catalog and existing Capacity preview priority.

The synthetic reviewed in-memory router exercises projection behavior without
claiming it has an installed, callable or presently valid production tier.
"""
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path

import pytest

from control_plane.capacity_economics_projection import (
    BYTEPLUS_COMMERCIAL_FLASH_MODELS,
    CapacityEconomicsProjectionError,
    project_quota_preference,
)
from control_plane.codex_provider_realm import (
    BYTEPLUS_MODELARK_COMMERCIAL,
    REVIEWED_CODEX_PROVIDER_REALMS,
)
from control_plane.model_router import ModelRouter, SuitabilityTier

CONFIG = Path(__file__).resolve().parents[1] / "config" / "executive_worker_routes.json"
GLM = "byteplus-modelark.glm-5.3-flash"
DEEPSEEK = "byteplus-modelark.deepseek-v4.1-flash"
ZAI = "glm.paid.sealed-input"
TIER = "research.routine.primary"
TIERS = ({"tier_id": TIER, "model_aliases": [ZAI, GLM, DEEPSEEK]},)


def preview(*, selected="zai-flash", glm_slots=2, deepseek_slots=1):
    return {
        "schema": "mastermind.quota_economics_preview/v1",
        "as_of": "2026-10-24T08:00:00Z",
        "authority": "NONE_PREVIEW_ONLY",
        "binding_verification": "NOT_PERFORMED",
        "live_admission": False,
        "claim_time_revalidation_required": True,
        "status": "PREVIEW_READY",
        "suggested_option": selected,
        "selected_tier": TIER,
        "options": [
            {
                "option_id": "zai-flash",
                "provider": "glm",
                "model_alias": ZAI,
                "eligible_in_preview": True,
                "estimated_startable_jobs": 8,
                "suggested_parallelism": 6,
                "expiry_pressure_jobs_per_hour": None,
            },
            {
                "option_id": "byteplus-glm",
                "provider": "byteplus-modelark",
                "model_alias": GLM,
                "eligible_in_preview": True,
                "estimated_startable_jobs": glm_slots,
                "suggested_parallelism": glm_slots,
                "expiry_pressure_jobs_per_hour": None,
            },
            {
                "option_id": "byteplus-deepseek",
                "provider": "byteplus-modelark",
                "model_alias": DEEPSEEK,
                "eligible_in_preview": True,
                "estimated_startable_jobs": deepseek_slots,
                "suggested_parallelism": deepseek_slots,
                "expiry_pressure_jobs_per_hour": None,
            },
        ],
    }


def projected_test_router(monkeypatch):
    """A future-review simulation; does NOT pass through Router.load tier parsing."""
    router = ModelRouter.load()
    monkeypatch.setitem(
        REVIEWED_CODEX_PROVIDER_REALMS,
        BYTEPLUS_MODELARK_COMMERCIAL.realm_id,
        BYTEPLUS_MODELARK_COMMERCIAL,
    )
    router.providers["byteplus-modelark"] = replace(
        router.providers["byteplus-modelark"],
        enabled=True,
        autonomous_allowed=True,
    )
    for alias in (GLM, DEEPSEEK):
        router.model_aliases[alias] = replace(
            router.model_aliases[alias], worker_eligible=True
        )
    router.routes["research"]["routine"] = (SuitabilityTier(TIER, (ZAI, GLM, DEEPSEEK)),)
    return router


def test_catalog_has_two_exact_commercial_model_ids_and_remains_offline():
    raw = json.loads(CONFIG.read_text())
    assert BYTEPLUS_COMMERCIAL_FLASH_MODELS == {
        GLM: "glm-5-3-flash-260828",
        DEEPSEEK: "deepseek-v4-1-flash-261017",
    }
    router = ModelRouter.load()
    for alias, model in BYTEPLUS_COMMERCIAL_FLASH_MODELS.items():
        row = raw["model_aliases"][alias]
        assert row["model"] == model
        assert row["provider_alias"] == "byteplus-modelark"
        assert row["execution_profile_id"] == "sealed.worker.write.no-extensions.v1"
        assert row["worker_eligible"] is False
        assert set(row["capabilities"]) == {"code", "tests"}
        assert router.model_aliases[alias].worker_eligible is False
    assert raw["providers"]["byteplus-modelark"]["enabled"] is False
    assert raw["providers"]["byteplus-modelark"]["autonomous_allowed"] is False
    assert raw["providers"]["byteplus"]["autonomous_allowed"] is False
    for route in raw["routes"].values():
        for risk in ("routine", "elevated"):
            for tier in route[risk]:
                assert not set(BYTEPLUS_COMMERCIAL_FLASH_MODELS).intersection(
                    tier["model_aliases"]
                )


def test_unreviewed_commercial_flash_cannot_be_selected_from_preview():
    doc = preview(selected="byteplus-glm")
    with pytest.raises(CapacityEconomicsProjectionError, match="unreviewed commercial"):
        project_quota_preference(TIERS, doc)
    baseline = project_quota_preference(TIERS, preview())
    assert baseline.provider == "glm"
    assert baseline.selection_is_commitment is False


def test_prefer_available_commercial_flash_over_zai_flash_in_first_tier(monkeypatch):
    router = projected_test_router(monkeypatch)
    doc = preview(glm_slots=2, deepseek_slots=3)
    before = deepcopy(doc)
    result = project_quota_preference(TIERS, doc, reviewed_router=router)
    assert result.provider == "byteplus-modelark"
    assert result.model_alias == DEEPSEEK
    assert result.suggested_parallelism == 3
    assert result.selection_is_commitment is False
    assert result.claim_time_revalidation_required is True
    assert doc == before


def test_glm_flash_and_deepseek_flash_equivalent_at_equal_headroom(monkeypatch):
    router = projected_test_router(monkeypatch)
    result = project_quota_preference(
        TIERS, preview(glm_slots=3, deepseek_slots=3), reviewed_router=router
    )
    assert result.model_alias == GLM


@pytest.mark.parametrize("variation", [
    "provider_disabled", "autonomy_disabled", "unreviewed_realm",
    "unknown_model", "different_first_tier", "no_capacity",
    "wrong_provider", "duplicate_option", "stale_model_name",
])
def test_commercial_flash_requires_exact_review_and_positive_headroom(monkeypatch, variation):
    router = projected_test_router(monkeypatch)
    doc = preview(glm_slots=2, deepseek_slots=1)
    if variation == "provider_disabled":
        router.providers["byteplus-modelark"] = replace(
            router.providers["byteplus-modelark"], enabled=False)
    elif variation == "autonomy_disabled":
        router.providers["byteplus-modelark"] = replace(
            router.providers["byteplus-modelark"], autonomous_allowed=False)
    elif variation == "unreviewed_realm":
        monkeypatch.delitem(
            REVIEWED_CODEX_PROVIDER_REALMS, BYTEPLUS_MODELARK_COMMERCIAL.realm_id)
    elif variation == "unknown_model":
        router.model_aliases[GLM] = replace(
            router.model_aliases[GLM], model="not-an-approved-commercial-model")
        router.model_aliases[DEEPSEEK] = replace(
            router.model_aliases[DEEPSEEK], model="not-an-approved-commercial-model")
    elif variation == "different_first_tier":
        router.routes["research"]["routine"] = (
            SuitabilityTier("research.routine.fallback", (ZAI, GLM, DEEPSEEK)),)
    elif variation == "no_capacity":
        for row in doc["options"][1:]:
            row["estimated_startable_jobs"] = 0
            row["suggested_parallelism"] = 0
    elif variation == "wrong_provider":
        for row in doc["options"][1:]:
            row["provider"] = "byteplus"
    elif variation == "duplicate_option":
        doc["options"].append(deepcopy(doc["options"][1]))
        doc["options"].append(deepcopy(doc["options"][2]))
    elif variation == "stale_model_name":
        doc["options"][1]["model_alias"] = "byteplus.attended"
        doc["options"][2]["model_alias"] = "byteplus.attended"
    result = project_quota_preference(TIERS, doc, reviewed_router=router)
    assert result.provider == "glm"
    assert result.model_alias == ZAI
    assert result.selection_is_commitment is False


def test_full_glm_model_is_not_displaced_by_flash_preference(monkeypatch):
    router = projected_test_router(monkeypatch)
    router.model_aliases[ZAI] = replace(
        router.model_aliases[ZAI], model="glm-5.3"
    )
    result = project_quota_preference(TIERS, preview(), reviewed_router=router)
    assert result.provider == "glm"


def test_other_pool_selection_is_not_overridden(monkeypatch):
    router = projected_test_router(monkeypatch)
    doc = preview()
    doc["options"][0]["provider"] = "codex"
    result = project_quota_preference(TIERS, doc, reviewed_router=router)
    assert result.provider == "codex"


def test_staged_held_tier_alias_is_rejected_by_actual_router_load(tmp_path):
    raw = json.loads(CONFIG.read_text())
    raw["routes"]["research"]["routine"][0]["model_aliases"].append(GLM)
    path = tmp_path / "unsafe-routes.json"
    path.write_text(json.dumps(raw))
    from control_plane.model_router import RoutingPolicyError
    with pytest.raises(RoutingPolicyError, match="ineligible alias"):
        ModelRouter.load(path)

@pytest.mark.parametrize(
    "field,bad_value,match",
    [
        ("model_alias", [], "bounded identifier"),
        ("model_alias", {}, "bounded identifier"),
        ("estimated_startable_jobs", 0, "cannot exceed"),
        ("estimated_startable_jobs", True, "non-negative integer"),
        ("suggested_parallelism", 0, "positive actionable capacity"),
        ("expiry_pressure_jobs_per_hour", [], "bounded decimal"),
    ],
)
def test_malformed_selected_preview_does_not_get_masked_by_byteplus(
    monkeypatch, field, bad_value, match,
):
    router = projected_test_router(monkeypatch)
    doc = preview()
    doc["options"][0][field] = bad_value
    with pytest.raises(CapacityEconomicsProjectionError, match=match):
        project_quota_preference(TIERS, doc, reviewed_router=router)


def test_unhashable_byteplus_option_alias_is_ignored(monkeypatch):
    router = projected_test_router(monkeypatch)
    doc = preview()
    for option in doc["options"][1:]:
        option["model_alias"] = ["byteplus-modelark.glm-5.3-flash"]
    result = project_quota_preference(TIERS, doc, reviewed_router=router)
    assert result.provider == "glm"
