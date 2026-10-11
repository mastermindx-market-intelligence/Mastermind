from __future__ import annotations

import dataclasses
from types import SimpleNamespace

import pytest

import control_plane.executive_service as executive_service
from control_plane.executive_service import ExecutiveControlService
from control_plane.model_router import ModelRouter


def _service_with_alias(alias_name: str) -> ExecutiveControlService:
    service = object.__new__(ExecutiveControlService)
    service.config = SimpleNamespace(
        coo_model_alias=alias_name,
        coo_operator_model_alias="coo.operator.readonly",
        coo_quota_class="claude-coo",
        coo_default_quota_class="claude-coo-default",
        coo_operator_quota_class="codex-coo-operator",
        proof_base_sha="a" * 40,
        operator_harness_binary_digest="b" * 64,
        operator_harness_version="fixture-v1",
        coo_operator_harness_armed=False,
    )
    return service


def _router_with_native_claude_alias(*, mismatched_surface: bool = False):
    router = ModelRouter.load()
    codex_alias = router.model_aliases["coo.sealed"]
    profile_id = (
        "sealed.worker.write.no-extensions.v1"
        if mismatched_surface
        else "sealed.worker.claude.write.no-extensions.v1"
    )
    profile = router.capability_registry.resolve(profile_id)
    claude_alias = dataclasses.replace(
        codex_alias,
        model_alias="claude.native.fixture",
        provider_alias="anthropic",
        adapter_id="claude-code",
        execution_profile_id=profile.profile_id,
        execution_profile_digest=profile.profile_digest,
    )
    aliases = dict(router.model_aliases)
    aliases[claude_alias.model_alias] = claude_alias
    return SimpleNamespace(
        model_aliases=aliases,
        capability_registry=router.capability_registry,
        policy_version=router.policy_version,
    )


def test_service_accepts_reviewed_native_claude_sealed_alias(monkeypatch):
    router = _router_with_native_claude_alias()
    monkeypatch.setattr(
        executive_service.ModelRouter,
        "load",
        lambda *_args, **_kwargs: router,
    )

    binding = _service_with_alias("claude.native.fixture")._load_coo_execution_binding()

    assert binding["provider"] == "anthropic"
    assert binding["execution_profile_id"] == (
        "sealed.worker.claude.write.no-extensions.v1"
    )
    assert binding["operator_provider"] == "codex"
    assert binding["operator_execution_profile_id"] == (
        "operator.appserver.readonly.docs-mcp.native-helper.v1"
    )


def test_service_refuses_native_claude_alias_on_codex_surface(monkeypatch):
    router = _router_with_native_claude_alias(mismatched_surface=True)
    monkeypatch.setattr(
        executive_service.ModelRouter,
        "load",
        lambda *_args, **_kwargs: router,
    )

    with pytest.raises(ValueError, match="sealed, extension-free"):
        _service_with_alias("claude.native.fixture")._load_coo_execution_binding()
