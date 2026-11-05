"""Pure projector: one authored Agent OS workstream record -> closed plan body.

``project_workstream_plan`` is the whole surface of this module.  It takes an
ALREADY-PARSED canonical workstream record (the frontmatter mapping that the
sealed producer parser ``scripts/agentos.py`` returns) plus the selection and
source identity validated by
:mod:`common.workspace_project_plan_contract`, and returns one closed
response body.  It performs NO I/O, owns NO parser, NO transport, NO cache,
NO task lifecycle and NO UI; the authenticated Workspace reader and transport
are composed by the integrating parent.

Deliberate, closed behaviours:

* Explicit-field projection only.  Unknown record metadata is ignored -- never
  surfaced -- so raw body content, history, credentials, ``wait`` structures
  and record claims cannot leak into a public response.
* ``adoption`` is always ``{'state': 'UNAVAILABLE', 'reason': 'NOT_DECLARED'}``
  and ``version_history`` is always ``{'state': 'UNAVAILABLE', 'reason':
  'NOT_SUPPLIED_BY_OWNER'}``.  No generic adoption/version field exists in the
  canonical record; no execution plan, admitted step or Git publication may be
  relabelled as adopted plan approval.  Authentic Git record revision history
  is composed separately by the parent; versions are never invented here.
* Authored status values are reproduced verbatim.  A ``done`` workstream or
  wave is authored record state -- never runtime acceptance, merge state or
  approval.  No Git state is inferred; the authored ``pr`` reference is
  normalized to a ``prs`` list of positive integers with malformed tokens
  skipped exactly as the producer's own records view skips them, and nothing
  more.  Derived producer views (``deps_satisfied``, ``done_at``, PR
  observations) are NOT consumed; the projection reads the parsed canonical
  record only.
* Authored wave order and dependency IDs are preserved verbatim, forward
  dependencies (a wave depending on a later wave) are supported, and unknown
  dependencies, duplicate wave IDs, duplicate dependencies within one wave and
  dependency cycles (including self-dependency) are rejected as
  ``RECORD_INVALID``.
* Optional text is ``null`` when absent/empty; ``depends_on`` defaults to
  ``[]``; ``pr`` defaults to ``[]``.
* Any structurally invalid producer record returns the typed unavailable body
  with ``RECORD_INVALID`` -- never a partial plan and never an exception that
  would leak record content.  Output over :data:`MAX_RESPONSE_BYTES` returns
  the typed ``CONTENT_OVER_BUDGET`` body -- never a truncated plan.
* Every list, mapping and string in the returned body is freshly constructed:
  mutating the response cannot corrupt the caller's record and mutating the
  record after the call cannot change the response.  Repeated calls with equal
  inputs produce equal bodies with byte-identical JSON.
"""

from __future__ import annotations

import json
from collections.abc import Mapping

from common.workspace_project_plan_contract import (
    AVAILABILITY_AVAILABLE,
    BODY_KEYS,
    BODY_SCHEMA,
    MAX_RESPONSE_BYTES,
    REASON_CONTENT_OVER_BUDGET,
    REASON_RECORD_INVALID,
    unavailable,
    validate_source,
    work_ref_key,
)

# Projection bounds mandated by the commissioned read contract.  These bound
# what the projector will vouch for publicly; they are producer-neutral facts
# about this response, not new producer vocabulary.
MAX_TITLE_CHARS = 512
MAX_OBJECTIVE_CHARS = 16384
MAX_OWNER_CHARS = 256
MAX_NEXT_ACTION_CHARS = 16384
MAX_WORKSTREAM_STATUS_CHARS = 64
MAX_WAVES = 64
MAX_WAVE_ID_CHARS = 128
MAX_WAVE_TITLE_CHARS = 1024
MAX_WAVE_STATUS_CHARS = 32
MAX_WAVE_NEXT_ACTION_CHARS = 16384
MAX_DEPENDENCY_ID_CHARS = 128
MAX_PRS_PER_WAVE = 32

# Sentinel returned by helpers whose result is "producer record is invalid".
# A module-private object: no record content can ever collide with it.
_INVALID = object()

ADOPTION_STATE_UNAVAILABLE = "UNAVAILABLE"
ADOPTION_REASON_NOT_DECLARED = "NOT_DECLARED"
VERSION_HISTORY_STATE_UNAVAILABLE = "UNAVAILABLE"
VERSION_HISTORY_REASON_NOT_SUPPLIED_BY_OWNER = "NOT_SUPPLIED_BY_OWNER"


