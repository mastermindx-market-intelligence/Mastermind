"""T3-native execution adapter (MMOS Rev 5 T3 lane, work package D3).

``T3ExecutionAdapter`` implements the ``WorkerExecutionAdapter`` floor plus
the ``RecoverableWorkerExecutionAdapter.reattach`` seam against the shared
child-execution contracts, backed by the T3 Code native thread seam through
an injected :class:`T3NativeClientPort`.

Donor (adapt the seam names, never rebuild): T3 Code,
``github.com/pingdotgg/t3code @0770446869d247a8b28c27d7ed93f47f8ff0c1e4``.
The seam vocabulary follows the verified census at that pin:

* ``t3_thread_launch`` + ``clientRequestId`` idempotency — upstream,
  ``commandId = sha256(JSON[requestNamespace, key])``; the same
  authenticated principal and namespace with the same key replays the
  ORIGINAL thread; a different key or principal mints a NEW thread.  This
  adapter derives the key DETERMINISTICALLY from the broker
  ``ExecutionBinding`` (child identity triple + request_digest +
  adapter_id) so every replay of one logical child carries ONE key.
* ``t3_thread_read`` takes an incremental cursor; the adapter persists the
  cursor and advances it only after a successful read.
* ``t3_thread_wait`` semantics: a wait/read timeout means
  still-waiting/unknown — NEVER permission to replace a run.
* ``t3_thread_send`` modes and exact-run ``interrupt``: cancel targets the
  exact run and stays available even when the binding lease is stale
  (stale leases block NEW execution only — Rev 5 §3A/§7).

Durable state (Rev 5 P0 — crash-safe original execution):

* All per-run state (launch intents, receipts, original refs, cursors, cancel
  ledger, start bindings/specs, result references) lives in an injected
  :class:`T3AdapterStateStore`.  :class:`SQLiteT3AdapterStateStore` persists
  each write in its own ``BEGIN IMMEDIATE`` transaction at the ordering point
  the discipline demands — intent BEFORE the native launch call, receipt +
  original ref BEFORE the start ACK, cursor only after a successful read —
  and its documented default file is a SIBLING of the Executive runtime's
  SQLite file in the same Executive-owned data directory (never the Executive
  file itself: the runtime pins its whole-file schema digest; see the store's
  docstring, which also records why the Executive store's
  ``launch_metadata_json`` is not a reusable attempt-scoped facility).  A cold-restart proof lives in
  ``tests/test_t3_adapter_durability.py``: a second adapter on the same store
  reattaches the SAME execution with the native launch count still one.
* Idempotency identity is ``(authenticated principal, request namespace,
  clientRequestId)``: the live proof (Rev 5 finding 1) showed the SAME
  ``clientRequestId`` under two different OAuth clients minting two
  DIFFERENT threads.  Every launch requires a port that ATTESTS its principal
  (``authenticated_namespace``) and runs under the principal-qualified
  namespace from :func:`t3_request_namespace`; the qualified namespace is
  persisted with the intent and receipt, replayed verbatim, and any reattach
  under a DIFFERENT or UNATTESTED principal is refused typed
  (:class:`T3NamespaceAttestationError`, re-auth required).

A3 audit rework (``integrations/t3/docs/AUDIT_T3_DURABLE_ADAPTER_OPUS_20261109.md``;
finding -> fix -> test table in ``integrations/t3/docs/LANE_T3_DIRECTOR_A.md``):

* exactly-once start across processes — the intent is CLAIMED atomically
  (``INSERT … ON CONFLICT DO NOTHING`` in ``BEGIN IMMEDIATE``); losers never
  launch (:class:`T3LaunchClaimConflictError`) and reattach to the winner;
  the clean-refusal rollback is claimant-conditional; receipts and results
  are write-once; the cursor is forward-only; a settled cancel is final;
* every store write checks existence, compare-and-set and rowcount inside
  its transaction and surfaces :class:`T3StateStoreError` (never raw
  sqlite3); a store failure after a successful launch is EFFECT_UNKNOWN;
* the store refuses every alias of the Executive file and any existing file
  with foreign schema objects BEFORE DDL; ``open_read_only`` is a ``mode=ro``
  read seam with no DDL;
* :class:`T3McpToolPort` is the reference live port: token-attested
  upstream namespace, upstream-derived echoes, lost-reply classification,
  exact-run interrupt and a dedicated terminal result read.

  Evidence scope: the rework is PROVEN_BY_TEST (fake ports/transports, real
  SQLite, real threads and processes).  The live receipts below predate it
  and were produced by the pre-rework adapter with the harness ports; no
  live T3 thread was launched through :class:`T3McpToolPort` (its wire
  shapes follow the donor schemas at the pin, read in source).

Honesty notes (Rev 5 D3):

* **PROVEN_LIVE for this adapter's own path** — one real native T3 execution
  + result return through this adapter has been observed and recorded
  (``integrations/t3/live_proof/t3_live_proof_receipt.json``: real
  ``t3_thread_launch`` with the binding-derived ``clientRequestId``,
  incremental-cursor reads to a terminal state, and ``collect_result``
  returning the native result "T3-PROOF-OK", 2026-11-09, environment
  m2studio / T3 Code 0.1.7).  The descriptor is therefore registered with
  ``implemented=True`` per the pin law in ``tests/test_worker_adapter.py``;
  registration still selects nothing — the adapter stays UNSELECTED until
  the incumbent runtime composes the real MCP port into its transport.
* **delegate_task lineage is never forged** — an external Hermes session
  is NOT a native T3 parent provider-session credential.  The launch
  envelope has no ``delegatedFrom`` field by construction; this adapter
  never claims native delegation lineage.

The adapter never speaks HTTP/MCP itself, holds no credentials, and spawns
no processes: the injected port is the only native seam.  Port contract:
implementations raise :class:`T3UnknownOutcomeError` when the native
outcome is unknown (lost reply); ANY other exception means the native call
definitively did not take effect (clean refusal).
"""
from __future__ import annotations

import base64
import dataclasses
import hashlib
import json
import os
import re
import sqlite3
import threading
import time
import types
import typing
import uuid
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol, runtime_checkable
from urllib.parse import quote

from control_plane.child_execution_contracts import ExecutionBinding, FanoutEnvelope
from control_plane.worker_adapter import AdapterBindingError
from control_plane.worker_execution_contract import (
    BinaryAttestation,
    CancelReceipt,
    CollectionReceipt,
    ProcessInspector,
    WorkerLaunchSpec,
    WorkerProcessRef,
    WorkerRecoveryBinding,
    WorkerResult,
    WorkerRunStatus,
    ValidationReceipt,
    worker_launch_spec_sha256,
)

T3_NATIVE_ADAPTER_ID = "t3-native"

# Schema constants for the closed T3 seam records.  The launch envelope
# deliberately carries NO ``delegatedFrom`` field: external Hermes is not a
# native T3 provider session, so delegation lineage is never forged.
T3_LAUNCH_ENVELOPE_SCHEMA = "mastermind.t3_thread_launch_envelope/v1"
T3_LAUNCH_RECEIPT_SCHEMA = "mastermind.t3_thread_launch_receipt/v1"
T3_THREAD_READ_SCHEMA = "mastermind.t3_thread_read/v1"
T3_INTERRUPT_OUTCOME_SCHEMA = "mastermind.t3_interrupt_outcome/v1"
T3_RESULT_REFERENCE_SCHEMA = "mastermind.t3_result_reference/v1"
T3_LAUNCH_INTENT_SCHEMA = "mastermind.t3_launch_intent/v1"
#: The adapter's pinned namespace PREFIX (also the v1.1 claim seam's
#: ``caller_namespace``).  The key inside it is derived per binding (never
#: caller-supplied, never regenerated on replay).  Upstream command identity
#: is ``(authenticated principal, namespace, key)`` — the live proof (Rev 5
#: finding 1) showed the SAME ``clientRequestId`` under two different OAuth
#: clients minting two DIFFERENT T3 threads — so every launch runs under the
#: PRINCIPAL-QUALIFIED namespace from :func:`t3_request_namespace` (the port
#: must attest its principal), and that qualified namespace is what gets
#: persisted with the intent and receipt and replayed verbatim.  Rows
#: persisted under this bare legacy value can be recovered only from a
#: retained ref (no native call); their native replay is refused.
T3_REQUEST_NAMESPACE = "mastermind.control_plane.t3_execution_adapter/v1"

#: Schema tag for the durable adapter-state table set (see
#: :class:`SQLiteT3AdapterStateStore`).
T3_ADAPTER_STATE_SCHEMA = "mastermind.t3_adapter_state/v1"

#: Documented default durable location for adapter state: a SIBLING SQLite
#: file in the Executive-owned data directory —
#: ``data/control_plane/t3_adapter_state.sqlite3`` (resolved from the
#: repository root exactly like ``RuntimeStore``'s default).  NOT a new
#: company database: it is adapter-private execution state (intent, receipt,
#: cursor, cancel ledger) keyed by the Executive run id, with no Job/Attempt/
#: claim semantics of its own.  Why NOT a table inside ``executive.sqlite3``:
#: the Executive runtime opens its file only if a normalized digest over the
#: ENTIRE ``sqlite_master`` equals the reviewed V7 DDL digest
#: (``control_plane/executive_runtime.py`` ``_normalized_schema_digest`` vs
#: ``_NORMALIZED_V7_SCHEMA_DIGEST``) — any foreign table makes the runtime
#: refuse to open with ``PersistenceError``.  Folding this table into the
#: Executive schema is a V8 migration on the shared runtime path (Director C /
#: integrator act), recorded as an open integration item, not a default.
#: The Executive durable store was also inspected for a reusable attempt-
#: scoped adapter-state facility and has none: ``attempts.launch_metadata_json``
#: is writable only inside the runtime's own guarded claim/dispatch
#: transactions and offers no write seam with the ordering discipline this
#: adapter needs (intent persisted BEFORE the native call, receipt + original
#: ref persisted BEFORE the ACK).
_T3_ADAPTER_STATE_DB_RELATIVE_PATH = (
    Path("data") / "control_plane" / "t3_adapter_state.sqlite3"
)
#: The Executive runtime's own file — the adapter store must NEVER default to it.
_EXECUTIVE_RUNTIME_DB_RELATIVE_PATH = Path("data") / "control_plane" / "executive.sqlite3"
_T3_ROOT = Path(__file__).resolve().parent.parent


def default_t3_adapter_state_path() -> Path:
    """The documented default SQLite file path for durable adapter state.

    A sibling file beside the Executive runtime store (see
    ``_T3_ADAPTER_STATE_DB_RELATIVE_PATH``), never the Executive file itself:
    the runtime pins its whole-file schema digest and would refuse to open.
    The runtime composition that selects the t3-native adapter decides
    whether to pass this default or an explicit path; constructing the
    adapter without a store stays non-durable (in-memory) and selects nothing.
    """
    return _T3_ROOT / _T3_ADAPTER_STATE_DB_RELATIVE_PATH


def executive_runtime_db_path() -> Path:
    """The Executive runtime's own SQLite file (for the never-default guard)."""
    return _T3_ROOT / _EXECUTIVE_RUNTIME_DB_RELATIVE_PATH


def t3_request_namespace(authenticated_principal: str | None) -> str:
    """The FULL idempotency namespace for an authenticated principal.

    Upstream command identity is the pair ``(requestNamespace, key)`` UNDER an
    authenticated client: two OAuth clients using the same fixed namespace and
    key are two DIFFERENT commands and mint two different threads (live proof,
    Rev 5 finding 1).  A principal-qualified namespace makes the full identity
    travel in the envelope itself: ``<legacy fixed namespace>:<principal>``.
    An empty/absent principal keeps the legacy fixed namespace byte-for-byte
    (ports that cannot report their authenticated principal).
    """
    principal = str(authenticated_principal or "").strip()
    if not principal:
        return T3_REQUEST_NAMESPACE
    return f"{T3_REQUEST_NAMESPACE}:{principal}"


def _namespace_principal(request_namespace: str) -> str:
    """The principal suffix of a namespace, or ``""`` for the legacy fixed one."""
    value = str(request_namespace or "")
    prefix = f"{T3_REQUEST_NAMESPACE}:"
    if value.startswith(prefix):
        return value[len(prefix):]
    return ""

_TERMINAL_STATES = frozenset({
    WorkerRunStatus.SUCCEEDED,
    WorkerRunStatus.FAILED,
    WorkerRunStatus.INVALID_RESULT,
    WorkerRunStatus.CANCELLED,
    WorkerRunStatus.TIMED_OUT,
})

#: Honest native-status mapping (verified T3 census vocabulary, lowercased).
_T3_STATUS_MAP: dict[str, WorkerRunStatus] = {
    "queued": WorkerRunStatus.STARTING,
    "starting": WorkerRunStatus.STARTING,
    "running": WorkerRunStatus.RUNNING,
    "in_progress": WorkerRunStatus.RUNNING,
    "succeeded": WorkerRunStatus.SUCCEEDED,
    "completed": WorkerRunStatus.SUCCEEDED,
    "failed": WorkerRunStatus.FAILED,
    "cancelled": WorkerRunStatus.CANCELLED,
    "canceled": WorkerRunStatus.CANCELLED,
    "timed_out": WorkerRunStatus.TIMED_OUT,
    "timeout": WorkerRunStatus.TIMED_OUT,
}

#: sha256 of empty bytes — T3 threads stream one event ledger, not separate
#: stdout/stderr files; the neutral CollectionReceipt digests the canonical
#: result reference instead (see ``_build_collection_receipt``).
_EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()

#: Identity-only binary placeholder.  T3 launches a native cloud thread, not
#: a local binary; these fields exist to satisfy the neutral
#: ``WorkerProcessRef`` floor and are NEVER used to spawn anything.
_T3_REMOTE_BINARY_PLACEHOLDER = BinaryAttestation(
    path="t3://remote/no-binary", real_path="t3://remote/no-binary",
    version="native-thread", sha256="0" * 64, team_identifier=None,
    size=0, device=0, inode=0, mode=0, uid=0, gid=0, mtime_ns=0,
)


class T3ExecutionAdapterError(AdapterBindingError):
    """T3-native adapter refused an operation; fail closed, never guess."""


class T3UnknownOutcomeError(T3ExecutionAdapterError):
    """Raised BY PORT implementations when the native outcome is unknown.

    Port contract: a lost reply / unknown outcome is EXACTLY this error.
    Any other exception from the port means the native call definitively
    did not take effect (a clean refusal).
    """


class T3LaunchEffectUnknownError(T3ExecutionAdapterError):
    """The native effect of a launch/replay is unknown; never auto-retried.

    Carries the deterministic ``client_request_id`` so recovery can replay
    the SAME command (same key + namespace) instead of minting a new one.
    """

    def __init__(self, message: str, *, client_request_id: str) -> None:
        super().__init__(message)
        self.client_request_id = client_request_id


class T3StateStoreError(T3ExecutionAdapterError):
    """The durable adapter-state store failed (I/O, lock, COMMIT, rowcount).

    Typed so callers never see a raw ``sqlite3`` error: a failed write is
    rolled back and the transaction is closed before this is raised.
    """


class T3LaunchClaimConflictError(T3ExecutionAdapterError):
    """Another claimant already owns this run's launch intent (audit #1).

    The atomic claim (``INSERT … ON CONFLICT DO NOTHING`` inside ``BEGIN
    IMMEDIATE``) admits exactly ONE claimant per run across processes and
    connections; every loser gets this error and NEVER calls the native
    launch.  ``reattach`` recovers the winner's execution.
    """

    def __init__(self, message: str, *, run_id: str) -> None:
        super().__init__(message)
        self.run_id = run_id


