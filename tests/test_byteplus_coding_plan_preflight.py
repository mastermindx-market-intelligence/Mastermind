"""Offline BytePlus preflight does not start a process or mint admission."""
from __future__ import annotations

import dataclasses
import json
import os
from types import SimpleNamespace
from pathlib import Path
import socket
import subprocess
import sys

import pytest

from scripts.byteplus_coding_plan_preflight import source_preflight
from control_plane.subscription_harness_bindings import get_binding
from control_plane.subscription_canary_admission import (
    CanaryAdmissionError, seal_subscription_canary_admission,
)


def test_source_preflight_refuses_any_real_network_or_subprocess(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("source preflight attempted process/network execution")

    with monkeypatch.context() as p:
        p.setattr(subprocess, "run", forbidden)
        p.setattr(subprocess, "Popen", forbidden)
        p.setattr(socket, "socket", forbidden)
        row = source_preflight()

    assert row["schema"] == "mastermind.byteplus_coding_plan_source_preflight/v1"
    assert row["evidence_scope"] == "SOURCE_ONLY"
    assert row["endpoint"] == "https://ark.ap-southeast.bytepluses.com/api/coding"
    assert row["canary_preparation_only"] is True
    assert row["canary_start_authorized"] is False
    assert row["autonomous_start_authorized"] is False
    assert row["credential_read"] is False
    assert row["quota_debit_observed"] is False
    assert row["actual_concurrent_worker_limit"] is None
    assert row["estimated_startable_jobs"] is None
    assert row["individual_supported_tool_mode_statically_allowed"] is True
    assert "implementation_not_built" in row["canary_source_blockers"]
    assert "provider_realm_enrolled" in row["canary_source_blockers"]
    assert "capacity_known" in row["canary_source_blockers"]
    assert "source_policy_disarmed" in row["production_source_blockers"]
    assert "implementation_not_proven_live" in row["production_source_blockers"]
    assert not any(
        marker in json.dumps(row).lower()
        for marker in ("anthropic_auth_token", "credential_value", "api_key")
    )


def test_preflight_matches_every_current_specialist_role():
    doc = source_preflight()
    assert doc["models_by_source_role"] == {
        "adversarial_review": "deepseek-v4-pro",
        "backend_coding": "deepseek-v4.1-flash",
        "fast": "dola-seed-2.0-lite",
        "frontend_visual": "dola-seed-2.0-code",
        "hard": "dola-seed-2.0-pro",
        "routine": "glm-5.3-flash",
        "subagent": "glm-5.3-flash",
    }
    assert get_binding(doc["binding_id"]).implementation_state == "SPEC_ONLY"


@pytest.mark.parametrize("kwargs", [
    {},
    {"adapter_implemented": True, "provider_realm_enrolled": True,
     "capacity_known": True, "real_canary_passed": True,
     "usage_policy_satisfied": True},
    {"capacity_fact": {"worker_id": "fake"},
     "realm_receipt": {"enrollment_state": "enrolled"}},
])
def test_unowned_or_caller_boolean_capacity_never_seals_admission(kwargs):
    with pytest.raises(CanaryAdmissionError):
        seal_subscription_canary_admission(**kwargs)



@pytest.mark.parametrize("missing", ["provider", "alias", "route"])
def test_missing_router_catalog_fails_with_typed_source_diagnostic(monkeypatch, missing):
    from control_plane.model_router import ModelRouter

    original = ModelRouter.load()
    providers = dict(original.providers)
    aliases = dict(original.model_aliases)
    routes = {key: dict(value) for key, value in original.routes.items()}
    if missing == "provider":
        providers.pop("byteplus")
    elif missing == "alias":
        aliases.pop("byteplus.attended")
    else:
        routes["implementation"].pop("routine")
    fake = SimpleNamespace(providers=providers, model_aliases=aliases, routes=routes)
    with monkeypatch.context() as patcher:
        patcher.setattr(ModelRouter, "load", classmethod(lambda cls: fake))
        with pytest.raises(RuntimeError, match="BytePlus reviewed router|BytePlus router suitability"):
            source_preflight()


def test_missing_reviewed_model_role_fails_closed(monkeypatch):
    import scripts.byteplus_coding_plan_preflight as preflight

    original_get = preflight.get_profile

    def incomplete(profile_id):
        profile = original_get(profile_id)
        models = dict(profile.models)
        models.pop("backend_coding")
        return dataclasses.replace(profile, models=models)

    with monkeypatch.context() as patcher:
        patcher.setattr(preflight, "get_profile", incomplete)
        with pytest.raises(RuntimeError, match="model class is missing"):
            source_preflight()


@pytest.mark.parametrize("alias", ["ark.payg", "modelark.claude", "volcengine.model"])
def test_new_byteplus_branded_alias_requires_canonical_router_admission(alias):
    from control_plane.model_router import ModelRouter, RoutingPolicyError

    with pytest.raises(RoutingPolicyError, match="unknown model alias"):
        ModelRouter.load().resolve_model_alias(alias)


def test_preflight_cli_emits_closed_json_without_activation():
    root = Path(__file__).resolve().parents[1]
    proc = subprocess.run(
        [sys.executable, "-m", "scripts.byteplus_coding_plan_preflight"],
        cwd=root, capture_output=True, text=True, check=True,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        timeout=15,
    )
    assert proc.stderr == ""
    body = json.loads(proc.stdout)
    assert body["evidence_scope"] == "SOURCE_ONLY"
    assert body["canary_start_authorized"] is False
    assert body["autonomous_start_authorized"] is False
    assert body["quota_debit_observed"] is False
