from __future__ import annotations

import json
import sqlite3

import pytest

from control_plane.ceo_intent import INTENT_SCHEMA_V2, submit_intent
from control_plane.executive_coo_policy import CooCyclePolicy
from control_plane.executive_runtime import (
    Runtime,
    StateConflict,
    _COO_CYCLE_DOMAIN_BUDGET_CAPABILITY,
    orchestration_digest,
)


BUDGET_EVENT = "COO_PROVIDER_WORK_BUDGET_RESERVED"


def _v2_intent(**overrides):
    value = {
        "schema": INTENT_SCHEMA_V2,
        "intent_id": "CEO-R9B-PROVIDER-BUDGET",
        "actor": "ceo-sol",
        "objective": "Reserve the initial COO domain provider budget.",
        "department": "executive-infrastructure",
        "priority": 9,
        "grounding": {"mastermind_sha": "a" * 40, "macro_sha": "b" * 40},
        "execution_contract": {
            "requested_authorities": ["READ"],
            "attempt_limit": 2,
        },
        "intent_kind": "executive_coo_cycle",
        "business_impact": "material",
    }
    value.update(overrides)
    return value


def _root_and_domain(tmp_path, *, intent_id="CEO-R9B-PROVIDER-BUDGET"):
    runtime = Runtime.at(tmp_path)
    receipt = submit_intent(runtime, _v2_intent(intent_id=intent_id))
    root = runtime.jobs.get_job(receipt["job_id"])
    assert root is not None
    domain = runtime.jobs.create_cycle_domain(
        root.job_id,
        command_id=f"coo-cycle:{root.job_id}:create-domain:0",
    )
    with runtime.store.read() as connection:
        budget_count = int(
            connection.execute(
                "SELECT COUNT(*) FROM events WHERE event_type=?", (BUDGET_EVENT,)
            ).fetchone()[0]
        )
    assert budget_count == 1
    return runtime, root, domain


def _budget_row(runtime, root_job_id, domain_job_id):
    with runtime.store.read() as connection:
        return connection.execute(
            """
            SELECT e.*,r.job_id AS root_join,j.job_id AS domain_join
            FROM events e
            JOIN jobs r ON r.job_id=e.job_id AND r.orchestration_role='aggregation'
            JOIN jobs j ON j.job_id=e.payload_json->>'$.domain_job_id'
            WHERE e.event_type=? AND r.job_id=? AND j.job_id=?
            """,
            (BUDGET_EVENT, root_job_id, domain_job_id),
        ).fetchone()


def _with_events_immutable(runtime, action):
    connection = sqlite3.connect(str(runtime.store.path))
    try:
        connection.executescript("DROP TRIGGER events_are_immutable_update;")
        action(connection)
        connection.executescript(
            """
            CREATE TRIGGER events_are_immutable_update
            BEFORE UPDATE ON events BEGIN
              SELECT RAISE(ABORT, 'events are immutable');
            END;
            """
        )
        connection.commit()
    finally:
        connection.close()


def _event_count(runtime):
    with runtime.store.read() as connection:
        return int(connection.execute("SELECT COUNT(*) FROM events").fetchone()[0])


def _corrupt_budget_payload(runtime, payload_json):
    def mutate(connection):
        connection.execute(
            "UPDATE events SET payload_json=? WHERE event_type=?",
            (payload_json, BUDGET_EVENT),
        )
    _with_events_immutable(runtime, mutate)


def _root_without_domain(tmp_path, *, intent_id):
    runtime = Runtime.at(tmp_path)
    receipt = submit_intent(runtime, _v2_intent(intent_id=intent_id))
    root = runtime.jobs.get_job(receipt["job_id"])
    assert root is not None
    return runtime, root


def _reservation_event(runtime):
    with runtime.store.read() as connection:
        return connection.execute(
            "SELECT * FROM events WHERE event_type=?", (BUDGET_EVENT,)
        ).fetchone()


