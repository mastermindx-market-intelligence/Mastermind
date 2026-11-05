"""Bounded metadata decoder for Codex (0.159.2) progress notifications.

Converts a narrow slice of ``turn/plan/updated`` / ``item/started`` /
``item/completed`` notifications into inert, fixed-vocabulary metadata for an
existing hot projection.  The decoder is deliberately non-verbatim:

* ``source_item_id`` is ``"sha256:" + sha256(native item id)``; authored plans
  use the fixed id ``"authored-plan"``.  Native ids never survive decoding.
* ``kind``, ``state`` and ``summary`` come from closed vocabularies plus plan
  status counts.  Commands, tool names/arguments/results, reasoning, paths,
  explanations, plan step text and every unknown/private field are checked
  for shape at most and then discarded; they are never stringified or
  exposed.
* Unknown methods and unrecognized item types are ignored (``None``).  A
  foreign thread/turn, a malformed recognized payload, or a plan with more
  than 128 steps is refused with ``ValueError``.

States: ``item/started`` -> ``partial``; ``item/completed`` ->
``completed``; ``turn/plan/updated`` -> ``partial`` always, even when every authored
step is completed (an authored plan is planned work, not executed work).
Completed tool lifecycle summaries always state ``outcome unverified``.

Standard library only; pure functions; no I/O, no auth grant, no lifecycle or
ledger or provider access, no credentials, no reasoning capture, and no
import-time side effects.  Unit tests live beside the projection tests; parent integration and
publication are authorized separately elsewhere.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

__all__ = ["ProgressMetadata", "decode_progress"]

# Bounds for the recognized Codex 0.159.2 progress slice.
_IDENTITY_MAX_CHARS = 256
_PLAN_MAX_STEPS = 128
_SUMMARY_MAX_CHARS = 256

# Source identity vocabulary.
_ITEM_ID_PREFIX = "sha256:"
_PLAN_SOURCE_ITEM_ID = "authored-plan"

# Recognized notification methods.
_TURN_PLAN = "turn/plan/updated"
_ITEM_STARTED = "item/started"
_ITEM_COMPLETED = "item/completed"

# Fixed output vocabulary.
_KIND_PLAN = "plan"
_STATE_PARTIAL = "partial"
_STATE_COMPLETED = "completed"
_PLAN_STEP_STATUSES = ("pending", "inProgress", "completed")
_TOOL_ITEM_TYPES = frozenset({
    "commandExecution",
    "fileChange",
    "mcpToolCall",
    "dynamicToolCall",
    "collabAgentToolCall",
    "webSearch",
    "imageView",
    "sleep",
    "imageGeneration",
})
_SUMMARY_PLAN = (
    "authored plan (non-executable): {pending} pending, "
    "{in_progress} in progress, {completed} completed"
)
_SUMMARY_ITEM_STARTED = "tool started"
_SUMMARY_ITEM_COMPLETED = "tool lifecycle completed; outcome unverified"


@dataclass(frozen=True)
class ProgressMetadata:
    """Inert progress metadata; every field is fixed-vocabulary text."""

    source_item_id: str
    kind: str
    state: str
    summary: str


def _identity_ok(value: Any) -> bool:
    """True for a nonempty, bounded string identity."""
    return isinstance(value, str) and 0 < len(value) <= _IDENTITY_MAX_CHARS


def _fail(message: str) -> None:
    raise ValueError("codex_progress_metadata: " + message)


def decode_progress(
    method: Any,
    params: Any,
    *,
    thread_id: Any,
    turn_id: Any,
) -> ProgressMetadata | None:
    """Decode one Codex progress notification into bounded metadata.

    ``thread_id``/``turn_id`` are the caller's expected session identity.
    They are validated, then matched exactly against the event's own
    identity, before any payload parsing.

    Returns ``None`` for events outside the recognized slice (unknown
    method, unrecognized item type).  Raises ``ValueError`` when the expected
    identity is unusable, the event belongs to a foreign thread/turn, or a
    recognized payload is malformed (bad shapes, non-string or empty or
    oversized identities, missing declared fields, bool/float/string
    timestamps, unknown plan statuses, or more than 128 plan steps).
    """
    # Expected identity is validated before any payload parsing.
    if not _identity_ok(thread_id) or not _identity_ok(turn_id):
        _fail("thread_id/turn_id must be nonempty strings of at most 256 characters")
    if not isinstance(params, Mapping):
        _fail("params must be a mapping")
    # Only the declared identity fields are read here; every other key in
    # params is ignored outright and never stringified.
    if not _identity_ok(params.get("threadId")) or not _identity_ok(params.get("turnId")):
        _fail("params threadId/turnId must be nonempty strings of at most 256 characters")
    if params["threadId"] != thread_id or params["turnId"] != turn_id:
        _fail("event belongs to a foreign thread/turn")
    if not isinstance(method, str):
        _fail("method must be a string")

    if method == _TURN_PLAN:
        return _decode_plan(params)
    if method in (_ITEM_STARTED, _ITEM_COMPLETED):
        return _decode_item(method, params)
    return None  # Unknown method: ignored, never an error.


def _decode_plan(params: Mapping[str, Any]) -> ProgressMetadata:
    plan = params.get("plan")
    if not isinstance(plan, list):
        _fail("turn/plan params.plan must be a list")
    if len(plan) > _PLAN_MAX_STEPS:
        _fail("turn/plan params.plan exceeds the 128 step bound")
    counts = dict.fromkeys(_PLAN_STEP_STATUSES, 0)
    for index, entry in enumerate(plan):
        if not isinstance(entry, Mapping):
            _fail(f"plan step {index} must be a mapping")
        step = entry.get("step")
        status = entry.get("status")
        # Step text is shape-checked here and then dropped; it never reaches
        # the output.
        if not isinstance(step, str):
            _fail(f"plan step {index} 'step' must be a string")
        if not isinstance(status, str) or status not in counts:
            _fail(
                f"plan step {index} 'status' must be one of: "
                + ", ".join(_PLAN_STEP_STATUSES)
            )
        counts[status] += 1
    summary = _SUMMARY_PLAN.format(
        pending=counts["pending"],
        in_progress=counts["inProgress"],
        completed=counts["completed"],
    )
    if len(summary) > _SUMMARY_MAX_CHARS:  # Unreachable at <= 128 steps.
        _fail("summary exceeded its bound")
    return ProgressMetadata(
        source_item_id=_PLAN_SOURCE_ITEM_ID,
        kind=_KIND_PLAN,
        # Authored plans stay "partial" even when all authored steps are
        # completed: planned work is not executed work.
        state=_STATE_PARTIAL,
        summary=summary,
    )


def _decode_item(method: str, params: Mapping[str, Any]) -> ProgressMetadata | None:
    item = params.get("item")
    if not isinstance(item, Mapping):
        _fail(f"{method} params.item must be a mapping")
    item_type = item.get("type")
    if not isinstance(item_type, str) or item_type not in _TOOL_ITEM_TYPES:
        return None  # Unknown/private/reasoning item types: ignored.
    native_id = item.get("id")
    if not _identity_ok(native_id):
        _fail(f"{method} params.item.id must be a nonempty string of at most 256 characters")
    timestamp_key = "startedAtMs" if method == _ITEM_STARTED else "completedAtMs"
    if timestamp_key not in params:
        _fail(f"{method} params.{timestamp_key} is required (integer or null)")
    timestamp = params[timestamp_key]
    if timestamp is not None and (isinstance(timestamp, bool) or not isinstance(timestamp, int)):
        _fail(f"{method} params.{timestamp_key} must be an integer or null")
    # The native id exists only inside this expression; the output carries
    # the hash alone.
    source_item_id = _ITEM_ID_PREFIX + hashlib.sha256(native_id.encode("utf-8")).hexdigest()
    completed = method == _ITEM_COMPLETED
    return ProgressMetadata(
        source_item_id=source_item_id,
        kind=item_type,
        state=_STATE_COMPLETED if completed else _STATE_PARTIAL,
        # Started events make no outcome claim; a completed tool lifecycle
        # always states that the outcome is unverified here.
        summary=_SUMMARY_ITEM_COMPLETED if completed else _SUMMARY_ITEM_STARTED,
    )


