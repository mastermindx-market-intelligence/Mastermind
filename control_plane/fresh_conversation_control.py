"""Authenticated native controls on the original dispatch and OHF operation.

The existing Runtime Event journal retains request identity. Supervisor/OHF
own interruption, idle physical closure and the sole same-Session G2 resume.
"""
from __future__ import annotations

import asyncio
import dataclasses
import json
import time

from common import fresh_conversation_contract as wire
from control_plane.fresh_conversation_native import select_original, read_native_status, session_projection
from control_plane.fresh_conversation_turn import _scope, _command, _context
from control_plane.operator_harness_contract import (
    OperationId, OperationReceiptKind, ProviderSessionHandoff, operation_receipt_command_id,
)

_SEAL = object()
_REQUEST = "FRESH_CONVERSATION_CONTROL_REQUESTED"
_SCHEMA = "mastermind.fresh_conversation_control_request.v1"


def _origin(owner, principal, request, *, for_write=False):
    root, original, material = select_original(owner, principal, request, for_write=for_write)
    if root is None:
        raise ValueError("CONVERSATION_ORIGINAL_UNAVAILABLE")
    creation = owner._runtime.store.unique_root_created_event(root.job_id)
    child_event = owner._runtime.events.get_event_by_command_id(f"coo-cycle:{root.job_id}:create-interactive:0")
    child = owner._runtime.jobs.get_job(child_event.job_id) if child_event is not None else None
    if child is None or not child.current_attempt_id:
        raise ValueError("CONVERSATION_ORIGINAL_ATTEMPT_UNAVAILABLE")
    binding = owner._runtime.jobs.assert_native_conversation_execution(child.job_id)
    if child.parent_job_id != root.job_id or binding["root_job_id"] != root.job_id:
        raise ValueError("CONVERSATION_ORIGINAL_CHANGED")
    identity = dict(principal=_scope(principal), work_ref=original["work_ref"],
        operation_key=original["operation_key"], root_job_id=root.job_id,
        root_event_id=creation.event_id, root_event_sha256=wire.canonical_digest(creation.to_dict()),
        locator=dict(work_ref=original["work_ref"], root_job_id=root.job_id,
                     job_id=child.job_id, attempt_id=child.current_attempt_id))
    return root, original, identity


def _operation(command, target, session):
    return OperationId("ohf-op:fresh-control:" + wire.canonical_digest(
        dict(command=command, target=target, session=session)))


def _request_event(owner, command, identity, *, kind, key):
    event = owner._runtime.events.get_event_by_command_id(command)
    if event is None:
        return None
    payload = event.payload
    if (event.event_type != _REQUEST or event.aggregate_type != "fresh_conversation"
            or event.aggregate_id != identity["root_job_id"] or event.job_id != identity["root_job_id"]
            or event.attempt_id != identity["locator"]["attempt_id"] or event.actor != "fresh-conversation-parent"
            or type(payload) is not dict or payload.get("schema") != _SCHEMA
            or payload.get("identity") != identity or payload.get("kind") != kind or payload.get("control_key") != key
            or command != _command(kind, identity["principal"], identity["root_job_id"], key)
            or payload.get("operation_id") != _operation(command, payload["target"], payload["session"]).command_id):
        raise ValueError("CONVERSATION_CONTROL_SOURCE_CHANGED")
    return event


