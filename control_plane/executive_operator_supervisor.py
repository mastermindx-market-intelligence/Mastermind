"""Executive-owned composition for one read-only operator planning Attempt.

This is not a scheduler and owns no durable state.  It claims one exact
command-bound planner through Executive Runtime, delegates provider effects to
the frozen Operator Harness orchestrator, and terminalizes only after the role
result is sealed, the worker process is proven dead/released, and the epoch is
abandoned.

The explicit native interactive composition reuses that same start/seal and
cleanup path while retaining a transient handle through canonical CONTINUE,
the existing terminal Wake ACK, native.reply, and authenticated parent read.
Executive Runtime remains the only durable session and Attempt authority.
"""
from __future__ import annotations

import asyncio
import copy
import hashlib
import inspect
import json
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from threading import Event
from typing import Any, Callable, Protocol

from control_plane.executive_agent_capabilities import (
    CLAUDE_OPERATOR_EXECUTION_SURFACE,
    CLAUDE_OPERATOR_HARNESS_KIND,
    CLAUDE_OPERATOR_PROVIDER,
    CapabilityPolicyError,
    DSH_NATIVE_CONVERSATION_PROFILE_ID,
    DSH_OPERATOR_EXECUTION_SURFACE,
    ExecutionCapabilityRegistry,
)
from control_plane.executive_operator_harness_port import ExecutiveOperatorHarnessPort
from control_plane.executive_orchestration_result import (
    PLAN_SCHEMA_V1, PLAN_SCHEMA_V3, PLAN_SCHEMA_V4, PLAN_SCHEMA_V5,
    canonical_bytes,
    canonical_digest,
    parse_canonical_json,
)
from control_plane.executive_runtime import (
    NATIVE_RETURN_TX5_EXECUTION_PROFILE,
    Attempt,
    AttemptLease,
    AttemptStatus,
    Job,
    JobPayload,
    OrchestrationDispatchOutcome,
    Runtime,
    StateConflict,
    _dialogue_source_from_root_creation,
    _ohf_json_digest,
)
from control_plane.executive_supervisor import (
    ExecutiveSupervisor,
    ReconcileReceipt,
    ReconcileStatus,
    VerifiedCommission,
    verify_commission_for_job,
    worker_result_schema,
)
from control_plane.operator_harness_contract import (
    AuthRealmRequirement,
    OperatorHarnessAdapter,
    EventCursor,
    LaunchDecision,
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
    OperatorHarnessOrchestrator,
    OperatorEffectUnknown,
    NativeTurnPending,
    OperatorOperationApplied,
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
from control_plane.native_conversation_result import (
    DSH_NATIVE_RESULT_CONTRACT, DSH_NATIVE_HARNESS_KIND, NativeConversationResultAdapter, NativeConversationResultRef,
    result_contract_for_profile,
)


class ExecutiveOperatorSupervisorError(RuntimeError):
    """One exact read-only operator Attempt could not be safely completed."""


@dataclass(frozen=True)
class RetainedNativeOperatorSession:
    """Transient handle held by the existing supervisor; Runtime owns custody."""
    owner: Any = field(repr=False)
    job: Job
    lease: AttemptLease = field(repr=False)
    session: OperatorSessionReceipt
    adapter: Any = field(repr=False)
    canonical_plan_json: str | None = field(default=None, repr=False)
    native_result: NativeConversationResultRef | None = None

    def __post_init__(self) -> None:
        role = type(self.canonical_plan_json) is str and bool(self.canonical_plan_json)
        native = type(self.native_result) is NativeConversationResultRef
        if (role == native or (not role and self.canonical_plan_json is not None)
                or (not native and self.native_result is not None)):
            raise StateConflict("retained result requires exactly one typed result contract")



@dataclass(frozen=True)
class PendingNativeOperatorTurn:
    """Original call custody on the existing dispatch; neither ACK nor result proof."""
    owner: Any = field(repr=False)
    job: Job
    lease: AttemptLease = field(repr=False)
    session: OperatorSessionReceipt
    adapter: Any = field(repr=False)
    turn: TurnRef
    operation_id: OperationId
    cursor: EventCursor | None = None
    foreground_operation: Any = field(default=None, repr=False)
    active_observer: Any = field(default=None, repr=False)


class NativeOperatorRecoveryPending(ExecutiveOperatorSupervisorError):
    def __init__(self, pending):
        if type(pending) is not PendingNativeOperatorTurn:
            raise TypeError("original pending native call required")
        super().__init__("original native turn requires bounded recovery")
        self.pending = pending


@dataclass(frozen=True)
class ActiveNativeOperatorTurn:
    """Observation on the incumbent dispatch, never a second cleanup owner."""
    owner: Any = field(repr=False)
    job: Job
    lease: AttemptLease = field(repr=False)
    session: OperatorSessionReceipt
    adapter: Any = field(repr=False)
    turn: TurnRef
    operation_id: OperationId
    _withdrawn: Event = field(default_factory=Event, init=False, repr=False, compare=False)

    @property
    def withdrawn(self) -> bool:
        return self._withdrawn.is_set()

    def withdraw(self) -> None:
        # Denial-only latch on this exact observation; never rearmed or copied
        # into another writer/cleanup owner.
        self._withdrawn.set()


RemoteAdapterFactory = Callable[
    [Callable[[Any], str]], RemoteCodexOperatorAdapter
]

# Installed host observations for the already-claimed Worker; no placement authority.
ClaimedWorkspaceIdentitySource = Callable[[Attempt, Job], WorkspaceIdentity]
ClaimedWorkspaceIdentitySelector = Callable[[Attempt, Job], bool]


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
        workspace_identity_selector: ClaimedWorkspaceIdentitySelector | None = None,
        plan_schema_version: str | None = None,
        foreground_only: bool = False,
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
        if workspace_identity_selector is not None and (
            not callable(workspace_identity_selector) or workspace_identity_source is None
            or claimed_adapter_factory is None
        ):
            raise ExecutiveOperatorSupervisorError(
                "workspace selection requires the original selected-host source and factory"
            )
        # ``None`` is legacy omission: the retained planner receipt alone decides
        # the contract. Any explicit value is a native-producer opt-in, including
        # V1, so it must arrive through a claim-aware adapter factory.
        if plan_schema_version is not None and (
            type(plan_schema_version) is not str
            or plan_schema_version not in {
                PLAN_SCHEMA_V1, PLAN_SCHEMA_V3, PLAN_SCHEMA_V4, PLAN_SCHEMA_V5,
            }
        ):
            raise ExecutiveOperatorSupervisorError("operator plan schema is not admitted")
        if plan_schema_version is not None and claimed_adapter_factory is None:
            raise ExecutiveOperatorSupervisorError(
                "versioned producer requires a claim-aware adapter factory"
            )
        # This is a fresh-creation preference only. Execution and recovery read
        # the immutable planner receipt, including historical V1 absence. Native
        # producer support is never inferred from claimed factory presence.
        self.plan_schema_version = (
            PLAN_SCHEMA_V1 if plan_schema_version is None else plan_schema_version
        )
        self.fresh_planner_schema_version = plan_schema_version
        if type(foreground_only) is not bool:
            raise ExecutiveOperatorSupervisorError("foreground_only must be boolean")
        self.foreground_only = foreground_only
        self.runtime = runtime
        self.adapter_factory = adapter_factory
        self._claimed_adapter_factory = claimed_adapter_factory
        self._workspace_identity_source = workspace_identity_source
        self._workspace_identity_selector = workspace_identity_selector
        self.prompt_source = prompt_source
        self.instance_id = instance_id

    def _planner_schema(self, job: Job) -> str:
        try:
            binding = self.runtime.jobs.get_planner_producer_binding(job.job_id)
        except StateConflict as exc:
            raise ExecutiveOperatorSupervisorError(str(exc)) from exc
        return PLAN_SCHEMA_V1 if binding is None else binding["plan_schema_version"]

    def _require_adapter_contract(self, job: Job, adapter: OperatorHarnessAdapter) -> None:
        try:
            native = self.runtime.jobs.get_native_conversation_binding(job.job_id)
            binding = self.runtime.jobs.get_planner_producer_binding(job.job_id)
        except StateConflict as exc:
            raise ExecutiveOperatorSupervisorError(str(exc)) from exc
        if native is not None:
            if (binding is not None or getattr(adapter, "result_contract", None) != DSH_NATIVE_RESULT_CONTRACT
                    or not isinstance(adapter, NativeConversationResultAdapter)
                    or getattr(adapter, "plan_contract", None) is not None):
                raise ExecutiveOperatorSupervisorError("native adapter differs from its original result contract")
            return
        if getattr(adapter, "result_contract", None) == DSH_NATIVE_RESULT_CONTRACT:
            raise ExecutiveOperatorSupervisorError("native adapter requires its original native creator")
        declared = getattr(adapter, "plan_contract", None)
        # A historical V1 transport remains historical. Schema support alone
        # must not promote that transport into a versioned native producer.
        if binding is None:
            if declared not in (None, "executive-plan-v1"):
                raise ExecutiveOperatorSupervisorError("legacy adapter plan contract must remain V1")
        elif declared != binding["native_result_contract"]["name"]:
            raise ExecutiveOperatorSupervisorError(
                "claim-bound adapter plan contract differs from retained producer binding"
            )

    def _adapter_for_attempt(
        self, lease: AttemptLease, requested: RequestedExecutionProfile,
        loader: Callable[[Any], str], *, recovery: bool,
        expected_recovery_seal: str | None = None,
        expected_native_result: NativeConversationResultRef | None = None,
    ) -> OperatorHarnessAdapter:
        factory = self._claimed_adapter_factory
        initial_job = self.runtime.jobs.get_job(lease.attempt.job_id)
        if initial_job is None:
            raise ExecutiveOperatorSupervisorError("planner Job disappeared before construction")
        native_binding = self.runtime.jobs.get_native_conversation_binding(initial_job.job_id)
        native = native_binding is not None
        if native and result_contract_for_profile(requested) != DSH_NATIVE_RESULT_CONTRACT:
            raise ExecutiveOperatorSupervisorError("native factory requires the original sealed native profile")
        if expected_native_result is not None and (not native or not recovery):
            raise ExecutiveOperatorSupervisorError("native history belongs to exact native recovery only")
        native_history = (None if expected_native_result is None else
            self.runtime.operator_harness.native_conversation_result(
                attempt_id=lease.attempt.attempt_id, reference=expected_native_result))
        retained_seal = expected_recovery_seal
        if native and retained_seal is not None:
            raise ExecutiveOperatorSupervisorError("native recovery cannot consume a planner result")
        if recovery and not native and lease.attempt.status is not AttemptStatus.CANCEL_REQUESTED:
            if self._sealed_role_result_json(initial_job, lease) != retained_seal:
                raise ExecutiveOperatorSupervisorError("retained role-result seal changed before construction")
        elif retained_seal is not None:
            raise ExecutiveOperatorSupervisorError("result consumption requires non-cancelled recovery")
        containment = recovery and (
            lease.attempt.status is AttemptStatus.CANCEL_REQUESTED or retained_seal is not None
        )
        if not containment:
            if native:
                self.runtime.jobs.assert_native_conversation_execution(initial_job.job_id)
            else:
                self.runtime.jobs.assert_frontier_planner_execution(initial_job.job_id)
        producer = (None if containment else
                    self.runtime.jobs.get_planner_producer_binding(initial_job.job_id))
        if factory is None and (producer is not None or native):
            raise ExecutiveOperatorSupervisorError("bound planner requires a claim-aware adapter factory")
        if factory is None and not recovery:
            assert self.adapter_factory is not None
            adapter = self.adapter_factory(loader)
            self._require_adapter_contract(initial_job, adapter)
            return adapter

        # Construction must not start a provider. Runtime retains the lease and
        # final effect admission; the callback receives no lease token or new authority.
        def current_binding() -> tuple[Attempt, tuple[Any, ...]]:
            current = self.runtime.attempts.get_attempt(lease.attempt.attempt_id)
            allowed = ({AttemptStatus.CLAIMED, AttemptStatus.RUNNING,
                        AttemptStatus.CHECKPOINTED, AttemptStatus.CANCEL_REQUESTED}
                       if recovery else {AttemptStatus.CLAIMED})
            if (containment or producer is not None or native) and not isinstance(
                requested, RequestedExecutionProfile
            ):
                raise ExecutiveOperatorSupervisorError("bound planner requested profile is invalid")
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
            if (recovery and not native and current.status is not AttemptStatus.CANCEL_REQUESTED
                    and self._sealed_role_result_json(
                        job, AttemptLease(current, lease.lease_token)
                    ) != retained_seal):
                raise ExecutiveOperatorSupervisorError("retained role-result seal moved during containment")
            current_native = self.runtime.jobs.get_native_conversation_binding(job.job_id)
            if current_native != native_binding:
                raise ExecutiveOperatorSupervisorError("native creator binding moved during construction")
            if expected_native_result is not None and self.runtime.operator_harness.native_conversation_result(
                    attempt_id=current.attempt_id, reference=expected_native_result) != native_history:
                raise ExecutiveOperatorSupervisorError("native historical result changed during construction")
            if not containment:
                if native:
                    self.runtime.jobs.assert_native_conversation_execution(job.job_id)
                else:
                    self.runtime.jobs.assert_frontier_planner_execution(job.job_id)
            current_producer = (None if containment else
                self.runtime.jobs.get_planner_producer_binding(job.job_id))
            if current_producer != producer:
                raise ExecutiveOperatorSupervisorError("planner producer binding moved during construction")
            if containment or producer is not None or native:
                # Containment consumes the recorded execution identity, even if
                # current quota metadata or producer defaults have changed.
                if current.requested_execution_profile is not None:
                    if (_ohf_json_digest(requested)[1] != current.requested_execution_profile_digest
                            or requested_execution_profile(current.requested_execution_profile) != requested):
                        raise ExecutiveOperatorSupervisorError("bound planner sealed profile differs")
                elif recovery or requested != self._requested_profile(job, AttemptLease(current, lease.lease_token)):
                    raise ExecutiveOperatorSupervisorError("bound planner requested profile differs from its Job")
            if not containment and (producer is not None or native):
                quota = self.runtime.workers.get_quota_class(current.worker_id, current.quota_class)
                if (quota is None or quota.active_attempt_id != current.attempt_id
                        or quota.active_job_id != job.job_id
                        or quota.fence_generation != current.fence_generation
                        or current.quota_class not in job.constraints["eligible_quota_classes"]
                        or quota.provider != job.constraints["provider"]
                        or quota.model != job.constraints["model"]
                        or quota.effort != job.constraints["effort"]
                        or quota.cost_class != job.constraints["cost_class"]
                        or any(quota.metadata.get(key) != job.constraints[key] for key in (
                            "routing_policy_version", "execution_profile_id", "execution_profile_digest",
                            "capability_policy_version", "capability_policy_digest",
                            "harness_binary_digest", "harness_version"))):
                    raise ExecutiveOperatorSupervisorError("bound planner quota execution identity moved")
            signature = tuple(getattr(current, key) for key in identity) + (
                current.status, current.execution_mode,
                current.requested_execution_profile_digest,
                current.effective_grant_digest, current.placement_snapshot_digest,
                current.execution_principal_snapshot_digest, job.status,
                canonical_digest(current_producer) if current_producer is not None else None,
                canonical_digest(current_native) if current_native is not None else None,
                canonical_digest(native_history) if native_history is not None else None,
            )
            return current, signature

        current, before = current_binding()
        try:
            if factory is None:
                assert self.adapter_factory is not None
                adapter = self.adapter_factory(loader)
            else:
                adapter = factory(copy.deepcopy(current), copy.deepcopy(requested),
                                  loader, recovery=recovery)
        except Exception:
            raise ExecutiveOperatorSupervisorError("claimed operator construction refused") from None
        _, after = current_binding()
        if before != after:
            raise ExecutiveOperatorSupervisorError("claimed operator binding changed during construction")
        if not containment or native:
            self._require_adapter_contract(initial_job, adapter)
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

    def _workspace_source_for(self, job: Job, attempt: Attempt | None):
        source = self._workspace_identity_source
        selector = self._workspace_identity_selector
        if source is None or selector is None:
            return source
        if attempt is None:
            raise ExecutiveOperatorSupervisorError("workspace selection has no claimed Attempt")
        try:
            selected = selector(copy.deepcopy(attempt), copy.deepcopy(job))
        except Exception:
            raise ExecutiveOperatorSupervisorError("original workspace selection refused") from None
        if type(selected) is not bool:
            if inspect.iscoroutine(selected):
                selected.close()
            raise ExecutiveOperatorSupervisorError("workspace selection is not an exact boolean")
        return source if selected else None

    def _workspace_identity(
        self, job: Job, attempt: Attempt | None = None
    ) -> WorkspaceIdentity:
        source = self._workspace_source_for(job, attempt)
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
            profile = registry.resolve(
                str(job.constraints.get("execution_profile_id") or "")
            )
        except CapabilityPolicyError as exc:
            raise ExecutiveOperatorSupervisorError(
                f"operator capability policy is invalid: {exc}"
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
        )
        native_binding = self.runtime.jobs.get_native_conversation_binding(job.job_id)
        native_conversation_profile_ok = (
            native_binding is not None
            and profile.profile_id == DSH_NATIVE_CONVERSATION_PROFILE_ID
            and profile.enabled is True
            and profile.execution_surface == DSH_OPERATOR_EXECUTION_SURFACE
            and profile.network_policy == "disabled"
            and profile.native_helper_policy.value == "DISABLED"
            and profile.native_helper is None
            and not profile.skill_grants
            and not profile.mcp_servers and not profile.mcp_server_grants
            and not profile.resource_grants and not profile.validation_resource_grants
            and profile.plugins == ("mastermind-company",)
            and not profile.forbidden
        )
        common_profile_ok = common_profile_ok and (
            native_conversation_profile_ok or not profile.plugins)
        docs_profile_ok = (
            profile.profile_id
            in {
                "operator.appserver.readonly.docs-mcp.native-helper.v1",
                "operator.appserver.readonly.docs-mcp.native-helper.sol61.v1",
            }
            and profile.execution_surface == "codex-app-server"
            and profile.network_policy == "disabled"
            and profile.native_helper_policy.value == "PARENT_READ_ONLY_CEILING"
            and profile.native_helper is not None
            and profile.native_helper.default_model == str(quota.model)
            and profile.native_helper.default_reasoning_effort == str(quota.effort)
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
        native_return_profile_ok = (
            profile.profile_id == "operator.appserver.interactive.native-return.v1"
            and profile.execution_surface == "codex-app-server"
            and profile.network_policy == "disabled"
            and profile.native_helper_policy.value == "DISABLED"
            and profile.native_helper is None
            and not profile.skill_grants
            and not profile.resource_grants
            and profile.mcp_servers == ("native-return-mcp-v1",)
            and profile.mcp_server_grants == (
                registry.mcp_servers.get("native-return-mcp-v1"),
            )
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
        if not common_profile_ok or not (
            docs_profile_ok or browser_profile_ok or native_return_profile_ok
            or native_claude_profile_ok or native_conversation_profile_ok
        ):
            raise ExecutiveOperatorSupervisorError(
                "operator planner profile is not one reviewed rich read-only lane"
            )
        if native_binding is not None:
            if (not native_conversation_profile_ok
                    or quota.provider != "acp" or job.constraints.get("provider") != "acp"):
                raise ExecutiveOperatorSupervisorError("native conversation profile or provider drifted")
            self.runtime.jobs.assert_native_conversation_execution(job.job_id)
        if native_return_profile_ok and (
            quota.provider != "codex" or job.constraints.get("provider") != "codex"
        ):
            raise ExecutiveOperatorSupervisorError(
                "native Codex return planner provider drifted after claim"
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
            provider=(
                "acp" if native_conversation_profile_ok else
                CLAUDE_OPERATOR_PROVIDER if native_claude_profile_ok else "openai-codex"
            ),
            requested_model=str(quota.model),
            harness_kind=(
                DSH_NATIVE_HARNESS_KIND if native_conversation_profile_ok else
                CLAUDE_OPERATOR_HARNESS_KIND
                if native_claude_profile_ok else "codex-app-server"
            ),
            harness_binary_digest=harness_digest,
            harness_version=harness_version,
            # Supply the claim to the original helper when host selection is
            # composed. That helper alone decides remote versus local identity.
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

    def _prompt(
        self,
        job: Job,
        lease: AttemptLease,
        commission: VerifiedCommission | None = None,
    ) -> str:
        grant = ExecutiveSupervisor._effective_grant(job, lease.attempt)
        version = (PLAN_SCHEMA_V1 if lease.attempt.status is AttemptStatus.CANCEL_REQUESTED
                   else self._planner_schema(job))
        schema = worker_result_schema(
            job_id=job.job_id,
            run_id=lease.attempt.attempt_id,
            worker_id=lease.attempt.worker_id,
            effective_grant_digest=lease.attempt.effective_grant_digest,
            orchestration_role="plan",
            root_job_id=job.root_job_id,
            plan_schema_version=version,
            coordinator_job_id=(job.parent_job_id if version == PLAN_SCHEMA_V5 else None),
        )
        base_prompt = (
            self.prompt_source._prompt(job, lease.attempt, grant)
            if commission is None
            else self.prompt_source._prompt(
                job,
                lease.attempt,
                grant,
                commission=commission.ref_dict(),
                inline_commission=commission.content.decode("utf-8"),
            )
        )
        return (
            base_prompt
            + "\n\nThe output schema is embedded below because this App Server lane "
            "has no separate schema-file argument. Return exactly one minified, "
            "UTF-8 JSON object with keys recursively sorted lexicographically, no "
            "markdown fence, no leading BOM, no trailing newline, and no commentary.\n"
            + json.dumps(schema, sort_keys=True, ensure_ascii=False, indent=2)
        )

    @staticmethod
    def _turn_operation_id(
        attempt_id: str,
        commission: VerifiedCommission | None,
    ) -> OperationId:
        """Bind commission-bearing TX-5 to stable immutable input identity.

        The model-visible prompt may include observational routing capacity that
        legitimately changes between the original turn and restart. Recovery
        identity therefore binds the durable Attempt to the exact immutable
        commission reference/content digest rather than re-hashing ambient
        routing observations. Source-free jobs retain their historical identity.
        """

        return ExecutiveOperatorSupervisor._commission_turn_operation_id(
            attempt_id, None if commission is None else commission.ref_dict()
        )

    @staticmethod
    def _commission_turn_operation_id(
        attempt_id: str, commission_ref: dict[str, str] | None,
    ) -> OperationId:
        if commission_ref is None:
            return OperationId(f"ohf-op:turn:{attempt_id}")
        binding = {
            "schema_version": "mastermind.operator_turn_commission_binding/v1",
            "attempt_id": attempt_id,
            "commission_ref": commission_ref,
        }
        binding_digest = hashlib.sha256(
            json.dumps(
                binding,
                sort_keys=True,
                ensure_ascii=False,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8", errors="strict")
        ).hexdigest()
        return OperationId(f"ohf-op:turn-commission:{binding_digest}")

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
        canonical_result_json: str | None,
        stop_operation: OperationId,
        native_result: NativeConversationResultRef | None = None,
    ) -> None:
        if (native_result is None) == (canonical_result_json is None):
            raise StateConflict("terminal cleanup requires exactly one result contract")
        orchestrator = self._orchestrator(lease, adapter)
        stopped = orchestrator.graceful_stop(
            session, operation_id=stop_operation,
            **({"native_terminal_result": native_result} if native_result is not None else {}),
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
            native_result=native_result,
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

    def _native_finalization_state(
        self, *, job: Job, lease: AttemptLease, session: OperatorSessionReceipt,
        reference: NativeConversationResultRef,
    ) -> dict[str, Any]:
        """Inspect the original owner, latest physical target and close receipts."""
        from control_plane.executive_runtime import _strict_canonical_json_loads
        if (type(reference) is not NativeConversationResultRef
                or session.attempt_id != lease.attempt.attempt_id
                or job.job_id != lease.attempt.job_id):
            raise StateConflict("native finalization identity differs")
        result = self.runtime.operator_harness.native_conversation_result(
            attempt_id=session.attempt_id, reference=reference)
        if (result["job_id"] != job.job_id
                or result["turn"]["session_epoch_id"] != session.epoch.session_epoch_id
                or result["observation"]["provider_session_id"] != session.observation.provider_session_id):
            raise StateConflict("native finalization result belongs to another Session")
        with self.runtime.store.read() as connection:
            row = connection.execute("SELECT * FROM attempts WHERE attempt_id=?", (session.attempt_id,)).fetchone()
            current_job = connection.execute("SELECT * FROM jobs WHERE job_id=?", (job.job_id,)).fetchone()
            if (row is None or current_job is None or row["job_id"] != job.job_id
                    or current_job["current_attempt_id"] != session.attempt_id
                    or row["worker_id"] != lease.attempt.worker_id
                    or row["quota_class"] != lease.attempt.quota_class):
                raise StateConflict("native finalization lost its original Job and Attempt")
            status = str(row["status"])
            if status not in {AttemptStatus.COMPLETED.value, AttemptStatus.CANCELLED.value}:
                row = self.runtime.operator_harness._leased(connection,
                    attempt_id=session.attempt_id, fence_generation=lease.attempt.fence_generation,
                    lease_token=lease.lease_token, timestamp=self.runtime.store.now_ms(),
                    statuses={AttemptStatus.RUNNING, AttemptStatus.CHECKPOINTED, AttemptStatus.CANCEL_REQUESTED})
            generation = self.runtime.operator_harness._owned_generation(connection,
                leased=row, epoch=session.epoch, generation=session.generation)
            latest = connection.execute(
                "SELECT process_generation_id FROM process_generations WHERE session_epoch_id=? ORDER BY generation_number DESC LIMIT 1",
                (session.epoch.session_epoch_id,)).fetchone()
            process = session.observation.process
            if (latest is None or latest[0] != session.generation.process_generation_id
                    or generation["provider_session_id"] != session.observation.provider_session_id
                    or generation["epoch_session"] != session.observation.provider_session_id
                    or (generation["pid"], generation["pgid"], generation["process_start_identity"], generation["boot_id"])
                       != (process.pid, process.pgid, process.process_start_identity, process.boot_id)
                    or generation["observed_attestation_digest"] != _ohf_json_digest(session.observed)[1]):
                raise StateConflict("native finalization target is not the latest exact physical generation")
            closing = connection.execute(
                """SELECT 1 FROM events WHERE aggregate_type='operator_operation' AND event_type=?
                   AND attempt_id=? AND json_extract(payload_json,'$.process_generation_id')=?
                   AND json_extract(payload_json,'$.operation_kind') IN ('graceful_stop','cancel') LIMIT 1""",
                (OperationReceiptKind.INTENT.value, session.attempt_id, session.generation.process_generation_id),
            ).fetchone() is not None
            abandoned_event_id = None
            if generation["state"] == "ABANDONED":
                closed = connection.execute(
                    "SELECT * FROM process_generations WHERE session_epoch_id=? ORDER BY generation_number",
                    (session.epoch.session_epoch_id,)).fetchall()
                if (len(closed) not in {1, 2} or any(g["executive_writer_held"] for g in closed)
                        or [int(g["generation_number"]) for g in closed] != list(range(1, len(closed) + 1))):
                    raise StateConflict("native abandoned generation history differs")
                closure_events = [self.runtime.operator_harness._validated_generation_closure_event(
                    connection, row=row, generation=g, provider_session_id=session.observation.provider_session_id) for g in closed]
                abandoned_event_id = self.runtime.operator_harness._validated_epoch_abandonment_event(
                    connection, row=row, epoch=session.epoch, closure_events=closure_events)
            if status == AttemptStatus.COMPLETED.value:
                self.runtime.operator_harness._native_conversation_terminal_payload(
                    connection, row=row, job=current_job, reference=reference)
            if status == AttemptStatus.CANCELLED.value:
                cancelled = connection.execute(
                    "SELECT * FROM events WHERE attempt_id=? AND event_type='JOB_CANCELLED'",
                    (session.attempt_id,)).fetchall()
                held = connection.execute("SELECT 1 FROM worker_quota_classes WHERE held_attempt_id=? LIMIT 1",
                                          (session.attempt_id,)).fetchone()
                if (abandoned_event_id is None or current_job["status"] != AttemptStatus.CANCELLED.value
                        or row["lease_token"] is not None or row["finished_at_ms"] is None or held is not None
                        or len(cancelled) != 1 or cancelled[0]["aggregate_type"] != "job"
                        or cancelled[0]["aggregate_id"] != job.job_id or cancelled[0]["job_id"] != job.job_id
                        or cancelled[0]["worker_id"] != row["worker_id"] or cancelled[0]["quota_class"] != row["quota_class"]
                        or cancelled[0]["actor"] != "operator"
                        or int(cancelled[0]["event_id"]) <= abandoned_event_id
                        or _strict_canonical_json_loads(str(cancelled[0]["payload_json"]), name="native cancellation") != {}):
                    raise StateConflict("native cancellation lost its original atomic terminal proof")
            return {"status": status, "epoch_state": str(generation["state"]),
                    "ended": generation["ended_at_ms"] is not None,
                    "released": generation["provider_writer_state"] == ProviderWriterState.RELEASED.value,
                    "closing": closing}

    def _complete_native_after_shutdown(
        self, *, job: Job, lease: AttemptLease, session: OperatorSessionReceipt,
        reference: NativeConversationResultRef,
    ) -> None:
        def state():
            return self._native_finalization_state(job=job, lease=lease, session=session, reference=reference)
        current = state()
        if current["status"] in {AttemptStatus.COMPLETED.value, AttemptStatus.CANCELLED.value}:
            return
        if not current["ended"] or not current["released"]:
            raise StateConflict("native finalization still requires exact physical closure")
        if current["epoch_state"] == "CURRENT":
            try:
                self.runtime.operator_harness.abandon_epoch(
                    epoch=session.epoch, generation=session.generation,
                    **({} if current["status"] == AttemptStatus.CANCEL_REQUESTED.value else {"native_terminal_result": reference}),
                    fence_generation=lease.attempt.fence_generation, lease_token=lease.lease_token)
            except Exception:
                # Reconcile the original transaction's result; never replay TX8
                # merely because its return was lost.
                current = state()
                if current["epoch_state"] != "ABANDONED":
                    raise
        elif current["epoch_state"] != "ABANDONED":
            raise StateConflict("native finalization epoch is neither current nor abandoned")
        current = state()
        if current["status"] in {AttemptStatus.COMPLETED.value, AttemptStatus.CANCELLED.value}:
            return
        lease_options = dict(fence_generation=lease.attempt.fence_generation, lease_token=lease.lease_token)
        if current["status"] != AttemptStatus.CANCEL_REQUESTED.value:
            payload = self.runtime.operator_harness.native_conversation_terminal_payload(
                attempt_id=session.attempt_id, reference=reference)
            try:
                self.runtime.attempts.complete_attempt(session.attempt_id, payload=payload, **lease_options)
                return
            except Exception:
                current = state()
                if current["status"] in {AttemptStatus.COMPLETED.value, AttemptStatus.CANCELLED.value}:
                    return
                if current["status"] != AttemptStatus.CANCEL_REQUESTED.value:
                    raise
        # Durable cancellation continues through its original acknowledgment.
        # A sealed useful result never upgrades cancellation to completion.
        try:
            self.runtime.attempts.acknowledge_cancel(session.attempt_id, **lease_options)
        except Exception:
            if state()["status"] != AttemptStatus.CANCELLED.value:
                raise

    def _finish_native_conversation(self, retained: RetainedNativeOperatorSession) -> None:
        if type(retained) is not RetainedNativeOperatorSession or retained.owner is not self:
            raise StateConflict("retained native handle belongs to another owner")
        self.runtime.operator_harness.native_conversation_result(
            attempt_id=retained.session.attempt_id, reference=retained.native_result)
        reference = self.runtime.operator_harness.latest_native_conversation_result(
            attempt_id=retained.session.attempt_id)
        current = self._native_finalization_state(
            job=retained.job, lease=retained.lease, session=retained.session, reference=reference)
        if current["status"] in {AttemptStatus.COMPLETED.value, AttemptStatus.CANCELLED.value}:
            return
        if current["epoch_state"] == "ABANDONED":
            self._complete_native_after_shutdown(job=retained.job, lease=retained.lease,
                                                session=retained.session, reference=reference)
            return
        orchestrator = self._orchestrator(retained.lease, retained.adapter)
        if not current["closing"] and not current["ended"]:
            if current["status"] == AttemptStatus.CANCEL_REQUESTED.value:
                if not self._cleanup_failed_session(lease=retained.lease, orchestrator=orchestrator,
                        handle=retained.session, stop_operation=self._retained_stop_operation(retained),
                        reason="durable Executive Runtime cancellation request"):
                    raise StateConflict("native cancellation still requires original reconciliation")
                return
            self._require_retained_native(retained)
            try:
                self._complete_after_stop(job=retained.job, lease=retained.lease, session=retained.session,
                    adapter=retained.adapter, canonical_result_json=None, native_result=reference,
                    stop_operation=self._retained_stop_operation(retained))
                return
            except (OperatorEffectUnknown, OperatorOperationApplied):
                # The original INTENT owns the provider effect. Inspect that
                # exact physical target once; never dispatch a second Stop.
                self._native_finalization_state(job=retained.job, lease=retained.lease,
                                                session=retained.session, reference=reference)
        observed = orchestrator.reconcile(retained.session)
        if (observed.process_liveness is not ProcessLiveness.PROVEN_DEAD
                or observed.provider_writer_state is not ProviderWriterState.RELEASED):
            raise StateConflict("native closure awaits original physical reconciliation")
        self._complete_native_after_shutdown(job=retained.job, lease=retained.lease,
                                            session=retained.session, reference=reference)

    def _complete_after_shutdown(
        self,
        *,
        job: Job,
        lease: AttemptLease,
        session: OperatorSessionReceipt,
        canonical_result_json: str | None,
        artifact_receipt_digest: str | None = None,
        native_result: NativeConversationResultRef | None = None,
    ) -> None:
        """Complete only after the caller has proven the generation shut down."""

        if ((native_result is None) == (canonical_result_json is None)
                or (native_result is not None and artifact_receipt_digest not in {None, canonical_digest([])})):
            raise StateConflict("native terminal cannot discard another result or artifact contract")
        if native_result is not None:
            self._complete_native_after_shutdown(job=job, lease=lease, session=session, reference=native_result)
            return
        self.runtime.operator_harness.abandon_epoch(
            epoch=session.epoch,
            fence_generation=lease.attempt.fence_generation,
            lease_token=lease.lease_token,
        )
        self.runtime.attempts.complete_attempt(
            lease.attempt.attempt_id,
            fence_generation=lease.attempt.fence_generation,
            lease_token=lease.lease_token,
            payload=(self.runtime.operator_harness.native_conversation_terminal_payload(
                attempt_id=lease.attempt.attempt_id, reference=native_result)
                if native_result is not None else self._terminal_payload(
                    job=job, lease=lease, canonical_result_json=canonical_result_json,
                    artifact_receipt_digest=artifact_receipt_digest)),
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
    ) -> tuple[OperatorSessionReceipt, TurnRef | None, OperationId | None]:
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
            return session, None, None
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
        return session, turn, operation

    def _recovery_owner_identity(
        self, job: Job, lease: AttemptLease, session: OperatorSessionReceipt
    ) -> WorkspaceIdentity:
        """Prove the exact recovery owner and return its sealed workspace.

        The returned identity is only the canonical Runtime-sealed requested
        workspace of the exact current G1 writer recovered under this exact
        lease: ``_recovery_session`` already proved the requested/observed
        launch match, and this proof re-reads the durable Attempt, the lease
        token/fence currency, the Job assignment and that same CURRENT writer
        before the identity may stand in for the absent local workspace.  The
        ``WorkspaceIdentity`` type alone is not admission and no model or
        caller label can mint it; the remote path is never stat'ed or resolved
        here.
        """
        current = self.runtime.attempts.get_attempt(lease.attempt.attempt_id)
        identity_keys = ("attempt_id", "job_id", "worker_id", "quota_class",
                         "fence_generation", "lease_owner", "authority_policy_hash")
        if (not isinstance(current, Attempt)
                or current.status not in {
                    AttemptStatus.CLAIMED,
                    AttemptStatus.RUNNING,
                    AttemptStatus.CHECKPOINTED,
                }
                or current.execution_mode != "OPERATOR_HARNESS"
                or current.requested_execution_profile != lease.attempt.requested_execution_profile
                or current.requested_execution_profile_digest != lease.attempt.requested_execution_profile_digest
                or any(getattr(current, key) != getattr(lease.attempt, key)
                       for key in identity_keys)):
            raise ExecutiveOperatorSupervisorError(
                "operator recovery lease is not the current Attempt owner"
            )
        current_job = self.runtime.jobs.get_job(job.job_id)
        if (current_job is None
                or current_job.orchestration_role != "plan"
                or current_job.current_attempt_id != current.attempt_id
                or current_job.assigned_worker_id != current.worker_id
                or current_job.assigned_quota_class != current.quota_class
                or current_job.worktree != job.worktree
                or current_job.constraints != job.constraints):
            raise ExecutiveOperatorSupervisorError(
                "operator recovery Job binding moved"
            )
        try:
            with self.runtime.store.read() as connection:
                leased = self.runtime.operator_harness._leased(
                    connection,
                    attempt_id=lease.attempt.attempt_id,
                    fence_generation=lease.attempt.fence_generation,
                    lease_token=lease.lease_token,
                    timestamp=self.runtime.store.now_ms(),
                    statuses={AttemptStatus.CLAIMED, AttemptStatus.RUNNING,
                              AttemptStatus.CHECKPOINTED},
                )
        except StateConflict:
            leased = None
        if not leased:
            raise ExecutiveOperatorSupervisorError(
                "operator recovery lease token is no longer current"
            )
        requested = session.launch.requested
        if (requested.worker_id != current.worker_id
                or requested.authority_policy_hash
                != current.authority_policy_hash):
            raise ExecutiveOperatorSupervisorError(
                "operator recovery requested profile is not this Attempt's"
            )
        current_session, _existing_turn, _existing_turn_operation = (
            self._recovery_session(lease, require_turn=False)
        )
        if current_session != session:
            raise ExecutiveOperatorSupervisorError(
                "operator recovery current writer moved during recovery"
            )
        sealed = requested.workspace
        if (type(sealed) is not WorkspaceIdentity
                or sealed.workspace_path != job.worktree
                or sealed.base_sha != job.constraints.get("base_sha")
                or any(type(getattr(sealed, field)) is not int
                       or getattr(sealed, field) < 0
                       for field in ("device", "inode", "uid", "gid"))
                or sealed.inode == 0):
            raise ExecutiveOperatorSupervisorError(
                "operator recovery sealed workspace is not the exact durable assignment"
            )
        return sealed

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
        native = self.runtime.jobs.get_native_conversation_binding(lease.attempt.job_id) is not None
        if native:
            orchestrator.runtime.observe_operator_reconcile(
                handle.attempt_id, handle.generation, observed)
        self.runtime.operator_harness.abandon_epoch(
            epoch=handle.epoch, **({"generation": handle.generation} if native else {}),
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
        self, job: Job, lease: AttemptLease, *, retain_native: bool = False,
        foreground_operation=None, _active_turn_observer=None,
    ) -> OrchestrationDispatchOutcome | RetainedNativeOperatorSession:
        if _active_turn_observer is not None and (not retain_native or not callable(_active_turn_observer)):
            raise ExecutiveOperatorSupervisorError("active turn observer requires retained ownership")
        expected_native_input = None
        def require_fresh_effect():
            if foreground_operation is None:
                return
            foreground_operation.require_root(job.root_job_id)
            with self.runtime.store.read() as connection:
                self.runtime.attempts._leased_row(connection,
                    attempt_id=lease.attempt.attempt_id,
                    fence_generation=lease.attempt.fence_generation,
                    lease_token=lease.lease_token, timestamp=self.runtime.store.now_ms(),
                    statuses={AttemptStatus.CLAIMED, AttemptStatus.RUNNING, AttemptStatus.CHECKPOINTED})
            current = self.runtime.jobs.get_job(job.job_id)
            if current is None or current.current_attempt_id != lease.attempt.attempt_id:
                raise ExecutiveOperatorSupervisorError("foreground Attempt is no longer current")
            if expected_native_input is not None and native_initial_message() != expected_native_input:
                raise ExecutiveOperatorSupervisorError("original native input changed at provider write")
            foreground_operation._require_live()  # Recheck after possibly blocking canonical reads.
        require_fresh_effect()  # Thread entry may follow request closure.
        interactive = self.runtime.operator_harness.is_interactive_job(job.job_id)
        native = self.runtime.jobs.get_native_conversation_binding(job.job_id) is not None
        if retain_native:
            expected_profile = (DSH_NATIVE_CONVERSATION_PROFILE_ID if native
                                else NATIVE_RETURN_TX5_EXECUTION_PROFILE)
            if not interactive or job.constraints.get("execution_profile_id") != expected_profile:
                raise ExecutiveOperatorSupervisorError("retention requires an exact native interactive Job")
        elif interactive:
            raise ExecutiveOperatorSupervisorError("one-shot supervisor refuses retained interactive Jobs")
        requested = self._requested_profile(job, lease)
        if not job.worktree:
            raise ExecutiveOperatorSupervisorError(
                "operator planner has no assigned workspace"
            )
        # Remote physical identity is not a local Git source. Source-free Jobs
        # need no local read; strict commissions still require a qualified source.
        selected_workspace = self._workspace_source_for(job, lease.attempt) is not None
        try:
            verified_commission = verify_commission_for_job(
                self.runtime, job,
                (None if selected_workspace else Path(job.worktree).resolve(strict=True)),
                owner_workspace_identity=(requested.workspace if selected_workspace else None),
            )
        except Exception as exc:
            raise ExecutiveOperatorSupervisorError(
                f"operator immutable commission verification failed: {exc}"
            ) from exc
        def native_initial_message():
            from control_plane.fresh_conversation_admission import require_native_initial_message
            return require_native_initial_message(self.runtime, job, foreground_operation, supervisor=self)
        prompt_by_turn: dict[str, str] = {
            "pending": (native_initial_message() if native
                        else self._prompt(job, lease, verified_commission))
        }
        expected_native_input = prompt_by_turn["pending"] if native else None
        from control_plane.operator_continuation_delivery import _continuation_for_claim
        continuation = (None if native else _continuation_for_claim(self.runtime, job, lease, requested,
            verified_commission, prompt_by_turn["pending"]))

        def load_turn(turn: Any) -> str:
            try:
                value = prompt_by_turn[turn.turn_id]
                if native and native_initial_message() != value:
                    raise ExecutiveOperatorSupervisorError("original native input changed")
                return value
            except KeyError as exc:
                raise ExecutiveOperatorSupervisorError(
                    "operator turn prompt is not bound to the Runtime turn"
                ) from exc

        adapter = self._adapter_for_attempt(lease, requested, load_turn, recovery=False)
        if foreground_operation is not None:
            from control_plane.remote_operator_harness_adapter import RemoteOperatorHarnessAdapter
            if not isinstance(adapter, RemoteOperatorHarnessAdapter):
                raise ExecutiveOperatorSupervisorError("foreground operator needs its qualified transport owner")
            adapter.bind_fresh_effect_guard(require_fresh_effect, attempt_id=lease.attempt.attempt_id)
        orchestrator = self._orchestrator(lease, adapter)
        attempt_id = lease.attempt.attempt_id
        start_operation = OperationId(f"ohf-op:start:{attempt_id}")
        turn_operation = self._turn_operation_id(
            attempt_id,
            verified_commission,
        ) if continuation is None else continuation.operation
        stop_operation = OperationId(f"ohf-op:stop:{attempt_id}")
        session: OperatorSessionReceipt | None = None
        try:
            session = orchestrator.start_attempt(
                attempt_id=attempt_id,
                requested=requested,
                operation_id=start_operation,
            )
            if native:
                stop_operation = OperationId(f"ohf-op:stop:{attempt_id}:{session.generation.process_generation_id}")
            # Initialization has its own native-contract and served-model
            # attestation. Validate before continuation preparation or useful work.
            self._require_adapter_contract(job, adapter)
            if continuation is not None:
                prompt_by_turn["pending"] = continuation.prepare(session)

            def bound_prompt(turn: Any) -> str:
                try:
                    value = prompt_by_turn.pop("pending")
                    if native and native_initial_message() != value:
                        raise ExecutiveOperatorSupervisorError("original native input changed before dispatch")
                    prompt_by_turn[turn.turn_id] = value
                    return value
                except Exception as exc:
                    if native:
                        from control_plane.remote_worker_transport import TransportError, TransportEffect
                        raise TransportError("native_input_refused", TransportEffect.NO_EFFECT) from exc
                    raise

            adapter.turn_input_loader = bound_prompt
            active = None
            def expose_active(turn):
                nonlocal active
                if not native:
                    require_fresh_effect()
                active = ActiveNativeOperatorTurn(self, job, lease, session, adapter, turn, turn_operation)
                self._require_active_native_turn(active)
                if native and foreground_operation is not None:
                    from control_plane.fresh_conversation_admission import require_native_initial_record
                    require_native_initial_record(self.runtime, active, foreground_operation)
                if _active_turn_observer(active, True) is not None:
                    raise ExecutiveOperatorSupervisorError("active turn observer returned authority")
                if not native:
                    require_fresh_effect()
            try:
                turn = orchestrator.run_turn(
                    session,
                    operation_id=turn_operation,
                    timeout_seconds=300.0,
                    **({"_on_turn_applied": expose_active} if _active_turn_observer is not None else {}),
                    **({"_before_role_seal": lambda receipt, raw:
                        continuation.consume_before_seal(receipt, raw, adapter, session)}
                        if continuation is not None else {}),
                )
            finally:
                # Initial cleanup remains local until the settled retained
                # handle returns. Withdraw the observation before that cleanup.
                if active is not None:
                    active.withdraw()  # Synchronous even if the event loop is delayed.
                    _active_turn_observer(active, False)
            if native:
                if not retain_native or type(turn.native_result) is not NativeConversationResultRef:
                    raise ExecutiveOperatorSupervisorError("native conversation lost its retained result reference")
                value = self.runtime.operator_harness.native_conversation_result(
                    attempt_id=session.attempt_id, reference=turn.native_result)
                if (value["job_id"] != job.job_id or value["turn"]["turn_id"] != turn.turn.turn_id
                        or value["observation"]["provider_session_id"] != session.observation.provider_session_id):
                    raise ExecutiveOperatorSupervisorError("native result differs from its original turn")
                return RetainedNativeOperatorSession(
                    self, job, lease, session, adapter, native_result=turn.native_result)
            raw = adapter.observe_raw_role_result(turn.turn)
            if retain_native:
                return RetainedNativeOperatorSession(
                    self, job, lease, session, adapter, raw.canonical_result_json)
            self._complete_after_stop(
                job=job,
                lease=lease,
                session=session,
                adapter=adapter,
                canonical_result_json=raw.canonical_result_json,
                stop_operation=stop_operation,
            )
        except NativeTurnPending as exc:
            if not native or not retain_native or session is None:
                raise
            raise NativeOperatorRecoveryPending(PendingNativeOperatorTurn(
                self, job, lease, session, adapter, exc.turn, exc.operation_id, exc.cursor,
                foreground_operation, _active_turn_observer)) from exc
        except OperatorStartRefused as exc:
            if native:
                stop_operation = OperationId(f"ohf-op:stop:{attempt_id}:{exc.handle.generation.process_generation_id}")
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
        if self.runtime.operator_harness.is_interactive_job(job_id):
            raise StateConflict("interactive Jobs are not owned by the one-shot supervisor")
        from control_plane.foreground_operation import _current_foreground_operation_or_none
        foreground_operation = _current_foreground_operation_or_none()
        if self.foreground_only and foreground_operation is None:
            raise ExecutiveOperatorSupervisorError("foreground-only operator requires its original request")
        if foreground_operation is not None:
            foreground_operation.require_root(job.root_job_id)
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
        completed = await asyncio.to_thread(self._run_claimed, job, lease,
            **({"foreground_operation": foreground_operation} if foreground_operation is not None else {}))
        return OrchestrationDispatchOutcome(
            command_id=command_id,
            job_id=completed.job_id,
            attempt=completed.attempt,
            outcome="TERMINAL",
        )

    async def start_retained_native_job(self, job_id: str, *, command_id: str,
                                        _active_turn_observer=None) -> RetainedNativeOperatorSession:
        """Start one explicit native interactive Job under the existing owners.

        This attended composition creates no registry, loop or replay path.
        The installed service retains it for one bounded authenticated native
        continuation. Canonical result read survives ordinary cleanup; only
        actual parent evidence can establish delivery or useful action.
        """
        job = self.runtime.jobs.get_job(job_id)
        native = job is not None and self.runtime.jobs.get_native_conversation_binding(job_id) is not None
        expected_profile = (DSH_NATIVE_CONVERSATION_PROFILE_ID if native else NATIVE_RETURN_TX5_EXECUTION_PROFILE)
        if (job is None or job.status.value != "QUEUED"
                or job.constraints.get("execution_profile_id") != expected_profile
                or not self.runtime.operator_harness.is_interactive_job(job_id)):
            raise StateConflict("native retention requires an unstarted explicit interactive Job")
        from control_plane.foreground_operation import _current_foreground_operation_or_none
        foreground_operation = _current_foreground_operation_or_none()
        if foreground_operation is not None:
            foreground_operation.require_root(job.root_job_id)
        from control_plane.fresh_conversation_admission import require_original_creation_request
        require_original_creation_request(self.runtime, self.runtime.jobs.get_job(job.root_job_id), foreground_operation)
        if native:
            from control_plane.fresh_conversation_admission import require_native_initial_message
            require_native_initial_message(self.runtime, job, foreground_operation, supervisor=self)
        outcome = self.runtime.attempts.dispatch_cycle_job(
            job_id, command_id=command_id, lease_owner=self.instance_id)
        if (outcome is None or outcome.attempt.status is not AttemptStatus.CLAIMED
                or outcome.lease_token is None):
            raise ExecutiveOperatorSupervisorError("native retention has no fresh exact Capacity claim")
        retained = await asyncio.to_thread(self._run_claimed, job,
            AttemptLease(outcome.attempt, outcome.lease_token), retain_native=True,
            _active_turn_observer=_active_turn_observer,
            **({"foreground_operation": foreground_operation} if foreground_operation is not None else {}))
        assert isinstance(retained, RetainedNativeOperatorSession)
        return retained


    def recover_pending_native_turn(self, pending, *, current, timeout_seconds=30.0):
        """A failed recovery check retains the same original pending owner."""
        if type(pending) is not PendingNativeOperatorTurn or pending.owner is not self:
            raise StateConflict("pending native turn belongs to another owner")
        try:
            return self._recover_pending_native_turn(pending, current=current, timeout_seconds=timeout_seconds)
        except NativeOperatorRecoveryPending:
            raise
        except Exception as exc:
            raise NativeOperatorRecoveryPending(pending) from exc

    def _recover_pending_native_turn(self, pending, *, current, timeout_seconds=30.0):
        """Use this same supervisor/lease/adapter to collect its retained call."""
        from control_plane.operator_harness_orchestrator import NativeTurnPending
        if (type(pending) is not PendingNativeOperatorTurn or pending.owner is not self
                or not callable(current) or current() is not None
                or pending.job.job_id != pending.lease.attempt.job_id
                or pending.turn.attempt_id != pending.session.attempt_id
                or pending.turn.attempt_id != pending.lease.attempt.attempt_id
                or pending.turn.session_epoch_id != pending.session.epoch.session_epoch_id
                or pending.turn.process_generation_id != pending.session.generation.process_generation_id
                or self.runtime.jobs.get_native_conversation_binding(pending.job.job_id) is None):
            raise StateConflict("pending native turn lost its original owner")
        self._require_adapter_contract(pending.job, pending.adapter)
        orchestrator = self._orchestrator(pending.lease, pending.adapter)
        if orchestrator.runtime.original_operator_native_turn(
                pending.session.attempt_id, pending.session.generation, pending.operation_id) != pending.turn:
            raise StateConflict("pending native target changed")
        active = None
        def expose(turn):
            nonlocal active
            if current() is not None:
                raise StateConflict("native recovery authentication changed")
            active = ActiveNativeOperatorTurn(self, pending.job, pending.lease,
                pending.session, pending.adapter, turn, pending.operation_id)
            self._require_active_native_turn(active)
            if pending.foreground_operation is not None:
                from control_plane.fresh_conversation_admission import require_native_initial_record
                require_native_initial_record(self.runtime, active, pending.foreground_operation)
            if pending.active_observer is not None and pending.active_observer(active, True) is not None:
                raise StateConflict("native recovery observer returned authority")
        try:
            if current() is not None:
                raise StateConflict("native recovery request changed")
            receipt = orchestrator.recover_native_turn(pending.session, operation_id=pending.operation_id,
                expected_turn=pending.turn, cursor=pending.cursor, timeout_seconds=timeout_seconds,
                _on_turn_applied=expose)
        except NativeTurnPending as exc:
            raise NativeOperatorRecoveryPending(pending) from exc
        finally:
            if active is not None:
                active.withdraw()
                if pending.active_observer is not None:
                    pending.active_observer(active, False)
        if type(receipt.native_result) is not NativeConversationResultRef:
            raise StateConflict("native recovery did not seal its original answer")
        retained = RetainedNativeOperatorSession(self, pending.job, pending.lease,
            pending.session, pending.adapter, native_result=receipt.native_result)
        self._require_retained_native(retained)
        return retained, receipt

    def _require_active_native_turn(self, active: ActiveNativeOperatorTurn):
        if (type(active) is not ActiveNativeOperatorTurn or active.owner is not self
                or active.withdrawn):
            raise StateConflict("active native turn is withdrawn or belongs to another owner")
        session, turn = active.session, active.turn
        if (type(turn) is not TurnRef or type(active.operation_id) is not OperationId
                or turn.attempt_id != session.attempt_id
                or turn.attempt_id != active.lease.attempt.attempt_id
                or turn.session_epoch_id != session.epoch.session_epoch_id
                or turn.process_generation_id != session.generation.process_generation_id
                or active.job.job_id != active.lease.attempt.job_id):
            raise StateConflict("active native turn identity differs")
        from control_plane.executive_runtime import _interactive_in_flight_turn_id
        with self.runtime.store.read() as connection:
            row = self.runtime.operator_harness._leased(connection,
                attempt_id=turn.attempt_id, fence_generation=active.lease.attempt.fence_generation,
                lease_token=active.lease.lease_token, timestamp=self.runtime.store.now_ms(),
                statuses={AttemptStatus.RUNNING, AttemptStatus.CHECKPOINTED})
            facts = self.runtime.current_harness_binding_source(turn.attempt_id, connection=connection)
            operation, _intent, intent, _applied, _payload = self.runtime.operator_harness._validated_tx5_receipts(
                connection, row=row, turn=turn)
            if (operation != active.operation_id or facts.job_id != active.job.job_id
                    or facts.worker_id != active.lease.attempt.worker_id
                    or facts.session_epoch_id != session.epoch.session_epoch_id
                    or facts.process_generation_id != session.generation.process_generation_id
                    or facts.provider_session_id != session.observation.provider_session_id
                    or intent["provider_session_id"] != facts.provider_session_id
                    or _interactive_in_flight_turn_id(connection, turn.process_generation_id) != turn.turn_id):
                raise StateConflict("active native turn is no longer the exact acknowledged writer")
        if active.withdrawn:
            raise StateConflict("active native turn was withdrawn during observation")
        return facts

    def _require_retained_native(self, retained: RetainedNativeOperatorSession):
        if not isinstance(retained, RetainedNativeOperatorSession) or retained.owner is not self:
            raise StateConflict("retained native handle belongs to another owner")
        native = self.runtime.jobs.get_native_conversation_binding(retained.job.job_id) is not None
        if native != (type(retained.native_result) is NativeConversationResultRef):
            raise StateConflict("retained result differs from its immutable creator contract")
        if native:
            result = self.runtime.operator_harness.native_conversation_result(
                attempt_id=retained.session.attempt_id, reference=retained.native_result)
            if (result["job_id"] != retained.job.job_id
                    or result["turn"]["session_epoch_id"] != retained.session.epoch.session_epoch_id
                    or result["observation"]["provider_session_id"] != retained.session.observation.provider_session_id):
                raise StateConflict("retained native history differs from its original Session")
        facts = self.runtime.current_harness_binding_source(retained.session.attempt_id)
        if (facts.job_id != retained.job.job_id
                or facts.worker_id != retained.lease.attempt.worker_id
                or facts.session_epoch_id != retained.session.epoch.session_epoch_id
                or facts.process_generation_id != retained.session.generation.process_generation_id
                or facts.provider_session_id != retained.session.observation.provider_session_id):
            raise StateConflict("retained native writer changed")
        return facts

    async def run_native_continuation(self, retained: RetainedNativeOperatorSession, *, source, read_ref: str):
        """Bind a post-ACK turn to the original canonical CONTINUE only."""
        if retained.native_result is not None:
            raise StateConflict("native conversation cannot consume the planner CONTINUE contract")
        from control_plane.native_continuation import NativeContinuationSource
        if not isinstance(source, NativeContinuationSource) or source.runtime is not self.runtime:
            raise StateConflict("native continuation requires the existing canonical Runtime owner")
        facts = self._require_retained_native(retained)
        captured = await source.read_continuation_source(read_ref=read_ref)
        request = captured["request"]
        message = captured["message"]
        if (request["attempt_id"] != facts.attempt_id or request["job_id"] != facts.job_id
                or request["worker_id"] != facts.worker_id):
            raise StateConflict("native continuation belongs to another writer")
        binding = source.resolve(native_session_id=facts.provider_session_id,
            operation_key=request["operation_key"], in_reply_to=message["message_key"])

        def guard():
            self._require_retained_native(retained)
            source.require_native_ack(binding,
                workspace_id=request["carrier"]["workspace_id"],
                channel_id=request["carrier"]["channel_id"])

        guard()  # The actual terminal attention ACK must already be persisted.
        if await source.read_continuation_source(read_ref=read_ref) != captured:
            raise StateConflict("native continuation changed during source read")
        prompt = (
            "Consume this exact canonical Agent Dialogue CONTINUE. Carry out its instruction "
            "within your existing read-only grant. Return the useful result and next action via "
            "native.reply using operation_key and in_reply_to below. Stop after the canonical "
            "reply receipt. Do not claim that the parent consumed the result.\n"
            + json.dumps({"operation_key": request["operation_key"],
                          "in_reply_to": message["message_key"], "continue": message},
                         sort_keys=True, ensure_ascii=False, separators=(",", ":")))
        operation = OperationId("ohf-op:native-continuation:" + canonical_digest({
            "request_event": captured["event"], "message": message}))
        from control_plane.remote_operator_harness_adapter import RemoteOperatorHarnessAdapter
        if isinstance(retained.adapter, RemoteOperatorHarnessAdapter):
            # The original create request guards initial start/turn only. A
            # later native turn has its own exact retained writer + durable
            # ACK source; install that source at the SAME remote write fence.
            retained.adapter.bind_native_continuation_guard(guard,
                attempt_id=facts.attempt_id, operation_id=operation)
        def load_turn(_turn):
            guard()  # Recheck the exact writer and ACK immediately before provider I/O.
            return prompt
        retained.adapter.turn_input_loader = load_turn
        return await asyncio.to_thread(self._orchestrator(retained.lease, retained.adapter).run_turn,
            retained.session, operation_id=operation, timeout_seconds=300.0)

    @staticmethod
    def _retained_stop_operation(retained: RetainedNativeOperatorSession) -> OperationId:
        suffix = ("" if retained.native_result is None
                  else ":" + retained.session.generation.process_generation_id)
        return OperationId(f"ohf-op:stop:{retained.session.attempt_id}{suffix}")

    async def idle_retained_native_job(self, retained: RetainedNativeOperatorSession) -> NativeConversationResultRef:
        """Close native G1 physically while Runtime retains original resume custody."""
        self._require_retained_native(retained)
        if retained.native_result is None:
            raise StateConflict("native idle disposition requires the native conversation contract")
        reference = self.runtime.operator_harness.latest_native_conversation_result(
            attempt_id=retained.session.attempt_id)
        await asyncio.to_thread(self._orchestrator(retained.lease, retained.adapter).graceful_stop,
            retained.session,
            operation_id=OperationId(f"ohf-op:idle:{retained.session.attempt_id}:{retained.session.generation.process_generation_id}"),
            native_idle_result=reference)
        return reference

    def native_idle_projection(self, retained: RetainedNativeOperatorSession, *, expected_result):
        """Read original idle custody without presenting a dead process as live."""
        if (type(retained) is not RetainedNativeOperatorSession or retained.owner is not self
                or type(expected_result) is not NativeConversationResultRef):
            raise StateConflict("native idle requires its exact retained owner")
        latest = self.runtime.operator_harness.latest_native_conversation_result(attempt_id=retained.session.attempt_id)
        if latest != expected_result:
            raise StateConflict("native idle result changed")
        state = self._native_finalization_state(job=retained.job, lease=retained.lease,
            session=retained.session, reference=expected_result)
        if (state["status"] not in {AttemptStatus.RUNNING.value, AttemptStatus.CHECKPOINTED.value}
                or state["epoch_state"] != "CURRENT" or not state["ended"] or not state["released"]):
            raise StateConflict("native idle physical closure is not proved")
        operation = OperationId(f"ohf-op:idle:{retained.session.attempt_id}:{retained.session.generation.process_generation_id}")
        intent = self.runtime.events.get_event_by_command_id(operation.command_id)
        applied = self.runtime.events.get_event_by_command_id(
            operation_receipt_command_id(operation, OperationReceiptKind.APPLIED))
        if (intent is None or applied is None
                or intent.payload.get("native_idle_result") != expected_result.to_wire()
                or applied.payload.get("native_idle_result") != expected_result.to_wire()
                or applied.payload.get("executive_writer_released") is not False):
            raise StateConflict("native idle lost its original disposition")
        with self.runtime.store.read() as connection:
            row = self.runtime.operator_harness._leased(connection, attempt_id=retained.session.attempt_id,
                fence_generation=retained.lease.attempt.fence_generation, lease_token=retained.lease.lease_token,
                timestamp=self.runtime.store.now_ms(), statuses={AttemptStatus.RUNNING, AttemptStatus.CHECKPOINTED})
            generations = connection.execute(
                "SELECT * FROM process_generations WHERE session_epoch_id=? ORDER BY generation_number",
                (retained.session.epoch.session_epoch_id,)).fetchall()
            if (len(generations) != 1 or retained.session.generation.generation_number != 1
                    or generations[-1]["process_generation_id"] != retained.session.generation.process_generation_id):
                raise StateConflict("native idle generation history changed")
            self.runtime.operator_harness._owned_generation(connection, leased=row,
                epoch=retained.session.epoch, generation=retained.session.generation,
                require_current=True, require_writer=True)
            self.runtime.operator_harness._require_native_closure_result(connection, row=row,
                epoch=retained.session.epoch, generation=retained.session.generation,
                reference=expected_result, idle=True)
            self.runtime.operator_harness._require_orchestration_g1_recovery_predicate(connection, row=row,
                epoch=retained.session.epoch, g1_generation_id=generations[0]["process_generation_id"],
                expected_generation_count=len(generations))
            closure = self.runtime.operator_harness._validated_generation_closure_event(connection,
                row=row, generation=generations[-1], provider_session_id=retained.session.observation.provider_session_id)
        from common.fresh_conversation_contract import canonical_digest
        identity = dict(attempt_id=retained.session.attempt_id, session_epoch_id=retained.session.epoch.session_epoch_id,
            process_generation_id=retained.session.generation.process_generation_id,
            provider_session_id=retained.session.observation.provider_session_id)
        digest = canonical_digest(dict(**identity, job_id=retained.job.job_id,
            worker_id=retained.lease.attempt.worker_id, quota_class=retained.lease.attempt.quota_class,
            fence_generation=retained.lease.attempt.fence_generation, head_result=expected_result.to_wire(),
            closure_event_id=closure, idle_intent_sha256=canonical_digest(intent.to_dict()),
            idle_applied_sha256=canonical_digest(applied.to_dict())))
        return dict(**identity, binding_digest=digest)

    async def finish_retained_native_job(self, retained: RetainedNativeOperatorSession) -> None:
        """Use original terminal cleanup; this never asserts parent consumption."""
        if retained.native_result is not None:
            await asyncio.to_thread(self._finish_native_conversation, retained)
            return
        self._require_retained_native(retained)
        reference = (None if retained.native_result is None else
            self.runtime.operator_harness.latest_native_conversation_result(
                attempt_id=retained.session.attempt_id))
        await asyncio.to_thread(self._complete_after_stop,
            job=retained.job, lease=retained.lease, session=retained.session,
            adapter=retained.adapter, canonical_result_json=retained.canonical_plan_json,
            native_result=reference, stop_operation=self._retained_stop_operation(retained))

    async def abort_retained_native_job(self, retained: RetainedNativeOperatorSession, *, reason: str) -> bool:
        """Settle a failed bounded continuation through the incumbent cleanup."""
        if not isinstance(retained, RetainedNativeOperatorSession) or retained.owner is not self:
            raise StateConflict("retained native handle belongs to another owner")
        if retained.native_result is not None:
            reference = self.runtime.operator_harness.latest_native_conversation_result(
                attempt_id=retained.session.attempt_id)
            current = self._native_finalization_state(job=retained.job, lease=retained.lease,
                session=retained.session, reference=reference)
            if current["status"] in {AttemptStatus.COMPLETED.value, AttemptStatus.CANCELLED.value}:
                return True
            if current["closing"] or current["epoch_state"] == "ABANDONED":
                if current["status"] == AttemptStatus.CANCEL_REQUESTED.value:
                    await asyncio.to_thread(self._finish_native_conversation, retained)
                    return True
                # Pending close and post-close bookkeeping remain owned by the
                # original finalizer; a service catch must not fail the result.
                return False
        return await asyncio.to_thread(self._cleanup_failed_session,
            lease=retained.lease, orchestrator=self._orchestrator(retained.lease, retained.adapter),
            handle=retained.session,
            stop_operation=self._retained_stop_operation(retained), reason=reason)

    def retain_native_wait_window(self, retained: RetainedNativeOperatorSession) -> None:
        """Extend the incumbent lease for attachment or one qualified request."""
        self._require_retained_native(retained)
        self._orchestrator(retained.lease, retained.adapter).runtime.extend_operator_lease(
            retained.session.attempt_id, 600)

    def _recover_one(
        self, attempt_id: str
    ) -> ReconcileReceipt:
        previous = self.runtime.attempts.get_attempt(attempt_id)
        if previous is not None and previous.status is not AttemptStatus.CANCEL_REQUESTED:
            from control_plane.operator_continuation_delivery import _continuation_recovery_held
            if _continuation_recovery_held(self.runtime, previous):
                return ReconcileReceipt(attempt_id=attempt_id, job_id=previous.job_id,
                    status=ReconcileStatus.LIVE_QUARANTINED, process_was_live=False)
        if previous is None:
            raise ExecutiveOperatorSupervisorError(
                "operator recovery Attempt disappeared"
            )
        previous_job = self.runtime.jobs.get_job(previous.job_id)
        if previous_job is not None and self.runtime.operator_harness.is_interactive_job(previous.job_id):
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
            session, existing_turn, existing_turn_operation = self._recovery_session(
                lease,
                require_turn=False,
            )
            sealed_result_json = (
                None if lease.attempt.status is AttemptStatus.CANCEL_REQUESTED
                else self._sealed_role_result_json(job, lease)
            )
            containment = (lease.attempt.status is AttemptStatus.CANCEL_REQUESTED
                           or sealed_result_json is not None)
            verified_commission = None
            if not containment:
                owner_workspace_identity = None
                selected_workspace = self._workspace_source_for(job, lease.attempt) is not None
                if selected_workspace:
                    # The selected-host identity is only ever the canonical
                    # Runtime-sealed requested workspace of the exact current
                    # G1 writer under this exact recovery lease, re-proven
                    # before and after the blocking source verification.
                    owner_workspace_identity = self._recovery_owner_identity(
                        job, lease, session
                    )
                try:
                    verified_commission = verify_commission_for_job(
                        self.runtime,
                        job,
                        (Path(job.worktree).resolve(strict=True)
                         if job.worktree and not selected_workspace
                         else None),
                        owner_workspace_identity=owner_workspace_identity,
                    )
                except Exception as exc:
                    raise ExecutiveOperatorSupervisorError(
                        f"operator immutable commission verification failed: {exc}"
                    ) from exc
                if owner_workspace_identity is not None:
                    # The canonical fetch blocks; the lease, durable assignment
                    # and current writer are re-proven before any adapter or
                    # resumed turn may consume the verified commission.
                    self._recovery_owner_identity(job, lease, session)
                # Source verification can block while a continuation PREPARE or
                # cross-realm hold becomes durable. Never resume through that hold.
                current_attempt = self.runtime.attempts.get_attempt(attempt_id)
                if current_attempt is None:
                    raise ExecutiveOperatorSupervisorError(
                        "operator recovery Attempt disappeared after source verification"
                    )
                from control_plane.operator_continuation_delivery import _continuation_recovery_held
                if _continuation_recovery_held(self.runtime, current_attempt):
                    return ReconcileReceipt(
                        attempt_id=attempt_id,
                        job_id=lease.attempt.job_id,
                        status=ReconcileStatus.LIVE_QUARANTINED,
                        process_was_live=False,
                    )
            # Cancellation and sealed-result consumption need only containment.
            # Do not require fresh source/provider admission or load turn input.
            if containment:
                def load_recovery_turn(_turn: Any) -> str:
                    raise ExecutiveOperatorSupervisorError(
                        "containment recovery cannot start or resume a turn"
                    )
            else:
                prompt = self._prompt(job, lease, verified_commission)
                def load_recovery_turn(_turn: Any) -> str:
                    return prompt
            if sealed_result_json is not None:
                # Preserve original input custody without reopening commission
                # source or requalifying a producer after its output is sealed.
                with self.runtime.store.read() as connection:
                    source = _dialogue_source_from_root_creation(
                        connection, root_job_id=job.root_job_id
                    )
                expected_turn_operation = (
                    self._commission_turn_operation_id(
                        attempt_id, source.commission_ref.to_dict()
                    ) if source is not None else None
                )
            else:
                expected_turn_operation = (
                    self._turn_operation_id(attempt_id, verified_commission)
                    if verified_commission is not None else None
                )
            if (
                expected_turn_operation is not None
                and (
                    (sealed_result_json is not None and existing_turn is None)
                    or (existing_turn is not None and (
                        existing_turn_operation is None
                        or existing_turn_operation.command_id
                        != expected_turn_operation.command_id
                    ))
                )
            ):
                raise ExecutiveOperatorSupervisorError(
                    "operator recovery turn input is not bound to the verified commission"
                )
            adapter = self._adapter_for_attempt(
                lease, session.launch.requested, load_recovery_turn, recovery=True,
                expected_recovery_seal=sealed_result_json,
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
                    if self.foreground_only:
                        return ReconcileReceipt(attempt_id=attempt_id, job_id=lease.attempt.job_id,
                            status=ReconcileStatus.LIVE_QUARANTINED, process_was_live=process_was_live)
                    turn = orchestrator.run_turn(
                        session,
                        operation_id=(
                            expected_turn_operation
                            if expected_turn_operation is not None
                            else OperationId(
                                f"ohf-op:recover-first-turn:{attempt_id}"
                            )
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
                if self.foreground_only:
                    return ReconcileReceipt(attempt_id=attempt_id, job_id=lease.attempt.job_id,
                        status=ReconcileStatus.LIVE_QUARANTINED, process_was_live=process_was_live)
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
                    operation_id=(
                        expected_turn_operation
                        if expected_turn_operation is not None
                        else OperationId(
                            f"ohf-op:recover-turn:{attempt_id}"
                        )
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