def _valid_fresh_root_envelope(runtime, root, domain_job_id):
    policy = CooCyclePolicy.load()
    body = {
        "available_provider_work_units": 31,
        "domain_job_id": domain_job_id,
        "max_provider_work_units_per_root": 32,
        "policy_schema_version": 2,
        "policy_sha256": policy.policy_sha256,
        "reserved_domain_consumption_units": 1,
        "reservation_status": "reservation_only",
        "root_job_id": root.job_id,
        "schema_version": (
            "mastermind.executive_coo_provider_work_budget_reservation/v1"
        ),
        "spent_provider_work_units": 0,
    }
    body["reservation_digest"] = orchestration_digest(body)
    command_id = f"coo-cycle:{root.job_id}:reserve-provider-budget:0"
    connection = sqlite3.connect(str(runtime.store.path))
    try:
        sequence = int(
            connection.execute(
                "SELECT COALESCE(MAX(sequence),0)+1 FROM events "
                "WHERE aggregate_type='job' AND aggregate_id=?",
                (root.job_id,),
            ).fetchone()[0]
        )
        connection.execute(
            "INSERT INTO events(aggregate_type,aggregate_id,sequence,event_type,"
            "command_id,actor,job_id,payload_json,created_at_ms) "
            "VALUES('job',?,?,?,?,?,?,?,?)",
            (
                root.job_id,
                sequence,
                BUDGET_EVENT,
                command_id,
                "coo",
                root.job_id,
                json.dumps(body, separators=(",", ":")),
                runtime.store.now_ms(),
            ),
        )
        connection.commit()
    finally:
        connection.close()


def test_domain_creation_projects_exact_reservation_and_survives_replay_reopen(tmp_path):
    runtime, root, domain = _root_and_domain(tmp_path)
    policy = CooCyclePolicy.load()
    expected = {
        "schema_version": (
            "mastermind.executive_coo_provider_work_budget_reservation/v1"
        ),
        "root_job_id": root.job_id,
        "domain_job_id": domain.job_id,
        "policy_schema_version": 2,
        "policy_sha256": policy.policy_sha256,
        "max_provider_work_units_per_root": 32,
        "reserved_domain_consumption_units": 1,
        "spent_provider_work_units": 0,
        "available_provider_work_units": 31,
        "reservation_status": "reservation_only",
    }
    projection = runtime.jobs.project_cycle_domain_provider_budget(root.job_id)
    assert {key: projection[key] for key in expected} == expected
    assert projection["reservation_digest"]

    row = _budget_row(runtime, root.job_id, domain.job_id)
    assert row is not None
    assert row["command_id"] == (
        f"coo-cycle:{root.job_id}:reserve-provider-budget:0"
    )
    assert row["aggregate_type"] == "job"
    assert row["aggregate_id"] == root.job_id
    assert row["actor"] == "coo"
    assert row["attempt_id"] is None
    assert row["worker_id"] is None
    assert row["quota_class"] is None
    with runtime.store.read() as connection:
        budget_events = int(
            connection.execute(
                "SELECT COUNT(*) FROM events WHERE event_type=?", (BUDGET_EVENT,)
            ).fetchone()[0]
        )
    assert budget_events == 1

    count = _event_count(runtime)
    replay = runtime.jobs.create_cycle_domain(
        root.job_id,
        command_id=f"coo-cycle:{root.job_id}:create-domain:0",
    )
    reopened = Runtime.at(tmp_path)
    assert replay.job_id == domain.job_id
    assert reopened.jobs.project_cycle_domain_provider_budget(
        root.job_id
    ) == projection
    assert _event_count(reopened) == count
    assert _budget_row(reopened, root.job_id, domain.job_id)["event_id"] == row[
        "event_id"
    ]


def _drifted_payload(runtime, root, domain, field, value):
    with runtime.store.read() as connection:
        payload = connection.execute(
            "SELECT payload_json FROM events WHERE event_type=?", (BUDGET_EVENT,)
        ).fetchone()[0]
    parsed = json.loads(payload)
    parsed[field] = value
    return json.dumps(parsed, separators=(",", ":"))