def _operation_receipts(owner, requested):
    """Resolve the original request -> exact INTENT -> original receipt, passively."""
    runtime, payload = owner._runtime, requested.payload
    identity, session = payload["identity"], payload["session"]
    locator = identity["locator"]
    attempt = runtime.attempts.get_attempt(locator["attempt_id"])
    if attempt is None or attempt.job_id != locator["job_id"]:
        raise ValueError("CONVERSATION_CONTROL_ATTEMPT_CHANGED")
    operation = OperationId(payload["operation_id"])
    events = {}
    for kind in (OperationReceiptKind.INTENT, OperationReceiptKind.APPLIED, OperationReceiptKind.EFFECT_UNKNOWN):
        event = runtime.events.get_event_by_command_id(operation_receipt_command_id(operation, kind))
        if event is not None:
            if (event.event_type != kind.value or event.aggregate_type != "operator_operation"
                    or event.aggregate_id != operation.command_id or event.actor != "supervisor"
                    or event.job_id != locator["job_id"] or event.attempt_id != attempt.attempt_id
                    or event.worker_id != attempt.worker_id or event.quota_class != attempt.quota_class
                    or event.event_id <= requested.event_id or type(event.payload) is not dict):
                raise ValueError("CONVERSATION_CONTROL_RECEIPT_CHANGED")
            events[kind] = event
    intent = events.get(OperationReceiptKind.INTENT)
    applied = events.get(OperationReceiptKind.APPLIED)
    unknown = events.get(OperationReceiptKind.EFFECT_UNKNOWN)
    if intent is None:
        if applied is not None or unknown is not None:
            raise ValueError("CONVERSATION_CONTROL_RECEIPT_CHANGED")
        return "RECONCILIATION_REQUIRED", None
    if applied is not None and unknown is not None:
        raise ValueError("CONVERSATION_CONTROL_RECEIPT_CHANGED")
    if any(event.event_id <= intent.event_id for event in (applied, unknown) if event is not None):
        raise ValueError("CONVERSATION_CONTROL_RECEIPT_CHANGED")
    if payload["kind"] == "stop":
        expected = dict(schema_version="mastermind.operator_harness_turn_operation/v1",
            operation_kind="interrupt_turn", attempt_id=attempt.attempt_id,
            session_epoch_id=session["session_epoch_id"], process_generation_id=session["process_generation_id"],
            worker_id=attempt.worker_id, turn_id=payload["target"]["turn_id"])
        expected_applied = dict(schema_version="mastermind.operator_harness_turn_operation_applied/v1",
            operation_kind="interrupt_turn", turn_id=payload["target"]["turn_id"])
    else:
        generation_id = intent.payload.get("process_generation_id")
        with runtime.store.read() as connection:
            generations = connection.execute(
                "SELECT * FROM process_generations WHERE session_epoch_id=? ORDER BY generation_number",
                (session["session_epoch_id"],)).fetchall()
        if (len(generations) != 2 or generations[0]["process_generation_id"] != session["process_generation_id"]
                or generations[1]["process_generation_id"] != generation_id
                or [int(g["generation_number"]) for g in generations] != [1, 2]
                or any(g["worker_id"] != attempt.worker_id for g in generations)):
            raise ValueError("CONVERSATION_CONTROL_RESUME_TARGET_CHANGED")
        expected = dict(operation_kind="resume_session", attempt_id=attempt.attempt_id,
            session_epoch_id=session["session_epoch_id"], process_generation_id=generation_id,
            worker_id=attempt.worker_id, provider_session_id=session["provider_session_id"])
        expected_applied = dict(operation_kind="resume_session", process_generation_id=generation_id,
            provider_session_id=session["provider_session_id"])
    if intent.payload != expected or (applied is not None and applied.payload != expected_applied):
        raise ValueError("CONVERSATION_CONTROL_RECEIPT_CHANGED")
    kind, receipt = ((OperationReceiptKind.APPLIED, applied) if applied is not None else
        (OperationReceiptKind.EFFECT_UNKNOWN, unknown) if unknown is not None else (OperationReceiptKind.INTENT, intent))
    return kind.name, dict(kind=kind.value, command_id=receipt.command_id, event_id=receipt.event_id,
                           event_sha256=wire.canonical_digest(receipt.to_dict()))


