"""Real SQLite lease/generation checks, with no provider or browser launch."""
from __future__ import annotations

import asyncio
import dataclasses
import importlib
from pathlib import Path

import pytest

from control_plane.executive_agent_capabilities import ExecutionCapabilityRegistry
from control_plane.operator_harness_contract import (
    OperationId, WorkspaceIdentity, ProcessIdentityObservation, ReconcileObservation,
    ProcessLiveness, ProviderWriterState,
)
from integrations.workbench_action_mcp.tunnel import create_runtime_channel
from integrations.workbench_browser_mcp.tunnel import load_browser_tunnel_config
from tests.test_ohf_p1b_runtime import _lease, _profile
from tests.test_executive_operator_supervisor import _attestation
from tests.test_workbench_browser_tunnel import _config_file, _call, _error_code, _tools
from tests.test_workbench_browser_worker_grant import _grant


def _api():
    return importlib.import_module("integrations.workbench_browser_mcp.worker")


def _setup(tmp_path):
    api = _api()
    path, _, _ = _config_file(tmp_path)
    config = load_browser_tunnel_config(str(path))
    executive, lease = _lease(tmp_path / "executive")
    profile = ExecutionCapabilityRegistry.load().resolve("operator.browser.local-review.v1")
    profile = dataclasses.replace(profile, profile_id="worker.browser.fixture",
        mcp_server_grants=(_grant(config),), resource_grants=(), skills=(),
        skill_grants=(), plugins=())
    root = Path(config.action.project_root)
    stat = root.stat()
    requested = dataclasses.replace(_profile(lease),
        harness_kind=profile.execution_surface,
        workspace=WorkspaceIdentity(str(root), "b" * 40, stat.st_dev, stat.st_ino,
                                    stat.st_uid, stat.st_gid),
        network_policy=profile.network_policy, sandbox_policy=profile.sandbox_policy,
        capabilities=profile.capability_manifest(harness_binary_digest="a" * 64),
        expected_config_digest=profile.expected_config_digest)
    executive.operator_harness.seal_operator_harness_attempt(lease.attempt.attempt_id,
        fence_generation=lease.attempt.fence_generation, lease_token=lease.lease_token,
        requested=requested)
    epoch, generation = executive.operator_harness.reserve_start(lease.attempt.attempt_id,
        fence_generation=lease.attempt.fence_generation, lease_token=lease.lease_token,
        operation_id=OperationId("ohf-op:browser-fixture-start"))
    executive.operator_harness.bind_start_result(epoch=epoch, generation=generation,
        operation_id=OperationId("ohf-op:browser-fixture-start"),
        fence_generation=lease.attempt.fence_generation, lease_token=lease.lease_token,
        provider_session_id="browser-test-provider-session",
        process=ProcessIdentityObservation(101, 101, "fixture-start", "fixture-boot"))
    executive.operator_harness.seal_attestation(generation=generation,
        fence_generation=lease.attempt.fence_generation, lease_token=lease.lease_token,
        requested=requested, attestation=_attestation(requested))
    executive.operator_harness.record_provider_writer_observation(generation=generation,
        fence_generation=lease.attempt.fence_generation, lease_token=lease.lease_token,
        observation=ReconcileObservation(ProcessLiveness.ALIVE,
            ProcessIdentityObservation(101, 101, "fixture-start", "fixture-boot"),
            True, ProviderWriterState.HELD))
    action = dataclasses.replace(config.action, lease=api.project_worker_browser_lease(
        config.action.lease, attempt=lease.attempt, epoch=epoch,
        generation=generation, profile=profile))
    return api, executive, lease, epoch, generation, profile, requested, dataclasses.replace(config, action=action)


