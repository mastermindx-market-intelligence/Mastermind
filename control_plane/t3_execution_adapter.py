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
  ``clientRequestId`` under two different OAuth clients minting two DIFFERENT
  threads.  Ports that can report their principal (``authenticated_namespace``)
  run under the principal-qualified namespace from
  :func:`t3_request_namespace`; the qualified namespace is persisted with
  the intent and receipt, replayed verbatim, and any reattach under a
  DIFFERENT principal is refused.

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

import dataclasses
import hashlib
import json
import sqlite3
import threading
import time
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

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
#: The persisted idempotency namespace for every launch this adapter mints.
#: The key inside it is derived per binding (never caller-supplied, never
#: regenerated on replay).  This is the LEGACY FIXED namespace: it identifies
#: the adapter, not the authenticated caller.  Upstream command identity is
#: ``(authenticated principal, namespace, key)`` — the live proof (Rev 5
#: finding 1) showed the SAME ``clientRequestId`` under two different OAuth
#: clients minting two DIFFERENT T3 threads — so a port that can report its
#: authenticated principal runs under the PRINCIPAL-QUALIFIED namespace from
#: :func:`t3_request_namespace`, and that qualified namespace is what gets
#: persisted with the intent and receipt and replayed verbatim.
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


@runtime_checkable
class T3AdapterStateStore(Protocol):
    """Durable state seam for :class:`T3ExecutionAdapter`.

    One row per run; every method is synchronous and fail-closed (a store
    error surfaces, never a silent skip).  ``put_launch_intent`` must
    complete BEFORE the native launch call and ``put_launch_receipt`` BEFORE
    the start ACK — the adapter's ordering discipline depends on the store
    actually persisting at call time, which is what the SQLite
    implementation does (its own ``BEGIN IMMEDIATE`` transaction per write).
    """

    def load_run(self, run_id: str) -> T3AdapterRunState | None: ...
    def run_ids(self) -> tuple[str, ...]: ...
    def put_launch_intent(
        self,
        intent: T3LaunchIntent,
        *,
        binding: ExecutionBinding,
        spec: WorkerLaunchSpec,
    ) -> None: ...
    def clear_launch_attempt(self, run_id: str) -> None: ...
    def put_launch_receipt(
        self,
        run_id: str,
        *,
        receipt: T3ThreadLaunchReceipt,
        original_ref: WorkerProcessRef,
        cursor: str = "",
        spec: WorkerLaunchSpec | None = None,
    ) -> None: ...
    def put_cursor(self, run_id: str, cursor: str) -> None: ...
    def put_cancel_record(self, run_id: str, record: _T3CancelLedgerEntry) -> None: ...
    def put_result_reference(self, reference: T3ResultReference) -> None: ...


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


# WorkerLaunchSpec field categories for exact round-trip reconstruction.
# Unknown fields in durable rows raise (drift is caught loudly, never
# silently dropped); fields absent from a row fall back to dataclass
# defaults (a field added after the row was written).
_SPEC_PATH_FIELDS = frozenset({
    "workspace_path", "run_dir", "result_schema_path",
})
_SPEC_PATH_TUPLE_FIELDS = frozenset({
    "allowed_artifact_paths", "isolation_roots", "isolation_denied_paths",
    "forbidden_paths",
})
_SPEC_STR_TUPLE_FIELDS = frozenset({"authorities"})
_SPEC_MAPPING_FIELDS = frozenset({
    "isolation_manifest", "secret_canary_verdict", "subscription_canary_claim",
})
_SPEC_FIELD_NAMES = frozenset(
    field.name for field in dataclasses.fields(WorkerLaunchSpec)
) | _SPEC_PATH_FIELDS | _SPEC_PATH_TUPLE_FIELDS | _SPEC_STR_TUPLE_FIELDS | _SPEC_MAPPING_FIELDS