class T3NamespaceAttestationError(T3ExecutionAdapterError):
    """The port cannot attest the authenticated principal recovery needs.

    Typed re-auth-required label (NM-08): a launch needs an attested
    principal, and a replay/reattach whose persisted namespace names a
    principal needs the port to attest THAT principal.  Never a silent
    merge, never a skipped check.
    """

    code = "T3_REAUTH_REQUIRED"

    def __init__(self, message: str, *, reason: str) -> None:
        super().__init__(message)
        self.reason = reason


class T3BindingJoinDriftError(T3ExecutionAdapterError):
    """A v1.1 binding's t3 idempotency join drifted from the launch (C-P1)."""


class T3ResultLedgerConflictError(T3ExecutionAdapterError):
    """The write-once result ledger already holds a DIFFERENT reference."""


class T3PortRefusalError(T3ExecutionAdapterError):
    """A port's definitive clean refusal (the native call took no effect)."""


@dataclasses.dataclass(frozen=True)
class T3ThreadLaunchEnvelope:
    """Secret-free t3_thread_launch envelope (donor param census, adapted).

    ``workspace_ref`` is the source ref only; mapping it onto the donor's
    workspaceStrategy (worktree/existing_worktree/root) is the port's
    runtime policy, never the adapter's.
    """

    schema: str = T3_LAUNCH_ENVELOPE_SCHEMA
    request_namespace: str = ""
    client_request_id: str = ""
    run_id: str = ""
    worker_id: str = ""
    title: str = ""
    message: str = ""
    workspace_ref: str = ""
    model_selection: str = ""
    created_at: str = ""


@dataclasses.dataclass(frozen=True)
class T3ThreadLaunchReceipt:
    """What the native launch/replay returned for one thread."""

    schema: str = T3_LAUNCH_RECEIPT_SCHEMA
    thread_id: str = ""
    run_id: str = ""
    project_id: str = ""
    status: str = ""
    link: str = ""
    created_at: str = ""
    request_namespace: str = ""
    client_request_id: str = ""


@dataclasses.dataclass(frozen=True)
class T3ThreadReadResult:
    """One incremental exact-run read through the port."""

    schema: str = T3_THREAD_READ_SCHEMA
    thread_id: str = ""
    run_id: str = ""
    native_status: str = ""
    cursor: str = ""
    next_cursor: str = ""
    result_ref: str = ""
    result_payload: Mapping[str, Any] = dataclasses.field(default_factory=dict)
    started_at: str = ""
    finished_at: str = ""
    error: str | None = None
    has_more: bool = False


@dataclasses.dataclass(frozen=True)
class T3InterruptOutcome:
    """What the exact-run interrupt reported.

    ``settled`` is only honest when ``observed_native_status`` maps to a
    terminal state; the adapter reconciles before claiming settled.
    """

    schema: str = T3_INTERRUPT_OUTCOME_SCHEMA
    requested: bool = False
    settled: bool = False
    already_exited: bool = False
    observed_native_status: str = ""
    finished_at: str = ""


@dataclasses.dataclass(frozen=True)
class T3ResultReference:
    """Canonical, durable result reference ledgered BEFORE company acceptance."""

    schema: str = T3_RESULT_REFERENCE_SCHEMA
    run_id: str = ""
    thread_id: str = ""
    result_ref: str = ""
    native_status: str = ""
    recorded_at: str = ""


@dataclasses.dataclass(frozen=True)
class T3LaunchIntent:
    """The persisted launch intent, written BEFORE any native call."""

    schema: str = T3_LAUNCH_INTENT_SCHEMA
    run_id: str = ""
    client_request_id: str = ""
    request_namespace: str = ""
    adapter_id: str = ""
    envelope: T3ThreadLaunchEnvelope | None = None
    created_at: str = ""


@dataclasses.dataclass(frozen=True)
class T3CancelReport:
    """Honest requested-versus-settled view of one cancellation."""

    run_id: str
    reason: str
    requested: bool
    signal_sent: bool
    escalated_to_sigkill: bool
    already_exited: bool
    settled: bool
    requested_at: str
    settled_at: str | None
    settled_state: str | None
    finished_at: str


@dataclasses.dataclass
class _T3CancelLedgerEntry:
    reason: str
    requested: bool
    signal_sent: bool
    escalated_to_sigkill: bool
    already_exited: bool
    settled: bool
    requested_at: str
    settled_at: str | None = None
    settled_state: str | None = None
    finished_at: str = ""


# =============================================================================
# Durable adapter state (Rev 5 P0: cold-restart-safe execution durability)
# =============================================================================


@dataclasses.dataclass(frozen=True)
class T3AdapterRunState:
    """Every durable fact the adapter holds for one run, loaded as a unit.

    ``intent``/``binding``/``spec`` are persisted together BEFORE the native
    launch call; ``receipt``/``original_ref`` are persisted together BEFORE
    the start ACK; ``cursor`` advances only after a successful exact read;
    ``cancel`` and ``result_reference`` are persisted at their write points.
    A run with only an intent (no receipt) is the effect-unknown zone: start
    stays blocked and reattach replays the SAME key + namespace.
    """

    run_id: str
    intent: T3LaunchIntent | None = None
    receipt: T3ThreadLaunchReceipt | None = None
    original_ref: WorkerProcessRef | None = None
    binding: ExecutionBinding | None = None
    spec: WorkerLaunchSpec | None = None
    cursor: str = ""
    cancel: _T3CancelLedgerEntry | None = None
    result_reference: T3ResultReference | None = None
    #: ``worker_launch_spec_sha256`` of the caller's ORIGINAL spec object,
    #: computed at persist time (audit #5).  Authoritative for drift checks:
    #: a JSON round-trip may normalize values (``str``→``Path``) and so can
    #: never be trusted to re-hash identically.  ``""`` on legacy rows.
    spec_sha256: str = ""
    #: The winning claimant's opaque token (audit #1): the clean-refusal
    #: rollback and the receipt write are conditional on it.  ``""`` on
    #: legacy rows and on pre-durability adoptions.
    claim_token: str = ""


@runtime_checkable
class T3AdapterStateStore(Protocol):
    """Durable state seam for :class:`T3ExecutionAdapter`.

    One row per run; every method is synchronous and fail-closed (a store
    error surfaces typed, never a silent skip).  ``claim_launch_intent``
    must complete BEFORE the native launch call and ``put_launch_receipt``
    BEFORE the start ACK — the adapter's ordering discipline depends on the
    store actually persisting at call time, which is what the SQLite
    implementation does (one ``BEGIN IMMEDIATE`` transaction per write, every
    existence check INSIDE that transaction, every rowcount checked).

    Write semantics (audit #1/#8/#9/#10):

    * ``claim_launch_intent`` is an atomic INSERT-or-nothing: exactly one
      claimant per run, never an upsert of an existing intent;
    * ``clear_launch_attempt`` deletes only the CALLER's own claim and only
      while no receipt exists;
    * ``put_launch_receipt`` is write-once (an identical re-write is an
      idempotent no-op; a different execution is refused);
    * ``put_cursor`` never moves backwards and treats ``""`` as "no advance";
    * ``put_cancel_record`` never downgrades a settled record;
    * ``put_result_reference`` is write-once.
    """

    def load_run(self, run_id: str) -> T3AdapterRunState | None: ...
    def run_ids(self) -> tuple[str, ...]: ...
    def claim_launch_intent(
        self,
        intent: T3LaunchIntent,
        *,
        binding: ExecutionBinding,
        spec: WorkerLaunchSpec,
        claim_token: str,
    ) -> bool: ...
    def put_launch_intent(
        self,
        intent: T3LaunchIntent,
        *,
        binding: ExecutionBinding,
        spec: WorkerLaunchSpec,
    ) -> str: ...
    def clear_launch_attempt(self, run_id: str, *, claim_token: str) -> None: ...
    def put_launch_receipt(
        self,
        run_id: str,
        *,
        receipt: T3ThreadLaunchReceipt,
        original_ref: WorkerProcessRef,
        cursor: str = "",
        spec: WorkerLaunchSpec | None = None,
        claim_token: str | None = None,
    ) -> None: ...
    def put_cursor(self, run_id: str, cursor: str) -> str: ...
    def put_cancel_record(
        self, run_id: str, record: _T3CancelLedgerEntry
    ) -> _T3CancelLedgerEntry: ...
    def put_result_reference(self, reference: T3ResultReference) -> T3ResultReference: ...


# --- serialization (secret-free JSON round-trips of the seam records) -------
#
# Every value below is adapter-owned seam state: refs, receipts, cursors,
# ledger entries — never credentials.  Reconstruction is exact (dataclass
# equality holds across a persist/load round-trip), which is what reattach
# and the cold-restart tests rely on.


def _jsonable(value: Any) -> Any:
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: _jsonable(getattr(value, field.name))
            for field in dataclasses.fields(value)
        }
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    raise T3ExecutionAdapterError(
        f"t3 adapter state is not JSON-serializable: {type(value).__name__}"
    )


