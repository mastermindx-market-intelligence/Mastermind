"""Fresh-only attended continuation on the incumbent Runtime/TX5 writer.

Existing immutable Events retain consumption/request/reply evidence. The existing
service waiter, OHF reservation/ACK/candidate and cleanup own execution. There is
no target, queue, grant, provider, session registry or Wake/CONTINUE substitution.
"""
from __future__ import annotations
import asyncio
import dataclasses
import json
import time
from dataclasses import dataclass

from common import fresh_conversation_contract as wire
from control_plane.operator_harness_contract import OperationId

_SEAL = object()
_IDENTITY = ("policy_id", "issuer_digest", "resource", "subject_digest", "client_ref")
_CONSUME = "FRESH_CONVERSATION_INITIAL_CONSUMED"
_REQUEST = "FRESH_CONVERSATION_TURN_REQUESTED"
_REPLY = "FRESH_CONVERSATION_TURN_RECORDED"
_UNKNOWN = "FRESH_CONVERSATION_TURN_UNKNOWN"
_AGGREGATE = "fresh_conversation"
_ACTOR = "fresh-conversation-parent"


def _scope(principal):
    return wire.canonical_digest({key: getattr(principal, key) for key in _IDENTITY})


def _command(kind, scope, root_id, key=""):
    return "fresh-" + kind + ":" + wire.canonical_digest(dict(principal=scope, root=root_id, key=key))


def _event(runtime, command, kind, root_id):
    value = runtime.events.get_event_by_command_id(command)
    if value is not None:
        schemas = {_CONSUME: "mastermind.fresh_conversation_initial_consumption.v1",
            _REQUEST: "mastermind.fresh_conversation_turn_request.v1",
            _REPLY: "mastermind.fresh_conversation_turn_reply.v1",
            _UNKNOWN: "mastermind.fresh_conversation_turn_unknown.v1"}
        if (value.event_type != kind or value.aggregate_type != _AGGREGATE
                or value.aggregate_id != root_id or value.actor != _ACTOR or value.job_id != root_id
                or type(value.payload) is not dict or value.payload.get("schema") != schemas[kind]):
            raise ValueError("CONVERSATION_RECORD_CHANGED")
    return value


def _append(runtime, connection, *, command, kind, root_id, payload, attempt_id=None):
    runtime.store.append_event(connection, aggregate_type=_AGGREGATE, aggregate_id=root_id,
        event_type=kind, actor=_ACTOR, job_id=root_id, attempt_id=attempt_id,
        command_id=command, payload=payload)


def _parent(owner, principal, request):
    # Actual original owner revalidates receipt/namespace/current authority and
    # initial seal, including ordinary terminal read after retained cleanup.
    selected = {key: request[key] for key in ("work_ref", "operation_key")}
    return selected


async def _initial(owner, principal, request):
    selected = _parent(owner, principal, request)
    data = await owner.read(principal, selected)
    if data["locator"] is None or data["result"] is None:
        raise ValueError("CONVERSATION_INITIAL_RESULT_UNAVAILABLE")
    if "initial_digest" in request and request["initial_digest"] != data["result"]["digest"]:
        raise ValueError("CONVERSATION_INITIAL_RESULT_CHANGED")
    root = owner._runtime.jobs.get_job(data["locator"]["root_job_id"])
    creation = owner._runtime.store.unique_root_created_event(root.job_id)
    identity = dict(principal=_scope(principal), work_ref=request["work_ref"],
        operation_key=request["operation_key"], root_job_id=root.job_id,
        root_event_id=creation.event_id, root_event_sha256=wire.canonical_digest(creation.to_dict()),
        initial_digest=data["result"]["digest"], locator=data["locator"])
    return data, root, identity


def _consumption(owner, identity):
    command = _command("consume", identity["principal"], identity["root_job_id"])
    event = _event(owner._runtime, command, _CONSUME, identity["root_job_id"])
    if event is None:
        return None
    if event.payload != dict(schema="mastermind.fresh_conversation_initial_consumption.v1", **identity):
        raise ValueError("CONVERSATION_CONSUMPTION_CHANGED")
    return dict(state="CONSUMED", event_id=event.event_id,
        event_sha256=wire.canonical_digest(event.to_dict()), initial_digest=identity["initial_digest"])


