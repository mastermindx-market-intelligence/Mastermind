"""Interactive G1/G2 same-turn recovery against adversarial Event read shapes.

No mutation of the protected production Event ledger. In-memory SQL rows model
rejected receipt combinations and exact Runtime writer output.
"""
from __future__ import annotations

import json
import sqlite3

import pytest

from control_plane.executive_runtime import (
    StateConflict, _interactive_in_flight_turn_id,
)
from control_plane.operator_harness_contract import (
    OperationId, OperationReceiptKind, operation_receipt_command_id,
)

JOB, ATT, GEN, EPOCH, WORKER, SESSION, QUOTA, TURN = (
    "JOB", "ATT", "GEN", "EPOCH", "worker", "provider-session", "default", "turn-1",
)
OP = "ohf-op:turn:ATT:g1"


def _seed():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.executescript("""
        CREATE TABLE process_generations(process_generation_id TEXT,session_epoch_id TEXT);
        CREATE TABLE harness_session_epochs(
          session_epoch_id TEXT,attempt_id TEXT,worker_id TEXT,provider_session_id TEXT);
        CREATE TABLE attempts(attempt_id TEXT,job_id TEXT,quota_class TEXT);
        CREATE TABLE events(
          event_type TEXT,aggregate_type TEXT,aggregate_id TEXT,command_id TEXT,
          actor TEXT,job_id TEXT,attempt_id TEXT,worker_id TEXT,
          quota_class TEXT,payload_json TEXT);
    """)
    db.execute("INSERT INTO process_generations VALUES(?,?)", (GEN,EPOCH))
    db.execute("INSERT INTO harness_session_epochs VALUES(?,?,?,?)",
               (EPOCH,ATT,WORKER,SESSION))
    db.execute("INSERT INTO attempts VALUES(?,?,?)", (ATT,JOB,QUOTA))
    return db


def _intent():
    return dict(schema_version="mastermind.operator_harness_turn_intent/v1",
                operation_kind="begin_turn", attempt_id=ATT,
                session_epoch_id=EPOCH, process_generation_id=GEN,
                worker_id=WORKER,provider_session_id=SESSION,turn_id=TURN)


def _applied():
    return dict(schema_version="mastermind.operator_harness_turn_applied/v1",
                operation_kind="begin_turn",attempt_id=ATT,
                session_epoch_id=EPOCH,process_generation_id=GEN,
                turn_id=TURN,provider_native_turn_id="native-1",acknowledged=True)


def _candidate():
    return {
        "schema_version": "mastermind.operator_harness_candidate_evidence/v1",
        "turn": {
            "turn_id": TURN, "session_epoch_id": EPOCH,
            "process_generation_id": GEN, "attempt_id": ATT,
        },
        "candidate": {
            "attempt_id": ATT, "session_epoch_id": EPOCH,
            "process_generation_id": GEN, "artifact_digest": None,
            "summary": "ok", "complete_job_permitted": False,
        },
        "events": [],
        "cursor": {
            "attempt_id": ATT, "session_epoch_id": EPOCH,
            "process_generation_id": GEN, "local_sequence": 1,
            "turn_id": TURN, "provider_replay_cursor": None,
        },
    }


def _write(db,kind,payload,*,op=OP,command=None):
    oid=OperationId(op)
    suffix = {
      "OPERATOR_OPERATION_INTENT": OperationReceiptKind.INTENT,
      "OPERATOR_OPERATION_APPLIED": OperationReceiptKind.APPLIED,
      "OPERATOR_OPERATION_EFFECT_UNKNOWN": OperationReceiptKind.EFFECT_UNKNOWN,
    }[kind]
    db.execute(
      "INSERT INTO events VALUES(?,?,?,?,?,?,?,?,?,?)",
      (kind,"operator_operation",op,
       command if command is not None else operation_receipt_command_id(oid,suffix),
       "supervisor",JOB,ATT,WORKER,QUOTA,
       json.dumps(payload,sort_keys=True,separators=(",",":"))))


def _read(db):
    return _interactive_in_flight_turn_id(db,GEN)


def test_original_intent_only_stays_in_flight():
    db=_seed()
    try:
        _write(db,"OPERATOR_OPERATION_INTENT",_intent())
        assert _read(db)==TURN
    finally:
        db.close()


def test_exact_acknowledged_begin_turn_stays_in_flight():
    db=_seed()
    try:
        _write(db,"OPERATOR_OPERATION_INTENT",_intent())
        _write(db,"OPERATOR_OPERATION_APPLIED",_applied())
        assert _read(db)==TURN
    finally:
        db.close()