def _canonical_state_json(value: Any) -> str:
    return json.dumps(
        _jsonable(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )


def _require_object(raw: Any, name: str) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise T3ExecutionAdapterError(
            f"durable t3 adapter state for {name} is malformed"
        )
    return raw


def _t3_envelope_from_json(raw: Any) -> T3ThreadLaunchEnvelope:
    return T3ThreadLaunchEnvelope(**_require_object(raw, "launch envelope"))


def _t3_receipt_from_json(raw: Any) -> T3ThreadLaunchReceipt:
    return T3ThreadLaunchReceipt(**_require_object(raw, "launch receipt"))


def _t3_intent_from_json(raw: Any) -> T3LaunchIntent:
    payload = dict(_require_object(raw, "launch intent"))
    envelope = payload.pop("envelope", None)
    if envelope is not None:
        payload["envelope"] = _t3_envelope_from_json(envelope)
    return T3LaunchIntent(**payload)


def _t3_result_reference_from_json(raw: Any) -> T3ResultReference:
    return T3ResultReference(**_require_object(raw, "result reference"))


def _t3_cancel_from_json(raw: Any) -> _T3CancelLedgerEntry:
    return _T3CancelLedgerEntry(**_require_object(raw, "cancel record"))


def _t3_process_ref_from_json(raw: Any) -> WorkerProcessRef:
    payload = dict(_require_object(raw, "process ref"))
    binary = payload.pop("binary", None)
    if binary is not None:
        payload["binary"] = BinaryAttestation(
            **_require_object(binary, "binary attestation")
        )
    return WorkerProcessRef(**payload)


def _t3_binding_from_json(raw: Any) -> ExecutionBinding:
    payload = dict(_require_object(raw, "execution binding"))
    payload.pop("schema", None)  # init=False; recomputed by __post_init__
    envelope = payload.pop("declared_fanout_envelope", None)
    if envelope is not None:
        payload["declared_fanout_envelope"] = FanoutEnvelope(
            **_require_object(envelope, "fanout envelope")
        )
    refs = payload.pop("shared_quota_resource_refs", None)
    if refs is not None:
        payload["shared_quota_resource_refs"] = tuple(refs)
    return ExecutionBinding(**payload)


# WorkerLaunchSpec exact per-field reconstruction (audit #5).  Each field is
# rebuilt from its DECLARED type (``typing.get_type_hints``), never from a
# hand-maintained category list: ``allowed_artifact_paths`` is declared
# ``tuple[str, ...]`` and must load back as ``str`` (the old list loaded it
# as ``Path``, which re-normalized ``a/./b`` -> ``a/b`` and drifted the spec
# sha, so post-restart reattach was refused).  Unknown fields in durable
# rows raise (drift is caught loudly, never silently dropped); fields absent
# from a row fall back to dataclass defaults (a field added after the row
# was written).  The persisted ``spec_sha256`` of the caller's ORIGINAL
# object stays the authoritative drift check either way.
_SPEC_FIELD_NAMES = frozenset(
    field.name for field in dataclasses.fields(WorkerLaunchSpec)
)


def _spec_field_types() -> dict[str, Any]:
    return typing.get_type_hints(WorkerLaunchSpec)


def _decode_typed(value: Any, annotation: Any, name: str) -> Any:
    """Rebuild one JSON value as exactly its declared annotation.

    Only ``Path`` needs reconstruction (JSON has no path type); tuples are
    rebuilt element-wise by their declared item type; every scalar keeps its
    JSON type unchanged (an ``int`` passed for a ``float`` field stays an
    ``int`` so the spec hash is reproduced, never coerced).
    """
    if value is None:
        return None
    origin = typing.get_origin(annotation)
    args = typing.get_args(annotation)
    if origin in (typing.Union, types.UnionType):
        members = [arg for arg in args if arg is not type(None)]
        if len(members) != 1:
            raise T3ExecutionAdapterError(
                f"durable t3 launch spec field {name!r} has an ambiguous type"
            )
        return _decode_typed(value, members[0], name)
    if annotation is Path:
        if not isinstance(value, str):
            raise T3ExecutionAdapterError(
                f"durable t3 launch spec field {name!r} is not a path string"
            )
        return Path(value)
    if origin is tuple:
        if not isinstance(value, list):
            raise T3ExecutionAdapterError(
                f"durable t3 launch spec field {name!r} is not a list"
            )
        item_type = args[0] if args else Any
        return tuple(_decode_typed(item, item_type, name) for item in value)
    return value


def _t3_spec_from_json(raw: Any) -> WorkerLaunchSpec:
    payload = dict(_require_object(raw, "launch spec"))
    unknown = set(payload) - _SPEC_FIELD_NAMES
    if unknown:
        raise T3ExecutionAdapterError(
            f"durable t3 launch spec carries unknown fields: {sorted(unknown)}"
        )
    types = _spec_field_types()
    kwargs = {
        name: _decode_typed(value, types[name], name)
        for name, value in payload.items()
    }
    try:
        return WorkerLaunchSpec(**kwargs)
    except TypeError as exc:
        raise T3ExecutionAdapterError(
            f"durable t3 launch spec is malformed: {exc}"
        ) from exc


def _row_to_run_state(row: Mapping[str, Any]) -> T3AdapterRunState:
    def loaded(column: str):
        value = row[column]
        return json.loads(value) if value else None

    run_id = str(row["run_id"])
    cursor = row["cursor_text"] or ""
    intent = _t3_intent_from_json(loaded("intent_json")) if loaded("intent_json") else None
    receipt = (
        _t3_receipt_from_json(loaded("receipt_json")) if loaded("receipt_json") else None
    )
    original_ref = (
        _t3_process_ref_from_json(loaded("original_ref_json"))
        if loaded("original_ref_json")
        else None
    )
    binding = _t3_binding_from_json(loaded("binding_json")) if loaded("binding_json") else None
    spec = _t3_spec_from_json(loaded("spec_json")) if loaded("spec_json") else None
    cancel = _t3_cancel_from_json(loaded("cancel_json")) if loaded("cancel_json") else None
    result_reference = (
        _t3_result_reference_from_json(loaded("result_ref_json"))
        if loaded("result_ref_json")
        else None
    )
    keys = set(row.keys()) if hasattr(row, "keys") else set(row)
    spec_sha256 = (row["spec_sha256"] or "") if "spec_sha256" in keys else ""
    claim_token = (row["claim_token"] or "") if "claim_token" in keys else ""
    return T3AdapterRunState(
        run_id=run_id,
        intent=intent,
        receipt=receipt,
        original_ref=original_ref,
        binding=binding,
        spec=spec,
        cursor=cursor,
        cancel=cancel,
        result_reference=result_reference,
        spec_sha256=str(spec_sha256),
        claim_token=str(claim_token),
    )


# --- shared write-merge rules (both stores apply the SAME semantics) --------

_DECIMAL_CURSOR = re.compile(r"[0-9]+")


def _now_ms() -> int:
    """Wall-clock milliseconds for ``updated_ms`` (never a monotonic clock:
    the value is compared across processes and restarts)."""
    return time.time_ns() // 1_000_000


def _require_claim_token(claim_token: Any) -> str:
    if not isinstance(claim_token, str) or not claim_token.strip():
        raise T3ExecutionAdapterError("a launch claim requires a non-empty claim token")
    return claim_token


def _cursor_rank(cursor: str) -> int | None:
    return int(cursor) if _DECIMAL_CURSOR.fullmatch(cursor) else None


def _merge_cursor(current: str, proposed: Any) -> str:
    """The forward-only cursor rule (audit #8 / NM-03).

    ``""`` is "no advance", never a reset.  Decimal positions (T3's
    ``afterPosition``/``nextPosition``) only ever move forward, so a slower
    concurrent reader's stale ``next_cursor`` can never rewind a faster
    one's.  A cursor that changes KIND (decimal <-> opaque) is refused.
    Two opaque cursors cannot be ordered: the newest successful read wins
    (documented; T3 at the pin only issues decimal positions).
    """
    proposed = str(proposed or "")
    current = str(current or "")
    if not proposed or proposed == current:
        return current
    if not current:
        return proposed
    current_rank, proposed_rank = _cursor_rank(current), _cursor_rank(proposed)
    if current_rank is not None and proposed_rank is not None:
        return proposed if proposed_rank > current_rank else current
    if (current_rank is None) != (proposed_rank is None):
        raise T3StateStoreError(
            f"refusing a cursor that changes kind ({current!r} -> {proposed!r})"
        )
    return proposed


def _merge_cancel(
    existing: _T3CancelLedgerEntry | None, proposed: _T3CancelLedgerEntry
) -> _T3CancelLedgerEntry:
    """Requested-versus-settled ledger merge (audit #9).

    A settled record is final: a later write (e.g. a second ``cancel()``
    whose interrupt outcome shows the run still RUNNING) never downgrades
    it.  An unsettled record keeps its FIRST request (reason + time) and
    may only move forward to settled.
    """
    if existing is None:
        return proposed
    if existing.settled:
        return existing
    return dataclasses.replace(
        proposed,
        reason=existing.reason,
        requested=existing.requested or proposed.requested,
        signal_sent=existing.signal_sent or proposed.signal_sent,
        requested_at=existing.requested_at or proposed.requested_at,
    )


def _result_identity(reference: T3ResultReference) -> tuple[str, str, str, str]:
    return (
        reference.run_id, reference.thread_id, reference.result_ref,
        reference.native_status,
    )


def _merge_result(
    existing: T3ResultReference | None, proposed: T3ResultReference
) -> T3ResultReference:
    """Write-once result ledger (audit #10): identical re-records are no-ops
    (the FIRST ``recorded_at`` stands); a different reference is refused."""
    if existing is None:
        return proposed
    if _result_identity(existing) == _result_identity(proposed):
        return existing
    raise T3ResultLedgerConflictError(
        f"result ledger for run {proposed.run_id!r} already holds "
        f"{existing.result_ref!r} ({existing.native_status!r}); refusing to "
        f"overwrite it with {proposed.result_ref!r} ({proposed.native_status!r})"
    )


def _receipt_is_same_execution(
    existing_receipt: T3ThreadLaunchReceipt | None,
    existing_ref: WorkerProcessRef | None,
    receipt: T3ThreadLaunchReceipt,
    original_ref: WorkerProcessRef,
) -> bool:
    return (
        existing_receipt is not None
        and existing_ref is not None
        and existing_receipt.thread_id == receipt.thread_id
        and existing_receipt.run_id == receipt.run_id
        and existing_ref == original_ref
    )


def _write_once_receipt_conflict(run_id: str) -> T3ExecutionAdapterError:
    return T3ExecutionAdapterError(
        f"a DIFFERENT native receipt is already persisted for run {run_id!r}; "
        "receipts are write-once — refusing to swap executions"
    )


def _missing_row(operation: str, run_id: str) -> T3ExecutionAdapterError:
    return T3ExecutionAdapterError(
        f"{operation} requires a persisted launch intent for run {run_id!r} first"
    )


class InMemoryT3AdapterStateStore:
    """Non-durable in-memory store: the test double and the default fallback.

    Constructing a :class:`T3ExecutionAdapter` without a store uses this, so
    the adapter's own-path behavior is unchanged for callers that have not
    composed a durable store yet (selection is still a deployment act).  It
    satisfies the same protocol AND the same write semantics as the SQLite
    store (atomic claim, claimant-conditional clear, write-once receipt and
    result, forward-only cursor, never-downgraded cancel), under one lock.
    It is NOT durable: process death loses everything, and every durability
    property is only as strong as the store actually used.
    """

    def __init__(self) -> None:
        self._runs: dict[str, dict[str, Any]] = {}
        self._lock = threading.RLock()

    @staticmethod
    def _empty_row() -> dict[str, Any]:
        return {
            "intent_json": None, "receipt_json": None,
            "original_ref_json": None, "binding_json": None,
            "spec_json": None, "cursor_text": "",
            "cancel_json": None, "result_ref_json": None,
            "spec_sha256": None, "claim_token": None,
        }

    def load_run(self, run_id: str) -> T3AdapterRunState | None:
        with self._lock:
            row = self._runs.get(str(run_id))
            if row is None:
                return None
            # Values are stored pre-serialized so the in-memory double
            # exercises the same reconstruction path as the SQLite store.
            return _row_to_run_state({"run_id": str(run_id), **row})

    def run_ids(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(self._runs)

    def claim_launch_intent(
        self,
        intent: T3LaunchIntent,
        *,
        binding: ExecutionBinding,
        spec: WorkerLaunchSpec,
        claim_token: str,
    ) -> bool:
        token = _require_claim_token(claim_token)
        row = self._empty_row()
        row["intent_json"] = _canonical_state_json(intent)
        row["binding_json"] = _canonical_state_json(binding)
        row["spec_json"] = _canonical_state_json(spec)
        row["spec_sha256"] = worker_launch_spec_sha256(spec)
        row["claim_token"] = token
        with self._lock:
            if intent.run_id in self._runs:
                return False
            self._runs[intent.run_id] = row
            return True

    def put_launch_intent(
        self,
        intent: T3LaunchIntent,
        *,
        binding: ExecutionBinding,
        spec: WorkerLaunchSpec,
    ) -> str:
        token = uuid.uuid4().hex
        if not self.claim_launch_intent(
            intent, binding=binding, spec=spec, claim_token=token
        ):
            raise T3LaunchClaimConflictError(
                f"run {intent.run_id!r} already has a persisted launch intent; "
                "intents are claimed once, never upserted",
                run_id=intent.run_id,
            )
        return token

    def clear_launch_attempt(self, run_id: str, *, claim_token: str) -> None:
        token = _require_claim_token(claim_token)
        with self._lock:
            row = self._runs.get(str(run_id))
            if row is None:
                return
            if row.get("receipt_json") or row.get("original_ref_json"):
                raise T3ExecutionAdapterError(
                    f"refusing to clear launch attempt for run {run_id!r}: a "
                    "native receipt is already persisted (possible effect)"
                )
            if (row.get("claim_token") or "") != token:
                raise T3LaunchClaimConflictError(
                    f"refusing to clear run {run_id!r}: the launch intent "
                    "belongs to another claimant",
                    run_id=str(run_id),
                )
            del self._runs[str(run_id)]

    def put_launch_receipt(
        self,
        run_id: str,
        *,
        receipt: T3ThreadLaunchReceipt,
        original_ref: WorkerProcessRef,
        cursor: str = "",
        spec: WorkerLaunchSpec | None = None,
        claim_token: str | None = None,
    ) -> None:
        receipt_json = _canonical_state_json(receipt)
        ref_json = _canonical_state_json(original_ref)
        spec_json = _canonical_state_json(spec) if spec is not None else None
        spec_sha = worker_launch_spec_sha256(spec) if spec is not None else None
        with self._lock:
            row = self._runs.get(str(run_id))
            if row is None:
                if claim_token is not None:
                    raise T3LaunchClaimConflictError(
                        f"the claimed launch intent for run {run_id!r} vanished "
                        "before its receipt was persisted",
                        run_id=str(run_id),
                    )
                # Adoption of a PRE-durability recovery binding (no row).
                row = self._empty_row()
                row.update(
                    receipt_json=receipt_json, original_ref_json=ref_json,
                    spec_json=spec_json, spec_sha256=spec_sha,
                    cursor_text=str(cursor or ""),
                )
                self._runs[str(run_id)] = row
                return
            if claim_token is not None and (row.get("claim_token") or "") != claim_token:
                raise T3LaunchClaimConflictError(
                    f"run {run_id!r}'s launch intent belongs to another claimant",
                    run_id=str(run_id),
                )
            if row.get("receipt_json") or row.get("original_ref_json"):
                state = _row_to_run_state({"run_id": str(run_id), **row})
                if _receipt_is_same_execution(
                    state.receipt, state.original_ref, receipt, original_ref
                ):
                    return
                raise _write_once_receipt_conflict(str(run_id))
            row["receipt_json"] = receipt_json
            row["original_ref_json"] = ref_json
            if row.get("spec_json") is None and spec_json is not None:
                row["spec_json"] = spec_json
                row["spec_sha256"] = spec_sha

    def put_cursor(self, run_id: str, cursor: str) -> str:
        with self._lock:
            row = self._require_row(run_id, "put_cursor")
            effective = _merge_cursor(row.get("cursor_text") or "", cursor)
            row["cursor_text"] = effective
            return effective

    def put_cancel_record(
        self, run_id: str, record: _T3CancelLedgerEntry
    ) -> _T3CancelLedgerEntry:
        with self._lock:
            row = self._require_row(run_id, "put_cancel_record")
            existing = (
                _t3_cancel_from_json(json.loads(row["cancel_json"]))
                if row.get("cancel_json") else None
            )
            effective = _merge_cancel(existing, record)
            row["cancel_json"] = _canonical_state_json(effective)
            return effective

    def put_result_reference(self, reference: T3ResultReference) -> T3ResultReference:
        with self._lock:
            row = self._require_row(reference.run_id, "put_result_reference")
            existing = (
                _t3_result_reference_from_json(json.loads(row["result_ref_json"]))
                if row.get("result_ref_json") else None
            )
            effective = _merge_result(existing, reference)
            row["result_ref_json"] = _canonical_state_json(effective)
            return effective

    def _require_row(self, run_id: str, operation: str) -> dict[str, Any]:
        row = self._runs.get(str(run_id))
        if row is None:
            raise _missing_row(operation, str(run_id))
        return row


# --- SQLite store ------------------------------------------------------------

_T3_STATE_TABLE = "t3_adapter_runs"
_T3_STATE_DDL = (
    "CREATE TABLE IF NOT EXISTS t3_adapter_runs ("
    " run_id TEXT PRIMARY KEY,"
    " intent_json TEXT,"
    " receipt_json TEXT,"
    " original_ref_json TEXT,"
    " binding_json TEXT,"
    " spec_json TEXT,"
    " cursor_text TEXT NOT NULL DEFAULT '',"
    " cancel_json TEXT,"
    " result_ref_json TEXT,"
    " schema_version TEXT NOT NULL DEFAULT 'mastermind.t3_adapter_state/v1',"
    " updated_ms INTEGER NOT NULL,"
    " spec_sha256 TEXT,"
    " claim_token TEXT"
    ")"
)
#: Nullable columns added after v1 shipped (older files gain them in place;
#: readers of the original columns — e.g. the fleet projection — are
#: unaffected).
_T3_STATE_ADDED_COLUMNS = (("spec_sha256", "TEXT"), ("claim_token", "TEXT"))


def _schema_objects(connection: sqlite3.Connection) -> set[str]:
    return {
        str(row[0])
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type IN ('table','view','trigger')"
        )
        if not str(row[0]).startswith("sqlite_")
    }


def _refuse_foreign_objects(names: set[str], path: Path) -> None:
    foreign = sorted(name for name in names if name != _T3_STATE_TABLE)
    if foreign:
        raise T3ExecutionAdapterError(
            f"refusing to open {path.name!r} as t3 adapter state: the file "
            f"already holds foreign schema objects {foreign} (another owner's "
            "database — e.g. the Executive runtime's, whose whole-file schema "
            "digest is pinned); no DDL was run"
        )


def _refuse_executive_runtime_file(path: Path) -> Path:
    """Resolve ``path`` and refuse every alias of the Executive runtime file.

    Audit #6: a name-only, case-sensitive compare let ``Executive.sqlite3``
    on case-insensitive APFS and a symlink alias open the real Executive
    file and run DDL.  Refused here: any path whose given OR resolved name
    casefolds to ``executive.sqlite3``; any path whose resolved string
    casefolds to the resolved Executive path; any existing file that is the
    same inode as the Executive file (``samefile`` / ``(st_dev, st_ino)``,
    which also catches hard links).
    """
    candidate = Path(path).expanduser()
    try:
        resolved = candidate.resolve(strict=False)
    except (OSError, RuntimeError) as exc:
        raise T3ExecutionAdapterError(
            f"t3 adapter state path cannot be resolved: {exc}"
        ) from exc
    executive = executive_runtime_db_path()
    try:
        executive_resolved = executive.resolve(strict=False)
    except (OSError, RuntimeError):
        executive_resolved = executive
    refusal = T3ExecutionAdapterError(
        "t3 adapter state store must not live inside the Executive runtime's "
        "own SQLite file (its reviewed schema digest is pinned); use the "
        "sibling default path"
    )
    executive_name = _EXECUTIVE_RUNTIME_DB_RELATIVE_PATH.name.casefold()
    if (
        candidate.name.casefold() == executive_name
        or resolved.name.casefold() == executive_name
        or str(resolved).casefold() == str(executive_resolved).casefold()
    ):
        raise refusal
    if resolved.exists() and executive_resolved.exists():
        try:
            same = os.path.samefile(resolved, executive_resolved)
            left, right = os.stat(resolved), os.stat(executive_resolved)
        except OSError as exc:
            raise T3ExecutionAdapterError(
                f"t3 adapter state path identity cannot be verified: {exc}"
            ) from exc
        if same or (left.st_dev, left.st_ino) == (right.st_dev, right.st_ino):
            raise refusal
    return resolved


class SQLiteT3AdapterStateStore:
    """SQLite-backed durable adapter state (the ``WorkspaceLeaseStore`` pattern).

    One row per run in the ``t3_adapter_runs`` table: sqlite3,
    ``isolation_level=None``, explicit ``BEGIN IMMEDIATE`` per write,
    ``row_factory=sqlite3.Row``.  The DOCUMENTED DEFAULT file path is the
    sibling file ``data/control_plane/t3_adapter_state.sqlite3`` in the
    Executive-owned data directory (see ``_T3_ADAPTER_STATE_DB_RELATIVE_PATH``
    for why it must not be the Executive runtime's own file).  The connection
    does not switch the journal mode (whole-file property; left to the file's
    owner — ``busy_timeout`` is connection-local and safe).

    Opening is fail-closed (audit #6): every alias of the Executive runtime
    file is refused (casefolded names, resolved paths, inode identity), and
    an existing file holding ANY foreign schema object is refused BEFORE any
    DDL runs — the check and the DDL share one ``BEGIN IMMEDIATE``.

    Every write runs its existence check, its compare-and-set and its
    rowcount check INSIDE one ``BEGIN IMMEDIATE`` transaction (audit #11); a
    failed statement or COMMIT is rolled back, the transaction is closed,
    and a typed :class:`T3StateStoreError` surfaces (never a raw sqlite3
    error).  :meth:`open_read_only` opens an existing file with a
    ``mode=ro`` URI and runs no DDL at all.
    """

    def __init__(self, path: str | Path) -> None:
        if not str(path).strip():
            raise T3ExecutionAdapterError("t3 adapter state store path is empty")
        self.path = Path(path)
        resolved = _refuse_executive_runtime_file(self.path)
        self._read_only = False
        self._lock = threading.RLock()
        resolved.parent.mkdir(parents=True, exist_ok=True)
        try:
            connection = sqlite3.connect(
                str(resolved), timeout=30.0, isolation_level=None,
                check_same_thread=False,
            )
        except sqlite3.Error as exc:
            raise T3StateStoreError(
                f"t3 adapter state store cannot be opened: {exc}"
            ) from exc
        connection.row_factory = sqlite3.Row
        self._connection = connection
        try:
            connection.execute("PRAGMA busy_timeout=10000")
            self._transaction(lambda conn: self._ensure_schema(conn, resolved))
        except BaseException:
            connection.close()
            raise

    @classmethod
    def open_read_only(cls, path: str | Path) -> "SQLiteT3AdapterStateStore":
        """Open an EXISTING adapter-state file read-only (``mode=ro``, no DDL).

        The read API (``load_run``/``run_ids``) works; every write method is
        refused typed.  The same Executive-file guard applies, a missing
        file or a file without the adapter table is a typed refusal, and a
        file holding foreign schema objects is refused.
        """
        if not str(path).strip():
            raise T3ExecutionAdapterError("t3 adapter state store path is empty")
        file_path = Path(path)
        resolved = _refuse_executive_runtime_file(file_path)
        if not resolved.is_file():
            raise T3StateStoreError(
                f"no t3 adapter state file at {file_path.name!r} to open read-only"
            )
        try:
            connection = sqlite3.connect(
                f"file:{quote(str(resolved))}?mode=ro", uri=True, timeout=5.0,
                isolation_level=None, check_same_thread=False,
            )
        except sqlite3.Error as exc:
            raise T3StateStoreError(
                f"t3 adapter state file cannot be opened read-only: {exc}"
            ) from exc
        try:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA query_only=ON")
            names = _schema_objects(connection)
            _refuse_foreign_objects(names, file_path)
            if _T3_STATE_TABLE not in names:
                raise T3StateStoreError(
                    f"{file_path.name!r} holds no t3 adapter state table"
                )
        except sqlite3.Error as exc:
            connection.close()
            raise T3StateStoreError(
                f"t3 adapter state file is unreadable: {exc}"
            ) from exc
        except BaseException:
            connection.close()
            raise
        store = cls.__new__(cls)
        store.path = file_path
        store._read_only = True
        store._lock = threading.RLock()
        store._connection = connection
        return store

    @property
    def read_only(self) -> bool:
        return self._read_only

    def close(self) -> None:
        self._connection.close()

    # -- internals -----------------------------------------------------------

    @staticmethod
    def _ensure_schema(connection: sqlite3.Connection, path: Path) -> None:
        # Foreign-object refusal BEFORE any DDL, inside the same IMMEDIATE
        # transaction (no window between the check and the CREATE).
        _refuse_foreign_objects(_schema_objects(connection), path)
        connection.execute(_T3_STATE_DDL)
        columns = {
            str(row[1])
            for row in connection.execute("PRAGMA table_info(t3_adapter_runs)")
        }
        for name, declared in _T3_STATE_ADDED_COLUMNS:
            if name not in columns:
                connection.execute(
                    f"ALTER TABLE t3_adapter_runs ADD COLUMN {name} {declared}"
                )

    def _require_writable(self, operation: str) -> None:
        if self._read_only:
            raise T3ExecutionAdapterError(
                f"{operation} refused: this t3 adapter state store was opened "
                "read-only"
            )

    def _rollback_quietly(self) -> None:
        try:
            if self._connection.in_transaction:
                self._connection.execute("ROLLBACK")
        except sqlite3.Error:
            pass

    def _transaction(self, operation: Callable[[sqlite3.Connection], Any]) -> Any:
        """Run ``operation`` in ONE ``BEGIN IMMEDIATE`` transaction.

        Any failure — in the statement OR the COMMIT — rolls back and
        closes the transaction before a typed error surfaces, so the next
        write never inherits a half-open transaction (audit #11).
        """
        with self._lock:
            connection = self._connection
            try:
                connection.execute("BEGIN IMMEDIATE")
            except sqlite3.Error as exc:
                self._rollback_quietly()
                raise T3StateStoreError(
                    f"t3 adapter state transaction could not begin: {exc}"
                ) from exc
            try:
                result = operation(connection)
            except sqlite3.Error as exc:
                self._rollback_quietly()
                raise T3StateStoreError(
                    f"t3 adapter state write failed: {exc}"
                ) from exc
            except BaseException:
                self._rollback_quietly()
                raise
            try:
                connection.execute("COMMIT")
            except BaseException as exc:
                self._rollback_quietly()
                if isinstance(exc, sqlite3.Error):
                    raise T3StateStoreError(
                        f"t3 adapter state COMMIT failed (rolled back): {exc}"
                    ) from exc
                raise
            return result

    def _read(self, sql: str, params: tuple) -> list[sqlite3.Row]:
        with self._lock:
            try:
                return self._connection.execute(sql, params).fetchall()
            except sqlite3.Error as exc:
                raise T3StateStoreError(
                    f"t3 adapter state read failed: {exc}"
                ) from exc

    @staticmethod
    def _select_run(connection: sqlite3.Connection, run_id: str) -> sqlite3.Row | None:
        return connection.execute(
            "SELECT * FROM t3_adapter_runs WHERE run_id=?", (str(run_id),)
        ).fetchone()

    @staticmethod
    def _expect_one(cursor: sqlite3.Cursor, operation: str) -> None:
        if cursor.rowcount != 1:
            raise T3StateStoreError(
                f"{operation} changed {cursor.rowcount} rows (expected exactly 1)"
            )

    # -- protocol surface ----------------------------------------------------

    def load_run(self, run_id: str) -> T3AdapterRunState | None:
        rows = self._read(
            "SELECT * FROM t3_adapter_runs WHERE run_id=?", (str(run_id),)
        )
        return _row_to_run_state(rows[0]) if rows else None

    def run_ids(self) -> tuple[str, ...]:
        rows = self._read("SELECT run_id FROM t3_adapter_runs ORDER BY rowid", ())
        return tuple(row["run_id"] for row in rows)

    def claim_launch_intent(
        self,
        intent: T3LaunchIntent,
        *,
        binding: ExecutionBinding,
        spec: WorkerLaunchSpec,
        claim_token: str,
    ) -> bool:
        """Atomically claim the run: exactly one claimant across processes.

        ``INSERT … ON CONFLICT(run_id) DO NOTHING`` inside ``BEGIN
        IMMEDIATE``; ``changes() == 0`` means another claimant (or an older
        attempt) owns the run and the caller must NOT launch.  An existing
        intent is never upserted (audit #1).
        """
        self._require_writable("claim_launch_intent")
        token = _require_claim_token(claim_token)
        values = (
            intent.run_id,
            _canonical_state_json(intent),
            _canonical_state_json(binding),
            _canonical_state_json(spec),
            worker_launch_spec_sha256(spec),
            token,
            _now_ms(),
        )

        def claim(connection: sqlite3.Connection) -> bool:
            connection.execute(
                "INSERT INTO t3_adapter_runs"
                " (run_id, intent_json, binding_json, spec_json, spec_sha256,"
                "  claim_token, cursor_text, schema_version, updated_ms)"
                " VALUES (?,?,?,?,?,?,'','mastermind.t3_adapter_state/v1',?)"
                " ON CONFLICT(run_id) DO NOTHING",
                values,
            )
            changes = int(connection.execute("SELECT changes()").fetchone()[0])
            if changes not in (0, 1):
                raise T3StateStoreError(
                    f"launch claim changed {changes} rows (expected 0 or 1)"
                )
            return changes == 1

        return bool(self._transaction(claim))

    def put_launch_intent(
        self,
        intent: T3LaunchIntent,
        *,
        binding: ExecutionBinding,
        spec: WorkerLaunchSpec,
    ) -> str:
        """Claim with a fresh token; refuse (never upsert) an existing run."""
        token = uuid.uuid4().hex
        if not self.claim_launch_intent(
            intent, binding=binding, spec=spec, claim_token=token
        ):
            raise T3LaunchClaimConflictError(
                f"run {intent.run_id!r} already has a persisted launch intent; "
                "intents are claimed once, never upserted",
                run_id=intent.run_id,
            )
        return token

    def clear_launch_attempt(self, run_id: str, *, claim_token: str) -> None:
        """Roll back the CALLER's own claim while no receipt exists.

        A persisted receipt means a possible native effect and is immutable;
        an intent claimed by someone else is never deleted (audit #1).
        """
        self._require_writable("clear_launch_attempt")
        token = _require_claim_token(claim_token)

        def clear(connection: sqlite3.Connection) -> None:
            row = self._select_run(connection, run_id)
            if row is None:
                return
            if row["receipt_json"] or row["original_ref_json"]:
                raise T3ExecutionAdapterError(
                    f"refusing to clear launch attempt for run {run_id!r}: a "
                    "native receipt is already persisted (possible effect)"
                )
            if (row["claim_token"] or "") != token:
                raise T3LaunchClaimConflictError(
                    f"refusing to clear run {run_id!r}: the launch intent "
                    "belongs to another claimant",
                    run_id=str(run_id),
                )
            self._expect_one(
                connection.execute(
                    "DELETE FROM t3_adapter_runs WHERE run_id=? AND claim_token=?"
                    " AND receipt_json IS NULL AND original_ref_json IS NULL",
                    (str(run_id), token),
                ),
                "clear_launch_attempt",
            )

        self._transaction(clear)

    def put_launch_receipt(
        self,
        run_id: str,
        *,
        receipt: T3ThreadLaunchReceipt,
        original_ref: WorkerProcessRef,
        cursor: str = "",
        spec: WorkerLaunchSpec | None = None,
        claim_token: str | None = None,
    ) -> None:
        """Persist the receipt + original ref, WRITE-ONCE.

        With ``claim_token`` (the start ACK path) the row must still be the
        caller's claim.  Without one (recovery adoption) a missing row is
        created (pre-durability binding) and an intent row gains the
        receipt.  An identical re-write is an idempotent no-op (two
        recoverers adopting the same original thread); a DIFFERENT execution
        is refused — never last-writer-wins.
        """
        self._require_writable("put_launch_receipt")
        receipt_json = _canonical_state_json(receipt)
        ref_json = _canonical_state_json(original_ref)
        spec_json = _canonical_state_json(spec) if spec is not None else None
        spec_sha = worker_launch_spec_sha256(spec) if spec is not None else None

        def write(connection: sqlite3.Connection) -> None:
            row = self._select_run(connection, run_id)
            now_ms = _now_ms()
            if row is None:
                if claim_token is not None:
                    raise T3LaunchClaimConflictError(
                        f"the claimed launch intent for run {run_id!r} vanished "
                        "before its receipt was persisted",
                        run_id=str(run_id),
                    )
                connection.execute(
                    "INSERT INTO t3_adapter_runs"
                    " (run_id, receipt_json, original_ref_json, spec_json,"
                    "  spec_sha256, cursor_text, schema_version, updated_ms)"
                    " VALUES (?,?,?,?,?,?,'mastermind.t3_adapter_state/v1',?)"
                    " ON CONFLICT(run_id) DO NOTHING",
                    (str(run_id), receipt_json, ref_json, spec_json, spec_sha,
                     str(cursor or ""), now_ms),
                )
                if int(connection.execute("SELECT changes()").fetchone()[0]) != 1:
                    raise T3StateStoreError(
                        f"receipt adoption for run {run_id!r} inserted no row"
                    )
                return
            if claim_token is not None and (row["claim_token"] or "") != claim_token:
                raise T3LaunchClaimConflictError(
                    f"run {run_id!r}'s launch intent belongs to another claimant",
                    run_id=str(run_id),
                )
            if row["receipt_json"] or row["original_ref_json"]:
                state = _row_to_run_state(row)
                if _receipt_is_same_execution(
                    state.receipt, state.original_ref, receipt, original_ref
                ):
                    return
                raise _write_once_receipt_conflict(str(run_id))
            self._expect_one(
                connection.execute(
                    "UPDATE t3_adapter_runs SET receipt_json=?, original_ref_json=?,"
                    " spec_json=COALESCE(spec_json, ?),"
                    " spec_sha256=CASE WHEN spec_json IS NULL THEN ? ELSE spec_sha256 END,"
                    " updated_ms=?"
                    " WHERE run_id=? AND receipt_json IS NULL"
                    " AND original_ref_json IS NULL",
                    (receipt_json, ref_json, spec_json, spec_sha, now_ms, str(run_id)),
                ),
                "put_launch_receipt",
            )

        self._transaction(write)

    def put_cursor(self, run_id: str, cursor: str) -> str:
        """Advance the cursor forward-only (audit #8); returns the effective one."""
        self._require_writable("put_cursor")

        def write(connection: sqlite3.Connection) -> str:
            row = self._select_run(connection, run_id)
            if row is None:
                raise _missing_row("put_cursor", str(run_id))
            current = row["cursor_text"] or ""
            effective = _merge_cursor(current, cursor)
            if effective != current:
                self._expect_one(
                    connection.execute(
                        "UPDATE t3_adapter_runs SET cursor_text=?, updated_ms=?"
                        " WHERE run_id=? AND cursor_text=?",
                        (effective, _now_ms(), str(run_id), current),
                    ),
                    "put_cursor",
                )
            return effective

        return str(self._transaction(write))

    def put_cancel_record(
        self, run_id: str, record: _T3CancelLedgerEntry
    ) -> _T3CancelLedgerEntry:
        """Merge into the cancel ledger; a settled record is final (audit #9)."""
        self._require_writable("put_cancel_record")

        def write(connection: sqlite3.Connection) -> _T3CancelLedgerEntry:
            row = self._select_run(connection, run_id)
            if row is None:
                raise _missing_row("put_cancel_record", str(run_id))
            existing = (
                _t3_cancel_from_json(json.loads(row["cancel_json"]))
                if row["cancel_json"] else None
            )
            effective = _merge_cancel(existing, record)
            if effective != existing:
                self._expect_one(
                    connection.execute(
                        "UPDATE t3_adapter_runs SET cancel_json=?, updated_ms=?"
                        " WHERE run_id=?",
                        (_canonical_state_json(effective), _now_ms(), str(run_id)),
                    ),
                    "put_cancel_record",
                )
            return effective

        return self._transaction(write)

    def put_result_reference(self, reference: T3ResultReference) -> T3ResultReference:
        """Write-once result ledger (audit #10); returns the persisted entry."""
        self._require_writable("put_result_reference")

        def write(connection: sqlite3.Connection) -> T3ResultReference:
            row = self._select_run(connection, reference.run_id)
            if row is None:
                raise _missing_row("put_result_reference", reference.run_id)
            existing = (
                _t3_result_reference_from_json(json.loads(row["result_ref_json"]))
                if row["result_ref_json"] else None
            )
            effective = _merge_result(existing, reference)
            if existing is None:
                self._expect_one(
                    connection.execute(
                        "UPDATE t3_adapter_runs SET result_ref_json=?, updated_ms=?"
                        " WHERE run_id=? AND result_ref_json IS NULL",
                        (_canonical_state_json(effective), _now_ms(),
                         reference.run_id),
                    ),
                    "put_result_reference",
                )
            return effective

        return self._transaction(write)


@runtime_checkable
class T3NativeClientPort(Protocol):
    """The native T3 thread owner this adapter launches and reads through.

    An authenticated native client implements this port; tests inject a
    fake.  The adapter never bypasses it to speak HTTP/MCP, holds no
    credentials, and spawns no processes.

    Choice documented: ``replay_launch`` is a SEPARATE seam from
    ``launch_thread`` (not an idempotent flag on it) so the minting path
    and the recovery path are structurally distinct — ``reattach`` can
    never accidentally mint.  Replay of a persisted envelope returns the
    original thread upstream (same namespace + same clientRequestId).

    ``authenticated_namespace`` (REQUIRED for every launch and for any
    recovery of a principal-scoped run): the port's ATTESTED authenticated
    principal / OAuth client namespace — the identity upstream command
    idempotency is really scoped by (T3 at the pin: ``client:<session id>``,
    see :class:`T3McpToolPort`).  The live proof (Rev 5 finding 1) showed
    the same ``clientRequestId`` under two different OAuth clients minting
    two different threads, so the adapter (a) refuses to launch through a
    port that cannot attest, (b) qualifies and persists the namespace with
    the intent and receipt, and (c) REFUSES any reattach whose port cannot
    attest, or attests a different principal than the persisted one (audit
    #3 — the old "unattested => skip the check" path failed open).

    Echo contract: a receipt's ``client_request_id``/``request_namespace``
    must come from UPSTREAM evidence (empty when the port cannot prove
    them), never copied from the request envelope — a crash-zone replay
    without them is not adopted.

    ``read_result(thread_id, run_id)`` (OPTIONAL): the dedicated terminal
    read ``collect_result`` uses; without it the adapter head-reads with an
    empty cursor.  Transport contract: raise :class:`T3UnknownOutcomeError`
    for every failure that may have happened after the request was sent.
    """

    async def launch_thread(
        self, envelope: T3ThreadLaunchEnvelope
    ) -> T3ThreadLaunchReceipt: ...

    async def read_thread(
        self, thread_id: str, run_id: str, cursor: str
    ) -> T3ThreadReadResult: ...

    async def interrupt_run(
        self, ref: WorkerProcessRef, reason: str
    ) -> T3InterruptOutcome: ...

    async def replay_launch(
        self, envelope: T3ThreadLaunchEnvelope
    ) -> T3ThreadLaunchReceipt: ...

    def authenticated_namespace(self) -> str: ...


def derive_t3_client_request_id(binding: ExecutionBinding) -> str:
    """Deterministic T3 clientRequestId for one broker binding.

    sha256 over the canonical JSON of the child identity triple
    ``(root_run_ref, immediate_parent_run_ref, logical_child_key)``, the
    admitted ``request_digest``, and the ``adapter_id`` — exactly the
    identity a replay must reproduce to hit the SAME upstream command.
    64 lowercase hex chars, far under the donor's 256-char cap.
    """
    if not isinstance(binding, ExecutionBinding):
        raise T3ExecutionAdapterError(
            "clientRequestId derivation requires an ExecutionBinding"
        )
    payload = {
        "adapter_id": binding.adapter_id,
        "child_identity": list(binding.child_identity()),
        "request_digest": binding.request_digest,
    }
    canonical = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _map_t3_status(native_status: str) -> WorkerRunStatus:
    """Map a native T3 thread status onto WorkerRunStatus.

    Honest-mapping rule (Rev 5 §3A): an unrecognized native state is never
    guessed as terminal.  Unmapped/empty status maps to the conservative
    non-terminal RUNNING until a recognized status arrives.
    """
    normalized = str(native_status or "").strip().lower()
    mapped = _T3_STATUS_MAP.get(normalized)
    if mapped is not None:
        return mapped
    return WorkerRunStatus.RUNNING


class T3ExecutionAdapter:
    """Built-but-unselected T3-native adapter over the closed native seam.

    Every method follows Rev 5 §3A/§7.  Selection is a deployment act by
    the incumbent runtime; constructing or registering this class selects
    nothing (the adapter's own path is PROVEN_LIVE by the recorded receipt
    in ``integrations/t3/live_proof/`` — but it stays UNSELECTED until the
    selected runtime composes the real MCP port into its transport).

    All per-run state (launch intents, receipts, original refs, cursors,
    cancel ledger, start bindings/specs, result references) lives in the
    injected :class:`T3AdapterStateStore` — an in-memory store by default
    (the test double / non-durable fallback), or
    :class:`SQLiteT3AdapterStateStore` for real durability: a second
    adapter constructed on the same store (a simulated cold restart, or a
    concurrent process) reattaches the SAME execution with the launch count
    still one.

    Exactly-once start (audit #1): the launch intent is CLAIMED atomically
    (one claimant per run across processes) BEFORE the native call; a loser
    never launches and gets :class:`T3LaunchClaimConflictError` — the
    winner's execution is recovered through :meth:`reattach`.
    """

    adapter_id = T3_NATIVE_ADAPTER_ID

    def __init__(
        self,
        port: T3NativeClientPort,
        binding_source: Callable[[WorkerLaunchSpec], ExecutionBinding | None],
        inspector: ProcessInspector,
        *,
        clock: Callable[[], datetime] | None = None,
        state_store: T3AdapterStateStore | None = None,
    ) -> None:
        self._port = port
        self._binding_source = binding_source
        self.inspector = inspector
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        # Durable adapter state per run.  Every mutation writes through the
        # store SYNCHRONOUSLY at its ordering point (intent claimed BEFORE
        # the native call; receipt + original ref BEFORE the ACK; cursor
        # only after a successful read).
        self._state: T3AdapterStateStore = (
            state_store if state_store is not None else InMemoryT3AdapterStateStore()
        )

    # --- state access (read-through; used by tests and operators) ---------

    def launch_intent(self, run_id: str) -> T3LaunchIntent | None:
        """The persisted launch intent for a run, if any (durable read)."""
        run = self._state.load_run(str(run_id))
        return run.intent if run is not None else None

    def launch_receipt(self, run_id: str) -> T3ThreadLaunchReceipt | None:
        """The persisted native launch receipt for a run, if any."""
        run = self._state.load_run(str(run_id))
        return run.receipt if run is not None else None

    def retained_original_ref(self, run_id: str) -> WorkerProcessRef | None:
        """The retained original neutral ref for a run, if any."""
        run = self._state.load_run(str(run_id))
        return run.original_ref if run is not None else None

    def read_cursor(self, run_id: str) -> str:
        """The persisted incremental read cursor for a run ("" when none)."""
        run = self._state.load_run(str(run_id))
        return run.cursor if run is not None else ""

    def result_ledger_entry(self, run_id: str) -> T3ResultReference | None:
        """The canonical ledgered result reference for a run, if any."""
        run = self._state.load_run(str(run_id))
        return run.result_reference if run is not None else None

    # --- start -------------------------------------------------------------

    async def start(self, spec: WorkerLaunchSpec) -> WorkerProcessRef:
        """Launch through the native port under the current broker binding.

        Refuses fail-closed without a valid, current ``ExecutionBinding``,
        without a port-attested authenticated principal, or when a v1.1 t3
        binding's idempotency join drifted (C-P1).  The launch intent (with
        the principal-qualified request namespace) is CLAIMED atomically
        BEFORE any native call — a concurrent or repeated start for the same
        run loses the claim and never launches; the receipt and the original
        neutral ref are persisted BEFORE the returned ref acknowledges start.
        """
        if not isinstance(spec, WorkerLaunchSpec):
            raise T3ExecutionAdapterError("start requires a WorkerLaunchSpec")
        binding = self._require_current_binding(spec)
        principal = self._require_attested_principal("launch")
        client_request_id = derive_t3_client_request_id(binding)
        self._verify_binding_join(binding, client_request_id, principal)
        namespace = t3_request_namespace(principal)
        envelope = self._launch_envelope(spec, client_request_id, namespace)
        intent = T3LaunchIntent(
            run_id=spec.run_id,
            client_request_id=client_request_id,
            request_namespace=namespace,
            adapter_id=T3_NATIVE_ADAPTER_ID,
            envelope=envelope,
            created_at=envelope.created_at,
        )
        claim_token = uuid.uuid4().hex
        # CLAIM the launch intent (with the binding + spec) BEFORE any native
        # call — atomic across processes; the store's transaction completes
        # first.  A store failure here precedes any native call: no effect.
        try:
            claimed = self._state.claim_launch_intent(
                intent, binding=binding, spec=spec, claim_token=claim_token
            )
        except T3ExecutionAdapterError:
            raise
        except Exception as exc:
            raise T3StateStoreError(
                f"launch intent could not be persisted (no native call made): {exc}"
            ) from exc
        if not claimed:
            raise T3LaunchClaimConflictError(
                f"run {spec.run_id!r} already has a persisted launch intent "
                "(another claimant, an earlier attempt, or the effect-unknown "
                "zone); start never retries and never launches twice — "
                "reattach recovers the SAME execution under the SAME "
                "clientRequestId",
                run_id=spec.run_id,
            )
        try:
            receipt = await self._port.launch_thread(envelope)
        except T3UnknownOutcomeError as exc:
            # Effect unknown: the intent STAYS persisted.  Never auto-retry,
            # never mint a new key — reattach replays the SAME command.
            raise T3LaunchEffectUnknownError(
                f"native launch outcome unknown for clientRequestId "
                f"{client_request_id!r}; never auto-retried and never given a "
                "new key — reattach replays the SAME key and namespace",
                client_request_id=client_request_id,
            ) from exc
        except Exception as exc:
            # Clean refusal per the port contract: the launch definitively
            # did NOT happen.  Roll back ONLY this claimant's intent so a
            # retry derives the SAME deterministic key; never a new key.
            try:
                self._state.clear_launch_attempt(spec.run_id, claim_token=claim_token)
            except Exception as clear_exc:
                raise T3ExecutionAdapterError(
                    f"native T3 port refused the launch ({exc}); the intent "
                    f"rollback also failed ({clear_exc}) — the intent stays "
                    "and start stays blocked for this run"
                ) from exc
            raise T3ExecutionAdapterError(
                f"native T3 port refused the launch: {exc}"
            ) from exc
        if (
            not isinstance(receipt, T3ThreadLaunchReceipt)
            or not receipt.thread_id
            or not receipt.run_id
        ):
            # A possible native effect with an unusable receipt: keep the
            # persisted intent (start stays blocked; reattach replays the
            # SAME key) — never assume no effect.
            raise T3LaunchEffectUnknownError(
                "native port returned an unusable launch receipt; the launch "
                f"intent for clientRequestId {client_request_id!r} stays "
                "persisted — reattach replays the SAME key",
                client_request_id=client_request_id,
            )
        if (receipt.client_request_id and receipt.client_request_id != client_request_id) or (
            receipt.request_namespace and receipt.request_namespace != namespace
        ):
            raise T3LaunchEffectUnknownError(
                "native launch receipt echoes a foreign idempotency identity; "
                f"the intent for clientRequestId {client_request_id!r} stays "
                "persisted for reconciliation",
                client_request_id=client_request_id,
            )
        # Persist the receipt and the ORIGINAL ref BEFORE the ACK (the
        # return below), conditional on still holding the claim.  The native
        # launch already took effect: a store failure here is EFFECT_UNKNOWN
        # (audit #12), never a raw sqlite3 error and never a clean refusal.
        ref = self._neutral_process_ref(spec, receipt, client_request_id)
        try:
            self._state.put_launch_receipt(
                spec.run_id, receipt=receipt, original_ref=ref, cursor="",
                claim_token=claim_token,
            )
        except Exception as exc:
            raise T3LaunchEffectUnknownError(
                f"native launch succeeded (thread {receipt.thread_id!r}) but its "
                f"receipt could not be persisted: {exc}; the intent for "
                f"clientRequestId {client_request_id!r} stays — reattach replays "
                "the SAME key",
                client_request_id=client_request_id,
            ) from exc
        return ref

    def _require_current_binding(self, spec: WorkerLaunchSpec) -> ExecutionBinding:
        try:
            binding = self._binding_source(spec)
        except AdapterBindingError:
            raise
        except Exception as exc:
            raise T3ExecutionAdapterError(
                f"broker ExecutionBinding resolution failed: {exc}"
            ) from exc
        if binding is None:
            raise T3ExecutionAdapterError(
                "refused: no current broker ExecutionBinding for this launch"
            )
        if not isinstance(binding, ExecutionBinding):
            raise T3ExecutionAdapterError(
                "refused: broker binding is not an ExecutionBinding.v1"
            )
        if binding.adapter_id != T3_NATIVE_ADAPTER_ID:
            raise T3ExecutionAdapterError(
                "refused: binding is not a fenced assignment of the "
                f"{T3_NATIVE_ADAPTER_ID!r} adapter"
            )
        if not binding.worker_id or binding.worker_id != spec.worker_id:
            raise T3ExecutionAdapterError(
                "refused: binding worker assignment does not match the launch spec"
            )
        if binding.lease_expiry:
            try:
                expiry = datetime.fromisoformat(
                    binding.lease_expiry.replace("Z", "+00:00")
                )
            except ValueError as exc:
                raise T3ExecutionAdapterError(
                    "refused: binding lease expiry is malformed"
                ) from exc
            if expiry.tzinfo is None or expiry.utcoffset() is None:
                raise T3ExecutionAdapterError(
                    "refused: binding lease expiry is not timezone aware"
                )
            if expiry <= self._clock():
                raise T3ExecutionAdapterError(
                    "refused: binding lease has expired (stale fenced assignment)"
                )
        return binding

    def _verify_binding_join(
        self, binding: ExecutionBinding, client_request_id: str, principal: str
    ) -> None:
        """C-P1: launch-time verification of the v1.1 t3 idempotency join.

        The claim seam (``executive_runtime._join_native_runtime_binding``)
        stamps a t3 binding with ``operation_key = derive_t3_client_request_id
        (binding)`` and ``caller_namespace = T3_REQUEST_NAMESPACE``.  The
        launch must run under EXACTLY that identity: a drifted
        ``operation_key`` (or a t3 binding without one), or a
        ``caller_namespace`` that is neither the pinned adapter namespace nor
        the namespace qualified by the PORT-ATTESTED principal, is refused
        typed — otherwise the broker would believe one upstream command is
        bound while the adapter launched another.
        """
        is_t3_binding = binding.runtime_kind == "t3-native"
        operation_key = str(binding.operation_key or "")
        if (is_t3_binding or operation_key) and operation_key != client_request_id:
            raise T3BindingJoinDriftError(
                "refused: the binding's operation_key "
                f"{operation_key!r} is not this binding's derived T3 "
                f"clientRequestId {client_request_id!r} (the claim-time join "
                "drifted); never launching under a different upstream key"
            )
        caller_namespace = str(binding.caller_namespace or "")
        allowed = {T3_REQUEST_NAMESPACE, t3_request_namespace(principal)}
        if (is_t3_binding or caller_namespace) and caller_namespace not in allowed:
            raise T3BindingJoinDriftError(
                f"refused: the binding's caller_namespace {caller_namespace!r} "
                "matches neither the pinned adapter namespace nor the "
                f"port-attested principal's namespace "
                f"{t3_request_namespace(principal)!r}"
            )

    def _launch_envelope(
        self,
        spec: WorkerLaunchSpec,
        client_request_id: str,
        request_namespace: str = T3_REQUEST_NAMESPACE,
    ) -> T3ThreadLaunchEnvelope:
        return T3ThreadLaunchEnvelope(
            request_namespace=request_namespace,
            client_request_id=client_request_id,
            run_id=spec.run_id,
            worker_id=spec.worker_id,
            title=f"mastermind {spec.job_id}/{spec.run_id}",
            message=spec.prompt,
            workspace_ref=str(spec.workspace_path),
            model_selection=spec.model,
            created_at=self._now_iso(),
        )

    # --- authenticated namespace (idempotency identity) --------------------

    def _port_authenticated_principal(self) -> str:
        """The port's attested principal, or ``""`` when it cannot attest.

        A port without ``authenticated_namespace`` (or returning ``None`` /
        an empty string) cannot attest; a non-string value is refused.
        Callers decide whether an unattested port may proceed — launches and
        principal-scoped recovery never may.
        """
        getter = getattr(self._port, "authenticated_namespace", None)
        if not callable(getter):
            return ""
        value = getter()
        if value is None:
            return ""
        if not isinstance(value, str):
            raise T3ExecutionAdapterError(
                "port authenticated_namespace must return a string or None"
            )
        return value.strip()

    def _require_attested_principal(self, operation: str) -> str:
        principal = self._port_authenticated_principal()
        if not principal:
            raise T3NamespaceAttestationError(
                f"refused: {operation} requires a port that attests its "
                "authenticated principal (authenticated_namespace); an "
                "unattested port cannot prove which OAuth client's "
                "idempotency identity it runs under — re-authenticate",
                reason="UNATTESTED",
            )
        return principal

    def _require_namespace_continuity(
        self, persisted_namespace: str, *, native_call: bool
    ) -> None:
        """Refuse recovery the port cannot prove runs under the SAME principal.

        The live proof (Rev 5 finding 1) showed the same clientRequestId
        under two different OAuth clients minting two different threads: the
        authenticated principal is part of the idempotency identity.  When
        the persisted namespace names a principal, the port MUST attest that
        same principal — an unattested port is refused (never skipped,
        audit #3) and a different principal is refused.  A legacy
        unqualified namespace carries no principal to verify: recovery that
        needs a native replay under it is refused; recovery of a retained
        ref (no native call) may proceed.
        """
        persisted_principal = _namespace_principal(persisted_namespace)
        if persisted_principal:
            principal = self._port_authenticated_principal()
            if not principal:
                raise T3NamespaceAttestationError(
                    "refused: the persisted launch namespace names principal "
                    f"{persisted_principal!r} but the port cannot attest its "
                    "authenticated namespace — recover under the original "
                    "principal (re-authenticate)",
                    reason="UNATTESTED",
                )
            if principal != persisted_principal:
                raise T3NamespaceAttestationError(
                    "refused: recovery under a different authenticated namespace "
                    f"({principal!r}) than the persisted launch namespace "
                    f"({persisted_principal!r}); two OAuth clients are never the "
                    "same idempotency identity — recover under the original "
                    "principal",
                    reason="PRINCIPAL_MISMATCH",
                )
            return
        if native_call:
            raise T3NamespaceAttestationError(
                "refused: the persisted launch namespace "
                f"{persisted_namespace!r} names no principal, so a native "
                "replay cannot be proven to run under the original OAuth "
                "client; reconcile this run out of band",
                reason="LEGACY_NAMESPACE_UNVERIFIABLE",
            )

    def _neutral_process_ref(
        self,
        spec: WorkerLaunchSpec,
        receipt: T3ThreadLaunchReceipt,
        client_request_id: str,
    ) -> WorkerProcessRef:
        """Deterministically map the native receipt onto the neutral floor.

        Built ONLY from (spec fields, receipt fields, key) so a replay of
        the same command reproduces an equal ref — which is what reattach
        verifies.  T3 runs a thread, not a local process: pid/pgid are 0,
        the binary placeholder is identity-only (nothing spawns from it),
        and the thread's single event ledger serves as both stdout and
        stderr paths.  ``process_start_identity`` is
        ``t3:<threadId>:<native runId>`` (see :func:`t3_native_run_coordinates`).
        """
        return WorkerProcessRef(
            run_id=spec.run_id,
            pid=0,
            pgid=0,
            session_id=None,
            process_start_identity=f"t3:{receipt.thread_id}:{receipt.run_id}",
            boot_session_id=f"t3-native:{receipt.thread_id}",
            launch_nonce=client_request_id,
            provider_session_id=receipt.thread_id,
            stdout_path=f"t3://thread/{receipt.thread_id}/events",
            stderr_path=f"t3://thread/{receipt.thread_id}/events",
            result_path=f"t3://thread/{receipt.thread_id}/result",
            started_at=receipt.created_at,
            binary=_T3_REMOTE_BINARY_PLACEHOLDER,
            base_sha=spec.expected_base_sha or "",
        )

    # --- status ------------------------------------------------------------

    async def status(self, ref: WorkerProcessRef) -> WorkerRunStatus:
        """Return the honest mapped state for that exact run.

        Exact-run read through the port using the PERSISTED incremental
        cursor; the cursor advances (persisted, forward-only) only after a
        successful read.
        """
        run = self._require_run_state(ref)
        original = run.original_ref
        assert original is not None  # _require_run_state guarantees this
        thread_id, native_run_id = self._native_coordinates(run)
        read = await self._read_exact(
            thread_id, native_run_id, run.cursor, original.run_id
        )
        state = _map_t3_status(read.native_status)
        entry = run.cancel
        if entry is not None and not entry.settled:
            if state in _TERMINAL_STATES:
                self._settle(original.run_id, entry, state)
            else:
                # Requested cancellation that has not settled yet: report the
                # honest intermediate state, never a premature CANCELLED.
                return WorkerRunStatus.CANCELLING
        return state

    # --- collect_result ----------------------------------------------------

    async def collect_result(self, ref: WorkerProcessRef) -> CollectionReceipt:
        """Read the exact run's final state/result through a TERMINAL read.

        Audit #13: the final result is never read from the incremental status
        cursor (status polls advance it PAST the final reply, live finding).
        The port's dedicated ``read_result(thread_id, run_id)`` is used when
        it exists; otherwise a head read (empty cursor) of the exact run.
        The terminal read never moves the persisted cursor.  A terminal read
        without a canonical result reference — or whose "reference" is just
        the bare thread id — is refused.  The canonical reference is stored
        in the WRITE-ONCE result ledger BEFORE the CollectionReceipt is
        constructed or returned.  Reading T3 is NOT company acceptance.
        """
        run = self._require_run_state(ref)
        original = run.original_ref
        assert original is not None
        thread_id, native_run_id = self._native_coordinates(run)
        read = await self._read_terminal(thread_id, native_run_id)
        state = _map_t3_status(read.native_status)
        if state not in _TERMINAL_STATES:
            raise T3ExecutionAdapterError(
                f"run {original.run_id!r} is not terminal; no final result to "
                "collect"
            )
        result_ref = str(read.result_ref or "")
        if not result_ref or result_ref in {thread_id, native_run_id}:
            raise T3ExecutionAdapterError(
                f"terminal read for run {original.run_id!r} carries no "
                "canonical result reference (a bare thread/run id is not a "
                "result); refusing to collect"
            )
        # STORE the canonical result reference BEFORE constructing/returning
        # the CollectionReceipt (reading T3 is NOT company acceptance).  The
        # ledger is write-once: a different later result is refused.
        self._state.put_result_reference(
            T3ResultReference(
                run_id=original.run_id,
                thread_id=thread_id,
                result_ref=result_ref,
                native_status=read.native_status,
                recorded_at=self._now_iso(),
            )
        )
        return self._build_collection_receipt(original, read, state)

    def _build_collection_receipt(
        self,
        original: WorkerProcessRef,
        read: T3ThreadReadResult,
        state: WorkerRunStatus,
    ) -> CollectionReceipt:
        run = self._state.load_run(original.run_id)
        spec = run.spec if run is not None else None
        if spec is None:
            raise T3ExecutionAdapterError(
                f"no persisted launch spec for run {original.run_id!r}; the "
                "CollectionReceipt requires the original spec"
            )
        result = WorkerResult(
            job_id=spec.job_id,
            run_id=original.run_id,
            worker_id=spec.worker_id,
            status=state,
            structured_output=dict(read.result_payload) or None,
            artifact_manifest=(),
            git_manifest={},
            usage={},
            provider_session_id=original.provider_session_id,
            exit_code=None,
            started_at=read.started_at,
            finished_at=read.finished_at or self._now_iso(),
            error=read.error,
        )
        return CollectionReceipt(
            process_ref=original,
            result=result,
            stdout_sha256=_EMPTY_SHA256,
            stderr_sha256=_EMPTY_SHA256,
            result_sha256=hashlib.sha256(read.result_ref.encode("utf-8")).hexdigest(),
        )

    # --- cancel ------------------------------------------------------------

    async def cancel(self, ref: WorkerProcessRef, reason: str) -> CancelReceipt:
        """Interrupt the exact run; report requested versus settled.

        Deliberately NO lease-freshness gate here: cancel must remain
        possible with an expired/stale binding lease (the retained-ref
        identity match is the only gate); staleness blocks NEW execution only
        (Rev 5 §3A/§7).  A run whose cancellation already SETTLED is not
        interrupted again: the settled ledger is returned unchanged (audit
        #9 / NM-03 — a cancel replay is idempotent, never a second cancel).
        """
        run = self._require_run_state(ref)
        original = run.original_ref
        assert original is not None
        if not isinstance(reason, str) or not reason.strip():
            raise T3ExecutionAdapterError("cancel requires a non-empty reason")
        if run.cancel is not None and run.cancel.settled:
            entry = run.cancel
            return CancelReceipt(
                run_id=original.run_id,
                reason=entry.reason,
                signal_sent=entry.signal_sent,
                escalated_to_sigkill=False,
                already_exited=True,
                finished_at=entry.finished_at or entry.settled_at or self._now_iso(),
            )
        try:
            outcome = await self._port.interrupt_run(original, reason)
        except T3UnknownOutcomeError as exc:
            # The interrupt request was made; whether it landed is unknown.
            # Record requested-but-unsettled honestly (the store merge never
            # clobbers an existing record), then surface the ambiguity —
            # status() reconciles once the native state shows.
            self._state.put_cancel_record(
                original.run_id,
                _T3CancelLedgerEntry(
                    reason=reason,
                    requested=True,
                    signal_sent=False,
                    escalated_to_sigkill=False,
                    already_exited=False,
                    settled=False,
                    requested_at=self._now_iso(),
                ),
            )
            raise T3ExecutionAdapterError(
                f"interrupt outcome unknown for run {original.run_id!r}; the "
                "cancel ledger records requested-but-unsettled until the "
                "native state is observed"
            ) from exc
        except Exception as exc:
            # Clean refusal: the interrupt definitively did not take effect;
            # nothing is recorded as requested.
            raise T3ExecutionAdapterError(
                f"native T3 port refused the interrupt for run "
                f"{original.run_id!r}: {exc}"
            ) from exc
        if not isinstance(outcome, T3InterruptOutcome):
            raise T3ExecutionAdapterError(
                "native port returned an unusable interrupt outcome"
            )
        now = self._now_iso()
        observed = _map_t3_status(outcome.observed_native_status)
        terminal_observed = observed in _TERMINAL_STATES
        # Reconcile native terminal state before claiming settled: a
        # claimed-settled outcome without an observed terminal state stays
        # unsettled until status() observes one.
        settled = bool(outcome.settled or outcome.already_exited) and terminal_observed
        entry = self._state.put_cancel_record(
            original.run_id,
            _T3CancelLedgerEntry(
                reason=reason,
                requested=bool(outcome.requested),
                signal_sent=bool(outcome.requested),
                escalated_to_sigkill=False,
                already_exited=bool(outcome.already_exited),
                settled=settled,
                requested_at=now,
                settled_at=now if settled else None,
                settled_state=observed.value if settled else None,
                finished_at=outcome.finished_at or now,
            ),
        )
        return CancelReceipt(
            run_id=original.run_id,
            reason=reason,
            signal_sent=bool(outcome.requested),
            escalated_to_sigkill=False,
            already_exited=bool(outcome.already_exited),
            finished_at=(entry.finished_at if entry is not None else "") or outcome.finished_at or now,
        )

    def cancel_report(self, run_id: str) -> T3CancelReport | None:
        """The requested-versus-settled record for a run, if any."""
        run = self._state.load_run(str(run_id))
        entry = run.cancel if run is not None else None
        if entry is None:
            return None
        return T3CancelReport(
            run_id=str(run_id),
            reason=entry.reason,
            requested=entry.requested,
            signal_sent=entry.signal_sent,
            escalated_to_sigkill=entry.escalated_to_sigkill,
            already_exited=entry.already_exited,
            settled=entry.settled,
            requested_at=entry.requested_at,
            settled_at=entry.settled_at,
            settled_state=entry.settled_state,
            finished_at=entry.finished_at,
        )

    def _settle(self, run_id: str, entry: _T3CancelLedgerEntry, state: WorkerRunStatus) -> None:
        self._state.put_cancel_record(
            run_id,
            dataclasses.replace(
                entry,
                settled=True,
                settled_at=self._now_iso(),
                settled_state=state.value,
            ),
        )

    # --- run_validation_argv -----------------------------------------------

    async def run_validation_argv(
        self,
        spec: WorkerLaunchSpec,
        argv: Any,
        *,
        timeout_seconds: float = 300.0,
    ) -> ValidationReceipt:
        """Refuse: the T3 seam exposes no argv-validation operation.

        The neutral adapter floor requires this method's presence; T3
        validates inside its native thread, never through local argv.  A
        refused operation, not a pretended one.
        """
        raise T3ExecutionAdapterError(
            "t3-native exposes no argv-validation seam; validation happens "
            "natively inside the launched thread"
        )

    # --- reattach ----------------------------------------------------------

    async def reattach(
        self, spec: WorkerLaunchSpec, binding: WorkerRecoveryBinding
    ) -> WorkerProcessRef:
        """Recover the SAME execution; never a replacement, never a new key.

        With a retained (persisted) original ref this needs no native call —
        including after a cold restart of the coordinator or from a process
        that lost the launch claim, because the retained ref is loaded from
        the durable state store.  Without one the SAME persisted launch
        command (same clientRequestId + namespace) is REPLAYED through
        ``replay_launch`` — upstream idempotent replay returns the ORIGINAL
        thread.  A replay that returns a different thread is refused; a
        crash-zone replay (thread not yet known) is adopted only when the
        receipt carries the port's upstream-derived echo of the SAME key and
        namespace; recovery under a different or unattested principal than
        the persisted one is refused (two OAuth clients are never the same
        idempotency identity).  ``launch_thread`` is never called from here.
        """
        if not isinstance(spec, WorkerLaunchSpec):
            raise T3ExecutionAdapterError("reattach requires a WorkerLaunchSpec")
        if not isinstance(binding, WorkerRecoveryBinding):
            raise T3ExecutionAdapterError(
                "reattach requires a WorkerRecoveryBinding"
            )
        if binding.adapter_id != T3_NATIVE_ADAPTER_ID:
            raise T3ExecutionAdapterError(
                "recovery binding belongs to another adapter"
            )
        original = binding.process_ref
        if original.run_id != spec.run_id:
            raise T3ExecutionAdapterError(
                "recovery binding run identity does not match the spec"
            )
        caller_spec_sha = worker_launch_spec_sha256(spec)
        if binding.launch_spec_sha256 != caller_spec_sha:
            raise T3ExecutionAdapterError(
                "recovery binding does not bind this launch spec"
            )
        run = self._state.load_run(spec.run_id)
        retained = run.original_ref if run is not None else None
        intent = run.intent if run is not None else None
        if run is not None and (intent is not None or retained is not None):
            # The persisted namespace is part of the idempotency identity.
            self._require_namespace_continuity(
                self._persisted_namespace(run), native_call=retained is None
            )
        if run is not None and (run.spec_sha256 or run.spec is not None):
            # Adapter-side drift guard across restart.  The persisted sha of
            # the caller's ORIGINAL spec object is authoritative (audit #5);
            # legacy rows without one fall back to re-hashing the loaded spec.
            persisted_sha = run.spec_sha256 or worker_launch_spec_sha256(run.spec)
            if caller_spec_sha != persisted_sha:
                raise T3ExecutionAdapterError(
                    "launch spec drifted from the persisted spec for run "
                    f"{spec.run_id!r}; refusing to recover under a different "
                    "command shape"
                )
        if retained is not None:
            if retained != original:
                raise T3ExecutionAdapterError(
                    "retained original ref differs from the recovery binding; "
                    "refusing to swap executions"
                )
            if intent is not None and original.launch_nonce != intent.client_request_id:
                raise T3ExecutionAdapterError(
                    "recovery binding carries a foreign clientRequestId; "
                    "refusing to operate under a different key"
                )
            return retained
        if intent is not None:
            # Crash/lost ACK after the intent claim: replay the persisted
            # envelope VERBATIM (same key + namespace).  Never a fresh key.
            if intent.envelope is None:
                raise T3ExecutionAdapterError(
                    "persisted launch intent carries no envelope; refusing to "
                    "replay under an unknown command shape"
                )
            if original.launch_nonce != intent.client_request_id:
                raise T3ExecutionAdapterError(
                    "recovery binding carries a foreign clientRequestId; "
                    "refusing to operate under a different key"
                )
            return await self._replay_and_adopt(spec, intent.envelope, original, intent)
        # No retained intent in the store (pre-durability recovery binding):
        # reconstruct the SAME command from the recovery binding — the key
        # comes from the ORIGINAL ref's launch_nonce, never regenerated.  The
        # original principal was never recorded, so the replayed thread can
        # only be verified against a thread the original ref already knew.
        key = original.launch_nonce
        if not key:
            raise T3ExecutionAdapterError(
                "recovery binding carries no original clientRequestId; "
                "refusing to replay without the SAME key"
            )
        if not original.provider_session_id:
            raise T3ExecutionAdapterError(
                "refused: a pre-durability recovery binding without a known "
                "original thread cannot prove a replay returns the ORIGINAL "
                "execution (the launching principal was never recorded)"
            )
        envelope = self._reconstruct_envelope(spec, key)
        return await self._replay_and_adopt(spec, envelope, original, None)

    @staticmethod
    def _persisted_namespace(run: T3AdapterRunState) -> str:
        intent_ns = run.intent.request_namespace if run.intent is not None else ""
        receipt_ns = run.receipt.request_namespace if run.receipt is not None else ""
        if intent_ns and receipt_ns and intent_ns != receipt_ns:
            raise T3ExecutionAdapterError(
                f"run {run.run_id!r} persists two different request namespaces "
                f"({intent_ns!r} vs {receipt_ns!r}); refusing recovery"
            )
        return intent_ns or receipt_ns

    def _reconstruct_envelope(
        self, spec: WorkerLaunchSpec, client_request_id: str
    ) -> T3ThreadLaunchEnvelope:
        """Same key under the CURRENT attested principal's namespace."""
        principal = self._require_attested_principal("replay")
        return self._launch_envelope(
            spec, client_request_id, t3_request_namespace(principal)
        )

    async def _replay_and_adopt(
        self,
        spec: WorkerLaunchSpec,
        envelope: T3ThreadLaunchEnvelope,
        original: WorkerProcessRef,
        intent: T3LaunchIntent | None,
    ) -> WorkerProcessRef:
        client_request_id = (
            intent.client_request_id if intent is not None
            else envelope.client_request_id
        )
        try:
            receipt = await self._port.replay_launch(envelope)
        except T3UnknownOutcomeError as exc:
            raise T3LaunchEffectUnknownError(
                f"replay outcome unknown for clientRequestId "
                f"{client_request_id!r}; never auto-retried and never given a "
                "new key — reattach replays the SAME command",
                client_request_id=client_request_id,
            ) from exc
        except Exception as exc:
            raise T3ExecutionAdapterError(
                f"native T3 port refused the replay: {exc}"
            ) from exc
        if (
            not isinstance(receipt, T3ThreadLaunchReceipt)
            or not receipt.thread_id
            or not receipt.run_id
        ):
            raise T3LaunchEffectUnknownError(
                "native port returned an unusable replay receipt; never "
                "auto-retried and never given a new key",
                client_request_id=client_request_id,
            )
        self._verify_replayed_thread(
            receipt, original, client_request_id, envelope
        )
        ref = self._neutral_process_ref(spec, receipt, client_request_id)
        if ref != original and original.provider_session_id:
            # The original ref already knew the thread: a replay reproducing
            # any other identity is a replacement — refused.
            raise T3ExecutionAdapterError(
                "replay did not reproduce the original execution identity; "
                "refusing to adopt a replacement"
            )
        # When the original ref predates any known thread (crash between
        # intent claim and ACK), the replayed receipt IS the first learned
        # identity of the SAME execution: the port's upstream-derived echo
        # proved (namespace, key) above.  Persist the receipt, the adopted
        # ORIGINAL ref and the validated spec BEFORE the ACK (write-once: a
        # concurrent recoverer that adopted the same thread is a no-op).
        try:
            self._state.put_launch_receipt(
                spec.run_id, receipt=receipt, original_ref=ref, spec=spec,
            )
        except T3ExecutionAdapterError as exc:
            if isinstance(exc, T3StateStoreError):
                raise T3LaunchEffectUnknownError(
                    f"replay returned thread {receipt.thread_id!r} but its "
                    f"receipt could not be persisted: {exc}",
                    client_request_id=client_request_id,
                ) from exc
            raise
        except Exception as exc:
            raise T3LaunchEffectUnknownError(
                f"replay returned thread {receipt.thread_id!r} but its receipt "
                f"could not be persisted: {exc}",
                client_request_id=client_request_id,
            ) from exc
        return ref

    def _verify_replayed_thread(
        self,
        receipt: T3ThreadLaunchReceipt,
        original: WorkerProcessRef,
        client_request_id: str,
        envelope: T3ThreadLaunchEnvelope,
    ) -> None:
        """Refuse any replay that does not provably return the ORIGINAL thread."""
        if original.provider_session_id and receipt.thread_id != original.provider_session_id:
            raise T3ExecutionAdapterError(
                "replay returned a DIFFERENT thread than the original "
                f"execution ({original.provider_session_id!r} -> "
                f"{receipt.thread_id!r}); refusing a replacement"
            )
        # The receipt's echoed idempotency identity must match the replayed
        # command.  Ports set the echo ONLY from upstream evidence (the live
        # port derives it from the upstream thread id), never by copying the
        # request envelope.
        if (
            receipt.client_request_id
            and receipt.client_request_id != client_request_id
        ):
            raise T3ExecutionAdapterError(
                "replay returned a receipt echoing a foreign "
                f"clientRequestId ({receipt.client_request_id!r} != "
                f"{client_request_id!r}); refusing a foreign execution"
            )
        if (
            receipt.request_namespace
            and envelope.request_namespace
            and receipt.request_namespace != envelope.request_namespace
        ):
            raise T3ExecutionAdapterError(
                "replay returned a receipt from a different request "
                f"namespace ({receipt.request_namespace!r} != "
                f"{envelope.request_namespace!r}); refusing a foreign "
                "execution"
            )
        if not original.provider_session_id and (
            not receipt.client_request_id or not receipt.request_namespace
        ):
            # Crash zone (thread not yet known): the upstream-derived echo is
            # the ONLY evidence this receipt belongs to this execution.  An
            # unechoed receipt is unverifiable — never adopted (audit #3).
            raise T3LaunchEffectUnknownError(
                "crash-zone replay returned a receipt without an upstream-"
                "derived echo of the clientRequestId and namespace; the "
                "thread cannot be proven to be the ORIGINAL execution — not "
                "adopted, reconcile out of band",
                client_request_id=client_request_id,
            )
        run = self._state.load_run(original.run_id)
        retained_receipt = run.receipt if run is not None else None
        if (
            retained_receipt is not None
            and retained_receipt.thread_id != receipt.thread_id
        ):
            raise T3ExecutionAdapterError(
                "replay returned a thread different from the retained "
                "original receipt; refusing a replacement"
            )

    # --- internals ---------------------------------------------------------

    def _native_coordinates(self, run: T3AdapterRunState) -> tuple[str, str]:
        """The persisted (threadId, native runId) for one neutral run."""
        receipt = run.receipt
        if receipt is None:
            raise T3ExecutionAdapterError(
                f"no native launch receipt persisted for run {run.run_id!r}"
            )
        return receipt.thread_id, receipt.run_id

    async def _read_exact(
        self, thread_id: str, native_run_id: str, cursor: str, run_id: str
    ) -> T3ThreadReadResult:
        read = await self._port_read(
            self._port.read_thread, thread_id, native_run_id, cursor
        )
        # Advance (persist) the cursor only AFTER a successful exact read;
        # the store keeps it forward-only ("" never resets it).
        self._state.put_cursor(run_id, read.next_cursor)
        return read

    async def _read_terminal(
        self, thread_id: str, native_run_id: str
    ) -> T3ThreadReadResult:
        """The dedicated terminal read for collection (never the cursor)."""
        reader = getattr(self._port, "read_result", None)
        if callable(reader):
            return await self._port_read(reader, thread_id, native_run_id)
        return await self._port_read(
            self._port.read_thread, thread_id, native_run_id, ""
        )

    async def _port_read(
        self, reader: Callable[..., Any], thread_id: str, native_run_id: str,
        *cursor: str,
    ) -> T3ThreadReadResult:
        try:
            read = await reader(thread_id, native_run_id, *cursor)
        except T3UnknownOutcomeError as exc:
            raise T3ExecutionAdapterError(
                f"thread read outcome unknown for thread {thread_id!r}; the "
                "persisted cursor stays unchanged"
            ) from exc
        except Exception as exc:
            raise T3ExecutionAdapterError(
                f"native T3 port refused the thread read: {exc}"
            ) from exc
        if (
            not isinstance(read, T3ThreadReadResult)
            or read.thread_id != thread_id
            or read.run_id != native_run_id
        ):
            raise T3ExecutionAdapterError(
                "thread read did not return the exact run's result; refusing "
                "a replacement"
            )
        return read

    def _require_run_state(self, ref: WorkerProcessRef) -> T3AdapterRunState:
        """Load the durable run state, refusing unknown or swapped refs."""
        if not isinstance(ref, WorkerProcessRef):
            raise T3ExecutionAdapterError("operation requires a WorkerProcessRef")
        run = self._state.load_run(ref.run_id)
        if run is None or run.original_ref is None:
            raise T3ExecutionAdapterError(
                f"no original ref retained for run {ref.run_id!r}"
            )
        if run.original_ref != ref:
            raise T3ExecutionAdapterError(
                "ref does not match the retained original ref"
            )
        return run

    def _now_iso(self) -> str:
        return self._clock().isoformat()


# =============================================================================
# Reference live port: T3 MCP tools over an injected transport (audit #3/#4/#7)
# =============================================================================
#
# The adapter never speaks HTTP/MCP; this port maps the donor's MCP tool wire
# shapes (pin 0770446) onto :class:`T3NativeClientPort` over an INJECTED
# ``call_tool(name, arguments) -> Mapping`` transport.  It holds no
# credential: :meth:`T3McpToolPort.from_access_token` only projects which
# upstream session a bearer token is and never stores or logs the token.

#: Upstream MCP client sessions carry this ``sub`` claim (donor
#: ``apps/server/src/auth/EnvironmentAuth.ts`` ``MCP_CLIENT_SUBJECT``).
T3_MCP_CLIENT_SUBJECT = "mcp-client"
#: JSON-RPC errors that reject a request BEFORE execution (parse error,
#: invalid request, method not found, invalid params).
_JSONRPC_REJECTED_BEFORE_EXECUTION = frozenset({-32700, -32600, -32601, -32602})
#: Exact-run statuses after which a run is done (donor OrchestrationV2RunStatus
#: + the interrupt tool's settled outcomes).
_T3_RUN_DONE_STATUSES = frozenset({
    "completed", "failed", "cancelled", "interrupted", "rolled_back",
})
_T3_RESULT_MAX_PAGES = 20


def t3_mcp_upstream_namespace(access_token: str) -> str:
    """The upstream request namespace a T3 MCP bearer token authenticates as.

    Donor fact (``McpOAuth.ts``): every MCP tool call runs under
    ``requestNamespace = "client:" + <auth session id>``, and the bearer
    token's signed claims payload carries that session id as ``sid``
    (``SessionStore.ts`` issue: ``base64url(JSON claims) + "." + signature``).
    This decodes the claims to project WHICH session the token is — the
    server still verifies the signature on every call; nothing here grants
    anything.  Only MCP-client bearer sessions are accepted.  The token is
    never stored, logged or echoed (errors name no token material).
    """
    if not isinstance(access_token, str) or access_token.count(".") != 1:
        raise T3NamespaceAttestationError(
            "MCP access token is not a session token; cannot attest its namespace",
            reason="UNREADABLE_TOKEN",
        )
    encoded = access_token.split(".", 1)[0]
    try:
        raw = base64.urlsafe_b64decode(
            (encoded + "=" * (-len(encoded) % 4)).encode("ascii")
        )
        claims = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeError) as exc:
        raise T3NamespaceAttestationError(
            "MCP access token claims are unreadable; cannot attest its namespace",
            reason="UNREADABLE_TOKEN",
        ) from exc
    if not isinstance(claims, dict):
        raise T3NamespaceAttestationError(
            "MCP access token claims are malformed", reason="UNREADABLE_TOKEN",
        )
    sid = claims.get("sid")
    if (
        claims.get("kind") != "session"
        or claims.get("sub") != T3_MCP_CLIENT_SUBJECT
        or claims.get("method", "bearer-access-token") != "bearer-access-token"
        or not isinstance(sid, str)
        or not sid.strip()
    ):
        raise T3NamespaceAttestationError(
            "token is not an MCP-client bearer session; cannot attest its "
            "upstream namespace",
            reason="NOT_AN_MCP_CLIENT_SESSION",
        )
    return f"client:{sid.strip()}"