def _required_text(value: object, max_chars: int) -> object:
    """Required non-empty bounded text, projected verbatim."""
    if not isinstance(value, str):
        return _INVALID
    if not value.strip() or len(value) > max_chars:
        return _INVALID
    return value


def _optional_text(value: object, max_chars: int) -> object:
    """Optional bounded text: absent/None/blank projects to None."""
    if value is None:
        return None
    if not isinstance(value, str):
        return _INVALID
    if len(value) > max_chars:
        return _INVALID
    if not value.strip():
        return None
    return value


def _normalized_prs(raw: object) -> object:
    """Authored ``pr`` reference -> ``prs`` list of positive ints.

    Mirrors the producer's own reference view (``scripts/agentos.py``
    ``_wave_prs``): a scalar is treated as a one-item list, and tokens that
    are not positive ints or digit-only strings are SKIPPED, not rejected --
    an authored ``'#5593'``-style token is a malformed reference, and dropping
    it reproduces exactly what the producer's records view shows for that
    wave.  Non-positive integers are dropped too: this contract projects
    positive references only.  Authored order is preserved with no
    de-duplication, no re-ordering, and no Git state attached.  More kept
    references than :data:`MAX_PRS_PER_WAVE` is a typed invalid record --
    never a truncated reference list.
    """
    if raw is None:
        return []
    values = raw if isinstance(raw, list) else [raw]
    if not values:
        return []
    prs: list[int] = []
    for item in values:
        if isinstance(item, bool) or not isinstance(item, (int, str)):
            continue
        if isinstance(item, int):
            if item > 0:
                prs.append(item)
            continue
        token = item.strip()
        if token.isdigit():
            number = int(token)
            if number > 0:
                prs.append(number)
    if len(prs) > MAX_PRS_PER_WAVE:
        return _INVALID
    return prs


def _projected_waves(raw_waves: object) -> object:
    """Project waves in authored order with the exact six-field wave shape."""
    if not isinstance(raw_waves, list):
        return _INVALID
    if len(raw_waves) > MAX_WAVES:
        return _INVALID
    projected: list[dict] = []
    seen_ids: set[str] = set()
    for wave in raw_waves:
        if not isinstance(wave, Mapping):
            return _INVALID
        wave_id = wave.get("id")
        if (
            not isinstance(wave_id, str)
            or not wave_id
            or wave_id != wave_id.strip()
            or len(wave_id) > MAX_WAVE_ID_CHARS
        ):
            return _INVALID
        if wave_id in seen_ids:
            return _INVALID
        seen_ids.add(wave_id)

        title = wave.get("title")
        if not isinstance(title, str) or not title.strip() or len(title) > MAX_WAVE_TITLE_CHARS:
            return _INVALID
        status = wave.get("status")
        if (
            not isinstance(status, str)
            or not status.strip()
            or len(status) > MAX_WAVE_STATUS_CHARS
        ):
            return _INVALID

        raw_deps = wave.get("depends_on")
        if raw_deps is None:
            deps: list[str] = []
        else:
            if not isinstance(raw_deps, list):
                return _INVALID
            deps = []
            for dep in raw_deps:
                if (
                    not isinstance(dep, str)
                    or not dep
                    or len(dep) > MAX_DEPENDENCY_ID_CHARS
                ):
                    return _INVALID
                if dep in deps:
                    return _INVALID
                deps.append(dep)

        next_action = _optional_text(wave.get("next_action"), MAX_WAVE_NEXT_ACTION_CHARS)
        if next_action is _INVALID:
            return _INVALID
        prs = _normalized_prs(wave.get("pr"))
        if prs is _INVALID:
            return _INVALID

        projected.append(
            {
                "id": wave_id,
                "title": title,
                "status": status,
                "depends_on": deps,
                "next_action": next_action,
                "prs": prs,
            }
        )

    for wave in projected:
        for dep in wave["depends_on"]:
            if dep not in seen_ids:
                return _INVALID
    if _has_dependency_cycle(projected):
        return _INVALID
    return projected


def _has_dependency_cycle(waves: list) -> bool:
    """Iterative colouring DFS; forward dependencies alone are never a cycle."""
    graph = {wave["id"]: list(wave["depends_on"]) for wave in waves}
    settled: set[str] = set()
    for start in graph:
        if start in settled:
            continue
        visiting: set[str] = {start}
        stack = [(start, iter(graph[start]))]
        while stack:
            node, deps = stack[-1]
            advanced = False
            for dep in deps:
                if dep in visiting:
                    return True
                if dep not in settled:
                    visiting.add(dep)
                    stack.append((dep, iter(graph[dep])))
                    advanced = True
                    break
            if not advanced:
                visiting.discard(node)
                settled.add(node)
                stack.pop()
    return False


