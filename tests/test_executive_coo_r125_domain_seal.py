"""Actual public later-turn provenance; typed transport is hermetic source proof."""
import dataclasses
import hashlib
import json

import pytest

from control_plane.executive_orchestration_result import (
    DOMAIN_CONSUMPTION_SCHEMA, RawRoleResultObservation, canonical_bytes,
)
from control_plane.executive_runtime import AttemptStatus, StateConflict
from tests.test_executive_coo_r124_domain_turn import (
    CONSUMPTION_NATIVE_TURN_PREFIX, TypedHermeticConsumptionAdapter,
    _append_negative_event, _fresh_orchestrator_for_domain_attempt,
    _real_consumption_context,
)
from tests.test_executive_coo_r119_later_turn import _inventory


class ObservedConsumptionAdapter(TypedHermeticConsumptionAdapter):
    """Raw body only for the exact actually dispatched/collected hermetic turn."""

    def __init__(self, provider_session_id, body):
        super().__init__()
        self.provider_session_id = provider_session_id
        self.body = body
        self.raw_calls = []

    def observe_raw_role_result(self, turn):
        assert self.begin_turn_calls[-1]["turn"] == turn
        assert self.collect_candidate_calls[-1] == turn
        self.raw_calls.append(turn)
        raw = canonical_bytes(self.body)
        return RawRoleResultObservation(
            attempt_id=turn.attempt_id, session_epoch_id=turn.session_epoch_id,
            process_generation_id=turn.process_generation_id, turn_id=turn.turn_id,
            provider_session_id=self.provider_session_id,
            provider_native_turn_id=f"{CONSUMPTION_NATIVE_TURN_PREFIX}-{turn.turn_id}",
            provider_turn_artifact_digest="a" * 64,
            canonical_result_json=raw.decode(), canonical_result_digest=hashlib.sha256(raw).hexdigest(),
            canonical_result_byte_length=len(raw),
        )


def _context(tmp_path, monkeypatch, result="工作與獨立審查已消化 · reviewed result"):
    rt, root, domain, attempt, session, _, _, _, op, digest = _real_consumption_context(tmp_path, monkeypatch)
    with rt.store.read() as c:
        provider = c.execute("SELECT provider_session_id FROM process_generations WHERE process_generation_id=?",
                             (session.generation.process_generation_id,)).fetchone()[0]
    body = dict(schema_version=DOMAIN_CONSUMPTION_SCHEMA, root_job_id=root.job_id,
                domain_job_id=domain.job_id, domain_attempt_id=attempt,
                consumption_projection_digest=digest, consumed_result=result)
    adapter = ObservedConsumptionAdapter(provider, body)
    orchestrator, lease = _fresh_orchestrator_for_domain_attempt(rt, attempt, adapter)
    receipt = orchestrator.run_domain_consumption_turn(
        session, operation_id=op, expected_consumption_projection_digest=digest,
    )
    raw = adapter.observe_raw_role_result(receipt.turn)
    command = f"coo-cycle:{root.job_id}:domain-consumption-seal:{attempt}:{receipt.turn.turn_id}"
    args = dict(domain_attempt_id=attempt, observation=raw, command_id=command,
                turn=receipt.turn, fence_generation=lease.attempt.fence_generation,
                lease_token=lease.lease_token)
    return rt, root, domain, adapter, receipt, args


def _seal(ctx, **changes):
    rt, root, _, _, _, args = ctx
    return rt.jobs.seal_cycle_domain_consumption(root.job_id, **(args | changes))


def _unchecked(raw, **changes):
    clone = object.__new__(RawRoleResultObservation)
    for field in dataclasses.fields(RawRoleResultObservation):
        object.__setattr__(clone, field.name, changes.get(field.name, getattr(raw, field.name)))
    return clone


