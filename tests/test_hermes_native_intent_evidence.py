"""Durable native intent boundaries against real SQLite, without a live host.

The separate native-owner suite exercises Hermes's actual lazy dispatcher.
These cases keep the relevant-history bound and duplicate/result fences visible
in ordinary offline CI.
"""
from __future__ import annotations

import json
import sqlite3

import pytest

from integrations.hermes_attended_fabric.native import SessionGrant, TOOL
from integrations.hermes_attended_fabric.native_evidence import qualify_native_intent


class EvidenceDB:
    def __init__(self):
        self.connection = sqlite3.connect(":memory:")
        self.connection.row_factory = sqlite3.Row
        self.connection.execute(
            "CREATE TABLE messages (id INTEGER PRIMARY KEY, session_id TEXT, "
            "role TEXT, tool_calls TEXT, tool_call_uids TEXT, tool_call_uid TEXT)")
        self.lineage = ["native-parent"]

    def _resume_lineage_ids(self, _session):
        return self.lineage

    def _read_all(self, sql, parameters):
        return self.connection.execute(sql, parameters).fetchall()

    def _read_one(self, sql, parameters):
        return self.connection.execute(sql, parameters).fetchone()

    def persist(self, call_id, arguments, *, wrapped=True, uid="durable-uid",
                wrapper=None, encoded=True):
        value = ({"calls": [{"name": TOOL, "arguments": arguments}]}
                 if wrapped else arguments)
        if wrapper is not None:
            value = wrapper
        call = {"id": call_id, "type": "function", "function": {
            "name": "tool_call" if wrapped else TOOL,
            "arguments": json.dumps(value) if encoded else value}}
        self.connection.execute(
            "INSERT INTO messages(session_id,role,tool_calls,tool_call_uids) "
            "VALUES (?,?,?,?)",
            ("native-parent", "assistant", json.dumps([call]),
             json.dumps({call_id: uid} if uid is not None else {})))

    def completed(self, uid="durable-uid"):
        self.connection.execute(
            "INSERT INTO messages(session_id,role,tool_call_uid) VALUES (?,?,?)",
            ("native-parent", "tool", uid))


@pytest.fixture
def db():
    value = EvidenceDB()
    yield value
    value.connection.close()


@pytest.fixture
def arguments():
    return {"action": "submit", "task_key": "read-source",
            "task_class": "census", "task_complexity": "C1_ROUTINE_BOUNDED",
            "work_packet": "Read the assigned source."}


def qualify(db, arguments, *, call_id="outer-call", original_submit=True):
    grant = SessionGrant(
        profile_id="fixture", session_id="native-parent",
        root_id="hermes-native-root", parent_id="hermes-native-root",
        generation="native-generation", origin_session_id="native-parent")
    return qualify_native_intent(
        db, grant, call_id, arguments, original_submit=original_submit)


@pytest.mark.parametrize("wrapped", [False, True])
@pytest.mark.parametrize("encoded", [False, True])
def test_direct_and_single_broker_envelopes_retain_outer_identity(
        db, arguments, wrapped, encoded):
    db.persist("outer-call", arguments, wrapped=wrapped, encoded=encoded)
    assert qualify(db, arguments)
    assert not qualify(db, arguments, call_id="invented-inner-call")


def test_unrelated_broker_history_does_not_consume_the_relevant_copy_bound(
        db, arguments):
    for number in range(300):
        db.persist(f"unrelated-{number}", {**arguments, "task_key": f"other-{number}"})
    db.persist("malformed-unrelated", arguments, wrapper={"calls": ["not-an-entry"]})
    db.persist("outer-call", arguments)
    assert qualify(db, arguments)


@pytest.mark.parametrize(("copies", "accepted"), [(256, True), (257, False)])
def test_relevant_copy_bound_remains_closed(db, arguments, copies, accepted):
    for _ in range(copies):
        db.persist("outer-call", arguments)
    assert qualify(db, arguments) is accepted


