"""Bounded original-parent READ of fresh-native conversations; no new store.

References are immutable source locators, never targets or grants. A pure READ
policy may match the original submit identity only through the trusted existing
AppPolicies pair selected by the installed host. No submit principal is minted.
"""
from __future__ import annotations
import json
import time
from common import fresh_conversation_contract as wire
from control_plane.fresh_conversation_admission import read_creation_restriction, NATIVE_SCHEMA
from control_plane.principal_projection import NeutralPrincipalProjection

_SCHEMA = "mastermind.fresh_conversation_reference.v1"
_KEYS = {"schema", "work_ref", "root_job_id", "root_event_id", "root_event_sha256", "principal_scope_sha256"}
_IDENTITY = ("policy_id", "issuer_digest", "resource", "subject_digest", "client_ref")
_LIMIT = 8


def origin_identity(owner, principal):
    from control_plane.installed_principal_read_binding import (
        READ_SCOPE, SUBMIT_SCOPE, read_matches_original as _read_matches_original)
    current = {key: getattr(principal,key,None) for key in _IDENTITY}
    if (type(principal) is not NeutralPrincipalProjection or type(principal.issued_at) is not int
            or type(principal.expires_at) is not int or not principal.issued_at <= time.time() < principal.expires_at
            or READ_SCOPE not in principal.scopes or any(type(v) is not str or not v for v in current.values())):
        raise ValueError("CONVERSATION_READ_PRINCIPAL_REQUIRED")
    pair = owner._trusted_read_pair
    expected = tuple(current[key] for key in ("policy_id","issuer_digest","resource"))
    if expected == owner._expected_policy and {READ_SCOPE,SUBMIT_SCOPE} <= set(principal.scopes):
        owner._current(principal,read_only=True)
        return current
    if pair is None:
        raise ValueError("CONVERSATION_READ_POLICY_UNAVAILABLE")
    original = {**current,"policy_id":pair[1].policy_id}
    if not _read_matches_original(original,current,principal,trusted_pair=pair):
        raise ValueError("CONVERSATION_READ_PRINCIPAL_REQUIRED")
    owner._require_host_current(read_only=True)
    return original


def _reference(root, event, material):
    return dict(schema=_SCHEMA,work_ref=material["work_ref"],root_job_id=root.job_id,
        root_event_id=event.event_id,root_event_sha256=wire.canonical_digest(event.to_dict()),
        principal_scope_sha256=material["principal_scope_sha256"])


def _original(owner, principal, reference):
    origin = origin_identity(owner,principal)
    if (type(reference) is not dict or set(reference)!=_KEYS or reference["schema"]!=_SCHEMA
            or type(reference["root_job_id"]) is not str or type(reference["root_event_id"]) is not int
            or reference["principal_scope_sha256"]!=wire.canonical_digest(origin)):
        raise ValueError("CONVERSATION_REFERENCE_INVALID")
    root = owner._runtime.jobs.get_job(reference["root_job_id"])
    if root is None:raise ValueError("CONVERSATION_REFERENCE_UNAVAILABLE")
    material = read_creation_restriction(owner._runtime,root)
    if (material is None or material["work_ref"]!=reference["work_ref"]
            or material["principal_scope_sha256"]!=wire.canonical_digest(origin)):
        raise ValueError("CONVERSATION_REFERENCE_UNAVAILABLE")
    event=owner._runtime.store.unique_root_created_event(root.job_id)
    if _reference(root,event,material)!=reference:
        raise ValueError("CONVERSATION_REFERENCE_CHANGED")
    return root,material,origin


