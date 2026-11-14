"""Post-seal execution-return wiring for t3-native attempts (Director F gap 2).

The runtime owns the terminal seal.  This module composes the SEALED facts
(Job/Attempt/binding provenance from the immutable event log) with the T3
adapter's ledgered result reference and one bounded GitHub evidence read
into an ``mastermind.execution_return/v1`` record, delivers it to the
ORIGINAL requester through the existing Hermes deliverer, and persists the
delivery receipt as an ``EXECUTION_RETURN_DELIVERY`` event — no new table.

Laws:
  * The seam NEVER raises into the terminal seal and never alters it; the
    seal is already committed when the seam runs (post-commit call site in
    ``Runtime._terminal``).
  * Delivery is NOT acceptance: the record's acceptance stays
    ``not_accepted`` (projection v1 law), and the receipt only records the
    delivery outcome (delivered / unknown / refused).
  * Exactly one receipt per attempt: the receipt event's command id is
    ``execution-return:{attempt_id}`` and the events table's UNIQUE
    command_id makes double delivery atomic-impossible; a prior receipt
    short-circuits BEFORE any transport call (no auto-retry — Director F
    gap 5: reconciling an unknown receipt is an Executive-runtime concern,
    never a loop here).
  * Unknown GitHub evidence stays honestly unknown (stage never claims
    beyond the proof); an absent original-requester binding or a failed
    projection is an honest REFUSED receipt, never a silent drop.
  * ``Runtime`` is not modified to import this module: the composing
    supervisor INSTALLS the seam (a deployment act); an uninstalled seam
    (the default) changes nothing anywhere.
"""
from __future__ import annotations

import asyncio
import dataclasses
from typing import Any, Callable, Mapping

from control_plane.execution_return_projection import (
    EXECUTION_RETURN_DELIVERY_STATES,
    project_execution_return,
)
from control_plane.executive_orchestration_principal import digest as orchestration_digest
# The deliverer is INJECTED by the composing service (an
# ``integrations.session_bridge.hermes_native_return.HermesExecutionReturnDeliverer``
# in production); control_plane never imports the integrations package
# (tests/test_hermes_selected_child_ingress.py pins that law). Duck type:
# ``async deliver(record) -> receipt mapping``.

#: Event type of the durable delivery receipt (an events row, not a table).
EXECUTION_RETURN_DELIVERY_EVENT = "EXECUTION_RETURN_DELIVERY"

#: Receipt command id — one per attempt, UNIQUE-enforced by the events table.
def execution_return_receipt_command_id(attempt_id: str) -> str:
    return f"execution-return:{attempt_id}"


_RESULT_TEXT_MAX = 8192
_ARTIFACT_REFS_MAX = 16


def _bounded_text(value: Any) -> str | None:
    if type(value) is not str or not value.strip():
        return None
    text = value.strip()
    return text[:_RESULT_TEXT_MAX] if len(text) > _RESULT_TEXT_MAX else text


