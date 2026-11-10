"""Honest T3 thread-list projection reads (source-level composition proofs).

Every state file, environment fact and receipt below is a disposable test
fixture written under ``tmp_path``.  These prove the projection's source
semantics only: no test launches, interrupts, sends to or otherwise touches a
real T3 thread or the real adapter state.  Honest absence stays an AVAILABLE
empty list; missing/malformed evidence is a typed refusal document, never a
partial projection and never an invented environment.
"""
import asyncio
import json
import sqlite3

import pytest

from common import workspace_t3_thread_projection_contract as wire
from control_plane.workspace_t3_thread_projection_read import (
    ExistingT3ThreadProjectionSource,
    T3ThreadProjectionError,
    handle_t3_thread_projection_frame,
    map_run_state,
    project_threads,
    read_thread_state_rows,
)
from tests.test_t3_attempt_fleet_projection import (
    NOW_ISO, THREAD_1, _intent as _fleet_intent, _receipt as _fleet_receipt,
    _spec, _state_file as _fleet_state_file,
)

ENVIRONMENT_ID = "m2studio"
ENVIRONMENT_DOC = {
    "schema": "mastermind.t3_environment_observation/v1",
    "environment_id": ENVIRONMENT_ID,
    "observed_at_utc": NOW_ISO,
    "source": "tests.workspace_t3_thread_projection",
}
HTTPS_LINK = "https://t3.example.com/threads/abc"
RUN_ID = "runs/att-1"


# ── fixtures (real adapter schema; synthetic rows; installed environment fact) ─


def _state_file(tmp_path, rows, name="t3_adapter_state.sqlite3"):
    """Create the REAL adapter schema, then insert raw JSON rows (test-only)."""
    from control_plane.t3_execution_adapter import SQLiteT3AdapterStateStore

    path = tmp_path / name
    store = SQLiteT3AdapterStateStore(path)  # writes the reviewed schema only
    store.close()
    connection = sqlite3.connect(path)
    for record in rows:
        connection.execute(
            "INSERT INTO t3_adapter_runs (run_id, intent_json, receipt_json,"
            " spec_json, result_ref_json, cursor_text, schema_version, updated_ms)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (
                record["run_id"],
                json.dumps(record.get("intent")),
                json.dumps(record["receipt"]) if record.get("receipt") else None,
                json.dumps(record["spec"]) if record.get("spec") else None,
                json.dumps(record["result_ref"]) if record.get("result_ref") else None,
                "",
                "mastermind.t3_adapter_state/v1",
                1,
            ),
        )
    connection.commit()
    connection.close()
    return path


def _environment_file(tmp_path, document=ENVIRONMENT_DOC):
    path = tmp_path / "t3_environment_observation.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def _intent(title=None, run_id=RUN_ID):
    intent = _fleet_intent(run_id=run_id)
    if title is not None:
        intent["envelope"]["title"] = title
    return intent


def _receipt(thread_id=THREAD_1, status="preparing", link=""):
    receipt = _fleet_receipt(thread_id=thread_id)
    receipt["status"] = status
    receipt["link"] = link
    return receipt


def _row(*, run_id=RUN_ID, title=None, status="preparing", link="", receipt=True,
         thread_id=THREAD_1, result_ref=None):
    row = {"run_id": run_id, "intent": _intent(title=title, run_id=run_id),
           "spec": _spec()}
    if receipt:
        row["receipt"] = _receipt(thread_id=thread_id, status=status, link=link)
    if result_ref is not None:
        row["result_ref"] = result_ref
    return row


def _source(tmp_path, rows, *, environment=True):
    return ExistingT3ThreadProjectionSource(
        adapter_state_path=_state_file(tmp_path, rows),
        environment_path=_environment_file(tmp_path) if environment else None,
    )


# ── composition: honest empty / honest unavailable ──────────────────────────


