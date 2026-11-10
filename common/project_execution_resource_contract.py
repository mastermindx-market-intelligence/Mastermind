"""Closed read evidence for original project roots and one selected resource.

Syntax and digests confer no authority. Only the existing bounded Runtime
origin owner and current DATA acquisition may supply these documents.
"""
from copy import deepcopy
import re

from common.executive_workspace_contract import digest, _check_job_id, _check_work_ref

HISTORY_SCHEMA = "mastermind.project_root_history.v1"
RESOURCE_SCHEMA = "mastermind.project_execution_resource.v1"
MAX_ROOTS = 50
_HASH = re.compile(r"[a-f0-9]{64}")
_OPERATION = re.compile(r"mmos-project-execute-[a-f0-9]{40}")
_STATUS = frozenset({"QUEUED", "RUNNING", "CHECKPOINTED", "RATE_LIMITED", "FAILED",
    "LOST", "CANCEL_REQUESTED", "COMPLETED", "CANCELLED"})
_EXECUTION = frozenset({"operation_key", "command_id", "continuation_mode", "source_sha256",
    "context_sha256", "input_reference_sha256", "previous_root_job_id"})
_ROOT = frozenset({"root_job_id", "kind", "purpose", "status", "creation_event_sha256", "execution"})


def _fail():
    raise ValueError("PROJECT_EXECUTION_RESOURCE_INVALID")


def _hash(value):
    return type(value) is str and _HASH.fullmatch(value) is not None


def validate_history(value, *, work_ref):
    if (type(value) is not dict or set(value) != {"schema", "work_ref", "roots", "observation"}
            or value["schema"] != HISTORY_SCHEMA or not _check_work_ref(work_ref)
            or value["work_ref"] != work_ref or type(value["roots"]) is not list
            or len(value["roots"]) > MAX_ROOTS):
        _fail()
    roots = value["roots"]
    ids = []
    for row in roots:
        if (type(row) is not dict or set(row) != _ROOT or not _check_job_id(row["root_job_id"])
                or type(row["status"]) is not str or row["status"] not in _STATUS
                or type(row["kind"]) is not str or type(row["purpose"]) is not str
                or not _hash(row["creation_event_sha256"])):
            _fail()
        ids.append(row["root_job_id"])
        execution = row["execution"]
        if execution is None:
            if (row["kind"], row["purpose"]) not in {
                    ("DIRECT_NATIVE_CEO", "PLANNING"), ("STRICT_V2_CEO", "ORCHESTRATION"),
                    ("LEGACY_CEO", "ORCHESTRATION")}:
                _fail()
            continue
        if (row["kind"] != "STRICT_V2_CEO" or row["purpose"] != "PROJECT_EXECUTION"
                or type(execution) is not dict or set(execution) != _EXECUTION
                or type(execution["operation_key"]) is not str
                or _OPERATION.fullmatch(execution["operation_key"]) is None
                or type(execution["command_id"]) is not str
                or re.fullmatch(r"ceo-intent:[A-Za-z0-9][A-Za-z0-9._-]{2,63}", execution["command_id"]) is None
                or type(execution["continuation_mode"]) is not str
                or execution["continuation_mode"] not in {"DURABLE", "ATTENDED"}
                or any(not _hash(execution[key]) for key in (
                    "source_sha256", "context_sha256", "input_reference_sha256"))
                or execution["previous_root_job_id"] is not None and (
                    not _check_job_id(execution["previous_root_job_id"])
                    or execution["previous_root_job_id"] == row["root_job_id"])):
            _fail()
    if ids != sorted(set(ids)):
        _fail()
    observation = value["observation"]
    if (type(observation) is not dict or set(observation) != {
            "schema", "state", "source_identity", "before", "after", "snapshot_digest"}
            or observation["schema"] != "mastermind.runtime_read_observation.v1"
            or observation["state"] != "SAME"
            or type(observation["source_identity"]) is not str
            or not 1 <= len(observation["source_identity"]) <= 256
            or any(ord(char) < 32 or 127 <= ord(char) <= 159 for char in observation["source_identity"])
            or type(observation["before"]) is not int or not 0 <= observation["before"] < 2**53
            or type(observation["after"]) is not int or not 0 <= observation["after"] < 2**53
            or observation["before"] != observation["after"]
            or observation["snapshot_digest"] != digest({"work_ref": work_ref, "roots": roots})):
        _fail()
    return value


def resource_from_history(history, *, root_job_id):
    if type(history) is not dict:
        _fail()
    history = validate_history(history, work_ref=history.get("work_ref"))
    matches = [row for row in history["roots"] if row["root_job_id"] == root_job_id]
    if len(matches) != 1 or matches[0]["execution"] is None:
        _fail()
    return {
        "schema": RESOURCE_SCHEMA,
        "scope": "ORIGINAL_PROJECT_EXECUTION_RESOURCE",
        "selection": {"work_ref": history["work_ref"], "root_job_id": root_job_id},
        "history": deepcopy(history),
        "original_execution": deepcopy(matches[0]["execution"]),
        "original_input": {"state": "UNAVAILABLE", "reason": "RETAINED_INPUT_AUTHORITY_NOT_COMPOSED"},
        "current_adoption": {"state": "NOT_OBSERVED", "reason": "CURRENT_ADOPTION_NOT_READ"},
        "execution_authorized": False,
    }


def validate_resource(value, *, work_ref, root_job_id):
    if (type(value) is not dict or set(value) != {"schema", "scope", "selection", "history",
            "original_execution", "original_input", "current_adoption", "execution_authorized"}
            or value["schema"] != RESOURCE_SCHEMA
            or value["scope"] != "ORIGINAL_PROJECT_EXECUTION_RESOURCE"
            or value["execution_authorized"] is not False
            or value["selection"] != {"work_ref": work_ref, "root_job_id": root_job_id}
            or not _check_job_id(root_job_id)):
        _fail()
    history = validate_history(value["history"], work_ref=work_ref)
    expected = resource_from_history(history, root_job_id=root_job_id)
    if value != expected:
        _fail()
    return value
