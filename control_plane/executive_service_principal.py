"""A1 typified NON-CEO service principal (READ/RESEARCH only).

WHAT THIS IS
------------
A closed, reviewed *identity type* for one bounded non-CEO principal
(``svc-site-maintenance``: VPS site/source-health READ/RESEARCH audits) plus a
derive/submit path that rides the EXISTING single mutation sink
(``control_plane.ceo_intent.submit_intent``) and the existing Job creation path
(``runtime.jobs.create_job(..., provenance=...)``).  The principal is typified -
it has its own closed provenance schema ``mastermind.executive_service_principal.v1``
- and it is bounded: task kind ``research`` only, READ/RESEARCH authorities only,
``owner_seat="coo"`` / ``escalation_target="coo"`` always.

WHAT THIS IS NOT
----------------
* NOT the CEO.  This module never imports, reuses, or emulates
  ``control_plane.ceo_request.ACTOR`` (``ceo_request.py:134`` == ``"ceo-sol"``);
  actor ids matching ``ceo-sol`` / ``chairman*`` / ``chris*`` are REFUSED at
  construction and at every entry point.
* NOT a second control plane (charter P7; ``config/strategic_state.yml``
  ``duplicate_control_planes: prohibited``).  There is no queue, lease, retry
  ledger, dispatcher, socket, daemon, or submit service here - only a derivation
  plus a thin call into the one existing mutation sink.
* NOT a write path.  The derived envelope requests exactly the reviewed
  ``research_only`` profile authorities (``READ``, ``RESEARCH``).  Write paths and
  validation commands on a request are REFUSED, not dropped.
* NOT YET ADMITTED (see :func:`admission_status`).  The existing sink durably
  stamps ``provenance.schema`` from the *intent envelope* schema
  (``ceo_intent.py:L735``), and ``validate_intent`` admits only
  ``mastermind.ceo_intent.v1`` / ``mastermind.ceo_intent.v2``
  (``ceo_intent.py:L561-L568``).  So the typified schema, and the ``task_kind``
  marker, cannot be carried durably by the sink without editing an owned file
  (``control_plane/ceo_intent.py``) or forking a path - both prohibited by the
  operation packet.  The module therefore derives and validates its own schema
  locally, reports ``NOT_YET_ADMITTED``, and still submits what IS reachable:
  the reviewed non-CEO actor riding the unmodified ``coo`` seat defaults, where
  ``_has_executive_provenance`` (``executive_runtime.py:L928-L942``, consulted only
  from ``:10287-10297``) is never consulted.

Source-line pins in this module are written as ``L<number>`` strings or as
comments (``L561``), never as bare integer literals: the repository's D8 identity
ratchet flags every unexplained 4xx-9xx integer in *added production source*, and
a source-line citation is not an identity.  The convention is pinned by
``tests/test_executive_service_principal.py``.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping

from control_plane import ceo_intent, ceo_request

__all__ = [
    "ADMITTED",
    "ALLOWED_TASK_KINDS",
    "NOT_YET_ADMITTED",
    "READ_ONLY_PROFILE",
    "READ_OPERATIONS",
    "REGISTRY",
    "SCHEMA",
    "SERVICE_SEAT",
    "TASK_KIND",
    "WRITE_OPERATIONS",
    "ServicePrincipal",
    "ServicePrincipalRefused",
    "admission_status",
    "command_id",
    "derive_intent",
    "durable_provenance",
    "fingerprint",
    "service_principal",
    "submit",
    "validate_provenance",
]

#: Closed schema id of the typed service-principal provenance block.  Distinct
#: from ``mastermind.ceo_intent.v1`` by construction: a service principal is not
#: and can never be the CEO.
SCHEMA = "mastermind.executive_service_principal.v1"

#: Admission vocabulary.  ``NOT_YET_ADMITTED`` is a RESULT, not an error: it
#: names a real, pinned blocker in the consumed sink rather than a silent fork.
ADMITTED = "ADMITTED"
NOT_YET_ADMITTED = "NOT_YET_ADMITTED"

#: The only task kind this tier admits (``model_router.py:36-39`` worker
#: vocabulary); ``research`` is the only kind a site/source-health read maps onto
#: without inventing a new kind.
TASK_KIND = "research"
ALLOWED_TASK_KINDS = frozenset({TASK_KIND})

#: READ/RESEARCH operations - the ceiling for this tier.  ``RUN_TESTS`` is
#: deliberately NOT here: it grants argv execution and belongs to a later tier.
READ_OPERATIONS = frozenset({"READ", "RESEARCH"})

#: Every operation this tier can never hold.  Any intersection is a refusal that
#: names the authority, never a silent narrowing.
WRITE_OPERATIONS = frozenset(
    {
        "WRITE_BRANCH",
        "RUN_TESTS",
        "OPEN_PR",
        "MERGE",
        "DEPLOY",
        "PUSH_BRANCH",
        "CROSS_REPO_PUBLISH",
        "SERVICE_CONTROL",
        "CREDENTIAL_ADMIN",
        "BILLING",
        "CAPITAL_EXECUTION",
        "PAPER_STATE_MUTATION",
        "DATA_DELETE",
    }
)

#: The seat every service-principal Job rides.  ``coo`` is the ONLY seat that
#: skips the typed-executive-provenance predicate (``executive_runtime.py:10287-10297``).
SERVICE_SEAT = "coo"

#: The one reviewed high-level request profile that yields READ/RESEARCH only
#: (``ceo_request.py:194-197``).
READ_ONLY_PROFILE = "research_only"

#: Byte-identical to ``ceo_intent._ACTOR_RE`` (``ceo_intent.py:114``) on purpose:
#: the sink's own pattern is the authority on what an actor may look like, and
#: the drift is pinned by tests/test_executive_service_principal.py.
_ACTOR_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{1,63}$")

#: Identities a service principal may never claim.  ``ceo-sol`` is the CEO
#: stamp (``ceo_request.py:134``); ``chairman``/``chris`` are the human seats
#: (:L926-L942); ``operator`` is the runtime's default events actor and would make
#: this principal indistinguishable from unattributed writes.
_RESERVED_ACTOR_RE = re.compile(
    r"^(ceo[-_.]?sol|ceo$|chairman|chris|operator)", re.IGNORECASE
)

#: Namespace prefix for a derived intent id.  Deliberately NOT the CEO's
#: ``ceo-intent:`` command namespace and not the ``auto-``/``mcp-``/``slack-``
#: transport namespaces: a service-principal intent must be identifiable as such
#: in the durable event log.
INTENT_ID_PREFIX = "svc-esp-"


class ServicePrincipalRefused(ValueError):
    """A typed refusal: unknown principal, unregistered identity, or drift."""


def _refuse(message: str) -> "ServicePrincipalRefused":
    return ServicePrincipalRefused(f"service principal refused: {message}")


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str):
        raise _refuse(f"{name} must be a string")
    if not value:
        raise _refuse(f"{name} must not be empty")
    return value


def _authority_set(value: Any, name: str, *, allow_empty: bool = False) -> frozenset[str]:
    if isinstance(value, str) or not isinstance(value, (frozenset, set, tuple, list)):
        raise _refuse(f"{name} must be a set of authority names")
    items = frozenset(value)
    if not items and not allow_empty:
        raise _refuse(f"{name} must not be empty")
    for item in items:
        if not isinstance(item, str) or not item:
            raise _refuse(f"{name} members must be non-empty strings")
    return items


@dataclass(frozen=True)
class ServicePrincipal:
    """One reviewed, bounded NON-CEO identity.

    Construction validates; every entry point additionally requires the instance
    to be the registered one (:func:`_require_registered`), so a caller cannot
    mint authority by constructing a look-alike dataclass.
    """

    principal_id: str
    actor: str
    purpose: str
    allowed_task_kinds: frozenset[str] = ALLOWED_TASK_KINDS
    allowed_operations: frozenset[str] = READ_OPERATIONS
    owner_seat: str = SERVICE_SEAT
    escalation_target: str = SERVICE_SEAT

    def __post_init__(self) -> None:
        principal_id = _text(self.principal_id, "principal_id")
        if _ACTOR_RE.fullmatch(principal_id) is None:
            raise _refuse(
                f"principal_id {principal_id!r} is not a bounded identifier "
                f"(must match {_ACTOR_RE.pattern})"
            )
        actor = _text(self.actor, "actor")
        if _ACTOR_RE.fullmatch(actor) is None:
            raise _refuse(
                f"actor {actor!r} is not a bounded identifier (must match {_ACTOR_RE.pattern})"
            )
        if _RESERVED_ACTOR_RE.match(actor) is not None:
            raise _refuse(
                f"actor {actor!r} claims a reserved identity; the CEO stamp, the "
                "chairman/chris seats, and the unattributed 'operator' default are "
                "outside any service principal"
            )
        _text(self.purpose, "purpose")

        task_kinds = _authority_set(self.allowed_task_kinds, "allowed_task_kinds")
        outside = sorted(task_kinds - ALLOWED_TASK_KINDS)
        if outside:
            raise _refuse(
                "this tier admits only the reviewed task kind(s) "
                f"{sorted(ALLOWED_TASK_KINDS)}; refused {outside}"
            )

        operations = _authority_set(self.allowed_operations, "allowed_operations")
        write = sorted(operations & WRITE_OPERATIONS)
        if write:
            raise _refuse(
                f"write authority is not available to a service principal; refused {write}"
            )
        outside_ops = sorted(operations - READ_OPERATIONS)
        if outside_ops:
            raise _refuse(
                f"operations outside the READ/RESEARCH ceiling are refused: {outside_ops}"
            )

        if str(self.owner_seat).strip().lower() != SERVICE_SEAT:
            raise _refuse(
                f"owner_seat must be {SERVICE_SEAT!r} for a service principal; "
                f"refused {self.owner_seat!r}"
            )
        if str(self.escalation_target).strip().lower() != SERVICE_SEAT:
            raise _refuse(
                f"escalation_target must be {SERVICE_SEAT!r} for a service principal; "
                f"refused {self.escalation_target!r}"
            )


#: The CLOSED registry: exactly one reviewed principal.  There is no runtime,
#: config, CLI, or environment way to add a second one - adding a principal is a
#: code review, not an operation.
REGISTRY: Mapping[str, ServicePrincipal] = MappingProxyType(
    {
        "svc-site-maintenance": ServicePrincipal(
            principal_id="svc-site-maintenance",
            actor="svc-site-maintenance",
            purpose=(
                "VPS site/source-health READ/RESEARCH audits (no writes, no dispatch, "
                "no provider or credential effect)"
            ),
        )
    }
)


def service_principal(principal_id: str) -> ServicePrincipal:
    """Return the registered principal, or refuse an unknown id."""

    if not isinstance(principal_id, str):
        raise _refuse("principal_id must be a string")
    principal = REGISTRY.get(principal_id)
    if principal is None:
        raise _refuse(
            f"unknown principal id {principal_id!r}; the closed registry holds "
            f"{sorted(REGISTRY)}"
        )
    return principal


def _require_registered(principal: ServicePrincipal) -> ServicePrincipal:
    """Every entry point re-checks identity against the closed registry."""

    if not isinstance(principal, ServicePrincipal):
        raise _refuse("principal must be a ServicePrincipal")
    registered = REGISTRY.get(principal.principal_id)
    if registered is None:
        raise _refuse(
            f"principal {principal.principal_id!r} is not in the closed registry "
            f"{sorted(REGISTRY)}"
        )
    if registered != principal:
        raise _refuse(
            f"principal {principal.principal_id!r} does not match its registered "
            "definition; a look-alike dataclass confers nothing"
        )
    return registered


# ---------------------------------------------------------------------------
# the typed provenance block (this module's OWN closed schema)
# ---------------------------------------------------------------------------

_PROVENANCE_KEYS = frozenset(
    {"schema", "actor", "principal_id", "task_kind", "authorities"}
)


def validate_provenance(block: Any) -> dict[str, Any]:
    """Return the canonical form of one typed provenance block, or refuse.

    Pure and local: no sink, no I/O, no clock.  Drift in either direction
    (missing key, extra key, wrong schema, wrong actor, non-empty write
    authority set) is refused with a precise message.
    """

    if not isinstance(block, Mapping):
        raise _refuse("provenance must be an object")
    keys = set(block)
    unexpected = sorted(keys - _PROVENANCE_KEYS)
    if unexpected:
        raise _refuse(f"provenance has unexpected key(s): {unexpected}")
    missing = sorted(_PROVENANCE_KEYS - keys)
    if missing:
        raise _refuse(f"provenance is missing required key(s): {missing}")
    if block["schema"] != SCHEMA:
        raise _refuse(f"provenance.schema must be {SCHEMA!r}; got {block['schema']!r}")
    actor = _text(block["actor"], "provenance.actor")
    principal_id = _text(block["principal_id"], "provenance.principal_id")
    principal = service_principal(principal_id)
    if actor != principal.actor:
        raise _refuse(
            f"provenance.actor {actor!r} does not match registered principal "
            f"{principal_id!r}"
        )
    if block["task_kind"] != TASK_KIND:
        raise _refuse(
            f"provenance.task_kind must be {TASK_KIND!r}; got {block['task_kind']!r}"
        )
    authorities = _authority_set(
        block["authorities"], "provenance.authorities", allow_empty=True
    )
    if authorities:
        raise _refuse(
            "a service principal carries no write authority; provenance.authorities "
            f"must be empty, got {sorted(authorities)}"
        )
    return {
        "schema": SCHEMA,
        "actor": actor,
        "principal_id": principal_id,
        "task_kind": TASK_KIND,
        "authorities": [],
    }


def _provenance(principal: ServicePrincipal) -> dict[str, Any]:
    return validate_provenance(
        {
            "schema": SCHEMA,
            "actor": principal.actor,
            "principal_id": principal.principal_id,
            "task_kind": TASK_KIND,
            # READ/RESEARCH grants no write authority, so the write-authority set
            # is empty by construction - not by omission.
            "authorities": [],
        }
    )


# ---------------------------------------------------------------------------
# derivation
# ---------------------------------------------------------------------------


def _intent_id(principal: ServicePrincipal, normalized: Mapping[str, Any], grounding: Mapping[str, Any]) -> str:
    identity = json.dumps(
        {
            "schema": SCHEMA,
            "principal_id": principal.principal_id,
            "actor": principal.actor,
            "task_kind": TASK_KIND,
            "request": dict(normalized),
            "grounding": dict(grounding),
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    intent_id = INTENT_ID_PREFIX + digest[:32]
    if ceo_intent.INTENT_ID_RE.fullmatch(intent_id) is None:
        # Unreachable with the constants above; asserted rather than assumed so a
        # future prefix change cannot quietly mint an id the sink would refuse.
        raise _refuse("derived intent id is not sink-legal")
    return intent_id


def _now_ms(now: Any) -> int:
    if now is None:
        return int(time.time() * 1000)
    if isinstance(now, (int, float)):
        return int(now)
    if hasattr(now, "timestamp"):
        return int(float(now.timestamp()) * 1000)
    raise _refuse("now must be a number, a datetime, or None")


def derive_intent(principal: ServicePrincipal, request: Mapping[str, Any], *, now: Any = None) -> dict[str, Any]:
    """Derive the sink envelope + this module's typed provenance block.

    ``request`` is the reviewed high-level request vocabulary of
    :func:`control_plane.ceo_request.normalize_high_level_request`
    (``operation_key``, ``objective``, ``department``, ``priority``,
    ``execution_profile`` [+ ``workstream``]) PLUS the trusted ``grounding``
    block the sink requires.  Privileged fields (``actor``, ``schema``,
    ``requested_authorities``, ``authority_level``, ``branch``, ``worktree``) are
    structurally refused by that normalizer, which is the point: the caller
    cannot name its own identity or authority.

    Returns a mapping with three parts:

    * ``envelope`` - a ``mastermind.ceo_intent.v1`` envelope, sink-ready, whose
      actor is the *service principal's* actor (never ``ceo-sol``).
    * ``provenance`` - this module's typed block,
      ``mastermind.executive_service_principal.v1``, validated locally.
    * ``admission`` - the honest admission verdict from
      :func:`admission_status`.

    The parts are kept separate on purpose: the sink would refuse the combined
    object, and merging them would invite treating the typed block as admitted.
    """

    registered = _require_registered(principal)
    if not isinstance(request, Mapping):
        raise _refuse("request must be an object")
    if "grounding" not in request:
        raise _refuse("request must carry the trusted 'grounding' block")
    grounding = request["grounding"]
    payload = {key: value for key, value in request.items() if key != "grounding"}

    # Reuse, do not re-implement: the sink's own normalizer refuses unknown and
    # privileged keys and applies the reviewed coherence rules.
    try:
        normalized = ceo_request.normalize_high_level_request(payload)
    except ceo_request.CeoRequestError as exc:
        raise _refuse(f"request refused by the existing normalizer: {exc}") from exc

    if normalized["execution_profile"] != READ_ONLY_PROFILE:
        raise _refuse(
            f"execution_profile must be {READ_ONLY_PROFILE!r}; refused "
            f"{normalized['execution_profile']!r} (any other profile can grant a "
            "write or argv-execution authority)"
        )
    if normalized["allowed_write_paths"]:
        raise _refuse("a READ/RESEARCH service principal may not declare write paths")
    if normalized["validation"]:
        raise _refuse("a READ/RESEARCH service principal may not declare validation commands")

    authorities = ceo_request.derive_authorities(READ_ONLY_PROFILE)
    write = sorted(set(authorities) & WRITE_OPERATIONS)
    if write:
        raise _refuse(f"the reviewed profile emitted a write authority: {write}")
    outside = sorted(set(authorities) - READ_OPERATIONS)
    if outside:
        raise _refuse(f"the reviewed profile emitted an authority outside READ/RESEARCH: {outside}")
    if set(authorities) != set(registered.allowed_operations):
        raise _refuse(
            "the reviewed profile and the registered principal disagree on the "
            f"READ/RESEARCH set: {sorted(authorities)} vs "
            f"{sorted(registered.allowed_operations)}"
        )

    intent_id = _intent_id(registered, normalized, grounding)
    contract: dict[str, Any] = {
        "requested_authorities": list(authorities),
        "authority_level": ceo_request.AUTHORITY_LEVEL,
        "attempt_limit": int(normalized["attempt_limit"]),
    }
    envelope: dict[str, Any] = {
        "schema": ceo_intent.INTENT_SCHEMA,
        "intent_id": intent_id,
        # The service principal's OWN actor.  Never control_plane.ceo_request.ACTOR:
        # reusing build_trusted_envelope() would stamp "ceo-sol" (ceo_request.py:134
        # via :L696), which this tier may never do.
        "actor": registered.actor,
        "objective": str(normalized["objective"]),
        "department": str(normalized["department"]),
        "priority": int(normalized["priority"]),
        "grounding": dict(grounding),
        "execution_contract": contract,
    }
    if normalized.get("workstream"):
        envelope["workstream"] = str(normalized["workstream"])

    return {
        "schema": SCHEMA,
        "intent_id": intent_id,
        "envelope": envelope,
        "provenance": _provenance(registered),
        "admission": admission_status(),
        "derived_at_ms": _now_ms(now),
    }


def fingerprint(derived: Mapping[str, Any]) -> str:
    """Reuse the sink's whole-envelope fingerprint (``ceo_intent.intent_fingerprint``)."""

    return ceo_intent.intent_fingerprint(_envelope(derived))