def _live(owner, principal, workspace, request, host_current, identity):
    if not callable(host_current) or host_current() is not None:
        raise ValueError("CONVERSATION_REQUEST_CLOSED")
    owner._current(principal)
    binding = owner._fresh(principal)
    project = owner._project(principal, workspace, request["work_ref"])
    from control_plane.fresh_conversation_admission import read_creation_restriction
    from control_plane.executive_runtime import normalize_executive_dialogue_source
    root = owner._runtime.jobs.get_job(identity["root_job_id"])
    material = read_creation_restriction(owner._runtime, root)
    raw = owner._service._ceo_ingress_dialogue_source_provider(material["intent_id"], request["work_ref"])
    source = normalize_executive_dialogue_source(raw, work_ref=request["work_ref"])
    if wire.canonical_digest(source.to_dict()) != material["dialogue_source_sha256"]:
        raise ValueError("CONVERSATION_SOURCE_CHANGED")
    dispatch = owner._service._native_operator_dispatch
    if (dispatch is None or dispatch.retained is None
            or dispatch.retained.job.root_job_id != identity["root_job_id"]
            or dispatch.retained.job.job_id != identity["locator"]["job_id"]):
        raise ValueError("CONVERSATION_WRITER_UNAVAILABLE")
    supervisor = owner._service._require_operator_supervisor()
    facts = supervisor._require_retained_native(dispatch.retained)
    if facts.attempt_id != identity["locator"]["attempt_id"]:
        raise ValueError("CONVERSATION_WRITER_CHANGED")
    return dispatch, wire.canonical_digest(dataclasses.asdict(facts)), binding, project


def _response(request, state, *, consumption, locator, effect="NONE", result=None, can_send=False):
    return dict(schema="mastermind.executive.fresh_conversation_turn_data.v1",
        work_ref=request["work_ref"], operation_key=request["operation_key"],
        turn_key=request.get("turn_key"), state=state, effect=effect,
        initial_consumption=consumption, locator=locator, result=result,
        parent_consumed=False, can_send=can_send, reference=None)


async def consume_initial(owner, principal, workspace, request, *, host_current):
    owner._current(principal)
    owner._project(principal, workspace, request["work_ref"])
    initial, root, identity = await _initial(owner, principal, request)
    existing = _consumption(owner, identity)
    if existing is not None:
        captured = _live(owner, principal, workspace, request, host_current, identity)
        return _response(request, "CONSUMED", consumption=existing, locator=identity["locator"],
            can_send=not captured[0].continuation.done())
    captured = _live(owner, principal, workspace, request, host_current, identity)
    def check():
        if _live(owner, principal, workspace, request, host_current, identity) != captured:
            raise ValueError("CONVERSATION_CONTEXT_CHANGED")
    check()
    command = _command("consume", identity["principal"], root.job_id)
    with owner._runtime.store.transaction() as connection:
        check()
        _append(owner._runtime, connection, command=command, kind=_CONSUME, root_id=root.job_id,
            payload=dict(schema="mastermind.fresh_conversation_initial_consumption.v1", **identity),
            attempt_id=identity["locator"]["attempt_id"])
        check()
    return _response(request, "CONSUMED", consumption=_consumption(owner, identity),
        locator=identity["locator"], effect="COMMITTED", can_send=True)


@dataclass(frozen=True, slots=True)
class FreshConversationTurnSource:
    _seal: object
    _owner: object
    _dispatch: object
    _command: str
    _payload: bytes
    _guard: object
    _completion: asyncio.Future
    _deadline: float

    def check(self):
        from control_plane.fresh_conversation import FreshConversationOwner
        if (self._seal is not _SEAL or type(self._owner) is not FreshConversationOwner
                or getattr(self._dispatch, "_fresh_turn_source", None) is not self
                or self._owner._service._native_operator_dispatch is not self._dispatch
                or not callable(self._guard) or time.monotonic() >= self._deadline):
            raise ValueError("CONVERSATION_TURN_SOURCE_REQUIRED")
        self._guard()
        payload = json.loads(self._payload)
        event = _event(self._owner._runtime, self._command, _REQUEST, payload["root_job_id"])
        if event is None or event.payload != payload:
            raise ValueError("CONVERSATION_TURN_SOURCE_CHANGED")
        return event, payload


