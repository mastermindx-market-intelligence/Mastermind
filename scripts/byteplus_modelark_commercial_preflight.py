#!/usr/bin/env python3
"""Key-free source qualification and incumbent Capacity-join reader.

This is NOT a provider canary, credential loader, worker enrollment, quota
registry, or admission path.  The credential/Capacity owners can use the
functions when real receipts exist; the CLI never accesses provider state,
private homes, Worker databases, network endpoints, or Executive services.

Use:
    python3 -m scripts.byteplus_modelark_commercial_preflight
"""
from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Sequence
from typing import Any

from control_plane.capacity_economics_projection import (
    BYTEPLUS_COMMERCIAL_MODEL_PINS,
)
from control_plane.codex_provider_realm import (
    BYTEPLUS_MODELARK_COMMERCIAL,
    CANDIDATE_CODEX_PROVIDER_REALMS_SPEC_ONLY,
    REVIEWED_CODEX_PROVIDER_REALMS,
)
from control_plane.executive_capacity_join import (
    CapacityJoinError,
    QuotaIdentityReader,
    read_remote_capacity_joins,
)
from control_plane.model_router import ModelRouter
from control_plane.worker_adapter import adapter_descriptor

SCHEMA = "mastermind.byteplus_modelark_commercial_source_preflight/v1"
CAPACITY_IDENTITY_SCHEMA = "mastermind.byteplus_modelark_capacity_identity_preflight/v1"
PROVIDER = "byteplus-modelark"
PERSONAL_PROVIDER = "byteplus"
PERSONAL_ALIAS = "byteplus.attended"
COMMERCIAL_CODING = "byteplus-modelark.commercial-coding"
COMMERCIAL_ENDPOINT = "https://ark.ap-southeast.bytepluses.com/api/v3"
OWNER_KEY_NAME = "BYTEPLUS_MODELARK_API_KEY"


class CommercialPreflightError(ValueError):
    """A closed, non-secret source/identity qualification refusal."""


def source_preflight(
    router: ModelRouter | None = None, *,
    expected_router_source_sha256: str | None = None,
) -> dict[str, Any]:
    """Canonical, key-free source-only proof; custom input requires an owner pin.

    An in-memory ModelRouter mutation or a byte-identical foreign file does not
    provide the canonical installed policy identity. This never promotes a
    credential, transport, Worker, or Capacity claim.
    """
    supplied = router is not None
    try:
        canonical = ModelRouter.load()
        canonical_bytes = canonical.source_path.read_bytes()
    except (OSError, ValueError) as exc:
        raise CommercialPreflightError("CANONICAL_ROUTER_UNAVAILABLE") from None
    canonical_digest = hashlib.sha256(canonical_bytes).hexdigest()
    if router is None:
        router = canonical
    if type(router) is not ModelRouter:
        raise CommercialPreflightError("ROUTER_NOT_VERIFIED")
    if supplied:
        if (
            type(expected_router_source_sha256) is not str
            or re.fullmatch(r"[0-9a-f]{64}", expected_router_source_sha256) is None
            or expected_router_source_sha256 != canonical_digest
        ):
            raise CommercialPreflightError("CUSTOM_ROUTER_SOURCE_NOT_OWNER_PINNED")
    if (
        router.source_path != canonical.source_path
        or router.policy_version != canonical.policy_version
        or router.providers != canonical.providers
        or router.model_aliases != canonical.model_aliases
        or router.routes != canonical.routes
        or router.capability_registry.policy_version
            != canonical.capability_registry.policy_version
        or router.capability_registry.policy_digest
            != canonical.capability_registry.policy_digest
        or router.capability_registry.source_path
            != canonical.capability_registry.source_path
    ):
        raise CommercialPreflightError("ROUTER_SOURCE_OR_IN_MEMORY_DRIFT")

    commercial = router.providers.get(PROVIDER)
    personal = router.providers.get(PERSONAL_PROVIDER)
    personal_alias = router.model_aliases.get(PERSONAL_ALIAS)
    realm = BYTEPLUS_MODELARK_COMMERCIAL
    if (
        realm.provider_alias != PROVIDER
        or realm.base_url != COMMERCIAL_ENDPOINT
        or realm.env_key != OWNER_KEY_NAME
        or realm.wire_api != "responses"
        or realm.interactive_subscription_only is not False
        or realm.commercial_api_only is not True
        or realm.realm_id != "byteplus-modelark-commercial"
        or realm.request_max_retries != 0
        or realm.stream_max_retries != 0
        or CANDIDATE_CODEX_PROVIDER_REALMS_SPEC_ONLY.get(realm.realm_id) is not realm
        or realm.realm_id in REVIEWED_CODEX_PROVIDER_REALMS
    ):
        raise CommercialPreflightError("COMMERCIAL_REALM_NOT_SOURCE_HELD")
    descriptor = adapter_descriptor("codex-cli")
    if (
        not descriptor.implemented
        or commercial is None
        or commercial.adapter_id != "codex-cli"
        or commercial.enabled is not False
        or commercial.autonomous_allowed is not False
        or personal is None
        or personal.enabled is not False
        or personal.autonomous_allowed is not False
        or personal_alias is None
        or personal_alias.worker_eligible is not False
        or personal_alias.provider_alias != PERSONAL_PROVIDER
    ):
        raise CommercialPreflightError("PROVIDER_CATALOG_NOT_SOURCE_HELD")

    models = dict(BYTEPLUS_COMMERCIAL_MODEL_PINS)
    for alias_name, model_name in models.items():
        alias = router.model_aliases.get(alias_name)
        if (
            alias is None
            or alias.provider_alias != PROVIDER
            or alias.adapter_id != "codex-cli"
            or alias.worker_eligible is not False
            or alias.model != model_name
            or not {"code", "tests"}.issubset(alias.capabilities)
        ):
            raise CommercialPreflightError("COMMERCIAL_MODEL_ALIAS_NOT_SOURCE_HELD")

    if any(
        alias in tier.model_aliases
        for work_routes in router.routes.values()
        for risk in ("routine", "elevated")
        for tier in work_routes[risk]
        for alias in (*models, PERSONAL_ALIAS)
    ):
        raise CommercialPreflightError("SOURCE_CANDIDATE_LEAKED_INTO_LIVE_TIER")

    # This canonical digest is diagnostic for SOURCE_ONLY; the owner must
    # independently approve an installed digest before runtime promotion.
    raw = canonical_bytes
    return {
        "schema": SCHEMA,
        "evidence_scope": "SOURCE_ONLY",
        "provider_alias": PROVIDER,
        "realm_id": realm.realm_id,
        "endpoint": realm.base_url,
        "wire_api": realm.wire_api,
        "owner_secret_env_name": realm.env_key,
        # This is an inert Codex transport configuration, not a rendered
        # command containing a key. Only the existing owner may supply it.
        "codex_config_overrides_key_free": list(realm.config_overrides()),
        "model_ids_by_alias": models,
        "router_source_sha256": hashlib.sha256(raw).hexdigest(),
        "model_router_source_held": True,
        "commercial_realm_source_held": True,
        "personal_plan_isolated": True,
        "credential_read": False,
        "provider_network_called": False,
        "provider_account_verified": False,
        "model_activation_verified": False,
        "review_accepted": False,
        "issuer_usage_verified": False,
        "quota_known": False,
        "worker_registered": False,
        "capacity_identity_read": False,
        "claim_time_capacity_verified": False,
        "production_start_authorized": False,
        "next_owner_actions": [
            "source integrator: validate the exact composed source, satisfy required CI and applicable protected release rules",
            "credential_owner: verify private commercial ModelArk account, region and one activated Flash model ID",
            "credential_owner: bind BYTEPLUS_MODELARK_API_KEY only via existing private provider-home loader",
            "credential_owner: one authorized bounded Responses transport canary with actual served model and provider-origin usage/debit evidence",
            "ProviderRealm owner: qualify exact transport only from authentic canary evidence; registry membership alone never grants START",
            "Capacity owner: bind the distinct commercial account and fresh issuer quota to the incumbent admission and settlement path",
            "consumer integrator: prove one bounded admitted turn and its terminal model/account/usage receipts; application HTTP and Executive Worker admission are distinct",
            "release owner: select the verified immutable generation through existing release controls; source preflight never authorizes production",
        ],
    }


