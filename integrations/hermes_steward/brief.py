"""Company-read briefing from the incumbent Steward: pure projection, no new owner.

The existing six Steward tools own grounding. This view selects ONE caller-bound
responsibility, not a best-fit workstream or a new task. Nothing here writes,
schedules, dispatches, chooses a provider, or injects system instructions.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from integrations.hermes_steward.client import StewardReadClient

from integrations.mastermind_secretary_mcp.schemas import (
    GatewayError, validate_tool_arguments,
)

BRIEF_SCHEMA = "mastermind.hermes_steward_brief.v1"
_READS = ("get_responsibility", "get_current_runtime", "explain_blocker")


def responsibility_brief(
    reader: StewardReadClient,
    *,
    responsibility_ref: str,
    authorization: object,
) -> dict[str, Any]:
    """Materialize read-only verified facts for one EXACT responsibility.

    Every tool is still authorized and grounded by the existing Steward owner;
    the returned document is only a model/UI input with explicit provenance.
    If a credential fails on any read, discard earlier sections rather than
    expose a stale partly-authorized card. UNKNOWN is never interpreted as
    no attention, no blocker, or completed company work.
    """
    try:
        bound = validate_tool_arguments(
            "get_responsibility", {"responsibility_ref": responsibility_ref},
        )
    except GatewayError:
        return _empty("INVALID_RESPONSIBILITY_REF", responsibility_ref=None)
    if not isinstance(reader, StewardReadClient):
        return _empty("READ_PORT_UNAVAILABLE", responsibility_ref=bound["responsibility_ref"])

    ref = bound["responsibility_ref"]
    sections: list[dict[str, Any]] = []
    for name in _READS:
        try:
            result = reader.read_grounded(
                name, {"responsibility_ref": ref}, authorization=authorization,
            )
        except Exception:
            # A host-side exception might embed a bearer or private path.
            return _empty("READ_PORT_UNAVAILABLE", responsibility_ref=ref)
        if not isinstance(result, Mapping) or result.get("ok") is not True:
            # A revoked/scope-mismatched token makes the *whole* snapshot
            # unavailable. No partial data is published after authorization loss.
            return _empty("READ_NOT_AUTHORIZED_OR_VERIFIED", responsibility_ref=ref)
        upstream = result.get("data")
        if not isinstance(upstream, Mapping) or upstream.get("ok") is not True:
            return _empty("READ_NOT_AUTHORIZED_OR_VERIFIED", responsibility_ref=ref)
        payload = upstream.get("data")
        if not isinstance(payload, Mapping) or not isinstance(payload.get("subjects"), list):
            return _empty("READ_NOT_AUTHORIZED_OR_VERIFIED", responsibility_ref=ref)
        subjects = payload["subjects"]
        if any(
            not isinstance(row, Mapping) or row.get("subject_ref") != ref
            for row in subjects
        ):
            return _empty("READ_NOT_AUTHORIZED_OR_VERIFIED", responsibility_ref=ref)
        facts = [
            {
                "predicate": fact["predicate"],
                "value": fact["value"],
                "freshness": fact["freshness"],
                "sources": fact["sources"],
            }
            for row in subjects
            for fact in row["facts"]
        ]
        sections.append({
            "tool": name,
            "state": payload["state"],
            "reason_codes": payload["reason_codes"],
            "facts": facts,
        })

    usable = all(
        section["state"] == "FACTS"
        and section["facts"]
        and all(fact["freshness"] == "FRESH" for fact in section["facts"])
        for section in sections
    )
    partial = any(section["facts"] for section in sections)
    return {
        "schema": BRIEF_SCHEMA,
        "responsibility_ref": ref,
        "status": "FACTS" if usable else "PARTIAL" if partial else "UNKNOWN",
        "sections": sections,
        "reason": None,
        "effect": "NONE",
        "company_completion_proven": False,
    }


def _empty(reason: str, *, responsibility_ref: str | None) -> dict[str, Any]:
    return {
        "schema": BRIEF_SCHEMA,
        "responsibility_ref": responsibility_ref,
        "status": "REFUSED",
        "sections": [],
        "reason": reason,
        "effect": "NONE",
        "company_completion_proven": False,
    }
