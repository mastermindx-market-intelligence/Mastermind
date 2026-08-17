"""OHF-P1A-R2 provider-neutral Operator Harness contract.

Pure architecture freeze.  This module must not:

* write Executive SQLite
* spawn subprocesses
* call providers
* open network sockets
* read credential bytes
* activate production workers
* mutate Job/Attempt lifecycle

``WorkerExecutionAdapter`` remains the sealed-worker floor.  This sibling
contract is the rich-operator interface.  Implementations belong to a later
commission; P1B must not invent types or method semantics that are missing here.

Interface version: ``mastermind.operator_harness/v1``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping, Protocol, Sequence, runtime_checkable


OPERATOR_HARNESS_INTERFACE_VERSION = "mastermind.operator_harness/v1"
CARDINALITY = "CARDINALITY_B"
WRITER_REALM_KEY = ("worker_id", "provider_session_id")
CANONICAL_SESSION_FIELD = "provider_session_id"
FORBIDDEN_SESSION_SYNONYM = "native_session_id"
V1_QUALITY_TRADEOFF = "V1_QUALITY_TRADEOFF_ACCEPTED"
ACCOUNT_REALM_STATUS = "ACCOUNT_REALM_ATTESTATION_UNPROVEN"
LIVE_APP_SERVER_ADOPTION = "NOT_SUPPORTED"
RESTORE_POLICY = "OPTION_A_BACKUP_MAY_CAPTURE_ACTIVE_INVALIDATE_ON_RESTORE"
POST_RESTORE_ATTEMPT_STATUS = "LOST"


class AttemptBoundary(str, Enum):
    SAME_ATTEMPT = "SAME_ATTEMPT"
    NEW_ATTEMPT = "NEW_ATTEMPT"
    REFUSE = "REFUSE"


class SessionEpochState(str, Enum):
    CURRENT = "CURRENT"
    TERMINAL = "TERMINAL"
    ABANDONED = "ABANDONED"


class ProcessLiveness(str, Enum):
    ALIVE = "ALIVE"
    PROVEN_DEAD = "PROVEN_DEAD"
    UNKNOWN = "UNKNOWN"


class ProviderWriterState(str, Enum):
    HELD = "HELD"
    RELEASED = "RELEASED"
    UNKNOWN = "UNKNOWN"


class LaunchDecision(str, Enum):
    ALLOW = "ALLOW"
    REFUSE_SERVED_MODEL_MISMATCH = "REFUSE_SERVED_MODEL_MISMATCH"
    REFUSE_MISSING_REQUIRED = "REFUSE_MISSING_REQUIRED"
    REFUSE_FORBIDDEN = "REFUSE_FORBIDDEN"
    REFUSE_UNCLASSIFIED = "REFUSE_UNCLASSIFIED"
    REFUSE_WORKSPACE_MISMATCH = "REFUSE_WORKSPACE_MISMATCH"
    REFUSE_AUTH_REALM_MISMATCH = "REFUSE_AUTH_REALM_MISMATCH"
    REFUSE_CONFIG_DRIFT = "REFUSE_CONFIG_DRIFT"
    REFUSE_HELPER_CEILING_MISSING = "REFUSE_HELPER_CEILING_MISSING"


class AdapterFailureClass(str, Enum):
    AUTH_FAILURE = "AUTH_FAILURE"
    QUOTA_OR_RATE_LIMIT = "QUOTA_OR_RATE_LIMIT"
    PROVIDER_CONCURRENCY = "PROVIDER_CONCURRENCY"
    PROCESS_CRASH = "PROCESS_CRASH"
    SESSION_MISSING = "SESSION_MISSING"
    ACTIVE_WRITER_CONFLICT = "ACTIVE_WRITER_CONFLICT"
    CAPABILITY_ATTESTATION_FAILURE = "CAPABILITY_ATTESTATION_FAILURE"
    WORKSPACE_MISMATCH = "WORKSPACE_MISMATCH"
    CONFIG_DRIFT = "CONFIG_DRIFT"
    MCP_OR_TOOL_TRANSPORT_FAILURE = "MCP_OR_TOOL_TRANSPORT_FAILURE"
    MODEL_OR_WORK_RESULT_FAILURE = "MODEL_OR_WORK_RESULT_FAILURE"
    VALIDATION_FAILURE = "VALIDATION_FAILURE"
    HUMAN_APPROVAL_REQUIRED = "HUMAN_APPROVAL_REQUIRED"


class MethodClass(str, Enum):
    COMMON_REQUIRED = "COMMON_REQUIRED"
    COMMON_OPTIONAL = "COMMON_OPTIONAL"
    PROVIDER_SPECIFIC = "PROVIDER_SPECIFIC"
    SUPERVISOR_RUNTIME = "SUPERVISOR_RUNTIME"
    REJECTED = "REJECTED"


class NativeHelperPolicy(str, Enum):
    DISABLED = "DISABLED"
    PARENT_READ_ONLY_CEILING = "PARENT_READ_ONLY_CEILING"
    REQUIRES_SUBAGENT_CAPABILITY_CEILING = "REQUIRES_SUBAGENT_CAPABILITY_CEILING"


class AuthIdentityConfidence(str, Enum):
    UNKNOWN = "UNKNOWN"
    SLOT_ONLY = "SLOT_ONLY"
    PROVIDER_REPORTED = "PROVIDER_REPORTED"


class CapabilityClass(str, Enum):
    REQUIRED = "REQUIRED"
    ALLOWED_AMBIENT = "ALLOWED_AMBIENT"
    FORBIDDEN = "FORBIDDEN"
    UNCLASSIFIED = "UNCLASSIFIED"


# Attempt-boundary matrix.  Canonical freeze for P1A-R2.  Context rotation is
# SAME_ATTEMPT (new epoch).  Aggregation / placement changes are NEW_ATTEMPT.
ATTEMPT_BOUNDARY_MATRIX: dict[str, AttemptBoundary] = {
    "graceful_process_replacement": AttemptBoundary.SAME_ATTEMPT,
    "safe_crash_recovery": AttemptBoundary.SAME_ATTEMPT,
    "sigkill_blocked_writer": AttemptBoundary.SAME_ATTEMPT,
    "sigkill_abandon_s1_start_s2": AttemptBoundary.SAME_ATTEMPT,
    "context_compaction": AttemptBoundary.SAME_ATTEMPT,
    "context_rotation": AttemptBoundary.SAME_ATTEMPT,
    "fresh_primary_session_same_placement": AttemptBoundary.SAME_ATTEMPT,
    "native_fork_or_helper": AttemptBoundary.SAME_ATTEMPT,
    "worker_or_placement_change": AttemptBoundary.NEW_ATTEMPT,
    "provider_change": AttemptBoundary.NEW_ATTEMPT,
    "account_or_auth_home_change": AttemptBoundary.NEW_ATTEMPT,
    "requested_model_change": AttemptBoundary.NEW_ATTEMPT,
    "harness_kind_change": AttemptBoundary.NEW_ATTEMPT,
    "harness_binary_digest_change": AttemptBoundary.NEW_ATTEMPT,
    "workspace_change": AttemptBoundary.NEW_ATTEMPT,
    "base_sha_or_workspace_identity_change": AttemptBoundary.NEW_ATTEMPT,
    "authority_envelope_change": AttemptBoundary.NEW_ATTEMPT,
    "allowed_write_paths_change": AttemptBoundary.NEW_ATTEMPT,
    "sandbox_change": AttemptBoundary.NEW_ATTEMPT,
    "approval_policy_change": AttemptBoundary.NEW_ATTEMPT,
    "network_policy_change": AttemptBoundary.NEW_ATTEMPT,
    "required_or_forbidden_capability_set_change": AttemptBoundary.NEW_ATTEMPT,
    "phase_1f_aggregation_after_leader_release": AttemptBoundary.NEW_ATTEMPT,
    "served_model_mismatch": AttemptBoundary.REFUSE,
    "unclassified_on_write_profile": AttemptBoundary.REFUSE,
    "forbidden_capability_present": AttemptBoundary.REFUSE,
    "required_capability_missing": AttemptBoundary.REFUSE,
    "cross_attempt_session_reuse": AttemptBoundary.REFUSE,
}


REATTEST_TRIGGERS: frozenset[str] = frozenset(
    {
        "new_process_generation",
        "harness_config_reload",
        "authoritative_workspace_identity_change",
    }
)


@dataclass(frozen=True)
class OperationId:
    """Executive-issued idempotency key.  Never wait for a provider id first."""

    command_id: str


@dataclass(frozen=True)
class WorkspaceIdentity:
    """Authoritative workspace proof.  A cwd string is not identity."""

    workspace_path: str
    base_sha: str
    device: int
    inode: int
    uid: int
    gid: int


@dataclass(frozen=True)
class CapabilityIdentity:
    """Strongest truthful identity available for one capability name."""

    name: str
    harness_binary_digest: str
    skill_content_digest: str | None = None
    tool_schema_digest: str | None = None
    mcp_server_identity: str | None = None
    mcp_server_version: str | None = None


@dataclass(frozen=True)
class CapabilityManifest:
    required: tuple[CapabilityIdentity, ...] = ()
    allowed_ambient: tuple[CapabilityIdentity, ...] = ()
    forbidden: tuple[str, ...] = ()
    unclassified_policy: str = "fail_closed_on_write"


@dataclass(frozen=True)
class AuthRealmFact:
    """Honest account-realm observation.  Must not contain credentials."""

    worker_id: str
    provider: str
    auth_class: str | None = None
    plan_type: str | None = None
    nonsecret_provider_account_id: str | None = None
    identity_confidence: AuthIdentityConfidence = AuthIdentityConfidence.UNKNOWN
    attestation_status: str = ACCOUNT_REALM_STATUS

    def __post_init__(self) -> None:
        forbidden = ("token", "refresh", "secret", "auth.json", "credential")
        blob = " ".join(
            str(value or "")
            for value in (
                self.auth_class,
                self.plan_type,
                self.nonsecret_provider_account_id,
            )
        ).lower()
        if any(token in blob for token in forbidden):
            raise ValueError("AuthRealmFact must not carry credential material")


@dataclass(frozen=True)
class RequestedExecutionProfile:
    """Sealed before harness process start.  Attempt-immutable once sealed."""

    worker_id: str
    provider: str
    requested_model: str
    harness_kind: str
    harness_binary_digest: str
    harness_version: str
    workspace: WorkspaceIdentity
    sandbox_policy: str
    approval_policy: str
    network_policy: str
    capabilities: CapabilityManifest
    native_helper_policy: NativeHelperPolicy
    authority_policy_hash: str
    allowed_write_paths: tuple[str, ...] = ()
    write_capable: bool = False


@dataclass(frozen=True)
class ObservedHarnessAttestation:
    """Collected after initialize, sealed before the first work turn."""

    served_model: str | None
    harness_version: str | None
    harness_binary_digest: str | None
    effective_skills: tuple[str, ...]
    effective_mcp: tuple[str, ...]
    effective_plugins_or_apps: tuple[str, ...]
    sandbox_state: str | None
    approval_state: str | None
    effective_config_digest: str | None
    auth: AuthRealmFact
    workspace: WorkspaceIdentity | None
    unknown_fields: tuple[str, ...] = ()


@dataclass(frozen=True)
class SessionEpochRef:
    session_epoch_id: str
    attempt_id: str
    epoch_number: int
    provider_session_id: str | None
    state: SessionEpochState


@dataclass(frozen=True)
class ProcessGenerationRef:
    process_generation_id: str
    session_epoch_id: str
    generation_number: int
    worker_id: str
    provider_session_id: str | None
    pid: int | None = None
    pgid: int | None = None
    process_start_identity: str | None = None
    boot_id: str | None = None


@dataclass(frozen=True)
class TurnRef:
    turn_id: str
    session_epoch_id: str
    process_generation_id: str
    attempt_id: str


@dataclass(frozen=True)
class EventCursor:
    """Resume point for normalized event reads.  Not a second event store."""

    attempt_id: str
    session_epoch_id: str | None = None
    process_generation_id: str | None = None
    turn_id: str | None = None
    last_provider_event_id: str | None = None
    last_sequence: int = 0


@dataclass(frozen=True)
class NormalizedEvent:
    attempt_id: str
    session_epoch_id: str
    process_generation_id: str
    turn_id: str | None
    kind: str
    provider_event_id: str | None = None
    native_subordinate_id: str | None = None
    payload_redacted: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class CandidateResult:
    """Provider/harness proposed result.  Never Executive Job completion."""

    attempt_id: str
    session_epoch_id: str
    process_generation_id: str
    artifact_digest: str | None
    summary: str | None
    complete_job_permitted: bool = False

    def __post_init__(self) -> None:
        if self.complete_job_permitted:
            raise ValueError("OperatorHarnessAdapter must not complete jobs")


@dataclass(frozen=True)
class ReconcileReport:
    """Observational only.  Supervisor decides kill/resume/LOST."""

    process_liveness: ProcessLiveness
    process_identity_match: bool | None
    provider_session_reachable: bool | None
    provider_writer_state: ProviderWriterState
    executive_writer_held: bool
    workspace_identity_match: bool | None
    profile_or_config_drift: bool | None
    resume_safe: bool
    recommended_failure_class: AdapterFailureClass | None = None
    may_kill: bool = False
    may_resume: bool = False
    may_mark_lost: bool = False
    may_start_attempt: bool = False

    def __post_init__(self) -> None:
        if self.may_kill or self.may_resume or self.may_mark_lost or self.may_start_attempt:
            raise ValueError("reconcile() may not decide lifecycle transitions")


@dataclass(frozen=True)
class ProfileValidation:
    requested: RequestedExecutionProfile
    accepted: bool
    reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class StageConfigRequest:
    attempt_id: str
    staging_directory: str
    requested: RequestedExecutionProfile
    operation_id: OperationId


@dataclass(frozen=True)
class StageConfigReceipt:
    attempt_id: str
    staging_directory: str
    files_written: tuple[str, ...]
    wrote_credentials: bool = False
    mutated_workspace: bool = False
    started_process: bool = False

    def __post_init__(self) -> None:
        if self.wrote_credentials or self.mutated_workspace or self.started_process:
            raise ValueError("stage_operator_config side-effect law violated")


@dataclass(frozen=True)
class LaunchComparison:
    requested: RequestedExecutionProfile
    observed: ObservedHarnessAttestation
    decision: LaunchDecision
    unclassified: tuple[str, ...] = ()


@dataclass(frozen=True)
class WriterFacts:
    process_liveness: ProcessLiveness
    executive_writer_held: bool
    provider_writer_state: ProviderWriterState


@dataclass(frozen=True)
class MethodContract:
    name: str
    classification: MethodClass
    timeout_seconds: float | None
    idempotent: bool
    cancellation: str
    allowed_side_effects: tuple[str, ...]
    forbidden_side_effects: tuple[str, ...]
    failure_classes: tuple[AdapterFailureClass, ...]
    notes: str


METHOD_CONTRACTS: dict[str, MethodContract] = {
    "describe_capabilities": MethodContract(
        name="describe_capabilities",
        classification=MethodClass.COMMON_REQUIRED,
        timeout_seconds=15.0,
        idempotent=True,
        cancellation="abort the describe call; no session created",
        allowed_side_effects=("read non-secret capability metadata",),
        forbidden_side_effects=(
            "start process",
            "read credentials",
            "mutate workspace",
            "mutate Executive lifecycle",
        ),
        failure_classes=(AdapterFailureClass.CONFIG_DRIFT,),
        notes="Returns CapabilityManifest plus optional/required method support.",
    ),
    "validate_requested_profile": MethodContract(
        name="validate_requested_profile",
        classification=MethodClass.COMMON_REQUIRED,
        timeout_seconds=15.0,
        idempotent=True,
        cancellation="abort validation; no durable effect",
        allowed_side_effects=("pure validation",),
        forbidden_side_effects=(
            "start process",
            "perform inference",
            "read credential bytes",
            "change credentials",
            "mutate authoritative workspace",
            "mutate Executive lifecycle",
        ),
        failure_classes=(
            AdapterFailureClass.CAPABILITY_ATTESTATION_FAILURE,
            AdapterFailureClass.WORKSPACE_MISMATCH,
            AdapterFailureClass.CONFIG_DRIFT,
        ),
        notes="Replaces kitchen-sink prepare(). Validation only.",
    ),
    "stage_operator_config": MethodContract(
        name="stage_operator_config",
        classification=MethodClass.COMMON_OPTIONAL,
        timeout_seconds=30.0,
        idempotent=True,
        cancellation="leave staging dir unchanged or replace atomically; no process",
        allowed_side_effects=(
            "write non-secret harness config under Attempt-owned staging directory",
        ),
        forbidden_side_effects=(
            "start process",
            "perform inference",
            "read credential bytes",
            "change credentials",
            "mutate authoritative workspace content",
            "mutate Executive lifecycle",
        ),
        failure_classes=(AdapterFailureClass.CONFIG_DRIFT,),
        notes="Idempotent on OperationId. Staging only; supervisor owns lifecycle.",
    ),
    "start_session": MethodContract(
        name="start_session",
        classification=MethodClass.COMMON_REQUIRED,
        timeout_seconds=60.0,
        idempotent=True,
        cancellation="do not leave an untracked provider session; report SESSION_MISSING if unknown",
        allowed_side_effects=(
            "create one primary provider session",
            "launch one ProcessGeneration when supervisor already allocated it",
        ),
        forbidden_side_effects=(
            "complete_job",
            "create a second session for the same OperationId",
            "adopt another process's stdio",
        ),
        failure_classes=(
            AdapterFailureClass.AUTH_FAILURE,
            AdapterFailureClass.QUOTA_OR_RATE_LIMIT,
            AdapterFailureClass.PROVIDER_CONCURRENCY,
            AdapterFailureClass.PROCESS_CRASH,
            AdapterFailureClass.ACTIVE_WRITER_CONFLICT,
            AdapterFailureClass.CAPABILITY_ATTESTATION_FAILURE,
            AdapterFailureClass.WORKSPACE_MISMATCH,
        ),
        notes="Requires sealed RequestedExecutionProfile and Executive OperationId.",
    ),
    "begin_turn": MethodContract(
        name="begin_turn",
        classification=MethodClass.COMMON_REQUIRED,
        timeout_seconds=30.0,
        idempotent=True,
        cancellation="turn must not start if cancelled before provider ack",
        allowed_side_effects=("start one model turn after ALLOW LaunchDecision",),
        forbidden_side_effects=(
            "work before attestation ALLOW",
            "complete_job",
            "second turn for same OperationId",
        ),
        failure_classes=(
            AdapterFailureClass.CAPABILITY_ATTESTATION_FAILURE,
            AdapterFailureClass.SESSION_MISSING,
            AdapterFailureClass.ACTIVE_WRITER_CONFLICT,
            AdapterFailureClass.HUMAN_APPROVAL_REQUIRED,
        ),
        notes="First meaningful work turn is illegal until LaunchDecision.ALLOW.",
    ),
    "read_events": MethodContract(
        name="read_events",
        classification=MethodClass.COMMON_REQUIRED,
        timeout_seconds=30.0,
        idempotent=True,
        cancellation="return events collected so far plus cursor; no rewind implied",
        allowed_side_effects=("read provider event stream",),
        forbidden_side_effects=("persist raw unredacted secrets", "create Executive event store"),
        failure_classes=(
            AdapterFailureClass.SESSION_MISSING,
            AdapterFailureClass.PROCESS_CRASH,
            AdapterFailureClass.MCP_OR_TOOL_TRANSPORT_FAILURE,
        ),
        notes="Cursor is the reconnect contract. Duplicates dropped by provider_event_id when present.",
    ),
    "interrupt_turn": MethodContract(
        name="interrupt_turn",
        classification=MethodClass.COMMON_REQUIRED,
        timeout_seconds=30.0,
        idempotent=True,
        cancellation="already an interrupt; repeated calls are no-ops after terminal turn",
        allowed_side_effects=("request in-flight turn stop",),
        forbidden_side_effects=("kill unrelated processes", "complete_job", "release writer falsely"),
        failure_classes=(
            AdapterFailureClass.SESSION_MISSING,
            AdapterFailureClass.PROCESS_CRASH,
        ),
        notes="Does not mark Attempt LOST. Supervisor decides.",
    ),
    "collect_candidate_result": MethodContract(
        name="collect_candidate_result",
        classification=MethodClass.COMMON_REQUIRED,
        timeout_seconds=60.0,
        idempotent=True,
        cancellation="return incomplete candidate or VALIDATION_FAILURE; never complete_job",
        allowed_side_effects=("read proposed artifacts",),
        forbidden_side_effects=("complete_job", "validate as Executive", "grant review"),
        failure_classes=(
            AdapterFailureClass.MODEL_OR_WORK_RESULT_FAILURE,
            AdapterFailureClass.VALIDATION_FAILURE,
        ),
        notes="CandidateResult.complete_job_permitted is always false.",
    ),
    "graceful_stop": MethodContract(
        name="graceful_stop",
        classification=MethodClass.COMMON_REQUIRED,
        timeout_seconds=60.0,
        idempotent=True,
        cancellation="escalate to supervisor signal_process; adapter must not steal locks",
        allowed_side_effects=("request harness exit", "observe process death", "observe writer release"),
        forbidden_side_effects=(
            "delete provider lock files",
            "invent provider RELEASED",
            "complete_job",
        ),
        failure_classes=(
            AdapterFailureClass.PROCESS_CRASH,
            AdapterFailureClass.ACTIVE_WRITER_CONFLICT,
            AdapterFailureClass.SESSION_MISSING,
        ),
        notes="Provider writer stays UNKNOWN until the provider confirms release.",
    ),
    "cancel": MethodContract(
        name="cancel",
        classification=MethodClass.COMMON_REQUIRED,
        timeout_seconds=60.0,
        idempotent=True,
        cancellation="this is the cancel path; repeats are no-ops",
        allowed_side_effects=("stop turn and request process exit",),
        forbidden_side_effects=("complete_job", "writer steal", "mutate other Attempts"),
        failure_classes=(
            AdapterFailureClass.PROCESS_CRASH,
            AdapterFailureClass.ACTIVE_WRITER_CONFLICT,
        ),
        notes="Executive still owns Attempt status transition.",
    ),
    "reconcile": MethodContract(
        name="reconcile",
        classification=MethodClass.COMMON_REQUIRED,
        timeout_seconds=30.0,
        idempotent=True,
        cancellation="return partial ReconcileReport; no lifecycle mutation",
        allowed_side_effects=("inspect process table", "ask provider session reachability"),
        forbidden_side_effects=(
            "kill",
            "resume",
            "mark Attempt LOST",
            "start Attempt",
            "select provider",
            "release quota",
            "complete_job",
        ),
        failure_classes=(
            AdapterFailureClass.PROCESS_CRASH,
            AdapterFailureClass.SESSION_MISSING,
            AdapterFailureClass.ACTIVE_WRITER_CONFLICT,
            AdapterFailureClass.WORKSPACE_MISMATCH,
            AdapterFailureClass.CONFIG_DRIFT,
        ),
        notes="Observational. ReconcileReport forbids lifecycle flags.",
    ),
    "probe": MethodContract(
        name="probe",
        classification=MethodClass.COMMON_OPTIONAL,
        timeout_seconds=30.0,
        idempotent=True,
        cancellation="abort probe; no session retained",
        allowed_side_effects=("laboratory/read-only capability probe",),
        forbidden_side_effects=("production worker activation", "write-capable work"),
        failure_classes=(AdapterFailureClass.AUTH_FAILURE, AdapterFailureClass.CONFIG_DRIFT),
        notes="P0-style inert probe only.",
    ),
    "resume_session": MethodContract(
        name="resume_session",
        classification=MethodClass.COMMON_OPTIONAL,
        timeout_seconds=60.0,
        idempotent=True,
        cancellation="do not attach a second writer; report ACTIVE_WRITER_CONFLICT if unsure",
        allowed_side_effects=(
            "start a NEW ProcessGeneration that resumes an existing provider_session_id",
        ),
        forbidden_side_effects=(
            "adopt old stdio",
            "resume an ABANDONED epoch",
            "cross Attempt resume",
            "free writer because process is dead",
        ),
        failure_classes=(
            AdapterFailureClass.ACTIVE_WRITER_CONFLICT,
            AdapterFailureClass.SESSION_MISSING,
            AdapterFailureClass.PROCESS_CRASH,
            AdapterFailureClass.CAPABILITY_ATTESTATION_FAILURE,
        ),
        notes="Requires resume_safe True. Adapters without native resume remain valid.",
    ),
    "send_input": MethodContract(
        name="send_input",
        classification=MethodClass.COMMON_OPTIONAL,
        timeout_seconds=15.0,
        idempotent=True,
        cancellation="drop unacked input",
        allowed_side_effects=("steer in-flight turn",),
        forbidden_side_effects=("start a new session", "complete_job"),
        failure_classes=(AdapterFailureClass.SESSION_MISSING,),
        notes="Capability-negotiated.",
    ),
    "respond_to_approval": MethodContract(
        name="respond_to_approval",
        classification=MethodClass.COMMON_OPTIONAL,
        timeout_seconds=30.0,
        idempotent=True,
        cancellation="leave approval pending",
        allowed_side_effects=("submit human approval decision",),
        forbidden_side_effects=("auto-approve by adapter policy",),
        failure_classes=(AdapterFailureClass.HUMAN_APPROVAL_REQUIRED,),
        notes="Human/supervisor decision, not model self-approval.",
    ),
    "fork_session": MethodContract(
        name="fork_session",
        classification=MethodClass.COMMON_OPTIONAL,
        timeout_seconds=60.0,
        idempotent=True,
        cancellation="do not leave an untracked fork",
        allowed_side_effects=("create subordinate native handle inside current epoch",),
        forbidden_side_effects=(
            "create Executive child Job",
            "consume primary epoch counter",
            "claim independent review",
            "enable helpers on write-capable Attempts without ceiling",
        ),
        failure_classes=(
            AdapterFailureClass.CAPABILITY_ATTESTATION_FAILURE,
            AdapterFailureClass.SESSION_MISSING,
        ),
        notes="Subordinate only. Not a session epoch.",
    ),
    "checkpoint": MethodContract(
        name="checkpoint",
        classification=MethodClass.COMMON_OPTIONAL,
        timeout_seconds=30.0,
        idempotent=True,
        cancellation="omit checkpoint; last trusted checkpoint remains",
        allowed_side_effects=("emit checkpoint candidate for Executive to persist",),
        forbidden_side_effects=("write Executive checkpoint_json directly",),
        failure_classes=(AdapterFailureClass.MODEL_OR_WORK_RESULT_FAILURE,),
        notes="Executive persists checkpoint_json.",
    ),
    "prepare": MethodContract(
        name="prepare",
        classification=MethodClass.REJECTED,
        timeout_seconds=None,
        idempotent=True,
        cancellation="n/a",
        allowed_side_effects=(),
        forbidden_side_effects=("kitchen-sink prepare",),
        failure_classes=(),
        notes="Removed. Use validate_requested_profile + optional stage_operator_config.",
    ),
    "complete_job": MethodContract(
        name="complete_job",
        classification=MethodClass.REJECTED,
        timeout_seconds=None,
        idempotent=True,
        cancellation="n/a",
        allowed_side_effects=(),
        forbidden_side_effects=("complete_job",),
        failure_classes=(),
        notes="Executive runtime only.",
    ),
    "signal_process": MethodContract(
        name="signal_process",
        classification=MethodClass.SUPERVISOR_RUNTIME,
        timeout_seconds=15.0,
        idempotent=True,
        cancellation="supervisor owns the signal",
        allowed_side_effects=("OS signal to a local pid the supervisor already knows",),
        forbidden_side_effects=("provider lock deletion", "stdio adoption"),
        failure_classes=(AdapterFailureClass.PROCESS_CRASH,),
        notes="Not on the provider-neutral adapter. Local supervisor machinery.",
    ),
}


@runtime_checkable
class OperatorHarnessAdapter(Protocol):
    """Typed rich-operator adapter.  Implementations are out of scope for P1A."""

    interface_version: str

    def describe_capabilities(self) -> Mapping[str, object]: ...

    def validate_requested_profile(
        self, requested: RequestedExecutionProfile
    ) -> ProfileValidation: ...

    def start_session(
        self,
        *,
        operation_id: OperationId,
        requested: RequestedExecutionProfile,
        attempt_id: str,
    ) -> SessionEpochRef: ...

    def begin_turn(
        self,
        *,
        operation_id: OperationId,
        generation: ProcessGenerationRef,
        launch: LaunchComparison,
    ) -> TurnRef: ...

    def read_events(
        self, cursor: EventCursor, *, timeout_seconds: float = 30.0
    ) -> tuple[tuple[NormalizedEvent, ...], EventCursor]: ...

    def interrupt_turn(self, turn: TurnRef, *, operation_id: OperationId) -> None: ...

    def collect_candidate_result(self, turn: TurnRef) -> CandidateResult: ...

    def graceful_stop(
        self, generation: ProcessGenerationRef, *, operation_id: OperationId
    ) -> WriterFacts: ...

    def cancel(
        self, generation: ProcessGenerationRef, *, reason: str, operation_id: OperationId
    ) -> WriterFacts: ...

    def reconcile(self, generation: ProcessGenerationRef) -> ReconcileReport: ...


def writer_realm_key(worker_id: str, provider_session_id: str) -> tuple[str, str]:
    worker = str(worker_id or "").strip()
    session = str(provider_session_id or "").strip()
    if not worker or not session:
        raise ValueError("writer realm requires worker_id and provider_session_id")
    return (worker, session)


def derive_resume_safety(
    *,
    epoch_state: SessionEpochState,
    facts: WriterFacts,
    process_identity_match: bool,
    workspace_match: bool,
    profile_match: bool,
    live_transport_adoptable: bool = False,
) -> bool:
    """Resume is derived.  It is not independent durable truth."""

    if live_transport_adoptable:
        return False
    if epoch_state is not SessionEpochState.CURRENT:
        return False
    if not facts.executive_writer_held:
        return False
    if facts.process_liveness is ProcessLiveness.UNKNOWN:
        return False
    if facts.process_liveness is ProcessLiveness.PROVEN_DEAD:
        if facts.provider_writer_state is not ProviderWriterState.RELEASED:
            return False
    if facts.provider_writer_state is ProviderWriterState.HELD and facts.process_liveness is not ProcessLiveness.ALIVE:
        return False
    if facts.provider_writer_state is ProviderWriterState.UNKNOWN:
        return False
    return bool(process_identity_match and workspace_match and profile_match)


def process_end_does_not_release_writer(ended_at_ms: int | None, facts: WriterFacts) -> WriterFacts:
    """ended_at records process death only."""

    if ended_at_ms is None:
        return facts
    return WriterFacts(
        process_liveness=ProcessLiveness.PROVEN_DEAD,
        executive_writer_held=facts.executive_writer_held,
        provider_writer_state=facts.provider_writer_state,
    )


def abandon_epoch(facts: WriterFacts) -> WriterFacts:
    """Abandonment drops Executive ownership.  It does not invent RELEASED."""

    provider = facts.provider_writer_state
    if provider is ProviderWriterState.RELEASED:
        provider = ProviderWriterState.RELEASED
    elif provider is ProviderWriterState.HELD:
        provider = ProviderWriterState.HELD
    else:
        provider = ProviderWriterState.UNKNOWN
    return WriterFacts(
        process_liveness=facts.process_liveness,
        executive_writer_held=False,
        provider_writer_state=provider,
    )


def classify_capability(
    name: str,
    *,
    required: Sequence[str],
    allowed_ambient: Sequence[str],
    forbidden: Sequence[str],
) -> CapabilityClass:
    value = str(name or "").strip()
    if value in set(forbidden):
        return CapabilityClass.FORBIDDEN
    if value in set(required):
        return CapabilityClass.REQUIRED
    if value in set(allowed_ambient):
        return CapabilityClass.ALLOWED_AMBIENT
    return CapabilityClass.UNCLASSIFIED


def compare_launch(
    requested: RequestedExecutionProfile,
    observed: ObservedHarnessAttestation,
    *,
    unclassified: Sequence[str] = (),
    missing_required: Sequence[str] = (),
    forbidden_present: Sequence[str] = (),
    workspace_match: bool = True,
    auth_realm_match: bool = True,
    config_drift: bool = False,
    lab_unclassified_policy: bool = False,
    supports_subagent_capability_ceiling: bool = False,
) -> LaunchComparison:
    decision = LaunchDecision.ALLOW
    if observed.served_model and observed.served_model != requested.requested_model:
        decision = LaunchDecision.REFUSE_SERVED_MODEL_MISMATCH
    elif missing_required:
        decision = LaunchDecision.REFUSE_MISSING_REQUIRED
    elif forbidden_present:
        decision = LaunchDecision.REFUSE_FORBIDDEN
    elif unclassified and requested.write_capable:
        decision = LaunchDecision.REFUSE_UNCLASSIFIED
    elif unclassified and not lab_unclassified_policy:
        decision = LaunchDecision.REFUSE_UNCLASSIFIED
    elif not workspace_match:
        decision = LaunchDecision.REFUSE_WORKSPACE_MISMATCH
    elif not auth_realm_match:
        decision = LaunchDecision.REFUSE_AUTH_REALM_MISMATCH
    elif config_drift:
        decision = LaunchDecision.REFUSE_CONFIG_DRIFT
    elif requested.write_capable and requested.native_helper_policy is NativeHelperPolicy.PARENT_READ_ONLY_CEILING:
        decision = LaunchDecision.REFUSE_HELPER_CEILING_MISSING
    elif (
        requested.write_capable
        and requested.native_helper_policy is NativeHelperPolicy.REQUIRES_SUBAGENT_CAPABILITY_CEILING
        and not supports_subagent_capability_ceiling
    ):
        decision = LaunchDecision.REFUSE_HELPER_CEILING_MISSING
    return LaunchComparison(
        requested=requested,
        observed=observed,
        decision=decision,
        unclassified=tuple(unclassified),
    )


def first_work_turn_allowed(decision: LaunchDecision) -> bool:
    return decision is LaunchDecision.ALLOW


def native_helpers_allowed(*, write_capable: bool, supports_subagent_capability_ceiling: bool) -> bool:
    if not write_capable:
        return True
    return bool(supports_subagent_capability_ceiling)


def restore_invalidation(facts: WriterFacts) -> tuple[WriterFacts, str]:
    """Restored rows are historical.  They are not live execution authority."""

    invalidated = WriterFacts(
        process_liveness=ProcessLiveness.UNKNOWN,
        executive_writer_held=False,
        provider_writer_state=facts.provider_writer_state
        if facts.provider_writer_state is not ProviderWriterState.RELEASED
        else ProviderWriterState.UNKNOWN,
    )
    return invalidated, POST_RESTORE_ATTEMPT_STATUS


def may_bind_provider_session(
    *,
    worker_id: str,
    provider_session_id: str,
    existing_bindings: Mapping[tuple[str, str], str],
    epoch_id: str,
) -> bool:
    key = writer_realm_key(worker_id, provider_session_id)
    owner = existing_bindings.get(key)
    return owner is None or owner == epoch_id


def may_hold_executive_writer(
    *,
    worker_id: str,
    provider_session_id: str,
    generation_id: str,
    held_by: Mapping[tuple[str, str], str],
) -> bool:
    key = writer_realm_key(worker_id, provider_session_id)
    owner = held_by.get(key)
    return owner is None or owner == generation_id


__all__ = [
    "ACCOUNT_REALM_STATUS",
    "ATTEMPT_BOUNDARY_MATRIX",
    "AuthIdentityConfidence",
    "AuthRealmFact",
    "AdapterFailureClass",
    "AttemptBoundary",
    "CANONICAL_SESSION_FIELD",
    "CARDINALITY",
    "CandidateResult",
    "CapabilityClass",
    "CapabilityIdentity",
    "CapabilityManifest",
    "EventCursor",
    "FORBIDDEN_SESSION_SYNONYM",
    "LaunchComparison",
    "LaunchDecision",
    "LIVE_APP_SERVER_ADOPTION",
    "METHOD_CONTRACTS",
    "MethodClass",
    "MethodContract",
    "NativeHelperPolicy",
    "NormalizedEvent",
    "OPERATOR_HARNESS_INTERFACE_VERSION",
    "ObservedHarnessAttestation",
    "OperationId",
    "OperatorHarnessAdapter",
    "POST_RESTORE_ATTEMPT_STATUS",
    "ProcessGenerationRef",
    "ProcessLiveness",
    "ProfileValidation",
    "ProviderWriterState",
    "REATTEST_TRIGGERS",
    "RESTORE_POLICY",
    "ReconcileReport",
    "RequestedExecutionProfile",
    "SessionEpochRef",
    "SessionEpochState",
    "StageConfigReceipt",
    "StageConfigRequest",
    "TurnRef",
    "V1_QUALITY_TRADEOFF",
    "WRITER_REALM_KEY",
    "WorkspaceIdentity",
    "WriterFacts",
    "abandon_epoch",
    "classify_capability",
    "compare_launch",
    "derive_resume_safety",
    "first_work_turn_allowed",
    "may_bind_provider_session",
    "may_hold_executive_writer",
    "native_helpers_allowed",
    "process_end_does_not_release_writer",
    "restore_invalidation",
    "writer_realm_key",
]