def _response(request, kind, state, *, identity, payload=None, receipt=None, preview=None):
    return dict(schema=wire.NATIVE_CONTROL_DATA_SCHEMA, work_ref=request["work_ref"],
        operation_key=request["operation_key"], reference=None, kind=kind, control_key=request[kind + "_key"],
        state=state, effect="NONE", locator=identity["locator"],
        session=None if payload is None else payload["session"],
        active_turn=None if payload is None else payload["active_turn"],
        operation_id=None if payload is None else payload.get("operation_id"), receipt=receipt,
        head_result=None if payload is None else payload["head_result"],
        preview_digest=preview, parent_consumed=False, target=None if payload is None else payload["target"])


def _capture(owner, principal, workspace, request, host_current, identity, kind):
    context = _context(owner, principal, workspace, request, host_current, identity, schema=wire.NATIVE_SCHEMA)
    dispatch = owner._service._native_operator_dispatch
    supervisor = owner._service._require_operator_supervisor()
    if (dispatch is None or dispatch.job_id != identity["locator"]["job_id"]
            or getattr(dispatch, "_fresh_control_source", None) is not None):
        raise ValueError("CONVERSATION_CONTROL_WRITER_UNAVAILABLE")
    if kind == "stop":
        active = dispatch.active_turn
        facts = supervisor._require_active_native_turn(active)
        session = session_projection(facts)
        if (request["turn_id"] != active.turn.turn_id or request["binding_digest"] != session["binding_digest"]
                or getattr(dispatch, "_fresh_interrupt_source", None) is not None):
            raise ValueError("CONVERSATION_CONTROL_TARGET_CHANGED")
        target = dict(turn_id=active.turn.turn_id, binding_digest=session["binding_digest"])
        active_projection = dict(turn_id=active.turn.turn_id, begin_operation_id=active.operation_id.command_id)
        results = owner._runtime.operator_harness.native_conversation_results(attempt_id=facts.attempt_id)
        head = results[-1] if results else None
    else:
        retained = dispatch.retained
        if (retained is None or getattr(dispatch, "native_phase", "READY") != "IDLE"
                or retained.session.generation.generation_number != 1
                or dispatch.continuation.done() or getattr(dispatch, "_fresh_interrupt_source", None) is not None):
            raise ValueError("CONVERSATION_RESUME_REQUIRES_IDLE_SESSION")
        head = owner._runtime.operator_harness.latest_native_conversation_result(attempt_id=retained.session.attempt_id)
        if head is None or head.seal_digest != request["expected_result_digest"]:
            raise ValueError("CONVERSATION_RESUME_RESULT_CHANGED")
        session = supervisor.native_idle_projection(retained, expected_result=head)
        target = dict(expected_result_digest=head.seal_digest, binding_digest=session["binding_digest"])
        active_projection = None
    if session["attempt_id"] != identity["locator"]["attempt_id"]:
        raise ValueError("CONVERSATION_CONTROL_ATTEMPT_CHANGED")
    from control_plane.fresh_conversation_native import result_projection
    return dispatch, context, dict(session=session, target=target, active_turn=active_projection,
                                  head_result=None if head is None else result_projection(head))


def _preview(request, identity, captured):
    return wire.canonical_digest(dict(request={k: v for k, v in request.items() if k != "preview_digest"},
        identity=identity, context=captured[1], target=captured[2]))