def _recorded_reply(owner, requested):
    """Rejoin a reply to its exact native candidate; UNKNOWN never grants a turn."""
    runtime = owner._runtime
    payload, root_id = requested.payload, requested.payload["root_job_id"]
    unknown = _event(runtime, requested.command_id + ":unknown", _UNKNOWN, root_id)
    if unknown is not None:
        if unknown.payload.get("request_event_id") != requested.event_id:
            raise ValueError("CONVERSATION_TURN_SOURCE_CHANGED")
        return None
    replied = _event(runtime, requested.command_id + ":reply", _REPLY, root_id)
    if replied is None:
        return None
    data, locator = replied.payload, payload["identity"]["locator"]
    candidate = runtime.events.get_event_by_command_id("ohf-candidate:" + data["turn_id"])
    if (data.get("request_event_id") != requested.event_id
            or data.get("request_event_sha256") != wire.canonical_digest(requested.to_dict())
            or data.get("operation_id") != payload["operation_id"]
            or data.get("native_acknowledged") is not True or data.get("parent_consumed") is not False
            or data["result"]["digest"] != wire.canonical_digest(data["result"]["envelope"])
            or candidate is None or candidate.event_type != "OHF_CANDIDATE_RESULT_RECORDED"
            or candidate.aggregate_id != data["turn_id"] or candidate.job_id != locator["job_id"]
            or candidate.attempt_id != locator["attempt_id"] or candidate.event_id != data["candidate_event_id"]
            or replied.attempt_id != locator["attempt_id"]
            or wire.canonical_digest(candidate.to_dict()) != data["candidate_event_sha256"]
            or len(json.dumps(data["result"]["envelope"], ensure_ascii=False).encode()) > 16384):
        raise ValueError("CONVERSATION_TURN_RESULT_CHANGED")
    return replied


def _settled_history_head(owner, identity, consumption, connection=None):
    """Bound previews/reservations to the latest settled immutable request."""
    if connection is None:
        with owner._runtime.store.read() as reader:
            return _settled_history_head(owner, identity, consumption, reader)
    row = connection.execute(
        "SELECT command_id FROM events WHERE aggregate_type=? AND aggregate_id=? AND event_type=? ORDER BY event_id DESC LIMIT 1",
        (_AGGREGATE, identity["root_job_id"], _REQUEST)).fetchone()
    if row is None:
        return None
    requested = _event(owner._runtime, row["command_id"], _REQUEST, identity["root_job_id"])
    payload = requested.payload
    if (payload.get("identity") != identity or payload.get("consumption") != consumption
            or requested.command_id != _command("turn", identity["principal"], identity["root_job_id"], payload["turn_key"])):
        raise ValueError("CONVERSATION_TURN_HISTORY_CHANGED")
    replied = _recorded_reply(owner, requested)
    if replied is None:
        raise ValueError("CONVERSATION_TURN_ALREADY_RESERVED")
    return dict(request_event_id=requested.event_id, request_event_sha256=wire.canonical_digest(requested.to_dict()),
        reply_event_id=replied.event_id, reply_event_sha256=wire.canonical_digest(replied.to_dict()))


def _preview_digest(request, identity, consumption, captured, history_head):
    # Correlation DATA only. Each preview/send independently obtains current
    # source, project, principal and actual retained writer/ACK qualification.
    return wire.canonical_digest(dict(
        request={k: v for k, v in request.items() if k != "preview_digest"},
        identity=identity, consumption=consumption, history_head=history_head, writer_digest=captured[1],
        profile_digest=wire.canonical_digest(captured[2]),
        project_digest=wire.canonical_digest(captured[3])))


async def preview_turn(owner, principal, workspace, request, *, host_current):
    owner._current(principal)
    initial, root, identity = await _initial(owner, principal, request)
    consumption = _consumption(owner, identity)
    if consumption is None:
        raise ValueError("CONVERSATION_INITIAL_NOT_CONSUMED")
    captured = _live(owner, principal, workspace, request, host_current, identity)
    if (captured[0].continuation.done() or _event(owner._runtime,
            _command("turn", identity["principal"], root.job_id, request["turn_key"]), _REQUEST, root.job_id) is not None):
        raise ValueError("CONVERSATION_TURN_ALREADY_RESERVED")
    history_head = _settled_history_head(owner, identity, consumption)
    if (_live(owner, principal, workspace, request, host_current, identity) != captured
            or _consumption(owner, identity) != consumption
            or _settled_history_head(owner, identity, consumption) != history_head):
        raise ValueError("CONVERSATION_CONTEXT_CHANGED")
    return dict(schema="mastermind.executive.fresh_conversation_turn_preview.v1",
        work_ref=request["work_ref"], operation_key=request["operation_key"], reference=None,
        turn_key=request["turn_key"], state="TURN_READY", effect="NONE",
        initial_consumption=consumption, locator=identity["locator"],
        preview_digest=_preview_digest(request, identity, consumption, captured, history_head),
        parent_consumed=False, can_send=True)