def test_missing_store_is_honest_empty_available_list(tmp_path):
    source = ExistingT3ThreadProjectionSource(
        adapter_state_path=tmp_path / "absent.sqlite3",
        environment_path=_environment_file(tmp_path),
    )
    document = source.read()
    assert wire.validate_document(document) is document
    assert document == {"schema": wire.LIST_SCHEMA, "availability": "AVAILABLE",
                        "reason": None, "threads": []}


def test_missing_environment_source_is_unavailable_naming_the_source(tmp_path):
    source = _source(tmp_path, [_row()], environment=False)
    document = source.read()
    assert document == wire.unavailable("T3_ENVIRONMENT_SOURCE_UNAVAILABLE")
    assert wire.validate_document(document) is document
    # Never a defaulted environment id, and never a partial projection.
    assert document["threads"] == []


def test_unreadable_environment_file_is_unavailable_not_defaulted(tmp_path):
    source = ExistingT3ThreadProjectionSource(
        adapter_state_path=_state_file(tmp_path, [_row()]),
        environment_path=tmp_path / "no-such-observation.json",
    )
    assert source.read() == wire.unavailable("T3_ENVIRONMENT_SOURCE_UNAVAILABLE")


@pytest.mark.parametrize("document", [
    {**ENVIRONMENT_DOC, "environment_id": "BAD ID"},
    {**ENVIRONMENT_DOC, "schema": "mastermind.foreign/v1"},
    {**ENVIRONMENT_DOC, "observed_at_utc": "2026-11-09T12:00:00"},  # no offset
    {"environment_id": ENVIRONMENT_ID},
    {"schema": "mastermind.t3_environment_observation/v1", "environment_id": ENVIRONMENT_ID,
     "observed_at_utc": NOW_ISO, "source": "x", "unexpected": 1},
])
def test_invalid_environment_fact_is_unavailable_never_invented(tmp_path, document):
    source = ExistingT3ThreadProjectionSource(
        adapter_state_path=_state_file(tmp_path, [_row()]),
        environment_path=_environment_file(tmp_path, document),
    )
    assert source.read() == wire.unavailable("T3_ENVIRONMENT_SOURCE_UNAVAILABLE")


# ── composition: exact rows from persisted facts ────────────────────────────


def test_persisted_receipt_projects_the_exact_frozen_row(tmp_path):
    document = _source(
        tmp_path, [_row(title="Launch builder", status="preparing", link=HTTPS_LINK)]
    ).read()
    assert wire.validate_document(document) is document
    assert document["availability"] == "AVAILABLE"
    assert document["threads"] == [{
        "threadId": THREAD_1,
        "environment": ENVIRONMENT_ID,
        "title": "Launch builder",
        "runState": "running",
        "lastActivity": NOW_ISO,
        "prLink": HTTPS_LINK,
        "repository": None,
        "companyManaged": True,
    }]


def test_absent_optional_facts_stay_null_not_guessed(tmp_path):
    document = _source(tmp_path, [_row(title=None, link="")]).read()
    thread = document["threads"][0]
    assert thread["title"] is None
    assert thread["prLink"] is None          # "" is not a link
    assert thread["repository"] is None      # no attested repository fact
    assert thread["companyManaged"] is True


def test_intent_without_receipt_is_omitted_documented_effect_unknown_rule(tmp_path):
    # Documented rule: an intent with no receipt has no honest thread identity
    # (the launch may or may not have minted a thread), so it is OMITTED from
    # the thread list; the per-attempt fleet read owns its effect-unknown state.
    document = _source(tmp_path, [_row(receipt=False)]).read()
    assert document["availability"] == "AVAILABLE"
    assert document["threads"] == []


def test_duplicate_thread_collapses_to_the_first_observation(tmp_path):
    document = _source(tmp_path, [
        _row(run_id="runs/att-1", title="first", status="preparing"),
        _row(run_id="runs/att-2", title="second", status="completed"),
    ]).read()
    assert [row["title"] for row in document["threads"]] == ["first"]
    assert len(document["threads"]) == 1