def test_actual_later_native_body_seals_once_and_replays_without_durable_delta(tmp_path, monkeypatch):
    ctx = _context(tmp_path, monkeypatch)
    rt, root, domain, adapter, receipt, args = ctx
    attempt = args["domain_attempt_id"]
    initial = rt.events.get_event_by_command_id(f"orchestration-result-seal:{attempt}")
    before = _inventory(rt)
    result = _seal(ctx)
    after = _inventory(rt)
    assert result["consumption_result"] == adapter.body
    assert result["consumed_result_byte_length"] == len(adapter.body["consumed_result"].encode())
    assert result["provider_native_turn_id"] != initial.payload["provider_native_turn_id"]
    assert result["current_projection_digest"] == adapter.body["consumption_projection_digest"]
    assert result["selected_revisions"][0]["qualifying_review_job_id"]
    assert result["selected_revision_result_identities"][0]["qualifying_review_attempt_id"]
    assert result["initial_plan_attempt_id"] == attempt
    assert args["lease_token"] not in json.dumps(result)
    assert result["seal_receipt_digest"] == hashlib.sha256(canonical_bytes({
        key: value for key, value in result.items()
        if key not in {"seal_receipt_digest", "seal_receipt_byte_length"}
    })).hexdigest()
    assert len(after["events"]) == len(before["events"]) + 1
    for table in before:
        if table != "events": assert after[table] == before[table], table
    event = rt.events.get_event_by_command_id(args["command_id"])
    assert (event.aggregate_type, event.aggregate_id, event.job_id, event.attempt_id, event.actor) == (
        "job", root.job_id, root.job_id, attempt, "coo")
    assert event.payload == result
    assert rt.attempts.get_attempt(attempt).status is AttemptStatus.CHECKPOINTED
    assert rt.jobs.get_job(domain.job_id).current_attempt_id == attempt
    assert rt.events.get_event_by_command_id(initial.command_id) == initial
    assert _seal(ctx) == result
    assert _inventory(rt) == after
    assert len(adapter.begin_turn_calls) == len(adapter.raw_calls) == 1


@pytest.mark.parametrize("field,value", [
    ("attempt_id", "foreign-attempt"), ("turn_id", "foreign-turn"),
    ("session_epoch_id", "foreign-epoch"), ("process_generation_id", "foreign-generation"),
    ("provider_session_id", "foreign-session"), ("provider_native_turn_id", "foreign-native"),
    ("provider_turn_artifact_digest", "b"*64), ("canonical_result_digest", "b"*64),
    ("schema_version", "wrong-schema"), ("canonical_result_byte_length", True),
    ("canonical_result_byte_length", -1), ("canonical_result_byte_length", 8*1024*1024+1),
    ("canonical_result_json", "{}\n"),
])
def test_altered_frozen_raw_refuses_without_effects(tmp_path, monkeypatch, field, value):
    ctx = _context(tmp_path, monkeypatch); before = _inventory(ctx[0])
    with pytest.raises(StateConflict):
        _seal(ctx, observation=_unchecked(ctx[-1]["observation"], **{field:value}))
    assert _inventory(ctx[0]) == before


def test_float_length_that_constructor_accepts_is_refused_on_runtime_ingress(tmp_path, monkeypatch):
    ctx = _context(tmp_path, monkeypatch); raw=ctx[-1]["observation"]
    altered=_unchecked(raw,canonical_result_byte_length=float(raw.canonical_result_byte_length))
    before=_inventory(ctx[0])
    with pytest.raises(StateConflict): _seal(ctx,observation=altered)
    assert _inventory(ctx[0])==before


@pytest.mark.parametrize("field,value", [
    ("schema_version", "wrong-schema"), ("root_job_id", "wrong-root"),
    ("domain_job_id", "wrong-domain"), ("domain_attempt_id", "wrong-attempt"),
    ("consumption_projection_digest", "b"*64), ("consumed_result", ""),
    ("extra", "closed-wire-refusal"),
])
def test_canonical_typed_body_still_requires_runtime_derived_closed_identity(tmp_path, monkeypatch, field, value):
    ctx=_context(tmp_path,monkeypatch);adapter=ctx[3];adapter.body[field]=value
    raw=adapter.observe_raw_role_result(ctx[4].turn);before=_inventory(ctx[0])
    with pytest.raises(StateConflict): _seal(ctx,observation=raw)
    assert _inventory(ctx[0])==before


