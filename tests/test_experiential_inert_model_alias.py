"""Source-only Experiential alias must not become an executable Fabric worker.

The canonical ModelRouter owns routes; this spec does not enable an org,
credential, capacity lease, Codex provider realm, or runtime worker.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from control_plane.model_router import ModelRouter, RoutingPolicyError


CONFIG = Path(__file__).resolve().parents[1] / "config" / "executive_worker_routes.json"
ALIAS = "experiential.flash.candidate"


def test_candidate_is_an_inert_identity_not_a_routed_worker():
    router = ModelRouter.load(CONFIG)
    provider = router.providers["experiential"]
    candidate = router.model_aliases[ALIAS]
    assert provider.adapter_id == "codex-cli"
    assert provider.enabled is False and provider.autonomous_allowed is False
    assert candidate.provider_alias == "experiential"
    assert candidate.model == "deepseek-v4.1-flash"
    assert candidate.execution_profile_id == "sealed.worker.write.no-extensions.v1"
    assert candidate.capabilities == ("code", "tests")
    assert candidate.worker_eligible is False
    with pytest.raises(RoutingPolicyError, match="not worker eligible"):
        router.resolve_model_alias(ALIAS)
    for route in router.routes.values():
        for risk in ("routine", "elevated"):
            assert all(
                ALIAS not in tier.model_aliases
                for tier in route[risk]
            )
    assert json.loads(CONFIG.read_text())["production_armed"] is False


@pytest.mark.parametrize("provider_enabled", [False, True])
def test_mere_alias_activation_without_autonomous_provider_refuses(tmp_path, provider_enabled):
    doc = json.loads(CONFIG.read_text())
    doc["model_aliases"][ALIAS]["worker_eligible"] = True
    doc["providers"]["experiential"]["enabled"] = provider_enabled
    assert doc["providers"]["experiential"]["autonomous_allowed"] is False
    target = tmp_path / "candidate.json"
    target.write_text(json.dumps(doc))
    with pytest.raises(RoutingPolicyError, match="requires an enabled autonomous provider"):
        ModelRouter.load(target)


def test_provider_autonomy_cannot_be_enabled_while_provider_disabled(tmp_path):
    doc = json.loads(CONFIG.read_text())
    doc["providers"]["experiential"]["autonomous_allowed"] = True
    target = tmp_path / "candidate.json"
    target.write_text(json.dumps(doc))
    with pytest.raises(RoutingPolicyError, match="cannot allow autonomous use while disabled"):
        ModelRouter.load(target)