@pytest.mark.parametrize("variant", [
    "two-workers", "mixed-local", "nested", "wrong-tool", "string-arguments",
    "missing-arguments", "ambiguous-outer", "ambiguous-entry", "non-list",
])
def test_ambiguous_or_noncanonical_wrapper_cannot_become_native_evidence(
        db, arguments, variant):
    entry = {"name": TOOL, "arguments": arguments}
    wrappers = {
        "two-workers": {"calls": [entry, entry]},
        "mixed-local": {"calls": [entry, {"name": "terminal", "arguments": {}}]},
        "nested": {"calls": [{"name": "tool_call", "arguments": {"calls": [entry]}}]},
        "wrong-tool": {"calls": [{"name": "another_tool", "arguments": arguments}]},
        "string-arguments": {"calls": [{"name": TOOL, "arguments": json.dumps(arguments)}]},
        "missing-arguments": {"calls": [{"name": TOOL}]},
        "ambiguous-outer": {"calls": [entry], "name": "another_tool"},
        "ambiguous-entry": {"calls": [{**entry, "id": "invented-inner-call"}]},
        "non-list": {"calls": entry},
    }
    db.persist("outer-call", arguments, wrapper=wrappers[variant])
    assert not qualify(db, arguments)


@pytest.mark.parametrize("variant", [
    "missing-uid", "empty-uid", "conflicting-uid", "rewritten-packet", "completed",
])
def test_wrapper_does_not_relax_durable_identity_or_result_fences(
        db, arguments, variant):
    uid = {"missing-uid": None, "empty-uid": ""}.get(variant, "durable-uid")
    db.persist("outer-call", arguments, uid=uid)
    if variant == "conflicting-uid":
        db.persist("outer-call", arguments, uid="different-durable-uid")
    if variant == "completed":
        db.completed()
    incoming = ({**arguments, "work_packet": "A different request."}
                if variant == "rewritten-packet" else arguments)
    assert not qualify(db, incoming)


@pytest.mark.parametrize("other_wrapped", [False, True])
def test_direct_and_broker_submit_intents_share_one_original_submit_fence(
        db, arguments, other_wrapped):
    db.persist("prior-call", arguments, wrapped=other_wrapped, uid="prior-uid")
    db.persist("outer-call", arguments)
    assert qualify(db, arguments, original_submit=False)
    assert not qualify(db, arguments, original_submit=True)


def test_matching_ambiguous_batch_is_not_hidden_from_original_submit_check(
        db, arguments):
    db.persist("prior-batch", arguments, wrapper={"calls": [
        {"name": "terminal", "arguments": {}},
        {"name": TOOL, "arguments": arguments},
    ]}, uid="prior-uid")
    db.persist("outer-call", arguments)
    assert qualify(db, arguments, original_submit=False)
    assert not qualify(db, arguments, original_submit=True)


def test_wrapper_still_requires_current_canonical_lineage(db, arguments):
    db.persist("outer-call", arguments)
    db.lineage = ["foreign-origin", "native-parent"]
    assert not qualify(db, arguments)
    db.lineage = ["native-parent"] + [f"segment-{number}" for number in range(99)]
    assert not qualify(db, arguments)

@pytest.mark.parametrize("variant", [
    "inner-json", "calls-object", "calls-json-array", "calls-json-object",
    "legacy-object", "legacy-json", "legacy-null-calls", "padded-name",
])
def test_broker_compatibility_forms_remain_original_submit_conflicts(
        db, arguments, variant):
    entry = {"name": TOOL, "arguments": arguments}
    wrappers = {
        "inner-json": {"calls": [{"name": TOOL, "arguments": json.dumps(arguments)}]},
        "calls-object": {"calls": entry},
        "calls-json-array": {"calls": json.dumps([entry])},
        "calls-json-object": {"calls": json.dumps(entry)},
        "legacy-object": entry,
        "legacy-json": {"name": TOOL, "arguments": json.dumps(arguments)},
        "legacy-null-calls": {"calls": None, **entry},
        "padded-name": {"calls": [{"name": "\t\u2003" + TOOL + "\n", "arguments": arguments}]},
    }
    db.persist("prior-compatible", arguments, wrapper=wrappers[variant], uid="prior-uid")
    # Noncanonical envelopes remain inadmissible on their own.
    assert not qualify(db, arguments, call_id="prior-compatible", original_submit=False)
    db.persist("outer-call", arguments)
    assert qualify(db, arguments, original_submit=False)
    assert not qualify(db, arguments, original_submit=True)
