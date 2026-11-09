"""Explicit original-owner acquisition on the existing read-only transport.

This does not widen the incumbent three-key v4 decoder or v2 grammar. It
selects a separate closed operation whose owner input is composed at the host.
"""
from __future__ import annotations

import copy

from common.executive_workspace_contract import (
    FRAME_SCHEMA_V2, MAX_REQUEST_BYTES, canonical, v2_selection, validate_v2_frame,
)
from common.product_acceptance_read_contract import FRAME_SCHEMA

OPERATION = "mission_v4_original"


def selection(value):
    return v2_selection(value, "mission_v3")


def validate_frame(frame):
    if (type(frame) is not dict
            or set(frame) != {"schema", "operation", "selection", "principal"}
            or frame["schema"] != FRAME_SCHEMA or frame["operation"] != OPERATION):
        raise ValueError("invalid_input")
    validate_v2_frame({"schema": FRAME_SCHEMA_V2, "operation": "mission_v3",
        "selection": selection(frame["selection"]), "principal": frame["principal"]})
    if len(canonical(frame)) + 1 > MAX_REQUEST_BYTES:
        raise ValueError("invalid_input")
    return frame


def mission_frame(frame):
    """Return the detached existing two-key authenticated frame R2 consumes."""
    validate_frame(frame)
    return {"schema": FRAME_SCHEMA_V2, "operation": "mission_v3",
            "selection": selection(frame["selection"]),
            "principal": copy.deepcopy(frame["principal"])}
