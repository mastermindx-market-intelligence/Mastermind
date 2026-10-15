"""Exact BeginTurn Event command binding for the content reader.

Use isolated memory SQLite to supply adversarial read shapes. The actual
Executive Event store forbids UPDATE/DELETE; these tests never tamper it.
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from control_plane.executive_content_observer import (
    ContentRefused, ExecutiveContentObserver,
)

OP = "ohf-op:turn:ATT"
JOB, ATT, EPOCH, GEN, WORKER = "JOB", "ATT", "EPOCH", "GEN", "worker-a"
TURN, PROVIDER_SESSION = "TURN", "PROVIDER-SESSION"


class _RuntimeStore:
    def __init__(self, connection):
        self.connection = connection

    @contextmanager
    def read(self):
        yield self.connection

    def now_ms(self):
        return 1000


def _fixture(*, intent_command=OP, applied_command=OP + ":applied"):
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    con.executescript("""
        CREATE TABLE attempts(
            job_id TEXT,attempt_id TEXT,worker_id TEXT,status TEXT,
            fence_generation INTEGER,lease_expires_at_ms INTEGER,
            execution_mode TEXT,quota_class TEXT
        );
        CREATE TABLE jobs(
            job_id TEXT,current_attempt_id TEXT,status TEXT
        );
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
    con.execute("INSERT INTO attempts VALUES(?,?,?,?,?,?,?,?)",
                (JOB, ATT, WORKER, "RUNNING", 1, 50000,
                 "OPERATOR_HARNESS", "default"))
    con.execute("INSERT INTO jobs VALUES(?,?,?)", (JOB, ATT, "RUNNING"))
    con.execute("INSERT INTO harness_session_epochs VALUES(?,?,?,?,?)",
                (ATT, EPOCH, "CURRENT", WORKER, PROVIDER_SESSION))
    con.execute("INSERT INTO process_generations VALUES(?,?,?,?,?,?,?)",
                (EPOCH, GEN, 1, WORKER, 1, "HELD", None))
    con.execute("INSERT INTO worker_quota_classes VALUES(?,?,?,?)",
                (WORKER, "default", ATT, 1))
    payloads = (
        (
            "OPERATOR_OPERATION_INTENT", intent_command,
            {
                "schema_version": "mastermind.operator_harness_turn_intent/v1",
                "operation_kind": "begin_turn",
                "attempt_id": ATT, "session_epoch_id": EPOCH,
                "process_generation_id": GEN, "turn_id": TURN,
                "worker_id": WORKER,
                "provider_session_id": PROVIDER_SESSION,
            }
        ),
        (
            "OPERATOR_OPERATION_APPLIED", applied_command,
            {
                "schema_version": "mastermind.operator_harness_turn_applied/v1",
                "operation_kind": "begin_turn",
                "attempt_id": ATT, "session_epoch_id": EPOCH,
                "process_generation_id": GEN, "turn_id": TURN,
                "provider_native_turn_id": "NATIVE-TURN",
                "acknowledged": True,
            }
        ),
    )
    for event_type, command, payload in payloads:
        con.execute(
            "INSERT INTO events VALUES(?,?,?,?,?,?,?,?,?,?)",
            (event_type, "operator_operation", OP, command, "supervisor",
             JOB, ATT, WORKER, "default",
             json.dumps(payload, sort_keys=True, separators=(",", ":"))),
        )
    profile = SimpleNamespace(
        job_id=JOB, attempt_id=ATT, session_epoch_id=EPOCH,
        process_generation_id=GEN, local_turn_id=TURN,
    )
    observer = ExecutiveContentObserver(
        runtime=SimpleNamespace(store=_RuntimeStore(con)),
        broker_client=None, profile_loader=None, now=lambda: 1000,
    )
    return con, observer, profile


def test_exact_intent_applied_command_pair_preserves_current_live_turn_key():
    con, observer, profile = _fixture()
    try:
        key, fence = observer._join(profile)
        assert fence == 1
        assert key["native_turn_id"] == "NATIVE-TURN"
        assert key["local_turn_id"] == TURN
    finally:
        con.close()


@pytest.mark.parametrize("bad", ["ohf-op:foreign:applied", OP, OP + ":refused"])
@pytest.mark.parametrize("live", [True, False])
def test_content_reader_refuses_mismatched_applied_command_id(bad, live):
    con, observer, profile = _fixture(applied_command=bad)
    try:
        with pytest.raises(ContentRefused, match="GRANT_INVALIDATED"):
            observer._join(profile, live=live)
    finally:
        con.close()


@pytest.mark.parametrize("bad", ["ohf-op:other", OP + ":applied"])
def test_content_reader_refuses_mismatched_intent_command_id(bad):
    con, observer, profile = _fixture(intent_command=bad)
    try:
        with pytest.raises(ContentRefused, match="GRANT_INVALIDATED"):
            observer._join(profile)
    finally:
        con.close()
