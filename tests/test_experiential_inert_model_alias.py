"""Disabled Experiential provider alias lives only in canonical ModelRouter.

This module must never infer provider entitlement or register a live worker.
"""
from __future__ import annotations

import json

import pytest

from control_plane.model_router import (
    DEFAULT_POLICY_PATH,
    ModelRouter,
    RoutingPolicyError,
    WorkRequest,
)

ALIAS = "experiential.flash.candidate"


def _policy():
    return json.loads(DEFAULT_POLICY_PATH.read_text(encoding="utf-8"))


def test_experiential_candidate_is_inert_but_identity_binds_exact_model():
    router = ModelRouter.load()
    provider = router.providers["experiential"]
    alias = router.model_aliases[ALIAS]
    assert provider.adapter_id == "codex-cli"
    assert not provider.enabled and not provider.autonomous_allowed
    assert alias.provider_alias == "experiential"
    assert alias.model == "deepseek-v4.1-flash"
    assert alias.execution_profile_id == "sealed.worker.write.no-extensions.v1"
    assert alias.capabilities == ("code", "tests")
    assert alias.worker_eligible is False
    assert _policy()["production_armed"] is False


@pytest.mark.parametrize("kind", ("implementation", "mechanical", "research", "review", "tests"))
def test_experiential_candidate_is_not_in_any_route(kind):
    raw = _policy()
    tiers = raw["routes"][kind]
    for risk in ("routine", "elevated"):
        for tier in tiers[risk]:
            assert ALIAS not in tier["model_aliases"]
    decision = ModelRouter.load().route(WorkRequest(task_kind=kind))
    assert all(ALIAS not in tier.model_aliases for tier in decision.suitability_tiers)


def test_attempt_to_enable_worker_alias_without_provider_capacity_is_refused(tmp_path):
    raw = _policy()
    raw["model_aliases"][ALIAS]["worker_eligible"] = True
    path = tmp_path / "bad_worker_eligible.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(RoutingPolicyError, match="requires an enabled autonomous provider"):
        ModelRouter.load(path)


def test_attempt_to_route_unproven_alias_is_refused(tmp_path):
    raw = _policy()
    raw["routes"]["implementation"]["routine"][0]["model_aliases"].append(ALIAS)
    path = tmp_path / "bad_route.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(RoutingPolicyError, match="ineligible"):
        ModelRouter.load(path)