@dataclasses.dataclass(frozen=True, slots=True)
class FreshConversationControlSource:
    _seal: object
    _owner: object
    _dispatch: object
    _command: str
    _payload: bytes
    _context_guard: object
    _target_guard: object
    _completion: asyncio.Future
    _deadline: float

    def check_record(self):
        from control_plane.fresh_conversation import FreshConversationOwner
        payload = json.loads(self._payload)
        slot = "_fresh_interrupt_source" if payload["kind"] == "stop" else "_fresh_control_source"
        if (self._seal is not _SEAL or type(self._owner) is not FreshConversationOwner
                or self._owner._service._native_operator_dispatch is not self._dispatch
                or getattr(self._dispatch, slot, None) is not self):
            raise ValueError("CONVERSATION_CONTROL_SOURCE_REQUIRED")
        event = _request_event(self._owner, self._command, payload["identity"], kind=payload["kind"], key=payload["control_key"])
        if event is None or event.payload != payload:
            raise ValueError("CONVERSATION_CONTROL_SOURCE_CHANGED")
        return event, payload

    def check(self):
        self.check_record()
        if time.monotonic() >= self._deadline or self._context_guard() is not None or self._target_guard() is not None:
            raise ValueError("CONVERSATION_CONTROL_CONTEXT_CHANGED")
        return self.check_record()

    def before_write(self, actual_operation=None, actual_payload=None):
        event, payload = self.check_record()
        if time.monotonic() >= self._deadline or self._context_guard() is not None:
            raise ValueError("CONVERSATION_CONTROL_CONTEXT_CHANGED")
        state, _receipt = _operation_receipts(self._owner, event)
        if actual_operation is not None and state != "INTENT":
            raise ValueError("CONVERSATION_CONTROL_INTENT_REQUIRED")
        if state == "RECONCILIATION_REQUIRED":
            self._target_guard()  # Guard binding before the original OHF INTENT.
        elif state != "INTENT":
            raise ValueError("CONVERSATION_CONTROL_ALREADY_DISPATCHED")
        elif payload["kind"] == "stop":
            self._target_guard()
        else:
            # TX10 has already allocated G2. Rejoin its exact INTENT, not a
            # stale G1-currentness check and not an arbitrary replacement writer.
            retained = self._dispatch.retained
            supervisor = self._owner._service._require_operator_supervisor()
            if retained is None or retained.owner is not supervisor:
                raise ValueError("CONVERSATION_CONTROL_SOURCE_CHANGED")
            with self._owner._runtime.store.read() as connection:
                row = supervisor.runtime.operator_harness._leased(connection,
                    attempt_id=retained.session.attempt_id, fence_generation=retained.lease.attempt.fence_generation,
                    lease_token=retained.lease.lease_token, timestamp=supervisor.runtime.store.now_ms())
                supervisor.runtime.operator_harness._require_orchestration_g1_recovery_predicate(connection,
                    row=row, epoch=retained.session.epoch, g1_generation_id=retained.session.generation.process_generation_id,
                    expected_generation_count=2)
                from control_plane.operator_harness_contract import ProcessGenerationRef
                intent = self._owner._runtime.events.get_event_by_command_id(payload["operation_id"])
                generation = ProcessGenerationRef(intent.payload["process_generation_id"],
                    retained.session.epoch.session_epoch_id, 2, retained.lease.attempt.worker_id)
                supervisor.runtime.operator_harness._owned_generation(connection, leased=row,
                    epoch=retained.session.epoch, generation=generation, require_current=True, require_writer=True)
        if actual_operation is not None:
            from control_plane.operator_harness_wire import to_wire
            session = payload["session"]
            expected_name = "ohf-interrupt" if payload["kind"] == "stop" else "ohf-resume"
            if actual_operation != expected_name or type(actual_payload) is not dict:
                raise ValueError("CONVERSATION_CONTROL_WRITE_CHANGED")
            if payload["kind"] == "stop":
                expected = dict(operation_id=to_wire(OperationId(payload["operation_id"])), turn=dict(
                    turn_id=payload["target"]["turn_id"], attempt_id=session["attempt_id"],
                    session_epoch_id=session["session_epoch_id"], process_generation_id=session["process_generation_id"]))
            else:
                retained = self._dispatch.retained
                expected = dict(operation_id=to_wire(OperationId(payload["operation_id"])),
                    epoch=to_wire(retained.session.epoch), generation=to_wire(generation),
                    requested=to_wire(retained.session.launch.requested),
                    provider_session=to_wire(ProviderSessionHandoff(
                        session["provider_session_id"], retained.lease.attempt.worker_id)))
            if actual_payload != expected:
                raise ValueError("CONVERSATION_CONTROL_WRITE_CHANGED")
        self.check_record()