def project_references(owner, principal, selection):
    origin=origin_identity(owner,principal)
    if type(selection) is not dict or set(selection)!={"work_ref"}:
        raise ValueError("CONVERSATION_REFERENCE_SELECTION_INVALID")
    wire.validate_request(dict(work_ref=selection["work_ref"],operation_key="reference-read"),operation="status")
    scope=wire.canonical_digest(origin)
    # One chosen project and one authenticated original identity, no fan-out.
    with owner._runtime.store.read() as connection:
        rows=connection.execute("""SELECT job_id,event_id FROM events
            WHERE event_type='JOB_CREATED' AND aggregate_type='job'
              AND json_extract(payload_json,'$.fresh_conversation_admission.source.work_ref')=?
              AND json_extract(payload_json,'$.fresh_conversation_admission.source.principal_scope_sha256')=?
            ORDER BY event_id DESC LIMIT ?""",(selection["work_ref"],scope,_LIMIT+1)).fetchall()
    entries=[]
    for row in rows[:_LIMIT]:
        root=owner._runtime.jobs.get_job(row["job_id"])
        if root is None:raise ValueError("CONVERSATION_REFERENCE_CHANGED")
        material=read_creation_restriction(owner._runtime,root)
        if material is None or material["work_ref"]!=selection["work_ref"] or material["principal_scope_sha256"]!=scope:
            raise ValueError("CONVERSATION_REFERENCE_CHANGED")
        event=owner._runtime.store.unique_root_created_event(root.job_id)
        if event.event_id!=row["event_id"]:raise ValueError("CONVERSATION_REFERENCE_CHANGED")
        if material["schema"] == NATIVE_SCHEMA:
            from control_plane.fresh_conversation_native_reference import initial_message, input_descriptor
            entries.append(dict(kind="fresh_native", reference=_reference(root,event,material),
                root_state=root.status.value, result_contract=wire.NATIVE_RESULT_CONTRACT,
                initial_input=input_descriptor(initial_message(material), event)))
            continue
        objective=json.loads(root.objective)
        if type(objective) is not dict or objective.get("mode")!="fresh_conversation" or type(objective.get("message")) is not str:
            raise ValueError("CONVERSATION_INITIAL_MESSAGE_UNAVAILABLE")
        entries.append(dict(kind="fresh_native",reference=_reference(root,event,material),
            initial_message=objective["message"],root_state=root.status.value))
    origin_identity(owner,principal)
    catalogue_schema = ("mastermind.fresh_conversation_references.v2"
        if any("initial_input" in row for row in entries) else "mastermind.fresh_conversation_references.v1")
    return _bounded(dict(schema=catalogue_schema,work_ref=selection["work_ref"],
        state="AVAILABLE",coverage=dict(state="PARTIAL" if len(rows)>_LIMIT else "COMPLETE",limit=_LIMIT,returned=len(entries)),entries=entries))


