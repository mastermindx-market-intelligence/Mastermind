"""Native variants of the existing FreshConversation owner projections.

All selections rejoin the original root and Runtime evidence. These functions
create no sessions, authority, history store, transport or execution lifecycle.
"""
from __future__ import annotations
import dataclasses

from common import fresh_conversation_contract as wire
from control_plane import ceo_intent, ceo_request
from control_plane.executive_runtime import JobStatus
from control_plane.fresh_conversation_admission import read_creation_restriction, NATIVE_SCHEMA


def select_original(owner, principal, request, *, for_write=False):
    owner._current(principal, read_only=not for_write)
    original = dict(request)
    if request.get("reference") is not None:
        from control_plane.fresh_conversation_reference import resolve_action_reference
        selected = resolve_action_reference(owner, principal, request["reference"], for_write=for_write)
        original = {**request, **selected}
        original.pop("reference")
    from control_plane.fresh_conversation import scoped_operation_key
    key = scoped_operation_key(principal, original["operation_key"])
    intent_id = ceo_request.automated_intent_id(ceo_request.app_request_ref(key))
    command = ceo_intent.command_id_for(intent_id)
    event = owner._runtime.store.find_event_by_command_id(command)
    if event is None:
        return None, original, None
    receipt = ceo_intent.resolve_intent(owner._runtime, intent_id)
    root = owner._runtime.jobs.get_job(receipt["job_id"])
    if root is None or receipt.get("work_ref") != request["work_ref"]:
        raise ValueError("NATIVE_CONVERSATION_ORIGINAL_ROOT_CHANGED")
    material = owner._require_fresh_original(root, principal, original, command, schema=wire.NATIVE_SCHEMA)
    if material["schema"] != NATIVE_SCHEMA:
        raise ValueError("NATIVE_CONVERSATION_ORIGINAL_CONTRACT_CHANGED")
    return root, original, material


def result_projection(reference):
    return wire.validate_native_result(dict(contract=wire.NATIVE_RESULT_CONTRACT,
        digest=reference.seal_digest, reference=reference.to_wire()))


def session_projection(facts):
    return dict(attempt_id=facts.attempt_id, session_epoch_id=facts.session_epoch_id,
        process_generation_id=facts.process_generation_id, provider_session_id=facts.provider_session_id,
        binding_digest=wire.canonical_digest(dataclasses.asdict(facts)))


def initial_identity(owner, principal, original, root, locator, initial_digest):
    from control_plane.fresh_conversation_turn import _scope
    creation = owner._runtime.store.unique_root_created_event(root.job_id)
    return dict(principal=_scope(principal), work_ref=original["work_ref"],
        operation_key=original["operation_key"], root_job_id=root.job_id,
        root_event_id=creation.event_id, root_event_sha256=wire.canonical_digest(creation.to_dict()),
        initial_digest=initial_digest, locator=locator)