async def submit_turn(owner, principal, workspace, request, *, host_current):
    owner._current(principal)
    owner._project(principal, workspace, request["work_ref"])
    root = _original_root(owner, principal, request)
    prior_command = _command("turn", _scope(principal), root.job_id, request["turn_key"])
    original = _event(owner._runtime, prior_command, _REQUEST, root.job_id)
    if original is not None:
        if original.payload.get("request_sha256") != wire.canonical_digest(request):
            raise ValueError("CONVERSATION_TURN_CONFLICT")
        return await read_turn(owner, principal, request)
    initial, root, identity = await _initial(owner, principal, request)
    consumption = _consumption(owner, identity)
    if consumption is None:
        raise ValueError("CONVERSATION_INITIAL_NOT_CONSUMED")
    command = _command("turn", identity["principal"], root.job_id, request["turn_key"])
    prior = _event(owner._runtime, command, _REQUEST, root.job_id)
    request_sha = wire.canonical_digest(request)
    if prior is not None:
        if prior.payload.get("request_sha256") != request_sha or prior.payload.get("identity") != identity:
            raise ValueError("CONVERSATION_TURN_CONFLICT")
        return await read_turn(owner, principal, request)
    captured = _live(owner, principal, workspace, request, host_current, identity)
    history_head = _settled_history_head(owner, identity, consumption)
    if ("preview_digest" in request
            and request["preview_digest"] != _preview_digest(request, identity, consumption, captured, history_head)):
        raise ValueError("CONVERSATION_TURN_PREVIEW_CHANGED")
    dispatch = captured[0]
    if dispatch.continuation.done():
        raise ValueError("CONVERSATION_TURN_ALREADY_RESERVED")
    def guard():
        if (_live(owner, principal, workspace, request, host_current, identity) != captured
                or _consumption(owner, identity) != consumption):
            raise ValueError("CONVERSATION_CONTEXT_CHANGED")
    guard()
    operation = OperationId("ohf-op:native-continuation:" + wire.canonical_digest(
        dict(command=command, initial_digest=identity["initial_digest"])))
    payload = dict(schema="mastermind.fresh_conversation_turn_request.v1", root_job_id=root.job_id,
        identity=identity, consumption=consumption, request_sha256=request_sha,
        turn_key=request["turn_key"], message=request["message"], operation_id=operation.command_id,
        previous_turn=history_head, writer_digest=captured[1], profile_digest=wire.canonical_digest(captured[2]),
        project_digest=wire.canonical_digest(captured[3]))
    with owner._runtime.store.transaction() as connection:
        guard()
        if (dispatch.continuation.done()
                or _settled_history_head(owner, identity, consumption, connection) != history_head):
            raise ValueError("CONVERSATION_TURN_PREVIEW_CHANGED")
        _append(owner._runtime, connection, command=command, kind=_REQUEST, root_id=root.job_id,
            payload=payload, attempt_id=identity["locator"]["attempt_id"])
        guard()
    source = FreshConversationTurnSource(_SEAL, owner, dispatch, command,
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(),
        guard, asyncio.get_running_loop().create_future(),
        time.monotonic() + min(300.0, principal.expires_at - time.time(), workspace.expires_at - time.time()))
    dispatch._fresh_turn_source = source
    source.check()
    # Signal only the incumbent single native waiter. Reopened/status/duplicate
    # requests never signal it again or re-enter a provider operation.
    dispatch.continuation.set_result(source)
    await asyncio.shield(source._completion)
    return await read_turn(owner, principal, request)