@pytest.mark.parametrize(
    "field,value,test_id",
    [
        ("available_provider_work_units", 30, "wrong-bounds"),
        ("max_provider_work_units_per_root", 31, "wrong-bounds"),
        ("reserved_domain_consumption_units", 0, "wrong-bounds"),
        ("spent_provider_work_units", 1, "spent"),
        ("reservation_status", "available", "available"),
        ("reservation_status", "spent", "spent"),
        ("policy_schema_version", 3, "policy"),
        ("policy_sha256", "0" * 64, "policy"),
        ("reservation_digest", "1" * 64, "digest"),
        ("root_job_id", "FOREIGN-ROOT", "root"),
        ("domain_job_id", "FOREIGN-DOMAIN", "domain"),
        ("max_provider_work_units_per_root", True, "bool-substitution"),
        ("max_provider_work_units_per_root", 32.0, "float-substitution"),
        ("reserved_domain_consumption_units", True, "bool-substitution"),
        ("available_provider_work_units", False, "bool-substitution"),
        ("available_provider_work_units", 31.0, "float-substitution"),
    ],
)
def test_corrupt_reservation_replay_and_projection_fail_closed(
    tmp_path, field, value, test_id
):
    runtime, root, domain = _root_and_domain(
        tmp_path,
        intent_id=(
            "CEO-R9B-"
            + field.replace("provider_work_units", "pwu")
            .replace("consumption_units", "cu")
            .replace("reservation", "res")
            + "-"
            + test_id
        )[:64],
    )
    payload_json = _drifted_payload(runtime, root, domain, field, value)
    _corrupt_budget_payload(runtime, payload_json)
    count = _event_count(runtime)
    with pytest.raises(StateConflict):
        runtime.jobs.project_cycle_domain_provider_budget(root.job_id)
    with pytest.raises(StateConflict):
        runtime.jobs.create_cycle_domain(
            root.job_id,
            command_id=f"coo-cycle:{root.job_id}:create-domain:0",
        )
    assert _event_count(runtime) == count
    assert runtime.jobs.get_job(domain.job_id) is not None


def test_duplicate_reservation_replay_fails_closed_without_new_effects(tmp_path):
    runtime, root, domain = _root_and_domain(
        tmp_path, intent_id="CEO-R9B-DUPLICATE-RESERVATION"
    )
    row = _reservation_event(runtime)
    _with_events_immutable(
        runtime,
        lambda connection: connection.execute(
            "UPDATE events SET command_id=? WHERE event_id=?",
            (row["command_id"] + "-DUPLICATE", row["event_id"]),
        ),
    )
    connection = sqlite3.connect(str(runtime.store.path))
    try:
        sequence = int(
            connection.execute(
                "SELECT COALESCE(MAX(sequence),0)+1 FROM events "
                "WHERE aggregate_type=? AND aggregate_id=?",
                (row["aggregate_type"], row["aggregate_id"]),
            ).fetchone()[0]
        )
        connection.execute(
            "INSERT INTO events(aggregate_type,aggregate_id,sequence,event_type,"
            "command_id,actor,job_id,payload_json,created_at_ms) "
            "VALUES(?,?,?,?,?,?,?,?,?)",
            (
                row["aggregate_type"],
                row["aggregate_id"],
                sequence,
                BUDGET_EVENT,
                row["command_id"],
                row["actor"],
                row["job_id"],
                row["payload_json"],
                row["created_at_ms"],
            ),
        )
        connection.commit()
    finally:
        connection.close()
    count = _event_count(runtime)
    with pytest.raises(StateConflict):
        runtime.jobs.project_cycle_domain_provider_budget(root.job_id)
    with pytest.raises(StateConflict):
        runtime.jobs.create_cycle_domain(
            root.job_id,
            command_id=f"coo-cycle:{root.job_id}:create-domain:0",
        )
    assert _event_count(runtime) == count
    assert runtime.jobs.get_job(domain.job_id) is not None


def test_duplicate_json_key_reservation_fails_closed(tmp_path):
    runtime, root, domain = _root_and_domain(
        tmp_path, intent_id="CEO-R9B-DUPLICATE-JSON-KEY"
    )
    payload = json.loads(_reservation_event(runtime)["payload_json"])
    payload["max_provider_work_units_per_root"] = 33
    payload_json = (
        '{"max_provider_work_units_per_root":32,'
        + json.dumps(payload, separators=(",", ":"))[1:]
    )
    _corrupt_budget_payload(runtime, payload_json)
    count = _event_count(runtime)
    with pytest.raises(StateConflict):
        runtime.jobs.project_cycle_domain_provider_budget(root.job_id)
    with pytest.raises(StateConflict):
        runtime.jobs.create_cycle_domain(
            root.job_id,
            command_id=f"coo-cycle:{root.job_id}:create-domain:0",
        )
    assert _event_count(runtime) == count
    assert runtime.jobs.get_job(domain.job_id) is not None