def test_ledgered_terminal_status_is_the_most_current_observation(tmp_path):
    document = _source(tmp_path, [
        _row(status="preparing", result_ref={"native_status": "completed"}),
    ]).read()
    assert document["threads"][0]["runState"] == "idle"


# ── runState: the adapter's own status vocabulary only ──────────────────────


@pytest.mark.parametrize("native,expected", [
    ("preparing", "running"), ("queued", "running"), ("starting", "running"),
    ("running", "running"), ("waiting", "running"), ("in_progress", "running"),
    ("succeeded", "idle"), ("completed", "idle"), ("failed", "idle"),
    ("cancelled", "idle"), ("interrupted", "idle"), ("rolled_back", "idle"),
    ("timed_out", "idle"),
    ("Succeeded", "idle"),            # the adapter vocabulary is case-folded
    ("unmapped_state", "unknown"),    # never guessed into a live/settled state
    ("", "unknown"),                  # absent is unknown, never idle
    (None, "unknown"),
])
def test_run_state_mapping_is_closed_and_never_defaults_to_idle(native, expected):
    assert map_run_state(native) == expected


def test_blocked_is_admitted_but_never_emitted(tmp_path):
    document = _source(tmp_path, [_row(status="preparing")]).read()
    assert all(row["runState"] != "blocked" for row in document["threads"])
    assert "blocked" in wire.RUN_STATES


@pytest.mark.parametrize("created_at,expected", [
    (NOW_ISO, NOW_ISO),
    ("2026-11-09T12:00:00Z", "2026-11-09T12:00:00Z"),
    ("yesterday", None),
    ("2026-11-09T12:00:00", None),   # no explicit offset is not an instant
])
def test_last_activity_uses_only_an_observed_iso_instant(tmp_path, created_at, expected):
    row = _row()
    row["receipt"]["created_at"] = created_at
    document = _source(tmp_path, [row]).read()
    assert document["threads"][0]["lastActivity"] == expected


@pytest.mark.parametrize("link,expected", [
    (HTTPS_LINK, HTTPS_LINK),
    ("http://t3.example.com/threads/abc", None),   # not https
    ("t3://thread/abc", None),
    ("", None),
])
def test_pr_link_is_only_an_https_receipt_link(tmp_path, link, expected):
    document = _source(tmp_path, [_row(link=link)]).read()
    assert document["threads"][0]["prLink"] == expected


# ── refusals: closed, typed, never partial ──────────────────────────────────


def test_over_cap_threads_are_refused_never_truncated(tmp_path):
    rows = [_row(run_id=f"runs/att-{index}",
                 thread_id="mcp:launch:" + format(index, "064d"))
            for index in range(wire.MAX_THREADS + 1)]
    document = _source(tmp_path, rows).read()
    assert document == wire.unavailable("THREADS_OVER_CAP")
    assert wire.validate_document(document) is document


def test_exactly_at_cap_is_available(tmp_path):
    rows = [_row(run_id=f"runs/att-{index}",
                 thread_id="mcp:launch:" + format(index, "064d"))
            for index in range(wire.MAX_THREADS)]
    document = _source(tmp_path, rows).read()
    assert document["availability"] == "AVAILABLE"
    assert len(document["threads"]) == wire.MAX_THREADS


def test_foreign_schema_is_a_typed_refusal(tmp_path):
    path = tmp_path / "foreign.sqlite3"
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE other (x TEXT)")
    connection.commit()
    connection.close()
    document = ExistingT3ThreadProjectionSource(
        adapter_state_path=path, environment_path=_environment_file(tmp_path)).read()
    assert document == wire.unavailable("ADAPTER_STATE_SCHEMA_UNKNOWN")


