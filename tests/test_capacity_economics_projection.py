import copy

import pytest

from control_plane.capacity_economics_projection import (
    CapacityEconomicsProjectionError,
    project_quota_preference,
)

TIERS = (
    {"tier_id": "implementation.routine.primary", "model_aliases": ["fast.engineering", "standard.engineering"]},
    {"tier_id": "implementation.routine.fallback", "model_aliases": ["fallback.engineering"]},
)


def preview():
    return {
        "schema": "mastermind.quota_economics_preview/v1",
        "as_of": "2026-09-13T17:00:00+00:00",
        "authority": "NONE_PREVIEW_ONLY",
        "binding_verification": "NOT_PERFORMED",
        "live_admission": False,
        "claim_time_revalidation_required": True,
        "status": "PREVIEW_READY",
        "suggested_option": "grok.fast",
        "selected_tier": "implementation.routine.primary",
        "options": [
            {
                "option_id": "grok.fast",
                "provider": "xai",
                "model_alias": "fast.engineering",
                "eligible_in_preview": True,
                "reasons": [],
                "estimated_startable_jobs": 6,
                "suggested_parallelism": 4,
                "expiry_pressure_jobs_per_hour": "1.250000",
                "forecasts": [],
            }
        ],
        "warnings": [],
    }


def test_projects_only_first_tier_preview_as_non_commitment():
    result = project_quota_preference(TIERS, preview())
    assert result.model_alias == "fast.engineering"
    assert result.provider == "xai"
    assert result.selection_is_commitment is False
    assert result.claim_time_revalidation_required is True
    assert result.to_dict()["schema"] == "mastermind.capacity_economics_projection/v1"


def test_refuses_lower_tier_promotion():
    doc = preview()
    doc["selected_tier"] = "implementation.routine.fallback"
    doc["options"][0]["model_alias"] = "fallback.engineering"
    with pytest.raises(CapacityEconomicsProjectionError, match="first lawful suitability tier"):
        project_quota_preference(TIERS, doc)


def test_refuses_later_tier_selection_while_option_remains_in_first_tier():
    doc = preview()
    doc["selected_tier"] = "implementation.routine.fallback"
    with pytest.raises(CapacityEconomicsProjectionError, match="first lawful suitability tier"):
        project_quota_preference(TIERS, doc)


def test_refuses_preview_that_claims_live_admission_or_skips_revalidation():
    doc = preview()
    doc["live_admission"] = True
    with pytest.raises(CapacityEconomicsProjectionError, match="live admission"):
        project_quota_preference(TIERS, doc)
    doc = preview()
    doc["claim_time_revalidation_required"] = False
    with pytest.raises(CapacityEconomicsProjectionError, match="revalidation"):
        project_quota_preference(TIERS, doc)


def test_refuses_ineligible_or_ambiguous_suggested_option():
    doc = preview()
    doc["options"][0]["eligible_in_preview"] = False
    with pytest.raises(CapacityEconomicsProjectionError, match="not eligible"):
        project_quota_preference(TIERS, doc)
    doc = preview()
    doc["options"].append(copy.deepcopy(doc["options"][0]))
    with pytest.raises(CapacityEconomicsProjectionError, match="exactly one"):
        project_quota_preference(TIERS, doc)


def test_refuses_parallelism_larger_than_available_startable_jobs():
    doc = preview()
    doc["options"][0]["suggested_parallelism"] = 7
    with pytest.raises(CapacityEconomicsProjectionError, match="cannot exceed"):
        project_quota_preference(TIERS, doc)