async def _execute_stop(service, source):
    try:
        _event, payload = source.check()
        dispatch, supervisor = source._dispatch, service._require_operator_supervisor()
        active = dispatch.active_turn
        supervisor._require_active_native_turn(active)
        operation = OperationId(payload["operation_id"])
        active.adapter.bind_native_control_guard(source.before_write,
            attempt_id=active.session.attempt_id, operation_id=operation, kind="stop")
        source.check()
        await asyncio.to_thread(supervisor._orchestrator(active.lease, active.adapter).interrupt_turn,
            active.session, active.turn, operation_id=operation)
    finally:
        if not source._completion.done():
            source._completion.set_result(None)


async def execute_resume(service, dispatch, source):
    if type(source) is not FreshConversationControlSource or source._dispatch is not dispatch:
        raise ValueError("CONVERSATION_CONTROL_SOURCE_REQUIRED")
    event, payload = source.check()
    if payload["kind"] != "resume" or source._owner._service is not service:
        raise ValueError("CONVERSATION_CONTROL_SOURCE_REQUIRED")
    retained, supervisor = dispatch.retained, service._require_operator_supervisor()
    operation = OperationId(payload["operation_id"])
    retained.adapter.bind_native_control_guard(source.before_write,
        attempt_id=retained.session.attempt_id, operation_id=operation, kind="resume")
    source.check()
    session = await asyncio.to_thread(supervisor._orchestrator(retained.lease, retained.adapter).resume,
        retained.session, operation_id=operation,
        handoff=ProviderSessionHandoff(retained.session.observation.provider_session_id, retained.lease.attempt.worker_id))
    # APPLIED and full writer readiness remain separate. A failure here leaves
    # the original receipt readable and does not authorize another resume.
    dispatch.retained = dataclasses.replace(retained, session=session)
    supervisor._require_retained_native(dispatch.retained)
    dispatch.native_phase = "READY"


async def settle_interrupted_turn(service, dispatch):
    source = getattr(dispatch, "_fresh_interrupt_source", None)
    if source is None:
        return
    if type(source) is not FreshConversationControlSource or source._dispatch is not dispatch:
        raise ValueError("CONVERSATION_CONTROL_SOURCE_REQUIRED")
    await asyncio.shield(source._completion)
    event, payload = source.check_record()
    state, _receipt = _operation_receipts(source._owner, event)
    if state != "APPLIED":
        raise ValueError("CONVERSATION_STOP_REQUIRES_RECONCILIATION")
    supervisor = service._require_operator_supervisor()
    if dispatch.retained.session.generation.generation_number == 2:
        await supervisor.finish_retained_native_job(dispatch.retained)
        dispatch.native_phase = "SETTLED"
        dispatch._fresh_interrupt_source = None
        return
    dispatch.native_phase = "IDLING"
    await supervisor.idle_retained_native_job(dispatch.retained)
    supervisor.native_idle_projection(dispatch.retained, expected_result=dispatch.retained.native_result)
    dispatch.native_phase = "IDLE"
    dispatch._fresh_interrupt_source = None


