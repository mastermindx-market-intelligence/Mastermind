"""Executive-owned composition for one read-only operator planning Attempt.

This is not a scheduler and owns no durable state.  It claims one exact
command-bound planner through Executive Runtime, delegates provider effects to
the frozen Operator Harness orchestrator, and terminalizes only after the role
result is sealed, the worker process is proven dead/released, and the epoch is
abandoned.
"""
from __future__ import annotations

import asyncio
import copy
import json
import re
import subprocess
from pathlib import Path
from typing import Any, Callable, Protocol

from control_plane.executive_agent_capabilities import (
    CLAUDE_OPERATOR_EXECUTION_SURFACE,
    CLAUDE_OPERATOR_HARNESS_KIND,
    CLAUDE_OPERATOR_PROVIDER,
    COO_DOMAIN_EXECUTION_PROFILE,
    CapabilityPolicyError,
    ExecutionCapabilityProfile,
    ExecutionCapabilityRegistry,
)
from control_plane.executive_operator_harness_port import ExecutiveOperatorHarnessPort
from control_plane.executive_orchestration_result import (
    canonical_bytes,
    canonical_digest,
    parse_canonical_json,
)
from control_plane.executive_runtime import (
    INTERACTIVE_TX5_EXECUTION_PROFILE,
    Attempt,
    AttemptLease,
    AttemptStatus,
    Job,
    JobPayload,
    OrchestrationDispatchOutcome,
    Runtime,
    StateConflict,
)
from control_plane.executive_supervisor import (
    ExecutiveSupervisor,
    ReconcileReceipt,
    ReconcileStatus,
    worker_result_schema,
)
from control_plane.operator_harness_contract import (
    AuthRealmRequirement,
    OperatorHarnessAdapter,
    EventCursor,
    LaunchDecision,
    NativeHelperPolicy,
    OperationId,
    OperationKind,
    OperationReceiptKind,
    ProcessIdentityObservation,
    ProcessLiveness,
    ProviderSessionHandoff,
    ProviderWriterState,
    RequestedExecutionProfile,
    SessionStartObservation,
    TurnRef,
    WorkspaceIdentity,
    compare_launch,
    operation_receipt_command_id,
)
from control_plane.operator_harness_orchestrator import (
    OperatorEffectUnknown,
    OperatorHarnessOrchestrator,
    OperatorSessionReceipt,
    OperatorStartHandle,
    OperatorStartRefused,
)
from control_plane.operator_harness_wire import (
    OperatorHarnessWireError,
    observed_harness_attestation,
    requested_execution_profile,
)
from control_plane.remote_codex_operator_adapter import RemoteCodexOperatorAdapter
from control_plane.executive_worker_broker import RemoteBrokerError
from control_plane.worker_browser_b1 import BrowserReviewReceipt


class ExecutiveOperatorSupervisorError(RuntimeError):
    """One exact read-only operator Attempt could not be safely completed."""


RemoteAdapterFactory = Callable[
    [Callable[[Any], str]], RemoteCodexOperatorAdapter
]

# Installed host observations for the already-claimed Worker; no placement authority.
ClaimedWorkspaceIdentitySource = Callable[[Attempt, Job], WorkspaceIdentity]


class ClaimedOperatorAdapterFactory(Protocol):
    """Host-owned construction, not placement or permission to perform I/O."""

    def __call__(self, attempt: Attempt, requested: RequestedExecutionProfile,
                 turn_input_loader: Callable[[Any], str], *,
                 recovery: bool) -> OperatorHarnessAdapter: ...


