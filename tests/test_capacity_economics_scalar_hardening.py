import pytest

from control_plane.capacity_economics_projection import (
    CapacityEconomicsProjectionError,
    project_quota_preference,
)
TIERS = ({"tier_id": "routine.primary", "model_aliases": ["worker.fast"]},)


def preview():
    return {
        "schema": "mastermind.quota_economics_preview/v1", "as_of": "2026-10-04T20:30:00Z",
        "authority": "NONE_PREVIEW_ONLY", "binding_verification": "NOT_PERFORMED",
        "live_admission": False, "claim_time_revalidation_required": True,
        "status": "PREVIEW_READY", "suggested_option": "provider.fast",
        "selected_tier": "routine.primary",
        "options": [{"option_id": "provider.fast", "provider": "provider",
                     "model_alias": "worker.fast", "eligible_in_preview": True,
                     "estimated_startable_jobs": 6, "suggested_parallelism": 4,
                     "expiry_pressure_jobs_per_hour": "1.250000"}],
    }


@pytest.mark.parametrize("pressure", ["NaN", "sNaN", "Infinity", "-Infinity", "-1", "tomorrow"])
def test_rejects_nonfinite_negative_or_nonnumeric_expiry_pressure(pressure):
    doc = preview()
    doc["options"][0]["expiry_pressure_jobs_per_hour"] = pressure
    with pytest.raises(CapacityEconomicsProjectionError, match="decimal"):
        project_quota_preference(TIERS, doc)


@pytest.mark.parametrize("pressure", [None, "0", "0.000000", "1.250000", "2e-3"])
def test_preserves_valid_expiry_pressure(pressure):
    doc = preview()
    doc["options"][0]["expiry_pressure_jobs_per_hour"] = pressure
    assert project_quota_preference(TIERS, doc).expiry_pressure_jobs_per_hour == pressure


def test_rejects_oversized_options_before_projection():
    doc = preview()
    doc["options"].extend({"option_id": f"other.{i}"} for i in range(512))
    with pytest.raises(CapacityEconomicsProjectionError, match="bounded"):
        project_quota_preference(TIERS, doc)
