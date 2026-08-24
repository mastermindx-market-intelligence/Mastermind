from __future__ import annotations

import json
from pathlib import Path

import pytest

from control_plane.executive_agent_capabilities import (
    CapabilityPolicyError,
    ExecutionCapabilityRegistry,
)
from control_plane.operator_harness_contract import NativeHelperPolicy


def _raw_policy() -> dict:
    source = Path("config/executive_agent_capabilities.json")
    return json.loads(source.read_text(encoding="utf-8"))


def _write(tmp_path: Path, value: dict) -> Path:
    path = tmp_path / "capabilities.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def test_default_policy_is_secret_free_unarmed_and_resolves_closed_profiles():
    registry = ExecutionCapabilityRegistry.load()
    assert registry.lifecycle_authority == "executive_os"
    assert registry.production_armed is False
    assert registry.policy_version == "2026-08-24.g0"
    assert len(registry.policy_digest) == 64

    sealed = registry.resolve("sealed.worker.write.no-extensions.v1")
    assert sealed.execution_surface == "codex-exec"
    assert sealed.write_capable is True
    assert sealed.native_helper_policy is NativeHelperPolicy.DISABLED
    assert sealed.required_capability_names == ()

    operator = registry.resolve("operator.appserver.readonly.v1")
    assert operator.execution_surface == "codex-app-server"
    assert operator.write_capable is False
    assert operator.sandbox_policy == "read-only"
    assert operator.required_capability_names == ()


def test_profile_compiles_exact_mcp_plugin_and_skill_manifest(tmp_path):
    raw = _raw_policy()
    raw["profiles"]["operator.tools.fixture.v1"] = {
        "enabled": True,
        "execution_surface": "codex-app-server",
        "auth_realm": "dedicated-worker-account",
        "sandbox_policy": "read-only",
        "approval_policy": "never",
        "network_policy": "disabled",
        "write_capable": False,
        "native_helper_policy": "disabled",
        "skills": ["mastermind-read"],
        "mcp_servers": ["executive-readonly"],
        "plugins": ["company-context"],
        "forbidden": ["browser-use"],
    }
    profile = ExecutionCapabilityRegistry.load(_write(tmp_path, raw)).resolve(
        "operator.tools.fixture.v1"
    )
    digest = "a" * 64
    manifest = profile.capability_manifest(harness_binary_digest=digest)
    assert [(item.kind, item.name) for item in manifest.required] == [
        ("skill", "mastermind-read"),
        ("mcp_server", "executive-readonly"),
        ("plugin", "company-context"),
    ]
    assert all(item.harness_binary_digest == digest for item in manifest.required)
    assert manifest.required[1].mcp_server_identity == "executive-readonly"
    assert manifest.forbidden == ("browser-use",)
    assert manifest.allowed_ambient == ()
    assert manifest.unclassified_policy == "fail_closed_on_write"


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda raw: raw.update(production_armed=True), "production_armed=false"),
        (
            lambda raw: raw["profiles"]["sealed.worker.write.no-extensions.v1"].update(
                mcp_servers=["unexpected"]
            ),
            "cannot grant MCP/plugins",
        ),
        (
            lambda raw: raw["profiles"]["operator.appserver.readonly.v1"].update(
                native_helper_policy="parent_read_only_ceiling"
            ),
            "cannot enable native helpers",
        ),
        (
            lambda raw: raw["profiles"]["operator.appserver.readonly.v1"].update(
                skills=["same"], forbidden=["same"]
            ),
            "both requires and forbids",
        ),
    ],
)
def test_policy_rejects_arming_or_ambient_authority_widening(tmp_path, mutate, message):
    raw = _raw_policy()
    mutate(raw)
    with pytest.raises(CapabilityPolicyError, match=message):
        ExecutionCapabilityRegistry.load(_write(tmp_path, raw))


def test_manifest_requires_exact_binary_digest():
    profile = ExecutionCapabilityRegistry.load().resolve(
        "operator.appserver.readonly.v1"
    )
    with pytest.raises(CapabilityPolicyError, match="lowercase SHA-256"):
        profile.capability_manifest(harness_binary_digest="not-a-digest")
