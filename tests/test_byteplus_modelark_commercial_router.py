"""Commercial API candidate must not alter first-lawful-tier live routing."""
import json
from pathlib import Path

import pytest

from control_plane.codex_provider_realm import BYTEPLUS_MODELARK_COMMERCIAL
from control_plane.model_router import ModelRouter, RoutingPolicyError

_ROOT = Path(__file__).resolve().parents[1]
_POLICY = _ROOT / "config" / "executive_worker_routes.json"


def test_commercial_modelark_catalog_is_separate_and_inert():
    raw=json.loads(_POLICY.read_text())
    assert raw["production_armed"] is False
    personal=raw["providers"]["byteplus"]
    commercial=raw["providers"]["byteplus-modelark"]
    assert personal["adapter_id"] == "attended-fabric"
    assert personal["enabled"] is False
    assert personal["autonomous_allowed"] is False
    assert commercial == {
        "adapter_id":"codex-cli",
        "enabled":False,
        "autonomous_allowed":False,
    }
    candidate=raw["model_aliases"]["byteplus-modelark.commercial-coding"]
    assert candidate["provider_alias"] == "byteplus-modelark"
    assert candidate["worker_eligible"] is False
    assert candidate["model"] == "dola-seed-2-1-turbo-260628"
    assert BYTEPLUS_MODELARK_COMMERCIAL.base_url.endswith("/api/v3")
    assert not BYTEPLUS_MODELARK_COMMERCIAL.base_url.endswith("/api/coding/v3")
    for route in raw["routes"].values():
        for risk in ("routine","elevated"):
            for tier in route[risk]:
                assert "byteplus-modelark.commercial-coding" not in tier["model_aliases"]


def test_commercial_candidate_validates_but_cannot_route():
    router=ModelRouter.load()
    commercial=router.providers["byteplus-modelark"]
    assert commercial.enabled is False
    assert commercial.autonomous_allowed is False
    with pytest.raises(RoutingPolicyError,match="not worker eligible"):
        router.resolve_model_alias("byteplus-modelark.commercial-coding")
    with pytest.raises(RoutingPolicyError,match="not worker eligible"):
        router.resolve_model_alias("byteplus.attended")