def t3_expected_launch_thread_id(upstream_namespace: str, client_request_id: str) -> str:
    """The thread id upstream derives for ``(namespace, clientRequestId)``.

    Donor fact (``mcp/toolkits/project/handlers.ts`` ``launchCommandId``):
    ``commandId = "mcp:launch:" + hex(sha256(JSON.stringify([namespace,
    key])))`` and ``threadId = commandId``.  A launch reply whose
    ``threadId`` equals this value is UPSTREAM evidence that the command ran
    under exactly that namespace and key — the only source this port uses
    for the receipt's echo fields (never the request envelope).
    """
    payload = json.dumps(
        [upstream_namespace, client_request_id], separators=(",", ":"),
        ensure_ascii=False,
    )
    return "mcp:launch:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def t3_native_run_coordinates(ref: WorkerProcessRef) -> tuple[str, str]:
    """``(threadId, native runId)`` of an adapter-issued neutral ref.

    The adapter builds ``process_start_identity = "t3:<threadId>:<runId>"``
    and ``provider_session_id = <threadId>`` from the persisted receipt
    (thread ids contain ``:``, so the run id is the suffix after the known
    thread id, never a naive split).  Exact-run interrupts need both (audit
    #7): without ``runId`` upstream interrupts the NEWEST running turn.
    """
    thread_id = str(getattr(ref, "provider_session_id", "") or "")
    identity = str(getattr(ref, "process_start_identity", "") or "")
    prefix = f"t3:{thread_id}:"
    if not thread_id or not identity.startswith(prefix) or len(identity) == len(prefix):
        raise T3PortRefusalError(
            "ref carries no exact T3 (threadId, runId) coordinates; refusing a "
            "non-exact-run operation"
        )
    return thread_id, identity[len(prefix):]


