import copy
import inspect

import pytest

import control_plane.capacity_economics_projection as capacity_economics_projection
from control_plane.capacity_economics_projection import (
    BYTEPLUS_IDENTITY_UNRECOGNIZED_REFUSED,
    BYTEPLUS_PERSONAL_CODING_PLAN_REFUSED,
    BYTEPLUS_ROUTE_NOT_APPLICABLE,
    BYTEPLUS_ROUTER_NOT_REVIEWED,
    BYTEPLUS_ELIGIBILITY_SCHEMA,
    CapacityEconomicsProjectionError,
    evaluate_byteplus_route_eligibility,
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


@pytest.mark.parametrize("starts,parallelism", [(0, 0), (4, 0)])
def test_refuses_zero_actionable_capacity_even_when_preview_claims_eligibility(starts, parallelism):
    doc = preview()
    row = doc["options"][0]
    row["estimated_startable_jobs"] = starts
    row["suggested_parallelism"] = parallelism
    before = copy.deepcopy(doc)
    with pytest.raises(CapacityEconomicsProjectionError, match="positive actionable capacity"):
        project_quota_preference(TIERS, doc)
    assert doc == before


def test_one_startable_job_remains_an_advisory_preference_not_a_claim():
    doc = preview()
    doc["options"][0]["estimated_startable_jobs"] = 1
    doc["options"][0]["suggested_parallelism"] = 1
    before = copy.deepcopy(doc)
    result = project_quota_preference(TIERS, doc)
    assert result.estimated_startable_jobs == 1
    assert result.suggested_parallelism == 1
    assert result.claim_time_revalidation_required is True
    assert result.selection_is_commitment is False
    assert doc == before


@pytest.mark.parametrize(
    "provider,alias",
    [("byteplus", "byteplus.attended"), ("byteplus", "fast.engineering"),
     ("byteplus-coding-plan-personal", "fast.engineering"),
     ("xai", "byteplus.attended"), ("xai", "BYTEPLUS.ATTENDED"),
     ("xai", "BytePlus.Attended"), ("xai", "byte.plus.attended")],
)
def test_personal_coding_plan_route_refused_with_typed_reason(provider, alias):
    # A quota-preview producer can never mint use rights or account-backed
    # subscription capacity by asserting a non-zero parallelism estimate.
    # The typed gate refuses the personal Coding Plan auth route with a
    # specific reason code EVEN IF a caller's supplied first-tier aliases
    # use that exact casing or the preview forces positive capacity.
    tiers = ({"tier_id": "implementation.routine.primary",
              "model_aliases": [alias]},)
    doc = preview()
    doc["options"][0]["provider"] = provider
    doc["options"][0]["model_alias"] = alias
    doc["options"][0]["estimated_startable_jobs"] = 25
    doc["options"][0]["suggested_parallelism"] = 8
    frozen = copy.deepcopy(doc)
    with pytest.raises(CapacityEconomicsProjectionError) as excinfo:
        project_quota_preference(tiers, doc)
    message = str(excinfo.value)
    assert "BYTEPLUS_PERSONAL_CODING_PLAN_REFUSED" in message
    assert "personal BytePlus Coding Plan" in message
    assert doc == frozen


@pytest.mark.parametrize(
    "provider,alias",
    [("BytePlus", "fast.engineering"), ("BYTEPLUS", "fast.engineering"),
     ("BytePlusTrusted", "fast.engineering"),
     ("xai", "byteplus.attended.back"), ("xai", "byteplus.attendedX"),
     ("xai", "mybyteplus.attended"), ("byte_plus", "fast.engineering"),
     ("byte.plus", "fast.engineering")],
)
def test_unrecognized_byteplus_family_identity_refused_with_typed_reason(provider, alias):
    # Near-miss byteplus-family labels are not the reviewed commercial
    # provider and not an approved auth route; each refusal is typed so a
    # consumer can distinguish them from the personal Coding Plan refusal.
    tiers = ({"tier_id": "implementation.routine.primary",
              "model_aliases": [alias]},)
    doc = preview()
    doc["options"][0]["provider"] = provider
    doc["options"][0]["model_alias"] = alias
    doc["options"][0]["estimated_startable_jobs"] = 25
    doc["options"][0]["suggested_parallelism"] = 8
    frozen = copy.deepcopy(doc)
    with pytest.raises(CapacityEconomicsProjectionError) as excinfo:
        project_quota_preference(tiers, doc)
    message = str(excinfo.value)
    assert "BYTEPLUS_IDENTITY_UNRECOGNIZED_REFUSED" in message
    assert doc == frozen


def test_typed_verdict_passes_non_byteplus_identity_through():
    verdict = evaluate_byteplus_route_eligibility(
        "xai", "fast.engineering",
        first_tier_id="implementation.routine.primary",
        first_tier_aliases=("fast.engineering",),
        reviewed_router=None,
    )
    assert verdict.gate_applies is False
    assert verdict.eligible is True
    assert verdict.reason_code == BYTEPLUS_ROUTE_NOT_APPLICABLE
    assert verdict.auth_route == "not-byteplus"
    assert verdict.to_dict()["schema"] == BYTEPLUS_ELIGIBILITY_SCHEMA


def test_typed_verdict_types_personal_pool_and_auth_route():
    verdict = evaluate_byteplus_route_eligibility(
        "byteplus", "byteplus.attended",
        first_tier_id="implementation.routine.primary",
        first_tier_aliases=("byteplus.attended",),
        reviewed_router=None,
    )
    assert verdict.gate_applies is True
    assert verdict.eligible is False
    assert verdict.reason_code == BYTEPLUS_PERSONAL_CODING_PLAN_REFUSED
    assert verdict.auth_route == "personal-coding-plan"
    assert verdict.pool_id == "byteplus"


def test_unreviewed_commercial_route_has_a_specific_typed_reason():
    verdict = evaluate_byteplus_route_eligibility(
        "byteplus-modelark", "byteplus-modelark.glm-5.3-flash",
        first_tier_id="implementation.routine.primary",
        first_tier_aliases=("byteplus-modelark.glm-5.3-flash",),
        reviewed_router=None,
    )
    assert verdict.gate_applies is True
    assert verdict.eligible is False
    assert verdict.reason_code == BYTEPLUS_ROUTER_NOT_REVIEWED
    assert verdict.auth_route == "modelark-commercial-api-key"
    assert verdict.pool_id == "byteplus"
    assert "unreviewed commercial" in verdict.detail


def test_malformed_identity_is_refused_fail_closed():
    verdict = evaluate_byteplus_route_eligibility(
        123, "fast.engineering",
        first_tier_id="implementation.routine.primary",
        first_tier_aliases=("fast.engineering",),
        reviewed_router=None,
    )
    assert verdict.eligible is False
    assert verdict.reason_code == BYTEPLUS_IDENTITY_UNRECOGNIZED_REFUSED


def test_unreviewed_commercial_selection_is_refused_with_typed_reason():
    doc = preview()
    doc["suggested_option"] = "bp.candidate"
    doc["options"][0].update({
        "option_id": "bp.candidate",
        "provider": "byteplus-modelark",
        "model_alias": "byteplus-modelark.glm-5.3-flash",
    })
    tiers = ({"tier_id": "implementation.routine.primary",
              "model_aliases": ["byteplus-modelark.glm-5.3-flash"]},)
    with pytest.raises(CapacityEconomicsProjectionError) as excinfo:
        project_quota_preference(tiers, doc)
    message = str(excinfo.value)
    assert "BYTEPLUS_ROUTER_NOT_REVIEWED" in message
    assert "unreviewed commercial" in message


def test_byteplus_gate_is_typed_and_not_a_substring_gate():
    # Readback pinned as a regression test: the substring gate no longer
    # gates eligibility anywhere in this module; the typed evaluator does.
    source = inspect.getsource(capacity_economics_projection)
    assert "_mentions_byteplus" not in source
    assert "evaluate_byteplus_route_eligibility(" in source
    assert "BYTEPLUS_PERSONAL_CODING_PLAN_REFUSED" in source
    assert "BYTEPLUS_ROUTE_REVIEWED_COMMERCIAL" in source



@pytest.mark.parametrize("ordinary_provider", ["xai", "codex", "glm", "qwen", "minimax", "alibaba"])
def test_byteplus_label_guard_does_not_reject_unrelated_first_tier(ordinary_provider):
    doc = preview()
    doc["options"][0]["provider"] = ordinary_provider
    frozen = copy.deepcopy(doc)
    result = project_quota_preference(TIERS, doc)
    assert result.provider == ordinary_provider
    assert result.selection_is_commitment is False
    assert result.claim_time_revalidation_required is True
    assert doc == frozen