def _t3_spec_from_json(raw: Any) -> WorkerLaunchSpec:
    payload = dict(_require_object(raw, "launch spec"))
    unknown = set(payload) - _SPEC_FIELD_NAMES
    if unknown:
        raise T3ExecutionAdapterError(
            f"durable t3 launch spec carries unknown fields: {sorted(unknown)}"
        )
    kwargs: dict[str, Any] = {}
    for name, value in payload.items():
        if name in _SPEC_PATH_FIELDS:
            kwargs[name] = Path(value)
        elif name in _SPEC_PATH_TUPLE_FIELDS:
            kwargs[name] = tuple(Path(item) for item in value)
        elif name in _SPEC_STR_TUPLE_FIELDS:
            kwargs[name] = tuple(value)
        else:
            kwargs[name] = value
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
    )


class InMemoryT3AdapterStateStore:
    """Non-durable in-memory store: the test double and the default fallback.

    Constructing a :class:`T3ExecutionAdapter` without a store uses this, so
    the adapter's own-path behavior is unchanged for callers that have not
    composed a durable store yet (selection is still a deployment act).  It
    satisfies the same protocol as the SQLite store, so tests exercise the
    identical seam.  It is NOT durable: process death loses everything, and
    every durability property is only as strong as the store actually used.
    """

    def __init__(self) -> None:
        self._runs: dict[str, dict[str, Any]] = {}

    def load_run(self, run_id: str) -> T3AdapterRunState | None:
        row = self._runs.get(str(run_id))
        if row is None:
            return None
        # Values are stored pre-serialized so the in-memory double exercises
        # the same reconstruction path as the SQLite store.
        return _row_to_run_state(
            {
                "run_id": str(run_id),
                "intent_json": row.get("intent_json"),
                "receipt_json": row.get("receipt_json"),
                "original_ref_json": row.get("original_ref_json"),
                "binding_json": row.get("binding_json"),
                "spec_json": row.get("spec_json"),
                "cursor_text": row.get("cursor_text", ""),
                "cancel_json": row.get("cancel_json"),
                "result_ref_json": row.get("result_ref_json"),
            }
        )

    def run_ids(self) -> tuple[str, ...]:
        return tuple(self._runs)

    def put_launch_intent(
        self,
        intent: T3LaunchIntent,
        *,
        binding: ExecutionBinding,
        spec: WorkerLaunchSpec,
    ) -> None:
        row = self._runs.setdefault(
            intent.run_id,
            {
                "intent_json": None, "receipt_json": None,
                "original_ref_json": None, "binding_json": None,
                "spec_json": None, "cursor_text": "",
                "cancel_json": None, "result_ref_json": None,
            },
        )
        row["intent_json"] = _canonical_state_json(intent)
        row["binding_json"] = _canonical_state_json(binding)
        row["spec_json"] = _canonical_state_json(spec)

    def clear_launch_attempt(self, run_id: str) -> None:
        row = self._runs.get(str(run_id))
        if row is None:
            return
        if row.get("receipt_json") or row.get("original_ref_json"):
            raise T3ExecutionAdapterError(
                f"refusing to clear launch attempt for run {run_id!r}: a native "
                "receipt is already persisted (possible effect)"
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
    ) -> None:
        row = self._runs.setdefault(
            str(run_id),
            {
                "intent_json": None, "receipt_json": None,
                "original_ref_json": None, "binding_json": None,
                "spec_json": None, "cursor_text": "",
                "cancel_json": None, "result_ref_json": None,
            },
        )
        row["receipt_json"] = _canonical_state_json(receipt)
        row["original_ref_json"] = _canonical_state_json(original_ref)
        if cursor:
            row["cursor_text"] = cursor
        if spec is not None:
            row["spec_json"] = _canonical_state_json(spec)

    def put_cursor(self, run_id: str, cursor: str) -> None:
        row = self._require_row(run_id, "put_cursor")
        row["cursor_text"] = str(cursor)

    def put_cancel_record(self, run_id: str, record: _T3CancelLedgerEntry) -> None:
        row = self._require_row(run_id, "put_cancel_record")
        row["cancel_json"] = _canonical_state_json(record)

    def put_result_reference(self, reference: T3ResultReference) -> None:
        row = self._require_row(reference.run_id, "put_result_reference")
        row["result_ref_json"] = _canonical_state_json(reference)

    def _require_row(self, run_id: str, operation: str) -> dict[str, Any]:
        row = self._runs.get(str(run_id))
        if row is None:
            raise T3ExecutionAdapterError(
                f"{operation} requires a persisted launch intent for run "
                f"{run_id!r} first"
            )
        return row