@pytest.mark.parametrize("changes", [
    {"turn":None}, {"fence_generation":None}, {"lease_token":None},
    {"lease_token":"foreign-authority"}, {"fence_generation":True},
    {"fence_generation":-1}, {"domain_attempt_id":"foreign-attempt"},
    {"command_id":"foreign-command"}, {"observation":{"consumed_result":"caller text"}},
])
def test_missing_or_foreign_authority_refuses_without_effects(tmp_path, monkeypatch, changes):
    ctx=_context(tmp_path,monkeypatch);before=_inventory(ctx[0])
    with pytest.raises(StateConflict): _seal(ctx,**changes)
    assert _inventory(ctx[0])==before


@pytest.mark.parametrize("event_name", ["final","intent","dispatch","applied","candidate","initial_plan"])
def test_appended_alias_or_orphan_evidence_refuses_without_effects(tmp_path, monkeypatch, event_name):
    ctx=_context(tmp_path,monkeypatch);rt,root,_,_,receipt,args=ctx
    with rt.store.read() as c:
        op=c.execute("SELECT operation_id,event_id FROM coo_provider_charges WHERE root_job_id=? AND effect_class='FINAL'",(root.job_id,)).fetchone()
        final_command=c.execute("SELECT command_id FROM events WHERE event_id=?",(op["event_id"],)).fetchone()[0]
    command=dict(final=final_command,intent=op["operation_id"],dispatch=op["operation_id"]+":dispatch",
                 applied=op["operation_id"]+":applied",candidate="ohf-candidate:"+receipt.turn.turn_id,
                 initial_plan="orchestration-result-seal:"+args["domain_attempt_id"])[event_name]
    event=rt.events.get_event_by_command_id(command)
    if event_name == "initial_plan":
        # The existing unique plan-seal invariant rejects this corruption at
        # append. Preserve it; do not bypass the index to manufacture a case.
        before = _inventory(rt)
        with pytest.raises(StateConflict):
            _append_negative_event(rt,event,command="adversarial-alias:"+command)
        assert _inventory(rt) == before
        return
    _append_negative_event(rt,event,command="adversarial-alias:"+command)
    before=_inventory(rt)
    with pytest.raises(StateConflict): _seal(ctx)
    assert _inventory(rt)==before


def test_unknown_after_applied_and_initial_turn_observation_cannot_seal(tmp_path, monkeypatch):
    ctx=_context(tmp_path,monkeypatch);rt,_,_,_,receipt,args=ctx
    with rt.store.read() as c:
        op=c.execute("SELECT operation_id FROM coo_provider_charges WHERE attempt_id=? AND effect_class='FINAL'",(args["domain_attempt_id"],)).fetchone()[0]
    event=rt.events.get_event_by_command_id(op)
    _append_negative_event(rt,event,command=op+":unknown-adversary",event_type="OPERATOR_OPERATION_EFFECT_UNKNOWN",
                           payload={"schema_version":"mastermind.operator_harness_effect_unknown/v1","phase":"fixture","detail":"ambiguous"})
    before=_inventory(rt)
    with pytest.raises(StateConflict): _seal(ctx)
    assert _inventory(rt)==before


def test_replay_rejects_second_alias_receipt_and_changed_body(tmp_path, monkeypatch):
    ctx=_context(tmp_path,monkeypatch);rt=ctx[0];_seal(ctx)
    ctx[3].body["consumed_result"]="different later return"
    changed=ctx[3].observe_raw_role_result(ctx[4].turn);before=_inventory(rt)
    with pytest.raises(StateConflict): _seal(ctx,observation=changed)
    assert _inventory(rt)==before
    event=rt.events.get_event_by_command_id(ctx[-1]["command_id"])
    _append_negative_event(rt,event,command="adversarial-alias-domain-seal")
    before=_inventory(rt)
    with pytest.raises(StateConflict): _seal(ctx)
    assert _inventory(rt)==before


