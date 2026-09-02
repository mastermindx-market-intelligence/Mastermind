from __future__ import annotations

import json
from pathlib import Path

import pytest

from control_plane.executive_agent_capabilities import (
    CAPABILITY_POLICY_SCHEMA,
    CAPABILITY_POLICY_SCHEMA_V3,
    CAPABILITY_POLICY_SCHEMA_V4,
    CapabilityPolicyError,
    ExecutionCapabilityRegistry,
    app_server_security_config_digest,
    observed_mcp_tool_schema_digest,
)
from control_plane.operator_harness_contract import NativeHelperPolicy
from integrations.mastermind_company_mcp.schemas import (
    SERVER_IDENTITY as COMPANY_DIALOGUE_SERVER_IDENTITY,
    SERVER_VERSION as COMPANY_DIALOGUE_SERVER_VERSION,
    TOOL_SCHEMA_DIGEST as COMPANY_DIALOGUE_TOOL_DIGEST,
    TOOL_SPECS as COMPANY_DIALOGUE_TOOL_SPECS,
)


def _raw_policy() -> dict:
    source = Path("config/executive_agent_capabilities.json")
    return json.loads(source.read_text(encoding="utf-8"))


def _write(tmp_path: Path, value: dict) -> Path:
    path = tmp_path / "capabilities.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def _company_dialogue_fixture_policy() -> dict:
    """Build a non-production registry fixture; no endpoint is checked in."""

    raw = _raw_policy()
    capability_id = "mastermind-company-dialogue-v1"
    raw["mcp_servers"][capability_id] = {
        "config_name": "mastermindCompanyDialogue",
        "transport": "streamable-http",
        "url": "https://company-dialogue.test.invalid/mcp",
        "required": True,
        "auth_status": "unsupported",
        "server_identity": COMPANY_DIALOGUE_SERVER_IDENTITY,
        "server_version": COMPANY_DIALOGUE_SERVER_VERSION,
        "enabled_tools": [spec.name for spec in COMPANY_DIALOGUE_TOOL_SPECS],
        "default_tools_approval_mode": "approve",
        "tool_schema_digest": COMPANY_DIALOGUE_TOOL_DIGEST,
    }
    profile = dict(raw["profiles"]["operator.appserver.readonly.v1"])
    profile["mcp_servers"] = [capability_id]
    raw["profiles"][
        "operator.appserver.readonly.company-dialogue.fixture.v1"
    ] = profile
    return raw


def test_default_policy_is_secret_free_unarmed_and_resolves_closed_profiles():
    registry = ExecutionCapabilityRegistry.load()
    assert registry.lifecycle_authority == "executive_os"
    assert registry.production_armed is False
    assert registry.policy_version == "2026-08-29.browser-b1"
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


