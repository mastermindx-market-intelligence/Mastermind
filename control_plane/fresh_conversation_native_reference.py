"""Native history projections on the original FreshConversation READ owner.

Text stays in its immutable creation/request Event. These bounded views and
fragments add no text store, execution owner, provider call or Send authority.
Native seals are result evidence; they are never rendered as answer text.
"""
from __future__ import annotations

import dataclasses
import hashlib

from common import fresh_conversation_contract as wire
from control_plane.fresh_conversation_admission import NATIVE_SCHEMA
from control_plane.fresh_conversation_native import result_projection

_PREVIEW_BYTES = 256
_FRAGMENT_BYTES = 4096


def initial_message(material):
    if material.get("schema") != NATIVE_SCHEMA:
        raise ValueError("CONVERSATION_NATIVE_CONTRACT_REQUIRED")
    text = wire.validate_native_message(material["initial_message"])
    raw = text.encode("utf-8")
    if (hashlib.sha256(raw).hexdigest() != material["initial_message_sha256"]
            or len(raw) != material["initial_message_utf8_bytes"]
            or material["result_contract"] != wire.NATIVE_RESULT_CONTRACT):
        raise ValueError("CONVERSATION_INITIAL_MESSAGE_CHANGED")
    return text


def input_descriptor(text, event):
    wire.validate_native_message(text)
    raw = text.encode("utf-8")
    preview = raw[:_PREVIEW_BYTES].decode("utf-8", errors="ignore")
    return dict(preview=preview, sha256=hashlib.sha256(raw).hexdigest(),
        utf8_bytes=len(raw), complete=len(preview.encode("utf-8")) == len(raw),
        source_event_id=event.event_id, source_event_sha256=wire.canonical_digest(event.to_dict()))


def _context(owner, root, material, reference, origin):
    """Only canonical history and an optional current writer observation."""
    from control_plane.fresh_conversation_turn import _command, _event, _CONSUME
    runtime = owner._runtime
    creation = runtime.store.unique_root_created_event(root.job_id)
    key = creation.payload.get("fresh_conversation_original_request")
    if (type(key) is not dict or set(key) != {"schema", "operation_key", "creation_digest"}
            or key["schema"] != "mastermind.fresh_conversation_original_request.v1"
            or key["creation_digest"] != wire.canonical_digest(material)):
        raise ValueError("CONVERSATION_ORIGINAL_KEY_CHANGED")
    wire.validate_native_request(dict(work_ref=material["work_ref"], operation_key=key["operation_key"]), operation="read")
    child_event = runtime.events.get_event_by_command_id(f"coo-cycle:{root.job_id}:create-interactive:0")
    child = runtime.jobs.get_job(child_event.job_id) if child_event else None
    locator = dict(work_ref=material["work_ref"], root_job_id=root.job_id, job_id=None, attempt_id=None)
    refs, epoch, state = (), None, "ADMITTED"
    if child is not None:
        if child.root_job_id != root.job_id or child.parent_job_id != root.job_id:
            raise ValueError("CONVERSATION_ORIGINAL_CHILD_CHANGED")
        runtime.jobs.assert_native_conversation_execution(child.job_id)
        locator.update(job_id=child.job_id, attempt_id=child.current_attempt_id)
        if child.current_attempt_id:
            attempt = runtime.attempts.get_attempt(child.current_attempt_id)
            if attempt is None or attempt.job_id != child.job_id:
                raise ValueError("CONVERSATION_ORIGINAL_ATTEMPT_CHANGED")
            refs = tuple(runtime.operator_harness.native_conversation_results(attempt_id=attempt.attempt_id))
            for ref in refs:
                value = runtime.operator_harness.native_conversation_result(attempt_id=attempt.attempt_id, reference=ref)
                if value["job_id"] != child.job_id or value["worker_id"] != attempt.worker_id:
                    raise ValueError("CONVERSATION_NATIVE_RESULT_CHANGED")
            state = "RECONCILIATION_REQUIRED"
            if child.status.value == "COMPLETED":
                if not refs:
                    raise ValueError("CONVERSATION_TERMINAL_RESULT_UNAVAILABLE")
                runtime.operator_harness.native_conversation_terminal_payload(attempt_id=attempt.attempt_id, reference=refs[-1])
                state = "SETTLED"
            else:
                try:
                    facts = runtime.current_harness_binding_source(attempt.attempt_id)
                    if facts.job_id != child.job_id:
                        raise ValueError("CONVERSATION_WRITER_CHANGED")
                    epoch = dict(attempt_id=facts.attempt_id,
                        generation_digest=wire.canonical_digest(dict(session_epoch_id=facts.session_epoch_id,
                            process_generation_id=facts.process_generation_id, generation=facts.generation_number)),
                        binding_digest=wire.canonical_digest(dataclasses.asdict(facts)))
                    state = "RETAINED"
                except Exception:
                    # History remains readable after process/lease loss. This
                    # absence never authorizes a replacement writer or resume.
                    epoch = None
    initial = result_projection(refs[0]) if refs else None
    head = result_projection(refs[-1]) if refs else None
    scope = wire.canonical_digest(origin)
    identity = dict(principal=scope, work_ref=material["work_ref"], operation_key=key["operation_key"],
        root_job_id=root.job_id, root_event_id=creation.event_id,
        root_event_sha256=wire.canonical_digest(creation.to_dict()),
        initial_digest=initial["digest"] if initial else None, locator=locator)
    consumed = _event(runtime, _command("consume", scope, root.job_id), _CONSUME, root.job_id)
    consumption = None
    if consumed is not None:
        if initial is None or consumed.payload != dict(schema="mastermind.fresh_conversation_initial_consumption.v1", **identity):
            raise ValueError("CONVERSATION_CONSUMPTION_CHANGED")
        consumption = dict(state="CONSUMED", event_id=consumed.event_id,
            event_sha256=wire.canonical_digest(consumed.to_dict()), initial_digest=initial["digest"])
    return dict(locator=locator, epoch=epoch, state=state, initial_result=initial,
        head_result=head, initial_consumption=consumption), identity


