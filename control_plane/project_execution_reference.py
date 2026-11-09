"""Bounded original-principal READ of project executions; no lifecycle effects.

The only catalogue query selects at most nine immutable creation references for
one project and principal. Runtime and the original-input owner validate each
selected record. A reference/result witness is DATA, never send authority.
"""
from __future__ import annotations

import json
import re

from common import project_conversation_read_contract as wire
from common.project_execution_private_contract import canonical, digest, validate_previous_run
from control_plane import project_execution_admission as admission
from control_plane.executive_runtime import Runtime
from control_plane.executive_supervisor import ExecutiveSupervisor

REFERENCE_SCHEMA = "mastermind.project_execution_reference.v1"
CATALOGUE_SCHEMA = "mastermind.project_execution_references.v1"
READ_SCHEMA = "mastermind.project_execution_window.v1"
_LIMIT = 8
_DATA_LIMIT = wire.MAX_RESPONSE_BYTES - 512


def _fail():
    raise ValueError("PROJECT_EXECUTION_READ_UNAVAILABLE")


def _check(runtime, supervisor, principal_scope, guard):
    if (type(runtime) is not Runtime or type(supervisor) is not ExecutiveSupervisor
            or supervisor.runtime is not runtime or type(principal_scope) is not str
            or re.fullmatch(r"[0-9a-f]{64}", principal_scope) is None
            or not callable(guard) or guard() is not True):
        _fail()


def _bounded(value):
    encoded = canonical(value)
    if len(encoded) > _DATA_LIMIT:
        _fail()
    return json.loads(encoded)


def _reference(root, event, source):
    return dict(schema=REFERENCE_SCHEMA, work_ref=source["work_ref"], root_job_id=root.job_id,
        root_event_id=event.event_id, root_event_sha256=digest(event.to_dict()),
        project_execution_source_sha256=digest(source), principal_scope_sha256=source["principal_scope_sha256"])


def _record(runtime, supervisor, *, work_ref, principal_scope, root_id, guard, reference=None):
    _check(runtime, supervisor, principal_scope, guard)
    root = runtime.jobs.get_job(root_id)
    source = admission.read_source(runtime, root)
    if (source is None or source["work_ref"] != work_ref
            or source["principal_scope_sha256"] != principal_scope):
        _fail()
    event = runtime.store.unique_root_created_event(root.job_id)
    actual = _reference(root, event, source)
    if reference is not None and reference != actual:
        _fail()
    private = json.loads(admission.read_original_input(supervisor, source))
    _check(runtime, supervisor, principal_scope, guard)
    current = runtime.jobs.get_job(root.job_id)
    if (current is None or admission.read_source(runtime, current) != source
            or _reference(current, runtime.store.unique_root_created_event(root.job_id), source) != actual
            or (current.status, current.current_attempt_id) != (root.status, root.current_attempt_id)):
        _fail()
    return root, source, event, private, actual


def _rows(runtime, work_ref, principal_scope):
    # Same existing Event source as Fresh references, never a root-wide scan.
    with runtime.store.read() as connection:
        rows = connection.execute("""SELECT job_id,event_id FROM events
            WHERE event_type='JOB_CREATED' AND aggregate_type='job'
              AND json_extract(payload_json,'$.project_execution_admission.source.work_ref')=?
              AND json_extract(payload_json,'$.project_execution_admission.source.principal_scope_sha256')=?
            ORDER BY event_id DESC LIMIT ?""", (work_ref, principal_scope, _LIMIT + 1)).fetchall()
    return tuple((row["job_id"], row["event_id"]) for row in rows)


def execution_references(runtime, supervisor, arguments, *, principal_scope, guard):
    selected = wire.arguments(arguments, "execution_references")
    _check(runtime, supervisor, principal_scope, guard)
    rows = _rows(runtime, selected["work_ref"], principal_scope)
    entries = []
    result = dict(schema=CATALOGUE_SCHEMA, work_ref=selected["work_ref"], state="AVAILABLE",
        coverage=dict(state="COMPLETE", limit=_LIMIT, returned=0), entries=entries, can_send=False)
    for root_id, event_id in rows[:_LIMIT]:
        root, _source, event, private, reference = _record(runtime, supervisor,
            work_ref=selected["work_ref"], principal_scope=principal_scope, root_id=root_id, guard=guard)
        if event.event_id != event_id:
            _fail()
        entry = dict(kind="project_execution", reference=reference,
            goal=private["request"]["objective"], root_state=root.status.value)
        entries.append(entry)
        result["coverage"]["returned"] = len(entries)
        if len(canonical(result)) > _DATA_LIMIT:
            entries.pop()
            break
    result["coverage"].update(returned=len(entries), state="PARTIAL" if len(rows) > len(entries) else "COMPLETE")
    _check(runtime, supervisor, principal_scope, guard)
    if _rows(runtime, selected["work_ref"], principal_scope) != rows:
        _fail()
    _check(runtime, supervisor, principal_scope, guard)
    return _bounded(result)


def execution_read(runtime, supervisor, arguments, *, principal_scope, guard):
    selected = wire.arguments(arguments, "execution_read")
    if selected["principal_scope_sha256"] != principal_scope:
        _fail()
    root, source, event, private, reference = _record(runtime, supervisor,
        work_ref=selected["work_ref"], principal_scope=principal_scope,
        root_id=selected["root_job_id"], reference=selected, guard=guard)
    previous = source.get("previous_run")
    if previous is not None:
        previous = validate_previous_run(previous)
    result = witness = None
    if root.status.value == "COMPLETED":
        _check(runtime, supervisor, principal_scope, guard)
        completed = admission.completed_run(supervisor, root.job_id, selected["work_ref"], principal_scope)
        witness = validate_previous_run(completed["witness"])
        if (witness["root_job_id"] != root.job_id or witness["root_event_id"] != event.event_id
                or witness["root_event_sha256"] != reference["root_event_sha256"]
                or witness["project_execution_source_sha256"] != reference["project_execution_source_sha256"]
                or witness["input_fingerprint_sha256"] != source["input_fingerprint_sha256"]
                or witness["attempt_id"] != root.current_attempt_id
                or completed["objective"] != private["request"]["objective"]
                or digest(completed["result_envelope"]) != witness["result_envelope_sha256"]
                or digest(completed["terminal_receipt"]) != witness["terminal_receipt_sha256"]):
            _fail()
        result = dict(digest=witness["result_envelope_sha256"], envelope=completed["result_envelope"],
            terminal_receipt_sha256=witness["terminal_receipt_sha256"])
    current = _record(runtime, supervisor, work_ref=selected["work_ref"], principal_scope=principal_scope,
        root_id=root.job_id, reference=selected, guard=guard)
    if ((current[0].status, current[0].current_attempt_id) != (root.status, root.current_attempt_id)
            or current[1] != source or current[3] != private):
        _fail()
    return _bounded(dict(schema=READ_SCHEMA, kind="project_execution", reference=reference,
        state=root.status.value, goal=private["request"]["objective"], continuation_mode=source["continuation_mode"],
        locator=dict(work_ref=source["work_ref"], root_job_id=root.job_id, job_id=root.job_id,
            attempt_id=root.current_attempt_id), previous_run=previous, result=result,
        parent_witness=witness, can_send=False))
