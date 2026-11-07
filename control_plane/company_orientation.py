"""Closed authored strategy projection. DATA only; no evaluation or execution."""

from __future__ import annotations
from datetime import date
import copy, re

SCHEMA = "mastermind.authored_company_orientation.v1"
AUTHORITY = "advisory_and_orientation_only"


def validate(value):
    if (
        type(value) is not dict
        or set(value) != {"schema", "authority", "as_of"}
        or value["schema"] != SCHEMA
        or value["authority"] != AUTHORITY
    ):
        raise ValueError("company_orientation_invalid")
    if (
        type(value["as_of"]) is not str
        or date.fromisoformat(value["as_of"]).isoformat() != value["as_of"]
    ):
        raise ValueError("company_orientation_invalid")
    return copy.deepcopy(value)


def from_state(state):
    """Called only by the canonical validated StrategicState boot owner."""
    meta = state.get("meta", {})
    return validate(
        {
            "schema": SCHEMA,
            "authority": meta.get("authority"),
            "as_of": str(meta.get("as_of")),
        }
    )