async def execute_attended_turn(service, dispatch, source):
    """Exact private service branch; public DATA/type labels cannot enter it."""
    if type(source) is not FreshConversationTurnSource or source._dispatch is not dispatch:
        raise ValueError("CONVERSATION_TURN_SOURCE_REQUIRED")
    owner, retained = source._owner, dispatch.retained
    # This sealed request already owns the reservation even when its live
    # reader closes before the service begins executing it.
    payload = json.loads(source._payload)
    event = None
    try:
        event = _event(owner._runtime, source._command, _REQUEST, payload["root_job_id"])
        if service is not owner._service:
            raise ValueError("CONVERSATION_TURN_SOURCE_REQUIRED")
        supervisor = service._require_operator_supervisor()
        operation = OperationId(payload["operation_id"])
        event, payload = source.check()
        # Renew only for this newly qualified request, under the incumbent
        # Attempt owner. Idle waiting never renews a lease or retries a turn.
        supervisor.retain_native_wait_window(retained)
        source.check()
        from control_plane.remote_operator_harness_adapter import RemoteOperatorHarnessAdapter
        if isinstance(retained.adapter, RemoteOperatorHarnessAdapter):
            retained.adapter.bind_native_continuation_guard(source.check,
                attempt_id=retained.session.attempt_id, operation_id=operation)
        base_prompt = supervisor._prompt(retained.job, retained.lease)
        prompt = base_prompt + "\nAttended original-parent follow-up. Answer this exact message in the same closed result envelope's summary. Do not launch children or claim parent consumption.\n" + json.dumps(payload["message"], ensure_ascii=False)
        def load_turn(_turn):
            source.check()
            return prompt
        retained.adapter.turn_input_loader = load_turn
        source.check()
        receipt = await asyncio.to_thread(supervisor._orchestrator(retained.lease, retained.adapter).run_turn,
            retained.session, operation_id=operation,
            timeout_seconds=min(300.0, source._deadline - time.monotonic()))
        source.check()
        raw = retained.adapter.observe_raw_role_result(receipt.turn)
        from control_plane.executive_orchestration_result import RawRoleResultObservation, parse_and_validate_envelope
        if type(raw) is not RawRoleResultObservation:
            raise ValueError("CONVERSATION_TURN_RESULT_UNAVAILABLE")
        if (receipt.start.acknowledged is not True
                or any(getattr(raw, key) != getattr(receipt.turn, key)
                    for key in ("attempt_id", "session_epoch_id", "process_generation_id", "turn_id"))
                or raw.provider_session_id != retained.session.observation.provider_session_id
                or raw.provider_native_turn_id != receipt.start.provider_native_turn_id
                or raw.provider_turn_artifact_digest != receipt.candidate.artifact_digest):
            raise ValueError("CONVERSATION_TURN_RESULT_CHANGED")
        envelope = parse_and_validate_envelope(raw.canonical_result_json,
            expected_job_id=retained.job.job_id, expected_run_id=retained.session.attempt_id,
            expected_worker_id=retained.lease.attempt.worker_id,
            expected_role="plan", expected_root_job_id=retained.job.root_job_id)
        encoded = json.dumps(envelope, ensure_ascii=False).encode()
        if len(encoded) > 16384:
            raise ValueError("CONVERSATION_TURN_RESULT_OVER_LIMIT")
        candidate = owner._runtime.events.get_event_by_command_id("ohf-candidate:" + receipt.turn.turn_id)
        if (candidate is None or candidate.event_type != "OHF_CANDIDATE_RESULT_RECORDED"
                or candidate.attempt_id != retained.session.attempt_id
                or candidate.payload["turn"] != dataclasses.asdict(receipt.turn)):
            raise ValueError("CONVERSATION_TURN_CANDIDATE_UNAVAILABLE")
        reply = dict(schema="mastermind.fresh_conversation_turn_reply.v1",
            request_event_id=event.event_id, request_event_sha256=wire.canonical_digest(event.to_dict()),
            operation_id=operation.command_id, turn_id=receipt.turn.turn_id,
            candidate_event_id=candidate.event_id, candidate_event_sha256=wire.canonical_digest(candidate.to_dict()),
            native_acknowledged=True, result=dict(digest=wire.canonical_digest(envelope), envelope=envelope),
            parent_consumed=False)
        with owner._runtime.store.transaction() as connection:
            source.check()
            _append(owner._runtime, connection, command=source._command + ":reply", kind=_REPLY,
                root_id=payload["root_job_id"], payload=reply,
                attempt_id=retained.session.attempt_id)
            source.check()
        # The service rearms its same waiter before acknowledging the HTTP
        # result, so an immediate next send cannot race a completed Future.
    except BaseException as exc:
        # The original request record remains the sole recovery identity.
        # Never infer a second request is permitted from an absent reply.
        try:
            if event is not None and event.payload == payload:
                with owner._runtime.store.transaction() as connection:
                    _append(owner._runtime, connection, command=source._command + ":unknown", kind=_UNKNOWN,
                        root_id=payload["root_job_id"], payload=dict(schema="mastermind.fresh_conversation_turn_unknown.v1",
                            request_event_id=event.event_id, reason="ORIGINAL_TURN_REQUIRES_RECONCILIATION"),
                        attempt_id=retained.session.attempt_id)
        finally:
            if not source._completion.done(): source._completion.set_result(None)
        raise