def test_missing_reservation_replay_fails_closed_without_recreation(tmp_path):
    runtime, root, domain = _root_and_domain(
        tmp_path, intent_id="CEO-R9B-MISSING-BUDGET"
    )
    def mutate(connection):
        connection.execute(
            "UPDATE jobs SET attempt_count=1,current_attempt_id='ATT-R9B-PROGRESS',"
            "assigned_worker_id='worker-r9b',assigned_quota_class='default',"
            "status='RUNNING' WHERE job_id=?",
            (domain.job_id,),
        )
        grant = '{"schema_version":"r9b-test-progress"}'
        connection.execute(
            "INSERT INTO attempts(attempt_id,job_id,attempt_number,worker_id,"
            "quota_class,status,fence_generation,authority_policy_hash,"
            "lease_token,lease_owner,lease_expires_at_ms,heartbeat_at_ms,"
            "execution_mode,requested_execution_profile_json,"
            "requested_execution_profile_digest,effective_grant_json,"
            "effective_grant_digest,placement_snapshot_json,"
            "placement_snapshot_digest,execution_principal_snapshot_json,"
            "execution_principal_snapshot_digest,started_at_ms,created_at_ms,"
            "updated_at_ms) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                "ATT-R9B-PROGRESS",
                domain.job_id,
                1,
                "worker-r9b",
                "default",
                "RUNNING",
                1,
                "0" * 64,
                "lease-r9b",
                "executive-coo-cycle",
                runtime.store.now_ms() + 3_600_000,
                runtime.store.now_ms(),
                "OPERATOR_HARNESS",
                grant,
                "1" * 64,
                grant,
                "1" * 64,
                grant,
                "1" * 64,
                grant,
                "1" * 64,
                runtime.store.now_ms(),
                runtime.store.now_ms(),
                runtime.store.now_ms(),
            ),
        )
        connection.execute(
            "INSERT INTO events(aggregate_type,aggregate_id,sequence,event_type,"
            "command_id,actor,job_id,attempt_id,payload_json,created_at_ms) "
            "VALUES('attempt',?,?,?,?,?,?,?,?,?)",
            (
                "ATT-R9B-PROGRESS",
                1,
                "ATTEMPT_CLAIMED",
                "r9b-domain-progress",
                "coo",
                domain.job_id,
                "ATT-R9B-PROGRESS",
                '{"progress":true}',
                runtime.store.now_ms(),
            ),
        )
        connection.execute(
            "DELETE FROM events WHERE event_type=?", (BUDGET_EVENT,)
        )
    connection = sqlite3.connect(str(runtime.store.path))
    try:
        connection.executescript(
            """
            DROP TRIGGER events_are_immutable_update;
            DROP TRIGGER events_are_immutable_delete;
            """
        )
        mutate(connection)
        connection.commit()
    finally:
        connection.close()
    count = _event_count(runtime)
    with pytest.raises(StateConflict):
        runtime.jobs.create_cycle_domain(
            root.job_id,
            command_id=f"coo-cycle:{root.job_id}:create-domain:0",
        )
    assert _event_count(runtime) == count
    assert runtime.jobs.get_job(domain.job_id) is not None


def test_matching_budget_evidence_for_fresh_root_fails_without_domain_creation(tmp_path):
    runtime, root = _root_without_domain(
        tmp_path, intent_id="CEO-R9B-FRESH-ROOT-EVIDENCE"
    )
    domain_job_id = f"{root.job_id}:plan"
    _valid_fresh_root_envelope(runtime, root, domain_job_id)
    count = _event_count(runtime)
    with pytest.raises(StateConflict, match="already exists for a new domain"):
        runtime.jobs.create_cycle_domain(
            root.job_id,
            command_id=f"coo-cycle:{root.job_id}:create-domain:0",
        )
    assert _event_count(runtime) == count
    with runtime.store.read() as check:
        domains = check.execute(
            "SELECT COUNT(*) FROM jobs WHERE orchestration_role='plan'"
        ).fetchone()[0]
        created = check.execute(
            "SELECT COUNT(*) FROM events WHERE event_type='JOB_CREATED' "
            "AND job_id=?", (domain_job_id,)
        ).fetchone()[0]
    assert domains == 0
    assert created == 0