def capacity_identity_preflight(
    registry: QuotaIdentityReader,
    candidate_keys: Sequence[tuple[str, str]],
    *,
    expected_worker_source_config_digest: str,
) -> dict[str, Any]:
    """Read only canonical quota identities; never assert headroom/admission.

    Owner-supplied expected digest MUST come from its independently verified
    installed Worker config. This argument and returned rows are NOT proof of
    source/install equality by themselves.
    """
    if (
        type(expected_worker_source_config_digest) is not str
        or len(expected_worker_source_config_digest) != 64
        or any(ch not in "0123456789abcdef"
               for ch in expected_worker_source_config_digest)
    ):
        raise CommercialPreflightError("EXPECTED_CONFIG_DIGEST_INVALID")
    try:
        rows = read_remote_capacity_joins(registry, candidate_keys)
    except CapacityJoinError as exc:
        raise CommercialPreflightError("CAPACITY_JOIN_" + exc.code) from None
    for row in rows:
        if row.provider != PROVIDER:
            raise CommercialPreflightError("CAPACITY_WORKER_PROVIDER_MISMATCH")
        if row.capacity_join.worker_source_config_digest != expected_worker_source_config_digest:
            raise CommercialPreflightError("CAPACITY_WORKER_CONFIG_MISMATCH")
    return {
        "schema": CAPACITY_IDENTITY_SCHEMA,
        "evidence_scope": "CANONICAL_REGISTRY_IDENTITY_READ_ONLY",
        "provider_alias": PROVIDER,
        "capacity_join_identity_validated": True,
        "candidate_count": len(rows),
        "candidates": [row.to_dict() for row in rows],
        "credential_read": False,
        "provider_network_called": False,
        "provider_origin_quota_verified": False,
        "claim_time_capacity_verified": False,
        "production_start_authorized": False,
        "next_action": "Provider Control verifies current account/region quota and Executive revalidates its owned claim; this identity read is not admission",
    }


def main() -> None:
    print(json.dumps(source_preflight(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