def _turn(owner, root, identity, consumption, command):
    from control_plane.fresh_conversation_turn import _command, _event, _REQUEST, _native_recorded_result
    requested = _event(owner._runtime, command, _REQUEST, root.job_id)
    if requested is None:
        raise ValueError("CONVERSATION_TURN_HISTORY_CHANGED")
    payload = requested.payload
    if (payload.get("schema") != "mastermind.fresh_conversation_turn_request.v1"
            or payload.get("result_contract") != wire.NATIVE_RESULT_CONTRACT
            or payload.get("root_job_id") != root.job_id or payload.get("identity") != identity
            or consumption is None or payload.get("consumption") != consumption
            or command != _command("turn", identity["principal"], root.job_id, payload["turn_key"])
            or requested.attempt_id != identity["locator"]["attempt_id"]):
        raise ValueError("CONVERSATION_TURN_HISTORY_CHANGED")
    wire.validate_native_message(payload["message"])
    resolved = _native_recorded_result(owner, requested)
    return requested, dict(turn_key=payload["turn_key"], input=input_descriptor(payload["message"], requested),
        state="RECORDED" if resolved else "RECONCILIATION_REQUIRED",
        result=resolved[0] if resolved else None, parent_consumed=False)


def read_native_reference(owner, principal, reference, root, material, origin, *, before=None, fragment=None):
    from control_plane.fresh_conversation_reference import _original, _bounded, _encoded_size, _LIMIT
    from control_plane.fresh_conversation_turn import _command, _REQUEST
    context, identity = _context(owner, root, material, reference, origin)
    creation = owner._runtime.store.unique_root_created_event(root.job_id)
    text = initial_message(material)
    descriptor = input_descriptor(text, creation)
    if fragment is not None:
        event = creation
        if fragment["kind"] == "turn_input":
            command = _command("turn", identity["principal"], root.job_id, fragment["turn_key"])
            event, turn = _turn(owner, root, identity, context["initial_consumption"], command)
            text, descriptor = event.payload["message"], turn["input"]
        if any(fragment[key] != descriptor[key] for key in ("sha256", "source_event_id", "source_event_sha256")):
            raise ValueError("CONVERSATION_INPUT_SOURCE_CHANGED")
        raw, start = text.encode("utf-8"), fragment["offset_utf8"]
        if type(start) is not int or not 0 <= start < len(raw):
            raise ValueError("CONVERSATION_INPUT_OFFSET_INVALID")
        try:
            raw[:start].decode("utf-8")  # Exact scalar boundary; never round a caller's cursor.
        except UnicodeDecodeError:
            raise ValueError("CONVERSATION_INPUT_OFFSET_INVALID") from None
        part = raw[start:start + _FRAGMENT_BYTES].decode("utf-8", errors="ignore")
        end = start + len(part.encode("utf-8"))
        if end <= start:
            raise ValueError("CONVERSATION_INPUT_OFFSET_INVALID")
        result = dict(schema="mastermind.fresh_conversation_input_fragment.v1", reference=dict(reference),
            fragment=dict(fragment), text=part, utf8_bytes=len(raw), next_offset_utf8=end if end < len(raw) else None)
    else:
        with owner._runtime.store.read() as connection:
            rows = connection.execute("""SELECT command_id,event_id FROM events
                WHERE aggregate_type='fresh_conversation' AND aggregate_id=? AND event_type=?
                  AND (? IS NULL OR event_id<?) ORDER BY event_id DESC LIMIT ?""",
                (root.job_id, _REQUEST, before, before, _LIMIT + 1)).fetchall()
        page = dict(kind="initial" if before is None else "history", before_event_id=before, next_before_event_id=None)
        result = dict(schema="mastermind.fresh_conversation_window.v3", kind="fresh_native",
            reference=dict(reference), **context, initial_input=descriptor,
            initial_digest=context["initial_result"]["digest"] if context["initial_result"] else None,
            turns=[], page=page, can_send=False, parent_consumed=False)
        turns, oldest = [], None
        for index, row in enumerate(rows[:_LIMIT]):
            event, turn = _turn(owner, root, identity, context["initial_consumption"], row["command_id"])
            if event.event_id != row["event_id"]:
                raise ValueError("CONVERSATION_TURN_HISTORY_CHANGED")
            candidate = {**result, "turns": list(reversed([*turns, turn])),
                "page": {**page, "next_before_event_id": row["event_id"] if index + 1 < len(rows) else None}}
            if _encoded_size(candidate) > 28000:
                if not turns:
                    raise ValueError("CONVERSATION_REFERENCE_RESPONSE_OVER_BUDGET")
                page["next_before_event_id"] = oldest
                break
            turns.append(turn)
            oldest = row["event_id"]
            result["turns"] = candidate["turns"]
            page["next_before_event_id"] = candidate["page"]["next_before_event_id"]
    if _original(owner, principal, reference) != (root, material, origin):
        raise ValueError("CONVERSATION_REFERENCE_CHANGED")
    if _context(owner, root, material, reference, origin) != (context, identity):
        raise ValueError("CONVERSATION_HISTORY_CHANGED")
    return _bounded(result)