class T3McpTransportError(Exception):
    """A typed MCP tool transport failure, classified by WHEN it happened.

    ``phase="pre_send"``: the request provably never left (connection
    refused, DNS failure, request build error).  ``phase="after_send"``: it
    may have been delivered (timeout, connection reset, 5xx, garbled reply).
    ``http_status`` / ``rpc_code`` / ``tool_error`` carry explicit upstream
    answers.  Transports raise this; the port classifies it.
    """

    PRE_SEND = "pre_send"
    AFTER_SEND = "after_send"

    def __init__(
        self,
        message: str,
        *,
        phase: str,
        http_status: int | None = None,
        rpc_code: int | None = None,
        tool_error: bool = False,
    ) -> None:
        if phase not in (self.PRE_SEND, self.AFTER_SEND):
            raise ValueError(f"unknown transport failure phase {phase!r}")
        super().__init__(message)
        self.phase = phase
        self.http_status = http_status
        self.rpc_code = rpc_code
        self.tool_error = tool_error


def t3_mcp_failure_is_definitive_refusal(exc: T3McpTransportError) -> bool:
    """True only when the failure proves the native call took NO effect.

    Audit #4: clean refusals are ONLY pre-send failures and explicit upstream
    refusals — a 4xx (except 408 Request Timeout), a JSON-RPC rejection
    before execution, or the tool's own ``isError`` answer.  Timeouts,
    connection resets, 5xx-after-send and unparsable replies are UNKNOWN
    outcomes (the launch intent must be kept).
    """
    if exc.phase == T3McpTransportError.PRE_SEND:
        return True
    if exc.tool_error:
        return True
    if exc.http_status is not None:
        return 400 <= int(exc.http_status) < 500 and int(exc.http_status) != 408
    if exc.rpc_code is not None:
        return int(exc.rpc_code) in _JSONRPC_REJECTED_BEFORE_EXECUTION
    return False


