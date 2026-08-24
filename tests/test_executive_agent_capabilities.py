from __future__ import annotations

import json
from pathlib import Path

import pytest

from control_plane.executive_agent_capabilities import (
    CapabilityPolicyError,
    ExecutionCapabilityRegistry,
    app_server_security_config_digest,
    observed_mcp_tool_schema_digest,
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
    assert registry.policy_version == "2026-08-24.g4"
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

    docs = registry.resolve("operator.appserver.readonly.docs-mcp.v1")
    assert docs.required_capability_names == ("openaiDeveloperDocs",)
    assert docs.mcp_servers == ("openai-developer-docs-v1",)
    assert len(docs.expected_config_digest) == 64
    assert docs.plugins == ()

    helper = registry.resolve(
        "operator.appserver.readonly.docs-mcp.native-helper.v1"
    )
    assert helper.native_helper_policy is NativeHelperPolicy.PARENT_READ_ONLY_CEILING
    assert helper.native_helper is not None
    assert helper.native_helper.max_concurrent_helpers == 1
    assert helper.native_helper.max_depth == 1
    assert helper.native_helper.max_runtime_seconds == 60
    assert helper.native_helper.hide_spawn_agent_metadata is True
    assert helper.mcp_servers == ("openai-developer-docs-v1",)


def test_profile_compiles_exact_mcp_manifest_and_secret_free_config():
    profile = ExecutionCapabilityRegistry.load().resolve(
        "operator.appserver.readonly.docs-mcp.v1"
    )
    digest = "a" * 64
    manifest = profile.capability_manifest(harness_binary_digest=digest)
    assert [(item.kind, item.name) for item in manifest.required] == [
        ("mcp_server", "openaiDeveloperDocs"),
    ]
    assert all(item.harness_binary_digest == digest for item in manifest.required)
    assert manifest.required[0].mcp_server_identity == "openai-docs-mcp"
    assert manifest.required[0].mcp_server_version == "1.0.0"
    assert manifest.required[0].mcp_auth_status == "unsupported"
    assert manifest.required[0].tool_schema_digest == (
        "9c6e56942336e507f7fb8e3cb781288c40028b2284c2b2d629e262521d66f8e7"
    )
    assert manifest.forbidden == ()
    assert manifest.allowed_ambient == ()
    assert manifest.unclassified_policy == "fail_closed_on_write"
    overrides = profile.app_server_config_overrides()
    rendered = "\n".join(overrides)
    assert "mcp_servers={}" in overrides
    assert "plugins={}" in overrides
    assert "agents.enabled=false" in overrides
    assert "features.plugins=false" in overrides
    assert "openaiDeveloperDocs.enabled_tools" in rendered
    assert "token" not in rendered.lower()
    assert "secret" not in rendered.lower()


def test_docs_mcp_schema_and_security_projection_are_exact_and_drift_sensitive():
    profile = ExecutionCapabilityRegistry.load().resolve(
        "operator.appserver.readonly.docs-mcp.v1"
    )
    observed_row = {
        "tools": {
            "fetch_openai_doc": {
                "name": "fetch_openai_doc",
                "annotations": {
                    "destructiveHint": False,
                    "readOnlyHint": True,
                },
                "inputSchema": {
                    "$schema": "http://json-schema.org/draft-07/schema#",
                    "properties": {
                        "anchor": {"type": "string"},
                        "url": {"minLength": 1, "type": "string"},
                    },
                    "required": ["url"],
                    "type": "object",
                },
            },
            "search_openai_docs": {
                "name": "search_openai_docs",
                "annotations": {
                    "destructiveHint": False,
                    "readOnlyHint": True,
                },
                "inputSchema": {
                    "$schema": "http://json-schema.org/draft-07/schema#",
                    "properties": {
                        "cursor": {"type": "string"},
                        "limit": {"maximum": 50, "minimum": 1, "type": "integer"},
                        "query": {"minLength": 1, "type": "string"},
                    },
                    "required": ["query"],
                    "type": "object",
                },
            },
        }
    }
    expected_tool_digest = profile.mcp_server_grants[0].tool_schema_digest
    assert observed_mcp_tool_schema_digest(observed_row) == expected_tool_digest

    widened_row = json.loads(json.dumps(observed_row))
    widened_row["tools"]["search_openai_docs"]["annotations"][
        "destructiveHint"
    ] = True
    assert observed_mcp_tool_schema_digest(widened_row) != expected_tool_digest

    expected_projection = profile.app_server_config_projection()
    assert app_server_security_config_digest(expected_projection) == (
        profile.expected_config_digest
    )
    widened_projection = json.loads(json.dumps(expected_projection))
    widened_projection["features"]["plugins"] = True
    assert app_server_security_config_digest(widened_projection) != (
        profile.expected_config_digest
    )
    widened_projection = json.loads(json.dumps(expected_projection))
    widened_projection["mcp_servers"]["ambient"] = {
        "default_tools_approval_mode": "approve",
        "enabled": True,
        "enabled_tools": ["write"],
        "required": False,
        "url": "https://example.invalid/mcp",
    }
    assert app_server_security_config_digest(widened_projection) != (
        profile.expected_config_digest
    )


def test_native_helper_profile_compiles_a_hidden_depth_one_parent_ceiling():
    profile = ExecutionCapabilityRegistry.load().resolve(
        "operator.appserver.readonly.docs-mcp.native-helper.v1"
    )
    helper = profile.native_helper
    assert helper is not None
    projection = profile.app_server_config_projection()
    assert projection["agents"] == {
        "default_subagent_model": "gpt-5.6-sol",
        "default_subagent_reasoning_effort": "xhigh",
        "enabled": True,
        "interrupt_message": None,
        "job_max_runtime_seconds": 60,
        "max_concurrent_threads_per_session": 1,
        "max_depth": 1,
    }
    assert projection["features"]["multi_agent"] is False
    assert projection["features"]["multi_agent_v2"] == {
        "enabled": True,
        "hide_spawn_agent_metadata": True,
        "max_concurrent_threads_per_session": 2,
        "non_code_mode_only": False,
    }
    overrides = "\n".join(profile.app_server_config_overrides())
    assert "hide_spawn_agent_metadata=true" in overrides
    assert "agents.max_depth=1" in overrides
    assert "agents.job_max_runtime_seconds=60" in overrides
    assert "agents.max_concurrent_threads_per_session=1" in overrides
    assert "features.plugins=false" in overrides
    assert "openaiDeveloperDocs.enabled_tools" in overrides

    widened = json.loads(json.dumps(projection))
    widened["agents"]["max_depth"] = 2
    assert app_server_security_config_digest(widened) != profile.expected_config_digest
    widened = json.loads(json.dumps(projection))
    widened["features"]["multi_agent_v2"]["hide_spawn_agent_metadata"] = False
    assert app_server_security_config_digest(widened) != profile.expected_config_digest


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda raw: raw.update(production_armed=True), "production_armed=false"),
        (
            lambda raw: raw["profiles"]["sealed.worker.write.no-extensions.v1"].update(
                mcp_servers=["openai-developer-docs-v1"]
            ),
            "cannot grant MCP/plugins",
        ),
        (
            lambda raw: raw["profiles"]["operator.appserver.readonly.v1"].update(
                native_helper_policy="parent_read_only_ceiling"
            ),
            "without an exact ceiling",
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


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda raw: raw["mcp_servers"]["openai-developer-docs-v1"].update(
                url="http://developers.openai.com/mcp"
            ),
            "HTTPS",
        ),
        (
            lambda raw: raw["mcp_servers"]["openai-developer-docs-v1"].update(
                required=False
            ),
            "fail startup closed",
        ),
        (
            lambda raw: raw["mcp_servers"]["openai-developer-docs-v1"].update(
                tool_schema_digest="not-a-digest"
            ),
            "lowercase SHA-256",
        ),
        (
            lambda raw: raw.update(plugins={"ambient": {}}),
            "installed-bundle attestation",
        ),
    ],
)
def test_mcp_and_plugin_policy_widening_fails_closed(tmp_path, mutate, message):
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
