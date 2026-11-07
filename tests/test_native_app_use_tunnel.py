"""Native MCP consumer proof through real Workbench and Runtime admission.

Native input is a fake provider here; the opt-in macOS proof covers actual UI.
No test launches a paid provider or claims a production worker materialization.
"""
from __future__ import annotations

import asyncio
import dataclasses
import os
from pathlib import Path

import pytest

from control_plane.executive_agent_capabilities import (
    ExecutionCapabilityRegistry, McpServerGrant, observed_mcp_tool_schema_digest,
)
from control_plane.operator_harness_contract import (
    OperationId, WorkspaceIdentity, ProcessIdentityObservation, ReconcileObservation,
    ProcessLiveness, ProviderWriterState,
)
from integrations.workbench_action_mcp.tunnel import create_runtime_channel, parse_tunnel_config
from integrations.workbench_action_mcp.worker_admission import (
    WorkerWorkbenchAdmission, project_worker_workbench_lease,
)
from integrations.workbench_app_use.contracts import AppUseRefused, NativeAppGrant
from integrations.workbench_app_use.tunnel import (
    SERVER_NAME, SERVER_VERSION, create_native_tunnel_server, create_worker_native_server, tool_surface,
)
from tests.workbench_action_mcp.test_tunnel import _document
from tests.test_native_app_use_port import Provider, TARGET
from tests.test_workbench_browser_tunnel import _call, _tools, _error_code
from tests.test_ohf_p1b_runtime import _lease, _profile
from tests.test_executive_operator_supervisor import _attestation
from tests.test_worker_browser_admission import _materialize

NAMES = ("native_app_inventory", "native_app_windows", "observe_native_window",
         "prepare_native_click", "run_native_action", "reconcile_native_action")


def grant_for(policy, names=NAMES):
    catalog = {tool.name: tool.model_dump(mode="json") for tool in tool_surface()
               if tool.name in names}
    return McpServerGrant(capability_id="worker-native-app", config_name="native_app_use",
        transport="stdio", url=None, command="/supervisor-owned/native-app-channel",
        args=("--native-policy-sha256", policy.policy_digest),
        required=True, auth_status="unsupported", server_identity=SERVER_NAME,
        server_version=SERVER_VERSION, enabled_tools=names,
        default_tools_approval_mode="approve",
        tool_schema_digest=observed_mcp_tool_schema_digest({"tools": catalog}),
        grant_digest="b" * 64)


def native_policy(runtime, generation=None):
    services = runtime.channel_services
    return NativeAppGrant("mcp:" + "b" * 64, services.host_binding.host_id,
        services.host_binding.boot_session_id, Provider.session_ref,
        generation or runtime.resolve_binding(services.caller, services.project_ref).scope.generation,
        (TARGET.bundle_id,), ("click_element",),
        runtime.resolve_binding(services.caller, services.project_ref).scope.expires_at_ms, (TARGET,))


async def channel(tmp_path):
    document, _, _, _ = _document(tmp_path, tag="native")
    config = parse_tunnel_config(document)
    runtime = await create_runtime_channel(config)
    return runtime, config


async def close(runtime):
    runtime.revoke()
    await runtime.aclose(timeout=5)


def test_real_workbench_mcp_consumer_and_durable_duplicate(tmp_path):
    async def exercise():
        runtime, _ = await channel(tmp_path)
        provider = Provider()
        policy = native_policy(runtime)
        try:
            server = create_native_tunnel_server(runtime, provider=provider,
                native_grant_provider=lambda binding: policy, mcp_grant=grant_for(policy),
                resolve_binding=runtime.resolve_binding)
            assert [tool.name for tool in await _tools(server)] == list(NAMES)
            observation = await _call(server, "observe_native_window", {"target": TARGET.wire()})
            assert not observation.isError
            prepared = await _call(server, "prepare_native_click", {
                "observation_ref": observation.structuredContent["observation_ref"],
                "element_id": "element-1"})
            ref = prepared.structuredContent["action_ref"]
            result = await _call(server, "run_native_action", {"action_ref": ref})
            duplicate = await _call(server, "run_native_action", {"action_ref": ref})
            assert result.structuredContent["effect_state"] == "APPLIED"
            assert result.structuredContent == duplicate.structuredContent
            assert provider.calls == 1
            assert _error_code(await _call(server, "native_app_inventory", {"host": "other"})) \
                == "NATIVE_REQUEST_REFUSED"
            assert _error_code(await _call(server, "prepare_native_text", {})) == "TOOL_NOT_AVAILABLE"
        finally:
            await close(runtime)
    asyncio.run(exercise())