async def read_native_content(owner, principal, reference, root, material, origin, selector, *, guard=None):
    """Resolve one original seal through the installed finite native READ."""
    from common.session_bridge_private_contract import (
        PRIVATE_SCHEMA, PRIVATE_RESULT_SCHEMA, SessionBridgeIngressOwner)
    from control_plane.native_conversation_read_contract import RESULT_SCHEMA
    from control_plane.native_conversation_read_contract import _result_data
    from control_plane.native_continuation import _digest as bridge_digest
    from control_plane.fresh_conversation_reference import _original, _bounded
    factory = owner._app.session_bridge_provider_factory
    if not callable(factory):
        raise ValueError("CONVERSATION_NATIVE_CONTENT_UNAVAILABLE")
    provider = factory(owner._runtime)
    if type(provider) is not SessionBridgeIngressOwner:
        raise ValueError("CONVERSATION_NATIVE_CONTENT_UNAVAILABLE")

    def current():
        if guard is not None:
            # The incumbent service guard returns True; the private native
            # before-write capability is deliberately synchronous/None.
            if guard() is not True:
                raise ValueError("CONVERSATION_NATIVE_CONTENT_HOST_CHANGED")
        if (owner._app.session_bridge_provider_factory is not factory
                or _original(owner, principal, reference) != (root, material, origin)):
            raise ValueError("CONVERSATION_NATIVE_CONTENT_SOURCE_CHANGED")

    current()
    selection = dict(work_ref=reference["work_ref"], root_job_id=reference["root_job_id"])
    request = dict(kind="result", **selector)
    projection = {key: getattr(principal, key) for key in (
        "policy_id", "issuer", "issuer_digest", "resource", "subject_digest",
        "client_ref", "issued_at", "expires_at", "jti_digest")}
    projection["scopes"] = list(principal.scopes)
    reply = await provider.handle_frame(dict(schema=PRIVATE_SCHEMA, tool="session_native_read",
        principal=projection, arguments=dict(selection=selection, read=request)), native_read_guard=current)
    current()
    if (type(reply) is not dict or set(reply) != {"schema", "tool", "ok", "data", "error"}
            or reply["schema"] != PRIVATE_RESULT_SCHEMA or reply["tool"] != "session_native_read"
            or reply["ok"] is not True or reply["error"] is not None):
        raise ValueError("CONVERSATION_NATIVE_CONTENT_UNAVAILABLE")
    data = reply["data"]
    if (type(data) is not dict or set(data) != {"schema", "selection", "read", "association_sha256",
            "root_event_id", "root_event_sha256", "native_session_id", "native", "observational_only",
            "can_send", "parent_consumed"}
            or data["schema"] != RESULT_SCHEMA or data["selection"] != selection or data["read"] != request
            or data["root_event_id"] != reference["root_event_id"]
            # Session Bridge retains its ASCII Event codec; Fresh references
            # retain UTF-8. Both hash the same original immutable Event.
            or data["root_event_sha256"] != bridge_digest(owner._runtime.store.unique_root_created_event(root.job_id).to_dict())
            or data["observational_only"] is not True or data["can_send"] is not False
            or data["parent_consumed"] is not False):
        raise ValueError("CONVERSATION_NATIVE_CONTENT_CHANGED")
    native = data["native"]
    _result_data(native, dict(kind="result", claim=native["claim"], terminal=native["terminal"],
        offset_bytes=selector["offset_bytes"], expected_sha256=selector["expected_sha256"]))
    if native["claim"]["sessionId"] != data["native_session_id"]:
        raise ValueError("CONVERSATION_NATIVE_CONTENT_SESSION_CHANGED")
    current()
    return _bounded(dict(schema="mastermind.fresh_conversation_native_content.v1",
        reference=dict(reference), content=dict(selector), native_session_id=data["native_session_id"],
        association_sha256=data["association_sha256"], native=native))