def test_malformed_row_json_is_a_typed_refusal(tmp_path):
    path = _state_file(tmp_path, [_row()])
    connection = sqlite3.connect(path)
    connection.execute("UPDATE t3_adapter_runs SET intent_json='not-json'")
    connection.commit()
    connection.close()
    document = ExistingT3ThreadProjectionSource(
        adapter_state_path=path, environment_path=_environment_file(tmp_path)).read()
    assert document == wire.unavailable("ADAPTER_ROW_MALFORMED")
    assert document["threads"] == []


def test_unopenable_state_file_is_a_typed_refusal(tmp_path):
    directory = tmp_path / "is-a-directory.sqlite3"
    directory.mkdir()
    document = ExistingT3ThreadProjectionSource(
        adapter_state_path=directory, environment_path=_environment_file(tmp_path)).read()
    assert document == wire.unavailable("ADAPTER_STATE_UNREADABLE")


def test_every_raisable_refusal_code_is_wire_legal():
    import inspect

    from control_plane import workspace_t3_thread_projection_read as reader

    source = inspect.getsource(reader)
    raisable, index, marker = set(), 0, "_refuse("
    while True:
        index = source.find(marker, index)
        if index < 0:
            break
        tail = source[index + len(marker):]
        token = tail.split('"')[1]
        if token.isupper():
            raisable.add(token)
        index += len(marker)
    assert raisable <= wire.REASONS, raisable - wire.REASONS


def test_read_is_read_only_and_creates_nothing(tmp_path):
    rows = [_row()]
    path = _state_file(tmp_path, rows)
    before = (sorted(p.name for p in tmp_path.iterdir()), path.read_bytes())
    source = ExistingT3ThreadProjectionSource(
        adapter_state_path=path, environment_path=_environment_file(tmp_path))
    source.read()
    after = (sorted(p.name for p in tmp_path.iterdir()), path.read_bytes())
    assert before[1] == after[1]          # bytes untouched
    assert set(before[0]) <= set(after[0])


def test_default_source_composes_the_installed_adapter_state_path(monkeypatch, tmp_path):
    from control_plane import workspace_t3_thread_projection_read as reader

    installed = tmp_path / "installed.sqlite3"
    monkeypatch.setattr(
        "control_plane.t3_execution_adapter.default_t3_adapter_state_path",
        lambda: installed,
    )
    source = reader.default_source()
    assert source.adapter_state_path == installed
    assert source.environment_path is None
    assert source.read() == wire.unavailable("T3_ENVIRONMENT_SOURCE_UNAVAILABLE")


# ── contract validators (frozen TS parity) ──────────────────────────────────


def test_contract_refuses_rows_outside_the_frozen_shape():
    row = {"threadId": THREAD_1, "environment": ENVIRONMENT_ID, "title": None,
           "runState": "idle", "lastActivity": None, "prLink": None,
           "repository": None, "companyManaged": True}
    assert wire.validate_row(row) is row
    with pytest.raises(ValueError):
        wire.validate_row({**row, "schema": wire.ROW_SCHEMA})     # no row schema key
    with pytest.raises(ValueError):
        wire.validate_row({k: v for k, v in row.items() if k != "title"})
    with pytest.raises(ValueError):
        wire.validate_row({**row, "runState": "stopped"})
    with pytest.raises(ValueError):
        wire.validate_row({**row, "companyManaged": "yes"})
    with pytest.raises(ValueError):
        wire.validate_row({**row, "threadId": "bad id"})
    with pytest.raises(ValueError):
        wire.validate_row({**row, "prLink": "http://t3.example.com/x"})


def test_contract_refuses_duplicate_identity_and_over_cap():
    row = {"threadId": THREAD_1, "environment": ENVIRONMENT_ID, "title": None,
           "runState": "idle", "lastActivity": None, "prLink": None,
           "repository": None, "companyManaged": True}
    with pytest.raises(ValueError):
        wire.available([row, dict(row)])
    with pytest.raises(ValueError):
        wire.available([row] * (wire.MAX_THREADS + 1))
    with pytest.raises(ValueError):
        wire.unavailable("NOT_A_REAL_REASON")


