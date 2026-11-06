"""Real disposable Runtime reads; corruption is confined to these test fixtures."""
import json
import sqlite3

import pytest
from control_plane import executive_runtime as er, workspace_source_join as join
from control_plane.ceo_intent import submit_intent
from tests.test_workspace_source_join import actual, intent


def legacy_intent(index=2):
    value = intent(index)
    value["schema"] = "mastermind.ceo_intent.v1"
    value.pop("intent_kind")
    value.pop("business_impact")
    return value


def corrupt_creation(writer, job_id, *, payload=None, raw=None, **fields):
    # Disposable test database only: deliberately model invalid retained evidence.
    with sqlite3.connect(writer.store.path) as connection:
        triggers = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type='trigger' AND name IN "
            "('events_are_immutable_update','events_are_immutable_delete') ORDER BY name").fetchall()
        connection.execute("DROP TRIGGER events_are_immutable_update")
        connection.execute("DROP TRIGGER events_are_immutable_delete")
        row = connection.execute(
            "SELECT payload_json FROM events WHERE job_id=? AND event_type='JOB_CREATED'",
            (job_id,)).fetchone()
        if payload is not None:
            body = json.loads(row[0])
            payload(body)
            fields["payload_json"] = er._json_dumps(body)
        if raw is not None:
            fields["payload_json"] = raw
        for column, value in fields.items():
            assert column in {"payload_json", "aggregate_id", "event_type", "command_id"}
            connection.execute(
                f"UPDATE events SET {column}=? WHERE job_id=? AND event_type='JOB_CREATED'",
                (value, job_id))
        for (ddl,) in triggers:
            connection.execute(ddl)


def unavailable(bound, namespace):
    result = join._bounded_runtime_inputs(bound())
    assert result[:3] == (None, None, None), result
    assert result[3] == {} and result[4]
    assert namespace.entries == namespace.exits and not namespace.active
    return result


def test_mixed_24_roots_preserves_both_ceo_candidates(actual):
    writer, bound, namespace, first = actual
    second = submit_intent(writer, intent(2))["job_id"]
    for index in range(22):
        writer.jobs.create_job(f"generic fixture {index}")
    result = join._bounded_runtime_inputs(bound())
    assert result[0] is not None, result[4]
    assert {row["job_id"] for row in result[0]} == {first, second}
    assert {row["workstream"] for row in result[0]} == {"WS:ONE"}
    assert result[4] == [] and result[5] is True
    assert namespace.entries == namespace.exits and not namespace.active


def test_legacy_ceo_workstream_remains_a_candidate(actual):
    writer, bound, namespace, first = actual
    second = submit_intent(writer, legacy_intent())["job_id"]
    result = join._bounded_runtime_inputs(bound())
    assert result[0] is not None, result[4]
    assert {row["job_id"] for row in result[0]} == {first, second}
    assert {row["workstream"] for row in result[0]} == {"WS:ONE"}