def test_company_dialogue_fixture_compiles_through_existing_capability_authority(tmp_path):
    observed_row = {
        "tools": {
            spec.name: {
                "name": spec.name,
                "annotations": spec.annotations,
                "inputSchema": spec.input_schema,
            }
            for spec in COMPANY_DIALOGUE_TOOL_SPECS
        }
    }
    assert observed_mcp_tool_schema_digest(observed_row) == COMPANY_DIALOGUE_TOOL_DIGEST

    raw = _company_dialogue_fixture_policy()
    registry = ExecutionCapabilityRegistry.load(_write(tmp_path, raw))
    profile = registry.resolve(
        "operator.appserver.readonly.company-dialogue.fixture.v1"
    )

    assert registry.production_armed is False
    assert profile.native_helper_policy is NativeHelperPolicy.DISABLED
    assert profile.skills == ()
    assert profile.plugins == ()
    assert profile.mcp_servers == ("mastermind-company-dialogue-v1",)
    assert len(profile.mcp_server_grants) == 1
    grant = profile.mcp_server_grants[0]
    assert grant.server_identity == COMPANY_DIALOGUE_SERVER_IDENTITY
    assert grant.server_version == COMPANY_DIALOGUE_SERVER_VERSION
    assert grant.tool_schema_digest == COMPANY_DIALOGUE_TOOL_DIGEST
    assert grant.enabled_tools == tuple(
        sorted(spec.name for spec in COMPANY_DIALOGUE_TOOL_SPECS)
    )

    manifest = profile.capability_manifest(harness_binary_digest="a" * 64)
    assert len(manifest.required) == 1
    identity = manifest.required[0]
    assert identity.kind == "mcp_server"
    assert identity.name == "mastermindCompanyDialogue"
    assert identity.mcp_server_identity == COMPANY_DIALOGUE_SERVER_IDENTITY
    assert identity.mcp_server_version == COMPANY_DIALOGUE_SERVER_VERSION
    assert identity.tool_schema_digest == COMPANY_DIALOGUE_TOOL_DIGEST
    assert manifest.forbidden == ()
    assert manifest.allowed_ambient == ()

    overrides = "\n".join(profile.app_server_config_overrides())
    assert "company-dialogue.test.invalid/mcp" in overrides
    assert "token" not in overrides.lower()
    assert "secret" not in overrides.lower()
    assert "bearer" not in overrides.lower()

    expected_digest = profile.expected_config_digest
    widened_projection = json.loads(json.dumps(profile.app_server_config_projection()))
    widened_projection["mcp_servers"]["ambient"] = {
        "default_tools_approval_mode": "approve",
        "enabled": True,
        "enabled_tools": ["post_anywhere"],
        "required": False,
        "url": "https://ambient.test.invalid/mcp",
    }
    assert app_server_security_config_digest(widened_projection) != expected_digest

    widened_raw = _company_dialogue_fixture_policy()
    widened_raw["mcp_servers"]["mastermind-company-dialogue-v1"][
        "enabled_tools"
    ].append("generic_slack_post")
    widened = ExecutionCapabilityRegistry.load(_write(tmp_path, widened_raw)).resolve(
        "operator.appserver.readonly.company-dialogue.fixture.v1"
    )
    assert widened.expected_config_digest != expected_digest


def test_production_policy_has_no_company_dialogue_placeholder_endpoint_or_profile():
    raw = _raw_policy()
    rendered = json.dumps(raw, sort_keys=True)
    assert "mastermind-company-dialogue" not in rendered
    assert "mastermindCompanyDialogue" not in rendered
    assert "company-dialogue.test.invalid" not in rendered


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