async def read_native_status(owner, principal, request, *, effect="NONE"):
    root, original, material = select_original(owner, principal, request)
    if root is None:
        return owner._response(request, "ABSENT", _schema=wire.NATIVE_SCHEMA)
    child_event = owner._runtime.events.get_event_by_command_id(
        f"coo-cycle:{root.job_id}:create-interactive:0")
    child = owner._runtime.jobs.get_job(child_event.job_id) if child_event else None
    locator = dict(work_ref=request["work_ref"], root_job_id=root.job_id,
        job_id=child.job_id if child else None, attempt_id=child.current_attempt_id if child else None)
    state, session, active_projection = "ADMITTED", None, None
    initial = head = None
    can_send = can_resume = can_stop = False
    if child is not None:
        binding = owner._runtime.jobs.assert_native_conversation_execution(child.job_id)
        if (child.parent_job_id != root.job_id or child.root_job_id != root.job_id
                or binding["root_job_id"] != root.job_id):
            raise ValueError("NATIVE_CONVERSATION_ORIGINAL_CHILD_CHANGED")
        if child.current_attempt_id:
            refs = owner._runtime.operator_harness.native_conversation_results(attempt_id=child.current_attempt_id)
            if refs:
                initial, head = result_projection(refs[0]), result_projection(refs[-1])
            dispatch = owner._service._native_operator_dispatch
            supervisor = owner._service.operator_supervisor
            from control_plane.executive_operator_supervisor import (
                ExecutiveOperatorSupervisor, RetainedNativeOperatorSession, ActiveNativeOperatorTurn)
            state = "RECONCILIATION_REQUIRED"
            if child.status is JobStatus.COMPLETED:
                if not refs:
                    raise ValueError("NATIVE_CONVERSATION_COMPLETION_WITHOUT_RESULT")
                owner._runtime.operator_harness.native_conversation_terminal_payload(
                    attempt_id=child.current_attempt_id, reference=refs[-1])
                state = "SETTLED"
            elif (owner._service._service_state == "READY"
                    and type(supervisor) is ExecutiveOperatorSupervisor and supervisor.runtime is owner._runtime
                    and dispatch is not None and dispatch.job_id == child.job_id):
                active = dispatch.active_turn
                retained = dispatch.retained
                if type(active) is ActiveNativeOperatorTurn and not active.withdrawn:
                    try:
                        facts = supervisor._require_active_native_turn(active)
                    except Exception:
                        facts = None  # Applied Stop can precede original terminal collection.
                    if facts is not None:
                        session = session_projection(facts)
                        active_projection = dict(turn_id=active.turn.turn_id,
                            begin_operation_id=active.operation_id.command_id)
                        state = "ACTIVE"
                        can_stop = getattr(dispatch, "_fresh_interrupt_source", None) is None
                elif (type(retained) is RetainedNativeOperatorSession and retained.owner is supervisor
                        and retained.job.job_id == child.job_id and retained.session.attempt_id == child.current_attempt_id
                        and refs):
                    phase = getattr(dispatch, "native_phase", "READY")
                    if phase == "IDLE":
                        session = supervisor.native_idle_projection(retained, expected_result=refs[-1])
                        state = "IDLE"
                        can_resume = (retained.session.generation.generation_number == 1
                            and not dispatch.continuation.done() and getattr(dispatch, "_fresh_control_source", None) is None)
                    elif phase == "READY" and getattr(dispatch, "_fresh_interrupt_source", None) is None:
                        facts = supervisor._require_retained_native(retained)
                        session = session_projection(facts)
                        state = "CREATED"
                        from control_plane.fresh_conversation_turn import _consumption
                        identity = initial_identity(owner, principal, original, root, locator, initial["digest"])
                        can_send = (_consumption(owner, identity) is not None and not dispatch.continuation.done()
                            and getattr(dispatch, "_fresh_turn_source", None) is None)
                        if supervisor._require_retained_native(retained) != facts:
                            raise ValueError("NATIVE_CONVERSATION_WRITER_CHANGED")
    # Rejoin original selection after every composite observation. No read resumes work.
    root_after, original_after, material_after = select_original(owner, principal, request)
    if root_after != root or original_after != original or material_after != material:
        raise ValueError("NATIVE_CONVERSATION_ORIGINAL_CONTEXT_CHANGED")
    return owner._response(request, state, effect=effect, _schema=wire.NATIVE_SCHEMA,
        locator=locator, session=session, active_turn=active_projection,
        result=initial, head_result=head, can_send=can_send, can_resume=can_resume, can_stop=can_stop)