class T3McpToolPort:
    """Reference :class:`T3NativeClientPort` over T3's MCP thread tools.

    * ``authenticated_namespace`` attests the upstream MCP client session
      (``client:<sid>``, from the token claims) — the identity upstream
      launch idempotency is really scoped by (audit #3);
    * launch/replay refuse (pre-send) an envelope whose namespace this
      client is not authenticated as; receipt echo fields are set ONLY when
      the upstream ``threadId`` proves ``(namespace, key)``
      (:func:`t3_expected_launch_thread_id`), never copied from the request;
      ``created_at`` is never a local clock (replays reproduce the ref);
    * transport failures are classified (audit #4): pre-send and explicit
      upstream refusals are clean refusals; everything after send is
      :class:`T3UnknownOutcomeError`;
    * reads report the EXACT run's status from ``recentRuns`` (never the
      thread status), and ``read_result`` is the dedicated terminal read
      whose ``result_ref`` names the run's final assistant item — never a
      bare thread id (audit #13);
    * ``interrupt_run`` sends ``threadId`` AND the native ``runId`` (audit #7)
      and verifies the upstream echo of both.
    """

    def __init__(
        self,
        call_tool: Callable[[str, Mapping[str, Any]], Mapping[str, Any]],
        *,
        upstream_namespace: str,
        launch_arguments: Mapping[str, Any] | None = None,
    ) -> None:
        if not callable(call_tool):
            raise T3ExecutionAdapterError("T3McpToolPort requires a call_tool transport")
        namespace = str(upstream_namespace or "").strip()
        if not namespace.startswith("client:") or namespace == "client:":
            raise T3NamespaceAttestationError(
                "T3McpToolPort requires the attested upstream namespace "
                "'client:<session id>'",
                reason="UNATTESTED",
            )
        self._call_tool = call_tool
        self._upstream_namespace = namespace
        self._launch_arguments = dict(launch_arguments or {})
        self.calls: list[dict[str, Any]] = []

    @classmethod
    def from_access_token(
        cls,
        call_tool: Callable[[str, Mapping[str, Any]], Mapping[str, Any]],
        access_token: str,
        **kwargs: Any,
    ) -> "T3McpToolPort":
        """Attest the namespace from the bearer token; the token is not kept."""
        return cls(
            call_tool, upstream_namespace=t3_mcp_upstream_namespace(access_token),
            **kwargs,
        )

    # -- principal -------------------------------------------------------------

    def authenticated_namespace(self) -> str:
        return self._upstream_namespace

    # -- transport classification ---------------------------------------------

    def _invoke(
        self, tool: str, arguments: Mapping[str, Any], *, mutating: bool
    ) -> Mapping[str, Any]:
        try:
            payload = self._call_tool(tool, dict(arguments))
        except T3UnknownOutcomeError:
            raise
        except T3McpTransportError as exc:
            if t3_mcp_failure_is_definitive_refusal(exc):
                raise T3PortRefusalError(f"{tool} refused: {exc}") from exc
            raise T3UnknownOutcomeError(
                f"{tool} outcome unknown (failure after send): {exc}"
            ) from exc
        except Exception as exc:
            if mutating:
                # Unclassified failure of a mutating call: it may have been
                # delivered — never a clean refusal.
                raise T3UnknownOutcomeError(
                    f"{tool} failed with an unclassified transport error: {exc}"
                ) from exc
            raise T3PortRefusalError(f"{tool} failed: {exc}") from exc
        if not isinstance(payload, Mapping):
            if mutating:
                raise T3UnknownOutcomeError(f"{tool} reply is unparsable")
            raise T3PortRefusalError(f"{tool} reply is unparsable")
        return payload

    # -- launch / replay -------------------------------------------------------

    async def launch_thread(self, envelope: T3ThreadLaunchEnvelope) -> T3ThreadLaunchReceipt:
        return self._launch(envelope, "launch")

    async def replay_launch(self, envelope: T3ThreadLaunchEnvelope) -> T3ThreadLaunchReceipt:
        # Same tool, same key, same authenticated session: upstream replays
        # the ORIGINAL thread (``getThreadShell(threadId)`` replay branch).
        return self._launch(envelope, "replay")

    def _launch(self, envelope: T3ThreadLaunchEnvelope, op: str) -> T3ThreadLaunchReceipt:
        expected_namespace = t3_request_namespace(self._upstream_namespace)
        if envelope.request_namespace != expected_namespace:
            raise T3PortRefusalError(
                f"refusing to {op} an envelope for namespace "
                f"{envelope.request_namespace!r}: this client is authenticated "
                f"as {expected_namespace!r} (nothing was sent)"
            )
        key = str(envelope.client_request_id or "")
        if not key:
            raise T3PortRefusalError(f"refusing to {op} without a clientRequestId")
        arguments: dict[str, Any] = dict(self._launch_arguments)
        arguments.update(
            title=envelope.title, message=envelope.message, clientRequestId=key,
        )
        if envelope.model_selection:
            selection = envelope.model_selection.strip()
            if selection.startswith("{"):
                try:
                    arguments["modelSelection"] = json.loads(selection)
                except ValueError as exc:
                    raise T3PortRefusalError(
                        "envelope modelSelection is not valid JSON (nothing was sent)"
                    ) from exc
            else:
                arguments["modelSelection"] = {"instanceId": selection}
        self.calls.append({"op": op, "clientRequestId": key})
        payload = self._invoke("t3_thread_launch", arguments, mutating=True)
        thread_id = str(payload.get("threadId") or "")
        proven = bool(thread_id) and thread_id == t3_expected_launch_thread_id(
            self._upstream_namespace, key
        )
        return T3ThreadLaunchReceipt(
            thread_id=thread_id,
            run_id=str(payload.get("runId") or ""),
            project_id=str(payload.get("projectId") or ""),
            status=str(payload.get("status") or ""),
            link=str(payload.get("link") or ""),
            created_at="",
            request_namespace=expected_namespace if proven else "",
            client_request_id=key if proven else "",
        )

    # -- reads -----------------------------------------------------------------

    @staticmethod
    def _exact_run(payload: Mapping[str, Any], run_id: str) -> Mapping[str, Any] | None:
        for entry in payload.get("recentRuns") or ():
            if isinstance(entry, Mapping) and str(entry.get("runId") or "") == run_id:
                return entry
        return None

    @staticmethod
    def _require_thread(payload: Mapping[str, Any], thread_id: str) -> None:
        thread = payload.get("thread")
        if isinstance(thread, Mapping):
            echoed = thread.get("threadId") or thread.get("id")
            if echoed is not None and str(echoed) != thread_id:
                raise T3PortRefusalError(
                    "thread read returned a different thread; refusing a replacement"
                )

    async def read_thread(
        self, thread_id: str, run_id: str, cursor: str
    ) -> T3ThreadReadResult:
        arguments: dict[str, Any] = {
            "threadId": thread_id, "view": "messages", "limit": 20,
            "maxCharsPerItem": 4000, "runLimit": 10,
        }
        if cursor:
            if not _DECIMAL_CURSOR.fullmatch(cursor):
                raise T3PortRefusalError(f"cursor {cursor!r} is not a T3 position")
            arguments["afterPosition"] = int(cursor)
        self.calls.append({"op": "read", "threadId": thread_id, "cursor": cursor})
        payload = self._invoke("t3_thread_read", arguments, mutating=False)
        self._require_thread(payload, thread_id)
        run = self._exact_run(payload, run_id)
        next_position = payload.get("nextPosition")
        items = payload.get("items") or ()
        return T3ThreadReadResult(
            thread_id=thread_id,
            run_id=run_id,
            # The EXACT run's status, never the thread's; an unlisted run is
            # unknown (non-terminal), never guessed.
            native_status=str(run.get("status") or "") if run is not None else "",
            cursor=cursor,
            next_cursor=(
                str(next_position)
                if isinstance(next_position, int) and not isinstance(next_position, bool)
                and next_position >= 0
                else ""
            ),
            result_ref="",
            result_payload={"item_count": len(items)},
            started_at=str((run or {}).get("startedAt") or ""),
            finished_at=str((run or {}).get("completedAt") or ""),
            has_more=bool(payload.get("hasMore")),
        )

    async def read_result(self, thread_id: str, run_id: str) -> T3ThreadReadResult:
        """Dedicated terminal read: the exact run's final assistant item.

        Pages from the HEAD of the thread (never the incremental status
        cursor) and keeps the LAST ``assistant_message`` item whose ``runId``
        is the exact run.  ``result_ref`` names that upstream item; with no
        such item it is ``""`` and the adapter refuses to collect.
        """
        position: int | None = None
        final_item: Mapping[str, Any] | None = None
        run: Mapping[str, Any] | None = None
        for _ in range(_T3_RESULT_MAX_PAGES):
            arguments: dict[str, Any] = {
                "threadId": thread_id, "view": "messages", "limit": 50,
                "maxCharsPerItem": 20000, "runLimit": 10,
            }
            if position is not None:
                arguments["afterPosition"] = position
            self.calls.append({"op": "read_result", "threadId": thread_id})
            payload = self._invoke("t3_thread_read", arguments, mutating=False)
            self._require_thread(payload, thread_id)
            run = self._exact_run(payload, run_id) or run
            for item in payload.get("items") or ():
                if (
                    isinstance(item, Mapping)
                    and str(item.get("runId") or "") == run_id
                    and item.get("type") == "assistant_message"
                    and isinstance(item.get("text"), str)
                    and item.get("text")
                ):
                    final_item = item
            next_position = payload.get("nextPosition")
            if (
                not payload.get("hasMore")
                or not isinstance(next_position, int)
                or (position is not None and next_position <= position)
            ):
                break
            position = next_position
        item_id = str((final_item or {}).get("itemId") or "")
        result_ref = (
            f"t3://thread/{thread_id}/run/{run_id}/item/{item_id}" if item_id else ""
        )
        text = str((final_item or {}).get("text") or "")
        return T3ThreadReadResult(
            thread_id=thread_id,
            run_id=run_id,
            native_status=str(run.get("status") or "") if run is not None else "",
            result_ref=result_ref,
            result_payload=(
                {
                    "text": text[-4000:],
                    "item_id": item_id,
                    "text_truncated": bool((final_item or {}).get("textTruncated"))
                    or len(text) > 4000,
                }
                if item_id else {}
            ),
            started_at=str((run or {}).get("startedAt") or ""),
            finished_at=str((run or {}).get("completedAt") or ""),
        )

    # -- interrupt -------------------------------------------------------------

    async def interrupt_run(self, ref: WorkerProcessRef, reason: str) -> T3InterruptOutcome:
        thread_id, run_id = t3_native_run_coordinates(ref)
        arguments = {"threadId": thread_id, "runId": run_id, "reason": str(reason)[:2000]}
        self.calls.append({"op": "interrupt", "threadId": thread_id, "runId": run_id})
        payload = self._invoke("t3_thread_interrupt", arguments, mutating=True)
        echoed_thread = payload.get("threadId")
        echoed_run = payload.get("runId")
        if (echoed_thread is not None and str(echoed_thread) != thread_id) or (
            echoed_run is not None and str(echoed_run) != run_id
        ):
            raise T3UnknownOutcomeError(
                "interrupt reply names a different thread/run than the exact "
                "run requested; outcome unknown"
            )
        status = str(payload.get("status") or "")
        return T3InterruptOutcome(
            requested=status == "interrupt_requested",
            settled=False,
            already_exited=bool(status) and status != "interrupt_requested",
            observed_native_status=status if status in _T3_RUN_DONE_STATUSES else "",
            finished_at="",
        )