def test_full_multibyte_body_near_byte_ceiling_is_preserved(tmp_path, monkeypatch):
    text="海"*((8*1024*1024-1200)//3)
    ctx=_context(tmp_path,monkeypatch,result=text)
    result=_seal(ctx)
    assert result["consumption_result"]["consumed_result"]==text
    assert result["consumed_result_byte_length"]==len(text.encode())
    assert len(canonical_bytes(result))<=8*1024*1024+64*1024


def test_sensitive_body_refuses_instead_of_redacting_observed_result(tmp_path, monkeypatch):
    ctx=_context(tmp_path,monkeypatch,result="sk-"+"x"*40);before=_inventory(ctx[0])
    with pytest.raises(StateConflict): _seal(ctx)
    assert _inventory(ctx[0])==before


@pytest.mark.parametrize("committed", [False, True])
def test_reserved_final_without_real_native_ack_cannot_seal(tmp_path, monkeypatch, committed):
    rt,root,domain,attempt,session,_,o,lease,op,digest=_real_consumption_context(tmp_path,monkeypatch)
    turn=o.runtime.begin_operator_domain_consumption_turn(
        attempt,session.generation,op,expected_consumption_projection_digest=digest)
    if committed:
        o.runtime.commit_operator_provider_dispatch(attempt,op,"begin_turn")
    with rt.store.read() as c:
        provider=c.execute("SELECT provider_session_id FROM process_generations WHERE process_generation_id=?",
                           (turn.process_generation_id,)).fetchone()[0]
    body=canonical_bytes(dict(schema_version=DOMAIN_CONSUMPTION_SCHEMA,root_job_id=root.job_id,
                              domain_job_id=domain.job_id,domain_attempt_id=attempt,
                              consumption_projection_digest=digest,consumed_result="unobserved caller return"))
    # Deliberate negative: a valid typed object cannot replace native receipts.
    raw=RawRoleResultObservation(attempt,turn.session_epoch_id,turn.process_generation_id,turn.turn_id,
        provider,"unobserved-later-native","a"*64,body.decode(),hashlib.sha256(body).hexdigest(),len(body))
    before=_inventory(rt)
    with pytest.raises(StateConflict):
        rt.jobs.seal_cycle_domain_consumption(root.job_id,domain_attempt_id=attempt,turn=turn,
            observation=raw,fence_generation=lease.attempt.fence_generation,lease_token=lease.lease_token,
            command_id=f"coo-cycle:{root.job_id}:domain-consumption-seal:{attempt}:{turn.turn_id}")
    assert _inventory(rt)==before


_AFFILIATION_LINKS = [
    "operation_id", "session_epoch_id", "process_generation_id",
    "candidate_event_command_id", "applied_event_command_id",
    "dispatch_event_command_id", "intent_event_command_id",
    "initial_plan_event_command_id", "initial_plan_attempt_id",
    "final_charge_id", "reservation_identity", "final_event_id",
    "current_projection_digest", "consumed_body_digest", "native_pair",
    "nested_root", "nested_domain", "nested_attempt", "nested_projection",
    "header_domain_job", "header_domain_aggregate",
]


@pytest.mark.parametrize("phase", ["fresh", "replay"])
@pytest.mark.parametrize("link", _AFFILIATION_LINKS)
def test_headerless_contradictory_seal_aliases_refuse_before_append_or_replay(
    tmp_path, monkeypatch, phase, link,
):
    ctx = _context(tmp_path, monkeypatch)
    rt, root, domain, adapter, receipt, args = ctx
    with rt.store.read() as connection:
        final = connection.execute(
            "SELECT * FROM coo_provider_charges WHERE root_job_id=? AND effect_class='FINAL'",
            (root.job_id,),
        ).fetchone()
    op = final["operation_id"]
    actual = dict(
        operation_id=op, session_epoch_id=receipt.turn.session_epoch_id,
        process_generation_id=receipt.turn.process_generation_id,
        candidate_event_command_id="ohf-candidate:" + receipt.turn.turn_id,
        applied_event_command_id=op+":applied", dispatch_event_command_id=op+":dispatch",
        intent_event_command_id=op,
        initial_plan_event_command_id="orchestration-result-seal:"+args["domain_attempt_id"],
        initial_plan_attempt_id=args["domain_attempt_id"],
        final_charge_id=final["charge_id"], reservation_identity=final["reservation_identity"],
        final_event_id=final["event_id"],
        current_projection_digest=adapter.body["consumption_projection_digest"],
        consumed_body_digest=hashlib.sha256(canonical_bytes(adapter.body)).hexdigest(),
    )
    if phase == "replay": _seal(ctx)
    # Deliberately contradictory orphan: only the selected independent link
    # identifies this real operation. Do not preserve canonical source headers.
    payload = dict(root_job_id="foreign-root", domain_job_id="foreign-domain",
                   domain_attempt_id="foreign-attempt", turn_id="foreign-turn",
                   command_id="foreign-command", consumption_result={})
    if link in actual:
        payload[link] = actual[link]
    elif link == "native_pair":
        payload.update(provider_session_id=args["observation"].provider_session_id,
                       provider_native_turn_id=args["observation"].provider_native_turn_id)
    elif link.startswith("nested_"):
        key = dict(nested_root="root_job_id", nested_domain="domain_job_id",
                   nested_attempt="domain_attempt_id", nested_projection="consumption_projection_digest")[link]
        payload["consumption_result"] = {key: adapter.body[key]}
    with rt.store.transaction() as connection:
        rt.store.append_event(
            connection, aggregate_type="job",
            aggregate_id=domain.job_id if link=="header_domain_aggregate" else "unrelated-aggregate",
            event_type="COO_DOMAIN_CONSUMPTION_SEALED", actor="negative-fixture",
            job_id=domain.job_id if link=="header_domain_job" else None,
            attempt_id=None, worker_id=None, quota_class=None,
            command_id="adversarial-domain-seal:"+phase+":"+link, payload=payload,
        )
    before = _inventory(rt)
    with pytest.raises(StateConflict, match="seal.*(alias|unique|foreign)"): _seal(ctx)
    assert _inventory(rt) == before
    assert len(adapter.begin_turn_calls) == 1


def test_foreign_seal_shared_artifact_and_worker_do_not_affiliate(tmp_path, monkeypatch):
    ctx=_context(tmp_path,monkeypatch);rt,root,domain,adapter,receipt,args=ctx
    with rt.store.transaction() as connection:
        rt.store.append_event(
            connection, aggregate_type="job", aggregate_id="foreign-root",
            event_type="COO_DOMAIN_CONSUMPTION_SEALED", actor="negative-fixture",
            job_id=None, attempt_id=None, worker_id=None, quota_class=None,
            command_id="unrelated-domain-seal",
            payload=dict(root_job_id="foreign-root", domain_job_id="foreign-domain",
                         domain_attempt_id="foreign-attempt", command_id="foreign-command",
                         provider_session_id="foreign-session",
                         provider_native_turn_id=args["observation"].provider_native_turn_id,
                         provider_turn_artifact_digest=args["observation"].provider_turn_artifact_digest),
        )
    result=_seal(ctx);after=_inventory(rt)
    assert result["consumption_result"]==adapter.body
    assert _seal(ctx)==result and _inventory(rt)==after



def _capture_unappended_expected_seal(ctx, monkeypatch):
    """Negative setup: actual validation reaches append; raise and roll back.

    No positive receipt is manufactured. The exact expected material then
    feeds a deliberately malformed Event through the normal append API.
    """
    import copy
    captured=[];rt=ctx[0];before=_inventory(rt);original=rt.store.append_event
    class CaptureBeforeAppend(Exception): pass
    def intercept(connection, **kwargs):
        if kwargs.get("event_type")=="COO_DOMAIN_CONSUMPTION_SEALED":
            captured.append(copy.deepcopy(kwargs));raise CaptureBeforeAppend
        return original(connection,**kwargs)
    with monkeypatch.context() as patch:
        patch.setattr(rt.store,"append_event",intercept)
        with pytest.raises(CaptureBeforeAppend): _seal(ctx)
    assert _inventory(rt)==before and len(captured)==1
    return captured[0]


_PROVENANCE_DIGEST_LINKS = [
    "candidate_event_digest", "applied_event_digest", "intent_event_digest",
    "initial_plan_event_digest", "final_event_digest", "raw_observation_digest",
    "initial_plan_digest", "seal_receipt_digest",
]
_AGGREGATE_OWNER_LINKS = [
    "operation_id", "turn_id", "domain_attempt_id", "session_epoch_id",
    "process_generation_id", "candidate_event_command_id",
    "final_charge_id", "reservation_identity", "final_event_id",
]


@pytest.mark.parametrize("phase", ["fresh", "replay"])
@pytest.mark.parametrize("link", _PROVENANCE_DIGEST_LINKS + ["aggregate:"+key for key in _AGGREGATE_OWNER_LINKS])
def test_aggregate_and_full_provenance_digest_aliases_refuse_without_effects(
    tmp_path, monkeypatch, phase, link,
):
    ctx=_context(tmp_path,monkeypatch);rt=ctx[0]
    expected=_capture_unappended_expected_seal(ctx,monkeypatch)["payload"]
    if phase=="replay": _seal(ctx)
    payload=dict(root_job_id="foreign-root",domain_job_id="foreign-domain",
                 domain_attempt_id="foreign-attempt",turn_id="foreign-turn",
                 command_id="foreign-command",consumption_result={})
    aggregate="foreign-aggregate"
    if link.startswith("aggregate:"): aggregate=str(expected[link.split(":",1)[1]])
    else: payload[link]=expected[link]
    with rt.store.transaction() as connection:
        rt.store.append_event(connection,aggregate_type="foreign-type",aggregate_id=aggregate,
            event_type="COO_DOMAIN_CONSUMPTION_SEALED",actor="negative-fixture",
            job_id=None,attempt_id=None,worker_id=None,quota_class=None,
            command_id="adversarial-provenance-seal:"+phase+":"+link,payload=payload)
    before=_inventory(rt)
    with pytest.raises(StateConflict,match="seal.*(alias|unique|foreign)"): _seal(ctx)
    assert _inventory(rt)==before


@pytest.mark.parametrize("field,kind", [
    ("fence_generation","bool"), ("fence_generation","float"),
    ("final_event_id","float"), ("consumed_result_byte_length","float"),
    ("consumed_body_byte_length","float"), ("raw_observation_byte_length","float"),
    ("seal_receipt_byte_length","float"),
    ("seal_receipt_digest","bad_digest"), ("seal_receipt_byte_length","bad_length"),
])
def test_canonical_command_replay_refuses_numeric_and_self_identity_drift(
    tmp_path,monkeypatch,field,kind,
):
    ctx=_context(tmp_path,monkeypatch);rt=ctx[0]
    kwargs=_capture_unappended_expected_seal(ctx,monkeypatch)
    payload=kwargs["payload"]
    if kind=="bool":
        assert payload[field]==1;payload[field]=True
    elif kind=="float": payload[field]=float(payload[field])
    elif kind=="bad_digest": payload[field]="b"*64
    else: payload[field]+=1
    with rt.store.transaction() as connection: rt.store.append_event(connection,**kwargs)
    before=_inventory(rt)
    with pytest.raises(StateConflict,match="replay.*(types|digest|length|payload)"): _seal(ctx)
    assert _inventory(rt)==before


def test_shared_dispatch_digest_text_worker_and_quota_do_not_affiliate(tmp_path,monkeypatch):
    ctx=_context(tmp_path,monkeypatch);rt=ctx[0]
    expected=_capture_unappended_expected_seal(ctx,monkeypatch)["payload"]
    with rt.store.transaction() as connection:
        rt.store.append_event(connection,aggregate_type="job",aggregate_id="foreign-root",
            event_type="COO_DOMAIN_CONSUMPTION_SEALED",actor="negative-fixture",
            job_id=None,attempt_id=None,worker_id=None,quota_class=None,command_id="unrelated-shared-dispatch",
            payload=dict(root_job_id="foreign-root",domain_job_id="foreign-domain",
                         domain_attempt_id="foreign-attempt",command_id="foreign-command",
                         dispatch_event_digest=expected["dispatch_event_digest"],
                         domain_worker_id=expected["domain_worker_id"],domain_quota_class=expected["domain_quota_class"],
                         consumed_result_digest=expected["consumed_result_digest"],
                         provider_turn_artifact_digest=expected["provider_turn_artifact_digest"]))
    result=_seal(ctx);after=_inventory(rt)
    assert result["consumption_result"]==ctx[3].body
    assert _seal(ctx)==result and _inventory(rt)==after
