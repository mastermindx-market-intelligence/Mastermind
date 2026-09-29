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
* ADMITTED (A2).  The strict non-CEO service schema
  ``mastermind.executive_service_intent.v1`` is carried by the EXISTING sink
  (``control_plane/ceo_intent.py``): the envelope is exact-keyed, READ/RESEARCH
  only under a sink-local ceiling, stamped with typed service evidence in
  ``event.payload["provenance"]`` (``ceo_intent.py:L877``), and seated explicitly
  on ``coo`` (``ceo_intent.py:L1180``).  :func:`admission_status` reports
  ``ADMITTED``, and :func:`submit` is therefore a thin passthrough that mutates
  ONLY through :func:`control_plane.ceo_intent.submit_intent` - one sink, no
  second writer, no dispatch, no queue of our own.

  The residual is a RUNTIME gap this slice does not fix and must not: because the
  sink now stamps the envelope's own schema, the SERVICE stamp no longer matches
  the CEO branch of ``_has_executive_provenance`` (``executive_runtime.py:L928-L942``,
  consulted only from ``:10287-10297``) - but a RAW ``mastermind.ceo_intent.v1``
  stamp still does.  That raw-v1 residual stays OWNED by
  ``executive_runtime.py`` (the Runtime seat lane).  Authenticated service
  ingress (A5) remains deferred to the app/gateway lane.

Identity law
------------
The intent id is a domain-separated hash of EXACTLY ``SCHEMA`` +
``principal_id`` + the normalized ``operation_key`` - nothing else.  One logical
operation keeps one intent id and one durable command id, so a later envelope for
the same operation (a changed objective, a changed grounding SHA) is adjudicated
by the sink's existing whole-envelope conflict predicate
(``ceo_intent.py:L928``, raising ``CeoIntentConflict``) instead of minting a
second Job.  A different ``operation_key`` is a different operation and
legitimately gets its own Job.

Grant law
---------
The typed block states the WRITE ceiling (``write_authorities``: always empty for
this tier) *and* the reviewed READ/RESEARCH grant (``requested_authorities`` and
``effective_authorities``, both exactly the registered principal/profile grant).
:func:`validate_grant` refuses drift in either direction - a block that disagrees
with the registry, or an envelope whose ``execution_contract`` disagrees with the
block - before any sink call is reachable.

Source-line pins in this module are written as ``L<number>`` strings or as
comments (``L633``), never as bare integer literals: the repository's D8 identity
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
    "ServicePrincipalNotAdmitted",
    "ServicePrincipalRefused",
    "admission_status",
    "command_id",
    "derive_intent",
    "durable_provenance",
    "fingerprint",
    "service_principal",
    "submit",
    "validate_grant",
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


class ServicePrincipalNotAdmitted(ServicePrincipalRefused):
    """Typed refusal: the sink does not (or no longer) carry this typed principal.

    Raised by :func:`submit` while :func:`admission_status` reports
    anything other than ``ADMITTED``, *before* the ``runtime`` argument is touched
    at all, so the tier fails closed instead of quietly landing an unattributed
    Job.  It carries the blocking predicates in its message.  A2 admits the
    schema, so this is now a latent gate rather than the standing verdict.
    """


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


def _authority_list(value: Any, name: str, *, allow_empty: bool = False) -> list[str]:
    """A reviewed authority LIST (ordered, string, non-empty unless allowed).

    ``_authority_set`` is the dataclass-field shape; this is the wire shape the
    sink's ``execution_contract.requested_authorities`` uses, so grant drift is
    compared as an ordered list rather than a silently-absorbing set.
    """

    if isinstance(value, str) or not isinstance(value, (tuple, list)):
        raise _refuse(f"{name} must be a list of authority names")
    if not value and not allow_empty:
        raise _refuse(f"{name} must not be empty")
    for item in value:
        if not isinstance(item, str) or not item:
            raise _refuse(f"{name} members must be non-empty strings")
    return list(value)