def test_real_attempt_prepares_browser_resource_without_oauth(tmp_path):
    api, executive, lease, epoch, generation, profile, requested, config = _setup(tmp_path)
    async def exercise():
        runtime = await create_runtime_channel(config.action)
        try:
            admission = api.WorkerBrowserAdmission(executive.store, lease, epoch,
                generation, requested, profile, "worker-browser-isolated", runtime)
            server = api.create_worker_browser_server(runtime, config.browser, admission)
            result = await _call(server, "prepare_browser_resource", {
                "project_ref": config.action.lease.project_ref, "mode": "isolated"})
            assert result.structuredContent["status"] == "PREPARED"
            assert lease.lease_token not in repr(admission)
        finally:
            runtime.revoke()
            await runtime.aclose(timeout=5)
    asyncio.run(exercise())


@pytest.mark.parametrize("invalidation", ["cancel", "fence", "generation", "attestation", "workspace"])
def test_durable_owner_changes_refuse_before_browser_effect(tmp_path, invalidation):
    api, executive, lease, epoch, generation, profile, requested, config = _setup(tmp_path)
    async def exercise():
        runtime = await create_runtime_channel(config.action)
        try:
            admission = api.WorkerBrowserAdmission(executive.store, lease, epoch,
                generation, requested, profile, "worker-browser-isolated", runtime)
            server = api.create_worker_browser_server(runtime, config.browser, admission)
            if invalidation == "cancel":
                executive.jobs.cancel_job(lease.attempt.job_id)
            elif invalidation == "fence":
                # Fault injection: an old capability must fail after its fence changes.
                with executive.store.transaction() as connection:
                    connection.execute("UPDATE attempts SET fence_generation=fence_generation+1")
            elif invalidation == "generation":
                with executive.store.transaction() as connection:
                    connection.execute("UPDATE process_generations SET executive_writer_held=0")
            elif invalidation == "attestation":
                with executive.store.transaction() as connection:
                    connection.execute("UPDATE process_generations SET observed_attestation_digest=?", ("0" * 64,))
            else:
                root = Path(config.action.project_root)
                root.rename(root.with_name("original-project"))
                root.mkdir(mode=0o700)
            result = await _call(server, "prepare_browser_resource", {
                "project_ref": config.action.lease.project_ref, "mode": "isolated"})
            assert _error_code(result) == "CHANNEL_ADMISSION_REFUSED"
            assert list(Path(config.action.artifact_directory).iterdir()) == []
        finally:
            runtime.revoke()
            await runtime.aclose(timeout=5)
    asyncio.run(exercise())


def test_other_attempt_cannot_borrow_an_existing_channel(tmp_path):
    api, executive, lease, epoch, generation, profile, requested, config = _setup(tmp_path)
    async def exercise():
        runtime = await create_runtime_channel(config.action)
        try:
            wrong_epoch = dataclasses.replace(epoch, attempt_id="another-attempt")
            with pytest.raises(ValueError, match="BROWSER_WORKER_ADMISSION_REFUSED"):
                api.WorkerBrowserAdmission(executive.store, lease, wrong_epoch,
                    generation, requested, profile, "worker-browser-isolated", runtime)
        finally:
            runtime.revoke()
            await runtime.aclose(timeout=5)
    asyncio.run(exercise())


def test_discovery_is_possible_before_attestation_but_dispatch_is_not(tmp_path):
    api, executive, lease, epoch, generation, profile, requested, config = _setup(tmp_path)
    with executive.store.transaction() as connection:
        connection.execute("UPDATE process_generations SET observed_attestation_json=NULL, observed_attestation_digest=NULL")
    async def exercise():
        runtime = await create_runtime_channel(config.action)
        try:
            admission = api.WorkerBrowserAdmission(executive.store, lease, epoch,
                generation, requested, profile, "worker-browser-isolated", runtime)
            server = api.create_worker_browser_server(runtime, config.browser, admission)
            assert [t.name for t in await _tools(server)] == ["prepare_browser_resource"]
            result = await _call(server, "prepare_browser_resource", {
                "project_ref": config.action.lease.project_ref, "mode": "isolated"})
            assert _error_code(result) == "CHANNEL_ADMISSION_REFUSED"
        finally:
            runtime.revoke()
            await runtime.aclose(timeout=5)
    asyncio.run(exercise())