class SQLiteT3AdapterStateStore:
    """SQLite-backed durable adapter state (the ``WorkspaceLeaseStore`` pattern).

    One row per run in the ``t3_adapter_runs`` table: sqlite3,
    ``isolation_level=None``, explicit ``BEGIN IMMEDIATE`` per write,
    ``row_factory=sqlite3.Row``.  The DOCUMENTED DEFAULT file path is the
    sibling file ``data/control_plane/t3_adapter_state.sqlite3`` in the
    Executive-owned data directory (see ``_T3_ADAPTER_STATE_DB_RELATIVE_PATH``
    for why it must not be the Executive runtime's own file).  The connection
    does not switch the journal mode (whole-file property; left to the file's
    owner — ``busy_timeout`` is connection-local and safe).  Opening the store
    on the Executive runtime's file is refused outright.

    Writes are synchronous: each ``put_*`` completes its transaction before
    returning, which is what makes "persisted BEFORE the native call / BEFORE
    the ACK" a real durable fact rather than a comment.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        if not str(self.path):
            raise T3ExecutionAdapterError("t3 adapter state store path is empty")
        if self.path.name == _EXECUTIVE_RUNTIME_DB_RELATIVE_PATH.name:
            # The Executive runtime refuses to open its file when any foreign
            # table changes its pinned whole-file schema digest; sharing the
            # file would brick the runtime.  Fail closed here instead.
            raise T3ExecutionAdapterError(
                "t3 adapter state store must not live inside the Executive "
                "runtime's own SQLite file (its reviewed schema digest is "
                "pinned); use the sibling default path"
            )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._connection = sqlite3.connect(
            str(self.path), timeout=30.0, isolation_level=None,
            check_same_thread=False,
        )
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA busy_timeout=10000")
        self._connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS t3_adapter_runs (
                run_id TEXT PRIMARY KEY,
                intent_json TEXT,
                receipt_json TEXT,
                original_ref_json TEXT,
                binding_json TEXT,
                spec_json TEXT,
                cursor_text TEXT NOT NULL DEFAULT '',
                cancel_json TEXT,
                result_ref_json TEXT,
                schema_version TEXT NOT NULL DEFAULT 'mastermind.t3_adapter_state/v1',
                updated_ms INTEGER NOT NULL
            );
            """
        )

    def close(self) -> None:
        self._connection.close()

    # -- internals -----------------------------------------------------------

    def _write(self, sql: str, params: tuple) -> None:
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                self._connection.execute(sql, params)
            except BaseException:
                self._connection.execute("ROLLBACK")
                raise
            self._connection.execute("COMMIT")

    def _require_row(self, run_id: str, operation: str) -> sqlite3.Row:
        row = self._connection.execute(
            "SELECT * FROM t3_adapter_runs WHERE run_id=?", (str(run_id),)
        ).fetchone()
        if row is None:
            raise T3ExecutionAdapterError(
                f"{operation} requires a persisted launch intent for run "
                f"{run_id!r} first"
            )
        return row

    # -- protocol surface ----------------------------------------------------

    def load_run(self, run_id: str) -> T3AdapterRunState | None:
        row = self._connection.execute(
            "SELECT * FROM t3_adapter_runs WHERE run_id=?", (str(run_id),)
        ).fetchone()
        if row is None:
            return None
        return _row_to_run_state(row)

    def run_ids(self) -> tuple[str, ...]:
        rows = self._connection.execute(
            "SELECT run_id FROM t3_adapter_runs ORDER BY rowid"
        ).fetchall()
        return tuple(row["run_id"] for row in rows)

    def put_launch_intent(
        self,
        intent: T3LaunchIntent,
        *,
        binding: ExecutionBinding,
        spec: WorkerLaunchSpec,
    ) -> None:
        now_ms = int(time.monotonic_ns() // 1_000_000)
        self._write(
            "INSERT INTO t3_adapter_runs"
            " (run_id, intent_json, binding_json, spec_json, cursor_text,"
            "  schema_version, updated_ms)"
            " VALUES (?,?,?,?,?,'mastermind.t3_adapter_state/v1',?)"
            " ON CONFLICT(run_id) DO UPDATE SET"
            "  intent_json=excluded.intent_json,"
            "  binding_json=excluded.binding_json,"
            "  spec_json=excluded.spec_json,"
            "  updated_ms=excluded.updated_ms",
            (
                intent.run_id,
                _canonical_state_json(intent),
                _canonical_state_json(binding),
                _canonical_state_json(spec),
                "",
                now_ms,
            ),
        )

    def clear_launch_attempt(self, run_id: str) -> None:
        # Only an attempt that never reached a receipt may be cleared; a
        # persisted receipt means a possible native effect and is immutable.
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                cursor = self._connection.execute(
                    "DELETE FROM t3_adapter_runs WHERE run_id=?"
                    " AND receipt_json IS NULL AND original_ref_json IS NULL",
                    (str(run_id),),
                )
                deleted = cursor.rowcount
            except BaseException:
                self._connection.execute("ROLLBACK")
                raise
            self._connection.execute("COMMIT")
        if not deleted:
            row = self._connection.execute(
                "SELECT receipt_json FROM t3_adapter_runs WHERE run_id=?",
                (str(run_id),),
            ).fetchone()
            if row is not None and row["receipt_json"]:
                raise T3ExecutionAdapterError(
                    f"refusing to clear launch attempt for run {run_id!r}: a "
                    "native receipt is already persisted (possible effect)"
                )

    def put_launch_receipt(
        self,
        run_id: str,
        *,
        receipt: T3ThreadLaunchReceipt,
        original_ref: WorkerProcessRef,
        cursor: str = "",
        spec: WorkerLaunchSpec | None = None,
    ) -> None:
        # Upsert by design: adoption of a PRE-durability recovery binding
        # (no persisted intent row) persists what recovery learned — the
        # receipt, the adopted original ref and the validated spec.
        now_ms = int(time.monotonic_ns() // 1_000_000)
        self._write(
            "INSERT INTO t3_adapter_runs"
            " (run_id, receipt_json, original_ref_json, spec_json,"
            "  cursor_text, schema_version, updated_ms)"
            " VALUES (?,?,?,?,?,'mastermind.t3_adapter_state/v1',?)"
            " ON CONFLICT(run_id) DO UPDATE SET"
            "  receipt_json=excluded.receipt_json,"
            "  original_ref_json=excluded.original_ref_json,"
            "  spec_json=COALESCE(excluded.spec_json, t3_adapter_runs.spec_json),"
            "  cursor_text=CASE WHEN excluded.cursor_text!=''"
            "   THEN excluded.cursor_text ELSE t3_adapter_runs.cursor_text END,"
            "  updated_ms=excluded.updated_ms",
            (
                str(run_id),
                _canonical_state_json(receipt),
                _canonical_state_json(original_ref),
                _canonical_state_json(spec) if spec is not None else None,
                str(cursor),
                now_ms,
            ),
        )

    def put_cursor(self, run_id: str, cursor: str) -> None:
        self._require_row(run_id, "put_cursor")
        now_ms = int(time.monotonic_ns() // 1_000_000)
        self._write(
            "UPDATE t3_adapter_runs SET cursor_text=?, updated_ms=? WHERE run_id=?",
            (str(cursor), now_ms, str(run_id)),
        )

    def put_cancel_record(self, run_id: str, record: _T3CancelLedgerEntry) -> None:
        self._require_row(run_id, "put_cancel_record")
        now_ms = int(time.monotonic_ns() // 1_000_000)
        self._write(
            "UPDATE t3_adapter_runs SET cancel_json=?, updated_ms=? WHERE run_id=?",
            (_canonical_state_json(record), now_ms, str(run_id)),
        )

    def put_result_reference(self, reference: T3ResultReference) -> None:
        self._require_row(reference.run_id, "put_result_reference")
        now_ms = int(time.monotonic_ns() // 1_000_000)
        self._write(
            "UPDATE t3_adapter_runs SET result_ref_json=?, updated_ms=?"
            " WHERE run_id=?",
            (_canonical_state_json(reference), now_ms, reference.run_id),
        )


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

    ``authenticated_namespace`` (OPTIONAL at runtime, checked with
    ``getattr``): the port's authenticated principal / OAuth client
    namespace — the identity upstream command idempotency is really scoped
    by.  The live proof (Rev 5 finding 1) showed the same
    ``clientRequestId`` under two different OAuth clients minting two
    different threads, so a port that CAN report its principal must, and
    the adapter then (a) qualifies the request namespace with it, (b)
    persists the qualified namespace with the intent and receipt, and (c)
    REFUSES any reattach whose current principal differs from the
    persisted one.  A port that cannot report a principal runs under the
    legacy fixed namespace (documented, not guessed).
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
    adapter constructed on the same store (a simulated cold restart)
    reattaches the SAME execution with the launch count still one.
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
        # store SYNCHRONOUSLY at its ordering point (intent BEFORE the
        # native call; receipt + original ref BEFORE the ACK; cursor only
        # after a successful read).
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

        Refuses fail-closed without a valid, current ``ExecutionBinding``.
        The launch intent (with the authenticated-principal-qualified
        request namespace) is persisted BEFORE any native call; the receipt
        and the original neutral ref are persisted BEFORE the returned ref
        acknowledges start.
        """
        if not isinstance(spec, WorkerLaunchSpec):
            raise T3ExecutionAdapterError("start requires a WorkerLaunchSpec")
        run = self._state.load_run(spec.run_id)
        if run is not None and run.original_ref is not None:
            raise T3ExecutionAdapterError(
                "run was already started; reattach recovers the same execution "
                "instead of starting a replacement"
            )
        if run is not None and run.intent is not None:
            # An intent is persisted (including the effect-unknown zone):
            # start never retries — reattach replays the SAME key+namespace.
            raise T3ExecutionAdapterError(
                f"run {spec.run_id!r} already has a persisted launch intent; "
                "start never retries — reattach recovers the SAME execution "
                "under the SAME clientRequestId"
            )
        binding = self._require_current_binding(spec)
        client_request_id = derive_t3_client_request_id(binding)
        namespace = self._current_request_namespace(binding)
        envelope = self._launch_envelope(spec, client_request_id, namespace)
        intent = T3LaunchIntent(
            run_id=spec.run_id,
            client_request_id=client_request_id,
            request_namespace=namespace,
            adapter_id=T3_NATIVE_ADAPTER_ID,
            envelope=envelope,
            created_at=envelope.created_at,
        )
        # PERSIST the launch intent (with the binding + spec) BEFORE any
        # native call — the store's transaction must complete first.
        self._state.put_launch_intent(intent, binding=binding, spec=spec)
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
            # did NOT happen.  Roll the intent back so a retry derives the
            # SAME deterministic key (upstream idempotency keeps it one
            # logical command); never a new key.
            self._state.clear_launch_attempt(spec.run_id)
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
        # Persist the receipt and the ORIGINAL ref BEFORE the ACK (the
        # return below).
        ref = self._neutral_process_ref(spec, receipt, client_request_id)
        self._state.put_launch_receipt(
            spec.run_id, receipt=receipt, original_ref=ref, cursor=""
        )
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
        """The port's authenticated principal / OAuth client namespace.

        Optional port seam (``authenticated_namespace``): a port that cannot
        report its principal returns ``""`` and the adapter runs under the
        legacy fixed namespace (documented, never guessed).  A port that
        reports a non-string or non-strip-able value is refused fail-closed.
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
        principal = value.strip()
        return principal

    def _port_request_namespace(self) -> str:
        """The namespace implied by the CURRENT port principal alone."""
        principal = self._port_authenticated_principal()
        return t3_request_namespace(principal) if principal else T3_REQUEST_NAMESPACE

    def _current_request_namespace(self, binding: ExecutionBinding) -> str:
        """The full request namespace for a NEW launch under ``binding``.

        Precedence: the port's authenticated principal (the credential that
        will actually make the native call — ground truth), then the
        binding's v1.1 ``caller_namespace`` (the broker's projection of the
        caller), then the legacy fixed namespace.
        """
        principal = self._port_authenticated_principal()
        if principal:
            return t3_request_namespace(principal)
        broker_namespace = str(getattr(binding, "caller_namespace", "") or "").strip()
        if broker_namespace:
            return t3_request_namespace(broker_namespace)
        return T3_REQUEST_NAMESPACE

    def _require_namespace_continuity(self, persisted_namespace: str) -> None:
        """Refuse recovery under a DIFFERENT authenticated principal.

        The live proof (Rev 5 finding 1) showed the same clientRequestId
        under two different OAuth clients minting two different threads:
        the authenticated principal is part of the idempotency identity, so
        a reattach whose CURRENT port principal differs from the persisted
        launch namespace would mint a replacement rather than recover the
        original — refused.  A port that cannot report its principal cannot
        be verified here; the persisted envelope is still replayed verbatim
        and the replayed thread is verified against the retained ref.
        """
        principal = self._port_authenticated_principal()
        if not principal:
            return
        persisted_principal = _namespace_principal(persisted_namespace)
        if persisted_principal and persisted_principal != principal:
            raise T3ExecutionAdapterError(
                "refused: recovery under a different authenticated namespace "
                f"({principal!r}) than the persisted launch namespace "
                f"({persisted_principal!r}); two OAuth clients are never the "
                "same idempotency identity — recover under the original "
                "principal"
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
        stderr paths.
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
        cursor; the cursor advances (persisted) only after a successful
        read.
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
        """Read the exact run's final state/result through the port.

        The canonical result reference is stored in the durable
        result-ledger BEFORE the CollectionReceipt is constructed or
        returned.  Reading T3 is NOT company acceptance — the ledger is
        evidence; acceptance is a separate downstream act.
        """
        run = self._require_run_state(ref)
        original = run.original_ref
        assert original is not None
        thread_id, native_run_id = self._native_coordinates(run)
        read = await self._read_exact(
            thread_id, native_run_id, run.cursor, original.run_id
        )
        state = _map_t3_status(read.native_status)
        if state not in _TERMINAL_STATES:
            raise T3ExecutionAdapterError(
                f"run {original.run_id!r} is not terminal; no final result to "
                "collect"
            )
        if not read.result_ref:
            raise T3ExecutionAdapterError(
                f"terminal read for run {original.run_id!r} carries no "
                "canonical result reference; refusing to collect"
            )
        # STORE the canonical result reference BEFORE constructing/returning
        # the CollectionReceipt (reading T3 is NOT company acceptance).
        self._state.put_result_reference(
            T3ResultReference(
                run_id=original.run_id,
                thread_id=thread_id,
                result_ref=read.result_ref,
                native_status=read.native_status,
                recorded_at=self._now_iso(),
            )
        )
        receipt = self._build_collection_receipt(original, read, state)
        return receipt

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
        identity match above is the only gate); staleness blocks NEW
        execution only (Rev 5 §3A/§7).
        """
        run = self._require_run_state(ref)
        original = run.original_ref
        assert original is not None
        if not isinstance(reason, str) or not reason.strip():
            raise T3ExecutionAdapterError("cancel requires a non-empty reason")
        try:
            outcome = await self._port.interrupt_run(original, reason)
        except T3UnknownOutcomeError as exc:
            # The interrupt request was made; whether it landed is unknown.
            # Record requested-but-unsettled honestly (without clobbering an
            # existing record), then surface the ambiguity — status()
            # reconciles once the native state shows.
            if run.cancel is None:
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
        self._state.put_cancel_record(
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
            finished_at=outcome.finished_at or now,
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
        including after a cold restart of the coordinator, because the
        retained ref is loaded from the durable state store.  Without one the
        SAME persisted launch command (same clientRequestId + namespace) is
        REPLAYED through ``replay_launch`` — upstream idempotent replay
        returns the ORIGINAL thread.  A replay that returns a different
        thread is refused, and recovery under a different authenticated
        namespace than the persisted one is refused (two OAuth clients are
        never the same idempotency identity).  ``launch_thread`` is never
        called from here.
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
        if binding.launch_spec_sha256 != worker_launch_spec_sha256(spec):
            raise T3ExecutionAdapterError(
                "recovery binding does not bind this launch spec"
            )
        run = self._state.load_run(spec.run_id)
        retained = run.original_ref if run is not None else None
        intent = run.intent if run is not None else None
        persisted_spec = run.spec if run is not None else None
        if intent is not None or retained is not None:
            # The persisted namespace is part of the idempotency identity.
            persisted_namespace = (
                intent.request_namespace if intent is not None
                else (run.receipt.request_namespace if run.receipt else "")
            )
            self._require_namespace_continuity(persisted_namespace)
        if persisted_spec is not None:
            # Adapter-side drift guard across restart: the caller's spec must
            # hash to the SAME persisted launch spec.
            if worker_launch_spec_sha256(spec) != worker_launch_spec_sha256(
                persisted_spec
            ):
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
            # Crash/lost ACK after intent persist: replay the persisted
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
        # comes from the ORIGINAL ref's launch_nonce, never regenerated.
        # Cross-provider/foreign threads are refused by the verification
        # below.
        key = original.launch_nonce
        if not key:
            raise T3ExecutionAdapterError(
                "recovery binding carries no original clientRequestId; "
                "refusing to replay without the SAME key"
            )
        envelope = self._reconstruct_envelope(spec, key)
        return await self._replay_and_adopt(spec, envelope, original, None)

    def _reconstruct_envelope(
        self, spec: WorkerLaunchSpec, client_request_id: str
    ) -> T3ThreadLaunchEnvelope:
        """Same namespace + SAME key; upstream identity is the (namespace, key)."""
        envelope = self._launch_envelope(
            spec, client_request_id, self._port_request_namespace()
        )
        return envelope

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
            # any other identity is a replacement — refused above by
            # _verify_replayed_thread; this second guard keeps the adoption
            # below honest.
            raise T3ExecutionAdapterError(
                "replay did not reproduce the original execution identity; "
                "refusing to adopt a replacement"
            )
        # When the original ref predates any known thread (crash between
        # intent persist and ACK), the replayed receipt IS the first learned
        # identity of the SAME execution: upstream idempotency under
        # (namespace, key) returned the original thread, and the key was
        # verified against the persisted intent above.
        run = self._state.load_run(spec.run_id)
        cursor = run.cursor if run is not None else ""
        # Persist the receipt, the adopted ORIGINAL ref and the validated
        # spec BEFORE the ACK (the return below).
        self._state.put_launch_receipt(
            spec.run_id, receipt=receipt, original_ref=ref, cursor=cursor,
            spec=spec,
        )
        return ref

    def _verify_replayed_thread(
        self,
        receipt: T3ThreadLaunchReceipt,
        original: WorkerProcessRef,
        client_request_id: str,
        envelope: T3ThreadLaunchEnvelope,
    ) -> None:
        """Refuse any replay that does not return the ORIGINAL thread."""
        if original.provider_session_id and receipt.thread_id != original.provider_session_id:
            raise T3ExecutionAdapterError(
                "replay returned a DIFFERENT thread than the original "
                f"execution ({original.provider_session_id!r} -> "
                f"{receipt.thread_id!r}); refusing a replacement"
            )
        # The receipt's echoed idempotency identity must match the replayed
        # command. In the crash zone (intent persisted, thread not yet
        # known) this echo is the ONLY evidence the receipt belongs to this
        # execution — a foreign echo is a foreign execution.
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
        try:
            read = await self._port.read_thread(thread_id, native_run_id, cursor)
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
        # Advance (persist) the cursor only AFTER a successful exact read.
        self._state.put_cursor(run_id, read.next_cursor)
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


__all__ = [
    "InMemoryT3AdapterStateStore",
    "SQLiteT3AdapterStateStore",
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
