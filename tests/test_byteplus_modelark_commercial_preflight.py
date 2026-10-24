"""Offline owner handoff without credential/API access or false Capacity START."""
from dataclasses import replace
from types import SimpleNamespace
import copy
import json
import subprocess
import sys

import pytest

from control_plane.model_router import ModelRouter, SuitabilityTier
from scripts.byteplus_modelark_commercial_preflight import (
    CAPACITY_IDENTITY_SCHEMA,
    COMMERCIAL_CODING,
    COMMERCIAL_ENDPOINT,
    CommercialPreflightError,
    OWNER_KEY_NAME,
    PROVIDER,
    SCHEMA,
    capacity_identity_preflight,
    source_preflight,
)

HOST_A = "host-" + "a" * 64
HOST_B = "host-" + "b" * 64
SOURCE_SHA = "c" * 64
KEY = ("worker-modelark-1", "modelark-commercial")


def test_source_preflight_is_source_only_no_credentials_or_start():
    report = source_preflight()
    assert report["schema"] == SCHEMA
    assert report["evidence_scope"] == "SOURCE_ONLY"
    assert report["provider_alias"] == PROVIDER
    assert report["endpoint"] == COMMERCIAL_ENDPOINT
    assert report["owner_secret_env_name"] == OWNER_KEY_NAME
    config = report["codex_config_overrides_key_free"]
    assert any("model_provider=" in item for item in config)
    assert any(".base_url=" in item and COMMERCIAL_ENDPOINT in item for item in config)
    assert any(".env_key=" in item and OWNER_KEY_NAME in item for item in config)
    assert not any("/api/coding" in item or "Bearer " in item for item in config)
    assert len(report["router_source_sha256"]) == 64
    assert report["model_ids_by_alias"][COMMERCIAL_CODING] == "dola-seed-2-1-turbo-260628"
    assert report["model_ids_by_alias"]["byteplus-modelark.glm-5.3-flash"] == "glm-5-3-flash-260828"
    assert report["model_ids_by_alias"]["byteplus-modelark.deepseek-v4.1-flash"] == "deepseek-v4-1-flash-261017"
    for field in (
        "credential_read", "provider_network_called", "provider_account_verified",
        "model_activation_verified", "review_accepted", "issuer_usage_verified",
        "quota_known", "worker_registered", "capacity_identity_read",
        "claim_time_capacity_verified", "production_start_authorized"
    ):
        assert report[field] is False
    assert report["commercial_realm_source_held"] is True
    assert report["personal_plan_isolated"] is True
    assert len(report["next_owner_actions"]) >= 7


def test_source_cli_does_not_require_provider_key(tmp_path, monkeypatch):
    monkeypatch.delenv(OWNER_KEY_NAME, raising=False)
    result = subprocess.run(
        [sys.executable, "-m", "scripts.byteplus_modelark_commercial_preflight"],
        capture_output=True, text=True, timeout=15, check=True
    )
    value = json.loads(result.stdout)
    assert value["credential_read"] is False
    assert value["production_start_authorized"] is False
    assert result.stderr == ""


@pytest.mark.parametrize("mutation", [
    "enabled", "autonomy", "personal_enabled", "personal_autonomy",
    "personal_alias", "missing_alias", "model_drift", "alias_worker",
    "personal_in_tier", "commercial_in_tier", "wrong_adapter",
])
def test_source_preflight_refuses_early_production_promotion(mutation):
    router = ModelRouter.load()
    if mutation == "enabled":
        router.providers[PROVIDER] = replace(router.providers[PROVIDER], enabled=True)
    elif mutation == "autonomy":
        router.providers[PROVIDER] = replace(router.providers[PROVIDER], autonomous_allowed=True)
    elif mutation == "personal_enabled":
        router.providers["byteplus"] = replace(router.providers["byteplus"], enabled=True)
    elif mutation == "personal_autonomy":
        router.providers["byteplus"] = replace(router.providers["byteplus"], autonomous_allowed=True)
    elif mutation == "personal_alias":
        router.model_aliases["byteplus.attended"] = replace(
            router.model_aliases["byteplus.attended"], provider_alias=PROVIDER)
    elif mutation == "missing_alias":
        del router.model_aliases["byteplus-modelark.glm-5.3-flash"]
    elif mutation == "model_drift":
        alias = router.model_aliases["byteplus-modelark.deepseek-v4.1-flash"]
        router.model_aliases[alias.model_alias] = replace(alias, model="unqualified-model")
    elif mutation == "alias_worker":
        alias = router.model_aliases[COMMERCIAL_CODING]
        router.model_aliases[COMMERCIAL_CODING] = replace(alias, worker_eligible=True)
    elif mutation == "wrong_adapter":
        router.providers[PROVIDER] = replace(router.providers[PROVIDER], adapter_id="attended-fabric")
    else:
        which = "byteplus.attended" if mutation == "personal_in_tier" else COMMERCIAL_CODING
        tier = router.routes["implementation"]["routine"][0]
        router.routes["implementation"]["routine"] = (
            SuitabilityTier(tier.tier_id, tier.model_aliases + (which,)),
        )
    with pytest.raises(CommercialPreflightError):
        source_preflight(router)