async def handle_control(owner, principal, workspace, request, *, operation, host_current, reader):
    kind = "stop" if operation.startswith("stop") else "resume"
    root, original, identity = _origin(owner, principal, request, for_write=operation in wire.NATIVE_DUAL_RESOURCE)
    key = original[kind + "_key"]
    command = _command(kind, identity["principal"], root.job_id, key)
    prior = _request_event(owner, command, identity, kind=kind, key=key)
    if prior is not None:
        if operation == "resume_preview":
            raise ValueError("CONVERSATION_CONTROL_ALREADY_RESERVED")
        if operation in wire.NATIVE_MODIFYING and prior.payload["request_sha256"] != wire.canonical_digest(original):
            raise ValueError("CONVERSATION_CONTROL_CONFLICT")
        state, receipt = _operation_receipts(owner, prior)
        owner._current(principal, read_only=True)
        return _response(original, kind, state, identity=identity, payload=prior.payload, receipt=receipt)
    if operation.endswith("_status"):
        return _response(original, kind, "ABSENT", identity=identity)
    def current():
        if (not callable(host_current) or host_current() is not None
                or (operation in wire.NATIVE_MODIFYING and (reader is None or reader.at_eof()))):
            raise ValueError("CONVERSATION_REQUEST_CLOSED")
        owner._current(principal)
    captured = _capture(owner, principal, workspace, original, current, identity, kind)
    dispatch, context, projection = captured
    if operation == "resume_preview":
        if _capture(owner, principal, workspace, original, current, identity, kind) != captured:
            raise ValueError("CONVERSATION_CONTROL_CONTEXT_CHANGED")
        return _response(original, kind, "RESUME_READY", identity=identity, payload=projection,
                         preview=_preview(original, identity, captured))
    if kind == "resume" and original["preview_digest"] != _preview(original, identity, captured):
        raise ValueError("CONVERSATION_RESUME_PREVIEW_CHANGED")
    target_handle = dispatch.active_turn if kind == "stop" else dispatch.retained
    def context_guard():
        if _context(owner, principal, workspace, original, current, identity, schema=wire.NATIVE_SCHEMA) != context:
            raise ValueError("CONVERSATION_CONTROL_CONTEXT_CHANGED")
    def target_guard():
        supervisor = owner._service._require_operator_supervisor()
        if kind == "stop":
            if dispatch.active_turn is not target_handle:
                raise ValueError("CONVERSATION_CONTROL_TARGET_CHANGED")
            actual = session_projection(supervisor._require_active_native_turn(target_handle))
        else:
            if dispatch.retained is not target_handle or getattr(dispatch, "native_phase", "READY") != "IDLE":
                raise ValueError("CONVERSATION_CONTROL_TARGET_CHANGED")
            actual = supervisor.native_idle_projection(target_handle, expected_result=target_handle.native_result)
        if actual != projection["session"]:
            raise ValueError("CONVERSATION_CONTROL_TARGET_CHANGED")
    payload = dict(schema=_SCHEMA, identity=identity, kind=kind, control_key=key,
        request_sha256=wire.canonical_digest(original), **projection,
        operation_id=_operation(command, projection["target"], projection["session"]).command_id)
    with owner._runtime.store.transaction() as connection:
        context_guard()
        target_guard()
        # One durable request owns this physical target, even if execution or
        # delivery was interrupted before an OHF receipt became observable.
        for row in connection.execute("SELECT payload_json FROM events WHERE aggregate_type='fresh_conversation' AND aggregate_id=? AND event_type=?",
                                      (root.job_id, _REQUEST)):
            existing = json.loads(row["payload_json"])
            if existing.get("kind") == kind and existing.get("target") == projection["target"]:
                raise ValueError("CONVERSATION_CONTROL_ALREADY_RESERVED")
        owner._runtime.store.append_event(connection, aggregate_type="fresh_conversation", aggregate_id=root.job_id,
            event_type=_REQUEST, command_id=command, actor="fresh-conversation-parent", job_id=root.job_id,
            attempt_id=identity["locator"]["attempt_id"], payload=payload)
        context_guard()
        target_guard()
    source = FreshConversationControlSource(_SEAL, owner, dispatch, command,
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(),
        context_guard, target_guard, asyncio.get_running_loop().create_future(),
        time.monotonic() + min(300.0, principal.expires_at - time.time(), workspace.expires_at - time.time()))
    if kind == "stop":
        dispatch._fresh_interrupt_source = source
        try:
            await owner._service._run_owned_coroutine(_execute_stop(owner._service, source))
        except Exception:
            pass  # Original receipt/state below is the sole outcome, never a replay.
    else:
        dispatch._fresh_control_source = source
        source.check()
        dispatch.continuation.set_result(source)
        await asyncio.shield(source._completion)
    prior = _request_event(owner, command, identity, kind=kind, key=key)
    state, receipt = _operation_receipts(owner, prior)
    owner._current(principal, read_only=True)
    return _response(original, kind, state, identity=identity, payload=prior.payload, receipt=receipt)