__all__ = [
    "InMemoryT3AdapterStateStore",
    "SQLiteT3AdapterStateStore",
    "T3_MCP_CLIENT_SUBJECT",
    "T3BindingJoinDriftError",
    "T3LaunchClaimConflictError",
    "T3McpToolPort",
    "T3McpTransportError",
    "T3NamespaceAttestationError",
    "T3PortRefusalError",
    "T3ResultLedgerConflictError",
    "T3StateStoreError",
    "t3_expected_launch_thread_id",
    "t3_mcp_failure_is_definitive_refusal",
    "t3_mcp_upstream_namespace",
    "t3_native_run_coordinates",
    "T3_ADAPTER_STATE_SCHEMA",
    "T3_INTERRUPT_OUTCOME_SCHEMA",
    "T3_LAUNCH_ENVELOPE_SCHEMA",
    "T3_LAUNCH_INTENT_SCHEMA",
    "T3_LAUNCH_RECEIPT_SCHEMA",
    "T3_NATIVE_ADAPTER_ID",
    "T3_REQUEST_NAMESPACE",
    "T3_RESULT_REFERENCE_SCHEMA",
    "T3_THREAD_READ_SCHEMA",
    "T3AdapterRunState",
    "T3AdapterStateStore",
    "T3CancelReport",
    "T3ExecutionAdapter",
    "T3ExecutionAdapterError",
    "T3InterruptOutcome",
    "T3LaunchEffectUnknownError",
    "T3LaunchIntent",
    "T3NativeClientPort",
    "T3ResultReference",
    "T3ThreadLaunchEnvelope",
    "T3ThreadLaunchReceipt",
    "T3ThreadReadResult",
    "T3UnknownOutcomeError",
    "default_t3_adapter_state_path",
    "executive_runtime_db_path",
    "derive_t3_client_request_id",
    "t3_request_namespace",
]