def test_reporting_rows_differ_by_environment_are_distinct_identities():
    row = {"threadId": THREAD_1, "environment": ENVIRONMENT_ID, "title": None,
           "runState": "idle", "lastActivity": None, "prLink": None,
           "repository": None, "companyManaged": True}
    document = wire.available([row, {**row, "environment": "other-host"}])
    assert len(document["threads"]) == 2


# ── frame handler ───────────────────────────────────────────────────────────


class _Owner:
    def __init__(self, source):
        self._t3_thread_projection_source = source
        self.authorize = lambda principal: True
        self.authorize.binding_digest = lambda principal: "a" * 64


def _frame():
    return {"schema": wire.FRAME_SCHEMA, "operation": wire.OPERATION,
            "selection": None, "principal": {"sub": "fixture"}}


def test_frame_handler_without_installed_source_serves_typed_absence():
    result = asyncio.run(handle_t3_thread_projection_frame(_Owner(None), _frame()))
    assert result == {"ok": True, "result": wire.unavailable("SOURCE_UNAVAILABLE")}


def test_frame_handler_refuses_foreign_frame_shape():
    owner = _Owner(None)
    for frame in (None, {}, {**_frame(), "schema": "foreign"},
                  {**_frame(), "operation": "other"}, {**_frame(), "extra": 1},
                  {**_frame(), "selection": THREAD_1}):
        result = asyncio.run(handle_t3_thread_projection_frame(owner, frame))
        assert result["ok"] is False and result["status"] == 400


def test_frame_handler_serves_a_source_swapped_mid_read_as_source_changed(
        tmp_path, monkeypatch):
    owner = _Owner(_source(tmp_path, [_row()]))
    real_read = ExistingT3ThreadProjectionSource.read

    def swap_mid_read(self):
        owner._t3_thread_projection_source = ExistingT3ThreadProjectionSource(
            adapter_state_path=self.adapter_state_path,
            environment_path=self.environment_path)
        return real_read(self)

    monkeypatch.setattr(ExistingT3ThreadProjectionSource, "read", swap_mid_read)
    result = asyncio.run(handle_t3_thread_projection_frame(owner, _frame()))
    assert result == {"ok": True, "result": wire.unavailable("SOURCE_CHANGED")}


@pytest.mark.parametrize("principal_revoked", [True, False])
def test_frame_handler_enforces_permission_at_release(tmp_path, principal_revoked):
    owner = _Owner(_source(tmp_path, [_row()]))
    calls = {"authorize": 0}

    def authorize(principal):
        calls["authorize"] += 1
        return not (principal_revoked and calls["authorize"] > 1)

    authorize.binding_digest = lambda principal: "a" * 64
    owner.authorize = authorize
    result = asyncio.run(handle_t3_thread_projection_frame(owner, _frame()))
    if principal_revoked:
        assert result["ok"] is False and result["status"] == 403
    else:
        assert result["ok"] is True
        assert result["result"]["threads"][0]["threadId"] == THREAD_1


def test_frame_handler_serves_the_exact_validated_document(tmp_path):
    owner = _Owner(_source(tmp_path, [_row(title="t")]))
    result = asyncio.run(handle_t3_thread_projection_frame(owner, _frame()))
    assert result["ok"] is True
    assert wire.validate_document(result["result"]) is result["result"]


def test_projection_never_raises_outside_its_typed_refusal(tmp_path):
    # A row-level contract violation must surface as a typed refusal, not as an
    # escaping ValueError from contract code.
    row = _row(thread_id="bad id")
    path = _state_file(tmp_path, [row])
    with pytest.raises(T3ThreadProjectionError):
        read_thread_state_rows(path)
    document = ExistingT3ThreadProjectionSource(
        adapter_state_path=path, environment_path=_environment_file(tmp_path)).read()
    assert document == wire.unavailable("ADAPTER_ROW_MALFORMED")