@pytest.mark.parametrize("fault", [
    "missing", "duplicate", "unknown_schema", "missing_workstream",
    "bad_identity", "explicit_null", "duplicate_json_key", "ceo_command_without_provenance",
])
def test_unresolved_origin_refuses_complete_mapping(actual, fault):
    writer, bound, namespace, first = actual
    root = submit_intent(writer, legacy_intent())["job_id"]
    if fault == "missing":
        corrupt_creation(writer, root, event_type="NOT_CREATION")
    elif fault == "duplicate":
        with sqlite3.connect(writer.store.path) as connection:
            connection.execute("""INSERT INTO events
                (aggregate_type,aggregate_id,sequence,event_type,command_id,actor,job_id,
                 payload_json,created_at_ms)
                SELECT aggregate_type,aggregate_id,sequence+100,event_type,'duplicate-origin',
                       actor,job_id,payload_json,created_at_ms FROM events
                WHERE job_id=? AND event_type='JOB_CREATED'""", (root,))
    elif fault == "unknown_schema":
        corrupt_creation(writer, root, payload=lambda body: body["provenance"].update(schema="unknown"))
    elif fault == "missing_workstream":
        corrupt_creation(writer, root, payload=lambda body: body["provenance"].pop("workstream"))
    elif fault == "bad_identity":
        corrupt_creation(writer, root, aggregate_id="JOB-999999")
    elif fault == "explicit_null":
        corrupt_creation(writer, root, command_id="non-ceo-looking",
                         payload=lambda body: body.update(provenance=None))
    elif fault == "duplicate_json_key":
        with sqlite3.connect(writer.store.path) as connection:
            raw = connection.execute("SELECT payload_json FROM events WHERE job_id=?", (root,)).fetchone()[0]
        corrupt_creation(writer, root, raw=raw[:-1]+',"provenance":null}')
    else:
        corrupt_creation(writer, root, payload=lambda body: body.pop("provenance"))
    result = unavailable(bound, namespace)
    assert "reviewed DDL" not in result[4][0]


@pytest.mark.parametrize("budget,value,fragment", [
    ("BOUNDED_ROOT_ORIGIN_MAX_STATEMENTS", 1, "statement budget"),
    ("BOUNDED_ROOT_ORIGIN_MAX_ROWS", 1, "row budget"),
    ("BOUNDED_ROOT_ORIGIN_MAX_CELL_BYTES", 32, "cell byte budget"),
    ("BOUNDED_ROOT_ORIGIN_MAX_TOTAL_BYTES", 32, "total byte budget"),
])
def test_origin_budget_exhaustion_returns_no_partial_or_receipt(actual, monkeypatch, budget, value, fragment):
    writer, bound, namespace, first = actual
    monkeypatch.setattr(er, budget, value)
    with pytest.raises(er.RuntimeReadUnavailable, match=fragment):
        with bound().observe_bounded_read() as read:
            read.discover_job_roots_bounded()
            read.classify_root_origins_bounded()
    with pytest.raises(er.StateConflict, match="not finalized"):
        _ = read.receipt
    assert namespace.entries == namespace.exits and not namespace.active


def test_vm_budget_is_cumulative_and_closes_without_receipt(actual, monkeypatch):
    writer, bound, namespace, first = actual
    # Lower the owner guard in this test only, before it installs its handler.
    guard = er._RuntimeReadProgressGuard
    monkeypatch.setattr(er, "_RuntimeReadProgressGuard", lambda: guard(limit=5))
    with pytest.raises(er.RuntimeReadUnavailable, match="VM budget"):
        with bound().observe_bounded_read() as read:
            read.discover_job_roots_bounded()
            read.classify_root_origins_bounded()
    with pytest.raises(er.StateConflict):
        _ = read.receipt
    assert namespace.entries == namespace.exits and not namespace.active


def test_classification_has_fixed_queries_and_returns_detached_cached_values(actual, monkeypatch):
    writer, bound, namespace, first = actual
    for _ in range(3):
        writer.jobs.create_job("ordinary root")
    traces = []
    connect = er.sqlite3.connect
    def traced(*args, **kwargs):
        connection = connect(*args, **kwargs)
        connection.set_trace_callback(traces.append)
        return connection
    monkeypatch.setattr(er.sqlite3, "connect", traced)
    monkeypatch.setattr(er.EventRegistry, "list_events", lambda *a, **kw: pytest.fail("Event history"))
    with bound().observe_bounded_read() as read:
        read.discover_job_roots_bounded()
        origins = read.classify_root_origins_bounded()
        before = len(traces)
        strict = next(row for row in origins if row.kind == "STRICT_V2_CEO")
        strict.provenance["workstream"] = "WS:TAMPERED"
        again = read.classify_root_origins_bounded()
        assert next(row for row in again if row.job_id == first).provenance["workstream"] == "WS:ONE"
        assert len(traces) == before
    assert read.receipt.state == "SAME"
    event_queries = [sql for sql in traces if "FROM events" in sql]
    assert len(event_queries) == 8
    assert all("LIMIT 2" in sql or "WHERE event_id=" in sql for sql in event_queries)
    assert not any(sql.lstrip().upper().startswith(("INSERT ", "UPDATE ", "DELETE ")) for sql in traces)


