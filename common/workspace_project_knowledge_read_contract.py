"""Three fixed project Knowledge reads under the incumbent Workspace principal.

Selectors carry opaque current source identities, never a path or a principal.
The capture body validators remain in workspace_project_knowledge_contract.
"""
from __future__ import annotations

import re
from common import executive_workspace_contract as workspace
from common.workspace_project_journal_contract import validate_selection as _work

FRAME_SCHEMA = "mastermind.workspace_project_knowledge_read.v1"
OPERATIONS = ("project_knowledge_catalogue", "project_knowledge_memory", "project_knowledge_source")
MAX_RESPONSE_BYTES = 131072


def selection(value, *, operation):
    if operation not in OPERATIONS or type(value) is not dict:
        raise ValueError("invalid_input")
    expected = {"work_ref", "source_ref", "expected_revision"} if operation == "project_knowledge_source" else {"work_ref"}
    if set(value) != expected:
        raise ValueError("invalid_input")
    _work({"work_ref": value["work_ref"]})
    if operation == "project_knowledge_source":
        if (type(value["source_ref"]) is not str
                or re.fullmatch(r"project-(?:file|record)\.v1\.[0-9a-f]{64}", value["source_ref"]) is None
                or type(value["expected_revision"]) is not str
                or re.fullmatch(r"[0-9a-f]{40}", value["expected_revision"]) is None):
            raise ValueError("invalid_input")
    return dict(value)


def validate_frame(value):
    if (type(value) is not dict or set(value) != {"schema", "operation", "selection", "principal"}
            or value["schema"] != FRAME_SCHEMA):
        raise ValueError("invalid_input")
    selected = selection(value["selection"], operation=value["operation"])
    workspace.validate_frame({"schema": workspace.FRAME_SCHEMA, "operation": "programs",
        "selection": None, "principal": value["principal"]})
    if len(workspace.canonical(value)) + 1 > workspace.MAX_REQUEST_BYTES:
        raise ValueError("invalid_input")
    return dict(value, selection=selected,
        principal=dict(value["principal"], scopes=list(value["principal"]["scopes"])))


def validate_body(value, *, operation):
    from common import workspace_project_knowledge_contract as body
    if operation == "project_knowledge_catalogue":
        return body.validate_catalogue(value)
    if operation == "project_knowledge_memory":
        return body.validate_memory(value)
    if operation == "project_knowledge_source":
        return body.validate_source(value)
    raise ValueError("invalid_input")


def unavailable(selected, *, operation, reason="SOURCE_UNAVAILABLE"):
    from common import workspace_project_knowledge_contract as body
    selected = selection(selected, operation=operation)
    if operation == "project_knowledge_source":
        return body.unavailable_source(selected["work_ref"], selected["source_ref"], reason)
    factory = body.unavailable_memory if operation == "project_knowledge_memory" else body.unavailable_catalogue
    return factory(selected["work_ref"], reason)