def test_dangling_job_created_replay_fails_as_state_conflict(tmp_path):
    runtime, root, _domain = _root_and_domain(
        tmp_path, intent_id="CEO-R9B-DANGLING-JOB-CREATED"
    )
    command_id = f"coo-cycle:{root.job_id}:create-domain:0"
    with runtime.store.read() as connection:
        domain_job_id = connection.execute(
            "SELECT job_id FROM jobs WHERE orchestration_role='plan'"
        ).fetchone()[0]
    connection = sqlite3.connect(str(runtime.store.path))
    try:
        connection.executescript(
            """
            DROP TRIGGER events_are_immutable_update;
            DROP TRIGGER events_are_immutable_delete;
            """
        )
        connection.execute("DELETE FROM jobs WHERE orchestration_role='plan'")
        connection.commit()
    finally:
        connection.close()
    count = _event_count(runtime)
    with pytest.raises(StateConflict, match="replay Job identity is missing"):
        runtime.jobs.create_cycle_domain(
            root.job_id, command_id=command_id
        )
    assert _event_count(runtime) == count
    with runtime.store.read() as check:
        dangling = check.execute(
            "SELECT COUNT(*) FROM events WHERE event_type='JOB_CREATED' AND job_id=?",
            (domain_job_id,),
        ).fetchone()[0]
    assert dangling == 1
    with runtime.store.read() as check:
        domains = check.execute(
            "SELECT COUNT(*) FROM jobs WHERE orchestration_role='plan'"
        ).fetchone()[0]
    assert domains == 0


def test_injected_budget_append_failure_rolls_back_domain_job_and_creation_event(tmp_path, monkeypatch):
    runtime = Runtime.at(tmp_path)
    receipt = submit_intent(runtime, _v2_intent(intent_id="CEO-R9B-ROLLBACK"))
    root = runtime.jobs.get_job(receipt["job_id"])
    assert root is not None
    before = _event_count(runtime)
    original_append = type(runtime.store).append_event

    def append_event(self, connection, **kwargs):
        if kwargs.get("event_type") == BUDGET_EVENT:
            raise RuntimeError("injected budget append failure")
        return original_append(self, connection, **kwargs)

    monkeypatch.setattr(type(runtime.store), "append_event", append_event)
    with pytest.raises(RuntimeError, match="injected budget append failure"):
        runtime.jobs.create_cycle_domain(
            root.job_id,
            command_id=f"coo-cycle:{root.job_id}:create-domain:0",
        )
    assert _event_count(runtime) == before
    with runtime.store.read() as connection:
        domains = connection.execute(
            "SELECT COUNT(*) FROM jobs WHERE orchestration_role='plan'"
        ).fetchone()[0]
    assert domains == 0


def test_public_capability_object_is_not_admitted_and_flat_job_has_no_budget(tmp_path):
    runtime, root, _domain = _root_and_domain(
        tmp_path, intent_id="CEO-R9B-ORDINARY-PATH"
    )
    ordinary = runtime.jobs.create_job(
        "ordinary flat R9B path",
        constraints={"cost_class": "small"},
        command_id="r9b-ordinary-flat",
    )
    assert ordinary is not None
    with runtime.store.read() as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM events WHERE event_type=?", (BUDGET_EVENT,)
        ).fetchone()[0] == 1


def test_domain_budget_capability_alone_is_not_admitted(tmp_path):
    runtime = Runtime.at(tmp_path)
    receipt = submit_intent(runtime, _v2_intent(intent_id="CEO-R9B-CAPABILITY"))
    root = runtime.jobs.get_job(receipt["job_id"])
    assert root is not None
    with pytest.raises(StateConflict, match="plan Job creation is restricted"):
        runtime.jobs.create_job(
            "forged budget domain",
            parent_job_id=root.job_id,
            requested_authorities=["READ"],
            constraints={"cost_class": "small"},
            attempt_limit=2,
            command_id="r9b-forged-budget-domain",
            orchestration_role="plan",
            orchestration_provenance={
                "schema_version": (
                    "mastermind.executive_orchestration_provenance_source/v1"
                ),
                "creator": "coo_cycle",
                "source_id": root.job_id,
                "source_digest": root.orchestration_provenance_digest,
            },
            _coo_cycle_domain_budget_capability=(
                _COO_CYCLE_DOMAIN_BUDGET_CAPABILITY
            ),
        )
