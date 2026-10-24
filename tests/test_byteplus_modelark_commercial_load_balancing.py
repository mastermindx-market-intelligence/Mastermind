"""ModelArk commercial routing never acquires rights from a quota preview."""
from dataclasses import replace
from types import SimpleNamespace

import pytest

from control_plane.capacity_economics_projection import (
    CapacityEconomicsProjectionError,
    project_quota_preference,
)
from control_plane.codex_provider_realm import (
    BYTEPLUS_MODELARK_COMMERCIAL,
    CANDIDATE_CODEX_PROVIDER_REALMS_SPEC_ONLY,
    REVIEWED_CODEX_PROVIDER_REALMS,
)
from control_plane.codex_worker import CodexWorkerAdapter, LaunchValidationError
from control_plane.model_router import ModelRouter, SuitabilityTier

ALIAS = "byteplus-modelark.commercial-coding"
TIER = "implementation.routine.primary"


def commercial_preview():
    return {
        "schema": "mastermind.quota_economics_preview/v1",
        "as_of": "2026-10-23T18:00:00+00:00",
        "authority": "NONE_PREVIEW_ONLY",
        "binding_verification": "NOT_PERFORMED",
        "live_admission": False,
        "claim_time_revalidation_required": True,
        "status": "PREVIEW_READY",
        "suggested_option": "commercial-ark-1",
        "selected_tier": TIER,
        "options": [{
            "option_id": "commercial-ark-1",
            "provider": "byteplus-modelark",
            "model_alias": ALIAS,
            "eligible_in_preview": True,
            "estimated_startable_jobs": 2,
            "suggested_parallelism": 1,
            "expiry_pressure_jobs_per_hour": None,
        }],
    }


def tiers():
    return ({"tier_id": TIER, "model_aliases": [ALIAS]},)


def reviewed_test_router(monkeypatch):
    """Fixture simulation of a later reviewed realm, never persisted."""
    router = ModelRouter.load()
    monarch = BYTEPLUS_MODELARK_COMMERCIAL
    monkeypatch.setitem(REVIEWED_CODEX_PROVIDER_REALMS, monarch.realm_id, monarch)
    monkeypatch.setitem(
        router.providers, "byteplus-modelark",
        replace(router.providers["byteplus-modelark"], enabled=True, autonomous_allowed=True),
    )
    monkeypatch.setitem(
        router.model_aliases, ALIAS,
        replace(router.model_aliases[ALIAS], worker_eligible=True),
    )
    router.routes["implementation"]["routine"] = (
        SuitabilityTier(TIER, (ALIAS,)),)
    return router


def test_commercial_preview_still_held_without_reviewed_realm():
    router = ModelRouter.load()
    with pytest.raises(CapacityEconomicsProjectionError, match="unreviewed commercial"):
        project_quota_preference(tiers(), commercial_preview(), reviewed_router=router)
    assert (BYTEPLUS_MODELARK_COMMERCIAL.realm_id
            in CANDIDATE_CODEX_PROVIDER_REALMS_SPEC_ONLY)
    assert BYTEPLUS_MODELARK_COMMERCIAL.realm_id not in REVIEWED_CODEX_PROVIDER_REALMS


def test_commercial_reviewed_route_allows_only_non_authoritative_preference(monkeypatch):
    router = reviewed_test_router(monkeypatch)
    result = project_quota_preference(
        tiers(), commercial_preview(), reviewed_router=router
    )
    assert result.provider == "byteplus-modelark"
    assert result.model_alias == ALIAS
    assert result.selection_is_commitment is False
    assert result.claim_time_revalidation_required is True
    assert result.estimated_startable_jobs == 2
    assert result.suggested_parallelism == 1