async def recover_original_native_call(owner, principal, workspace, request, *, operation, current):
    """Join one retained call; ordinary status/history remain provider-free."""
    from control_plane.executive_operator_supervisor import PendingNativeOperatorTurn
    from control_plane import fresh_conversation_turn as turns
    current()
    root, original, material = select_original(owner, principal, request, for_write=True)
    if root is None:
        raise ValueError("NATIVE_CONVERSATION_ORIGINAL_ROOT_UNAVAILABLE")
    binding = owner._fresh(principal, schema=wire.NATIVE_SCHEMA)
    project = owner._project(principal, workspace, original["work_ref"])
    dispatch = owner._service._native_operator_dispatch
    pending = None if dispatch is None else dispatch.pending_turn
    if type(pending) is PendingNativeOperatorTurn:
        child = owner._runtime.jobs.get_job(dispatch.job_id)
        if (child is None or child.parent_job_id != root.job_id or child.root_job_id != root.job_id
                or pending.job.job_id != child.job_id or child.current_attempt_id != pending.session.attempt_id
                or pending.owner is not owner._service._require_operator_supervisor()):
            raise ValueError("NATIVE_CONVERSATION_RECOVERY_OWNER_CHANGED")
        source = getattr(dispatch, "_fresh_turn_source", None)
        if operation == "turn_recover":
            command = turns._command("turn", turns._scope(principal), root.job_id, original["turn_key"])
            if source is None or source._command != command:
                raise ValueError("NATIVE_CONVERSATION_RECOVERY_TURN_CHANGED")
            event, payload = source.check_record()
            if (source._owner._runtime is not owner._runtime or source._owner._service is not owner._service
                    or payload["turn_key"] != original["turn_key"]
                    or payload["operation_id"] != pending.operation_id.command_id
                    or payload["identity"]["principal"] != turns._scope(principal)
                    or payload["identity"]["work_ref"] != original["work_ref"]):
                raise ValueError("NATIVE_CONVERSATION_RECOVERY_SOURCE_CHANGED")
        elif source is not None:
            raise ValueError("NATIVE_CONVERSATION_RECOVERY_REQUIRES_ORIGINAL_TURN")
        def qualified():
            current()
            if (owner._service._native_operator_dispatch is not dispatch or dispatch.pending_turn is not pending
                    or owner._fresh(principal, schema=wire.NATIVE_SCHEMA) != binding
                    or owner._project(principal, workspace, original["work_ref"]) != project
                    or select_original(owner, principal, original, for_write=True) != (root, original, material)):
                raise ValueError("NATIVE_CONVERSATION_RECOVERY_CONTEXT_CHANGED")
            if source is not None and source.check_record() != (event, payload):
                raise ValueError("NATIVE_CONVERSATION_RECOVERY_SOURCE_CHANGED")
        qualified()
        await owner._service.recover_native_operator_turn(dispatch, current=qualified)
    current()
    if operation == "turn_recover":
        return await turns.read_turn(owner, principal, original, schema=wire.NATIVE_SCHEMA)
    return await read_native_status(owner, principal, original)

async def handle_native_followup(owner, principal, workspace, request, *, operation, host_current, reader):
    root, original, _material = select_original(owner, principal, request,
        for_write=operation in wire.NATIVE_DUAL_RESOURCE)
    if root is None:
        raise ValueError("NATIVE_CONVERSATION_ORIGINAL_ROOT_UNAVAILABLE")
    if operation.startswith(("stop", "resume")):
        from control_plane.fresh_conversation_control import handle_control
        value = await handle_control(owner, principal, workspace, original, operation=operation,
            host_current=host_current, reader=reader)
    else:
        from control_plane import fresh_conversation_turn as turns
        def current():
            if not callable(host_current) or host_current() is not None:
                raise ValueError("NATIVE_CONVERSATION_REQUEST_CLOSED")
            if operation in wire.NATIVE_MODIFYING and (reader is None or reader.at_eof()):
                raise ValueError("NATIVE_CONVERSATION_REQUEST_CLOSED")
            owner._current(principal, read_only=operation in wire.NATIVE_PASSIVE)
        current()
        if operation in {"recover", "turn_recover"}:
            value = await recover_original_native_call(owner, principal, workspace, original,
                operation=operation, current=current)
        elif operation == "consume":
            value = await turns.consume_initial(owner, principal, workspace, original,
                host_current=current, schema=wire.NATIVE_SCHEMA)
        elif operation == "consume_status":
            value = await turns.read_initial_consumption(owner, principal, original, schema=wire.NATIVE_SCHEMA)
        elif operation == "turn_preview":
            value = await turns.preview_turn(owner, principal, workspace, original,
                host_current=current, schema=wire.NATIVE_SCHEMA)
        elif operation == "turn":
            value = await turns.submit_turn(owner, principal, workspace, original,
                host_current=current, schema=wire.NATIVE_SCHEMA)
        else:
            value = await turns.read_turn(owner, principal, original, schema=wire.NATIVE_SCHEMA)
        current()
    if request.get("reference") is not None:
        value = {**value, "operation_key": None, "reference": request["reference"]}
    return wire.validate_native_data(value, request)
