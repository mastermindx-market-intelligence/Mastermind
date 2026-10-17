"""Adversarial identity joins for content reads and interactive turn settlement.

The tests use isolated in-memory SQLite and never mutate the production Event
ledger. They discriminate foreign outer identity, open payload shapes,
ambiguous candidate evidence and interrupt EFFECT_UNKNOWN.
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from control_plane.executive_content_observer import (
    ContentRefused,
    ExecutiveContentObserver,
)
from control_plane.executive_runtime import (
    StateConflict,
    _interactive_in_flight_turn_id,
)
from control_plane.operator_harness_contract import (
    OperationId,
    OperationReceiptKind,
    operation_receipt_command_id,
)


JOB, ATT, EPOCH, GEN, WORKER, QUOTA = (
    "JOB", "ATT", "EPOCH", "GEN", "worker-a", "default",
)
TURN, PROVIDER_SESSION = "TURN", "PROVIDER-SESSION"
BEGIN_OP = "ohf-op:turn:ATT"
INTERRUPT_OP = "ohf-op:interrupt:ATT"


class _RuntimeStore:
    def __init__(self, connection):
        self.connection = connection

    @contextmanager
    def read(self):
        yield self.connection

    def now_ms(self):
        return 1000


def _intent():
    return {
        "schema_version": "mastermind.operator_harness_turn_intent/v1",
        "operation_kind": "begin_turn",
        "attempt_id": ATT,
        "session_epoch_id": EPOCH,
        "process_generation_id": GEN,
        "worker_id": WORKER,
        "provider_session_id": PROVIDER_SESSION,
        "turn_id": TURN,
    }


def _applied():
    return {
        "schema_version": "mastermind.operator_harness_turn_applied/v1",
        "operation_kind": "begin_turn",
        "attempt_id": ATT,
        "session_epoch_id": EPOCH,
        "process_generation_id": GEN,
        "turn_id": TURN,
        "provider_native_turn_id": "NATIVE-TURN",
        "acknowledged": True,
    }


def _content_fixture():
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    con.executescript("""
        CREATE TABLE attempts(
            job_id TEXT,attempt_id TEXT,worker_id TEXT,status TEXT,
            fence_generation INTEGER,lease_expires_at_ms INTEGER,
            execution_mode TEXT,quota_class TEXT
        );
        CREATE TABLE jobs(job_id TEXT,current_attempt_id TEXT,status TEXT);
        CREATE TABLE harness_session_epochs(
            attempt_id TEXT,session_epoch_id TEXT,state TEXT,worker_id TEXT,
            provider_session_id TEXT
        );
        CREATE TABLE process_generations(
            session_epoch_id TEXT,process_generation_id TEXT,generation_number INTEGER,
            worker_id TEXT,executive_writer_held INTEGER,
            provider_writer_state TEXT,ended_at_ms INTEGER
        );
        CREATE TABLE worker_quota_classes(
            worker_id TEXT,quota_class TEXT,held_attempt_id TEXT,
            fence_counter INTEGER
        );
        CREATE TABLE events(
            event_type TEXT,aggregate_type TEXT,aggregate_id TEXT,command_id TEXT,
            actor TEXT,job_id TEXT,attempt_id TEXT,worker_id TEXT,
            quota_class TEXT,payload_json TEXT
        );
    """)
    con.execute(
        "INSERT INTO attempts VALUES(?,?,?,?,?,?,?,?)",
        (JOB, ATT, WORKER, "RUNNING", 1, 50000, "OPERATOR_HARNESS", QUOTA),
    )
    con.execute("INSERT INTO jobs VALUES(?,?,?)", (JOB, ATT, "RUNNING"))
    con.execute(
        "INSERT INTO harness_session_epochs VALUES(?,?,?,?,?)",
        (ATT, EPOCH, "CURRENT", WORKER, PROVIDER_SESSION),
    )
    con.execute(
        "INSERT INTO process_generations VALUES(?,?,?,?,?,?,?)",
        (EPOCH, GEN, 1, WORKER, 1, "HELD", None),
    )
    con.execute(
        "INSERT INTO worker_quota_classes VALUES(?,?,?,?)",
        (WORKER, QUOTA, ATT, 1),
    )
    for event_type, payload, receipt_kind in (
        ("OPERATOR_OPERATION_INTENT", _intent(), OperationReceiptKind.INTENT),
        ("OPERATOR_OPERATION_APPLIED", _applied(), OperationReceiptKind.APPLIED),
    ):
        con.execute(
            "INSERT INTO events VALUES(?,?,?,?,?,?,?,?,?,?)",
            (
                event_type,
                "operator_operation",
                BEGIN_OP,
                operation_receipt_command_id(OperationId(BEGIN_OP), receipt_kind),
                "supervisor",
                JOB,
                ATT,
                WORKER,
                QUOTA,
                json.dumps(payload, sort_keys=True, separators=(",", ":")),
            ),
        )
    profile = SimpleNamespace(
        job_id=JOB,
        attempt_id=ATT,
        session_epoch_id=EPOCH,
        process_generation_id=GEN,
        local_turn_id=TURN,
    )
    observer = ExecutiveContentObserver(
        runtime=SimpleNamespace(store=_RuntimeStore(con)),
        broker_client=None,
        profile_loader=None,
        now=lambda: 1000,
    )
    return con, observer, profile


def test_content_exact_closed_receipts_join():
    con, observer, profile = _content_fixture()
    try:
        key, fence = observer._join(profile)
        assert fence == 1
        assert key["native_turn_id"] == "NATIVE-TURN"
    finally:
        con.close()


@pytest.mark.parametrize("column", ["job_id", "worker_id", "quota_class"])
@pytest.mark.parametrize(
    "event_type", ["OPERATOR_OPERATION_INTENT", "OPERATOR_OPERATION_APPLIED"]
)
def test_content_outer_source_identity_substitution_refuses(column, event_type):
    con, observer, profile = _content_fixture()
    try:
        con.execute(
            f"UPDATE events SET {column}='foreign' WHERE event_type=?",
            (event_type,),
        )
        with pytest.raises(ContentRefused, match="GRANT_INVALIDATED"):
            observer._join(profile)
    finally:
        con.close()


@pytest.mark.parametrize(
    "event_type,damage",
    [
        ("OPERATOR_OPERATION_INTENT", "extra"),
        ("OPERATOR_OPERATION_INTENT", "schema"),
        ("OPERATOR_OPERATION_APPLIED", "extra"),
        ("OPERATOR_OPERATION_APPLIED", "schema"),
    ],
)
def test_content_receipt_payload_shape_is_closed(event_type, damage):
    con, observer, profile = _content_fixture()
    try:
        row = con.execute(
            "SELECT payload_json FROM events WHERE event_type=?", (event_type,)
        ).fetchone()
        payload = json.loads(row["payload_json"])
        if damage == "extra":
            payload["unexpected"] = True
        else:
            payload["schema_version"] = "foreign"
        con.execute(
            "UPDATE events SET payload_json=? WHERE event_type=?",
            (json.dumps(payload, sort_keys=True, separators=(",", ":")), event_type),
        )
        with pytest.raises(ContentRefused, match="GRANT_INVALIDATED"):
            observer._join(profile)
    finally:
        con.close()


def _runtime_seed():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.executescript("""
        CREATE TABLE process_generations(
            process_generation_id TEXT,session_epoch_id TEXT
        );
        CREATE TABLE harness_session_epochs(
            session_epoch_id TEXT,attempt_id TEXT,worker_id TEXT,
            provider_session_id TEXT
        );
        CREATE TABLE attempts(attempt_id TEXT,job_id TEXT,quota_class TEXT);
        CREATE TABLE events(
            event_type TEXT,aggregate_type TEXT,aggregate_id TEXT,command_id TEXT,
            actor TEXT,job_id TEXT,attempt_id TEXT,worker_id TEXT,
            quota_class TEXT,payload_json TEXT
        );
    """)
    db.execute("INSERT INTO process_generations VALUES(?,?)", (GEN, EPOCH))
    db.execute(
        "INSERT INTO harness_session_epochs VALUES(?,?,?,?)",
        (EPOCH, ATT, WORKER, PROVIDER_SESSION),
    )
    db.execute("INSERT INTO attempts VALUES(?,?,?)", (ATT, JOB, QUOTA))
    return db


def _write_operation(db, kind, payload, *, op=BEGIN_OP, command=None):
    receipt = {
        "OPERATOR_OPERATION_INTENT": OperationReceiptKind.INTENT,
        "OPERATOR_OPERATION_APPLIED": OperationReceiptKind.APPLIED,
        "OPERATOR_OPERATION_EFFECT_UNKNOWN": OperationReceiptKind.EFFECT_UNKNOWN,
    }[kind]
    db.execute(
        "INSERT INTO events VALUES(?,?,?,?,?,?,?,?,?,?)",
        (
            kind,
            "operator_operation",
            op,
            command
            if command is not None
            else operation_receipt_command_id(OperationId(op), receipt),
            "supervisor",
            JOB,
            ATT,
            WORKER,
            QUOTA,
            json.dumps(payload, sort_keys=True, separators=(",", ":")),
        ),
    )


def _begin_applied(db):
    _write_operation(db, "OPERATOR_OPERATION_INTENT", _intent())
    _write_operation(db, "OPERATOR_OPERATION_APPLIED", _applied())


def _candidate_payload():
    return {
        "schema_version": "mastermind.operator_harness_candidate_evidence/v1",
        "turn": {
            "turn_id": TURN,
            "session_epoch_id": EPOCH,
            "process_generation_id": GEN,
            "attempt_id": ATT,
        },
        "candidate": {
            "attempt_id": ATT,
            "session_epoch_id": EPOCH,
            "process_generation_id": GEN,
            "artifact_digest": None,
            "summary": "ok",
            "complete_job_permitted": False,
        },
        "events": [],
        "cursor": {
            "attempt_id": ATT,
            "session_epoch_id": EPOCH,
            "process_generation_id": GEN,
            "local_sequence": 1,
            "turn_id": TURN,
            "provider_replay_cursor": None,
        },
    }


def _write_candidate(db, payload=None, **outer):
    values = {
        "aggregate_type": "operator_turn",
        "aggregate_id": TURN,
        "command_id": f"ohf-candidate:{TURN}",
        "actor": "supervisor",
        "job_id": JOB,
        "attempt_id": ATT,
        "worker_id": WORKER,
        "quota_class": QUOTA,
    }
    values.update(outer)
    db.execute(
        "INSERT INTO events VALUES(?,?,?,?,?,?,?,?,?,?)",
        (
            "OHF_CANDIDATE_RESULT_RECORDED",
            values["aggregate_type"],
            values["aggregate_id"],
            values["command_id"],
            values["actor"],
            values["job_id"],
            values["attempt_id"],
            values["worker_id"],
            values["quota_class"],
            json.dumps(
                _candidate_payload() if payload is None else payload,
                sort_keys=True,
                separators=(",", ":"),
            ),
        ),
    )


def test_exact_candidate_closes_only_its_bound_turn():
    db = _runtime_seed()
    try:
        _begin_applied(db)
        _write_candidate(db)
        assert _interactive_in_flight_turn_id(db, GEN) is None
    finally:
        db.close()


@pytest.mark.parametrize(
    "field",
    [
        "aggregate_type",
        "aggregate_id",
        "command_id",
        "actor",
        "job_id",
        "worker_id",
        "quota_class",
    ],
)
def test_foreign_candidate_outer_identity_cannot_release_turn(field):
    db = _runtime_seed()
    try:
        _begin_applied(db)
        _write_candidate(db, **{field: "foreign"})
        with pytest.raises(StateConflict, match="candidate|identity|provenance"):
            _interactive_in_flight_turn_id(db, GEN)
    finally:
        db.close()


def test_duplicate_candidate_identity_is_ambiguous():
    db = _runtime_seed()
    try:
        _begin_applied(db)
        _write_candidate(db)
        _write_candidate(db)
        with pytest.raises(StateConflict, match="candidate|ambiguous"):
            _interactive_in_flight_turn_id(db, GEN)
    finally:
        db.close()


@pytest.mark.parametrize(
    "path",
    ["turn.session_epoch_id", "candidate.attempt_id", "cursor.process_generation_id"],
)
def test_candidate_nested_identity_substitution_cannot_release_turn(path):
    db = _runtime_seed()
    try:
        _begin_applied(db)
        payload = _candidate_payload()
        parent, child = path.split(".")
        payload[parent][child] = "foreign"
        _write_candidate(db, payload)
        with pytest.raises(StateConflict, match="candidate|identity|provenance"):
            _interactive_in_flight_turn_id(db, GEN)
    finally:
        db.close()


def _interrupt_payloads():
    return (
        {
            "schema_version": "mastermind.operator_harness_turn_operation/v1",
            "operation_kind": "interrupt_turn",
            "attempt_id": ATT,
            "session_epoch_id": EPOCH,
            "process_generation_id": GEN,
            "worker_id": WORKER,
            "turn_id": TURN,
        },
        {
            "schema_version": "mastermind.operator_harness_turn_operation_applied/v1",
            "operation_kind": "interrupt_turn",
            "turn_id": TURN,
        },
    )


def _write_interrupt_pair(db):
    intent, applied = _interrupt_payloads()
    _write_operation(
        db, "OPERATOR_OPERATION_INTENT", intent, op=INTERRUPT_OP
    )
    _write_operation(
        db, "OPERATOR_OPERATION_APPLIED", applied, op=INTERRUPT_OP
    )


def test_exact_interrupt_pair_releases_turn():
    db = _runtime_seed()
    try:
        _begin_applied(db)
        _write_interrupt_pair(db)
        assert _interactive_in_flight_turn_id(db, GEN) is None
    finally:
        db.close()


def test_duplicate_interrupt_intent_is_ambiguous():
    db = _runtime_seed()
    try:
        _begin_applied(db)
        intent, applied = _interrupt_payloads()
        _write_operation(
            db, "OPERATOR_OPERATION_INTENT", intent, op=INTERRUPT_OP
        )
        _write_operation(
            db, "OPERATOR_OPERATION_INTENT", intent, op=INTERRUPT_OP
        )
        _write_operation(
            db, "OPERATOR_OPERATION_APPLIED", applied, op=INTERRUPT_OP
        )
        with pytest.raises(StateConflict, match="interrupt|ambiguous"):
            _interactive_in_flight_turn_id(db, GEN)
    finally:
        db.close()


def test_interrupt_applied_plus_same_operation_unknown_never_releases_turn():
    db = _runtime_seed()
    try:
        _begin_applied(db)
        _write_interrupt_pair(db)
        _write_operation(
            db,
            "OPERATOR_OPERATION_EFFECT_UNKNOWN",
            {
                "schema_version": "mastermind.operator_harness_effect_unknown/v1",
                "phase": "interrupt_turn",
                "detail": "lost response",
            },
            op=INTERRUPT_OP,
        )
        with pytest.raises(StateConflict, match="interrupt|unknown"):
            _interactive_in_flight_turn_id(db, GEN)
    finally:
        db.close()