def _unavailable_record_invalid(work_ref: str) -> dict:
    return unavailable(work_ref, REASON_RECORD_INVALID)


def project_workstream_plan(record: object, *, work_ref: object, source: object) -> dict:
    """Project one parsed canonical workstream record into a closed plan body.

    ``record`` is the frontmatter mapping produced by the sealed producer
    parser for the selected canonical record.  ``work_ref`` is the strict
    ``WS:<KEY>`` selector and ``source`` the exact source identity; both are
    caller facts validated here first -- a malformed one raises ``ValueError``
    carrying the contract's closed constant, because that is a caller bug and
    must never be folded into a response body.

    Returns the closed available body with EXACT keys ``schema``, ``selection``,
    ``availability``, ``source``, ``plan``, ``reason_codes``, or the equally
    closed typed unavailable body for an invalid producer record
    (``RECORD_INVALID``) or an over-budget response (``CONTENT_OVER_BUDGET``).
    """
    key = work_ref_key(work_ref)
    source_identity = validate_source(source, work_ref)

    if not isinstance(record, Mapping):
        return _unavailable_record_invalid(work_ref)
    if record.get("key") != key:
        # The record at the pinned path must be the selected workstream; a
        # different key means the pinned bytes are not the selected record.
        return _unavailable_record_invalid(work_ref)

    title = _required_text(record.get("title"), MAX_TITLE_CHARS)
    if title is _INVALID:
        return _unavailable_record_invalid(work_ref)
    objective = _required_text(record.get("objective"), MAX_OBJECTIVE_CHARS)
    if objective is _INVALID:
        return _unavailable_record_invalid(work_ref)
    status = _required_text(record.get("status"), MAX_WORKSTREAM_STATUS_CHARS)
    if status is _INVALID:
        return _unavailable_record_invalid(work_ref)
    owner = _required_text(record.get("owner"), MAX_OWNER_CHARS)
    if owner is _INVALID:
        return _unavailable_record_invalid(work_ref)
    next_action = _optional_text(record.get("next_action"), MAX_NEXT_ACTION_CHARS)
    if next_action is _INVALID:
        return _unavailable_record_invalid(work_ref)
    waves = _projected_waves(record.get("waves"))
    if waves is _INVALID:
        return _unavailable_record_invalid(work_ref)

    plan = {
        "title": title,
        "objective": objective,
        "status": status,
        "owner": owner,
        "next_action": next_action,
        "waves": waves,
        "adoption": {
            "state": ADOPTION_STATE_UNAVAILABLE,
            "reason": ADOPTION_REASON_NOT_DECLARED,
        },
        "version_history": {
            "state": VERSION_HISTORY_STATE_UNAVAILABLE,
            "reason": VERSION_HISTORY_REASON_NOT_SUPPLIED_BY_OWNER,
        },
    }
    body = {
        "schema": BODY_SCHEMA,
        "selection": {"work_ref": work_ref},
        "availability": AVAILABILITY_AVAILABLE,
        "source": dict(source_identity),
        "plan": plan,
        "reason_codes": [],
    }
    if tuple(body.keys()) != BODY_KEYS:
        # Closed-shape guard: the literal above and the contract constant must
        # never drift apart.
        return _unavailable_record_invalid(work_ref)

    payload = json.dumps(body, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    if len(payload.encode("utf-8")) > MAX_RESPONSE_BYTES:
        # Typed unavailability, never a truncated plan.
        return unavailable(work_ref, REASON_CONTENT_OVER_BUDGET)
    return body


__all__ = [
    "ADOPTION_REASON_NOT_DECLARED",
    "ADOPTION_STATE_UNAVAILABLE",
    "MAX_DEPENDENCY_ID_CHARS",
    "MAX_NEXT_ACTION_CHARS",
    "MAX_OBJECTIVE_CHARS",
    "MAX_OWNER_CHARS",
    "MAX_PRS_PER_WAVE",
    "MAX_TITLE_CHARS",
    "MAX_WAVES",
    "MAX_WAVE_ID_CHARS",
    "MAX_WAVE_NEXT_ACTION_CHARS",
    "MAX_WAVE_STATUS_CHARS",
    "MAX_WAVE_TITLE_CHARS",
    "MAX_WORKSTREAM_STATUS_CHARS",
    "VERSION_HISTORY_REASON_NOT_SUPPLIED_BY_OWNER",
    "VERSION_HISTORY_STATE_UNAVAILABLE",
    "project_workstream_plan",
]