def join(*, host=HOST_A, digest=SOURCE_SHA):
    return {
        "schema": "mastermind.executive_capacity_join/v1",
        "host_ref": host,
        "capacity_capability_id": "byteplus_modelark_worker_capability",
        "provider_capacity_schema": "mastermind.provider_capacity.v1",
        "worker_source_config_digest": digest,
    }


class Registry:
    def __init__(self, provider=PROVIDER, metadata=None):
        self.calls = []
        self.quota = SimpleNamespace(
            worker_id=KEY[0], quota_class=KEY[1], provider=provider,
            metadata=metadata if metadata is not None else {"capacity_join": join()}
        )

    def get_quota_class(self, worker_id, quota_class):
        self.calls.append((worker_id, quota_class))
        return self.quota

    def get_worker(self, worker_id):
        raise AssertionError("Capacity identity preflight MUST NOT enumerate workers")


def test_capacity_owner_reads_canonical_quota_join_but_never_infers_slots():
    registry = Registry()
    registry.quota.metadata["private_account_api_key"] = "SECRET_DO_NOT_PROJECT"
    out = capacity_identity_preflight(
        registry, [KEY], expected_worker_source_config_digest=SOURCE_SHA
    )
    assert registry.calls == [KEY]
    assert out["schema"] == CAPACITY_IDENTITY_SCHEMA
    assert out["evidence_scope"] == "CANONICAL_REGISTRY_IDENTITY_READ_ONLY"
    assert out["candidate_count"] == 1
    assert out["candidates"][0]["capacity_join"] == join()
    assert out["provider_origin_quota_verified"] is False
    assert out["claim_time_capacity_verified"] is False
    assert out["production_start_authorized"] is False
    assert out["credential_read"] is False
    assert "SECRET_DO_NOT_PROJECT" not in json.dumps(out)


@pytest.mark.parametrize("digest", [
    "", "A"*64, "g"*64, "a"*65, None, 123, "c"*63
])
def test_invalid_expected_worker_config_digest_refuses_before_registry(digest):
    registry = Registry()
    with pytest.raises(CommercialPreflightError, match="EXPECTED_CONFIG_DIGEST_INVALID"):
        capacity_identity_preflight(
            registry, [KEY], expected_worker_source_config_digest=digest
        )
    assert registry.calls == []


@pytest.mark.parametrize("variant,expected", [
    ("wrong_provider", "CAPACITY_WORKER_PROVIDER_MISMATCH"),
    ("personal_provider", "CAPACITY_WORKER_PROVIDER_MISMATCH"),
    ("wrong_digest", "CAPACITY_WORKER_CONFIG_MISMATCH"),
    ("local_unbound", "CAPACITY_JOIN_REMOTE_HOST_UNBOUND"),
    ("bad_schema", "CAPACITY_JOIN_PROVIDER_CAPACITY_SCHEMA_INVALID"),
    ("missing_metadata", "CAPACITY_JOIN_JOIN_MISSING"),
])
def test_capacity_refuses_wrong_worker_provider_and_unbound_joins(variant, expected):
    registry = Registry()
    if variant == "wrong_provider":
        registry.quota.provider = "codex"
    elif variant == "personal_provider":
        registry.quota.provider = "byteplus"
    elif variant == "wrong_digest":
        registry.quota.metadata = {"capacity_join": join(digest="d" * 64)}
    elif variant == "local_unbound":
        registry.quota.metadata = {"capacity_join": join(host="local-unbound")}
    elif variant == "bad_schema":
        invalid = join()
        invalid["provider_capacity_schema"] = "unreviewed-capacity"
        registry.quota.metadata = {"capacity_join": invalid}
    else:
        registry.quota.metadata = {}
    with pytest.raises(CommercialPreflightError, match=expected):
        capacity_identity_preflight(
            registry, [KEY], expected_worker_source_config_digest=SOURCE_SHA
        )


def test_duplicate_and_overbound_worker_identity_fails_closed():
    registry = Registry()
    for candidates in ([KEY, KEY], [KEY] * 4, []):
        with pytest.raises(CommercialPreflightError, match="CAPACITY_JOIN"):
            capacity_identity_preflight(
                registry, candidates,
                expected_worker_source_config_digest=SOURCE_SHA
            )
    assert registry.calls == []


def test_two_different_workers_need_real_distinct_owner_joins():
    first = Registry()
    duplicate = copy.deepcopy(first.quota)
    duplicate.worker_id = "worker-modelark-2"

    class DoubleRegistry:
        def get_quota_class(self, worker_id, quota_class):
            return first.quota if worker_id == KEY[0] else duplicate

    with pytest.raises(CommercialPreflightError, match="CAPACITY_JOIN_DUPLICATE_CAPACITY_JOIN"):
        capacity_identity_preflight(
            DoubleRegistry(),
            [KEY, ("worker-modelark-2", KEY[1])],
            expected_worker_source_config_digest=SOURCE_SHA
        )
