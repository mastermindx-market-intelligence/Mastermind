"""P2 security negatives: staging-only tests, NOT production authorization."""
from dataclasses import replace
from datetime import datetime, timezone
import hashlib

import pytest

from control_plane.capacity_economics_projection import (
    CapacityEconomicsProjectionError,
    QuotaPreviewFreshness,
    _source_freshness_ok,
    project_quota_preference,
)
from control_plane.codex_provider_realm import (
    BYTEPLUS_MODELARK_COMMERCIAL,
    REVIEWED_CODEX_PROVIDER_REALMS,
)
from control_plane.model_router import ModelRouter, SuitabilityTier
from scripts.byteplus_modelark_commercial_preflight import (
    CommercialPreflightError, source_preflight,
)

CODING = "byteplus-modelark.commercial-coding"
TIER = "implementation.routine.primary"


def test_coding_model_pin_blocks_wrong_model_even_under_simulated_review(monkeypatch):
    import control_plane.capacity_economics_projection as cep
    router = ModelRouter.load()
    monkeypatch.setitem(REVIEWED_CODEX_PROVIDER_REALMS, BYTEPLUS_MODELARK_COMMERCIAL.realm_id,
                        BYTEPLUS_MODELARK_COMMERCIAL)
    monkeypatch.setitem(router.providers, "byteplus-modelark",
                        replace(router.providers["byteplus-modelark"],
                                enabled=True, autonomous_allowed=True))
    monkeypatch.setitem(router.model_aliases, CODING,
                        replace(router.model_aliases[CODING],
                                model="wrong-model-id", worker_eligible=True))
    router.routes["implementation"]["routine"] = (SuitabilityTier(TIER, (CODING,)),)
    monkeypatch.setattr(cep, "_canonical_model_router_matches", lambda r: r is router)
    preview = {
        "schema": "mastermind.quota_economics_preview/v1",
        "as_of": "2026-10-24T08:00:00+00:00",
        "authority": "NONE_PREVIEW_ONLY", "binding_verification": "NOT_PERFORMED",
        "live_admission": False, "claim_time_revalidation_required": True,
        "status": "PREVIEW_READY", "selected_tier": TIER,
        "suggested_option": "candidate",
        "options": [{"option_id": "candidate", "provider": "byteplus-modelark",
                     "model_alias": CODING, "eligible_in_preview": True,
                     "estimated_startable_jobs": 1, "suggested_parallelism": 1,
                     "expiry_pressure_jobs_per_hour": None}],
    }
    with pytest.raises(CapacityEconomicsProjectionError, match="unreviewed commercial"):
        project_quota_preference(({"tier_id": TIER, "model_aliases": [CODING]},),
                                 preview, reviewed_router=router)


def test_default_preflight_rejects_custom_router_without_owner_pin():
    with pytest.raises(CommercialPreflightError, match="CUSTOM_ROUTER"):
        source_preflight(ModelRouter.load())


def test_foreign_router_rejected_even_with_identical_bytes_and_digest(tmp_path):
    router = ModelRouter.load()
    clone = tmp_path / "copied_policy.json"
    raw = router.source_path.read_bytes()
    clone.write_bytes(raw)
    with pytest.raises(CommercialPreflightError, match="ROUTER_SOURCE"):
        source_preflight(ModelRouter.load(clone),
                         expected_router_source_sha256=hashlib.sha256(raw).hexdigest())


def test_capability_registry_identity_mutation_rejected(tmp_path):
    router = ModelRouter.load()
    raw = router.source_path.read_bytes()
    router.capability_registry = replace(
        router.capability_registry, policy_digest="f" * 64,
    )
    with pytest.raises(CommercialPreflightError, match="ROUTER_SOURCE_OR_IN_MEMORY_DRIFT"):
        source_preflight(router,
            expected_router_source_sha256=hashlib.sha256(raw).hexdigest())


def test_in_memory_policy_mutation_rejected_despite_same_canonical_digest():
    router = ModelRouter.load()
    raw = router.source_path.read_bytes()
    router.providers["byteplus-modelark"] = replace(
        router.providers["byteplus-modelark"], enabled=True)
    with pytest.raises(CommercialPreflightError, match="ROUTER_SOURCE_OR_IN_MEMORY_DRIFT"):
        source_preflight(router, expected_router_source_sha256=hashlib.sha256(raw).hexdigest())


@pytest.mark.parametrize("variant", ["naive", "future", "stale", "negative_age", "overlong_limit", "split_stale"])
def test_freshness_rejects_untrusted_or_stale_time(variant):
    t = datetime(2026, 10, 24, 8, 0, tzinfo=timezone.utc)
    observed = t
    verified = datetime(2026, 10, 24, 8, 1, tzinfo=timezone.utc)
    limit = 120
    if variant == "naive":
        observed = datetime(2026, 10, 24, 8, 0)
    elif variant == "future":
        observed = datetime(2026, 10, 24, 8, 10, tzinfo=timezone.utc)
    elif variant == "stale":
        verified = datetime(2026, 10, 24, 8, 10, tzinfo=timezone.utc)
    elif variant == "split_stale":
        observed = datetime(2026, 10, 24, 8, 1, 30, tzinfo=timezone.utc)
        verified = datetime(2026, 10, 24, 8, 2, 30, tzinfo=timezone.utc)
    elif variant == "negative_age":
        verified = datetime(2026, 10, 24, 7, 59, tzinfo=timezone.utc)
    elif variant == "overlong_limit":
        limit = 3600
    assert _source_freshness_ok("2026-10-24T08:00:00Z",
                                QuotaPreviewFreshness(observed, verified, limit)) is False


def test_canonical_preflight_remains_only_source_and_does_not_enable_start():
    result = source_preflight()
    assert result["model_router_source_held"] is True
    assert result["personal_plan_isolated"] is True
    assert result["provider_network_called"] is False
    assert result["production_start_authorized"] is False
