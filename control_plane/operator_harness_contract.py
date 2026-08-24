"""OHF-P1A-R3.3 provider-neutral Operator Harness contract.

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

import inspect
import re
from dataclasses import dataclass, field, fields
from enum import Enum
from typing import Mapping, Protocol, Sequence, get_type_hints, runtime_checkable


OPERATOR_HARNESS_INTERFACE_VERSION = "mastermind.operator_harness/v1"
CARDINALITY = "CARDINALITY_B"
WRITER_REALM_KEY = ("worker_id", "provider_session_id")
PREBIND_WRITER_FENCE_KEY = ("session_epoch_id",)
CANONICAL_SESSION_FIELD = "provider_session_id"
FORBIDDEN_SESSION_SYNONYM = "native_session_id"
V1_QUALITY_TRADEOFF = "V1_QUALITY_TRADEOFF_ACCEPTED"
ACCOUNT_REALM_STATUS = "ACCOUNT_REALM_ATTESTATION_UNPROVEN"
LIVE_APP_SERVER_ADOPTION = "NOT_SUPPORTED"
RESTORE_POLICY = "OPTION_A_BACKUP_MAY_CAPTURE_ACTIVE_INVALIDATE_ON_RESTORE"
POST_RESTORE_ATTEMPT_STATUS = "LOST"
OPERATION_AGGREGATE_TYPE = "operator_operation"
OPERATION_COMMAND_ID_PREFIX = "ohf-op:"
WORKER_SLOT_AUTH_BINDING_PRODUCTION_INVARIANT = (
    "A worker_id used as the V1 session realm must not be silently rebound to a "
    "different provider/auth home/account while historical native-session bindings exist."
)

# Mirrors control_plane.executive_runtime._COMMAND_ID_RE.  Duplicated here so
# this pure module does not import the runtime.  Tests pin the two patterns equal.
COMMAND_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
COMMAND_ID_MAX_LEN = 128  # 1 first char + {0,127}
OPERATION_RECEIPT_COMMAND_SUFFIXES: tuple[str, ...] = (
    "applied",
    "refused",
    "effect-unknown",
    "reconciled",
)
LONGEST_OPERATION_RECEIPT_SUFFIX_LEN = max(
    len(f":{item}") for item in OPERATION_RECEIPT_COMMAND_SUFFIXES
)
# Longest derived receipt is `:effect-unknown` (15).  Every accepted OperationId
# must leave room for that suffix under COMMAND_ID_MAX_LEN.
MAX_OPERATION_ID_LEN = COMMAND_ID_MAX_LEN - LONGEST_OPERATION_RECEIPT_SUFFIX_LEN


def operation_id_permits_all_derived_receipts(command_id: str) -> bool:
    """True iff command_id and every derived receipt match COMMAND_ID_RE."""

    value = str(command_id or "")
    if COMMAND_ID_RE.fullmatch(value) is None:
        return False
    if len(value) > MAX_OPERATION_ID_LEN:
        return False
    for suffix in OPERATION_RECEIPT_COMMAND_SUFFIXES:
        if COMMAND_ID_RE.fullmatch(f"{value}:{suffix}") is None:
            return False
    return True

LEGACY_SEALED_WORKER_ATTEMPT_FIELDS: frozenset[str] = frozenset(
    {
        "provider_session_id",
        "pid",
        "pgid",
        "process_start_identity",
        "boot_id",
    }
)
OHF_PROPOSED_ATTEMPT_COLUMNS: frozenset[str] = frozenset(
    {
        "execution_mode",
        "requested_execution_profile_json",
        "requested_execution_profile_digest",
    }
)
OHF_FORBIDDEN_ATTEMPT_COLUMNS: frozenset[str] = frozenset(
    {
        "current_session_epoch_id",
        "current_process_generation_id",
    }
)
EXECUTIVE_ALLOCATED_IDS: frozenset[str] = frozenset(
    {
        "session_epoch_id",
        "epoch_number",
        "process_generation_id",
        "generation_number",
        "turn_id",
    }
)
ADAPTER_OBSERVED_IDS: frozenset[str] = frozenset(
    {
        "provider_session_id",
        "provider_event_id",
        "provider_native_fork_id",
        "provider_native_turn_id",
        "provider_replay_cursor",
    }
)
FORBIDDEN_COMPARE_LAUNCH_PARAMETERS: frozenset[str] = frozenset(
    {
        "unclassified",
        "missing_required",
        "forbidden_present",
        "workspace_match",
        "auth_realm_match",
        "config_drift",
        "lab_unclassified_policy",
        "supports_subagent_capability_ceiling",
    }
)
EXECUTIVE_OWNED_RECONCILE_FIELDS: frozenset[str] = frozenset(
    {
        "executive_writer_held",
        "resume_safe",
        "workspace_identity_match",
        "profile_or_config_drift",
        "process_identity_match",
        "may_kill",
        "may_resume",
        "may_mark_lost",
        "may_start_attempt",
    }
)

PROPOSED_SQL_INVARIANTS: dict[str, str] = {
    "unique_attempt_epoch_number": "UNIQUE(attempt_id, epoch_number)",
    "one_current_epoch": (
        "CREATE UNIQUE INDEX harness_session_epochs_one_current "
        "ON harness_session_epochs(attempt_id) WHERE state = 'CURRENT'"
    ),
    "prebind_epoch_writer": (
        "CREATE UNIQUE INDEX process_generations_one_epoch_writer "
        "ON process_generations(session_epoch_id) WHERE executive_writer_held = 1"
    ),
    "postbind_realm_writer": (
        "CREATE UNIQUE INDEX process_generations_one_executive_writer "
        "ON process_generations(worker_id, provider_session_id) "
        "WHERE executive_writer_held = 1 AND provider_session_id IS NOT NULL"
    ),
    "epoch_session_realm": (
        "CREATE UNIQUE INDEX harness_session_epochs_session_realm "
        "ON harness_session_epochs(worker_id, provider_session_id) "
        "WHERE provider_session_id IS NOT NULL"
    ),
    "unique_generation_number": "UNIQUE(session_epoch_id, generation_number)",
    "process_identity_pid_positive": "CHECK (pid IS NULL OR pid > 0)",
    "process_identity_pgid_positive": "CHECK (pgid IS NULL OR pgid > 0)",
    "process_identity_recorded_together": (
        "CHECK ("
        "(pid IS NULL AND pgid IS NULL AND process_start_identity IS NULL "
        "AND boot_id IS NULL) OR "
        "(pid IS NOT NULL AND pgid IS NOT NULL "
        "AND length(trim(process_start_identity)) > 0 "
        "AND length(trim(boot_id)) > 0))"
    ),
}


class AttemptExecutionMode(str, Enum):
    SEALED_WORKER = "SEALED_WORKER"
    OPERATOR_HARNESS = "OPERATOR_HARNESS"


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


class ObservedTriState(str, Enum):
    VERIFIED = "VERIFIED"
    FALSE = "FALSE"
    UNKNOWN = "UNKNOWN"


class AuthRealmRequirement(str, Enum):
    SLOT_BOUND_V1 = "SLOT_BOUND_V1"
    VERIFIED_PROVIDER_ACCOUNT = "VERIFIED_PROVIDER_ACCOUNT"


class LaunchDecision(str, Enum):
    ALLOW = "ALLOW"
    REFUSE_SERVED_MODEL_MISMATCH = "REFUSE_SERVED_MODEL_MISMATCH"
    REFUSE_SERVED_MODEL_UNKNOWN = "REFUSE_SERVED_MODEL_UNKNOWN"
    REFUSE_MISSING_REQUIRED = "REFUSE_MISSING_REQUIRED"
    REFUSE_FORBIDDEN = "REFUSE_FORBIDDEN"
    REFUSE_UNCLASSIFIED = "REFUSE_UNCLASSIFIED"
    REFUSE_WORKSPACE_MISMATCH = "REFUSE_WORKSPACE_MISMATCH"
    REFUSE_AUTH_REALM_MISMATCH = "REFUSE_AUTH_REALM_MISMATCH"
    REFUSE_CONFIG_DRIFT = "REFUSE_CONFIG_DRIFT"
    REFUSE_HELPER_CEILING_MISSING = "REFUSE_HELPER_CEILING_MISSING"
    REFUSE_HARNESS_BINARY_MISMATCH = "REFUSE_HARNESS_BINARY_MISMATCH"
    REFUSE_SANDBOX_MISMATCH = "REFUSE_SANDBOX_MISMATCH"
    REFUSE_APPROVAL_MISMATCH = "REFUSE_APPROVAL_MISMATCH"
    REFUSE_NETWORK_MISMATCH = "REFUSE_NETWORK_MISMATCH"
    REFUSE_UNATTESTABLE = "REFUSE_UNATTESTABLE"


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


class OperationIdempotencyClass(str, Enum):
    PURE_IDEMPOTENT = "PURE_IDEMPOTENT"
    EXECUTIVE_DEDUPED_AT_MOST_ONCE = "EXECUTIVE_DEDUPED_AT_MOST_ONCE"
    PROVIDER_NATIVE_IDEMPOTENT = "PROVIDER_NATIVE_IDEMPOTENT"
    NON_REPLAYABLE_ON_UNKNOWN_EFFECT = "NON_REPLAYABLE_ON_UNKNOWN_EFFECT"


class OperationReceiptKind(str, Enum):
    INTENT = "OPERATOR_OPERATION_INTENT"
    APPLIED = "OPERATOR_OPERATION_APPLIED"
    REFUSED = "OPERATOR_OPERATION_REFUSED"
    EFFECT_UNKNOWN = "OPERATOR_OPERATION_EFFECT_UNKNOWN"
    RECONCILED = "OPERATOR_OPERATION_RECONCILED"


class OperationKind(str, Enum):
    """What an OperationId INTENT authorized.  Lives in events.payload_json."""

    START_SESSION = "start_session"
    RESUME_SESSION = "resume_session"
    BEGIN_TURN = "begin_turn"


OPERATION_INTENT_TARGET_FIELDS: tuple[str, ...] = (
    "operation_kind",
    "attempt_id",
    "session_epoch_id",
    "process_generation_id",
    "worker_id",
    "provider_session_id",
)


class OperationResolution(str, Enum):
    NOT_STARTED = "NOT_STARTED"
    MAY_RETRY_SAME_OPERATION_ID = "MAY_RETRY_SAME_OPERATION_ID"
    APPLIED = "APPLIED"
    REFUSED = "REFUSED"
    EFFECT_UNKNOWN = "EFFECT_UNKNOWN"
    RECONCILED = "RECONCILED"


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


class TransactionGroup(str, Enum):
    TX1_SEAL_RICH_ATTEMPT = "TX-1"
    TX2_START_INTENT = "TX-2"
    TX3_BIND_START_RESULT = "TX-3"
    TX4_SEAL_ATTESTATION = "TX-4"
    TX5_BEGIN_TURN_INTENT = "TX-5"
    TX6_GRACEFUL_GENERATION_STOP = "TX-6"
    TX7_HARD_PROCESS_DEATH = "TX-7"
    TX8_ABANDON_POISONED_EPOCH = "TX-8"
    TX9_RESTORE_INVALIDATION = "TX-9"
    TX10_SAME_EPOCH_GENERATION_RECOVERY = "TX-10"
    TX11_BIND_RESUME_RESULT = "TX-11"


class SameEpochRecoveryRefusal(str, Enum):
    EPOCH_NOT_CURRENT = "EPOCH_NOT_CURRENT"
    PROCESS_NOT_PROVEN_DEAD = "PROCESS_NOT_PROVEN_DEAD"
    PROCESS_LIVENESS_UNKNOWN = "PROCESS_LIVENESS_UNKNOWN"
    PROVIDER_WRITER_NOT_RELEASED = "PROVIDER_WRITER_NOT_RELEASED"
    RESUME_NOT_SAFE = "RESUME_NOT_SAFE"
    OLD_WRITER_NOT_HELD = "OLD_WRITER_NOT_HELD"
    SUCCESSOR_WRITER_CONFLICT = "SUCCESSOR_WRITER_CONFLICT"
    OPERATION_ID_DUPLICATE = "OPERATION_ID_DUPLICATE"
    GENERATION_NOT_SEQUENTIAL = "GENERATION_NOT_SEQUENTIAL"
    EPOCH_MISMATCH = "EPOCH_MISMATCH"


class SameEpochRecoveryReplay(str, Enum):
    RETRY_SAME_OPERATION_ON_ALLOCATED_GENERATION = (
        "RETRY_SAME_OPERATION_ON_ALLOCATED_GENERATION"
    )
    EFFECT_UNKNOWN_HOLD_GENERATION = "EFFECT_UNKNOWN_HOLD_GENERATION"
    NOT_STARTED = "NOT_STARTED"
    APPLIED = "APPLIED"
    REFUSED = "REFUSED"
    RECONCILED = "RECONCILED"


class ResumeBindRefusal(str, Enum):
    INTENT_MISSING = "INTENT_MISSING"
    INTENT_TARGET_MISMATCH = "INTENT_TARGET_MISMATCH"
    EPOCH_NOT_CURRENT = "EPOCH_NOT_CURRENT"
    GENERATION_NOT_WRITER = "GENERATION_NOT_WRITER"
    EPOCH_SESSION_UNBOUND = "EPOCH_SESSION_UNBOUND"
    HANDOFF_MISMATCH = "HANDOFF_MISMATCH"
    PROVIDER_SESSION_MISMATCH = "PROVIDER_SESSION_MISMATCH"
    PROCESS_IDENTITY_INCOMPLETE = "PROCESS_IDENTITY_INCOMPLETE"
    INDEX_PROJECTION_MISMATCH = "INDEX_PROJECTION_MISMATCH"
    ALREADY_APPLIED_CONFLICT = "ALREADY_APPLIED_CONFLICT"
    EPOCH_MISMATCH = "EPOCH_MISMATCH"


class EnforcementSite(str, Enum):
    SQL_INDEX = "SQL_INDEX"
    SQL_TRIGGER = "SQL_TRIGGER"
    BEGIN_IMMEDIATE = "BEGIN_IMMEDIATE"
    PURE_COMPARATOR = "PURE_COMPARATOR"
    SUPERVISOR = "SUPERVISOR"


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
    "served_model_unknown": AttemptBoundary.REFUSE,
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


TRANSACTION_GROUPS: dict[TransactionGroup, str] = {
    TransactionGroup.TX1_SEAL_RICH_ATTEMPT: (
        "BEGIN IMMEDIATE: set execution_mode=OPERATOR_HARNESS; persist "
        "RequestedExecutionProfile JSON+digest; append profile-sealed receipt. "
        "No provider/process side effect."
    ),
    TransactionGroup.TX2_START_INTENT: (
        "BEGIN IMMEDIATE: verify Attempt lease/fence and OPERATOR_HARNESS; "
        "allocate epoch/generation IDs; insert CURRENT epoch with "
        "provider_session_id NULL; insert generation executive_writer_held=1; "
        "append OPERATOR_OPERATION_INTENT with command_id=OperationId. "
        "Commit before adapter call."
    ),
    TransactionGroup.TX3_BIND_START_RESULT: (
        "BEGIN IMMEDIATE: verify INTENT; verify epoch CURRENT and generation "
        "still owns pre-bind writer; bind immutable provider_session_id; bind "
        "generation index projection; record process identity; enforce post-bind "
        "realm uniqueness; append OPERATOR_OPERATION_APPLIED."
    ),
    TransactionGroup.TX4_SEAL_ATTESTATION: (
        "BEGIN IMMEDIATE: persist ObservedHarnessAttestation+digest; append "
        "ATTESTATION_OBSERVED. Then run pure compare_launch. No work turn before ALLOW."
    ),
    TransactionGroup.TX5_BEGIN_TURN_INTENT: (
        "BEGIN IMMEDIATE: allocate TurnRef; append BEGIN_TURN INTENT with "
        "command_id=OperationId. Adapter side effect only after commit. "
        "Ack appends APPLIED. EFFECT_UNKNOWN is non-replayable."
    ),
    TransactionGroup.TX6_GRACEFUL_GENERATION_STOP: (
        "After confirmed graceful stop: mark generation ended; record historical "
        "provider writer; clear executive_writer_held; append stop receipt. "
        "Only then may a successor generation for the same epoch acquire the writer."
    ),
    TransactionGroup.TX7_HARD_PROCESS_DEATH: (
        "BEGIN IMMEDIATE: record ended/process death; do NOT clear "
        "executive_writer_held; do NOT invent provider RELEASED; append death observation."
    ),
    TransactionGroup.TX8_ABANDON_POISONED_EPOCH: (
        "Allowed only when process is PROVEN_DEAD (or process absence proven). "
        "BEGIN IMMEDIATE: mark epoch ABANDONED; clear executive_writer_held; "
        "preserve provider writer observation; append abandon receipt. "
        "Do not create S2 in the same transaction."
    ),
    TransactionGroup.TX9_RESTORE_INVALIDATION: (
        "BEGIN IMMEDIATE before service re-enable: OPERATOR_HARNESS active Attempts "
        "→ LOST; CURRENT epochs → ABANDONED; executive_writer_held → 0; historical "
        "provider observations unchanged; append OHF_RESTORE_INVALIDATED."
    ),
    TransactionGroup.TX10_SAME_EPOCH_GENERATION_RECOVERY: (
        "BEGIN IMMEDIATE: verify epoch CURRENT; verify old generation is the held "
        "writer; verify old process PROVEN_DEAD; verify provider_writer_state "
        "RELEASED; verify Executive-derived resume_safe; clear old "
        "executive_writer_held; allocate next process_generation_id + "
        "generation_number on the SAME epoch; insert successor with "
        "executive_writer_held=1 and provider_session_id index projection already "
        "bound to S1; append OPERATOR_OPERATION_INTENT command_id=OperationId "
        "for resume_session whose events.payload_json is the typed "
        "OperationIntentTarget (operation_kind=resume_session, attempt_id, "
        "session_epoch_id, process_generation_id, worker_id, already-bound "
        "provider_session_id). No sidecar table. No new SessionEpoch. No new "
        "Attempt. Commit before resume_session(). Executive then passes "
        "ProviderSessionHandoff of the already-bound S1 into resume_session. "
        "Process identity and APPLIED are TX-11, not TX-10."
    ),
    TransactionGroup.TX11_BIND_RESUME_RESULT: (
        "BEGIN IMMEDIATE after resume_session observation: verify TX-10 INTENT "
        "for this OperationId including typed OperationIntentTarget against "
        "current G2/S1 (kind, attempt, epoch, generation, worker, bound "
        "session); verify epoch CURRENT; verify G2 still owns the writer; "
        "verify observed provider_session_id equals already-bound S1 (refuse "
        "rebind / new session / NULL); record G2 process identity "
        "(pid/pgid/start/boot); append OPERATOR_OPERATION_APPLIED. Must not "
        "mutate epoch.provider_session_id. Must not create a SessionEpoch. "
        "Must not consume an Attempt. First bind of a NULL epoch session is "
        "TX-3 only. INTENT for G3, another epoch, another session, "
        "start_session, or another Attempt is INTENT_TARGET_MISMATCH."
    ),
}


CRASH_WINDOW_MATRIX: dict[str, dict[str, str]] = {
    "after_tx2_before_adapter_call": {
        "durable_state": "INTENT committed; CURRENT epoch; pre-bind writer held; provider_session_id NULL",
        "external_side_effect": "none if Executive can prove the adapter was never entered",
        "safe_automatic_retry": "only if local execution state proves the adapter call did not begin",
        "required_reconciliation": "inspect local call-start flag; otherwise EFFECT_UNKNOWN",
        "writer_held": "yes, pre-bind epoch writer",
        "epoch_may_be_abandoned": "no while process liveness is UNKNOWN",
        "new_epoch_may_start": "no",
    },
    "during_process_launch": {
        "durable_state": "INTENT committed; writer held; provider_session_id NULL",
        "external_side_effect": "possible local process",
        "safe_automatic_retry": "no",
        "required_reconciliation": "prove process absence or treat EFFECT_UNKNOWN",
        "writer_held": "yes",
        "epoch_may_be_abandoned": "only after process PROVEN_DEAD or slot reset",
        "new_epoch_may_start": "no while process liveness UNKNOWN",
    },
    "provider_created_s1_before_response": {
        "durable_state": "INTENT committed; provider_session_id still NULL",
        "external_side_effect": "possible S1",
        "safe_automatic_retry": "no unless provider-native idempotency is advertised",
        "required_reconciliation": "EFFECT_UNKNOWN; do not issue a second create",
        "writer_held": "yes",
        "epoch_may_be_abandoned": "not while process liveness UNKNOWN",
        "new_epoch_may_start": "no",
    },
    "after_s1_response_before_tx3": {
        "durable_state": "INTENT committed; S1 known only in adapter memory",
        "external_side_effect": "S1 exists",
        "safe_automatic_retry": "no",
        "required_reconciliation": "bind S1 in TX-3 if still obtainable; else EFFECT_UNKNOWN",
        "writer_held": "yes",
        "epoch_may_be_abandoned": "not while process may still be alive",
        "new_epoch_may_start": "no",
    },
    "after_tx3_before_attestation": {
        "durable_state": "S1 bound; process identity recorded; APPLIED",
        "external_side_effect": "yes, already bound",
        "safe_automatic_retry": "n/a — start already applied",
        "required_reconciliation": "collect attestation; LaunchDecision still pending",
        "writer_held": "yes",
        "epoch_may_be_abandoned": "only after later hard-fail law",
        "new_epoch_may_start": "no",
    },
    "after_attestation_before_turn": {
        "durable_state": "attestation sealed; LaunchDecision derived",
        "external_side_effect": "session exists; no work turn yet",
        "safe_automatic_retry": "n/a for start; turn not issued",
        "required_reconciliation": "ALLOW may begin TX-5; REFUSE reconciles/terminates",
        "writer_held": "yes",
        "epoch_may_be_abandoned": "if REFUSE and process proven dead/stopped",
        "new_epoch_may_start": "only after lawful abandon or rotation",
    },
    "provider_accepted_turn_before_applied": {
        "durable_state": "BEGIN_TURN INTENT committed; APPLIED absent",
        "external_side_effect": "possible in-flight turn",
        "safe_automatic_retry": "no",
        "required_reconciliation": "EFFECT_UNKNOWN; do not reissue the same turn OperationId",
        "writer_held": "yes",
        "epoch_may_be_abandoned": "no solely from missing APPLIED",
        "new_epoch_may_start": "no",
    },
    "graceful_stop_succeeded_before_tx6": {
        "durable_state": "provider may have RELEASED; Executive writer still held",
        "external_side_effect": "graceful stop may have completed",
        "safe_automatic_retry": "observe, then commit TX-6; do not invent RELEASED",
        "required_reconciliation": "re-observe provider writer; then TX-6",
        "writer_held": "yes until TX-6",
        "epoch_may_be_abandoned": "no; this is graceful replacement",
        "new_epoch_may_start": "no",
    },
    "sigkill_before_tx7": {
        "durable_state": "generation still looks live in SQLite",
        "external_side_effect": "process may already be dead",
        "safe_automatic_retry": "n/a",
        "required_reconciliation": "observe death; TX-7 records death without clearing writer",
        "writer_held": "yes",
        "epoch_may_be_abandoned": "only after TX-7 and PROVEN_DEAD plus recovery policy",
        "new_epoch_may_start": "not until TX-8 if abandoning",
    },
    "tx8_committed_e2_not_created": {
        "durable_state": "Attempt active; no CURRENT epoch; no Executive writer",
        "external_side_effect": "none for E2",
        "safe_automatic_retry": "yes — create E2 via a new TX-2 INTENT",
        "required_reconciliation": "none beyond verifying abandon committed",
        "writer_held": "no",
        "epoch_may_be_abandoned": "already abandoned",
        "new_epoch_may_start": "yes if placement still lawful and process PROVEN_DEAD",
    },
    "restore_completed_before_tx9": {
        "durable_state": "SQLite may still say CURRENT/held",
        "external_side_effect": "external processes/sessions are not restored",
        "safe_automatic_retry": "n/a — execution remains disabled until TX-9",
        "required_reconciliation": "TX-9 must run before any worker is re-enabled",
        "writer_held": "historical row may still say 1 until TX-9",
        "epoch_may_be_abandoned": "must, in TX-9",
        "new_epoch_may_start": "no; Attempt becomes LOST",
    },
    "controller_dies_during_tx9": {
        "durable_state": "partial invalidation possible across Attempts",
        "external_side_effect": "none of Executive authority is live",
        "safe_automatic_retry": "replay TX-9 remaining Attempts; services stay disabled",
        "required_reconciliation": "complete TX-9 for every OPERATOR_HARNESS Attempt",
        "writer_held": "must be cleared before re-enable",
        "epoch_may_be_abandoned": "yes, remaining CURRENT epochs",
        "new_epoch_may_start": "no",
    },
    "after_tx10_before_resume_call": {
        "durable_state": (
            "resume INTENT committed; G1 writer released; G2 writer held on the "
            "same CURRENT epoch; provider_session_id already S1; G2 process not launched"
        ),
        "external_side_effect": "none if Executive can prove resume_session was never entered",
        "safe_automatic_retry": (
            "only the same OperationId against already-allocated G2, and only if "
            "local execution state proves the adapter call did not begin; never allocate G3"
        ),
        "required_reconciliation": (
            "inspect local call-start flag; proven-not-started → "
            "RETRY_SAME_OPERATION_ON_ALLOCATED_GENERATION; otherwise "
            "EFFECT_UNKNOWN_HOLD_GENERATION"
        ),
        "writer_held": "yes, G2 post-bind epoch+realm writer",
        "epoch_may_be_abandoned": "no while G2 process liveness is UNKNOWN",
        "new_epoch_may_start": "no",
    },
    "during_resume_session": {
        "durable_state": "TX-10 committed; G2 writer held; S1 bound; APPLIED absent",
        "external_side_effect": "possible new OS process attached to existing S1",
        "safe_automatic_retry": "no",
        "required_reconciliation": "EFFECT_UNKNOWN; do not allocate G3; do not create a new epoch",
        "writer_held": "yes, G2",
        "epoch_may_be_abandoned": "not while G2 process liveness is UNKNOWN",
        "new_epoch_may_start": "no",
    },
    "resume_returned_before_applied": {
        "durable_state": "TX-10 committed; resume observation only in adapter memory; TX-11 not committed",
        "external_side_effect": "G2 process and S1 resume likely exist",
        "safe_automatic_retry": "no",
        "required_reconciliation": (
            "TX-11 persist G2 process identity + APPLIED if the observation is "
            "still obtainable and observed session equals bound S1; else EFFECT_UNKNOWN"
        ),
        "writer_held": "yes, G2",
        "epoch_may_be_abandoned": "not while G2 process may still be alive",
        "new_epoch_may_start": "no",
    },
    "after_tx11_applied": {
        "durable_state": (
            "resume APPLIED; G2 process identity recorded; epoch.provider_session_id "
            "still S1; G2 writer held"
        ),
        "external_side_effect": "yes, already bound to S1 on G2",
        "safe_automatic_retry": "n/a — resume already applied; matching TX-11 replay is a no-op",
        "required_reconciliation": "collect attestation (new_process_generation); LaunchDecision still pending",
        "writer_held": "yes, G2",
        "epoch_may_be_abandoned": "only after later hard-fail law",
        "new_epoch_may_start": "no",
    },
    "observed_session_mismatch_refuses_tx11": {
        "durable_state": "TX-10 committed; bound S1 unchanged; APPLIED absent",
        "external_side_effect": "possible foreign session or missing session",
        "safe_automatic_retry": "no — do not rebind epoch.provider_session_id; do not allocate G3",
        "required_reconciliation": "PROVIDER_SESSION_MISMATCH; EFFECT_UNKNOWN on the resume OperationId; hold G2",
        "writer_held": "yes, G2",
        "epoch_may_be_abandoned": "not while G2 process liveness is UNKNOWN",
        "new_epoch_may_start": "no",
    },
    "incomplete_process_identity_refuses_tx11": {
        "durable_state": "TX-10 committed; S1 bound; APPLIED absent; G2 process identity unset",
        "external_side_effect": "possible G2 process",
        "safe_automatic_retry": "no",
        "required_reconciliation": (
            "PROCESS_IDENTITY_INCOMPLETE; EFFECT_UNKNOWN; hold G2; do not invent "
            "pid/boot; zero/negative pid/pgid and blank/whitespace start/boot refuse"
        ),
        "writer_held": "yes, G2",
        "epoch_may_be_abandoned": "not while G2 process may still be alive",
        "new_epoch_may_start": "no",
    },
    "intent_target_mismatch_refuses_tx11": {
        "durable_state": "TX-10 G2 INTENT committed for OperationId A; APPLIED absent",
        "external_side_effect": "possible G2 resume of S1",
        "safe_automatic_retry": "no — do not apply a different OperationId onto G2",
        "required_reconciliation": (
            "INTENT_TARGET_MISMATCH when the Event-plane INTENT payload does not "
            "bind this OperationId to resume_session + this attempt + this epoch "
            "+ this generation + this worker + already-bound S1"
        ),
        "writer_held": "yes, G2",
        "epoch_may_be_abandoned": "not while G2 process liveness is UNKNOWN",
        "new_epoch_may_start": "no",
    },
    "duplicate_tx11_matching_observation": {
        "durable_state": "TX-11 already APPLIED; G2 process identity already recorded",
        "external_side_effect": "none from the duplicate persist",
        "safe_automatic_retry": "yes as a no-op if observed session and process identity match the sealed row",
        "required_reconciliation": "matching observation is identity; mismatch is ALREADY_APPLIED_CONFLICT",
        "writer_held": "yes, G2",
        "epoch_may_be_abandoned": "no",
        "new_epoch_may_start": "no",
    },
    "duplicate_tx10_while_successor_holds": {
        "durable_state": "G2 already holds the epoch and realm writer; OperationId may already be reserved",
        "external_side_effect": "none from the duplicate",
        "safe_automatic_retry": "no — unique writer index and unique command_id refuse before any provider call",
        "required_reconciliation": "SUCCESSOR_WRITER_CONFLICT and/or OPERATION_ID_DUPLICATE; no adapter call",
        "writer_held": "yes, the already-allocated successor",
        "epoch_may_be_abandoned": "no",
        "new_epoch_may_start": "no",
    },
    "hard_dead_g1_provider_held_or_unknown": {
        "durable_state": "TX-7 death recorded; Executive writer still held on G1; provider not RELEASED",
        "external_side_effect": "none from a refused TX-10",
        "safe_automatic_retry": "no — TX-10 is refused; do not invent RELEASED",
        "required_reconciliation": "no G2; TX-8 abandon+new epoch remains the S2 path if process is PROVEN_DEAD",
        "writer_held": "yes, G1",
        "epoch_may_be_abandoned": "yes via TX-8 only, not via TX-10",
        "new_epoch_may_start": "only after TX-8, never as G2 on S1",
    },
    "unknown_process_blocks_tx10": {
        "durable_state": "CURRENT epoch; G1 writer held; process liveness UNKNOWN",
        "external_side_effect": "possible live G1 process",
        "safe_automatic_retry": "no",
        "required_reconciliation": "TX-10 refused; no G2; no new epoch; Attempt LOST if recovery cannot prove absence",
        "writer_held": "yes, G1",
        "epoch_may_be_abandoned": "no while process liveness is UNKNOWN",
        "new_epoch_may_start": "no",
    },
}


INVARIANT_ENFORCEMENT: dict[str, EnforcementSite] = {
    "unique_attempt_epoch_number": EnforcementSite.SQL_INDEX,
    "one_current_epoch": EnforcementSite.SQL_INDEX,
    "prebind_epoch_writer": EnforcementSite.SQL_INDEX,
    "postbind_realm_writer": EnforcementSite.SQL_INDEX,
    "epoch_session_realm": EnforcementSite.SQL_INDEX,
    "provider_session_id_immutable_once_bound": EnforcementSite.SQL_TRIGGER,
    "abandoned_or_terminal_cannot_become_current": EnforcementSite.SQL_TRIGGER,
    "epoch_worker_matches_attempt": EnforcementSite.BEGIN_IMMEDIATE,
    "generation_worker_matches_attempt": EnforcementSite.BEGIN_IMMEDIATE,
    "generation_session_matches_epoch_once_bound": EnforcementSite.BEGIN_IMMEDIATE,
    "execution_mode_immutable": EnforcementSite.SQL_TRIGGER,
    "legacy_attempt_fields_not_rewritten_for_ohf": EnforcementSite.BEGIN_IMMEDIATE,
    "launch_decision": EnforcementSite.PURE_COMPARATOR,
    "resume_safety": EnforcementSite.PURE_COMPARATOR,
    "unknown_process_blocks_new_writer": EnforcementSite.SUPERVISOR,
    "restore_invalidation_before_reenable": EnforcementSite.BEGIN_IMMEDIATE,
    "same_epoch_generation_recovery": EnforcementSite.BEGIN_IMMEDIATE,
    "resume_provider_session_handoff": EnforcementSite.PURE_COMPARATOR,
    "resume_bind_process_identity": EnforcementSite.BEGIN_IMMEDIATE,
    "operation_intent_target": EnforcementSite.BEGIN_IMMEDIATE,
    "process_identity_positive_nonblank": EnforcementSite.SQL_TRIGGER,
}


@dataclass(frozen=True)
class OperationId:
    """Durable Executive intent key.  Equals events.command_id of INTENT."""

    command_id: str

    def __post_init__(self) -> None:
        value = str(self.command_id or "")
        if not value.startswith(OPERATION_COMMAND_ID_PREFIX):
            raise ValueError("OperationId must use the ohf-op: command_id prefix")
        if COMMAND_ID_RE.fullmatch(value) is None:
            raise ValueError("OperationId.command_id must match events.command_id law")
        if not operation_id_permits_all_derived_receipts(value):
            raise ValueError(
                "OperationId.command_id must leave room for every derived receipt "
                "command_id under events.command_id law"
            )


@dataclass(frozen=True)
class OperationIntentTarget:
    """Durable Event-plane INTENT payload.  No sidecar table.

    Binds ``events.command_id`` (the OperationId) to the exact state
    transition it authorized.  Canonical JSON keys are
    ``OPERATION_INTENT_TARGET_FIELDS``.  Event columns ``attempt_id`` and
    ``worker_id`` must equal the payload fields of the same name.
    """

    operation_kind: OperationKind
    attempt_id: str
    session_epoch_id: str
    process_generation_id: str
    worker_id: str
    provider_session_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.operation_kind, OperationKind):
            raise ValueError("OperationIntentTarget.operation_kind is required")
        for name in (
            "attempt_id",
            "session_epoch_id",
            "process_generation_id",
            "worker_id",
            "provider_session_id",
        ):
            raw = getattr(self, name)
            value = str(raw or "").strip()
            if not value:
                raise ValueError(f"OperationIntentTarget.{name} is required")
            if raw != value:
                raise ValueError(f"OperationIntentTarget.{name} must be trimmed")

    def to_event_payload(self) -> dict[str, str]:
        return {
            "operation_kind": self.operation_kind.value,
            "attempt_id": self.attempt_id,
            "session_epoch_id": self.session_epoch_id,
            "process_generation_id": self.process_generation_id,
            "worker_id": self.worker_id,
            "provider_session_id": self.provider_session_id,
        }


@dataclass(frozen=True)
class OperationIntentReceipt:
    """Existing Event-plane INTENT row.  aggregate_id = command_id = OperationId."""

    operation_id: OperationId
    target: OperationIntentTarget
    aggregate_type: str = OPERATION_AGGREGATE_TYPE

    def __post_init__(self) -> None:
        if self.aggregate_type != OPERATION_AGGREGATE_TYPE:
            raise ValueError("Operation INTENT stays on the operator_operation Event plane")

    @property
    def aggregate_id(self) -> str:
        return self.operation_id.command_id

    @property
    def command_id(self) -> str:
        return self.operation_id.command_id

    @property
    def event_type(self) -> str:
        return OperationReceiptKind.INTENT.value

    @property
    def attempt_id(self) -> str:
        return self.target.attempt_id

    @property
    def worker_id(self) -> str:
        return self.target.worker_id


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
    """Requested capability identity at the strongest truthful precision."""

    name: str
    harness_binary_digest: str
    kind: str = "skill"
    skill_content_digest: str | None = None
    tool_schema_digest: str | None = None
    mcp_server_identity: str | None = None
    mcp_server_version: str | None = None
    mcp_auth_status: str | None = None


@dataclass(frozen=True)
class ObservedCapabilityIdentity:
    """Adapter-observed capability identity.  Missing digests stay None."""

    kind: str
    name: str
    skill_content_digest: str | None = None
    tool_schema_digest: str | None = None
    mcp_server_identity: str | None = None
    mcp_server_version: str | None = None
    mcp_auth_status: str | None = None


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
    auth_realm_requirement: AuthRealmRequirement = AuthRealmRequirement.SLOT_BOUND_V1
    expected_provider_account_id: str | None = None
    expected_config_digest: str | None = None
    allowed_write_paths: tuple[str, ...] = ()
    write_capable: bool = False


@dataclass(frozen=True)
class ObservedHarnessAttestation:
    """Collected after initialize, sealed before the first work turn."""

    served_model: str | None
    harness_version: str | None
    harness_binary_digest: str | None
    capabilities: tuple[ObservedCapabilityIdentity, ...]
    effective_skills: tuple[str, ...]
    effective_mcp: tuple[str, ...]
    effective_plugins_or_apps: tuple[str, ...]
    sandbox_state: str | None
    approval_state: str | None
    network_state: str | None
    effective_config_digest: str | None
    auth: AuthRealmFact
    workspace: WorkspaceIdentity | None
    supports_subagent_capability_ceiling: ObservedTriState = ObservedTriState.UNKNOWN
    unknown_fields: tuple[str, ...] = ()


@dataclass(frozen=True)
class SessionEpochRef:
    """Executive-allocated epoch identity.  Does not require a provider session."""

    session_epoch_id: str
    attempt_id: str
    worker_id: str
    epoch_number: int


@dataclass(frozen=True)
class ProcessGenerationRef:
    """Executive-allocated generation identity.  OS identity is observed later."""

    process_generation_id: str
    session_epoch_id: str
    generation_number: int
    worker_id: str


@dataclass(frozen=True)
class ProcessIdentityObservation:
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
    """Reconnect cursor scoped to one ProcessGeneration.  Not a second store."""

    attempt_id: str
    session_epoch_id: str
    process_generation_id: str
    local_sequence: int = 0
    turn_id: str | None = None
    provider_replay_cursor: str | None = None


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
class ReconcileObservation:
    """Adapter-owned observations only.  Supervisor derives authority."""

    process_liveness: ProcessLiveness
    observed_process: ProcessIdentityObservation
    provider_session_reachable: bool | None
    provider_writer_state: ProviderWriterState
    observed_provider_session_id: str | None = None
    observed_config_digest: str | None = None
    recommended_failure_class: AdapterFailureClass | None = None


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
class SessionStartObservation:
    provider_session_id: str | None
    process: ProcessIdentityObservation
    provider_operation_ref: str | None = None
    initialization_notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class ProviderSessionHandoff:
    """Already-bound epoch session identity.  Executive passes this INTO resume_session.

    Not an Executive-allocated ID.  Not adapter-minted on the resume call.
    Must equal ``harness_session_epochs.provider_session_id`` and the
    generation index projection.  Empty values are refused.
    """

    provider_session_id: str
    worker_id: str

    def __post_init__(self) -> None:
        if not str(self.provider_session_id or "").strip():
            raise ValueError("ProviderSessionHandoff.provider_session_id is required")
        if not str(self.worker_id or "").strip():
            raise ValueError("ProviderSessionHandoff.worker_id is required")


@dataclass(frozen=True)
class TurnStartObservation:
    provider_native_turn_id: str | None = None
    acknowledged: bool = False


@dataclass(frozen=True)
class NativeForkObservation:
    provider_native_fork_id: str
    parent_session_epoch_id: str
    parent_process_generation_id: str


@dataclass(frozen=True)
class CheckpointObservation:
    checkpoint_candidate: Mapping[str, object]
    provider_mutated_state: bool = True


@dataclass(frozen=True)
class LaunchComparison:
    requested: RequestedExecutionProfile
    observed: ObservedHarnessAttestation
    decision: LaunchDecision
    mismatch_reasons: tuple[str, ...] = ()
    missing_required: tuple[str, ...] = ()
    forbidden_present: tuple[str, ...] = ()
    unclassified: tuple[str, ...] = ()
    unknown_required_observations: tuple[str, ...] = ()


@dataclass(frozen=True)
class WriterFacts:
    process_liveness: ProcessLiveness
    executive_writer_held: bool
    provider_writer_state: ProviderWriterState


@dataclass(frozen=True)
class RestoreInvalidationResult:
    historical_provider_writer_state: ProviderWriterState
    historical_process_liveness: ProcessLiveness
    clear_executive_writer: bool = True
    abandon_epoch: bool = True
    attempt_status: str = POST_RESTORE_ATTEMPT_STATUS


@dataclass(frozen=True)
class ProcessGenerationRecord:
    """Pure in-memory generation row for TX-10 architecture proofs.  Not SQLite."""

    ref: ProcessGenerationRef
    executive_writer_held: bool
    process_liveness: ProcessLiveness
    provider_writer_state: ProviderWriterState
    provider_session_id: str | None = None


@dataclass(frozen=True)
class SameEpochRecoverySnapshot:
    """Pre/post TX-10 durable facts.  Attempt identity is unchanged by construction."""

    epoch: SessionEpochRef
    epoch_state: SessionEpochState
    provider_session_id: str
    generations: tuple[ProcessGenerationRecord, ...]
    reserved_operation_ids: frozenset[str] = frozenset()
    intent_receipts: tuple[OperationIntentReceipt, ...] = ()
    creates_new_epoch: bool = False
    consumes_attempt: bool = False


@dataclass(frozen=True)
class ResumeBindSnapshot:
    """Pre/post TX-11 durable facts.  Epoch session identity is already bound."""

    epoch: SessionEpochRef
    epoch_state: SessionEpochState
    bound_provider_session_id: str
    generation: ProcessGenerationRecord
    operation_id: OperationId
    intent_receipt: OperationIntentReceipt | None
    applied: bool = False
    process: ProcessIdentityObservation | None = None
    creates_new_epoch: bool = False
    consumes_attempt: bool = False
    epoch_provider_session_mutated: bool = False


@dataclass(frozen=True)
class HarnessAdapterCapabilities:
    interface_version: str
    supported_required_operations: tuple[str, ...]
    supported_optional_operations: tuple[str, ...]
    supports_native_resume: bool
    supports_native_fork: bool
    supports_steering: bool
    supports_approval_response: bool
    supports_checkpoint: bool
    supports_config_staging: bool
    supports_subagent_capability_ceiling: bool
    supports_structured_events: bool
    supports_provider_native_idempotency: bool = False
    provider_capability_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class MethodContract:
    name: str
    classification: MethodClass
    timeout_seconds: float | None
    idempotency: OperationIdempotencyClass
    requires_operation_id: bool
    cancellation: str
    allowed_side_effects: tuple[str, ...]
    forbidden_side_effects: tuple[str, ...]
    failure_classes: tuple[AdapterFailureClass, ...]
    notes: str


def _contract(
    *,
    name: str,
    classification: MethodClass,
    timeout_seconds: float | None,
    idempotency: OperationIdempotencyClass,
    requires_operation_id: bool,
    cancellation: str,
    allowed_side_effects: tuple[str, ...],
    forbidden_side_effects: tuple[str, ...],
    failure_classes: tuple[AdapterFailureClass, ...],
    notes: str,
) -> MethodContract:
    return MethodContract(
        name=name,
        classification=classification,
        timeout_seconds=timeout_seconds,
        idempotency=idempotency,
        requires_operation_id=requires_operation_id,
        cancellation=cancellation,
        allowed_side_effects=allowed_side_effects,
        forbidden_side_effects=forbidden_side_effects,
        failure_classes=failure_classes,
        notes=notes,
    )


METHOD_CONTRACTS: dict[str, MethodContract] = {
    "describe_capabilities": _contract(
        name="describe_capabilities",
        classification=MethodClass.COMMON_REQUIRED,
        timeout_seconds=15.0,
        idempotency=OperationIdempotencyClass.PURE_IDEMPOTENT,
        requires_operation_id=False,
        cancellation="abort the describe call; no session created",
        allowed_side_effects=("read non-secret capability metadata",),
        forbidden_side_effects=(
            "start process",
            "read credentials",
            "mutate workspace",
            "mutate Executive lifecycle",
        ),
        failure_classes=(AdapterFailureClass.CONFIG_DRIFT,),
        notes="Returns HarnessAdapterCapabilities. Pure capability negotiation.",
    ),
    "validate_requested_profile": _contract(
        name="validate_requested_profile",
        classification=MethodClass.COMMON_REQUIRED,
        timeout_seconds=15.0,
        idempotency=OperationIdempotencyClass.PURE_IDEMPOTENT,
        requires_operation_id=False,
        cancellation="abort validation; no durable effect",
        allowed_side_effects=("pure validation",),
        forbidden_side_effects=(
            "start process",
            "perform inference",
            "read credential bytes",
            "change credentials",
            "mutate authoritative workspace",
            "mutate Executive lifecycle",
            "perform launch attestation",
        ),
        failure_classes=(
            AdapterFailureClass.CAPABILITY_ATTESTATION_FAILURE,
            AdapterFailureClass.WORKSPACE_MISMATCH,
            AdapterFailureClass.CONFIG_DRIFT,
        ),
        notes="Static preflight only. Does not replace observed compare_launch.",
    ),
    "stage_operator_config": _contract(
        name="stage_operator_config",
        classification=MethodClass.COMMON_OPTIONAL,
        timeout_seconds=30.0,
        idempotency=OperationIdempotencyClass.NON_REPLAYABLE_ON_UNKNOWN_EFFECT,
        requires_operation_id=True,
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
        notes="INTENT before write. Staging only; supervisor owns lifecycle.",
    ),
    "start_session": _contract(
        name="start_session",
        classification=MethodClass.COMMON_REQUIRED,
        timeout_seconds=60.0,
        idempotency=OperationIdempotencyClass.NON_REPLAYABLE_ON_UNKNOWN_EFFECT,
        requires_operation_id=True,
        cancellation="do not leave an untracked provider session; report SESSION_MISSING if unknown",
        allowed_side_effects=(
            "launch one ProcessGeneration already allocated by Executive",
            "create one primary provider session for the preallocated epoch",
        ),
        forbidden_side_effects=(
            "complete_job",
            "allocate session_epoch_id",
            "allocate process_generation_id",
            "persist Executive lifecycle",
            "declare LaunchDecision",
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
        notes="Receives preallocated SessionEpochRef+ProcessGenerationRef. Returns observation only.",
    ),
    "begin_turn": _contract(
        name="begin_turn",
        classification=MethodClass.COMMON_REQUIRED,
        timeout_seconds=30.0,
        idempotency=OperationIdempotencyClass.NON_REPLAYABLE_ON_UNKNOWN_EFFECT,
        requires_operation_id=True,
        cancellation="turn must not start if cancelled before provider ack",
        allowed_side_effects=("start one model turn after ALLOW LaunchDecision",),
        forbidden_side_effects=(
            "work before attestation ALLOW",
            "complete_job",
            "allocate turn_id",
        ),
        failure_classes=(
            AdapterFailureClass.CAPABILITY_ATTESTATION_FAILURE,
            AdapterFailureClass.SESSION_MISSING,
            AdapterFailureClass.ACTIVE_WRITER_CONFLICT,
            AdapterFailureClass.HUMAN_APPROVAL_REQUIRED,
        ),
        notes="Receives preallocated TurnRef. Missing APPLIED ⇒ EFFECT_UNKNOWN, no reissue.",
    ),
    "read_events": _contract(
        name="read_events",
        classification=MethodClass.COMMON_REQUIRED,
        timeout_seconds=30.0,
        idempotency=OperationIdempotencyClass.PURE_IDEMPOTENT,
        requires_operation_id=False,
        cancellation="return events collected so far plus cursor; no rewind implied",
        allowed_side_effects=("read provider event stream",),
        forbidden_side_effects=("persist raw unredacted secrets", "create Executive event store"),
        failure_classes=(
            AdapterFailureClass.SESSION_MISSING,
            AdapterFailureClass.PROCESS_CRASH,
            AdapterFailureClass.MCP_OR_TOOL_TRANSPORT_FAILURE,
        ),
        notes="EventCursor is scoped to one ProcessGeneration. No cross-generation replay promise.",
    ),
    "interrupt_turn": _contract(
        name="interrupt_turn",
        classification=MethodClass.COMMON_REQUIRED,
        timeout_seconds=30.0,
        idempotency=OperationIdempotencyClass.NON_REPLAYABLE_ON_UNKNOWN_EFFECT,
        requires_operation_id=True,
        cancellation="already an interrupt; repeated calls are no-ops after terminal turn",
        allowed_side_effects=("request in-flight turn stop",),
        forbidden_side_effects=("kill unrelated processes", "complete_job", "release writer falsely"),
        failure_classes=(
            AdapterFailureClass.SESSION_MISSING,
            AdapterFailureClass.PROCESS_CRASH,
        ),
        notes="Does not mark Attempt LOST. Supervisor decides.",
    ),
    "collect_candidate_result": _contract(
        name="collect_candidate_result",
        classification=MethodClass.COMMON_REQUIRED,
        timeout_seconds=60.0,
        idempotency=OperationIdempotencyClass.PURE_IDEMPOTENT,
        requires_operation_id=False,
        cancellation="return incomplete candidate or VALIDATION_FAILURE; never complete_job",
        allowed_side_effects=("read proposed artifacts",),
        forbidden_side_effects=("complete_job", "validate as Executive", "grant review"),
        failure_classes=(
            AdapterFailureClass.MODEL_OR_WORK_RESULT_FAILURE,
            AdapterFailureClass.VALIDATION_FAILURE,
        ),
        notes="CandidateResult.complete_job_permitted is always false.",
    ),
    "graceful_stop": _contract(
        name="graceful_stop",
        classification=MethodClass.COMMON_REQUIRED,
        timeout_seconds=60.0,
        idempotency=OperationIdempotencyClass.NON_REPLAYABLE_ON_UNKNOWN_EFFECT,
        requires_operation_id=True,
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
    "cancel": _contract(
        name="cancel",
        classification=MethodClass.COMMON_REQUIRED,
        timeout_seconds=60.0,
        idempotency=OperationIdempotencyClass.NON_REPLAYABLE_ON_UNKNOWN_EFFECT,
        requires_operation_id=True,
        cancellation="this is the cancel path; repeats are no-ops after terminal receipt",
        allowed_side_effects=("stop turn and request process exit",),
        forbidden_side_effects=("complete_job", "writer steal", "mutate other Attempts"),
        failure_classes=(
            AdapterFailureClass.PROCESS_CRASH,
            AdapterFailureClass.ACTIVE_WRITER_CONFLICT,
        ),
        notes="Executive still owns Attempt status transition.",
    ),
    "reconcile": _contract(
        name="reconcile",
        classification=MethodClass.COMMON_REQUIRED,
        timeout_seconds=30.0,
        idempotency=OperationIdempotencyClass.PURE_IDEMPOTENT,
        requires_operation_id=False,
        cancellation="return partial ReconcileObservation; no lifecycle mutation",
        allowed_side_effects=("inspect process table", "ask provider session reachability"),
        forbidden_side_effects=(
            "kill",
            "resume",
            "mark Attempt LOST",
            "start Attempt",
            "select provider",
            "release quota",
            "complete_job",
            "assert executive_writer_held",
            "assert resume_safe",
        ),
        failure_classes=(
            AdapterFailureClass.PROCESS_CRASH,
            AdapterFailureClass.SESSION_MISSING,
            AdapterFailureClass.ACTIVE_WRITER_CONFLICT,
            AdapterFailureClass.WORKSPACE_MISMATCH,
            AdapterFailureClass.CONFIG_DRIFT,
        ),
        notes="Observational only. ReconcileObservation forbids Executive judgments.",
    ),
    "probe": _contract(
        name="probe",
        classification=MethodClass.COMMON_OPTIONAL,
        timeout_seconds=30.0,
        idempotency=OperationIdempotencyClass.NON_REPLAYABLE_ON_UNKNOWN_EFFECT,
        requires_operation_id=True,
        cancellation="abort probe; no session retained",
        allowed_side_effects=("laboratory/read-only capability probe",),
        forbidden_side_effects=("production worker activation", "write-capable work"),
        failure_classes=(AdapterFailureClass.AUTH_FAILURE, AdapterFailureClass.CONFIG_DRIFT),
        notes="P0-style inert probe. OperationId required because a probe process may start.",
    ),
    "resume_session": _contract(
        name="resume_session",
        classification=MethodClass.COMMON_OPTIONAL,
        timeout_seconds=60.0,
        idempotency=OperationIdempotencyClass.NON_REPLAYABLE_ON_UNKNOWN_EFFECT,
        requires_operation_id=True,
        cancellation="do not attach a second writer; report ACTIVE_WRITER_CONFLICT if unsure",
        allowed_side_effects=(
            "start a NEW ProcessGeneration that resumes an existing provider_session_id",
        ),
        forbidden_side_effects=(
            "adopt old stdio",
            "resume an ABANDONED epoch",
            "cross Attempt resume",
            "free writer because process is dead",
            "allocate process_generation_id",
            "allocate session_epoch_id",
            "allocate provider_session_id",
            "create a new provider session",
            "rebind epoch.provider_session_id",
        ),
        failure_classes=(
            AdapterFailureClass.ACTIVE_WRITER_CONFLICT,
            AdapterFailureClass.SESSION_MISSING,
            AdapterFailureClass.PROCESS_CRASH,
            AdapterFailureClass.CAPABILITY_ATTESTATION_FAILURE,
        ),
        notes=(
            "Executive passes already-bound S1 as ProviderSessionHandoff. "
            "Adapter must not mint a session. Observed provider_session_id must "
            "equal the handoff. G2 process identity and APPLIED are TX-11. "
            "Requires Executive-derived resume_safe at TX-10. Adapters without "
            "native resume remain valid."
        ),
    ),
    "send_input": _contract(
        name="send_input",
        classification=MethodClass.COMMON_OPTIONAL,
        timeout_seconds=15.0,
        idempotency=OperationIdempotencyClass.NON_REPLAYABLE_ON_UNKNOWN_EFFECT,
        requires_operation_id=True,
        cancellation="drop unacked input",
        allowed_side_effects=("steer in-flight turn",),
        forbidden_side_effects=("start a new session", "complete_job"),
        failure_classes=(AdapterFailureClass.SESSION_MISSING,),
        notes="Capability-negotiated steering.",
    ),
    "respond_to_approval": _contract(
        name="respond_to_approval",
        classification=MethodClass.COMMON_OPTIONAL,
        timeout_seconds=30.0,
        idempotency=OperationIdempotencyClass.NON_REPLAYABLE_ON_UNKNOWN_EFFECT,
        requires_operation_id=True,
        cancellation="leave approval pending",
        allowed_side_effects=("submit human approval decision",),
        forbidden_side_effects=("auto-approve by adapter policy",),
        failure_classes=(AdapterFailureClass.HUMAN_APPROVAL_REQUIRED,),
        notes="Human/supervisor decision, not model self-approval.",
    ),
    "fork_session": _contract(
        name="fork_session",
        classification=MethodClass.COMMON_OPTIONAL,
        timeout_seconds=60.0,
        idempotency=OperationIdempotencyClass.NON_REPLAYABLE_ON_UNKNOWN_EFFECT,
        requires_operation_id=True,
        cancellation="do not leave an untracked fork",
        allowed_side_effects=("create subordinate native handle inside current epoch",),
        forbidden_side_effects=(
            "create Executive child Job",
            "consume primary epoch counter",
            "claim independent review",
            "allocate session_epoch_id",
            "enable helpers on write-capable Attempts without ceiling",
        ),
        failure_classes=(
            AdapterFailureClass.CAPABILITY_ATTESTATION_FAILURE,
            AdapterFailureClass.SESSION_MISSING,
        ),
        notes="Returns NativeForkObservation. Not a session epoch. No v3 fork table.",
    ),
    "checkpoint": _contract(
        name="checkpoint",
        classification=MethodClass.COMMON_OPTIONAL,
        timeout_seconds=30.0,
        idempotency=OperationIdempotencyClass.NON_REPLAYABLE_ON_UNKNOWN_EFFECT,
        requires_operation_id=True,
        cancellation="omit checkpoint; last trusted checkpoint remains",
        allowed_side_effects=("emit checkpoint candidate for Executive to persist", "provider compaction"),
        forbidden_side_effects=("write Executive checkpoint_json directly",),
        failure_classes=(AdapterFailureClass.MODEL_OR_WORK_RESULT_FAILURE,),
        notes="V1 treats checkpoint as provider-state-changing. Executive persists checkpoint_json.",
    ),
    "prepare": _contract(
        name="prepare",
        classification=MethodClass.REJECTED,
        timeout_seconds=None,
        idempotency=OperationIdempotencyClass.PURE_IDEMPOTENT,
        requires_operation_id=False,
        cancellation="n/a",
        allowed_side_effects=(),
        forbidden_side_effects=("kitchen-sink prepare",),
        failure_classes=(),
        notes="Removed. Use validate_requested_profile + optional stage_operator_config.",
    ),
    "complete_job": _contract(
        name="complete_job",
        classification=MethodClass.REJECTED,
        timeout_seconds=None,
        idempotency=OperationIdempotencyClass.PURE_IDEMPOTENT,
        requires_operation_id=False,
        cancellation="n/a",
        allowed_side_effects=(),
        forbidden_side_effects=("complete_job",),
        failure_classes=(),
        notes="Executive runtime only.",
    ),
    "signal_process": _contract(
        name="signal_process",
        classification=MethodClass.SUPERVISOR_RUNTIME,
        timeout_seconds=15.0,
        idempotency=OperationIdempotencyClass.NON_REPLAYABLE_ON_UNKNOWN_EFFECT,
        requires_operation_id=True,
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

    def describe_capabilities(self) -> HarnessAdapterCapabilities: ...

    def validate_requested_profile(
        self, requested: RequestedExecutionProfile
    ) -> ProfileValidation: ...

    def start_session(
        self,
        *,
        operation_id: OperationId,
        requested: RequestedExecutionProfile,
        epoch: SessionEpochRef,
        generation: ProcessGenerationRef,
        staged_config_receipt: StageConfigReceipt | None = None,
    ) -> SessionStartObservation: ...

    def begin_turn(
        self,
        *,
        operation_id: OperationId,
        turn: TurnRef,
        generation: ProcessGenerationRef,
        launch: LaunchComparison,
    ) -> TurnStartObservation: ...

    def read_events(
        self, cursor: EventCursor, *, timeout_seconds: float = 30.0
    ) -> tuple[tuple[NormalizedEvent, ...], EventCursor]: ...

    def interrupt_turn(self, turn: TurnRef, *, operation_id: OperationId) -> None: ...

    def collect_candidate_result(self, turn: TurnRef) -> CandidateResult: ...

    def graceful_stop(
        self, generation: ProcessGenerationRef, *, operation_id: OperationId
    ) -> ReconcileObservation: ...

    def cancel(
        self, generation: ProcessGenerationRef, *, reason: str, operation_id: OperationId
    ) -> ReconcileObservation: ...

    def reconcile(self, generation: ProcessGenerationRef) -> ReconcileObservation: ...


@runtime_checkable
class SupportsProbe(Protocol):
    def probe(
        self, *, operation_id: OperationId, requested: RequestedExecutionProfile
    ) -> HarnessAdapterCapabilities: ...


@runtime_checkable
class SupportsConfigStaging(Protocol):
    def stage_operator_config(self, request: StageConfigRequest) -> StageConfigReceipt: ...


@runtime_checkable
class SupportsSessionResume(Protocol):
    def resume_session(
        self,
        *,
        operation_id: OperationId,
        epoch: SessionEpochRef,
        generation: ProcessGenerationRef,
        provider_session: ProviderSessionHandoff,
        requested: RequestedExecutionProfile,
    ) -> SessionStartObservation: ...


@runtime_checkable
class SupportsSteering(Protocol):
    def send_input(self, *, operation_id: OperationId, turn: TurnRef, payload: str) -> None: ...


@runtime_checkable
class SupportsApprovalResponse(Protocol):
    def respond_to_approval(
        self, *, operation_id: OperationId, turn: TurnRef, decision: str
    ) -> None: ...


@runtime_checkable
class SupportsNativeFork(Protocol):
    def fork_session(
        self,
        *,
        operation_id: OperationId,
        epoch: SessionEpochRef,
        generation: ProcessGenerationRef,
    ) -> NativeForkObservation: ...


@runtime_checkable
class SupportsCheckpoint(Protocol):
    def checkpoint(
        self, *, operation_id: OperationId, generation: ProcessGenerationRef
    ) -> CheckpointObservation: ...


OPTIONAL_ADAPTER_PROTOCOLS: dict[str, type] = {
    "probe": SupportsProbe,
    "stage_operator_config": SupportsConfigStaging,
    "resume_session": SupportsSessionResume,
    "send_input": SupportsSteering,
    "respond_to_approval": SupportsApprovalResponse,
    "fork_session": SupportsNativeFork,
    "checkpoint": SupportsCheckpoint,
}


def writer_realm_key(worker_id: str, provider_session_id: str) -> tuple[str, str]:
    worker = str(worker_id or "").strip()
    session = str(provider_session_id or "").strip()
    if not worker or not session:
        raise ValueError("writer realm requires worker_id and provider_session_id")
    return (worker, session)


def may_hold_prebind_epoch_writer(
    *,
    session_epoch_id: str,
    generation_id: str,
    held_by_epoch: Mapping[str, str],
) -> bool:
    """At most one Executive-held writer per session_epoch_id, including NULL S1."""

    epoch = str(session_epoch_id or "").strip()
    generation = str(generation_id or "").strip()
    if not epoch or not generation:
        raise ValueError("pre-bind fence requires session_epoch_id and generation_id")
    owner = held_by_epoch.get(epoch)
    return owner is None or owner == generation


def may_hold_postbind_realm_writer(
    *,
    worker_id: str,
    provider_session_id: str,
    generation_id: str,
    held_by: Mapping[tuple[str, str], str],
) -> bool:
    key = writer_realm_key(worker_id, provider_session_id)
    owner = held_by.get(key)
    return owner is None or owner == generation_id


def may_hold_executive_writer(
    *,
    worker_id: str,
    provider_session_id: str,
    generation_id: str,
    held_by: Mapping[tuple[str, str], str],
) -> bool:
    """Post-bind native-session realm fence.  Pre-bind uses may_hold_prebind_epoch_writer."""

    return may_hold_postbind_realm_writer(
        worker_id=worker_id,
        provider_session_id=provider_session_id,
        generation_id=generation_id,
        held_by=held_by,
    )


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


def may_bind_epoch_provider_session(
    *,
    epoch_provider_session_id: str | None,
    observed_provider_session_id: str,
) -> bool:
    observed = str(observed_provider_session_id or "").strip()
    if not observed:
        return False
    if epoch_provider_session_id is None:
        return True
    return epoch_provider_session_id == observed


def operation_receipt_command_id(
    operation_id: OperationId, kind: OperationReceiptKind
) -> str:
    if kind is OperationReceiptKind.INTENT:
        return operation_id.command_id
    suffix_map = {
        OperationReceiptKind.APPLIED: "applied",
        OperationReceiptKind.REFUSED: "refused",
        OperationReceiptKind.EFFECT_UNKNOWN: "effect-unknown",
        OperationReceiptKind.RECONCILED: "reconciled",
    }
    suffix = suffix_map[kind]
    if suffix not in OPERATION_RECEIPT_COMMAND_SUFFIXES:
        raise ValueError("receipt suffix is not in the frozen suffix set")
    derived = f"{operation_id.command_id}:{suffix}"
    if COMMAND_ID_RE.fullmatch(derived) is None:
        raise ValueError("derived command_id exceeds Executive command_id law")
    return derived


def resolve_operation_after_crash(
    *,
    intent_committed: bool,
    terminal_receipt: OperationReceiptKind | None,
    external_call_proven_not_started: bool,
) -> OperationResolution:
    """Absence of APPLIED is not proof the side effect did not occur."""

    if not intent_committed:
        return OperationResolution.NOT_STARTED
    if terminal_receipt is OperationReceiptKind.APPLIED:
        return OperationResolution.APPLIED
    if terminal_receipt is OperationReceiptKind.REFUSED:
        return OperationResolution.REFUSED
    if terminal_receipt is OperationReceiptKind.RECONCILED:
        return OperationResolution.RECONCILED
    if terminal_receipt is OperationReceiptKind.EFFECT_UNKNOWN:
        return OperationResolution.EFFECT_UNKNOWN
    if external_call_proven_not_started:
        return OperationResolution.MAY_RETRY_SAME_OPERATION_ID
    return OperationResolution.EFFECT_UNKNOWN


def same_epoch_recovery_replay_disposition(
    *,
    intent_committed: bool,
    terminal_receipt: OperationReceiptKind | None,
    external_call_proven_not_started: bool,
) -> SameEpochRecoveryReplay:
    """Crash after TX-10 INTENT: retry the allocated G2 or fail closed.

    Allocating another generation is never a legal replay after TX-10 commits.
    """

    resolution = resolve_operation_after_crash(
        intent_committed=intent_committed,
        terminal_receipt=terminal_receipt,
        external_call_proven_not_started=external_call_proven_not_started,
    )
    if resolution is OperationResolution.NOT_STARTED:
        return SameEpochRecoveryReplay.NOT_STARTED
    if resolution is OperationResolution.MAY_RETRY_SAME_OPERATION_ID:
        return SameEpochRecoveryReplay.RETRY_SAME_OPERATION_ON_ALLOCATED_GENERATION
    if resolution is OperationResolution.EFFECT_UNKNOWN:
        return SameEpochRecoveryReplay.EFFECT_UNKNOWN_HOLD_GENERATION
    if resolution is OperationResolution.APPLIED:
        return SameEpochRecoveryReplay.APPLIED
    if resolution is OperationResolution.REFUSED:
        return SameEpochRecoveryReplay.REFUSED
    return SameEpochRecoveryReplay.RECONCILED


def may_allocate_another_generation_after_tx10(*, intent_committed: bool) -> bool:
    """TX-10 already placed G2 on the writer fence.  G3 is never a replay."""

    del intent_committed
    return False


def diagnose_same_epoch_generation_recovery(
    snapshot: SameEpochRecoverySnapshot,
    *,
    old_generation_id: str,
    new_generation: ProcessGenerationRef,
    operation_id: OperationId,
    resume_safe: bool,
) -> SameEpochRecoveryRefusal | None:
    if snapshot.epoch_state is not SessionEpochState.CURRENT:
        return SameEpochRecoveryRefusal.EPOCH_NOT_CURRENT
    if new_generation.session_epoch_id != snapshot.epoch.session_epoch_id:
        return SameEpochRecoveryRefusal.EPOCH_MISMATCH
    if snapshot.creates_new_epoch or snapshot.consumes_attempt:
        return SameEpochRecoveryRefusal.EPOCH_MISMATCH
    old = next(
        (
            row
            for row in snapshot.generations
            if row.ref.process_generation_id == old_generation_id
        ),
        None,
    )
    if old is None:
        return SameEpochRecoveryRefusal.EPOCH_MISMATCH
    if old.ref.session_epoch_id != snapshot.epoch.session_epoch_id:
        return SameEpochRecoveryRefusal.EPOCH_MISMATCH
    if new_generation.worker_id != snapshot.epoch.worker_id:
        return SameEpochRecoveryRefusal.EPOCH_MISMATCH
    if old.process_liveness is ProcessLiveness.UNKNOWN:
        return SameEpochRecoveryRefusal.PROCESS_LIVENESS_UNKNOWN
    if old.process_liveness is not ProcessLiveness.PROVEN_DEAD:
        return SameEpochRecoveryRefusal.PROCESS_NOT_PROVEN_DEAD
    if old.provider_writer_state is not ProviderWriterState.RELEASED:
        return SameEpochRecoveryRefusal.PROVIDER_WRITER_NOT_RELEASED
    if not resume_safe:
        return SameEpochRecoveryRefusal.RESUME_NOT_SAFE
    if not old.executive_writer_held:
        return SameEpochRecoveryRefusal.OLD_WRITER_NOT_HELD
    expected_number = max(row.ref.generation_number for row in snapshot.generations) + 1
    if new_generation.generation_number != expected_number:
        return SameEpochRecoveryRefusal.GENERATION_NOT_SEQUENTIAL
    held_by_epoch = {
        row.ref.session_epoch_id: row.ref.process_generation_id
        for row in snapshot.generations
        if row.executive_writer_held
    }
    released_epoch = {
        key: value for key, value in held_by_epoch.items() if value != old_generation_id
    }
    if not may_hold_prebind_epoch_writer(
        session_epoch_id=snapshot.epoch.session_epoch_id,
        generation_id=new_generation.process_generation_id,
        held_by_epoch=released_epoch,
    ):
        return SameEpochRecoveryRefusal.SUCCESSOR_WRITER_CONFLICT
    held_by_realm = {
        writer_realm_key(snapshot.epoch.worker_id, snapshot.provider_session_id): (
            row.ref.process_generation_id
        )
        for row in snapshot.generations
        if row.executive_writer_held and row.provider_session_id
    }
    released_realm = {
        key: value for key, value in held_by_realm.items() if value != old_generation_id
    }
    if not may_hold_postbind_realm_writer(
        worker_id=snapshot.epoch.worker_id,
        provider_session_id=snapshot.provider_session_id,
        generation_id=new_generation.process_generation_id,
        held_by=released_realm,
    ):
        return SameEpochRecoveryRefusal.SUCCESSOR_WRITER_CONFLICT
    if operation_id.command_id in snapshot.reserved_operation_ids:
        return SameEpochRecoveryRefusal.OPERATION_ID_DUPLICATE
    return None


def may_recover_same_epoch_generation(
    snapshot: SameEpochRecoverySnapshot,
    *,
    old_generation_id: str,
    new_generation: ProcessGenerationRef,
    operation_id: OperationId,
    resume_safe: bool,
) -> bool:
    return (
        diagnose_same_epoch_generation_recovery(
            snapshot,
            old_generation_id=old_generation_id,
            new_generation=new_generation,
            operation_id=operation_id,
            resume_safe=resume_safe,
        )
        is None
    )


def apply_same_epoch_generation_recovery(
    snapshot: SameEpochRecoverySnapshot,
    *,
    old_generation_id: str,
    new_generation: ProcessGenerationRef,
    operation_id: OperationId,
    resume_safe: bool,
) -> SameEpochRecoverySnapshot:
    """Pure TX-10.  Releases G1 writer, inserts G2 writer, reserves OperationId."""

    refusal = diagnose_same_epoch_generation_recovery(
        snapshot,
        old_generation_id=old_generation_id,
        new_generation=new_generation,
        operation_id=operation_id,
        resume_safe=resume_safe,
    )
    if refusal is not None:
        raise ValueError(refusal.value)
    updated: list[ProcessGenerationRecord] = []
    for row in snapshot.generations:
        if row.ref.process_generation_id == old_generation_id:
            updated.append(
                ProcessGenerationRecord(
                    ref=row.ref,
                    executive_writer_held=False,
                    process_liveness=row.process_liveness,
                    provider_writer_state=row.provider_writer_state,
                    provider_session_id=row.provider_session_id,
                )
            )
        else:
            updated.append(row)
    updated.append(
        ProcessGenerationRecord(
            ref=new_generation,
            executive_writer_held=True,
            process_liveness=ProcessLiveness.UNKNOWN,
            provider_writer_state=ProviderWriterState.UNKNOWN,
            provider_session_id=snapshot.provider_session_id,
        )
    )
    return SameEpochRecoverySnapshot(
        epoch=snapshot.epoch,
        epoch_state=SessionEpochState.CURRENT,
        provider_session_id=snapshot.provider_session_id,
        generations=tuple(updated),
        reserved_operation_ids=frozenset(
            {*snapshot.reserved_operation_ids, operation_id.command_id}
        ),
        intent_receipts=(
            *snapshot.intent_receipts,
            OperationIntentReceipt(
                operation_id=operation_id,
                target=tx10_resume_intent_target(
                    epoch=snapshot.epoch,
                    generation=new_generation,
                    provider_session_id=snapshot.provider_session_id,
                ),
            ),
        ),
        creates_new_epoch=False,
        consumes_attempt=False,
    )


def may_start_successor_rich_writer(
    *,
    process_liveness: ProcessLiveness,
    process_proven_absent: bool,
    external_effect_unknown: bool,
) -> bool:
    """UNKNOWN process blocks a new writer until absence is proven.

    ``external_effect_unknown`` is retained as a documented input so callers
    cannot drop it.  It does not authorize a successor while the process may
    still be alive.  A PROVEN_DEAD generation may be abandoned and replaced
    even when the provider writer remains UNKNOWN.
    """

    if process_liveness is ProcessLiveness.UNKNOWN and not process_proven_absent:
        return False
    if process_liveness is ProcessLiveness.ALIVE:
        return False
    if process_liveness is ProcessLiveness.PROVEN_DEAD:
        return True
    return bool(process_proven_absent)


def may_abandon_epoch(*, process_liveness: ProcessLiveness) -> bool:
    return process_liveness is ProcessLiveness.PROVEN_DEAD


def event_cursor_scoped_to(cursor: EventCursor, process_generation_id: str) -> bool:
    return cursor.process_generation_id == process_generation_id


def workspace_identities_equal(
    requested: WorkspaceIdentity, observed: WorkspaceIdentity | None
) -> bool:
    if observed is None:
        return False
    return (
        requested.workspace_path == observed.workspace_path
        and requested.base_sha == observed.base_sha
        and requested.device == observed.device
        and requested.inode == observed.inode
        and requested.uid == observed.uid
        and requested.gid == observed.gid
    )


def process_identities_match(
    expected: ProcessIdentityObservation, observed: ProcessIdentityObservation
) -> bool:
    if None in (
        expected.pid,
        expected.pgid,
        expected.process_start_identity,
        expected.boot_id,
        observed.pid,
        observed.pgid,
        observed.process_start_identity,
        observed.boot_id,
    ):
        return False
    return (
        expected.pid == observed.pid
        and expected.pgid == observed.pgid
        and expected.process_start_identity == observed.process_start_identity
        and expected.boot_id == observed.boot_id
    )


def process_identity_is_complete(process: ProcessIdentityObservation) -> bool:
    """Executive local-process law: positive pid/pgid and nonblank trimmed start/boot."""

    if process.pid is None or process.pgid is None:
        return False
    try:
        pid = int(process.pid)
        pgid = int(process.pgid)
    except (TypeError, ValueError):
        return False
    if pid <= 0 or pgid <= 0:
        return False
    start = str(process.process_start_identity or "").strip()
    boot = str(process.boot_id or "").strip()
    return bool(start) and bool(boot)


def tx10_resume_intent_target(
    *,
    epoch: SessionEpochRef,
    generation: ProcessGenerationRef,
    provider_session_id: str,
) -> OperationIntentTarget:
    """TX-10 Event-plane INTENT payload for resume_session of already-bound S1."""

    return OperationIntentTarget(
        operation_kind=OperationKind.RESUME_SESSION,
        attempt_id=epoch.attempt_id,
        session_epoch_id=epoch.session_epoch_id,
        process_generation_id=generation.process_generation_id,
        worker_id=epoch.worker_id,
        provider_session_id=str(provider_session_id).strip(),
    )


def operation_intent_target_from_event_payload(
    payload: Mapping[str, object],
) -> OperationIntentTarget:
    """Parse events.payload_json of OPERATOR_OPERATION_INTENT."""

    missing = [
        name for name in OPERATION_INTENT_TARGET_FIELDS if name not in payload
    ]
    if missing:
        raise ValueError(
            "INTENT payload missing " + ", ".join(missing)
        )
    try:
        kind = OperationKind(str(payload["operation_kind"]))
    except ValueError as exc:
        raise ValueError("unknown operation_kind in INTENT payload") from exc
    return OperationIntentTarget(
        operation_kind=kind,
        attempt_id=str(payload["attempt_id"]),
        session_epoch_id=str(payload["session_epoch_id"]),
        process_generation_id=str(payload["process_generation_id"]),
        worker_id=str(payload["worker_id"]),
        provider_session_id=str(payload["provider_session_id"]),
    )


def intent_receipt_for_operation(
    receipts: Sequence[OperationIntentReceipt],
    operation_id: OperationId,
) -> OperationIntentReceipt | None:
    for receipt in receipts:
        if receipt.operation_id.command_id == operation_id.command_id:
            return receipt
    return None


def diagnose_resume_intent_target(
    receipt: OperationIntentReceipt | None,
    *,
    operation_id: OperationId,
    epoch: SessionEpochRef,
    generation: ProcessGenerationRecord,
    bound_provider_session_id: str,
) -> ResumeBindRefusal | None:
    if receipt is None:
        return ResumeBindRefusal.INTENT_MISSING
    target = receipt.target
    bound = str(bound_provider_session_id or "").strip()
    if receipt.operation_id.command_id != operation_id.command_id:
        return ResumeBindRefusal.INTENT_TARGET_MISMATCH
    if receipt.aggregate_type != OPERATION_AGGREGATE_TYPE:
        return ResumeBindRefusal.INTENT_TARGET_MISMATCH
    if target.operation_kind is not OperationKind.RESUME_SESSION:
        return ResumeBindRefusal.INTENT_TARGET_MISMATCH
    if target.attempt_id != epoch.attempt_id:
        return ResumeBindRefusal.INTENT_TARGET_MISMATCH
    if target.session_epoch_id != epoch.session_epoch_id:
        return ResumeBindRefusal.INTENT_TARGET_MISMATCH
    if target.session_epoch_id != generation.ref.session_epoch_id:
        return ResumeBindRefusal.INTENT_TARGET_MISMATCH
    if target.process_generation_id != generation.ref.process_generation_id:
        return ResumeBindRefusal.INTENT_TARGET_MISMATCH
    if target.worker_id != epoch.worker_id:
        return ResumeBindRefusal.INTENT_TARGET_MISMATCH
    if target.worker_id != generation.ref.worker_id:
        return ResumeBindRefusal.INTENT_TARGET_MISMATCH
    if bound and target.provider_session_id != bound:
        return ResumeBindRefusal.INTENT_TARGET_MISMATCH
    return None


def provider_session_handoff_for_resume(
    *,
    epoch: SessionEpochRef,
    bound_provider_session_id: str,
) -> ProviderSessionHandoff:
    """Build the resume IN argument from the already-bound epoch session."""

    session = str(bound_provider_session_id or "").strip()
    worker = str(epoch.worker_id or "").strip()
    if not session:
        raise ValueError("resume requires already-bound provider_session_id")
    if not worker:
        raise ValueError("resume handoff requires worker_id")
    return ProviderSessionHandoff(provider_session_id=session, worker_id=worker)


def resume_session_handoff_is_lawful(
    handoff: ProviderSessionHandoff,
    *,
    epoch: SessionEpochRef,
    bound_provider_session_id: str,
) -> bool:
    bound = str(bound_provider_session_id or "").strip()
    return (
        bool(bound)
        and handoff.worker_id == epoch.worker_id
        and handoff.provider_session_id == bound
    )


def diagnose_resume_bind(
    snapshot: ResumeBindSnapshot,
    *,
    observation: SessionStartObservation,
    handoff: ProviderSessionHandoff,
) -> ResumeBindRefusal | None:
    target_refusal = diagnose_resume_intent_target(
        snapshot.intent_receipt,
        operation_id=snapshot.operation_id,
        epoch=snapshot.epoch,
        generation=snapshot.generation,
        bound_provider_session_id=snapshot.bound_provider_session_id,
    )
    if target_refusal is not None:
        return target_refusal
    if snapshot.epoch_state is not SessionEpochState.CURRENT:
        return ResumeBindRefusal.EPOCH_NOT_CURRENT
    if snapshot.creates_new_epoch or snapshot.consumes_attempt:
        return ResumeBindRefusal.EPOCH_MISMATCH
    if snapshot.epoch_provider_session_mutated:
        return ResumeBindRefusal.EPOCH_MISMATCH
    if snapshot.generation.ref.session_epoch_id != snapshot.epoch.session_epoch_id:
        return ResumeBindRefusal.EPOCH_MISMATCH
    if snapshot.generation.ref.worker_id != snapshot.epoch.worker_id:
        return ResumeBindRefusal.EPOCH_MISMATCH
    if not snapshot.generation.executive_writer_held:
        return ResumeBindRefusal.GENERATION_NOT_WRITER
    bound = str(snapshot.bound_provider_session_id or "").strip()
    if not bound:
        return ResumeBindRefusal.EPOCH_SESSION_UNBOUND
    if not resume_session_handoff_is_lawful(
        handoff,
        epoch=snapshot.epoch,
        bound_provider_session_id=bound,
    ):
        return ResumeBindRefusal.HANDOFF_MISMATCH
    if snapshot.generation.provider_session_id != bound:
        return ResumeBindRefusal.INDEX_PROJECTION_MISMATCH
    observed_session = str(observation.provider_session_id or "").strip()
    if observed_session != bound:
        return ResumeBindRefusal.PROVIDER_SESSION_MISMATCH
    if not process_identity_is_complete(observation.process):
        return ResumeBindRefusal.PROCESS_IDENTITY_INCOMPLETE
    if snapshot.applied:
        if snapshot.process is None:
            return ResumeBindRefusal.ALREADY_APPLIED_CONFLICT
        if not process_identities_match(snapshot.process, observation.process):
            return ResumeBindRefusal.ALREADY_APPLIED_CONFLICT
        return None
    return None


def may_bind_resume_result(
    snapshot: ResumeBindSnapshot,
    *,
    observation: SessionStartObservation,
    handoff: ProviderSessionHandoff,
) -> bool:
    return (
        diagnose_resume_bind(snapshot, observation=observation, handoff=handoff)
        is None
    )


def apply_resume_bind(
    snapshot: ResumeBindSnapshot,
    *,
    observation: SessionStartObservation,
    handoff: ProviderSessionHandoff,
) -> ResumeBindSnapshot:
    """Pure TX-11.  Records G2 process identity and APPLIED.  Does not rebind S1."""

    refusal = diagnose_resume_bind(
        snapshot, observation=observation, handoff=handoff
    )
    if refusal is not None:
        raise ValueError(refusal.value)
    if snapshot.applied:
        return snapshot
    bound = snapshot.bound_provider_session_id
    return ResumeBindSnapshot(
        epoch=snapshot.epoch,
        epoch_state=SessionEpochState.CURRENT,
        bound_provider_session_id=bound,
        generation=ProcessGenerationRecord(
            ref=snapshot.generation.ref,
            executive_writer_held=True,
            process_liveness=ProcessLiveness.ALIVE,
            provider_writer_state=ProviderWriterState.HELD,
            provider_session_id=bound,
        ),
        operation_id=snapshot.operation_id,
        intent_receipt=snapshot.intent_receipt,
        applied=True,
        process=observation.process,
        creates_new_epoch=False,
        consumes_attempt=False,
        epoch_provider_session_mutated=False,
    )


def derive_resume_safety(
    *,
    epoch_state: SessionEpochState,
    executive_writer_held: bool,
    process_liveness: ProcessLiveness,
    provider_writer_state: ProviderWriterState,
    expected_process: ProcessIdentityObservation,
    observed_process: ProcessIdentityObservation,
    requested: RequestedExecutionProfile,
    observed: ObservedHarnessAttestation,
    live_transport_adoptable: bool = False,
) -> bool:
    """Resume is derived by Executive code.  The adapter cannot certify it."""

    if live_transport_adoptable:
        return False
    if epoch_state is not SessionEpochState.CURRENT:
        return False
    if not executive_writer_held:
        return False
    if process_liveness is ProcessLiveness.UNKNOWN:
        return False
    if process_liveness is ProcessLiveness.PROVEN_DEAD:
        if provider_writer_state is not ProviderWriterState.RELEASED:
            return False
    if provider_writer_state is ProviderWriterState.HELD and process_liveness is not ProcessLiveness.ALIVE:
        return False
    if provider_writer_state is ProviderWriterState.UNKNOWN:
        return False
    if not process_identities_match(expected_process, observed_process):
        return False
    if compare_launch(requested, observed).decision is not LaunchDecision.ALLOW:
        return False
    return True


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

    return WriterFacts(
        process_liveness=facts.process_liveness,
        executive_writer_held=False,
        provider_writer_state=facts.provider_writer_state,
    )


def restore_invalidation(facts: WriterFacts) -> RestoreInvalidationResult:
    """Invalidate authority.  Do not rewrite historical provider/process evidence."""

    return RestoreInvalidationResult(
        historical_provider_writer_state=facts.provider_writer_state,
        historical_process_liveness=facts.process_liveness,
        clear_executive_writer=True,
        abandon_epoch=True,
        attempt_status=POST_RESTORE_ATTEMPT_STATUS,
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


def _identity_proven(
    requested: CapabilityIdentity,
    observed: ObservedCapabilityIdentity,
    harness_binary_digest: str | None,
) -> bool:
    if requested.name != observed.name:
        return False
    if requested.kind and observed.kind and requested.kind != observed.kind:
        return False
    if requested.harness_binary_digest != (harness_binary_digest or ""):
        return False
    if requested.skill_content_digest and requested.skill_content_digest != observed.skill_content_digest:
        return False
    if requested.tool_schema_digest and requested.tool_schema_digest != observed.tool_schema_digest:
        return False
    if requested.mcp_server_identity and requested.mcp_server_identity != observed.mcp_server_identity:
        return False
    if requested.mcp_server_version and requested.mcp_server_version != observed.mcp_server_version:
        return False
    if requested.mcp_auth_status and requested.mcp_auth_status != observed.mcp_auth_status:
        return False
    return True


def classify_observed_capabilities(
    requested: RequestedExecutionProfile,
    observed: ObservedHarnessAttestation,
) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    """Return (missing_required, forbidden_present, unclassified, unknown_precision)."""

    observed_caps = list(observed.capabilities)
    named = {item.name for item in observed_caps}
    named.update(observed.effective_skills)
    named.update(observed.effective_mcp)
    named.update(observed.effective_plugins_or_apps)

    missing: list[str] = []
    unknown_precision: list[str] = []
    for rule in requested.capabilities.required:
        proven = any(
            _identity_proven(rule, item, observed.harness_binary_digest) for item in observed_caps
        )
        if proven:
            continue
        if any(item.name == rule.name for item in observed_caps) or rule.name in named:
            unknown_precision.append(rule.name)
            missing.append(rule.name)
        else:
            missing.append(rule.name)

    forbidden_present = tuple(
        name for name in sorted(named) if name in set(requested.capabilities.forbidden)
    )
    required_names = {item.name for item in requested.capabilities.required}
    allowed_names = {item.name for item in requested.capabilities.allowed_ambient}
    unclassified: list[str] = []
    for name in sorted(named):
        if name in required_names or name in allowed_names or name in set(requested.capabilities.forbidden):
            continue
        unclassified.append(name)

    for rule in requested.capabilities.allowed_ambient:
        if rule.name not in named:
            continue
        proven = any(
            _identity_proven(rule, item, observed.harness_binary_digest) for item in observed_caps
        )
        if not proven:
            unknown_precision.append(rule.name)
            if rule.name not in unclassified and rule.name not in required_names:
                unclassified.append(rule.name)

    return (
        tuple(missing),
        forbidden_present,
        tuple(unclassified),
        tuple(dict.fromkeys(unknown_precision)),
    )


def _auth_realm_allows(
    requested: RequestedExecutionProfile, observed: ObservedHarnessAttestation
) -> bool:
    if observed.auth.worker_id != requested.worker_id:
        return False
    if observed.auth.provider != requested.provider:
        return False
    if requested.auth_realm_requirement is AuthRealmRequirement.SLOT_BOUND_V1:
        return True
    expected = str(requested.expected_provider_account_id or "").strip()
    observed_id = str(observed.auth.nonsecret_provider_account_id or "").strip()
    return bool(expected) and expected == observed_id


def compare_launch(
    requested: RequestedExecutionProfile,
    observed: ObservedHarnessAttestation,
) -> LaunchComparison:
    """Pure function of requested + observed.  No caller-supplied security verdicts."""

    reasons: list[str] = []
    unknown: list[str] = []
    decision = LaunchDecision.ALLOW

    if not observed.served_model:
        decision = LaunchDecision.REFUSE_SERVED_MODEL_UNKNOWN
        reasons.append("served_model_unknown")
        unknown.append("served_model")
    elif observed.served_model != requested.requested_model:
        decision = LaunchDecision.REFUSE_SERVED_MODEL_MISMATCH
        reasons.append("served_model_mismatch")

    if decision is LaunchDecision.ALLOW:
        if not observed.harness_binary_digest:
            decision = LaunchDecision.REFUSE_UNATTESTABLE
            reasons.append("harness_binary_digest_unknown")
            unknown.append("harness_binary_digest")
        elif observed.harness_binary_digest != requested.harness_binary_digest:
            decision = LaunchDecision.REFUSE_HARNESS_BINARY_MISMATCH
            reasons.append("harness_binary_digest_mismatch")

    if decision is LaunchDecision.ALLOW and not workspace_identities_equal(
        requested.workspace, observed.workspace
    ):
        decision = LaunchDecision.REFUSE_WORKSPACE_MISMATCH
        reasons.append("workspace_mismatch")
        if observed.workspace is None:
            unknown.append("workspace")

    if decision is LaunchDecision.ALLOW:
        if not observed.sandbox_state:
            decision = LaunchDecision.REFUSE_UNATTESTABLE
            reasons.append("sandbox_unknown")
            unknown.append("sandbox")
        elif observed.sandbox_state != requested.sandbox_policy:
            decision = LaunchDecision.REFUSE_SANDBOX_MISMATCH
            reasons.append("sandbox_mismatch")

    if decision is LaunchDecision.ALLOW:
        if not observed.approval_state:
            decision = LaunchDecision.REFUSE_UNATTESTABLE
            reasons.append("approval_unknown")
            unknown.append("approval")
        elif observed.approval_state != requested.approval_policy:
            decision = LaunchDecision.REFUSE_APPROVAL_MISMATCH
            reasons.append("approval_mismatch")

    if decision is LaunchDecision.ALLOW:
        if not observed.network_state:
            decision = LaunchDecision.REFUSE_UNATTESTABLE
            reasons.append("network_unknown")
            unknown.append("network")
        elif observed.network_state != requested.network_policy:
            decision = LaunchDecision.REFUSE_NETWORK_MISMATCH
            reasons.append("network_mismatch")

    if decision is LaunchDecision.ALLOW and requested.expected_config_digest:
        if not observed.effective_config_digest:
            decision = LaunchDecision.REFUSE_UNATTESTABLE
            reasons.append("config_unknown")
            unknown.append("effective_config_digest")
        elif observed.effective_config_digest != requested.expected_config_digest:
            decision = LaunchDecision.REFUSE_CONFIG_DRIFT
            reasons.append("config_drift")

    if decision is LaunchDecision.ALLOW and not _auth_realm_allows(requested, observed):
        decision = LaunchDecision.REFUSE_AUTH_REALM_MISMATCH
        reasons.append("auth_realm_mismatch")
        if (
            requested.auth_realm_requirement is AuthRealmRequirement.VERIFIED_PROVIDER_ACCOUNT
            and not observed.auth.nonsecret_provider_account_id
        ):
            unknown.append("provider_account_id")

    missing, forbidden_present, unclassified, unknown_precision = classify_observed_capabilities(
        requested, observed
    )
    unknown.extend(unknown_precision)

    if decision is LaunchDecision.ALLOW and forbidden_present:
        decision = LaunchDecision.REFUSE_FORBIDDEN
        reasons.append("forbidden_present")
    if decision is LaunchDecision.ALLOW and missing:
        decision = LaunchDecision.REFUSE_MISSING_REQUIRED
        reasons.append("missing_required")
    if decision is LaunchDecision.ALLOW and unclassified:
        lab_ok = (
            not requested.write_capable
            and requested.capabilities.unclassified_policy == "lab_allow_unclassified_readonly"
        )
        if not lab_ok:
            decision = LaunchDecision.REFUSE_UNCLASSIFIED
            reasons.append("unclassified")

    if decision is LaunchDecision.ALLOW:
        helpers_requested = requested.native_helper_policy is not NativeHelperPolicy.DISABLED
        if requested.write_capable and helpers_requested:
            if (
                observed.supports_subagent_capability_ceiling
                is not ObservedTriState.VERIFIED
            ):
                decision = LaunchDecision.REFUSE_HELPER_CEILING_MISSING
                reasons.append("helper_ceiling_missing")
        elif (
            requested.write_capable
            and requested.native_helper_policy is NativeHelperPolicy.PARENT_READ_ONLY_CEILING
        ):
            decision = LaunchDecision.REFUSE_HELPER_CEILING_MISSING
            reasons.append("prompt_only_helper_policy")

    return LaunchComparison(
        requested=requested,
        observed=observed,
        decision=decision,
        mismatch_reasons=tuple(reasons),
        missing_required=missing,
        forbidden_present=forbidden_present,
        unclassified=unclassified,
        unknown_required_observations=tuple(dict.fromkeys(unknown)),
    )


def first_work_turn_allowed(decision: LaunchDecision) -> bool:
    return decision is LaunchDecision.ALLOW


def native_helpers_allowed(
    *,
    write_capable: bool,
    native_helper_policy: NativeHelperPolicy,
    supports_subagent_capability_ceiling: ObservedTriState,
) -> bool:
    if native_helper_policy is NativeHelperPolicy.DISABLED:
        return False
    if not write_capable:
        return native_helper_policy is NativeHelperPolicy.PARENT_READ_ONLY_CEILING
    return supports_subagent_capability_ceiling is ObservedTriState.VERIFIED


def compare_launch_parameter_names() -> tuple[str, ...]:
    return tuple(inspect.signature(compare_launch).parameters)


def adapter_method_returns_executive_id(method_name: str) -> bool:
    method = getattr(OperatorHarnessAdapter, method_name, None)
    if method is None:
        return False
    hints = get_type_hints(method)
    returned = hints.get("return")
    return returned in {SessionEpochRef, ProcessGenerationRef, TurnRef}


def reconcile_observation_field_names() -> frozenset[str]:
    return frozenset(item.name for item in fields(ReconcileObservation))


def rich_ohf_may_rewrite_legacy_attempt_field(field_name: str) -> bool:
    return field_name not in LEGACY_SEALED_WORKER_ATTEMPT_FIELDS


__all__ = [
    "ACCOUNT_REALM_STATUS",
    "ADAPTER_OBSERVED_IDS",
    "ATTEMPT_BOUNDARY_MATRIX",
    "AuthIdentityConfidence",
    "AuthRealmFact",
    "AuthRealmRequirement",
    "AdapterFailureClass",
    "AttemptBoundary",
    "AttemptExecutionMode",
    "CANONICAL_SESSION_FIELD",
    "CARDINALITY",
    "COMMAND_ID_MAX_LEN",
    "COMMAND_ID_RE",
    "CRASH_WINDOW_MATRIX",
    "CandidateResult",
    "CapabilityClass",
    "CapabilityIdentity",
    "CapabilityManifest",
    "CheckpointObservation",
    "EnforcementSite",
    "EventCursor",
    "EXECUTIVE_ALLOCATED_IDS",
    "EXECUTIVE_OWNED_RECONCILE_FIELDS",
    "FORBIDDEN_COMPARE_LAUNCH_PARAMETERS",
    "FORBIDDEN_SESSION_SYNONYM",
    "HarnessAdapterCapabilities",
    "INVARIANT_ENFORCEMENT",
    "LEGACY_SEALED_WORKER_ATTEMPT_FIELDS",
    "LaunchComparison",
    "LaunchDecision",
    "LIVE_APP_SERVER_ADOPTION",
    "LONGEST_OPERATION_RECEIPT_SUFFIX_LEN",
    "MAX_OPERATION_ID_LEN",
    "METHOD_CONTRACTS",
    "MethodClass",
    "MethodContract",
    "NativeForkObservation",
    "NativeHelperPolicy",
    "NormalizedEvent",
    "OHF_FORBIDDEN_ATTEMPT_COLUMNS",
    "OHF_PROPOSED_ATTEMPT_COLUMNS",
    "OPERATOR_HARNESS_INTERFACE_VERSION",
    "OPERATION_AGGREGATE_TYPE",
    "OPERATION_COMMAND_ID_PREFIX",
    "OPERATION_INTENT_TARGET_FIELDS",
    "OPERATION_RECEIPT_COMMAND_SUFFIXES",
    "OPTIONAL_ADAPTER_PROTOCOLS",
    "ObservedCapabilityIdentity",
    "ObservedHarnessAttestation",
    "ObservedTriState",
    "OperationId",
    "OperationIdempotencyClass",
    "OperationIntentReceipt",
    "OperationIntentTarget",
    "OperationKind",
    "OperationReceiptKind",
    "OperationResolution",
    "OperatorHarnessAdapter",
    "POST_RESTORE_ATTEMPT_STATUS",
    "PREBIND_WRITER_FENCE_KEY",
    "PROPOSED_SQL_INVARIANTS",
    "ProcessGenerationRecord",
    "ProcessGenerationRef",
    "ProcessIdentityObservation",
    "ProcessLiveness",
    "ProfileValidation",
    "ProviderSessionHandoff",
    "ProviderWriterState",
    "REATTEST_TRIGGERS",
    "RESTORE_POLICY",
    "ReconcileObservation",
    "RequestedExecutionProfile",
    "RestoreInvalidationResult",
    "ResumeBindRefusal",
    "ResumeBindSnapshot",
    "SameEpochRecoveryRefusal",
    "SameEpochRecoveryReplay",
    "SameEpochRecoverySnapshot",
    "SessionEpochRef",
    "SessionEpochState",
    "SessionStartObservation",
    "StageConfigReceipt",
    "StageConfigRequest",
    "SupportsApprovalResponse",
    "SupportsCheckpoint",
    "SupportsConfigStaging",
    "SupportsNativeFork",
    "SupportsProbe",
    "SupportsSessionResume",
    "SupportsSteering",
    "TRANSACTION_GROUPS",
    "TransactionGroup",
    "TurnRef",
    "TurnStartObservation",
    "V1_QUALITY_TRADEOFF",
    "WORKER_SLOT_AUTH_BINDING_PRODUCTION_INVARIANT",
    "WRITER_REALM_KEY",
    "WorkspaceIdentity",
    "WriterFacts",
    "abandon_epoch",
    "adapter_method_returns_executive_id",
    "apply_resume_bind",
    "apply_same_epoch_generation_recovery",
    "classify_capability",
    "classify_observed_capabilities",
    "compare_launch",
    "compare_launch_parameter_names",
    "diagnose_resume_bind",
    "diagnose_resume_intent_target",
    "diagnose_same_epoch_generation_recovery",
    "derive_resume_safety",
    "event_cursor_scoped_to",
    "first_work_turn_allowed",
    "intent_receipt_for_operation",
    "may_allocate_another_generation_after_tx10",
    "may_abandon_epoch",
    "may_bind_epoch_provider_session",
    "may_bind_provider_session",
    "may_bind_resume_result",
    "may_hold_executive_writer",
    "may_hold_postbind_realm_writer",
    "may_hold_prebind_epoch_writer",
    "may_recover_same_epoch_generation",
    "may_start_successor_rich_writer",
    "native_helpers_allowed",
    "operation_id_permits_all_derived_receipts",
    "operation_intent_target_from_event_payload",
    "operation_receipt_command_id",
    "process_end_does_not_release_writer",
    "process_identities_match",
    "process_identity_is_complete",
    "provider_session_handoff_for_resume",
    "resume_session_handoff_is_lawful",
    "reconcile_observation_field_names",
    "resolve_operation_after_crash",
    "restore_invalidation",
    "rich_ohf_may_rewrite_legacy_attempt_field",
    "same_epoch_recovery_replay_disposition",
    "tx10_resume_intent_target",
    "workspace_identities_equal",
    "writer_realm_key",
]