def test_generic_runner_cannot_execute_action_outside_mcp_ceiling(tmp_path):
    async def exercise():
        runtime, _ = await channel(tmp_path)
        provider = Provider()
        policy = native_policy(runtime)
        try:
            full = create_native_tunnel_server(runtime, provider=provider,
                native_grant_provider=lambda binding: policy, mcp_grant=grant_for(policy),
                resolve_binding=runtime.resolve_binding)
            observation = await _call(full, "observe_native_window", {"target": TARGET.wire()})
            prepared = await _call(full, "prepare_native_click", {
                "observation_ref": observation.structuredContent["observation_ref"],
                "element_id": "element-1"})
            narrow = create_native_tunnel_server(runtime, provider=provider,
                native_grant_provider=lambda binding: policy,
                mcp_grant=grant_for(policy, ("run_native_action", "reconcile_native_action")),
                resolve_binding=runtime.resolve_binding)
            result = await _call(narrow, "run_native_action",
                {"action_ref": prepared.structuredContent["action_ref"]})
            assert _error_code(result) == "NATIVE_REQUEST_REFUSED"
            assert provider.calls == 0
        finally:
            await close(runtime)
    asyncio.run(exercise())


@pytest.mark.parametrize("changes", [
    {"tool_schema_digest": "0" * 64}, {"server_identity": "Browser"},
    {"args": ()}, {"transport": "streamable-http"}, {"enabled_tools": ("arbitrary_shell",)},
])
def test_unmaterialized_or_mismatched_native_grant_refuses(tmp_path, changes):
    async def exercise():
        runtime, _ = await channel(tmp_path)
        policy = native_policy(runtime)
        try:
            with pytest.raises(AppUseRefused):
                create_native_tunnel_server(runtime, provider=Provider(),
                    native_grant_provider=lambda binding: policy,
                    mcp_grant=dataclasses.replace(grant_for(policy), **changes),
                    resolve_binding=runtime.resolve_binding)
        finally:
            await close(runtime)
    asyncio.run(exercise())


def test_native_policy_content_is_bound_to_materialized_mcp_digest(tmp_path):
    async def exercise():
        runtime, _ = await channel(tmp_path)
        policy = native_policy(runtime)
        try:
            server = create_native_tunnel_server(runtime, provider=Provider(),
                native_grant_provider=lambda binding: dataclasses.replace(policy,
                    application_ids=("com.other.app",)),
                mcp_grant=grant_for(policy), resolve_binding=runtime.resolve_binding)
            result = await _call(server, "native_app_inventory", {})
            assert _error_code(result) == "NATIVE_PREDISPATCH_REFUSED"
        finally:
            await close(runtime)
    asyncio.run(exercise())