def test_browser_profile_uses_existing_capability_registry_for_stdio_mcp_and_one_resource(
    tmp_path,
):
    """Dropping either grant must refuse the rich browser Attempt at profile seal."""

    registry = ExecutionCapabilityRegistry.load()
    profile = registry.resolve("operator.browser.local-review.v1")

    assert profile.execution_surface == "codex-app-server"
    assert profile.sandbox_policy == "read-only"
    assert profile.network_policy == "loopback-browser-only"
    assert profile.native_helper_policy is NativeHelperPolicy.DISABLED
    assert profile.mcp_servers == (
        "openai-developer-docs-v1",
        "playwright-worker-browser-b1",
    )
    assert len(profile.resource_grants) == 1
    resource = profile.resource_grants[0]
    assert resource.resource_id == "worker-browser-b1-local"
    assert resource.kind == "browser-devserver"
    assert resource.manifest_path == "config/worker_browser_b1_control_room_devserver.json"
    assert len(resource.manifest_digest) == 64
    assert resource.runtime_manifest_path == (
        "/Volumes/Mastermind/worker-browser-b1/runtime/"
        "worker-browser-b1-install-manifest.json"
    )
    assert resource.runtime_manifest_digest == (
        "ca55da0fbdd1366bfc6fd78612ebe9cc669e45ef5c21b084ad338b50e2d0e49d"
    )

    assert profile.mcp_server_grants[0] == registry.mcp_servers[
        "openai-developer-docs-v1"
    ]
    mcp = profile.mcp_server_grants[1]
    assert mcp.transport == "stdio"
    assert mcp.command == "/usr/bin/python3"
    assert mcp.args[:3] == ("-I", "-S", "-c")
    assert len(mcp.args) == 4
    assert "os.open" in mcp.args[3]
    assert "os.fchdir" in mcp.args[3]
    assert "os.execve" in mcp.args[3]
    assert "runtime/bin/worker-browser-b1-launcher" in mcp.args[3]
    assert "/dev/fd" not in mcp.args[3]
    assert len(
        json.dumps(list(mcp.args), ensure_ascii=True, separators=(",", ":")).encode(
            "utf-8"
        )
    ) <= 4096
    assert mcp.url is None
    assert mcp.server_identity == "playwright"
    assert mcp.server_version == "1.63.0-alpha-2026-08-05"
    assert mcp.tool_schema_digest == (
        "859063beb705b4ed15b0defc2c42533d6bce1a3f18bf02c38f28f2422598fc0b"
    )
    assert mcp.enabled_tools == (
        "browser_click",
        "browser_close",
        "browser_console_messages",
        "browser_fill_form",
        "browser_hover",
        "browser_navigate",
        "browser_network_requests",
        "browser_resize",
        "browser_snapshot",
        "browser_tabs",
        "browser_take_screenshot",
        "browser_wait_for",
    )

    manifest = profile.capability_manifest(harness_binary_digest="a" * 64)
    assert [(item.kind, item.name) for item in manifest.required] == [
        ("mcp_server", "openaiDeveloperDocs"),
        ("mcp_server", "playwrightWorkerBrowser"),
        ("resource", "worker-browser-b1-local"),
    ]
    assert manifest.required[2].resource_contract_digest == resource.grant_digest
    raw = _raw_policy()
    raw["resources"]["worker-browser-b1-local"]["runtime_manifest_digest"] = "1" * 64
    changed = ExecutionCapabilityRegistry.load(_write(tmp_path, raw))
    assert (
        changed.resources["worker-browser-b1-local"].grant_digest
        != resource.grant_digest
    )
    projection = profile.app_server_config_projection()
    assert projection["mcp_servers"]["playwrightWorkerBrowser"] == {
        "args": list(mcp.args),
        "command": "/usr/bin/python3",
        "default_tools_approval_mode": "approve",
        "enabled": True,
        "enabled_tools": list(mcp.enabled_tools),
        "required": True,
    }
    overrides = "\n".join(profile.app_server_config_overrides())
    assert "openaiDeveloperDocs.url" in overrides
    assert "playwrightWorkerBrowser.command" in overrides
    assert "playwrightWorkerBrowser.args" in overrides
    assert "PLAYWRIGHT_MCP" not in overrides


@pytest.mark.parametrize(
    "mutation",
    [
        lambda raw: raw["mcp_servers"]["playwright-worker-browser-b1"].update(
            url="https://example.invalid/mcp"
        ),
        lambda raw: raw["resources"]["worker-browser-b1-local"].update(
            browser_profile="Chairman Chrome"
        ),
        lambda raw: raw["profiles"]["operator.appserver.readonly.v1"].update(
            resources=["worker-browser-b1-local"]
        ),
        lambda raw: raw["resources"]["worker-browser-b1-local"].pop(
            "runtime_manifest_digest"
        ),
        lambda raw: raw["resources"]["worker-browser-b1-local"].update(
            runtime_manifest_digest="A" * 64
        ),
        lambda raw: raw["resources"]["worker-browser-b1-local"].update(
            runtime_manifest_path="runtime/install-manifest.json"
        ),
        lambda raw: raw["mcp_servers"]["playwright-worker-browser-b1"].update(
            command="/usr/bin/python3",
            args=["-I", "-S", "-c", "import os; os.execve('/tmp/unbound', [], {})"],
        ),
        lambda raw: raw["mcp_servers"]["playwright-worker-browser-b1"].update(
            args=["-I", "-S", "-c", "x" * 4097],
        ),
    ],
)
def test_browser_grants_refuse_transport_identity_or_profile_widening(tmp_path, mutation):
    raw = _raw_policy()
    mutation(raw)
    with pytest.raises(CapabilityPolicyError):
        ExecutionCapabilityRegistry.load(_write(tmp_path, raw))