def _original_root(owner, principal, request):
    from control_plane.fresh_conversation import scoped_operation_key
    from control_plane import ceo_intent, ceo_request
    owner._current(principal, read_only=True)
    key = scoped_operation_key(principal, request["operation_key"])
    intent_id = ceo_request.automated_intent_id(ceo_request.app_request_ref(key))
    command = ceo_intent.command_id_for(intent_id)
    receipt = ceo_intent.resolve_intent(owner._runtime, intent_id)
    root = owner._runtime.jobs.get_job(receipt["job_id"])
    owner._require_fresh_original(root, principal, request, command)
    return root


def _retained_identity(owner, principal, request, root, requested):
    # Original READ is independent of the live provider writer during/after
    # ordinary cleanup. Rejoin immutable root, child and first role seal.
    identity = requested.payload["identity"]
    creation = owner._runtime.store.unique_root_created_event(root.job_id)
    locator = identity["locator"]
    child = owner._runtime.jobs.get_job(locator["job_id"])
    attempt = owner._runtime.attempts.get_attempt(locator["attempt_id"])
    child_event = owner._runtime.events.get_event_by_command_id(f"coo-cycle:{root.job_id}:create-interactive:0")
    if (identity["principal"] != _scope(principal) or identity["work_ref"] != request["work_ref"]
            or identity["operation_key"] != request["operation_key"] or identity["root_job_id"] != root.job_id
            or identity["root_event_id"] != creation.event_id
            or identity["root_event_sha256"] != wire.canonical_digest(creation.to_dict())
            or child is None or child.root_job_id != root.job_id or child.parent_job_id != root.job_id
            or child_event is None or child_event.job_id != child.job_id
            or attempt is None or attempt.job_id != child.job_id
            or child.current_attempt_id != attempt.attempt_id):
        raise ValueError("CONVERSATION_ORIGINAL_CHANGED")
    from control_plane.executive_runtime import _sealed_role_result_payload
    with owner._runtime.store.read() as connection:
        seal = _sealed_role_result_payload(connection, attempt_id=attempt.attempt_id, expected_role="plan")
    if (seal["job_id"] != child.job_id or seal["worker_id"] != attempt.worker_id
            or seal["effective_grant_digest"] != attempt.effective_grant_digest
            or wire.canonical_digest(seal["result_envelope"]) != identity["initial_digest"]):
        raise ValueError("CONVERSATION_INITIAL_RESULT_CHANGED")
    return identity


async def read_turn(owner, principal, request):
    root = _original_root(owner, principal, request)
    command = _command("turn", _scope(principal), root.job_id, request["turn_key"])
    requested = _event(owner._runtime, command, _REQUEST, root.job_id)
    if requested is None:
        # An absent turn says nothing about permission to create/resend it.
        selected = {key: request[key] for key in ("work_ref", "operation_key")}
        data = await owner.status(principal, selected)
        return _response(request, "ABSENT", consumption=None, locator=data["locator"])
    identity = _retained_identity(owner, principal, request, root, requested)
    consumption = _consumption(owner, identity)
    if consumption is None or consumption != requested.payload["consumption"]:
        raise ValueError("CONVERSATION_CONSUMPTION_CHANGED")
    if requested.payload.get("identity") != identity or requested.payload.get("turn_key") != request["turn_key"]:
        raise ValueError("CONVERSATION_TURN_SOURCE_CHANGED")
    replied = _recorded_reply(owner, requested)
    if replied is None:
        return _response(request, "RECONCILIATION_REQUIRED", consumption=consumption,
            locator=identity["locator"], effect="UNKNOWN")
    data = replied.payload
    owner._current(principal, read_only=True)
    return _response(request, "RECORDED", consumption=consumption, locator=identity["locator"],
        effect="COMMITTED", result=data["result"])