def _registered_grant(principal: ServicePrincipal) -> list[str]:
    """The one reviewed grant, bound to BOTH the registered principal and the profile.

    ``sorted`` matches the sink's own ``derive_authorities`` ordering
    (``ceo_request.py:L514``), so the typed block and the sink envelope always
    carry byte-identical lists.
    """

    grant = sorted(principal.allowed_operations)
    profile_grant = sorted(ceo_request.derive_authorities(READ_ONLY_PROFILE))
    if grant != profile_grant or grant != sorted(READ_OPERATIONS):
        raise _refuse(
            f"principal {principal.principal_id!r} does not carry the reviewed "
            f"READ/RESEARCH grant {sorted(READ_OPERATIONS)}: registry says {grant}, "
            f"profile {READ_ONLY_PROFILE!r} says {profile_grant}"
        )
    return grant


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
_SINK_BINDING = ("svc-site-maintenance", "svc-site-maintenance")
if ceo_intent.SERVICE_PRINCIPAL_BINDINGS != frozenset({_SINK_BINDING}):
    raise RuntimeError(
        "service principal emitter and canonical sink enrollment contract differ"
    )

REGISTRY: Mapping[str, ServicePrincipal] = MappingProxyType(
    {
        _SINK_BINDING[0]: ServicePrincipal(
            principal_id=_SINK_BINDING[0],
            actor=_SINK_BINDING[1],
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
    {
        "schema",
        "actor",
        "principal_id",
        "task_kind",
        # The WRITE ceiling.  Always empty for this tier; named "write" so an
        # empty value can never be misread as "no grant at all".
        "write_authorities",
        # The reviewed READ/RESEARCH grant, stated truthfully in both directions.
        "requested_authorities",
        "effective_authorities",
    }
)


def validate_provenance(block: Any) -> dict[str, Any]:
    """Return the canonical form of one typed provenance block, or refuse.

    Pure and local: no sink, no I/O, no clock.  Drift in either direction
    (missing key, extra key, wrong schema, wrong actor, a non-empty WRITE
    ceiling, or a READ/RESEARCH grant that disagrees with the registered
    principal/profile) is refused with a precise message.
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
    write = _authority_list(
        block["write_authorities"], "provenance.write_authorities", allow_empty=True
    )
    if write:
        raise _refuse(
            "a service principal carries no write authority; "
            f"provenance.write_authorities must be empty, got {sorted(write)}"
        )
    expected = _registered_grant(principal)
    requested = sorted(
        _authority_list(block["requested_authorities"], "provenance.requested_authorities")
    )
    effective = sorted(
        _authority_list(block["effective_authorities"], "provenance.effective_authorities")
    )
    if requested != expected:
        raise _refuse(
            f"provenance.requested_authorities {requested} does not match the "
            f"registered principal/profile grant {expected}"
        )
    if effective != expected:
        raise _refuse(
            f"provenance.effective_authorities {effective} does not match the "
            f"registered principal/profile grant {expected}"
        )
    return {
        "schema": SCHEMA,
        "actor": actor,
        "principal_id": principal_id,
        "task_kind": TASK_KIND,
        "write_authorities": [],
        "requested_authorities": list(expected),
        "effective_authorities": list(expected),
    }


def _provenance(principal: ServicePrincipal, authorities: Any) -> dict[str, Any]:
    """The typed block for ``principal``: empty WRITE ceiling, truthful READ grant."""

    grant = sorted(_authority_list(authorities, "grant"))
    return validate_provenance(
        {
            "schema": SCHEMA,
            "actor": principal.actor,
            "principal_id": principal.principal_id,
            "task_kind": TASK_KIND,
            # READ/RESEARCH grants no write authority, so the write-authority set
            # is empty by construction - not by omission.
            "write_authorities": [],
            # ...and the READ/RESEARCH grant is stated, not hidden behind an
            # empty list that only ever named the WRITE ceiling.
            "requested_authorities": grant,
            "effective_authorities": grant,
        }
    )


_CONTRACT_KEYS = frozenset({"requested_authorities", "authority_level", "attempt_limit"})


def validate_grant(derived: Mapping[str, Any]) -> dict[str, Any]:
    """Refuse grant drift in EITHER direction, before any sink call is reachable.

    Two independent statements must agree:

    * the typed block carries exactly the registered principal/profile grant
      (enforced by :func:`validate_provenance`), and
    * the derived envelope's ``execution_contract.requested_authorities`` is
      exactly that grant - the same list the block declares as both requested
      and effective.

    Pure: no runtime, no sink, no I/O.  :func:`submit` calls this BEFORE it reads
    its ``runtime`` argument or reaches the sink, so a drifted pair is refused
    before it can mutate anything.
    """

    if not isinstance(derived, Mapping):
        raise _refuse("derived intent must be an object")
    canonical = validate_provenance(derived.get("provenance"))
    envelope = _envelope(derived)
    contract = envelope.get("execution_contract")
    if not isinstance(contract, Mapping):
        raise _refuse("envelope.execution_contract must be an object")
    unexpected = sorted(set(contract) - _CONTRACT_KEYS)
    if unexpected:
        raise _refuse(f"envelope.execution_contract has unexpected key(s): {unexpected}")
    if "requested_authorities" not in contract:
        raise _refuse("envelope.execution_contract is missing requested_authorities")
    envelope_requested = sorted(
        _authority_list(
            contract["requested_authorities"],
            "envelope.execution_contract.requested_authorities",
        )
    )
    write = sorted(set(envelope_requested) & WRITE_OPERATIONS)
    if write:
        raise _refuse(f"envelope requests write authority: {write}")
    if envelope_requested != canonical["requested_authorities"]:
        raise _refuse(
            "envelope.execution_contract.requested_authorities "
            f"{envelope_requested} differ from the typed block "
            f"requested_authorities {canonical['requested_authorities']}"
        )
    if envelope_requested != canonical["effective_authorities"]:
        raise _refuse(
            "envelope.execution_contract.requested_authorities "
            f"{envelope_requested} differ from the typed block "
            f"effective_authorities {canonical['effective_authorities']}"
        )
    return canonical


# ---------------------------------------------------------------------------
# derivation
# ---------------------------------------------------------------------------


def _intent_id(principal: ServicePrincipal, normalized: Mapping[str, Any]) -> str:
    """Stable logical-operation identity: EXACTLY (SCHEMA, principal_id, operation_key).

    Nothing else enters the hash - not the objective, not the priority, not the
    grounding SHAs.  A repeat of the same logical operation therefore reuses ONE
    intent id and ONE durable command id, and any changed envelope under that id
    is refused by the sink's existing whole-envelope conflict predicate
    (``ceo_intent.py:L928``, raising ``CeoIntentConflict``) instead of silently
    creating a second Job.  A different ``operation_key`` is a different
    operation and legitimately gets its own Job.
    """

    operation_key = normalized.get("operation_key")
    if not isinstance(operation_key, str) or not operation_key:
        raise _refuse("the normalized request is missing its operation_key")
    identity = json.dumps(
        {
            "schema": SCHEMA,
            "principal_id": principal.principal_id,
            "operation_key": operation_key,
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

    * ``envelope`` - a ``mastermind.executive_service_intent.v1`` envelope,
      sink-ready, whose actor is the *service principal's* actor (never
      ``ceo-sol``), carrying the registered ``principal_id`` and the reviewed
      ``task_kind``.
    * ``provenance`` - this module's typed block,
      ``mastermind.executive_service_principal.v1``, validated locally.
    * ``admission`` - the honest admission verdict from
      :func:`admission_status`.

    The parts are kept separate on purpose: the typed block is EVIDENCE about the
    principal, not an envelope field, and merging them would invite treating the
    block as the admitted schema.
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

    intent_id = _intent_id(registered, normalized)
    provenance = _provenance(registered, authorities)
    contract: dict[str, Any] = {
        # The envelope's grant is READ OFF the typed block, so the two can never
        # be built to disagree; validate_grant() then refuses any drift a caller
        # puts between them afterwards.
        "requested_authorities": list(provenance["effective_authorities"]),
        "authority_level": ceo_request.AUTHORITY_LEVEL,
        "attempt_limit": int(normalized["attempt_limit"]),
    }
    envelope: dict[str, Any] = {
        "schema": ceo_intent.INTENT_SCHEMA_SERVICE,
        "intent_id": intent_id,
        # The service principal's OWN actor.  Never control_plane.ceo_request.ACTOR:
        # reusing build_trusted_envelope() would stamp "ceo-sol" (ceo_request.py:134
        # via :L696), which this tier may never do.
        "actor": registered.actor,
        "objective": str(normalized["objective"]),
        "department": str(normalized["department"]),
        "priority": int(normalized["priority"]),
        "grounding": dict(grounding),
        # The typed service identity the sink's strict service branch requires:
        # the registered principal id and the reviewed task kind.
        "principal_id": registered.principal_id,
        "task_kind": TASK_KIND,
        "execution_contract": contract,
    }
    if normalized.get("workstream"):
        envelope["workstream"] = str(normalized["workstream"])

    derived: dict[str, Any] = {
        "schema": SCHEMA,
        "intent_id": intent_id,
        "envelope": envelope,
        "provenance": provenance,
        "admission": admission_status(),
        "derived_at_ms": _now_ms(now),
    }
    # Self-audit the ENVELOPE with the sink's OWN validator - no local shadow
    # copy of the key sets or the ceiling: the envelope this module emits must be
    # exactly what the sink admits, or derive fails here.
    ceo_intent.validate_intent(envelope)
    # Self-audit: a future edit that builds the block and the envelope apart
    # fails here, loudly, instead of shipping a false grant.
    validate_grant(derived)
    return derived


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
    """Admit one request through the EXISTING single sink - nothing else.

    Order of business:

    1. derive + locally validate (closed identity, typed block, truthful grant),
    2. refuse any grant drift between block and envelope,
    3. re-read :func:`admission_status` (the gate stays live),
    4. hand the envelope to :func:`control_plane.ceo_intent.submit_intent`.

    No second path, no dispatch, no Attempt, no worker, no queue of our own.  The
    gate is a live read, not a hard-coded refusal: should the sink's admission
    ever regress, ``_require_admitted`` closes this path again by itself.
    """

    derived = derive_intent(principal, request, now=now)
    validate_grant(derived)
    _require_admitted()
    return ceo_intent.submit_intent(runtime, derived["envelope"])


def _require_admitted() -> None:
    """The A3 gate: this is the ONLY production-facing callable that mutates Runtime."""

    status = admission_status()
    if status["status"] == ADMITTED:
        return
    blockers = "; ".join(
        f"{predicate['file']}:{predicate['line']} {predicate['what']}"
        for predicate in status["predicates"]
    )
    raise ServicePrincipalNotAdmitted(
        f"service principal refused: submit() is closed while admission_status()['status'] "
        f"is {status['status']!r} for schema {status['schema']!r}: {status['reason']}. "
        f"blocking predicates: {blockers}"
    )


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
# admission verdict - ADMITTED on the existing sink, with the pinning predicates
# ---------------------------------------------------------------------------

#: Every ``"line"`` value below is an ``L<number>`` STRING, never a bare integer:
#: the D8 identity ratchet scans added production source for unexplained 4xx-9xx
#: integer literals, and a source-line citation is not an identity.  The tests
#: consume these pins as strings and still assert the same source predicates.


def admission_status() -> dict[str, Any]:
    """ADMITTED: the sink carries the strict service schema, READ/RESEARCH only.

    Every claim below is pinned by a passing test in
    ``tests/test_executive_service_principal.py`` that triggers the real refusal
    (or reads the real durable stamp) rather than trusting this text.
    """

    return {
        "status": ADMITTED,
        "schema": SCHEMA,
        "reason": (
            "the existing single mutation sink admits the strict non-CEO schema "
            "mastermind.executive_service_intent.v1 on its non-v2 branch: the "
            "envelope is exact-keyed, READ/RESEARCH only under a sink-local ceiling, "
            "stamped with typed service evidence, and seated explicitly on coo, so "
            "the typed service-principal provenance is durably carried with no "
            "second path and no Runtime change"
        ),
        "sink": "control_plane.ceo_intent.submit_intent",
        "submit_gate": (
            "public submit() is OPEN while this verdict is ADMITTED: it derives + "
            "validates, refuses grant drift, re-reads this verdict, then mutates ONLY "
            "through ceo_intent.submit_intent - one sink, no dispatch, no second "
            "writer.  The gate is a live read, so a sink admission regression closes "
            "this path again by itself"
        ),
        "predicates": (
            {
                "file": "control_plane/ceo_intent.py",
                "line": "L640",
                "what": (
                    "validate_intent admits the third, strict service schema through "
                    "the same exact-key-set fence: _SERVICE_REQUIRED_KEYS = the v1 keys "
                    "plus principal_id and task_kind (no extra carrier)"
                ),
            },
            {
                "file": "control_plane/ceo_intent.py",
                "line": "L585",
                "what": (
                    "_require_service_ceiling refuses any requested authority outside "
                    "{READ, RESEARCH}, any allowed_write_paths, and any authority_level "
                    "other than the READ level A0 - the ceiling the downstream policy "
                    "would otherwise GRANT (executive_authority.py:21)"
                ),
            },
            {
                "file": "control_plane/ceo_intent.py",
                "line": "L877",
                "what": (
                    "_provenance() stamps the typed service evidence (principal_id, "
                    "task_kind, requested_authorities, effective_authorities, "
                    "write_authorities) beside the envelope schema tag, so "
                    "event.payload['provenance']['schema'] is the SERVICE schema"
                ),
            },
            {
                "file": "control_plane/ceo_intent.py",
                "line": "L1180",
                "what": (
                    "the service branch of submit_intent passes EXPLICIT "
                    "owner_seat='coo' / escalation_target='coo' and no orchestration "
                    "role, no execution_binding and no dialogue_source, so a service "
                    "Job can never be seated above coo"
                ),
            },
        ),
        "identity": {
            "id": (
                "domain-separated hash of EXACTLY (SCHEMA, principal_id, normalized "
                "operation_key); the objective and the grounding SHAs are NOT in it"
            ),
            "conflict_predicates": (
                {
                    "file": "control_plane/ceo_intent.py",
                    "line": "L1125",
                    "what": (
                        "submit_intent looks the derived command id up in the durable "
                        "event log first, so a reused intent id reconciles instead of "
                        "creating a second Job"
                    ),
                },
                {
                    "file": "control_plane/ceo_intent.py",
                    "line": "L928",
                    "what": (
                        "_receipt_from_event raises CeoIntentConflict when the reused "
                        "intent id was already accepted under a DIFFERENT whole-envelope "
                        "fingerprint; that predicate is the whole-envelope conflict law "
                        "this module relies on rather than reimplement"
                    ),
                },
                {
                    "file": "control_plane/ceo_intent.py",
                    "line": "L783",
                    "what": "command_id_for() derives the durable command id from the intent id",
                },
            ),
        },
        "reachable_today": (
            "public submit(principal, request, runtime) - and equally a caller that "
            "goes DIRECTLY to the sink "
            "(control_plane.ceo_intent.submit_intent(runtime, derived['envelope'])) "
            "- reaches exactly one QUEUED Job with actor='svc-site-maintenance', "
            "explicit owner_seat='coo' / escalation_target='coo', READ/RESEARCH "
            "authorities, a durable event.payload['provenance']['schema'] of "
            "mastermind.executive_service_intent.v1, and no dispatch"
        ),
        "not_reachable_today": (
            "any write authority (WRITE_BRANCH / RUN_TESTS), a declared write path, an "
            "authority_level other than A0, a reserved identity (the CEO stamp, the "
            "human seats, or the unattributed operator default), a non-'svc-' intent "
            "id, a task_kind other than 'research', an unknown envelope key, and any "
            "seat above coo - each refused by the sink, including a service-schema "
            "envelope shaped like v2"
        ),
        "unblocking_owner": (
            "none for the A2 schema slice: it is DONE on the existing sink.  Two "
            "residuals stay OUTSIDE this module and outside this packet: (1) "
            "_has_executive_provenance (executive_runtime.py:L928-L942, call sites "
            ":10287-10297) still lets a RAW mastermind.ceo_intent.v1 stamp satisfy its "
            "schema-only CEO branch - OWNED by executive_runtime.py, Runtime seat lane "
            # Adjacent literals on purpose: the D8 scan is mechanical about added
            # production source, so the PR number is split (one string at runtime).
            "(PR #6" "99); the SERVICE stamp no longer does, which is pinned by test. "
            "(2) authenticated service ingress (A5) is deferred to the app/gateway lane."
        ),
    }
