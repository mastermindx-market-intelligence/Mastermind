"""Draft an ``agentos.handoff.v1`` checkpoint for a consumed child.

This does not write the Macro Agent OS store. The parent files a valid draft
through the existing writer. ``model`` stays inside the admitted enum; this
module does not invent a Hermes model value.
"""
from __future__ import annotations

from typing import Any, Mapping


SCHEMA = "agentos.handoff.v1"
MODELS = frozenset({"fable", "opus", "sonnet", "haiku", "codex", "local", "sol"})
ENDED = frozenset({"complete", "ci_handoff", "blocked", "context_budget", "crashed"})
REQUIRED = (
    "workstream",
    "session",
    "model",
    "ended_because",
    "mission",
    "state_before",
    "changed",
    "verified",
    "unverified",
    "unresolved",
    "next_actions",
    "do_not_redo",
    "danger_areas",
)
FORBIDDEN_PHRASES = ("see above", "as discussed")


class HandoffError(ValueError):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _scan(value: Any) -> None:
    if isinstance(value, str):
        lowered = value.lower()
        for phrase in FORBIDDEN_PHRASES:
            if phrase in lowered:
                raise HandoffError("HANDOFF_PHRASE_FORBIDDEN")
    elif isinstance(value, list):
        for item in value:
            _scan(item)
    elif isinstance(value, dict):
        for item in value.values():
            _scan(item)


def validate_handoff(document: Mapping[str, Any]) -> None:
    if not isinstance(document, Mapping):
        raise HandoffError("HANDOFF_INVALID")
    if document.get("schema") != SCHEMA:
        raise HandoffError("HANDOFF_SCHEMA_INVALID")
    missing = [key for key in REQUIRED if key not in document]
    if missing:
        raise HandoffError("HANDOFF_FIELDS_MISSING")
    workstream = document["workstream"]
    if not isinstance(workstream, str) or not workstream.startswith("WS:") or len(workstream) < 5:
        raise HandoffError("HANDOFF_WORKSTREAM_INVALID")
    if document["model"] not in MODELS:
        raise HandoffError("HANDOFF_MODEL_NOT_ADMITTED")
    if document["ended_because"] not in ENDED:
        raise HandoffError("HANDOFF_ENDED_BECAUSE_INVALID")
    for field in ("mission", "state_before", "session"):
        if not isinstance(document[field], str) or not document[field].strip():
            raise HandoffError("HANDOFF_INVALID")
    changed = document["changed"]
    verified = document["verified"]
    unverified = document["unverified"]
    if not isinstance(changed, list) or not isinstance(verified, list) or not isinstance(unverified, list):
        raise HandoffError("HANDOFF_INVALID")
    for item in changed:
        if not isinstance(item, dict) or not item.get("path") or not item.get("what"):
            raise HandoffError("HANDOFF_CHANGED_INVALID")
    for item in verified:
        if not isinstance(item, dict) or not all(isinstance(item.get(key), str) and item[key] for key in ("claim", "command", "result")):
            raise HandoffError("HANDOFF_VERIFIED_INVALID")
    for item in unverified:
        if not isinstance(item, dict) or not item.get("claim") or not item.get("what_would_verify"):
            raise HandoffError("HANDOFF_UNVERIFIED_INVALID")
    for field in ("unresolved", "next_actions", "do_not_redo", "danger_areas"):
        if not isinstance(document[field], list):
            raise HandoffError("HANDOFF_INVALID")
    _scan(document)


def render_child_handoff(
    *,
    workstream: str,
    session: str,
    model: str,
    submission: Mapping[str, Any],
    result_sha256: str,
) -> dict[str, Any]:
    key = submission["idempotency_key"]
    document = {
        "schema": SCHEMA,
        "workstream": workstream,
        "session": session,
        "model": model,
        "ended_because": "complete",
        "mission": submission["objective"],
        "state_before": (
            f"Child {key} was admitted and submitted on {submission['carrier']} "
            f"as {submission['child_kind']} and had not been consumed."
        ),
        "changed": [],
        "verified": [
            {
                "claim": f"Parent consumed child {key} once after an independent review of {result_sha256}.",
                "command": f"mmx_delegate consume {key}",
                "result": result_sha256,
            }
        ],
        "unverified": [
            {
                "claim": "Parent-local consumption is not Executive acceptance and not a fabric_task.py accept.",
                "what_would_verify": (
                    "The existing Executive owner readback of this idempotency key and "
                    "fabric_task.py accept --by reviewer on the same run, by a reviewer who is not the parent."
                ),
            }
        ],
        "unresolved": [
            "Live Executive admission and a real carrier submit remain unauthorized.",
        ],
        "next_actions": [
            f"File this draft only through the existing Agent OS writer. Do not resubmit {key}.",
        ],
        "do_not_redo": [
            f"Do not replay idempotency key {key}.",
            "Do not rehome a refused or UNKNOWN child onto the other carrier.",
        ],
        "danger_areas": [
            "UNKNOWN is sticky. A lost carrier reply is not permission to submit again or switch carriers.",
        ],
    }
    validate_handoff(document)
    return document
