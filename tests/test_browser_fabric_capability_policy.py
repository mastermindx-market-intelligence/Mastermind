"""An unadmitted fabric browser declaration must never become launch authority."""
from __future__ import annotations

import dataclasses
import json

import pytest

from control_plane.executive_agent_capabilities import (
    CapabilityPolicyError, ExecutionCapabilityRegistry, ResourceGrant,
)

PROFILE = "operator.browser.isolated.v1"
RESOURCE = "worker-browser-isolated"


def _raw():
    from pathlib import Path
    return json.loads(Path("config/executive_agent_capabilities.json").read_text())


def _load(tmp_path, raw):
    path = tmp_path / "policy.json"
    path.write_text(json.dumps(raw))
    return ExecutionCapabilityRegistry.load(path)


def test_pending_declaration_is_distinct_and_unselectable():
    registry = ExecutionCapabilityRegistry.load()
    profile = registry.profiles[PROFILE]
    resource = registry.resources[RESOURCE]
    assert not isinstance(resource, ResourceGrant)
    assert resource.kind == "browser-fabric-pending"
    assert resource.mode == "isolated"
    assert resource.transport == "stdio"
    assert resource.admission == "required"
    assert not profile.enabled
    assert profile.resource_grants == (resource,)
    assert not profile.mcp_server_grants
    with pytest.raises(CapabilityPolicyError, match="disabled"):
        registry.resolve(PROFILE)


@pytest.mark.parametrize("projection", [
    "app_server_config_projection", "app_server_config_overrides",
    "expected_config_digest", "capability_manifest",
])
@pytest.mark.parametrize("rename", [False, True])
def test_direct_profile_access_cannot_compile_pending_authority(projection, rename):
    profile = ExecutionCapabilityRegistry.load().profiles[PROFILE]
    # Even accidental dataclass replacement cannot turn the resource into a grant.
    if rename:
        profile = dataclasses.replace(profile, enabled=True, profile_id="renamed.fixture")
    with pytest.raises(CapabilityPolicyError, match="owner admission"):
        if projection == "expected_config_digest":
            _ = profile.expected_config_digest
        elif projection == "capability_manifest":
            profile.capability_manifest(harness_binary_digest="a" * 64)
        else:
            getattr(profile, projection)()


@pytest.mark.parametrize("field,value", [
    ("enabled", True), ("resources", []),
    ("resources", ["worker-browser-b1-local"]),
    ("mcp_servers", ["playwright-worker-browser-b1"]),
    ("network_policy", "loopback-browser-only"),
    ("execution_surface", "codex-exec"),
    ("write_capable", True), ("skills", ["fixture"]),
    ("plugins", ["fixture"]), ("forbidden", ["fixture"]),
])
def test_pending_profile_cannot_be_enabled_or_widened(tmp_path, field, value):
    raw = _raw()
    raw["profiles"][PROFILE][field] = value
    with pytest.raises(CapabilityPolicyError):
        _load(tmp_path, raw)


@pytest.mark.parametrize("field,value", [
    ("kind", "browser-devserver"), ("mode", "authenticated"),
    ("transport", "streamable-http"), ("admission", "admitted"),
    ("lease_token", "forbidden"), ("command", "/usr/bin/python3"),
    ("runtime_root", "/Volumes/Mastermind/worker-browser-b1/runtime"),
])
def test_pending_resource_has_a_closed_inert_schema(tmp_path, field, value):
    raw = _raw()
    raw["resources"][RESOURCE][field] = value
    with pytest.raises(CapabilityPolicyError):
        _load(tmp_path, raw)


@pytest.mark.parametrize("target", ["operator.appserver.readonly.v1", "operator.browser.local-review.v1", "alias.fixture"])
def test_pending_resource_cannot_be_attached_to_another_profile(tmp_path, target):
    raw = _raw()
    raw["profiles"][target] = dict(raw["profiles"][PROFILE], enabled=False)
    if target == "alias.fixture":
        del raw["profiles"][PROFILE]
    with pytest.raises(CapabilityPolicyError):
        _load(tmp_path, raw)


def test_pending_resource_id_cannot_be_aliased(tmp_path):
    raw = _raw()
    raw["resources"]["alias.fixture"] = raw["resources"].pop(RESOURCE)
    raw["profiles"][PROFILE]["resources"] = ["alias.fixture"]
    with pytest.raises(CapabilityPolicyError):
        _load(tmp_path, raw)


def test_existing_profiles_and_b1_grants_are_unchanged(tmp_path):
    raw = _raw()
    registry = _load(tmp_path, raw)
    del raw["profiles"][PROFILE]
    del raw["resources"][RESOURCE]
    previous = _load(tmp_path, raw)
    assert registry.resources["worker-browser-b1-local"] == previous.resources["worker-browser-b1-local"]
    assert registry.mcp_servers == previous.mcp_servers
    for key, profile in previous.profiles.items():
        assert registry.profiles[key] == profile
    assert registry.policy_digest != previous.policy_digest


@pytest.mark.parametrize("field,choice_set,alternate", [
    ("auth_realm", "_AUTH_REALMS", "future-account"),
    ("approval_policy", "_APPROVAL_POLICIES", "future-approval"),
])
def test_pending_ceiling_survives_future_registry_choices(tmp_path, monkeypatch, field, choice_set, alternate):
    from control_plane import executive_agent_capabilities as policy
    monkeypatch.setattr(policy, choice_set, getattr(policy, choice_set) | {alternate})
    raw = _raw()
    raw["profiles"][PROFILE][field] = alternate
    with pytest.raises(CapabilityPolicyError, match="pending fabric browser profile"):
        _load(tmp_path, raw)