class ExecutiveOperatorSupervisor:
    """Run only ``plan`` roles through the Runtime-owned OHF lifecycle."""

    def __init__(
        self,
        runtime: Runtime,
        *,
        adapter_factory: RemoteAdapterFactory | None = None,
        prompt_source: ExecutiveSupervisor,
        instance_id: str = "executive-coo-operator",
        claimed_adapter_factory: ClaimedOperatorAdapterFactory | None = None,
        workspace_identity_source: ClaimedWorkspaceIdentitySource | None = None,
    ) -> None:
        if ((adapter_factory is None) == (claimed_adapter_factory is None)
                or (adapter_factory is not None and not callable(adapter_factory))
                or (claimed_adapter_factory is not None and not callable(claimed_adapter_factory))):
            raise ExecutiveOperatorSupervisorError("exactly one callable operator factory is required")
        if workspace_identity_source is not None and (
            not callable(workspace_identity_source) or claimed_adapter_factory is None
        ):
            raise ExecutiveOperatorSupervisorError(
                "selected-host workspace identity requires a claim-aware factory"
            )
        self.runtime = runtime
        self.adapter_factory = adapter_factory
        self._claimed_adapter_factory = claimed_adapter_factory
        self._workspace_identity_source = workspace_identity_source
        self.prompt_source = prompt_source
        self.instance_id = instance_id

    def _adapter_for_attempt(
        self, lease: AttemptLease, requested: RequestedExecutionProfile,
        loader: Callable[[Any], str], *, recovery: bool,
    ) -> OperatorHarnessAdapter:
        factory = self._claimed_adapter_factory
        if factory is None:
            assert self.adapter_factory is not None
            return self.adapter_factory(loader)

        # Construction must not start a provider. Runtime retains the lease and
        # final effect admission; the callback receives no lease token or new authority.
        def current_binding() -> tuple[Attempt, tuple[Any, ...]]:
            current = self.runtime.attempts.get_attempt(lease.attempt.attempt_id)
            allowed = ({AttemptStatus.CLAIMED, AttemptStatus.RUNNING,
                        AttemptStatus.CHECKPOINTED, AttemptStatus.CANCEL_REQUESTED}
                       if recovery else {AttemptStatus.CLAIMED})
            identity = ("attempt_id", "job_id", "worker_id", "quota_class",
                        "fence_generation", "lease_owner", "authority_policy_hash")
            if (not isinstance(current, Attempt) or current.status not in allowed
                    or any(getattr(current, key) != getattr(lease.attempt, key)
                           for key in identity)
                    or requested.worker_id != current.worker_id
                    or requested.authority_policy_hash != current.authority_policy_hash):
                raise ExecutiveOperatorSupervisorError("claimed operator identity is no longer current")
            job = self.runtime.jobs.get_job(current.job_id)
            if (job is None or job.current_attempt_id != current.attempt_id
                    or job.assigned_worker_id != current.worker_id
                    or job.assigned_quota_class != current.quota_class):
                raise ExecutiveOperatorSupervisorError("claimed operator Job binding moved")
            signature = tuple(getattr(current, key) for key in identity) + (
                current.status, current.execution_mode,
                current.requested_execution_profile_digest,
                current.effective_grant_digest, current.placement_snapshot_digest,
                current.execution_principal_snapshot_digest, job.status,
            )
            return current, signature

        current, before = current_binding()
        try:
            adapter = factory(copy.deepcopy(current), copy.deepcopy(requested),
                              loader, recovery=recovery)
        except Exception:
            raise ExecutiveOperatorSupervisorError("claimed operator construction refused") from None
        _, after = current_binding()
        if before != after:
            raise ExecutiveOperatorSupervisorError("claimed operator binding changed during construction")
        return adapter

    @staticmethod
    def _git_head(workspace: Path) -> str:
        try:
            value = subprocess.run(
                ["git", "-C", str(workspace), "rev-parse", "HEAD"],
                check=True,
                capture_output=True,
                text=True,
                timeout=10,
                env={
                    "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
                    "GIT_CONFIG_GLOBAL": "/dev/null",
                    "GIT_CONFIG_NOSYSTEM": "1",
                    "LC_ALL": "C",
                },
            ).stdout.strip().lower()
        except (OSError, subprocess.SubprocessError) as exc:
            raise ExecutiveOperatorSupervisorError(
                "operator workspace HEAD is not observable"
            ) from exc
        if re.fullmatch(r"[0-9a-f]{40}", value) is None:
            raise ExecutiveOperatorSupervisorError(
                "operator workspace HEAD is not exact 40-hex"
            )
        return value

    def _workspace_identity(
        self, job: Job, attempt: Attempt | None = None
    ) -> WorkspaceIdentity:
        source = self._workspace_identity_source
        if source is not None:
            # Validate the logical identity without touching the host filesystem.
            base = job.constraints.get("base_sha")
            if (type(job.worktree) is not str or not job.worktree
                    or not Path(job.worktree).is_absolute()
                    or str(Path(job.worktree)) != job.worktree
                    or ".." in Path(job.worktree).parts
                    or job.worktree.startswith("//")
                    or type(base) is not str
                    or re.fullmatch(r"[0-9a-f]{40}", base) is None):
                raise ExecutiveOperatorSupervisorError(
                    "selected-host workspace identity Job is invalid"
                )
            # A remote path must never be stat'ed or resolved on the Control host.
            # The installed owner supplies physical facts from the selected host.
            if attempt is None:
                raise ExecutiveOperatorSupervisorError(
                    "selected-host workspace identity has no claimed Attempt"
                )
            current_job = self.runtime.jobs.get_job(job.job_id)
            current = self.runtime.attempts.get_attempt(attempt.attempt_id)
            keys = ("attempt_id", "job_id", "worker_id", "quota_class",
                    "fence_generation", "lease_owner", "authority_policy_hash")
            if (current_job is None or current is None
                    or current.status is not AttemptStatus.CLAIMED
                    or any(getattr(current, key) != getattr(attempt, key)
                           for key in keys)
                    or current_job.current_attempt_id != current.attempt_id
                    or current_job.assigned_worker_id != current.worker_id
                    or current_job.assigned_quota_class != current.quota_class
                    or current_job.worktree != job.worktree
                    or current_job.constraints != job.constraints):
                raise ExecutiveOperatorSupervisorError(
                    "selected-host workspace identity claim is no longer current"
                )
            def stable_claim(value: Attempt) -> dict[str, Any]:
                fields = value.to_dict()
                for field in ("version", "heartbeat_at", "lease_expires_at"):
                    fields.pop(field)
                return fields

            before_job = copy.deepcopy(current_job)
            before_claim = stable_claim(current)
            try:
                observed = source(copy.deepcopy(current), copy.deepcopy(current_job))
            except Exception:
                raise ExecutiveOperatorSupervisorError(
                    "selected-host workspace identity source refused"
                ) from None
            after_job = self.runtime.jobs.get_job(job.job_id)
            after = self.runtime.attempts.get_attempt(attempt.attempt_id)
            if (after_job != before_job or after is None
                    or stable_claim(after) != before_claim):
                raise ExecutiveOperatorSupervisorError(
                    "selected-host workspace binding moved during observation"
                )
            if (type(observed) is not WorkspaceIdentity
                    or observed.workspace_path != job.worktree
                    or observed.base_sha != job.constraints.get("base_sha")
                    or any(type(getattr(observed, field)) is not int
                           or getattr(observed, field) < 0
                           for field in ("device", "inode", "uid", "gid"))
                    or observed.inode == 0):
                raise ExecutiveOperatorSupervisorError(
                    "selected-host workspace identity is invalid"
                )
            return observed
        if not job.worktree:
            raise ExecutiveOperatorSupervisorError(
                "operator planner has no assigned workspace"
            )
        workspace = Path(job.worktree).resolve(strict=True)
        info = workspace.lstat()
        if workspace.is_symlink() or not workspace.is_dir():
            raise ExecutiveOperatorSupervisorError(
                "operator planner workspace is not a real directory"
            )
        head = self._git_head(workspace)
        if head != job.constraints.get("base_sha"):
            raise ExecutiveOperatorSupervisorError(
                "operator planner workspace differs from its exact base"
            )
        return WorkspaceIdentity(
            workspace_path=str(workspace),
            base_sha=head,
            device=int(info.st_dev),
            inode=int(info.st_ino),
            uid=int(info.st_uid),
            gid=int(info.st_gid),
        )

    def _requested_profile(
        self, job: Job, lease: AttemptLease
    ) -> RequestedExecutionProfile:
        constraints = job.constraints
        if constraints.get("execution_profile_id") == (
            "operator.appserver.interactive.v1"
        ):
            raise ExecutiveOperatorSupervisorError(
                "App Server supervisor refuses the interactive profile before claim"
            )
        if job.orchestration_role != "plan":
            raise ExecutiveOperatorSupervisorError(
                "App Server composition accepts only the read-only planner role"
            )
        if (
            job.requested_authorities != ["READ"]
            or job.allowed_write_paths
            or job.validation_commands
        ):
            raise ExecutiveOperatorSupervisorError(
                "operator planner authority is not closed read-only"
            )
        quota = self.runtime.workers.get_quota_class(
            lease.attempt.worker_id, lease.attempt.quota_class
        )
        if quota is None:
            raise ExecutiveOperatorSupervisorError(
                "operator planner quota disappeared after claim"
            )
        identity_keys = (
            "execution_profile_id",
            "execution_profile_digest",
            "capability_policy_version",
            "capability_policy_digest",
        )
        if any(
            quota.metadata.get(key) != job.constraints.get(key)
            for key in identity_keys
        ):
            raise ExecutiveOperatorSupervisorError(
                "operator quota execution-profile identity drifted"
            )
        harness_digest = str(job.constraints.get("harness_binary_digest") or "")
        harness_version = str(job.constraints.get("harness_version") or "")
        if (
            quota.metadata.get("harness_binary_digest") != harness_digest
            or quota.metadata.get("harness_version") != harness_version
            or re.fullmatch(r"[0-9a-f]{64}", harness_digest) is None
            or not harness_version
        ):
            raise ExecutiveOperatorSupervisorError(
                "operator quota harness identity drifted"
            )
        try:
            registry = ExecutionCapabilityRegistry.load()
        except CapabilityPolicyError as exc:
            raise ExecutiveOperatorSupervisorError(
                f"operator capability policy is invalid: {exc}"
            ) from exc
        requested_profile_id = str(
            job.constraints.get("execution_profile_id") or ""
        )
        try:
            # Ordinary admission for every profile.  A disabled profile
            # (including the shipped-disabled COO domain source shape) is
            # refused here; no caller may index ``registry.profiles`` to
            # bypass admission.  The closed read-only domain shape remains
            # validated by ``domain_profile_ok`` below and by
            # ``ExecutionCapabilityRegistry.load`` against
            # ``COO_DOMAIN_PROFILE_SHAPE``.
            profile = registry.resolve(requested_profile_id)
        except CapabilityPolicyError as exc:
            raise ExecutiveOperatorSupervisorError(
                f"operator capability profile is not admitted: {exc}"
            ) from exc
        common_profile_ok = (
            registry.policy_version
            == job.constraints.get("capability_policy_version")
            and registry.policy_digest
            == job.constraints.get("capability_policy_digest")
            and profile.profile_digest
            == job.constraints.get("execution_profile_digest")
            and profile.auth_realm == "dedicated-worker-account"
            and profile.sandbox_policy == "read-only"
            and profile.approval_policy == "never"
            and not profile.write_capable
            and not profile.skills
            and not profile.plugins
        )
        docs_profile_ok = (
            profile.profile_id
            == "operator.appserver.readonly.docs-mcp.native-helper.v1"
            and profile.execution_surface == "codex-app-server"
            and profile.network_policy == "disabled"
            and profile.native_helper_policy.value == "PARENT_READ_ONLY_CEILING"
            and profile.native_helper is not None
            and profile.mcp_servers == ("openai-developer-docs-v1",)
            and not profile.resource_grants
        )
        browser_profile_ok = (
            profile.profile_id == "operator.browser.local-review.v1"
            and profile.execution_surface == "codex-app-server"
            and profile.network_policy == "loopback-browser-only"
            and profile.native_helper_policy.value == "DISABLED"
            and profile.native_helper is None
            and profile.mcp_servers
            == (
                "openai-developer-docs-v1",
                "playwright-worker-browser-b1",
            )
            and tuple(grant.resource_id for grant in profile.resource_grants)
            == ("worker-browser-b1-local",)
        )
        native_claude_profile_ok = (
            profile.profile_id == "operator.claude.readonly.v1"
            and profile.enabled is True
            and profile.execution_surface == CLAUDE_OPERATOR_EXECUTION_SURFACE
            and profile.network_policy == "disabled"
            and profile.native_helper_policy.value == "DISABLED"
            and profile.native_helper is None
            and not profile.skill_grants
            and not profile.mcp_server_grants
            and not profile.resource_grants
        )
        domain_profile_ok = (
            profile.profile_id == COO_DOMAIN_EXECUTION_PROFILE
            and profile.execution_surface == "codex-app-server"
            and profile.network_policy == "disabled"
            and profile.native_helper_policy is NativeHelperPolicy.DISABLED
            and profile.native_helper is None
            and not profile.mcp_server_grants
            and not profile.resource_grants
            and not profile.skill_grants
        )
        if not common_profile_ok or not (
            docs_profile_ok or browser_profile_ok or domain_profile_ok
            or native_claude_profile_ok
        ):
            raise ExecutiveOperatorSupervisorError(
                "operator planner profile is not one reviewed rich read-only lane"
            )
        if native_claude_profile_ok and (
            quota.provider != CLAUDE_OPERATOR_PROVIDER
            or job.constraints.get("provider") != CLAUDE_OPERATOR_PROVIDER
        ):
            raise ExecutiveOperatorSupervisorError(
                "native Claude planner provider drifted after claim"
            )
        if quota.model != job.constraints.get("model") or quota.effort != job.constraints.get(
            "effort"
        ):
            raise ExecutiveOperatorSupervisorError(
                "operator planner model/effort drifted after claim"
            )
        return RequestedExecutionProfile(
            worker_id=lease.attempt.worker_id,
            provider=(CLAUDE_OPERATOR_PROVIDER if native_claude_profile_ok else "openai-codex"),
            requested_model=str(quota.model),
            harness_kind=(CLAUDE_OPERATOR_HARNESS_KIND if native_claude_profile_ok else "codex-app-server"),
            harness_binary_digest=harness_digest,
            harness_version=harness_version,
            workspace=(
                self._workspace_identity(job, lease.attempt)
                if self._workspace_identity_source is not None
                else self._workspace_identity(job)
            ),
            sandbox_policy="read-only",
            approval_policy="never",
            network_policy=profile.network_policy,
            capabilities=profile.capability_manifest(
                harness_binary_digest=harness_digest
            ),
            native_helper_policy=profile.native_helper_policy,
            authority_policy_hash=lease.attempt.authority_policy_hash,
            auth_realm_requirement=AuthRealmRequirement.SLOT_BOUND_V1,
            expected_config_digest=profile.expected_config_digest,
            allowed_write_paths=(),
            write_capable=False,
        )

    def _prompt(self, job: Job, lease: AttemptLease) -> str:
        grant = ExecutiveSupervisor._effective_grant(job, lease.attempt)
        schema = worker_result_schema(
            job_id=job.job_id,
            run_id=lease.attempt.attempt_id,
            worker_id=lease.attempt.worker_id,
            effective_grant_digest=lease.attempt.effective_grant_digest,
            orchestration_role="plan",
            root_job_id=job.root_job_id,
        )
        return (
            self.prompt_source._prompt(job, lease.attempt, grant)
            + "\n\nThe output schema is embedded below because this App Server lane "
            "has no separate schema-file argument. Return exactly one minified, "
            "UTF-8 JSON object with keys recursively sorted lexicographically, no "
            "markdown fence, no leading BOM, no trailing newline, and no commentary.\n"
            + json.dumps(schema, sort_keys=True, ensure_ascii=False, indent=2)
        )

    @staticmethod
    def _terminal_payload(
        *,
        job: Job,
        lease: AttemptLease,
        canonical_result_json: str,
        artifact_receipt_digest: str | None = None,
    ) -> dict[str, Any]:
        envelope = parse_canonical_json(canonical_result_json)
        if not isinstance(envelope, dict):
            raise ExecutiveOperatorSupervisorError(
                "operator role result is not an object"
            )
        terminal = {
            "schema_version": "mastermind.orchestration_terminal_receipt/v1",
            "status": "COMPLETED",
            "job_id": job.job_id,
            "attempt_id": lease.attempt.attempt_id,
            "orchestration_role": job.orchestration_role,
            "execution_mode": "OPERATOR_HARNESS",
            "result_seal_command_id": (
                f"orchestration-result-seal:{lease.attempt.attempt_id}"
            ),
            "result_evidence": None,
            "result_envelope": envelope,
            "result_envelope_digest": canonical_digest(envelope),
            "artifact_receipt_digest": (
                artifact_receipt_digest
                if artifact_receipt_digest is not None
                else canonical_digest([])
            ),
            "validation_receipt_digest": canonical_digest([]),
            "effective_grant_digest": lease.attempt.effective_grant_digest,
        }
        terminal["terminal_evidence_digest"] = canonical_digest(terminal)
        return terminal

    def _orchestrator(
        self,
        lease: AttemptLease,
        adapter: RemoteCodexOperatorAdapter,
    ) -> OperatorHarnessOrchestrator:
        return OperatorHarnessOrchestrator(
            ExecutiveOperatorHarnessPort(self.runtime, lease),
            adapter,
            attestation_reader=lambda value, generation: value.observed_attestation(
                generation
            ),
        )

    def _complete_after_stop(
        self,
        *,
        job: Job,
        lease: AttemptLease,
        session: OperatorSessionReceipt,
        adapter: RemoteCodexOperatorAdapter,
        canonical_result_json: str,
        stop_operation: OperationId,
    ) -> None:
        orchestrator = self._orchestrator(lease, adapter)
        stopped = orchestrator.graceful_stop(
            session, operation_id=stop_operation
        )
        if (
            stopped.process_liveness is not ProcessLiveness.PROVEN_DEAD
            or stopped.provider_writer_state is not ProviderWriterState.RELEASED
        ):
            raise ExecutiveOperatorSupervisorError(
                "operator graceful stop did not prove dead/released"
            )
        artifact_receipt_digest = self._terminal_artifact_receipt_digest(
            session=session, adapter=adapter
        )
        self._complete_after_shutdown(
            job=job,
            lease=lease,
            session=session,
            canonical_result_json=canonical_result_json,
            artifact_receipt_digest=artifact_receipt_digest,
        )

    @staticmethod
    def _terminal_artifact_receipt_digest(
        *,
        session: OperatorSessionReceipt,
        adapter: RemoteCodexOperatorAdapter,
    ) -> str:
        requires_resource = any(
            capability.kind == "resource"
            for capability in session.observed.capabilities
        )
        try:
            receipt = adapter.terminal_artifact_receipt(session.generation)
        except Exception as exc:
            if requires_resource:
                raise ExecutiveOperatorSupervisorError(
                    "browser Attempt lacks its post-sweep artifact receipt"
                ) from exc
            return canonical_digest([])
        if receipt is None:
            if requires_resource:
                raise ExecutiveOperatorSupervisorError(
                    "browser Attempt lacks its post-sweep artifact receipt"
                )
            return canonical_digest([])
        if not isinstance(receipt, BrowserReviewReceipt):
            raise ExecutiveOperatorSupervisorError(
                "operator terminal artifact receipt is not typed"
            )
        if (
            not requires_resource
            or receipt.attempt_id != session.attempt_id
            or receipt.session_epoch_id != session.epoch.session_epoch_id
            or receipt.process_generation_id
            != session.generation.process_generation_id
        ):
            raise ExecutiveOperatorSupervisorError(
                "operator terminal artifact receipt identity drifted"
            )
        return receipt.digest

    def _complete_after_shutdown(
        self,
        *,
        job: Job,
        lease: AttemptLease,
        session: OperatorSessionReceipt,
        canonical_result_json: str,
        artifact_receipt_digest: str | None = None,
    ) -> None:
        """Complete only after the caller has proven the generation shut down."""

        self.runtime.operator_harness.abandon_epoch(
            epoch=session.epoch,
            fence_generation=lease.attempt.fence_generation,
            lease_token=lease.lease_token,
        )
        self.runtime.attempts.complete_attempt(
            lease.attempt.attempt_id,
            fence_generation=lease.attempt.fence_generation,
            lease_token=lease.lease_token,
            payload=self._terminal_payload(
                job=job,
                lease=lease,
                canonical_result_json=canonical_result_json,
                artifact_receipt_digest=artifact_receipt_digest,
            ),
        )

    def _sealed_role_result_json(self, job: Job, lease: AttemptLease) -> str | None:
        event = self.runtime.events.get_event_by_command_id(
            f"orchestration-result-seal:{lease.attempt.attempt_id}"
        )
        if event is None:
            return None
        payload = event.payload
        if (
            event.event_type != "ORCHESTRATION_ROLE_RESULT_SEALED"
            or event.job_id != job.job_id
            or event.attempt_id != lease.attempt.attempt_id
            or event.worker_id != lease.attempt.worker_id
            or event.quota_class != lease.attempt.quota_class
            or not isinstance(payload, dict)
            or payload.get("schema_version")
            != "mastermind.orchestration_role_result_seal/v1"
            or payload.get("job_id") != job.job_id
            or payload.get("attempt_id") != lease.attempt.attempt_id
            or payload.get("worker_id") != lease.attempt.worker_id
            or payload.get("quota_class") != lease.attempt.quota_class
            or payload.get("orchestration_role") != job.orchestration_role
            or payload.get("effective_grant_digest")
            != lease.attempt.effective_grant_digest
            or not isinstance(payload.get("result_envelope"), dict)
            or canonical_digest(payload["result_envelope"])
            != payload.get("result_envelope_digest")
        ):
            raise ExecutiveOperatorSupervisorError(
                "operator recovery role-result seal is not exact"
            )
        return canonical_bytes(payload["result_envelope"]).decode("utf-8")

    def _recovery_session(
        self,
        lease: AttemptLease,
        *,
        require_turn: bool = True,
    ) -> tuple[OperatorSessionReceipt, TurnRef | None]:
        """Reconstruct exact CURRENT G1, optionally before its first turn."""

        profile_raw = lease.attempt.requested_execution_profile
        try:
            requested = requested_execution_profile(profile_raw)
        except OperatorHarnessWireError as exc:
            raise ExecutiveOperatorSupervisorError(
                "operator recovery profile is not canonical"
            ) from exc
        with self.runtime.store.read() as connection:
            rows = connection.execute(
                """
                SELECT e.session_epoch_id,e.attempt_id,e.worker_id AS epoch_worker,
                       e.epoch_number,e.provider_session_id AS epoch_session,e.state,
                       g.process_generation_id,g.worker_id AS generation_worker,
                       g.generation_number,g.provider_session_id,g.pid,g.pgid,
                       g.process_start_identity,g.boot_id,g.executive_writer_held,
                       g.observed_attestation_json
                FROM harness_session_epochs e
                JOIN process_generations g
                  ON g.session_epoch_id=e.session_epoch_id
                WHERE e.attempt_id=? AND e.state='CURRENT'
                  AND g.executive_writer_held=1
                ORDER BY e.epoch_number,g.generation_number
                """,
                (lease.attempt.attempt_id,),
            ).fetchall()
            turn_events = connection.execute(
                """
                SELECT * FROM events
                WHERE attempt_id=? AND aggregate_type='operator_operation'
                  AND event_type=? ORDER BY event_id
                """,
                (
                    lease.attempt.attempt_id,
                    OperationReceiptKind.INTENT.value,
                ),
            ).fetchall()
        if len(rows) != 1:
            raise ExecutiveOperatorSupervisorError(
                "operator recovery requires one CURRENT Executive writer"
            )
        row = rows[0]
        if (
            row["attempt_id"] != lease.attempt.attempt_id
            or row["epoch_worker"] != lease.attempt.worker_id
            or row["generation_worker"] != lease.attempt.worker_id
            or row["provider_session_id"] != row["epoch_session"]
            or not row["provider_session_id"]
            or int(row["generation_number"]) != 1
            or not row["observed_attestation_json"]
        ):
            raise ExecutiveOperatorSupervisorError(
                "operator recovery identity is not exact G1"
            )
        try:
            observed = observed_harness_attestation(
                json.loads(str(row["observed_attestation_json"]))
            )
        except (json.JSONDecodeError, OperatorHarnessWireError) as exc:
            raise ExecutiveOperatorSupervisorError(
                "operator recovery attestation is not canonical"
            ) from exc
        launch = compare_launch(requested, observed)
        if launch.decision is not LaunchDecision.ALLOW:
            raise ExecutiveOperatorSupervisorError(
                "operator recovery launch identity no longer allows work"
            )
        epoch, generation = self.runtime.operator_harness.generation_refs(
            str(row["process_generation_id"])
        )
        process = ProcessIdentityObservation(
            pid=row["pid"],
            pgid=row["pgid"],
            process_start_identity=row["process_start_identity"],
            boot_id=row["boot_id"],
        )
        if (
            process.pid is None
            or process.pgid is None
            or not process.process_start_identity
            or not process.boot_id
        ):
            raise ExecutiveOperatorSupervisorError(
                "operator recovery process identity is incomplete"
            )
        session = OperatorSessionReceipt(
            attempt_id=lease.attempt.attempt_id,
            epoch=epoch,
            generation=generation,
            observation=SessionStartObservation(
                provider_session_id=str(row["provider_session_id"]),
                process=process,
            ),
            observed=observed,
            launch=launch,
        )
        turn_matches: list[tuple[Any, dict[str, Any]]] = []
        for event in turn_events:
            try:
                payload = json.loads(str(event["payload_json"]))
            except json.JSONDecodeError as exc:
                raise ExecutiveOperatorSupervisorError(
                    "operator recovery turn intent is malformed"
                ) from exc
            if payload.get("operation_kind") == OperationKind.BEGIN_TURN.value:
                turn_matches.append((event, payload))
        if len(turn_matches) > 1 or (require_turn and len(turn_matches) != 1):
            raise ExecutiveOperatorSupervisorError(
                "operator recovery has invalid begin-turn INTENT cardinality"
            )
        if not turn_matches:
            return session, None
        turn_event, turn_payload = turn_matches[0]
        operation = OperationId(str(turn_event["command_id"]))
        applied = self.runtime.events.get_event_by_command_id(
            operation_receipt_command_id(
                operation, OperationReceiptKind.APPLIED
            )
        )
        unknown = self.runtime.events.get_event_by_command_id(
            operation_receipt_command_id(
                operation, OperationReceiptKind.EFFECT_UNKNOWN
            )
        )
        expected_turn_keys = {
            "schema_version",
            "operation_kind",
            "attempt_id",
            "session_epoch_id",
            "process_generation_id",
            "worker_id",
            "provider_session_id",
            "turn_id",
        }
        if (
            applied is None
            or unknown is not None
            or set(turn_payload) != expected_turn_keys
            or turn_payload.get("attempt_id") != lease.attempt.attempt_id
            or turn_payload.get("session_epoch_id") != epoch.session_epoch_id
            or turn_payload.get("process_generation_id")
            != generation.process_generation_id
            or turn_payload.get("worker_id") != lease.attempt.worker_id
            or turn_payload.get("provider_session_id")
            != row["provider_session_id"]
            or not str(turn_payload.get("turn_id") or "")
        ):
            raise ExecutiveOperatorSupervisorError(
                "operator recovery turn has no exact acknowledged receipt"
            )
        turn = TurnRef(
            turn_id=str(turn_payload["turn_id"]),
            session_epoch_id=epoch.session_epoch_id,
            process_generation_id=generation.process_generation_id,
            attempt_id=lease.attempt.attempt_id,
        )
        return session, turn

    def _cleanup_failed_session(
        self,
        *,
        lease: AttemptLease,
        orchestrator: OperatorHarnessOrchestrator,
        handle: OperatorSessionReceipt | OperatorStartHandle,
        stop_operation: OperationId,
        reason: str,
    ) -> bool:
        """Terminalize a failed launch/turn only after dead + released proof."""

        current = self.runtime.attempts.get_attempt(lease.attempt.attempt_id)
        cancellation_requested = (
            current is not None
            and current.status is AttemptStatus.CANCEL_REQUESTED
        )
        observed = orchestrator.reconcile(handle)
        if (
            observed.process_liveness is ProcessLiveness.ALIVE
            and observed.provider_writer_state is ProviderWriterState.HELD
        ):
            if cancellation_requested:
                observed = orchestrator.cancel(
                    handle,
                    operation_id=OperationId(
                        f"ohf-op:cancel:{lease.attempt.attempt_id}"
                    ),
                    reason="durable Executive Runtime cancellation request",
                )
            else:
                observed = orchestrator.graceful_stop(
                    handle, operation_id=stop_operation
                )
        if (
            observed.process_liveness is not ProcessLiveness.PROVEN_DEAD
            or observed.provider_writer_state is not ProviderWriterState.RELEASED
        ):
            return False
        self.runtime.operator_harness.abandon_epoch(
            epoch=handle.epoch,
            fence_generation=lease.attempt.fence_generation,
            lease_token=lease.lease_token,
        )
        current = self.runtime.attempts.get_attempt(lease.attempt.attempt_id)
        if current is not None and current.status is AttemptStatus.CANCEL_REQUESTED:
            self.runtime.attempts.acknowledge_cancel(
                current.attempt_id,
                fence_generation=lease.attempt.fence_generation,
                lease_token=lease.lease_token,
            )
        elif current is not None and current.status in {
            AttemptStatus.CLAIMED,
            AttemptStatus.RUNNING,
            AttemptStatus.CHECKPOINTED,
        }:
            self.runtime.attempts.fail_attempt(
                current.attempt_id,
                fence_generation=lease.attempt.fence_generation,
                lease_token=lease.lease_token,
                payload=JobPayload(
                    summary="Operator Harness attempt failed closed after cleanup.",
                    current_state="failed_closed",
                    errors=[str(reason or "operator failure")[:256]],
                ),
            )
        return True

    def _run_claimed(
        self, job: Job, lease: AttemptLease
    ) -> OrchestrationDispatchOutcome:
        requested = self._requested_profile(job, lease)
        is_domain_job = (
            str(job.constraints.get("execution_profile_id") or "")
            == COO_DOMAIN_EXECUTION_PROFILE
        )
        prompt_by_turn: dict[str, str] = {}

        def load_turn(turn: Any) -> str:
            try:
                return prompt_by_turn[turn.turn_id]
            except KeyError as exc:
                raise ExecutiveOperatorSupervisorError(
                    "operator turn prompt is not bound to the Runtime turn"
                ) from exc

        adapter = self._adapter_for_attempt(lease, requested, load_turn, recovery=False)
        orchestrator = self._orchestrator(lease, adapter)
        attempt_id = lease.attempt.attempt_id
        start_operation = OperationId(f"ohf-op:start:{attempt_id}")
        turn_operation = OperationId(f"ohf-op:turn:{attempt_id}")
        stop_operation = OperationId(f"ohf-op:stop:{attempt_id}")
        checkpoint_operation = OperationId(
            f"ohf-op:checkpoint:{attempt_id}"
        )
        session: OperatorSessionReceipt | None = None
        domain_checkpoint_effect_unknown = False
        try:
            session = orchestrator.start_attempt(
                attempt_id=attempt_id,
                requested=requested,
                operation_id=start_operation,
            )
            prompt_by_turn["pending"] = self._prompt(job, lease)

            def bound_prompt(turn: Any) -> str:
                value = prompt_by_turn.pop("pending")
                prompt_by_turn[turn.turn_id] = value
                return value

            adapter.turn_input_loader = bound_prompt
            turn = orchestrator.run_turn(
                session,
                operation_id=turn_operation,
                timeout_seconds=300.0,
            )
            raw = adapter.observe_raw_role_result(turn.turn)
            if is_domain_job:
                # Domain post-claim path: the initial plan is sealed only as
                # a typed checkpoint under the same deterministic operation
                # ID.  We deliberately do NOT seal a terminal role result,
                # NOT call _complete_after_stop/_complete_after_shutdown/
                # complete_attempt/abandon_epoch here; the same nonterminal
                # Attempt, current epoch/session and observed generation are
                # preserved until the later same-domain consumption turn.
                try:
                    orchestrator.checkpoint(
                        session,
                        operation_id=checkpoint_operation,
                    )
                except OperatorEffectUnknown:
                    # The checkpoint external effect is UNKNOWN.  Do not
                    # stop/terminalize/abandon/replay provider work; the
                    # nonterminal Attempt, current epoch and observed
                    # generation stay preserved for later same-actor
                    # consumption (the generic handler below must skip
                    # cleanup for this exact case).
                    domain_checkpoint_effect_unknown = True
                    raise
            else:
                self._complete_after_stop(
                    job=job,
                    lease=lease,
                    session=session,
                    adapter=adapter,
                    canonical_result_json=raw.canonical_result_json,
                    stop_operation=stop_operation,
                )
        except OperatorStartRefused as exc:
            try:
                self._cleanup_failed_session(
                    lease=lease,
                    orchestrator=orchestrator,
                    handle=exc.handle,
                    stop_operation=stop_operation,
                    reason=type(exc).__name__,
                )
            except Exception:
                pass
            raise
        except Exception as exc:
            # A domain initial-plan checkpoint with UNKNOWN external effect
            # must never stop/abandon/terminalize or replay provider work;
            # preserve state for later same-actor consumption.  Ordinary
            # flat-planner failures keep the bounded cleanup below.
            if domain_checkpoint_effect_unknown:
                raise
            # Never blind-retry a provider effect.  If a session exists, make
            # one bounded stop attempt under the same generation; Runtime
            # receipts decide whether later reconciliation may proceed.
            if session is not None:
                try:
                    self._cleanup_failed_session(
                        lease=lease,
                        orchestrator=orchestrator,
                        handle=session,
                        stop_operation=stop_operation,
                        reason=type(exc).__name__,
                    )
                except Exception:
                    pass
            raise
        current = self.runtime.attempts.get_attempt(attempt_id)
        if is_domain_job:
            if current is None or current.status is not AttemptStatus.CHECKPOINTED:
                raise ExecutiveOperatorSupervisorError(
                    "operator domain Attempt did not reach durable CHECKPOINTED"
                )
            # Real nonterminal outcome for a checkpointed domain: the lease
            # is still active (CHECKPOINTED is in
            # ``_LEASE_ACTIVE_ATTEMPT_STATUSES``) and the same generation
            # stays observed for the later same-domain consumption turn.
            return OrchestrationDispatchOutcome(
                command_id=(
                    f"coo-cycle:{job.root_job_id}:dispatch:{job.job_id}:attempt:"
                    f"{job.attempt_count}"
                ),
                job_id=job.job_id,
                attempt=current,
                outcome="ACTIVE",
                lease_token=lease.lease_token,
                claimed_now=False,
            )
        if current is None or current.status is not AttemptStatus.COMPLETED:
            raise ExecutiveOperatorSupervisorError(
                "operator Attempt did not reach durable COMPLETED"
            )
        return OrchestrationDispatchOutcome(
            command_id=(
                f"coo-cycle:{job.root_job_id}:dispatch:{job.job_id}:attempt:"
                f"{job.attempt_count + 1}"
            ),
            job_id=job.job_id,
            attempt=current,
            outcome="TERMINAL",
        )

    async def start_cycle_job(
        self, job_id: str, *, command_id: str
    ) -> OrchestrationDispatchOutcome:
        job = self.runtime.jobs.get_job(job_id)
        if job is None:
            raise StateConflict(f"job {job_id!r} does not exist")
        if job.orchestration_role != "plan":
            raise StateConflict("App Server supervisor accepts only planner Jobs")
        outcome = self.runtime.attempts.dispatch_cycle_job(
            job_id,
            command_id=command_id,
            lease_owner=self.instance_id,
        )
        if outcome is None:
            raise ExecutiveOperatorSupervisorError(
                f"no exact Operator Harness capacity for {job_id}"
            )
        if (
            outcome.outcome == "TERMINAL"
            or outcome.attempt.status is not AttemptStatus.CLAIMED
        ):
            return outcome
        if outcome.lease_token is None:
            raise ExecutiveOperatorSupervisorError(
                "operator dispatch lost its lease token"
            )
        lease = AttemptLease(outcome.attempt, outcome.lease_token)
        # All remote proxy methods are deliberately synchronous so the frozen
        # orchestrator cannot hide provider calls inside an event loop.
        completed = await asyncio.to_thread(self._run_claimed, job, lease)
        if completed.outcome != "TERMINAL":
            # A domain post-claim path returns a real nonterminal
            # (ACTIVE) outcome here.  Propagate it unchanged so the
            # upstream caller observes the same checkpointed Attempt
            # instead of an unconditional TERMINAL.  The flat planner
            # path still falls through to the wrapping TERMINAL below.
            return OrchestrationDispatchOutcome(
                command_id=command_id,
                job_id=completed.job_id,
                attempt=completed.attempt,
                outcome=completed.outcome,
                lease_token=completed.lease_token,
                claimed_now=completed.claimed_now,
            )
        return OrchestrationDispatchOutcome(
            command_id=command_id,
            job_id=completed.job_id,
            attempt=completed.attempt,
            outcome="TERMINAL",
        )

    def _recover_one(
        self, attempt_id: str
    ) -> ReconcileReceipt:
        previous = self.runtime.attempts.get_attempt(attempt_id)
        if previous is None:
            raise ExecutiveOperatorSupervisorError(
                "operator recovery Attempt disappeared"
            )
        previous_job = self.runtime.jobs.get_job(previous.job_id)
        if previous_job is not None and previous_job.constraints.get(
            "execution_profile_id"
        ) == INTERACTIVE_TX5_EXECUTION_PROFILE:
            return ReconcileReceipt(
                attempt_id=attempt_id,
                job_id=previous.job_id,
                status=ReconcileStatus.AWAITING_LEASE_EXPIRY,
                process_was_live=False,
            )
        # Domain post-claim path: an Attempt whose initial plan was sealed
        # only as a typed checkpoint (or whose process crashed after that
        # seal but before the checkpoint reservation) must NOT be
        # terminalized here merely because the plan seal exists.  Preserve
        # the nonterminal domain Attempt and return a bounded pending
        # status until the later same-domain consumption turn.
        #
        # Preservation is authorized by the *live* identity bind observed in
        # the current epoch/generation rows, never by a historical event
        # receipt.  An earlier ``OPERATOR_OPERATION_EFFECT_UNKNOWN``
        # checkpoint event is not authority: the same nonterminal state is
        # produced when the initial plan was sealed and the process crashed
        # before the checkpoint reservation wrote any event.  Requiring that
        # historical receipt is what let a live initial-plan state fall
        # through to ordinary takeover and be finalized as a completed
        # result below.
        domain_preserve = bool(
            previous_job is not None
            and previous_job.constraints.get("execution_profile_id")
            == COO_DOMAIN_EXECUTION_PROFILE
            and previous.status
            in {AttemptStatus.CHECKPOINTED, AttemptStatus.RUNNING}
        )
        if domain_preserve:
            # The preserved Attempt is only surfaced as pending when exactly
            # one CURRENT epoch of THIS Attempt still owns the executive
            # writer, and that held writer belongs to that same CURRENT
            # epoch.  Counting a held writer from an unrelated or stale epoch
            # would otherwise satisfy a naive (1, 1) match and grant live
            # authority to a dead generation.  Missing, ambiguous or stale
            # identity fails closed: it neither claims live success nor
            # terminalizes from the initial-plan seal.
            with self.runtime.store.read() as connection:
                domain_authority = connection.execute(
                    """
                    SELECT
                      (SELECT COUNT(*) FROM harness_session_epochs
                       WHERE attempt_id=? AND state='CURRENT') AS current_epochs,
                      (SELECT COUNT(*) FROM process_generations g
                       JOIN harness_session_epochs e
                         ON e.session_epoch_id=g.session_epoch_id
                       WHERE e.attempt_id=? AND e.state='CURRENT'
                         AND g.executive_writer_held=1) AS current_writers,
                      (SELECT COUNT(*) FROM process_generations g
                       JOIN harness_session_epochs e
                         ON e.session_epoch_id=g.session_epoch_id
                       WHERE e.attempt_id=?
                         AND g.executive_writer_held=1) AS total_writers
                    """,
                    (attempt_id, attempt_id, attempt_id),
                ).fetchone()
            if domain_authority is None:
                raise ExecutiveOperatorSupervisorError(
                    "operator domain checkpoint authority disappeared"
                )
            if (
                int(domain_authority["current_epochs"]),
                int(domain_authority["current_writers"]),
                int(domain_authority["total_writers"]),
            ) != (1, 1, 1):
                return ReconcileReceipt(
                    attempt_id=attempt_id,
                    job_id=previous.job_id,
                    status=ReconcileStatus.IDENTITY_AMBIGUOUS,
                    process_was_live=False,
                )
            return ReconcileReceipt(
                attempt_id=attempt_id,
                job_id=previous.job_id,
                status=ReconcileStatus.AWAITING_LEASE_EXPIRY,
                process_was_live=False,
            )
        try:
            lease = self.runtime.attempts.takeover_expired_operator_harness(
                attempt_id,
                expected_fence_generation=previous.fence_generation,
                lease_owner=self.instance_id,
                lease_seconds=360,
            )
        except StateConflict:
            current = self.runtime.attempts.get_attempt(attempt_id)
            if current is None or current.status not in {
                AttemptStatus.CLAIMED,
                AttemptStatus.RUNNING,
                AttemptStatus.CHECKPOINTED,
                AttemptStatus.CANCEL_REQUESTED,
            }:
                raise
            return ReconcileReceipt(
                attempt_id=attempt_id,
                job_id=current.job_id,
                status=ReconcileStatus.AWAITING_LEASE_EXPIRY,
                process_was_live=False,
            )

        job = self.runtime.jobs.get_job(lease.attempt.job_id)
        if job is None:
            raise ExecutiveOperatorSupervisorError(
                "operator recovery Job disappeared"
            )
        if lease.attempt.status is AttemptStatus.CANCEL_REQUESTED:
            with self.runtime.store.read() as connection:
                authority = connection.execute(
                    """
                    SELECT
                      (SELECT COUNT(*) FROM harness_session_epochs
                       WHERE attempt_id=? AND state='CURRENT') AS current_epochs,
                      (SELECT COUNT(*) FROM process_generations g
                       JOIN harness_session_epochs e
                         ON e.session_epoch_id=g.session_epoch_id
                       WHERE e.attempt_id=? AND g.executive_writer_held=1) AS writers
                    """,
                    (attempt_id, attempt_id),
                ).fetchone()
            if authority is None:
                raise ExecutiveOperatorSupervisorError(
                    "operator cancellation authority disappeared"
                )
            cardinality = (
                int(authority["current_epochs"]),
                int(authority["writers"]),
            )
            if cardinality == (0, 0):
                self.runtime.attempts.acknowledge_cancel(
                    attempt_id,
                    fence_generation=lease.attempt.fence_generation,
                    lease_token=lease.lease_token,
                )
                return ReconcileReceipt(
                    attempt_id=attempt_id,
                    job_id=lease.attempt.job_id,
                    status=ReconcileStatus.MISSING_CANCELLED,
                    process_was_live=False,
                )
            if cardinality != (1, 1):
                return ReconcileReceipt(
                    attempt_id=attempt_id,
                    job_id=lease.attempt.job_id,
                    status=ReconcileStatus.IDENTITY_AMBIGUOUS,
                    process_was_live=False,
                )
        process_was_live = False
        try:
            session, existing_turn = self._recovery_session(
                lease,
                require_turn=False,
            )
            prompt = self._prompt(job, lease)
            adapter = self._adapter_for_attempt(
                lease, session.launch.requested, lambda _turn: prompt, recovery=True
            )
            orchestrator = self._orchestrator(lease, adapter)
            port = ExecutiveOperatorHarnessPort(self.runtime, lease)
            try:
                observation = orchestrator.reconcile(session)
            except RemoteBrokerError as exc:
                if exc.code != "BrokerStateError":
                    raise
                config_digest = str(
                    session.observed.effective_config_digest or ""
                )
                if re.fullmatch(r"[0-9a-f]{64}", config_digest) is None:
                    raise ExecutiveOperatorSupervisorError(
                        "operator recovery has no exact config digest"
                    ) from exc
                observation = adapter.reconcile_absence(
                    session.generation,
                    process=session.observation.process,
                    provider_session_id=str(
                        session.observation.provider_session_id or ""
                    ),
                    config_digest=config_digest,
                )
                port.observe_operator_reconcile(
                    lease.attempt.attempt_id,
                    session.generation,
                    observation,
                )
            process_was_live = (
                observation.process_liveness is ProcessLiveness.ALIVE
            )
            if lease.attempt.status is AttemptStatus.CANCEL_REQUESTED:
                if (
                    observation.process_liveness is ProcessLiveness.ALIVE
                    and observation.provider_writer_state is ProviderWriterState.HELD
                ):
                    observation = orchestrator.cancel(
                        session,
                        operation_id=OperationId(
                            f"ohf-op:recover-cancel:{attempt_id}"
                        ),
                        reason="durable Executive Runtime cancellation request",
                    )
                if (
                    observation.process_liveness is not ProcessLiveness.PROVEN_DEAD
                    or observation.provider_writer_state
                    is not ProviderWriterState.RELEASED
                ):
                    return ReconcileReceipt(
                        attempt_id=attempt_id,
                        job_id=lease.attempt.job_id,
                        status=ReconcileStatus.LIVE_QUARANTINED,
                        process_was_live=process_was_live,
                    )
                self.runtime.operator_harness.abandon_epoch(
                    epoch=session.epoch,
                    fence_generation=lease.attempt.fence_generation,
                    lease_token=lease.lease_token,
                )
                self.runtime.attempts.acknowledge_cancel(
                    attempt_id,
                    fence_generation=lease.attempt.fence_generation,
                    lease_token=lease.lease_token,
                )
                return ReconcileReceipt(
                    attempt_id=attempt_id,
                    job_id=lease.attempt.job_id,
                    status=ReconcileStatus.MISSING_CANCELLED,
                    process_was_live=process_was_live,
                )
            sealed_result_json = self._sealed_role_result_json(job, lease)
            if sealed_result_json is not None:
                if (
                    observation.process_liveness is ProcessLiveness.ALIVE
                    and observation.provider_writer_state is ProviderWriterState.HELD
                ):
                    observation = orchestrator.graceful_stop(
                        session,
                        operation_id=OperationId(
                            f"ohf-op:recover-stop-sealed:{attempt_id}"
                        ),
                    )
                if (
                    observation.process_liveness is not ProcessLiveness.PROVEN_DEAD
                    or observation.provider_writer_state
                    is not ProviderWriterState.RELEASED
                ):
                    return ReconcileReceipt(
                        attempt_id=attempt_id,
                        job_id=lease.attempt.job_id,
                        status=ReconcileStatus.LIVE_QUARANTINED,
                        process_was_live=process_was_live,
                    )
                self._complete_after_shutdown(
                    job=job,
                    lease=lease,
                    session=session,
                    canonical_result_json=sealed_result_json,
                    artifact_receipt_digest=(
                        self._terminal_artifact_receipt_digest(
                            session=session, adapter=adapter
                        )
                    ),
                )
                current = self.runtime.attempts.get_attempt(attempt_id)
                if current is None or current.status is not AttemptStatus.COMPLETED:
                    raise ExecutiveOperatorSupervisorError(
                        "sealed operator result did not complete after shutdown"
                    )
                return ReconcileReceipt(
                    attempt_id=attempt_id,
                    job_id=current.job_id,
                    status=ReconcileStatus.OPERATOR_RECOVERED,
                    process_was_live=process_was_live,
                )
            if (
                observation.process_liveness is ProcessLiveness.ALIVE
                and observation.provider_writer_state is ProviderWriterState.HELD
            ):
                if existing_turn is None:
                    turn = orchestrator.run_turn(
                        session,
                        operation_id=OperationId(
                            f"ohf-op:recover-first-turn:{attempt_id}"
                        ),
                        timeout_seconds=300.0,
                    )
                    raw = adapter.observe_raw_role_result(turn.turn)
                else:
                    cursor = EventCursor(
                        attempt_id=session.attempt_id,
                        session_epoch_id=session.epoch.session_epoch_id,
                        process_generation_id=(
                            session.generation.process_generation_id
                        ),
                        turn_id=existing_turn.turn_id,
                    )
                    events, next_cursor = adapter.read_events(
                        cursor, timeout_seconds=300.0
                    )
                    candidate = adapter.collect_candidate_result(existing_turn)
                    raw = adapter.observe_raw_role_result(existing_turn)
                    port.finish_operator_candidate(
                        session.attempt_id,
                        existing_turn,
                        candidate,
                        events,
                        next_cursor,
                    )
                    port.seal_operator_role_result(
                        session.attempt_id, existing_turn, raw
                    )
                self._complete_after_stop(
                    job=job,
                    lease=lease,
                    session=session,
                    adapter=adapter,
                    canonical_result_json=raw.canonical_result_json,
                    stop_operation=OperationId(
                        f"ohf-op:recover-stop-live:{attempt_id}"
                    ),
                )
            elif (
                observation.process_liveness is ProcessLiveness.PROVEN_DEAD
                and observation.provider_writer_state
                is ProviderWriterState.RELEASED
            ):
                provider_session_id = str(
                    session.observation.provider_session_id or ""
                )
                resumed = orchestrator.resume(
                    session,
                    operation_id=OperationId(
                        f"ohf-op:recover-resume:{attempt_id}"
                    ),
                    handoff=ProviderSessionHandoff(
                        provider_session_id=provider_session_id,
                        worker_id=lease.attempt.worker_id,
                    ),
                )
                turn = orchestrator.run_turn(
                    resumed,
                    operation_id=OperationId(
                        f"ohf-op:recover-turn:{attempt_id}"
                    ),
                    timeout_seconds=300.0,
                )
                raw = adapter.observe_raw_role_result(turn.turn)
                self._complete_after_stop(
                    job=job,
                    lease=lease,
                    session=resumed,
                    adapter=adapter,
                    canonical_result_json=raw.canonical_result_json,
                    stop_operation=OperationId(
                        f"ohf-op:recover-stop:{attempt_id}"
                    ),
                )
            else:
                return ReconcileReceipt(
                    attempt_id=attempt_id,
                    job_id=lease.attempt.job_id,
                    status=ReconcileStatus.LIVE_QUARANTINED,
                    process_was_live=process_was_live,
                )
        except Exception:
            # Any ambiguous provider/process effect remains fenced to this
            # same Attempt.  The next reconciliation must inspect it again;
            # no second session or G3 is allocated here.
            return ReconcileReceipt(
                attempt_id=attempt_id,
                job_id=lease.attempt.job_id,
                status=ReconcileStatus.IDENTITY_AMBIGUOUS,
                process_was_live=process_was_live,
            )
        current = self.runtime.attempts.get_attempt(attempt_id)
        if current is None or current.status is not AttemptStatus.COMPLETED:
            return ReconcileReceipt(
                attempt_id=attempt_id,
                job_id=lease.attempt.job_id,
                status=ReconcileStatus.IDENTITY_AMBIGUOUS,
                process_was_live=process_was_live,
            )
        return ReconcileReceipt(
            attempt_id=attempt_id,
            job_id=current.job_id,
            status=ReconcileStatus.OPERATOR_RECOVERED,
            process_was_live=process_was_live,
        )

    def reconcile_restart(
        self, *, requeue_lost: bool = False
    ) -> list[ReconcileReceipt]:
        """Recover exact OHF planner Attempts without cross-Attempt retry."""

        # An Operator Harness recovery either finishes the same Attempt or
        # remains quarantined.  Generic automatic requeue is intentionally not
        # part of this boundary.
        del requeue_lost
        outcomes: list[ReconcileReceipt] = []
        for attempt in self.runtime.attempts.list_attempts():
            if (
                attempt.execution_mode != "OPERATOR_HARNESS"
                or attempt.status
                not in {
                    AttemptStatus.CLAIMED,
                    AttemptStatus.RUNNING,
                    AttemptStatus.CHECKPOINTED,
                    AttemptStatus.CANCEL_REQUESTED,
                }
            ):
                continue
            outcomes.append(self._recover_one(attempt.attempt_id))
        return outcomes


__all__ = ["ExecutiveOperatorSupervisor", "ExecutiveOperatorSupervisorError"]