def test_original_runtime_attempt_and_native_domain_materialization(tmp_path):
    async def exercise():
        initial, config = await channel(tmp_path)
        policy = native_policy(initial)
        await close(initial)
        executive, lease = _lease(tmp_path / "executive")
        profile = ExecutionCapabilityRegistry.load().resolve("operator.browser.local-review.v1")
        native_mcp = grant_for(policy)
        profile = dataclasses.replace(profile, profile_id="worker.native.fixture",
            mcp_server_grants=(native_mcp,), resource_grants=(), skills=(), skill_grants=(), plugins=())
        root = Path(config.project_root)
        actual = root.stat()
        requested = dataclasses.replace(_profile(lease),
            harness_kind=profile.execution_surface,
            workspace=WorkspaceIdentity(str(root), "b" * 40, actual.st_dev, actual.st_ino,
                                        actual.st_uid, actual.st_gid),
            network_policy=profile.network_policy, sandbox_policy=profile.sandbox_policy,
            capabilities=profile.capability_manifest(harness_binary_digest="a" * 64),
            expected_config_digest=profile.expected_config_digest)
        executive.operator_harness.seal_operator_harness_attempt(lease.attempt.attempt_id,
            fence_generation=lease.attempt.fence_generation, lease_token=lease.lease_token,
            requested=requested)
        epoch, generation = executive.operator_harness.reserve_start(lease.attempt.attempt_id,
            fence_generation=lease.attempt.fence_generation, lease_token=lease.lease_token,
            operation_id=OperationId("ohf-op:native-fixture-start"))
        executive.operator_harness.bind_start_result(epoch=epoch, generation=generation,
            operation_id=OperationId("ohf-op:native-fixture-start"),
            fence_generation=lease.attempt.fence_generation, lease_token=lease.lease_token,
            provider_session_id="native-test-provider-session",
            process=ProcessIdentityObservation(101, 101, "fixture-start", "fixture-boot"))
        executive.operator_harness.seal_attestation(generation=generation,
            fence_generation=lease.attempt.fence_generation, lease_token=lease.lease_token,
            requested=requested, attestation=_attestation(requested))
        executive.operator_harness.record_provider_writer_observation(generation=generation,
            fence_generation=lease.attempt.fence_generation, lease_token=lease.lease_token,
            observation=ReconcileObservation(ProcessLiveness.ALIVE,
                ProcessIdentityObservation(101, 101, "fixture-start", "fixture-boot"),
                True, ProviderWriterState.HELD))
        projected = project_worker_workbench_lease(config.lease, attempt=lease.attempt,
            epoch=epoch, generation=generation, profile=profile, domain="native-app")
        browser_projection = project_worker_workbench_lease(config.lease, attempt=lease.attempt,
            epoch=epoch, generation=generation, profile=profile, domain="browser")
        assert projected.generation != browser_projection.generation
        run_root = tmp_path / "run-root"
        run_root.mkdir(mode=0o700)
        _materialize(run_root, executive, epoch, generation, requested)
        runtime = await create_runtime_channel(dataclasses.replace(config, lease=projected))
        provider = Provider()
        try:
            admission = WorkerWorkbenchAdmission(executive.store, lease, epoch,
                generation, requested, profile, native_mcp.capability_id, runtime,
                run_root=run_root, expected_owner_uid=os.getuid(), domain="native-app")
            def resolve_policy(binding):
                return dataclasses.replace(policy, control_generation=binding.scope.generation,
                    expires_at_ms=binding.scope.expires_at_ms)
            server = create_worker_native_server(runtime, provider=provider,
                native_grant_provider=resolve_policy, admission=admission)
            result = await _call(server, "native_app_inventory", {})
            assert not result.isError, result
            for path in run_root.rglob("*"):
                if path.is_file():
                    path.unlink()
            refused = await _call(server, "native_app_inventory", {})
            assert refused.isError
            assert provider.calls == 0
        finally:
            await close(runtime)
    asyncio.run(exercise())


def test_reply_serialization_failure_after_execution_is_not_not_applied(tmp_path, monkeypatch):
    import integrations.workbench_app_use.tunnel as module
    async def exercise():
        runtime, _ = await channel(tmp_path)
        provider = Provider()
        policy = native_policy(runtime)
        original = module._result
        try:
            server = create_native_tunnel_server(runtime, provider=provider,
                native_grant_provider=lambda binding: policy, mcp_grant=grant_for(policy),
                resolve_binding=runtime.resolve_binding)
            observation = await _call(server, "observe_native_window", {"target": TARGET.wire()})
            prepared = await _call(server, "prepare_native_click", {
                "observation_ref": observation.structuredContent["observation_ref"],
                "element_id": "element-1"})
            def fail_success(value, *, error=False):
                if value.get("effect_state") == "APPLIED":
                    raise AppUseRefused("reply encoding failed")
                return original(value, error=error)
            monkeypatch.setattr(module, "_result", fail_success)
            result = await _call(server, "run_native_action",
                {"action_ref": prepared.structuredContent["action_ref"]})
            assert result.structuredContent["effect_state"] == "EFFECT_UNKNOWN"
            assert provider.calls == 1
        finally:
            await close(runtime)
    asyncio.run(exercise())