def read_reference(owner, principal, selection, *, guard=None):
    from common.project_conversation_read_contract import arguments
    selected=arguments(selection,"fresh_read")
    before=selected.get("before_event_id")
    reference={key:value for key,value in selected.items() if key not in {"before_event_id", "fragment", "content"}}
    root,material,origin=_original(owner,principal,reference)
    if material["schema"] == NATIVE_SCHEMA:
        if "content" in selected:
            from control_plane.fresh_conversation_native_reference import read_native_content
            return read_native_content(owner, principal, reference, root, material, origin,
                selected["content"], guard=guard)
        from control_plane.fresh_conversation_native_reference import read_native_reference
        return read_native_reference(owner,principal,reference,root,material,origin,
            before=before,fragment=selected.get("fragment"))
    if "fragment" in selected or "content" in selected:
        raise ValueError("CONVERSATION_NATIVE_CONTRACT_REQUIRED")
    objective=json.loads(root.objective)
    if type(objective) is not dict or objective.get("mode")!="fresh_conversation" or type(objective.get("message")) is not str:
        raise ValueError("CONVERSATION_INITIAL_MESSAGE_UNAVAILABLE")
    child_event=owner._runtime.events.get_event_by_command_id(f"coo-cycle:{root.job_id}:create-interactive:0")
    child=owner._runtime.jobs.get_job(child_event.job_id) if child_event else None
    locator=dict(work_ref=material["work_ref"],root_job_id=root.job_id,job_id=None,attempt_id=None)
    initial=epoch=None
    state="ADMITTED"
    if child is not None:
        if child.root_job_id!=root.job_id or child.parent_job_id!=root.job_id:
            raise ValueError("CONVERSATION_ORIGINAL_CHILD_CHANGED")
        locator.update(job_id=child.job_id,attempt_id=child.current_attempt_id)
        if child.current_attempt_id:
            attempt=owner._runtime.attempts.get_attempt(child.current_attempt_id)
            if attempt is None or attempt.job_id!=child.job_id:
                raise ValueError("CONVERSATION_ORIGINAL_ATTEMPT_CHANGED")
            seal_event=owner._runtime.events.get_event_by_command_id("orchestration-result-seal:"+attempt.attempt_id)
            if seal_event is not None:
                from control_plane.executive_runtime import _sealed_role_result_payload
                from control_plane.executive_orchestration_result import validate_envelope
                with owner._runtime.store.read() as connection:
                    seal=_sealed_role_result_payload(connection,attempt_id=attempt.attempt_id,expected_role="plan")
                envelope=validate_envelope(seal["result_envelope"],expected_job_id=child.job_id,
                    expected_run_id=attempt.attempt_id,expected_worker_id=attempt.worker_id,
                    expected_role="plan",expected_root_job_id=root.job_id)
                if (seal["job_id"]!=child.job_id or seal["worker_id"]!=attempt.worker_id
                        or seal["effective_grant_digest"]!=attempt.effective_grant_digest
                        or len(json.dumps(envelope,ensure_ascii=False).encode())>16384):
                    raise ValueError("CONVERSATION_INITIAL_RESULT_CHANGED")
                initial=dict(digest=wire.canonical_digest(envelope),envelope=envelope)
            try:
                facts=owner._runtime.current_harness_binding_source(attempt.attempt_id)
                if facts.job_id!=child.job_id:raise ValueError()
                import dataclasses
                epoch=dict(attempt_id=facts.attempt_id,
                    generation_digest=wire.canonical_digest(dict(session_epoch_id=facts.session_epoch_id,
                        process_generation_id=facts.process_generation_id,generation=facts.generation_number)),
                    binding_digest=wire.canonical_digest(dataclasses.asdict(facts)))
                state="RETAINED"
            except Exception:
                if child.status.value=="COMPLETED":
                    completed=owner._runtime.validated_role_completion(child.job_id,expected_attempt_id=attempt.attempt_id)
                    if initial is None or wire.canonical_digest(completed.result_envelope)!=initial["digest"]:
                        raise ValueError("CONVERSATION_TERMINAL_RESULT_CHANGED")
                    state="SETTLED"
                else:
                    state="RECONCILIATION_REQUIRED"
    # Actual consumed-parent and recorded follow-up evidence, independent of
    # generic Wake targets. These rows never imply permission to send.
    from control_plane.fresh_conversation_turn import _command,_event,_CONSUME,_REQUEST,_recorded_reply
    scope=wire.canonical_digest(origin)
    consumed=_event(owner._runtime,_command("consume",scope,root.job_id),_CONSUME,root.job_id)
    consumption=None
    if consumed is not None:
        data=consumed.payload
        if (data["root_event_id"]!=reference["root_event_id"] or data["root_event_sha256"]!=reference["root_event_sha256"]
                or data["principal"]!=scope or data["work_ref"]!=reference["work_ref"] or initial is None
                or data["initial_digest"]!=initial["digest"] or data["locator"]!=locator):
            raise ValueError("CONVERSATION_CONSUMPTION_CHANGED")
        consumption=dict(state="CONSUMED",event_id=consumed.event_id,event_sha256=wire.canonical_digest(consumed.to_dict()),initial_digest=initial["digest"])
    with owner._runtime.store.read() as connection:
        requests=connection.execute("""SELECT command_id,event_id FROM events
            WHERE aggregate_type='fresh_conversation' AND aggregate_id=? AND event_type=?
              AND (? IS NULL OR event_id<?) ORDER BY event_id DESC LIMIT ?""",
            (root.job_id,_REQUEST,before,before,_LIMIT+1)).fetchall()
    page=dict(kind="initial" if before is None else "history",before_event_id=before,next_before_event_id=None)
    window=dict(schema="mastermind.fresh_conversation_window.v2",kind="fresh_native",reference=dict(reference),
        state=state,locator=locator,epoch=epoch,initial_message=objective["message"],
        initial_result=initial if before is None else None,
        initial_digest=initial["digest"] if initial is not None else None,
        initial_consumption=consumption,turns=[],page=page,can_send=False,parent_consumed=False)
    _bounded(window)
    turns=[]
    oldest=None
    for index,row in enumerate(requests[:_LIMIT]):
        requested=_event(owner._runtime,row["command_id"],_REQUEST,root.job_id)
        identity=requested.payload["identity"]
        if (requested.event_id!=row["event_id"] or identity["principal"]!=scope
                or identity["root_job_id"]!=root.job_id or identity["locator"]!=locator
                or identity["root_event_id"]!=reference["root_event_id"] or identity["work_ref"]!=reference["work_ref"]
                or identity["root_event_sha256"]!=reference["root_event_sha256"] or initial is None
                or identity["initial_digest"]!=initial["digest"] or consumption is None
                or consumption!=requested.payload["consumption"]
                or row["command_id"]!=_command("turn",scope,root.job_id,requested.payload["turn_key"])):
            raise ValueError("CONVERSATION_TURN_HISTORY_CHANGED")
        reply=_recorded_reply(owner,requested)
        turn=dict(turn_key=requested.payload["turn_key"],message=requested.payload["message"],
            state="RECORDED" if reply else "RECONCILIATION_REQUIRED",
            result=reply.payload["result"] if reply else None,parent_consumed=False)
        candidate={**window,"turns":list(reversed([*turns,turn])),
            "page":{**page,"next_before_event_id":row["event_id"] if index+1<len(requests) else None}}
        if _encoded_size(candidate)>28000:
            if not turns:
                if before is not None:
                    raise ValueError("CONVERSATION_REFERENCE_RESPONSE_OVER_BUDGET")
                # Keep the complete initial envelope. The first history page
                # starts at the latest request, with no skipped or cut reply.
                page["next_before_event_id"]=row["event_id"]+1
            else:
                page["next_before_event_id"]=oldest
            break
        turns.append(turn);oldest=row["event_id"]
        window["turns"]=candidate["turns"]
        page["next_before_event_id"]=candidate["page"]["next_before_event_id"]
    _original(owner,principal,reference)
    if epoch is not None:
        import dataclasses
        current=owner._runtime.current_harness_binding_source(epoch["attempt_id"])
        if wire.canonical_digest(dataclasses.asdict(current))!=epoch["binding_digest"]:
            raise ValueError("CONVERSATION_WRITER_CHANGED")
    return _bounded(window)