def test_complete_64_root_discovery_does_not_raise_detail_limit(actual):
    writer, bound, namespace, first = actual
    for _ in range(63):
        writer.jobs.create_job("generic bounded root")
    result = join._bounded_runtime_inputs(bound())
    assert [row["job_id"] for row in result[0]] == [first], result[4]
    writer.jobs.create_job("65th root refuses, never omitted")
    unavailable(bound, namespace)


def test_18_legacy_candidates_exceed_unchanged_detail_limit(actual):
    writer, bound, namespace, first = actual
    for index in range(2, 19):
        submit_intent(writer, legacy_intent(index))
    result = unavailable(bound, namespace)
    assert "selected root detail budget" in result[4][0]


def test_unknown_observation_cannot_be_promoted_by_valid_origin(actual):
    writer, bound, namespace, first = actual
    unbound = er.Runtime.at(writer.store.root, create=False)
    result = join._bounded_runtime_inputs(unbound)
    assert result[:3] == (None, None, None) and "not SAME" in result[4][0]


def test_origin_read_refuses_before_selection_and_after_close(actual):
    writer, bound, namespace, first = actual
    with pytest.raises(er.RuntimeReadUnavailable):
        with bound().observe_bounded_read() as read:
            read.classify_root_origins_bounded()
    with bound().observe_bounded_read() as read:
        read.discover_job_roots_bounded()
        read.classify_root_origins_bounded()
    with pytest.raises(er.StateConflict):
        read.classify_root_origins_bounded()


def test_changed_observation_refuses_even_when_all_origins_validate(actual, monkeypatch):
    writer, bound, namespace, first = actual
    original = er.BoundedRuntimeReadObservation.classify_root_origins_bounded
    def concurrent_change(read):
        result = original(read)
        # A legal concurrent writer commits after the read snapshot. The retained
        # connection's final data_version must detect it, even for a non-CEO row.
        writer.jobs.create_job("independent concurrent fixture")
        return result
    monkeypatch.setattr(er.BoundedRuntimeReadObservation, "classify_root_origins_bounded", concurrent_change)
    result = unavailable(bound, namespace)
    assert "not SAME" in result[4][0]


def test_generic_creation_cannot_erase_unknown_provenance(actual):
    writer, bound, namespace, first = actual
    writer.jobs.create_job("source unknown", provenance={"schema": "future.ceo.origin"})
    unavailable(bound, namespace)


def test_legacy_workstream_drift_between_discovery_and_detail_refuses(actual, monkeypatch):
    writer, bound, namespace, first = actual
    legacy = submit_intent(writer, legacy_intent())["job_id"]
    original = join._root_evidence
    changed = False
    def detail(runtime, root):
        nonlocal changed
        if not changed:
            corrupt_creation(writer, legacy, payload=lambda body:
                             body["provenance"].update(workstream="WS:CHANGED"))
            changed = True
        return original(runtime, root)
    monkeypatch.setattr(join, "_root_evidence", detail)
    result = unavailable(bound, namespace)
    assert "changed after discovery" in result[4][0]


@pytest.mark.parametrize("change", [
    {"root_job_id": "JOB-999999"},
    {"parent_job_id": "JOB-999999"},
    {"depth": True},
    {"status": "RUNNING"},
])
def test_strict_creation_shape_conflict_is_unresolved(actual, change):
    writer, bound, namespace, first = actual
    corrupt_creation(writer, first, payload=lambda body: body.update(change))
    result = unavailable(bound, namespace)
    assert "reviewed DDL" not in result[4][0]
