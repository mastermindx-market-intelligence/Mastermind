"""Closed READ-only Control Room presentation over the incumbent Workspace app.

Same signed Workspace principal and existing private App-peer socket; a
different frame kind prevents control-room action names being interpreted as
Workspace reads. No caller-supplied URL, filesystem path or auth grant.
"""
from __future__ import annotations

from common.executive_workspace_contract import (
    FRAME_SCHEMA as WORKSPACE_SCHEMA,
    MAX_REQUEST_BYTES, canonical,
    validate_frame as validate_workspace_frame,
)

FRAME_SCHEMA = "mastermind.workspace_control_room_read.v1"
OPERATIONS = frozenset({"state", "discover"})


def validate_frame(value):
    if (type(value) is not dict
            or set(value) != {"schema", "operation", "principal"}
            or value["schema"] != FRAME_SCHEMA
            or type(value["operation"]) is not str
            or value["operation"] not in OPERATIONS
            or len(canonical(value)) + 1 > MAX_REQUEST_BYTES):
        raise ValueError("invalid_input")
    # Reuse *exact* incumbent principal grammar and audience/scope law.
    validate_workspace_frame({"schema": WORKSPACE_SCHEMA, "operation": "programs",
                              "selection": None, "principal": value["principal"]})
    return value
