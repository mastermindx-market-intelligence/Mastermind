"""Trusted supervisor composition of an existing OHF Attempt and Browser ports.

The worker receives only the resulting stdio server. RuntimeStore, lease tokens,
action keys and host configuration stay with the existing supervisor. This
module neither allocates Attempts nor starts providers, selects hosts, installs
profiles, or changes the B1 capability. Deployment must supply the admitted
network/resource boundary; this adapter is not an egress sandbox.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
from datetime import datetime
from pathlib import Path
import stat

from control_plane.executive_agent_capabilities import ExecutionCapabilityProfile
from control_plane.executive_runtime import (
    Attempt, AttemptLease, AttemptStatus, OperatorHarnessRegistry, RuntimeStore,
    _ohf_json_digest,
)
from control_plane.operator_harness_contract import (
    LaunchDecision, ProcessGenerationRef, RequestedExecutionProfile, SessionEpochRef,
    compare_launch,
)
from control_plane.operator_harness_wire import observed_harness_attestation
from integrations.workbench_action_mcp.runtime import (
    StableWorkbenchActionLease, WorkbenchActionRuntime,
)
from integrations.workbench_action_mcp.service import BrowserServiceConfig
from .tunnel import create_browser_tunnel_server


def _refuse():
    raise ValueError("BROWSER_WORKER_ADMISSION_REFUSED")


def _references(attempt, epoch, generation, profile):
    if (
        type(attempt) is not Attempt
        or type(epoch) is not SessionEpochRef
        or type(generation) is not ProcessGenerationRef
        or type(profile) is not ExecutionCapabilityProfile
        or not profile.enabled
        or epoch.attempt_id != attempt.attempt_id
        or epoch.worker_id != attempt.worker_id
        or generation.worker_id != attempt.worker_id
        or generation.session_epoch_id != epoch.session_epoch_id
        or type(epoch.epoch_number) is not int or epoch.epoch_number < 1
        or type(generation.generation_number) is not int or generation.generation_number < 1
    ):
        _refuse()
    identities = (attempt.job_id, attempt.attempt_id, attempt.worker_id,
                  epoch.session_epoch_id, generation.process_generation_id, profile.profile_digest)
    if any(type(item) is not str or not item or len(item) > 256 for item in identities):
        _refuse()

    def ref(kind, *values):
        encoded = json.dumps(["worker-browser", kind, *values], separators=(",", ":"))
        return kind + ":" + hashlib.sha256(encoded.encode()).hexdigest()

    # Projection into the existing scope fields, not a second identity registry.
    return {
        "context_ref": ref("context", attempt.job_id),
        "responsibility_ref": ref("responsibility", attempt.attempt_id),
        "operation_ref": ref("operation", attempt.attempt_id, epoch.session_epoch_id),
        "owner_ref": ref("owner", attempt.worker_id),
        "generation": ref("generation", generation.process_generation_id,
                          attempt.fence_generation, profile.profile_digest),
    }


def project_worker_browser_lease(
    lease: StableWorkbenchActionLease, *, attempt: Attempt, epoch: SessionEpochRef,
    generation: ProcessGenerationRef, profile: ExecutionCapabilityProfile,
) -> StableWorkbenchActionLease:
    """Narrow a supervisor-issued channel lease to its original Attempt.

    This pure projection is not admission. WorkerBrowserAdmission must validate
    the live authoritative lease, sealed profile and observed generation before
    any browser call, including after the executor queues an action.
    """
    if type(lease) is not StableWorkbenchActionLease:
        _refuse()
    refs = _references(attempt, epoch, generation, profile)
    expiry = int(datetime.fromisoformat(attempt.lease_expires_at).timestamp() * 1000)
    return dataclasses.replace(lease, **refs,
        lease_expires_at_ms=min(lease.lease_expires_at_ms, expiry))


class WorkerBrowserAdmission:
    """Read the existing Runtime owner on every dispatch; store no new state."""

    def __init__(self, store: RuntimeStore, lease: AttemptLease, epoch: SessionEpochRef,
                 generation: ProcessGenerationRef, requested: RequestedExecutionProfile,
                 profile: ExecutionCapabilityProfile, capability_id: str,
                 workbench: WorkbenchActionRuntime):
        if (type(store) is not RuntimeStore or type(lease) is not AttemptLease
                or type(requested) is not RequestedExecutionProfile
                or not isinstance(workbench, WorkbenchActionRuntime)):
            _refuse()
        refs = _references(lease.attempt, epoch, generation, profile)
        grants = [g for g in profile.mcp_server_grants if g.capability_id == capability_id]
        if (
            len(grants) != 1 or requested.worker_id != epoch.worker_id
            or requested.harness_kind != profile.execution_surface
            or requested.capabilities != profile.capability_manifest(
                harness_binary_digest=requested.harness_binary_digest)
            or requested.expected_config_digest != profile.expected_config_digest
            or requested.network_policy != profile.network_policy
            or requested.sandbox_policy != profile.sandbox_policy
            or requested.approval_policy != profile.approval_policy
            or requested.write_capable != profile.write_capable
            or requested.native_helper_policy != profile.native_helper_policy
        ):
            _refuse()
        self._registry = OperatorHarnessRegistry(store)
        self._lease = lease
        self._epoch, self._generation = epoch, generation
        self._requested = requested
        self._requested_json, self._requested_digest = _ohf_json_digest(requested)
        self._refs = refs
        self._workbench = workbench
        self.grant = grants[0]

    def resolve_binding(self, caller, project_ref):
        """A refusal/error is absence of authority, never retry or renewal."""
        try:
            binding = self._workbench.resolve_binding(caller, project_ref)
            if binding is None:
                return None
            scope = binding.scope
            if any(getattr(scope, key) != value for key, value in self._refs.items()):
                return None
            workspace = self._requested.workspace
            actual = Path(workspace.workspace_path).lstat()
            if (not stat.S_ISDIR(actual.st_mode)
                    or (actual.st_dev, actual.st_ino, actual.st_uid, actual.st_gid)
                    != (workspace.device, workspace.inode, workspace.uid, workspace.gid)):
                return None
            if (scope.root_device, scope.root_inode) != (workspace.device, workspace.inode):
                return None
            store = self._registry.store
            with store.read() as connection:
                row = self._registry._leased(connection,
                    attempt_id=self._epoch.attempt_id,
                    fence_generation=self._lease.attempt.fence_generation,
                    lease_token=self._lease.lease_token, timestamp=store.now_ms(),
                    statuses={AttemptStatus.RUNNING, AttemptStatus.CHECKPOINTED})
                current = self._registry._owned_generation(connection, leased=row,
                    epoch=self._epoch, generation=self._generation,
                    require_current=True, require_writer=True)
                if (row["job_id"] != self._lease.attempt.job_id
                        or row["requested_execution_profile_json"] != self._requested_json
                        or row["requested_execution_profile_digest"] != self._requested_digest
                        or scope.expires_at_ms > row["lease_expires_at_ms"]
                        or current["ended_at_ms"] is not None
                        or current["provider_writer_state"] != "HELD"
                        or not current["provider_session_id"]):
                    return None
                raw = current["observed_attestation_json"]
                digest = current["observed_attestation_digest"]
                if not raw or hashlib.sha256(raw.encode()).hexdigest() != digest:
                    return None
                observed = observed_harness_attestation(json.loads(raw))
                if compare_launch(self._requested, observed).decision is not LaunchDecision.ALLOW:
                    return None
                # Preserve the stronger current role/placement/active-work law
                # for orchestrators; do not turn a valid flat lease into it.
                self._registry._require_active_orchestration_generation(connection,
                    row=row, generation_id=self._generation.process_generation_id)
            return binding
        except Exception:
            return None


def create_worker_browser_server(runtime: WorkbenchActionRuntime,
                                config: BrowserServiceConfig,
                                admission: WorkerBrowserAdmission):
    """The supervisor serves this on its admitted attempt-private stdio pair."""
    if type(admission) is not WorkerBrowserAdmission or admission._workbench is not runtime:
        _refuse()
    return create_browser_tunnel_server(runtime, config, mcp_grant=admission.grant,
        resolve_binding=admission.resolve_binding)
