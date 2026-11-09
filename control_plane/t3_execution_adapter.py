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
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from typing import Any, Protocol, runtime_checkable

from control_plane.child_execution_contracts import ExecutionBinding
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
#: regenerated on replay).
T3_REQUEST_NAMESPACE = "mastermind.control_plane.t3_execution_adapter/v1"

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
    """

    adapter_id = T3_NATIVE_ADAPTER_ID

    def __init__(
        self,
        port: T3NativeClientPort,
        binding_source: Callable[[WorkerLaunchSpec], ExecutionBinding | None],
        inspector: ProcessInspector,
        *,
        clock: Callable[[], datetime] | None = None,
        intent_store: dict[str, T3LaunchIntent] | None = None,
        result_ledger: dict[str, T3ResultReference] | None = None,
    ) -> None:
        self._port = port
        self._binding_source = binding_source
        self.inspector = inspector
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        # Durable launch intents per run, persisted BEFORE any native call.
        self._launch_intents: dict[str, T3LaunchIntent] = (
            intent_store if intent_store is not None else {}
        )
        # Durable result ledger: canonical result references stored BEFORE
        # the neutral CollectionReceipt is built.  Reading T3 is NOT
        # company acceptance — acceptance is a separate downstream act.
        self._result_ledger: dict[str, T3ResultReference] = (
            result_ledger if result_ledger is not None else {}
        )
        # The original neutral ref per run, retained at start BEFORE the ACK.
        self._original_refs: dict[str, WorkerProcessRef] = {}
        # The persisted native launch receipt per run (threadId/runId).
        self._launch_receipts: dict[str, T3ThreadLaunchReceipt] = {}
        # Persisted incremental read cursor per run, advanced only after a
        # successful read.
        self._cursors: dict[str, str] = {}
        # Requested-versus-settled cancellation ledger per run.
        self._cancel_records: dict[str, _T3CancelLedgerEntry] = {}
        # The broker binding / neutral spec that authorized each start.
        self._start_bindings: dict[str, ExecutionBinding] = {}
        self._start_specs: dict[str, WorkerLaunchSpec] = {}

    # --- start -------------------------------------------------------------

    async def start(self, spec: WorkerLaunchSpec) -> WorkerProcessRef:
        """Launch through the native port under the current broker binding.

        Refuses fail-closed without a valid, current ``ExecutionBinding``.
        The launch intent is persisted BEFORE any native call; the receipt
        and the original neutral ref are retained BEFORE the returned ref
        acknowledges start.
        """
        if not isinstance(spec, WorkerLaunchSpec):
            raise T3ExecutionAdapterError("start requires a WorkerLaunchSpec")
        if spec.run_id in self._original_refs:
            raise T3ExecutionAdapterError(
                "run was already started; reattach recovers the same execution "
                "instead of starting a replacement"
            )
        if spec.run_id in self._launch_intents:
            # An intent is persisted (including the effect-unknown zone):
            # start never retries — reattach replays the SAME key+namespace.
            raise T3ExecutionAdapterError(
                f"run {spec.run_id!r} already has a persisted launch intent; "
                "start never retries — reattach recovers the SAME execution "
                "under the SAME clientRequestId"
            )
        binding = self._require_current_binding(spec)
        client_request_id = derive_t3_client_request_id(binding)
        envelope = self._launch_envelope(spec, client_request_id)
        intent = T3LaunchIntent(
            run_id=spec.run_id,
            client_request_id=client_request_id,
            request_namespace=T3_REQUEST_NAMESPACE,
            adapter_id=T3_NATIVE_ADAPTER_ID,
            envelope=envelope,
            created_at=envelope.created_at,
        )
        # PERSIST the launch intent BEFORE any native call.
        self._launch_intents[spec.run_id] = intent
        self._start_bindings[spec.run_id] = binding
        self._start_specs[spec.run_id] = spec
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
            self._launch_intents.pop(spec.run_id, None)
            self._start_bindings.pop(spec.run_id, None)
            self._start_specs.pop(spec.run_id, None)
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
        # Persist the receipt and retain the ORIGINAL ref BEFORE the ACK
        # (the return below).
        self._launch_receipts[spec.run_id] = receipt
        ref = self._neutral_process_ref(spec, receipt, client_request_id)
        self._original_refs[spec.run_id] = ref
        self._cursors.setdefault(spec.run_id, "")
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
        self, spec: WorkerLaunchSpec, client_request_id: str
    ) -> T3ThreadLaunchEnvelope:
        return T3ThreadLaunchEnvelope(
            request_namespace=T3_REQUEST_NAMESPACE,
            client_request_id=client_request_id,
            run_id=spec.run_id,
            worker_id=spec.worker_id,
            title=f"mastermind {spec.job_id}/{spec.run_id}",
            message=spec.prompt,
            workspace_ref=str(spec.workspace_path),
            model_selection=spec.model,
            created_at=self._now_iso(),
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
        cursor; the cursor advances only after a successful read.
        """
        original = self._require_original_ref(ref)
        thread_id, native_run_id = self._native_coordinates(original.run_id)
        cursor = self._cursors.get(original.run_id, "")
        read = await self._read_exact(thread_id, native_run_id, cursor, original.run_id)
        state = _map_t3_status(read.native_status)
        entry = self._cancel_records.get(original.run_id)
        if entry is not None and not entry.settled:
            if state in _TERMINAL_STATES:
                self._settle(entry, state)
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
        original = self._require_original_ref(ref)
        thread_id, native_run_id = self._native_coordinates(original.run_id)
        cursor = self._cursors.get(original.run_id, "")
        read = await self._read_exact(thread_id, native_run_id, cursor, original.run_id)
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
        self._result_ledger[original.run_id] = T3ResultReference(
            run_id=original.run_id,
            thread_id=thread_id,
            result_ref=read.result_ref,
            native_status=read.native_status,
            recorded_at=self._now_iso(),
        )
        receipt = self._build_collection_receipt(original, read, state)
        return receipt

    def _build_collection_receipt(
        self,
        original: WorkerProcessRef,
        read: T3ThreadReadResult,
        state: WorkerRunStatus,
    ) -> CollectionReceipt:
        spec = self._start_specs[original.run_id]
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
        original = self._require_original_ref(ref)
        if not isinstance(reason, str) or not reason.strip():
            raise T3ExecutionAdapterError("cancel requires a non-empty reason")
        try:
            outcome = await self._port.interrupt_run(original, reason)
        except T3UnknownOutcomeError as exc:
            # The interrupt request was made; whether it landed is unknown.
            # Record requested-but-unsettled honestly, then surface the
            # ambiguity — status() reconciles once the native state shows.
            self._cancel_records.setdefault(
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
        self._cancel_records[original.run_id] = _T3CancelLedgerEntry(
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
        entry = self._cancel_records.get(str(run_id))
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

    def _settle(self, entry: _T3CancelLedgerEntry, state: WorkerRunStatus) -> None:
        entry.settled = True
        entry.settled_at = self._now_iso()
        entry.settled_state = state.value

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

        With a retained receipt this needs no native call.  Without one the
        SAME persisted launch command (same clientRequestId + namespace)
        is REPLAYED through ``replay_launch`` — upstream idempotent replay
        returns the ORIGINAL thread.  A replay that returns a different
        thread is refused.  ``launch_thread`` is never called from here.
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
        retained = self._original_refs.get(spec.run_id)
        intent = self._launch_intents.get(spec.run_id)
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
            return await self._replay_and_adopt(spec, intent.envelope, original, intent)
        # No retained intent in this process: reconstruct the SAME command
        # from the recovery binding — the key comes from the ORIGINAL ref's
        # launch_nonce, never regenerated.  Cross-provider/foreign threads
        # are refused by the verification below.
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
        envelope = self._launch_envelope(spec, client_request_id)
        return dataclasses.replace(envelope, request_namespace=T3_REQUEST_NAMESPACE)

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
        self._verify_replayed_thread(receipt, original, client_request_id)
        ref = self._neutral_process_ref(spec, receipt, client_request_id)
        if ref != original:
            raise T3ExecutionAdapterError(
                "replay did not reproduce the original execution identity; "
                "refusing to adopt a replacement"
            )
        self._launch_receipts[spec.run_id] = receipt
        self._original_refs[spec.run_id] = ref
        self._cursors.setdefault(spec.run_id, "")
        return ref

    def _verify_replayed_thread(
        self,
        receipt: T3ThreadLaunchReceipt,
        original: WorkerProcessRef,
        client_request_id: str,
    ) -> None:
        """Refuse any replay that does not return the ORIGINAL thread."""
        if original.provider_session_id and receipt.thread_id != original.provider_session_id:
            raise T3ExecutionAdapterError(
                "replay returned a DIFFERENT thread than the original "
                f"execution ({original.provider_session_id!r} -> "
                f"{receipt.thread_id!r}); refusing a replacement"
            )
        retained_receipt = self._launch_receipts.get(original.run_id)
        if (
            retained_receipt is not None
            and retained_receipt.thread_id != receipt.thread_id
        ):
            raise T3ExecutionAdapterError(
                "replay returned a thread different from the retained "
                "original receipt; refusing a replacement"
            )

    # --- internals ---------------------------------------------------------

    def _native_coordinates(self, run_id: str) -> tuple[str, str]:
        """The persisted (threadId, native runId) for one neutral run."""
        receipt = self._launch_receipts.get(run_id)
        if receipt is None:
            raise T3ExecutionAdapterError(
                f"no native launch receipt persisted for run {run_id!r}"
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
        # Advance the persisted cursor only AFTER a successful exact read.
        self._cursors[run_id] = read.next_cursor
        return read

    def _require_original_ref(self, ref: WorkerProcessRef) -> WorkerProcessRef:
        if not isinstance(ref, WorkerProcessRef):
            raise T3ExecutionAdapterError("operation requires a WorkerProcessRef")
        retained = self._original_refs.get(ref.run_id)
        if retained is None:
            raise T3ExecutionAdapterError(
                f"no original ref retained for run {ref.run_id!r}"
            )
        if retained != ref:
            raise T3ExecutionAdapterError(
                "ref does not match the retained original ref"
            )
        return retained

    def _now_iso(self) -> str:
        return self._clock().isoformat()


__all__ = [
    "T3_INTERRUPT_OUTCOME_SCHEMA",
    "T3_LAUNCH_ENVELOPE_SCHEMA",
    "T3_LAUNCH_INTENT_SCHEMA",
    "T3_LAUNCH_RECEIPT_SCHEMA",
    "T3_NATIVE_ADAPTER_ID",
    "T3_REQUEST_NAMESPACE",
    "T3_RESULT_REFERENCE_SCHEMA",
    "T3_THREAD_READ_SCHEMA",
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
    "derive_t3_client_request_id",
]
