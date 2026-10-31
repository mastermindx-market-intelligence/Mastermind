"""Producer for the executive workspace result-references route.

One actual bounded Fabric v3 acquisition per accepted frame, bracketed by
the existing control-room cache snapshot pair exactly as the Mission v3
route brackets it.  Sole-root admission stays with the existing
``_join``/``_qualified`` guards before Runtime is ever touched; the SAME
source observation stays with the existing ``_observation``; companion and
index strict validation stays with the existing Mission workspace
validators.  This module only joins those owners and translates every
refusal into the frozen typed UNAVAILABLE body — never into synthesized
index facts, a truncated partition, or a fabricated absence.

Authentication and final permission remain the existing frame owner's
unchanged responsibility; the producer neither authorizes nor re-checks
the principal.  A missing or ambiguous sole root keeps refusing with the
existing ``LookupError`` before acquisition, which the transport maps to
the actual 404.
"""

from __future__ import annotations

from common.executive_workspace_contract import MAX_RESULT_RESPONSE_BYTES, canonical
from common.executive_workspace_result_references_contract import (
    INDEX_AVAILABILITY_STATES,
    REASON_CODES,
    SCHEMA,
    frame_selection,
    unavailable,
    validate_body,
)


class _TypedUnavailable(Exception):
    """Typed refusal carrying exactly one closed result-references reason."""

    def __init__(self, reason):
        if reason not in REASON_CODES:
            raise ValueError(
                f"result-references refusal reason {reason!r} not in "
                f"REASON_CODES={sorted(REASON_CODES)}")
        super().__init__(reason)
        self.reason = reason


def read_result_references(owner, frame):
    """Handle one ``result_references`` frame for the existing frame owner.

    Returns ``{ok: True, result: BODY}`` — with an AVAILABLE body only when
    the sole root was admitted from a fresh qualified cache bracket, one
    actual bounded Fabric v3 acquisition finalized SAME survived the paired
    after-bracket, and the actual index passed the existing strict
    validators inside the frozen response budget.  Every other outcome is
    the typed UNAVAILABLE body for exactly one closed reason code.
    """
    selected = frame_selection(frame)
    try:
        body = _produce(owner, selected)
    except _TypedUnavailable as refusal:
        return unavailable(selected, refusal.reason)
    return {"ok": True, "result": validate_body(body, selected)}


def _produce(owner, selected):
    from control_plane.workspace_read_service import _join, _observation, _qualified
    cache = getattr(owner, "cache", None)
    if not hasattr(cache, "snapshot"):
        raise _TypedUnavailable("SOURCE_UNAVAILABLE")
    try:
        before = cache.snapshot()
    except _TypedUnavailable:
        raise
    except Exception:
        raise _TypedUnavailable("SOURCE_UNAVAILABLE") from None
    # The existing sole-root guard refuses with LookupError before Runtime
    # is touched; the frame owner preserves that actual 404.
    _join(before.document, selected)
    if not _qualified(before, selected):
        raise _TypedUnavailable("SOURCE_UNAVAILABLE")
    companion = _acquire(owner, selected)
    try:
        after = cache.snapshot()
    except _TypedUnavailable:
        raise
    except Exception:
        raise _TypedUnavailable("SOURCE_UNAVAILABLE") from None
    row = _join(after.document, selected)
    if not _qualified(after, selected):
        raise _TypedUnavailable("SOURCE_UNAVAILABLE")
    index = _finalized_index(companion, selected)
    # The canonical Fabric owner returns only after observation physical
    # close; the five-key runtime receipt is bound to the finalized index
    # generation by construction and re-checked inside the contract.
    observation = _observation(before, after, selected, dict(index["generation"]))
    state = observation["state"]
    if state != "SAME":
        raise _TypedUnavailable(
            "SOURCE_CHANGED" if state == "CONFLICT" else "SOURCE_UNAVAILABLE")
    body = {
        "schema": SCHEMA,
        "selection": selected,
        "availability": "AVAILABLE",
        "reason_codes": [],
        "index": index,
        "source_observation": observation,
        "catalogue": _catalogue(row, after.document),
    }
    if len(canonical({"ok": True, "result": body})) + 1 > MAX_RESULT_RESPONSE_BYTES:
        # Neither truncating the index nor fabricating absent/omitted
        # partitions after the fact is legal: the whole body becomes the
        # typed over-budget unavailable shape instead.
        raise _TypedUnavailable("OVER_BUDGET")
    return body


def _acquire(owner, selected):
    """One actual bounded Fabric v3 acquisition through the existing seam."""
    acquire = getattr(owner, "_mission_v3_acquire", None)
    if acquire is None:
        from control_plane.fabric_job_view import read_fabric_view_v3_from_runtime
        acquire = read_fabric_view_v3_from_runtime
    bounded = getattr(owner, "_bounded_runtime", None)
    runtime = owner.runtime
    observed_runtime = bounded(runtime) if bounded is not None else runtime
    try:
        companion = acquire(observed_runtime, selected["root_job_id"],
                            armed=owner.armed, runtime_identity=owner.runtime_identity)
    except _TypedUnavailable:
        raise
    except Exception:
        # A missing, unstarted or failing Runtime owner stays a source
        # refusal; it is never laundered into a usable index.
        raise _TypedUnavailable("SOURCE_UNAVAILABLE") from None
    if type(companion) is not dict:
        raise _TypedUnavailable("REFERENCE_INDEX_UNAVAILABLE")
    return companion


def _finalized_index(companion, selected):
    """Strict existing validation, then the finalized-readable refusal gate."""
    from control_plane.mission_workspace import (
        _validate_companion_against_v2,
        _validate_fabric_v3_companion,
        _validate_result_reference_index,
    )
    try:
        fabric = _validate_fabric_v3_companion(companion)
        index = _validate_result_reference_index(fabric["result_refs"])
        _validate_companion_against_v2(
            index, nested_v2=fabric["fabric_view"],
            selected_root_job_id=selected["root_job_id"])
    except _TypedUnavailable:
        raise
    except Exception:
        raise _TypedUnavailable("REFERENCE_INDEX_UNAVAILABLE") from None
    if index["availability"] not in INDEX_AVAILABILITY_STATES:
        raise _TypedUnavailable("REFERENCE_INDEX_UNAVAILABLE")
    if index["generation"]["state"] != "SAME":
        raise _TypedUnavailable("REFERENCE_INDEX_UNAVAILABLE")
    return index


def _catalogue(row, document):
    """Orientation only — no ``mission_current`` field, no CURRENT assertion.

    The row freshness fact is the existing projection mapper's
    ``_freshness_for`` verdict for the selected responsibility at the
    actual control-room reference clock; a recognized stale or unknown row
    still reads and is reported as such.
    """
    from control_plane.workspace_read_service import (
        _FRESHNESS_CURRENT,
        _FRESHNESS_NONCURRENT,
    )
    stale, unknown = _FRESHNESS_NONCURRENT
    freshness = {
        _FRESHNESS_CURRENT: "CURRENT",
        stale: "STALE",
        unknown: "UNKNOWN",
    }
    sources = document.get("sources", {})
    stamp = sources.get("agent_os_state_generated_at") if isinstance(sources, dict) else None
    return {"generated_at": stamp,
            "freshness": freshness[row["freshness"]]}