def _encoded_size(value):
    return len(json.dumps(value,ensure_ascii=False,separators=(",",":"),allow_nan=False).encode("utf-8"))


def _bounded(value):
    # Match actual compact UTF-8 framing, leaving space inside the incumbent
    # 32-KiB Executive response. Full result envelopes are never truncated.
    if _encoded_size(value)>28000:
        raise ValueError("CONVERSATION_REFERENCE_RESPONSE_OVER_BUDGET")
    return value


def resolve_action_reference(owner, principal, reference, *, for_write=True):
    """Recover correlation DATA privately; this never supplies an action grant."""
    owner._current(principal,read_only=not for_write)  # READ-only pairing never grants submit.
    root,material,origin=_original(owner,principal,reference)
    creation=owner._runtime.store.unique_root_created_event(root.job_id)
    original=creation.payload.get("fresh_conversation_original_request")
    key=None
    if original is not None:
        if (type(original) is not dict or set(original)!={"schema","operation_key","creation_digest"}
                or original["schema"]!="mastermind.fresh_conversation_original_request.v1"
                or original["creation_digest"]!=wire.canonical_digest(material)):
            raise ValueError("CONVERSATION_ORIGINAL_KEY_CHANGED")
        key=original["operation_key"]
    else:
        # Legacy161 receipts were truthful but did not retain this DATA. Only
        # genuine later consumption/turn originals may supply it; no backfill,
        # key inversion, generated replacement or new root is permitted.
        read_reference(owner,principal,reference)
        from control_plane.fresh_conversation_turn import _command,_event,_CONSUME
        consumed=_event(owner._runtime,_command("consume",wire.canonical_digest(origin),root.job_id),_CONSUME,root.job_id)
        if consumed is None:
            raise ValueError("CONVERSATION_ORIGINAL_KEY_UNAVAILABLE")
        identity=consumed.payload
        if (identity.get("principal")!=wire.canonical_digest(origin)
                or identity.get("root_job_id")!=root.job_id):
            raise ValueError("CONVERSATION_ORIGINAL_KEY_CHANGED")
        # Consumption precedes every follow-up and retains this original key.
        # More recorded turns do not create another key recovery authority.
        key=identity["operation_key"]
    wire.validate_request(dict(work_ref=reference["work_ref"],operation_key=key),operation="status")
    from control_plane.fresh_conversation import scoped_operation_key
    from control_plane import ceo_intent,ceo_request
    command=ceo_intent.command_id_for(ceo_request.automated_intent_id(ceo_request.app_request_ref(scoped_operation_key(principal,key))))
    if command!=material["command_id"]:
        raise ValueError("CONVERSATION_ORIGINAL_KEY_CHANGED")
    owner._current(principal,read_only=not for_write)
    return dict(work_ref=reference["work_ref"],operation_key=key)