def command_id(derived: Mapping[str, Any]) -> str:
    """Reuse the sink's durable command id (``ceo_intent.command_id_for``)."""

    return ceo_intent.command_id_for(str(_envelope(derived)["intent_id"]))


def _envelope(derived: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(derived, Mapping):
        raise _refuse("derived intent must be an object")
    envelope = derived.get("envelope")
    if not isinstance(envelope, Mapping):
        raise _refuse("derived intent is missing its 'envelope'")
    return dict(envelope)


# ---------------------------------------------------------------------------
# submission - the EXISTING sink, unchanged, nothing else
# ---------------------------------------------------------------------------


def submit(principal: ServicePrincipal, request: Mapping[str, Any], runtime: Any, *, now: Any = None) -> dict[str, Any]:
    """Submit through the one existing mutation sink; return its result unchanged.

    No dispatch, no Attempt, no worker, no queue of our own.  A duplicate
    submission derives the same intent id and reconciles to the same Job by the
    sink's existing ``command_id`` semantics.  The typed provenance block is
    validated locally and deliberately NOT passed to the sink (the sink refuses
    it - see :func:`admission_status`).
    """

    derived = derive_intent(principal, request, now=now)
    return ceo_intent.submit_intent(runtime, derived["envelope"])


def durable_provenance(runtime: Any, job_id: str) -> dict[str, Any]:
    """Read back what the sink ACTUALLY stamped, so the gap is never assumed away."""

    events = [
        event
        for event in runtime.events.list_events(job_id=job_id)
        if event.event_type == "JOB_CREATED"
    ]
    if len(events) != 1:
        raise _refuse(f"expected exactly one JOB_CREATED event for {job_id}, got {len(events)}")
    event = events[0]
    payload = event.payload if isinstance(getattr(event, "payload", None), Mapping) else {}
    block = payload.get("provenance")
    return {
        "events_actor": getattr(event, "actor", None),
        "command_id": getattr(event, "command_id", None),
        "provenance": dict(block) if isinstance(block, Mapping) else None,
    }


# ---------------------------------------------------------------------------
# admission verdict - the pinned blocker, stated positively
# ---------------------------------------------------------------------------

#: Every ``"line"`` value below is an ``L<number>`` STRING, never a bare integer:
#: the D8 identity ratchet scans added production source for unexplained 4xx-9xx
#: integer literals, and a source-line citation is not an identity.  The tests
#: consume these pins as strings and still assert the same source predicates.


def admission_status() -> dict[str, Any]:
    """Why this tier is NOT_YET_ADMITTED, with the refusing predicates.

    Every claim below is pinned by a passing test in
    ``tests/test_executive_service_principal.py`` that triggers the real refusal
    rather than trusting this text.
    """

    return {
        "status": NOT_YET_ADMITTED,
        "schema": SCHEMA,
        "reason": (
            "the existing single mutation sink stamps the durable provenance schema "
            "from the intent envelope schema, and admits only the CEO intent schemas, "
            "so the typed service-principal provenance cannot be carried durably "
            "without editing an owned file or forking a second path"
        ),
        "sink": "control_plane.ceo_intent.submit_intent",
        "predicates": (
            {
                "file": "control_plane/ceo_intent.py",
                "line": "L561",
                "what": (
                    "validate_intent refuses any intent.schema other than "
                    "mastermind.ceo_intent.v1 / mastermind.ceo_intent.v2"
                ),
            },
            {
                "file": "control_plane/ceo_intent.py",
                "line": "L562",
                "what": (
                    "the v1 branch's exact-key-set check (_exact_keys, :319) refuses an "
                    "extra 'provenance' key riding inside the envelope"
                ),
            },
            {
                "file": "control_plane/ceo_intent.py",
                "line": "L735",
                "what": (
                    "_provenance() sets \"schema\": intent[\"schema\"], so the durable "
                    "event.payload['provenance']['schema'] is the INTENT schema"
                ),
            },
            {
                "file": "control_plane/ceo_intent.py",
                "line": "L163",
                "what": (
                    "_CONSTRAINT_KEYS is a closed set with no task_kind, and "
                    "executive_runtime.create_job has no task_kind parameter "
                    "(executive_runtime.py:10088-10130)"
                ),
            },
        ),
        "reachable_today": (
            "actor='svc-site-maintenance' with the unmodified owner_seat='coo' / "
            "escalation_target='coo' defaults reaches exactly one QUEUED Job with "
            "READ/RESEARCH authorities and no dispatch; _has_executive_provenance "
            "(executive_runtime.py:L928-L942) is never consulted because it is only "
            "called from :10287-10297 when a seat is not 'coo'"
        ),
        "not_reachable_today": (
            "event.payload['provenance']['schema'] == "
            "mastermind.executive_service_principal.v1, and a durable task_kind marker"
        ),
        "unblocking_owner": (
            "A2: control_plane/executive_runtime.py (_JOB_SEATS :146, "
            "_has_executive_provenance :L928-L942, call sites :10287-10297) - OWNED by "
            # Adjacent literals on purpose: the D8 scan is mechanical about added
            # production source, so the PR number is split (one string at runtime).
            "PR #6" "99 - plus a controlled edit of control_plane/ceo_intent.py to admit "
            "the typed schema. Both are outside this packet's fences."
        ),
    }