def test_v3_compatibility_digests_and_schema_constants_remain_exact():
    """CAP-S1 package-identity amendment: opt-in V4 must never move V3 identity.

    These are the exact protected-master values verified live before the V4
    dispatch/duplicate-key production edit landed.
    """

    assert CAPABILITY_POLICY_SCHEMA == CAPABILITY_POLICY_SCHEMA_V3
    assert CAPABILITY_POLICY_SCHEMA_V3 == "mastermind.executive_agent_capabilities/v3"
    assert CAPABILITY_POLICY_SCHEMA_V4 == "mastermind.executive_agent_capabilities/v4"

    registry = ExecutionCapabilityRegistry.load()
    assert registry.schema_version == CAPABILITY_POLICY_SCHEMA_V3
    assert registry.capability_packages == {}
    assert registry.policy_digest == (
        "0d025d2728c7dbf73977ac5997e1bd6832be5660ab996ad7e837e50887f7c856"
    )
    assert registry.resolve(
        "operator.appserver.readonly.docs-mcp.native-helper.v1"
    ).profile_digest == (
        "028fce73ff8c4cb8f8ada7b514e89b74fba64b92f29db3780004a360e0995d39"
    )

    for profile in registry.profiles.values():
        assert profile.skill_grants == ()
        assert profile.app_server_config_projection()["skills"] == {"config": None}


@pytest.mark.parametrize(
    "raw_key_path",
    [
        (),
        ("profiles", "operator.appserver.readonly.v1"),
    ],
)
def test_duplicate_json_keys_refuse_for_v3_documents(tmp_path, raw_key_path):
    """Identity amendment §5.1: duplicate JSON keys refuse at every depth,

    including for V3 documents, under the shared object_pairs_hook.
    """

    raw_text = json.dumps(_raw_policy())
    # Build a hand-crafted duplicate: re-serialize the target object with one
    # of its own keys repeated, verbatim, as a second occurrence.
    raw = _raw_policy()
    target = raw
    for key in raw_key_path:
        target = target[key]
    dup_key = next(iter(target))
    dup_value = target[dup_key]

    def _canon(value):
        if isinstance(value, dict):
            return "{" + ",".join(f"{json.dumps(k)}:{_canon(v)}" for k, v in value.items()) + "}"
        if isinstance(value, list):
            return "[" + ",".join(_canon(v) for v in value) + "]"
        return json.dumps(value)

    def _canon_with_dup(value, path):
        if not path:
            assert isinstance(value, dict)
            inner = ",".join(f"{json.dumps(k)}:{_canon(v)}" for k, v in value.items())
            inner += f",{json.dumps(dup_key)}:{_canon(dup_value)}"
            return "{" + inner + "}"
        head, *rest = path
        parts = []
        for k, v in value.items():
            if k == head:
                parts.append(f"{json.dumps(k)}:{_canon_with_dup(v, rest)}")
            else:
                parts.append(f"{json.dumps(k)}:{_canon(v)}")
        return "{" + ",".join(parts) + "}"

    duplicated_text = _canon_with_dup(raw, list(raw_key_path))
    path = tmp_path / "dup.json"
    path.write_text(duplicated_text, encoding="utf-8")
    with pytest.raises(CapabilityPolicyError, match="duplicate JSON key"):
        ExecutionCapabilityRegistry.load(path)