@pytest.mark.parametrize("mutation", ["provider_off", "no_autonomy", "not_worker", "wrong_tier"])
def test_reviewed_route_refuses_unqualified_state(monkeypatch, mutation):
    router = reviewed_test_router(monkeypatch)
    if mutation == "provider_off":
        router.providers["byteplus-modelark"] = replace(
            router.providers["byteplus-modelark"], enabled=False)
    elif mutation == "no_autonomy":
        router.providers["byteplus-modelark"] = replace(
            router.providers["byteplus-modelark"], autonomous_allowed=False)
    elif mutation == "not_worker":
        router.model_aliases[ALIAS] = replace(
            router.model_aliases[ALIAS], worker_eligible=False)
    else:
        router.routes["implementation"]["routine"] = (
            SuitabilityTier("different.tier", (ALIAS,)),)
    with pytest.raises(CapacityEconomicsProjectionError, match="unreviewed commercial"):
        project_quota_preference(tiers(), commercial_preview(), reviewed_router=router)


@pytest.mark.parametrize(
    "provider,alias",
    [
        ("byteplus", ALIAS),
        ("BytePlus-ModelArk", ALIAS),
        ("byteplus-modelark", "byteplus.attended"),
        ("byteplus-modelark-extra", ALIAS),
        ("byteplus-modelark", "byteplus-modelark.attended"),
        ("byteplus-modelark", "BytePlus-ModelArk.commercial-coding"),
    ],
)
def test_commercial_review_does_not_license_personal_near_miss(monkeypatch, provider, alias):
    router = reviewed_test_router(monkeypatch)
    doc = commercial_preview()
    doc["options"][0].update(provider=provider, model_alias=alias)
    with pytest.raises(CapacityEconomicsProjectionError):
        project_quota_preference(
            ({"tier_id": TIER, "model_aliases": [alias]},), doc,
            reviewed_router=router,
        )


def test_commercial_preview_can_never_claim_live_admission(monkeypatch):
    router = reviewed_test_router(monkeypatch)
    doc = commercial_preview()
    doc["live_admission"] = True
    with pytest.raises(CapacityEconomicsProjectionError, match="live admission"):
        project_quota_preference(tiers(), doc, reviewed_router=router)


def guarded_adapter(realm, subscription_owner=None, credential_loader=lambda: "unused"):
    adapter = object.__new__(CodexWorkerAdapter)
    adapter.provider_realm = realm
    adapter.provider_credential_loader = credential_loader
    adapter.subscription_realm_owner = subscription_owner
    return adapter


def test_commercial_transport_does_not_launch_while_candidate():
    adapter = guarded_adapter(BYTEPLUS_MODELARK_COMMERCIAL)
    with pytest.raises(LaunchValidationError):
        adapter._refuse_subscription_for_plain_start(
            SimpleNamespace(subscription_canary_claim=False))


def test_only_exact_reviewed_commercial_realm_may_reach_plain_worker_start(monkeypatch):
    realm = BYTEPLUS_MODELARK_COMMERCIAL
    monkeypatch.setitem(REVIEWED_CODEX_PROVIDER_REALMS, realm.realm_id, realm)
    spec = SimpleNamespace(subscription_canary_claim=False)
    guarded_adapter(realm)._refuse_subscription_for_plain_start(spec)
    for adapter, claim in [
        (guarded_adapter(replace(realm, display_name="Unreviewed copy")), False),
        (guarded_adapter(realm, credential_loader=None), False),
        (guarded_adapter(realm, subscription_owner=object()), False),
        (guarded_adapter(realm), True),
    ]:
        with pytest.raises(LaunchValidationError):
            adapter._refuse_subscription_for_plain_start(
                SimpleNamespace(subscription_canary_claim=claim))


def test_codex_plain_start_does_not_accept_subscription_canary():
    from control_plane.codex_provider_realm import MINIMAX_TOKEN_PLAN
    adapter = guarded_adapter(MINIMAX_TOKEN_PLAN)
    with pytest.raises(LaunchValidationError):
        adapter._refuse_subscription_for_plain_start(
            SimpleNamespace(subscription_canary_claim=False))