def _bounded_refs(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    refs: list[str] = []
    for item in values:
        if type(item) is str and item and len(item) <= 512 and item not in refs:
            refs.append(item)
        if len(refs) >= _ARTIFACT_REFS_MAX:
            break
    return refs


@dataclasses.dataclass(frozen=True)
class GitHubEvidenceSource:
    """Where the bounded GitHub evidence read goes (repository + port)."""

    repository: str
    port: Any


class ExecutionReturnWiring:
    """The installed post-terminal seam (callable as ``seam(job=, status=))``.

    Composed by the supervisor that owns the t3-native launch; never by the
    runtime itself.  Every failure path records an honest receipt or returns
    quietly for a non-t3 attempt — the seal is already durable.
    """

    def __init__(
        self,
        *,
        store: Any,
        deliverer: Any,
        github: GitHubEvidenceSource | None = None,
        t3_adapter: Any = None,
        t3_run_resolver: Callable[[str], str | None] | None = None,
    ) -> None:
        if not callable(getattr(deliverer, "deliver", None)):
            raise TypeError("deliverer must expose an async deliver(record) method")
        self._store = store
        self._deliverer = deliverer
        self._github = github
        self._t3_adapter = t3_adapter
        self._t3_run_resolver = t3_run_resolver or (lambda attempt_id: attempt_id)

    # --- event-log reads ----------------------------------------------------

    @staticmethod
    def _claim_binding(store: Any, job: Any) -> dict[str, Any] | None:
        """The ExecutionBinding dict carried by this Job's JOB_CLAIMED event."""
        if not job.current_attempt_id:
            return None
        events = store.list_events(
            job_id=job.job_id, attempt_id=job.current_attempt_id)
        for event in events:
            if event.event_type != "JOB_CLAIMED":
                continue
            payload = event.payload if isinstance(event.payload, dict) else {}
            binding = payload.get("execution_binding")
            return binding if isinstance(binding, dict) else None
        return None

    @staticmethod
    def _admission_provenance(store: Any, job: Any) -> dict[str, Any] | None:
        """The child-request provenance of the ADMISSION Job.

        The placement Job's own JOB_CREATED provenance carries only the
        composition link; the v1.2 ``original_requester`` block lives on
        the admission Job's JOB_CREATED receipt (the same receipt the
        NM-07 lookup path recovers).  Chase the deterministic admission
        command id through the immutable event log.
        """
        provenance = None
        for event in store.list_events(job_id=job.job_id):
            if event.event_type != "JOB_CREATED":
                continue
            payload = event.payload if isinstance(event.payload, dict) else {}
            block = payload.get("provenance")
            provenance = block if isinstance(block, dict) else None
            break
        if not isinstance(provenance, dict):
            return None
        composition = provenance.get("child_placement_composition")
        admission_command_id = None
        if isinstance(composition, dict):
            candidate = composition.get("admission_command_id")
            if isinstance(candidate, str) and candidate:
                admission_command_id = candidate
        if admission_command_id is None:
            # A directly admitted Job: its own provenance is the record.
            return provenance
        admission_event = store.get_event_by_command_id(admission_command_id)
        if admission_event is None or not admission_event.job_id:
            return None
        for event in store.list_events(job_id=str(admission_event.job_id)):
            if event.event_type != "JOB_CREATED":
                continue
            payload = event.payload if isinstance(event.payload, dict) else {}
            block = payload.get("provenance")
            return block if isinstance(block, dict) else None
        return None

    def _t3_attested_namespace(self, job: Any) -> str:
        """The request namespace the adapter persisted for this attempt's
        launch (receipt first, intent second); empty when none is ledgered."""
        if self._t3_adapter is None or not job.current_attempt_id:
            return ""
        run_id = self._t3_run_resolver(job.current_attempt_id)
        if not run_id:
            return ""
        for reader in ("launch_receipt", "launch_intent"):
            method = getattr(self._t3_adapter, reader, None)
            if method is None:
                continue
            try:
                record = method(run_id)
            except Exception:
                continue
            namespace = getattr(record, "request_namespace", "") if record is not None else ""
            if isinstance(namespace, str) and namespace:
                return namespace
        return ""

    def _t3_result_reference(self, job: Any) -> tuple[str | None, str | None, list[str]]:
        """(native thread id, native run id, artifact refs) from the adapter
        ledger, honestly empty when no ledgered reference exists."""
        if self._t3_adapter is None or not job.current_attempt_id:
            return (None, None, [])
        run_id = self._t3_run_resolver(job.current_attempt_id)
        if not run_id:
            return (None, None, [])
        try:
            entry = self._t3_adapter.result_ledger_entry(run_id)
        except Exception:
            return (None, None, [])
        if entry is None:
            return (None, None, [])
        refs = [entry.result_ref] if getattr(entry, "result_ref", "") else []
        return (getattr(entry, "thread_id", "") or None, run_id, refs)

    # --- receipt persistence -------------------------------------------------

    def _record_receipt(
        self, store: Any, job: Any, attempt_id: str, receipt: Mapping[str, Any],
        *, stage: str | None = None,
    ) -> None:
        """Persist one delivery receipt as an events row (idempotent by the
        events table's UNIQUE command_id; a concurrent duplicate rolls back)."""
        payload: dict[str, Any] = {"delivery": dict(receipt)}
        if stage is not None:
            payload["stage"] = stage
        with store.transaction() as connection:
            store.append_event(
                connection,
                aggregate_type="attempt",
                aggregate_id=attempt_id,
                event_type=EXECUTION_RETURN_DELIVERY_EVENT,
                job_id=job.job_id,
                attempt_id=attempt_id,
                payload=payload,
                command_id=execution_return_receipt_command_id(attempt_id),
            )

    def _record_refusal(
        self, store: Any, job: Any, attempt_id: str, code: str, detail: str = "",
    ) -> None:
        """An honest refused receipt without any transport call."""
        receipt = {
            "schema": "mastermind.execution_return_delivery/v1",
            "return_id": "",
            "return_digest": "0" * 64,
            "conversation_id": "",
            "submission_id": "execret-" + "0" * 32,
            "state": "refused",
            "transport_ref": None,
            "refusal_code": code,
        }
        payload: dict[str, Any] = {"delivery": receipt, "refusal_detail": detail}
        with store.transaction() as connection:
            store.append_event(
                connection,
                aggregate_type="attempt",
                aggregate_id=attempt_id,
                event_type=EXECUTION_RETURN_DELIVERY_EVENT,
                job_id=job.job_id,
                attempt_id=attempt_id,
                payload=payload,
                command_id=execution_return_receipt_command_id(attempt_id),
            )

    # --- the seam --------------------------------------------------------

    def __call__(self, *, job: Any, status: Any) -> None:
        self.deliver(job=job, status=status)

    def deliver(self, *, job: Any, status: Any) -> Mapping[str, Any] | None:
        """One post-seal delivery attempt; never raises."""
        try:
            return self._deliver(job=job, status=status, store=self._store)
        except Exception as exc:  # last-resort fence: the seal stays durable
            try:
                if job.current_attempt_id:
                    self._record_refusal(
                        self._store, job, job.current_attempt_id,
                        "RETURN_WIRING_FAILED", str(exc)[:200])
            except Exception:
                pass
            return None

    def _deliver(self, *, job: Any, status: Any, store: Any) -> Mapping[str, Any] | None:
        binding = self._claim_binding(store, job)
        if not isinstance(binding, dict) or binding.get("runtime_kind") != "t3-native":
            return None  # not a t3-native attempt: the seam does not apply
        attempt_id = str(job.current_attempt_id or "")
        if not attempt_id:
            return None
        # Idempotency: exactly one receipt event per attempt, ever.
        command_id = execution_return_receipt_command_id(attempt_id)
        if store.get_event_by_command_id(command_id) is not None:
            return None
        provenance = self._admission_provenance(store, job)
        requester_block = (
            provenance.get("original_requester")
            if isinstance(provenance, dict) else None)
        # The authenticated namespace is what the PORT attested at launch and
        # the adapter persisted with the intent/receipt (REVIEW_C_E_OPUS A2:
        # the claim stamps no namespace; an empty caller_namespace is the
        # claim's honest statement, never a value to return).
        # Review #2 C-2: no fallback to the claim's caller_namespace — it is
        # empty for every reviewed claim and could only ever carry an
        # unattested legacy value.
        namespace = self._t3_attested_namespace(job)
        if not isinstance(requester_block, dict):
            self._record_refusal(
                store, job, attempt_id, "ORIGINAL_BINDING_MISSING",
                "admission carried no v1.2 original_requester block")
            return None
        if not namespace:
            self._record_refusal(
                store, job, attempt_id, "ORIGINAL_BINDING_MISSING",
                "no attested launch namespace persisted for this attempt")
            return None
        child_request = provenance.get("child_request") if isinstance(provenance, dict) else {}
        idempotency_key = (
            child_request.get("command_id") if isinstance(child_request, dict) else None)
        if not isinstance(idempotency_key, str) or not idempotency_key:
            self._record_refusal(
                store, job, attempt_id, "ORIGINAL_BINDING_MISSING",
                "admission provenance lost the child-request command id")
            return None
        thread_id, native_run_id, ledger_refs = self._t3_result_reference(job)

        # Seal digest: the runtime's canonical digest over the terminal facts
        # (status + sealed result + identities), recomputed here from the
        # immutable rows — the projector only requires a 64-hex seal.
        result = job.result if isinstance(job.result, dict) else {}
        seal_digest = orchestration_digest({
            "attempt_id": attempt_id,
            "job_id": job.job_id,
            "status": getattr(status, "value", str(status)),
            "result_digest": orchestration_digest(result),
        })
        github_facts: dict[str, Any] = {
            "branch": None, "pr_number": None, "pr_url": None,
            "checks": None, "merge_state": "unknown",
        }
        if self._github is not None and getattr(job, "branch", None):
            from control_plane.github_attempt_evidence_reader import (
                read_attempt_github_evidence,
            )
            github_facts = read_attempt_github_evidence(
                repository=self._github.repository,
                branch=str(job.branch), port=self._github.port,
            )
        facts = {
            "original_requester": {
                **requester_block,
                "authenticated_namespace": namespace,
            },
            "attempt": {
                "attempt_id": attempt_id,
                "root_id": str(job.root_job_id or job.job_id),
                "idempotency_key": idempotency_key,
                "authenticated_namespace": namespace,
                "t3_thread_id": thread_id,
                "t3_run_id": native_run_id,
                "seal": {
                    "schema": "mastermind terminal seal",
                    "digest": seal_digest,
                },
            },
            "result": {
                "text": _bounded_text(result.get("summary")) or (
                    f"attempt {attempt_id} sealed "
                    f"{getattr(status, 'value', str(status))}"),
                "artifact_refs": _bounded_refs(
                    list(result.get("artifacts") or []) + ledger_refs),
                "acceptance": "not_accepted",
                "installation_claimed": False,
            },
            "github": github_facts,
        }
        from control_plane.execution_return_projection import (
            ExecutionReturnProjectionError,
        )
        try:
            record = project_execution_return(facts)
        except ExecutionReturnProjectionError as exc:
            self._record_refusal(
                store, job, attempt_id, exc.code, str(exc)[:200])
            return None
        try:
            receipt = self._await_delivery(record)
        except _AsyncContextUnavailable:
            self._record_refusal(
                store, job, attempt_id, "ASYNC_CONTEXT_UNAVAILABLE",
                "a running event loop owns this thread; no retry is attempted")
            return None
        if receipt.get("state") not in EXECUTION_RETURN_DELIVERY_STATES:
            self._record_refusal(
                store, job, attempt_id, "TRANSPORT_REFUSED",
                "deliverer returned an unreadable receipt state")
            return None
        self._record_receipt(store, job, attempt_id, receipt, stage=record["stage"])
        return receipt

    def _await_delivery(self, record: Any) -> dict[str, Any]:
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        if running is not None:
            # Never block a live event loop with asyncio.run; reconciliation
            # of this refusal is the Executive runtime's concern (gap 5).
            raise _AsyncContextUnavailable()
        return asyncio.run(self._deliverer.deliver(record))


class _AsyncContextUnavailable(Exception):
    pass


def install_execution_return_seam(
    runtime: Any,
    *,
    deliverer: Any,
    github: GitHubEvidenceSource | None = None,
    t3_adapter: Any = None,
    t3_run_resolver: Callable[[str], str | None] | None = None,
) -> ExecutionReturnWiring:
    """Install the post-terminal return seam on one Runtime instance.

    A deployment act by the composing supervisor.  ``Runtime`` is a frozen
    dataclass, so the seam is attached with ``object.__setattr__`` on the
    single instance; nothing global changes and an uninstalled runtime
    behaves exactly as before.
    """
    wiring = ExecutionReturnWiring(
        store=runtime.store, deliverer=deliverer, github=github,
        t3_adapter=t3_adapter, t3_run_resolver=t3_run_resolver)
    # The terminal seal is owned by the runtime's AttemptRegistry (_terminal);
    # the seam is attached there.  An uninstalled registry keeps its None
    # default and behaves exactly as before.
    runtime.attempts._execution_return_seam = wiring
    return wiring


__all__ = [
    "EXECUTION_RETURN_DELIVERY_EVENT",
    "ExecutionReturnWiring",
    "GitHubEvidenceSource",
    "execution_return_receipt_command_id",
    "install_execution_return_seam",
]