@pytest.mark.parametrize("state", [
    "OPERATOR_OPERATION_APPLIED","OPERATOR_OPERATION_INTENT"
])
def test_bad_unpaired_or_unauthenticated_receipt_refuses_instead_of_guess(state):
    db=_seed()
    try:
        if state=="OPERATOR_OPERATION_APPLIED":
            _write(db,state,_applied())
        else:
            _write(db,state,_intent(),command="ohf-op:foreign")
        with pytest.raises(StateConflict,match="receipt|identity|provenance"):
            _read(db)
    finally:
        db.close()


@pytest.mark.parametrize("bad", [
    "ohf-op:foreign:applied",OP,OP+":refused"
])
def test_applied_cannot_have_unsupported_receipt_command(bad):
    db=_seed()
    try:
        _write(db,"OPERATOR_OPERATION_INTENT",_intent())
        _write(db,"OPERATOR_OPERATION_APPLIED",_applied(),command=bad)
        with pytest.raises(StateConflict,match="receipt|identity|provenance"):
            _read(db)
    finally:
        db.close()


@pytest.mark.parametrize("field,bad", [
    ("process_generation_id","foreign"),("worker_id","foreign"),
    ("provider_session_id","foreign"),("attempt_id","foreign")
])
def test_intent_binding_drift_refuses_to_guess_turn_state(field,bad):
    db=_seed()
    try:
        intent=_intent();intent[field]=bad
        _write(db,"OPERATOR_OPERATION_INTENT",intent)
        with pytest.raises(StateConflict,match="receipt|identity|provenance"):
            _read(db)
    finally:db.close()


def test_effect_unknown_from_original_intent_preserves_in_flight():
    db=_seed()
    try:
        _write(db,"OPERATOR_OPERATION_INTENT",_intent())
        _write(db,"OPERATOR_OPERATION_EFFECT_UNKNOWN",{
            "schema_version":"mastermind.operator_harness_effect_unknown/v1",
            "phase":"begin_turn","detail":"unknown"})
        assert _read(db)==TURN
    finally:db.close()


def test_conflicting_applied_and_unknown_cannot_count_as_settled():
    db=_seed()
    try:
        _write(db,"OPERATOR_OPERATION_INTENT",_intent())
        _write(db,"OPERATOR_OPERATION_APPLIED",_applied())
        _write(db,"OPERATOR_OPERATION_EFFECT_UNKNOWN",{
            "schema_version":"mastermind.operator_harness_effect_unknown/v1",
            "phase":"begin_turn","detail":"contradiction"})
        with pytest.raises(StateConflict,match="receipt|identity|provenance"):
            _read(db)
    finally:db.close()


def test_completed_acknowledged_turn_with_real_candidate_is_not_in_flight():
    db=_seed()
    try:
        _write(db,"OPERATOR_OPERATION_INTENT",_intent())
        _write(db,"OPERATOR_OPERATION_APPLIED",_applied())
        db.execute(
           "INSERT INTO events VALUES(?,?,?,?,?,?,?,?,?,?)",
           ("OHF_CANDIDATE_RESULT_RECORDED","operator_turn",TURN,
            f"ohf-candidate:{TURN}","supervisor",JOB,ATT,WORKER,QUOTA,
            json.dumps(_candidate(),sort_keys=True,separators=(",",":"))))
        assert _read(db) is None
    finally:db.close()


def _interrupt_applied(db, *, op="ohf-op:interrupt:ATT",
                       command=None, complete_intent=False):
    intent = {
        "schema_version":"mastermind.operator_harness_turn_operation/v1",
        "operation_kind":"interrupt_turn","attempt_id":ATT,
        "session_epoch_id":EPOCH,"process_generation_id":GEN,
        "worker_id":WORKER,"turn_id":TURN,
    }
    if complete_intent:
        _write(db,"OPERATOR_OPERATION_INTENT",intent,op=op)
    applied = {
        "schema_version":"mastermind.operator_harness_turn_operation_applied/v1",
        "operation_kind":"interrupt_turn","turn_id":TURN,
    }
    _write(db,"OPERATOR_OPERATION_APPLIED",applied,op=op,command=command)


@pytest.mark.parametrize("with_intent,command", [
    (False,None), (True,"ohf-op:unrelated:applied"),
    (True,"ohf-op:interrupt:ATT"),
])
def test_unpaired_interrupt_applied_does_not_clear_inflight_turn(
        with_intent, command):
    db=_seed()
    try:
        _write(db,"OPERATOR_OPERATION_INTENT",_intent())
        _write(db,"OPERATOR_OPERATION_APPLIED",_applied())
        _interrupt_applied(db,complete_intent=with_intent,command=command)
        with pytest.raises(StateConflict,match="receipt|identity|provenance"):
            _read(db)
    finally:db.close()


def test_original_paired_interrupt_release_is_not_inflight():
    db=_seed()
    try:
        _write(db,"OPERATOR_OPERATION_INTENT",_intent())
        _write(db,"OPERATOR_OPERATION_APPLIED",_applied())
        _interrupt_applied(db,complete_intent=True)
        assert _read(db) is None
    finally:db.close()
