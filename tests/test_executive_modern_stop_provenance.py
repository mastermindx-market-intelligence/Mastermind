"""Minimal read-only projection tests for modern-stop provenance.

The production Executive Event store is immutable. These SQLite tables live
only in memory and test adversarial read shapes without rewriting real receipts.
They never authorize a retry or synthesize a production OHF release event.
"""
from __future__ import annotations

import json
import sqlite3

import pytest

from control_plane.executive_runtime import OHF_INTERNAL_GENERATION_OPERATION_SCHEMA_VERSION
from control_plane.executive_session_recovery import _modern_stop_without_legacy_quota_proof

JOB, ATT, WORKER, CLASS = "job", "att", "worker", "quota"
OP, GEN, EPOCH, SESSION = "ohf-op:stop-1", "gen-1", "epoch-1", "session-1"


def _fixture():
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    con.executescript("""
    CREATE TABLE events(
        event_id INTEGER PRIMARY KEY, event_type TEXT, aggregate_type TEXT,
        aggregate_id TEXT, command_id TEXT, actor TEXT,
        job_id TEXT, attempt_id TEXT, worker_id TEXT, quota_class TEXT,
        payload_json TEXT);
    CREATE TABLE process_generations(
        process_generation_id TEXT,session_epoch_id TEXT,worker_id TEXT,
        ended_at_ms INTEGER,executive_writer_held INTEGER,
        provider_writer_state TEXT);
    CREATE TABLE harness_session_epochs(
        session_epoch_id TEXT,attempt_id TEXT,worker_id TEXT,provider_session_id TEXT);
    """)
    con.execute("INSERT INTO harness_session_epochs VALUES(?,?,?,?)",
                (EPOCH, ATT, WORKER, SESSION))
    con.execute("INSERT INTO process_generations VALUES(?,?,?,?,?,?)",
                (GEN, EPOCH, WORKER, 1234, 0, "RELEASED"))
    return con


def _append(con, event_type, op, payload, *, applied=False):
    con.execute(
        "INSERT INTO events(event_type,aggregate_type,aggregate_id,command_id,actor,"
        "job_id,attempt_id,worker_id,quota_class,payload_json) "
        "VALUES (?,?,?,?,?,?,?,?,?,?)",
        (event_type, "operator_operation", op, op + (":applied" if applied else ""),
         "supervisor", JOB, ATT, WORKER, CLASS,
         json.dumps(payload, sort_keys=True, separators=(",", ":"))))


def _intent(*, generation=GEN):
    return {
        "schema_version": OHF_INTERNAL_GENERATION_OPERATION_SCHEMA_VERSION,
        "operation_kind": "graceful_stop", "attempt_id": ATT,
        "session_epoch_id": EPOCH, "process_generation_id": generation,
        "worker_id": WORKER, "provider_session_id": SESSION,
    }


def _applied(*, generation=GEN):
    return {
        "schema_version": OHF_INTERNAL_GENERATION_OPERATION_SCHEMA_VERSION,
        "operation_kind": "graceful_stop",
        "process_generation_id": generation,
        "process_liveness": "PROVEN_DEAD",
        "provider_writer_state": "RELEASED",
        "executive_writer_released": True,
    }


def _read(con):
    return _modern_stop_without_legacy_quota_proof(
        con, job_id=JOB, attempt_id=ATT, worker_id=WORKER, quota_class=CLASS,
    )


def test_applied_without_matching_intent_does_not_claim_authentic_stop():
    con = _fixture()
    try:
        _append(con, "OPERATOR_OPERATION_APPLIED", OP, _applied(), applied=True)
        assert _read(con) is False
    finally:
        con.close()


@pytest.mark.parametrize("drift", [
    {"process_generation_id": "other-generation"},
    {"provider_session_id": "different-session"},
    {"worker_id": "different-worker"},
    {"attempt_id": "different-attempt"},
    {"operation_kind": "cancel"},
])
def test_intent_drift_does_not_claim_proven_modern_stop(drift):
    con = _fixture()
    try:
        _append(con, "OPERATOR_OPERATION_INTENT", OP, {**_intent(), **drift})
        _append(con, "OPERATOR_OPERATION_APPLIED", OP, _applied(), applied=True)
        assert _read(con) is False
    finally:
        con.close()


def test_exact_incumbent_intent_and_applied_pair_is_a_diagnostic_only():
    con = _fixture()
    try:
        _append(con, "OPERATOR_OPERATION_INTENT", OP, _intent())
        _append(con, "OPERATOR_OPERATION_APPLIED", OP, _applied(), applied=True)
        assert _read(con) is True
    finally:
        con.close()


def test_legacy_stop_for_same_generation_removes_missing_proof_label():
    con = _fixture()
    try:
        _append(con, "OPERATOR_OPERATION_INTENT", OP, _intent())
        _append(con, "OPERATOR_OPERATION_APPLIED", OP, _applied(), applied=True)
        con.execute(
            "INSERT INTO events(event_type,aggregate_type,aggregate_id,command_id,"
            "actor,job_id,attempt_id,worker_id,quota_class,payload_json) "
            "VALUES(?,?,?,?,?,?,?,?,?,?)",
            ("OHF_GRACEFUL_STOP", "process_generation", GEN, "release-old",
             "supervisor", JOB, ATT, WORKER, CLASS, "{}"))
        assert _read(con) is False
    finally:
        con.close()


@pytest.mark.parametrize("bad_applied_command", [
    "ohf-op:other:applied",
    "ohf-op:stop-1:effect-unknown",
    "ohf-op:stop-1",
])
def test_applied_receipt_command_identity_must_match_exact_original_op(
        bad_applied_command):
    con = _fixture()
    try:
        _append(con, "OPERATOR_OPERATION_INTENT", OP, _intent())
        _append(con, "OPERATOR_OPERATION_APPLIED", OP, _applied(), applied=True)
        # Read-only evidence fixture intentionally uses an unconstrained SQLite
        # table. Production Event rows are immutable and not altered here.
        con.execute(
            "UPDATE events SET command_id=? "
            "WHERE event_type='OPERATOR_OPERATION_APPLIED'",
            (bad_applied_command,),
        )
        assert _read(con) is False
    finally:
        con.close()


def test_applied_receipt_must_match_same_original_attempt_and_worker():
    con = _fixture()
    try:
        _append(con, "OPERATOR_OPERATION_INTENT", OP, _intent())
        _append(con, "OPERATOR_OPERATION_APPLIED", OP, _applied(), applied=True)
        con.execute("UPDATE events SET attempt_id='other' WHERE "
                    "event_type='OPERATOR_OPERATION_INTENT'")
        assert _read(con) is False
    finally:
        con.close()
