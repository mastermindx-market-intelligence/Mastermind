"""Quota rollover proofs: synthetic transport evidence, real SQLite transactions.

These are NOT provider/host acceptance receipts. No provider is launched.
"""
from __future__ import annotations

import importlib.util
import json
import sqlite3

import pytest


def _module():
    name = "control_plane.executive_quota_rollover"
    assert importlib.util.find_spec(name) is not None, "quota rollover proof producer is missing"
    return __import__(name, fromlist=["quota_rollover_material"])


def _dump(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


@pytest.fixture
def source():
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    con.executescript("""
    CREATE TABLE jobs(job_id TEXT, current_attempt_id TEXT, status TEXT,
      checkpoint_json TEXT, result_json TEXT);
    CREATE TABLE attempts(attempt_id TEXT, job_id TEXT, worker_id TEXT,
      quota_class TEXT, status TEXT, execution_mode TEXT, lease_token TEXT,
      fence_generation INTEGER, checkpoint_sequence INTEGER, checkpoint_json TEXT,
      effective_grant_json TEXT, result_json TEXT, finished_at_ms INTEGER);
    CREATE TABLE worker_quota_classes(worker_id TEXT, quota_class TEXT,
      status TEXT, held_attempt_id TEXT, fence_counter INTEGER);
    CREATE TABLE harness_session_epochs(session_epoch_id TEXT, attempt_id TEXT,
      worker_id TEXT, provider_session_id TEXT, state TEXT);
    CREATE TABLE process_generations(process_generation_id TEXT, session_epoch_id TEXT,
      worker_id TEXT, provider_session_id TEXT, started_at_ms INTEGER,
      ended_at_ms INTEGER, executive_writer_held INTEGER, provider_writer_state TEXT);
    CREATE TABLE events(event_id INTEGER PRIMARY KEY, aggregate_type TEXT,
      aggregate_id TEXT, event_type TEXT, actor TEXT, job_id TEXT,
      attempt_id TEXT, worker_id TEXT, quota_class TEXT, payload_json TEXT,
      created_at_ms INTEGER);
    """)
    checkpoint = _dump({"summary": "inspected source", "completed_steps": ["census"],
                        "next_actions": ["verify candidate"], "artifacts": ["github:commit:abc"]})
    con.execute("INSERT INTO jobs VALUES('job','attempt','RATE_LIMITED',?,NULL)", (checkpoint,))
    con.execute("INSERT INTO attempts VALUES('attempt','job','worker','pool','RATE_LIMITED',"
                "'OPERATOR_HARNESS',NULL,4,1,?,?,NULL,300)",
                (checkpoint, _dump({"authorities": ["READ"], "write_paths": []})))
    con.execute("INSERT INTO worker_quota_classes VALUES('worker','pool','RATE_LIMITED','attempt',4)")
    con.execute("INSERT INTO harness_session_epochs VALUES('epoch','attempt','worker','native','ABANDONED')")
    con.execute("INSERT INTO process_generations VALUES('generation','epoch','worker','native',100,200,0,'RELEASED')")
    con.execute("INSERT INTO events VALUES(1,'process_generation','generation','OHF_GRACEFUL_STOP',"
                "'supervisor','job','attempt','worker','pool',?,200)",
                (_dump({"writer_released": True}),))
    con.execute("INSERT INTO events VALUES(2,'job','job','JOB_RATE_LIMITED','worker',"
                "'job','attempt','worker','pool',?,300)", (_dump({"checkpoint_sequence": 1}),))
    yield con
    con.close()


def material(con):
    return _module().quota_rollover_material(
        con, job=dict(con.execute("SELECT * FROM jobs").fetchone()),
        attempt=dict(con.execute("SELECT * FROM attempts").fetchone()))


def test_positive_release_returns_content_bound_material(source):
    value = material(source)
    assert value is not None
    assert value["schema_version"] == "mastermind.quota_rollover_proof/v1"
    assert value["attempt_id"] == "attempt"
    assert len(value["evidence_digest"]) == 64
    assert value["checkpoint_sequence"] == 1
    assert value["generation_ids"] == ["generation"]


@pytest.mark.parametrize("sql", [
    "UPDATE jobs SET current_attempt_id='other'",
    "UPDATE jobs SET status='FAILED'",
    "UPDATE attempts SET status='RUNNING'",
    "UPDATE attempts SET execution_mode='SEALED_WORKER'",
    "UPDATE attempts SET lease_token='still-live'",
    "UPDATE attempts SET checkpoint_sequence=0",
    "UPDATE attempts SET checkpoint_json=NULL",
    "UPDATE jobs SET checkpoint_json='{}'",
    "UPDATE jobs SET result_json='{}'",
    "UPDATE attempts SET result_json='{}'",
    "UPDATE worker_quota_classes SET status='AVAILABLE'",
    "UPDATE worker_quota_classes SET held_attempt_id='other'",
    "UPDATE worker_quota_classes SET fence_counter=5",
    "UPDATE harness_session_epochs SET state='CURRENT'",
    "UPDATE harness_session_epochs SET worker_id='foreign'",
    "UPDATE process_generations SET ended_at_ms=NULL",
    "UPDATE process_generations SET provider_writer_state='UNKNOWN'",
    "UPDATE process_generations SET executive_writer_held=1",
    "UPDATE process_generations SET provider_session_id='foreign'",
    "UPDATE process_generations SET worker_id='foreign'",
    "DELETE FROM process_generations",
    "DELETE FROM harness_session_epochs",
    "DELETE FROM events WHERE event_type='OHF_GRACEFUL_STOP'",
    "DELETE FROM events WHERE event_type='JOB_RATE_LIMITED'",
    "UPDATE events SET actor='worker' WHERE event_id=1",
    "UPDATE events SET aggregate_id='foreign' WHERE event_id=1",
    "UPDATE events SET attempt_id='foreign' WHERE event_id=2",
    "UPDATE events SET worker_id='foreign' WHERE event_id=2",
    "UPDATE events SET quota_class='foreign' WHERE event_id=2",
    "UPDATE events SET created_at_ms=301 WHERE event_id=1",
    "UPDATE events SET created_at_ms=299 WHERE event_id=2",
    "UPDATE events SET payload_json='{\"writer_released\":false}' WHERE event_id=1",
    "UPDATE events SET payload_json='{\"checkpoint_sequence\":2}' WHERE event_id=2",
])
def test_missing_contradictory_or_live_evidence_never_proves_rollover(source, sql):
    source.execute(sql)
    assert material(source) is None


@pytest.mark.parametrize("grant", [
    {"authorities": ["WRITE"], "write_paths": ["repo"]},
    {"authorities": ["READ", "WRITE"], "write_paths": []},
    {"authorities": [], "write_paths": []},
    {"authorities": ["READ"], "write_paths": ["repo"]},
    {"authorities": ["READ"]},
    {"authorities": "READ", "write_paths": []},
])
def test_modifying_or_unknown_grants_are_not_quota_retry_authority(source, grant):
    source.execute("UPDATE attempts SET effective_grant_json=?", (_dump(grant),))
    assert material(source) is None


@pytest.mark.parametrize("event_type", [
    "OPERATOR_OPERATION_EFFECT_UNKNOWN", "OHF_CANDIDATE_RESULT_RECORDED",
    "ORCHESTRATION_ROLE_RESULT_SEALED",
])
def test_unresolved_effect_and_accepted_work_are_not_replayed(source, event_type):
    source.execute("INSERT INTO events VALUES(3,'job','job',?,'supervisor','job',"
                   "'attempt','worker','pool','{}',250)", (event_type,))
    assert material(source) is None


def test_duplicate_rate_limit_evidence_is_ambiguous(source):
    source.execute("INSERT INTO events SELECT 3,aggregate_type,aggregate_id,event_type,actor,"
                   "job_id,attempt_id,worker_id,quota_class,payload_json,created_at_ms "
                   "FROM events WHERE event_id=2")
    assert material(source) is None


def test_every_generation_must_be_proven_released(source):
    source.execute("INSERT INTO process_generations VALUES('second','epoch','worker','native',110,210,0,'RELEASED')")
    assert material(source) is None
    source.execute("INSERT INTO events VALUES(3,'process_generation','second','OHF_GRACEFUL_STOP',"
                   "'supervisor','job','attempt','worker','pool','{\"writer_released\":true}',210)")
    assert material(source)["generation_ids"] == ["generation", "second"]


def test_checkpoint_change_changes_proof_digest(source):
    before = material(source)["evidence_digest"]
    checkpoint = _dump({"summary": "later state", "next_actions": ["review"]})
    source.execute("UPDATE jobs SET checkpoint_json=?", (checkpoint,))
    source.execute("UPDATE attempts SET checkpoint_json=?", (checkpoint,))
    assert material(source)["evidence_digest"] != before


@pytest.mark.parametrize("bad", [
    '{"writer_released":false,"writer_released":true}',
    '{"writer_released":true,"extra":NaN}',
    '{"writer_released":1}',
])
def test_malformed_or_coerced_producer_json_is_refused(source, bad):
    source.execute("UPDATE events SET payload_json=? WHERE event_id=1", (bad,))
    assert material(source) is None


@pytest.mark.parametrize("actions", ["continue", [None], [""], [4], []])
def test_a_frontier_requires_concrete_typed_next_actions(source, actions):
    checkpoint = _dump({"summary": "state", "next_actions": actions})
    source.execute("UPDATE jobs SET checkpoint_json=?", (checkpoint,))
    source.execute("UPDATE attempts SET checkpoint_json=?", (checkpoint,))
    assert material(source) is None


def test_malformed_historical_proof_identity_is_refused_without_database_error(source):
    assert _module().validate_saved_quota_proof(source, {
        "schema_version": "mastermind.quota_rollover_proof/v1", "attempt_id": []}) is False


def test_boolean_checkpoint_sequence_is_not_integer_provenance(source):
    source.execute("UPDATE events SET payload_json='{\"checkpoint_sequence\":true}' WHERE event_id=2")
    assert material(source) is None


# Independent review regressions: current authorization and historical receipts differ.
def test_existing_operator_quota_owner_is_a_valid_typed_stop_producer(source):
    source.execute("UPDATE events SET actor='operator' WHERE event_id=2")
    assert material(source) is not None


@pytest.mark.parametrize("actor", ["provider", "model", "unknown", "supervisor"])
def test_unrecognized_quota_stop_actors_do_not_gain_retry_authority(source, actor):
    source.execute("UPDATE events SET actor=? WHERE event_id=2", (actor,))
    assert material(source) is None


def test_saved_receipt_does_not_reread_mutable_generation_state(source):
    proof = material(source)
    source.execute("UPDATE process_generations SET provider_writer_state='UNKNOWN',executive_writer_held=1")
    assert material(source) is None  # Fresh retry is still blocked.
    assert _module().validate_saved_quota_proof(source, proof) is True  # Historical read only.


def test_late_unknown_effect_does_not_erase_a_previously_committed_receipt(source):
    proof = material(source)
    source.execute("INSERT INTO events VALUES(3,'job','job','OPERATOR_OPERATION_EFFECT_UNKNOWN',"
                   "'supervisor','job','attempt','worker','pool','{}',400)")
    assert material(source) is None
    assert _module().validate_saved_quota_proof(source, proof) is True


def test_additive_event_column_does_not_invalidate_historical_proof(source):
    proof = material(source)
    source.execute("ALTER TABLE events ADD COLUMN harmless_projection TEXT")
    source.execute("UPDATE events SET harmless_projection='new schema metadata'")
    assert material(source) == proof
    assert _module().validate_saved_quota_proof(source, proof) is True


def test_saved_receipt_still_rejects_referenced_event_corruption(source):
    proof = material(source)
    source.execute("UPDATE events SET actor='foreign' WHERE event_id=1")
    assert _module().validate_saved_quota_proof(source, proof) is False


@pytest.mark.parametrize("field", ["event_digest", "epoch_state", "provider_writer_state", "executive_writer_held"])
def test_closed_frozen_release_snapshot_cannot_be_tampered(source, field):
    proof = material(source)
    proof["releases"][0][field] = "tampered"
    assert _module().validate_saved_quota_proof(source, proof) is False


def test_proof_json_uses_the_same_canonical_wire_as_runtime(source):
    source.execute("UPDATE events SET payload_json='{\"writer_released\": true}' WHERE event_id=1")
    assert material(source) is None


def test_canonical_unicode_checkpoint_roundtrips_without_ascii_reencoding(source):
    checkpoint = json.dumps({"next_actions": ["Review café evidence"]}, sort_keys=True,
                            separators=(",", ":"), ensure_ascii=False)
    source.execute("UPDATE jobs SET checkpoint_json=?", (checkpoint,))
    source.execute("UPDATE attempts SET checkpoint_json=?", (checkpoint,))
    proof = material(source)
    assert proof is not None
    assert _module().validate_saved_quota_proof(source, proof) is True
